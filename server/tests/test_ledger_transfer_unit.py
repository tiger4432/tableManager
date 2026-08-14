# -*- coding: utf-8 -*-
"""The THIRD grammar - `dt_log` -> `transferred`. Everything provable without a database.

WHAT THIS FILE IS ACTUALLY GUARDING
------------------------------------
Two of these tests would pass on a translator that quietly did the wrong thing, so they
are written from the failing side:

  * `test_the_destination_is_never_the_rows_own_dt_lot` feeds a row whose recorded
    `dt_lot` DISAGREES with the confirmed one and asserts the atom takes the CONFIRMED
    value. A fixture where the two agree decides nothing - both rules give the same answer.
  * `test_container_object_carries_exactly_three_keys` pins the shape the position walk
    joins on. An extra field inside `to` breaks every continuity join in the system
    SILENTLY, because the join is a comparison of the whole object.
"""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                            # noqa: E402
from ledger import config as ledger_config             # noqa: E402
from ledger import gate                                # noqa: E402
from ledger.transfer_translator import (               # noqa: E402
    TransferMolecule, TransferTranslator)

SOURCE = "dt_log"
EVENT_TIME = "2026-05-11 00:00:00"


@pytest.fixture(autouse=True)
def _clean_counters():
    gate.reset_counters()
    yield
    gate.reset_counters()


# ------------------------------------------------------------------------- declarations
def transfer_cfg(**overrides):
    cfg = {
        "kind": "transfer",
        "occurred_at_column": "event_time",
        "occurred_at_format": "%Y-%m-%dT%H:%M:%S",
        "occurred_at_timezone": "Asia/Seoul",
        "subject_types": ["Wafer"],
        "register_entity_types": ["Wafer"],
        "group": {"column": "dt_job", "row_order_column": "row_id"},
        "container": {"relation": "dt_inventory", "key_column": "dt_job",
                      "lot_column": "dt_lot", "slot_column": "dt_slot"},
        "columns": {"row_identity": "business_key_val", "group_key": "dt_job",
                    "wafer": "core_wafer", "recorded_lot": "dt_lot",
                    "recorded_slot": "dt_slot"},
    }
    cfg.update(overrides)
    return cfg


def full_cfg(**overrides):
    return {"version": 1, "sources": {SOURCE: transfer_cfg(**overrides)}}


def row(wafer="WF.010120", job="DT-EQP-01_20260511T0000_T01", **overrides):
    base = {"row_identity": f"{job}_1_3", "group_key": job, "wafer": wafer,
            "event_time": EVENT_TIME, "recorded_lot": "DT-2601-001",
            "recorded_slot": "01"}
    base.update(overrides)
    return base


def translate_group(rows, cfg=None, containers=None, source=SOURCE):
    """One job-run through the DRIVER's control flow. `(atoms, report)`.

    🔴 Shaped like `backfill._run_transfer`'s loop on purpose (rulings R-H-bis 1 and 3):
    the driver owns `gate.building_molecule` and screens inside it, so a helper that opened
    no scope would exercise a control flow production does not have - `_build` asserts the
    scope and a gate refusal would come back as a value instead of unwinding.
    """
    cfg = cfg or full_cfg()
    source_cfg = ledger_config.source_config(cfg, source)
    translator = TransferTranslator(
        source, source_cfg, ledger_config.translator_version(cfg, source),
        ledger_config.declared_derivations(cfg, source))
    molecule = TransferMolecule(source, rows[0]["group_key"], rows)
    try:
        with gate.building_molecule(source):
            atoms, report = translator.translate(molecule, containers or {})
            if atoms is None:
                return None, report, translator
            kept, screen = gate.screen_molecule(
                source, atoms, ledger_config.declared_derivations(cfg, source),
                ledger_config.declared_subject_types(cfg, source),
                molecule_ref=molecule.ref, source_rows=len(rows))
    except gate.MoleculeRefused as refusal:
        return None, {"refused": True, "reason": refusal.reason,
                      "violations": [refusal.detail]}, translator
    return kept, screen, translator


