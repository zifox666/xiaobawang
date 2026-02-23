"""
建筑通知 FastAPI 路由

OAuth 认证流程:
  POST /struct_notify/api/auth/url            - 获取 EVE OAuth 授权 URL
  GET  /struct_notify/auth/callback            - OAuth 回调
  GET  /struct_notify/api/auth/me              - 获取当前认证角色信息

页面:
  GET  /struct_notify/page                     - 管理页

API (需要 session 认证):
  GET  /struct_notify/api/categories           - 获取可订阅类别
  GET  /struct_notify/api/subscriptions        - 当前角色的订阅列表
  PUT  /struct_notify/api/subscriptions/{id}   - 更新订阅
  DELETE /struct_notify/api/subscriptions/{id} - 删除订阅
  POST /struct_notify/api/verify_code          - 生成 verify 验证码
"""

import json
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from nonebot import logger
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

from ..cache import get_cache
from ..eve_oauth.service import oauth_service
from .categories import CATEGORY_LABELS, NOTIFICATION_CATEGORIES
from .service import (
    create_verify_code,
    delete_subscription,
    get_subscriptions_by_character,
    update_subscription,
)

router = APIRouter()
html_dir = Path(__file__).parent / "src"

cache = get_cache("structure_notifications")

SESSION_PREFIX = "page_session:"
SESSION_EXPIRE = 3600  # 1 小时


# ── 响应模型 ──────────────────────────────────────────────

class APIResponse(BaseModel):
    code: int = 200
    data: dict | list | None = None
    msg: str = "ok"


def success(data=None, msg="ok"):
    return APIResponse(code=200, data=data, msg=msg)


def failure(msg: str, code: int = 500):
    return APIResponse(code=code, data=None, msg=msg)


# ── Session 认证 ─────────────────────────────────────────

async def require_user(token: str | None) -> dict:
    """校验 session token, 返回 {character_id, character_name}"""
    if not token:
        raise HTTPException(status_code=401, detail="未认证，请先授权角色")
    data = await cache.get(f"{SESSION_PREFIX}{token}")
    if not data:
        raise HTTPException(status_code=401, detail="会话已过期，请重新授权")
    return data


# ── 请求模型 ──────────────────────────────────────────────

class UpdateSubRequest(BaseModel):
    categories: list[str] | None = None
    is_enabled: bool | None = None


class VerifyCodeRequest(BaseModel):
    categories: list[str] = Field(default_factory=lambda: ["structure"])


# ── 页面 ──────────────────────────────────────────────────

@router.get("/page")
async def struct_notify_page():
    return FileResponse(html_dir / "index.html", media_type="text/html; charset=utf-8")


# ── OAuth 认证 ────────────────────────────────────────────

@router.post("/api/auth/url", response_model=APIResponse)
async def get_auth_url(request: Request):
    """生成 EVE OAuth 授权 URL, 复用已注册的 eve_oauth 回调地址"""
    base_url = str(request.base_url).rstrip("/")
    redirect_after = f"{base_url}/struct_notify/auth/complete"

    try:
        data = await oauth_service.create_authorization_url(
            requested_scopes=["esi-characters.read_notifications.v1"],
            state_payload={"redirect_after": redirect_after},
        )
        return success({"auth_url": data["auth_url"]})
    except Exception as e:
        logger.error(f"创建授权链接失败: {e}")
        return failure(f"创建授权链接失败: {e}", code=500)


@router.get("/auth/complete")
async def auth_complete(character_id: int, character_name: str = ""):
    """从 eve_oauth 页面重定向而来, 携带角色信息, 创建页面 session"""
    try:
        session_token = uuid4().hex
        await cache.set(
            f"{SESSION_PREFIX}{session_token}",
            {"character_id": character_id, "character_name": character_name},
            expire=SESSION_EXPIRE,
        )
        return RedirectResponse(url=f"/struct_notify/page?token={session_token}")
    except Exception as e:
        logger.error(f"创建页面会话失败: {e}")
        from urllib.parse import quote
        return RedirectResponse(url=f"/struct_notify/page?error={quote(str(e))}")



@router.get("/api/auth/me", response_model=APIResponse)
async def get_me(token: str = Query(None)):
    """获取当前认证角色信息"""
    user = await require_user(token)
    return success(user)


# ── API ───────────────────────────────────────────────────

