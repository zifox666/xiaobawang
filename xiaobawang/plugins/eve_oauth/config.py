from pathlib import Path
from secrets import token_hex

from nonebot import get_plugin_config, logger
from pydantic import BaseModel


class Config(BaseModel):
	esi_oauth_client_id: str | None = None
	esi_oauth_client_secret: str | None = None
	esi_oauth_redirect_uri: str | None = None

	esi_oauth_authorize_url: str = "https://login.eveonline.com/v2/oauth/authorize"
	esi_oauth_token_url: str = "https://login.eveonline.com/v2/oauth/token"
	esi_oauth_verify_url: str = "https://login.eveonline.com/oauth/verify"

	esi_oauth_redis_url: str = "redis://127.0.0.1:6379/4"
	esi_oauth_proxy: str | None = None
	esi_oauth_refresh_before_seconds: int = 300
	esi_oauth_state_expire_seconds: int = 600

	# 内部 API 访问密钥，未配置时自动生成（仅当次运行有效）
	esi_oauth_api_key: str | None = None


plugin_config = get_plugin_config(Config)

if not plugin_config.esi_oauth_api_key:
	plugin_config.esi_oauth_api_key = token_hex(32)
	logger.warning(
		"未配置 esi_oauth_api_key，已自动生成临时密钥，"
		"建议在 .env 中设置固定值以便其他服务持久化调用"
	)

PLUGIN_PATH = Path(__file__).resolve().parent
SCOPES_PATH = PLUGIN_PATH / "src" / "scopes.json"

