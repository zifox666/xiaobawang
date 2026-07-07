中文 ｜ [English](README_EN.md)

<div style="text-align:center">

## 小霸王 Bot

</div>

<div style="text-align:center">

“可跨平台 EVE 信息查询与订阅机器人”<br>
[在线体验](https://xbw.newdoublex.space/chat) | [文档](https://zifox666.github.io/xiaobawang/)

本项目基于 [Alconna](https://github.com/nonebot/plugin-alconna) 支持多平台交互，并提供网页化订阅管理与后台能力。

> [!NOTE]
> 在接下来的版本中 将会逐步停止对除Milky协议以外的支持

|                           项目地址                           |    平台    |   备注   |
| :----------------------------------------------------------: | :--------: | :------: |
| [LuckyLilliaBot](https://github.com/LLOneBot/LuckyLilliaBot) | OneBot V11 |   可用   |
|        [Napcat](https://github.com/NapNeko/NapCatQQ)         | OneBot V11 | 基本可用 |
|   [Telegram](https://github.com/nonebot/adapter-telegram)    |  Telegram  | 基本可用 |

</div>

## 🛠️ 简单部署

### DOCKER 部署

- 当前版本依赖 **PostgreSQL + Redis**，`docker-compose.yml` 默认提供 Bot、Redis、Playwright，PostgreSQL 需自行准备并在 `.env.local` 中配置
- 本地启动
  ```bash
  docker compose up -d
  ```

### 命令行

```bash
git clone https://github.com/zifox666/xiaobawang.git

cd xiaobawang

pip install uv
uv sync --frozen

uv tool install nb-cli

uv run nb orm upgrade

uv run nb run
```

### 数据库迁移

- 当前主数据库与 SDE 数据库均默认使用 PostgreSQL（见 `.env.example` 中的 `SQLALCHEMY_DATABASE_URL` 与 `SDE_DATABASE_URL`）
- 若你是从旧版 SQLite 升级，可参考 `migrations/sqlite2pgsql.py` 进行数据迁移

## 📝 简单配置

在 `.env.local` 或对应环境的 `.env.*` 文件中填写你的机器人配置项<br>

推荐优先确认以下配置项：

- `SQLALCHEMY_DATABASE_URL`：主数据库连接串（PostgreSQL）
- `SDE_DATABASE_URL`：SDE 数据库连接串（PostgreSQL）
- `REDIS_URL`：Redis 连接串
- `user_agent`：EVE 相关请求必填标识
- `zkb_listener_method`：`r2z2`（推荐）或 `redisQ`
- `admin_token`：启用 `/admin` 管理后台登录
- `billing_enabled` / `billing_unit_price`：订阅积分计费与单价配置

> [!NOTE]
> zkillboard的wss killmail stream订阅已迁移到 [RedisQ](https://github.com/zKillboard/RedisQ)<br>
> zkillboard的km推送 又又又迁移到了 [R2Z2](<https://github.com/zKillboard/zKillboard/wiki/API-(R2Z2)>)

## 📋 功能列表

> [!NOTE]
> 本机器人正在快速开发状态，饼要一点一点画，饭要一点一点吃

### 🆕 近期更新

- **网页订阅中心**：新增 `/subscription` 页面，统一管理 KM 订阅、建筑通知订阅、EVE 服务器状态订阅；部分旧聊天命令已迁移至网页端
- **订阅积分网关**：新增账户积分、低余额提醒、余额不足自动暂停、按订阅类型计费等机制
- **ISK 充值流程**：支持生成支付码，向指定角色转账后自动为会话充值积分
- **管理后台**：新增 `/admin` 页面，可查看会话、订单、订阅、交易记录，并支持手动加积分与手动确认到账
- **建筑推送增强**：建筑通知现支持角色授权、分类订阅与更细的事件过滤
- **数据库升级**：项目已从 SQLite 迁移至 PostgreSQL，配套 Alembic 迁移与 SQLite -> PostgreSQL 迁移脚本已提供

### 🔧 基础功能

- ✅: 完全支持
- 📝: 部分支持
- ❌: 插件/适配器未支持
- 🚫: 协议未支持
- 🚧: 计划中或部分支持或为实验性支持

> [!WARNING]
> 斜体的协议名称意味着其协议或其适配器长时间未维护或已失效

| 功能\适配器              | ONEBOT V11 | Telegram |
| ------------------------ | :--------: | :------: |
| 价格查询 ojita           |     ✅     |    ✅    |
| 查询统计 zkb             |     ✅     |    ✅    |
| 专有名词翻译 trans       |     ✅     |    ✅    |
| 虫洞查询 wormhole        |     ✅     |    ✅    |
| KM订阅 sub               |     ✅     |    ✅    |
| 链接预览 link preview    |     ✅     |    ✅    |
| 旗舰导航规划 JDC         |     🚧     |    🚧    |
| 合同估价 Janice          |     ✅     |    ✅    |
| 深渊装备估价 Abyss       |     🚧     |    🚧    |
| SDE更新                  |     ✅     |    ✅    |
| 汇率查询 currency        |     ✅     |    ✅    |
| EVE服务器状态 eve status |     ✅     |    ✅    |

> [!TIP]
> 订阅相关能力目前更推荐通过网页端使用：`/subscription` 用于用户自助管理，`/admin` 用于后台运营与支付处理

## 📊 数据统计

本项目会收集基本的命令使用统计信息，以帮助我们改进功能和用户体验。收集的数据包括但不限于：

<details>

<summary>收集的数据</summary>

```text
- 机器人ID
- 适配器平台
- 命令来源
- 原始命令
- 事件类型
- 会话ID
```

</details>

**如何禁用**：如果您不希望分享这些数据，可在 `.env` 文件中添加以下配置：

`upload_statistics=false`

## 🙏 感谢

[nonebot / nonebot2](https://github.com/nonebot/nonebot2) ：跨平台 Python 异步机器人框架  
[nonenot / plugin-alconna](https://github.com/nonebot/plugin-alconna): 多平台命令解析适配

## 📜 版权声明

All EVE related materials are property of [CCP Games](https://www.ccpgames.com/)

### CCP GAMES 版权声明

EVE Online 和 EVE 标志是 CCP hf. 的注册商标。全球所有权利均予保留。所有其他商标均为其各自所有者的财产。EVE Online、EVE 标志、EVE 以及所有相关标志和设计均为 CCP hf. 的知识产权。与这些商标相关的所有艺术作品、截图、角色、车辆、故事情节、世界事实或其他可识别的知识产权特征同样属于 CCP hf. 的知识产权。
本项目遵循 CCP GAMES 的使用许可条款，仅用于信息查询和非商业用途。本项目不隶属于 CCP hf.，也未得到 CCP hf. 的认可。CCP 对本项目的内容或功能不承担任何责任，也不对使用本项目而产生的任何损害承担责任。

### License

本项目采用 [GNU通用公共许可证v3.0（GPL-3.0）](https://www.gnu.org/licenses/gpl-3.0.html)
