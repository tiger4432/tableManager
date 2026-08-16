"""Safe Template Method for a coded ledger translator.

Most source tables should use the ``declared`` grammar: one row -> N claims needs no
Python.  This module is for the measured boundary beyond that grammar -- grouping several
rows, positional list pairing, or a batched lookup.  It owns the invariant machinery so a
new translator does not copy the dangerous parts of an older one.

Subclass authors implement only :meth:`claim_drafts` and, when needed,
:meth:`occurred_at_value`.  The driver still owns ``gate.building_molecule`` and the gate
still screens the returned atoms against the live vocabulary.
"""
from __future__ import annotations

import abc
import dataclasses
import json

from . import gate, vocabulary
from .config import DEFAULT_OCCURRED_AT_FORMAT
from .envelope import Atom, canonical_keys
from .store import parse_occurred_at


def _json_scalar(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


class SourceMolecule:
    """A source-defined transaction unit consumed by :class:`SafeTranslatorTemplate`.

    Grouping belongs outside the translator because it also determines paging boundaries.
    The grouped rows and their stable key are handed in; neither is inferred here.
    """

    __slots__ = ("source", "key", "rows", "event_time", "is_complete")

    def __init__(self, source, key, rows, event_time, is_complete=True):
        self.source = str(source)
        self.key = key
        self.rows = list(rows)
        self.event_time = event_time
        self.is_complete = bool(is_complete)

    @property
    def ref(self):
        return json.dumps([self.source, self.key], ensure_ascii=False,
                          separators=(",", ":"), default=_json_scalar)


@dataclasses.dataclass(frozen=True)
class ClaimDraft:
    """The source-specific part of one Atom.

    Provenance, time, raw references, first-sight registration and translator version are
    absent on purpose: the template stamps those uniformly.
    """

    predicate: str
    subject_type: str
    subject_keys: dict
    derivation: str
    object_kind: str = None
    object_payload: dict = None
    rows: tuple = ()


class SafeTranslatorTemplate(abc.ABC):
    """Template Method that makes an all-or-nothing translator the default shape.

    A subclass supplies domain claims.  This base supplies everything that is easy to get
    subtly wrong: time parsing without ``now()`` fallback, source-correct provenance,
    deterministic raw references, first-sight register atoms, and rollback of registration
    memo entries when the molecule refuses.
    """

    def __init__(self, source, source_cfg, translator_ver, declared_derivations):
        self.source = str(source)
        self.cfg = source_cfg
        self.translator_ver = translator_ver
        self.declared = declared_derivations
        self.time_column = source_cfg["occurred_at_column"]
        self.time_format = source_cfg.get("occurred_at_format",
                                          DEFAULT_OCCURRED_AT_FORMAT)
        self.timezone_name = source_cfg["occurred_at_timezone"]
        self.register_types = frozenset(source_cfg.get("register_entity_types") or ())
        self.registered = set()
        self._registered_here = []

    def occurred_at_value(self, molecule):
        """Return the source's world-time value. Override only when it lives elsewhere."""
        return molecule.event_time

    @abc.abstractmethod
    def claim_drafts(self, molecule, occurred_at):
        """Return every domain claim for one molecule or call :meth:`refuse`.

        Return an iterable of :class:`ClaimDraft`.  Build the complete iterable before
        returning when possible; a refusal then happens before even provisional register
        memos are added.
        """
        raise NotImplementedError

    def translate(self, molecule):
        report = {"molecule": molecule.ref, "refused": False, "reason": None,
                  "atoms": 0, "incomplete": not bool(molecule.is_complete)}
        self._registered_here = []
        try:
            if not gate.molecule_is_open():
                raise RuntimeError(
                    "translator must run inside gate.building_molecule(source); the driver "
                    "owns the all-or-nothing scope")
            source_time = self.occurred_at_value(molecule)
            occurred_at = parse_occurred_at(source_time, self.time_format,
                                            self.timezone_name)
            if occurred_at is None:
                self.refuse(
                    gate.REFUSE_MISSING_OCCURRED_AT,
                    f"{self.time_column}={source_time!r} does not parse as "
                    f"{self.time_format!r} in {self.timezone_name}; arrival time is not "
                    "substituted", rows=len(molecule.rows))

            # Materialise first. A generator that refuses after yielding draft 1 must not
            # leave draft 1's registration memo behind.
            drafts = list(self.claim_drafts(molecule, occurred_at))
            atoms = []
            for draft in drafts:
                raw_rows = list(draft.rows) if draft.rows else molecule.rows
                register = self._register(molecule, draft.subject_type,
                                          draft.subject_keys, occurred_at, raw_rows)
                if register is not None:
                    atoms.append(register)
                atoms.append(self._atom(
                    molecule, draft.predicate, draft.subject_type, draft.subject_keys,
                    occurred_at, raw_rows, draft.derivation, draft.object_kind,
                    draft.object_payload))
        except gate.MoleculeRefused as refusal:
            self._forget_this_molecules_registers()
            report.update(refused=True, reason=refusal.reason)
            return None, report

        self._registered_here = []
        report["atoms"] = len(atoms)
        return atoms, report

    def refuse(self, reason, detail, rows=1):
        """Refuse this whole molecule under the actual source name."""
        gate.refuse(self.source, reason, detail, rows=rows)

    def require(self, row, column, where="row"):
        """Read a required value; absence is a named refusal, never a blank identity."""
        value = row.get(column)
        if value is None or str(value).strip() == "":
            self.refuse(gate.REFUSE_NO_IDENTITY,
                        f"{where}.{column} is blank; a claim with a blank identity is not "
                        "emitted", rows=1)
        return value

    def _atom(self, molecule, predicate, subject_type, subject_keys, occurred_at,
              rows, derivation, object_kind=None, object_payload=None):
        return Atom(
            subject_type=subject_type,
            subject_keys=dict(subject_keys),
            predicate=str(predicate),
            object_kind=object_kind,
            object_payload=object_payload,
            occurred_at=occurred_at,
            source_who=self.source,
            source_translator_ver=f"{self.translator_ver}#{derivation}",
            source_raw_ref=self.raw_ref(rows),
            molecule_ref=molecule.ref,
            derivation=str(derivation),
        )

    def _register(self, molecule, entity_type, keys, occurred_at, rows):
        if entity_type not in self.register_types or not vocabulary.requires_register(
                entity_type):
            return None
        memo = (entity_type, canonical_keys(keys))
        if memo in self.registered:
            return None
        self.registered.add(memo)
        self._registered_here.append(memo)
        return self._atom(molecule, "register", entity_type, keys, occurred_at, rows,
                          "first_sight")

    def _forget_this_molecules_registers(self):
        for memo in self._registered_here:
            self.registered.discard(memo)
        self._registered_here = []

    def raw_ref(self, rows):
        identities = sorted({str(row.get("row_identity")) for row in rows})
        return self.source + ":" + json.dumps(identities, ensure_ascii=False,
                                               separators=(",", ":"))

