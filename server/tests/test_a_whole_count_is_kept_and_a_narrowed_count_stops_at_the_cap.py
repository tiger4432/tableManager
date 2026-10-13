"""The grid's count (소유자 ㄱ · 총괄 67e5e9ccd ㄱ-1): a table's whole count is counted by one paced worker off
`invalidate_table_cache`, never in the request; a narrowed count stops past COUNT_CAP; /data, /data/count and the
export read the one function `table_total`."""
import json
import threading
import time
import uuid

import pytest

import main as main_mod
from database import models

TABLE = "raw_table_1"          # conftest seeds 10 rows
OTHER = "inventory_master"
WORKER = "whole-counter"


def _counts_by_thread(monkeypatch):
    """Every `Query.count()` as (thread name, the counted statement) - at SQLAlchemy, so a route that reached past
    `table_total` is seen too."""
    from sqlalchemy.orm import Query

    real, seen = Query.count, []

    def spy(self):
        seen.append((threading.current_thread().name,
                     str(self.statement.compile(compile_kwargs={"literal_binds": True}))))
        return real(self)

    monkeypatch.setattr(Query, "count", spy)
    return seen


def _held(table):
    with main_mod._COUNT_COND:
        return [dict(h) for k, h in main_mod._WHOLE.items() if main_mod.count_cache_table_of(k) == table]


