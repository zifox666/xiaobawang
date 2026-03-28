import re

from arclet.alconna import Alconna, Arparma, Option
from nonebot import logger
from nonebot import Bot, on_regex
from nonebot.internal.adapter import Event
from nonebot.params import RegexStr
from nonebot_plugin_alconna import UniMessage, on_alconna

from ..helper.zkb.killmail import km
from ..utils.common import convert_time, get_reply_message_id
from ..utils.common.cache import get_msg_cache, save_msg_cache
from ..utils.common.emoji import emoji_action
from ..utils.render import html2gif, html2pic, html2pic_br, html2pic_war_beacon

link = on_alconna(
    Alconna(
        "link",
    ),
    use_cmd_start=True,
    aliases={"链接"},
)

br = on_alconna(
    Alconna("br", Option("damage|d"), Option("timeline|t"), Option("summary|s"), Option("composition|c")),
    use_cmd_start=True,
)

br_preview_time = on_regex(r"https://br.evetools.org/br/([a-zA-Z0-9]{24})")
br_preview_zkb = on_regex(r"https://zkillboard.com/related/([0-9]{8})/([0-9]{12})/")
br_preview_alt = on_regex(r"https://br.evetools.org/related/([0-9]{8})/([0-9]{12})")
wb_preview_alt = on_regex(r"https://warbeacon.net/br/report/([a-zA-Z0-9\-]+)")
wb_preview_time = on_regex(r"https://warbeacon.net/br/related/([0-9]{8})/([0-9]{12})")
kmapp_preview_time = on_regex(r"https://killmail.app/related/([0-9]{8})/([0-9]{12})")
kmapp_preview_alt = on_regex(r"https://killmail.app/br/([a-zA-Z0-9\-]+)") # https://killmail.app/br/PTWi4A7Pyh-atioth-2026-03-28


@link.handle()
async def _(
    bot: Bot,
    event: Event,
):
    msg_id = await get_reply_message_id(bot, event)
    if not msg_id:
        return
    save_link = await get_msg_cache(msg_id)
    if save_link:
        await link.send(UniMessage.reply(msg_id) + UniMessage.text(save_link))


@br.handle()
async def _(
    bot: Bot,
    event: Event,
    result: Arparma,
):
    click_selector = "参与者"
    if result.find("damage"):
        click_selector = "伤害"
    elif result.find("timeline"):
        click_selector = "时间线"
    elif result.find("summary"):
        click_selector = "统计"
    elif result.find("composition"):
        click_selector = "构成"

    msg_id = await get_reply_message_id(bot, event)
    save_link = await get_msg_cache(msg_id)
    if not save_link or not isinstance(save_link, str):
        await br.finish("未找到相关链接或链接格式不正确")
    if save_link.startswith("https://zkillboard"):
        matched = re.search(r"https://zkillboard\.com/kill/(\d+)/", save_link)
        kill_id = matched.group(1)
        data = await km.get(kill_id)
        br_link = f"https://warbeacon.net/br/related/{data['solar_system_id']}/{convert_time(data['killmail_time'])}"
        no_url = False
    else:
        br_link = save_link
        no_url = True

    if br_link:
        if not no_url:
            await save_msg_cache(
                await br.send(UniMessage.reply(msg_id) + UniMessage.text(br_link)),
                br_link,
            )
        await save_msg_cache(
            await br.send(
                UniMessage.reply(msg_id)
                + UniMessage.image(
                    raw=await html2pic_war_beacon(
                            url=br_link,
                            element_class="compact-teams" if click_selector != "时间线" else "battle-report-involved",
                            click_text=click_selector,
                        )
                )
            ),
            br_link,
        )


@br_preview_alt.handle()
async def _(event: Event, url: str = RegexStr()):
    matched = re.search(r"https://br.evetools.org/related/([0-9]{8})/([0-9]{12})", url)
    if not matched:
        return

    await emoji_action(event)
    system, time = matched.groups()
    url = f"https://warbeacon.net/br/related/{system}/{time}"

    await save_msg_cache(
        await UniMessage.image(
            raw=await html2pic_war_beacon(
                url=url,
                element_class="compact-teams",
                click_text=None,
            )
        ).send(target=event, reply_to=True),
        url,
    )


@br_preview_time.handle()
async def _(event: Event, url: str = RegexStr()):
    await emoji_action(event)
    await save_msg_cache(
        await UniMessage.image(
            raw=await html2pic_br(
                url=url,
                element=".development",
                hide_elements=["bp3-navbar", "bp3-fixed-top", "bp3-dark", "_2ds1SVI_"],
            )
        ).send(target=event, reply_to=True),
        url,
    )


@br_preview_zkb.handle()
async def _(event: Event, url: str = RegexStr()):
    matched = re.match(r"https://zkillboard.com/related/([0-9]+)/([0-9]+)/", url)
    if not matched:
        return
    await emoji_action(event)
    system, time = matched.groups()
    url = f"https://warbeacon.net/br/related/{system}/{time}"

    await save_msg_cache(
        await UniMessage.image(
            raw=await html2pic_war_beacon(
                url=url,
                element_class="compact-teams",
                click_text=None,
            )
        ).send(target=event, reply_to=True),
        url,
    )


@wb_preview_alt.handle()
@wb_preview_time.handle()
async def _(event: Event, url: str = RegexStr()):
    await emoji_action(event)
    await save_msg_cache(
        await UniMessage.image(
            raw=await html2pic_war_beacon(
                url=url,
                element_class="compact-teams",
                click_text=None,
            )
        ).send(target=event, reply_to=True),
        url,
    )

@kmapp_preview_time.handle()
@kmapp_preview_alt.handle()
async def _(event: Event, url: str = RegexStr()):
    await emoji_action(event)

    pic = await html2pic(
        url=url,
        viewport_width=1280,
        viewport_height=720,
        element="main"
    )
    await save_msg_cache(
        await UniMessage.image(raw=pic).send(target=event, reply_to=True),
        url,
    )

    try:
        gif = await html2gif(
            url=url,
            element="main",
            viewport_width=1280,
            viewport_height=850,
            fps=8,
            min_output_seconds=8,
            max_output_seconds=15,
            seek_wait_ms=200,
        )
        await save_msg_cache(
            await UniMessage.image(raw=gif).send(target=event),
            url,
        )
    except Exception as e:
        logger.warning(f"killmail.app GIF 生成失败: {e!s}")
