from datetime import datetime
from typing import Optional


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

    async def make(self):
        """
        处理数据
        :return:
        """
        query_ids = set()
        if self._type == "characterID":
            query_ids.add(self.corporation_id)
            query_ids.add(self.alliance_id)
        elif self._type == "corporationID":
            query_ids.add(self.alliance_id)





