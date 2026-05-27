from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """机器人介绍/公告/二维码配置，可在 .env 中设置。"""

    # 是否在击毁邮件图片中显示机器人信息区域
    bot_info_enabled: bool = True

    # 机器人名称，显示在信息区标题
    bot_info_name: str = "小霸王机器人"

    # 一句话介绍/口号
    bot_info_slogan: str = "EVE Online 机器人助手"

    # 添加好友按钮说明文字
    bot_info_add_friend_text: str = "添加机器人好友"

    # 添加好友二维码
    # 支持三种格式：
    #   空字符串 → 不显示
    #   http(s):// 开头的 URL → 直接作为 <img src>
    #   本地文件路径 → 读取后转为 base64 Data URI
    bot_info_add_friend_qr: str = ""

    # 订阅击毁邮件说明文字
    bot_info_subscribe_text: str = "订阅击毁邮件"

    # 订阅击毁邮件二维码（格式同上）
    bot_info_subscribe_qr: str = ""

    # 公告列表，每条为一个字符串
    bot_info_announcements: list[str] = []


plugin_config = get_plugin_config(Config)
