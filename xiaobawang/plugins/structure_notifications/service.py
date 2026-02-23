"""
建筑通知服务层 - 负责 ESI 拉取、数据库存储和推送逻辑
"""

import json
from datetime import datetime, timezone

import httpx
from nonebot import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..cache import get_cache
from ..eve_oauth.api import get_access_token, require_scopes
from .categories import ALL_STRUCTURE_TYPES, TYPE_TO_CATEGORY, get_type_label
from .config import plugin_config
from .models import StructureNotificationRecord, StructureNotificationSub

# 注册本插件所需的 ESI scopes
require_scopes("structure_notifications", [
    "esi-characters.read_notifications.v1",
])

cache = get_cache("structure_notifications")

ESI_NOTIFICATIONS_URL = "https://esi.evetech.net/latest/characters/{character_id}/notifications/"
VERIFY_CODE_PREFIX = "verify_code:"
VERIFY_CODE_EXPIRE = 600  # 10 分钟过期


# ── 验证码管理 ─────────────────────────────────────────────

async def create_verify_code(
    code: str,
    character_id: int,
    sub_id: int | None = None,
    categories: list[str] | None = None,
    character_name: str = "",
) -> bool:
    """将验证码写入缓存, 等待 /verify 命令消费"""
    payload = {
        "character_id": character_id,
        "character_name": character_name,
        "sub_id": sub_id,
        "categories": categories or ["structure"],
    }
    return await cache.set(f"{VERIFY_CODE_PREFIX}{code}", payload, expire=VERIFY_CODE_EXPIRE)


async def consume_verify_code(code: str) -> dict | None:
    """消费验证码, 返回 payload 并删除"""
    payload = await cache.get(f"{VERIFY_CODE_PREFIX}{code}")
    if payload:
        await cache.delete(f"{VERIFY_CODE_PREFIX}{code}")
    return payload


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

def format_notification(record: StructureNotificationRecord, character_name: str = "") -> str:
    """将一条通知格式化为推送文本"""
    label = get_type_label(record.notification_type)
    ts_str = record.timestamp.strftime("%Y-%m-%d %H:%M:%S") if record.timestamp else ""

    lines = [f"{label}"]
    if character_name:
        lines.append(f"角色: {character_name}")
    lines.append(f"时间: {ts_str}")

    # 尝试解析 text 字段中的关键信息
    if record.text:
        parsed = _parse_notification_text(record.text)
        if parsed:
            lines.append(parsed)

    return "\n".join(lines)


def _parse_notification_text(text: str) -> str:
    """尝试从 YAML-like 的 text 字段中提取关键信息"""
    if not text:
        return ""
    info_parts = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 提取常见字段
        if key in ("structureName", "structureTypeName", "solarsystemID",
                    "moonID", "shieldPercentage", "armorPercentage", "hullPercentage"):
            info_parts.append(f"{key}: {val}")
    return "\n".join(info_parts) if info_parts else ""


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
