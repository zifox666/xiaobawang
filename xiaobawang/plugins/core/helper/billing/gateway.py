"""
BillingGateway —— 计费网关

三模块推送的统一扣费入口：
  - precheck:  推送前余额预检（killmail 先查，省掉无谓渲染）
  - charge:    推送成功后扣费 + 写流水
  - recharge:  充值
  - pause_subscription: 余额耗尽自动暂停订阅

灰度期 billing_enabled=False 时，charge 直接返回成功但不实际扣费，账户体系照常可查。
"""

from dataclasses import dataclass

from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...config import plugin_config
from ...db.models.credit import CreditAccount, CreditTransaction
from ...db.models.subscription import Subscription
from ...utils.common.cache import cache
from .rules import BillingRules

_BALANCE_CACHE_PREFIX = "billing:balance:"
_BALANCE_CACHE_EXPIRE = 60  # 余额缓存 60s，precheck 高频读不压 DB


@dataclass
class ChargeResult:
    """扣费结果"""
    success: bool
    charged: int
    balance_after: int
    reason: str = ""


class BillingGateway:
    """计费网关（单例风格，方法均为 async classmethod/实例方法）"""

    # ── 余额缓存 ────────────────────────────────────────────
    @staticmethod
    async def _cache_balance(session_key: str, balance: int) -> None:
        try:
            await cache.set(
                f"{_BALANCE_CACHE_PREFIX}{session_key}", balance, expire=_BALANCE_CACHE_EXPIRE
            )
        except Exception as e:
            logger.debug(f"[billing] 缓存余额失败: {e}")

    @staticmethod
    async def _read_cached_balance(session_key: str) -> int | None:
        try:
            return await cache.get(f"{_BALANCE_CACHE_PREFIX}{session_key}")
        except Exception:
            return None

    @staticmethod
    async def _invalidate_balance(session_key: str) -> None:
        try:
            await cache.delete(f"{_BALANCE_CACHE_PREFIX}{session_key}")
        except Exception:
            pass

    # ── 账户 ────────────────────────────────────────────────
    async def get_account(self, session_key: str) -> CreditAccount | None:
        async with get_session() as session:
            result = await session.execute(
                select(CreditAccount).where(CreditAccount.session_key == session_key)
            )
            return result.scalar_one_or_none()

    async def get_or_create_account(
        self,
        session_key: str,
        platform: str = "",
        bot_id: str = "",
        session_id: str = "",
        session_type: str = "",
    ) -> CreditAccount:
        """获取或创建账户；新账户发放初始积分"""
        async with get_session() as session:
            result = await session.execute(
                select(CreditAccount).where(CreditAccount.session_key == session_key)
            )
            account = result.scalar_one_or_none()
            if account is not None:
                return account

            initial = getattr(plugin_config, "billing_initial_credit", 0)
            account = CreditAccount(
                session_key=session_key,
                platform=platform,
                bot_id=bot_id,
                session_id=session_id,
                session_type=session_type,
                balance=initial,
                total_recharged=initial,
            )
            session.add(account)
            # 初始发放记一条充值流水
            if initial > 0:
                session.add(
                    CreditTransaction(
                        session_key=session_key,
                        txn_type="recharge",
                        amount=initial,
                        balance_after=initial,
                        ref_type=None,
                        ref_id=None,
                        description="新账户初始积分",
                    )
                )
            await session.commit()
            await self._cache_balance(session_key, initial)
            logger.info(f"[billing] 新建账户 {session_key} 初始积分 {initial}")
            return account

    async def get_balance(self, session_key: str) -> int:
        """查询余额（先走缓存）"""
        cached = await self._read_cached_balance(session_key)
        if cached is not None:
            return int(cached)
        account = await self.get_account(session_key)
        balance = account.balance if account else 0
        await self._cache_balance(session_key, balance)
        return balance

    # ── 充值 ────────────────────────────────────────────────
    async def recharge(
        self, session_key: str, amount: int, description: str = "管理员充值"
    ) -> ChargeResult:
        if amount <= 0:
            return ChargeResult(False, 0, 0, "充值金额必须 > 0")
        async with get_session() as session:
            result = await session.execute(
                select(CreditAccount).where(CreditAccount.session_key == session_key)
            )
            account = result.scalar_one_or_none()
            if account is None:
                return ChargeResult(False, 0, 0, "账户不存在")
            account.balance += amount
            account.total_recharged += amount
            account.is_active = True
            balance_after = account.balance
            session.add(
                CreditTransaction(
                    session_key=session_key,
                    txn_type="recharge",
                    amount=amount,
                    balance_after=balance_after,
                    description=description,
                )
            )
            await session.commit()
            await self._cache_balance(session_key, balance_after)
            logger.info(f"[billing] 充值 {session_key} +{amount} → {balance_after}")
            return ChargeResult(True, amount, balance_after)

    # ── 模块计费开关 ────────────────────────────────────────
    @staticmethod
    def should_bill(sub_type: str) -> bool:
        """判断某模块是否启用计费拦截（全局开关 × 模块白名单）"""
        if not getattr(plugin_config, "billing_enabled", False):
            return False
        modules = getattr(plugin_config, "billing_enabled_modules", []) or []
        return sub_type in modules

    # ── 预检 ────────────────────────────────────────────────
    async def precheck(self, session_key: str, estimated_cost: int) -> bool:
        """推送前余额预检。estimated_cost<=0 视为免费，直接放行。"""
        if estimated_cost <= 0:
            return True
        if not getattr(plugin_config, "billing_enabled", False):
            return True 
        balance = await self.get_balance(session_key)
        return balance >= estimated_cost

    # ── 扣费 ────────────────────────────────────────────────
    async def charge(
        self,
        session_key: str,
        sub_type: str,
        subscription_id: int | None = None,
        count: int = 1,
        unit_price: int | None = None,
        factor: float = 1.0,
        ref_id: str | None = None,
        description: str = "",
    ) -> ChargeResult:
        """
        推送成功后扣费
        """
        if unit_price is None:
            unit_price = BillingRules.get_unit_price(sub_type)
        charged = BillingRules.calc_charge(sub_type, unit_price, factor, count)

        billing_enabled = self.should_bill(sub_type)

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(CreditAccount).where(CreditAccount.session_key == session_key)
                )
                account = result.scalar_one_or_none()
                if account is None:
                    # 自动建账户（用 0 初始积分，避免推送链路因缺账户中断）
                    account = CreditAccount(
                        session_key=session_key, platform="", balance=plugin_config.billing_migrate_credit, total_recharged=0
                    )
                    session.add(account)

                # commit 前快照余额，避免 expire_on_commit 后访问 account.balance 触发异步懒加载
                bal = account.balance

                if not billing_enabled or charged <= 0:
                    session.add(
                        CreditTransaction(
                            session_key=session_key,
                            txn_type="consume",
                            amount=0,
                            balance_after=bal,
                            ref_type=sub_type,
                            ref_id=ref_id,
                            description=description or f"{sub_type} 推送 ×{count}（未计费）",
                        )
                    )
                    await session.commit()
                    return ChargeResult(True, 0, bal, "未计费")

                if bal < charged:
                    # 余额不足
                    session.add(
                        CreditTransaction(
                            session_key=session_key,
                            txn_type="consume",
                            amount=0,
                            balance_after=bal,
                            ref_type=sub_type,
                            ref_id=ref_id,
                            description=f"{description} 余额不足跳过（需 {charged}）",
                        )
                    )
                    await session.commit()
                    logger.warning(
                        f"[billing] 余额不足 {session_key} 余额 {bal} < 需 {charged}"
                    )
                    return ChargeResult(False, 0, bal, "余额不足")

                account.balance = bal - charged
                account.total_consumed += charged
                balance_after = account.balance
                session.add(
                    CreditTransaction(
                        session_key=session_key,
                        txn_type="consume",
                        amount=-charged,
                        balance_after=balance_after,
                        ref_type=sub_type,
                        ref_id=ref_id,
                        description=description or f"{sub_type} 推送 ×{count} ({ref_id})",
                    )
                )
                await session.commit()
                await self._cache_balance(session_key, balance_after)
                logger.debug(
                    f"[billing] 扣费 {session_key} -{charged} → {balance_after} ({sub_type} ×{count})"
                )
                return ChargeResult(True, charged, balance_after)
        except Exception as e:
            logger.error(f"[billing] charge 异常 {session_key} {sub_type}: {e}")
            return ChargeResult(False, 0, 0, f"计费异常: {e}")

    # ── 订阅注册表 ──────────────────────────────────────────
    async def register_subscription(
        self,
        session_key: str,
        sub_type: str,
        source_table: str,
        source_id: int,
        unit_price: int | None = None,
        factor: float = 1.0,
    ) -> Subscription:
        """订阅创建时写入注册表（含计费快照）"""
        if unit_price is None:
            unit_price = BillingRules.get_unit_price(sub_type)
        async with get_session() as session:
            sub = Subscription(
                session_key=session_key,
                sub_type=sub_type,
                source_table=source_table,
                source_id=source_id,
                is_enabled=True,
                unit_price=unit_price,
                complexity_factor=factor,
            )
            session.add(sub)
            await session.commit()
            await session.refresh(sub)
            return sub

    async def pause_subscription(self, subscription_id: int, reason: str = "") -> bool:
        """余额耗尽自动暂停订阅（仅置注册表 is_enabled=False；模块表由调用方同步）"""
        async with get_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            sub = result.scalar_one_or_none()
            if sub is None:
                return False
            sub.is_enabled = False
            await session.commit()
            logger.info(f"[billing] 暂停订阅 #{subscription_id}: {reason}")
            return True

    # ── 低余额提醒 ──────────────────────────────────────────
    async def notify_low_balance_if_needed(
        self,
        session_key: str,
        platform: str,
        bot_id: str,
        session_id: str,
        session_type: str,
        balance: int,
    ) -> None:
        """
        余额低于 billing_low_balance_threshold 时向会话推送一条提醒。

        - 仅 billing_enabled=True 时提醒（灰度期不打扰）
        - 1 小时内同一 session 只提醒一次（Redis 冷却去重）
        """
        threshold = getattr(plugin_config, "billing_low_balance_threshold", 1000)
        if balance > threshold:
            return
        if not getattr(plugin_config, "billing_enabled", False):
            return
        if not (platform and session_id and session_type):
            return

        # 冷却去重
        notify_key = f"billing:low_notified:{session_key}"
        try:
            if await cache.get(notify_key):
                return
        except Exception:
            pass

        try:
            from nonebot_plugin_alconna import Target, UniMessage

            target = Target(
                id=str(session_id),
                self_id=str(bot_id),
                channel=session_type.upper() in ("GROUP", "CHANNEL"),
                private=session_type.upper() == "PRIVATE",
                platform=platform,
            )
            msg = (
                f"积分余额不足提醒\n"
                f"当前余额: {balance}\n"
                f"部分订阅推送可能已暂停\n"
                f"前往 https://xbw.newdoublex.space/subscription 进行管理"
            )
            await UniMessage.text(msg).send(target=target)
            await cache.set(notify_key, 1, expire=3600)
            logger.info(f"[billing] 低余额提醒已发送 {session_key} 余额 {balance}")
        except Exception as e:
            logger.error(f"[billing] 低余额提醒发送失败: {e}")


billing = BillingGateway()
