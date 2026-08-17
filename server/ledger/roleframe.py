"""Ledger v2 Stage 4 EventFrame -> RoleFrame -> LedgerFrame compiler.

This module is deliberately capability-poor.  It accepts an already prepared pandas
EventFrame and an immutable Stage 3 setup snapshot.  It has no database, cursor, gate,
store, source reader, virtual-join, or translator imports.  Both declarative and custom
Python mappers can only return :class:`RoleEmission` values; the Pack compiler is the
single owner of LedgerFrame payload construction.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import numbers
from types import MappingProxyType
from typing import Any, final
import uuid

import pandas as pd

from .envelope import source_event_identity
from .ledger_frame import (
    LEDGER_FRAME_COLUMNS,
    LEDGER_FRAME_ATTR,
    LEDGER_FRAME_SCHEMA_VERSION,
    validate_ledger_frame,
)
from .setup_registry import (
    ClaimDescriptor,
    ImplementationKey,
    LedgerSetupSnapshot,
    MapperDescriptor,
    ProfileDescriptor,
    RoleDescriptor,
    SourcePlan,
)


ROLE_FRAME_SCHEMA_VERSION = 1
ROLE_FRAME_ATTR = "assy_manager.role_frame_schema_version"
ROLE_FRAME_COLUMNS = (
    "source_event_id",
    "mapping_id",
    "claim_ref",
    "roles",
    "source_row_refs",
)
EVENT_FRAME_REQUIRED_ATTRS = (
    "source_id",
    "source_event_id",
    "molecule_ref",
    "source_raw_ref",
    "setup_snapshot_hash",
)
SOURCE_ROW_REF_COLUMN = "__source_row_ref"
UNIT_SOURCE_ROW_REFS_ATTR = "assy_manager.unit_source_row_refs"


class RoleFrameError(ValueError):
    """Stable, path-addressed Stage 4 refusal."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({
            str(key): _freeze(value[key]) for key in sorted(value, key=str)
        })
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise TypeError("naive datetime has no deterministic instant")
        return {"$datetime": value.isoformat()}
    if isinstance(value, uuid.UUID):
        return {"$uuid": str(value)}
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    return value


