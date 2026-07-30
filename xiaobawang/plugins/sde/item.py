from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import html
import math
import re
from typing import Any
import unicodedata

from sqlalchemy import and_, case, func, or_, select

from .config import plugin_config
from .db import get_session
from .models import (
    TC_CATEGORY_ID,
    TC_GROUP_ID,
    TC_TYPES_ID,
    DgmAttributeTypes,
    DgmEffects,
    DgmTypeAttributes,
    DgmTypeEffects,
    EveIcons,
    EveUnits,
    InvCategories,
    InvGroups,
    InvTraits,
    InvTypes,
    TrnTranslations,
)
from .utils import text_processor

TC_TYPE_DESCRIPTION_ID = 33
TC_UNIT_NAME_ID = 58
TC_ATTRIBUTE_NAME_ID = 59
SHIP_CATEGORY_ID = 6

REQUIRED_SKILL_ATTRIBUTES = dict(zip(range(182, 188), range(277, 283)))
SLOT_EFFECTS = {
    "hiPower": "高能量槽",
    "medPower": "中能量槽",
    "loPower": "低能量槽",
    "rigSlot": "改装件槽",
    "subSystem": "子系统槽",
    "serviceSlot": "服务槽",
}

ATTRIBUTE_LABELS_ZH = {
    "power": "能量栅格需求",
    "cpu": "CPU 需求",
    "powerOutput": "能量栅格输出",
    "cpuOutput": "CPU 输出",
    "speedFactor": "最大速度加成",
    "maxVelocity": "最大速度",
    "maxTargetRange": "锁定距离",
    "maxLockedTargets": "最大锁定目标数",
    "scanResolution": "扫描分辨率",
    "signatureRadius": "信号半径",
    "capacitorCapacity": "电容容量",
    "shieldCapacity": "护盾值",
    "shieldRechargeRate": "护盾回充时间",
    "armorHP": "装甲值",
    "hp": "结构值",
    "droneCapacity": "无人机挂舱容量",
    "droneBandwidth": "无人机带宽",
    "capacity": "容量",
    "volume": "体积",
    "mass": "质量",
    "duration": "持续时间",
    "optimalSigRadius": "最佳信号半径",
    "maxRange": "最佳射程",
    "falloff": "失准范围",
    "trackingSpeed": "跟踪速度",
    "damageMultiplier": "伤害倍率",
    "rateOfFire": "射击间隔",
    "capacitorNeed": "启用电容消耗",
    "armorEmDamageResonance": "装甲电磁伤害抗性",
    "armorThermalDamageResonance": "装甲热能伤害抗性",
    "armorKineticDamageResonance": "装甲动能伤害抗性",
    "armorExplosiveDamageResonance": "装甲爆炸伤害抗性",
    "shieldEmDamageResonance": "护盾电磁伤害抗性",
    "shieldThermalDamageResonance": "护盾热能伤害抗性",
    "shieldKineticDamageResonance": "护盾动能伤害抗性",
    "shieldExplosiveDamageResonance": "护盾爆炸伤害抗性",
    "emDamageResonance": "结构电磁伤害抗性",
    "thermalDamageResonance": "结构热能伤害抗性",
    "kineticDamageResonance": "结构动能伤害抗性",
    "explosiveDamageResonance": "结构爆炸伤害抗性",
    "armorEmDamageResistanceBonus": "装甲电磁伤害抗性加成",
    "armorThermalDamageResistanceBonus": "装甲热能伤害抗性加成",
    "armorKineticDamageResistanceBonus": "装甲动能伤害抗性加成",
    "armorExplosiveDamageResistanceBonus": "装甲爆炸伤害抗性加成",
    "shieldEmDamageResistanceBonus": "护盾电磁伤害抗性加成",
    "shieldThermalDamageResistanceBonus": "护盾热能伤害抗性加成",
    "shieldKineticDamageResistanceBonus": "护盾动能伤害抗性加成",
    "shieldExplosiveDamageResistanceBonus": "护盾爆炸伤害抗性加成",
    "maxTargetRangeBonus": "锁定距离加成",
    "scanResolutionBonus": "扫描分辨率加成",
    "signatureRadiusBonus": "信号半径加成",
    "maxVelocityBonus": "最大速度加成",
    "agilityBonus": "惯性调整加成",
    "droneVelocityBonus": "无人机速度加成",
    "droneDamageBonus": "无人机伤害加成",
    "droneHitpointsBonus": "无人机生命值加成",
}