def moved(atoms):
    return [a for a in atoms if a.predicate == "transferred"]


# ------------------------------------------------------------------- the atom's shape
def test_a_job_run_becomes_one_atom_per_source_wafer_carrying_qty():
    """The declared unit, with the measured fact that shapes it.

    "One atom per job-run" and "subject = Wafer" meet at a fact: one DT job is fed by
    SEVERAL core wafers (measured on `assy_manager`: of 396 jobs, 83 are fed by one, 83 by
    two, 8 by eighty-eight). A single atom whose subject was several wafers is not
    expressible, so the fold is per (job-run, wafer) and a job fed by ONE wafer utters
    exactly one atom - the declared shape, unchanged.
    """
    rows = [row(wafer="WF.010120", row_identity="j_1_3"),
            row(wafer="WF.010120", row_identity="j_1_4"),
            row(wafer="WF.010121", row_identity="j_1_5")]
    atoms, report, _tr = translate_group(rows)
    assert report["refused"] is False
    events = moved(atoms)
    assert len(events) == 2
    by_wafer = {a.subject_keys["wafer"]: a for a in events}
    assert by_wafer["WF.010120"].object_payload["qty"] == 2
    assert by_wafer["WF.010121"].object_payload["qty"] == 1
    assert all(a.subject_type == "Wafer" for a in events)
    assert all(a.object_kind == "value" for a in events)
    # Every wafer the job-run names is registered, once.
    registers = [a for a in atoms if a.predicate == "register"]
    assert {a.subject_keys["wafer"] for a in registers} == {"WF.010120", "WF.010121"}
    assert len(registers) == 2


def test_the_world_time_is_the_rows_event_time_not_arrival():
    atoms, _report, _tr = translate_group([row()])
    atom = moved(atoms)[0]
    assert atom.occurred_at.tzinfo is not None
    assert atom.occurred_at.strftime("%Y-%m-%dT%H:%M:%S") == "2026-05-11T00:00:00"
    # The declared zone is Asia/Seoul, so the stored instant is 9 hours before midnight
    # UTC. Asserted as an INSTANT rather than as wall clock: a translator that dropped the
    # zone would still print the same wall clock.
    assert atom.occurred_at.utcoffset().total_seconds() == 9 * 3600


@pytest.mark.parametrize("spelling", ["2026-05-11 00:00:00", "2026-05-11T00:00:00",
                                      "2026-08-09T00:00:00Z", "2026-08-10T00:07:00+09:00"])
def test_every_event_time_spelling_this_box_holds_is_read(spelling):
    """MEASURED: `dt_log` on `assy_manager` holds three spellings of `event_time`.

    A translator that read only the declared one would refuse 26,239 of 34,939 rows for
    `missing_occurred_at` and the refusal would point at the config instead of at the fact
    that the column is text with mixed transports.
    """
    atoms, report, _tr = translate_group([row(event_time=spelling)])
    assert report["refused"] is False, report
    assert atoms


# --------------------------------------------------- the destination, and its honesty
def test_the_destination_is_never_the_rows_own_dt_lot():
    """🔴 THE DECIDING FIXTURE: the row's recorded lot DISAGREES with the confirmed one.

    A fixture where the two agree cannot tell the two rules apart - both produce the same
    `to`. Here the source row says `DT-2601-001` and `dt_inventory` says `DT-2601-999`, and
    the atom must take the CONFIRMED value, because the row's column is this table's
    declared inference target ("10% PRESENT BUT WRONG") and a wrong one makes a join
    succeed quietly.
    """
    containers = {"DT-EQP-01_20260511T0000_T01": {"lot": "DT-2601-999", "slot": "07"}}
    atoms, _report, tr = translate_group([row(recorded_lot="DT-2601-001",
                                              recorded_slot="01")],
                                         containers=containers)
    atom = moved(atoms)[0]
    assert atom.object_payload["to"] == {"type": "dt_slot",
                                         "keys": {"dt_lot": "DT-2601-999",
                                                  "dt_slot": "07"},
                                         "position": None}
    assert atom.derivation == ledger_config.DERIVATION_TRANSFER_CONFIRMED
    assert atom.source_translator_ver.endswith("#job_run_to_confirmed_container")
    # And the source's own reading is PRESERVED beside it, never instead of it.
    assert atom.object_payload["container_recorded"] == [{"dt_lot": "DT-2601-001",
                                                          "dt_slot": "01"}]
    assert (tr.confirmed_groups, tr.unconfirmed_groups) == (1, 0)


