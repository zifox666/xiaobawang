import nonebot


nonebot.init()

driver = nonebot.get_driver()

try:
    from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

    driver.register_adapter(ONEBOT_V11Adapter)
except:
    print("onebot 适配器未安装")

try:
    from nonebot.adapters.telegram import Adapter as TELEGRAMAdapter

    driver.register_adapter(TELEGRAMAdapter)
except:
    print("telegram 适配器未安装")


nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()