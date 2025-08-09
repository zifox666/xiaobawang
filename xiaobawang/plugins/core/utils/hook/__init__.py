from typing import Any

from nonebot.adapters import Bot
from nonebot.internal.adapter import Event
from nonebot.message import event_preprocessor
from nonebot_plugin_uninfo import Uninfo

from ..common.cache import cache


@Bot.on_calling_api
async def handle_api_call(bot: Bot, api: str, data: dict[str, Any]):
    cache_key = "send_msg"
    if api == "send_msg":
        i = await cache.get(cache_key)
        i = int(i) + 1 if i else 1
        await cache.set(cache_key, str(i), -1)


@event_preprocessor
async def handle_event_preprocessor(event: Event, user_session: Uninfo):
    if event.get_type() == "message":
        session = event.get_session_id()
        user_id = user_session.user.id
        session_info = user_session.scene

        _ = f"event_msg_{session}_{user_id}_{session_info}"
