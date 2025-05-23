from fastapi import APIRouter, Response
from nonebot_plugin_orm import get_session
from pydantic import BaseModel
from starlette.responses import HTMLResponse
from nonebot_plugin_htmlrender import template_to_html

from ..db.models.record import CommandRecord
from ..helper.statics import data_analysis
from ..utils.render import templates_path

router = APIRouter()

class SubmitStatistics(BaseModel):
    """
    提交统计数据
    """
    bot_id: str
    platform: str
    source: str
    origin: str
    sender: str
    event: str
    session: str


@router.post("", summary="提交统计数据")
async def submit_statistics(
        submit_data: SubmitStatistics,
) -> dict:
    """
    提交统计数据
    """
    command_record = CommandRecord(
        bot_id=submit_data.bot_id,
        platform=submit_data.platform,
        source=submit_data.source,
        origin=submit_data.origin,
        sender=submit_data.sender,
        event=submit_data.event,
        session=submit_data.session,
    )
    async with get_session() as session:
        await session.add(command_record)
        await session.commit()
    return {"success": True}


@router.get("", summary="查看统计数据")
async def get_statistics(
        days: int = 30,
) -> Response:
    """查看统计数据"""
    data = await data_analysis.generate(days)
    html_content = await template_to_html(
        template_path=templates_path / "statics",
        template_name="statics.html.jinja2",
        **data,
    )
    return HTMLResponse(content=html_content)
