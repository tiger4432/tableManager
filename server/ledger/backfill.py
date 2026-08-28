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

🔴 THE `fetch_*` HELPERS ARE GONE (2026-08-21), AND THE SENTENCE THAT KEPT THEM IS WHY
THEY LASTED. This header used to assert that `ledger/dry_run.py` imported them "for the
admin dry-run", so everyone who came to check whether they still had callers read the
assertion instead of the module and stopped. The assertion was false: `dry_run.py` imports
`Mapping`, `logging` and `.envelope`, and nothing whatever from here. Nothing else called
them either, and `_group_transfer_rows` could not have run if something had - it imported
`transfer_translator`, deleted with the other three translators above. The admin dry-run is
a real entry point (`POST /admin/ledger/dry-run`) and it is retired with `ledger/config.py`
rather than here; it simply never depended on this module. 🔴 A DOCSTRING THAT NAMES YOUR
CALLER IS NOT A CALLER. Grep before believing this file about who reads it.

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
therefore a KEY, not a row offset, and a batch is always a whole number of that key's
GROUPS:

  * fetch a page ordered by `(page key, row identity)`;
  * if the page filled, drop the trailing group - it may be cut, and there is no way to
    tell from inside the page;
  * if dropping it leaves nothing (one group bigger than a page), fetch that whole group
    explicitly and process it alone.

The cursor advances to the last page-key value whose group was processed IN FULL. A crash
between batches re-reads that group's successor and nothing else.

🔴 WHICH column that is has one answer and it is `_page_key()` - the cursor's own first
column, never the time column. `lot_event` made the two indistinguishable for a year;
`dt_job` made them different and the difference cost twelve wrong atoms. Read `_page_key`
before touching any of this.

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

#: One page for the write-free test run behind the setup screen. Small on purpose: the
#: screen asks "does this declaration work at all", and that answer arrives in the first
#: page of a table with ten million rows exactly as it does in the first page of one with
#: forty. `DEFAULT_FETCH_ROWS` belongs to a run that intends to sweep the whole table.
PREVIEW_FETCH_ROWS = 200


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
        ontology_root=None, retranslate=None):
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
    from .setup import (
        DEFAULT_ONTOLOGY_ROOT, LedgerSetupError, _require_declared_source,
        load_setup)

    # 🔴 Positional guard, not a type nicety. `run()` used to be `run(engine, cfg, source=…)`
    # and the second POSITION now means `source`. Without this, a caller written against
    # the old shape passes a declaration dict straight into the selector and gets
    # `TypeError: unhashable type: 'dict'` from three frames down - a removal that reports
    # itself as a crash in unrelated code instead of as a retired argument.
    if not isinstance(source, str):
        raise LedgerSetupError(
            "invalid_source_argument", "source",
            f"source must be a source id string, got {type(source).__name__}; "
            f"run() no longer takes a legacy config as its second positional argument",
        )
    cutover = load_setup(
        DEFAULT_ONTOLOGY_ROOT if ontology_root is None else ontology_root)
    # 🔴 Checked HERE and not left to the write boundary. `execute_selected_cursor_batch`
    # does re-check, but only once a batch exists: an empty source would then return a
    # clean zero instead of the refusal, and a selector left on `legacy` would look like a
    # source with nothing to do. A refusal that only fires when there is work is not a
    # refusal. Reuses the cutover module's own predicate so there is one spelling of it.
    _require_declared_source(cutover, source)
    return _run_v2_lineage(
        engine, cutover, source=source, fetch_rows=fetch_rows,
        reset_cursor=reset_cursor, start_from=start_from,
        max_batches=max_batches, retranslate=retranslate)


