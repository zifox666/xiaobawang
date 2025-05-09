import traceback
from typing import Optional, Dict, Any, Literal
from nonebot import logger

from ..base import BaseClient
from ...utils.common.cache import cache_result, cache


ALLOW_CATEGORY = Literal["agents", "corporations", "characters", "alliances", "systems", "constellations", "regions", "stations"]


class ESIClient(BaseClient):
    def __init__(self):
        super().__init__()
        self._base_url = "https://esi.evetech.net/latest"
        self.batch_size = 500

    @cache_result(expire_time=cache.TIME_DAY, prefix="esi:get_universe_id", exclude_args=[0])
    async def get_universe_id(
            self,
            name: str,
            lang: str = "en",
            type_: ALLOW_CATEGORY=None,
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
        endpoint = f"/universe/ids/?language={lang}"
        data = [ name ]
        r = await self._post(endpoint, data)
        print(type_)
        if type_:
            return r.get(type_, [])[0]
        else:
            return r

    @cache_result(expire_time=cache.TIME_DAY, prefix="esi:get_names", exclude_args=[0])
    async def get_names(
        self,
        ids: list[int],
    ) -> Dict[str, Dict[str, str] | int] | None:
        """
        获取名称
        Res:
            ids: ID列表
        Return:
            分类的名称列表
        """
        result = {}
        endpoint = f"/universe/names/?datasource=tranquility"

        if isinstance(ids, int):
            ids = [ids]

        for i in range(0, len(ids), self.batch_size):
            batch_ids = ids[i:i+self.batch_size]
            data = batch_ids
            try:
                r = await self._post(endpoint, data)

                for item in r:
                    category = item["category"]
                    item_id = item["id"]
                    name = item["name"]

                    if category not in result:
                        result[category] = {}

                    result[category][item_id] = name

            except Exception as e:
                logger.error(f"获取名称失败 (批次 {i//self.batch_size + 1}): {e}\n{traceback.format_exc()}")
        if result != {}:
            return result
        else:
            return None

    @cache_result(expire_time=7 * cache.TIME_DAY, prefix="esi_system_", exclude_args=[0])  # 缓存1天
    async def get_system_info(self, system_id: int) -> Dict[str, Any]:
        """
        获取星系、星座和区域信息

        Args:
            system_id: 星系ID

        Returns:
            包含星系信息的字典
        """
        try:
            system_resp = await self._get(f"/universe/systems/{system_id}/")
            constellation_id = system_resp.get("constellation_id")

            const_resp = {}
            if constellation_id:
                const_resp = await self._get(f"/universe/constellations/{constellation_id}/")

            region_resp = {}
            region_id = const_resp.get("region_id")
            if region_id:
                region_resp = await self._get(f"/universe/regions/{region_id}/")

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
            logger.error(f"获取星系信息失败: {e}\n{traceback.format_exc()}")
            return {}

    @cache_result(expire_time=cache.TIME_DAY, exclude_args=[0])
    async def get_moon_info(self, moon_id: int) -> Dict | None:
        """
        获取卫星信息
        :param moon_id: 卫星id
        :return: 卫星信息
        """
        try:
            endpoint = f"/universe/moons/{str(moon_id)}/?datasource=tranquility"
            data = await self._get(endpoint)
            return data
        except Exception as e:
            logger.error(f"获取卫星名称失败: {e}")
            return None

    async def get_trans_name(
            self,
            _id: int,
            type_: str,
            lang: str = "zh",
    ) -> str | None:
        """
        获取翻译名称
        :param _id:
        :param type_:
        :param lang:
        :return:
        """
        try:
            endpoint = f"/universe/{type_}/{_id}/?datasource&language={lang}"
            data = await self._get(endpoint)
            if "name" in data:
                return data["name"]
            else:
                return None
        except Exception as e:
            logger.error(f"获取{type_}名称失败: {e}")
            return None

    async def get_api_status(self) -> Optional[Dict[str, str]]:
        """
        获取ESI API状态
        :return: API状态
        """
        try:
            endpoint = "https://esi.evetech.net/status.json?version=latest"
            r = await self._client.get(url=endpoint)
            r.raise_for_status()
            data = r.json()
            green, yellow, red = 0, 0, 0
            for i in data:
                status = i.get("status")
                if status == "green":
                    green += 1
                elif status == "yellow":
                    yellow += 1
                else:
                    red += 1

            return {
                "green": green,
                "yellow": yellow,
                "red": red,
                "total": len(data),
            }
        except Exception as e:
            logger.error(f"获取API状态失败: {e}")
            return {}

    async def get_server_status(self) -> Optional[Dict[str, str]]:
        """
        获取EVE服务器状态
        :return: 服务器状态
        """
        try:
            endpoint = "/status/?datasource=tranquility"
            return await self._get(endpoint)
        except Exception as e:
            logger.error(f"获取服务器状态失败: {e}")
            return {}


esi_client = ESIClient()
