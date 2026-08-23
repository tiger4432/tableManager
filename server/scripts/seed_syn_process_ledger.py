"""Process conditions, recipes, a second finding kind - and the ANSWER KEY for all of it.

WHAT THIS ADDS, ON TOP OF `seed_syn_void_base_join`
---------------------------------------------------
That script built 2,500 synthetic base wafers, the SAT scans on them, and the join that
says which die is under a void. It could not say ANYTHING about why a void happened,
because the system had nowhere to put a process condition. This script fills that hole
and then plants something for an analysis to find:

  1. `processed_with` v0 - the reserved predicate, opened. One atom per (wafer, step).
  2. `Recipe` as an ISSUED entity with `rev` IN THE SUBJECT KEY, plus `has_param`, one
     atom per setpoint. Two revisions of the bonding recipe differ in two parameters.
  3. An ANSWER KEY: one factor that genuinely drives each finding kind, and DECOYS that
     are common to BOTH the found and the clean-scanned populations.
  4. A SECOND finding kind (`delam`) with a DIFFERENT planted factor, so "switch the kind
     and each kind's own factor comes out" is an assertion rather than a hope.

🔴 THE POINT OF THE DECOYS
---------------------------
A view that finds the shared factors of six voids will always find something: they all
went through the BONDING step, they were all bonded under recipe `SYN-RCP-BOND`, and 70%
of them sat in chamber `CH-A`. Every one of those is true, and every one of them is also
true of the packages that were scanned and were FINE. An intersection view cannot tell
them apart; a contrast view can, and if it cannot, it is not working. So the decoys are
not padding - they are the test. `--prove` asserts BOTH directions: the planted factor is
enriched, and each decoy is NOT.

🔴 «MEASURED BEATS SETPOINT» IS NOT IMPLEMENTED HERE, AND THAT IS THE DESIGN PAYING OFF
----------------------------------------------------------------------------------------
For a wafer whose equipment log exists there are TWO `processed_with` atoms: one carrying
`params_actual` (what the machine said) and one carrying `params_setpoint` (what the
recipe declared). Nothing in this file, and nothing in `ledger_trace`, was written to make
the measurement win. It wins because `claim_class` puts an atom with the payload flag
`inferred: true` at class 3 and a plain utterance at class 2, and `claim_rank_key` seals
every tiebreak INSIDE the class - so no later level can promote the setpoint.

The fixture is built so that ONLY the class can decide, which is the whole difference
between a test and a coincidence:

  * the setpoint atom is written FIRST, so its uuid7 sorts lower (rank level 3 favours it)
  * the setpoint atom's `occurred_at` is LATER (rank level 2b favours it)
  * both sources are unregistered, so `get_source_priority` is 99 for both (level 1 ties)

A class-blind resolver therefore picks the SETPOINT on every such wafer, and `--prove`
runs exactly that mutant to show the fixture can tell the difference.

🔴 HOW THE VOID FACTOR WAS PLANTED, STATED PLAINLY
---------------------------------------------------
The 91,756 voids already in `assy_manager` were generated at random and this script is
ADD-ONLY: it may not rewrite them. So the void factor is planted by ASSIGNING the recipe
revision against each wafer's ALREADY-MEASURED void incidence - the wafers in the top
decile get `rev5`. The association in the data is therefore real and is exactly what a
contrast view has to find; what is synthetic is the direction of construction (outcome ->
factor rather than factor -> outcome). The second kind is built the other way round -
`delam` findings are GENERATED from the moulding equipment - so the detector is scored
against one association of each construction, and neither route is the only one it has
ever seen.

Usage::

    # dry run: build everything, write nothing, print what would land
    conda run -n assy_manager python server/scripts/seed_syn_process_ledger.py

    # write (this box's dev database is `assy_manager` and it is the owner's)
    ... seed_syn_process_ledger.py --apply --i-accept-writing-to-owner-database

    # the deliverable: the answer key, in both directions, for EVERY declared kind
    ... seed_syn_process_ledger.py --prove
    ... seed_syn_process_ledger.py --prove --finding delam

ROLLBACK
--------
    DELETE FROM ledger_events            WHERE source_translator_ver LIKE 'syn_process_ledger/%';
    DELETE FROM ledger_translator_cursor WHERE source = 'syn_process_ledger';
    DELETE FROM delam_obs                WHERE run_uid LIKE 'scat|%';
    DELETE FROM inspection_run           WHERE method = 'scat';
    -- and the cell layers those two RDB tables wrote:
    DELETE FROM cell_sources    WHERE updated_by = 'seed_syn_process_ledger';
    DELETE FROM cell_overwrites WHERE updated_by = 'seed_syn_process_ledger';
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# --------------------------------------------------------------------------
# Namespace. Every row and every atom this script writes is reachable by one of
# these, which is what makes the rollback above a predicate rather than a list.
# --------------------------------------------------------------------------
SOURCE = "syn_process_ledger"
UPDATED_BY = "seed_syn_process_ledger"
SOURCE_NAME = "custom_script"

#: The provenance stamp. 🔴 THIS is the ledger's rollback marker, not `source_who`:
#: `source_who` deliberately VARIES (an equipment log and a recipe book are different
#: utterers, and the fixture needs them to be) so it cannot also be the fixture's
#: boundary. `source_translator_ver` is constant per derivation prefix and is indexed
#: by nothing, which is fine for a DELETE that runs once.
TRANSLATOR_BASE = f"{SOURCE}/1/rules:answerkey1"

BASE_ID_PREFIX = "SYN-BW-"
BOND_LOT_PREFIX = "SYN-VOID-"

#: Who UTTERED each flavour. Both unregistered in `crud.SOURCE_PRIORITY`, hence both
#: rank 99 - see the module docstring: the fixture must not let source priority decide
#: what only the class is allowed to decide.
WHO_EQP_LOG = "syn_eqp_log"
WHO_RECIPE_BOOK = "syn_recipe_book"

#: Derivations this generator may stamp. `screen_molecule` refuses anything outside the
#: set, exactly as it does for a config-declared translator. They are declared HERE
#: rather than in `ledger_config.json` because this source is a generator, not a table
#: translator - `ledger_config.validate` requires `columns.lot`/`event_type`/... which a
#: generator has none of, and inventing empty ones would put a declaration in the
#: operator's config that describes nothing.
DERIV_FIRST_SIGHT = "first_sight"        # register, on first appearance
DERIV_EQP_LOG = "eqp_log"                # params_actual - the utterance
DERIV_RECIPE_SETPOINT = "recipe_setpoint"  # params_setpoint - the class-3 fallback
DERIV_RECIPE_BOOK = "recipe_book"        # has_param - the recipe sheet
#: `transfer_log` - a chip movement as the handling system uttered it (§2-bis). It is an
#: UTTERANCE, not a convention, so it resolves at class 2; it is listed here because the
#: gate refused the whole molecule when it was not, which is the check working.
DERIV_TRANSFER_LOG = "transfer_log"
DECLARED_DERIVATIONS = frozenset({DERIV_FIRST_SIGHT, DERIV_EQP_LOG,
                                  DERIV_RECIPE_SETPOINT, DERIV_RECIPE_BOOK,
                                  DERIV_TRANSFER_LOG})
DECLARED_SUBJECT_TYPES = frozenset({"Wafer", "Recipe"})

FORBIDDEN_DATABASES = ()   # the owner's box IS the target today; the flag below is the gate

CHUNK = 1000

# --------------------------------------------------------------------------
# The world: steps, recipes, equipment
# --------------------------------------------------------------------------

#: `step_family` is in the signature because mechanism-graph validity is scoped by family
#: (PHYSICS_ONTOLOGY_SETUP §2: "보이드 모델은 packaging 과에만"). One fab step is emitted
#: so a wafer's `processed_with` history actually crosses the fab/packaging line rather
#: than only claiming it can.
STEPS = {
    "DIFFUSION": {"family": "fab", "recipe": ("SYN-RCP-DIFF", "2"), "has_eqp_log": False},
    "BONDING":   {"family": "packaging", "recipe": None, "has_eqp_log": True},
    "MOLDING":   {"family": "packaging", "recipe": ("SYN-RCP-MOLD", "1"),
                  "has_eqp_log": True},
    # 🔴 DT IS NOT IN THE PER-BASE-WAFER LOOP, AND THAT IS THE WHOLE CORRECTION.
    # A first draft of this fixture put DT there, which models it as a step a wafer
    # PASSES THROUGH. It is not: some of a core wafer's dies are picked onto a DT slot
    # and the rest stay behind, and some of that slot is bonded while the rest stays as
    # inventory. That is a MOVEMENT, and movements are `transferred` events whose
    # existence IS the selection (§2-bis). This entry exists only so the DT run's
    # CONDITIONS have a recipe to name - see `dt_condition_atoms`, which is emitted
    # ALONGSIDE the movement events and never instead of them.
    "DT":        {"family": "packaging", "recipe": ("SYN-RCP-DT", "1"),
                  "has_eqp_log": False, "in_wafer_step_loop": False},
}

#: 🔴 THE VOID FACTOR. rev5 lowers bonding pressure, which is the mechanism graph's
#: `압력↓ → BLT↑ → void↑` path (PHYSICS_ONTOLOGY_SETUP §4) and S2's "+5 temp" diff.
#: Two parameters move and four do not, so a diff view has to separate signal from
#: noise instead of reporting "everything changed".
RECIPES = {
    ("SYN-RCP-BOND", "4"): {
        "pressure_MPa": (0.35, "MPa"), "temp_C": (145.0, "C"), "time_s": (12.0, "s"),
        "vacuum_Pa": (5.0, "Pa"), "purge_delay_s": (0, "s"),
        "vacuum_assist": (True, "bool"),
    },
    ("SYN-RCP-BOND", "5"): {
        "pressure_MPa": (0.22, "MPa"), "temp_C": (150.0, "C"), "time_s": (12.0, "s"),
        "vacuum_Pa": (5.0, "Pa"), "purge_delay_s": (0, "s"),
        "vacuum_assist": (True, "bool"),
    },
    ("SYN-RCP-MOLD", "1"): {
        "mold_temp_C": (175.0, "C"), "clamp_kN": (60.0, "kN"),
        "cure_s": (120.0, "s"), "transfer_mm_s": (4.5, "mm/s"),
    },
    ("SYN-RCP-DIFF", "2"): {
        "furnace_C": (1050.0, "C"), "ramp_C_min": (8.0, "C/min"),
        "dwell_min": (45.0, "min"), "o2_slm": (2.0, "slm"),
    },
    ("SYN-RCP-DT", "1"): {
        "pick_force_N": (0.8, "N"), "place_accuracy_um": (5.0, "um"),
        "uv_dose_mJ": (120.0, "mJ"), "stage_temp_C": (60.0, "C"),
    },
}

#: 🔴 EXPLICIT ORDER, AND IT IS APPEND-ONLY. Each recipe's `occurred_at` is derived from
#: its position here. It used to be derived from `sorted(RECIPES)`, which meant adding
#: `SYN-RCP-DT` would have slid `SYN-RCP-MOLD` from index 3 to 4 - a different timestamp,
#: a different `identity()` tuple, and every already-written MOLD atom would have been
#: RE-INSERTED as a duplicate instead of deduping on re-run. A sorted-order timestamp is
#: an idempotency bug that only fires the day somebody adds a member in the middle.
RECIPE_ORDER = (
    ("SYN-RCP-BOND", "4"), ("SYN-RCP-BOND", "5"),
    ("SYN-RCP-DIFF", "2"), ("SYN-RCP-MOLD", "1"),
    ("SYN-RCP-DT", "1"),                       # appended 2026-08-14; never inserted above
)

BOND_RECIPE_ID = "SYN-RCP-BOND"
BOND_REV_CAUSAL = "5"      # the planted one
BOND_REV_BASE = "4"

MOLD_EQPS = ("SYN-MLD-01", "SYN-MLD-02", "SYN-MLD-03", "SYN-MLD-04")
#: 🔴 THE DELAM FACTOR - a different axis entirely from the void factor, and assigned
#: INDEPENDENTLY of it, which is what makes "switch the kind, get the other factor" a
#: real question. If the two factors were correlated both kinds would surface both, and
#: a console that simply reported everything would pass.
MOLD_EQP_CAUSAL = "SYN-MLD-03"
DELAM_P_CAUSAL = 0.55
DELAM_P_BASE = 0.12

CHAMBERS = ("CH-A", "CH-B")
#: 🔴 THE DECOY WITH TEETH. 70% of everything sits in `CH-A`, so "5 of 6 findings share
#: chamber CH-A" is TRUE - and so is "5 of 6 clean packages share chamber CH-A". A view
#: that ranks by prevalence in the found population alone puts this at the top.
CHAMBER_SKEW = 0.70

DELAM_METHOD_KIND = "delam"     # which registry entry this generator fills
DELAM_INTERFACES = ("die-to-die", "die-to-substrate")
DELAM_UNIT = "um"
DELAM_SCANS_PER_WAFER = 12      # << 141 positions, so "never scanned" stays real

PROCESS_DAY = _dt.datetime(2026, 8, 10)      # processing precedes the 08-13 scans
TZ_OFFSET = "+09:00"


def _stamp(day_offset: int, minutes: int) -> _dt.datetime:
    """An aware instant. R5: never a naive stamp; the envelope refuses one anyway."""
    when = PROCESS_DAY + _dt.timedelta(days=day_offset, minutes=minutes)
    return _dt.datetime.fromisoformat(when.strftime("%Y-%m-%dT%H:%M:%S") + TZ_OFFSET)


def _stamp_text(day_offset: int, minutes: int) -> str:
    when = PROCESS_DAY + _dt.timedelta(days=day_offset, minutes=minutes)
    return when.strftime("%Y-%m-%dT%H:%M:%S") + TZ_OFFSET


def _h(*parts) -> int:
    """A stable hash. 🔴 NEVER `hash()` - it is salted per process for str, so a
    factor assignment built on it would change between the seeding run and the proving
    run and the answer key would be about a fixture that no longer exists."""
    material = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


# --------------------------------------------------------------------------
# Factor assignment
# --------------------------------------------------------------------------


def measured_void_rate(db):
    """`{base_wafer_id: (runs, dirty_runs)}` from the EXISTING fixture. Reads only.

    This is the outcome the void factor is assigned against. It is measured rather than
    assumed because the fixture it describes was written by another script on another
    day: assuming a rate here would make the answer key a claim about what that script
    was supposed to do rather than about what is in the database.
    """
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT r.base_wafer_id,
               count(*) AS runs,
               count(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM void_obs v WHERE v.run_uid = r.run_uid)) AS dirty
        FROM inspection_run r
        WHERE r.method = ANY(:methods) AND r.base_wafer_id LIKE :p
        GROUP BY 1
    """), {"methods": _void_methods(), "p": BASE_ID_PREFIX + "%"}).all()
    return {w: (int(n), int(d)) for w, n, d in rows}


