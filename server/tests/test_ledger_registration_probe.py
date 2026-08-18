"""The first-sight probe is declared, and the declaration reproduces the old literals.

`backfill._v2_lot_event_subjects` hard-coded `lot_id`/`parent_lot`/`child_lot`/`waferids`,
the types `Lot`/`Wafer`, and the separator `":"`, while `run()` sent EVERY v2 source through
it -- so no source but `lot_event` could be stood up on v2 at all.

🔴 THE ATOM BASELINE CANNOT SEE THIS CHANGE. `task/evidence/ledger_atom_baseline.py` calls
`preview_selected_cursor_batch(..., known_registrations=())`, supplying the set directly, so
the probe never runs there and a diff of 0 says nothing about it. This file is the proof
that belongs with the change: the declaration must produce the SAME set the literals did,
on the same frames, or the round's own gate is blind to a regression.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.backfill import _v2_registration_subjects                    # noqa: E402
from ledger.setup import load_setup                         # noqa: E402
from ledger.envelope import canonical_keys                               # noqa: E402
from ledger.setup_bundle import (                                        # noqa: E402
    LedgerSetupValidationError,
    require_ready_bundle,
    validate_bundle,
    validate_bundle_errors,
)
from ledger.setup_registry import compile_setup_snapshot                 # noqa: E402
from ledger.implementations import trusted_implementations               # noqa: E402


LOT_EVENT_PROBE = [
    {"entity_type": "Lot@1", "columns": ["lot_id", "parent_lot", "child_lot"]},
    {"entity_type": "Wafer@1", "columns": ["waferids"], "list_separator": ":"},
]

FRAMES = {
    "split": pd.DataFrame([
        # `txn_seq` carries no subject and is here on purpose: the superset test widens
        # the probe onto it, which only proves anything if the column is really in the
        # frame. A widening onto an absent column is silently a no-op.
        {"lot_id": "CL-2601-006", "parent_lot": "", "child_lot": "CL-2601-006-A1",
         "waferids": "W01:W02", "txn_seq": "1001"},
        {"lot_id": "CL-2601-006-A1", "parent_lot": "CL-2601-006", "child_lot": "",
         "waferids": "W01", "txn_seq": "1002"},
    ]),
    "merge": pd.DataFrame([
        {"lot_id": "CL-2601-008", "parent_lot": "", "child_lot": "CL-2601-008-M",
         "waferids": "W21:W22"},
        {"lot_id": "CL-2601-008-M", "parent_lot": "CL-2601-008", "child_lot": "",
         "waferids": "W21:W22"},
    ]),
    # The child lot is named ONLY by `child_lot` here -- its own row never arrived. This
    # is baseline case `split_incomplete_child_missing`, and it is the one frame where
    # dropping `child_lot` from the probe actually loses a subject; on a complete split
    # the child also appears as some row's `lot_id`, so a narrowed probe looks harmless.
    "split_child_row_missing": pd.DataFrame([
        {"lot_id": "CL-2601-007", "parent_lot": "", "child_lot": "CL-2601-007-A1",
         "waferids": "W11:W12", "txn_seq": "2001"},
    ]),
    "track_in": pd.DataFrame([
        {"lot_id": "CL-2601-009", "parent_lot": "", "child_lot": "",
         "waferids": "W31:W32:W33"},
    ]),
    "blank_and_padded": pd.DataFrame([
        {"lot_id": " CL-2601-010 ", "parent_lot": None, "child_lot": "",
         "waferids": " W41 : : W42 "},
    ]),
}


def _retired_hardcoded_subjects(frame):
    """VERBATIM copy of the deleted `backfill._v2_lot_event_subjects`.

    Kept here, and only here, as the reference the declaration is scored against. If it
    ever needs editing to keep a test green, the declaration has changed behaviour and the
    edit is the bug.
    """
    subjects = set()
    lots = set(frame["lot_id"].tolist())
    lots.update(frame["parent_lot"].tolist())
    lots.update(frame["child_lot"].tolist())
    for lot in lots:
        text = str(lot or "").strip()
        if text:
            subjects.add(("Lot", canonical_keys({"lot": text})))
    for value in frame["waferids"].tolist():
        for wafer in str(value or "").split(":"):
            text = wafer.strip()
            if text:
                subjects.add(("Wafer", canonical_keys({"wafer": text})))
    return subjects


def _plan_with_probe(probe):
    setup = load_setup()
    logical = setup.bundle.to_mapping()
    logical["sources"]["lot_event"]["driver"]["registration_probe"] = probe
    # Re-validating the live bundle must judge it against the SAME physical catalog the
    # load used -- `setup.catalog` carries it -- or the probe would be checked against one
    # world and the plan compiled against another.
    bundle = require_ready_bundle(validate_bundle(logical, catalog=setup.catalog))
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(),
        tuple(setup.snapshot.verified_joins.values()), catalog=setup.catalog)
    return snapshot.source_plans["lot_event"]


@pytest.mark.parametrize("name", sorted(FRAMES))
def test_the_declaration_reproduces_the_retired_literals_exactly(name):
    plan = _plan_with_probe(LOT_EVENT_PROBE)
    frame = FRAMES[name]
    assert _v2_registration_subjects(plan, frame) == _retired_hardcoded_subjects(frame)


def test_the_probe_is_a_superset_so_an_extra_column_cannot_move_atoms():
    """Over-declaring is the SAFE direction and this pins that it stays safe.

    The result only suppresses a register atom for a subject already in the store, so a
    candidate no atom mentions matches nothing. Under-declaring is what duplicates atoms,
    which is why the missing-column case below is the one that must differ.
    """
    frame = FRAMES["split"]
    baseline = _v2_registration_subjects(_plan_with_probe(LOT_EVENT_PROBE), frame)

    wider = _v2_registration_subjects(_plan_with_probe([
        {"entity_type": "Lot@1",
         "columns": ["lot_id", "parent_lot", "child_lot", "txn_seq"]},
        {"entity_type": "Wafer@1", "columns": ["waferids"], "list_separator": ":"},
    ]), frame)
    assert baseline < wider

    # Measured on the frame where it BITES. On a complete split the child lot also
    # arrives as a row's own `lot_id`, so narrowing the probe to `lot_id` changes nothing
    # and would have proved nothing -- two rules agreeing on one input decide neither.
    incomplete = FRAMES["split_child_row_missing"]
    full = _v2_registration_subjects(_plan_with_probe(LOT_EVENT_PROBE), incomplete)
    narrower = _v2_registration_subjects(_plan_with_probe([
        {"entity_type": "Lot@1", "columns": ["lot_id"]},
        {"entity_type": "Wafer@1", "columns": ["waferids"], "list_separator": ":"},
    ]), incomplete)
    assert narrower < full
    assert ("Lot", canonical_keys({"lot": "CL-2601-007-A1"})) in full - narrower


def test_a_missing_separator_would_probe_the_unsplit_string():
    """Names the failure the `list_separator` declaration exists to prevent."""
    frame = FRAMES["track_in"]
    without = _v2_registration_subjects(_plan_with_probe([
        {"entity_type": "Wafer@1", "columns": ["waferids"]},
    ]), frame)
    assert without == {("Wafer", canonical_keys({"wafer": "W31:W32:W33"}))}
    assert ("Wafer", canonical_keys({"wafer": "W31"})) not in without


def test_no_probe_answers_None_rather_than_an_empty_set():
    """`None` means "did not answer" and the runtime refuses; `set()` would claim
    "nothing is registered", suppress nothing, and duplicate every first-sight atom."""
    assert _v2_registration_subjects(_plan_with_probe([]), FRAMES["split"]) is None


@pytest.mark.parametrize("probe,code", [
    ([{"entity_type": "Nope@1", "columns": ["lot_id"]}], "unknown_entity_type"),
    ([{"entity_type": "Lot@1", "columns": ["no_such_column"]}], "unknown_column"),
    ([{"entity_type": "Lot@1", "columns": []}], "invalid_type"),
    ([{"entity_type": "Lot@1", "columns": ["lot_id"], "list_separator": ""}],
     "invalid_registration_probe"),
    ([{"entity_type": "Lot@1", "columns": ["lot_id"]},
      {"entity_type": "Lot@1", "columns": ["child_lot"]}],
     "duplicate_registration_probe"),
    ([{"entity_type": "Lot@1", "columns": ["lot_id"], "module": "os"}],
     "unsafe_declaration"),
])
def test_a_malformed_probe_is_refused_at_load_with_its_own_code(probe, code):
    setup = load_setup()
    logical = setup.bundle.to_mapping()
    logical["sources"]["lot_event"]["driver"]["registration_probe"] = probe
    issues = validate_bundle_errors(logical, catalog=setup.catalog)
    assert code in {issue.code for issue in issues}, [i.to_mapping() for i in issues]
    with pytest.raises(LedgerSetupValidationError):
        validate_bundle(logical, catalog=setup.catalog)


def test_the_shipped_config_still_loads_without_a_probe():
    """The field is optional, so adding it did not invalidate the operator's root."""
    setup = load_setup()
    assert setup.snapshot.source_plans["lot_event"].driver.registration_probe == ()