def _canonical(value: Any, *, path: str) -> str:
    try:
        return json.dumps(
            _plain(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RoleFrameError(
            "invalid_role_value", path,
            f"value is not deterministic JSON: {exc}",
        ) from exc


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(missing, bool):
        return missing
    if getattr(missing, "shape", None) == ():
        return bool(missing)
    return False


@dataclass(frozen=True)
class RoleEmission:
    """The only value a custom mapper interpretation hook may emit."""

    mapping_id: str
    claim_ref: str
    roles: Mapping[str, Any]
    source_row_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("mapping_id", "claim_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise RoleFrameError(
                    "invalid_role_emission", f"role_emission.{name}",
                    "must be a trimmed non-blank string",
                )
        if not isinstance(self.roles, Mapping):
            raise RoleFrameError(
                "invalid_role_emission", "role_emission.roles", "must be a mapping")
        refs = tuple(self.source_row_refs)
        if (not refs or any(not isinstance(item, str) or not item.strip()
                            or item != item.strip() for item in refs)):
            raise RoleFrameError(
                "invalid_role_emission", "role_emission.source_row_refs",
                "must contain trimmed non-blank source row references",
            )
        object.__setattr__(self, "roles", _freeze(self.roles))
        object.__setattr__(self, "source_row_refs", tuple(sorted(set(refs))))


@dataclass(frozen=True)
class MapperContext:
    """Read-only Stage 4 mapper context; no runtime or persistence capability."""

    snapshot: LedgerSetupSnapshot
    source_plan: SourcePlan

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, LedgerSetupSnapshot):
            raise TypeError("snapshot must be LedgerSetupSnapshot")
        if not isinstance(self.source_plan, SourcePlan):
            raise TypeError("source_plan must be SourcePlan")
        registered = self.snapshot.source_plans.get(self.source_plan.source_id)
        if registered is not self.source_plan:
            raise RoleFrameError(
                "invalid_source_plan", "context.source_plan",
                "source plan must be the descriptor owned by the setup snapshot",
            )


def mapper_context(snapshot: LedgerSetupSnapshot, source_id: str) -> MapperContext:
    if not isinstance(snapshot, LedgerSetupSnapshot) or snapshot.readiness != "ready":
        raise RoleFrameError(
            "setup_not_ready", "snapshot", "a ready LedgerSetupSnapshot is required")
    plan = snapshot.source_plans.get(source_id)
    if plan is None:
        raise RoleFrameError(
            "unknown_source", "source_id", f"source {source_id!r} is not registered")
    return MapperContext(snapshot=snapshot, source_plan=plan)


class BaseLedgerMapper:
    """Template Method for all Stage 4 RoleFrame-producing mappers."""

    @final
    def map(
        self,
        context: MapperContext,
        event_frame: pd.DataFrame,
        descriptor: MapperDescriptor,
        profile: ProfileDescriptor,
    ) -> pd.DataFrame:
        _validate_event_frame(context, event_frame, descriptor, profile)
        emissions: list[RoleEmission] = []
        for unit_index, unit in enumerate(
                _partition_units(context, event_frame, descriptor)):
            try:
                produced = self.interpret_unit(context, unit, profile)
            except RoleFrameError:
                raise
            except Exception as exc:
                raise RoleFrameError(
                    "mapper_failed", f"mapper.units[{unit_index}]",
                    f"interpret_unit raised {exc.__class__.__name__}: {exc}",
                ) from exc
            if (isinstance(produced, (pd.DataFrame, Mapping, str, bytes, bytearray))
                    or not isinstance(produced, Sequence)):
                raise RoleFrameError(
                    "unsupported_mapper_output", f"mapper.units[{unit_index}]",
                    "interpret_unit must return a sequence of RoleEmission values",
                )
            for emission_index, emission in enumerate(produced):
                if not isinstance(emission, RoleEmission):
                    raise RoleFrameError(
                        "unsupported_mapper_output",
                        f"mapper.units[{unit_index}].emissions[{emission_index}]",
                        "raw Atom, LedgerFrame, mappings, and arbitrary values are forbidden",
                    )
                emissions.append(emission)
        frame = _role_frame_from_emissions(event_frame.attrs, emissions)
        return validate_role_frame(context, frame, descriptor, profile)

    def interpret_unit(
        self,
        context: MapperContext,
        unit: pd.DataFrame,
        profile: ProfileDescriptor,
    ) -> Sequence[RoleEmission]:
        raise NotImplementedError


class DeclarativeRoleMapper(BaseLedgerMapper):
    """Evaluate approved column/constant/entity Profile bindings without DB access."""

    def interpret_unit(
        self,
        context: MapperContext,
        unit: pd.DataFrame,
        profile: ProfileDescriptor,
    ) -> Sequence[RoleEmission]:
        refs = _source_row_refs(unit)
        out = []
        for mapping in profile.mappings:
            roles = {
                role_id: _evaluate_binding(binding, unit, path=(
                    f"{mapping.config_path}.bind.{role_id}"))
                for role_id, binding in mapping.bindings.items()
            }
            out.append(RoleEmission(
                mapping_id=mapping.mapping_id,
                claim_ref=mapping.claim_ref,
                roles=roles,
                source_row_refs=refs,
            ))
        return out


class RoleMapperImplementationRegistry:
    """Closed executable mapper classes keyed only by trusted implementation ID/version."""

    def __init__(self) -> None:
        self._items: dict[ImplementationKey, type[BaseLedgerMapper]] = {}
        self._sealed = False

    def register(
        self,
        implementation_id: str,
        implementation_version: int,
        mapper_type: type[BaseLedgerMapper],
    ) -> None:
        if self._sealed:
            raise RuntimeError("role mapper implementation registry is sealed")
        key = ImplementationKey(implementation_id, implementation_version)
        if not isinstance(mapper_type, type) or not issubclass(mapper_type, BaseLedgerMapper):
            raise TypeError("mapper_type must inherit BaseLedgerMapper")
        for ancestor in mapper_type.__mro__:
            if ancestor is BaseLedgerMapper:
                break
            if "map" in ancestor.__dict__:
                raise RoleFrameError(
                    "unsupported_mapper_override", "mapper_type.map",
                    "BaseLedgerMapper.map() is final and cannot be overridden",
                )
        if key in self._items:
            raise ValueError(f"mapper implementation {implementation_id!r}@"
                             f"{implementation_version} is already registered")
        self._items[key] = mapper_type

    def seal(self) -> "RoleMapperImplementationRegistry":
        self._sealed = True
        return self

    def resolve(self, key: ImplementationKey) -> BaseLedgerMapper:
        if not self._sealed:
            raise RoleFrameError(
                "mapper_registry_not_sealed", "mapper_registry",
                "mapper implementation registry must be sealed before execution",
            )
        mapper_type = self._items.get(key)
        if mapper_type is None:
            raise RoleFrameError(
                "unsupported_mapper_implementation", "mapper.implementation",
                f"no executable Role mapper is registered for "
                f"{key.implementation_id!r}@{key.implementation_version}",
            )
        try:
            return mapper_type()
        except TypeError as exc:
            raise RoleFrameError(
                "unsupported_mapper_implementation", "mapper.implementation",
                "registered Role mapper must have a no-argument constructor",
            ) from exc


def map_event_frame(
    context: MapperContext,
    event_frame: pd.DataFrame,
    implementations: RoleMapperImplementationRegistry,
) -> pd.DataFrame:
    if not isinstance(implementations, RoleMapperImplementationRegistry):
        raise TypeError("implementations must be RoleMapperImplementationRegistry")
    descriptor = context.source_plan.driver.mapper
    mapper = implementations.resolve(descriptor.implementation)
    return mapper.map(context, event_frame, descriptor, context.source_plan.profile)


def _validate_event_frame(
    context: MapperContext,
    value: Any,
    descriptor: MapperDescriptor,
    profile: ProfileDescriptor,
) -> None:
    path = "event_frame"
    if not isinstance(value, pd.DataFrame):
        raise RoleFrameError(
            "invalid_event_frame", path, "expected pandas.DataFrame")
    if value.empty:
        raise RoleFrameError(
            "invalid_event_frame", path, "one source event must contain at least one row")
    if value.columns.has_duplicates:
        raise RoleFrameError(
            "invalid_event_frame", f"{path}.columns", "duplicate columns are forbidden")
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        if name not in value.attrs:
            raise RoleFrameError(
                "missing_event_context", f"{path}.attrs.{name}", "attribute is required")
    source_id = value.attrs["source_id"]
    if source_id != context.source_plan.source_id or source_id != profile.source_id:
        raise RoleFrameError(
            "invalid_event_context", f"{path}.attrs.source_id",
            "source_id disagrees with SourcePlan/Profile")
    event_id = value.attrs["source_event_id"]
    if not isinstance(event_id, uuid.UUID):
        raise RoleFrameError(
            "invalid_event_context", f"{path}.attrs.source_event_id",
            "source_event_id must be uuid.UUID")
    for name in ("molecule_ref", "source_raw_ref"):
        item = value.attrs[name]
        if not isinstance(item, str) or not item.strip():
            raise RoleFrameError(
                "invalid_event_context", f"{path}.attrs.{name}",
                "must be a non-blank string")
    if value.attrs["setup_snapshot_hash"] != context.snapshot.snapshot_sha256:
        raise RoleFrameError(
            "snapshot_mismatch", f"{path}.attrs.setup_snapshot_hash",
            "EventFrame was not prepared for this setup snapshot")
    missing = [column for column in descriptor.input_columns
               if column not in value.columns]
    if missing:
        raise RoleFrameError(
            "missing_mapper_input", f"{path}.columns",
            f"mapper input columns are missing: {missing}")


def _partition_units(
    context: MapperContext,
    frame: pd.DataFrame,
    descriptor: MapperDescriptor,
) -> tuple[pd.DataFrame, ...]:
    kind = descriptor.unit_kind
    if kind == "event":
        unit = frame.copy(deep=False)
        unit.attrs[UNIT_SOURCE_ROW_REFS_ATTR] = _frame_row_refs(frame)
        return (unit,)
    if kind == "row":
        ordered = sorted(
            range(len(frame)),
            key=lambda position: _row_sort_token(frame.iloc[position], frame.columns),
        )
        units = []
        refs = _frame_row_refs(frame)
        for position in ordered:
            unit = frame.iloc[[position]].copy(deep=False)
            unit.attrs[UNIT_SOURCE_ROW_REFS_ATTR] = (refs[position],)
            units.append(unit)
        return tuple(units)
    if kind == "group_by":
        columns = tuple(descriptor.unit_columns)
        if not columns or any(column not in frame.columns for column in columns):
            raise RoleFrameError(
                "invalid_mapper_unit", "mapper.unit.group_by",
                "MapperDescriptor group_by columns must exist in EventFrame")
        groups: dict[str, list[int]] = {}
        for position in range(len(frame)):
            token = _canonical(
                {column: frame.iloc[position][column] for column in columns},
                path=f"event_frame.rows[{position}]",
            )
            groups.setdefault(token, []).append(position)
        refs = _frame_row_refs(frame)
        units = []
        for token in sorted(groups):
            positions = groups[token]
            unit = frame.iloc[positions].copy(deep=False)
            unit.attrs[UNIT_SOURCE_ROW_REFS_ATTR] = tuple(
                sorted(refs[position] for position in positions))
            units.append(unit)
        return tuple(units)
    raise RoleFrameError(
        "unsupported_mapper_unit", "mapper.unit.kind",
        f"unsupported mapper unit {kind!r}")


def _row_sort_token(row: pd.Series, columns: Sequence[Any]) -> str:
    return _canonical(
        {str(column): row[column] for column in sorted(columns, key=str)},
        path="event_frame.row",
    )


def _source_row_refs(unit: pd.DataFrame) -> tuple[str, ...]:
    declared = unit.attrs.get(UNIT_SOURCE_ROW_REFS_ATTR)
    if isinstance(declared, tuple) and declared:
        return declared
    return _frame_row_refs(unit)


def _frame_row_refs(frame: pd.DataFrame) -> tuple[str, ...]:
    if SOURCE_ROW_REF_COLUMN in frame.columns:
        refs = tuple(str(value).strip() for value in frame[SOURCE_ROW_REF_COLUMN].tolist())
        if any(not value for value in refs):
            raise RoleFrameError(
                "invalid_source_row_ref", f"event_frame.{SOURCE_ROW_REF_COLUMN}",
                "source row references must be non-blank")
        if len(set(refs)) != len(refs):
            raise RoleFrameError(
                "ambiguous_source_row_ref", f"event_frame.{SOURCE_ROW_REF_COLUMN}",
                "source row references must be unique within one source event")
        return refs
    base = str(frame.attrs.get("source_raw_ref") or "").strip()
    if len(frame) == 1:
        return (base,)
    refs = []
    for position in range(len(frame)):
        token = _row_sort_token(frame.iloc[position], frame.columns)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
        refs.append(f"{base}#row:{digest}")
    if len(set(refs)) != len(refs):
        raise RoleFrameError(
            "ambiguous_source_row_ref", "event_frame.rows",
            "indistinguishable rows require explicit __source_row_ref values")
    return tuple(refs)


def _evaluate_binding(binding: Mapping[str, Any], unit: pd.DataFrame, *, path: str) -> Any:
    if binding.get("approval_status") != "approved":
        raise RoleFrameError(
            "binding_not_approved", f"{path}.approval_status",
            "only approved bindings are executable")
    kind = binding.get("kind")
    if kind == "column":
        column = binding.get("column")
        if column not in unit.columns:
            raise RoleFrameError(
                "missing_binding_column", f"{path}.column",
                f"column {column!r} is absent from the EventFrame unit")
        values = [unit.iloc[index][column] for index in range(len(unit))]
        if any(_is_missing(value) for value in values):
            raise RoleFrameError(
                "missing_binding_value", f"{path}.column",
                f"column {column!r} contains a missing value")
        distinct = {_canonical(value, path=f"{path}.column") for value in values}
        if len(distinct) != 1:
            raise RoleFrameError(
                "ambiguous_binding_value", f"{path}.column",
                f"column {column!r} has multiple values in one mapper unit")
        return values[0]
    if kind == "constant":
        return _plain(binding.get("value"))
    if kind == "entity":
        keys = {
            key: _evaluate_binding(child, unit, path=f"{path}.keys.{key}")
            for key, child in binding.get("keys", {}).items()
        }
        return {"type": binding.get("entity_type"), "keys": keys}
    raise RoleFrameError(
        "unsupported_binding", f"{path}.kind",
        f"binding kind {kind!r} is not supported by Stage 4")


def _role_frame_from_emissions(
    event_attrs: Mapping[str, Any],
    emissions: Sequence[RoleEmission],
) -> pd.DataFrame:
    rows = [{
        "source_event_id": event_attrs["source_event_id"],
        "mapping_id": emission.mapping_id,
        "claim_ref": emission.claim_ref,
        "roles": emission.roles,
        "source_row_refs": emission.source_row_refs,
    } for emission in emissions]
    frame = pd.DataFrame({
        column: pd.Series([row[column] for row in rows], dtype=object)
        for column in ROLE_FRAME_COLUMNS
    })
    frame.attrs[ROLE_FRAME_ATTR] = ROLE_FRAME_SCHEMA_VERSION
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        frame.attrs[name] = event_attrs[name]
    return frame


def validate_role_frame(
    context: MapperContext,
    value: Any,
    descriptor: MapperDescriptor | None = None,
    profile: ProfileDescriptor | None = None,
) -> pd.DataFrame:
    descriptor = descriptor or context.source_plan.driver.mapper
    profile = profile or context.source_plan.profile
    path = "role_frame"
    if not isinstance(value, pd.DataFrame):
        raise RoleFrameError(
            "invalid_role_frame", path, "expected pandas.DataFrame")
    if value.attrs.get(ROLE_FRAME_ATTR) != ROLE_FRAME_SCHEMA_VERSION:
        raise RoleFrameError(
            "unmarked_role_frame", f"{path}.attrs.{ROLE_FRAME_ATTR}",
            "arbitrary DataFrames are not RoleFrames")
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        if name not in value.attrs:
            raise RoleFrameError(
                "missing_event_context", f"{path}.attrs.{name}",
                "RoleFrame must preserve EventFrame provenance")
    if value.attrs["source_id"] != context.source_plan.source_id:
        raise RoleFrameError(
            "invalid_event_context", f"{path}.attrs.source_id",
            "RoleFrame source_id disagrees with SourcePlan")
    if value.attrs["setup_snapshot_hash"] != context.snapshot.snapshot_sha256:
        raise RoleFrameError(
            "snapshot_mismatch", f"{path}.attrs.setup_snapshot_hash",
            "RoleFrame was not built for this setup snapshot")
    if tuple(value.columns) != ROLE_FRAME_COLUMNS:
        raise RoleFrameError(
            "invalid_role_frame_schema", f"{path}.columns",
            f"columns must exactly match RoleFrame v{ROLE_FRAME_SCHEMA_VERSION}")
    mappings = {item.mapping_id: item for item in profile.mappings}
    sort_rows: list[tuple[str, dict[str, Any]]] = []
    for position in range(len(value)):
        row = value.iloc[position]
        row_path = f"{path}.rows[{position}]"
        if row["source_event_id"] != value.iloc[0]["source_event_id"]:
            raise RoleFrameError(
                "cross_event_mapper_output", f"{row_path}.source_event_id",
                "one RoleFrame may not cross source-event boundaries")
        if row["source_event_id"] != value.attrs["source_event_id"]:
            raise RoleFrameError(
                "cross_event_mapper_output", f"{row_path}.source_event_id",
                "RoleFrame row source_event_id disagrees with preserved EventFrame context")
        mapping = mappings.get(row["mapping_id"])
        if mapping is None:
            raise RoleFrameError(
                "unknown_mapping", f"{row_path}.mapping_id",
                f"Profile has no mapping {row['mapping_id']!r}")
        if row["claim_ref"] != mapping.claim_ref:
            raise RoleFrameError(
                "invalid_claim_ref", f"{row_path}.claim_ref",
                "claim_ref disagrees with the Profile mapping")
        if row["claim_ref"] not in descriptor.emits:
            raise RoleFrameError(
                "unsupported_claim", f"{row_path}.claim_ref",
                "claim_ref is outside MapperDescriptor.emits")
        claim = _claim(context.snapshot, row["claim_ref"], f"{row_path}.claim_ref")
        roles = row["roles"]
        if not isinstance(roles, Mapping):
            raise RoleFrameError(
                "invalid_roles", f"{row_path}.roles", "must be a mapping")
        unknown = sorted(set(roles) - set(claim.roles))
        if unknown:
            raise RoleFrameError(
                "unknown_role", f"{row_path}.roles.{unknown[0]}",
                f"Claim does not declare Role {unknown[0]!r}")
        for role_id, role in claim.roles.items():
            if role.required and role_id not in roles:
                raise RoleFrameError(
                    "missing_required_role", f"{row_path}.roles.{role_id}",
                    f"Claim requires Role {role_id!r}")
            if role_id in roles:
                _validate_role_value(
                    context.snapshot, role, roles[role_id],
                    path=f"{row_path}.roles.{role_id}")
                binding = mapping.bindings.get(role_id)
                if (isinstance(binding, Mapping) and binding.get("kind") == "entity"
                        and isinstance(roles[role_id], Mapping)
                        and roles[role_id].get("type") != binding.get("entity_type")):
                    raise RoleFrameError(
                        "invalid_entity_ref", f"{row_path}.roles.{role_id}.type",
                        "entity Role type disagrees with the Profile binding")
        refs = row["source_row_refs"]
        if (not isinstance(refs, (tuple, list)) or not refs
                or any(not isinstance(item, str) or not item.strip() for item in refs)):
            raise RoleFrameError(
                "invalid_source_row_ref", f"{row_path}.source_row_refs",
                "must be a non-empty sequence of source row references")
        normalized_row = {
            "source_event_id": row["source_event_id"],
            "mapping_id": row["mapping_id"],
            "claim_ref": row["claim_ref"],
            "roles": roles,
            "source_row_refs": tuple(sorted(set(refs))),
        }
        canonical_row = dict(normalized_row)
        canonical_row["source_event_id"] = str(row["source_event_id"])
        sort_rows.append((_canonical(canonical_row, path=row_path), normalized_row))
    sorted_rows = [item[1] for item in sorted(sort_rows, key=lambda item: item[0])]
    out = pd.DataFrame({
        column: pd.Series([row[column] for row in sorted_rows], dtype=object)
        for column in ROLE_FRAME_COLUMNS
    })
    out.attrs[ROLE_FRAME_ATTR] = ROLE_FRAME_SCHEMA_VERSION
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        out.attrs[name] = value.attrs[name]
    return out


def _claim(snapshot: LedgerSetupSnapshot, claim_ref: str, path: str) -> ClaimDescriptor:
    try:
        pack_id, claim_id = claim_ref.split("/", 1)
    except (AttributeError, ValueError) as exc:
        raise RoleFrameError(
            "invalid_claim_ref", path, "claim_ref must be pack@version/claim") from exc
    pack = snapshot.packs.get(pack_id)
    if pack is None or claim_id not in pack.claims:
        raise RoleFrameError(
            "unknown_claim", path, f"unknown Claim {claim_ref!r}")
    return pack.claims[claim_id]


def _validate_role_value(
    snapshot: LedgerSetupSnapshot,
    role: RoleDescriptor,
    value: Any,
    *,
    path: str,
) -> None:
    kind = role.kind
    if _is_missing(value):
        raise RoleFrameError(
            "missing_role_value", path, "present Role values cannot be null/missing")
    if kind == "entity":
        if not isinstance(value, Mapping) or set(value) != {"type", "keys"}:
            raise RoleFrameError(
                "invalid_entity_ref", path,
                "entity Role must be exactly {'type', 'keys'}")
        entity_type = value.get("type")
        entity = snapshot.entities.get(entity_type)
        if entity is None:
            raise RoleFrameError(
                "unknown_entity_type", f"{path}.type",
                f"unknown entity type {entity_type!r}")
        keys = value.get("keys")
        if not isinstance(keys, Mapping) or set(keys) != set(entity.identity_keys):
            raise RoleFrameError(
                "invalid_entity_ref", f"{path}.keys",
                "entity keys must exactly match the registered identity keys")
        for key in entity.identity_keys:
            key_value = keys[key]
            if _is_missing(key_value) and not entity.allow_null:
                raise RoleFrameError(
                    "invalid_entity_ref", f"{path}.keys.{key}",
                    "null entity identity key is not allowed")
            _scalar(key_value, f"{path}.keys.{key}", allow_null=entity.allow_null)
        return
    if kind == "time":
        if (not isinstance(value, datetime) or value.tzinfo is None
                or _is_missing(value)):
            raise RoleFrameError(
                "invalid_time_role", path,
                "time Role must be a timezone-aware datetime")
        return
    if kind == "quantity":
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise RoleFrameError(
                "invalid_quantity_role", path, "quantity Role must be a JSON number")
        if not math.isfinite(float(value)):
            raise RoleFrameError(
                "invalid_quantity_role", path, "quantity Role must be finite")
        return
    if kind in {"identity", "order", "attribute", "symbolic"}:
        _scalar(value, path)
        if kind == "symbolic" and value not in role.allowed_values:
            raise RoleFrameError(
                "invalid_symbolic_value", path,
                f"value {value!r} is outside the registered symbolic domain")
        return
    raise RoleFrameError(
        "unsupported_role_kind", path, f"unsupported Role kind {kind!r}")


def _scalar(value: Any, path: str, *, allow_null: bool = False) -> None:
    if value is None and allow_null:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, numbers.Integral):
        return
    if isinstance(value, numbers.Real) and math.isfinite(float(value)):
        return
    if isinstance(value, str):
        return
    raise RoleFrameError(
        "invalid_scalar_role", path,
        "Role value must be a finite JSON scalar")


