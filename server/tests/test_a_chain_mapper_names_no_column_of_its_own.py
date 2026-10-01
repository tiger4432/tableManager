# -*- coding: utf-8 -*-
"""The two lot_event chain mappers name no column of their own (총괄 0cb2ab958).

    운영에서는 체인 규칙의 params 에 읽을 칼럼과 쓸 칼럼(target_<역할>_column)을 적으면 됩니다.
    빠진 칸은 이름 대어 거절되고, 대상 표가 선언하지 않은 칼럼도 이름 대어 거절됩니다.

Every column name, read and written, comes from the rule through `chain_bindings.params_of`,
with no default; the key column is the one the target table declares. A rule written before
(cells flat, no output cells) is filled by the v6 migration in the words the code used.
"""
import ast
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings                                                     # noqa: E402
from mappers import lot_lineage_mapper, lot_slot_wafer_mapper            # noqa: E402
from scripts import migrate_ledger_config_to_v6 as v6                    # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
T1 = "2026-01-01T10:00:00"


def _shipped(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


RULES = {rule["name"]: rule for rule in _shipped("chain_rules.json.sample")["rules"]}
TABLES = _shipped("table_config.json.sample")
MAPPERS = {"lot_event_to_lot_slot_wafer": lot_slot_wafer_mapper.build_lot_slot_wafer_rows,
           "lot_event_to_lot_lineage": lot_lineage_mapper.build_lot_lineage_rows}
PAYLOADS = [{"data": {"lot_id": "L1", "slotnumbers": "1:2", "waferids": "W1:W2",
                      "event_time": T1, "event_type": "split", "parent_lot": "P1",
                      "child_lot": None}}]


@pytest.fixture(autouse=True)
def targets_declared(monkeypatch):
    """The targets' declarations as they ship: the mappers read their key column there."""
    from database import crud
    for table in ("lot_slot_wafer", "lot_lineage"):
        monkeypatch.setitem(crud.TABLE_CONFIG, table, TABLES[table])


def run(name, rule=None):
    return MAPPERS[name](None, copy.deepcopy(PAYLOADS), rule or RULES[name])["updates"]


def test_the_shipped_rule_writes_the_rows_the_mapper_wrote_before():
    """Written out by hand - what the mapper emitted while its names were its own defaults."""
    assert run("lot_event_to_lot_slot_wafer") == [
        {"updates": {"lot": "L1", "slot": slot, "wafer": wafer, "event_time": T1,
                     "event_type": "split", "lot_slot_wafer_key": f"L1|{slot}|{wafer}|{T1}"},
         "source_name": "chain_ingestion", "updated_by": "chain_lot_slot_wafer",
         "business_key_val": f"L1|{slot}|{wafer}|{T1}"}
        for slot, wafer in (("1", "W1"), ("2", "W2"))]
    assert run("lot_event_to_lot_lineage") == [
        {"updates": {"parent_lot": "P1", "child_lot": "L1", "event_type": "split",
                     "event_time": T1, "lot_lineage_key": f"P1|L1|split|{T1}"},
         "source_name": "chain_ingestion", "updated_by": "chain_lot_lineage",
         "business_key_val": f"P1|L1|split|{T1}"}]


@pytest.mark.parametrize("name, cell", [("lot_event_to_lot_slot_wafer", "target_slot_column"),
                                        ("lot_event_to_lot_slot_wafer", "list_delimiter"),
                                        ("lot_event_to_lot_lineage", "parent_column")])
def test_a_missing_cell_is_refused_by_name_with_the_migration_as_next(name, cell):
    rule = copy.deepcopy(RULES[name])
    del rule["params"][cell]

    with pytest.raises(chain_bindings.ColumnBindingRefused) as refused:
        run(name, rule)

    assert f"'{cell}'" in str(refused.value) and name in str(refused.value)
    assert "scripts/migrate_ledger_config_to_v6.py" in str(refused.value)


@pytest.mark.parametrize("name, cell", [("lot_event_to_lot_slot_wafer", "target_wafer_column"),
                                        ("lot_event_to_lot_lineage", "target_child_column")])
def test_a_written_column_the_target_does_not_declare_is_refused_by_name(name, cell):
    rule = copy.deepcopy(RULES[name])
    rule["params"][cell] = "not_a_column"

    with pytest.raises(chain_bindings.ColumnBindingRefused, match="declares no such column"):
        run(name, rule)


def test_neither_mapper_spells_a_column_name():
    """가1: every string constant the code holds, docstrings aside, against every column the
    tables it reads and writes declare."""
    columns = {column for table in ("lot_event", "lot_slot_wafer", "lot_lineage")
               for column in TABLES[table]["column_types"]}
    for module in (lot_slot_wafer_mapper, lot_lineage_mapper):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                      if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                      and node.body and isinstance(node.body[0], ast.Expr)}
        spelled = {node.value for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)
                   and id(node) not in docstrings}
        assert not spelled & columns, (module.__name__, sorted(spelled & columns))


def test_a_rule_from_before_runs_on_after_the_migration_as_it_did():
    """The box's shape: the read cells flat, no written cells. The migration adds, under
    params, only what the rule does not state - and the rule then writes what it wrote."""
    shipped = RULES["lot_event_to_lot_slot_wafer"]
    before = {key: value for key, value in shipped.items() if key != "params"}
    before.update({cell: shipped["params"][cell] for cell in (
        "list_delimiter", "slot_list_column", "wafer_list_column", "lot_column",
        "time_column", "event_type_column")})
    rules = {"rules": [copy.deepcopy(before)]}

    said = v6.fill_lot_slot_wafer_params(rules)

    migrated = rules["rules"][0]
    assert said == ["chain_rules.lot_event_to_lot_slot_wafer.params: + " + ", ".join(
        f"{cell}={shipped['params'][cell]!r}" for cell in (
            "target_lot_column", "target_slot_column", "target_wafer_column",
            "target_time_column", "target_event_type_column"))]
    assert {key: value for key, value in migrated.items() if key != "params"} == before
    assert run("lot_event_to_lot_slot_wafer", migrated) == run("lot_event_to_lot_slot_wafer")
    assert v6.fill_lot_slot_wafer_params(rules) == [], "a second run changes nothing"