def test_an_unconfirmed_destination_is_the_job_itself_and_says_so():
    """The state this box is actually in: `dt_inventory` confirms ZERO jobs.

    The atom must not fall back to the row's dt_lot, and it must not be refused either -
    "wafer W put 3 dies into job J" is a true claim about a real movement. What it must do
    is name the ACQUISITION unit as itself so the missing link reads as missing.
    """
    atoms, _report, tr = translate_group([row()], containers={})
    atom = moved(atoms)[0]
    assert atom.object_payload["to"] == {
        "type": "dt_job",
        "keys": {"dt_job": "DT-EQP-01_20260511T0000_T01"},
        "position": None}
    assert atom.derivation == ledger_config.DERIVATION_TRANSFER_JOB
    assert (tr.confirmed_groups, tr.unconfirmed_groups) == (0, 1)
    # 🔴 The recorded pair is carried and is NOT identity - it is outside `to`.
    assert "recorded_lot" not in atom.object_payload["to"]
    assert atom.object_payload["container_recorded"] == [{"dt_lot": "DT-2601-001",
                                                          "dt_slot": "01"}]


def test_a_half_blank_confirmation_is_not_a_confirmation():
    """A `dt_inventory` row with a lot and no slot confirms nothing.

    Taking the lot alone would produce a container that is missing half its identity and
    would collide with every other slot of the same lot - the concatenated-identity
    failure, one level up.
    """
    containers = {"DT-EQP-01_20260511T0000_T01": {"lot": "DT-2601-999", "slot": ""}}
    atoms, _report, _tr = translate_group([row()], containers=containers)
    assert moved(atoms)[0].object_payload["to"]["type"] == "dt_job"


def test_container_object_carries_exactly_three_keys():
    """🔴 THE SHAPE THE POSITION WALK JOINS ON, pinned.

    `seed_syn_process_ledger.prove_position_walk` indexes on
    `json.dumps(payload["to"], sort_keys=True)` and the residual fold groups by
    `object_payload->'to'` - both compare the WHOLE object. One extra field inside a
    container makes every continuity join miss while every atom still looks well formed,
    which is the quietest possible way to break §2-bis's "chain of arbitrary length".
    """
    atoms, _report, _tr = translate_group([row()])
    payload = moved(atoms)[0].object_payload
    for side in ("from", "to"):
        assert set(payload[side]) == {"type", "keys", "position"}, side
    assert payload["from"] == {"type": "wafer_grid", "keys": {"wafer": "WF.010120"},
                               "position": None}


def test_disagreeing_recorded_pairs_are_all_carried():
    """A job-run whose rows disagree about the destination keeps BOTH readings.

    Measured: 4,617 of 4,618 (job, wafer) groups record exactly one pair and ONE records
    two. Collapsing a disagreement to a single value is how the disagreement stops being
    visible, and this source's whole difficulty is that some of those values are wrong.
    """
    rows = [row(row_identity="a", recorded_slot="01"),
            row(row_identity="b", recorded_slot="02")]
    atoms, _report, _tr = translate_group(rows)
    assert moved(atoms)[0].object_payload["container_recorded"] == [
        {"dt_lot": "DT-2601-001", "dt_slot": "01"},
        {"dt_lot": "DT-2601-001", "dt_slot": "02"}]


