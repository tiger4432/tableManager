# -*- coding: utf-8 -*-
"""Lead 11-08 (QA): «is this rule on» has one answer. A rule the chain switched off after its failures in a row
(`control.count_outcome`) read ON everywhere but the drain - the catalogue drew it enabled and a replay still ran it.

  the running state    `loaded_chain_rules` - the declared rules with the chain's switch-off (`control.with_rules_off`)
  the declared rules   `declared_chain_rules` - what builds structure (an index must not come and go with failures)
  the axes             switched off · switched on again by a save (`release_rules`) · a rule never switched off
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import control, graph, replay                             # noqa: E402
from chain import ingestion_worker as worker                         # noqa: E402

RULES = [{"name": "r_fails", "trigger_table": "t_a", "target_table": "t_b", "enabled": True},
         {"name": "r_runs", "trigger_table": "t_a", "target_table": "t_c", "enabled": True}]


@pytest.fixture(name="held")
def fixture_held(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "control_path", lambda: str(tmp_path / "chain_control.json"))
    monkeypatch.setattr(worker, "_LOADED_RULES", [dict(rule) for rule in RULES])
    control.count_outcome(["r_fails"], failed=True, cap=2)
    control.count_outcome(["r_fails"], failed=True, cap=2)
    assert list(control.rules_off()) == ["r_fails"], "canary: the chain switched the rule off"


def _on(rules):
    return {rule["name"]: rule.get("enabled", True) is not False for rule in rules}


def test_a_switched_off_rule_reads_off_where_it_runs_and_stays_declared(held):
    assert _on(worker.loaded_chain_rules()) == {"r_fails": False, "r_runs": True}
    assert [rule["name"] for rule in replay.load_rules()] == ["r_runs"], "a replay does not run it"
    assert _on(graph._chain_rules()) == {"r_fails": False, "r_runs": True}, "the catalogue draws it off"
    assert _on(worker.declared_chain_rules()) == {"r_fails": True, "r_runs": True}, "structure reads the declaration"


def test_a_save_switches_it_on_again_everywhere(held):
    control.release_rules()
    assert _on(worker.loaded_chain_rules()) == {"r_fails": True, "r_runs": True}
    assert [rule["name"] for rule in replay.load_rules()] == ["r_fails", "r_runs"]


def test_the_rule_s_own_screen_reads_it_off(held, tmp_path, monkeypatch):
    import json

    from ledger import admin

    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": RULES}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    assert admin.chain_rule_raw_view("r_runs")["enabled"] is True, "canary: the view reads this file"
    assert admin.chain_rule_raw_view("r_fails")["enabled"] is False


def test_a_derived_key_index_reads_the_declared_rules(held, monkeypatch):
    from database import models

    asked = []
    monkeypatch.setattr(worker, "declared_chain_rules", lambda: asked.append("declared") or [])
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: asked.append("running") or [])
    models.derived_key_indexes(tables={})
    assert asked == ["declared"], "an index must not come and go with a rule's failures"
