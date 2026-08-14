# -*- coding: utf-8 -*-
"""The three journey axes the console asks for and the ledger has no field for yet:
post-bond queue time, an MI measured quantity, and path features (rework / skip).

WHY THIS IS A NEW FILE AND NOT A KEY ADDED TO `seed_syn_process_ledger`
----------------------------------------------------------------------
🔴 `object_payload` IS PART OF THE ATOM IDENTITY. `ledger/schema.DEDUPE_COLUMNS` lists
`coalesce(object_payload, '{}'::jsonb)` among the seven columns the unique index compares.
So adding one key to the payload of an EXISTING atom family and re-running does not update
those atoms - it inserts a SECOND atom beside every one of them, same subject, same step,
same `occurred_at`, differing only in the new key. The walk then counts two claims where
the world has one.

That is not a hypothetical: the board records exactly this artefact already ("엑스커전
웨이퍼 75장이 BONDING 리비전 주장을 «둘» 이고 있다" - rev5 and rev6 both live, so `rev=5`
also enriches at 9.19x). Re-running the answer-key generator with a widened payload would
reproduce it across EVERY `processed_with` atom in the fixture and would shake the very
answer key ruling R-F says not to shake.

So every atom here is a NEW claim about a step that had no atom before. Nothing existing is
rewritten, nothing is deleted, and a re-run with the same inputs dedupes to zero because the
identity is a pure function of the inputs.

WHERE THE FIELDS LAND, AND WHO SAYS SO
--------------------------------------
`config/mechanism_models.json` -> `bindings` declares the address form
(`<predicate>:<dotted field path>`) and names, in as many words, the gap this file fills:

    「`post_bond_queue_h` (the observation-bias model's only source) has NO field in the
      ledger today - no translated payload carries the bond-to-inspection wait」

So the queue lands at `params_actual.post_bond_queue_h`, which is the path a binding would
name. ⚠️ THE BINDING ITSELF IS NOT WRITTEN HERE - config is not this lane's to edit. Until
somebody declares `processed_with:params_actual.post_bond_queue_h -> post_bond_queue_h`, the
factor reaches the ranking with `unknown` in the mechanism column, which the bindings
docstring says is the correct behaviour for an unbound candidate rather than a defect.

The MI quantity is deliberately UNBOUND - no thickness node exists in either formation
model - because the numeric-contrast and missing-class demos do not need one, and inventing
a mechanism edge to make a screen look complete is the thing the same docstring forbids.

THE THREE FAMILIES, AND WHAT EACH ONE IS FOR
--------------------------------------------
A. POST_BOND_QUEUE  every wafer.  One excursion lot waits far longer than the rest, so the
                    contrast has something to catch. It is an OBSERVATION-BIAS node
                    (`void_observation_bias`), so a screen that ranks it as a cause is
                    wrong and this fixture is how that gets seen.
B. MI_THICKNESS     most wafers. A deliberate hole - one excursion lot is mostly unmeasured
                    - because 「없어서 0」 is its own class and a fixture with full coverage
                    cannot show it. 「결측 부류가 뜨는 게 데모의 일부다.」
C. PLASMA_CLEAN     a PATH feature, and the two cases are deliberately different:
                      * SKIPPED on one excursion lot        -> discriminates (case-only)
                      * RUN TWICE on one excursion lot AND on one control lot
                                                            -> does NOT discriminate
                    A fixture where every path feature separates the cases teaches that
                    path features always separate the cases.

🔴 WHY NEITHER PLANT OUTRANKS THE ANSWER KEY. Each covers ONE of the three excursion lots,
so its case coverage is 1/3, while `processed_with·recipe.rev = 6` covers 3/3 - MEASURED
after this script ran: case 75/75, control 0/834, `absent_from_control_population`, CI
[104.5, 26661], gates `PP-`. And `seed_syn_process_ledger --prove` still returns PASS on all
four of its own two-way assertions, which is the re-confirmation ruling R-F asks for.

⚠️ TWO MEASUREMENT NOTES, because both of them cost time to establish and neither is
guessable from the response:

  * THE SCOPE SHORTHAND IS NOT THREE LOTS. `scope=bond_lot:SYN-VOID-101,102,103` parses to
    `values: ["SYN-VOID-101", "102", "103"]`; the last two match no row and the API does not
    say so, so the case set is ONE lot's 25 wafers. Spell every value out
    (`...,SYN-VOID-102,SYN-VOID-103`) to get 75. The board's recorded answer key uses the
    shorthand.
  * THE CI MOVED, AND NOT BECAUSE THE PLANT DID. The walk samples the control group under a
    60,000-atom budget (`atoms_estimated 52,050`, `control_subjects 834 of 2,500`,
    `sample_step 3`). The ~7k atoms here raise atoms-per-subject and therefore eat that
    headroom, which widens every CI in the response. The verdicts do not move; the interval
    does. Anyone comparing a CI against a number recorded on another day must check
    `walk.control_subjects` first.

SEPARATION
----------
Every atom carries `source_translator_ver LIKE 'syn_journey/%'`. No RDB row is written at
all, so there is no `updated_by` footprint to clean up.

    ROLLBACK:  DELETE FROM ledger_events WHERE source_translator_ver LIKE 'syn_journey/%';
               DELETE FROM ledger_translator_cursor WHERE source = 'syn_journey';

Usage::

    conda run -n assy_manager python server/scripts/seed_syn_journey_atoms.py
    conda run -n assy_manager python server/scripts/seed_syn_journey_atoms.py \
        --apply --i-accept-writing-to-owner-database
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The answer-key generator owns wafer enumeration, the stable hash and the timestamp
# convention. Importing them keeps "which wafers exist" and "what time is day 0" answered
# in ONE place - a second spelling of either is how two fixtures come to describe two
# different worlds while claiming to describe one.
import seed_syn_process_ledger as apl  # noqa: E402

SOURCE = "syn_journey"
TRANSLATOR_BASE = f"{SOURCE}/1/rules:journey1"

#: Utterers. Unregistered in `crud.SOURCE_PRIORITY` on purpose, same as the answer key's:
#: source priority must not decide what the claim class is allowed to decide.
WHO_MES = "syn_mes_queue"
WHO_MI = "syn_mi_gauge"
WHO_EQP = "syn_eqp_log"
WHO_RECIPE_BOOK = "syn_recipe_book"

DERIV_MES_QUEUE = "mes_queue"
DERIV_MI_GAUGE = "mi_gauge"
DERIV_EQP_LOG = "eqp_log"
DERIV_FIRST_SIGHT = "first_sight"
DERIV_RECIPE_BOOK = "recipe_book"
DECLARED_DERIVATIONS = frozenset({DERIV_MES_QUEUE, DERIV_MI_GAUGE, DERIV_EQP_LOG,
                                  DERIV_FIRST_SIGHT, DERIV_RECIPE_BOOK})
DECLARED_SUBJECT_TYPES = frozenset({"Wafer", "Recipe"})

#: 🔴 THE GATE REQUIRES A RECIPE ON EVERY `processed_with`, AND IT IS RIGHT TO.
#: `ledger/gate.py` refuses the predicate without `step`, `step_family`, `eqp` and
#: `recipe` - a step that ran under no recipe is a claim nobody can reproduce. So each
#: family here declares its own, and the reference is not left dangling: `recipe_atoms`
#: below emits the `register` + `has_param` atoms those payloads point at. A `recipe`
#: key pointing at a subject with no atoms would put a reference on screen that the walk
#: cannot resolve, which is worse than no reference.
#:
#: The setpoints are the ones a reader would want beside the measurement: the stocker's
#: holding limit next to the wait, the thickness spec next to the gauge reading.
RECIPES = {
    ("SYN-RCP-QUEUE", "1"): {"max_queue_h": (24.0, "h")},
    ("SYN-RCP-MI", "1"): {"spec_thickness_um": (750.0, "um"), "tol_um": (8.0, "um")},
    ("SYN-RCP-CLEAN", "1"): {"clean_time_s": (60.0, "s"), "power_W": (300.0, "W")},
}
#: APPEND-ONLY, for the reason `seed_syn_process_ledger.RECIPE_ORDER` spells out: the
#: index decides `occurred_at`, so inserting a member above an existing one re-stamps it
#: and every already-written atom of that recipe is re-inserted instead of deduping.
RECIPE_ORDER = (
    ("SYN-RCP-QUEUE", "1"), ("SYN-RCP-MI", "1"), ("SYN-RCP-CLEAN", "1"),
)

STEP_QUEUE = "POST_BOND_QUEUE"
STEP_MI = "MI_THICKNESS"
STEP_CLEAN = "PLASMA_CLEAN"
#: `step_family` scopes mechanism validity (PHYSICS_ONTOLOGY_SETUP §2). The queue and the
#: clean are packaging steps; metrology is its own family and is bound to no model, which
#: is the honest state for a quantity no formation graph names.
FAMILY_PACKAGING = "packaging"
FAMILY_METROLOGY = "metrology"

#: The excursion lots (`seed_syn_lot_excursion`). Named rather than derived so the one
#: fact this file needs from that fixture is legible in one line.
EXCURSION_LOTS = ("101", "102", "103")
#: Which lot each demo lands on. One excursion lot each, so no plant covers more than a
#: third of the case set - see the docstring's note on why that keeps the answer key on top.
LOT_LONG_QUEUE = "101"      # waits days instead of hours
LOT_MI_SPARSE = "102"       # mostly unmeasured - the missing class
LOT_SKIP_CLEAN = "103"      # never plasma-cleaned - a path feature that DOES discriminate
#: Rework lands on a case AND a control on purpose: a path feature that does not separate
#: the two groups is the negative case, and a fixture without one cannot show it.
LOTS_REWORK = ("101", "007")

QUEUE_H_MIN, QUEUE_H_MAX = 4, 20            # the ordinary bond-to-inspection wait
QUEUE_H_LONG_MIN, QUEUE_H_LONG_MAX = 60, 96
MI_ABSENT_PCT = 30            # ordinary lots: this share of wafers is never measured
MI_ABSENT_PCT_SPARSE = 85     # the sparse lot
THICKNESS_UM_MIN, THICKNESS_UM_MAX = 742.0, 758.0

MI_EQPS = ("SYN-MI-01", "SYN-MI-02")
CLEAN_EQPS = ("SYN-PC-01", "SYN-PC-02", "SYN-PC-03")
STOCKERS = ("SYN-STK-A", "SYN-STK-B")


def _atom(subject_type, subject_keys, predicate, object_kind, payload, occurred_at,
          who, derivation, raw_ref, molecule_ref):
    """This file's own atom builder, and it MUST NOT be `seed_syn_process_ledger._atom`.

    🔴 MEASURED THE HARD WAY, 2026-08-14: the first version of this script called the
    answer key's `_atom` to avoid a second spelling of the envelope. That helper closes
    over ITS OWN module-level `TRANSLATOR_BASE`, so all 6,964 atoms landed stamped
    `syn_process_ledger/1/rules:answerkey1#...` — the answer key's name. Two consequences,
    both silent: the rollback predicate documented at the top of this file matched ZERO
    rows, and every atom this lane added became indistinguishable from the answer key's to
    anyone measuring that fixture. The insert reported `inserted 6964` either way.

    Reusing a helper is right when the helper is a pure function of its arguments. This one
    is not: the provenance stamp is exactly the thing that must differ per generator, so it
    is the one piece that cannot be borrowed.
    """
    from ledger.envelope import Atom

    return Atom(
        subject_type=subject_type, subject_keys=subject_keys, predicate=predicate,
        object_kind=object_kind, object_payload=payload, occurred_at=occurred_at,
        source_who=who,
        source_translator_ver=f"{TRANSLATOR_BASE}#{derivation}",
        source_raw_ref=raw_ref, derivation=derivation, molecule_ref=molecule_ref)


def lot_of(wafer: str) -> str:
    """`SYN-BW-<lot>-<slot>` -> `<lot>`. The base id format `seed_syn_void_base_join` mints.

    Returns `""` for a wafer id that does not carry a lot, so a differently shaped id is
    simply not assigned a lot-level demo rather than raising or - worse - silently landing
    in the wrong lot.
    """
    parts = wafer.split("-")
    return parts[2] if len(parts) >= 4 else ""


def _span(wafer: str, salt: str, low, high):
    """A stable value in `[low, high]`, from the answer key's sha256 hash.

    Never `hash()` - it is salted per process for str, so the seeding run and the proving
    run would disagree about the same wafer (`seed_syn_process_ledger._h` says why).
    """
    steps = 1000
    frac = (apl._h(salt, wafer) % steps) / float(steps - 1)
    return low + (high - low) * frac


def _pct(wafer: str, salt: str) -> int:
    return apl._h(salt, wafer) % 100


def _pick(wafer: str, salt: str, options):
    return options[apl._h(salt, wafer) % len(options)]


def recipe_atoms():
    """`register` + one `has_param` per setpoint, so no payload's `recipe` dangles."""
    missing = set(RECIPES) ^ set(RECIPE_ORDER)
    if missing:
        raise SystemExit("REFUSED: RECIPE_ORDER and RECIPES disagree about %s - a member "
                         "in one and not the other is an atom with no stamp or a stamp "
                         "with no atom." % sorted(missing))
    atoms = []
    for index, (recipe_id, rev) in enumerate(RECIPE_ORDER):
        keys = {"recipe": recipe_id, "rev": rev}
        ref = f"recipe_book:{recipe_id}@{rev}"
        molecule = f"{SOURCE}:recipe:{recipe_id}:{rev}"
        when = apl._stamp(-3, 100 + index)
        atoms.append(_atom("Recipe", keys, "register", None, None, when,
                               WHO_RECIPE_BOOK, DERIV_FIRST_SIGHT, ref, molecule))
        for name, (value, unit) in sorted(RECIPES[(recipe_id, rev)].items()):
            atoms.append(_atom(
                "Recipe", keys, "has_param", "value",
                {"param": name, "value": value, "unit": unit},
                when, WHO_RECIPE_BOOK, DERIV_RECIPE_BOOK, f"{ref}#{name}", molecule))
    return atoms


