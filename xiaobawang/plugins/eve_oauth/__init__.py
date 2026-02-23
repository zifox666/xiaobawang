from nonebot import get_app, logger, require

from .models import EsiOAuthAuthorization
from .service import oauth_service

from .router import router

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

app = get_app()
app.include_router(router, prefix="/esi")

_ = EsiOAuthAuthorization


@scheduler.scheduled_job("interval", minutes=5, id="esi_oauth_refresh_job")
async def refresh_tokens_job():
    try:
        await oauth_service.refresh_expiring_tokens()
    except Exception as e:
        logger.warning(f"ESI OAuth 定时刷新失败: {e!s}")
