"""Ledger v2: the cursor's page -> one EventFrame per molecule.

The existing source cursor owns the base-relation read.  This module takes that bounded
pandas page, drops the rows `read.exclude_when` says are not the source's, refuses a molecule
by name when a declared cell is empty, and returns complete per-event EventFrames.  It has no
cursor, gate, LedgerStore, commit, rollback, or Atom capability.

⚰️ [총괄 e14416950] THE PREPARER IS GONE: a declaration's `prepare` section, its python
implementations and the read-time verified joins it carried. The one working preparer
(lot_event's) moved to the chain - computation writes a table, the ledger reads it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import json
import math
from types import MappingProxyType
from typing import Any
import uuid

import pandas as pd

from .envelope import source_event_identity
from .roleframe import aware_time as roleframe_aware_time
from .roleframe import (
    EVENT_FRAME_REQUIRED_ATTRS,
    SOURCE_OCCURRED_AT_COLUMN,
    SOURCE_ROW_REF_COLUMN,
    _is_missing,
    _unit_says,
    read_columns_once,
)
from .setup_bundle import entity_type_column, exclusion_columns
from .setup_registry import (
    LedgerSetupSnapshot,
    SourcePlan,
)
from declaration_names import bare_name


#: The frame column of every dynamic table, read by the ENGINE rather than by a declaration
#: (판정 135, 2026-09-08).
#:
#: 🔴 IT IS NOT AN ENGINE-INVENTED NAME -- it is a real physical column,
#: and `table_config` gives it to all 44 relations. What is engine-owned is the DECISION to
#: read it: a source that never names `row_id` in its `read` still needs it, because the
#: ledger has to be able to say which physical row an atom came from when that row is
#: DELETED and there is nothing left to translate.
#:
#: 🔬 MEASURED BEFORE IT WAS ADDED: of the 15 shipped sources, FOUR carried `row_id` into the
#: read and eleven did not -- the four only because their `order_by` or a mapper input
#: happened to name it. Ruling 132 had assumed all of them did. Building on that would have
#: given eleven sources a delete path that silently did nothing, and the first fixture the
#: ruling named sits inside the lucky four, so measuring only there would have passed.
#:
#: ⚰️ 판정 136 narrowed this to 「a source whose relation has one」, for view sources. Those are
#: refused at load now (총괄 f3bc02f6e), so every planned source's relation has `row_id` again.
#:
#: ⚠️ IT GOES IN `base_select_columns` AND NOT IN `bound_select_columns`: no binding names it,
#: so it is not in the row print either.
FRAME_ROW_ID_COLUMN = "row_id"

#: 🔴 A STORED SPELLING, NOT A MECHANISM. Every atom stores its event's `source_raw_ref`
#: (`roleframe._claim_source_raw_ref`), and that text sits under an md5 unique index. It
#: carried the read-time join proofs, always `[]` once those retired (86d598fb5). Dropping
#: the key would re-spell the ref of every atom on its next translation, so the same fact
#: would land as a second atom. The key stays, empty, for that reason alone.
STORED_RAW_REF_JOINS: tuple = ()

#: ⚠️ `source_preparation_incomplete` (the refusal code below) and `SourcePreparationError`
#: keep the retired module's name: a wire code is an identity (총괄 ae3d408ae ⑤).


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


def is_blank_source_value(value: Any) -> bool:
    """"Empty" as this seam spells it: missing, or a string with nothing but space.

    🔴 ONE FUNCTION BECAUSE TWO SPELLINGS DISAGREE EXACTLY WHERE THE QUESTION LIVES
    (판정 194 ㉢). `count_rows_missing` already wrote `_is_missing(v) or (isinstance(v, str)
    and not v.strip())` at its own call site, and `exclude_when` needs the same sentence.
    Left as two, the day one of them learns about a new empty shape is the day an operator
    is told "3 of 200 rows are blank" by one and "0" by the other, about the same rows.

    ⚠️ WHITESPACE IS NOT `_is_missing`'S JOB. That one answers "is this value absent",
    which a `"  "` is not - it is a present string. This is the IDENTITY question layered
    on top: a key part made of spaces names nothing.
    """
    return _is_missing(value) or (isinstance(value, str) and not value.strip())


def row_excluded(clauses: Sequence[Mapping[str, Any]], value_of) -> bool:
    """Does `read.exclude_when` take this row out - ANY clause: its column blank, or its `when`
    matched the way a mapping's `when` is (`_unit_says`, one spelling of equality) - so a row whose
    column is empty is not taken out by a value (총괄 e91433bf1). `value_of(column)` reads the row.
    The page and the backfill's census ask this one function."""
    for clause in clauses:
        when = clause.get("when")
        if when is not None:
            if _unit_says({column: (value_of(column),) for column in when}, when):
                return True
        elif is_blank_source_value(value_of(clause["column"])):
            return True
    return False


