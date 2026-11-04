# -*- coding: utf-8 -*-
"""Rules that wake each other by column, inside one table, never settle - refused, as a circular reference (owner 10-28
ㄱ: b=[c]+1 with c=[b]+1). One judge, `ingestion_worker.column_loops`, read by the loader and the save door; a loop
through a rule woken by its whole table is still only reported (판정 402).

    case                                         gate
    two formulas reading each other              the second save refused «fx: b -> c -> b - …»
    three in a ring                              the closing save refused, the loop as the values flow
    a loop written by hand                       both refused at load, the list's sentence
    a chain a -> b -> c                          stands; no table loop said for it
    a join and a formula in a ring               refused at load
    a rule woken by its whole table              reported as a table loop, not refused
    rules that do not opt in                     no loop - their writes wake nothing
    a join woken by a key its row is found by    stands at load and at save - target_columns adds
      (business key, a composite piece, map key)   the key, the loop does not count it (owner 11-04)
    a join writing a finding column it lists     refused - it changes it
    two joins taking each other's key            refused at load and at save, as today -
                                                 조인 고리 거절, 소유자 11-04 ㄱ: rows that
                                                 disagree never settle and the cut value is right for neither side
"""
import json

import pytest
from fastapi import HTTPException

from chain import formula
from chain import ingestion_worker as worker
from database import crud
from ledger import admin

T = "fx"
TABLES = {T: {"business_key": "k", "composite_key_source": ["k"],
              "column_types": {"k": "string", "a": "number", "b": "number", "c": "number", "d": "number",
                               "t": "string", "x": "number"}},
          "fk": {"business_key": "bk", "composite_key_source": ["p", "q"], "map_key_columns": ["m"],
                 "column_types": {c: "string" for c in ("bk", "p", "q", "m", "v", "w")}},
          "fs": {"business_key": "sk", "composite_key_source": ["sk"],
                 "column_types": {c: "string" for c in ("sk", "bk", "p", "q", "m", "v", "w")}}}
NEVER = " - these rules wake each other and never settle"


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch):
    import mapper_sdk

    for name, config in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, config)
    mapper_sdk.discover()
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "bk"))
    worker.forget_loaded_chain_rules()
    yield path
    worker.forget_loaded_chain_rules()


def _save(path, column, text):
    return admin.save_chain_rule_raw(formula.RULE_NAME % (T, column), formula.to_declaration(T, column, text),
                                     admin.file_fingerprint(str(path)))


def _write(path, *declarations):
    path.write_text(json.dumps({"rules": list(declarations)}), encoding="utf-8")
    worker.forget_loaded_chain_rules()


def _join_x_from_b():
    return {"name": "copy x", "enabled": True, "allow_chain_trigger": True, "on": {"table": T}, "into": {"table": T},
            "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}],
                                                "take": [{"into": "x", "from": "b"}]}}}


def test_two_formulas_reading_each_other_are_refused_at_the_second_save(rules_file):
    assert _save(rules_file, "b", "=[c]+1")["ok"]
    with pytest.raises(HTTPException) as refused:
        _save(rules_file, "c", "=[b]+1")
    assert "fx: b -> c -> b" + NEVER in str(refused.value.detail)


def test_three_in_a_ring_are_refused_at_the_closing_save(rules_file):
    assert _save(rules_file, "b", "=[c]+1")["ok"] and _save(rules_file, "c", "=[d]+1")["ok"]
    with pytest.raises(HTTPException) as refused:
        _save(rules_file, "d", "=[b]+1")
    assert "fx: b -> d -> c -> b" + NEVER in str(refused.value.detail), "in the direction the values flow"


def test_a_loop_written_by_hand_is_refused_at_load_with_the_lists_sentence(rules_file):
    _write(rules_file, formula.to_declaration(T, "b", "=[c]+1"), formula.to_declaration(T, "c", "=[b]+1"))
    assert [rule.get("name") for rule in worker.load_chain_rules()] == []
    said = "column_loop - fx: b -> c -> b" + NEVER
    assert worker.refused_chain_rules() == {"formula fx.b": said, "formula fx.c": said}


