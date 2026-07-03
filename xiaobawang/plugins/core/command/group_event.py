from nonebot import logger, on_notice
from nonebot.adapters.onebot.v11 import GroupDecreaseNoticeEvent
from nonebot_plugin_orm import get_session
from sqlalchemy import update

from ..db.models.event_sub import EVEServerStatusSub
from ..db.models.killmail import (
    KillmailConditionSubscription,
    KillmailHighValueSubscription,
    KillmailSubscription,
)

try:
    from ...structure_notifications.models import StructureNotificationSub

    _STRUCT_SUB_MODEL = StructureNotificationSub
except ImportError:
    _STRUCT_SUB_MODEL = None

# 需要停用的全部订阅模型（均有 platform, bot_id, session_id, is_enabled 字段）
_SUB_MODELS = [
    KillmailSubscription,
    KillmailHighValueSubscription,
    KillmailConditionSubscription,
    EVEServerStatusSub,
]

group_leave_handler = on_notice()


@group_leave_handler.handle()
async def _(event: GroupDecreaseNoticeEvent):
    """bot 退群/被踢时，自动停用该群的所有订阅"""
    if str(event.user_id) != event.self_id:
        return

    bot_id = event.self_id
    group_id = str(event.group_id)
    platform = event.bot.adapter.get_name()

    logger.info(f"检测到 bot 退群: {group_id}，开始停用该群的所有订阅")

    total_disabled = 0

    async with get_session() as session:
        for model in _SUB_MODELS:
            stmt = (
                update(model)
                .where(model.session_id == group_id)
                .where(model.bot_id == bot_id)
                .where(model.is_enabled.is_(True))
                .values(is_enabled=False)
            )
            result = await session.execute(stmt)
            count = result.rowcount
            if count:
                total_disabled += count
                logger.debug(f"已停用 {model.__tablename__} 中 {count} 条订阅")

        # structure_notification_sub（可能不在同一个插件包中）
        if _STRUCT_SUB_MODEL is not None:
            stmt = (
                update(_STRUCT_SUB_MODEL)
                .where(_STRUCT_SUB_MODEL.session_id == group_id)
                .where(_STRUCT_SUB_MODEL.bot_id == bot_id)
                .where(_STRUCT_SUB_MODEL.is_enabled.is_(True))
                .values(is_enabled=False)
            )
            result = await session.execute(stmt)
            count = result.rowcount
            if count:
                total_disabled += count
                logger.debug(f"已停用 structure_notification_sub 中 {count} 条订阅")

        await session.commit()

    if total_disabled:
        logger.info(f"群 {group_id} 退群处理完成，共停用 {total_disabled} 条订阅")
    else:
        logger.debug(f"群 {group_id} 无活跃订阅，无需处理")
