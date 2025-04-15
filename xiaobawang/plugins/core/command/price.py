from datetime import datetime

from arclet.alconna import (
    Args,
    Alconna,
    MultiVar,
    CommandMeta,
    Arparma
)

from nonebot import logger, require
from nonebot.internal.adapter import Event, Bot
from nonebot.plugin.on import on_command
from nonebot_plugin_orm import AsyncSession

from ..api.esi.market import market
from ..utils.common import get_reply_message_id
from ..utils.common.cache import cache
from ..helper.price import price_helper
from ..utils.render import render_template, templates_path

require("xiaobawang.plugins.sde")
require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import on_alconna, UniMessage

__all__ = ["query_price", "next_page", "prev_page"]

query_price = on_alconna(
    Alconna(
        "ojita",
        Args['args', MultiVar(str)],
        meta=CommandMeta(
            "查询欧服吉他价格",
            usage="可以模糊查询名称或者名称*数量",
            example="/jita 毒蜥级*10",
            fuzzy_match=True
        )
    ),
    aliases=("查价", "Ojita", "OJITA", "jita"),
    auto_send_output=True,
    use_cmd_start=True
)
"""next_page = on_alconna(
    Alconna("next"),
    extensions=[ReplyRecordExtension()]
)"""
next_page = on_command("next", aliases={"下一页"})
prev_page = on_command("last", aliases={"上一页", "prev"})
update_market_cache = on_command("更新市场数据", aliases={"更新市场", "更新市场数据"}, priority=5)


@query_price.handle()
async def handle_query_price(
        result: Arparma,
        session: AsyncSession,
        event: Event
):

    # 参数解析部分
    args = result.args
    args = ' '.join(args)
    word = args if "*" not in args else args.split("*")[0].strip()
    num = 1 if "*" not in args else (int(args.split("*")[1].strip()) if args.split("*")[1].strip().isdigit() else 1)
    logger.debug(f"市场查询 {word} * {num}")

    async with session:
        r = await price_helper.get(session, word, num)
        logger.debug(r)

        if r["success"]:
            r["now"] = datetime.now()
            msg_id = await query_price.send(
                UniMessage.image(raw=await render_template(
                    template_path=templates_path,
                    template_name="price.html.jinja2",
                    data=r,
                ))
            )
            msg_id = msg_id.msg_ids[0]["message_id"]
            cache_key = f"query_price_{event.get_session_id()}_{msg_id}"
            await cache.set(
                cache_key,
                {"word": r["word"], "num": r["num"], "current_page": 1, "total_pages": r["pagination"]["total_pages"]},
                6 * 3600
            )
        else:
            await query_price.finish(f"未找到[{args}]")


@next_page.handle()
async def handle_next_page(
        bot: Bot,
        session: AsyncSession,
        event: Event,
):
    msg_id = await get_reply_message_id(bot, event)
    if msg_id:

        cache_key = f"query_price_{event.get_session_id()}_{msg_id}"
        cache_data = await cache.get(cache_key)
        if cache_data:
            if cache_data["total_pages"] <= cache_data["current_page"]:
                await next_page.finish("已经是最后一页了")

            word = cache_data["word"]
            num = cache_data["num"]

            async with session:
                r = await price_helper.next(session=session, word=word, num=num, current_page=cache_data["current_page"])
                if r["success"]:
                    await next_page.send(f'{r["items"]}')
                    await cache.set(cache_key, {"word": word, "num": num, "current_page": cache_data["current_page"] + 1, "total_pages": r["pagination"]["total_pages"]}, 6 * 3600)


@prev_page.handle()
async def handle_prev_page(
        bot: Bot,
        session: AsyncSession,
        event: Event,
):
    msg_id = await get_reply_message_id(bot, event)
    if msg_id:
        cache_key = f"query_price_{event.get_session_id()}_{msg_id}"
        cache_data = await cache.get(cache_key)
        if cache_data:
            if cache_data["current_page"] <= 1:
                await prev_page.finish("已经是第一页了")

            word = cache_data["word"]
            num = cache_data["num"]

            async with session:
                r = await price_helper.prev(session=session, word=word, num=num, current_page=cache_data["current_page"])
                if r["success"]:
                    await prev_page.send(f'{r["items"]}')
                    await cache.set(cache_key, {"word": word, "num": num, "current_page": cache_data["current_page"] - 1, "total_pages": r["pagination"]["total_pages"]}, 6 * 3600)


@update_market_cache.handle()
async def _():
    await market.refresh()

