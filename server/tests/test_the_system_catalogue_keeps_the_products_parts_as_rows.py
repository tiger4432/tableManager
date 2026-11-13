"""The product's own parts as rows (owner 11-06 «풀하면 다 알아서 셋업되게»): the shipped System tables, filled from the
declarations by `system_catalog.sync` - only what changed, a person's description kept, a part no longer declared kept
and marked - and the shipped `system` world that reads them loads with every source planned."""
import copy

import pytest

import shipped
import system_catalog
from chain import graph, rule_shape
from database import crud, models
from database.database import Base

USER_TABLES = {
    "lots": {"business_key": "lot_id", "column_types": {"lot_id": "string", "grade": "string", "owner_name": "string"}},
    "wafers": {"business_key": "wafer_id",
               "column_types": {"wafer_id": "string", "lot_id": "string", "grade": "string", "note": "string"}},
    "lot_summary": {"business_key": "lot_id", "column_types": {"lot_id": "string", "wafer_count": "number"}},
}
JOIN = {"name": "grade_from_lot", "on": {"table": "lots"}, "into": {"table": "wafers"},
        "derive": {"kind": "join", "join": {"on": [{"left": "lot_id", "right": "lot_id"}],
                                            "take": ["grade", {"from": "owner_name", "into": "note"}]}}}
DECIDE = {"name": "lot_roll", "on": {"table": "wafers"}, "into": {"table": "lot_summary"},
          "derive": {"kind": "decide", "decide": {"key": ["lot_id"], "aggregations": {"wafer_count": "count"}}}}


def _rules(*declarations):
    out = []
    for declaration in declarations:
        rules, refusal, _notes = rule_shape.expand_declaration(declaration, crud.TABLE_CONFIG)
        assert refusal is None, refusal
        out += rules
    return out


@pytest.fixture
def catalogue(db_session, monkeypatch, tmp_path):
    tables = {**copy.deepcopy(USER_TABLES), **shipped.tables()}
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    Base.metadata.create_all(bind=db_session.get_bind())
    models.sync_dynamic_tables_schema(db_session.get_bind())
    rules = {"now": _rules(JOIN, DECIDE)}
    monkeypatch.setattr(graph, "chain_graph", lambda db: {"rules": [graph.rule_facts(r) for r in rules["now"]]})
    from parsers import directory_watcher
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings", lambda: {"external_sources": [
        {"path": str(tmp_path), "table_name": "wafers", "options": {"glob": "*.csv"}}]})
    from ledger import schema, setup, setup_bundle
    monkeypatch.setattr(schema, "world_listing", lambda: {"worlds": ["system"], "operating": "default"})
    monkeypatch.setattr(setup, "live_physical_catalog",
                        lambda: setup_bundle._adapt_physical_catalog(crud.TABLE_CONFIG))
    # the parts' state writes datetime cells, which SQLite refuses through the write door - its own test is PostgreSQL's
    # (test_the_system_catalogue_keeps_each_parts_state_pg)
    monkeypatch.setattr(system_catalog, "runtime", lambda db: {})
    return rules


def _rows(db, table):
    model = models.DYNAMIC_TABLES[table]
    return db.query(model).all()


