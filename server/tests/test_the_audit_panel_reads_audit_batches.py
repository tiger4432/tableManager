# -*- coding: utf-8 -*-
"""Cell-source overhaul, D's read share - the audit panel reads `audit_batches` alone (docs/design/
CELL_SOURCE_OVERHAUL.md «감사 로그», owner 11-10 «트랜잭션, 테이블별, 누가, 바뀐 행수, 바뀐 작업 타입» · «바뀐 행 네비» ·
ㄱ «audit_logs 완전 은퇴»). Lines and batches by hand (tests/support/line_tables) until the write share.

    list     newest first by each group's newest batch; per table: kinds and writers in the order written, the
             batches' count, rows changed counted distinct from its lines - None for a relation without lines; a
             replay page's tail is one group; a table the reader may not read is not shown
    pages    one group a page - a group with batches on both sides of a boundary named once, none missing; a walk
             past recent_max_scan_rows says truncated with its cursor, an exhausted one does not
    bounds   the walk past recent_walk_seconds answers what it named; cut before any group: not loaded
    merge    a later batch's group to the top, in slices, every batch once; a notification's `changed` at once,
             replaced by the merge's exact count
    behind   the read answers the projection it holds at once, `updating` while the walk runs
    jump     ?table=&limit=1 is the first row written; every row of the table without it; 404 without a batch
    events   a receipt or a table-wide record in audit_logs is its transaction's line beside its tables (owner 11-11 ㄱ):
             alone or with cell lines, after a merge, on the transaction route; a cell's line there is not one
    grid     the transaction filter is the rows of its lines; none in a relation without lines
"""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

import event_constants
import grid_read
from admin import audit_cache, audit_history
from admin.audit_cache import AuditLogCache
from conftest import retire_dynamic_model
from admin import access
from database import lines, models
from tests.support import line_tables
from tests.test_a_rows_history_is_its_lines import ENTRY, TABLE, dialect_client, _line_table_fixture  # noqa: F401

T0 = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
URL = "/audit_logs/recent?limit_groups=100"
LEDGER = "ab_ledger_view"                      # a relation an audit batch names that keeps no lines


@pytest.fixture
def panel(dialect_client, monkeypatch):
    client, engine, bits = _line_table_fixture(dialect_client, monkeypatch, TABLE, ENTRY)
    monkeypatch.setattr(audit_history, "load_config", lambda *a, **k: {})
    with engine.begin() as conn:
        conn.execute(lines.AuditBatch.__table__.delete())
        conn.execute(models.AuditLog.__table__.delete())
    audit_cache.audit_cache.__init__()
    try:
        yield client, engine, bits
    finally:
        with engine.begin() as conn:
            conn.execute(lines.AuditBatch.__table__.delete())
            conn.execute(models.AuditLog.__table__.delete())
        line_tables.drop(engine, TABLE)
        retire_dynamic_model(TABLE)
        audit_cache.audit_cache.__init__()


def _knobs(monkeypatch, **knobs):
    monkeypatch.setattr(audit_history, "load_config", lambda *a, **k: knobs)


def _seed(engine, bits):
    """ab-a: r2 then r1 new by a file, its page 2 edits r1 by hand; ab-b: a ledger receipt (no lines); ab-c: the
    chain edits r3 - the newest."""
    with engine.begin() as conn:
        line_tables.line(conn, TABLE, bits, "r2", at=T0 + timedelta(minutes=1), batch="ab-a", values={"a": "x"},
                         business_key="K2")
        line_tables.line(conn, TABLE, bits, "r1", at=T0 + timedelta(minutes=1), batch="ab-a", values={"a": "y"},
                         business_key="K1")
        line_tables.audit_batch(conn, "ab-a", TABLE, written_by="parser", kind="new", at=T0 + timedelta(minutes=1))
        page_2 = "ab-a" + event_constants.GROUP_PART + "2"
        line_tables.line(conn, TABLE, bits, "r1", at=T0 + timedelta(minutes=3), batch=page_2, values={"a": "z"},
                         business_key="K1")
        line_tables.audit_batch(conn, page_2, TABLE, written_by="person", kind="edit", at=T0 + timedelta(minutes=3))
        line_tables.audit_batch(conn, "ab-b", LEDGER, written_by="ledger", kind="receipt", at=T0)
        line_tables.line(conn, TABLE, bits, "r3", at=T0 + timedelta(minutes=4), batch="ab-c", values={"a": "w"},
                         business_key="K3")
        line_tables.audit_batch(conn, "ab-c", TABLE, written_by="chain", kind="edit", at=T0 + timedelta(minutes=4))
        for row_id, key in (("r1", "K1"), ("r2", "K2"), ("r3", "K3")):
            line_tables.now(conn, TABLE, row_id, key, {"k": key, "a": "v"})