@router.get("/api/categories", response_model=APIResponse)
async def list_categories():
    """返回可订阅的通知类别"""
    cats = [
        {"key": k, "label": CATEGORY_LABELS.get(k, k), "types": v}
        for k, v in NOTIFICATION_CATEGORIES.items()
    ]
    return success(cats)


@router.get("/api/subscriptions", response_model=APIResponse)
async def list_subscriptions(token: str = Query(None)):
    """返回当前角色的所有订阅"""
    user = await require_user(token)
    character_id = user["character_id"]
    subs = await get_subscriptions_by_character(character_id)
    data = []
    for s in subs:
        data.append({
            "id": s.id,
            "character_id": s.character_id,
            "character_name": s.character_name,
            "platform": s.platform,
            "bot_id": s.bot_id,
            "session_id": s.session_id,
            "session_type": s.session_type,
            "categories": json.loads(s.categories) if s.categories else [],
            "is_enabled": s.is_enabled,
            "created_at": s.created_at.isoformat() if s.created_at else "",
            "updated_at": s.updated_at.isoformat() if s.updated_at else "",
        })
    return success(data)


@router.post("/api/verify_code", response_model=APIResponse)
async def generate_verify_code(
    req: VerifyCodeRequest,
    token: str = Query(None),
):
    """生成验证码, 用户在聊天中发送 /verify <code> 绑定会话"""
    user = await require_user(token)
    code = secrets.token_hex(4)  # 8 字符 hex
    ok = await create_verify_code(
        code,
        user["character_id"],
        categories=req.categories,
        character_name=user.get("character_name", ""),
    )
    if not ok:
        return failure("生成验证码失败")
    return success({"code": code, "expire_seconds": 600})


@router.put("/api/subscriptions/{sub_id}", response_model=APIResponse)
async def update_sub(sub_id: int, req: UpdateSubRequest, token: str = Query(None)):
    """更新订阅 (权限校验: 仅允许操作自己角色的订阅)"""
    user = await require_user(token)
    subs = await get_subscriptions_by_character(user["character_id"])
    if not any(s.id == sub_id for s in subs):
        return failure("无权操作该订阅", code=403)

    kwargs = {}
    if req.categories is not None:
        kwargs["categories"] = req.categories
    if req.is_enabled is not None:
        kwargs["is_enabled"] = req.is_enabled

    if not kwargs:
        return failure("无更新内容", code=400)

    sub = await update_subscription(sub_id, **kwargs)
    if sub is None:
        return failure("订阅不存在", code=404)
    return success({"id": sub.id})


@router.delete("/api/subscriptions/{sub_id}", response_model=APIResponse)
async def delete_sub(sub_id: int, token: str = Query(None)):
    """删除订阅 (权限校验: 仅允许操作自己角色的订阅)"""
    user = await require_user(token)
    subs = await get_subscriptions_by_character(user["character_id"])
    if not any(s.id == sub_id for s in subs):
        return failure("无权操作该订阅", code=403)

    ok = await delete_subscription(sub_id)
    if not ok:
        return failure("订阅不存在", code=404)
    return success(msg="已删除")


@router.post("/api/subscriptions/{sub_id}/test", response_model=APIResponse)
async def test_push(sub_id: int, token: str = Query(None)):
    """向指定订阅发送一条测试推送消息"""
    user = await require_user(token)
    subs = await get_subscriptions_by_character(user["character_id"])
    sub = next((s for s in subs if s.id == sub_id), None)
    if sub is None:
        return failure("无权操作该订阅", code=403)

    from nonebot_plugin_alconna import Target, UniMessage

    character_name = sub.character_name or str(sub.character_id)
    message_text = (
        f"🔔 测试推送\n"
        f"角色: {character_name}\n"
        f"会话: {sub.session_id}\n"
        f"类别: {json.loads(sub.categories) if sub.categories else []}\n"
        f"如果你看到这条消息，说明推送通道正常工作！"
    )

    try:
        target = Target(
            id=sub.session_id,
            self_id=sub.bot_id,
            channel=True if sub.session_type.upper() in ("GROUP", "CHANNEL") else False,
            private=sub.session_type.upper() == "PRIVATE",
            platform=sub.platform,
        )
        await UniMessage.text(message_text).send(target=target)
    except Exception as e:
        logger.error(f"测试推送失败: sub_id={sub_id} 错误={e}")
        return failure(f"推送失败: {e}", code=500)

    return success(msg="测试消息已发送")