def _recipe_ref(recipe_id: str, rev: str) -> dict:
    """The shape the answer key's payloads already use, so one reader serves both."""
    return {"id": recipe_id, "rev": rev}


def queue_atoms(wafer: str):
    """The bond-to-inspection wait. ONE atom per wafer, on a step nothing else claims."""
    lot = lot_of(wafer)
    if lot == LOT_LONG_QUEUE:
        hours = _span(wafer, "queue_long", QUEUE_H_LONG_MIN, QUEUE_H_LONG_MAX)
    else:
        hours = _span(wafer, "queue", QUEUE_H_MIN, QUEUE_H_MAX)
    hours = round(hours, 1)
    payload = {
        "step": STEP_QUEUE, "step_family": FAMILY_PACKAGING,
        "eqp": _pick(wafer, "stocker", STOCKERS),
        "recipe": _recipe_ref("SYN-RCP-QUEUE", "1"),
        # The dotted path `bindings` would name: `processed_with:params_actual.<field>`.
        "params_actual": {"post_bond_queue_h": hours},
    }
    molecule = f"{SOURCE}:queue:{wafer}"
    return [_atom("Wafer", {"wafer": wafer}, "processed_with", "value", payload,
                      apl._stamp(1, 30), WHO_MES, DERIV_MES_QUEUE,
                      f"mes_queue:{wafer}", molecule)]


