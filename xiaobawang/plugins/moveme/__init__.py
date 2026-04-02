import heapq
from pathlib import Path

from nonebot import require
from nonebot.plugin import PluginMetadata
from sqlalchemy import func, select

from .config import Config

require("nonebot_plugin_alconna")
require("xiaobawang.plugins.sde")

from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna

from xiaobawang.plugins.sde.db import get_session
from xiaobawang.plugins.sde.models import MapSolarSystemJumps, TrnTranslations

__plugin_meta__ = PluginMetadata(
    name="moveme",
    description="-",
    usage="没什么用",
    type="application",
    config=Config,
    extra={},
)

TC_SOLAR_SYSTEM_ID = 40

_SYSTEM_TXT = Path(__file__).parent / "system.txt"
_MOVEME_SYSTEMS: list[str] = [
    line.strip() for line in _SYSTEM_TXT.read_text(encoding="utf-8").splitlines() if line.strip()
]


async def _resolve_system_name(session, name: str) -> int | None:
    """将星系名称解析为 solarSystemID（英文不区分大小写匹配）。"""
    name = name.strip()
    result = await session.execute(
        select(TrnTranslations).where(
            TrnTranslations.tcID == TC_SOLAR_SYSTEM_ID,
            TrnTranslations.languageID == "en",
            func.lower(TrnTranslations.text) == func.lower(name),
        )
    )
    row = result.scalars().first()
    return row.keyID if row else None


async def _get_system_name(session, system_id: int) -> str:
    """将 solarSystemID 解析回英文名称。"""
    result = await session.execute(
        select(TrnTranslations).where(
            TrnTranslations.tcID == TC_SOLAR_SYSTEM_ID,
            TrnTranslations.languageID == "en",
            TrnTranslations.keyID == system_id,
        )
    )
    row = result.scalars().first()
    return row.text if row else str(system_id)


async def _build_graph(session) -> dict[int, list[int]]:
    """从 mapSolarSystemJumps 构建无向邻接表。"""
    result = await session.execute(select(MapSolarSystemJumps))
    jumps = result.scalars().all()
    graph: dict[int, list[int]] = {}
    for j in jumps:
        graph.setdefault(j.fromSolarSystemID, []).append(j.toSolarSystemID)
        graph.setdefault(j.toSolarSystemID, []).append(j.fromSolarSystemID)
    return graph


def _astar(graph: dict[int, list[int]], start: int, goals: set[int]) -> tuple[int, int] | None:
    """
    A* 搜索（h=0，等价于 Dijkstra）。
    返回 (目标系ID, 跳数)，找不到返回 None。
    """
    # (cost, node)
    heap: list[tuple[int, int]] = [(0, start)]
    visited: dict[int, int] = {}  # node -> best cost

    while heap:
        cost, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited[node] = cost

        if node in goals:
            return node, cost

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                heapq.heappush(heap, (cost + 1, neighbor))

    return None


moveme = on_alconna(
    Alconna(
        "moveme",
        Args["system", str],
    ),
    use_cmd_start=True,
)


@moveme.handle()
async def handle_moveme(arp: Arparma):
    system_input: str = arp.main_args["system"].strip()
    system_upper = system_input.upper()

    async with await get_session() as session:
        start_id = await _resolve_system_name(session, system_input)
        if start_id is None:
            await moveme.finish(f"未找到星系：{system_upper}")
            return

        goal_ids: dict[int, str] = {}
        for name in _MOVEME_SYSTEMS:
            sid = await _resolve_system_name(session, name)
            if sid is not None:
                goal_ids[sid] = name

        if not goal_ids:
            await moveme.finish("moveme 目标星系列表为空，请检查配置。")
            return

        graph = await _build_graph(session)

    result = _astar(graph, start_id, set(goal_ids))
    if result is None:
        await moveme.finish(f"无法从 {system_upper} 到达任何 moveme 星系。")
        return

    target_id, jumps = result
    target_name = goal_ids.get(target_id, str(target_id))
    await moveme.finish(f"{system_upper} → {target_name}：{jumps} 跳")

    