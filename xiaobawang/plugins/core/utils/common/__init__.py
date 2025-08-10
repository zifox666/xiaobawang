from datetime import datetime
import re

from nonebot.internal.adapter import Bot, Event
from nonebot_plugin_alconna.uniseg import reply_fetch


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


def is_chinese(text: str) -> bool:
    """
    判断字符串是否包含中文字符
    :param text: 输入字符串
    :return: 如果包含中文字符，返回True；否则返回False
    """
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            return True
    return False


def type_word(args: str) -> str:
    """
    整理合同内容
    :param args: 合同内容
    :return: 整理后的合同内容
    """
    args = args.replace("\r", "\n")
    lines = args.split("\n")
    converted_text = ""
    for line in lines:
        fields = line.split("\t")
        converted_text += "\t".join(fields) + "\n"
    return converted_text


def format_value(value: str | float) -> str:
    """
    根据数值大小自动转换为 K、M、B、T 格式

    :param value: 需要格式化的数值
    :return: 格式化后的字符串
    """
    value = float(value)
    if value is None:
        return "0"

    if value >= 1_000_000_000_000:  # 万亿及以上用 T
        return f"{value / 1_000_000_000_000:.2f}T"
    elif value >= 1_000_000_000:  # 十亿及以上用 B
        return f"{value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:  # 百万及以上用 M
        return f"{value / 1_000_000:.2f}M"
    elif value >= 1_000:  # 千及以上用 K
        return f"{value / 1_000:.2f}K"
    else:
        return f"{value:.2f}"


def is_blueprint(item_name: str) -> bool:
    """
    判断物品名称是否为蓝图

    :param item_name: 物品名称

    :return: 如果是蓝图，返回True；否则返回False
    """
    if not item_name:
        return False

    return "蓝图" in item_name or "Blueprint" in item_name


def clean_colored_text(text: str) -> str:
    """
    清除文本中的颜色标签，包括HTML和Unity富文本格式
    :param text: 输入文本
    """
    pattern = r"<color=.*?>|</color>|<c>|</c>"
    text = re.sub(pattern, "", text)

    pattern = r"<[^>]*>"
    text = re.sub(pattern, "", text)

    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip()

    return text
