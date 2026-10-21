import asyncio
import random
import re
import time

import httpx
from nonebot import get_bots, logger
from nonebot.exception import ActionFailed
from nonebot_plugin_alconna import CustomNode, Target, UniMessage, get_bot
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...config import plugin_config
from ...db.models.push import PushEvent
from ..billing import billing, key_from_session_fields
from ..billing.rules import BillingRules
from .store import PushStore, key


def classify_error(error):
    """Only retry when rejection/non-delivery is known. Unknown transport results need review."""
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "retry", 0
    if isinstance(error, ActionFailed):
        code = getattr(error, "code", None) or getattr(error, "status_code", None)
        data = getattr(error, "data", None) or getattr(error, "info", None)
        if isinstance(data, dict):
            code = data.get("error_code", data.get("retcode", code))
        description = str(getattr(error, "description", "") or "").lower()
        match = re.search(r"retry after (\d+)", description)
        if match:
            return "retry", max(5, int(match.group(1)))
        if code == 429:
            parameters = data.get("parameters", {}) if isinstance(data, dict) else {}
            return "retry", max(5, int(parameters.get("retry_after", 60)))
        if code in (400, 401, 403, 404) or getattr(error, "retcode", None) in (100, 1400, 1401, 1403, 1404):
            return "dead", 0
        if code in (100, 1400, 1401, 1403, 1404) or description.startswith(("forbidden:", "bad request:")):
            return "dead", 0
        return "retry", 0
    return "uncertain", 0