def _void_methods():
    """The denominator methods for the DEFAULT kind - read from the registry.

    Not the literal `['sat']`: the registry is where a kind's methods live, and a second
    copy here is the hardcoding the brief forbids wearing a constant's costume.
    """
    from ledger_api import finding_kinds

    return finding_kinds.methods(finding_kinds.DEFAULT_KIND)


def assign_factors(void_rates, causal_top_fraction: float = 0.10):
    """`{wafer: factors}`. The one place the answer key is decided.

    The bonding REVISION is assigned from the measured void rate (see module docstring).
    Everything else is assigned from a hash of the wafer id, which is independent of that
    rate by construction - so every other factor is a DECOY, and the moulding equipment
    is free to drive the second kind without touching the first.
    """
    ranked = sorted(void_rates,
                    key=lambda w: (-(void_rates[w][1] / max(1, void_rates[w][0])), w))
    cut = max(1, int(round(len(ranked) * causal_top_fraction)))
    causal = set(ranked[:cut])

    factors = {}
    for wafer in void_rates:
        factors[wafer] = {
            # planted for kind `void`
            "bond_rev": BOND_REV_CAUSAL if wafer in causal else BOND_REV_BASE,
            # planted for kind `delam`, independent of the above
            "mold_eqp": MOLD_EQPS[_h("mold", wafer) % len(MOLD_EQPS)],
            # decoys
            "chamber": (CHAMBERS[0] if (_h("chamber", wafer) % 100) < CHAMBER_SKEW * 100
                        else CHAMBERS[1]),
            "has_eqp_log": (_h("eqplog", wafer) % 100) < 70,
        }
    return factors


