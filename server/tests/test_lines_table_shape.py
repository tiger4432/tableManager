"""database.lines on sqlite: names, bit slots never reused, two tables + a view that refuses writes, column DDL on
both tables alike (docs/design/CELL_SOURCE_OVERHAUL.md)."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from database import lines

CFG = {"column_types": {"lot": "string", "qty": "number", "seen": "datetime"}}


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    lines.LineColumn.__table__.create(engine)
    lines.AuditBatch.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_names_refuse_over_63_bytes():
    assert lines.now_relation("a") == "a__now" and lines.lines_relation("a") == "a__lines"
    assert lines.now_relation("x" * 58) == "x" * 58 + "__now"
    with pytest.raises(ValueError):
        lines.lines_relation("x" * 57)


def test_a_dropped_columns_slot_is_never_handed_out_again(db):
    lines.ensure_line_table(db, "t", CFG)
    before = lines.bit_map(db, "t")
    assert sorted(before.values()) == [0, 1, 2] and "row_id" not in before
    kept = {k: v for k, v in CFG["column_types"].items() if k != "qty"}
    lines.alter_columns(db, "t", {"column_types": kept}, drop=["qty"])
    cfg2 = {"column_types": {**kept, "grade": "string"}}
    lines.alter_columns(db, "t", cfg2, add=["grade"])
    after = lines.bit_map(db, "t")
    assert "qty" not in after and after["grade"] == 3
    assert after["lot"] == before["lot"] and after["seen"] == before["seen"]


def test_two_tables_and_a_view_that_refuses_writes(db):
    lines.ensure_line_table(db, "t", CFG)
    insp = inspect(db.connection())
    assert {"t__now", "t__lines"} <= set(insp.get_table_names()) and "t" in insp.get_view_names()
    view_cols = [c["name"] for c in insp.get_columns("t")]
    assert "won_by" not in view_cols and {"row_id", "lot", "qty", "seen"} <= set(view_cols)
    assert {"written_0", "head_0", "withdrawn_0"} <= {c["name"] for c in insp.get_columns("t__lines")}
    db.execute(text("INSERT INTO t__now (row_id) VALUES ('r0')"))      # a row-level trigger fires per row
    for stmt in ("INSERT INTO t (row_id) VALUES ('r1')", "UPDATE t SET lot = 'x'", "DELETE FROM t"):
        with pytest.raises(Exception, match="write through database.lines"):
            db.execute(text(stmt))


def test_a_column_added_lands_on_both_tables_and_the_view(db):
    lines.ensure_line_table(db, "t", CFG)
    cfg2 = {"column_types": {**CFG["column_types"], "grade": "string"}}
    lines.alter_columns(db, "t", cfg2, add=["grade"])
    insp = inspect(db.connection())
    for rel in ("t__now", "t__lines", "t"):
        assert "grade" in {c["name"] for c in insp.get_columns(rel)}, rel


def test_a_65th_column_adds_a_second_chunk(db):
    cfg = {"column_types": {f"c{i}": "string" for i in range(64)}}
    lines.ensure_line_table(db, "t", cfg)
    cfg2 = {"column_types": {**cfg["column_types"], "c64": "string"}}
    lines.alter_columns(db, "t", cfg2, add=["c64"])
    cols = {c["name"] for c in inspect(db.connection()).get_columns("t__lines")}
    assert {"written_1", "head_1", "withdrawn_1"} <= cols and lines.bit_map(db, "t")["c64"] == 64


def test_drop_line_table_leaves_nothing(db):
    lines.ensure_line_table(db, "t", CFG)
    assert lines.has_lines(db, "t")
    lines.drop_line_table(db, "t")
    insp = inspect(db.connection())
    assert not ({"t__now", "t__lines"} & set(insp.get_table_names())) and "t" not in insp.get_view_names()


def test_seeding_is_scoped():
    assert not lines.is_seeding()
    with lines.seeding():
        assert lines.is_seeding()
    assert not lines.is_seeding()
