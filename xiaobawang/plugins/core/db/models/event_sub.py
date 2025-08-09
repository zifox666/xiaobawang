from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column


class EVEServerStatusSub(Model):
    """
    EVE服务器状态订阅推送
    """

    __tablename_ = "eve_server_status_subscription"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column()
    bot_id: Mapped[str] = mapped_column()
    session_id: Mapped[str] = mapped_column()
    session_type: Mapped[str] = mapped_column()

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)
