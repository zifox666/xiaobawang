"""
ESI 钱包支付服务

- create_payment_order: 用户发起充值，生成 8 位支付码 + 按汇率换算积分
- poll_and_match_payments: 定时拉取钱包 journal，匹配 pending 订单并自动充值
- get_or_create_setting / update_setting: 钱包绑定 + 汇率配置
"""

import secrets
from datetime import datetime, timedelta

from nonebot import logger, require
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...db.models.payment import PaymentOrder, PaymentSetting
from ...api.esi.wallet import get_wallet_journal
from .gateway import billing

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

from xiaobawang.plugins.eve_oauth.api import require_scopes  # noqa: E402
require_scopes("billing", ["esi-wallet.read_character_wallet.v1"])

_PAYMENT_CODE_EXPIRE_HOURS = 24


# ── 配置 ────────────────────────────────────────────────────
async def get_or_create_setting() -> PaymentSetting:
    async with get_session() as session:
        result = await session.execute(select(PaymentSetting).where(PaymentSetting.id == 1))
        setting = result.scalar_one_or_none()
        if setting is None:
            setting = PaymentSetting(id=1, isk_per_1b=500)
            session.add(setting)
            await session.commit()
            await session.refresh(setting)
        return setting


async def update_setting(
    wallet_character_id: int | None = None,
    wallet_character_name: str | None = None,
    isk_per_1b: int | None = None,
) -> PaymentSetting:
    await get_or_create_setting()
    async with get_session() as session:
        result = await session.execute(select(PaymentSetting).where(PaymentSetting.id == 1))
        s = result.scalar_one()
        if wallet_character_id is not None:
            s.wallet_character_id = wallet_character_id
        if wallet_character_name is not None:
            s.wallet_character_name = wallet_character_name
        if isk_per_1b is not None:
            s.isk_per_1b = isk_per_1b
        await session.commit()
        await session.refresh(s)
        return s


# ── 订单 ────────────────────────────────────────────────────
def _generate_code() -> str:
    return secrets.token_hex(4).upper()  # 8 位大写 hex


async def create_payment_order(session_key: str, isk_amount: float) -> PaymentOrder:
    """创建支付订单：生成 8 位码，按汇率换算积分"""
    setting = await get_or_create_setting()
    credit_amount = int(isk_amount / 1e8 * setting.isk_per_1b)
    if credit_amount <= 0:
        raise ValueError("金额过小，兑换积分为 0")

    # 生成唯一码（重试 5 次）
    code = None
    for _ in range(5):
        candidate = _generate_code()
        async with get_session() as session:
            existing = await session.execute(
                select(PaymentOrder).where(PaymentOrder.payment_code == candidate)
            )
            if existing.scalar_one_or_none() is None:
                code = candidate
                break
    if code is None:
        raise RuntimeError("生成支付码失败，请重试")

    order = PaymentOrder(
        payment_code=code,
        session_key=session_key,
        isk_amount=isk_amount,
        credit_amount=credit_amount,
        status="pending",
        expires_at=datetime.now() + timedelta(hours=_PAYMENT_CODE_EXPIRE_HOURS),
    )
    async with get_session() as session:
        session.add(order)
        await session.commit()
        await session.refresh(order)
    logger.info(
        f"[payment] 创建订单 {code} 会话 {session_key} {isk_amount} ISK → {credit_amount} 积分"
    )
    return order


async def get_payment_order(code: str) -> PaymentOrder | None:
    async with get_session() as session:
        result = await session.execute(
            select(PaymentOrder).where(PaymentOrder.payment_code == code)
        )
        return result.scalar_one_or_none()


async def list_payment_orders(
    status: str | None = None, limit: int = 50
) -> list[PaymentOrder]:
    async with get_session() as session:
        query = select(PaymentOrder).order_by(PaymentOrder.created_at.desc()).limit(limit)
        if status:
            query = query.where(PaymentOrder.status == status)
        result = await session.execute(query)
        return list(result.scalars().all())


