import asyncio
import os

from nonebot import get_driver, logger, require

from .command import *  # noqa: F403
from .command.subscription import start_km_listen_, stop_km_listen_
from .config import plugin_config
from .router import *  # noqa: F403
from .utils.common.cache import cache as c
from .utils.common.command_record import HelperExtension
from .utils.common.http_client import close_client
from .utils.common.http_client import init_client as init_client
from .utils.github import updater
from .utils.hook import *  # noqa: F403

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import add_global_extension

driver = get_driver()


TITLE = r"""
 __   ___               ____         __          __
 \ \ / (_)             |  _ \        \ \        / /
  \ V / _  __ _  ___   | |_) | __ _   \ \  /\  / /_ _ _ __   __ _
   > < | |/ _` |/ _ \  |  _ < / _` |   \ \/  \/ / _` | '_ \ / _` |
  / . \| | (_| | (_) | | |_) | (_| |    \  /\  / (_| | | | | (_| |
 /_/ \_\_|\__,_|\___/  |____/ \__,_|     \/  \/ \__,_|_| |_|\__, |
                                                             __/ |
                                                            |___/ """


@driver.on_startup
async def init():
    logger.info(TITLE)

    await c.init()

    if plugin_config.EVE_JANICE_API_KEY == "G9KwKq3465588VPd6747t95Zh94q3W2E":
        logger.opt(colors=True).warning(
            "请向JANICE作者申请专用API KEY，临时API有严重速率限制。访问 https://github.com/E-351/janice"
        )

    if plugin_config.upload_statistics:
        logger.opt(colors=True).info(
            f"上传云端统计已启用 将会上传到 {plugin_config.upload_statistics_url} \n"
            f"如果不想上传请在配置文件中关闭 upload_statistics"
        )

    add_global_extension(HelperExtension())

    await start_km_listen_()

    if not os.getenv("DOCKER", "").lower() == "true":
        await updater.check()


@driver.on_shutdown
async def shutdown():
    await stop_km_listen_()
    await close_client()
    await c.close()
