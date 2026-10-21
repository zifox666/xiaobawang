"""
建筑通知订阅聚合端点（挂 /api/subscriptions/structure）

复用 core 认证（get_current_user），按 session_id 隔离。
EVE OAuth 直接从聚合页发起，授权后角色全局可用，本端点查询已授权角色供选择。
"""

import json
from secrets import token_urlsafe
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from nonebot import logger
from nonebot_plugin_orm import AsyncSession, get_session
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...eve_oauth.models import EsiOAuthAuthorization
from ...eve_oauth.service import oauth_service
from ...cache import get_cache
from ..helper.auth import get_current_user
from ..helper.billing import key_from_current_user

# structure_notifications is imported lazily inside the handlers below:
# importing it here creates a circular load (structure_notifications.service
# imports core at module level, which would re-enter this router package).

router = APIRouter()
cache = get_cache("subscription_structure_oauth")

OAUTH_NONCE_PREFIX = "nonce:"
VISIBLE_CHARS_PREFIX = "visible_chars:"
OAUTH_NONCE_EXPIRE = 600
VISIBLE_CHARS_EXPIRE = 86400


class CreateStructSubRequest(BaseModel):
    character_id: int
    character_name: str = ""
    categories: list[str] = Field(default_factory=lambda: ["structure"])


class UpdateStructSubRequest(BaseModel):
    categories: list[str] | None = None
    is_enabled: bool | None = None


def _visible_key(session_key: str) -> str:
    return f"{VISIBLE_CHARS_PREFIX}{session_key}"


async def _get_visible_characters(session_key: str) -> list[dict]:
    chars = await cache.get(_visible_key(session_key), [])
    return chars if isinstance(chars, list) else []


async def _add_visible_character(session_key: str, character_id: int, character_name: str) -> None:
    chars = await _get_visible_characters(session_key)
    rows = [c for c in chars if int(c.get("character_id", 0)) != character_id]
    rows.append({"character_id": character_id, "character_name": character_name})
    await cache.set(_visible_key(session_key), rows, expire=VISIBLE_CHARS_EXPIRE)


async def _ensure_character_visible(session_key: str, character_id: int) -> None:
    chars = await _get_visible_characters(session_key)
    if not any(int(c.get("character_id", 0)) == character_id for c in chars):
        raise HTTPException(status_code=403, detail="该角色未在当前会话完成授权")


@router.get("/categories", summary="建筑通知类别")
async def list_categories() -> dict:
    from ...structure_notifications.categories import CATEGORY_LABELS, NOTIFICATION_CATEGORIES

    cats = [{"key": k, "label": CATEGORY_LABELS.get(k, k)} for k in NOTIFICATION_CATEGORIES]
    return {"success": True, "data": cats}


