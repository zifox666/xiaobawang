from datetime import datetime

from nonebot.internal.adapter import Bot, Event
from nonebot_plugin_alconna.uniseg import reply_fetch


def parse_session_id(session_id: str) -> dict:
    """
    解析会话ID

    :param session_id: 会话ID，格式为 'user_id' 或 'group_{group_id}_{user_id}'
    :return: 包含会话类型和相关ID的字典
    """
    result = {}

    if session_id.startswith("group_"):
        # 群聊消息: group_{group_id}_{user_id}
        parts = session_id.split("_")
        if len(parts) >= 3:
            result["type"] = "group"
            result["group_id"] = parts[1]
            result["user_id"] = parts[2]
    else:
        # 私聊消息: user_id
        result["type"] = "private"
        result["user_id"] = session_id
    return result


async def get_reply_message_id(bot: Bot, event: Event) -> str | None:
    reply = await reply_fetch(event, bot)
    if reply:
        return reply.id
    return None


def convert_time(killmail_time: str) -> str:
    """格式化时间"""
    dt = datetime.strptime(killmail_time, "%Y-%m-%dT%H:%M:%SZ")
    rounded_hour = dt.hour
    rounded_minute = (dt.minute // 10) * 10
    return dt.strftime(f"%Y%m%d{rounded_hour:02d}{rounded_minute:02d}")

