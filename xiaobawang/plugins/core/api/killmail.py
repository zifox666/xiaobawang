from nonebot import logger

from ..utils.common.cache import cache, cache_result
from ..utils.common.http_client import get_client


@cache_result(expire_time=cache.TIME_HOUR)
async def get_zkb_killmail(
    kill_id: int,
) -> dict:
    """
    获取zkb组合信息
    Res:
        kill_id
    Return:
        zkb info
    """
    client = get_client()
    url = f"https://zkillboard.com/api/killID/{kill_id}/"
    try:
        r = await client.get(url)
        r.raise_for_status()
    except Exception as e:
        raise e
    zkb = r.json()[0].get("zkb")
    esi_url = f"https://esi.evetech.net/latest/killmails/{kill_id}/{zkb.get('hash')}/"
    try:
        r = await client.get(esi_url)
        r.raise_for_status()
    except Exception as e:
        logger.error(e)
        return {}
    data = r.json()
    data["zkb"] = zkb

    return data
