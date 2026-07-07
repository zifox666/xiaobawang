from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class Config(BaseModel):
    EVE_PROXY: str = "http://127.0.0.1:7890"

    EVE_DB: str = None
    EVE_JANICE_API_KEY: str = "G9KwKq3465588VPd6747t95Zh94q3W2E"
    EVE_MARKET_API: str = "esi_cache"

    redis_url: str = "redis://127.0.0.1:6379/4"

    proxy: str = None

    user_agent: str = None

    zkb_listener_method: str = "r2z2"
    zkb_listener_url: str = "https://zkillredisq.stream/listen.php"

    tq_status_url: str = None

    upload_statistics: bool = True
    upload_statistics_url: str = "https://xbw.newdoublex.space/statics"

    low_memory_mode: bool = False
    max_queue_size: int = 20
    max_total_messages: int = 50

    billing_enabled: bool = True
    billing_enabled_modules: list[str] = Field(
        default_factory=lambda: ["killmail", "eve_status", "structure"], description="启用计费的模块"
    )
    billing_initial_credit: int = 100  # 新账户初始积分
    billing_migrate_credit: int = 100  # 存量 session 迁移积分
    billing_low_balance_threshold: int = 10  # 低余额预警线
    billing_pause_after_nsf: int = 3  # 连续 N 次余额不足后暂停订阅
    billing_unit_price: dict = Field(
        default_factory=lambda: {"eve_status": 1, "structure": 2, "killmail": 5}
    )
    billing_key_with_platform: bool = False  # session_key 是否带 platform 前缀防撞
    admin_token: str | None = None  # 管理后台登录 token；配置后 /admin 使用该 token 登录


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
