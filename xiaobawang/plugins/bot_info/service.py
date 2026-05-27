"""
机器人信息服务

将 bot_info 配置转换为可直接注入 Jinja2 模板的字典。
QR 图片支持：
  - 空字符串 → 不渲染
  - http(s):// URL → 用 qrcode 库生成二维码图片，转为 base64 Data URI
  - 本地文件路径 → 读取并转为 base64 Data URI
"""

import base64
import io
from pathlib import Path

from nonebot import logger

from .config import plugin_config


def _url_to_qr_data_uri(url: str) -> str:
    """将任意字符串用 qrcode 生成二维码，返回 PNG base64 Data URI。"""
    try:
        import qrcode  # type: ignore

        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        logger.warning(f"[bot_info] 生成二维码失败: {e}")
        return ""


def _resolve_qr(value: str) -> str:
    """将 QR 配置值解析为可用于 <img src> 的字符串，失败返回空串。"""
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return _url_to_qr_data_uri(value)
    # 本地文件路径
    try:
        path = Path(value)
        if not path.is_file():
            logger.warning(f"[bot_info] QR 文件不存在: {value}")
            return ""
        data = path.read_bytes()
        suffix = path.suffix.lower().lstrip(".")
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(suffix, "image/png")
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception as e:
        logger.warning(f"[bot_info] 读取 QR 文件失败: {e}")
        return ""


def get_bot_info_data() -> dict:
    """
    返回用于注入 Jinja2 模板的 bot_info 字典。

    模板中以 ``{{ bot_info.xxx }}`` 方式访问。
    """
    cfg = plugin_config
    return {
        "enabled": cfg.bot_info_enabled,
        "name": cfg.bot_info_name,
        "slogan": cfg.bot_info_slogan,
        "add_friend_text": cfg.bot_info_add_friend_text,
        "add_friend_qr": _resolve_qr(cfg.bot_info_add_friend_qr),
        "subscribe_text": cfg.bot_info_subscribe_text,
        "subscribe_qr": _resolve_qr(cfg.bot_info_subscribe_qr),
        "announcements": cfg.bot_info_announcements,
    }
