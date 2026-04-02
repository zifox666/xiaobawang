from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    pass


plugin_config = get_plugin_config(Config)
