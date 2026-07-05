from pathlib import Path
from typing import Literal

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """SDE 模块配置（只读模式 — 数据由外部服务维护）"""

    # 语言和分词
    sde_default_language: Literal["zh", "en", "ru"] = "zh"
    sde_default_participle: Literal["jieba", "normal"] = "jieba"
    jieba_words_path: str | None = None

    # PostgreSQL 独立数据库连接
    sde_database_url: str = "postgresql+psycopg://localhost:5432/eve_sde"

    # Redis 缓存
    redis_url: str = "redis://127.0.0.1:6379/4"


current_dir = Path(__file__).parent.parent.parent.parent
SRC_DIR = current_dir / "xiaobawang" / "src"

plugin_config = get_plugin_config(Config)
