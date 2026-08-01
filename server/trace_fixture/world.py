# -*- coding: utf-8 -*-
"""Builds one batch of the trace fixture world.

Everything in `docs/spec/TRACE_FIXTURE_SPEC.md` that is load-bearing is asserted
here rather than merely intended. The reason is stated in the spec itself: a fixture
that violates one of these constraints does not fail loudly -- it produces data on
which an algorithm that works on real data quietly fails, and then the algorithm
gets blamed. Each `_require` below is one such trap nailed shut.

The seven invariants, and where each is enforced:

 1. slot_numbers / wafer_ids are colon-delimited and correspond POSITIONALLY, equal
    length                                            -> `_lot_event` (every row)
 2. tape slot -> DT slot preserves MONOTONIC ORDER     -> `_dt_sessions`
 3. anchor density is banded per job: high / mid / none-> `_dt_sessions`
 4. every coordinate column carries its OWN frame,
    drawn independently                               -> `_frames`
 5. 40% of jobs get a symmetric DT subset that no
    rotation can distinguish                          -> `_tape_cells`
 6. missing values come in two kinds, identical in the
    data and separable only in the oracle             -> `_miss`
 7. 10% of dt_lot / dt_slot are PRESENT BUT WRONG      -> `_dt_sessions`
"""

import random
from datetime import datetime, timedelta

from .frames import CANONICAL, FRAMES, FrameGrid, circular_mask

SEP = ":"
TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Missing-value kinds. The first two are indistinguishable in the data ON PURPOSE --
# that is the whole point of the board's "was it never there, or did we drop it"
# question, and it can only be studied if the answer lives outside the data.
NEVER_EXISTED = "never_existed"
PIPELINE_DROPPED = "pipeline_dropped"
PRESENT_BUT_WRONG = "present_but_wrong"

EQUIPMENTS = ("DT-EQP-01", "DT-EQP-02")
PRODUCTS = ("PRD-A", "PRD-B")
BOND_EQUIPMENTS = ("BD-EQP-01",)


class GeneratorConfig(object):
    """Scale knobs. Defaults are spec section 5 -- deliberately small.

    A large fixture makes wrong things large; the first pass exists to prove the whole
    path turns over, not to be impressive.
    """

    def __init__(self, batch=1, core_lots=8, slots_per_lot=25, grid=13,
                 mask_radius=6.3, tape_wafers=120, dt_transfer_ratio=0.60,
                 bond_ratio=0.60, seed=None):
        self.batch = int(batch)
        self.core_lots = int(core_lots)
        self.slots_per_lot = int(slots_per_lot)
        self.grid = int(grid)
        self.mask_radius = float(mask_radius)
        self.tape_wafers = int(tape_wafers)
        self.dt_transfer_ratio = float(dt_transfer_ratio)
        self.bond_ratio = float(bond_ratio)
        self.seed = 20260801 * self.batch if seed is None else int(seed)


def _require(cond, msg):
    if not cond:
        raise AssertionError("[trace_fixture] invariant violated: " + msg)


