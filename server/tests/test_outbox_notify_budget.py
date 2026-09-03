"""[P5] One `NOTIFY outbox_event` per transaction, not one per staged row.

`database.stage_event` runs from a `before_flush` listener for every created,
dirty or deleted dynamic row, and each call issued its own
`session.execute(text("NOTIFY outbox_event;"))`. A 200-cell map push therefore sent
200 NOTIFY statements - an extra round trip per row, growing linearly with the
write, on the event fabric every other process depends on.


HOW THE "SAME DELIVERY" CLAIM WAS ESTABLISHED, AND WHAT IS NOT ESTABLISHED HERE
-------------------------------------------------------------------------------
Two separate claims, with different evidence:

1. "Exactly one NOTIFY statement is SENT per transaction that stages outbox rows,
   and at least one is sent in every such transaction." That is what these tests
   measure, directly, as a statement count at the cursor. See `notify_probe` for
   how a PostgreSQL-only branch is exercised on this suite's SQLite.

2. "The listener sees the same thing it saw before." That is NOT observed here and
   these tests do not claim it. It rests on two things. First, PostgreSQL's
   documented rule that duplicate notifications on the same channel with identical
   payloads inside one transaction are collapsed into a single delivered event - so
   the old 200 were already being delivered as 1. Second, the listener's own code:
   `chain_ingestion_worker.OutboxListener._wait_blocking` pops `connection.notifies`
   until empty and returns a bare `True`, so it cannot distinguish 1 from 200 even
   if PostgreSQL delivered them. What the worker needs in order to wake is AT LEAST
   ONE notify on the channel it listens to, and `test_the_channel_is_the_one_the_
   chain_worker_listens_on` plus the one-row case below pin exactly that.

   No PostgreSQL was run for this change. If that collapse rule were ever wrong,
   the symptom would be a chain worker that wakes on its 2 s poll fallback instead
   of instantly - not lost data, since the outbox row is committed either way.


WHY THE LATCH IS CLEARED SO AGGRESSIVELY
----------------------------------------
The failure directions are not symmetric. An extra NOTIFY costs one round trip. A
missing one means no wake-up, and every downstream write waits for the poll
timeout. So the latch is dropped at the end of ANY transaction scope, including a
SAVEPOINT's - which is a correctness requirement, not tidiness: PostgreSQL discards
a NOTIFY issued inside a subtransaction that rolls back, and
`enrichment_config._isolated_execute` wraps reference queries in savepoints.
`test_a_savepoint_rollback_does_not_swallow_the_wake_up` is that case.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database import models
from database.database import Base


TABLE = "p5notify_test_rows"  # prefixed so it cannot collide with the user's config


@pytest.fixture
def notify_db():
    """A session on its own engine, with the dialect NAME reported as postgresql.

    Why the name is faked rather than a real PostgreSQL used: the NOTIFY branch in
    `stage_event` is guarded on `bind.dialect.name`, so on this suite's SQLite it is
    dead code and the thing under test would never run. Faking the NAME - not the
    dialect - takes the production branch while SQLite still executes everything.

    It is safe HERE and would not be safe on the shared session: `crud`'s bulk
    upserts branch on the same attribute to pick `postgresql.insert` vs
    `sqlite.insert`. Nothing in this module goes through crud; these are plain ORM
    inserts, so the only statement the fake reroutes is the NOTIFY itself, and that
    one is rewritten below before it reaches SQLite.
    """
    config = {TABLE: {"business_key": "k",
                      "column_types": {"k": "string", "v": "string"}}}
    models.init_dynamic_models(config)

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)

    sent = []

    def _intercept(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("NOTIFY"):
            sent.append(statement.strip())
            return "SELECT 1", ()
        return statement, parameters

    event.listen(engine, "before_cursor_execute", _intercept, retval=True)

    real_name = engine.dialect.name
    engine.dialect.name = "postgresql"
    db = sessionmaker(bind=engine)()
    try:
        yield db, sent
    finally:
        engine.dialect.name = real_name
        db.close()
        event.remove(engine, "before_cursor_execute", _intercept)
        Base.metadata.drop_all(bind=engine)
        # Deliberately NOT popped from `models.DYNAMIC_TABLES`. `init_dynamic_models`
        # is idempotent via that registry but leaves its `Table` in `Base.metadata`;
        # unregistering would make the next parametrised run build a SECOND Table of
        # the same name and `create_all` would fail on the duplicate index. The engine
        # is per-fixture and in-memory, so nothing survives it anyway.


@contextmanager
def counting(sent):
    """Statements captured inside the block only."""
    start = len(sent)
    captured = []
    try:
        yield captured
    finally:
        captured.extend(sent[start:])


def _add(db, i):
    model = models.DYNAMIC_TABLES[TABLE]
    db.add(model(row_id=f"r{i}", business_key_val=f"k{i}", k=f"k{i}", v="1"))


def _outbox_count(db):
    return db.query(models.DatabaseOutbox).count()


# ---------------------------------------------------------------------------
# The budget
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rows", [1, 200])
def test_a_transaction_sends_exactly_one_notify_however_many_rows_it_stages(
        notify_db, rows):
    """Both halves in one property. `rows=1` is the case that must NOT be optimised
    away - a single-cell save has to wake the worker as before. `rows=200` is the
    map push that used to send 200."""
    db, sent = notify_db

    with counting(sent) as notifies:
        for i in range(rows):
            _add(db, i)
        db.commit()

    assert _outbox_count(db) == rows, "precondition: every row really staged an event"
    assert len(notifies) == 1, (
        f"{rows} staged rows must cost exactly one NOTIFY, not {len(notifies)}")
    assert notifies[0] == "NOTIFY outbox_event;"


def test_the_next_transaction_on_the_same_session_notifies_again(notify_db):
    """The latch is per transaction, not per session. If it leaked, every write
    after the first on a long-lived session would stage rows that nothing was told
    about, and the chain worker would only find them on its 2 s poll."""
    db, sent = notify_db

    with counting(sent) as first:
        _add(db, 1)
        db.commit()
    with counting(sent) as second:
        _add(db, 2)
        db.commit()
    with counting(sent) as third:
        for i in range(3, 60):
            _add(db, i)
        db.commit()

    assert [len(first), len(second), len(third)] == [1, 1, 1]


def test_one_transaction_with_several_flushes_still_sends_one_notify(notify_db):
    """The test that tells "per transaction" apart from "per flush".

    SQLAlchemy opens an internal SUBTRANSACTION around every `flush()`, so the
    obvious spelling of the latch-clearing hook fires once per flush and the budget
    quietly becomes one NOTIFY per flush. It is not a theoretical difference:
    `crud.apply_batch_updates` flushes more than once whenever the batch also purges
    (`replace_map`), and any caller may flush mid-transaction.

    Three flushes, one transaction, one notify.
    """
    db, sent = notify_db

    with counting(sent) as notifies:
        _add(db, 1)
        db.flush()
        _add(db, 2)
        db.flush()
        _add(db, 3)
        db.commit()

    assert _outbox_count(db) == 3
    assert len(notifies) == 1, (
        f"three flushes in one transaction cost {len(notifies)} NOTIFYs - the latch "
        f"is being cleared by the flush's own subtransaction")


def test_a_rollback_does_not_latch_the_transaction_after_it(notify_db):
    db, sent = notify_db

    with counting(sent) as during:
        _add(db, 1)
        db.flush()          # forces before_flush -> stage_event -> the latch is SET
        db.rollback()

    assert len(during) == 1, "precondition: the rolled-back transaction did notify"

    with counting(sent) as after:
        _add(db, 2)
        db.commit()

    assert _outbox_count(db) == 1
    assert len(after) == 1, "a rolled-back transaction must not silence the next one"


def test_a_savepoint_rollback_does_not_swallow_the_wake_up(notify_db):
    """PostgreSQL discards a NOTIFY issued inside a subtransaction that rolls back.
    A latch that survived the savepoint would leave the rows staged AFTER it with no
    notification at all - committed data nobody is told about, which is precisely
    the failure this system's real-time contract exists to prevent."""
    db, sent = notify_db

    with counting(sent) as notifies:
        nested = db.begin_nested()
        _add(db, 1)           # NOTIFY #1, issued inside the savepoint
        db.flush()
        nested.rollback()     # PostgreSQL would discard NOTIFY #1 here

        _add(db, 2)           # must produce a NOTIFY of its own
        db.commit()

    assert _outbox_count(db) == 1, "only the row staged outside the savepoint survives"
    assert len(notifies) >= 2, (
        "the row staged after the savepoint rolled back needs its own NOTIFY - the "
        "one issued inside the savepoint was discarded with it")


