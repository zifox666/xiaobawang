from nonebot import logger

from ..api.anoik import anoik_api


class WormholeHelper:
    def __init__(self):
        self._static_data: dict | None = {}
        self._constellations: dict | None = {}
        self._effects: dict | None = {}
        self._wormholes: dict | None = {}
        self._celestialtypes: dict | None = {}
        self._wormholeclasses: dict | None = {}
        self._roman: list | None = []
        self._systems: dict | None = {}
        self._regions: dict | None = {}
        self._connect: dict = {}

    def _format_wormhole(self):
        """
        初始化漫游洞
        :return:
        """
        for name, data in self._wormholes.items():
            if src := data.get("src", []):
                for src_id in src:
                    if src_id not in self._connect:
                        self._connect[src_id] = []
                    if not data.get("static"):
                        d = {
                            "name": name,
                            "dest": data.get("dest", "c0"),
                            "color": self._wormholeclasses[data.get("dest", "c0")].get("color", "#FFFFFF"),
                            "total_mass": data.get("total_mass", 0),
                        }
                        self._connect[src_id].append(d)

    async def _initialize(self):
        """
        初始化虫洞助手
        :return:
        """
        logger.debug("初始化虫洞数据")
        self._static_data = await anoik_api.get_static()
        self._constellations = self._static_data.get("constellations", {})
        self._effects = self._static_data.get("effects", {})
        self._wormholes = self._static_data.get("wormholes", {})
        self._celestialtypes = self._static_data.get("celestialtypes", {})
        self._wormholeclasses = self._static_data.get("wormholeclasses", {})
        self._roman = self._static_data.get("roman", [])
        self._systems = self._static_data.get("systems", {})
        self._regions = self._static_data.get("regions", {})

        self._format_wormhole()
        self._static_data = {}

    def _make_wormhole(self, data: dict, name: str) -> dict:
        """
        整理虫洞数据
        :param data: 原始虫洞数据
        :param name: 洞名称
        :return: 格式化后的虫洞信息
        """
        if name == "K162":
            result = {
                "name": "K162",
                "dest": "由对面先发现",
                "src": [],
                "max_mass_per_jump": 0,
                "total_mass": 0,
                "lifetime": 24,
                "dest_info": {},
                "color": "hsl(100, 100%, 100%)",
                "src_info": [],
                "max_mass_formatted": "0",
                "mass_per_jump_ratio": 3.0,
                "mass_per_jump_ratio_formatted": "0",
                "total_mass_formatted": "0",
                "static": "漫游 ",
                "mass_regen": 0,
                "ship_support": "",
            }
            return result

        result = {}

        # 基本信息
        result["name"] = name
        result["dest"] = data.get("dest", "c0")
        result["src"] = data.get("src", [])
        result["max_mass_per_jump"] = data.get("max_mass_per_jump", 0)
        result["total_mass"] = data.get("total_mass", 0)
        result["lifetime"] = data.get("lifetime", "未知")

        # 目标区域信息
        if result["dest"] in self._wormholeclasses:
            result["dest_info"] = self._wormholeclasses[result["dest"]]
            result["color"] = result["dest_info"].get("color", "#FFFFFF")
        else:
            result["dest_info"] = {}
            result["color"] = "#FFFFFF"

        # 可能的来源区域
        result["src_info"] = []
        if result["src"]:
            for src_class in result["src"]:
                if src_class in self._wormholeclasses:
                    src_data = {
                        "class": src_class,
                        "name": src_class,
                        "color": self._wormholeclasses[src_class].get("color", "#FFFFFF"),
                    }
                    result["src_info"].append(src_data)

        # 格式化质量信息
        if result["max_mass_per_jump"] > 0:
            result["max_mass_formatted"] = "{:,.0f}".format(result["max_mass_per_jump"])
            result["mass_per_jump_ratio"] = (
                result["total_mass"] / result["max_mass_per_jump"] if result["max_mass_per_jump"] != 0 else 0
            )
            result["mass_per_jump_ratio_formatted"] = "{:.2f}".format(result["mass_per_jump_ratio"])

        if result["total_mass"] > 0:
            result["total_mass_formatted"] = "{:,.0f}".format(result["total_mass"])

        # 附加信息
        result["static"] = "固定" if data.get("static", False) else "漫游"
        result["mass_regen"] = data.get("mass_regen", 0)

        # 封装船只类型支持信息
        if result["max_mass_per_jump"] >= 1000000000:
            result["ship_support"] = "支持大型船只（包括运输舰）"
        elif result["max_mass_per_jump"] >= 300000000:
            result["ship_support"] = "支持中型船只（不含运输舰）"
        else:
            result["ship_support"] = "仅支持小型船只"

        return result

    def _make_system(self, data: dict) -> dict:
        """
        整理虫洞星系数据
        :param data:
        :return:
        """
        result: dict = {"name": data.get("solarSystemName", "Unknown")}
        # 名称类
        region_id = data.get("regionID", 0)
        result["region_name"] = self._regions.get(str(region_id), "Unknown")
        constellation_id = data.get("constellationID", 0)
        result["constellation_name"] = self._constellations.get(str(constellation_id), "Unknown")

        result["class"] = data.get("wormholeClass", "c1")
        result["class_info"] = self._wormholeclasses.get(result["class"], {})

        # 效果类
        if effect := data.get("effectName", None):
            effect_info = self._effects.get(effect, "Unknown")
            effect_details = []
            for effect_name, effect_data in effect_info.items():
                effect_details.append(f"{effect_name}: {effect_data[result['class_info']['effectPower']]}")

            result["effect"] = {"name": effect, "effect_details": effect_details}
        else:
            result["effect"] = {}

        # 连接虫洞类
        result["statics"] = []
        statics = data.get("statics", [])
        for name in statics:
            d = {
                "name": name,
                "dest": self._wormholes[name].get("dest", "c0"),
                "color": self._wormholeclasses[self._wormholes[name].get("dest", "c0")].get("color", "#FFFFFF"),
                "total_mass": self._wormholes[name].get("total_mass", 0),
            }
            result["statics"].append(d)
        result["wanderings"] = self._connect.get(result["class"], [])

        # 其他
        result["cels"] = data.get("cels", [])
        """
        cel pb
        0: 6=Sun,7:Plant
        1: celestialTypeID
        Plant Only:
        2: x
        3: y
        4: z
        5: 轨道
        6: 当前轨道的第几个 只有一个就没有
        """

        result["celestialtypes"] = self._celestialtypes

        return result

    async def get(self, name: str) -> tuple[dict | None, str]:
        """
        获取虫洞数据
        :param name: 洞名称
        :return:
        """
        name = str.capitalize(name)
        if not self._wormholes:
            await self._initialize()
        if name in self._wormholes:
            return self._make_wormhole(self._wormholes[name], name), "wormhole"
        elif name in self._systems:
            return self._make_system(self._systems[name]), "system"
        else:
            return None, "Not Found"
