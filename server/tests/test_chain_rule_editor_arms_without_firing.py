# -*- coding: utf-8 -*-
"""Saving a chain rule must arm it, not fire it.

The transform CODE has list, read and write routes and a screen; the rule that hangs that
code on a table had only a read - so the last step of "the chain builds the table" was
outside the application.

🔴 BUT A RULE IS NOT A TABLE. A saved table registers something and nothing runs; a saved
rule is re-read by load_chain_rules on the next SYSTEM_RELOAD and RUNS, with no restart,
because `rule.get("enabled", True)` defaults to ON at all six sites that ask. "The same
shape as the table editor" therefore means the save must carry the same WEIGHT - so a new
rule lands switched off, and the operator turns it on by editing that value in the same
raw editor.

⚠️ Editing an EXISTING rule leaves `enabled` exactly as it was. Silently switching off
something that was running is the worse half of the same mistake.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_admin                                             # noqa: E402


@pytest.fixture
def rules_file(tmp_path, monkeypatch):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [
        {"name": "live_one", "trigger_table": "a", "target_table": "b", "enabled": True},
    ]}), encoding="utf-8")
    monkeypatch.setattr(ledger_admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(ledger_admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))
    return path


def base_of(path):
    return ledger_admin.file_fingerprint(str(path))


def rules_of(path):
    return {r["name"]: r for r in json.loads(path.read_text(encoding="utf-8"))["rules"]}


def test_a_NEW_rule_is_saved_armed_but_not_firing(rules_file):
    """🔴 THE RULING. Saving is loading; it must not also be firing."""
    result = ledger_admin.save_chain_rule_raw(
        "fresh", {"trigger_table": "x", "target_table": "y"}, base_of(rules_file))
    assert result["created"] is True
    assert result["enabled"] is False
    assert rules_of(rules_file)["fresh"]["enabled"] is False


def test_editing_an_existing_rule_does_not_switch_it_off(rules_file):
    """⚠️ The worse half of the same mistake: a rule that was running stops, silently,
    because somebody fixed a typo in it."""
    ledger_admin.save_chain_rule_raw(
        "live_one", {"trigger_table": "a2", "target_table": "b"}, base_of(rules_file))
    saved = rules_of(rules_file)["live_one"]
    assert saved["enabled"] is True
    assert saved["trigger_table"] == "a2"


def test_an_explicit_enabled_is_respected_on_both_paths(rules_file):
    """Turning it on IS the raw editor - no second control was invented for it."""
    ledger_admin.save_chain_rule_raw(
        "fresh", {"trigger_table": "x", "target_table": "y", "enabled": True},
        base_of(rules_file))
    assert rules_of(rules_file)["fresh"]["enabled"] is True


def test_the_other_rules_are_left_alone(rules_file):
    ledger_admin.save_chain_rule_raw(
        "fresh", {"trigger_table": "x", "target_table": "y"}, base_of(rules_file))
    assert set(rules_of(rules_file)) == {"live_one", "fresh"}


def test_a_moved_file_is_refused_by_name(rules_file):
    stale = base_of(rules_file)
    ledger_admin.save_chain_rule_raw("one", {"trigger_table": "x"}, stale)
    with pytest.raises(Exception) as raised:
        ledger_admin.save_chain_rule_raw("two", {"trigger_table": "x"}, stale)
    assert raised.value.detail["code"] == "stale_base"


def test_a_cycle_is_refused_by_the_validator_that_already_exists(rules_file):
    """⚠️ Found by measuring rather than by building: this is the ONE validator these
    rules have, and it reads the whole set. Nothing validates a single rule's shape -
    chain_bindings refuses at run time - and none was invented here."""
    ledger_admin.save_chain_rule_raw(
        "a_to_b", {"trigger_table": "a", "target_table": "b",
                   "allow_chain_trigger": True, "enabled": True}, base_of(rules_file))
    with pytest.raises(Exception) as raised:
        ledger_admin.save_chain_rule_raw(
            "b_to_a", {"trigger_table": "b", "target_table": "a",
                       "allow_chain_trigger": True, "enabled": True},
            base_of(rules_file))
    assert raised.value.detail["code"] == "chain_cycle"


def test_the_view_offers_one_rule_and_its_switch(rules_file):
    view = ledger_admin.chain_rule_raw_view("live_one")
    assert view["editable_unit"] == "rule"
    assert view["rules"] == ["live_one"]
    assert view["enabled"] is True
    assert view["base"] == base_of(rules_file)
