"""The one pandas boundary between a Chain mapper and the existing Ledger gate.

``LedgerFrame`` is intentionally a schema-marked :class:`pandas.DataFrame`, not a
second Claim DTO.  It exists only in memory: mappers return it, this module validates
it and recreates the existing :class:`ledger.envelope.Atom`, and the existing gate and
``LedgerStore`` keep owning every decision after that point.

The pandas index is never inspected for identity.  A source event has an explicit,
deterministic UUID in every row that belongs to it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import uuid

import pandas as pd

from .envelope import (
    Atom,
    PayloadNotPreservable,
    SOURCE_EVENT_STATES,
    freeze_payload,
    source_event_identity,
)


LEDGER_FRAME_SCHEMA_VERSION = 1
LEDGER_FRAME_ATTR = "assy_manager.ledger_frame_schema_version"

# This is an interchange contract, so order is significant and extra columns are
# refused.  Storage-only ``Atom.id`` is absent because it is minted by LedgerStore.
LEDGER_FRAME_COLUMNS = (
    "source_event_id",
    "source_event_state",
    "subject_type",
    "subject_keys",
    "predicate",
    "object_kind",
    "object_payload",
    "occurred_at",
    "source_who",
    "source_translator_ver",
    "source_raw_ref",
    "supersedes",
    "molecule_ref",
    "derivation",
)


class LedgerFrameError(ValueError):
    """A stable, path-addressed mapper-result contract failure."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def empty_ledger_frame() -> pd.DataFrame:
    """Return the explicit, valid ``0 Claim`` result.

    An arbitrary empty DataFrame is not equivalent: the schema marker is what lets the
    caller distinguish a deliberate no-output event from a mapper that forgot to return
    a result.
    """
    frame = pd.DataFrame({name: pd.Series(dtype=object)
                          for name in LEDGER_FRAME_COLUMNS})
    frame.attrs[LEDGER_FRAME_ATTR] = LEDGER_FRAME_SCHEMA_VERSION
    return frame


def ledger_frame_from_atoms(atoms: Sequence[Atom]) -> pd.DataFrame:
    """Create a LedgerFrame without mutating translator-owned ``Atom`` instances."""
    rows = []
    for index, atom in enumerate(atoms):
        if not isinstance(atom, Atom):
            raise LedgerFrameError(
                "invalid_atom", f"atoms[{index}]", "expected ledger.envelope.Atom")
        event_id = atom.source_event_id
        event_state = atom.source_event_state
        if event_id is None and event_state is None:
            try:
                event_id, event_state = source_event_identity(
                    atom.source_who,
                    atom.occurred_at,
                    molecule_ref=atom.molecule_ref,
                    source_raw_ref=atom.source_raw_ref,
                )
            except (TypeError, ValueError) as exc:
                raise LedgerFrameError(
                    "invalid_source_event", f"atoms[{index}]", str(exc)) from exc
        rows.append({
            "source_event_id": event_id,
            "source_event_state": event_state,
            "subject_type": atom.subject_type,
            "subject_keys": atom.subject_keys,
            "predicate": atom.predicate,
            "object_kind": atom.object_kind,
            "object_payload": atom.object_payload,
            "occurred_at": atom.occurred_at,
            "source_who": atom.source_who,
            "source_translator_ver": atom.source_translator_ver,
            "source_raw_ref": atom.source_raw_ref,
            "supersedes": atom.supersedes,
            "molecule_ref": atom.molecule_ref,
            "derivation": atom.derivation,
        })
    if not rows:
        return empty_ledger_frame()
    # Per-column object Series prevents pandas from coercing nested JSON or nullable
    # values into strings/floats.  The validator still proves every cell below.
    frame = pd.DataFrame({
        name: pd.Series([row[name] for row in rows], dtype=object)
        for name in LEDGER_FRAME_COLUMNS
    })
    frame.attrs[LEDGER_FRAME_ATTR] = LEDGER_FRAME_SCHEMA_VERSION
    return validate_ledger_frame(frame)


