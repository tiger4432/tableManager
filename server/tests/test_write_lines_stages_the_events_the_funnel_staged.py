# -*- coding: utf-8 -*-
"""write_lines stages the outbox events today's funnel staged (lead 11-10: the chain and the mappers read them) - one
event a write, in its transaction, the shapes the ORM flush hook gave (recorded 11-10 from crud.apply_batch_updates on
a sqlite dynamic table: create, an edit, the same again, another source's edit; per row and collapsed), compared as
JSON letters. One differs, by ruling: a whole number reads back from its line as 2 (crud.line_value, lead 11-11) -
the hook's CREATE held the cast 2 and its EDIT read 2.0 back from the Float column; now both are 2."""
import json

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from database import crud, lines, models
from database.context import outbox_mode
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import keep_lines, ticking_clock

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
    keep_lines(db, TABLE, CFG)
    ticking_clock(monkeypatch)
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


def _text(events):
    """Events as their JSON letters - 2 and 2.0 are equal in Python and two spellings on the wire."""
    return json.dumps(events, sort_keys=True)


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
    assert _text(create) == _text([("CREATE", {"row_id": row_id, "business_key": "A", "data": {
        "k": dict(SAID, value="A"), "n": dict(SAID, value="x"), "m": dict(SAID, value=2)},
        "updated_by": "probe", "source_name": "f1"})])
    data = {"k": dict(SAID, value="A"), "n": dict(SAID, value="y"), "m": dict(SAID, value=2)}
    assert _text(edit) == _text([("EDIT", {"row_id": row_id, "business_key": "A", "data": data, "updated_by": "probe",
                                           "source_name": "f1", "old": {"n": "x"}})])
    assert again == [], "a write that changes nothing stages nothing"
    assert _text(other) == _text([("EDIT", {"row_id": row_id, "business_key": "A",
                                            "data": dict(data, n=dict(SAID, value="z")), "updated_by": "probe",
                                            "source_name": "f2", "old": {"n": "y"}})])


def test_collapsed_events_are_today_s(db):
    with outbox_mode("collapsed"):
        create, edit, again, other = _four(db)
    [(kind, payload)] = create
    [row_id] = payload["row_ids"]
    head = {"row_ids": [row_id], "row_count": 1, "table_name": TABLE, "updated_by": "probe"}
    assert _text(create) == _text([("CREATE", dict(head, columns=["business_key_val", "k", "m", "n", "row_id"],
                                                   source_name="f1"))])
    assert _text(edit) == _text([("EDIT", dict(head, columns=["n"], source_name="f1", old=[{"n": "x"}]))])
    assert again == []
    assert _text(other) == _text([("EDIT", dict(head, columns=["n"], source_name="f2", old=[{"n": "y"}]))])


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


def test_a_time_column_stored_as_text_carries_its_text_as_written(db, monkeypatch):
    """Box shape (lot_event.event_time): declared datetime, stored as text - the text a write kept is what its events
    carry, as today, and a mapper's key built from it stays one key (lead 11-11). t's physical type answers
    (lines.value_types), not the declaration."""
    table, written = "ob_text_time", "2026-01-01T13:00:00"
    cfg = {"composite_key_source": ["k"], "column_types": {"k": "string", "n": "string", "t": "string"}}
    monkeypatch.setitem(crud.TABLE_CONFIG, table, cfg)
    keep_lines(db, table, cfg)
    db.commit()
    monkeypatch.setitem(crud.TABLE_CONFIG, table, dict(cfg, column_types=dict(cfg["column_types"], t="datetime")))
    for values in ({"k": "A", "n": "x", "t": written}, {"k": "A", "n": "y"}):
        write_lines(db, table, [{"key": {"k": "A"}, "values": values, "source_name": "f1"}], kind="funnel",
                    transaction_id="tx")
        db.commit()
    create, edit = (row.payload["data"]["t"]["value"] for row in db.execute(
        select(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id)).scalars())
    assert (create, edit) == (written, written), (create, edit)
    held = db.execute(text("SELECT t FROM ob_text_time")).scalar_one()
    assert held == written, "t holds the text as written, not a time spelled again"


def test_a_column_of_no_history_changes_t_and_its_event_with_no_line_and_no_audit(db, monkeypatch):
    """no_history_columns (lead 11-11 ㄴ): a state cell written every few seconds leaves no line - t changes, the event
    says it as today, the audit has no row for it; the same write's other column is a line as ever."""
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(CFG, no_history_columns=["n"]))
    ln = lines.shape(db, TABLE, CFG)["lines"]
    out = _write(db, "f1", k="A", n="busy")
    _events(db)
    [row_id] = out["changed"]
    n = ln.c[lines.value_column("n")]
    lined = db.execute(select(n).where(ln.c.row_id == row_id)).scalars().all()
    with crud.transaction_context("probe", "tx", "f1"):
        again = _write(db, "f1", k="A", n="idle")
    assert (again["items"][0]["work"], again["lines"], again["audit"]) == ("edit", 0, []), again
    assert _text(_events(db)) == _text([("EDIT", {"row_id": row_id, "business_key": "A", "data": {
        "k": dict(SAID, value="A"), "n": dict(SAID, value="idle"), "m": dict(SAID, value=None)},
        "updated_by": "probe", "source_name": "f1", "old": {"n": "busy"}})])
    same = _write(db, "f1", k="A", n="idle")
    assert (same["items"][0]["work"], _events(db)) == ("left_out", []), "the same state again moves nothing"
    both = _write(db, "f2", k="A", n="off", m="3")
    t = lines.shape(db, TABLE, CFG)["table"]
    now = db.execute(select(t.c.n, t.c.m, t.c.won_by)).one()
    assert (both["lines"], now.n, now.m, set(now.won_by)) == (1, "off", 3, {"k", "m"}), (both, now)
    assert lined == [None] and db.execute(select(n).where(n.is_not(None))).scalars().all() == [], \
        "no line ever holds the column"
