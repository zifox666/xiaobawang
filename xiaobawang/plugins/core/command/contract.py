from arclet.alconna import Alconna, Args, MultiVar
from nonebot import on_regex
from nonebot.internal.adapter import Event
from nonebot.params import RegexStr
from nonebot_plugin_alconna import UniMessage, on_alconna

from ..api.janice import janice_api
from ..utils.common import type_word
from ..utils.common.command_record import get_msg_id
from ..utils.common.emoji import emoji_action
from ..utils.render import capture_element

__all__ = ["janice", "janice_preview"]

janice = on_alconna(
    Alconna("janice", Args["text", MultiVar(str)]), use_cmd_start=True, aliases=("合同估价", "合同", "contract")
)

janice_preview = on_regex(r"janice\.e-351\.com/a/([a-zA-Z0-9]{6})")


@janice.handle()
async def handle_janice(
    event: Event,
):
    """
    处理合同估价请求
    :param event: 事件对象
    """
    await emoji_action(event)
    msg = event.get_message()
    items = type_word(str(msg))
    appraisal = await janice_api.get(items)
    msg = f"""估价地址：{appraisal.janiceUrl}
合同体积：{appraisal.totalVolume} m3
合同卖单：{appraisal.totalSellPrice:,.2f} isk
合同买单：{appraisal.totalBuyPrice:,.2f} isk
中间价：{appraisal.totalSplitPrice:,.2f} isk"""
    send_event = await janice.send(UniMessage.reply(event.message_id) + UniMessage.text(msg))
    msg_id = get_msg_id(send_event)
    pic = await capture_element(url=appraisal.janiceUrl, element=".appraisal", full_page=False)
    if pic:
        await janice.finish(UniMessage.reply(msg_id) + UniMessage.image(raw=pic))


@janice_preview.handle()
async def handle_janice_preview(event: Event, url: str = RegexStr()):
    """
    处理合同估价请求
    :param event: 事件对象
    :param url:
    """
    url = f"https://{url}"
    await emoji_action(event)
    pic = await capture_element(url=url, element=".appraisal", full_page=False)
    if pic:
        await UniMessage.image(raw=pic).send(target=event, reply_to=True)
