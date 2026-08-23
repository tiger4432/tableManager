# -*- coding: utf-8 -*-
"""A lot that splits into two branches bonded at different pressure, then merges back.

WHAT THIS EXISTS TO PROVE
-------------------------
`config/mechanism_models.json` asserts, in two separate models, that ONE quantity pushes
TWO different defects in OPPOSITE directions:

    void_formation    bond_pressure  --(-)-->  interface_unfill  --(+)-->  void
    delam_formation   bond_pressure  --(+)-->  die_stress        --(+)-->  delam

and its own `signatures` block says so in a sentence: 「pressure LOW feeds void_formation,
pressure HIGH feeds die_stress - the two models together make bond_pressure vs quality
non-monotone」. Until now that was a declaration with no data under it. This script writes
the data, in the direction the declaration states:

    branch A   LOW pressure     -> voids up,   delam at baseline
    branch B   HIGH pressure    -> delam up,   voids at baseline
    retained   setpoint pressure-> both at baseline          (the arm with nothing planted)

🔴 THE SIGN IS THE WHOLE POINT. Seeded the other way round the mechanism gate SHOULD reject
both as direction mismatches, so a flipped fixture would not "still work" - it would quietly
test the opposite thing. `_assert_direction()` re-reads both models from the config at run
time and refuses to write if either edge stops saying what this file assumes. That is
cheaper than being right today and wrong after somebody edits the graph.

🔴 AND THERE IS A THIRD ARM ON PURPOSE. Eight wafers stay in the parent lot at the recipe's
declared setpoint. Without them 「심지 않은 쪽은 안 뜬다」 is untestable: every wafer in the
fixture would carry a planted condition and a screen that colours everything would look
correct. The retained arm is the one that must stay grey.

ZERO NEW DECLARATIONS, WHICH IS THE TEST
----------------------------------------
Nothing here declares a new axis, factor, route or predicate. The branch is expressed as LOT
MEMBERSHIP (`lot_event` rows - the ledger's own grammar) and the condition lives only in
`processed_with` `params_actual.pressure_MPa`, a path `bindings` already maps to
`bond_pressure`. The contrast is supposed to find the divergence by WALKING and the mechanism
gate to explain each branch from M4 alone. If either needs a declaration added, the console
has not earned the word 「유니버셜」 yet, and this fixture is how that gets found out.

All three arms cite the SAME recipe and revision (`SYN-RCP-BOND` rev 4, an already-registered
subject). An arm that also differed by revision would let the contrast win on `recipe.rev`
and never look at the number - the fixture would pass while testing nothing.

THE SHAPE
---------
    SYN-SPL-400  (24 wafers)
      ├─split→ SYN-SPL-400-A   8 wafers, low pressure  ─┐
      ├─split→ SYN-SPL-400-B   8 wafers, high pressure ─┴─merge→ SYN-MRG-400
      └─retains 8 wafers at setpoint

⚠️ TWO TRAPS IN THE `lot_event` GRAMMAR, BOTH MEASURED ON THE EXISTING CORPUS RATHER THAN
ASSUMED, AND THE FIRST ONE ATE A ROW OF THE FIRST DRAFT:

  1. The business key is `lot|event_type|event_time` (composed by `crud` from
     `table_config`), so ONE LOT CANNOT HAVE TWO ROWS OF THE SAME EVENT TYPE AT THE SAME
     INSTANT - they collide into one row and one of the two splits silently disappears. The
     parent's split to A and its split to B therefore happen an hour apart, and so do the
     two merges. `event_id` is NOT written here at all; writing it would be a second
     spelling of a key `crud` already composes.
  2. A split's two rows are both POST-move (disjoint wafer sets: the parent row lists what
     STAYED, the child row what MOVED). A merge's source row is PRE-move and its destination
     row POST-move, so the moved wafers appear on BOTH - and that overlap is exactly what
     the translator reads to emit `slot_map#shared_wafer`. A merge written as two disjoint
     lists is not "tidier", it is a merge with no slot mapping.

The pair becomes ONE `derived_from` Lot->Lot atom (subject = the row carrying `parent_lot`),
plus `has_wafer` per listed wafer. `derived_from` is the ONE predicate the walk recurses on
(`ledger_trace.traversal_predicate()`), so the merge lot reaches both branches and
`has_wafer` says which wafer went which way - 「어느 갈래를 걸어왔는지가 걷기로 복원 가능」
with nothing declared.

⚠️ NOTHING TRANSLATES `lot_event` ON ITS OWN. There is no worker: the rows become atoms only
when somebody runs `python -m ledger.backfill --source lot_event`. A previous lane's habit of
writing rows and reporting 「연결됨」 would produce a lot_event table nobody walked. `--apply`
therefore prints the exact commands, and `--verify-rollback` counts the atoms.

⚠️ `bonding_log.bond_lot` STAYS THE ARM'S LOT, deliberately. Nothing in the codebase joins
`bonding_log` to `lot_event` (measured), and re-keying those rows to the merge lot would
erase the branch from the source table - the ledger's whole claim is that it preserves what
the source said at the time.

WHAT IS DELIBERATELY *NOT* PLANTED
----------------------------------
The three arms share one equipment pool, one chamber assignment rule and one scan recipe per
kind, all drawn from the wafer index and therefore branch-independent by construction.
`post_bond_queue_h` is NOT emitted here at all - `seed_syn_journey_atoms` is the single owner
of that field and draws it from a wafer-id hash that knows nothing about branches. Two
writers of one field is how a fixture acquires a factor nobody planted, and the brief is
explicit that the observation-bias gate must not ring on this lot.

Ratios are aimed away from the excursion ladder (measured 2.30 / 3.38 / 4.97x) so nobody
reading a coloured cell has to ask which fixture produced it.

SEPARATION AND ROLLBACK
-----------------------
    DELETE FROM void_obs        WHERE base_wafer_id LIKE 'SYN-BW-SPL-400-%';
    DELETE FROM delam_obs       WHERE base_wafer_id LIKE 'SYN-BW-SPL-400-%';
    DELETE FROM inspection_run  WHERE base_wafer_id LIKE 'SYN-BW-SPL-400-%';
    DELETE FROM bonding_log     WHERE bond_lot LIKE 'SYN-SPL-400%';
    DELETE FROM lot_event       WHERE lot LIKE 'SYN-SPL-400%' OR lot = 'SYN-MRG-400';
    DELETE FROM wafer_map_metadata WHERE map_id LIKE 'SYN-SPL-400%';
    DELETE FROM ledger_events   WHERE source_translator_ver LIKE 'syn_split_merge/%';
    DELETE FROM ledger_translator_cursor WHERE source = 'syn_split_merge';
    DELETE FROM cell_sources    WHERE updated_by = 'seed_syn_split_merge_pressure';

`--verify-rollback` COUNTS every one of those and REFUSES if the ledger predicate matches
zero, because a rollback predicate that matches nothing is the failure mode this lane hit
tonight: a borrowed `_atom` helper stamped 6,964 rows with ANOTHER module's translator name
and the documented predicate silently pointed at nothing. Every helper below that writes a
namespace value is declared HERE for that reason, even where an import would have worked.

Usage::

    conda run -n assy_manager python server/scripts/seed_syn_split_merge_pressure.py
    conda run -n assy_manager python server/scripts/seed_syn_split_merge_pressure.py \
        --apply --i-accept-writing-to-owner-database
    conda run -n assy_manager python server/scripts/seed_syn_split_merge_pressure.py \
        --verify-rollback
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Geometry primitives only. `vbj` owns "which cells exist" and "bond -> base"; a second
# spelling of either is how two screens come to disagree about where a die is.
import seed_syn_void_base_join as vbj            # noqa: E402
# Stable hash, timestamps, chambers and the delam vocabulary. NOT `_atom` and NOT `_write` -
# both close over that module's own namespace constants.
import seed_syn_process_ledger as apl            # noqa: E402

SOURCE = "syn_split_merge"
TRANSLATOR_BASE = f"{SOURCE}/1/rules:pressure1"
UPDATED_BY = "seed_syn_split_merge_pressure"
SOURCE_NAME = "custom_script"
CHUNK = 1000

WHO_EQP_LOG = "syn_eqp_log"
DERIV_EQP_LOG = "eqp_log"
DECLARED_DERIVATIONS = frozenset({DERIV_EQP_LOG})
DECLARED_SUBJECT_TYPES = frozenset({"Wafer"})

PARENT_LOT = "SYN-SPL-400"
CHILD_A = "SYN-SPL-400-A"
CHILD_B = "SYN-SPL-400-B"
MERGE_LOT = "SYN-MRG-400"
BASE_ID_FMT = "SYN-BW-SPL-400-%02d"
PER_ARM = 8

#: `(branch, lot, pressure)`. "P" is the retained arm and its pressure IS the setpoint.
ARMS = (
    ("A", CHILD_A, 0.12),
    ("B", CHILD_B, 0.58),
    ("P", PARENT_LOT, 0.35),
)
PRESSURE_JITTER = 0.02

#: An already-registered recipe subject. All three arms cite it, so `recipe.rev` cannot
#: separate them and the number has to.
RECIPE_ID, RECIPE_REV = "SYN-RCP-BOND", "4"

#: Dirty-scan probabilities. The planted arm is high; the other two sit at one shared
#: baseline, which is what makes 「심지 않은 쪽은 안 뜬다」 checkable rather than asserted.
P_PLANTED, P_BASE = 0.80, 0.13
SCAN_EVERY = 3                      # 141 positions -> 47 scanned per wafer per kind

BOND_EQP_POOL = ("SYN-BD-11", "SYN-BD-12")
VOID_RECIPE, VOID_EQP = "SYN_VOID_R1", "SYN-SAT-01"
DELAM_RECIPE, DELAM_EQP = "SYN_DELAM_R1", "SYN-SCAT-01"
STOCKER = "SYN-STK-11"

#: 🔴 FOUR DISTINCT INSTANTS, one per event. See trap 1 in the module docstring: the business
#: key is `lot|event_type|event_time`, so the parent's two splits MUST NOT share an instant
#: and neither may the merge lot's two merges.
T_SPLIT_A = "2026-08-12 01:00:00"
T_SPLIT_B = "2026-08-12 02:00:00"
T_MERGE_A = "2026-08-12 05:00:00"
T_MERGE_B = "2026-08-12 06:00:00"


# --------------------------------------------------------------------------
# The declaration this fixture reproduces - re-read, never assumed
# --------------------------------------------------------------------------


def _assert_direction():
    """Refuse to write if M4 no longer says what the plant assumes.

    Both paths are checked end to end. A fixture that hard-codes a sign it never re-read is
    a fixture that keeps testing yesterday's graph.
    """
    path = os.path.join(_SERVER, "config", "mechanism_models.json")
    if not os.path.exists(path):
        path = os.path.join(_SERVER, "config", "sample",
                            "mechanism_models.json.sample")
    with open(path, encoding="utf-8") as fh:
        models = json.load(fh)

    def edge(model, src, dst):
        for e in (models.get(model) or {}).get("edges") or ():
            if e.get("from") == src and e.get("to") == dst:
                return e.get("dir")
        return None

    expected = (("void_formation", "bond_pressure", "interface_unfill", "-"),
                ("void_formation", "interface_unfill", "void", "+"),
                ("delam_formation", "bond_pressure", "die_stress", "+"),
                ("delam_formation", "die_stress", "delam", "+"))
    problems = ["%s: %s -> %s is %r, expected %r" % (m, s, d, edge(m, s, d), want)
                for m, s, d, want in expected if edge(m, s, d) != want]
    if problems:
        raise SystemExit(
            "REFUSED: M4 no longer declares the directions this fixture plants, so writing "
            "it would seed the OPPOSITE of what the graph says:\n  " + "\n  ".join(problems))
    return "low pressure -> void, high pressure -> delam (re-read from mechanism_models)"


# --------------------------------------------------------------------------
# The world
# --------------------------------------------------------------------------


def wafers():
    """`[(base_id, branch, bond_lot, bond_slot, index)]` - 8 per arm, slots 01..08 in each."""
    out = []
    for arm_no, (branch, lot, _p) in enumerate(ARMS):
        for i in range(PER_ARM):
            index = arm_no * PER_ARM + i
            out.append((BASE_ID_FMT % (index + 1), branch, lot, "%02d" % (i + 1), index))
    return out


def arm_wafers(branch):
    return [w[0] for w in wafers() if w[1] == branch]


def pressure_for(branch, base_id):
    centre = dict((b, p) for b, _l, p in ARMS)[branch]
    jitter = ((apl._h("p", base_id) % 2001) - 1000) / 1000.0        # -1.0 .. +1.0
    return round(centre + PRESSURE_JITTER * jitter, 4)


def bonding_rows(base_id, bond_lot, bond_slot, index):
    """One wafer's bonded dies. Base (x, y) DERIVED through the declared frame transform.

    The recorded frame is cycled across wafers exactly as `vbj.frame_for_wafer` does, so this
    lot exercises rotations and both sides rather than only the identity case.
    """
    frame = vbj.frame_for_wafer(400, index + 1)
    to_base, _to_recorded, cells = vbj.base_derivation(frame)
    rng = vbj._rng(20260814, 400, index + 1)
    rows = []
    for bond_x, bond_y in cells:
        bx, by = to_base(bond_x, bond_y)
        rows.append({
            "bond_lot": bond_lot, "bond_slot": bond_slot,
            "bond_x": bond_x, "bond_y": bond_y,
            "base_id": base_id, "bx": bx, "by": by,
            "b_bn": "0" if rng.random() < 0.05 else "1",
            "stack_height": vbj.STACK_MIN + ((bond_x * 5 + bond_y * 3)
                                             % (vbj.STACK_MAX - vbj.STACK_MIN + 1)),
            "bond_eqp": BOND_EQP_POOL[index % len(BOND_EQP_POOL)],
            "event_time": vbj.EVENT_TIME,
        })
    return frame, rows


def scan_rows(base_id, branch, bond, index):
    """`(runs, voids, delams)` for one wafer - BOTH kinds on the SAME positions.

    Scanning both kinds on every wafer is what lets the contrast say 「voids up here, delam up
    there」 rather than 「these wafers were scanned differently」. The two kinds share
    `inspection_run` and are told apart by `method`, which is key material - so the method is
    read from the registry rather than typed, and a deployment that renames it follows.
    """
    from ledger_api import finding_kinds

    void_method = finding_kinds.methods(finding_kinds.DEFAULT_KIND)[0]
    delam_method = finding_kinds.methods(apl.DELAM_METHOD_KIND)[0]
    p_void = P_PLANTED if branch == "A" else P_BASE
    p_delam = P_PLANTED if branch == "B" else P_BASE

    runs, voids, delams = [], [], []
    for n, row in enumerate(bond[::SCAN_EVERY]):
        bx, by, stack = row["bx"], row["by"], int(row["stack_height"])
        gate = 1 + (apl._h("gate", base_id, bx, by) % max(1, stack))
        for kind, method, recipe, eqp, p, day in (
                ("void", void_method, VOID_RECIPE, VOID_EQP, p_void, 3),
                ("delam", delam_method, DELAM_RECIPE, DELAM_EQP, p_delam, 4)):
            observed_at = apl._stamp_text(day, index * 13 + n * 2)
            run = {"method": method, "base_wafer_id": base_id, "base_x": bx, "base_y": by,
                   "stack_gate": gate, "recipe_id": recipe, "eqp_id": eqp,
                   "observed_at": observed_at}
            run_uid = apl._business_key("inspection_run", run)
            if run_uid is None:
                raise SystemExit("REFUSED: could not key a %s run for %s (%s, %s)."
                                 % (method, base_id, bx, by))
            runs.append(run)
            # The run is recorded BEFORE the coin flip: a clean scan is the denominator's
            # whole point and a fixture without one cannot tell 「미검사」 from 「0」.
            if (apl._h("dirty", kind, base_id, bx, by) % 10000) / 10000.0 >= p:
                continue
            for k in range(1 + (apl._h("count", kind, base_id, bx, by) % 3)):
                common = {
                    "run_uid": run_uid, "base_wafer_id": base_id,
                    "base_x": bx, "base_y": by, "stack_gate": gate,
                    "inchip_x": 50.0 + (apl._h("ix", kind, base_id, bx, by, k) % 39800) / 4.0,
                    "inchip_y": 50.0 + (apl._h("iy", kind, base_id, bx, by, k) % 39800) / 4.0}
                if kind == "void":
                    common.update({
                        "radius_x": round(1.0 + (apl._h("rx", base_id, bx, by, k) % 1400)
                                          / 100.0, 3),
                        "radius_y": round(1.0 + (apl._h("ry", base_id, bx, by, k) % 1400)
                                          / 100.0, 3),
                        "unit": vbj.UNIT})
                    voids.append(common)
                else:
                    common.update({
                        "extent_x": round(1.0 + (apl._h("ex", base_id, bx, by, k) % 4000)
                                          / 100.0, 2),
                        "extent_y": round(1.0 + (apl._h("ey", base_id, bx, by, k) % 4000)
                                          / 100.0, 2),
                        # Screened against `finding_kinds.classes("delam")` by the observation
                        # translator, which refuses an unlisted value by name.
                        "interface": apl.DELAM_INTERFACES[
                            apl._h("if", base_id, bx, by, k) % len(apl.DELAM_INTERFACES)],
                        "unit": apl.DELAM_UNIT})
                    delams.append(common)
    return runs, voids, delams


def _event(lot, event_type, when, *, parent="", child="", slots=(), ids=()):
    """One `lot_event` row. `event_id` is NOT set - `crud` composes the business key from
    `lot|event_type|event_time`, and a second spelling of a key is how a row lands under an
    identity nothing else can look up."""
    if len(slots) != len(ids):
        raise SystemExit("REFUSED: %s/%s has %d slots and %d wafers - the two lists are "
                         "read positionally and the translator refuses the molecule."
                         % (lot, event_type, len(slots), len(ids)))
    return {"lot": lot, "event_type": event_type,
            "parent_lot": parent, "child_lot": child,
            "slot_numbers": ":".join(slots), "wafer_ids": ":".join(ids),
            "equipment": STOCKER, "event_time": when}


def lot_event_rows():
    """The two splits and the two merges, two rows each, in the corpus's own shape."""
    a, b, p = arm_wafers("A"), arm_wafers("B"), arm_wafers("P")
    s8 = ["%02d" % (i + 1) for i in range(PER_ARM)]
    s16 = ["%02d" % (i + 1) for i in range(PER_ARM * 2)]

    return [
        # --- split 1: A moves out; B and the retained arm STAY with the parent.
        _event(PARENT_LOT, "split", T_SPLIT_A, child=CHILD_A, slots=s16, ids=b + p),
        _event(CHILD_A, "split", T_SPLIT_A, parent=PARENT_LOT, slots=s8, ids=a),
        # --- split 2: B moves out; the retained arm stays. An hour later, or the parent's
        #     two split rows would share a business key and one of them would vanish.
        _event(PARENT_LOT, "split", T_SPLIT_B, child=CHILD_B, slots=s8, ids=p),
        _event(CHILD_B, "split", T_SPLIT_B, parent=PARENT_LOT, slots=s8, ids=b),
        # --- merge 1: source row is PRE-move, destination row POST-move. The overlap is
        #     what the translator reads as `slot_map#shared_wafer`.
        _event(CHILD_A, "merge", T_MERGE_A, child=MERGE_LOT, slots=s8, ids=a),
        _event(MERGE_LOT, "merge", T_MERGE_A, parent=CHILD_A, slots=s8, ids=a),
        # --- merge 2: the destination now holds both arms, so its list is all sixteen.
        _event(CHILD_B, "merge", T_MERGE_B, child=MERGE_LOT, slots=s8, ids=b),
        _event(MERGE_LOT, "merge", T_MERGE_B, parent=CHILD_B, slots=s16, ids=a + b),
    ]