def compile_role_frame(context: MapperContext, role_frame: pd.DataFrame) -> pd.DataFrame:
    """Compile a normalized RoleFrame with the snapshot-owned Pack emission only."""
    normalized = validate_role_frame(context, role_frame)
    rows = []
    for position in range(len(normalized)):
        row = normalized.iloc[position]
        mapping = next(item for item in context.source_plan.profile.mappings
                       if item.mapping_id == row["mapping_id"])
        claim = _claim(context.snapshot, row["claim_ref"],
                       f"role_frame.rows[{position}].claim_ref")
        emission = claim.emission
        roles = row["roles"]
        subject = roles[emission.subject.role_id]
        occurred_at = roles[emission.occurred_at.role_id]
        obj_value = roles.get(emission.object_role.role_id)
        qualifiers = {
            name: roles[reference.role_id]
            for name, reference in emission.qualifiers.items()
            if reference.role_id in roles
        }
        predicate = context.snapshot.vocabulary.get(emission.predicate_id)
        if predicate is None or predicate.status != "active":
            raise RoleFrameError(
                "invalid_predicate", f"{claim.config_path}.emit.predicate",
                "Pack emission requires an active registered predicate")
        if subject["type"] not in predicate.subject_entity_types:
            raise RoleFrameError(
                "invalid_entity_ref", f"role_frame.rows[{position}].roles."
                f"{emission.subject.role_id}.type",
                "subject Entity type is outside the Vocabulary signature")
        if emission.object_kind != predicate.object_kind:
            raise RoleFrameError(
                "invalid_predicate", f"{claim.config_path}.emit.object.kind",
                "Pack object kind disagrees with the Vocabulary signature")
        if (emission.object_kind == "entity_ref"
                and obj_value["type"] not in predicate.object_entity_types):
            raise RoleFrameError(
                "invalid_entity_ref", f"role_frame.rows[{position}].roles."
                f"{emission.object_role.role_id}.type",
                "object Entity type is outside the Vocabulary signature")
        qualifier_names = set(qualifiers)
        required_qualifiers = set(predicate.required_qualifiers)
        allowed_qualifiers = required_qualifiers | set(predicate.optional_qualifiers)
        if not required_qualifiers <= qualifier_names:
            missing = sorted(required_qualifiers - qualifier_names)[0]
            raise RoleFrameError(
                "missing_required_payload", f"{claim.config_path}.emit.object."
                f"qualifiers.{missing}",
                f"predicate requires qualifier {missing!r}")
        if not qualifier_names <= allowed_qualifiers:
            unknown = sorted(qualifier_names - allowed_qualifiers)[0]
            raise RoleFrameError(
                "unknown_payload_field", f"{claim.config_path}.emit.object."
                f"qualifiers.{unknown}",
                f"predicate does not allow qualifier {unknown!r}")
        if emission.object_kind == "entity_ref":
            object_payload = {
                "type": obj_value["type"],
                "keys": _plain(obj_value["keys"]),
            }
        elif emission.object_kind == "value":
            object_payload = {"value": _plain(obj_value)}
        elif emission.object_kind == "event_ref":
            object_payload = {"event": _plain(obj_value)}
        else:
            raise RoleFrameError(
                "unsupported_object_kind", f"{claim.config_path}.emit.object.kind",
                f"object kind {emission.object_kind!r} is unsupported")
        if qualifiers:
            object_payload["qualifiers"] = _plain(qualifiers)
        expected_id, event_state = source_event_identity(
            context.source_plan.source_id,
            occurred_at,
            molecule_ref=str(normalized.attrs["molecule_ref"]),
            source_raw_ref=str(normalized.attrs["source_raw_ref"]),
        )
        if expected_id != row["source_event_id"]:
            raise RoleFrameError(
                "invalid_source_event",
                f"role_frame.rows[{position}].source_event_id",
                "source_event_id does not match source provenance and occurred_at Role",
            )
        rows.append({
            "source_event_id": expected_id,
            "source_event_state": event_state,
            "subject_type": subject["type"],
            "subject_keys": _plain(subject["keys"]),
            "predicate": emission.predicate_id,
            "object_kind": emission.object_kind,
            "object_payload": object_payload,
            "occurred_at": occurred_at,
            "source_who": context.source_plan.source_id,
            "source_translator_ver": (
                f"ledger-v2:{context.snapshot.snapshot_sha256}#"
                f"{mapping.mapping_id}"),
            "source_raw_ref": _claim_source_raw_ref(
                normalized.attrs["source_raw_ref"], row["source_row_refs"]),
            "supersedes": None,
            "molecule_ref": normalized.attrs["molecule_ref"],
            "derivation": mapping.mapping_id,
        })
    frame = pd.DataFrame({
        column: pd.Series([row[column] for row in rows], dtype=object)
        for column in LEDGER_FRAME_COLUMNS
    })
    frame.attrs[LEDGER_FRAME_ATTR] = LEDGER_FRAME_SCHEMA_VERSION
    return validate_ledger_frame(frame)


