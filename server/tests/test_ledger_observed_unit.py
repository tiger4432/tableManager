# -*- coding: utf-8 -*-
"""Ruling R-2026-08-14-D + E - the `observed` word, its translator, and the walk it must
stay out of. Everything provable without a database.

WHY THE WALK TESTS LIVE BESIDE THE TRANSLATOR TESTS
-----------------------------------------------------
Addendum ① of R-2026-08-14-D is not a separate feature, it is a CONDITION on this one:
translating 102,177 findings into the ledger kills the trace screen unless the walk is
already refusing to fetch them. The two therefore land together and are asserted together
- a file that tested only the translation could go green on the change that breaks the
screen.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config as ledger_config          # noqa: E402
from ledger import gate, vocabulary                 # noqa: E402
from ledger.observation_translator import (         # noqa: E402
    ObservationMolecule, ObservationTranslator)

OBSERVED_AT = datetime(2026, 8, 13, 8, 32, tzinfo=timezone.utc)


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


def finding_row(**overrides):
    row = {"row_identity": "019ffd76-2377-753c-9762-1067d02f964d",
           "wafer": "SYN-BW-002-13", "run_key": "sat|SYN-BW-002-13|8|12|4|…",
           "die_x": 8.0, "die_y": 12.0, "die_gate": 4.0,
           "inchip_x": 17556.75, "inchip_y": 3068.5,
           "extent_x": 5.593, "extent_y": 1.974, "unit": "um",
           "__watermark__": [OBSERVED_AT, "019ffd76-2377-753c-9762-1067d02f964d"]}
    row.update(overrides)
    return row


def runs_for(row, **overrides):
    run = {"occurred_at": OBSERVED_AT, "method": "sat"}
    run.update(overrides)
    return {row["run_key"]: run}


def translate_one(row, cfg=None, runs=None, source="void_obs", classes=()):
    """One finding row through the driver's control flow. `(atoms, report)`.

    🔴 SHAPED LIKE `backfill._run_observation`'s loop on purpose: the driver opens
    `gate.building_molecule` and screens INSIDE it (rulings R-H-bis 1 and 3), so a helper
    that opened no scope would exercise a control flow production does not have - `_build`
    would refuse to run at all and a gate refusal would come back as a value instead of
    unwinding.
    """
    cfg = cfg or full_cfg()
    source_cfg = ledger_config.source_config(cfg, source)
    translator = ObservationTranslator(
        source, source_cfg, ledger_config.translator_version(cfg, source),
        ledger_config.declared_derivations(cfg, source), declared_classes=classes)
    molecule = ObservationMolecule(source, row)
    runs = runs_for(row) if runs is None else runs
    try:
        with gate.building_molecule(source):
            atoms, report = translator.translate(molecule, runs)
            if atoms is None:
                return None, report
            kept, screen = gate.screen_molecule(
                source, atoms, ledger_config.declared_derivations(cfg, source),
                ledger_config.declared_subject_types(cfg, source),
                molecule_ref=molecule.ref, source_rows=1)
    except gate.MoleculeRefused as refusal:
        return None, {"refused": True, "reason": refusal.reason,
                      "violations": [refusal.detail]}
    return kept, screen


def observed_atom(atoms):
    return next(a for a in atoms if a.predicate == "observed")


# ------------------------------------------------------------------- the atom's shape
def test_a_finding_row_becomes_one_observed_atom_about_the_wafer():
    """§6-bis's shape, end to end: subject = Wafer, everything else in the payload.

    The die coordinates are in the PAYLOAD rather than in the subject because `Die` is a
    COMPOSED entity with no registration - and the consequence is the reason: every chip's
    findings fold under one substrate, so "이 웨이퍼의 보이드" is one query rather than a
    scan for keys that look alike.
    """
    atoms, report = translate_one(finding_row())
    assert report["refused"] is False
    atom = observed_atom(atoms)
    assert atom.subject_type == "Wafer"
    assert atom.subject_keys == {"wafer": "SYN-BW-002-13"}
    assert atom.object_kind == "value"
    assert atom.object_payload["finding_kind"] == "void"
    assert atom.object_payload["method"] == "sat"
    assert atom.object_payload["die"] == {"x": 8.0, "y": 12.0, "gate": 4.0}
    assert atom.object_payload["inchip"] == {"x": 17556.75, "y": 3068.5}
    assert atom.object_payload["extent"] == {"x": 5.593, "y": 1.974}
    assert atom.object_payload["unit"] == "um"
    # The world time is the SCAN's, not the row's arrival - there is no other time here.
    assert atom.occurred_at == OBSERVED_AT
    # Class 2 (observation) is not asserted by a flag: it is what an atom with no
    # inference derivation and no inferred payload flag resolves to by default.
    assert atom.source_translator_ver.endswith("#observation_row")
    assert atom.source_raw_ref.startswith("void_obs:[")


def test_the_run_reference_is_carried_so_the_denominator_survives_translation():
    """🔴 The red item of ruling R-2026-08-14-D, asserted from both sides.

    A rate needs a denominator, the denominator is the scan population, and an atom that
    did not name its run would leave the LEDGER unable to divide by anything - the exact
    position the source tables are already out of. So the payload carries it, AND the
    signature refuses an atom that does not.
    """
    atoms, _report = translate_one(finding_row())
    assert observed_atom(atoms).object_payload["run_uid"] == "sat|SYN-BW-002-13|8|12|4|…"

    violations = vocabulary.check_signature(
        "observed", "Wafer", "value", {"finding_kind": "void", "method": "sat"})
    assert violations, "an observation with no run_uid must not pass the signature"
    assert "run_uid" in violations[0]


def test_the_atom_says_it_is_synthetic_because_the_source_declared_it():
    """The source tables on this box are 100% generated, so the atoms are too.

    Readable FROM THE ATOM - `object_payload->>'synthetic'` - rather than from somebody's
    memory of which tables were seeded. Both directions, because a flag that is always
    present says nothing: remove the declaration and it disappears.
    """
    atoms, _ = translate_one(finding_row())
    assert observed_atom(atoms).object_payload["synthetic"] is True

    cfg = full_cfg(synthetic=False)
    atoms, _ = translate_one(finding_row(), cfg=cfg)
    assert "synthetic" not in observed_atom(atoms).object_payload


def test_a_class_the_kind_does_not_declare_is_refused_by_name():
    """§6-quater: the class set is per-kind, CLOSED and add-only.

    Both arms. A declared value lands in the payload as part of the same utterance; an
    undeclared one refuses the whole atom rather than putting an unreviewed word in the
    ledger - which is the check §6-quater asks for ("두 장비가 같은 class 이름을 쓰면
    프레임 검사 먼저"), and it only happens if a new spelling cannot arrive quietly.
    """
    cfg = full_cfg(finding_kind="delam")
    cfg["sources"]["void_obs"]["columns"]["class"] = "interface"

    atoms, _ = translate_one(finding_row(**{"class": "die-to-die"}), cfg=cfg,
                             classes=("die-to-die", "die-to-substrate"))
    assert observed_atom(atoms).object_payload["class"] == "die-to-die"

    atoms, report = translate_one(finding_row(**{"class": "voids-r-us"}), cfg=cfg,
                                  classes=("die-to-die", "die-to-substrate"))
    assert atoms is None
    assert report["reason"] == gate.REFUSE_UNDECLARED_VOCABULARY


@pytest.mark.parametrize("broken, reason", [
    ({"wafer": "  "}, gate.REFUSE_NO_IDENTITY),
    ({"run_key": ""}, gate.REFUSE_NO_IDENTITY),
])
def test_a_finding_with_no_subject_or_no_run_produces_nothing(broken, reason):
    """Neither is a tidy-up. A finding with no wafer is not a claim, and a finding with no
    run is a finding nothing can be divided by."""
    atoms, report = translate_one(finding_row(**broken))
    assert atoms is None
    assert report["reason"] == reason


def test_a_finding_whose_run_is_missing_is_refused_rather_than_timestamped_on_arrival():
    """🔴 Design §10 risk 1, one table over, and it is the silent one.

    `void_obs` has `created_at`, so substituting it would produce a perfectly well-formed
    atom for every orphaned finding and the ORDER OF HISTORY would be wrong with nothing
    complaining. The refusal is the feature.
    """
    row = finding_row()
    atoms, report = translate_one(row, runs={})
    assert atoms is None
    assert report["reason"] == gate.REFUSE_MISSING_OCCURRED_AT


def test_a_row_with_no_geometry_still_utters_that_something_was_found():
    """A blank extent is not a broken row. "There is a void here, I could not size it" is
    a true claim, and refusing it would delete evidence - so it lands and is COUNTED."""
    row = finding_row(die_x=None, die_y=None, die_gate=None, inchip_x=None,
                      inchip_y=None, extent_x=None, extent_y=None, unit=None)
    atoms, report = translate_one(row)
    assert report["refused"] is False
    payload = observed_atom(atoms).object_payload
    assert set(payload) == {"finding_kind", "method", "run_uid", "synthetic"}


def test_a_zero_coordinate_is_kept_because_zero_is_a_position():
    """⚠️ Truthiness would delete the origin column of every wafer map. `0.0` is a real
    die coordinate and a real extent; only `None` means the source said nothing."""
    atoms, _ = translate_one(finding_row(die_x=0.0, die_y=0.0, extent_x=0.0))
    payload = observed_atom(atoms).object_payload
    assert payload["die"]["x"] == 0.0 and payload["die"]["y"] == 0.0
    assert payload["extent"]["x"] == 0.0


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


def test_the_lineage_declaration_still_validates_unchanged():
    """A source that does not declare `kind` is a LINEAGE source, so every declaration
    written before this ruling means exactly what it meant. The default is a fact about
    history, not a preference."""
    cfg = ledger_config.load()
    assert ledger_config.source_kind(cfg, "lot_event") == "lineage"
    assert ledger_config.source_kind(cfg, "void_obs") == "observation"
    assert sorted(ledger_config.declared_derivations(cfg, "void_obs")) == [
        "first_sight", "observation_row"]


# ------------------------------------------------------------- the walk (R-2026-08-14-E)
def test_observed_is_not_in_the_walk_at_all():
    """🔴 ADDENDUM ① OF R-2026-08-14-D, and this is the assertion that protects the trace
    screen from the translation this same file tests.

    `claims_for_lots` drags back EVERY claim of EVERY lot the walk reaches. A wafer carries
    tens of thousands of observations, so `observed` joining that set would mean the trace
    screen dies on the day the defect translator first succeeds - which is today. The
    declaration says so, and both the derived fetch set and the constant readers use are
    asserted, because a reader could reach for either.
    """
    import ledger_trace

    assert vocabulary.PREDICATES["observed"]["traversable"] is None
    assert "observed" not in vocabulary.walk_predicates()
    assert "observed" not in vocabulary.traversable_predicates()
    assert "observed" not in ledger_trace.LINEAGE_PREDICATES


def test_the_walk_vocabulary_is_derived_and_still_says_what_it_said():
    """🔴 THE BEHAVIOUR-INVARIANCE PROOF for lifting the walk into the declaration.

    Before R-2026-08-14-E `ledger_trace.LINEAGE_PREDICATES` was the literal tuple below and
    the recursive CTE joined on the literal `'derived_from'`. Both now come from the
    vocabulary, so this asserts the derived answers are EXACTLY the historical ones - a
    refactor that quietly changed which atoms a trace fetches would change what the screen
    says while every other test stayed green.
    """
    import ledger_trace

    assert set(ledger_trace.LINEAGE_PREDICATES) == {
        "derived_from", "slot_map", "has_wafer", "register"}
    assert ledger_trace.traversal_predicate() == "derived_from"
    assert vocabulary.walk_direction("derived_from") == "subject_to_object"


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
