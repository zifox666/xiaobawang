import calendar
from datetime import UTC, datetime
import traceback

from arclet.alconna import Alconna, Args, Arparma, CommandMeta, MultiVar, Option
import httpx
from nonebot import logger, require
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

from .config import Config, plugin_config

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_htmlrender")

from nonebot_plugin_alconna import Subcommand, UniMessage, on_alconna
from nonebot_plugin_htmlrender import template_to_pic
from nonebot_plugin_uninfo import Uninfo

__plugin_meta__ = PluginMetadata(
    name="FRT PAP 查询插件",
    description="查询FRT联盟成员PAP",
    usage="没什么用",
    type="application",
    config=Config,
    extra={},
)


pap_query = on_alconna(
    Alconna(
        "pap",
        Option("-m|--month", Args["month", str], default="0"),
        Option("-y|--year", Args["year", str], default="0"),
        Subcommand(
            "rank",
            Option("-m|--month", Args["month", str], default="0"),
            Option("-y|--year", Args["year", str], default="0"),
        ),
        Subcommand(
            "query",
            Args["name", MultiVar(str)],
            Option("-m|--month", Args["month", str], default="0"),
            Option("-y|--year", Args["year", str], default="0"),
        ),
        CommandMeta(
            description="查询FRT联盟成员PAP",
            usage="/pap -m <month> -y <year>",
        )
    ),
    use_cmd_start=True
)
pap_query_by_name = pap_query.dispatch("query")
pap_rank = pap_query.dispatch("rank")

npc_kills_query = on_alconna(
    Alconna(
        "刷怪报表",
        Option("-m|--month", Args["month", str], default="0"),
        Option("-y|--year", Args["year", str], default="0"),
        CommandMeta(
            description="查询刷怪报表",
            usage="/刷怪报表 -m <month> -y <year>",
        )
    ),
    use_cmd_start=True
)


async def get_corp_name(corp_id: int) -> str:
    """通过ESI API获取军团名称"""
    if not corp_id:
        return "Unknown Corporation"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://esi.evetech.net/universe/names/",
                json=[corp_id],
                headers={
                    "Content-Type": "application/json",
                    "X-Compatibility-Date": "2025-12-16",
                }
            )
            r.raise_for_status()
            data = r.json()
            return data[0].get("name", "Unknown Corporation") if data else "Unknown Corporation"
    except Exception:
        return "Unknown Corporation"


@pap_rank.handle()
async def _handle_pap_rank(
    arp: Arparma,
    user_info: Uninfo,
):
    month = arp.other_args.get("month", "0")
    year = arp.other_args.get("year", "0")
    if not month.isdigit() or not year.isdigit():
        await pap_query.finish("月份和年份必须为数字")
    month = int(month)
    year = int(year)

    if year == 0:
        year = datetime.now(UTC).year

    url = f"{plugin_config.pap_track_url}/api/rank?year={year}"
    if month != 0:
        url += f"&month={month}"

    try:
        async with httpx.AsyncClient(
            headers={"x-api-key": f"{plugin_config.api_key}"},
            timeout=120
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()

        # 获取军团名称（包括军团排名和个人排名中的军团）
        corp_ids = set([corp["corporation_id"] for corp in data.get("corporation_rankings", [])])
        # 添加个人排名中的军团ID
        for player in data.get("group_rankings", [])[:10]:
            corp_ids.add(player["corporation_id"])

        corp_names = {}
        for corp_id in list(corp_ids):
            if not corp_id:
                continue
            try:
                corp_name = await get_corp_name(int(corp_id))
                corp_names[str(corp_id)] = corp_name
            except Exception as e:
                logger.warning(f"Failed to get corp name for {corp_id}: {e}")
                corp_names[str(corp_id)] = f"Corp #{corp_id}"

        template_data = {
            "year": data.get("year"),
            "month": month if month != 0 else None,
            "corporation_rankings": data.get("corporation_rankings", [])[:10],
            "group_rankings": data.get("group_rankings", [])[:10],
            "ship_rankings": data.get("ship_rankings", [])[:3],
            "slacker_rankings": data.get("slacker_rankings", [])[:10],
            "corp_names": corp_names,
        }

        pic = await template_to_pic(
            template_path=str(__file__).replace("__init__.py", ""),
            template_name="rank.html.jinja2",
            templates=template_data,
            pages={
                "viewport": {"width": 1200, "height": 100},
                "base_url": f"file://{__file__.replace('__init__.py', '')}",
            },
        )

        await pap_query.finish(UniMessage.image(raw=pic))
    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"Error in rank query: {e} \n {traceback.format_exc()}")
        await pap_query.finish(f"排名查询失败: {e!s}")


