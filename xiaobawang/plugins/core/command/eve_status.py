from arclet.alconna import Alconna, Arparma, Option
from nonebot_plugin_alconna import UniMessage, on_alconna
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_uninfo import Uninfo

from ..helper.status import eve_server_status

__all__ = ["eve_status", "eve_status_sub"]

eve_status = on_alconna(Alconna("eve_status"), use_cmd_start=True, aliases=("EVE状态", "eve状态", "dt"))

eve_status_sub = on_alconna(
    Alconna("eve_status_sub", Option("-r|--remove")),
    use_cmd_start=True,
    aliases=("EVE状态订阅", "eve状态订阅", "dt订阅"),
)


@eve_status.handle()
async def get_eve_status():
    await eve_status.finish(UniMessage.text(str(eve_server_status)))


@eve_status_sub.handle()
async def set_eve_status_sub(result: Arparma, session: async_scoped_session, user_info: Uninfo):
    remove = True if result.options.get("remove") else False
    if remove:
        await eve_server_status.remove_sub(session=session, user_info=user_info)
        await eve_status_sub.finish("已移除EVE状态订阅")
    else:
        await eve_server_status.add_sub(session=session, user_info=user_info)
        await eve_status_sub.finish("已添加EVE状态订阅")
