"""
定时拉取 ESI 通知并推送到绑定会话
"""

from datetime import datetime, timedelta, timezone
import json

from nonebot import logger
from nonebot_plugin_alconna import Target, UniMessage

from .categories import TYPE_TO_CATEGORY
from .service import (
    fetch_notifications,
    format_notification,
    get_all_enabled_subscriptions,
    mark_pushed,
    save_notifications,
)


async def poll_and_push():
    """
    定时任务入口:
    1. 获取所有启用的订阅, 按角色分组
    2. 对每个角色拉取 ESI 通知
    3. 存入数据库, 仅对新记录进行推送
    """
    subs = await get_all_enabled_subscriptions()
    if not subs:
        return

    # 按角色分组
    char_subs: dict[int, list] = {}
    for s in subs:
        char_subs.setdefault(s.character_id, []).append(s)

    for character_id, sub_list in char_subs.items():
        try:
            await _process_character(character_id, sub_list)
        except Exception as e:
            logger.error(f"处理角色 {character_id} 建筑通知时出错: {e}")


async def _process_character(character_id: int, sub_list: list):
    """处理单个角色的通知拉取和推送"""
    notifications = await fetch_notifications(character_id)
    if not notifications:
        return

    new_records = await save_notifications(character_id, notifications)
    if not new_records:
        return

    logger.info(f"角色 {character_id} 新增 {len(new_records)} 条建筑通知")

    # 对每个订阅, 过滤出匹配的通知并推送
    pushed_ids: list[int] = []

    for sub in sub_list:
        try:
            sub_categories = json.loads(sub.categories) if sub.categories else []
        except (json.JSONDecodeError, TypeError):
            sub_categories = []

        if not sub_categories:
            continue

        # 过滤出该订阅关心的通知, 超过 2 天的不推送
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=2)
        matched_records = []
        for record in new_records:
            if record.timestamp and record.timestamp < cutoff:
                continue
            cat = TYPE_TO_CATEGORY.get(record.notification_type)
            if cat and cat in sub_categories:
                matched_records.append(record)

        if not matched_records:
            continue

        # 构造推送消息
        character_name = sub.character_name or str(character_id)
        lines = [f"📢 建筑通知 ({character_name}) - {len(matched_records)} 条"]
        for record in matched_records:
            lines.append("─" * 10)
            lines.append(format_notification(record, character_name))

        message_text = "\n".join(lines)

        # 发送到绑定的会话
        try:
            target = Target(
                id=sub.session_id,
                self_id=sub.bot_id,
                channel=True if sub.session_type.upper() in ("GROUP", "CHANNEL") else False,
                private=sub.session_type.upper() == "PRIVATE",
                platform=sub.platform,
            )
            await UniMessage.text(message_text).send(target=target)
            logger.info(
                f"建筑通知推送成功: 角色={character_id} 会话={sub.session_id} "
                f"通知数={len(matched_records)}"
            )
            pushed_ids.extend(r.id for r in matched_records)
        except Exception as e:
            logger.error(
                f"建筑通知推送失败: 角色={character_id} 会话={sub.session_id} 错误={e}"
            )

    await mark_pushed(pushed_ids)
