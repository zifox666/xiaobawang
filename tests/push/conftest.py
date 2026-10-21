"""Load the queue without starting the bot, schedulers or external services."""
import importlib.util
from pathlib import Path
import sys
import types

import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

ROOT = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def load_module(name, relative):
    parent = name.rsplit(".", 1)[0]
    for i in range(1, len(parent.split(".")) + 1):
        package = ".".join(parent.split(".")[:i])
        if package not in sys.modules:
            module = types.ModuleType(package)
            module.__path__ = []
            sys.modules[package] = module
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


original_orm = sys.modules.get("nonebot_plugin_orm")
fake_orm = types.ModuleType("nonebot_plugin_orm")
fake_orm.Model = Base
sys.modules["nonebot_plugin_orm"] = fake_orm
try:
    for model in ("credit", "record", "push"):
        load_module(f"push_test.core.db.models.{model}", f"xiaobawang/plugins/core/db/models/{model}.py")
finally:
    if original_orm is None:
        del sys.modules["nonebot_plugin_orm"]
    else:
        sys.modules["nonebot_plugin_orm"] = original_orm

store_module = load_module("push_test.core.helper.push.store", "xiaobawang/plugins/core/helper/push/store.py")


@pytest_asyncio.fixture
async def store(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'push.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield store_module.PushStore(sessions, initial_credit=100, bot_interval=0)
    await engine.dispose()