# ------------------------------------------------------------ what refuses, what counts
def test_a_job_run_with_no_wafer_anywhere_is_refused():
    _atoms, report, _tr = translate_group([row(wafer=""), row(wafer=None,
                                                              row_identity="b")])
    assert report["refused"] is True
    assert report["reason"] == gate.REFUSE_NO_IDENTITY


def test_a_partly_anchored_job_run_lands_and_is_counted_incomplete():
    """The distinction that keeps evidence alive: incomplete is NOT refused.

    6,731 of 34,939 rows carry no `core_wafer`, and 80 job-runs mix anchored and unanchored
    rows. Refusing those 80 would destroy the true claims of the wafers that ARE named.
    """
    rows = [row(wafer="WF.010120", row_identity="a"),
            row(wafer="", row_identity="b")]
    cfg = full_cfg()
    source_cfg = ledger_config.source_config(cfg, SOURCE)
    translator = TransferTranslator(SOURCE, source_cfg,
                                    ledger_config.translator_version(cfg, SOURCE),
                                    ledger_config.declared_derivations(cfg, SOURCE))
    molecule = TransferMolecule(SOURCE, rows[0]["group_key"], rows)
    assert molecule.is_complete is False
    with gate.building_molecule(SOURCE):
        atoms, report = translator.translate(molecule, {})
    assert report["refused"] is False
    assert report["incomplete"] is True
    assert moved(atoms)[0].object_payload["qty"] == 1
    assert translator.unanchored_rows == 1


def test_a_blank_event_time_refuses_the_job_run():
    """8 of 396 job-runs on this box. Arrival time is never substituted."""
    _atoms, report, _tr = translate_group([row(event_time="")])
    assert report["refused"] is True
    assert report["reason"] == gate.REFUSE_MISSING_OCCURRED_AT


def test_two_world_times_in_one_job_run_refuse_it():
    """A job-run is ONE event. Measured 0 violations today, which is exactly when to add
    the check: folding two instants would be this translator choosing when history
    happened, and it would look like a successful translation."""
    rows = [row(row_identity="a", event_time="2026-05-11 00:00:00"),
            row(row_identity="b", event_time="2026-05-12 00:00:00")]
    _atoms, report, _tr = translate_group(rows)
    assert report["refused"] is True
    assert report["reason"] == gate.REFUSE_ATOMICITY


def test_a_refused_job_run_gives_back_its_register_memos():
    """The half-refusal one move later: a wafer memoised by a REFUSED molecule is
    registered nowhere, and the next molecule that mentions it emits no register either."""
    cfg = full_cfg()
    source_cfg = ledger_config.source_config(cfg, SOURCE)
    translator = TransferTranslator(SOURCE, source_cfg,
                                    ledger_config.translator_version(cfg, SOURCE),
                                    ledger_config.declared_derivations(cfg, SOURCE))
    good = TransferMolecule(SOURCE, "J1", [row(job="J1", group_key="J1")])
    with gate.building_molecule(SOURCE):
        translator.translate(good, {})
    assert translator.registered            # the wafer is memoised by a molecule that stood

    translator.registered.clear()
    bad = TransferMolecule(SOURCE, "J2", [row(job="J2", group_key="J2",
                                              event_time="not-a-time")])
    with gate.building_molecule(SOURCE):
        atoms, report = translator.translate(bad, {})
    assert atoms is None and report["refused"] is True
    assert translator.registered == set(), (
        "a refused job-run left a register memo behind, so the wafer would never be "
        "registered by anybody")


def test_build_outside_the_gate_scope_raises_rather_than_counting():
    """R-H-bis 3's second net. Outside the scope a `refuse` only COUNTS and execution
    carries on past the check that was supposed to stop it."""
    cfg = full_cfg()
    source_cfg = ledger_config.source_config(cfg, SOURCE)
    translator = TransferTranslator(SOURCE, source_cfg, "v", frozenset())
    with pytest.raises(RuntimeError, match="building_molecule"):
        translator.translate(TransferMolecule(SOURCE, "J", [row()]), {})


