import httpx
from nonebot.plugin import PluginMetadata
from nonebot import require
from datetime import datetime, UTC
from arclet.alconna import Alconna, Option, Args, CommandMeta, Arparma

from .config import plugin_config, Config

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_htmlrender")

from nonebot_plugin_alconna import on_alconna, UniMessage, Subcommand
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_htmlrender import template_to_pic


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
        CommandMeta(
            description="查询FRT联盟成员PAP",
            usage="/pap -m <month> -y <year>",
        )
    ),
    use_cmd_start=True
)
frt_bind = on_alconna(
    Alconna(
        "bind_frt",
        CommandMeta(
            description="绑定FRT联盟Seat授权",
            usage="/bind_frt",
        )
    ),
    use_cmd_start=True
)


@frt_bind.handle()
async def _handle_bind_frt(
    user_info: Uninfo,
):
    if not user_info.scene.is_private:
        await frt_bind.finish("请在私聊中使用此命令进行绑定")
    await frt_bind.finish(
        "请前往以下链接进行授权绑定：\n"
        f"{plugin_config.pap_track_url}/oauth/login?qq={user_info.user.id}\n"
        "授权后即可使用/pap命令查询PAP数据。"
    )


async def get_corp_name(corp_id: int) -> str:
    """通过ESI API获取军团名称"""
    if not corp_id:
        return "Unknown Corporation"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://esi.evetech.net/latest/universe/names/",
                json=[corp_id],
                headers={"Content-Type": "application/json"}
            )
            r.raise_for_status()
            data = r.json()
            return data[0].get("name", "Unknown Corporation") if data else "Unknown Corporation"
    except Exception:
        return "Unknown Corporation"


@pap_query.assign("rank")
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

    async with httpx.AsyncClient(
        headers={"x-api-key": f"{plugin_config.api_key}"}
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
        for corp_id in corp_ids:
            corp_name = await get_corp_name(int(corp_id))
            corp_names[str(corp_id)] = corp_name

        template_data = {
            "year": data.get("year"),
            "month": month if month != 0 else None,
            "corporation_rankings": data.get("corporation_rankings", [])[:10],
            "group_rankings": data.get("group_rankings", [])[:10],
            "ship_rankings": data.get("ship_rankings", [])[:3],
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


@pap_query.handle()
async def _handle_pap(
    arp: Arparma,
    user_info: Uninfo,
):
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
            await pap_query.finish(f"你没有授权机器人访问你的联盟seat，请私聊机器人发送\n\n/bind_frt\n\n进行操作")
        r.raise_for_status()
        data = r.json()
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

        result = {
            "pap": pap,
            "name": data.get("main_character"),
            "charterID": data.get("main_character_id"),
            "characterName": data.get("main_character"),
            "ship": {},
        }

        sorted_items = sorted(
            ship_stats.items(),
            key=lambda kv: kv[1]["num"],
            reverse=True,
        )
        for idx, (type_id, info) in enumerate(sorted_items):
            result["ship"][str(idx)] = {
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
            "ship": result["ship"],
            "fleets": fleets,
            "ranking": data.get("ranking"),
            "corporation_id": data.get("ranking", {}).get("corporation_id", ""),
            "corporation_name": await get_corp_name(data.get("ranking", {}).get("corporation_id", 0)),
        }

        pic = await template_to_pic(
            template_path=str(__file__).replace("__init__.py", ""),
            template_name="template.html.jinja2",
            templates=template_data,
            pages={
                "viewport": {"width": 1200, "height": 100},
                "base_url": f"file://{__file__.replace('__init__.py', '')}",
            },
        )

        await pap_query.finish(UniMessage.image(raw=pic))



