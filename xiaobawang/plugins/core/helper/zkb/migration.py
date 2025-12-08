"""
KM订阅数据迁移脚本

将现有的 KillmailHighValueSubscription 和 KillmailConditionSubscription
迁移到新的 KillmailSubscription 统一模型
"""

import json
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xiaobawang.plugins.core.db.models.killmail import (
    KillmailSubscription,
    KillmailHighValueSubscription,
    KillmailConditionSubscription,
)


async def migrate_high_value_subscriptions(session: AsyncSession) -> tuple[int, int]:
    """
    迁移高价值订阅

    Args:
        session: 数据库会话

    Returns:
        (成功数, 失败数)
    """
    success_count = 0
    fail_count = 0

    try:
        # 查询所有高价值订阅
        query = select(KillmailHighValueSubscription)
        result = await session.execute(query)
        old_subs = result.scalars().all()

        logger.info(f"开始迁移 {len(old_subs)} 个高价值订阅...")

        for old_sub in old_subs:
            try:
                # 创建新订阅
                new_sub = KillmailSubscription(
                    platform=old_sub.platform,
                    bot_id=old_sub.bot_id,
                    session_id=old_sub.session_id,
                    session_type=old_sub.session_type,
                    name="高价值击杀",
                    description="从旧系统迁移的高价值订阅",
                    is_enabled=old_sub.is_enabled,
                    min_value=old_sub.min_value,
                    condition_groups=json.dumps({
                        "logic": "AND",
                        "conditions": []  # 无额外条件,仅价值过滤
                    }),
                    created_at=old_sub.created_at,
                    updated_at=old_sub.updated_at,
                )

                session.add(new_sub)
                success_count += 1
                logger.debug(f"✓ 迁移高价值订阅 {old_sub.id}")

            except Exception as e:
                fail_count += 1
                logger.error(f"✗ 迁移高价值订阅 {old_sub.id} 失败: {e}")

        # 批量提交
        await session.commit()
        logger.info(f"高价值订阅迁移完成: {success_count} 成功, {fail_count} 失败")

    except Exception as e:
        logger.error(f"高价值订阅迁移过程出错: {e}")
        await session.rollback()

    return success_count, fail_count


async def migrate_condition_subscriptions(session: AsyncSession) -> tuple[int, int]:
    """
    迁移条件订阅

    Args:
        session: 数据库会话

    Returns:
        (成功数, 失败数)
    """
    success_count = 0
    fail_count = 0

    try:
        # 查询所有条件订阅
        query = select(KillmailConditionSubscription)
        result = await session.execute(query)
        old_subs = result.scalars().all()

        logger.info(f"开始迁移 {len(old_subs)} 个条件订阅...")

        for old_sub in old_subs:
            try:
                # 确定角色
                if old_sub.is_victim and not old_sub.is_final_blow:
                    role = "victim"
                elif old_sub.is_final_blow and not old_sub.is_victim:
                    role = "final_blow"
                elif old_sub.is_victim and old_sub.is_final_blow:
                    # 两者都选则为any_attacker
                    role = "any_attacker"
                else:
                    # 默认为any_attacker
                    role = "any_attacker"

                # 根据目标类型构造条件
                condition = _build_condition_from_old_sub(old_sub, role)
                if not condition:
                    logger.warning(f"⚠ 无法转换订阅 {old_sub.id},跳过")
                    fail_count += 1
                    continue

                # 创建新订阅
                new_sub = KillmailSubscription(
                    platform=old_sub.platform,
                    bot_id=old_sub.bot_id,
                    session_id=old_sub.session_id,
                    session_type=old_sub.session_type,
                    name=f"{old_sub.target_name}订阅",
                    description=f"从旧系统迁移的条件订阅 ({old_sub.target_type})",
                    is_enabled=old_sub.is_enabled,
                    min_value=old_sub.min_value,
                    condition_groups=json.dumps({
                        "logic": "AND",
                        "conditions": [condition]
                    }),
                    created_at=old_sub.created_at,
                    updated_at=old_sub.updated_at,
                )

                session.add(new_sub)
                success_count += 1
                logger.debug(f"✓ 迁移条件订阅 {old_sub.id} ({old_sub.target_type})")

            except Exception as e:
                fail_count += 1
                logger.error(f"✗ 迁移条件订阅 {old_sub.id} 失败: {e}")

        # 批量提交
        await session.commit()
        logger.info(f"条件订阅迁移完成: {success_count} 成功, {fail_count} 失败")

    except Exception as e:
        logger.error(f"条件订阅迁移过程出错: {e}")
        await session.rollback()

    return success_count, fail_count


def _build_condition_from_old_sub(old_sub: Any, role: str) -> dict | None:
    """
    从旧订阅构建条件

    Args:
        old_sub: 旧订阅对象
        role: 角色 (victim/final_blow/any_attacker)

    Returns:
        条件字典或None
    """
    target_type = old_sub.target_type.lower()

    # 处理实体条件
    if target_type in ("character", "corporation", "alliance"):
        return {
            "type": "entity",
            "entity_type": target_type,
            "entity_id": old_sub.target_id,
            "entity_name": old_sub.target_name,
            "role": role
        }

    # 处理faction
    elif target_type == "faction":
        return {
            "type": "entity",
            "entity_type": "faction",
            "entity_id": old_sub.target_id,
            "entity_name": old_sub.target_name,
            "role": role
        }

    # 处理系统位置
    elif target_type == "system":
        return {
            "type": "location",
            "location_type": "system",
            "location_id": old_sub.target_id,
            "location_name": old_sub.target_name
        }

    # 处理物品/舰船
    elif target_type == "inventory_type":
        return {
            "type": "ship",
            "ship_type_id": old_sub.target_id,
            "ship_name": old_sub.target_name,
            "ship_role": f"{role}_ship"
        }

    # 处理区域
    elif target_type == "region":
        return {
            "type": "location",
            "location_type": "region",
            "location_id": old_sub.target_id,
            "location_name": old_sub.target_name
        }

    else:
        logger.warning(f"未知的目标类型: {target_type}")
        return None


async def migrate_all_subscriptions(session: AsyncSession) -> dict[str, Any]:
    """
    执行完整的迁移

    Args:
        session: 数据库会话

    Returns:
        迁移结果统计
    """
    logger.info("=" * 50)
    logger.info("开始KM订阅全量迁移...")
    logger.info("=" * 50)

    result = {
        "start_time": datetime.now(),
        "high_value": {"success": 0, "fail": 0},
        "condition": {"success": 0, "fail": 0},
        "total_success": 0,
        "total_fail": 0,
    }

    try:
        # 迁移高价值订阅
        hv_success, hv_fail = await migrate_high_value_subscriptions(session)
        result["high_value"]["success"] = hv_success
        result["high_value"]["fail"] = hv_fail

        # 迁移条件订阅
        cond_success, cond_fail = await migrate_condition_subscriptions(session)
        result["condition"]["success"] = cond_success
        result["condition"]["fail"] = cond_fail

        # 汇总
        result["total_success"] = hv_success + cond_success
        result["total_fail"] = hv_fail + cond_fail
        result["end_time"] = datetime.now()

        logger.info("=" * 50)
        logger.info("迁移完成!")
        logger.info(f"高价值订阅: {hv_success} 成功, {hv_fail} 失败")
        logger.info(f"条件订阅: {cond_success} 成功, {cond_fail} 失败")
        logger.info(f"总计: {result['total_success']} 成功, {result['total_fail']} 失败")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"迁移过程出错: {e}")
        result["error"] = str(e)

    return result