def test_the_first_sync_fills_every_table_and_a_second_writes_nothing(db_session, catalogue):
    said = system_catalog.sync(db_session)
    db_session.commit()
    declared = {name for name in crud.TABLE_CONFIG if not name.startswith("__")}
    assert {r.table_name for r in _rows(db_session, "sys_tables")} == declared
    assert len(_rows(db_session, "sys_columns")) == sum(len(crud.TABLE_CONFIG[t]["column_types"]) for t in declared)
    assert {r.rule_name: r.kind for r in _rows(db_session, "sys_chain_rules")} == {
        r["name"]: rule_shape.declared_kind(r) for r in catalogue["now"]}
    cells = {(r.rule_name, r.role, r.table_name, r.column_name, r.from_table, r.from_column)
             for r in _rows(db_session, "sys_rule_columns")}
    assert ("grade_from_lot", "joins_on", "wafers", "lot_id", None, None) in cells
    assert ("grade_from_lot", "joins_on", "lots", "lot_id", None, None) in cells
    assert ("grade_from_lot", "writes_column", "wafers", "note", "lots", "owner_name") in cells
    decided = [r for r in catalogue["now"] if r["mapper"] == "declared:enrich"][0]["name"]
    assert (decided, "decides_by", "lot_summary", "lot_id", None, None) in cells
    assert [(r.table_name, r.pattern) for r in _rows(db_session, "sys_ingestion")] == [("wafers", "*.csv")]
    built = {(r.source_id, r.entity_type) for r in _rows(db_session, "sys_source_builds")}
    assert ("sys_columns", "column") in built and ("sys_rule_columns", "chain_rule") in built
    assert all(said[t]["written"] for t in ("sys_tables", "sys_columns", "sys_chain_rules", "sys_rule_columns",
                                            "sys_ingestion", "sys_ledger_sources", "sys_source_builds"))
    again = system_catalog.sync(db_session)
    assert all(not any(counts.values()) for counts in again.values()), again


def test_a_description_a_person_wrote_survives_a_resync(db_session, catalogue):
    from database import schemas

    system_catalog.sync(db_session)
    db_session.commit()
    crud.apply_batch_updates(db_session, "sys_tables", schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"table_name": "lots", "description": "one row per lot"}, source_name="user", updated_by="user")]))
    db_session.commit()
    crud.TABLE_CONFIG["lots"]["column_types"]["spec"] = "string"
    said = system_catalog.sync(db_session)
    db_session.commit()
    lots = [r for r in _rows(db_session, "sys_tables") if r.table_name == "lots"][0]
    assert (lots.description, lots.column_count, said["sys_tables"]["written"]) == ("one row per lot", 4, 1)


def test_a_rule_no_longer_declared_keeps_its_row_marked_no(db_session, catalogue):
    system_catalog.sync(db_session)
    db_session.commit()
    gone = {r["name"] for r in catalogue["now"]} - {r["name"] for r in _rules(DECIDE)}
    catalogue["now"] = _rules(DECIDE)
    said = system_catalog.sync(db_session)
    db_session.commit()
    rows = {r.rule_name: r.declared for r in _rows(db_session, "sys_chain_rules")}
    assert {r for r, d in rows.items() if d == "no"} == gone and "grade_from_lot" in gone
    assert said["sys_chain_rules"]["marked"] == len(gone)
    assert {r for r, d in rows.items() if d == "yes"} == {r["name"] for r in catalogue["now"]}
    assert system_catalog.sync(db_session)["sys_chain_rules"]["marked"] == 0


def test_a_column_that_stops_being_a_key_has_its_key_cell_withdrawn(db_session, catalogue):
    system_catalog.sync(db_session)
    db_session.commit()
    crud.TABLE_CONFIG["lots"]["business_key"] = "grade"
    said = system_catalog.sync(db_session)
    db_session.commit()
    keyed = {r.column_name: r.key_of for r in _rows(db_session, "sys_columns") if r.table_name == "lots"}
    # a shipped table keeps no lines, so no history: the cleared cell is written blank (lead 11-13 ㄴ)
    assert keyed == {"lot_id": None, "grade": "lots", "owner_name": None}
    assert said["sys_columns"] == {"written": 2, "marked": 0}


def test_the_shipped_world_loads_with_every_source_planned():
    from ledger import setup_bundle
    from ledger.setup import load_setup

    loaded = load_setup(shipped.world_root("system"),
                        catalog=setup_bundle._adapt_physical_catalog(shipped.tables()), imported={})
    plans = loaded.snapshot.source_plans
    assert set(plans) == set(shipped.tables()) and all(p.planned for p in plans.values())


