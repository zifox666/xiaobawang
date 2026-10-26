import asyncio
from datetime import datetime
import traceback

from nonebot import logger

from ...api.esi.universe import esi_client
from ...api.killmail import get_zkb_killmail
from ...api.zkillboard import zkb_api
from ...utils.common import format_value
from ...utils.render import render_template, templates_path
from .label import ZkbLabelHelper


class ZkbStats:
    """
    zkillboard 统计处理

    支持 zkillboard 全部实体类型:
    characterID / corporationID / allianceID / factionID /
    shipTypeID / groupID / solarSystemID / regionID

    各实体类型字段差异（实测 /api/stats/{type}/{id}/）:
    - regionID / solarSystemID: 无 shipsLost/pointsLost/iskLost/soloLosses；
      solarSystemID 还无 dangerRatio
    - factionID / shipTypeID / groupID / regionID: 无 activity（活动热图）
    - shipTypeID: info 为 null，名称需通过 ESI 解析
    - allianceID: info 字段为 camelCase（memberCount/corpCount/executorCorpID）
    """

    def __init__(self, data: dict):
        self.data = data

        self._id: int = data.get("id", 0)
        self._type: str = data.get("type", "")

        # info 可能为 null（shipTypeID），统一兜底为空 dict
        self.info: dict = data.get("info") or {}
        self.name: str = self.info.get("name", "")

        # ---- 通用战斗统计（部分实体可能缺失损失侧字段） ----
        self.ships_destroyed: int = data.get("shipsDestroyed", 0)
        self.points_destroyed: int = data.get("pointsDestroyed", 0)
        self.isk_destroyed: float = data.get("iskDestroyed", 0.00)

        self.ships_lost: int = data.get("shipsLost", 0)
        self.points_lost: int = data.get("pointsLost", 0)
        self.isk_lost: float = data.get("iskLost", 0.00)
        # regionID / solarSystemID 没有损失统计
        self.has_loss_data: bool = "shipsLost" in data or "iskLost" in data

        self.solo_kills: int = data.get("soloKills", 0)
        self.solo_losses: int = data.get("soloLosses", 0)

        self.danger_ratio: float = data.get("dangerRatio", 0.0)
        self.gang_ratio: float = data.get("gangRatio", 0.0)
        # solarSystemID / regionID 无 dangerRatio
        self.has_danger_ratio: bool = "dangerRatio" in data

        self.avg_gang_size: float = data.get("avgGangSize", 0.0)

        if self.ships_destroyed > 0:
            self.ship_ratio: float = self.points_destroyed / self.ships_destroyed
        else:
            self.ship_ratio: float = 0.00

        self.active_pvp: dict = data.get("activepvp") or {}
        self.kills: int = self.active_pvp.get("kills", {}).get("count", 0)

        # 活动热图（factionID/shipTypeID/groupID/regionID 无此字段）
        self.activity: dict = data.get("activity") or {}
        self.has_activity: bool = bool(self.activity)

        # 排名（weekly/recent/alltime 三档，ranks.all.overall 为综合排名）
        self.rankings: dict = data.get("rankings") or {}

        self.top_lists: list = data.get("topLists") or []
        for item in self.top_lists:
            if item.get("type") == "shipType":
                self.top_ships = item.get("values", [])
            if item.get("type") == "character":
                self.top_characters = item.get("values", [])
        self.top_ships: list = getattr(self, "top_ships", [])
        self.top_characters: list = getattr(self, "top_characters", [])

        self.query_names: dict[int, str] = {}

        # 低活跃实体 activepvp 为空时会跳过 KM 处理，需提前初始化
        self.killmail_data: list = []
        self.recent_killmails: list = []

        self.labels: dict = ZkbLabelHelper(data).make()

        # ---- 各实体类型的专属信息 ----
        if self._type == "characterID":
            self.corporation_id: int = self.info.get("corporation_id", 0)
            self.alliance_id: int = self.info.get("alliance_id", 0)
            self.birthday: datetime = datetime.strptime(
                self.info.get("birthday", "1999-01-01T00:00:00Z"), "%Y-%m-%dT%H:%M:%SZ"
            )
            self.security_status: float = self.info.get("secStatus", 0.00)
            self.title: str | None = self.info.get("title", None)
        elif self._type == "corporationID":
            self.alliance_id: int = self.info.get("alliance_id", 0)
            self.ticker: str = self.info.get("ticker", "")
            self.ceo_id: int = self.info.get("ceo_id", 0)
            self.date_founded: datetime = datetime.strptime(
                self.info.get("date_founded", "1999-01-01T00:00:00Z"), "%Y-%m-%dT%H:%M:%SZ"
            )
            self.member_count: int = self.info.get("member_count", 0)
        elif self._type == "allianceID":
            # 注意: alliance 的 info 字段是 camelCase
            self.ticker: str = self.info.get("ticker", "")
            self.executor_corp_id: int = self.info.get("executor_corp_id") or self.info.get("executorCorpID", 0)
            self.member_count: int = self.info.get("memberCount", 0)
            self.corp_count: int = self.info.get("corpCount", 0)
            self.date_founded: datetime | None = None
            if self.info.get("date_founded"):
                self.date_founded = datetime.strptime(
                    self.info["date_founded"], "%Y-%m-%dT%H:%M:%SZ"
                )
        elif self._type == "shipTypeID":
            # info 为 null，名称/组名在 _query_info 中通过 ESI/SDE 解析
            self.group_name: str = ""
        elif self._type == "groupID":
            self.category_id: int = self.info.get("category_id") or self.info.get("categoryID", 0)
        elif self._type == "solarSystemID":
            self.security_status: float = self.info.get("secStatus") or self.info.get("security_status", 0.0)
            self.security_class: str = self.info.get("secClass") or self.info.get("security_class", "")
            self.region_id: int = self.info.get("regionID") or self.info.get("region_id", 0)
            self.constellation_id: int = self.info.get("constellation_id") or self.info.get("constellationID", 0)

    def get_rank(self, scope: str, key: str = "overall") -> int | None:
        """
        获取指定范围的排名
        :param scope: weekly / recent / alltime
        :param key: 排名键，默认 overall（综合排名）
        :return: 无数据时返回 None（部分实体的 scope 可能是空列表而非字典）
        """
        scope_data = self.rankings.get(scope)
        if not isinstance(scope_data, dict):
            return None
        all_data = scope_data.get("all")
        if not isinstance(all_data, dict):
            return None
        ranks = all_data.get("ranks")
        if not isinstance(ranks, dict):
            return None
        rank = ranks.get(key)
        return int(rank) if isinstance(rank, (int, float)) else None

    async def _query_names(self, query_ids: set[int]):
        data = await esi_client.get_names(list(query_ids))
        if not data:
            return

        for category, id_name_map in data.items():
            for item_id, name in id_name_map.items():
                self.query_names[int(item_id)] = name

    async def _query_info(self):
        query_ids: set[int] = set()
        if self._type == "characterID":
            query_ids.add(self.corporation_id)
            query_ids.add(self.alliance_id)
        elif self._type == "corporationID":
            query_ids.add(self.alliance_id)
            query_ids.add(self.ceo_id)
        elif self._type == "allianceID":
            # 执行军团（CEO 所在军团）
            query_ids.add(self.executor_corp_id)
        elif self._type == "shipTypeID":
            # info 为 null，通过 ESI 解析舰船名称
            await self._query_names({self._id})
            self.name = self.query_names.get(self._id, "") or self.name
        elif self._type == "solarSystemID":
            # 星系所属区域名称
            query_ids.add(self.region_id)
            query_ids.add(self.constellation_id)

        if query_ids:
            await self._query_names(query_ids)

        if self._type == "characterID":
            self.corporation_name = self.query_names.get(self.corporation_id, "")
            self.alliance_name = self.query_names.get(self.alliance_id, "")
        elif self._type == "corporationID":
            self.alliance_name = self.query_names.get(self.alliance_id, "")
            self.ceo_name = self.query_names.get(self.ceo_id, "")
        elif self._type == "allianceID":
            self.executor_corp_name = self.query_names.get(self.executor_corp_id, "")
        elif self._type == "shipTypeID":
            # 舰船所属组名（中文），如 突击舰/隐秘侦察舰
            try:
                from xiaobawang.plugins.sde.oper import sde_search
                self.group_name = await sde_search.get_type_group(self._id) or ""
            except Exception:
                logger.debug(f"获取舰船组名失败: {self._id}")
        elif self._type == "solarSystemID":
            self.region_name = self.query_names.get(self.region_id, "")
            self.constellation_name = self.query_names.get(self.constellation_id, "")

    async def _handle_killmail(self, data: dict) -> dict:
        """
        处理击杀数据
        :param data:
        :return:
        """
        try:
            query_ids: set[int] = set()
            if not data:
                return {}
            victim = data.get("victim", {})
            attackers = data.get("attackers", [])
            zkb_data = data.get("zkb", {})
            final_attacker = {}
            for attacker in attackers:
                if attacker.get("final_blow", False):
                    final_attacker = attacker
                    break

            final_attacker_character_id = final_attacker.get("character_id", 0)
            final_attacker_corporation_id = final_attacker.get("corporation_id", 0)
            final_attacker_alliance_id = final_attacker.get("alliance_id", 0)
            query_ids.add(final_attacker_character_id)
            query_ids.add(final_attacker_corporation_id)
            query_ids.add(final_attacker_alliance_id)

            query_ids.add(victim.get("character_id", 0))
            query_ids.add(victim.get("corporation_id", 0))
            query_ids.add(victim.get("alliance_id", 0))
            query_ids.add(victim.get("ship_type_id", 0))
            query_ids.add(data.get("solar_system_id", 0))

            system_data = await esi_client.get_system_info(data.get("solar_system_id", 0))
            region_name = system_data.get("region_name", "")

            await self._query_names(query_ids)
            result = {
                "killmail_id": data.get("killmail_id", 0),
                "killmail_time": data.get("killmail_time", ""),
                "ship_type_id": victim.get("ship_type_id", 0),
                "victim": {
                    "character_id": victim.get("character_id", 0),
                    "corporation_id": victim.get("corporation_id", 0),
                    "alliance_id": victim.get("alliance_id", 0),
                    "character_name": self.query_names.get(victim.get("character_id", 0), "unknown"),
                    "corporation_name": self.query_names.get(victim.get("corporation_id", 0), "unknown"),
                    "alliance_name": self.query_names.get(victim.get("alliance_id", 0), "unknown"),
                },
                "attacker": {
                    "character_id": final_attacker_character_id,
                    "corporation_id": final_attacker_corporation_id,
                    "alliance_id": final_attacker_alliance_id,
                    "character_name": self.query_names.get(final_attacker_character_id, "unknown"),
                    "corporation_name": self.query_names.get(final_attacker_corporation_id, "unknown"),
                    "alliance_name": self.query_names.get(final_attacker_alliance_id, "unknown"),
                },
                "solar_system_id": data.get("solar_system_id", 0),
                "solar_system_name": self.query_names.get(data.get("solar_system_id", 0), "unknown"),
                "total_value": format_value(zkb_data.get("totalValue", 0)),
                "solo": zkb_data.get("solo", False),
                "total_attackers": len(attackers),
                "region_name": region_name,
            }

            ids_to_remove = {final_attacker_character_id, final_attacker_corporation_id, final_attacker_alliance_id}
            query_ids -= ids_to_remove

            # 按实体类型判断这封 KM 是否为该实体的损失
            if self._type == "characterID":
                lose = victim.get("character_id") == self._id
            elif self._type == "corporationID":
                lose = victim.get("corporation_id") == self._id
            elif self._type == "allianceID":
                lose = victim.get("alliance_id") == self._id
            elif self._type == "shipTypeID":
                lose = victim.get("ship_type_id") == self._id
            elif self._type == "solarSystemID":
                lose = data.get("solar_system_id") == self._id
            elif self._type == "regionID":
                lose = system_data.get("region_id") == self._id
            else:
                lose = None
            result["lose"] = lose

            return result
        except Exception:
            logger.error(f"处理killmail失败\n{traceback.format_exc()}")
            return {}

    async def _handle_recent_killmail(self, limit: int = 3):
        self.killmail_data = []
        # 直接传 stats 响应的 type 字段（characterID 等），API 内部会自动解析
        killmails = await zkb_api.get_killmail_list(
            type_=self._type,
            id_=self._id,
        )
        if not killmails:
            self.recent_killmails = []
            return

        target_killmails = killmails[:limit]

        tasks = []
        for killmail in target_killmails:
            killmail_id = killmail.get("killmail_id")
            if killmail_id:
                tasks.append(self._process_single_killmail(killmail_id))

        results = await asyncio.gather(*tasks)

        self.killmail_data = [result for result in results if result]

    async def _process_single_killmail(self, killmail_id):
        """处理单个击杀邮件"""
        data = await get_zkb_killmail(killmail_id)
        return await self._handle_killmail(data=data)

    async def _make(self, limit: int = 3):
        """
        处理数据
        :return:
        """
        await self._query_info()
        if limit and self.active_pvp:
            await self._handle_recent_killmail(limit)

    async def render(self, limit: int = 3, command: str = "zkb") -> bytes:
        """
        渲染图片
        :param command: 命令： zkb / recent_km
        :param limit: 最近击杀数量
        :return:
        """
        await self._make(limit)
        return await render_template(
            template_path=templates_path / "zkb",
            template_name="zkb.html.jinja2" if command == "zkb" else "recent_km.html.jinja2",
            data={"stats": self},
            width=1280,
            height=900,
        )
