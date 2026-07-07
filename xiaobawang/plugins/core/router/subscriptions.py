"""
聚合订阅网关 —— 统一管理三种订阅（killmail/structure/eve_status）

端点 (prefix=/api/subscriptions):
  GET /          聚合订阅列表（查注册表，按 session_key 隔离）
  GET /stats     聚合统计（各类型计数 + 余额 + 今日消耗）

Phase 2 骨架：基于 subscription 注册表聚合。注册表在订阅创建时由
BillingGateway.register_subscription 写入；存量订阅由 Phase 1 回填脚本补齐。
killmail Tab 仍直接用 /sub 原接口，本网关为账户余额 Tab 与 Phase 3 统一管理准备。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import and_, func, select

from ..db.models.credit import CreditTransaction
from ..db.models.subscription import Subscription
from ..helper.auth import get_current_user
from ..helper.billing import billing, key_from_current_user, short_key

router = APIRouter()


@router.get("", summary="聚合订阅列表")
async def list_subscriptions(
    sub_type: str | None = Query(None, description="按类型过滤 killmail/structure/eve_status"),
    is_enabled: bool | None = Query(None, description="启用状态过滤"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    session_key = key_from_current_user(current_user)

    query = select(Subscription).where(Subscription.session_key == session_key)
    if sub_type:
        query = query.where(Subscription.sub_type == sub_type)
    if is_enabled is not None:
        query = query.where(Subscription.is_enabled == is_enabled)
    query = query.order_by(Subscription.created_at.desc())

    rows = (await session.execute(query)).scalars().all()

    return {
        "success": True,
        "data": {
            "session_key": short_key(session_key),
            "total": len(rows),
            "items": [
                {
                    "id": r.id,
                    "sub_type": r.sub_type,
                    "source_table": r.source_table,
                    "source_id": r.source_id,
                    "is_enabled": r.is_enabled,
                    "unit_price": r.unit_price,
                    "complexity_factor": r.complexity_factor,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        },
    }


@router.get("/stats", summary="聚合统计")
async def aggregate_stats(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """各类型订阅计数 + 余额 + 今日消费"""
    session_key = key_from_current_user(current_user)

    # 各类型计数
    count_query = (
        select(Subscription.sub_type, func.count(Subscription.id))
        .where(Subscription.session_key == session_key)
        .group_by(Subscription.sub_type)
    )
    counts = {row[0]: row[1] for row in (await session.execute(count_query)).all()}

    # 余额（走缓存）
    balance = await billing.get_balance(session_key)

    # 今日消费（amount<0 的 consume 汇总绝对值）
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    consumed_q = select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
        and_(
            CreditTransaction.session_key == session_key,
            CreditTransaction.txn_type == "consume",
            CreditTransaction.amount < 0,
            CreditTransaction.created_at >= today_start,
        )
    )
    consumed_today = (await session.execute(consumed_q)).scalar() or 0

    return {
        "success": True,
        "data": {
            "session_key": short_key(session_key),
            "counts": {
                "killmail": counts.get("killmail", 0),
                "structure": counts.get("structure", 0),
                "eve_status": counts.get("eve_status", 0),
            },
            "balance": balance,
            "consumed_today": abs(int(consumed_today)),
        },
    }