# --------------------------------------------------------------------------
# Atoms - this file's OWN builder, for the reason the module docstring gives
# --------------------------------------------------------------------------


def _atom(subject_keys, payload, occurred_at, raw_ref, molecule_ref):
    from ledger.envelope import Atom

    return Atom(
        subject_type="Wafer", subject_keys=subject_keys, predicate="processed_with",
        object_kind="value", object_payload=payload, occurred_at=occurred_at,
        source_who=WHO_EQP_LOG,
        source_translator_ver=f"{TRANSLATOR_BASE}#{DERIV_EQP_LOG}",
        source_raw_ref=raw_ref, derivation=DERIV_EQP_LOG, molecule_ref=molecule_ref)


def pressure_atoms():
    """One BONDING `processed_with` per wafer. Pressure is the ONLY thing that varies by arm.

    Everything else in the payload is drawn from the wafer index, which is arm-independent by
    construction - so a contrast that ranks any of them above pressure is telling us
    something about itself rather than about the world.
    """
    atoms = []
    for base_id, branch, _lot, _slot, index in wafers():
        jitter = ((apl._h("p", base_id) % 2001) - 1000) / 1000.0
        payload = {
            "step": "BONDING", "step_family": "packaging",
            "eqp": BOND_EQP_POOL[index % len(BOND_EQP_POOL)],
            "chamber": apl.CHAMBERS[index % len(apl.CHAMBERS)],
            "recipe": {"id": RECIPE_ID, "rev": RECIPE_REV},
            "params_actual": {
                "pressure_MPa": pressure_for(branch, base_id),
                "temp_C": round(150.0 + 2.0 * jitter, 3),
                "time_s": round(12.0 + 0.4 * jitter, 3),
            },
        }
        atoms.append(_atom({"wafer": base_id}, payload, apl._stamp(0, 60 + index),
                           f"eqp_log:{payload['eqp']}:{base_id}:BONDING",
                           f"{SOURCE}:bond:{base_id}"))
    return atoms


