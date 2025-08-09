from arclet.alconna import Alconna
from nonebot.adapters.onebot.v11 import Event as ob11_Event
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna import UniMessage, on_alconna

from xiaobawang.plugins.core.utils.render import render_template, templates_path

help = on_alconna(
    Alconna(
        "help",
    ),
    use_cmd_start=True,
    aliases=("帮助", "菜单", "start", "about"),
)


help_data = {
    "title": "小霸王 帮助菜单",
    "data": [
        {
            "title": "基础查询",
            "img": "money_with_wings.png",
            "items": [
                {
                    "title": "查询jita物品价格",
                    "new": False,
                    "hot": True,
                    "commands": ["/jita 物品名称", "/jita 物品名称*数量", "回复消息 + /next"],
                    "desc": "查询到的物品如果很多，会以三个一组显示，可以回复消息进行翻页。物品组会给出物品组总价格。",
                },
                {
                    "title": "翻译EVE专有名词",
                    "new": False,
                    "hot": False,
                    "commands": [
                        "/trans 物品名称",
                        "/trans 物品名称 --limit 数量",
                    ],
                    "desc": "翻译EVE专有名词，使用 --limit 限制翻译数量。目前只支持中英文互翻",
                },
                {
                    "title": "查询虫洞星系",
                    "new": True,
                    "hot": False,
                    "commands": [
                        "/wormhole 虫洞星系名称/虫洞名称",
                    ],
                    "desc": "查询虫洞星系的相关信息,例如/cd J111613或/cd D792",
                },
            ],
        },
        {
            "title": "zkillboard相关",
            "img": "candle.png",
            "items": [
                {
                    "title": "查询zkb统计信息",
                    "new": False,
                    "hot": True,
                    "commands": [
                        "/zkb 名称",
                        "/zkb 名称 -t corporation",
                    ],
                    "desc": "查询zkb的统计信息,可以使用 -t [type] 来查询指定类型信息。目前只支持corporation, character",
                },
                {
                    "title": "订阅指定条件KM",
                    "new": False,
                    "hot": False,
                    "commands": ["/sub <add/remove> <type> <name>", "[-a value] [-v value]"],
                    "desc": "订阅高价值KM,可以使用[value]设置最低推送阈值 -a:最后一击,-v:损失，默认30m。"
                    "目前支持[char,corp,alliance,ship,system]",
                },
                {
                    "title": "订阅高价值KM",
                    "new": False,
                    "hot": False,
                    "commands": ["/sub_high", "/sub_high 20_000_000_000", "/sub_high -r"],
                    "desc": "订阅高价值KM,可以使用[-r]取消订阅，默认推送18b以上的KM",
                },
            ],
        },
        {
            "title": "小功能",
            "img": "hammer_and_wrench.png",
            "items": [
                {
                    "title": "查询对RMB汇率",
                    "new": False,
                    "hot": False,
                    "commands": ["/hl 100 USD", "/exchangerate 100 日元"],
                    "desc": "查询对RMB汇率,可以使用 hl 汇率",
                },
                {
                    "title": "查询EVE时间",
                    "new": False,
                    "hot": False,
                    "commands": [
                        "/evetime",
                    ],
                },
                {
                    "title": "查询EVE服务器状态",
                    "new": False,
                    "hot": False,
                    "commands": ["/eve_status", "/dt"],
                },
            ],
        },
    ],
}

help_en_data = {
    "title": "XiaoBaWang Help Menu",
    "data": [
        {
            "title": "Basic Queries",
            "img": "money_with_wings.png",
            "items": [
                {
                    "title": "Query Jita Item Prices",
                    "new": False,
                    "hot": True,
                    "commands": ["/jita item_name", "/jita item_name*quantity", "Reply to message + /next"],
                    "desc": "When many items are found, they will be displayed in groups of three,"
                    " and you can reply to paginate. Item groups will show total group price.",
                },
                {
                    "title": "Translate EVE Terms",
                    "new": False,
                    "hot": False,
                    "commands": [
                        "/trans item_name",
                        "/trans item_name --limit number",
                    ],
                    "desc": "Translate EVE specific terms, use --limit to limit the number of translations."
                    " Currently only supports Chinese-English translation.",
                },
                {
                    "title": "Query Wormhole Systems",
                    "new": True,
                    "hot": False,
                    "commands": [
                        "/wormhole wormhole_system_name/wormhole_name",
                    ],
                    "desc": "Query information related to wormhole systems, for example /cd J111613 or /cd D792",
                },
            ],
        },
        {
            "title": "zkillboard Related",
            "img": "candle.png",
            "items": [
                {
                    "title": "Query zkb Statistics",
                    "new": False,
                    "hot": True,
                    "commands": [
                        "/zkb name",
                        "/zkb name -t corporation",
                    ],
                    "desc": "Query zkb statistics, you can use -t [type] to query specific type of information."
                    " Currently only supports corporation, character",
                },
                {
                    "title": "Subscribe to Specific KMs",
                    "new": False,
                    "hot": False,
                    "commands": ["/sub <add/remove> <type> <name>", "[-a value] [-v value]"],
                    "desc": "Subscribe to killmails, use [value] to set minimum threshold -a:"
                    " final blow, -v: loss, default 30m. Currently supports [char,corp,alliance,ship,system]",
                },
                {
                    "title": "Subscribe to High-value KMs",
                    "new": False,
                    "hot": False,
                    "commands": ["/sub_high", "/sub_high 20_000_000_000", "/sub_high -r"],
                    "desc": "Subscribe to high-value killmails, use [-r] to unsubscribe, default pushes KMs above 18b",
                },
            ],
        },
        {
            "title": "Utilities",
            "img": "hammer_and_wrench.png",
            "items": [
                {
                    "title": "Check RMB Exchange Rate",
                    "new": False,
                    "hot": False,
                    "commands": ["/hl 100 USD", "/exchangerate 100 JPY"],
                    "desc": "Check exchange rate to RMB, can use hl for exchange rate",
                },
                {
                    "title": "Check EVE Time",
                    "new": False,
                    "hot": False,
                    "commands": [
                        "/evetime",
                    ],
                },
                {
                    "title": "Check EVE Server Status",
                    "new": False,
                    "hot": False,
                    "commands": ["/eve_status", "/dt"],
                },
            ],
        },
    ],
}


@help.handle()
async def _(event: Event):
    if isinstance(event, ob11_Event):
        data = help_data
    else:
        data = help_en_data
    await help.send(
        UniMessage.text(
            "Documents: https://zifox666.github.io/xiaobawang/",
        )
    )
    await help.finish(
        UniMessage.image(
            raw=await render_template(
                template_path=templates_path / "help", template_name="help.html.jinja2", data=data, width=1080
            )
        )
    )
