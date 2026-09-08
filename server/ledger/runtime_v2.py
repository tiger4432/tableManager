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
from .envelope import canonical_keys, registration_fingerprint, registration_token
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
from .setup_registry import LedgerSetupSnapshot, cursor_translator_version


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
    #: Molecules the preparation refused by name instead of killing the page.
    refusals: tuple = ()
    #: Rows the preparer's own marker removed, or `None` when it declares no marker.
    excluded_rows: Any = None
    #: `(relation, row_id, source_raw_ref)` for every physical row this batch translated
    #: (S-54-b). Carried on the preview because this is the one place both halves are in
    #: hand, and written in the same transaction as the atoms -- see `_row_ref_index`.
    row_refs: tuple = ()

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


def _refusal_reasons(refusals) -> dict:
    """`{reason: count}` for the store's per-batch breakdown. Sums to `refused`."""
    counts: dict = {}
    for refusal in refusals:
        counts[refusal.reason] = counts.get(refusal.reason, 0) + 1
    return counts


def _record_refusals(source_id: str, preview: "CursorBatchPreview") -> None:
    """Charge this batch's molecule refusals to the process counters.

    🔴 CALLED FROM THE EXECUTE DOORS AND NOWHERE ELSE, WHICH IS WHAT MAKES A PREVIEW A
    PREVIEW. `preview_cursor_batch` computes exactly the same refusals and touches no
    counter, so a test run answers with the same values while `gate.refusal_report()`
    stays byte-identical across it. One judge, two readers - rather than a second
    predicate somewhere that knows it is "in dry-run mode".

    Both doors, for the same reason: `execute_scoped_batch` is where an operator re-runs
    the molecule they just fixed, so a refusal it hits has to land in the same counters
    the forward scan reports from, or the two answer differently about one source.
    """
    for refusal in preview.refusals:
        gate.refuse(source_id, refusal.reason, refusal.detail,
                    rows=refusal.rows, addresses=refusal.addresses)


