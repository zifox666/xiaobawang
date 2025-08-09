import asyncio

from arclet.alconna import Alconna, Args, Arparma, CommandMeta, MultiVar, Option, Subcommand
from nonebot import logger
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_orm import AsyncSession
from nonebot_plugin_uninfo import SceneType, Uninfo

from ..api.esi.universe import esi_client
from ..helper.subscription import KillmailSubscriptionManager
from ..helper.zkb.listener import zkb_listener

__all__ = ["start_km_listen", "start_km_listen_", "stop_km_listen_", "sub", "sub_high"]


start_km_alc = Alconna("wss", Subcommand("start"), Subcommand("stop"))


start_km_listen = on_alconna(start_km_alc, use_cmd_start=True, permission=SUPERUSER)


@start_km_listen.assign("start")
async def start_km_listen_():
    _ = asyncio.create_task(zkb_listener.start())  # noqa: RUF006
    logger.info("开始监听zkb")


@start_km_listen.assign("stop")
async def stop_km_listen_():
    await zkb_listener.stop()
    logger.info("停止监听zkb")


category_type_list = {
    "char": "character",
    "corp": "corporation",
    "alli": "alliance",
    "system": "system",
    "角色": "character",
    "军团": "corporation",
    "联盟": "alliance",
    "星系": "system",
    "ship": "inventory_type",
    "舰船": "inventory_type",
}


sub = on_alconna(
    Alconna(
        "sub",
        Subcommand(
            "add",
            Args["type", str]["name", MultiVar(str)],
            Option("-a|--attack", Args["value", int, 30_000_000]),
            Option("-v|--victim", Args["value", int, 30_000_000]),
        ),
        Subcommand(
            "remove",
            Args["type", str]["name", MultiVar(str)],
        ),
        Subcommand("list"),
        meta=CommandMeta(fuzzy_match=True),
    ),
    use_cmd_start=True,
)


sub_high = on_alconna(
    Alconna(
        "sub_high",
        Args["value", int, 18_000_000_000],
        Option("-r|--remove", help_text="移除高价值订阅"),
        meta=CommandMeta(fuzzy_match=True),
    ),
    use_cmd_start=True,
)


@sub.assign("add")
async def _add_sub(
    result: Arparma,
    user_info: Uninfo,
    session: AsyncSession,
):
    if user_info.member and user_info.member.role.id not in ["CHANNEL_ADMINISTRATOR", "ADMINISTRATOR", "OWNER"]:
        await sub.finish("你还不是群管理员，无法使用此功能")

    platform = user_info.adapter
    target_name = " ".join(result.name)
    try:
        id_data = await esi_client.get_universe_id(
            type_=f"{category_type_list[result.type]}s",
            name=target_name,
        )
    except Exception:
        await sub.finish(f"[{target_name}]不存在，请检查")

    if id_data.get("id"):
        target_id = id_data["id"]
        target_name = id_data["name"]

        session_id = user_info.scene.id
        session_type = user_info.scene.type

        attack_limit = result.add.options.get("attack").args.get("value")
        victim_limit = result.add.options.get("victim").args.get("value")

        async with session:
            sub_manager = KillmailSubscriptionManager(session)
            if int(attack_limit) != 0:
                attack_limit = attack_limit if attack_limit >= 20_000_000 else 50_000_000

                a_flag = await sub_manager.add_subscription(
                    platform=platform,
                    bot_id=user_info.self_id,
                    target_id=target_id,
                    target_name=target_name,
                    target_type=category_type_list[result.type],
                    session_id=session_id,
                    session_type=session_type,
                    sub_type="condition",
                    min_value=attack_limit,
                    is_victim=False,
                )
            if int(victim_limit) != 0:
                victim_limit = victim_limit if victim_limit >= 20_000_000 else 50_000_000

                v_flag = await sub_manager.add_subscription(
                    platform=platform,
                    bot_id=user_info.self_id,
                    target_id=target_id,
                    target_name=target_name,
                    target_type=category_type_list[result.type],
                    session_id=session_id,
                    session_type=session_type,
                    sub_type="condition",
                    min_value=victim_limit,
                    is_victim=True,
                )

        if a_flag or v_flag:
            logger.info(f"""订阅已增加
[{platform}]{user_info.self_id}
[{SceneType(user_info.scene.type).name}]{session_id}
[{category_type_list[result.type]}]{target_name}({target_id})
[击杀推送阈值]{attack_limit if a_flag else "关闭"}
[损失推送阈值]{victim_limit if v_flag else "关闭"}""")

            await sub.finish(f"""订阅已增加
[{platform}]{user_info.self_id}
[{SceneType(user_info.scene.type).name}]{session_id}
[{category_type_list[result.type]}]{target_name}({target_id})
[击杀推送阈值]{attack_limit if a_flag else "关闭"}
[损失推送阈值]{victim_limit if v_flag else "关闭"}""")


