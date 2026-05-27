"""
建筑通知 FastAPI 路由

登录流程 (Bot 验证码):
  GET  /struct_notify/api/login-code              - 生成页面登录验证码
  GET  /struct_notify/api/login-code/{code}/status - 轮询登录结果

EVE 角色授权 (用于绑定 ESI 令牌):
  POST /struct_notify/api/auth/url               - 获取 EVE OAuth 授权 URL
  GET  /struct_notify/auth/complete              - OAuth 回调

页面:
  GET  /struct_notify/page                       - 管理页

API (需要 session 认证):
  GET  /struct_notify/api/characters             - 已授权角色列表
  POST /struct_notify/api/session/character      - 选择当前会话角色
  GET  /struct_notify/api/categories             - 获取可订阅类别
  GET  /struct_notify/api/subscriptions          - 当前角色的订阅列表
  POST /struct_notify/api/subscriptions          - 创建订阅
  PUT  /struct_notify/api/subscriptions/{id}     - 更新订阅
  DELETE /struct_notify/api/subscriptions/{id}   - 删除订阅
"""

import json
import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from nonebot import logger
from nonebot_plugin_orm import get_session as get_orm_session
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.responses import FileResponse

from ..cache import get_cache
from ..eve_oauth.models import EsiOAuthAuthorization
from ..eve_oauth.service import oauth_service
from .categories import CATEGORY_LABELS, NOTIFICATION_CATEGORIES
from .service import (
    create_subscription,
    delete_subscription,
    get_subscriptions_by_character,
    update_subscription,
)

router = APIRouter()
html_dir = Path(__file__).parent / "src"

cache = get_cache("structure_notifications")

SESSION_PREFIX = "page_session:"
SESSION_EXPIRE = 3600  # 1 小时

LOGIN_STATE_PREFIX = "struct_login_state:"
LOGIN_CODE_EXPIRE = 300  # 5 分钟


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

async def require_login(token: str | None) -> dict:
    """校验 session token，仅要求 bot 验证码登录完成（允许尚未选择角色）"""
    if not token:
        raise HTTPException(status_code=401, detail="未登录，请先完成验证")
    data = await cache.get(f"{SESSION_PREFIX}{token}")
    if not data:
        raise HTTPException(status_code=401, detail="会话已过期，请重新验证")
    return data


async def require_user(token: str | None) -> dict:
    """校验 session token，要求已登录且已选择 EVE 角色"""
    data = await require_login(token)
    if not data.get("character_id"):
        raise HTTPException(status_code=401, detail="请先在网页选择要管理的 EVE 角色")
    return data


# ── 请求模型 ──────────────────────────────────────────────

class UpdateSubRequest(BaseModel):
    categories: list[str] | None = None
    is_enabled: bool | None = None


class CreateSubRequest(BaseModel):
    categories: list[str] = Field(default_factory=lambda: ["structure"])


class SelectCharacterRequest(BaseModel):
    character_id: int


# ── 页面 ──────────────────────────────────────────────────

@router.get("/page")
async def struct_notify_page():
    return FileResponse(html_dir / "index.html", media_type="text/html; charset=utf-8")


# ── 登录验证码 ────────────────────────────────────────────

@router.get("/api/login-code", response_model=APIResponse)
async def get_login_code():
    """生成用于页面登录的 bot 验证码，前端展示后由用户在聊天中发送 /verify <code>"""
    from ..verify_code import generate_verify_code

    code = secrets.token_hex(4)  # 8 字符 hex
    ok = await generate_verify_code(
        code,
        module="structure_notify_login",
        payload={"code": code},
        expire=LOGIN_CODE_EXPIRE,
    )
    if not ok:
        return failure("生成验证码失败")

    await cache.set(f"{LOGIN_STATE_PREFIX}{code}", {"status": "pending"}, expire=LOGIN_CODE_EXPIRE + 30)
    return success({"code": code, "expires_in": LOGIN_CODE_EXPIRE})


@router.get("/api/login-code/{code}/status", response_model=APIResponse)
async def poll_login_code_status(code: str):
    """轮询登录验证码状态。status: pending | done | expired"""
    if len(code) != 8 or not code.isalnum():
        return failure("无效验证码", code=400)

    state = await cache.get(f"{LOGIN_STATE_PREFIX}{code}")
    if not state:
        return success({"status": "expired"})

    if state.get("status") == "done":
        token = state.get("token")
        # 一次性读取，删除 login_state（token 本身仍有效）
        await cache.delete(f"{LOGIN_STATE_PREFIX}{code}")
        return success({"status": "done", "token": token})

    return success({"status": "pending"})