def _row_ref_index(source_plan, event_frames):
    """`(relation, row_id, source_raw_ref)` for every row these event frames translated.

    🔴 THE ONE PLACE BOTH HALVES ARE IN HAND. `source_raw_ref` is built at the preparation
    boundary from a row's `order_by` values, and `row_id` rides the same frame because the
    engine now reads it on every source (판정 135). Once the physical row is DELETED neither
    can be recovered -- the ref cannot be rebuilt from values that are gone -- so it is
    written down while the row is still here.

    A frame that carries neither column contributes nothing rather than raising: a caller
    handing in a frame this shallow is a test double, and the write it feeds is the same
    write it always was.
    """
    from .roleframe import SOURCE_ROW_REF_COLUMN
    from .source_preparation import FRAME_ROW_ID_COLUMN

    pairs: dict = {}
    for frame in event_frames:
        if (FRAME_ROW_ID_COLUMN not in frame.columns
                or SOURCE_ROW_REF_COLUMN not in frame.columns):
            continue
        for index in range(len(frame)):
            row_id = frame.iloc[index][FRAME_ROW_ID_COLUMN]
            ref = frame.iloc[index][SOURCE_ROW_REF_COLUMN]
            if row_id is None or ref is None:
                continue
            pairs[str(row_id)] = str(ref)
    return tuple((source_plan.relation, row_id, pairs[row_id])
                 for row_id in sorted(pairs))


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
    refusals: list = []
    excluded: list = []
    event_frames = prepare_v2_cursor_batch(
        snapshot, source_id, base_rows, join_reader, preparers, refusals=refusals,
        excluded=excluded)
    mapper_context = MapperContext(snapshot, source_plan)
    event_results = tuple(
        dry_run_event_frame(mapper_context, event_frame, mappers)
        for event_frame in event_frames
    )
    row_refs = _row_ref_index(source_plan, event_frames)
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
        translator_version=cursor_translator_version(snapshot, source_id),
        cursor_value=MappingProxyType(normalized_cursor),
        event_results=event_results,
        candidate_semantics=tuple(MappingProxyType(item) for item in semantics),
        known_registrations=normalized_registrations,
        incomplete_count=sum(
            bool(result.role_frame.attrs.get(SOURCE_EVENT_INCOMPLETE_ATTR, False))
            for result in event_results),
        refusals=tuple(refusals),
        excluded_rows=(sum(excluded) if excluded else None),
        row_refs=row_refs,
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
    retranslate_approved: bool = False,
) -> CursorBatchExecutionResult:
    """Gate every complete event, then append atoms + cursor in LedgerStore once.

    🔴 THIS IS THE FORWARD SCAN, and "atoms + cursor in one transaction" is a promise
    about it specifically. There is a second caller of the same store door now -
    `execute_scoped_batch` below - which redoes a NAMED PART of a source and therefore must
    not move the position at all. The two are not two doors and not two write paths: they
    share this module's preview, this module's screening, and `store.write_batch`. They
    differ in one statement, and which one they get is decided HERE rather than by the
    store, so a reader of either function can see the whole answer without leaving it.

    🔴 `retranslate_approved` ARRIVES AS AN ARGUMENT AND NOTHING ELSE. The store's
    version guard is the SECOND place this refusal lives - the first is `backfill.run` - and
    a refusal in two places needs the approval in both. Passing it through global state or an
    environment variable would make「who approved this write」unanswerable at the call site.
    """
    preview = preview_cursor_batch(
        snapshot, source_id, base_rows, cursor_value, join_reader, preparers, mappers,
        known_registrations=known_registrations)
    kept_all = _screened_atoms(snapshot, source_id, preview)
    try:
        written = store.write_batch(
            source_id,
            preview.translator_version,
            kept_all,
            dict(preview.cursor_value),
            preview.molecule_count,
            refused=len(preview.refusals),
            incomplete=preview.incomplete_count,
            reasons=_refusal_reasons(preview.refusals),
            # Still True by default: without an approval the store refuses exactly as before.
            enforce_translator_version=not retranslate_approved,
            # 🔴 THE FORWARD SCAN IS WHERE THE INDEX IS BUILT. The scoped door fills it too,
            # but a source is read forward once and rescoped rarely -- an index that only
            # the rescope wrote would name a few rows out of millions and a delete would
            # look like it worked.
            row_refs=preview.row_refs,
        )
    except TypeError as exc:
        # A store implementation without the version-guarded existing transaction is
        # not a supported Stage 6 sink; fail before pretending the cursor was protected.
        if "enforce_translator_version" in str(exc) or "row_refs" in str(exc):
            raise LedgerV2RuntimeError(
                "unsupported_store_contract", "store.write_batch",
                "LedgerStore must enforce the setup snapshot cursor version",
            ) from exc
        raise
    _record_refusals(source_id, preview)
    if preview.incomplete_count:
        gate.record_incomplete(source_id, preview.incomplete_count)
    return CursorBatchExecutionResult(
        preview=preview,
        store_result=MappingProxyType(dict(written)),
    )


