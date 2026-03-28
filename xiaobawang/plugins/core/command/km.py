import re
from arclet.alconna import Arparma
from nonebot import logger, on_regex
from nonebot.internal.adapter import Event
from nonebot.params import RegexStr
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, UniMessage, on_alconna

from ..api.killmail import get_zkb_killmail
from ..helper.zkb.killmail import km
from ..utils.common.cache import save_msg_cache
from ..utils.common.emoji import emoji_action
from ..utils.render import render_template, templates_path

__all__ = ["km_handler", "km_sub_push_test"]

km_handler = on_regex(r"https://zkillboard.com/kill/([0-9]{9})/")

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
    event: Event,
    url: str = RegexStr(),
):
    await emoji_action(event)
    matched = re.match(r"https://zkillboard.com/kill/([0-9]{9})/", url)
    if not matched:
        logger.debug(f"URL不匹配: {url}")
        return
    kill_id = matched.group(1)
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
        await UniMessage.image(raw=pic).send(target=event, reply_to=True),
        url,
    )


@km_sub_push_test.handle()
async def _(result: Arparma):
    await km.check(await get_zkb_killmail(result["kill_id"]))