GENERIC_ATTRIBUTE_EXCLUSIONS = {
    "damage",
    "hp",
    "techLevel",
    "metaLevelOld",
    "metaGroupID",
    "uniformity",
    "capacity",
    "mass",
    "volume",
}

_TAG_RE = re.compile(r"<[^>]+>")
_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def relevance_score(query: str, names: list[str]) -> float:
    """Return a deterministic relevance score for localized EVE type names."""
    query_normalised = _normalise(query)
    if not query_normalised:
        return 0

    best = 0.0
    query_tokens = set(query_normalised.split())
    for name in names:
        candidate = _normalise(name)
        if not candidate:
            continue
        if candidate == query_normalised:
            score = 10_000.0
        elif candidate.startswith(query_normalised):
            score = 8_000.0 - (len(candidate) - len(query_normalised))
        elif query_normalised in candidate:
            score = 6_000.0 - (len(candidate) - len(query_normalised))
        else:
            candidate_tokens = set(candidate.split())
            coverage = len(query_tokens & candidate_tokens) / max(1, len(query_tokens))
            similarity = SequenceMatcher(None, query_normalised, candidate).ratio()
            score = coverage * 3_000.0 + similarity * 1_000.0
        best = max(best, score)
    return best


def _number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    numeric = float(value)
    if numeric.is_integer():
        return f"{int(numeric):,}"
    return f"{numeric:,.{digits}f}".rstrip("0").rstrip(".")


def _duration(milliseconds: float) -> str:
    seconds = float(milliseconds) / 1000
    if seconds >= 60:
        minutes, remaining = divmod(round(seconds), 60)
        return f"{minutes}分 {remaining:02d}秒" if remaining else f"{minutes}分"
    return f"{_number(seconds)}秒"


def _distance(metres: float) -> str:
    metres = float(metres)
    if abs(metres) >= 1000:
        return f"{_number(metres / 1000)} km"
    return f"{_number(metres)} m"


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = _TAG_RE.sub("", value)
    value = html.unescape(value)
    value = "\n".join(line.strip() for line in value.splitlines())
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _ship_packaged_volume(group_name: str) -> float | None:
    """Return the standard packaged volume used by common ship size groups."""
    group_name = group_name.casefold()
    rules = (
        (("shuttle", "capsule"), 500),
        (("frigate", "corvette"), 2_500),
        (("destroyer",), 5_000),
        (("battlecruiser",), 15_000),
        (("cruiser",), 10_000),
        (("battleship",), 50_000),
    )
    return next((volume for names, volume in rules if any(name in group_name for name in names)), None)


def _attribute_label(attribute_name: str, translated_name: str | None = None) -> str:
    if translated_name:
        return translated_name
    if attribute_name in ATTRIBUTE_LABELS_ZH:
        return ATTRIBUTE_LABELS_ZH[attribute_name]
    semantic_words = (
        ("shield", "护盾"),
        ("armor", "装甲"),
        ("hull", "结构"),
        ("structure", "结构"),
        ("em", "电磁"),
        ("thermal", "热能"),
        ("kinetic", "动能"),
        ("explosive", "爆炸"),
        ("damage", "伤害"),
        ("resonance", "抗性"),
        ("resistance", "抗性"),
        ("velocity", "速度"),
        ("range", "射程"),
        ("duration", "持续时间"),
        ("bonus", "加成"),
        ("multiplier", "倍率"),
    )
    words = _CAMEL_RE.sub(" ", attribute_name).replace("_", " ").strip()
    translated_words = []
    for word in words.split():
        translated_words.append(next((zh for en, zh in semantic_words if word.casefold() == en), word))
    return "".join(translated_words)


def _icon_url(icon_file: str | None) -> str | None:
    if not icon_file:
        return None
    filename = icon_file.replace("\\", "/").rsplit("/", 1)[-1]
    return f"./src/{filename}"


def _format_attribute(
    attribute_name: str,
    value: float,
    unit_id: int | None,
    unit_name: str | None,
) -> str:
    if unit_id == 101:
        return _duration(value)
    if unit_id == 1:
        return _distance(value)
    if unit_id == 108 and "DamageResonance" in attribute_name:
        return f"{_number((1 - float(value)) * 100)}%"
    if unit_id in {105, 109, 111, 121, 124, 127, 139}:
        return f"{_number(value)}%"
    if unit_id == 104:
        return f"{_number(value)}×"
    unit = unit_name or ""
    return f"{_number(value)}{f' {unit}' if unit else ''}"


