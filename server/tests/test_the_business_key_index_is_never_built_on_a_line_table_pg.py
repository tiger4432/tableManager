# -*- coding: utf-8 -*-
"""The business key unique index is t's, never t__lines' (lead 11-12, D's first boot on the migrated copy): every
line of a keyed row carries the row's key, so a UNIQUE (business_key_val) on t__lines refuses the row's second write.
The start's picker leaves line tables out (lines.is_line_table), and one built before is dropped at the start, said."""
import logging

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import crud, lines, models
from database.write_lines import write_lines
from migrations import add_business_key_unique_index as uq
from test_write_lines_writes_a_line_a_change_and_its_current_line import keep_lines

pytestmark = pytest.mark.pg

TABLE = "wl_bk_lines_pg"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="db")
def fixture_db(pg_engine, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource, models.DatabaseOutbox, models.CellOverwrite):
        model.__table__.create(pg_engine, checkfirst=True)
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


def _write(db, a, tx):
    write_lines(db, TABLE, [{"key": {"k": "K1"}, "values": {"k": "K1", "a": a}, "source_name": "f1.csv"}],
                kind="funnel", transaction_id=tx)
    db.commit()


def _indexes(db):
    return set(db.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
                               "AND tablename = :t"), {"t": lines.lines_relation(TABLE)}).scalars())


def _live(db, by, a, tx):
    """A live write of the row: by its key (a file) or by its row_id (the chain)."""
    if by == "key":
        _write(db, a, tx)
        return
    row_id = db.execute(text('SELECT row_id FROM "%s"' % TABLE)).scalar()
    write_lines(db, TABLE, [{"row_id": row_id, "values": {"a": a}, "source_name": "chain"}], kind="funnel",
                transaction_id=tx)
    db.commit()


@pytest.mark.parametrize("first, second", [("row_id", "row_id"), ("key", "key"), ("row_id", "key"),
                                           ("key", "row_id")])
def test_a_migrated_keyed_rows_second_live_write_goes_after_the_start_built_the_key_indexes(db, pg_engine, first,
                                                                                            second):
    """D's after-board 11-12: the migrated lines carry no key (copy_page), the start's picker built the key index on
    t__lines too, a row's first live write stamped its key on one line, its second live write met that index."""
    from chain import ingestion_worker

    _write(db, "seed", "tx-seed")
    db.execute(text('UPDATE "%s" SET business_key_val = NULL' % lines.lines_relation(TABLE)))   # as copy_page left them
    db.commit()
    ingestion_worker._ensure_business_key_unique_indexes_sync(sessionmaker(bind=pg_engine))
    _live(db, first, "one", "tx-1")
    _live(db, second, "two", "tx-2")                # refused by uq_bk_<t>__lines while the picker took line tables
    assert db.execute(text('SELECT a FROM "%s"' % TABLE)).scalars().all() == ["two"]
    assert uq.unique_index_name(lines.lines_relation(TABLE)) not in _indexes(db)


def test_a_key_index_built_on_a_line_table_before_is_dropped_at_the_start_and_said(db, pg_engine, caplog):
    caplog.set_level(logging.INFO, logger=lines.__name__)
    name = uq.unique_index_name(lines.lines_relation(TABLE))
    db.execute(text('CREATE UNIQUE INDEX "%s" ON "%s" (business_key_val)' % (name, lines.lines_relation(TABLE))))
    db.commit()
    assert lines.ensure_declared(pg_engine, tables=[TABLE]) == {}
    assert name not in _indexes(db)
    assert any(name in r.getMessage() and "dropped" in r.getMessage() for r in caplog.records)
    _write(db, "one", "tx-1")
    _write(db, "two", "tx-2")
