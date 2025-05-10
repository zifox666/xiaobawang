from arclet.alconna import Alconna, Option, Args, MultiVar, Arparma
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna import on_alconna, UniMessage

from ..utils.common.emoji import emoji_action
from ..api.esi.universe import esi_client
from ..api.zkillboard import zkb_api
from ..helper.zkb.stats import ZkbStats
from ..utils.common.cache import save_msg_cache

__all__ = ["zkb", "zkb_preview"]

zkb = on_alconna(
    Alconna(
        "zkb",
        Args["args", MultiVar(str)],
        Option("-t|--type", Args["type", str], default="character"),
    ),
    use_cmd_start=True,
)

zkb_preview = on_alconna(
    Alconna(
        "{:.*}https://zkillboard.com/{type:str}/{id:int}/{:.*}",
        separators=["\x04", "\n"],
    ),
    use_cmd_start=False,
)


@zkb_preview.handle()
async def handle_zkb(
        arp: Arparma,
        event: Event
):
    await emoji_action(event)
    result = arp.header
    entity_type = result["type"]
    entity_id = result["id"]

    if entity_type not in ["character", "corporation"]:
        return

    pic = await ZkbStats(
        await zkb_api.get_stats(entity_type, entity_id)
    ).render()

    if pic:
        await save_msg_cache(
            send_event=await zkb_preview.send(
                UniMessage.reply(event.message_id) +
                UniMessage.image(raw=pic)
            ),
            value_=f"https://zkillboard.com/{entity_type}/{entity_id}/",
        )
    else:
        await zkb_preview.finish("获取数据失败，请稍后再试")


@zkb.handle()
async def handle_zkb(
        arp: Arparma,
        event: Event,
):
    args = " ".join(arp.main_args.get("args"))
    type_ = arp.other_args.get("type", "character")

    data = await esi_client.get_universe_id(type_=f"{type_}s", name=args)
    id_ = data.get("id")
    if id_ is None:
        msg = f"未找到[{type_}]{args}"
        if type_ != "character":
            msg += "\n查询军团请使用/zkb name --type corporation"
        await zkb.finish(msg)

    pic = await ZkbStats(
        await zkb_api.get_stats(type_, id_)
    ).render()

    if pic:
        await save_msg_cache(
            send_event=await zkb.send(
                UniMessage.reply(event.message_id) +
                UniMessage.image(raw=pic)
            ),
            value_=f"https://zkillboard.com/{type_}/{id_}/",
        )
    else:
        await zkb.finish("获取数据失败，请稍后再试")

