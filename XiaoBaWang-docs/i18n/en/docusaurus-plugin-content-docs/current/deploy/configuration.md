---
sidebar_position: 2
---

# Configuration Guide

XiaoBaWang Bot uses environment variables for configuration. You can modify the configuration by editing the `.env.prod` file.

## Basic Configuration

```dotenv
# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Database configuration (SQLite)
SQLALCHEMY_DATABASE_URL="sqlite+aiosqlite:///./data/xiaobawang.db"

# Redis configuration (optional, used for advanced features like KM subscription)
# REDIS_URL="redis://localhost:6379/0"

# Superuser ID list (with administrative permissions)
SUPERUSER=["123456789"]

# User agent (please use your own identifier)
user_agent="xiaobawang-bot"

# EVE market data API selection: "esi", "evemarketer", etc.
EVE_MARKET_API="esi"

# ZKillboard listening settings
zkb_listener_method="redisQ"
zkb_listener_url="https://redisq.zkillboard.com/listen.php"
```

## Nonebot Adapters

Please refer to nonebot.dev