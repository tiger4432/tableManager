# -*- coding: utf-8 -*-
"""Thin CLI: run the baseline tracer and score it against the five oracle files.

All logic is in `server/trace_fixture`. This file loads rows, asks enrichment for its
candidates, runs the tracer and prints the four breakdowns.

Console output is ASCII plus CP949 only -- an em dash makes a Windows console line
vanish, so this uses a horizontal bar.
"""

import argparse
import os
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import paths                                        # noqa: E402
import enrichment_candidates as ec                   # noqa: E402
import enrichment_config                             # noqa: E402
from database import crud                            # noqa: E402
from database.database import SessionLocal           # noqa: E402
from trace_fixture import scoring                    # noqa: E402
from trace_fixture.baseline_trace import UNRESOLVED, BaselineTracer  # noqa: E402
from trace_fixture.emit import oracle_dir            # noqa: E402
from trace_fixture.frames import FrameGrid           # noqa: E402

RULE1 = "dt_job_lot_slot_attribution"
RULE2 = "eqp_product_frame_attribution"


def fetch(db, table, cols):
    from sqlalchemy import text
    q = 'SELECT %s FROM "%s"' % (", ".join('"%s"' % c for c in cols), table)
    return [dict(zip(cols, row)) for row in db.execute(text(q)).fetchall()]


