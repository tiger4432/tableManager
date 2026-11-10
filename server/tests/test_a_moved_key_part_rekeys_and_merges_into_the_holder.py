# -*- coding: utf-8 -*-
"""A write that moves a key part's shown value rebuilds the row's key, and a row whose new key another row holds is
merged into it - write_lines' step 5½, every writer (lead 11-11: a test a caller - the funnel, the pin,
merge_into_key_holders). Which value wins is the old merge's; the holder is merged again and a cell whose shown value
moved is an EDIT event like any write (lead 11-11 ㄱ).

    door                           key free              key held
    funnel (a row named by id)     re-keyed in place     merged: the shell's newer value shows, EDIT + DELETE
    a person on both rows          -                     the shell's «user» shows, the holder's kept as old_exist
    the holder's newer line        -                     the shell's value, held by the merge's pin
    a shell value no line said     -                     kept as a line of the writer's
    the holder's person value      -                     kept - unless the write named that cell
    pin                            -                     merged: the holder is the row answered, the shell gone
    merge_into_key_holders         -                     merged, one «merge» audit row
    a table without lines          re-keyed in place     merged, the shell's value on t
"""
import json

import pytest
from sqlalchemy import select

from database import crud, lines, models, schemas
from database.database import Base
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE = "rk_line"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


def _fixture(db, monkeypatch, with_lines=True):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db.get_bind())
    if with_lines:
        lines.ensure_line_table(db, TABLE, CFG)
    db.commit()
    ticking_clock(monkeypatch)
    return db


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    return _fixture(db_session, monkeypatch)


def _write(db, source, values, row_id=None, by="loader"):
    out = crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=row_id, business_key_val=None if row_id else values["k"], updates=values, source_name=source,
        updated_by=by)]))
    db.commit()
    return out


def _rows(db):
    model = models.DYNAMIC_TABLES[TABLE]
    db.expire_all()
    return {r.business_key_val: (r.row_id, r.a) for r in db.query(model)}


def _events(db):
    rows = db.execute(select(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id)).scalars().all()
    out = [(r.event_type, json.dumps(r.payload, sort_keys=True)) for r in rows if r.table_name == TABLE]
    db.query(models.DatabaseOutbox).delete()
    db.commit()
    return out


def _sources(db, row_id, column="a"):
    from admin.audit_history import head_lines
    return {s: h["value"] for s, h in (head_lines(db, TABLE, [row_id], [column]).get((row_id, column)) or {}).items()}


def _two(db):
    _write(db, "f1.csv", {"k": "K1", "a": "one"})
    _write(db, "f2.csv", {"k": "K2", "a": "two"})
    rows = _rows(db)
    assert set(rows) == {"K1", "K2"}, "canary: two rows"
    return rows["K1"][0], rows["K2"][0]


def test_a_key_part_edited_re_keys_the_row_in_place(db):
    holder, shell = _two(db)
    _write(db, "f3.csv", {"k": "K9"}, row_id=shell)
    assert _rows(db) == {"K1": (holder, "one"), "K9": (shell, "two")}


def test_a_key_part_edited_onto_a_held_key_merges_the_row_into_the_holder(db):
    holder, shell = _two(db)
    _events(db)
    results, _cells, _logs, deleted = _write(db, "f3.csv", {"k": "K1"}, row_id=shell)
    assert (_rows(db), deleted, [row.row_id for row, _new in results]) == ({"K1": (holder, "two")}, [shell], [holder])
    tag = "K2_%s" % shell[:6]
    assert _sources(db, holder) == {"f1.csv": "one", "f2.csv (%s)" % tag: "two", crud.COLLISION_SOURCE: "two"}
    events = _events(db)
    edits = [e for e in events if e[0] == "EDIT" and holder in e[1] and '"a"' in e[1]]
    assert (len(edits), [e[0] for e in events if shell in e[1]]) == (1, ["DELETE"]), events
    assert db.query(models.CellOverwrite).filter_by(table_name=TABLE, row_id=shell).count() == 0


def test_the_holders_person_value_is_kept(db):
    holder, shell = _two(db)
    _write(db, crud.USER_SOURCE, {"k": "K1", "a": "mine"}, by="kim")
    assert _rows(db)["K1"] == (holder, "mine"), "canary: a person's value shows"
    _write(db, "f3.csv", {"k": "K1"}, row_id=shell)
    assert _rows(db) == {"K1": (holder, "mine")}


