import httpx

from typing import Optional, Dict, Any
from nonebot import logger

from ..utils.common.http_client import get_client


class BaseClient:
    """
    通用请求框架
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = get_client()
        self._base_url: str = ""

    async def _get(
            self,
            endpoint: str,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict:
        """
        GET
        :param endpoint: 接口地址
        :param params: 请求参数
        :return: 数据
        """
        url = f"{self._base_url}{endpoint}"

        try:
            response = await self._client.get(url, params=params)
            logger.debug(f"[{endpoint}]{response.status_code} {response.url}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"[{endpoint}]{e}\n{response.text}")
            raise e

    async def _post(
            self,
            endpoint: str,
            data: Optional[Dict[str, Any] | list] = None,
    ) -> Dict:
        """
        POST
        :param endpoint: 接口地址
        :param data: 请求参数
        :return: 数据
        """
        url = f"{self._base_url}{endpoint}"
        try:
            response = await self._client.post(url, json=data)
            logger.debug(f"[{endpoint}]{response.status_code} {response.url}\ndata: {data}")
            logger.debug(f"响应内容: {response.json()}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"[{endpoint}]{e}\n{response.text}")
            raise e