def _session(engine):
    return sessionmaker(bind=engine)()


def _load(engine, limit_groups=100, cache=None):
    cache = cache or audit_cache.audit_cache
    session = _session(engine)
    try:
        cache.load_initial(session, limit_groups)
    finally:
        session.close()
    cache._behind_ended = float("inf")                         # no catch-up behind the reads below
    return cache


def _said(group):
    return (group["transaction_id"], group["total_count"], group["logs"],
            [(c["table_name"], c["changed_rows"], c["kinds"], c["written_by"]) for c in group["changed"]])


def _keys(groups):
    return [g["transaction_id"] for g in groups]


def test_the_list_names_each_transaction_by_its_batches_newest_first(panel, monkeypatch):
    client, engine, bits = panel
    _seed(engine, bits)
    _load(engine)
    body = client.get(URL).json()
    assert [_said(g) for g in body["groups"]] == [
        ("ab-c", 0, [], [(TABLE, 1, ["edit"], ["chain"])]),
        ("ab-a", 0, [], [(TABLE, 2, ["new", "edit"], ["parser", "person"])]),
        ("ab-b", 0, [], [(LEDGER, None, ["receipt"], ["ledger"])])], body
    at = body["groups"][1]["changed"][0]["at"]
    assert datetime.fromisoformat(at) == T0 + timedelta(minutes=3), at
    assert (body["truncated"], body["next_cursor"], body["returned"]) == (False, None, 3)
    monkeypatch.setattr(access, "may", lambda user, name, what: name != LEDGER)
    assert _keys(client.get(URL).json()["groups"]) == ["ab-c", "ab-a"], "a table the reader may not read"


def test_pages_name_each_group_once_across_a_boundary(panel):
    _client, engine, bits = panel
    _seed(engine, bits)
    with engine.begin() as conn:      # ab-a's newest batch now sits above ab-c: on page 1, its older batch below
        line_tables.audit_batch(conn, "ab-a", TABLE, written_by="person", kind="edit", at=T0 + timedelta(minutes=5))
    cache = _load(engine, limit_groups=1)
    seen, cursor = _keys(cache.groups), cache.next_cursor
    session = _session(engine)
    try:
        for _ in range(5):
            if not cursor:
                break
            groups, _truncated, cursor, _scanned = cache.page_from_cursor(session, cursor, 1)
            seen += _keys(groups)
    finally:
        session.close()
    assert (seen, cursor) == (["ab-a", "ab-c", "ab-b"], None), seen


def test_a_walk_past_its_rows_says_truncated_and_an_exhausted_one_does_not(panel, monkeypatch):
    _client, engine, bits = panel
    _seed(engine, bits)
    _knobs(monkeypatch, recent_max_scan_rows=2, recent_scan_chunk_rows=1)
    cache = _load(engine, cache=AuditLogCache())
    assert (_keys(cache.groups), cache.truncated, bool(cache.next_cursor)) == (["ab-c", "ab-a"], True, True)
    _knobs(monkeypatch, recent_scan_chunk_rows=1)
    cache = _load(engine, cache=AuditLogCache())
    assert (_keys(cache.groups), cache.truncated, cache.next_cursor) == (["ab-c", "ab-a", "ab-b"], False, None)


