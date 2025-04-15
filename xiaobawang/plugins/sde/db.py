from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from nonebot import logger

Base = declarative_base()

_engine = None
_sessionmaker = None


async def init_engine(db_path: str = None):
    """初始化SDE数据库引擎"""
    global _engine, _sessionmaker

    try:
        url = f"sqlite+aiosqlite:///{db_path}"

        logger.info(f"初始化SDE数据库连接: {url}")

        _engine = create_async_engine(
            url,
            poolclass=NullPool,  # SQLite建议使用NullPool
            echo=False
        )

        _sessionmaker = sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        logger.info("SDE数据库引擎初始化成功")
    except Exception as e:
        logger.error(f"SDE数据库引擎初始化失败: {e}")
        raise e


def get_engine() -> AsyncEngine:
    """获取SDE数据库引擎"""
    if _engine is None:
        raise RuntimeError("SDE数据库引擎尚未初始化")
    return _engine


def get_sessionmaker():
    """获取SDE数据库会话构造器"""
    if _sessionmaker is None:
        raise RuntimeError("SDE数据库会话构造器尚未初始化")
    return _sessionmaker


async def get_session() -> AsyncSession:
    """创建并返回一个新的SDE数据库会话"""
    if _sessionmaker is None:
        await init_engine()
    return _sessionmaker()


async def close_engine():
    """关闭SDE数据库引擎"""
    global _engine
    if _engine is not None:
        logger.info("关闭SDE数据库连接")
        await _engine.dispose()
        _engine = None