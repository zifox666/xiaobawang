from nonebot.adapters import Bot
from ..common.cache import cache


@Bot.on_calling_api
async def handle_api_call(api: str,):
    cache_key = "send_msg"
    if api == "send_msg":
        i = await cache.get(cache_key)
        i = int(i) + 1 if i else 1
        await cache.set(cache_key, str(i), -1)

