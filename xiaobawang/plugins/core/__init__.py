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
require("nonebot_plugin_uninfo")

from nonebot_plugin_alconna import add_global_extension
from nonebot_plugin_uninfo import Uninfo

from ..verify_code import register_handler

driver = get_driver()


# ── 订阅网页登录 verify_code handler ────────────────────────────

async def _subscription_auth_handler(payload: dict, user_info: Uninfo) -> str:
    """
    用户执行 /verify <code> 后被调用。
    从 Uninfo 提取会话信息，生成访问 token，并将结果写入等待队列供前端轮询获取。
    """
    from .helper.token_manager import TokenManager
    from .router.auth import AUTH_STATE_PREFIX, AUTH_CODE_EXPIRE

    code = payload.get("code")

    user_dict = {
        "platform": user_info.scope,
        "bot_id": user_info.self_id,
        "session_id": user_info.scene.id,
        "session_type": user_info.scene.type.name,
        "qq": user_info.user.id,
    }

    token = await TokenManager().generate_token(user_dict, expire=c.TIME_DAY)

    if code:
        await c.set(
            f"{AUTH_STATE_PREFIX}{code}",
            {"status": "done", "token": token, "user": user_dict},
            expire=120,  # 前端有 2 分钟时间读取结果
        )
        logger.info(f"[auth] 验证码 {code} 已由 {user_info.scope}/{user_info.scene.id} 完成验证")

    return "✅ 网页登录验证成功，请返回订阅管理页面"


register_handler("subscription_auth", _subscription_auth_handler)


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
