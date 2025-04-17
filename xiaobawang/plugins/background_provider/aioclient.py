import asyncio

import httpx
from nonebot import logger
from .config import plugin_config

client: httpx.AsyncClient | None = None


async def create_client():
    global client
    client = httpx.AsyncClient(timeout=plugin_config.req_timeout, proxy=plugin_config.proxy, follow_redirects=True)
    logger.debug("已初始化httpxAsyncClient")


async def close_client():
    global client
    await client.aclose()


def get_client() -> httpx.AsyncClient:
    global client
    if client:
        return client
    else:
        asyncio.run(create_client())
        return client
