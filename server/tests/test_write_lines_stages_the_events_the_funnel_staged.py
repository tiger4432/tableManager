# -*- coding: utf-8 -*-
"""write_lines stages the outbox events today's funnel staged (lead 11-10: the chain and the mappers read them) - one
event a write, in its transaction, the shapes the ORM flush hook gave (recorded 11-10 from crud.apply_batch_updates on
a sqlite dynamic table: create, an edit, the same again, another source's edit; per row and collapsed). One letter
differs: a new row's number reads back from its line - 2.0 where the hook's pending object held the cast 2."""
import contextlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import crud, lines, models
from database.context import outbox_mode
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import stand_in_winners

TABLE = "ob_rows"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "n": "string", "m": "number"}}
SAID = {"is_overwrite": False, "updated_by": "system"}


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    engine = create_engine("sqlite://")
    for model in (lines.LineColumn, lines.AuditBatch, models.DatabaseOutbox):
        model.__table__.create(engine)
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(lines, "winners_sql", stand_in_winners(lines.ensure_line_table(db, TABLE, CFG)), raising=False)
    db.commit()
    try:
        yield db
    finally:
        db.close()


def _events(db):
    rows = db.execute(select(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id)).scalars().all()
    out = [(r.event_type, {k: v for k, v in r.payload.items() if k not in ("timestamp", "transaction_id")})
           for r in rows]
    db.query(models.DatabaseOutbox).delete()
    db.commit()
    return out


def _write(db, source, **values):
    out = write_lines(db, TABLE, [{"key": {"k": values["k"]}, "values": values, "source_name": source,
                                   "written_by": "probe"}], kind="funnel", transaction_id="tx")
    db.commit()
    return out


def _four(db):
    said = []
    for source, values in (("f1", dict(k="A", n="x", m="2")), ("f1", dict(k="A", n="y", m="2")),
                           ("f1", dict(k="A", n="y", m="2")), ("f2", dict(k="A", n="z"))):
        with crud.transaction_context("probe", "tx", source):
            _write(db, source, **values)
        said.append(_events(db))
    return said


def test_per_row_events_are_today_s(db):
    create, edit, again, other = _four(db)
    [(kind, payload)] = create
    row_id = payload["row_id"]
    assert (kind, payload) == ("CREATE", {"row_id": row_id, "business_key": "A", "data": {
        "k": dict(SAID, value="A"), "n": dict(SAID, value="x"), "m": dict(SAID, value=2.0)},
        "updated_by": "probe", "source_name": "f1"})
    data = {"k": dict(SAID, value="A"), "n": dict(SAID, value="y"), "m": dict(SAID, value=2.0)}
    assert edit == [("EDIT", {"row_id": row_id, "business_key": "A", "data": data, "updated_by": "probe",
                              "source_name": "f1", "old": {"n": "x"}})]
    assert again == [], "a write that changes nothing stages nothing"
    assert other == [("EDIT", {"row_id": row_id, "business_key": "A", "data": dict(data, n=dict(SAID, value="z")),
                               "updated_by": "probe", "source_name": "f2", "old": {"n": "y"}})]


def test_collapsed_events_are_today_s(db):
    with outbox_mode("collapsed"):
        create, edit, again, other = _four(db)
    [(kind, payload)] = create
    [row_id] = payload["row_ids"]
    head = {"row_ids": [row_id], "row_count": 1, "table_name": TABLE, "updated_by": "probe"}
    assert (kind, payload) == ("CREATE", dict(head, columns=["business_key_val", "k", "m", "n", "row_id"],
                                              source_name="f1"))
    assert edit == [("EDIT", dict(head, columns=["n"], source_name="f1", old=[{"n": "x"}]))]
    assert again == []
    assert other == [("EDIT", dict(head, columns=["n"], source_name="f2", old=[{"n": "y"}]))]


def test_a_rolled_back_write_leaves_no_event(db):
    write_lines(db, TABLE, [{"key": {"k": "A"}, "values": {"k": "A", "n": "x"}, "source_name": "f1"}],
                kind="funnel", transaction_id="tx")
    db.rollback()
    assert db.execute(select(models.DatabaseOutbox)).scalars().all() == []


def test_a_line_that_changes_no_shown_value_stages_nothing(db):
    _write(db, "f1", k="A", n="x")
    _events(db)
    out = _write(db, "f2", k="A", n="x")
    assert out["lines"] == 1 and _events(db) == [], "another source saying what the cell shows is a line, not an edit"
