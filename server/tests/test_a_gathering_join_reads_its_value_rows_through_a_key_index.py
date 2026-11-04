# -*- coding: utf-8 -*-
"""Owner 10-29 «함수조인 ㄱ» (lead): a gathering join (`take ... fn`) reads every value row of the keys a batch touched,
and the value table had no index on the join key - many rows a key, so no unique one - so each batch scanned the
whole value table. The left lookup seat (`declared_lookup_targets` -> `ensure_lookup_once`) now names the value side
of a gathering join too; the index is the key expression the read compares (`notation_norm`, one author).
Owner 11-04 «조인이 너무 느린데»: a plain take without `key.unique` had the same whole-table read (10M value rows: 0.4 -
1.3 s a batch) - its value side is a lookup target too; one with `key.unique` has its unique index instead. A table a
join key index was just built on is analysed whatever it moved, and the rules list says, on a running join's line,
which of its tables has no lookup index standing."""
import os
import sys

import pytest
from sqlalchemy import event, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import join_into, rule_shape, synthesis, unique_key  # noqa: E402
from chain import join_key_index as vjc                         # noqa: E402
from database import crud, models, schemas                     # noqa: E402

TABLES = {"gk_meas": {"business_key": "rid", "composite_key_source": ["rid"],
                      "column_types": {"rid": "string", "lot": "string", "item": "string", "v": "number"},
                      "display_columns": ["rid", "lot", "item", "v"]},
          "gk_tgt": {"business_key": "tid", "composite_key_source": ["tid"],
                     "column_types": {"tid": "string", "lot": "string", "item": "string", "m": "number",
                                      "w": "number"},
                     "display_columns": ["tid", "lot", "item", "m", "w"]}}
VALUE_INDEX = vjc.required_index_name("gk_meas", ["lot", "item"], [None, None], vjc.LOOKUP_PREFIX)


def _stood(take, **cells):
    declaration = {"name": "gk", "on": {"table": "gk_meas"}, "into": {"table": "gk_tgt"}, **cells,
                   "derive": {"kind": "join", "join": {"on": [{"left": c, "right": c} for c in ("lot", "item")],
                                                       "take": take}}}
    stood, refusal, _notes = rule_shape.expand_declaration(declaration, crud.TABLE_CONFIG)
    assert not refusal, refusal
    return stood


@pytest.fixture(name="tables")
def fixture_tables():
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    try:
        yield
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def test_the_value_side_is_a_lookup_target_unless_the_join_has_a_unique_key(tables):
    def targets(take, **cells):
        return {t for t, _c, _f in synthesis.declared_lookup_targets(_stood(take, **cells))}
    gathering = targets([{"from": "v", "into": "m", "fn": "max"}])
    plain = targets([{"from": "v", "into": "w"}])
    unique = targets([{"from": "v", "into": "w"}], key={"unique": True})
    assert (gathering, plain, unique) == ({"gk_tgt", "gk_meas"}, {"gk_tgt", "gk_meas"}, {"gk_tgt"})


def test_a_table_an_index_was_just_built_on_is_analysed_whatever_it_moved(monkeypatch, tables):
    from chain import ingestion_worker as worker
    from parsers import directory_watcher as dw

    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10000)
    analysed = []
    monkeypatch.setattr(dw, "_analyze_after_load",
                        lambda name, rows, why=None, forced=False: analysed.append((name, forced)) or True)

    class _Session:
        def execute(self, statement, params=None):
            return type("_R", (), {"all": lambda self_inner: []})()

        def close(self):
            pass

    assert worker._analyze_stale_tables_sync(lambda: _Session()) == [] and analysed == []
    assert worker._analyze_stale_tables_sync(lambda: _Session(), built={"gk_meas"}) == ["gk_meas"]
    assert analysed == [("gk_meas", True)]


def test_the_index_work_hands_the_tables_it_built_to_the_analyse(monkeypatch, tables):
    from chain import ingestion_worker as worker

    monkeypatch.setattr(synthesis, "ensure_declared_unique_keys", lambda db, rules: {"built": ["gk_tgt"]})
    monkeypatch.setattr(synthesis, "ensure_declared_lookup_keys", lambda db, rules: {"built": ["gk_meas"]})
    monkeypatch.setattr(synthesis, "retract_unrequired_indexes_once", lambda db: {})
    handed = []
    monkeypatch.setattr(worker, "_analyze_stale_tables_sync", lambda factory, built=(): handed.append(set(built)))

    class _Db:
        def close(self):
            pass
    worker._ensure_declared_indexes_sync([], lambda: _Db())
    assert handed == [{"gk_tgt", "gk_meas"}]


