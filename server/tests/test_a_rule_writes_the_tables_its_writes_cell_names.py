# -*- coding: utf-8 -*-
"""Lead 10-22 (widens 2dd93d4a9): a rule writes its target and the tables its `writes` cell names - `reads`'s twin.
Every seat that asks «what does this rule write» asks `chain_bindings.rule_tables(rule, write)`.

  the list      the writes tables join the target in rule_tables; a rule without the cell writes its target only
  the save      a writes table the catalogue does not declare is refused by name; a non-list too
  the batch     a scoped batch to a writes table is the target's kind (replace_map with a scope); another table is
                still refused, and a trigger write-back still plain updates only
  the group     its tables are the group's targets - held and ordered like the target
  the cycle     a loop closed by a writes table is seen
"""
import types

import pytest

import chain_bindings as cb
import dt_map_derivation
from chain import ingestion_worker as worker
from database import crud

RULE = {"name": "r", "enabled": True, "trigger_table": "t", "target_table": "u", "writes": ["w1", "w2"],
        "allow_replace_map": True, "allow_chain_trigger": True}


def test_the_writes_tables_join_the_target():
    assert cb.rule_tables(RULE, cb.TABLE_ROLE_WRITE) == {"u", "w1", "w2"}
    assert cb.rule_tables(dict(RULE, writes=None), cb.TABLE_ROLE_WRITE) == {"u"}
    assert "w1" not in cb.rule_tables(RULE, cb.TABLE_ROLE_READ)


@pytest.fixture
def declared(monkeypatch):
    for name in ("t", "u", "w1"):
        monkeypatch.setitem(crud.TABLE_CONFIG, name, {"column_types": {"request_id": "string"}})


@pytest.mark.parametrize("writes, code", [(["w1"], None), (["w1", "nowhere"], "unknown_writes_table"),
                                          ("w1", "bad_writes"), ([""], "bad_writes")])
def test_the_save_refuses_a_writes_table_it_does_not_declare(declared, writes, code):
    issues = cb.rule_refusals(dict(RULE, writes=writes, mapper="m"), "rules[0]", mapper_resolvable=lambda name: True,
                              derived_tables=set())
    codes = [issue.code for issue in issues if "writes" in issue.code]
    assert codes == ([] if code is None else [code]), [(i.code, str(i)) for i in issues]


def test_a_scoped_batch_goes_to_a_writes_table_as_to_the_target():
    batch = {"target_table": "w1", "replace_map": True, "scope": {"request_id": "R1"}, "updates": [{"updates": {}}]}
    assert dt_map_derivation.normalize_scoped_batch(batch, RULE, "u") == ("w1", [{"updates": {}}],
                                                                         {"request_id": "R1"}, None)
    with pytest.raises(ValueError, match="cannot redirect a scoped batch to 'elsewhere'"):
        dt_map_derivation.normalize_scoped_batch(dict(batch, target_table="elsewhere"), RULE, "u")
    with pytest.raises(ValueError, match="a write-back is plain updates only"):
        dt_map_derivation.normalize_scoped_batch(dict(batch, target_table="t"), RULE, "u")


def test_the_writes_tables_are_the_groups_targets():
    event = types.SimpleNamespace(table_name="t", event_type="CREATE", payload={})
    assert worker._group_target_tables([event], [RULE]) == {"u", "w1", "w2"}


def test_a_loop_closed_by_a_writes_table_is_seen():
    back = {"name": "back", "enabled": True, "trigger_table": "w2", "target_table": "t", "allow_chain_trigger": True}
    found = worker._validate_chain_cascade_graph([RULE, back])
    assert found and "w2" in found[0]
    assert worker._validate_chain_cascade_graph([dict(RULE, writes=None), back]) == [], "the control: no writes, no loop"


def test_the_census_photographs_the_writes_tables():
    from chain import rule_census

    assert rule_census.rule_row(RULE, 0)["tables"]["writes"] == ["w1", "w2"]
    changed = rule_census.census_diff(rule_census.census([dict(RULE, writes=["w1"])]), rule_census.census([RULE]))
    assert changed, "a writes cell that changed is a change the boot line says"