def test_a_transaction_that_stages_nothing_sends_nothing(notify_db):
    """Unchanged: the NOTIFY only ever came from `stage_event`, and nothing staged
    means nothing to wake anyone for."""
    db, sent = notify_db

    with counting(sent) as notifies:
        db.commit()
        db.query(models.DatabaseOutbox).count()
        db.commit()

    assert notifies == []


def test_only_graph_meta_changes_still_stage_and_notify_nothing(notify_db):
    """The existing `before_flush` exemption (a row dirtied only in its graph-sync
    columns publishes no outbox event) must keep costing no NOTIFY either."""
    db, sent = notify_db
    _add(db, 1)
    db.commit()
    before = _outbox_count(db)

    model = models.DYNAMIC_TABLES[TABLE]
    row = db.query(model).filter(model.row_id == "r1").one()
    with counting(sent) as notifies:
        row.is_graph_synced = True
        db.commit()

    assert _outbox_count(db) == before, "precondition: no outbox event was staged"
    assert notifies == []


# ---------------------------------------------------------------------------
# The other dialect, and the other end of the wire
# ---------------------------------------------------------------------------

def test_a_non_postgresql_session_sends_no_notify_at_all(db_session):
    """The suite's ordinary SQLite session. The guard is unchanged, so the whole
    branch stays dead there - and this is the test that would catch the latch being
    'simplified' into an unconditional emission."""
    from sql_budget import record_statements

    model = models.DYNAMIC_TABLES["raw_table_1"]
    with record_statements(db_session) as recorded:
        db_session.add(model(row_id="p5_sqlite", business_key_val="P5S",
                             EQP_ID="P5S"))
        db_session.commit()

    assert [c for c in recorded if c.sql.strip().upper().startswith("NOTIFY")] == []


