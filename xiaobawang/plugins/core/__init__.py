from nonebot import get_driver, logger, require

from .command.subscription import _start_km_listen
from .config import plugin_config
from .utils.common.cache import cache as c
from .utils.common.command_record import HelperExtension
from .command import *
from .utils.github import GitHubAutoUpdater
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

    await GitHubAutoUpdater(
        repo_owner="zifox666",
        repo_name="xiaobawang"
    ).check()

    await c.init()

    if plugin_config.EVE_JANICE_API_KEY == "G9KwKq3465588VPd6747t95Zh94q3W2E":
        logger.warning("请向JANICE作者申请专用API KEY，临时API有严重速率限制。访问 https://github.com/E-351/janice")

    add_global_extension(HelperExtension())

    await _start_km_listen()


@driver.on_shutdown
async def shutdown():
    await close_client()

