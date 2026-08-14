"""`void_obs` / `delam_obs` -> `observed` atoms. The SECOND grammar, and the first
translator this package has that is not about lineage.

RULING R-2026-08-14-D, and why this is construction rather than design
-----------------------------------------------------------------------
`MI_LEDGER_SCHEMA_PROPOSAL` §6-bis had already drawn it: a defect observation and a
metrology measurement share the whole 6-element envelope and differ in the OBJECT only, so
the ledger needs one word for "a finding exists here" (`observed`) and one for "a quantity
has this value" (`measured`). The structure census (`3202ac7`) then measured the gap in the
other direction: 91,756 voids and 10,421 delaminations lived in source tables only, every
finding kind came back `in_ledger: false`, and the type graph had no defect edge at all.
This module is that drawing, built.

🔴 ONE SOURCE ROW IS ONE MOLECULE, AND THAT IS NOT A SIMPLIFICATION
--------------------------------------------------------------------
`lot_event`'s molecule is a PAIR of rows because one split writes two of them and neither
is the event by itself. A finding row is different in kind: it names its own wafer, its own
chip, its own extent and its own run, so it is true standing alone - atomicity check ① -
and grouping would invent a unit the source does not have. The all-or-nothing rule is
therefore trivially satisfied here, which is exactly why the SCOPE is still opened by the
driver (`backfill`) and still asserted below: a rule that holds by luck in one translator
is a rule the next one does not inherit.

🔴 THE WORLD TIME IS NOT ON THE ROW
------------------------------------
`void_obs` has `created_at` and `updated_at` - both ARRIVAL times, stamped by the ingester
- and nothing else. The instant a void was found is the instant of the SCAN that found it,
which lives on `inspection_run.observed_at`. So this translator reads the time through the
declared run relation, and a finding whose run cannot be found produces NOTHING rather than
an atom timestamped by when a file happened to be loaded. Design §10 risk 1 is that
substitution, and it is silent: every atom would look well formed and the ordering of
history would be wrong.

The run lookup is ONE query per page (the driver does it and hands the mapping in), the
same shape `store.existing_registrations` uses and for the same reason: a per-row lookup is
what makes a ten-million row backfill quadratic.

WHAT LANDS IN THE PAYLOAD, AND WHAT DELIBERATELY DOES NOT
----------------------------------------------------------
Lands: `finding_kind`, `method`, `run_uid` (the three the signature REQUIRES - see
`vocabulary.observed` for why the run is one of them), the die designation, the in-chip
position, the extent, the source's own unit, and `class` when the source utters one.

Does not: any pass/fail. `void_obs`'s own config comment says the verdict is
`area > threshold` with the threshold living in a recipe, so a stored verdict makes history
un-re-judgeable when the recipe changes. The console shows extent; it does not show a
grade.

🔴 `class` IS A CLAIM, NOT A COLUMN (§6-quater)
------------------------------------------------
The product owner's own words: "정확히는 class에 대한 주장이지". `delam_obs.interface`
is the TOOL's classification of a delamination, uttered at scan time, so it rides in the
same atom as part of the same utterance. A human who later looks at the image and disagrees
does not edit it - they assert `classified_as` against this atom's id, and the layering
rules resolve the contest. That second predicate is not registered yet (nothing emits it),
which is this vocabulary's growth rule and not an omission.

The VALUES are a closed, add-only set declared per kind in `server/finding_kinds.py`, and
a value outside it is refused by name. Two tools that spell a class the same way have to be
checked for meaning the same thing before it is registered, and a translator that quietly
admitted a new spelling is how that check never happens.
"""
from __future__ import annotations

import json
import logging

from . import gate, vocabulary
from .config import (DEFAULT_OCCURRED_AT_FORMAT, DERIVATION_OBSERVATION_ROW,
                     OBSERVATION_PREDICATE)
from .envelope import Atom, canonical_keys
from .store import parse_occurred_at