def bond_eqp_by_wafer(db):
    """`{base_wafer_id: bond_eqp}` READ OUT of `bonding_log`, never invented.

    🔴 The bonding equipment is already a fact in this database. Asserting a different
    one in a `processed_with` atom would make the fixture self-contradictory, and every
    conclusion drawn on it would be about the contradiction rather than about the method.
    It is a decoy either way - `bond_eqp` is determined by the lot, which is independent
    of the void rate - so nothing is lost by telling the truth.
    """
    from sqlalchemy import text

    rows = db.execute(text(
        "SELECT base_id, min(bond_eqp) FROM bonding_log WHERE bond_lot LIKE :p "
        "GROUP BY 1"), {"p": BOND_LOT_PREFIX + "%"}).all()
    return {w: e for w, e in rows}


# --------------------------------------------------------------------------
# Atoms
# --------------------------------------------------------------------------


def _atom(subject_type, subject_keys, predicate, object_kind, payload, occurred_at,
          who, derivation, raw_ref, molecule_ref):
    from ledger.envelope import Atom

    return Atom(
        subject_type=subject_type, subject_keys=subject_keys, predicate=predicate,
        object_kind=object_kind, object_payload=payload, occurred_at=occurred_at,
        source_who=who,
        # The derivation rides in the provenance column the resolver already reads
        # (`ledger_trace.claim_basis`), so the rule behind an atom is queryable with
        # `LIKE '%#recipe_setpoint'` and the envelope does not grow a column.
        source_translator_ver=f"{TRANSLATOR_BASE}#{derivation}",
        source_raw_ref=raw_ref, derivation=derivation, molecule_ref=molecule_ref)


def recipe_atoms():
    """`register` + one `has_param` per setpoint, for every declared revision.

    A revision is a new SUBJECT (`rev` is key material), so rev4's parameters remain
    permanently assertable after rev5 lands - which is what makes "what did the wafers
    that ran under rev4 actually see" answerable a year later.
    """
    missing = set(RECIPES) ^ set(RECIPE_ORDER)
    if missing:
        raise SystemExit("REFUSED: RECIPE_ORDER and RECIPES disagree about %s. The order "
                         "decides each recipe's occurred_at, so a member in one and not "
                         "the other is an atom with no stamp or a stamp with no atom."
                         % sorted(missing))
    atoms = []
    for index, (recipe_id, rev) in enumerate(RECIPE_ORDER):
        params = RECIPES[(recipe_id, rev)]
        keys = {"recipe": recipe_id, "rev": rev}
        ref = f"recipe_book:{recipe_id}@{rev}"
        molecule = f"recipe:{recipe_id}:{rev}"
        when = _stamp(-3, index)
        atoms.append(_atom("Recipe", keys, "register", None, None, when,
                           WHO_RECIPE_BOOK, DERIV_FIRST_SIGHT, ref, molecule))
        for name, (value, unit) in sorted(params.items()):
            atoms.append(_atom(
                "Recipe", keys, "has_param", "value",
                {"param": name, "value": value, "unit": unit},
                when, WHO_RECIPE_BOOK, DERIV_RECIPE_BOOK, f"{ref}#{name}", molecule))
    return atoms


def _recipe_for(step: str, factors: dict):
    if step == "BONDING":
        return BOND_RECIPE_ID, factors["bond_rev"]
    return STEPS[step]["recipe"]


def _eqp_for(step: str, factors: dict, bond_eqp: str):
    if step == "BONDING":
        return bond_eqp
    if step == "MOLDING":
        return factors["mold_eqp"]
    return "SYN-DIF-01"


def _actual_from_setpoint(setpoints: dict, wafer: str, step: str):
    """`params_actual` - the setpoints with equipment-scale scatter, deterministic.

    Scatter matters: if the measurement were identical to the setpoint, the fixture could
    not tell a console that reads the measurement from one that reads the recipe, and
    "measured beats setpoint" would be untestable on the very data built to test it.
    """
    actual = {}
    for name, (value, _unit) in setpoints.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            actual[name] = value
            continue
        jitter = ((_h(wafer, step, name) % 2001) - 1000) / 1000.0    # -1.0 .. +1.0
        actual[name] = round(float(value) * (1.0 + 0.04 * jitter), 4)
    return actual


def wafer_atoms(wafer: str, index: int, factors: dict, bond_eqp: str):
    """Every atom about ONE wafer, in the order they must be WRITTEN.

    🔴 ORDER IS PART OF THE FIXTURE. The setpoint atom is emitted before the measured
    one so that `insert_atoms` mints it a lower uuid7 - rank level 3 then favours the
    setpoint, as level 2b already does (its `occurred_at` is later). Only the class can
    make the measurement win, which is the property `--prove`'s mutant checks.
    """
    atoms = [_atom("Wafer", {"wafer": wafer}, "register", None, None,
                   _stamp(0, index % 1440), WHO_EQP_LOG, DERIV_FIRST_SIGHT,
                   f"wafer_registry:{wafer}", f"wafer:{wafer}")]

    for step_no, step in enumerate(("DIFFUSION", "BONDING", "MOLDING")):
        recipe_id, rev = _recipe_for(step, factors)
        setpoints = RECIPES[(recipe_id, rev)]
        eqp = _eqp_for(step, factors, bond_eqp)
        molecule = f"wafer:{wafer}:{step}"
        common = {
            "step": step, "step_family": STEPS[step]["family"], "eqp": eqp,
            "chamber": factors["chamber"],
            "recipe": {"id": recipe_id, "rev": rev},
        }
        # --- the class-3 FALLBACK, written first and dated later (see docstring)
        fallback = dict(common)
        fallback["params_setpoint"] = {n: v for n, (v, _u) in sorted(setpoints.items())}
        # 🔴 `inferred` is `DEFAULT_RESOLVER_CONFIG["inference_payload_flag"]`. Design §3
        # puts confidence INSIDE the payload, so this is the existing mechanism and not a
        # new one; nothing in `ledger_trace` was touched to make this rank at class 3.
        fallback["inferred"] = True
        fallback["basis"] = DERIV_RECIPE_SETPOINT
        atoms.append(_atom(
            "Wafer", {"wafer": wafer}, "processed_with", "value", fallback,
            _stamp(2, step_no * 60 + (index % 60)), WHO_RECIPE_BOOK,
            DERIV_RECIPE_SETPOINT, f"recipe_book:{recipe_id}@{rev}:{wafer}", molecule))

        # --- the class-2 OBSERVATION, only where an equipment log exists
        if STEPS[step]["has_eqp_log"] and factors["has_eqp_log"]:
            measured = dict(common)
            measured["params_actual"] = _actual_from_setpoint(setpoints, wafer, step)
            atoms.append(_atom(
                "Wafer", {"wafer": wafer}, "processed_with", "value", measured,
                _stamp(0, step_no * 60 + (index % 60)), WHO_EQP_LOG, DERIV_EQP_LOG,
                f"eqp_log:{eqp}:{wafer}:{step}", molecule))
    return atoms


