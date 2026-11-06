from nonebot.adapters.onebot.v11.exception import ActionFailed
from push_test.core.db.models.push import PushBot, PushDelivery
from push_test.core.helper.group_leave import disable_group_subscriptions
from push_test.core.helper.push.errors import classify_error
from push_test.core.helper.push.store import key
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def send_failure(tail, content="hello"):
    message = (
        "invoke failed, wrapperSession.getMsgService().sendMsg, [ '0', { chatType: 2, peerUid: '1', guildId: '' }, "
        f"[ {{ textElement: {{ content: '{content}' }} }} ], Map(1) {{}} ], {tail}"
    )
    return ActionFailed(status="failed", retcode=1200, data=None, message=message, wording=message, echo="1")


@pytest.mark.parametrize("tail", [
    "{ result: 110, errMsg: '发送失败，你已被移出该群，请重新加群。' }",
    "{ result: 16, errMsg: '发送失败，请先添加对方为好友' }",
])
def test_removed_from_target_is_permanent(tail):
    assert classify_error(send_failure(tail)) == ("dead", 0)


@pytest.mark.parametrize("error", [
    send_failure("{ result: -1, errMsg: 'rich media transfer failed' }"),
    ActionFailed(status="failed", retcode=1200, data=None, message="发送伪造合并转发消息失败 (res_id: abc)"),
    # The message text is echoed before the result code and must not be mistaken for it.
    send_failure("{ result: -1, errMsg: 'x' }", content="{ result: 110, errMsg: 'x' }"),
])
def test_other_send_failures_keep_retrying(error):
    assert classify_error(error)[0] == "retry"


async def test_dead_delivery_does_not_block_the_bot(store):
    delivery_id = await store.enqueue(
        event_id="eve_status:1", kind="eve_status", platform="OneBot V11", bot_id="bot", session_id="gone",
        session_type="GROUP", account_key="GROUP:gone", payload={"text": "x"}, cost=1,
    )
    rows = await store.claim([key("OneBot V11", "bot")])
    attempt = await store.begin_send(rows)
    state, _ = classify_error(send_failure("{ result: 110, errMsg: 'x' }"))
    await store.finish(rows, state, "x", retry_delay=900, attempt_id=attempt)
    async with store.sessions() as session:
        assert (await session.get(PushDelivery, delivery_id)).state == "dead"
        bot = await session.get(PushBot, key("OneBot V11", "bot"))
    assert bot.available_at < rows[0].created_at + 60


class Base(DeclarativeBase):
    pass


class Sub(Base):
    __tablename__ = "sub"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[str]
    session_id: Mapped[str]
    session_type: Mapped[str]
    is_enabled: Mapped[bool] = mapped_column(default=True)


async def test_group_leave_disables_only_that_bots_group_subscriptions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'subs.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        session.add_all([
            Sub(id=1, bot_id="123", session_id="456", session_type="GROUP"),
            Sub(id=2, bot_id="123", session_id="456", session_type="1"),
            Sub(id=3, bot_id="123", session_id="456", session_type="PRIVATE"),
            Sub(id=4, bot_id="123", session_id="456", session_type="0"),
            Sub(id=5, bot_id="123", session_id="456", session_type="private"),
            Sub(id=6, bot_id="999", session_id="456", session_type="GROUP"),
            Sub(id=7, bot_id="123", session_id="789", session_type="GROUP"),
        ])

    parameters = []
    event.listen(engine.sync_engine, "before_cursor_execute",
                 lambda conn, cur, stmt, params, ctx, many: parameters.append(params))
    async with sessions() as session, session.begin():
        # OneBot gives an int self_id; the columns are strings and PostgreSQL rejects the comparison.
        disabled = await disable_group_subscriptions(session, [Sub], 123, 456)
    assert disabled == {"sub": 2}
    assert "123" in parameters[0]
    assert 123 not in parameters[0]

    async with sessions() as session:
        enabled = (await session.scalars(select(Sub.id).where(Sub.is_enabled.is_(True)))).all()
    assert sorted(enabled) == [3, 4, 5, 6, 7]
    await engine.dispose()
