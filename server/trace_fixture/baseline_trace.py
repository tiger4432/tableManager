# -*- coding: utf-8 -*-
"""A baseline reasoner over what the system ACTUALLY knows, for scoring.

This is the consumer side of the fixture: it answers the section 0 question --
"this bonded chip failed; which core wafer and which die did it come from" -- using
only what is in the database plus what enrichment has confirmed. Its score is
therefore a measurement of the system's current capability, not of an oracle-aware
shortcut.

[The one rule this module obeys]

It NEVER guesses. Every step that cannot be resolved returns UNRESOLVED and the chain
stops there. That is what makes the score meaningful: a tracer that fell back to "the
most likely core wafer" would score higher and tell us nothing, because a plausible
wrong answer is precisely the failure this project refuses. The scorer counts those
stops as `honest_miss`, separately from `wrong`.

[Why it needs a lot_event walk and not a join]

`bonding_log` records (dt_lot, dt_slot) as of BONDING. `dt_log` recorded its own as of
DT. Split and merge moved the wafer in between, so joining the two columns does not
error -- it matches the wrong wafer. The walk below reconstructs, from lot_event
snapshots, WHICH WAFER stood at that lot and slot at that moment, and follows the
wafer (the identity) rather than the position (a state).
"""

import bisect
from collections import defaultdict

from .frames import CANONICAL, FrameGrid

UNRESOLVED = "미상"
SEP = ":"


def norm_lot(v):
    """`CL_2601_001` and `CL-2601-001` are the same lot. Notation drift is applied on
    the referencing side only, so undoing it here is lossless."""
    return (v or "").strip().replace("_", "-")


def norm_slot(v):
    """`7` and `07` are the same slot -- which only survives because the column is
    declared `string`. A `number` declaration would have destroyed this at write time."""
    v = (v or "").strip()
    return v.zfill(2) if v.isdigit() else v


class PositionHistory:
    """Where every wafer stood, over time, reconstructed from lot_event alone.

    Each lot_event row carries the COMPLETE post-event membership of one lot, so a
    row is a snapshot rather than a delta. A wafer's position at time T is the latest
    snapshot at or before T that mentions it.
    """

    def __init__(self, rows):
        self._by_wafer = defaultdict(list)   # wafer -> [(time, lot, slot)]
        self._by_lot = defaultdict(list)     # lot -> [(time, {slot: wafer})]
        for r in rows:
            slots = (r["slot_numbers"] or "").split(SEP) if r["slot_numbers"] else []
            wafers = (r["wafer_ids"] or "").split(SEP) if r["wafer_ids"] else []
            if len(slots) != len(wafers):
                # The generator asserts this cannot happen; if it ever does, refusing
                # is the only safe move -- a positional mismatch silently reattributes
                # wafers to the wrong slots and every answer built on it looks fine.
                continue
            t = r["event_time"]
            members = {}
            for s, w in zip(slots, wafers):
                s = norm_slot(s)
                members[s] = w
                self._by_wafer[w].append((t, norm_lot(r["lot"]), s))
            self._by_lot[norm_lot(r["lot"])].append((t, members))
        for w in self._by_wafer:
            self._by_wafer[w].sort(key=lambda x: x[0])
        for l in self._by_lot:
            self._by_lot[l].sort(key=lambda x: x[0])

    def wafer_at(self, lot, slot, at):
        """Which wafer stood at (lot, slot) at that moment. None if unknowable."""
        lot, slot = norm_lot(lot), norm_slot(slot)
        snaps = self._by_lot.get(lot)
        if not snaps:
            return None
        i = bisect.bisect_right([s[0] for s in snaps], at) - 1
        if i < 0:
            return None
        return snaps[i][1].get(slot)

    def position_at(self, wafer, at):
        """(lot, slot) of a wafer at that moment. None if unknowable."""
        hist = self._by_wafer.get(wafer)
        if not hist:
            return None
        i = bisect.bisect_right([h[0] for h in hist], at) - 1
        if i < 0:
            return None
        return hist[i][1], hist[i][2]