# --------------------------------------------------------------------------
# `transferred` - the chip movement axis (PHYSICS_ONTOLOGY_SETUP §2-bis)
# --------------------------------------------------------------------------

#: Container KINDS a chip can sit in. `from`/`to` name one of these, never a step name -
#: the walk joins on POSITION, so the container is the thing that has to be comparable.
PLACE_WAFER_GRID = "wafer_grid"
PLACE_DT_SLOT = "dt_slot"
PLACE_PACKAGE_GATE = "package_gate"

#: The staging DT lot a re-transferred population passes through. 🔴 ITS ONLY PURPOSE IS
#: TO MAKE THE CHAIN LONGER THAN ONE HOP, and that is not decoration - see
#: `prove_transfer_chain`. A fixture where DT always happens once cannot tell a
#: position-continuity walk from a step-name walk, because both give the same answer.
STAGING_DT_PREFIX = "SYN-DTX-"
DOUBLE_DT_FRACTION = 0.10

DERIV_TRANSFER = DERIV_TRANSFER_LOG


def place(kind: str, keys: dict, position=None) -> dict:
    """One end of a movement. 🔴 ONE constructor, because continuity is EQUALITY.

    Event N's `to` has to compare equal to event N+1's `from` or the chain breaks, and
    two hand-built dicts that differ by a key order, a missing `position`, or an int
    where the other has a str are a chain that silently stops. Building both ends through
    one function is what makes "the same place" the same value.
    """
    return {"type": kind, "keys": dict(keys), "position": position}


def dt_transfer_facts(db):
    """MEASURED movement: `{(dt_lot, dt_slot): {base_wafer: dies}}` from `bonding_log`.

    The consumption side is not invented. Every die this fixture bonded already records
    which DT lot and slot it came from, so "how many dies went from DT slot S into base
    wafer B" is a count over rows that exist. Only the LOAD side is planted, because
    nothing in this database says how many dies were picked onto a DT slot in the first
    place - and that gap is exactly what the selection model is for.
    """
    from sqlalchemy import text

    rows = db.execute(text(
        "SELECT dt_lot, dt_slot, base_id, count(*) FROM bonding_log "
        "WHERE bond_lot LIKE :p GROUP BY 1, 2, 3"), {"p": BOND_LOT_PREFIX + "%"}).all()
    facts = {}
    for dt_lot, dt_slot, base_id, dies in rows:
        facts.setdefault((dt_lot, dt_slot), {})[base_id] = int(dies)
    return facts


def transfer_atoms(facts, double_fraction: float = DOUBLE_DT_FRACTION):
    """The chip movement chain per (dt_lot, dt_slot). Returns `(atoms, stats)`.

    🔴 SELECTION IS THE EVENT'S CONTENT, NOT A SEPARATE CLAIM (§2-bis). A wafer does not
    "pass through" DT: some of its dies are picked and the rest stay behind, and the way
    that is said is that a transfer event exists for what moved and does not exist for
    what did not. `qty` carries how many, so residual is a FOLD - inflow minus outflow per
    container - rather than a stored number that can disagree with its own inputs.

    🔴 AND SOME CHAINS ARE THREE HOPS LONG, DELIBERATELY. A tenth of the DT slots are fed
    through a STAGING lot first, so the population reaches its recorded slot by
    wafer -> DTX -> DT -> package. Every hop is the same predicate and the walk joins
    `to` to `from`; nothing anywhere counts hops.
    """
    atoms, stats = [], {"load": 0, "restage": 0, "consume": 0, "chains_3hop": 0,
                        "chains_2hop": 0, "core_wafers": 0}

    for pair_index, ((dt_lot, dt_slot), consumers) in enumerate(sorted(facts.items())):
        consumed_total = sum(consumers.values())
        core_wafer = "SYN-CW-%s-%s" % (dt_lot.replace("SYN-DT-", ""), dt_slot)
        molecule = "transfer:%s:%s" % (dt_lot, dt_slot)

        # The load is PARTIAL in both directions and both numbers are planted, because
        # nothing on disk says either one. Residual stays positive by construction: a DT
        # slot that was emptied exactly would make "잔량" untestable on every row.
        residual = 6 + (_h("residual", dt_lot, dt_slot) % 25)
        loaded = consumed_total + residual
        wafer_die_population = loaded + 40 + (_h("skipped", dt_lot, dt_slot) % 120)

        recorded_slot = place(PLACE_DT_SLOT, {"dt_lot": dt_lot, "dt_slot": dt_slot})
        origin = place(PLACE_WAFER_GRID, {"wafer": core_wafer})

        atoms.append(_atom("Wafer", {"wafer": core_wafer}, "register", None, None,
                           _stamp(-2, pair_index % 1440), WHO_EQP_LOG,
                           DERIV_FIRST_SIGHT, "core_wafer_registry:%s" % core_wafer,
                           molecule))
        stats["core_wafers"] += 1

        double = (_h("double", dt_lot, dt_slot) % 1000) < double_fraction * 1000
        if double:
            staging = place(PLACE_DT_SLOT,
                            {"dt_lot": STAGING_DT_PREFIX + dt_lot.replace("SYN-DT-", ""),
                             "dt_slot": dt_slot})
            hops = [(origin, staging, loaded, -1, "pick"),
                    (staging, recorded_slot, loaded, 0, "restage")]
            stats["chains_3hop"] += 1
        else:
            hops = [(origin, recorded_slot, loaded, -1, "pick")]
            stats["chains_2hop"] += 1

        for source, target, qty, day, label in hops:
            payload = {"from": source, "to": target, "qty": qty}
            if label == "pick":
                # What the selection COST, so a reader can see it was a selection:
                # the wafer held this many dies and this many were taken.
                payload["source_population"] = wafer_die_population
            atoms.append(_atom(
                "Wafer", {"wafer": core_wafer}, "transferred", "value", payload,
                _stamp(day, pair_index % 720), WHO_EQP_LOG, DERIV_TRANSFER,
                "transfer_log:%s:%s:%s" % (dt_lot, dt_slot, label), molecule))
            stats["load" if label == "pick" else "restage"] += 1

        # Consumption: one event per bonding pick out of this slot. The `from` is the
        # SAME value the previous hop's `to` was, by construction, so continuity holds.
        for consumer_index, (base_wafer, dies) in enumerate(sorted(consumers.items())):
            atoms.append(_atom(
                "Wafer", {"wafer": core_wafer}, "transferred", "value",
                {"from": recorded_slot,
                 "to": place(PLACE_PACKAGE_GATE, {"base_wafer": base_wafer}),
                 "qty": dies},
                _stamp(1, (pair_index + consumer_index) % 1440), WHO_EQP_LOG,
                DERIV_TRANSFER,
                "transfer_log:%s:%s:bond:%s" % (dt_lot, dt_slot, base_wafer),
                molecule))
            stats["consume"] += 1

    return atoms, stats


