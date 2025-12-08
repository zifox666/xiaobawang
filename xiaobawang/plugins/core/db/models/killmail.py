from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class KillmailSubscription(Model):
    """新的统一订阅表 - 支持灵活的条件组合"""
    __tablename__ = "killmail_subscription"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 会话信息
    platform: Mapped[str] = mapped_column()
    bot_id: Mapped[str] = mapped_column()
    session_id: Mapped[str] = mapped_column()
    session_type: Mapped[str] = mapped_column()

    # 订阅元信息
    name: Mapped[str] = mapped_column(default="未命名订阅")  # 用户自定义名称
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 描述

    # 启用状态
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 全局过滤
    min_value: Mapped[float] = mapped_column(Float, default=100_000_000)  # 最低价值
    max_age_days: Mapped[int | None] = mapped_column(default=None)  # 最大天数 (可选)

    # 条件逻辑 (JSON字段存储条件组)
    # 结构: {"logic": "AND", "conditions": [...], "groups": [...]}
    condition_groups: Mapped[str] = mapped_column(Text)  # JSON string

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)


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
