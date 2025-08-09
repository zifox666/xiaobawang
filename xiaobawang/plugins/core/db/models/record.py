from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class CommandRecord(Model):
    __tablename__ = "command_record"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True, unique=True)
    bot_id: Mapped[str] = mapped_column(default="0", nullable=True)
    platform: Mapped[str] = mapped_column(default="OneBot V11", nullable=True)
    source: Mapped[str] = mapped_column()
    origin: Mapped[str] = mapped_column()
    sender: Mapped[str] = mapped_column()
    event: Mapped[str] = mapped_column()
    session: Mapped[str] = mapped_column()
    time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class KillmailPushRecord(Model):
    __tablename__ = "killmail_push_record"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True, unique=True)
    bot_id: Mapped[str] = mapped_column()
    platform: Mapped[str] = mapped_column()
    session_id: Mapped[str] = mapped_column()
    session_type: Mapped[str] = mapped_column()
    killmail_id: Mapped[int] = mapped_column()
    time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class BlackList(Model):
    __tablename__ = "blacklist"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True, unique=True)
    session_id: Mapped[int] = mapped_column()