@dataclass(frozen=True)
class MoleculeRefusal:
    """One molecule the preparation could not build, named the way the GATE names it.

    🔴 THE NAME COMES FROM `ledger.gate.REFUSAL_REASONS` AND IS NOT INVENTED HERE. The
    gatekeeper already holds a closed vocabulary of twelve and already knows these two -
    `no_identity` and `missing_occurred_at`. This module was refusing the same facts one
    layer earlier, by raising, so the same fact had two behaviours: a name and a count on
    one path, a dead page on the other.

    It is a VALUE, not a gate call. This module stays free of process counters:
    the executing caller records these, the previewing caller reports them, and neither
    has to remember which it is (see `runtime_v2`).
    """
    reason: str
    detail: str
    rows: int
    addresses: tuple = ()


@dataclass(frozen=True)
class SourcePreparationContext:
    snapshot: LedgerSetupSnapshot
    source_plan: SourcePlan
    #: Molecules refused during this preparation. Out-parameter, deliberately: the
    #: return value is EventFrames and a batch can now produce both.
    refusals: list = field(default_factory=list, compare=False, repr=False)
    #: Rows `read.exclude_when` removed, per batch. A ONE-ELEMENT LIST rather than an int
    #: because the count has three states and `0` can only say two: no entry at all means
    #: this source declares no `exclude_when` and nothing was measured, which is not the
    #: same claim as "measured, and none".
    excluded_rows: list = field(default_factory=list, compare=False, repr=False)

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


def locked_select_columns(
    *,
    identity: Sequence[str] = (),
    group_by: Sequence[str] = (),
    order_by: Sequence[str] = (),
    cursor_columns: Sequence[str] = (),
    occurred_at_column: str | None = None,
    exclude_when_columns: Sequence[str] = (),
    condition_columns: Sequence[str] = (),
    binding_columns: Sequence[str] = (),
) -> tuple[str, ...]:
    """The columns a source's declaration names - keys, order, time, exclusions, conditions,
    bindings. `bound_select_columns` feeds it from a compiled plan."""
    columns = set(identity)
    columns.update(group_by)
    columns.update(order_by)
    columns.update(cursor_columns)
    # 🔴 S-91. A column named by `exclude_when` HAS to be read, or the exclusion is asked
    # about a column that is not in the frame. It goes HERE rather than only in
    # `base_select_columns`, which is the opposite of where `FRAME_ROW_ID_COLUMN` goes -
    # and for that field's own stated reason. `row_id` is kept off this list because an
    # author did not choose it and a locked chip would offer a decision nobody has; an
    # `exclude_when` column IS chosen, so drawing it as "this arrives anyway" is true.
    #
    # ⚠️ AND THE OWNER'S OWN CASE WOULD HAVE HIDDEN THIS. There the column is `core_x`, an
    # identity part, so it is already in the first term and arrives by luck. Building
    # against that case alone runs there and silently reads a missing column everywhere
    # else.
    columns.update(exclude_when_columns)
    # 🔴 S-99, and the SAME reason as the line above. A column a sentence's `when` names is
    # not otherwise read - it is neither an identity, a key, nor anybody's declared input -
    # so without this the mapper is asked to judge a column that is not in the frame.
    columns.update(condition_columns)
    # 판정 201 · 총괄 c38eae7cf. A bound column is read because it is bound.
    columns.update(binding_columns)
    if occurred_at_column:
        columns.add(occurred_at_column)
    return tuple(sorted(columns))


