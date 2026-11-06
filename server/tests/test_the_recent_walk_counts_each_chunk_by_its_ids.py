# -*- coding: utf-8 -*-
"""The recent walk counts each chunk by its ids (총괄 11-06, 소유자 ㄴ) - on PostgreSQL the same groups, counts and
receipt worlds as an independent count of the seeded rows, in each caller's shape:

  load_initial      every group, chunks of 3 (groups straddle them) and of 1000 (one chunk)
  page_from_cursor  two pages are a partition - no group in both, none in neither
  refresh_if_stale  the rows added after the load merged into the same counts (its id-range tally, not changed)

The speed - no whole-table scan per chunk - is not asserted: a seed this small is planned as a scan whatever the
query says. That is the box board's (RUN.md).
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from admin import audit_cache, audit_history
from admin.audit_cache import AuditLogCache
from database import models
from ledger.runtime_v2 import RECEIPT_COLUMN

pytestmark = pytest.mark.pg

TABLE = "zz_recent_walk_ids"
BASE = datetime(2031, 1, 1, tzinfo=timezone.utc)        # above whatever else the database holds
# (transaction, minute, column, world) - oldest first; "a" and "b" each come back later, so they straddle the chunks
ROWS = ([("w-a", 0, "value", None)] * 4 + [("w-b", 1, "value", None)] * 2 + [("w-c", 2, RECEIPT_COLUMN, "w1")] * 3
        + [("w-a", 3, "value", None)] * 2 + [("w-d", 4, RECEIPT_COLUMN, "w2")] + [("w-b", 5, RECEIPT_COLUMN, "w1")] * 2
        + [("w-e", 6, "value", None)] * 5)
LATER = [("w-f", 7, "value", None)] * 3 + [("w-a", 8, RECEIPT_COLUMN, "w2")] * 2


def _seed(db, rows):
    for n, (tid, minute, column, world) in enumerate(rows):
        db.add(models.AuditLog(table_name=TABLE, row_id="r%d-%d" % (minute, n), column_name=column, old_value=None,
                               new_value={"world": world} if world else "v", source_name="test", updated_by="test",
                               transaction_id=tid, timestamp=BASE + timedelta(minutes=minute)))
    db.commit()


def _oracle(rows):
    """{transaction: (rows, {world: receipts})}, newest first - counted here, not by the walk."""
    newest, said = {}, {}
    for n, (tid, minute, column, world) in enumerate(rows):
        newest[tid] = (minute, n)
        count, worlds = said.setdefault(tid, [0, {}])
        said[tid][0] = count + 1
        if column == RECEIPT_COLUMN:
            worlds[world] = worlds.get(world, 0) + 1
    return [(tid, said[tid][0], said[tid][1]) for tid in sorted(newest, key=newest.get, reverse=True)]


def _seen(groups):
    return [(g["transaction_id"], g["total_count"], {w: c[0] for w, c in g["summary"]["worlds"].items()})
            for g in groups if g["transaction_id"].startswith("w-")]


@pytest.fixture(name="db")
def fixture_db(pg_session, monkeypatch):
    knobs = {}
    monkeypatch.setattr(audit_history, "load_config", lambda *a, **k: knobs)
    pg_session.knobs = knobs
    try:
        yield pg_session
    finally:
        pg_session.rollback()
        pg_session.execute(text("DELETE FROM audit_logs WHERE table_name = :t"), {"t": TABLE})
        pg_session.commit()


def test_the_load_counts_what_an_independent_count_counts(db):
    _seed(db, ROWS)
    for chunk in (3, 1000):
        db.knobs.update(recent_max_scan_rows=10_000, recent_scan_chunk_rows=chunk)
        cache = AuditLogCache()
        cache.load_initial(db, limit_groups=50)
        assert _seen(cache.groups) == _oracle(ROWS), chunk


def test_two_pages_are_a_partition(db):
    _seed(db, ROWS)
    db.knobs.update(recent_max_scan_rows=10_000, recent_scan_chunk_rows=3)
    cache = AuditLogCache()
    cache.load_initial(db, limit_groups=2)
    assert cache.next_cursor, "a first page of two leaves more"
    later, _truncated, _next, _scanned = cache.page_from_cursor(db, cache.next_cursor, limit_groups=50)
    first, second = [g["transaction_id"] for g in cache.groups], [g["transaction_id"] for g in later]
    assert first + [t for t in second if t.startswith("w-")] == [tid for tid, _n, _w in _oracle(ROWS)]


def test_a_refresh_merges_the_rows_after_the_load_into_the_same_counts(db):
    _seed(db, ROWS)
    db.knobs.update(recent_max_scan_rows=10_000, recent_scan_chunk_rows=3)
    cache = AuditLogCache()
    cache.load_initial(db, limit_groups=50)
    _seed(db, LATER)
    assert cache.refresh_if_stale(db, limit_groups=50) is not False
    assert _seen(cache.groups) == _oracle(ROWS + LATER)
