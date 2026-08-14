"""`dt_log` -> `transferred` atoms. The THIRD grammar, and the first translator in this
package whose source is REAL DATA rather than a generator.

WHAT IS NEW HERE, IN ONE LINE
------------------------------
Every atom the ledger held until now came from a fixture. `lot_event` is seeded,
`void_obs`/`delam_obs` declare `synthetic: true` in so many words, and `syn_*` are
generators. `dt_log` is the operator's own table. 🔴 SO NOTHING HERE MARKS ITS ATOMS
SYNTHETIC - the ledger has no UPDATE, so a wrong `synthetic` flag is not a typo, it is a
permanent lie that can only be corrected by re-translating. `dt_log` DOES hold seeded rows
alongside the real ones (the `SYN-*` job families), and that is a fact about the SOURCE
TABLE, not about the translation - it is reported by the round, not stamped into atoms.

🔴 THE MOLECULE IS THE JOB-RUN, AND THE ATOM UNIT IS (JOB-RUN x SOURCE WAFER)
-------------------------------------------------------------------------------
The design says "one atom per job-run" and `transferred`'s subject is a WAFER
(`PHYSICS_ONTOLOGY_SETUP` §2-bis: a die is COMPOSED, so the die's permanent identity root
is the wafer it came from). Those two sentences meet at a measured fact: ONE DT JOB IS FED
BY SEVERAL CORE WAFERS. Measured on `assy_manager` 2026-08-14 - of 396 jobs, 83 are fed by
exactly one core wafer, 83 by two, 60 by three, and 8 by eighty-eight.

A single atom per job-run is therefore not expressible: its subject would have to be
several wafers at once. So a job-run utters ONE ATOM PER SOURCE WAFER, each carrying `qty`
- the number of dies that wafer contributed to that job - and a job fed by one wafer
utters exactly one atom, which is the declared shape unchanged. 4,669 atoms from 34,939
source rows.

🔴 `qty`, NOT ONE ATOM PER DIE - AND THE POSITIONS ARE NOT LOST
----------------------------------------------------------------
§2-bis's payload is `die` XOR `qty`: an event either names one die or carries a count.
This grammar carries the count, so no per-die `(core_x, core_y) -> (dt_x, dt_y)` pairing
lands as an atom. That is the scale decision and it is the same one ruling R-2026-08-14-D
addendum ① made for observations: a walk that dragged 34,939 die-level atoms behind every
wafer would die, and the walk is what all of this is for. The positions are still uttered
by the source and `source_raw_ref` names exactly which rows say them.

🔴 `source_raw_ref` IS A PREDICATE, NOT AN ENUMERATION - and this translator is the reason
----------------------------------------------------------------------------------------
The other two translators list their source rows by id, because their molecules are one or
two rows. A job-run group here is up to 150 rows, and 150 business keys is ~6 KB of row ids
in EVERY atom - at ten million source rows the provenance would be larger than the ledger.
So the ref names the SET by the predicate that defines it:

    dt_log:{"core_wafer":"SYN-CW-001-01","dt_job":"SYN-DTJ-001-01"}

Atomicity check ④ asks whether `raw_ref` can re-utter the claim, and a predicate that
selects exactly the rows the atom was folded from answers it - deterministically, at
bounded size, and with the same answer on every run (sorted keys), which is what lets
`uq_ledger_atom` recognise a re-translation.

WHAT REFUSES AND WHAT MERELY COUNTS - the two are different and stay different
------------------------------------------------------------------------------
  * A job whose `event_time` will not parse REFUSES. Arrival time is never substituted
    (design §10 risk 1). MEASURED: 8 jobs of 396 carry a blank `event_time` on every row.
  * A job in which NO row names a core wafer REFUSES with `no_identity` - there is nothing
    nameable for the atom to be about. MEASURED: 48 jobs.
  * A job in which SOME rows name a core wafer and some do not is INCOMPLETE, not refused.
    The anchored wafers' claims are true and destroying them would destroy evidence; the
    hole is what `incomplete` is the number for. MEASURED: 80 jobs. The unanchored rows
    carry `core_lot`/`core_slot` instead, and composing a wafer id out of those two would
    be the concatenated-identity incident design §3 is built from - `a_b` collapsed to `a`
    when one piece was blank and 170,000 production rows followed.
"""
from __future__ import annotations

import json
import logging

from . import gate, vocabulary
from .config import (DEFAULT_OCCURRED_AT_FORMAT, DERIVATION_TRANSFER_CONFIRMED,
                     DERIVATION_TRANSFER_JOB, PLACE_DT_JOB, PLACE_DT_SLOT,
                     PLACE_WAFER_GRID, TRANSFER_PREDICATE)