def bound_select_columns(source_plan: SourcePlan) -> tuple[str, ...]:
    """The columns a source reads because its declaration names them - keys, order, time,
    exclusions, conditions, bindings - and not the rest of the relation nor `row_id`: a
    column reaches an atom only through these (판정 201). What the row print covers (총괄 (나))."""
    driver = source_plan.driver
    return locked_select_columns(
        identity=driver.identity,
        # The mapper's group is read like the source's (총괄 c38eae7cf).
        group_by=(*driver.group_by, *driver.mapper.unit_columns),
        order_by=driver.order_by,
        cursor_columns=driver.cursor_columns,
        occurred_at_column=driver.occurred_at.column,
        exclude_when_columns=[column for clause in driver.exclude_when
                              for column in exclusion_columns(clause)],
        condition_columns=sorted({
            column
            for mapping in source_plan.profile.mappings.values()
            for column in mapping.when
        }),
        # The compiler already intersected these with the catalogue.
        binding_columns=source_plan.binding_select_columns,
    )


def named_columns(source_plan: SourcePlan) -> tuple[str, ...]:
    """What the declaration names, and the engine's `row_id` (every planned source reads a table
    that has it, 총괄 f3bc02f6e) - what a frame must carry and what a row unit is ordered by
    (총괄 164553a6f). A column outside it reaches no atom (판정 201), so neither its absence nor
    its type may stop a source."""
    return tuple(sorted({*bound_select_columns(source_plan), source_plan.frame_row_id}))


def base_select_columns(source_plan: SourcePlan) -> tuple[str, ...]:
    """Physical columns the cursor asks for: every column of the relation (소유자 10-03 - the
    mapper receives them all) and the named ones. The read leaves out a catalogue column the
    table does not have (`backfill._readable_columns`)."""
    return tuple(sorted({*named_columns(source_plan), *source_plan.relation_columns}))


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
    missing = [column for column in named_columns(context.source_plan)
               if column not in frame.columns]
    if missing:
        raise SourcePreparationError(
            "source_preparation_incomplete", "source_batch.columns",
            f"base cursor batch is missing physical columns: {missing}",
        )
    driver = context.source_plan.driver
    required_physical = set(driver.identity) | set(driver.group_by)
    # 🔴 `occurred_at.column` AND `order_by` (= the cursor, `setup_bundle._derived_cursor`)
    # ARE DELIBERATELY NOT HERE ANY MORE. Each is a fact about ONE ROW with a gate name -
    # `missing_occurred_at`, `no_raw_ref` - and refusing the page threw away every other
    # molecule (box dt_log 09-30: one job's empty `dt_cell_key` stopped every follow-up of
    # it). `_refuse_molecule` answers them, where molecules exist (S-41 ②, 총괄 4b5964ab2).
    # identity and group_by stay: without them there is no molecule to name.
    for column in sorted(required_physical):
        for position, value in enumerate(frame[column].tolist()):
            if is_blank_source_value(value):
                raise SourcePreparationError(
                    "source_preparation_incomplete",
                    f"source_batch.rows[{position}].{column}",
                    "driver identity/group_by value is missing",
                )


def event_frames(
    context: SourcePreparationContext,
    base_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, ...]:
    """The cursor's page -> one EventFrame per molecule. The one entry, for every caller."""
    _validate_base_frame(context, base_frame)
    return _event_frames(context, _without_excluded_rows(context, base_frame))


