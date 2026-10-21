from typing import Any

import httpx
from nonebot import logger, require
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Uninfo
from sqlalchemy import Select, Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.esi.universe import esi_client
from ..config import plugin_config
from ..db.models.event_sub import EVEServerStatusSub
from ..utils.common.http_client import get_client
from .push.service import push_service

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler


class EVEServerStatus:
    """
    Class to represent the status of an EVE server.
    """

    def __init__(self):
        self.status: dict[str, Any] | None = None
        self.api_status: dict[str, Any] | None = None

        self.previous_server_online: bool | None = None
        self._client: httpx.AsyncClient | None = get_client()

        scheduler.add_job(self.check, "cron", second="*/30", id="eve_server_status_check")

    async def check(self):
        """
        Check the server status.
        """
        self.api_status = await esi_client.get_api_status()
        try:
            if not plugin_config.tq_status_url:
                r = await self._client.get("https://esi.evetech.net/latest/status/?datasource=tranquility")
                if r.status_code == 200:
                    self.status = r.json()
                elif r.status_code // 100 == 5:
                    self.status = {
                        "players": 0,
                        "server_version": "0",
                        "start_time": "2000-01-01T00:00:00Z",
                        "vip": False,
                    }
                else:
                    r.raise_for_status()
            else:
                r = await self._client.get(plugin_config.tq_status_url)
                r.raise_for_status()
                if r.json().get("code") == 200:
                    data = r.json().get("data")
                    self.status = {
                        "players": int(data.get("tqCount", 0) if data.get("tqStatus") == "ONLINE" else 0),
                        "server_version": data.get("server_version", ""),
                        "vip": data.get("vip", False),
                    }
        except Exception as e:
            logger.error(f"获取EVE服务器状态失败: {e!s}")
            raise e

        if self.status:
            players_count = self.status.get("players", 0)
            current_online = players_count > 100

            logger.debug(f"EVE服务器状态: 玩家数={players_count}, 在线={current_online}")
        else:
            current_online = self.previous_server_online

        if current_online is not None:
            await push_service.store.status_change(current_online, {"text": str(self)})
            self.previous_server_online = current_online

    async def notify_status_change(self, event_id: str, status_message: str):
        async with get_session() as session:
            subs = await self.get_subs(session=session, is_enabled=True)
            for sub in subs:
                await push_service.enqueue(
                    event_id=event_id, kind="eve_status", platform=sub.platform, bot_id=sub.bot_id,
                    session_id=sub.session_id, session_type=sub.session_type,
                    text=status_message, priority=10,
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
                (EVEServerStatusSub.platform == user_info.adapter)
                & (EVEServerStatusSub.bot_id == user_info.self_id)
                & (EVEServerStatusSub.session_id == user_info.scene.id)
                & (EVEServerStatusSub.session_type == user_info.scene.type.name)
            )
        )

        existing_sub = result.scalars().first()
        if existing_sub:
            return False

        sub = EVEServerStatusSub(
            platform=user_info.adapter,
            bot_id=user_info.self_id,
            session_id=user_info.scene.id,
            session_type=user_info.scene.type.name,
            is_enabled=True,
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
                (EVEServerStatusSub.platform == user_info.adapter)
                & (EVEServerStatusSub.bot_id == user_info.self_id)
                & (EVEServerStatusSub.session_id == user_info.scene.id)
                & (EVEServerStatusSub.session_type == user_info.scene.type.name)
                & (EVEServerStatusSub.is_enabled.is_(True))
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
        platform: str | None = None,
        bot_id: str | None = None,
        is_enabled: bool | None = True,
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
        msg = """EVE Tranquility Status\n"""
        if server_status.get("players", 0):
            vip = "\nVIP MODE: ON" if server_status.get("vip", False) else ""
            msg += f"""------\nServer Status: ON{vip}\n
             - Online Players: {server_status["players"]}\n
              - Version: {server_status["server_version"]}\n"""
        else:
            msg += """------\nServer Status: OFF\n"""
        if api_status:
            msg += f"""------\nAPI Status:\n
             - 🟢 {api_status["green"]} 🟡 {api_status["yellow"]} 🔴 {api_status["red"]}\n
              - Total: {api_status["total"]}\n"""
        return msg


eve_server_status = EVEServerStatus()
