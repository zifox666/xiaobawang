"""
管理员 API（SUPERUSER）

端点 (prefix=/api/admin):
  POST /login            使用配置 admin_token 登录
  GET  /sessions         所有会话账户（模拟登录选目标）
  GET  /subscriptions    模拟登录：查任意 session 的订阅
  GET  /balance          模拟登录：查任意 session 余额
  GET  /transactions     模拟登录：查任意 session 流水
  GET  /orders           支付记录
  POST /orders/{code}/mark-paid  手动标记订单已支付
  POST /credit/recharge  手动给会话加积分
  GET  /setting          支付配置
  POST /setting          更新配置（钱包绑定 + 汇率）
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from nonebot_plugin_orm import get_session
from pydantic import BaseModel
from sqlalchemy import func, select

from ..config import plugin_config
from ..db.models.credit import CreditAccount, CreditTransaction
from ..db.models.payment import PaymentOrder
from ..db.models.subscription import Subscription
from ..helper.billing import billing, short_key
from ..helper.billing.payment import get_or_create_setting, list_payment_orders, update_setting

router = APIRouter()


def _configured_admin_token() -> str | None:
    token = getattr(plugin_config, "admin_token", None)
    return token.strip() if isinstance(token, str) and token.strip() else None


async def require_admin_token(authorization: str = Header("", alias="Authorization")) -> None:
    expected = _configured_admin_token()
    if expected is None:
        raise HTTPException(status_code=503, detail="未配置 admin_token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="管理员 token 无效")


class AdminLoginRequest(BaseModel):
    token: str


@router.post("/login", summary="管理员 token 登录")
async def admin_login(req: AdminLoginRequest) -> dict:
    expected = _configured_admin_token()
    if expected is None:
        raise HTTPException(status_code=503, detail="未配置 admin_token")
    if req.token.strip() != expected:
        raise HTTPException(status_code=403, detail="管理员 token 无效")
    return {"success": True, "data": {"token": expected}}


@router.get("/sessions", summary="所有会话账户")
async def admin_sessions(_admin: None = Depends(require_admin_token)) -> dict:
    async with get_session() as session:
        result = await session.execute(
            select(CreditAccount).order_by(CreditAccount.created_at.desc())
        )
        accounts = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "session_key": a.session_key,  # 完整 key，传给其他 admin 端点
                "display": short_key(a.session_key),
                "platform": a.platform,
                "session_id": a.session_id,
                "session_type": a.session_type,
                "balance": a.balance,
                "total_recharged": a.total_recharged,
                "total_consumed": a.total_consumed,
                "is_active": a.is_active,
            }
            for a in accounts
        ],
    }


@router.get("/subscriptions", summary="模拟登录：查任意 session 订阅")
async def admin_subscriptions(
    session_key: str = Query(..., description="完整 session_key"),
    _admin: None = Depends(require_admin_token),
) -> dict:
    async with get_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.session_key == session_key)
        )
        subs = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": s.id,
                "sub_type": s.sub_type,
                "source_table": s.source_table,
                "source_id": s.source_id,
                "is_enabled": s.is_enabled,
                "unit_price": s.unit_price,
                "complexity_factor": s.complexity_factor,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in subs
        ],
    }


@router.get("/balance", summary="模拟登录：查任意 session 余额")
async def admin_balance(
    session_key: str = Query(...),
    _admin: None = Depends(require_admin_token),
) -> dict:
    balance = await billing.get_balance(session_key)
    return {"success": True, "data": {"session_key": short_key(session_key), "balance": balance}}


@router.get("/transactions", summary="模拟登录：查任意 session 流水")
async def admin_transactions(
    session_key: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: None = Depends(require_admin_token),
) -> dict:
    async with get_session() as session:
        query = select(CreditTransaction).where(
            CreditTransaction.session_key == session_key
        )
        count_q = select(func.count(CreditTransaction.id)).where(
            CreditTransaction.session_key == session_key
        )
        total = (await session.execute(count_q)).scalar() or 0
        query = query.order_by(CreditTransaction.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
    return {
        "success": True,
        "data": {
            "total": total,
            "items": [
                {
                    "id": r.id,
                    "txn_type": r.txn_type,
                    "amount": r.amount,
                    "balance_after": r.balance_after,
                    "ref_type": r.ref_type,
                    "description": r.description,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        },
    }


@router.get("/orders", summary="支付记录")
async def admin_orders(
    status: str | None = Query(None),
    _admin: None = Depends(require_admin_token),
) -> dict:
    orders = await list_payment_orders(status=status, limit=100)
    return {
        "success": True,
        "data": [
            {
                "payment_code": o.payment_code,
                "session_key": short_key(o.session_key),
                "isk_amount": o.isk_amount,
                "credit_amount": o.credit_amount,
                "status": o.status,
                "payer_character_id": o.payer_character_id,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            }
            for o in orders
        ],
    }


class ManualRechargeRequest(BaseModel):
    session_key: str
    amount: int
    description: str = "管理员手动加积分"


@router.post("/credit/recharge", summary="手动给会话加积分")
async def admin_manual_recharge(
    req: ManualRechargeRequest,
    _admin: None = Depends(require_admin_token),
) -> dict:
    result = await billing.recharge(req.session_key, req.amount, req.description)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.reason)
    return {
        "success": True,
        "data": {
            "session_key": short_key(req.session_key),
            "amount": result.charged,
            "balance_after": result.balance_after,
        },
    }


class MarkPaidRequest(BaseModel):
    description: str = "管理员手动确认支付"


@router.post("/orders/{payment_code}/mark-paid", summary="手动标记订单已支付")
async def admin_mark_order_paid(
    payment_code: str,
    req: MarkPaidRequest,
    _admin: None = Depends(require_admin_token),
) -> dict:
    code = payment_code.upper()
    async with get_session() as session:
        result = await session.execute(
            select(PaymentOrder).where(PaymentOrder.payment_code == code)
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise HTTPException(status_code=404, detail="订单不存在")
        if order.status == "paid":
            return {
                "success": True,
                "data": {
                    "payment_code": order.payment_code,
                    "already_paid": True,
                    "credit_amount": order.credit_amount,
                    "status": order.status,
                },
            }
        if order.status != "pending":
            raise HTTPException(status_code=400, detail=f"订单状态异常: {order.status}")

        account_result = await session.execute(
            select(CreditAccount).where(CreditAccount.session_key == order.session_key).with_for_update()
        )
        account = account_result.scalar_one_or_none()
        if account is None:
            raise HTTPException(status_code=400, detail="账户不存在")

        credit_amount = order.credit_amount
        order_code = order.payment_code
        isk_amount = order.isk_amount
        session_key = order.session_key
        account.balance += order.credit_amount
        account.total_recharged += order.credit_amount
        account.is_active = True
        balance_after = account.balance
        order.status = "paid"
        order.paid_at = datetime.now()
        session.add(
            CreditTransaction(
                session_key=order.session_key,
                txn_type="recharge",
                amount=order.credit_amount,
                balance_after=balance_after,
                ref_type="payment",
                ref_id=order.payment_code,
                description=f"{req.description} {order_code} ({isk_amount:.0f} ISK)",
            )
        )
        await session.commit()
        await billing._cache_balance(session_key, balance_after)
        return {
            "success": True,
            "data": {
                "payment_code": order_code,
                "credit_amount": credit_amount,
                "status": "paid",
                "balance_after": balance_after,
            },
        }


@router.get("/setting", summary="支付配置")
async def admin_get_setting(_admin: None = Depends(require_admin_token)) -> dict:
    s = await get_or_create_setting()
    return {
        "success": True,
        "data": {
            "wallet_character_id": s.wallet_character_id,
            "wallet_character_name": s.wallet_character_name,
            "isk_per_1b": s.isk_per_1b,
        },
    }


class UpdateSettingRequest(BaseModel):
    wallet_character_id: int | None = None
    wallet_character_name: str | None = None
    isk_per_1b: int | None = None


@router.post("/setting", summary="更新支付配置（钱包绑定 + 汇率）")
async def admin_update_setting(
    req: UpdateSettingRequest,
    _admin: None = Depends(require_admin_token),
) -> dict:
    s = await update_setting(
        wallet_character_id=req.wallet_character_id,
        wallet_character_name=req.wallet_character_name,
        isk_per_1b=req.isk_per_1b,
    )
    return {
        "success": True,
        "data": {
            "wallet_character_id": s.wallet_character_id,
            "wallet_character_name": s.wallet_character_name,
            "isk_per_1b": s.isk_per_1b,
        },
    }
