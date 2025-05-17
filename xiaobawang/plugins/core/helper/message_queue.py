import asyncio
from typing import Dict, List, Any
import time
from collections import defaultdict

from nonebot import logger
from nonebot_plugin_alconna import Target, UniMessage, get_bot, CustomNode

from ..utils.common.cache import save_msg_cache


class MessageQueueSender:
    def __init__(
            self,
            check_interval: int = 45,
            max_wait_time: int = 180,
            threshold_for_extended_wait: int = 5
    ):
        """
        初始化消息队列发送器

        Args:
            check_interval: 基本检查队列的时间间隔(秒)
            max_wait_time: 消息堆积时的最大等待时间(秒)
            threshold_for_extended_wait: 触发延长等待的消息阈值
        """
        self.check_interval = check_interval
        self.max_wait_time = max_wait_time
        self.threshold_for_extended_wait = threshold_for_extended_wait
        self.message_queue = defaultdict(list)  # {(platform, bot_id, session_id, session_type): [messages]}
        self.queue_last_active = {}  # 记录队列最后活跃时间 {queue_key: timestamp}
        self.running = False
        self.task = None

        self.platform_handlers = {
            "OneBot V11": self._handle_onebot_v11
        }

    async def start(self):
        """启动消息队列处理任务"""
        if self.running:
            return

        self.running = True
        self.task = asyncio.create_task(self._process_queue_loop())
        logger.info("消息队列发送器已启动")

    async def stop(self):
        """停止消息队列处理任务"""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("消息队列发送器已停止")

    async def add_message(
            self,
            platform: str,
            bot_id: str,
            session_id: str,
            session_type: str,
            message_content: Any,
            metadata: Dict = None,
            immediate: bool = False
    ):
        """
        添加消息到队列

        Args:
            platform: 平台名称
            bot_id: 机器人ID
            session_id: 会话ID
            session_type: 会话类型 (private/group)
            message_content: 消息内容
            metadata: 额外的元数据 (如链接等)
            immediate: 是否立即发送消息
        """
        queue_key = (platform, bot_id, session_id, session_type)

        message = {
            "content": message_content,
            "metadata": metadata or {},
            "timestamp": time.time()
        }

        if immediate:
            await self._handle_default(platform, bot_id, session_id, session_type, [message])
            logger.debug(f"立即发送消息到队列: {platform}:{session_id}")
        else:
            self.queue_last_active[queue_key] = time.time()
            self.message_queue[queue_key].append(message)
            logger.debug(f"已添加消息到队列: {platform}:{session_id} 当前队列长度: {len(self.message_queue[queue_key])}")

    async def _process_queue_loop(self):
        """持续处理队列的循环"""
        while self.running:
            try:
                current_time = time.time()
                queues_to_process = []

                for queue_key, messages in self.message_queue.items():
                    if not messages:
                        continue

                    last_active = self.queue_last_active.get(queue_key, current_time)
                    wait_time = current_time - last_active

                    if len(messages) > self.threshold_for_extended_wait:
                        adjusted_wait_time = min(
                            self.check_interval * (1 + len(messages) / 10),
                            self.max_wait_time
                        )

                        if wait_time >= adjusted_wait_time or wait_time >= self.max_wait_time * 0.8:
                            queues_to_process.append(queue_key)
                            logger.debug(
                                f"队列 {queue_key} 消息数量: {len(messages)}，已等待: {wait_time:.1f}秒, 开始推送")
                    else:
                        if wait_time >= self.check_interval:
                            queues_to_process.append(queue_key)

                if queues_to_process:
                    await self._process_selected_queues(queues_to_process)

                await asyncio.sleep(min(10, self.check_interval / 2))

            except Exception as e:
                logger.error(f"处理消息队列时出错: {e}")
                await asyncio.sleep(10)

    async def _process_selected_queues(self, queue_keys):
        """处理选定的消息队列"""
        for queue_key in queue_keys:
            if queue_key not in self.message_queue:
                continue

            messages = self.message_queue[queue_key]
            if not messages:
                continue

            del self.message_queue[queue_key]
            if queue_key in self.queue_last_active:
                del self.queue_last_active[queue_key]

            platform, bot_id, session_id, session_type = queue_key

            try:
                if platform in self.platform_handlers:
                    await self.platform_handlers[platform](bot_id, session_id, session_type, messages)
                else:
                    await self._handle_default(platform, bot_id, session_id, session_type, messages)
            except Exception as e:
                logger.error(f"处理队列 {platform}:{session_id} 时出错: {e}")

    async def _handle_default(
            self,
            platform: str,
            bot_id: str,
            session_id: str,
            session_type: str,
            messages: List[Dict]
    ):
        """默认的消息处理方法"""
        if not messages:
            return

        try:
            bot = await get_bot(adapter=platform, bot_id=bot_id)
            target = Target(
                id=session_id,
                private=(session_type == "private")
            )

            for msg in messages:
                content = msg["content"]
                metadata = msg["metadata"]

                send_event = await UniMessage(content).send(
                    bot=bot,
                    target=target
                )

                if "url" in metadata:
                    await save_msg_cache(send_event, metadata["url"])

        except Exception as e:
            logger.error(f"发送消息到 {platform}:{session_id} 失败: {e}")

    async def _handle_onebot_v11(
            self,
            bot_id: str,
            session_id: str,
            session_type: str,
            messages: List[Dict]
    ):
        """OneBot V11 平台的特殊处理，支持合并发送"""
        if not messages:
            return

        try:
            bot = await get_bot(adapter="OneBot V11", bot_id=bot_id)
            is_private = (session_type == "private")
            target = Target(
                id=session_id,
                private=is_private
            )

            if len(messages) > 2:
                merged_nodes = []

                max_messages = 80

                if len(messages) > max_messages:
                    logger.warning(f"消息数量({len(messages)})超过限制，将只发送最新的{max_messages}条")
                    messages = messages[-max_messages:]

                for msg in messages:
                    content = msg["content"]
                    metadata = msg["metadata"]

                    node = CustomNode(
                        uid=bot_id,
                        name="小霸王Bot",
                        content=content + UniMessage.text(metadata.get("url", ""))
                    )
                    merged_nodes.append(node)

                send_event = await UniMessage.reference(*merged_nodes).send(
                    bot=bot,
                    target=target
                )

                logger.info(f"已发送合并消息到 {session_id}，共{len(messages)}条")
            else:
                for msg in messages:
                    content = msg["content"]
                    metadata = msg["metadata"]

                    send_event = await UniMessage(content).send(
                        bot=bot,
                        target=target
                    )

                    if "url" in metadata:
                        await save_msg_cache(send_event, metadata["url"])

        except Exception as e:
            logger.error(f"发送消息到 OneBot V11:{session_id} 失败: {e}")

    def register_platform_handler(self, platform: str, handler):
        """注册平台特定的处理器"""
        self.platform_handlers[platform] = handler


message_sender = MessageQueueSender(check_interval=45, max_wait_time=180, threshold_for_extended_wait=5)


async def queue_killmail_message(
        platform: str,
        bot_id: str,
        session_id: str,
        session_type: str,
        pic: bytes,
        reason: str,
        kill_id: str,
        immediate: bool = False
):
    """将击杀邮件添加到消息队列"""
    if not pic:
        return

    content = UniMessage.text(reason) + UniMessage.image(raw=pic)
    metadata = {"url": f'https://zkillboard.com/kill/{kill_id}/'}

    await message_sender.add_message(
        platform=platform,
        bot_id=bot_id,
        session_id=session_id,
        session_type=session_type,
        message_content=content,
        metadata=metadata,
        immediate=immediate
    )
    if not immediate:
        logger.debug(f"已添加击杀邮件 {kill_id} 到队列")