def _run_v2_lineage(engine, setup, source="lot_event", fetch_rows=DEFAULT_FETCH_ROWS,
                    reset_cursor=False, start_from=None, max_batches=None,
                    retranslate=None):
    """Run one selected source on the existing Store/cursor.

    ``run()`` is the only caller and there is no longer an alternative driver to fall back
    to.  Reset/re-read controls are refused here because changing an existing source
    cursor requires a separate destructive approval.
    """
    from .setup import (
        LedgerSetupError,
        execute_selected_cursor_batch,
    )
    from .setup_registry import cursor_translator_version
    from . import schema
    from .store import LedgerStore

    # 🔴 THE APPROVAL IS THE SOURCE'S OWN NAME, and that is the whole design.
    # `retranslate=True` would be a global switch a caller could leave on; `retranslate=
    # "void_observation"` can only ever unlock the one source it names, and unlocking a
    # second one means writing its name too. The default is None, so a call with no new
    # argument refuses exactly as it did before this existed.
    approved = retranslate is not None and retranslate == source
    if retranslate is not None and not approved:
        raise LedgerSetupError(
            "approval_names_another_source", "retranslate",
            "the approval must name the source being re-translated: "
            f"got {retranslate!r} while running {source!r}",
        )
    if (reset_cursor or start_from is not None) and not approved:
        path = "reset_cursor" if reset_cursor else "start_from"
        raise LedgerSetupError(
            "destructive_approval_required", path,
            "v2 cursor reset or replay requires a separate destructive approval - "
            f"pass retranslate={source!r} to give it",
        )
    if not isinstance(fetch_rows, int) or isinstance(fetch_rows, bool) or fetch_rows < 1:
        raise LedgerSetupError(
            "invalid_fetch_rows", "fetch_rows", "must be a positive integer")

    plan = setup.snapshot.source_plans[source]
    if plan.driver.preparation.verified_join_descriptors:
        raise LedgerSetupError(
            "verified_join_reader_required", "source_preparation.join_reader",
            "the backfill entry requires a registered read-only join reader",
        )
    store = LedgerStore(engine)
    store.ensure_schema()
    read = store.connection()
    try:
        existing = store.read_cursor(read, source)
        cursor_value = (existing or {}).get("cursor_value") or {}
        expected_version = cursor_translator_version(setup.snapshot, source)
        # ⚠️ BOTH GUARDS STAY. An approval does not delete them - it is the thing
        # they were asking for. Without `retranslate` naming this source they refuse exactly
        # as before, which is what makes「the declaration changed, re-read it」an explicit
        # act rather than a side effect of editing a file.
        cursor_before = dict(cursor_value) if cursor_value else None
        if existing and set(cursor_value) != set(plan.driver.cursor_columns):
            if not approved:
                raise LedgerSetupError(
                    "legacy_cursor_reset_required", f"ledger_cursor.{source}.cursor_value",
                    "existing cursor shape does not match the v2 physical cursor; "
                    "inspect, back up, and obtain separate reset approval",
                )
            cursor_value = {}
        if existing and existing.get("translator_ver") != expected_version:
            if not approved:
                raise LedgerSetupError(
                    "cursor_snapshot_reset_required",
                    f"ledger_cursor.{source}.translator_ver",
                    "existing cursor belongs to a different setup snapshot; inspect, "
                    "back up, and obtain separate reset or replay approval",
                )
            cursor_value = {}
        if approved and reset_cursor:
            cursor_value = {}
        after_key = cursor_value.get(_page_key(plan))
        result = BackfillResult(
            source=source,
            translator_ver=expected_version,
            started_from=dict(cursor_value) if cursor_value else None,
            molecules=0, refused_molecules=0, incomplete_molecules=0,
            attempted=0, inserted=0, deduped=0, batches=0,
            rows_read=0, cursor=dict(cursor_value) if cursor_value else None,
            seconds=0.0,
        )
        # 🔴 AN APPROVED REPLAY REPLACES; IT DOES NOT ADD. Measured 2026-08-28 with
        # one batch: re-translating under a changed declaration wrote 1,999 NEW `observed`
        # atoms beside the 1,999 old ones - `deduped 0`, because the new shape has a
        # different `uq_ledger_atom` key and collides with nothing. A full run that way
        # leaves two generations of the same finding and the walk counts both.
        #
        # So the approval that unlocks the cursor also clears what this source wrote before.
        # The atoms are a PROJECTION of the source rows, which are still there, so this
        # removes a derived generation rather than a record - the standing distinction.
        #
        # ⚠️ NAMED, NOT HIDDEN: the clear and the rewrite are not one transaction. A
        # run that dies midway leaves the old generation gone and the new one partial. The
        # honest fix is a snapshot column the reader filters on, which is a declaration
        # change; until then a failed replay is re-run, and `atoms_deleted` in the return is
        # how a caller sees that it happened at all.
        if approved:
            write = store.connection()
            try:
                cur = write.cursor()
                cur.execute(
                    f"DELETE FROM {schema.LEDGER_TABLE} WHERE source_who = %s", (source,))
                result["atoms_deleted"] = int(cur.rowcount or 0)
                write.commit()
            finally:
                write.close()
        started = time.monotonic()
        # 🔴 THE SPLIT GUARD. One source event must land in ONE batch; if a group this run
        # already processed IN FULL comes back in a later page, it did not, and every
        # count taken over it is a count of a page rather than of the event. It asserts
        # the SYMPTOM, not the cause, so it survives whatever produces the split -- a page
        # key that stops being group-constant, an ORDER BY that stops making groups
        # contiguous, a fourth grammar that copies the loop. `_page_key` explains why the
        # cause cannot be asserted from the declaration at all.
        #
        # IT WOULD HAVE FIRED ON DAY ONE. Paging `dt_job` on `created_at` split 24 jobs;
        # this run would have stopped at the SECOND sighting of the first one instead of
        # silently writing ingestion-batch counts for all 24.
        #
        # 🔴 WHAT IT DOES NOT DO: it fires when the group comes BACK, so the first half is
        # already committed. It bounds the damage to that one molecule and makes it loud;
        # it cannot prevent it, because nothing in a page can see the row that follows it.
        #
        # Scope is THIS RUN, deliberately. Across runs the pager reads `WHERE page_key >
        # cursor`, so a completed group is never re-read -- and a run that legitimately
        # re-reads (a future reset/replay) must not be refused by a guard that remembers
        # work it was told to redo. Bounded by group count per run, not by row count.
        guard_columns = tuple(
            column for column in plan.driver.group_by
            if column in v2_base_select_columns(setup.snapshot, source))
        split_guard = len(guard_columns) == len(plan.driver.group_by)
        if not split_guard:
            # Said out loud rather than skipped quietly: this source's group identity is
            # DERIVED by its preparer, so the guard cannot read it from a base row and the
            # operator is entitled to know the run is unguarded on this axis.
            derived = sorted(set(plan.driver.group_by) - set(guard_columns))
            result["split_guard"] = f"inactive: group key is derived ({derived})"
            logger.warning(
                "[Ledger] split guard inactive for %s: group columns %s are not base "
                "columns, so a split molecule cannot be detected from the page", source,
                derived)
        completed_groups: set[tuple] = set()
        pages = walk_group_pages(
            lambda position: _fetch_v2_lineage_page(
                read, plan, position, fetch_rows),
            lambda page_value: _fetch_v2_lineage_group(read, plan, page_value),
            _page_key(plan), after_key, fetch_rows,
        )
        for complete, next_after, _last_page in pages:
            if max_batches is not None and result["batches"] >= max_batches:
                break
            frame = _v2_frame(complete)
            result["rows_read"] += len(frame)
            subjects = _v2_registration_subjects(plan, frame)
            known = (None if subjects is None
                     else store.existing_registrations(read, subjects))
            # End every SELECT-only transaction before LedgerStore opens its existing
            # Atom+cursor write transaction.  This is the same lock boundary as legacy.
            read.rollback()
            ordered = frame.sort_values(list(plan.driver.cursor_columns))
            last = ordered.iloc[-1]
            next_cursor = {
                column: last[column] for column in plan.driver.cursor_columns}
            # Checked BEFORE the write, so the returning half is refused rather than
            # committed beside the half that is already there. Read off the base frame the
            # loop already holds -- a second preparation pass to recover molecule refs
            # measured 61% of a preview per batch, which is not a price a guard may charge
            # on every batch forever.
            batch_groups = set(
                frame[list(guard_columns)].drop_duplicates()
                .itertuples(index=False, name=None)) if split_guard else set()
            repeated = sorted(str(token) for token in batch_groups & completed_groups)
            if repeated:
                raise LedgerSetupError(
                    "source_event_split_across_batches",
                    f"sources.{source}.read.cursor.columns",
                    f"{len(repeated)} source event(s) already processed in full came "
                    f"back in a later page, so one event is being split across two "
                    f"batches and its counts describe pages rather than events: "
                    f"{repeated[:5]}",
                )
            executed = execute_selected_cursor_batch(
                setup, source, frame, next_cursor, _no_join_reader(), store,
                known_registrations=known, retranslate_approved=approved,
            )
            written = executed.store_result
            result["molecules"] += executed.preview.molecule_count
            result["incomplete_molecules"] += executed.preview.incomplete_count
            result["attempted"] += int(written.get("attempted", 0))
            result["inserted"] += int(written.get("inserted", 0))
            result["deduped"] += int(written.get("deduped", 0))
            result["batches"] += 1
            result["cursor"] = dict(executed.preview.cursor_value)
            completed_groups |= batch_groups
            after_key = next_after
        result["seconds"] = round(time.monotonic() - started, 3)
        # 🔴 WHAT AN APPROVAL ACTUALLY DID, IN NUMBERS. A caller who unlocked the
        # cursor must be able to read back what changed without querying anything.
        result["retranslated"] = bool(approved)
        result["cursor_before"] = cursor_before
        result["cursor_after"] = result.get("cursor")
        return result
    finally:
        read.close()


