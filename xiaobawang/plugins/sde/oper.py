
from nonebot import logger
from sqlalchemy import and_, or_, select

from .cache import cache_result
from .config import plugin_config
from .db import get_session
from .models import TC_GROUP_ID, TC_TYPES_ID, InvFlags, InvTypes, TrnTranslations
from .utils import text_processor


class SDESearch:
    def __init__(self):
        self.default_lang = plugin_config.sde_default_language

    @cache_result(prefix="type_search_", exclude_args=[0])
    async def search_item_by_name(self, name: str, market: bool = True, limit: int = 1000):
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
                        and_(TrnTranslations.languageID == "en", conditions),
                    ),
                )
            )
            trans_results = await session.execute(trans_query)
            translations = trans_results.scalars().all()

            matched_type_ids = [trans.keyID for trans in translations]

            if not matched_type_ids:
                return {"total": 0, "items": []}

            types_query = select(InvTypes).where(InvTypes.typeID.in_(matched_type_ids))

            if market:
                types_query = types_query.where(and_(InvTypes.marketGroupID.is_not(None), InvTypes.published.is_(True)))

            types_results = await session.execute(types_query)
            types = types_results.scalars().all()

            translations_map = {}
            for trans in translations:
                if trans.languageID == self.default_lang:
                    translations_map[trans.keyID] = trans.text

            items = []
            for type_item in types:
                items.append(
                    {
                        "typeID": type_item.typeID,
                        "typeName": type_item.typeName,
                        "transName": translations_map.get(type_item.typeID, type_item.typeName),
                        "marketGroupID": type_item.marketGroupID,
                        "groupID": type_item.groupID,
                    }
                )

            total = len(items)
            items = items[:limit]

            return {"total": total, "items": items}

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
                TrnTranslations.languageID == language,
            )
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_type_names(
        self, type_ids: list[int | str], language_id: str | None = None
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
                    TrnTranslations.languageID == language_id,
                )
            )
            translations_result = await session.execute(translations_query)
            translations = {item.keyID: item.text for item in translations_result.scalars().all()}

            for type_id in int_type_ids:
                if type_id in inv_types:
                    inv_type = inv_types[type_id]
                    result[type_id] = {
                        "typeName": inv_type.typeName,
                        "translation": translations.get(type_id, inv_type.typeName),
                    }

        return result

    @cache_result(prefix="type_group_", exclude_args=[0])
    async def get_type_group(self, type_id: int | str, language: str = "zh", _id: bool = False) -> str | int | None:
        """
        从物品ID获取GROUP名称
        Args:
            type_id: 物品ID
            language: 语言 默认 zh
            _id: 返回group_id
        Returns:
            GROUP名称 str 或 None 或 int
        """
        async with await get_session() as session:
            # 获取物品对应的组ID
            types_query = select(InvTypes.groupID).where(InvTypes.typeID == type_id)
            group_id_result = await session.execute(types_query)
            group_id = group_id_result.scalar_one_or_none()

            if group_id is None:
                return None

            if _id:
                return group_id

            # 获取组名称的翻译
            tns_query = select(TrnTranslations.text).where(
                and_(
                    TrnTranslations.tcID == TC_GROUP_ID,
                    TrnTranslations.keyID == group_id,
                    TrnTranslations.languageID == language,
                )
            )
            group_name_result = await session.execute(tns_query)
            group_name = group_name_result.scalar_one_or_none()

            return group_name

    @cache_result(prefix="fuzzy_search_", exclude_args=[0])
    async def trans_items(
        self, search_item: str, limit: int = 10, source_lang: str | None = None, target_lang: str = "en"
    ) -> tuple[list[dict], int]:
        """
        根据输入词查找最相似的物品，支持中英文互转

        Args:
            search_item: 搜索词
            limit: 返回结果数量限制
            source_lang: 源语言，默认为None，自动检测
            target_lang: 目标语言，默认英文

        Returns:
            最相似物品列表，包含原文和翻译
        """
        if not search_item:
            return [], 0

        if source_lang is None:
            source_lang = "zh" if text_processor._contains_chinese(search_item) else "en"

        if target_lang == source_lang:
            target_lang = "en" if source_lang == "zh" else "zh"

        tokens = await text_processor.tokenize(search_item)

        async with await get_session() as session:
            conditions = and_(*[TrnTranslations.text.ilike(f"%{token}%") for token in tokens])

            source_query = select(TrnTranslations).where(
                and_(TrnTranslations.tcID == TC_TYPES_ID, TrnTranslations.languageID == source_lang, conditions)
            )
            source_results = await session.execute(source_query)
            source_translations = source_results.scalars().all()

            if not source_translations:
                return [], 0

            matched_type_ids = [trans.keyID for trans in source_translations]

            source_map = {trans.keyID: trans.text for trans in source_translations}

            target_query = select(TrnTranslations).where(
                and_(
                    TrnTranslations.tcID == TC_TYPES_ID,
                    TrnTranslations.languageID == target_lang,
                    TrnTranslations.keyID.in_(matched_type_ids),
                )
            )
            target_results = await session.execute(target_query)
            target_translations = target_results.scalars().all()

            target_map = {trans.keyID: trans.text for trans in target_translations}

            types_query = select(InvTypes).where(
                # and_(InvTypes.typeID.in_(matched_type_ids), InvTypes.published.is True)
                and_(InvTypes.typeID.in_(matched_type_ids), InvTypes.published.is_(True))
            )
            types_results = await session.execute(types_query)
            types = types_results.scalars().all()

            results = []
            for type_item in types:
                type_id = type_item.typeID
                source_text = source_map.get(type_id)
                target_text = target_map.get(type_id)

                if source_text and target_text:
                    score = sum(1 for token in tokens if token.lower() in source_text.lower())

                    results.append(
                        {
                            "typeID": type_id,
                            "typeName": type_item.typeName,
                            "source": {"lang": source_lang, "text": source_text},
                            "translation": {"lang": target_lang, "text": target_text},
                            "score": score,
                        }
                    )

            results.sort(key=lambda x: x["score"], reverse=True)
            total = len(results)
        return results[:limit], total


sde_search = SDESearch()
