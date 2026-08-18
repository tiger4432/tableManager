"""Ledger v2 Stage 6 execution adapter over the existing gate/store transaction.

There is no worker, cursor, or sink here.  The existing driver supplies one complete
base-relation batch and its next physical cursor; Stage 5 prepares EventFrames; Stage 4
compiles them; the existing gate and LedgerStore perform the only live write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from types import MappingProxyType
from typing import Any, Mapping

import pandas as pd

from . import gate
from .backfill import prepare_v2_cursor_batch
from .envelope import canonical_keys
from .ledger_frame import atoms_from_ledger_frame
from .roleframe import (
    LedgerV2DryRunResult,
    MapperContext,
    RoleMapperImplementationRegistry,
    SOURCE_EVENT_INCOMPLETE_ATTR,
    dry_run_event_frame,
)
from .source_preparation import (
    SourcePreparerImplementationRegistry,
    VerifiedJoinBatchReader,
)
from .setup_registry import LedgerSetupSnapshot


class LedgerV2RuntimeError(ValueError):
    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class CursorBatchPreview:
    source_id: str
    snapshot_hash: str
    translator_version: str
    cursor_value: Mapping[str, Any]
    event_results: tuple[LedgerV2DryRunResult, ...]
    candidate_semantics: tuple[Mapping[str, Any], ...]
    known_registrations: tuple[tuple[str, str], ...] | None
    incomplete_count: int

    @property
    def atom_count(self) -> int:
        return len(self.candidate_semantics)

    @property
    def molecule_count(self) -> int:
        return len(self.event_results)


@dataclass(frozen=True)
class CursorBatchExecutionResult:
    preview: CursorBatchPreview
    store_result: Mapping[str, Any]


def preview_cursor_batch(
    snapshot: LedgerSetupSnapshot,
    source_id: str,
    base_rows: pd.DataFrame,
    cursor_value: Mapping[str, Any],
    join_reader: VerifiedJoinBatchReader,
    preparers: SourcePreparerImplementationRegistry,
    mappers: RoleMapperImplementationRegistry,
    *,
    known_registrations: Any = None,
) -> CursorBatchPreview:
    """Compile the exact candidates execute will use, without gate/store writes."""
    source_plan = _source_plan(snapshot, source_id)
    normalized_cursor = _cursor_value(source_plan, base_rows, cursor_value)
    event_frames = prepare_v2_cursor_batch(
        snapshot, source_id, base_rows, join_reader, preparers)
    mapper_context = MapperContext(snapshot, source_plan)
    event_results = tuple(
        dry_run_event_frame(mapper_context, event_frame, mappers)
        for event_frame in event_frames
    )
    normalized_registrations = _known_registrations(known_registrations)
    event_atoms = _filtered_event_atoms(event_results, normalized_registrations)
    semantics = []
    for atoms in event_atoms:
        for atom in atoms:
            atom.ensure_source_event_identity()
            semantics.append(_semantic_atom(atom))
    semantics.sort(key=_canonical)
    return CursorBatchPreview(
        source_id=source_id,
        snapshot_hash=snapshot.snapshot_sha256,
        translator_version=f"ledger-v2:{snapshot.snapshot_sha256}",
        cursor_value=MappingProxyType(normalized_cursor),
        event_results=event_results,
        candidate_semantics=tuple(MappingProxyType(item) for item in semantics),
        known_registrations=normalized_registrations,
        incomplete_count=sum(
            bool(result.role_frame.attrs.get(SOURCE_EVENT_INCOMPLETE_ATTR, False))
            for result in event_results),
    )


def execute_cursor_batch(
    snapshot: LedgerSetupSnapshot,
    source_id: str,
    base_rows: pd.DataFrame,
    cursor_value: Mapping[str, Any],
    join_reader: VerifiedJoinBatchReader,
    preparers: SourcePreparerImplementationRegistry,
    mappers: RoleMapperImplementationRegistry,
    store: Any,
    *,
    known_registrations: Any = None,
) -> CursorBatchExecutionResult:
    """Gate every complete event, then append atoms + cursor in LedgerStore once."""
    preview = preview_cursor_batch(
        snapshot, source_id, base_rows, cursor_value, join_reader, preparers, mappers,
        known_registrations=known_registrations)
    kept_all = []
    event_atoms = _filtered_event_atoms(
        preview.event_results, preview.known_registrations)
    _stamp_occurred_at_basis(_source_plan(snapshot, source_id), event_atoms)
    for result, atoms in zip(preview.event_results, event_atoms):
        molecule_ref = result.role_frame.attrs["molecule_ref"]
        with gate.building_molecule(source_id):
            kept, _report = gate.screen_compiled_molecule(
                source_id,
                atoms,
                result.gate_preview["declared_derivations"],
                result.gate_preview["declared_subject_types"],
                molecule_ref=molecule_ref,
                source_rows=len({
                    ref for refs in result.role_frame["source_row_refs"].tolist()
                    for ref in refs
                }),
            )
            kept_all.extend(kept)
    try:
        written = store.write_batch(
            source_id,
            preview.translator_version,
            kept_all,
            dict(preview.cursor_value),
            preview.molecule_count,
            refused=0,
            incomplete=preview.incomplete_count,
            reasons={},
            enforce_translator_version=True,
        )
    except TypeError as exc:
        # A store implementation without the version-guarded existing transaction is
        # not a supported Stage 6 sink; fail before pretending the cursor was protected.
        if "enforce_translator_version" in str(exc):
            raise LedgerV2RuntimeError(
                "unsupported_store_contract", "store.write_batch",
                "LedgerStore must enforce the setup snapshot cursor version",
            ) from exc
        raise
    if preview.incomplete_count:
        gate.record_incomplete(source_id, preview.incomplete_count)
    return CursorBatchExecutionResult(
        preview=preview,
        store_result=MappingProxyType(dict(written)),
    )


def _known_registrations(value: Any) -> tuple[tuple[str, str], ...] | None:
    """Normalize the existing LedgerStore registration memo without DB capability.

    The existing cursor driver obtains this set with the existing batched
    ``LedgerStore.existing_registrations`` query.  Supplying it keeps first-sight state
    outside Mapper code and makes dry-run/execute consume the same immutable snapshot.
    ``None`` is distinct from an explicitly empty set and fails closed only when the
    compiled candidates actually contain ``register`` Claims.
    """
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        raise LedgerV2RuntimeError(
            "invalid_registration_context", "known_registrations",
            "must be an iterable of (subject_type, canonical_keys) pairs",
        )
    try:
        items = tuple(value)
    except TypeError as exc:
        raise LedgerV2RuntimeError(
            "invalid_registration_context", "known_registrations",
            "must be an iterable of (subject_type, canonical_keys) pairs",
        ) from exc
    normalized = set()
    for index, item in enumerate(items):
        path = f"known_registrations[{index}]"
        if (not isinstance(item, (tuple, list)) or len(item) != 2
                or not isinstance(item[0], str) or not item[0].strip()
                or item[0] != item[0].strip() or not isinstance(item[1], str)):
            raise LedgerV2RuntimeError(
                "invalid_registration_context", path,
                "must be (trimmed subject_type, canonical JSON object) pair",
            )
        try:
            keys = json.loads(item[1])
        except (TypeError, ValueError) as exc:
            raise LedgerV2RuntimeError(
                "invalid_registration_context", f"{path}[1]",
                "canonical_keys must be valid JSON",
            ) from exc
        if not isinstance(keys, dict):
            raise LedgerV2RuntimeError(
                "invalid_registration_context", f"{path}[1]",
                "canonical_keys must encode a JSON object",
            )
        normalized.add((item[0], canonical_keys(keys)))
    return tuple(sorted(normalized))


def _filtered_event_atoms(
    event_results: tuple[LedgerV2DryRunResult, ...],
    known_registrations: tuple[tuple[str, str], ...] | None,
) -> tuple[tuple[Any, ...], ...]:
    raw = tuple(tuple(atoms_from_ledger_frame(result.ledger_frame))
                for result in event_results)
    has_register = any(atom.predicate == "register"
                       for atoms in raw for atom in atoms)
    if has_register and known_registrations is None:
        raise LedgerV2RuntimeError(
            "registration_context_required", "known_registrations",
            "sources emitting register require an explicit existing-registration snapshot",
        )
    known = set(known_registrations or ())
    selected: dict[tuple[str, str], tuple[tuple[Any, ...], tuple[int, int]]] = {}
    for event_index, atoms in enumerate(raw):
        for atom_index, atom in enumerate(atoms):
            if atom.predicate != "register":
                continue
            token = (atom.subject_type, canonical_keys(atom.subject_keys))
            if token in known:
                continue
            sort_key = (
                atom.occurred_at.timestamp(), event_index, atom_index,
            )
            current = selected.get(token)
            if current is None or sort_key < current[0]:
                selected[token] = (sort_key, (event_index, atom_index))
    filtered = []
    for event_index, atoms in enumerate(raw):
        kept = []
        for atom_index, atom in enumerate(atoms):
            if atom.predicate == "register":
                token = (atom.subject_type, canonical_keys(atom.subject_keys))
                if token in known or selected[token][1] != (event_index, atom_index):
                    continue
            kept.append(atom)
        filtered.append(tuple(kept))
    return tuple(filtered)


def _stamp_occurred_at_basis(source_plan, event_atoms) -> None:
    """Mark every atom of a source that admitted where its time came from.

    Stamped HERE rather than threaded through the LedgerFrame on purpose: the frame is an
    interchange contract that refuses extra columns, so carrying this there would bump its
    version and oblige every mapper to restate a value that is constant for the whole
    source. It is stamped BEFORE the gate so the gate screens the atom that will actually
    be written, not a version of it missing a field.

    A source whose table carries world time leaves this None, which is what every atom
    written before this field existed also has - absence keeps meaning "world time".
    """
    basis = source_plan.driver.occurred_at.basis
    if basis is None:
        return
    for atoms in event_atoms:
        for atom in atoms:
            atom.occurred_at_basis = basis

def _source_plan(snapshot: LedgerSetupSnapshot, source_id: str):
    if not isinstance(snapshot, LedgerSetupSnapshot) or snapshot.readiness != "ready":
        raise LedgerV2RuntimeError(
            "setup_not_ready", "snapshot", "a ready LedgerSetupSnapshot is required")
    try:
        return snapshot.source_plans[source_id]
    except KeyError as exc:
        raise LedgerV2RuntimeError(
            "unknown_source", "source_id", f"unknown source {source_id!r}") from exc


def _cursor_value(source_plan, frame: Any, value: Any) -> dict[str, Any]:
    path = "cursor_value"
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise LedgerV2RuntimeError(
            "invalid_cursor_batch", "source_batch", "non-empty pandas batch required")
    if not isinstance(value, Mapping):
        raise LedgerV2RuntimeError(
            "invalid_cursor", path, "cursor value must be a mapping")
    expected = set(source_plan.driver.cursor_columns)
    if set(value) != expected:
        raise LedgerV2RuntimeError(
            "invalid_cursor", path,
            f"cursor must contain exactly physical columns {sorted(expected)}",
        )
    missing_columns = sorted(expected - set(frame.columns))
    if missing_columns:
        raise LedgerV2RuntimeError(
            "invalid_cursor_batch", "source_batch.columns",
            f"base batch is missing cursor columns {missing_columns}",
        )
    normalized = {}
    for column in sorted(expected):
        item = value[column]
        if item is None or (isinstance(item, str) and not item.strip()):
            raise LedgerV2RuntimeError(
                "invalid_cursor", f"{path}.{column}", "cursor value is missing")
        rendered = _json_scalar(item)
        normalized[column] = rendered
    ordered = tuple(sorted(expected))
    candidate_tuples = {
        tuple(_json_scalar(frame.iloc[position][column]) for column in ordered)
        for position in range(len(frame))
    }
    if tuple(normalized[column] for column in ordered) not in candidate_tuples:
        raise LedgerV2RuntimeError(
            "invalid_cursor", path,
            "cursor tuple is not one physical row in the bounded base batch",
        )
    return normalized


def _json_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat()
        return value.isoformat()
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not (float("-inf") < value < float("inf")):
            raise LedgerV2RuntimeError(
                "invalid_cursor", "cursor_value", "cursor number must be finite")
        return value
    if isinstance(value, str):
        return value
    raise LedgerV2RuntimeError(
        "invalid_cursor", "cursor_value",
        f"cursor scalar {value.__class__.__name__} is not JSON-preservable",
    )


def _semantic_atom(atom: Any) -> dict[str, Any]:
    return {
        "source_event_id": str(atom.source_event_id),
        "source_event_state": atom.source_event_state,
        "subject_type": atom.subject_type,
        "subject_keys": atom.subject_keys,
        "predicate": atom.predicate,
        "object_kind": atom.object_kind,
        "object_payload": atom.object_payload,
        "occurred_at": atom.occurred_at.isoformat(),
        "source_who": atom.source_who,
        "source_raw_ref": atom.source_raw_ref,
        "source_translator_ver": atom.source_translator_ver,
        "supersedes": str(atom.supersedes) if atom.supersedes else None,
        "derivation": atom.derivation,
        "molecule_ref": atom.molecule_ref,
    }


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
