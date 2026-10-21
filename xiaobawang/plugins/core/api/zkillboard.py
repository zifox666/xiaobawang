from typing import Any

from nonebot import logger

from ..utils.common.cache import cache, cache_result
from .base import BaseClient
from .zkb_ranks import parse_ranks_html


class ZkillboardApi(BaseClient):
    """
    Zkillboard API
    """

    def __init__(self):
        super().__init__()
        self._base_url: str = "https://zkillboard.com/api"
        self._site_url: str = "https://zkillboard.com"
        # 短类型名 -> zkillboard API 实体类型名
        self._type_map: dict[str, str] = {
            "character": "characterID",
            "corporation": "corporationID",
            "alliance": "allianceID",
            "faction": "factionID",
            "ship": "shipTypeID",
            "group": "groupID",
            "system": "solarSystemID",
            "region": "regionID",
        }
        self._allowed_types: list[str] = list(self._type_map.keys())
        # Top Ranks 页面支持的实体类型（group 类型页面返回 403，不支持）
        self._rank_types: list[str] = ["character", "corporation", "alliance", "faction", "shipType"]
        # Top Ranks 支持的排序键（overallRank 为综合排名，其余为指标列）
        self._rank_sorts: list[str] = [
            "overallRank", "shipsDestroyed", "shipsLost",
            "pointsDestroyed", "pointsLost", "iskDestroyed", "iskLost",
        ]

    def _resolve_type(self, type_: str) -> str:
        """
        解析实体类型为 zkillboard API 类型名
        :param type_: 短类型名(character/corporation/...) 或 API 类型名(characterID/...)
        :return: API 类型名
        """
        if type_ in self._type_map:
            return self._type_map[type_]
        if type_ in self._type_map.values():
            return type_
        raise ValueError(f"不支持的类型: {type_}")

    @cache_result(expire_time=5 * cache.TIME_MIN, prefix="zkill:get_stats", exclude_args=[0])
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
            endpoint = f"/stats/{self._type_map[type_]}/{id_}/kills/"
            data = await self._get(endpoint)
            return data
        except Exception as e:
            logger.error(f"获取Zkillboard数据失败: {e}")
            return None

    @cache_result(expire_time=5 * cache.TIME_MIN, prefix="zkill:get_killmail_list", exclude_args=[0])
    async def get_killmail_list(
        self,
        type_: str,
        id_: str | int,
    ) -> dict[str, Any] | None:
        """
        获取击杀列表
        :param type_: 短类型名或 API 类型名（characterID 等，stats 响应的 type 字段可直接传入）
        :param id_:
        :return:
        """
        try:
            endpoint = f"/{self._resolve_type(type_)}/{id_}/"
            data = await self._get(endpoint)
            return data
        except Exception as e:
            logger.error(f"获取Zkillboard数据失败: {e}")
            return None


    @cache_result(expire_time=30 * cache.TIME_MIN, prefix="zkill:get_ranks", exclude_args=[0])
    async def get_ranks(
        self,
        type_: str,
        kl: str = "k",
        epoch: str = "recent",
        group: str = "all",
        page: int = 1,
        sort: str = "overallRank",
    ) -> list[dict[str, Any]]:
        """
        获取 zKillboard Top Ranks 页面数据（每页最多 500 行）

        页面地址: https://zkillboard.com/{type}/ranks/{kl}/{group}/{epoch}/{page}/[{sort}/{dir}/]
        :param type_: 实体类型 character/corporation/alliance/faction/shipType
        :param kl: 阵营 k=击杀(killers) / l=损失(losers)
        :param epoch: 时间范围 weekly(7天)/recent(90天)/alltime(开服以来)
        :param group: 全部(all) / 仅SOLO(solo)
        :param page: 页码
        :param sort: 排序键，overallRank 为综合排名（升序），指标键为降序
        :return: 解析后的行列表，见 zkb_ranks.parse_ranks_html
        """
        if type_ not in self._rank_types:
            raise ValueError(f"不支持的排行榜类型: {type_}")
        if kl not in ("k", "l"):
            raise ValueError(f"不支持的阵营: {kl}")
        if epoch not in ("weekly", "recent", "alltime"):
            raise ValueError(f"不支持的时间范围: {epoch}")
        if group not in ("all", "solo"):
            raise ValueError(f"不支持的分组: {group}")
        if sort not in self._rank_sorts:
            raise ValueError(f"不支持的排序键: {sort}")

        direction = "asc" if sort == "overallRank" else "desc"
        endpoint = f"/{type_}/ranks/{kl}/{group}/{epoch}/{page}/{sort}/{direction}/"

        try:
            html_text = await self._get_text(endpoint, base_url=self._site_url)
            rows = parse_ranks_html(html_text)
            if not rows:
                logger.warning(f"zKillboard 排行榜解析为空: {endpoint}")
            return rows
        except Exception as e:
            logger.error(f"获取zKillboard排行榜失败: {e}")
            raise


zkb_api = ZkillboardApi()
