# -*- coding: utf-8 -*-
"""총괄 9eb902922 ① (소유자 10-07 「Object of type datetime is not JSON serializable」): six senders
announce a changed row as a `batch_row_upsert` item - five grid routes and the chain worker's group
broadcast - and each passed the row's cells as it held them: a datetime cell is a Python datetime
there, so `json.dumps` died AFTER the write had committed (the cell write's broadcast and the chain's
were lost; the four cell-menu routes raised outright). They all build the item in
`event_constants.upsert_item` now. On PostgreSQL: sqlite's DateTime refuses the written text first."""
import json

import pytest

from database import crud, models, schemas

TABLE = "time_cell_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "when": "datetime", "n": "number", "e": "string",
                          "v": "string"}}
SRC = "time_cell_src"
SRC_ENTRY = {"business_key": "k", "composite_key_source": ["k"],
             "column_types": {"k": "string", "v": "string"}}
COLS = ("when", "n", "e", "v")


@pytest.fixture
def grid(pg_engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import MetaData, text
    from sqlalchemy.orm import sessionmaker

    import main
    from conftest import PG_TEST_SCHEMA
    from database.database import get_db

    models.init_dynamic_models({TABLE: ENTRY, SRC: SRC_ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    monkeypatch.setitem(crud.TABLE_CONFIG, SRC, SRC_ENTRY)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in (TABLE, SRC):
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    heard = []

    async def broadcast(message):
        heard.append(json.loads(message))

    monkeypatch.setattr(main.manager, "broadcast", broadcast)
    main.app.dependency_overrides[get_db] = lambda: session
    try:
        with TestClient(main.app) as client:
            yield client, heard, session
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        session.close()
        with pg_engine.begin() as conn:
            for name in (TABLE, SRC):
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))


def _write(client, **cells):
    return client.put("/tables/%s/data/updates" % TABLE, json={"updates": [
        {"updates": cells, "business_key_val": cells["k"], "source_name": "user",
         "updated_by": "probe"}]})


def _read(client):
    [row] = client.get("/tables/%s/data" % TABLE).json()["data"]
    return row


def _a_row_of_three_kinds(client, **v):
    assert _write(client, k="A", when="2026-10-07 10:00:00", n=1.5, e="", **v).status_code == 200
    row = _read(client)
    before = row["data"]
    assert ("2026-10-07" in before["when"]["value"], before["n"]["value"],
            before["e"]["value"]) == (True, 1.5, None)               # canary: the three kinds are there
    return row


# Each route acts on cell `v` of the one row; the row also holds a datetime, a number and an empty cell.
ROUTES = {
    "cell write": lambda c, rid: _write(c, k="A", v="y"),
    "pin one": lambda c, rid: c.put("/tables/%s/%s/v/priority" % (TABLE, rid),
                                    json={"source_name": "user"}),
    "pin batch": lambda c, rid: c.put("/tables/%s/cells/priority/batch" % TABLE, json={
        "updates": [{"row_id": rid, "column_name": "v"}], "source_name": "user"}),
    "delete source one": lambda c, rid: c.delete("/tables/%s/%s/v/sources/user" % (TABLE, rid)),
    "delete source batch": lambda c, rid: c.post("/tables/%s/cells/sources/delete/batch" % TABLE, json={
        "cells": [{"row_id": rid, "column_name": "v"}], "source_name": "user"}),
}


@pytest.mark.pg
@pytest.mark.parametrize("route", sorted(ROUTES))
def test_a_route_announces_the_row_as_the_grid_reads_it(grid, route):
    client, heard, _ = grid
    row = _a_row_of_three_kinds(client, v="x")
    heard.clear()
    answer = ROUTES[route](client, row["row_id"])
    assert (answer.status_code, answer.json()["status"]) == (200, "success"), answer.text
    [item] = [item for msg in heard if msg.get("event") == "batch_row_upsert"
              for item in msg["items"]]
    read = _read(client)["data"]
    assert {c: item["data"][c]["value"] for c in COLS} == {c: read[c]["value"] for c in COLS}


@pytest.mark.pg
def test_the_chain_announces_the_row_as_the_grid_reads_it(grid):
    """The sixth sender: a join writes `v` into the same row, and its group's broadcast - through
    the transport's own `json.dumps` - carries the row as the grid reads it."""
    import mapper_sdk
    from chain import ingestion_worker as worker
    from chain import rule_shape
    from utils.payload_helper import get_payload_dict

    client, _heard, session = grid
    mapper_sdk.discover()
    rules, refusal, _ = rule_shape.expand_declaration(
        {"name": "time_cell_join", "on": {"table": SRC}, "into": {"table": TABLE},
         "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}], "take": ["v"]}},
         "key": {"unique": True}}, table_config={TABLE: ENTRY, SRC: SRC_ENTRY})
    assert refusal is None, refusal
    _a_row_of_three_kinds(client)          # `v` left to the chain: a person's layer would outrank it
    crud.apply_batch_updates(session, SRC, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"k": "A", "v": "y"}, source_name="file", updated_by="t")]))
    session.commit()
    events = [e for e in session.query(models.DatabaseOutbox)
              .filter(models.DatabaseOutbox.processed_chain.is_(False)).all() if e.table_name == SRC]
    ok, error, messages = worker._process_chain_transaction_group_sync(
        get_payload_dict(events[0]).get("transaction_id"), events, session, rules)
    assert ok, error
    [item] = [item for msg in json.loads(json.dumps(messages))
              if msg.get("event") == "batch_row_upsert" for item in msg["items"]]
    read = _read(client)["data"]
    assert read["v"]["value"] == "y"                                 # canary: the chain wrote
    assert {c: item["data"][c]["value"] for c in COLS} == {c: read[c]["value"] for c in COLS}
