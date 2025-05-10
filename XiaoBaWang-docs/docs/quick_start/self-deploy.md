---
sidebar_position: 2
---

# 自助部署简介

如果您想自己部署小霸王Bot，可以按照以下简要步骤操作：

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

详细部署请访问 [部署指南](../deploy/installation.md)