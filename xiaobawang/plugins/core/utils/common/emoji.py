import traceback

from nonebot import logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent as ob11_GroupMessageEvent
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna import message_reaction


async def emoji_action(event: Event, emoji: str = "🔥"):
    """
    发送表情包
    :param event: 事件对象
    :param emoji 除了ob11以外的emoji
    """
    try:
        if isinstance(event, ob11_GroupMessageEvent):
            await message_reaction(event=event, emoji="12893")
        else:
            await message_reaction(event=event, emoji=emoji)
    except Exception:
        logger.error(f"表情包发送失败: {traceback.format_exc()}")