def mi_atoms(wafer: str):
    """A measured thickness - or NOTHING, which is the other half of this axis.

    An unmeasured wafer emits no atom at all. That is what makes the missing class real:
    a placeholder atom carrying `null` would be a record of a measurement that did not
    happen, and the worklist would have nothing to ask for.
    """
    lot = lot_of(wafer)
    cutoff = MI_ABSENT_PCT_SPARSE if lot == LOT_MI_SPARSE else MI_ABSENT_PCT
    if _pct(wafer, "mi_present") < cutoff:
        return []
    payload = {
        "step": STEP_MI, "step_family": FAMILY_METROLOGY,
        "eqp": _pick(wafer, "mi_eqp", MI_EQPS),
        "recipe": _recipe_ref("SYN-RCP-MI", "1"),
        "params_actual": {
            "thickness_um": round(_span(wafer, "thk", THICKNESS_UM_MIN,
                                        THICKNESS_UM_MAX), 2)},
    }
    molecule = f"{SOURCE}:mi:{wafer}"
    return [_atom("Wafer", {"wafer": wafer}, "processed_with", "value", payload,
                      apl._stamp(1, 90), WHO_MI, DERIV_MI_GAUGE,
                      f"mi_gauge:{wafer}", molecule)]


def clean_atoms(wafer: str):
    """Zero, one or two passes of the same step - the path feature.

    Two passes are TWO atoms with different `occurred_at` and different `source_raw_ref`,
    which is what a rework actually looks like in a log. They are not a duplicate: the pass
    number is in the payload, so a consumer that counts hops and a consumer that reads the
    latest claim both get the right answer.
    """
    lot = lot_of(wafer)
    if lot == LOT_SKIP_CLEAN:
        return []
    passes = 2 if lot in LOTS_REWORK else 1
    eqp = _pick(wafer, "clean_eqp", CLEAN_EQPS)
    molecule = f"{SOURCE}:clean:{wafer}"
    atoms = []
    for pass_no in range(1, passes + 1):
        payload = {"step": STEP_CLEAN, "step_family": FAMILY_PACKAGING,
                   "eqp": eqp, "pass_no": pass_no,
                   "recipe": _recipe_ref("SYN-RCP-CLEAN", "1"),
                   "params_actual": {
                       "clean_time_s": round(_span(wafer, "clean%d" % pass_no,
                                                   45.0, 75.0), 1)}}
        atoms.append(_atom(
            "Wafer", {"wafer": wafer}, "processed_with", "value", payload,
            apl._stamp(-1, 20 + (pass_no - 1) * 45), WHO_EQP, DERIV_EQP_LOG,
            f"eqp_log:{eqp}:{wafer}:{STEP_CLEAN}:p{pass_no}", molecule))
    return atoms