def _no_join_reader():
    """The join reader for a source that inherits no verified join: it refuses if asked.

    Built here rather than declared at module scope because `LedgerSetupError` lives in
    `.setup`, which imports `runtime_v2`, which imports THIS module -- every import in
    this file is lazy for that reason.  One factory rather than one class per caller: the
    execute path and the write-free preview path must refuse an unsupplied reader with the
    SAME code, or the screen and the backfill disagree about what happened.
    """
    from .setup import LedgerSetupError
    from .source_preparation import VerifiedJoinBatchReader

    class NoJoinReader(VerifiedJoinBatchReader):
        def read_chunk(self, descriptor, keys):
            raise LedgerSetupError(
                "verified_join_reader_required", "source_preparation.join_reader",
                "selected source inherits a verified join but no reader was supplied",
            )

    return NoJoinReader()


def preview_first_batch(engine, setup, source, fetch_rows=PREVIEW_FETCH_ROWS):
    """Compile ONE batch of this source's FIRST page. WRITES NOTHING, MOVES NO CURSOR.

    Returns `(rows_read, preview_or_None)`; the preview is `None` only when the relation
    handed back no rows at all, which is an ANSWER ("read 0 rows") and not a failure.

    🔴 THE FIRST PAGE, NEVER THE CURSOR. A source being authored has no cursor row, and a
    source that has one would have this read start past everything it has already done --
    so a screen asking "does my declaration work" would be answered by an empty page on
    exactly the sources that have run. Reading from the start costs one indexed page and
    is the only position that answers the question for a new source and an old one alike.
    Nothing here reads or writes `ledger_cursor`.

    🔴 `known_registrations` IS THE EMPTY SNAPSHOT WHEN A PROBE IS DECLARED, and that is a
    decision rather than a shortcut. Passing the LIVE set makes every `register` sentence
    report zero on a source that has already been backfilled -- measured on `lot_event`:
    1,173 atoms with the live set against 1,323 with the empty one, the difference being
    150 registrations the ledger already holds. A sentence reporting zero because the work
    is done reads identically to a sentence that emits nothing, which is the silent hole
    this whole surface exists to remove. The empty snapshot answers what the DECLARATION
    says about these rows.

    🔴 `None` WHEN NO PROBE IS DECLARED, and that is NOT the same as empty. `None` is what
    makes `runtime_v2._filtered_event_atoms` refuse with `registration_context_required`
    for a source that emits `register` without declaring how to look one up -- one of the
    five refusals `lot_event` met at backfill while the screen was green. Substituting an
    empty set here would swallow it.
    """
    from .setup import LedgerSetupError, preview_selected_cursor_batch

    plan = setup.snapshot.source_plans[source]
    if plan.driver.preparation.verified_join_descriptors:
        # Same refusal, same code, as the backfill entry: this path has no registered
        # read-only join reader either, and inventing one for a preview would report a
        # pass for a declaration the run cannot execute.
        raise LedgerSetupError(
            "verified_join_reader_required", "source_preparation.join_reader",
            "the test run requires a registered read-only join reader",
        )
    read = engine.raw_connection()
    try:
        rows = _fetch_v2_lineage_page(read, plan, None, fetch_rows)
        complete, dropped = _cut_on_group_boundary(
            rows, fetch_rows, key=_page_key(plan))
        # A page that is ENTIRELY one group cannot be cut down; fetch that group whole,
        # exactly as `walk_group_pages` does, so a molecule is never previewed in halves.
        if not complete and dropped is not None:
            complete = _fetch_v2_lineage_group(read, plan, dropped)
    finally:
        # Every statement above is a SELECT; ending the transaction rather than leaving it
        # open is the same lock boundary the run keeps before it writes.
        read.rollback()
        read.close()
    if not complete:
        return 0, None
    frame = _v2_frame(complete)
    subjects = _v2_registration_subjects(plan, frame)
    known = None if subjects is None else ()
    ordered = frame.sort_values(list(plan.driver.cursor_columns))
    last = ordered.iloc[-1]
    cursor_value = {column: last[column] for column in plan.driver.cursor_columns}
    preview = preview_selected_cursor_batch(
        setup, source, frame, cursor_value, _no_join_reader(),
        known_registrations=known)
    return len(frame), preview


