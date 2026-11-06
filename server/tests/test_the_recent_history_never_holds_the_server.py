# -*- coding: utf-8 -*-
"""Owner 11-06 «STALL 303s P /audit_logs/recent ... D9/228s SELECT audit_logs»: whatever makes a statement slow, the
recent history answers within its two limits (`recent_statement_seconds` · `recent_walk_seconds`) - what it named so
far, truncated with its cursor - and a merge it cut is continued by the next read.

  walk     a statement past its limit (PostgreSQL cancels it) · the walk past its seconds · cut before any group
  merge    sliced by recent_scan_chunk_rows, every row counted once · a slice cut, the rest merged by the next read
  scope    the statement limit ends with the walk - the route's other statements do not carry it
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from admin import audit_cache, audit_history
from admin.audit_cache import AuditLogCache
from database import models

pytestmark = pytest.mark.pg

TABLE = "zz_recent_never_holds"
BASE = datetime(2032, 1, 1, tzinfo=timezone.utc)


def _seed(db, groups, start=0):
    for n, tid in enumerate(groups):
        for k in range(3):
            db.add(models.AuditLog(table_name=TABLE, row_id="r%d-%d-%d" % (start, n, k), column_name="v", old_value=None,
                                   new_value="x", source_name="t", updated_by="t", transaction_id=tid,
                                   timestamp=BASE + timedelta(minutes=start + n)))
    db.commit()


@pytest.fixture(name="db")
def fixture_db(pg_session, monkeypatch):
    knobs = {"recent_max_scan_rows": 10_000, "recent_scan_chunk_rows": 3, "recent_statement_seconds": 1,
             "recent_walk_seconds": 10}
    monkeypatch.setattr(audit_history, "load_config", lambda *a, **k: knobs)
    pg_session.knobs = knobs
    try:
        yield pg_session
    finally:
        pg_session.rollback()
        pg_session.execute(text("DELETE FROM audit_logs WHERE table_name = :t"), {"t": TABLE})
        pg_session.commit()


def _mine(groups):
    return [g["transaction_id"] for g in groups if g["transaction_id"].startswith("nh-")]


def _slow_from(monkeypatch, name, nth):
    """From its `nth` call on, `AuditLogCache.<name>` first sleeps 2 s in the database - a statement past a 1 s limit -
    until `state["off"]`."""
    real, state = getattr(AuditLogCache, name), {"calls": 0, "off": False}

    def slow(self, db, *args, **kwargs):
        state["calls"] += 1
        if state["calls"] >= nth and not state["off"]:
            db.execute(text("SELECT pg_sleep(2)"))
        return real(self, db, *args, **kwargs)
    monkeypatch.setattr(AuditLogCache, name, slow)
    return state


def test_a_statement_past_its_limit_answers_what_it_named_truncated(db, monkeypatch, caplog):
    _seed(db, ["nh-%d" % n for n in range(6)])                    # one group a chunk of 3 rows
    slow = _slow_from(monkeypatch, "_count_by_transaction", 3)
    cache, began = AuditLogCache(), time.monotonic()
    with caplog.at_level("WARNING"):
        cache.load_initial(db, limit_groups=50)
    assert time.monotonic() - began < 1.9, "cancelled at 1 s, not slept out"
    assert _mine(cache.groups) == ["nh-5", "nh-4"] and cache.truncated and cache.next_cursor
    assert "[Audit] recent walk cut at" in caplog.text and "a chunk's count past recent_statement_seconds 1" in caplog.text
    slow["off"] = True
    rest, _t, _n, _s = cache.page_from_cursor(db, cache.next_cursor, limit_groups=50)
    assert _mine(rest)[:1] == ["nh-3"], "the cursor resumes where the cut left"


def test_the_walk_past_its_seconds_answers_what_it_named(db, monkeypatch, caplog):
    _seed(db, ["nh-%d" % n for n in range(6)])
    db.knobs["recent_walk_seconds"] = 1
    real = AuditLogCache._chunk_edge
    monkeypatch.setattr(AuditLogCache, "_chunk_edge", lambda self, *a: time.sleep(0.6) or real(self, *a))
    cache = AuditLogCache()
    with caplog.at_level("WARNING"):
        cache.load_initial(db, limit_groups=50)
    assert _mine(cache.groups) == ["nh-5", "nh-4"] and cache.truncated and cache.next_cursor
    assert "past recent_walk_seconds 1" in caplog.text


def test_cut_before_any_group_is_not_loaded_and_the_next_read_walks_again(db, monkeypatch):
    _seed(db, ["nh-0"])
    slow = _slow_from(monkeypatch, "_count_by_transaction", 1)
    cache = AuditLogCache()
    cache.load_initial(db, limit_groups=50)
    assert not cache.is_loaded
    slow["off"] = True
    cache.load_initial(db, limit_groups=50)
    assert cache.is_loaded and _mine(cache.groups) == ["nh-0"]


def test_a_merge_goes_in_slices_and_a_cut_slice_is_continued_by_the_next_read(db, monkeypatch, caplog):
    _seed(db, ["nh-0"])
    cache = AuditLogCache()
    cache.load_initial(db, limit_groups=50)
    _seed(db, ["nh-1", "nh-2", "nh-3", "nh-4"], start=10)        # 12 ids: four slices of 3
    real, calls = audit_cache._tally, []

    def slow_third(db_, restrict):
        calls.append(1)
        if len(calls) == 3:
            db_.execute(text("SELECT pg_sleep(2)"))
        return real(db_, restrict)
    monkeypatch.setattr(audit_cache, "_tally", slow_third)
    with caplog.at_level("WARNING"):
        assert cache.refresh_if_stale(db, limit_groups=50) is True
    assert _mine(cache.groups) == ["nh-2", "nh-1", "nh-0"], "two slices merged before the cut"
    assert "[Audit] recent merge cut at" in caplog.text and "a slice's count past recent_statement_seconds 1" in caplog.text
    assert cache.refresh_if_stale(db, limit_groups=50) is True
    assert [(g["transaction_id"], g["total_count"]) for g in cache.groups if g["transaction_id"].startswith("nh-")] == [
        ("nh-4", 3), ("nh-3", 3), ("nh-2", 3), ("nh-1", 3), ("nh-0", 3)]


def test_the_statement_limit_ends_with_the_walk(db):
    _seed(db, ["nh-0"])
    cache = AuditLogCache()
    cache.load_initial(db, limit_groups=50)
    cache.refresh_if_stale(db, limit_groups=50)
    assert db.execute(text("SHOW statement_timeout")).scalar() == "0"