def build(wafers):
    atoms = recipe_atoms()
    tally = {"recipe": len(atoms), "queue": 0, "mi": 0, "clean": 0,
             "mi_absent": 0, "clean_skipped": 0, "clean_rework": 0}
    for wafer in sorted(wafers):
        q = queue_atoms(wafer)
        m = mi_atoms(wafer)
        c = clean_atoms(wafer)
        atoms.extend(q + m + c)
        tally["queue"] += len(q)
        tally["mi"] += len(m)
        tally["clean"] += len(c)
        if not m:
            tally["mi_absent"] += 1
        if not c:
            tally["clean_skipped"] += 1
        if len(c) > 1:
            tally["clean_rework"] += 1
    return atoms, tally


def screen_all(atoms):
    """Through `gate.screen_molecule`, the same gate the production path runs.

    A fixture that bypassed the gate is a fixture production would refuse.
    """
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
            raise SystemExit(
                "REFUSED: the generator produced a molecule the ledger gate rejects "
                "(%s: %s). This is a bug in this script, not in the gate."
                % (refusal.reason, refusal.detail))
    return kept


def write_atoms(atoms, batch_size: int = 2000) -> dict:
    from database.database import engine
    from ledger.store import LedgerStore

    store = LedgerStore(engine, who=SOURCE)
    store.ensure_schema()
    totals = {"attempted": 0, "inserted": 0, "deduped": 0}
    for start in range(0, len(atoms), batch_size):
        chunk = atoms[start:start + batch_size]
        result = store.write_batch(
            SOURCE, TRANSLATOR_BASE, chunk,
            cursor_value={"written_through": start + len(chunk)},
            molecules=len({a.molecule_ref for a in chunk}),
            refused=0, incomplete=0, reasons={})
        for key in totals:
            totals[key] += result[key]
    return totals


