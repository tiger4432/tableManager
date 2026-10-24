# -*- coding: utf-8 -*-
"""총괄 10-24: the write funnel reads the stored layers of the columns its batch WRITES, not of every column - box
board B read six columns' 6,000 layers to write one column of 1,000 rows. The proof that a cache miss is an absence
is by (row, column) (`crud.LayersRead`); a collision merge reads every column of its two rows and primes them first.

  the answer          the same before-state and batch, the funnel as it stands and a funnel told nothing up front
                      (every cell it did not cache asked of the database): the same rows, layers, overwrites, outbox
                      and audit lines
  the axes            a new row · a row written its own value (skipped) · a changed value · a person's write (a line
                      a cell) · a machine's write (a ROW_UPDATE line) · a key rewritten onto another row (merge) · that
                      merge's two rows holding layers in columns the batch does not write · a `write` notation fold ·
                      a file layer repeating an older file's value (fold) · a map replaced (`replace_map` diff)
                      - each first shown to happen in the before/after (a canary), else its comparison proves nothing
  what it saves       20 rows x 6 columns of layers, one column written: 20 layers read, not 120
"""
import json
import os
import re
import sys

import pytest
from sqlalchemy import MetaData, event, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from database import crud, models, schemas                           # noqa: E402

pytestmark = pytest.mark.pg
TABLE = "lr_cells"
COLUMNS = {"k": "string", "job": "string", "x": "number", "y": "number", "a": "number", "b": "string",
           "c": "string", "lot": "string"}
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["job", "x", "y"], "map_key_columns": ["job"],
                  "column_types": COLUMNS, "display_columns": list(COLUMNS)}}
VOLATILE = {"transaction_id", "timestamp", "created_at", "updated_at", "processed_at",
            "broadcast_at", "event_uuid", "ingested_at", "id", "tx_id"}


@pytest.fixture(name="world")
def fixture_world(pg_engine, tmp_path, monkeypatch):
    import notation_norm
    from database import config_watcher

    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    rules = tmp_path / "notation_rules.json"
    rules.write_text(json.dumps({"columns": {TABLE: {"lot": {"write": True, "rules": {"replace": [[" *[.] *", "."]]}}}}}),
                     encoding="utf-8")
    monkeypatch.setattr(notation_norm, "NOTATION_RULES_PATH", str(rules))
    config_watcher.forget_held()
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
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)
        config_watcher.forget_held()


def _item(updates, source, row_id=None):
    return schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source, updated_by="probe")


def _at(job, x, y, **values):
    return {"job": job, "x": x, "y": y, **values}


def _write(db, items, **batch):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=items, **batch))
    db.commit()


def _clean(world):
    with world["engine"].begin() as conn:
        conn.execute(text('DELETE FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
            conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, table)), {"t": TABLE})


