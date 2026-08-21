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
    ProfileSentences,
    RoleEmission,
    RoleFrameError,
    SentenceShape,
    SOURCE_OCCURRED_AT_COLUMN,
    SOURCE_ROW_REF_COLUMN,
)
from ledger.setup_registry import ProfileDescriptor
from ledger.source_preparation import (
    BaseSourcePreparer,
    PreparedJoin,
    SourcePreparationContext,
    SourcePreparationError,
    SOURCE_EVENT_INCOMPLETE_COLUMN,
    SOURCE_ROW_EXCLUDED_COLUMN,
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


class LiveLotEventSourcePreparer(BaseSourcePreparer):
    """Normalize the production physical lot_event columns before event grouping.

    The mapping is source-specific implementation code, not compiler logic.  Catalog and
    cursor plans continue to name only physical columns while Profile/Mapper contracts use
    the stable logical event vocabulary proven during Stage 6 parity.
    """

    implementation_id = "lot-event-live-frame"
    implementation_version = 1

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
        # WHICH ROWS ARE NOT OURS.  The physical table carries two generations: 80 rows
        # spell the identity `lot_id` and 61 spell it `lot` -- 1 more says neither, so 62
        # rows are excluded in total -- with the same split across
        # `slotnumbers`/`slot_numbers` and `waferids`/`wafer_ids`.  Every column this
        # preparer reads is the first spelling, so the second generation reaches the engine
        # with an empty identity.  Measured 2026-08-21 across all 26 ingested tables: six
        # carry both spellings of some word, and `lot_event` is the only one whose ROWS
        # actually split between them.  Owner ruling the same day: drop the old generation.
        #
        # The knowledge that an empty `lot` means "not this source's row" is specific to
        # this table, so it lives here and not in the common module.
        outputs[SOURCE_ROW_EXCLUDED_COLUMN] = tuple(
            not _text(value) for value in normalized["lot"].tolist())
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
    """Interpret split, merge, and track-in EventFrames as registered Pack Roles.

    THE SENTENCES THIS MAPPER CAN SAY, in the mapper's own words.  Each carries the NAME
    this mapper gives it, and the Profile files under that name the mapping that realizes
    it.  Rename ``has_wafer@1`` to anything, call a Lot a Batch, re-bind every role --
    none of it reaches this file.

    Qualifier names stay because they ARE the business vocabulary: a slot is a slot, and
    "from where, to where, which wafer" is what a slot map means.  The engine checks them
    against the Claim, so a deployment that spells them differently gets a named refusal
    instead of a wrong atom.
    """

    implementation_id = "lot-event-role"
    implementation_version = 1

    # 🔴 TWO FIRST-SIGHT SENTENCES, NOT ONE SHAPE SAID TWICE (2026-08-21).  This was a
    # single `FIRST_SIGHT` steered by a `subject_type=` selector the mapper had learned
    # from the Profile, which put half the sentence's identity at the CALL SITE.  A
    # sentence is picked by its name now, so the two announcements this mapper actually
    # makes get two names.  Holder and item stay this mapper's own words -- the thing that
    # holds items in slots, and the thing it holds -- exactly as they were when they were
    # selector values; what changed is that they are said here, once, instead of being
    # looked up out of the declaration on every unit.
    #: "this holder exists".
    FIRST_SIGHT_HOLDER = SentenceShape()
    #: "this item exists".
    FIRST_SIGHT_ITEM = SentenceShape()
    #: "this holder carries that item, in this slot".
    IN_SLOT = SentenceShape(qualifiers=("slot",))
    #: "this lot came out of that lot".
    DESCENT = SentenceShape()

    # Split slot-carry and merge slot-join realize the SAME Claim -- same predicate, same
    # subject/object types, same three qualifiers -- and differ only in the rule that
    # computed them, which is what each atom's `derivation` records.  Nothing about their
    # structure tells them apart, which is why structure stopped being how a sentence is
    # chosen; each has a name, and the Profile files a mapping under each.  These are this
    # mapper's words, not the config's: rename anything in `ledger_config.json` and they
    # still hold.
    #: "this wafer stayed in its slot as the child was split off".
    SPLIT_SLOT_CARRY = SentenceShape(qualifiers=("from", "to", "wafer"))
    #: "this wafer moved from that slot to this one as the two lots merged".
    MERGE_SLOT_JOIN = SentenceShape(qualifiers=("from", "to", "wafer"))

    def interpret_unit(
        self,
        context: MapperContext,
        unit: pd.DataFrame,
        profile: ProfileDescriptor,
    ) -> Sequence[RoleEmission]:
        missing = sorted(
            (set(LOT_EVENT_COLUMNS)
             | {SOURCE_ROW_REF_COLUMN, SOURCE_OCCURRED_AT_COLUMN}) - set(unit.columns))
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
        all_refs = tuple(sorted(refs))
        sentences = ProfileSentences(
            context, profile, occurred_at=unit.iloc[0][SOURCE_OCCURRED_AT_COLUMN])

        emissions: list[RoleEmission] = []

        def keep(emission: RoleEmission | None) -> None:
            if emission is not None:
                emissions.append(emission)

        lots = sorted({value for value in (
            {_text(row["lot"]) for row in rows} | {parent, child}) if value})
        if not lots:
            raise RoleFrameError(
                "missing_source_identity", "event_frame.lot",
                "lot event names no Lot identity",
            )
        for lot in lots:
            keep(sentences.first_sight(self.FIRST_SIGHT_HOLDER, lot, all_refs))

        pairs_by_row: list[list[tuple[str, str]]] = []
        for position, row in enumerate(rows):
            pairs = _positional_pairs(row, path=f"event_frame.rows[{position}]")
            pairs_by_row.append(pairs)
            for slot, wafer in pairs:
                if not wafer:
                    continue
                keep(sentences.first_sight(
                    self.FIRST_SIGHT_ITEM, wafer, (refs[position],)))
                keep(sentences.say(
                    self.IN_SLOT, _text(row["lot"]), (refs[position],),
                    obj=wafer, qualifiers={"slot": slot}))

        if event_type in {"split", "merge"} and parent and child:
            keep(sentences.say(self.DESCENT, child, all_refs, obj=parent))

        if event_type == "split":
            child_position = next(
                (index for index, row in enumerate(rows)
                 if _text(row["lot"]) == child), None)
            if child_position is not None:
                for slot, wafer in pairs_by_row[child_position]:
                    if wafer and slot:
                        keep(sentences.say(
                            self.SPLIT_SLOT_CARRY, parent, (refs[child_position],),
                            obj=child,
                            qualifiers={"from": slot, "to": slot, "wafer": wafer}))
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
                        keep(sentences.say(
                            self.MERGE_SLOT_JOIN, parent,
                            (refs[parent_position], refs[child_position]),
                            obj=child,
                            qualifiers={"from": parent_slots[wafer], "to": slot,
                                        "wafer": wafer}))
        return tuple(emissions)


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
