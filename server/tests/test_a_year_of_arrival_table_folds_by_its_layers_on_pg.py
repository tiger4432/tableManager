# -*- coding: utf-8 -*-
"""On PostgreSQL - where ops runs - a table with a `"year": "arrival"` time column backfills each layer with the year
it came in (its head line's `at`): its fold is not a function of the spelling, so one spelling folded once would give
one year (lead 11-10). One path since the backfill moved onto lines (A 11-11)."""
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
from database import crud, lines, models, schemas                   # noqa: E402

pytestmark = pytest.mark.pg

ARRIVAL = "pgqa_arr_dates"
TABLES = {ARRIVAL: {"business_key": "k", "column_types": {"k": "string", "seen": "string"}}}
DECLARED = {ARRIVAL: {"seen": {"write": True, "rules": {"time": {"from": ["%m월 %d일"], "year": "arrival"}}}}}


def _declare(path, columns):
    path.write_text(json.dumps({"columns": columns}, ensure_ascii=False), encoding="utf-8")
    from database import config_watcher
    config_watcher.forget_held()


@pytest.fixture(scope="module")
def folded(pg_engine, tmp_path_factory):
    from sqlalchemy.orm import sessionmaker

    import migrations.add_business_key_unique_index as bk
    from database.context import channel

    url, _ = _resolve_pg_test_url()
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[ARRIVAL].__table__.to_metadata(scratch, schema=None)
    emptied = ", ".join('"%s"."%s"' % (PG_TEST_SCHEMA, t) for t in
                        ("cell_overwrites", "database_outbox", ARRIVAL))
    rules_path = tmp_path_factory.mktemp("arr") / "notation_rules.json"
    out = {}
    with _declared_as_test_database(url), pytest.MonkeyPatch.context() as mp:
        mp.setattr(nn, "NOTATION_RULES_PATH", str(rules_path))
        scratch.create_all(pg_engine)
        db = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
        try:
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            # the table as ops keeps it: its key's unique index, then its lines
            db.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "%s" ON "%s" (business_key_val)'
                            % (bk.unique_index_name(ARRIVAL), ARRIVAL)))
            lines.ensure_line_table(db, ARRIVAL, TABLES[ARRIVAL])
            db.commit()
            out["schema"] = db.execute(text("SELECT current_schema()")).scalar()
            _declare(rules_path, {})
            for source, year in (("f24.csv", 2024), ("f25.csv", 2025)):
                with channel(event_constants.CHANNEL_API):
                    crud.apply_batch_updates(db, ARRIVAL, schemas.GeneralUpdateBatch(updates=[
                        schemas.GeneralUpdateItem(updates={"k": "K%d" % year, "seen": "3월 5일"},
                                                  source_name=source, updated_by="seed", business_key_val="K%d" % year)
                        ], silent=True))
                db.commit()
                db.execute(text('UPDATE "%s" SET at = :at WHERE source_name = :s' % lines.lines_relation(ARRIVAL)),
                           {"at": datetime(year, 6, 1, 12, 0, 0), "s": source})
                db.commit()
            _declare(rules_path, DECLARED)
            out["dialect"] = db.get_bind().dialect.name
            out[ARRIVAL] = replay.fold_written_notation(db, ARRIVAL, apply=True, log=lambda m: None)
            db.expire_all()
            model = models.DYNAMIC_TABLES[ARRIVAL]
            out["shown"] = sorted((r.k, r.seen) for r in db.query(model))
            heads = lines.layers(db, ARRIVAL, [r.row_id for r in db.query(model)], ["seen"])
            out["layers"] = sorted((source, head["value"]) for layer in heads.values()
                                   for source, head in layer.items())
        finally:
            db.rollback()
            lines.drop_line_table(db, ARRIVAL)
            db.execute(lines.LineColumn.__table__.delete().where(lines.LineColumn.table_name == ARRIVAL))
            db.execute(lines.AuditBatch.__table__.delete().where(lines.AuditBatch.table_name == ARRIVAL))
            db.commit()
            db.close()
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            scratch.drop_all(pg_engine, tables=[scratch.tables["%s.%s" % (PG_TEST_SCHEMA, ARRIVAL)]])
            from database import config_watcher
            config_watcher.forget_held()
            crud.TABLE_CONFIG.pop(ARRIVAL, None)
            retire_dynamic_model(ARRIVAL)
    return out


def test_it_ran_on_postgresql_in_the_scratch_schema(folded):
    assert (folded["dialect"], folded["schema"]) == ("postgresql", PG_TEST_SCHEMA)


def test_each_layer_takes_the_year_it_came_in(folded):
    assert folded["shown"] == [("K2024", "2024-03-05 00:00:00"), ("K2025", "2025-03-05 00:00:00")]
    assert folded["layers"] == [("f24.csv", "2024-03-05 00:00:00"), ("f25.csv", "2025-03-05 00:00:00")]
    assert folded[ARRIVAL]["layers_folded"] == 2 and folded[ARRIVAL]["time_left"] == {}
