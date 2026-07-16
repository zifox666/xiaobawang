"""
建筑通知服务层 - 负责 ESI 拉取、数据库存储和推送逻辑
"""

from datetime import datetime, timezone
from html import unescape
import json
import re
from typing import Any

import httpx
from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select
import yaml

from ..cache import get_cache
from ..core.api.esi.universe import esi_client
from ..eve_oauth.api import get_access_token, require_scopes
from .categories import ALL_STRUCTURE_TYPES, get_type_label
from .config import plugin_config
from .models import StructureNotificationRecord, StructureNotificationSub

# 注册本插件所需的 ESI scopes
require_scopes("structure_notifications", [
    "esi-characters.read_notifications.v1",
    "esi-universe.read_structures.v1",
])

cache = get_cache("structure_notifications")

ESI_NOTIFICATIONS_URL = "https://esi.evetech.net/characters/{character_id}/notifications/"

INTERNAL_LINK_KEYS = {
    "allianceLinkData",
    "corpLinkData",
    "ownerCorpLinkData",
    "structureShowInfoData",
}

FIELD_LABELS: dict[str, str] = {
    "aggressorAllianceID": "攻击方联盟",
    "aggressorCorpID": "攻击方军团",
    "aggressorID": "攻击者",
    "allianceID": "联盟",
    "allianceName": "联盟名称",
    "allStructureInfo": "建筑列表",
    "armorPercentage": "装甲",
    "armorValue": "装甲",
    "assetSafetyDurationFull": "资产安全完整时间",
    "assetSafetyDurationMinimum": "资产安全最短时间",
    "assetSafetyFullTimestamp": "资产安全完整时间点",
    "assetSafetyMinimumTimestamp": "资产安全最短时间点",
    "autoTime": "自动裂解时间",
    "campaignEventType": "战役事件类型",
    "cancelledBy": "取消者",
    "charID": "角色",
    "constellationID": "星座",
    "corpID": "军团",
    "corpName": "军团名称",
    "daysUntilAbandon": "废弃剩余天数",
    "decloakTime": "显形时间",
    "destructTime": "自毁时间",
    "durationSeconds": "持续秒数",
    "firedBy": "发射者",
    "firedByLink": "发射者链接",
    "hour": "小时",
    "hullPercentage": "结构",
    "hullValue": "结构",
    "isAbandoned": "是否废弃",
    "isCorpOwned": "是否军团拥有",
    "issuedAt": "购买时间",
    "listOfServiceModuleIDs": "服务模块",
    "listOfTypesAndQty": "类型与数量",
    "lpAmount": "LP 数量",
    "moonID": "卫星 ID",
    "newOwnerCorpID": "新拥有军团",
    "newStationID": "新空间站",
    "numStructures": "建筑数量",
    "oldOwnerCorpID": "原拥有军团",
    "oreVolumeByType": "矿石体积",
    "ownerCorpName": "拥有军团",
    "purchasedByCharacterID": "购买角色",
    "readyTime": "就绪时间",
    "shieldPercentage": "护盾",
    "shieldValue": "护盾",
    "solarSystemID": "星系",
    "solarsystemID": "星系",
    "startedBy": "启动者",
    "startedByLink": "启动者链接",
    "structureID": "建筑",
    "structureIDs": "建筑",
    "structureName": "建筑名称",
    "structureTypeID": "建筑类型",
    "timestamp": "时间戳",
    "timeLeft": "剩余时间",
    "typeID": "类型",
    "vulnerableTime": "可攻击时间",
    "wants": "需求",
    "weekday": "星期",
}

IMPLICIT_ID_KEYS = {
    "cancelledBy",
    "firedBy",
    "startedBy",
}

STRUCTURE_ID_KEYS = {
    "structureID",
    "structureIDs",
}

ID_KEY_RE = re.compile(r"(?:^|[A-Z_])(id|ids)$", re.IGNORECASE)
SHOWINFO_RE = re.compile(r"<a\s+href=\"\"showinfo:(\d+)//(\d+)\"\">(.*?)</a>", re.IGNORECASE | re.DOTALL)


# ── 订阅 CRUD ──────────────────────────────────────────────

async def get_subscriptions_by_character(character_id: int) -> list[StructureNotificationSub]:
    async with get_session() as session:
        result = await session.execute(
            select(StructureNotificationSub).where(
                StructureNotificationSub.character_id == character_id
            )
        )
        return list(result.scalars().all())


async def get_all_enabled_subscriptions() -> list[StructureNotificationSub]:
    async with get_session() as session:
        result = await session.execute(
            select(StructureNotificationSub).where(
                StructureNotificationSub.is_enabled.is_(True)
            )
        )
        return list(result.scalars().all())


