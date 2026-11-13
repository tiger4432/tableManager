# -*- coding: utf-8 -*-
"""Cell-source overhaul, D's read share (docs/design/CELL_SOURCE_OVERHAUL.md «읽기 — D 분야», lead 11-10 안 1): a row's
history is its lines in `t__lines`, said in today's entry fields so the screen reads it as it does. Lines built by hand
(tests/support/line_tables) until the write share lands.

  row history   newest first by (at, line_id); a line says each column it wrote - a withdrawn one without a value -;
                a deleted line is today's row-deletion entry; a mark line is not a history entry; no old_value
  entry id      "<line_id>:<column>" (audit_history.entry_id - the broadcast's too)
  cell history  the lines that said that column, and the deletion; the row's line count beside it
  paging        a page counts lines; lines of one instant page without a repeat or a gap
  deletion      «deleted» lines answer deleted_rows; every line's key answers a deleted row's key
  bits          a table past 64 columns - the 64th column's bit is a bigint's sign
"""
from datetime import datetime, timedelta, timezone

import pytest

from conftest import retire_dynamic_model
from database import crud, models
from tests.support import line_tables

TABLE = "lines_history_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "a": "string", "b": "number", "c": "string"}}
T0 = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=pytest.mark.pg)])
def dialect_client(request):
    """(client, engine) - the in-memory sqlite suite's, or one on the PG test schema: the same statements both."""
    if request.param == "sqlite":
        return request.getfixturevalue("client"), request.getfixturevalue("db_session").get_bind()
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    import main
    from database.database import get_db

    engine = request.getfixturevalue("pg_engine")
    made = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def per_request():
        session = made()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[get_db] = per_request
    request.addfinalizer(lambda: main.app.dependency_overrides.pop(get_db, None))
    client = TestClient(main.app)
    return client, engine


def _line_table_fixture(dialect_client, monkeypatch, name, entry):
    client, engine = dialect_client
    models.init_dynamic_models({name: entry})
    monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)
    return client, engine, line_tables.build(engine, name)


@pytest.fixture
def history(dialect_client, monkeypatch):
    client, engine, bits = _line_table_fixture(dialect_client, monkeypatch, TABLE, ENTRY)
    try:
        yield client, engine, bits
    finally:
        line_tables.drop(engine, TABLE)
        retire_dynamic_model(TABLE)


def _seed(engine, bits):
    """r1: a file wrote k a b, a person wrote a, the chain withdrew b, a pin mark; r2: written then deleted."""
    with engine.begin() as conn:
        ids = {
            "file": line_tables.line(conn, TABLE, bits, "r1", source="f.csv", at=T0, written_by="parser", batch="tx1",
                                     values={"k": "K1", "a": "A1", "b": 1.5}, business_key="K1"),
            "hand": line_tables.line(conn, TABLE, bits, "r1", source="user", at=T0 + timedelta(minutes=1),
                                     written_by="person", batch="tx2", values={"a": "A2"}, business_key="K1"),
            "withdraw": line_tables.line(conn, TABLE, bits, "r1", kind="withdraw", source="chain:rule_x",
                                         at=T0 + timedelta(minutes=2), written_by="chain", batch="tx3",
                                         withdrawn=("b",), business_key="K1"),
            "mark": line_tables.line(conn, TABLE, bits, "r1", kind="mark", source="pin", at=T0 + timedelta(minutes=3),
                                     written_by="person", batch="tx4", business_key="K1"),
            "r2": line_tables.line(conn, TABLE, bits, "r2", source="f.csv", at=T0, written_by="parser", batch="tx1",
                                   values={"k": "K2", "a": "X"}, business_key="K2"),
            "r2 gone": line_tables.line(conn, TABLE, bits, "r2", kind="deleted", source="user",
                                        at=T0 + timedelta(minutes=5), written_by="person", batch="tx5",
                                        business_key="K2"),
        }
        line_tables.now(conn, TABLE, "r1", "K1", {"k": "K1", "a": "A2"}, {"k": ids["file"], "a": ids["hand"]})
    return ids


