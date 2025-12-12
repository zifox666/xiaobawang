import httpx
from nonebot.plugin import PluginMetadata
from nonebot import require
from datetime import datetime, UTC
from arclet.alconna import Alconna, Option, Args, CommandMeta, Arparma

from .config import plugin_config, Config

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_htmlrender")

from nonebot_plugin_alconna import on_alconna
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
        f"{plugin_config.pap_track_url}/oauth/pap?qq={user_info.user.id}\n"
        "授权后即可使用/pap命令查询PAP数据。"
    )


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
            await pap_query.finish(f"你没有授权机器人访问你的联盟seat，请私聊机器人发送/bind_frt进行操作")
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
        for idx, (_, info) in enumerate(sorted_items):
            result["ship"][str(idx)] = {
                "name": info["name"],
                "type": info["type"],
                "num": info["num"],
            }

        lines = [
            f"{result['characterName']} (ID: {result['charterID']})",
            f"总 PAP: {result['pap']}",
            "舰船参与统计：",
        ]
        for idx, item in result["ship"].items():
            lines.append(f"{idx}. {item['name']} [{item['type']}] x {item['num']}")

        await pap_query.finish("\n".join(lines))



