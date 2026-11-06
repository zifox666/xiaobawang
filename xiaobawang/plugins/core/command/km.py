import re
from arclet.alconna import Arparma
from nonebot import logger, on_regex
from nonebot.internal.adapter import Event
from nonebot.params import RegexStr
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, UniMessage, on_alconna

from ..api.killmail import KillmailFetchError, KillmailNotFoundError, get_zkb_killmail
from ..helper.push.errors import send_with_media_retry
from ..helper.zkb.killmail import km
from ..utils.common.cache import save_msg_cache
from ..utils.common.emoji import emoji_action
from ..utils.render import render_template, templates_path
from ...bot_info import get_bot_info_data

__all__ = ["km_handler", "km_sub_push_test"]

KILL_URL = r"https?://(?:www\.)?zkillboard\.com/kill/(\d+)"

km_handler = on_regex(KILL_URL)

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
    kill_id = re.match(KILL_URL, url).group(1)
    try:
        data = await km.get(kill_id)
    except KillmailNotFoundError:
        await km_handler.finish("暂时没有从 zKillboard 获取到这封击杀邮件，可能还没同步或已不可用。")
    except KillmailFetchError:
        await km_handler.finish("获取击毁报告失败，请稍后再试。")
    if not data:  # 处理失败时 processor 返回空字典
        await km_handler.finish("处理击毁报告失败，请稍后再试。")

    data["title"] = "击毁报告"
    data["bot_info"] = get_bot_info_data()
    try:
        pic = await render_template(
            template_path=templates_path / "killmail",
            template_name="killmail_v3.html.jinja2",
            data=data,
            width=1060,
            height=100,
        )
    except Exception:
        logger.exception(f"[{kill_id}] 击毁报告渲染失败")
        await km_handler.finish("击毁报告渲染失败，请稍后再试。")
    try:
        receipt = await send_with_media_retry(lambda: UniMessage.image(raw=pic).send(target=event, reply_to=True))
    except Exception:
        logger.exception(f"[{kill_id}] 击毁报告图片发送失败")
        await km_handler.finish("击毁报告图片发送失败，请稍后再试。")
    # /br、/gif 依赖带结尾斜杠的链接格式，统一后再缓存
    await save_msg_cache(receipt, f"https://zkillboard.com/kill/{kill_id}/")


@km_sub_push_test.handle()
async def _(result: Arparma):
    try:
        await km.check(await get_zkb_killmail(result["kill_id"]))
    except KillmailFetchError as e:
        await km_sub_push_test.finish(f"获取击毁报告失败: {e}")
