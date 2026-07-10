from nonebot import logger

from ..utils.common.cache import cache, cache_result
from ..utils.common.http_client import get_client


class KillmailFetchError(Exception):
    """获取 killmail 数据失败。"""


class KillmailNotFoundError(KillmailFetchError):
    """zKillboard 暂未返回指定 killmail。"""


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
        zkb_list = r.json()
    except Exception as e:
        raise e

    if not zkb_list:
        try:
            r = await client.get(url=f"https://warbeacon.net/api/killmail/{kill_id}")
            r.raise_for_status()
            zkb_list = r.json()
            zkb_list[0] = zkb_list.get("data", {})
        except Exception as e:
            logger.error(f"[{kill_id}] 获取 killmail 数据失败: {e}")

    if not zkb_list:
        logger.warning(f"[{kill_id}] zKillboard 未返回 killmail 数据")
        raise KillmailNotFoundError(f"zKillboard 未找到 killmail: {kill_id}")

    zkb = zkb_list[0].get("zkb") or {}
    killmail_hash = zkb.get("hash")
    if not killmail_hash:
        logger.warning(f"[{kill_id}] zKillboard 数据缺少 hash")
        raise KillmailFetchError(f"zKillboard 数据缺少 hash: {kill_id}")

    esi_url = f"https://esi.evetech.net/latest/killmails/{kill_id}/{killmail_hash}/"
    try:
        r = await client.get(esi_url, headers={"X-Compatibility-Date": "2025-12-16"})
        r.raise_for_status()
    except Exception as e:
        logger.error(f"[{kill_id}] 获取 ESI killmail 失败: {e}")
        raise KillmailFetchError(f"获取 ESI killmail 失败: {kill_id}") from e
    data = r.json()
    data["zkb"] = zkb

    return data
