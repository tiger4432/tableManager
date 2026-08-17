"""Ledger v2 Role mapper for one prepared ``lot_event`` source event.

The preparer only derives the multi-row event key.  The mapper performs the domain
interpretation that cannot be expressed as independent column bindings: split/merge
pairing, positional slot lists, and first-sight registration candidates.  It emits only
``RoleEmission`` records; Pack compilation remains the sole owner of Ledger payloads.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from types import MappingProxyType
from typing import Any

import pandas as pd

from ledger.roleframe import (
    BaseLedgerMapper,
    MapperContext,
    RoleEmission,
    RoleFrameError,
    SOURCE_ROW_REF_COLUMN,
)
from ledger.setup_registry import ClaimDescriptor, ProfileDescriptor, ProfileMappingDescriptor
from ledger.source_preparation import (
    BaseSourcePreparer,
    PreparedJoin,
    SourcePreparationContext,
    SourcePreparationError,
    SOURCE_EVENT_INCOMPLETE_COLUMN,
)


LOT_EVENT_COLUMNS = (
    "lot", "event_type", "slots", "wafers", "parent_lot", "child_lot",
    "row_identity", "event_time",
)
EVENT_GROUP_COLUMN = "event_group_key"
LIVE_LOT_EVENT_INPUT_COLUMNS = (
    "lot_id", "event_type", "slotnumbers", "waferids", "parent_lot",
    "child_lot", "txn_seq", "event_time",
)
LIVE_LOT_EVENT_OUTPUT_MAP = MappingProxyType({
    "lot": "lot_id",
    "slots": "slotnumbers",
    "wafers": "waferids",
    "row_identity": "txn_seq",
})


class LotEventSourcePreparer(BaseSourcePreparer):
    """Derive one stable group key for both rows of a split or merge."""

    def prepare_outputs(
        self,
        context: SourcePreparationContext,
        base_frame: pd.DataFrame,
        joins: Mapping[str, PreparedJoin],
    ) -> Mapping[str, Sequence[Any]]:
        if joins:
            raise SourcePreparationError(
                "unsupported_source_preparation",
                "source_preparation.join_rules",
                "lot_event preparation does not accept virtual joins",
            )
        declared = set(
            context.source_plan.driver.preparation.preparer.output_columns)
        if declared != {EVENT_GROUP_COLUMN, SOURCE_EVENT_INCOMPLETE_COLUMN}:
            raise SourcePreparationError(
                "unsupported_source_preparer_output",
                "source_preparation.outputs",
                "lot_event preparer requires event group and incomplete outputs",
            )
        missing = sorted(set(LOT_EVENT_COLUMNS) - set(base_frame.columns))
        if missing:
            raise SourcePreparationError(
                "source_preparation_incomplete",
                "source_batch.columns",
                f"lot_event source columns are missing: {missing}",
            )
        return _event_outputs(base_frame)


class LiveLotEventSourcePreparer(BaseSourcePreparer):
    """Normalize the production physical lot_event columns before event grouping.

    The mapping is source-specific implementation code, not compiler logic.  Catalog and
    cursor plans continue to name only physical columns while Profile/Mapper contracts use
    the stable logical event vocabulary proven during Stage 6 parity.
    """

    def prepare_outputs(
        self,
        context: SourcePreparationContext,
        base_frame: pd.DataFrame,
        joins: Mapping[str, PreparedJoin],
    ) -> Mapping[str, Sequence[Any]]:
        if joins:
            raise SourcePreparationError(
                "unsupported_source_preparation",
                "source_preparation.join_rules",
                "lot_event preparation does not accept virtual joins",
            )
        missing = sorted(set(LIVE_LOT_EVENT_INPUT_COLUMNS) - set(base_frame.columns))
        if missing:
            raise SourcePreparationError(
                "source_preparation_incomplete",
                "source_batch.columns",
                f"live lot_event source columns are missing: {missing}",
            )
        normalized = base_frame.copy(deep=False).rename(columns={
            physical: logical
            for logical, physical in LIVE_LOT_EVENT_OUTPUT_MAP.items()
        })
        group_outputs = _event_outputs(normalized)
        outputs = {
            logical: tuple(base_frame[physical].tolist())
            for logical, physical in LIVE_LOT_EVENT_OUTPUT_MAP.items()
        }
        outputs.update(group_outputs)
        declared = set(
            context.source_plan.driver.preparation.preparer.output_columns)
        if set(outputs) != declared:
            raise SourcePreparationError(
                "unsupported_source_preparer_output",
                "source_preparation.outputs",
                "live lot_event preparer declaration disagrees with its normalized outputs",
            )
        return MappingProxyType(outputs)


class LotEventRoleMapper(BaseLedgerMapper):
    """Interpret split, merge, and track-in EventFrames as registered Pack Roles."""

    def interpret_unit(
        self,
        context: MapperContext,
        unit: pd.DataFrame,
        profile: ProfileDescriptor,
    ) -> Sequence[RoleEmission]:
        missing = sorted(
            (set(LOT_EVENT_COLUMNS) | {SOURCE_ROW_REF_COLUMN}) - set(unit.columns))
        if missing:
            raise RoleFrameError(
                "missing_mapper_input", "event_frame.columns",
                f"lot_event mapper columns are missing: {missing}",
            )
        rows = [
            {column: _plain(unit.iloc[position][column]) for column in LOT_EVENT_COLUMNS}
            for position in range(len(unit))
        ]
        keys = {
            _event_key(row, path=f"mapper.rows[{position}]")
            for position, row in enumerate(rows)
        }
        if len(keys) != 1:
            raise RoleFrameError(
                "invalid_source_event_boundary", "event_frame",
                f"mapper received {len(keys)} source events; expected one",
            )
        event_type, _event_time, parent, child, ambiguous = _decode_event_key(
            next(iter(keys)))
        if ambiguous is not None:
            raise RoleFrameError(
                "ambiguous_source_event", "event_frame",
                "one row declares both parent_lot and child_lot",
            )
        if event_type not in {"split", "merge", "track_in"}:
            raise RoleFrameError(
                "undeclared_source_vocabulary", "event_frame.event_type",
                f"unsupported lot event type {event_type!r}",
            )

        refs = tuple(str(value) for value in unit[SOURCE_ROW_REF_COLUMN].tolist())
        occurred_at = unit.iloc[0]["event_time"]
        all_refs = tuple(sorted(refs))
        emissions: list[RoleEmission] = []
        registered: set[tuple[str, str]] = set()

        def emit(
            predicate: str,
            subject_type: str,
            subject_value: Any,
            source_refs: Sequence[str],
            *,
            object_type: str | None = None,
            object_value: Any = None,
            qualifiers: Mapping[str, Any] | None = None,
            mapping_hint: str | None = None,
        ) -> None:
            mapping, claim = _resolve_mapping(
                context, profile, predicate=predicate, subject_type=subject_type,
                mapping_hint=mapping_hint)
            roles: dict[str, Any] = {
                claim.emission.subject.role_id: _entity_for_role(
                    mapping, claim.emission.subject.role_id, subject_value),
                claim.emission.occurred_at.role_id: occurred_at,
            }
            if claim.emission.object_role is not None:
                if object_type is None:
                    raise RoleFrameError(
                        "invalid_lot_event_contract", mapping.config_path,
                        f"predicate {predicate!r} requires an object Entity",
                    )
                roles[claim.emission.object_role.role_id] = _entity_for_role(
                    mapping, claim.emission.object_role.role_id, object_value,
                    expected_type=object_type)
            qualifier_values = dict(qualifiers or {})
            if set(qualifier_values) != set(claim.emission.qualifiers):
                raise RoleFrameError(
                    "invalid_lot_event_contract", mapping.config_path,
                    f"predicate {predicate!r} qualifier contract disagrees with mapper",
                )
            for name, reference in claim.emission.qualifiers.items():
                roles[reference.role_id] = qualifier_values[name]
            emissions.append(RoleEmission(
                mapping_id=mapping.mapping_id,
                claim_ref=mapping.claim_ref,
                roles=roles,
                source_row_refs=tuple(source_refs),
            ))

        lots = sorted({value for value in (
            {_text(row["lot"]) for row in rows} | {parent, child}) if value})
        if not lots:
            raise RoleFrameError(
                "missing_source_identity", "event_frame.lot",
                "lot event names no Lot identity",
            )
        for lot in lots:
            _register_once(
                registered, emissions, context, profile, "Lot", lot,
                occurred_at, all_refs)

        pairs_by_row: list[list[tuple[str, str]]] = []
        for position, row in enumerate(rows):
            pairs = _positional_pairs(row, path=f"event_frame.rows[{position}]")
            pairs_by_row.append(pairs)
            for slot, wafer in pairs:
                if not wafer:
                    continue
                _register_once(
                    registered, emissions, context, profile, "Wafer", wafer,
                    occurred_at, (refs[position],))
                emit(
                    "has_wafer", "Lot", _text(row["lot"]), (refs[position],),
                    object_type="Wafer", object_value=wafer,
                    qualifiers={"slot": slot},
                    mapping_hint="positional_row",
                )

        if event_type in {"split", "merge"}:
            if not parent or not child:
                pass
            else:
                emit(
                    "derived_from", "Lot", child, all_refs,
                    object_type="Lot", object_value=parent,
                    mapping_hint="pair_field",
                )

        if event_type == "split":
            child_position = next(
                (index for index, row in enumerate(rows)
                 if _text(row["lot"]) == child), None)
            if child_position is not None:
                for slot, wafer in pairs_by_row[child_position]:
                    if wafer and slot:
                        emit(
                            "slot_map", "Lot", parent, (refs[child_position],),
                            object_type="Lot", object_value=child,
                            qualifiers={"from": slot, "to": slot, "wafer": wafer},
                            mapping_hint="slot_preserving",
                        )
        elif event_type == "merge":
            parent_position = next(
                (index for index, row in enumerate(rows)
                 if _text(row["lot"]) == parent), None)
            child_position = next(
                (index for index, row in enumerate(rows)
                 if _text(row["lot"]) == child), None)
            if parent_position is not None and child_position is not None:
                parent_slots = {
                    wafer: slot for slot, wafer in pairs_by_row[parent_position] if wafer}
                for slot, wafer in pairs_by_row[child_position]:
                    if wafer and wafer in parent_slots:
                        emit(
                            "slot_map", "Lot", parent,
                            (refs[parent_position], refs[child_position]),
                            object_type="Lot", object_value=child,
                            qualifiers={"from": parent_slots[wafer], "to": slot,
                                        "wafer": wafer},
                            mapping_hint="shared_wafer",
                        )
        return tuple(emissions)


def _register_once(
    memo: set[tuple[str, str]],
    emissions: list[RoleEmission],
    context: MapperContext,
    profile: ProfileDescriptor,
    entity_type: str,
    value: Any,
    occurred_at: Any,
    refs: Sequence[str],
) -> None:
    token = (entity_type, json.dumps(value, ensure_ascii=False, sort_keys=True))
    if token in memo:
        return
    memo.add(token)
    mapping, claim = _resolve_mapping(
        context, profile, predicate="register", subject_type=entity_type,
        mapping_hint=("first_sight_lot" if entity_type == "Lot"
                      else "first_sight_wafer"))
    roles = {
        claim.emission.subject.role_id: _entity_for_role(
            mapping, claim.emission.subject.role_id, value),
        claim.emission.occurred_at.role_id: occurred_at,
    }
    emissions.append(RoleEmission(
        mapping_id=mapping.mapping_id,
        claim_ref=mapping.claim_ref,
        roles=roles,
        source_row_refs=tuple(refs),
    ))


def _resolve_mapping(
    context: MapperContext,
    profile: ProfileDescriptor,
    *,
    predicate: str,
    subject_type: str,
    mapping_hint: str | None = None,
) -> tuple[ProfileMappingDescriptor, ClaimDescriptor]:
    matches: list[tuple[ProfileMappingDescriptor, ClaimDescriptor]] = []
    for mapping in profile.mappings:
        pack_id, claim_id = mapping.claim_ref.split("/", 1)
        pack = context.snapshot.packs.get(pack_id)
        if pack is None or claim_id not in pack.claims:
            continue
        claim = pack.claims[claim_id]
        subject_binding = mapping.bindings.get(claim.emission.subject.role_id)
        if (_base(claim.emission.predicate_id) == predicate
                and isinstance(subject_binding, Mapping)
                and subject_binding.get("kind") == "entity"
                and _base(subject_binding.get("entity_type")) == subject_type):
            matches.append((mapping, claim))
    if mapping_hint is not None:
        matches = [item for item in matches if item[0].mapping_id == mapping_hint]
    if len(matches) != 1:
        raise RoleFrameError(
            "invalid_lot_event_contract", profile.config_path,
            f"expected one {predicate!r}/{subject_type!r} mapping, found {len(matches)}",
        )
    return matches[0]


def _entity_for_role(
    mapping: ProfileMappingDescriptor,
    role_id: str,
    value: Any,
    *,
    expected_type: str | None = None,
) -> Mapping[str, Any]:
    binding = mapping.bindings.get(role_id)
    if not isinstance(binding, Mapping) or binding.get("kind") != "entity":
        raise RoleFrameError(
            "invalid_lot_event_contract", f"{mapping.config_path}.bind.{role_id}",
            "lot_event Entity Role requires an entity binding",
        )
    entity_type = binding.get("entity_type")
    if expected_type is not None and _base(entity_type) != expected_type:
        raise RoleFrameError(
            "invalid_lot_event_contract", f"{mapping.config_path}.bind.{role_id}",
            f"expected Entity type {expected_type!r}",
        )
    keys = binding.get("keys")
    if not isinstance(keys, Mapping) or len(keys) != 1:
        raise RoleFrameError(
            "invalid_lot_event_contract", f"{mapping.config_path}.bind.{role_id}.keys",
            "lot_event v1 supports one identity key per Lot/Wafer Entity",
        )
    key = next(iter(keys))
    return {"type": entity_type, "keys": {key: value}}


def _event_outputs(frame: pd.DataFrame) -> Mapping[str, Sequence[Any]]:
    keys = tuple(
        _event_key(frame.iloc[position], path=f"source_batch.rows[{position}]")
        for position in range(len(frame))
    )
    groups: dict[str, list[int]] = {}
    for position, key in enumerate(keys):
        groups.setdefault(key, []).append(position)
    incomplete_by_key = {}
    for key, positions in groups.items():
        event_type, _time, parent, child, ambiguous = _decode_event_key(key)
        lots = {_text(frame.iloc[position]["lot"]) for position in positions}
        incomplete_by_key[key] = bool(
            ambiguous is None and event_type in {"split", "merge"}
            and (not parent or not child or parent not in lots or child not in lots))
    return MappingProxyType({
        EVENT_GROUP_COLUMN: keys,
        SOURCE_EVENT_INCOMPLETE_COLUMN: tuple(
            incomplete_by_key[key] for key in keys),
    })


def _event_key(row: Mapping[str, Any] | pd.Series, *, path: str) -> str:
    lot = _text(row["lot"])
    parent = _text(row["parent_lot"])
    child = _text(row["child_lot"])
    event_type = _text(row["event_type"])
    event_time = _plain(row["event_time"])
    ambiguous = _text(row["row_identity"]) if parent and child else None
    if parent and child:
        values = (event_type, event_time, parent, child, ambiguous)
    elif parent:
        values = (event_type, event_time, parent, lot, None)
    elif child:
        values = (event_type, event_time, lot, child, None)
    else:
        values = (event_type, event_time, None, lot, None)
    try:
        return json.dumps(
            values, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            default=lambda value: value.isoformat(),
        )
    except (TypeError, ValueError) as exc:
        raise SourcePreparationError(
            "source_preparation_incomplete", path,
            f"lot event identity is not deterministic JSON: {exc}",
        ) from exc


def _decode_event_key(value: str) -> tuple[Any, ...]:
    decoded = json.loads(value)
    return tuple(decoded)


def _positional_pairs(row: Mapping[str, Any], *, path: str) -> list[tuple[str, str]]:
    slots = _split(row["slots"])
    wafers = _split(row["wafers"])
    if len(slots) != len(wafers):
        raise RoleFrameError(
            "invalid_positional_list", path,
            f"slots has {len(slots)} entries but wafers has {len(wafers)}",
        )
    return list(zip(slots, wafers))


def _split(value: Any) -> list[str]:
    text = _text(value)
    return [] if not text else [item.strip() for item in text.split(":")]


def _text(value: Any) -> str:
    value = _plain(value)
    return "" if value is None else str(value).strip()


def _plain(value: Any) -> Any:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, bool) and missing:
        return None
    return value


def _base(value: Any) -> str:
    return str(value or "").rsplit("@", 1)[0]
