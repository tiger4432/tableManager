# -*- coding: utf-8 -*-
"""Independent verification of the trace fixture's seven invariants.

These deliberately re-derive each property FROM THE EMITTED ROWS rather than trusting
the asserts inside the generator. An invariant checked only by the code that produces
it is checked by its own opinion of itself: the two would fail together on the same
misunderstanding, and the fixture would go on looking correct while quietly no longer
exercising what it exists to exercise.

Every count below is recomputed here; none is copied from a commit message, the board,
or the spec.
"""

import os
import sys
from collections import defaultdict

import pytest

_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from trace_fixture import GeneratorConfig, generate_batch  # noqa: E402
from trace_fixture.emit import ORDER  # noqa: E402
from trace_fixture.frames import FRAMES, FrameGrid  # noqa: E402
from trace_fixture.world import (  # noqa: E402
    NEVER_EXISTED, PIPELINE_DROPPED, PRESENT_BUT_WRONG, SEP,
)

SMALL = dict(core_lots=4, slots_per_lot=25, grid=13, tape_wafers=80)


@pytest.fixture(scope="module")
def built():
    return generate_batch(GeneratorConfig(batch=1, **SMALL))


# --------------------------------------------------------------- invariant 1
def test_slot_and_wafer_lists_correspond_positionally(built):
    """A length mismatch here reattributes wafers to the wrong slots, silently."""
    rows = built.tables["lot_event"]
    assert rows, "no lot_event rows were produced at all"
    for r in rows:
        slots = r["slot_numbers"].split(SEP) if r["slot_numbers"] else []
        wafers = r["wafer_ids"].split(SEP) if r["wafer_ids"] else []
        assert len(slots) == len(wafers), (
            "%s/%s at %s: %d slots vs %d wafers"
            % (r["lot"], r["event_type"], r["event_time"], len(slots), len(wafers)))
        assert len(set(slots)) == len(slots), "duplicate slot in %r" % r["slot_numbers"]
        assert len(set(wafers)) == len(wafers), "duplicate wafer in %r" % r["wafer_ids"]


def test_lot_event_business_key_is_unique(built):
    """(lot, event_type, event_time) is the declared composite key -- a collision
    would silently merge two events into one row."""
    seen = set()
    for r in built.tables["lot_event"]:
        key = (r["lot"], r["event_type"], r["event_time"])
        assert key not in seen, "duplicate lot_event key %r" % (key,)
        seen.add(key)


def test_split_and_merge_rows_come_in_pairs(built):
    """The user's shape: one event, two rows, one naming the child and one the parent."""
    by_event = defaultdict(list)
    for r in built.tables["lot_event"]:
        if r["event_type"] in ("split", "merge"):
            by_event[(r["event_type"], r["event_time"])].append(r)
    assert by_event, "no split or merge events were produced"
    for (etype, when), rows in by_event.items():
        assert len(rows) == 2, "%s at %s produced %d rows, expected 2" % (etype, when, len(rows))
        parents = [r for r in rows if r["child_lot"]]
        children = [r for r in rows if r["parent_lot"]]
        assert len(parents) == 1 and len(children) == 1, (
            "%s at %s is not a parent/child pair" % (etype, when))
        assert not parents[0]["parent_lot"], "parent row must leave parent_lot blank"
        assert not children[0]["child_lot"], "child row must leave child_lot blank"


def test_absent_lineage_side_is_blank_not_a_placeholder(built):
    """A literal '-' would be a perfectly good graph identity and would mint one
    Lot('-') hub wired to every split and merge in the fixture."""
    for r in built.tables["lot_event"]:
        for col in ("parent_lot", "child_lot", "equipment"):
            assert r[col] != "-", "%s carries a '-' placeholder" % col


# --------------------------------------------------------------- invariant 2
def test_tape_slot_to_dt_slot_is_monotonic(built):
    """The constraint that makes inference #1 tractable at all.

    Re-derived from the emitted rows: group jobs by (equipment, instant), sort by the
    tape slot encoded in dt_job, and read each tape wafer's DT slot out of the
    position truth. An arbitrary permutation here would leave an algorithm that works
    on real data failing on the fixture for a reason that is not the algorithm's.
    """
    pos_at = {}
    for r in built.oracle["truth_wafer_position"]:
        pos_at.setdefault((r["wafer_id"], r["event_time"]), (r["lot"], r["slot"]))

    sessions = defaultdict(list)
    for job in built.jobs:
        sessions[(job["eqp"], job["when"])].append(job)

    assert sessions, "no DT sessions were produced"
    for key, jobs in sessions.items():
        ordered = sorted(jobs, key=lambda j: j["job"].rsplit("_", 1)[1])
        dt_slots = [j["dt_slot_true"] for j in ordered]
        assert dt_slots == sorted(dt_slots), (
            "session %r assigns DT slots %s, which is not monotonic in tape slot"
            % (key, dt_slots))
        assert len(set(dt_slots)) == len(dt_slots), (
            "session %r reuses a DT slot" % (key,))


