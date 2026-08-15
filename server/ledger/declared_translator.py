"""The translator that is a DECLARATION rather than a class (`ADMIN_SETUP_BRIEF` §6-2).

WHY THIS EXISTS
----------------
A translator belongs to a SHAPE, not to a source: `void_obs` and `delam_obs` are two
sources sharing one translator because they are one shape. So what is actually missing
when a new table arrives is not a source entry - it is a shape - and「a Python class per
shape」is precisely what put the owner's standing completion condition (「다른 스키마의
운영 환경에서 코드 0줄, 선언 교체만으로 발화」) out of reach. This module is the shape
「one row says N things」, and the things it says come from the config.

WHAT IT DELIBERATELY CANNOT DO, AND THE MEASUREMENT BEHIND THE LINE
--------------------------------------------------------------------
No list decomposition, no positional pairing. One `lot_event` row pairs `slot_numbers`
against `wafer_ids` by position and yields `derived_from` 1 + `has_wafer` 19; expressing
that in JSON means inventing loops, indices and zip, which is a small programming language
with no debugger, no stack trace and no tests. That shape keeps `lot_event_translator.py`.
The boundary is not "this was hard" - it is that the declarative form STOPS BEING EASIER TO
READ THAN THE CODE at exactly that point.

🔴 WHY THE PREDICATE IS NOT CHECKED HERE
-----------------------------------------
This translator never asks whether a predicate is in the vocabulary. The GATE does, per
atom, against the live merged set. That split matters because of the round this arrived
in: an operator registers a word on one screen and declares a source that uses it on the
next, and a config-load-time vocabulary check would consult whatever the cache held when
the process last reloaded. The gate's check cannot go stale in that window.

🔴 A MISSING COLUMN IS A REFUSAL, NOT A BLANK
----------------------------------------------
`"$leg"` naming a column the row does not have is refused by name. The alternative -
resolving to `None` and carrying on - produces an atom that is well formed, plausible, and
about nothing, which is the failure mode every other refusal in this system exists to
prevent. A NULL in a column that exists is different and is allowed through to the gate,
where the predicate's own `required` list decides.
"""
from __future__ import annotations

import json
import logging

from . import gate, vocabulary
from .config import COLUMN_REF_PREFIX, DEFAULT_OCCURRED_AT_FORMAT
from .envelope import Atom, canonical_keys, entity_ref
from .store import parse_occurred_at

logger = logging.getLogger("Ledger.Declared")


class DeclaredMolecule:
    """One source row. One row is one molecule in this grammar - and the scope is still
    opened by the driver, because the day a rule needs two rows the all-or-nothing rule is
    already holding it."""

    __slots__ = ("source", "row", "watermark")

    def __init__(self, source, row):
        self.source = source
        self.row = row
        self.watermark = row.get("__watermark__")

    @property
    def rows(self):
        return [self.row]

    @property
    def ref(self) -> str:
        return json.dumps([self.source, self.row.get("row_identity")],
                          separators=(",", ":"), ensure_ascii=False)


def raw_ref(source, row) -> str:
    return f"{source}:" + json.dumps([row.get("row_identity")],
                                     separators=(",", ":"), ensure_ascii=False)


def resolve(value, row, source, where):
    """A declared value -> a concrete one. `"$col"` reads the row; anything else is literal.

    `"$$"` escapes a literal `$`, so a payload that genuinely needs one is expressible
    rather than being an unreachable corner of the grammar.
    """
    if isinstance(value, dict):
        return {k: resolve(v, row, source, f"{where}.{k}") for k, v in value.items()
                if not str(k).startswith("__")}
    if isinstance(value, list):
        return [resolve(v, row, source, f"{where}[{i}]") for i, v in enumerate(value)]
    if not isinstance(value, str) or not value.startswith(COLUMN_REF_PREFIX):
        return value
    if value.startswith(COLUMN_REF_PREFIX * 2):
        return value[1:]
    column = value[len(COLUMN_REF_PREFIX):]
    if column not in row:
        gate.refuse(source, gate.REFUSE_NO_IDENTITY,
                    f"{where} reads column {column!r}, which this source's rows do not "
                    f"have (available: {', '.join(sorted(k for k in row if not str(k).startswith('__')))}). "
                    f"Resolving it to nothing would produce a well-formed atom about "
                    f"nothing.", rows=1)
    return row[column]


