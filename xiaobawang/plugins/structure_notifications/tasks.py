"""Persist source events before formatting or delivery."""
from datetime import datetime, timedelta, timezone
import json

from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..core.helper.push.service import push_service
from .categories import TYPE_TO_CATEGORY
from .models import StructureNotificationRecord
from .service import fetch_notifications, format_notification, get_all_enabled_subscriptions, save_notifications


async def poll_and_push():
    subs = await get_all_enabled_subscriptions()
    for character_id in {sub.character_id for sub in subs}:
        try:
            notifications = await fetch_notifications(character_id)
            # Ingest ALL returned notifications, including previously saved records.
            # Delivery IDs deduplicate per target; failed work remains independently retryable.
            for notification in notifications:
                await push_service.store.ingest(
                    f"structure:{character_id}:{notification['notification_id']}", "structure",
                    {"character_id": character_id, "notification": notification},
                )
            # Recover pre-upgrade records that never reached a target.
            async with get_session() as session:
                records = await session.scalars(select(StructureNotificationRecord).where(
                    StructureNotificationRecord.character_id == character_id,
                    StructureNotificationRecord.pushed.is_(False),
                    StructureNotificationRecord.timestamp >= datetime.now(timezone.utc) - timedelta(days=2),
                ))
                for record in records:
                    await push_service.store.ingest(
                        f"structure:{character_id}:{record.notification_id}", "structure",
                        {"character_id": character_id, "notification": {
                            "notification_id": record.notification_id, "type": record.notification_type,
                            "text": record.text, "timestamp": record.timestamp.isoformat(),
                            "sender_id": record.sender_id, "sender_type": record.sender_type,
                        }},
                    )
        except Exception:
            logger.exception(f"建筑通知采集失败 character={character_id}")


async def dispatch_event(event):
    character_id = event.payload["character_id"]
    notification = event.payload["notification"]
    timestamp = datetime.fromisoformat(notification["timestamp"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if timestamp < datetime.now(timezone.utc) - timedelta(days=2):
        return
    await save_notifications(character_id, [notification])
    async with get_session() as session:
        record = await session.scalar(select(StructureNotificationRecord).where(
            StructureNotificationRecord.character_id == character_id,
            StructureNotificationRecord.notification_id == notification["notification_id"],
        ))
        subs = await get_all_enabled_subscriptions()
        for sub in subs:
            if sub.character_id != character_id:
                continue
            if TYPE_TO_CATEGORY.get(record.notification_type) not in json.loads(sub.categories or "[]"):
                continue
            text = f"📢 建筑通知 ({sub.character_name or character_id})\n"
            text += await format_notification(record, sub.character_name)
            await push_service.enqueue(
                event_id=event.id, kind="structure", platform=sub.platform, bot_id=sub.bot_id,
                session_id=sub.session_id, session_type=sub.session_type, text=text, priority=20,
                metadata={"record_id": record.id},
            )
