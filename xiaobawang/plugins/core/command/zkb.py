from arclet.alconna import Alconna, Option, Args, MultiVar, Arparma
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna import on_alconna, UniMessage

from xiaobawang.plugins.core.api.esi.universe import esi_client
from xiaobawang.plugins.core.api.zkillboard import zkb_api
from xiaobawang.plugins.core.helper.zkb.stats import ZkbStats

zkb = on_alconna(
    Alconna(
        "zkb",
        Args["args", MultiVar(str)],
        Option("-t|--type", Args["type", str], default="character"),
    ),
    use_cmd_start=True,
)


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
        await zkb.finish(
            UniMessage.image(raw=pic),
        )
    else:
        await zkb.finish("获取数据失败，请稍后再试")