def test_a_rows_history_is_its_lines_said_column_by_column(history):
    client, engine, bits = history
    ids = _seed(engine, bits)
    page = client.get("/tables/%s/rows/r1/history" % TABLE).json()
    said = [(e["id"], e["column_name"], e["new_value"], e["source_name"], e["updated_by"], e["transaction_id"])
            for e in page["logs"]]
    assert said == [("%d:b" % ids["withdraw"], "b", None, "chain:rule_x", "chain", "tx3"),
                    ("%d:a" % ids["hand"], "a", "A2", "user", "person", "tx2"),
                    ("%d:k" % ids["file"], "k", "K1", "f.csv", "parser", "tx1"),
                    ("%d:a" % ids["file"], "a", "A1", "f.csv", "parser", "tx1"),
                    ("%d:b" % ids["file"], "b", 1.5, "f.csv", "parser", "tx1")], said
    assert all("old_value" not in e and e["business_key"] == "K1" and e["is_row_deleted"] is False
               for e in page["logs"])
    assert (page["returned"], page["truncated"], page["next_cursor"]) == (5, False, None)


def test_a_cells_history_is_the_lines_that_said_it_and_a_deleted_row_says_so(history):
    client, engine, bits = history
    ids = _seed(engine, bits)
    cell = client.get("/tables/%s/rows/r1/cells/a/history" % TABLE).json()
    assert [(e["id"], e["new_value"]) for e in cell["logs"]] == [("%d:a" % ids["hand"], "A2"),
                                                                  ("%d:a" % ids["file"], "A1")]
    assert cell["row_history_total"] == 3, "the row's history lines - write, write, withdraw (the mark is not one)"
    gone = client.get("/tables/%s/rows/r2/cells/a/history" % TABLE).json()["logs"]
    assert [(e["column_name"], e["new_value"], e["source_name"], e["is_row_deleted"], e["business_key"])
            for e in gone] == [(crud.ROW_DELETION_COLUMN, "row deleted", "system", True, "K2"),
                               ("a", "X", "f.csv", True, "K2")]
    from sqlalchemy.orm import Session

    import main

    with Session(bind=engine) as session:
        assert crud.deleted_rows(session, TABLE, ["r1", "r2", "r9"]) == {"r2"}
        assert main.get_deleted_rows_business_keys_bulk(session, TABLE, ["r1", "r2", "r9"]) == {"r1": "K1", "r2": "K2"}
        assert main.get_deleted_row_business_key(session, TABLE, "r2") == "K2"


def test_lines_of_one_instant_page_without_a_repeat_or_a_gap(history):
    client, engine, bits = history
    with engine.begin() as conn:
        made = [line_tables.line(conn, TABLE, bits, "r1", at=T0, batch="tx", values={"a": "v%d" % n},
                                 business_key="K1") for n in range(5)]
    seen, cursor = [], None
    for _ in range(5):
        page = client.get("/tables/%s/rows/r1/history" % TABLE,
                          params=dict({"limit": 2}, **({"cursor": cursor} if cursor else {}))).json()
        seen += [e["id"] for e in page["logs"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ["%d:a" % i for i in reversed(made)], seen


@pytest.fixture
def wide(dialect_client, monkeypatch):
    name = "lines_wide_probe"
    entry = {"business_key": "k", "composite_key_source": ["k"],
             "column_types": dict({"k": "string"}, **{"c%02d" % i: "string" for i in range(70)})}
    client, engine, bits = _line_table_fixture(dialect_client, monkeypatch, name, entry)
    try:
        yield client, engine, bits, name
    finally:
        line_tables.drop(engine, name)
        retire_dynamic_model(name)


def test_a_column_past_the_64th_and_the_64th_itself_are_read_by_their_bit(wide):
    client, engine, bits, name = wide
    by_bit = {bit: column for column, bit in bits.items()}
    sign, past = by_bit[63], by_bit[65]
    with engine.begin() as conn:
        first = line_tables.line(conn, name, bits, "w1", at=T0, values={sign: "S", past: "P"}, business_key="W1")
        line_tables.line(conn, name, bits, "w1", at=T0 + timedelta(seconds=1), values={by_bit[0]: "Z"},
                         business_key="W1")
    for column, value in ((sign, "S"), (past, "P")):
        logs = client.get("/tables/%s/rows/w1/cells/%s/history" % (name, column)).json()["logs"]
        assert [(e["id"], e["new_value"]) for e in logs] == [("%d:%s" % (first, column), value)], (column, logs)
