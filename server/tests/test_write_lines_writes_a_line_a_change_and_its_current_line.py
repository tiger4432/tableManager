# -*- coding: utf-8 -*-
"""The cell-source overhaul's one write (docs/design/CELL_SOURCE_OVERHAUL.md «쓰기», A 11-10): a write is a line, the
same write again is none, a later line of one source takes the head, a withdraw takes a cell back (a NULL head too), a
deleted line keeps the key and the current line goes, one new key twice in a batch is one row, and the line's batch
and the audit row's transaction id are the transaction id as given (D 11-10). sqlite."""
import threading
import time

import pytest
from sqlalchemy import bindparam, create_engine, select, text
from sqlalchemy.orm import sessionmaker

import event_constants
from database import crud, lines, models
from database.write_lines import write_lines

TABLE = "wl_probe"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string", "n": "number"}}


def ticking_clock(monkeypatch):
    """sqlite's now() is a second: two writes in one second tie on `at` and the rank's last term (the source name)
    decides. PostgreSQL's is the transaction's start, so writes of separate transactions never tie. Each write here
    reads a clock one second on."""
    from datetime import datetime, timedelta, timezone

    ticks = iter(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=n) for n in range(10 ** 6))
    monkeypatch.setattr(crud, "batch_write_instant", lambda db: next(ticks))


def keep_lines(db, table, cfg):
    """t as a declared table is today - framework and declared columns, its business_key_val unique (the index
    write_lines' claim stands on: the runtime builds it, `index_wants`) - given its lines. -> the shape. The
    write_lines test files share it."""
    from sqlalchemy import Index, MetaData, Table, inspect

    for shared in (lines.LineSource, models.CellOverwrite):     # the rank's source names · the pins
        shared.__table__.create(db.connection(), checkfirst=True)
    if not inspect(db.connection()).has_table(table):
        t = Table(table, MetaData(), *lines._data_columns(cfg, models.sql_type_of, row_id_key=True))
        Index("uq_%s_bk" % table, t.c.business_key_val, unique=True)
        t.create(db.connection())
    return lines.ensure_line_table(db, table, cfg)


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    engine = create_engine("sqlite://")
    lines.LineColumn.__table__.create(engine)
    lines.AuditBatch.__table__.create(engine)
    models.DatabaseOutbox.__table__.create(engine)
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    db = sessionmaker(bind=engine)()
    keep_lines(db, TABLE, CFG)
    ticking_clock(monkeypatch)
    try:
        yield db
    finally:
        db.close()


def _lines(db):
    ln = lines.shape(db, TABLE, CFG)["lines"]
    return [dict(r) for r in db.execute(select(ln).order_by(ln.c.line_id)).mappings()]


def _now(db):
    now = lines.shape(db, TABLE, CFG)["table"]
    return {r["row_id"]: dict(r) for r in db.execute(select(now)).mappings()}


def _write(db, *items, kind="funnel", tx="tx1"):
    return write_lines(db, TABLE, list(items), kind=kind, transaction_id=tx)


def test_a_write_is_one_line_its_current_line_and_one_audit_row(db):
    out = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x", "n": "2"}, "source_name": "f1",
                      "written_by": "loader"})
    [line] = _lines(db)
    [(row_id, change)] = out["changed"].items()
    assert (line["line_kind"], line["row_id"], line["business_key_val"], line["a"], line["n"]) == (
        "write", row_id, "K1", "x", "2.0"), line
    assert _now(db)[row_id]["n"] == 2.0, "a line keeps text; the current line has the column's type (crud.line_value)"
    assert line["written_0"] == line["head_0"] != 0 and line["withdrawn_0"] == 0
    assert change["work"] == "new" and change["old"] is None and change["new"]["a"] == "x" and change["new"]["n"] == 2.0
    assert _now(db)[row_id]["a"] == "x" and _now(db)[row_id]["won_by"]["a"] == line["line_id"]
    audit = db.execute(select(lines.AuditBatch.__table__)).mappings().all()
    assert [(a["transaction_id"], a["table_name"], a["written_by"], a["work_kind"]) for a in audit] == [
        ("tx1", TABLE, "loader", "new")]