def test_the_walk_past_its_seconds_answers_what_it_named_and_a_cut_before_any_is_not_loaded(
        panel, monkeypatch, caplog):
    _client, engine, bits = panel
    _seed(engine, bits)
    _knobs(monkeypatch, recent_walk_seconds=1, recent_scan_chunk_rows=1)
    clock = {"now": 0.0}
    monkeypatch.setattr(audit_cache.time, "monotonic", lambda: clock.__setitem__("now", clock["now"] + 0.6)
                        or clock["now"])
    with caplog.at_level("WARNING"):
        cache = _load(engine, cache=AuditLogCache())
    assert cache.is_loaded and cache.truncated and _keys(cache.groups) == ["ab-c"], _keys(cache.groups)
    assert "past recent_walk_seconds 1" in caplog.text
    monkeypatch.setattr(audit_cache, "_walk", lambda *a: ([], True, 0, "a chunk past recent_statement_seconds 5"))
    cache = AuditLogCache()
    cache.load_initial(_session(engine))
    assert not cache.is_loaded, "nothing named: the next read walks again rather than show none"


def test_a_later_batch_reaches_the_top_in_slices_and_a_notification_at_once(panel, monkeypatch):
    client, engine, bits = panel
    _seed(engine, bits)
    _load(engine)
    audit_cache.audit_cache.add_changed([{"transaction_id": "ab-d", "table_name": TABLE, "changed_rows": 1,
                                          "kind": "withdraw", "written_by": "chain"},
                                         {"transaction_id": "ab-d", "table_name": TABLE, "changed_rows": 1,
                                          "kind": "withdraw", "written_by": "chain"}])
    assert _said(client.get(URL).json()["groups"][0]) == ("ab-d", 0, [], [(TABLE, 2, ["withdraw"], ["chain"])]), \
        "two shares added at once - over the distinct count until the merge"
    with engine.begin() as conn:
        for minute in (9, 10):
            line_tables.line(conn, TABLE, bits, "r2", at=T0 + timedelta(minutes=minute), batch="ab-d",
                             withdrawn=("a",), kind="withdraw", business_key="K2")
            line_tables.audit_batch(conn, "ab-d", TABLE, written_by="chain", kind="withdraw",
                                    at=T0 + timedelta(minutes=minute))
        line_tables.audit_batch(conn, "ab-e", LEDGER, written_by="ledger", kind="receipt",
                                at=T0 + timedelta(minutes=11))
    _knobs(monkeypatch, recent_scan_chunk_rows=1)
    session = _session(engine)
    try:
        assert audit_cache.audit_cache.refresh_if_stale(session) is True
    finally:
        session.close()
    groups = client.get(URL).json()["groups"]
    assert [_said(g) for g in groups[:2]] == [("ab-e", 0, [], [(LEDGER, None, ["receipt"], ["ledger"])]),
                                              ("ab-d", 0, [], [(TABLE, 1, ["withdraw"], ["chain"])])], groups[:2]
    assert _keys(groups) == ["ab-e", "ab-d", "ab-c", "ab-a", "ab-b"], "three slices, every batch once"


def test_the_read_answers_at_once_and_walks_behind(panel, monkeypatch):
    client, engine, bits = panel
    _seed(engine, bits)
    go, real = threading.Event(), AuditLogCache._discover
    monkeypatch.setattr(AuditLogCache, "_discover", lambda self, *a, **k: go.wait(30) and real(self, *a, **k))
    began = time.monotonic()
    first = client.get(URL).json()
    assert time.monotonic() - began < 1.0, "the read did not wait for the walk"
    assert (first["groups"], first["updating"]) == ([], True), first
    go.set()
    audit_cache.audit_cache._behind.join(30)
    second = client.get(URL).json()
    assert (_keys(second["groups"]), second["updating"]) == (["ab-c", "ab-a", "ab-b"], False), second


