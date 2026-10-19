from arclet.alconna import Arparma, Option
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, UniMessage, on_alconna

from ..api.zkillboard import zkb_api
from ..utils.common.cache import save_msg_cache
from ..utils.common import format_value
from ..utils.render import render_template, templates_path

__all__ = ["zkbrank"]

# 实体类型: 输入 -> zkillboard URL 类型
_TYPE_MAP: dict[str, str] = {
    "char": "character", "character": "character", "chara": "character",
    "人物": "character", "角色": "character", "个人": "character",
    "corp": "corporation", "corporation": "corporation", "corps": "corporation",
    "军团": "corporation",
    "alliance": "alliance", "联盟": "alliance",
    "faction": "faction", "势力": "faction",
    "ship": "shipType", "shiptype": "shipType", "ship_type": "shipType",
    "舰船": "shipType", "船只": "shipType",
}
# 阵营: 输入 -> k(击杀) / l(损失)
_SIDE_MAP: dict[str, str] = {
    "k": "k", "kill": "k", "kills": "k", "killer": "k", "killers": "k",
    "击杀": "k", "击杀最多": "k",
    "l": "l", "loss": "l", "losses": "l", "loser": "l", "losers": "l",
    "损失": "l", "损失最多": "l",
}
# 指标: 输入 -> count(数量) / value(价值)
_METRIC_MAP: dict[str, str] = {
    "count": "count", "n": "count", "num": "count", "number": "count",
    "数量": "count", "按数量": "count",
    "value": "value", "isk": "value", "v": "value",
    "价值": "value", "按价值": "value",
}
# 时间范围: 输入 -> weekly(7天) / recent(90天) / alltime(开服以来)
_EPOCH_MAP: dict[str, str] = {
    "week": "weekly", "weekly": "weekly", "7": "weekly", "7d": "weekly", "周": "weekly",
    "recent": "recent", "90": "recent", "90d": "recent", "season": "recent",
    "all": "alltime", "alltime": "alltime", "total": "alltime",
    "总": "alltime", "开服": "alltime", "开服以来": "alltime",
}
# 分组: 输入 -> all(全部) / solo(仅SOLO)
_GROUP_MAP: dict[str, str] = {
    "all": "all", "全部": "all",
    "solo": "solo", "仅solo": "solo",
}

_TYPE_LABELS: dict[str, str] = {
    "character": "人物", "corporation": "军团", "alliance": "联盟", "faction": "势力", "shipType": "舰船",
}
_SIDE_LABELS: dict[str, str] = {"k": "击杀最多", "l": "损失最多"}
_METRIC_LABELS: dict[str, str] = {"count": "按数量", "value": "按价值"}
_EPOCH_LABELS: dict[str, str] = {"weekly": "最近 7 天", "recent": "最近 90 天", "alltime": "开服以来"}
_GROUP_LABELS: dict[str, str] = {"all": "全部", "solo": "仅SOLO"}

# 不同阵营/指标组合对应的 zkillboard 排序键与展示字段
# (sort_key, primary_field, secondary_field)
_METRIC_FIELDS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("k", "count"): ("shipsDestroyed", "ships_destroyed", "isk_destroyed"),
    ("k", "value"): ("iskDestroyed", "isk_destroyed", "ships_destroyed"),
    ("l", "count"): ("shipsLost", "ships_lost", "isk_lost"),
    ("l", "value"): ("iskLost", "isk_lost", "ships_lost"),
}

USAGE = (
    "/zkbrank -t [char|corp|alliance|faction|ship] -s [k|l] -m [count|value] "
    "-e [week|recent|all] -g [all|solo] -l [1-50]\n"
    "默认: 军团 · 击杀最多 · 按数量 · 最近90天 · 前20\n"
    "也可以直接发送: 人物排行 / 军团排行 / 联盟排行 / 势力排行 / 舰船排行"
)

zkbrank = on_alconna(
    Alconna(
        "zkbrank",
        Option("-t|--type", Args["type_", str], default="corporation"),
        Option("-s|--side", Args["side", str], default="k"),
        Option("-m|--metric", Args["metric", str], default="count"),
        Option("-e|--epoch", Args["epoch", str], default="recent"),
        Option("-g|--group", Args["group", str], default="all"),
        Option("-l|--limit", Args["limit", int], default=20),
        CommandMeta(
            description="zKillboard 排行榜（人物/军团/联盟/势力/舰船）",
            usage=USAGE,
        ),
    ),
    use_cmd_start=True,
)

