from datetime import datetime
from typing import List

from fastapi import APIRouter, Response, Depends, HTTPException
from nonebot_plugin_orm import get_session, AsyncSession
from pydantic import BaseModel
from starlette.responses import HTMLResponse
from nonebot_plugin_htmlrender import template_to_html

from ..db.models.record import CommandRecord, KillmailPushRecord
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
    time: datetime

class SubmitKillmail(BaseModel):
    """
    提交Killmail数据
    """
    bot_id: str
    platform: str
    session_id: str
    session_type: str
    killmail_id: int
    time: datetime


@router.post("/command", summary="提交命令统计数据")
async def submit_statistics(
        submit_data: SubmitStatistics,
        session: AsyncSession = Depends(get_session)
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
        time=submit_data.time,
    )
    session.add(command_record)
    await session.commit()
    return {"success": True}


@router.post("/km")
async def submit_km(
        submit_data: SubmitKillmail,
        session: AsyncSession = Depends(get_session)
) -> dict:
    """
    提交Killmail数据
    """
    killmail_push_record = KillmailPushRecord(
        bot_id=submit_data.bot_id,
        platform=submit_data.platform,
        session_id=submit_data.session_id,
        session_type=submit_data.session_type,
        killmail_id=submit_data.killmail_id,
        time=submit_data.time,
    )
    session.add(killmail_push_record)
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


@router.post("/command/batch", summary="批量提交命令统计数据")
async def batch_submit_statistics(
        submit_data_list: List[SubmitStatistics],
        session: AsyncSession = Depends(get_session)
) -> dict:
    """
    批量提交命令统计数据

    参数:
    - submit_data_list: 命令统计数据列表

    返回:
    - success: 是否成功
    - count: 成功提交的记录数
    """
    try:
        command_records = [
            CommandRecord(
                bot_id=item.bot_id,
                platform=item.platform,
                source=item.source,
                origin=item.origin,
                sender=item.sender,
                event=item.event,
                session=item.session,
                time=item.time,
            ) for item in submit_data_list
        ]

        session.add_all(command_records)
        await session.commit()

        return {"success": True, "count": len(command_records)}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"批量提交命令统计数据失败: {str(e)}")


# 批量提交击杀邮件数据
@router.post("/km/batch", summary="批量提交击杀邮件数据")
async def batch_submit_km(
        submit_data_list: List[SubmitKillmail],
        session: AsyncSession = Depends(get_session)
) -> dict:
    """
    批量提交击杀邮件数据

    参数:
    - submit_data_list: 击杀邮件数据列表

    返回:
    - success: 是否成功
    - count: 成功提交的记录数
    """
    try:
        killmail_records = [
            KillmailPushRecord(
                bot_id=item.bot_id,
                platform=item.platform,
                session_id=item.session_id,
                session_type=item.session_type,
                killmail_id=item.killmail_id,
                time=item.time,
            ) for item in submit_data_list
        ]

        session.add_all(killmail_records)
        await session.commit()

        return {"success": True, "count": len(killmail_records)}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"批量提交击杀邮件数据失败: {str(e)}")
