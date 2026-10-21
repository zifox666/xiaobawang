import time

from push_test.core.db.models.credit import CreditAccount, CreditTransaction
from push_test.core.db.models.push import PushArtifact, PushAttempt, PushBot, PushCursor, PushDelivery, PushEvent
from push_test.core.helper.push.store import key
import pytest
from sqlalchemy import func, select


async def enqueue(store, event="killmail:1", target="group", **kwargs):
    return await store.enqueue(
        event_id=event, kind="killmail", platform="OneBot V11", bot_id="bot", session_id=target,
        session_type="GROUP", account_key="GROUP:" + target, payload={"text": "test", "kill_id": "1"},
        cost=5, image=b"image", **kwargs,
    )


async def claim(store):
    return await store.claim([key("OneBot V11", "bot")])


async def read(store, model, id):
    async with store.sessions() as session:
        return await session.get(model, id)


async def test_event_and_cursor_commit_together_and_deduplicate(store):
    await store.ingest("killmail:1", "killmail", {"killmail_id": 1}, ("r2z2", {"sequence": 2}))
    await store.ingest("killmail:1", "killmail", {"killmail_id": 1}, ("r2z2", {"sequence": 1}))
    assert (await store.cursor("r2z2"))["sequence"] == 2
    event = await store.claim_event()
    assert event.id == "killmail:1"
    assert await store.claim_event() is None
    await store.finish_event(event, "render failed")
    assert (await read(store, PushEvent, event.id)).state == "retry"


async def test_skip_cursor_advances_and_never_regresses(store):
    await store.skip_cursor("r2z2", {"sequence": 5})
    await store.skip_cursor("r2z2", {"sequence": 3})
    assert (await store.cursor("r2z2"))["sequence"] == 5


async def test_success_settles_once_and_records_receipt_atomically(store):
    id = await enqueue(store)
    assert await enqueue(store) == id
    rows = await claim(store)
    assert len(rows) == 1
    account = await read(store, CreditAccount, "GROUP:group")
    assert (account.balance, account.frozen) == (95, 5)
    attempt = await store.begin_send(rows)
    await store.finish(rows, "sent", receipt="123", attempt_id=attempt)
    await store.finish(rows, "sent", receipt="123", attempt_id=attempt)
    account = await read(store, CreditAccount, "GROUP:group")
    assert (account.balance, account.frozen, account.total_consumed) == (95, 0, 5)
    assert (await read(store, PushDelivery, id)).state == "sent"
    assert (await read(store, PushEvent, "receipt:" + id)).payload["message_id"] == "123"
    async with store.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(CreditTransaction)) == 1
        assert await session.scalar(select(func.count()).select_from(PushArtifact)) == 1


async def test_retry_retains_batch_and_does_not_double_reserve(store):
    ids = [await enqueue(store, f"killmail:{i}") for i in range(3)]
    rows = await claim(store)
    attempt = await store.begin_send(rows)
    await store.finish(rows, "retry", "limited", retry_delay=0, attempt_id=attempt)
    await enqueue(store, "killmail:new")
    again = await claim(store)
    assert {r.id for r in again} == set(ids)
    assert {r.batch_id for r in again} == {rows[0].batch_id}
    account = await read(store, CreditAccount, "GROUP:group")
    assert (account.balance, account.frozen) == (85, 15)


async def test_crash_before_send_retries_but_during_send_is_uncertain(store):
    id = await enqueue(store)
    rows = await claim(store)
    async with store.sessions() as session, session.begin():
        (await session.get(PushDelivery, id)).lease_until = 0
    await store.recover()
    assert (await read(store, PushDelivery, id)).state == "retry"
    assert await store.begin_send(rows) is None
    async with store.sessions() as session, session.begin():
        (await session.get(PushBot, rows[0].bot_key)).lease_until = 0
    rows = await claim(store)
    attempt = await store.begin_send(rows)
    async with store.sessions() as session, session.begin():
        (await session.get(PushDelivery, id)).lease_until = 0
    await store.recover()
    assert (await read(store, PushDelivery, id)).state == "uncertain"
    assert (await read(store, PushAttempt, attempt)).state == "uncertain"
    assert await claim(store) == []
    with pytest.raises(ValueError, match="核实"):
        await store.action(id, "retry")


async def test_permanent_failure_releases_and_success_cannot_be_retried(store):
    id = await enqueue(store)
    rows = await claim(store)
    attempt = await store.begin_send(rows)
    await store.finish(rows, "dead", "forbidden", attempt_id=attempt)
    account = await read(store, CreditAccount, "GROUP:group")
    assert (account.balance, account.frozen) == (100, 0)
    await store.action(id, "retry")
    async with store.sessions() as session, session.begin():
        (await session.get(PushBot, rows[0].bot_key)).available_at = 0
    rows = await claim(store)
    attempt = await store.begin_send(rows)
    await store.finish(rows, "sent", attempt_id=attempt)
    with pytest.raises(ValueError, match="不可操作"):
        await store.action(id, "retry")


async def test_offline_and_paused_bots_do_not_consume_attempts(store):
    id = await enqueue(store)
    assert await store.claim([]) == []
    async with store.sessions() as session, session.begin():
        (await session.get(PushBot, key("OneBot V11", "bot"))).paused = True
    assert await claim(store) == []
    assert (await read(store, PushDelivery, id)).attempts == 0


async def test_batch_splits_without_loss(store):
    for i in range(85):
        await enqueue(store, f"killmail:{i}")
    counts = []
    while rows := await claim(store):
        counts.append(len(rows))
        attempt = await store.begin_send(rows)
        await store.finish(rows, "sent", attempt_id=attempt)
        # Fund the account; batches intentionally wait instead of sending on credit.
        async with store.sessions() as session, session.begin():
            account = await session.get(CreditAccount, "GROUP:group")
            account.balance = 1000
            for row in await session.scalars(select(PushDelivery).where(PushDelivery.state == "waiting_balance")):
                row.available_at = 0
    assert sum(counts) == 85
    assert max(counts) <= 30


async def test_uncertain_expires_and_releases_credit(store):
    id = await enqueue(store)
    rows = await claim(store)
    attempt = await store.begin_send(rows)
    await store.finish(rows, "uncertain", "timeout", attempt_id=attempt)
    async with store.sessions() as session, session.begin():
        (await session.get(PushDelivery, id)).available_at = time.time() - 86401
    await store.recover()
    account = await read(store, CreditAccount, "GROUP:group")
    assert (account.balance, account.frozen) == (100, 0)
    assert (await read(store, PushDelivery, id)).state == "expired"


async def test_status_event_is_transactional_and_not_duplicated(store):
    await store.status_change(True, {"text": "online"})
    assert await store.claim_event() is None
    await store.status_change(False, {"text": "offline"})
    await store.status_change(False, {"text": "offline"})
    assert (await store.claim_event()).payload["text"] == "offline"
    assert await store.claim_event() is None
    assert (await read(store, PushCursor, "eve_status")).value["online"] is False
