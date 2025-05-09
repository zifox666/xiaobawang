import traceback
from datetime import datetime
from typing import Optional

from nonebot import logger

from ...api.zkillboard import zkb_api
from ...api.esi.universe import esi_client
from ...api.killmail import get_zkb_killmail
from ...utils.common import format_value
from ...utils.render import render_template, templates_path


class ZkbStats:
    """
    zkillboard 统计处理
    """
    def __init__(self, data: dict):
        self.data = data

        self._id: int = data.get("id", 0)
        self._type: str = data.get("type", "")

        self.ships_destroyed: int = data.get("shipsDestroyed", 0)
        self.points_destroyed: int = data.get("pointsDestroyed", 0)
        self.isk_destroyed: float = data.get("iskDestroyed", 0.00)

        self.solo_kills: int = data.get("soloKills", 0)
        self.danger_ratio: float = data.get("dangerRatio", 0.0)
        self.gang_ratio: float = data.get("gangRatio", 0.0)

        self.ships_lost: int = data.get("shipsLost", 0)
        self.points_lost: int = data.get("pointsLost", 0)
        self.isk_lost: float = data.get("iskLost", 0.00)

        self.active_pvp: dict = data.get("activepvp", {})
        self.kills: int = self.active_pvp.get("kills", {}).get("count", 0)

        self.info: dict = data.get("info", {})
        self.name: str = self.info.get("name", "")
        if self._type == "characterID":
            self.corporation_id: int = self.info.get("corporation_id", 0)
            self.alliance_id: int = self.info.get("alliance_id", 0)
            self.birthday: datetime = datetime.strptime(self.info.get("birthday", "1999-01-01T00:00:00Z"), "%Y-%m-%dT%H:%M:%SZ")
            self.security_status: float = self.info.get("secStatus", 0.00)
            self.title: Optional[str] = self.info.get("title", None)
        if self._type == "corporationID":
            self.alliance_id: int = self.info.get("alliance_id", 0)
            self.ticker: str = self.info.get("ticker", "")
            self.ceo_id: int = self.info.get("ceo_id", 0)
            self.date_founded: datetime = datetime.strptime(self.info.get("date_founded", "1999-01-01T00:00:00Z"), "%Y-%m-%dT%H:%M:%SZ")
            self.member_count: int = self.info.get("member_count", 0)
        if self._type == "allianceID":
            # TODO: stats 补全计划
            pass

        self.activity: dict = data.get("activity", {})

        self.top_lists: list = data.get("topLists", [])
        for item in self.top_lists:
            if item.get("type") == "shipType":
                self.top_ships = item.get("values", [])
            if item.get("type") == "character":
                self.top_characters = item.get("values", [])

        self.query_names: dict[int, str] = {}

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

        await self._query_names(query_ids)

        if self._type == "characterID":
            self.corporation_name = self.query_names.get(self.corporation_id, "")
            self.alliance_name = self.query_names.get(self.alliance_id, "")
        elif self._type == "corporationID":
            self.alliance_name = self.query_names.get(self.alliance_id, "")
            self.ceo_name = self.query_names.get(self.ceo_id, "")

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
            print(final_attacker)

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
                "lose": True if victim.get("character_id", 0) == self._id else False,
            }

            return result
        except Exception as e:
            logger.error(f"处理killmail失败\n{traceback.format_exc()}")
            return {}


    async def _handle_recent_killmail(self):
        self.killmail_data = []
        killmails = await zkb_api.get_killmail_list(
            type_=self._type[:-2],
            id_=self._id,
        )
        if not killmails:
            self.recent_killmails = []
            return
        for killmail in killmails[:3]:
            killmail_id = killmail.get("killmail_id")
            if killmail_id:
                data = await get_zkb_killmail(killmail_id)
                result = await self._handle_killmail(data=data)
                print(result)
                if result:
                    self.killmail_data.append(result)

    async def _make(self):
        """
        处理数据
        :return:
        """
        await self._query_info()
        await self._handle_recent_killmail()


    async def render(self) -> bytes:
        """
        渲染图片
        :return:
        """
        await self._make()
        return await render_template(
            template_path=templates_path / "zkb",
            template_name="zkb.html.jinja2",
            data={"stats": self},
            width=1080,
            height=900,
        )





