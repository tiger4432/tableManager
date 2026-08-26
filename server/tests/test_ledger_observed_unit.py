# -*- coding: utf-8 -*-
"""Ruling R-2026-08-14-D + E - the `observed` word and the walk it must stay out of.

`ledger/observation_translator.py` was deleted on 2026-08-18 and the translation half of
this file went with it. What remains is live on both sides:

  * THE READ AXIS. `observed` is not in the walk, and `walk_predicates` /
    `traversable_predicates` / `walk_direction` are DERIVED from `PREDICATES` rather than
    listed. Addendum (1) of R-2026-08-14-D is a condition, not a feature: 102,177 findings
    reachable by the walk kill the trace screen. Read code, still running.
  * THE DECLARATION GRAMMAR, which `ledger/config.py` still validates. These die with that
    module, not before it.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config as ledger_config          # noqa: E402
from ledger import gate, vocabulary                 # noqa: E402


@pytest.fixture(autouse=True)
def _clean_counters():
    gate.reset_counters()
    yield
    gate.reset_counters()


# ------------------------------------------------------------------------- declarations
def observation_cfg(**overrides):
    cfg = {
        "kind": "observation",
        "finding_kind": "void",
        "synthetic": True,
        "occurred_at_column": "observed_at",
        "occurred_at_timezone": "Asia/Seoul",
        "subject_types": ["Wafer"],
        "register_entity_types": ["Wafer"],
        "watermark": {"columns": ["updated_at", "row_id"]},
        "run": {"relation": "inspection_run", "key_column": "run_uid",
                "method_column": "method"},
        "columns": {"row_identity": "row_id", "wafer": "base_wafer_id",
                    "run_key": "run_uid", "die_x": "base_x", "die_y": "base_y",
                    "die_gate": "stack_gate", "inchip_x": "inchip_x",
                    "inchip_y": "inchip_y", "extent_x": "radius_x",
                    "extent_y": "radius_y", "unit": "unit"},
    }
    cfg.update(overrides)
    return cfg


def full_cfg(**overrides):
    return {"version": 1, "sources": {"void_obs": observation_cfg(**overrides)}}


# --------------------------------------------------------------------- the declaration
def test_an_observation_source_is_not_validated_against_the_lineage_columns():
    """`kind` exists because the two grammars have different required columns.

    Without the dispatch `void_obs` would be refused for having no `parent_lot`, which is
    a true statement about a declaration and a useless one.
    """
    ledger_config.validate(full_cfg())          # does not raise

    with pytest.raises(ledger_config.LedgerConfigError) as excinfo:
        ledger_config.validate({"version": 1, "sources": {
            "void_obs": observation_cfg(run=None)}})
    assert "run" in str(excinfo.value)

    with pytest.raises(ledger_config.LedgerConfigError) as excinfo:
        ledger_config.validate({"version": 1, "sources": {
            "void_obs": observation_cfg(watermark={})}})
    assert "watermark" in str(excinfo.value)


def test_a_column_mapping_nothing_reads_is_refused():
    """Ruling R-2026-08-13-D, applied to the new grammar: a declaration field has an
    enforcement point or it does not exist. Here it is usually a typo for one that IS
    read, and a silently ignored mapping means an atom quietly missing a field."""
    cfg = observation_cfg()
    cfg["columns"]["radius"] = "radius_x"
    with pytest.raises(ledger_config.LedgerConfigError) as excinfo:
        ledger_config.validate({"version": 1, "sources": {"void_obs": cfg}})
    assert "radius" in str(excinfo.value)




# ------------------------------------------------------------- the walk (R-2026-08-14-E)




def test_the_walk_declaration_is_complete_and_binds_nothing_it_should_not():
    """Every predicate declares `traversable`, and a direction only where it is walked.

    The second half is the one that matters: a direction on an edge nobody traverses would
    teach a reader a constraint that binds nothing, which is the decoy declaration this
    project has already ruled on twice.
    """
    assert vocabulary.check_walk_declaration() == []
    for name, sig in vocabulary.PREDICATES.items():
        if sig["traversable"] is not True:
            assert sig["direction"] is None, name
