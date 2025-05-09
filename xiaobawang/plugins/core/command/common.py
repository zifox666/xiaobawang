from datetime import datetime, timezone

from arclet.alconna import Alconna, Args
from nonebot_plugin_alconna import on_alconna

from xiaobawang.plugins.core.api.common import get_exchangerate
from xiaobawang.plugins.core.api.esi.universe import esi_client

__all__ = ["hl", "evetime", "eve_status"]

hl = on_alconna(
    Alconna(
        "hl",
        Args["value", float]["currency", str],
    ),
    use_cmd_start=True,
    aliases=("汇率", "exchangerate")
)

evetime = on_alconna(
    Alconna("evetime"),
    use_cmd_start=True,
    aliases=("EVE时间", "eve时间")
)

eve_status = on_alconna(
    Alconna("eve_status"),
    use_cmd_start=True,
    aliases=("EVE状态", "eve状态", "dt")
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


@eve_status.handle()
async def _():
    server_status = await esi_client.get_server_status()
    api_status = await esi_client.get_api_status()

    msg = f"""EVE Tranquility Status\n"""
    if server_status.get("players", 0):
        msg += f"""------\nServer Status: ON\n - Online Players: {server_status['players']}\n - Version: {server_status['server_version']}\n"""
    else:
        msg += f"""------\nServer Status: OFF\n"""
    if api_status:
        msg += f"""------\nAPI Status:\n - 🟢 {api_status['green']} 🟡 {api_status['yellow']} 🔴 {api_status['red']}\n - Total: {api_status['total']}\n"""


    await eve_status.finish(msg)