def _without_excluded_rows(context: SourcePreparationContext,
                           base: pd.DataFrame) -> pd.DataFrame:
    """The page minus the rows `read.exclude_when` says are not this source's.

    A row is excluded when ANY clause takes it (`row_excluded`). The rows leave here before
    anything asks them for an identity. `lot_event` held two generations
    that spelled the same facts differently, and the old one arrived at the identity loop
    with nothing in it and refused the whole batch.

    An all-excluded page yields an EMPTY frame and no atoms rather than a refusal: pages are
    cut by the cursor, not by generation, so a page holding only old rows is normal and
    refusing would stall the backfill on it forever. The cursor advances off the base page
    (`backfill.rows_missing_from_the_index`), never off what survives here.

    🔴 COUNTED HERE BECAUSE THIS IS WHERE THEY GO. Without it the test run says "200 rows
    read, 3 molecules, 0 refused" and the screen cannot say where the other 197 went.
    """
    out = base.reset_index(drop=True)
    exclude_when = context.source_plan.driver.exclude_when
    if exclude_when:
        cells = read_columns_once(out)
        excluded = [row_excluded(exclude_when, lambda column, at=position: cells[column][at])
                    for position in range(len(out))]
        context.excluded_rows.append(sum(excluded))
        out = out.loc[[not value for value in excluded]].reset_index(drop=True)
    typed_key_columns = tuple(
        child["column"] for _mapping, _role, binding, _type in _row_typed(context.source_plan)
        for child in binding.get("keys", {}).values()
        if isinstance(child, Mapping) and child.get("kind") == "column")
    for column in _required_entity_columns(context.source_plan) + typed_key_columns:
        # 🔴 A MISSING COLUMN IS A PAGE REFUSAL AND A MISSING VALUE IS NOT. The column is a
        # fact about the DECLARATION; an empty cell is a fact about ONE ROW, and it refuses
        # that row's molecule by name in `_refuse_molecule`.
        if column not in out.columns:
            raise SourcePreparationError(
                "source_preparation_incomplete", f"event_frame.columns.{column}",
                "entity identity column is missing from the read",
            )
    return out


def _required_entity_columns(source_plan: SourcePlan) -> tuple[str, ...]:
    """The cells every row must fill to name its entities. A type read per row is its TYPE
    column here; which key columns that row needs depends on its type (`_row_type_refusal`)."""
    columns: set[str] = set()
    for mapping in source_plan.profile.mappings.values():
        for binding in mapping.bindings.values():
            if not isinstance(binding, Mapping) or binding.get("kind") != "entity":
                continue
            if entity_type_column(binding):
                columns.add(entity_type_column(binding))
                continue
            for key_binding in binding.get("keys", {}).values():
                if (isinstance(key_binding, Mapping)
                        and key_binding.get("kind") == "column"):
                    columns.add(key_binding["column"])
    return tuple(sorted(columns))


def _row_typed(source_plan: SourcePlan) -> tuple:
    """(mapping, role, binding, type column) for every role whose type is read per row."""
    return tuple(
        (mapping, role, binding, entity_type_column(binding))
        for _sentence, mapping in sorted(source_plan.profile.mappings.items())
        for role, binding in sorted(mapping.bindings.items())
        if entity_type_column(binding))


def _row_type_refusal(context, cells, positions, key):
    """A row whose type, read from a column, the predicate does not admit in that role - or
    whose own type's key cell is empty (총괄 7255b4918 ④). The type is the cell as written,
    folded by `bare_name`."""
    from .gate import REFUSE_NO_IDENTITY, REFUSE_TYPE_NOT_ADMITTED

    for mapping, role, binding, type_column in _row_typed(context.source_plan):
        if type_column not in cells:
            continue
        admitted = context.snapshot.vocabulary[mapping.predicate_id].entity_types_of(role)
        for position in positions:
            named = bare_name(str(cells[type_column][position]).strip())
            path = f"event_frame.rows[{position}].{type_column}"
            if named not in admitted:
                return MoleculeRefusal(
                    reason=REFUSE_TYPE_NOT_ADMITTED,
                    detail=(f"molecule {key}: the row at {path} names type {named!r}, which "
                            f"{mapping.predicate_id!r} does not admit as its {role} "
                            f"({', '.join(admitted)})"),
                    rows=len(positions),
                    addresses=({"code": "invalid_entity_ref", "path": path},))
            declared = context.snapshot.entities.get(named)
            for key_name in (declared.identity_keys if declared is not None else ()):
                child = binding.get("keys", {}).get(key_name)
                column = (child.get("column") if isinstance(child, Mapping)
                          and child.get("kind") == "column" else None)
                if column in cells and is_blank_source_value(cells[column][position]):
                    path = f"event_frame.rows[{position}].{column}"
                    return MoleculeRefusal(
                        reason=REFUSE_NO_IDENTITY,
                        detail=(f"molecule {key}: a row of type {named!r} needs {column!r} "
                                f"and the row at {path} leaves it empty"),
                        rows=len(positions),
                        addresses=({"code": "source_preparation_incomplete", "path": path},))
    return None


