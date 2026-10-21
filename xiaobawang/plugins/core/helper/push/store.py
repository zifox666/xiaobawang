"""Transactional inbox, delivery queue and credit settlement."""

from datetime import datetime
import hashlib
import json
import time
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ...db.models.credit import CreditAccount, CreditTransaction
from ...db.models.push import PushArtifact, PushAttempt, PushBot, PushCursor, PushDelivery, PushEvent
from ...db.models.record import KillmailPushRecord

READY = ("pending", "retry", "waiting_balance")
TERMINAL = ("sent", "dead", "expired", "cancelled")


def key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


async def insert_once(session, model, values):
    dialect = session.get_bind(mapper=model).dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    await session.execute(insert(model).values(**values).on_conflict_do_nothing())


class PushStore:
    def __init__(self, sessions, initial_credit=0, max_attempts=8, lease_seconds=120, bot_interval=5):
        self.sessions = sessions
        self.initial_credit = initial_credit
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self.bot_interval = bot_interval

    async def ingest(self, event_id, kind, payload, cursor=None):
        async with self.sessions() as session, session.begin():
            await insert_once(session, PushEvent, {"id": event_id, "kind": kind, "payload": payload})
            if cursor:
                await insert_once(session, PushCursor, {"id": cursor[0], "value": {}})
                row = await session.get(PushCursor, cursor[0], with_for_update=True)
                # Concurrent collectors must never move a sequence backwards.
                if cursor[1].get("sequence", 0) >= row.value.get("sequence", 0):
                    row.value = cursor[1]

    async def cursor(self, name):
        async with self.sessions() as session:
            row = await session.get(PushCursor, name)
            return row.value if row else None

    async def skip_cursor(self, name, value):
        """Advance a source cursor past an event that can never be persisted."""
        async with self.sessions() as session, session.begin():
            await insert_once(session, PushCursor, {"id": name, "value": {}})
            row = await session.get(PushCursor, name, with_for_update=True)
            # Concurrent collectors must never move a sequence backwards.
            if value.get("sequence", 0) >= row.value.get("sequence", 0):
                row.value = value

    async def status_change(self, online, payload):
        async with self.sessions() as session, session.begin():
            await insert_once(session, PushCursor, {"id": "eve_status", "value": {"online": online}})
            cursor = await session.get(PushCursor, "eve_status", with_for_update=True)
            if cursor.value["online"] == online:
                return
            event_id = "eve_status:" + uuid4().hex
            await insert_once(session, PushEvent, {"id": event_id, "kind": "eve_status", "payload": payload})
            cursor.value = {"online": online, "event_id": event_id}

    async def claim_event(self):
        now = time.time()
        async with self.sessions() as session, session.begin():
            row = await session.scalar(select(PushEvent).where(
                PushEvent.state.in_(("pending", "retry")), PushEvent.available_at <= now,
            ).order_by(PushEvent.available_at).limit(1).with_for_update(skip_locked=True))
            if row is None:
                return None
            row.state, row.token = "processing", uuid4().hex
            row.lease_until = now + self.lease_seconds
            row.attempts += 1
            await session.flush()
            session.expunge(row)
            return row

    async def finish_event(self, event, error=None):
        async with self.sessions() as session, session.begin():
            row = await session.get(PushEvent, event.id, with_for_update=True)
            if row.token != event.token or row.state != "processing":
                return
            row.state = "done" if error is None else ("dead" if row.attempts >= self.max_attempts else "retry")
            row.error = str(error or "")[:4000]
            row.available_at = time.time() + min(900, 5 * 3 ** min(row.attempts - 1, 6))

    async def enqueue(self, *, event_id, kind, platform, bot_id, session_id, session_type,
                      account_key, payload, cost=0, image=None, priority=0, delay=0, ttl=86400):
        session_type = str(session_type).upper()
        delivery_id = key(event_id, platform, str(bot_id), str(session_id), session_type, kind)
        bot_key = key(platform, str(bot_id))
        artifact_id = hashlib.sha256(image).hexdigest() if image else None
        async with self.sessions() as session, session.begin():
            if artifact_id:
                await insert_once(session, PushArtifact, {"id": artifact_id, "data": image})
            await insert_once(session, PushBot, {"id": bot_key, "platform": platform, "bot_id": str(bot_id)})
            await insert_once(session, PushDelivery, {
                "id": delivery_id, "event_id": event_id, "kind": kind, "bot_key": bot_key,
                "platform": platform, "bot_id": str(bot_id), "session_id": str(session_id),
                "session_type": session_type,
                "account_key": account_key, "payload": payload, "cost": cost, "artifact_id": artifact_id,
                "priority": priority, "available_at": time.time() + delay, "expires_at": time.time() + ttl,
            })
        return delivery_id

    async def claim(self, online_bots):
        """Claim one bot and a fixed batch. No network operation runs inside this transaction."""
        if not online_bots:
            return []
        now = time.time()
        async with self.sessions() as session, session.begin():
            has_work = select(PushDelivery.id).where(
                PushDelivery.bot_key == PushBot.id, PushDelivery.state.in_(READY),
                PushDelivery.available_at <= now,
            ).exists()
            bot = await session.scalar(select(PushBot).where(
                PushBot.id.in_(online_bots), PushBot.paused.is_(False), PushBot.available_at <= now,
                PushBot.lease_until <= now, has_work,
            ).order_by(PushBot.available_at).limit(1).with_for_update(skip_locked=True))
            if bot is None:
                return []
            first = await session.scalar(select(PushDelivery).where(
                PushDelivery.bot_key == bot.id, PushDelivery.state.in_(READY), PushDelivery.available_at <= now,
            ).order_by(PushDelivery.priority.desc(), PushDelivery.available_at, PushDelivery.created_at)
                .limit(1).with_for_update(skip_locked=True))
            if first is None:
                return []
            query = select(PushDelivery).where(PushDelivery.bot_key == bot.id, PushDelivery.state.in_(READY))
            if first.batch_id:
                query = query.where(PushDelivery.batch_id == first.batch_id)
            elif first.platform == "OneBot V11" and first.kind == "killmail" and first.priority == 0:
                query = query.where(
                    PushDelivery.session_id == first.session_id, PushDelivery.session_type == first.session_type,
                    PushDelivery.kind == first.kind, PushDelivery.batch_id == "", PushDelivery.priority == 0,
                    PushDelivery.available_at <= now,
                )
            else:
                query = query.where(PushDelivery.id == first.id)
            rows = list((await session.scalars(query.order_by(PushDelivery.created_at)
                                               .limit(30).with_for_update(skip_locked=True))).all())
            batch_id = first.batch_id or uuid4().hex
            selected = []
            for row in rows:
                if row.expires_at <= now:
                    await self._release(session, row)
                    row.state, row.completed_at = "expired", now
                    continue
                if row.cost and not row.reserved:
                    await insert_once(session, CreditAccount, {
                        "session_key": row.account_key, "platform": row.platform, "bot_id": row.bot_id,
                        "session_id": row.session_id, "session_type": row.session_type, "balance": self.initial_credit,
                    })
                    account = await session.get(CreditAccount, row.account_key, with_for_update=True)
                    if not account.is_active or account.balance < row.cost:
                        row.state, row.available_at = "waiting_balance", now + 60
                        continue
                    # balance is spendable; frozen holds the reservation separately.
                    account.balance -= row.cost
                    account.frozen += row.cost
                    row.reserved = True
                row.state, row.batch_id = "claimed", batch_id
                row.lease_until = now + self.lease_seconds
                selected.append(row)
            bot.available_at = now + self.bot_interval
            if selected:
                bot.token, bot.lease_until = batch_id, now + self.lease_seconds
            await session.flush()
            for row in selected:
                session.expunge(row)
            return selected

    async def begin_send(self, rows):
        async with self.sessions() as session, session.begin():
            bot = await session.get(PushBot, rows[0].bot_key, with_for_update=True)
            if bot.token != rows[0].batch_id or bot.lease_until <= time.time() or bot.paused:
                return None
            current = list((await session.scalars(select(PushDelivery).where(
                PushDelivery.id.in_([r.id for r in rows]), PushDelivery.state == "claimed",
                PushDelivery.batch_id == rows[0].batch_id,
            ).with_for_update())).all())
            if len(current) != len(rows):
                return None
            attempt_id = uuid4().hex
            session.add(PushAttempt(id=attempt_id, batch_id=rows[0].batch_id, delivery_ids=[r.id for r in rows]))
            for row in current:
                row.state = "sending"
                row.attempts += 1
            return attempt_id

    async def artifact(self, artifact_id):
        async with self.sessions() as session:
            row = await session.get(PushArtifact, artifact_id)
            if row is None:
                raise FileNotFoundError(f"Missing push artifact {artifact_id}")
            return row.data

    async def _release(self, session, row):
        if row.reserved:
            account = await session.get(CreditAccount, row.account_key, with_for_update=True)
            account.frozen -= row.cost
            account.balance += row.cost
            row.reserved = False

    async def finish(self, rows, state, error="", receipt="", retry_delay=15, attempt_id=None):
        now = time.time()
        async with self.sessions() as session, session.begin():
            bot = await session.get(PushBot, rows[0].bot_key, with_for_update=True)
            if bot.token != rows[0].batch_id:
                return
            current = list((await session.scalars(select(PushDelivery).where(
                PushDelivery.id.in_([r.id for r in rows]), PushDelivery.batch_id == rows[0].batch_id,
                PushDelivery.state.in_(("claimed", "sending")),
            ).order_by(PushDelivery.account_key, PushDelivery.id).with_for_update())).all())
            for row in current:
                outcome = "dead" if state == "retry" and row.attempts >= self.max_attempts else state
                row.state, row.error, row.receipt = outcome, error[:4000], receipt
                row.available_at = now + retry_delay
                if outcome == "sent":
                    await insert_once(session, PushEvent, {
                        "id": "receipt:" + row.id, "kind": "push_receipt",
                        "payload": {"message_id": receipt, "url": row.payload.get("url", ""),
                                 "kind": row.kind, "platform": row.platform, "bot_id": row.bot_id,
                                 "session_id": row.session_id, "session_type": row.session_type,
                                 "kill_id": row.payload.get("kill_id"), "delivery_id": row.id},
                    })
                    if row.reserved:
                        account = await session.get(CreditAccount, row.account_key, with_for_update=True)
                        account.frozen -= row.cost
                        account.total_consumed += row.cost
                        row.reserved = False
                        session.add(CreditTransaction(
                            session_key=row.account_key, txn_type="consume", amount=-row.cost,
                            balance_after=account.balance, ref_type=row.kind, ref_id=row.id,
                            description=f"推送 {row.event_id}"[:255], push_delivery_id=row.id,
                        ))
                    if row.kind == "killmail":
                        session.add(KillmailPushRecord(
                            bot_id=row.bot_id, platform=row.platform, session_id=row.session_id,
                            session_type=row.session_type, killmail_id=int(row.payload["kill_id"]), time=datetime.now(),
                        ))
                elif outcome in TERMINAL:
                    await self._release(session, row)
                if outcome in TERMINAL:
                    row.completed_at = now
            if attempt_id:
                attempt = await session.get(PushAttempt, attempt_id)
                attempt.state, attempt.error, attempt.receipt = state, error[:4000], receipt
                attempt.finished_at = now
            bot.lease_until = 0
            bot.available_at = now + max(self.bot_interval, retry_delay if state == "retry" else 0)

    async def recover(self):
        now = time.time()
        async with self.sessions() as session, session.begin():
            events = await session.scalars(select(PushEvent).where(
                PushEvent.state == "processing", PushEvent.lease_until < now,
            ).with_for_update(skip_locked=True).limit(100))
            for event in events:
                event.state = "retry" if event.attempts < self.max_attempts else "dead"
                event.error = "处理租约过期，等待恢复"
                event.token = ""
            rows = list((await session.scalars(select(PushDelivery).where(
                ((PushDelivery.state.in_(("claimed", "sending"))) & (PushDelivery.lease_until < now))
                | ((PushDelivery.state.in_(READY)) & (PushDelivery.expires_at < now))
                | ((PushDelivery.state == "uncertain") & (PushDelivery.available_at < now - 86400)),
            ).order_by(PushDelivery.account_key, PushDelivery.id).with_for_update(skip_locked=True).limit(100))).all())
            for row in rows:
                if row.state == "sending":
                    row.state, row.available_at = "uncertain", now
                    row.error = "发送中进程退出或租约过期；需核实后重试"
                    attempts = await session.scalars(select(PushAttempt).where(
                        PushAttempt.batch_id == row.batch_id, PushAttempt.state == "sending",
                    ))
                    for attempt in attempts:
                        attempt.state, attempt.finished_at, attempt.error = "uncertain", now, row.error
                elif row.state == "claimed":
                    row.state, row.available_at = "retry", now
                    row.batch_id = ""  # Fence the old claimant before it can issue a send.
                else:
                    was_uncertain = row.state == "uncertain"
                    row.state, row.completed_at = "expired", now
                    if was_uncertain:
                        row.error += "; 超过24小时未核实，释放预留，不自动补发"
                    await self._release(session, row)

    async def action(self, delivery_id, action, accept_duplicate_risk=False):
        if action not in ("retry", "cancel"):
            raise ValueError("仅支持 retry/cancel")
        async with self.sessions() as session, session.begin():
            row = await session.get(PushDelivery, delivery_id, with_for_update=True)
            if row is None:
                raise LookupError(delivery_id)
            if row.state not in ("dead", "uncertain", "expired", "waiting_balance", "retry", "pending"):
                raise ValueError("发送中或已成功的任务不可操作")
            if action == "retry" and (row.state == "uncertain" or "核实" in row.error) and not accept_duplicate_risk:
                raise ValueError("发送结果不确定，需核实并接受重复风险")
            await self._release(session, row)
            row.state = "pending" if action == "retry" else "cancelled"
            row.error = f"管理员执行 {action}; 原因: {row.error}"[:4000]
            row.available_at, row.expires_at = time.time(), time.time() + 86400
            row.attempts, row.batch_id = 0, ""
            row.completed_at = None if action == "retry" else time.time()

    async def summary(self):
        async with self.sessions() as session:
            counts = (await session.execute(
                select(PushDelivery.state, func.count()).group_by(PushDelivery.state))).all()
            oldest = await session.scalar(
                select(func.min(PushDelivery.created_at)).where(PushDelivery.state.in_(READY)))
            events = (await session.execute(select(PushEvent.state, func.count()).group_by(PushEvent.state))).all()
            return {"deliveries": dict(counts), "events": dict(events),
                    "oldest_pending_seconds": time.time() - oldest if oldest else 0}
