"""
其他插件通过此模块获取 ESI OAuth 服务，所有调用均在进程内完成，无需 API key。

使用方式:

    from xiaobawang.plugins.eve_oauth.api import (
        require_scopes,
        get_access_token,
        get_authorized_scopes,
    )

    # 1. 插件启动时声明自己需要的 scopes
    require_scopes("structure_notifications", [
        "esi-universe.read_structures.v1",
        "esi-characters.read_notifications.v1",
    ])

    # 2. 需要调 ESI 时获取 access_token
    token = await get_access_token(character_id=12345)
    # token = {"access_token": "...", "expires_at": 1234567890, "scopes": [...]}

    # 3. 检查某角色已授权的 scopes
    scopes = await get_authorized_scopes(character_id=12345)
"""

from nonebot_plugin_orm import get_session

from .service import oauth_service, scope_registry


def require_scopes(plugin_name: str, scopes: list[str]) -> None:
    """声明本插件需要的 scopes，授权页构造链接时会自动包含"""
    scope_registry.register(plugin_name, scopes)


async def get_access_token(
    character_id: int,
    required_scopes: list[str] | None = None,
) -> dict:
    """
    获取指定角色的有效 access_token。

    - 自动从缓存取，过期自动刷新
    - required_scopes 传空则只要有授权就返回
    - 无授权或权限不足时抛 ValueError
    """
    async with get_session() as session:
        return await oauth_service.get_access_token(
            session, character_id, required_scopes or []
        )


async def get_authorized_scopes(character_id: int) -> list[str]:
    """查询角色当前已授权的 scopes 列表，未授权返回空列表"""
    async with get_session() as session:
        auth = await oauth_service.get_authorization(session, character_id)
        if auth is None:
            return []
        return auth.scopes.split(" ")


async def is_authorized(character_id: int, required_scopes: list[str] | None = None) -> bool:
    """检查角色是否已授权，且覆盖所需 scopes"""
    granted = await get_authorized_scopes(character_id)
    if not granted:
        return False
    if required_scopes:
        return set(required_scopes).issubset(set(granted))
    return True