def execute_scoped_batch(
    snapshot: LedgerSetupSnapshot,
    source_id: str,
    base_rows: pd.DataFrame,
    scope: Any,
    join_reader: VerifiedJoinBatchReader,
    preparers: SourcePreparerImplementationRegistry,
    mappers: RoleMapperImplementationRegistry,
    store: Any,
    *,
    known_registrations: Any = None,
    withdraw_refs: Any = None,
) -> CursorBatchExecutionResult:
    """Redo ONE NAMED PART of a source. Same gate, same translation, CURSOR UNTOUCHED.

    🔴 WHY THE POSITION MUST NOT MOVE, EITHER WAY. Writing the batch's last row as the
    cursor makes the watermark say "read this far" about a source that was read further; and
    when the scope lies BEHIND the current position - the ordinary case, since a correction
    arrives after the row was first read - it drags the watermark backwards, and then every
    row between is read again or, on the next correction, skipped. Writing it and restoring
    it afterwards is the same hazard plus a window in which a crash leaves the wrong value
    committed. So the cursor statement is not repaired here; it is not issued.

    🔴 AND THAT IS WHY THE SCOPE IS CHECKED RATHER THAN TRUSTED. Without the cursor
    statement this is "write atoms for these rows and leave no trace", which must never be
    available for a WHOLE source - that would be the second write door the standing rule
    forbids, wearing this function's name. A guard that only asked "was a scope passed"
    would be decorative, so `_require_scope` proves the BATCH is the scope: every row it
    carries names a value the caller declared. A full-source batch cannot get through,
    whatever it says about itself.

    🔴 THE WITHDRAWAL RIDES IN THE SAME TRANSACTION AS THE WRITE, when there is one.
    `withdraw_refs` names the `source_raw_ref`s whose atoms this batch REPLACES, and the
    store deletes them inside the one commit that writes the new ones. `backfill.rescope`
    used to do that delete in a transaction of its own and commit it first, so a remake that
    failed left the withdrawal standing and the rows' atoms were gone -- measured, twice, on
    2026-09-08. Passed as `None` this still ADDS a generation rather than replacing one,
    which is what a caller with nothing to withdraw wants.
    """
    _require_scope(base_rows, scope)
    plan = _source_plan(snapshot, source_id)
    # Computed to satisfy the preview's contract - it requires a cursor tuple that is one
    # physical row of the batch - and then never written, because `advance_cursor=False`
    # skips the only statement that would write it. Taken from the batch rather than read
    # from the stored cursor deliberately: a value read here and handed to the writer would
    # be a read-then-write race with any concurrent forward scan, which is the same silent
    # rewind by a longer route.
    ordered = base_rows.sort_values(list(plan.driver.cursor_columns))
    last = ordered.iloc[-1]
    unwritten_cursor = {
        column: last[column] for column in plan.driver.cursor_columns}
    preview = preview_cursor_batch(
        snapshot, source_id, base_rows, unwritten_cursor, join_reader, preparers, mappers,
        known_registrations=known_registrations)
    kept_all = _screened_atoms(snapshot, source_id, preview)
    try:
        written = store.write_batch(
            source_id,
            preview.translator_version,
            kept_all,
            dict(preview.cursor_value),
            preview.molecule_count,
            refused=len(preview.refusals),
            incomplete=preview.incomplete_count,
            reasons=_refusal_reasons(preview.refusals),
            advance_cursor=False,
            withdraw_refs=withdraw_refs,
            row_refs=preview.row_refs,
        )
    except TypeError as exc:
        # A store that cannot separate the two statements would advance the cursor instead,
        # and one that cannot take the withdrawal would leave it to a second transaction --
        # the shape that lost atoms. Both are refused by name, in the same shape as the
        # version-guard refusal beside them, rather than left to land as a bare TypeError.
        if "advance_cursor" in str(exc) or "withdraw_refs" in str(exc):
            raise LedgerV2RuntimeError(
                "unsupported_store_contract", "store.write_batch",
                "LedgerStore must be able to append atoms without moving the cursor, and "
                "to withdraw the generation they replace in the same transaction",
            ) from exc
        raise
    _record_refusals(source_id, preview)
    if preview.incomplete_count:
        gate.record_incomplete(source_id, preview.incomplete_count)
    return CursorBatchExecutionResult(
        preview=preview,
        store_result=MappingProxyType(dict(written)),
    )


