# -*- coding: utf-8 -*-
"""The world the hold-copy gates and the table-emptying gates both stand on (PostgreSQL scratch
schema): a source log and an official table, the copy rule and the recount rule
(`copy_rows_with_hold`), and a ledger source reading the official table that excludes a blank
hold. Every seat is the product's: crud writes, the chain's transaction-group body,
`followup.drain_once`, the worker's withdrawal after a drained deletion.
"""
import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, event, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402
from ledger import followup, schema                                 # noqa: E402
from ledger.implementations import (role_mapper_registry,           # noqa: E402
                                    trusted_implementations)
from ledger.setup import LedgerSetup                                # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,             # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot            # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
LOG, OFFICIAL = "hc_log", "hc_official"
KEYS = ["dt_job", "dt_x", "dt_y"]
KEY = {"dt_job": "J1", "dt_x": 1, "dt_y": 2}
TABLES = {
    LOG: {"business_key": "log_id", "composite_key_source": ["log_id"],
          "column_types": {"log_id": "string", "dt_job": "string", "dt_x": "number",
                           "dt_y": "number", "netdie": "number"},
          "display_columns": ["log_id", "dt_job", "dt_x", "dt_y", "netdie"]},
    OFFICIAL: {"composite_key_source": KEYS,
               "column_types": {"dt_job": "string", "dt_x": "number", "dt_y": "number",
                                "netdie": "number", "hold": "string", "note": "string"},
               "display_columns": ["dt_job", "dt_x", "dt_y", "netdie", "hold", "note"]},
}
RULE = {"name": "hc_copy", "trigger_table": LOG, "target_table": OFFICIAL,
        "mapper": "copy_rows_with_hold", "require": KEYS,
        "params": {"key_columns": KEYS, "columns": ["netdie"], "hold_column": "hold"}}
#: The same function on the target: recount only. A deleted source row reaches it as the chain's
#: withdrawal, hence the opt-in.
RECOUNT = {"name": "hc_recount", "trigger_table": OFFICIAL, "target_table": OFFICIAL,
           "mapper": "copy_rows_with_hold", "allow_chain_trigger": True,
           "params": {**RULE["params"], "source_table": LOG}}
#: The ledger source: the official table, a held row excluded - the RELEASE_LOG's line.
SOURCE = "hc_official"
LEDGER_SOURCE = {
    "relation": OFFICIAL,
    "read": {"exclude_when": [{"column": "hold", "blank": True}]},
    # `note` is read (every column is) and bound by nothing - an edit there moves no atom (판정 201)
    "map": {"implementation_id": "declarative-role", "implementation_version": 1},
    "bind": {"mappings": {"counted": {
        "predicate": "has_netdie@1",
        "bind": {"subject": {"kind": "entity", "entity_type": "dtjob@1",
                             "keys": {"dt_job": {"kind": "column", "column": "dt_job"}}},
                 "value": {"kind": "column", "column": "netdie"}}}}},
}


def sample(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


def build(pg_engine, monkeypatch, tmp_path, batch=False):
    """The world, yielded; the caller wraps it as its own fixture. `batch`: both rules declare
    `is_batch` (the mapper is handed the batch) or neither (one row a call)."""
    mapper_sdk.discover()
    import mappers.hold_copy                                         # noqa: F401 - registers
    saved = dict(crud.TABLE_CONFIG)
    for name in TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1

    def clean():
        with pg_engine.begin() as conn:
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
            for table in ("cell_sources", "database_outbox"):
                conn.execute(text('DELETE FROM "%s".%s WHERE table_name IN (:a, :b)'
                                  % (PG_TEST_SCHEMA, table)), {"a": LOG, "b": OFFICIAL})
            for table in (schema.LEDGER_TABLE, schema.ROW_REF_TABLE):
                conn.execute(text('DELETE FROM "%s".%s WHERE source_who = :s'
                                  % (PG_TEST_SCHEMA, table)), {"s": SOURCE})

    raw = pg_engine.raw_connection()
    try:
        schema.ensure_schema(raw)
        raw.commit()
        schema.ensure_partition(raw, datetime.now(timezone.utc))
    finally:
        raw.close()
    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    rules_path = tmp_path / "chain_rules.json"
    rules_path.write_text(json.dumps({"rules": [{**RULE, "is_batch": batch},
                                                {**RECOUNT, "is_batch": batch}]}),
                          encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(rules_path))
    rules = [r for r in worker.load_chain_rules() if r.get("name") in (RULE["name"], RECOUNT["name"])]
    assert len(rules) == 2
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: rules)
    monkeypatch.setattr(worker, "_READ_BY_SOURCE_NAME", set())
    table_config = sample("table_config.json.sample")
    table_config.update(TABLES)
    catalog_path = tmp_path / "table_config.json"
    catalog_path.write_text(json.dumps(table_config), encoding="utf-8")
    catalog = load_physical_catalog(catalog_path)
    doc = sample("ledger_config.json.sample")
    doc["sources"] = {SOURCE: copy.deepcopy(LEDGER_SOURCE)}
    bundle = require_ready_bundle(validate_bundle(doc, catalog=catalog))
    setup = LedgerSetup(
        config_root=Path(SAMPLE), bundle=bundle,
        snapshot=compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog),
        mappers=role_mapper_registry(), catalog=catalog)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    stale = []
    event.listen(session, "after_commit", lambda _s: stale.extend(stale_holds(pg_engine, seen)))
    seen = {}
    followup.reset()
    try:
        yield {"db": session, "engine": pg_engine, "setup": setup, "rules": rules, "stale": stale}
    finally:
        session.close()
        followup.reset()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in TABLES:
            retire_dynamic_model(name)