def test_the_same_write_again_writes_nothing(db):
    item = {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x", "n": 2}, "source_name": "f1", "written_by": "loader"}
    _write(db, item)
    out = _write(db, dict(item, values={"k": "K1", "a": "x", "n": "2.0"}), tx="tx2")
    assert (out["lines"], out["left_out"], out["changed"]) == (0, 1, {}), out
    assert len(_lines(db)) == 1


@pytest.mark.parametrize("again", [{"written_by": "kim"}, {"input_row": "r9"}])
def test_the_same_value_from_another_hand_or_input_row_is_a_new_statement(db, again):
    item = {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1", "written_by": "loader",
            "input_row": "r1"}
    _write(db, item)
    out = _write(db, dict(item, **again), tx="tx2")
    assert (out["lines"], out["left_out"]) == (1, 0), out


def test_a_column_that_says_what_its_source_said_is_not_written_again(db):
    item = {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x", "n": 2}, "source_name": "f1"}
    _write(db, item)
    _write(db, dict(item, values={"k": "K1", "a": "y", "n": "2.0"}), tx="tx2")
    first, second = _lines(db)
    bits = lines.shape(db, TABLE, CFG)["bits"]
    assert second["written_0"] == 1 << bits["a"], "only the column that changed is written"
    assert first["head_0"] == (1 << bits["k"]) | (1 << bits["n"]) and second["n"] is None, (first, second)


def test_a_later_line_of_one_source_takes_the_head(db):
    first = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})
    [row_id] = first["changed"]
    out = _write(db, {"row_id": row_id, "values": {"a": "y"}, "source_name": "f1"}, tx="tx2")
    old, new = _lines(db)
    bit_a = 1 << lines.shape(db, TABLE, CFG)["bits"]["a"]
    assert not old["head_0"] & bit_a and new["head_0"] & bit_a, (old, new)
    assert old["head_0"] & (1 << lines.shape(db, TABLE, CFG)["bits"]["k"]), "k is still the first line's"
    assert out["changed"][row_id]["work"] == "edit" and _now(db)[row_id]["a"] == "y"


def test_a_withdraw_takes_the_cell_back_even_a_null_head(db):
    first = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": None}, "source_name": "f1"})
    [row_id] = first["changed"]
    out = _write(db, {"row_id": row_id, "line_kind": "withdraw", "columns": ["a"], "source_name": "f1"},
                 kind="withdraw", tx="tx2")
    line = _lines(db)[-1]
    bit_a = 1 << lines.shape(db, TABLE, CFG)["bits"]["a"]
    assert line["line_kind"] == "withdraw" and line["withdrawn_0"] == bit_a == line["head_0"], line
    assert out["changed"][row_id]["work"] == "withdraw" and _now(db)[row_id]["won_by"].get("a") is None


def test_a_withdraw_of_a_cell_its_source_does_not_speak_is_left_out(db):
    first = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})
    [row_id] = first["changed"]
    out = _write(db, {"row_id": row_id, "line_kind": "withdraw", "columns": ["a"], "source_name": "f2"},
                 {"row_id": "gone", "line_kind": "withdraw", "columns": ["a"], "source_name": "f1"}, tx="tx2")
    assert (out["lines"], out["left_out"]) == (0, 1), out
    assert len(_lines(db)) == 1


def test_a_deleted_line_keeps_the_key_and_the_current_line_goes(db):
    first = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})
    [row_id] = first["changed"]
    out = _write(db, {"row_id": row_id, "line_kind": "deleted", "source_name": "user", "written_by": "kim"},
                 kind="delete", tx="tx2")
    line = _lines(db)[-1]
    assert (line["line_kind"], line["business_key_val"], line["head_0"], line["written_0"]) == ("deleted", "K1", 0, 0)
    change = out["changed"][row_id]
    assert row_id not in _now(db) and change["new"] is None and change["work"] == "delete" and change["old"]["a"] == "x"


def test_one_new_key_twice_in_a_batch_is_one_row(db):
    out = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"},
                 {"key": {"k": "K1"}, "values": {"k": "K1", "a": "y"}, "source_name": "f1"})
    assert len(_now(db)) == 1 and len(out["changed"]) == 1
    [row_id] = out["changed"]
    assert _now(db)[row_id]["a"] == "y", "the later line of one source on one cell wins"


def test_the_batch_and_the_audit_transaction_are_the_transaction_id_as_given(db):
    tx = "replay-7" + event_constants.GROUP_PART + "3"
    _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"}, tx=tx)
    assert _lines(db)[0]["batch"] == tx
    assert db.execute(select(lines.AuditBatch.__table__.c.transaction_id)).scalar() == tx