class PushService:
    def __init__(self):
        self.store = PushStore(
            get_session, plugin_config.billing_migrate_credit, plugin_config.push_max_attempts,
            plugin_config.push_lease_seconds, plugin_config.push_bot_interval,
        )
        self.tasks = []
        self.running = False

    async def enqueue(self, *, event_id, kind, platform, bot_id, session_id, session_type,
                      text, image=None, priority=0, metadata=None, count=1):
        session_type = {0: "PRIVATE", 1: "GROUP"}.get(session_type, str(session_type).upper())
        cost = BillingRules.calc_charge(kind, count=count) if billing.should_bill(kind) else 0
        return await self.store.enqueue(
            event_id=event_id, kind=kind, platform=platform, bot_id=bot_id,
            session_id=session_id, session_type=session_type,
            account_key=key_from_session_fields(platform, str(session_id), session_type),
            payload={"text": text, **(metadata or {})}, cost=cost, image=image, priority=priority,
            delay=plugin_config.push_merge_seconds if kind == "killmail" and not priority else 0,
            ttl=plugin_config.push_message_ttl,
        )

    async def start(self):
        if self.running:
            return
        # Fail startup clearly when migrations have not been applied.
        async with get_session() as session:
            await session.execute(select(PushEvent.id).limit(1))
        self.running = True
        self.tasks = [asyncio.create_task(self._events()) for _ in range(plugin_config.push_prepare_workers)]
        self.tasks += [asyncio.create_task(self._sender()) for _ in range(plugin_config.push_send_workers)]
        self.tasks.append(asyncio.create_task(self._maintenance()))
        logger.info("持久化推送服务已启动")

    async def stop(self):
        self.running = False
        if self.tasks:
            _, pending = await asyncio.wait(self.tasks, timeout=plugin_config.push_send_timeout + 5)
            for task in pending:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def _heartbeat(self, event):
        while True:
            await asyncio.sleep(self.store.lease_seconds / 3)
            async with get_session() as session, session.begin():
                row = await session.get(PushEvent, event.id, with_for_update=True)
                if row.token != event.token or row.state != "processing":
                    return
                row.lease_until = time.time() + self.store.lease_seconds

    async def _events(self):
        while self.running:
            heartbeat = None
            try:
                event = await self.store.claim_event()
                if event is None:
                    await asyncio.sleep(1)
                    continue
                heartbeat = asyncio.create_task(self._heartbeat(event))
                try:
                    await self._process_event(event)
                except Exception as error:
                    logger.exception(f"推送事件处理失败 {event.id}")
                    await self.store.finish_event(event, error)
                else:
                    await self.store.finish_event(event)
            except Exception:
                logger.exception("推送事件 Worker 异常")
                await asyncio.sleep(3)
            finally:
                if heartbeat:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)

    async def _process_event(self, event):
        if event.kind == "killmail":
            from ..zkb.killmail import KillmailHelper

            async with get_session() as session:
                await KillmailHelper(session).check(event.payload)
        elif event.kind == "structure":
            from ....structure_notifications.tasks import dispatch_event

            await dispatch_event(event)
        elif event.kind == "eve_status":
            from ..status import eve_server_status

            await eve_server_status.notify_status_change(event.id, event.payload["text"])
        elif event.kind == "push_receipt":
            from ...utils.common.cache import cache

            if event.payload.get("message_id") and event.payload.get("url"):
                await cache.set(f"send_msg_id:{event.payload['message_id']}", event.payload["url"])
        else:
            raise ValueError(f"Unknown push event kind {event.kind}")

    async def _sender(self):
        while self.running:
            try:
                online = [key(bot.adapter.get_name(), str(bot.self_id)) for bot in get_bots().values()]
                rows = await self.store.claim(online)
                if not rows:
                    await asyncio.sleep(1)
                    continue
                await self._deliver(rows)
            except Exception:
                # If result persistence failed, lease recovery marks sending rows uncertain.
                logger.exception("推送发送 Worker 异常，任务保留在数据库")
                await asyncio.sleep(3)

    async def _deliver(self, rows):
        first = rows[0]
        try:
            bot = await get_bot(adapter=first.platform, bot_id=first.bot_id)
        except Exception as error:
            await self.store.finish(rows, "retry", str(error), retry_delay=30)
            return
        try:
            messages = []
            for row in rows:
                message = UniMessage.text(row.payload["text"])
                if row.artifact_id:
                    message += UniMessage.image(raw=await self.store.artifact(row.artifact_id))
                if row.payload.get("url"):
                    message += UniMessage.text(row.payload["url"])
                messages.append(message)
            if len(messages) > 1:
                message = UniMessage.reference(*[
                    CustomNode(uid=first.bot_id, name="小霸王Bot", content=item) for item in messages
                ])
            else:
                message = messages[0]
            target = Target(id=first.session_id, private=first.session_type == "PRIVATE",
                            channel=first.session_type in ("GROUP", "CHANNEL"))
        except Exception as error:
            await self.store.finish(rows, "dead", f"消息构造失败: {error}")
            return
        attempt_id = await self.store.begin_send(rows)
        if not attempt_id:
            return
        try:
            receipt = await asyncio.wait_for(message.send(bot=bot, target=target), plugin_config.push_send_timeout)
        except Exception as error:
            state, delay = classify_error(error)
            delay = delay or min(900, 5 * 3 ** min(max(r.attempts for r in rows), 6)) * random.uniform(0.8, 1.2)
            await self.store.finish(rows, state, repr(error), retry_delay=delay, attempt_id=attempt_id)
            logger.warning(f"推送 {first.batch_id}: {state}: {error}")
            return
        # Receipt serialization is post-send work: never turn it into a send retry.
        from ...utils.common.command_record import get_msg_id

        try:
            message_id = str(get_msg_id(receipt))
        except Exception:
            message_id = ""
            logger.exception("平台已确认，但无法提取消息 ID")
        await self.store.finish(rows, "sent", receipt=message_id, attempt_id=attempt_id)
        for row in rows:
            await billing._invalidate_balance(row.account_key)

    async def _maintenance(self):
        ticks = 0
        while self.running:
            try:
                await self.store.recover()
                if ticks % 12 == 0:
                    summary = await self.store.summary()
                    logger.info(f"推送队列状态: {summary}")
                ticks += 1
            except Exception:
                logger.exception("推送队列恢复任务失败")
            await asyncio.sleep(5)


push_service = PushService()
