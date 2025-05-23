import asyncio

from nonebot import get_driver, logger, require

from .command.subscription import start_km_listen_, stop_km_listen_
from .config import plugin_config
from .utils.common.cache import cache as c
from .utils.common.command_record import HelperExtension
from .command import *
from .utils.github import updater
from .utils.hook import *
from .utils.common.http_client import init_client, close_client
from .router import *

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import add_global_extension

driver = get_driver()


TITLE = """
 __   ___               ____         __          __               
 \ \ / (_)             |  _ \        \ \        / /               
  \ V / _  __ _  ___   | |_) | __ _   \ \  /\  / /_ _ _ __   __ _ 
   > < | |/ _` |/ _ \  |  _ < / _` |   \ \/  \/ / _` | '_ \ / _` |
  / . \| | (_| | (_) | | |_) | (_| |    \  /\  / (_| | | | | (_| |
 /_/ \_\_|\__,_|\___/  |____/ \__,_|     \/  \/ \__,_|_| |_|\__, |
                                                             __/ |
                                                            |___/                                                                                                                                
"""



@driver.on_startup
async def init():
    print(TITLE)

    await c.init()

    if plugin_config.EVE_JANICE_API_KEY == "G9KwKq3465588VPd6747t95Zh94q3W2E":
        logger.opt(colors=True).warning("请向JANICE作者申请专用API KEY，临时API有严重速率限制。访问 https://github.com/E-351/janice")

    add_global_extension(HelperExtension())

    await start_km_listen_()

    await updater.check()


@driver.on_shutdown
async def shutdown():
    await stop_km_listen_()
    await asyncio.sleep(6)
    await close_client()
    await c.close()