class World(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.grid = FrameGrid(cfg.grid, cfg.grid)
        self.mask = sorted(circular_mask(cfg.grid, cfg.mask_radius))
        self.t0 = datetime(2026, 5, 1) + timedelta(days=30 * (cfg.batch - 1))

        self.tables = {k: [] for k in (
            "lot_event", "core_wafer_map", "dt_log", "bonding_log",
            "wafer_id_status", "wafer_map_metadata")}
        self.oracle = {k: [] for k in (
            "truth_wafer_position", "truth_die_lineage", "truth_frame",
            "truth_ambiguous", "truth_missing")}

        self.pos = {}          # wafer_id -> (lot, slot)
        self.lot_members = {}  # lot -> {slot: wafer_id}
        self._used_event_keys = set()
        self.stats = {}

    # ------------------------------------------------------------------ helpers
    def _t(self, day, minute=0):
        return self.t0 + timedelta(days=day, minutes=minute)

    def _ts(self, dt):
        return dt.strftime(TIME_FMT)

    def _miss(self, table, key, column, true_value):
        """Record a deliberate absence and WHICH KIND it is.

        70% never existed (real work), 30% the pipeline dropped it (a bug). The data
        cannot tell them apart -- only this file can. That asymmetry is the experiment.
        """
        kind = NEVER_EXISTED if self.rng.random() < 0.70 else PIPELINE_DROPPED
        self.oracle["truth_missing"].append({
            "table": table, "business_key_val": key, "column": column,
            "true_value": true_value, "kind": kind})
        return kind

    def _wrong(self, table, key, column, true_value, recorded):
        self.oracle["truth_missing"].append({
            "table": table, "business_key_val": key, "column": column,
            "true_value": true_value, "kind": PRESENT_BUT_WRONG,
            "recorded_value": recorded})

    def _ambiguous(self, case, subject, question, why, candidates):
        self.oracle["truth_ambiguous"].append({
            "case": case, "subject": subject, "question": question,
            "expected_answer": "미상", "why": why,
            "candidates": SEP.join(candidates)})

    # --------------------------------------------------------------- lot_event
    def _lot_event(self, lot, event_type, when, slots, wafers,
                   parent_lot="", child_lot="", equipment=""):
        # INVARIANT 1. Asserted in the generator, not only in the oracle: an unequal
        # length here does not raise anywhere downstream, it silently reattributes
        # wafers to the wrong slots and every reconstruction built on it is wrong in
        # a way that still looks well-formed.
        _require(len(slots) == len(wafers),
                 "slot_numbers/wafer_ids length mismatch on %s %s at %s (%d vs %d)"
                 % (lot, event_type, self._ts(when), len(slots), len(wafers)))
        key = (lot, event_type, self._ts(when))
        _require(key not in self._used_event_keys,
                 "duplicate lot_event business key %r -- the composite key "
                 "(lot, event_type, event_time) would collapse two events into one" % (key,))
        self._used_event_keys.add(key)
        self.tables["lot_event"].append({
            "lot": lot, "event_type": event_type,
            "parent_lot": parent_lot, "child_lot": child_lot,
            "slot_numbers": SEP.join(slots), "wafer_ids": SEP.join(wafers),
            "equipment": equipment, "event_time": self._ts(when)})

    def _members(self, lot):
        """(slots, wafer_ids) of a lot, sorted by slot and POSITIONALLY aligned."""
        m = self.lot_members[lot]
        slots = sorted(m)
        return slots, [m[s] for s in slots]

    def _place(self, wafer, lot, slot, when):
        old = self.pos.get(wafer)
        if old:
            self.lot_members[old[0]].pop(old[1], None)
        self.pos[wafer] = (lot, slot)
        self.lot_members.setdefault(lot, {})[slot] = wafer
        self.oracle["truth_wafer_position"].append({
            "wafer_id": wafer, "event_time": self._ts(when), "lot": lot, "slot": slot})

    # ------------------------------------------------------------------ frames
    def _frames(self):
        """INVARIANT 4 -- one independent draw per coordinate space.

        core_x,y and dt_x,y are NOT the same unknown. A row holding both couples them
        without fixing either: knowing a corresponding pair takes 8x8 candidates down
        to 8, it does not pick one. Only an anchor against the CONFIGURED map fixes a
        space, which is exactly why they are drawn independently here.

        core_wafer_map itself stays CANONICAL: it is the configured reference map, and
        the question the system has to answer is whether a recorded coordinate follows
        the same convention as that map.
        """
        self.frame_of = {}
        self.declared = {}
        combos = [(e, p) for e in EQUIPMENTS for p in PRODUCTS]
        for i, (eqp, prod) in enumerate(combos):
            core_f = self.rng.choice(FRAMES)
            dt_f = self.rng.choice(FRAMES)
            self.frame_of[(eqp, prod)] = {"core": core_f, "dt": dt_f}
            # The declaration exists but is not trustworthy (user, Q11: "인폼이 제대로
            # 안 됨"). 60% of combos are declared correctly; the rest carry a stale
            # rot0_front. A system that simply believes the declaration is therefore
            # wrong 40% of the time, and the oracle knows which.
            honest = self.rng.random() < 0.60
            self.declared[(eqp, prod)] = {
                "core": core_f if honest else CANONICAL,
                "dt": dt_f if honest else CANONICAL}
            for space in ("core", "dt"):
                self.oracle["truth_frame"].append({
                    "space": space, "scope": "%s|%s" % (eqp, prod),
                    "true_frame": self.frame_of[(eqp, prod)][space],
                    "declared_frame": self.declared[(eqp, prod)][space],
                    "declaration_is_honest": "Y" if honest else "N"})
        for eqp in BOND_EQUIPMENTS:
            f = self.rng.choice(FRAMES)
            self.frame_of[("bond", eqp)] = {"bond": f}
            self.oracle["truth_frame"].append({
                "space": "bond", "scope": eqp, "true_frame": f,
                "declared_frame": CANONICAL, "declaration_is_honest": "N"})
        self.oracle["truth_frame"].append({
            "space": "core_map", "scope": "core_wafer_map",
            "true_frame": CANONICAL, "declared_frame": CANONICAL,
            "declaration_is_honest": "Y"})
        # The all-symmetric combo: for this one, no job's occupancy can break the tie,
        # so the frame is genuinely undeterminable and "unresolved" is the right answer.
        self.symmetric_combo = combos[3]

    # -------------------------------------------------------------- core lots
    def _core_lots(self):
        cfg = self.cfg
        self.core_lot_names = []
        for i in range(cfg.core_lots):
            lot = "CL-26%02d-%03d" % (cfg.batch, i + 1)
            self.core_lot_names.append(lot)
            self.lot_members[lot] = {}
            for s in range(1, cfg.slots_per_lot + 1):
                slot = "%02d" % s
                wafer = "WF.%02d%02d%02d" % (cfg.batch, i + 1, s)
                self._place(wafer, lot, slot, self._t(0, s))

    def _lineage(self, lots, day_lo, day_hi, splits, merges, tag):
        """Split and merge, recorded as events -- never inferred from a name rule.

        Split: the child takes a NEW identity (user, spec section 1) and its wafers KEEP
        their slot numbers (user's own worked example). Merge: two at a time only,
        A+B=A, and B's wafers take the lowest free slots in A -- so a merge moves
        wafers between slot numbers, which is precisely why (lot, slot) is a state
        and not an identity.
        """
        clock = self._t(day_lo)
        step = timedelta(minutes=137)
        live = list(lots)
        child_seq = 0
        for _ in range(splits):
            clock += step
            cands = [l for l in live if len(self.lot_members.get(l, {})) >= 2]
            if not cands:
                break
            parent = self.rng.choice(cands)
            slots, wafers = self._members(parent)
            k = self.rng.randint(1, min(len(slots) - 1, self.cfg.slots_per_lot))
            moving = sorted(self.rng.sample(list(zip(slots, wafers)), k))
            child_seq += 1
            child = "%s-%s%d" % (parent, tag, child_seq)
            self.lot_members.setdefault(child, {})
            for slot, wafer in moving:
                self._place(wafer, child, slot, clock)
            p_slots, p_wafers = self._members(parent)
            c_slots, c_wafers = self._members(child)
            self._lot_event(parent, "split", clock, p_slots, p_wafers, child_lot=child)
            self._lot_event(child, "split", clock, c_slots, c_wafers, parent_lot=parent)
            live.append(child)
        for _ in range(merges):
            clock += step
            cands = [l for l in live if self.lot_members.get(l)]
            if len(cands) < 2:
                break
            a, b = self.rng.sample(cands, 2)
            b_slots, b_wafers = self._members(b)
            self._lot_event(b, "merge", clock, b_slots, b_wafers, child_lot=a)
            free = [s for s in ("%02d" % i for i in range(1, self.cfg.slots_per_lot + 1))
                    if s not in self.lot_members[a]]
            for wafer in b_wafers:
                if not free:
                    break
                self._place(wafer, a, free.pop(0), clock)
            a_slots, a_wafers = self._members(a)
            self._lot_event(a, "merge", clock, a_slots, a_wafers, parent_lot=b)
            live = [l for l in live if self.lot_members.get(l)]
        return live

    # -------------------------------------------------------------- core maps
    def _core_maps(self):
        """One row per die, measured BEFORE any split or merge.

        The measurement time matters. The map is taken at the wafer's ORIGINAL (lot,
        slot); split and merge then move the wafer, so by DT time its (lot, slot) is a
        different pair. Finding the die therefore requires walking lot_event from the
        DT-time position back to the measurement-time position -- it is not a join.
        Recording the map after the lineage would have quietly removed that step and
        left a fixture that never exercises the thing it exists for.

        Recorded in the canonical frame: this is the CONFIGURED reference map, and the
        question the system must answer is whether other coordinates share its convention.
        """
        when = self._ts(self._t(1))
        self.core_bin = {}
        self.map_home = {}
        for wafer, (lot, slot) in sorted(self.pos.items()):
            if not wafer.startswith("WF."):
                continue
            self.map_home[wafer] = (lot, slot)
            for (x, y) in self.mask:
                bad = self.rng.random() < 0.08
                self.core_bin[(wafer, x, y)] = "0" if bad else "1"
                # wafer_id on the map is deliberately sparse -- absence here is the
                # difference between "this slot never carried an id" and "we lost it".
                wid = wafer
                if self.rng.random() < 0.40:
                    self._miss("core_wafer_map",
                               "%s_%s_%d_%d" % (lot, slot, x, y), "wafer_id", wafer)
                    wid = ""
                self.tables["core_wafer_map"].append({
                    "core_lot": lot, "core_slot": slot, "core_x": x, "core_y": y,
                    "c_bn": "0" if bad else "1", "wafer_id": wid, "event_time": when})
            self.tables["wafer_map_metadata"].append({
                "target_table": "core_wafer_map", "map_id": "%s_%s" % (lot, slot),
                "grid_metadata": self._grid_meta(CANONICAL)})

    def _grid_meta(self, frame):
        import json
        rot, side = frame[3:].split("_", 1)
        return json.dumps({
            "grid_cols": self.cfg.grid, "grid_rows": self.cfg.grid,
            "grid_start_x": 0, "grid_start_y": 0, "grid_y_invert": False,
            "rotation": int(rot), "side": side,
            "phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
            "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0,
        }, ensure_ascii=False)

    # ------------------------------------------------------------- tape cells
    def _tape_cells(self, symmetric, target):
        """INVARIANT 5 -- 40% of jobs get a subset no rotation can distinguish.

        A symmetric subset is built as a union of D4 ORBITS, so it is invariant under
        all eight frames by construction and its stabiliser is the whole group: the
        frame genuinely cannot be recovered and "unresolved" is the correct answer.
        An asymmetric subset is drawn at random and then CHECKED -- randomness alone
        does not guarantee asymmetry, and an accidentally symmetric "asymmetric" job
        would be scored against the wrong expectation.
        """
        if symmetric:
            cells = set()
            pool = list(self.mask)
            self.rng.shuffle(pool)
            for seed in pool:
                if len(cells) >= target:
                    break
                cells |= (self.grid.orbit(*seed) & set(self.mask))
            inv = self.grid.invariant_frames(cells)
            _require(len(inv) == len(FRAMES),
                     "symmetric job subset is not stabilised by all 8 frames (got %d)"
                     % len(inv))
            return sorted(cells), inv
        for _ in range(40):
            cells = set(self.rng.sample(self.mask, min(target, len(self.mask))))
            inv = self.grid.invariant_frames(cells)
            if len(inv) == 1:
                return sorted(cells), inv
        _require(False, "could not draw an asymmetric tape subset in 40 attempts")

    def _die_pool(self, wafers):
        """Untransferred dies on these wafers, bad ones mostly left behind."""
        out = []
        for src in wafers:
            for (cx, cy) in self.mask:
                if (src, cx, cy) in self.used_core_die:
                    continue
                if self.core_bin[(src, cx, cy)] == "0" and self.rng.random() < 0.9:
                    continue
                out.append((src, cx, cy))
        return out

    # ----------------------------------------------------------- DT transfer
    def _dt_sessions(self):
        cfg = self.cfg
        self.used_core_die = set()
        self._combo_noted = False
        core_wafers = sorted(w for w in self.pos if w.startswith("WF."))
        per_tape = max(8, int(len(self.mask) * cfg.dt_transfer_ratio))
        n_sessions = max(1, cfg.tape_wafers // 20)
        per_session = max(1, cfg.tape_wafers // n_sessions)

        self.jobs = []
        bands = ("high", "mid", "none")
        job_i = 0
        # Sessions whose track-in event never reaches us. Chosen DETERMINISTICALLY, not
        # by a coin flip: at 6 sessions a 20% chance of dropping produced ZERO drops on
        # the first seed, so the fixture shipped with no genuinely unresolvable lot
        # attribution at all while claiming to have some. An invariant that holds only
        # in expectation is not an invariant. At least one session always loses its
        # track-in, and at least one always keeps it, so both outcomes exist.
        n_drop = max(1, int(round(0.20 * n_sessions))) if n_sessions >= 2 else 0
        dropped_sessions = set(range(n_sessions - n_drop, n_sessions))
        for si in range(n_sessions):
            eqp = EQUIPMENTS[si % len(EQUIPMENTS)]
            prod = PRODUCTS[(si // len(EQUIPMENTS)) % len(PRODUCTS)]
            frames = self.frame_of[(eqp, prod)]
            when = self._t(10 + si, 0)
            stamp = when.strftime("%Y%m%dT%H%M")
            dt_lot = "DT-26%02d-%03d" % (cfg.batch, si + 1)

            # INVARIANT 2. Tape slots and DT slots are BOTH sorted ascending before the
            # zip, so the assignment is monotonic by construction; the assert then
            # guards against a later edit breaking it. Without this the search space
            # is n! permutations instead of one monotonic assignment, and an algorithm
            # that works on real data fails here for a reason that is not its fault.
            tape_slots = sorted("T%02d" % (i + 1) for i in range(per_session))
            dt_slots = sorted(self.rng.sample(
                ["%02d" % i for i in range(1, cfg.slots_per_lot + 1)], per_session))
            assign = dict(zip(tape_slots, dt_slots))
            _require(all(a < b for a, b in zip(dt_slots, dt_slots[1:])),
                     "DT slot list is not strictly increasing for %s" % dt_lot)
            _require([assign[t] for t in tape_slots] == dt_slots,
                     "tape slot -> DT slot assignment is not monotonic for %s" % dt_lot)

            self.lot_members.setdefault(dt_lot, {})
            tape_of = {}
            for tslot in tape_slots:
                tape = "TP.%02d%02d%s" % (cfg.batch, si + 1, tslot[1:])
                tape_of[tslot] = tape
                self._place(tape, dt_lot, assign[tslot], when)

            # The track-in event is the RECORDED FACT the lot attribution rests on.
            # Dropping it for one session in five is what makes some jobs genuinely
            # unresolvable rather than merely unresolved-so-far.
            slots, wafers = self._members(dt_lot)
            if si not in dropped_sessions:
                self._lot_event(dt_lot, "track_in", when, slots, wafers, equipment=eqp)
            else:
                for tslot in tape_slots:
                    job = "%s_%s_%s" % (eqp, stamp, tslot)
                    self._miss("lot_event", "%s|track_in|%s" % (dt_lot, self._ts(when)),
                               "event_row", dt_lot)
                    self._ambiguous("dt_lot_attribution", job, "dt_lot",
                                    "설비 track-in 기록이 없어 이 job이 어느 DT 랏에 "
                                    "속했는지 근거가 남지 않았다", [dt_lot])

            for tslot in tape_slots:
                job = "%s_%s_%s" % (eqp, stamp, tslot)
                band = bands[job_i % len(bands)]
                job_i += 1
                # INVARIANT 5 targets 40% symmetric OVERALL. One combo in four is
                # entirely symmetric (so a whole decision key is genuinely
                # undeterminable, not just individual jobs), which already supplies
                # 25%; 0.20 on the remaining 75% brings the total to 0.25 + 0.15 = 0.40.
                symmetric = ((eqp, prod) == self.symmetric_combo
                             or self.rng.random() < 0.20)
                cells, inv = self._tape_cells(symmetric, per_tape)
                if len(inv) > 1:
                    self._ambiguous(
                        "coordinate_frame", job, "dt_frame",
                        "이 job의 점유 셀 집합이 8지 전부에 대해 대칭이라 회전을 "
                        "구별할 신호가 데이터 안에 없다", list(inv))

                # A die is transferred ONCE. Drawing core cells with replacement would
                # let two tape cells claim the same die, and then no correct answer
                # exists for either -- the oracle would be self-contradictory.
                # Bad dies are mostly left behind, which is what makes the transferred
                # subset partial (user: "코어에서 불량 칩을 빼고 다시 맵을 구성").
                #
                # The pool is GROWN to fit the cell set, never the other way round.
                # Truncating `cells` to fit the pool was the first version and it was
                # wrong: it ran after _tape_cells had verified the set's symmetry, so a
                # subset certified as fully symmetric arrived at the oracle with a
                # stabiliser of 2. The job was then recorded as undeterminable while
                # its data had in fact become determinable -- the scorer would have
                # marked an honest "unresolved" wrong. Caught by the independent test,
                # not by the generator's own assert, which is why that test exists.
                sources = self.rng.sample(core_wafers, self.rng.randint(1, 3))
                spare = [w for w in core_wafers if w not in sources]
                self.rng.shuffle(spare)
                pool = self._die_pool(sources)
                while len(pool) < len(cells) and spare:
                    extra = spare.pop()
                    sources.append(extra)
                    pool.extend(self._die_pool([extra]))
                _require(len(pool) >= len(cells),
                         "ran out of untransferred core dies for job %s "
                         "(need %d, have %d)" % (job, len(cells), len(pool)))
                self.rng.shuffle(pool)
                true_lot, true_slot = self.pos[tape_of[tslot]]

                # INVARIANT 7 + the 40% absence, decided PER JOB so every cell of one
                # job tells the same story -- a per-cell decision would let a single
                # job contradict itself, which no real equipment does.
                roll = self.rng.random()
                if roll < 0.40:
                    rec_lot, rec_slot = "", ""
                    self._miss("dt_log", job, "dt_lot", true_lot)
                    self._miss("dt_log", job, "dt_slot", true_slot)
                elif roll < 0.50:
                    # The wrong value must actually BE wrong. Drawing from all DT lots
                    # without excluding the true one produced "wrong" values equal to
                    # the truth, which would have quietly diluted the 10% and let a
                    # system score credit for a case it never faced.
                    # Prefer a REAL other DT lot: that is the nastier case, because the
                    # bad join then finds rows and succeeds quietly. But the first
                    # session has no other DT lot yet, and falling back to the true lot
                    # made the "wrong" value equal the truth -- so the fallback is a
                    # transcription slip on the serial, which is wrong by construction.
                    others = [l for l in sorted(self.lot_members)
                              if l.startswith("DT-") and l != true_lot]
                    if others:
                        rec_lot = self.rng.choice(others)
                    else:
                        head, tail = true_lot.rsplit("-", 1)
                        rec_lot = "%s-%03d" % (head, (int(tail) % 99) + 1)
                    slots = ["%02d" % i for i in range(1, self.cfg.slots_per_lot + 1)
                             if "%02d" % i != true_slot]
                    rec_slot = self.rng.choice(slots)
                    _require(rec_lot != true_lot or rec_slot != true_slot,
                             "a 'present but wrong' value is identical to the truth "
                             "for job %s" % job)
                    self._wrong("dt_log", job, "dt_lot", true_lot, rec_lot)
                    self._wrong("dt_log", job, "dt_slot", true_slot, rec_slot)
                else:
                    rec_lot, rec_slot = true_lot, true_slot

                # INVARIANT 3 by CONSTRUCTION, not by probability. A per-cell coin
                # flip lands near the target but not on it, and on a small job it can
                # fall out of band -- which would make the fixture's own guarantee a
                # dice roll. The anchored cells are chosen as an exact count instead.
                frac_target = {"high": self.rng.uniform(0.50, 0.80),
                               "mid": self.rng.uniform(0.10, 0.30),
                               "none": 0.0}[band]
                self.jobs.append({
                    "job": job, "eqp": eqp, "product": prod, "when": when,
                    "dt_lot_true": true_lot, "dt_slot_true": true_slot,
                    "tape": tape_of[tslot], "cells": cells, "band": band,
                    "symmetric": len(inv) > 1})

                n_anchor = int(round(frac_target * len(cells)))
                anchored_ix = set(self.rng.sample(range(len(cells)), n_anchor))
                anchors_placed = 0
                for ci, ((dx, dy), (src, cx, cy)) in enumerate(zip(cells, pool)):
                    self.used_core_die.add((src, cx, cy))
                    dt_lot_now, dt_slot_now = self.pos[src]
                    map_lot, map_slot = self.map_home[src]
                    rx, ry = self.grid.record(frames["dt"], dx, dy)
                    rcx, rcy = self.grid.record(frames["core"], cx, cy)
                    anchored = ci in anchored_ix
                    core_wafer = src if anchored else ""
                    anchors_placed += 1 if anchored else 0
                    if not anchored:
                        self._miss("dt_log", "%s_%d_%d" % (job, rx, ry),
                                   "core_wafer", src)
                    # At least one of (core_lot+core_slot) or core_wafer is always
                    # present -- the user was explicit that one of the two is certain.
                    show_ls = (not anchored) or self.rng.random() < 0.5
                    self.tables["dt_log"].append({
                        "dt_job": job, "dt_eqp": eqp, "product": prod,
                        "dt_lot": rec_lot, "dt_slot": rec_slot,
                        "dt_x": rx, "dt_y": ry,
                        # The core lot/slot AS OF DT TIME, which is not where the core
                        # map was measured -- lot_event is the only bridge between them.
                        "core_lot": self._drift_lot(dt_lot_now) if show_ls else "",
                        "core_slot": self._drift_slot(dt_slot_now) if show_ls else "",
                        "core_wafer": core_wafer,
                        "core_x": rcx, "core_y": rcy,
                        "c_bn": self.core_bin[(src, cx, cy)],
                        "event_time": self._ts(when)})
                    self.oracle["truth_die_lineage"].append({
                        "dt_job": job, "dt_x_true": dx, "dt_y_true": dy,
                        "core_wafer": src,
                        "core_lot_at_dt": dt_lot_now, "core_slot_at_dt": dt_slot_now,
                        "core_lot": map_lot, "core_slot": map_slot,
                        "core_x_true": cx, "core_y_true": cy,
                        "bond_lot": "", "bond_slot": "", "bond_x_true": "",
                        "bond_y_true": ""})
                # INVARIANT 3, checked against what was actually produced rather than
                # against the probability that was intended.
                frac = (anchors_placed / float(len(cells))) if cells else 0.0
                # EPS absorbs the rounding to a whole number of cells: an exact 10%
                # target on 69 cells is 6.9 cells, and 7/69 = 0.1014 while 6/69 =
                # 0.0870. The band is a statement about intent, not about float
                # equality, and a bare `>=` here fails on arithmetic rather than on
                # anything being wrong with the data.
                eps = 1.0 / max(len(cells), 1)
                if band == "none":
                    _require(frac == 0.0, "band 'none' produced anchors (%.2f)" % frac)
                elif band == "high":
                    _require(frac >= 0.50 - eps,
                             "band 'high' produced only %.3f anchor density" % frac)
                else:
                    _require(0.10 - eps <= frac <= 0.30 + eps,
                             "band 'mid' produced %.3f, outside 0.10-0.30" % frac)
                self.tables["wafer_map_metadata"].append({
                    "target_table": "dt_map", "map_id": job,
                    "grid_metadata": self._grid_meta(self.declared[(eqp, prod)]["dt"])})

            # Once per combo, not once per session: the same combo can run several
            # sessions, and a duplicated truth row would double-count the case.
            if (eqp, prod) == self.symmetric_combo and not self._combo_noted:
                self._combo_noted = True
                self._ambiguous(
                    "coordinate_frame", "%s|%s" % (eqp, prod), "dt_frame",
                    "이 설비/제품의 job이 전부 대칭 부분집합이라 어느 job을 봐도 "
                    "회전이 갈리지 않는다", list(FRAMES))

    def _drift_lot(self, lot):
        """Notation drift on the REFERENCING side only.

        `LOT_01` vs `LOT-01` is applied where a lot is quoted (dt_log), never where it
        is defined (core_wafer_map). Drifting the defining side would split one
        wafer's map into two map_ids and break the map view -- a different defect from
        the one this drift exists to exercise, which is join-side normalisation.
        """
        return lot.replace("-", "_") if self.rng.random() < 0.10 else lot

    def _drift_slot(self, slot):
        """`07` vs `7`. Only survives if the column is declared `string`."""
        return slot.lstrip("0") or "0" if self.rng.random() < 0.15 else slot

    # ---------------------------------------------------------------- bonding
    def _bonding(self):
        cfg = self.cfg
        bond_eqp = BOND_EQUIPMENTS[0]
        bframe = self.frame_of[("bond", bond_eqp)]["bond"]
        lineage_ix = {}
        for row in self.oracle["truth_die_lineage"]:
            lineage_ix.setdefault(row["dt_job"], {})[(row["dt_x_true"], row["dt_y_true"])] = row

        for bi, job in enumerate(self.jobs):
            bond_lot = "BS-26%02d-%03d" % (cfg.batch, (bi // cfg.slots_per_lot) + 1)
            bond_slot = "%02d" % ((bi % cfg.slots_per_lot) + 1)
            when = self._t(25, bi)
            # The bonding-time position, AFTER the DT lot's own split/merge history.
            # This is the crux: it differs from what dt_log recorded at DT time, so a
            # join on (dt_lot, dt_slot) does not error -- it matches the wrong wafer.
            bond_lot_seen, bond_slot_seen = self.pos[job["tape"]]
            frames = self.frame_of[(job["eqp"], job["product"])]
            chosen = [c for c in job["cells"] if self.rng.random() < cfg.bond_ratio]
            for (dx, dy) in chosen:
                bx, by = self.grid.record(bframe, dx, dy)
                rdx, rdy = self.grid.record(frames["dt"], dx, dy)
                self.tables["bonding_log"].append({
                    "bond_lot": bond_lot, "bond_slot": bond_slot,
                    "bond_x": bx, "bond_y": by,
                    "b_bn": "0" if self.rng.random() < 0.05 else "1",
                    "stack_height": self.rng.randint(8, 12),
                    "dt_lot": bond_lot_seen, "dt_slot": bond_slot_seen,
                    "dt_x": rdx, "dt_y": rdy,
                    "bond_eqp": bond_eqp, "event_time": self._ts(when)})
                src = lineage_ix.get(job["job"], {}).get((dx, dy))
                if src is not None:
                    src["bond_lot"] = bond_lot
                    src["bond_slot"] = bond_slot
                    src["bond_x_true"] = bx
                    src["bond_y_true"] = by

    # ------------------------------------------------------- sparse witnesses
    def _wafer_id_status(self):
        """Only 20% of real state changes are recorded (user: "SPARSE 함")."""
        for row in self.oracle["truth_wafer_position"]:
            if not row["wafer_id"].startswith("WF."):
                continue
            if self.rng.random() >= 0.20:
                continue
            self.tables["wafer_id_status"].append({
                "core_lot": row["lot"], "core_slot": row["slot"],
                "wafer_id": row["wafer_id"], "valid_from": row["event_time"]})

    # -------------------------------------------------------------------- run
    def build(self):
        self._frames()
        self._core_lots()
        # Core maps are measured BEFORE the lineage runs, on purpose -- see _core_maps.
        self._core_maps()
        self._lineage(self.core_lot_names, 2, 9,
                      splits=self.cfg.core_lots, merges=max(1, self.cfg.core_lots // 3),
                      tag="A")
        self._dt_sessions()
        dt_lots = [l for l in self.lot_members if l.startswith("DT-")]
        self._lineage(dt_lots, 20, 24, splits=max(1, len(dt_lots)),
                      merges=max(1, len(dt_lots) // 2), tag="B")
        self._bonding()
        self._wafer_id_status()

        # A die whose bonding row was never written cannot be scored against; drop it
        # from the lineage oracle rather than leaving a half-filled row that would
        # read as "the system failed to trace this".
        self.oracle["truth_die_lineage"] = [
            r for r in self.oracle["truth_die_lineage"] if r["bond_lot"]]

        bands = {}
        for j in self.jobs:
            bands[j["band"]] = bands.get(j["band"], 0) + 1
        self.stats = {
            "batch": self.cfg.batch,
            "rows": {k: len(v) for k, v in self.tables.items()},
            "oracle": {k: len(v) for k, v in self.oracle.items()},
            "jobs": len(self.jobs),
            "jobs_symmetric": sum(1 for j in self.jobs if j["symmetric"]),
            "anchor_bands": bands,
        }
        return self


def generate_batch(cfg):
    return World(cfg).build()
