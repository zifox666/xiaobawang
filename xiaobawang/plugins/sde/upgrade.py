"""
SDE 数据库更新/升级功能
========================
本模块为只读模式，数据库更新由外部独立服务完成。

如需更新 SDE 数据，请使用外部工具连接 PostgreSQL
数据库 `eve_sde` 并执行数据导入。
"""

from nonebot import logger

logger.info("SDE 模块运行于只读模式 — 数据库更新由外部服务管理")
