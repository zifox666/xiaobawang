from pathlib import Path

import nonebot
from nonebot import require

from .almanac import DailyLuck
from .router import router as daily_luck_router

require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_uninfo")

from fastapi import FastAPI
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_htmlrender import template_to_pic
from nonebot_plugin_uninfo import Uninfo

app: FastAPI = nonebot.get_app()
app.include_router(daily_luck_router, prefix="")

plugin_path = Path(__file__).resolve().parent
templates_path = plugin_path / "templates"


params = {"use_cmd_start": True, "block": True, "priority": 13}
daily_luck = on_alconna(
    "今日黄历",
    aliases=("EVE老黄历", "老黄历"),
    **params
)


@daily_luck.handle()
async def _(user_info: Uninfo):
    luck_info = DailyLuck(user_id=user_info.user.id)
    _json = {
        "today_str": luck_info.today_str,
        "good_events": luck_info.good_events,
        "bad_events": luck_info.bad_events,
        "direction": luck_info.direction,
        "ships": luck_info.chosen_ships,
        "locals": luck_info.chosen_spaces,
        "goddess_value": luck_info.goddess_value,
        "luck_level": luck_info.get_luck_level(),
        "user_name": user_info.user.nick if user_info.user.nick else user_info.user.name,
        "is_screenshot": True,
    }

    await daily_luck.finish(
        UniMessage.image(
            raw=await render(_json)
        ),
        reply_to=True
    )


async def render(_json) -> bytes:

    return await template_to_pic(
        template_path=str(templates_path),
        template_name="almanac.html.jinja2",
        templates=_json,
        pages={
            "viewport": {"width": 350, "height": 10},
            "base_url": f"file://{templates_path}",
        },
    )
