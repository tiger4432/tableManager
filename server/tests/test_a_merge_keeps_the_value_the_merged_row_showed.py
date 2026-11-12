# -*- coding: utf-8 -*-
"""총괄 9280922aa: a merge copies the merged-away row's layers onto the key's holder under merged
names - all unregistered, all of one rank - so among the copies the stamp decides. Copied with
one stamp, the NAME decided: a row that showed chain:b's later value came out showing chain:a's
earlier one (the 08-11 defect, inside a merge). Stamped in the row's own delivery order, the copy
of the value it showed is the newest - whichever name came later:

  n   chain:a 1, then chain:b 2     one stamp for all copies shows 1
  h   chain:b x, then chain:a y     copies stamped in the order they are read (by name) show x
  t   chain:a p, chain:b q at ONE   the row shows q - one instant, the later line (rank 2c; the name
      time                          deciding a tie, stored before 9280922aa, has no line); its copies keep it
On the lines (the overhaul): the copies are the holder's lines under merged names (`lines.layers`).
"""
import os
import sys

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import retire_dynamic_model                            # noqa: E402
from database import crud, lines, models, schemas                    # noqa: E402
from database.database import Base                                   # noqa: E402

TABLE = "mk_rows"
COLUMNS = {"k": "string", "job": "string", "x": "number", "y": "number", "n": "string",
           "h": "string", "t": "string"}
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["job", "x", "y"],
                  "column_types": COLUMNS, "display_columns": list(COLUMNS)}}


@pytest.fixture(name="db")
def fixture_db():
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    from tests.support import line_tables

    line_tables.build(engine, TABLE)                                   # the product's shape: a table keeps lines
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _write(db, updates, source, row_id=None):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source,
                                  updated_by="probe")]))
    db.commit()


def test_a_merge_keeps_the_value_the_merged_row_showed(db):
    model = models.DYNAMIC_TABLES[TABLE]
    _write(db, {"job": "J1", "x": 1, "y": 2, "n": "0"}, "chain:p")             # the holder
    _write(db, {"job": "J5", "x": 1, "y": 2, "n": "1", "t": "p"}, "chain:a")   # the row ...
    _write(db, {"job": "J5", "x": 1, "y": 2, "n": "2", "h": "x", "t": "q"}, "chain:b")
    _write(db, {"job": "J5", "x": 1, "y": 2, "h": "y"}, "chain:a")             # ... shows 2, y
    rows = {row.job: row for row in db.query(model)}
    holder, merged = rows["J1"].row_id, rows["J5"].row_id
    from sqlalchemy import text

    db.execute(text('UPDATE "%s" SET at = :at WHERE row_id = :r' % lines.lines_relation(TABLE)),
               {"at": datetime(2026, 10, 1, 9, 0, 0), "r": merged})     # the row's lines at one instant: a tie
    db.commit()
    rows = {row.job: row for row in db.query(model)}
    assert (rows["J5"].n, rows["J5"].h, rows["J5"].t) == ("2", "y", "q")
    _write(db, {"job": "J1", "x": 1, "y": 2}, "chain:m", row_id=merged)        # merged into J1

    assert [row.row_id for row in db.query(model)] == [holder]
    db.expire_all()
    for column, value, writer in (("n", "2", "chain:b"), ("h", "y", "chain:a"), ("t", "q", "chain:b")):
        layers = lines.layers(db, TABLE, [holder], [column])[(holder, column)]
        copies = [name for name in layers if crud.layer_writer(name) in ("chain:a", "chain:b")]
        assert len(copies) == 2 and all(name not in ("chain:a", "chain:b") for name in copies)
        shown, top = crud.compute_priority_value(layers, None, TABLE)
        assert (column, shown) == (column, value), (top, writer)     # the value kept, under the merge's own
        # «collision_merge» line where one wins (write_lines._merge_into) - the copies are the history
        assert getattr(db.query(model).one(), column) == value
