# -*- coding: utf-8 -*-
"""Owner 11-09 «오딧로그가 아예 안 뜨네 · no row» → «다시 뜸», «쓰는 중에도 90 % 가 페치 중», lead: reads are not held by
writes. `GET /audit_logs/recent` answers the projection it holds at once; its walk (the first) and its merge of what
other processes wrote run behind the read, one at a time (`AuditLogCache.behind`), and `updating` says so - with no
groups yet it means «reading», never «no history».

    read before the walk    at once, no groups, updating · the walk slow or cut: still at once, still updating
    read after the walk     the groups, not updating
    rows another process    the held list at once and updating; read again after the merge: the new group on top
    wrote meanwhile
"""
import threading
import time

from sqlalchemy.exc import OperationalError

import db_waits
from admin import audit_cache
from admin.audit_cache import AuditLogCache
from runtime import request_timing
from tests.test_audit_cache_recent_scan import seed

URL = "/audit_logs/recent?limit_groups=100"


def _settle():
    """The catch-up behind the last read has ended; a read now (within CATCH_UP_GAP_SECONDS) starts none."""
    behind = audit_cache.audit_cache._behind
    if behind is not None:
        behind.join(30)


def _gap_passed():
    """As if CATCH_UP_GAP_SECONDS went by: the next read starts the next catch-up."""
    audit_cache.audit_cache._behind_ended = float("-inf")


def _mine(body):
    return [g["transaction_id"] for g in body["groups"] if g["transaction_id"].startswith("aw-")]


def test_a_read_before_the_walk_answers_at_once_reading_and_the_next_has_the_groups(
        client, db_session, monkeypatch, caplog):
    seed(db_session, [("aw-a", 2), ("aw-b", 2)])
    audit_cache.audit_cache.__init__()                          # a restart
    go, real = threading.Event(), AuditLogCache._discover_groups
    monkeypatch.setattr(AuditLogCache, "_discover_groups", lambda self, *a, **k: go.wait(30) and real(self, *a, **k))
    monkeypatch.setattr(request_timing, "slow_request_ms", lambda: 0)
    began = time.monotonic()
    first = client.get(URL).json()
    assert time.monotonic() - began < 1.0, "the read did not wait for the walk"
    assert (first["groups"], first["updating"]) == ([], True), first
    with caplog.at_level("WARNING", logger="Server"):
        go.set()
        _settle()
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Slow] recent history behind")]
    assert len(said) == 1 and " · walk " in said[0] and " · merge " in said[0], said    # the walk says its time
    second = client.get(URL).json()
    assert _mine(second) == ["aw-b", "aw-a"] and second["updating"] is False, second


class _Cancelled(Exception):
    pgcode = db_waits.QUERY_CANCELED


def test_a_walk_cut_before_any_group_still_says_reading_not_none(client, db_session, monkeypatch):
    seed(db_session, [("aw-a", 2)])
    audit_cache.audit_cache.__init__()
    cut = {"on": True}
    real = AuditLogCache._discover_groups

    def walk(self, *a, **k):
        if cut["on"]:
            raise OperationalError("SELECT ...", {}, _Cancelled())
        return real(self, *a, **k)
    monkeypatch.setattr(AuditLogCache, "_discover_groups", walk)
    client.get(URL)
    audit_cache.audit_cache._behind.join(30)
    after_cut = client.get(URL).json()                         # within the gap: no walk runs, none has loaded
    assert (after_cut["groups"], after_cut["updating"]) == ([], True), after_cut
    cut["on"] = False
    _gap_passed()
    client.get(URL)
    _settle()
    assert _mine(client.get(URL).json()) == ["aw-a"]


def test_rows_another_process_wrote_come_from_the_merge_behind_the_read(client, db_session, monkeypatch):
    seed(db_session, [("aw-a", 2)])
    audit_cache.audit_cache.__init__()
    client.get(URL)
    _settle()
    assert _mine(client.get(URL).json()) == ["aw-a"]
    seed(db_session, [("aw-b", 2)])                             # committed elsewhere: no notification here
    _gap_passed()
    go, real = threading.Event(), AuditLogCache.refresh_if_stale
    monkeypatch.setattr(AuditLogCache, "refresh_if_stale", lambda self, *a, **k: go.wait(30) and real(self, *a, **k))
    began = time.monotonic()
    held = client.get(URL).json()
    assert time.monotonic() - began < 1.0, "the read did not wait for the merge"
    assert _mine(held) == ["aw-a"] and held["updating"] is True, held
    go.set()
    _settle()
    merged = client.get(URL).json()
    assert _mine(merged) == ["aw-b", "aw-a"] and merged["updating"] is False, merged


def test_the_screens_read_again_does_not_start_the_next_catch_up(client, db_session):
    # The panel reads again HISTORY_REREAD_MS (2 s) after an `updating` answer; with the gap at 2 s every read-again
    # started another catch-up and the panel said «Updating» for ever (Chrome look 11-09).
    seed(db_session, [("aw-a", 2)])
    audit_cache.audit_cache.__init__()
    assert client.get(URL).json()["updating"] is True
    _settle()
    audit_cache.audit_cache._behind_ended -= 2.5               # the screen's read-again, a little late
    again = client.get(URL).json()
    assert _mine(again) == ["aw-a"] and again["updating"] is False, again
