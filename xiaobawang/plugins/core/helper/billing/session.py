"""
session_key 工具 —— 付费实体标识

付费实体 = session，以 f"{session.scen.type.name}:{session.scen.id}" 为账户主键，
与现有认证/数据隔离方式（按 session_id）完全一致，零迁移成本。

可选 billing_key_with_platform=True 时存储为 f"{platform}:{session_type}:{session_id}"
以避免跨平台 session_id 撞号；对外展示仍建议用不带 platform 的短形式。
"""

from ...config import plugin_config


def make_session_key(
    session_type: str,
    session_id: str,
    platform: str | None = None,
    with_platform: bool | None = None,
) -> str:
    """
    构造付费实体 key。

    Args:
        session_type: 场景类型名 (GROUP/PRIVATE/CHANNEL...)
        session_id: 场景 ID (群号 / 用户号)
        platform: 适配器名 (OneBot V11 / Telegram...)，with_platform=True 时使用
        with_platform: 是否带 platform 前缀防撞；None 时读配置 billing_key_with_platform
    """
    if with_platform is None:
        with_platform = getattr(plugin_config, "billing_key_with_platform", False)
    base = f"{session_type}:{session_id}"
    if with_platform and platform:
        return f"{platform}:{base}"
    return base


def key_from_current_user(current_user: dict, with_platform: bool | None = None) -> str:
    """从 get_current_user 返回的字典构造 key（网页 API 侧使用）"""
    return make_session_key(
        current_user["session_type"],
        current_user["session_id"],
        current_user.get("platform"),
        with_platform,
    )


def key_from_session_fields(
    platform: str,
    session_id: str,
    session_type: str,
    with_platform: bool | None = None,
) -> str:
    """从推送侧的会话四元组字段构造 key（推送拦截器侧使用）"""
    return make_session_key(session_type, session_id, platform, with_platform)


def short_key(session_key: str) -> str:
    """把可能带 platform 前缀的 key 还原为展示用短形式 type:id"""
    parts = session_key.split(":", 2)
    # 带 platform 前缀时为 3 段：platform:TYPE:id（TYPE 可能含冒号？目前不会）
    # 实际 type:id 是 2 段；platform:type:id 是 3 段
    if len(parts) == 3:
        return f"{parts[1]}:{parts[2]}"
    return session_key