def _translate_trait(text: str) -> str:
    text = _plain_text(text)
    replacements = (
        ("Can fit ", "可装配"),
        ("reduction in ", "降低"),
        ("bonus to ", "加成："),
        (" penalty", "惩罚"),
        ("Small Energy Turret", "小型能量炮台"),
        ("Small Hybrid Turret", "小型混合炮台"),
        ("Small Projectile Turret", "小型射弹炮台"),
        ("Microwarpdrive", "微型跃迁推进器"),
        ("signature radius", "信号半径"),
        ("activation cost", "启用电容消耗"),
        ("rate of fire", "射速"),
        ("optimal range", "最佳射程"),
        ("falloff", "失准范围"),
        ("damage", "伤害"),
        ("Assault Damage Controls", "突击型损伤控制"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text


class ItemLookup:
    async def find_most_relevant(self, query: str) -> dict[str, Any] | None:
        query = query.strip()
        if not query:
            return None

        tokens = [token for token in await text_processor.tokenize(query) if token.strip()]
        token_conditions = [TrnTranslations.text.ilike(f"%{token}%") for token in tokens]
        search_condition = or_(
            TrnTranslations.text.ilike(f"%{query}%"),
            and_(*token_conditions) if token_conditions else TrnTranslations.text.ilike(f"%{query}%"),
        )

        async with await get_session() as session:
            priority = case(
                (func.lower(TrnTranslations.text) == query.casefold(), 0),
                (func.lower(TrnTranslations.text).like(f"{query.casefold()}%"), 1),
                else_=2,
            )
            candidates_query = (
                select(InvTypes)
                .join(TrnTranslations, TrnTranslations.keyID == InvTypes.typeID)
                .where(
                    and_(
                        TrnTranslations.tcID == TC_TYPES_ID,
                        TrnTranslations.languageID.in_({plugin_config.sde_default_language, "en"}),
                        search_condition,
                        InvTypes.published.is_(True),
                    )
                )
                .order_by(priority, InvTypes.typeID)
                .limit(500)
            )
            candidates = (await session.execute(candidates_query)).scalars().unique().all()
            if not candidates:
                return None

            type_ids = [item.typeID for item in candidates]
            names_query = select(TrnTranslations).where(
                and_(
                    TrnTranslations.tcID == TC_TYPES_ID,
                    TrnTranslations.keyID.in_(type_ids),
                    TrnTranslations.languageID.in_({plugin_config.sde_default_language, "en"}),
                )
            )
            translations = (await session.execute(names_query)).scalars().all()
            names: dict[int, dict[str, str]] = defaultdict(dict)
            for translation in translations:
                names[translation.keyID][translation.languageID] = translation.text

            best = max(
                candidates,
                key=lambda item: (
                    relevance_score(query, [item.typeName, *names[item.typeID].values()]),
                    -len(names[item.typeID].get(plugin_config.sde_default_language, item.typeName)),
                    -item.typeID,
                ),
            )
            return await self._get_details(session, best.typeID)

    async def _translations(
        self,
        session,
        tc_id: int,
        key_ids: list[int],
        language: str | None = None,
    ) -> dict[int, str]:
        if not key_ids:
            return {}
        result = await session.execute(
            select(TrnTranslations).where(
                and_(
                    TrnTranslations.tcID == tc_id,
                    TrnTranslations.keyID.in_(key_ids),
                    TrnTranslations.languageID == (language or plugin_config.sde_default_language),
                )
            )
        )
        return {row.keyID: row.text for row in result.scalars().all()}

    async def _required_skills(self, session, type_id: int) -> list[dict[str, Any]]:
        requirements: dict[int, dict[str, int]] = {}
        queue: list[tuple[int, int]] = [(type_id, 0)]
        visited: set[int] = set()

        while queue:
            parent_id, depth = queue.pop(0)
            if parent_id in visited or depth > 5:
                continue
            visited.add(parent_id)
            result = await session.execute(
                select(DgmTypeAttributes).where(
                    and_(
                        DgmTypeAttributes.typeID == parent_id,
                        DgmTypeAttributes.attributeID.in_(
                            {*REQUIRED_SKILL_ATTRIBUTES, *REQUIRED_SKILL_ATTRIBUTES.values()}
                        ),
                    )
                )
            )
            values = {
                row.attributeID: row.valueInt if row.valueInt is not None else row.valueFloat
                for row in result.scalars().all()
            }
            for skill_attribute, level_attribute in REQUIRED_SKILL_ATTRIBUTES.items():
                skill_id = int(values.get(skill_attribute) or 0)
                if not skill_id:
                    continue
                level = int(values.get(level_attribute) or 0)
                existing = requirements.setdefault(skill_id, {"level": level, "depth": depth})
                existing["level"] = max(existing["level"], level)
                existing["depth"] = min(existing["depth"], depth)
                queue.append((skill_id, depth + 1))

        skill_names = await self._translations(session, TC_TYPES_ID, list(requirements))
        return [
            {
                "type_id": skill_id,
                "name": skill_names.get(skill_id, f"技能 {skill_id}"),
                "level": data["level"],
                "level_marks": "■" * data["level"] + "□" * (5 - data["level"]),
                "depth": data["depth"],
            }
            for skill_id, data in requirements.items()
        ]

    async def _get_details(self, session, type_id: int) -> dict[str, Any] | None:
        item_query = (
            select(InvTypes, InvGroups, InvCategories)
            .join(InvGroups, InvTypes.groupID == InvGroups.groupID)
            .join(InvCategories, InvGroups.categoryID == InvCategories.categoryID)
            .where(InvTypes.typeID == type_id)
        )
        row = (await session.execute(item_query)).one_or_none()
        if row is None:
            return None
        item, group, category = row
        packaged_volume = _ship_packaged_volume(group.groupName) if category.categoryID == SHIP_CATEGORY_ID else None

        localized_name = await self._translations(session, TC_TYPES_ID, [type_id])
        localized_description = await self._translations(session, TC_TYPE_DESCRIPTION_ID, [type_id])
        localized_group = await self._translations(session, TC_GROUP_ID, [group.groupID])
        localized_category = await self._translations(session, TC_CATEGORY_ID, [category.categoryID])

        attributes_query = (
            select(DgmTypeAttributes, DgmAttributeTypes, EveUnits, EveIcons)
            .join(DgmAttributeTypes, DgmTypeAttributes.attributeID == DgmAttributeTypes.attributeID)
            .outerjoin(EveUnits, DgmAttributeTypes.unitID == EveUnits.unitID)
            .outerjoin(EveIcons, DgmAttributeTypes.iconID == EveIcons.iconID)
            .where(DgmTypeAttributes.typeID == type_id)
        )
        attribute_rows = (await session.execute(attributes_query)).all()
        attribute_ids = [metadata.attributeID for _, metadata, _, _ in attribute_rows]
        unit_ids = [unit.unitID for _, _, unit, _ in attribute_rows if unit]
        localized_attributes = await self._translations(session, TC_ATTRIBUTE_NAME_ID, attribute_ids)
        localized_units = await self._translations(session, TC_UNIT_NAME_ID, unit_ids)

        attributes: dict[str, dict[str, Any]] = {}
        for value_row, metadata, unit, icon in attribute_rows:
            value = value_row.valueInt if value_row.valueInt is not None else value_row.valueFloat
            attributes[metadata.attributeName] = {
                "id": metadata.attributeID,
                "name": metadata.attributeName,
                "label": _attribute_label(metadata.attributeName, localized_attributes.get(metadata.attributeID)),
                "value": value,
                "formatted": _format_attribute(
                    metadata.attributeName,
                    value,
                    metadata.unitID,
                    localized_units.get(metadata.unitID) or (unit.displayName if unit else None),
                ),
                "unit_id": metadata.unitID,
                "category_id": metadata.categoryID,
                "published": bool(metadata.published),
                "icon_url": _icon_url(icon.iconFile if icon else None),
            }

        details: dict[str, Any] = {
            "type_id": type_id,
            "name": localized_name.get(type_id, item.typeName),
            "name_en": item.typeName,
            "description": _plain_text(localized_description.get(type_id, item.description)),
            "group": localized_group.get(group.groupID, group.groupName),
            "category": localized_category.get(category.categoryID, category.categoryName),
            "category_id": category.categoryID,
            "is_ship": category.categoryID == SHIP_CATEGORY_ID,
            "volume": f"{_number(item.volume)} m³" if item.volume is not None else None,
            "packaged_volume": f"{_number(packaged_volume)} m³" if packaged_volume is not None else None,
            "mass": f"{_number(item.mass)} kg" if item.mass is not None else None,
            "capacity": f"{_number(item.capacity)} m³" if item.capacity is not None else None,
            "skills": await self._required_skills(session, type_id),
        }

        if details["is_ship"]:
            await self._add_ship_details(session, details, attributes)
        else:
            await self._add_item_details(session, details, attributes, type_id)
        return details

    async def _add_ship_details(self, session, details: dict[str, Any], attrs: dict[str, dict[str, Any]]) -> None:
        traits = (
            (await session.execute(select(InvTraits).where(InvTraits.typeID == details["type_id"]))).scalars().all()
        )
        trait_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for trait in traits:
            trait_groups[trait.skillID or -1].append(
                {
                    "bonus": f"{_number(abs(trait.bonus))}%" if trait.bonus is not None else None,
                    "text": _translate_trait(trait.bonusText),
                }
            )
        skill_ids = [skill_id for skill_id in trait_groups if skill_id > 0]
        skill_names = await self._translations(session, TC_TYPES_ID, skill_ids)
        details["traits"] = [
            {
                "title": "基础加成" if skill_id == -1 else f"{skill_names.get(skill_id, str(skill_id))}加成（每级）",
                "items": bonuses,
            }
            for skill_id, bonuses in trait_groups.items()
        ]

        def raw(name: str, default: float = 0) -> float:
            return float((attrs.get(name) or {}).get("value") or default)

        def formatted(name: str) -> str | None:
            return (attrs.get(name) or {}).get("formatted")

        shield_hp = raw("shieldCapacity")
        shield_recharge_ms = raw("shieldRechargeRate")
        capacitor = raw("capacitorCapacity")
        capacitor_recharge_ms = raw("rechargeRate")

        details["defences"] = [
            {
                "title": "护盾",
                "hp": formatted("shieldCapacity"),
                "icon_url": (attrs.get("shieldCapacity") or {}).get("icon_url"),
                "uniformity": _number((1 - raw("shieldUniformity", 1)) * 100),
                "recharge": _duration(shield_recharge_ms) if shield_recharge_ms else None,
                "peak": (
                    f"{_number(2.5 * shield_hp / (shield_recharge_ms / 1000), 3)} HP/s"
                    if shield_hp and shield_recharge_ms
                    else None
                ),
                "resists": self._resists(attrs, "shield"),
            },
            {
                "title": "装甲",
                "hp": formatted("armorHP"),
                "icon_url": (attrs.get("armorHP") or {}).get("icon_url"),
                "uniformity": _number((1 - raw("armorUniformity", 1)) * 100),
                "resists": self._resists(attrs, "armor"),
            },
            {
                "title": "结构",
                "hp": formatted("hp"),
                "icon_url": (attrs.get("hp") or {}).get("icon_url"),
                "uniformity": _number((1 - raw("structureUniformity", 1)) * 100),
                "resists": self._resists(attrs, "hull"),
            },
        ]

        slots = [
            ("炮台", raw("turretSlotsLeft"), "个"),
            ("发射器", raw("launcherSlotsLeft"), "个"),
            ("高能量槽", raw("hiSlots"), "个"),
            ("中能量槽", raw("medSlots"), "个"),
            ("低能量槽", raw("lowSlots"), "个"),
            ("改装件槽", raw("rigSlots") or raw("upgradeSlotsLeft"), "个"),
        ]
        details["fitting"] = [
            {"label": label, "value": f"{_number(value)}{unit}"} for label, value, unit in slots if value
        ]
        details["fitting"].extend(
            item
            for item in (
                {"label": "CPU 输出", "value": formatted("cpuOutput")},
                {"label": "能量栅格输出", "value": formatted("powerOutput")},
                {"label": "电容容量", "value": formatted("capacitorCapacity")},
                {
                    "label": "电容回充",
                    "value": _duration(capacitor_recharge_ms) if capacitor_recharge_ms else None,
                },
                {
                    "label": "峰值电容回充",
                    "value": (
                        f"{_number(2.5 * capacitor / (capacitor_recharge_ms / 1000), 3)} GJ/s"
                        if capacitor and capacitor_recharge_ms
                        else None
                    ),
                },
                {"label": "信号半径", "value": formatted("signatureRadius")},
            )
            if item["value"]
        )

        mass = float(str(details["mass"]).replace(",", "").split()[0]) if details.get("mass") else 0
        agility = raw("agility")
        align_time = math.ceil(-math.log(0.25) * mass * agility / 1_000_000) if mass and agility else None
        warp_speed = raw("baseWarpSpeed") * raw("warpSpeedMultiplier", 1)
        details["propulsion"] = [
            {"label": "最大速度", "value": formatted("maxVelocity")},
            {"label": "对齐时间", "value": f"{align_time}秒" if align_time else None},
            {"label": "跃迁速度", "value": f"{_number(warp_speed)} AU/s" if warp_speed else None},
        ]

        sensor_names = (
            ("scanRadarStrength", "雷达"),
            ("scanLadarStrength", "光雷达"),
            ("scanMagnetometricStrength", "磁力"),
            ("scanGravimetricStrength", "引力"),
        )
        sensor_type, sensor_strength = next(
            ((label, raw(name)) for name, label in sensor_names if raw(name)),
            (None, 0),
        )
        details["sensors"] = [
            {"label": "锁定距离", "value": formatted("maxTargetRange")},
            {"label": "扫描分辨率", "value": formatted("scanResolution")},
            {"label": "最大锁定目标", "value": formatted("maxLockedTargets")},
            {
                "label": "传感器",
                "value": f"{sensor_type} / {_number(sensor_strength)} 点" if sensor_type else None,
            },
        ]

    @staticmethod
    def _resists(attrs: dict[str, dict[str, Any]], layer: str) -> list[dict[str, Any]]:
        names = {
            "shield": {
                "em": ("电磁", "shieldEmDamageResonance"),
                "thermal": ("热能", "shieldThermalDamageResonance"),
                "kinetic": ("动能", "shieldKineticDamageResonance"),
                "explosive": ("爆炸", "shieldExplosiveDamageResonance"),
            },
            "armor": {
                "em": ("电磁", "armorEmDamageResonance"),
                "thermal": ("热能", "armorThermalDamageResonance"),
                "kinetic": ("动能", "armorKineticDamageResonance"),
                "explosive": ("爆炸", "armorExplosiveDamageResonance"),
            },
            "hull": {
                "em": ("电磁", "emDamageResonance"),
                "thermal": ("热能", "thermalDamageResonance"),
                "kinetic": ("动能", "kineticDamageResonance"),
                "explosive": ("爆炸", "explosiveDamageResonance"),
            },
        }
        return [
            {
                "kind": kind,
                "label": label,
                "value": attrs[name]["formatted"],
                "percent": max(0, min(100, round((1 - float(attrs[name]["value"])) * 100, 2))),
                "icon_url": attrs[name]["icon_url"],
            }
            for kind, (label, name) in names[layer].items()
            if name in attrs
        ]

    async def _add_item_details(
        self,
        session,
        details: dict[str, Any],
        attrs: dict[str, dict[str, Any]],
        type_id: int,
    ) -> None:
        effects_query = (
            select(DgmEffects)
            .join(DgmTypeEffects, DgmEffects.effectID == DgmTypeEffects.effectID)
            .where(DgmTypeEffects.typeID == type_id)
        )
        effects = (await session.execute(effects_query)).scalars().all()
        slots = [SLOT_EFFECTS[effect.effectName] for effect in effects if effect.effectName in SLOT_EFFECTS]

        fitting = [{"label": "槽位", "value": slot} for slot in slots]
        for name in ("cpu", "power", "upgradeCost", "capacitorNeed"):
            if name in attrs:
                fitting.append(
                    {
                        "label": attrs[name]["label"],
                        "value": attrs[name]["formatted"],
                        "icon_url": attrs[name]["icon_url"],
                    }
                )
        details["fitting"] = fitting

        details["attributes"] = [
            {"label": attr["label"], "value": attr["formatted"], "icon_url": attr["icon_url"]}
            for name, attr in attrs.items()
            if attr["published"]
            and name not in GENERIC_ATTRIBUTE_EXCLUSIONS
            and not name.startswith(("requiredSkill", "canFitShip"))
            and attr["category_id"] not in {1, 4, 7, 8, 9, 31, 36, 52}
        ]


item_lookup = ItemLookup()
