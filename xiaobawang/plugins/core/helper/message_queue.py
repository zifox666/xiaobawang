"""Compatibility entry points: all proactive messages are durably queued."""
from uuid import uuid4

from nonebot_plugin_alconna import UniMessage

from .push.service import push_service

message_sender = push_service


async def queue_killmail_message(platform, bot_id, session_id, session_type, pic, reason, kill_id, immediate=False):
    if not pic:
        raise ValueError("Killmail rendering returned no image")
    return await push_service.enqueue(
        event_id=f"killmail:{kill_id}", kind="killmail", platform=platform, bot_id=bot_id,
        session_id=session_id, session_type=session_type, text=reason, image=pic,
        priority=10 if immediate else 0,
        metadata={"kill_id": str(kill_id), "url": f"https://zkillboard.com/kill/{kill_id}/"},
    )


async def queue_common(platform, bot_id, session_id, session_type, msg: UniMessage,
                       metadata=None, immediate=True):
    metadata = metadata or {}
    # These callers produce text. Reject unsupported segments rather than silently dropping them.
    if any(segment.type != "text" for segment in msg):
        raise ValueError("queue_common requires text; use push_service.enqueue for images")
    return await push_service.enqueue(
        event_id=metadata.get("event_id", "common:" + uuid4().hex), kind=metadata.get("kind", "common"),
        platform=platform, bot_id=bot_id, session_id=session_id, session_type=session_type,
        text=str(msg), priority=10 if immediate else 0, metadata=metadata,
    )
