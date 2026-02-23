"""
EVE 建筑通知预警模块

- 通过 ESI 拉取角色建筑通知
- 用户在网页选择角色+通知类别后生成验证码
- 用户在聊天中发送 /verify <code> 绑定会话（由 verify_code 插件统一处理）
- 定时拉取并推送匹配的通知
"""

from nonebot import get_app, logger, require

from .config import plugin_config
from .models import StructureNotificationRecord, StructureNotificationSub
from .router import router

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_uninfo")

from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_uninfo import Uninfo

from .service import create_subscription
from .tasks import poll_and_push
from ..verify_code import register_handler

# ── 确保 ORM 发现模型 ─────────────────────────────────────
_ = StructureNotificationSub
__ = StructureNotificationRecord

# ── 注册 FastAPI 路由 ─────────────────────────────────────
app = get_app()
app.include_router(router, prefix="/struct_notify")


# ── 注册验证码绑定回调 ────────────────────────────────────

async def _on_verify(payload: dict, user_info: Uninfo) -> str:
    """
    /verify 命令触发时由 verify_code 插件回调。
    payload 字段由 router.py 生成验证码时写入。
    """
    character_id = payload.get("character_id")
    if not character_id:
        raise ValueError("验证码数据异常，请重新生成")

    platform = user_info.adapter
    bot_id = user_info.self_id
    session_id = user_info.scene.id
    session_type = user_info.scene.type.name

    categories = payload.get("categories", ["structure"])
    character_name = payload.get("character_name") or str(character_id)

    sub = await create_subscription(
        character_id=character_id,
        character_name=character_name,
        platform=platform,
        bot_id=bot_id,
        session_id=session_id,
        session_type=session_type,
        categories=categories,
    )
    return (
        f"✅ 建筑通知绑定成功!\n"
        f"角色: {character_name}\n"
        f"会话: {session_id}\n"
        f"类别: {', '.join(categories)}\n"
        f"订阅 ID: {sub.id}"
    )


register_handler("structure_notifications", _on_verify)


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
