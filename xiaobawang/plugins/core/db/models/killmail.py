from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column


class KillmailHighValueSubscription(Model):
    __tablename__ = "killmail_high_value_subscription"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column()
    bot_id: Mapped[str] = mapped_column()
    session_id: Mapped[str] = mapped_column()
    session_type: Mapped[str] = mapped_column()

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_value: Mapped[float] = mapped_column(Float, default=1_500_000_000)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)


class KillmailConditionSubscription(Model):
    __tablename__ = "killmail_condition_subscription"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column()
    bot_id: Mapped[str] = mapped_column()
    session_id: Mapped[str] = mapped_column()
    session_type: Mapped[str] = mapped_column()

    target_type: Mapped[str] = mapped_column()  # character, corporation, alliance, system, inventory_type
    target_id: Mapped[int] = mapped_column()
    target_name: Mapped[str] = mapped_column()

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_victim: Mapped[bool] = mapped_column(Boolean, default=True)
    is_final_blow: Mapped[bool] = mapped_column(Boolean, default=True)
    min_value: Mapped[float] = mapped_column(Float, default=100_000_000)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)
