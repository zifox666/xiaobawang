from nonebot.internal.adapter import Event
from nonebot.permission import SUPERUSER


async def super_admin(event: Event, *args, **kwargs) -> bool:
    user_id = event.get_user_id()
    if user_id not in SUPERUSER:
        return False
    return True
