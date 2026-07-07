from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import BigInteger, Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column


class Subscription(Model):
    """
    统一订阅注册表 —— 聚合三种订阅（killmail/structure/eve_status）的索引与计费归属

    不合并各模块订阅表（会破坏 killmail 条件引擎与 structure OAuth），
    本表只做聚合索引与计费快照：source_table + source_id 指向各模块订阅表的主键。
    """

    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String(128), index=True)  # 付费实体归属
    sub_type: Mapped[str] = mapped_column(String(32))  # killmail / structure / eve_status
    source_table: Mapped[str] = mapped_column(String(64))  # 对应模块订阅表名
    source_id: Mapped[int] = mapped_column(BigInteger)  # 对应模块订阅表主键

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 计费快照：订阅创建时锁定单价与复杂度因子，避免规则变更影响存量订阅
    unit_price: Mapped[int] = mapped_column(default=0)
    complexity_factor: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)
