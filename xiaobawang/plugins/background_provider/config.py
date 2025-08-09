from pathlib import Path
from typing import Literal

from nonebot import get_plugin_config
from pydantic import BaseModel

plugin_path = Path(__file__).resolve().resolve()
DEFAULT_BG_PATH = plugin_path / "bg.jpg"


class Config(BaseModel):
    bg_provider: str = "loli"
    bg_preload_count: int = 5
    bg_lolicon_r18_type: Literal[0, 1, 2] = 0
    bg_local_path: Path = DEFAULT_BG_PATH
    req_timeout: int | None = 10
    proxy: str = None


plugin_config = get_plugin_config(Config)
