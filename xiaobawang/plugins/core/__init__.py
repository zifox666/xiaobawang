from nonebot import get_driver, logger, require

from .config import plugin_config
from .utils.common.cache import cache
from .utils.common.command_record import HelperExtension
from .command import *
from .utils.hook import *
from .utils.common.http_client import init_client

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import add_global_extension

driver = get_driver()


@driver.on_startup
async def init():
    await cache.init()

    if plugin_config.EVE_JANICE_API_KEY == "G9KwKq3465588VPd6747t95Zh94q3W2E":
        logger.warning("请向JANICE作者申请专用API KEY，临时API有严重速率限制")

    add_global_extension(HelperExtension())