def validate_ledger_frame(value, *, path: str = "ledger_frame") -> pd.DataFrame:
    """Return ``value`` unchanged when it is exactly the LedgerFrame contract."""
    if value is None:
        raise LedgerFrameError(
            "missing_ledger_frame", path,
            "mapper returned None; return a valid LedgerFrame or a typed refusal")
    if not isinstance(value, pd.DataFrame):
        raise LedgerFrameError(
            "invalid_ledger_frame", path,
            f"mapper returned {type(value).__name__}; expected pandas.DataFrame")
    marker = value.attrs.get(LEDGER_FRAME_ATTR)
    if marker != LEDGER_FRAME_SCHEMA_VERSION:
        raise LedgerFrameError(
            "unmarked_ledger_frame", f"{path}.attrs[{LEDGER_FRAME_ATTR!r}]",
            "arbitrary DataFrames are not LedgerFrames; use the schema builder")
    actual_columns = tuple(value.columns)
    if actual_columns != LEDGER_FRAME_COLUMNS:
        missing = [name for name in LEDGER_FRAME_COLUMNS
                   if name not in actual_columns]
        extra = [str(name) for name in actual_columns
                 if name not in LEDGER_FRAME_COLUMNS]
        raise LedgerFrameError(
            "invalid_ledger_frame_schema", f"{path}.columns",
            f"columns must exactly match LedgerFrame v1; missing={missing}, extra={extra}")

    event_facts: dict[uuid.UUID, tuple] = {}
    event_boundaries: dict[tuple[str, str, str], uuid.UUID] = {}
    for position in range(len(value)):
        row = value.iloc[position]
        row_path = f"{path}.rows[{position}]"
        event_id = row["source_event_id"]
        if not isinstance(event_id, uuid.UUID):
            raise LedgerFrameError(
                "invalid_source_event", f"{row_path}.source_event_id",
                "source_event_id must be uuid.UUID, never a pandas index or row number")
        state = row["source_event_state"]
        if state not in SOURCE_EVENT_STATES:
            raise LedgerFrameError(
                "invalid_source_event", f"{row_path}.source_event_state",
                f"state must be one of {list(SOURCE_EVENT_STATES)}")

        _required_text(row["subject_type"], f"{row_path}.subject_type")
        _structured_identity(row["subject_keys"], f"{row_path}.subject_keys")
        _required_text(row["predicate"], f"{row_path}.predicate")
        object_kind = row["object_kind"]
        if object_kind is not None:
            _required_text(object_kind, f"{row_path}.object_kind")
        payload = row["object_payload"]
        if payload is not None and not isinstance(payload, Mapping):
            raise LedgerFrameError(
                "invalid_structured_payload", f"{row_path}.object_payload",
                "object_payload must be a mapping or null; rendered JSON is forbidden")
        try:
            freeze_payload(payload)
        except PayloadNotPreservable as exc:
            raise LedgerFrameError(
                "invalid_structured_payload", f"{row_path}.object_payload", str(exc)) from exc

        occurred_at = row["occurred_at"]
        if (not isinstance(occurred_at, datetime)
                or occurred_at.tzinfo is None
                or pd.isna(occurred_at)):
            raise LedgerFrameError(
                "invalid_occurred_at", f"{row_path}.occurred_at",
                "occurred_at must be a timezone-aware source world time")
        for name in ("source_who", "source_translator_ver", "source_raw_ref",
                     "molecule_ref", "derivation"):
            _required_text(row[name], f"{row_path}.{name}")
        supersedes = row["supersedes"]
        if supersedes is not None and not isinstance(supersedes, (str, uuid.UUID)):
            raise LedgerFrameError(
                "invalid_supersedes", f"{row_path}.supersedes",
                "supersedes must be a UUID/string reference or null")

        # New mapper results are reproducible from source provenance.  ``legacy_atom``
        # is retained solely for controlled imports whose old identity cannot be rebuilt.
        if state != "legacy_atom":
            expected_id, expected_state = source_event_identity(
                row["source_who"], occurred_at,
                molecule_ref=(row["molecule_ref"] if state == "source_molecule" else None),
                source_raw_ref=row["source_raw_ref"],
            )
            if event_id != expected_id or state != expected_state:
                raise LedgerFrameError(
                    "invalid_source_event", f"{row_path}.source_event_id",
                    "source event identity does not match its explicit provenance")

        facts = (state, row["source_who"], occurred_at, row["molecule_ref"])
        previous = event_facts.setdefault(event_id, facts)
        if previous != facts:
            raise LedgerFrameError(
                "inconsistent_source_event", f"{row_path}.source_event_id",
                "rows sharing source_event_id disagree on event provenance")
        if state != "legacy_atom":
            boundary = (
                row["source_who"], state,
                (row["molecule_ref"] if state == "source_molecule"
                 else row["source_raw_ref"]),
            )
            previous_id = event_boundaries.setdefault(boundary, event_id)
            if previous_id != event_id:
                raise LedgerFrameError(
                    "inconsistent_source_event", f"{row_path}.occurred_at",
                    "one explicit source-event boundary produced multiple event IDs; "
                    "a mapper may not split one event by world time")
    return value


def atoms_from_ledger_frame(value) -> list[Atom]:
    """Validate and recreate the existing gate input, preserving nested values."""
    frame = validate_ledger_frame(value)
    atoms = []
    for position in range(len(frame)):
        row = frame.iloc[position]
        atoms.append(Atom(
            subject_type=row["subject_type"],
            subject_keys=dict(row["subject_keys"]),
            predicate=row["predicate"],
            object_kind=row["object_kind"],
            object_payload=(None if row["object_payload"] is None
                            else dict(row["object_payload"])),
            occurred_at=row["occurred_at"],
            source_who=row["source_who"],
            source_translator_ver=row["source_translator_ver"],
            source_raw_ref=row["source_raw_ref"],
            supersedes=row["supersedes"],
            molecule_ref=row["molecule_ref"],
            derivation=row["derivation"],
            source_event_id=row["source_event_id"],
            source_event_state=row["source_event_state"],
        ))
    return atoms


def _required_text(value, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerFrameError(
            "invalid_ledger_frame_value", path, "must be a non-blank string")
    return value


def _structured_identity(value, path: str) -> None:
    if not isinstance(value, Mapping) or not value:
        raise LedgerFrameError(
            "invalid_structured_identity", path,
            "subject_keys must be a non-empty mapping")
    if any(not isinstance(key, str) or not key.strip() for key in value):
        raise LedgerFrameError(
            "invalid_structured_identity", path,
            "subject key names must be non-blank strings")
    try:
        freeze_payload(dict(value))
    except PayloadNotPreservable as exc:
        raise LedgerFrameError("invalid_structured_identity", path, str(exc)) from exc
