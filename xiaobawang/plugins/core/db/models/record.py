from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime
from sqlalchemy.orm import mapped_column, Mapped


class CommandRecord(Model):
    __tablename__ = "command_record"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True, unique=True)
    source: Mapped[str] = mapped_column()
    origin: Mapped[str] = mapped_column()
    sender: Mapped[str] = mapped_column()
    event: Mapped[str] = mapped_column()
    session: Mapped[str] = mapped_column()
    time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class KillmailPushRecord(Model):
    __tablename__ = "killmail_push_record"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True, unique=True)
    sender: Mapped[int] = mapped_column()
    send_type: Mapped[str] = mapped_column()
    killmail_id: Mapped[int] = mapped_column()
    time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class BlackList(Model):
    __tablename__ = "blacklist"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True, unique=True)
    session_id: Mapped[int] = mapped_column()