def screen_all(atoms):
    from ledger import gate

    groups = {}
    for atom in atoms:
        groups.setdefault(atom.molecule_ref, []).append(atom)
    kept = []
    for ref, members in groups.items():
        try:
            with gate.building_molecule(SOURCE):
                accepted, _report = gate.screen_molecule(
                    SOURCE, members, DECLARED_DERIVATIONS, DECLARED_SUBJECT_TYPES,
                    molecule_ref=ref)
            kept.extend(accepted)
        except gate.MoleculeRefused as refusal:
            raise SystemExit("REFUSED by the ledger gate (%s: %s). This is a bug in this "
                             "script, not in the gate." % (refusal.reason, refusal.detail))
    return kept


def write_atoms(atoms):
    from database.database import engine
    from ledger.store import LedgerStore

    store = LedgerStore(engine, who=SOURCE)
    store.ensure_schema()
    return store.write_batch(
        SOURCE, TRANSLATOR_BASE, atoms, cursor_value={"written": len(atoms)},
        molecules=len({a.molecule_ref for a in atoms}), refused=0, incomplete=0, reasons={})


# --------------------------------------------------------------------------
# RDB writing - own batch, own marker
# --------------------------------------------------------------------------


def _write(db, table, rows):
    from database import crud, schemas

    written = 0
    for start in range(0, len(rows), CHUNK):
        report = {}
        batch = schemas.GeneralUpdateBatch(
            updates=[schemas.GeneralUpdateItem(updates=r, source_name=SOURCE_NAME,
                                               updated_by=UPDATED_BY)
                     for r in rows[start:start + CHUNK]],
            replace_map=False, scope=None)
        _, changed, _, _ = crud.apply_batch_updates(db, table, batch, drop_report=report)
        if report.get("dropped_cells"):
            raise SystemExit(
                "REFUSED: writing '%s' DROPPED %d update cell(s), column(s) %s - they are "
                "not declared in table_config.json. A dropped key lands as a 200 with "
                "nothing written."
                % (table, report["dropped_cells"], sorted(report.get("by_column") or {})))
        written += len(changed or ())
        db.commit()
    return written