def test_the_answer_says_each_audit_row_and_the_distinct_rows_it_wrote(db):
    _write(db, {"key": {"k": "K0"}, "values": {"k": "K0", "a": "x"}, "source_name": "f1", "written_by": "loader"})
    out = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1", "written_by": "loader"},
                 {"key": {"k": "K1"}, "values": {"k": "K1", "a": "y"}, "source_name": "f1", "written_by": "loader"},
                 {"key": {"k": "K2"}, "values": {"k": "K2", "a": "x"}, "source_name": "f1", "written_by": "loader"},
                 {"key": {"k": "K0"}, "values": {"k": "K0", "a": "x"}, "source_name": "f1", "written_by": "loader"},
                 {"key": {"k": "K0"}, "values": {"a": "z"}, "source_name": "user", "written_by": "kim"}, tx="tx2")
    assert out["left_out"] == 1 and out["audit"] == [
        {"transaction_id": "tx2", "table_name": TABLE, "changed_rows": 1, "kind": "edit", "written_by": "kim"},
        {"transaction_id": "tx2", "table_name": TABLE, "changed_rows": 2, "kind": "new", "written_by": "loader"}]
    rows = db.execute(select(lines.AuditBatch.__table__).where(lines.AuditBatch.transaction_id == "tx2")).mappings()
    assert sorted((a["work_kind"], a["written_by"]) for a in rows) == [(a["kind"], a["written_by"]) for a in out["audit"]]


def test_a_write_the_database_gives_no_time_for_is_refused(db, monkeypatch):
    monkeypatch.setattr(crud, "batch_write_instant", lambda _db: None)
    with pytest.raises(RuntimeError, match="gave no time"):
        _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})
    assert _lines(db) == [] and _now(db) == {}


def test_two_sqlite_writers_of_one_row_wait_for_the_write_lock_before_they_read(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "wl.db"), connect_args={"check_same_thread": False})
    lines.LineColumn.__table__.create(engine)
    lines.AuditBatch.__table__.create(engine)
    models.DatabaseOutbox.__table__.create(engine)
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    make = sessionmaker(bind=engine)
    setup = make()
    keep_lines(setup, TABLE, CFG)
    ticking_clock(monkeypatch)
    [row_id] = _write(setup, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "0"}, "source_name": "f0"})["changed"]
    setup.commit()
    setup.close()
    first, second, got = make(), make(), {}

    def run():
        try:
            got["answer"] = _write(second, {"row_id": row_id, "values": {"a": "2"}, "source_name": "f2"}, tx="tx3")
            second.commit()
        except Exception as exc:                  # noqa: BLE001 - the test says what the second writer met
            got["error"] = exc
            second.rollback()

    try:
        _write(first, {"row_id": row_id, "values": {"a": "1"}, "source_name": "f1"}, tx="tx2")
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
        engine.dispose()
    assert still and "error" not in got, got.get("error")
    assert got["answer"]["changed"][row_id]["old"]["a"] == "1", "the second read the row before the first let it go"


def test_a_version_gated_table_takes_a_newer_version_and_refuses_an_older_one_after_the_lock(db, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(CFG, version_column="n"))
    [row_id] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x", "n": 2}, "source_name": "f1"})["changed"]
    older = _write(db, {"row_id": row_id, "values": {"a": "old", "n": 1}, "source_name": "f2"}, tx="tx2")
    by_hand = _write(db, {"row_id": row_id, "values": {"a": "kim"}, "source_name": "user"}, tx="tx3")
    newer = _write(db, {"row_id": row_id, "values": {"a": "new", "n": 3}, "source_name": "f2"}, tx="tx4")
    assert (older["lines"], older["gated"]) == (0, {crud.REASON_VERSION_OLDER: 1}), older
    assert (by_hand["lines"], by_hand["gated"]) == (1, {}), "a person's correction is not version-ordered"
    assert (newer["lines"], _lines(db)[-1]["a"]) == (1, "new"), newer


