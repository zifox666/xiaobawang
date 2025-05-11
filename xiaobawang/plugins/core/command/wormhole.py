from arclet.alconna import Alconna, Args

from nonebot_plugin_alconna import on_alconna, UniMessage

from ..helper.wormhole import WormholeHelper

__all__ = ["wormhole"]

from ..utils.render import render_template, templates_path

wormhole = on_alconna(
    Alconna(
        "wormhole",
        Args["args", str]
    ),
    use_cmd_start=True,
    aliases=("wh", "cd", "虫洞")
)


@wormhole.handle()
async def handle_wormhole(
        args: str,
):
    wormhole_helper = WormholeHelper()
    data, type_ = await wormhole_helper.get(args)
    print(data)
    if not data:
        await wormhole.finish(f"没有找到相关数据[{args}]")
    pic = await render_template(
        template_path=templates_path / "wormhole",
        template_name="system.html.jinja2" if type_ == "system" else "wormhole.html.jinja2",
        data=data,
        width=1080 if type_ == "system" else 400,
    )
    if pic:
        await wormhole.finish(
            UniMessage.image(raw=pic),
            reply_to=True
        )

