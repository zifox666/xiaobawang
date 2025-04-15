from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    EVE_PROXY: str = "http://127.0.0.1:7890"

    EVE_DB: str = None
    EVE_JANICE_API_KEY: str = "G9KwKq3465588VPd6747t95Zh94q3W2E"
    EVE_MARKET_API: str = "esi_cache"

    REDIS_URL: str = "redis://nas.newdoublex.space:6379/4"

plugin_config = get_plugin_config(Config)

ROOT_PATH = Path(__name__).parent.absolute()

DATA_PATH = ROOT_PATH / "data"

PLUGIN_PATH = Path(__file__).resolve().parent

SRC_PATH = ROOT_PATH / "xiaobawang" / "src"