def _ids(world):
    with world["engine"].connect() as conn:
        return {"%s/%s/%s" % (r[0], int(r[1]), int(r[2])): r[3] for r in conn.execute(text(
            'SELECT job, x, y, row_id FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))}


def _scenario(world):
    """The before-state, then the batch under test and a map replaced. -> (before, after) dumps."""
    db = world["db"]
    _clean(world)
    _write(db, [_item(_at("J1", 1, 1, a=1, b="pb"), "user"),
                _item(_at("J1", 1, 1, c="pc"), "chain:p"),
                _item(_at("J1", 1, 2, a=2, c="qc"), "chain:q"),
                _item(_at("J1", 1, 2, b="qb"), "user"),
                _item(_at("J2", 1, 1, a=3, b="rb", lot="L.1"), "chain:r"),
                _item(_at("J4", 1, 1, a=3, c="sc"), "chain:s"),
                _item(_at("J3", 1, 1, a=5), "f1.csv")])
    _write(db, [_item(_at("J3", 1, 1, a=6), "f2.csv")])
    _write(db, [_item(_at("J7", x, y, b="m%d%d" % (x, y)), "user") for x, y in ((1, 1), (1, 2), (2, 1))],
           replace_map=True, scope={"job": "J7"})
    _write(db, [_item(_at("J7", x, y, c="mc"), "chain:m7") for x, y in ((1, 1), (1, 2), (2, 1))])
    ids = _ids(world)
    crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": ids["J1/1/1"], "column_name": "a"}], "user")
    db.commit()
    before = _dump(world, ids)
    _write(db, [
        _item(_at("J9", 1, 1, a=9), "chain:a"),                               # a new row
        _item(_at("J4", 1, 1, a=3), "chain:s"),                               # its own value: skipped
        _item(_at("J2", 1, 1, a=4), "user"),                                  # changed, by a person
        _item(_at("J2", 1, 1, lot="L . 2"), "chain:r"),                       # folded as written
        _item(_at("J1", 1, 1, a=7), "user", row_id=ids["J1/1/2"]),            # Q re-keyed onto P: merge
        _item(_at("J3", 1, 1, a=5), "f3.csv"),                                # f1's 5 again: f1 folds
    ])
    _write(db, [_item(_at("J7", x, y, b="n%d%d" % (x, y)), "user") for x, y in ((1, 1), (2, 1))],
           replace_map=True, scope={"job": "J7"})
    return before, _dump(world, {**ids, **_ids(world)})


def _dump(world, ids):
    s = PG_TEST_SCHEMA
    named = {row_id: "<%s>" % key for key, row_id in ids.items()}
    with world["engine"].connect() as conn:
        def q(sql):
            return [dict(r._mapping) for r in conn.execute(text(sql))]

        def norm(value):
            if isinstance(value, dict):
                return {k: norm(v) for k, v in sorted(value.items()) if k not in VOLATILE}
            if isinstance(value, list):
                return [norm(v) for v in value]
            if isinstance(value, str) and value in named:
                return named[value]
            if isinstance(value, str):      # a merged layer's name carries its row id's first six (uuid7: its time)
                return re.sub(r"_[0-9a-f]{6}\)$", "_<id6>)", value)
            return value

        def lines(table):
            return sorted(json.dumps(norm(r), sort_keys=True, default=str) for r in q(
                "SELECT * FROM \"%s\".%s WHERE table_name = '%s'" % (s, table, TABLE)))
        rows = {named.get(r["row_id"], r["row_id"]): {c: r[c] for c in COLUMNS} for r in q(
            'SELECT row_id, %s FROM "%s"."%s"' % (", ".join('"%s"' % c for c in COLUMNS), s, TABLE))}
        return {"rows": rows, "cell_sources": lines("cell_sources"), "cell_overwrites": lines("cell_overwrites"),
                "outbox": lines("database_outbox"), "audit": lines("audit_logs")}


def _layers(dump, row, column):
    return {json.loads(line)["source_name"]: json.loads(line)["value"] for line in dump["cell_sources"]
            if json.loads(line)["row_id"] == row and json.loads(line)["column_name"] == column}


def _audit(dump, row, **cells):
    return [json.loads(line) for line in dump["audit"] if json.loads(line)["row_id"] == row
            and all(json.loads(line).get(k) == v for k, v in cells.items())]


def test_the_funnel_answers_as_a_funnel_told_nothing_up_front(world, monkeypatch):
    before, product = _scenario(world)
    p, q, r, s, f, n = "<J1/1/1>", "<J1/1/2>", "<J2/1/1>", "<J4/1/1>", "<J3/1/1>", "<J9/1/1>"
    # the axes, each shown to happen - else its comparison below is empty
    assert n in product["rows"] and n not in before["rows"], "canary: a new row"
    assert _audit(product, s) == _audit(before, s) and product["rows"][s]["a"] == 3, "canary: S written 3 again"
    assert _audit(product, r, column_name="a", source_name="user"), "canary: a person's line a cell"
    assert _audit(product, n, column_name="ROW_UPDATE"), "canary: a machine's ROW_UPDATE line"
    assert product["rows"][r]["lot"] == "L.2" and _audit(product, r, old_value="L . 2"), "canary: folded as written"
    assert q not in product["rows"] and _audit(product, p, source_name="collision_merge"), "canary: Q merged into P"
    assert "user" in _layers(before, q, "b") and "chain:q" in _layers(before, q, "c"), "canary: Q's other columns"
    assert "chain:q (J1_1_2_<id6>)" in _layers(product, p, "c"), ("canary: the merge moved a layer of a column the batch did not "
                                                   "write", _layers(product, p, "c"))
    assert "f1.csv" in _layers(before, f, "a") and "f1.csv" not in _layers(product, f, "a"), "canary: f1 folded"
    assert "<J7/1/2>" in before["rows"] and "<J7/1/2>" not in product["rows"], "canary: the map's dropped cell"
    assert any('"manual_priority_source": "user"' in line for line in before["cell_overwrites"]), "canary: P pinned"

    real = crud._load_metadata_row_cell

    def asks_the_database(db, table_name, row_id, col_name, is_new, sources_cache, overwrites_cache,
                          cell_sources_to_upsert, cell_overwrites_to_upsert, layers_read=None):
        return real(db, table_name, row_id, col_name, is_new, sources_cache, overwrites_cache,
                    cell_sources_to_upsert, cell_overwrites_to_upsert, None)
    monkeypatch.setattr(crud, "_load_metadata_row_cell", asks_the_database)
    _before, oracle = _scenario(world)

    assert product == oracle


def test_one_column_written_reads_that_columns_layers_only(world):
    db = world["db"]
    _clean(world)
    _write(db, [_item(_at("J5", i, 1, a=i, b="b", c="c", lot="L"), "chain:w") for i in range(20)])
    read = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("SELECT") and "FROM cell_sources" in statement:
            read.append(cursor.rowcount)
    event.listen(world["engine"], "after_cursor_execute", count)
    try:
        _write(db, [_item(_at("J5", i, 1, a=i + 100), "chain:w") for i in range(20)])
    finally:
        event.remove(world["engine"], "after_cursor_execute", count)
    with world["engine"].connect() as conn:
        stored = conn.execute(text("SELECT count(*) FROM \"%s\".cell_sources WHERE table_name = :t"
                                   % PG_TEST_SCHEMA), {"t": TABLE}).scalar()
    assert stored == 20 * 8, "canary: a layer in each of the eight columns (keys included) of 20 rows"
    # the batch writes a and the four key columns (the key is assembled into `k`)
    assert sum(read) == 20 * 5, read
