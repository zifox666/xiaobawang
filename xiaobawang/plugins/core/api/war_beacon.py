from datetime import datetime
import traceback
from typing import Any

from nonebot import logger

from .base import BaseClient


class WarBeaconAPI(BaseClient):
    """
    EVE 战争信标 API
    """
    def __init__(self):
        super().__init__()
        self._base_url: str = "https://warbeacon.net/api"

    async def auto(
            self,
            system_id: int | str,
            start_time: datetime.time,
            end_time: datetime.time,
    ) -> dict[str, Any] | None:
        """
        自动分队
        :param system_id: 星系ID
        :param start_time: 开始时间
        :param end_time: 结束时间
        :return: 返回分队结果
        """
        endpoint = "/br/auto"
        data = {
            "system_id": system_id,
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "end_time": end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        try:
            data = await self._post(endpoint, data=data)
            if data.get("success") and data.get("data", {}).get("teams"):
                pass
            else:
                return {}
        except Exception as e:
            logger.error(f"WarBeacon API 请求失败: {e}\n{traceback.format_exc()}")
            return {}
