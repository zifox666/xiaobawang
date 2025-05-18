from pathlib import Path

from nonebot import get_driver, logger
from nonebot.plugin import PluginMetadata

from .cache import cache
from .config import Config, SDE_DB_PATH, plugin_config
from .upgrade import download_and_extract_sde
from .oper import sde_search
from .db import init_engine, close_engine
from .utils import text_processor
from ..core.helper.message_queue import message_sender

__plugin_meta__ = PluginMetadata(
    name="EVE SDE 数据库",
    description="EVE Online 静态数据库管理插件",
    usage="自动下载和管理EVE SDE数据库",
)

driver = get_driver()


@driver.on_startup
async def startup():
    """检查SDE数据库是否存在，不存在则根据配置下载"""
    db_path = Path(plugin_config.sde_db_path) if plugin_config.sde_db_path else SDE_DB_PATH

    if not db_path.exists():
        logger.info("SDE数据库文件不存在，准备下载...")
        if not plugin_config.sde_auto_download:
            raise FileNotFoundError(f"SDE数据库文件 {db_path} 不存在，且自动下载已禁用。请手动下载数据库或启用自动下载。")

        await download_and_extract_sde(
            download_url=plugin_config.sde_download_url,
            target_path=db_path
        )
    else:
        logger.info(f"SDE数据库文件已存在: {db_path}")

    await init_engine(db_path)
    await cache.init()
    await message_sender.start()


@driver.on_shutdown
async def shutdown():
    """清理SDE数据库连接"""
    await text_processor.close()
    await close_engine()
    await message_sender.stop()


async def update_sde():
    """手动更新SDE数据库"""
    db_path = Path(plugin_config.sde_db_path) if plugin_config.sde_db_path else SDE_DB_PATH

    if not plugin_config.sde_auto_download:
        raise RuntimeError("自动下载已禁用，无法更新SDE数据库")

    logger.info("开始更新SDE数据库...")
    await download_and_extract_sde(
        download_url=plugin_config.sde_download_url,
        target_path=db_path
    )
    logger.info("SDE数据库更新完成")
