# -*- coding: utf-8 -*-
"""The product's own parts as rows (owner 11-06 «온톨로지까지 시스템이 알아서, 사람은 각 선언이 무엇 역할인지 설명만»):
the tables the product ships (`server/declarations/table_config.json`, group System), filled from the declarations,
which the `system` ledger world reads (`server/declarations/worlds/system`).

    sys_tables · sys_columns   the catalogue (`crud.TABLE_CONFIG`)
    sys_chain_rules · sys_rule_columns   every rule the chain runs, as its declaration says it (`chain.graph.rule_facts`)
    sys_ingestion              a table's own workspace folder, and the external sources (ingestion_settings.json)
    sys_ledger_sources · sys_source_builds   every world's ledger sources and the entity types each builds
    sys_collectors             the Auto Update collectors the scheduler loaded (its status file)

`sync` writes only the cells that changed, through the table write door under its own layer (`SOURCE`); a person's
`description` is the user layer and stands. A part no longer declared keeps its row, `declared` «no». The chain
dispatcher wakes it when it reads the declaration (`wake`); it runs on its own thread, never in the loop.
The parts' state (`runtime`, owner 11-09 step 1) is written by the same writer under `RUNTIME` - on every sync, and
between them every `RUNTIME_JOB` pace (pacing.json); its cells are the tables' `no_history_columns`. A pass between
syncs reads the collectors' file again too: the scheduler loads collectors on its own.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping

from error_said import told

logger = logging.getLogger("SystemCatalog")

#: The layer the catalogue writes - below a person's (`crud.SOURCE_PRIORITY`, unlisted).
SOURCE = "system_catalog"
#: The layer the parts' state is written under, and the pacing.json job whose rest is the seconds between passes.
RUNTIME = RUNTIME_JOB = "system_runtime"
YES, NO = "yes", "no"
DECLARED = "declared"


def _keys(table) -> list:
    from database import crud

    config = crud.TABLE_CONFIG.get(table) or {}
    return list(config.get("composite_key_source") or [config["business_key"]])


def _row(**cells) -> dict:
    return {**cells, DECLARED: YES}


def _catalogue_rows(config) -> dict:
    tables, columns = [], []
    for name, entry in sorted(config.items()):
        if not isinstance(entry, dict) or name.startswith("__"):
            continue
        keys = list(entry.get("composite_key_source") or ([entry["business_key"]] if entry.get("business_key") else []))
        types = entry.get("column_types") or {}
        tables.append(_row(table_name=name, group=entry.get("group"), key_columns=", ".join(keys),
                           column_count=len(types)))
        for column, kind in types.items():
            at = keys.index(column) + 1 if column in keys else None
            columns.append(_row(table_name=name, column_name=column, column_type=kind,
                                key_position=at, key_of=name if at else None))
    return {"sys_tables": tables, "sys_columns": columns}


def _rule_rows(db) -> dict:
    from chain.graph import chain_graph

    rules, columns = [], []
    for facts in chain_graph(db).get("rules") or ():
        rules.append(_row(rule_name=facts["name"], kind=facts["kind"],
                          declaration=facts["declaration"], enabled=YES if facts["enabled"] else NO,
                          runs_on=facts["runs_on"], when=facts["when"] or None, trigger_table=facts["trigger_table"],
                          target_table=facts["target_table"], function=facts["function"] or None,
                          formula=facts["formula"] or None))
        for cell in facts["columns"]:
            columns.append(_row(rule_name=facts["name"], table_name=cell["table"],
                                column_name=cell["column"], role=cell["role"], origin="declared",
                                from_table=cell["from_table"], from_column=cell["from_column"]))
    return {"sys_chain_rules": rules, "sys_rule_columns": columns}


def _ingestion_parts(config) -> list:
    """[(row, the file checklist's source of its files)] - a table's own folder's files carry no source or `raws`
    (None here), an external source's its root."""
    import paths
    from parsers import directory_watcher as watcher

    parts = []
    for table in sorted(config):
        root = watcher.resolve_workspace_root(paths.WORKSPACE_DIR, table, config)
        if os.path.isdir(root):
            parts.append((_row(ingestion_id=os.path.relpath(root, paths.WORKSPACE_DIR), table_name=table,
                               folder=root, pattern=None, parser=None, enabled=YES), None))
    specs, _errors = watcher.validate_external_source_specs(watcher.load_ingestion_settings(), config,
                                                            paths.WORKSPACE_DIR)
    for spec in specs:
        parts.append((_row(ingestion_id=spec["source_id"], table_name=spec["table_name"],
                           folder=spec["root"], pattern=", ".join((spec.get("options") or {}).get("glob") or ())
                           or None, parser=spec.get("parser"), enabled=NO if spec.get("off") else YES), spec["root"]))
    return parts


def _ingestion_rows(config) -> list:
    return [row for row, _source in _ingestion_parts(config)]


def _ledger_rows() -> dict:
    from ledger import schema, setup_bundle
    from ledger.setup import load_setup

    sources, builds = [], []
    for world in schema.world_listing()["worlds"]:
        try:
            setup = load_setup(schema.world_names(world).declaration_root)
        except Exception as exc:                                   # noqa: BLE001 - one world's file, said
            logger.warning("[SystemCatalog] world %s: its ledger declaration did not load - its sources are left "
                           "as they were: %s", world, told(exc))
            raise _Unread(world) from exc
        for source_id, plan in sorted(setup.snapshot.source_plans.items()):
            sources.append(_row(world=world, source_id=source_id, relation=plan.relation,
                                status=plan.status))
            # a type named in the binding, and every type a binding reading its type from a column can carry - what its
            # predicate admits there (`setup_bundle.column_typed_entity_types`, the list the ledger checks rows against)
            types = set()
            for mapping in plan.profile.mappings.values() if plan.profile else ():
                bindings = mapping.bindings or {}
                types.update(binding["entity_type"] for binding in bindings.values()
                             if isinstance(binding, Mapping) and isinstance(binding.get("entity_type"), str)
                             and binding["entity_type"])
                for typed in setup_bundle.column_typed_entity_types(
                        {"predicate": mapping.predicate_id, "bind": bindings}, setup.snapshot.vocabulary).values():
                    types.update(typed)
            for entity_type in sorted(types):
                builds.append(_row(world=world, source_id=source_id, entity_type=entity_type))
    return {"sys_ledger_sources": sources, "sys_source_builds": builds}


def _collector_entries():
    """The scheduler's collectors as the Auto Update tab shows them; `_Unread` when it has written no status file."""
    from runtime import running

    status = running.scheduler_status()
    if status is None:
        raise _Unread("the scheduler has written no status file")
    return running.collectors_shown(status.get("collectors") or [])


def _collector_key(entry) -> str:
    return "%s/%s" % (entry.get("table_name"), entry.get("script_name"))


def _collector_rows() -> dict:
    return {"sys_collectors": [_row(collector=_collector_key(entry), table_name=entry.get("table_name"),
                                    script_name=entry.get("script_name"),
                                    schedule=None if entry.get("cron_expression") in (None, "Manual-only")
                                    else entry.get("cron_expression"), window=entry.get("window"))
                               for entry in _collector_entries()]}


class _Unread(Exception):
    """A declaration that did not load: its tables are not synced this time - a row is never marked «no» for it."""


def _read_each(reads) -> dict:
    """{table: rows} of each read that answered; one that raised is said and left out, so its rows stay as they are."""
    out = {}
    for name, read in reads:
        try:
            out.update(read())
        except Exception as exc:                                   # noqa: BLE001 - said, the rest still syncs
            if not isinstance(exc, _Unread):
                logger.warning("[SystemCatalog] the %s were not read - their rows are left as they were: %s",
                               name, told(exc), exc_info=exc)
    return out


def desired(db) -> dict:
    """{table: [row]} - every part the declarations say now. A table whose declaration could not be read is left
    out, so its rows stay as they are."""
    from database import crud

    return {**_catalogue_rows(crud.TABLE_CONFIG), "sys_ingestion": _ingestion_rows(crud.TABLE_CONFIG),
            **_read_each((("rules", lambda: _rule_rows(db)), ("ledger", _ledger_rows),
                          ("collectors", _collector_rows)))}


def _at(epoch):
    from datetime import datetime, timezone

    return None if epoch is None else datetime.fromtimestamp(float(epoch), timezone.utc)


def _rule_state(db) -> dict:
    """Each rule's switch-off and failures in a row (`chain.control`), and its last evaluation as the chain loop holds
    it (`running.chain_sight` - the queue screen's sight); a loop not seen leaves the evaluation cells as they were."""
    from chain import control
    from runtime import running

    off, streaks, sight = control.rules_off(), control.failure_streaks(), running.chain_sight()
    outcomes = (sight["instants"] or {}).get("outcomes") or {}
    rows = []
    for (name,) in db.query(_model("sys_chain_rules").rule_name).all():
        said = off.get(name) or {}
        row = {"rule_name": name, "switched_off_at": said.get("at"), "switched_off_cause": said.get("cause"),
               "failures_in_a_row": streaks.get(name)}
        if sight["via"] is not None:
            last = outcomes.get(name) or {}
            row.update(last_outcome=last.get("outcome"), last_outcome_at=_at(last.get("at")),
                       last_reason=last.get("reason"))
        rows.append(row)
    return {"sys_chain_rules": rows}


def _table_state(db) -> dict:
    """Each table's waiting chain events and the oldest one's time (`queue_lines.waiting_by`), and the planner's row
    estimate (`column_stats.estimated_rows`, PostgreSQL only - blank elsewhere)."""
    from chain import queue_lines
    from database import models
    from ledger import column_stats

    waiting = {table: (count, oldest)
               for table, count, oldest, _retried in queue_lines.waiting_by(db, models.DatabaseOutbox.table_name)}
    postgres = db.get_bind().dialect.name == "postgresql"
    rows = []
    for (name,) in db.query(_model("sys_tables").table_name).all():
        model = models.DYNAMIC_TABLES.get(name)
        count, oldest = waiting.get(name, (0, None))
        rows.append({"table_name": name, "events_waiting": count, "oldest_waiting_at": oldest,
                     "row_estimate": column_stats.estimated_rows(db, model.__table__.name)
                     if postgres and model is not None else None})
    return {"sys_tables": rows}


def _ingestion_state(db) -> dict:
    """Each ingestion folder's last file and error off the file checklist (`checkpoint.last_files`): a table's own
    folder holds its rows of no source or `raws`, an external source the rows of its root."""
    from database import crud
    from ingestion import checkpoint, reread

    parts = _ingestion_parts(crud.TABLE_CONFIG)
    asked = {row["ingestion_id"]: [(row["table_name"], each) for each in
                                   ((None, reread.RAWS) if source is None else (source,))] for row, source in parts}
    files = checkpoint.last_files(db, [pair for pairs in asked.values() for pair in pairs])
    rows = []
    for row, _source in parts:
        held = [files[pair] for pair in asked[row["ingestion_id"]] if pair in files]
        newest = max(held, key=lambda said: str(said["at"] or ""), default={})
        rows.append({"ingestion_id": row["ingestion_id"], "last_file": newest.get("file"),
                     "last_file_at": newest.get("at"),
                     "last_error": next((said["error"] for said in held if said["error"]), None)})
    return {"sys_ingestion": rows}


def _collector_state() -> dict:
    from datetime import datetime

    def ran(text):
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S") if text else None
        except ValueError:
            return None

    return {"sys_collectors": [{"collector": _collector_key(entry), "active": YES if entry.get("active") else NO,
                                "last_run_at": ran(entry.get("last_run")), "last_status": entry.get("last_status"),
                                "last_error": entry.get("last_error")} for entry in _collector_entries()]}


def runtime(db) -> dict:
    """{table: [row]} - the parts' state now, the key and its state cells; a read that raised is left out."""
    return _read_each((("rules' state", lambda: _rule_state(db)), ("tables' state", lambda: _table_state(db)),
                       ("ingestion state", lambda: _ingestion_state(db)), ("collectors' state", _collector_state)))


def _model(table):
    from database import models

    return models.DYNAMIC_TABLES[table]


def _write(db, table, rows, layer, mark) -> dict:
    """One table's rows written where they changed (`crud.value_key`, the one equality), through the table write door
    under `layer`; a cell that turned blank is written blank - a shipped table keeps no lines, so no history and no
    layer to withdraw (`crud.keeps_history`, lead 11-13 ㄴ). `mark`: a part gone from `rows` keeps its row,
    `declared` «no» - else (the parts' state) a key no row holds is left alone, no row is made for it.
    -> {"written": rows, "marked": rows no longer declared}."""
    from database import crud, models, schemas

    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        logger.warning("[SystemCatalog] %s has no model in this process - not synced; its declaration is "
                       "server/declarations/table_config.json", table)
        return {"written": 0, "marked": 0, "no_model": 1}
    keys, types = _keys(table), crud.TABLE_CONFIG[table].get("column_types") or {}

    def same(column, value):
        return crud.value_key(value, types.get(column))

    current = {tuple(same(key, getattr(row, key, None)) for key in keys): row for row in db.query(model).all()}
    items, seen = [], set()
    for row in rows:
        key = tuple(same(column, row.get(column)) for column in keys)
        seen.add(key)
        have = current.get(key)
        if have is None and not mark:
            continue
        changed = {column: value for column, value in row.items()
                   if column not in keys and (have is None or same(column, getattr(have, column, None))
                                              != same(column, value))}
        if changed:
            items.append({**{column: row.get(column) for column in keys}, **changed})
    marked = [{**{column: getattr(have, column, None) for column in keys}, DECLARED: NO}
              for key, have in current.items()
              if mark and key not in seen and same(DECLARED, getattr(have, DECLARED, None)) != same(DECLARED, NO)]
    updates = [schemas.GeneralUpdateItem(updates=item, source_name=layer, updated_by=layer) for item in items + marked]
    if updates:
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=updates))
    return {"written": len(items), "marked": len(marked)}