def _until_counted(table, total, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        held = _held(table)
        if held and held[0]["total"] == total:
            return held[0]
        time.sleep(0.02)
    raise AssertionError("the worker did not count %s to %s in %s s: %s" % (table, total, seconds, _held(table)))


def _add(db_session, n, prefix="CNT"):
    model = models.DYNAMIC_TABLES[TABLE]
    for i in range(n):
        key = "%s_%02d_%s" % (prefix, i, uuid.uuid4().hex[:6])
        db_session.add(model(row_id=str(uuid.uuid4()), business_key_val=key, EQP_ID=key))
    db_session.commit()


def _count(client, table=TABLE, **params):
    r = client.get(f"/tables/{table}/data/count", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _pacing(monkeypatch, seconds):
    from parsers import directory_watcher
    monkeypatch.setattr(directory_watcher, "count_recount_seconds", lambda settings=None: seconds)


# ── the table whole ─────────────────────────────────────────────────────────────────────────────────────────────

def test_the_whole_count_is_counted_by_the_worker_and_never_in_the_request(client, monkeypatch):
    seen = _counts_by_thread(monkeypatch)

    body = _count(client)
    grid = client.get(f"/tables/{TABLE}/data").json()

    assert [name for name, _ in seen] == [WORKER], seen
    assert body["total"] == 10 and body["capped"] is False and body["counting"] is False
    assert body["counted_at"] and isinstance(body["count_seconds"], float)
    assert grid["total"] == 10 and grid["count"] == {k: body[k] for k in grid["count"]}


def test_right_after_a_restart_it_says_counting_then_the_count(client, monkeypatch):
    monkeypatch.setattr(main_mod, "COUNT_WAIT_SECONDS", 0)

    first = _count(client)
    _until_counted(TABLE, 10)
    then = _count(client)

    assert first == {"table_name": TABLE, "total": None, "capped": False, "counted_at": None,
                     "count_seconds": None, "counting": True}
    assert then["total"] == 10 and then["counting"] is False


def test_a_changed_table_keeps_its_last_count_until_the_pacing_then_follows_by_itself(client, db_session,
                                                                                     monkeypatch):
    _pacing(monkeypatch, 1.0)
    before = _count(client)
    _add(db_session, 2)
    main_mod.invalidate_table_cache(TABLE)

    stale = _count(client)
    followed = _until_counted(TABLE, 12)        # no request asks - the worker wakes at the pacing
    after = _count(client)

    assert stale == before, "inside the pacing a changed table must keep its last count and its time"
    assert after["total"] == 12 and after["counted_at"] == followed["counted_at"] > before["counted_at"]


def test_a_change_while_the_first_count_runs_is_counted_again(client, db_session, monkeypatch):
    from sqlalchemy.orm import Query

    _pacing(monkeypatch, 0)
    monkeypatch.setattr(main_mod, "COUNT_WAIT_SECONDS", 0)
    real, counted, go = Query.count, threading.Event(), threading.Event()

    def held(self):
        total = real(self)
        if threading.current_thread().name == WORKER and not counted.is_set():
            counted.set()
            go.wait(5)
        return total

    monkeypatch.setattr(Query, "count", held)
    _count(client)
    assert counted.wait(5), "the worker did not count"
    _add(db_session, 1)                                     # after the count's snapshot, before it is kept
    main_mod.invalidate_table_cache(TABLE)
    go.set()

    _until_counted(TABLE, 11)


def test_a_table_not_changed_is_not_counted_again(client, monkeypatch):
    _pacing(monkeypatch, 0)
    _count(client)
    _count(client, OTHER)
    seen = _counts_by_thread(monkeypatch)

    main_mod.invalidate_table_cache(TABLE)
    _count(client)
    _count(client, OTHER)

    assert [name for name, _ in seen] == [WORKER], "only the changed table is counted again: %s" % seen
    assert "raw_table_1" in seen[0][1]


def test_a_count_that_fails_leaves_the_worker_counting_the_next(client, monkeypatch, caplog):
    real = main_mod.grid_model

    def broken(table_name, world=None):
        if threading.current_thread().name == WORKER:
            raise RuntimeError("count broken on purpose")
        return real(table_name, world)

    monkeypatch.setattr(main_mod, "grid_model", broken)
    failed = _count(client)
    monkeypatch.setattr(main_mod, "grid_model", real)
    counted = _count(client)

    assert failed["counting"] is True and failed["total"] is None
    assert any("the whole count of" in r.getMessage() and "count broken on purpose" in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]
    assert counted["total"] == 10 and counted["counting"] is False


# ── narrowed ────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("narrowing", [
    {"q": "CAPPED"},
    {"filters": json.dumps({"EQP_ID": {"filterType": "text", "type": "startsWith", "filter": "CAPPED"}})},
], ids=["q", "filters"])
def test_a_narrowed_count_is_counted_here_and_stops_past_the_cap(client, db_session, monkeypatch, narrowing):
    monkeypatch.setattr(main_mod, "COUNT_CAP", 3)
    _add(db_session, 5, "CAPPED")
    seen = _counts_by_thread(monkeypatch)

    over = _count(client, **narrowing)
    grid = client.get(f"/tables/{TABLE}/data", params=narrowing).json()
    monkeypatch.setattr(main_mod, "COUNT_CAP", 7)
    under = _count(client, **narrowing)
    monkeypatch.setattr(main_mod, "COUNT_CAP", 5)
    at = _count(client, **narrowing)

    assert over["total"] == 3 and over["capped"] is True and over["counting"] is False
    assert grid["total"] == 3 and {"table_name": TABLE, **grid["count"]} == over, \
        "the grid's read of the same narrowing is the kept count - when, and what it took"
    assert under["total"] == 5 and under["capped"] is False
    assert at["total"] == 5 and at["capped"] is False
    assert WORKER not in [name for name, _ in seen]
    assert ["LIMIT 4" in seen[0][1], "LIMIT 8" in seen[1][1], "LIMIT 6" in seen[2][1]] == [True] * 3, seen


# ── the export ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_export_counts_here_not_the_kept_whole_count(client, db_session):
    kept = _count(client)
    _add(db_session, 1)
    main_mod.invalidate_table_cache(TABLE)

    r = client.get(f"/tables/{TABLE}/export")

    assert _count(client)["total"] == kept["total"] == 10, "inside the pacing the grid keeps its last count"
    assert r.status_code == 200 and r.headers["X-Total-Rows"] == "11"


def test_the_export_past_its_cap_says_more_than_the_cap(client, monkeypatch):
    monkeypatch.setattr(main_mod, "EXPORT_MAX_ROWS", 4)

    r = client.get(f"/tables/{TABLE}/export")

    assert r.status_code == 413 and "More than 4 rows" in r.json()["detail"], r.text
