import json
import pickle
import asyncio
from typing import Any

from nonebot import get_driver
import redis.asyncio as redis
from nonebot import logger


class GlobalCache:
    _instance = None
    _redis: redis.Redis | None = None
    _initialized = False
    _prefix = "xiaobawang:global:"
    _init_lock: asyncio.Lock | None = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def _resolve_redis_url() -> str:
        config = get_driver().config
        redis_url = getattr(config, "cache_redis_url", None) or getattr(config, "redis_url", None)
        if redis_url:
            return redis_url
        legacy_redis_url = getattr(config, "esi_oauth_redis_url", None)
        if legacy_redis_url:
            return legacy_redis_url
        return "redis://127.0.0.1:6379/0"

    async def init(self, redis_url: str | None = None):
        if self._initialized:
            return
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self._initialized:
                return
            target_url = redis_url or self._resolve_redis_url()
            self._redis = redis.from_url(target_url)
            await self._redis.ping()
            self._initialized = True
            logger.info(f"GlobalCache 连接成功: {target_url}")

    async def ensure_init(self):
        if not self._initialized:
            await self.init()

    async def close(self):
        if self._redis is not None:
            await self._redis.close()
        self._initialized = False

    @property
    def redis(self) -> redis.Redis:
        if not self._initialized or self._redis is None:
            raise RuntimeError("GlobalCache 尚未初始化")
        return self._redis

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def set(self, key: str, value: Any, expire: int | None = None) -> bool:
        try:
            await self.ensure_init()
            cache_key = self._key(key)
            try:
                payload = json.dumps(value)
                value_type = "json"
            except (TypeError, ValueError):
                payload = pickle.dumps(value)
                value_type = "pickle"

            await self.redis.set(cache_key, payload)
            await self.redis.set(f"{cache_key}:type", value_type)
            if expire and expire > 0:
                await self.redis.expire(cache_key, expire)
                await self.redis.expire(f"{cache_key}:type", expire)
            return True
        except Exception as e:
            logger.error(f"GlobalCache set 失败 {key}: {e!s}")
            return False

    async def get(self, key: str, default: Any = None) -> Any:
        try:
            await self.ensure_init()
            cache_key = self._key(key)
            value_type = await self.redis.get(f"{cache_key}:type")
            if value_type is None:
                return default

            payload = await self.redis.get(cache_key)
            if payload is None:
                return default

            if value_type.decode() == "pickle":
                return pickle.loads(payload)
            return json.loads(payload)
        except Exception as e:
            logger.error(f"GlobalCache get 失败 {key}: {e!s}")
            return default

    async def delete(self, key: str) -> bool:
        try:
            await self.ensure_init()
            cache_key = self._key(key)
            await self.redis.delete(cache_key, f"{cache_key}:type")
            return True
        except Exception as e:
            logger.error(f"GlobalCache delete 失败 {key}: {e!s}")
            return False


class NamespaceCache:
    def __init__(self, backend: GlobalCache, namespace: str):
        self._backend = backend
        self._namespace = namespace.strip(":")

    def _ns_key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def set(self, key: str, value: Any, expire: int | None = None) -> bool:
        return await self._backend.set(self._ns_key(key), value, expire)

    async def get(self, key: str, default: Any = None) -> Any:
        return await self._backend.get(self._ns_key(key), default)

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(self._ns_key(key))


cache = GlobalCache()


def get_cache(namespace: str) -> NamespaceCache:
    return NamespaceCache(cache, namespace)
