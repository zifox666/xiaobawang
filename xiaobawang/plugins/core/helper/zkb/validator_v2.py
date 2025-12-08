from datetime import datetime, timezone
from typing import Any

from nonebot import logger

from .condition_matcher import ConditionMatcher
from ..subscription_v2 import KillmailSubscriptionManagerV2


class KillmailValidatorV2:
    """新的Killmail验证器 - 支持灵活的条件组合"""

    def __init__(self, subscription_manager: KillmailSubscriptionManagerV2):
        """
        初始化验证器

        Args:
            subscription_manager: 新的订阅管理器
        """
        self.subscription_manager = subscription_manager

    async def validate_and_match(self, data: dict[str, Any]) -> dict[tuple, list[str]] | None:
        """
        验证killmail并匹配新式订阅

        Args:
            data: zkillboard推送的killmail数据

        Returns:
            匹配的会话信息字典 {(platform, bot_id, session_id, session_type, total_value): [reasons]}
            如果不符合要求则返回None
        """
        try:
            # 检查价值
            if not self._check_killmail_value(data):
                return None

            # 获取所有新式订阅
            all_subscriptions = await self.subscription_manager.get_all_subscriptions()
            if not all_subscriptions:
                logger.debug("没有可用的订阅")
                return None

            # 检查时间
            if not self._check_killmail_time(data):
                logger.debug("超过限制时间")
                return None

            # 生成标签
            labels = data.get("zkb", {}).get("labels", [])

            # 创建匹配器
            matcher = ConditionMatcher(data)

            # 匹配订阅 - 批量并发处理
            matched_sessions = {}
            # 过滤启用的订阅
            enabled_subs = [sub for sub in all_subscriptions if sub["is_enabled"]]
            
            # 分批处理,每批100个
            batch_size = 100
            total_value = float(data.get("zkb", {}).get("totalValue", 0))
            
            for i in range(0, len(enabled_subs), batch_size):
                batch = enabled_subs[i:i + batch_size]
                # 并发匹配当前批次
                import asyncio
                tasks = [matcher.match_subscription(sub) for sub in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 处理匹配结果
                for sub, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.error(f"订阅 {sub['id']} ({sub['name']}) 匹配出错: {result}")
                        continue
                    
                    matched, reasons = result
                    if matched:
                        session_key = (
                            sub["platform"],
                            sub["bot_id"],
                            sub["session_id"],
                            sub["session_type"],
                            total_value
                        )
                        # 添加订阅名称到原因列表
                        full_reasons = [f"[{sub['name']}]"] + reasons
                        matched_sessions.setdefault(session_key, []).extend(full_reasons)
                        logger.debug(f"订阅 {sub['id']} ({sub['name']}) 匹配成功")

            return matched_sessions if matched_sessions else None

        except Exception as e:
            logger.error(f"验证和匹配过程出错: {e}")
            return None

    def _check_killmail_value(self, data: dict) -> bool:
        """检查killmail价值"""
        try:
            total_value = float(data.get("zkb", {}).get("totalValue", 0))
            if total_value < 1_000_000:
                logger.debug(f"价值过低: {total_value:,.0f} ISK")
                return False
            return True
        except Exception as e:
            logger.error(f"价值检查出错: {e}")
            return False

    def _check_killmail_time(self, data: dict) -> bool:
        """检查killmail时间 - 只处理最近10天内的"""
        try:
            killmail_time = data.get("killmail_time")
            if not killmail_time:
                return True

            # 解析时间
            kill_dt = datetime.strptime(killmail_time, "%Y-%m-%dT%H:%M:%SZ")
            kill_dt = kill_dt.replace(tzinfo=timezone.utc)

            # 计算时间差
            now = datetime.now(timezone.utc)
            age_days = (now - kill_dt).days

            if age_days > 10:
                logger.debug(f"killmail时间过久: {age_days} 天前")
                return False

            return True
        except Exception as e:
            logger.error(f"时间检查出错: {e}")
            return True


# ============================================
# 与旧系统兼容的验证器 (保留用于过渡期)
# ============================================


class KillmailValidatorLegacy:
    """旧的Killmail验证器 - 用于过渡期"""

    def __init__(self, subscription_manager: KillmailSubscriptionManagerV2):
        """
        初始化验证器

        Args:
            subscription_manager: 支持新旧两种订阅的管理器
        """
        self.subscription_manager = subscription_manager
        self.v2_validator = KillmailValidatorV2(subscription_manager)

    async def validate_and_match(self, data: dict[str, Any]) -> dict[tuple, list[str]] | None:
        """
        验证killmail并匹配订阅 (兼容旧系统)

        同时处理新式订阅和旧式订阅
        """
        # 先尝试使用新的验证器
        result = await self.v2_validator.validate_and_match(data)
        if result:
            return result

        # 如果新式订阅没有匹配,尝试旧式订阅
        # (保留以便过渡期使用,之后可以删除)
        return None
