# -*- coding: utf-8 -*-
"""Lead 11-12 ㄴ (D after_r1: opening the migration's batch read 7.9 M lines for 26-37 s): GET /audit_logs/transaction
answers a page and its cursor, the lined rows first written first, then the receipt-only rows - the same «more» runs
on into them -, and its count is counted up to ROW_TOTAL_PROBE_CAP.

    pages    250 lined rows (a fifth with a later line of the group) + 300 receipt-only rows (and a receipt naming
             lined rows): every row once over the pages, none twice, at the cursor's end not truncated
    steps    a step shorter than a page (GROUP_STEP_LINES) gives the same rows
    count    exact under the cap, the floor past it - on the route and on the recent list
    cursor   one it cannot read is a 400
"""
from datetime import datetime, timedelta, timezone

import pytest

import event_constants
from admin import audit_history
from database import models
from ledger.runtime_v2 import RECEIPT_COLUMN
from tests.support import line_tables
from tests.test_a_rows_history_is_its_lines import dialect_client  # noqa: F401
from tests.test_the_audit_panel_reads_audit_batches import TABLE, _load, panel  # noqa: F401

T0 = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
TX = "pg-a"
LINED, RECEIPT_ONLY = 250, 300


def _seed(engine, bits):
    """250 rows with a line of the group (every 5th a second, later one on its page 2), 300 rows its receipts name
    alone, and a receipt naming 20 of the lined rows too."""
    page_2 = TX + event_constants.GROUP_PART + "2"
    with engine.begin() as conn:
        for i in range(LINED):
            line_tables.line(conn, TABLE, bits, "L%03d" % i, at=T0 + timedelta(seconds=i), batch=TX,
                             values={"a": "x%d" % i})
        for i in range(0, LINED, 5):
            line_tables.line(conn, TABLE, bits, "L%03d" % i, at=T0 + timedelta(seconds=LINED + i), batch=page_2,
                             values={"a": "y%d" % i})
        line_tables.audit_batch(conn, TX, TABLE, written_by="parser", kind="new", at=T0)
        line_tables.audit_batch(conn, page_2, TABLE, written_by="person", kind="edit", at=T0 + timedelta(minutes=9))
        named = ["R%03d" % i for i in range(RECEIPT_ONLY)]
        receipts = [named[:100], named[100:200] + ["L%03d" % i for i in range(20)], named[200:]]
        for row_ids in receipts:
            conn.execute(models.AuditLog.__table__.insert().values(
                table_name=TABLE, row_id="-", column_name=RECEIPT_COLUMN, transaction_id=TX,
                new_value={"row_ids": row_ids}, source_name="formula", updated_by="formula fx.c", timestamp=T0))


def _pages(client, limit=200):
    pages, cursor = [], None
    while True:
        body = client.get("/audit_logs/transaction/%s" % TX,
                          params=dict({"limit": limit}, **({"cursor": cursor} if cursor else {}))).json()
        pages.append(body)
        if not body["truncated"]:
            assert body["next_cursor"] is None, body["next_cursor"]
            return pages
        cursor = body["next_cursor"]
        assert cursor and len(pages) < 20, "a cursor that does not move on"


@pytest.mark.parametrize("step", [audit_history.GROUP_STEP_LINES, 7])
def test_every_row_once_over_the_pages_lines_then_receipts(panel, monkeypatch, step):
    client, engine, bits = panel
    _seed(engine, bits)
    monkeypatch.setattr(audit_history, "GROUP_STEP_LINES", step)
    pages = _pages(client)
    rows = [log["row_id"] for page in pages for log in page["logs"]]
    assert [len(page["logs"]) for page in pages] == [200, 200, 150]
    assert len(rows) == len(set(rows)) == LINED + RECEIPT_ONLY
    assert rows[:LINED] == ["L%03d" % i for i in range(LINED)], "lined rows first, first written first"
    assert rows[LINED:] == ["R%03d" % i for i in range(RECEIPT_ONLY)], "then the receipt-only rows as named"
    assert (pages[0]["total_count"], pages[0]["total_truncated"]) == (LINED + RECEIPT_ONLY, False)


def test_the_count_is_the_floor_past_the_cap_on_the_route_and_the_recent_list(panel, monkeypatch):
    client, engine, bits = panel
    _seed(engine, bits)
    monkeypatch.setattr(audit_history, "ROW_TOTAL_PROBE_CAP", 100)
    body = client.get("/audit_logs/transaction/%s" % TX).json()
    assert (body["total_count"], body["total_truncated"]) == (100, True)
    _load(engine)
    [group] = client.get("/audit_logs/recent?limit_groups=100").json()["groups"]
    assert [(c["changed_rows"], c["changed_rows_truncated"]) for c in group["changed"]] == [(100, True)]
    monkeypatch.setattr(audit_history, "ROW_TOTAL_PROBE_CAP", 1000)
    session = _session(engine)
    try:                                        # closed before the fixture drops the table - PG waits on an open read
        assert audit_history.changed_rows(session, TABLE, TX) == (LINED + RECEIPT_ONLY, False)
    finally:
        session.close()


def test_a_cursor_it_cannot_read_is_a_400(panel):
    client, engine, bits = panel
    _seed(engine, bits)
    assert client.get("/audit_logs/transaction/%s" % TX, params={"cursor": "not-a-cursor"}).status_code == 400


def _session(engine):
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=engine)()
