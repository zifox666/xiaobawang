"""
新版订阅管理器 - 支持灵活的条件组合

使用新的 KillmailSubscription 模型，支持复杂的条件逻辑
"""

import json
from typing import Any

from loguru import logger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.killmail import KillmailSubscription
from ..utils.common.cache import cache, cache_result


class KillmailSubscriptionManagerV2:
    """新版击毁邮件订阅管理器 - 支持灵活的条件组合"""

    def __init__(self, session: AsyncSession | None):
        """
        初始化订阅管理器

        Args:
            session: 数据库会话 (可以为None，用于获取模板等不需要数据库的操作)
        """
        self.session = session

    @cache_result(expire_time=5 * cache.TIME_MIN, prefix="sub_get_all_subscriptions")
    async def get_all_subscriptions(self) -> list[dict[str, Any]]:
        """获取所有启用的订阅"""
        if not self.session:
            return []

        try:
            query = select(KillmailSubscription).where(
                KillmailSubscription.is_enabled.is_(True)
            )
            result = await self.session.execute(query)
            subscriptions = result.scalars().all()

            subscription_data = []
            for sub in subscriptions:
                # 解析条件组
                try:
                    condition_groups = json.loads(sub.condition_groups)
                except json.JSONDecodeError:
                    logger.warning(f"订阅 {sub.id} 的条件组格式错误")
                    condition_groups = {}

                sub_dict = {
                    "id": sub.id,
                    "platform": sub.platform,
                    "bot_id": sub.bot_id,
                    "session_id": sub.session_id,
                    "session_type": sub.session_type,
                    "name": sub.name,
                    "description": sub.description,
                    "is_enabled": sub.is_enabled,
                    "min_value": sub.min_value,
                    "max_age_days": sub.max_age_days,
                    "condition_groups": condition_groups,
                    "created_at": sub.created_at,
                    "updated_at": sub.updated_at,
                }
                subscription_data.append(sub_dict)

            return subscription_data
        except Exception as e:
            logger.error(f"获取订阅列表失败: {e}")
            return []

    @cache_result(expire_time=5 * cache.TIME_MIN, prefix="sub_get_subscription_by_id")
    async def get_subscription_by_id(self, subscription_id: int) -> dict[str, Any] | None:
        """根据ID获取订阅"""
        if not self.session:
            return None

        try:
            query = select(KillmailSubscription).where(
                KillmailSubscription.id == subscription_id
            )
            result = await self.session.execute(query)
            sub = result.scalar_one_or_none()

            if not sub:
                return None

            # 解析条件组
            try:
                condition_groups = json.loads(sub.condition_groups)
            except json.JSONDecodeError:
                condition_groups = {}

            return {
                "id": sub.id,
                "platform": sub.platform,
                "bot_id": sub.bot_id,
                "session_id": sub.session_id,
                "session_type": sub.session_type,
                "name": sub.name,
                "description": sub.description,
                "is_enabled": sub.is_enabled,
                "min_value": sub.min_value,
                "max_age_days": sub.max_age_days,
                "condition_groups": condition_groups,
                "created_at": sub.created_at,
                "updated_at": sub.updated_at,
            }
        except Exception as e:
            logger.error(f"获取订阅失败: {e}")
            return None

    async def create_subscription(
        self,
        platform: str,
        bot_id: str,
        session_id: str,
        session_type: str,
        name: str,
        condition_config: dict | str,
        description: str | None = None,
        min_value: float = 20_000_000,
        max_age_days: int | None = None,
    ) -> int | None:
        """
        创建新的订阅

        Args:
            platform: 平台
            bot_id: 机器人ID
            session_id: 会话ID
            session_type: 会话类型
            name: 订阅名称
            condition_config: 条件配置 (dict 或 JSON 字符串)
            description: 订阅描述
            min_value: 最低价值 (必须大于20_000_000)
            max_age_days: 最大天数

        Returns:
            新创建的订阅ID，失败返回None
        """
        if not self.session:
            return None

        try:
            # 验证 min_value 必须大于 20_000_000
            if min_value <= 20_000_000:
                logger.error(f"min_value 必须大于 20_000_000，当前值: {min_value}")
                return None

            # 解析条件配置
            if isinstance(condition_config, str):
                condition_dict = json.loads(condition_config)
            else:
                condition_dict = condition_config

            # 验证条件配置
            validation_error = self._validate_condition_config(condition_dict, min_value)
            if validation_error:
                logger.error(validation_error)
                return None

            adjusted_min_value = self._adjust_min_value_for_single_value_condition(
                condition_dict, min_value
            )

            condition_json = json.dumps(condition_dict)

            new_sub = KillmailSubscription(
                platform=platform,
                bot_id=bot_id,
                session_id=session_id,
                session_type=session_type,
                name=name,
                description=description,
                min_value=adjusted_min_value,
                max_age_days=max_age_days,
                condition_groups=condition_json,
                is_enabled=True,
            )

            self.session.add(new_sub)
            await self.session.commit()
            await self.session.refresh(new_sub)

            logger.info(f"创建订阅成功: {new_sub.id} - {name}")
            return new_sub.id

        except json.JSONDecodeError as e:
            logger.error(f"条件配置 JSON 格式错误: {e}")
            return None
        except Exception as e:
            logger.error(f"创建订阅失败: {e}")
            await self.session.rollback()
            return None

    async def update_subscription(
        self,
        subscription_id: int,
        **kwargs
    ) -> bool:
        """
        更新订阅

        Args:
            subscription_id: 订阅ID
            **kwargs: 要更新的字段

        Returns:
            是否成功
        """
        if not self.session:
            return False

        try:
            query = select(KillmailSubscription).where(
                KillmailSubscription.id == subscription_id
            )
            result = await self.session.execute(query)
            sub = result.scalar_one_or_none()

            if not sub:
                logger.warning(f"订阅不存在: {subscription_id}")
                return False

            if "min_value" in kwargs:
                min_value = kwargs["min_value"]
                if min_value <= 20_000_000:
                    logger.error(f"min_value 必须大于 20_000_000，当前值: {min_value}")
                    return False

            # 验证条件配置
            if "condition_groups" in kwargs:
                condition_value = kwargs["condition_groups"]

                if isinstance(condition_value, str):
                    try:
                        condition_dict = json.loads(condition_value)
                    except json.JSONDecodeError as e:
                        logger.error(f"条件配置 JSON 格式错误: {e}")
                        return False
                else:
                    condition_dict = condition_value

                validation_error = self._validate_condition_config(condition_dict, sub.min_value)
                if validation_error:
                    logger.error(validation_error)
                    return False

                adjusted_min_value = self._adjust_min_value_for_single_value_condition(
                    condition_dict, sub.min_value
                )

                if isinstance(condition_value, dict):
                    condition_value = json.dumps(condition_value)
                kwargs["condition_groups"] = condition_value

                if adjusted_min_value != sub.min_value:
                    kwargs["min_value"] = adjusted_min_value

            # 更新字段
            for key, value in kwargs.items():
                if hasattr(sub, key):
                    setattr(sub, key, value)

            await self.session.commit()
            logger.info(f"更新订阅成功: {subscription_id}")
            return True

        except Exception as e:
            logger.error(f"更新订阅失败: {e}")
            await self.session.rollback()
            return False

    async def delete_subscription(self, subscription_id: int) -> bool:
        """
        删除订阅

        Args:
            subscription_id: 订阅ID

        Returns:
            是否成功
        """
        if not self.session:
            return False

        try:
            query = select(KillmailSubscription).where(
                KillmailSubscription.id == subscription_id
            )
            result = await self.session.execute(query)
            sub = result.scalar_one_or_none()

            if not sub:
                logger.warning(f"订阅不存在: {subscription_id}")
                return False

            await self.session.delete(sub)
            await self.session.commit()
            logger.info(f"删除订阅成功: {subscription_id}")
            return True

        except Exception as e:
            logger.error(f"删除订阅失败: {e}")
            await self.session.rollback()
            return False

    def _validate_condition_config(self, condition_config: dict, min_value: float) -> str | None:
        """
        验证条件配置的有效性

        Args:
            condition_config: 条件配置字典
            min_value: 最小值

        Returns:
            验证错误信息，验证通过返回None
        """
        # 检查是否包含条件
        if "conditions" not in condition_config:
            return "条件配置必须包含 'conditions' 字段"

        conditions = condition_config.get("conditions", [])
        if not conditions:
            return "条件列表不能为空"

        # 检查是否只有标签属性的条件
        has_non_tag_condition = False
        for condition in conditions:
            condition_type = condition.get("type")
            
            # 标签类型的条件
            if condition_type == "tag":
                # 标签不能单独作为条件，必须配合其他条件
                continue
            
            # 其他非标签条件
            if condition_type in ["value", "entity", "region", "ship"]:
                has_non_tag_condition = True
                break

        if not has_non_tag_condition:
            return "黑名单策略"

        return None

    def _adjust_min_value_for_single_value_condition(
        self, condition_config: dict, min_value: float
    ) -> float:
        """
        如果只有单个 value 类型条件，则调整 min_value

        Args:
            condition_config: 条件配置
            min_value: 传入的 min_value

        Returns:
            调整后的 min_value
        """
        conditions = condition_config.get("conditions", [])
        
        # 检查是否只有一个 value 类型条件
        value_conditions = [c for c in conditions if c.get("type") == "value"]
        non_value_conditions = [c for c in conditions if c.get("type") != "value"]
        
        # 如果只有一个 value 条件，且没有其他非标签的值条件
        if len(value_conditions) == 1 and not any(c.get("type") != "tag" for c in non_value_conditions):
            value_condition = value_conditions[0]
            
            # 如果只有 min 字段，没有 max 字段
            if "min" in value_condition and "max" not in value_condition:
                # 设置为 15_000_000_000
                adjusted_value = 15_000_000_000
                if adjusted_value > min_value:
                    logger.info(
                        f"只有 value 的 min 条件，调整 min_value 从 {min_value} 到 {adjusted_value}"
                    )
                    return adjusted_value
        
        return min_value
    
    @classmethod
    def get_subscription_template(cls, template_name: str) -> dict | None:
        """
        获取预定义的订阅模板

        Args:
            template_name: 模板名称

        Returns:
            模板配置，不存在返回None
        """
        templates = {
            "high_value": {
                "name": "高价值击杀",
                "description": "订阅价值超过25b的击杀",
                "config": {
                    "logic": "AND",
                    "conditions": [
                        {
                            "type": "value",
                            "min": 25_000_000_000
                        }
                    ]
                }
            },
            "alliance_loss": {
                "name": "角色/军团/联盟损失",
                "description": "订阅特定的损失",
                "config": {
                    "logic": "AND",
                    "conditions": [
                        {
                            "type": "entity",
                            "entity_type": "alliance",
                            "entity_id": 0,
                            "entity_name": "",
                            "role": "victim"
                        }
                    ]
                }
            },
        }

        return templates.get(template_name)
