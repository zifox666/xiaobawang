"""Durable push state. Timestamps are UTC Unix seconds."""

import time

from nonebot_plugin_orm import Model
from sqlalchemy import JSON, Float, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class PushEvent(Model):
    __tablename__ = "push_event"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[float] = mapped_column(Float, default=time.time)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    token: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    __table_args__ = (Index("ix_push_event_due", "state", "available_at"),)


class PushCursor(Model):
    __tablename__ = "push_cursor"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class PushArtifact(Model):
    __tablename__ = "push_artifact"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class PushBot(Model):
    __tablename__ = "push_bot"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(64))
    bot_id: Mapped[str] = mapped_column(String(128))
    paused: Mapped[bool] = mapped_column(default=False)
    available_at: Mapped[float] = mapped_column(Float, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    token: Mapped[str] = mapped_column(String(64), default="")


class PushDelivery(Model):
    __tablename__ = "push_delivery"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(160), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    bot_key: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(64))
    bot_id: Mapped[str] = mapped_column(String(128))
    session_id: Mapped[str] = mapped_column(String(128))
    session_type: Mapped[str] = mapped_column(String(32))
    account_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    priority: Mapped[int] = mapped_column(default=0)
    cost: Mapped[int] = mapped_column(default=0)
    reserved: Mapped[bool] = mapped_column(default=False)
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[float] = mapped_column(Float, default=time.time)
    expires_at: Mapped[float] = mapped_column(Float)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    batch_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    receipt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (Index("ix_push_delivery_due", "state", "available_at", "priority"),)


class PushAttempt(Model):
    __tablename__ = "push_attempt"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    delivery_ids: Mapped[list] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24), default="sending")
    started_at: Mapped[float] = mapped_column(Float, default=time.time)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    receipt: Mapped[str] = mapped_column(Text, default="")
