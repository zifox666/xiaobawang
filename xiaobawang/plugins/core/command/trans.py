from arclet.alconna import Alconna, Args, MultiVar, Option
from nonebot_plugin_alconna import on_alconna

from ..api.esi.universe import esi_client
from ..utils.common import is_chinese
from xiaobawang.plugins.sde.oper import sde_search

trans = on_alconna(
    Alconna(
        "trans",
        Args['args', MultiVar(str)],
        Option("-l|--limit", Args['value', int], default=10),
    ),
    use_cmd_start=True,
    aliases=("fy", "翻译", "fanyi")
)


@trans.handle()
async def _trans(
        args:  tuple,
        limit: int,
):
    args = " ".join(args)
    lang = is_chinese(args)
    name_data = await esi_client.get_universe_id(
        name=args,
        lang=lang,
    )
    system_name = None
    if name_data:
        name_id = None
        if 'systems' in name_data:
            name_id = name_data['systems'][0]['id']
            type_ = 'systems'
        elif 'constellations' in name_data:
            name_id = name_data['constellations'][0]['id']
            type_ = 'constellations'
        elif 'regions' in name_data:
            name_id = name_data['regions'][0]['id']
            type_ = 'regions'

        if name_id:
            name = await esi_client.get_trans_name(
                type_ids=[name_id],
                lang=lang,
                type_=type_,
            )
            await trans.finish(f"{args} <-> {name}")

    if not system_name:
        msg = ""
        data, total = await sde_search.trans_items(
            search_item=args,
            limit=limit,
        )
        if total == 0:
            await trans.finish(f"没有查询到[{args}]相关物品")
        if total >= limit:
            msg += f"查询到的物品数量有{total}个，你可以进一步查询\n"
        for t in data:
            msg += f"[{t.get('typeID')}] {t.get('source').get('text')} : {t.get('translation').get('text')}\n"

        await trans.finish(msg)