def dt_condition_atoms(facts):
    """`processed_with` for the DT RUN's conditions - alongside, never instead (§2-bis).

    The movement and the conditions are two different claims about one run, so they are
    two different predicates about the same subject. Collapsing them would make "what
    were the pick conditions" unanswerable without parsing a movement event.
    """
    recipe_id, rev = STEPS["DT"]["recipe"]
    setpoints = RECIPES[(recipe_id, rev)]
    atoms = []
    for index, (dt_lot, dt_slot) in enumerate(sorted(facts)):
        core_wafer = "SYN-CW-%s-%s" % (dt_lot.replace("SYN-DT-", ""), dt_slot)
        atoms.append(_atom(
            "Wafer", {"wafer": core_wafer}, "processed_with", "value",
            {"step": "DT", "step_family": STEPS["DT"]["family"],
             "eqp": "SYN-DTQ-%02d" % (1 + (_h("dtq", dt_lot, dt_slot) % 3)),
             "recipe": {"id": recipe_id, "rev": rev},
             "job": "SYN-DTJOB-%s-%s" % (dt_lot, dt_slot),
             "params_setpoint": {n: v for n, (v, _u) in sorted(setpoints.items())},
             "inferred": True, "basis": DERIV_RECIPE_SETPOINT},
            _stamp(2, 180 + index % 60), WHO_RECIPE_BOOK, DERIV_RECIPE_SETPOINT,
            "recipe_book:%s@%s:%s" % (recipe_id, rev, core_wafer),
            "transfer:%s:%s" % (dt_lot, dt_slot)))
    return atoms


def prove_transfer_chain(db, sample: int = 400):
    """Walk `void -> package -> DT slot -> core wafer` BY POSITION, and score the mutant.

    🔴 THE MUTANT IS THE POINT. A walk that joins on the STEP NAME and a walk that joins
    on POSITION CONTINUITY give the SAME answer on every chain where DT happens once - so
    a fixture with only 2-hop chains proves nothing about either. This runs both walks
    and requires them to DISAGREE on the 3-hop chains: the step-name walk stops at the
    staging lot (or jumps over it), the position walk reaches the core wafer.
    """
    import json as _json

    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT subject_keys->>'wafer', object_payload, occurred_at, id
        FROM ledger_events
        WHERE predicate = 'transferred'
    """)).all()

    # index by `from` and by `to`, as the walk itself would
    by_to, by_from = {}, {}
    for wafer, payload, occurred_at, atom_id in rows:
        key_to = _json.dumps(payload["to"], sort_keys=True)
        key_from = _json.dumps(payload["from"], sort_keys=True)
        by_to.setdefault(key_to, []).append((wafer, payload, occurred_at, atom_id))
        by_from.setdefault(key_from, []).append((wafer, payload, occurred_at, atom_id))

    packages = [k for k in by_to if '"package_gate"' in k]
    walked = reached_core = hops_3 = hops_2 = 0
    step_name_walk_wrong = 0

    for key in sorted(packages)[:sample]:
        walked += 1
        # BACKWARD walk: from the package, keep asking "which event ended where this one
        # began?" until nothing does. NOTHING HERE COUNTS HOPS.
        current = by_to[key][0]
        depth = 0
        while True:
            previous = by_to.get(_json.dumps(current[1]["from"], sort_keys=True))
            if not previous:
                break
            current = min(previous, key=lambda e: (e[2], str(e[3])))
            depth += 1
            if depth > 20:               # a cycle guard, never a hop count
                break
        origin = current[1]["from"]
        if origin.get("type") == PLACE_WAFER_GRID:
            reached_core += 1
        if depth >= 2:
            hops_3 += 1
            # The MUTANT: a walk that assumed "DT happens once" would take exactly one
            # step back from the package and call whatever it landed on the origin.
            one_step = by_to[key][0][1]["from"]
            if one_step.get("type") != PLACE_WAFER_GRID:
                step_name_walk_wrong += 1
        else:
            hops_2 += 1

    return {"packages_walked": walked, "reached_core_wafer": reached_core,
            "chains_with_extra_dt_hop": hops_3, "chains_with_one_dt_hop": hops_2,
            "single_hop_assumption_would_be_wrong_on": step_name_walk_wrong}


def prove_residual_is_a_fold(db, limit: int = 5):
    """Residual per container = inflow - outflow, computed from events only.

    Never a stored number: a stored residual can disagree with the events it summarises,
    and then nobody can tell which is wrong.
    """
    from sqlalchemy import text

    rows = db.execute(text("""
        WITH ev AS (
            SELECT object_payload->'to'   AS dst,
                   object_payload->'from' AS src,
                   (object_payload->>'qty')::numeric AS qty
            FROM ledger_events WHERE predicate = 'transferred'
        ),
        inflow  AS (SELECT dst AS box, sum(qty) q FROM ev
                    WHERE dst->>'type' = :slot GROUP BY 1),
        outflow AS (SELECT src AS box, sum(qty) q FROM ev
                    WHERE src->>'type' = :slot GROUP BY 1)
        SELECT coalesce(i.box, o.box) AS box,
               coalesce(i.q, 0) AS loaded, coalesce(o.q, 0) AS shipped,
               coalesce(i.q, 0) - coalesce(o.q, 0) AS residual
        FROM inflow i FULL JOIN outflow o ON o.box = i.box
        ORDER BY residual DESC NULLS LAST
    """), {"slot": PLACE_DT_SLOT}).mappings().all()
    negative = [r for r in rows if r["residual"] is not None and r["residual"] < 0]
    return {"containers": len(rows), "sample": [dict(r) for r in rows[:limit]],
            "negative_residual_containers": len(negative)}


# --------------------------------------------------------------------------
# The second finding kind - generated FROM the factor, not assigned to it
# --------------------------------------------------------------------------


def delam_rows(wafer: str, positions, factors: dict, index: int):
    """`(runs, findings)` for one wafer's `scat` scans.

    The outcome is drawn from the moulding equipment, so this association runs
    factor -> outcome. `void`'s runs the other way (outcome -> factor, because the voids
    were already on disk and this script is add-only). One of each is deliberate.
    """
    from ledger_api import finding_kinds

    method = finding_kinds.methods(DELAM_METHOD_KIND)[0]
    p_dirty = (DELAM_P_CAUSAL if factors["mold_eqp"] == MOLD_EQP_CAUSAL
               else DELAM_P_BASE)
    runs, findings = [], []
    for n, (bx, by, stack_height) in enumerate(positions):
        gate = 1 + (_h("gate", wafer, bx, by) % max(1, int(stack_height)))
        observed_at = _stamp_text(3, index % 1200 + n * 3)
        run = {"method": method, "base_wafer_id": wafer, "base_x": bx, "base_y": by,
               "stack_gate": gate,
               "recipe_id": "SYN_DELAM_R1", "eqp_id": "SYN-SCAT-%02d" % (1 + n % 3),
               "observed_at": observed_at}
        run_uid = _business_key("inspection_run", run)
        if run_uid is None:
            raise SystemExit("REFUSED: could not key a scat run for %s (%s, %s)."
                             % (wafer, bx, by))
        runs.append(run)
        if (_h("dirty", wafer, bx, by) % 10000) / 10000.0 >= p_dirty:
            continue                      # a CLEAN scan - the denominator's whole point
        seen = set()
        for k in range(1 + (_h("count", wafer, bx, by) % 2)):
            ix = 50.0 + (_h("ix", wafer, bx, by, k) % 39800) / 4.0
            iy = 50.0 + (_h("iy", wafer, bx, by, k) % 39800) / 4.0
            if (ix, iy) in seen:
                continue
            seen.add((ix, iy))
            findings.append({
                "run_uid": run_uid, "base_wafer_id": wafer, "base_x": bx, "base_y": by,
                "stack_gate": gate, "inchip_x": ix, "inchip_y": iy,
                "extent_x": round(1.0 + (_h("ex", wafer, bx, by, k) % 4000) / 100.0, 2),
                "extent_y": round(1.0 + (_h("ey", wafer, bx, by, k) % 4000) / 100.0, 2),
                "interface": DELAM_INTERFACES[_h("if", wafer, bx, by, k) % 2],
                "unit": DELAM_UNIT,
            })
    return runs, findings


def _business_key(table: str, row: dict):
    """The key `crud` itself would compute. Borrowed, never re-joined - the rule
    `void_sat_format.compose_business_key` states, and this calls that very function so
    there is not even a second call site's worth of drift."""
    from parsers import void_sat_format

    return void_sat_format.compose_business_key(table, row)


