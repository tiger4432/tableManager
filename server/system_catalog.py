# -*- coding: utf-8 -*-
"""The product's own parts as rows (owner 11-06 «온톨로지까지 시스템이 알아서, 사람은 각 선언이 무엇 역할인지 설명만»):
the tables the product ships (`server/declarations/table_config.json`, group System), filled from the declarations,
which the `system` ledger world reads (`server/declarations/worlds/system`).

    sys_tables · sys_columns   the catalogue (`crud.TABLE_CONFIG`)
    sys_chain_rules · sys_rule_columns   every rule the chain runs, as its declaration says it (`chain.graph.rule_facts`)
    sys_ingestion              a table's own workspace folder, and the external sources (ingestion_settings.json)
    sys_ledger_sources · sys_source_builds   every world's ledger sources and the entity types each builds

`sync` writes only the cells that changed, through the table write door under its own layer (`SOURCE`); a person's
`description` is the user layer and stands. A part no longer declared keeps its row, `declared` «no». The chain
dispatcher wakes it when it reads the declaration (`wake`); it runs on its own thread, never in the loop.
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


def _ingestion_rows(config) -> list:
    import paths
    from parsers import directory_watcher as watcher

    rows = []
    for table in sorted(config):
        root = watcher.resolve_workspace_root(paths.WORKSPACE_DIR, table, config)
        if os.path.isdir(root):
            rows.append(_row(ingestion_id=os.path.relpath(root, paths.WORKSPACE_DIR), table_name=table,
                             folder=root, pattern=None, parser=None, enabled=YES))
    specs, _errors = watcher.validate_external_source_specs(watcher.load_ingestion_settings(), config,
                                                            paths.WORKSPACE_DIR)
    for spec in specs:
        rows.append(_row(ingestion_id=spec["source_id"], table_name=spec["table_name"],
                         folder=spec["root"], pattern=", ".join((spec.get("options") or {}).get("glob") or ()) or None,
                         parser=spec.get("parser"), enabled=NO if spec.get("off") else YES))
    return rows


def _ledger_rows() -> dict:
    from ledger import schema
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
            types = {binding.get("entity_type") for mapping in plan.profile.mappings.values()
                     for binding in (mapping.bindings or {}).values()
                     if isinstance(binding, Mapping) and binding.get("entity_type")} if plan.profile else set()
            for entity_type in sorted(types):
                builds.append(_row(world=world, source_id=source_id, entity_type=entity_type))
    return {"sys_ledger_sources": sources, "sys_source_builds": builds}


class _Unread(Exception):
    """A declaration that did not load: its tables are not synced this time - a row is never marked «no» for it."""


def desired(db) -> dict:
    """{table: [row]} - every part the declarations say now. A table whose declaration could not be read is left
    out, so its rows stay as they are."""
    from database import crud

    out = {**_catalogue_rows(crud.TABLE_CONFIG), "sys_ingestion": _ingestion_rows(crud.TABLE_CONFIG)}
    for name, read in (("rules", lambda: _rule_rows(db)), ("ledger", _ledger_rows)):
        try:
            out.update(read())
        except Exception as exc:                                   # noqa: BLE001 - said, the rest still syncs
            if not isinstance(exc, _Unread):
                logger.warning("[SystemCatalog] the %s were not read - their rows are left as they were: %s",
                               name, told(exc), exc_info=exc)
    return out


def _text(value):
    """One spelling to compare by - blank is None, 3.0 is 3."""
    from database import crud

    value = crud.none_if_blank(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return None if value is None else str(value)


def sync(db) -> dict:
    """Writes what changed -> {table: {"written": rows, "withdrawn": cells, "marked": rows no longer declared}}."""
    from database import crud, models, schemas

    said = {}
    for table, rows in desired(db).items():
        model = models.DYNAMIC_TABLES.get(table)
        if model is None:
            logger.warning("[SystemCatalog] %s has no model in this process - not synced; its declaration is "
                           "server/declarations/table_config.json", table)
            said[table] = {"written": 0, "withdrawn": 0, "marked": 0, "no_model": 1}
            continue
        keys = _keys(table)
        current = {tuple(_text(getattr(row, key, None)) for key in keys): row for row in db.query(model).all()}
        items, withdraw, seen = [], [], set()
        for row in rows:
            key = tuple(_text(row.get(column)) for column in keys)
            seen.add(key)
            have = current.get(key)
            changed = {column: value for column, value in row.items()
                       if column not in keys and (have is None or _text(getattr(have, column, None)) != _text(value))}
            if have is not None:
                withdraw += [{"row_id": have.row_id, "column_name": column}
                             for column, value in changed.items() if _text(value) is None]
            changed = {column: value for column, value in changed.items() if _text(value) is not None}
            if changed:
                items.append({**{column: row.get(column) for column in keys}, **changed})
        marked = [{**{column: getattr(have, column, None) for column in keys}, DECLARED: NO}
                  for key, have in current.items() if key not in seen and _text(getattr(have, DECLARED, None)) != NO]
        updates = [schemas.GeneralUpdateItem(updates=item, source_name=SOURCE, updated_by=SOURCE)
                   for item in items + marked]
        if updates:
            crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=updates))
        if withdraw:
            crud.delete_cell_source_batch(db, table, withdraw, SOURCE)
        said[table] = {"written": len(items), "withdrawn": len(withdraw), "marked": len(marked)}
    return said


_wake = threading.Event()
_thread = []


def wake():
    """The declaration was read: sync on the catalogue's own thread, started on the first call."""
    _wake.set()
    if not _thread:
        _thread.append(threading.Thread(target=_run, name="system-catalog", daemon=True))
        _thread[0].start()


def _run():
    from database.database import SessionLocal

    while True:
        _wake.wait()
        _wake.clear()
        db = SessionLocal()
        try:
            said = sync(db)
            db.commit()
            moved = {table: counts for table, counts in said.items() if any(counts.values())}
            logger.info("[SystemCatalog] synced - %s", " · ".join(
                "%s %d written %d withdrawn %d no longer declared" % (table, c["written"], c["withdrawn"], c["marked"])
                for table, c in sorted(moved.items())) or "nothing changed")
        except Exception as exc:                                   # noqa: BLE001 - the next wake tries again
            db.rollback()
            logger.error("[SystemCatalog] sync stopped - the next declaration read tries again: %s", told(exc),
                         exc_info=exc)
        finally:
            db.close()
