from arclet.alconna import Arparma
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, UniMessage, on_alconna

from ..api.killmail import get_zkb_killmail
from ..helper.zkb.killmail import km
from ..utils.common.cache import save_msg_cache
from ..utils.common.emoji import emoji_action
from ..utils.render import render_template, templates_path

__all__ = ["km_handler", "km_sub_push_test"]

km_handler = on_alconna(
    Alconna(
        "km",
        Args["kill_id", str],
        meta=CommandMeta(description="查询击毁邮件信息"),
    ),
    use_cmd_start=True,
)

km_handler.shortcut(r"https://zkillboard\.com/kill/(\d+)/", command="/km {0}", fuzzy=True)

km_sub_push_test = on_alconna(
    Alconna(
        "km_push",
        Args["kill_id", str],
        meta=CommandMeta(description="测试击毁邮件推送", hide=True),
    ),
    use_cmd_start=True,
)


@km_handler.handle()
async def handle_km(
    result: Arparma,
    event: Event,
):
    await emoji_action(event)
    kill_id = result["kill_id"]
    data = await km.get(kill_id)
    data["title"] = "击毁报告"
    pic = await render_template(
        template_path=templates_path / "killmail",
        template_name="killmail.html.jinja2",
        data=data,
        width=665,
        height=100,
    )
    await save_msg_cache(
        await km_handler.send(UniMessage.reply(event.message_id) + UniMessage.image(raw=pic)),
        f"https://zkillboard.com/kill/{kill_id}/",
    )


@km_sub_push_test.handle()
async def _(result: Arparma):
    await km.check(await get_zkb_killmail(result["kill_id"]))
