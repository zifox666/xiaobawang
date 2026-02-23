"""
通用验证码绑定服务

提供:
  - generate_verify_code(code, module, payload, expire)  写入缓存
  - consume_verify_code(code)                             消费验证码
  - register_handler(module, handler)                     注册模块绑定回调
  - dispatch_verify(code, user_info)                      命令层统一入口
"""

from typing import Any, Awaitable, Callable

from nonebot import logger
from nonebot_plugin_uninfo import Uninfo

from ..cache import get_cache

cache = get_cache("verify_code")

VERIFY_CODE_PREFIX = "vc:"
VERIFY_CODE_EXPIRE = 600  # 10 分钟

# module_key -> async handler(payload: dict, user_info: Uninfo) -> str
# handler 返回成功提示文本，失败抛出异常
_handlers: dict[str, Callable[[dict, Uninfo], Awaitable[str]]] = {}


def register_handler(
    module: str,
    handler: Callable[[dict, Uninfo], Awaitable[str]],
) -> None:
    """
    注册某模块的验证码绑定回调。

    handler 签名:
        async def handler(payload: dict, user_info: Uninfo) -> str:
            ...
            return "✅ 绑定成功消息"

    payload 为生成验证码时传入的自定义字段（不含 module 字段）。
    """
    _handlers[module] = handler
    logger.debug(f"[verify_code] 注册 handler: {module}")


async def generate_verify_code(
    code: str,
    module: str,
    payload: dict[str, Any],
    expire: int = VERIFY_CODE_EXPIRE,
) -> bool:
    """
    生成验证码并写入缓存。

    Args:
        code:    验证码字符串（调用方自行生成，如 secrets.token_hex(4)）
        module:  模块标识，对应 register_handler 时的 module 参数
        payload: 任意自定义数据，/verify 命令触发时会原样传给 handler
        expire:  过期秒数，默认 600 秒
    """
    data = {"module": module, **payload}
    return await cache.set(f"{VERIFY_CODE_PREFIX}{code}", data, expire=expire)


async def consume_verify_code(code: str) -> dict | None:
    """消费验证码（读取并删除），返回含 module 字段的完整 payload。"""
    data = await cache.get(f"{VERIFY_CODE_PREFIX}{code}")
    if data:
        await cache.delete(f"{VERIFY_CODE_PREFIX}{code}")
    return data


async def dispatch_verify(code: str, user_info: Uninfo) -> str:
    """
    统一入口：消费验证码并分发给对应模块的 handler。

    Returns:
        handler 返回的成功消息字符串

    Raises:
        ValueError: 验证码无效 / 数据异常 / 未知模块
    """
    payload = await consume_verify_code(code)
    if payload is None:
        raise ValueError("验证码无效或已过期，请重新生成")

    module = payload.get("module")
    if not module:
        raise ValueError("验证码数据异常，请重新生成")

    handler = _handlers.get(module)
    if handler is None:
        raise ValueError(f"未知模块 '{module}'，无法处理绑定")

    return await handler(payload, user_info)
