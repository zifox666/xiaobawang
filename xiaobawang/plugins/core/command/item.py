from arclet.alconna import Alconna, Args, Arparma, CommandMeta, MultiVar
from nonebot import logger, require

from ..api.esi.market import market
from ..utils.render import render_template, templates_path

require("xiaobawang.plugins.sde")

from nonebot_plugin_alconna import UniMessage, on_alconna

from xiaobawang.plugins.sde.item import item_lookup

__all__ = ["query_item"]

query_item = on_alconna(
    Alconna(
        "item",
        Args["name", MultiVar(str)],
        meta=CommandMeta(
            usage="/item <物品名称>",
            description="查询最相关的 EVE 物品或舰船资料",
        ),
    ),
    aliases=("物品", "物品信息", "Item"),
    auto_send_output=True,
    use_cmd_start=True,
)


def _format_isk(value: float | None) -> str | None:
    if not value:
        return None
    return f"{float(value):,.2f} ISK"


@query_item.handle()
async def handle_query_item(result: Arparma):
    query = " ".join(result.name).strip()
    if not query:
        await query_item.finish("请输入物品名称，例如：item 审判者级")

    details = await item_lookup.find_most_relevant(query)
    if details is None:
        await query_item.finish(f"未找到与「{query}」相关的物品")

    details["query"] = query
    try:
        prices = await market.get_price([details["type_id"]])
        price_data = prices.get(details["type_id"]) or prices.get(str(details["type_id"])) or {}
        highest_buy = price_data.get("highest_buy") or {}
        lowest_sell = price_data.get("lowest_sell") or {}
        details["market"] = {
            "buy": _format_isk(highest_buy.get("price")),
            "sell": _format_isk(lowest_sell.get("price")),
        }
    except Exception:
        logger.warning(f"item 查询市场价格失败，type_id={details['type_id']}", exc_info=True)
        details["market"] = {}

    image = await render_template(
        template_path=templates_path / "item",
        template_name="item.html.jinja2",
        data=details,
        width=820,
    )
    await query_item.finish(UniMessage.image(raw=image))