def _v2_frame(rows):
    import pandas as pd
    return pd.DataFrame(rows)


def _page_key(plan):
    """The physical column a page is CUT on: the cursor's first column.

    🔴 IT MUST BE THE COLUMN THE CURSOR IS WRITTEN FROM, and for a while it was not. The
    cursor is written from `driver.cursor_columns` and validated against
    `driver.cursor_columns`, while the page was cut on `driver.occurred_at.column` --
    the read key and the write key disagreed by construction, and that ONE argument
    produced three symptoms at once:

      * a molecule whose rows span two values of the time column was cut ACROSS pages,
        each half becoming its own event. MEASURED on `dt_log` 2026-08-19: of the 26
        `dt_job`s written by two ingestion batches, 24 were split this way, and each
        half minted an atom counting an INGESTION BATCH ("59 dies" and "13 dies" for a
        72-row job);
      * `after` was read from a key the cursor does not carry, so it was always None and
        every run restarted at row 1;
      * the two disagreed silently, because on the only source that existed when this
        was written they are the same column.

    THE INVARIANT IS THAT THE PAGE KEY IS CONSTANT WITHIN A GROUP -- then a page cut on
    it cannot split a molecule.

    🔴 AND NOTHING HERE CAN CHECK THAT. It is tempting to say the cursor's first column
    is group-constant "by construction, because the cursor only advances to groups
    completed in full" -- that does not follow, and the retraction is the reason the
    guard below this exists. Cursor advancement says nothing about whether a column
    varies INSIDE a group. What actually makes it true today, measured per source:

      * `dt_job` groups by `dt_job` and pages on `dt_job` -- the same column, so no
        split is possible;
      * `lot_event` groups by `event_group_key`, which the PREPARER derives and which no
        page query can order by (that is also why this is not `group_by[0]`). Paging on
        `event_time` is safe only because the mapper's `_event_key` EMBEDS `event_time`
        in that derived key, making the page key a COARSENING of the group -- and a
        coarsening never splits.

    The second one is a fact about a mapper, INVISIBLE TO THE DECLARATION. The compiler
    cannot verify it and cannot refuse a future source whose cursor starts on a column
    that varies within its group; such a config would read as correct right up to the
    day it silently split a molecule. That is why the run carries a cause-agnostic guard
    on the SYMPTOM (`completed_groups` in `_run_v2_lineage`) instead of an assertion here
    on the cause.

    This function returns `event_time` for `lot_event`, the same column as before; only
    a source whose two keys actually differ changes behaviour.
    """
    return plan.driver.cursor_columns[0]