def candidates_for(db, rule, keys, fields):
    """Ask enrichment for its answer per (key, field). `single` -> value, else 미상.

    This is `resolve_target_candidate`, the same predicate the auto-confirm sweep and
    the dry-run route use -- so the score measures the shipped behaviour, not a
    reimplementation of it.
    """
    out = {}
    for key_values in keys:
        row = {}
        for f in fields:
            res = ec.resolve_target_candidate(db, rule, key_values, f)
            row[f] = res.get("value") if res.get("status") == ec.STATUS_SINGLE else UNRESOLVED
            row[f + "__reason"] = res.get("reason")
        out[tuple(sorted(key_values.items()))] = row
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle", default=None)
    args = ap.parse_args(argv)
    od = args.oracle or oracle_dir(paths.DATA_ROOT)

    oracle = scoring.load_oracle(od)
    print("trace fixture scoring ― oracle at %s" % od)
    for k, v in sorted(oracle.items()):
        print("   %-24s %d rows" % (k, len(v)))

    db = SessionLocal()
    try:
        rules = {r["name"]: r for r in enrichment_config.load_enrichment_rules(
            known_tables=crud.TABLE_CONFIG)}
        r1, r2 = rules[RULE1], rules[RULE2]

        lot_events = fetch(db, "lot_event",
                           ["lot", "event_type", "event_time", "slot_numbers",
                            "wafer_ids", "parent_lot", "child_lot", "equipment"])
        dt_rows = fetch(db, "dt_log",
                        ["dt_job", "dt_eqp", "product", "dt_lot", "dt_slot",
                         "dt_x", "dt_y", "core_lot", "core_slot", "core_wafer",
                         "core_x", "core_y", "event_time"])
        bond_rows = fetch(db, "bonding_log",
                          ["bond_lot", "bond_slot", "bond_x", "bond_y",
                           "dt_lot", "dt_slot", "dt_x", "dt_y", "event_time"])
        print("\nrows read ― lot_event=%d dt_log=%d bonding_log=%d"
              % (len(lot_events), len(dt_rows), len(bond_rows)))

        jobs = sorted({r["dt_job"] for r in dt_rows})
        combos = sorted({(r["dt_eqp"], r["product"]) for r in dt_rows})

        # ---- ask enrichment ------------------------------------------------
        c1 = candidates_for(db, r1, [{"dt_job": j} for j in jobs],
                            ["dt_lot_confirmed", "dt_slot_confirmed"])
        c2 = candidates_for(db, r2,
                            [{"dt_eqp": e, "product": p} for e, p in combos],
                            ["core_frame", "dt_frame"])

        job_answers = {}
        for j in jobs:
            a = c1[(("dt_job", j),)]
            job_answers[j] = (a["dt_lot_confirmed"], a["dt_slot_confirmed"])
        frame_answers = {}
        for e, p in combos:
            a = c2[tuple(sorted({"dt_eqp": e, "product": p}.items()))]
            frame_answers[(e, p)] = {"core": a["core_frame"], "dt": a["dt_frame"]}

        # ---- per-job facts, RE-DERIVED from the rows ------------------------
        grid = FrameGrid(13, 13)
        per_job_cells = defaultdict(set)
        per_job_anchor = defaultdict(lambda: [0, 0])
        job_combo = {}
        recorded_lot = {}
        for r in dt_rows:
            per_job_cells[r["dt_job"]].add((r["dt_x"], r["dt_y"]))
            a = per_job_anchor[r["dt_job"]]
            a[1] += 1
            if (r["core_wafer"] or "").strip():
                a[0] += 1
            job_combo[r["dt_job"]] = (r["dt_eqp"], r["product"])
            recorded_lot.setdefault(r["dt_job"], (r["dt_lot"], r["dt_slot"]))

        band_of = {}
        for j, (anch, tot) in per_job_anchor.items():
            frac = anch / float(tot)
            eps = 1.0 / tot
            band_of[j] = ("none" if frac == 0 else
                          "high" if frac >= 0.50 - eps else
                          "mid" if frac <= 0.30 + eps else "other")
        symmetric_of = {j: len(grid.invariant_frames(c)) > 1
                        for j, c in per_job_cells.items()}

        # Truth for inference #1: the oracle overrides wherever it recorded a
        # deliberate absence or a deliberate wrong value; everywhere else the fixture
        # wrote the true value into dt_log by construction.
        truth_job = {}
        for j in jobs:
            truth_job[j] = {"dt_lot": recorded_lot[j][0], "dt_slot": recorded_lot[j][1]}
        for r in oracle["truth_missing"]:
            if r["table"] == "dt_log" and r["column"] in ("dt_lot", "dt_slot"):
                if r["business_key_val"] in truth_job:
                    truth_job[r["business_key_val"]][r["column"]] = r["true_value"]

        # ---- 1. inference #1, BY ANCHOR BAND --------------------------------
        print("\n" + "=" * 74)
        print("INFERENCE #1 ― dt_lot / dt_slot, by anchor band")
        print("=" * 74)
        amb_jobs = {r["subject"] for r in oracle["truth_ambiguous"]
                    if r["question"] == "dt_lot"}
        tally = defaultdict(lambda: defaultdict(int))
        for j in jobs:
            b = band_of[j]
            lot_ans, slot_ans = job_answers[j]
            expect_unres = j in amb_jobs
            tally[b]["jobs"] += 1
            if expect_unres:
                tally[b]["unresolvable"] += 1
                if lot_ans == UNRESOLVED and slot_ans == UNRESOLVED:
                    tally[b]["correct_honest"] += 1
                    tally[b]["correct"] += 1
                else:
                    tally[b]["false_confidence"] += 1
            else:
                ok = (lot_ans == truth_job[j]["dt_lot"]
                      and slot_ans == truth_job[j]["dt_slot"])
                if lot_ans == UNRESOLVED or slot_ans == UNRESOLVED:
                    tally[b]["honest_miss"] += 1
                elif ok:
                    tally[b]["correct"] += 1
                else:
                    tally[b]["wrong"] += 1
        hdr = ("band", "jobs", "correct", "wrong", "honest_miss",
               "unresolvable", "correct_honest", "false_conf")
        print("  %-7s %6s %8s %6s %12s %13s %15s %11s" % hdr)
        for b in ("high", "mid", "none", "other"):
            if not tally[b]["jobs"]:
                continue
            t = tally[b]
            print("  %-7s %6d %8d %6d %12d %13d %15d %11d"
                  % (b, t["jobs"], t["correct"], t["wrong"], t["honest_miss"],
                     t["unresolvable"], t["correct_honest"], t["false_confidence"]))

        # ---- 2. inference #2, BY SYMMETRY -----------------------------------
        print("\n" + "=" * 74)
        print("INFERENCE #2 ― coordinate frame, by subset symmetry")
        print("=" * 74)
        truth_frame = {(r["space"], r["scope"]): r for r in oracle["truth_frame"]}
        amb_frame = {r["subject"] for r in oracle["truth_ambiguous"]
                     if r["question"] == "dt_frame"}
        print("  %-22s %-8s %-14s %-14s %-12s %s"
              % ("scope", "space", "true", "answered", "symmetric?", "verdict"))
        f_tally = defaultdict(lambda: defaultdict(int))
        for (e, p) in combos:
            scope = "%s|%s" % (e, p)
            jobs_here = [j for j in jobs if job_combo[j] == (e, p)]
            all_sym = all(symmetric_of[j] for j in jobs_here)
            grp = "symmetric" if all_sym else "asymmetric"
            for space in ("core", "dt"):
                t = truth_frame.get((space, scope))
                if not t:
                    continue
                ans = frame_answers[(e, p)]["core" if space == "core" else "dt"]
                expect_unres = (scope in amb_frame) and space == "dt"
                if expect_unres:
                    verdict = "CORRECT(honest)" if ans == UNRESOLVED else "FALSE CONFIDENCE"
                    f_tally[grp]["correct" if ans == UNRESOLVED else "false_confidence"] += 1
                elif ans == UNRESOLVED:
                    verdict = "honest_miss"
                    f_tally[grp]["honest_miss"] += 1
                elif ans == t["true_frame"]:
                    verdict = "CORRECT"
                    f_tally[grp]["correct"] += 1
                else:
                    verdict = "WRONG"
                    f_tally[grp]["wrong"] += 1
                f_tally[grp]["total"] += 1
                print("  %-22s %-8s %-14s %-14s %-12s %s"
                      % (scope, space, t["true_frame"], ans, grp, verdict))
        print()
        for grp in ("asymmetric", "symmetric"):
            t = f_tally[grp]
            if not t["total"]:
                continue
            print("  %-11s total=%-3d correct=%-3d wrong=%-3d honest_miss=%-3d "
                  "false_confidence=%d"
                  % (grp, t["total"], t["correct"], t["wrong"],
                     t["honest_miss"], t["false_confidence"]))

        # ---- 3. die lineage --------------------------------------------------
        print("\n" + "=" * 74)
        print("DIE LINEAGE ― the section 0 question")
        print("=" * 74)
        tracer = BaselineTracer(lot_events, dt_rows, job_answers, frame_answers)
        answers = []
        stops = defaultdict(int)
        for b in bond_rows:
            res = tracer.trace(b)
            if res["stop"]:
                stops[res["stop"]] += 1
            answers.append({
                "bond_lot": b["bond_lot"], "bond_slot": b["bond_slot"],
                "bond_x": b["bond_x"], "bond_y": b["bond_y"],
                "core_wafer": res["core_wafer"],
                "core_x": res["core_x"], "core_y": res["core_y"]})
        rep = scoring.score_die_lineage(oracle, answers)
        total = max(rep["total"], 1)
        print("  truth rows            : %d" % rep["total"])
        print("  correct (recall)      : %d  (%.1f%%)" % (rep["correct"], 100.0 * rep["correct"] / total))
        print("  wrong                 : %d  (%.1f%%)" % (rep["wrong"], 100.0 * rep["wrong"] / total))
        print("     of which: right wafer, wrong coordinates : %d"
              % rep["wafer_right_coords_wrong"])
        print("     (that split matters ― the wafer comes from the lineage walk,")
        print("      the coordinates from the frame. One number would hide which.)")
        print("  honest miss (unknown) : %d  (%.1f%%)" % (rep["honest_miss"], 100.0 * rep["honest_miss"] / total))
        print("  unanswered            : %d" % rep["unanswered"])
        print("  -- where the trace stopped --")
        for k, v in sorted(stops.items(), key=lambda x: -x[1]):
            print("     %-42s %d" % (k, v))

        # ---- 4. honesty over every ambiguous case ---------------------------
        print("\n" + "=" * 74)
        print("HONESTY ― truth_ambiguous (unresolved answered unresolved = CORRECT)")
        print("=" * 74)
        # Only answers the system ACTUALLY produced go in here. The first version
        # broadcast each combo's frame answer down onto every job in that combo, which
        # manufactured 41 "false confidence" cases out of nothing: the system never
        # claims a per-job frame -- its decision unit is (equipment, product). Scoring
        # a per-combo answer against a per-job question is a category error in the
        # SCORER, and inventing answers in order to mark them wrong is just as
        # dishonest as inventing them to mark them right.
        all_ans = {}
        for j in jobs:
            all_ans[(j, "dt_lot")] = job_answers[j][0]
        for (e, p) in combos:
            all_ans[("%s|%s" % (e, p), "dt_frame")] = frame_answers[(e, p)]["dt"]
        h = scoring.score_ambiguous(oracle, all_ans)
        print("  ambiguous cases       : %d" % h["total"])
        print("  answered UNRESOLVED   : %d   <- counted CORRECT" % h["answered_unresolved"])
        print("  answered with a VALUE : %d   <- FALSE CONFIDENCE" % h["answered_with_value"])
        print("  no system answer      : %d" % h["unanswered"])
        if h["subjects"]:
            print("  false-confidence subjects: %s"
                  % ", ".join(map(str, h["subjects"][:10])))
        job_frame_cases = sum(1 for r in oracle["truth_ambiguous"]
                              if r["question"] == "dt_frame" and "|" not in r["subject"])
        print("  -- of the 'no system answer' cases, %d are per-JOB dt_frame entries."
              % job_frame_cases)
        print("     The oracle records symmetry per job; the system decides per")
        print("     (equipment, product). That granularity gap is a fixture finding,")
        print("     not a score: a symmetric job inside an ASYMMETRIC combo is")
        print("     legitimately answerable from its siblings' evidence.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
