# -*- coding: utf-8 -*-
"""총괄 9eb902922 ① (소유자 10-07 「Object of type datetime is not JSON serializable」): a grid cell
write on a table with a datetime column committed, then its broadcast died in `json.dumps` - the row's
datetime cell rode `items[].data` as a Python datetime - so no screen heard of the write. The item is
spelled as the grid's read spells it. On PostgreSQL: sqlite's DateTime refuses the written text first."""
import json

import pytest

from database import crud, models

TABLE = "time_cell_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "when": "datetime", "v": "string"}}


@pytest.fixture
def grid(pg_engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import MetaData, text
    from sqlalchemy.orm import sessionmaker

    import main
    from conftest import PG_TEST_SCHEMA
    from database.database import get_db

    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    heard = []

    async def broadcast(message):
        heard.append(json.loads(message))

    monkeypatch.setattr(main.manager, "broadcast", broadcast)
    main.app.dependency_overrides[get_db] = lambda: session
    try:
        with TestClient(main.app) as client:
            yield client, heard
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        session.close()
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))


def _write(client, **cells):
    answer = client.put("/tables/%s/data/updates" % TABLE, json={"updates": [
        {"updates": cells, "business_key_val": cells["k"], "source_name": "user",
         "updated_by": "probe"}]})
    assert answer.status_code == 200, answer.text


def _heard_cell(heard, column):
    [item] = [item for msg in heard if msg.get("event") == "batch_row_upsert"
              for item in msg["items"]]
    return item["data"][column]["value"]


@pytest.mark.pg
def test_a_written_row_with_a_time_cell_is_broadcast_as_the_grid_reads_it(grid):
    client, heard = grid
    _write(client, k="A", when="2026-10-07 10:00:00", v="x")
    [row] = client.get("/tables/%s/data" % TABLE).json()["data"]
    read = row["data"]["when"]["value"]
    assert read and "2026-10-07" in read                     # canary: the grid reads the cell
    assert _heard_cell(heard, "when") == read
    heard.clear()
    _write(client, k="A", v="y")                             # another cell of the same row
    assert (_heard_cell(heard, "when"), _heard_cell(heard, "v")) == (read, "y")