def test_the_answer_says_each_item_s_row_work_and_columns_in_the_items_order(db, monkeypatch):
    """A caller resolves its own items by `items` (a map's claimed rows, a dropped cell's row): a row that changed
    nothing is still its row - "left_out", not absent."""
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(CFG, version_column="n"))
    [a] = _write(db, {"key": {"k": "A"}, "values": {"k": "A", "a": "x", "n": 2}, "source_name": "f1"})["changed"]
    out = _write(db, {"row_id": a, "line_kind": "withdraw", "columns": ["a"], "source_name": "f9"},
                 {"key": {"k": "B"}, "values": {"k": "B", "a": "y"}, "source_name": "f1"},
                 {"row_id": a, "values": {"a": "old", "n": 1}, "source_name": "f2"},
                 {"row_id": "gone", "line_kind": "withdraw", "columns": ["a"], "source_name": "f1"},
                 {"row_id": a, "values": {"k": "A", "a": "z", "n": 3}, "source_name": "f1"}, tx="tx2")
    [b] = [row_id for row_id, change in out["changed"].items() if change["work"] == "new"]
    assert out["items"] == [{"row_id": a, "work": "left_out", "columns": []},
                            {"row_id": b, "work": "new", "columns": ["a", "k"]},
                            {"row_id": a, "work": "gated", "columns": ["a", "n"]},
                            {"row_id": None, "work": None, "columns": ["a"]},
                            {"row_id": a, "work": "edit", "columns": ["a", "n"]}], out["items"]


def test_a_column_no_line_has_written_keeps_t_s_value_and_one_withdrawn_to_nothing_empties(db):
    """t is what it was until written (owner 11-11 «옛날 거 끊어»): a row from before the landing written in one column
    keeps its other columns as they were, with no won_by for them; a column whose every line is withdrawn empties."""
    t = lines.shape(db, TABLE, CFG)["table"]
    db.execute(t.insert().values(row_id="old", business_key_val="K0", k="K0", a="before", n=7.0))
    out = _write(db, {"row_id": "old", "values": {"n": "8"}, "source_name": "f1"})
    row = _now(db)["old"]
    assert (out["changed"]["old"]["work"], row["a"], row["n"], set(row["won_by"])) == ("edit", "before", 8, {"n"}), row
    _write(db, {"row_id": "old", "line_kind": "withdraw", "columns": ["n"], "source_name": "f1"}, tx="tx2")
    row = _now(db)["old"]
    assert (row["a"], row["n"], row["won_by"]) == ("before", None, {}), row


def test_a_write_of_nothing_makes_no_row_and_names_one_that_is_there(db):
    """The funnel's phantom-row guard: an item whose every cell was dropped writes nothing - a new key or id gets no
    row (no row, no event), a row that is there is still its row (left out), so the funnel can say what it dropped."""
    [row_id] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})["changed"]
    out = _write(db, {"key": {"k": "K9"}, "values": {}, "source_name": "f1"},
                 {"row_id": "never", "values": {}, "source_name": "f1"},
                 {"key": {"k": "K1"}, "values": {}, "source_name": "f1"}, tx="tx2")
    assert [(it["row_id"], it["work"]) for it in out["items"]] == [(None, None), (None, None), (row_id, "left_out")]
    assert set(_now(db)) == {row_id} and out["changed"] == {}


def test_a_persons_write_marks_its_cell_and_takes_the_pin_off_and_a_pin_holds_the_merge(db):
    """Pins stay in cell_overwrites this landing (lead 11-11): a machine write leaves no mark; a person's write marks
    the cell and takes its pin off, the same value again included; a pin makes its source's head line the cell's
    value, and a pin whose source has no head line leaves t's value (C's lines.merge)."""
    ov = models.CellOverwrite.__table__

    def mark():
        return [tuple(r) for r in db.execute(select(ov.c.is_overwrite, ov.c.updated_by, ov.c.manual_priority_source))]

    def pin(source):
        db.execute(ov.update().values(manual_priority_source=source))

    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})["changed"]
    assert mark() == [] and _now(db)[r]["a"] == "x", "a machine write marks nothing"
    _write(db, {"row_id": r, "values": {"a": "kim"}, "source_name": "user", "written_by": "kim"}, tx="tx2")
    assert mark() == [(True, "kim", None)] and _now(db)[r]["a"] == "kim"
    pin("f1")
    _write(db, {"row_id": r, "values": {"a": "y"}, "source_name": "f2", "written_by": "loader"}, tx="tx3")
    assert mark() == [(True, "loader", "f1")] and _now(db)[r]["a"] == "x", "the pin holds f1's line over the others"
    _write(db, {"row_id": r, "values": {"a": "kim"}, "source_name": "user", "written_by": "kim"}, tx="tx4")
    assert mark() == [(True, "kim", None)] and _now(db)[r]["a"] == "kim", "the same value again takes the pin off"
    pin("f9")
    _write(db, {"row_id": r, "values": {"a": "z"}, "source_name": "f1", "written_by": "loader"}, tx="tx5")
    assert _now(db)[r]["a"] == "kim", "a pin whose source has no head line leaves t's value"
