"""Compile the file-backed transfer sample through the production setup boundary."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import virtual_join_config as virtual_join_config_module

from ledger.implementations import trusted_implementations
from ledger.setup_bundle import (
    load_physical_catalog, load_setup_bundle, require_ready_bundle)
from ledger.setup_registry import compile_setup_snapshot


SAMPLE_ROOT = (
    Path(__file__).parents[2] / "config" / "sample" / "ontology" /
    "transfer_explorer")

#: The physical schema of the deployment the sample describes.  The sample is a DIFFERENT
#: plant -- that is the whole point of it, and the owner's completion bar ("a different
#: schema operating environment, zero Python, swap the declarations") is exactly what it
#: demonstrates.  A different plant has its own `table_config.json`, so the sample gets
#: one; it does NOT get a `tables` section back inside `ledger_config.json`, because the
#: thing being retired is the ledger keeping a physical copy nothing compares.
#:
#: It sits here rather than in the sample root because `load_setup_bundle` refuses a root
#: holding any JSON other than `ledger_config.json`, and that refusal is the single-file
#: promise -- not something to carve an exception into for a fixture.
SAMPLE_CATALOG = Path(__file__).parent / "transfer_explorer_table_config.json"


def load_transfer_sample_setup(_root: str | Path = SAMPLE_ROOT):
    catalog = load_physical_catalog(SAMPLE_CATALOG)
    bundle = require_ready_bundle(load_setup_bundle(SAMPLE_ROOT, catalog=catalog))
    raw = bundle.to_mapping()
    rule = raw["virtual_joins"]["dt_job_to_inventory"]
    normalized = [{
        "name": "dt_job_to_inventory",
        "left_table": rule["left_table"],
        "right_table": rule["right_table"],
        "join_key": [
            {"left": item["left"], "right": item["right"], "fold": None}
            for item in rule["join_key"]
        ],
        "expose": list(rule["expose"]),
        "join_cardinality": rule["join_cardinality"],
    }]
    with (
        patch.object(
            virtual_join_config_module, "load_virtual_join_rules",
            return_value=normalized),
        patch.object(
            virtual_join_config_module, "verify_uniqueness",
            return_value={
                "unique_index": "uq_dt_inventory_job",
                "refused": False,
                "code": None,
            }),
    ):
        verified = tuple(virtual_join_config_module.load_verified_rules(object()))
    # The sample names the GENERIC implementations the repository ships; the trusted set
    # is discovered from those classes rather than restated here.  This support module
    # used to carry a fourth hand-kept trust list, which is how the sample came to name
    # two implementations that existed nowhere.
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(), verified, catalog=catalog)
    return SimpleNamespace(config_root=SAMPLE_ROOT, bundle=bundle, snapshot=snapshot,
                           catalog=catalog)
