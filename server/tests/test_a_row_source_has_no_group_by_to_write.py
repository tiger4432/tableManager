"""총괄 3a109bfd9 ① (482288b12): `read.group_by` is a field of `unit: group` alone.

The skeleton gates it with `when {field: unit, is: group}`, so the save drops it from a row
source; the validator and the compiler read an absent one as empty through ONE accessor
(`setup_bundle.read_group_by`). The plan's 「Filled: unit=row -> no group_by」 row was the
second way of saying the same thing - it drew 「not applicable」 AND refilled the key the save
had dropped, so the save could not be the one that left it out.

The tracked sample writes no `group_by` on a row source; a file written before this carries
`"group_by": []` there (`held` below), and saving it is the path an operator's file takes.
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.config_authoring import authoring_plan, filled_declaration   # noqa: E402
from ledger.implementations import trusted_implementations               # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,                  # noqa: E402
                                 require_ready_bundle, validate_bundle,
                                 validate_bundle_errors)
from ledger.setup_registry import (compile_setup_snapshot,               # noqa: E402
                                   source_cursor_fingerprint)

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")


@pytest.fixture(scope="module", name="world")
def fixture_world():
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    # 🔴 THE SHIPPED SAMPLE HOLDS NO GROUP SOURCE SINCE setup_version 6 - lot_event was the only
    # one and it retired. So the group half is a variant of a shipped row source, declared here.
    grouped = copy.deepcopy(document["sources"]["lot_lineage"])
    grouped["read"] = {"unit": "group", "identity": ["child_lot"], "group_by": ["child_lot"],
                       "order_by": ["event_time", "lot_lineage_key"],
                       "occurred_at": dict(grouped["read"]["occurred_at"])}
    document["sources"]["lineage_by_child"] = grouped
    # A retired source is not read, so it has no unit to judge (lot_event, setup_version 6).
    units = {name: source["read"]["unit"] for name, source in document["sources"].items()
             if source.get("status") != "retired"}
    assert "row" in units.values() and "group" in units.values(), (
        "CANARY: the sample must carry both units", units)
    held = copy.deepcopy(document)
    for name, unit in units.items():
        if unit == "row":
            assert "group_by" not in document["sources"][name]["read"], name
            held["sources"][name]["read"]["group_by"] = []
    return document, held, catalog, units


def _saved(document, catalog, names):
    """`document` with each of `names` passed through the save's own filling."""
    saved, dropped = copy.deepcopy(document), {}
    for name in names:
        out, went = filled_declaration(document, catalog, ["sources", name],
                                       document["sources"][name])
        saved["sources"][name] = out
        dropped[name] = [item["path"] for item in went]
    return saved, dropped


def _fingerprints(document, catalog):
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    snapshot = compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog)
    return {name: source_cursor_fingerprint(snapshot, name) for name, plan
            in snapshot.source_plans.items() if plan.runs}


def test_a_saved_row_source_leaves_group_by_out_and_the_bundle_still_validates(world):
    document, held, catalog, units = world
    rows = [name for name, unit in units.items() if unit == "row"]
    saved, dropped = _saved(held, catalog, rows)
    for name in rows:
        assert "group_by" not in saved["sources"][name]["read"], name
        assert "bundle.sources.%s.read.group_by" % name in dropped[name], dropped[name]
    assert validate_bundle_errors(saved, catalog=catalog) == ()
    assert validate_bundle_errors(document, catalog=catalog) == ()


def test_leaving_it_out_moves_no_sources_fingerprint(world):
    """A moved fingerprint stops that source's cursor (`cursor_snapshot_reset_required`)."""
    document, held, catalog, units = world
    saved, _ = _saved(held, catalog, [n for n, unit in units.items() if unit == "row"])
    assert saved != held
    before = _fingerprints(held, catalog)
    assert _fingerprints(saved, catalog) == before
    assert _fingerprints(document, catalog) == before


def test_a_row_sources_bundle_holds_none_and_its_compiled_plan_reads_it_empty(world):
    """The explorer cuts a draft's `raw` from the loaded bundle (`config_drafts.create`), so a
    bundle that filled `[]` in made every row-source save report dropping it (총괄 3a109bfd9)."""
    document, _, catalog, units = world
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    snapshot = compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog)
    for name, unit in units.items():
        read = bundle.to_mapping()["sources"][name]["read"]
        compiled = snapshot.source_plans[name].driver.group_by
        if unit == "row":
            assert "group_by" not in read and compiled == (), (name, compiled)
        else:
            assert compiled == tuple(document["sources"][name]["read"]["group_by"]), name


def test_a_group_source_keeps_its_group_by_and_its_row_in_the_plan(world):
    document, _, catalog, units = world
    groups = [name for name, unit in units.items() if unit == "group"]
    saved, dropped = _saved(document, catalog, groups)
    for name in groups:
        assert saved["sources"][name]["read"]["group_by"] == \
            document["sources"][name]["read"]["group_by"]
        assert not [path for path in dropped[name] if path.endswith(".group_by")]
    drawn = {row["path"] for row in authoring_plan(document, catalog)["fields"]
             if row["path"].endswith(".read.group_by")}
    # The form draws a RETIRED source's declaration too - it is still a declaration an
    # operator may edit - so its group_by square is drawn beside the live ones.
    retired_groups = [name for name, source in document["sources"].items()
                      if source.get("status") == "retired" and source["read"]["unit"] == "group"]
    assert drawn == {"bundle.sources.%s.read.group_by" % name
                     for name in groups + retired_groups}, drawn


def test_a_group_source_without_group_by_groups_by_its_identity(world):
    """총괄 0c9b6e3c0 ③ ㄴ - 3a109bfd9 ① reversed: left out, group_by is the source's identity,
    the value the form already offered. The same bundle, so the same atoms, as writing it."""
    document, _, catalog, units = world
    name = next(n for n, unit in units.items() if unit == "group")
    cut = copy.deepcopy(document)
    del cut["sources"][name]["read"]["group_by"]
    written = copy.deepcopy(cut)
    written["sources"][name]["read"]["group_by"] = list(cut["sources"][name]["read"]["identity"])
    assert validate_bundle_errors(cut, catalog=catalog) == ()
    assert validate_bundle(cut, catalog=catalog).to_mapping() == (
        validate_bundle(written, catalog=catalog).to_mapping())
    snapshot = lambda doc: compile_setup_snapshot(
        require_ready_bundle(validate_bundle(doc, catalog=catalog)), trusted_implementations(),
        catalog=catalog).snapshot_sha256
    assert snapshot(cut) == snapshot(written)
