# -*- coding: utf-8 -*-
"""Lead 11-11i (a release blocker): a marking's values meet its column as the column compares them
(`column_filter.set_values`) - the set filter every door reads (the grid, `/tables/{t}/data?marking`, the reach), and
the reach's «not in the table». The screen sends a row id of digits as a number; PostgreSQL refused
«character varying = integer» and the Tables walk stopped at its first step (500).

  row ids     a text row_id table and an integer row_id table (the same rows, the column altered) × the values sent as
              numbers and as texts: the reach reaches the same rows, says none «not in the table», and the grid pages
              the marking's rows (the integer table's page waits on the lead - its xfail says where)
  grid        a text column keeps a text as it came - '007' is not '7', '3.0' is not '3' - a number sent there meets
              the text that spells it; a number column takes numbers and texts that read as numbers, and refuses one
              that does not, by name
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, text

import column_filter
from conftest import PG_TEST_SCHEMA, retire_dynamic_model
from database import crud, models
from test_a_reach_is_the_rows_the_walk_read_pg import WAFERS, _board, _times_declared  # noqa: F401
from test_ledger_worlds_are_independent_and_meet_in_a_walk import fixture_config, fixture_world  # noqa: F401

pytestmark = pytest.mark.pg

GRID = "mark_values_grid"
GRID_CONFIG = {"column_types": {"code": "string", "n": "number"}}
CODES = [("a", "007", 7.0), ("b", "7", 3.0), ("c", "3.0", 7.0), ("d", "3", None)]


@pytest.fixture(name="numbered")
def fixture_numbered(world):
    """The reach board, lot_slot_wafer's row ids renumbered 1 · 2 · 3 (as the rehearsal's) before the ledger is read."""
    import test_a_reach_is_the_rows_the_walk_read_pg as reach_board
    from ledger import backfill

    real = backfill.run

    def numbered_first(engine, **kwargs):
        with engine.begin() as conn:
            ids = [row for (row,) in conn.execute(text("SELECT row_id FROM lot_slot_wafer ORDER BY lot_slot_wafer_key"))]
            if ids and not ids[0].isdigit():
                for number, row_id in enumerate(ids, 1):
                    conn.execute(text("UPDATE lot_slot_wafer SET row_id = :n WHERE row_id = :r"),
                                 {"n": str(number), "r": row_id})
        return real(engine, **kwargs)

    backfill.run = numbered_first
    try:
        return reach_board._board(world)
    finally:
        backfill.run = real


@pytest.fixture(name="client")
def fixture_client(world):
    import main
    from database.database import get_db

    def per_request():
        session = world["maker"]()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[get_db] = per_request
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def _integer_row_ids(world):
    with world["engine"].begin() as conn:
        conn.execute(text("ALTER TABLE lot_slot_wafer ALTER COLUMN row_id TYPE integer USING row_id::integer"))
        assert conn.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema = :s AND "
                                 "table_name = 'lot_slot_wafer' AND column_name = 'row_id'"),
                            {"s": PG_TEST_SCHEMA}).scalar() == "integer"


def _reached(world, values):
    from ledger import trace_router

    with world["engine"].connect() as conn:
        said = trace_router.reach(conn, engine="virtual", **{**WAFERS, "column": "row_id", "values": values})
    return sorted(said["rows"]), [item for item in said["left_out"] if item["why"] == "not in the table"]


def _paged(client, values):
    kept = client.post("/markings", json={"table": "lot_slot_wafer", "column": "row_id", "values": values})
    assert kept.status_code == 200, kept.text
    answer = client.get("/tables/lot_slot_wafer/data", params={"marking": kept.json()["id"]})
    assert answer.status_code == 200, answer.text
    return sorted(str((row.get("data") or row).get("row_id") or row.get("row_id")) for row in answer.json()["data"])


@pytest.mark.parametrize("integer", [False, True], ids=["text row_id", "integer row_id"])
def test_a_row_id_marking_reaches_the_same_rows_sent_as_numbers_or_texts(numbered, integer):
    world = numbered
    if integer:
        _integer_row_ids(world)
    as_texts, as_numbers = _reached(world, ["1", "2"]), _reached(world, [1, 2])
    assert as_texts == as_numbers and as_texts[0] and not as_texts[1], (as_texts, as_numbers)
    assert _reached(world, [1, 2, 9])[1][0]["values"] == 1, "a value not in the table is still said"


@pytest.mark.parametrize("integer", [False, pytest.param(True, marks=pytest.mark.xfail(
    strict=True, reason="the grid's metadata read (grid_read.fetch_and_merge_metadata) asks cell_overwrites' text "
                        "row_id with the table's integers - not the marking's seat; asked of the lead 11-12"))],
    ids=["text row_id", "integer row_id"])
def test_a_row_id_marking_pages_the_same_rows_sent_as_numbers_or_texts(numbered, client, integer):
    if integer:
        _integer_row_ids(numbered)
    assert _paged(client, [1, 2]) == _paged(client, ["1", "2"]) == ["1", "2"]


@pytest.fixture(name="grid")
def fixture_grid(world):
    retire_dynamic_model(GRID)
    models.init_dynamic_models({GRID: GRID_CONFIG})
    crud.TABLE_CONFIG[GRID] = GRID_CONFIG
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[GRID].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(world["engine"])
    with world["engine"].begin() as conn:
        for row_id, code, n in CODES:
            conn.execute(text(f'INSERT INTO "{GRID}" (row_id, code, n) VALUES (:r, :c, :n)'),
                         {"r": row_id, "c": code, "n": n})
    try:
        yield world
    finally:
        with world["engine"].begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS "{PG_TEST_SCHEMA}"."{GRID}"'))
        crud.TABLE_CONFIG.pop(GRID, None)
        retire_dynamic_model(GRID)


def _kept(world, column, values):
    from sqlalchemy import select

    model = models.DYNAMIC_TABLES[GRID]
    condition = column_filter.get_column_filter_condition(model, column, {"filterType": column_filter.SET,
                                                                          "values": values})
    with world["engine"].connect() as conn:
        return sorted(conn.execute(select(model.row_id).where(condition)).scalars())


@pytest.mark.parametrize("column, values, rows", [
    ("code", ["007"], ["a"]), ("code", ["7"], ["b"]), ("code", ["3.0"], ["c"]), ("code", ["3"], ["d"]),
    ("code", [7], ["b"]), ("code", [3.0], ["d"]), ("code", ["007", None], ["a"]),
    ("n", [7], ["a", "c"]), ("n", ["7"], ["a", "c"]), ("n", ["3.0"], ["b"]), ("n", [None], ["d"])],
    ids=lambda v: repr(v))
def test_a_grid_set_filter_meets_a_text_as_written_and_a_number_as_the_column_spells_it(grid, column, values, rows):
    assert _kept(grid, column, values) == rows


def test_a_number_column_refuses_a_text_that_reads_as_no_number_by_name(grid):
    with pytest.raises(column_filter.FilterRefused) as refused:
        _kept(grid, "n", ["abc"])
    assert "is not a list of numbers for 'n'" in str(refused.value)
