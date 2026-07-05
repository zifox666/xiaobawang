from nonebot import get_driver, logger
from nonebot.plugin import PluginMetadata

from ..core.helper.message_queue import message_sender
from .cache import cache
from .config import Config as Config
from .config import plugin_config
from .db import close_engine, init_engine
from .oper import sde_search as sde_search
from .utils import text_processor

__plugin_meta__ = PluginMetadata(
    name="EVE SDE 数据库（只读）",
    description="EVE Online 静态数据库查询插件 — 数据由外部服务维护",
    usage="只读查询 EVE SDE 数据库（PostgreSQL）",
)

driver = get_driver()


@driver.on_startup
async def startup():
    """启动时初始化 SDE 数据库连接和缓存"""
    await init_engine()
    await cache.init()
    await message_sender.start()


@driver.on_shutdown
async def shutdown():
    """关闭时清理 SDE 数据库连接和缓存"""
    text_processor.close()
    await close_engine()
    await message_sender.stop()
