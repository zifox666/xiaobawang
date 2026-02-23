from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from nonebot_plugin_orm import AsyncSession, get_session
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

from .config import plugin_config
from .service import oauth_service, scope_registry

router = APIRouter()
html_dir = Path(__file__).parent / "src"


class APIResponse(BaseModel):
    code: int = 200
    data: dict | list | None = None
    msg: str = "ok"


async def verify_api_key(x_esi_api_key: str = Header(..., alias="X-ESI-API-Key")) -> str:
    """校验内部 API 密钥，保护敏感端点"""
    if x_esi_api_key != plugin_config.esi_oauth_api_key:
        raise HTTPException(status_code=403, detail="API key 无效")
    return x_esi_api_key


class ScopeRequest(BaseModel):
    character_id: int | None = None


class CreateAuthUrlRequest(BaseModel):
    requested_scopes: list[str] = Field(default_factory=list)
    character_id: int | None = None
    state_payload: dict[str, Any] = Field(default_factory=dict)


class ExchangeCodeRequest(BaseModel):
    code: str
    state: str


class CharacterRequest(BaseModel):
    character_id: int


class AccessTokenRequest(BaseModel):
    character_id: int
    required_scopes: list[str] = Field(default_factory=list)


def success(data: dict | list | None = None, msg: str = "ok") -> APIResponse:
    return APIResponse(code=200, data=data, msg=msg)


def failure(msg: str, code: int = 500) -> APIResponse:
    return APIResponse(code=code, data=None, msg=msg)


@router.get("/oauth/page")
async def oauth_page() -> FileResponse:
    return FileResponse(html_dir / "oauth.html", media_type="text/html; charset=utf-8")


@router.post("/oauth/scopes", response_model=APIResponse)
async def oauth_scopes(req: ScopeRequest, session: AsyncSession = Depends(get_session)) -> APIResponse:
    try:
        scopes = oauth_service.list_scopes()
        current_scopes: list[str] = []
        if req.character_id:
            auth = await oauth_service.get_authorization(session, req.character_id)
            if auth:
                current_scopes = auth.scopes.split(" ")
        return success({"scopes": scopes, "current_scopes": current_scopes})
    except Exception as e:
        return failure(f"获取 scopes 失败: {e!s}")


@router.post("/oauth/registered_plugins", response_model=APIResponse)
async def registered_plugins() -> APIResponse:
    """返回所有已注册插件及其所需 scopes，供前端展示覆盖情况"""
    return success(scope_registry.registered_plugins())


@router.post("/oauth/list_authorizations", response_model=APIResponse)
async def list_authorizations(session: AsyncSession = Depends(get_session)) -> APIResponse:
    try:
        rows = await oauth_service.list_authorizations(session)
        return success(
            [
                {
                    "character_id": row.character_id,
                    "character_name": row.character_name,
                    "scopes": row.scopes.split(" "),
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in rows
            ]
        )
    except Exception as e:
        return failure(f"获取授权角色列表失败: {e!s}")


@router.post("/oauth/create_auth_url", response_model=APIResponse)
async def create_auth_url(req: CreateAuthUrlRequest) -> APIResponse:
    try:
        data = await oauth_service.create_authorization_url(
            requested_scopes=req.requested_scopes,
            character_id=req.character_id,
            state_payload=req.state_payload,
        )
        return success(data)
    except ValueError as e:
        return failure(str(e), code=400)
    except Exception as e:
        return failure(f"创建授权链接失败: {e!s}")


@router.post("/oauth/exchange_code", response_model=APIResponse)
async def exchange_code(req: ExchangeCodeRequest, session: AsyncSession = Depends(get_session)) -> APIResponse:
    try:
        state_data = await oauth_service.consume_state(req.state)
        token_data = await oauth_service.exchange_code(req.code)
        verify_data = await oauth_service.verify_token(token_data["access_token"])

        record = await oauth_service.save_authorization(
            session=session,
            token_data=token_data,
            verify_data=verify_data,
            scopes=state_data["scopes"],
        )

        return success(
            {
                "character_id": record.character_id,
                "character_name": record.character_name,
                "scopes": record.scopes.split(" "),
                "expires_on": verify_data.get("ExpiresOn"),
                "ext": state_data.get("ext", {}),
            },
            msg="授权成功",
        )
    except ValueError as e:
        return failure(str(e), code=400)
    except Exception as e:
        return failure(f"授权码交换失败: {e!s}")


@router.post("/oauth/get_authorization", response_model=APIResponse)
async def get_authorization(
    req: CharacterRequest,
    session: AsyncSession = Depends(get_session),
    _key: str = Depends(verify_api_key),
) -> APIResponse:
    try:
        auth = await oauth_service.get_authorization(session, req.character_id)
        if auth is None:
            return failure("未找到该角色授权", code=404)
        return success(
            {
                "character_id": auth.character_id,
                "character_name": auth.character_name,
                "scopes": auth.scopes.split(" "),
                "last_authorized_at": auth.last_authorized_at.isoformat(),
            }
        )
    except Exception as e:
        return failure(f"查询授权信息失败: {e!s}")


@router.post("/oauth/get_access_token", response_model=APIResponse)
async def get_access_token(
    req: AccessTokenRequest,
    session: AsyncSession = Depends(get_session),
    _key: str = Depends(verify_api_key),
) -> APIResponse:
    try:
        token_data = await oauth_service.get_access_token(
            session=session,
            character_id=req.character_id,
            required_scopes=req.required_scopes,
        )
        return success(token_data)
    except ValueError as e:
        return failure(str(e), code=400)
    except Exception as e:
        return failure(f"获取 access_token 失败: {e!s}")


@router.post("/oauth/refresh", response_model=APIResponse)
async def refresh(
    req: CharacterRequest,
    session: AsyncSession = Depends(get_session),
    _key: str = Depends(verify_api_key),
) -> APIResponse:
    try:
        token_data = await oauth_service.get_access_token(session, req.character_id, [])
        return success(token_data, msg="刷新成功")
    except Exception as e:
        return failure(f"刷新失败: {e!s}")



