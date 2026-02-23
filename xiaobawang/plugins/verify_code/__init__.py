"""
通用验证码绑定插件

其他模块通过 register_handler 注册自己的绑定逻辑，用户执行
/verify <code> 时自动消费验证码并分发给对应模块处理。

公开 API:
    generate_verify_code(code, module, payload, expire)  生成验证码
    register_handler(module, handler)                    注册绑定回调

使用示例（在其他模块的 __init__.py 中）::

    from ..verify_code import generate_verify_code, register_handler

    async def _my_handler(payload: dict, user_info: Uninfo) -> str:
        # 从 payload 取出自定义字段，执行绑定逻辑
        ...
        return "✅ 绑定成功"

    register_handler("my_module", _my_handler)
"""

from nonebot import logger, require
from nonebot.exception import FinishedException

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")

from nonebot_plugin_alconna import Alconna, Args, CommandMeta, on_alconna
from nonebot_plugin_uninfo import Uninfo

from .service import dispatch_verify, generate_verify_code, register_handler

__all__ = ["generate_verify_code", "register_handler"]

# ── /verify 命令（全局唯一，统一处理所有模块的绑定） ────────

_verify_cmd = on_alconna(
    Alconna(
        "verify",
        Args["code", str],
        meta=CommandMeta(
            description="验证绑定（通用）",
            usage="/verify <验证码>",
        ),
    ),
    use_cmd_start=True,
    block=True,
    priority=15,
)


@_verify_cmd.handle()
async def _handle_verify(user_info: Uninfo, code: str):
    try:
        msg = await dispatch_verify(code, user_info)
        await _verify_cmd.finish(msg)
    except FinishedException:
        pass
    except ValueError as e:
        await _verify_cmd.finish(str(e))
    except Exception as e:
        logger.error(f"[verify_code] 处理绑定失败: {e}")
        await _verify_cmd.finish(f"绑定失败: {e}")
