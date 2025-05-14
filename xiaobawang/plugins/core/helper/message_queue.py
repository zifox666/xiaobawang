import asyncio
from typing import Dict, List, Any
import time
from collections import defaultdict

from nonebot import logger
from nonebot_plugin_alconna import Target, UniMessage, get_bot, CustomNode

from ..utils.common.cache import save_msg_cache


class MessageQueueSender:
    def __init__(self, check_interval: int = 60):
        """
        初始化消息队列发送器

        Args:
            check_interval: 检查队列的时间间隔(秒)
        """
        self.check_interval = check_interval
        self.message_queue = defaultdict(list)  # {(platform, bot_id, session_id, session_type): [messages]}
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

    def add_message(self, platform: str, bot_id: str, session_id: str,
                    session_type: str, message_content: Any, metadata: Dict = None):
        """
        添加消息到队列

        Args:
            platform: 平台名称
            bot_id: 机器人ID
            session_id: 会话ID
            session_type: 会话类型 (private/group)
            message_content: 消息内容
            metadata: 额外的元数据 (如链接等)
        """
        queue_key = (platform, bot_id, session_id, session_type)

        message = {
            "content": message_content,
            "metadata": metadata or {},
            "timestamp": time.time()
        }

        self.message_queue[queue_key].append(message)
        logger.debug(f"已添加消息到队列: {platform}:{session_id}")

    async def _process_queue_loop(self):
        """持续处理队列的循环"""
        while self.running:
            try:
                await self._process_all_queues()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"处理消息队列时出错: {e}")
                await asyncio.sleep(10)

    async def _process_all_queues(self):
        """处理所有队列中的消息"""
        if not self.message_queue:
            return

        current_queues = dict(self.message_queue)
        self.message_queue.clear()

        for queue_key, messages in current_queues.items():
            if not messages:
                continue

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

            if len(messages) > 3:
                merged_nodes = []
                for msg in messages:
                    content = msg["content"]
                    node = CustomNode(
                        uid="2382766384",
                        name="小霸王Bot",
                        content=content + UniMessage.text(msg["metadata"].get("url", "")),
                    )
                    merged_nodes.append(node)
                send_event = await (
                    UniMessage
                    .reference(*merged_nodes)
                    .send(
                        bot=bot,
                        target=target,
                    )
                )

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


message_sender = MessageQueueSender()


async def queue_killmail_message(
        platform: str,
        bot_id: str,
        session_id: str,
        session_type: str,
        pic: bytes,
        reason: str,
        kill_id: str
):
    """将击杀邮件添加到消息队列"""
    if not pic:
        return

    content = UniMessage.text(reason) + UniMessage.image(raw=pic)
    metadata = {"url": f'https://zkillboard.com/kill/{kill_id}/'}

    message_sender.add_message(
        platform=platform,
        bot_id=bot_id,
        session_id=session_id,
        session_type=session_type,
        message_content=content,
        metadata=metadata
    )
    logger.debug(f"已添加击杀邮件 {kill_id} 到队列")
