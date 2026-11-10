"""Each part's state in the system catalogue (owner 11-09 step 1): a rule's switch-off, failures in a row and last
evaluation, a table's waiting chain events and row estimate, an ingestion folder's last file and error, an Auto Update
collector's switch and last run - read off the readers the screens read, written under `system_runtime` where they
changed, with no history line; a pass between syncs never makes a row. PostgreSQL: the state cells are datetimes."""
import json
import os

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

from conftest import PG_TEST_SCHEMA, retire_dynamic_model
import shipped
import system_catalog
from chain import activity, control, graph
from database import crud, models, schemas
from test_the_system_catalogue_keeps_the_products_parts_as_rows import DECIDE, JOIN, USER_TABLES, _rules
from utils import auto_update_control as auc
from utils import heartbeat

pytestmark = pytest.mark.pg

ROLLED = "enrichment_dedup:lot_roll"                       # the decide's first rule, as the declaration expands it
COLLECTOR = {"table_name": "lots", "script_name": "pull_lots.py", "cron_expression": "*/5 * * * *",
             "last_run": "2026-11-09 07:00:00", "last_status": "FAILED", "last_error": "host unreachable",
             "runner": None, "window": "7d"}


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    tables = {**USER_TABLES, **shipped.tables()}
    saved = dict(crud.TABLE_CONFIG)
    for name in tables:
        retire_dynamic_model(name)
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)

    def clean():
        with pg_engine.begin() as conn:
            for name in tables:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
            for name in ("cell_sources", "audit_logs", "database_outbox", "file_checklist", "file_ingestion_logs"):
                conn.execute(text('DELETE FROM "%s".%s' % (PG_TEST_SCHEMA, name)))

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in tables:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    rules = _rules(JOIN, DECIDE)
    monkeypatch.setattr(graph, "chain_graph", lambda db: {"rules": [graph.rule_facts(r) for r in rules]})
    source = tmp_path / "share"
    source.mkdir()
    shares = [{"path": str(source), "table_name": "wafers", "options": {"glob": "*.csv"}}]
    from parsers import directory_watcher
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings", lambda: {"external_sources": list(shares)})
    from ledger import schema
    monkeypatch.setattr(schema, "world_listing", lambda: {"worlds": [], "operating": "default"})
    monkeypatch.setattr(control, "control_path", lambda: str(tmp_path / "chain_control.json"))
    monkeypatch.setattr(auc, "SERVER_DIR", str(tmp_path))
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(heartbeat, "read_all", lambda: {})
    activity.registry.clear()
    activity.registry.attach()
    db = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        yield {"db": db, "tmp": tmp_path, "source": str(source), "engine": pg_engine, "shares": shares}
    finally:
        db.close()
        activity.registry.clear()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in tables:
            retire_dynamic_model(name)


def _collectors(world, *entries):
    (world["tmp"] / "config" / "scheduler_status.json").write_text(
        json.dumps({"last_updated": "2026-11-09 07:00:00", "collectors": list(entries)}), encoding="utf-8")


def _row(world, table, **key):
    model = models.DYNAMIC_TABLES[table]
    return world["db"].query(model).filter_by(**key).one_or_none()


def _drained(world):
    with world["engine"].begin() as conn:
        conn.execute(text('UPDATE "%s".database_outbox SET processed_chain = true' % PG_TEST_SCHEMA))


def _naming_state(lines):
    """The (table, column, new value) lines that name a state cell - its own line, or a row's line naming it - whatever
    wrote them (a state cell blanked leaves «delete_source:system_runtime», not the layer's own name)."""
    quiet = {table: set(crud.TABLE_CONFIG[table].get("no_history_columns") or ())
             for table in ("sys_tables", "sys_chain_rules", "sys_ingestion", "sys_collectors")}
    assert all(quiet.values()), "CANARY: the system tables list their state cells"
    return [line for line in lines if line[0] in quiet and (line[1] in quiet[line[0]] or any(
        "%s:" % column in str(line[2]) for column in quiet[line[0]]))]


def _state_history(world):
    with world["engine"].connect() as conn:
        return _naming_state(conn.execute(text('SELECT table_name, column_name, new_value FROM "%s".audit_logs'
                                               % PG_TEST_SCHEMA)).fetchall())


def _seed(world):
    db = world["db"]
    for _ in range(2):
        control.count_outcome(["grade_from_lot"], failed=True, cause="mapper refused", cap=2)
    activity.registry.record_outcome(ROLLED, "run", None, 3, 1)
    crud.apply_batch_updates(db, "wafers", schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"wafer_id": "W1", "lot_id": "L1"}, source_name="file", updated_by="t")]))
    db.commit()
    with world["engine"].begin() as conn:
        conn.execute(text('UPDATE "%s".database_outbox SET processed_chain = false WHERE table_name = :t'
                          % PG_TEST_SCHEMA), {"t": "wafers"})
        log = conn.execute(text('INSERT INTO "%s".file_ingestion_logs (filename, filepath, table_name, status, '
                                'error_message) VALUES (:f, :p, :t, :s, :e) RETURNING id' % PG_TEST_SCHEMA),
                           {"f": "b.csv", "p": "x", "t": "wafers", "s": "FAILED", "e": "column lot_id missing"}).scalar()
        for name, status, log_id, at in (("a.csv", "DONE", None, "2026-11-09 06:00+09"),
                                         ("b.csv", "FAILED", log, "2026-11-09 06:30+09"),
                                         ("c.csv", "DONE", None, "2026-11-09 06:45+09")):
            conn.execute(text('INSERT INTO "%s".file_checklist (table_name, path_key, filepath, filename, source, '
                              'status, log_id, updated_at) VALUES (:t, :k, :p, :f, :s, :st, :l, :at)' % PG_TEST_SCHEMA),
                         {"t": "wafers", "k": name, "p": os.path.join(world["source"], name), "f": name,
                          "s": world["source"], "st": status, "l": log_id, "at": at})
        conn.execute(text('ANALYZE "%s".wafers' % PG_TEST_SCHEMA))
    _collectors(world, COLLECTOR)


