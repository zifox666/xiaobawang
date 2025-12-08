from nonebot import get_bot
from nonebot.internal.adapter import Event
from nonebot_plugin_uninfo import Uninfo


async def super_admin(event: Event) -> bool:
    user_id = event.get_user_id()
    bot = get_bot()
    return (
        f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}" in bot.config.superusers
        or user_id in bot.config.superusers  # 兼容旧配置
    )


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
