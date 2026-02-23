from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class EsiOAuthAuthorization(Model):
    __tablename__ = "esi_oauth_authorization"
    __table_args__ = (UniqueConstraint("character_id", name="uq_esi_oauth_authorization_character_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(index=True, unique=True)
    character_name: Mapped[str] = mapped_column(nullable=False)
    owner_hash: Mapped[str] = mapped_column(nullable=False)

    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)

    last_authorized_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
