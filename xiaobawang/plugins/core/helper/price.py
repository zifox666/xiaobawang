from typing import Dict, List, Any, Optional
from nonebot import require, logger
from sqlalchemy import select

from .alias import AliasHelper
from ..api.esi.market import market
from ..db.models.alias import TypeAlias
from ..utils.common.cache import cache
from ..utils.common.line import generate_minimal_chart

require("xiaobawang.plugins.sde")

from xiaobawang.plugins.sde import sde_search


class PriceHelper:
    def __init__(self):
        self.LIMIT_SIZE: int = 6  # 单页显示长度
        self.CUT_SIZE: int = 3  # 超出数量显示长度
        self.SKIN_GROUP_ID: int = 1950
        self.GRADE_GROUP_ID: int = 300
        self.cache_key_prefix: str = "price_"
        self.alias_cache_key_prefix: str = "alias_"
        self.low_priority_keywords = [
            "蓝图", "blueprint", "SKIN", "皮肤", "涂装",
        ]
        self.alias_helper = AliasHelper()
        self.alias_plex = {
            "月卡": 500,
            "季卡": 1200,
            "半年卡": 2100,
            "年卡": 3600,
            "两年卡": 6600,
            "plex": 500,
            "PLEX": 500,
            "伊甸币": 500
        }

    async def get(self, session, word: str, num: int = 1, current_page: int = 1) -> Dict[str, Any]:
        """
        获取物品价格，支持分页

        Args:
            session: 数据库会话
            word: 查询关键字
            num: 物品数量
            current_page: 当前页码

        Returns:
            查询结果字典
        """
        # 处理 PLEX 特殊情况
        if word in self.alias_plex and num == 1:
            num = self.alias_plex[word]
            word = "伊甸币"
            logger.info(f"查询价格:{word}*{num}")

        # 查询别名
        alias_results = await self.alias_helper.check(session, word)
        all_items = []

        if alias_results:
            logger.debug(f"找到别名: {word} -> {alias_results}")

            for alias_name in alias_results:
                cache_key = f"{self.cache_key_prefix}{alias_name}"
                cached_data = await cache.get(cache_key)

                if not cached_data:
                    search_result = await sde_search.search_item_by_name(alias_name, market=True)
                    if search_result["total"] > 0:
                        prioritized_items = await self._prioritize_items(alias_name, search_result["items"])
                        cache_data = {
                            "total": search_result["total"],
                            "items": prioritized_items,
                            "word": alias_name
                        }
                        await cache.set(cache_key, cache_data, 7 * 24 * 3600)
                        all_items.extend(prioritized_items)
                else:
                    all_items.extend(cached_data["items"])

        if not alias_results or not all_items:
            cache_key = f"{self.cache_key_prefix}{word}"
            cached_data = await cache.get(cache_key)

            if not cached_data:
                search_result = await sde_search.search_item_by_name(word, market=True)
                if search_result["total"] == 0:
                    return {"success": False, "message": f"未找到物品：{word}"}

                prioritized_items = await self._prioritize_items(word, search_result["items"])
                cache_data = {
                    "total": search_result["total"],
                    "items": prioritized_items,
                    "word": word
                }
                await cache.set(cache_key, cache_data, 7 * 24 * 3600)
                all_items = prioritized_items
            else:
                all_items = cached_data["items"]

        combined_data = {
            "total": len(all_items),
            "items": all_items,
            "word": word
        }

        page_data = await self._get_page_data(combined_data, current_page)
        result = await self._query_and_format_prices(page_data, word, num, current_page, len(all_items))

        return result


    async def _prioritize_items(self, word: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        调整物品优先级，将蓝图、皮肤等物品调低优先级

        Args:
            word: 查询关键字
            items: 物品列表

        Returns:
            调整优先级后的物品列表
        """
        contains_low_priority = any(kw in word.lower() for kw in self.low_priority_keywords)

        if not contains_low_priority:
            normal_items = []
            low_priority_items = []

            for item in items:
                is_low_priority = (
                        item.get("marketGroupID") == self.SKIN_GROUP_ID or
                        item.get("groupID") == self.GRADE_GROUP_ID or
                        any(kw in item.get("typeName", "").lower() for kw in self.low_priority_keywords) or
                        any(kw in item.get("transName", "").lower() for kw in self.low_priority_keywords)
                )

                if is_low_priority:
                    low_priority_items.append(item)
                else:
                    normal_items.append(item)

            return normal_items + low_priority_items

        return items

    async def _get_page_data(self, cached_data: Dict[str, Any], current_page: int) -> Dict[str, Any]:
        """
        获取指定页面的数据

        Args:
            cached_data: 缓存的数据
            current_page: 当前页码

        Returns:
            当前页的数据
        """
        total_items = cached_data["items"]
        total_count = len(total_items)

        page_size = self.LIMIT_SIZE if total_count <= self.LIMIT_SIZE else self.CUT_SIZE

        total_pages = (total_count + page_size - 1) // page_size

        current_page = max(1, min(current_page, total_pages))

        start_index = (current_page - 1) * page_size
        end_index = min(start_index + page_size, total_count)

        current_items = total_items[start_index:end_index]

        return {
            "items": current_items,
            "current_page": current_page,
            "total_pages": total_pages,
            "total_count": total_count,
            "word": cached_data["word"]
        }

    async def _query_and_format_prices(
            self,
            page_data: Dict[str, Any],
            word: str,
            num: int,
            current_page: int,
            total_count: int
    ) -> Dict[str, Any]:
        """
        查询价格并格式化结果

        Args:
            page_data: 当前页的数据
            word: 查询关键字
            num: 物品数量
            current_page: 当前页码
            total_count: 总物品数

        Returns:
            市场价格
        """
        items = page_data["items"]
        type_ids = [item["typeID"] for item in items]

        prices = await market.get_price(type_ids=type_ids)

        histories_line = {}
        for type_id in type_ids:
            history_data = await market.get_history(type_id)
            histories_line[type_id] = generate_minimal_chart(history_data["history"]) if history_data else None

        formatted_items = []
        total_sell = 0
        total_buy = 0
        total_mid = 0
        is_all_grade = all(item.get("groupID") == self.GRADE_GROUP_ID for item in items)

        for item in items:
            type_id = item["typeID"]
            price_data = prices.get(str(type_id)) or prices.get(type_id, {})
            history_line = histories_line.get(type_id, None)

            highest_buy = price_data.get("highest_buy", {})
            lowest_sell = price_data.get("lowest_sell", {})

            buy_price = highest_buy.get("price", 0) if highest_buy else 0
            sell_price = lowest_sell.get("price", 0) if lowest_sell else 0
            mid_price = (buy_price + sell_price) / 2 if buy_price and sell_price else 0

            buy_volume_remain = highest_buy.get("volume_remain", 0) if highest_buy else 0
            sell_volume_remain = lowest_sell.get("volume_remain", 0) if lowest_sell else 0

            item_sell = sell_price * num if sell_price else 0
            item_buy = buy_price * num if buy_price else 0
            item_mid = mid_price * num if mid_price else 0

            total_sell += item_sell
            total_buy += item_buy
            total_mid += item_mid

            formatted_item = {
                "typeID": type_id,
                "name": item["transName"] or item["typeName"],
                "quantity": num,
                "sell_price": sell_price,
                "buy_price": buy_price,
                "mid_price": mid_price,
                "total_sell": item_sell,
                "total_buy": item_buy,
                "total_mid": item_mid,
                "buy_volume_remain": buy_volume_remain,
                "sell_volume_remain": sell_volume_remain,
                "history_line": history_line
            }
            formatted_items.append(formatted_item)

        pagination = {
            "current_page": current_page,
            "total_pages": page_data["total_pages"],
            "total_count": total_count,
            "has_next": current_page < page_data["total_pages"],
            "has_prev": current_page > 1
        }

        result = {
            "success": True,
            "items": formatted_items,
            "pagination": pagination,
            "word": word,
            "num": num
        }

        if is_all_grade:
            result["group_total"] = {
                "sell": total_sell,
                "buy": total_buy,
                "mid": total_mid
            }

        return result

    async def next(self, session, word: str, current_page: int, num: int = 1) -> Dict[str, Any]:
        """获取下一页结果"""
        return await self.get(session, word, num, current_page + 1)

    async def prev(self, session, word: str, current_page: int, num: int = 1) -> Dict[str, Any]:
        """获取上一页结果"""
        return await self.get(session, word, num, current_page - 1)

price_helper = PriceHelper()