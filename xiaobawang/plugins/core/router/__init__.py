from fastapi import FastAPI
import nonebot

from .statics import router as statics_router

__all__ = ["app"]

app: FastAPI = nonebot.get_app()

app.include_router(statics_router, prefix="/statics")
