# -*- coding: utf-8 -*-
"""Lead 11-06 (pfab, 120 columns): a batch asks `compute_priority_value` once per (column, source, dated?) for a cell
holding one layer and no pin, and keeps the WINNER - not once per cell (120,000 asks a 1,000-row chunk).

  the answer   every stored cell equals `compute_priority_value` over that cell's stored layers and pin
  the axes     new rows (one layer, remembered) · changed rows (two layers, asked) · a pinned cell · a person's write
  the canary   the first batch asks fewer times than it writes cells, and more than zero
"""
import os
import sys

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from database import crud, models, schemas                           # noqa: E402

pytestmark = pytest.mark.pg
TABLE = "wo_cells"
COLUMNS = {"k": "string", "a": "number", "b": "string", "c": "string"}
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["k"], "column_types": COLUMNS,
                  "display_columns": list(COLUMNS)}}


@pytest.fixture(name="world")
def fixture_world(pg_engine):
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        yield {"db": session, "engine": pg_engine}
    finally:
        session.close()
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
            for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
                conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, table)), {"t": TABLE})
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _write(db, rows, source):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=r, source_name=source, updated_by="probe") for r in rows]))
    db.commit()


def test_every_cell_is_the_winner_of_its_layers(world, monkeypatch):
    db, engine = world["db"], world["engine"]
    asks = []
    real = crud.compute_priority_value
    monkeypatch.setattr(crud, "compute_priority_value", lambda *a, **k: asks.append(1) or real(*a, **k))
    _write(db, [{"k": "r%d" % i, "a": i, "b": "b%d" % i, "c": "c%d" % i} for i in range(20)], "f1.csv")
    assert 0 < len(asks) < 20 * 3, len(asks)                            # canary: remembered, and asked at all
    with engine.connect() as conn:
        ids = dict(conn.execute(text('SELECT k, row_id FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE))).fetchall())
    crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": ids["r1"], "column_name": "a"}], "f1.csv")
    db.commit()
    _write(db, [{"k": "r%d" % i, "a": 100 + i, "b": "x%d" % i} for i in range(4)]            # changed: two layers
           + [{"k": "n%d" % i, "a": i, "b": "n", "c": "n"} for i in range(5)], "f2.csv")   # new: one layer
    _write(db, [{"k": "r2", "c": "person"}], "user")
    # a stored layer that wins one cell (rank 3 over a file's 99) and loses the next to a rank-2 layer: the remembered
    # winner is a ONE-layer cell's only - a cell of more layers whose first one won elsewhere is asked again
    _write(db, [{"k": "q%d" % i, "b": "script"} for i in range(2)], "custom_script")
    _write(db, [{"k": "q1", "b": "parser"}], "pipeline_parser")
    _write(db, [{"k": "q%d" % i, "b": "file"} for i in range(2)], "f3.csv")

    with engine.connect() as conn:
        cells = {(r[0], col): r[i + 1] for r in conn.execute(text(
            'SELECT row_id, a, b, c FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE))) for i, col in enumerate("abc")}
        layers = {}
        for row_id, col, src, value, at in conn.execute(text(
                'SELECT row_id, column_name, source_name, value, ingested_at FROM "%s".cell_sources '
                'WHERE table_name = :t' % PG_TEST_SCHEMA), {"t": TABLE}):
            layers.setdefault((row_id, col), {})[src] = {"value": value, "ingested_at": at}
        pins = dict(((r[0], r[1]), r[2]) for r in conn.execute(text(
            'SELECT row_id, column_name, manual_priority_source FROM "%s".cell_overwrites WHERE table_name = :t'
            % PG_TEST_SCHEMA), {"t": TABLE}))
    assert sum(len(v) > 1 for v in layers.values()) >= 8                 # canary: the changed rows hold two layers
    assert pins.get((ids["r1"], "a")) == "f1.csv"                        # canary: the pin is stored
    wrong = {}
    for cell, value in cells.items():
        want = real(layers.get(cell, {}), pins.get(cell), TABLE)[0]
        if crud.value_key(value, COLUMNS[cell[1]]) != crud.value_key(want, COLUMNS[cell[1]]):
            wrong[cell] = (value, want)
    assert not wrong, wrong
    assert float(cells[(ids["r1"], "a")]) == 1.0
    with engine.connect() as conn:
        q = dict(conn.execute(text('SELECT k, b FROM "%s"."%s" WHERE k LIKE :q' % (PG_TEST_SCHEMA, TABLE)),
                              {"q": "q%"}).fetchall())
    assert q == {"q0": "script", "q1": "parser"}, q                       # rank 3 beats the file, rank 2 beats both                          # the pin held f1's value against f2