def matches(when, row, source) -> bool:
    """Whether an `emit` rule fires for this row. One operator, checked by the config."""
    if not when:
        return True
    column = when["column"]
    if column not in row:
        gate.refuse(source, gate.REFUSE_NO_IDENTITY,
                    f"a `when` clause branches on column {column!r}, which this source's "
                    f"rows do not have. A branch on a column that is not there would "
                    f"silently take the same arm forever.", rows=1)
    value = row[column]
    if "equals" in when:
        return _text(value) == _text(when["equals"])
    if "not_equals" in when:
        return _text(value) != _text(when["not_equals"])
    if "in" in when:
        return _text(value) in {_text(v) for v in when["in"]}
    if "not_in" in when:
        return _text(value) not in {_text(v) for v in when["not_in"]}
    if "present" in when:
        present = value is not None and _text(value) != ""
        return present if when["present"] else not present
    if "absent" in when:
        absent = value is None or _text(value) == ""
        return absent if when["absent"] else not absent
    return True                              # unreachable - the config refuses zero operators


def _text(value):
    return "" if value is None else str(value).strip()


class DeclaredTranslator:
    """Stateless per call except the registration memo, exactly like its siblings."""

    def __init__(self, source, source_cfg, translator_ver, declared_derivations):
        self.source = source
        self.cfg = source_cfg
        self.translator_ver = translator_ver
        self.declared = declared_derivations
        self.who = source
        self.emit = list(source_cfg.get("emit") or [])
        self.time_column = source_cfg["occurred_at_column"]
        self.time_format = source_cfg.get("occurred_at_format",
                                          DEFAULT_OCCURRED_AT_FORMAT)
        self.timezone_name = source_cfg["occurred_at_timezone"]
        #: 🔴 CARRIED INTO EVERY VALUE PAYLOAD (ruling R-2026-08-15-N ②). The declaration
        #: has to state whether the time column is the moment of the CLAIM or merely when
        #: the row appeared, and stating it in a file nobody reads at query time would be a
        #: declaration with no enforcement point. Stamping it makes the fact readable FROM
        #: THE ATOM - `object_payload->>'occurred_at_basis'` - which is the same device
        #: `synthetic` uses one translator over.
        #:
        #: ⚠️ VALUE PAYLOADS ONLY. An `entity_ref` payload has a strictly checked shape
        #: (`type`/`keys`/`qualifiers`) and an extra key there is refused by
        #: `check_signature`, correctly. So an entity_ref atom from a `row_created` source
        #: carries the fact in its declaration rather than in itself, and that asymmetry is
        #: named here rather than discovered later.
        self.occurred_at_basis = str(source_cfg.get("occurred_at_basis") or "").strip()
        self.register_types = frozenset(source_cfg.get("register_entity_types") or ())
        self.synthetic = bool(source_cfg.get("synthetic"))
        self.registered = set()
        self._registered_here = []
        #: Rows that matched no `emit` rule at all. NOT a refusal - a registry table whose
        #: rules cover only some rows is a legitimate declaration - but it is the number
        #: that explains「why did 1,181 rows produce 40 atoms」, so the dry run reports it.
        self.rows_matching_nothing = 0

    # ------------------------------------------------------------------- atom makers
    def _atom(self, molecule, predicate, subject_type, subject_keys, occurred_at,
              derivation, object_kind=None, object_payload=None):
        return Atom(
            subject_type=subject_type,
            subject_keys=subject_keys,
            predicate=predicate,
            object_kind=object_kind,
            object_payload=object_payload,
            occurred_at=occurred_at,
            source_who=self.who,
            source_translator_ver=f"{self.translator_ver}#{derivation}",
            source_raw_ref=raw_ref(self.source, molecule.row),
            molecule_ref=molecule.ref,
            derivation=derivation,
        )

    def _register(self, molecule, subject_type, keys, occurred_at):
        if subject_type not in self.register_types:
            return None
        if not vocabulary.requires_register(subject_type):
            return None
        memo = (subject_type, canonical_keys(keys))
        if memo in self.registered:
            return None
        self.registered.add(memo)
        self._registered_here.append(memo)
        return self._atom(molecule, "register", subject_type, keys, occurred_at,
                          "first_sight")

    # ---------------------------------------------------------------------- the work
    def translate(self, molecule):
        report = {"molecule": molecule.ref, "refused": False, "reason": None,
                  "atoms": 0, "incomplete": False}
        self._registered_here = []
        try:
            atoms = self._build(molecule)
        except gate.MoleculeRefused as refusal:
            self._forget_this_molecules_registers()
            report.update(refused=True, reason=refusal.reason)
            return None, report
        self._registered_here = []
        report["atoms"] = len(atoms)
        return atoms, report

    def _forget_this_molecules_registers(self):
        for memo in self._registered_here:
            self.registered.discard(memo)
        self._registered_here = []

    def _build(self, molecule):
        if not gate.molecule_is_open():
            raise RuntimeError(
                "_build must run inside gate.building_molecule() - outside it a refusal "
                "counts without aborting, which is the defect ruling R-2026-08-13-H "
                "removed. The scope belongs to the driver.")

        row = molecule.row
        occurred_at = parse_occurred_at(row.get("event_time"), self.time_format,
                                        self.timezone_name)
        if occurred_at is None:
            # 🔴 REFUSED, never substituted with `now()`. The brief's risk 2: arrival time
            # standing in for world time is the defect that never announces itself, because
            # every atom stays well formed and only the ORDER of history is wrong.
            gate.refuse(self.source, gate.REFUSE_MISSING_OCCURRED_AT,
                        f"row {row.get('row_identity')!r}: {self.time_column}="
                        f"{row.get('event_time')!r} does not parse as "
                        f"{self.time_format!r} in {self.timezone_name}",
                        rows=1)

        atoms, fired = [], 0
        for index, rule in enumerate(self.emit):
            where = f"emit[{index}]({rule.get('rule')})"
            if not matches(rule.get("when"), row, self.source):
                continue
            fired += 1
            derivation = str(rule["rule"]).strip()
            subject_type = rule["subject"]["type"]
            subject_keys = resolve(rule["subject"]["keys"], row, self.source,
                                   f"{where}.subject.keys")
            subject_keys = {k: _text(v) for k, v in subject_keys.items()}

            register = self._register(molecule, subject_type, subject_keys, occurred_at)
            if register is not None:
                atoms.append(register)

            object_kind, object_payload = self._object(rule, row, where)
            atoms.append(self._atom(
                molecule, str(rule["predicate"]).strip(), subject_type, subject_keys,
                occurred_at, derivation, object_kind=object_kind,
                object_payload=object_payload))

        if fired == 0:
            # Counted, never refused. "No rule matched this row" is the correct outcome for
            # a registry whose rules cover a subset, and refusing it would make a partial
            # declaration unusable. It IS reported, because a declaration that matches
            # nothing at all looks identical to one that works until somebody counts.
            self.rows_matching_nothing += 1
        return atoms

    def _object(self, rule, row, where):
        declared = rule.get("object")
        if declared is None:
            return None, None
        kind = declared["kind"]
        if kind == "value":
            payload = resolve(declared["payload"], row, self.source, f"{where}.payload")
            if self.occurred_at_basis:
                payload["occurred_at_basis"] = self.occurred_at_basis
            if self.synthetic:
                payload["synthetic"] = True
            return "value", payload
        if kind == "entity_ref":
            keys = resolve(declared["keys"], row, self.source, f"{where}.object.keys")
            keys = {k: _text(v) for k, v in keys.items()}
            qualifiers = resolve(declared.get("qualifiers") or {}, row, self.source,
                                 f"{where}.object.qualifiers")
            return "entity_ref", entity_ref(declared["type"], keys,
                                            **{k: _text(v) for k, v in qualifiers.items()})
        # `event_ref` is in the object-kind enum but no declared source has needed one, and
        # inventing its shape here without a caller would be the decoy declaration again.
        gate.refuse(self.source, gate.REFUSE_UNDECLARED_VOCABULARY,
                    f"{where}: object kind {kind!r} is legal in the vocabulary but this "
                    f"grammar has no shape for it yet - declare the source with a value or "
                    f"entity_ref object, or the shape needs its own round.", rows=1)