def scan_positions(db, per_wafer: int):
    """`{wafer: [(bx, by, stack_height)]}` - the positions `scat` will look at.

    A STRIDED subset, so most bonded positions stay never-scanned for this kind and the
    third population is real rather than nominal.
    """
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT base_id, bx, by, stack_height,
               row_number() OVER (PARTITION BY base_id ORDER BY bx, by) AS rn,
               count(*)     OVER (PARTITION BY base_id)                 AS total
        FROM bonding_log WHERE bond_lot LIKE :p
    """), {"p": BOND_LOT_PREFIX + "%"}).all()
    by_wafer = {}
    for base_id, bx, by, stack_height, rn, total in rows:
        stride = max(1, int(total) // max(1, per_wafer))
        if (int(rn) - 1) % stride:
            continue
        bucket = by_wafer.setdefault(base_id, [])
        if len(bucket) < per_wafer:
            bucket.append((int(bx), int(by), int(stack_height or 1)))
    return by_wafer


# --------------------------------------------------------------------------
# Writing - through the SAME gate and the SAME store
# --------------------------------------------------------------------------


def screen_all(atoms):
    """Every molecule through `gate.screen_molecule`, inside `building_molecule`.

    A fixture that bypassed the gate would be a fixture the production path would refuse,
    which is the same defect `seed_syn_void_base_join.screened` exists to prevent one
    layer down. Grouped by `molecule_ref` because that is the transaction unit the gate
    judges all-or-nothing.
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
                "(%s: %s). This is a bug in this script, not in the gate." %
                (refusal.reason, refusal.detail))
    return kept


def write_atoms(atoms, batch_size: int = 2000) -> dict:
    """Through `LedgerStore.write_batch` - same store, same transaction discipline."""
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


def _batch(rows):
    from database import schemas

    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=row, source_name=SOURCE_NAME,
                                           updated_by=UPDATED_BY) for row in rows],
        replace_map=False, scope=None)


def write_rows(db, table: str, rows: list) -> int:
    """Chunked upsert with the dropped-cell check `seed_syn_void_base_join` documents."""
    from database import crud

    written = 0
    for start in range(0, len(rows), CHUNK):
        report = {}
        _, changed, _, _ = crud.apply_batch_updates(
            db, table, _batch(rows[start:start + CHUNK]), drop_report=report)
        if report.get("dropped_cells"):
            raise SystemExit(
                "REFUSED: writing '%s' DROPPED %d update cell(s), column(s) %s - the "
                "columns are not declared in table_config.json. A dropped key lands as a "
                "200 with nothing written."
                % (table, report["dropped_cells"], sorted(report.get("by_column") or {})))
        written += len(changed or ())
        db.commit()
    return written


def ensure_tables(db):
    """Create any table declared in config that the database does not have yet.

    `create_missing_dynamic_tables` is the CREATE path (information_schema-gated,
    checkfirst); `sync_dynamic_tables_schema` is ALTER-only and would skip a new table
    entirely - the server-pm lessons file records that trap by name.
    """
    from database import crud, models
    from database.database import engine

    models.init_dynamic_models(crud.TABLE_CONFIG)
    models.create_missing_dynamic_tables(engine)


def guard_database(db, allow_owner: bool, writing: bool = True) -> str:
    """Refuse the owner's database unless the owner said so. Only when WRITING.

    A dry run and `--prove` read; refusing them would make the answer key unreadable on
    the only box that holds the fixture, and a guard that blocks reading teaches people
    to pass the override flag by reflex - which is how the flag stops meaning anything.
    """
    from sqlalchemy import text

    name = db.execute(text("SELECT current_database()")).scalar()
    if writing and name == "assy_manager" and not allow_owner:
        raise SystemExit(
            "REFUSED: connected to 'assy_manager', the owner's working database. Pass "
            "--i-accept-writing-to-owner-database if the owner has decided otherwise.")
    print("database: %s" % name)
    print("!! rollback (ledger): DELETE FROM ledger_events WHERE "
          "source_translator_ver LIKE '%s%%'" % (TRANSLATOR_BASE.split("rules:")[0]))
    print("!! rollback (rdb):    DELETE FROM cell_sources WHERE updated_by = '%s'"
          % UPDATED_BY)
    return name


# --------------------------------------------------------------------------
# THE ANSWER KEY
# --------------------------------------------------------------------------


def resolved_factors(db):
    """`{wafer: {field: value}}` - the WINNING `processed_with` claim per (wafer, step).

    🔴 Resolution runs through `ledger_trace.claim_rank_key`, the real resolver, not a
    re-implementation. That is the point of the exercise: if the answer key ranked claims
    with its own rule it would be scoring the console against a second opinion, and
    "measured beats setpoint" would be true of the answer key rather than of the system.
    """
    import ledger_trace as lt
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT id, subject_type, subject_keys, predicate, object_kind, object_payload,
               occurred_at, source_who, source_translator_ver, source_raw_ref
        FROM ledger_events
        WHERE predicate = 'processed_with' AND subject_type = 'Wafer'
    """)).all()

    by_key = {}
    for row in rows:
        claim = lt.Claim(id=str(row[0]), subject_type=row[1], subject_keys=row[2],
                         predicate=row[3], object_kind=row[4], object_payload=row[5],
                         occurred_at=row[6], source_who=row[7],
                         source_translator_ver=row[8], source_raw_ref=row[9])
        payload = claim.object_payload or {}
        key = ((claim.subject_keys or {}).get("wafer"), payload.get("step"))
        by_key.setdefault(key, []).append(claim)

    winners = {}
    cfg = lt.load_resolver_config()
    for (wafer, step), claims in by_key.items():
        best = min(claims, key=lambda c: lt.claim_rank_key(c, cfg))
        payload = best.object_payload or {}
        bucket = winners.setdefault(wafer, {})
        bucket["step:%s" % step] = step
        bucket["eqp@%s" % step] = payload.get("eqp")
        bucket["chamber@%s" % step] = payload.get("chamber")
        recipe = payload.get("recipe") or {}
        bucket["recipe@%s" % step] = recipe.get("id")
        bucket["recipe_rev@%s" % step] = "%s@%s" % (recipe.get("id"), recipe.get("rev"))
        bucket["_class@%s" % step] = lt.CLASS_NAMES.get(lt.claim_class(best, cfg))
    return winners


def population_by_wafer(db, kind: str):
    """`{wafer: (found, clean, unscanned)}` PACKAGE counts for one kind.

    Uses `finding_kinds.population_ctes` so the three-way split has ONE spelling. The
    clean set is `scanned MINUS found`; a never-scanned package cannot reach it.
    """
    from ledger_api import finding_kinds
    from sqlalchemy import text

    ctes = finding_kinds.population_ctes(kind)
    sql = f"""
