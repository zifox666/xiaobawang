"""
bot_info 插件

提供机器人介绍、公告、二维码等信息，可注入到图片模板中。
无需 NoneBot 插件依赖，仅作为工具模块供其他插件调用。

对外接口：
    from xiaobawang.plugins.bot_info import get_bot_info_data
"""

from .service import get_bot_info_data

__all__ = ["get_bot_info_data"]
