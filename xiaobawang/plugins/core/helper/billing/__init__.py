"""
积分计费层（Billing）

对外暴露:
    billing            —— BillingGateway 单例，三模块推送侧 import 使用
    BillingRules       —— 计费规则与复杂度计算
    make_session_key / key_from_current_user / key_from_session_fields
                       —— session_key 构造（付费实体标识）
"""

from .gateway import BillingGateway, ChargeResult, billing
from .rules import BillingRules
from .session import (
    key_from_current_user,
    key_from_session_fields,
    make_session_key,
    short_key,
)

# 导入 payment 模块以注册 ESI 钱包 scope + journal 定时拉取任务
from . import payment  # noqa: F401,E402

__all__ = [
    "BillingGateway",
    "ChargeResult",
    "billing",
    "BillingRules",
    "make_session_key",
    "key_from_current_user",
    "key_from_session_fields",
    "short_key",
]