def register_frames(db, frames):
    import map_meta_registrar

    rows = []
    for bond_lot, bond_slot, frame in frames:
        map_id = map_meta_registrar.compose_map_id(
            ["bond_lot", "bond_slot"], {"bond_lot": bond_lot, "bond_slot": bond_slot},
            "bonding_log")
        if map_id is None:
            raise SystemExit("REFUSED: could not compose a map_id for %s/%s."
                             % (bond_lot, bond_slot))
        rows.append({"target_table": "bonding_log", "map_id": map_id,
                     "grid_metadata": json.dumps(vbj.recorded_meta(frame),
                                                 ensure_ascii=False, sort_keys=True)})
    return _write(db, "wafer_map_metadata", rows)


def guard_database(db, allow_owner, writing):
    from sqlalchemy import text

    name = db.execute(text("SELECT current_database()")).scalar()
    if writing and name == "assy_manager" and not allow_owner:
        raise SystemExit(
            "REFUSED: connected to 'assy_manager', the owner's working database. Pass "
            "--i-accept-writing-to-owner-database - the flag is the RECORD that this write "
            "happened (ruling R-2026-08-14-I), not a permission to wait for.")
    print("database: %s" % name)
    return name


ROLLBACK = (
    ("void_obs", "base_wafer_id LIKE 'SYN-BW-SPL-400-%'"),
    ("delam_obs", "base_wafer_id LIKE 'SYN-BW-SPL-400-%'"),
    ("inspection_run", "base_wafer_id LIKE 'SYN-BW-SPL-400-%'"),
    ("bonding_log", "bond_lot LIKE 'SYN-SPL-400%'"),
    ("lot_event", "lot LIKE 'SYN-SPL-400%' OR lot = 'SYN-MRG-400'"),
    ("wafer_map_metadata", "map_id LIKE 'SYN-SPL-400%'"),
    ("ledger_events", "source_translator_ver LIKE 'syn_split_merge/%'"),
    ("cell_sources", "updated_by = 'seed_syn_split_merge_pressure'"),
)


