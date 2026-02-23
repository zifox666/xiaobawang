from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    # ESI 代理 (可选, 复用 eve_oauth 的代理)
    structure_notify_proxy: str | None = None
    # 定时拉取间隔 (分钟), ESI 此路由缓存 10 分钟
    structure_notify_interval: int = 10


plugin_config = get_plugin_config(Config)
