from arclet.alconna import Alconna, MultiVar, Args, Arparma
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna import on_alconna, UniMessage

from ..utils.common import type_word
from ..utils.common.command_record import get_msg_id
from ..utils.common.emoji import emoji_action
from ..utils.render import capture_element
from ..api.janice import janice_api

__all__ = ["janice", "janice_preview"]

janice = on_alconna(
    Alconna(
        "janice",
        Args["text", MultiVar(str)]
    ),
    use_cmd_start=True,
    aliases=("合同估价", "合同", "contract")
)

janice_preview = on_alconna(
    Alconna(
        "https://janice.e-351.com/a/{code:str}",
        separators=["\x04", "\n"],
    ),
    use_cmd_start=False,
)


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
    msg = f'''估价地址：{appraisal.janiceUrl}
合同体积：{appraisal.totalVolume} m3
合同卖单：{appraisal.totalSellPrice:,.2f} isk
合同买单：{appraisal.totalBuyPrice:,.2f} isk
中间价：{appraisal.totalSplitPrice:,.2f} isk'''
    send_event = await janice.send(
        UniMessage.reply(event.message_id) + UniMessage.text(msg)
    )
    msg_id = get_msg_id(send_event)
    pic = await capture_element(url=appraisal.janiceUrl, element=".appraisal", full_page=False)
    if pic:
        await janice.finish(
            UniMessage.reply(msg_id) + UniMessage.image(raw=pic)
        )




@janice_preview.handle()
async def handle_janice_preview(
        arp: Arparma,
        event: Event,
):
    """
    处理合同估价请求
    :param event: 事件对象
    :param arp:
    """
    await emoji_action(event)
    code = arp.header["code"]
    url = f"https://janice.e-351.com/a/{code}"
    pic = await capture_element(url=url, element=".appraisal", full_page=False)
    if pic:
        await janice_preview.finish(
            UniMessage.reply(event.message_id) + UniMessage.image(raw=pic)
        )