# --------------------------------------------------------------- invariant 3
def test_anchor_density_is_banded(built):
    """High (>=50%), mid (10-30%) and none (0%) must all be present.

    Without a 'none' band every job resolves and the fixture never produces a case
    that genuinely cannot be answered; without a 'high' band nothing resolves and the
    inference looks impossible rather than tractable.
    """
    per_job = defaultdict(lambda: [0, 0])
    for r in built.tables["dt_log"]:
        cell = per_job[r["dt_job"]]
        cell[1] += 1
        if r["core_wafer"]:
            cell[0] += 1

    bands = {"high": 0, "mid": 0, "none": 0, "other": 0}
    for job, (anchored, total) in per_job.items():
        frac = anchored / float(total)
        eps = 1.0 / total
        if frac == 0.0:
            bands["none"] += 1
        elif frac >= 0.50 - eps:
            bands["high"] += 1
        elif 0.10 - eps <= frac <= 0.30 + eps:
            bands["mid"] += 1
        else:
            bands["other"] += 1
    assert bands["other"] == 0, "jobs outside every declared band: %d" % bands["other"]
    for name in ("high", "mid", "none"):
        assert bands[name] > 0, "band %r is empty -- %r" % (name, bands)


def test_every_dt_row_identifies_its_core_somehow(built):
    """The user was explicit: one of core_wafer or (core_lot, core_slot) is always there."""
    for r in built.tables["dt_log"]:
        assert r["core_wafer"] or (r["core_lot"] and r["core_slot"]), (
            "dt_log row %s (%s,%s) names no core source at all"
            % (r["dt_job"], r["dt_x"], r["dt_y"]))


# --------------------------------------------------------------- invariant 4
def test_coordinate_spaces_carry_independent_frames(built):
    """core_x,y and dt_x,y must not be the same unknown."""
    pairs = defaultdict(dict)
    for r in built.oracle["truth_frame"]:
        if r["space"] in ("core", "dt"):
            pairs[r["scope"]][r["space"]] = r["true_frame"]
    assert pairs, "no equipment/product frame truth was recorded"
    differing = [s for s, d in pairs.items() if d.get("core") != d.get("dt")]
    assert differing, (
        "every scope drew the SAME frame for core and dt -- they are being coupled, "
        "which collapses 64 candidates to 8 and hides the real ambiguity: %r" % dict(pairs))


def test_dt_log_key_does_not_collide(built):
    """(dt_job, dt_x, dt_y) is the declared key. The spec draft's (dt_job, core_x,
    core_y) collides whenever one job draws the same core cell from two wafers."""
    seen = set()
    draft_seen = set()
    draft_collisions = 0
    for r in built.tables["dt_log"]:
        key = (r["dt_job"], r["dt_x"], r["dt_y"])
        assert key not in seen, "dt_log key collision at %r" % (key,)
        seen.add(key)
        draft = (r["dt_job"], r["core_x"], r["core_y"])
        if draft in draft_seen:
            draft_collisions += 1
        draft_seen.add(draft)
    # Not an assertion about the fixture, a demonstration of why the key was changed.
    print("draft key (dt_job, core_x, core_y) would have collided %d times"
          % draft_collisions)


# --------------------------------------------------------------- invariant 5
def test_symmetric_and_asymmetric_jobs_both_exist(built):
    """Recomputed from the RECORDED coordinates.

    Stabiliser size is conjugation-invariant, so it can be measured from the recorded
    set without knowing which frame it was recorded in -- which is the point: the
    observer is in exactly that position.
    """
    grid = FrameGrid(SMALL["grid"], SMALL["grid"])
    cells = defaultdict(set)
    for r in built.tables["dt_log"]:
        cells[r["dt_job"]].add((r["dt_x"], r["dt_y"]))

    sym = [j for j, s in cells.items() if len(grid.invariant_frames(s)) > 1]
    asym = [j for j, s in cells.items() if len(grid.invariant_frames(s)) == 1]
    assert sym, "no job has a symmetric subset -- every frame would be determinable"
    assert asym, "no job has an asymmetric subset -- no frame would ever be determinable"
    ratio = len(sym) / float(len(cells))
    assert 0.25 <= ratio <= 0.55, (
        "symmetric share is %.2f, far from the intended 0.40 (sym=%d asym=%d)"
        % (ratio, len(sym), len(asym)))
    for job in sym:
        assert len(grid.invariant_frames(cells[job])) == len(FRAMES), (
            "job %s is partially symmetric; the fixture only models fully "
            "undeterminable and fully determinable" % job)