def _require_scope(base_rows: Any, scope: Any) -> None:
    """Prove this batch IS the scope, and name what is outside it when it is not.

    Three refusals rather than one because they are three different operator mistakes with
    three different fixes: nothing was named, the named column is not in this batch, or the
    batch reaches outside what was named. Collapsing them into "bad scope" would leave the
    third - the only dangerous one - looking like a typo.

    Values are compared as rendered text. The scope reached SQL as `= ANY(%s)` and the rows
    came back matched, so on this path a mismatch here is a real reach outside the scope;
    the offending values are named so that a rendering difference, if one ever arises, reads
    as itself rather than as a mystery.
    """
    if not isinstance(scope, (tuple, list)) or len(scope) != 2:
        raise LedgerV2RuntimeError(
            "scope_required", "scope",
            "a scoped write needs (column, values); this door cannot write a whole source")
    column, values = scope
    values = tuple(values or ())
    if not column or not values:
        raise LedgerV2RuntimeError(
            "scope_required", "scope",
            "a scoped write needs a column and at least one value")
    if not isinstance(base_rows, pd.DataFrame) or column not in base_rows.columns:
        raise LedgerV2RuntimeError(
            "scope_column_absent", f"scope.{column}",
            f"the batch does not carry {column!r}, so it cannot be shown to be in scope")
    allowed = {str(item) for item in values}
    outside = sorted({str(item) for item in base_rows[column].tolist()} - allowed)
    if outside:
        raise LedgerV2RuntimeError(
            "scope_not_honoured", f"scope.{column}",
            f"{len(outside)} value(s) in this batch are outside the declared scope: "
            f"{outside[:5]}")


def _screened_atoms(snapshot: LedgerSetupSnapshot, source_id: str, preview) -> list:
    """Gate every complete event and return what survives. One copy, both doors.

    Extracted the moment there were two callers rather than copied into the second: a
    scoped redo that screened even slightly differently would be a way to land atoms the
    forward scan's gate refuses, which is the one thing it must not be.
    """
    kept_all = []
    event_atoms = _filtered_event_atoms(
        preview.event_results, preview.known_registrations)
    _stamp_occurred_at_basis(_source_plan(snapshot, source_id), event_atoms)
    for result, atoms in zip(preview.event_results, event_atoms):
        molecule_ref = result.role_frame.attrs["molecule_ref"]
        with gate.building_molecule(source_id):
            # 🔴 `_report` STAYS DISCARDED HERE, AND THAT IS MEASURED RATHER THAN LAZY.
            # This call sits inside `gate.building_molecule`, and a refusal there does not
            # return -- `gate.refuse` raises `MoleculeRefused` while a molecule is open, so
            # the pair this line binds is only ever the ACCEPTING answer. Consuming it
            # would therefore yield nothing about any refusal.
            # The refusal's code and address travel on the refusal path instead:
            # `screen_compiled_molecule` hands `report["violation_details"]` to
            # `gate.refuse(..., addresses=...)`, which stamps them on the gate's sample
            # list, and `backfill`'s run result reads that list.
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
    return kept_all


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


def _registration_slot(atom) -> tuple:
    """What makes two registrations THE SAME ONE for this batch: the entity, and what the
    registration says about it.

    Two functions, not one: `registration_token` answers existence and is the only
    spelling the probe can produce; `registration_fingerprint` answers state and exists
    only inside atoms. Folding them would make the probe's set unmatchable - measured.
    """
    return (*registration_token(atom.subject_type, atom.subject_keys),
            registration_fingerprint(atom.object_payload))


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
    selected: dict[tuple, tuple[tuple[Any, ...], tuple[int, int]]] = {}
    for event_index, atoms in enumerate(raw):
        for atom_index, atom in enumerate(atoms):
            if atom.predicate != "register":
                continue
            token = _registration_slot(atom)
            # 🔴 THE `known` SKIP APPLIES TO REGISTRATIONS THAT SAY NOTHING (S-52, ruling
            # 128). The probe that built `known` reads the source RELATION and has no
            # attribute values, so it can only answer "does this entity exist". A
            # registration carrying attributes says something the probe never saw, so it
            # is not filtered here - two registrations of the same state are the SAME
            # ATOM (the id hashes the payload) and storage folds them.
            if not token[2] and token[:2] in known:
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
                token = _registration_slot(atom)
                if ((not token[2] and token[:2] in known)
                        or selected[token][1] != (event_index, atom_index)):
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
