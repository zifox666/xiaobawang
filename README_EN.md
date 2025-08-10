[中文](README.md) | English

<div align=center>

## XiaoBaWang Bot

</div>

<div align=center>

"Cross-platform EVE Information Query and Subscription Bot"

This project is based on [Alconna](https://github.com/nonebot/plugin-alconna) supporting multiple platforms, and can interact with the following bot frameworks/platforms

|                             Project                             |  Platform  |   Note   |
|:---------------------------------------------------------------:|:----------:|:--------:|
|       [LLOneBot](https://github.com/LLOneBot/LLOneBot)        |   NTQQ   | Available |
|         [Napcat](https://github.com/NapNeko/NapCatQQ)         |   NTQQ   | Available |
| [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core) |   NTQQ   | Available |
|    [Telegram](https://github.com/nonebot/adapter-telegram)    | Telegram | Basically Available |
|     [Discord](https://github.com/nonebot/adapter-discord)     | Discord  | Untested  |

</div>

## 🛠️ Simple Deployment

```bash
# Get the code
git clone https://github.com/zifox666/xiaobawang.git

# Enter directory
cd xiaobawang

# Install dependencies
pip install uv
uv sync

# Install scaffolding
uv tool install nb-cli

# Start running
uv run nb run
```

## 📝 Simple Configuration

Fill in your bot configuration items in the .env.dev file

> [!NOTE] 
> zkillboard's wss killmail stream subscription has been migrated to RedisQ<br>
> If TQ_STATUS_URL is not configured, the TQ status will be retrieved from CCP ESI, which may cause errors during downtime. It is recommended to research your own TQ status retrieval method<br>
> zkillboard's wss blocks Python websockets, so using wss is not recommended

## 📋 Feature List

> [!NOTE]
> This bot is in rapid development. Rome wasn't built in a day.

### 🔧 Basic Features

- ✅: Fully supported
- 📝: Partially supported
- ❌: Plugin/adapter not supported
- 🚫: Protocol not supported
- 🚧: Planned or partially supported or experimental support

> [!WARNING]
> Protocol names in italics mean that the protocol or its adapter has not been maintained for a long time or has become invalid

| Feature\Adapter      | ONEBOT V11 | Telegram | QQ-API | Console | Kaiheila | Discord |
|---------------------|:----------:|:--------:|:------:|:-------:|:--------:|:-------:|
| Price query ojita    |     ✅     |    ✅    |   ✅   |    ✅    |    ✅    |    ✅    |
| Stats query zkb      |     ✅     |    ✅    |   ✅   |    ✅    |    ✅    |    ✅    |
| Term translation trans |    ✅     |    ✅    |   ✅   |    ✅    |    ✅    |    ✅    |
| Wormhole query      |      ✅       |     ✅      |    ✅     |     ✅     |   ✅   |     ✅     |
| KM subscription sub  |     ✅     |    ✅    |   🚫   |    ✅    |    ✅    |    ✅    |
| Link preview        |     ✅     |    ✅    |   📝   |    📝   |    📝    |    ✅    |
| Jump Drive Calculator JDC |  🚧   |    🚧    |   🚧   |    🚧   |    🚧    |    🚧    |
| Contract appraisal Janice |  ✅   |    ✅    |   📝   |    📝   |    📝    |    ✅    |
| Abyss equipment appraisal |  🚧   |    🚧    |   🚧   |    🚧   |    🚧    |    🚧    |
| SDE update          |     ✅     |    ✅    |   ✅   |    ✅    |    ✅    |    ✅    |
| Currency query      |     ✅     |    ✅    |   ✅   |    ✅    |    ✅    |    ✅    |
| EVE server status   |     ✅     |    ✅    |   ✅   |    ✅    |    ✅    |    ✅    |

## 📊 Statistics Collection

This project collects basic command usage statistics to help us improve features and user experience. The collected data includes but is not limited to:

<details>

<summary>Collected Data</summary>

```text
- Bot ID
- Adapter platform
- Command source
- Original command
- Event type
- Session ID
```

</details>

**How to disable**: If you prefer not to share these statistics, you can add the following configuration to your `.env` file:

`upload_statistics=false`

## 🙏 Acknowledgements

[nonebot / nonebot2](https://github.com/nonebot/nonebot2): Cross-platform Python async bot framework  
[nonebot / plugin-alconna](https://github.com/nonebot/plugin-alconna): Multi-platform command parsing adapter

## 📜 Copyright Notice

All EVE related materials are property of [CCP Games](https://www.ccpgames.com/)

### CCP GAMES Copyright Notice

EVE Online and the EVE logo are registered trademarks of CCP hf. All rights are reserved worldwide. All other trademarks are the property of their respective owners. EVE Online, the EVE logo, EVE and all associated logos and designs are the intellectual property of CCP hf. All artwork, screenshots, characters, vehicles, storylines, world facts or other recognizable features of the intellectual property relating to these trademarks are likewise the intellectual property of CCP hf.
This project follows CCP GAMES' terms of use license and is used solely for information query and non-commercial purposes. This project is not affiliated with CCP hf. and is not endorsed by CCP hf. CCP is not responsible for the content or functionality of this project and shall not be liable for any damages arising from the use of this project.

### License

This project uses the [GNU General Public License v3.0 (GPL-3.0)](https://www.gnu.org/licenses/gpl-3.0.html)