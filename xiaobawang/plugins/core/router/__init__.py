from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import nonebot

from .statics import router as statics_router

__all__ = ["app"]

app: FastAPI = nonebot.get_app()

app.include_router(statics_router, prefix="/statics")


@app.get("/", summary="首页")
async def home():
    return RedirectResponse(url="https://zifox666.github.io/xiaobawang/")
