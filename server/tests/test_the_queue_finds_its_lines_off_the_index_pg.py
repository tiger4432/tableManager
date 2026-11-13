# -*- coding: utf-8 -*-
"""The chain queue's lines off the index (owner 11-13, lead: D's R4 split - the old grouping of every waiting row took
0.86 s at 403k rows, 3.8-9.9 s at 1.6-1.9M). `queue_lines.waiting_lines` answers as the old grouping did - the same
lines in the same order, run, first id, first time and total - and `line_counts` the same counts through COUNTED_TO;
its time stays flat as the waiting rows grow under the same lines, where the old grouping's grows with them.

The one answer that differs, pinned: a line whose first row carries no run but whose later rows do (a transaction id
equal to a run id - a run id is 8 or 12 hex characters, a transaction a uuid4, «chain_<tx>» or «replay_<run>») is a run
line by the old max(run_id) and a live line by its first row now."""
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
from chain import queue_lines                                         # noqa: E402
from database import models                                           # noqa: E402

pytestmark = pytest.mark.pg

RETRO, WANTED, NOW = (event_constants.EVENT_RETROACTIVE_RUN, event_constants.EVENT_INDEX_WANTED,
                      event_constants.EVENT_SCHEDULER_RUN_NOW)
T0 = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)
MIXED = "r4dd"                                                        # its first row carries no run - the pinned line


def _old_lines(db, cap, chain_only=False):
    """The grouping of every waiting row the queue answered with up to 11-13 (main 0e7de32bd), as it was - the oracle."""
    from sqlalchemy import case as _case
    from sqlalchemy import func as _f
    from sqlalchemy import select as _select

    outbox = models.DatabaseOutbox
    waiting_only = (event_constants.chain_waiting(outbox) if chain_only
                    else (outbox.processed_chain == False,))  # noqa: E712
    line_key = event_constants.queue_line_key(outbox)
    pairs = (_select(line_key.label("key"), _f.max(outbox.run_id).label("run"), outbox.table_name,
                     outbox.event_type, _f.count().label("events"),
                     _f.sum(_f.coalesce(outbox.row_count, 1)).label("rows"),
                     _f.min(outbox.id).label("first_id"), _f.min(outbox.created_at).label("created_at"),
                     _f.max(outbox.retry_count).label("max_retry"),
                     _f.max(_case((outbox.status == "RETRYING", 1), else_=0)).label("retrying"))
             .where(*waiting_only).group_by(line_key, outbox.table_name, outbox.event_type).subquery())
    by_line = _select(pairs, _f.min(pairs.c.first_id).over(partition_by=pairs.c.key).label("line_first"),
                      _f.max(pairs.c.run).over(partition_by=pairs.c.key).label("line_run")).subquery()
    numbered = _select(by_line, _f.dense_rank().over(order_by=(by_line.c.line_run.isnot(None), by_line.c.line_first,
                                                               by_line.c.key)).label("line_no")).subquery()
    counted = _select(numbered, _f.max(numbered.c.line_no).over().label("lines_total")).subquery()
    folded = {}
    for pair in db.execute(_select(counted).where(counted.c.line_no <= cap)
                           .order_by(counted.c.line_no, counted.c.table_name, counted.c.event_type)):
        line = folded.setdefault(pair.key, {
            "key": pair.key, "run": None, "events": 0, "rows": 0, "first_id": pair.line_first,
            "created_at": None, "max_retry": 0, "retrying": False, "lines_total": pair.lines_total, "pairs": []})
        line["run"] = max(filter(None, (line["run"], pair.run)), default=None)
        line["events"] += pair.events
        line["rows"] += pair.rows or 0
        line["created_at"] = min(filter(None, (line["created_at"], pair.created_at)), default=None)
        line["max_retry"] = max(line["max_retry"], pair.max_retry or 0)
        line["retrying"] = line["retrying"] or bool(pair.retrying)
        line["pairs"].append((pair.table_name, pair.event_type))
    return list(folded.values())


