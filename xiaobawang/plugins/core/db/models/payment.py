from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import BigInteger, Float, String
from sqlalchemy.orm import Mapped, mapped_column


class PaymentOrder(Model):
    """
    ESI 钱包支付订单

    用户发起充值时生成 8 位支付码，在游戏内向管理员钱包转账并备注该码；
    系统定时拉取钱包 journal 匹配码 + 金额，确认到账后充值积分。
    """

    __tablename__ = "payment_order"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # 8 位码
    session_key: Mapped[str] = mapped_column(String(128), index=True)  # 发起充值的会话
    isk_amount: Mapped[float] = mapped_column(Float)  # 应支付 ISK
    credit_amount: Mapped[int] = mapped_column()  # 应到积分
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/paid/expired

    # 到账后填充（用于去重与审计）
    payer_character_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    journal_ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)


class PaymentSetting(Model):
    """
    支付配置（单行表，id=1）

    存管理员绑定的 ESI 钱包角色 + ISK 汇率。
    """

    __tablename__ = "payment_setting"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    wallet_character_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wallet_character_name: Mapped[str] = mapped_column(String(128), default="")
    isk_per_1b: Mapped[int] = mapped_column(default=500)  # 1 亿 ISK = 多少积分
