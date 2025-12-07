from nonebot import get_app

from .router import router

# 注册 FastAPI 路由
app = get_app()
app.include_router(router, prefix="/chat")

