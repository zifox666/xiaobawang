"""
积分计费 API 路由

端点 (prefix=/api/credit):
  GET  /balance        当前 session 余额
  GET  /account        账户详情（余额/累计充值/累计消费/活跃）
  GET  /transactions   流水分页
  POST /recharge       充值（仅 SUPERUSER）
  GET  /rules          计费规则展示

认证与隔离复用 get_current_user，按 session_key 隔离，与 killmail /sub 的隔离方式一致。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from nonebot import get_driver
from nonebot_plugin_orm import AsyncSession, get_session
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..db.models.credit import CreditAccount, CreditTransaction
from ..helper.auth import get_current_user
from ..helper.billing import BillingRules, billing, key_from_current_user, make_session_key, short_key

router = APIRouter()


# ============================================================================
# 数据模型
# ============================================================================


class RechargeRequest(BaseModel):
    """充值请求"""
    session_type: str | None = Field(default=None, description="目标会话类型，留空则充值当前 session")
    session_id: str | None = Field(default=None, description="目标会话 ID，留空则充值当前 session")
    platform: str | None = Field(default=None, description="目标平台（防撞前缀）")
    amount: int = Field(..., gt=0, description="充值积分")
    description: str = Field(default="管理员充值", description="备注")


# ============================================================================
# 辅助
# ============================================================================


def _is_admin(current_user: dict) -> bool:
    """判断当前用户是否为 SUPERUSER；未配置 SUPERUSERS 时放行（便于开发期调试）"""
    supers = set(get_driver().config.superusers or [])
    if not supers:
        return True
    return str(current_user.get("qq", "")) in supers


async def _ensure_account(current_user: dict) -> str:
    """确保当前 session 的账户存在，返回 session_key"""
    session_key = key_from_current_user(current_user)
    await billing.get_or_create_account(
        session_key,
        platform=current_user.get("platform", ""),
        bot_id=current_user.get("bot_id", ""),
        session_id=current_user.get("session_id", ""),
        session_type=current_user.get("session_type", ""),
    )
    return session_key


# ============================================================================
# 路由
# ============================================================================


@router.get("/balance", summary="当前 session 余额")
async def get_balance(current_user: dict = Depends(get_current_user)) -> dict:
    session_key = await _ensure_account(current_user)
    balance = await billing.get_balance(session_key)
    return {
        "success": True,
        "data": {
            "session_key": short_key(session_key),
            "balance": balance,
        },
    }


@router.get("/account", summary="账户详情")
async def get_account(current_user: dict = Depends(get_current_user)) -> dict:
    session_key = await _ensure_account(current_user)
    async with get_session() as session:
        result = await session.execute(
            select(CreditAccount).where(CreditAccount.session_key == session_key)
        )
        account = result.scalar_one_or_none()
    if account is None:
        return {"success": True, "data": {"session_key": short_key(session_key), "balance": 0}}
    return {
        "success": True,
        "data": {
            "session_key": short_key(session_key),
            "balance": account.balance,
            "frozen": account.frozen,
            "total_recharged": account.total_recharged,
            "total_consumed": account.total_consumed,
            "is_active": account.is_active,
            "created_at": account.created_at.isoformat() if account.created_at else None,
        },
    }


@router.get("/transactions", summary="流水分页")
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    txn_type: str | None = Query(None, description="类型过滤 recharge/consume/refund/adjust"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    session_key = key_from_current_user(current_user)

    async with get_session() as session:
        query = select(CreditTransaction).where(CreditTransaction.session_key == session_key)
        count_query = select(func.count(CreditTransaction.id)).where(
            CreditTransaction.session_key == session_key
        )
        if txn_type:
            query = query.where(CreditTransaction.txn_type == txn_type)
            count_query = count_query.where(CreditTransaction.txn_type == txn_type)

        total = (await session.execute(count_query)).scalar() or 0

        query = query.order_by(CreditTransaction.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        rows = (await session.execute(query)).scalars().all()

    return {
        "success": True,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": r.id,
                    "txn_type": r.txn_type,
                    "amount": r.amount,
                    "balance_after": r.balance_after,
                    "ref_type": r.ref_type,
                    "ref_id": r.ref_id,
                    "description": r.description,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        },
    }


@router.post("/recharge", summary="充值（仅 SUPERUSER）")
async def recharge(
    req: RechargeRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅 SUPERUSER 可充值")

    if req.session_type and req.session_id:
        target = make_session_key(req.session_type, req.session_id, req.platform)
    else:
        target = key_from_current_user(current_user)

    # 确保目标账户存在
    await billing.get_or_create_account(
        target,
        platform=req.platform or "",
        session_id=req.session_id or "",
        session_type=req.session_type or "",
    )

    result = await billing.recharge(target, req.amount, req.description)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.reason)

    logger.info(
        f"[credit] {current_user.get('qq')} 充值 {target} +{req.amount} → {result.balance_after}"
    )
    return {
        "success": True,
        "message": "充值成功",
        "data": {
            "session_key": short_key(target),
            "charged": result.charged,
            "balance_after": result.balance_after,
        },
    }


@router.get("/rules", summary="计费规则")
async def get_rules() -> dict:
    return {"success": True, "data": BillingRules.to_dict()}