def test_the_channel_is_the_one_the_chain_worker_listens_on(notify_db):
    """Emitter and listener, pinned against each other. A renamed channel on one
    side is silent: writes commit, nobody wakes, and the only symptom is latency."""
    import chain_ingestion_worker

    db, sent = notify_db
    with counting(sent) as notifies:
        _add(db, 1)
        db.commit()

    listener = chain_ingestion_worker.OutboxListener(db_session_factory=lambda: None)
    channel = listener._channel
    assert channel == "outbox_event"
    assert notifies == [f"NOTIFY {channel};"]


# ---------------------------------------------------------------------------
# GET /admin/chain/queue — the chain-queue instrument
# ---------------------------------------------------------------------------
# 🔴 THE POINT OF THIS ROUTE IS ONE NUMBER: how old the oldest waiting row is. Depth alone
# cannot tell "busy" from "stuck" - it rises and falls under load either way - so the tests
# below pin the age's three states (nothing waiting / something waiting / it grows) and the
# fact that the route writes nothing.

import datetime as _dt
import uuid

import main as _main
from database import models as _models
from sql_budget import record_statements


def _queue(client):
    r = client.get("/admin/chain/queue")
    assert r.status_code == 200, r.text
    return r.json()


def _stage(db, *, processed_chain, created_at=None, retry_count=0):
    row = _models.DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), event_type="TEST", table_name=TABLE,
        payload={}, status="PENDING", retry_count=retry_count,
        processed_chain=processed_chain)
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.commit()
    return row


def test_an_empty_queue_reports_no_age_rather_than_zero(client, db_session):
    """🔴 `null` IS NOT `0`, and on a screen the two are one careless `or` apart.

    `0` says "something arrived this instant"; `null` says "nothing is waiting". An
    instrument built to remove an ambiguity must not introduce one.
    """
    db_session.query(_models.DatabaseOutbox).delete()
    db_session.commit()

    body = _queue(client)
    assert body["waiting"] == 0
    assert body["oldest_waiting_seconds"] is None
    assert body["oldest_waiting_at"] is None