def guard_database(db, allow_owner: bool, writing: bool) -> str:
    from sqlalchemy import text

    name = db.execute(text("SELECT current_database()")).scalar()
    if writing and name == "assy_manager" and not allow_owner:
        raise SystemExit(
            "REFUSED: connected to 'assy_manager', the owner's working database. Pass "
            "--i-accept-writing-to-owner-database - the flag is the RECORD that this "
            "write happened (ruling R-2026-08-14-I), not a permission to wait for.")
    print("database: %s" % name)
    print("!! rollback: DELETE FROM ledger_events WHERE source_translator_ver LIKE "
          "'%s/%%'" % SOURCE)
    print("!! rollback: DELETE FROM ledger_translator_cursor WHERE source = '%s'" % SOURCE)
    return name


def main():
    ap = argparse.ArgumentParser(
        description="Seed post-bond queue, MI thickness and path-feature atoms. "
                    "Additive: no existing atom or row is touched.")
    ap.add_argument("--apply", action="store_true", help="write; otherwise report only")
    ap.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                    dest="allow_owner")
    args = ap.parse_args()

    from database.database import SessionLocal
    from database import crud, models
    models.init_dynamic_models(crud.TABLE_CONFIG)

    db = SessionLocal()
    try:
        guard_database(db, args.allow_owner, writing=args.apply)
        # The wafer set is MEASURED from the fixture that already exists, never assumed -
        # the same reason `measured_void_rate`'s docstring gives.
        wafers = sorted(apl.measured_void_rate(db))
    finally:
        db.close()

    print("wafers in fixture   : %d" % len(wafers))
    atoms, tally = build(wafers)
    kept = screen_all(atoms)
    print("atoms built         : %d  (gate kept %d)" % (len(atoms), len(kept)))
    print("  recipe register/has_param : %d" % tally["recipe"])
    print("  POST_BOND_QUEUE   : %d" % tally["queue"])
    print("  MI_THICKNESS      : %d   (unmeasured wafers: %d)"
          % (tally["mi"], tally["mi_absent"]))
    print("  PLASMA_CLEAN      : %d   (skipped wafers: %d, reworked wafers: %d)"
          % (tally["clean"], tally["clean_skipped"], tally["clean_rework"]))
    for lot in EXCURSION_LOTS:
        sample = [w for w in wafers if lot_of(w) == lot][:1]
        if sample:
            w = sample[0]
            print("  lot %s sample %-16s queue=%s mi=%s clean_passes=%d"
                  % (lot, w,
                     queue_atoms(w)[0].object_payload["params_actual"]["post_bond_queue_h"],
                     "yes" if mi_atoms(w) else "ABSENT", len(clean_atoms(w))))
    if not args.apply:
        print("DRY RUN, nothing written.")
        return
    totals = write_atoms(kept)
    print("attempted %(attempted)d  inserted %(inserted)d  deduped %(deduped)d" % totals)


if __name__ == "__main__":
    main()
