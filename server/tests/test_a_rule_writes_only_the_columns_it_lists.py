# -*- coding: utf-8 -*-
"""총괄 a7b67be28 ㄱ (소유자 「ㄴ」): a chain rule lists the columns it writes - `target_columns`. One answer,
`chain_bindings.written_columns` (the list and the columns a row is found by), read by the write's filter
(`rule_run.signed`), `columns_a_rule_writes` and R2 narrowed to one rule (`replay.unwritten_scope`).

  filter     a whole row handed over keeps the listed column and the keys, in updates and batch items alike; map
             metadata is another table's and is not narrowed; a rule without the list is untouched
  answer     columns_a_rule_writes answers the list, whatever this run handed over
  save gate  a listed name the target table does not have, or a list that is not one, is refused by name
  withdraw   R2 for one rule: its declaration, the target's columns outside the list - a key column stays out of it
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                # noqa: E402
from chain import replay, rule_run                                   # noqa: E402
from database import crud                                            # noqa: E402

TABLE = {"business_key": "tkey", "composite_key_source": ["m", "k"], "map_key_columns": ["m"],
         "column_types": {"tkey": "string", "k": "string", "m": "string", "a": "string", "c": "string"}}
RULE = {"name": "wc_rule", "trigger_table": "wc_src", "target_table": "wc_target", "target_columns": ["c"]}


@pytest.fixture(autouse=True)
def table(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, "wc_target", TABLE)


def _row():
    return {"updates": {"tkey": "M1|k1", "k": "k1", "m": "M1", "a": "same as the file", "c": "mine"}}


def test_the_filter_keeps_the_list_and_the_keys():
    result = {"updates": [_row()], "batches": [{"updates": [_row()]}],
              "map_metadata_updates": [{"updates": {"a": "another table's"}}]}
    kept_out = {}
    rule_run.signed(result, "wc_rule", RULE, kept_out)
    for item in (result["updates"][0], result["batches"][0]["updates"][0]):
        assert item["updates"] == {"tkey": "M1|k1", "k": "k1", "m": "M1", "c": "mine"}, item
        assert item["updated_by"] == "wc_rule"
    assert result["map_metadata_updates"][0]["updates"] == {"a": "another table's"}
    assert kept_out == {"a": 2}

    plain = {"updates": [_row()]}
    rule_run.signed(plain, "wc_plain", dict(RULE, target_columns=None), {})
    assert plain["updates"][0]["updates"] == _row()["updates"]


def test_the_rule_answers_its_list():
    assert rule_run.columns_a_rule_writes(RULE, [_row()]) == {"c", "tkey", "k", "m", "row_id", "business_key_val"}


@pytest.mark.parametrize("listed, code", [(["c", "nope"], "unknown_target_columns_column"),
                                          ("c", "bad_target_columns"), (["c"], None)])
def test_the_save_gate_names_a_column_the_target_does_not_have(listed, code):
    issues = chain_bindings.rule_refusals(dict(RULE, target_columns=listed), "rules[0]",
                                          mapper_resolvable=lambda name: True, derived_tables=set())
    codes = [i.code for i in issues if "target_columns" in i.code]
    assert codes == ([code] if code else []), [(i.code, i.message) for i in issues]


def test_one_rules_withdrawal_takes_what_it_does_not_write(monkeypatch):
    monkeypatch.setattr(replay, "find_rule", lambda name, rules=None, row_scoped=False: dict(RULE, name=name))
    assert replay.unwritten_scope("wc_rule", "wc_target") == (("wc_rule",), ["a"])
    assert replay.unwritten_scope(None, "wc_target", ["a"]) == (None, ["a"])
    for table, rule, why in (("other", RULE, "writes 'wc_target'"),
                             ("wc_target", dict(RULE, target_columns=None), "lists no target_columns"),
                             ("wc_target", dict(RULE, target_columns=["a", "c"]), "nothing to withdraw")):
        monkeypatch.setattr(replay, "find_rule", lambda name, rules=None, row_scoped=False, rule=rule: rule)
        with pytest.raises(replay.ReplayRefused, match=why):
            replay.unwritten_scope("wc_rule", table)
