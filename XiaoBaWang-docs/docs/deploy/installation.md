---
sidebar_position: 1
---

# 安装指南

## 系统要求

- Python 3.8 或更高版本
- Git
- Poetry (Python包管理工具)
- 可选: Redis 服务器 (用于某些高级功能)

## 部署步骤

### 1. 获取项目代码

```bash
# 克隆仓库
git clone https://github.com/zifox666/xiaobawang.git

# 进入项目目录
cd xiaobawang
```

### 2. 安装依赖

```bash
# 安装 Poetry (如果尚未安装)
pip install poetry

# 使用 Poetry 安装项目依赖
poetry install
```

### 3. 配置项目

复制环境配置文件:

`cp .env.dev .env.prod`

按照[配置指南](./configuration.md)编辑 .env.prod 文件

### 4. 启动服务

```bash
poetry run python bot.py
```