# ------------------------------------------------------------------ provenance and refs
def test_raw_ref_is_a_predicate_that_selects_exactly_this_atoms_rows():
    """Atomicity check ④, at bounded size.

    A job-run group is up to 150 rows; enumerating their business keys would put ~6 KB of
    ids in every atom. The ref names the SET by the predicate that defines it, in the
    SOURCE's own column names, sorted so the value is byte-identical on every run - which
    is what lets `uq_ledger_atom` recognise a re-translation.
    """
    atoms, _report, _tr = translate_group([row(row_identity="a"),
                                           row(row_identity="b")])
    atom = moved(atoms)[0]
    assert atom.source_raw_ref.startswith("dt_log:")
    selector = json.loads(atom.source_raw_ref.split(":", 1)[1])
    assert selector == {"dt_job": "DT-EQP-01_20260511T0000_T01",
                        "core_wafer": "WF.010120"}
    assert atom.source_who == "dt_log"


def test_no_atom_of_this_source_is_marked_synthetic():
    """🔴 `dt_log` IS REAL DATA. The ledger has no UPDATE, so a `synthetic` flag written by
    reflex is a permanent mark on real observations - correctable only by re-translating.
    """
    atoms, _report, _tr = translate_group([row()])
    assert all("synthetic" not in (a.object_payload or {}) for a in atoms)


# ----------------------------------------------------------------- the declaration itself
def test_the_live_declaration_validates_and_declares_this_source():
    cfg = ledger_config.load()
    assert "dt_log" in cfg["sources"]
    assert ledger_config.source_kind(cfg, "dt_log") == ledger_config.SOURCE_KIND_TRANSFER
    assert ledger_config.declared_derivations(cfg, "dt_log") == frozenset({
        "first_sight", "job_run_to_job", "job_run_to_confirmed_container"})
    assert ledger_config.declared_subject_types(cfg, "dt_log") == frozenset({"Wafer"})


def test_a_transfer_source_that_declares_no_container_cannot_emit_the_confirmed_rule():
    cfg = full_cfg(container={"relation": None})
    ledger_config.validate(cfg)
    assert ledger_config.declared_derivations(cfg, SOURCE) == frozenset(
        {"first_sight", "job_run_to_job"})


@pytest.mark.parametrize("mutation,fragment", [
    ({"group": {"row_order_column": "row_id"}}, "group must declare the column"),
    ({"group": {"column": "dt_job"}}, "row_order_column"),
    ({"container": "dt_inventory"}, "container must declare"),
    ({"container": {"relation": "dt_inventory", "key_column": "dt_job"}}, "lot_column"),
    ({"vocabulary": {"split": {}}}, "LINEAGE declaration"),
])
def test_a_transfer_declaration_that_would_have_to_be_guessed_at_is_refused(mutation,
                                                                           fragment):
    cfg = full_cfg(**mutation)
    with pytest.raises(ledger_config.LedgerConfigError, match=fragment):
        ledger_config.validate(cfg)


def test_a_column_mapping_nothing_reads_is_refused():
    cfg = full_cfg()
    cfg["sources"][SOURCE]["columns"]["core_x"] = "core_x"
    with pytest.raises(ledger_config.LedgerConfigError, match="core_x"):
        ledger_config.validate(cfg)


def test_the_group_column_may_not_be_spelled_twice_differently():
    cfg = full_cfg()
    cfg["sources"][SOURCE]["columns"]["group_key"] = "dt_eqp"
    with pytest.raises(ledger_config.LedgerConfigError, match="group.column"):
        ledger_config.validate(cfg)