def test_the_age_is_measured_from_the_oldest_waiting_row(client, db_session):
    """And it is the OLDEST, not the newest and not the average.

    🔴 THE ROWS ARRIVE THE WAY THE SYSTEM MAKES THEM: `created_at` ascending together with
    `id`. That correlation is what lets the route find the oldest row by walking the
    partial index in `id` order instead of asking for `MIN(created_at)`, which has no
    index and would scan the table. It is not an assumption about luck - measured
    2026-09-03, all NINE places that construct a `DatabaseOutbox` leave `created_at` to
    `server_default=func.now()`, so nothing can back-date a row into the queue.

    The assertion below is the one that matters: the cheap answer must equal the expensive
    one. A route that read the LAST row, or let the newest win, fails it.
    """
    db_session.query(_models.DatabaseOutbox).delete()
    db_session.commit()

    now = _dt.datetime.now(_dt.timezone.utc)
    for age in (600, 30, 5):                       # oldest first, as arrivals happen
        _stage(db_session, processed_chain=False,
               created_at=now - _dt.timedelta(seconds=age))

    body = _queue(client)
    assert body["waiting"] == 3
    assert 550 <= body["oldest_waiting_seconds"] <= 700, (
        f"the age must come from the 600s row, not another one: {body}")

    # 🔴 THE CHEAP SCAN MUST AGREE WITH THE EXPENSIVE QUESTION. `MIN(created_at)` is what
    # the instrument MEANS; the index walk is only how it is afforded. Asserting the two
    # match on data the system can produce is what makes the shortcut checkable rather
    # than argued - and it is affordable here because the fixture is three rows.
    from sqlalchemy import func as _sqlf
    truth = (db_session.query(_sqlf.min(_models.DatabaseOutbox.created_at))
             .filter(_models.DatabaseOutbox.processed_chain == False).scalar())  # noqa: E712
    if truth.tzinfo is None:
        truth = truth.replace(tzinfo=_dt.timezone.utc)
    expected = (_dt.datetime.now(_dt.timezone.utc) - truth).total_seconds()
    assert abs(body["oldest_waiting_seconds"] - expected) < 5, (
        f"the id-ordered walk and MIN(created_at) disagree: "
        f"{body['oldest_waiting_seconds']} vs {expected}")


def test_a_row_the_chain_has_run_stops_counting(client, db_session):
    """The queue is what has NOT been processed. A finished row that kept counting would
    make the depth grow forever and the age never fall - the instrument would report a
    jam that had already cleared."""
    db_session.query(_models.DatabaseOutbox).delete()
    db_session.commit()

    now = _dt.datetime.now(_dt.timezone.utc)
    _stage(db_session, processed_chain=True, created_at=now - _dt.timedelta(seconds=9999))
    assert _queue(client)["waiting"] == 0
    assert _queue(client)["oldest_waiting_seconds"] is None

    _stage(db_session, processed_chain=False, created_at=now - _dt.timedelta(seconds=42))
    body = _queue(client)
    assert body["waiting"] == 1
    assert 30 <= body["oldest_waiting_seconds"] <= 120, (
        "the processed row's age leaked into the answer")


def test_retries_are_counted_among_the_waiting_only(client, db_session):
    """The name says the narrowing, and the narrowing is why it is affordable.

    Counting every row ever retried is a sequential scan of the whole table
    (EXPLAIN cost 272,812 against 6 for this one), so what is offered is the half that
    rides the partial index. A retried row that has since been processed is NOT here.
    """
    db_session.query(_models.DatabaseOutbox).delete()
    db_session.commit()

    _stage(db_session, processed_chain=False, retry_count=2)
    _stage(db_session, processed_chain=False, retry_count=0)
    _stage(db_session, processed_chain=True, retry_count=7)      # done: not our business

    body = _queue(client)
    assert body["waiting"] == 2
    assert body["retried_among_waiting"] == 1


def test_the_route_writes_nothing(client, db_session):
    """🔴 A DIAGNOSTIC THAT MUTATES IS NOT A DIAGNOSTIC. Asserted on the statements the
    session actually issues, not on the absence of an obvious `add()` - the route is read
    only by construction and this is what makes that claim checkable."""
    _stage(db_session, processed_chain=False)

    with record_statements(db_session) as recorded:
        _queue(client)

    verbs = {str(call.sql).strip().split()[0].upper() for call in recorded if call.sql}
    assert verbs <= {"SELECT", "BEGIN", "COMMIT", "ROLLBACK", "SET", "PRAGMA"}, (
        f"the queue route issued something other than reads: {sorted(verbs)}")
    assert any(v == "SELECT" for v in verbs), "it did not read anything; test is vacuous"


def test_what_it_did_not_measure_is_named_rather_than_left_to_look_like_zero(client):
    """An absent number reads as zero. Both of the two the brief asked for and this route
    refused to pay for are named in the body, with the reason."""
    body = _queue(client)
    assert set(body["not_measured"]) == {"retried_total", "processed_recently"}
    assert all(body["not_measured"].values()), "a reason that is empty explains nothing"
