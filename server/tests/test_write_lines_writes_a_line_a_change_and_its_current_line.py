# -*- coding: utf-8 -*-
"""The cell-source overhaul's one write (docs/design/CELL_SOURCE_OVERHAUL.md «쓰기», A 11-10): a write is a line, the
same write again is none, a later line of one source takes the head, a withdraw takes a cell back (a NULL head too), a
deleted line keeps the key and the current line goes, one new key twice in a batch is one row, and the line's batch
and the audit row's transaction id are the transaction id as given (D 11-10). sqlite."""
import pytest
from sqlalchemy import bindparam, create_engine, select, text
from sqlalchemy.orm import sessionmaker

import event_constants
from database import crud, lines
from database.write_lines import write_lines

TABLE = "wl_probe"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string", "n": "number"}}


def stand_in_winners(shape):
    """Stand-in for C's lines.winners_sql until it lands (11-11): the latest head line of the column wins - no rank, no
    pin. The two write_lines test files share it."""
    def winners(table, cfg, column, param):
        k, m = shape["bits"][column] // 64, 1 << (shape["bits"][column] % 64)
        head = "h.line_kind = 'write' AND (h.head_{k} & {m}) != 0 AND (h.withdrawn_{k} & {m}) = 0".format(k=k, m=m)
        return text("SELECT h.row_id, h.{c}, h.line_id FROM {t} h WHERE h.row_id IN :{p} AND {head} AND h.line_id = "
                    "(SELECT max(line_id) FROM {t} h2 WHERE h2.row_id = h.row_id AND {head2})".format(
                        c=column, t=shape["lines"].name, p=param, head=head, head2=head.replace("h.", "h2."))
                    ).bindparams(bindparam(param, expanding=True))
    return winners


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    engine = create_engine("sqlite://")
    lines.LineColumn.__table__.create(engine)
    lines.AuditBatch.__table__.create(engine)
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(lines, "winners_sql", stand_in_winners(lines.ensure_line_table(db, TABLE, CFG)), raising=False)
    try:
        yield db
    finally:
        db.close()


def _lines(db):
    ln = lines.shape(db, TABLE, CFG)["lines"]
    return [dict(r) for r in db.execute(select(ln).order_by(ln.c.line_id)).mappings()]


def _now(db):
    now = lines.shape(db, TABLE, CFG)["now"]
    return {r["row_id"]: dict(r) for r in db.execute(select(now)).mappings()}


def _write(db, *items, kind="funnel", tx="tx1"):
    return write_lines(db, TABLE, list(items), kind=kind, transaction_id=tx)


def test_a_write_is_one_line_its_current_line_and_one_audit_row(db):
    out = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x", "n": "2"}, "source_name": "f1",
                      "written_by": "loader"})
    [line] = _lines(db)
    [(row_id, change)] = out["changed"].items()
    assert (line["line_kind"], line["row_id"], line["business_key_val"], line["a"], line["n"]) == (
        "write", row_id, "K1", "x", 2.0), line
    assert line["written_0"] == line["head_0"] != 0 and line["withdrawn_0"] == 0
    assert change["work"] == "new" and change["old"] is None and change["new"]["a"] == "x"
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
