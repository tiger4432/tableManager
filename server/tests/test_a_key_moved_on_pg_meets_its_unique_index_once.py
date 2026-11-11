# -*- coding: utf-8 -*-
"""Step 5½ on PostgreSQL, under t's unique business key index (QA 11-11: «_put_keys' clear-then-take was never run
under the index»): rows of one write swapping keys or passing one along move without a unique violation, and a row
moved onto a held key is merged into the holder - the shell gone, its lines on the holder."""
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from database import crud, lines, models
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import keep_lines

pytestmark = pytest.mark.pg

TABLE = "wl_rekey_pg"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="db")
def fixture_db(pg_engine, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    lines.LineColumn.__table__.create(pg_engine, checkfirst=True)
    lines.AuditBatch.__table__.create(pg_engine, checkfirst=True)
    lines.LineSource.__table__.create(pg_engine, checkfirst=True)
    models.DatabaseOutbox.__table__.create(pg_engine, checkfirst=True)
    models.CellOverwrite.__table__.create(pg_engine, checkfirst=True)
    db = sessionmaker(bind=pg_engine, autoflush=False)()
    keep_lines(db, TABLE, CFG)
    db.commit()
    try:
        yield db
    finally:
        db.rollback()
        lines.drop_line_table(db, TABLE)
        db.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))
        db.execute(lines.LineColumn.__table__.delete().where(lines.LineColumn.table_name == TABLE))
        db.execute(lines.AuditBatch.__table__.delete().where(lines.AuditBatch.table_name == TABLE))
        db.commit()
        db.close()


def _write(db, items, tx):
    answer = write_lines(db, TABLE, items, kind="funnel", transaction_id=tx)
    db.commit()
    return answer


def _rows(db):
    now = lines.shape(db, TABLE, CFG)["table"]
    return {key: (row_id, a) for row_id, key, a in db.execute(select(now.c.row_id, now.c.business_key_val, now.c.a))}


def _two(db):
    _write(db, [{"key": {"k": "K1"}, "values": {"k": "K1", "a": "one"}, "source_name": "f1.csv"},
                {"key": {"k": "K2"}, "values": {"k": "K2", "a": "two"}, "source_name": "f2.csv"}], "tx-seed")
    rows = _rows(db)
    assert set(rows) == {"K1", "K2"}, "canary: two rows"
    return rows["K1"][0], rows["K2"][0]


def test_two_rows_swapping_keys_in_one_write_move(db):
    one, two = _two(db)
    _write(db, [{"row_id": one, "values": {"k": "K2"}, "source_name": "f9.csv"},
                {"row_id": two, "values": {"k": "K1"}, "source_name": "f9.csv"}], "tx-swap")
    assert _rows(db) == {"K2": (one, "one"), "K1": (two, "two")}


def test_a_key_passed_along_in_one_write_moves(db):
    one, two = _two(db)
    _write(db, [{"row_id": one, "values": {"k": "K2"}, "source_name": "f9.csv"},
                {"row_id": two, "values": {"k": "K3"}, "source_name": "f9.csv"}], "tx-along")
    assert _rows(db) == {"K2": (one, "one"), "K3": (two, "two")}


def test_a_row_moved_onto_a_held_key_is_merged_into_the_holder(db):
    one, two = _two(db)
    answer = _write(db, [{"row_id": two, "values": {"k": "K1"}, "source_name": "f9.csv"}], "tx-merge")
    assert (_rows(db), answer["merged"]) == ({"K1": (one, "two")}, {two: one})
    ln = lines.shape(db, TABLE, CFG)["lines"]
    assert db.execute(select(ln.c.row_id).where(ln.c.row_id == two)).first() is None, "the shell's lines moved"
