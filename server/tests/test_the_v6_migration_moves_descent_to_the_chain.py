# -*- coding: utf-8 -*-
"""`scripts/migrate_ledger_config_to_v6` (총괄 e14416950 · c6a8c069c ④): the shipped samples ARE
its target - a v5 setup (lot_event saying `descent`, no lineage table or rule) migrates to exactly
what ships, and a second run changes nothing."""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import migrate_ledger_config_to_v6 as v6                    # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
#: The ledger declaration as it shipped at setup_version 5 (022ffc74d), frozen: the shipped
#: sample no longer carries `prepare`, so a v5 rebuilt from it would test nothing.
V5_LEDGER = os.path.join(os.path.dirname(__file__), "support", "v5_setup", "ledger_config.json")


def load(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def shipped():
    return (load("ledger_config.json.sample"), load("table_config.json.sample"),
            load("chain_rules.json.sample"))


def as_v5(ledger, tables, rules):
    """The setup as it stood before v6: the frozen ledger, and the shipped table and rule
    samples without what the migration adds."""
    with open(V5_LEDGER, encoding="utf-8") as handle:
        ledger = json.load(handle)
    tables, rules = copy.deepcopy(tables), copy.deepcopy(rules)
    del tables[v6.LINEAGE]
    rules["rules"] = [r for r in rules["rules"] if r.get("name") != v6.LINEAGE_RULE]
    return ledger, tables, rules


def test_a_v5_setup_migrates_to_exactly_what_ships(shipped):
    ledger, tables, rules = as_v5(*shipped)

    said = v6.migrate(ledger, tables, rules)

    assert (ledger, tables, rules) == shipped
    assert said == [
        "sources.lot_event.bind.mappings.descent -> sources.lot_lineage (derived_from for split, merge)",
        "sources.lot_event: retired (its atoms stay)",
        "vocabulary.register@1.subjects: - lot@1, wafer@1 (no active source registers them)",
        "setup_version 5 -> 6: prepare dropped from 6 source(s) (die_inspection, dt_job, "
        "lot_event, lot_slot_wafer, transfer_event, wafer_process_recipe)",
        "table_config: + lot_lineage", "chain_rules: + lot_event_to_lot_lineage (enabled)"]


def test_a_second_run_changes_nothing(shipped):
    ledger, tables, rules = copy.deepcopy(shipped)

    assert v6.migrate(ledger, tables, rules) == []
    assert (ledger, tables, rules) == shipped


def test_exclude_when_moves_from_prepare_to_read_unchanged(shipped):
    ledger, tables, rules = as_v5(*shipped)
    clause = [{"column": "wafer", "blank": True}]
    ledger["sources"]["lot_slot_wafer"]["prepare"]["exclude_when"] = copy.deepcopy(clause)

    v6.migrate(ledger, tables, rules)

    source = ledger["sources"]["lot_slot_wafer"]
    assert source["read"]["exclude_when"] == clause and "prepare" not in source


def test_a_descent_end_with_two_keys_is_refused_rather_than_guessed(shipped):
    ledger, tables, rules = as_v5(*shipped)
    ledger["sources"]["lot_event"]["bind"]["mappings"]["descent"]["bind"]["target"]["keys"][
        "slot"] = {"kind": "column", "column": "slot"}

    with pytest.raises(v6.MigrationRefusal, match="one entity with one key"):
        v6.migrate(ledger, tables, rules)