from .envelope import Atom, canonical_keys
from .store import parse_occurred_at

logger = logging.getLogger("Ledger.Transfer")


class TransferMolecule:
    """One job-run: every source row that shares a `group_key`.

    Carries the same interface the driver expects of a molecule, so the shared refusal
    and flush machinery does not branch on grammar.
    """

    __slots__ = ("source", "group_key", "rows")

    def __init__(self, source, group_key, rows=None):
        self.source = source
        self.group_key = group_key
        self.rows = list(rows or ())

    @property
    def ref(self) -> str:
        """The non-semantic correlation marker (design §3's excluded list).

        Never a column, never read by a consumer. It exists so the gate can decide
        all-or-nothing and so a refusal in the log names one job-run.
        """
        return json.dumps([self.source, self.group_key], ensure_ascii=False,
                          separators=(",", ":"))

    @property
    def is_complete(self) -> bool:
        """False when some row of this job-run names no wafer.

        🔴 Stated as a PROPERTY OF THE GROUP rather than of each row, because that is what
        the number has to mean downstream: "this job-run's movement record has a hole in
        it". A row without a wafer is not an error - `dt_log` legitimately records a die
        whose core wafer id has not been enriched yet - it is a claim that cannot be made
        about anything nameable.
        """
        return all(_text(row.get("wafer")) for row in self.rows)

    def unanchored_rows(self) -> int:
        return sum(1 for row in self.rows if not _text(row.get("wafer")))


