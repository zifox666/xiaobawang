from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
import nonebot

from .auth import router as auth_router
from .autocomplete import router as autocomplete_router
from .statics import router as statics_router
from .admin import router as admin_router
from .credit import router as credit_router
from .eve_status_sub import router as eve_status_sub_router
from .payment import router as payment_router
from .structure_sub import router as structure_sub_router
from .sub import router as sub_router
from .subscriptions import router as subscriptions_router

__all__ = ["app"]

app: FastAPI = nonebot.get_app()

app.include_router(statics_router, prefix="/statics")
app.include_router(auth_router, tags=["Authentication"])
app.include_router(autocomplete_router, prefix="/autocomplete", tags=["Autocomplete"])
app.include_router(sub_router, prefix="/sub", tags=["Subscription"])
app.include_router(credit_router, prefix="/api/credit", tags=["Credit"])
app.include_router(subscriptions_router, prefix="/api/subscriptions", tags=["Subscriptions"])
app.include_router(structure_sub_router, prefix="/api/subscriptions/structure", tags=["Structure Subscription"])
app.include_router(eve_status_sub_router, prefix="/api/subscriptions/eve_status", tags=["EVE Status Subscription"])
app.include_router(payment_router, prefix="/api/payment", tags=["Payment"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])

# 静态资源目录：css / js 等子目录自动按路径提供
_html_dir = Path(__file__).parent.parent.parent.parent / "src" / "html"
app.mount("/static", StaticFiles(directory=str(_html_dir)), name="core_static")


@app.get("/", summary="首页")
async def home():
    return RedirectResponse(url="/chat")


@app.get("/subscription", summary="订阅管理")
async def subscription():
    """提供订阅管理HTML页面"""
    html_path = _html_dir / "subscription.html"
    return FileResponse(html_path, media_type="text/html; charset=utf-8")


@app.get("/admin", summary="管理后台")
async def admin_page():
    """提供管理后台 HTML 页面（SUPERUSER）"""
    html_path = _html_dir / "admin.html"
    return FileResponse(html_path, media_type="text/html; charset=utf-8")

