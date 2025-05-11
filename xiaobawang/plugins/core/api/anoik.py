from .base import BaseClient
from ..utils.common.cache import cache_result, cache


class AnoikApi(BaseClient):
    def __init__(self):
        super().__init__()
        self._base_url = "https://anoik.is/static"

    @cache_result(expire_time=cache.TIME_DAY * 30, prefix="anoik:get_static", exclude_args=[0])
    async def get_static(self):
        """
        获取虫洞静态数据
        :return:
        """
        endpoint = "/static.json"
        data = await self._get(endpoint)
        return data


anoik_api = AnoikApi()
