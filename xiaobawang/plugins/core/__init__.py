from nonebot import get_driver, logger, require

from .config import plugin_config
from .utils.common.cache import cache
from .utils.common.command_record import HelperExtension
from .command import *
from .utils.hook import *
from .utils.common.http_client import init_client, close_client

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
    await cache.init()

    if plugin_config.EVE_JANICE_API_KEY == "G9KwKq3465588VPd6747t95Zh94q3W2E":
        logger.warning("请向JANICE作者申请专用API KEY，临时API有严重速率限制")

    add_global_extension(HelperExtension())


@driver.on_shutdown
async def shutdown():
    await close_client()

