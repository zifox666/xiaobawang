from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    pap_track_url: str | None = None
    api_key: str | None = None


plugin_config = get_plugin_config(Config)
