from arclet.alconna import Arparma
from nonebot import require

from ...db.models.record import CommandRecord

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna.extension import Extension
from nonebot_plugin_orm import get_session


class HelperExtension(Extension):
    @property
    def priority(self) -> int:
        return 16

    @property
    def id(self) -> str:
        return "nonebot_plugin_alchelper:HelperExtension"

    async def parse_wrapper(self, bot, state, event, res: Arparma) -> None:
        async with get_session() as session:
            session.add(
                CommandRecord(
                    source=res.source.path,
                    origin=str(res.origin),
                    sender=str(event.get_user_id()),
                    event=str(event.get_event_name()),
                    session=str(event.get_session_id()),
                )
            )
            await session.commit()
