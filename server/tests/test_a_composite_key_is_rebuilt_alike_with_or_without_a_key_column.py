# -*- coding: utf-8 -*-
"""총괄 a61d32f4f 답 ㄱ: a table that declares only `composite_key_source` rebuilds its key by the
same mechanism, with the same answer, as one that also carries a `business_key` column.

One fixture, run on both shapes (each with its `uq_bk_` index, as every keyed table in an install
has); each branch must leave the same rows, keys, values and layers - the `business_key` column
itself is the only thing one shape has and the other has not.

  by key               create, write again by key                    one row
  named id             create under a uuid7, write again by key      one row
  grid                 an empty row, key parts typed by its id       one row
  part edited          a key part written by id                      key rebuilt, by key finds it
  part blanked         a key part blanked by id                      key NULL
  edited onto a key    another row holds the new key                 merged, one row
  pinned               a pin moves a key part's shown value          key rebuilt
"""
import os
import sys

import pytest
import uuid6
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from database import crud, models, schemas                           # noqa: E402

pytestmark = pytest.mark.pg
PARTS = ["job", "x", "y"]
COLUMNS = {"job": "string", "x": "number", "y": "number", "netdie": "number"}
SHAPES = {
    "rk_key": {"business_key": "k", "composite_key_source": PARTS,
               "column_types": {"k": "string", **COLUMNS}},
    "rk_parts": {"composite_key_source": PARTS, "column_types": dict(COLUMNS)},
}


@pytest.fixture(name="world")
def fixture_world(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    config = {t: {**c, "display_columns": list(c["column_types"])} for t, c in SHAPES.items()}
    saved = dict(crud.TABLE_CONFIG)
    for table in SHAPES:
        retire_dynamic_model(table)
    models.init_dynamic_models(config)
    crud.TABLE_CONFIG.update(config)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for table in SHAPES:
        models.DYNAMIC_TABLES[table].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    with pg_engine.begin() as conn:
        for table in SHAPES:
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "uq_bk_%s" ON "%s"."%s" (business_key_val)'
                              % (table, PG_TEST_SCHEMA, table)))
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        yield {"db": session, "engine": pg_engine}
    finally:
        session.close()
        with pg_engine.begin() as conn:
            for table in SHAPES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, table)))
                for side in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t'
                                      % (PG_TEST_SCHEMA, side)), {"t": table})
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for table in SHAPES:
            retire_dynamic_model(table)


def _write(db, table, items):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source,
                                  updated_by="t") for row_id, updates, source in items]))
    db.commit()


def _part(job, netdie=None):
    return {"job": job, "x": 1, "y": 2, **({} if netdie is None else {"netdie": netdie})}


def _ids(db, table):
    return [r for (r,) in db.execute(text('SELECT row_id FROM "%s"."%s" ORDER BY row_id'
                                          % (PG_TEST_SCHEMA, table)))]


def _by_key(db, table):
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    _write(db, table, [(None, _part("J1", 2), "chain:b")])


def _named(db, table):
    _write(db, table, [(str(uuid6.uuid7()), _part("J1", 1), "chain:a")])
    _write(db, table, [(None, _part("J1", 2), "chain:b")])


def _grid(db, table):
    crud.create_empty_rows_batch(db, table, 1, "t")
    db.commit()
    _write(db, table, [(_ids(db, table)[0], _part("J1", 1), "user")])
    _write(db, table, [(None, _part("J1", 2), "chain:b")])


def _part_edited(db, table):
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    _write(db, table, [(_ids(db, table)[0], {"job": "J2"}, "user")])
    _write(db, table, [(None, _part("J2", 2), "chain:b")])


def _part_blanked(db, table):
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    _write(db, table, [(_ids(db, table)[0], {"job": ""}, "user")])


def _edited_onto_a_key(db, table):
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    first = _ids(db, table)[0]
    _write(db, table, [(None, _part("J2", 2), "chain:a")])
    second = [r for r in _ids(db, table) if r != first][0]
    _write(db, table, [(second, {"job": "J1"}, "user")])


def _pinned(db, table):
    """Three layers on a key part; the pin shows the middle one - a key neither write left."""
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    row = _ids(db, table)[0]
    _write(db, table, [(row, {"job": "J2"}, "chain:b")])
    _write(db, table, [(row, {"job": "J3"}, "chain:c")])
    crud.set_cell_manual_priority_batch(db, table, [{"row_id": row, "column_name": "job"}],
                                        "chain:b")
    db.commit()


BRANCHES = {"by_key": (_by_key, ["J1_1_2"]), "named": (_named, ["J1_1_2"]),
            "grid": (_grid, ["J1_1_2"]), "part_edited": (_part_edited, ["J2_1_2"]),
            "part_blanked": (_part_blanked, [None]),
            "edited_onto_a_key": (_edited_onto_a_key, ["J1_1_2"]),
            "pinned": (_pinned, ["J2_1_2"])}


def _answer(world, table):
    """Rows (key and values) and layers, by key rather than by row_id - ids differ per run."""
    with world["engine"].connect() as conn:
        rows = conn.execute(text('SELECT row_id, business_key_val, job, x, y, netdie FROM "%s"."%s"'
                                 % (PG_TEST_SCHEMA, table))).all()
        key_of = {r[0]: r[1] for r in rows}
        layers = conn.execute(text(
            'SELECT row_id, column_name, source_name, value FROM "%s".cell_sources '
            "WHERE table_name = :t AND column_name <> 'k'" % PG_TEST_SCHEMA), {"t": table}).all()
    return (sorted((r[1] or "", r[2] or "", str(r[3]), str(r[4]), str(r[5])) for r in rows),
            sorted((key_of.get(l[0]) or "", l[1], l[2], l[3] or "") for l in layers))


@pytest.mark.parametrize("branch", list(BRANCHES))
def test_both_shapes_give_one_answer(world, branch):
    build, keys = BRANCHES[branch]
    answers = {}
    for table in SHAPES:
        build(world["db"], table)
        answers[table] = _answer(world, table)
        assert [r[0] or None for r in answers[table][0]] == keys, (table, answers[table][0])
    assert answers["rk_key"] == answers["rk_parts"]
