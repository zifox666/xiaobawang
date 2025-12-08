from functools import wraps
import json
import pickle
from typing import Any, TypeVar

from nonebot import logger
from nonebot_plugin_alconna.uniseg import Receipt
import redis.asyncio as redis

from ...config import plugin_config
from .command_record import get_msg_id

T = TypeVar("T")

# Redis 缓存前缀
CACHE_PREFIX = "xiaobawang:core:"

# 默认的缓存过期时间（1天）
DEFAULT_EXPIRE_TIME = 1 * 24 * 60 * 60


class RedisCache:
    """SDE Redis缓存管理类"""

    _instance = None
    _redis: redis.Redis = None
    _initialized = False

    TIME_SECOND = 60
    TIME_MIN = 60 * TIME_SECOND
    TIME_HOUR = 60 * TIME_MIN
    TIME_DAY = 24 * TIME_MIN

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init(self):
        """初始化Redis连接"""
        if not self._initialized:
            try:
                redis_url = plugin_config.redis_url
                self._redis = redis.from_url(redis_url)
                await self._redis.ping()
                logger.info("SDE Redis缓存连接成功")
                self._initialized = True
            except Exception as e:
                logger.error(f"SDE Redis缓存连接失败: {e}")
                raise e

    async def close(self):
        """关闭Redis连接"""
        if self._initialized and self._redis is not None:
            await self._redis.close()
            logger.info("SDE Redis缓存连接已关闭")
            self._initialized = False

    @property
    def redis(self) -> redis.Redis:
        """获取Redis客户端实例"""
        if not self._initialized:
            raise RuntimeError("Redis缓存尚未初始化")
        return self._redis

    @classmethod
    def _get_key(cls, key: str) -> str:
        """获取带前缀的缓存键名"""
        return f"{CACHE_PREFIX}{key}"

    async def set(self, key: str, value: Any, expire: int = DEFAULT_EXPIRE_TIME) -> bool:
        """
        设置缓存
        :param key: 缓存键名
        :param value: 缓存值
        :param expire: 过期时间（秒）
        :return: 是否成功
        """
        try:
            cache_key = self._get_key(key)

            # 尝试使用JSON序列化，失败则使用pickle
            try:
                serialized = json.dumps(value)
                use_pickle = False
            except (TypeError, OverflowError):
                serialized = pickle.dumps(value)
                use_pickle = True

            # 存储序列化方式的标记
            await self.redis.set(f"{cache_key}:type", "pickle" if use_pickle else "json")
            await self.redis.set(cache_key, serialized)

            if expire > 0:
                await self.redis.expire(cache_key, expire)
                await self.redis.expire(f"{cache_key}:type", expire)

            return True
        except Exception as e:
            logger.error(f"设置缓存失败 {key}: {e}")
            return False

    async def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存
        :param key: 缓存键名
        :param default: 默认返回值
        :return: 缓存值或默认值
        """
        try:
            cache_key = self._get_key(key)

            # 获取序列化类型
            serialization_type = await self.redis.get(f"{cache_key}:type")
            if not serialization_type:
                return default

            data = await self.redis.get(cache_key)
            if data is None:
                return default

            # 根据序列化类型反序列化
            if serialization_type.decode() == "pickle":
                return pickle.loads(data)
            else:
                return json.loads(data)
        except Exception as e:
            logger.error(f"获取缓存失败 {key}: {e}")
            return default

    async def delete(self, key: str) -> bool:
        """
        删除缓存
        :param key: 缓存键名
        :return: 是否成功
        """
        try:
            cache_key = self._get_key(key)
            await self.redis.delete(cache_key, f"{cache_key}:type")
            return True
        except Exception as e:
            logger.error(f"删除缓存失败 {key}: {e}")
            return False

    async def clear_all_sde_cache(self) -> bool:
        """
        清除所有SDE相关缓存
        :return: 是否成功
        """
        try:
            keys = await self.redis.keys(f"{CACHE_PREFIX}*")
            if keys:
                await self.redis.delete(*keys)
            logger.info("已清除所有SDE缓存")
            return True
        except Exception as e:
            logger.error(f"清除所有SDE缓存失败: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        检查缓存是否存在
        :param key: 缓存键名
        :return: 是否存在
        """
        try:
            cache_key = self._get_key(key)
            return await self.redis.exists(cache_key) > 0
        except Exception as e:
            logger.error(f"检查缓存是否存在失败 {key}: {e}")
            return False

    async def mset(self, mapping: dict, expire: int = DEFAULT_EXPIRE_TIME) -> bool:
        """
        批量设置缓存
        :param mapping: 键值映射字典 {key: value, ...}
        :param expire: 过期时间（秒）
        :return: 是否成功
        """
        try:
            pipeline = self.redis.pipeline()

            for key, value in mapping.items():
                cache_key = self._get_key(key)

                # 尝试使用JSON序列化，失败则使用pickle
                try:
                    serialized = json.dumps(value)
                    use_pickle = False
                except (TypeError, OverflowError):
                    serialized = pickle.dumps(value)
                    use_pickle = True

                # 存储序列化方式的标记
                await pipeline.set(f"{cache_key}:type", "pickle" if use_pickle else "json")
                await pipeline.set(cache_key, serialized)

                if expire > 0:
                    await pipeline.expire(cache_key, expire)
                    await pipeline.expire(f"{cache_key}:type", expire)

            await pipeline.execute()
            return True
        except Exception as e:
            logger.error(f"批量设置缓存失败: {e}")
            return False


cache = RedisCache()


def cache_result(expire_time: int = DEFAULT_EXPIRE_TIME, prefix: str = "", exclude_args: list | None = None):
    """
    简化版缓存装饰器，用于缓存函数调用结果
    :param expire_time: 过期时间（秒）
    :param prefix: 缓存键前缀
    :param exclude_args: 排除在缓存键计算之外的参数索引列表
    :return: 装饰器
    """
    exclude_args = exclude_args or []

    def decorator(func):
        # 获取函数名，用于构建缓存键
        func_name = func.__qualname__

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 准备用于缓存键生成的参数
            cache_args = [arg for i, arg in enumerate(args) if i not in exclude_args]

            # 构建简单的缓存键
            key_parts = [prefix, func_name]

            # 添加参数到键中
            if cache_args:
                try:
                    key_parts.append(str(cache_args))
                except Exception:
                    key_parts.append("args")

            # 添加关键字参数
            if kwargs:
                try:
                    sorted_kwargs = sorted(kwargs.items())
                    key_parts.append(str(sorted_kwargs))
                except Exception:
                    key_parts.append("kwargs")

            # 简单拼接成缓存键
            cache_key = ":".join(key_parts)

            # 查询缓存
            result = await cache.get(cache_key)
            if result is not None:
                return result

            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, expire_time)
            return result

        return wrapper

    return decorator


async def save_msg_cache(send_event: Receipt, value_: str | dict):
    """
    储存消息缓存
    :param value_: 要储存的信息
    :param send_event: 发送事件
    """
    msg_id = get_msg_id(send_event)
    await cache.set(f"send_msg_id:{msg_id}", value_)


async def get_msg_cache(msg_id: str) -> str | dict | None:
    """
    获取消息缓存
    :param msg_id: 消息ID
    :return: 缓存的值
    """
    return await cache.get(f"send_msg_id:{msg_id}")
