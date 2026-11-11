# -*- coding: utf-8 -*-
"""An alignment rule's decision-key index and a table's map-key index have ONE builder - the scheduler's index line,
at its start and at a Reload (소유자 10-15 «the chain worker builds nothing», 총괄 11-05 ㄱ) - through the one door,
`ensure_model_indexes`, as rows of the one comparison (`models.derived_key_indexes`, 총괄 11-06 ㄷ). They were built in
`models.refresh_dynamic_models` too, which the chain loop, each slot and the watcher run on a Reload: N processes
building one index at once. Until the line builds a new rule's index, the rules list says so (the join's word).

  process \\ Reload          builds a reload index
  chain loop / slot          no (reload_rules -> refresh_dynamic_models, spied)
  watcher                    no (refresh_dynamic_models, spied)
  scheduler's index line     yes - its declared work, once; on PG the indexes stand after its poll;
                             a failure is said in its log (the rules list's word points there)
  rules list                 «no key index on <t> yet» before, nothing after
"""
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from chain import enrich_declarations, synthesis
from chain import ingestion_worker as worker
from database import crud, models

TABLE = "zz_reload_ix"
ENTRY = {"business_key": "row_id", "map_key_columns": ["m"], "column_types": {"m": "string", "k": "string"}}
RULE = {"name": "zz_align", "alignment": True, "source_table": TABLE, "decision_key": ["k"]}


@pytest.fixture(name="spied")
def fixture_spied(monkeypatch):
    called = []
    for name in ("ensure_model_indexes", "_ensure_one_index"):
        monkeypatch.setattr(models, name, lambda *a, _n=name, **k: called.append(_n) or [])
    monkeypatch.setattr(crud, "TABLE_CONFIG", {})
    monkeypatch.setattr(crud, "load_table_config", lambda *a, **k: {TABLE: ENTRY})
    monkeypatch.setattr(enrich_declarations, "declarations", lambda *a, **k: [RULE])
    for name in ("init_dynamic_models", "create_missing_dynamic_tables", "ensure_ingestion_checkpoint_table",
                 "sync_dynamic_tables_schema"):
        monkeypatch.setattr(models, name, lambda *a, **k: [])
    return called


def test_a_chain_loop_or_slot_reload_builds_no_index(spied, monkeypatch):
    for name in ("reload_worker_process_cache", "warmup_worker"):
        monkeypatch.setattr(worker, name, lambda *a, **k: None)
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
    from runtime import system_reload

    worker.reload_rules(system_reload.FULL)
    assert crud.TABLE_CONFIG == {TABLE: ENTRY}, "CANARY: the reload read the declarations"
    assert spied == []


def test_the_watchers_reload_builds_no_index(spied):
    models.refresh_dynamic_models(object())                 # run_watcher's call on a FULL reload
    assert crud.TABLE_CONFIG == {TABLE: ENTRY}, "CANARY"
    assert spied == []


def test_the_index_lines_reload_runs_the_declared_work_once(monkeypatch):
    from runtime import index_wants, maintenance_line, system_reload
    import event_constants

    ran = []
    for name in ("_ensure_declared_indexes_sync",):
        monkeypatch.setattr(worker, name, lambda *a, _n=name: ran.append(_n))
    for name in ("ensure_model_indexes_sync", "ensure_auto_indexes_sync"):
        monkeypatch.setattr(models, name, lambda *a, _n=name: ran.append(_n))
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
    monkeypatch.setattr(system_reload, "reloads_after", lambda db, mark: [type("_Row", (), {"id": 1})()])
    monkeypatch.setattr(system_reload, "reload_for", lambda reader, rows, released=None: system_reload.FULL)
    monkeypatch.setattr(event_constants, "mark_processed", lambda row, status: None)
    monkeypatch.setattr(index_wants, "taken", lambda db: [])

    class _Db:
        def commit(self):
            pass

        def close(self):
            pass

    maintenance_line.poll_once(_Db, 0)
    assert ran.count("ensure_model_indexes_sync") == 1


def test_a_failed_build_is_said_in_the_lines_log(monkeypatch):
    """The rules list says «auto_update.log says why» - a failure goes to the logger, not to stdout."""
    said = []
    monkeypatch.setattr(worker, "logger", type("_Log", (), {"warning": staticmethod(said.append),
                                                         "info": staticmethod(lambda *a: None)})())
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    monkeypatch.setattr(enrich_declarations, "declarations", lambda *a, **k: [RULE])

    class _Refuses:
        def connect(self):
            raise RuntimeError("no database here")

    class _Db:
        def get_bind(self):
            return _Refuses()

        def close(self):
            pass

    models.ensure_model_indexes_sync(_Db, ("model", "table"), worker.logger.warning)     # the line's call
    assert any("the declared indexes of model/table were not compared" in line for line in said), said


@pytest.mark.pg
def test_on_postgresql_the_line_builds_them_and_the_rules_list_said_so_before(pg_session, monkeypatch):
    from runtime import index_wants, maintenance_line, system_reload

    engine = pg_session.get_bind()
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    stood = [{"name": RULE["name"], "params": RULE}]
    # the rules as this process loaded them - the scheduler's own reading (`declared_chain_rules`), no other
    monkeypatch.setattr(worker, "declared_chain_rules", lambda: stood)
    monkeypatch.setattr(worker, "_ensure_declared_indexes_sync", lambda *a: None)
    monkeypatch.setattr(models, "ensure_auto_indexes_sync", lambda *a: None)
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
    monkeypatch.setattr(index_wants, "taken", lambda db: [])
    with engine.begin() as c:
        c.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))
        c.execute(text('CREATE TABLE "%s" (row_id varchar PRIMARY KEY, m varchar, k varchar, updated_at timestamp)'
                       % TABLE))
    try:
        declared = {row["name"]: row["state"] for row in models.index_states(engine)["declared"]
                    if row["table"] == TABLE}
        assert {name: declared.get(name) for name in ("idx_%s_map_key" % TABLE, "idx_%s_decision_key" % TABLE)} == {
            "idx_%s_map_key" % TABLE: models.INDEX_MISSING, "idx_%s_decision_key" % TABLE: models.INDEX_MISSING}
        assert synthesis.rules_without_key_index(pg_session, stood) == {RULE["name"]: ([TABLE], None)}
        assert synthesis.no_key_index_line([TABLE]) == synthesis.NO_KEY_INDEX_LINE % TABLE
        factory = sessionmaker(bind=engine)
        db = factory()
        try:
            mark = system_reload.latest_reload_id(db)
            system_reload.publish_reload(db)
            db.commit()
        finally:
            db.close()
        maintenance_line.poll_once(factory, mark)
        with engine.connect() as c:
            held = {row[0] for row in c.execute(text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = :t"),
                {"t": TABLE})}
        assert {"idx_%s_map_key" % TABLE, "idx_%s_decision_key" % TABLE} <= held, held
        assert synthesis.rules_without_key_index(pg_session, stood) == {}
    finally:
        pg_session.rollback()
        with engine.begin() as c:
            c.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))
