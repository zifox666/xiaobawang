"""
ESI 钱包 journal 封装

需要 scope: esi-wallet.read_character_wallet.v1
文档: https://esi.evetech.net/latest/characters/{character_id}/wallet/journal/
"""

import httpx
from nonebot import logger

from ...config import plugin_config
from xiaobawang.plugins.eve_oauth.api import get_access_token

ESI_WALLET_JOURNAL_URL = "https://esi.evetech.net/latest/characters/{character_id}/wallet/journal/"


async def get_wallet_journal(character_id: int, rows: int = 100) -> list[dict]:
    """
    拉取角色钱包 journal（最近 rows 条）。

    journal 条目关键字段:
      - ref_id:        条目唯一 ID（去重用）
      - date:          时间
      - amount:        金额（ISK，正数入账）
      - type:          交易类型（player_donation 为玩家转账）
      - reason:        转账备注（匹配支付码）
      - first_party:   付款方 ID
      - second_party:  收款方 ID（应为钱包角色本人）
    """
    try:
        token_info = await get_access_token(
            character_id,
            required_scopes=["esi-wallet.read_character_wallet.v1"],
        )
    except ValueError as e:
        logger.warning(f"[wallet] 获取角色 {character_id} access_token 失败: {e}")
        return []

    access_token = token_info["access_token"]
    url = ESI_WALLET_JOURNAL_URL.format(character_id=character_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "X-Compatibility-Date": "2025-12-16",
    }
    proxy = plugin_config.proxy

    try:
        async with httpx.AsyncClient(timeout=20, proxy=proxy) as client:
            resp = await client.get(url, headers=headers, params={"rows": rows})
            if resp.status_code == 304:
                return []
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"[wallet] 拉取 journal 失败 (角色 {character_id}): {e}")
        return []