@sub.assign("remove")
async def _remove_sub(
    result: Arparma,
    user_info: Uninfo,
    session: AsyncSession,
):
    if user_info.member and user_info.member.role.id not in ["CHANNEL_ADMINISTRATOR", "ADMINISTRATOR", "OWNER"]:
        await sub.finish("你还不是群管理员，无法使用此功能")

    platform = user_info.adapter
    target_name = " ".join(result.name)
    try:
        id_data = await esi_client.get_universe_id(
            type_=f"{category_type_list[result.type]}s",
            name=target_name,
        )
    except Exception:
        await sub.finish(f"[{target_name}]不存在，请检查")

    if id_data.get("id"):
        target_id = id_data["id"]
        target_name = id_data["name"]

        session_id = user_info.scene.id
        session_type = user_info.scene.type

        async with session:
            sub_manager = KillmailSubscriptionManager(session)

            subscriptions = await sub_manager.get_session_subscriptions(
                platform=platform, bot_id=user_info.self_id, session_id=session_id, session_type=session_type
            )

            removed = False
            for cond_sub in subscriptions["condition_subscriptions"]:
                if cond_sub["target_type"] == category_type_list[result.type] and cond_sub["target_id"] == target_id:
                    sub_removed = await sub_manager.remove_subscription(
                        subscription_id=cond_sub["id"], sub_type="condition"
                    )
                    if sub_removed:
                        removed = True

        if removed:
            logger.info(f"""订阅已移除
[{platform}]{user_info.self_id}
[{SceneType(user_info.scene.type).name}]{session_id}
[{category_type_list[result.type]}]{target_name}({target_id})""")
            await sub.finish(f"""订阅已移除
[{platform}]{user_info.self_id}
[{SceneType(user_info.scene.type).name}]{session_id}
[{category_type_list[result.type]}]{target_name}({target_id})""")
        else:
            await sub.finish("没有找到符合条件的订阅")


@sub_high.handle()
async def _handle_sub_high(
    result: Arparma,
    user_info: Uninfo,
    session: AsyncSession,
):
    if user_info.member and user_info.member.role.id not in ["CHANNEL_ADMINISTRATOR", "ADMINISTRATOR", "OWNER"]:
        await sub.finish("你还不是群管理员，无法使用此功能")

    platform = user_info.adapter
    session_id = user_info.scene.id
    session_type = user_info.scene.type

    async with session:
        sub_manager = KillmailSubscriptionManager(session)
        if result.options.get("remove"):
            subscriptions = await sub_manager.get_session_subscriptions(
                platform=platform, bot_id=user_info.self_id, session_id=session_id, session_type=session_type
            )

            if subscriptions["high_value_subscription"]:
                removed = await sub_manager.remove_subscription(
                    subscription_id=subscriptions["high_value_subscription"]["id"], sub_type="high_value"
                )

                if removed:
                    logger.info(f"""高价值订阅已移除
[{platform}]{user_info.self_id}
[{SceneType(user_info.scene.type).name}]{session_id}""")
                    await sub_high.finish(f"""高价值订阅已移除
[{platform}]{user_info.self_id}
[{SceneType(user_info.scene.type).name}]{session_id}""")
                else:
                    await sub_high.finish("移除高价值订阅失败")
            else:
                await sub_high.finish("没有找到高价值订阅")
        else:
            min_value = result.value
            min_value = min_value if min_value >= 8_000_000_000 else 18_000_000_000

            added = await sub_manager.add_subscription(
                platform=platform,
                bot_id=user_info.self_id,
                session_id=session_id,
                session_type=session_type,
                sub_type="high_value",
                min_value=min_value,
            )

            if added:
                logger.info(f"""高价值订阅已添加
[{platform}]{user_info.self_id}
[{SceneType(user_info.scene.type).name}]{session_id}
[最低价值]{min_value}""")
                await sub_high.finish(f"""高价值订阅已添加
[{platform}]{user_info.self_id}
[{SceneType(user_info.scene.type).name}]{session_id}
[最低价值]{min_value}""")
            else:
                await sub_high.finish("添加高价值订阅失败")


@sub.assign("list")
async def _handle_sub_list(
    user_info: Uninfo,
    session: AsyncSession,
):
    sub_manager = KillmailSubscriptionManager(session)
    data = await sub_manager.get_session_subscriptions(
        platform=user_info.adapter,
        bot_id=user_info.self_id,
        session_id=user_info.scene.id,
        session_type=user_info.scene.type,
    )

    result_parts = ["当前订阅列表："]

    hv_sub = data["high_value_subscription"]
    if hv_sub:
        min_value = hv_sub["min_value"]
        value_str = (
            f"{min_value / 1_000_000_000:.2f}B" if min_value >= 1_000_000_000 else f"{min_value / 1_000_000:.2f}M"
        )
        result_parts.append(f"● 高价值击杀订阅 (最低{value_str})")

    if data["condition_subscriptions"]:
        result_parts.append("● 条件订阅：")

        targets = {}
        for cond in data["condition_subscriptions"]:
            key = (cond["target_type"], cond["target_id"])
            if key not in targets:
                targets[key] = {
                    "name": cond["target_name"],
                    "type": cond["target_type"],
                    "attack": None,
                    "victim": None,
                }

            value = cond["min_value"]
            value_str = f"{value / 1_000_000_000:.2f}B" if value >= 1_000_000_000 else f"{value / 1_000_000:.2f}M"

            if cond["is_victim"]:
                targets[key]["victim"] = value_str
            else:
                targets[key]["attack"] = value_str

        for i, (_, target) in enumerate(targets.items(), 1):
            type_name = {
                "character": "角色",
                "corporation": "军团",
                "alliance": "联盟",
                "system": "星系",
                "inventory_type": "舰船",
            }.get(target["type"], target["type"])

            attack_str = f"击杀 {target['attack']}" if target["attack"] else "击杀 关闭"
            victim_str = f"损失 {target['victim']}" if target["victim"] else "损失 关闭"

            result_parts.append(f"  {i}. [{type_name}] {target['name']}")
            result_parts.append(f"     {attack_str} | {victim_str}")

    if len(result_parts) == 1:
        result_parts.append("暂无订阅")

    result_text = "\n".join(result_parts)
    await sub.finish(result_text)