def test_ambiguous_cases_are_recorded_as_unresolved(built):
    """Every truth_ambiguous row must state that the expected answer is 'unknown'."""
    amb = built.oracle["truth_ambiguous"]
    assert amb, "no ambiguous cases were recorded -- honesty could not be scored"
    for r in amb:
        assert r["expected_answer"] == "미상", r
        assert r["why"], "an ambiguous case with no stated reason is not reviewable"


def test_every_symmetric_job_is_in_the_ambiguous_oracle(built):
    """A symmetric job absent from truth_ambiguous would be scored against a frame
    the data cannot support -- the scorer would then punish the honest answer."""
    grid = FrameGrid(SMALL["grid"], SMALL["grid"])
    cells = defaultdict(set)
    for r in built.tables["dt_log"]:
        cells[r["dt_job"]].add((r["dt_x"], r["dt_y"]))
    sym = {j for j, s in cells.items() if len(grid.invariant_frames(s)) > 1}
    recorded = {r["subject"] for r in built.oracle["truth_ambiguous"]
                if r["question"] == "dt_frame"}
    missing = sym - recorded
    assert not missing, "symmetric jobs missing from truth_ambiguous: %s" % sorted(missing)[:5]


# --------------------------------------------------------------- invariant 6
def test_missing_comes_in_two_kinds_indistinguishable_in_the_data(built):
    kinds = defaultdict(int)
    for r in built.oracle["truth_missing"]:
        kinds[r["kind"]] += 1
    assert kinds[NEVER_EXISTED] > 0, "no 'never existed' cases -- no real work to do"
    assert kinds[PIPELINE_DROPPED] > 0, "no 'pipeline dropped' cases -- no bug to find"

    # The data must not leak the distinction. Both kinds land on core_wafer as an
    # empty string; if one used a sentinel the classification would be trivial.
    dropped = {r["business_key_val"] for r in built.oracle["truth_missing"]
               if r["kind"] == PIPELINE_DROPPED and r["column"] == "core_wafer"}
    never = {r["business_key_val"] for r in built.oracle["truth_missing"]
             if r["kind"] == NEVER_EXISTED and r["column"] == "core_wafer"}
    assert dropped and never
    for r in built.tables["dt_log"]:
        key = "%s_%s_%s" % (r["dt_job"], r["dt_x"], r["dt_y"])
        if key in dropped or key in never:
            assert r["core_wafer"] == "", (
                "a deliberately-missing core_wafer is not blank: %r" % r["core_wafer"])


# --------------------------------------------------------------- invariant 7
def test_ten_percent_of_dt_lot_is_present_but_wrong(built):
    """Worse than absent: a wrong value makes a join succeed quietly."""
    wrong_jobs = {r["business_key_val"] for r in built.oracle["truth_missing"]
                  if r["kind"] == PRESENT_BUT_WRONG and r["column"] == "dt_lot"}
    absent_jobs = {r["business_key_val"] for r in built.oracle["truth_missing"]
                   if r["kind"] in (NEVER_EXISTED, PIPELINE_DROPPED)
                   and r["column"] == "dt_lot"}
    total = len(built.jobs)
    assert wrong_jobs, "no wrong dt_lot values -- the quiet-join failure is not modelled"
    assert 0.03 <= len(wrong_jobs) / float(total) <= 0.20, (
        "wrong-value share is %.3f, intended ~0.10" % (len(wrong_jobs) / float(total)))
    assert 0.30 <= len(absent_jobs) / float(total) <= 0.50, (
        "absent share is %.3f, intended ~0.40" % (len(absent_jobs) / float(total)))

    # And the wrong value must actually be wrong, and must look ordinary.
    recorded = {r["dt_job"]: r["dt_lot"] for r in built.tables["dt_log"]}
    truth = {j["job"]: j["dt_lot_true"] for j in built.jobs}
    for job in wrong_jobs:
        assert recorded[job], "a 'wrong' value is actually blank for %s" % job
        assert recorded[job] != truth[job], "the 'wrong' value equals the truth for %s" % job


