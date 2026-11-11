from sqlalchemy import Float
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.attributes import flag_modified
from typing import Any, NamedTuple, Optional
from . import models, schemas
from contextlib import contextmanager

@contextmanager
def transaction_context(user: str, tx_id: str, source: str):
    from database.context import request_user, request_transaction_id, request_source
    token_user = request_user.set(user)
    token_tx = request_transaction_id.set(tx_id)
    token_src = request_source.set(source)
    try:
        yield
    finally:
        request_user.reset(token_user)
        request_transaction_id.reset(token_tx)
        request_source.reset(token_src)
import hashlib
import io
import uuid
import uuid6
import codecs
import json
import decimal
import math
import numbers
import os
import logging
import threading
from datetime import datetime, date, timezone, timedelta

# The one render/fold module for world time (S-182). Stdlib-only by design, so importing
# it here cannot pull an application module into the write path.
from utils import time_format
from utils.logger import announce_crossed
import event_constants
from maps import alignment_batch_counts

logger = logging.getLogger("Server")

# [P2-C9] 감사 로그 값 길이 상한 — 공용 상수(server/event_constants.py) 단일 정의를 공유한다.
# crud는 server/ 상위가 sys.path에 없는 컨텍스트에서 import될 수 있으므로(플러그인 shim 등)
# 실패 시 무제한 폴백 대신 **동일 기본값을 내장한 로컬 구현**으로 폴백한다(조용한 무상한 금지).
try:
    from event_constants import MAX_AUDIT_VALUE_CHARS, truncate_audit_value
except ImportError:  # pragma: no cover - 방어적 폴백
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from event_constants import MAX_AUDIT_VALUE_CHARS, truncate_audit_value

# 값 절단 경고는 (테이블, 컬럼)별 1회만 — create_audit_log는 셀 단위 핫패스라
# 무조건 로깅하면 대형 파일 1건이 수십만 줄의 WARNING을 쏟아 로그 자체가 병목이 된다.
_audit_truncation_warned = set()


def _warn_audit_truncation_once(table_name: str, col_name: str):
    key = (table_name, col_name)
    if key in _audit_truncation_warned:
        return
    _audit_truncation_warned.add(key)
    logger.warning(
        f"[Audit] Audit value(s) exceeded {MAX_AUDIT_VALUE_CHARS} chars and were truncated "
        f"with an explicit marker (table='{table_name}', column='{col_name}'). "
        f"This warning is emitted once per (table, column) per process."
    )


# [Schema] A column that is absent from table_config.json is dropped from the update
# while the write still reports success, so a config that lags its client loses fields
# silently (map_doe/map_doe_source lost `eventtime` this way). Surface the first drop
# per (table, column); repeating it from a per-cell loop would flood the log and get
# the whole log ignored.
#
# Shape note: the admission registry is a dict of per-table sets rather than one set
# of (table, column) tuples, because it also answers "how many DISTINCT undeclared
# columns has this table seen", which is what the budget below is spent on. Entries
# are never cleared; a column added to the config simply stops reaching the drop
# branch.
_undeclared_column_warned = {}

# 🔴 HOW MANY, not just "at least once". Warning once per (table, column) per process
# meant a chain dropping the same key ten thousand times logged ONE line at startup
# and was mute for the rest of the day — so a deployment that had been FIXED and one
# that was still silently losing a column produced byte-identical logs from then on.
# That is how a production column-name mismatch stayed invisible for a full day.
#
# The counter is therefore incremented on EVERY drop and re-announced at each power
# of ten. Powers of ten rather than every drop because the whole reason the original
# was once-only is that this branch runs per cell: a 100k-row ingest dropping one
# column must not emit 100k lines. Ten lines over four orders of magnitude is a
# volume signal that costs nothing.
_undeclared_column_drops = {}

# Drops on a table that has already spent its distinct-column budget. Counted per
# TABLE, not per column, on purpose: the budget exists because column names come from
# the payload, so a junk header row can mint unbounded distinct names — and a
# `{(table, column): count}` dict that admitted them would be the same unbounded
# growth wearing a different hat. The total is still never lost, it just stops being
# attributable to a specific column. Bounded by the number of tables, which is config.
_undeclared_column_drops_over_budget = {}

# Per-table budget. For a correct caller the registry is bounded by schema size, but
# the keys come from the payload, so junk column names (a malformed header row, a
# parser emitting values as headers) could otherwise grow it without limit. On
# saturation the table stops growing and stops naming columns — which is announced
# once so the silence is never a surprise. Drops keep being COUNTED past this point
# (see `_undeclared_column_drops_over_budget`); saturation costs attribution, not
# visibility.
_MAX_UNDECLARED_WARNED_PER_TABLE = 64


def undeclared_column_drops() -> dict:
    """Snapshot of undeclared-column drops so far in THIS process: {(table, col): count}.

    Public because the log is not a readable channel for this: the drops happen in the
    chain worker, a different process from the web server, and "is this deployment
    still losing a column?" has to be answerable without grepping a worker's stdout.
    `chain_ingestion_worker` publishes a digest of this through the heartbeat, which
    `/health` already reads.

    A key of `(table, None)` counts drops on a table that had already spent its
    distinct-column budget, so the totals here always add up to every drop that
    happened even when the column name could no longer be attributed.

    Returns a copy; the caller cannot mutate the registry.
    """
    snap = dict(_undeclared_column_drops)
    for table_name, count in _undeclared_column_drops_over_budget.items():
        snap[(table_name, None)] = count
    return snap


def _warn_undeclared_column_once(table_name: str, col_name: str):
    """Count this drop, and announce it on the 1st, 10th, 100th, 1000th ... occurrence.

    ⚠️ THE NAME IS HISTORICAL AND NOW UNDERSTATES WHAT THIS DOES. It no longer warns
    once — warning once is what let a fixed deployment and a broken one produce
    identical logs. It is kept only because the sole call site was pinned by the
    change request; renaming it to `_record_undeclared_column_drop` is a four-line
    follow-up (here, `apply_row_update_internal`, and a comment in
    `parsers/directory_watcher.py` and `tests/test_ingestion_drop_visibility.py`).
    """
    warned = _undeclared_column_warned.get(table_name)
    if warned is None:
        warned = _undeclared_column_warned[table_name] = set()
    elif col_name not in warned and len(warned) >= _MAX_UNDECLARED_WARNED_PER_TABLE:
        # Past the budget: still counted, just no longer attributable to a column.
        _undeclared_column_drops_over_budget[table_name] = (
            _undeclared_column_drops_over_budget.get(table_name, 0) + 1)
        return

    key = (table_name, col_name)
    count = _undeclared_column_drops.get(key, 0) + 1
    _undeclared_column_drops[key] = count
    if not announce_crossed(count - 1, count):
        return
    warned.add(col_name)
    logger.warning(
        f"[Schema] Column '{col_name}' is not declared in column_types for table "
        f"'{table_name}' and was DROPPED from the update; the write still succeeded "
        f"for the declared columns. Add it to config/table_config.json to persist it. "
        f"Dropped {count} time(s) in this process so far; this warning repeats at each "
        f"power of ten, so silence after this line means the drops STOPPED."
    )
    if count == 1 and len(warned) >= _MAX_UNDECLARED_WARNED_PER_TABLE:
        logger.warning(
            f"[Schema] Reached {_MAX_UNDECLARED_WARNED_PER_TABLE} distinct undeclared "
            f"columns for table '{table_name}'; further undeclared columns on this table "
            f"will be dropped without naming the column (the drop count is still "
            f"available from crud.undeclared_column_drops())."
        )


# ---------------------------------------------------------------------------
# [Drop report] The CALLER learns what its own write discarded.
# ---------------------------------------------------------------------------
# `undeclared_column_drops()` above answers "is this PROCESS still losing a column?" for
# an operator reading /health. It cannot answer "did MY batch land?", because it is a
# process-lifetime counter with no batch, no row and no transaction in it. So a caller
# that issued a 1,000-key write still had exactly two possible outcomes - an exception,
# or silence that means success - and a partial discard had to pick one of them. It
# picked silence, and that is the whole of the 2026-08-11 incident: a misspelled key
# column was dropped, 200 SUCCESS came back, and the row landed with no identity.
#
# `apply_batch_updates(..., drop_report={})` is the third answer. It is an OUT-PARAMETER
# for exactly the reason `replace_report` is one (see that docstring): the 4-tuple return
# is unpacked at ~10 production call sites and dozens of tests, and a caller that does not
# want the detail must not have to change a line. Both are filled in place by the attempt
# that COMMITS.
#
# Reason names, not a generic count: "the config does not declare this column" and "this
# is a system column no payload may write" need different fixes by different people.

#: A column the payload named that `column_types` does not declare. Today's incident.
DROP_UNDECLARED_COLUMN = "undeclared_column"
#: A row that would break a uniqueness some VIRTUAL JOIN declared on this table.
DROP_UNIQUE_VIOLATED = "unique_violated"
#: A column the write path owns (`row_id`, `updated_at`, graph-sync flags ...). A payload
#: may name it; it is never taken from one.
DROP_SYSTEM_COLUMN = "system_column"
#: [S-243, 판정 405] A blank cell from a writer that cannot mean 「I emptied this」. It is
#: 「not entered yet」, so it makes no layer - and that is not a failure, which is why it is
#: COUNTED rather than warned about. Without a name in this report, a file whose column
#: went blank would look exactly like a file that never named the column at all.
DROP_ABSENT_NOT_WRITTEN = "absent_not_written"
#: [총괄 791c0f45e 3] Declared, but THIS PROCESS'S model does not hold the column - a reload
#: that failed half-way, the moment between a config swap and the model, or a declared name
#: the model build skips. It was written to the layer and silently not to the table
#: (0a7c46615 ㉠); now it is neither, and counted.
DROP_UNMAPPED_COLUMN = "unmapped_column"
#: A value its column's type does not take (`CellRefused`). It used to refuse the whole batch - one 'N/A' in a number
#: column stopped a file, a grid paste and a chain group (owner 10-29 «데이터 값은 멈추지 않는다» ㄱ): now that cell
#: is not entered, the rest of its row is written, and the cell is counted here with its value.
DROP_VALUE_REFUSED = "value_refused"
#: One answer gave one cell two values - the items one owner (`layer_owner`: a rule and its key) proposed (owner 11-08:
#: «한 답 안의 한 칸 두 값 = 오류»). Neither is written. Different owners on one cell are not this: the later shows.
DROP_TWO_VALUES = "two_values_in_one_answer"

# Both caps exist for the same reason the undeclared-column registry has a budget: every
# name and every row id in this report comes from the PAYLOAD, so a malformed file must
# not be able to grow it without limit. Counts are never capped - only the named detail
# is - and the report always says how much it withheld.
MAX_DROP_REPORT_ROWS = 20
MAX_DROP_REPORT_COLUMNS = 64


def _new_drop_stats() -> dict:
    """Per-batch accumulator for discarded update keys.

    Allocated unconditionally by `_apply_batch_updates_once` (one dict per batch) because
    it feeds TWO consumers with different lifetimes: the optional `drop_report` the caller
    asked for, and the phantom-row guard, which must work whether or not anyone asked for
    a report. Nothing touches it on a batch that discards nothing.
    """
    return {
        "cells": 0,
        "by_reason": {},
        "by_column": {},
        "columns_omitted": 0,
        # row ids that lost at least one key. Bounded by the batch size (the same order
        # as `unique_results`, which this function already holds), NOT by the table.
        "rows_with_drops": set(),
        # capped detail sample: [{row_id, business_key_val, columns: {col: reason}}]
        "sample": [],
        "sample_index": {},
        # Whole rows refused by name before a cell was read - today the virtual-join
        # uniqueness refusal (S-174). Declared here so a reader never tests for the key.
        "row_refusals": [],
        # {column: {"cells": n, "first": the first value refused there}} - capped like by_column.
        "refused_values": {},
        # {reason: {column: non-blank values}} - the columns by_column counts, by why, counted as a file's load
        # counts them (a blank lost nothing; a column of blanks only is still named, at 0) - not_written_sentence's
        "by_reason_column": {},
    }


def _refuse_two_values_in_one_answer(table_name, items, drop_stats):
    """The cells one owner's items give two different values in this batch, taken off every such item and counted
    (`DROP_TWO_VALUES`). Only an owned layer has an owner - a file's or a person's items are never asked."""
    types = (TABLE_CONFIG.get(table_name) or {}).get("column_types") or {}
    seen = {}
    for item in items:
        if layer_owner(item.source_name) is None:
            continue
        row = item.row_id or item.business_key_val
        for column, value in (item.updates or {}).items():
            seen.setdefault((row, item.source_name, column), []).append((item, value))
    for (row, _name, column), said in seen.items():
        first = said[0][1]
        if not any(values_differ(first, value, types.get(column, "string")) for _item, value in said[1:]):
            continue
        for item, value in said:
            item.updates.pop(column, None)
            _record_dropped_cell(drop_stats, item.row_id, item.business_key_val, column, DROP_TWO_VALUES, value)


def _record_dropped_cell(drop_stats: dict, row_id: str, business_key_val: Any,
                         col_name: str, reason: str, value: Any):
    """One discarded (row, column) pair. Called only from a branch that already decided
    to discard, so the healthy write path never reaches it."""
    drop_stats["cells"] += 1
    by_reason = drop_stats["by_reason"]
    by_reason[reason] = by_reason.get(reason, 0) + 1

    by_column = drop_stats["by_column"]
    if col_name in by_column:
        by_column[col_name] += 1
    elif len(by_column) < MAX_DROP_REPORT_COLUMNS:
        by_column[col_name] = 1
    else:
        drop_stats["columns_omitted"] += 1
    if col_name in by_column:
        named = drop_stats["by_reason_column"].setdefault(reason, {})
        named[col_name] = named.get(col_name, 0) + (0 if is_blank_value(value) else 1)

    drop_stats["rows_with_drops"].add(row_id)

    entry = drop_stats["sample_index"].get(row_id)
    if entry is None:
        if len(drop_stats["sample"]) >= MAX_DROP_REPORT_ROWS:
            return
        entry = {
            "row_id": row_id,
            # The caller's OWN handle on this record, not the stored one. At the moment a
            # key column is dropped the row has no stored identity yet - that is the
            # defect - so the stored value would be `None` for exactly the rows an
            # operator most needs to find.
            "business_key_val": business_key_val,
            "columns": {},
        }
        drop_stats["sample"].append(entry)
        drop_stats["sample_index"][row_id] = entry
    if len(entry["columns"]) < MAX_DROP_REPORT_COLUMNS:
        entry["columns"][col_name] = reason


def _refused_row_counts(drop_stats: dict, version_stats: Optional[dict]) -> dict:
    """`{reason: rows}` for every WHOLE row refused before a cell was read.

    🔴 ONE MAP, TWO SOURCES, BECAUSE AN OPERATOR ASKS ONE QUESTION. The version gate and
    the virtual-join uniqueness refusal (S-174) both answer 「this row was not written, and
    here is the word for why」; publishing them under two keys would make the screen ask
    which list it is looking at, and a third refusal would add a third key.

    `VERSION_NOTES_APPLIED` are excluded outright because they name rows the gate APPLIED, and a refusal count that
    includes accepted rows is worse than no count.
    """
    counts = {k: v for k, v in (version_stats or {}).get("counts", {}).items()
              if v and k not in VERSION_NOTES_APPLIED}
    for refusal in drop_stats.get("row_refusals") or ():
        reason = refusal.get("reason") or DROP_UNIQUE_VIOLATED
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _render_drop_report(drop_report: dict, table_name: str, drop_stats: dict,
                        version_stats: Optional[dict], suppressed_row_ids: list,
                        reported_only_for_drops: int = 0):
    """Fill the caller's dict in place. Shape is stable whether or not anything dropped:
    a caller must be able to read `dropped_cells` without first testing for the key.

    🔴 `reported_only_for_drops` IS THE NUMBER THE RESPONSE SUBTRACTS (판정 207). A row whose
    every update key was dropped changed nothing, so it is not part of 「N rows updated」 -
    but the caller still has to be TOLD about it, or the grid never learns the write was
    processed at all. So it rides in the answer and not in the count, and this is how the
    layer that builds the count knows how many of those there were.
    """
    rows_affected = len(drop_stats["rows_with_drops"])
    drop_report.update({
        "table": table_name,
        # ⚠️ ROWS, NOT CELLS, and a SUBSET of `rows_affected`: a row that lost one key and
        # kept another changed, so it is counted like any other change and is not here.
        "reported_only_for_drops": reported_only_for_drops,
        # Total discarded (row, column) pairs. Never capped.
        "dropped_cells": drop_stats["cells"],
        "by_reason": dict(drop_stats["by_reason"]),
        "by_column": dict(drop_stats["by_column"]),
        "columns_omitted": drop_stats["columns_omitted"],
        "rows_affected": rows_affected,
        "rows": list(drop_stats["sample"]),
        # 정본 — 「표본 목록이 «잘렸다»」. 바로 위 `columns_omitted` 는 «버림»이라 여기 «안»
        # 들어온다: 잘림은 「상한을 올려라」이고 버림은 「선언을 고쳐라」다.
        "truncated": {"rows": event_constants.truncated_note(
            rows_affected > len(drop_stats["sample"]),
            max(0, rows_affected - len(drop_stats["sample"])),
            "affected rows beyond the detail sample cap")},
        # Whole ROWS refused before a single cell was read, by name - the version gate and
        # the virtual-join uniqueness refusal. `_refused_row_counts` owns the arithmetic
        # and the warning about summing them.
        "rows_refused": _refused_row_counts(drop_stats, version_stats),
        # ⚠️ NAMED, AND CAPPED LIKE EVERY OTHER DETAIL LIST. The counts above say HOW MANY;
        # an operator fixing the data needs WHICH, and each entry carries the other row
        # that claims the same key - which is the whole of what makes it fixable.
        "refusals": list(drop_stats["row_refusals"])[:MAX_DROP_REPORT_ROWS],
        "refused_values": dict(drop_stats["refused_values"]),
        "by_reason_column": {reason: dict(columns) for reason, columns in drop_stats["by_reason_column"].items()},
        # Rows that were NOT inserted because every key the payload carried for them was
        # discarded - see the guard in `_apply_batch_updates_once`.
        "empty_rows_suppressed": len(suppressed_row_ids),
        "empty_rows": [
            {"row_id": r_id,
             "business_key_val": (drop_stats["sample_index"].get(r_id) or {}).get(
                 "business_key_val")}
            for r_id in suppressed_row_ids[:MAX_DROP_REPORT_ROWS]
        ],
    })


# ---------------------------------------------------------------------------
# [Version gate] Version is the authority, arrival order is not.
# ---------------------------------------------------------------------------
# A table whose single business key must always hold the LATEST row declares
# `version_column` in table_config.json. A machine write against an EXISTING row of such
# a table is applied unless the incoming version is LOWER than the one the row already
# holds. Without it this path is last-write-wins, so re-dropping a superseded file makes
# current state regress with no record of any kind. The SAME version is taken (owner 10-26
# «버전이 같아도 들어온 새 걸로 업데이트되게»): a row whose cells are the same writes nothing
# by itself, and a map judged at the same version is written only when it would change
# something (`_map_unchanged`) - a map file read again does not purge and rewrite its map.
#
# 🔴 The gate is a VETO, never a promotion. A row that passes still goes cell by cell
# through `compute_priority_value`, where `user` (0) outranks every machine source. That
# is the whole of "version orders only WITHIN a priority tier, never across one": a newer
# version can decide whether the parser's row is considered at all, and it can never
# decide a cell a person has corrected. Writing the payload onto the row once the version
# passes - the plausible reading of "version is the authority" - would silently undo human
# corrections on the next ingestion, and `test_human_correction_survives_a_newer_version`
# exists to turn red the moment anyone does.
#
# The declaration is per TABLE, not per REQUEST. A table either has a version column or it
# does not, and this function is the funnel six direct callers plus HTTP converge on: a
# request-level flag is one every caller has to remember, and the caller who forgets falls
# back to exactly the last-write-wins regression this closes. A table that declares
# nothing is byte-identical to before.

# The names refusals are reported under. Same vocabulary and same shape as
# `enrichment_candidates.REASON_*` - a refusal is counted under a name, never folded into
# a generic failure.
REASON_VERSION_MISSING = "version_missing"
REASON_VERSION_UNORDERABLE = "version_unorderable"
REASON_VERSION_OLDER = "version_older"
# Not a refusal: the row is applied. Named anyway because it happens exactly once per row
# and only while a table is adopting the gate.
NOTE_ROW_VERSION_ABSENT = "row_version_absent"
# A map at the stored map's version (lead 10-26 ㄱ): the same content is left as it is - nothing to write, not a
# refusal - and a different one is applied.
NOTE_MAP_UNCHANGED = "unchanged"
NOTE_MAP_SAME_APPLIED = "applied"
#: the notes that name rows the gate APPLIED - never counted as refused
VERSION_NOTES_APPLIED = (NOTE_ROW_VERSION_ABSENT, NOTE_MAP_SAME_APPLIED)

# table_name -> {reasons already announced at WARNING in this process}. Bounded by the
# constant set of reason names above, so unlike the undeclared-column registry it needs
# no budget. Entries are never cleared; a feed that stops regressing simply stops
# reaching the branch.
_version_gate_announced = {}

# What each outcome MEANS, in the log, in one sentence. Two of these outcomes APPLY the
# row, one leaves an unchanged map and three refuse it; a single generic sentence would describe the applied ones as
# refusals, which is how a diagnostic starts lying.
_VERSION_OUTCOME_EXPLANATION = {
    REASON_VERSION_MISSING:
        "the incoming row carries no usable value in the version column, and an unknown "
        "version is read neither as older nor as newer - the stored row is kept",
    REASON_VERSION_UNORDERABLE:
        "the version value cannot be ordered (not a number, not an ISO-8601 timestamp, "
        "or the two sides are different kinds) - the stored row is kept",
    REASON_VERSION_OLDER:
        "the incoming version is LOWER than the stored one, so this is a superseded file "
        "arriving late - the stored row is kept",
    NOTE_MAP_UNCHANGED:
        "the map is at the stored map's version and its content is the same, so nothing is "
        "written - the map stays as it was (not a refusal)",
    NOTE_MAP_SAME_APPLIED:
        "the map is at the stored map's version and its content differs, so it is applied - "
        "the same version is taken",
    NOTE_ROW_VERSION_ABSENT:
        "the stored row had no usable version, so the incoming one was ADOPTED and the "
        "row WAS written. Expected while a table takes up version gating; it should stop",
}


def _naive_utc(value):
    """One instant, one spelling - the doctrine `temporal_text_value` already pins.

    Aware values are converted to UTC; naive values are taken as already-UTC (that is
    what the SQLite dialect hands back and the only shape a naive column can be here).
    Returning naive UTC on both arms is what makes the two sides comparable at all:
    comparing an aware datetime to a naive one raises TypeError.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None)
    return datetime(value.year, value.month, value.day)


def _parse_temporal_version(text: str):
    try:
        return ("temporal", _naive_utc(datetime.fromisoformat(text)))
    except ValueError:
        return None


def parse_version_key(raw: Any, col_type: str):
    """A version value rendered to `(kind, sortable)`, or None when it cannot be ordered.

    🔴 The comparison is chosen from the VALUE, not only from the declaration, and it is
    never a text comparison. `column_text_sql` / `TEMPORAL_TEXT_FORMAT` are deliberately
    NOT used here: they exist to render a column to text for a SQL predicate, and text is
    precisely what mis-orders a version - `'10' < '9'`. What IS reused is the reasoning
    behind `TEMPORAL_TEXT_FORMAT`: an ISO-8601 timestamp is an ordered value, arbitrary
    text is not.

    Both sides must produce the same `kind`. A feed that emits `7` and then
    `2026-08-04T09:00:00` has not moved forward; it has changed what a version means, and
    coercing the two into one order would invent an answer. Different kinds are refused
    by the caller under `version_unorderable`.

    A `string` column is tried as a number FIRST (numeric revisions live in text columns
    all the time) and then as ISO-8601. Anything else is unorderable - `REV_B > REV_A` is
    a lexical accident, not a version order, and the ruling on this feature is that an
    unknown version is refused by name rather than read as older OR as newer.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None  # a flag is not a version
    if isinstance(raw, (datetime, date)):
        return ("temporal", _naive_utc(raw))
    if isinstance(raw, (int, float)):
        return ("numeric", float(raw)) if math.isfinite(raw) else None

    text = str(raw).strip()
    if text == "":
        return None

    if col_type == "number":
        try:
            parsed = float(text)
        except ValueError:
            return None
        return ("numeric", parsed) if math.isfinite(parsed) else None

    if col_type == "datetime":
        return _parse_temporal_version(text)

    try:
        parsed = float(text)
        if math.isfinite(parsed):
            return ("numeric", parsed)
    except ValueError:
        pass
    return _parse_temporal_version(text)


def _same_source_content_differs(db, table_name, row, update_item, config, version_col,
                                 is_new, sources_cache, overwrites_cache,
                                 cell_sources_to_upsert, cell_overwrites_to_upsert,
                                 layers_read=None):
    """Columns whose incoming value differs from what THIS SAME SOURCE last wrote.

    🔴 Measured against the source's own previous value, not against the displayed cell.
    A human correction makes the displayed value differ from the file permanently, so
    comparing against the cell would call every re-read of an unchanged file «changed».
    Against the source's own history the predicate is exact: same version, different
    content, same writer.

    Reads come from the caches (`_load_metadata_row_cell` is cache-first) - `_map_unchanged` fills them for the whole
    map in one read. It only runs on the equal-version arm of a map's verdict, which is the re-read case.
    """
    # The same loadable answer as the write itself; the dict beside it answers a
    # DIFFERENT question (what type is this column), which is not a filter.
    loadable = loadable_columns(config)
    col_types = (config or {}).get("column_types") or {}
    differing = []
    for col_name, val in update_item.updates.items():
        if col_name == version_col or col_name not in loadable:
            continue
        col_type = col_types.get(col_name, "string")
        try:
            incoming = cast_value_by_type(val, col_type, col_name, table_name)
        except ValueError:
            differing.append(col_name)
            continue
        col_srcs, _ow = _load_metadata_row_cell(
            db, table_name, row.row_id, col_name, is_new, sources_cache, overwrites_cache,
            cell_sources_to_upsert, cell_overwrites_to_upsert, layers_read)
        prev = next((s.value for s in col_srcs if s.source_name == update_item.source_name),
                    None)
        # The source has never written this cell: that is a NEW field appearing at an
        # unchanged version, which is the same upstream defect.
        if values_differ(prev, incoming, col_type):
            differing.append(col_name)
    return differing


def version_gate_verdict(table_name, config, row, is_new, update_item):
    """Per-ROW verdict: `(applied: bool, reason: str | None)`.

    Judged at the row and not at the cell. A per-cell version check would accept some
    columns of a stale row and refuse others, leaving the row half-updated and internally
    inconsistent - which is worse than either taking it or refusing it whole. If the row
    is applied, the ordinary per-cell layering then decides every cell.
    """
    version_col = config.get("version_column")
    if not version_col:
        return True, None  # not a version-gated table - the untouched default

    # A person's correction is not version-ordered. A grid edit carries one cell and no
    # version column at all; gating it would make the table read-only for people, and
    # `user` already outranks every machine source cell by cell.
    if update_item.source_name == "user":
        return True, None

    # Creating a row is not an overwrite: there is nothing to regress.
    if is_new:
        return True, None

    col_type = config.get("column_types", {}).get(version_col, "string")

    if version_col not in update_item.updates:
        return False, REASON_VERSION_MISSING
    incoming_raw = update_item.updates.get(version_col)
    if is_blank_value(incoming_raw):
        return False, REASON_VERSION_MISSING
    incoming = parse_version_key(incoming_raw, col_type)
    if incoming is None:
        return False, REASON_VERSION_UNORDERABLE

    return _version_order(incoming, parse_version_key(getattr(row, version_col, None), col_type))


def _version_order(incoming, stored, unchanged=None):
    """`(applied, reason)` for two `parse_version_key` keys - a row's, or a map's (its rows' greatest). The same version
    is taken (owner 10-26); a map's `unchanged()` says first whether it would write anything."""
    if stored is None:
        # Adoption. A row written before the column existed has nothing to regress to,
        # and refusing it would wedge the table behind a manual backfill forever. Named
        # so the one-time adoption is visible rather than assumed.
        return True, NOTE_ROW_VERSION_ABSENT

    if incoming[0] != stored[0]:
        return False, REASON_VERSION_UNORDERABLE
    if incoming[1] > stored[1]:
        return True, None
    if incoming[1] == stored[1]:
        if unchanged is None:
            return True, None
        return (False, NOTE_MAP_UNCHANGED) if unchanged() else (True, NOTE_MAP_SAME_APPLIED)
    return False, REASON_VERSION_OLDER


def map_version_verdict(config, items, stored_values, unchanged=None):
    """Per-MAP verdict for a map replace (소유자 10-21 「맵교체랑 섞이면 맵단위로 버전관리」): `(applied, reason)`.
    A map's version is the greatest of its rows' - the incoming items', the stored rows' (`stored_values`). Not
    asked: a table with no version column · a batch with no item (a scope emptied) · a person's batch. At the same
    version, `unchanged()` (`_map_unchanged`) decides: the same content is left, a different one applied."""
    version_col = config.get("version_column")
    if not version_col or not items or all(item.source_name == "user" for item in items):
        return True, None
    col_type = config.get("column_types", {}).get(version_col, "string")
    incoming = [parse_version_key(item.updates.get(version_col), col_type) for item in items
                if not is_blank_value(item.updates.get(version_col))]
    if not incoming:
        return False, REASON_VERSION_MISSING
    if None in incoming or len({key[0] for key in incoming}) > 1:
        return False, REASON_VERSION_UNORDERABLE
    stored = [key for key in (parse_version_key(value, col_type) for value in stored_values) if key is not None]
    if not stored:
        return True, NOTE_ROW_VERSION_ABSENT if stored_values else None
    if len({key[0] for key in stored}) > 1:
        return False, REASON_VERSION_UNORDERABLE
    return _version_order(max(incoming), max(stored), unchanged)


def _map_unchanged(db, table_name, config, items, row_ids) -> bool:
    """True when a map at the stored map's version would write nothing (lead 10-26 ㄱ): the stored rows `row_ids` are
    the items' rows one for one by key, and no item's column differs from what its source last wrote there
    (`_same_source_content_differs`). The map's layers are read once, its rows' and its sources'."""
    table_model = models.DYNAMIC_TABLES[table_name]
    rows = db.query(table_model).filter(table_model.row_id.in_(list(row_ids))).all() if row_ids else []
    if len(rows) != len(items):
        return False
    by_key = {clean_str_value(row.business_key_val): row for row in rows}
    key_col = config.get("business_key")
    sources_cache = {}
    for layer in db.query(models.CellSource).filter(
            models.CellSource.table_name == table_name, models.CellSource.row_id.in_([row.row_id for row in rows]),
            models.CellSource.source_name.in_(sorted({item.source_name for item in items}))):
        sources_cache.setdefault((layer.row_id, layer.column_name), []).append(layer)
    read = LayersRead([row.row_id for row in rows], {col for item in items for col in item.updates})
    seen = set()
    for item in items:
        assemble_composite_business_key(table_name, item)
        key = clean_str_value(item.business_key_val or (item.updates.get(key_col) if key_col else None))
        row = by_key.get(key) if key else None
        if row is None or row.row_id in seen:
            return False
        seen.add(row.row_id)
        if _same_source_content_differs(db, table_name, row, item, config, config.get("version_column"), False,
                                        sources_cache, {}, None, None, read):
            return False
    return True


def log_version_gate_summary(table_name, version_col, source_name, stats):
    """Individual silence, named aggregate - the shape the ingestion drop report uses.

    Nothing per row: at 10M rows a per-row line buries every real event. A WARNING on
    FIRST sighting per (table, reason) per process, because that is the moment something
    genuinely changed; a later warning is therefore by definition news. Then one INFO per
    batch carrying the counts, so "nothing was refused" and "200 rows were refused" can
    never look the same to anyone who goes looking.

    ASCII only - this reaches a cp949 console.
    """
    if not stats:
        return
    counts = {k: v for k, v in stats.get("counts", {}).items() if v}
    if not counts:
        return

    announced = _version_gate_announced.setdefault(table_name, set())
    for reason in sorted(counts):
        if reason in announced:
            continue
        announced.add(reason)
        logger.warning(
            f"[VersionGate] '{table_name}' is version-gated on column '{version_col}': "
            f"outcome '{reason}' seen for the first time in this process (source "
            f"'{source_name}'), {counts[reason]} row(s) in this batch - "
            f"{_VERSION_OUTCOME_EXPLANATION.get(reason, 'no explanation registered')}."
            f" Repeats are reported at INFO, once per batch."
        )

    named = ", ".join(f"{reason}={counts[reason]}" for reason in sorted(counts))
    logger.info(
        f"[VersionGate] '{table_name}' version column '{version_col}', source "
        f"'{source_name}': {named} out of {stats.get('rows', 0)} row(s) in this batch."
    )


class LightCellSource:
    # 🔴 [S-280] `origin_row_id` IS A SLOT AND IS SELECTED BY EVERY PREFETCH, not an
    # afterthought defaulted to None. This object is what `apply_row_update_internal`
    # compares the incoming item against, so an origin the cache does not carry reads as
    # 「the origin changed」 on EVERY write - which would bump `ingested_at`, and that
    # timestamp is the layering tiebreak.
    __slots__ = ('table_name', 'row_id', 'column_name', 'source_name', 'value', 'updated_by', 'ingested_at', 'origin_row_id')
    def __init__(self, table_name, row_id, column_name, source_name, value, updated_by, ingested_at, origin_row_id=None):
        self.table_name = table_name
        self.row_id = row_id
        self.column_name = column_name
        self.source_name = source_name
        self.value = value
        self.updated_by = updated_by
        self.ingested_at = ingested_at
        self.origin_row_id = origin_row_id

class LightCellOverwrite:
    __slots__ = ('table_name', 'row_id', 'column_name', 'is_overwrite', 'updated_by', 'updated_at', 'manual_priority_source')
    def __init__(self, table_name, row_id, column_name, is_overwrite, updated_by, updated_at, manual_priority_source):
        self.table_name = table_name
        self.row_id = row_id
        self.column_name = column_name
        self.is_overwrite = is_overwrite
        self.updated_by = updated_by
        self.updated_at = updated_at
        self.manual_priority_source = manual_priority_source

# 소스별 우선순위 정의 (숫자가 낮을수록 높음)
#: The derived-table worker's layer. Named here because S-243 has to ASK who wrote a
#: blank, and a second literal in the asking would be a second answer to 「is this the
#: chain」 - the repository already spells this string in six other modules.
CHAIN_SOURCE = "chain_ingestion"
#: A language model's draft (e38466810: the meaning table). Below every other writer - a person's value wins - and not
#: a writer that can mean 「I emptied this cell」 (`can_mean_emptied`).
LLM_DRAFT_SOURCE = "llm_draft"

SOURCE_PRIORITY = {
    "user": 0,
    "collision_merge": 1,
    "pipeline_parser": 2,
    "custom_script": 3,
    # [QA G1-⑥] 체인 파생 쓰기 소스 서열 명시(구: 미등재 기본 99). 기존 4대 소스와의
    # 상대 서열은 불변(4 > 3)이라 표시값 레이어링 결과는 유지되며, 미등재 소스 대비로만 승격된다.
    CHAIN_SOURCE: 4,
    LLM_DRAFT_SOURCE: 5,
}

# The priority-0 layer above is the only source that means "a human typed this".
# Every other writer is machine-driven: `collision_merge` is the merge engine,
# `chain_ingestion` is the derived-table worker, and file parsers write under the
# *ingested filename* as their source name (so the set of automatic source values is
# open-ended - 10,750 distinct values on the live DB as of 2026-07-27). That is why
# human writes must be selected POSITIVELY by this constant and never by blacklisting
# automatic ones.
USER_SOURCE = "user"

#: Who wrote a cell, in the words a colour rule's written_by picks (owner 11-06, lead 11-07), by a layer's base name
#: (`layer_writer`). None = no word, said here so it is not mistaken for one left out: a merge's value is other writers'
#: and the legend would say whose it cannot back (lead 11-07 ②). A name not here is a file's (`is_file_layer`).
WRITER_KINDS = {USER_SOURCE: "person", CHAIN_SOURCE: "chain", "custom_script": "chain", LLM_DRAFT_SOURCE: "ai",
                "pipeline_parser": "file", "collision_merge": "merge"}


def can_mean_emptied(source_name: str, replaces_map: bool = False) -> bool:
    """Can this writer MEAN 「I emptied this cell」? (S-243, 판정 405)

    🔴 TWO WRITERS CAN, AND THE SET IS CLOSED BY CONSTRUCTION. A person clearing a cell
    (rank 0) and the chain asserting that a matched right row IS empty (판정 f3c04dee).
    Everything else that arrives blank means 「아직 입력하지 않은 것」 and makes no layer -
    except a write that REPLACES A MAP WHOLE (`replaces_map`: a `replace_map` batch, a file of a table declaring
    `allow_replace_map`): its rows are its statement of the map, so a cell it names blank is emptied, as the chain's
    replace already did (총괄 10-21, 소유자 「기존 값 그대로 있음」). A cell the file does not name is not in its rows.

    🔴 POSITIVELY, NEVER BY BLACKLIST - the reason is twenty lines above this one: file
    parsers write under the INGESTED FILENAME, so the set of automatic source names is
    open-ended (10,750 distinct values on the live database) and cannot be enumerated.

    ⚠️ IT IS A FUNCTION RATHER THAN A CONDITION AT ITS ONE SEAT because it has a SECOND
    reader now: `scripts/count_absent_null_layers.py` asks the same question of layers
    already stored (S-243-b). Two spellings of 「who may empty a cell」 is how the counting
    and the writing come to disagree about what they are counting.
    """
    return replaces_map or layer_ranks_as(source_name) in (USER_SOURCE, CHAIN_SOURCE)


def merged_layer_name(name: str, tag: str) -> str:
    """The name collision merge gives a layer it keeps from a merged row: the writer's name, the
    merged row in brackets. ONE spelling - `layer_writer` reads it back. The chain's layer per source
    row is spelled the same way (`chain_ingestion (<row>)`, 총괄 8ec008914)."""
    return "%s (%s)" % (name, tag)


#: What an owner's part may not hold as itself in a layer name: the escape, the parts' separator, the brackets, and
#: control characters - each written %XX, so a part never holds a space or a bracket and `layer_writer` still reads
#: the writer before the first « (».
_OWNER_UNSAFE = frozenset("% ()") | frozenset(chr(code) for code in range(32)) | {chr(127)}


def _owner_part(text) -> str:
    return "".join("%%%02X" % ord(ch) if ch in _OWNER_UNSAFE else ch for ch in str(text))


def _ownable_bases() -> tuple:
    """The layer names a rule's owned layer is built on: the chain's, and auto-confirm's two (their rank is theirs)."""
    from chain.enrichment import candidates

    return CHAIN_SOURCE, candidates.SOURCE_NAME, candidates.SOURCE_NAME_PARTIAL_KEY


def owned_layer_name(rule, key, base=CHAIN_SOURCE) -> str:
    """THE name of the layer (rule, key) owns (owner 11-06 step 2 ㄱ): `<base> (<rule> <key>)` - `base` the chain's
    layer or auto-confirm's - each part escaped (`_OWNER_UNSAFE`). Built here only; read back by `layer_owner` only.
    The cells `owner_rule` / `owner_key` say the same and are what aiming, picking and tests read - the name keeps
    the one unique index."""
    return merged_layer_name(base, "%s %s" % (_owner_part(rule), _owner_part(key)))


def layer_owner(source_name):
    """(rule, key) of a layer `owned_layer_name` built - None for any other name (a source row's bracket, a
    collision-merge copy, a person's or a file's). Its base is `layer_writer`'s."""
    from urllib.parse import unquote

    name = str(source_name or "")
    base = layer_writer(name)
    if base not in _ownable_bases() or not name.startswith(base + " (") or not name.endswith(")"):
        return None
    parts = name[len(base) + 2:-1].split(" ")
    if len(parts) != 2:
        return None
    return unquote(parts[0]), unquote(parts[1])


def layer_writer(source_name) -> str:
    """Whose layer this is. A collision-merge copy (`merged_layer_name`) is its writer's."""
    return str(source_name or "").split(" (", 1)[0]


def human_source_clause():
    """The SQL of «`layer_writer`(source_name) is USER_SOURCE» - a person's line, a collision-merge copy of one
    included (lead 11-10 ㄴ). The text IS the t__lines partial index's predicate (`lines.HUMAN_SOURCE_SQL`, C): the
    planner uses the index only on the same words, so it is read from there, never spelled again."""
    from sqlalchemy import text

    from database import lines

    return text(lines.HUMAN_SOURCE_SQL)


def layer_ranks_as(source_name):
    """The name a layer is ranked and judged as (rank · 「can it mean emptied」 · 「is it the chain」): a
    chain layer per source row as the chain's, any other name as itself (총괄 8ec008914 · 판정 10-11 - a
    collision-merge copy of another writer keeps today's rank) - and an owned layer as its base. The one seat that
    asks it."""
    writer = layer_writer(source_name)
    return writer if writer == CHAIN_SOURCE or layer_owner(source_name) else source_name


_MACHINE_LAYER_NAMES = []


def machine_layer_names() -> frozenset:
    """Every layer name the product itself writes - ASSEMBLED from the constants that define
    them, never retyped (총괄 a7d2e90ec). Read lazily: two of them live in modules that
    import this one."""
    if not _MACHINE_LAYER_NAMES:
        from chain.enrichment import backfill, candidates
        _MACHINE_LAYER_NAMES.append(frozenset(SOURCE_PRIORITY) | {
            USER_SOURCE, CHAIN_SOURCE, candidates.SOURCE_NAME,
            candidates.SOURCE_NAME_PARTIAL_KEY, backfill.SOURCE_NAME})
    return _MACHINE_LAYER_NAMES[0]


def writer_kind(source_name):
    """person · chain · ai · file - who wrote the layer `source_name`, or None (no layer, or `WRITER_KINDS` says none).
    The enrichment chain's layers are the chain's; any other name outside the product's own is a file's."""
    if not source_name:
        return None
    name = layer_writer(source_name)
    if name in WRITER_KINDS:
        return WRITER_KINDS[name]
    if name in machine_layer_names():
        return "chain"
    return "file"


def is_file_layer(source_name) -> bool:
    """A layer a file wrote - any name outside `machine_layer_names`, because a file parser
    writes under the ingested file name, an open set.

    ⚠️ A hand-written mapper that writes under its own name reads as a file layer too. The
    fold only removes a layer that a NEWER layer of the same class repeats, so the winning
    value never moves; what goes is the record of which older writer said it first."""
    return layer_writer(source_name) not in machine_layer_names()


#: An external file's layer name - «external:<parser>@<table>@<root><LAYER_SHARE_END><path>» (owner 11-04 «ㄷ»):
#: the share it was read from (`<table>@<root>`, its source's id) is in the name, so two shares saying one value
#: keep a layer each. Built by `external_layer_name`, read by `layer_share` - the one place the shape is spelled.
EXTERNAL_LAYER = "external:"
LAYER_SHARE_END = "|"


def external_layer_name(parser: str, source_id: str, path: str) -> str:
    return "%s%s@%s%s%s" % (EXTERNAL_LAYER, parser, source_id, LAYER_SHARE_END, path)


def layer_share(source_name):
    """The share an external layer was read from (`<table>@<root>`), or None: a name from before 11-04 (no share in
    it), a raws file's, any other writer's."""
    name = str(source_name or "")
    if not name.startswith(EXTERNAL_LAYER) or LAYER_SHARE_END not in name:
        return None
    head = name[len(EXTERNAL_LAYER):].split(LAYER_SHARE_END, 1)[0]
    return head.split("@", 1)[1] if "@" in head else None


def same_share(a, b) -> bool:
    """May layer `a` fold into layer `b` - THE question the write's fold asks (`file_layer_fold`): one
    share, or either share not known (an old name, a raws file), which folds as every file layer did before."""
    share_a, share_b = layer_share(a), layer_share(b)
    return share_a is None or share_b is None or share_a == share_b


def value_key(value, col_type: str):
    """What a value COMPARES as - the ONE equality every 「did this cell change」 asks (총괄
    a7d2e90ec · 2dd93d4a9 2): a blank is absence (판정 284), a number column compares numbers
    when the value reads as one, a datetime column instants (`expression._wall` on the declared zone),
    anything else its text with the ends trimmed."""
    if is_blank_value(value):
        return None
    if col_type == "number":
        try:
            number = float(value)
        except (ValueError, TypeError):
            number = None
        if number is not None and number == number:          # a «nan» text compares as its text, not as NaN
            return ("n", number + 0.0)                          # + 0.0 folds -0.0 into 0.0
    if col_type == "datetime":
        import expression

        moment = expression._wall(value, expression.time_zone())
        if moment is not None:
            return ("t", moment)
    return ("s", str(value).strip())


def values_differ(old, new, col_type: str) -> bool:
    return value_key(old, col_type) != value_key(new, col_type)


def line_text(value, col_type: str):
    """A value as a line stores it - text whatever the column's type, so retyping a column never touches history
    (총괄 11-10 ㄱ). Built from `value_key`: two values get one text exactly when they compare equal. None = absent."""
    key = value_key(value, col_type)
    if key is None:
        return None
    kind, v = key
    return repr(v) if kind == "n" else v.isoformat() if kind == "t" else v


def line_value(text, col_type: str):
    """A line's text read back as the column's type - the one read-side cast."""
    if text is None:
        return None
    if col_type == "number":
        try:
            number = float(text)
        except ValueError:
            return text
        if number != number:
            return text
        return int(number) if number.is_integer() and abs(number) < 2 ** 53 else number   # «2.0» reads back as 2
    if col_type == "datetime":
        from datetime import datetime

        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return text
    return text


def file_layer_fold(col_srcs, source_name: str, value, col_type: str, table_name: str,
                    pin=None):
    """(repeat, folded, moved) for a file layer about to be written into a cell (총괄 225b2c658 · f224477c1), by the
    file layers of its share that hold the same value (`same_share`; each share keeps its own layer, owner «ㄷ») and
    the newest layer of its whole priority class - the one the cell shows of it (QA 11-08):

    repeat  its share holds the value and the class's newest is a file layer saying it too - write nothing
    moved   its share holds the value but the class's newest does not say it - that layer goes to the front, no new
            layer (소유자 11-08 «층을 새로하지 말고 순서를 바꿔»: share A's newer file repeating its old value takes
            the cell back from share B's change); the share's other layers of the value are `folded`
    neither its share does not hold the value - its own layer is written
    The same layer resent unchanged is the seat's `source_unchanged`, not this: it is not a new statement.
    Never the pinned one.
    """
    rank = get_source_priority(source_name, table_name)
    same_class = [s for s in col_srcs if get_source_priority(s.source_name, table_name) == rank]
    same = [s for s in same_class
            if same_share(s.source_name, source_name) and s.source_name not in (source_name, pin)
            and is_file_layer(s.source_name) and not values_differ(s.value, value, col_type)]
    if not same:
        return False, [], None

    def newest(layers):
        name = compute_priority_value({s.source_name: {"value": s.value, "ingested_at": s.ingested_at}
                                       for s in layers}, None, table_name)[1]
        return next(s for s in layers if s.source_name == name)
    top = newest(same_class)
    if is_file_layer(top.source_name) and not values_differ(top.value, value, col_type):
        return True, [], None
    keep = newest(same)
    return False, [s for s in same if s is not keep], keep


# Config location comes from the single override point (server/paths.py, ASSY_DATA_ROOT).
# Same import guard as event_constants above: crud can be imported without server/ on sys.path.
try:
    import paths as _paths
except ImportError:  # pragma: no cover - defensive fallback
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    import paths as _paths

CONFIG_PATH = _paths.config_path("table_config.json")

def sanitize_to_utf8(data: Any) -> Any:
    """
    데이터 객체(Dict, List, Str 등) 내부의 모든 문자열을 재귀적으로 탐색하여 
    비유효한 UTF-8 바이트 시퀀스를 제거/정정합니다.
    JSON 직렬화가 불가능한 datetime/UUID 등도 문자열로 변환합니다.
    """
    if isinstance(data, dict):
        return {k: sanitize_to_utf8(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_to_utf8(v) for v in data]
    elif isinstance(data, str):
        # 비유효한 UTF-8 바이트를 무시(ignore)하고 다시 디코딩하여 깨끗한 문자열 생성
        return data.encode("utf-8", "ignore").decode("utf-8")
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, uuid.UUID):
        return str(data)
    elif hasattr(data, "isoformat"):
        return data.isoformat()
    else:
        return data

class TableConfigError(RuntimeError):
    """table_config.json exists but cannot be read as a table map.

    Two causes, both parse-level: the bytes are not decodable/parsable JSON, or
    they parse into something that is not a JSON object. Raised only by
    `load_table_config_or_raise`. Deliberately narrow: see the scope note on
    that function for what does NOT raise.
    """


def _parse_position(exc) -> str:
    """Where the parse gave up, in a form an operator can act on."""
    if isinstance(exc, json.JSONDecodeError):
        return f"line {exc.lineno} column {exc.colno} (char {exc.pos}): {exc.msg}"
    if isinstance(exc, UnicodeDecodeError):
        return f"byte offset {exc.start}: not valid UTF-8 ({exc.reason})"
    return str(exc)


def _decode_config_text(raw: bytes) -> str:
    """Decode config bytes, honouring whatever BOM the operator's editor wrote.

    On Windows a BOM is the DEFAULT, not an exotic case. PowerShell 5.1 writes a
    UTF-8 BOM from `Set-Content -Encoding utf8` and `Out-File`, a bare `>`
    redirect writes UTF-16 LE with a BOM, and Notepad offers "UTF-8 with BOM"
    outright. A plain `raw.decode("utf-8")` turns every one of those into a
    UnicodeDecodeError - and because boot is fail-fast on decode/parse failures,
    an operator who added one column with the wrong editor would get a file that
    looks perfect in every editor and a web server that never starts again.

    A BOM is an encoding marker, not content: stripping it is not leniency about
    corrupt input, it is reading the file in the encoding it was written in.
    Bytes with no BOM are still strict UTF-8, so genuinely mis-encoded files
    (e.g. cp949 Korean saved without a BOM) still raise.
    """
    # UTF-32 LE (ff fe 00 00) must be tested BEFORE UTF-16 LE (ff fe), which is
    # its prefix - otherwise every UTF-32 LE file decodes as UTF-16 garbage.
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig")
    if raw.startswith(codecs.BOM_UTF32_LE) or raw.startswith(codecs.BOM_UTF32_BE):
        return raw.decode("utf-32")
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16")
    return raw.decode("utf-8")


def load_table_config_or_raise():
    """Boot-time loader. Raises TableConfigError when the file cannot be parsed.

    [#13] Coming up "successfully" with zero tables is the worst outcome
    available on a restart: the UI looks wiped, the log is clean, and nobody has
    a thread to pull. Callers on the boot path use this one so the process dies
    with the reason attached.

    SCOPE - what raises and what deliberately does not:
      raises : the file is present and is not JSON, or its bytes cannot be
               decoded. A leading BOM is read as the encoding marker it is
               (see _decode_config_text), so BOM-prefixed files are NOT failures.
      returns: the file is absent (a fresh install has no config yet).
      returns: the file cannot be read (OSError - a lock, a permission blip).
               An unreadable file is not a corrupt one, and refusing to boot on
               a transient read failure trades one outage for another.
      returns: the file parses but declares something odd. Semantic complaints
               must never keep a production server down.
      raises : the file parses but is not a JSON object. That is not a semantic
               complaint - `[]` or `null` cannot be a table map at all, and
               every consumer here treats the result as a mapping. Letting one
               through produces exactly the failure #13 exists to abolish: a
               server that boots with zero dynamic models and a near-clean log.
    """
    import shipped
    if not os.path.exists(CONFIG_PATH):
        return shipped.merged({})
    try:
        with open(CONFIG_PATH, "rb") as f:
            raw = f.read()
    except OSError as exc:
        # Not a parse failure -> loud, but not fatal (see scope note above).
        logger.error(
            f"[Config] Could not read table_config.json at '{CONFIG_PATH}' "
            f"([{type(exc).__name__}] {exc}). Continuing with an EMPTY table config."
        )
        return {}
    try:
        parsed = json.loads(_decode_config_text(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TableConfigError(
            f"table_config.json is not valid JSON: '{CONFIG_PATH}' -> {_parse_position(exc)}"
        ) from exc
    if not isinstance(parsed, dict):
        # Measured: `[]` reached models.init_dynamic_models(), died on
        # AttributeError, was caught by main's broad `except Exception`, and the
        # server came up with ZERO dynamic models behind a single ERROR line -
        # the UI looks wiped, the log looks fine. `null` was worse: TABLE_CONFIG
        # stayed None for the whole process lifetime.
        raise TableConfigError(
            f"table_config.json must be a JSON object mapping table name -> "
            f"declaration, but its top level is {type(parsed).__name__}: '{CONFIG_PATH}'"
        )
    # the tables the product ships stand beside the owner's (owner 11-06, `shipped`)
    return shipped.merged(parsed)


def load_table_config():
    """Runtime-safe loader: returns {} on failure, but never silently.

    [#13] The old body was `except Exception: return {}` with no log. Live, the
    empty-config guard in models.refresh_dynamic_models absorbed it, so the only
    visible symptom was a schema change that never arrived; on a restart it was
    every table disappearing at once. Returning {} is still right here - it is
    what stops a bad read from wiping the live singleton - but the log line is
    what turns "everything vanished" into "line 3, column 5 of this file".
    """
    try:
        return load_table_config_or_raise()
    except TableConfigError as exc:
        logger.error(
            f"[Config] {exc}. Returning an EMPTY table config - the in-memory "
            f"config and the physical schema are left UNCHANGED."
        )
        return {}

def update_table_config(new_config: dict):
    """테이블 설정을 갱신하고 디스크에 저장합니다."""
    global TABLE_CONFIG
    TABLE_CONFIG.update(new_config)
    try:
        import shipped
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(shipped.owner_only(TABLE_CONFIG), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[crud] Failed to save table config: {told(e)}")

import sys
from error_said import told
if not hasattr(sys, "_table_config_singleton"):
    sys._table_config_singleton = load_table_config()
TABLE_CONFIG = sys._table_config_singleton


class ReadOnlyRelation(ValueError):
    """⛔ THIS RELATION DOES NOT ACCEPT WRITES — a REFUSAL, not a fault.

    A `ValueError` still, because that is what the sentence was raised as before it moved
    here and callers already catch it that way; a NAME so the route can answer 422 with the
    reason instead of 500 with a traceback.
    """


def refuse_write_to_view(table_name):
    """🔴 THE ONE PLACE 「이 관계가 쓰기를 받나」 IS ANSWERED (S-224).

    The sentence used to live INSIDE `apply_batch_updates`, on the reasoning that every
    write converges there. It does not. `create_empty_rows_batch`, `delete_rows_batch`,
    `delete_cell_source_batch` and `set_cell_manual_priority_batch` reach the relation
    directly, and on a view none of them found a gate — the owner's add-row button answered
    **500** `TypeError: 'row_id' is an invalid keyword argument`, which is what a missing
    refusal looks like when the model happens to lack a column. Where the view DOES declare
    `row_id` there is no crash at all: the deletes would have removed that row's cell layers
    and let PostgreSQL refuse only the last statement.

    🔴 BEFORE THE EMPTY-PAYLOAD SHORTCUT, in every caller. 「빈 요청이라 통과됐다」 and
    「쓸 수 있는 관계라 통과됐다」 must not be the same answer, or the refusal starts
    depending on what the caller happened to send.

    ⚠️ `catalog_kind` DECIDES THE WORD, not a fourth spelling of
    `.get("kind") or "table"` — that function exists because this repository already had
    four of them (S-187).
    """
    from ledger.setup_bundle import catalog_kind

    if catalog_kind(TABLE_CONFIG.get(table_name)) == "view":
        raise ReadOnlyRelation(
            "'%s' is read-only (kind: view) - the catalogue declares it a view, so it takes no writes." % table_name)


def normalize_stored_text(value: Any) -> Any:
    """THE write-boundary normalizer for text. Strips a string; leaves anything else alone.

    [Why storage, and not a cleverer comparison]
    `clean_str_value` (the read/compare spelling) strips with Python's `str.strip()`,
    which removes ALL Unicode whitespace - tab, newline, CR, FF, VT, NBSP (U+00A0),
    ideographic space (U+3000), the U+2000-200A range: 29 codepoints. Postgres
    `btrim(x)` with no second argument strips exactly ONE of them, U+0020.

    So if storage were allowed to hold `"\t"`, Python would call it empty and SQL would
    call it non-empty, and any pushed-down predicate would disagree with the payload the
    user is looking at. The fix is NOT to teach SQL Python's whitespace table - that is a
    second spelling that drifts. The fix is that the divergent input never reaches
    storage, after which `col IS NULL OR col = ''` and `clean_str_value(v) == ""` are the
    same predicate BY CONSTRUCTION.

    This is not a new policy; it is the layer that was never told. `clean_str_value`
    already strips on every read and compare, `_update_row_business_key` already strips
    `business_key_val`, and the line below already mapped a whitespace-only value to NULL.
    Only the non-empty case still let surrounding whitespace through.

    Only `str` is stripped. A list/dict (the JSON columns - `map_doe.mat_*` carries raw
    material tokens where "the token text IS the identity") is returned untouched: those
    are containers, not text, and their elements are not this boundary's business.
    """
    return value.strip() if isinstance(value, str) else value


#: What a cell refused for an infinite number is told it expected (owner 11-08 2ㄱ) - `cast_value_by_type`.
INFINITE_EXPECTED = "a finite value (not an infinite value)"


class CellRefused(ValueError):
    """A value its column's type does not take - ONE sentence for it, whichever door wrote the
    row (총괄 bed890af2 ②: the grid said it in Korean, a file load stored a traceback).

    `row` is the 1-based row of what the caller submitted, where a caller knows it. The write funnel does not raise
    it any more - it folds the cell (`DROP_VALUE_REFUSED`, owner 10-29); the casts outside the funnel still do."""

    def __init__(self, column, value, expected, row=None):
        super().__init__(column, value, expected)
        self.column, self.value, self.expected, self.row = column, value, expected, row

    def __str__(self):
        where = "Row %s: column" % self.row if self.row is not None else "Column"
        return "%s '%s' does not take '%s' - %s is expected." % (
            where, self.column, self.value, self.expected)


#: What an operator does about a column that was offered and not written, by reason - the
#: first words of the sentence, because a file's status field keeps 500 characters (총괄
#: c4faced98 · d4a949a8c ③).
NOT_WRITTEN_NEXT = {
    DROP_UNDECLARED_COLUMN: "declare the undeclared columns in table_config.json",
    DROP_UNMAPPED_COLUMN: "reload or restart so this process holds the unmapped columns, "
                          "then Retry the file",
    DROP_VALUE_REFUSED: "fix the values their columns' types do not take - the rest of each row was written",
    DROP_TWO_VALUES: "fix the rule - one answer gave these cells two values, neither was written",
}


def _first_shown(value):
    """A refused value as the not-written sentence shows it - an infinite number by name (owner 11-08 2ㄱ)."""
    return "an infinite value" if isinstance(value, float) and math.isinf(value) else repr(value)


def not_written_sentence(by_reason, tail, firsts=None, rows=None):
    """`Next: <actions>. <tail>: <reason> <columns> · ...[ over N row(s).]` - ONE spelling for the
    columns offered and not written, a file's and a grid save's (lead 10-29), whether some rows were
    written (`tail` "Not written") or none (`NothingWritten`). `by_reason` is `{reason: {column:
    values}}`, or `{reason: [column, ...]}` where the values are not known (a header); `firsts`
    `{column: the first value refused there}` (the drop report's refused_values); `rows` the rows
    offered. None when it names no reason of NOT_WRITTEN_NEXT."""
    reasons = [reason for reason in NOT_WRITTEN_NEXT if by_reason.get(reason)]
    if not reasons:
        return None
    firsts = firsts or {}
    named = []
    for reason in reasons:
        columns = by_reason[reason]
        named.append("%s %s" % (reason, ", ".join(
            "%s=%s%s" % (column, columns[column], " (first %s)" % _first_shown(firsts[column]) if column in firsts else "")
            for column in sorted(columns))
            if isinstance(columns, dict) else ", ".join(sorted(columns))))
    return "Next: %s. %s: %s%s" % ("; ".join(NOT_WRITTEN_NEXT[reason] for reason in reasons),
                                   tail, "; ".join(named), "" if rows is None else " over %d row(s)." % rows)


class NothingWritten(ValueError):
    """A file every column of which was dropped, so nothing of it was written - ONE sentence
    whichever parser read it (총괄 8e54a261b ② · f0578f20a): the standard parser meets it in the
    header, the file loader's write loop in the rows. `columns` is `{reason: [column, ...]}` -
    undeclared, or declared and not held by this process's model (총괄 d4a949a8c ③). Named by
    column, not by value count, because the header does not know the values."""

    def __init__(self, table, columns):
        super().__init__(table, columns)
        self.table = table
        self.columns = {reason: sorted(names) for reason, names in dict(columns).items() if names}

    def __str__(self):
        return not_written_sentence(
            self.columns, "Nothing was written to '%s' - dropped" % self.table) + "."


def cast_value_by_type(value: Any, col_type: str, col_name: str,
                       table_name: str = None) -> Any:
    """컬럼의 타입 스펙에 맞춰 데이터를 int, float 등으로 명시적으로 형변환합니다.

    This is the write boundary: `apply_row_update_internal` runs EVERY value through it,
    and that function's only caller is `apply_batch_updates` - the funnel every write
    path converges on. Normalizing here rather than at each call site is the same
    reasoning `refuse_virtual_join_columns` records: a per-call-site rule is one the next
    author has to remember.
    """
    # The write boundary asks THE blank question rather than restating it (S2,
    # 2026-09-03). Proven identical over a twelve-value matrix before folding:
    # `v is None or str(v).strip() == ""` and `is_blank_value(v)` disagree ZERO
    # times, 0 and 0.0 and False included.
    if none_if_blank(value) is None:
        return None
    if isinstance(value, numbers.Real) and not isinstance(value, bool) and not math.isfinite(value):
        raise CellRefused(col_name, value, INFINITE_EXPECTED)          # owner 11-08 2ㄱ: every column, by name

    if col_type == "datetime":
        # 🔴 SCHEMA_CANON R5 IS ENFORCED HERE FOR THE FIRST TIME (S-182 ⓐ, 판정 289).
        # This function has never had a datetime arm, and the catalogue's own comment
        # measured what that costs: 「assy_qa 에서 실측 — offset 붙은 문자열은 제대로 앉고,
        # 쓰레기는 거절되고(DataError), **naive 문자열은 세션 TimeZone 으로 조용히
        # 재해석된다**」. R5 forbids exactly that value, and until now nothing looked.
        #
        # 🔴 [d94342107] THE OWNER ANSWERED R5 ⓑ - NOT A REFUSAL BUT A ZONE (「한국시간」). Round ⓐ passed a naive
        #    value through unchanged, so PostgreSQL read it in the SESSION zone while its key read it in the
        #    declared one: one text, two instants. It is now read where the key reads it (`expression._wall`,
        #    ingestion_settings "expression_time_zone") and passed on with that zone's offset. Still counted -
        #    «it came without an offset» is the observation. A value with an offset, and a text that is not a time
        #    (PostgreSQL refuses it as before), pass byte-identical.
        #    ⚠️ ONLY INTO A TIME COLUMN (총괄 after 3ea1ae778): a text column declared datetime is not read by
        #    PostgreSQL, its key already reads it in the declared zone, so the person's text stays as written.
        if time_format.time_is_naive(value):
            time_format.note_naive_time(table_name, col_name)
            import expression
            from chain import join_key_index

            moment = (None if join_key_index.column_is_text(table_name, col_name)
                      else expression._wall(value, expression.time_zone()))
            if moment is not None:
                value = moment.isoformat()
        # 🔴 [총괄 791c0f45e 4] A datetime OBJECT - what the chain moves out of a datetime
        #    column - leaves here in crud's JSON spelling (ISO, its offset kept), because the
        #    layer is JSON and the object made the whole write raise TypeError. Text passes
        #    byte-identical and the instant never moves, so round ⓐ above still holds.
        return sanitize_to_utf8(value)

    if col_type == "number":
        val_str = str(value).strip()
        try:
            if "." in val_str:
                return float(val_str)
            else:
                return int(val_str)
        except ValueError:
            # [NUM1, found by contracts/blank_predicate 2026-07-31] The branch above
            # decides int-vs-float by asking whether the REPR contains a '.'. `str(1e16)`
            # is `'1e+16'` and `str(1e-05)` is `'1e-05'` - neither has one - so both went
            # to `int()` and were REFUSED, for values that are ordinary doubles the column
            # (`double precision`) holds exactly. Decide from the VALUE, not from its repr.
            #
            # Strictly additive: every input that already parsed still takes the branch
            # above and returns the same type it always did. This arm only converts a
            # refusal into a value.
            #
            # nan/inf stay REFUSED. They parse as floats but are not data - letting them
            # through would put a NaN in a numeric column, where every comparison against
            # it is false and no filter can ever find the row again.
            try:
                parsed = float(val_str)
            except ValueError:
                parsed = None
            if parsed is not None and math.isfinite(parsed):
                return parsed
            raise CellRefused(col_name, value, INFINITE_EXPECTED if parsed is not None and math.isinf(parsed)
                              else "a number") from None

    # 🔴 [총괄 c6a8c069c ㉡, 소유자 「문자타입에 숫자 들어올때 정수형으로 접어서」] A NUMBER INTO A
    # TEXT COLUMN IS STORED IN `clean_str_value`'S SPELLING, the one every reader already uses.
    # Passed through, the layer kept a JSON number (1.0) while PostgreSQL wrote '1.0' into the
    # text column - Python read '1', `->>` read '1.0', one cell with two answers - and a notation
    # rule, which reads text, never met it. A bool is a number to Python and stays as it came; a NaN is blank and an
    # infinite number refused above, so every number here is finite.
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        value = clean_str_value(value)
    # Strip BEFORE sanitizing: the UTF-8 scrub can only remove bytes, so it can turn
    # `"abc\udcff"` into `"abc"` but never introduces whitespace - order is not
    # load-bearing today, and doing it first keeps "normalize, then sanitize" readable.
    return sanitize_to_utf8(normalize_stored_text(value))

def times_the_database_refuses(db: Session, table_name: str, updates) -> tuple:
    """`({column: {spelling, ...}}, {column: {spelling: timestamptz}})` - the values (as `str(value).strip()`) headed for this table's time columns that PostgreSQL will not read as a
    timestamptz, asked of PostgreSQL itself (lead 10-29), and its reading of the rest: the write puts that moment in
    the batch ahead of the key, so a time without a zone is stored on `expression_time_zone` whichever spelling it came
    in (lead 10-31 - the text went to PostgreSQL, which read it on the session's zone, while our reader's ISO went on
    this one). Measured on 24 spellings: our reader (`expression.TIME`)
    and PostgreSQL part on nine - «2026.10.29», «2026/10/29», «3:05 PM», «20261029» ... are taken by PostgreSQL and
    not by us - so our reader cannot be the judge without dropping values that load today.

    ONE query for the batch's values that are not already in the reader's ISO spelling (those PostgreSQL always
    takes), in a savepoint; only when it refuses are the values halved and asked again, so k bad values among n cost
    about 2k·log n queries and a clean batch one. No version branch: `pg_input_is_valid` would need PostgreSQL 16.
    A text column declared datetime is not read by PostgreSQL (`join_key_index.column_is_text`) and is not asked.
    Another database never refuses a time here, so it is not asked either."""
    types = (TABLE_CONFIG.get(table_name) or {}).get("column_types") or {}
    asked = {}                                          # {spelling: {column, ...}}
    for item in updates:
        for column, value in (getattr(item, "updates", None) or {}).items():
            spelling = time_text_to_ask(table_name, column, types.get(column), value)
            if spelling is not None:
                asked.setdefault(spelling, set()).add(column)
    readings, refused = times_postgresql_reads(db, asked)
    out, read = {}, {}
    for spelling, columns in asked.items():
        for column in columns:
            if spelling in refused:
                out.setdefault(column, set()).add(spelling)
            elif spelling in readings:
                read.setdefault(column, {})[spelling] = readings[spelling]
    return out, read


def time_text_to_ask(table_name: str, column: str, declared_type, value):
    """The spelling (`str(value).strip()`) PostgreSQL is asked to read for a value headed for a declared time column,
    or None - not a time column, blank, already a datetime, in our reader's ISO spelling (`expression.TIME`, which
    PostgreSQL always takes), or a text column declared datetime (`join_key_index.column_is_text`). The one question
    the write's refusal (`times_the_database_refuses`) and the nokey print (`NokeyPrint`) ask (lead 10-31)."""
    if declared_type != "datetime" or is_blank_value(value) or isinstance(value, (bool, datetime)):
        return None
    import expression
    from chain import join_key_index

    if isinstance(value, str) and expression.TIME.match(value.strip()):
        return None
    if not isinstance(value, (str, numbers.Real)) or join_key_index.column_is_text(table_name, column):
        return None
    return str(value).strip()


def times_postgresql_reads(db: Session, spellings, zone=None) -> tuple:
    """`({spelling: timestamptz}, {refused spelling, ...})` - ONE query for all, in a savepoint; only when PostgreSQL
    refuses are the spellings halved and asked again, so k bad ones among n cost about 2k·log n queries and a clean set
    one. No version branch: `pg_input_is_valid` would need PostgreSQL 16. Another database is not asked: ({}, set()).

    A time without a zone is read on `zone` - the ledger's declared one (lead 10-31 ②) - else on `expression_time_zone`,
    the zone `key_part` reads it on (lead 10-31): the
    savepoint sets TimeZone to it and puts the session's back before it is released - a SET LOCAL outlives a released
    savepoint until the transaction ends (measured), and the write's transaction goes on after this."""
    if db.get_bind().dialect.name != "postgresql":
        return {}, set()
    from sqlalchemy import exc as sa_exc, text as sa_text
    from session_contract import in_savepoint
    import expression

    readings, refused = {}, set()
    zone = zone or expression.time_zone().key
    setting = sa_text("SELECT current_setting('TimeZone'), set_config('TimeZone', :zone, true)")
    statement = sa_text("SELECT v, CAST(v AS timestamptz) FROM unnest(CAST(:vals AS text[])) AS v")
    put_back = sa_text("SELECT set_config('TimeZone', :zone, true)")

    def read(part):
        session_zone = db.execute(setting, {"zone": zone}).first()[0]
        rows = db.execute(statement, {"vals": part}).all()
        db.execute(put_back, {"zone": session_zone})
        return rows

    def ask(part):
        try:
            readings.update(in_savepoint(db, "times_the_database_refuses", lambda: read(part)))
        except sa_exc.DataError:
            if len(part) == 1:
                refused.add(part[0])
                return
            half = len(part) // 2
            ask(part[:half])
            ask(part[half:])

    if spellings:
        ask(sorted(spellings))
    return readings, refused


def clean_str_value(val: Any) -> str:
    """값을 깔끔하게 문자열로 변환합니다. float인 경우 소수점 이하가 .0이면 정수로 처리합니다.

    ⚠️ **The `7.0` -> `'7'` fold does NOT diverge from PostgreSQL, and a green SQLite test
    is what makes people think it does.** (Recorded 2026-07-31 because it was got wrong
    once already, in a task brief.) `number` maps to `Float` maps to `double precision`,
    and Postgres renders `cast(col AS varchar)` of 7.0 as `'7'` - agreeing with this
    function. It is the SQLite TEST dialect that renders `'7.0'`. So a suite run on SQLite
    shows a divergence that production does not have, and reasoning from it produces a fix
    for a bug that is not there.
    `contracts/blank_predicate` scores the production dialect as an opt-in axis
    (`ASSY_CONTRACT_PG_URL`); `dialect_facts` in its vectors.json holds the measurement.

    The one float case that DOES diverge is exponent notation - `str(1e16)` is
    `'10000000000000000'` here and `'1e+16'` in Postgres. That is
    `declared_divergences.FLOAT_EXPONENT`, deliberately not chased (Lead PM, 2026-07-31),
    and it is out of reach of every production column measured that day.
    """
    if val is None:
        return ""
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return str(val)
    return str(val).strip()


def none_if_blank(value: Any) -> Any:
    """`value`, or None when it is blank (`is_blank_value`) - THE fold the write boundary makes
    (`cast_value_by_type`) and the value a cell shows from its stored layers (`compute_priority_value`) passes:
    a layer stored before the fold (box: 67 «""» layers of 07-17 ~ 08-07) wins as None (총괄 11-05)."""
    return None if is_blank_value(value) else value


def is_blank_value(val: Any, *, containers: bool = False, identity: bool = False, spaces: bool = True) -> bool:
    """THE blank judgement (owner 11-08 1ㄱ): None · a text of only whitespace · a NaN (float, Decimal) · pandas' NA
    and NaT. The text «nan» is a value; so is an infinite number (the write refuses it by name, `cast_value_by_type`).
    Every seat asks this; where one differs on purpose it is an argument here, not a second function:
      containers   a list or tuple of blanks and an empty dict are blank too - the expression language's
      identity     a key part: a float not finite or from KEY_EXACT_LIMIT up names nothing (`is_blank_key_part`)
      spaces=False «absent» rather than «blank»: a text of spaces is a present value (판정 194 ㉢ - the ledger's role
                   frame, and the entrances turning pandas' markers into None: `mapper_call`, `pipeline_base`)
    SQL twin: `blank_sql_condition`.

    🔴 `str(x or "").strip() == ""` IS NOT THIS: `or ""` calls 0, 0.0, False, [] and {} blank (2026-09-03, a
    twelve-value matrix - five disagreements)."""
    if val is None:
        return True
    if isinstance(val, str):
        return spaces and not val.strip()
    if isinstance(val, bool):
        return False
    if isinstance(val, numbers.Real):
        if val != val:                                                  # NaN, any float kind
            return True
        return identity and isinstance(val, float) and not (math.isfinite(val) and abs(val) < KEY_EXACT_LIMIT)
    if isinstance(val, decimal.Decimal):
        return val.is_nan()
    if isinstance(val, (list, tuple)):
        return containers and all(is_blank_value(v, containers=True, identity=identity, spaces=spaces) for v in val)
    if isinstance(val, dict):
        return containers and not val
    if type(val).__module__.startswith(("pandas", "numpy")):
        import pandas as pd

        missing = pd.isna(val)
        if missing is True or (getattr(missing, "shape", None) == () and bool(missing)):
            return True
    return spaces and clean_str_value(val) == ""


def row_is_blank(values) -> bool:
    """A file row with no value in its DECLARED cells - skipped, not written, by every parser
    path (총괄 69aad666e C: the standard parser skipped it, a workspace parser's rows counted it).
    `is_blank_value` per cell, so a cell of spaces is blank on both."""
    return all(is_blank_value(v) for v in values)


def blank_sql_condition(col_expr):
    """THE emptiness predicate, SQL side. Must answer exactly like `is_blank_value`.

    🔴 **This is only correct because `normalize_stored_text` makes storage canonical.**
    It tests NULL-or-empty and nothing else - deliberately no `btrim`, because `btrim`
    would be an incomplete imitation of `str.strip()` (1 codepoint of 29) and a complete
    one would be a 29-character class that the next schema change silently invalidates.
    Storage carries the invariant instead, so the SQL stays this short.

    If you are tempted to add trimming here, the actual bug is upstream: something wrote
    a value that did not pass through `cast_value_by_type`.

    ⚠️ **PRECONDITION: `col_expr` must be text-typed.** This compares against `''`, and
    PostgreSQL rejects `double precision = ''` outright. Casting inside instead was
    considered and rejected - a `CAST` wrapped around an already-varchar column can cost
    the planner an index. Every caller therefore passes a cast expression:
    `main.get_column_filter_condition` (`col_expr` is already `cast(raw_col, String)` on
    the blank path) and `enrichment_analysis._human_resolved_cells`
    (`cast(tgt, String)`).

    🔴 **Callers, so a future reader can check that this is still the only spelling:**
    `blank_to_null` · `not_blank_sql_condition` · `main.get_column_filter_condition`
    (`blank`/`notBlank`) · `enrichment_analysis._human_resolved_cells`. The 2026-07-31
    contract counts these by AST; a new inline `or_(x.is_(None), x == "")` is a finding,
    not a style preference.
    """
    from sqlalchemy import or_
    from sqlalchemy.sql import sqltypes
    from sqlalchemy.sql.elements import Cast

    # a number column's NaN is blank too, by the column's type (owner 11-08 1ㄱ): its text is 'NaN' only there - a text
    # column's «NaN» is a value, as in Python
    if isinstance(col_expr, Cast) and isinstance(getattr(col_expr.clause, "type", None), sqltypes.Numeric):
        return or_(col_expr.is_(None), col_expr == "", col_expr == "NaN")
    return or_(col_expr.is_(None), col_expr == "")


def blank_to_null(col_expr):
    """`col_expr`, or SQL NULL wherever `blank_sql_condition` calls it blank.

    The COALESCE-shaped building block the virtual-join resolved value is made of.
    Written as a CASE over `blank_sql_condition` rather than as `NULLIF(col, '')` on
    purpose: NULLIF would be a THIRD spelling of "blank", indistinguishable today and
    free to drift tomorrow. Deriving it means the resolved value cannot disagree with
    the emptiness test it is built on.
    """
    from sqlalchemy import case
    return case((blank_sql_condition(col_expr), None), else_=col_expr)


def not_blank_sql_condition(col_expr):
    """Negation of `blank_sql_condition` - derived, so the two cannot answer differently (a number column's 'NaN',
    owner 11-08 1ㄱ). `NOT (c IS NULL OR ...)` lets no NULL through: a NULL c makes the inner OR true.

    Same text-typed precondition as `blank_sql_condition`; see there.
    """
    return ~blank_sql_condition(col_expr)


class _NaN(TypeDecorator):
    """A NaN a number column is compared with: bound as the float, drawn inline as the dialect spells one -
    PostgreSQL 'NaN'::float8, SQLite NULL (it stores a NaN as NULL). A bare float('nan') drawn inline is the word
    nan, which both read as a column (A 11-08: the hold count's gates, `hold_copy._gated`). One class at module
    level: the statement cache keys on it - a class made per call missed the cache every time (lead 11-08)."""
    impl, cache_ok = Float, True

    def literal_processor(self, dialect):
        return lambda _value: "'NaN'::float8" if dialect.name == "postgresql" else "NULL"


def _nan_sql():
    """-> the NaN a number column is compared with (`_NaN`)."""
    from sqlalchemy import literal

    return literal(float("nan"), _NaN())


# The BIGINT-safe magnitude guard in `numeric_text_sql`. Conservative: 9.2e18 < 2**63,
# so the CAST(... AS BIGINT) arm can never raise "bigint out of range" on PostgreSQL.
BIGINT_SAFE_NUMERIC_TEXT_BOUND = 9.2e18


def numeric_text_sql(col_expr):
    """A NUMERIC column rendered to its canonical comparison text - the SQL twin of
    `clean_str_value`'s numeric branch, INT spelling included (7.0 -> '7', 7.5 -> '7.5').

    Exists for `virtual_join_executor.resolved_expression` (board item N7, user report
    2026-08-02): a numeric expose column cannot sit in `COALESCE(..., '<label>')` as a
    number. On PostgreSQL the pre-fix expression died twice over - `blank_to_null`'s
    `col = ''` arm violates `blank_sql_condition`'s stated text-typed precondition
    (`double precision = ''` is refused outright), and `COALESCE(double precision, text)`
    cannot be matched to one type. The user ruling: cast to STRING for the COALESCE, and
    spell integral values as INT (a slot comes back as 3, never 3.0).

    Why not a plain `cast(col, String)`: the dialects disagree about it. PostgreSQL
    renders float8 7.0 as '7' (shortest round-trip - `contracts/blank_predicate`
    `dialect_facts`, measured 2026-07-31); SQLite renders '7.0'. Python's
    `clean_str_value` folds integral floats through `str(int(v))`. This expression
    produces the int spelling ON EVERY DIALECT instead of leaning on the agreement
    Postgres happens to share with Python:

        CASE WHEN col BETWEEN -9.2e18 AND 9.2e18
             THEN CASE WHEN CAST(col AS BIGINT) = col
                       THEN CAST(CAST(col AS BIGINT) AS VARCHAR)
                       ELSE CAST(col AS VARCHAR) END
             ELSE CAST(col AS VARCHAR) END

    - NULL needs no arm of its own: every branch propagates NULL (CAST(NULL) is NULL,
      `NULL = col` is UNKNOWN -> else -> CAST(NULL AS VARCHAR) is NULL). That is also
      why this does NOT wrap `blank_to_null`: for a number the blank rule genuinely is
      IS NULL alone - a number is never `''` (the blank-predicate contract's own
      wording: "numbers are not text; the SQL blank arm is IS NULL"). Adding the text
      blank test here would be a per-row no-op bought at WHERE-clause cost on a
      10-million-row scan.
    - The magnitude guard is what keeps the BIGINT cast from raising on PostgreSQL for
      |v| >= 2**63. Beyond the bound the plain cast runs and the dialects may reach
      exponent notation - the same reach as `declared_divergences.FLOAT_EXPONENT`
      (deliberately not chased, Lead PM 2026-07-31), out of range of every production
      column measured that day. WITHIN the bound this actually agrees with Python even
      at 1e16, where the plain Postgres cast does not.
    - Dialect rounding differences in the BIGINT cast (SQLite truncates 3.7 -> 3,
      Postgres rounds 3.7 -> 4) cannot change any answer: the folded spelling is used
      only when the cast round-trips EQUAL to the original value, i.e. only when the
      value was integral to begin with.
    """
    from sqlalchemy import case, cast, String, BigInteger, and_, null
    as_big = cast(col_expr, BigInteger)
    folded = case((as_big == col_expr, cast(as_big, String)),
                  else_=cast(col_expr, String))
    return case(
        (col_expr == _nan_sql(), null()),                              # a NaN is blank (owner 11-08 1ㄱ)
        (and_(col_expr >= -BIGINT_SAFE_NUMERIC_TEXT_BOUND,
              col_expr <= BIGINT_SAFE_NUMERIC_TEXT_BOUND), folded),
        else_=cast(col_expr, String),
    )


# ---------------------------------------------------------------------------
# Rendering a column to its canonical comparison TEXT - one funnel, every type
#
# [Board item N8, 2026-08-04. Why this is a family and not a second numeric patch]
# `virtual_join_executor.resolved_expression` builds `COALESCE(<parts>, '<label>')`.
# The label is TEXT, so EVERY part must be text. N7 shipped that insight as "numeric
# needs a cast", and the next type through the same door - `datetime` - died with the
# identical failure (`InvalidDatetimeFormat`, measured on PostgreSQL 18.3). Boolean
# dies too (`InvalidTextRepresentation`, same measurement), and on SQLite it does not
# even crash: it answers `True` for every unmatched row, which is worse.
#
# So the question is not "which types need a cast" but "which types are ALREADY text".
# `column_text_sql` below inverts the test accordingly: only the string family goes
# through untouched; everything else is rendered, and anything this file has never
# heard of falls to a plain CAST rather than to a 500. A type added tomorrow cannot
# reopen this defect.
#
# THE COLUMN TYPES THIS SYSTEM CAN ACTUALLY PUT HERE (measured 2026-08-04):
# `models.init_dynamic_models` maps `table_config` `column_types` to exactly three
# SQLAlchemy types - `number`->Float, `datetime`->DateTime(timezone=True), everything
# else->String - plus the shared metadata columns, which add Boolean
# (`is_graph_synced`, `needs_graph_rollback`) and DateTime (`created_at`, `updated_at`,
# `graph_synced_at`). A metadata NAME declared in `column_types` is skipped by the
# model builder but still resolves to the metadata column, and `virtual_join_config`
# validates `expose` against `column_types` keys - so Boolean and DateTime are both
# reachable through an ordinary declaration. The live config declares
# `production_plan.created_at/updated_at` as `datetime` today.
# Numeric / Integer / Enum / JSON / ARRAY / UUID are NOT produced by the model builder;
# they are handled defensively (Enum explicitly, the rest by the CAST fallback) because
# "not produced today" is exactly the reasoning that left `datetime` broken.
#
# EACH RENDERER HAS A PYTHON TWIN, and that pairing is the point. The SQL text is what
# a filter / `?q=` / CSV export compares; the twin is what the row payload carries into
# the browser. A renderer added without its twin re-creates the seam this closes.
# ---------------------------------------------------------------------------

# The canonical temporal text. UTC, space-separated, microseconds ALWAYS six digits.
#
# 🔴 It is pinned, not inherited from the dialect, and here is what the dialect default
# actually is (PostgreSQL 18.3, live, 2026-08-04): `CAST(timestamptz AS varchar)` renders
# `2026-08-04 06:23:39.123456+00` in the SESSION's TimeZone (measured `+09` here, because
# the GUC is Asia/Seoul) and DROPS the fractional part entirely when it is zero. Both
# halves of that are moving targets - the offset follows a server GUC, the width follows
# the value - so a text comparison built on it would answer differently on two servers
# holding the same row. SQLite, by contrast, stores DATETIME as this exact literal text,
# which is why the default arm of `temporal_text_sql` is a plain CAST.
#
# Fixed width also buys an accident that is worth naming: lexical order equals
# chronological order, so `lessThan` on a resolved temporal column is not a lie.
TEMPORAL_TEXT_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
_PG_TEMPORAL_TEXT_FORMAT = "YYYY-MM-DD HH24:MI:SS.US"


def _install_temporal_text_construct():
    """The one dialect-branching construct in this module, built once at import.

    A `@compiles` variant rather than a runtime `if dialect == 'postgresql'` because the
    expression is handed to callers that never see a connection (`resolved_expression`
    takes a Session but the expression outlives the call, and the CSV export re-binds it
    to a streaming statement). Letting the compiler choose keeps one expression object
    correct on every bind.
    """
    from sqlalchemy import String as _String, cast as _cast, func as _func
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.sql.functions import FunctionElement

    class _TemporalText(FunctionElement):
        type = _String()
        name = "temporal_text"
        inherit_cache = True

    @compiles(_TemporalText)
    def _default(element, compiler, **kw):
        # SQLite (this suite) stores DATETIME as 'YYYY-MM-DD HH:MM:SS.ffffff' - the
        # canonical spelling verbatim - so the plain cast IS the pinned format. Any
        # other dialect lands here too; that is the no-crash floor, not a promise
        # that its spelling matches. Add a variant when a third dialect appears.
        return compiler.process(_cast(list(element.clauses)[0], _String), **kw)

    @compiles(_TemporalText, "postgresql")
    def _postgresql(element, compiler, **kw):
        col, zone = list(element.clauses)
        # `timezone(zone, ts)` is the function spelling of `ts AT TIME ZONE zone`.
        return compiler.process(
            _func.to_char(_func.timezone(zone, col), _PG_TEMPORAL_TEXT_FORMAT), **kw)

    return _TemporalText


_TemporalText = _install_temporal_text_construct()


def temporal_text_sql(col_expr, zone="UTC"):
    """A DATE/TIME column rendered to `TEMPORAL_TEXT_FORMAT`. SQL twin of
    `temporal_text_value`.

    NULL propagates (CAST and `to_char` both return NULL for NULL), which is the whole
    blank rule for a temporal column: a timestamp is never `''`, so - exactly as with
    `numeric_text_sql` - this is deliberately NOT wrapped in `blank_to_null`. Wrapping it
    would put `col = ''` back in front of a non-text column, which is the crash.

    `zone` is the zone the wall clock is spelled in, on PostgreSQL. SQLite has no zone
    database; its spelling is the stored UTC whatever `zone` says.
    """
    return _TemporalText(col_expr, zone)


def temporal_text_value(value):
    """Python twin of `temporal_text_sql`: the same instant, the same spelling.

    Aware values are converted to UTC first, so the text does not depend on the
    connection's session timezone. Naive values are taken as already-UTC (that is what
    the SQLite test dialect hands back, and the only shape a naive column can be here).
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.strftime(TEMPORAL_TEXT_FORMAT)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).strftime(TEMPORAL_TEXT_FORMAT)
    return value


def boolean_text_sql(col_expr):
    """A BOOLEAN column rendered to `'true'` / `'false'`. SQL twin of
    `boolean_text_value`.

    The NULL arm is written out FIRST and on purpose: `CASE WHEN col THEN ... ELSE ...`
    routes NULL to the ELSE, so without it every unmatched row would resolve to
    `'false'` - a value - instead of folding into the unresolved label.

    Spelling `'true'`, not Python's `'True'`: the payload carries the raw boolean, JSON
    writes it as `true`, and the browser prints `true`. `clean_str_value(True)` is
    `'True'` and is the one spelling nobody ever sees. (PostgreSQL's own
    `CAST(bool AS varchar)` agrees with this choice - measured 18.3, 2026-08-04 - but the
    CASE is written out anyway so SQLite, which would say `'1'`, cannot disagree.)
    """
    from sqlalchemy import case
    return case((col_expr.is_(None), None), (col_expr, "true"), else_="false")


def boolean_text_value(value):
    """Python twin of `boolean_text_sql`."""
    if value is None or not isinstance(value, bool):
        return value
    return "true" if value else "false"


def boolean_text_read(value, name="value"):
    """The reading twin of `boolean_text_value`: the two words it writes, `true` / `false` (case
    and surrounding space aside), a bool as itself, a blank as None - anything else is refused
    as `name`, in `validation.flag_refusal`'s sentence (총괄 d4a949a8c ⑤: "yes" was True to one
    reader and False to another)."""
    if isinstance(value, bool):
        return value
    if is_blank_value(value):
        return None
    word = str(value).strip().lower()
    if word in ("true", "false"):
        return word == "true"
    import validation

    raise ValueError(validation.flag_refusal(name, value))


def column_text_sql(col_expr):
    """THE funnel: any column expression rendered to the canonical comparison text.

    🔴 The test is "is this ALREADY text", not "is this one of the types we know to be a
    problem". The second shape is what shipped N7 and left `datetime` and `boolean`
    holding the identical crash; an unknown type therefore falls to a CAST, never to the
    raw column.

    `Enum` is pulled out of the string family explicitly: SQLAlchemy models it as a
    String subclass, but on PostgreSQL a native enum column compared to `''` raises the
    same way a float does. No dynamic table declares one - which is precisely the
    sentence that was true of `datetime` last week.
    """
    from sqlalchemy import cast, String
    from sqlalchemy.sql import sqltypes

    col_type = getattr(col_expr, "type", None)
    if isinstance(col_type, (sqltypes.Numeric, sqltypes.Float, sqltypes.Integer)):
        return numeric_text_sql(col_expr)
    if isinstance(col_type, sqltypes.Boolean):
        return boolean_text_sql(col_expr)
    if isinstance(col_type, (sqltypes.DateTime, sqltypes.Date, sqltypes.Time)):
        return temporal_text_sql(col_expr)
    if isinstance(col_type, sqltypes.JSON):
        # The scalar itself (`#>> '{}'` / `json_extract(.., '$')`): a CAST reads JSON null as
        # 'null' and "" as '""', neither of them blank (총괄 c773b0fed ③ - a layer's value).
        return blank_to_null(col_expr[()].as_string())
    if isinstance(col_type, sqltypes.String) and not isinstance(col_type, sqltypes.Enum):
        return blank_to_null(col_expr)
    # Unknown, or text-shaped but not text-typed. Cast FIRST so `blank_sql_condition`'s
    # stated text-typed precondition holds on every dialect.
    return blank_to_null(cast(col_expr, String))


def resolved_text_value(value):
    """Python twin of `column_text_sql`, for the value that goes into the row PAYLOAD.

    Renders exactly the families whose SQL spelling this module pins to text, so the
    grid paints the string a filter / `?q=` / CSV export will compare against.

    🔴 Numbers ride RAW, and that is a recorded gap, not an oversight. The numeric payload
    has shipped as a JSON number since N7; the browser stringifies it with JavaScript's
    rules, which agree with the SQL text everywhere except a measured band
    (`contracts/blank_predicate` `NUMERIC_BROWSER_SPELLING`, board item N9). Rendering it
    here would close that band AND change a shipped cell value's type, which is a
    boundary-contract decision for the Lead PM - not one to take in passing.
    """
    if isinstance(value, bool):
        return boolean_text_value(value)
    if isinstance(value, (datetime, date)):
        return temporal_text_value(value)
    return value


def comparison_text_value(value):
    """A FILTER value rendered the way the resolved column spells it.

    `main.get_column_filter_condition` bridges a non-string filter value against a
    text-resolved virtual column with this. `clean_str_value` alone is not enough: it
    spells a boolean `'True'` where the column spells `'true'`, and a datetime with
    whatever `str()` gives rather than `TEMPORAL_TEXT_FORMAT`.
    """
    rendered = resolved_text_value(value)
    return rendered if isinstance(rendered, str) else clean_str_value(rendered)


def get_row_by_business_key(db: Session, table_name: str, key_value: Any):
    """테이블별 비즈니스 키를 기반으로 행을 조회합니다. (인덱스 컬럼 사용으로 최적화)"""
    # `clean_str_value`, not `str().strip()`: an identity has ONE spelling and the
    # writers use that function. A float 1234.0 is `'1234'` there and would be
    # `'1234.0'` here, so this lookup would miss the row it stored itself.
    target_val = clean_str_value(key_value) if key_value is not None else ""
    if not target_val:
        return None
        
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return None
        
    return db.query(table_model).filter(
        table_model.business_key_val == target_val
    ).first()

def resolve_priority_map(table_name: str = None) -> dict:
    """[QA G1-⑥] 소스 서열 맵 해석의 단일 원천 — 테이블별 source_priority 커스텀 포함.

    표시값 레이어링과 provenance 판정이 같은 맵을 공유한다(서열 이원화 금지).
    """
    priority_map = SOURCE_PRIORITY
    if table_name:
        table_info = TABLE_CONFIG.get(table_name, {})
        custom_priority = table_info.get("source_priority")
        if custom_priority and isinstance(custom_priority, dict):
            priority_map = custom_priority
    return priority_map


def get_source_priority(source_name: str, table_name: str = None) -> int:
    """소스명 → 우선순위 값(작을수록 우선, 미등재 99). 레이어링과 동일 서열 — 이름은 `layer_ranks_as` 로 읽는다."""
    return resolve_priority_map(table_name).get(layer_ranks_as(source_name), 99)


_last_layer_instant = None
_layer_instant_lock = threading.Lock()


def layer_instant() -> datetime:
    """🔴 THE ONE SEAT THAT STAMPS A CELL LAYER'S `ingested_at` (총괄 9280922aa): now, and in this
    process strictly after the last one it gave - equal or earlier moves one microsecond on.

    `compute_priority_value` ranks equal sources by the newest delivery, so the later item of
    one batch must carry the later time, as it would in a batch of its own. Each layer took
    `datetime.now()`: two items in one clock tick tied and the source NAME picked the earlier,
    so a batch's answer depended on the clock (measured, report ff9867655).
    """
    global _last_layer_instant
    with _layer_instant_lock:
        now = datetime.now()
        if _last_layer_instant is not None and now <= _last_layer_instant:
            now = _last_layer_instant + timedelta(microseconds=1)
        _last_layer_instant = now
        return now


def resolution_ingested_at(entry: Any, source_name: str = None,
                           ingested_at_by_source: dict = None):
    """A source layer's `ingested_at` as absolute POSIX seconds, or None if unknown.

    Callers spell the SAME column three different ways and there is no third
    storage - `cell_sources.ingested_at` is the only origin of any of them:
      * `{"value", "timestamp": <ISO str>, "updated_by"}` - crud + main.py,
      * `{"value", "ingested_at": <datetime>}`            - chain_replay.withdraw_source,
      * a bare scalar value with no timestamp at all      - main.fetch_and_merge_metadata,
        whose `sources` payload is a client-facing contract (`{source: value}`) and
        therefore cannot carry one. That caller passes `ingested_at_by_source`
        instead, which is why this override is checked FIRST.

    Naive and aware datetimes coexist in one dict on purpose-free grounds: the write
    path stamps `layer_instant()` (naive, local) while PostgreSQL's `timestamptz`
    reads back aware. Comparing the two raises TypeError, so both are normalised to
    UTC here - `astimezone()` reads a naive value as local, which is exactly what
    `layer_instant()` produced.
    """
    raw = None
    if ingested_at_by_source and source_name is not None:
        raw = ingested_at_by_source.get(source_name)
    if raw is None and isinstance(entry, dict):
        raw = entry.get("ingested_at")
        if raw is None:
            raw = entry.get("timestamp")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if not isinstance(raw, datetime):
        return None
    try:
        return raw.astimezone(timezone.utc).timestamp()
    except (ValueError, OSError, OverflowError):  # pragma: no cover - defensive
        return None


#: chain.formula - imported at the first cell asked about (it imports this module).
_FORMULAS = []


def _rule_priorities() -> dict:
    """{rule: declared priority} (`rule_shape.priorities`) - read where the chain's rules are loaded."""
    from chain import rule_shape

    return rule_shape.priorities()


def _rule_order() -> dict:
    """{rule: its place in the rules file} (`rule_shape.declared_order`)."""
    from chain import rule_shape

    return rule_shape.declared_order()


def _formulas():
    if not _FORMULAS:
        from chain import formula

        _FORMULAS.append(formula)
    return _FORMULAS[0]


def formula_written(table_name: str, column: str, source_name) -> Optional[str]:
    """The formula's name («formula T.c») when this write is a formula column's - a chain write to a column a formula
    computes, which only the formula's rule may write (`formula.second_writers`) - else None. Such a write holds no
    layer and leaves no line of its own: the value is the declaration's, its history the batch's receipt (lead 10-28)."""
    if layer_ranks_as(source_name) != CHAIN_SOURCE or (table_name, column) not in _formulas().columns():
        return None
    return _formulas().RULE_NAME % (table_name, column)


_TERMS_MEMO = ("rank_terms",)


def rank_terms(table_name: str = None):
    """THE layer order, as one list of terms - each term(line, unowned) - that `compute_priority_value` and
    `lines.merge` both walk, so the two cannot drift (C 11-11). A line is {"ranks_as", "owner_rule", "at" (POSIX
    seconds or None), "source_name"}. `unowned`: a chain layer no rule owns sits on the cell.
    Smaller sorts first; the pin is not a term (it wins before the order is asked)."""
    priority_map = resolve_priority_map(table_name)
    said = _rule_priorities()
    order = _rule_order()

    return [
        # 1. declared ranking
        lambda ln, u: priority_map.get(ln["ranks_as"], 99),
        # 1b. a rule that says its priority before one that does not
        lambda ln, u: 0 if ln["owner_rule"] in said else 1,
        # 1c. the smaller priority
        lambda ln, u: said.get(ln["owner_rule"], 0),
        # 1d. the rule declared later - unless an unowned chain layer sits on the cell
        lambda ln, u: -order.get(ln["owner_rule"], -1) if ln["owner_rule"] and not u else 0,
        # 2a. a dated layer beats an undated one
        lambda ln, u: 0 if ln["at"] is not None else 1,
        # 2b. newest first
        lambda ln, u: -ln["at"] if ln["at"] is not None else 0.0,
        # 2c. one instant, the later line - a batch's lines share its time and the later item wins, as
        #     layer_instant's later time for it did (A QA 11-11); a layer with no line (cell_sources) skips it
        lambda ln, u: -(ln.get("line_id") or 0),
        # 3. total order, always decides
        lambda ln, u: ln["source_name"],
    ]


def compute_priority_value(sources: dict, manual_priority_source: str = None, table_name: str = None,
                           ingested_at_by_source: dict = None, ranks: dict = None, cell: tuple = None):
    """여러 소스들 중 가장 우선순위가 높은 값을 결정합니다.

    🔴 THE ORDER IS EXPLICIT AND TOTAL, AND IT HAS TO BE. This used to be
    `sorted(sources.keys(), key=priority_map.get(k, 99))` and nothing else. Every
    file-derived source name is unregistered, so all of them return 99 and ALL OF
    THEM TIE; `sorted` is stable, so the winner fell to dict insertion order, and
    that order is not arbitrary - the write path loads the stored sources first and
    appends the incoming one last (`apply_row_update_internal`), so the INCUMBENT
    won every tie by construction. A later delivery carrying a corrected value was
    stored in `cell_sources` and then discarded in silence, because `has_changed`
    was false and that suppresses the column write, the audit log AND the outbox
    event. Measured 2026-08-11 on `assy_qa`: 200 of 200 tied cells displayed the
    older value. Worse than wrong, it was not even stable - the tiebreak was
    physical heap order, so a VACUUM FULL could change a displayed value with no
    write and no audit entry.

    The three levels, and why each one exists:

    1. **Registered priority** (`priority_map`, unregistered = 99). The DECLARED
       ranking is the authority and this change does not move it: `user` (0) still
       outranks every machine source, and a registered source still outranks an
       unregistered filename. Levels 2 and 3 only ever break a tie WITHIN one
       priority - they can never promote a lower-ranked source over a higher one.
    2. **`ingested_at` descending** - among equally-ranked sources the most recent
       delivery is the current statement of fact, and an older one is by definition
       superseded. A layer whose timestamp is unknown sorts AFTER one that has it
       (2a), so a legacy NULL cannot displace a dated delivery; without 2a the
       comparison would also have to order `None` against a float.
    3. **`source_name` ascending** - the final TOTAL order. Two layers can carry the
       same `ingested_at` (two processes stamp in one clock tick, or the layers were stored
       before `layer_instant`),
       and without a total order the answer would fall back to dict order, which is
       the defect above. `idx_sources_lookup_source` is unique on
       (table, row, column, source_name), so within one cell `source_name` is unique
       and level 3 always decides. The result therefore does not depend on the order
       the caller assembled `sources` in, on the SELECT that produced it, or on the
       physical row order underneath that SELECT.

    `cell` (table, column, row): a column a formula rule writes has one more layer, undated, ranked as the chain
    (`chain.formula.columns`, lead 10-28) - its value is the formula over `row`. A pin names a stored layer only.
    """
    formula = None
    if cell is not None:
        formula = _formulas().columns().get(cell[:2])
    if not sources and formula is None:
        return None, None

    if manual_priority_source and manual_priority_source in sources:
        return layer_value(sources, manual_priority_source), manual_priority_source
    if formula is not None and formula[0] not in sources:
        sources = {**sources, formula[0]: {}}
    else:
        formula = None

    # `ranks` - a batch's memo over its rows, one table (here: the term list, built once); alone, this call's own
    ranks = {} if ranks is None else ranks

    # a chain layer no rule owns yet (written before owner 11-06 step 2, not adopted) has no rule to order by - while
    # one sits on the cell, the chain's layers there order by time as before
    unowned = any(layer_ranks_as(name) == CHAIN_SOURCE and not layer_owner(name) for name in sources)
    terms = ranks.get(_TERMS_MEMO)
    if terms is None:
        terms = ranks[_TERMS_MEMO] = rank_terms(table_name)

    def _rank(name):
        # two rules' layers on one cell: the priority decides, then the rule declared later - never ingested_at
        # (owner 11-06 step 2 1ㄱ, lead 11-08 ㄴ). One rule's layers, a file's or a person's: as before.
        owner = layer_owner(name)
        line = {"ranks_as": layer_ranks_as(name), "owner_rule": owner[0] if owner else None,
                "at": resolution_ingested_at(sources[name], name, ingested_at_by_source), "source_name": name}
        return tuple(term(line, unowned) for term in terms)

    # `min` rather than `sorted`: the same first element, without materialising and
    # sorting the whole list on a per-cell hot path.
    top_source = min(sources.keys(), key=_rank)
    if formula is not None and top_source == formula[0]:
        return none_if_blank(formula[1]([{name: getattr(cell[2], name, None) for name in formula[2]}])), top_source
    return layer_value(sources, top_source), top_source


def layer_value(sources: dict, name):
    """What layer `name` of `sources` says - its "value" (or the entry itself), a blank as absence. The value
    `compute_priority_value` returns for its pin or winner, and the batch's one-layer memo's (QA 11-08: it copied it)."""
    val_data = sources[name]
    return none_if_blank(val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data)

#: The declaration cell that scopes `?q=`. Absent means "the identity" - see
#: `resolve_search_columns`, which is the only place that spelling lives.
SEARCH_COLUMNS_KEY = "search_columns"


def search_scope_default(table_info: dict) -> tuple:
    """What `?q=` searches when nothing declares otherwise: the row's IDENTITY.

    🔴 MEASURED, AND THE DEFAULT IS THE WHOLE FINDING (S-125, 판정 255). The old default
    was "every declared column, plus every virtual-join column". On `dt_log` that built 31
    ILIKE arms over casts AND SIX aliased LEFT JOINs to `dt_inventory` on the same key -
    2,174 ms, a sequential scan, and the filter applied only after all six joins were
    built. A plain page and a `?cols=`-scoped search both build ZERO joins, so the cost
    was created entirely by the unscoped default rather than by searching as such.

    ⚠️ NEVER EMPTY. A scope that contributes no condition returns the WHOLE TABLE with a
    200 while the response implies a search happened - this function's own caller carries
    the refusal written for that incident. `row_id` and `business_key_val` are physical on
    every dynamic table, so the last fallback cannot be empty.
    """
    key = (table_info or {}).get("composite_key_source") or ()
    if key:
        return tuple(key)
    business_key = (table_info or {}).get("business_key")
    if business_key:
        return (business_key,)
    return ("row_id", "business_key_val")


def resolve_search_columns(table_name: str, known_columns=None) -> tuple:
    """`(columns, unknown)` - the declared `?q=` scope for a table, and the names in it
    that nothing can search.

    🔴 ONE SPELLING, TWO READERS, AND THAT IS WHY IT RETURNS THE UNKNOWNS INSTEAD OF
    LOGGING THEM. The search path knows the virtual-join columns from its binder; the
    config load knows them from the rules file. Both must reach the same verdict about the
    same declaration, so the DECISION is here and each caller says it in its own voice -
    a second copy of this rule is how one door comes to search a column the other refuses.

    ⛔ AN UNKNOWN NAME IS NOT DROPPED IN SILENCE (판정 255). It is returned so the caller
    can name it; a `search_columns` entry that nothing matches is a declaration the
    operator believes is in force.

    `known_columns` of None means "do not judge" - the caller could not enumerate what is
    searchable, so it must not report absences it cannot see.
    """
    table_info = (TABLE_CONFIG.get(table_name) or {})
    declared = table_info.get(SEARCH_COLUMNS_KEY)
    if not isinstance(declared, (list, tuple)) or not declared:
        return search_scope_default(table_info), ()

    columns = tuple(str(c).strip() for c in declared if str(c).strip())
    if known_columns is None:
        return columns, ()

    known = set(known_columns) | {"row_id", "business_key_val"}
    unknown = tuple(c for c in columns if c not in known)
    return tuple(c for c in columns if c in known) or search_scope_default(table_info),         unknown

def unmapped_columns(table_name: str, columns) -> list:
    """The `columns` this process's model of `table_name` does not hold - the one answer the
    write door and the file watcher's filter share (총괄 791c0f45e 3)."""
    model = models.DYNAMIC_TABLES.get(table_name)
    if model is None:
        return []           # no model at all: the door refuses the table by name
    return [column for column in columns if column not in model.__table__.columns]


def loadable_columns(table_info: dict) -> tuple:
    """The columns a write may land in this table, in declaration order (S-119, 판정 12:20).

    🔴 ONE ANSWER FOR EVERY ROUTE, BECAUSE THERE WERE TWO. The file watcher filtered by
    `display_columns` and dropped what was not there BEFORE this module ever saw the row;
    this module filtered by `column_types`. So a column declared in one and not the other
    landed through the API and was silently discarded through the watcher - measured on
    `dt_log`, whose `dt_job` the API writes and the watcher drops. Same table, same file,
    two answers depending on which door it came through.

    🔴 `column_types` IS THE LOADABLE AXIS AND `display_columns` IS THE SHOWING ONE.
    A column can exist and be written without being on a screen; a screen cannot show a
    column that does not exist. Loading therefore asks "does this exist", which is the
    question `column_types` answers. `display_columns` keeps its own job -
    `GET /tables/{t}/schema` and the grid - and is not consulted here.

    ⚠️ AN EMPTY DECLARATION STILL MEANS NOTHING LOADS, and that is unchanged on both
    sides: this module already dropped every column of a table with no `column_types`, and
    the watcher already dropped every column of one with no `display_columns`. What is new
    is that they now say it about the SAME declaration.
    """
    return tuple((table_info or {}).get("column_types") or ())


def create_audit_log(db: Session, table_name: str, row_id: str, col_name: str, old_val: Any, new_val: Any, source: str, user: str, transaction_id: str = None, business_key: str = None, add_to_cache: bool = True):
    """감사 로그를 기록합니다. (저장 전 인코딩 정제 수행)

    None - no line, no db.add, nothing cached - for a column its table keeps no history for (`keeps_history`).
    add_to_cache=False는 인메모리 캐시 추가뿐 아니라 DB persist(db.add)도 생략한다.
    이 경우 호출자가 반환된 log_dict를 모아 commit 전에 bulk_insert_audit_logs로
    직접 DB에 적재할 책임을 진다.
    """
    if not keeps_history(table_name, col_name):     # owner 11-09 ㄴ · lead ㅁ''': whoever wrote it
        return None
    if not transaction_id:
        transaction_id = str(uuid6.uuid7())

    from datetime import timezone
    ts = datetime.now(timezone.utc)
    
    clean_old = sanitize_to_utf8(old_val)
    clean_new = sanitize_to_utf8(new_val)

    # [P2-C9] 값 길이 상한 — sanitize_to_utf8은 인코딩 정제만 하므로 길이는 무제한이었다.
    # 대형 텍스트 셀(맵 문자열류)이 대상이 되면 created_logs 500건 절단 후에도 페이로드가
    # 수십 MB가 될 수 있다(2026-07-25 이벤트 루프 동결 인시던트의 잔여 경로).
    # 절단은 **DB 저장본과 통지 dict 양쪽에 동일 적용**하고, 절단 사실은 값 안의 마커로 명시된다.
    clean_old, old_truncated = truncate_audit_value(clean_old)
    clean_new, new_truncated = truncate_audit_value(clean_new)
    if old_truncated or new_truncated:
        _warn_audit_truncation_once(table_name, col_name)

    if add_to_cache:
        log = models.AuditLog(
            table_name=table_name,
            row_id=row_id,
            column_name=col_name,
            old_value=clean_old,
            new_value=clean_new,
            source_name=source,
            updated_by=user,
            transaction_id=transaction_id,
            timestamp=ts,
            business_key=business_key
        )
        db.add(log)

    log_dict = {
        "id": 0,
        "table_name": table_name,
        "row_id": row_id,
        "column_name": col_name,
        "old_value": clean_old,
        "new_value": clean_new,
        "source_name": source,
        "updated_by": user,
        "transaction_id": transaction_id,
        "business_key": business_key,
        "timestamp": ts
    }
        
    return log_dict

def receipt_log(db, table_name, batch_id, label, facts, source, who, transaction_id, row_ids=None) -> list:
    """A batch's receipt in the history - lines under RECEIPT_COLUMN whose `new_value` is `facts` with `receipt_label`,
    the word the screen shows (lead 10-28: the ledger's «Ledger batch», a formula's «formula T.c»). `row_ids`, the rows
    the batch changed, are split over as many lines as keep each under the audit value cap (MAX_AUDIT_VALUE_CHARS,
    07-25), each line with `part` · `parts` and `rows` - the rows that line names, so a group's lines sum to its rows (lead
    10-28). `transaction_id` as given, None too (판정 248: an invented id makes a backfill look like a group of one).
    Built, not persisted - the caller writes them. -> [line]"""
    from event_constants import MAX_AUDIT_VALUE_CHARS
    from ledger.runtime_v2 import RECEIPT_COLUMN

    said = dict(facts, receipt_label=label)
    parts = [said]
    if row_ids is not None:
        said = dict(said, rows=len(row_ids), part=0, parts=0, row_ids=[])
        room, parts, ids = MAX_AUDIT_VALUE_CHARS - len(repr(said)) - 8, [], []
        used = 0
        for row_id in row_ids:
            cost = len(repr(row_id)) + 2
            if ids and used + cost > room:
                parts.append(ids)
                ids, used = [], 0
            ids.append(row_id)
            used += cost
        parts = [dict(said, rows=len(ids_k), part=k, parts=len(parts) + 1, row_ids=ids_k)
                 for k, ids_k in enumerate(parts + [ids], 1)]
    lines = []
    for value in parts:
        line = create_audit_log(db, table_name, batch_id, RECEIPT_COLUMN, None, value, source, who,
                                transaction_id=transaction_id, add_to_cache=False)
        line["transaction_id"] = transaction_id
        lines.append(line)
    return lines


def keeps_history(table_name, column_name) -> bool:
    """Whether a change of this cell leaves a history line - asked where a line is made: `create_audit_log` (a cell's
    line, whoever wrote it) and `row_update_line` (the columns a row's line names). Not when the table's entry lists
    the column in `no_history_columns` (owner 11-09 ㄴ: the system tables' state cells, a person's hand write too -
    lead ㅁ'''). Unsaid: every column keeps its history."""
    return column_name not in ((TABLE_CONFIG.get(table_name) or {}).get("no_history_columns") or ())


def bulk_insert_audit_logs(db: Session, logs: list[dict]):
    """AuditLog를 Bulk Insert로 초고속 적재합니다."""
    if not logs:
        return
    mappings = []
    for l in logs:
        mappings.append({
            "table_name": l["table_name"],
            "row_id": l["row_id"],
            "column_name": l["column_name"],
            "old_value": l["old_value"],
            "new_value": l["new_value"],
            "source_name": l["source_name"],
            "updated_by": l["updated_by"],
            "transaction_id": l["transaction_id"],
            "timestamp": l["timestamp"],
            "business_key": l.get("business_key")
        })
    db.bulk_insert_mappings(models.AuditLog, mappings)


# ── 재교정률 (re-correction rate) — SYSTEM_OVERVIEW §1 핵심가치 #1 "최소 공수 교정"의 계기 ──
#
# 정의: 창(window) 안에서 사람이 쓴 셀 중, 사람이 **두 번 이상** 쓴 셀의 비율.
#       셀 = (table_name, row_id, column_name). 낮을수록 좋다.
#
# 이 값이 왜 그렇게 계산되는지(각 결정의 근거)는 아래 주석에 남긴다. 숫자만 보고
# 정의를 되짚을 수 없으면, 이 지표는 다시 "그럴듯해 보이는 틀린 숫자"가 된다.

RECORRECTION_WINDOW_DAYS = 7
# 감사 로그는 프루닝되지 않는다(2026-07-27 확인: outbox의 7일 보존은 database_outbox 전용이고
# audit_logs를 지우는 운영 경로는 존재하지 않는다 — 실측 2,628,453행이 프로젝트 개시일부터
# 연속). 창을 7일로 고정하는 것은 보존 한계 때문이 아니라 **지표를 현재 마찰에 반응하게**
# 하기 위해서다. 전 기간 창은 과거 누적에 희석돼 어떤 회귀에도 움직이지 않는다.


def human_lines(db: Session, since) -> list:
    """[(table, row_id, history group, {columns it wrote})] - every line a person wrote at or after `since`, in each
    declared table that keeps lines (`human_source_clause`; the t__lines partial index on it). What the two Overview
    figures count (cell-source overhaul: audit_logs retires)."""
    import sqlalchemy as sa

    from admin import audit_history
    from admin.audit_cache import group_of
    from database import lines

    found = []
    for table_name in sorted(TABLE_CONFIG):
        if not lines.has_lines(db, table_name):
            continue
        bits = audit_history.line_bits(db, table_name)
        t = audit_history.line_table(table_name, bits)
        written = [t.c[name] for name in t.c.keys() if name.startswith("written_")]
        for row in db.execute(sa.select(t.c.row_id, t.c.batch, *written).where(
                human_source_clause(), t.c.at >= since)):
            found.append((table_name, row.row_id, group_of(row.batch),
                          {name for name, bit in bits.items() if audit_history.bit_said(row, bit)}))
    return found


def get_recorrection_stats(db: Session, window_days: int = RECORRECTION_WINDOW_DAYS) -> dict:
    """사람이 같은 셀을 두 번 이상 고친 비율을 반환한다.

    반환: {window_days, measured_cells, recorrected_cells, rate_pct}
    `rate_pct`는 분모가 0이면 None — 표본이 없을 때 0%로 위장하지 않는다.
    분모(`measured_cells`)는 **항상 함께** 반환한다. 분모 없는 비율은 읽을 수 없다.
    A cell is (table, row, column) a person's line wrote in the window (`human_lines`); it is re-corrected when two or
    more of their transactions wrote it - a paste touching a cell twice is one act. A line is written only when a value
    changes, so a re-write of the same value is none.
    """
    from datetime import timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    cells = {}
    for table_name, row_id, group, columns in human_lines(db, cutoff):
        for column in columns:
            cells.setdefault((table_name, row_id, column), set()).add(group)
    measured = len(cells)
    recorrected = sum(1 for groups in cells.values() if len(groups) > 1)
    return {
        "window_days": window_days,
        "measured_cells": measured,
        "recorrected_cells": recorrected,
        "rate_pct": round(100.0 * recorrected / measured, 2) if measured else None,
    }


# ── 완료까지의 상호작용 점수 (interaction score to completion) ────────────────
#
# SYSTEM_OVERVIEW §1 핵심가치 #1 "최소 공수 교정"의 **정본 계기**(사용자 2026-07-29).
# 한 교정 tx를 완료하는 데 사람이 쓴 손의 양. 낮을수록 좋다.
#
#     점수(tx) = key×w_key + mouse×w_mouse + nav×w_nav
#
# 재교정률(위 get_recorrection_stats)은 보조 계기로 강등됐다 — 같은 셀을 두 번 고쳤다는
# 사실만으로는 UI 공수 탓인지 데이터 품질 탓인지 갈라지지 않기 때문이다. 이 계기는 그
# 중간 추론을 건너뛰고 공수 자체를 잰다.
#
# 이 값은 **소급 산출이 불가능**하다(과거 세션에 클릭 로그가 없다). 계측이 붙은 시점부터의
# 데이터만 존재하므로, 교정 표면을 고치기 전에 확보한 기준선이 유일한 "before"다.

EFFORT_WINDOW_DAYS = 7
# 재교정률과 같은 창을 쓴다. 이유도 같다 — 지표가 **현재 마찰**에 반응해야 하고, 전 기간
# 누적은 어떤 회귀에도 움직이지 않는다. 두 계기가 같은 창을 보면 나란히 읽을 수도 있다.


def record_interaction_effort(db: Session, transaction_id: str, session_id: str,
                              key: int, mouse: int, nav: int,
                              nav_preserved: int = 0) -> bool:
    """한 tx의 원시 상호작용 카운트를 기록한다. 기록됐으면 True.

    **계측은 계측 대상을 절대 깨뜨리지 않는다.** 이 함수는 교정이 이미 커밋된 뒤에
    별도 트랜잭션으로 호출되며, 실패하면 로그만 남기고 False를 돌려준다. 공수 한 건을
    놓치는 것이 사용자의 교정을 잃는 것보다 언제나 낫다.

    같은 tx가 재도달하면(클라 재시도) **첫 기록이 이긴다** — UNIQUE 제약 위반을 잡아
    조용히 통과시킨다. 재전송은 사람이 새로 쓴 공수가 아니다.
    """
    from sqlalchemy.exc import IntegrityError
    try:
        db.add(models.InteractionEffortLog(
            transaction_id=transaction_id,
            session_id=session_id,
            key_count=key, mouse_count=mouse, nav_count=nav,
            nav_preserved_count=nav_preserved,
        ))
        db.commit()
        return True
    except IntegrityError:
        # 같은 transaction_id가 이미 있다 = 재시도. 첫 기록 보존.
        db.rollback()
        return False
    except Exception as e:
        db.rollback()
        print(f"[EffortMetric] failed to record effort for tx {transaction_id}: {told(e)}")
        return False


def get_effort_stats(db: Session, weights: dict,
                     window_days: int = EFFORT_WINDOW_DAYS) -> dict:
    """창 안의 상호작용 점수를 **세션별 평균 → 세션 간 평균**으로 반환한다.

    반환: {window_days, avg_score, tx_count, session_count, weights, measured_ratio}

    집계 단위가 왜 두 단계인가(사용자 지정 "세션별 평균"): tx를 통째로 평균하면 한 세션이
    500건을 처리한 날 그 세션이 전체 평균을 지배한다. 세션을 먼저 접으면 각 작업 세션이
    같은 무게를 갖는다 — 재교정률이 transaction_id로 사람 행위를 접는 것과 같은 이유다.

    `measured_ratio`(계측 tx / 전체 사람 tx)는 **필수 동반 값**이다. 계측은 클라이언트가
    보내 줄 때만 이뤄지므로 커버리지가 절대 1.0이라고 가정할 수 없고, 비율 없이 내보낸
    평균은 측정되지 않은 범위까지 대표하는 것처럼 읽힌다(재교정률의 분모와 같은 규율).
    """
    import sqlalchemy as sa
    from datetime import timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    EL = models.InteractionEffortLog

    w_key = float(weights.get("key", 1))
    w_mouse = float(weights.get("mouse", 3))
    w_nav = float(weights.get("nav", 5))
    # 컨텍스트 유지 전이의 배점. 기본 0 = 오늘의 점수는 이 항이 없던 때와 **완전히 동일**하다.
    # 그런데도 카운트를 보관하는 이유: 면제 판단이 틀린 것으로 밝혀졌을 때 이 숫자 하나만
    # 바꿔 과거 데이터를 재채점할 수 있게 하기 위해서다(수집 시점에 버리면 되돌릴 길이 없다).
    w_nav_preserved = float(weights.get("nav_preserved", 0))

    # 1단계: tx당 점수 → 세션별 평균.
    per_session = (
        db.query(
            EL.session_id.label("s"),
            sa.func.avg(
                EL.key_count * w_key + EL.mouse_count * w_mouse + EL.nav_count * w_nav
                + EL.nav_preserved_count * w_nav_preserved
            ).label("avg_score"),
            sa.func.count().label("txs"),
        )
        .filter(EL.timestamp >= cutoff)
        .group_by(EL.session_id)
        .subquery()
    )

    # 2단계: 세션 간 평균. 세션 수·계측 tx 총수를 같은 스캔에서 얻는다.
    avg_of_avgs, session_count, tx_count = db.query(
        sa.func.avg(per_session.c.avg_score),
        sa.func.count(),
        sa.func.coalesce(sa.func.sum(per_session.c.txs), 0),
    ).select_from(per_session).one()

    tx_count = int(tx_count or 0)
    session_count = int(session_count or 0)

    # 분모: 같은 창에서 **사람이 만든 전체 tx** 수 - the people's lines' transactions (`human_lines`).
    total_user_tx = len({group for _t, _r, group, _c in human_lines(db, cutoff)})

    return {
        "window_days": window_days,
        "avg_score": round(float(avg_of_avgs), 2) if avg_of_avgs is not None else None,
        "tx_count": tx_count,
        "session_count": session_count,
        "weights": {"key": w_key, "mouse": w_mouse, "nav": w_nav,
                    "nav_preserved": w_nav_preserved},
        # 표본이 없으면 비율도 없다 — 0.0은 "전부 미계측"과 "측정할 것이 없었다"를 섞어버린다.
        "measured_ratio": round(tx_count / total_user_tx, 4) if total_user_tx else None,
    }


#: [P3] Rows per statement for the cell-metadata bulk helpers. Same value and same
#: 1000-row statements follow the repository's established batch convention.
#:
#: ⚠️ THIS COMMENT USED TO SAY THIS BOUND WAS A CORRECTNESS BOUND ENFORCED BY THE
#: DRIVER - "the wire protocol carries a statement's parameter count in an int16, so
#: no statement may bind more than 32,767 values, psycopg2 refuses before sending".
#: THAT IS FALSE FOR THE DRIVER THIS PROJECT RUNS, and it was believed for a year.
#: psycopg2 interpolates parameters CLIENT-SIDE and ships one finished SQL string:
#: `cursor.mogrify("SELECT %s, %s", ("a", 1))` returns `b"SELECT 'a', 1"`. No bound
#: parameters ever cross the wire, so the extended-query protocol's int16 parameter
#: count - which is real - is never consulted. Re-measured on the isolated `assy_qa`:
#: ONE multi-row upsert of 12,000 rows x 7 columns = 84,000 binds was ACCEPTED and
#: stored all 12,000. Nothing refuses at 32,767; nothing here would notice if it did.
#:
#: 🔴 THE BOUND STAYS, and it is still not a tuning knob - the reasons are just
#: different and none of them is a hard ceiling. What it buys, per statement:
#:   - statement TEXT size and the client-side memory `mogrify` needs to build it.
#:     Measured on a `cell_sources` chunk: 1,000 rows = 7,000 binds is a 23 KB
#:     template that mogrifies to 135 KB on the wire; 12,000 rows is 276 KB -> 1.6 MB,
#:     and it scales with the VALUES, so one fat JSON cell moves it;
#:   - lock duration and rollback cost - a failing multi-row VALUES applies 0 rows of
#:     its chunk (measured) where the executemany it replaced had applied K-1, so a
#:     bigger chunk is a bigger unit of loss on the retry;
#:   - a per-chunk shape the SQL cache in `_pg_multirow_upsert` can reuse.
#: It DOES become a hard parameter ceiling under psycopg (v3), which binds
#: server-side - but `_pg_multirow_upsert` declines on `dialect.driver != "psycopg2"`,
#: so under psycopg3 the fallback carries the load at 7,000 binds and is safe there
#: too. Raising this constant is a memory/rollback trade, not a correctness cliff;
#: say which of the three you measured before you move it.
BULK_CHUNK_SIZE = 1000


def _chunks(seq, size=BULK_CHUNK_SIZE):
    """Successive `size`-long slices of `seq`."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _is_executemany_safe(mappings: list[dict]) -> bool:
    """Can this mapping list be sent as ONE compiled statement + N parameter sets?

    [P3] `.values(chunk)` builds a fresh multi-row VALUES clause - one BindParameter
    object per cell - and compiles it per chunk. Measured on a 100,000-row map file:
    `bulk_upsert_cell_sources` cost 223.2 s, of which only 60.2 s was SQL and 163 s
    was that construction. Being able to hand the driver a flat parameter list instead
    is what this predicate gates.

    ⚠️ [P4] PASSING THIS IS NOT ITSELF THE SPEED-UP, and reading it that way is what
    cost this path a year of per-row round trips. `db.execute(stmt, param_list)` on an
    `ON CONFLICT DO UPDATE` degenerates to `cursor.executemany`, i.e. one round trip
    per row. What the predicate now gates is `_pg_multirow_upsert`, which sends a real
    multi-row `VALUES` - measured 20 statements instead of 20,000 round trips.

    Two properties are required and neither is guaranteed by the type annotation:

    1. **Every mapping carries the same keys.** A ragged list is NOT refused either way
       (총괄 1495534c9 - this said it was): `.values(ragged_list)` raises `CompileError`
       only when the first mapping has the key another lacks, and sends the whole chunk
       without it - NULL, silently - when the first is the one lacking it. So
       `bulk_upsert_cell_sources` fills every mapping to one key set before it gets here.
    2. **No value is a SQL expression.** The collision-merge path used to put
       `func.now()` into these dicts; a `ClauseElement` cannot be bound as a
       parameter. Those sites now emit real datetimes, but an outside caller is free
       to hand one in and must get the old shape rather than an exception.

    Anything that fails either test falls back to the historical per-chunk VALUES
    path, so this is a pure fast path: it can be slow, it cannot be wrong.

    ⚠️ THAT LAST SENTENCE IS A PROPERTY OF TWO FUNCTIONS, NOT OF THIS ONE. Passing here
    only means the list has a uniform, bindable SHAPE; whether the raw send can reproduce
    what the fallback would STORE is decided by `_pg_multirow_upsert`'s decline set. This
    predicate answers True for a key that is present with value `None`, and that alone
    used to be enough to write NULL over a defaulted column - see the `None`-on-a-default
    decline there. Weaken those declines and this sentence becomes false without a word of
    it changing here.
    """
    from sqlalchemy.sql.elements import ClauseElement
    first_keys = mappings[0].keys()
    for m in mappings:
        if m.keys() != first_keys:
            return False
        for v in m.values():
            if isinstance(v, ClauseElement):
                return False
    return True


# A decline in `_pg_multirow_upsert` reverts EVERY write of that shape to one server
# round trip per row - by this path's own census 7.8 s -> 31.2 s on a 100k-row push - and
# until this registry existed it did so with no log line, no counter and no health field.
# The operator saw "ingestion got slow again" and had nothing to separate it from load.
#
# Once per (table, REASON CODE) per process, deliberately not per (table, column): the
# reason codes are a closed vocabulary of four, while column names come from the caller's
# mapping keys, and a registry keyed on those is the unbounded growth
# `_undeclared_column_warned` needs a budget for. The offending column is named in the
# MESSAGE, so the first announcement is still actionable; a second column failing the same
# way on the same table is silent, which is the price of the bound.
_upsert_fastpath_declined_warned = set()


def _warn_upsert_fastpath_declined_once(table_name: str, reason: str, detail: str):
    key = (table_name, reason)
    if key in _upsert_fastpath_declined_warned:
        return
    _upsert_fastpath_declined_warned.add(key)
    logger.warning(
        f"[BulkUpsert] Multi-row fast path DECLINED for '{table_name}' "
        f"(reason={reason}): {detail}. Writes of this shape fall back to ONE SERVER "
        f"ROUND TRIP PER ROW - this path's own census puts a 100k-row push at 7.8 s "
        f"batched and 31.2 s on that fallback. The rows are still written CORRECTLY; "
        f"only the send strategy changed. Once per (table, reason) per process."
    )


def _pg_multirow_upsert(db: Session, table, mappings: list[dict],
                        conflict_cols: list[str], update_cols: list[str],
                        chunk_size: int, copy: bool = False) -> bool:
    """Send `mappings` as one MULTI-ROW `VALUES` statement per chunk. `False` = declined.

    `copy=True` sends them as ONE `COPY ... FROM STDIN` instead - only for rows NO stored row can share a conflict
    key with (the caller's to prove: `bulk_upsert_cell_sources`' new rows). Same declines, same bind processors; a
    database error is translated by SQLAlchemy's own `DBAPIError.instance`, so a unique or NOT NULL failure still
    arrives as `IntegrityError` at the three sites below (lead 11-07: 1,000 new rows x 120 columns, 6.18 -> 3.68 s).

    🔴 WHY THIS EXISTS: `db.execute(stmt, list_of_dicts)` DOES NOT BATCH THIS STATEMENT.
    It reads like a batched send and it is not. SQLAlchemy 2.0 routes a parameter list
    through `insertmanyvalues`, and `insertmanyvalues` refuses any INSERT whose
    `ON CONFLICT DO UPDATE` references `excluded` - measured on this statement,
    `compiled.insertmanyvalues is False` while `dialect.use_insertmanyvalues is True`.
    What is left is `cursor.executemany`, and psycopg2's `executemany` is a Python loop
    over `cursor.execute`: ONE SERVER ROUND TRIP PER ROW.

    Counted with a `cursor_factory` that tallies driver calls, 20,000 mappings into a
    `LIKE cell_sources INCLUDING ALL` scratch table on the isolated `assy_qa`
    (2026-08-12):

        db.execute(stmt, chunk)   execute=     0   executemany=   20   param sets = 20,000
        this function             execute=    20   executemany=    0   param sets =      0

    20 statements against 20,000 round trips, and the wall clock follows: 5.65 s -> 1.19 s,
    **-79 %**, 3 of 3 interleaved rounds, same direction every time. The earlier
    `.values(chunk)` shape sent the same 20 statements but rebuilt a `BindParameter` per
    cell and recompiled per chunk; this keeps that path's SQL and drops its Python.

    ⚠️ IT MUST STAY INSIDE SQLAlchemy - BUT NOT FOR THE REASON THIS DOCSTRING USED TO
    GIVE. `psycopg2.extras.execute_values` on a raw cursor measures the same (1.21 s) and
    is still rejected; both halves of the old justification were measured false and are
    recorded here so nobody re-derives them and concludes the constraint is decorative:

      - "`apply_batch_updates`' business-key recovery would stop seeing the exceptions it
        classifies" - IT CANNOT BE BLINDED FROM HERE. This helper only ever writes
        `cell_sources` and `cell_overwrites`, and NEITHER TABLE HAS A `business_key_val`
        COLUMN (0 rows in `information_schema.columns`). The `uq_bk_*` violation is raised
        by the ORM flush of the DATA row, which happens after this function has returned.
      - "the Session would not know its transaction had gone bad" - it does not know on
        the chosen path either. Measured on all three arms after one identical NOT NULL
        fault: `SessionTransaction.is_active` is still True and `db.commit()` still
        RETURNS SUCCESS while committing nothing. That half buys exactly zero.

    THE REASON THAT IS TRUE, and the only one: three sites in this project catch
    `sqlalchemy.exc.IntegrityError` BY CLASS - `record_interaction_effort`,
    `apply_batch_updates`, and `main.py`'s batch-update endpoint, which is the one this
    helper can actually feed and which turns that class into a 409 instead of a 500. A
    raw cursor raises `psycopg2.errors.NotNullViolation`; measured, `except IntegrityError`
    DOES NOT CATCH IT, so a `cell_sources` NOT NULL or unique failure would sail past all
    three. `exec_driver_sql` goes through the same error translation and connection
    bookkeeping every other statement here uses, for the same measured cost.

    DECLINES (returns False, having written nothing) rather than guessing, whenever the
    caller's existing path would do something this one cannot reproduce. EVERY decline is
    logged once per (table, reason) - see `_warn_upsert_fastpath_declined_once`, and do
    not add a silent one:
      - not PostgreSQL, or not psycopg2 (the `%s` placeholders and the client-side
        interpolation that makes 7,000 binds per statement legal are both psycopg2's);
      - a mapping key that is not a column of `table`;
      - a column carrying a PYTHON-side default that the mappings omit. SQLAlchemy's
        insert would compute and send it (`CellOverwrite.is_overwrite` is `default=True`);
        raw SQL would leave it NULL. Server defaults are fine when OMITTED - PostgreSQL
        still applies those to a column the statement does not name;
      - 🔴 a column carrying ANY default (Python-side or server-side) that a mapping
        SUPPLIES AS `None`. This is the one that was missing and it was destructive.
        SQLAlchemy OMITS a defaulted column from the statement when its value is `None`,
        so the database applies the default; this function names every key of
        `mappings[0]`, so it sent a literal NULL instead. Three columns diverged -
        `cell_sources.ingested_at`, `cell_overwrites.updated_at` and, worst,
        `cell_overwrites.is_overwrite`, whose NULL reads as falsy and silently retires the
        overwrite marker that makes a manual correction beat the automatic layer. It
        applies on the `DO UPDATE` arm too, where it overwrites a REAL stored value with
        NULL - measured, a row seeded `is_overwrite=true` came back NULL - and it does
        it PER ROW, so one bad mapping among 500 good ones corrupts exactly that one and
        leaves the other 500 correct. The scan is one `any()` pass per defaulted key
        (1 key for `cell_sources`, 2 for `cell_overwrites`): 18.8 ms per 100,000
        `cell_overwrites` mappings, against a fallback that costs whole seconds.

    CALLER OBLIGATIONS - both of them, because a list that lists one reads as complete:

      1. `_is_executemany_safe` must have passed. This reads the key list off
         `mappings[0]` and assumes the list is not ragged.
      2. 🔴 `mappings` MUST ALREADY BE UNIQUE ON `conflict_cols`. Two mappings sharing one
         conflict key in ONE multi-row statement is not last-value-wins here: PostgreSQL
         raises SQLSTATE 21000 `ON CONFLICT DO UPDATE command cannot affect row a second
         time`. Measured on both tables, that surfaces as `sqlalchemy.exc.ProgrammingError`
         with `.orig = psycopg2.errors.CardinalityViolation` - NOT an `IntegrityError`, so
         none of the three `except IntegrityError` sites sees it, nothing retries it, and
         the whole transaction aborts: the batch is lost, not the duplicate. Note that the
         executemany send this replaced TOLERATED duplicates silently (last value won), so
         this precondition is newly load-bearing and a caller written against the old
         behaviour fails in production and nowhere else.
         Both current callers rebuild a dict keyed on exactly `conflict_cols` before
         dispatching; a third caller must do the same. Splitting duplicates across chunks
         does NOT help by accident - it happens to work, because the violation is
         per-statement, but nothing orders the list to make that true.
    """
    bind = db.get_bind()
    dialect = bind.dialect
    if dialect.name != "postgresql" or dialect.driver != "psycopg2":
        _warn_upsert_fastpath_declined_once(
            table.name, "dialect",
            f"the bind is {dialect.name}+{dialect.driver}, not postgresql+psycopg2")
        return False

    keys = list(mappings[0].keys())
    cols = []
    for k in keys:
        col = table.c.get(k)
        if col is None:
            _warn_upsert_fastpath_declined_once(
                table.name, "unknown_column",
                f"mapping key '{k}' is not a column of this table")
            return False
        cols.append(col)
    for col in table.c:
        if col.default is not None and col.name not in mappings[0]:
            _warn_upsert_fastpath_declined_once(
                table.name, "python_default_omitted",
                f"column '{col.name}' carries a Python-side default and the mappings "
                f"omit it")
            return False

    # 🔴 A DEFAULTED COLUMN SUPPLIED AS `None` IS NOT THE SAME AS A DEFAULTED COLUMN
    # OMITTED, and the guard above only sees the omission. SQLAlchemy drops the column
    # from the statement in BOTH cases, so the database applies the default; this
    # function names every key it was given, so `None` becomes a literal NULL. Measured
    # against the fallback on the isolated `assy_qa`, INSERT arm and `DO UPDATE` arm
    # alike: `is_overwrite` True -> NULL, `ingested_at` 2020-01-01 -> NULL. See the
    # docstring's decline list for why the `is_overwrite` case is the one that matters.
    #
    # Keys are scanned rather than columns so the mapping key is what is tested (a
    # `Column.key` need not equal its `Column.name`), and `any()` runs the scan in C.
    # `server_default` counts as well as `default`: PostgreSQL computing `now()` is not
    # reproducible from Python, so the only faithful answer is to hand the batch back.
    for k, col in zip(keys, cols):
        if col.default is None and col.server_default is None:
            continue
        if any(m[k] is None for m in mappings):
            _warn_upsert_fastpath_declined_once(
                table.name, "defaulted_column_is_none",
                f"column '{k}' carries a default and at least one mapping supplies it "
                f"as None, which the fallback stores as the DEFAULT and a raw statement "
                f"would store as NULL")
            return False

    prep = dialect.identifier_preparer
    col_list = ", ".join(prep.quote(k) for k in keys)
    conflict_list = ", ".join(prep.quote(c) for c in conflict_cols)
    set_list = ", ".join(f"{prep.quote(c)} = EXCLUDED.{prep.quote(c)}" for c in update_cols)
    head = (f"INSERT INTO {prep.format_table(table)} ({col_list}) VALUES ")
    tail = f" ON CONFLICT ({conflict_list}) DO UPDATE SET {set_list}"

    # The per-column bind processors are the ONLY reason the values land identically.
    # `cell_sources.value` is a `JSON` column, and its processor is what turns a Python
    # dict/str/None into the text PostgreSQL casts to json - without it a bare string
    # value is invalid json and the statement fails outright. Verified by oracle rather
    # than by reading: the same 2,000 mappings (str / int / None / nested dict) written
    # through this path and through `db.execute(stmt, chunk)` produced byte-identical
    # rows on all seven columns, `value::text` included.
    procs = [col.type.dialect_impl(dialect).bind_processor(dialect) for col in cols]

    # `db.execute()` autoflushes; a driver-level statement does not. This keeps the
    # flush at the same point in the sequence for any caller whose Session has it on.
    #
    # ⚠️ THIS IS A NO-OP FOR THIS APPLICATION and that is worth knowing rather than
    # assuming either way: `database.SessionLocal` is `autoflush=False`, so the send
    # this replaces never flushed here either, and a business-key UNIQUE violation goes
    # on surfacing where it always did - at `db.commit()`. Measured both arms with a
    # pending ORM row outstanding: neither flushes it. The line stays because an
    # outside caller with a default `sessionmaker` would otherwise see the two paths
    # disagree, which is exactly the kind of difference nobody would find later.
    if db.autoflush:
        db.flush()

    conn = db.connection()
    if copy:
        import time

        from runtime import request_timing

        statement = f"COPY {prep.format_table(table)} ({col_list}) FROM STDIN"
        dbapi = dialect.loaded_dbapi
        for chunk in _chunks(mappings, chunk_size):            # the chunking stays (QA 11-08: one COPY took all)
            buf = io.StringIO()
            for m in chunk:
                buf.write("\t".join(_copy_field(p(m[k]) if p is not None else m[k]) for k, p in zip(keys, procs)))
                buf.write("\n")
            buf.seek(0)
            started = time.perf_counter()
            try:
                with conn.connection.dbapi_connection.cursor() as cursor:
                    cursor.copy_expert(statement, buf)
            except dbapi.Error as orig:
                raise DBAPIError.instance(statement, None, orig, dbapi.Error, dialect=dialect) from orig
            request_timing.add(time.perf_counter() - started, 1)
        return True
    one_row = "(" + ",".join(["%s"] * len(keys)) + ")"
    row_sql_cache: dict[int, str] = {}
    for chunk in _chunks(mappings, chunk_size):
        n = len(chunk)
        sql = row_sql_cache.get(n)
        if sql is None:
            sql = head + ",".join([one_row] * n) + tail
            row_sql_cache[n] = sql
        flat = []
        for m in chunk:
            for k, p in zip(keys, procs):
                v = m[k]
                flat.append(p(v) if p is not None else v)
        conn.exec_driver_sql(sql, tuple(flat))
    return True


#: What an existing `cell_sources` row takes from the incoming one on conflict.
#
# 🔴 ONE LIST, BECAUSE THERE WERE THREE AND THEY HAD TO AGREE. `bulk_upsert_cell_sources`
# spells its update set three times — once as `update_cols` for the multi-row send and
# twice as `set_={...}` for the two fallbacks — and a column added to two of the three is
# a column that updates or does not depending on which path the batch takes and on nothing
# else. Nothing would raise: the insert would carry the value and the conflicting row would
# quietly keep its old one.
def _copy_field(value) -> str:
    """One value in COPY's text format: NULL is \\N; tab, newline, carriage return and backslash escaped."""
    if value is None:
        return "\\N"
    if isinstance(value, bool):
        return "t" if value else "f"
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    return (str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
            .replace("\r", "\\r"))


CELL_SOURCE_CONFLICT_COLS = ('table_name', 'row_id', 'column_name', 'source_name')
CELL_SOURCE_UPDATE_COLS = ('value', 'updated_by', 'ingested_at', 'origin_row_id', 'owner_rule', 'owner_key')


def owner_cells(source_name) -> dict:
    """`owner_rule` / `owner_key` of a layer named `source_name` - read off its name by the one parser
    (`layer_owner`), so a write and every copy of a layer (a merge, a fold, a pin) say the same owner (owner 11-06
    step 2). None for a layer no rule owns."""
    owner = layer_owner(source_name)
    return {"owner_rule": owner[0] if owner else None, "owner_key": owner[1] if owner else None}


from sqlalchemy import event as sa_event                             # noqa: E402


@sa_event.listens_for(models.CellSource, "before_insert")
@sa_event.listens_for(models.CellSource, "before_update")
def _owner_of_a_layer_row(_mapper, _connection, target):
    """A layer row written through the ORM (`db.add`) says its owner as the bulk upsert does (`owner_cells`)."""
    for column, value in owner_cells(target.source_name).items():
        setattr(target, column, value)


def bulk_upsert_cell_sources(db: Session, mappings: list[dict], chunk_size: int = BULK_CHUNK_SIZE,
                             new_rows=frozenset()):
    """`new_rows` - (table, row_id) of rows THIS transaction inserted (flushed before this call) whose ids hold no
    layers - the caller's prefetch read every id it was handed (`LayersRead`): their layers go by COPY; every other
    layer is upserted as before."""
    if not mappings:
        return
    models.require_owner_columns(db.get_bind())     # added at boot; the insert names them

    # Deduplicate mappings to avoid psycopg2.errors.CardinalityViolation in PostgreSQL.
    # Keep the last (most recent) dictionary for each unique constraint key.
    deduped = {}
    for item in mappings:
        key = (item['table_name'], item['row_id'], item['column_name'], item['source_name'])
        deduped[key] = {**item, **owner_cells(item['source_name'])}

    # Sort deterministically by key to prevent Deadlocks in PostgreSQL.
    sorted_keys = sorted(deduped.keys())
    # 🔴 ONE KEY SET FOR THE WHOLE LIST (총괄 1495534c9). A list where one mapping lacks a key
    #    another has is refused by `.values()` (CompileError) or - when the first one lacks
    #    it - sends NULL for that key in the whole chunk without a word: from 09-16 a merge's
    #    layers lacked `origin_row_id` beside a write's. A key a mapping lacks is None here.
    keys = set().union(*deduped.values())
    deduped_mappings = [{key: deduped[k].get(key) for key in keys} for k in sorted_keys]

    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        from sqlalchemy.dialects.sqlite import insert as upsert_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as upsert_insert

    # Chunked, but still one transaction: nothing is committed here, so the batch
    # remains all-or-nothing exactly as it was when it was a single statement.
    # Chunks are cut from the SORTED list, so the deadlock-avoiding lock ordering
    # is preserved across them.
    #
    # 🔴 THE CHUNKING STAYS AND THE FAST PATH KEEPS IT. `BULK_CHUNK_SIZE` bounds
    # statement text, `mogrify` memory and the rollback unit - NOT a driver parameter
    # limit; that rationale was re-measured and is false for psycopg2, see the
    # constant's own comment. What changes below is HOW those rows are sent, never how
    # many go per call.
    if new_rows and _is_executemany_safe(deduped_mappings):
        fresh_rows = {(m['table_name'], m['row_id']) for m in deduped_mappings} & set(new_rows)
        fresh = [m for m in deduped_mappings if (m['table_name'], m['row_id']) in fresh_rows]
        if fresh and _pg_multirow_upsert(
                db, models.CellSource.__table__, fresh,
                conflict_cols=list(CELL_SOURCE_CONFLICT_COLS),
                update_cols=list(CELL_SOURCE_UPDATE_COLS),
                chunk_size=chunk_size, copy=True):
            deduped_mappings = [m for m in deduped_mappings if (m['table_name'], m['row_id']) not in fresh_rows]
            if not deduped_mappings:
                return
    if _is_executemany_safe(deduped_mappings):
        # [P4] One MULTI-ROW statement per chunk. This used to be
        # `db.execute(stmt, chunk)` with a comment claiming psycopg2 rewrote the
        # executemany into a multi-row INSERT. It does not, and it never did on
        # SQLAlchemy 2.0 - `insertmanyvalues` declines an `ON CONFLICT DO UPDATE` that
        # references `excluded`, leaving `cursor.executemany`, which is a loop of
        # `cursor.execute`. Counted on the isolated `assy_qa`: 20,000 round trips for
        # 20,000 rows, 5.65 s, where 20 statements do it in 1.19 s. See
        # `_pg_multirow_upsert` for the census and why it stays inside SQLAlchemy.
        if _pg_multirow_upsert(
                db, models.CellSource.__table__, deduped_mappings,
                conflict_cols=list(CELL_SOURCE_CONFLICT_COLS),
                update_cols=list(CELL_SOURCE_UPDATE_COLS),
                chunk_size=chunk_size):
            return

        # Declined (SQLite, or a mapping shape it will not guess at): the historical
        # send. Still one compiled statement and one parameter set per row.
        stmt = upsert_insert(models.CellSource)
        stmt = stmt.on_conflict_do_update(
            index_elements=list(CELL_SOURCE_CONFLICT_COLS),
            set_={col: getattr(stmt.excluded, col) for col in CELL_SOURCE_UPDATE_COLS}
        )
        for chunk in _chunks(deduped_mappings, chunk_size):
            db.execute(stmt, chunk)
        return

    for chunk in _chunks(deduped_mappings, chunk_size):
        stmt = upsert_insert(models.CellSource).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=list(CELL_SOURCE_CONFLICT_COLS),
            set_={col: getattr(stmt.excluded, col) for col in CELL_SOURCE_UPDATE_COLS}
        )
        db.execute(stmt)

def bulk_upsert_cell_overwrites(db: Session, mappings: list[dict], chunk_size: int = BULK_CHUNK_SIZE):
    if not mappings:
        return

    # Deduplicate mappings to avoid psycopg2.errors.CardinalityViolation in PostgreSQL.
    # Keep the last (most recent) dictionary for each unique constraint key.
    deduped = {}
    for item in mappings:
        key = (item['table_name'], item['row_id'], item['column_name'])
        deduped[key] = item

    # Sort deterministically by key to prevent Deadlocks in PostgreSQL.
    sorted_keys = sorted(deduped.keys())
    deduped_mappings = [deduped[k] for k in sorted_keys]

    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        from sqlalchemy.dialects.sqlite import insert as upsert_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as upsert_insert

    # Same fast path, same fallback, same chunk size - see `bulk_upsert_cell_sources`.
    # [P4] Identical send-path repair, and it matters here for the same reason: a map
    # push declares `source_name='user'`, so EVERY cell takes an overwrite marker and
    # this list is the same length as the source list.
    if _is_executemany_safe(deduped_mappings):
        if _pg_multirow_upsert(
                db, models.CellOverwrite.__table__, deduped_mappings,
                conflict_cols=['table_name', 'row_id', 'column_name'],
                update_cols=['is_overwrite', 'updated_by', 'updated_at',
                             'manual_priority_source'],
                chunk_size=chunk_size):
            return

        stmt = upsert_insert(models.CellOverwrite)
        stmt = stmt.on_conflict_do_update(
            index_elements=['table_name', 'row_id', 'column_name'],
            set_={
                'is_overwrite': stmt.excluded.is_overwrite,
                'updated_by': stmt.excluded.updated_by,
                'updated_at': stmt.excluded.updated_at,
                'manual_priority_source': stmt.excluded.manual_priority_source
            }
        )
        for chunk in _chunks(deduped_mappings, chunk_size):
            db.execute(stmt, chunk)
        return

    for chunk in _chunks(deduped_mappings, chunk_size):
        stmt = upsert_insert(models.CellOverwrite).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=['table_name', 'row_id', 'column_name'],
            set_={
                'is_overwrite': stmt.excluded.is_overwrite,
                'updated_by': stmt.excluded.updated_by,
                'updated_at': stmt.excluded.updated_at,
                'manual_priority_source': stmt.excluded.manual_priority_source
            }
        )
        db.execute(stmt)

def bulk_delete_cell_sources(db: Session, delete_keys, chunk_size: int = BULK_CHUNK_SIZE):
    """Delete `(table, row_id, column, source_name)` layers - the file-layer fold's write.

    One `row_id IN (...)` per (table, column, source): the planner reads that as one array. A
    thousand keys OR'ed together - as a row-value IN too - spent 436 ms PLANNING each statement
    against 20 ms running it (box, PostgreSQL 18.3)."""
    if not delete_keys:
        return
    groups = {}
    for t_name, r_id, col_name, src_name in delete_keys:
        groups.setdefault((t_name, col_name, src_name), []).append(r_id)
    for (t_name, col_name, src_name), row_ids in sorted(groups.items()):
        for chunk in _chunks(sorted(row_ids), chunk_size):
            db.query(models.CellSource).filter(
                models.CellSource.table_name == t_name,
                models.CellSource.column_name == col_name,
                models.CellSource.source_name == src_name,
                models.CellSource.row_id.in_(chunk)
            ).delete(synchronize_session=False)


def bulk_delete_cell_overwrites(db: Session, delete_keys: list[tuple[str, str, str]], chunk_size: int = BULK_CHUNK_SIZE):
    if not delete_keys:
        return

    from sqlalchemy import and_, or_
    # Sorted for the same reason the upserts above are: a fixed lock order across
    # chunks. Also makes the chunk boundaries deterministic for a given key set.
    keys = sorted(delete_keys)
    for chunk in _chunks(keys, chunk_size):
        conds = [
            and_(
                models.CellOverwrite.table_name == t_name,
                models.CellOverwrite.row_id == r_id,
                models.CellOverwrite.column_name == col_name
            )
            for t_name, r_id, col_name in chunk
        ]
        db.query(models.CellOverwrite).filter(or_(*conds)).delete(synchronize_session=False)

class ProbedIdentity(NamedTuple):
    """Identity values the batch prefetch ASKED about and got NOTHING back for.

    Membership therefore means **this table holds no such row**, established by a
    query that already ran. That proof is what lets `_get_or_create_row` and the
    composite-key collision probe stop issuing one SELECT per row to be told, at
    0.03-0.10 ms of execution and more than that of planning, that a freshly ingested
    row is new. Measured on a 100,000-row map file: 200,000 of the run's 301,222
    statements were those two probes.

    🔴 THIS IS NOT `LayersRead`, and confusing the two is a data-loss bug
    rather than a slow path. That one is the cells that came BACK (rows that exist, and
    whose cell metadata is consequently in the caches). This one is the values that
    came back EMPTY. They are complements, and each is only sound for its own question.

    🔴 IT IS ALSO NOT "the values we asked about". `apply_batch_updates` subtracts the
    rows the prefetch returned before building this; see the comment there for the
    rename-inside-one-batch case that makes the subtraction load-bearing rather than
    tidy.

    ⚠️ ROW IDS AND BUSINESS KEYS ARE SEPARATE SETS ON PURPOSE. The prefetch is
    `row_id IN (ids) OR business_key_val IN (keys)`; a string covered as a business
    key proves nothing about whether some row carries it as a `row_id`. One merged set
    would silently answer the wrong question for any value that appears in both roles.

    ⚠️ ONLY VALID INSIDE THE BATCH'S `no_autoflush` LOOP. Nothing the loop creates is
    flushed, so no row can appear in the table behind the proof; rows the loop creates
    are tracked in `row_cache`, which every consumer probes FIRST. A row resolved by a
    route the prefetch did not cover (a composite key assembled from column values
    that differs from the payload's, a collision-merge conflict row) is simply not in
    these sets and is still queried.
    """
    row_ids: frozenset
    business_keys: frozenset


class ByRow(dict):
    """A batch's pending layers or marks keyed (table, row_id, ...) that also knows each row's keys, in the order they
    came - so a collision merge moves one row's keys without walking the batch (owner 10-24 «소급 3천행에 10분», 총괄
    be730e1e7: every merge walked every pending key, a group cost rows² × columns - 529 rows of 40 columns, 172 s)."""

    def __init__(self):
        super().__init__()
        self.rows = {}

    def __setitem__(self, key, value):
        if key not in self:
            self.rows.setdefault(key[1], {})[key] = None
        super().__setitem__(key, value)

    def __delitem__(self, key):
        super().__delitem__(key)
        _forget_row_key(self.rows, key)

    def pop(self, key, *default):
        if key in self:
            _forget_row_key(self.rows, key)
        return super().pop(key, *default)


class ByRowSet(set):
    """`ByRow` for a batch's pending set of keys (the overwrite marks it deletes)."""

    def __init__(self):
        super().__init__()
        self.rows = {}

    def add(self, key):
        if key not in self:
            self.rows.setdefault(key[1], {})[key] = None
        super().add(key)

    def discard(self, key):
        if key in self:
            _forget_row_key(self.rows, key)
        super().discard(key)


class ByRowLogs(list):
    """`ByRow` for a batch's audit lines: each row's lines, so a merge re-aims one row's lines."""

    def __init__(self):
        super().__init__()
        self.rows = {}

    def append(self, log):
        self.rows.setdefault(log.get("row_id"), []).append(log)
        super().append(log)


def _forget_row_key(rows, key):
    keys = rows.get(key[1])
    if keys is not None:
        keys.pop(key, None)
        if not keys:
            del rows[key[1]]


def row_keys(container, row_id):
    """The keys of `row_id` in a batch's pending container - its own index (`ByRow`), else a walk."""
    rows = getattr(container, "rows", None)
    if rows is not None:
        return list(rows.get(row_id, ()))
    return [key for key in container if key[1] == row_id]


class LayersRead:
    """The cells whose stored layers and overwrites a batch READ up front - so a miss in its caches is proven absent,
    by (row, column) (총괄 10-24): `rows` were read for `columns` only (the columns the batch writes - box board B read
    six columns' 6,000 layers to write one column of 1,000 rows), `whole` holds rows the batch made (none stored in any
    column). A cell outside is not proven and is asked. `_load_metadata_row_cell` is the one reader."""
    __slots__ = ("rows", "columns", "whole")

    def __init__(self, rows, columns):
        self.rows = set(rows)
        self.columns = frozenset(columns)
        self.whole = set()

    def knows(self, row_id, column) -> bool:
        return row_id in self.whole or (row_id in self.rows and column in self.columns)


def _absence_is_proven(value: Any, probed: frozenset) -> bool:
    """True when the batch prefetch asked about `value` and brought no row back."""
    return probed is not None and value in probed


def _engine_minted_row_id(supplied: Any, table_name: str) -> str:
    """The `row_id` a NEW row gets. The engine mints it; a caller may not invent one.

    🔴 ROW IDS ARE THE ENGINE'S, AND THAT IS AN ORDERING CONTRACT (S-66 · 판정 150). uuid7
    is time-ordered, so "later row, later id" holds and anything paging on `row_id` walks
    arrivals in order. A supplied id that is not uuid7 breaks that silently: measured
    2026-09-08, ten hand-written `zzdoe-wp-brk-*` ids in `wafer_process` sort AFTER every
    uuid7 in a varchar column, the ledger cursor came to rest on the largest of them, and
    470,000 later rows were then invisible to the forward scan -- no error, and a cursor
    reporting it had finished.

    ⚠️ THE UPDATE PATH IS UNTOUCHED. Naming an existing row by its id is how every caller
    addresses a row; what is refused is MINTING one. So this guard sits on the branch that
    creates, and `enrichment_candidates` naming a row it is updating never reaches it.

    ⛔ AND IT REFUSES BY NAME rather than quietly minting a replacement. Substituting one
    would leave the caller believing the id it chose is the id that exists.
    """
    if not supplied:
        return str(uuid6.uuid7())
    try:
        version = uuid.UUID(str(supplied)).version
    except (ValueError, AttributeError, TypeError):
        version = None
    if version != 7:
        raise ValueError(
            f"'{table_name}': row_id {supplied!r} was supplied for a NEW row and is not a "
            f"uuid7. Row ids are minted by the engine so that they sort by arrival; a "
            f"hand-written id breaks every reader that pages on row_id. Omit row_id to "
            f"create a row, or name an existing row to update it.")
    return str(supplied)


def _get_or_create_row(db: Session, table_model: Any, update_item: schemas.GeneralUpdateItem, row_cache: dict, table_name: str,
                       probed_identity: "ProbedIdentity" = None) -> tuple[Any, bool]:
    """대상 행 객체를 캐시 또는 DB에서 획득하고, 존재하지 않으면 신규 생성합니다."""
    # 🔴 판정 191. TWO KEYS MAY NAME ONE ROW, AND THE ORDER IS THE RULING.
    # `business_key_val` is the ASSEMBLED identity (188/190). `_supplied_business_key_val`
    # holds what the caller sent when it differs - which is a rename naming the row by its
    # OLD key. Asking the assembled key ALONE mints a duplicate and orphans that row
    # (S-90); asking the supplied key alone is 190 undone. Assembled first means identity
    # still wins wherever both name a row, and the old key is consulted only when the new
    # identity is nobody's.
    bk_candidates = []
    for candidate in (update_item.business_key_val,
                      update_item._supplied_business_key_val):
        if candidate and candidate not in bk_candidates:
            bk_candidates.append(candidate)

    row = None
    if row_cache is not None:
        if update_item.row_id and update_item.row_id in row_cache:
            row = row_cache[update_item.row_id]
        else:
            for candidate in bk_candidates:
                if candidate in row_cache:
                    row = row_cache[candidate]
                    break

    if not row:
        # [P3] Both lookups below are skipped ONLY when the batch's prefetch already
        # asked about this exact value and got nothing. Every other caller passes
        # `probed_identity=None` and keeps today's two queries.
        probed_ids = probed_identity.row_ids if probed_identity else None
        probed_bks = probed_identity.business_keys if probed_identity else None
        if update_item.row_id and not _absence_is_proven(update_item.row_id, probed_ids):
            row = db.query(table_model).filter(table_model.row_id == update_item.row_id).first()
        for candidate in bk_candidates:
            if row:
                break
            # `clean_str_value`: the spelling the prefetch asked and `get_row_by_business_key`
            # compares - a 1.0 asked as '1.0' was «proven absent» beside a row stored as '1'
            if not _absence_is_proven(clean_str_value(candidate), probed_bks):
                row = get_row_by_business_key(db, table_name, candidate)

        if row and row_cache is not None:
            row_cache[row.row_id] = row
            if row.business_key_val:
                row_cache[row.business_key_val] = row
    
    is_new = False
    if not row:
        # [P3] `updated_at` is deliberately NOT set here. The column carries
        # `server_default=func.now()` (models.init_dynamic_models), so an INSERT that
        # omits it stores the same transaction timestamp `func.now()` produced - the
        # value is identical, it is still the DATABASE's clock, and nothing downstream
        # can tell the difference.
        #
        # What changes is that the INSERT no longer carries a SQL EXPRESSION in its
        # parameter set. SQLAlchemy cannot fold rows whose values are expressions into
        # one `insertmanyvalues` batch, so every new row was emitted as its own
        # `INSERT ... RETURNING` statement: 100,000 statements and 49.3 s of client
        # time on a 100,000-row file, while the outbox rows written in the SAME flush -
        # plain values, batchable - cost 8.2 s for the same count.
        row = table_model(
            row_id=_engine_minted_row_id(update_item.row_id, table_name)
        )
        db.add(row)
        is_new = True
        if row_cache is not None:
            row_cache[row.row_id] = row
            if row.business_key_val:
                row_cache[row.business_key_val] = row
            
    return row, is_new

def _find_business_key_conflict(db: Session, table_model: Any, new_bk_val: str, row: Any,
                                row_cache: dict, probed_identity: "ProbedIdentity" = None):
    """The OTHER row already carrying `new_bk_val`, or None.

    [P3] This is the SECOND per-row identity gate, and it is the one nobody had
    listed. It fires for every row of every map file whose payload carries the key
    column empty - the key is then assembled from the row's own values, so it never
    matches the `business_key_val` the row was created with, and this probe runs. At
    100,000 rows that was 100,000 index scans costing 0.032 ms each to execute and
    0.17 ms each to PLAN. Closing only `_get_or_create_row` would have removed one of
    three round trips and left this one standing.

    The skip is taken only when the batch prefetch asked about this exact key and
    NOTHING came back for it - not even this row. Any cache entry at all sends the
    call to the database unchanged, which is deliberately conservative: a table with
    duplicate business keys (there is no unique index on the column) can have a second
    holder that `row_cache` overwrote, and a merge that fails to see it would leave two
    rows where the collision-merge policy says there must be one.
    """
    if row_cache is not None and new_bk_val in row_cache:
        return db.query(table_model).filter(
            table_model.business_key_val == new_bk_val,
            table_model.row_id != row.row_id
        ).first()
    if probed_identity is not None and new_bk_val in probed_identity.business_keys:
        return None
    return db.query(table_model).filter(
        table_model.business_key_val == new_bk_val,
        table_model.row_id != row.row_id
    ).first()


def compose_business_key(table_name: str, values, columns) -> str:
    """These values, joined the way THIS table declares - the one spelling of an identity.

    🔴 THIS IS A DATA-INTEGRITY FUNCTION, NOT A TIDINESS ONE. Four places used to compose
    a composite `business_key_val`, and the day two of them disagreed the same row would
    carry two identities with NOTHING raising: one write matches an existing row, the next
    creates a second, and both look like ordinary rows afterwards.

    🔴 AND IT DELIBERATELY DOES NOT JUDGE BLANKNESS. The four callers do four DIFFERENT
    things when a component is missing - refuse to build a key, fall back to a
    caller-supplied one, produce `None`, and compose the partial key anyway (the last is
    the owner's ruling of 2026-08-05: work with whatever key survived). Those four are not
    an accident to be tidied into one; folding a blank check in here would silently
    reverse that ruling. What is shared is the SPELLING - the separator, the order, and
    `clean_str_value` - and nothing else.

    `values` arrives already ordered by `composite_key_source`, because the material
    differs per caller (a payload, a row, a decision-key map) and unifying THAT would mean
    telling three callers to fetch what they already have. `columns` says which column each
    one is, and each is spelled as that column STORES it (`key_part`) - so a payload's part
    and the same part read back from the row compose one key (총괄 e243d6abf ③).
    """
    separator = TABLE_CONFIG.get(table_name, {}).get("composite_key_separator", "_")
    return separator.join(clean_str_value(key_part(table_name, column, value))
                          for column, value in zip(columns, values))


def key_part(table_name: str, column: str, value):
    """🔴 ONE KEY PART AS ITS COLUMN STORES IT - the one spelling a payload's part and a stored
    row's part share (총괄 e243d6abf ③ · d5cf3a954): the one speller by the declared type
    (`map_overlay.canonical_key_value`, 총괄 88761926b - "1.0" · "01" · 1.0 -> "1", "1.50" ->
    "1.5", a time -> its instant in ISO on the declared zone, 총괄 599fc1988) - the write door passes
    its text and PostgreSQL gives back a datetime, and both spell one key."""
    import map_overlay

    if is_blank_value(value):
        return None
    return map_overlay.canonical_key_value(value, map_overlay.declared_column_type(table_name, column))


def rebuilt_business_key(table_name: str, row) -> Optional[str]:
    """The key this row's own parts compose to, or None when every part is blank (a blank part among filled ones is
    a part, `_unfilled_composite_parts`) - what both seats that rebuild a key ask: the write's
    (`apply_row_update_internal` «2.») and the pin's (`set_cell_manual_priority_batch`) (총괄 a61d32f4f ㄱ).

    🔴 `fold_key_value` / `is_blank_key_part`, because this MAKES an identity: NaN passes `is_blank_value`, becomes
    the text 'nan' through `clean_str_value`, and rows missing different things collide on one key (2026-09-04).
    """
    parts = TABLE_CONFIG.get(table_name, {}).get("composite_key_source") or ()
    values = [fold_key_value(table_name, column, getattr(row, column, None)) for column in parts]
    if not values or every_key_part_blank(values):
        return None
    return compose_business_key(table_name, values, parts)


def put_business_key(table_name: str, row, key) -> tuple:
    """Write a rebuilt key onto the row: `business_key_val` always, the declared `business_key`
    column only on a table that has one - the one seat that asks which of the two shapes this
    is (총괄 a61d32f4f ㄱ). Returns (that column, its old value), or (None, None)."""
    column = TABLE_CONFIG.get(table_name, {}).get("business_key")
    old = getattr(row, column, None) if column else None
    row.business_key_val = key
    if column:
        setattr(row, column, key)
    return column, old


def assemble_composite_business_key(table_name: str, update_item: schemas.GeneralUpdateItem) -> bool:
    """Fill in `business_key_val` from the payload's own column values, for a table
    whose business key is a join of other columns (`composite_key_source`).

    Returns True if it set one. Calling it twice is safe because this is a PURE
    FUNCTION of the payload's own columns - the second call assembles again and lands on
    the same value - which is what lets `apply_batch_updates` call it up front while
    `apply_row_update_internal` keeps calling it for its own protection.

    ⚠️ THAT SAFETY USED TO BE CREDITED TO A GUARD (「an item that already carries a
    row_id OR a business_key_val is left alone」) and the credit was misplaced; 판정 190
    removed the business-key half, because a supplied key switching the assembly off is
    how two payloads with the same composite columns became two rows under one identity.
    Only `row_id` still stops it: a caller naming a row by id is not asking about
    identity. A supplied key is kept instead - see 판정 191 below.

    It always sets the framework-owned `update_item.business_key_val`. When the table
    ALSO declares a physical `business_key` column - one of its `loadable_columns` - it keeps the
    historical second side effect and writes the key back into `updates[key_col]` when absent; a
    `business_key` that names no column gets nothing written (the guide: «물리 칸이 없으면
    business_key_val 에만»), else every row made by its keys counted a drop the table's own
    declaration caused (총괄 10-23). A
    source-owned schema may instead declare only `composite_key_source`; in that form
    no synthetic source column is invented and the assembled identity lives only in
    the framework's `business_key_val` column.

    ⚠️ AND ONE ORDERING CONSTRAINT. Writing `updates[key_col]` is visible to
    `derive_replace_map_scope`, whose LEGACY (undeclared `map_key_columns`) branch
    derives the purge filters from every non-coordinate column present in the first
    payload row - and the business key column is not in its skip list. Running this
    before that resolver would narrow a whole-map purge down to a single die. The
    batch path therefore calls it AFTER the replace_map block, which is exactly where
    it effectively ran before (inside the per-row loop).
    """
    # 🔴 판정 190 A. The supplied key USED TO TURN THIS OFF: `or
    # update_item.business_key_val` meant a caller that sent one skipped assembly
    # entirely, so its row was looked up and stored under a key that is not the
    # table's identity. Two requests with the SAME composite columns under different
    # supplied keys then made TWO rows sharing one assembled identity -- and that is
    # how 1,000 seeded rows hid from three cleanups filtering on the supplied key.
    #
    # ⚠️ IDEMPOTENCE DID NOT LIVE IN THAT GUARD. This is a pure function of the
    # payload's own columns, so calling it twice yields the same value -- the property
    # the docstring credited to the guard is the FUNCTION's. Only `row_id` still stops
    # it: a caller naming a row by id is not asking about identity at all.
    if update_item.row_id:
        return False

    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    composite_src = config.get("composite_key_source")
    if not composite_src or _unfilled_composite_parts(composite_src, update_item.updates):
        return _key_from_the_key_column(table_name, update_item, key_col, composite_src)

    # The blank check above is THIS caller's policy; the join below is everyone's.
    computed_key = compose_business_key(
        table_name, [fold_key_value(table_name, col, update_item.updates.get(col)) for col in composite_src],
        composite_src)

    # 🔴 판정 191. THE SUPPLIED KEY MOVES ASIDE; IT IS NOT DISCARDED. 190 made the
    # assembled key the identity, and the line below overwrites whatever the caller sent.
    # For every caller that sends the key its own columns assemble to that is a no-op.
    # For ONE shape it is not: a rename addresses a row BY ITS OLD KEY and sends the NEW
    # key parts in the same item, so the value being overwritten is the only handle on
    # the row the caller means. Measured 2026-09-09 (S-90): the assembled key named no
    # row, a second row was minted, and the row being renamed was orphaned.
    #
    # ⛔ AND THE ANSWER IS NOT "DO NOT ASSEMBLE WHEN A KEY WAS SENT" - that is 190
    # undone, and it is how 1,000 rows hid from three cleanups. The two live together
    # because they are ORDERED: `_get_or_create_row` asks the assembled key first and
    # reaches this one only when the assembled key names nothing.
    supplied = update_item.business_key_val
    if clean_str_value(supplied) not in ("", computed_key):
        # `clean_str_value`, the spelling a key is stored under and the prefetch asks
        update_item._supplied_business_key_val = clean_str_value(supplied)
    update_item.business_key_val = computed_key
    if key_col in loadable_columns(config) and key_col not in update_item.updates:
        update_item.updates[key_col] = computed_key
    return True


def _key_from_the_key_column(table_name: str, update_item, key_col, composite_src) -> bool:
    """The key of an item whose table does not assemble it from parts here (총괄 5c0a86cec): the key it
    sent, or - only when it sent none - its key column's value. A plain key is spelled as its column
    stores it (`key_part`, the composite parts' spelling - owner 10-14 «접어, 정수변환»): a mapper's
    1.0 and a file's «1.0» on a number key are '1'. The arrived spelling, if it differs, moves aside
    (판정 191), so a row stored under it is found and re-keyed. A key sent beside a different key
    column value wins as it did (총괄: not changed without the owner). A composite key column is
    an assembled text, kept as it came. Without these a key in `updates` only and a 1.0 named no
    row and every write made another."""
    supplied = update_item.business_key_val
    raw = supplied
    if is_blank_key_part(raw) and key_col:
        raw = (update_item.updates or {}).get(key_col)
    if is_blank_key_part(raw):
        return False
    arrived = clean_str_value(raw)
    key = arrived if composite_src or not key_col else compose_business_key(table_name, [raw], [key_col])
    if arrived != key and not update_item._supplied_business_key_val:
        update_item._supplied_business_key_val = arrived
    update_item.business_key_val = key
    return True


#: The one value `null_policy` carries (판정 286 removed `placeholder`; 🔴 owner 10-31 «ㄴ» retired `skip` - declared,
#: it did nothing: no seat asked `key_fold_drops_row`). A blank declared key column of a row read from a FILE is filled
#: with its file's content key (`NokeyPrint`, owner 10-31) - 286 overridden for this value alone (owner 09-30). Anything else is said
#: (`null_policy_unread`) and read as no policy: a blank key is handled at each seat as it is today.
KEY_NULL_NOKEY = "nokey"
#: The columns the write path owns - a value offered for one is not written (`DROP_SYSTEM_COLUMN`), and a nokey
#: print leaves them out.
SYSTEM_COLUMNS = ("created_at", "updated_at", "row_id", "id", "updated_by")


def key_null_policy(table_name: str, column: str):
    """`"nokey"` or None - `null_policy: {<key column>: "nokey"}` beside `column_types` (총괄 4311a51ed). None is
    today's behaviour at every seat."""
    policy = (TABLE_CONFIG.get(table_name) or {}).get("null_policy") or {}
    return KEY_NULL_NOKEY if policy.get(column) == KEY_NULL_NOKEY else None


def null_policy_unread(table_name: str, declaration=None) -> list:
    """The sentence (`validation.unread_said`) naming each `null_policy` entry nothing reads - a value other than
    "nokey" (a retired "skip" too, owner 10-31), or "nokey" on a column that is not a key column - or [] (lead 10-31:
    one seat is asked what of it is unread). `declaration`: the table's entry, its TABLE_CONFIG one when None."""
    import validation

    entry = TABLE_CONFIG.get(table_name) if declaration is None else declaration
    policy = entry.get("null_policy") if isinstance(entry, dict) else None
    if not isinstance(policy, dict):
        return []
    keys = set(entry.get("composite_key_source") or [entry.get("business_key")])
    unread = ["%s: %s" % (column, json.dumps(value, ensure_ascii=False)) for column, value in policy.items()
              if value != KEY_NULL_NOKEY or column not in keys]
    return [validation.unread_said(table_name, "null_policy", unread,
                                   ' Only "nokey" on a key column is read - the rest is read as no null_policy.')
            ] if unread else []


class NokeyPrint:
    """THE nokey keys of one file's rows (owner 10-31 «노키 로직을 파일 내용 해시로» · «같은 파일이 아니어도 정의된 유효
    내용이 같으면 같은 키» · «행 하나 말고 파일로 입력된 전체로») - `nokey_<print, 12 hex>_<number>`, made only from what
    the file put in: each row's declared columns (not the system ones), each value as the write door casts it
    (`cast_value_by_type`, a value it refuses counted blank) and then spelled by the one key speller (`key_part`, lead
    10-31 ㄷ: 1 · 1.0 · 1.00 one number, a time our reader reads one instant), before any nokey fill; a value met again
    in its column takes the spelling remembered (`NOKEY_SPELLED_MAX` distinct at most). A row's time columns are hashed
    apart (owner 10-31 ㄱ, lead ㄴ): its other columns when it is added, its times in `keys`, where the spellings our
    reader leaves as text («2026/10/29») are read by PostgreSQL first - one query, no second read of the file. The rows
    are put in content order; the print is the hash of that order and a row's number its place in it (equal rows,
    numbers in a run). A file's name, times, undeclared columns, column order, header spelling and row order are not
    in it.

    The standard parser's first pass and the watcher's row list (a plugin's) feed the same `add`, so one content
    gives one set of keys by either road. `keys()` answers in the order the rows were added."""

    def __init__(self, table_name: str, table_info: dict):
        self.table = table_name
        self.types = dict((table_info or {}).get("column_types") or {})
        self.columns = sorted(c for c in self.types if c not in SYSTEM_COLUMNS)
        self.by_lower = {}
        for column in loadable_columns(table_info):
            self.by_lower.setdefault(column.lower(), column)
        self.time_columns = [c for c in self.columns if self.types[c] == "datetime"]
        self.digests = []                               # each row's other columns, hashed
        self.row_times = []                             # each row's time spellings, hashed in `keys`
        self.spelled = {}                               # (column, type, value) -> its spelling, this file only
        self.unread = set()                             # the time spellings for PostgreSQL

    def add(self, row) -> None:
        cells = {}
        for name, value in row.items():                 # the watcher's own mapping: case-blind, the last one wins
            column = self.by_lower.get(str(name).lower())
            if column is not None:
                cells[column] = value
        values, times = [], []
        for column in self.columns:
            raw = cells.get(column)
            memo = (column, type(raw), raw)             # type: 1 · 1.0 · True are one dict key
            try:
                spelled = self.spelled.get(memo, _NOT_SPELLED)
            except TypeError:                           # a value that cannot be a key (a plugin's list)
                memo = spelled = _NOT_SPELLED
            if spelled is _NOT_SPELLED:
                try:
                    value = cast_value_by_type(raw, self.types[column], column, self.table)
                except CellRefused:
                    value = None
                asked = time_text_to_ask(self.table, column, self.types[column], value)
                if asked is not None:
                    self.unread.add(asked)
                spelled = key_part(self.table, column, value)
                if memo is not _NOT_SPELLED and len(self.spelled) < NOKEY_SPELLED_MAX:
                    self.spelled[memo] = spelled
            (times if self.types[column] == "datetime" else values).append(spelled)
        self.digests.append(hashlib.blake2b(json.dumps(values, default=str, ensure_ascii=False).encode("utf-8"),
                                            digest_size=16).digest())
        if self.time_columns:
            self.row_times.append(times)

    def keys(self, db=None) -> list:
        """`db`: PostgreSQL reads the time spellings our reader left as text (`times_postgresql_reads`, owner 10-31 ㄱ),
        each spelled as `key_part` spells its moment. Without a database, or a spelling it refuses, the text stays."""
        digests = self.digests
        if self.time_columns:
            readings = times_postgresql_reads(db, self.unread)[0] if self.unread and db is not None else {}
            read = {spelling: key_part(self.table, self.time_columns[0], moment)   # any time column: one speller
                    for spelling, moment in readings.items()}
            digests = [hashlib.blake2b(digest + json.dumps([read.get(t, t) for t in times], default=str,
                                                           ensure_ascii=False).encode("utf-8"), digest_size=16).digest()
                       for digest, times in zip(self.digests, self.row_times)]
        order = sorted(range(len(digests)), key=lambda at: (digests[at], at))
        print_ = hashlib.blake2b(b"".join(digests[at] for at in order),
                                 digest_size=NOKEY_PRINT_HEX // 2).hexdigest()
        keys = [None] * len(order)
        for number, at in enumerate(order, start=1):
            keys[at] = "nokey_%s_%d" % (print_, number)
        return keys


#: The print part of a nokey key, hex characters (owner 10-31).
NOKEY_PRINT_HEX = 12
#: How many distinct values one print remembers the spelling of (lead 10-31: a coordinate log repeats its values; past
#: this a value is spelled each time, so a file of all-different values stays bounded).
NOKEY_SPELLED_MAX = 200_000
_NOT_SPELLED = object()


def nokey_print(table_name: str, table_info: dict):
    """A `NokeyPrint` for a table with a key column declared `nokey`, None for any other - its reads are as before."""
    info = table_info or {}
    columns = [c for c in (info.get("composite_key_source") or [info.get("business_key")]) if c]
    policy = info.get("null_policy") if isinstance(info.get("null_policy"), dict) else {}
    return NokeyPrint(table_name, info) if any(policy.get(c) == KEY_NULL_NOKEY for c in columns) else None


def fill_nokey_keys(table_name: str, batch) -> None:
    """Fill each item's blank key columns declared `nokey` with its file row's key (`NokeyPrint`, carried on the batch
    as `_nokey_keys`, one per file row) - the one seat, ahead of the key assembly (총괄 4311a51ed). An item with an
    identity of its own, or not read from a file, is not touched. Writes `batch._nokey`: {"rows": n, "columns":
    {col: n}}."""
    config = TABLE_CONFIG.get(table_name) or {}
    key_col = config.get("business_key")
    columns = [c for c in (config.get("composite_key_source") or [key_col]) if c]
    nokey_columns = [c for c in columns if key_null_policy(table_name, c) == KEY_NULL_NOKEY]
    keys = getattr(batch, "_nokey_keys", None)
    if not nokey_columns or keys is None:
        return
    counts = {"rows": 0, "columns": {}}
    for item in batch.updates:
        if item._file_row is None or item.row_id:
            continue
        filled = False
        for column in nokey_columns:
            if not is_blank_key_part(item.updates.get(column)):
                continue
            if column == key_col and not is_blank_key_part(item.business_key_val):
                continue
            item.updates[column] = keys[item._file_row - 1]
            if column == key_col:
                item.business_key_val = item.updates[column]
            counts["columns"][column] = counts["columns"].get(column, 0) + 1
            filled = True
        counts["rows"] += filled
    batch._nokey = counts


def fold_key_value(table_name: str, column: str, value):
    """🔴 THE ONE FOLD FOR A KEY VALUE (S-181, 판정 284·285·287).

    Null was ONE AXIS being judged separately at seven seats, and the seats disagreed —
    measured: the composite-key render folds `None`, `''` and `'  '` together; the join's
    `==` never matches NULL against NULL; `canonical_key_value` keeps `None` but returns
    `''` for `''`; the ledger treats `''` as a value; and PostgreSQL's plain unique index
    calls two NULLs distinct while calling `''` a value. Same input, five answers.

    🔴 IT INVENTS NO PREDICATE. Blankness already has one name at the write door —
    `is_blank_value`, pinned by `contracts/blank_predicate`, with a SQL twin in
    `blank_sql_condition` — and 판정 284 is exactly that predicate's rule (strip, then
    length zero). This calls `is_blank_key_part`, which IS that predicate plus the one
    identity-path addition it already carries: a non-finite float is not an identity
    (measured 2026-09-04, `compose_business_key("t", ["A", nan, "C"])` -> `"A_nan_C"`).
    Using the narrower one here would let `nan` back in as a key.

    ⚠️ THE SQL SIDE IS `coalesce(<col>, '')` AND DELIBERATELY DOES NOT TRIM, for the reason
    `blank_sql_condition` states: storage is canonical (`normalize_stored_text`), so a
    whitespace-only value never reaches the database, and a `btrim` here would be an
    incomplete imitation of `str.strip()` that the next schema change invalidates.
    `chain.join_key_index.index_key_expression` is where that spelling lives (S-283 moved it
    out of `virtual_join` before that package was deleted), so the DDL and the query
    expression cannot drift — a mismatch there does not fail, it silently stops using the
    index.
    """
    return None if is_blank_key_part(value) else value


def is_blank_key_part(value) -> bool:
    """A key part that names nothing - `is_blank_value(identity=True)`: blank, and a float not finite or from
    KEY_EXACT_LIMIT up (it cannot tell neighbouring whole numbers apart, and PostgreSQL and Python spell some of them
    differently: 1e23 '9.999999999999999e+22' / '1e+23', lead 10-31). A NaN key part composed «A_nan_C», one identity
    for unrelated rows (measured 2026-09-04)."""
    return is_blank_value(value, identity=True)


#: The float magnitude from which a key part is blank (`is_blank_key_part`) - written into `notation_norm.KEY_NUMBER_SQL`
KEY_EXACT_LIMIT = 2 ** 53


def every_key_part_blank(key) -> bool:
    """A key whose EVERY part is blank is no key (owner 10-20 «키가 전부 빈 행은 유일성에서 뺀다», 총괄 534f375f8): the
    join matches nothing on it, and the join's unique index and the write gate leave its row out. One blank part among
    filled ones is still a key (blank equals blank, S-181). The SQL twin is `join_key_index.blank_key_slot_expression`."""
    return all(is_blank_key_part(part) for part in key)


def _unfilled_composite_parts(composite_src, updates) -> list:
    """Which `composite_key_source` columns this payload does not supply a value for.

    Extracted so that the assembler above and `unfilled_key_columns` below cannot drift
    apart: one asks "may I build a key?" and the other asks "will a key be buildable?",
    and those must be THE SAME QUESTION or a gate would refuse rows the writer would have
    keyed (or, worse, pass rows it will not).

    Blankness is `is_blank_key_part` (`is_blank_value` plus a non-finite float).

    🔴 A BLANK PART AMONG FILLED ONES IS A PART (소유자 10-24 «a,빈값 a,빈값 같은거로 처리하라고 지금 키충돌나면
    접잖아», 총괄 242f4a43a): it composes as blank, so (a, blank) twice is one key - folded by the door a key
    collision folds by, as the join, its unique index, the write gate and decide already read it. A part the payload
    does not carry, or EVERY part blank (`every_key_part_blank`), is still no key.
    """
    updates = updates or {}
    unfilled = [col for col in composite_src if col not in updates or is_blank_key_part(updates.get(col))]
    keyless = len(unfilled) == len(composite_src) or any(col not in updates for col in composite_src)
    return unfilled if keyless else []


def unfilled_key_columns(table_name: str, update_item) -> list:
    """The declared key columns `update_item` leaves empty, or `[]` when it carries one.

    🔴 READ-ONLY. It must never call `assemble_composite_business_key`, whose two side
    effects include writing the key back into `updates[key_col]` - and doing that before
    `derive_replace_map_scope` runs would narrow a whole-map purge down to a single die
    (see that function's ordering constraint). This answers the question without moving
    anything, so it is safe to ask at any point before the write.

    An EMPTY list means "accept", and it is returned for three different reasons that all
    have to mean accept:

      * the item names a `row_id` or carries a `business_key_val` - it already has an
        identity and the writer will resolve onto it;
      * the table declares neither a plain `business_key` nor a
        `composite_key_source` - nothing to judge, so judging it would be inventing a
        policy;
      * the table declares a business key column and the payload supplies it with a
        value - the assembler keys the item by it (`_key_from_the_key_column`).

    A NON-EMPTY list names the columns, so a refusal can say WHICH column was blank
    instead of "some key is missing".
    """
    # Truthiness, deliberately, on both - it is what `_get_or_create_row` uses to decide
    # whether to look a row up, so a value it would ignore must not read as an identity
    # here either.
    if update_item.row_id:
        return []
    if (update_item.business_key_val
            and not is_blank_key_part(update_item.business_key_val)):
        return []

    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    composite_src = config.get("composite_key_source")
    declared = isinstance(key_col, str) and bool(key_col.strip())

    if composite_src:
        # A physical business-key column is optional here: the assembler can keep the
        # joined identity in the framework-owned `business_key_val` without adding a
        # synthetic column to a source-owned schema. Its value keys the item when parts
        # are missing (`_key_from_the_key_column`).
        unfilled = _unfilled_composite_parts(composite_src, update_item.updates)
        if unfilled and declared and not is_blank_key_part((update_item.updates or {}).get(key_col)):
            return []
        return unfilled

    if declared:
        updates = update_item.updates or {}
        if key_col in updates and not is_blank_key_part(updates.get(key_col)):
            return []
        return [key_col]

    return []


def _update_row_business_key(row: Any, key_col: str, update_item: schemas.GeneralUpdateItem, row_cache: dict,
                             table_name: str = None):
    """비즈니스 키가 업데이트 항목에 있거나 기존 행에 존재하면 DYNAMIC 테이블의 business_key_val 필드를 최신화합니다.

    🔴 A BLANK KEY COLUMN NEVER PRODUCES `''`. A new row is left with the **NULL** it
    was created with. The two spellings are not interchangeable and the difference is
    the whole reason this branch exists.

    `''` is a VALUE, so every keyless row in a table carries the SAME identity. With
    the UNIQUE index from `migrations/add_business_key_unique_index.py` in place, five
    such rows in one batch collide WITH EACH OTHER - and `apply_batch_updates`'
    `IntegrityError` recovery cannot fix that, because its recovery is "roll back,
    re-read the database, resolve onto the row the winner committed" and none of the
    colliding rows was ever committed. The replay reproduces the same collision and
    after `BK_CONFLICT_MAX_RETRIES` the batch is REFUSED. Measured on this workstation
    against real PostgreSQL with the index installed, three pushes of a 5-row payload
    whose key column arrived blank: **0 rows written each time**, not five duplicates.
    One source file with a blank key column would stop that table's ingestion outright.

    NULL is PostgreSQL's "unknown" and a plain UNIQUE index treats NULLs as distinct,
    so any number of rows may hold it. That is also the shape a keyless row already
    has everywhere else - `create_empty_rows_batch` writes it, the grid addresses such
    rows by `row_id`, and the live database carries them today (measured 2026-08-07:
    11 in `wafer_map_metadata`, 10 in `production_plan`, all from manual merges).

    🔴 A BLANK VALUE WRITES NOTHING AT ALL - it does not clear an existing key either. That is the KEY
    COLUMN's own value arriving blank (818c9c0); a blanked composite key PART is another write - the
    rebuild below clears the key then (a61d32f4f: 「이 행의 키는 이제 없다」, 총괄 10-14 kept it).
    A new row therefore keeps its NULL, and a row that already has a key keeps it. The
    first draft of this cleared to NULL on blank, which is what the old `''` write
    effectively did too, and it was WRONG for the reason the old code never had to
    face because its own bug hid it:

      A map CSV carries its key column PRESENT AND BLANK, and that column is DERIVED -
      `map_pk` is assembled from `map_id`+`die_no`. Blank there means "the file did not
      supply it", not "this row has no key". On a re-push of an unchanged map the
      composite recomputation below is skipped (`is_src_changed` is False and the row
      is not new), so nothing puts the key back. Measured against real PostgreSQL: the
      second push of an unchanged 4-row map left all four rows with NULL keys, and the
      third push then created four MORE rows. The old `''` code produced the same
      destruction but collided on the way out, so the batch was refused and the damage
      was never committed - a bug masking a bug.

    Blanking a displayed key cell therefore leaves `business_key_val` stale rather than
    destroying it. That is the deliberate trade: a stale-but-unique handle is
    recoverable by typing a new key, whereas dropping the identity of a live row
    orphans everything keyed to it (`FrameConfirmation.unit_key`, and the ledger's
    subject keys; `GraphNode.identity_key` was a third until 2026-08-18)
    and `''` additionally collides. Re-keying happens through the routes that KNOW a new
    key - a non-blank value here, or the composite reassembly below.
    """
    def _apply(raw):
        if raw is None:
            return
        # THE SAME SPELLING the item's key was assembled with (`compose_business_key` - the
        # key column's type, 총괄 88761926b): a row named by id whose key column says '1.50'
        # is keyed '1.5', as the next write by key asks. A second spelling stores the row
        # under a key nothing looks it up by - without colliding on `uq_bk_`.
        str_val = compose_business_key(table_name, [raw], [key_col])
        if str_val == "":
            # Blank -> write nothing. Never `''` (a shared identity that collides), and
            # never a clear (it destroys a map row's key on re-push). See the docstring.
            return
        if row.business_key_val != str_val:
            row.business_key_val = str_val
            if row_cache is not None:
                row_cache[str_val] = row

    if update_item.business_key_val:
        # 🔴 THE ITEM'S OWN KEY WINS, WHETHER OR NOT THE TABLE HAS A KEY COLUMN. It is
        # what the row was LOOKED UP by - `_get_or_create_row` and the batch prefetch
        # both filter on `business_key_val` - so storing anything else means the row is
        # found by one string and saved under another.
        #
        # This branch used to be guarded on `not key_col`, i.e. it only ran for
        # source-exact composite schemas with no physical key column. A plain-keyed
        # table has one, so it fell to the branch below and re-derived the identity from
        # the payload instead of keeping the one it had just resolved on.
        _apply(update_item.business_key_val)
    elif key_col and key_col in update_item.updates:
        _apply(update_item.updates[key_col])
    elif key_col and hasattr(row, key_col):
        existing_val = getattr(row, key_col)
        _apply(existing_val.get("value") if isinstance(existing_val, dict) else existing_val)

def _load_metadata_row_cell(db: Session, table_name: str, row_id: str, col_name: str, is_new: bool, sources_cache: dict, overwrites_cache: dict, cell_sources_to_upsert: dict, cell_overwrites_to_upsert: dict, layers_read: "LayersRead" = None) -> tuple[list, Any]:
    """해당 셀의 CellSource 리스트와 CellOverwrite 객체를 캐시 혹은 DB로부터 획득합니다.

    layers_read: the cells `apply_batch_updates` loaded metadata for up front (`LayersRead`).
    """
    key = (row_id, col_name)

    # [P2] A cache miss means "this cell has no stored metadata" - but ONLY for a CELL
    # the batch read. The prefetch selects the cell_sources/cell_overwrites rows of its
    # rows in the columns the batch writes (총괄 10-24 - every column, before), so for
    # those cells "not in the cache" and "not in the table" are the same statement, and
    # a column being written for the first time costs no SELECT to be told it is empty.
    # Another column of the same row was not read: it is asked (a collision merge reads
    # every column, and primes them first - `prime_merge_cells`).
    #
    # 🔴 THE PREDICATE IS MEMBERSHIP IN THE CELLS READ, NOT "the row exists".
    # Substituting the latter is a data-loss bug, not an optimisation: a row can be
    # resolved AFTER the prefetch filter was built - `apply_row_update_internal`
    # assembles a composite business key out of column values and looks the row up, and
    # a collision merge switches onto a conflict row found the same way. Those rows
    # exist and were never read, so claiming they have no sources would drop their
    # stored `user` layer out of the priority computation and delete the overwrite
    # marker with it. Unknown cells must still be queried; that is what `is not None and
    # knows(...)` buys, and why every caller outside the batch path passes None.
    # a row made on an id the batch read (an orphan's layers, QA 11-08) is answered by that read, as any read row
    absence_is_known = ((is_new and (layers_read is None or row_id not in layers_read.rows))
                        or (layers_read is not None and layers_read.knows(row_id, col_name)))

    # CellSource 로드
    #
    # [ORDER BY source_name] These two SELECTs feed `compute_priority_value`, and an
    # unordered SELECT returns rows in whatever order the heap and the plan happen to
    # produce. That order used to BE the tiebreak (see `compute_priority_value` for the
    # measurement), so a resolution built on it could change after a VACUUM FULL or a
    # plan flip with nothing written. The resolver now imposes its own total order and
    # no longer depends on this, but a SELECT that feeds a decision states its order:
    # `source_name` is UNIQUE per cell (`idx_sources_lookup_source`), so it is a total
    # order, it is identical on PostgreSQL and SQLite, and it has no NULL-ordering
    # dialect difference the way `ingested_at` would.
    if sources_cache is not None:
        if key not in sources_cache:
            if absence_is_known:
                col_srcs = []
            else:
                col_srcs = db.query(models.CellSource).filter(
                    models.CellSource.table_name == table_name,
                    models.CellSource.row_id == row_id,
                    models.CellSource.column_name == col_name
                ).order_by(models.CellSource.source_name.asc()).all()
                if cell_sources_to_upsert is not None:
                    for s in col_srcs:
                        db.expunge(s)
            sources_cache[key] = col_srcs
        else:
            col_srcs = sources_cache[key]
    else:
        if absence_is_known:
            col_srcs = []
        else:
            col_srcs = db.query(models.CellSource).filter(
                models.CellSource.table_name == table_name,
                models.CellSource.row_id == row_id,
                models.CellSource.column_name == col_name
            ).order_by(models.CellSource.source_name.asc()).all()
            if cell_sources_to_upsert is not None:
                for s in col_srcs:
                    db.expunge(s)

    # CellOverwrite 로드
    if overwrites_cache is not None:
        if key not in overwrites_cache:
            if absence_is_known:
                ow = None
            else:
                ow = db.query(models.CellOverwrite).filter(
                    models.CellOverwrite.table_name == table_name,
                    models.CellOverwrite.row_id == row_id,
                    models.CellOverwrite.column_name == col_name
                ).first()
                if ow and cell_overwrites_to_upsert is not None:
                    db.expunge(ow)
            overwrites_cache[key] = ow
        else:
            ow = overwrites_cache[key]
    else:
        if absence_is_known:
            ow = None
        else:
            ow = db.query(models.CellOverwrite).filter(
                models.CellOverwrite.table_name == table_name,
                models.CellOverwrite.row_id == row_id,
                models.CellOverwrite.column_name == col_name
            ).first()
            if ow and cell_overwrites_to_upsert is not None:
                db.expunge(ow)
            
    return col_srcs, ow

def array_params(db, columns, rows):
    """`(params, casts)` - one PostgreSQL array per column, each value through its column's bind processor."""
    dialect = db.get_bind().dialect
    params, casts = {}, []
    for i, (column, values) in enumerate(zip(columns, zip(*rows))):
        bind = column.type.bind_processor(dialect)
        params["a%d" % i] = [bind(value) if bind else value for value in values]
        casts.append("CAST(:a%d AS %s[])" % (i, column.type.compile(dialect=dialect)))
    return params, casts


def update_by_arrays(db, table, names, rows, batch_now, key="row_id"):
    """`rows` [[key, a value per name but updated_at]] into `table` in one statement - updated_at, when
    named, is the batch's instant as the door stamps it (`batch_write_instant`, else now()). -> the result
    (its `rowcount`). The one array writer: the notation fold, the unit mark and the flush's changed rows
    (`database.write_changed_rows_by_shape`, 총괄 8af4d378c) call it."""
    from sqlalchemy import text

    valued = [name for name in names if name != "updated_at"]
    columns = [table.c[key]] + [table.c[name] for name in valued]
    params, casts = array_params(db, columns, rows)
    sets = ['"%s" = v.a%d' % (name, i) for i, name in enumerate(valued, start=1)]
    if "updated_at" in names:
        sets.append('"updated_at" = %s' % ("now()" if batch_now is None else ":updated_at"))
        params["updated_at"] = batch_now
    # the key's own `= ANY(keys)` bounds the table side to the page by its key index: without it a
    # 1M-row table was hash-joined by a scan of the whole table, every page (box dt_map, 총괄 10-11)
    return db.execute(text('UPDATE "%s" SET %s FROM unnest(%s) AS v(%s) WHERE "%s"."%s" = v.a0 AND "%s"."%s" = ANY(%s)'
                           % (table.name, ", ".join(sets), ", ".join(casts),
                              ", ".join("a%d" % i for i in range(len(columns))),
                              table.name, key, table.name, key, casts[0])), params)


def batch_write_instant(db):
    """ONE timestamp for a whole request, read from the DATABASE. `None` if it cannot be.

    🔴 S-83 ③. This exists so the row UPDATE can carry a VALUE rather than a SQL expression:
    an expression in the SET clause takes the write off its batched path, which is what made
    a 1,000-row request send 1,000 UPDATE statements. See `apply_row_update_internal`.

    ⚠️ ONE INSTANT PER REQUEST IS THE POINT, not merely a saving. On PostgreSQL `now()` is
    the TRANSACTION timestamp, so the per-row expression already gave every row of a batch
    the same value; reading it once reproduces that exactly rather than approximating it.

    Falls back to `None` - the caller then keeps the expression - rather than reaching for
    the app server's clock, which would be a SECOND clock source on a column whose INSERT
    path takes the database's through `server_default`.
    """
    from sqlalchemy import select
    from sqlalchemy.sql import func

    try:
        # ⛔ NO AUTOFLUSH. This is a read taken for its VALUE, and a session query flushes
        # pending work first by default -- so asking the time would push half-built rows at
        # the database ahead of the batch that is still assembling them.
        with db.no_autoflush:
            return db.scalar(select(func.now()))
    except Exception:  # pragma: no cover - a session that cannot answer keeps today's path
        return None


def _merge_into_key_holder(db, table_name, table_model, row_to_delete, row, *, explicit,
                           human_columns, source_name, updated_by, transaction_id, changed_cols,
                           overwrites_cache=None, sources_cache=None, layers_read=None,
                           cell_sources_to_upsert=None, cell_overwrites_to_upsert=None,
                           cell_overwrites_to_delete=None, logs_to_cache=None,
                           deleted_row_ids=None, row_cache=None, deleted_edits=None):
    """[대안 B: Silent Merge & Overwrite] A row whose rebuilt key another row already holds: its
    values, layers and pending caches move onto that row (`row`) and the shell (`row_to_delete`)
    is deleted. The ONE merge body (총괄 6e041f4cb ①) - the write seat (a key part written) and the
    pin seat (a pin that moves a key part's shown value) both call it; the caller swaps the rows.

    `explicit` is what the caller wrote this time, column -> value: those columns are «directly
    edited» (a human value on the key's holder does not protect them) and their value wins.
    `human_columns` are the columns this write counts as a PERSON's - only those it wrote: the
    write seat's item, when a person wrote it, in the columns it carries; a pin, only the pinned
    cells (a pin is a person choosing which layer a cell shows, not a person's value). Every other
    cell is read by the writer of its layer, so the key holder's own human value stays (총괄
    6e041f4cb ① 답 · the write seat counted EVERY column of a person's item, which let a write of
    a key part alone overwrite the holder's human values with the shell's machine ones). `source_name` / `updated_by` name the writer on the fallback
    layer and the merge's audit lines.
    """
    key_col = TABLE_CONFIG.get(table_name, {}).get("business_key")
    column_types = TABLE_CONFIG.get(table_name, {}).get("column_types") or {}
    # 3. 임시 행(row_to_delete)에 채워진 모든 실제 값을 충돌 행(row)에 덮어쓰기 병합
    columns_to_merge = [c.name for c in table_model.__table__.columns]
    # [P-4] 두 행의 덮어쓰기를 «한 번에» 읽는다. 종전에는 컬럼마다 두 번씩
    # 물었고 그 대다수가 「덮어쓰기가 «없는» 컬럼」이었다 — 없는 것을 확인하려고
    # 컬럼 수만큼 왕복했다. `overwrites_cache` 가 None 인 호출자를 위해 지역
    # dict 로 떨어지므로 «판정은 한 글자도 바뀌지 않는다».
    merge_ow = overwrites_cache if overwrites_cache is not None else {}
    prime_merge_cells(db, table_name, merge_ow, sources_cache if cell_sources_to_upsert is not None else None,
                      [row.row_id, row_to_delete.row_id], columns_to_merge)
    for col_name in columns_to_merge:
        if col_name in [key_col, "row_id", "business_key_val", "created_at", "updated_at"]:
            continue

        is_explicitly_edited = (col_name in explicit)

        # [병합 보호 정책] 충돌 행(row)에 이미 사용자 수정(user)이나 핀이 들어있고, 이번에 직접 수정하는 셀이 아니면 기존 값 보존
        old_ow = merge_ow.get((row.row_id, col_name))

        is_old_user_overwritten = False
        if old_ow:
            # collision_merge인 경우는 단순 병합 충돌 메타이므로 보호 가드 대상에서 제외
            if old_ow.updated_by != "collision_merge" and old_ow.manual_priority_source != "collision_merge":
                is_old_user_overwritten = old_ow.is_overwrite or (old_ow.manual_priority_source is not None)

        # 새 값이 사용자 입력값인지 판단
        is_new_user_overwritten = col_name in human_columns
        new_ow = merge_ow.get((row_to_delete.row_id, col_name))
        if new_ow:
            if new_ow.updated_by != "collision_merge" and new_ow.manual_priority_source != "collision_merge":
                is_new_user_overwritten = is_new_user_overwritten or new_ow.is_overwrite or (new_ow.manual_priority_source is not None)

        if is_old_user_overwritten and is_new_user_overwritten:
            # User vs User collision: apply the newly overwritten value
            is_value_protected = False
        else:
            is_value_protected = is_old_user_overwritten and not is_explicitly_edited

        new_val = none_if_blank(getattr(row_to_delete, col_name, None))

        # explicit에도 명시적으로 새로 기입된 값이 있으면 그 값을 우선적으로 선정
        if col_name in explicit:
            # cast as every write casts (총괄 88761926b: a float 1.0 into a text column was stored '1.0')
            try:
                new_val = cast_value_by_type(explicit[col_name], column_types.get(col_name, "string"),
                                             col_name, table_name)
            except CellRefused as refused:
                # the edit's value is dropped as before - said, since the merged row's value is kept instead
                logger.warning("[Merge] %s row %s column %s: the edited value was refused (%s) - the merged row's "
                               "value %r is kept", table_name, row.row_id, col_name, refused, new_val)

        old_val = getattr(row, col_name, None)

        has_cell_changed = new_val is not None and values_differ(
            old_val, new_val,
            column_types.get(col_name, "string"))

        if has_cell_changed and not is_value_protected:
            setattr(row, col_name, new_val)
            if col_name not in changed_cols:
                changed_cols.append(col_name)

            # 중복키 충돌 병합이 발생했음을 가벼운 Overwrite 테이블에도 기록하여 그리드 성능 최적화 지원
            if cell_overwrites_to_upsert is not None:
                # [P3] A real datetime, not `func.now()`. Every other
                # producer of these dicts already writes
                # `datetime.now()` (see the source/overwrite blocks
                # above), and a SQL expression in ONE mapping forces
                # the whole bulk upsert off its batched path -
                # `_is_executemany_safe` refuses a `ClauseElement`.
                ow_key = (table_name, row.row_id, col_name)
                cell_overwrites_to_upsert[ow_key] = {
                    "table_name": table_name,
                    "row_id": row.row_id,
                    "column_name": col_name,
                    "is_overwrite": True,
                    "updated_by": "collision_merge",
                    "updated_at": datetime.now(),
                    "manual_priority_source": "collision_merge"
                }
                if cell_overwrites_to_delete is not None:
                    cell_overwrites_to_delete.discard(ow_key)

            # AuditLog 기록
            # 🔴 THE RETURN IS KEPT, AND THAT IS THE WHOLE FIX. This
            # was the ONE call of ten that dropped it. When
            # `logs_to_cache` is a list, `add_to_cache` is False and
            # `create_audit_log` skips `db.add` as well as the cache
            # (its own docstring says so) - so a discarded return meant
            # the row reached NEITHER. The sole live caller of this
            # function always passes a list, so this merge's history
            # was not sometimes lost, it was always lost.
            # The sibling collision_merge site does exactly this.
            log_dict = create_audit_log(
                db, table_name, row.row_id, col_name, old_val, new_val,
                "collision_merge", (updated_by or "system"),
                transaction_id=transaction_id, business_key=row.business_key_val,
                add_to_cache=(logs_to_cache is None)
            )
            if logs_to_cache is not None and log_dict is not None:
                logs_to_cache.append(log_dict)

        # [소스 이력 적재] 값 덮어쓰기 보호 여부와 상관없이, 껍데기 행이 가졌던 오리지널 소스 목록은 무조건 적재(Append)
        if cell_sources_to_upsert is not None:
            # 껍데기 행이 원래 가졌던 소스 명칭 추적 계승
            old_srcs, _ = _load_metadata_row_cell(
                db, table_name, row_to_delete.row_id, col_name,
                is_new=False,
                sources_cache=sources_cache,
                overwrites_cache=overwrites_cache,
                cell_sources_to_upsert=cell_sources_to_upsert,
                cell_overwrites_to_upsert=cell_overwrites_to_upsert,
                layers_read=layers_read
            )

            # 대상 행(row)에 이미 등록되어 있거나 upsert 대기 중인 소스명 목록 추출
            # [P2] `row` here is the CONFLICT row this merge switched onto,
            # found by business key inside this loop. It is routinely absent
            # from the cells read, and the membership test below is what
            # keeps it being read instead of assumed empty.
            target_srcs, _ = _load_metadata_row_cell(
                db, table_name, row.row_id, col_name,
                is_new=False,
                sources_cache=sources_cache,
                overwrites_cache=overwrites_cache,
                cell_sources_to_upsert=cell_sources_to_upsert,
                cell_overwrites_to_upsert=cell_overwrites_to_upsert,
                layers_read=layers_read
            )
            existing_names = {s.source_name for s in target_srcs} if target_srcs else set()
            for (t, _r, c, s_name) in row_keys(cell_sources_to_upsert or {}, row.row_id):
                if t == table_name and c == col_name:
                    existing_names.add(s_name)

            # user 간 충돌 시 기존의 standard "user" 값을 "user (old_exist_xyz)"로 백업하여 원천에 기존 user값을 보존
            if is_old_user_overwritten and is_new_user_overwritten:
                old_user_src = next((s for s in target_srcs if s.source_name == "user"), None) if target_srcs else None
                pending_user_key = (table_name, row.row_id, col_name, "user")
                pending_user_data = cell_sources_to_upsert.get(pending_user_key) if cell_sources_to_upsert else None

                old_val_to_backup = pending_user_data["value"] if pending_user_data else (old_user_src.value if old_user_src else None)
                old_by_to_backup = pending_user_data["updated_by"] if pending_user_data else (old_user_src.updated_by if old_user_src else "system")

                if old_val_to_backup is not None:
                    backup_src_name = merged_layer_name(USER_SOURCE, f"old_exist_{row.row_id[:6]}")
                    backup_key = (table_name, row.row_id, col_name, backup_src_name)
                    cell_sources_to_upsert[backup_key] = {
                        "table_name": table_name,
                        "row_id": row.row_id,
                        "column_name": col_name,
                        "source_name": backup_src_name,
                        "value": clean_str_value(old_val_to_backup),
                        "updated_by": old_by_to_backup,
                        # A person's value read from no row (총괄 1495534c9).
                        "origin_row_id": None,
                        # [P3] see the collision-merge overwrite dict
                        # above: a real datetime keeps the bulk upsert
                        # on its batched path.
                        "ingested_at": layer_instant()
                    }

            src_list = []
            if old_srcs:
                # Stamped below one by one in the shell's own delivery order - oldest first,
                # equal times by name descending - so the copy of the value the shell showed
                # is the newest and wins among the copies (총괄 9280922aa).
                def delivered(layer):
                    at = resolution_ingested_at({"ingested_at": layer.ingested_at})
                    return (at is not None, at or 0.0)
                for s in sorted(sorted(old_srcs, key=lambda layer: layer.source_name,
                                       reverse=True), key=delivered):
                    src_list.append((s.source_name, s.value, s.updated_by, s.origin_row_id))
            elif not is_blank_value(new_val):
                # 폴백 소스 - only a value the shell holds: absence makes no layer (판정 405 ·
                # 총괄 c773b0fed - an empty one was the newest layer and won the next resolve)
                src_list.append((source_name or "user", new_val, updated_by or "system", None))

            for s_name, s_val, s_by, s_origin in src_list:
                effective_src_name = s_name
                if s_name == "user" and is_old_user_overwritten and is_new_user_overwritten:
                    effective_src_name = "user"
                else:
                    r_id_6 = row_to_delete.row_id[:6] if row_to_delete.row_id else "merged"
                    tag = f"{row_to_delete.business_key_val}_{r_id_6}" if getattr(row_to_delete, "business_key_val", None) else r_id_6
                    effective_src_name = merged_layer_name(effective_src_name, tag)

                src_key = (table_name, row.row_id, col_name, effective_src_name)
                cell_sources_to_upsert[src_key] = {
                    "table_name": table_name,
                    "row_id": row.row_id,
                    "column_name": col_name,
                    "source_name": effective_src_name,
                    "value": clean_str_value(s_val),
                    "updated_by": s_by or "system",
                    # The shell's layer keeps the row it was read from (총괄 1495534c9) - a
                    # retraction of that row still finds it here.
                    "origin_row_id": s_origin,
                    # [P3] real datetime - see above.
                    "ingested_at": layer_instant()
                }

    # 4. 캐시 맵 마이그레이션 (row_to_delete.row_id ➡️ conflict_row.row_id)
    gone_id = row_to_delete.row_id
    if cell_sources_to_upsert is not None:
        keys_to_migrate = row_keys(cell_sources_to_upsert, gone_id)
        for k in keys_to_migrate:
            src_data = cell_sources_to_upsert.pop(k)
            new_k = (k[0], row.row_id, k[2], k[3])
            src_data["row_id"] = row.row_id
            cell_sources_to_upsert[new_k] = src_data

    if cell_overwrites_to_upsert is not None:
        keys_to_migrate = row_keys(cell_overwrites_to_upsert, gone_id)
        for k in keys_to_migrate:
            ow_data = cell_overwrites_to_upsert.pop(k)
            new_k = (k[0], row.row_id, k[2])
            ow_data["row_id"] = row.row_id
            cell_overwrites_to_upsert[new_k] = ow_data

    if cell_overwrites_to_delete is not None:
        keys_to_migrate = row_keys(cell_overwrites_to_delete, gone_id)
        for k in keys_to_migrate:
            cell_overwrites_to_delete.discard(k)
            cell_overwrites_to_delete.add((k[0], row.row_id, k[2]))

    if logs_to_cache is not None:
        by_row = getattr(logs_to_cache, "rows", None)
        moved = by_row.pop(gone_id, []) if by_row is not None else [
            log for log in logs_to_cache if log.get("row_id") == gone_id]
        for log in moved:
            log["row_id"] = row.row_id
        if by_row is not None and moved:
            by_row.setdefault(row.row_id, []).extend(moved)

    for obj in db.new:
        if isinstance(obj, models.AuditLog) and obj.row_id == gone_id:
            obj.row_id = row.row_id

    # 5. 무의미한 껍데기 행을 DB 세션 및 메모리 캐시에서 완전 소거
    # 🔴 A ROW THIS BATCH MADE IS TAKEN OUT, NOT DELETED (총괄 829e3fe20). It is pending -
    #    never written - and `db.delete` refuses it; the refusal was swallowed here, so the
    #    shell was INSERTED at the flush with every layer gone to the holder. `expunge`, as a
    #    new row with nothing to say is taken out in `_apply_batch_updates_once`: no INSERT, no
    #    outbox event. Its id still goes on `deleted_row_ids` - an earlier item of the batch may
    #    already be answering for it.
    if deleted_edits is not None:                 # {row_id: the table it was an edit of} - the caller's message
        from admin import access
        edit = access.edit_of_row(table_name, row_to_delete)
        if edit is not None:
            deleted_edits[row_to_delete.row_id] = edit
    if row_to_delete in db.new:
        db.expunge(row_to_delete)
    else:
        # 🔴 ITS STORED LAYERS AND MARKS GO WITH IT (소유자 10-03, 총괄 a13fcf00c) - here, after
        #    the holder took what it takes above; earlier, a person's value would go with them.
        #    They stayed under a row_id no row had, read by nothing, since the merge was written.
        delete_row_layers(db, table_name, [row_to_delete.row_id])
        db.delete(row_to_delete)
    if deleted_row_ids is not None:
        deleted_row_ids.append(row_to_delete.row_id)
    if row_cache is not None:
        row_cache.pop(row_to_delete.row_id, None)
        if row_to_delete.business_key_val:
            row_cache.pop(row_to_delete.business_key_val, None)


def merge_into_key_holders(db: Session, table_name: str, pairs, *, source_name: str,
                           updated_by: str, transaction_id: str) -> list:
    """Each (row_id, holder row_id) - a row whose rebuilt key the holder already carries - merged
    into the holder through `_merge_into_key_holder`, for a caller that writes no value: no cell
    is a person's this time (`human_columns` empty), so both rows' overwrite marks keep a
    person's value. The audit lines, layers and marks are written; the caller commits. Returns
    the merged rows' ids. Not undone. (rebuild_blank_business_keys --apply, the notation backfill)"""
    model = models.DYNAMIC_TABLES[table_name]
    sources, overwrites, overwrites_gone, logs, merged = ByRow(), ByRow(), ByRowSet(), ByRowLogs(), []
    for row_id, holder_id in pairs:
        shell = db.query(model).filter(model.row_id == row_id).one()
        holder = db.query(model).filter(model.row_id == holder_id).one()
        _merge_into_key_holder(
            db, table_name, model, shell, holder, explicit={}, human_columns=set(),
            source_name=source_name, updated_by=updated_by, transaction_id=transaction_id,
            changed_cols=[], overwrites_cache={}, cell_sources_to_upsert=sources,
            cell_overwrites_to_upsert=overwrites, cell_overwrites_to_delete=overwrites_gone,
            logs_to_cache=logs, deleted_row_ids=merged)
    if logs:
        bulk_insert_audit_logs(db, logs)
    bulk_upsert_cell_sources(db, list(sources.values()))
    bulk_upsert_cell_overwrites(db, list(overwrites.values()))
    bulk_delete_cell_overwrites(db, list(overwrites_gone))
    return merged


def update_item_as_line(table_name: str, update_item: schemas.GeneralUpdateItem, plan: dict, drop_stats: dict,
                        replaces_map: bool = False):
    """One funnel item as a `write_lines` item (lead 11-10 ㄱ: the funnel's cell judgement stays, its end hands
    write_lines its items) - a system, undeclared or unmapped column, a refused value and a blank from a writer that
    cannot mean emptied are dropped and counted by reason as `apply_row_update_internal` counts them; a formula's
    column holds no line (its value is the merge's, its history the batch's receipt, tallied in `plan["receipts"]`).
    The item is named by its row_id or its assembled key - write_lines claims it. `plan`: what the batch works out
    once (loadable, unmapped, refused_times, receipts, map_judged). -> (the write_lines item, the formulas whose
    column it carried - their receipts name the item's row)."""
    config = TABLE_CONFIG.get(table_name, {})
    types = config.get("column_types") or {}
    named = update_item.row_id or update_item.business_key_val
    values, formulas = {}, []
    for col_name, val in update_item.updates.items():
        reason = (DROP_SYSTEM_COLUMN if col_name in SYSTEM_COLUMNS
                  else DROP_UNDECLARED_COLUMN if col_name not in plan["loadable"] else None)
        if reason is None:
            if col_name not in plan["unmapped"]:
                plan["unmapped"][col_name] = bool(unmapped_columns(table_name, (col_name,)))
            reason = DROP_UNMAPPED_COLUMN if plan["unmapped"][col_name] else None
        if reason == DROP_UNDECLARED_COLUMN:
            _warn_undeclared_column_once(table_name, col_name)
        if reason is not None:
            _record_dropped_cell(drop_stats, named, update_item.business_key_val, col_name, reason, val)
            continue
        col_type = types.get(col_name, "string")
        formula = formula_written(table_name, col_name, update_item.source_name)
        tally = (plan["receipts"].setdefault(formula, {"row_ids": [], "blank": 0, "refused": 0,
                                                       "who": update_item.updated_by}) if formula else None)
        try:
            if col_name in plan["refused_times"] and str(val).strip() in plan["refused_times"][col_name]:
                raise CellRefused(col_name, val, "a time")
            clean_val = cast_value_by_type(val, col_type, col_name, table_name)
        except CellRefused as refused:
            if tally is None:
                _record_dropped_cell(drop_stats, named, update_item.business_key_val, col_name, DROP_VALUE_REFUSED,
                                     val)
                seen = drop_stats["refused_values"].get(col_name)
                if seen is not None:
                    seen["cells"] += 1
                elif len(drop_stats["refused_values"]) < MAX_DROP_REPORT_COLUMNS:
                    drop_stats["refused_values"][col_name] = {"cells": 1, "first": refused.value}
                continue
            clean_val = None
            tally["refused"] += 1
        if tally is not None:
            tally["blank"] += val is None
            formulas.append(formula)
            continue                                # a formula's column: no line
        if is_blank_value(clean_val) and not can_mean_emptied(update_item.source_name, replaces_map):
            _record_dropped_cell(drop_stats, named, update_item.business_key_val, col_name, DROP_ABSENT_NOT_WRITTEN,
                                 clean_val)
            continue
        values[col_name] = val
    return ({"row_id": update_item.row_id, "business_key_val": update_item.business_key_val, "values": values,
             "source_name": update_item.source_name, "written_by": update_item.updated_by,
             "input_row": update_item.origin_row_id, "version_judged": plan.get("map_judged", False)}, formulas)


def apply_row_update_internal(
    db: Session, 
    table_name: str, 
    update_item: schemas.GeneralUpdateItem,
    row_cache: dict = None,
    sources_cache: dict = None,
    overwrites_cache: dict = None,
    transaction_id: str = None,
    logs_to_cache: list = None,
    cell_sources_to_upsert: dict = None,
    cell_overwrites_to_upsert: dict = None,
    cell_overwrites_to_delete: set = None,
    deleted_row_ids: list = None,
    deleted_edits: dict = None,
    version_stats: dict = None,
    # [P2] The cells the caller prefetched cell metadata for (`LayersRead`, by row and
    # column). For these - and only these - a cache miss is a proven absence rather than
    # an unknown. See `_load_metadata_row_cell` for why "the row exists" is not the
    # same predicate and must not be substituted.
    layers_read: "LayersRead" = None,
    # [P3] The identity values the caller's prefetch ASKED about - see `ProbedIdentity`.
    # Distinct from `layers_read` (the cells that came back). None everywhere
    # outside the batch path, which keeps every other caller's query count unchanged.
    probed_identity: "ProbedIdentity" = None,
    # [Drop report] Per-batch accumulator for update keys this row DISCARDED
    # (`_new_drop_stats`). Written only from a branch that has already decided to drop,
    # so a batch that discards nothing never touches it. None = do not account.
    drop_stats: dict = None,
    # [S-83 ③] ONE instant for the whole request, read from the DATABASE by
    # `batch_write_instant`. A VALUE here rather than a SQL expression is what keeps the row
    # UPDATE on its batched path; None keeps the expression, so every caller outside the
    # batch path writes exactly what it wrote before.
    batch_now: Any = None,
    # [file-layer fold] Per-batch accumulator of `(table, row, column, source)` layers a file
    # write made redundant (`file_layer_fold`). None = do not fold.
    cell_sources_to_delete: set = None,
    plan: dict = None,
    # The batch replaces a map whole (`batch.replace_map`): a blank cell it names empties it (`can_mean_emptied`).
    replaces_map: bool = False
) -> tuple[Any, bool, list[str]]:
    """[통합 코어] row_id 또는 business_key 기반으로 행을 찾아 업데이트하고 메타데이터 테이블을 갱신합니다."""
    # The three graph-sync names left with their branch on 2026-08-31. They stay OUT of
    # this skip list rather than being kept "just in case": the list is what a write path
    # refuses to touch, and a name here that nothing writes is a rule protecting nothing.
    system_cols = SYSTEM_COLUMNS
    models.require_owner_columns(db.get_bind())     # added at boot; an ORM insert names every column

    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    composite_src = config.get("composite_key_source")

    # 인제션 매칭을 위해 updates 기반 선제 키 조립
    # [P6] The batch path now does this for every item BEFORE it builds the prefetch
    # filter, which is the only way the prefetch can see a key that does not exist yet
    # in the payload. The call stays here too: it is idempotent (the item already has a
    # key by now, so this returns immediately) and it keeps this function correct on its
    # own terms rather than on its caller's. A batch that already did says so in `plan` (총괄 249b43409).
    if not (plan or {}).get("keys_assembled"):
        assemble_composite_business_key(table_name, update_item)

    row, is_new = _get_or_create_row(db, table_model, update_item, row_cache, table_name,
                                     probed_identity=probed_identity)
    changed_cols = []
    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")

    # [Version gate] Judged HERE - after the row is resolved (so the verdict sees the row
    # the write would actually land on, however it was keyed) and before a single cell is
    # touched. A refusal returns an EMPTY changed_cols, so no value moves, no CellSource
    # is upserted, no audit log is written and nothing is broadcast as changed.
    gate_applied, gate_reason = version_gate_verdict(          # a row of a map judged whole: not asked again
        table_name, config, row, is_new or (plan or {}).get("map_judged", False), update_item)
    if gate_reason is not None and version_stats is not None:
        counts = version_stats.setdefault("counts", {})
        counts[gate_reason] = counts.get(gate_reason, 0) + 1
    if not gate_applied:
        return row, is_new, changed_cols

    # Update business key first
    _update_row_business_key(row, key_col, update_item, row_cache, table_name)

    # Old values snapshot for auditing
    old_values_snapshot = {}
    for col_name in update_item.updates.keys():
        if col_name in system_cols: continue
        old_values_snapshot[col_name] = getattr(row, col_name, None)

    # `plan` - what a batch worked out once for all its rows; alone, this row works it out itself
    loadable = plan["loadable"] if plan else loadable_columns(config)
    unmapped = plan["unmapped"] if plan else {}
    for col_name, val in update_item.updates.items():
        if col_name in system_cols:
            # [Drop report] A discard too, and it was the ONE silent branch nobody had
            # even counted. The write path owns these columns, so refusing the value is
            # right - but "we own that column" and "we never saw it" are different
            # answers and the caller could not tell them apart.
            if drop_stats is not None:
                _record_dropped_cell(drop_stats, row.row_id, update_item.business_key_val,
                                     col_name, DROP_SYSTEM_COLUMN, val)
            continue

        # The one answer, so this path and the watcher's cannot drift (S-119). The
        # type dict below answers a DIFFERENT question - what this column IS, not whether
        # it may be written - so it is read where it is used, not used as a filter.
        if col_name not in loadable:
            # Drop behaviour is deliberately unchanged: rejecting the write would turn a
            # lagging config into an outage. Only the silence is fixed.
            # ⚠️ Despite the name this COUNTS every drop and re-announces at each power
            # of ten; `undeclared_column_drops()` reads the counts. Warning once per
            # process is what made a fixed deployment and a broken one look identical.
            _warn_undeclared_column_once(table_name, col_name)
            # [Drop report] The process-lifetime counter above cannot say WHICH batch or
            # WHICH row, so it can never answer "did my write land?". This can.
            if drop_stats is not None:
                _record_dropped_cell(drop_stats, row.row_id, update_item.business_key_val,
                                     col_name, DROP_UNDECLARED_COLUMN, val)
            continue

        if col_name not in unmapped:
            unmapped[col_name] = bool(unmapped_columns(table_name, (col_name,)))
        if unmapped[col_name]:
            if drop_stats is not None:
                _record_dropped_cell(drop_stats, row.row_id, update_item.business_key_val,
                                     col_name, DROP_UNMAPPED_COLUMN, val)
            continue

        key = (row.row_id, col_name)
        col_srcs, ow = _load_metadata_row_cell(db, table_name, row.row_id, col_name, is_new, sources_cache, overwrites_cache, cell_sources_to_upsert, cell_overwrites_to_upsert, layers_read)

        # 3. 소스 데이터 upsert
        col_type = (config.get("column_types") or {}).get(col_name, "string")
        formula = formula_written(table_name, col_name, update_item.source_name)
        tally = (plan["receipts"].setdefault(formula, {"row_ids": [], "blank": 0, "refused": 0,
                                                       "who": update_item.updated_by})
                 if formula and plan else None)
        try:
            if plan and col_name in plan["refused_times"] and str(val).strip() in plan["refused_times"][col_name]:
                raise CellRefused(col_name, val, "a time")
            clean_val = cast_value_by_type(val, col_type, col_name, table_name)
        except CellRefused as refused:
            if tally is None:
                if drop_stats is not None:
                    _record_dropped_cell(drop_stats, row.row_id, update_item.business_key_val,
                                         col_name, DROP_VALUE_REFUSED, val)
                    seen = drop_stats["refused_values"].get(col_name)
                    if seen is not None:
                        seen["cells"] += 1
                    elif len(drop_stats["refused_values"]) < MAX_DROP_REPORT_COLUMNS:
                        drop_stats["refused_values"][col_name] = {"cells": 1, "first": refused.value}
                continue                        # not entered: no layer, the row's other cells go on
            clean_val = None                    # counted; the display answer casts the formula's own the same way
            tally["refused"] += 1
        if tally is not None and val is None:
            tally["blank"] += 1

        # 🔴 [S-243, 판정 405] ABSENCE MAKES NO LAYER; ONLY A DELIBERATE BLANK DOES.
        # 소유자 2026-09-15: 「빈 층 고의 입력은 진짜 빈 것, 그냥 없던 것은 아직 입력하지
        # 않은 것」. A file's empty cell used to be cast to NULL and STORED as that source's
        # layer - and because a file source outranks the chain (2 or 99 vs 4), that NULL
        # then hid a value the join had correctly written, forever. The virtual join's
        # COALESCE fills; this path did not, and nothing said so.
        #
        # ⛔ THE WRITER IS SELECTED POSITIVELY, for the reason `USER_SOURCE` states twenty
        # lines above: file parsers write under the INGESTED FILENAME, so the set of
        # automatic source names is open-ended and cannot be blacklisted. Only two writers
        # can MEAN an empty cell - a person clearing it, and the chain asserting that the
        # matched right row is empty (판정 f3c04dee).
        #
        # ⚠️ AND THE EXISTING LAYER IS LEFT ALONE, not deleted. 「Not entered」 is not
        # 「withdraw what you said before」 - so yesterday's value stays, and removing it is
        # the business of a person, of `withdraw_source` (R2), or of `replace_map`.
        if is_blank_value(clean_val) and not can_mean_emptied(update_item.source_name, replaces_map):
            if drop_stats is not None:
                _record_dropped_cell(drop_stats, row.row_id, update_item.business_key_val,
                                     col_name, DROP_ABSENT_NOT_WRITTEN, clean_val)
            continue

        src_obj = next((s for s in col_srcs if s.source_name == update_item.source_name), None)

        # [no-op write] Re-storing a source layer that already holds this exact value from
        # this exact writer is not an update, and PostgreSQL charges for it as if it were:
        # `ON CONFLICT DO UPDATE` writes a new tuple version, so a dead tuple per
        # cell-column either way. Measured on a 20,000-cell map re-pushed unchanged:
        # 120,000 dead tuples on cell_sources and 120,000 more on cell_overwrites, for a
        # map in which nothing had changed.
        #
        # 🔴 THE VALUE LAYER ALREADY DECIDED THIS. `has_changed` below has always
        # suppressed the column write, the audit log and the outbox event when the
        # resolved value is unchanged; only the SOURCE layer disagreed and wrote anyway.
        # Two layers disagreeing about whether the same fact changed is the defect.
        #
        # What this gives up is `ingested_at` moving on a no-op write, and that is the
        # improvement: it now means "when this source last CHANGED this value" instead
        # of "when someone last pressed save".
        #
        # 🔴 THIS COMMENT USED TO SAY "nothing resolves values by timestamp, so no cell
        # can change which layer wins because of this". THAT IS NO LONGER TRUE and the
        # sentence was left here long enough to be quoted as evidence in a diagnosis.
        # `compute_priority_value` now reads `ingested_at` to break a tie between
        # equally-ranked sources, so this line decides ties. The behaviour is still the
        # one we want, for a reason that has to be stated rather than assumed: a source
        # that re-delivers a value it has already delivered has not made a NEW
        # statement, so it must not jump ahead of a differing source that spoke after
        # it. "Newest" means newest assertion of a value, not newest touch. Removing
        # this guard would let a periodic re-delivery of a stale value silently win.
        # 🔴 [S-280 · 판정 434] THE ORIGIN IS PART OF THE STATEMENT. A cell whose value is
        # unchanged but whose INPUT ROW changed is a new statement about where the value
        # came from, and this is the note a retraction aims with - leaving it stale would
        # withdraw cells on the strength of a row that no longer feeds them, which is the
        # defect class this column exists to close.
        source_unchanged = (
            src_obj is not None
            and not values_differ(src_obj.value, clean_val, col_type)
            and src_obj.updated_by == update_item.updated_by
            and getattr(src_obj, "origin_row_id", None) == update_item.origin_row_id
        )
        # 🔴 [총괄 225b2c658 · f224477c1] WIDENED HERE, not beside it: a file layer that repeats
        # the newest layer of its class writes nothing either - an hourly refetch of an
        # unchanged row stacked one layer per file per cell (owner's production: nine deep,
        # prefetch 32 s of a 60 s chunk). One that differs is written, and the older file
        # layers of the class that say the same value go. 🔴 [소유자 11-08] And a NEW chain layer that says what the
        # cell shows writes nothing (production: a mapper handing back a file's cells made each a chain layer of the
        # same value); one the chain holds already is written as before, so it never stays behind with an old value.
        repeat, folded, moved = False, (), None
        if (not source_unchanged and is_file_layer(update_item.source_name)
                and (cell_sources_to_upsert is None or cell_sources_to_delete is not None)):
            repeat, folded, moved = file_layer_fold(
                col_srcs, update_item.source_name, clean_val, col_type, table_name,
                ow.manual_priority_source if ow else None)
        elif (not source_unchanged and not is_new
              and writer_kind(update_item.source_name) == "chain"
              and not any(layer_ranks_as(s.source_name) == layer_ranks_as(update_item.source_name)
                          for s in col_srcs)):                         # nor its row layers (chain_ingestion (<row>))
            # against what its layers compute, not the stored cell - skipping it then changes nothing: a key just
            # assembled on its row shows with no layer under it, a stored blank can sit over a file layer
            shown = compute_priority_value({s.source_name: {"value": s.value, "ingested_at": s.ingested_at}
                                            for s in col_srcs}, ow.manual_priority_source if ow else None, table_name)[0]
            repeat = not values_differ(shown, clean_val, col_type)
        source_unchanged = source_unchanged or repeat or bool(formula)    # a formula column holds no layer
        src_obj = src_obj or moved                     # its share's layer of this value is written, to the front

        if not src_obj and not repeat and not formula:
            if cell_sources_to_upsert is None:
                # No bulk accumulator: this object IS the write, so it has to be the
                # mapped one.
                src_obj = models.CellSource(
                    table_name=table_name,
                    row_id=row.row_id,
                    column_name=col_name,
                    source_name=update_item.source_name
                )
                db.add(src_obj)
            else:
                # [P3] With an accumulator, this object is never persisted - the row is
                # written from `cell_sources_to_upsert` below. It exists only to join
                # `col_srcs` for the priority computation, which reads exactly the four
                # attributes `LightCellSource` carries, and which is ALREADY handed
                # `LightCellSource` instances by the batch prefetch. Constructing a
                # mapped instance instead costs an InstanceState plus an attribute
                # event per assignment: measured 9 ORM constructions per ingested row
                # (7 of them here) and 45,000 `_initialize_instance` calls per 5,000
                # rows, 2.8 s of a 28.5 s run.
                src_obj = LightCellSource(
                    table_name, row.row_id, col_name, update_item.source_name,
                    None, None, None
                )
            col_srcs.append(src_obj)

        if not source_unchanged:
            src_obj.value = clean_val
            src_obj.updated_by = update_item.updated_by
            src_obj.origin_row_id = update_item.origin_row_id
            src_obj.ingested_at = layer_instant()
            for gone in folded:
                col_srcs.remove(gone)
                if cell_sources_to_upsert is None:
                    db.delete(gone)
                else:
                    gone_key = (table_name, row.row_id, col_name, gone.source_name)
                    cell_sources_to_upsert.pop(gone_key, None)
                    cell_sources_to_delete.add(gone_key)

            if cell_sources_to_upsert is not None:
                upsert_key = (table_name, row.row_id, col_name, src_obj.source_name)
                cell_sources_to_upsert[upsert_key] = {
                    "table_name": table_name,
                    "row_id": row.row_id,
                    "column_name": col_name,
                    "source_name": src_obj.source_name,
                    "value": clean_val,
                    "updated_by": update_item.updated_by,
                    # Unconditionally, never omitted when absent: `_is_executemany_safe`
                    # requires every mapping to carry the SAME keys, and a ragged list
                    # falls back to the slow send for a reason that has nothing to do
                    # with this column.
                    "origin_row_id": update_item.origin_row_id,
                    "ingested_at": src_obj.ingested_at
                }

        # 4. 우선순위 결정
        #
        # [tiebreak] An unknown `ingested_at` is reported as None, NOT as `now()`.
        # This used to substitute `datetime.now()`, which was harmless while the
        # timestamp was decoration and became a defect the moment it became the
        # tiebreak: `now()` is the largest timestamp there is, so an undated legacy
        # layer would have outranked every dated delivery - the exact inversion of
        # `compute_priority_value`'s level 2a ("a dated layer beats an undated one").
        # It would also have made this path disagree with `chain_replay._load_cell_state`
        # and `main.get_cell_sources`, which both pass the raw value through, so two
        # code paths resolving the SAME cell could pick different winners.
        # Measured 2026-08-11 on `assy_qa`: 0 of 2,432,116 `cell_sources` rows have a
        # NULL `ingested_at` (the column carries `server_default=func.now()`), so this
        # is a latent hazard being closed, not an observed one being repaired.
        sources_dict = {}
        for s in col_srcs:
            sources_dict[s.source_name] = {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else None,
                "updated_by": s.updated_by
            }
            
        manual_pin = ow.manual_priority_source if ow else None
        if update_item.source_name == "user":
            manual_pin = None # 수동 값 입력 시 핀 초기화
            
        # 🔴 One layer and no pin (lead 11-06, pfab: once per cell was 120,000 asks a 1,000-row x 120-column chunk):
        # the winner is that layer or the column's formula, and which depends on the column, the source and whether
        # the layer is dated - never on the value or the row. The batch asks once per that key and keeps the WINNER;
        # the value is the layer's own. Two or more layers, a pin, or a formula winning ask every time.
        # «dated?» reads "timestamp" where `resolution_ingested_at` does: `sources_dict` above holds only value ·
        # timestamp (ingested_at.isoformat() or None) · updated_by, so the two answers cannot part here. Asking
        # resolution itself per cell re-parses the time and costs the whole gain (C 11-06: 5.97 / 6.75 s).
        only = next(iter(sources_dict)) if plan is not None and manual_pin is None and len(sources_dict) == 1 else None
        asked = (col_name, only, sources_dict[only]["timestamp"] is None) if only else None
        if asked and plan.setdefault("winners", {}).get(asked) == only:
            new_val, top_src = layer_value(sources_dict, only), only
        else:
            new_val, top_src = compute_priority_value(sources_dict, manual_pin, table_name,
                                                      ranks=plan["ranks"] if plan else None,
                                                      cell=(table_name, col_name, row))
            if asked:
                plan["winners"][asked] = top_src
        old_val = old_values_snapshot.get(col_name)
        
        # 6. cell_overwrites 마킹
        is_overwrite = ("user" in sources_dict) or (manual_pin is not None)
        if is_overwrite:
            # [no-op write] Same argument as the source layer above, and the same measured
            # cost: a map push declares source_name='user', which marks EVERY cell-column
            # as an overwrite, so cell_overwrites takes an identical hit to cell_sources.
            # An overwrite marker that already says exactly this is not re-stated.
            # 🔴 `source_unchanged` IS PART OF THIS PREDICATE ON PURPOSE, and leaving it
            # out was a real over-reach caught by its own test. The overwrite row stores a
            # flag, a writer and a pin - not the value - so on a cell whose VALUE changed
            # those three are still identical, and a skip based on them alone would stop
            # refreshing `updated_at` on a genuine user edit. That silently redefines a
            # column other code displays.
            #
            # Requiring the source to be unchanged too costs nothing we wanted: the bloat
            # being removed is entirely on cells where nothing changed. A changed cell
            # keeps today's behaviour exactly.
            ow_unchanged = (
                source_unchanged
                and ow is not None
                and ow.is_overwrite is True
                and ow.updated_by == (update_item.updated_by or "system")
                and ow.manual_priority_source == manual_pin
            )
            if not ow:
                # [P3] Same argument as the CellSource above: with an accumulator this
                # marker is written from `cell_overwrites_to_upsert`, never from this
                # object, and `overwrites_cache` is already populated with
                # `LightCellOverwrite` by the batch prefetch.
                if cell_overwrites_to_upsert is None:
                    ow = models.CellOverwrite(
                        table_name=table_name,
                        row_id=row.row_id,
                        column_name=col_name
                    )
                    db.add(ow)
                else:
                    ow = LightCellOverwrite(
                        table_name, row.row_id, col_name, None, None, None, None)
                if overwrites_cache is not None:
                    overwrites_cache[key] = ow
            if not ow_unchanged:
                ow.is_overwrite = True
                ow.updated_by = update_item.updated_by or "system"
                ow.updated_at = datetime.now()
                ow.manual_priority_source = manual_pin

            if not ow_unchanged and cell_overwrites_to_upsert is not None:
                ow_key = (table_name, row.row_id, col_name)
                cell_overwrites_to_upsert[ow_key] = {
                    "table_name": table_name,
                    "row_id": row.row_id,
                    "column_name": col_name,
                    "is_overwrite": True,
                    "updated_by": ow.updated_by,
                    "updated_at": ow.updated_at,
                    "manual_priority_source": ow.manual_priority_source
                }
                if cell_overwrites_to_delete is not None:
                    cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                ow_key = (table_name, row.row_id, col_name)
                if cell_overwrites_to_delete is not None:
                    cell_overwrites_to_delete.add(ow_key)
                    if cell_overwrites_to_upsert is not None:
                        cell_overwrites_to_upsert.pop(ow_key, None)
                else:
                    db.delete(ow)
                if overwrites_cache is not None:
                    overwrites_cache[key] = None

        has_changed = is_new or values_differ(old_val, new_val, col_type)

        if has_changed:
            setattr(row, col_name, new_val)
            changed_cols.append(col_name)
            if tally is not None:
                tally["row_ids"].append(row.row_id)
            if update_item.source_name == "user":
                log_dict = create_audit_log(
                    db, table_name, row.row_id, col_name, old_val, new_val, 
                    update_item.source_name, (update_item.updated_by or "user"), 
                    transaction_id=transaction_id, business_key=row.business_key_val,
                    add_to_cache=(logs_to_cache is None)
                )
                if logs_to_cache is not None and log_dict is not None:
                    logs_to_cache.append(log_dict)

        # 총괄 5ee9d3bd1 ② · 3eb161a9c ①: a value the notation fold changed leaves one line per
        # cell - the spelling that arrived, what is stored, under the writer that sent it - only
        # when the cell is written. A re-sent spelling the no-op above kept writes nothing.
        arrived = (update_item._written_spelling or {}).get(col_name)
        if arrived is not None and (has_changed or not source_unchanged):
            log_dict = create_audit_log(
                db, table_name, row.row_id, col_name, arrived, clean_val,
                update_item.source_name, (update_item.updated_by or "system"),
                transaction_id=transaction_id, business_key=row.business_key_val,
                add_to_cache=(logs_to_cache is None))
            if logs_to_cache is not None and log_dict is not None:
                logs_to_cache.append(log_dict)

    lined = [col for col in changed_cols if not formula_written(table_name, col, update_item.source_name)]
    if lined and update_item.source_name != "user":
        log_dict = row_update_line(
            db, table_name, row.row_id, lined, {col: getattr(row, col, None) for col in lined},
            old_values_snapshot, is_new, update_item.source_name, update_item.updated_by,
            transaction_id, row.business_key_val, add_to_cache=(logs_to_cache is None))
        if logs_to_cache is not None and log_dict is not None:
            logs_to_cache.append(log_dict)

    # ⚰️ [Notation normalization] REVERSED FOR `write` COLUMNS BY THE OWNER'S DECISION (총괄
    # 5ee9d3bd1 ③): such a column is folded ONCE, ahead of this function, by
    # `_fold_written_notation`, and the cell loop above writes its audit line. The paragraph
    # below is the record of the compare-only model, which every other column still has.
    # [Notation normalization] THERE IS NOTHING HERE ANY MORE, and that is the design.
    # A derivation hook used to sit at this exact spot, refreshing a physical
    # `<col>_norm` column from the value that had just won the priority computation.
    # User ruling 2026-08-04 withdrew the stored column: normalization is now a
    # DECLARATION consumed at QUERY TIME, folding both sides of a comparison in SQL
    # (`notation_norm.fold_notation_sql`). The write path stores raw and only raw, so
    # a folding rule can be changed by editing one config line with nothing to
    # backfill, nothing to re-derive, and no column that is visible but uneditable.
    # See `notation_norm`'s module docstring for the measurements that forced it.

    # 2. 복합 비즈니스 키 실시간 재계산 및 동기화, 유일성 검사
    # 🔴 [총괄 a61d32f4f ㄱ] 조합키를 선언한 표 «전부»다. `business_key` 칸이 없는 표(신원이
    #   `business_key_val` 에만 산다)가 이 문 밖에 있어서, id 로 부르며 키 조각을 처음 채운
    #   행(이름 붙인 id 로 만들기 · 그리드 새 행)이 키 없이 남고 다음 키 쓰기가 행을 하나 더
    #   만들었다. 그 칸을 쓰는 줄만 그 칸이 있을 때.
    if composite_src:
        is_src_changed = any(col in changed_cols for col in composite_src)
        # ⛔ `or is_new` IS GONE (판정 190 B), NOT THE WHOLE BRANCH. Since A assembles
        # before the lookup, a new row already ARRIVES carrying its assembled key, so
        # recomputing here only produced the shell row the composite xfail was pinning.
        # What remains is a DIFFERENT event: an edit that changes a key PART re-keys an
        # existing row, and that path's collision merge is still needed.
        if is_src_changed:
            new_bk_val = rebuilt_business_key(table_name, row)
            if is_new and (new_bk_val is None or _unfilled_composite_parts(composite_src, update_item.updates)):
                # 이 쓰기가 키를 지을 조각을 안 실은 새 행(조각이 모두 비었거나 안 실림)은 이 쓰기가 준 키를 지킨다 -
                # 위 `_update_row_business_key` 가 이미 행에 올렸다. 안 실린 조각을 NULL 로 읽어 지으면 조립(판정 190 B)과
                # 갈라져 같은 키의 새 행이 여럿 생긴다. 실린 빈 조각은 조각이라 조립 키가 준 키를 이긴다(총괄 242f4a43a
                # ㄱ2 — 총괄 10-14 (b) 는 «안 실린» 조각에만 남는다).
                new_bk_val = getattr(row, "business_key_val", None)

            current_bk = getattr(row, "business_key_val", None)
            if current_bk != new_bk_val:
                if new_bk_val is not None:
                    conflict_row = _find_business_key_conflict(
                        db, table_model, new_bk_val, row, row_cache, probed_identity)
                    if conflict_row:
                        # -------------------------------------------------------------
                        # [대안 B: Silent Merge & Overwrite]
                        # -------------------------------------------------------------
                        # 1. 중복되어 버려질 임시 껍데기 행 기록
                        row_to_delete = row
                        
                        # 2. 가공 대상 행을 기존 존재하던 충돌 행으로 스위칭
                        row = conflict_row
                        is_new = False
                        
                        _merge_into_key_holder(
                            db, table_name, table_model, row_to_delete, row,
                            explicit=update_item.updates,
                            human_columns=(
                                set(update_item.updates)
                                if (update_item.source_name == "user" or (
                                    update_item.updated_by and update_item.updated_by != "system"
                                    and "parser" not in str(update_item.updated_by).lower()))
                                else set()),
                            source_name=update_item.source_name,
                            updated_by=update_item.updated_by, transaction_id=transaction_id,
                            changed_cols=changed_cols, overwrites_cache=overwrites_cache,
                            sources_cache=sources_cache, layers_read=layers_read,
                            cell_sources_to_upsert=cell_sources_to_upsert,
                            cell_overwrites_to_upsert=cell_overwrites_to_upsert,
                            cell_overwrites_to_delete=cell_overwrites_to_delete,
                            logs_to_cache=logs_to_cache, deleted_row_ids=deleted_row_ids,
                            row_cache=row_cache, deleted_edits=deleted_edits)

                written_col, old_bk_col_val = put_business_key(table_name, row, new_bk_val)
                if row_cache is not None:
                    if current_bk in row_cache and row_cache[current_bk] == row:
                        del row_cache[current_bk]
                    if new_bk_val is not None:
                        row_cache[new_bk_val] = row

                if written_col and old_bk_col_val != new_bk_val:
                    changed_cols.append(written_col)
                    if update_item.source_name == "user":
                        log_dict = create_audit_log(
                            db, table_name, row.row_id, written_col, old_bk_col_val, new_bk_val, 
                            update_item.source_name, (update_item.updated_by or "user"), 
                            transaction_id=transaction_id, business_key=row.business_key_val,
                            add_to_cache=(logs_to_cache is None)
                        )
                        if logs_to_cache is not None and log_dict is not None:
                            logs_to_cache.append(log_dict)

    if changed_cols or is_new:
        from sqlalchemy.sql import func
        if not is_new:
            # [P3] Only an UPDATE needs this. On an INSERT the column's server default
            # is the same `now()` in the same transaction, and setting it explicitly is
            # what forced one statement per row (see `_get_or_create_row`).
            #
            # 🔴 S-83 ③. AND ON AN UPDATE IT FORCED ONE STATEMENT PER ROW TOO, for the same
            # reason [P3] already names three screens up: a `ClauseElement` in the SET clause
            # takes the write off its batched path. Measured on 1,000 rows in this box:
            # `UPDATE ... SET updated_at=CURRENT_TIMESTAMP, ... WHERE row_id = ?` ONE
            # DISTINCT TEXT, executed a THOUSAND TIMES - 1,006 statements for one request.
            # With a value here instead it is ONE executemany, and 7 statements for the
            # request. On sqlite that is 0.44 s -> 0.26 s; on PostgreSQL those thousand
            # executions are a thousand ROUND TRIPS, which is the number this is about.
            #
            # ⚠️ THE CLOCK STAYS THE DATABASE'S. `batch_now` is `SELECT now()` taken ONCE by
            # the caller, in this transaction - and on PostgreSQL `now()` IS the transaction
            # timestamp, so every row of the batch gets exactly the instant the per-row
            # expression would have produced. Reading the app server's clock instead would
            # put two clock sources on one column, since INSERT still takes the DB's through
            # `server_default` - and skew between them is invisible until the day it orders
            # `idx_<table>_updated` wrong.
            row.updated_at = func.now() if batch_now is None else batch_now
    return row, is_new, changed_cols


def row_update_line(db, table_name, row_id, changed_cols, new_values, old_values, is_new, source_name, updated_by,
                    transaction_id, business_key, add_to_cache=True):
    """The `ROW_UPDATE` history line a machine write leaves on a row it changed - the write door's, and
    `replay.fold_units`' for the cells whose answer is already decided (총괄 10-11). A column its table keeps no
    history for (`keeps_history`) is not named; None - no line made - when none is left (lead 11-09 ②)."""
    changed_cols = [col for col in changed_cols if keeps_history(table_name, col)]
    if not changed_cols:
        return None
    new_parts = ["%s: %s" % (col, "empty" if new_values.get(col) is None else new_values.get(col))
                 for col in changed_cols]
    if is_new:
        old_summary, summary_msg = None, "New row: " + ", ".join(new_parts)
    else:
        old_summary = ", ".join("%s: %s" % (col, "empty" if old_values.get(col) is None else old_values.get(col))
                                for col in changed_cols)
        summary_msg = ", ".join(new_parts)
    return create_audit_log(db, table_name, row_id, "ROW_UPDATE", old_summary, summary_msg, source_name,
                            updated_by or "system", transaction_id=transaction_id, business_key=business_key,
                            add_to_cache=add_to_cache)


def prime_merge_cells(db, table_name: str, overwrites_cache: dict, sources_cache, row_ids, columns):
    """Every overwrite these rows carry, in ONE query, with the ABSENCES cached too - and, given a
    `sources_cache`, every layer of theirs not cached yet, in one more: a merge reads every column and
    the batch read only the columns it writes (`LayersRead`, 총괄 10-24). A cell already cached is the
    batch's own, written to in this pass, and is kept.

    🔴 A CACHE MISS AND AN ABSENT OVERWRITE WERE THE SAME VALUE. The collision-merge
    loop asked with `.get(...)` and treated a falsy answer as "not loaded", so every
    column that simply HAS no overwrite issued its own SELECT - and having no overwrite
    is the ordinary state of a column. The cost was 2 x (columns) statements per merged
    row rather than one statement for the pair of rows.

    🔴 AND THE CONFLICT ROW WAS NEVER PREFETCHED AT ALL. `_apply_batch_updates_once`
    primes `overwrites_cache` from the row ids the batch NAMED; the conflict row is found
    by a business key recomputed during the pass, so it is not among them and not one of
    its columns was cached.

    Storing `None` for a (row, column) with no overwrite is what `_load_metadata_row_cell`
    already does a few hundred lines above, and for the same reason: with `None` stored,
    "asked, and there is none" stops looking like "never asked".

    ⚠️ IT DECIDES NOTHING. The merge's protection rules read the same objects they read
    before; only where those objects come from changed.
    """
    if overwrites_cache is None or not row_ids or not columns:
        return 0
    ids = [r for r in dict.fromkeys(row_ids) if r]
    unread = [r for r in ids if sources_cache is not None and any((r, c) not in sources_cache for c in columns)]
    if unread:
        layers = {}
        cs = models.CellSource
        for layer in (db.query(cs.table_name, cs.row_id, cs.column_name, cs.source_name, cs.value, cs.updated_by,
                               cs.ingested_at, cs.origin_row_id)
                      .filter(cs.table_name == table_name, cs.row_id.in_(unread))
                      .order_by(cs.row_id, cs.column_name, cs.source_name.asc())):
            layers.setdefault((layer[1], layer[2]), []).append(LightCellSource(*layer))
        for r in unread:
            for c in columns:
                sources_cache.setdefault((r, c), layers.get((r, c), []))
    unprimed = [r for r in ids
                if any((r, c) not in overwrites_cache for c in columns)]
    if not unprimed:
        return 0
    for ow in (db.query(models.CellOverwrite)
                 .filter(models.CellOverwrite.table_name == table_name,
                         models.CellOverwrite.row_id.in_(unprimed)).all()):
        overwrites_cache[(ow.row_id, ow.column_name)] = ow
    for r in unprimed:
        for c in columns:
            overwrites_cache.setdefault((r, c), None)
    return len(unprimed)


def map_keys_said(table_name: str, row_ids, values, limit: int = 5) -> str:
    """The first `limit` of `row_ids` as an operator reads them (총괄 10-21, 소유자 「로그 띄워 지워진 것」): each row's
    key inside its map - composite_key_source less map_key_columns, «base_x=3 base_y=4» - from `values` ({row_id: its
    values}); its row_id when the table names no such key. «…» past the limit."""
    cfg = TABLE_CONFIG.get(table_name, {})
    inside = [c for c in (cfg.get("composite_key_source") or []) if c not in (cfg.get("map_key_columns") or [])]
    said = []
    for row_id in list(row_ids)[:limit]:
        cells = values.get(row_id) or {}
        said.append(" ".join("%s=%s" % (c, key_part(table_name, c, cells.get(c))) for c in inside)
                    if inside and cells else str(row_id))
    return ", ".join(said) + (" …" if len(row_ids) > limit else "")


def _write_deleted_edits(db, table_name, row_ids, deleted_edits):
    """`deleted_edits` (the caller's out-argument, None = not asked: nothing read) takes what each of `row_ids` is an
    edit of (`access.edits_by_row`)."""
    if deleted_edits is None or not row_ids:
        return
    from admin import access
    deleted_edits.update(access.edits_by_row(db, table_name, row_ids) or {})


def purge_map_rows(db, table_model, table_name: str, row_ids, said=None):
    """Delete map rows and their cell metadata, and TELL THE OUTBOX. `said` (a list): the deleted rows' keys are put
    on it as one text (`map_keys_said`), from the values read before the delete - for the replace line.

    🔴 THE ONE WRITE THE OUTBOX COULD NOT SEE. Every other write in this system reaches
    `database.stage_event` through SQLAlchemy's `before_flush`, which walks
    `session.deleted`. A bulk `.delete(synchronize_session=False)` never loads the rows
    into the session, so that list stays empty and these deletions produced no event at
    all: no history to ask later, and the graph and sweep never learned. That made this
    write the exception to a rule everything else in the codebase follows -- the fourth
    cleanliness rule, one capability with two paths.

    ⛔ AND THERE WERE TWO PURGE SITES, NOT ONE. The diff branch (`removed_row_ids`) and the
    non-diff branch (`purged_row_ids`) each spelled the same three deletes by hand, so
    repairing only the one that was read would have left the other still invisible. They
    call this instead, which is why the event cannot be added to one and forgotten on the
    other.

    🔴 AND IT WRITES AUDIT HISTORY, THROUGH THE PLACE THAT ALREADY DID.
    Until 2026-09-07 this wrote the outbox event and nothing else, and the docstring said so
    -- 「IT DOES NOT WRITE AUDIT HISTORY」. Those are two different questions and the second
    stayed open for the whole time the first read as closed. `delete_rows_batch` had recorded
    every row it removed since long before; the same 「행을 지운다」 through this path recorded
    none, so 「what was deleted?」 had an answer for one kind of deletion and not the other.
    `record_row_deletions` is that one place and both paths call it, which is why the
    recording cannot be added to one and forgotten on the other.

    ⚠️ THE USER AND THE TRANSACTION COME FROM THE REQUEST CONTEXT, not from new
    arguments. `stage_collapsed_event` below reads the same three contextvars for the same
    reason, and widening this signature would have moved the two call sites and the
    assertions that pin them for a fact both callers already carry.

    🔵 A `DELETE` event wakes every rule but an AI's (`chain_bindings.takes_deletions`, owner 11-06 step 2) - it
    carries each row's values as its old values for those rules.
    """
    from database.database import row_values, stage_collapsed_event

    row_ids = list(row_ids or [])
    if not row_ids:
        return []

    # 🔴 READ BEFORE THE DELETE, for the same reason `delete_rows_batch` reads first:
    # the business key lives on the row, and after the delete there is nothing to ask.
    rows = db.query(table_model).filter(table_model.row_id.in_(row_ids)).all()
    # Staged BEFORE the deletes so the event is added to the same flush that removes the
    # rows -- the transactional-outbox guarantee this codebase keeps everywhere else.
    # With each row's values as its old values (총괄 옛 키).
    values = {row.row_id: row_values(row) for row in rows}
    if said is not None:
        said.append(map_keys_said(table_name, row_ids, values))
    stage_collapsed_event(db, "DELETE", table_name, row_ids,
                          old=[values.get(row_id, {}) for row_id in row_ids])

    from database.context import request_user, request_transaction_id
    record_row_deletions(
        db, table_name, rows,
        request_user.get() or "system",
        request_transaction_id.get() or str(uuid6.uuid7()))

    delete_row_layers(db, table_name, row_ids)
    db.query(table_model).filter(
        table_model.row_id.in_(row_ids)
    ).delete(synchronize_session=False)
    return row_ids


def replace_map_columns(table_name: str, table_info: dict = None):
    """The map_key_columns a file replaces whole when the table's table_config sets `allow_replace_map` (the chain
    rule's word, widened to files - lead 59b020ca2, owner 10-20); None when it does not. Refused (ValueError, one
    sentence) when the cell is not true/false, or is on for a table declaring no map_key_columns. The watcher asks
    it where it loads its sources and where it writes a file."""
    import validation

    info = TABLE_CONFIG.get(table_name, {}) if table_info is None else (table_info or {})
    on = info.get("allow_replace_map", False)
    why = validation.flag_refusal("allow_replace_map", on)
    if why:
        raise ValueError("table_config '%s': %s" % (table_name, why))
    if not on:
        return None
    columns = info.get("map_key_columns")
    if not columns or not isinstance(columns, list):
        raise ValueError("table_config '%s' sets allow_replace_map but declares no map_key_columns - a file replaces "
                         "each map it holds whole, and the map is named by those columns. Next: declare "
                         "map_key_columns, or remove allow_replace_map" % table_name)
    return [str(column) for column in columns]


def derive_replace_map_scope(table_name: str, batch: schemas.GeneralUpdateBatch) -> Optional[dict]:
    """Resolve the exact {column: value} filters a replace_map purge will DELETE by.

    Single source of truth for the purge scope: apply_batch_updates deletes with the
    returned filters and the API layer echoes the same dict to the caller, so what the
    client is told IS what was deleted (both sides call this pure function - no drift).

    Resolution order:
      1. batch.scope (explicit) - validated strictly: every key must be a declared
         column, inside the table's map-key contract, physically on the model, and
         carry a non-empty value. Any violation raises ValueError - a dropped filter
         would WIDEN a DELETE, so nothing is silently skipped on this path.
      2. batch.updates[0] (derived) - map_key_columns when declared, else the legacy
         fallback (every non-coordinate column that the first payload row carries).

    Returns None when no filter can be resolved. Callers MUST treat None as a refusal:
    an empty filter set would either delete the whole table or (the historical bug)
    delete nothing while still answering 200 - rows then accumulate silently.
    """
    config = TABLE_CONFIG.get(table_name, {})
    col_types = config.get("column_types", {})
    map_key_cols = config.get("map_key_columns", [])
    col_types_lower = {k.lower(): k for k in col_types.keys()}
    table_model = models.DYNAMIC_TABLES.get(table_name)

    if map_key_cols and isinstance(map_key_cols, list) and len(map_key_cols) > 0:
        target_cols = [str(c) for c in map_key_cols]
    else:
        skip_cols = {"x", "y", "col_x", "col_y", "val", "code", "die_id", "grid_metadata", "leg"}
        target_cols = [c for c in col_types.keys() if c.lower() not in skip_cols]
    allowed_lower = {c.lower() for c in target_cols}

    if batch.scope is not None:
        resolved = {}
        for c_name, c_val in batch.scope.items():
            real_col_name = col_types_lower.get(str(c_name).lower())
            if real_col_name is None:
                raise ValueError(
                    f"replace_map scope column '{c_name}' is not a declared column of '{table_name}'"
                )
            if str(c_name).lower() not in allowed_lower:
                raise ValueError(
                    f"replace_map scope column '{c_name}' is outside the map-key contract of "
                    f"'{table_name}' (allowed: {sorted(target_cols)})"
                )
            if is_blank_value(c_val):
                raise ValueError(f"replace_map scope column '{c_name}' has an empty value")
            if table_model is not None and getattr(table_model, real_col_name, None) is None:
                raise ValueError(
                    f"replace_map scope column '{real_col_name}' does not physically exist on '{table_name}'"
                )
            resolved[real_col_name] = c_val
        return resolved or None

    if not batch.updates:
        return None
    sample_item = batch.updates[0]
    resolved = {}
    for target_col in target_cols:
        real_col_name = col_types_lower.get(target_col.lower())
        if not real_col_name:
            continue
        # Mirrors the historical derived-path behaviour: a config column missing on the
        # model is skipped (config/model mismatch is transient during schema rollout).
        if table_model is not None and getattr(table_model, real_col_name, None) is None:
            continue
        for c_name, c_val in sample_item.updates.items():
            if c_name.lower() == real_col_name.lower() and not is_blank_value(c_val):
                resolved[real_col_name] = c_val
                break
    return resolved or None


def _virtual_join_right_keys(db: Session, table_name: str):
    """`(rule, columns, folds)` for every APPROVED virtual join whose RIGHT side is this
    table - i.e. every uniqueness this table is actually carrying an index for.

    🔴 APPROVED, NOT MERELY DECLARED, AND THAT DIRECTION IS THE WHOLE CARE. Approval means
    「a UNIQUE index covering this join key EXISTS」; where it does not, there is no
    constraint for a duplicate to break, the write succeeds, and refusing rows would be a
    guard throwing away data the database would have taken. So the refusal fires exactly
    where the failure it is named after can happen.

    `right_folds` rides along because the index is built on the FOLDED expression
    (`index_key_expression`); comparing raw values would miss exactly the duplicates the
    index catches, which is the under-approximation that is not safe here.

    ⚠️ ONE LOAD PER PROCESS, KEYED TO LOADING RATHER THAN TO A CLOCK (판정 652 · 667). The
    answer used to come from the read-time join engine's 5-second TTL cache; that engine is
    retired and the declarations are the REAL join's now. The seat is
    `chain.synthesis.right_keys_for`, which pays file-once plus one index probe per declared
    key on this process's FIRST batch and nothing on every batch after, until the process
    reads the declarations again. With no declarations it probes nothing at all.
    """
    try:
        from chain import synthesis
        return synthesis.right_keys_for(db, table_name)
    except Exception as e:
        # Same posture as the sibling guard below: an unreadable declaration means NO join
        # is in effect, so there is no uniqueness to protect. Failing the write here would
        # turn a config problem into an outage.
        logger.error(f"[JoinUnique] could not load declarations for "
                     f"'{table_name}', no row is refused: {e}", exc_info=True)
        return []


def _folded_join_key(updates: dict, columns: list, folds: list, table_name: str):
    """One item's value for a join key, folded THE WAY THE INDEX FOLDS IT, or None.

    `None` means 「this payload does not carry the whole key」, which is not a verdict: the
    stored row may complete it, and refusing on a partial update would refuse a write that
    cannot break anything. And 「every part is blank」 (`every_key_part_blank`): the index leaves that row out.
    """
    import map_overlay
    import notation_norm

    key = []
    for index, column in enumerate(columns):
        if column not in (updates or {}):
            return None
        value = updates.get(column)
        # a datetime key is the index's `assy_key_instant` - the one speller's spelling
        value = (map_overlay.canonical_bind_value(table_name, column, value)
                 if map_overlay.key_time_zone(table_name, column) and not is_blank_key_part(value)
                 else clean_str_value(value))
        rules = folds[index] if index < len(folds) else None
        key.append(notation_norm.fold_notation(value, rules) if rules else value)
    return None if every_key_part_blank(key) else tuple(key)


def _item_identity(item, index: int):
    """Which ROW this batch item lands on, as far as the payload can say.

    The uniqueness a join owes is violated by two DIFFERENT rows sharing one key; two items
    landing on the SAME row are merged by `unique_results` long before any statement runs,
    so identity - not payload equality - is what separates a duplicate emission from a
    genuine conflict. An item carrying neither handle is its own row, which is the reading
    that refuses rather than the one that lets a pair through.
    """
    return (getattr(item, "row_id", None)
            or getattr(item, "business_key_val", None)
            or ("#%d" % index))



def _stored_join_key_owners(db: Session, table_name: str, columns: list, folds: list,
                            wanted: dict):
    """`{folded key: identity}` for rows ALREADY STORED under one of `wanted`'s keys.

    🔴 THE HALF `refuse_virtual_join_duplicates` SAID IT DID NOT DO (2026-09-14 outage).
    The in-batch pass catches one mapper emitting the pair. A row colliding with one that
    is already in the table breaks the same index, is NOT part of the statement's
    `ON CONFLICT` target, and therefore kills the WHOLE statement - so nothing is written,
    a file ingestion fails entirely, and no chain rule has to be involved for it to happen.
    That is why disabling every chain rule did not stop it.

    The filter uses the SAME folded expression the index is built on
    (`index_key_expression`), per column, and the exact tuple match is done in Python.
    Column-wise `IN` is a SUPERSET of the wanted tuples - never a subset - so the Python
    pass decides and nothing is missed.
    """
    if not wanted:
        return {}
    model = models.DYNAMIC_TABLES.get(table_name)
    if model is None:
        return {}
    from chain import join_key_index
    from sqlalchemy import text as sa_text

    exprs = [join_key_index.index_key_expression(column, folds[i] if i < len(folds) else None,
                                      table_name)
             for i, column in enumerate(columns)]
    params, wheres = {}, []
    for i, expr in enumerate(exprs):
        values = sorted({str(key[i]) for key in wanted})
        names = []
        for j, value in enumerate(values):
            names.append(":k%d_%d" % (i, j))
            params["k%d_%d" % (i, j)] = value
        wheres.append("%s IN (%s)" % (expr, ", ".join(names)))
    sql = 'SELECT row_id, business_key_val, %s FROM "%s" WHERE %s' % (
        ", ".join("%s AS k%d" % (expr, i) for i, expr in enumerate(exprs)),
        table_name, " AND ".join(wheres))
    owners = {}
    for row in db.execute(sa_text(sql), params).fetchall():
        key = tuple(row[2 + i] for i in range(len(exprs)))
        if key in wanted:
            # 🔴 BOTH HANDLES, BECAUSE THE ITEM MAY CARRY EITHER. Returning one of them
            # and comparing it against the other is how a row re-pushing its OWN key was
            # read as a clash - an upsert refused as a duplicate, silently dropping a
            # legitimate update. The caller must be able to match on whichever the item has.
            owners[key] = (row[0], row[1])
    return owners

def refuse_virtual_join_duplicates(db: Session, table_name: str,
                                   batch: schemas.GeneralUpdateBatch):
    """Two rows claiming one virtual join's key are refused BY NAME; the rest are written.

    🔴 THE SHAPE OF THE REFUSAL WAS THE DEFECT, NOT THE DETECTION (S-174, owner
    2026-09-11). A mapper emitting two rows with the same right-side key made the upsert
    fail on `uq_vjoin_<table>_<columns>` - a unique constraint that is NOT the statement's
    `ON CONFLICT` target, so there is no `DO UPDATE` arm for it and the whole STATEMENT
    dies. That failed the group, quarantined it, re-expanded it into a thousand per-row
    events, and the HOL guard then held every other group behind that table. One row of
    data stopped one table's chain, and all the operator saw was a driver error in Korean.

    ⚠️ BOTH ARE REFUSED, NOT ONE. Which of the two is true is a question the DATA asks and
    the product cannot answer; keeping either would write a guess and the guess would look
    like a fact. So both are skipped, both are named, and each is told the other's key.

    ⚠️ BOTH HALVES: a pair within one batch, and a row whose key a DIFFERENT stored row holds
    (`_stored_join_key_owners`, one read per batch - the «stored half» below). Measured on
    PostgreSQL 10-29: either overlap leaves the batch running, the offending rows refused.

    Returns the refusals; `batch.updates` is left holding the survivors.
    """
    keys = _virtual_join_right_keys(db, table_name)
    if not keys or not batch.updates:
        return []

    items = list(batch.updates)
    refused_indexes, refusals = set(), []
    for rule_name, columns, folds in keys:
        by_key = {}
        for index, item in enumerate(items):
            key = _folded_join_key(getattr(item, "updates", None), columns, folds, table_name)
            if key is not None:
                by_key.setdefault(key, []).append(index)
        for key, group in sorted(by_key.items(), key=lambda pair: str(pair[0])):
            identities = {}
            for index in group:
                identities.setdefault(_item_identity(items[index], index), []).append(index)
            if len(identities) < 2:
                # One row, named twice. `unique_results` merges those into a single row
                # before any statement is built, so nothing can violate anything.
                continue
            named = sorted(str(name) for name in identities)
            for index in group:
                refused_indexes.add(index)
                mine = str(_item_identity(items[index], index))
                refusals.append({
                    "reason": DROP_UNIQUE_VIOLATED,
                    "rule": rule_name,
                    "columns": list(columns),
                    "key": list(key),
                    "row": mine,
                    "others": [name for name in named if name != mine],
                    "message": (
                        f"규칙 '{rule_name}' 의 행 {mine} 이(가) 조인 선언의 오른쪽 "
                        f"유일성({', '.join(columns)}={', '.join(str(v) for v in key)})을 "
                        f"어겨 건너뜀 — 같은 조인 키의 다른 행: "
                        f"{', '.join(name for name in named if name != mine)}"),
                })
            # 🔴 [S-247] AND THE ACTION IS NOT OBVIOUS FROM THE SYMPTOM. 「같은 조인
            # 키의 행이 둘」 has two opposite repairs - fold the data, or widen the
            # declaration - and which one is right depends on whether those rows are the
            # SAME fact. The line says so rather than leaving the operator to guess.
            import operator_line

            logger.warning("%s", operator_line.line(
                "JoinUnique", rule_name,
                "%s 에 같은 오른쪽 키(%s=%s)를 쓰는 행 %d 개가 «한 배치 안»에 있어 "
                "«모두» 건너뜁니다 — 어느 쪽이 사실인지 제품이 고를 수 없습니다"
                % (table_name, ", ".join(columns),
                   ", ".join(str(v) for v in key), len(identities)),
                operator_line.fold_the_data(table_name, columns),
                named))
    # 🔴 AND NOW THE STORED HALF (2026-09-14 outage). Everything above is within ONE batch.
    # A row whose join key is already held by a DIFFERENT stored row breaks the same index,
    # is not the statement's ON CONFLICT target, and kills the whole statement - every row
    # in the file, not just the offender. Skipping the offender by name is what the owner
    # ruled ("키 중복되면 접어라") and what this function already does for its in-batch twin.
    for rule_name, columns, folds in keys:
        wanted = {}
        for index, item in enumerate(items):
            if index in refused_indexes:
                continue
            key = _folded_join_key(getattr(item, "updates", None), columns, folds, table_name)
            if key is not None:
                wanted.setdefault(key, []).append(index)
        if not wanted:
            continue
        try:
            owners = _stored_join_key_owners(db, table_name, columns, folds, wanted)
        except Exception as probe_error:
            # ⚠️ A PROBE THAT CANNOT RUN MUST NOT REFUSE. Failing open leaves today's
            # behaviour exactly as it was; failing closed would drop good rows on a
            # dialect quirk.
            logger.warning("[JoinUnique] %s: stored-key probe skipped (%s)",
                           table_name, told(probe_error))
            continue
        if not owners:
            continue
        for key, indexes in wanted.items():
            holder = owners.get(key)
            if not holder:
                continue
            held_row_id, held_bk = holder
            holder_name = held_bk or held_row_id or "(stored row)"
            for index in indexes:
                item = items[index]
                mine = str(_item_identity(item, index))
                own_row_id = getattr(item, "row_id", None)
                own_bk = getattr(item, "business_key_val", None)
                if ((own_row_id and held_row_id and str(own_row_id) == str(held_row_id))
                        or (own_bk and held_bk and str(own_bk) == str(held_bk))):
                    continue  # the same row being updated - an upsert, not a clash
                refused_indexes.add(index)
                refusals.append({
                    "reason": DROP_UNIQUE_VIOLATED,
                    "rule": rule_name,
                    "columns": list(columns),
                    "key": list(key),
                    "row": mine,
                    "others": [str(holder_name)],
                    "message": (
                        f"규칙 '{rule_name}' 의 행 {mine} 이(가) 조인 선언의 오른쪽 "
                        f"유일성({', '.join(columns)}={', '.join(str(v) for v in key)})을 "
                        f"어겨 건너뜀 — 같은 조인 키를 «이미 가진» 행: {holder_name}"),
                })
            if any(i in refused_indexes for i in indexes):
                import operator_line

                logger.warning("%s", operator_line.line(
                    "JoinUnique", rule_name,
                    "들어온 행이 %s 에 «이미 있는» 행 %s 과 같은 오른쪽 키(%s=%s)를 "
                    "들고 있어 건너뜁니다 — 나머지 행은 정상으로 써집니다"
                    % (table_name, holder_name, ", ".join(columns),
                       ", ".join(str(v) for v in key)),
                    operator_line.fold_the_data(table_name, columns),
                    [holder_name]))

    if not refused_indexes:
        return []
    batch.updates = [item for index, item in enumerate(items)
                     if index not in refused_indexes]
    return refusals


# [S-283] `refuse_virtual_join_columns` LIVED HERE, and it is gone rather than relaxed.
# It refused a write aimed at a `virtual_only` column - a column not stored on the left
# table, computed in the read payload from a verified join - because the undeclared-column
# gate would otherwise DROP it silently: 200 from the API, the client re-rendering the
# joined value, and the user's edit vanishing with no explanation. Silence was the defect.
#
# The read-time join was retired (ruling 461), so there is no column that exists only in
# the read payload and nothing is left to refuse. `collide` columns were never refused -
# they were stored columns a join also fed, and writing one was the override - and they
# are now simply stored columns.
#
# 🔴 The argument was never wrong, only its subject was withdrawn: if a future round
# computes a column at read time again, this guard comes back with it.


# [Notation normalization] `refuse_notation_derived_columns` USED TO LIVE HERE, and it
# is gone rather than relaxed. It refused a write aimed at a `<col>_norm` column
# because that column was a pure function of its raw column, so a written value would
# have survived until the raw column next changed and then vanished unexplained.
#
# User ruling 2026-08-04 withdrew the stored column entirely - and the refusal was one
# of the reasons: a column users could see and could not edit rode along in CSV
# extracts, and the moment it entered `display_columns` an incoming file with a
# matching header reached this funnel and the refusal failed the WHOLE batch. There is
# now no derived column to write to, so there is nothing to refuse; normalization is a
# query-time fold over both sides of a comparison (`notation_norm`).
#
# 🔴 If a future round ever persists a folded value anywhere, this guard comes back -
# the argument for it was never wrong, only its subject was withdrawn.


# [D3] Index name prefix written by `migrations/add_business_key_unique_index.py`.
# Duplicated as a literal rather than imported: `crud` is imported from contexts where
# `server/migrations` is not on `sys.path` (plugin shims, the watcher's own path setup),
# and an ImportError here would take down every write path to save one constant.
BK_UNIQUE_INDEX_PREFIX = "uq_bk_"

def _is_business_key_unique_violation(exc) -> bool:
    """True only for "another writer already has this business key".

    🔴 THE NARROWNESS IS THE POINT. Retrying on any `IntegrityError` would swallow a
    genuine constraint failure - a NOT NULL breach, a `cell_sources` unique collision, a
    real key conflict inside one payload - and replay it until it gave up, replacing one
    invisible failure with another. Only the constraint this lane created is recoverable
    here, because only for that one is "read what the other process wrote and merge into
    it" a correct answer.

    Two dialects are recognised on purpose. PostgreSQL is the production answer:
    SQLSTATE 23505 plus the constraint name, which is authoritative. SQLite is what the
    test suite runs, and it reports the same event as
    `UNIQUE constraint failed: <table>.business_key_val` with no code and no constraint
    name - so the column name in the message is the only signal available there. A
    detector that only understood PostgreSQL could never be exercised by a test, which
    is how untested recovery paths get shipped.
    """
    orig = getattr(exc, "orig", None)
    if orig is not None:
        if getattr(orig, "pgcode", None) == "23505":
            diag = getattr(orig, "diag", None)
            name = getattr(diag, "constraint_name", None) or ""
            return name.startswith(BK_UNIQUE_INDEX_PREFIX)
        # No pgcode: not PostgreSQL. Fall through to the message test.
    text = str(getattr(exc, "orig", exc) or exc).lower()
    return "unique" in text and "business_key_val" in text


def _violated_constraint_name(exc) -> str:
    """The constraint an `IntegrityError` names, or `""` when it names none (S-269).

    PostgreSQL is authoritative — `exc.orig.diag.constraint_name` is what the server
    itself reports. SQLite gives no field at all, only
    `UNIQUE constraint failed: <table>.<column>`, so the message's own tail is the only
    name available there; a reader that understood PostgreSQL alone could never be
    exercised by this suite, which is how untested refusal paths get shipped
    (`_is_business_key_unique_violation` is two dialects for the same reason).
    """
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if name:
        return str(name)
    text = str(orig or exc).strip().splitlines()[0] if (orig or exc) else ""
    marker = "constraint failed:"
    if marker in text:
        return text.split(marker, 1)[1].strip()
    return ""


def _say_the_constraint_refused_this_batch(table_name, batch, exc) -> None:
    """One operator line for a constraint this lane cannot recover from (S-269).

    🔴 THE ACTION IS CHOSEN, NOT GUESSED, AND ONLY WHERE THE PRODUCT KNOWS IT. An index
    this product BUILT from a declaration (`uq_vjoin_`) has one correct repair and it is
    not a data edit: retract the declaration and the product drops the index itself
    (S-248). For any other constraint the two repairs are OPPOSITE — fold the rows, or
    widen the declaration — and naming the wrong one destroys a fact, so the line says
    「가르십시오」 and points at where that is decided rather than picking.

    ⚠️ THE LINE IS THE ONLY RECORD. Production logs cannot be pasted here, so the sentence
    has to carry what an operator needs in itself: the constraint's name, how many rows the
    refused batch held, a sample, and the next action.
    """
    import operator_line
    from chain import join_key_index

    constraint = _violated_constraint_name(exc)
    samples = [item.business_key_val for item in (batch.updates or [])
               if getattr(item, "business_key_val", None) is not None]
    if constraint.startswith(join_key_index.INDEX_PREFIX):
        # ⚰️ [판정 652] 여기가 `virtual_join_rules.json` 을 «먼저» 댔다. 그 문법은 은퇴했고,
        #    이 줄은 «뭔가 깨진 순간»에 나가는 줄이라 없는 파일로 보내면 운영자가 열어 봐야
        #    고칠 것이 없다. 조인 선언이 사는 곳은 이제 하나다.
        action = operator_line.retract_the_declaration(
            "`chain_rules.json` 의 그 조인 선언")
    else:
        action = operator_line.decide_the_repair(table_name, constraint or "(이름 없음)")
    logger.error("%s", operator_line.line(
        "Ingest", table_name,
        "제약 `%s` 위반으로 이 배치(%s 행, tx %s)를 «거절»했습니다 — 세션은 되돌렸습니다"
        % (constraint or "(이름 없음)", len(batch.updates or []), batch.transaction_id),
        action, samples))


def apply_batch_updates(db: Session, table_name: str, batch: schemas.GeneralUpdateBatch,
                        replace_report: Optional[dict] = None,
                        drop_report: Optional[dict] = None,
                        notation_report: Optional[dict] = None,
                        deleted_edits: Optional[dict] = None):
    """Batch write - its cells as lines (`write_lines`, through `_apply_batch_updates_once`).

    notation_report: optional out-param (dict) - `{verdict: count}` of the time values a
    `write` column's `time` rule left as written (`notation_norm.TIME_LEFT_AS_WRITTEN`), for
    the watcher's file line (총괄 a7d2e90ec ㉯ ㄴ). Empty when nothing was left.

    drop_report: optional out-param (dict), the same shape of contract `replace_report`
    already has and for the same reason - the 4-tuple return is unpacked at ~10 production
    call sites and dozens of tests, so the detail cannot ride on the return value without
    changing every one of them. Pass a dict to learn WHAT THIS BATCH DISCARDED: which
    update keys, on which rows, and under which reason name. See `_render_drop_report`
    for the shape and `DROP_UNDECLARED_COLUMN` / `DROP_SYSTEM_COLUMN` for the vocabulary.
    Pass nothing and behaviour is byte-identical to before.

    [D3] Two writers of one new business key end on one row inside `write_lines`' claim (INSERT ... ON CONFLICT on
    the key's unique index, read back under the lock) - the replay that turned the lost race's IntegrityError into a
    merge is retired with the race (lead 11-11 ㄹ). Every IntegrityError is refused by name after a rollback.
    """
    from sqlalchemy.exc import IntegrityError

    # 🔴 A READ-ONLY RELATION IS REFUSED BY NAME (S-186, 판정 296), AND THE SENTENCE NO
    # LONGER LIVES HERE (S-224). This seat is a funnel for the CELL paths — cell edits,
    # layering, ingestion and chain writes all converge on it — but row creation, row
    # deletion and the two source controls reach the relation without passing through, so
    # 「관문이 여기 하나」 was true of this function and false of the relation.
    refuse_write_to_view(table_name)
    _fold_written_notation(db, table_name, batch, notation_report)
    if drop_report is not None:
        drop_report.clear()
    if deleted_edits is not None:
        deleted_edits.clear()
    try:
        return _apply_batch_updates_once(db, table_name, batch, replace_report, drop_report, deleted_edits)
    except IntegrityError as exc:
        # 🔴 [S-269] REFUSED BY NAME, AND AFTER A ROLLBACK - raising on an aborted transaction leaves the caller's next
        # read saying 「Instance is not bound to a Session」 instead of the constraint (owner 2026-09-16).
        from session_contract import undo_step
        undo_step(db)
        # 🔴 [S-275] the line that explains the refusal may not replace it (「진단기는 자기가 진단하는 것을 죽일 수 없다」)
        try:
            _say_the_constraint_refused_this_batch(table_name, batch, exc)
        except Exception as line_err:                          # noqa: BLE001
            logger.warning(
                "[Ingest] %s refusal line skipped (%s: %s) - the batch is still "
                "refused and the original error is raised unchanged",
                table_name, type(line_err).__name__, told(line_err))
        raise


def _fold_written_notation(db, table_name: str, batch, notation_report=None):
    """A `write` column's values are stored folded - THE seat that changes them (총괄 47aba5d44 ③).

    Once per `apply_batch_updates` call, ahead of its retry loop: a retry re-runs the same
    items, and a second fold would move again a value a non-idempotent declaration moves, and
    would lose the spelling that arrived - which the audit line keeps (5ee9d3bd1 ②). The
    replace_map scope is folded with the values, or it would scope the spelling no stored row
    has any more. A table with no `write` column reads nothing.
    """
    import notation_norm

    if not notation_norm.written_columns(table_name):
        return
    aliases = notation_norm.aliases_by_column(db)
    composite_src = TABLE_CONFIG.get(table_name, {}).get("composite_key_source")
    left = {}
    for item in batch.updates:
        raw_updates, raw_key = item.updates, item.business_key_val
        item.updates, item.business_key_val, arrived, counts = \
            notation_norm.fold_item_for_write(table_name, item.updates,
                                              item.business_key_val, aliases)
        if arrived:
            item._written_spelling = arrived
        for verdict, n in counts.items():
            left[verdict] = left.get(verdict, 0) + n
        # 총괄 3eb161a9c ②: a row stored under the raw spelling is found by it - the spelling
        # moves aside the way a supplied key does (판정 191), and the write re-keys that row.
        if composite_src:
            raw_key = (compose_business_key(table_name,
                                            [raw_updates.get(col) for col in composite_src],
                                            composite_src)
                       if any(col in arrived for col in composite_src)
                       and not _unfilled_composite_parts(composite_src, raw_updates)
                       else None)
        elif raw_key == item.business_key_val:
            raw_key = None
        if raw_key and not item._supplied_business_key_val:
            item._supplied_business_key_val = clean_str_value(raw_key)
    if batch.scope:
        batch.scope = notation_norm.fold_item_for_write(table_name, batch.scope, None,
                                                        aliases)[0]
    if notation_report is not None:
        notation_report.update(left)


#: A batch's flush past this many seconds is said with its table's indexes (owner 10-16: 1,000 rows, 20 s).
SLOW_FLUSH_SECONDS = 5.0


def _say_a_slow_flush(db, table_model, table_name, rows, seconds):
    """One line for a slow flush: its table, its rows, its indexes and how many are GIN - a GIN pending list merged by
    this write is one cause (`runtime.maintenance_line.clean_gin_pending` merges them ahead). Contained: a line."""
    if seconds < SLOW_FLUSH_SECONDS:
        return
    from sqlalchemy import text as sql_text

    try:
        relation = getattr(getattr(table_model, '__table__', None), 'name', None) or table_name
        from session_contract import in_savepoint

        # in a savepoint: a failed read rolls back to it, never the batch's transaction (QA 10-20)
        kinds = in_savepoint(db, "slow flush line", lambda: db.execute(sql_text(
            "SELECT am.amname FROM pg_index x JOIN pg_class c ON c.oid = x.indexrelid JOIN pg_am am ON am.oid = c.relam"
            " WHERE x.indrelid = to_regclass(:relation)"), {"relation": '"%s"' % relation}).scalars().all())
        said = "%d index(es), %d GIN" % (len(kinds), sum(1 for k in kinds if k == 'gin'))
    except Exception as exc:  # noqa: BLE001 - the line is said without its indexes
        said = "indexes unread: %s: %s" % (type(exc).__name__, told(exc))
    logger.warning("[Batch] slow flush: %s %d row(s) in %.1f s - %s", table_name, rows, seconds, said)


def _apply_batch_updates_once(db: Session, table_name: str,
                              batch: schemas.GeneralUpdateBatch,
                              replace_report: Optional[dict] = None,
                              drop_report: Optional[dict] = None,
                              deleted_edits: Optional[dict] = None):
    """통합 업데이트를 배치로 처리합니다.

    replace_report: optional out-param (dict). When batch.replace_map is set and a dict
    is passed, it is filled with {"filters": <scope dict>, "deleted": <purged row count>}
    so the API layer can report the exact purge honestly without changing this
    function's widely-unpacked 4-tuple return signature (worker/parser/test call sites).

    drop_report: optional out-param (dict) with the same contract - see
    `apply_batch_updates`, which owns it and clears it per attempt.
    """
    # ⚰️ [S-283] A BATCH AIMED AT A VIRTUAL-JOIN COLUMN WAS REFUSED HERE, whole, ahead
    # of transaction_context and ahead of the replace_map purge. The refusal is gone with
    # its subject: read-time joins are retired, so no column is computed at read time and
    # every name in a payload is either a stored column or already dropped by the
    # undeclared-column gate in `apply_row_update_internal`.

    tx_id = batch.transaction_id or str(uuid6.uuid7())
    
    user_val = batch.updates[0].updated_by if batch.updates else "system"
    source_val = batch.updates[0].source_name if batch.updates else "batch"
    
    with transaction_context(user_val, tx_id, source_val):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")

        # [adopt] Row ids inside the scope a replace_map write declares. Empty for every
        # other write path, which is what makes the adoption check below a no-op there.
        replace_scope_row_ids = set()
        # a map replace on a version-gated table: the map judged whole, its rows not asked again (map_version_verdict)
        map_judged, map_note = False, None

        if batch.replace_map:
            # [U6] The purge scope comes from ONE shared resolver (also called by the API
            # layer to echo the scope in the response). No resolvable scope = honest 4xx
            # refusal instead of the historical silent 200-noop that deleted nothing and
            # let map rows accumulate. An explicit batch.scope with an empty payload is
            # the legitimate erase-all of that scope.
            scope_filters = derive_replace_map_scope(table_name, batch)
            if not scope_filters:
                raise ValueError(
                    f"replace_map on '{table_name}' could not derive a purge scope: "
                    f"declare 'map_key_columns' in table_config and send their values in the "
                    f"payload (or pass an explicit 'scope' object). Refusing instead of "
                    f"silently replacing nothing."
                )

            meta_conditions = [
                getattr(table_model, col_name) == col_val
                for col_name, col_val in scope_filters.items()
            ]

            from sqlalchemy import and_
            _cfg = TABLE_CONFIG.get(table_name, {})
            map_version_col = _cfg.get("version_column")
            # locked as read, row_id order - the purge or the diff compares against them (총괄 09f58844f ②)
            matching_rows = db.query(table_model.row_id, *([getattr(table_model, map_version_col)] if map_version_col
                                                           else [])).filter(and_(*meta_conditions)) \
                .order_by(table_model.row_id).with_for_update().all()
            purged_row_ids = [r[0] for r in matching_rows if r[0]]
            # 🔴 The map is one version (소유자 10-21): judged here, before the purge or the diff deletes anything.
            #    Refused, the map is neither written nor deleted - the VersionGate line says it in its words.
            map_applied, map_note = map_version_verdict(
                _cfg, batch.updates, [r[1] for r in matching_rows] if map_version_col else [],
                lambda: _map_unchanged(db, table_name, _cfg, batch.updates, purged_row_ids))
            if not map_applied:
                log_version_gate_summary(table_name, map_version_col, source_val,
                                         {"rows": len(batch.updates), "counts": {map_note: len(batch.updates)}})
                if replace_report is not None:          # a map the same as stored is left, not refused
                    replace_report.update(filters=scope_filters, deleted=0, in_scope=len(purged_row_ids), reason=map_note,
                                          mode=NOTE_MAP_UNCHANGED if map_note == NOTE_MAP_UNCHANGED else "refused")
                from session_contract import end_step
                end_step(db)
                return [], [], [], []
            map_judged = bool(map_version_col and batch.updates)

            # [scope diff] Only a DECLARED scope may be diffed.
            #
            # The legacy derivation (no `map_key_columns`) builds its filters from every
            # non-coordinate column of `updates[0]`, so the scope it resolves can be far
            # NARROWER than the map - it matches only rows identical to the first payload
            # row in all of those columns. A diff decides what disappeared by subtracting
            # the rows it wrote from the rows in scope, so a scope narrower than the map
            # would report a genuine surviving cell as "still there" while a second push
            # inserted a duplicate beside it. Wrong data, quietly. The purge does not have
            # that failure mode, because it only ever deletes what it can see.
            #
            # So the branch that cannot resolve the true scope keeps the behaviour it has
            # today, and the reason travels in the response rather than being inferred
            # from an absence of improvement.
            # [scope diff] The SECOND requirement, and it is not cosmetic: the diff must
            # be able to RESOLVE an incoming cell onto the row it already has. That
            # resolution is `assemble_composite_business_key`. A plain key in the payload
            # was not matched at all until 총괄 5c0a86cec (every push a fresh row); it is
            # now, but the diff stays on composite-keyed maps - all seven shipped map
            # tables declare one, so this excludes no real map.
            use_diff = bool(_cfg.get("map_key_columns")) and bool(_cfg.get("composite_key_source"))
            # 🔴 소유자 10-24 «그냥 소스 통째로 걷기로 했잖아» · «기존 맵 아예 지우고 하니 제대로 들어옴»: a FILE that
            #    replaces its maps purges each map whole - every row, every source's layer (the chain's too) - and
            #    writes the file. The diff kept re-sent rows with their chain layers, which outrank every file.
            if getattr(batch, "_file_replace", False):
                use_diff = False


            # [adopt] The ids this write DECLARED it was operating on - the whole scope,
            # whether or not it is about to be purged. Both the removal set and the
            # adoption set are computed against THIS, so it is captured before the purge
            # branch below is allowed to empty its own working list.
            replace_scope_row_ids = set(purged_row_ids)

            if use_diff:
                # Nothing is deleted here. The rows in scope stay, the write loop below
                # resolves the ones the payload still claims, and whatever it did not
                # claim is removed after the loop - see [scope diff] there.
                purged_row_ids = []

            purged_keys = []
            if purged_row_ids:
                # One helper for both purge sites, so the outbox event cannot be added to
                # one branch and forgotten on the other. See `purge_map_rows`.
                purge_map_rows(db, table_model, table_name, purged_row_ids, said=purged_keys)
                db.flush()

            if replace_report is not None:
                replace_report["filters"] = scope_filters
                # On the diff path this is filled in AFTER the loop, once the set of rows
                # the payload did not claim is known. Seeded here so a caller never reads
                # a missing key as zero.
                replace_report["deleted"] = len(purged_row_ids)
                # [adopt] Which resolver produced `filters`, and therefore which strategy
                # this write is allowed to use. `legacy_column_derivation` is the honest
                # answer to "why did this table not get the diff".
                replace_report["mode"] = "diff" if use_diff else "purge"
                replace_report["in_scope"] = len(replace_scope_row_ids)
                replace_report["reason"] = (
                    "declared_map_key_columns" if use_diff
                    else "file_replace" if getattr(batch, "_file_replace", False)
                    else "legacy_column_derivation" if not _cfg.get("map_key_columns")
                    else "unresolvable_row_identity"
                )

            logger.info(
                f"🔄 [Map Replace Executed] Table: '{table_name}' | TX: {tx_id} | "
                f"Mode: {'diff' if use_diff else 'purge'} | Filters: {scope_filters} | "
                f"Rows In Scope: {len(replace_scope_row_ids)} | "
                f"Purged Old Rows: {len(purged_row_ids)}{' (%s)' % purged_keys[0] if purged_keys else ''} | "
                f"Incoming Active Cells: {len(batch.updates)}"
            )

        # [P6] Assemble the composite business key for every item BEFORE the prefetch
        # filter is built from it.
        #
        # The key of a map row is a join of its own column values (`composite_key_source`
        # - 11 of the 14 real tables declare one, including every map table). The payload
        # a map push sends carries neither `row_id` nor `business_key_val`: it carries the
        # source columns. The assembly used to happen inside `apply_row_update_internal`,
        # i.e. per row and AFTER `target_bks` had already been collected - so `target_bks`
        # was empty, the prefetch below matched nothing, `row_cache` stayed empty, and
        # `_get_or_create_row` fell through to one full-model SELECT per row. Measured on
        # a 200-cell update: 201 SELECTs on the data table where 1 is enough.
        #
        # ⚠️ THIS MOVES WHEN THE KEY IS COMPUTED, NOT WHAT IT IS. Same function and the
        # same two side effects. The GUARD has since narrowed to `row_id` alone (판정 190)
        # and a supplied key that differs from the assembled one is now kept aside rather
        # than overwritten (판정 191) - both of which this block reads, never decides.
        #
        # ⚠️ AND IT DOES NOTHING FOR A `replace_map` PUSH - which is what the map editor
        # sends. The purge above already deleted the scope's rows and flushed, so the
        # prefetch looks up keys whose rows no longer exist, finds nothing, and
        # `_get_or_create_row` probes for each of them anyway. Measured: 202 SELECTs
        # before, 202 after, at 200 cells. This helps the paths that UPDATE existing
        # composite-keyed rows - grid edits, file re-ingestion, chain writes, enrichment
        # - where the same 200-cell batch goes from 2,604 statements to 406.
        # Closing the insert case needs a business-key equivalent of
        # `layers_read`: the prefetch PROVES those rows are absent, and
        # `_get_or_create_row` does not read that proof. That is a separate correctness
        # argument and is deliberately not made here.
        #
        # ⚠️ AND IT MUST STAY BELOW THE replace_map BLOCK. The assembly writes the key
        # into `updates[key_col]`, and `derive_replace_map_scope`'s legacy branch builds
        # the purge filters from every non-coordinate column present in the first payload
        # row - the business key column included. Hoisting this above the purge would turn
        # "delete this map" into "delete this one die". Here, the resolver sees exactly
        # the payload it saw before.
        # A time PostgreSQL reads and our reader does not («2026/10/29») goes on as PostgreSQL's moment on
        # expression_time_zone (lead 10-31) - not in a key column: its spelling is the row's identity (owner 10-21 «키 칸은
        # 시간 절대 안 쓰는 걸로», 총괄 d5cf3a954), and an old table's key column keeps the text it came as.
        from chain.cell_layer import key_columns

        refused_times, read_times = times_the_database_refuses(db, table_name, batch.updates)
        read_times = {column: readings for column, readings in read_times.items()
                      if column not in key_columns(table_name)}
        for item in batch.updates:
            for column, readings in read_times.items():
                value = item.updates.get(column)
                if value is not None and str(value).strip() in readings:
                    item.updates[column] = readings[str(value).strip()].isoformat()
        fill_nokey_keys(table_name, batch)
        for item in batch.updates:
            assemble_composite_business_key(table_name, item)

        # [S-174] Two rows claiming one virtual join's right-side key are refused BY NAME
        # and the rest of the batch is written. BELOW the assembly because the refusal
        # names each row by its identity and a composite key does not exist until here;
        # ABOVE the prefetch so the refused rows are not looked up on their way out.
        vjoin_refusals = refuse_virtual_join_duplicates(db, table_name, batch)
        if vjoin_refusals and not batch.updates and batch.replace_map:
            # 🔴 EVERY row was refused ON A `replace_map` PUSH, and the purge above has
            # already run. Carrying on would leave the map EMPTY - the scope's rows
            # deleted and nothing replacing them - which is the same ruling the key gate
            # made for its own whole-batch refusal ("actively destructive"). It cannot
            # skip the write the way the gate does, because the gate runs before the
            # purge and this runs after, so it raises: `transaction_context` unwinds and
            # the map is left exactly as it was.
            raise ValueError(
                f"All {len(vjoin_refusals)} row(s) sent to '{table_name}' break the join declaration's right-side "
                f"uniqueness, so none can be written. The whole request was cancelled so the map is not emptied. "
                + " / ".join(r.get("message", "") for r in vjoin_refusals[:3]))

        # 🔴 THE CELLS GO IN AS LINES (cell-source overhaul, lead 11-10 ㄱ): each item is judged here as it always was
        #    (`update_item_as_line` - system, undeclared, unmapped, refused, a blank its writer cannot mean emptied) and
        #    written by `write_lines` in one call - it claims the rows (new keys under ON CONFLICT, so two writers of a
        #    new key end on one row), judges the version, leaves out what changes nothing, writes the lines, the marks
        #    and the pins, merges t again and stages the events. Its `items` answer names each item's row - what the
        #    map diff, the drop report and the phantom-row guard below read.
        from database.write_lines import write_lines

        version_col = TABLE_CONFIG.get(table_name, {}).get("version_column")
        version_stats = {"rows": len(batch.updates)} if version_col else None
        if map_note is not None and version_stats is not None:
            version_stats["counts"] = {map_note: len(batch.updates)}
        drop_stats = _new_drop_stats()
        # Whole rows refused before the write, by name - not cell drops, they ride beside the cell accounting.
        drop_stats["row_refusals"] = vjoin_refusals
        _refuse_two_values_in_one_answer(table_name, batch.updates, drop_stats)
        plan = {"loadable": frozenset(loadable_columns(TABLE_CONFIG.get(table_name, {}))), "unmapped": {},
                "map_judged": map_judged, "receipts": {}, "refused_times": refused_times}
        alignment_batch_counts.write_count("cells offered", sum(len(item.updates) for item in batch.updates),
                                           "cells offered")
        with alignment_batch_counts.write_step("row build", unit="cells changed") as count:
            said = [update_item_as_line(table_name, item, plan, drop_stats, bool(batch.replace_map))
                    for item in batch.updates]
            answer = write_lines(db, table_name, [it for it, _formulas in said], kind="funnel",
                                 transaction_id=tx_id)
            resolved = answer["items"]
            total_changed_cells = _changed_cells(answer, resolved)
            count(len(total_changed_cells))

        # an item's row: a new one, one that changed, one only named (left out, refused by its version)
        unique_results, rows_with_content = {}, set()
        for got in resolved:
            if got["row_id"] is None:
                continue
            unique_results[got["row_id"]] = unique_results.get(got["row_id"], False) or got["work"] == "new"
            if got["work"] not in ("left_out", "gated"):
                rows_with_content.add(got["row_id"])
        if version_stats is not None and answer["gated"]:
            counts = version_stats.setdefault("counts", {})
            for reason, n in answer["gated"].items():
                counts[reason] = counts.get(reason, 0) + n
        for (_it, formulas), got in zip(said, resolved):
            for label in formulas:
                if got["row_id"] is not None:
                    plan["receipts"][label]["row_ids"].append(got["row_id"])

        # [phantom row] An item whose every cell was dropped makes no row (write_lines claims none for a write of
        # nothing) - said here by the name it came with, never silently. A row it names that is there stays named.
        names = [item.row_id or item.business_key_val for item in batch.updates]
        dropped_rows = {got["row_id"] for name, got in zip(names, resolved)
                        if name in drop_stats["rows_with_drops"] and got["row_id"] is not None}
        suppressed_row_ids = [name for name, (it, _f), got in zip(names, said, resolved)
                              if name in drop_stats["rows_with_drops"] and got["row_id"] is None and not it["values"]]
        if suppressed_row_ids:
            logger.warning(
                f"[Schema] Table: '{table_name}' | TX: {tx_id} | "
                f"{len(suppressed_row_ids)} row(s) were NOT created because every update "
                f"key they carried was dropped - the columns are not declared in "
                f"column_types (or are write-path system columns). Nothing was written "
                f"for them and no CREATE was announced. Dropped column(s): "
                f"{sorted(drop_stats['by_column'])[:8]}. Fix "
                f"config/table_config.json or the sender's column names."
            )
        if version_stats is not None:
            log_version_gate_summary(table_name, version_col, source_val, version_stats)
        # 🔴 판정 207 - the rows in the answer only because something was dropped: computed once, read twice.
        reported_only_for_drops = {r for r in dropped_rows
                                   if r in unique_results and not (unique_results[r] or r in rows_with_content)}
        if drop_report is not None:
            _render_drop_report(drop_report, table_name, drop_stats, version_stats, suppressed_row_ids,
                                reported_only_for_drops=len(reported_only_for_drops))
        refused_cells = drop_stats["by_reason"].get(DROP_VALUE_REFUSED)
        if refused_cells:
            logger.warning("[Write] %s: %d cell(s) refused - %s - not entered, the rest of each row written",
                           table_name, refused_cells, "; ".join(
                               "%s=%d (first %r)" % (column, seen["cells"], seen["first"])
                               for column, seen in sorted(drop_stats["refused_values"].items())))
        receipts = []
        for label, tally in plan["receipts"].items():
            if tally["blank"] or tally["refused"]:
                logger.info("[Formula] %s: %d blank answer(s), %d not of the column's type - written blank",
                            label, tally["blank"], tally["refused"])
            if tally["row_ids"]:
                receipts.extend(receipt_log(
                    db, table_name, str(uuid6.uuid7()), label, {"blank": tally["blank"], "refused": tally["refused"]},
                    CHAIN_SOURCE, tally["who"] or "system", tx_id, row_ids=tally["row_ids"]))
        with alignment_batch_counts.write_step("audit logs") as count:
            if receipts:
                bulk_insert_audit_logs(db, receipts)
            count(len(receipts))

        deleted_row_ids = []
        # [scope diff] What disappeared: the scope MINUS what this write claimed - every row an item resolved to,
        # the unchanged ones included (an unchanged re-push claims its rows; reading «changed» here would purge them).
        if batch.replace_map and use_diff:
            removed_row_ids = [r for r in replace_scope_row_ids if r not in unique_results]
            removed_keys = []
            if removed_row_ids:
                _write_deleted_edits(db, table_name, removed_row_ids, deleted_edits)     # before they go
                purge_map_rows(db, table_model, table_name, removed_row_ids, said=removed_keys)
            if replace_report is not None:
                replace_report["deleted"] = len(removed_row_ids)
            deleted_row_ids = removed_row_ids
            logger.info(
                f"🔄 [Map Diff] Table: '{table_name}' | TX: {tx_id} | "
                f"In Scope: {len(replace_scope_row_ids)} | Claimed: {len(unique_results)} | "
                f"Written: {len(rows_with_content)} | "
                f"Removed: {len(removed_row_ids)}{' (%s)' % removed_keys[0] if removed_keys else ''}"
            )

        # [adopt] Rows written from outside the scope a replace_map declared - read before the commit, said after.
        adopted_row_ids = ([r for r, was_new in unique_results.items() if not was_new and r not in replace_scope_row_ids]
                           if batch.replace_map else [])
        if adopted_row_ids:
            _write_deleted_edits(db, table_name, adopted_row_ids, deleted_edits)

        from session_contract import end_step
        end_step(db)                # a commit, or a held group's step (총괄 09f58844f)
        from admin.audit_cache import audit_cache
        audit_cache.add_changed(answer["audit"])   # this process's history list at once (a worker's is not loaded)

        if batch.replace_map:
            if replace_report is not None:
                replace_report["adopted"] = len(adopted_row_ids)
                replace_report["adopted_row_ids"] = adopted_row_ids
            if adopted_row_ids:
                logger.warning(
                    f"⚠️ [Map Replace Adopted] Table: '{table_name}' | TX: {tx_id} | "
                    f"Filters: {scope_filters} | Rows written from OUTSIDE this scope: "
                    f"{len(adopted_row_ids)} | first: {adopted_row_ids[:5]}"
                )
            # adopted rows left the map they belonged to: announced as departures, kept apart in adopted_row_ids
            deleted_row_ids = list(deleted_row_ids) + adopted_row_ids

        # 🔴 판정 187 ④ / 192 / 207: the answer holds a row this request made, changed, or only dropped cells on -
        # an unchanged save has no item. The rows are read once, as t holds them now.
        shown = [r for r, was_new in unique_results.items()
                 if was_new or r in rows_with_content or r in reported_only_for_drops]
        rows = {}
        for page in [shown[at:at + 1000] for at in range(0, len(shown), 1000)]:
            for row in (db.query(table_model).filter(table_model.row_id.in_(page))
                        .execution_options(populate_existing=True)):
                rows[row.row_id] = row
        results = [(rows[r], unique_results[r]) for r in shown if r in rows]
        serialized_logs = _said_logs(table_name, answer, resolved, said, tx_id, rows)
        return results, total_changed_cells, serialized_logs, deleted_row_ids

def _changed_cells(answer, resolved) -> list:
    """(row_id, column) of each cell a funnel write moved - a new row's every column its items named, an edited row's
    columns whose value t shows now differs from before (a pin taken off moves cells no item named). From
    `write_lines`' answer - what the API counts, the worker reads for written blanks and the watcher tallies."""
    named = {}
    for got in resolved:
        if got["row_id"] is not None and got["work"] not in (None, "left_out", "gated"):
            named.setdefault(got["row_id"], set()).update(got["columns"])
    out = []
    for row_id, change in answer["changed"].items():
        if change["new"] is None:
            continue
        if change["work"] == "new":
            out.extend((row_id, c) for c in sorted(named.get(row_id, ())))
        else:
            old = change["old"] or {}
            out.extend((row_id, c) for c in sorted(change["new"]) if old.get(c) != change["new"][c])
    return out


def _said_logs(table_name, answer, resolved, said, transaction_id, rows) -> list:
    """The funnel's `serialized_logs` - the broadcast's payload, not the audit (lead 11-11 ㄱ1; the audit is
    `audit_batches`, written by write_lines): a person's write a line per cell it moved, any other writer one
    ROW_UPDATE line a row, today's shapes, `old_value` empty. A column of no history is not named
    (`keeps_history`). A value is cut to the audit cap as the audit line cut it (`truncate_audit_value`)."""
    from datetime import datetime

    from event_constants import truncate_audit_value

    def clip(value):
        return truncate_audit_value(value)[0]

    at = datetime.now().isoformat()
    who = {}
    for (it, _formulas), got in zip(said, resolved):
        if got["row_id"] is not None and got["work"] not in (None, "left_out", "gated"):
            who[got["row_id"]] = (it.get("source_name"), it.get("written_by"))
    out = []
    for row_id, change in answer["changed"].items():
        if change["new"] is None:
            continue
        old, new, is_new = change["old"] or {}, change["new"], change["work"] == "new"
        cols = [c for c in sorted(new) if keeps_history(table_name, c)
                and ((new[c] is not None) if is_new else old.get(c) != new[c])]
        if not cols:
            continue
        source, by = who.get(row_id, (None, None))
        row = rows.get(row_id)
        line = {"id": 0, "table_name": table_name, "row_id": row_id, "old_value": None, "source_name": source,
                "transaction_id": transaction_id, "timestamp": at,
                "business_key": getattr(row, "business_key_val", None)}
        if source == "user":
            out.extend(dict(line, column_name=c, new_value=clip(new[c]), updated_by=by or "user") for c in cols)
        else:
            parts = ", ".join("%s: %s" % (c, "empty" if new[c] is None else clip(new[c])) for c in cols)
            out.append(dict(line, column_name="ROW_UPDATE", new_value=clip(("New row: " + parts) if is_new else parts),
                            updated_by=by or "system"))
    return out


def create_empty_row(db: Session, table_name: str):
    """신규 빈 행을 하나 생성합니다."""
    new_rows = create_empty_rows_batch(db, table_name, 1)
    return new_rows[0] if new_rows else None

def create_empty_rows_batch(db: Session, table_name: str, count: int, user_name: str = "system"):
    """신규 빈 행을 일괄 생성하고 요약 히스토리를 남깁니다."""
    # ⛔ A VIEW FIRST. Without this the owner's add-row button reached
    # `table_model(row_id=…)` and answered 500 (S-224).
    refuse_write_to_view(table_name)

    from sqlalchemy.sql import func
    
    tx_id = str(uuid6.uuid7())
    
    with transaction_context(user_name, tx_id, "batch_create"):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
            
        new_rows = []
        for _ in range(count):
            row = table_model(
                row_id=str(uuid6.uuid7()),
                updated_at=func.now()
            )
            new_rows.append(row)
        
        db.add_all(new_rows)
        
        logs_to_cache = []
        if count > 0:
            for row in new_rows:
                log_dict = create_audit_log(
                    db, table_name, row.row_id, "CREATE",
                    None, "row created", "system", user_name,
                    transaction_id=tx_id,
                    business_key=row.business_key_val,
                    add_to_cache=False
                )
                logs_to_cache.append(log_dict)

        if logs_to_cache:
            bulk_insert_audit_logs(db, logs_to_cache)

        db.commit()

        return new_rows

def delete_row(db: Session, table_name: str, row_id: str, user_name: str):
    """단일 행을 삭제합니다 (배치 로직으로 통합).

    🔴 [판정 431] `user_name` HAS NO DEFAULT, AND THAT IS THE FIX. It defaulted to `"system"`,
    and the only caller that relied on it was a public route with no author parameter - so a
    person's deletion was recorded as the system's. A default cannot say 「모른다」; it can only
    say a name, and any name it says is wrong when nobody gave one. The caller that does not
    know now has to write that down (`event_constants.AUTHOR_NOT_STATED`).
    """
    return delete_rows_batch(db, table_name, [row_id], user_name) > 0

#: The column a row's deletion history line names - what 「this row was deleted」 is read by.
ROW_DELETION_COLUMN = "DELETE"


def deleted_rows(db: Session, table_name: str, row_ids) -> set:
    """The rows among `row_ids` that have a deletion history line (`record_row_deletions` - the grid's
    delete, the map purge and the job retraction all write one): gone, not unreadable (총괄 10-09,
    S-158 widened) - a «deleted» line (cell-source overhaul), asked by the (row_id, at) index's lead."""
    from admin import audit_history

    return audit_history.deleted_line_rows(db, table_name, row_ids)


def record_row_deletions(db: Session, table_name: str, rows, user_name: str,
                         transaction_id: str):
    """The audit history for rows that are going away — ONE place, two callers.

    🔴 THE TWO DELETION PATHS WROTE DIFFERENT HISTORY, AND ONLY ONE WROTE ANY.
    `delete_rows_batch` recorded every row it removed; `purge_map_rows` recorded none, so
    「what was deleted?」 had an answer for one kind of deletion and not for the other. The
    rows are gone either way — what went missing was the place to ask.

    ⚠️ IT WRITES TO THE LEDGER TABLE, NOT TO THE IN-MEMORY CACHE. The cache is a
    post-COMMIT concern and this function does not own the commit: `delete_rows_batch`
    commits and then publishes, while the map purge runs inside a batch that commits later.
    Publishing here would put entries in the cache for a transaction that can still roll
    back. Callers that own a commit publish the returned dicts themselves.

    Returns the log dicts so a caller can do exactly that.
    """
    logs = []
    for row in rows or []:
        logs.append(create_audit_log(
            db, table_name, row.row_id, ROW_DELETION_COLUMN,
            None, "row deleted", "system", user_name,
            transaction_id=transaction_id,
            business_key=getattr(row, "business_key_val", None),
            add_to_cache=False))
    if logs:
        bulk_insert_audit_logs(db, logs)
    return logs


def delete_row_layers(db: Session, table_name: str, row_ids: list) -> None:
    """Rows' cell layers and overwrite marks, gone with the rows - the one place a row's metadata
    is deleted: a row delete, a map purge, and a merge's stored shell (총괄 a13fcf00c)."""
    db.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).delete(synchronize_session=False)
    db.query(models.CellSource).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id.in_(row_ids)
    ).delete(synchronize_session=False)


def delete_rows_batch(db: Session, table_name: str, row_ids: list[str], user_name: str):
    """여러 행을 일괄 삭제하고 개별 히스토리를 남기며 메타데이터도 연쇄 삭제합니다."""
    # ⛔ A VIEW FIRST — and BEFORE the empty-list shortcut, so the answer does not depend
    # on what the caller sent. This path deletes the row's cell layers before it touches the
    # relation, so on a view that declares `row_id` it destroyed metadata and only then let
    # PostgreSQL refuse (S-224).
    refuse_write_to_view(table_name)

    if not row_ids:
        return 0
        
    tx_id = str(uuid6.uuid7())
    
    with transaction_context(user_name, tx_id, "batch_delete"):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
            
        # 삭제하기 전 row_id와 business_key_val을 먼저 조회
        rows_to_delete = db.query(table_model).filter(
            table_model.row_id.in_(row_ids)
        ).all()
            
        # 메타데이터 연쇄 삭제
        delete_row_layers(db, table_name, row_ids)

        # 기본 데이터 삭제
        deleted_count = db.query(table_model).filter(
            table_model.row_id.in_(row_ids)
        ).delete(synchronize_session=False)
                
        if deleted_count > 0:
            # 🔴 THE DELETE DOOR HAD TO BE TOLD (S-74). A bulk
            # `.delete(synchronize_session=False)` never puts the objects in
            # `session.deleted`, so the `before_flush` hook that stages every other write
            # cannot see them: measured 2026-09-08, this box's whole outbox history holds
            # 1,618 CREATE, one RETROACTIVE_RUN and ZERO DELETE, while an EDIT of the same
            # row stages normally. Everything downstream of the outbox -- the chain, and the
            # ledger's follow-up that withdraws a deleted row's facts -- had therefore never
            # once received a live deletion.
            #
            # ⚠️ THE SAME CALL `purge_map_rows` ALREADY MAKES, not a second spelling of it.
            # And it stages the ids that were actually removed rather than the ids asked
            # for, so a delete of something already gone does not announce a deletion.
            from database.database import row_values, stage_collapsed_event

            # with each row's values as its old values (총괄 옛 키)
            stage_collapsed_event(
                db, "DELETE", table_name, [row.row_id for row in rows_to_delete],
                old=[row_values(row) for row in rows_to_delete])
            logs_to_cache = record_row_deletions(
                db, table_name, rows_to_delete, user_name, tx_id)
            from session_contract import end_step
            end_step(db)

            
        return deleted_count

def get_row_cell(db: Session, table_name: str, row_id: str):
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return None
    return db.query(table_model).filter(table_model.row_id == row_id).first()


def delete_cell_source_batch(db: Session, table_name: str, cells: list[dict], source_name: str):
    """여러 셀의 특정 데이터 원천(Source)을 일괄 삭제합니다."""
    # ⛔ A VIEW FIRST. `delete_cell_source` delegates here, so the single-cell control is
    # gated by this one line too (S-224).
    refuse_write_to_view(table_name)

    if not cells:
        return [], []

    row_ids = list(set(c["row_id"] for c in cells))
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return [], []
        
    rows = db.query(table_model).filter(table_model.row_id.in_(row_ids)).all()
    row_map = {r.row_id: r for r in rows}

    # 1. 특정 소스 일괄 삭제 실행 (동일 트랜잭션 내)
    from sqlalchemy import and_, or_
    delete_conds = []
    for item in cells:
        delete_conds.append(
            and_(
                models.CellSource.table_name == table_name,
                models.CellSource.row_id == item["row_id"],
                models.CellSource.column_name == item["column_name"],
                models.CellSource.source_name == source_name
            )
        )
    db.query(models.CellSource).filter(or_(*delete_conds)).delete(synchronize_session=False)

    # 2. 캐시 일괄 생성 (N+1 SELECT 차단)
    # [ORDER BY source_name] Same reason as `_load_metadata_row_cell`: this list feeds
    # `compute_priority_value`, so its order is stated rather than inherited from the heap.
    all_sources = db.query(
        models.CellSource.table_name,
        models.CellSource.row_id,
        models.CellSource.column_name,
        models.CellSource.source_name,
        models.CellSource.value,
        models.CellSource.updated_by,
        models.CellSource.ingested_at,
        models.CellSource.origin_row_id
    ).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id.in_(row_ids)
    ).order_by(models.CellSource.source_name.asc()).all()
    
    sources_cache = {}
    for t_name, r_id, col_name, src_name, val, upd_by, ing_at, origin in all_sources:
        key = (r_id, col_name)
        if key not in sources_cache:
            sources_cache[key] = []
        sources_cache[key].append(LightCellSource(t_name, r_id, col_name, src_name, val, upd_by, ing_at, origin))

    all_overwrites = db.query(
        models.CellOverwrite.table_name,
        models.CellOverwrite.row_id,
        models.CellOverwrite.column_name,
        models.CellOverwrite.is_overwrite,
        models.CellOverwrite.updated_by,
        models.CellOverwrite.updated_at,
        models.CellOverwrite.manual_priority_source
    ).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).all()
    
    overwrites_cache = {}
    for t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin in all_overwrites:
        overwrites_cache[(r_id, col_name)] = LightCellOverwrite(t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin)

    # 3. 인메모리 비교 루프 실행
    changed_rows = []
    tx_id = str(uuid6.uuid7())
    logs_to_cache = []
    
    cell_overwrites_to_upsert = {}
    cell_overwrites_to_delete = set()

    for item in cells:
        r_id = item["row_id"]
        col_name = item["column_name"]
        row = row_map.get(r_id)
        if not row:
            continue

        key = (r_id, col_name)
        col_srcs = sources_cache.get(key, [])
        ow = overwrites_cache.get(key)

        manual_pin = ow.manual_priority_source if ow else None
        if manual_pin == source_name:
            manual_pin = None
            if ow:
                ow.manual_priority_source = None

        sources_dict = {
            s.source_name: {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else None,
                "updated_by": s.updated_by
            }
            for s in col_srcs
        }

        old_val = getattr(row, col_name, None)
        new_val, top_src = compute_priority_value(sources_dict, manual_pin, table_name, cell=(table_name, col_name, row))
        moved = values_differ(old_val, new_val, (TABLE_CONFIG.get(table_name, {}).get(
            "column_types") or {}).get(col_name, "string"))
        if moved:                       # the value it already shows is not written again - no event (총괄 f5ff1e3e9)
            setattr(row, col_name, new_val)

        is_overwrite = ("user" in sources_dict) or (manual_pin is not None)
        ow_key = (table_name, r_id, col_name)
        if is_overwrite:
            ow_updated_by = ow.updated_by if ow else "system"
            ow_updated_at = ow.updated_at if ow else datetime.now()
            cell_overwrites_to_upsert[ow_key] = {
                "table_name": table_name,
                "row_id": r_id,
                "column_name": col_name,
                "is_overwrite": True,
                "updated_by": ow_updated_by,
                "updated_at": ow_updated_at,
                "manual_priority_source": manual_pin
            }
            cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                cell_overwrites_to_delete.add(ow_key)
                cell_overwrites_to_upsert.pop(ow_key, None)

        if moved:
            log_dict = create_audit_log(
                db, table_name, r_id, col_name, old_val, new_val,
                f"delete_source:{source_name}", "system",
                transaction_id=tx_id, business_key=row.business_key_val,
                add_to_cache=False
            )
            if log_dict is not None:
                logs_to_cache.append(log_dict)

        if row not in changed_rows:
            changed_rows.append(row)

    # 4. 벌크 갱신 및 삭제
    if logs_to_cache:
        bulk_insert_audit_logs(db, logs_to_cache)
    bulk_upsert_cell_overwrites(db, list(cell_overwrites_to_upsert.values()))
    bulk_delete_cell_overwrites(db, list(cell_overwrites_to_delete))

    db.commit()

    serialized_logs = []
    for log in logs_to_cache:
        log_copy = log.copy()
        if isinstance(log_copy.get("timestamp"), datetime):
            log_copy["timestamp"] = log_copy["timestamp"].isoformat()
        serialized_logs.append(log_copy)

    return changed_rows, serialized_logs

def delete_cell_source(db: Session, table_name: str, row_id: str, col_name: str, source_name: str):
    """특정 소스의 데이터를 삭제하고 값을 재계산합니다."""
    changed_rows, logs = delete_cell_source_batch(db, table_name, [{"row_id": row_id, "column_name": col_name}], source_name)
    return changed_rows[0] if changed_rows else None, [col_name] if logs else []

def set_cell_manual_priority_batch(db: Session, table_name: str, updates: list[dict], source_name: Optional[str], updated_by: str = "user",
                                   deleted_edits: Optional[dict] = None):
    """여러 셀의 표시 우선순위 소스를 수동으로 일괄 지정합니다 (Pin)."""
    # ⛔ A VIEW FIRST. `set_cell_manual_priority` delegates here (S-224).
    refuse_write_to_view(table_name)

    if not updates:
        return [], []

    row_ids = list(set(u["row_id"] for u in updates))
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return [], []
        
    rows = db.query(table_model).filter(table_model.row_id.in_(row_ids)).all()
    row_map = {r.row_id: r for r in rows}

    # 1. 인메모리 캐시 일괄 조회 및 적재
    # [ORDER BY source_name] Same reason as `_load_metadata_row_cell`: this list feeds
    # `compute_priority_value`, so its order is stated rather than inherited from the heap.
    all_sources = db.query(
        models.CellSource.table_name,
        models.CellSource.row_id,
        models.CellSource.column_name,
        models.CellSource.source_name,
        models.CellSource.value,
        models.CellSource.updated_by,
        models.CellSource.ingested_at,
        models.CellSource.origin_row_id
    ).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id.in_(row_ids)
    ).order_by(models.CellSource.source_name.asc()).all()
    
    sources_cache = {}
    for t_name, r_id, col_name, src_name, val, upd_by, ing_at, origin in all_sources:
        key = (r_id, col_name)
        if key not in sources_cache:
            sources_cache[key] = []
        sources_cache[key].append(LightCellSource(t_name, r_id, col_name, src_name, val, upd_by, ing_at, origin))

    all_overwrites = db.query(
        models.CellOverwrite.table_name,
        models.CellOverwrite.row_id,
        models.CellOverwrite.column_name,
        models.CellOverwrite.is_overwrite,
        models.CellOverwrite.updated_by,
        models.CellOverwrite.updated_at,
        models.CellOverwrite.manual_priority_source
    ).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).all()
    
    overwrites_cache = {}
    for t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin in all_overwrites:
        overwrites_cache[(r_id, col_name)] = LightCellOverwrite(t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin)

    # 2. 인메모리 연산 루프
    changed_rows = []
    tx_id = str(uuid6.uuid7())
    logs_to_cache = ByRowLogs()
    deleted_row_ids = []
    
    cell_overwrites_to_upsert = ByRow()
    cell_overwrites_to_delete = ByRowSet()
    cell_sources_to_upsert = ByRow()
    
    for item in updates:
        r_id = item["row_id"]
        col_name = item["column_name"]
        row = row_map.get(r_id)
        if not row:
            continue

        key = (r_id, col_name)
        col_srcs = sources_cache.get(key, [])
        ow = overwrites_cache.get(key)

        current_pin = ow.manual_priority_source if ow else None
        effective_source = None if (current_pin == source_name) else source_name

        if effective_source and not any(s.source_name == effective_source for s in col_srcs):
            continue

        sources_dict = {
            s.source_name: {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else None,
                "updated_by": s.updated_by
            }
            for s in col_srcs
        }

        old_val = getattr(row, col_name, None)
        new_val, top_src = compute_priority_value(sources_dict, effective_source, table_name,
                                                  cell=(table_name, col_name, row))
        moved = values_differ(old_val, new_val, (TABLE_CONFIG.get(table_name, {}).get(
            "column_types") or {}).get(col_name, "string"))
        if moved:                       # the value it already shows is not written again - no event (총괄 f5ff1e3e9)
            setattr(row, col_name, new_val)

        is_overwrite = ("user" in sources_dict) or (effective_source is not None)
        ow_key = (table_name, r_id, col_name)
        if is_overwrite:
            ow_updated_by = ow.updated_by if ow else "system"
            ow_updated_at = ow.updated_at if ow else datetime.now()
            cell_overwrites_to_upsert[ow_key] = {
                "table_name": table_name,
                "row_id": r_id,
                "column_name": col_name,
                "is_overwrite": True,
                "updated_by": updated_by or ow_updated_by,
                "updated_at": datetime.now(),
                "manual_priority_source": effective_source
            }
            cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                cell_overwrites_to_delete.add(ow_key)
                cell_overwrites_to_upsert.pop(ow_key, None)

        if moved:
            log_dict = create_audit_log(
                db, table_name, r_id, col_name, old_val, new_val,
                f"set_priority:{effective_source}", updated_by,
                transaction_id=tx_id, business_key=row.business_key_val,
                add_to_cache=False
            )
            if log_dict is not None:
                logs_to_cache.append(log_dict)

        # 복합 비즈니스 키 실시간 재계산 및 갱신 가드
        table_info = TABLE_CONFIG.get(table_name, {})
        composite_src = table_info.get("composite_key_source")
        key_col = table_info.get("business_key")

        # 🔴 [총괄 a61d32f4f ㄱ] 위 «2.» 와 같은 문 · 같은 함수 — `business_key` 칸이 없는 표도
        #   들어온다. 이 호출자의 정책은 「하나라도 비면 None」(위 «2.» 의 새 행 폴백 없음).
        if composite_src and col_name in composite_src:
            new_bk_val = rebuilt_business_key(table_name, row)

            current_bk = getattr(row, "business_key_val", None)
            if current_bk != new_bk_val:
                if new_bk_val is not None:
                    # 중복 충돌 검사
                    conflict_row = db.query(table_model).filter(
                        table_model.business_key_val == new_bk_val,
                        table_model.row_id != row.row_id
                    ).first()
                    
                    if conflict_row:
                        # [대안 B] the write seat's merge, the one body (총괄 6e041f4cb ①). Its
                        # own copy stood here and named a `changed_cols` this function never
                        # had, so any merge that changed a cell raised (a65640ca8 .. 10-03).
                        row_to_delete = row
                        row = conflict_row
                        _merge_into_key_holder(
                            db, table_name, table_model, row_to_delete, row,
                            explicit={u["column_name"]: getattr(row_to_delete, u["column_name"], None)
                                      for u in updates},
                            human_columns={u["column_name"] for u in updates},
                            source_name=source_name, updated_by=updated_by, transaction_id=tx_id,
                            changed_cols=[], overwrites_cache=overwrites_cache,
                            cell_sources_to_upsert=cell_sources_to_upsert,
                            cell_overwrites_to_upsert=cell_overwrites_to_upsert,
                            cell_overwrites_to_delete=cell_overwrites_to_delete,
                            logs_to_cache=logs_to_cache, deleted_row_ids=deleted_row_ids,
                            deleted_edits=deleted_edits)

                        # 3. 변경 대상 변경사항 캐시 스위칭
                        if row not in changed_rows:
                            changed_rows.append(row)

                written_col, _ = put_business_key(table_name, row, new_bk_val)
                if written_col:
                    # 감사 로그 생성
                    log_dict = create_audit_log(
                        db, table_name, r_id, written_col, current_bk, new_bk_val,
                        "set_priority_sync", updated_by,
                        transaction_id=tx_id, business_key=new_bk_val,
                        add_to_cache=False
                    )
                    if log_dict is not None:
                        logs_to_cache.append(log_dict)
            
        if row not in changed_rows:
            changed_rows.append(row)

    # 3. 벌크 갱신 및 삭제 수행
    if logs_to_cache:
        bulk_insert_audit_logs(db, logs_to_cache)
    bulk_upsert_cell_sources(db, list(cell_sources_to_upsert.values()))
    bulk_upsert_cell_overwrites(db, list(cell_overwrites_to_upsert.values()))
    bulk_delete_cell_overwrites(db, list(cell_overwrites_to_delete))

    db.commit()
    
    serialized_logs = []
    for log in logs_to_cache:
        log_copy = log.copy()
        if isinstance(log_copy.get("timestamp"), datetime):
            log_copy["timestamp"] = log_copy["timestamp"].isoformat()
        serialized_logs.append(log_copy)
        
    return changed_rows, serialized_logs, deleted_row_ids

def set_cell_manual_priority(db: Session, table_name: str, row_id: str, col_name: str, source_name: Optional[str], updated_by: str = "user",
                             deleted_edits: Optional[dict] = None):
    """수동 소스 우선순위(Pin)를 설정합니다."""
    changed_rows, logs, deleted_row_ids = set_cell_manual_priority_batch(db, table_name, [{"row_id": row_id, "column_name": col_name}], source_name, updated_by,
                                                                         deleted_edits=deleted_edits)
    return changed_rows[0] if changed_rows else None, [col_name] if logs else [], deleted_row_ids

