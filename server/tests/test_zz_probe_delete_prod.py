# -*- coding: utf-8 -*-
"""SCRATCH PROBE - not committed. «Delete every row» row by row at production shape on a throwaway DB: a 100-column
table with 16 layers a row, audit_logs and cell_sources filled by SQL to production counts, stage by stage.
PROBE_AUDIT / PROBE_LAYERS_OTHER: rows put in audit_logs / cell_sources (other tables) before the op."""
import json
import os
import time

import pytest
from sqlalchemy import MetaData, text

from chain import replay
from conftest import PG_TEST_SCHEMA, retire_dynamic_model
from database import crud, models

pytestmark = pytest.mark.pg
OUT = os.environ.get("PROBE_OUT", "probe_prod.jsonl")
N = int(os.environ.get("PROBE_N", "1000"))
AUDIT = int(os.environ.get("PROBE_AUDIT", "0"))
OTHER = int(os.environ.get("PROBE_LAYERS_OTHER", "0"))
MARKS = int(os.environ.get("PROBE_OVERWRITES_OTHER", "0"))
WIDE, LAYERS = 100, 16
TABLE = "zz_wide"


@pytest.fixture(name="wide")
def fixture_wide(pg_engine, monkeypatch):
    config = {TABLE: {"business_key": "k", "composite_key_source": ["k"],
                      "column_types": {"k": "string", **{"c%03d" % i: "string" for i in range(WIDE)}}}}
    retire_dynamic_model(TABLE)
    models.init_dynamic_models(config)
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, config[TABLE])
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))
    retire_dynamic_model(TABLE)


VARIANTS = [v for v in os.environ.get("PROBE_VARIANTS", "none").split(";") if v]


def _rows(engine):
    """The wide table's rows and their 16 layers, put back for the next variant."""
    cols = ", ".join("c%03d" % i for i in range(WIDE))
    vals = ", ".join("'v%d-' || g" % i for i in range(WIDE))
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM "%s"' % TABLE))
        conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": TABLE})
        conn.execute(text('INSERT INTO "%s" (row_id, k, business_key_val, %s) SELECT \'r\' || lpad(g::text, 8, \'0\'), '
                          "'k' || g, 'k' || g, %s FROM generate_series(1, :n) g" % (TABLE, cols, vals)), {"n": N})
        conn.execute(text("INSERT INTO cell_sources (table_name, row_id, column_name, source_name, value, updated_by) "
                          "SELECT :t, 'r' || lpad(g::text, 8, '0'), 'c' || lpad((l % 100)::text, 3, '0'), "
                          "CASE WHEN l < 8 THEN 'file_a' ELSE 'chain_ingestion' END, to_json('x' || g), 'seed' "
                          "FROM generate_series(1, :n) g, generate_series(0, :l - 1) l"), {"t": TABLE, "n": N, "l": LAYERS})


def _fill(engine):
    cols = ", ".join("c%03d" % i for i in range(WIDE))
    vals = ", ".join("'v%d-' || g" % i for i in range(WIDE))
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO "%s" (row_id, k, business_key_val, %s) SELECT \'r\' || lpad(g::text, 8, \'0\'), '
                          "'k' || g, 'k' || g, %s FROM generate_series(1, :n) g" % (TABLE, cols, vals)), {"n": N})
        conn.execute(text("INSERT INTO cell_sources (table_name, row_id, column_name, source_name, value, updated_by) "
                          "SELECT :t, 'r' || lpad(g::text, 8, '0'), 'c' || lpad((l % 100)::text, 3, '0'), "
                          "CASE WHEN l < 8 THEN 'file_a' ELSE 'chain_ingestion' END, to_json('x' || g), 'seed' "
                          "FROM generate_series(1, :n) g, generate_series(0, :l - 1) l"), {"t": TABLE, "n": N, "l": LAYERS})
        if OTHER:
            conn.execute(text("INSERT INTO cell_sources (table_name, row_id, column_name, source_name, value, updated_by) "
                              "SELECT 'other_' || (g % 7), md5(g::text), 'c' || (g % 40), 'file_a', to_json(g), 'seed' "
                              "FROM generate_series(1, :n) g"), {"n": OTHER})
        if MARKS:
            conn.execute(text("INSERT INTO cell_overwrites (table_name, row_id, column_name, is_overwrite, updated_by) "
                              "SELECT 'other_' || (g % 7), md5(g::text), 'c' || (g % 40), true, 'seed' "
                              "FROM generate_series(1, :n) g"), {"n": MARKS})
            conn.execute(text("ANALYZE cell_overwrites"))
        if AUDIT:
            conn.execute(text("INSERT INTO audit_logs (table_name, row_id, column_name, old_value, new_value, source_name, "
                              "updated_by, transaction_id, timestamp, business_key) "
                              "SELECT 'other_' || (g % 7), md5(g::text), 'c' || (g % 40), NULL, to_json(g), 'file_a', "
                              "'seed', 'tx' || (g / 2000), now() - (g || ' seconds')::interval, 'bk' || g "
                              "FROM generate_series(1, :n) g"), {"n": AUDIT})
        conn.execute(text("ANALYZE cell_sources"))
        conn.execute(text("ANALYZE audit_logs"))
        conn.execute(text('ANALYZE "%s"' % TABLE))


