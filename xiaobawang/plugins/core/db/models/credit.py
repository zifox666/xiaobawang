from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class CreditAccount(Model):
    """
    积分账户 —— 主键为 session_key（付费实体）

    session_key = f"{session_type}:{session_id}"，例如 "GROUP:123456789"
    一个群 / 一个私聊 = 一个积分账户，与现有认证隔离方式一致。
    """

    __tablename__ = "credit_account"

    # 付费实体：f"{session_type}:{session_id}"（可选加 platform 前缀防跨平台撞号）
    session_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    # 冗余存平台信息，便于反查与展示
    platform: Mapped[str] = mapped_column(String(64))
    bot_id: Mapped[str] = mapped_column(String(128), default="")
    session_id: Mapped[str] = mapped_column(String(128))
    session_type: Mapped[str] = mapped_column(String(32))

    balance: Mapped[int] = mapped_column(default=0)  # 可用余额
    frozen: Mapped[int] = mapped_column(default=0)  # 冻结（预扣）
    total_recharged: Mapped[int] = mapped_column(default=0)  # 累计充值
    total_consumed: Mapped[int] = mapped_column(default=0)  # 累计消费
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 余额耗尽可停用

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)


class CreditTransaction(Model):
    """
    积分流水 —— 每一笔充值/消费/退款/调整都记录，可追溯。

    amount 正数为入账（充值/退款），负数为出账（消费）。
    """

    __tablename__ = "credit_transaction"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String(128), index=True)
    txn_type: Mapped[str] = mapped_column(String(16))  # recharge/consume/refund/adjust
    amount: Mapped[int] = mapped_column()  # 正入账 / 负出账
    balance_after: Mapped[int] = mapped_column()  # 操作后余额快照
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # killmail/structure/eve_status
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 关联推送/订阅 ID
    push_delivery_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.now, index=True)