# 中文快捷短语，自动解析成命令（可追加参数，如 "人物排行 -s l -m value"）
for _phrase, _type in {
    "人物": "character", "角色": "character",
    "军团": "corporation",
    "联盟": "alliance",
    "势力": "faction",
    "舰船": "shipType", "船只": "shipType",
}.items():
    zkbrank.shortcut(
        rf"^{_phrase}排行\s*(.*)$",
        command=f"zkbrank -t {_type} {{0}}",
        fuzzy=True,
    )


def _normalize(mapping: dict[str, str], value: str, default: str) -> str:
    return mapping.get(value.strip().lower(), mapping.get(value.strip(), default))


@zkbrank.handle()
async def _handle_zkbrank(arp: Arparma):
    type_ = _normalize(_TYPE_MAP, str(arp.other_args.get("type_", "corporation")), "corporation")
    side = _normalize(_SIDE_MAP, str(arp.other_args.get("side", "k")), "k")
    metric = _normalize(_METRIC_MAP, str(arp.other_args.get("metric", "count")), "count")
    epoch = _normalize(_EPOCH_MAP, str(arp.other_args.get("epoch", "recent")), "recent")
    group = _normalize(_GROUP_MAP, str(arp.other_args.get("group", "all")), "all")
    try:
        limit = int(arp.other_args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))

    sort_key, primary_field, secondary_field = _METRIC_FIELDS[(side, metric)]

    rows = await _fetch_rows(type_, side, epoch, group, sort_key, primary_field)
    if not rows:
        await zkbrank.finish("未获取到排行榜数据，请稍后再试")

    view_rows = []
    for index, row in enumerate(rows[:limit]):
        if metric == "count":
            primary = f"{int(row[primary_field]):,}"
            secondary = f"{format_value(row[secondary_field])} ISK"
        else:
            primary = format_value(row[primary_field])
            secondary = f"{int(row[secondary_field]):,} 次"
        view_rows.append({
            "rank": index + 1,
            "name": row["name"] or f"ID {row['id']}",
            "avatar": row["avatar"].replace("size=32", "size=64") if row["avatar"] else "",
            "primary": primary,
            "secondary": secondary,
        })

    source_url = f"https://zkillboard.com/{type_}/ranks/{side}/{group}/{epoch}/1/"
    pic = await render_template(
        template_path=templates_path / "zkbrank",
        template_name="zkbrank.html.jinja2",
        data={
            "meta": {
                "type": type_,
                "type_label": _TYPE_LABELS[type_],
                "side": side,
                "side_label": _SIDE_LABELS[side],
                "metric": metric,
                "metric_label": _METRIC_LABELS[metric],
                "epoch": epoch,
                "epoch_label": _EPOCH_LABELS[epoch],
                "group": group,
                "group_label": _GROUP_LABELS[group],
                "source_url": source_url,
            },
            "rows": view_rows,
        },
        width=550,
        height=600,
    )

    if pic:
        await save_msg_cache(
            send_event=await zkbrank.send(
                message=UniMessage.image(raw=pic),
                reply_to=True,
            ),
            value_=source_url,
        )
    else:
        await zkbrank.finish("渲染排行榜失败，请稍后再试")


async def _fetch_rows(
    type_: str, side: str, epoch: str, group: str, sort_key: str, primary_field: str
) -> list[dict]:
    """
    获取排行榜数据：优先使用 zkillboard 服务端指标排序；
    失败（如 alltime 部分排序键 500）时回退到综合排名页并本地按指标重排
    """
    try:
        return await zkb_api.get_ranks(type_, kl=side, epoch=epoch, group=group, sort=sort_key)
    except Exception:
        pass

    try:
        rows = await zkb_api.get_ranks(type_, kl=side, epoch=epoch, group=group, sort="overallRank")
    except Exception:
        return []

    rows.sort(key=lambda r: r.get(primary_field, 0), reverse=True)
    return rows
