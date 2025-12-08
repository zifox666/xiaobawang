from fastapi import FastAPI
from fastapi.responses import RedirectResponse, FileResponse
from pathlib import Path
import nonebot

from .statics import router as statics_router
from .sub import router as sub_router
from .auth import router as auth_router
from .autocomplete import router as autocomplete_router

__all__ = ["app"]

app: FastAPI = nonebot.get_app()

app.include_router(statics_router, prefix="/statics")
app.include_router(auth_router, tags=["Authentication"])
app.include_router(autocomplete_router, prefix="/autocomplete", tags=["Autocomplete"])
app.include_router(sub_router, prefix="/sub", tags=["Subscription"])


@app.get("/", summary="首页")
async def home():
    return RedirectResponse(url="/chat")


@app.get("/subscription", summary="订阅管理")
async def subscription():
    """提供订阅管理HTML页面"""
    html_path = Path(__file__).parent.parent.parent.parent / "src" / "html" / "subscription.html"
    return FileResponse(html_path, media_type="text/html; charset=utf-8")


@app.get("/{file_src}/{file_name}")
async def serve_static(file_src: str, file_name: str):
    """提供静态文件"""
    file_path = Path(__file__).parent.parent.parent.parent / "src" / "html" / file_src / file_name
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return {"error": "File not found"}