def _fetch_v2_lineage_page(connection, plan, after, limit):
    return _fetch_v2_lineage_rows(connection, plan, after=after, limit=limit)


def _fetch_v2_lineage_group(connection, plan, page_value):
    return _fetch_v2_lineage_rows(
        connection, plan, group_value=page_value, limit=None)


def _fetch_v2_lineage_rows(connection, plan, *, after=None, group_value=None,
                           limit=None):
    """Read physical catalog columns with identifier-safe psycopg2 composition."""
    from psycopg2 import sql

    from .source_preparation import base_select_columns
    columns = base_select_columns(plan)
    # The page key leads the ORDER BY so that its groups are CONTIGUOUS -- that
    # contiguity is the whole basis on which `_cut_on_group_boundary` may drop a trailing
    # group and `walk_group_pages` may resume with `> after`.
    page_key = _page_key(plan)
    order = tuple(dict.fromkeys((page_key, *plan.driver.order_by)))
    select_sql = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    relation_sql = sql.SQL(".").join(
        sql.Identifier(part) for part in plan.relation.split("."))
    where_sql = sql.SQL("")
    params = []
    if group_value is not None:
        where_sql = sql.SQL(" WHERE {} = %s").format(sql.Identifier(page_key))
        params.append(group_value)
    elif after is not None:
        where_sql = sql.SQL(" WHERE {} > %s").format(sql.Identifier(page_key))
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