def verify_rollback(db):
    """Count what each documented predicate matches. A ledger predicate matching zero is a
    REFUSAL, not a printed zero - see the module docstring for the night this cost."""
    from sqlalchemy import text

    counts = {}
    for table, where in ROLLBACK:
        counts[table] = db.execute(
            text("SELECT count(*) FROM %s WHERE %s" % (table, where))).scalar()
        print("   %-20s %-54s -> %d" % (table, where[:54], counts[table]))
    lineage = db.execute(text(
        "SELECT count(*) FROM ledger_events WHERE source_translator_ver LIKE 'lot_event%' "
        "AND (subject_keys->>'lot' LIKE 'SYN-SPL-400%' "
        "     OR subject_keys->>'lot' = 'SYN-MRG-400')")).scalar()
    print("   %-20s %-54s -> %d" % ("ledger_events", "lot_event atoms for these lots",
                                    lineage))
    if counts.get("ledger_events", 0) == 0:
        raise SystemExit(
            "REFUSED: the ledger rollback predicate matches ZERO rows. Either nothing was "
            "written, or the atoms landed under another translator name - which is exactly "
            "how a documented rollback comes to point at nothing.")
    if lineage == 0:
        print("   ⚠️  lot_event rows are present but NOT TRANSLATED - the walk cannot see "
              "the split yet. Run: python -m ledger.backfill --source lot_event")
    return counts


