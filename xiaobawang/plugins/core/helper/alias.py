from typing import Optional, List

from sqlalchemy import select

from ..db.models.alias import TypeAlias
from ..utils.common.cache import cache


class AliasHelper:
    def __init__(self):
        self.alias_cache_key_prefix: str = "alias_"

    async def check(self, session, word: str) -> Optional[List[str]]:
        """
        检查输入是否为物品别名

        Args:
            session: 数据库会话
            word: 查询关键字

        Returns:
            如果存在别名则返回实际物品名称列表，否则返回None
        """
        cache_key = f"{self.alias_cache_key_prefix}{word}"
        cached_alias = await cache.get(cache_key)

        if cached_alias:
            return cached_alias

        query = select(TypeAlias).where(TypeAlias.alia == word)
        result = await session.execute(query)
        alias_items = result.scalars().all()

        if alias_items:
            item_names = [item.name for item in alias_items]
            await cache.set(cache_key, item_names, 7 * 24 * 3600)
            return item_names

        return None

    @classmethod
    async def add(cls, session, alias_name: str, type_name_list: list[str]):
        """
        添加物品别名

        Args:
            session: 数据库会话
            alias_name: 别名名称
            type_name_list: 实际物品名称列表
        """
        for type_name in type_name_list:
            alias = TypeAlias(alia=alias_name, name=type_name)
            session.add(alias)
        await session.commit()

    @classmethod
    async def remove(cls, session, alias_name: str):
        """
        删除物品别名

        Args:
            session: 数据库会话
            alias_name: 别名名称
        """
        query = select(TypeAlias).where(TypeAlias.alia == alias_name)
        result = await session.execute(query)
        alias_items = result.scalars().all()

        for item in alias_items:
            await session.delete(item)
        await session.commit()