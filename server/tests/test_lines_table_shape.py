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


def test_stored_relation_by_declaration():
    assert lines.stored_relation("t", CFG) == "t__now"
    assert lines.stored_relation("audit_batches", None) == "audit_batches"
    assert lines.stored_relation("v", {"kind": "view", "column_types": {}}) == "v"


def test_declared_of_reads_stored_relation_backwards():
    tables = {"t": CFG, "v": {"kind": "view", "column_types": {}}}
    assert lines.declared_of("t__now", tables) == "t" and lines.declared_of("v", tables) == "v"
    assert lines.declared_of("t", tables) is None and lines.declared_of("audit_batches", tables) is None


def test_chunks_follow_the_built_table_not_the_slot_map(db):
    cfg = {"column_types": {f"c{i}": "string" for i in range(64)}}
    lines.ensure_line_table(db, "t", cfg)
    wider = {"column_types": {**cfg["column_types"], "c64": "string"}}
    lines.ensure_line_table(db, "t", wider)            # slots grow, the built table does not
    lines.alter_columns(db, "t", wider, add=["c64"])
    cols = {c["name"] for c in inspect(db.connection()).get_columns("t__lines")}
    assert {"c64", "written_1", "head_1", "withdrawn_1"} <= cols
    head_sql = db.execute(text("SELECT sql FROM sqlite_master WHERE name = 't__lines_h'")).scalar()
    assert "head_1" in head_sql
    said = lines.alter_columns(db, "t", {"column_types": {**wider["column_types"], **{f"d{i}": "string" for i in range(64)}}},
                               add=[f"d{i}" for i in range(64)])
    index_line = next(x for x in said if "t__lines_h" in x and x.startswith("CREATE INDEX"))
    db.execute(text('DROP INDEX "t__lines_h"'))
    db.execute(text(index_line))                        # the line shown to the operator runs as it is


def test_now_has_row_id_as_its_key(db):
    lines.ensure_line_table(db, "t", CFG)
    pk = inspect(db.connection()).get_pk_constraint("t__now")["constrained_columns"]
    assert pk == ["row_id"]


def test_a_name_whose_derived_index_name_is_too_long_is_refused():
    with pytest.raises(ValueError):
        lines.index_name("x" * 54, "ra")
    assert lines.index_name("x" * 53, "ra") == "x" * 53 + "__lines_ra"


def test_a_too_long_table_name_is_refused_with_its_size():
    assert lines.MAX_TABLE_NAME_BYTES == 53
    assert lines.table_name_refusal("x" * 53) is None
    said = lines.table_name_refusal("표" * 18)                 # 54 bytes in UTF-8
    assert "54 bytes" in said and "53 or fewer" in said


def test_a_quoted_table_name_is_refused_before_migration():
    assert "quote" in lines.table_name_refusal('a"b')


def test_line_values_are_text_and_one_text_means_one_value(db):
    from database import crud

    lines.ensure_line_table(db, "t", CFG)
    types = {c["name"]: str(c["type"]) for c in inspect(db.connection()).get_columns("t__lines")}
    assert all(types[c].startswith("VARCHAR") for c in ("lot", "qty", "seen"))
    pairs = [("9", 9.0, "number"), ("9", "9.5", "number"), (" x ", "x", "string"), ("", None, "string"),
             ("abc", "abc ", "number"), ("2026-11-10 10:00", "2026-11-10T10:00:00", "datetime"),
             ("2026-11-10 10:00", "2026-11-10 10:01", "datetime"), ("0", "-0.000", "number"),
             ("nan", "NaN", "number"), ("nan", "nan", "number")]
    for a, b, kind in pairs:
        assert (crud.line_text(a, kind) != crud.line_text(b, kind)) == crud.values_differ(a, b, kind), (a, b, kind)
    assert crud.line_value(crud.line_text("9", "number"), "number") == 9.0
    assert crud.line_value(crud.line_text("nan", "number"), "number") == "nan"


@pytest.mark.parametrize("text_value", ["00123", "007", "1.10", "9.0"])
def test_a_string_columns_text_keeps_its_zeros(text_value):
    from database import crud

    assert crud.line_text(text_value, "string") == text_value
    assert crud.line_value(crud.line_text(text_value, "string"), "string") == text_value


def test_a_string_column_tells_007_from_7():
    from database import crud

    assert crud.line_text("007", "string") != crud.line_text("7", "string")
    assert crud.values_differ("007", "7", "string")
    assert crud.line_text("007", "number") == crud.line_text("7", "number")       # a number column folds them


@pytest.mark.parametrize("value", ["2", 2, 2.0, "-0.000", "2.5", "1e20", "9007199254740993", "abc", "nan"])
def test_a_number_line_value_round_trips_and_whole_numbers_read_as_int(value):
    from database import crud

    text_once = crud.line_text(value, "number")
    back = crud.line_value(text_once, "number")
    assert crud.line_text(back, "number") == text_once
    if text_once in ("2.0", "0.0"):
        assert type(back) is int


def test_value_types_follow_the_physical_column(db):
    lines.ensure_line_table(db, "t", CFG)
    assert lines.value_types(db, "t") == {"lot": "string", "qty": "number", "seen": "datetime"}
    db.execute(text("CREATE TABLE u__now (row_id VARCHAR PRIMARY KEY, business_key_val VARCHAR, "
                    "created_at TIMESTAMP, updated_at TIMESTAMP, event_time VARCHAR, won_by JSON)"))
    assert lines.value_types(db, "u") == {"event_time": "string"}     # declared datetime, stored as text


def test_shape_types_a_built_column_as_stored(db):
    lines.ensure_line_table(db, "u", {"column_types": {"event_time": "string"}})      # built as text
    s = lines.shape(db, "u", {"column_types": {"event_time": "datetime"}})              # declaration says datetime
    assert type(s["now"].c.event_time.type).__name__ == "String"
    db.execute(s["now"].insert().values(row_id="r1", event_time="2026-01-01T13:00:00"))
    assert db.execute(text("SELECT event_time FROM u__now")).scalar() == "2026-01-01T13:00:00"


def test_which_tables_keep_lines():
    import shipped

    system = sorted(shipped.tables())[0]
    assert system.startswith("sys_")                                             # canary: a shipped table exists
    assert lines.keeps_lines("t", CFG)
    assert not lines.keeps_lines("v", {"kind": "view", "column_types": {}})
    assert not lines.keeps_lines(system, shipped.tables()[system])
    assert not lines.keeps_lines("ledger_atom_rows", None)                       # undeclared: the ledger's own
    assert lines.stored_relation(system, shipped.tables()[system]) == system
