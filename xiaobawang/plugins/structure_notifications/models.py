from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class StructureNotificationSub(Model):
    """建筑通知订阅 - 将角色的建筑通知推送到指定会话"""

    __tablename__ = "structure_notification_sub"
    __table_args__ = (
        UniqueConstraint("character_id", "platform", "session_id", name="uq_struct_sub_char_session"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 关联的 EVE 角色
    character_id: Mapped[int] = mapped_column(Integer, index=True)
    character_name: Mapped[str] = mapped_column(String(128), default="")

    # 会话信息 (通过 /verify 绑定获得)
    platform: Mapped[str] = mapped_column(String(64))
    bot_id: Mapped[str] = mapped_column(String(128))
    session_id: Mapped[str] = mapped_column(String(128))
    session_type: Mapped[str] = mapped_column(String(32))

    # 订阅的通知类别 (JSON 数组, 如 ["structure", "moonmining", "sovereignty"])
    categories: Mapped[str] = mapped_column(Text, default='["structure"]')

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class StructureNotificationRecord(Model):
    """已推送的建筑通知记录 - 防止重复推送"""

    __tablename__ = "structure_notification_record"
    __table_args__ = (
        UniqueConstraint("notification_id", "character_id", name="uq_struct_notif_id_char"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    notification_id: Mapped[int] = mapped_column(Integer, index=True)
    character_id: Mapped[int] = mapped_column(Integer, index=True)
    notification_type: Mapped[str] = mapped_column(String(128))
    sender_id: Mapped[int] = mapped_column(Integer)
    sender_type: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)

    pushed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
