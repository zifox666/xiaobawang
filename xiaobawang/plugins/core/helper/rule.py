from nonebot.internal.adapter import Event
from nonebot.permission import SUPERUSER
from nonebot_plugin_uninfo import Uninfo


async def super_admin(event: Event) -> bool:
    user_id = event.get_user_id()
    if user_id == SUPERUSER:
        return True
    if user_id not in SUPERUSER:
        return False
    return True


async def is_admin(event: Event, user_info: Uninfo) -> bool:
    """判断是否是群管理或者机器人管理"""
    try:
        flag = False
        if user_info.member.role.id in ["CHANNEL_ADMINISTRATOR", "ADMINISTRATOR", "OWNER"]:
            flag = True
        if await super_admin(event):
            flag = True
        if user_info.scene.type == 0:
            flag = True
        return flag
    except Exception:
        return False
