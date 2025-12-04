from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    EVE_PROXY: str = "http://127.0.0.1:7890"

    EVE_DB: str = None
    EVE_JANICE_API_KEY: str = "G9KwKq3465588VPd6747t95Zh94q3W2E"
    EVE_MARKET_API: str = "esi_cache"

    redis_url: str = "redis://127.0.0.1:6379/4"

    proxy: str = None

    user_agent: str = None

    zkb_listener_method: str = "websocket"
    zkb_listener_url: str = "ws://127.0.0.1:8080"

    tq_status_url: str = None

    upload_statistics: bool = True
    upload_statistics_url: str = "https://xbw.newdoublex.space/statics"

    low_memory_mode: bool = False
    max_queue_size: int = 20
    max_total_messages: int = 50


plugin_config = get_plugin_config(Config)

if not plugin_config.user_agent:
    raise RuntimeError("请在配置文件中设置 user_agent")

ROOT_PATH = Path(__name__).parent.absolute()

DATA_PATH = ROOT_PATH / "data"

PLUGIN_PATH = Path(__file__).resolve().parent

SRC_PATH = ROOT_PATH / "xiaobawang" / "src"

HEADERS = {
    "user_agent": f"Nonebot2/XiaoBaWang(https://github.com/zifox666/xiaobawang) zifox666@gmail.com "
    f"Deployed by {plugin_config.user_agent}",
    "Accept-Language": "zh",
}
