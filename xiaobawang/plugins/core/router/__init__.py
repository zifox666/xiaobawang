import nonebot
from fastapi import FastAPI

from .statics import router as statics_router

__all__ = ["app"]

app: FastAPI = nonebot.get_app()

app.include_router(statics_router, prefix="/statics")
