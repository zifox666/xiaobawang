

class ZkbLabelHelper:
    def __init__(self, zkb: dict):
        self.zkb_labels: dict = zkb.get("labels", {})
        self.shipsDestroyed: int = zkb.get("shipsDestroyed", 0)
        self.danger_ratio: int = zkb.get("dangerRatio", 0)
        self.solo: int = zkb.get("soloKills", 0)
        if self.shipsDestroyed == 0:
            self.shipPoint = 0.0
        else:
            self.shipPoint: float = zkb.get("pointsDestroyed", 0.0) / self.shipsDestroyed

        del zkb

        self.local_label: list[str] = ["loc:nullsec", "loc:lowsec", "loc:highsec", "loc:w-space"]
        self.tz_label: list[str] = ["tz:au", "tz:eu", "tz:use", "tz:ru", "tz:usw"]
        self.member_label: list[str] = ["#1", "#10+", "#100+", "#2+", "#25+", "#5+", "#50+"]
        self.top: list[str] = [*self.local_label, *self.tz_label]

        self.condition_label: list[str] = ["awox", "atShip", "capital", "cat:22"]

        self.label: dict[str, dict[str, str | int]] = {
            "loc:nullsec": {
                "name": "00玩家",
                "color": "bg-red-500 text-white"
            },
            "loc:lowsec": {
                "name": "低安玩家",
                "color": "bg-orange-500 text-white"
            },
            "loc:highsec": {
                "name": "高安玩家",
                "color": "bg-blue-700 text-white"
            },
            "loc:w-space": {
                "name": "虫洞玩家",
                "color": "bg-gray-700 text-white"
            },
            "tz:au": {
                "name": "亚/澳时区",
                "color": "bg-amber-900 text-white"
            },
            "tz:eu": {
                "name": "欧洲时区",
                "color": "bg-yellow-600 text-white"
            },
            "tz:use": {
                "name": "美东时区",
                "color": "bg-red-400 text-white"
            },
            "tz:ru": {
                "name": "俄罗斯时区",
                "color": "bg-white text-gray-900"
            },
            "tz:usw": {
                "name": "美西时区",
                "color": "bg-red-400 text-white"
            },
            "cat:22": {
                "name": "拆迁狂",
                "percent": 0.05,
                "sum": 200,
                "color": "bg-gray-800 text-white"
            },
            "awox": {
                "name": "加团就是为了打蓝星",
                "percent": 0.05,
                "sum": 50,
                "color": "bg-blue-500 text-white"
            },
            "atShip": {
                "name": "AT SHIP",
                "percent": 0.001,
                "sum": 100,
                "color": "bg-yellow-500 text-white"
            },
            "capital": {
                "name": "旗舰杀手",
                "percent": 0.01,
                "sum": 100,
                "color": "bg-purple-600 text-white"
            }
        }
        self.result: dict[str, dict] = {"loc": {}, "tz:": {}}

    def top_handle(self, key: str, obj: dict):
        scope = obj.get("shipsDestroyed", 0) + obj.get("shipsLost", 0)
        if scope >= self.result[key[:3]].get("scope", 0):
            self.result[key[:3]]["name"] = self.label.get(key, {}).get("name", key)
            self.result[key[:3]]["color"] = self.label.get(key, {}).get("color", "")
            self.result[key[:3]]["scope"] = scope

    def condition_handle(self, key: str, obj: dict):
        if self.shipsDestroyed * self.label[key].get("percent", 0.05) <= obj.get("shipsDestroyed", 0):
            self.result[key] = {
                "name": self.label.get(key, {}).get("name", key),
                "color": self.label.get(key, {}).get("color", ""),
            }
        elif self.label[key].get("num", 100) <= obj.get("shipsDestroyed", 0):
            self.result[key] = {
                "name": self.label.get(key, {}).get("name", key),
                "color": self.label.get(key, {}).get("color", ""),
            }

    def pvp_handle(self):
        if self.shipsDestroyed >= 100 and self.danger_ratio >= 40:
            if self.shipPoint <= 1.4:
                self.result["f1"] = {
                    "name": "F1战士",
                    "color": "bg-green-900 text-white"
                }
            elif self.solo >= 50 and self.solo >= self.shipsDestroyed * 0.4:
                self.result["solo"] = {
                    "name": "SOLO",
                    "color": "bg-yellow-900 text-white"
                }
            elif self.shipPoint >= 2.0:
                self.result["small_team"] = {
                    "name": "小队糕手",
                    "color": "bg-purple-900 text-white"
                }

    def make(self) -> dict:
        for key, obj in self.zkb_labels.items():
            if key in self.top:
                self.top_handle(key, obj)
            elif key in self.condition_label:
                self.condition_handle(key, obj)

        self.pvp_handle()

        if not self.result["loc"]:
            self.result.pop("loc", None)
        if not self.result["tz:"]:
            self.result.pop("tz:", None)

        return self.result
