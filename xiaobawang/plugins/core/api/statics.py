from datetime import datetime
import traceback

from nonebot import logger

from ..config import plugin_config
from .base import BaseClient


class Statics(BaseClient):
    def __init__(self):
        super().__init__()
        self._base_url = plugin_config.upload_statistics_url

    async def send_command_record(
        self,
        bot_id: str,
        platform: str,
        source: str,
        origin: str,
        sender: str,
        event: str,
        session: str,
    ):
        """
        发送命令记录
        :param bot_id: bot id
        :param platform: 平台
        :param source: 来源
        :param origin: 原始数据
        :param sender: 发送者
        :param event: 事件
        :param session: 会话
        :return:
        """
        try:
            _ = await self._post(
                endpoint="/command",
                data={
                    "bot_id": bot_id,
                    "platform": platform,
                    "source": source,
                    "origin": origin,
                    "sender": sender,
                    "event": event,
                    "session": session,
                    "time": datetime.now().isoformat(),
                },
            )
        except Exception:
            logger.error(f"发送命令记录失败: {traceback.format_exc()}")

    async def send_km_record(
        self,
        bot_id: str,
        platform: str,
        session_id: str,
        session_type: str,
        killmail_id: str,
    ):
        """
        发送击杀记录
        :param bot_id: bot id
        :param platform: 平台
        :param session_id: 会话id
        :param session_type: 会话类型
        :param killmail_id: 击杀邮件id
        :return:
        """
        try:
            r = await self._post(
                endpoint="/km",
                data={
                    "bot_id": bot_id,
                    "platform": platform,
                    "session_id": session_id,
                    "session_type": session_type,
                    "killmail_id": killmail_id,
                    "time": datetime.now().isoformat(),
                },
            )
            logger.debug(r)
        except Exception:
            logger.error(f"发送击杀记录失败: {traceback.format_exc()}")


upload_statistics = Statics()
