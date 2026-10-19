import re

from arclet.alconna import Alconna, Args, Arparma, MultiVar, Option
from nonebot.internal.adapter import Event
from nonebot.params import RegexStr
from nonebot.plugin.on import on_regex
from nonebot_plugin_alconna import CommandMeta, UniMessage, on_alconna

from ..api.esi.universe import esi_client
from ..api.zkillboard import zkb_api
from ..helper.zkb.stats import ZkbStats
from ..utils.common.cache import save_msg_cache
from ..utils.common.emoji import emoji_action

__all__ = ["zkb", "zkb_preview"]

# 类型别名 -> 统一类型名
_TYPE_ALIASES: dict[str, str] = {
    "character": "character", "char": "character", "chara": "character",
    "人物": "character", "角色": "character",
    "corporation": "corporation", "corp": "corporation", "corps": "corporation",
    "军团": "corporation",
    "alliance": "alliance", "联盟": "alliance",
    "faction": "faction", "势力": "faction", "帝国": "faction",
    "ship": "ship", "shiptype": "ship", "ship_type": "ship",
    "舰船": "ship", "船只": "ship",
    "group": "group", "类别": "group", "组": "group",
    "system": "system", "solarsystem": "system", "solar_system": "system",
    "星系": "system",
    "region": "region", "星域": "region", "地区": "region",
}

# 统一类型名 -> ESI /universe/ids 分类（group 无法通过 ESI 按名称解析，走 SDE）
_ESI_CATEGORY: dict[str, str] = {
    "character": "characters",
    "corporation": "corporations",
    "alliance": "alliances",
    "faction": "factions",
    "ship": "inventory_types",
    "system": "systems",
    "region": "regions",
}

_TYPE_LABELS: dict[str, str] = {
    "character": "人物", "corporation": "军团", "alliance": "联盟", "faction": "势力",
    "ship": "舰船", "group": "类别", "system": "星系", "region": "星域",
}

USAGE = (
    "/zkb <名称> -t [类型] -l [数量]\n"
    "类型可选: character/corporation/alliance/faction/ship/group/system/region\n"
    "（人物/军团/联盟/势力/舰船/类别/星系/星域），默认为 character，limit 为击杀记录数量，默认为 3"
)

zkb = on_alconna(
    Alconna(
        "zkb",
        Args["args", MultiVar(str)],
        Option("-t|--type", Args["type", str], default="character"),
        Option("-l|--limit", Args["limit", int], default=3),
        CommandMeta(
            description="查询ZKB统计数据(人物/军团/联盟/势力/舰船/类别/星系/星域)",
            usage=USAGE,
        ),
    ),
    aliases={"kill"},
    use_cmd_start=True,
)
zkb.shortcut(
    r"^kkn (.+)$",
    command="zkb {0} -t character -l 10",
    fuzzy=True
)

# zkillboard 实体页链接预览（group 页面 403，不支持）
zkb_preview = on_regex(r"https://zkillboard.com/(character|corporation|alliance|faction|ship|system|region)/([0-9]+)/")


async def _resolve_group_id(name: str) -> int | None:
    """通过 SDE 按名称解析舰船类别 groupID（支持中英文）"""
    from sqlalchemy import and_, select

    from xiaobawang.plugins.sde.db import get_session
    from xiaobawang.plugins.sde.models import InvGroups, TC_GROUP_ID, TrnTranslations

    async with await get_session() as session:
        query = (
            select(InvGroups.groupID)
            .join(
                TrnTranslations,
                and_(TrnTranslations.tcID == TC_GROUP_ID, TrnTranslations.keyID == InvGroups.groupID),
            )
            .where(TrnTranslations.text.ilike(name.strip()))
            .where(TrnTranslations.languageID.in_(["zh", "en"]))
            .where(InvGroups.published.is_(True))
            .limit(1)
        )
        return (await session.execute(query)).scalar_one_or_none()


@zkb_preview.handle()
async def handle_zkb(
    event: Event,
    url: str = RegexStr(),
):
    match = re.match(r"https://zkillboard.com/([a-zA-Z]+)/([0-9]+)/", url)
    if not match:
        return
    entity_type, entity_id = match.groups()

    if entity_type not in zkb_api._allowed_types:
        return
    await emoji_action(event)

    zkb_data = await zkb_api.get_stats(entity_type, entity_id)
    if not zkb_data or zkb_data.get("error"):
        await zkb_preview.finish("获取数据失败，请稍后再试")
    pic = await ZkbStats(zkb_data).render()

    if pic:
        await save_msg_cache(
            send_event=await UniMessage.image(raw=pic).send(target=event, reply_to=True),
            value_=f"https://zkillboard.com/{entity_type}/{entity_id}/",
        )
    else:
        await zkb_preview.finish("获取数据失败，请稍后再试")


@zkb.handle()
async def _handle_zkb(
    arp: Arparma,
):
    args = " ".join(arp.main_args.get("args"))
    type_raw = str(arp.other_args.get("type", "character"))
    type_ = _TYPE_ALIASES.get(type_raw.strip().lower(), _TYPE_ALIASES.get(type_raw.strip()))
    limit = arp.other_args.get("limit", 3)
    if limit > 10:
        limit = 10

    if type_ is None:
        await zkb.finish(f"不支持的类型[{type_raw}]\n{USAGE}")

    # 名称 -> ID 解析
    id_ = None
    if type_ == "group":
        id_ = await _resolve_group_id(args)
    elif type_ in _ESI_CATEGORY:
        try:
            data = await esi_client.get_universe_id(type_=_ESI_CATEGORY[type_], name=args)
        except Exception:
            data = None
        if isinstance(data, dict):
            id_ = data.get("id")

    if id_ is None:
        msg = f"未找到[{_TYPE_LABELS[type_]}]{args}"
        if type_ != "character":
            msg += f"\n{USAGE}"
        await zkb.finish(msg)

    zkb_data = await zkb_api.get_stats(type_, id_)
    if not zkb_data or zkb_data.get("error", None):
        await zkb.finish(f"未找到[{_TYPE_LABELS[type_]}]{args}")
    pic = await ZkbStats(zkb_data).render(limit=limit)

    if pic:
        await save_msg_cache(
            send_event=await zkb.send(
                message=UniMessage.image(raw=pic),
                reply_to=True,
            ),
            value_=f"https://zkillboard.com/{type_}/{id_}/",
        )
    else:
        await zkb.finish("获取数据失败，请稍后再试")
