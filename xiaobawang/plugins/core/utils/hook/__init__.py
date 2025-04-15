from typing import Dict, Any
from nonebot.adapters import Bot, Event
from nonebot.message import event_preprocessor

from ..common import parse_session_id
from ..common.cache import cache


@Bot.on_calling_api
async def handle_api_call(bot: Bot, api: str, data: Dict[str, Any]):
    cache_key = "send_msg"
    if api == "send_msg":
        i = await cache.get(cache_key)
        i = int(i) + 1 if i else 1
        await cache.set(cache_key, str(i), -1)


@event_preprocessor
async def handle_event_preprocessor(event: Event):
    if event.get_type() == "message":
        session = event.get_session_id()
        user_id = int(event.get_user_id())
        session_info = parse_session_id(session)