def test_a_panel_line_jumps_to_the_first_row_written_and_the_transaction_lists_its_rows(panel):
    client, engine, bits = panel
    _seed(engine, bits)
    first = client.get("/audit_logs/transaction/ab-a", params={"table": TABLE, "limit": 1}).json()
    assert [(e["row_id"], e["business_key"], e["column_name"], e["is_row_deleted"]) for e in first["logs"]] == [
        ("r2", "K2", None, False)], first
    every = client.get("/audit_logs/transaction/ab-a").json()
    assert [(e["row_id"], e["updated_by"]) for e in every["logs"]] == [("r2", "probe"), ("r1", "probe")], every
    assert every["total_count"] == 2
    receipt = client.get("/audit_logs/transaction/ab-b").json()
    assert (receipt["logs"], receipt["total_count"]) == ([], 0), "a relation without lines: its batch, no rows"
    assert client.get("/audit_logs/transaction/ab-none").status_code == 404


def test_the_grids_transaction_filter_is_the_rows_of_its_lines(panel):
    _client, engine, bits = panel
    _seed(engine, bits)
    session = _session(engine)
    try:
        model = models.DYNAMIC_TABLES[TABLE]
        found = sorted(r.row_id for r in session.query(model).filter(
            grid_read.transaction_rows(session, model, TABLE, "ab-a")))
        assert found == ["r1", "r2"], found
    finally:
        session.close()


@pytest.mark.pg
def test_a_statement_past_its_limit_answers_what_the_walk_named_truncated(pg_engine, monkeypatch, caplog):
    """PostgreSQL cancels a walk's statement past recent_statement_seconds; the walk answers what it named."""
    from sqlalchemy import text

    with pg_engine.begin() as conn:
        conn.execute(lines.AuditBatch.__table__.delete())
        for minute in range(3):
            line_tables.audit_batch(conn, "ab-cut-%d" % minute, LEDGER, kind="receipt",
                                    at=T0 + timedelta(minutes=minute))
    _knobs(monkeypatch, recent_statement_seconds=1, recent_scan_chunk_rows=1)
    real, calls = audit_cache._seen_at_or_above, []

    def slow(db, floor, keys):
        calls.append(1)
        db.execute(text("SELECT pg_sleep(2)"))
        return real(db, floor, keys)
    monkeypatch.setattr(audit_cache, "_seen_at_or_above", slow)
    session = _session(pg_engine)
    try:
        cache = AuditLogCache()
        cache.load_initial(session, limit_groups=1)
        assert _keys(cache.groups) == ["ab-cut-2"] and cache.next_cursor
        began = time.monotonic()
        with caplog.at_level("WARNING"):
            groups, truncated, _nxt, _scanned = cache.page_from_cursor(session, cache.next_cursor, 5)
        assert time.monotonic() - began < 1.9, "cancelled at 1 s, not slept out"
        assert (groups, truncated, len(calls)) == ([], True, 1)
        assert "the groups an earlier page named past recent_statement_seconds 1" in caplog.text
    finally:
        session.close()
        with pg_engine.begin() as conn:
            conn.execute(lines.AuditBatch.__table__.delete())


def _events(engine, *written):
    """audit_logs rows as their writers build them - `crud.receipt_log` (a ledger batch's receipt, `runtime_v2`) or
    `crud.create_audit_log` (a table-wide «*» record, set_aside; a cell's line) - inserted as the ledger store does."""
    from database import crud

    session = _session(engine)
    try:
        for each in written:
            crud.bulk_insert_audit_logs(session, each)
        session.commit()
    finally:
        session.close()


def _receipt(tx, rows=("r1", "r2")):
    from database import crud
    from ledger.runtime_v2 import RECEIPT_LABEL

    return crud.receipt_log(None, LEDGER, "batch-" + str(tx), RECEIPT_LABEL, {"rows": len(rows), "status": "ok"},
                            "ledger", "ledger", tx, row_ids=list(rows))


def _line(tx, column, row_id="r1", new="v"):
    from database import crud

    return [crud.create_audit_log(None, TABLE, row_id, column, None, new, "chain", "chain", transaction_id=tx,
                                  add_to_cache=False)]


