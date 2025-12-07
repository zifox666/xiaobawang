from arclet.alconna import Alconna, Args, Option
from nonebot_plugin_alconna import CommandMeta, UniMessage, on_alconna

from ..helper.statics import data_analysis
from ..utils.render import render_template, templates_path

__all__ = ["statics"]

statics = on_alconna(
    Alconna(
        "statics",
          Option("--days|-d", Args["days", int], default=30),
            CommandMeta(description="数据统计展示", usage="/statics [--days 天数]")),
    use_cmd_start=True,
    aliases={"statics", "统计"},
)


@statics.handle()
async def handle_statics(
    days: int = 30,
):
    pic = await render_template(
        template_path=templates_path / "statics",
        template_name="statics.html.jinja2",
        data=await data_analysis.generate(days),
        width=1280,
    )
    if pic:
        await statics.finish(UniMessage.image(raw=pic))
