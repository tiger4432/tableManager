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
    assert (line["line_kind"], line["row_id"], line["business_key_val"], line[lines.value_column("a")], line[lines.value_column("n")]) == (
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
    assert first["head_0"] == (1 << bits["k"]) | (1 << bits["n"]) and second[lines.value_column("n")] is None, (first, second)


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


def test_a_delete_on_a_table_without_lines_takes_the_row_out_with_no_line(db, monkeypatch):
    """A table that keeps no lines (shipped, or one ensure refused - lead 11-11 2) still loses the row a delete names;
    nothing is written as its history there."""
    from sqlalchemy import Index, MetaData, Table, insert, inspect

    name = "wl_bare"
    monkeypatch.setitem(crud.TABLE_CONFIG, name, CFG)
    t = Table(name, MetaData(), *lines._data_columns(CFG, models.sql_type_of, row_id_key=True))
    Index("uq_%s_bk" % name, t.c.business_key_val, unique=True)
    t.create(db.connection())
    db.execute(insert(t).values(row_id="r1", business_key_val="K1", k="K1", a="x"))
    assert not lines.has_lines(db, name)
    out = write_lines(db, name, [{"row_id": "r1", "line_kind": "deleted", "written_by": "kim"}], kind="delete",
                      transaction_id="tx-d")
    assert (out["lines"], out["items"][0]["work"], out["items"][0]["line_id"]) == (0, "delete", None), out
    assert db.execute(t.select()).all() == [] and not inspect(db.connection()).has_table(name + "__lines")


def test_a_created_line_makes_a_row_with_no_value_and_an_existing_row_is_not_made_again(db):
    """The grid's «add row» (C 11-11, the pair of «deleted»): a «created» line, its three bit words 0, work "new", the
    row's CREATE event; an item naming a row already there makes nothing."""
    out = _write(db, {"line_kind": "created", "written_by": "kim"}, kind="create")
    [said] = out["items"]
    [line] = _lines(db)
    assert (said["work"], line["line_kind"], line["written_0"], line["head_0"], line["withdrawn_0"], line["row_id"]) == (
        "new", "created", 0, 0, 0, said["row_id"]), (said, line)
    assert said["row_id"] in _now(db) and [a["kind"] for a in out["audit"]] == ["new"]
    again = _write(db, {"row_id": said["row_id"], "line_kind": "created", "written_by": "kim"}, kind="create", tx="tx2")
    assert (again["items"][0]["work"], again["lines"], len(_lines(db))) == (None, 0, 1), again


def test_a_created_item_with_a_key_makes_that_keys_row_or_names_the_row_holding_it(db):
    """Lead 11-11 (an item sent with updates={} - the funnel's «created»): a key nobody holds makes its row, keyed; a key
    a row holds names that row and makes nothing - no second row, no «created» line (the old _get_or_create_row)."""
    out = _write(db, {"business_key_val": "K9", "line_kind": "created", "written_by": "kim"}, kind="funnel")
    [said] = out["items"]
    assert (_now(db)[said["row_id"]]["business_key_val"], said["work"], [l["line_kind"] for l in _lines(db)]) == (
        "K9", "new", ["created"]), out
    again = _write(db, {"business_key_val": "K9", "line_kind": "created", "written_by": "kim"}, kind="funnel", tx="tx2")
    assert (again["items"][0]["row_id"], again["lines"], len(_now(db)), len(_lines(db))) == (said["row_id"], 0, 1, 1), again


def test_a_column_of_no_history_shows_the_batch_s_last_word(db, monkeypatch):
    """QA 11-11: [n=3, n=5] on a row at 5 - each item meets the row its earlier items left (`_version_gate`'s
    `before`), so 5 shows; on the batch's first state both items «moved» and 3 was the merge's."""
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(CFG, no_history_columns=["n"]))
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x", "n": "5"}, "source_name": "f1"})["changed"]
    _write(db, {"row_id": r, "values": {"n": "3"}, "source_name": "f1"},
           {"row_id": r, "values": {"n": "5"}, "source_name": "f1"}, tx="tx2")
    assert _now(db)[r]["n"] == 5.0


def test_at_one_instant_step_two_asks_the_later_line_as_the_merge_shows_it(db, monkeypatch):
    """B 11-11: a.csv says x, then b.csv says y, at one instant - the cell shows y (rank 2c, the later line). A chain's
    new layer of x is then no repeat of what the cell shows and is written; step 2 used to rank the two by name (a.csv
    first) and saw x shown."""
    from datetime import datetime, timezone

    monkeypatch.setattr(crud, "batch_write_instant", lambda db: datetime(2026, 1, 1, tzinfo=timezone.utc))
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "a.csv"})["changed"]
    _write(db, {"row_id": r, "values": {"a": "y"}, "source_name": "b.csv"}, tx="tx2")
    assert _now(db)[r]["a"] == "y"
    _write(db, {"row_id": r, "values": {"a": "x"}, "source_name": crud.CHAIN_SOURCE}, tx="tx3")
    assert crud.CHAIN_SOURCE in lines.layers(db, TABLE, [r])[(r, "a")]