def main():
    ap = argparse.ArgumentParser(
        description="Seed a split/merge lot whose arms differ only in bond pressure. "
                    "Additive; no existing row is touched.")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                    dest="allow_owner")
    ap.add_argument("--verify-rollback", action="store_true", dest="verify")
    args = ap.parse_args()

    from database.database import SessionLocal
    from database import crud, models
    models.init_dynamic_models(crud.TABLE_CONFIG)

    db = SessionLocal()
    try:
        guard_database(db, args.allow_owner, writing=args.apply)
        if args.verify:
            verify_rollback(db)
            return

        print("direction check: %s" % _assert_direction())

        bonding, frames, runs, voids, delams = [], [], [], [], []
        per_arm = {}
        for base_id, branch, bond_lot, bond_slot, index in wafers():
            frame, rows = bonding_rows(base_id, bond_lot, bond_slot, index)
            frames.append((bond_lot, bond_slot, frame))
            bonding.extend(rows)
            r, v, d = scan_rows(base_id, branch, rows, index)
            runs.extend(r)
            voids.extend(v)
            delams.extend(d)
            tally = per_arm.setdefault(branch, {"void": 0, "delam": 0, "p": []})
            tally["void"] += len(v)
            tally["delam"] += len(d)
            tally["p"].append(pressure_for(branch, base_id))

        runs = vbj.screened("inspection_run", runs, source=UPDATED_BY)
        voids = vbj.screened("void_obs", voids, source=UPDATED_BY)
        events = lot_event_rows()
        atoms = screen_all(pressure_atoms())

        print("wafers            : %d  (%d per arm x 3 arms)" % (len(wafers()), PER_ARM))
        print("bonding_log       : %d" % len(bonding))
        print("wafer_map_metadata: %d" % len(frames))
        print("inspection_run    : %d" % len(runs))
        print("void_obs          : %d" % len(voids))
        print("delam_obs         : %d" % len(delams))
        print("lot_event         : %d" % len(events))
        print("ledger atoms      : %d" % len(atoms))
        for branch, lot, _p in ARMS:
            t = per_arm[branch]
            print("   arm %s (%-14s) pressure %.3f..%.3f   void %-5d delam %-5d"
                  % (branch, lot, min(t["p"]), max(t["p"]), t["void"], t["delam"]))

        if not args.apply:
            print("DRY RUN, nothing written.")
            return

        print("bonding_log written       : %d" % _write(db, "bonding_log", bonding))
        print("wafer_map_metadata written: %d" % register_frames(db, frames))
        print("inspection_run written    : %d" % _write(db, "inspection_run", runs))
        print("void_obs written          : %d" % _write(db, "void_obs", voids))
        print("delam_obs written         : %d" % _write(db, "delam_obs", delams))
        print("lot_event written         : %d" % _write(db, "lot_event", events))
        print("ledger                    : %s" % write_atoms(atoms))
        print()
        print("rollback predicates, counted:")
        verify_rollback(db)
        print()
        print("🔴 NOT DONE YET - nothing translates these rows on its own:")
        print("   python -m ledger.backfill --source lot_event")
        print("   python -m ledger.backfill --source void_obs")
        print("   python -m ledger.backfill --source delam_obs")
    finally:
        db.close()


if __name__ == "__main__":
    main()
