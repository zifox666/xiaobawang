[中文](README.md) | English

<div style="text-align:center">

## XiaoBaWang Bot

</div>

<div style="text-align:center">

"A cross-platform EVE information query and subscription bot"<br>
[Online Experience](https://xbw.newdoublex.space/chat) | [Documentation](https://zifox666.github.io/xiaobawang/)

This project is built on [Alconna](https://github.com/nonebot/plugin-alconna) and supports multiple platforms. It can interact with the following projects, bot frameworks, and platforms:

| Project URL | Platform | Note |
|:---------------------------------------------------------------:|:----------:|:--------:|
| [LLOneBot](https://github.com/LLOneBot/LLOneBot) | NTQQ | Available |
| [Napcat](https://github.com/NapNeko/NapCatQQ) | NTQQ | Available |
| [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core) | NTQQ | Available |
| [Telegram](https://github.com/nonebot/adapter-telegram) | Telegram | Basically available |
| [Discord](https://github.com/nonebot/adapter-discord) | Discord | Untested |

</div>

## 🛠️ Quick Deployment

### Docker deployment

- Local build

```bash
docker compose up -d
```

- Pull and run

```bash
docker run newdoublex/xiaobawang:latest -d
```

### Command line

```bash
git clone https://github.com/zifox666/xiaobawang.git

cd xiaobawang

pip install uv
uv sync --frozen

uv tool install nb-cli

uv run nb orm upgrade

uv run nb run
```

## 📝 Simple configuration

Fill in your bot configuration items in the `.env.dev` file.

> [!NOTE]
> The zkillboard WSS killmail stream subscription has been migrated to [RedisQ](https://github.com/zKillboard/RedisQ).


## 📋 Feature list

> [!NOTE]
> This bot is in rapid development — we build features piece by piece.

### 🔧 Basic support levels

- ✅: Fully supported
- 📝: Partially supported
- ❌: Plugin/adapter not supported
- 🚫: Protocol not supported
- 🚧: Planned / partially supported / experimental

> [!WARNING]
> Protocol names in italics indicate the protocol or its adapter is stale or unmaintained.

| Feature \ Adapter | ONEBOT V11 | Telegram | QQ-API | Console | Kaiheila | Discord |
|---------------------|:----------:|:--------:|:------:|:-------:|:--------:|:-------:|
| Price query (ojita) |     ✅     |    ✅    |   ✅   |    ✅   |    ✅    |    ✅   |
| Stats query (zkb)   |     ✅     |    ✅    |   ✅   |    ✅   |    ✅    |    ✅   |
| Term translation (trans) | ✅    |    ✅    |   ✅   |    ✅   |    ✅    |    ✅   |
| Wormhole query (wormhole) | ✅   |    ✅    |   ✅   |    ✅   |    ✅    |    ✅   |
| KM subscription (sub) |    ✅   |    ✅    |   🚫   |    ✅   |    ✅    |    ✅   |
| Link preview         |     ✅     |    ✅    |   📝   |    📝   |    📝    |    ✅   |
| Jump Drive Calculator (JDC) | 🚧  |    🚧    |   🚧   |    🚧   |    🚧    |    🚧  |
| Contract appraisal (Janice) | ✅ |    ✅    |   📝   |    📝   |    📝   |    ✅   |
| Abyss equipment appraisal (Abyss) | 🚧 | 🚧 |  🚧  |   🚧  |   🚧   |   🚧  |
| SDE update           |     ✅     |    ✅    |   ✅   |    ✅   |    ✅    |    ✅   |
| Currency query       |     ✅     |    ✅    |   ✅   |    ✅   |    ✅    |    ✅   |
| EVE server status    |     ✅     |    ✅    |   ✅   |    ✅   |    ✅    |    ✅   |


## 📊 Statistics collection

This project collects basic command usage statistics to help us improve features and user experience. Collected data includes but is not limited to:

<details>

<summary>Collected data</summary>

```text
- Bot ID
- Adapter platform
- Command source
- Original command
- Event type
- Session ID
```

</details>

**How to disable**: If you do not want to share this data, add the following to your `.env` file:

`upload_statistics=false`


## 🙏 Thanks

[nonebot / nonebot2](https://github.com/nonebot/nonebot2): Cross-platform Python async bot framework  
[nonebot / plugin-alconna](https://github.com/nonebot/plugin-alconna): Multi-platform command parsing adapter


## 📜 Copyright

All EVE related materials are property of [CCP Games](https://www.ccpgames.com/)

### CCP GAMES Copyright Notice

EVE Online and the EVE logo are registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features related to these trademarks are likewise the intellectual property of CCP hf.
This project follows CCP GAMES' terms of use and is intended only for information query and non-commercial use. This project is not affiliated with or endorsed by CCP hf. CCP is not responsible for the content or functionality of this project and shall not be liable for any damages arising from its use.

### License

This project is licensed under the [GNU General Public License v3.0 (GPL-3.0)](https://www.gnu.org/licenses/gpl-3.0.html)