def test_at_one_instant_a_batch_s_line_ranks_after_every_stored_line(db, monkeypatch):
    """B 11-11: a.csv said x; one batch [b.csv y, the chain x] at a.csv's instant - step 2 ranks b.csv's line (not
    numbered yet) after a.csv's, so the cell shows y and the chain's x is written. A naive instant: sqlite reads a
    stored `at` back naive, and the batch's own aware one would not tie with it."""
    from datetime import datetime

    monkeypatch.setattr(crud, "batch_write_instant", lambda db: datetime(2026, 1, 1))
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "a.csv"})["changed"]
    _write(db, {"row_id": r, "values": {"a": "y"}, "source_name": "b.csv"},
           {"row_id": r, "values": {"a": "x"}, "source_name": crud.CHAIN_SOURCE}, tx="tx2")
    assert crud.CHAIN_SOURCE in lines.layers(db, TABLE, [r])[(r, "a")]


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
    assert (newer["lines"], _lines(db)[-1][lines.value_column("a")]) == (1, "new"), newer


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
    assert [{k: v for k, v in said.items() if k != "line_id"} for said in out["items"]] == [
        {"row_id": a, "work": "left_out", "columns": []},
        {"row_id": b, "work": "new", "columns": ["a", "k"]},
        {"row_id": a, "work": "gated", "columns": ["a", "n"]},
        {"row_id": None, "work": None, "columns": ["a"]},
        {"row_id": a, "work": "edit", "columns": ["a", "n"]}], out["items"]
    lined = [said["line_id"] for said in out["items"]]          # the line each item wrote, None where it wrote none
    assert [line_id is not None for line_id in lined] == [False, True, False, False, True]
    assert sorted(r["line_id"] for r in _lines(db) if r["batch"] == "tx2") == sorted(lined[1::3]), lined


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


def test_a_write_reads_t_s_shape_once_a_key_merge_too(db, monkeypatch):
    """Lead 11-11: one shape a write - the step-5 merge and a key merge's merge, spoken and layers take the write's
    (s=), and a line's text takes its stored kind from it (shape["kinds"]): t's stored kinds and its bit map are read
    once, by that shape (C 68c8145ef)."""
    _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1", "written_by": "loader"})
    _write(db, {"key": {"k": "K2"}, "values": {"k": "K2", "a": "y"}, "source_name": "f1", "written_by": "loader"})
    k2 = [r for r, row in _now(db).items() if row["k"] == "K2"][0]
    seen = {"shape": 0, "value_types": 0, "physical_kinds": 0, "bit_maps": 0}
    for name in seen:
        real = getattr(lines, name)

        def counted(*a, _real=real, _name=name, **k):
            seen[_name] += 1
            return _real(*a, **k)
        monkeypatch.setattr(lines, name, counted)
    _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "z"}, "source_name": "f2", "written_by": "loader"})
    plain = dict(seen)
    seen.update(dict.fromkeys(seen, 0))
    merged = _write(db, {"row_id": k2, "values": {"k": "K1"}, "source_name": "f3", "written_by": "loader"})["merged"]
    once = {"shape": 1, "value_types": 0, "physical_kinds": 1, "bit_maps": 1}
    assert (plain, dict(seen), len(merged)) == (once, once, 1)


SAME_HAND = ("loader", "r1")


@pytest.mark.parametrize("column, first, again, hand, left_out", [
    ("a", None, None, SAME_HAND, True),
    ("a", "", None, SAME_HAND, True),                    # a blank is absence
    ("a", "   ", "", SAME_HAND, True),
    ("a", " x ", "x", SAME_HAND, True),                  # the ends trimmed
    ("n", "1", 1.0, SAME_HAND, True),                    # one number, one text on a number column
    ("a", "가나", "가나", SAME_HAND, True),
    ("a", "가나", "가나다", SAME_HAND, False),
    ("a", "Ab", "ab", SAME_HAND, False),                 # case is a value
    ("a", "x", "y", SAME_HAND, False),
    ("a", "x", "x", ("kim", "r1"), False),               # the same value from another hand is a new statement
    ("a", "x", "x", ("loader", "r2"), False),            # ... from another input row too (ruling 434)
])
def test_a_write_saying_its_head_lines_text_again_is_left_out_cell_by_cell(db, column, first, again, hand, left_out):
    """Step 2's «the same text, hand and input row» per cell - the answer the SQL comparison gave before 11-11 and
    the head-line read gives now (both texts through crud.line_text): this table is green on both trees."""
    _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", column: first}, "source_name": "f1",
                "written_by": SAME_HAND[0], "input_row": SAME_HAND[1]})
    before = len(_lines(db))
    _write(db, {"key": {"k": "K1"}, "values": {column: again}, "source_name": "f1", "written_by": hand[0],
                "input_row": hand[1]}, tx="tx2")
    assert (len(_lines(db)) == before) is left_out


