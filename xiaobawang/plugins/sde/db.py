from nonebot import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import plugin_config

Base = declarative_base()

_engine: AsyncEngine | None = None
_sessionmaker = None


async def init_engine(database_url: str | None = None):
    """初始化 SDE PostgreSQL 数据库引擎（只读模式）"""
    global _engine, _sessionmaker

    try:
        url = database_url or plugin_config.sde_database_url

        logger.info(f"初始化 SDE 数据库连接: {url}")

        _engine = create_async_engine(
            url,
            echo=False,
            # 只读连接池配置
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )

        _sessionmaker = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

        logger.info("SDE PostgreSQL 数据库引擎初始化成功")
    except Exception as e:
        logger.error(f"SDE 数据库引擎初始化失败: {e}")
        raise e


def get_engine() -> AsyncEngine:
    """获取 SDE 数据库引擎"""
    if _engine is None:
        raise RuntimeError("SDE 数据库引擎尚未初始化")
    return _engine


def get_sessionmaker():
    """获取 SDE 数据库会话构造器"""
    if _sessionmaker is None:
        raise RuntimeError("SDE 数据库会话构造器尚未初始化")
    return _sessionmaker


async def get_session() -> AsyncSession:
    """创建并返回一个新的 SDE 数据库会话"""
    if _sessionmaker is None:
        await init_engine()
    return _sessionmaker()


async def close_engine():
    """关闭 SDE 数据库引擎"""
    global _engine
    if _engine is not None:
        logger.info("关闭 SDE 数据库连接")
        await _engine.dispose()
        _engine = None