async def _render_pap_pic(data: dict, month: int, year: int) -> bytes:
    """从API响应data中提取ship统计并渲染PAP模板，返回图片二进制。"""
    pap = data.get("total_pap", 0)
    fleets = data.get("fleets", [])

    ship_stats: dict[str, dict] = {}
    for fleet in fleets:
        ship = fleet.get("ship", {})
        type_id = ship.get("typeID") or ship.get("type_id") or ""
        type_name = ship.get("typeName") or ship.get("type_name") or "Unknown"
        group_name = ship.get("groupName") or ship.get("group_name") or "Unknown"

        key = str(type_id) if str(type_id) != "" else type_name
        if key not in ship_stats:
            ship_stats[key] = {
                "name": type_name,
                "type": group_name,
                "num": 0,
            }
        ship_stats[key]["num"] += 1

    sorted_items = sorted(
        ship_stats.items(),
        key=lambda kv: kv[1]["num"],
        reverse=True,
    )
    ship_result: dict[str, dict] = {}
    for idx, (type_id, info) in enumerate(sorted_items):
        ship_result[str(idx)] = {
            "name": info["name"],
            "type": info["type"],
            "num": info["num"],
            "type_id": type_id,
        }

    template_data = {
        "name": data.get("main_character"),
        "charterID": data.get("main_character_id"),
        "characterName": data.get("main_character"),
        "pap": pap,
        "yearly_total_pap": data.get("yearly_total_pap", 0),
        "month": month,
        "year": year,
        "ship": ship_result,
        "fleets": fleets,
        "ranking": data.get("ranking"),
        "corporation_id": data.get("ranking", {}).get("corporation_id", ""),
        "corporation_name": await get_corp_name(data.get("ranking", {}).get("corporation_id", 0)),
    }

    return await template_to_pic(
        template_path=str(__file__).replace("__init__.py", ""),
        template_name="template.html.jinja2",
        templates=template_data,
        pages={
            "viewport": {"width": 1200, "height": 100},
            "base_url": f"file://{__file__.replace('__init__.py', '')}",
        },
    )


@pap_query_by_name.handle()
async def _handle_pap_query(
    arp: Arparma,
):
    month = arp.other_args.get("month", "0")
    year = arp.other_args.get("year", "0")
    if not month.isdigit() or not year.isdigit():
        await pap_query.finish("月份和年份必须为数字")
    character_name = " ".join(arp.name)

    month = int(month)
    year = int(year)

    if month == 0:
        month = datetime.now(UTC).month
    if year == 0:
        year = datetime.now(UTC).year
    
    async with httpx.AsyncClient(
        headers={"x-api-key": f"{plugin_config.api_key}"},
        timeout=120
    ) as client:
        url = f"{plugin_config.pap_track_url}/api/pap/main?main_character={character_name}&month={month}&year={year}"
        r = await client.get(url)
        if r.status_code == 404:
            await pap_query.finish(f"未找到角色[{character_name}]的PAP数据，可能是因为该角色没有PAP记录或者名字输入有误。")
        r.raise_for_status()
        data = r.json()
        pic = await _render_pap_pic(data, month, year)
        await pap_query.finish(UniMessage.image(raw=pic))


