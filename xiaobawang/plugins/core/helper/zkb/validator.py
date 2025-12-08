"""
Killmail 验证和订阅匹配模块
负责检查 killmail 是否符合订阅条件
"""
from datetime import datetime, timezone
from typing import Any

from nonebot import logger

from ...helper.subscription import KillmailSubscriptionManager


class KillmailValidator:
    """Killmail 验证器，负责检查 killmail 是否符合订阅要求"""

    def __init__(self, subscription_manager: KillmailSubscriptionManager):
        self.subscription_manager = subscription_manager

    async def validate_and_match(self, data: dict[str, Any]) -> dict[tuple, list[str]] | None:
        """
        验证 killmail 并匹配订阅条件
        
        Args:
            data: zkillboard 推送的 killmail 数据
            
        Returns:
            匹配的会话信息字典 {(platform, bot_id, session_id, session_type, total_value): [reasons]}
            如果不符合要求则返回 None
        """
        # 检查价值
        if not await self._check_killmail_value(data):
            return None

        # 获取订阅
        high_value_subs, condition_subs = await self._get_active_subscriptions()
        if not high_value_subs and not condition_subs:
            return None

        # 检查时间
        if not await self._check_killmail_time(data):
            logger.debug("超过限制时间")
            return None

        # 提取信息
        victim_info, attacker_info = self._extract_kill_info(data)

        # 匹配订阅
        matched_sessions = await self._match_subscriptions(
            data, victim_info, attacker_info, high_value_subs, condition_subs
        )

        return matched_sessions if matched_sessions else None

    @classmethod
    async def _check_killmail_value(cls, data: dict[str, Any]) -> bool:
        """检查击杀价值是否符合最低要求"""
        zkb_data = data.get("zkb", {})
        total_value = float(zkb_data.get("totalValue", 0))

        min_subscription_value = 1_000_000
        if total_value < min_subscription_value:
            return False
        return True

    @classmethod
    async def _check_killmail_time(cls, data: dict[str, Any]) -> bool:
        """检查击杀时间是否在10天以内"""
        killmail_time_str = data.get("killmail_time", "")
        if not killmail_time_str:
            logger.warning("收到无效的 killmail 数据: 缺少时间信息")
            return False

        try:
            killmail_time = datetime.fromisoformat(killmail_time_str.replace("Z", "+00:00"))
            current_time = datetime.now(timezone.utc)
            time_diff = current_time - killmail_time

            if time_diff.days > 10:
                logger.debug(f"击杀时间超过10天，忽略 killmail: {data.get('killmail_id')}, 时间: {killmail_time_str}")
                return False
            return True
        except Exception as e:
            logger.warning(f"解析击杀时间失败: {e}, 时间字符串: {killmail_time_str}")
            return False

    async def _get_active_subscriptions(self):
        """获取活跃的订阅"""
        high_value_subs = await self.subscription_manager.get_high_value_subscriptions()
        condition_subs = await self.subscription_manager.get_condition_subscriptions()
        return high_value_subs, condition_subs

    def _extract_kill_info(self, data: dict[str, Any]):
        """提取击杀和受害者信息"""
        victim = data.get("victim", {})
        victim_info = {
            "character_id": self._ensure_int(victim.get("character_id", 0)),
            "corporation_id": self._ensure_int(victim.get("corporation_id", 0)),
            "alliance_id": self._ensure_int(victim.get("alliance_id", 0)),
            "ship_type_id": self._ensure_int(victim.get("ship_type_id", 0)),
        }

        solar_system_id = self._ensure_int(data.get("solar_system_id", 0))
        victim_info["solar_system_id"] = solar_system_id

        attackers = data.get("attackers", [])
        final_blow_attacker = next((a for a in attackers if a.get("final_blow")), attackers[0] if attackers else {})

        attacker_info = {
            "final_blow_character_id": self._ensure_int(final_blow_attacker.get("character_id", 0)),
            "final_blow_corporation_id": self._ensure_int(final_blow_attacker.get("corporation_id", 0)),
            "final_blow_alliance_id": self._ensure_int(final_blow_attacker.get("alliance_id", 0)),
            "final_blow_ship_type_id": self._ensure_int(final_blow_attacker.get("ship_type_id", 0)),
            "attackers": attackers,
        }

        return victim_info, attacker_info

    async def _match_subscriptions(
        self,
        data: dict[str, Any],
        victim_info: dict[str, Any],
        attacker_info: dict[str, Any],
        high_value_subs: list[dict],
        condition_subs: list[dict],
    ) -> dict[tuple, list[str]]:
        """匹配订阅条件并返回匹配的会话信息"""
        matched_sessions = {}  # {(platform, bot_id, session_id, session_type, total_value): [reasons]}

        # high value subscriptions
        total_value = float(data.get("zkb", {}).get("totalValue", 0))
        for sub in high_value_subs:
            if total_value >= sub["min_value"]:
                session_key = (sub["platform"], sub["bot_id"], sub["session_id"], sub["session_type"], total_value)
                reason = "高价值击杀"
                matched_sessions.setdefault(session_key, []).append(reason)

        # 预处理参与攻击信息
        attacker_character_ids = set()
        attacker_corporation_ids = set()
        attacker_alliance_ids = set()

        need_all_attackers = any(not sub["is_victim"] and not sub["is_final_blow"] for sub in condition_subs)

        if need_all_attackers:
            for attacker in attacker_info["attackers"]:
                char_id = self._ensure_int(attacker.get("character_id", 0))
                if char_id:
                    attacker_character_ids.add(char_id)

                corp_id = self._ensure_int(attacker.get("corporation_id", 0))
                if corp_id:
                    attacker_corporation_ids.add(corp_id)

                alliance_id = self._ensure_int(attacker.get("alliance_id", 0))
                if alliance_id:
                    attacker_alliance_ids.add(alliance_id)

        # condition subscriptions
        for sub in condition_subs:
            if total_value < sub["min_value"]:
                continue

            target_id = self._ensure_int(sub["target_id"])
            target_type = sub["target_type"]
            matched = False
            reason = ""
            is_victim = sub.get("is_victim", False)

            if is_victim:
                matched, reason = self._match_victim_condition(sub, target_id, target_type, victim_info)

            if not is_victim:
                if sub["is_final_blow"]:
                    matched, reason = self._match_final_blow_condition(sub, target_id, target_type, attacker_info)
                else:
                    matched, reason = self._match_attacker_condition(
                        sub,
                        target_id,
                        target_type,
                        attacker_character_ids,
                        attacker_corporation_ids,
                        attacker_alliance_ids,
                    )

            if matched:
                session_key = (sub["platform"], sub["bot_id"], sub["session_id"], sub["session_type"], total_value)
                logger.debug(f"符合条件\n{session_key}\n{reason}")
                matched_sessions.setdefault(session_key, []).append(reason)

        return matched_sessions

    @classmethod
    def _match_victim_condition(cls, sub, target_id, target_type, victim_info):
        """匹配受害者条件"""
        if target_type == "character" and victim_info["character_id"] == target_id:
            return True, f"[Char]损失: {sub['target_name']}"
        elif target_type == "corporation" and victim_info["corporation_id"] == target_id:
            return True, f"[Corp]损失: {sub['target_name']}"
        elif target_type == "alliance" and victim_info["alliance_id"] == target_id:
            return True, f"[Alliance]损失: {sub['target_name']}"
        elif target_type == "system" and victim_info["solar_system_id"] == target_id:
            return True, f"[System]损失: {sub['target_name']}"
        elif target_type == "inventory_type" and victim_info["ship_type_id"] == target_id:
            return True, f"[Ship]损失: {sub['target_name']}"
        return False, ""

    @classmethod
    def _match_final_blow_condition(cls, sub, target_id, target_type, attacker_info):
        """匹配最后一击条件"""
        if target_type == "character" and attacker_info["final_blow_character_id"] == target_id:
            return True, f"[Char]最后一击: {sub['target_name']}"
        elif target_type == "corporation" and attacker_info["final_blow_corporation_id"] == target_id:
            return True, f"[Corp]最后一击: {sub['target_name']}"
        elif target_type == "alliance" and attacker_info["final_blow_alliance_id"] == target_id:
            return True, f"[Alliance]最后一击: {sub['target_name']}"
        elif target_type == "ship" and attacker_info["final_blow_ship_type_id"] == target_id:
            return True, f"[Ship]最后一击: {sub['target_name']}"
        return False, ""

    @classmethod
    def _match_attacker_condition(cls, sub, target_id, target_type, character_ids, corporation_ids, alliance_ids):
        """匹配参与攻击者条件"""
        if target_type == "character" and target_id in character_ids:
            return True, f"[Char]参与击杀: {sub['target_name']}"
        elif target_type == "corporation" and target_id in corporation_ids:
            return True, f"[Corp]参与击杀: {sub['target_name']}"
        elif target_type == "alliance" and target_id in alliance_ids:
            return True, f"[Alliance]参与击杀: {sub['target_name']}"
        return False, ""

    @classmethod
    def _ensure_int(cls, value) -> int | None:
        """确保值为整数类型"""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
