"""
战报渲染主模块。

完整流程：
  1. 从指定来源获取数据（sources.py）
  2. 没有分组时自动分组（auto_group.py）
  3. 从 ESI 获取势力/角色名称；从 SDE 获取船型名称/分组
  4. 构建 Jinja2 模板上下文（与 test_br.py 的 process() 兼容）
  5. 渲染 HTML + Playwright 截图
  6. 非 warbeacon 来源时向 warbeacon 提交战报，返回链接

公共 API：
    render_br(source_type, **kwargs) -> tuple[bytes | None, str | None]
        返回 (截图字节, warbeacon_url)
"""
from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from nonebot import logger

from .auto_group import faction_key, perform_auto_teaming
from .sources import (
    UnifiedBR,
    fetch_evetools_hash,
    fetch_killmail_app,
    fetch_killmail_app_hash,
    fetch_scit,
    fetch_warbeacon_auto,
    fetch_warbeacon_hash,
)
from ..common.http_client import get_client
from ..render import render_template

# 模板目录：xiaobawang/src/templates/battlereport/
_TEMPLATE_DIR = Path(__file__).parents[4] / "src" / "templates" / "battlereport"

TEAM_COLORS = [
    "#3b82f6",  # Blue
    "#ef4444",  # Red
    "#22c55e",  # Green
    "#f59e0b",  # Amber
    "#a855f7",  # Purple
    "#f97316",  # Orange
    "#06b6d4",  # Cyan
    "#ec4899",  # Pink
]

ESI_BASE = "https://esi.evetech.net/latest"
WARBEACON_API = "https://warbeacon.net/api/br"


# ══════════════════════════════════════════════════════════════ 格式化工具