@npc_kills_query.handle()
async def _handle_npc_kills(
    arp: Arparma,
    user_info: Uninfo,
):
    month = arp.other_args.get("month", "0")
    year = arp.other_args.get("year", "0")
    if not month.isdigit() or not year.isdigit():
        await npc_kills_query.finish("月份和年份必须为数字")
    month = int(month)
    year = int(year)

    if month == 0:
        month = datetime.now(UTC).month
    if year == 0:
        year = datetime.now(UTC).year

    start_date = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end_date = f"{year}-{month:02d}-{last_day:02d}"

    try:
        async with httpx.AsyncClient(
            headers={"x-api-key": f"{plugin_config.api_key}"},
            timeout=120,
        ) as client:
            url = (
                f"{plugin_config.pap_track_url}/api/npc/kills"
                f"?qq={user_info.user.id}&start_date={start_date}&end_date={end_date}&lang=zh"
            )
            r = await client.get(url)
            if r.status_code == 404:
                await npc_kills_query.finish(
                    f"未找到刷怪数据，可能是因为没有记录或未授权。\n"
                    f"请前往 {plugin_config.pap_track_url}/oauth/login 进行授权"
                )
            r.raise_for_status()
            data = r.json()

        def _fmt_isk(v: float) -> str:
            return f"{v:,.0f}"

        summary_raw = data.get("summary", {})
        trend_raw: list[dict] = data.get("trend", [])
        # 为每条趋势数据预计算格式化金额，供模板直接使用
        for item in trend_raw:
            item["amount_fmt"] = _fmt_isk(item.get("amount", 0))

        template_data = {
            "year": year,
            "month": month,
            "summary": {
                "total_bounty": _fmt_isk(summary_raw.get("total_bounty", 0)),
                "total_ess": _fmt_isk(summary_raw.get("total_ess", 0)),
                "total_tax": _fmt_isk(summary_raw.get("total_tax", 0)),
                "actual_income": _fmt_isk(summary_raw.get("actual_income", 0)),
                "total_records": summary_raw.get("total_records", 0),
                "estimated_hours": int(summary_raw.get("estimated_hours", 0)),
            },
            "by_npc": data.get("by_npc", []),
            "trend": trend_raw,
        }

        pic = await template_to_pic(
            template_path=str(__file__).replace("__init__.py", ""),
            template_name="npc_kills.html.jinja2",
            templates=template_data,
            pages={
                "viewport": {"width": 1000, "height": 100},
                "base_url": f"file://{__file__.replace('__init__.py', '')}",
            },
        )
        await npc_kills_query.finish(UniMessage.image(raw=pic))
    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"Error in npc kills query: {e} \n {traceback.format_exc()}")
        await npc_kills_query.finish(f"刷怪报表查询失败: {e!s}")


@pap_query.handle()
async def _handle_pap(
    arp: Arparma,
    user_info: Uninfo,
):
    if arp.find("rank") or arp.find("query"):
        return
    month = arp.other_args.get("month", "0")
    year = arp.other_args.get("year", "0")
    if not month.isdigit() or not year.isdigit():
        await pap_query.finish("月份和年份必须为数字")
    month = int(month)
    year = int(year)

    if month == 0:
        month = datetime.now(UTC).month
    if year == 0:
        year = datetime.now(UTC).year

    async with httpx.AsyncClient(
        headers={"x-api-key": f"{plugin_config.api_key}"}
    ) as client:
        url = f"{plugin_config.pap_track_url}/api/pap?qq={user_info.user.id}&month={month}&year={year}"
        r = await client.get(url)
        if r.status_code == 404:
            await pap_query.finish(f"你没有授权机器人访问你的联盟seat\n 请前往{plugin_config.pap_track_url}/oauth/login 进行授权\n 支持 pap/刷怪报表")
        r.raise_for_status()
        data = r.json()
        pic = await _render_pap_pic(data, month, year)
        await pap_query.finish(UniMessage.image(raw=pic))

