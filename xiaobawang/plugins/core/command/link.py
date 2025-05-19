import re

from arclet.alconna import Alconna, Arparma, Option
from nonebot.params import RegexStr
from nonebot_plugin_alconna import on_alconna, UniMessage
from nonebot import Bot, on_regex
from nonebot.internal.adapter import Event

from ..helper.zkb.killmail import km
from ..utils.common import get_reply_message_id, convert_time
from ..utils.common.emoji import emoji_action
from ..utils.common.cache import get_msg_cache, save_msg_cache
from ..utils.render import html2pic_br

link = on_alconna(
    Alconna(
        "link",
    ),
    use_cmd_start=True,
    aliases={"链接"},
)

br = on_alconna(
    Alconna(
        "br",
        Option("damage|d"),
        Option("timeline|t"),
        Option("summary|s"),
        Option("composition|c")
    ),
    use_cmd_start=True,
)

br_preview_time = on_regex(r"https://br.evetools.org/br/([a-zA-Z0-9]{24})")
br_preview_alt = on_regex(r"https://br.evetools.org/related/([0-9]{8})/([0-9]{12})")


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
        await link.send(
            UniMessage.reply(msg_id) + UniMessage.text(save_link)
        )


@br.handle()
async def _(
        bot: Bot,
        event: Event,
        result: Arparma,
):
    click_selector = "involved"
    if result.find("damage"):
        click_selector = "damage"
    elif result.find("timeline"):
        click_selector = "timeline"
    elif result.find("summary"):
        click_selector = "summary"
    elif result.find("composition"):
        click_selector = "composition"

    msg_id = await get_reply_message_id(bot, event)
    save_link = await get_msg_cache(msg_id)
    if not save_link or not isinstance(save_link, str):
        await br.finish("未找到相关链接或链接格式不正确")
    if save_link.startswith("https://zkillboard"):
        matched = re.search(r"https://zkillboard\.com/kill/(\d+)/", save_link)
        kill_id = matched.group(1)
        data = await km.get(kill_id)
        br_link = f"https://br.evetools.org/related/{data['solar_system_id']}/{convert_time(data['killmail_time'])}"
        no_url = False
    else:
        br_link = save_link
        no_url = True

    if br_link:
        if not no_url:
            await save_msg_cache(
                await br.send(
                    UniMessage.reply(msg_id) + UniMessage.text(br_link)
                ),
                br_link,
            )
        await save_msg_cache(
            await br.send(
                UniMessage.reply(msg_id) +
                UniMessage.image(
                    raw=await html2pic_br(
                        url=br_link,
                        element=".development",
                        hide_elements=['bp3-navbar', 'bp3-fixed-top', 'bp3-dark', '_2ds1SVI_', 'MNHgrY8N', 'bp3-dark'],
                        click_selector=click_selector,
                    )
                )
            ),
            br_link
        )


@br_preview_time.handle()
async def _(
        event: Event,
        url: str = RegexStr()
):
    await emoji_action(event)
    await save_msg_cache(
        await UniMessage.image(
            raw=await html2pic_br(
                url=url,
                element=".development",
                hide_elements=['bp3-navbar', 'bp3-fixed-top', 'bp3-dark', '_2ds1SVI_'],
            )
        ).send(
            target=event,
            reply_to=True
        ),
        url
    )


@br_preview_alt.handle()
async def _(
        event: Event,
        url: str = RegexStr()
):
    await emoji_action(event)
    await save_msg_cache(
        await UniMessage.image(
            raw=await html2pic_br(
                url=url,
                element=".development",
                hide_elements=['bp3-navbar', 'bp3-fixed-top', 'bp3-dark', '_2ds1SVI_'],
            )
        ).send(
            target=event,
            reply_to=True
        ),
        url
    )

