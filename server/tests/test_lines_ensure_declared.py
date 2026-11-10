"""lines.ensure_declared on sqlite: a declared table that keeps lines gets them, a built one passes with no DDL, a
column t was given reaches t__lines, the schema sync is the door (lead 11-11)."""
import pytest
from sqlalchemy import MetaData, Table, create_engine, event, inspect, text

from database import crud, lines, models
from database.models import sql_type_of

CFG = {"column_types": {"lot": "string", "qty": "number"}}


@pytest.fixture()
def engine(monkeypatch):
    engine = create_engine("sqlite://")
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource):
        model.__table__.create(engine)
    Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(engine)
    monkeypatch.setattr(crud, "TABLE_CONFIG", {"t": CFG, "v": {"kind": "view", "column_types": {}}})
    stand_in = type("StandIn", (), {})
    monkeypatch.setattr(models, "DYNAMIC_TABLES", {"t": stand_in, "v": stand_in})
    return engine


def ddl_of(engine, call):
    said = []
    listener = lambda conn, cursor, statement, *a: said.append(statement)       # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        call()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return [s for s in said if s.lstrip().upper().startswith(("CREATE", "ALTER", "DROP"))]


def test_a_declared_table_gets_its_lines_and_a_built_one_passes_with_no_ddl(engine):
    first = ddl_of(engine, lambda: lines.ensure_declared(engine))
    assert any("t__lines" in s for s in first)                                   # canary: the counter sees DDL
    insp = inspect(engine)
    assert insp.has_table("t__lines") and "won_by" in {c["name"] for c in insp.get_columns("t")}
    assert not insp.has_table("v__lines")
    assert ddl_of(engine, lambda: lines.ensure_declared(engine)) == []


def test_a_column_t_was_given_reaches_its_lines(engine, monkeypatch):
    lines.ensure_declared(engine)
    wider = {"column_types": {**CFG["column_types"], "grade": "string"}}
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "t" ADD COLUMN "grade" VARCHAR'))          # what the schema sync does to t
    monkeypatch.setattr(crud, "TABLE_CONFIG", {"t": wider})
    assert lines.ensure_declared(engine) == {}
    assert "v_grade" in {c["name"] for c in inspect(engine).get_columns("t__lines")}


def test_only_the_named_tables(engine):
    assert lines.ensure_declared(engine, ["v"]) == {}
    assert not inspect(engine).has_table("t__lines")


def test_the_schema_sync_is_the_door(engine, monkeypatch):
    called = []
    monkeypatch.setattr(models, "DYNAMIC_TABLES", {})
    monkeypatch.setattr(lines, "ensure_declared", lambda e, tables=None: called.append(e) or {})
    models.sync_dynamic_tables_schema(engine)
    assert called == [engine]


def test_t_built_again_beside_its_old_lines_is_refused_not_attached(engine):
    lines.ensure_declared(engine)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE "t"'))
    Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(engine)
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        assert not lines.has_lines(db, "t")                                     # t__lines alone is not «built»
    said = lines.ensure_declared(engine)
    assert said["t"] == lines.ORPHAN_REFUSAL % {"t": "t", "lines": "t__lines"}
    assert "won_by" not in {c["name"] for c in inspect(engine).get_columns("t")}


def test_drop_every_line_table_leaves_no_orphan(engine):
    lines.ensure_declared(engine)
    assert lines.drop_every_line_table(engine) == ["t__lines"]
    assert not inspect(engine).has_table("t__lines")
