**Chinese** | [English](README_EN.md)

<div style="text-align:center">

## Xiaobawang Bot

</div>

<div style="text-align:center">

"A cross-platform EVE information query and subscription bot"<br>
[Online Demo](https://xbw.newdoublex.space/chat) | [Documentation](https://zifox666.github.io/xiaobawang/)

This project is built on [Alconna](https://github.com/nonebot/plugin-alconna) to support multi-platform interaction, and provides web-based subscription management and admin capabilities.

> [!NOTE]
> In upcoming versions, support for protocols other than Milky will be gradually phased out.

|                          Project Link                           |   Platform   |   Status   |
|:-------------------------------------------------------------:|:------------:|:----------:|
|       [LuckyLilliaBot](https://github.com/LLOneBot/LuckyLilliaBot)        | OneBot V11   | Available  |
|         [Napcat](https://github.com/NapNeko/NapCatQQ)         | OneBot V11   | Basically Available |
|    [Telegram](https://github.com/nonebot/adapter-telegram)    | Telegram     | Basically Available |

</div>

## 🛠️ Simple Deployment

### DOCKER Deployment

- The current version depends on **PostgreSQL + Redis**. The `docker-compose.yml` file provides Bot, Redis, and Playwright by default. PostgreSQL must be prepared separately and configured in `.env.local`.
- Start locally:

    ```bash
    docker compose up -d
    ```

### Command Line

```bash
git clone https://github.com/zifox666/xiaobawang.git

cd xiaobawang

pip install uv      
uv sync --frozen

uv tool install nb-cli

uv run nb orm upgrade

uv run nb run
```

### Database Migration

- Both the main database and the SDE database use PostgreSQL by default (see `SQLALCHEMY_DATABASE_URL` and `SDE_DATABASE_URL` in `.env.example`).
- If you are upgrading from an older SQLite version, refer to `migrations/sqlite2pgsql.py` for data migration.

## 📝 Simple Configuration

Fill in your bot configuration items in `.env.local` or the corresponding `.env.*` file for your environment.<br>

It is recommended to verify the following configuration items first:

- `SQLALCHEMY_DATABASE_URL`: Main database connection string (PostgreSQL)
- `SDE_DATABASE_URL`: SDE database connection string (PostgreSQL)
- `REDIS_URL`: Redis connection string
- `user_agent`: Required identifier for EVE-related requests
- `zkb_listener_method`: `r2z2` (recommended) or `redisQ`
- `admin_token`: Enables login to the `/admin` management backend
- `billing_enabled` / `billing_unit_price`: Subscription credit billing and unit price configuration

> [!NOTE]
> The zkillboard WSS killmail stream subscription has been migrated to [RedisQ](https://github.com/zKillboard/RedisQ)<br>
> The zkillboard KM push has been migrated again to [R2Z2](https://github.com/zKillboard/zKillboard/wiki/API-(R2Z2))

## 📋 Feature List

> [!NOTE]
> This bot is under rapid development. Features are being added step by step.

### 🆕 Recent Updates

- **Web Subscription Center**: Added `/subscription` page for unified management of KM subscriptions, structure notification subscriptions, and EVE server status subscriptions; some legacy chat commands have been migrated to the web interface.
- **Subscription Credit Gateway**: Added account credits, low-balance alerts, automatic suspension on insufficient balance, and per-subscription-type billing mechanisms.
- **ISK Recharge Flow**: Supports generating payment codes; after transferring ISK to a designated character, credits are automatically added to the session.
- **Admin Backend**: Added `/admin` page to view sessions, orders, subscriptions, transaction records, with support for manually adding credits and manually confirming received payments.
- **Structure Notification Enhancements**: Structure notifications now support character authorization, category-based subscription, and finer event filtering.
- **Database Upgrade**: The project has been migrated from SQLite to PostgreSQL, with Alembic migrations and an SQLite-to-PostgreSQL migration script provided.

### 🔧 Basic Features

- ✅: Fully supported
- 📝: Partially supported
- ❌: Not supported by plugin/adapter
- 🚫: Not supported by protocol
- 🚧: Planned, partially supported, or experimental

> [!WARNING]
> Protocol names in *italics* indicate that the protocol or its adapter has been unmaintained for a long time or is no longer functional.

| Feature \ Adapter          |  ONEBOT V11  |  Telegram  |
|----------------------------|:------------:|:----------:|
| Price Query (ojita)        |      ✅       |     ✅      |
| Query Statistics (zkb)     |      ✅       |     ✅      |
| Terminology Translation (trans) |      ✅  |     ✅      |
| Wormhole Query (wormhole)  |      ✅       |     ✅      |
| KM Subscription (sub)      |      ✅       |     ✅      |
| Link Preview               |      ✅       |     ✅      |
| Capital Navigation Planning (JDC) |  🚧  |     🚧     |
| Contract Valuation (Janice)|      ✅       |     ✅      |
| Abyssal Equipment Valuation (Abyss) | 🚧 |     🚧     |
| SDE Update                 |      ✅       |     ✅      |
| Exchange Rate Query (currency) |   ✅   |     ✅      |
| EVE Server Status (eve status) |  ✅   |     ✅      |

> [!TIP]
> Subscription-related features are now recommended for use via the web interface: `/subscription` for user self-management, and `/admin` for backend operations and payment processing.

## 📊 Data Statistics

This project collects basic command usage statistics to help us improve functionality and user experience. The data collected includes but is not limited to:

<details>

<summary>Collected Data</summary>

```text
- Bot ID
- Adapter platform
- Command source
- Raw command
- Event type
- Session ID
```

</details>

**How to Disable**: If you do not wish to share this data, add the following configuration to your `.env` file:

`upload_statistics=false`

## 🙏 Acknowledgments

[nonebot / nonebot2](https://github.com/nonebot/nonebot2): Cross-platform Python asynchronous bot framework  
[nonenot / plugin-alconna](https://github.com/nonebot/plugin-alconna): Multi-platform command parsing adapter

## 📜 Copyright Notice

All EVE related materials are property of [CCP Games](https://www.ccpgames.com/)

### CCP GAMES Copyright Notice

EVE Online and the EVE logo are registered trademarks of CCP hf. All rights reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE, and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts, or other recognizable intellectual property features associated with these trademarks are likewise the intellectual property of CCP hf.
This project is subject to the CCP GAMES usage license terms and is intended solely for information inquiry and non-commercial use. This project is not affiliated with or endorsed by CCP hf. CCP accepts no responsibility for the content or functionality of this project, nor for any damages arising from its use.

### License

This project is licensed under the [GNU General Public License v3.0 (GPL-3.0)](https://www.gnu.org/licenses/gpl-3.0.html)