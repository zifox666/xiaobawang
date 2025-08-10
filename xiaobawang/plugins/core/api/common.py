from ..utils.common.cache import cache, cache_result
from ..utils.common.http_client import get_client


@cache_result(expire_time=cache.TIME_HOUR)
async def get_exchangerate() -> dict:
    """
    获取汇率数据
    :return: 汇率数据
    """
    _client = get_client()
    r = await _client.get("https://open.er-api.com/v6/latest/CNY")
    r.raise_for_status()
    return r.json().get("rates", {})