def _sync(db, declared) -> dict:
    """The declared parts written under `SOURCE`, then their state read and written under `RUNTIME` - read after, so a
    row a part just got is there. -> {table: counts}, the state's as «state written»."""
    said = {table: _write(db, table, rows, SOURCE, mark=True) for table, rows in declared.items()}
    for table, rows in runtime(db).items():
        counts = _write(db, table, rows, RUNTIME, mark=False)
        said[table] = {**said.get(table, {}), "state written": counts["written"],
                       **({"no_model": 1} if counts.get("no_model") else {})}
    return said


def sync(db) -> dict:
    """Every part the declarations say and its state, written where it changed -> {table: counts}."""
    return _sync(db, desired(db))


def tick(db) -> dict:
    """Between syncs, every `RUNTIME_JOB` pace: the parts' state, and the collectors the scheduler holds now."""
    return _sync(db, _read_each((("collectors", _collector_rows),)))


_wake = threading.Event()
_thread = []


def wake():
    """The declaration was read: sync on the catalogue's own thread, started on the first call."""
    _wake.set()
    if not _thread:
        _thread.append(threading.Thread(target=_run, name="system-catalog", daemon=True))
        _thread[0].start()


def _run():
    """A declaration read syncs everything; between them a pass of the state every `RUNTIME_JOB` pace's rest."""
    import pacing
    from database.database import SessionLocal

    while True:
        woken = _wake.wait(pacing.job_pace(RUNTIME_JOB)[1] or None)
        _wake.clear()
        db = SessionLocal()
        try:
            said = sync(db) if woken else tick(db)
            db.commit()
            moved = {table: counts for table, counts in said.items() if any(counts.values())}
            if woken or moved:
                logger.info("[SystemCatalog] %s - %s", "synced" if woken else "state", " · ".join(
                    "%s %s" % (table, " ".join("%d %s" % (n, "no longer declared" if what == "marked" else what)
                                       for what, n in counts.items() if n))
                    for table, counts in sorted(moved.items())) or "nothing changed")
        except Exception as exc:                                   # noqa: BLE001 - the next pass tries again
            db.rollback()
            logger.error("[SystemCatalog] %s stopped - the next pass tries again: %s",
                         "sync" if woken else "the state pass", told(exc), exc_info=exc)
        finally:
            db.close()