def test_a_running_join_without_its_lookup_index_says_so_on_its_line(monkeypatch, tables):
    import main
    from chain import control as chain_control
    from chain import ingestion_worker as worker

    rules = _stood([{"from": "v", "into": "w"}])
    monkeypatch.setattr(worker, "read_rules_document", lambda *_a, **_k: {"exists": True, "error": None, "rules": []})
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: rules)
    monkeypatch.setattr(chain_control, "rules_off", lambda: {})
    monkeypatch.setattr(worker, "refused_chain_rules", lambda: {})
    monkeypatch.setattr(synthesis, "joins_without_lookup_index", lambda db, rules: {"gk": ["gk_meas"]})
    rows = {row["name"]: row for row in main.get_chain_rules(db=None)["data"]}
    assert rows["gk"]["rule_state_detail"] == synthesis.NO_KEY_INDEX_LINE % "gk_meas"
    assert "rule_state_detail" not in rows["gk:target"]


@pytest.mark.pg
def test_the_gathering_read_is_planned_through_the_value_key_index(tables, pg_session):
    db = pg_session
    from database.database import Base

    Base.metadata.create_all(bind=db.get_bind(), tables=[models.DYNAMIC_TABLES[t].__table__ for t in TABLES])
    rules = _stood([{"from": "v", "into": "m", "fn": "max"}])
    unique_key.forget()
    report = synthesis.ensure_declared_lookup_keys(db, rules)
    assert (VALUE_INDEX, "ok") in [(name, one.get("state")) for name, one in report["ensured"]], report
    crud.apply_batch_updates(db, "gk_meas", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"rid": "m%d" % i, "lot": "L1", "item": "I%d" % (i % 3), "v": i},
                                  source_name="seed", updated_by="gk") for i in range(6)]))
    crud.apply_batch_updates(db, "gk_tgt", schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"tid": "t1", "lot": "L1", "item": "I1"}, source_name="seed", updated_by="gk")]))
    db.commit()
    reference = next(r for r in rules if r.get("trigger_table") == "gk_meas")
    row_ids = [r[0] for r in db.execute(text("SELECT row_id FROM gk_meas"))]
    said = []

    def seen(_conn, _cursor, statement, params, _context, _many):
        if "FROM gk_meas" in statement and "coalesce" in statement.lower() and "v" in statement:
            said.append((statement, params))
    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", seen)
    try:
        join_into.read(db, reference, row_ids)
    finally:
        event.remove(engine, "before_cursor_execute", seen)
    assert said, "the read asked the value table nothing - this measures nothing"
    statement, params = said[-1]
    raw = db.connection().connection.dbapi_connection
    with raw.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute("EXPLAIN " + statement, params)
        plan = " / ".join(row[0] for row in cursor.fetchall())
    assert VALUE_INDEX in plan, plan


@pytest.mark.pg
def test_the_list_reads_which_lookup_index_does_not_stand(tables, pg_session):
    db = pg_session
    from database.database import Base

    Base.metadata.create_all(bind=db.get_bind(), tables=[models.DYNAMIC_TABLES[t].__table__ for t in TABLES])
    rules = _stood([{"from": "v", "into": "w"}])
    for table in TABLES:                                    # the gathering test above may have left them
        db.execute(text('DROP INDEX IF EXISTS "%s"' % vjc.required_index_name(table, ["lot", "item"], [None, None],
                                                                              vjc.LOOKUP_PREFIX)))
    db.commit()
    before = synthesis.joins_without_lookup_index(db, rules)
    unique_key.forget()
    report = synthesis.ensure_declared_lookup_keys(db, rules)
    assert sorted(report["built"]) == ["gk_meas", "gk_tgt"], report
    assert before == {"gk": ["gk_tgt", "gk_meas"], "gk:target": ["gk_tgt", "gk_meas"]}
    assert synthesis.joins_without_lookup_index(db, rules) == {}
