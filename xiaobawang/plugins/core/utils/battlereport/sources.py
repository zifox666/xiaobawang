"""
多来源数据获取与格式统一。

支持三种外部来源：
  1. killmail.app  GET https://killmail.app/api/battle-reports/related/{systemId}/{timeStr}
  2. scit          GET https://scit.scers.cn:45161/api/public/battle_reports/share/{id}?lang=zh
  3. warbeacon auto POST https://warbeacon.net/api/br/auto {"locations":[...]}

以及直接使用已有 warbeacon BR：
  4. warbeacon hash GET https://warbeacon.net/api/br/report/{uuid}
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from ..common.cache import cache as _cache
from ..common.http_client import get_client

WARBEACON_API = "https://warbeacon.net/api/br"
KILLMAIL_APP_API = "https://killmail.app/api/battle-reports/related"
KILLMAIL_APP_HASH_API = "https://killmail.app/api/battle-reports"
SCIT_API = "https://scit.scers.cn:45161/api/public/battle_reports/share"
EVETOOLS_API = "https://br.evetools.org/newapi/br/composition"

_BR_CACHE_TTL = 2 * 60 * 60  # 2 小时


# ────────────────────────────────────────────────────────────────── 统一内部格式

@dataclass
class UnifiedBR:
    """统一的战报内部格式。"""
    killmails: list[dict]
    """标准化 killmail 列表：victim / attackers 均使用标准字段名。"""

    teams: list[set[str]] | None
    """
    队伍列表，每个元素是该队势力键的集合（如 'alliance_99003581'）。
    None 表示无分组信息，需要调用 auto_group.perform_auto_teaming()。
    """

    solar_system_id: int
    solar_system_name: str
    time_start: str          # ISO 8601
    time_end: str            # ISO 8601
    source: str              # "warbeacon_hash" | "warbeacon_auto" | "killmail_app" | "scit"
    source_uuid: str | None = None   # 已有 warbeacon UUID（warbeacon_hash / warbeacon_auto）
    region_id: int | None = None
    region_name: str | None = None
    tickers: dict[int, str] = field(default_factory=dict)  # entity_id -> ticker（从来源直接获取）


# ────────────────────────────────────────────────────────────────── 辅助函数

def _norm_evetools_killmail(raw: dict, system_id: int) -> dict:
    """
    将 br.evetools.org killmail 格式（ally/corp/char/ship/dmg/time ms）
    标准化为内部格式。
    """
    time_ms = raw.get("time", 0)
    if time_ms:
        dt = datetime.datetime.utcfromtimestamp(time_ms / 1000).replace(
            tzinfo=datetime.timezone.utc
        )
        killmail_time = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        killmail_time = ""

    v = raw.get("victim", {})
    victim = {
        "character_id": v.get("char") or None,
        "corporation_id": v.get("corp") or None,
        "alliance_id": v.get("ally") or None,
        "ship_type_id": v.get("ship") or None,
        "damage_taken": int(v.get("dmg") or 0),
    }

    attackers = [
        {
            "character_id": a.get("char") or None,
            "corporation_id": a.get("corp") or None,
            "alliance_id": a.get("ally") or None,
            "ship_type_id": a.get("ship") or None,
            "damage_done": int(a.get("dmg") or 0),
            "final_blow": False,
        }
        for a in raw.get("attackers", [])
        if a.get("ship")
    ]

    return {
        "killmail_id": raw.get("id", 0),
        "killmail_time": killmail_time,
        "total_value": float(v.get("lossValue") or raw.get("totalValue") or 0),
        "solar_system_id": raw.get("system", system_id),
        "victim": victim,
        "attackers": attackers,
    }


def _norm_killmail(raw: dict) -> dict:
    """
    将各来源 killmail 格式统一为内部格式。
    统一字段：killmail_id, killmail_time, total_value, solar_system_id, victim, attackers。

    兼容两种格式：
    - 标准格式（warbeacon/zkb）: { killmail_id, victim:{...}, attackers:[...], total_value, killmail_time }
    - killmail.app hash 格式: { id, character_id, corporation_id, alliance_id, ship_type_id,
                                isk_value, created_at, attackers:[...] }
      （victim 字段直接平铺在顶层，无嵌套 victim 对象）
    """
    km: dict = {}

    # ID
    km["killmail_id"] = raw.get("killmail_id") or raw.get("id") or 0

    # 时间
    km["killmail_time"] = (
        raw.get("killmail_time")
        or raw.get("created_at")
        or raw.get("time")
        or ""
    )

    # 价值
    km["total_value"] = float(
        raw.get("total_value")
        or raw.get("isk_value")
        or raw.get("zkb_value")
        or raw.get("value")
        or 0
    )

    # 星系
    km["solar_system_id"] = (
        raw.get("solar_system_id")
        or raw.get("system_id")
        or 0
    )

    # 受害者：优先使用嵌套 victim 对象；若不存在则从顶层字段读取（killmail.app hash 格式）
    victim_raw = raw.get("victim") or {}
    if victim_raw:
        km["victim"] = {
            "character_id": victim_raw.get("character_id") or None,
            "corporation_id": victim_raw.get("corporation_id") or None,
            "alliance_id": victim_raw.get("alliance_id") or None,
            "ship_type_id": victim_raw.get("ship_type_id") or None,
            "damage_taken": int(victim_raw.get("damage_taken") or 0),
        }
    else:
        km["victim"] = {
            "character_id": raw.get("character_id") or None,
            "corporation_id": raw.get("corporation_id") or None,
            "alliance_id": raw.get("alliance_id") or None,
            "ship_type_id": raw.get("ship_type_id") or None,
            "damage_taken": int(raw.get("damage_taken") or 0),
        }

    # 攻击者
    attackers_raw = raw.get("attackers", [])
    km["attackers"] = [
        {
            "character_id": a.get("character_id") or None,
            "corporation_id": a.get("corporation_id") or None,
            "alliance_id": a.get("alliance_id") or None,
            "ship_type_id": a.get("ship_type_id") or None,
            "damage_done": int(a.get("damage_done") or 0),
            "final_blow": bool(a.get("final_blow", False)),
        }
        for a in attackers_raw
        if a.get("ship_type_id")  # 排除无船型的NPC/胶囊
    ]

    return km


def _warbeacon_data_to_unified(data: dict, source: str, uuid: str) -> UnifiedBR:
    """将 warbeacon API 的 data 字段转为 UnifiedBR。"""
    teams_raw: list[dict] = data.get("teams", [])
    teams: list[set[str]] | None = (
        [set(t.keys()) for t in teams_raw] if teams_raw else None
    )

    killmails = [_norm_killmail(km) for km in data.get("killmails", [])]

    locations: list[dict] = data.get("locations", [])
    loc = locations[0] if locations else {}
    time_range: dict = data.get("timeRange", {})

    return UnifiedBR(
        killmails=killmails,
        teams=teams,
        solar_system_id=loc.get("id", 0),
        solar_system_name=loc.get("name", ""),
        time_start=time_range.get("earliest", ""),
        time_end=time_range.get("latest", ""),
        source=source,
        source_uuid=data.get("uuid", uuid),
    )


def _scit_teams_to_sets(scit_teams: list[dict]) -> tuple[list[set[str]], dict[int, str]]:
    """
    将 scit API 的 teams 转换为势力键集合列表，同时提取 ticker 信息。
    返回 (team_sets, tickers)。
    """
    team_sets: list[set[str]] = []
    tickers: dict[int, str] = {}

    for team in scit_teams:
        team_set: set[str] = set()
        for member in team.get("members", []):
            org_id: int | None = member.get("org_id")
            is_alliance: bool = member.get("is_alliance", False)
            ticker: str = member.get("ticker", "")
            if org_id:
                prefix = "alliance" if is_alliance else "corporation"
                team_set.add(f"{prefix}_{org_id}")
                if ticker:
                    tickers[org_id] = ticker
        if team_set:
            team_sets.append(team_set)

    return team_sets, tickers


def _killmail_app_sides_to_sets(side_overrides: list[dict]) -> list[set[str]] | None:
    """
    将 killmail.app 的 side_overrides 转为势力键集合列表。
    格式示例：[{"type": "alliance", "id": 99003581, "side": 0}, ...]
    如果 side_overrides 为空则返回 None。
    """
    if not side_overrides:
        return None

    teams_dict: dict[int, set[str]] = {}
    for override in side_overrides:
        # 兼容两种可能的字段名
        entity_type = override.get("type") or override.get("entity_type", "")
        entity_id = override.get("id") or override.get("entity_id")
        side = int(override.get("side", 0))

        if entity_id and entity_type in ("alliance", "corporation"):
            fkey = f"{entity_type}_{entity_id}"
            teams_dict.setdefault(side, set()).add(fkey)

    if not teams_dict:
        return None

    return [teams_dict[k] for k in sorted(teams_dict.keys())]


# ────────────────────────────────────────────────────────────────── 公共获取函数

async def fetch_warbeacon_hash(uuid: str) -> UnifiedBR:
    """
    获取已有 warbeacon 战报。
    来源标识：'warbeacon_hash'，不会再向 warbeacon 提交。
    """
    cache_key = f"br:warbeacon_hash:{uuid}"
    cached = await _cache.get(cache_key)
    if cached is not None:
        return cached

    client = get_client()
    resp = await client.get(f"{WARBEACON_API}/report/{uuid}")
    resp.raise_for_status()
    data: dict = resp.json()["data"]

    result = _warbeacon_data_to_unified(data, source="warbeacon_hash", uuid=uuid)
    await _cache.set(cache_key, result, expire=_BR_CACHE_TTL)
    return result


async def fetch_warbeacon_auto(solar_system_id: int, middle_time: str) -> UnifiedBR:
    """
    调用 warbeacon auto 接口创建新战报。
    来源标识：'warbeacon_auto'，已在 warbeacon 服务端创建，不再重复提交。

    :param solar_system_id: EVE 星系 ID
    :param middle_time: 战斗时间中点，ISO 8601 UTC 格式，如 '2026-05-05T06:00:00Z'
    """
    cache_key = f"br:warbeacon_auto:{solar_system_id}:{middle_time}"
    cached = await _cache.get(cache_key)
    if cached is not None:
        return cached

    payload = {"locations": [{"id": solar_system_id, "middleTime": middle_time}]}

    client = get_client()
    resp = await client.post(f"{WARBEACON_API}/auto", json=payload)
    resp.raise_for_status()
    api_result: dict = resp.json()

    # 响应中找 UUID
    data_field = api_result.get("data", {})
    uuid: str = (
        data_field.get("id")
        or data_field.get("uuid")
        or ""
    )
    if not uuid:
        raise ValueError(f"warbeacon auto API 未返回 UUID，响应：{api_result}")

    # 获取完整战报
    resp2 = await client.get(f"{WARBEACON_API}/report/{uuid}")
    resp2.raise_for_status()
    data: dict = resp2.json()["data"]

    br = _warbeacon_data_to_unified(data, source="warbeacon_auto", uuid=uuid)
    await _cache.set(cache_key, br, expire=_BR_CACHE_TTL)
    return br


async def fetch_killmail_app(solar_system_id: int, time_str: str) -> UnifiedBR:
    """
    从 killmail.app 获取战报数据。

    :param solar_system_id: EVE 星系 ID
    :param time_str: 时间字符串，格式 'YYYYMMDDHHmm'（UTC），如 '202605061630'
    """
    cache_key = f"br:killmail_app:{solar_system_id}:{time_str}"
    cached = await _cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{KILLMAIL_APP_API}/{solar_system_id}/{time_str}"
    client = get_client()
    resp = await client.get(url)
    resp.raise_for_status()
    raw: dict = resp.json()

    killmails = [_norm_killmail(km) for km in raw.get("killmails", [])]
    teams = _killmail_app_sides_to_sets(raw.get("side_overrides", []))

    loc: dict = raw.get("location", {})
    period_start: str = raw.get("period_start", "")
    period_end: str = raw.get("period_end", "")

    # 从 killmails 中推算时间范围（period_start/end 可能是精确的）
    time_start = period_start
    time_end = period_end
    if killmails:
        times = sorted(
            km["killmail_time"] for km in killmails if km.get("killmail_time")
        )
        if times:
            time_start = time_start or times[0]
            time_end = time_end or times[-1]

    result = UnifiedBR(
        killmails=killmails,
        teams=teams,
        solar_system_id=loc.get("solar_system_id", solar_system_id),
        solar_system_name=loc.get("solar_system_name", ""),
        region_id=loc.get("region_id"),
        region_name=loc.get("region_name"),
        time_start=time_start,
        time_end=time_end,
        source="killmail_app",
    )
    await _cache.set(cache_key, result, expire=_BR_CACHE_TTL)
    return result


async def fetch_killmail_app_hash(report_id: str) -> UnifiedBR:
    """
    从 killmail.app hash-based API 获取战报数据。

    :param report_id: 战报 ID（取自 URL 第一个 '-' 之前的部分，如 'PTWi4A7Pyh'）
    """
    cache_key = f"br:killmail_app_hash:{report_id}"
    cached = await _cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{KILLMAIL_APP_HASH_API}/{report_id}"
    client = get_client()
    resp = await client.get(url)
    resp.raise_for_status()
    raw: dict = resp.json()

    killmails = [_norm_killmail(km) for km in raw.get("killmails", [])]
    teams = _killmail_app_sides_to_sets(raw.get("side_overrides", []))

    loc: dict = raw.get("location", {})
    time_start = raw.get("period_start", "")
    time_end = raw.get("period_end", "")

    if killmails and not time_start:
        times = sorted(
            km["killmail_time"] for km in killmails if km.get("killmail_time")
        )
        if times:
            time_start = times[0]
            time_end = times[-1]

    result = UnifiedBR(
        killmails=killmails,
        teams=teams,
        solar_system_id=loc.get("solar_system_id", 0),
        solar_system_name=loc.get("solar_system_name", ""),
        region_id=loc.get("region_id"),
        region_name=loc.get("region_name"),
        time_start=time_start,
        time_end=time_end,
        source="killmail_app_hash",
    )
    await _cache.set(cache_key, result, expire=_BR_CACHE_TTL)
    return result


async def fetch_evetools_hash(br_id: str) -> UnifiedBR:
    """
    从 br.evetools.org 获取战报数据。

    :param br_id: 24 位 hex 战报 ID，如 '69ff48939bf3fc001122f1f9'
    """
    cache_key = f"br:evetools_hash:{br_id}"
    cached = await _cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{EVETOOLS_API}/{br_id}"
    client = get_client()
    resp = await client.get(url)
    resp.raise_for_status()
    raw: dict = resp.json()

    # 解析 killmails（可能跨多个 related 星系）
    killmails: list[dict] = []
    for related in raw.get("relateds", []):
        system_id: int = related.get("systemID", 0)
        for km in related.get("kms", []):
            killmails.append(_norm_evetools_killmail(km, system_id))

    # 主星系信息（第一个 related 的 system 对象）
    first_related: dict = (raw.get("relateds") or [{}])[0]
    sys_info: dict = first_related.get("system", {})
    solar_system_id: int = sys_info.get("id") or first_related.get("systemID", 0)
    solar_system_name: str = sys_info.get("name", "")
    region_id: int | None = sys_info.get("regionId")
    region_name: str | None = sys_info.get("region")

    # 时间范围（timings 中的 start/end 是 unix 秒）
    timings: list[dict] = raw.get("timings", [])
    if timings:
        t = timings[0]
        time_start = datetime.datetime.utcfromtimestamp(t["start"]).replace(
            tzinfo=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        time_end = datetime.datetime.utcfromtimestamp(t["end"]).replace(
            tzinfo=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        # 回退：从 killmail 时间推算
        times = sorted(km["killmail_time"] for km in killmails if km.get("killmail_time"))
        time_start = times[0] if times else ""
        time_end = times[-1] if times else ""

    result = UnifiedBR(
        killmails=killmails,
        teams=None,  # evetools 不提供分组信息，由 auto_group 处理
        solar_system_id=solar_system_id,
        solar_system_name=solar_system_name,
        region_id=region_id,
        region_name=region_name,
        time_start=time_start,
        time_end=time_end,
        source="evetools_hash",
    )
    await _cache.set(cache_key, result, expire=_BR_CACHE_TTL)
    return result


async def fetch_scit(report_id: str) -> UnifiedBR:
    """
    从 scit 获取战报数据。

    :param report_id: scit 战报 ID（hash），如 '2cbc843a'
    """
    cache_key = f"br:scit:{report_id}"
    cached = await _cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{SCIT_API}/{report_id}?lang=zh"
    client = get_client()
    resp = await client.get(url)
    resp.raise_for_status()
    raw: dict = resp.json()

    report: dict = raw.get("report", {})

    # 标准化 killmails
    killmails = [_norm_killmail(km) for km in report.get("killmails", [])]

    # 队伍与 ticker
    scit_teams: list[dict] = report.get("teams", [])
    teams, tickers = _scit_teams_to_sets(scit_teams)
    teams_result: list[set[str]] | None = teams if teams else None

    # 星系信息（取第一个）
    systems: list[dict] = report.get("systems", [])
    sys_info = systems[0] if systems else {}

    time_start = raw.get("start_time") or report.get("start_time", "")
    time_end = raw.get("end_time") or report.get("end_time", "")

    result = UnifiedBR(
        killmails=killmails,
        teams=teams_result,
        solar_system_id=sys_info.get("system_id", 0),
        solar_system_name=sys_info.get("system_name", ""),
        time_start=time_start,
        time_end=time_end,
        source="scit",
        tickers=tickers,
    )
    await _cache.set(cache_key, result, expire=_BR_CACHE_TTL)
    return result
