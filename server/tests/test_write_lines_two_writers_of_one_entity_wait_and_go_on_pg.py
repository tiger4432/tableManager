# -*- coding: utf-8 -*-
"""The one write's lock gate (docs/design/CELL_SOURCE_OVERHAUL.md «쓰기» rules, A 11-10): two connections writing one
entity - an existing one, and a new key both name - the second waits for the first, then goes on without an error on
the same row_id; head lines = sources, no orphan line. PostgreSQL (sqlite has no row locks)."""
import faulthandler
import threading
import time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from database import crud, lines
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import stand_in_winners

pytestmark = pytest.mark.pg

TABLE = "wl_gate"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="sessions")
def fixture_sessions(pg_engine, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    lines.LineColumn.__table__.create(pg_engine, checkfirst=True)
    lines.AuditBatch.__table__.create(pg_engine, checkfirst=True)
    faulthandler.dump_traceback_later(90, exit=True)      # a hung lock gate says where, then stops
    make = sessionmaker(bind=pg_engine, autoflush=False)
    setup = make()
    monkeypatch.setattr(lines, "winners_sql", stand_in_winners(lines.ensure_line_table(setup, TABLE, CFG)),
                        raising=False)
    setup.commit()
    try:
        yield make
    finally:
        setup.rollback()
        lines.drop_line_table(setup, TABLE)
        setup.execute(lines.LineColumn.__table__.delete().where(lines.LineColumn.table_name == TABLE))
        setup.execute(lines.AuditBatch.__table__.delete().where(lines.AuditBatch.table_name == TABLE))
        setup.commit()
        setup.close()
        faulthandler.cancel_dump_traceback_later()


def _second_waits(make, first_items, second_items):
    """The first session writes and holds; the second writes in a thread - it must still be waiting after a while, and
    finish once the first commits. -> (the second's answer, seconds it waited)."""
    first, second = make(), make()
    got = {}

    def run():
        start = time.monotonic()
        try:
            got["answer"] = write_lines(second, TABLE, second_items, kind="funnel", transaction_id="tx-second")
            second.commit()
        except Exception as exc:                  # noqa: BLE001 - the test says what the second writer met
            got["error"] = exc
            second.rollback()
        got["waited"] = time.monotonic() - start

    try:                                          # a red first writer must not hold its locks into the teardown
        write_lines(first, TABLE, first_items, kind="funnel", transaction_id="tx-first")
        thread = threading.Thread(target=run)
        thread.start()
        time.sleep(1.0)
        still = thread.is_alive()
        first.commit()
        thread.join(30)
    finally:
        first.rollback()
        first.close()
        second.close()
    assert still, "the second writer did not wait for the first's lock"
    assert "error" not in got, got.get("error")
    return got["answer"], got["waited"]


def _state(make):
    s = make()
    shape = lines.shape(s, TABLE, CFG)
    ln, now = shape["lines"], shape["now"]
    rows = s.execute(select(ln.c.row_id, ln.c.source_name, ln.c.head_0, ln.c.line_kind)).all()
    alive = {r[0] for r in s.execute(select(now.c.row_id))}
    s.close()
    return rows, alive


def test_two_writers_of_one_row_end_on_it_one_after_the_other(sessions):
    make = sessions
    s = make()
    out = write_lines(s, TABLE, [{"key": {"k": "K1"}, "values": {"k": "K1", "a": "0"}, "source_name": "f0"}],
                      kind="funnel", transaction_id="tx-0")
    s.commit()
    s.close()
    [row_id] = out["changed"]
    answer, waited = _second_waits(make, [{"row_id": row_id, "values": {"a": "1"}, "source_name": "f1"}],
                                   [{"row_id": row_id, "values": {"a": "2"}, "source_name": "f2"}])
    rows, alive = _state(make)
    assert waited >= 0.9 and list(answer["changed"]) == [row_id]
    assert answer["changed"][row_id]["old"]["a"] == "1", "the second read the row before the first let it go"
    assert sorted(src for r, src, head, kind in rows if head) == ["f0", "f1", "f2"], rows
    assert {r for r, *_ in rows} <= alive, "no orphan line"


def test_two_writers_by_the_key_of_a_committed_row_one_after_the_other(sessions):
    make = sessions
    s = make()
    out = write_lines(s, TABLE, [{"key": {"k": "K3"}, "values": {"k": "K3", "a": "0"}, "source_name": "f0"}],
                      kind="funnel", transaction_id="tx-0")
    s.commit()
    s.close()
    [row_id] = out["changed"]
    answer, waited = _second_waits(make, [{"key": {"k": "K3"}, "values": {"k": "K3", "a": "1"}, "source_name": "f1"}],
                                   [{"key": {"k": "K3"}, "values": {"k": "K3", "a": "2"}, "source_name": "f2"}])
    assert waited >= 0.9 and list(answer["changed"]) == [row_id]
    assert answer["changed"][row_id]["old"]["a"] == "1", "the second read the row before the first let it go"


def test_two_writers_of_one_new_key_end_on_one_row(sessions):
    make = sessions
    item = {"key": {"k": "K2"}, "values": {"k": "K2", "a": "x"}, "source_name": "f1"}
    answer, waited = _second_waits(make, [item], [dict(item, source_name="f2")])
    rows, alive = _state(make)
    assert waited >= 0.9 and len(alive) == 1, alive
    assert {r for r, *_ in rows} == alive and len(rows) == 2, rows
    assert list(answer["changed"]) == list(alive)