def test_a_chain_stands_and_no_table_loop_is_said_for_it(rules_file):
    _write(rules_file, *[formula.to_declaration(T, column, text)
                         for column, text in (("a", "=[t]+0"), ("b", "=[a]+1"), ("c", "=[b]*2"))])
    rules = worker.load_chain_rules()
    assert len(rules) == 3 and worker.refused_chain_rules() == {}
    assert worker.column_loops(rules) == [] and worker._validate_chain_cascade_graph(rules) == []


def test_a_join_and_a_formula_in_a_ring_are_refused_at_load(rules_file):
    _write(rules_file, _join_x_from_b(), formula.to_declaration(T, "b", "=[x]+1"))
    worker.load_chain_rules()
    assert set(worker.refused_chain_rules()) >= {"copy x", "formula fx.b"}
    assert worker.refused_chain_rules()["formula fx.b"] == "column_loop - fx: b -> x -> b" + NEVER


def _stood(column, text):
    from chain import rule_shape

    return rule_shape.expand_declaration(formula.to_declaration(T, column, text), crud.TABLE_CONFIG)[0][0]


def test_a_rule_woken_by_its_whole_table_is_reported_not_refused(rules_file):
    whole = dict(_stood("b", "=[c]+1"), name="whole", trigger_columns=[])   # writes b, woken by any change of fx
    ring = [whole, _stood("c", "=[b]+1")]
    assert worker.column_loops(ring) == []
    assert worker._validate_chain_cascade_graph(ring) == ["allow_chain_trigger cycle: fx -> fx"]


def test_rules_that_do_not_opt_in_make_no_loop(rules_file):
    ring = [_stood("b", "=[c]+1"), _stood("c", "=[b]+1")]
    assert [loop[1] for loop in worker.column_loops(ring)] == [["b", "c", "b"]], "the instrument sees the ring"
    assert worker.column_loops([dict(rule, allow_chain_trigger=False) for rule in ring]) == []


def _join_into_fk(name, key, take_into, listed):
    return {"name": name, "enabled": True, "allow_chain_trigger": True, "target_columns": listed,
            "on": {"table": "fs"}, "into": {"table": "fk"},
            "derive": {"kind": "join", "join": {"on": [{"left": key, "right": key}],
                                                "take": [{"into": take_into, "from": "v"}]}}}


@pytest.mark.parametrize("key", ["bk", "p", "q", "m"])
def test_a_join_woken_by_a_key_its_row_is_found_by_stands(rules_file, key):
    _write(rules_file, _join_into_fk("take v", key, "v", ["v"]))
    rules = worker.load_chain_rules()
    assert [rule.get("name") for rule in rules] == ["take v", "take v:target"] and worker.refused_chain_rules() == {}
    assert worker.column_loops(rules) == []


def test_a_join_writing_a_finding_column_it_lists_is_refused(rules_file):
    _write(rules_file, _join_into_fk("into bk", "bk", "bk", ["bk"]))
    worker.load_chain_rules()
    assert worker.refused_chain_rules()["into bk:target"] == "column_loop - fk: bk -> bk" + NEVER


def test_two_joins_taking_each_others_key_are_refused(rules_file):
    _write(rules_file, _join_into_fk("w by v", "v", "w", ["w"]), _join_into_fk("v by w", "w", "v", ["v"]))
    worker.load_chain_rules()
    said = "column_loop - fk: v -> w -> v" + NEVER
    refused = worker.refused_chain_rules()
    assert (refused.get("w by v:target"), refused.get("v by w:target")) == (said, said)


def _save_join(path, declaration):
    return admin.save_chain_rule_raw(declaration["name"], declaration, admin.file_fingerprint(str(path)))


@pytest.mark.parametrize("key", ["bk", "p", "q", "m"])
def test_the_save_door_takes_a_join_woken_by_a_key_its_row_is_found_by(rules_file, key):
    assert _save_join(rules_file, _join_into_fk("take v", key, "v", ["v"]))["ok"]


def test_the_save_door_refuses_two_joins_taking_each_others_key(rules_file):
    assert _save_join(rules_file, _join_into_fk("w by v", "v", "w", ["w"]))["ok"]
    with pytest.raises(HTTPException) as refused:
        _save_join(rules_file, _join_into_fk("v by w", "w", "v", ["v"]))
    assert "fk: v -> w -> v" + NEVER in str(refused.value.detail)
