from .cache import cache, cache_result
from .models import TrnTranslations, TC_TYPES_ID, InvTypes, TC_GROUP_ID, InvFlags
from .utils import text_processor
from .config import plugin_config
from .db import get_session

from nonebot import logger
from sqlalchemy import or_, and_, select


class SDESearch:
    def __init__(self):
        self.default_lang = plugin_config.sde_default_language

    @cache_result(prefix="type_search_", exclude_args=[0])
    async def search_item_by_name(
            self,
            name: str,
            market: bool = True,
            limit: int = 1000
    ):
        """
        按物品名称搜索，支持中英文模糊查询
        """
        async with await get_session() as session:
            conditions = await self._build_search_conditions(name)
            logger.debug(f"conditions: {conditions}")

            trans_query = select(TrnTranslations).where(
                and_(
                    TrnTranslations.tcID == TC_TYPES_ID,
                    or_(
                        and_(TrnTranslations.languageID == self.default_lang, conditions),
                        and_(TrnTranslations.languageID == "en", conditions)
                    )
                )
            )
            trans_results = await session.execute(trans_query)
            translations = trans_results.scalars().all()

            matched_type_ids = [trans.keyID for trans in translations]

            if not matched_type_ids:
                return {"total": 0, "items": []}

            types_query = select(InvTypes).where(InvTypes.typeID.in_(matched_type_ids))

            if market:
                types_query = types_query.where(
                    and_(
                        InvTypes.marketGroupID.is_not(None),
                        InvTypes.published == True
                    )
                )

            types_results = await session.execute(types_query)
            types = types_results.scalars().all()

            translations_map = {}
            for trans in translations:
                if trans.languageID == self.default_lang:
                    translations_map[trans.keyID] = trans.text

            items = []
            for type_item in types:
                items.append({
                    "typeID": type_item.typeID,
                    "typeName": type_item.typeName,
                    "transName": translations_map.get(type_item.typeID, type_item.typeName),
                    "marketGroupID": type_item.marketGroupID,
                    "groupID": type_item.groupID,
                })

            total = len(items)
            items = items[:limit]
            print(items)

            return {
                "total": total,
                "items": items
            }

    @classmethod
    async def _build_search_conditions(cls, text: str):
        """构建搜索条件，使用分词后的关键词进行模糊匹配"""
        tokens = await text_processor.tokenize(text)
        logger.debug(f"分词结果: {tokens}")

        if not tokens:
            return TrnTranslations.text.ilike(f"%{text}%")

        conditions = and_(*[TrnTranslations.text.ilike(f"%{token}%") for token in tokens])
        return conditions

    @classmethod
    @cache_result(prefix="inv_flags_", exclude_args=[0])
    async def get_flag_info(cls) -> dict | None:
        """
        获取所有槽位标识和名称

        Returns:
            槽位ID到名称的映射
        """
        try:
            async with await get_session() as session:
                result = await session.execute(select(InvFlags))
                flags = result.scalars().all()

                return {flag.flagID: flag.flagName for flag in flags}

        except Exception as e:
            logger.error(f"获取槽位信息失败: {e}")
            return None

    @classmethod
    @cache_result(prefix="type_name_", exclude_args=[0, 1])
    async def _get_type_name(cls, session, type_id: int | str) -> str | None:
        """获取物品名称"""
        query = select(InvTypes).where(InvTypes.typeID == type_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    @cache_result(prefix="type_trans_", exclude_args=[0, 1])
    async def _get_type_translation(cls, session, type_id: int | str, language: str) -> str | None:
        """获取指定语言的物品名称翻译"""
        query = select(TrnTranslations.text).where(
            and_(
                TrnTranslations.tcID == TC_TYPES_ID,
                TrnTranslations.keyID == type_id,
                TrnTranslations.languageID == language
            )
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_type_names(
            self,
            type_ids: list[int | str],
            language_id: str = None
    ) -> dict[int, dict[str, str]]:
        """
        批量获取多个物品的名称

        Args:
            type_ids: 物品ID列表
            language_id: 语言代码，如 'zh', 'en'，默认使用 self.default_lang

        Returns:
            物品ID到名称及翻译的映射字典
        """
        if language_id is None:
            language_id = self.default_lang

        if not type_ids:
            return {}

        int_type_ids = [int(type_id) for type_id in type_ids]

        result = {}
        async with await get_session() as session:
            inv_types_query = select(InvTypes).where(InvTypes.typeID.in_(int_type_ids))
            inv_types_result = await session.execute(inv_types_query)
            inv_types = {item.typeID: item for item in inv_types_result.scalars().all()}

            translations_query = select(TrnTranslations).where(
                and_(
                    TrnTranslations.tcID == TC_TYPES_ID,
                    TrnTranslations.keyID.in_(int_type_ids),
                    TrnTranslations.languageID == language_id
                )
            )
            translations_result = await session.execute(translations_query)
            translations = {item.keyID: item.text for item in translations_result.scalars().all()}

            for type_id in int_type_ids:
                if type_id in inv_types:
                    inv_type = inv_types[type_id]
                    result[type_id] = {
                        "typeName": inv_type.typeName,
                        "translation": translations.get(type_id, inv_type.typeName)
                    }

        return result

    @cache_result(prefix="type_group_", exclude_args=[0])
    async def get_type_group(self, type_id: int | str, language: str = 'zh') -> str | None:
        """
        从物品ID获取GROUP名称
        Args:
            type_id: 物品ID
            language: 语言 默认 zh
        Returns:
            GROUP名称 str 或 None
        """
        async with await get_session() as session:
            # 获取物品对应的组ID
            types_query = select(InvTypes.groupID).where(InvTypes.typeID == type_id)
            group_id_result = await session.execute(types_query)
            group_id = group_id_result.scalar_one_or_none()

            if group_id is None:
                return None

            # 获取组名称的翻译
            tns_query = select(TrnTranslations.text).where(
                and_(
                    TrnTranslations.tcID == TC_GROUP_ID,
                    TrnTranslations.keyID == group_id,
                    TrnTranslations.languageID == language
                )
            )
            group_name_result = await session.execute(tns_query)
            group_name = group_name_result.scalar_one_or_none()

            return group_name

sde_search = SDESearch()