# --------------------------------------------------------------------- the batch boundary
def test_the_page_cut_never_splits_a_job_run():
    """A group that the page may have cut is DROPPED, not processed.

    The rule shared with the lineage driver, over a different column. A batch boundary
    inside a job-run would fold a FRAGMENT of the dies into `qty`, and a wrong count is the
    one defect that looks exactly like a right one.
    """
    rows = [{"group_key": "J1"}, {"group_key": "J1"}, {"group_key": "J2"}]
    kept, dropped = backfill._cut_on_group_boundary(rows, 3, key="group_key")
    assert [r["group_key"] for r in kept] == ["J1", "J1"]
    assert dropped == "J2"
    # A short page reached the end of the source: nothing is at risk, nothing is dropped.
    kept, dropped = backfill._cut_on_group_boundary(rows, 10, key="group_key")
    assert len(kept) == 3 and dropped is None


def test_a_group_bigger_than_a_page_leaves_nothing_to_process():
    """The escape hatch's precondition. When every row of a full page is one group the cut
    returns EMPTY, which is the signal the driver uses to fetch that group whole."""
    rows = [{"group_key": "J1"} for _ in range(3)]
    kept, dropped = backfill._cut_on_group_boundary(rows, 3, key="group_key")
    assert kept == [] and dropped == "J1"


def test_the_lineage_cut_is_unchanged_by_the_new_parameter():
    rows = [{"event_time": "t1"}, {"event_time": "t2"}]
    kept, dropped = backfill._cut_on_group_boundary(rows, 2)
    assert [r["event_time"] for r in kept] == ["t1"]
    assert dropped == "t2"


# ------------------------------------------------------- the dropped group comes BACK
class _FakePage:
    """A source table with a page limit, so the drop-and-resume path can be walked.

    🔴 THIS IS THE ONLY TEST IN THE PACKAGE THAT MAKES THE PAGE LOOP DROP A GROUP.
    `lot_event` is 43 rows on every box this has ever run on, so `dropped` was always
    `None` and the resume path was unreachable - which is why a cursor that advanced PAST
    the dropped group survived until a 34,939-row source ran the same loop.
    """

    def __init__(self, groups, limit):
        self.rows = [{"group_key": g, "row_identity": f"{g}-{i}"}
                     for g, n in groups for i in range(n)]
        self.limit = limit
        self.pages = 0

    def page(self, after):
        self.pages += 1
        rows = [r for r in self.rows if after is None or r["group_key"] > after]
        return rows[:self.limit]

    def group(self, key):
        return [r for r in self.rows if r["group_key"] == key]


def _walk(source, max_pages=20):
    """🔴 Drives `backfill.walk_group_pages` ITSELF, not a copy of it.

    An earlier draft of this test reimplemented the loop, which would have gone green on a
    driver that had regressed - the shape this project has already paid for twice ("a
    snippet reproduced out of context is not the behaviour"). The fetch halves are fakes;
    every rule under test is the production function's.
    """
    seen = []
    pages = backfill.walk_group_pages(source.page, source.group, "group_key", None,
                                      source.limit)
    for complete, _after, _last in pages:
        seen.extend(complete)
        if len(seen) > max_pages * source.limit:      # a runaway guard, never a page count
            raise AssertionError("walk_group_pages did not terminate")
    return seen


def test_a_group_dropped_at_a_page_boundary_is_read_on_the_next_page():
    """The defect this round measured: 17 job-runs and 1,862 rows silently gone.

    The cursor used to advance to the DROPPED group's key while the fetch is `> cursor`,
    so the group that was set aside *because it might be cut* was then skipped entirely.
    Both halves are asserted - every row arrives, and each arrives exactly once - because
    a resume that re-read a group would pass a completeness check while doubling `qty`.
    """
    source = _FakePage([("J1", 2), ("J2", 3), ("J3", 2), ("J4", 1)], limit=4)
    seen = _walk(source)
    assert [r["row_identity"] for r in seen] == [r["row_identity"] for r in source.rows]
    assert len(seen) == len(set(r["row_identity"] for r in seen)) == 8


def test_a_group_larger_than_a_page_is_read_whole_and_the_walk_continues():
    source = _FakePage([("J1", 6), ("J2", 1)], limit=4)
    seen = _walk(source)
    assert sorted(r["row_identity"] for r in seen) == sorted(
        r["row_identity"] for r in source.rows)