def stale_holds(engine, seen):
    """After a commit: official rows whose values changed in it, with a hold other than the one
    their key's source rows give at that moment (two or more value sets: blank, else agreed).
    What the ledger would read if the values landed without their hold."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            'SELECT o.dt_job, o.dt_x, o.dt_y, o.netdie, o.hold, '
            '(SELECT count(*) FROM (SELECT DISTINCT l.netdie FROM "%s" l '
            '  WHERE l.dt_job IS NOT DISTINCT FROM o.dt_job AND l.dt_x IS NOT DISTINCT FROM o.dt_x '
            '  AND l.dt_y IS NOT DISTINCT FROM o.dt_y) d) FROM "%s" o' % (LOG, OFFICIAL))).fetchall()
    stale = []
    for job, x, y, netdie, hold, claims in rows:
        key = (job, x, y)
        if seen.get(key) != netdie:
            seen[key] = netdie
            if (hold or "") != ("" if claims > 1 else "agreed"):
                stale.append((key, netdie, hold, claims))
    return stale


def push(world, rows):
    db = world["db"]
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, LOG, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(r), source_name="user", updated_by="hc")
            for r in rows]))
        db.commit()


def run_chain(world, rounds=12):
    """The chain's transaction-group body until nothing is pending - every event marked
    processed, rule or no rule, as the worker does."""
    db = world["db"]
    for _ in range(rounds):
        pending = (db.query(models.DatabaseOutbox)
                   .filter(models.DatabaseOutbox.processed_chain.is_(False),
                           models.DatabaseOutbox.table_name.in_([LOG, OFFICIAL]))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            break
        groups = {}
        for item in pending:
            groups.setdefault(get_payload_dict(item).get("transaction_id"), []).append(item)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(
                tx_id, events, db, world["rules"])
            assert ok, error
            for item in events:
                event_constants.mark_processed(item, "SUCCESS")
            db.commit()
    else:
        raise AssertionError("the chain did not settle")


def settle(world, rounds=12):
    """The chain, then the ledger follow-up from the outbox until nothing is left - the two
    loops the chain worker runs, with the worker's own withdrawal after a drained deletion."""
    db = world["db"]
    run_chain(world, rounds)
    retracted = False
    while True:
        done = followup.drain_outbox_once(world["engine"], world["setup"])
        if done is None:
            break
        assert not any("error" in (s or {}) for s in (done or {}).get("sources", {}).values()), done
        if done and done.get("event_type") == "DELETE" and done.get("row_ids"):
            worker._retract_what_those_rows_fed(db, done["table"], done["row_ids"])
            db.commit()
            retracted = True
    if retracted:
        settle(world, rounds)


def official(world):
    world["db"].expire_all()
    return world["db"].query(models.DYNAMIC_TABLES[OFFICIAL]).one()


def hold(world):
    return official(world).hold


def delete(world, log_id):
    db = world["db"]
    row_id = db.execute(text('SELECT row_id FROM "%s" WHERE log_id = :l' % LOG),
                        {"l": log_id}).scalar()
    crud.delete_rows_batch(db, LOG, [row_id], "hc")
    db.commit()


def recount_writes(world):
    """Chain events the recount rule's own writes left on the official table."""
    return [e.id for e in world["db"].query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.table_name == OFFICIAL).all()
            if RECOUNT["name"] in (event_constants.written_by_of(get_payload_dict(e)) or ())]


def said(world):
    with world["engine"].connect() as conn:
        return [tuple(r) for r in conn.execute(text(
            "SELECT subject_keys->>'dt_job', object_payload->>'value' FROM %s "
            "WHERE source_who = :s ORDER BY 2" % schema.LEDGER_TABLE), {"s": SOURCE})]