def test_each_parts_state_is_written_once_and_keeps_no_history(world, monkeypatch):
    # the recent changes' cache leg retired (D 11-11): the cache holds write batches (audit_batches), never a cell's
    # line, so «no state cell in the cache» has nothing to ask
    _seed(world)
    system_catalog.sync(world["db"])
    world["db"].commit()
    rule = _row(world, "sys_chain_rules", rule_name="grade_from_lot")
    assert (rule.switched_off_cause, rule.failures_in_a_row, rule.switched_off_at is not None) == (
        "mapper refused", 2, True)
    rolled = _row(world, "sys_chain_rules", rule_name=ROLLED)
    assert (rolled.last_outcome, rolled.last_outcome_at is not None, rolled.failures_in_a_row) == ("run", True, None)
    wafers = _row(world, "sys_tables", table_name="wafers")
    assert (wafers.events_waiting, wafers.oldest_waiting_at is not None, wafers.row_estimate) == (1, True, 1)
    assert _row(world, "sys_tables", table_name="lots").events_waiting == 0
    share = _row(world, "sys_ingestion", table_name="wafers")
    assert (share.last_file, share.last_error) == ("c.csv", "column lot_id missing")
    pulled = _row(world, "sys_collectors", collector="lots/pull_lots.py")
    assert (pulled.table_name, pulled.schedule, pulled.window, pulled.active, pulled.last_status,
            pulled.last_error, pulled.declared) == ("lots", "*/5 * * * *", "7d", "yes", "FAILED", "host unreachable",
                                                    "yes")
    assert _state_history(world) == []
    _drained(world)
    system_catalog.tick(world["db"])                       # the queue drained: the waiting counts move once
    world["db"].commit()
    world["db"].expire_all()
    wafers = _row(world, "sys_tables", table_name="wafers")
    assert (wafers.events_waiting, wafers.oldest_waiting_at) == (0, None), "CANARY: the drained queue blanked a cell"
    assert _state_history(world) == []                     # its layer withdrawn, no line (lead 11-09 ㅁ)
    _drained(world)
    again = system_catalog.tick(world["db"])
    assert all(not any(counts.values()) for counts in again.values()), again


def test_a_person_s_description_keeps_its_history_beside_the_state(world):
    _seed(world)
    system_catalog.sync(world["db"])
    world["db"].commit()
    crud.apply_batch_updates(world["db"], "sys_chain_rules", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"rule_name": "grade_from_lot", "description": "grade from its lot"},
                                  source_name=crud.USER_SOURCE, updated_by="kim")]))
    world["db"].commit()
    with world["engine"].connect() as conn:
        kept = conn.execute(text('SELECT column_name FROM "%s".audit_logs WHERE table_name = :t AND updated_by = :u'
                                 % PG_TEST_SCHEMA), {"t": "sys_chain_rules", "u": "kim"}).fetchall()
    assert [c for (c,) in kept] == ["description"] and _state_history(world) == []


def test_a_pass_between_syncs_makes_no_row_and_marks_a_collector_gone(world):
    _seed(world)
    system_catalog.sync(world["db"])
    world["db"].commit()
    later = world["tmp"] / "later"
    later.mkdir()
    world["shares"].append({"path": str(later), "table_name": "lots"})   # a share the next declaration read brings
    with world["engine"].begin() as conn:                                  # a file read from it already
        conn.execute(text('INSERT INTO "%s".file_checklist (table_name, path_key, filepath, filename, source, status) '
                          "VALUES ('lots', 'l.csv', :p, 'l.csv', :s, 'DONE')" % PG_TEST_SCHEMA),
                     {"p": str(later / "l.csv"), "s": str(later)})
    _collectors(world)
    system_catalog.tick(world["db"])
    world["db"].commit()
    assert [r.table_name for r in world["db"].query(models.DYNAMIC_TABLES["sys_ingestion"]).all()] == ["wafers"]
    assert _row(world, "sys_collectors", collector="lots/pull_lots.py").declared == "no"


def test_a_loop_not_seen_leaves_the_last_evaluation_as_it_was(world, monkeypatch):
    _seed(world)
    system_catalog.sync(world["db"])
    world["db"].commit()
    monkeypatch.setattr(activity.registry, "_attached", False)     # the loop is not in this process, no heartbeat holds it
    system_catalog.tick(world["db"])
    world["db"].commit()
    assert _row(world, "sys_chain_rules", rule_name=ROLLED).last_outcome == "run"