def _old_detail(db, key):
    """The route's old reads of a line: its retroactive control rows and its newest retrying row's failure."""
    o = models.DatabaseOutbox
    narrow, line = event_constants.queue_line_rows(o, key)
    rows = db.query(o).filter(o.processed_chain == False, narrow, line).order_by(o.id).all()   # noqa: E712
    retro = [(r.id, r.payload) for r in rows if r.event_type == RETRO]
    failed = [r for r in rows if r.status == "RETRYING"]
    said = ({event_constants.LAST_FAILURE: failed[-1].payload.get(event_constants.LAST_FAILURE),
             event_constants.LAST_FAILURE_STAGE: failed[-1].payload.get(event_constants.LAST_FAILURE_STAGE)}
            if failed else None)
    return retro, said


def _row(i, tx=None, run=None, kind="UPDATE", table="t_a", count=None, status="PENDING", retry=0, payload=None):
    body = dict(payload or {})
    body.update({k: v for k, v in (("transaction_id", tx), ("run_id", run), ("row_count", count)) if v is not None})
    return {"event_uuid": "u%d" % i, "event_type": kind, "table_name": table, "payload": body, "status": status,
            "retry_count": retry, "processed_chain": False, "created_at": T0 + timedelta(seconds=i),
            "run_id": run, "transaction_id": tx, "row_count": count}


def _seed(db):
    """Lines of every shape, their first rows interleaved: 40 live lines of 1-7 rows, a live line of 1,500 rows (past
    COUNTED_TO), a run with its control row first, a run without one, rows with no line key (control and data), a
    line of control rows only, a retrying row with its failure, a run whose late row has no run (same answer) and
    MIXED."""
    rows, i = [], 0

    def add(**kw):
        nonlocal i
        i += 1
        rows.append(_row(i, **kw))

    add(kind=WANTED, table="t_b")                                                    # no line key, a control row
    add(tx="r4dd")                                                                   # MIXED: its first row, no run
    add(kind=RETRO, table=event_constants.RETROACTIVE_RUN_TABLE, run="r1aa",
        payload={"op": "reread", "requested_by": "ops", "params": {"x": 1}})
    for n in range(40):
        for k in range(1 + n % 7):
            add(tx="tx-%02d" % n, kind=("INSERT", "UPDATE")[k % 2], table=("t_a", "t_b")[n % 2],
                count=3 if k == 2 else None,
                **({"status": "RETRYING", "retry": 2, "payload": {event_constants.LAST_FAILURE: "boom",
                                                                   event_constants.LAST_FAILURE_STAGE: "map"}}
                   if (n, k) == (5, 1) else {}))
        if n == 10:
            add()                                                                    # no line key, a data row
            add(kind=NOW, table="t_a")                                               # no line key, a control row
            add(tx="tx-ctl", kind=WANTED, table="t_a")                               # a line of control rows only
        if n == 20:
            for _ in range(5):
                add(run="r2bb", tx="chain_r2", table="t_b")
            add(run="r3cc", tx="chain_r3")
            add(run=MIXED, tx="chain_r4")
    for k in range(1500):
        add(tx="tx-huge", kind=("INSERT", "UPDATE")[k % 3 == 0], count=2 if k % 5 == 0 else None)
    for _ in range(20):
        add(run="r1aa", tx="chain_r1", table="t_b")
    add(tx="r3cc")                                                                   # same key, no run, after a run row
    db.execute(insert(models.DatabaseOutbox.__table__), rows)
    db.commit()