def _aware_time(value: Any, timezone_name: str, path: str) -> datetime:
    """The `occurred_at` reading, in this layer's refusal vocabulary.

    🔴 THE LOGIC MOVED AND DID NOT FORK (S-84-b, 판정 09-10 13:44). A `timestamp` VALUE
    needs exactly the reading this column has had since 2026-08-21, and the seat that
    evaluates a value binding is in `roleframe` - which this module already imports, while
    the reverse would be a cycle. So the parse lives there and this stays as the thin
    boundary that names the refusal the way this module's callers expect: two
    layers refusing in their own words, one function deciding what a timestamp IS.
    """
    return roleframe_aware_time(
        value, timezone_name, path,
        error=lambda code, at, message: SourcePreparationError(
            "source_preparation_incomplete", at,
            "occurred_at value must be datetime" if code == "invalid_time_value"
            and "datetime" in message else message))


def _molecule_key(driver, cells, positions) -> str:
    """What the operator has to look up to find this molecule.

    `group_by` when the source declares one - that IS the molecule's name there. A
    row-unit source has none, so the row's position in the page is the only handle the
    refusal can offer.
    """
    if driver.group_by:
        return _canonical(
            {column: _plain(cells[column][positions[0]])
             for column in driver.group_by},
            path="event_frame.molecule")
    return f"rows[{positions[0]}]"


def _refuse_molecule(context, cells, positions) -> "MoleculeRefusal | None":
    """The empty declared value that stops THIS molecule, or None.

    🔴 THE UNIT IS THE MOLECULE, FOR BOTH FACTS (ruling 116). Time forces it: the event's
    instant is read from EVERY row of the group in one pass, so a row with no time does
    not make the event smaller, it makes it unbuildable. Refusing identity per row while
    refusing time per molecule would put two units on one fact, and it would admit a
    partial molecule - a different contract (`incomplete`) that is not this line.

    Both names are the gate's own. The sentence carries the molecule's key and the
    address carries the empty cell, so the operator reads WHICH EVENT and WHICH ROW from
    one refusal.
    """
    # 🔴 IMPORTED, NOT RESPELLED. The refusal vocabulary is closed and lives in the
    # gatekeeper; a second copy of either string here would drift the day one is renamed
    # and `refuse()` would reject it at the door with no test having said so.
    from .gate import REFUSE_MISSING_OCCURRED_AT, REFUSE_NO_IDENTITY, REFUSE_NO_RAW_REF

    plan = context.source_plan
    driver = plan.driver
    key = _molecule_key(driver, cells, positions)
    # the one "empty" `runtime_v2.placeable_rows` also asks - a row it will not name as
    # the cursor is a row refused here, or the two disagree about the same cell
    _empty = is_blank_source_value

    # 🔴 THE CURSOR FIRST (총괄 4b5964ab2): a row names itself by its cursor columns, so an
    # empty one leaves its molecule no reference to be said from - `no_raw_ref`, the
    # address the declaration cell to fill. A cursor cell that is also the time is this one.
    for position in positions:
        empty = [column for column in driver.cursor_columns
                 if column in cells and _empty(cells[column][position])]
        if empty:
            row = plan.frame_row_id
            named = cells[row][position] if row in cells else f"at event_frame.rows[{position}]"
            return MoleculeRefusal(
                reason=REFUSE_NO_RAW_REF,
                detail=(f"molecule {key}: row {named} leaves its cursor column "
                        f"{', '.join(empty)} empty - the ledger names a row by its cursor "
                        f"(read.order_by); fill {', '.join(empty)}"),
                rows=len(positions),
                addresses=tuple({"code": "source_preparation_incomplete",
                                 "path": f"bundle.sources.{plan.source_id}.read.order_by."
                                         f"{column}"} for column in empty),
            )

    checks = (
        (REFUSE_NO_IDENTITY, tuple(_required_entity_columns(plan)) + tuple(driver.identity)),
        (REFUSE_MISSING_OCCURRED_AT, (driver.occurred_at.column,)),
    )
    for reason, columns in checks:
        for column in columns:
            if column not in cells:
                continue
            for position in positions:
                if not _empty(cells[column][position]):
                    continue
                path = f"event_frame.rows[{position}].{column}"
                return MoleculeRefusal(
                    reason=reason,
                    detail=(f"molecule {key} declares {column!r} and the row at "
                            f"{path} leaves it empty"),
                    rows=len(positions),
                    addresses=({"code": "source_preparation_incomplete",
                                "path": path},),
                )
    return _row_type_refusal(context, cells, positions, key)


