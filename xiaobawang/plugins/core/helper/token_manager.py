import random

from ..utils.common.cache import RedisCache, cache


class TokenManager:
    """
    订阅令牌管理器
    """
    def __init__(self):
        self._cache: RedisCache = cache
        self.cache_prefix = "subscription_token:"
        self.TOKEN_EXPIRY = cache.TIME_DAY

    async def generate_token(
        self,
        user_info: dict,
        expire: int = cache.TIME_DAY
    ) -> str:
        """
        生成临时访问令牌
        """
        token = "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
        await self._cache.set(
            f"{self.cache_prefix}{token}",
            user_info,
            expire
        )
        return token

    async def verify_token(self, token: str) -> dict | None:
        """
        获取令牌对应的用户信息
        """
        user_info = await self._cache.get(f"{self.cache_prefix}{token}")
        if not user_info:
            return None
        return user_info

