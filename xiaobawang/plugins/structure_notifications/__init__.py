"""
EVE 建筑通知预警模块

- 通过 ESI 拉取角色建筑通知
- 用户在网页通过 /verify 验证码登录（由 verify_code 插件统一处理）
- 登录后在网页选择角色和通知类别，直接创建订阅
- 定时拉取并推送匹配的通知
"""

from uuid import uuid4

from nonebot import get_app, logger, require

from .config import plugin_config
from .models import StructureNotificationRecord, StructureNotificationSub
from .router import router, LOGIN_STATE_PREFIX, SESSION_PREFIX, SESSION_EXPIRE

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_uninfo")

from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_uninfo import Uninfo

from .tasks import poll_and_push
from ..verify_code import register_handler
from ..cache import get_cache

# ── 确保 ORM 发现模型 ─────────────────────────────────────
_ = StructureNotificationSub
__ = StructureNotificationRecord

# ── 注册 FastAPI 路由 ─────────────────────────────────────
app = get_app()
app.include_router(router, prefix="/struct_notify")


# ── 注册页面登录验证码回调 ────────────────────────────────

_login_cache = get_cache("structure_notifications")


async def _on_page_login(payload: dict, user_info: Uninfo) -> str:
    """
    /verify 命令触发时由 verify_code 插件回调。
    创建页面会话（仅含 bot 信息），供前端轮询后获取 session token。
    """
    code = payload.get("code")
    if not code:
        raise ValueError("验证码数据异常，请重新生成")

    session_token = uuid4().hex
    bot_session = {
        "session_id": user_info.scene.id,
        "session_type": user_info.scene.type.name,
        # platform 存适配器名（如 "OneBot V11"），与推送链路 get_bot(adapter=...) 对齐
        "platform": user_info.adapter,
        "bot_id": user_info.self_id,
        "qq": user_info.user.id,
        "character_id": None,
        "character_name": None,
    }

    await _login_cache.set(f"{SESSION_PREFIX}{session_token}", bot_session, expire=SESSION_EXPIRE)
    await _login_cache.set(
        f"{LOGIN_STATE_PREFIX}{code}",
        {"status": "done", "token": session_token},
        expire=120,
    )

    return "✅ 建筑通知页面登录成功，请返回网页选择角色"


register_handler("structure_notify_login", _on_page_login)


async def _on_bind_session(payload: dict, user_info: Uninfo) -> str:
    """
    /verify 命令触发时由 verify_code 插件回调。
    将 bot 会话信息与已授权角色创建订阅。
    """
    character_id = payload.get("character_id")
    character_name = payload.get("character_name", "")
    categories = payload.get("categories") or ["structure"]

    if not character_id:
        raise ValueError("验证码数据异常，请重新生成")

    from .service import create_subscription

    await create_subscription(
        character_id=character_id,
        character_name=character_name,
        platform=user_info.adapter,
        bot_id=user_info.self_id,
        session_id=user_info.scene.id,
        session_type=user_info.scene.type.name,
        categories=categories,
    )

    cats_str = "、".join(categories)
    return f"✅ 建筑通知绑定成功！\n角色: {character_name}\n类别: {cats_str}"


register_handler("structure_notify_bind", _on_bind_session)


# ── 定时任务: 拉取并推送建筑通知 ──────────────────────────

@scheduler.scheduled_job(
    "interval",
    minutes=plugin_config.structure_notify_interval,
    id="structure_notification_poll",
)
async def _poll_job():
    try:
        await poll_and_push()
    except Exception as e:
        logger.error(f"建筑通知定时任务异常: {e}")
