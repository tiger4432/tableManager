"""The ai_model sample world (lead 10-27 A-4): it reads the AI's structure and step-map tables and points at the shared
types with `imports`, so its quantity · step · physical_* are the default world's nodes. A «no common» answer says no
`is_a` and leaves the row's other sentences standing (a mapping's `when`, no code). The declarations are the committed
samples; the rows are this file's."""
import copy
import os

import pandas as pd
import pytest

from ledger import setup, setup_bundle
from ledger.backfill import _v2_frame, prepare_v2_cursor_batch
from ledger.implementations import role_mapper_registry, trusted_implementations
from ledger.roleframe import dry_run_event_frame, mapper_context
from ledger.setup_bundle import require_ready_bundle, validate_bundle, validate_bundle_errors
from ledger.setup_registry import compile_setup_snapshot
from support import declaration

STORED_AT = pd.Timestamp("2026-10-28T01:00:00+00:00")


@pytest.fixture(scope="module")
def worlds():
    catalog = setup.load_physical_catalog(os.path.join(declaration.SAMPLE, "table_config.json.sample"))
    written = declaration.committed_worlds()
    imported = {name: {"entities": dict(doc["entities"]), setup_bundle.IMPORTS: dict(doc.get(setup_bundle.IMPORTS) or {})}
                for name, doc in ((n, setup_bundle.fold_versions(d)) for n, d in written.items())}  # as live_imported
    return catalog, written, imported


def _said(worlds, source, rows):
    catalog, written, imported = worlds
    snapshot = compile_setup_snapshot(require_ready_bundle(validate_bundle(
        written["ai_model"], catalog=catalog, imported=imported)), trusted_implementations(), catalog=catalog)
    refusals = []
    events = prepare_v2_cursor_batch(snapshot, source, _v2_frame([dict(r, created_at=STORED_AT) for r in rows]),
                                     refusals=refusals)
    atoms = [atom for event in events for atom in dry_run_event_frame(
        mapper_context(snapshot, source), event, role_mapper_registry()).ledger_frame.to_dict("records")]
    return sorted((a["subject_type"], tuple(sorted(a["subject_keys"].values())), a["predicate"],
                   a["object_payload"]["type"], tuple(sorted(a["object_payload"]["keys"].values()))) for a in atoms), refusals


def test_the_world_takes_the_shared_types_from_the_default_world(worlds):
    catalog, written, imported = worlds
    assert validate_bundle_errors(written["ai_model"], catalog=catalog, imported=imported) == ()
    resolved, notices, refusals = setup_bundle.resolve_imports(written["ai_model"], imported)
    assert (notices, refusals) == ((), ())
    for name in ("process_step", "quantity", "physical_object"):
        assert resolved["entities"][name] == imported["default"]["entities"][name], "the default's keys, one place"
    assert "product_structure" in imported["ai_model"]["entities"]
    assert "product_structure" not in imported["default"]["entities"], "declared once"
    default = setup_bundle.fold_versions(written["default"])
    for predicate in ("part_of", "acts_on", "describes", "is_a"):
        assert predicate not in default["vocabulary"], "one definition of each name"
    assert default["vocabulary"]["of_kind"]["subjects"] == ["defect"]


def test_without_imports_the_world_does_not_stand(worlds):
    catalog, written, imported = worlds
    bare = copy.deepcopy(written["ai_model"])
    bare.pop(setup_bundle.IMPORTS)
    assert validate_bundle_errors(bare, catalog=catalog, imported=imported), "its quantity · step are not its own"


def test_a_structure_row_says_part_of_and_is_a_and_no_common_says_no_is_a(worlds):
    said, refusals = _said(worlds, "ai_structure", [
        {"row_id": "s1", "product": "P1", "structure": "V1", "parent": "M1", "kind": "via"},
        {"row_id": "s2", "product": "P1", "structure": "D1", "parent": "M1", "kind": "no common"}])
    assert refusals == []
    assert said == [
        ("product_structure", ("D1", "P1"), "part_of", "product_structure", ("M1", "P1")),
        ("product_structure", ("P1", "V1"), "is_a", "physical_object", ("via",)),
        ("product_structure", ("P1", "V1"), "part_of", "product_structure", ("M1", "P1"))]


def test_a_step_map_row_says_acts_on_is_a_and_describes(worlds):
    said, refusals = _said(worlds, "ai_step_map", [
        {"row_id": "m1", "product": "P1", "step_seq": "AA010", "item_id": None, "process_kind": "etch",
         "acts_on": "V1", "item_desc": None},
        {"row_id": "m2", "product": "P1", "step_seq": "AA020", "item_id": "THK", "process_kind": "no common",
         "acts_on": "V1", "item_desc": "thickness"}])
    assert refusals == []
    assert said == [
        ("process_step", ("AA010", "P1"), "acts_on", "product_structure", ("P1", "V1")),
        ("process_step", ("AA010", "P1"), "is_a", "physical_process", ("etch",)),
        ("process_step", ("AA020", "P1"), "acts_on", "product_structure", ("P1", "V1")),
        ("quantity", ("THK",), "describes", "product_structure", ("P1", "V1"))]
