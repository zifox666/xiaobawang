import re

from arclet.alconna import Alconna, Args
from nonebot_plugin_alconna import on_alconna, UniMessage
from nonebot import Bot
from nonebot.internal.adapter import Event

from ..helper.zkb.killmail import km
from ..utils.common import get_reply_message_id, convert_time
from ..utils.common.cache import get_msg_cache
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
    ),
    use_cmd_start=True,
)

br_preview = on_alconna(
    Alconna(
        "br_preview",
        Args["br_link", str]
    ),
    use_cmd_start=True
)

br_preview.shortcut(
    r"https://br.evetools.org/related/([0-9]{8})/([0-9]{12})",
    command="/br_preview https://br.evetools.org/related/{0}/{1}",
    fuzzy=True
)
br_preview.shortcut(
    r"https://br.evetools.org/br/([a-zA-Z0-9]{24})",
    command="/br_preview https://br.evetools.org/br/{0}",
    fuzzy=True
)


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
):
    msg_id = await get_reply_message_id(bot, event)
    if not msg_id:
        return
    save_link = await get_msg_cache(msg_id)
    matched = re.search(r"https://zkillboard\.com/kill/(\d+)/", save_link)
    kill_id = matched.group(1)
    data = await km.get(kill_id)
    br_link = f"https://br.evetools.org/related/{data['solar_system_id']}/{convert_time(data['killmail_time'])}"
    if br_link:
        await br.send(
            UniMessage.reply(msg_id) + UniMessage.text(br_link)
        )
        await br.finish(
            UniMessage.reply(msg_id) +
            UniMessage.image(
                raw=await html2pic_br(
                    url=br_link,
                    element=".development",
                    hide_elements=['bp3-navbar', 'bp3-fixed-top', 'bp3-dark', '_2ds1SVI_'],
                )
            )
        )


@br_preview.handle()
async def _(
        event: Event,
        br_link: str = Args["br_link", str]
):
    await br_preview.finish(
        UniMessage.reply(event.message_id) +
        UniMessage.image(
            raw=await html2pic_br(
                url=br_link,
                element=".development",
                hide_elements=['bp3-navbar', 'bp3-fixed-top', 'bp3-dark', '_2ds1SVI_'],
            )
        )
)

