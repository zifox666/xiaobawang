import asyncio

import httpx
from httpx import AsyncClient
from nonebot import logger

from ...config import HEADERS, plugin_config

# 全局客户端实例
_client: httpx.AsyncClient | None = None
ESI_COMPATIBILITY_HEADER = "X-Compatibility-Date"
ESI_COMPATIBILITY_DATE = "2025-12-16"
ESI_HOST = "esi.evetech.net"


def _inject_esi_compatibility_header(request: httpx.Request) -> None:
    """Automatically attach ESI compatibility date for ESI host requests."""
    if request.url.host == ESI_HOST and ESI_COMPATIBILITY_HEADER not in request.headers:
        request.headers[ESI_COMPATIBILITY_HEADER] = ESI_COMPATIBILITY_DATE


def _build_event_hooks(existing: dict | None = None) -> dict:
    hooks = {} if existing is None else dict(existing)
    request_hooks = list(hooks.get("request", []))
    request_hooks.append(_inject_esi_compatibility_header)
    hooks["request"] = request_hooks
    return hooks


def create_client(**kwargs) -> AsyncClient:
    """Create a configured httpx client with shared request hooks."""
    event_hooks = _build_event_hooks(kwargs.pop("event_hooks", None))
    return httpx.AsyncClient(follow_redirects=True, event_hooks=event_hooks, **kwargs)


async def init_client(
    timeout: float = 30.0, max_connections: int = 1000, max_keepalive_connections: int = 200, **kwargs
) -> AsyncClient:
    """初始化全局httpx异步客户端"""
    global _client

    if _client is not None:
        logger.warning("HTTP客户端已经初始化，将重新初始化")
        await close_client()

    logger.info(
        f"初始化HTTP异步客户端 "
        f"(timeout={timeout}s, max_connections={max_connections}, proxy={plugin_config.proxy}, headers={HEADERS})"
    )
    limits = httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_keepalive_connections)

    _client = create_client(
        timeout=timeout,
        limits=limits,
        proxy=plugin_config.proxy,
        headers=HEADERS,
        **kwargs,
    )

    return _client


def get_client() -> httpx.AsyncClient:
    """获取全局httpx异步客户端实例"""
    if _client is None:
        asyncio.run(init_client())
    return _client


async def close_client() -> None:
    """关闭全局httpx异步客户端"""
    global _client
    if _client is not None:
        logger.info("关闭HTTP异步客户端")
        await _client.aclose()
        _client = None