def _event_frames(
    context: SourcePreparationContext,
    prepared: pd.DataFrame,
) -> tuple[pd.DataFrame, ...]:
    plan = context.source_plan
    driver = plan.driver
    # 🔴 THE PAGE IS READ ONCE, HERE (S-64-b). Every line below used to reach a cell
    # with `prepared.iloc[position][column]`, which builds a pandas Series for that row -
    # and with a mixed-dtype page that means `find_common_type` and a copy, per read. There
    # were nine such sites and they ran about ten times per molecule; profiled on a
    # 2,000-row page they were roughly a third of the whole translation.
    #
    # ⚠️ `roleframe` ALREADY MADE THIS REPAIR AND WROTE IT DOWN (「READ THE COLUMNS
    # ONCE」), so this calls that same function rather than spelling it a second time.
    # ⚠️ NAMED `cells`, NOT `columns`: `_refuse_molecule` below already binds
    # `columns` to a tuple of COLUMN NAMES in its own loop, and the first version of
    # this change shadowed it - `cells[column]` became a tuple indexed by a string and
    # every page refused. Two things called `columns` in one file is enough.
    cells = read_columns_once(prepared)
    if driver.unit == "row":
        groups = [[position] for position in range(len(prepared))]
    else:
        grouped: dict[str, list[int]] = {}
        for position in range(len(prepared)):
            identity = {}
            for column in driver.group_by:
                value = cells[column][position]
                if is_blank_source_value(value):
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
        refusal = _refuse_molecule(context, cells, positions)
        if refusal is not None:
            # Counted and named, never raised: the rest of this page still lands. The
            # caller decides whether this is recorded (execute) or reported (preview).
            context.refusals.append(refusal)
            continue
        event = prepared.iloc[positions].copy(deep=True).reset_index(drop=True)
        identity: dict[str, Any] = {}
        for column in driver.identity:
            # The empty-value branch that stood here is gone rather than left unreachable:
            # `_refuse_molecule` above answers that fact for the whole molecule, and a
            # second copy of it here could only disagree. Disagreeing on ONE identity
            # value below is a different fact and still refuses the page.
            values = {
                _canonical(cells[column][position],
                           path=f"source_batch.rows[{position}].{column}")
                for position in positions
            }
            if len(values) != 1:
                raise SourcePreparationError(
                    "source_preparation_incomplete", f"event_frame.identity.{column}",
                    "one source event has more than one identity value",
                )
            identity[column] = cells[column][positions[0]]
        # ONE read of the declared time origin. Both the published cell and the instant
        # the event id is minted from come off this list, so they cannot be a pair of
        # reads that disagree.
        occurred_cells = [
            cells[driver.occurred_at.column][position]
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
        # WHICH of the group's reads IS the event's instant.  The two declarations answer
        # differently because they are not the same kind of time.
        #
        # A `column` source names a WORLD time.  Two different world instants inside one
        # event mean the GROUPING is wrong, and no aggregate can repair that -- so this
        # refusal stays exactly as it was, and stays the only behaviour on this path.
        #
        # A `basis` source names when WE FIRST SAW the rows, and nothing promises that one
        # event's rows arrive in one ingestion batch.  `dt_job` was the first grouped
        # `basis` user and 26 of its 396 jobs are written by two batches; demanding one
        # instant there split single jobs into two atoms whose counts were INGESTION BATCH
        # SIZES ("59 dies" and "13 dies" for a 72-row job) -- a boundary with no business
        # meaning.  The group's time is `min` (owner ruling 2026-08-19): the earliest
        # sighting is the only aggregate that does not MOVE when a later piece of the same
        # event arrives, and the event id is minted from this instant, so a moving one
        # would re-mint the same event under a new id and duplicate the atom on the next
        # backfill.  `min` returns the FIRST position holding that instant, so a re-run
        # over the same group publishes the same cell.
        if driver.occurred_at.basis is None:
            instants = {value.timestamp() for value in occurred_values}
            if len(instants) != 1:
                raise SourcePreparationError(
                    "source_preparation_incomplete", "event_frame.occurred_at",
                    "one source event must have exactly one occurred_at instant",
                )
            earliest = 0
        else:
            earliest = min(
                range(len(occurred_values)),
                key=lambda index: occurred_values[index].timestamp(),
            )
        row_refs = []
        for position in positions:
            order = {column: cells[column][position]
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
        # The published cell is the INTERPRETED instant, the same one the event id is
        # minted from below.  🔴 THE DECLARED TIMEZONE READS A NAIVE COLUMN (owner ruling
        # 2026-08-21): a value that writes its own offset keeps it, and `occurred_at
        # .timezone` answers only for a value that carries none.
        #
        # Until that ruling this line published the value AS READ, and the two halves
        # disagreed: the id below was ALREADY minted from `occurred_values[earliest]`, so
        # the declared timezone was trusted to say WHICH instant an event happened at while
        # the published cell kept the raw text and was refused outright by the Role
        # validator ("time Role must be a timezone-aware datetime").  One assumption, good
        # enough for identity and not for the value, is not a safeguard -- it is a source
        # that cannot produce an atom at all, which is what `lot_event` did.
        #
        # The price is named on purpose: EVERY source whose time column carries no zone is
        # now read through the timezone someone declared for it.  That is what the
        # declaration is FOR -- if it were never allowed to decide this, the square would
        # have had zero freedom and belonged out of the file entirely.
        #
        # object dtype so the exact value survives instead of being re-derived through a
        # pandas datetime64 conversion.
        event[SOURCE_OCCURRED_AT_COLUMN] = pd.Series(
            [occurred_values[earliest]] * len(event), index=event.index, dtype=object)
        molecule_ref = _canonical(
            {"source": plan.source_id, "identity": identity},
            path="event_frame.molecule_ref",
        )
        source_raw_ref = _canonical(
            {"relation": plan.relation, "rows": sorted(row_refs),
             "verified_joins": STORED_RAW_REF_JOINS},
            path="event_frame.source_raw_ref",
        )
        event_id, _state = source_event_identity(
            plan.source_id, occurred_values[earliest], molecule_ref=molecule_ref,
            source_raw_ref=source_raw_ref,
        )
        event.attrs.update({
            "source_id": plan.source_id,
            "source_event_id": event_id,
            "molecule_ref": molecule_ref,
            "source_raw_ref": source_raw_ref,
            "setup_snapshot_hash": context.snapshot.snapshot_sha256,
        })
        missing_attrs = [name for name in EVENT_FRAME_REQUIRED_ATTRS
                         if name not in event.attrs]
        if missing_attrs:
            raise AssertionError(f"internal EventFrame attrs missing: {missing_attrs}")
        events.append(event)
    return tuple(events)
