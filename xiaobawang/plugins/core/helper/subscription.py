from typing import Any, Literal

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.killmail import KillmailConditionSubscription, KillmailHighValueSubscription
from ..utils.common.cache import cache, cache_result


class KillmailSubscriptionManager:
    """击毁邮件订阅管理器"""

    def __init__(self, session: AsyncSession):
        """
        初始化订阅管理器

        Args:
            session: 数据库会话
        """
        self.session = session

    @cache_result(expire_time=1 * cache.TIME_HOUR, prefix="km_subscriptions")
    async def get_high_value_subscriptions(self) -> list[dict[str, Any]]:
        """获取所有高价值击杀订阅"""
        try:
            query = select(KillmailHighValueSubscription).where(KillmailHighValueSubscription.is_enabled.is_(True))
            result = await self.session.execute(query)
            subscriptions = result.scalars().all()

            subscription_data = []
            for sub in subscriptions:
                sub_dict = {
                    "id": sub.id,
                    "platform": sub.platform,
                    "bot_id": sub.bot_id,
                    "session_id": sub.session_id,
                    "session_type": sub.session_type,
                    "is_enabled": sub.is_enabled,
                    "min_value": sub.min_value,
                    "created_at": sub.created_at,
                    "updated_at": sub.updated_at,
                }
                subscription_data.append(sub_dict)

            return subscription_data
        except Exception as e:
            logger.error(f"获取高价值击杀订阅信息失败: {e}")
            return []

    @cache_result(expire_time=1 * cache.TIME_HOUR, prefix="km_condition_subs")
    async def get_condition_subscriptions(self) -> list[dict[str, Any]]:
        """获取所有条件订阅"""
        try:
            query = select(KillmailConditionSubscription).where(KillmailConditionSubscription.is_enabled.is_(True))
            result = await self.session.execute(query)
            subscriptions = result.scalars().all()

            subscription_data = []
            for sub in subscriptions:
                sub_dict = {
                    "id": sub.id,
                    "platform": sub.platform,
                    "bot_id": sub.bot_id,
                    "session_id": sub.session_id,
                    "session_type": sub.session_type,
                    "target_type": sub.target_type,
                    "target_id": sub.target_id,
                    "target_name": sub.target_name,
                    "is_enabled": sub.is_enabled,
                    "is_victim": sub.is_victim,
                    "is_final_blow": sub.is_final_blow,
                    "min_value": sub.min_value,
                    "created_at": sub.created_at,
                    "updated_at": sub.updated_at,
                }
                subscription_data.append(sub_dict)

            return subscription_data
        except Exception as e:
            logger.error(f"获取条件订阅信息失败: {e}")
            return []

    async def add_subscription(
        self,
        platform: str,
        bot_id: str,
        session_id: str,
        session_type: str,
        sub_type: Literal["high_value", "condition"],
        min_value: float,
        target_type: str | None = None,
        target_id: int | None = None,
        target_name: str | None = None,
        is_victim: bool = True,
        is_final_blow: bool = True,
    ) -> bool:
        """
        添加订阅（高价值或条件）

        Args:
            platform: 平台
            bot_id: 机器人ID
            session_id: 会话ID
            session_type: 会话类型
            sub_type: 订阅类型 "high_value" 或 "condition"
            min_value: 最低价值
            target_type: 目标类型（条件订阅必填）
            target_id: 目标ID（条件订阅必填）
            target_name: 目标名称（条件订阅必填）
            is_victim: 是否为受害者（条件订阅）
            is_final_blow: 是否为最后一击（条件订阅）

        Returns:
            添加是否成功
        """
        if sub_type == "high_value":
            return await self._add_high_value_subscription(platform, bot_id, session_id, session_type, min_value)
        elif sub_type == "condition":
            if target_type is None or target_id is None or target_name is None:
                logger.error("添加条件订阅失败: 缺少必要参数")
                return False

            return await self._add_condition_subscription(
                platform,
                bot_id,
                session_id,
                session_type,
                target_type,
                target_id,
                target_name,
                is_victim,
                is_final_blow,
                min_value,
            )
        else:
            logger.error(f"无效的订阅类型: {sub_type}")
            return False

    async def remove_subscription(self, subscription_id: int, sub_type: Literal["high_value", "condition"]) -> bool:
        """
        删除订阅

        Args:
            subscription_id: 订阅ID
            sub_type: 订阅类型 "high_value" 或 "condition"

        Returns:
            删除是否成功
        """
        if sub_type == "high_value":
            return await self._delete_high_value_subscription(subscription_id)
        elif sub_type == "condition":
            return await self._delete_condition_subscription(subscription_id)
        else:
            logger.error(f"无效的订阅类型: {sub_type}")
            return False

    async def disable_subscription(self, subscription_id: int, sub_type: Literal["high_value", "condition"]) -> bool:
        """
        禁用订阅

        Args:
            subscription_id: 订阅ID
            sub_type: 订阅类型 "high_value" 或 "condition"

        Returns:
            禁用是否成功
        """
        if sub_type == "high_value":
            return await self._disable_high_value_subscription(subscription_id)
        elif sub_type == "condition":
            return await self._disable_condition_subscription(subscription_id)
        else:
            logger.error(f"无效的订阅类型: {sub_type}")
            return False

    async def get_session_subscriptions(
        self, platform: str, bot_id: str, session_id: str, session_type: str
    ) -> dict[str, Any]:
        """获取特定会话的所有订阅信息"""
        try:
            # 查询高价值订阅
            hv_query = select(KillmailHighValueSubscription).where(
                and_(
                    KillmailHighValueSubscription.platform == platform,
                    KillmailHighValueSubscription.bot_id == bot_id,
                    KillmailHighValueSubscription.session_id == session_id,
                    KillmailHighValueSubscription.session_type == session_type,
                    KillmailHighValueSubscription.is_enabled.is_(True),
                )
            )
            hv_result = await self.session.execute(hv_query)
            hv_subscription = hv_result.scalar_one_or_none()

            # 查询条件订阅
            cond_query = select(KillmailConditionSubscription).where(
                and_(
                    KillmailConditionSubscription.platform == platform,
                    KillmailConditionSubscription.bot_id == bot_id,
                    KillmailConditionSubscription.session_id == session_id,
                    KillmailConditionSubscription.session_type == session_type,
                    KillmailConditionSubscription.is_enabled.is_(True),
                )
            )
            cond_result = await self.session.execute(cond_query)
            cond_subscriptions = cond_result.scalars().all()

            result = {"high_value_subscription": None, "condition_subscriptions": []}

            if hv_subscription:
                result["high_value_subscription"] = {"id": hv_subscription.id, "min_value": hv_subscription.min_value}

            for cond in cond_subscriptions:
                result["condition_subscriptions"].append(
                    {
                        "id": cond.id,
                        "target_type": cond.target_type,
                        "target_id": cond.target_id,
                        "target_name": cond.target_name,
                        "is_victim": cond.is_victim,
                        "is_final_blow": cond.is_final_blow,
                        "min_value": cond.min_value,
                    }
                )

            return result
        except Exception as e:
            logger.error(f"获取会话订阅信息失败: {e}")
            return {"high_value_subscription": None, "condition_subscriptions": []}

    @classmethod
    async def invalidate_cache(cls):
        """使缓存失效"""
        from ..utils.common.cache import cache

        redis_cache = cache._instance
        if redis_cache:
            await redis_cache.delete("km_subscriptions")
            await redis_cache.delete("km_condition_subs")

    async def _add_high_value_subscription(
        self, platform: str, bot_id: str, session_id: str, session_type: str, min_value: float
    ) -> bool:
        """添加高价值击杀订阅"""
        try:
            query = select(KillmailHighValueSubscription).where(
                and_(
                    KillmailHighValueSubscription.platform == platform,
                    KillmailHighValueSubscription.bot_id == bot_id,
                    KillmailHighValueSubscription.session_id == session_id,
                    KillmailHighValueSubscription.session_type == session_type,
                )
            )
            result = await self.session.execute(query)
            subscription = result.scalar_one_or_none()

            if subscription:
                subscription.is_enabled = True
                subscription.min_value = min_value
            else:
                subscription = KillmailHighValueSubscription(
                    platform=platform,
                    bot_id=bot_id,
                    session_id=session_id,
                    session_type=session_type,
                    is_enabled=True,
                    min_value=min_value,
                )
                self.session.add(subscription)

            await self.session.commit()
            await self.invalidate_cache()
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"添加高价值击杀订阅失败: {e}")
            return False

    async def _add_condition_subscription(
        self,
        platform: str,
        bot_id: str,
        session_id: str,
        session_type: str,
        target_type: str,
        target_id: int,
        target_name: str,
        is_victim: bool = True,
        is_final_blow: bool = True,
        min_value: float = 100_000_000,
    ) -> bool:
        """添加条件订阅"""
        try:
            query = select(KillmailConditionSubscription).where(
                and_(
                    KillmailConditionSubscription.platform == platform,
                    KillmailConditionSubscription.bot_id == bot_id,
                    KillmailConditionSubscription.session_id == session_id,
                    KillmailConditionSubscription.session_type == session_type,
                    KillmailConditionSubscription.target_type == target_type,
                    KillmailConditionSubscription.target_id == target_id,
                    KillmailConditionSubscription.is_victim == is_victim,
                    KillmailConditionSubscription.is_final_blow == is_final_blow,
                )
            )
            result = await self.session.execute(query)
            condition = result.scalar_one_or_none()

            if condition:
                condition.is_enabled = True
                condition.target_name = target_name
                condition.min_value = min_value
            else:
                condition = KillmailConditionSubscription(
                    platform=platform,
                    bot_id=bot_id,
                    session_id=session_id,
                    session_type=session_type,
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    is_enabled=True,
                    is_victim=is_victim,
                    is_final_blow=is_final_blow,
                    min_value=min_value,
                )
                self.session.add(condition)

            await self.session.commit()
            await self.invalidate_cache()
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"添加条件订阅失败: {e}")
            return False

    async def _delete_high_value_subscription(self, subscription_id: int) -> bool:
        """删除高价值击杀订阅"""
        try:
            subscription = await self.session.get(KillmailHighValueSubscription, subscription_id)
            if subscription:
                await self.session.delete(subscription)
                await self.session.commit()
                await self.invalidate_cache()
                return True
            return False
        except Exception as e:
            await self.session.rollback()
            logger.error(f"删除高价值击杀订阅失败: {e}")
            return False

    async def _delete_condition_subscription(self, condition_id: int) -> bool:
        """删除条件订阅"""
        try:
            condition = await self.session.get(KillmailConditionSubscription, condition_id)
            if condition:
                await self.session.delete(condition)
                await self.session.commit()
                await self.invalidate_cache()
                return True
            return False
        except Exception as e:
            await self.session.rollback()
            logger.error(f"删除条件订阅失败: {e}")
            return False

    async def _disable_high_value_subscription(self, subscription_id: int) -> bool:
        """禁用高价值击杀订阅（设置为不活跃）"""
        try:
            subscription = await self.session.get(KillmailHighValueSubscription, subscription_id)
            if subscription:
                subscription.is_enabled = False
                await self.session.commit()
                await self.invalidate_cache()
                return True
            return False
        except Exception as e:
            await self.session.rollback()
            logger.error(f"禁用高价值击杀订阅失败: {e}")
            return False

    async def _disable_condition_subscription(self, condition_id: int) -> bool:
        """禁用条件订阅（设置为不活跃）"""
        try:
            condition = await self.session.get(KillmailConditionSubscription, condition_id)
            if condition:
                condition.is_enabled = False
                await self.session.commit()
                await self.invalidate_cache()
                return True
            return False
        except Exception as e:
            await self.session.rollback()
            logger.error(f"禁用条件订阅失败: {e}")
            return False
