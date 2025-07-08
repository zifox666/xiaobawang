import asyncio
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from nonebot import logger, require
from sqlalchemy import Delete

from ...utils.common.cache import cache
from ...utils.common.http_client import get_client
from ...config import plugin_config

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler


class MarketHandle:
    def __init__(self):
        self.esi_base_url: str = "https://esi.evetech.net/latest/"
        self.client = get_client()

        if plugin_config.EVE_MARKET_API == "esi_cache":
            logger.info("启用定时市场缓存")
            scheduler.add_job(
                self._market_refresh_mission, "cron", minute='*/30', id="market_refresh_mission"
            )

    async def _mult_get(
            self,
            region_id: int = 10000002,
            type_id: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        并发获取多页数据
        :param region_id: 区域ID
        :param type_id: 物品ID
        :return: 市场数据列表
        """
        url = f"{self.esi_base_url}markets/{region_id}/orders/"
        params = {}
        if type_id:
            params["type_id"] = type_id

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()

            total_pages = int(response.headers.get("x-pages", 1))
            logger.debug(f"市场数据共 {total_pages} 页")

            first_page_data = response.json()

            if total_pages == 1:
                return first_page_data

            tasks = []
            for page in range(2, total_pages + 1):
                page_params = params.copy()
                page_params["page"] = page
                tasks.append(self._get_market_page(url, page_params))

            other_pages_data = await asyncio.gather(*tasks, return_exceptions=True)

            all_data = first_page_data
            for page_data in other_pages_data:
                all_data.extend(page_data)

            return all_data

        except Exception as e:
            logger.error(f"获取市场数据失败: {e}\n{traceback.format_exc()}")
            return []

    async def _get_market_page(self, url: str, params: dict) -> List[Dict[str, Any]]:
        """
        获取市场数据的单个页面
        :param url: 请求URL
        :param params: 请求参数
        :return: 页面数据
        """
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            page = params.get("page", "unknown")
            logger.error(f"获取市场数据第 {page} 页失败: {e.__traceback__}")
            return []

    @classmethod
    async def _process_market_data(
            cls,
            orders: List[Dict[str, Any]]
    ) -> Dict[int, Dict[str, Any]]:
        """
        处理市场数据，按type_id分类，找出最高买单和最低卖单

        :param orders: 市场订单列表
        :return: 按type_id分类的市场数据字典
        """
        result: Dict = {}

        for order in orders:
            type_id = order["type_id"]

            if type_id not in result:
                result[type_id] = {
                    "buy_orders": [],
                    "sell_orders": [],
                    "highest_buy": None,
                    "lowest_sell": None,
                    "buy_volume": 0,
                    "sell_volume": 0
                }

            if order["is_buy_order"]:
                result[type_id]["buy_orders"].append(order)
                result[type_id]["buy_volume"] = order["volume_remain"]
            else:
                result[type_id]["sell_orders"].append(order)
                result[type_id]["sell_volume"] = order["volume_remain"]

        for type_id, data in result.items():
            if data["buy_orders"]:
                data["buy_orders"].sort(key=lambda x: x["price"], reverse=True)
                data["highest_buy"] = {
                    "price": data["buy_orders"][0]["price"],
                    "volume_remain": data["buy_orders"][0]["volume_remain"],
                    "buy_volume_remain": data["buy_volume"]
                }

            if data["sell_orders"]:
                data["sell_orders"].sort(key=lambda x: x["price"])
                data["lowest_sell"] = {
                    "price": data["sell_orders"][0]["price"],
                    "volume_remain": data["sell_orders"][0]["volume_remain"],
                    "sell_volume_remain": data["sell_volume"]
                }

            data.pop("buy_orders")
            data.pop("sell_orders")

        return result

    async def _market_refresh_mission(self):
        """定时更新市场数据任务"""
        logger.debug("市场定时缓存任务启动")
        market_data = await self._mult_get()
        processed_data = await self._process_market_data(market_data)

        cache_dict = {
            f"market:10000002:{type_id}": data
            for type_id, data in processed_data.items()
        }

        await cache.mset(cache_dict, 3600)

        # plex特殊星域
        plex_data = await self._mult_get(region_id=19000001, type_id=44992)
        processed_plex_data = await self._process_market_data(plex_data)

        plex_cache_key = "market:19000001:44992"
        await cache.set(plex_cache_key, processed_plex_data.get(44992), 3600)

        logger.info(f"定时缓存任务完成，共缓存 {len(processed_data)} 条市场数据")

    async def get_price(
            self,
            type_ids: list[int | str],
            region_id: int = 10000002,
    ):
        """
        获取市场数据
        :param type_ids: 物品ID组
        :param region_id: 区域ID
        :return: 市场数据字典
        """
        result: Dict = {}
        for type_id in type_ids:
            cache_key = f"market:{region_id}:{type_id}"
            result[type_id] =  await cache.get(cache_key)

            if result[type_id] is None:
                logger.debug(f"缓存未命中 region_id: {region_id} type_id: {type_id}")
                market_data = await self._mult_get(region_id, type_id)
                processed_data = await self._process_market_data(market_data)
                result[type_id] = processed_data.get(type_id)
                await cache.set(cache_key, result[type_id], 3600)

        logger.info(result)
        return result

    async def refresh(self):
        """手动刷新市场数据"""
        await self._market_refresh_mission()

    async def get_history(
            self,
            type_id: int,
            region_id: int = 10000002,
    ) -> Optional[Dict[str, Any]]:
        """
        获取市场历史数据
        :param type_id: 物品ID
        :param region_id: 区域ID
        :return: 处理后的市场历史数据
        """
        cache_key = f"market_history:{region_id}:{type_id}"
        cached_data = await cache.get(cache_key)

        if cached_data is not None:
            return cached_data

        url = f"{self.esi_base_url}markets/{region_id}/history/"
        params = {"type_id": type_id}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            history_data = response.json()

            today = datetime.now().date()
            three_months_ago = (today - timedelta(days=90)).isoformat()

            filtered_data = [item for item in history_data if item["date"] >= three_months_ago]

            result = {
                "type_id": type_id,
                "region_id": region_id,
                "history": filtered_data,
                "total_volume": sum(item["volume"] for item in filtered_data),
                "avg_price": sum(item["average"] * item["volume"] for item in filtered_data) /
                             (sum(item["volume"] for item in filtered_data) if sum(
                                 item["volume"] for item in filtered_data) > 0 else 1),
                "updated_at": datetime.now().isoformat()
            }

            await cache.set(cache_key, result, 24 * 3600)
            return result

        except Exception as e:
            logger.error(f"获取市场历史数据失败 type_id: {type_id}, region_id: {region_id}\n {e.__traceback__}")
            return None


market = MarketHandle()