def _fmt_isk(value: float) -> str:
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}t"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}b"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def _fmt_dmg(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def _parse_eve_time(t: str) -> str:
    """ISO 8601 → 'YYYY-MM-DD HH:MM'，异常时返回空串。"""
    if not t:
        return ""
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return t[:16].replace("T", " ")


def _parse_ts(t: str) -> float:
    """ISO 8601 → POSIX timestamp（秒）。"""
    return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()


# ══════════════════════════════════════════════════════════════ 队伍辅助

def _build_entity_team_map(teams: list[set[str]]) -> dict[int, int]:
    """势力 ID → 队伍索引。"""
    emap: dict[int, int] = {}
    for idx, team in enumerate(teams):
        for fkey in team:
            eid = int(fkey.split("_", 1)[1])
            emap[eid] = idx
    return emap


def _find_team(
    alliance_id: int | None, corporation_id: int | None, emap: dict[int, int]
) -> int:
    """返回队伍索引，-1 表示未找到。"""
    if alliance_id and alliance_id in emap:
        return emap[alliance_id]
    if corporation_id and corporation_id in emap:
        return emap[corporation_id]
    return -1


def _is_alliance_entity(entity_id: int, teams: list[set[str]]) -> bool:
    fkey = f"alliance_{entity_id}"
    return any(fkey in team for team in teams)


# ══════════════════════════════════════════════════════════════ ESI / SDE 名称获取

async def _fetch_esi_names(ids: list[int]) -> dict[int, str]:
    """
    批量从 ESI /universe/names/ 获取 ID → 名称映射。
    自动分块（每批最多 1000 个）。
    """
    if not ids:
        return {}
    # 过滤无效 ID（≤0）
    valid_ids = [i for i in ids if i and i > 0]
    if not valid_ids:
        return {}

    result: dict[int, str] = {}
    chunk_size = 1000
    client = get_client()
    for i in range(0, len(valid_ids), chunk_size):
        chunk = valid_ids[i : i + chunk_size]
        try:
            resp = await client.post(
                f"{ESI_BASE}/universe/names/?datasource=tranquility",
                json=chunk,
            )
            if resp.status_code == 200:
                for item in resp.json():
                    result[item["id"]] = item["name"]
        except Exception:
            pass
    return result


async def _fetch_esi_tickers(
    faction_keys: list[set[str]],
) -> dict[int, str]:
    """
    从 ESI 获取联盟/公司 ticker。仅针对队伍中出现的势力。
    并发请求，失败时静默跳过。
    """
    items: list[tuple[int, str]] = []
    for team in faction_keys:
        for fkey in team:
            etype, eid_str = fkey.split("_", 1)
            items.append((int(eid_str), etype))

    if not items:
        return {}

    tickers: dict[int, str] = {}

    async def _fetch_one(eid: int, etype: str) -> None:
        url = (
            f"{ESI_BASE}/alliances/{eid}/"
            if etype == "alliance"
            else f"{ESI_BASE}/corporations/{eid}/"
        )
        try:
            resp = await get_client().get(url)
            if resp.status_code == 200:
                data = resp.json()
                if "ticker" in data:
                    tickers[eid] = data["ticker"]
        except Exception:
            pass

    await asyncio.gather(*[_fetch_one(eid, etype) for eid, etype in items])
    return tickers


async def _get_type_data(type_ids: list[int]) -> dict[int, dict[str, Any]]:
    """
    从 SDE 批量获取船型名称 + 分组 ID。
    返回 {type_id: {name: str, group_id: int}}。
    """
    if not type_ids:
        return {}
    from xiaobawang.plugins.sde.oper import sde_search

    type_names = await sde_search.get_type_names(type_ids)

    # 并发获取 group_id
    group_ids: dict[int, int] = {}
    results = await asyncio.gather(
        *[sde_search.get_type_group(tid, _id=True) for tid in type_ids],
        return_exceptions=True,
    )
    for tid, gid in zip(type_ids, results):
        group_ids[tid] = gid if isinstance(gid, int) else 0

    out: dict[int, dict[str, Any]] = {}
    for tid in type_ids:
        info = type_names.get(tid, {})
        name = info.get("translation") or info.get("typeName") or f"Ship {tid}"
        out[tid] = {"name": name, "group_id": group_ids.get(tid, 0)}

    return out


# ══════════════════════════════════════════════════════════════ 时间工具

def _compute_middle_time(time_start: str, time_end: str) -> str:
    """计算时间范围中点，返回 ISO 8601 UTC 格式。"""
    try:
        t1 = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(time_end.replace("Z", "+00:00"))
        mid = t1 + (t2 - t1) / 2
        return mid.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        # 无法解析时用当前时间
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_middle_from_killmails(killmails: list[dict]) -> str:
    times = sorted(
        km["killmail_time"]
        for km in killmails
        if km.get("killmail_time")
    )
    if len(times) >= 2:
        return _compute_middle_time(times[0], times[-1])
    if times:
        return _compute_middle_time(times[0], times[0])
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ══════════════════════════════════════════════════════════════ warbeacon 提交

def _count_pilots_per_faction(
    killmails: list[dict], teams: list[set[str]]
) -> dict[str, int]:
    """统计每个势力键对应的独立飞行员数量。"""
    all_fkeys = {fkey for team in teams for fkey in team}
    alliance_ids = {int(k.split("_")[1]) for k in all_fkeys if k.startswith("alliance_")}

    # 构建公司→联盟映射
    corp_alliance: dict[int, int] = {}
    for km in killmails:
        for ent in [km.get("victim", {})] + km.get("attackers", []):
            cid = ent.get("corporation_id")
            aid = ent.get("alliance_id")
            if cid and aid:
                corp_alliance[cid] = aid

    pilots_per_faction: dict[str, set[int]] = {fkey: set() for fkey in all_fkeys}

    def _assign(alliance_id: int | None, corp_id: int | None, char_id: int | None) -> None:
        if not char_id:
            return
        fkey = faction_key(alliance_id, corp_id)
        if fkey and fkey in pilots_per_faction:
            pilots_per_faction[fkey].add(char_id)
        elif corp_id:
            # 尝试通过公司→联盟映射
            mapped_aid = corp_alliance.get(corp_id)
            if mapped_aid:
                ak = f"alliance_{mapped_aid}"
                if ak in pilots_per_faction:
                    pilots_per_faction[ak].add(char_id)

    for km in killmails:
        v = km.get("victim", {})
        _assign(v.get("alliance_id"), v.get("corporation_id"), v.get("character_id"))
        for att in km.get("attackers", []):
            _assign(att.get("alliance_id"), att.get("corporation_id"), att.get("character_id"))

    return {fkey: max(len(chars), 1) for fkey, chars in pilots_per_faction.items()}


async def _post_warbeacon_create(
    unified: UnifiedBR, teams: list[set[str]]
) -> str:
    """
    向 warbeacon create API 提交战报，返回 warbeacon URL。
    """
    pilot_counts = _count_pilots_per_faction(unified.killmails, teams)

    teams_payload = [
        {fkey: pilot_counts.get(fkey, 1) for fkey in team}
        for team in teams
        if team  # 跳过空队
    ]

    # 计算中间时间
    if unified.time_start and unified.time_end:
        middle_time = _compute_middle_time(unified.time_start, unified.time_end)
    else:
        middle_time = _compute_middle_from_killmails(unified.killmails)

    payload = {
        "locations": [{"id": unified.solar_system_id, "middleTime": middle_time}],
        "teams": teams_payload,
    }

    logger.debug(f"_post_warbeacon_create payload: {payload}")

    client = get_client()
    resp = await client.post(f"{WARBEACON_API}/create", json=payload)
    resp.raise_for_status()
    result = resp.json()

    data_field = result.get("data", {})
    uuid: str = data_field.get("id") or data_field.get("uuid") or ""
    if not uuid:
        raise ValueError(f"warbeacon create API 未返回 UUID，响应：{result}")

    return f"https://warbeacon.net/br/report/{uuid}"


# ══════════════════════════════════════════════════════════════ 模板上下文构建

def _build_template_context(
    unified: UnifiedBR,
    teams: list[set[str]],
    entity_names: dict[int, str],
    tickers: dict[int, str],
    type_data: dict[int, dict[str, Any]],
    br_uuid: str = "",
) -> dict:
    """
    从统一格式数据构建 Jinja2 模板所需的上下文字典。
    与 test_br.py 的 process() 函数保持兼容的输出格式。
    """
    n = len(teams)
    if n == 0:
        return {"report": {}, "teams": [], "isk_chart": None}

    killmails = unified.killmails
    emap = _build_entity_team_map(teams)

    # ── 每队累计统计 ──────────────────────────────────────────────────────────
    team_kills = [0] * n
    team_isk_killed = [0.0] * n

    # ship_losses[team_idx][ship_type_id] = {count, isk}
    ship_losses: list[dict[int, dict]] = [defaultdict(lambda: {"count": 0, "isk": 0.0}) for _ in range(n)]
    # ship_dmg_done[team_idx][ship_type_id] = damage_total
    ship_dmg_done: list[dict[int, int]] = [defaultdict(int) for _ in range(n)]

    # pilot_stats[team_idx][char_id] = {...}
    pilot_stats: list[dict[int, dict]] = [dict() for _ in range(n)]

    # 参与者集合
    team_pilot_sets: list[set[int]] = [set() for _ in range(n)]
    # topFactions 统计 (team_idx -> faction_id -> set of unique char_ids)
    team_faction_cnts: list[dict[int, set]] = [defaultdict(set) for _ in range(n)]
    # topShipTypes 统计 (team_idx -> ship_type_id -> set of unique char_ids)
    team_ship_cnts: list[dict[int, set]] = [defaultdict(set) for _ in range(n)]
    # 损失统计
    team_losses = [0] * n
    team_loss_values = [0.0] * n

    for km in killmails:
        km_value = float(km.get("total_value", 0))
        victim = km.get("victim", {})
        attackers = km.get("attackers", [])
        total_victim_dmg = sum(a.get("damage_done", 0) for a in attackers)

        v_ally = victim.get("alliance_id")
        v_corp = victim.get("corporation_id")
        v_char = victim.get("character_id")
        v_ship = victim.get("ship_type_id")

        victim_team = _find_team(v_ally, v_corp, emap)

        if victim_team >= 0:
            team_losses[victim_team] += 1
            team_loss_values[victim_team] += km_value

            if v_ship:
                sl = ship_losses[victim_team][v_ship]
                sl["count"] += 1
                sl["isk"] = sl.get("isk", 0.0) + km_value

            if v_char:
                team_pilot_sets[victim_team].add(v_char)
                if v_char not in pilot_stats[victim_team]:
                    pilot_stats[victim_team][v_char] = {
                        "character_id": v_char,
                        "name": entity_names.get(v_char, f"Pilot {v_char}"),
                        "corp_id": v_corp or 0,
                        "alliance_id": v_ally or 0,
                        "ship_type_id": v_ship or 0,
                        "kills": 0, "participated": 0, "losses": 0,
                        "isk_lost": 0.0, "damage_done": 0, "damage_taken": 0,
                    }
                ps = pilot_stats[victim_team][v_char]
                ps["losses"] += 1
                ps["isk_lost"] += km_value
                ps["damage_taken"] += total_victim_dmg
                if v_ally:
                    ps["alliance_id"] = v_ally

            # topFactions
            fid = v_ally or v_corp
            if fid:
                team_faction_cnts[victim_team][fid].add(v_char or fid)

            if v_ship:
                # 受害者每次 killmail 是一次独立损失，用 killmail_id 作为唯一标识
                team_ship_cnts[victim_team][v_ship].add(v_char or km.get("killmail_id", id(km)))

        # final_blow 攻击方统计
        fb = next((a for a in attackers if a.get("final_blow")), None)
        if fb is None and attackers:
            fb = max(attackers, key=lambda a: a.get("damage_done", 0))

        if fb:
            kb_team = _find_team(fb.get("alliance_id"), fb.get("corporation_id"), emap)
            if kb_team >= 0 and victim_team >= 0 and kb_team != victim_team:
                team_kills[kb_team] += 1
                team_isk_killed[kb_team] += km_value

        for att in attackers:
            att_team = _find_team(att.get("alliance_id"), att.get("corporation_id"), emap)
            att_ship = att.get("ship_type_id")
            att_dmg = att.get("damage_done", 0)
            att_char = att.get("character_id")
            att_ally = att.get("alliance_id")
            att_corp = att.get("corporation_id")

            if att_team >= 0:
                if att_char:
                    team_pilot_sets[att_team].add(att_char)

                if att_ship:
                    ship_dmg_done[att_team][att_ship] += att_dmg
                    if att_char:  # 只计登录的玩家，NPC 无 char_id 不计入
                        team_ship_cnts[att_team][att_ship].add(att_char)

                fid = att_ally or att_corp
                if fid:
                    team_faction_cnts[att_team][fid].add(att_char or fid)

                # 攻击方参与击杀统计（所有有 char_id 的玩家攻击方）
                if att_char and att_team != victim_team:
                    if att_char not in pilot_stats[att_team]:
                        pilot_stats[att_team][att_char] = {
                            "character_id": att_char,
                            "name": entity_names.get(att_char, f"Pilot {att_char}"),
                            "corp_id": att_corp or 0,
                            "alliance_id": att_ally or 0,
                            "ship_type_id": att_ship or 0,
                            "kills": 0, "participated": 0, "losses": 0,
                            "isk_lost": 0.0, "damage_done": 0, "damage_taken": 0,
                        }
                    ps = pilot_stats[att_team][att_char]
                    ps["participated"] += 1
                    ps["damage_done"] += att_dmg
                    if att_ship and not ps.get("ship_type_id"):
                        ps["ship_type_id"] = att_ship
                    if att.get("final_blow"):
                        ps["kills"] += 1  # final blow 次数

    # ── 全局统计 ─────────────────────────────────────────────────────────────
    total_isk_lost = sum(team_loss_values)
    total_kills = sum(team_losses)
    total_pilots = sum(len(s) for s in team_pilot_sets)

    raw_total_share = sum(team_isk_killed)

    def _normalize_share(isk_k: float) -> float:
        return isk_k / raw_total_share * 100.0 if raw_total_share > 0 else 0.0

    display_mode = (
        "individual" if total_pilots < 50
        else "ship_type" if total_pilots <= 200
        else "ship_group"
    )

    # ── 时间 / 星系 ───────────────────────────────────────────────────────────
    system_name = unified.solar_system_name
    region_name = unified.region_name or ""
    system_id = unified.solar_system_id or None

    t_start = _parse_eve_time(unified.time_start)
    t_end = _parse_eve_time(unified.time_end)

    # ── 构建每队数据 ──────────────────────────────────────────────────────────
    teams_out = []
    for idx in range(n):
        color = TEAM_COLORS[idx % len(TEAM_COLORS)]
        team_set = teams[idx]

        # 主势力 = 参与人数最多的势力键
        pilot_counts_per_fac = {
            int(fkey.split("_", 1)[1]): len(team_faction_cnts[idx].get(int(fkey.split("_", 1)[1]), set()))
            for fkey in team_set
        }
        main_id = max(pilot_counts_per_fac, key=pilot_counts_per_fac.get, default=0)
        if main_id == 0 and team_set:
            main_id = int(next(iter(team_set)).split("_", 1)[1])

        is_ally = _is_alliance_entity(main_id, teams)
        main_name = entity_names.get(main_id, f"Entity {main_id}")
        main_ticker = tickers.get(main_id, "???")

        losses = team_losses[idx]
        isk_lost = team_loss_values[idx]
        isk_killed = team_isk_killed[idx]
        kills = team_kills[idx]
        part_count = len(team_pilot_sets[idx])

        isk_total = isk_lost + isk_killed
        isk_efficiency = (isk_killed / isk_total * 100) if isk_total > 0 else 0.0
        isk_share = _normalize_share(isk_killed)

        # top factions
        top_factions = []
        sorted_factions = sorted(team_faction_cnts[idx].items(), key=lambda x: -len(x[1]))
        for fid, chars in sorted_factions[:10]:
            pcnt = len(chars)
            fname = entity_names.get(fid, f"Entity {fid}")
            fticker = tickers.get(fid, "")
            f_ally = _is_alliance_entity(fid, teams)
            top_factions.append({
                "faction_id": fid,
                "name": fname,
                "ticker": fticker,
                "participant_count": pcnt,
                "is_alliance": f_ally,
            })

        # ship type stats（以该队伍的 topShipTypes 为来源）
        # used_ships: list of (ship_id, count) sorted by count desc
        used_ships_raw = team_ship_cnts[idx]  # dict[ship_id, set[char_id]]
        used_ships = sorted(used_ships_raw.items(), key=lambda x: -len(x[1]))
        ship_type_stats = []
        for ship_id, char_set in used_ships[:25]:
            usage = len(char_set)
            info = type_data.get(ship_id, {})
            sname = info.get("name", f"Ship {ship_id}")
            sl = ship_losses[idx].get(ship_id, {"count": 0, "isk": 0.0})
            sd = ship_dmg_done[idx].get(ship_id, 0)
            dmg_taken = sum(ship_dmg_done[j].get(ship_id, 0) for j in range(n) if j != idx)
            isk_l = sl["isk"]
            ship_type_stats.append({
                "ship_type_id": ship_id,
                "name": sname,
                "count": usage,
                "losses": sl["count"],
                "isk_lost": isk_l,
                "isk_lost_fmt": _fmt_isk(isk_l) if isk_l > 0 else "--",
                "damage_done": sd,
                "damage_done_fmt": _fmt_dmg(sd) if sd > 0 else "--",
                "damage_taken": dmg_taken,
                "damage_taken_fmt": _fmt_dmg(dmg_taken) if dmg_taken > 0 else "--",
            })

        # ship group stats
        groups: dict[int, dict] = {}
        for ship_id, char_set in used_ships_raw.items():
            usage = len(char_set)
            info = type_data.get(ship_id, {})
            gid = info.get("group_id", 0)
            gname = info.get("group_name") or f"Class {gid}"
            sl = ship_losses[idx].get(ship_id, {"count": 0, "isk": 0.0})
            isk_l = sl["isk"]
            sd = ship_dmg_done[idx].get(ship_id, 0)
            dmg_taken = sum(ship_dmg_done[j].get(ship_id, 0) for j in range(n) if j != idx)
            if gid not in groups:
                groups[gid] = {"group_id": gid, "name": gname, "count": 0, "isk_lost": 0.0,
                               "losses": 0, "damage_done": 0, "damage_taken": 0,
                               "rep_ship_id": ship_id, "rep_usage": usage}
            elif usage > groups[gid].get("rep_usage", 0):
                groups[gid]["rep_ship_id"] = ship_id
                groups[gid]["rep_usage"] = usage
            groups[gid]["count"] += usage
            groups[gid]["isk_lost"] += isk_l
            groups[gid]["losses"] += sl.get("count", 0)
            groups[gid]["damage_done"] += sd
            groups[gid]["damage_taken"] += dmg_taken

        ship_group_stats = sorted(groups.values(), key=lambda g: -g["count"])[:18]
        for g in ship_group_stats:
            g["isk_lost_fmt"] = _fmt_isk(g["isk_lost"]) if g["isk_lost"] > 0 else "--"
            g["damage_done_fmt"] = _fmt_dmg(g["damage_done"]) if g["damage_done"] > 0 else "--"
            g["damage_taken_fmt"] = _fmt_dmg(g["damage_taken"]) if g["damage_taken"] > 0 else "--"

        # individual pilot stats
        individual_stats = sorted(
            pilot_stats[idx].values(),
            key=lambda p: (-p.get("participated", 0), -p.get("isk_lost", 0)),
        )[:20]
        for p in individual_stats:
            p["isk_lost_fmt"] = _fmt_isk(p["isk_lost"]) if p.get("isk_lost", 0) > 0 else "--"
            p["damage_done_fmt"] = _fmt_dmg(p["damage_done"]) if p.get("damage_done", 0) > 0 else "--"
            p["damage_taken_fmt"] = _fmt_dmg(p["damage_taken"]) if p.get("damage_taken", 0) > 0 else "--"
            sid = p.get("ship_type_id", 0)
            p["ship_name"] = type_data.get(sid, {}).get("name", "") if sid else ""
            p.setdefault("alliance_id", 0)

        teams_out.append({
            "team_id": idx,
            "color": color,
            "main_faction_id": main_id,
            "main_faction_name": main_name,
            "main_faction_ticker": main_ticker,
            "is_alliance": is_ally,
            "participant_count": part_count,
            "kills": kills,
            "losses": losses,
            "isk_lost": isk_lost,
            "isk_lost_fmt": _fmt_isk(isk_lost),
            "isk_killed": isk_killed,
            "isk_killed_fmt": _fmt_isk(isk_killed),
            "isk_efficiency": isk_efficiency,
            "isk_killed_share": isk_share,
            "top_factions": top_factions,
            "ship_type_stats": ship_type_stats,
            "ship_group_stats": ship_group_stats,
            "individual_stats": individual_stats,
        })

    # ── ISK 时间线图表 ────────────────────────────────────────────────────────
    sorted_kms = sorted(killmails, key=lambda k: k.get("killmail_time", ""))
    isk_chart = None
    if sorted_kms:
        t_first = _parse_ts(sorted_kms[0]["killmail_time"])
        t_last = _parse_ts(sorted_kms[-1]["killmail_time"])
        t_range_s = t_last - t_first or 1

        team_cum = [0.0] * n
        series_pts: list[list[tuple[float, float]]] = [[(0.0, 0.0)] for _ in range(n)]

        for km in sorted_kms:
            km_ts = _parse_ts(km["killmail_time"])
            x = (km_ts - t_first) / t_range_s * 100.0
            v = km.get("victim", {})
            vt = _find_team(v.get("alliance_id"), v.get("corporation_id"), emap)
            if vt >= 0:
                team_cum[vt] += float(km.get("total_value", 0))
            for i in range(n):
                series_pts[i].append((x, team_cum[i]))

        for i in range(n):
            series_pts[i].append((100.0, team_cum[i]))

        max_isk_chart = max(
            (max(y for _, y in s) for s in series_pts if s),
            default=1.0
        ) or 1.0

        def _to_polyline(pts: list) -> str:
            out = []
            for x, isk in pts:
                y = 95.0 - (isk / max_isk_chart * 88.0)
                out.append(f"{x:.2f},{y:.2f}")
            return " ".join(out)

        svg_series = []
        for i, team in enumerate(teams_out):
            line_pts = _to_polyline(series_pts[i])
            fill_pts = f"0,95 {line_pts} 100,95"
            svg_series.append({
                "color": team["color"],
                "ticker": team["main_faction_ticker"],
                "points": line_pts,
                "fill_points": fill_pts,
                "final_isk": team_cum[i],
                "final_isk_fmt": _fmt_isk(team_cum[i]),
            })

        isk_chart = {
            "svg_series": svg_series,
            "max_isk_fmt": _fmt_isk(max_isk_chart),
            "t_start_label": _parse_eve_time(sorted_kms[0]["killmail_time"]),
            "t_end_label": _parse_eve_time(sorted_kms[-1]["killmail_time"]),
        }

    return {
        "report": {
            "uuid": br_uuid,
            "system": system_name,
            "system_id": system_id,
            "region": region_name,
            "time_start": t_start,
            "time_end": t_end,
            "total_participants": total_pilots,
            "total_kills": total_kills,
            "total_isk_lost": total_isk_lost,
            "total_isk_lost_fmt": _fmt_isk(total_isk_lost),
            "display_mode": display_mode,
        },
        "teams": teams_out,
        "isk_chart": isk_chart,
    }


# ══════════════════════════════════════════════════════════════ 公共入口

async def render_br(
    source_type: str,
    *,
    # killmail.app
    solar_system_id: int | None = None,
    time_str: str | None = None,
    # scit
    report_id: str | None = None,
    # warbeacon hash
    uuid: str | None = None,
    # warbeacon auto
    middle_time: str | None = None,
) -> tuple[bytes | None, str | None]:
    """
    获取、处理、渲染战报。

    :param source_type: 'killmail_app' | 'scit' | 'warbeacon_auto' | 'warbeacon_hash'
    :return: (PNG 截图字节 | None, warbeacon URL | None)

    示例::
        img, url = await render_br('scit', report_id='2cbc843a')
        img, url = await render_br('killmail_app', solar_system_id=30002439, time_str='202605061630')
        img, url = await render_br('warbeacon_auto', solar_system_id=30002439, middle_time='2026-05-06T17:00:00Z')
        img, url = await render_br('warbeacon_hash', uuid='b92c98c9-5c1c-459f-bbe5-3d3cf03699d8')
    """
    # ── 1. 获取数据 ───────────────────────────────────────────────────────────
    if source_type == "warbeacon_hash":
        if not uuid:
            raise ValueError("render_br: source_type='warbeacon_hash' 需要 uuid 参数")
        unified = await fetch_warbeacon_hash(uuid)

    elif source_type == "warbeacon_auto":
        if not solar_system_id:
            raise ValueError("render_br: source_type='warbeacon_auto' 需要 solar_system_id 参数")
        if not middle_time:
            if time_str:
                # 将 'YYYYMMDDHHmm' 转为 ISO 8601
                dt = datetime.strptime(time_str, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
                middle_time = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                raise ValueError("render_br: source_type='warbeacon_auto' 需要 middle_time 或 time_str 参数")
        unified = await fetch_warbeacon_auto(solar_system_id, middle_time)

    elif source_type == "killmail_app":
        if not solar_system_id or not time_str:
            raise ValueError("render_br: source_type='killmail_app' 需要 solar_system_id 和 time_str 参数")
        unified = await fetch_killmail_app(solar_system_id, time_str)

    elif source_type == "killmail_app_hash":
        if not report_id:
            raise ValueError("render_br: source_type='killmail_app_hash' 需要 report_id 参数")
        unified = await fetch_killmail_app_hash(report_id)

    elif source_type == "evetools_hash":
        if not report_id:
            raise ValueError("render_br: source_type='evetools_hash' 需要 report_id 参数")
        unified = await fetch_evetools_hash(report_id)

    elif source_type == "scit":
        if not report_id:
            raise ValueError("render_br: source_type='scit' 需要 report_id 参数")
        unified = await fetch_scit(report_id)

    else:
        raise ValueError(f"render_br: 未知 source_type '{source_type}'")

    # ── 2. 自动分组（如果没有分组信息）────────────────────────────────────────
    teams: list[set[str]] = unified.teams if unified.teams else []
    if not teams:
        teams = perform_auto_teaming(unified.killmails)
    if not teams:
        logger.warning(
            f"render_br [{source_type}]: 自动分队失败，killmail 数量={len(unified.killmails)}"
        )
        return None, None

    # ── 3. 收集需要查询名称的 ID ──────────────────────────────────────────────
    entity_ids: set[int] = set()
    type_ids: set[int] = set()

    for km in unified.killmails:
        victim = km.get("victim", {})
        for fld in ("character_id", "corporation_id", "alliance_id"):
            v = victim.get(fld)
            if v:
                entity_ids.add(v)
        if victim.get("ship_type_id"):
            type_ids.add(victim["ship_type_id"])

        for att in km.get("attackers", []):
            for fld in ("character_id", "corporation_id", "alliance_id"):
                v = att.get(fld)
                if v:
                    entity_ids.add(v)
            if att.get("ship_type_id"):
                type_ids.add(att["ship_type_id"])

    # ── 4. 并发获取名称 ───────────────────────────────────────────────────────
    entity_names, esi_tickers, type_data = await asyncio.gather(
        _fetch_esi_names(list(entity_ids)),
        _fetch_esi_tickers(teams),
        _get_type_data(list(type_ids)),
    )

    # 合并 ticker：来源提供的优先，ESI 作为补充
    tickers = {**esi_tickers, **unified.tickers}

    # 补充船型分组名称（直接用 group_id 查 TrnTranslations，tcID=TC_GROUP_ID）
    group_ids_needed = {td["group_id"] for td in type_data.values() if td.get("group_id")}
    if group_ids_needed:
        try:
            from xiaobawang.plugins.sde.oper import sde_search
            group_name_results = await asyncio.gather(
                *[sde_search.get_group_name(gid) for gid in group_ids_needed],
                return_exceptions=True,
            )
            group_id_to_name = {
                gid: name if isinstance(name, str) else f"Class {gid}"
                for gid, name in zip(group_ids_needed, group_name_results)
            }
            for td in type_data.values():
                gid = td.get("group_id", 0)
                if gid and gid in group_id_to_name:
                    td["group_name"] = group_id_to_name[gid]
        except Exception:
            logger.exception("获取 group 名称失败")

    # ── 5. 构建模板上下文 ─────────────────────────────────────────────────────
    br_uuid = unified.source_uuid or ""
    ctx = _build_template_context(
        unified, teams, entity_names, tickers, type_data, br_uuid=br_uuid
    )

    # ── 6. 渲染模板 + 截图 ────────────────────────────────────────────────
    _n_teams = len(ctx.get("teams", []))
    if _n_teams <= 2:
        _viewport_w = 1200
    elif _n_teams == 3:
        _viewport_w = 1400
    elif _n_teams == 4:
        _viewport_w = 1600
    elif _n_teams == 5:
        _viewport_w = 1800
    else:
        _viewport_w = 2000
    try:
        image_bytes: bytes | str | None = await render_template(
            template_path=_TEMPLATE_DIR,
            template_name="battlereport.html.jinja2",
            data=ctx,
            width=_viewport_w,
        )
    except Exception:
        logger.exception(f"render_br [{source_type}]: render_template 失败")
        image_bytes = None

    # ── 7. 非 warbeacon 来源时提交到 warbeacon，获取链接 ──────────────────────
    warbeacon_url: str | None = None
    if source_type in ("warbeacon_hash", "warbeacon_auto"):
        if unified.source_uuid:
            warbeacon_url = f"https://warbeacon.net/br/report/{unified.source_uuid}"
    else:
        # killmail_app / scit → 提交到 warbeacon create
        try:
            warbeacon_url = await _post_warbeacon_create(unified, teams)
        except Exception:
            warbeacon_url = None

    return image_bytes, warbeacon_url
