import base64
import json
from urllib.parse import urlencode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import get_cache
from .config import SCOPES_PATH, plugin_config
from .models import EsiOAuthAuthorization

cache = get_cache("esi_oauth")


class _ScopeRegistry:
    """其他插件注册自己所需的 scopes，授权页会自动聚合展示"""

    def __init__(self):
        self._entries: dict[str, list[str]] = {}  # plugin_name -> [scopes]

    def register(self, plugin_name: str, scopes: list[str]) -> None:
        self._entries[plugin_name] = list(scopes)
        logger.debug(f"scope 注册: {plugin_name} -> {scopes}")

    def all_required_scopes(self) -> set[str]:
        result: set[str] = set()
        for scopes in self._entries.values():
            result.update(scopes)
        return result

    def registered_plugins(self) -> dict[str, list[str]]:
        return dict(self._entries)


scope_registry = _ScopeRegistry()


class EsiOAuthService:
    ACCESS_TOKEN_PREFIX = "access_token:"
    AUTH_STATE_PREFIX = "auth_state:"

    def __init__(self):
        self._scopes = self._load_scopes(SCOPES_PATH)

    @staticmethod
    def _load_scopes(path: Path) -> list[dict[str, Any]]:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data

    def list_scopes(self) -> list[dict[str, Any]]:
        return self._scopes

    def _required_scopes(self) -> list[str]:
        return [item["scope"] for item in self._scopes if item.get("required")]

    def _supported_scope_set(self) -> set[str]:
        return {item["scope"] for item in self._scopes}

    @staticmethod
    def _encode_client_auth() -> str:
        if not plugin_config.esi_oauth_client_id or not plugin_config.esi_oauth_client_secret:
            raise RuntimeError("缺少 ESI OAuth 客户端配置: esi_oauth_client_id / esi_oauth_client_secret")
        raw = f"{plugin_config.esi_oauth_client_id}:{plugin_config.esi_oauth_client_secret}".encode()
        return base64.b64encode(raw).decode()

    @staticmethod
    def _to_epoch(expires_on: str) -> int:
        dt = datetime.fromisoformat(expires_on.replace("Z", "+00:00"))
        return int(dt.timestamp())

    @staticmethod
    def _normalize_scopes(scopes: str | list[str]) -> list[str]:
        if isinstance(scopes, str):
            if not scopes.strip():
                return []
            return [item.strip() for item in scopes.split(" ") if item.strip()]
        return [item.strip() for item in scopes if item.strip()]

    @staticmethod
    def _scope_cover(granted: list[str], required: list[str]) -> bool:
        return set(required).issubset(set(granted))

    async def _create_http_client(self) -> httpx.AsyncClient:
        proxies = plugin_config.esi_oauth_proxy
        return httpx.AsyncClient(timeout=20, proxy=proxies)

    async def create_authorization_url(
        self,
        requested_scopes: list[str],
        character_id: int | None = None,
        state_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not plugin_config.esi_oauth_redirect_uri:
            raise RuntimeError("缺少配置: esi_oauth_redirect_uri")
        if not plugin_config.esi_oauth_client_id:
            raise RuntimeError("缺少配置: esi_oauth_client_id")

        supported = self._supported_scope_set()
        invalid_scopes = [scope for scope in requested_scopes if scope not in supported]
        if invalid_scopes:
            raise ValueError(f"存在无效 scopes: {invalid_scopes}")

        scopes = set(self._required_scopes())
        scopes.update(requested_scopes)
        scopes.update(scope_registry.all_required_scopes())

        if character_id is not None:
            async with get_session() as session:
                existing = await self.get_authorization(session, character_id)
                if existing:
                    scopes.update(self._normalize_scopes(existing.scopes))

        state = uuid4().hex
        state_data = {
            "scopes": sorted(scopes),
            "character_id": character_id,
            "ext": state_payload or {},
            "created_at": int(datetime.now(tz=timezone.utc).timestamp()),
        }
        await cache.set(
            f"{self.AUTH_STATE_PREFIX}{state}",
            state_data,
            expire=plugin_config.esi_oauth_state_expire_seconds,
        )

        params = {
            "response_type": "code",
            "redirect_uri": plugin_config.esi_oauth_redirect_uri,
            "client_id": plugin_config.esi_oauth_client_id,
            "scope": " ".join(sorted(scopes)),
            "state": state,
        }

        query = urlencode(params)
        return {
            "auth_url": f"{plugin_config.esi_oauth_authorize_url}?{query}",
            "state": state,
            "scopes": sorted(scopes),
        }

    async def exchange_code(self, code: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Basic {self._encode_client_auth()}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "authorization_code", "code": code}

        async with await self._create_http_client() as client:
            response = await client.post(plugin_config.esi_oauth_token_url, headers=headers, data=data)
            response.raise_for_status()
            return response.json()

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Basic {self._encode_client_auth()}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}

        async with await self._create_http_client() as client:
            response = await client.post(plugin_config.esi_oauth_token_url, headers=headers, data=data)
            response.raise_for_status()
            return response.json()

    async def verify_token(self, access_token: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with await self._create_http_client() as client:
            response = await client.get(plugin_config.esi_oauth_verify_url, headers=headers)
            response.raise_for_status()
            return response.json()

    async def get_authorization(self, session: AsyncSession, character_id: int) -> EsiOAuthAuthorization | None:
        result = await session.execute(
            select(EsiOAuthAuthorization).where(EsiOAuthAuthorization.character_id == character_id)
        )
        return result.scalars().first()

    async def list_authorizations(self, session: AsyncSession) -> list[EsiOAuthAuthorization]:
        result = await session.execute(
            select(EsiOAuthAuthorization).order_by(EsiOAuthAuthorization.updated_at.desc())
        )
        return result.scalars().all()

    async def save_authorization(
        self,
        session: AsyncSession,
        token_data: dict[str, Any],
        verify_data: dict[str, Any],
        scopes: list[str],
    ) -> EsiOAuthAuthorization:
        character_id = int(verify_data["CharacterID"])
        character_name = verify_data.get("CharacterName", "")
        owner_hash = verify_data.get("CharacterOwnerHash", "")

        record = await self.get_authorization(session, character_id)
        if record is None:
            record = EsiOAuthAuthorization(
                character_id=character_id,
                character_name=character_name,
                owner_hash=owner_hash,
                refresh_token=token_data["refresh_token"],
                scopes=" ".join(sorted(set(scopes))),
            )
            session.add(record)
        else:
            merged_scopes = set(self._normalize_scopes(record.scopes))
            merged_scopes.update(scopes)
            record.character_name = character_name
            record.owner_hash = owner_hash
            record.refresh_token = token_data["refresh_token"]
            record.scopes = " ".join(sorted(merged_scopes))
            record.last_authorized_at = datetime.now()

        await session.commit()
        await session.refresh(record)

        expires_at = self._to_epoch(verify_data["ExpiresOn"])
        await cache.set(
            f"{self.ACCESS_TOKEN_PREFIX}{character_id}",
            {
                "access_token": token_data["access_token"],
                "expires_at": expires_at,
                "scopes": self._normalize_scopes(record.scopes),
            },
            expire=max(expires_at - int(datetime.now(tz=timezone.utc).timestamp()), 1),
        )
        return record

    async def get_access_token(self, session: AsyncSession, character_id: int, required_scopes: list[str]) -> dict[str, Any]:
        cached = await cache.get(f"{self.ACCESS_TOKEN_PREFIX}{character_id}")
        now_epoch = int(datetime.now(tz=timezone.utc).timestamp())

        if cached and cached.get("expires_at", 0) > now_epoch + plugin_config.esi_oauth_refresh_before_seconds:
            cached_scopes = self._normalize_scopes(cached.get("scopes", []))
            if self._scope_cover(cached_scopes, required_scopes):
                return cached

        authorization = await self.get_authorization(session, character_id)
        if authorization is None:
            raise ValueError("该角色未授权")

        granted_scopes = self._normalize_scopes(authorization.scopes)
        if not self._scope_cover(granted_scopes, required_scopes):
            raise ValueError("当前授权范围不足，请先进行增量授权")

        token_data = await self.refresh_access_token(authorization.refresh_token)
        verify_data = await self.verify_token(token_data["access_token"])

        authorization.refresh_token = token_data.get("refresh_token", authorization.refresh_token)
        authorization.last_authorized_at = datetime.now()
        await session.commit()

        expires_at = self._to_epoch(verify_data["ExpiresOn"])
        payload = {
            "access_token": token_data["access_token"],
            "expires_at": expires_at,
            "scopes": granted_scopes,
        }
        await cache.set(
            f"{self.ACCESS_TOKEN_PREFIX}{character_id}",
            payload,
            expire=max(expires_at - now_epoch, 1),
        )
        return payload

    async def consume_state(self, state: str) -> dict[str, Any]:
        key = f"{self.AUTH_STATE_PREFIX}{state}"
        data = await cache.get(key)
        if not data:
            raise ValueError("state 不存在或已过期")
        await cache.delete(key)
        return data

    async def refresh_expiring_tokens(self):
        async with get_session() as session:
            result = await session.execute(select(EsiOAuthAuthorization))
            rows = result.scalars().all()

            for row in rows:
                try:
                    await self.get_access_token(session, row.character_id, [])
                except Exception as e:
                    logger.warning(f"刷新角色 {row.character_id} token 失败: {e!s}")


oauth_service = EsiOAuthService()
