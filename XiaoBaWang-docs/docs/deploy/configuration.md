---
sidebar_position: 2
---

# 配置指南

小霸王Bot使用环境变量进行配置。您可以通过编辑 `.env.prod` 文件来修改配置。

## 基础配置

```dotenv
# 日志级别: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# 数据库配置 (SQLite)
SQLALCHEMY_DATABASE_URL="sqlite+aiosqlite:///./data/xiaobawang.db"

# Redis配置 (可选，用于高级功能如KM订阅)
# REDIS_URL="redis://localhost:6379/0"

# 超级用户ID列表 (具有管理权限)
SUPERUSER=["123456789"]

# 用户代理 (请使用自己的标识)
user_agent="xiaobawang-bot"

# EVE市场数据API选择: "esi", "evemarketer" 等
EVE_MARKET_API="esi"

# ZKillboard 监听设置
zkb_listener_method="redisQ"
zkb_listener_url="https://redisq.zkillboard.com/listen.php"
```

## Nonebot适配器

请参考nonebot.dev