# ── EVE OAuth（用于绑定 ESI 令牌，不再用于页面登录） ──────

@router.post("/api/auth/url", response_model=APIResponse)
async def get_auth_url(request: Request, token: str = Query(None)):
    """生成 EVE OAuth 授权 URL。token 为当前页面 session token，授权完成后自动回跳"""
    # 鉴权要求：至少已完成 bot 验证码登录
    if token:
        await require_login(token)

    base_url = str(request.base_url).rstrip("/")
    redirect_after = f"{base_url}/struct_notify/auth/complete"
    if token:
        redirect_after += f"?page_token={token}"

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
async def auth_complete(
    character_id: int,
    character_name: str = "",
    page_token: str = "",
    error: str = "",
):
    """EVE OAuth 回调。若携带 page_token，则将角色写入该 session 并回跳页面"""
    if error:
        return RedirectResponse(url=f"/struct_notify/page?error={quote(error)}")

    # 如果有 page_token，把角色写进 session，无需新建 session
    if page_token:
        session_data = await cache.get(f"{SESSION_PREFIX}{page_token}")
        if session_data:
            session_data["character_id"] = character_id
            session_data["character_name"] = character_name
            await cache.set(f"{SESSION_PREFIX}{page_token}", session_data, expire=SESSION_EXPIRE)
        return RedirectResponse(url=f"/struct_notify/page?token={page_token}&char_added=1")

    # 兼容：无 page_token 时创建新 session（旧流程兼容，仅含角色信息）
    from uuid import uuid4
    session_token = uuid4().hex
    await cache.set(
        f"{SESSION_PREFIX}{session_token}",
        {"character_id": character_id, "character_name": character_name,
         "session_id": None, "session_type": None, "platform": None,
         "bot_id": None, "qq": None},
        expire=SESSION_EXPIRE,
    )
    return RedirectResponse(url=f"/struct_notify/page?token={session_token}")


# ── API ───────────────────────────────────────────────────

@router.get("/api/auth/me", response_model=APIResponse)
async def get_me(token: str = Query(None)):
    """获取当前会话信息（兼容旧接口）"""
    user = await require_login(token)
    return success(user)


@router.get("/api/characters", response_model=APIResponse)
async def list_characters(token: str = Query(None)):
    """返回所有已通过 EVE OAuth 授权的角色列表"""
    await require_login(token)
    async with get_orm_session() as db:
        result = await db.execute(select(EsiOAuthAuthorization))
        chars = result.scalars().all()
    data = [
        {"character_id": c.character_id, "character_name": c.character_name}
        for c in chars
    ]
    return success(data)


@router.post("/api/session/character", response_model=APIResponse)
async def select_character(req: SelectCharacterRequest, token: str = Query(None)):
    """将选中角色写入当前 session"""
    session_data = await require_login(token)

    # 确认角色已授权 ESI
    async with get_orm_session() as db:
        result = await db.execute(
            select(EsiOAuthAuthorization).where(
                EsiOAuthAuthorization.character_id == req.character_id
            )
        )
        char = result.scalar_one_or_none()

    if char is None:
        return failure("该角色未授权 ESI，请先完成 EVE OAuth 授权", code=404)

    session_data["character_id"] = char.character_id
    session_data["character_name"] = char.character_name
    await cache.set(f"{SESSION_PREFIX}{token}", session_data, expire=SESSION_EXPIRE)

    return success({"character_id": char.character_id, "character_name": char.character_name})


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


@router.post("/api/subscriptions", response_model=APIResponse)
async def create_sub(req: CreateSubRequest, token: str = Query(None)):
    """直接创建订阅（需已登录且已选择角色，使用 session 中的 bot 会话信息）"""
    user = await require_user(token)

    if not user.get("session_id"):
        return failure("当前会话缺少 bot 信息，请重新通过验证码登录", code=400)

    if not req.categories:
        return failure("请至少选择一种通知类别", code=400)

    sub = await create_subscription(
        character_id=user["character_id"],
        character_name=user.get("character_name", str(user["character_id"])),
        platform=user["platform"],
        bot_id=user["bot_id"],
        session_id=user["session_id"],
        session_type=user["session_type"],
        categories=req.categories,
    )
    return success({"id": sub.id})


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
