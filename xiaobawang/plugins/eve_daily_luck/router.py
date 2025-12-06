import json
import urllib.parse
from datetime import datetime
from fastapi import APIRouter, Response, Request
from starlette.responses import FileResponse
from pathlib import Path

from .almanac import DailyLuck

router = APIRouter()
plugin_path = Path(__file__).resolve().parent
templates_path = plugin_path / "templates"


def generate_luck_data(user_id: int | str = "browser_user") -> dict:
    """生成今日运势数据"""
    luck_info = DailyLuck(user_id=user_id)
    return {
        "today_str": luck_info.today_str,
        "good_events": luck_info.good_events,
        "bad_events": luck_info.bad_events,
        "direction": luck_info.direction,
        "ships": luck_info.chosen_ships,
        "locals": luck_info.chosen_spaces,
        "goddess_value": luck_info.goddess_value,
        "luck_level": luck_info.get_luck_level(),
        "user_name": "你的",
    }


@router.get("/almanac", summary="查看EVE老黄历浏览器版")
async def get_almanac_browser(request: Request) -> FileResponse:
    """获取EVE老黄历浏览器版静态页面"""
    return FileResponse(templates_path / "browser.html", media_type="text/html; charset=utf-8")


@router.get("/api/luck", summary="获取今日运势API数据")
async def get_luck_api(request: Request, response: Response) -> dict:
    """获取今日运势JSON数据，支持Cookie缓存"""
    today = datetime.now().strftime("%Y-%m-%d")
    uuid = request.cookies.get("user_uuid")

    luck_data = generate_luck_data(user_id=uuid)
    
    response_data = json.dumps(luck_data, ensure_ascii=False)
    encoded_data = urllib.parse.quote(response_data)
    
    response.set_cookie(
        key="daily_luck_data",
        value=encoded_data,
        max_age=86400,  # 24小时
        httponly=False,  # 允许JS访问
        samesite="lax"
    )
    
    # 设置日期cookie用于判断是否是新的一天
    response.set_cookie(
        key="daily_luck_date",
        value=today,
        max_age=86400,
        httponly=False,
        samesite="lax"
    )
    
    return luck_data