def _v2_registration_subjects(plan, frame):
    """One batched first-sight query, driven by the source's declared probe.

    This function used to be `_v2_lot_event_subjects` and named `lot_id`, `parent_lot`,
    `child_lot`, `waferids`, `"Lot"`, `"Wafer"` and `":"` as literals -- so `run()` sent
    EVERY v2 source down a branch that could only work for one table. That is why no
    second source could be stood up on v2 at all, and it is what this replaces.

    Returns `None` when the source declares no probe. `None` is not "no subjects": it is
    "this source did not answer the question", and `runtime_v2._filtered_event_atoms`
    refuses with `registration_context_required` if the source emits `register` anyway. A
    source that emits no `register` needs no probe and is unaffected. Returning an empty
    set instead would claim nothing is registered yet, which SUPPRESSES nothing and
    duplicates every first-sight atom -- the unsafe direction (see
    `setup_bundle._validate_registration_probe` for why the error is one-sided).
    """
    from .envelope import canonical_keys

    probes = plan.driver.registration_probe
    if not probes:
        return None
    subjects = set()
    for probe in probes:
        values = []
        for column in probe.columns:
            if column in frame.columns:
                values.extend(frame[column].tolist())
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            parts = (text.split(probe.list_separator) if probe.list_separator
                     else [text])
            for part in parts:
                key = part.strip()
                if key:
                    subjects.add((probe.subject_type,
                                  canonical_keys({probe.identity_key: key})))
    return subjects


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
    from .setup import DEFAULT_ONTOLOGY_ROOT, LedgerSetupError

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
        raise LedgerSetupError(
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
