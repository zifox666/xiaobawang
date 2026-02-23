# 开发规范

## ORM

采用 nonebot-plugin-orm [docs](./orm.md)

## Cache

[cache](./cache/__init__.py) 使用本模块作为缓存

## Uninfo

nonebot-plugin-uninfo 负责处理用户跨平台信息 [docs](./uninfo.md)

## Fastapi

```python
from nonebot import get_app
from fastapi import FastAPI

app: FastAPI = get_app()
app.include_router(router)  # router 来自于 plugins/你的插件/router.py
```

## 网页开发

使用tailwindcss，兼容暗色模式 保证`{code,data,msg}`格式封装

## 定时任务

使用nonebot_plugin_apscheduler

```python
from nonebot import require

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

@scheduler.scheduled_job("cron", hour="*/2", id="xxx", args=[1], kwargs={"arg2": 2})
async def run_every_2_hour(arg1, arg2):
    pass

scheduler.add_job(run_every_day_from_program_start, "interval", days=1, id="xxx")
```

## 命令解析

使用 nonebot_plugin_alconna [demo](./alc.py)

## 代码要求

只保留重要注释 没有许可不需要生成文档
