from datetime import datetime, timezone

from arclet.alconna import Alconna, Args, CommandMeta
from nonebot_plugin_alconna import on_alconna

from xiaobawang.plugins.core.api.common import get_exchangerate

__all__ = ["evetime", "hl"]

hl = on_alconna(
    Alconna(
        "hl",
        Args["value", float]["currency", str],
        meta=CommandMeta(
            usage="/hl <数值> <货币代码>",
            description="将指定货币转换为人民币",
        )
    ),
    use_cmd_start=True,
    aliases=("汇率", "exchangerate"),
)

evetime = on_alconna(
    Alconna(
        "evetime",
        meta=CommandMeta(
            usage="/evetime",
            description="获取当前EVE时间",
        )
    ),
    use_cmd_start=True,
    aliases=("EVE时间", "eve时间")
)


hl_aliases = {
    "RMB": "CNY",
    "美元": "USD",
    "欧元": "EUR",
    "日元": "JPY",
    "英镑": "GBP",
    "港币": "HKD",
    "新加坡元": "SGD",
    "澳元": "AUD",
    "卢布": "RUB",
}


@hl.handle()
async def handle_hl(
    value: float = Args["value", float],
    currency: str = Args["currency", str],
):
    if u := hl_aliases.get(currency):
        currency = u
    if currency == "CNY":
        return
    rates = await get_exchangerate()
    if currency not in rates:
        await hl.finish("不支持的货币")

    rate = rates[currency]
    result = value / rate
    await hl.finish(f"{value} {currency} = {result:.2f} CNY")


@evetime.handle()
async def _():
    await evetime.finish(f"EVE TIME:{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
