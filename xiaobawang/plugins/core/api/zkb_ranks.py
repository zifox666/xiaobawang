"""
zKillboard Top Ranks 页面解析（纯标准库实现，无 nonebot 依赖）

数据来源: https://zkillboard.com/{type}/ranks/{kl}/{group}/{epoch}/{page}/
页面为服务端渲染表格，每页 500 行，每行含 16 个 data-order 原始数值
（排名 + Ships/Points/ISK 各 5 列），可直接用于本地重排序。
"""

import html as html_lib
import re
from typing import Any

# 排行表格 15 个指标列的顺序（与 zkillboard ranks 页面列顺序一致）
RANK_METRIC_KEYS: list[str] = [
    "ships_destroyed", "sd_rank", "ships_lost", "sl_rank", "ships_pct",
    "points_destroyed", "pd_rank", "points_lost", "pl_rank", "points_pct",
    "isk_destroyed", "id_rank", "isk_lost", "il_rank", "isk_pct",
]

# 行首标记：<td style="width: 35px;" data-order="1"><strong>1</strong></td>
# （损失榜的排名可能带千分位逗号，如 <strong>4,885</strong>）
_ROW_START_RE = re.compile(r'<tr><td style="width: 35px;" data-order="(\d+)"><strong>[\d,]+</strong></td>')
# 实体链接：/character/{id}/ /corporation/{id}/ /alliance/{id}/ /faction/{id}/ /ship/{id}/(shipType)
_ENTITY_RE = re.compile(r'href="/(?:character|corporation|alliance|faction|ship)/(\d+)/"')
# 头像/图标（faction 行没有图片）
_IMG_RE = re.compile(r'src="(https://images\.evetech\.net/[^"]+)"')
# 名称：优先 tooltip 的 title 属性，faction 行回退到链接文本
_TITLE_RE = re.compile(r'title="([^"]*)"')
_FACTION_NAME_RE = re.compile(r'<a href="/faction/\d+/">([^<]+)</a>')
# 指标原始值（ISK 可能是科学计数法，如 1.541884545511E+14）
_DATA_ORDER_RE = re.compile(r'data-order="(-?[0-9.]+(?:[eE][+-]?\d+)?)"')


def parse_ranks_html(html: str) -> list[dict[str, Any]]:
    """
    解析 zkillboard ranks 页面 HTML，返回行列表

    每行结构:
    {
        "rank": int,                # zkb 综合排名
        "id": int,                  # 实体 ID（shipType 为类型 ID）
        "name": str,                # 名称
        "avatar": str,              # 头像/图标 URL（faction 为空）
        "ships_destroyed": float, "sd_rank": float, "ships_lost": float, "sl_rank": float, "ships_pct": float,
        "points_destroyed": float, "pd_rank": float, "points_lost": float, "pl_rank": float, "points_pct": float,
        "isk_destroyed": float, "id_rank": float, "isk_lost": float, "il_rank": float, "isk_pct": float,
    }
    """
    starts = list(_ROW_START_RE.finditer(html))
    rows: list[dict[str, Any]] = []

    for index, match in enumerate(starts):
        seg_start = match.start()
        next_start = starts[index + 1].start() if index + 1 < len(starts) else html.find("</tbody>", seg_start)
        segment = html[seg_start:next_start if next_start > 0 else len(html)]

        entity = _ENTITY_RE.search(segment)
        if not entity:
            continue

        title = _TITLE_RE.search(segment)
        if title:
            name = html_lib.unescape(title.group(1)).strip()
        else:
            faction_name = _FACTION_NAME_RE.search(segment)
            name = html_lib.unescape(faction_name.group(1)).strip() if faction_name else ""

        image = _IMG_RE.search(segment)
        values = _DATA_ORDER_RE.findall(segment)
        # 第一个 data-order 是排名列，其后 15 个为指标列
        metrics = values[1 : 1 + len(RANK_METRIC_KEYS)]
        if len(metrics) < len(RANK_METRIC_KEYS):
            continue

        row: dict[str, Any] = {
            "rank": int(match.group(1)),
            "id": int(entity.group(1)),
            "name": name,
            "avatar": html_lib.unescape(image.group(1)) if image else "",
        }
        row.update({key: float(value) for key, value in zip(RANK_METRIC_KEYS, metrics)})
        rows.append(row)

    return rows
