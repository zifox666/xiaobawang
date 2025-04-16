from typing import Optional, Dict, Any, Literal, get_origin
from nonebot import logger

from ...utils.common.cache import cache_result, cache
from ...utils.common.http_client import get_client


ALLOW_CATEGORY = Literal["agents", "corporations", "characters", "alliances", "systems", "constellations", "regions", "stations"]


class ESIClient:
    def __init__(self):
        self.client = get_client()
        self.base_url = "https://esi.evetech.net/latest/"
        self.batch_size = 300  # ESI API 批量请求的最大限制

    async def _get(
            self,
            endpoint: str,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict:
        """
        GET
        Res:
            endpoint: ESI接口地址
            params: 请求参数
        Return:
            ESI数据
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            logger.debug(f"[{endpoint}]{response.status_code} {response.url}")
            return response.json()
        except Exception as e:
            raise e

    async def _post(
            self,
            endpoint: str,
            data: Optional[Dict[str, Any] | list] = None,
    ) -> Dict:
        """
        POST
        Res:
            endpoint: ESI接口地址
            data: 请求参数
        Return:
            ESI数据
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = await self.client.post(url, json=data)
            response.raise_for_status()
            logger.debug(f"[{endpoint}]{response.status_code} {response.url}")
            return response.json()
        except Exception as e:
            raise e

    @cache_result(expire_time=cache.TIME_DAY, prefix="esi:get_universe_id")
    async def get_universe_id(
            self,
            type_: ALLOW_CATEGORY,
            name: str,
            lang: str = "en",
    ) -> Dict[str, str | int] | Any:
        """
        获取TYPE_ID
        Res:
            type_: 类型
            name: 名称
            lang: 语言 默认 en
        Return:
            ID int
        """
        url = f"{self.base_url}users/universe/ids/?language={lang}"
        data = [ name ]
        r = await self._post(url, data)
        if type_:
            return r.get(type_, [])[0]
        else:
            # 天体特别处理
            for key, item in r.items():
                return item.get("name")

    @cache_result(expire_time=cache.TIME_DAY, prefix="esi:get_names")
    async def get_names(
        self,
        ids: list[int],
    ) -> Dict[str, Dict[str, str] | int]:
        """
        获取名称
        Res:
            ids: ID列表
        Return:
            分类的名称列表
        """
        result = {}
        url = f"{self.base_url}universe/names/"

        for i in range(0, len(ids), self.batch_size):
            batch_ids = ids[i:i+self.batch_size]
            data = batch_ids
            try:
                r = await self._post(url, data)

                for item in r:
                    category = item["category"]
                    item_id = item["id"]
                    name = item["name"]

                    if category not in result:
                        result[category] = {}

                    result[category][item_id] = name

            except Exception as e:
                logger.error(f"获取名称失败 (批次 {i//self.batch_size + 1}): {e}")

        return result

    @cache_result(expire_time=7 * cache.TIME_DAY, prefix="esi_system_")  # 缓存1天
    async def get_system_info(self, system_id: int) -> Dict[str, Any]:
        """
        获取星系、星座和区域信息

        Args:
            system_id: 星系ID

        Returns:
            包含星系信息的字典
        """
        try:
            client = get_client()

            system_resp = await self._get(f"{self.base_url}/systems/{system_id}/")
            constellation_id = system_resp.get("constellation_id")

            const_resp = {}
            if constellation_id:
                const_resp = await client.get(f"{self.base_url}/constellations/{constellation_id}/")

            region_resp = {}
            region_id = const_resp.get("region_id")
            if region_id:
                region_resp = await client.get(f"{self.base_url}/regions/{region_id}/")

            return {
                "system_id": system_id,
                "system_name": system_resp.get("name"),
                "constellation_id": constellation_id,
                "constellation_name": const_resp.get("name"),
                "region_id": region_id,
                "region_name": region_resp.get("name"),
                "security_status": system_resp.get("security_status")
            }

        except Exception as e:
            logger.error(f"获取星系信息失败: {e}")
            return {}

esi_client = ESIClient()