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
    one batch                      a swap, a key passed along: moved, nothing merged (QA 11-11)
    a declared key column          it shows the key - the next write does not take it back (QA 11-11)
    one key merged twice           two layers, one head line each (the tag names the whole merged row)
    this write's person cell       -                     the holder's cell marked a person's (the old pending mark)
    a table keyed by one column    its key column edited re-keys the row, a held key merges, a blank writes nothing
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
    return {s: h["value"] for s, h in (lines.layers(db, TABLE, [row_id], [column]).get((row_id, column)) or {}).items()}


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
    tag = "K2_%s" % shell
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
    assert "user (K2_%s)" % shell not in said, "the shell's person value is «user» there, not its moved copy"


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
    assert _sources(db, holder)["notation (K2_%s)" % shell] == "bare"


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


def _batch(db, moves, by="loader"):
    out = crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=row_id, updates={"k": key}, source_name="f9.csv", updated_by=by) for row_id, key in moves]))
    db.commit()
    return out


@pytest.mark.parametrize("order", [1, -1])
def test_two_rows_swapping_keys_in_one_batch_move(db, order):
    one, two = _two(db)
    _results, _cells, _logs, deleted = _batch(db, [(one, "K2"), (two, "K1")][::order])
    assert (_rows(db), deleted) == ({"K2": (one, "one"), "K1": (two, "two")}, [])


def test_keys_passed_along_in_one_batch_move(db):
    one, two = _two(db)
    _batch(db, [(one, "K2"), (two, "K3")])
    assert _rows(db) == {"K2": (one, "one"), "K3": (two, "two")}


def test_a_declared_key_column_shows_the_key_after_the_next_write(db_session, monkeypatch):
    table, cfg = "rk_bk", {"business_key": "bk", "composite_key_source": ["k"],
                           "column_types": {"bk": "string", "k": "string", "a": "string"}}
    models.init_dynamic_models({table: cfg})
    monkeypatch.setitem(crud.TABLE_CONFIG, table, cfg)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, table, cfg)
    db_session.commit()
    ticking_clock(monkeypatch)

    def write(values, row_id=None):
        crud.apply_batch_updates(db_session, table, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            row_id=row_id, business_key_val=None if row_id else values["k"], updates=values, source_name="f.csv",
            updated_by="loader")]))
        db_session.commit()

    model = models.DYNAMIC_TABLES[table]
    write({"bk": "K1", "k": "K1", "a": "one"})
    row = db_session.query(model).one().row_id
    write({"k": "K9"}, row_id=row)
    write({"a": "two"}, row_id=row)
    db_session.expire_all()
    got = db_session.query(model).filter_by(row_id=row).one()
    assert (got.business_key_val, got.bk, got.a) == ("K9", "K9", "two")


def test_one_key_merged_twice_into_a_holder_leaves_one_head_line_a_layer(db):
    holder, shell = _two(db)
    _write(db, "f3.csv", {"k": "K1"}, row_id=shell)
    _write(db, "f2.csv", {"k": "K2", "a": "again"})
    again = _rows(db)["K2"][0]
    _write(db, "f3.csv", {"k": "K1"}, row_id=again)
    said = _sources(db, holder)
    assert (said["f2.csv (K2_%s)" % shell], said["f2.csv (K2_%s)" % again]) == ("two", "again"), said
    ln = lines.shape(db, TABLE, CFG)["lines"]
    names = db.execute(select(ln.c.source_name).where(ln.c.row_id == holder, ln.c.head_0 != 0)).scalars().all()
    assert len(names) == len(set(names)), names


def test_this_writes_person_cell_is_the_holders_person_cell(db):
    holder, shell = _two(db)
    _write(db, crud.USER_SOURCE, {"k": "K1"}, row_id=shell, by="kim")
    mark = db.query(models.CellOverwrite).filter_by(table_name=TABLE, row_id=holder, column_name="k").one()
    assert (_rows(db), mark.is_overwrite, mark.manual_priority_source) == ({"K1": (holder, "two")}, True, None)


def test_a_moved_withdraw_line_does_not_empty_the_holders_cell(db):
    _write(db, "f1.csv", {"k": "K1"})
    _write(db, "f2.csv", {"k": "K2", "a": "two"})
    rows = _rows(db)
    holder, shell = rows["K1"][0], rows["K2"][0]
    model = models.DYNAMIC_TABLES[TABLE]
    db.query(model).filter_by(row_id=holder).update({"a": "kept"})      # a value no line said
    db.commit()
    crud.delete_cell_source_batch(db, TABLE, [{"row_id": shell, "column_name": "a"}], "f2.csv")
    assert _rows(db)["K2"] == (shell, None), "canary: the shell's a withdrawn"
    _write(db, "f3.csv", {"k": "K1"}, row_id=shell)
    assert _rows(db) == {"K1": (holder, "kept")}


@pytest.fixture(name="one_key")
def fixture_one_key(db_session, monkeypatch):
    table, cfg = "rk_one", {"business_key": "code", "column_types": {"code": "string", "a": "string"}}
    models.init_dynamic_models({table: cfg})
    monkeypatch.setitem(crud.TABLE_CONFIG, table, cfg)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, table, cfg)
    db_session.commit()
    ticking_clock(monkeypatch)

    def write(values, row_id=None):
        out = crud.apply_batch_updates(db_session, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(row_id=row_id, business_key_val=None if row_id else values["code"],
                                      updates=values, source_name="f.csv", updated_by="loader")]))
        db_session.commit()
        return out

    def rows():
        model = models.DYNAMIC_TABLES[table]
        db_session.expire_all()
        return {r.business_key_val: (r.row_id, r.code, r.a) for r in db_session.query(model)}

    write({"code": "C1", "a": "one"})
    write({"code": "C2", "a": "two"})
    return write, rows


def test_a_key_column_edited_re_keys_its_row(one_key):
    write, rows = one_key
    row = rows()["C2"][0]
    write({"code": "C9"}, row_id=row)
    assert rows()["C9"] == (row, "C9", "two")


def test_a_key_column_edited_onto_a_held_key_merges(one_key):
    write, rows = one_key
    holder, shell = rows()["C1"][0], rows()["C2"][0]
    _results, _cells, _logs, deleted = write({"code": "C1"}, row_id=shell)
    assert (rows(), deleted) == ({"C1": (holder, "C1", "two")}, [shell])


def test_a_key_column_written_blank_keeps_the_key(one_key):
    write, rows = one_key
    row = rows()["C2"][0]
    write({"code": None, "a": "x"}, row_id=row)
    assert rows()["C2"][0] == row