WITH {ctes},
found_n     AS (SELECT base_wafer_id AS w, count(*) n FROM kind_found     GROUP BY 1),
clean_n     AS (SELECT base_wafer_id AS w, count(*) n FROM kind_clean     GROUP BY 1),
unscanned_n AS (SELECT base_id       AS w, count(*) n FROM kind_unscanned GROUP BY 1)
SELECT coalesce(f.w, c.w, u.w) AS wafer,
       coalesce(f.n, 0), coalesce(c.n, 0), coalesce(u.n, 0)
FROM found_n f
FULL JOIN clean_n c ON c.w = f.w
FULL JOIN unscanned_n u ON u.w = coalesce(f.w, c.w)
"""
    rows = db.execute(text(sql),
                      {"methods": finding_kinds.methods(kind)}).all()
    return {w: (int(a), int(b), int(c)) for w, a, b, c in rows}


def contrast(db, kind: str, factors_by_wafer=None):
    """The case-control contrast for ONE kind. No kind name appears in this function.

    Returns `{factor_value: {"cases", "controls", "p_case", "p_control", "ratio"}}` plus
    the three population totals. Both denominators travel with every rate, because a
    prevalence without one is the number this project bans from the screen.
    """
    factors_by_wafer = factors_by_wafer or resolved_factors(db)
    population = population_by_wafer(db, kind)

    cases = controls = unscanned = 0
    tally = {}
    for wafer, (found, clean, never) in population.items():
        cases += found
        controls += clean
        unscanned += never
        for field, value in (factors_by_wafer.get(wafer) or {}).items():
            if field.startswith("_") or value is None:
                continue
            entry = tally.setdefault("%s=%s" % (field, value),
                                     {"cases": 0, "controls": 0})
            entry["cases"] += found
            entry["controls"] += clean

    for entry in tally.values():
        entry["p_case"] = entry["cases"] / cases if cases else None
        entry["p_control"] = entry["controls"] / controls if controls else None
        entry["ratio"] = (entry["p_case"] / entry["p_control"]
                          if entry["p_control"] else None)
    return {"kind": kind, "cases": cases, "controls": controls,
            "unscanned": unscanned, "factors": tally}


#: 🔴 THE ANSWER KEY ITSELF. What was planted, per kind, and what must NOT come out.
#: Data, so that a consumer (a test, the console's acceptance run) reads the same table
#: this generator planted from - a second copy is a second opinion.
ANSWER_KEY = {
    "void": {
        "planted": "recipe_rev@BONDING=%s@%s" % (BOND_RECIPE_ID, BOND_REV_CAUSAL),
        "min_ratio": 1.5,
        "decoys_max_ratio": 1.2,
        "decoys": ["step:BONDING=BONDING",
                   "recipe@BONDING=%s" % BOND_RECIPE_ID,
                   "chamber@BONDING=%s" % CHAMBERS[0],
                   "recipe_rev@MOLDING=SYN-RCP-MOLD@1",
                   "eqp@MOLDING=%s" % MOLD_EQP_CAUSAL],   # the OTHER kind's factor
    },
    "delam": {
        "planted": "eqp@MOLDING=%s" % MOLD_EQP_CAUSAL,
        "min_ratio": 2.0,
        "decoys_max_ratio": 1.2,
        "decoys": ["step:MOLDING=MOLDING",
                   "chamber@BONDING=%s" % CHAMBERS[0],
                   "recipe_rev@MOLDING=SYN-RCP-MOLD@1",
                   "recipe_rev@BONDING=%s@%s" % (BOND_RECIPE_ID, BOND_REV_CAUSAL)],
    },
}


def prove(db, kind: str):
    """Assert the answer key for one kind, in BOTH directions. Returns a report dict."""
    key = ANSWER_KEY.get(kind)
    if key is None:
        raise SystemExit("no answer key declared for finding kind %r" % kind)
    result = contrast(db, kind)
    tally = result["factors"]
    failures = []

    planted = tally.get(key["planted"])
    if planted is None:
        failures.append("PLANTED FACTOR %s is not present in the contrast at all"
                        % key["planted"])
    elif not planted["ratio"] or planted["ratio"] < key["min_ratio"]:
        failures.append("PLANTED FACTOR %s ratio %s < required %s"
                        % (key["planted"], planted["ratio"], key["min_ratio"]))

    for decoy in key["decoys"]:
        entry = tally.get(decoy)
        if entry is None:
            continue                       # absent is stronger than not-enriched
        if entry["ratio"] and entry["ratio"] > key["decoys_max_ratio"]:
            failures.append("DECOY %s came out enriched (ratio %.3f > %.2f)"
                            % (decoy, entry["ratio"], key["decoys_max_ratio"]))
    result["failures"] = failures
    result["planted"] = key["planted"]
    result["planted_entry"] = planted
    result["decoy_entries"] = {d: tally.get(d) for d in key["decoys"]}
    return result


def prove_class_decides(db, sample: int = 200):
    """«Measured beats setpoint», and the MUTANT that shows the fixture can tell.

    🔴 A green here means nothing on its own: if the two atoms agreed on every ranking
    level, a resolver with the class boundary REMOVED would give the same answer and the
    assertion would be about arithmetic rather than about the class. So the mutant is run
    too, and it must DISAGREE - on every wafer that has both flavours.
    """
    import ledger_trace as lt
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT id, subject_type, subject_keys, predicate, object_kind, object_payload,
               occurred_at, source_who, source_translator_ver, source_raw_ref
        FROM ledger_events
        WHERE predicate = 'processed_with' AND object_payload->>'step' = 'BONDING'
    """)).all()
    claims = {}
    for row in rows:
        claim = lt.Claim(id=str(row[0]), subject_type=row[1], subject_keys=row[2],
                         predicate=row[3], object_kind=row[4], object_payload=row[5],
                         occurred_at=row[6], source_who=row[7],
                         source_translator_ver=row[8], source_raw_ref=row[9])
        claims.setdefault((claim.subject_keys or {}).get("wafer"), []).append(claim)

    cfg = lt.load_resolver_config()

    def class_blind(claim):
        return lt.claim_rank_key(claim, cfg)[1:]     # the tuple WITHOUT the class level

    both = measured_wins = mutant_disagrees = 0
    for _wafer, members in list(claims.items())[:sample]:
        if len(members) < 2:
            continue
        both += 1
        winner = min(members, key=lambda c: lt.claim_rank_key(c, cfg))
        mutant = min(members, key=class_blind)
        if "params_actual" in (winner.object_payload or {}):
            measured_wins += 1
        if mutant.id != winner.id:
            mutant_disagrees += 1
    return {"wafers_with_both": both, "measured_wins": measured_wins,
            "mutant_disagrees": mutant_disagrees}


# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--prove", action="store_true")
    parser.add_argument("--finding", default=None,
                        help="finding kind to prove; default = every declared kind")
    parser.add_argument("--wafers", type=int, default=0,
                        help="cap the wafer count (0 = every fixture wafer)")
    parser.add_argument("--scans-per-wafer", type=int, default=DELAM_SCANS_PER_WAFER)
    parser.add_argument("--causal-top-fraction", type=float, default=0.10)
    parser.add_argument("--double-dt-fraction", type=float, default=DOUBLE_DT_FRACTION,
                        help="share of DT slots reached via a SECOND dt slot. 🔴 zero "
                             "makes every chain one hop, and then a position-continuity "
                             "walk and a step-name walk cannot be told apart")
    parser.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                        dest="allow_owner")
    args = parser.parse_args()

    from database import crud, models
    from database.database import SessionLocal

    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        guard_database(db, args.allow_owner, writing=args.apply)

        if args.prove and not args.apply:
            from ledger_api import finding_kinds

            for kind in ([args.finding] if args.finding else finding_kinds.kinds()):
                report = prove(db, kind)
                print("\n=== ANSWER KEY :: finding=%s ===" % kind)
                print("populations: found=%d  clean-scanned=%d  never-scanned=%d"
                      % (report["cases"], report["controls"], report["unscanned"]))
                entry = report["planted_entry"]
                if entry:
                    print("PLANTED  %-40s cases %6d/%d (%.3f)  controls %6d/%d (%.3f)"
                          "  ratio %.3f"
                          % (report["planted"], entry["cases"], report["cases"],
                             entry["p_case"], entry["controls"], report["controls"],
                             entry["p_control"], entry["ratio"]))
                for name, dec in sorted(report["decoy_entries"].items()):
                    if dec is None:
                        print("DECOY    %-40s absent from this population" % name)
                        continue
                    print("DECOY    %-40s cases %6d/%d (%.3f)  controls %6d/%d (%.3f)"
                          "  ratio %.3f"
                          % (name, dec["cases"], report["cases"], dec["p_case"],
                             dec["controls"], report["controls"], dec["p_control"],
                             dec["ratio"] or 0.0))
                print("VERDICT: %s" % ("PASS" if not report["failures"]
                                       else "FAIL -> " + " | ".join(report["failures"])))
            klass = prove_class_decides(db)
            print("\n=== MEASURED BEATS SETPOINT (class 2 > class 3) ===")
            print("wafers carrying both flavours: %d | measured won: %d | "
                  "class-blind mutant disagreed: %d"
                  % (klass["wafers_with_both"], klass["measured_wins"],
                     klass["mutant_disagrees"]))
            print("VERDICT: %s" % (
                "PASS" if klass["wafers_with_both"]
                and klass["measured_wins"] == klass["wafers_with_both"]
                and klass["mutant_disagrees"] == klass["wafers_with_both"]
                else "FAIL - the fixture cannot tell the class apart from the tiebreaks"))

            chain = prove_transfer_chain(db)
            print("\n=== TRANSFER CHAIN :: package -> DT slot(s) -> core wafer ===")
            print("packages walked: %d | reached the core wafer: %d"
                  % (chain["packages_walked"], chain["reached_core_wafer"]))
            print("chains passing TWO dt slots: %d | one dt slot: %d"
                  % (chain["chains_with_extra_dt_hop"],
                     chain["chains_with_one_dt_hop"]))
            print("a 'DT happens once' join would be WRONG on: %d of them"
                  % chain["single_hop_assumption_would_be_wrong_on"])
            print("VERDICT: %s" % (
                "PASS" if chain["packages_walked"]
                and chain["reached_core_wafer"] == chain["packages_walked"]
                and chain["chains_with_extra_dt_hop"] > 0
                and chain["single_hop_assumption_would_be_wrong_on"]
                == chain["chains_with_extra_dt_hop"]
                else "FAIL - either the walk does not reach the core wafer, or every "
                     "chain is one hop and the fixture cannot tell a position walk from "
                     "a step-name walk"))

            fold = prove_residual_is_a_fold(db)
            print("\n=== RESIDUAL IS A FOLD (inflow - outflow), never a stored number ===")
            print("dt slot containers: %d | containers with NEGATIVE residual: %d"
                  % (fold["containers"], fold["negative_residual_containers"]))
            for row in fold["sample"][:3]:
                print("  %s loaded=%s shipped=%s residual=%s"
                      % (row["box"], row["loaded"], row["shipped"], row["residual"]))
            print("VERDICT: %s" % ("PASS" if fold["containers"]
                                   and not fold["negative_residual_containers"]
                                   else "FAIL - a container shipped more than it held"))
            return

        started = time.time()
        rates = measured_void_rate(db)
        if args.wafers:
            rates = {w: rates[w] for w in sorted(rates)[:args.wafers]}
        factors = assign_factors(rates, args.causal_top_fraction)
        bond_eqps = bond_eqp_by_wafer(db)
        positions = scan_positions(db, args.scans_per_wafer)

        atoms = recipe_atoms()
        transfer_facts = dt_transfer_facts(db)
        chain_atoms, chain_stats = transfer_atoms(transfer_facts,
                                                  args.double_dt_fraction)
        atoms.extend(chain_atoms)
        atoms.extend(dt_condition_atoms(transfer_facts))
        runs, findings = [], []
        for index, wafer in enumerate(sorted(rates)):
            atoms.extend(wafer_atoms(wafer, index, factors[wafer],
                                     bond_eqps.get(wafer, "SYN-BD-01")))
            wafer_runs, wafer_findings = delam_rows(
                wafer, positions.get(wafer, ()), factors[wafer], index)
            runs.extend(wafer_runs)
            findings.extend(wafer_findings)
        atoms = screen_all(atoms)
        build_s = time.time() - started

        causal_wafers = sum(1 for f in factors.values()
                            if f["bond_rev"] == BOND_REV_CAUSAL)
        mold_causal = sum(1 for f in factors.values()
                          if f["mold_eqp"] == MOLD_EQP_CAUSAL)
        print("wafers=%d  atoms=%d  scat runs=%d  delam findings=%d  (built in %.1fs)"
              % (len(rates), len(atoms), len(runs), len(findings), build_s))
        print("planted: bond rev%s on %d wafers (top %.0f%% by MEASURED void rate); "
              "mould eqp %s on %d wafers (independent hash)"
              % (BOND_REV_CAUSAL, causal_wafers, args.causal_top_fraction * 100,
                 MOLD_EQP_CAUSAL, mold_causal))
        print("decoys: step/recipe id (100%% of both populations), chamber %s (~%.0f%% "
              "of both), bond eqp (lot-determined)" % (CHAMBERS[0], CHAMBER_SKEW * 100))
        print("transfer chain: core wafers=%d  pick=%d  restage=%d  bond-consume=%d  |  "
              "chains via TWO dt slots=%d, via one=%d"
              % (chain_stats["core_wafers"], chain_stats["load"],
                 chain_stats["restage"], chain_stats["consume"],
                 chain_stats["chains_3hop"], chain_stats["chains_2hop"]))

        if not args.apply:
            print("DRY RUN: nothing written. Re-run with --apply.")
            return

        ensure_tables(db)
        t0 = time.time()
        atom_totals = write_atoms(atoms)
        run_n = write_rows(db, "inspection_run", runs)
        find_n = write_rows(db, "delam_obs", findings)
        print("WROTE atoms attempted=%d inserted=%d deduped=%d | inspection_run cells=%d"
              " | delam_obs cells=%d in %.1fs"
              % (atom_totals["attempted"], atom_totals["inserted"],
                 atom_totals["deduped"], run_n, find_n, time.time() - t0))

        if args.prove:
            from ledger_api import finding_kinds

            for kind in ([args.finding] if args.finding else finding_kinds.kinds()):
                report = prove(db, kind)
                print("finding=%s -> %s" % (kind, "PASS" if not report["failures"]
                                            else report["failures"]))
    finally:
        db.close()


if __name__ == "__main__":
    main()