# ── journal 匹配 ────────────────────────────────────────────
@scheduler.scheduled_job("interval", hours=1, id="poll_and_match_payments")
async def poll_and_match_payments():
    """定时任务：拉取钱包 journal，匹配 pending 订单并充值"""
    setting = await get_or_create_setting()
    if not setting.wallet_character_id:
        return  # 未绑定钱包

    async with get_session() as session:
        result = await session.execute(
            select(PaymentOrder).where(PaymentOrder.status == "pending")
        )
        pending_orders = list(result.scalars().all())

    if not pending_orders:
        return

    code_map = {o.payment_code: o for o in pending_orders}

    journal = await get_wallet_journal(setting.wallet_character_id, rows=100)
    if not journal:
        return

    paid_count = 0
    for entry in journal:
        if entry.get("type") != "player_donation":
            continue
        reason = entry.get("reason", "") or ""
        amount = float(entry.get("amount", 0))
        ref_id = entry.get("ref_id")

        # 匹配 reason 含支付码
        matched_code = next((c for c in code_map if c in reason), None)
        if not matched_code:
            continue

        order = code_map[matched_code]
        # 金额匹配（允许 1 ISK 误差）
        if abs(amount - order.isk_amount) > 1:
            logger.warning(
                f"[payment] 订单 {matched_code} 金额不匹配: 期望 {order.isk_amount} 实际 {amount}"
            )
            continue

        # 去重
        if order.journal_ref_id == ref_id:
            continue

        # 充值积分
        await billing.recharge(
            order.session_key,
            order.credit_amount,
            description=f"ESI 钱包充值 {matched_code} ({amount:.0f} ISK)",
        )
        # 标记 paid
        async with get_session() as session:
            result = await session.execute(
                select(PaymentOrder).where(PaymentOrder.id == order.id)
            )
            o = result.scalar_one_or_none()
            if o and o.status == "pending":
                o.status = "paid"
                o.payer_character_id = entry.get("first_party")
                o.journal_ref_id = ref_id
                o.paid_at = datetime.now()
                await session.commit()
                paid_count += 1
                logger.info(
                    f"[payment] 订单 {matched_code} 已完成 +{o.credit_amount} 积分"
                )

    if paid_count:
        logger.info(f"[payment] 本次处理 {paid_count} 笔到账")


# ── 手动核销 ──────────────
async def verify_payment(code: str) -> dict:
    """拉 journal 匹配该订单，到账则充值并标记 paid"""
    order = await get_payment_order(code)
    if order is None:
        return {"success": False, "reason": "订单不存在"}
    if order.status == "paid":
        return {"success": True, "already_paid": True, "credit_amount": order.credit_amount}
    if order.status != "pending":
        return {"success": False, "reason": f"订单状态异常: {order.status}"}

    setting = await get_or_create_setting()
    if not setting.wallet_character_id:
        return {"success": False, "reason": "管理员未绑定钱包"}

    journal = await get_wallet_journal(setting.wallet_character_id, rows=100)
    for entry in journal:
        if entry.get("type") != "player_donation":
            continue
        reason = entry.get("reason", "") or ""
        amount = float(entry.get("amount", 0))
        ref_id = entry.get("ref_id")
        if code not in reason:
            continue
        if abs(amount - order.isk_amount) > 1:
            continue
        if order.journal_ref_id == ref_id:
            continue
        await billing.recharge(
            order.session_key,
            order.credit_amount,
            description=f"ESI 钱包充值 {code} ({amount:.0f} ISK)",
        )
        async with get_session() as session:
            result = await session.execute(
                select(PaymentOrder).where(PaymentOrder.id == order.id)
            )
            o = result.scalar_one_or_none()
            if o and o.status == "pending":
                o.status = "paid"
                o.payer_character_id = entry.get("first_party")
                o.journal_ref_id = ref_id
                o.paid_at = datetime.now()
                await session.commit()
                logger.info(f"[payment] 订单 {code} 已完成 +{o.credit_amount} 积分")
        return {"success": True, "credit_amount": order.credit_amount}

    return {"success": False, "reason": "未找到匹配转账，请确认已转账并备注支付码"}