class TransferTranslator:
    """Stateless per call except the registration memo, which is run-scoped.

    Seeded per page by the driver (`store.existing_registrations`) exactly as the other two
    translators' are, and for the same reason: 953 distinct core wafers across 34,939
    `dt_log` rows on this box, so a wafer that appears in twenty-eight jobs is looked up
    once.
    """

    def __init__(self, source, source_cfg, translator_ver, declared_derivations):
        self.source = source
        self.cfg = source_cfg
        self.translator_ver = translator_ver
        self.declared = declared_derivations
        self.who = source
        self.columns = dict(source_cfg.get("columns") or {})
        self.container_cfg = dict(source_cfg.get("container") or {})
        self.time_column = source_cfg["occurred_at_column"]
        self.time_format = source_cfg.get("occurred_at_format",
                                          DEFAULT_OCCURRED_AT_FORMAT)
        self.timezone_name = source_cfg["occurred_at_timezone"]
        self.register_types = frozenset(source_cfg.get("register_entity_types") or ())
        self.registered = set()
        self._registered_here = []
        #: Counted, never refused: rows of an otherwise good job-run that name no wafer.
        self.unanchored_rows = 0
        #: Job-runs whose destination had no confirmed container. The number that says how
        #: much of this source's movement chain is UNJOINABLE, which is this round's
        #: honest output rather than its failure.
        self.unconfirmed_groups = 0
        self.confirmed_groups = 0

    # ------------------------------------------------------------------- atom makers
    def _atom(self, molecule, predicate, subject_keys, occurred_at, derivation,
              raw_ref_extra=None, object_kind=None, object_payload=None):
        return Atom(
            subject_type="Wafer",
            subject_keys=subject_keys,
            predicate=predicate,
            object_kind=object_kind,
            object_payload=object_payload,
            occurred_at=occurred_at,
            source_who=self.who,
            source_translator_ver=f"{self.translator_ver}#{derivation}",
            source_raw_ref=raw_ref(self.source, self.columns, molecule.group_key,
                                   raw_ref_extra),
            molecule_ref=molecule.ref,
            derivation=derivation,
        )

    def _register(self, molecule, wafer, occurred_at):
        """A `register` atom on first sight of a core wafer, or `None`.

        A DT handler log registering a substrate is first-hand: picking dies off a wafer is
        evidence the wafer exists. It is a DECLARATION either way
        (`register_entity_types`), so a site that would rather its handler logs never mint
        entities empties that list and nothing here changes.
        """
        if "Wafer" not in self.register_types:
            return None
        if not vocabulary.requires_register("Wafer"):
            return None
        memo = ("Wafer", canonical_keys({"wafer": wafer}))
        if memo in self.registered:
            return None
        self.registered.add(memo)
        self._registered_here.append(memo)
        return self._atom(molecule, "register", {"wafer": wafer}, occurred_at,
                          "first_sight", raw_ref_extra={"wafer": wafer})

    # ---------------------------------------------------------------------- the work
    def translate(self, molecule, containers):
        """One job-run -> `(atoms, report)`, or `(None, report)` when it was refused.

        `containers` is `{group_key: {"lot": ..., "slot": ...}}` for this page, fetched
        once by the driver. A key absent from it is a job whose destination was never
        confirmed - which is a FACT to be recorded, not a lookup miss to paper over, so it
        changes the derivation rather than causing a refusal.
        """
        report = {"molecule": molecule.ref, "refused": False, "reason": None,
                  "atoms": 0, "incomplete": not molecule.is_complete}
        self._registered_here = []
        try:
            atoms = self._build(molecule, containers)
        except gate.MoleculeRefused as refusal:
            self._forget_this_molecules_registers()
            report.update(refused=True, reason=refusal.reason)
            return None, report
        self._registered_here = []
        report["atoms"] = len(atoms)
        return atoms, report

    def _forget_this_molecules_registers(self):
        """Give back the memos of a job-run that landed nothing - see the lineage
        translator's own note. A wafer left marked "already registered" by a REFUSED
        molecule is registered nowhere, and the next molecule that mentions it emits no
        register either."""
        for memo in self._registered_here:
            self.registered.discard(memo)
        self._registered_here = []

    def _build(self, molecule, containers):
        """The atoms of one job-run, or a raised `gate.MoleculeRefused`. Never both."""
        if not gate.molecule_is_open():
            raise RuntimeError(
                "_build must run inside gate.building_molecule() - outside it a refusal "
                "counts without aborting, which is the defect ruling R-2026-08-13-H "
                "removed. The scope belongs to the driver (`backfill.run`), so a caller "
                "driving this translator by hand has to open it: "
                "`with gate.building_molecule(source): tr.translate(molecule, {})`.")

        if not molecule.rows:
            gate.refuse(self.source, gate.REFUSE_NO_IDENTITY,
                        f"job-run {molecule.group_key!r} has no rows", rows=0)

        # --- the world time of the job-run ----------------------------------------
        # 🔴 ONE time for the whole group, and the group is refused if its rows disagree.
        # A job-run is one event; two world times inside it would mean the group column
        # does not identify an event on this source, and folding them (min? first?) would
        # be this translator deciding which instant history happened at. MEASURED on
        # `assy_manager` 2026-08-14: 0 of 396 jobs carry more than one distinct
        # `event_time`, so the check costs nothing today and is the thing that will
        # complain rather than average on the day a feed changes.
        stamps = {_text(row.get("event_time")) for row in molecule.rows}
        stamps.discard("")
        if len(stamps) > 1:
            gate.refuse(self.source, gate.REFUSE_ATOMICITY,
                        f"job-run {molecule.group_key!r} carries {len(stamps)} distinct "
                        f"{self.time_column} values ({', '.join(sorted(stamps)[:3])}...); "
                        f"a job-run is ONE event, so folding them would be this translator "
                        f"choosing which instant history happened at",
                        rows=len(molecule.rows))
        occurred_at = parse_occurred_at(next(iter(stamps), None), self.time_format,
                                        self.timezone_name)
        if occurred_at is None:
            gate.refuse(self.source, gate.REFUSE_MISSING_OCCURRED_AT,
                        f"job-run {molecule.group_key!r}: {self.time_column}="
                        f"{next(iter(stamps), None)!r} is blank or does not parse as "
                        f"{self.time_format!r}; arrival time is NOT substituted "
                        f"(design §10 risk 1)",
                        rows=len(molecule.rows))

        # --- the destination, and whether anybody confirmed it ---------------------
        destination, derivation = self._destination(molecule, containers)

        # --- fold the rows onto their source wafers --------------------------------
        # 🔴 THE COUNTERS BELOW ARE LOCAL UNTIL THE MOLECULE IS SAFE. A refusal after this
        # point unwinds every atom, and a counter that survived it would describe rows and
        # groups that produced NOTHING - the same half-landing as a register memo left
        # behind by a refused molecule, one field over. They are added to `self` only past
        # the last refusal site in this method.
        unanchored_here = 0
        by_wafer = {}
        for row in molecule.rows:
            wafer = _text(row.get("wafer"))
            if not wafer:
                # NOT a refusal - see `is_complete`. The row is true and says nothing
                # nameable; the job-run is counted `incomplete` by the driver.
                unanchored_here += 1
                continue
            bucket = by_wafer.setdefault(wafer, {"qty": 0, "recorded": set()})
            bucket["qty"] += 1
            recorded = _recorded_container(row)
            if recorded:
                bucket["recorded"].add(recorded)

        if not by_wafer:
            gate.refuse(self.source, gate.REFUSE_NO_IDENTITY,
                        f"job-run {molecule.group_key!r}: none of its "
                        f"{len(molecule.rows)} row(s) names a "
                        f"{self.columns.get('wafer')}, so there is no substrate this "
                        f"movement could be ABOUT. Composing one out of the origin lot "
                        f"and slot columns would mint an identity the source never "
                        f"uttered (design §3)",
                        rows=len(molecule.rows))

        # Past the last refusal site: this job-run will land, so its tallies are real.
        self.unanchored_rows += unanchored_here
        if derivation == DERIVATION_TRANSFER_CONFIRMED:
            self.confirmed_groups += 1
        else:
            self.unconfirmed_groups += 1

        atoms = []
        for wafer in sorted(by_wafer):
            bucket = by_wafer[wafer]
            register = self._register(molecule, wafer, occurred_at)
            if register:
                atoms.append(register)
            atoms.append(self._atom(
                molecule, TRANSFER_PREDICATE, {"wafer": wafer}, occurred_at, derivation,
                raw_ref_extra={"wafer": wafer}, object_kind="value",
                object_payload=self._payload(wafer, destination, bucket)))
        return atoms

    def _destination(self, molecule, containers):
        """`(container, derivation)` for this job-run's `to`.

        🔴 THE CONTAINER OBJECT CARRIES EXACTLY `type`, `keys`, `position` AND NOTHING
        ELSE. Position continuity (§2-bis) is `to` of event N compared with `from` of event
        N+1, and the comparison in this system is BY VALUE over the whole object -
        `seed_syn_process_ledger.prove_position_walk` keys its index on
        `json.dumps(payload["to"], sort_keys=True)`, and the residual fold groups by
        `object_payload->'to'`. One extra field inside the container makes every such join
        miss, silently, while every atom still looks well formed. So anything this
        translator wants to say ABOUT the destination goes at the payload's top level, not
        inside the container.
        """
        confirmed = containers.get(molecule.group_key) or {}
        lot = _text(confirmed.get("lot"))
        slot = _text(confirmed.get("slot"))
        if lot and slot:
            return ({"type": PLACE_DT_SLOT, "keys": {"dt_lot": lot, "dt_slot": slot},
                     "position": None},
                    DERIVATION_TRANSFER_CONFIRMED)
        # 🔴 The acquisition unit, named as itself. NOT the row's own dt_lot/dt_slot: those
        # are the source's declared inference targets and a wrong one makes a join succeed
        # quietly, which is the single failure this whole fixture exists to demonstrate.
        return ({"type": PLACE_DT_JOB, "keys": {"dt_job": molecule.group_key},
                 "position": None},
                DERIVATION_TRANSFER_JOB)

    def _payload(self, wafer, destination, bucket):
        """The movement, folded. Nothing here infers anything.

        `from` is the wafer's own grid with no position: this atom is a COUNT, so naming a
        single cell would be false. The per-die cells are uttered by the source rows that
        `source_raw_ref` selects.
        """
        payload = {
            "from": {"type": PLACE_WAFER_GRID, "keys": {"wafer": wafer},
                     "position": None},
            "to": dict(destination),
            "qty": bucket["qty"],
        }
        recorded = sorted(bucket["recorded"])
        if recorded:
            # 🔴 WHAT THE SOURCE ROWS WROTE DOWN, PRESERVED - AND IT IS NOT IDENTITY.
            # A LIST because a job-run's rows can disagree (measured: 4,617 of 4,618
            # (job, wafer) groups record exactly one pair and one records two), and
            # collapsing a disagreement to one value is how the disagreement stops being
            # visible. Outside the container object on purpose - see `_destination`.
            payload["container_recorded"] = [{"dt_lot": lot, "dt_slot": slot}
                                             for lot, slot in recorded]
        return payload


def _recorded_container(row):
    lot = _text(row.get("recorded_lot"))
    slot = _text(row.get("recorded_slot"))
    if not lot and not slot:
        return None
    return (lot, slot)


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def raw_ref(source, columns, group_key, extra=None) -> str:
    """`<source>:{"<group column>":"...","<wafer column>":"..."}` - the route back (§3).

    A PREDICATE rather than a list of row ids, and the module docstring says why. The keys
    are the SOURCE'S OWN COLUMN NAMES, so the ref is a query somebody can run without
    holding this file open, and `sort_keys` makes the value byte-identical on every run -
    which is what lets `uq_ledger_atom` recognise a re-translation instead of storing a
    second copy of the same claim.
    """
    selector = {columns["group_key"]: group_key}
    for logical, value in (extra or {}).items():
        physical = columns.get(logical)
        if physical and value is not None:
            selector[physical] = value
    return source + ":" + json.dumps(selector, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"))