def test_a_value_the_write_named_wins_over_the_holders_person_value(db):
    holder, shell = _two(db)
    _write(db, crud.USER_SOURCE, {"k": "K1", "a": "mine"}, by="kim")
    _write(db, "f3.csv", {"k": "K1", "a": "named"}, row_id=shell, by="system")
    assert _rows(db) == {"K1": (holder, "named")}, "the merge's choice over a person's line, held by its pin"


def test_a_person_on_both_rows_shows_the_shells_and_keeps_the_holders(db):
    holder, shell = _two(db)
    _write(db, crud.USER_SOURCE, {"k": "K1", "a": "mine"}, by="kim")
    _write(db, crud.USER_SOURCE, {"k": "K2", "a": "yours"}, by="lee")
    _write(db, crud.USER_SOURCE, {"k": "K1"}, row_id=shell, by="lee")
    assert _rows(db) == {"K1": (holder, "yours")}
    said = _sources(db, holder)
    assert (said[crud.USER_SOURCE], said["user (old_exist_%s)" % holder[:6]]) == ("yours", "mine"), said
    assert "user (K2_%s)" % shell[:6] not in said, "the shell's person value is «user» there, not its moved copy"


def test_the_shells_value_wins_though_the_holders_line_is_newer(db):
    _write(db, "f2.csv", {"k": "K2", "a": "two"})
    _write(db, "f1.csv", {"k": "K1", "a": "one"})                  # the holder's line is the newer
    rows = _rows(db)
    holder, shell = rows["K1"][0], rows["K2"][0]
    _write(db, "f3.csv", {"k": "K1"}, row_id=shell)
    assert _rows(db) == {"K1": (holder, "two")}, "the merge's choice, held by its pin"


def test_a_shell_value_no_line_said_is_kept_as_the_writers_line(db):
    _write(db, "f1.csv", {"k": "K1", "a": "one"})
    _write(db, "f2.csv", {"k": "K2"})
    rows = _rows(db)
    holder, shell = rows["K1"][0], rows["K2"][0]
    model = models.DYNAMIC_TABLES[TABLE]
    db.query(model).filter_by(row_id=shell).update({"a": "bare"})   # a value t holds that no line said
    db.commit()
    crud.merge_into_key_holders(db, TABLE, [(shell, holder)], source_name="notation", updated_by="op",
                                transaction_id="tx-bare")
    db.commit()
    assert _rows(db) == {"K1": (holder, "bare")}
    assert _sources(db, holder)["notation (K2_%s)" % shell[:6]] == "bare"


def test_a_pin_onto_a_held_key_merges_its_row_into_the_holder(db):
    _write(db, "f2.csv", {"k": "K2", "a": "two"})
    shell = _rows(db)["K2"][0]
    _write(db, "f4.csv", {"k": "K4"}, row_id=shell)                # the newer file shows K4 - the key moves
    _write(db, "f1.csv", {"k": "K2", "a": "one"})                  # K2 is free: a new row holds it
    holder = _rows(db)["K2"][0]
    assert holder != shell and _rows(db)["K4"][0] == shell, "canary: two rows, the shell keyed K4"
    rows, _logs, gone = crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": shell, "column_name": "k"}],
                                                            "f2.csv", "lee")
    assert ([r.row_id for r in rows], gone, _rows(db)) == ([holder], [shell], {"K2": (holder, "two")})


def test_merge_into_key_holders_merges_and_writes_one_merge_audit_row(db):
    holder, shell = _two(db)
    merged = crud.merge_into_key_holders(db, TABLE, [(shell, holder)], source_name="notation", updated_by="op",
                                         transaction_id="tx-merge")
    db.commit()
    assert (merged, _rows(db)) == ([shell], {"K1": (holder, "two")})
    kinds = db.execute(select(lines.AuditBatch.work_kind, lines.AuditBatch.written_by)
                       .where(lines.AuditBatch.transaction_id == "tx-merge")).all()
    assert kinds == [("merge", "op")]


def test_a_table_without_lines_re_keys_and_merges_on_t(db_session, monkeypatch):
    db = _fixture(db_session, monkeypatch, with_lines=False)
    holder, shell = _two(db)
    _write(db, "f3.csv", {"k": "K9"}, row_id=shell)
    assert _rows(db) == {"K1": (holder, "one"), "K9": (shell, "two")}
    _results, _cells, _logs, deleted = _write(db, "f3.csv", {"k": "K1"}, row_id=shell)
    assert (_rows(db), deleted) == ({"K1": (holder, "two")}, [shell])
