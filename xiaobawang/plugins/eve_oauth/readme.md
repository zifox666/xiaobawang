# EVE ESI OAuth 授权管理模块

管理 EVE Online ESI OAuth2 授权流程，集中存储 `refresh_token`，通过 Redis 缓存 `access_token`，供机器人其他插件安全获取。

## 配置

在 `.env` 中添加：

```env
# 必填 - 从 https://developers.eveonline.com 创建应用获取
esi_oauth_client_id=你的client_id
esi_oauth_client_secret=你的client_secret
esi_oauth_redirect_uri=http://你的域名:8170/esi/oauth/page

# 可选 - 内部 API 密钥（未设置则每次启动自动生成临时密钥）
esi_oauth_api_key=一个随机字符串

# 可选 - 覆盖默认值
esi_oauth_proxy=http://127.0.0.1:7890
esi_oauth_refresh_before_seconds=300
esi_oauth_state_expire_seconds=600
```

## 授权页面

启动后访问 `http://你的域名:8170/esi/oauth/page`，选择 scopes 后点击「立即前往授权」，完成 EVE 登录后自动回调并保存授权。

## 其他插件调用

通过 `api.py` 提供的 Python API 调用，进程内直接 import，**无需 API key**：

```python
from xiaobawang.plugins.eve_oauth.api import (
    require_scopes,
    get_access_token,
    get_authorized_scopes,
    is_authorized,
)

# 1. 注册所需 scopes（插件加载时调用一次，授权页会自动聚合展示）
require_scopes("你的插件名", [
    "esi-characters.read_notifications.v1",
])

# 2. 获取 access_token（自动缓存、自动刷新）
token_data = await get_access_token(character_id=12345)
access_token = token_data["access_token"]

# 3. 检查角色已授权的 scopes
scopes = await get_authorized_scopes(character_id=12345)

# 4. 判断是否已授权且覆盖指定 scopes
ok = await is_authorized(12345, ["esi-characters.read_notifications.v1"])
```

> `get_access_token` 在角色未授权或权限不足时抛出 `ValueError`。

## Scopes 管理

在 `src/scopes.json` 中定义用户可选/必选的授权范围：

```json
[
  { "scope": "publicData", "name": "公开数据", "description": "...", "required": true },
  { "scope": "esi-killmails.read_killmails.v1", "name": "击杀邮件", "description": "...", "required": false }
]
```

各插件通过 `require_scopes()` 注册的 scopes 也会自动合并到授权链接中。

## HTTP API

所有接口均为 POST，前缀 `/esi`。

| 端点 | 说明 | 鉴权 |
|---|---|---|
| `/oauth/page` | 授权管理页面 (GET) | 无 |
| `/oauth/scopes` | 获取可选 scopes 列表 | 无 |
| `/oauth/registered_plugins` | 获取已注册插件及其所需 scopes | 无 |
| `/oauth/list_authorizations` | 获取已授权角色列表 | 无 |
| `/oauth/create_auth_url` | 构造授权链接 | 无 |
| `/oauth/exchange_code` | 回调授权码交换 | 无 |
| `/oauth/get_authorization` | 查询角色授权详情 | **需要 API key** |
| `/oauth/get_access_token` | 获取角色 access_token | **需要 API key** |
| `/oauth/refresh` | 手动刷新角色 token | **需要 API key** |

受保护端点需在请求头中携带 `X-ESI-API-Key: 你配置的密钥`。

## 文件结构

| 文件 | 说明 |
|---|---|
| `__init__.py` | 插件入口，注册路由和定时刷新任务 |
| `config.py` | 配置定义 |
| `models.py` | ORM 模型（`esi_oauth_authorization` 表） |
| `service.py` | OAuth 核心逻辑（token 交换/刷新/缓存） |
| `router.py` | HTTP 路由 |
| `api.py` | **其他插件的调用入口** |
| `src/scopes.json` | Scope 定义 |
| `src/oauth.html` | 前端授权页 |
