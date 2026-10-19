from typing import Any

import httpx
from nonebot import logger

from ..config import plugin_config
from ..utils.common.http_client import get_client


class BaseClient:
    """
    通用请求框架
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = get_client()
        self._base_url: str = ""
        self.headers: dict[str, str] = {}
        self.headers["user-agent"] = plugin_config.user_agent

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        """
        GET
        :param endpoint: 接口地址
        :param params: 请求参数
        :return: 数据
        """
        url = f"{self._base_url}{endpoint}"

        try:
            request_headers = {**self.headers, **(headers or {})}
            response = await self._client.get(url, params=params, headers=request_headers)
            logger.debug(f"[{endpoint}]{response.status_code} {response.url}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise e

    async def _get_text(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        base_url: str | None = None,
    ) -> str:
        """
        GET 并返回文本响应（用于抓取 HTML 页面）
        :param endpoint: 接口地址
        :param params: 查询参数
        :param headers: 附加请求头
        :param base_url: 覆盖默认 base_url
        :return:
        """
        url = f"{base_url or self._base_url}{endpoint}"

        try:
            request_headers = {**self.headers, **(headers or {})}
            response = await self._client.get(url, params=params, headers=request_headers)
            logger.debug(f"[{endpoint}]{response.status_code} {response.url}")
            response.raise_for_status()
            return response.text
        except Exception as e:
            raise e

    async def _post(
        self,
        endpoint: str,
        data: dict[str, Any] | list | None = None,
    ) -> dict:
        """
        POST
        :param endpoint: 接口地址
        :param data: 请求参数
        :return: 数据
        """
        url = f"{self._base_url}{endpoint}"
        try:
            response = await self._client.post(url, json=data, headers=self.headers)
            logger.debug(f"[{endpoint}]{response.status_code} {response.url}\ndata: {data}")
            logger.debug(f"响应内容: {response.json()}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise e