@pytest.fixture
def db(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM database_outbox"))
    session = sessionmaker(bind=pg_engine, autoflush=False)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM database_outbox"))


@pytest.mark.parametrize("cap, chain_only", [(200, False), (200, True), (10, False), (50, True)])
def test_the_lines_are_the_old_groupings(db, cap, chain_only):
    _seed(db)
    old = [line for line in _old_lines(db, cap + 1, chain_only) if line["key"] != MIXED][:cap]
    new = queue_lines.waiting_lines(db, cap + 1, chain_only)
    mixed = [line for line in new if line.key == MIXED]
    assert len(mixed) == 1 and mixed[0].run is None, "MIXED is a live line by its first row - the pinned difference"
    new = [line for line in new if line.key != MIXED][:cap]
    assert len(old) == min(cap, old[0]["lines_total"] - 1) and len(old) > 5, "the fixture's lines are listed"
    assert [(n.key, n.run, n.first_id, n.created_at, n.lines_total) for n in new] == \
        [(o["key"], o["run"], o["first_id"], o["created_at"], o["lines_total"]) for o in old]
    assert any(n.key.startswith(event_constants.QUEUE_ROW_KEY_PREFIX) for n in new), \
        "the rows with no line key are lines of their own"


def test_the_drawn_lines_count_as_the_old_grouping_through_counted_to(db):
    _seed(db)
    old = {line["key"]: line for line in _old_lines(db, 200)}
    lines = queue_lines.waiting_lines(db, 200)
    counts = queue_lines.line_counts(db, lines)
    huge = counts["tx-huge"]
    assert (huge.events, huge.counted_to) == (queue_lines.COUNTED_TO, queue_lines.COUNTED_TO), "past it, said"
    assert huge.rows == sum(2 if k % 5 == 0 else 1 for k in range(queue_lines.COUNTED_TO)), "rows of the counted"
    assert counts["tx-05"].retrying and counts["tx-05"].max_retry == 2, "the fixture's retrying row is read"
    for line in lines:
        got, was = counts[line.key], old[line.key]
        retro, said = _old_detail(db, line.key)
        assert (got.retroactive, got.last_failure) == (retro, said), line.key
        if line.key == "tx-huge":
            continue
        assert got.counted_to is None, line.key
        assert (got.events, got.rows, got.max_retry, got.retrying, got.pairs) == \
            (was["events"], was["rows"], was["max_retry"], was["retrying"], was["pairs"]), line.key
    assert counts["r1aa"].retroactive and counts["tx-05"].last_failure, "the fixture's two read rows are read"


def _grow(db, rows):
    """`rows` more waiting rows under the fixture's lines - spread over its 40 live lines, none new."""
    db.execute(text(
        "INSERT INTO database_outbox (event_uuid, event_type, table_name, payload, status, retry_count, "
        "processed_chain, created_at, transaction_id) SELECT 'g' || g, 'UPDATE', 't_a', '{}'::jsonb, 'PENDING', 0, "
        "false, :t0 + g * interval '1 millisecond', 'tx-' || lpad(mod(g, 40)::text, 2, '0') "
        "FROM generate_series(1, :n) AS g"), {"n": rows, "t0": T0 + timedelta(days=1)})
    db.commit()
    db.execute(text("ANALYZE database_outbox"))
    db.commit()


def _clock(fn, times=5):
    took = []
    for _ in range(times):
        began = time.perf_counter()
        fn()
        took.append(time.perf_counter() - began)
    return statistics.median(took)


def test_the_time_follows_the_lines_not_the_waiting_rows(db):
    _seed(db)

    def new():
        queue_lines.line_counts(db, queue_lines.waiting_lines(db, 200))

    def old():
        _old_lines(db, 200)

    times = {}
    for rows in (20_000, 140_000):                                   # 20k waiting, then 160k under the same lines
        _grow(db, rows)
        lines = queue_lines.waiting_lines(db, 200)
        assert {line.key for line in lines} >= {"tx-%02d" % n for n in range(40)} and len(lines) < 60
        times[rows] = (_clock(new), _clock(old))
    (new_small, old_small), (new_big, old_big) = times[20_000], times[140_000]
    assert old_big >= old_small * 4, ("the old grouping grows with the rows - else this measures nothing", times)
    assert new_big <= new_small * 2, ("the lines' time follows the lines", times)
