from datetime import datetime, timezone
import json
from typing import Any, Tuple

from nonebot import logger

from ...api.esi.universe import esi_client


class ConditionMatcher:
    """条件匹配引擎 - 支持灵活的条件组合和标签匹配"""

    def __init__(self, killmail_data: dict, label_helper_result: dict = None):
        """
        初始化匹配器

        Args:
            killmail_data: zkillboard推送的完整killmail数据
            label_helper_result: 已废弃，改为直接从killmail的zkb.labels读取
        """
        self.data = killmail_data
        self.victim = killmail_data.get("victim", {})
        self.attackers = killmail_data.get("attackers", [])
        self.final_blow = next((a for a in self.attackers if a.get("final_blow")), {})
        self.zkb = killmail_data.get("zkb", {})
        # 直接从killmail的zkb.labels数组读取标签
        self.labels = set(self.zkb.get("labels", []))
        self.solar_system_id = killmail_data.get("solar_system_id")
        self.killmail_id = killmail_data.get("killmail_id")

    async def match_subscription(self, subscription: dict) -> Tuple[bool, list[str]]:
        """
        匹配订阅条件

        Args:
            subscription: 订阅配置字典,包含condition_groups字段

        Returns:
            (是否匹配, 匹配原因列表)
        """
        sub_id = subscription.get('id', 'unknown')
        # logger.debug(f"[KM:{self.killmail_id}] 开始匹配订阅 {sub_id}")
        
        try:
            # 检查全局过滤
            if not self._check_global_filters(subscription):
                # logger.debug(f"[KM:{self.killmail_id}] 订阅 {sub_id} 在全局过滤被丢弃")
                return False, []

            # 解析条件配置(支持字典或JSON字符串)
            condition_groups = subscription.get("condition_groups", {})
            if isinstance(condition_groups, str):
                condition_config = json.loads(condition_groups)
            else:
                condition_config = condition_groups or {}
            
            # logger.debug(f"[KM:{self.killmail_id}] 订阅 {sub_id} 条件配置: {condition_config}")

            # 递归匹配条件组
            matched, reasons = await self._match_condition_group(condition_config)
            
            if matched:
                logger.debug(f"[KM:{self.killmail_id}] 订阅 {sub_id} 匹配成功,原因: {reasons}")
            
            return matched, reasons
        except Exception as e:
            logger.error(f"订阅 {subscription.get('id')} 匹配出错: {e}")
            return False, []

    def _check_global_filters(self, subscription: dict) -> bool:
        """检查全局过滤条件"""
        sub_id = subscription.get('id', 'unknown')
        
        # 价值检查
        total_value = float(self.zkb.get("totalValue", 0))
        min_value = subscription.get("min_value", 1_000_000)
        # logger.debug(f"[KM:{self.killmail_id}] 订阅 {sub_id} 价值检查: {total_value:,.0f} >= {min_value:,.0f}")
        if total_value < min_value:
            # logger.debug(f"[KM:{self.killmail_id}] 订阅 {sub_id} 价值不足被丢弃")
            return False

        max_age_days = subscription.get("max_age_days", 10)
        # logger.debug(f"[KM:{self.killmail_id}] 订阅 {sub_id} 时效检查: max_age_days={max_age_days}")
        if not self._check_killmail_age(max_age_days):
            logger.debug(f"[KM:{self.killmail_id}] 订阅 {sub_id} 时效超期被丢弃")
            return False

        return True

    async def _check_killmail_age(self, max_age_days: int = 10) -> bool:
        """检查击杀时间"""
        killmail_time_str = self.data.get("killmail_time", "")
        if not killmail_time_str:
            logger.warning("收到无效的 killmail 数据: 缺少时间信息")
            return False

        try:
            killmail_time = datetime.fromisoformat(killmail_time_str.replace("Z", "+00:00"))
            current_time = datetime.now(timezone.utc)
            time_diff = current_time - killmail_time

            if time_diff.days > max_age_days:
                # logger.debug(f"击杀时间超过{max_age_days}天，
                # 忽略 killmail: {self.data.get('killmail_id')}, 时间: {killmail_time_str}")
                return False
            return True
        except Exception as e:
            logger.warning(f"解析击杀时间失败: {e}, 时间字符串: {killmail_time_str}")
            return False

    async def _match_condition_group(self, group: dict) -> Tuple[bool, list[str]]:
        """
        匹配条件组 - 支持递归AND/OR逻辑

        Args:
            group: 条件组配置 {"logic": "AND|OR", "conditions": [...], "groups": [...]}

        Returns:
            (是否匹配, 匹配原因列表)
        """
        logic = group.get("logic", "AND").upper()
        conditions = group.get("conditions", [])
        sub_groups = group.get("groups", [])
        
        # logger.debug(f"[KM:{self.killmail_id}]
        # 匹配条件组: logic={logic}, conditions={len(conditions)}, sub_groups={len(sub_groups)}")

        results = []
        reasons = []

        # 匹配直接条件
        for idx, condition in enumerate(conditions):
            matched, reason = await self._match_single_condition(condition)
            # logger.debug(f"[KM:{self.killmail_id}] 条件 #{idx+1} {condition.get('type')}: {'✓' if matched else '✗'} {reason or ''}")
            results.append(matched)
            if matched and reason:
                reasons.append(reason)

        # 递归匹配子组
        for idx, sub_group in enumerate(sub_groups):
            matched, sub_reasons = await self._match_condition_group(sub_group)
            # logger.debug(f"[KM:{self.killmail_id}] 子组 #{idx+1}: {'✓' if matched else '✗'}")
            results.append(matched)
            reasons.extend(sub_reasons)

        # 空条件组视为通过
        if not results:
            # logger.debug(f"[KM:{self.killmail_id}] 空条件组,默认通过")
            return True, reasons

        # 应用逻辑运算
        if logic == "AND":
            final_match = all(results)
        elif logic == "OR":
            final_match = any(results)
        else:
            logger.warning(f"Unknown logic operator: {logic}")
            final_match = False
        
        # logger.debug(f"[KM:{self.killmail_id}]
        # 条件组结果: {logic} -> {'✓ 通过' if final_match else '✗ 失败'} (results={results})")

        return final_match, reasons if final_match else []

    async def _match_single_condition(self, condition: dict) -> Tuple[bool, str]:
        """
        匹配单个条件

        Args:
            condition: 条件配置 {"type": "...", ...}

        Returns:
            (是否匹配, 匹配原因)
        """
        cond_type = condition.get("type", "").lower()
        # logger.debug(f"[KM:{self.killmail_id}] 检查条件: type={cond_type}, config={condition}")

        try:
            if cond_type == "entity":
                return await self._match_entity_condition(condition)
            elif cond_type == "label":
                return self._match_label_condition(condition)
            elif cond_type == "value":
                return self._match_value_condition(condition)
            else:
                logger.warning(f"Unknown condition type: {cond_type}")
                return False, ""
        except Exception as e:
            logger.error(f"条件匹配出错 (type={cond_type}): {e}")
            return False, ""

    async def _match_entity_condition(self, condition: dict) -> Tuple[bool, str]:
        """
        匹配实体条件 (character/corporation/alliance/ship/system/region/constellation)

        Args:
            condition: {
                "type": "entity",
                "entity_type": "character|corporation|alliance|ship|system|region|constellation",
                "entity_id": int,
                "entity_name": str,
                "role": "victim|final_blow|any_attacker" (如果是位置类型则不需要role)
            }

        Returns:
            (是否匹配, 匹配原因)
        """
        entity_type = condition.get("entity_type", "").lower()
        entity_id = condition.get("entity_id")
        entity_name = condition.get("entity_name", "")
        role = condition.get("role", "").lower()

        if not entity_type or not entity_id:
            return False, ""

        # 处理位置类型实体
        if entity_type == "system":
            if self.solar_system_id == entity_id:
                return True, f"星系: {entity_name}"
            return False, ""

        elif entity_type == "region":
            # 通过ESI获取星系信息来确定所属区域
            system_info = await esi_client.get_system_info(self.solar_system_id)
            if system_info.get("region_id") == entity_id:
                return True, f"区域: {entity_name}"
            return False, ""

        elif entity_type == "constellation":
            # 通过ESI获取星系信息来确定所属星座
            system_info = await esi_client.get_system_info(self.solar_system_id)
            if system_info.get("constellation_id") == entity_id:
                return True, f"星座: {entity_name}"
            return False, ""

        # 处理舰船类型实体
        elif entity_type == "ship":
            role_type = condition.get("ship_role", "victim_ship")
            if role_type == "victim_ship":
                if self.victim.get("ship_type_id") == entity_id:
                    return True, f"受害舰船: {entity_name}"
            elif role_type == "final_blow_ship":
                if self.final_blow.get("ship_type_id") == entity_id:
                    return True, f"最后一击舰船: {entity_name}"
            return False, ""

        # 处理实体角色 (character/corporation/alliance)
        else:
            if not role:
                return False, ""

            if role == "victim":
                if self._check_entity_match(self.victim, entity_type, entity_id):
                    return True, f"[{entity_type}]损失: {entity_name}"
                return False, ""

            elif role == "final_blow":
                if self._check_entity_match(self.final_blow, entity_type, entity_id):
                    return True, f"[{entity_type}]最后一击: {entity_name}"
                return False, ""

            elif role == "any_attacker":
                for attacker in self.attackers:
                    if self._check_entity_match(attacker, entity_type, entity_id):
                        return True, f"[{entity_type}]参与击杀: {entity_name}"
                return False, ""

        return False, ""

    @staticmethod
    def _check_entity_match(target: dict, entity_type: str, entity_id: int) -> bool:
        """
        检查实体是否匹配

        Args:
            target: 目标对象 (victim或attacker)
            entity_type: 实体类型
            entity_id: 实体ID

        Returns:
            是否匹配
        """
        if not target:
            return False

        entity_type = entity_type.lower()
        if entity_type == "character":
            return target.get("character_id") == entity_id
        elif entity_type == "corporation":
            return target.get("corporation_id") == entity_id
        elif entity_type == "alliance":
            return target.get("alliance_id") == entity_id

        return False

    def _match_label_condition(self, condition: dict) -> Tuple[bool, str]:
        """
        匹配标签条件 (基于killmail的zkb.labels数组)

        Args:
            condition: {
                "type": "label",
                "required_labels": [str] (可选，至少匹配一个),
                "excluded_labels": [str] (可选，排除任意一个都不匹配)
            }

        Returns:
            (是否匹配, 匹配原因)
        """
        required_labels = condition.get("required_labels", [])
        excluded_labels = condition.get("excluded_labels", [])

        if not required_labels and not excluded_labels:
            return True, ""

        # 检查排除标签 - 如果任意一个排除标签存在则不匹配
        for excluded in excluded_labels:
            if excluded in self.labels:
                return False, ""

        # 检查必需标签 - 如果指定了必需标签，需要至少匹配一个
        if required_labels:
            if not any(label in self.labels for label in required_labels):
                return False, ""

        # 构建匹配原因
        matched_labels = [label for label in required_labels if label in self.labels]
        reason = "标签: " + ", ".join(matched_labels) if matched_labels else "标签匹配"
        return True, reason

    def _match_value_condition(self, condition: dict) -> Tuple[bool, str]:
        """
        匹配价值条件

        Args:
            condition: {
                "type": "value",
                "min": float (可选),
                "max": float (可选)
            }

        Returns:
            (是否匹配, 匹配原因)
        """
        value_min = condition.get("min")
        value_max = condition.get("max")
        total_value = float(self.zkb.get("totalValue", 0))

        if value_min and total_value < value_min:
            return False, ""
        if value_max and total_value > value_max:
            return False, ""

        return True, f"价值: {total_value:,.0f} ISK"
