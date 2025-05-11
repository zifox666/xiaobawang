中文 ｜ [English](README_EN.md)

<div align=center>

## 小霸王 Bot

</div>

<div align=center>

“可跨平台 EVE 信息查询与订阅机器人”

本项目基于 [Alconna](https://github.com/nonebot/plugin-alconna) 支持多个平台，可基于以下项目与机器人框架/平台进行交互

|                             项目地址                              |    平台    |  备注  |
|:-------------------------------------------------------------:|:--------:|:----:|
|       [LLOneBot](https://github.com/LLOneBot/LLOneBot)        |   NTQQ   |  可用  |
|         [Napcat](https://github.com/NapNeko/NapCatQQ)         |   NTQQ   |  可用  |
| [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core) |   NTQQ   |  可用  |
|    [Telegram](https://github.com/nonebot/adapter-telegram)    | Telegram | 基本可用 |
|     [Discord](https://github.com/nonebot/adapter-discord)     | Discord  | 未测试  |

</div>

## 🛠️ 简单部署

```bash
# 获取代码
git clone https://github.com/zifox666/xiaobawang.git

# 进入目录
cd xiaobawang

# 安装依赖
pip install poetry      # 安装 poetry
poetry install          # 安装依赖

# 开始运行
poetry run python bot.py
```

## 📝 简单配置

在 .env.dev 文件中填写你的机器人配置项

## 📋 功能列表

> [!NOTE]
> 本机器人正在快速开发状态，饼要一点一点画，饭要一点一点吃

### 🔧 基础功能

- ✅: 完全支持
- 📝: 部分支持
- ❌: 插件/适配器未支持
- 🚫: 协议未支持
- 🚧: 计划中或部分支持或为实验性支持

> [!WARNING]
> 斜体的协议名称意味着其协议或其适配器长时间未维护或已失效

| 功能\适配器              |  ONEBOT V11  |  Telegram  |  QQ-API  |  Console  |  开黑啦  |  Discord  |
|---------------------|:------------:|:----------:|:--------:|:---------:|:-----:|:---------:|
| 价格查询 ojita          |      ✅       |     ✅      |    ✅     |     ✅     |   ✅   |     ✅     |
| 查询统计 zkb          |      ✅       |     ✅      |    ✅     |     ✅     |   ✅   |     ✅     |
| 专有名词翻译 trans        |      ✅       |     ✅      |    ✅     |     ✅     |   ✅   |     ✅     |
| 虫洞查询 wormhole       |      ✅       |     ✅      |    ✅     |     ✅     |   ✅   |     ✅     |
| KM订阅  sub           |      ✅       |     ✅      |    🚫    |     ✅     |   ✅   |     ✅     |
| 链接预览 link preview   |      ✅       |     ✅      |    📝    |    📝     |  📝   |     ✅     |
| 旗舰导航规划      JDC     |      🚧      |     🚧     |    🚧    |    🚧     |  🚧   |    🚧     | 🚧       |
| 合同估价 Janice         |      ✅       |     ✅      |    📝    |    📝     |  📝   |     ✅     |
| 深渊装备估价 Abyss        |      🚧      |     🚧     |    🚧    |    🚧     |  🚧   |    🚧     | 🚧       |
| SDE更新               |      ✅       |     ✅      |    ✅     |     ✅     |   ✅   |     ✅     |
| 汇率查询 currency       |      ✅       |     ✅      |    ✅     |     ✅     |   ✅   |     ✅     |
| EVE服务器状态 eve status |      ✅       |     ✅      |    ✅     |     ✅     |   ✅   |     ✅     |


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
