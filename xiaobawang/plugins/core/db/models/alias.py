from nonebot_plugin_orm import Model
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column


class TypeAlias(Model):
    __tablename__ = "type_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alia: Mapped[str] = mapped_column()
    name: Mapped[str] = mapped_column()
