import traceback

from arclet.alconna import Arparma
from nonebot import require, logger
from nonebot.adapters.telegram.model import Message as TelegramMessage
from nonebot_plugin_alconna.uniseg import Receipt

from ...config import plugin_config
from ...api.statics import upload_statistics
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
                    bot_id=bot.self_id,
                    platform=str(bot.adapter),
                    source=res.source.path,
                    origin=str(res.origin),
                    sender=str(event.get_user_id()),
                    event=str(event.get_event_name()),
                    session=str(event.get_session_id()),
                )
            )
            await session.commit()

        if plugin_config.upload_statistics:
            await upload_statistics.send_command_record(
                bot_id=str(bot.self_id),
                platform=str(bot.adapter),
                source=str(res.source.path),
                origin=str(res.origin),
                sender=str(event.get_user_id()),
                event=str(event.get_event_name()),
                session=str(event.get_session_id()),
            )


def get_msg_id(send_event: Receipt) -> str | int:
    """
    获取消息ID
    :param send_event: 发送事件
    :return: 消息ID
    """
    try:
        # logger.debug(send_event.msg_ids)
        if isinstance(send_event.msg_ids[0], TelegramMessage):
            msg_id = send_event.msg_ids[0].message_id
        else:
            msg_id = send_event.msg_ids[0]["message_id"]
    except Exception as e:
        logger.error(f"获取消息id失败\n{traceback.format_exc()}")
        return 0
    return msg_id
