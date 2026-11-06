from nonebot import logger, on_notice
from nonebot.adapters.onebot.v11 import GroupDecreaseNoticeEvent
from nonebot_plugin_orm import get_session

from ..db.models.event_sub import EVEServerStatusSub
from ..db.models.killmail import (
    KillmailConditionSubscription,
    KillmailHighValueSubscription,
    KillmailSubscription,
)
from ..helper.group_leave import disable_group_subscriptions

# 需要停用的全部订阅模型（均有 bot_id, session_id, session_type, is_enabled 字段）
_SUB_MODELS = [
    KillmailSubscription,
    KillmailHighValueSubscription,
    KillmailConditionSubscription,
    EVEServerStatusSub,
]

try:
    from ...structure_notifications.models import StructureNotificationSub

    _SUB_MODELS.append(StructureNotificationSub)
except ImportError:
    pass

group_leave_handler = on_notice()


@group_leave_handler.handle()
async def _(event: GroupDecreaseNoticeEvent):
    """bot 退群/被踢时，自动停用该群的所有订阅"""
    logger.debug(f"[退群事件|{event.group_id}]{event.user_id} bot相关({event.is_tome()})")
    if not event.is_tome():
        return

    group_id = str(event.group_id)

    logger.info(f"检测到 bot 退群: {group_id}，开始停用该群的所有订阅")

    async with get_session() as session:
        disabled = await disable_group_subscriptions(session, _SUB_MODELS, event.self_id, group_id)
        await session.commit()

    if disabled:
        logger.info(f"群 {group_id} 退群处理完成，共停用 {sum(disabled.values())} 条订阅: {disabled}")
    else:
        logger.debug(f"群 {group_id} 无活跃订阅，无需处理")
