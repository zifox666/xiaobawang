"""
EVE 建筑通知预警模块

- 通过 ESI 拉取角色建筑通知
- 用户在网页选择角色+通知类别后生成验证码
- 用户在聊天中发送 /verify <code> 绑定会话
- 定时拉取并推送匹配的通知
"""

from nonebot import get_app, logger, require
from nonebot.exception import FinishedException

from .config import plugin_config
from .models import StructureNotificationRecord, StructureNotificationSub
from .router import router

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")

from nonebot_plugin_alconna import Alconna, Args, CommandMeta, UniMessage, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_uninfo import Uninfo

from .tasks import poll_and_push
from .service import consume_verify_code, create_subscription

# ── 确保 ORM 发现模型 ─────────────────────────────────────
_ = StructureNotificationSub
__ = StructureNotificationRecord

# ── 注册 FastAPI 路由 ─────────────────────────────────────
app = get_app()
app.include_router(router, prefix="/struct_notify")


# ── /verify 命令 ──────────────────────────────────────────

verify_cmd = on_alconna(
    Alconna(
        "verify",
        Args["code", str],
        meta=CommandMeta(
            description="验证建筑通知推送绑定",
            usage="/verify <验证码>",
        ),
    ),
    use_cmd_start=True,
    block=True,
    priority=15,
)


@verify_cmd.handle()
async def handle_verify(user_info: Uninfo, code: str):
    """
    用户在聊天发送 /verify abc123
    后端查 cache 是否存在该验证码, 存在则绑定当前会话
    """
    payload = await consume_verify_code(code)
    if payload is None:
        await verify_cmd.finish("验证码无效或已过期，请重新生成")

    character_id = payload.get("character_id")
    if not character_id:
        await verify_cmd.finish("验证码数据异常，请重新生成")

    # 从 Uninfo 获取会话信息
    platform = user_info.adapter
    bot_id = user_info.self_id
    session_id = user_info.scene.id
    session_type = user_info.scene.type.name

    categories = payload.get("categories", ["structure"])
    character_name = payload.get("character_name", str(character_id))

    try:
        sub = await create_subscription(
            character_id=character_id,
            character_name=character_name or str(character_id),
            platform=platform,
            bot_id=bot_id,
            session_id=session_id,
            session_type=session_type,
            categories=categories,
        )
        await verify_cmd.finish(
            f"✅ 建筑通知绑定成功!\n"
            f"角色: {character_name or character_id}\n"
            f"会话: {session_id}\n"
            f"类别: {', '.join(categories)}\n"
            f"订阅 ID: {sub.id}"
        )
    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"创建建筑通知订阅失败: {e}")
        await verify_cmd.finish(f"绑定失败: {e}")


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
