"""
EVE 服务器状态订阅端点（挂 /api/subscriptions/eve_status）

复用 core 认证，按 session_id 隔离。一个会话至多一个 eve_status 订阅（开关）。
"""

from fastapi import APIRouter, Depends, HTTPException
from nonebot_plugin_orm import AsyncSession, get_session
from pydantic import BaseModel
from sqlalchemy import select

from ..db.models.event_sub import EVEServerStatusSub
from ..helper.auth import get_current_user

router = APIRouter()


class ToggleRequest(BaseModel):
    is_enabled: bool


async def _get_sub(session: AsyncSession, current_user: dict) -> EVEServerStatusSub | None:
    result = await session.execute(
        select(EVEServerStatusSub).where(
            EVEServerStatusSub.session_id == current_user["session_id"],
            EVEServerStatusSub.platform == current_user["platform"],
        )
    )
    return result.scalar_one_or_none()


@router.get("", summary="当前会话的服务器状态订阅")
async def get_eve_status_sub(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    sub = await _get_sub(session, current_user)
    if sub is None:
        return {"success": True, "data": {"exists": False, "is_enabled": False}}
    return {
        "success": True,
        "data": {"id": sub.id, "exists": True, "is_enabled": sub.is_enabled},
    }


@router.post("", summary="启用服务器状态订阅")
async def enable_eve_status(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    sub = await _get_sub(session, current_user)
    if sub is None:
        sub = EVEServerStatusSub(
            platform=current_user["platform"],
            bot_id=current_user["bot_id"],
            session_id=current_user["session_id"],
            session_type=current_user["session_type"],
            is_enabled=True,
        )
        session.add(sub)
    else:
        sub.is_enabled = True
    await session.commit()
    return {"success": True, "data": {"is_enabled": True}}


@router.put("", summary="切换服务器状态订阅开关")
async def toggle_eve_status(
    req: ToggleRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    sub = await _get_sub(session, current_user)
    if sub is None:
        if not req.is_enabled:
            return {"success": True, "data": {"is_enabled": False}}
        sub = EVEServerStatusSub(
            platform=current_user["platform"],
            bot_id=current_user["bot_id"],
            session_id=current_user["session_id"],
            session_type=current_user["session_type"],
            is_enabled=True,
        )
        session.add(sub)
    else:
        sub.is_enabled = req.is_enabled
    await session.commit()
    return {"success": True, "data": {"is_enabled": req.is_enabled}}


@router.delete("", summary="删除服务器状态订阅")
async def delete_eve_status(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    sub = await _get_sub(session, current_user)
    if sub is None:
        raise HTTPException(status_code=404, detail="订阅不存在")
    await session.delete(sub)
    await session.commit()
    return {"success": True, "message": "已删除"}
