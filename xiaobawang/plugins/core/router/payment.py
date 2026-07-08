"""
支付 API（用户侧）

端点 (prefix=/api/payment):
  POST /order          创建充值订单（生成 8 位支付码）
  GET  /order/{code}   查订单状态（轮询是否到账）
  GET  /setting        支付配置（钱包角色 + 汇率，用于展示转账指引）
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..helper.auth import get_current_user
from ..helper.billing import key_from_current_user
from ..helper.billing.payment import (
    create_payment_order,
    get_or_create_setting,
    get_payment_order,
    verify_payment,
)

router = APIRouter()


class CreateOrderRequest(BaseModel):
    isk_amount: float = Field(..., gt=0, description="充值 ISK 金额（1e8 = 1 亿）")


@router.post("/order", summary="创建充值订单")
async def create_order(
    req: CreateOrderRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    session_key = key_from_current_user(current_user)
    try:
        order = await create_payment_order(session_key, req.isk_amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    setting = await get_or_create_setting()
    return {
        "success": True,
        "data": {
            "payment_code": order.payment_code,
            "isk_amount": order.isk_amount,
            "credit_amount": order.credit_amount,
            "status": order.status,
            "wallet_character_name": setting.wallet_character_name,
            "wallet_character_id": setting.wallet_character_id,
            "expires_at": order.expires_at.isoformat() if order.expires_at else None,
        },
    }


@router.get("/order/{code}", summary="查订单状态")
async def get_order_status(
    code: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    order = await get_payment_order(code)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {
        "success": True,
        "data": {
            "payment_code": order.payment_code,
            "isk_amount": order.isk_amount,
            "credit_amount": order.credit_amount,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        },
    }


@router.post("/order/{code}/verify", summary="我已支付：核销订单")
async def verify_order(
    code: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """用户点击「我已支付」后触发：拉取钱包 journal 匹配该订单，到账则充值"""
    result = await verify_payment(code)
    return {"success": result["success"], "data": result}


@router.get("/setting", summary="支付配置（转账指引）")
async def get_payment_setting(
    current_user: dict = Depends(get_current_user),
) -> dict:
    setting = await get_or_create_setting()
    return {
        "success": True,
        "data": {
            "wallet_character_id": setting.wallet_character_id,
            "wallet_character_name": setting.wallet_character_name,
            "isk_per_1b": setting.isk_per_1b,
        },
    }
