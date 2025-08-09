from typing import Any

from nonebot import logger

from ..utils.common.cache import cache, cache_result
from .base import BaseClient


class ZkillboardApi(BaseClient):
    """
    Zkillboard API
    """

    def __init__(self):
        super().__init__()
        self._base_url: str = "https://zkillboard.com/api"
        self._allowed_types: list[str] = ["character", "corporation", "alliance"]

    @cache_result(expire_time=cache.TIME_DAY, prefix="zkill:get_stats", exclude_args=[0])
    async def get_stats(
        self,
        type_: str,
        id_: str | int,
    ) -> dict[str, Any] | None:
        """
        获取Zkillboard对应类型的统计数据ß
        :param type_: 类型
        :param id_: id
        :return:
        """
        if type_ not in self._allowed_types:
            raise ValueError(f"不支持的类型: {type_}")

        try:
            endpoint = f"/stats/{type_}ID/{id_}/"
            data = await self._get(endpoint)
            return data
        except Exception as e:
            logger.error(f"获取Zkillboard数据失败: {e}")
            return None

    @cache_result(expire_time=cache.TIME_HOUR, prefix="zkill:get_killmail_list", exclude_args=[0])
    async def get_killmail_list(
        self,
        type_: str,
        id_: str | int,
    ) -> dict[str, Any] | None:
        """
        获取击杀列表
        :param type_:
        :param id_:
        :return:
        """
        if type_ not in self._allowed_types:
            raise ValueError(f"不支持的类型: {type_}")

        try:
            endpoint = f"/{type_}ID/{id_}/"
            data = await self._get(endpoint)
            return data
        except Exception as e:
            logger.error(f"获取Zkillboard数据失败: {e}")
            return None


zkb_api = ZkillboardApi()