async def create_subscription(
    character_id: int,
    character_name: str,
    platform: str,
    bot_id: str,
    session_id: str,
    session_type: str,
    categories: list[str],
) -> StructureNotificationSub:
    async with get_session() as session:
        sub = StructureNotificationSub(
            character_id=character_id,
            character_name=character_name,
            platform=platform,
            bot_id=bot_id,
            session_id=session_id,
            session_type=session_type,
            categories=json.dumps(categories),
            is_enabled=True,
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


async def update_subscription(sub_id: int, **kwargs) -> StructureNotificationSub | None:
    async with get_session() as session:
        result = await session.execute(
            select(StructureNotificationSub).where(StructureNotificationSub.id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            return None
        for key, value in kwargs.items():
            if key == "categories" and isinstance(value, list):
                value = json.dumps(value)
            setattr(sub, key, value)
        await session.commit()
        await session.refresh(sub)
        return sub


async def delete_subscription(sub_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(StructureNotificationSub).where(StructureNotificationSub.id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            return False
        await session.delete(sub)
        await session.commit()
        return True


# ── ESI 拉取 ──────────────────────────────────────────────

async def fetch_notifications(character_id: int) -> list[dict]:
    """从 ESI 拉取角色通知, 仅返回建筑相关类型"""
    try:
        token_info = await get_access_token(
            character_id,
            required_scopes=["esi-characters.read_notifications.v1"],
        )
    except ValueError as e:
        logger.warning(f"获取角色 {character_id} access_token 失败: {e}")
        return []

    access_token = token_info["access_token"]
    url = ESI_NOTIFICATIONS_URL.format(character_id=character_id)
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "X-Compatibility-Date": "2025-12-16",
    }

    proxy = plugin_config.structure_notify_proxy
    try:
        async with httpx.AsyncClient(timeout=20, proxy=proxy) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 304:
                return []
            resp.raise_for_status()
            notifications = resp.json()
    except Exception as e:
        logger.error(f"ESI 拉取通知失败 (角色 {character_id}): {e}")
        return []

    # 只保留建筑相关类型
    return [n for n in notifications if n.get("type") in ALL_STRUCTURE_TYPES]


async def save_notifications(character_id: int, notifications: list[dict]) -> list[StructureNotificationRecord]:
    """将通知存入数据库, 返回新增的记录"""
    if not notifications:
        return []

    new_records: list[StructureNotificationRecord] = []
    async with get_session() as session:
        for n in notifications:
            nid = n["notification_id"]
            # 检查是否已存在
            existing = await session.execute(
                select(StructureNotificationRecord).where(
                    StructureNotificationRecord.notification_id == nid,
                    StructureNotificationRecord.character_id == character_id,
                )
            )
            if existing.scalar_one_or_none():
                continue

            ts = n.get("timestamp", "")
            if isinstance(ts, str):
                try:
                    ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    ts_dt = datetime.now(tz=timezone.utc)
            else:
                ts_dt = datetime.now(tz=timezone.utc)

            record = StructureNotificationRecord(
                notification_id=nid,
                character_id=character_id,
                notification_type=n.get("type", ""),
                sender_id=n.get("sender_id", 0),
                sender_type=n.get("sender_type", ""),
                text=n.get("text", ""),
                timestamp=ts_dt,
                pushed=False,
            )
            session.add(record)
            new_records.append(record)

        if new_records:
            await session.commit()
            for r in new_records:
                await session.refresh(r)

    return new_records


# ── 推送格式化 ─────────────────────────────────────────────

async def format_notification(record: StructureNotificationRecord, character_name: str = "") -> str:
    """将一条通知格式化为推送文本"""
    label = get_type_label(record.notification_type)
    ts_str = record.timestamp.strftime("%Y-%m-%d %H:%M:%S") if record.timestamp else ""

    lines = [f"{label}"]
    lines.append(f"时间: {ts_str}")

    # 尝试解析 text 字段中的关键信息
    if record.text:
        parsed = await _parse_notification_text(record.text, record.character_id)
        if parsed:
            lines.append(parsed)

    return "\n".join(lines)


async def _parse_notification_text(text: str, character_id: int) -> str:
    """从 ESI YAML-like text 中解析全部可读字段，并批量解析 ID 名称。"""
    if not text:
        return ""

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        logger.warning(f"建筑通知 text 解析失败，回退原始行解析: {e}")
        data = _parse_text_fallback(text)

    if not isinstance(data, dict):
        return text.strip()

    ids = sorted(_collect_lookup_ids(data))
    structure_ids = sorted(_collect_structure_ids(data))
    names = await _get_id_names(ids)
    names.update(await _get_structure_names(structure_ids, character_id))

    lines: list[str] = []
    for key, value in data.items():
        if key in INTERNAL_LINK_KEYS or key.endswith("LinkData"):
            continue
        formatted = _format_field(key, value, names)
        if formatted:
            lines.extend(formatted)
    return "\n".join(lines)


def _parse_text_fallback(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in text.strip().splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        data[key.strip()] = val.strip()
    return data


def _collect_lookup_ids(value: Any, key: str | None = None) -> set[int]:
    ids: set[int] = set()
    if isinstance(value, dict):
        if key == "oreVolumeByType":
            for child_key in value:
                try:
                    ids.add(int(child_key))
                except (TypeError, ValueError):
                    continue
            return ids
        for child_key, child_value in value.items():
            ids.update(_collect_lookup_ids(child_value, str(child_key)))
        return ids

    if isinstance(value, list):
        if key == "allStructureInfo":
            for item in value:
                if isinstance(item, list):
                    if len(item) >= 3:
                        ids.update(_collect_lookup_ids(item[2], "structureTypeID"))
            return ids
        if key == "listOfTypesAndQty":
            for item in value:
                if isinstance(item, list) and item:
                    ids.update(_collect_lookup_ids(item[0], "typeID"))
            return ids
        for item in value:
            ids.update(_collect_lookup_ids(item, key))
        return ids

    if _should_lookup_id(key) and not _is_structure_id_key(key) and isinstance(value, int):
        ids.add(value)
    return ids


def _collect_structure_ids(value: Any, key: str | None = None) -> set[int]:
    ids: set[int] = set()
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            ids.update(_collect_structure_ids(child_value, str(child_key)))
        return ids

    if isinstance(value, list):
        if key == "allStructureInfo":
            for item in value:
                if isinstance(item, list) and item and isinstance(item[0], int):
                    ids.add(item[0])
            return ids
        for item in value:
            ids.update(_collect_structure_ids(item, key))
        return ids

    if _is_structure_id_key(key) and isinstance(value, int):
        ids.add(value)
    return ids


def _is_structure_id_key(key: str | None) -> bool:
    return bool(key and key in STRUCTURE_ID_KEYS)


def _should_lookup_id(key: str | None) -> bool:
    if not key:
        return False
    if key == "moonID":
        return False
    if key in IMPLICIT_ID_KEYS:
        return True
    return bool(ID_KEY_RE.search(key))


async def _get_id_names(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}

    try:
        names_data = await esi_client.get_names(ids)
    except Exception as e:
        logger.warning(f"建筑通知 ESI 名称批量解析失败，准备拆分重试: ids={ids}, error={e}")
        names_data = None

    names: dict[int, str] = {}
    if names_data:
        for category_values in names_data.values():
            if isinstance(category_values, dict):
                for item_id, name in category_values.items():
                    names[int(item_id)] = name

    missing_ids = [item_id for item_id in ids if item_id not in names]
    if not missing_ids:
        return names
    if len(ids) == 1:
        logger.warning(f"建筑通知 ID 名称解析失败，保留原始 ID: {ids[0]}")
        return names

    midpoint = max(1, len(missing_ids) // 2)
    names.update(await _get_id_names(missing_ids[:midpoint]))
    names.update(await _get_id_names(missing_ids[midpoint:]))
    return names


async def _get_structure_names(structure_ids: list[int], character_id: int) -> dict[int, str]:
    if not structure_ids:
        return {}

    try:
        token_info = await get_access_token(
            character_id,
            required_scopes=["esi-universe.read_structures.v1"],
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"建筑通知无法获取建筑查询授权，建筑名称将保留 ID: character={character_id}, error={e}")
        return {}

    access_token = token_info.get("access_token")
    if not access_token:
        logger.warning(f"建筑通知 access token 为空，建筑名称将保留 ID: character={character_id}")
        return {}

    names: dict[int, str] = {}
    for structure_id in structure_ids:
        try:
            structure = await esi_client.get_structure_info(structure_id, access_token)
            name = structure.get("name") if isinstance(structure, dict) else None
            if name:
                names[structure_id] = str(name)
            else:
                logger.warning(f"建筑通知建筑名称为空，保留原始 ID: {structure_id}")
        except Exception as e:
            logger.warning(f"建筑通知建筑名称解析失败，保留原始 ID: {structure_id}, error={e}")
    return names


def _format_field(key: str, value: Any, names: dict[int, str]) -> list[str]:
    label = FIELD_LABELS.get(key, key)

    if key in ("structureLink", "startedByLink", "firedByLink", "cancelledByLink"):
        link_name = _extract_showinfo_name(str(value))
        return [f"{label}: {link_name}"] if link_name else []

    if isinstance(value, dict):
        return _format_dict_field(label, key, value, names)

    if isinstance(value, list):
        return _format_list_field(label, key, value, names)

    if value is None:
        return [f"{label}: 无"]

    return [f"{label}: {_format_scalar(key, value, names)}"]


def _format_dict_field(label: str, key: str, value: dict[Any, Any], names: dict[int, str]) -> list[str]:
    lines = [f"{label}:"]
    if key == "oreVolumeByType":
        for child_key, child_value in value.items():
            try:
                type_id = int(child_key)
                ore_name = _format_scalar("typeID", type_id, names)
            except (TypeError, ValueError):
                ore_name = str(child_key)
            lines.append(f"  {ore_name}: {child_value}")
        return lines

    for child_key, child_value in value.items():
        child_key_str = str(child_key)
        child_label = FIELD_LABELS.get(child_key_str, child_key_str)
        if isinstance(child_value, dict | list):
            child_lines = _format_field(child_key_str, child_value, names)
            lines.extend(f"  {line}" for line in child_lines)
        else:
            lines.append(f"  {child_label}: {_format_scalar(child_key_str, child_value, names)}")
    return lines


def _format_list_field(label: str, key: str, value: list[Any], names: dict[int, str]) -> list[str]:
    if not value:
        return [f"{label}: 无"]

    lines = [f"{label}:"]
    if key == "allStructureInfo":
        for item in value:
            if isinstance(item, list):
                structure_id = item[0] if len(item) >= 1 else None
                structure_name = item[1] if len(item) >= 2 else ""
                structure_type = item[2] if len(item) >= 3 else None
                parts = []
                if isinstance(structure_id, int):
                    resolved_name = names.get(structure_id) or structure_name
                    parts.append(
                        f"{resolved_name} ({structure_id})" if resolved_name else str(structure_id)
                    )
                elif structure_name:
                    parts.append(str(structure_name))
                if isinstance(structure_type, int):
                    parts.append(f"类型 {_format_scalar('structureTypeID', structure_type, names)}")
                lines.append(f"  - {' / '.join(parts) if parts else item}")
            else:
                lines.append(f"  - {_format_scalar(key, item, names)}")
        return lines

    if key == "listOfTypesAndQty":
        for item in value:
            if isinstance(item, list) and len(item) >= 2:
                lines.append(f"  - {_format_scalar('typeID', item[0], names)} x {item[1]}")
            else:
                lines.append(f"  - {item}")
        return lines

    for item in value:
        if isinstance(item, dict):
            child_parts = []
            for child_key, child_value in item.items():
                child_key_str = str(child_key)
                child_label = FIELD_LABELS.get(child_key_str, child_key_str)
                child_parts.append(f"{child_label}: {_format_scalar(child_key_str, child_value, names)}")
            lines.append(f"  - {'; '.join(child_parts)}")
        else:
            lines.append(f"  - {_format_scalar(_singular_id_key(key), item, names)}")
    return lines


def _singular_id_key(key: str) -> str:
    if key.endswith("IDs"):
        return f"{key[:-3]}ID"
    return key


def _format_scalar(key: str | None, value: Any, names: dict[int, str]) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if _should_lookup_id(key) and isinstance(value, int):
        name = names.get(value)
        return f"{name} ({value})" if name else str(value)
    if isinstance(value, float) and _is_percentage_key(key):
        if key and key.endswith("Value"):
            return f"{value * 100:.2f}%"
        return f"{value:.2f}%"
    if isinstance(value, str):
        extracted = _extract_showinfo_name(value)
        return extracted or value
    return str(value)


def _is_percentage_key(key: str | None) -> bool:
    return bool(key and (key.endswith("Percentage") or key.endswith("Value")))


def _extract_showinfo_name(value: str) -> str:
    match = SHOWINFO_RE.search(value)
    if not match:
        return ""
    return unescape(re.sub(r"\s+", " ", match.group(3)).strip())


async def mark_pushed(record_ids: list[int]) -> None:
    """标记通知已推送"""
    if not record_ids:
        return
    async with get_session() as session:
        result = await session.execute(
            select(StructureNotificationRecord).where(
                StructureNotificationRecord.id.in_(record_ids)
            )
        )
        for record in result.scalars().all():
            record.pushed = True
        await session.commit()
