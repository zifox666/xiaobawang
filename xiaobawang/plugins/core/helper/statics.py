import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import matplotlib.pyplot as plt
from sqlalchemy import func, text, select
from io import BytesIO

from nonebot_plugin_orm import get_session
from nonebot import logger

from ..db.models.record import CommandRecord, KillmailPushRecord


class DataAnalysisHelper:
    """
    数据报表分析
    """

    @classmethod
    async def get_command_stats(
            cls,
            days: int = 7,
            group_by: str = "day"
    ) -> Dict[str, Any]:
        """
        获取指定天数内的命令使用统计

        :param days: 查询的天数范围
        :param group_by: 分组方式，支持 'day', 'hour', 'command', 'source'

        :return: 包含统计数据的字典
        """
        try:
            async with get_session() as session:
                start_date = datetime.now() - timedelta(days=days)

                if group_by == "day":
                    query = (
                        select(
                            func.strftime('%Y-%m-%d', CommandRecord.time).label("day"),
                            func.count().label("count")
                        )
                        .where(CommandRecord.time >= start_date)
                        .group_by(text("day"))
                        .order_by(text("day"))
                    )
                    result = await session.execute(query)
                    data = [{"日期": row.day, "命令数": row.count}
                            for row in result.fetchall()]

                elif group_by == "hour":
                    query = (
                        select(
                            func.strftime('%H', CommandRecord.time).label("hour"),
                            func.count().label("count")
                        )
                        .where(CommandRecord.time >= start_date)
                        .group_by(text("hour"))
                        .order_by(text("hour"))
                    )
                    result = await session.execute(query)
                    data = [{"小时": f"{int(row.hour)}时", "命令数": row.count}
                            for row in result.fetchall()]

                elif group_by == "command":
                    query = (
                        select(
                            CommandRecord.event,
                            func.count().label("count")
                        )
                        .where(CommandRecord.time >= start_date)
                        .group_by(CommandRecord.event)
                        .order_by(text("count DESC"))
                        .limit(10)
                    )
                    result = await session.execute(query)
                    data = [{"命令": row.event, "使用次数": row.count}
                            for row in result.fetchall()]

                elif group_by == "source":
                    query = (
                        select(
                            CommandRecord.source,
                            func.count().label("count")
                        )
                        .where(CommandRecord.time >= start_date)
                        .group_by(CommandRecord.source)
                        .order_by(text("count DESC"))
                    )
                    result = await session.execute(query)
                    data = [{"来源": row.source, "命令数": row.count}
                            for row in result.fetchall()]

                total_query = (
                    select(func.count())
                    .select_from(CommandRecord)
                    .where(CommandRecord.time >= start_date)
                )
                total_result = await session.execute(total_query)
                total_count = total_result.scalar() or 0

                return {
                    "total_count": total_count,
                    "data": data,
                    "period": f"过去{days}天"
                }

        except Exception as e:
            logger.error(f"获取命令统计数据失败: {e}")
            return {"error": f"获取数据失败: {e}", "data": [], "total_count": 0}

    @classmethod
    async def get_killmail_push_stats(
            cls,
            days: int = 7,
            group_by: str = "day"
    ) -> Dict[str, Any]:
        """
        获取指定天数内的击杀邮件推送统计

        :param days: 查询的天数范围
        :param group_by: 分组方式，支持 'day', 'platform', 'session'

        :return: 包含统计数据的字典
        """
        try:
            async with get_session() as session:
                start_date = datetime.now() - timedelta(days=days)

                if group_by == "day":
                    query = (
                        select(
                            func.strftime('%Y-%m-%d', KillmailPushRecord.time).label("day"),
                            func.count().label("count")
                        )
                        .where(KillmailPushRecord.time >= start_date)
                        .group_by(text("day"))
                        .order_by(text("day"))
                    )
                    result = await session.execute(query)
                    data = [{"日期": row.day, "推送数": row.count}
                            for row in result.fetchall()]

                elif group_by == "platform":
                    query = (
                        select(
                            KillmailPushRecord.platform,
                            func.count().label("count")
                        )
                        .where(KillmailPushRecord.time >= start_date)
                        .group_by(KillmailPushRecord.platform)
                        .order_by(text("count DESC"))
                    )
                    result = await session.execute(query)
                    data = [{"平台": row.platform, "推送数": row.count}
                            for row in result.fetchall()]

                elif group_by == "session":
                    query = (
                        select(
                            KillmailPushRecord.session_id,
                            KillmailPushRecord.session_type,
                            func.count().label("count")
                        )
                        .where(KillmailPushRecord.time >= start_date)
                        .group_by(KillmailPushRecord.session_id, KillmailPushRecord.session_type)
                        .order_by(text("count DESC"))
                        .limit(10)
                    )
                    result = await session.execute(query)
                    data = [{"会话ID": row.session_id, "会话类型": row.session_type, "推送数": row.count}
                            for row in result.fetchall()]

                total_query = (
                    select(func.count())
                    .select_from(KillmailPushRecord)
                    .where(KillmailPushRecord.time >= start_date)
                )
                total_result = await session.execute(total_query)
                total_count = total_result.scalar() or 0

                return {
                    "total_count": total_count,
                    "data": data,
                    "period": f"过去{days}天"
                }

        except Exception as e:
            logger.error(f"获取击杀邮件推送统计数据失败: {e}")
            return {"error": f"获取数据失败: {e}", "data": [], "total_count": 0}

    @classmethod
    async def get_active_users(cls, days: int = 7) -> Dict[str, Any]:
        """
        获取最活跃的用户统计
        :param days: 查询的天数范围
        :return: 包含活跃用户统计的字典
        """
        try:
            async with get_session() as session:
                start_date = datetime.now() - timedelta(days=days)

                query = (
                    select(
                        CommandRecord.sender,
                        func.count().label("count")
                    )
                    .where(CommandRecord.time >= start_date)
                    .group_by(CommandRecord.sender)
                    .order_by(text("count DESC"))
                    .limit(10)
                )
                result = await session.execute(query)

                active_users = [{"用户": row.sender, "命令数": row.count}
                                for row in result.fetchall()]

                return {
                    "data": active_users,
                    "period": f"过去{days}天"
                }

        except Exception as e:
            logger.error(f"获取活跃用户统计失败: {e}")
            return {"error": f"获取数据失败: {e}", "data": []}

    @classmethod
    async def get_usage_trend(cls, days: int = 30) -> Dict[str, Any]:
        """
        获取使用趋势统计（按天统计命令数和击杀邮件推送数）
        :param days: 查询的天数范围
        :return: 包含使用趋势的字典
        """
        try:
            async with get_session() as session:
                start_date = datetime.now() - timedelta(days=days)

                cmd_query = (
                    select(
                        func.strftime('%Y-%m-%d', CommandRecord.time).label("day"),
                        func.count().label("count")
                    )
                    .where(CommandRecord.time >= start_date)
                    .group_by(text("day"))
                    .order_by(text("day"))
                )
                cmd_result = await session.execute(cmd_query)
                cmd_data = {row.day: row.count for row in cmd_result.fetchall()}

                km_query = (
                    select(
                        func.strftime('%Y-%m-%d', KillmailPushRecord.time).label("day"),
                        func.count().label("count")
                    )
                    .where(KillmailPushRecord.time >= start_date)
                    .group_by(text("day"))
                    .order_by(text("day"))
                )
                km_result = await session.execute(km_query)
                km_data = {row.day: row.count for row in km_result.fetchall()}

                date_range = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                              for i in range(days, 0, -1)]

                trend_data = []
                for date in date_range:
                    trend_data.append({
                        "日期": date,
                        "命令数": cmd_data.get(date, 0),
                        "击杀邮件推送数": km_data.get(date, 0)
                    })

                return {
                    "data": trend_data,
                    "period": f"过去{days}天"
                }

        except Exception as e:
            logger.error(f"获取使用趋势统计失败: {e}")
            return {"error": f"获取数据失败: {e}", "data": []}

    @classmethod
    async def generate(cls, days: int = 30) -> Optional[dict]:
        """
        生成完整的报表

        :param days: 查询的天数范围
        :return: 报表json
        """
        try:
            command_stats_day = await cls.get_command_stats(days, "day")
            command_stats_hour = await cls.get_command_stats(days, "hour")
            command_stats_cmd = await cls.get_command_stats(days, "command")
            command_stats_source = await cls.get_command_stats(days, "source")

            killmail_stats_day = await cls.get_killmail_push_stats(days, "day")
            killmail_stats_platform = await cls.get_killmail_push_stats(days, "platform")
            killmail_stats_session = await cls.get_killmail_push_stats(days, "session")

            active_users = await cls.get_active_users(days)
            usage_trend = await cls.get_usage_trend(days)

            chart_data = {
                "command_stats": {
                    "by_day": json.dumps(command_stats_day["data"]),
                    "by_hour": json.dumps(command_stats_hour["data"]),
                    "by_command": json.dumps(command_stats_cmd["data"]),
                    "by_source": json.dumps(command_stats_source["data"]),
                },
                "killmail_stats": {
                    "by_day": json.dumps(killmail_stats_day["data"]),
                    "by_platform": json.dumps(killmail_stats_platform["data"]),
                    "by_session": json.dumps(killmail_stats_session["data"]),
                },
                "active_users": json.dumps(active_users["data"]),
                "usage_trend": json.dumps(usage_trend["data"]),
            }

            report_data = {
                "period": f"过去{days}天",
                "command_stats": {
                    "total": command_stats_day.get("total_count", 0),
                    "by_day": command_stats_day,
                    "by_hour": command_stats_hour,
                    "by_command": command_stats_cmd,
                    "by_source": command_stats_source
                },
                "killmail_stats": {
                    "total": killmail_stats_day.get("total_count", 0),
                    "by_day": killmail_stats_day,
                    "by_platform": killmail_stats_platform,
                    "by_session": killmail_stats_session
                },
                "active_users": active_users,
                "usage_trend": usage_trend,
                "chart_data": chart_data
            }

            return report_data

        except Exception as e:
            logger.error(f"生成HTML报表失败: {e}")
            return None

data_analysis = DataAnalysisHelper()
