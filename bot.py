import nonebot
from nonebot import logger


logger.add(
    "./data/xiaobawang.log",
    level="INFO",
    format=nonebot.log.default_format,
    rotation="100 MB",
    retention="10 days",
    compression="zip",
)

nonebot.init()

driver = nonebot.get_driver()

try:
    from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

    driver.register_adapter(ONEBOT_V11Adapter)
except:
    logger.info("onebot 适配器未安装")

try:
    from nonebot.adapters.telegram import Adapter as TELEGRAMAdapter

    driver.register_adapter(TELEGRAMAdapter)
except:
    logger.info("telegram 适配器未安装")


nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()