def _claim_source_raw_ref(event_ref: str, row_refs: Sequence[str]) -> str:
    refs = tuple(sorted(set(row_refs)))
    if refs == (event_ref,):
        return event_ref
    return json.dumps(
        {"event": event_ref, "rows": refs}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class LedgerV2DryRunResult:
    role_frame: pd.DataFrame
    ledger_frame: pd.DataFrame
    gate_preview: Mapping[str, Any]
    provenance: Mapping[str, Any]
    snapshot_hash: str


def dry_run_event_frame(
    context: MapperContext,
    event_frame: pd.DataFrame,
    implementations: RoleMapperImplementationRegistry,
) -> LedgerV2DryRunResult:
    """Use the production mapper/compiler path and return candidates without writes."""
    _validate_event_frame(
        context, event_frame, context.source_plan.driver.mapper,
        context.source_plan.profile)
    role_frame = map_event_frame(context, event_frame, implementations)
    ledger_frame = compile_role_frame(context, role_frame)
    derivations = tuple(sorted(set(ledger_frame["derivation"].tolist())))
    subjects = tuple(sorted(set(ledger_frame["subject_type"].tolist())))
    mappings = tuple(sorted(set(role_frame["mapping_id"].tolist())))
    refs = tuple(sorted({ref for values in role_frame["source_row_refs"].tolist()
                         for ref in values}))
    gate_preview = MappingProxyType({
        "status": "candidate",
        "atom_count": len(ledger_frame),
        "source_event_id": str(event_frame.attrs["source_event_id"]),
        "declared_derivations": derivations,
        "declared_subject_types": subjects,
    })
    provenance = MappingProxyType({
        "source_id": event_frame.attrs["source_id"],
        "source_event_id": str(event_frame.attrs["source_event_id"]),
        "molecule_ref": event_frame.attrs["molecule_ref"],
        "source_raw_ref": event_frame.attrs["source_raw_ref"],
        "mapping_ids": mappings,
        "source_row_refs": refs,
        "mapper_implementation": (
            f"{context.source_plan.driver.mapper.implementation.implementation_id}@"
            f"{context.source_plan.driver.mapper.implementation.implementation_version}"
        ),
        "setup_snapshot_hash": context.snapshot.snapshot_sha256,
    })
    return LedgerV2DryRunResult(
        role_frame=role_frame,
        ledger_frame=ledger_frame,
        gate_preview=gate_preview,
        provenance=provenance,
        snapshot_hash=context.snapshot.snapshot_sha256,
    )