def _timed(monkeypatch, owner, name, label, spent):
    real = getattr(owner, name)

    def wrap(*a, **k):
        began = time.perf_counter()
        try:
            return real(*a, **k)
        finally:
            spent[label] = spent.get(label, 0.0) + time.perf_counter() - began
    monkeypatch.setattr(owner, name, wrap)


def test_probe(wide, monkeypatch, pg_session):
    import database.database as dbmod
    import session_contract
    from sqlalchemy import event

    began = time.perf_counter()
    _fill(wide)
    seed = time.perf_counter() - began
    db = pg_session
    spent, sql = {}, {}

    @event.listens_for(wide, "before_cursor_execute")
    def _b(conn, cur, stmt, *a):
        conn.info["t"] = time.perf_counter()

    @event.listens_for(wide, "after_cursor_execute")
    def _a(conn, cur, stmt, *a):
        label = " ".join(stmt.split())[:60]
        held = sql.setdefault(label, [0.0, 0])
        held[0] += time.perf_counter() - conn.info["t"]
        held[1] += 1

    for owner, name, label in ((crud, "delete_rows_batch", "delete_rows_batch (all)"),
                               (crud, "delete_row_layers", "  layers"),
                               (crud, "record_row_deletions", "  audit write"),
                               (dbmod, "stage_collapsed_event", "  outbox event"),
                               (session_contract, "end_step", "  commit")):
        _timed(monkeypatch, owner, name, label, spent)
    for variant in VARIANTS:
        if variant != VARIANTS[0]:
            _rows(wide)
        dropped = [name for name in variant.split(",") if name != "none"]
        with wide.begin() as conn:
            defs = {name: conn.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = :n "
                                            "AND schemaname = current_schema()"), {"n": name}).scalar()
                    for name in dropped}
            assert all(defs.values()), defs
            for name in dropped:
                conn.execute(text('DROP INDEX "%s"' % name))
            conn.execute(text("ANALYZE cell_sources"))
            conn.execute(text("ANALYZE cell_overwrites"))
        spent.clear()
        sql.clear()
        db.expire_all()
        began = time.perf_counter()
        stats = replay.delete_every_row(db, TABLE, apply=True, log=lambda m: None)
        op = time.perf_counter() - began
        with wide.begin() as conn:
            for name in dropped:
                conn.execute(text(defs[name]))
        top = sorted(sql.items(), key=lambda kv: -kv[1][0])[:5]
        line = {"variant": variant, "n": N, "audit": AUDIT, "other_layers": OTHER, "other_marks": MARKS, "seed_s": round(seed, 1),
                "op_s": round(op, 3), "rows_per_s": round(N / op, 1), "pages": stats["pages"],
                "stages_ms_per_row": {k: round(v * 1000 / N, 3) for k, v in spent.items()},
                "top_sql": [[k, round(v[0], 3), v[1]] for k, v in top]}
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        assert stats["rows_deleted"] == N
