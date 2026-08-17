"""Stage 6 deterministic legacy <-> Ledger v2 semantic parity tests."""
from __future__ import annotations

import copy

import pytest

from ledger.runtime_v2 import preview_cursor_batch
from ledger.ledger_frame import atoms_from_ledger_frame
from ledger.shadow_parity import PARITY_FIELDS, compare_shadow
from test_ledger_setup_registry import snapshot
from test_ledger_source_preparation import (
    base_rows,
    mappers,
    preparers,
    reader_for,
)


def candidates():
    compiled = snapshot()
    base = base_rows(2)
    preview = preview_cursor_batch(
        compiled, "input_rows", base,
        {"event_at": base.iloc[-1]["event_at"],
         "record_id": base.iloc[-1]["record_id"]},
        reader_for(base), preparers(), mappers())
    return [dict(item) for item in preview.candidate_semantics]


def candidate_forms():
    compiled = snapshot()
    base = base_rows(2)
    preview = preview_cursor_batch(
        compiled, "input_rows", base,
        {"event_at": base.iloc[-1]["event_at"],
         "record_id": base.iloc[-1]["record_id"]},
        reader_for(base), preparers(), mappers())
    atoms = [
        atom
        for event in preview.event_results
        for atom in atoms_from_ledger_frame(event.ledger_frame)
    ]
    return atoms, [dict(item) for item in preview.candidate_semantics]


def test_existing_atom_envelope_and_v2_candidate_mapping_normalize_equally():
    atoms, mappings = candidate_forms()

    report = compare_shadow(atoms, mappings)

    assert report.status == "equal"
    assert report.equal_claims == len(atoms) == len(mappings)


def test_equal_semantics_are_order_independent_and_count_duplicates():
    values = candidates()
    report = compare_shadow(values + [values[0]], list(reversed(values)) + [values[0]])

    assert report.status == "equal"
    assert report.equal_claims == len(values) + 1
    assert report.differences == ()


def test_unexplained_semantic_difference_is_a_regression():
    legacy = candidates()
    v2 = copy.deepcopy(legacy)
    v2[0]["object_payload"]["keys"]["output_id"] = "CHANGED"

    report = compare_shadow(legacy, v2)

    assert report.status == "regression"
    assert report.regressions >= 1
    assert any(item.path.endswith("object_payload.keys.output_id")
               for item in report.differences)


def test_difference_requires_explicit_approved_explanation_or_ignore_rule():
    legacy = candidates()
    v2 = copy.deepcopy(legacy)
    v2[0]["source_translator_ver"] = "ledger-v2:new-compiler"

    explained = compare_shadow(
        legacy, v2,
        approved_explanations={
            "*.source_translator_ver": "v2 snapshot fingerprint replaces legacy name",
        },
    )
    ignored = compare_shadow(
        legacy, v2, ignored_fields=("source_translator_ver",))

    assert explained.status == "explained_difference"
    assert explained.explained_differences == 1
    assert explained.differences[0].reason == (
        "v2 snapshot fingerprint replaces legacy name")
    assert ignored.status == "equal"


def test_claim_count_difference_is_never_silently_lost():
    legacy = candidates()
    report = compare_shadow(legacy, legacy[:-1])

    assert report.status == "regression"
    assert report.regressions == 2
    assert any(".legacy_only[" in item.path for item in report.differences)
    assert any(item.path == "outcome.molecules" for item in report.differences)


def test_refusal_incomplete_and_molecule_outcomes_are_part_of_parity():
    values = candidates()
    report = compare_shadow(
        values, values,
        legacy_outcome={"molecules": 2, "refused": 1, "incomplete": 0},
        v2_outcome={"molecules": 2, "refused": 0, "incomplete": 1},
    )

    assert report.status == "regression"
    assert {item.path for item in report.differences} == {
        "outcome.refused", "outcome.incomplete"}


def test_outcome_contract_is_closed_and_non_negative():
    with pytest.raises(ValueError, match="contain exactly"):
        compare_shadow([], [], legacy_outcome={"refused": 0})
    with pytest.raises(ValueError, match="non-negative integer"):
        compare_shadow(
            [], [],
            legacy_outcome={"molecules": 0, "refused": -1, "incomplete": 0})


def test_parity_report_and_difference_order_are_deterministic():
    legacy = candidates()
    v2 = copy.deepcopy(legacy)
    v2[0]["source_raw_ref"] = "changed/ref"
    v2[-1]["source_who"] = "different-source"

    first = compare_shadow(legacy, v2).to_mapping()
    second = compare_shadow(list(reversed(legacy)), list(reversed(v2))).to_mapping()

    assert first == second


def test_parity_contract_is_closed_and_rejects_bad_normalization_declarations():
    assert set(PARITY_FIELDS) >= {
        "source_event_id", "source_event_state", "subject_type", "subject_keys",
        "predicate", "object_kind", "object_payload", "occurred_at",
        "source_who", "source_raw_ref", "derivation", "supersedes",
        "molecule_ref",
    }
    with pytest.raises(ValueError, match="unknown parity ignored fields"):
        compare_shadow([], [], ignored_fields=("not_a_semantic_field",))
    with pytest.raises(ValueError, match="non-blank path/reason"):
        compare_shadow([], [], approved_explanations={"*.source_raw_ref": " "})
