# -*- coding: utf-8 -*-
"""On PostgreSQL - where ops runs - a table with a `"year": "arrival"` time column backfills by the row path, each
layer with the year it came in; its fold is not a function of the spelling, so the page by value (`_fold_by_values`)
would give one spelling one year (lead 11-10). A control table with a spelling rule still folds by value, so the
answer is of two paths, not of one path twice."""
import json
import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import MetaData, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                              # noqa: E402
import notation_norm as nn                                          # noqa: E402
from chain import replay                                            # noqa: E402
from conftest import PG_TEST_SCHEMA, _declared_as_test_database, _resolve_pg_test_url, retire_dynamic_model  # noqa: E402
from database import crud, models, schemas                          # noqa: E402

pytestmark = pytest.mark.pg

ARRIVAL, CONTROL = "pgqa_arr_dates", "pgqa_arr_control"
TABLES = {t: {"business_key": "k", "column_types": {"k": "string", "seen": "string"}} for t in (ARRIVAL, CONTROL)}
DECLARED = {ARRIVAL: {"seen": {"write": True, "rules": {"time": {"from": ["%m월 %d일"], "year": "arrival"}}}},
            CONTROL: {"seen": {"write": True, "rules": {"replace": [["x", "y"]]}}}}


def _declare(path, columns):
    path.write_text(json.dumps({"columns": columns}, ensure_ascii=False), encoding="utf-8")
    from database import config_watcher
    config_watcher.forget_held()


@pytest.fixture(scope="module")
def folded(pg_engine, tmp_path_factory):
    from sqlalchemy.orm import sessionmaker

    from database.context import channel

    url, _ = _resolve_pg_test_url()
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for t in TABLES:
        models.DYNAMIC_TABLES[t].__table__.to_metadata(scratch, schema=None)
    emptied = ", ".join('"%s"."%s"' % (PG_TEST_SCHEMA, t) for t in
                        ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox", *TABLES))
    rules_path = tmp_path_factory.mktemp("arr") / "notation_rules.json"
    out = {"by_value": []}
    real_by_values = replay._fold_by_values

    def by_values(*args, **kwargs):
        out["by_value"].append(args[1])
        return real_by_values(*args, **kwargs)

    with _declared_as_test_database(url), pytest.MonkeyPatch.context() as mp:
        mp.setattr(nn, "NOTATION_RULES_PATH", str(rules_path))
        mp.setattr(replay, "_fold_by_values", by_values)
        scratch.create_all(pg_engine)
        db = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
        try:
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            out["schema"] = db.execute(text("SELECT current_schema()")).scalar()
            _declare(rules_path, {})
            for source, year in (("f24.csv", 2024), ("f25.csv", 2025)):
                for table in TABLES:
                    with channel(event_constants.CHANNEL_API):
                        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
                            schemas.GeneralUpdateItem(updates={"k": "K%d" % year, "seen": "3월 5일"},
                                                      source_name=source, updated_by="seed", business_key_val="K%d" % year)
                            ], silent=True))
                    db.commit()
                db.query(models.CellSource).filter(models.CellSource.source_name == source).update(
                    {"ingested_at": datetime(year, 6, 1, 12, 0, 0)}, synchronize_session=False)
                db.commit()
            _declare(rules_path, DECLARED)
            out["dialect"] = db.get_bind().dialect.name
            for table in TABLES:
                out[table] = replay.fold_written_notation(db, table, apply=True, log=lambda m: None)
            db.expire_all()
            out["shown"] = {t: sorted((r.k, r.seen) for r in db.query(models.DYNAMIC_TABLES[t])) for t in TABLES}
            out["layers"] = sorted((s.table_name, s.row_id is not None and s.source_name, s.value)
                                   for s in db.query(models.CellSource).filter(
                                       models.CellSource.table_name.in_(list(TABLES)),
                                       models.CellSource.column_name == "seen"))
        finally:
            db.close()
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            scratch.drop_all(pg_engine, tables=[scratch.tables["%s.%s" % (PG_TEST_SCHEMA, t)] for t in TABLES])
            from database import config_watcher
            config_watcher.forget_held()
            for t in TABLES:
                crud.TABLE_CONFIG.pop(t, None)
                retire_dynamic_model(t)
    return out


def test_it_ran_on_postgresql_in_the_scratch_schema(folded):
    assert (folded["dialect"], folded["schema"]) == ("postgresql", PG_TEST_SCHEMA)


def test_the_control_folds_by_value_and_the_arrival_table_does_not(folded):
    assert CONTROL in folded["by_value"] and ARRIVAL not in folded["by_value"], folded["by_value"]


def test_each_layer_takes_the_year_it_came_in(folded):
    assert folded["shown"][ARRIVAL] == [("K2024", "2024-03-05 00:00:00"), ("K2025", "2025-03-05 00:00:00")]
    assert [(source, value) for table, source, value in folded["layers"] if table == ARRIVAL] == [
        ("f24.csv", "2024-03-05 00:00:00"), ("f25.csv", "2025-03-05 00:00:00")]
    assert folded[ARRIVAL]["layers_folded"] == 2 and folded[ARRIVAL]["time_left"] == {}
