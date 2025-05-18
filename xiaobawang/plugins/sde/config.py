from typing import Literal, Optional

from nonebot import get_plugin_config
from pydantic import BaseModel
from pathlib import Path


class Config(BaseModel):
    sde_default_language: Literal["zh", "en", "ru"] = "zh"
    sde_default_participle: Literal["jieba", "normal"] = "jieba"

    sde_download_url: str = "https://www.fuzzwork.co.uk/dump/sqlite-latest.sqlite.bz2"
    sde_auto_download: bool = True
    sde_db_path: str = None
    jieba_words_path: Optional[str] = None

    redis_url: str = "redis://127.0.0.1:6379/4"


current_dir = Path(__file__).parent.parent.parent.parent
SDE_DB_PATH = current_dir / "data" / "sqlite-latest.sqlite3"
SRC_DIR = current_dir / "xiaobawang" / "src"

plugin_config = get_plugin_config(Config)