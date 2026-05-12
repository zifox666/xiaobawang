import re

from arclet.alconna import Alconna, Option
from nonebot import Bot, logger, on_regex
from nonebot.internal.adapter import Event
from nonebot.matcher import Matcher
from nonebot.params import RegexStr
from nonebot_plugin_alconna import UniMessage, on_alconna

from ..helper.zkb.killmail import km
from ..utils.battlereport import render_br
from ..utils.common import convert_time, get_reply_message_id
from ..utils.common.cache import get_msg_cache, save_msg_cache
from ..utils.common.emoji import emoji_action
from ..utils.render import html2gif

# ─── 匹配器定义 ───────────────────────────────────────────────────────────────

link = on_alconna(
    Alconna("link"),
    use_cmd_start=True,
    aliases={"链接"},
)

wb = on_alconna(
    Alconna("wb", Option("damage|d"), Option("timeline|t"), Option("summary|s"), Option("composition|c")),
    use_cmd_start=True,
)
br = on_alconna(
    Alconna("br"),
    use_cmd_start=True,
)
gif = on_alconna(
    Alconna("gif"),
    use_cmd_start=True,
)

br_preview_time = on_regex(r"https://br.evetools.org/br/([a-zA-Z0-9]{24})")
br_preview_zkb = on_regex(r"https://zkillboard.com/related/([0-9]{8})/([0-9]{12})/")
br_preview_alt = on_regex(r"https://br.evetools.org/related/([0-9]{8})/([0-9]{12})")
wb_preview_alt = on_regex(r"https://warbeacon.net/br/report/([a-zA-Z0-9\-]+)")
wb_preview_time = on_regex(r"https://warbeacon.net/br/related/([0-9]{8})/([0-9]{12})")
kmapp_preview_time = on_regex(r"https://killmail.app/related/([0-9]{8})/([0-9]{12})")
kmapp_preview_alt = on_regex(r"https://killmail.app/br/([a-zA-Z0-9\-]+)")  # e.g. killmail.app/br/PTWi4A7Pyh-atioth-2026-03-28
scit_preview = on_regex(r"https://br\.scers\.cn/br/s/([a-zA-Z0-9]+)")  # e.g. https://br.scers.cn/br/s/f7159951
scit_preview_alt = on_regex(r"https://br\.scers\.cn/br/related/([0-9]{8})/([0-9]{12})")  # e.g. https://br.scers.cn/br/related/30002439/202605061630


# ─── URL 分发工具 ─────────────────────────────────────────────────────────────

async def _dispatch_render(url: str) -> tuple[bytes | None, str | None]:
    """
    根据 URL 格式分发到对应的 render_br source_type。

    路由规则：
    - warbeacon.net/br/report/{uuid}     → warbeacon_hash
    - br.evetools.org/br/{hash24}        → evetools_hash
    - killmail.app/br/{hash}             → killmail_app_hash
    - br.scers.cn/br/s/{id}              → scit
    - */related/{system}/{time}（所有域名）→ warbeacon_auto
    """
    m = re.search(r"warbeacon\.net/br/report/([a-zA-Z0-9\-]+)", url)
    if m:
        return await render_br("warbeacon_hash", uuid=m.group(1))

    m = re.search(r"br\.evetools\.org/br/([a-zA-Z0-9]{24})", url)
    if m:
        return await render_br("evetools_hash", report_id=m.group(1))

    m = re.search(r"killmail\.app/br/([a-zA-Z0-9\-]+)", url)
    if m:
        return await render_br("killmail_app_hash", report_id=m.group(1).split("-")[0])

    m = re.search(r"br\.scers\.cn/br/s/([a-zA-Z0-9]+)", url)
    if m:
        return await render_br("scit", report_id=m.group(1))

    # 所有 /related/{system}/{time} 或 /br/related/{system}/{time} 格式
    # 覆盖：warbeacon / killmail.app / br.evetools.org / zkillboard / br.scers.cn
    m = re.search(r"/(?:br/)?related/([0-9]{8})/([0-9]{12})", url)
    if m:
        return await render_br(
            "warbeacon_auto",
            solar_system_id=int(m.group(1)),
            time_str=m.group(2),
        )

    return None, None


