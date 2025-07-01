from typing import Optional, Dict, Any

from nonebot import require, logger
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_orm import get_session
from sqlalchemy import Sequence, Select
from sqlalchemy.ext.asyncio import AsyncSession
from nonebot_plugin_uninfo import Uninfo

from ..api.esi.universe import esi_client
from ..db.models.event_sub import EVEServerStatusSub
from .message_queue import queue_common

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler


class EVEServerStatus:
    """
    Class to represent the status of an EVE server.
    """

    def __init__(self):
        self.status: Optional[Dict[str, Any]] = None
        self.api_status: Optional[Dict[str, Any]] = None

        self.previous_server_online: Optional[bool] = True

        scheduler.add_job(
            self.check, "cron", second="*/15", id="eve_server_status_check"
        )

    async def check(self):
        """
        Check the server status.
        """
        self.status = await esi_client.get_server_status()
        self.api_status = await esi_client.get_api_status()

        self.status = await esi_client.get_server_status()
        self.api_status = await esi_client.get_api_status()

        current_online = bool(self.status and self.status.get("players", 0) > 0 and self.status.get("vip", False))

        if self.previous_server_online is None:
            self.previous_server_online = current_online
            return

        if current_online != self.previous_server_online:
            await self.notify_status_change()
            self.previous_server_online = current_online

    async def notify_status_change(self):
        """
        推送服务器消息到订阅
        :return:
        """
        async with get_session() as session:
            subs = await self.get_subs(
                session=session,
                is_enabled=True
            )

            if not subs:
                return

            for sub in subs:
                await queue_common(
                    platform=sub.platform,
                    bot_id=sub.bot_id,
                    session_id=sub.session_id,
                    session_type=sub.session_type,
                    msg=UniMessage(str(self))
                )

    @classmethod
    async def add_sub(cls, session: AsyncSession, user_info: Uninfo) -> bool:
        """
        添加服务器状态订阅推送
        :param session:
        :param user_info:
        :return: 添加成功返回True，已存在返回False
        """
        result = await session.execute(
            Select(EVEServerStatusSub).where(
                (EVEServerStatusSub.platform == user_info.adapter) &
                (EVEServerStatusSub.bot_id == user_info.self_id) &
                (EVEServerStatusSub.session_id == user_info.scene.id) &
                (EVEServerStatusSub.session_type == user_info.scene.type)
            )
        )

        existing_sub = result.scalars().first()
        if existing_sub:
            return False

        sub = EVEServerStatusSub(
            platform=user_info.adapter,
            bot_id=user_info.self_id,
            session_id=user_info.scene.id,
            session_type=user_info.scene.type,
            is_enabled=True
        )

        session.add(sub)
        await session.commit()

        return True

    @classmethod
    async def remove_sub(cls, session: AsyncSession, user_info: Uninfo) -> bool:
        """
        禁用服务器状态订阅推送
        :param session:
        :param user_info:
        :return: 禁用成功返回True，订阅不存在返回False
        """
        result = await session.execute(
            Select(EVEServerStatusSub).where(
                (EVEServerStatusSub.platform == user_info.adapter) &
                (EVEServerStatusSub.bot_id == user_info.self_id) &
                (EVEServerStatusSub.session_id == user_info.scene.id) &
                (EVEServerStatusSub.session_type == user_info.scene.type) &
                (EVEServerStatusSub.is_enabled == True)
            )
        )

        existing_sub = result.scalars().first()
        if not existing_sub:
            return False

        existing_sub.is_enabled = False
        await session.commit()

        return True

    @classmethod
    async def get_subs(
            cls,
            session: AsyncSession,
            platform: str = None,
            bot_id: str = None,
            is_enabled: bool = True
    ) -> Sequence[EVEServerStatusSub]:
        """
        获取服务器状态订阅列表，可按条件筛选
        :param session: 数据库会话
        :param platform: 平台名称，None表示不限平台
        :param bot_id: 机器人ID，None表示不限机器人
        :param is_enabled: 是否只返回已启用的订阅
        :return: 订阅列表
        """
        query_conditions = []

        if is_enabled is not None:
            query_conditions.append(EVEServerStatusSub.is_enabled == is_enabled)

        if platform:
            query_conditions.append(EVEServerStatusSub.platform == platform)

        if bot_id:
            query_conditions.append(EVEServerStatusSub.bot_id == bot_id)

        query = Select(EVEServerStatusSub).order_by(EVEServerStatusSub.id)
        if query_conditions:
            for condition in query_conditions:
                query = query.where(condition)

        result = await session.execute(query)

        return result.scalars().all()

    def __str__(self) -> str:
        server_status = self.status
        api_status = self.api_status
        msg = f"""EVE Tranquility Status\n"""
        if server_status.get("players", 0):
            vip = "\nVIP MODE: ON" if server_status.get("vip", False) else ""
            msg += f"""------\nServer Status: ON{vip}\n - Online Players: {server_status['players']}\n - Version: {server_status['server_version']}\n"""
        else:
            msg += f"""------\nServer Status: OFF\n"""
        if api_status:
            msg += f"""------\nAPI Status:\n - 🟢 {api_status['green']} 🟡 {api_status['yellow']} 🔴 {api_status['red']}\n - Total: {api_status['total']}\n"""
        return msg


eve_server_status = EVEServerStatus()
