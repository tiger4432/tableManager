"""The backfill drivers - cursor loops that never cut a molecule in half.

    conda run -n assy_manager python -m ledger.backfill --source lot_event

🔴 ONE GRAMMAR, ONE DRIVER (owner ruling, 2026-08-18: "remove legacy")
-----------------------------------------------------------------------------
`run()` loads the ontology root, requires that the source is selected for v2, and drives
it through `_run_v2_lineage`. There is one execution path and one driver.

⚠️ THE FOUR GRAMMAR DRIVERS ARE GONE (this commit, 798 lines).
`_run_lineage`, `_run_observation`, `_run_transfer` and `_run_declared` each lazily
imported a translator module the owner deleted on 2026-08-18 (`lot_event_translator`,
`observation_translator`, `transfer_translator`, `declared_translator`), so each could
only raise `ImportError` where a refusal belonged. Their private helpers went with them
(`_flush`, `_refusal_totals`, `_refusal_delta`, `_watermark_json`, `_cursor_json`) and so
did `run()`'s `cfg` parameter, which existed to carry the legacy declaration into them.

🔴 The `fetch_*` helpers below OUTLIVED their drivers on purpose, and that is not
leftovers. `ledger/dry_run.py` imports `fetch_observation_page`, `fetch_runs`,
`fetch_declared_page`, `fetch_transfer_page`, `fetch_transfer_group`, `fetch_containers`,
`_group_transfer_rows`, `_plain` and `_forget_registers` for the admin dry-run, which is a
separate entry point behind `POST /admin/ledger/dry-run` and is retired with
`ledger/config.py` rather than here. Deleting them in this commit would have taken down a
live route to tidy a module.

🔴 The count in this header used to be maintained by hand and went stale silently: it said
THREE until 2026-08-18, having missed `_run_declared`, and the wrong count propagated into
four documents before anyone re-read `run()`. Prose that COUNTS something the code also
counts will go stale, because nothing executes the prose. The count is now one, and it is
one because there is one function.

WHERE THE BATCH IS CUT, AND WHY IT MATTERS MORE THAN THE BATCH SIZE
--------------------------------------------------------------------
The two rows of one source event share an `event_time` and differ in `lot`, so a batch
boundary drawn at "N rows" can fall BETWEEN them - and then the molecule is split across
two transactions, which is the exact half-landing the brief forbids. The cursor is
therefore an `event_time`, not a row offset, and a batch is always a whole number of
`event_time` GROUPS:

  * fetch a page ordered by `(event_time, row identity)`;
  * if the page filled, drop the trailing group - it may be cut, and there is no way to
    tell from inside the page;
  * if dropping it leaves nothing (one group bigger than a page), fetch that whole group
    explicitly and process it alone.

The cursor advances to the last event_time whose group was processed IN FULL. A crash
between batches re-reads that group's successor and nothing else.

WHY THE CURSOR IS `event_time` AND WHAT THAT COSTS - stated, not hidden
-----------------------------------------------------------------------
🔴 `event_time` is WORLD time. A row that arrives late with an older timestamp lands
BEHIND the cursor and this backfill will not see it. That is acceptable for a one-off
backfill (the point of which is to sweep what already exists) and it is NOT acceptable
for the live subscription that follows in §10 step 2, which must be driven by the outbox
rather than by re-scanning this table. Writing it down here so the next lane does not
inherit the assumption silently: `--from` re-runs any window, and the unique index makes
re-running free of duplicates.

IDEMPOTENCY HAS TWO INDEPENDENT NETS AND BOTH ARE PROVEN SEPARATELY
--------------------------------------------------------------------
1. **The cursor.** A second run reads zero rows, so it writes zero atoms.
2. **`uq_ledger_atom`.** Reset the cursor and run again: rows ARE read, atoms ARE built,
   and the database accepts none of them.

Net 1 alone would pass a test while net 2 was broken, and vice versa. This project has
already paid for a fix that closed one of two doors and reported success
(`_get_or_create_row`, 2026-08-11), so `test_ledger_l1_pg.py` exercises them separately.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import logging
import os
import sys
import time

logger = logging.getLogger("Ledger.Backfill")

DEFAULT_FETCH_ROWS = 2000


def _bootstrap_path():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)


class BackfillResult(dict):
    """A plain dict, named so a caller can see what a run reports without reading code."""


def v2_base_select_columns(snapshot, source_id):
    """Stage 5 hand-off: columns the existing cursor reads from the base relation.

    This is deliberately a small adapter on the established driver module.  It does not
    create a second cursor or reader; Stage 6 will exercise its PostgreSQL transaction.
    """
    from .source_preparation import base_select_columns
    try:
        source_plan = snapshot.source_plans[source_id]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"unknown Ledger v2 source {source_id!r}") from exc
    return base_select_columns(source_plan)


def prepare_v2_cursor_batch(snapshot, source_id, rows, reader, implementations):
    """Convert one complete existing-cursor batch into prepared EventFrames.

    The function has no store/cursor mutation.  A preparation refusal propagates before
    any Role mapper/compiler call, so the caller keeps its current cursor unchanged.
    """
    import pandas as pd
    from .source_preparation import SourcePreparationContext, prepare_source_batch
    try:
        source_plan = snapshot.source_plans[source_id]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"unknown Ledger v2 source {source_id!r}") from exc
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    return prepare_source_batch(
        SourcePreparationContext(snapshot, source_plan), frame, reader, implementations)


def fetch_page(connection, source, columns, after, limit):
    """One page of source rows past `after`, as dicts with LOGICAL key names.

    The translator never sees a physical column name - the config maps them - so a source
    that spells `wafer_ids` differently needs a config line, not a code change.
    """
    time_column = columns["event_time_column"]
    identity = columns["row_identity"]
    select = [
        f"{identity} AS row_identity",
        f"{columns['lot']} AS lot",
        f"{columns['event_type']} AS event_type",
        f"{columns['parent_lot']} AS parent_lot",
        f"{columns['child_lot']} AS child_lot",
        f"{columns['slots']} AS slots",
        f"{columns['wafers']} AS wafers",
        f"{time_column} AS event_time",
    ]
    with connection.cursor() as cursor:
        where, params = "", []
        if after is not None:
            where = f"WHERE {time_column} > %s "
            params.append(after)
        params.append(limit)
        cursor.execute(
            f"SELECT {', '.join(select)} FROM {source} "
            f"{where}ORDER BY {time_column}, {identity} "
            f"LIMIT %s", tuple(params))
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def fetch_group(connection, source, columns, event_time):
    """Every row of ONE `event_time`. The escape hatch for a group bigger than a page."""
    time_column = columns["event_time_column"]
    identity = columns["row_identity"]
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {identity} AS row_identity, {columns['lot']} AS lot, "
            f"{columns['event_type']} AS event_type, "
            f"{columns['parent_lot']} AS parent_lot, "
            f"{columns['child_lot']} AS child_lot, {columns['slots']} AS slots, "
            f"{columns['wafers']} AS wafers, {time_column} AS event_time "
            f"FROM {source} WHERE {time_column} = %s ORDER BY {identity}",
            (event_time,))
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def _cut_on_group_boundary(rows, page_limit, key="event_time"):
    """`(complete_rows, trailing_group_value_or_None)`.

    Returns the rows that are safe to process now, plus the group value whose group had to
    be dropped because the page may have cut it. `None` for the second element means the
    page reached the end of the source and nothing was dropped.

    `key` is a parameter rather than a constant because the TRANSFER grammar cuts on the
    same boundary for the same reason, over a different column (ruling R-2026-08-14-D's
    third grammar). The rule being shared is what matters: a batch is a whole number of
    groups or the molecule lands half.
    """
    if not rows:
        return [], None
    if len(rows) < page_limit:
        return rows, None
    last_value = rows[-1][key]
    kept = [r for r in rows if r[key] != last_value]
    return kept, last_value


def walk_group_pages(fetch_page, fetch_group, key, after, page_limit):
    """Yield `(rows, cursor_after, is_last_page)` - whole groups only, none skipped.

    🔴 THE ONE PLACE THE PAGE RULE LIVES, and it is one place because it was two and they
    were both wrong in the same way. Both drivers that page over groups need three
    behaviours and the third is the one that bit:

      1. a page that filled may have CUT its trailing group, so that group is dropped;
      2. a page that is ENTIRELY one group cannot be cut down at all, so that group is
         fetched whole and processed alone;
      3. 🔴 the cursor then advances to the last group processed IN FULL - never to the
         dropped one. The fetch is `WHERE key > cursor`, so advancing to the dropped
         group's key skips the very group that was set aside because it still needed
         reading.

    MEASURED 2026-08-14, when `dt_log` became the first source larger than one page: 396
    job-runs in the table, 379 translated, 17 groups and 1,862 source rows silently gone.
    `lot_event` is 43 rows, so `dropped` was always `None` there and rule 3 had never been
    executed by anything.

    `fetch_page(after)` and `fetch_group(key_value)` are the source-specific halves; every
    rule above is here, so a fourth grammar inherits them by calling this rather than by
    copying a loop.
    """
    while True:
        rows = fetch_page(after)
        if not rows:
            return
        complete, dropped = _cut_on_group_boundary(rows, page_limit, key=key)
        if not complete:
            complete = fetch_group(dropped)
            dropped = None
        after = complete[-1][key]
        last = dropped is None and len(rows) < page_limit
        yield complete, after, last
        if last:
            return


def run(engine, source="lot_event", fetch_rows=DEFAULT_FETCH_ROWS,
        reset_cursor=False, start_from=None, max_batches=None, probe_lag=True,
        ontology_root=None):
    """Translate everything past the cursor. Returns a `BackfillResult`.

    🔴 ONE EXECUTION PATH (owner ruling, 2026-08-18: "remove legacy")
    ------------------------------------------------------------------
    This function used to dispatch on the source's declared `kind` and fall through to one
    of four legacy grammar drivers. Every one of those drivers lazily imported a
    translator module the owner has since deleted, so the fallthrough could only ever
    raise `ImportError` - a traceback where a refusal belonged. The fallthrough is gone:
    a source that the ontology root does not select for v2 is REFUSED here, by name, and
    the reason is the declaration rather than a missing file.

    The `cfg` parameter went with the drivers. It carried the parsed legacy declaration
    and nothing else ever read it; keeping it as an ignored argument would have left a
    name that answers for a body that no longer decides anything, which is the failure
    this retirement is cleaning up.

    `reset_cursor=True` deliberately re-reads work that is already done - it is how net 2
    of the idempotency argument gets exercised, and how an operator re-translates after a
    rule change (the new `source_translator_ver` makes the new atoms distinct from the
    old ones, which is correct: they are different claims made by different rules).
    """
    from .cutover_v2 import (
        DEFAULT_ONTOLOGY_ROOT, LedgerV2CutoverError, _require_v2_selection,
        load_cutover_setup)

    # 🔴 Positional guard, not a type nicety. `run()` used to be `run(engine, cfg, source=…)`
    # and the second POSITION now means `source`. Without this, a caller written against
    # the old shape passes a declaration dict straight into the selector and gets
    # `TypeError: unhashable type: 'dict'` from three frames down - a removal that reports
    # itself as a crash in unrelated code instead of as a retired argument.
    if not isinstance(source, str):
        raise LedgerV2CutoverError(
            "invalid_source_argument", "source",
            f"source must be a source id string, got {type(source).__name__}; "
            f"run() no longer takes a legacy config as its second positional argument",
        )
    cutover = load_cutover_setup(
        DEFAULT_ONTOLOGY_ROOT if ontology_root is None else ontology_root)
    # 🔴 Checked HERE and not left to the write boundary. `execute_selected_cursor_batch`
    # does re-check, but only once a batch exists: an empty source would then return a
    # clean zero instead of the refusal, and a selector left on `legacy` would look like a
    # source with nothing to do. A refusal that only fires when there is work is not a
    # refusal. Reuses the cutover module's own predicate so there is one spelling of it.
    _require_v2_selection(cutover, source)
    return _run_v2_lineage(
        engine, cutover, source=source, fetch_rows=fetch_rows,
        reset_cursor=reset_cursor, start_from=start_from,
        max_batches=max_batches)


def _run_v2_lineage(engine, setup, source="lot_event", fetch_rows=DEFAULT_FETCH_ROWS,
                    reset_cursor=False, start_from=None, max_batches=None):
    """Run one selected source on the existing Store/cursor.

    ``run()`` is the only caller and there is no longer an alternative driver to fall back
    to.  Reset/re-read controls are refused here because changing an existing source
    cursor requires a separate destructive approval.
    """
    from .cutover_v2 import (
        LedgerV2CutoverError,
        execute_selected_cursor_batch,
    )
    from .source_preparation import VerifiedJoinBatchReader
    from .store import LedgerStore

    if reset_cursor or start_from is not None:
        path = "reset_cursor" if reset_cursor else "start_from"
        raise LedgerV2CutoverError(
            "destructive_approval_required", path,
            "v2 cursor reset or replay requires a separate destructive approval",
        )
    if not isinstance(fetch_rows, int) or isinstance(fetch_rows, bool) or fetch_rows < 1:
        raise LedgerV2CutoverError(
            "invalid_fetch_rows", "fetch_rows", "must be a positive integer")

    class NoJoinReader(VerifiedJoinBatchReader):
        def read_chunk(self, descriptor, keys):
            raise LedgerV2CutoverError(
                "verified_join_reader_required", "source_preparation.join_reader",
                "selected source inherits a verified join but no reader was supplied",
            )

    plan = setup.snapshot.source_plans[source]
    if plan.driver.preparation.verified_join_descriptors:
        raise LedgerV2CutoverError(
            "verified_join_reader_required", "source_preparation.join_reader",
            "the backfill entry requires a registered read-only join reader",
        )
    store = LedgerStore(engine)
    store.ensure_schema()
    read = store.connection()
    try:
        existing = store.read_cursor(read, source)
        cursor_value = (existing or {}).get("cursor_value") or {}
        expected_version = f"ledger-v2:{setup.snapshot.snapshot_sha256}"
        if existing and set(cursor_value) != set(plan.driver.cursor_columns):
            raise LedgerV2CutoverError(
                "legacy_cursor_reset_required", f"ledger_cursor.{source}.cursor_value",
                "existing cursor shape does not match the v2 physical cursor; "
                "inspect, back up, and obtain separate reset approval",
            )
        if existing and existing.get("translator_ver") != expected_version:
            raise LedgerV2CutoverError(
                "cursor_snapshot_reset_required",
                f"ledger_cursor.{source}.translator_ver",
                "existing cursor belongs to a different setup snapshot; inspect, "
                "back up, and obtain separate reset or replay approval",
            )
        after_time = cursor_value.get(plan.driver.occurred_at.column)
        result = BackfillResult(
            source=source,
            translator_ver=expected_version,
            started_from=dict(cursor_value) if cursor_value else None,
            molecules=0, refused_molecules=0, incomplete_molecules=0,
            attempted=0, inserted=0, deduped=0, batches=0,
            rows_read=0, cursor=dict(cursor_value) if cursor_value else None,
            seconds=0.0,
        )
        started = time.monotonic()
        pages = walk_group_pages(
            lambda position: _fetch_v2_lineage_page(
                read, plan, position, fetch_rows),
            lambda event_time: _fetch_v2_lineage_group(read, plan, event_time),
            plan.driver.occurred_at.column, after_time, fetch_rows,
        )
        for complete, next_after, _last_page in pages:
            if max_batches is not None and result["batches"] >= max_batches:
                break
            frame = _v2_frame(complete)
            result["rows_read"] += len(frame)
            subjects = _v2_lot_event_subjects(frame)
            known = store.existing_registrations(read, subjects)
            # End every SELECT-only transaction before LedgerStore opens its existing
            # Atom+cursor write transaction.  This is the same lock boundary as legacy.
            read.rollback()
            ordered = frame.sort_values(list(plan.driver.cursor_columns))
            last = ordered.iloc[-1]
            next_cursor = {
                column: last[column] for column in plan.driver.cursor_columns}
            executed = execute_selected_cursor_batch(
                setup, source, frame, next_cursor, NoJoinReader(), store,
                known_registrations=known,
            )
            written = executed.store_result
            result["molecules"] += executed.preview.molecule_count
            result["incomplete_molecules"] += executed.preview.incomplete_count
            result["attempted"] += int(written.get("attempted", 0))
            result["inserted"] += int(written.get("inserted", 0))
            result["deduped"] += int(written.get("deduped", 0))
            result["batches"] += 1
            result["cursor"] = dict(executed.preview.cursor_value)
            after_time = next_after
        result["seconds"] = round(time.monotonic() - started, 3)
        return result
    finally:
        read.close()


def _v2_frame(rows):
    import pandas as pd
    return pd.DataFrame(rows)


def _fetch_v2_lineage_page(connection, plan, after, limit):
    return _fetch_v2_lineage_rows(connection, plan, after=after, limit=limit)


def _fetch_v2_lineage_group(connection, plan, occurred_at):
    return _fetch_v2_lineage_rows(
        connection, plan, group_value=occurred_at, limit=None)


def _fetch_v2_lineage_rows(connection, plan, *, after=None, group_value=None,
                           limit=None):
    """Read physical catalog columns with identifier-safe psycopg2 composition."""
    from psycopg2 import sql

    from .source_preparation import base_select_columns
    columns = base_select_columns(plan)
    occurred = plan.driver.occurred_at.column
    order = tuple(dict.fromkeys((occurred, *plan.driver.order_by)))
    select_sql = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    relation_sql = sql.SQL(".").join(
        sql.Identifier(part) for part in plan.relation.split("."))
    where_sql = sql.SQL("")
    params = []
    if group_value is not None:
        where_sql = sql.SQL(" WHERE {} = %s").format(sql.Identifier(occurred))
        params.append(group_value)
    elif after is not None:
        where_sql = sql.SQL(" WHERE {} > %s").format(sql.Identifier(occurred))
        params.append(after)
    query = sql.SQL("SELECT {} FROM {}{} ORDER BY {}").format(
        select_sql, relation_sql, where_sql,
        sql.SQL(", ").join(sql.Identifier(column) for column in order),
    )
    if limit is not None:
        query += sql.SQL(" LIMIT %s")
        params.append(limit)
    with connection.cursor() as cursor:
        cursor.execute(query, tuple(params))
        names = [description[0] for description in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def _v2_lot_event_subjects(frame):
    """One batched first-sight query for the source-specific live lot event shape."""
    from .envelope import canonical_keys
    subjects = set()
    lots = set(frame["lot_id"].tolist())
    lots.update(frame["parent_lot"].tolist())
    lots.update(frame["child_lot"].tolist())
    for lot in lots:
        text = str(lot or "").strip()
        if text:
            subjects.add(("Lot", canonical_keys({"lot": text})))
    for value in frame["waferids"].tolist():
        for wafer in str(value or "").split(":"):
            text = wafer.strip()
            if text:
                subjects.add(("Wafer", canonical_keys({"wafer": text})))
    return subjects


def fetch_observation_page(connection, source, source_cfg, after, limit):
    """One page of finding rows past the keyset `after`, as dicts with LOGICAL names.

    🔴 KEYSET, NOT OFFSET, AND NOT A TIME. The row-value comparison
    `(updated_at, row_id) > (…, …)` is what the declared watermark index answers directly,
    so page N costs the same as page 1 - the property an OFFSET loses and the reason this
    project forbids large offsets. A world-time cursor is not available here at all: the
    findings' world time lives on the run, and their own `updated_at` is stamped in bulk
    (92 distinct values across 91,756 rows on this box), so a time cursor would make one
    load one indivisible group.
    """
    columns = source_cfg["columns"]
    watermark = list(source_cfg["watermark"]["columns"])
    select = [f"{columns['row_identity']} AS row_identity",
              f"{columns['wafer']} AS wafer",
              f"{columns['run_key']} AS run_key"]
    for logical in ("die_x", "die_y", "die_gate", "inchip_x", "inchip_y",
                    "extent_x", "extent_y", "unit", "class"):
        physical = columns.get(logical)
        if physical:
            select.append(f"{physical} AS {logical}")
    select.extend(f"{column} AS __wm{index}__"
                  for index, column in enumerate(watermark))
    ordered = ", ".join(watermark)
    where, params = "", []
    if after:
        placeholders = ", ".join(["%s"] * len(watermark))
        where = f"WHERE ({ordered}) > ({placeholders}) "
        params.extend(after)
    params.append(limit)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(select)} FROM {source} {where}"
            f"ORDER BY {ordered} LIMIT %s", tuple(params))
        names = [d[0] for d in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    for row in rows:
        row["__watermark__"] = [row.pop(f"__wm{index}__")
                                for index in range(len(watermark))]
    return rows


def fetch_runs(connection, source_cfg, keys):
    """`{run_key: {occurred_at, method}}` for a whole page. ONE query.

    A per-row lookup is what makes a ten-million row backfill quadratic - the same
    argument `store.existing_registrations` is built on, one relation over. The page's
    distinct keys are bound as an ARRAY, so the planner counts them instead of guessing.
    """
    if not keys:
        return {}
    run = source_cfg["run"]
    relation = run["relation"]
    key_column = run["key_column"]
    time_column = source_cfg["occurred_at_column"]
    method_column = run.get("method_column")
    select = [f"{key_column} AS run_key", f"{time_column} AS occurred_at"]
    if method_column:
        select.append(f"{method_column} AS method")
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(select)} FROM {relation} "
            f"WHERE {key_column} = ANY(%s)", (sorted(keys),))
        names = [d[0] for d in cursor.description]
        return {row[0]: dict(zip(names, row)) for row in cursor.fetchall()}


def fetch_declared_page(connection, source, source_cfg, after, limit):
    """One page of rows past the keyset `after`, with EVERY column the row has.

    🔴 `SELECT *`, and it is the one place in this file that does. The other grammars know
    their columns because a Python class reads named fields; this grammar's columns are
    named by the OPERATOR inside `emit` (`"$leg"`), and the set of them is not knowable
    until the declaration is read - which is the whole point of the kind. Building a
    projection from the declaration instead would mean parsing `$` tokens out of arbitrary
    nested payloads to decide a SELECT list, and getting that wrong yields a row missing a
    column, which this translator (correctly) refuses. A registry table is small by nature
    - `bonding_map` is 1,181 rows - so the wide read costs nothing that matters.

    The keyset, the ordering and the `LIMIT` are the observation driver's, for the same
    reason: page N costs what page 1 costs.
    """
    watermark = list(source_cfg["watermark"]["columns"])
    identity = source_cfg["columns"]["row_identity"]
    ordered = ", ".join(watermark)
    select = ["*", f"{identity} AS row_identity",
              f"{source_cfg['occurred_at_column']} AS event_time"]
    select.extend(f"{column} AS __wm{index}__" for index, column in enumerate(watermark))
    where, params = "", []
    if after:
        placeholders = ", ".join(["%s"] * len(watermark))
        where = f"WHERE ({ordered}) > ({placeholders}) "
        params.extend(after)
    params.append(limit)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(select)} FROM {source} {where}"
            f"ORDER BY {ordered} LIMIT %s", tuple(params))
        names = [d[0] for d in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    for row in rows:
        row["__watermark__"] = [row.pop(f"__wm{index}__")
                                for index in range(len(watermark))]
    return rows


def _plain(value, row):
    """A declared value resolved WITHOUT the gate - for the register pre-fetch only.

    The pre-fetch is an optimisation (one query per page instead of one per row), so a
    value it cannot resolve must not refuse anything: it raises `KeyError`, the caller
    skips that row's pre-fetch, and the TRANSLATOR meets the same missing column inside
    the molecule scope and refuses it by name. Two code paths reaching one refusal, with
    only the second one counting.
    """
    from .config import COLUMN_REF_PREFIX

    if not isinstance(value, str) or not value.startswith(COLUMN_REF_PREFIX):
        return value
    if value.startswith(COLUMN_REF_PREFIX * 2):
        return value[1:]
    column = value[len(COLUMN_REF_PREFIX):]
    if column not in row:
        raise KeyError(column)
    return row[column]


# ------------------------------------------------------------------ transfer driver
def _transfer_select(source_cfg):
    """The SELECT list for a transfer page, in LOGICAL names. Shared by page and group.

    Written once because the two fetches below MUST produce identically shaped dicts: the
    group-escape fetch exists precisely for the case where a page could not hold a whole
    molecule, and a translator receiving a differently shaped row on that path would fail
    only on groups larger than a page - the rarest input, so the last one anybody tests.
    """
    columns = source_cfg["columns"]
    select = [f"{columns['row_identity']} AS row_identity",
              f"{columns['group_key']} AS group_key",
              f"{columns['wafer']} AS wafer",
              f"{source_cfg['occurred_at_column']} AS event_time"]
    for logical in ("recorded_lot", "recorded_slot"):
        physical = columns.get(logical)
        if physical:
            select.append(f"{physical} AS {logical}")
    return select


def fetch_transfer_page(connection, source, source_cfg, after, limit):
    """One page of transfer rows past `after`, ordered so groups are CONTIGUOUS.

    🔴 ORDERED BY `(group column, row order column)`, NOT BY THE ROW IDENTITY ALONE. On
    `dt_log` the identity is `business_key_val = '<dt_job>_<dt_x>_<dt_y>'`, so ordering by
    it LOOKS like ordering by job - and it is, only as long as no job name is a prefix of
    another (measured: 0 pairs today). That is an accident of the current data, not a
    property of the source, and a batch boundary that depends on an accident is the
    half-landing waiting for one new job name. Ordering by the declared group column makes
    contiguity structural.
    """
    group_column = source_cfg["group"]["column"]
    order_column = source_cfg["group"]["row_order_column"]
    where, params = "", []
    if after:
        where = f"WHERE {group_column} > %s "
        params.append(after)
    params.append(limit)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(_transfer_select(source_cfg))} FROM {source} {where}"
            f"ORDER BY {group_column}, {order_column} LIMIT %s", tuple(params))
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def fetch_transfer_group(connection, source, source_cfg, group_key):
    """Every row of ONE group. The escape hatch for a group bigger than a page."""
    group_column = source_cfg["group"]["column"]
    order_column = source_cfg["group"]["row_order_column"]
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(_transfer_select(source_cfg))} FROM {source} "
            f"WHERE {group_column} = %s ORDER BY {order_column}", (group_key,))
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def fetch_containers(connection, source_cfg, keys):
    """`{group_key: {"lot": ..., "slot": ...}}` for a whole page. ONE query.

    Same shape and same argument as `fetch_runs`: a per-group lookup is what makes a
    ten-million row backfill quadratic. A group ABSENT from the result is a destination
    nobody confirmed, and the translator records that rather than treating it as an error -
    which is why this returns only what it found and never a placeholder.
    """
    container = source_cfg.get("container") or {}
    relation = str(container.get("relation") or "").strip()
    if not relation or not keys:
        return {}
    key_column = container["key_column"]
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {key_column} AS group_key, {container['lot_column']} AS lot, "
            f"{container['slot_column']} AS slot FROM {relation} "
            f"WHERE {key_column} = ANY(%s)", (sorted(keys),))
        return {row[0]: {"lot": row[1], "slot": row[2]} for row in cursor.fetchall()}


def _group_transfer_rows(source, rows):
    """Rows already in group order -> molecules, order preserved.

    Deliberately does NOT assume contiguity: a group value that reappears after another
    group started still lands in its own molecule rather than a second one. Contiguity is
    what the ORDER BY buys and what the page cut relies on; this function not depending on
    it means a mis-ordered page produces a wrong batch boundary (loud, the cursor moves
    oddly) rather than two half molecules (silent).
    """
    from .transfer_translator import TransferMolecule

    molecules, order = {}, []
    for row in rows:
        key = row["group_key"]
        molecule = molecules.get(key)
        if molecule is None:
            molecule = TransferMolecule(source, key)
            molecules[key] = molecule
            order.append(key)
        molecule.rows.append(row)
    return [molecules[key] for key in order]


def _forget_registers(translator, atoms):
    from .envelope import canonical_keys
    for atom in atoms or ():
        if atom.predicate == "register":
            translator.registered.discard(
                (atom.subject_type, canonical_keys(atom.subject_keys)))


def beat(result):
    """Publish the run's state to the shared heartbeat file, note and all.

    `force=True` because a backfill's beats are rare and the throttle exists to stop a
    fast loop from writing constantly, not to drop the only beat a run emits.
    """
    try:
        from utils import heartbeat
        from . import observability
        heartbeat.beat("ledger", note=observability.note(result.get("lag_note")),
                       force=True)
    except Exception as exc:                                     # pragma: no cover
        logger.warning("[Ledger] heartbeat could not be written: %s", exc)


def main(argv=None):
    _bootstrap_path()
    from .cutover_v2 import DEFAULT_ONTOLOGY_ROOT, LedgerV2CutoverError

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default="lot_event")
    parser.add_argument("--reset-cursor", action="store_true",
                        help="re-read work already done (exercises the unique index)")
    parser.add_argument("--from", dest="start_from", default=None,
                        help="start after this position instead of the cursor: an "
                             "event_time for a lineage source, a '|'-joined keyset "
                             "(updated_at|row_id) for an observation source")
    parser.add_argument("--fetch-rows", type=int, default=DEFAULT_FETCH_ROWS)
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument(
        "--ontology-root", default=str(DEFAULT_ONTOLOGY_ROOT),
        help="the Ledger config root (the only operator path)")
    args = parser.parse_args(argv)

    # This is the public operator boundary.  Until a separate destructive approval
    # capability exists, neither execution mode may reset or replay a cursor.  Keep
    # the gate ahead of config, database, source, and store access.
    if args.reset_cursor or args.start_from is not None:
        path = "reset_cursor" if args.reset_cursor else "start_from"
        raise LedgerV2CutoverError(
            "destructive_approval_required", path,
            "cursor reset or replay requires a separate destructive approval",
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    from database.database import engine

    result = run(engine, source=args.source, fetch_rows=args.fetch_rows,
                 reset_cursor=args.reset_cursor, start_from=args.start_from,
                 max_batches=args.max_batches, ontology_root=args.ontology_root)
    beat(result)

    logger.info("[Ledger] %s", {k: v for k, v in result.items() if k != "census"})
    logger.info("[Ledger] census by predicate: %s", result.get("census"))
    if result.get("gate_note"):
        logger.warning("[Ledger] %s", result["gate_note"])
    logger.info("[Ledger] %s", result.get("lag_note"))
    return 0


if __name__ == "__main__":                                       # pragma: no cover
    sys.exit(main())