async def _handle_render_command(matcher: Matcher, bot: Bot, event: Event) -> None:
    """通用战报命令处理（/br 和 /wb 共用）。"""
    msg_id = await get_reply_message_id(bot, event)
    save_link = await get_msg_cache(msg_id)
    if not save_link or not isinstance(save_link, str):
        await matcher.finish("未找到相关链接或链接格式不正确")

    # zkillboard 单杀 → 转换为 related 格式
    if "zkillboard.com/kill/" in save_link:
        matched = re.search(r"zkillboard\.com/kill/(\d+)/", save_link)
        if not matched:
            await matcher.finish("无法解析 zkillboard 链接")
        data = await km.get(matched.group(1))
        url = f"https://killmail.app/related/{data['solar_system_id']}/{convert_time(data['killmail_time'])}"
    else:
        url = save_link

    try:
        img, wb_url = await _dispatch_render(url)
    except Exception as e:
        logger.exception(f"render_br 失败: {e}")
        await matcher.finish("战报渲染失败，请稍后重试")
        return

    if not img:
        await matcher.finish("战报渲染失败，无法生成图片")

    if wb_url and wb_url != url:
        await save_msg_cache(
            await matcher.send(UniMessage.reply(msg_id) + UniMessage.text(wb_url)),
            wb_url,
        )

    await save_msg_cache(
        await matcher.send(UniMessage.reply(msg_id) + UniMessage.image(raw=img)),
        wb_url or url,
    )


# ─── 命令处理器 ───────────────────────────────────────────────────────────────

@link.handle()
async def _(bot: Bot, event: Event):
    msg_id = await get_reply_message_id(bot, event)
    if not msg_id:
        return
    save_link = await get_msg_cache(msg_id)
    if save_link:
        await link.send(UniMessage.reply(msg_id) + UniMessage.text(save_link))


@br.handle()
@wb.handle()
async def _(matcher: Matcher, bot: Bot, event: Event):
    await _handle_render_command(matcher, bot, event)


@gif.handle()
async def _(bot: Bot, event: Event):
    msg_id = await get_reply_message_id(bot, event)
    save_link = await get_msg_cache(msg_id)
    if not save_link or not isinstance(save_link, str):
        await gif.finish("未找到相关链接或链接格式不正确")

    if "zkillboard.com/kill/" in save_link:
        matched = re.search(r"zkillboard\.com/kill/(\d+)/", save_link)
        if not matched:
            await gif.finish("无法解析 zkillboard 链接")
        data = await km.get(matched.group(1))
        url = f"https://killmail.app/related/{data['solar_system_id']}/{convert_time(data['killmail_time'])}"
    else:
        url = save_link

    try:
        gif_bytes = await html2gif(
            url=url,
            element="main",
            viewport_width=1280,
            viewport_height=850,
            fps=8,
            min_output_seconds=8,
            max_output_seconds=15,
            seek_wait_ms=200,
        )
        await save_msg_cache(
            await gif.send(UniMessage.reply(msg_id) + UniMessage.image(raw=gif_bytes)),
            url,
        )
    except Exception as e:
        await gif.finish(f"GIF 生成失败: {e!s}")


# ─── 链接自动预览处理器 ───────────────────────────────────────────────────────

@br_preview_time.handle()
@br_preview_alt.handle()
@br_preview_zkb.handle()
@wb_preview_alt.handle()
@wb_preview_time.handle()
@scit_preview.handle()
@scit_preview_alt.handle()
async def _(event: Event, url: str = RegexStr()):
    """通用战报预览：渲染图片，有新 warbeacon URL 时先发链接。"""
    await emoji_action(event)
    img, wb_url = await _dispatch_render(url)
    if not img:
        return
    if wb_url and wb_url != url:
        await save_msg_cache(
            await UniMessage.text(wb_url).send(target=event, reply_to=True),
            wb_url,
        )
    await save_msg_cache(
        await UniMessage.image(raw=img).send(target=event, reply_to=True),
        wb_url or url,
    )


@kmapp_preview_time.handle()
@kmapp_preview_alt.handle()
async def _(event: Event, url: str = RegexStr()):
    """killmail.app 战报预览：渲染图片 + GIF 时间轴。"""
    await emoji_action(event)

    try:
        img, wb_url = await _dispatch_render(url)
    except Exception as e:
        logger.exception(f"killmail.app 战报渲染失败: {e}")
        await UniMessage.text("战报渲染失败，请稍后重试").send(target=event, reply_to=True)
        return
    if img:
        await save_msg_cache(
            await UniMessage.image(raw=img).send(target=event, reply_to=True),
            wb_url or url,
        )

    try:
        gif_bytes = await html2gif(
            url=url,
            element="main",
            viewport_width=1280,
            viewport_height=850,
            fps=8,
            min_output_seconds=8,
            max_output_seconds=15,
            seek_wait_ms=200,
        )
        await save_msg_cache(
            await UniMessage.image(raw=gif_bytes).send(target=event),
            wb_url or url,
        )
    except Exception as e:
        logger.warning(f"killmail.app GIF 生成失败: {e!s}")