logger = logging.getLogger("Ledger.Observation")


class ObservationMolecule:
    """One source row. Carries the same interface the driver expects of a molecule."""

    __slots__ = ("row", "source")

    def __init__(self, source, row):
        self.source = source
        self.row = row

    @property
    def rows(self):
        return [self.row]

    @property
    def ref(self) -> str:
        """The non-semantic correlation marker (design §3's excluded list).

        Never a column, never read by a consumer. It exists so the gate can decide
        all-or-nothing and so a refusal in the log names one source row.
        """
        return json.dumps([self.source, str(self.row.get("row_identity"))],
                          ensure_ascii=False, separators=(",", ":"))

    @property
    def is_complete(self) -> bool:
        """A finding row is whole by construction - there is no second half to wait for.

        Stated rather than left out, because `incomplete` means "a true utterance arrived
        without all of its parts" and answering `True` here would put every observation in
        a bucket that explains lineage holes.
        """
        return True

    @property
    def watermark(self):
        return self.row.get("__watermark__")


class ObservationTranslator:
    """Stateless per call except the registration memo, which is run-scoped.

    The memo is seeded per page by the driver (`store.existing_registrations`) exactly as
    the lineage translator's is: 2,500 distinct base wafers across 91,756 `void_obs` rows on
    this box, so a wafer that appears in forty rows is registered once and looked up once.
    """

    def __init__(self, source, source_cfg, translator_ver, declared_derivations,
                 declared_classes=None):
        self.source = source
        self.cfg = source_cfg
        self.translator_ver = translator_ver
        self.declared = declared_derivations
        self.who = source
        self.columns = dict(source_cfg.get("columns") or {})
        self.finding_kind = str(source_cfg.get("finding_kind") or "").strip()
        self.run_cfg = dict(source_cfg.get("run") or {})
        self.time_column = source_cfg["occurred_at_column"]
        self.time_format = source_cfg.get("occurred_at_format",
                                          DEFAULT_OCCURRED_AT_FORMAT)
        self.timezone_name = source_cfg["occurred_at_timezone"]
        self.register_types = frozenset(source_cfg.get("register_entity_types") or ())
        #: 🔴 A DECLARED FACT ABOUT THE SOURCE, CARRIED INTO EVERY ATOM. `void_obs`,
        #: `delam_obs` and `inspection_run` on this box are 100% generated (the answer-key
        #: fixture), and an atom translated from a fabricated row is itself fabricated. The
        #: flag makes that readable FROM THE ATOM - `object_payload->>'synthetic'` - rather
        #: than from a lane's memory of which tables were seeded, and it disappears by
        #: changing one declaration on the day a real feed arrives.
        self.synthetic = bool(source_cfg.get("synthetic"))
        #: The kind's CLOSED class set (§6-quater). Empty means the kind declares none, and
        #: then a source that utters one is a registry decision somebody has to make.
        self.declared_classes = frozenset(declared_classes or ())
        self.registered = set()
        self._registered_here = []
        #: Counted, not refused: a row whose optional geometry is entirely blank still
        #: utters "something was found here", which is a true claim.
        self.blank_geometry = 0

    # ------------------------------------------------------------------- atom makers
    def _atom(self, molecule, predicate, subject_keys, occurred_at, derivation,
              object_kind=None, object_payload=None):
        return Atom(
            subject_type="Wafer",
            subject_keys=subject_keys,
            predicate=predicate,
            object_kind=object_kind,
            object_payload=object_payload,
            occurred_at=occurred_at,
            source_who=self.who,
            source_translator_ver=f"{self.translator_ver}#{derivation}",
            source_raw_ref=raw_ref(self.source, molecule.rows),
            molecule_ref=molecule.ref,
            derivation=derivation,
        )

    def _register(self, molecule, keys, occurred_at):
        """A `register` atom on first sight of a wafer, or `None`.

        An observation source registering a substrate is not a stretch: seeing a defect on
        it IS first-hand evidence that it exists. It is a DECLARATION either way
        (`register_entity_types`), so a site that would rather its observation feeds never
        mint entities turns it off without a code change.
        """
        if "Wafer" not in self.register_types:
            return None
        if not vocabulary.requires_register("Wafer"):
            return None
        memo = ("Wafer", canonical_keys(keys))
        if memo in self.registered:
            return None
        self.registered.add(memo)
        self._registered_here.append(memo)
        return self._atom(molecule, "register", keys, occurred_at, "first_sight")

    # ---------------------------------------------------------------------- the work
    def translate(self, molecule, runs):
        """One row -> `(atoms, report)`, or `(None, report)` when it was refused.

        `runs` is `{run_key: {"occurred_at": ..., "method": ...}}` for this page, fetched
        once by the driver. A key absent from it is a finding whose run does not exist, and
        that is a refusal rather than a lookup miss to paper over.
        """
        report = {"molecule": molecule.ref, "refused": False, "reason": None,
                  "atoms": 0, "incomplete": False}
        self._registered_here = []
        try:
            atoms = self._build(molecule, runs)
        except gate.MoleculeRefused as refusal:
            self._forget_this_molecules_registers()
            report.update(refused=True, reason=refusal.reason)
            return None, report
        self._registered_here = []
        report["atoms"] = len(atoms)
        return atoms, report

    def _forget_this_molecules_registers(self):
        """Give back the memos of a row that landed nothing - see the lineage translator's
        own note. A wafer left marked "already registered" by a REFUSED row is registered
        nowhere, and the next row that mentions it emits no register either."""
        for memo in self._registered_here:
            self.registered.discard(memo)
        self._registered_here = []

    def _build(self, molecule, runs):
        """The atoms of one row, or a raised `gate.MoleculeRefused`. Never both."""
        if not gate.molecule_is_open():
            raise RuntimeError(
                "_build must run inside gate.building_molecule() - outside it a refusal "
                "counts without aborting, which is the defect ruling R-2026-08-13-H "
                "removed. The scope belongs to the driver (`backfill.run`), so a caller "
                "driving this translator by hand has to open it.")

        row = molecule.row
        wafer = _text(row.get("wafer"))
        if not wafer:
            gate.refuse(self.source, gate.REFUSE_NO_IDENTITY,
                        f"row {row.get('row_identity')!r}: "
                        f"{self.columns.get('wafer')} is blank, so this finding is about "
                        f"nothing nameable; 'a void exists on some wafer' is not a claim",
                        rows=1)

        run_key = _text(row.get("run_key"))
        if not run_key:
            gate.refuse(self.source, gate.REFUSE_NO_IDENTITY,
                        f"row {row.get('row_identity')!r}: "
                        f"{self.run_cfg.get('key_column')} is blank. An observation with "
                        f"no inspection run has no denominator - '3 voids' means nothing "
                        f"without 'out of how many scans' - and `observed` requires "
                        f"run_uid in its payload for exactly that reason",
                        rows=1)

        run = runs.get(run_key)
        if run is None:
            gate.refuse(self.source, gate.REFUSE_MISSING_OCCURRED_AT,
                        f"row {row.get('row_identity')!r}: run {run_key!r} is not in "
                        f"{self.run_cfg.get('relation')}, so this finding has no world "
                        f"time and no method; arrival time is NOT substituted "
                        f"(design §10 risk 1)",
                        rows=1)

        occurred_at = parse_occurred_at(run.get("occurred_at"), self.time_format,
                                        self.timezone_name)
        if occurred_at is None:
            gate.refuse(self.source, gate.REFUSE_MISSING_OCCURRED_AT,
                        f"row {row.get('row_identity')!r}: run {run_key!r} carries "
                        f"{self.time_column}={run.get('occurred_at')!r}, which does not "
                        f"parse as {self.time_format!r}",
                        rows=1)

        method = _text(run.get("method"))
        if not method:
            gate.refuse(self.source, gate.REFUSE_NOT_TRUE_ALONE,
                        f"row {row.get('row_identity')!r}: run {run_key!r} declares no "
                        f"method. The method is HOW this was looked for, it is what the "
                        f"kind's denominator is defined against "
                        f"(`finding_kinds.observed_by`), and `observed` requires it",
                        rows=1)

        atoms = []
        register = self._register(molecule, {"wafer": wafer}, occurred_at)
        if register:
            atoms.append(register)
        atoms.append(self._atom(
            molecule, OBSERVATION_PREDICATE, {"wafer": wafer}, occurred_at,
            DERIVATION_OBSERVATION_ROW, "value",
            self._payload(molecule, row, run_key, method)))
        return atoms

    def _payload(self, molecule, row, run_key, method):
        """The finding, transcribed. Nothing here computes anything.

        🔴 Numbers are carried with the type the source column has (`base_x` is a double
        precision, so it arrives as `8.0` and stays `8.0`). Rounding a die coordinate to an
        integer would be this translator deciding what the source meant, and design §3's
        object row is the audit that found `0` and `"0"` rendered identically - the ledger's
        answer to type ambiguity is to preserve, never to tidy.
        """
        payload = {
            "finding_kind": self.finding_kind,
            "method": method,
            "run_uid": run_key,
        }
        die = _compact({"x": row.get("die_x"), "y": row.get("die_y"),
                        "gate": row.get("die_gate")})
        if die:
            payload["die"] = die
        inchip = _compact({"x": row.get("inchip_x"), "y": row.get("inchip_y")})
        if inchip:
            payload["inchip"] = inchip
        extent = _compact({"x": row.get("extent_x"), "y": row.get("extent_y")})
        if extent:
            payload["extent"] = extent
        if not die and not inchip and not extent:
            self.blank_geometry += 1
        unit = _text(row.get("unit"))
        if unit:
            # ONE unit, at the top level, because the SOURCE has one unit column for the
            # whole row. Copying it into both `extent` and `inchip` would be this
            # translator asserting that the in-chip coordinate is measured in it, which is
            # likely and is not something the row says.
            payload["unit"] = unit
        klass = _text(row.get("class"))
        if klass:
            if klass not in self.declared_classes:
                gate.refuse(self.source, gate.REFUSE_UNDECLARED_VOCABULARY,
                            f"row {row.get('row_identity')!r}: "
                            f"{self.columns.get('class')}={klass!r} is not in the closed "
                            f"class set declared for finding kind "
                            f"{self.finding_kind!r} "
                            f"(declared: {', '.join(sorted(self.declared_classes)) or 'none'}). "
                            f"§6-quater: the class set is per-kind, closed and add-only - "
                            f"register it in server/finding_kinds.py after checking that "
                            f"it means what the same word means on the tool next door",
                            rows=1)
            payload["class"] = klass
        if self.synthetic:
            payload["synthetic"] = True
        return payload


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _compact(mapping):
    """Drop the keys the source left NULL. An absent geometry is a fact about the row.

    ⚠️ `None` only. `0.0` is a legitimate die coordinate and a legitimate extent, and a
    truthiness filter here would silently delete the origin column of every wafer map -
    the same mistake `vocabulary.check_signature` documents one file over.
    """
    kept = {k: v for k, v in mapping.items() if v is not None}
    return kept or None


def raw_ref(source, rows) -> str:
    """`<source>:["<row id>"]` - the only route back to re-translation (design §3).

    Identical shape to the lineage translator's, deliberately: a reader that can split one
    can split the other, and a JSON array is what keeps a row identity that already
    contains delimiters recoverable.
    """
    identities = sorted({str(row["row_identity"]) for row in rows})
    return source + ":" + json.dumps(identities, ensure_ascii=False,
                                     separators=(",", ":"))
