"""Ledger v2 Stage 5 pandas source-preparation boundary.

The existing source cursor owns the base-relation read.  This module consumes that
bounded pandas batch, reads only right relations named by physically verified join
descriptors, and returns complete per-event EventFrames.  It has no cursor, gate,
LedgerStore, commit, rollback, or Atom capability.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, final
import uuid
from zoneinfo import ZoneInfo

import pandas as pd

from verified_join_contract import (
    VerifiedJoinDescriptor,
    is_physically_verified_descriptor,
)
from .envelope import source_event_identity
from .roleframe import (
    EVENT_FRAME_REQUIRED_ATTRS,
    SOURCE_EVENT_INCOMPLETE_ATTR,
    SOURCE_OCCURRED_AT_COLUMN,
    SOURCE_ROW_REF_COLUMN,
)
from .setup_registry import (
    ImplementationKey,
    LedgerSetupSnapshot,
    SourcePlan,
)


DEFAULT_JOIN_CHUNK_SIZE = 1000
PREPARATION_PROVENANCE_ATTR = "assy_manager.preparation_provenance"
PREPARATION_METRICS_ATTR = "assy_manager.preparation_metrics"
SOURCE_PREPARER_ATTR = "assy_manager.source_preparer"
SOURCE_EVENT_INCOMPLETE_COLUMN = "__source_event_incomplete"


class SourcePreparationError(ValueError):
    """Stable, path-addressed refusal raised before mapper/compiler execution."""

    def __init__(
        self,
        code: str,
        path: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message
        self.details = _freeze(details or {})
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.details:
            out["details"] = _plain(self.details)
        return out


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({
            str(key): _freeze(value[key]) for key in sorted(value, key=str)
        })
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
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
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        return _plain(value.to_pydatetime())
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite numbers are not deterministic JSON")
        return value
    return value


def _canonical(value: Any, *, path: str) -> str:
    try:
        return json.dumps(
            _plain(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SourcePreparationError(
            "source_preparation_incomplete", path,
            f"value is not deterministic JSON: {exc}",
        ) from exc


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(result, bool):
        return result
    if getattr(result, "shape", None) == ():
        return bool(result)
    return False


@dataclass(frozen=True)
class JoinRightRow:
    """One right-relation row returned for a normalized join key."""

    key: tuple[Any, ...]
    identity: Mapping[str, Any]
    values: Mapping[str, Any]
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.key:
            raise TypeError("JoinRightRow.key must not be empty")
        if not isinstance(self.identity, Mapping) or not self.identity:
            raise TypeError("JoinRightRow.identity must be a non-empty mapping")
        if not isinstance(self.values, Mapping):
            raise TypeError("JoinRightRow.values must be a mapping")
        if not isinstance(self.updated_at, datetime) or self.updated_at.tzinfo is None:
            raise TypeError("JoinRightRow.updated_at must be timezone-aware")
        object.__setattr__(self, "key", tuple(self.key))
        object.__setattr__(self, "identity", _freeze(self.identity))
        object.__setattr__(self, "values", _freeze(self.values))


class VerifiedJoinBatchReader:
    """Read-only adapter contract; callers chunk, implementations execute one SELECT."""

    def read_chunk(
        self,
        descriptor: VerifiedJoinDescriptor,
        keys: tuple[tuple[Any, ...], ...],
    ) -> Mapping[tuple[Any, ...], Sequence[JoinRightRow]]:
        raise NotImplementedError


class SQLAlchemyVerifiedJoinBatchReader(VerifiedJoinBatchReader):
    """Actual read-only adapter over the existing SQLAlchemy table models.

    It deliberately exposes no transaction methods.  The supplied session owns its
    transaction and the caller decides rollback/commit outside this object.
    """

    def __init__(self, db: Any) -> None:
        self._db = db
        self.query_count = 0

    def read_chunk(
        self,
        descriptor: VerifiedJoinDescriptor,
        keys: tuple[tuple[Any, ...], ...],
    ) -> Mapping[tuple[Any, ...], Sequence[JoinRightRow]]:
        if not is_physically_verified_descriptor(descriptor):
            raise SourcePreparationError(
                "unverified_join", "source_preparation.join_descriptor",
                "join descriptor was not issued by physical verification",
            )
        if not keys:
            return MappingProxyType({})
        if len(keys) > DEFAULT_JOIN_CHUNK_SIZE:
            raise SourcePreparationError(
                "invalid_join_batch", "source_preparation.join_keys",
                f"one read chunk cannot exceed {DEFAULT_JOIN_CHUNK_SIZE} keys",
            )

        from database import models
        import notation_norm
        from sqlalchemy import tuple_

        right = models.DYNAMIC_TABLES.get(descriptor["right_table"])
        if right is None:
            raise SourcePreparationError(
                "source_preparation_incomplete", "source_preparation.right_relation",
                f"right relation {descriptor['right_table']!r} has no table model",
            )
        pairs = tuple(descriptor["join_key"])
        raw_key_columns = [getattr(right, pair["right"]) for pair in pairs]
        key_expressions = [
            notation_norm.fold_notation_sql(column, pair.get("fold") or {})
            for column, pair in zip(raw_key_columns, pairs)
        ]
        row_id_column = getattr(right, "row_id", None)
        updated_at_column = getattr(right, "updated_at", None)
        if row_id_column is None or updated_at_column is None:
            raise SourcePreparationError(
                "source_preparation_incomplete", "source_preparation.right_relation",
                "right relation must expose row_id and updated_at provenance columns",
            )
        expose_columns = [getattr(right, name) for name in descriptor["expose"]]
        selected = raw_key_columns + [row_id_column, updated_at_column] + expose_columns
        query = self._db.query(*selected)
        if len(key_expressions) == 1:
            query = query.filter(key_expressions[0].in_([key[0] for key in keys]))
        else:
            query = query.filter(tuple_(*key_expressions).in_(list(keys)))
        query = query.order_by(*key_expressions, row_id_column)
        self.query_count += 1
        result: dict[tuple[Any, ...], list[JoinRightRow]] = {}
        for row in query.all():
            raw_key = row[:len(raw_key_columns)]
            normalized_key = tuple(
                notation_norm.fold_notation(value, pair.get("fold") or {})
                for value, pair in zip(raw_key, pairs)
            )
            offset = len(raw_key_columns)
            identity = {"row_id": row[offset]}
            updated_at = row[offset + 1]
            values = {
                name: row[offset + 2 + index]
                for index, name in enumerate(descriptor["expose"])
            }
            result.setdefault(normalized_key, []).append(JoinRightRow(
                key=normalized_key,
                identity=identity,
                values=values,
                updated_at=updated_at,
            ))
        return MappingProxyType({key: tuple(result[key]) for key in sorted(
            result, key=lambda item: _canonical(item, path="right_row.key"))})


@dataclass(frozen=True)
class PreparedJoin:
    descriptor: VerifiedJoinDescriptor
    rows: tuple[JoinRightRow, ...]

    def value(self, position: int, column: str) -> Any:
        return self.rows[position].values[column]


@dataclass(frozen=True)
class SourcePreparationContext:
    snapshot: LedgerSetupSnapshot
    source_plan: SourcePlan
    join_chunk_size: int = DEFAULT_JOIN_CHUNK_SIZE

    def __post_init__(self) -> None:
        if self.snapshot.readiness != "ready":
            raise SourcePreparationError(
                "setup_not_ready", "snapshot.readiness",
                "only a ready setup snapshot may prepare source data",
            )
        registered = self.snapshot.source_plans.get(self.source_plan.source_id)
        if registered is not self.source_plan:
            raise SourcePreparationError(
                "source_plan_mismatch", "source_plan",
                "SourcePlan must be the exact object owned by the setup snapshot",
            )
        if (not isinstance(self.join_chunk_size, int)
                or isinstance(self.join_chunk_size, bool)
                or not 1 <= self.join_chunk_size <= DEFAULT_JOIN_CHUNK_SIZE):
            raise SourcePreparationError(
                "invalid_join_batch", "source_preparation.join_chunk_size",
                f"must be an integer from 1 to {DEFAULT_JOIN_CHUNK_SIZE}",
            )


class BaseSourcePreparer:
    """Template Method: bounded DataFrame in, complete EventFrames out.

    A concrete preparer declares its OWN trusted identity through ``implementation_id``
    and ``implementation_version``; see :class:`ledger.roleframe.BaseLedgerMapper` for why
    the declaration lives on the class rather than in a hand-kept list.
    """

    #: Self-declared trusted identity; ``None`` means "not addressable from config".
    implementation_id: str | None = None
    implementation_version: int | None = None

    @final
    def prepare_batch(
        self,
        context: SourcePreparationContext,
        base_frame: pd.DataFrame,
        reader: VerifiedJoinBatchReader,
    ) -> tuple[pd.DataFrame, ...]:
        _validate_base_frame(context, base_frame)
        prepared_joins, metrics = _read_verified_joins(context, base_frame, reader)
        try:
            outputs = self.prepare_outputs(context, base_frame.copy(deep=True),
                                           prepared_joins)
        except SourcePreparationError:
            raise
        except Exception as exc:
            raise SourcePreparationError(
                "source_preparer_failed", "source_preparation.outputs",
                f"prepare_outputs raised {exc.__class__.__name__}: {exc}",
            ) from exc
        prepared = _assemble_prepared_frame(context, base_frame, outputs)
        return _event_frames(context, prepared, prepared_joins, metrics)

    def prepare_outputs(
        self,
        context: SourcePreparationContext,
        base_frame: pd.DataFrame,
        joins: Mapping[str, PreparedJoin],
    ) -> Mapping[str, Sequence[Any]]:
        raise NotImplementedError


class DirectJoinSourcePreparer(BaseSourcePreparer):
    """Default implementation for one-to-one exposed columns with no calculation.

    This is the GENERIC preparer: every declared output column must be exposed by exactly
    one inherited verified join, so it computes nothing and a source that only needs
    joined columns needs no preparer code.
    """

    implementation_id = "direct-join"
    implementation_version = 1

    def prepare_outputs(
        self,
        context: SourcePreparationContext,
        base_frame: pd.DataFrame,
        joins: Mapping[str, PreparedJoin],
    ) -> Mapping[str, Sequence[Any]]:
        outputs: dict[str, tuple[Any, ...]] = {}
        declared = context.source_plan.driver.preparation.preparer.output_columns
        for output in sorted(declared):
            candidates = [join for join in joins.values()
                          if output in join.descriptor["expose"]]
            if len(candidates) != 1:
                raise SourcePreparationError(
                    "unsupported_source_preparer_output",
                    f"source_preparation.outputs.{output}",
                    "direct preparer output must be exposed by exactly one inherited rule",
                )
            outputs[output] = tuple(
                candidates[0].value(position, output)
                for position in range(len(base_frame))
            )
        return MappingProxyType(outputs)


class SourcePreparerImplementationRegistry:
    """Sealed runtime classes keyed by trusted implementation ID/version."""

    def __init__(self) -> None:
        self._items: dict[ImplementationKey, type[BaseSourcePreparer]] = {}
        self._sealed = False

    def register(
        self,
        implementation_id: str,
        implementation_version: int,
        preparer_type: type[BaseSourcePreparer],
    ) -> None:
        if self._sealed:
            raise RuntimeError("source preparer implementation registry is sealed")
        key = ImplementationKey(implementation_id, implementation_version)
        if (not isinstance(preparer_type, type)
                or not issubclass(preparer_type, BaseSourcePreparer)):
            raise TypeError("preparer_type must inherit BaseSourcePreparer")
        for ancestor in preparer_type.__mro__:
            if ancestor is BaseSourcePreparer:
                break
            if "prepare_batch" in ancestor.__dict__:
                raise SourcePreparationError(
                    "unsupported_source_preparer_override", "preparer_type.prepare_batch",
                    "BaseSourcePreparer.prepare_batch() is final and cannot be overridden",
                )
        if key in self._items:
            raise ValueError(f"source preparer {implementation_id!r}@"
                             f"{implementation_version} is already registered")
        self._items[key] = preparer_type

    def seal(self) -> "SourcePreparerImplementationRegistry":
        self._sealed = True
        return self

    def resolve(self, key: ImplementationKey) -> BaseSourcePreparer:
        if not self._sealed:
            raise SourcePreparationError(
                "source_preparer_registry_not_sealed", "source_preparer_registry",
                "source preparer registry must be sealed before execution",
            )
        preparer_type = self._items.get(key)
        if preparer_type is None:
            raise SourcePreparationError(
                "unsupported_source_preparer_implementation",
                "source_preparer.implementation",
                f"no executable source preparer is registered for "
                f"{key.implementation_id!r}@{key.implementation_version}",
            )
        try:
            return preparer_type()
        except TypeError as exc:
            raise SourcePreparationError(
                "unsupported_source_preparer_implementation",
                "source_preparer.implementation",
                "registered source preparer must have a no-argument constructor",
            ) from exc


def base_select_columns(source_plan: SourcePlan) -> tuple[str, ...]:
    """Physical columns the existing cursor must SELECT before preparation."""
    driver = source_plan.driver
    outputs = set(driver.preparation.preparer.output_columns)
    columns = set(driver.identity) - outputs
    columns.update(set(driver.group_by) - outputs)
    columns.update(driver.order_by)
    columns.update(driver.cursor_columns)
    columns.add(driver.occurred_at.column)
    columns.update(driver.preparation.preparer.input_columns)
    columns.update(column for column in driver.mapper.input_columns
                   if column not in outputs)
    return tuple(sorted(columns))


def prepare_source_batch(
    context: SourcePreparationContext,
    base_frame: pd.DataFrame,
    reader: VerifiedJoinBatchReader,
    implementations: SourcePreparerImplementationRegistry,
) -> tuple[pd.DataFrame, ...]:
    if not isinstance(implementations, SourcePreparerImplementationRegistry):
        raise TypeError("implementations must be SourcePreparerImplementationRegistry")
    descriptor = context.source_plan.driver.preparation.preparer
    preparer = implementations.resolve(descriptor.implementation)
    return preparer.prepare_batch(context, base_frame, reader)


def _validate_base_frame(
    context: SourcePreparationContext,
    frame: Any,
) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise SourcePreparationError(
            "invalid_source_batch", "source_batch", "expected pandas.DataFrame")
    if frame.empty:
        raise SourcePreparationError(
            "invalid_source_batch", "source_batch", "source batch must not be empty")
    if frame.columns.has_duplicates:
        raise SourcePreparationError(
            "invalid_source_batch", "source_batch.columns",
            "duplicate source columns are forbidden")
    missing = [column for column in base_select_columns(context.source_plan)
               if column not in frame.columns]
    if missing:
        raise SourcePreparationError(
            "source_preparation_incomplete", "source_batch.columns",
            f"base cursor batch is missing physical columns: {missing}",
        )
    collisions = sorted(
        set(context.source_plan.driver.preparation.preparer.output_columns)
        & set(frame.columns)
    )
    if collisions:
        raise SourcePreparationError(
            "source_preparation_output_collision", "source_batch.columns",
            f"prepared outputs cannot overwrite base values: {collisions}",
        )
    driver = context.source_plan.driver
    outputs = set(driver.preparation.preparer.output_columns)
    required_physical = (set(driver.identity) | set(driver.group_by)) - outputs
    required_physical.update(driver.order_by)
    required_physical.update(driver.cursor_columns)
    required_physical.add(driver.occurred_at.column)
    for column in sorted(required_physical):
        for position, value in enumerate(frame[column].tolist()):
            if _is_missing(value) or (isinstance(value, str) and not value.strip()):
                raise SourcePreparationError(
                    "source_preparation_incomplete",
                    f"source_batch.rows[{position}].{column}",
                    "driver identity/order/cursor/time value is missing",
                )


def _normalize_key(value: Any, fold: Mapping[str, Any]) -> Any:
    import notation_norm
    return notation_norm.fold_notation(value, dict(fold))


def _read_verified_joins(
    context: SourcePreparationContext,
    frame: pd.DataFrame,
    reader: VerifiedJoinBatchReader,
) -> tuple[Mapping[str, PreparedJoin], Mapping[str, Any]]:
    if not isinstance(reader, VerifiedJoinBatchReader):
        raise TypeError("reader must implement VerifiedJoinBatchReader")
    prepared: dict[str, PreparedJoin] = {}
    total_queries = 0
    total_unique_keys = 0
    for descriptor in context.source_plan.driver.preparation.verified_join_descriptors:
        if not is_physically_verified_descriptor(descriptor):
            raise SourcePreparationError(
                "unverified_join", "source_preparation.join_descriptor",
                "join descriptor was not issued by physical verification",
            )
        keys: list[tuple[Any, ...]] = []
        for position in range(len(frame)):
            values = []
            for pair_index, pair in enumerate(descriptor["join_key"]):
                column = pair["left"]
                value = frame.iloc[position][column]
                if _is_missing(value):
                    raise SourcePreparationError(
                        "source_preparation_incomplete",
                        f"source_batch.rows[{position}].{column}",
                        "join key value is missing",
                        details={"rule_id": descriptor.rule_id,
                                 "join_key_index": pair_index},
                    )
                values.append(_normalize_key(value, pair.get("fold") or {}))
            keys.append(tuple(values))
        unique_keys = tuple(sorted(
            set(keys), key=lambda item: _canonical(item, path="source_batch.join_key")))
        total_unique_keys += len(unique_keys)
        matches: dict[tuple[Any, ...], list[JoinRightRow]] = {}
        for start in range(0, len(unique_keys), context.join_chunk_size):
            chunk = unique_keys[start:start + context.join_chunk_size]
            returned = reader.read_chunk(descriptor, chunk)
            total_queries += 1
            if not isinstance(returned, Mapping):
                raise SourcePreparationError(
                    "invalid_join_reader", "source_preparation.join_reader",
                    "read_chunk must return a mapping",
                )
            requested = set(chunk)
            for key, rows in returned.items():
                normalized_key = tuple(key)
                if normalized_key not in requested:
                    raise SourcePreparationError(
                        "invalid_join_reader", "source_preparation.join_reader",
                        "reader returned a key outside the requested chunk",
                    )
                if (isinstance(rows, (str, bytes, bytearray, Mapping))
                        or not isinstance(rows, Sequence)):
                    raise SourcePreparationError(
                        "invalid_join_reader", "source_preparation.join_reader",
                        "reader values must be sequences of JoinRightRow",
                    )
                for row in rows:
                    if not isinstance(row, JoinRightRow) or row.key != normalized_key:
                        raise SourcePreparationError(
                            "invalid_join_reader", "source_preparation.join_reader",
                            "reader row key must equal its mapping key",
                        )
                    matches.setdefault(normalized_key, []).append(row)
        selected: dict[tuple[Any, ...], JoinRightRow] = {}
        for key in unique_keys:
            rows = matches.get(key, [])
            key_path = _canonical(key, path="source_batch.join_key")
            if not rows:
                raise SourcePreparationError(
                    "source_preparation_missing",
                    f"source_preparation.join_rules.{descriptor.rule_id}.keys.{key_path}",
                    "verified right relation returned no row",
                    details={"rule_id": descriptor.rule_id, "key": key},
                )
            if len(rows) != 1:
                raise SourcePreparationError(
                    "source_preparation_ambiguous",
                    f"source_preparation.join_rules.{descriptor.rule_id}.keys.{key_path}",
                    f"verified right relation returned {len(rows)} rows",
                    details={"rule_id": descriptor.rule_id, "key": key,
                             "match_count": len(rows)},
                )
            selected[key] = rows[0]
        prepared[descriptor.rule_id] = PreparedJoin(
            descriptor=descriptor,
            rows=tuple(selected[key] for key in keys),
        )
    metrics = MappingProxyType({
        "join_queries": total_queries,
        "unique_join_keys": total_unique_keys,
        "source_rows": len(frame),
    })
    return MappingProxyType(prepared), metrics


def _assemble_prepared_frame(
    context: SourcePreparationContext,
    base: pd.DataFrame,
    outputs: Any,
) -> pd.DataFrame:
    if not isinstance(outputs, Mapping):
        raise SourcePreparationError(
            "invalid_source_preparer_output", "source_preparation.outputs",
            "prepare_outputs must return a mapping of declared columns",
        )
    declared = set(context.source_plan.driver.preparation.preparer.output_columns)
    if set(outputs) != declared:
        raise SourcePreparationError(
            "invalid_source_preparer_output", "source_preparation.outputs",
            f"output columns must exactly match the declaration: {sorted(declared)}",
        )
    out = base.copy(deep=True).reset_index(drop=True)
    for column in sorted(outputs):
        values = outputs[column]
        if (isinstance(values, (str, bytes, bytearray, Mapping))
                or not isinstance(values, Sequence) or len(values) != len(base)):
            raise SourcePreparationError(
                "invalid_source_preparer_output",
                f"source_preparation.outputs.{column}",
                "output must contain exactly one value per source row",
            )
        out[column] = list(values)
    for column in base.columns:
        if not out[column].equals(base.reset_index(drop=True)[column]):
            raise SourcePreparationError(
                "source_preparation_output_collision",
                f"source_preparation.outputs.{column}",
                "source preparer must not alter base physical values",
            )
    for column in _required_entity_columns(context.source_plan):
        if column not in out.columns:
            raise SourcePreparationError(
                "source_preparation_incomplete", f"event_frame.columns.{column}",
                "entity identity column is missing after preparation",
            )
        for position, value in enumerate(out[column].tolist()):
            if _is_missing(value) or (isinstance(value, str) and not value.strip()):
                raise SourcePreparationError(
                    "source_preparation_incomplete",
                    f"event_frame.rows[{position}].{column}",
                    "entity identity value is missing after preparation",
                )
    return out


def _required_entity_columns(source_plan: SourcePlan) -> tuple[str, ...]:
    columns: set[str] = set()
    for mapping in source_plan.profile.mappings:
        for binding in mapping.bindings.values():
            if not isinstance(binding, Mapping) or binding.get("kind") != "entity":
                continue
            for key_binding in binding.get("keys", {}).values():
                if (isinstance(key_binding, Mapping)
                        and key_binding.get("kind") == "column"):
                    columns.add(key_binding["column"])
    return tuple(sorted(columns))


def _aware_time(value: Any, timezone_name: str, path: str) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        raise SourcePreparationError(
            "source_preparation_incomplete", path,
            "occurred_at value must be datetime",
        )
    if value.tzinfo is None:
        try:
            value = value.replace(tzinfo=ZoneInfo(timezone_name))
        except Exception as exc:
            raise SourcePreparationError(
                "source_preparation_incomplete", path,
                f"declared timezone {timezone_name!r} cannot be applied",
            ) from exc
    return value


def _event_frames(
    context: SourcePreparationContext,
    prepared: pd.DataFrame,
    joins: Mapping[str, PreparedJoin],
    metrics: Mapping[str, Any],
) -> tuple[pd.DataFrame, ...]:
    plan = context.source_plan
    driver = plan.driver
    if driver.unit == "row":
        groups = [[position] for position in range(len(prepared))]
    else:
        grouped: dict[str, list[int]] = {}
        for position in range(len(prepared)):
            identity = {}
            for column in driver.group_by:
                value = prepared.iloc[position][column]
                if _is_missing(value) or (isinstance(value, str) and not value.strip()):
                    raise SourcePreparationError(
                        "source_preparation_incomplete",
                        f"event_frame.rows[{position}].{column}",
                        "prepared event group identity is missing",
                    )
                identity[column] = value
            token = _canonical(identity, path=f"source_batch.rows[{position}]")
            grouped.setdefault(token, []).append(position)
        # The existing cursor supplies rows in declared order_by order.  Preserve the
        # first occurrence of each complete event so stateful kernel concerns such as
        # first-sight registration follow the same deterministic driver order.
        groups = list(grouped.values())
    events = []
    for positions in groups:
        event = prepared.iloc[positions].copy(deep=True).reset_index(drop=True)
        incomplete = False
        if SOURCE_EVENT_INCOMPLETE_COLUMN in event.columns:
            values = event[SOURCE_EVENT_INCOMPLETE_COLUMN].tolist()
            if (any(not isinstance(value, bool) for value in values)
                    or len(set(values)) != 1):
                raise SourcePreparationError(
                    "source_preparation_incomplete",
                    f"event_frame.{SOURCE_EVENT_INCOMPLETE_COLUMN}",
                    "event incomplete marker must be one consistent boolean",
                )
            incomplete = values[0]
        identity: dict[str, Any] = {}
        for column in driver.identity:
            for position in positions:
                value = prepared.iloc[position][column]
                if _is_missing(value) or (isinstance(value, str) and not value.strip()):
                    raise SourcePreparationError(
                        "source_preparation_incomplete",
                        f"event_frame.rows[{position}].{column}",
                        "prepared event identity is missing",
                    )
            values = {
                _canonical(prepared.iloc[position][column],
                           path=f"source_batch.rows[{position}].{column}")
                for position in positions
            }
            if len(values) != 1:
                raise SourcePreparationError(
                    "source_preparation_incomplete", f"event_frame.identity.{column}",
                    "one source event has more than one identity value",
                )
            identity[column] = prepared.iloc[positions[0]][column]
        # ONE read of the declared time origin. Both the published cell and the instant
        # the event id is minted from come off this list, so they cannot be a pair of
        # reads that disagree.
        occurred_cells = [
            prepared.iloc[position][driver.occurred_at.column]
            for position in positions
        ]
        occurred_values = [
            _aware_time(
                value,
                driver.occurred_at.timezone,
                f"source_batch.rows[{position}].{driver.occurred_at.column}",
            )
            for position, value in zip(positions, occurred_cells)
        ]
        instants = {value.timestamp() for value in occurred_values}
        if len(instants) != 1:
            raise SourcePreparationError(
                "source_preparation_incomplete", "event_frame.occurred_at",
                "one source event must have exactly one occurred_at instant",
            )
        row_refs = []
        for position in positions:
            order = {column: prepared.iloc[position][column]
                     for column in driver.order_by}
            row_refs.append(
                f"{plan.relation}:" + _canonical(order, path="source_row_ref"))
        if len(set(row_refs)) != len(row_refs):
            raise SourcePreparationError(
                "source_preparation_incomplete", "event_frame.source_row_refs",
                "driver order_by columns do not uniquely identify source rows",
            )
        event[SOURCE_ROW_REF_COLUMN] = row_refs
        # Publish the event's time under ONE engine-owned name.  A mapper that had to ask
        # `source_plan.driver.occurred_at.column` was reading a physical column name, so a
        # source declaring `basis` moved the time out from under it; resolving a
        # declaration to a column is this boundary's job, and now it is only this
        # boundary's job.
        #
        # The published cell is the value AS READ, not `occurred_values[0]`.  The two
        # differ in exactly one case: a naive cell, which `_aware_time` localizes with the
        # declared timezone for the id while the Role validator refuses it outright
        # ("time Role must be a timezone-aware datetime").  Publishing the localized
        # instant would make that refusal disappear -- a source whose time column carries
        # no zone would start minting atoms at a GUESSED instant, silently.  Whether the
        # declared timezone may interpret a naive column is a separate ruling; this change
        # moves where a mapper reads the time, not what the time is allowed to be.
        #
        # object dtype so the exact cell survives instead of being re-derived through a
        # pandas datetime64 conversion.
        event[SOURCE_OCCURRED_AT_COLUMN] = pd.Series(
            [occurred_cells[0]] * len(event), index=event.index, dtype=object)
        molecule_ref = _canonical(
            {"source": plan.source_id, "identity": identity},
            path="event_frame.molecule_ref",
        )
        provenance_base = []
        for rule_id in sorted(joins):
            join = joins[rule_id]
            seen: set[str] = set()
            for position in positions:
                row = join.rows[position]
                identity_token = _canonical(row.identity, path="right_row.identity")
                if identity_token in seen:
                    continue
                seen.add(identity_token)
                fingerprint = right_value_fingerprint(join.descriptor, row)
                provenance_base.append({
                    "rule_id": rule_id,
                    "right_relation": join.descriptor["right_table"],
                    "join_key": _plain(row.key),
                    "right_identity": _plain(row.identity),
                    "right_value_fingerprint": fingerprint,
                    "right_updated_at": row.updated_at.isoformat(),
                    "preparer": (
                        f"{driver.preparation.preparer.preparer_id}#"
                        f"{driver.preparation.preparer.implementation.implementation_id}@"
                        f"{driver.preparation.preparer.implementation.implementation_version}"
                    ),
                })
        # The raw evidence reference binds the base rows and every right-side proof.
        # RoleFrame only promises to preserve the canonical source_raw_ref attribute, so
        # keeping the join proof here prevents it from disappearing at the compiler edge.
        source_raw_ref = _canonical(
            {"relation": plan.relation, "rows": sorted(row_refs),
             "verified_joins": provenance_base},
            path="event_frame.source_raw_ref",
        )
        event_id, _state = source_event_identity(
            plan.source_id, occurred_values[0], molecule_ref=molecule_ref,
            source_raw_ref=source_raw_ref,
        )
        provenance = tuple({
            "source_id": plan.source_id,
            "source_event_id": str(event_id),
            **item,
        } for item in provenance_base)
        event.attrs.update({
            "source_id": plan.source_id,
            "source_event_id": event_id,
            "molecule_ref": molecule_ref,
            "source_raw_ref": source_raw_ref,
            "setup_snapshot_hash": context.snapshot.snapshot_sha256,
            PREPARATION_PROVENANCE_ATTR: provenance,
            PREPARATION_METRICS_ATTR: _plain(metrics),
            SOURCE_PREPARER_ATTR: (
                f"{driver.preparation.preparer.preparer_id}#"
                f"{driver.preparation.preparer.implementation.implementation_id}@"
                f"{driver.preparation.preparer.implementation.implementation_version}"
            ),
            SOURCE_EVENT_INCOMPLETE_ATTR: incomplete,
        })
        missing_attrs = [name for name in EVENT_FRAME_REQUIRED_ATTRS
                         if name not in event.attrs]
        if missing_attrs:
            raise AssertionError(f"internal EventFrame attrs missing: {missing_attrs}")
        events.append(event)
    return tuple(events)


def right_value_fingerprint(
    descriptor: VerifiedJoinDescriptor,
    row: JoinRightRow,
) -> str:
    canonical = _canonical({
        "rule_id": descriptor.rule_id,
        "right_relation": descriptor["right_table"],
        "right_identity": row.identity,
        "values": row.values,
        "updated_at": row.updated_at,
    }, path="right_row")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dependency_replay_worklist(
    preparation_provenance: Sequence[Mapping[str, Any]],
    right_changes: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    """Pure worklist candidates for already-successful events whose right row changed."""
    changes = {}
    for change in right_changes:
        key = (
            str(change.get("rule_id") or ""),
            _canonical(change.get("right_identity") or {}, path="right_change.identity"),
        )
        new_fingerprint = str(change.get("right_value_fingerprint") or "").strip()
        if not key[0] or not new_fingerprint:
            raise SourcePreparationError(
                "source_preparation_incomplete", "right_changes",
                "right change requires rule_id, right_identity, and fingerprint",
            )
        changes[key] = new_fingerprint
    candidates = []
    for item in preparation_provenance:
        key = (
            str(item.get("rule_id") or ""),
            _canonical(item.get("right_identity") or {}, path="provenance.identity"),
        )
        new_fingerprint = changes.get(key)
        old_fingerprint = str(item.get("right_value_fingerprint") or "")
        if new_fingerprint and new_fingerprint != old_fingerprint:
            candidates.append(MappingProxyType({
                "action": "dependency_replay",
                "source_id": item.get("source_id"),
                "source_event_id": item.get("source_event_id"),
                "rule_id": item.get("rule_id"),
                "right_identity": _freeze(item.get("right_identity") or {}),
                "previous_fingerprint": old_fingerprint,
                "current_fingerprint": new_fingerprint,
            }))
    return tuple(sorted(candidates, key=lambda item: _canonical(
        item, path="dependency_replay")))


def preparation_action_candidate(
    error: SourcePreparationError,
    *,
    source_id: str,
) -> Mapping[str, Any] | None:
    action = {
        "source_preparation_missing": "target_mapping_missing",
        "source_preparation_incomplete": "target_mapping_missing",
        "source_preparation_ambiguous": "target_mapping_ambiguous",
    }.get(error.code)
    if action is None:
        return None
    return MappingProxyType({
        "action": action,
        "source_id": source_id,
        "error": _freeze(error.to_mapping()),
    })
