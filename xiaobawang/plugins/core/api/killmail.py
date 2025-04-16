from typing import Dict

from ..utils.common.cache import cache_result, cache
from ..utils.common.http_client import get_client


@cache_result(expire_time=cache.TIME_HOUR, prefix="killmail:get_zkb_killmail")
async def get_zkb_killmail(
        kill_id: int,
) -> Dict:
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
    esi_url = f"https://esi.evetech.net/latest/killmails/{kill_id}/{zkb.get("hash")}/"
    try:
        r = await client.get(esi_url)
        r.raise_for_status()
    except Exception as e:
        raise e
    data = r.json()
    data["zkb"] = zkb

    return data