"""Canonical Profile evaluation inside the registered Chain-mapper boundary.

There is no public execution plan or lifecycle here.  An approved canonical Profile is
validated, its bindings are evaluated over the explicitly supplied input DataFrame, and
trusted Pack/Claim emitters create the existing Atom meaning.  The result is the same
LedgerFrame returned by Python mappers.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Callable, Optional

import pandas as pd

from .chain_mapper import (
    LedgerMapperContext,
    LedgerMapperError,
    mapper_provenance,
)
from .config import PLACE_WAFER_GRID, TRANSFER_PREDICATE
from .envelope import Atom
from .ledger_frame import empty_ledger_frame, ledger_frame_from_atoms
from .source_profile import (
    BindingDefinition,
    ProfileRegistries,
    ProfileValidationError,
    SourceOntologyProfile,
    require_executable_profile,
    validate_profile,
)


LookupBatchFunction = Callable[[Mapping[str, Any], tuple[Any, ...]], Mapping[str, Sequence]]
ClaimEmitter = Callable[[Mapping[str, Any], str], Mapping[str, Any]]


@dataclass(frozen=True)
class DeclaredLookupAdapter:
    """Trusted, batch-only lookup callable named by ``declared_lookup.lookup_id``."""

    lookup_id: str
    selects: tuple[str, ...]
    resolve_many: LookupBatchFunction


@dataclass(frozen=True)
class ClaimEmitterDescriptor:
    pack_id: str
    pack_version: int
    claim_id: str
    emitter_id: str
    derivation: str
    subject_types: tuple[str, ...]
    emit: ClaimEmitter


class ClaimEmitterRegistry:
    """Trusted Pack/Claim semantic adapters, independent of source/table names."""

    def __init__(self, descriptors: Sequence[ClaimEmitterDescriptor] = ()):
        self._items: dict[tuple[str, int, str], ClaimEmitterDescriptor] = {}
        self._sealed = False
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: ClaimEmitterDescriptor) -> None:
        if self._sealed:
            raise RuntimeError("claim emitter registry is sealed")
        if not isinstance(descriptor, ClaimEmitterDescriptor):
            raise TypeError("emitter descriptor must be ClaimEmitterDescriptor")
        strings = (descriptor.pack_id, descriptor.claim_id, descriptor.emitter_id,
                   descriptor.derivation, *descriptor.subject_types)
        if any(not isinstance(item, str) or not item.strip() for item in strings):
            raise ValueError("emitter descriptor strings must not be blank")
        if (isinstance(descriptor.pack_version, bool)
                or not isinstance(descriptor.pack_version, int)
                or descriptor.pack_version < 1):
            raise ValueError("emitter pack version must be a positive integer")
        if not descriptor.subject_types or not callable(descriptor.emit):
            raise ValueError("emitter requires subject types and callable")
        key = (descriptor.pack_id, descriptor.pack_version, descriptor.claim_id)
        if key in self._items:
            raise ValueError(f"claim emitter {key!r} is already registered")
        self._items[key] = descriptor

    def seal(self) -> "ClaimEmitterRegistry":
        self._sealed = True
        return self

    def get(self, pack_id: str, version: int,
            claim_id: str) -> Optional[ClaimEmitterDescriptor]:
        return self._items.get((pack_id, version, claim_id))


def map_profile_to_ledger_frame(db, payload, rule=None):
    """Existing Chain mapper shape for a simple, approved canonical Profile."""
    if not isinstance(db, LedgerMapperContext):
        raise LedgerMapperError(
            "invalid_mapper_context", "context",
            "Profile mapper accepts only LedgerMapperContext, never a DB session")
    if not isinstance(payload, pd.DataFrame):
        raise LedgerMapperError(
            "invalid_mapper_input", "payload",
            "Profile mapper requires a pandas DataFrame")
    if not isinstance(rule, Mapping):
        raise LedgerMapperError(
            "missing_mapper_rule", "rule", "Profile mapper requires its rule")

    raw_profile = rule.get("profile")
    registries = rule.get("profile_registries")
    if registries is not None and not isinstance(registries, ProfileRegistries):
        raise LedgerMapperError(
            "invalid_mapper_rule", "rule.profile_registries",
            "profile_registries must be ProfileRegistries")
    try:
        if isinstance(raw_profile, SourceOntologyProfile):
            profile = raw_profile
        elif isinstance(raw_profile, Mapping):
            profile = validate_profile(raw_profile, registries=registries)
        else:
            raise LedgerMapperError(
                "missing_mapper_rule", "rule.profile",
                "validated canonical Profile or its four-field mapping is required")
        # Recursively checks declared_lookup.key and every top-level Binding.
        require_executable_profile(profile)
    except ProfileValidationError as exc:
        raise LedgerMapperError(exc.code, exc.path, exc.message) from exc

    event = rule.get("source_event")
    if not isinstance(event, Mapping):
        raise LedgerMapperError(
            "missing_source_event", "rule.source_event",
            "driver must provide explicit source-event provenance")
    molecule_ref = _required_text(
        event.get("molecule_ref"), "rule.source_event.molecule_ref")
    source_raw_ref = _required_text(
        event.get("source_raw_ref"), "rule.source_event.source_raw_ref")
    source = profile.source
    if "source" in rule and rule.get("source") != source:
        raise LedgerMapperError(
            "profile_source_mismatch", "rule.source",
            f"Profile source {source!r} does not match driver source {rule.get('source')!r}")

    emitters = rule.get("emitter_registry") or default_claim_emitter_registry()
    if not isinstance(emitters, ClaimEmitterRegistry):
        raise LedgerMapperError(
            "invalid_mapper_rule", "rule.emitter_registry",
            "emitter registry must be ClaimEmitterRegistry")
    if payload.empty or not profile.mappings:
        return empty_ledger_frame()

    rows = [{str(name): _plain(payload.iloc[position][name])
             for name in payload.columns}
            for position in range(len(payload))]
    pack_versions = {pack.pack_id: pack.version for pack in profile.packs}
    profile_hash = hashlib.sha256(profile.serialize().encode("utf-8")).hexdigest()
    provenance_base = mapper_provenance(
        f"profile-v{profile.profile_version}:{profile_hash[:16]}", rule)

    atoms: list[Atom] = []
    declared_derivations: set[str] = set()
    declared_subject_types: set[str] = set()
    lookup_cache: dict[tuple[str, str], list[Any]] = {}
    for mapping_index, mapping in enumerate(profile.mappings):
        pack_id, claim_id = mapping.use.split("/", 1)
        descriptor = emitters.get(pack_id, pack_versions[pack_id], claim_id)
        mapping_path = f"mappings[{mapping_index}]"
        if descriptor is None:
            raise LedgerMapperError(
                "unsupported_claim_execution", f"{mapping_path}.use",
                f"no emitter is registered for {mapping.use}@{pack_versions[pack_id]}")
        values_by_role = {
            role_id: _evaluate_binding_many(
                binding, rows, db, f"{mapping_path}.bind.{role_id}", lookup_cache)
            for role_id, binding in mapping.bind.items()
        }
        for row_index in range(len(rows)):
            roles = {role_id: values[row_index]
                     for role_id, values in values_by_role.items()}
            emitted = descriptor.emit(roles, mapping_path)
            atoms.append(Atom(
                subject_type=emitted["subject_type"],
                subject_keys=dict(emitted["subject_keys"]),
                predicate=emitted["predicate"],
                object_kind=emitted.get("object_kind"),
                object_payload=emitted.get("object_payload"),
                occurred_at=emitted["occurred_at"],
                source_who=source,
                source_translator_ver=(
                    f"{provenance_base}#{descriptor.derivation}"),
                source_raw_ref=source_raw_ref,
                supersedes=emitted.get("supersedes"),
                molecule_ref=molecule_ref,
                derivation=descriptor.derivation,
            ))
        declared_derivations.add(descriptor.derivation)
        declared_subject_types.update(descriptor.subject_types)
    frame = ledger_frame_from_atoms(atoms)
    frame.attrs["gate_contract"] = {
        "declared_derivations": tuple(sorted(declared_derivations)),
        "declared_subject_types": tuple(sorted(declared_subject_types)),
        "source_rows": len(rows),
    }
    return frame


def _evaluate_binding_many(
        binding: BindingDefinition,
        rows: Sequence[Mapping[str, Any]],
        context: LedgerMapperContext,
        path: str,
        cache: dict[tuple[str, str], list[Any]]) -> list[Any]:
    if binding.kind == "column":
        column = str(binding.values["column"])
        values = []
        for index, row in enumerate(rows):
            if column not in row:
                raise LedgerMapperError(
                    "binding_column_missing", f"{path}.column",
                    f"input row {index} has no column {column!r}")
            values.append(row[column])
        return values
    if binding.kind == "constant":
        value = _thaw(binding.values["value"])
        return [_copy_json(value) for _ in rows]
    if binding.kind != "declared_lookup":
        raise LedgerMapperError(
            "unsupported_binding_kind", f"{path}.kind",
            f"binding kind {binding.kind!r} has no evaluator")

    lookup_id = str(binding.values["lookup_id"])
    adapter = context.lookups.get(lookup_id)
    if not isinstance(adapter, DeclaredLookupAdapter):
        raise LedgerMapperError(
            "unsupported_lookup", f"{path}.lookup_id",
            f"declared lookup {lookup_id!r} has no registered adapter")
    select = str(binding.values["select"])
    if select not in adapter.selects:
        raise LedgerMapperError(
            "unsupported_lookup_select", f"{path}.select",
            f"lookup {lookup_id!r} does not declare select {select!r}")
    key_binding = binding.values.get("key")
    if not isinstance(key_binding, BindingDefinition):
        raise LedgerMapperError(
            "unsupported_binding_structure", f"{path}.key",
            "declared_lookup.key must be a normalized Binding")
    keys = _evaluate_binding_many(
        key_binding, rows, context, f"{path}.key", cache)
    unique: dict[str, Any] = {}
    for key in keys:
        unique.setdefault(_canonical_json(key, f"{path}.key"), key)
    uncached = {canonical: key for canonical, key in unique.items()
                if (lookup_id, canonical) not in cache}
    if uncached:
        try:
            resolved = adapter.resolve_many(
                context.values, tuple(uncached[canonical]
                                      for canonical in sorted(uncached)))
        except LedgerMapperError:
            raise
        except Exception as exc:
            raise LedgerMapperError(
                "lookup_failed", path,
                f"lookup {lookup_id!r} raised {exc.__class__.__name__}: {exc}") from exc
        if not isinstance(resolved, Mapping):
            raise LedgerMapperError(
                "lookup_result_invalid", path,
                "lookup adapter must return canonical-key -> result rows mapping")
        for canonical in sorted(uncached):
            raw_matches = resolved.get(canonical, ())
            if (not isinstance(raw_matches, Sequence)
                    or isinstance(raw_matches, (str, bytes, Mapping))):
                raise LedgerMapperError(
                    "lookup_result_invalid", path,
                    "each lookup result must be a sequence of row mappings")
            cache[(lookup_id, canonical)] = list(raw_matches[:2])

    values = []
    for key in keys:
        canonical = _canonical_json(key, f"{path}.key")
        matches = cache[(lookup_id, canonical)]
        if not matches:
            raise LedgerMapperError(
                "lookup_not_found", path,
                f"declared lookup {lookup_id!r} returned 0 rows")
        if len(matches) != 1:
            raise LedgerMapperError(
                "lookup_not_unique", path,
                f"declared lookup {lookup_id!r} returned more than 1 row")
        row = matches[0]
        if not isinstance(row, Mapping):
            raise LedgerMapperError(
                "lookup_result_invalid", path,
                "declared lookup result row must be a mapping")
        if select not in row:
            raise LedgerMapperError(
                "lookup_select_missing", f"{path}.select",
                f"lookup result has no selected field {select!r}")
        values.append(row[select])
    return values


def default_claim_emitter_registry() -> ClaimEmitterRegistry:
    return ClaimEmitterRegistry((
        ClaimEmitterDescriptor(
            "lot-lineage", 1, "transition", "lot-lineage.transition@1",
            "profile_lot_transition", ("Lot",), _emit_lot_transition),
        ClaimEmitterDescriptor(
            "transfer", 1, "movement", "transfer.movement@1",
            "profile_transfer_movement", ("Wafer",), _emit_transfer),
    )).seal()


def _emit_lot_transition(roles: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    subject = _entity(roles.get("subject"), "Lot", "lot", f"{path}.bind.subject")
    child = _entity(roles.get("child"), "Lot", "lot", f"{path}.bind.child")
    parent = _entity(roles.get("parent"), "Lot", "lot", f"{path}.bind.parent")
    if subject != child:
        raise LedgerMapperError(
            "invalid_claim_value", f"{path}.bind.subject",
            "lot-lineage transition subject must be the child lot")
    return {
        "subject_type": "Lot",
        "subject_keys": subject,
        "predicate": "derived_from",
        "object_kind": "entity_ref",
        "object_payload": {"type": "Lot", "keys": parent},
        "occurred_at": _aware_time(
            roles.get("occurred_at"), f"{path}.bind.occurred_at"),
    }


def _emit_transfer(roles: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    subject = _entity(
        roles.get("subject"), "Wafer", "wafer", f"{path}.bind.subject")
    origin_value = roles.get("from")
    if origin_value == "source_position":
        origin = {"type": PLACE_WAFER_GRID, "keys": {"wafer": subject["wafer"]},
                  "position": None}
    else:
        origin = _position(origin_value, f"{path}.bind.from")
    destination = _position(roles.get("to"), f"{path}.bind.to")
    payload = {"from": origin, "to": destination}
    if "qty" in roles:
        qty = roles["qty"]
        if (isinstance(qty, bool) or not isinstance(qty, (int, float)) or qty <= 0):
            raise LedgerMapperError(
                "invalid_claim_value", f"{path}.bind.qty",
                "qty must be a positive number")
        payload["qty"] = qty
    return {
        "subject_type": "Wafer",
        "subject_keys": subject,
        "predicate": TRANSFER_PREDICATE,
        "object_kind": "value",
        "object_payload": payload,
        "occurred_at": _aware_time(
            roles.get("occurred_at"), f"{path}.bind.occurred_at"),
    }


def _entity(value, entity_type: str, key_name: str, path: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        if set(value) == {"type", "keys"} and value.get("type") == entity_type:
            keys = value.get("keys")
            if isinstance(keys, Mapping) and set(keys) == {key_name}:
                value = keys[key_name]
            else:
                value = None
        else:
            value = None
    if value is None or (isinstance(value, str) and not value.strip()):
        raise LedgerMapperError(
            "invalid_claim_value", path,
            f"{entity_type} identity {key_name!r} must not be blank")
    return {key_name: value}


def _position(value, path: str) -> dict[str, Any]:
    if (not isinstance(value, Mapping)
            or set(value) != {"type", "keys", "position"}
            or not isinstance(value.get("type"), str)
            or not value["type"].strip()
            or not isinstance(value.get("keys"), Mapping)
            or not value["keys"]
            or any(not isinstance(key, str) or not key.strip()
                   for key in value["keys"])):
        raise LedgerMapperError(
            "invalid_claim_value", path,
            "position must contain exactly non-blank type, non-empty keys, and position")
    return {"type": value["type"], "keys": dict(value["keys"]),
            "position": value["position"]}


def _aware_time(value, path: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    if (not isinstance(value, datetime) or value.tzinfo is None
            or pd.isna(value)):
        raise LedgerMapperError(
            "invalid_claim_value", path,
            "occurred_at must be a timezone-aware source world time")
    return value


def _canonical_json(value, path: str) -> str:
    try:
        return json.dumps(
            _thaw(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LedgerMapperError(
            "lookup_key_invalid", path,
            f"lookup key must be a finite JSON value: {exc}") from exc


def _thaw(value):
    if isinstance(value, Mapping):
        return {str(name): _thaw(value[name]) for name in sorted(value, key=str)}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _copy_json(value):
    return _thaw(value)


def _plain(value):
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, bool) and missing:
        return None
    return value


def _required_text(value, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerMapperError(
            "invalid_mapper_rule", path, "must be a non-blank string")
    return value
