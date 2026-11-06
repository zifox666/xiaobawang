from sqlalchemy import update

# 历史数据里群会话的 session_type 有 "GROUP" 和 SceneType 枚举值 "1" 两种写法。
# 必须按类型过滤：群号可能与同一 bot 的私聊 QQ 号相同。
GROUP_SESSION_TYPES = ("GROUP", "group", "1")


async def disable_group_subscriptions(session, models, bot_id, group_id) -> dict[str, int]:
    """停用 bot 在指定群的订阅，返回各表实际停用的条数（不提交事务）"""
    disabled = {}
    for model in models:
        result = await session.execute(
            update(model)
            .where(model.session_id == str(group_id))
            .where(model.session_type.in_(GROUP_SESSION_TYPES))
            .where(model.bot_id == str(bot_id))
            .where(model.is_enabled.is_(True))
            .values(is_enabled=False)
        )
        if result.rowcount:
            disabled[model.__tablename__] = result.rowcount
    return disabled
