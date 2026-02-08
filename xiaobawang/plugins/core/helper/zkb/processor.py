"""
Killmail 数据处理和渲染模块
负责处理 killmail 原始数据、格式化、渲染和发送
"""
from datetime import datetime, timezone
import math
from typing import Any

from nonebot import logger

from xiaobawang.plugins.sde.oper import sde_search

from ...api.esi.universe import esi_client
from ...utils.common import clean_colored_text, is_blueprint


class KillmailProcessor:
    """Killmail 数据处理器，负责格式化和渲染 killmail 数据"""

    async def process_killmail_data(self, killmail_data: dict[str, Any]) -> dict[str, Any]:
        """
        处理和格式化 killmail 数据用于渲染
        
        Args:
            killmail_data: 原始击杀邮件数据
            
        Returns:
            处理后的击杀邮件详细数据
        """
        try:
            ids_to_query = set()
            type_ids_to_query = set()

            # 收集需要查询的 ID
            victim = killmail_data.get("victim", {})
            victim_character_id = victim.get("character_id")
            victim_corporation_id = victim.get("corporation_id")
            victim_alliance_id = victim.get("alliance_id", 0)
            victim_ship_type_id = victim.get("ship_type_id")

            if victim_character_id:
                ids_to_query.add(victim_character_id)
            if victim_corporation_id:
                ids_to_query.add(victim_corporation_id)
            if victim_alliance_id:
                ids_to_query.add(victim_alliance_id)
            if victim_ship_type_id:
                type_ids_to_query.add(victim_ship_type_id)

            solar_system_id = killmail_data.get("solar_system_id")
            if solar_system_id:
                ids_to_query.add(solar_system_id)

            attackers = killmail_data.get("attackers", [])
            for attacker in attackers:
                attacker_character_id = attacker.get("character_id")
                attacker_corporation_id = attacker.get("corporation_id")
                attacker_alliance_id = attacker.get("alliance_id")
                attacker_ship_type_id = attacker.get("ship_type_id")
                weapon_type_id = attacker.get("weapon_type_id")

                if attacker_character_id:
                    ids_to_query.add(attacker_character_id)
                if attacker_corporation_id:
                    ids_to_query.add(attacker_corporation_id)
                if attacker_alliance_id:
                    ids_to_query.add(attacker_alliance_id)
                if attacker_ship_type_id:
                    type_ids_to_query.add(attacker_ship_type_id)
                if weapon_type_id:
                    type_ids_to_query.add(weapon_type_id)

            def collect_item_ids(items_list):
                for item in items_list:
                    item_type_id = item.get("item_type_id")
                    if item_type_id:
                        type_ids_to_query.add(item_type_id)

                    # 处理嵌套物品
                    nested_items = item.get("items", [])
                    if nested_items:
                        collect_item_ids(nested_items)

            victim_items = victim.get("items", [])
            collect_item_ids(victim_items)

            entity_names = {}
            system_info = {}
            item_names = {}

            # 批量查询名称
            if ids_to_query:
                names_data = await esi_client.get_names(list(ids_to_query))

                for category, items in names_data.items():
                    for entity_id, name in items.items():
                        entity_names[int(entity_id)] = {"category": category, "name": name}

            if type_ids_to_query:
                item_names = await sde_search.get_type_names(list(type_ids_to_query))

            if solar_system_id:
                system_info = await esi_client.get_system_info(solar_system_id)

            # 处理时间
            killmail_time = datetime.fromisoformat(killmail_data.get("killmail_time", "").replace("Z", "+00:00"))
            current_time = datetime.now()
            time_difference = self._format_time_difference(killmail_time, current_time)
            formatted_time = killmail_time.strftime("%Y-%m-%d %H:%M:%S")

            # 处理安全等级
            security = system_info.get("security_status", 0)
            sec_color = self._get_security_color(security)
            sec_formatted = f"{security:.1f}" if security > 0 else "0.0"

            attacker_number = len(attackers)

            # 处理价值
            zkb_data = killmail_data.get("zkb", {})
            total_value = zkb_data.get("totalValue", 0)
            drop_value = zkb_data.get("droppedValue", 0)
            formatted_total_value = f"{total_value:,.2f}"
            formatted_drop_value = f"{drop_value:,.2f}"

            # 处理物品
            slot_list = self._format_items(victim.get("items", []), item_names, await sde_search.get_flag_info())

            result = {
                "killmail_id": killmail_data.get("killmail_id"),
                "killmail_time": killmail_data.get("killmail_time"),
                "time": formatted_time,
                "time_difference": time_difference,
                "solar_system_id": solar_system_id,
                "solar_system": system_info.get("system_name", "未知星系"),
                "constellation": system_info.get("constellation_name", "未知星座"),
                "region": system_info.get("region_name", "未知区域"),
                "sec_color": sec_color,
                "sec": sec_formatted,
                "victim": await self._format_victim(victim, entity_names, item_names),
                "attacker_number": attacker_number,
                "attackMember": self._format_attackers(attackers, entity_names, item_names),
                "slot_list": slot_list.get("slotList", []),
                "zkb": killmail_data.get("zkb", {}),
                "total_value": formatted_total_value,
                "drop_value": formatted_drop_value,
                "position": killmail_data.get("position", {}),
            }

            # 计算最近天体
            if killmail_data.get("victim").get("position"):
                result["nearest_celestial"] = await self._calculate_nearest_celestial(
                    killmail_data.get("victim").get("position"), killmail_data["zkb"].get("locationID", 0)
                )
                result["location_name"] = result["nearest_celestial"].get("location_name", "未知位置")
                result["distance_str"] = result["nearest_celestial"].get("distance_str", "未知距离")

            return result

        except Exception as e:
            logger.error(f"处理击杀邮件详细数据失败: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {}

    @classmethod
    async def _format_victim(
        cls, victim: dict[str, Any], entity_names: dict[int, dict], item_names: dict[int, dict]
    ) -> dict[str, Any]:
        """格式化受害者信息"""
        victim_id = victim.get("character_id", 0)
        corp_id = victim.get("corporation_id", 0)
        alliance_id = victim.get("alliance_id", 0)
        ship_type_id = victim.get("ship_type_id", 0)
        ship_group_name = await sde_search.get_type_group(victim.get("ship_type_id", 0))
        damage_taken = victim.get("damage_taken", 0)

        if victim_id:
            victim_info = await esi_client.get_character_public_info(victim_id)
            victim_title = victim_info.get("title", None)
            if victim_title:
                victim_title = clean_colored_text(victim_title)
        else:
            victim_title = None

        result = {
            "victim_id": victim_id,
            "victim_title": victim_title,
            "victim_name": entity_names.get(victim_id, {}).get("name", "Unknown"),
            "victim_corp_id": corp_id,
            "victim_corp": entity_names.get(corp_id, {}).get("name", "Unknown"),
            "victim_alliance_id": alliance_id,
            "victim_alliance_name": entity_names.get(alliance_id, {}).get("name", ""),
            "ship_type_id": ship_type_id,
            "ship_type_name": item_names.get(ship_type_id, {}).get("translation", "Unknown Ship"),
            "damage_taken": f"{damage_taken:,.0f}",
            "ship_group_name": ship_group_name,
        }

        return result

    @classmethod
    def _format_attackers(
        cls, attackers: list[dict], entity_names: dict[int, dict], item_names: dict[int, dict]
    ) -> list[dict]:
        """格式化攻击者信息"""
        formatted_attackers = []

        sorted_attackers = sorted(attackers, key=lambda a: a.get("damage_done", 0), reverse=True)

        total_damage = sum(attacker.get("damage_done", 0) for attacker in attackers)

        for attacker in sorted_attackers:
            character_id = attacker.get("character_id", 0)
            corporation_id = attacker.get("corporation_id", 0)
            alliance_id = attacker.get("alliance_id", 0)
            ship_type_id = attacker.get("ship_type_id", 0)
            weapon_type_id = attacker.get("weapon_type_id", 0)
            damage_done = attacker.get("damage_done", 0)

            formatted_attacker = {
                "attacker_id": character_id,
                "attacker_name": entity_names.get(character_id, {}).get("name", "Unknown"),
                "attacker_corp_id": corporation_id,
                "attacker_corp": entity_names.get(corporation_id, {}).get("name", "Unknown"),
                "attacker_alliance_id": alliance_id,
                "attacker_alliance": entity_names.get(alliance_id, {}).get("name", ""),
                "ship_type_id": ship_type_id,
                "ship_type_name": item_names.get(ship_type_id, {}).get("translation", "Unknown Ship"),
                "weapon_type_id": weapon_type_id,
                "weapon_type_name": item_names.get(weapon_type_id, {}).get("translation", "Unknown Weapon"),
                "damage_done": f"{damage_done:,.0f}",
                "damage_percent": round((damage_done / total_damage * 100) if total_damage else 0, 2),
                "final_blow": attacker.get("final_blow", False),
            }

            formatted_attackers.append(formatted_attacker)

        final_blow_index = next((i for i, a in enumerate(formatted_attackers) if a.get("final_blow")), 0)
        if final_blow_index > 0:
            final_blow = formatted_attackers.pop(final_blow_index)
            formatted_attackers.insert(0, final_blow)

        return formatted_attackers

    def _format_items(
        self, items: list[dict], item_names: dict[int, dict], flag_info: dict[int, str]
    ) -> dict[str, Any]:
        """
        格式化物品信息，按槽位类型分类并处理嵌套物品
        """
        slot_type_groups = {}

        # 临时存储，用于按物品ID和状态(drop/destroyed)合并相同物品
        # 结构: {slot_type: {item_id: {"drop": {}, "destroyed": {}}}}
        item_tracking = {}

        for item in items:
            flag = item.get("flag", 0)
            item_type_id = item.get("item_type_id", 0)
            quantity_dropped = item.get("quantity_dropped", 0)
            quantity_destroyed = item.get("quantity_destroyed", 0)
            singleton = item.get("singleton", 0)

            flag_name = flag_info.get(flag, f"Flag: {flag}")

            slot_type = self._get_slot_type(flag_name)
            slot_image = self._get_slot_image_name(slot_type)
            slot_display_name = self._get_slot_display_name(slot_type)

            if slot_type not in slot_type_groups:
                slot_type_groups[slot_type] = {
                    "slotName": slot_display_name,
                    "slotPng": slot_image,
                    "slot_items": [],
                    "slotType": slot_type,
                }
                item_tracking[slot_type] = {}

            item_name = item_names.get(item_type_id, {}).get("translation", f"TypeID: {item_type_id}")

            if is_blueprint(item_name):
                item_name = f"{item_name} ({'拷贝' if singleton == 2 else '原图'})"
                blueprint = True
            else:
                blueprint = False

            nested_items = []
            has_nested = "items" in item
            if has_nested:
                nested_items = self._process_nested_items(
                    item["items"], item_names, "drop" if quantity_dropped > 0 else "destroyed"
                )

                if quantity_dropped > 0:
                    slot_type_groups[slot_type]["slot_items"].append(
                        {
                            "item_id": item_type_id,
                            "item_name": item_name,
                            "item_number": quantity_dropped,
                            "drop": "drop",
                            "nested_items": nested_items,
                            "singleton": singleton,
                            "blueprint": blueprint,
                        }
                    )

                if quantity_destroyed > 0:
                    slot_type_groups[slot_type]["slot_items"].append(
                        {
                            "item_id": item_type_id,
                            "item_name": item_name,
                            "item_number": quantity_destroyed,
                            "drop": "destroyed",
                            "nested_items": nested_items,
                            "singleton": singleton,
                            "blueprint": blueprint,
                        }
                    )
            else:
                item_key = (item_type_id, singleton)
                if item_key not in item_tracking[slot_type]:
                    item_tracking[slot_type][item_key] = {
                        "drop": {"count": 0, "name": item_name, "singleton": singleton, "blueprint": blueprint},
                        "destroyed": {"count": 0, "name": item_name, "singleton": singleton, "blueprint": blueprint},
                    }

                if quantity_dropped > 0:
                    item_tracking[slot_type][item_key]["drop"]["count"] += quantity_dropped

                if quantity_destroyed > 0:
                    item_tracking[slot_type][item_key]["destroyed"]["count"] += quantity_destroyed

        for slot_type, items_map in item_tracking.items():
            for item_key, states in items_map.items():
                item_id, singleton = item_key
                if states["drop"]["count"] > 0:
                    slot_type_groups[slot_type]["slot_items"].append(
                        {
                            "item_id": item_id,
                            "item_name": states["drop"]["name"],
                            "item_number": states["drop"]["count"],
                            "drop": "drop",
                            "nested_items": None,
                            "singleton": states["drop"]["singleton"],
                            "blueprint": states["drop"]["blueprint"],
                        }
                    )

                if states["destroyed"]["count"] > 0:
                    slot_type_groups[slot_type]["slot_items"].append(
                        {
                            "item_id": item_id,
                            "item_name": states["destroyed"]["name"],
                            "item_number": states["destroyed"]["count"],
                            "drop": "destroyed",
                            "nested_items": None,
                            "singleton": states["destroyed"]["singleton"],
                            "blueprint": states["destroyed"]["blueprint"],
                        }
                    )

        # 按优先级排序槽位组
        slot_order = {"high": 1, "med": 2, "low": 3, "rig": 4, "subsystem": 5, "drone": 6, "fighter": 7, "cargo": 8}

        slot_list = list(slot_type_groups.values())
        slot_list.sort(key=lambda x: slot_order.get(x["slotType"], 999))

        return {
            "slotList": slot_list,
        }

    def _process_nested_items(self, nested_items: list[dict], item_names: dict, drop: str = "destroyed") -> list[dict]:
        """
        递归处理嵌套物品，返回嵌套物品列表

        Args:
            nested_items: 嵌套物品列表
            item_names: 物品名称字典
            drop: 物品状态（"dropped" 或 "destroyed"）

        Returns:
            处理后的嵌套物品列表
        """
        formatted_items = []

        for item in nested_items:
            item_type_id = item.get("item_type_id", 0)
            quantity_dropped = item.get("quantity_dropped", 0)
            quantity_destroyed = item.get("quantity_destroyed", 0)
            singleton = item.get("singleton", 0)

            item_name = item_names.get(item_type_id, {}).get("translation", f"TypeID: {item_type_id}")

            if is_blueprint(item_name):
                item_name = f"{item_name} ({'拷贝' if singleton == 2 else '原图'})"
                blueprint = True
            else:
                blueprint = False

            sub_items = []
            if "items" in item:
                sub_items = self._process_nested_items(item["items"], item_names)

            if quantity_dropped > 0:
                formatted_items.append(
                    {
                        "item_id": item_type_id,
                        "item_name": item_name,
                        "item_number": quantity_dropped,
                        "drop": drop,
                        "nested_items": sub_items if sub_items else None,
                        "singleton": singleton,
                        "blueprint": blueprint,
                    }
                )

            if quantity_destroyed > 0:
                formatted_items.append(
                    {
                        "item_id": item_type_id,
                        "item_name": item_name,
                        "item_number": quantity_destroyed,
                        "drop": drop,
                        "nested_items": sub_items if sub_items else None,
                        "singleton": singleton,
                        "blueprint": blueprint,
                    }
                )

        return formatted_items

    @classmethod
    async def _calculate_nearest_celestial(cls, position: dict[str, float], location_id: int) -> dict[str, Any]:
        """
        计算距离最近的天体

        Args:
            location_id: 天体ID
            position: 击杀事件发生的位置坐标

        Returns:
            包含最近天体信息的字典
        """
        try:
            data = await esi_client.get_moon_info(location_id)

            dx = math.fabs(position["x"] - data["position"]["x"])
            dy = math.fabs(position["y"] - data["position"]["y"])
            dz = math.fabs(position["z"] - data["position"]["z"])
            distance = math.sqrt(dx**2 + dy**2 + dz**2)

            if distance > 149597870700 * 0.1:
                distance_au = distance / 149597870700
                distance_str = f"{distance_au:.2f} AU"
            else:
                distance_km = distance / 1000
                distance_str = f"{distance_km:,.2f} km"

            return {
                "location_name": data.get("name", "Unknown"),
                "distance_str": distance_str,
            }

        except Exception as e:
            logger.error(f"计算最近天体距离失败: {e}")
            return {"location_name": "Unknown", "distance_str": 0}

    @classmethod
    def _get_slot_image_name(cls, flag_name: str) -> str:
        """根据槽位名称获取对应的图标名称"""
        flag_name = flag_name.lower()

        if "high" in flag_name:
            return "3/3c/Icon_fit_high"
        elif "med" in flag_name:
            return "9/9a/Icon_fit_medium"
        elif "low" in flag_name:
            return "e/e6/Icon_fit_low"
        elif "rig" in flag_name:
            return "e/eb/Icon_fit_rig"
        elif "drone" in flag_name:
            return "thumb/0/07/Icon_fit_drone.png/48px-Icon_fit_drone"
        elif "cargo" in flag_name:
            return "thumb/8/82/Icon_capacity.png/48px-Icon_capacity"
        elif "subsystem" in flag_name:
            return "e/eb/Icon_fit_rig"
        elif "fighter" in flag_name:
            return "thumb/f/f6/Icon_drone_bandwidth.png/30px-Icon_drone_bandwidth"
        else:
            return "thumb/8/82/Icon_capacity.png/48px-Icon_capacity"

    @classmethod
    def _get_slot_type(cls, flag_name: str) -> str:
        """从槽位名称提取槽位类型（去掉数字编号）"""
        flag_name = flag_name.lower()

        if flag_name.startswith("hislot"):
            return "high"
        elif flag_name.startswith("medslot"):
            return "med"
        elif flag_name.startswith("loslot"):
            return "low"
        elif flag_name.startswith("rigslot"):
            return "rig"
        elif flag_name.startswith("subsystem"):
            return "subsystem"
        elif "drone" in flag_name:
            return "drone"
        elif "fighter" in flag_name:
            return "fighter"
        elif "cargo" in flag_name:
            return "cargo"
        else:
            return "other"

    @classmethod
    def _get_slot_display_name(cls, slot_type: str) -> str:
        """根据槽位类型获取显示名称"""
        if slot_type == "high":
            return "高能量槽"
        elif slot_type == "med":
            return "中能量槽"
        elif slot_type == "low":
            return "低能量槽"
        elif slot_type == "rig":
            return "改装件安装座"
        elif slot_type == "drone":
            return "无人机挂仓"
        elif slot_type == "cargo":
            return "货柜仓"
        elif slot_type == "subsystem":
            return "子系统槽位"
        elif slot_type == "fighter":
            return "铁骑舰载机机库"
        else:
            return "其他"

    @classmethod
    def _get_security_color(cls, security: float) -> str:
        """根据安全等级获取对应的颜色变量"""
        security_rounded = round(security, 1)

        if security_rounded <= 0.0:
            return "--00sec-color"
        elif security_rounded <= 0.1:
            return "--01sec-color"
        elif security_rounded <= 0.2:
            return "--02sec-color"
        elif security_rounded <= 0.3:
            return "--03sec-color"
        elif security_rounded <= 0.4:
            return "--04sec-color"
        elif security_rounded <= 0.5:
            return "--05sec-color"
        elif security_rounded <= 0.6:
            return "--06sec-color"
        elif security_rounded <= 0.7:
            return "--07sec-color"
        elif security_rounded <= 0.8:
            return "--08sec-color"
        elif security_rounded <= 0.9:
            return "--09sec-color"
        else:
            return "--10sec-color"

    @classmethod
    def _format_time_difference(cls, past_time: datetime, current_time: datetime) -> str:
        """计算并格式化两个时间之间的差异"""
        if past_time.tzinfo is None:
            past_time = past_time.replace(tzinfo=timezone.utc)

        if current_time.tzinfo is None:
            current_time = current_time.astimezone()

        past_time = past_time.astimezone(current_time.tzinfo)
        time_diff = current_time - past_time

        seconds = int(time_diff.total_seconds())

        if seconds < 60:
            return f"{seconds}秒前"

        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}分钟前"

        hours = minutes // 60
        if hours < 24:
            return f"{hours}小时前"

        days = hours // 24
        if days < 30:
            return f"{days}天前"

        months = days // 30
        if months < 12:
            return f"{months}个月前"

        years = months // 12
        return f"{years}年前"

    @classmethod
    def generate_killmail_text(cls, html_data: dict, reason: str) -> str:
        """生成击杀邮件的文本信息"""
        victim = html_data.get("victim", {})
        zkb_data = html_data.get("zkb", {})

        victim_name = victim.get("victim_name", "Unknown")
        victim_title = victim.get("victim_title", "")
        ship_name = victim.get("ship_type_name", "Unknown")
        ship_group = victim.get("ship_group_name", "Unknown")
        solar_system = html_data.get("solar_system", "Unknown")
        sec = html_data.get("sec", "0.0")
        region = html_data.get("region", "Unknown")
        location = html_data.get("location_name", "Unknown")
        distance = html_data.get("distance_str", "Unknown")
        time = html_data.get("time", "Unknown")
        time_difference = html_data.get("time_difference", "Unknown")
        drop_value = html_data.get("drop_value", "0")
        total_value = html_data.get("total_value", "0")

        points = zkb_data.get("points", 0)

        text = f"{reason}\n"
        text += f"受害者: {victim_name}\n"
        if victim_title:
            text += f"受害者头衔: {victim_title}\n"
        text += f"舰船: {ship_name} ({ship_group})\n"
        text += f"星系: {solar_system} ({sec}) / {region}\n"
        text += f"距离: {location} ({distance})\n"
        text += f"时间: {time}({time_difference})\n"
        text += f"分数: {points}\n"
        text += f"掉落: {drop_value} ISK\n"
        text += f"总价值: {total_value} ISK"

        return text