class BaselineTracer:
    def __init__(self, lot_events, dt_rows, job_answers, frame_answers):
        """
        job_answers   : {dt_job: (dt_lot|UNRESOLVED, dt_slot|UNRESOLVED)}
        frame_answers : {(eqp, product): {"core": frame|UNRESOLVED, "dt": ...}}
        """
        self.hist = PositionHistory(lot_events)
        self.job_answers = job_answers
        self.frame_answers = frame_answers
        self.grid = FrameGrid(13, 13)

        self.job_meta = {}
        self.cells = {}
        for r in dt_rows:
            job = r["dt_job"]
            self.cells[(job, r["dt_x"], r["dt_y"])] = r
            if job not in self.job_meta:
                self.job_meta[job] = {"eqp": r["dt_eqp"], "product": r["product"],
                                      "when": r["event_time"]}

        # Which tape wafer each job produced, via the CONFIRMED lot/slot only. A job
        # whose attribution is unresolved contributes nothing -- it does not fall back
        # to the recorded dt_lot, because 10% of those are wrong and a wrong one makes
        # this map silently point at the wrong wafer.
        self.wafer_to_job = {}
        for job, (lot, slot) in job_answers.items():
            if lot == UNRESOLVED or slot == UNRESOLVED:
                continue
            meta = self.job_meta.get(job)
            if not meta:
                continue
            w = self.hist.wafer_at(lot, slot, meta["when"])
            if w:
                self.wafer_to_job[w] = job

    def trace(self, bond_row):
        """One bonding row -> the core die it came from, or a named stop."""
        out = {"core_wafer": UNRESOLVED, "core_x": UNRESOLVED,
               "core_y": UNRESOLVED, "stop": None}

        tape = self.hist.wafer_at(bond_row["dt_lot"], bond_row["dt_slot"],
                                  bond_row["event_time"])
        if not tape:
            out["stop"] = "no_wafer_at_bonding_position"
            return out

        job = self.wafer_to_job.get(tape)
        if not job:
            out["stop"] = "tape_wafer_not_attributed_to_a_job"
            return out

        cell = self.cells.get((job, bond_row["dt_x"], bond_row["dt_y"]))
        if cell is None:
            out["stop"] = "no_dt_cell_at_that_position"
            return out

        meta = self.job_meta[job]
        frames = self.frame_answers.get((meta["eqp"], meta["product"]), {})
        core_frame = frames.get("core", UNRESOLVED)
        if core_frame == UNRESOLVED:
            out["stop"] = "core_frame_unresolved"
            return out

        # The anchor, when present, names the wafer outright.
        wafer = (cell.get("core_wafer") or "").strip()
        if not wafer:
            # Otherwise fall back to the recorded core lot/slot AT DT TIME, and walk
            # back to the identity. Notation drift is undone first.
            lot = norm_lot(cell.get("core_lot"))
            slot = norm_slot(cell.get("core_slot"))
            if not lot or not slot:
                out["stop"] = "no_core_identity_on_the_dt_cell"
                return out
            wafer = self.hist.wafer_at(lot, slot, meta["when"])
            if not wafer:
                # The core lots' ORIGINAL membership is never written to lot_event --
                # only splits and merges are -- so a wafer that never moved has no
                # snapshot to be found in. Named, not silently guessed.
                out["stop"] = "core_lot_slot_has_no_lot_event_snapshot"
                return out

        try:
            cx, cy = self.grid.restore(core_frame, int(cell["core_x"]), int(cell["core_y"]))
        except (TypeError, ValueError):
            out["stop"] = "core_coordinates_unreadable"
            return out

        out["core_wafer"] = wafer
        out["core_x"] = cx
        out["core_y"] = cy
        return out