# ------------------------------------------------------- ingestion contract
def test_emitted_columns_satisfy_the_ingestion_contract(built):
    """Header must be a subset of display_columns, and must carry either the business
    key or every composite source -- otherwise std_parser rejects the file to err/."""
    import json
    cfg_path = os.path.join(_SERVER, "config", "table_config.json")
    with open(cfg_path, encoding="utf-8") as fh:
        tc = json.load(fh)

    for table, order in ORDER.items():
        assert table in tc, "%s is emitted but not declared in table_config" % table
        info = tc[table]
        loadable = set(info.get("display_columns") or info.get("column_types", {}))
        unknown = [c for c in order if c not in loadable]
        assert not unknown, "%s emits columns not loadable: %s" % (table, unknown)

        bk = info.get("business_key")
        src = info.get("composite_key_source") or []
        assert (bk in order) or (src and all(c in order for c in src)), (
            "%s emits neither business_key %r nor all composite sources %s"
            % (table, bk, src))

        rows = built.tables.get(table) or []
        for r in rows[:50]:
            for c in src:
                assert str(r.get(c, "")).strip() != "", (
                    "%s row has a blank composite key part %r -- std_parser would skip "
                    "it as keyless and crud would mint an orphan on every re-ingest"
                    % (table, c))


def test_some_lot_attributions_are_genuinely_unresolvable(built):
    """At least one DT session must lose its track-in event.

    Without one, every job's lot is recoverable and the fixture never produces the case
    where the honest answer is 'unknown' -- which is half of what it exists to test.
    This was a 20% coin flip in the first version and came up zero on the first seed:
    the fixture claimed cases it did not have.
    """
    amb = [r for r in built.oracle["truth_ambiguous"]
           if r["question"] == "dt_lot"]
    assert amb, "no unresolvable lot attribution -- inference #1 always succeeds"

    tracked = {r["lot"] for r in built.tables["lot_event"]
               if r["event_type"] == "track_in"}
    dt_lots = {j["dt_lot_true"] for j in built.jobs}
    assert tracked, "no track_in events at all -- nothing would ever resolve"
    assert dt_lots - tracked, "every DT lot has a track_in; no unresolvable case exists"


def test_lineage_walk_is_actually_required(built):
    """Some dies must have MOVED between core measurement and DT.

    If every wafer sat still, (core_lot, core_slot) recorded at DT would address the
    core map directly and the whole split/merge apparatus would be decoration -- a
    plain join would score 100% and prove nothing.
    """
    rows = built.oracle["truth_die_lineage"]
    assert rows, "no die lineage was recorded"
    moved = [r for r in rows
             if (r["core_lot"], r["core_slot"]) != (r["core_lot_at_dt"], r["core_slot_at_dt"])]
    assert moved, (
        "no die changed (lot, slot) between core measurement and DT -- a direct join "
        "would answer the whole scenario and the lot_event walk would never be needed")


def test_bonding_time_dt_position_differs_from_dt_time(built):
    """The crux: bonding_log's (dt_lot, dt_slot) must not always equal dt_log's.

    When they agree everywhere, joining the two tables works and the scenario's central
    claim -- that the join silently matches the wrong wafer -- is untestable.
    """
    at_dt = {j["job"]: (j["dt_lot_true"], j["dt_slot_true"]) for j in built.jobs}
    tape_job = {}
    for j in built.jobs:
        tape_job[j["tape"]] = j["job"]
    differing = 0
    seen = set()
    for r in built.tables["bonding_log"]:
        key = (r["dt_lot"], r["dt_slot"])
        if key in seen:
            continue
        seen.add(key)
        if key not in set(at_dt.values()):
            differing += 1
    assert differing, (
        "every bonding-time (dt_lot, dt_slot) still matches a DT-time one -- the DT "
        "lots never moved between DT and bonding, so the hard case is absent")


def test_scoring_counts_an_honest_unresolved_as_correct():
    """The rule the whole oracle exists to make possible."""
    from trace_fixture import scoring

    oracle = {
        "truth_frame": [{"space": "dt", "scope": "E|P", "true_frame": "rot90_front",
                         "declared_frame": "rot0_front", "declaration_is_honest": "N"}],
        "truth_ambiguous": [{"case": "coordinate_frame", "subject": "E|P",
                             "question": "dt_frame", "expected_answer": "미상",
                             "why": "symmetric", "candidates": ""}],
    }
    honest = scoring.score_frames(oracle, [{"space": "dt", "scope": "E|P", "frame": "미상"}])
    assert honest["correct"] == 1 and honest["false_confidence"] == 0

    # A confident answer that happens to match the truth is still false confidence:
    # the data could not support it, so it was a guess that got lucky.
    lucky = scoring.score_frames(
        oracle, [{"space": "dt", "scope": "E|P", "frame": "rot90_front"}])
    assert lucky["correct"] == 0 and lucky["false_confidence"] == 1
