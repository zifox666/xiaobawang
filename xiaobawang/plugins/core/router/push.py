"""Push operations share the existing administrator authentication."""
from fastapi import APIRouter, Depends, HTTPException, Query
from nonebot_plugin_orm import get_session
from pydantic import BaseModel
from sqlalchemy import Text, cast, select

from ..db.models.push import PushAttempt, PushBot, PushDelivery, PushEvent
from ..helper.push.service import push_service
from .admin import require_admin_token

router = APIRouter(dependencies=[Depends(require_admin_token)])


def serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.get("/summary")
async def summary():
    return await push_service.store.summary()


@router.get("/deliveries")
async def deliveries(state: str | None = None, session_id: str | None = None,
                     event_id: str | None = None, limit: int = Query(50, ge=1, le=200),
                     offset: int = Query(0, ge=0)):
    query = select(PushDelivery)
    for name, value in (("state", state), ("session_id", session_id), ("event_id", event_id)):
        if value is not None:
            query = query.where(getattr(PushDelivery, name) == value)
    async with get_session() as session:
        rows = await session.scalars(query.order_by(PushDelivery.created_at.desc()).offset(offset).limit(limit))
        return [serialize(row) for row in rows]


@router.get("/deliveries/{delivery_id}")
async def delivery(delivery_id: str):
    async with get_session() as session:
        row = await session.get(PushDelivery, delivery_id)
        if row is None:
            raise HTTPException(404, "任务不存在")
        attempts = await session.scalars(select(PushAttempt).where(
            cast(PushAttempt.delivery_ids, Text).contains('"' + delivery_id + '"')
        ).order_by(PushAttempt.started_at.desc()).limit(100))
        return {"delivery": serialize(row),
                "attempts": [serialize(a) for a in attempts if delivery_id in a.delivery_ids]}


class Action(BaseModel):
    action: str
    accept_duplicate_risk: bool = False


@router.post("/deliveries/{delivery_id}")
async def delivery_action(delivery_id: str, body: Action):
    async with get_session() as session:
        row = await session.get(PushDelivery, delivery_id)
        if row is not None and row.state == "uncertain" and body.action == "retry" and not body.accept_duplicate_risk:
            raise HTTPException(409, "发送结果不确定；核实后设置 accept_duplicate_risk=true 重试")
    try:
        await push_service.store.action(delivery_id, body.action, body.accept_duplicate_risk)
    except LookupError as error:
        raise HTTPException(404, "任务不存在") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return {"success": True}


@router.get("/events")
async def events(state: str = "dead", limit: int = Query(50, ge=1, le=200)):
    async with get_session() as session:
        rows = await session.scalars(select(PushEvent).where(PushEvent.state == state)
                                     .order_by(PushEvent.created_at.desc()).limit(limit))
        return [serialize(row) for row in rows]


@router.post("/events/{event_id}/retry")
async def retry_event(event_id: str):
    import time

    async with get_session() as session, session.begin():
        row = await session.get(PushEvent, event_id, with_for_update=True)
        if row is None:
            raise HTTPException(404, "事件不存在")
        if row.state not in ("dead", "retry"):
            raise HTTPException(409, "只能重试失败事件")
        row.state, row.attempts, row.available_at = "pending", 0, time.time()
    return {"success": True}


@router.get("/bots")
async def bots():
    async with get_session() as session:
        return [serialize(row) for row in await session.scalars(select(PushBot))]


class BotControl(BaseModel):
    paused: bool


@router.post("/bots/{bot_key}")
async def bot_control(bot_key: str, body: BotControl):
    async with get_session() as session, session.begin():
        row = await session.get(PushBot, bot_key, with_for_update=True)
        if row is None:
            raise HTTPException(404, "机器人不存在")
        row.paused = body.paused
    return {"success": True}
