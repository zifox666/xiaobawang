from datetime import datetime, timedelta, timezone
import time

from push_test.core.db.models.credit import CreditAccount
from push_test.core.db.models.push import PushDelivery
from push_test.core.helper.push.store import key
from push_test.core.helper.status_debounce import (
    ESI_FAILURE_CONFIRM_POLLS,
    OFFLINE_CONFIRM_POLLS,
    ONLINE_CONFIRM_POLLS,
    StatusDebouncer,
)
from sqlalchemy import update

OUTSIDE_DT = datetime(2026, 11, 5, 20, 0, tzinfo=timezone.utc)
AT_DT = datetime(2026, 11, 5, 11, 1, tzinfo=timezone.utc)


def confirmed(debouncer, count, online, **kwargs):
    return [debouncer.observe(online, **kwargs) for _ in range(count)]


def test_esi_failures_interrupted_by_success_never_confirm_offline():
    debouncer = StatusDebouncer()
    results = []
    for _ in range(100):
        results += confirmed(debouncer, ESI_FAILURE_CONFIRM_POLLS - 1, False, esi_failure=True, when=OUTSIDE_DT)
        results += confirmed(debouncer, 1, True)
    assert False not in results


def test_sustained_esi_failure_outside_dt_confirms_offline_late():
    results = confirmed(StatusDebouncer(), ESI_FAILURE_CONFIRM_POLLS, False, esi_failure=True, when=OUTSIDE_DT)
    assert results == [None] * (ESI_FAILURE_CONFIRM_POLLS - 1) + [False]


def test_esi_failure_during_dt_confirms_offline_quickly():
    results = confirmed(StatusDebouncer(), OFFLINE_CONFIRM_POLLS, False, esi_failure=True, when=AT_DT)
    assert results == [None] * (OFFLINE_CONFIRM_POLLS - 1) + [False]


def test_low_player_count_confirms_offline_outside_dt():
    results = confirmed(StatusDebouncer(), OFFLINE_CONFIRM_POLLS, False, when=OUTSIDE_DT)
    assert results[-1] is False


def test_online_needs_consecutive_successes():
    debouncer = StatusDebouncer()
    assert confirmed(debouncer, ONLINE_CONFIRM_POLLS, True)[-1] is True
    assert debouncer.observe(False, esi_failure=True, when=OUTSIDE_DT) is None


async def enqueue_status(store, event, target="group", kind="eve_status"):
    return await store.enqueue(
        event_id=event, kind=kind, platform="OneBot V11", bot_id="bot", session_id=target,
        session_type="GROUP", account_key="GROUP:" + target, payload={"text": event, "kill_id": "1"}, cost=1,
    )


async def age(store, delivery_id, seconds):
    async with store.sessions() as session, session.begin():
        await session.execute(update(PushDelivery).where(PushDelivery.id == delivery_id).values(
            created_at=time.time() - seconds))


async def claim(store):
    return await store.claim([key("OneBot V11", "bot")])


async def read(store, model, id):
    async with store.sessions() as session:
        return await session.get(model, id)


async def test_only_newest_status_is_delivered_per_target(store):
    ids = [await enqueue_status(store, f"eve_status:{i}") for i in range(3)]
    for i, delivery_id in enumerate(ids):
        await age(store, delivery_id, 300 - i)
    other = await enqueue_status(store, "eve_status:0", target="other")

    delivered = []
    for _ in range(4):
        rows = await claim(store)
        delivered += [row.id for row in rows]
        for row in rows:
            await store.finish([row], "sent", attempt_id=None)

    assert sorted(delivered) == sorted([ids[2], other])
    assert (await read(store, PushDelivery, ids[0])).state == "cancelled"
    assert (await read(store, PushDelivery, ids[1])).state == "cancelled"


async def test_outdated_status_is_expired_without_sending(store):
    delivery_id = await enqueue_status(store, "eve_status:old")
    await age(store, delivery_id, store.status_ttl + 1)
    assert await claim(store) == []
    assert (await read(store, PushDelivery, delivery_id)).state == "expired"


async def test_superseded_status_releases_credit_reservation(store):
    older = await enqueue_status(store, "eve_status:1")
    await age(store, older, 60)
    rows = await claim(store)
    assert [row.id for row in rows] == [older]
    await store.finish(rows, "retry", retry_delay=0)
    assert (await read(store, CreditAccount, "GROUP:group")).frozen == 1

    newest = await enqueue_status(store, "eve_status:2")
    assert await claim(store) == []  # The older row came up first and was dropped.
    assert (await read(store, PushDelivery, older)).state == "cancelled"
    assert (await read(store, CreditAccount, "GROUP:group")).frozen == 0
    rows = await claim(store)
    assert [row.id for row in rows] == [newest]
    account = await read(store, CreditAccount, "GROUP:group")
    assert (account.balance, account.frozen) == (99, 1)


async def test_other_kinds_are_not_superseded(store):
    first = await enqueue_status(store, "killmail:1", kind="structure")
    await age(store, first, timedelta(days=0.5).total_seconds())
    await enqueue_status(store, "killmail:2", kind="structure")
    rows = await claim(store)
    assert [row.id for row in rows] == [first]