def test_an_owner_table_under_a_shipped_name_is_left_out_and_the_owner_file_is_written_without_shipped():
    merged = shipped.merged({"sys_tables": {"business_key": "x", "column_types": {"x": "string"}}, "mine": {}})
    assert merged["sys_tables"] == shipped.tables()["sys_tables"] and "mine" in merged
    assert set(shipped.owner_only(merged)) == {"mine"}


def test_a_save_under_a_shipped_table_name_is_refused_by_name():
    from fastapi import HTTPException
    from ledger import admin

    with pytest.raises(HTTPException) as refused:
        admin.save_table_config_raw("sys_columns", {"column_types": {}}, base="")
    assert refused.value.detail["code"] == "shipped_table"


def test_the_processes_that_write_or_read_the_shipped_tables_build_their_models_from_crud():
    """The chain worker (it syncs) and the ledger worker (it translates the system world) build their models from
    crud's one loader - the owner's tables and the shipped ones. Measured on the box 11-06: the chain worker read the
    owner's file itself, had no model for any shipped table and synced nothing."""
    import ast
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for entry in ("run_chain_worker.py", "run_ledger_worker.py"):
        tree = ast.parse(open(os.path.join(here, entry), encoding="utf-8").read())
        built = [call for call in ast.walk(tree) if isinstance(call, ast.Call)
                 and getattr(call.func, "attr", None) == "init_dynamic_models"]
        assert len(built) == 1, entry
        argument = built[0].args[0]
        assert isinstance(argument, ast.Call) and getattr(argument.func, "attr", None) == "load_table_config_or_raise", entry

def test_a_binding_that_reads_its_type_from_a_column_builds_every_type_it_can_carry(db_session, catalogue, tmp_path,
                                                                                     monkeypatch, caplog):
    """owner 11-10 «시스템 카탈로그 원장에 dict 타입 에러»: a binding whose `entity_type` is read from a column
    ({kind: column, column}) put that dict in a set, so one world's binding left every world's ledger rows unread. Its
    types are what its predicate admits there (`setup_bundle.column_typed_entity_types`), the other world is read too."""
    import dataclasses
    import json
    import logging
    import os

    from ledger import schema, setup, setup_bundle
    from tests.test_an_entity_type_can_be_read_from_a_column import CANDIDATES, COLUMNS, SAMPLE, SOURCE, document

    shipped_ledger = json.load(open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8"))
    said = document(shipped_ledger, SOURCE)
    said["sources"] = {CANDIDATES: said["sources"][CANDIDATES]}
    root = tmp_path / "candidates_world"
    root.mkdir()
    (root / setup_bundle.CONFIG_FILENAME).write_text(json.dumps(said), encoding="utf-8")
    physical = dict(setup_bundle.load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample")))
    physical[CANDIDATES] = {"columns": {**{name: "string" for name in COLUMNS}, "created_at": "datetime"},
                            "business_key": "cand_id"}
    monkeypatch.setattr(setup, "live_physical_catalog",
                        lambda: {**physical, **setup_bundle._adapt_physical_catalog(crud.TABLE_CONFIG)})
    monkeypatch.setattr(schema, "world_listing", lambda: {"worlds": ["system", "candidates"], "operating": "default"})
    names = schema.world_names
    monkeypatch.setattr(schema, "world_names", lambda world=None: dataclasses.replace(
        names("system"), world="candidates", declaration_root=str(root)) if world == "candidates" else names(world))
    caplog.set_level(logging.WARNING)
    system_catalog.sync(db_session)
    db_session.commit()
    assert "were not read" not in caplog.text
    built = {(r.world, r.source_id, r.entity_type) for r in _rows(db_session, "sys_source_builds")}
    assert {"quantity", "defect_kind"} <= {t for w, s, t in built if (w, s) == ("candidates", CANDIDATES)}, built
    assert ("system", "sys_columns", "column") in built, "the other world's rows are read too"