def test_a_line_that_moves_no_shown_value_leaves_the_row_s_updated_at(db):
    """Lead 11-11 ㄱ: t.updated_at is when a shown value moved (the old write's rule) - a person saying what the cell
    shows writes a line and leaves it; another value moves it."""
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})["changed"]
    first = _now(db)[r]["updated_at"]
    out = _write(db, {"row_id": r, "values": {"a": "x"}, "source_name": "user", "written_by": "kim"}, tx="tx2")
    assert first is not None and out["lines"] == 1 and _now(db)[r]["updated_at"] == first, out
    _write(db, {"row_id": r, "values": {"a": "y"}, "source_name": "user", "written_by": "kim"}, tx="tx3")
    assert _now(db)[r]["a"] == "y" and _now(db)[r]["updated_at"] != first


@pytest.mark.parametrize("batch", [
    [{"values": {"a": "y"}}, {"values": {"a": "x"}}],                        # x said again after y in one batch
    [{"line_kind": "withdraw", "columns": ["a"]}, {"values": {"a": "x"}}],    # x said again after its withdraw
])
def test_a_batch_s_last_word_on_a_cell_wins(db, batch):
    """Lead 11-11 ㄱ: step 2 judges a batch's items on the heads as its earlier items left them, as the old write wrote
    them one by one - not each on the heads the batch began with."""
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})["changed"]
    out = _write(db, *[dict(it, row_id=r, source_name="f1") for it in batch], tx="tx2")
    assert (out["lines"], _now(db)[r]["a"]) == (2, "x"), out


@pytest.mark.parametrize("column, head, again, left_out", [
    ("a", " x ", "x", False),          # a text column's head as it stands: the trimmed text is a change
    ("a", "", None, True),             # a blank is absence (CLAUDE.md «길이 0 은 NULL»)
    ("n", "1", 1.0, True),             # a number column: one number, one text (lead 11-11 accepted)
])
def test_a_head_written_before_line_text_compares_by_its_column(db, column, head, again, left_out):
    """Lead 11-11 ㄴ: a head whose text is not what line_text would store (written before it) - a text column's
    compares as it stands, any other column's by its line text."""
    item = {"key": {"k": "K1"}, "source_name": "f1", "written_by": "loader", "input_row": "r1"}
    _write(db, dict(item, values={"k": "K1", column: "5"}))
    ln = lines.shape(db, TABLE, CFG)["lines"]
    db.execute(ln.update().values({lines.value_column(column): head}))
    before = len(_lines(db))
    _write(db, dict(item, values={column: again}), tx="tx2")
    assert (len(_lines(db)) == before) is left_out


def test_a_key_that_moves_a_declared_key_column_moves_updated_at(db, monkeypatch):
    """QA 11-11: a re-key (step 5½) after the merge moves the declared key column - a shown column - so updated_at
    moves, as the old write's written_col did; a table keyed in business_key_val alone keeps it (no shown column
    moved)."""
    table, cfg = "wl_keyed", {"business_key": "bk", "composite_key_source": ["k"],
                              "column_types": {"bk": "string", "k": "string", "a": "string"}}
    monkeypatch.setitem(crud.TABLE_CONFIG, table, cfg)
    keep_lines(db, table, cfg)
    [r] = write_lines(db, table, [{"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"}],
                      kind="funnel", transaction_id="tx1")["changed"]
    now = lines.shape(db, table, cfg)["table"]
    db.execute(now.update().where(now.c.row_id == r).values(business_key_val="OLD", bk="OLD"))
    before = dict(db.execute(select(now).where(now.c.row_id == r)).mappings().one())
    write_lines(db, table, [{"row_id": r, "line_kind": "mark", "columns": [], "rekey": True, "source_name": "f1"}],
                kind="mark", transaction_id="tx2")
    after = dict(db.execute(select(now).where(now.c.row_id == r)).mappings().one())
    assert (before["bk"], after["bk"]) == ("OLD", "K1") and after["updated_at"] != before["updated_at"], (before, after)
