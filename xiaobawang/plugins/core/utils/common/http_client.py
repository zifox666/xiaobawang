import asyncio

import httpx
from typing import Optional

from httpx import AsyncClient
from nonebot import logger

from ...config import plugin_config

# 全局客户端实例
_client: Optional[httpx.AsyncClient] = None


async def init_client(
        timeout: float = 30.0,
        max_connections: int = 1000,
        max_keepalive_connections: int = 200,
        **kwargs
) -> AsyncClient:
    """初始化全局httpx异步客户端"""
    global _client

    if _client is not None:
        logger.warning("HTTP客户端已经初始化，将重新初始化")
        await close_client()

    logger.info(f"初始化HTTP异步客户端 (timeout={timeout}s, max_connections={max_connections})， proxy=({plugin_config.proxy})")
    limits = httpx.Limits(
        max_connections=max_connections,
        max_keepalive_connections=max_keepalive_connections
    )

    _client = httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        proxies=plugin_config.proxy,
        follow_redirects=True,
        **kwargs
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
