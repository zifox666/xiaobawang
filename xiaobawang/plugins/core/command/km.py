from arclet.alconna import Arparma
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    on_alconna,
    message_reaction
)

from ..helper.killmail import km
from ..utils.render import render_template, templates_path

km_cmd = Alconna(
    "/km",
    Args["kill_id", str],
    meta=CommandMeta(
        description="查询击毁邮件信息"
    ),
)

km_handler = on_alconna(km_cmd)

km_handler.shortcut(
    r"https://zkillboard\.com/kill/(\d+)/",
    command="/km {0}",
    fuzzy=True
)

@km_handler.handle()
async def handle_km(
        result: Arparma,
        event: Event,
):
    await message_reaction(event=event, emoji="🔥")
    kill_id = result["kill_id"]
    data = await km.get(kill_id)
    pic = await render_template(
        template_path=templates_path / "killmail",
        template_name="killmail.html.jinja2",
        data=data,
        width=665,
        height=900,
    )
    await km_handler.finish(MessageSegment.image(pic))
