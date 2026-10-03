# -*- coding: utf-8 -*-
"""총괄 6e2a93ef9: rows keyed in the old spelling (e243d6abf ③) are found by the census and
rewritten by `rebuild_blank_business_keys --apply` through `crud.put_business_key` - the key and,
on a table that declares one, its business_key column - with an audit line. A row whose rebuilt key
another row holds is skipped and named until the owner answers. After the rewrite the same payload
lands on its row: one row, no merge."""
import os
import sys

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in (SERVER_DIR, os.path.join(SERVER_DIR, "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
import event_constants                                              # noqa: E402
import rebuild_blank_business_keys as rekey                         # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402

pytestmark = pytest.mark.pg
T_ONLY, T_KEY = "zz_rekey_only", "zz_rekey_key"
TYPES = {"lot": "string", "wafer": "number", "t": "datetime", "v": "string"}
TABLES = {
    T_ONLY: {"composite_key_source": ["lot", "wafer", "t"], "column_types": dict(TYPES)},
    T_KEY: {"business_key": "bk", "composite_key_source": ["lot", "wafer", "t"],
            "column_types": {"bk": "string", **TYPES}},
}
WHEN = "2026-10-03 12:00:00"


@pytest.fixture(name="db")
def fixture_db(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    saved = dict(crud.TABLE_CONFIG)
    for name in TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)

    def clean():
        with pg_engine.begin() as conn:
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                for side in ("cell_sources", "cell_overwrites", "database_outbox", "audit_logs"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t'
                                      % (PG_TEST_SCHEMA, side)), {"t": name})

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    maker = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    session = maker()
    try:
        yield {"db": session, "maker": maker, "engine": pg_engine}
    finally:
        session.close()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in TABLES:
            retire_dynamic_model(name)


def _write(db, table, row):
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(row), source_name="parser_a", updated_by="t")]))
        db.commit()


def _old_spelling(world, table, lot, old):
    """What a row written before ③ carries: its key in the payload's spelling."""
    key_column = TABLES[table].get("business_key")
    with world["engine"].begin() as conn:
        conn.execute(text('UPDATE "%s"."%s" SET business_key_val = :k%s WHERE lot = :l'
                          % (PG_TEST_SCHEMA, table, ", %s = :k" % key_column if key_column else "")),
                     {"k": old, "l": lot})


def _plan(world, table):
    sources = TABLES[table]["composite_key_source"]
    with world["engine"].connect() as conn:
        rows = conn.execute(text('SELECT row_id, business_key_val, %s FROM "%s"."%s"'
                                 % (", ".join(sources), PG_TEST_SCHEMA, table))).mappings().all()
    return rekey.plan_rekeys(table, rows, sources, "_")


def _rows(world, table, lot):
    key_column = TABLES[table].get("business_key") or "business_key_val"
    with world["engine"].connect() as conn:
        return conn.execute(text('SELECT row_id, business_key_val, %s FROM "%s"."%s" WHERE lot = :l'
                                 % (key_column, PG_TEST_SCHEMA, table)), {"l": lot}).all()


@pytest.mark.parametrize("table", [T_ONLY, T_KEY])
def test_an_old_spelled_row_is_rewritten_and_the_same_data_lands_on_it(db, table):
    _write(db["db"], table, {"lot": "L1", "wafer": "1", "t": WHEN, "v": "a"})
    _old_spelling(db, table, "L1", "L1_1.0_2026-10-03 12:00")
    # a pair that collides: B's rebuilt key is the key C was given after B went old
    _write(db["db"], table, {"lot": "L2", "wafer": "2", "t": WHEN, "v": "b"})
    _old_spelling(db, table, "L2", "L2_2.0_2026-10-03 12:00")
    _write(db["db"], table, {"lot": "L2", "wafer": "2", "t": WHEN, "v": "c"})

    plan = _plan(db, table)
    (old_row,) = [r for r in _rows(db, table, "L1")]
    assert [row_id for row_id, _key in plan["pending"]] == [old_row[0]]
    assert plan["stat"]["collides"] == 1 and plan["moved_by"] == {"datetime + number": 2}
    (skipped, holder, key), = plan["collide_sample"]
    assert key == "L2_2_2026-10-03 12:00:00" and skipped != holder

    assert rekey.apply_rekeys(db["db"], table, plan["pending"], "tester") == 1
    assert _rows(db, table, "L1") == [(old_row[0], "L1_1_2026-10-03 12:00:00",
                                       "L1_1_2026-10-03 12:00:00")]   # both key cells
    with db["engine"].connect() as conn:
        audit = conn.execute(text('SELECT old_value, new_value, updated_by FROM "%s".audit_logs '
                                  "WHERE table_name = :t AND source_name = :s"
                                  % PG_TEST_SCHEMA), {"t": table, "s": rekey.REKEY_SOURCE}).all()
    assert [tuple(map(str, a)) for a in audit] == [
        ("L1_1.0_2026-10-03 12:00", "L1_1_2026-10-03 12:00:00", "tester")]

    _write(db["db"], table, {"lot": "L1", "wafer": "1.0", "t": "2026-10-03 12:00", "v": "again"})
    assert len(_rows(db, table, "L1")) == 1                         # found, not a new row
    with db["engine"].connect() as conn:
        merges = conn.execute(text('SELECT count(*) FROM "%s".audit_logs WHERE table_name = :t '
                                   "AND source_name = 'collision_merge'" % PG_TEST_SCHEMA),
                              {"t": table}).scalar()
    assert merges == 0
    again = _plan(db, table)
    assert (again["pending"], again["stat"]["collides"]) == ([], 1)  # the skipped pair stays named