def _event_said(group):
    return (group["transaction_id"], group["total_count"], group["summary_columns"],
            [(log["table_name"], log["column_name"], (log["new_value"] or {}).get("receipt_label")
              if isinstance(log["new_value"], dict) else log["new_value"]) for log in group["logs"]],
            [c["table_name"] for c in group["changed"]])


def test_a_receipt_is_its_transactions_line_beside_its_tables_and_a_cells_line_is_not(panel, monkeypatch):
    """A ledger batch's receipt alone (ab-r), one in a transaction that also wrote cells (ab-c), a table-wide record
    (ab-s), and a cell's line still written to audit_logs (ab-x) - not an event, so no line of its own."""
    from ledger.runtime_v2 import RECEIPT_COLUMN

    client, engine, bits = panel
    _seed(engine, bits)
    _events(engine, _line("ab-x", "a"), _receipt("ab-c"), _line("ab-s", "*", row_id="*", new=3), _receipt("ab-r"))
    _load(engine)
    body = client.get(URL).json()
    said = {g["transaction_id"]: _event_said(g) for g in body["groups"]}
    assert _keys(body["groups"])[:3] == ["ab-r", "ab-s", "ab-c"], _keys(body["groups"])
    assert said["ab-r"] == ("ab-r", 1, [RECEIPT_COLUMN], [(LEDGER, RECEIPT_COLUMN, "Ledger batch")], []), said
    assert said["ab-c"] == ("ab-c", 1, [RECEIPT_COLUMN], [(LEDGER, RECEIPT_COLUMN, "Ledger batch")], [TABLE]), said
    assert said["ab-s"] == ("ab-s", 1, ["*"], [(TABLE, "*", 3)], []), said
    assert "ab-x" not in said, "a cell's line in audit_logs is not an event"
    monkeypatch.setattr(access, "may", lambda user, name, what: name != LEDGER)
    said = {g["transaction_id"]: _event_said(g) for g in client.get(URL).json()["groups"]}
    assert "ab-r" not in said and said["ab-c"][3] == [], "a receipt of a table the reader may not read"


def test_a_later_receipt_reaches_the_top_and_its_transaction_route_lists_it(panel):
    from ledger.runtime_v2 import RECEIPT_COLUMN

    client, engine, bits = panel
    _seed(engine, bits)
    _load(engine)
    _events(engine, _receipt("ab-r"), _line("ab-x", "a"))
    session = _session(engine)
    try:
        assert audit_cache.audit_cache.refresh_if_stale(session) is True
    finally:
        session.close()
    groups = client.get(URL).json()["groups"]
    assert [_event_said(g) for g in groups[:1]] == [
        ("ab-r", 1, [RECEIPT_COLUMN], [(LEDGER, RECEIPT_COLUMN, "Ledger batch")], [])], groups[:1]
    assert "ab-x" not in _keys(groups)
    route = client.get("/audit_logs/transaction/ab-r").json()
    assert [(e["table_name"], e["column_name"], e["row_id"]) for e in route["logs"]] == [
        (LEDGER, RECEIPT_COLUMN, "batch-ab-r")], route
    assert route["total_count"] == 1
    assert client.get("/audit_logs/transaction/ab-x").status_code == 404, "a cell's line in audit_logs is not one"


def test_pages_name_a_receipt_group_once(panel):
    _client, engine, bits = panel
    _seed(engine, bits)
    _events(engine, _receipt("ab-c"), _receipt("ab-r"))
    cache = _load(engine, limit_groups=1)
    seen, cursor = _keys(cache.groups), cache.next_cursor
    session = _session(engine)
    try:
        for _ in range(6):
            if not cursor:
                break
            groups, _truncated, cursor, _scanned = cache.page_from_cursor(session, cursor, 1)
            seen += _keys(groups)
    finally:
        session.close()
    assert (seen, cursor) == (["ab-r", "ab-c", "ab-a", "ab-b"], None), seen