@router.post("/auth/url", summary="生成建筑通知 EVE OAuth 授权 URL")
async def create_auth_url(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """生成聚合页内使用的 EVE OAuth URL。

    前端以弹窗打开该 URL；OAuth 模块完成 token 交换后会重定向到本 router 的
    /auth/complete，由它通过 postMessage 通知原页面刷新已授权角色。
    """
    session_key = key_from_current_user(current_user)
    nonce = token_urlsafe(24)
    await cache.set(
        f"{OAUTH_NONCE_PREFIX}{nonce}",
        {"session_key": session_key},
        expire=OAUTH_NONCE_EXPIRE,
    )

    base_url = str(request.base_url).rstrip("/")
    redirect_after = (
        f"{base_url}/api/subscriptions/structure/auth/complete?"
        + urlencode({"nonce": nonce})
    )
    try:
        data = await oauth_service.create_authorization_url(
            requested_scopes=["esi-characters.read_notifications.v1"],
            state_payload={
                "redirect_after": redirect_after,
                "source": "subscription_structure",
            },
        )
        return {"success": True, "data": {"auth_url": data["auth_url"]}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"创建建筑通知授权链接失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建授权链接失败: {e}") from e


@router.get("/auth/complete", summary="建筑通知 OAuth 弹窗完成页")
async def auth_complete(
    nonce: str = "",
    character_id: int | None = None,
    character_name: str = "",
    error: str = "",
) -> HTMLResponse:
    session_key = ""
    if not error:
        nonce_data = await cache.get(f"{OAUTH_NONCE_PREFIX}{nonce}") if nonce else None
        if not nonce_data:
            error = "授权会话已过期，请回到订阅页重新发起授权"
        else:
            session_key = nonce_data.get("session_key", "")
            await cache.delete(f"{OAUTH_NONCE_PREFIX}{nonce}")
            if character_id is None:
                error = "授权回调缺少角色信息"
            elif session_key:
                await _add_visible_character(session_key, int(character_id), character_name or str(character_id))

    safe_name = escape(character_name or "")
    safe_error = escape(error or "")
    success = "false" if error else "true"
    message = safe_error or f"{safe_name} 授权完成"
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>EVE OAuth 授权完成</title>
</head>
<body style="background:#0b0e11;color:#eaecef;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
    <div>{message}</div>
    <script>
        const payload = {{
            type: 'structure-oauth-complete',
            success: {success},
            character_id: {character_id or "null"},
            character_name: {json.dumps(character_name or "")},
            error: {json.dumps(error or "")}
        }};
        if (window.opener) {{
            window.opener.postMessage(payload, window.location.origin);
            window.close();
        }} else {{
            window.location.href = '/subscription?tab=structure&oauth=' + (payload.success ? 'success' : 'error');
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(html)


@router.get("/characters", summary="已授权 EVE 角色")
async def list_characters(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """返回当前网页登录会话内完成授权的角色。"""
    session_key = key_from_current_user(current_user)
    visible_chars = await _get_visible_characters(session_key)
    visible_ids = [int(c["character_id"]) for c in visible_chars if c.get("character_id")]
    if not visible_ids:
        return {"success": True, "data": []}

    result = await session.execute(
        select(EsiOAuthAuthorization).where(EsiOAuthAuthorization.character_id.in_(visible_ids))
    )
    chars = result.scalars().all()
    return {
        "success": True,
        "data": [
            {"character_id": c.character_id, "character_name": c.character_name}
            for c in chars
        ],
    }


@router.get("", summary="当前会话的建筑通知订阅")
async def list_subs(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    from ...structure_notifications.models import StructureNotificationSub

    result = await session.execute(
        select(StructureNotificationSub).where(
            StructureNotificationSub.session_id == current_user["session_id"],
            StructureNotificationSub.platform == current_user["platform"],
            StructureNotificationSub.session_type == current_user["session_type"],
            StructureNotificationSub.bot_id == current_user["bot_id"],
        )
    )
    subs = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": s.id,
                "character_id": s.character_id,
                "character_name": s.character_name,
                "categories": json.loads(s.categories) if s.categories else [],
                "is_enabled": s.is_enabled,
                "created_at": s.created_at.isoformat() if s.created_at else "",
            }
            for s in subs
        ],
    }


@router.post("", summary="创建建筑通知订阅")
async def create_sub(
    req: CreateStructSubRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not req.categories:
        raise HTTPException(status_code=400, detail="请至少选择一种类别")
    session_key = key_from_current_user(current_user)
    await _ensure_character_visible(session_key, req.character_id)

    from ...structure_notifications.service import create_subscription

    sub = await create_subscription(
        character_id=req.character_id,
        character_name=req.character_name or str(req.character_id),
        platform=current_user["platform"],
        bot_id=current_user["bot_id"],
        session_id=current_user["session_id"],
        session_type=current_user["session_type"],
        categories=req.categories,
    )
    return {"success": True, "data": {"id": sub.id}}


@router.put("/{sub_id}", summary="更新建筑通知订阅")
async def update_sub(
    sub_id: int,
    req: UpdateStructSubRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    from ...structure_notifications.models import StructureNotificationSub
    from ...structure_notifications.service import update_subscription

    result = await session.execute(
        select(StructureNotificationSub).where(StructureNotificationSub.id == sub_id)
    )
    sub = result.scalar_one_or_none()
    if (
        sub is None
        or sub.session_id != current_user["session_id"]
        or sub.platform != current_user["platform"]
        or sub.session_type != current_user["session_type"]
        or sub.bot_id != current_user["bot_id"]
    ):
        raise HTTPException(status_code=403, detail="无权操作该订阅")

    kwargs = {}
    if req.categories is not None:
        kwargs["categories"] = req.categories
    if req.is_enabled is not None:
        kwargs["is_enabled"] = req.is_enabled
    if not kwargs:
        raise HTTPException(status_code=400, detail="无更新内容")

    updated = await update_subscription(sub_id, **kwargs)
    return {"success": True, "data": {"id": updated.id}}


@router.delete("/{sub_id}", summary="删除建筑通知订阅")
async def delete_sub(
    sub_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    from ...structure_notifications.models import StructureNotificationSub
    from ...structure_notifications.service import delete_subscription

    result = await session.execute(
        select(StructureNotificationSub).where(StructureNotificationSub.id == sub_id)
    )
    sub = result.scalar_one_or_none()
    if (
        sub is None
        or sub.session_id != current_user["session_id"]
        or sub.platform != current_user["platform"]
        or sub.session_type != current_user["session_type"]
        or sub.bot_id != current_user["bot_id"]
    ):
        raise HTTPException(status_code=403, detail="无权操作该订阅")

    await delete_subscription(sub_id)
    return {"success": True, "message": "已删除"}
