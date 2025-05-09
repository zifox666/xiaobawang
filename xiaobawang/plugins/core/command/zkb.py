from arclet.alconna import Alconna, Option, Args, MultiVar, Arparma
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna import on_alconna

zkb = on_alconna(
    Alconna(
        "zkb",
        Args["args", MultiVar(str)],
        Option("-t|--type", Args["type", str], default="char"),
    ),
    use_cmd_start=True,
)


@zkb.handle()
async def handle_zkb(
        arp: Arparma,
        event: Event,
):
    args = " ".join(arp.main_args.get("args"))
    type_ = arp.other_args.get("type", "char")


