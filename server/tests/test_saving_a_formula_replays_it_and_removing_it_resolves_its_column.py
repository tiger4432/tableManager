# -*- coding: utf-8 -*-
"""Saving a formula (lead 10-28): its rule switched on through the rule editor's door and R1 over the table queued.
Removing it: the rule taken out through ledger.admin's one removal door - the save door's shape - and R3 over the
column queued with `formula_removed`, which resolves that column's every cell from its layers, under two layers too, so
no value is left with no source. No other cell under two layers is touched.

    seat                                  gate
    POST /admin/chain/formula + base      the rule saved on; R1 queued for it
    ... formula ""                        the rule gone, a backup made; R3 queued with formula_removed
    remove_chain_rule_raw                 refused by name while a run holds the rule; the file as opened
    R3 formula_removed                    no layer -> blank, one layer -> its value, a person's stays; a row it asks merged whole
    chain_rules.json changed              the grid pool started again, the walk pool not (it reads nothing of it)
    /tables/{t}/schema                    «formulas» as saved, gone when removed, absent on a table with none
"""
import json

import pytest
from fastapi import HTTPException

from chain import formula, replay
from chain import ingestion_worker as worker
from database import crud, models, schemas
from ledger import admin
from tests.test_a_formula_on_a_column_is_a_join_onto_its_own_row import T, _put, fixture_db  # noqa: F401


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "bk"))
    worker.forget_loaded_chain_rules()
    yield path
    worker.forget_loaded_chain_rules()


def _queued(db):
    from admin import retroactive

    return [(run["op"], run["params"]) for run in retroactive.runs(db)]


def _route(db, **payload):
    import main

    return main.post_chain_formula(dict({"table": T, "column": "c"}, **payload), db)


def test_saving_switches_the_rule_on_and_queues_r1(db, rules_file):
    said = _route(db, formula="=[a]*2", base=admin.file_fingerprint(str(rules_file)))
    [rule] = json.loads(rules_file.read_text(encoding="utf-8"))["rules"]
    assert formula.of_declaration(rule) == (T, "c", "=[a]*2") and rule["enabled"] is True
    assert said["rule"] == "formula fx.c" and said["run_id"] and said["base"] == admin.file_fingerprint(str(rules_file))
    assert _queued(db) == [("chain_replay", {"rule": "formula fx.c"})]


def test_removing_takes_the_rule_out_and_queues_r3_over_the_column(db, rules_file, tmp_path):
    from admin import retroactive

    rules_file.write_text(json.dumps({"rules": [formula.to_declaration(T, "c", "=[a]*2")]}), encoding="utf-8")
    _put(db, [{"k": "k1", "a": 1}])
    db.query(models.DYNAMIC_TABLES[T]).update({"c": 2})          # what the formula wrote, with no layer
    db.commit()
    said = _route(db, formula="", base=admin.file_fingerprint(str(rules_file)))
    assert json.loads(rules_file.read_text(encoding="utf-8"))["rules"] == [] and said["run_id"]
    assert list((tmp_path / "bk").iterdir()), "the saves' history: a backup of the file before"
    [(op, params)] = _queued(db)
    assert (op, params) == ("resolve", {"table": T, "columns": ["c"], "formula_removed": ["c"]})
    retroactive.OPERATIONS[op]["run"](db, params, lambda _line: None)
    db.expire_all()
    assert db.query(models.DYNAMIC_TABLES[T]).one().c is None, "the run the removal queued leaves no sourceless value"


def test_removal_is_refused_by_name_while_a_run_holds_the_rule_and_on_a_stale_base(db, rules_file):
    _route(db, formula="=[a]*2", base=admin.file_fingerprint(str(rules_file)))
    with pytest.raises(HTTPException) as held:
        _route(db, formula="", base=admin.file_fingerprint(str(rules_file)))
    assert "Next: switch the rule off and remove it when nothing holds it" in str(held.value.detail)
    with pytest.raises(HTTPException) as stale:
        admin.remove_chain_rule_raw("formula fx.c", "an old base")
    assert "This file changed after you opened it" in str(stale.value.detail)


@pytest.mark.parametrize("removed, expected", [
    (["c"], {"k1": None, "k2": 100, "k3": 50}),
    ((), {"k1": 7, "k2": 100, "k3": 7}),
])
def test_r3_resolves_a_column_that_lost_its_formula_and_no_other_cell_under_two_layers(db, removed, expected):
    _put(db, [{"k": "k1", "a": 1}, {"k": "k2", "a": 1, "c": 100}, {"k": "k3", "a": 1}])
    model = models.DYNAMIC_TABLES[T]
    rows = {row.k: row for row in db.query(model)}
    crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=rows["k3"].row_id, updates={"c": 50}, source_name="f.csv", updated_by="f.csv")]))   # k3's «c»: one layer
    db.commit()
    for k in ("k1", "k3"):
        rows[k].c = 7                                       # what a formula wrote, with no layer
    rows["k1"].a = 9                                        # a one-layer cell out of step with its layer
    db.commit()
    replay.recompute_display_values(db, T, apply=True, formula_removed=removed, log=lambda _l: None)
    db.expire_all()
    shown = {row.k: (row.c, row.a) for row in db.query(model)}
    assert {k: c for k, (c, _a) in shown.items()} == expected
    # the row is the unit (lead 11-11: row-unit merge is canonical): a row R3 asks is merged whole - k1's «a» takes
    # its line's 1; a row it does not ask keeps t's 9
    assert shown["k1"][1] == (1 if removed else 9)


def test_a_rules_file_change_starts_the_grid_pool_again_and_not_the_walk_pool(monkeypatch):
    from database import config_watcher
    from runtime import process_pool

    monkeypatch.setattr(process_pool, "_warmed", [True])
    monkeypatch.setattr(process_pool, "warm", lambda: None)
    generation = lambda: {pool.name: pool.generation[0] for pool in process_pool.POOLS}  # noqa: E731
    before = generation()
    config_watcher._chain_rules(None, None)
    assert generation() == dict(before, grid=before["grid"] + 1)
    process_pool.recycle()
    assert generation() == {"walk": before["walk"] + 1, "grid": before["grid"] + 2}


def test_the_schema_says_the_tables_formulas_as_saved_and_removed(db, rules_file):
    import main

    assert "formulas" not in main.get_table_schema(T, db=db)
    _route(db, formula="=[a]*2", base=admin.file_fingerprint(str(rules_file)))
    assert main.get_table_schema(T, db=db)["formulas"] == {"c": "=[a]*2"}
    assert "formulas" not in main.get_table_schema("another", db=db)
    db.query(models.RetroactiveRun).delete()                     # the R1 the save queued, gone - it held the rule
    db.commit()
    _route(db, formula="", base=admin.file_fingerprint(str(rules_file)))
    assert "formulas" not in main.get_table_schema(T, db=db)
