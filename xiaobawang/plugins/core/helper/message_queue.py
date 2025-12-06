import asyncio
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
import time
import traceback
from typing import Any

from nonebot import logger
from nonebot_plugin_alconna import CustomNode, Target, UniMessage, get_bot
from nonebot_plugin_orm import get_session

from ..api.statics import upload_statistics
from ..config import plugin_config
from ..db.models.record import KillmailPushRecord
from ..utils.common.cache import save_msg_cache


class MessageQueueSender:
    def __init__(
            self,
            check_interval: int = 45,
            max_wait_time: int = 180,
            threshold_for_extended_wait: int = 5,
            per_queue_max_messages: int = 200,
            immediate_flush_count: int = 30
    ):
        """
        初始化消息队列发送器

        Args:
            check_interval: 基本检查队列的时间间隔(秒)
            max_wait_time: 消息堆积时的最大等待时间(秒)
            threshold_for_extended_wait: 触发延长等待的消息阈值
            per_queue_max_messages: 每个会话允许保留的最大消息数（超过则丢弃最旧）
            immediate_flush_count: 当单个队列达到该条数时立即触发发送（不等待周期）
        """
        self.check_interval = check_interval
        self.max_wait_time = max_wait_time
        self.threshold_for_extended_wait = threshold_for_extended_wait
        self.per_queue_max_messages = per_queue_max_messages
        # 到达该阈值时立即触发该会话队列的发送（仅触发一次，触发条件为 len == immediate_flush_count）
        self.immediate_flush_count = int(immediate_flush_count)
        # 使用有界 deque 以自动丢弃最旧消息，防止内存无限增长
        # 强制转为 int 以避免类型检查器认为为 float
        # {(platform, bot_id, session_id, session_type): deque([messages])}
        self.message_queue = defaultdict(lambda: deque(maxlen=int(self.per_queue_max_messages)))
        self.queue_last_active = {}  # 记录队列最后活跃时间 {queue_key: timestamp}
        self.running = False
        self.task = None

        self.platform_handlers = {"OneBot V11": self._handle_onebot_v11}

        # 临时图片存放目录
        self._image_dir = Path("data/msg_images")
        try:
            self._image_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # 如果没法创建目录也不要阻塞主流程
            logger.warning("无法创建消息图片缓存目录 data/msg_images")

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
        metadata: dict | None = None,
        immediate: bool | None = False,
    ):
        """
        添加消息到队列

        Args:
            platform: 平台名称
            bot_id: 机器人ID
            session_id: 会话ID
            session_type: 会话类型 (private/group)
            message_content: 消息内容；为了节省内存，对于包含图片的消息应传入一个轻量结构
            metadata: 额外的元数据 (如链接等)
            immediate: 是否立即发送消息
        """
        queue_key = (platform, bot_id, session_id, session_type)

        message = {"content": message_content, "metadata": metadata or {}, "timestamp": time.time()}

        if immediate:
            await self._handle_default(platform, bot_id, session_id, session_type, [message])
            logger.debug(f"立即发送消息到队列: {platform}:{session_id}")
        else:
            dq = self.message_queue[queue_key]
            if len(dq) >= self.per_queue_max_messages:
                try:
                    oldest = dq[0]
                    logger.warning(
                        f"队列 {queue_key} 达到上限 ({self.per_queue_max_messages})，"
                        f"将丢弃最旧消息 时间戳:{oldest.get('timestamp')}")
                    old_meta = oldest.get("metadata", {})
                    if old_meta.get("image_path"):
                        self._cleanup_image_file(old_meta.get("image_path"))
                except Exception:
                    logger.debug("在记录被丢弃的旧消息时出错", exc_info=True)

            self.queue_last_active[queue_key] = time.time()
            self.message_queue[queue_key].append(message)
            logger.debug(
                f"已添加消息到队列: {platform}:{session_id} 当前队列长度: {len(self.message_queue[queue_key])}"
            )

            try:
                current_len = len(self.message_queue[queue_key])
                if 0 < self.immediate_flush_count == current_len:
                    logger.info(f"队列 {queue_key} 达到立即推送阈值({self.immediate_flush_count})，立即触发发送")
                    asyncio.create_task(self._process_selected_queues([queue_key]))  # noqa: RUF006
            except Exception:
                logger.debug("触发立即刷新时出错", exc_info=True)

        await self._record_pushed_killmail(queue_key, (metadata or {}).get("kill_id", 0))

    @classmethod
    async def _record_pushed_killmail(cls, query_key: tuple[str, str, str, str], kill_id: int):
        """
        记录已推送的击杀邮件
        :param query_key:
        :param kill_id:
        """
        try:
            record = KillmailPushRecord(
                bot_id=query_key[1],
                platform=query_key[0],
                session_id=query_key[2],
                session_type=query_key[3],
                killmail_id=int(kill_id),
                time=datetime.now(),
            )
            async with get_session() as session:
                session.add(record)
                await session.flush()
                await session.commit()
            if plugin_config.upload_statistics:
                await upload_statistics.send_km_record(
                    bot_id=query_key[1],
                    platform=query_key[0],
                    session_id=query_key[2],
                    session_type=query_key[3],
                    killmail_id=int(kill_id),
                )
        except Exception as e:
            logger.error(f"记录击杀邮件推送失败: {e}\n{traceback.format_exc()}")

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
                        adjusted_wait_time = min(self.check_interval * (1 + len(messages) / 10), self.max_wait_time)

                        if wait_time >= adjusted_wait_time or wait_time >= self.max_wait_time * 0.8:
                            queues_to_process.append(queue_key)
                            logger.debug(
                                f"队列 {queue_key} 消息数量: {len(messages)}，已等待: {wait_time:.1f}秒, 开始推送"
                            )
                    else:
                        if wait_time >= self.check_interval:
                            queues_to_process.append(queue_key)

                    # 检查是否达到立即刷新的阈值
                    if len(messages) == self.immediate_flush_count:
                        queues_to_process.append(queue_key)

                if queues_to_process:
                    await self._process_selected_queues(queues_to_process)

                await asyncio.sleep(min(10, int(self.check_interval / 2)))

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

            # 从字典中移除队列，用以避免并发处理
            del self.message_queue[queue_key]
            if queue_key in self.queue_last_active:
                del self.queue_last_active[queue_key]

            platform, bot_id, session_id, session_type = queue_key

            try:
                handler = self.platform_handlers.get(platform)
                if handler:
                    await handler(bot_id, session_id, session_type, list(messages))
                else:
                    await self._handle_default(platform, bot_id, session_id, session_type, list(messages))
            except Exception as e:
                logger.error(f"处理队列 {platform}:{session_id} 时出错: {e}")

    def _save_image_to_disk(self, image_bytes: bytes, kill_id: str | int | None = None) -> str | None:
        """将图片 bytes 保存到磁盘，返回路径或 None"""
        try:
            if not image_bytes:
                return None
            ts = int(time.time() * 1000)
            filename = f"km_{kill_id}_{ts}.img" if kill_id is not None else f"img_{ts}.img"
            path = self._image_dir / filename
            with open(path, "wb") as f:
                f.write(image_bytes)
            return str(path)
        except Exception:
            logger.exception("保存图片到磁盘失败")
            return None

    @classmethod
    def _cleanup_image_file(cls, path: str | None):
        """尝试删除临时图片文件"""
        try:
            if not path:
                return
            p = Path(path)
            if p.exists():
                p.unlink()
        except Exception:
            logger.debug("删除临时图片文件失败", exc_info=True)

    @classmethod
    def _build_unimessage_from_message(cls, msg: dict) -> UniMessage:
        """根据消息数据构造 UniMessage（在发送前读取图片文件）"""
        content = msg.get("content")
        # 如果 content 本身已经是 UniMessage，则直接返回
        if isinstance(content, UniMessage):
            return content

        reason = None
        image_path = None
        if isinstance(content, dict):
            reason = content.get("reason")
            image_path = content.get("image_path")

        parts = None
        if reason:
            parts = UniMessage.text(reason)
        else:
            parts = UniMessage.text("")

        if image_path:
            try:
                with open(image_path, "rb") as f:
                    img = f.read()
                parts = parts + UniMessage.image(raw=img)
            except Exception:
                logger.debug(f"读取图片 {image_path} 失败，在发送时跳过图片", exc_info=True)

        return parts

    async def _handle_default(
        self, platform: str, bot_id: str, session_id: str, session_type: str, messages: list[dict]
    ):
        """默认的消息处理方法"""
        if not messages:
            return

        try:
            bot = await get_bot(adapter=platform, bot_id=bot_id)
            target = Target(id=session_id, private=(session_type == 0))

            for msg in messages:
                content_msg = self._build_unimessage_from_message(msg)
                metadata = msg.get("metadata", {})

                send_event = await UniMessage(content_msg).send(bot=bot, target=target)

                if metadata.get("image_path"):
                    self._cleanup_image_file(metadata.get("image_path"))

                if "url" in metadata:
                    await save_msg_cache(send_event, metadata["url"])

        except Exception as e:
            logger.error(f"发送消息到 {platform}:{session_id} 失败: {e}")

    async def _handle_onebot_v11(self, bot_id: str, session_id: str, session_type: str, messages: list[dict]):
        """OneBot V11 平台的特殊处理，支持合并发送"""
        if not messages:
            return

        try:
            bot = await get_bot(adapter="OneBot V11", bot_id=bot_id)
            is_private = session_type == 0
            target = Target(id=session_id, private=is_private)

            if len(messages) > 2:
                merged_nodes = []
                last_url = ""

                max_messages = 80

                if len(messages) > max_messages:
                    logger.warning(f"消息数量({len(messages)})超过限制，将只发送最新的{max_messages}条")
                    messages = messages[-max_messages:]

                for msg in messages:
                    metadata = msg.get("metadata", {})
                    content_msg = self._build_unimessage_from_message(msg)

                    node = CustomNode(
                        uid=bot_id, name="小霸王Bot", content=content_msg + UniMessage.text(metadata.get("url", ""))
                    )
                    merged_nodes.append(node)

                    last_url = metadata.get("url")

                    if metadata.get("image_path"):
                        self._cleanup_image_file(metadata.get("image_path"))

                await save_msg_cache(await UniMessage.reference(*merged_nodes).send(bot=bot, target=target), last_url)

                logger.info(f"已发送合并消息到 {session_id}，共{len(messages)}条")
            else:
                for msg in messages:
                    metadata = msg.get("metadata", {})
                    content_msg = self._build_unimessage_from_message(msg)

                    send_event = await UniMessage(content_msg).send(bot=bot, target=target)

                    # 发送后清理临时图片
                    if metadata.get("image_path"):
                        self._cleanup_image_file(metadata.get("image_path"))

                    if "url" in metadata:
                        await save_msg_cache(send_event, metadata["url"])

        except Exception:
            logger.error(f"发送消息到 OneBot V11:{session_id} 失败: {traceback.format_exc()}")

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
    immediate: bool = False,
):
    """将击杀邮件添加到消息队列"""
    if not pic:
        return

    image_path = message_sender._save_image_to_disk(pic, kill_id=kill_id)

    content = {"reason": reason, "image_path": image_path}
    metadata = {"url": f"https://zkillboard.com/kill/{kill_id}/", "kill_id": kill_id, "image_path": image_path}

    await message_sender.add_message(
        platform=platform,
        bot_id=bot_id,
        session_id=session_id,
        session_type=session_type,
        message_content=content,
        metadata=metadata,
        immediate=immediate,
    )
    if not immediate:
        logger.debug(f"已添加击杀邮件 {kill_id} 到队列")


async def queue_common(
    platform: str,
    bot_id: str,
    session_id: str,
    session_type: str,
    msg: UniMessage,
    metadata: dict | None = None,
    immediate: bool | None = True,
):
    """
    统一消息队列
    :param platform: 平台名称
    :param bot_id: 机器人ID
    :param session_id: 会话ID
    :param session_type: 会话类型 (private/group)
    :param msg: 消息内容
    :param metadata: 额外的元数据 (如链接等)
    :param immediate: 是否立即发送消息
    """
    await message_sender.add_message(
        platform=platform,
        bot_id=bot_id,
        session_id=session_id,
        session_type=session_type,
        message_content=msg,
        metadata=metadata or {},
        immediate=immediate,
    )
