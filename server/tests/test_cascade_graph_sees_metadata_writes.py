# -*- coding: utf-8 -*-
"""The cycle guard has to see BOTH tables a rule writes, not just its target.

A rule declaring `allow_map_metadata_upsert` writes map metadata as well as its target
table, and that write raises its own chain event. The guard built its graph from
`target_table` alone, so that second edge existed in the running system and not in the
graph it checked.

MEASURED 2026-09-04: rule #3 (dt_inventory -> dt_map) wrote five metadata rows per run
under that flag; those woke the metadata -> dt_inventory rule; and #3 consumes
dt_inventory under `allow_chain_trigger`. A live cycle, and this validator passed it -
it was caught by a human enabling the hop, watching the loop, and reversing it by hand.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                          # noqa: E402
import map_meta_registrar                                        # noqa: E402

META = map_meta_registrar.META_TABLE


def rule(name, trigger, target, meta=False, chain=True, enabled=True):
    return {"name": name, "trigger_table": trigger, "target_table": target,
            "allow_map_metadata_upsert": meta, "allow_chain_trigger": chain,
            "enabled": enabled}


def test_a_loop_closed_by_the_metadata_write_is_refused():
    """🔴 THE ONE THAT GOT THROUGH. Neither `target_table` closes the loop; the metadata
    write does."""
    rules = [rule("writes_map_and_meta", "dt_inventory", "dt_map", meta=True),
             rule("meta_back_to_trigger", META, "dt_inventory")]
    with pytest.raises(ValueError) as raised:
        worker._validate_chain_cascade_graph(rules)
    assert "cycle" in str(raised.value)
    assert META in str(raised.value) and "dt_inventory" in str(raised.value)


def test_the_same_pair_without_the_metadata_flag_is_fine():
    """The discriminator: identical rules, flag off. If this also refused, the guard
    would be rejecting on the pair rather than on the edge."""
    rules = [rule("writes_map_only", "dt_inventory", "dt_map", meta=False),
             rule("meta_back_to_trigger", META, "dt_inventory")]
    worker._validate_chain_cascade_graph(rules)


def test_a_metadata_writer_alone_is_not_a_cycle():
    """One rule writing two tables is two edges, not a loop. A guard that counted it as
    one would reject every metadata writer."""
    worker._validate_chain_cascade_graph(
        [rule("writes_map_and_meta", "dt_inventory", "dt_map", meta=True)])


def test_a_disabled_rule_does_not_close_the_loop():
    rules = [rule("writes_map_and_meta", "dt_inventory", "dt_map", meta=True),
             rule("meta_back_to_trigger", META, "dt_inventory", enabled=False)]
    worker._validate_chain_cascade_graph(rules)


def test_a_rule_that_is_not_chain_triggered_does_not_close_the_loop():
    """The graph is about OPT-IN chain edges. A rule that does not consume chain events
    cannot continue a cascade."""
    rules = [rule("writes_map_and_meta", "dt_inventory", "dt_map", meta=True),
             rule("meta_back_to_trigger", META, "dt_inventory", chain=False)]
    worker._validate_chain_cascade_graph(rules)


def test_the_live_declaration_still_passes():
    """⛔ ZERO FALSE POSITIVES on what is actually declared. A guard that starts refusing
    the current configuration stops the worker from loading at all."""
    import io
    import json

    path = os.path.join(os.path.dirname(__file__), "..", "config", "chain_rules.json")
    if not os.path.exists(path):
        pytest.skip("no live chain rules on this box")
    rules = json.load(io.open(path, encoding="utf-8"))["rules"]
    worker._validate_chain_cascade_graph(rules)
