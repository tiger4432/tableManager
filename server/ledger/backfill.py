"""The backfill drivers - cursor loops that never cut a molecule in half.

    conda run -n assy_manager python -m ledger.backfill --source lot_event

🔴 ONE GRAMMAR, ONE DRIVER (owner ruling, 2026-08-18: "remove legacy")
-----------------------------------------------------------------------------
`run()` loads the ontology root, requires that the source is selected for v2, and drives
it through `_run_via_events`. There is one execution path and one driver.

⚰️ THE CURSOR READ PATH IS GONE (판정 163/171/173). `_run_v2_lineage` walked a
watermark forward and `rows_past_cursor` counted one page from it; both are deleted here,
with the result class only they built (`BackfillResult`). What replaces them is not a
smaller cursor -- it is a different question. The row index says WHICH ROWS the ledger
holds facts from, so 『how much is left』 is `rows_not_yet_translated`: the relation's
rows minus the indexed rows, exactly, with no page that can come back short.

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
from dataclasses import dataclass
import json
import logging
import os
import sys
from pathlib import Path
import time
from typing import Any

logger = logging.getLogger("Ledger.Backfill")

DEFAULT_FETCH_ROWS = 2000

#: One page for the write-free test run behind the setup screen. Small on purpose: the
#: screen asks "does this declaration work at all", and that answer arrives in the first
#: page of a table with ten million rows exactly as it does in the first page of one with
#: forty. `DEFAULT_FETCH_ROWS` belongs to a run that intends to sweep the whole table.
#: How many MOLECULES are enough to have shown a declaration compiles. One is: the
#: question a test run answers is "does my declaration work", not "how much of my table
#: is good", and the second question has a whole route of its own.
PREVIEW_MIN_MOLECULES = 1

#: How many pages the test run may read looking for those molecules. An INSTRUMENT'S
#: budget, not a declaration axis - an operator does not author how far a probe reads,
#: and a source whose first pages are all empty must not turn one screen into a scan.
PREVIEW_MAX_PAGES = 5

#: How many refused molecules the test run carries back as samples. The COUNT is always
#: exact; this caps only how many the operator is shown, the same way the gate caps its
#: own. Not a declaration axis - an operator does not author an instrument's budget.
PREVIEW_REFUSAL_SAMPLES = 20

PREVIEW_FETCH_ROWS = 200


def _bootstrap_path():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)


def prepare_v2_cursor_batch(snapshot, source_id, rows, reader, implementations,
                            refusals=None, excluded=None):
    """Convert one complete existing-cursor batch into prepared EventFrames.

    The function has no store/cursor mutation.  A preparation refusal propagates before
    any Role mapper/compiler call, so the caller keeps its current cursor unchanged.

    `refusals`: a list to receive the molecules this batch could NOT build. A page whose
    every molecule is refused returns no frames and raises nothing - that is a page fully
    read and fully refused, and the values say so. Callers that do not pass one get the
    frames alone, exactly as before.
    """
    import pandas as pd
    from .source_preparation import SourcePreparationContext, prepare_source_batch
    try:
        source_plan = snapshot.source_plans[source_id]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"unknown Ledger v2 source {source_id!r}") from exc
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    context = SourcePreparationContext(snapshot, source_plan)
    frames = prepare_source_batch(context, frame, reader, implementations)
    if refusals is not None:
        refusals.extend(context.refusals)
    if excluded is not None:
        excluded.extend(context.excluded_rows)
    return frames


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


def run(engine, source="lot_event", fetch_rows=DEFAULT_FETCH_ROWS,
        reset_cursor=False, start_from=None, max_batches=None,
        ontology_root=None, retranslate=None, checkpoint=None, pace=None,
        catalog=None):
    """Translate every row this source has not translated yet, down the LIVE path.

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

    ⚰️ `reset_cursor`, `start_from` and `retranslate` are REFUSED BY NAME below
    (판정 171). They named a position in a path that no longer reads anything, and
    `rescope` is the tool for redoing a named set of rows. `probe_lag` went WITHOUT a
    refusal because it was never an operator's word: nothing passed it and nothing read
    it, so a refusal would have announced a retirement no caller could have noticed.
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
    # 🔴 `catalog` NAMES THE PHYSICAL SCHEMA THIS DECLARATION IS CHECKED AGAINST, and
    # omitting it keeps production's answer exactly: the deployment's own `table_config.json`.
    # Same reason `ledger.config.load` grew one (판정 212) - a proof that drives the SHIPPED
    # declaration must be checked against the SHIPPED catalogue, or it is measuring whether
    # this box happens to have adopted it.
    cutover = load_setup(
        DEFAULT_ONTOLOGY_ROOT if ontology_root is None else ontology_root,
        **({} if catalog is None else {"catalog": catalog}))
    # 🔴 Checked HERE and not left to the write boundary. `execute_selected_scoped_batch`
    # does re-check, but only once a batch exists: an empty source would then return a
    # clean zero instead of the refusal, and a selector left on `legacy` would look like a
    # source with nothing to do. A refusal that only fires when there is work is not a
    # refusal. Reuses the cutover module's own predicate so there is one spelling of it.
    _require_declared_source(cutover, source)
    # 🔴 REFUSED BY NAME RATHER THAN SKIPPED, because this one was TYPED. The census above
    # walks every source and a retired one is simply not its business; here an operator
    # asked for this source by name, and answering with a clean zero would tell them the
    # relation is empty. `status` is the answer to a different question than
    # 「is it declared」, so it is a separate refusal with its own word.
    if cutover.snapshot.source_plans[source].status != "active":
        raise LedgerSetupError(
            "source_retired",
            f"source {source!r} is retired; its atoms stay and nothing new is read. "
            f"Set `sources.{source}.status` to 'active' to read it again.")
    for name, value in (("reset_cursor", reset_cursor), ("start_from", start_from),
                        ("retranslate", retranslate)):
        if value:
            # 🔴 THESE THREE WERE CURSOR WORDS, and there is no cursor to reset, start from
            # or replay past. Accepting them silently would let an operator ask for a rewind
            # and get a normal load, which is the "answered a different question" shape this
            # whole retirement is about. `rescope` is the tool for redoing a named part.
            raise LedgerSetupError(
                "retired_cursor_argument", f"run().{name}",
                f"{name!r} named a position in the cursor path, which no longer reads "
                f"anything (판정 163). Use `rescope` to redo a named set of rows.")
    return _run_via_events(
        engine, cutover, source=source, page_rows=fetch_rows,
        max_pages=max_batches, checkpoint=checkpoint, pace=pace)


def _run_via_events(engine, setup, source, page_rows=DEFAULT_FETCH_ROWS,
                    max_pages=None, checkpoint=None, pace=None):
    """`run()`'s body since 판정 171: the load goes down the live path.

    🔴 THE SAME KEYS, AND THE MEANINGS SAID OUT LOUD. Callers read `rows_read`, `batches`,
    `inserted`, `deduped`, `molecules` and `stopped`, so those names stay -- but a name kept
    with a changed meaning is a false log, so: `rows_read` is the rows STAGED as events,
    `batches` is the pages that became events, and `molecules` is gone rather than reported
    as something it no longer counts. `cursor`/`cursor_after` are gone for the same reason:
    nothing advances a position any more, and `translator_ver` is the fingerprint that
    remains.
    """
    from . import followup
    from .setup_registry import cursor_translator_version

    plan = setup.snapshot.source_plans[source]
    report = {"source": source, "relation": plan.relation, "batches": 0, "rows_read": 0,
              "inserted": 0, "deduped": 0, "max_queue_depth": 0, "stopped": False,
              "translator_ver": cursor_translator_version(setup.snapshot, source),
              "page_rows": page_rows}
    if not plan.frame_row_id:
        # 🔴 A VIEW THAT DOES NOT CARRY row_id CANNOT BE INITIALLY LOADED, and the refusal
        # says what to do about it rather than only that it happened (판정 171). Its LIVE
        # path is unaffected -- a new base-table row reaches it through the page key -- so
        # what is refused is the one-time load, not the source.
        report["refused"] = "no_row_id"
        report["remedy"] = (
            f"expose the base table's row_id column on {plan.relation!r}: declare it in "
            f"table_config as a view column of type string, and this load can then say "
            f"which rows are already translated.")
        return report

    pages_per_cycle, rest_seconds = resolve_pace(pace)
    started = time.perf_counter()
    after = None
    while max_pages is None or report["batches"] < max_pages:
        page = rows_missing_from_the_index(engine, setup, source, page_rows, after)
        if not page:
            break
        after = page[-1]
        report["batches"] += 1
        report["rows_read"] += len(page)
        followup.enqueue(plan.relation, page, "CREATE")
        report["max_queue_depth"] = max(report["max_queue_depth"],
                                        followup.queue_depth())
        while followup.queue_depth() >= EVENT_LOAD_QUEUE_LIMIT:
            _drain_into(engine, setup, report)
        if pages_per_cycle and rest_seconds and (
                report["batches"] % pages_per_cycle == 0):
            time.sleep(rest_seconds)
        if checkpoint is not None and checkpoint(report["rows_read"]):
            report["stopped"] = True
            logger.info("[Ledger] stopped by request after %d rows", report["rows_read"])
            break
    while followup.queue_depth():
        _drain_into(engine, setup, report)
    # 🔴 THE REFUSAL COUNTS COME WITH THE KEYS (판정 171: keep the names).
    # These three were published by the cursor driver and were LOST when the load
    # moved here, silently -- the only test of them inspected that driver's source, so
    # it stayed green while measuring a function nothing called. Restored with the
    # driver's own reasoning intact: `refused_samples` stops at `MAX_REFUSAL_SAMPLES`,
    # so "400 refused, 20 addressed" must never render as "20 refusals" -- truncation
    # read as absence. Two counts and a flag, no sentence.
    from . import gate

    report["refused_total"] = sum(gate.refusals().values())
    report["refused_samples"] = gate.samples()
    report["refused_samples_capped"] = (
        report["refused_total"] > len(report["refused_samples"]))
    # 🔴 THE THREE VALUES RIDE THE RESULT (S-69, 판정 173). The CLI must stay a
    # PRINTER: a second call from there would load the setup again and read the database
    # a second time, and a caller that stubs this function out would find the CLI still
    # doing work behind it. One read, one place, and every reader of the result gets it.
    report.update({key: value for key, value in
                   rows_not_yet_translated(engine, setup, source).items()
                   if key in ("relation_rows", "indexed_rows", "not_yet",
                              "index_names_absent_rows")})
    report["seconds"] = round(time.perf_counter() - started, 3)
    return report


def _drain_into(engine, setup, report):
    from . import followup

    done = followup.drain_once(engine, setup)
    if done is None:
        return
    for value in (done.get("sources") or {}).values():
        report["inserted"] += value.get("inserted", 0) or 0
        report["deduped"] += value.get("deduped", 0) or 0
    if done.get("cannot_follow"):
        report.setdefault("cannot_follow", []).extend(done["cannot_follow"])


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


def preview_rescope(engine, setup, source, scope_column, scope_values):
    """What a scoped redo would withdraw and what it would put back. WRITES NOTHING.

    🔴 THE TWO NUMBERS ARE NOT THE SAME QUESTION, so they are counted separately:

        withdraw  atoms this source ALREADY wrote from the rows in scope
        remake    atoms the CURRENT declaration makes from those same rows

    They differ exactly when the correction did something, which is the point of running
    this first.

    🔴 AND THE LINK IS `source_raw_ref`, NOT THE SUBJECT KEYS. Measured 2026-08-30 on the
    four sources this exists for - dt_transfer, bw_dt_seat, transfer_event, bonded_from -
    every one writes a `die` atom keyed `x, y, mat_id, mat_type` with no qualifiers, so the
    scope column (`core_wafer`, `dt_job`, `base_id`) appears NOWHERE in the atom. The atom
    says which die; it does not say which carrier's row made it. `source_raw_ref` is the
    only exact link back, and it is built in one place - `roleframe._claim_source_raw_ref` -
    so this reads the refs off a real preview rather than assembling them, where one
    character of drift would withdraw nothing and then write a duplicate, in silence.

    ⚠️ A ROW THAT NO LONGER EXISTS CANNOT BE NAMED, so its atoms are simply not in scope and
    are not withdrawn - deleting what the scope cannot name would be the unscoped act this
    tool exists to avoid. They are also NOT COUNTED here yet: "atoms whose source row is
    gone" is a different and more expensive question than "atoms outside this scope", and
    reporting the second under the first's name would be a number that lies.
    """
    from . import schema
    from .store import LedgerStore
    from .setup import preview_selected_cursor_batch
    from .runtime_v2 import _filtered_event_atoms

    plan = setup.snapshot.source_plans[source]
    scoped = _scope_predicate(plan, (scope_column, scope_values))
    read = engine.raw_connection()
    try:
        rows = _fetch_v2_lineage_rows(read, plan, scope=scoped)
    finally:
        read.rollback()
        read.close()
    result = {"source": source, "scope_column": scoped[0],
              "scope_values": len(scoped[1]), "rows_in_scope": len(rows),
              "withdraw": 0, "remake": 0, "refs": []}
    if not rows:
        return result

    frame = _v2_frame(rows)
    subjects = _v2_registration_subjects(plan, frame)
    ordered = frame.sort_values(list(plan.driver.cursor_columns))
    last = ordered.iloc[-1]
    cursor_value = {column: last[column] for column in plan.driver.cursor_columns}
    preview = preview_selected_cursor_batch(
        setup, source, frame, cursor_value, _no_join_reader(),
        known_registrations=None if subjects is None else ())
    # 🔴 THE SAME REGISTRATION BASIS AS THE LINE ABOVE, AND IT HAS TO BE. `None` there
    # means "this source declares no probe"; here it means "no snapshot was supplied", and
    # `_filtered_event_atoms` refuses that outright the moment any `register` atom appears
    # (`registration_context_required`). So a source that registers -- which is most of
    # them -- could never get a rescope PREVIEW at all, while `rescope` itself offered `()`
    # and worked. Two spellings of one question, and the preview held the wrong one from
    # `b98f0c38` (2026-08-17) until now.
    #
    # `()` is "nothing assumed already registered", which is exactly what `rescope`'s own
    # docstring says it offers: the preview counts what the apply then writes, so the two
    # have to ask on the same basis or the number shown is not the number produced.
    atoms = [atom for group in _filtered_event_atoms(
                preview.event_results, None if subjects is None else ())
             for atom in group]
    refs = sorted({str(atom.source_raw_ref) for atom in atoms})
    result["remake"] = len(atoms)
    result["refs"] = refs

    store = LedgerStore(engine)
    connection = store.connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) FROM {schema.LEDGER_TABLE} "
                "WHERE source_who = %s AND source_raw_ref = ANY(%s)",
                (source, refs))
            result["withdraw"] = int(cursor.fetchone()[0])
    finally:
        connection.rollback()
        connection.close()
    return result


#: How many distinct refs the orphan sweep reads before it calls itself a sample. A source
#: with 371,593 of them is not a request-path scan, and `count_kind` exists so the answer
#: can say which of the two it is instead of quietly being the smaller one.
ORPHAN_SCAN_LIMIT = 4000
ORPHAN_CHUNK = 1000


def _ref_row_keys(ref):
    """-> [(relation, {key: value}), ...] read OUT of one `source_raw_ref`.

    🔴 SPLIT ON THE FIRST COLON, NOT ANY COLON. Every ref element is
    `<relation>:<json of that row's identity>`, and the json routinely contains colons -
    a `run_uid` carries an ISO timestamp, a `void_uid` carries several. Splitting on the
    last colon, or on all of them, reads a relation name out of the middle of a value and
    then asks a table that does not exist.

    Reading the keys out is deliberate and is the opposite of rebuilding the ref: the
    translator owns that string (`roleframe._claim_source_raw_ref`) and one character of
    drift in a rebuilt one would report every atom as an orphan.
    """
    out = []
    for item in json.loads(ref).get("rows", []):
        cut = item.index(":")
        out.append((item[:cut], json.loads(item[cut + 1:])))
    return out


def _group_ref_identities(refs):
    """-> `(groups, owners, unreadable)` for a set of `source_raw_ref` strings.

    `groups[(relation, key_names)]` is the set of identity tuples to look for, and
    `owners[(relation, key_names, identity)]` is the refs that named it. Written once
    because the orphan count and the index backfill ask the SAME question of the SAME
    strings -- if the two grouped differently, one would index a row the other calls gone.
    """
    groups: dict = {}
    owners: dict = {}
    unreadable = 0
    for ref in refs:
        try:
            named = _ref_row_keys(ref)
        except Exception:
            unreadable += 1
            continue
        for relation, keys in named:
            names = tuple(sorted(keys))
            identity = tuple(keys[name] for name in names)
            groups.setdefault((relation, names), set()).add(identity)
            owners.setdefault((relation, names, identity), set()).add(ref)
    return groups, owners, unreadable


def _join_identities(cursor, relation, names, identities, extra_columns=()):
    """Which of these identities the relation still has. `-> [(identity, extras...)]`.

    One query per thousand rather than one per identity: three sessions share this database
    and a per-row loop is someone else's wait.

    `extra_columns` rides along for a caller that needs more than the answer to "is it
    there" -- the index backfill needs the `row_id` of the row it found. The predicate is
    the same either way, which is the point of the shared function.
    """
    columns = ", ".join('"%s"' % name for name in names)
    selected = ", ".join('"%s"' % name for name in (*names, *extra_columns))
    out = []
    items = sorted(identities, key=lambda item: [str(value) for value in item])
    for start in range(0, len(items), ORPHAN_CHUNK):
        chunk = tuple(items[start:start + ORPHAN_CHUNK])
        cursor.execute(
            'SELECT %s FROM "%s" WHERE (%s) IN %%s' % (selected, relation, columns),
            (chunk,))
        for row in cursor.fetchall():
            out.append(tuple(row[:len(names)]) if not extra_columns
                       else (tuple(row[:len(names)]), *row[len(names):]))
    return out


def count_orphan_atoms(engine, source, scan_limit=ORPHAN_SCAN_LIMIT):
    """Atoms this source wrote whose SOURCE ROW no longer exists. READ ONLY.

    🔴 THIS IS ABOUT THE SOURCE, NOT ABOUT ANY SCOPE, and the two must not be added
    together. A scope names rows; a row that was deleted cannot be named by one, so asking
    "how many of THIS scope's atoms are orphaned" has no answer - the scope is a predicate
    over a relation and the relation no longer carries the row. What can be answered is the
    source-wide question, and that is what this is.

    ⚠️ THREE COUNTS, NOT ONE, because they are three different facts and a reader who saw
    only a total could not tell them apart:

        rows_gone       row identities named by a ref that the relation no longer has
        atoms           atoms carrying those refs - what an operator would actually see
        unreadable_refs refs this could not parse at all

    An unreadable ref is NOT an orphan. Folding it in would report a bookkeeping failure
    of this function as a fact about the data.
    """
    from . import schema
    from .store import LedgerStore

    store = LedgerStore(engine)
    connection = store.connection()
    result = {"source": source, "refs_total": 0, "refs_scanned": 0,
              "count_kind": "exact", "truncated": False, "rows_gone": 0,
              "refs_gone": 0, "atoms": 0, "unreadable_refs": 0}
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(DISTINCT source_raw_ref) FROM {schema.LEDGER_TABLE} "
                "WHERE source_who = %s", (source,))
            result["refs_total"] = int(cursor.fetchone()[0])
            cursor.execute(
                f"SELECT DISTINCT source_raw_ref FROM {schema.LEDGER_TABLE} "
                "WHERE source_who = %s LIMIT %s", (source, scan_limit))
            refs = [row[0] for row in cursor.fetchall()]
            result["refs_scanned"] = len(refs)
            result["truncated"] = result["refs_total"] > len(refs)
            if result["truncated"]:
                result["count_kind"] = "sample"

            groups, owners, unreadable = _group_ref_identities(refs)
            result["unreadable_refs"] = unreadable

            gone_refs = set()
            for (relation, names), wanted in groups.items():
                found = set(_join_identities(cursor, relation, names, wanted))
                for identity in wanted - found:
                    result["rows_gone"] += 1
                    gone_refs |= owners[(relation, names, identity)]

            result["refs_gone"] = len(gone_refs)
            if gone_refs:
                cursor.execute(
                    f"SELECT count(*) FROM {schema.LEDGER_TABLE} "
                    "WHERE source_who = %s AND source_raw_ref = ANY(%s)",
                    (source, sorted(gone_refs)))
                result["atoms"] = int(cursor.fetchone()[0])
    finally:
        connection.rollback()
        connection.close()
    return result


def _scope_row_ids(plan, frame):
    """The physical row ids the scope read, in order, or `()`.

    Empty for a source reading a VIEW, which has no `row_id` to index by - the same
    structural absence `sources_without_row_index` reports, and the reason the caller says
    so by name rather than reporting a quiet zero.
    """
    column = plan.frame_row_id
    if not column or column not in frame.columns:
        return ()
    ids = []
    for value in frame[column].tolist():
        if value is None or value != value:            # NaN is not equal to itself
            continue
        text = str(value)
        if text:
            ids.append(text)
    return tuple(dict.fromkeys(ids))


def rescope(engine, setup, source, scope_column, scope_values, apply=False,
            withdraw=True):
    """Redo exactly the part of a source the named rows touched. Withdraw, then remake.

    `apply=False` is `preview_rescope` and writes nothing; the numbers it reports are the
    numbers this then produces, because both run the SAME preview over the SAME scope.

    🔴 THE WATERMARK DOES NOT MOVE, AND THAT IS THE WHOLE DESIGN. The write goes through
    `execute_scoped_batch`, which issues the atom statement and not the cursor statement, so
    the source's position is neither advanced to wherever the scoped rows happen to end nor
    dragged backwards to wherever they begin. A scope is almost always BEHIND the position -
    a correction arrives after the row was first read - and a watermark that moved back
    would re-read everything after it, or, on the next correction, skip it.

    🔴 THE WITHDRAWAL AND THE REMAKE ARE ONE TRANSACTION SINCE 2026-09-08 (S-60), AND THE
    REASON IS A MEASUREMENT RATHER THAN A PREFERENCE. They used to be two, in this order,
    and this docstring called that "named rather than hidden" -- but naming a hazard is not
    containing one: a remake that failed for ANY reason left the withdrawal committed and
    the rows had no atoms at all. It happened: two atoms of one `dt_job` (its `register` and
    its `has_netdie`) were gone, and only a second run of the same scope brought them back.
    Grade 1, because a failure DELETED data.

    Reordering does not fix it either. Remake-first collides with the atoms still present on
    `uq_ledger_atom`, so the write dedupes to nothing and the withdrawal then takes
    everything -- worse, and silently. The delete therefore travels to
    `store.write_batch` as `withdraw_refs` and runs inside the one commit that writes the
    new generation. Nothing outside that transaction can see between the two statements, so
    the "two generations at once" objection has no observer.

    🔴 THE WITHDRAWAL IS AIMED FROM THE INDEX, NOT FROM THE NEW TRANSLATION (S-101,
    ruling 199). It used to be aimed only at the refs the CURRENT declaration makes from the
    rows in scope, and that aim goes EMPTY in exactly the case where the old atoms most need
    to go: a row that is no longer this source's row produces no ref at all. Adding S-91's
    `exclude_when` to a source measured 5 rows in scope, 10 atoms already written and 0 refs
    previewed - so this returned before writing anything and the 10 atoms and their 5 index
    rows stayed. An EDIT that merely BLANKS the declared column arrives at the same place, so
    it was never a deployment-only door.

    The refs are therefore the union of two questions: what the new translation makes, and
    what `schema.ROW_REF_TABLE` says this source already said about these rows - the note
    taken while the row still spoke, which is the instrument `withdraw_deleted_rows` already
    aims with. A row that stops being translated is then withdrawn by the same road as a row
    that was deleted, and its index line goes with it.

    ⚠️ THE UNION, NOT THE DIFFERENCE. Ruling 199 names the difference because that is what
    this ADDS; the refs the new generation re-creates have to be withdrawn as well, or the
    old generation stands beside the new one - which is the hazard the paragraph above is
    about. It also picks up a ref that MOVED: a corrected `order_by` value spells a new ref,
    and the atom under the old one was previously left behind.

    ⚠️ AND ONLY WHERE THERE IS A ROW INDEX (판정 136). A source reading a VIEW has no
    `row_id`, so there is nothing to ask the index with and the aim is the old one; the
    return says `no_row_index` rather than reporting a quiet zero. For such a source
    `remake == 0` with `rows_in_scope > 0` is still the declaration question it always was,
    and widening it means deleting by something other than the scope - the unscoped act this
    tool exists to avoid.

    Registrations are offered on the same basis the dry-run counted them on (`()` - nothing
    assumed already registered), so `remake` and `attempted` are the same question asked
    twice. Any register atom that is in fact still there collides with `uq_ledger_atom` and
    comes back as `deduped`, which is the mechanism that already exists for exactly this.
    """
    from .store import LedgerStore
    from .setup import execute_selected_scoped_batch

    # 🔴 `withdraw=False` TRANSLATES ONCE, AND A CREATE IS EXACTLY THAT CASE (판정 166).
    # The preview exists to AIM a withdrawal: it compiles the rows to learn which refs the
    # ledger currently holds for them. A row that has just been created holds none, so that
    # first translation answers a question with no content -- and it is not free. Measured
    # 2026-09-09 on `lot_event`, the event path cost 27.16 ms/molecule against the cursor
    # path's 15.66, and the whole gap was this second pass.
    #
    # ⚠️ EDIT STILL WITHDRAWS. A corrected row DOES hold atoms, and remaking without
    # withdrawing would leave the old generation standing beside the new one.
    if withdraw:
        result = preview_rescope(engine, setup, source, scope_column, scope_values)
        refs = result.pop("refs", [])
    else:
        result, refs = {"rows_in_scope": None, "previewed": False}, None
    result.update({"applied": False, "withdrawn": 0, "forgotten": 0,
                   "attempted": 0, "inserted": 0, "deduped": 0})
    if not apply:
        return result

    plan = setup.snapshot.source_plans[source]
    scoped = _scope_predicate(plan, (scope_column, scope_values))
    store = LedgerStore(engine)

    read = engine.raw_connection()
    try:
        rows = _fetch_v2_lineage_rows(read, plan, scope=scoped)
    finally:
        read.rollback()
        read.close()
    frame = _v2_frame(rows)
    if result.get("rows_in_scope") is None:
        result["rows_in_scope"] = len(frame)
    if frame.empty:
        # 🔴 AN EMPTY SCOPE IS AN ANSWER, NOT A FAULT (S-81). A VIEW does not have to contain
        # every row of the table it reads -- measured 2026-09-09, `dt_log_transferable`
        # excludes 7,731 of `dt_log`'s 35,939 -- so a base-table event naming an excluded row
        # scopes this source to nothing at all. Falling through handed an empty frame to the
        # write boundary, which refused it as `scope.row_id: the batch does not carry
        # 'row_id'`: a missing-column error for a frame that has no columns because it has no
        # rows. It repeated every three seconds and the drain DROPPED each event.
        result["scope_empty"] = True
        return result
    scope_row_ids = _scope_row_ids(plan, frame)
    aimed = refs
    if withdraw:
        indexed = set()
        if scope_row_ids:
            indexed = {ref for who, ref
                       in store.row_refs_for(plan.relation, scope_row_ids)
                       if who == source}
        else:
            result["no_row_index"] = True
        result["indexed_refs"] = len(indexed)
        aimed = sorted(set(refs or ()) | indexed)
        if not aimed:
            # Neither the new translation nor the index says anything about these rows, so
            # there is nothing to withdraw and nothing to put in its place.
            return result
    subjects = _v2_registration_subjects(plan, frame)
    executed = execute_selected_scoped_batch(
        setup, source, frame, scoped, _no_join_reader(), store,
        known_registrations=None if subjects is None else (),
        withdraw_refs=aimed)
    written = executed.store_result
    result["withdrawn"] = int(written.get("withdrawn", 0))
    result["attempted"] = int(written.get("attempted", 0))
    result["inserted"] = int(written.get("inserted", 0))
    result["deduped"] = int(written.get("deduped", 0))
    result["applied"] = True
    if withdraw and scope_row_ids:
        # 🔴 THE INDEX ROWS GO LAST, for the reason `withdraw_deleted_rows` states: while
        # they are still here the withdrawal can be run again, and a run that dies between
        # the two leaves an index row pointing at atoms already withdrawn - which the next
        # pass reads as "nothing to withdraw" and then clears.
        #
        # Only the rows the new generation did NOT name: one it did name has just had its
        # index line rewritten by that same transaction. And only THIS source's line, because
        # the row is still there and another source reading it still speaks for it.
        spoken = {str(row_id) for _relation, row_id, _ref in executed.preview.row_refs}
        stale = [row_id for row_id in scope_row_ids if row_id not in spoken]
        if stale:
            result["forgotten"] = store.forget_row_refs(
                plan.relation, stale, source=source)
    return result


#: Rows in one staged CREATE event of an initial load. The same 1,000 the collapsed outbox
#: uses, because a page here becomes exactly one of those events.
EVENT_LOAD_PAGE_ROWS = 1000

#: How many pages may sit in the follow-up queue before the loader stops reading and drains.
#:
#: 🔴 THE QUEUE IS MEMORY (`followup` holds a deque), so an initial load of ten million rows
#: cannot simply enqueue them all -- the ruling that asked for this said so before the code
#: did. The loader therefore reads, enqueues, and BLOCKS on its own drain, so the number of
#: row ids held at once is bounded by this times the page size.
EVENT_LOAD_QUEUE_LIMIT = 4


def rows_missing_from_the_index(engine, setup, source, limit, after=None):
    """The relation's rows that the row index does not yet name, oldest id first.

    🔴 THIS IS THE PROGRESS MARKER, AND IT IS NOT A WATERMARK. A cursor says "I read up to
    here" and is wrong the moment a row arrives behind it -- the whole S-65 family. The index
    says "the ledger holds facts from THIS row", which is a statement about the row rather
    than about an ordering, so a load that dies halfway resumes by asking again and no
    position has to be trusted.

    ⚠️ IT ONLY ANSWERS FOR A SOURCE THAT CARRIES `row_id`. A source whose frame has no
    row_id writes no index rows at all, so this would offer every row forever; the caller
    checks `frame_row_id` and refuses rather than looping.
    """
    from psycopg2 import sql

    from . import schema
    from .setup import LedgerSetupError

    plan = setup.snapshot.source_plans[source]
    if not plan.frame_row_id:
        # 🔴 REFUSE, DO NOT RETURN EMPTY. A source whose frame has no row_id writes no index
        # rows, so "not in the index" is EVERY row, forever. An empty list would read as
        # "nothing left to do", which is the opposite answer.
        raise LedgerSetupError(
            "no_row_id", f"sources.{source}.read",
            f"reads {plan.relation!r}, which carries no row_id, so the row index cannot say "
            f"what has been translated; this source cannot be loaded by the event path.")
    relation = sql.SQL(".").join(
        sql.Identifier(part) for part in str(plan.relation).split("."))
    query = sql.SQL(
        "SELECT r.row_id FROM {relation} r "
        " WHERE NOT EXISTS (SELECT 1 FROM {refs} x "
        "                    WHERE x.relation = %s AND x.source_who = %s "
        "                      AND x.row_id = r.row_id) "
        "   AND (%s IS NULL OR r.row_id > %s) "
        " ORDER BY r.row_id LIMIT %s"
    ).format(relation=relation, refs=sql.Identifier(schema.ROW_REF_TABLE))
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (plan.relation, source, after, after, limit))
            return [row[0] for row in cursor.fetchall()]
    finally:
        connection.rollback()
        connection.close()


def rows_not_yet_translated(engine, setup, source, *, exact_rows=True):
    """Three values: the relation's rows, the rows the index names, and the difference.

    🔴 THIS IS THE LINE S-69 ASKED FOR, AND A CURSOR COULD NOT SAY IT.
    `rows_past_cursor` read ONE PAGE from a watermark, so a full page could only ever report
    "at least N" -- counting past a position means reading past it. The row index is a set of
    statements about ROWS, so the remainder is arithmetic, and it is EXACT.

    ⚠️ IT REFUSES A SOURCE WITHOUT `row_id` RATHER THAN ANSWERING. Such a source
    writes no index rows at all, so `relation - indexed` would be the whole table, and a
    source whose rows all arrived by the live path would be reported as one that has never
    been touched. "Cannot be counted" and "nothing has been done" are different sentences.
    """
    from psycopg2 import sql

    from . import schema

    plan = setup.snapshot.source_plans[source]
    report = {"source": source, "relation": plan.relation}
    if not plan.frame_row_id:
        report["refused"] = "no_row_id"
        report["remedy"] = (
            f"expose the base table's row_id column on {plan.relation!r}: declare it in "
            f"table_config as a view column of type string, and this count can then say "
            f"which rows are already translated.")
        return report

    relation = sql.SQL(".").join(
        sql.Identifier(part) for part in str(plan.relation).split("."))
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            # 🔴 THE PACED CENSUS MUST NOT SCAN (S-122, 판정 09-10 12:57). This ran
            # `count(*)` on the relation every tick, for every source, without resting -
            # measured on this box 1.18 s over 1.43M rows, and on a production table it is
            # never NOT scanning, so every other query queues behind it. The planner keeps
            # a free estimate of exactly this number, and an estimate is what a census
            # line is for: it says how big a thing is, not how many there are to the row.
            #
            # ⚠️ IT IS PUBLISHED AS AN ESTIMATE, not quietly swapped. `measured(exact=...)`
            # already carries that distinction to the screen, and a number that is off by a
            # few thousand while CLAIMING to be exact is worse than one that says what it
            # is. The exact count is the human CLI's (`python -m ledger census`).
            #
            # ⚠️ AND A VIEW HAS NO `reltuples`. `pg_class` holds -1 for a relation that was
            # never analysed and views are not analysed at all, so the scan stays for those
            # - a view relation was already the expensive case and is now the only one.
            estimated = None
            from_estimate = False
            if exact_rows is False:
                cursor.execute(
                    "SELECT c.reltuples::bigint FROM pg_class c "
                    "  LEFT JOIN pg_namespace n ON n.oid = c.relnamespace "
                    " WHERE c.relkind = 'r' AND c.relname = %s "
                    "   AND c.reltuples >= 0 "
                    " ORDER BY (n.nspname = current_schema()) DESC LIMIT 1",
                    (str(plan.relation).split(".")[-1],))
                row = cursor.fetchone()
                estimated = None if row is None else int(row[0])
            if estimated is None:
                cursor.execute(sql.SQL("SELECT count(*) FROM {relation}").format(
                    relation=relation))
                total = cursor.fetchone()[0]
            else:
                total = estimated
                from_estimate = True
            # 🔴 DISTINCT row_id, NOT count(*). The index is keyed
            # `(relation, row_id, source_who, source_raw_ref)` and its own comment says
            # why: ONE physical row appears under SEVERAL refs when a source emits
            # more than one sentence over different subsets. `count(*)` therefore counts
            # (row, ref) PAIRS, and subtracting pairs from rows gives a remainder that is
            # too small -- and goes NEGATIVE on a source with two sentences, which this
            # function would then have reported as an un-withdrawn deletion. Two
            # different causes wearing one number.
            # 🔴 THE COUNTER, NOT THE SCAN (S-122-b, 판정 250). `count(DISTINCT row_id)`
            # over the index was the last scan the paced census did - 2.055 s for the
            # largest source on the QA box, which is not cheaper than the relation count
            # this round already removed. The two seats that MOVE the index keep this
            # number inside the atoms' own transaction, so it is exact by construction.
            #
            # ⚠️ NULL MEANS NEVER PLANTED, so it is counted ONCE - here, by whoever asks
            # first - and maintained from then on. The exact path always counts anyway, so
            # a person's `census` both refreshes the plant and is the drift check.
            indexed = None
            if exact_rows is False:
                cursor.execute(
                    sql.SQL("SELECT {column} FROM {cursor_table} WHERE source = %s").format(
                        column=sql.Identifier(schema.ROWS_INDEXED_COLUMN),
                        cursor_table=sql.Identifier(schema.CURSOR_TABLE)),
                    (source,))
                row = cursor.fetchone()
                indexed = None if row is None else row[0]
            if indexed is None:
                cursor.execute(
                    sql.SQL("SELECT count(DISTINCT row_id) FROM {refs} "
                            " WHERE relation = %s AND source_who = %s").format(
                                refs=sql.Identifier(schema.ROW_REF_TABLE)),
                    (plan.relation, source))
                indexed = cursor.fetchone()[0]
                counted_now = True
            else:
                counted_now = False
    finally:
        connection.rollback()
        connection.close()

    # 🔴 A GROUP SOURCE COUNTS TWO DIFFERENT THINGS, so the subtraction is refused
    # rather than published. The index holds ONE entry per translated GROUP while the
    # relation holds rows, and `rows - groups` is a number with no meaning: measured on
    # `lot_event` (unit=group) it read 3,633 - 490 = 3,143 「not yet translated」 on the
    # operator's screen while the source was fully translated. That is the false-log shape,
    # and a plausible wrong number is worse than a blank.
    #
    # ⚠️ THE OTHER HALF OF THE ANSWER IS NOT BUILT: counting DISTINCT groups would make
    # them comparable, but `driver.group_by` carries LOGICAL names (`event_group_key`) and
    # the physical column behind one is resolved elsewhere. Guessing that mapping to produce
    # a number is how the wrong number got there in the first place, so the shape says what
    # it counted and stops.
    grouped = getattr(plan.driver, "unit", "row") == "group"
    report.update({"relation_rows": total, "indexed_rows": indexed,
                   "relation_rows_estimated": from_estimate,
                   "indexed_rows_counted_now": counted_now,
                   "counts": "rows vs groups" if grouped else "rows"})
    if grouped:
        report["not_comparable"] = (
            f"this source reads by group ({', '.join(plan.driver.group_by)}), so the "
            f"relation's {total} ROWS and the index's {indexed} GROUPS are different units; "
            f"the remainder is not published rather than published wrong.")
        return report
    remainder = total - indexed
    report["not_yet"] = max(remainder, 0)
    if remainder < 0:
        # ⛔ A SILENT ZERO. The index names rows the relation no longer holds -- a
        # deletion the follow-up could not withdraw. Clamping without saying so would
        # report "nothing left" for a table that is actually missing its withdrawals.
        # ⚠️ Since the count above is DISTINCT, this can no longer also mean "one row
        # under several refs" -- which it silently did until 2026-09-09, so a source with
        # two sentences reported a deletion fault that was not there.
        report["index_names_absent_rows"] = -remainder
    return report


#: The paced job that measures 「table rows · indexed rows · remainder」 for every source.
#: A NAME, because `pacing.json` is keyed by one and an operator who needs this to stop
#: crowding the database at 2am edits a cell there rather than a constant.
ROW_CENSUS_JOB = "ledger_row_census"


def measure_row_census(engine, setup, source, now=None, *, exact_rows=True):
    """One source's census, STAMPED -- what was counted, how, and when.

    🔴 THIS IS THE JOB'S WORK, NOT THE REQUEST'S (D5, 판정 180). Both numbers are
    scans: `count(*)` on a relation that may hold ten million rows, and
    `count(DISTINCT row_id)` on the index. A request that did this would be a request that
    waits for a table, so the request READS what this wrote.

    ⚠️ BOTH NUMBERS COME FROM ONE MEASUREMENT, and the remainder is their difference
    rather than a third query. Two queries a second apart can disagree -- rows arrive
    between them -- and a remainder computed from a mismatched pair is a number that was
    never true at any instant.

    A source that cannot be counted is stamped as refused rather than as zero: the whole
    point of `rows_not_yet_translated`'s refusal is that 「셀 수 없다」 and 「한 것이 없다」
    are different, and storing a 0 here would throw that away one layer later.
    """
    from datetime import datetime, timezone

    from ledger_trace import measured

    census = rows_not_yet_translated(engine, setup, source, exact_rows=exact_rows)
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    stamped = {"source": census["source"], "relation": census["relation"],
               "measured_at": stamp}
    if census.get("refused"):
        stamped["refused"] = census["refused"]
        stamped["remedy"] = census["remedy"]
        return stamped
    # ⚠️ BEFORE THE GROUPED RETURN, because this number does not have the unit problem
    # that stops the remainder being published: it counts ROWS on both sides whatever the
    # source's unit is. A source that reads by group still has rows waiting to be withdrawn.
    excluded, page = count_excluded_but_indexed(engine, setup, census["source"])
    if page:
        stamped["excluded_but_indexed"] = measured(
            excluded, exact=False,
            method=f"exclude_when over the first {page} rows, joined to the row index",
            measured_at=stamp)
    grouped = census.get("counts") == "rows vs groups"
    # ⚠️ THE METHOD IS PART OF THE NUMBER (S-122). A paced tick reads the planner's free
    # estimate and a person's `census` command counts; publishing both as `exact=True`
    # would make a figure that is off by a few thousand indistinguishable from one that is
    # not, which is the difference this field exists to carry.
    estimated = census.get("relation_rows_estimated")
    stamped["relation_rows"] = measured(
        census["relation_rows"], exact=not estimated,
        method=("pg_class.reltuples (planner estimate, no scan)" if estimated
                else ("count(*) [rows]" if grouped else "count(*)")),
        measured_at=stamp)
    # ⚠️ THE METHOD SAYS WHICH ONE ANSWERED (S-122-b). A counted value maintained inside
    # the atoms' transaction and a fresh `count(DISTINCT)` are both exact, but they are not
    # the same act, and an operator reading a census line is entitled to know which.
    from_counter = not census.get("indexed_rows_counted_now", True)
    stamped["indexed_rows"] = measured(
        census["indexed_rows"], exact=True,
        method=("rows_indexed (counted at write time)" if from_counter
                else ("count(distinct row_id) [groups]" if grouped
                      else "count(distinct row_id)")),
        measured_at=stamp)
    # 🔴 CARRIED OUT OF THE STAMPING, because `measure_and_store` is what plants the
    # counter and this dict is all it gets. The first version left the flag on the inner
    # report, so the plant never fired and every counter stayed NULL - which the gate
    # caught by finding fifteen NULLs after a full lap.
    stamped["indexed_rows_counted_now"] = bool(
        census.get("indexed_rows_counted_now"))
    # ⛔ NO REMAINDER FOR A GROUP SOURCE, and the reason travels instead of the number.
    # `rows - groups` published 3,143 「not yet translated」 for a fully translated
    # `lot_event`; a key that is simply absent leaves the cell blank, which is the honest
    # rendering of 「these two do not subtract」.
    if grouped:
        stamped["not_comparable"] = census["not_comparable"]
        return stamped
    stamped["not_yet"] = measured(
        census["not_yet"], exact=True, method="relation_rows - indexed_rows",
        measured_at=stamp)
    if census.get("index_names_absent_rows"):
        stamped["index_names_absent_rows"] = census["index_names_absent_rows"]
    return stamped


def measure_and_store(engine, setup, source, store, now=None, *, exact_rows=True):
    """Measure one source's census and store it AGAINST ITS CURRENT FINGERPRINT.

    🔴 THE ONE SEAT (S-113 ⓑ-1, ruling 221). Three loops measure a source -- the
    worker's paced tick, the sweep below, and the CLI -- and the write is now what gives a
    source its registry row, so each of them computing the fingerprint separately would be
    three spellings of 「which declaration is this row on」. `cursor_translator_version` is
    already the one spelling of the string itself; this is the one spelling of 「measure,
    then say it」.
    """
    from .setup_registry import cursor_translator_version

    census = measure_row_census(engine, setup, source, now=now, exact_rows=exact_rows)
    store.write_row_census(
        source, census,
        translator_ver=cursor_translator_version(setup.snapshot, source))
    # 🔴 PLANTED ONCE, THEN MAINTAINED (S-122-b). A source whose counter is NULL was just
    # counted exactly - by the tick, once in its life - so that number is written down and
    # the two seats that move the index keep it from then on.
    #
    # ⚠️ AND AN EXACT RUN IS THE DRIFT CHECK. `python -m ledger census` always counts, so
    # comparing what it counted with what the column claims is free - and a difference is
    # NAMED rather than silently overwritten, because a counter that quietly corrects
    # itself can never tell anybody it was wrong.
    counted = census.get("indexed_rows")
    if census.get("indexed_rows_counted_now") and counted is not None:
        drifted = store.plant_rows_indexed(source, int(counted.get("estimate", 0)
                                                       if isinstance(counted, dict)
                                                       else counted))
        if drifted is not None:
            logger.warning(
                "[Ledger] %s: rows_indexed said %d and counting says %d - the counter "
                "drifted by %d and has been corrected. Two seats move it, both inside the "
                "atoms' commit, so a difference means one of them was not reached.",
                source, drifted, int(counted.get("estimate", 0)
                                     if isinstance(counted, dict) else counted),
                drifted - int(counted.get("estimate", 0)
                              if isinstance(counted, dict) else counted))
    return census


def measure_every_source(engine, setup, store=None, now=None):
    """Measure each declared source in turn and store what it found.

    ⛔ ONE SOURCE'S FAILURE DOES NOT END THE SWEEP. A relation that was dropped, or a
    permission that changed, must cost that source's number and not every source after it --
    the shape the follow-up loop already carries, for the same reason.
    """
    from .store import LedgerStore

    writer = LedgerStore(engine) if store is None else store
    done = []
    for source in sorted(setup.snapshot.source_plans, key=str):
        # ⛔ NAMED, NOT SILENT (S-103). A retired source has nothing arriving, so counting
        # 「rows not yet translated」 for it would publish a remainder that will never move
        # and read as a backlog. Saying which ones were skipped is what keeps that from
        # looking like the sweep quietly losing sources.
        if setup.snapshot.source_plans[source].status != "active":
            logger.info("[Ledger] census skips %s: retired", source)
            continue
        try:
            measure_and_store(engine, setup, source, writer, now=now)
        except Exception as exc:
            logger.warning("[Ledger] census of %s failed: %s", source, exc)
            continue
        done.append(source)
    return done


def load_via_events(engine, setup, source, page_rows=EVENT_LOAD_PAGE_ROWS,
                    queue_limit=EVENT_LOAD_QUEUE_LIMIT, max_pages=None, apply=False):
    """Translate everything this source has NOT translated, down the live path.

    🔴 THE CURSOR IS NOT TOUCHED, AND THAT IS THE POINT (판정 163). Every repair of the last
    week -- S-53, S-54, S-65 and its letters, S-66, S-74 -- was the cursor path being told
    something the outbox already knew. An initial load that stages CREATE events uses the one
    path that is told, so "did this row sort before or after the watermark" stops being a
    question anybody can get wrong.

    ⚠️ AND IT IS RESUMABLE WITHOUT A POSITION. The rows it offers are the rows the index does
    not name, so a run that dies leaves nothing to reconcile: the next run asks the same
    question and gets the remainder.
    """
    from . import followup

    plan = setup.snapshot.source_plans[source]
    report = {"source": source, "relation": plan.relation, "pages": 0, "rows": 0,
              "inserted": 0, "deduped": 0, "max_queue_depth": 0, "applied": bool(apply),
              "page_rows": page_rows, "queue_limit": queue_limit}
    if not plan.frame_row_id:
        report["refused"] = "no_row_id"
        return report

    after, started = None, time.perf_counter()
    while max_pages is None or report["pages"] < max_pages:
        page = rows_missing_from_the_index(engine, setup, source, page_rows, after)
        if not page:
            break
        after = page[-1]
        report["pages"] += 1
        report["rows"] += len(page)
        if not apply:
            continue
        followup.enqueue(plan.relation, page, "CREATE")
        report["max_queue_depth"] = max(report["max_queue_depth"],
                                        followup.queue_depth())
        # Drain down to the limit before reading more: the queue is memory, and this is what
        # keeps the number of row ids held at once bounded rather than the table's size.
        while followup.queue_depth() >= queue_limit:
            done = followup.drain_once(engine, setup)
            if done is None:
                break
            for value in (done.get("sources") or {}).values():
                report["inserted"] += value.get("inserted", 0) or 0
                report["deduped"] += value.get("deduped", 0) or 0
    while apply and followup.queue_depth():
        done = followup.drain_once(engine, setup)
        if done is None:
            break
        for value in (done.get("sources") or {}).values():
            report["inserted"] += value.get("inserted", 0) or 0
            report["deduped"] += value.get("deduped", 0) or 0
    report["seconds"] = round(time.perf_counter() - started, 3)
    return report


#: How many distinct refs one paced cycle of the index backfill reads.
INDEX_BACKFILL_CHUNK = 1000

#: How many unindexable refs the report NAMES before it stops listing them. A count says how
#: big the hole is; the names say which rows are in it, and an operator cannot act on the
#: first without a few of the second.
INDEX_BACKFILL_SAMPLE = 20


def sources_without_row_index(setup, *, relation=None, source=None):
    """Which sources this system can NEVER index or withdraw by row, and why. ONE answer.

    🔴 BOTH ENDS ASK IT, SO BOTH ENDS MUST ASK IT HERE (판정 138 ㉣). The delete step asks
    per RELATION -- that is what the outbox names -- and the retroactive index asks per
    SOURCE. Two spellings of "does this one have a row index" is how they come to disagree,
    and the disagreement would be silent: the backfill would try a column the read cannot
    supply while the delete reported nothing owed.

    A source's relation is a VIEW with no `row_id` (판정 138), so the absence is structural
    rather than a gap: nothing writes an outbox DELETE for a view. It is NAMED because a
    quiet zero and "there was nothing to withdraw" are the same pixel.
    """
    plans = getattr(getattr(setup, "snapshot", None), "source_plans", None) or {}
    return sorted(
        name for name, plan in plans.items()
        if not getattr(plan, "frame_row_id", None)
        and (relation is None or plan.relation == relation)
        and (source is None or name == source))


def index_existing_refs(engine, source, setup=None, apply=False, pace=None,
                        chunk=INDEX_BACKFILL_CHUNK):
    """Recover `(relation, row_id) -> source_raw_ref` for atoms written before the index.

    🔴 ONE-OFF AND PACED, because it reads every distinct ref a source ever wrote and joins
    each identity back against the source table. It is not on any request path, nobody is
    waiting for it, and the pace comes from the same declaration every other long job reads.

    🔴 A REF THAT WILL NOT JOIN IS NOT A FAILURE OF THIS JOB. It means the physical row is
    already gone -- the atom was ALREADY an orphan before the index existed, and this could
    not have caught it either way. Those are counted and NAMED (`unindexable_sample`) and
    left exactly where they are: no delete event was ever seen for them, and 「투영은 지워도
    기록은 안 된다」. Folding them into a failure count would report a fact about the data as
    a fault of the tool.

    ⚠️ IT USES THE SAME GROUPING AND THE SAME JOIN AS `count_orphan_atoms`. If the two asked
    differently, this would index a row that one calls present and the other calls gone.

    `apply=False` reports what it would write and writes nothing.
    """
    from . import schema
    from .source_preparation import FRAME_ROW_ID_COLUMN
    from .store import LedgerStore

    units, rest = resolve_pace(pace)
    store = LedgerStore(engine)
    # 🔴 A DRY RUN THAT ANSWERS `0` ANSWERS NOTHING. 「저장 전에 무엇이 도나」 -- the point of
    # running this without `--apply` is to learn the size of the job, so `would_index` is
    # counted on both paths and `indexed` counts only what was written.
    result = {"source": source, "refs_total": 0, "refs_read": 0,
              "would_index": 0, "indexed": 0,
              "unreadable_refs": 0, "unindexable_refs": 0, "unindexable_sample": [],
              "no_row_index": [], "applied": bool(apply), "pace": pace or "fast"}
    # 🔴 THE SAME ANSWER THE DELETE STEP GETS (판정 138 ㉣). A source whose relation carries
    # no `row_id` cannot be indexed by one, and joining for it would ask the read for a
    # column it does not have -- which is the `UndefinedColumn` this whole round is about.
    # It is named and skipped, not attempted and not silently zero.
    if setup is None:
        # 🔴 `None` MUST NOT ANSWER `[]`. Without a setup this helper has no plans to look
        # at, so it says "nothing lacks a row index" -- a vacuous answer that reads exactly
        # like a clean one and then dies on `UndefinedColumn` inside the join. The CLI is
        # the caller that omits it, so the default root is loaded here, through the same
        # function every other entry point uses.
        from .setup import load_setup

        setup = load_setup()
    result["no_row_index"] = sources_without_row_index(setup, source=source)
    if result["no_row_index"]:
        return result
    connection = store.connection()
    try:
        with connection.cursor() as cursor:
            # An install that has not run a translation since the index was added has no
            # table to write into, and `UndefinedTable` out of a paced job is a worse
            # answer than making it. Same DDL as `ensure_schema`, called rather than copied.
            schema.ensure_row_ref_table(cursor)
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(DISTINCT source_raw_ref) FROM {schema.LEDGER_TABLE} "
                "WHERE source_who = %s", (source,))
            result["refs_total"] = int(cursor.fetchone()[0])
        offset = 0
        done = 0
        while True:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT DISTINCT source_raw_ref FROM {schema.LEDGER_TABLE} "
                    "WHERE source_who = %s ORDER BY source_raw_ref LIMIT %s OFFSET %s",
                    (source, chunk, offset))
                refs = [row[0] for row in cursor.fetchall()]
            if not refs:
                break
            offset += len(refs)
            result["refs_read"] += len(refs)
            _index_one_chunk(connection, store, source, refs, result, apply)
            done += 1
            if units is not None and done >= units:
                done = 0
                if rest:
                    time.sleep(rest)
    finally:
        connection.rollback()
        connection.close()
    return result


def _index_one_chunk(connection, store, source, refs, result, apply):
    """One paced unit: group, join, write. The unit is where resuming is exact."""
    from .source_preparation import FRAME_ROW_ID_COLUMN

    groups, owners, unreadable = _group_ref_identities(refs)
    result["unreadable_refs"] += unreadable
    pairs = []
    resolved = set()
    with connection.cursor() as cursor:
        for (relation, names), wanted in groups.items():
            for identity, row_id in _join_identities(
                    cursor, relation, names, wanted,
                    extra_columns=(FRAME_ROW_ID_COLUMN,)):
                if row_id is None:
                    continue
                resolved.add((relation, names, identity))
                for ref in owners[(relation, names, identity)]:
                    pairs.append((relation, str(row_id), ref))
    missing = [key for key in owners if key not in resolved]
    result["unindexable_refs"] += len(missing)
    for relation, names, identity in missing[:max(
            0, INDEX_BACKFILL_SAMPLE - len(result["unindexable_sample"]))]:
        result["unindexable_sample"].append(
            {"relation": relation,
             "identity": dict(zip(names, [str(value) for value in identity]))})
    result["would_index"] += len(pairs)
    if not apply or not pairs:
        return
    store._write_row_refs(connection, source, pairs)
    connection.commit()
    result["indexed"] += len(pairs)


def withdraw_deleted_rows(engine, setup, relation, row_ids, apply=False):
    """Withdraw the atoms of physical rows that are GONE. No remake -- see below.

    운영에서는 아무것도 적지 않습니다 -- 표에서 행이 사라지면 원장에서 그 행의 사실이 걷힙니다.

    🔴 WHY THIS IS NOT `rescope`, SINCE S-101. Both aim with the same instrument now:
    `schema.ROW_REF_TABLE`, written while the row was still there, in the same transaction as
    the atoms it names. What separates them is the ROW, not the aim. A scope selects rows
    FROM the relation and re-translates them; a deleted row cannot be selected, so there is
    nothing to scope and nothing to remake.

    That is also why this drops the index line for EVERY source (`forget_row_refs` with no
    `source`) while a rescope drops only its own: a gone row is gone for everybody, and a row
    one source stopped translating is still there for the rest.

    Until S-101 the difference was larger and was stated here as the reason this function
    exists: `rescope` aimed at the CURRENT translation, so it could not withdraw for a row
    that no longer produced a ref. It could not do that for an EXCLUDED row either, which is
    the defect ruling 199 named -- the sentence was true about deletions and false as a
    statement about what a scope can be aimed with.

    🔴 AND THERE IS NO REMAKE HALF, so `store.withdraw` rather than `write_batch`: nothing
    is being replaced, and a transaction that paired a delete with an empty write would be
    asserting a replacement that does not exist.

    ⚠️ THE INDEX ROWS GO LAST. While they are here the withdrawal can be run again; a run
    that dies between the two leaves an index row pointing at atoms already withdrawn, which
    the next pass reads as "nothing to withdraw" and then clears. Dropping them first would
    make a failed run unrepeatable.

    `apply=False` reports what it would do and writes nothing.
    """
    from .store import LedgerStore

    store = LedgerStore(engine)
    ids = [str(item) for item in (row_ids or ()) if item]
    result = {"relation": relation, "rows": len(ids), "applied": False,
              "sources": {}, "forgotten": 0, "no_row_index": []}
    # 🔴 A SOURCE WITH NO ROW INDEX IS NAMED, NOT PASSED OVER IN SILENCE (판정 136). A source
    # reading a VIEW has no `row_id` to index by, so this step can do nothing for it -- and
    # a quiet zero would be indistinguishable from "there was nothing to withdraw". The
    # absence is structurally correct (nothing writes an outbox DELETE for a view), which is
    # the reason to say it plainly rather than to treat it as a gap.
    result["no_row_index"] = sources_without_row_index(setup, relation=relation)
    if not ids:
        return result
    by_source: dict = {}
    for source_who, ref in store.row_refs_for(relation, ids):
        by_source.setdefault(source_who, set()).add(ref)
    for source in sorted(by_source):
        result["sources"][source] = {"refs": len(by_source[source]), "withdrawn": 0}
    if not apply or not by_source:
        return result
    for source in sorted(by_source):
        result["sources"][source]["withdrawn"] = store.withdraw(
            source, sorted(by_source[source]))
    result["forgotten"] = store.forget_row_refs(relation, ids)
    result["applied"] = True
    return result


def resolve_pace(name, paces=None):
    """The shared pacing table, with this module's refusal shape.

    🔴 THE TABLE MOVED OUT when ingestion became the second caller - one table, every long
    job. What stays here is the translation of its refusal into `LedgerSetupError`, because
    every other refusal on this path is one and a caller that had to catch two exception
    types for "you asked for something undeclared" would eventually catch only one.
    """
    from .setup import LedgerSetupError

    import pacing

    try:
        return pacing.resolve(name, paces)
    except pacing.UnknownPace as exc:
        raise LedgerSetupError("unknown_pace", "pace", str(exc)) from exc


def load_paces(path=None):
    import pacing

    return pacing.load_paces(path)


@dataclass(frozen=True)
class TestRunReading:
    """What a test run READ, as values.

    🔴 IT REPLACED `(rows_read, preview_or_None)` BECAUSE THAT PAIR COULD NOT SAY WHAT
    HAPPENED ANY MORE. `None` used to mean exactly one thing - the relation handed back no
    rows - and once the run may read ONWARD it has to distinguish "read nothing" from
    "read a thousand rows and compiled none of them". The first is an empty table; the
    second is a declaration meeting rows it cannot use, and they need opposite moves.

    `preview` is the batch that ANSWERED - the first page that compiled a molecule, or the
    last one read if none did. `refusals` accumulates across every page walked, so a head
    of empty rows is counted even though the answer came from further in.
    """
    rows_read: int
    pages: int
    preview: Any
    refusals: tuple
    #: The key columns of every row on the page that answered, so a refusal's position can
    #: be turned into the key an operator looks up. Empty unless a sample was asked for.
    page_keys: tuple
    #: A few of the rows this run actually READ, as values (S-92). The owner asked for
    #: 「체크한 로우들」 and the answer was a count: the page was in memory and thrown away.
    #: Key columns first, then the columns the declaration reads - not the whole row, which
    #: would put a source's every column through a screen nobody asked to see.
    rows_sample: tuple
    #: Rows the preparer's marker removed, or `None` where this source declares no
    #: marker - "not measured" and "measured, none" are different answers.
    excluded_rows: Any

    # 🔴 NO FIELD DEFAULTS. There is exactly one place that builds this and it passes all
    # five, so a default is a value nothing takes - and a mutant that changed one proved
    # it by staying green. A default here would also be the wrong shape twice over:
    # `excluded_rows = 0` would claim "measured, none" for a source that declares no
    # marker at all.


def _sample_columns(plan) -> tuple:
    """The columns a sample shows: the page key first, then what the declaration reads.

    🔴 NOT THE WHOLE ROW. A source relation can be forty columns wide and the question the
    sample answers is 「which rows did you check」 - so it shows the ones that identify a row
    and the ones the declaration actually looks at. Everything else would be a payload the
    screen never asked for.
    """
    columns: list = []
    for name in (_page_key(plan),) + tuple(plan.driver.cursor_columns):
        if name and name not in columns:
            columns.append(str(name))
    occurred = getattr(plan.driver, "occurred_at", None)
    for name in (getattr(occurred, "column", None),):
        if name and name not in columns:
            columns.append(str(name))
    return tuple(columns)


def _rows_sample(plan, rows, limit: int) -> tuple:
    """`limit` of `rows`, cut to the sample columns. Reads nothing - `rows` is in hand."""
    if limit <= 0 or not rows:
        return ()
    columns = _sample_columns(plan)
    sample = []
    for row in rows[:limit]:
        if not isinstance(row, Mapping):
            continue
        sample.append({name: row.get(name) for name in columns if name in row})
    return tuple(sample)


def preview_first_batch(engine, setup, source, fetch_rows=PREVIEW_FETCH_ROWS,
                        sample_rows: int = 0):
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
    page_key = _page_key(plan)
    rows_read = pages = 0
    refusals: list = []
    sampled: tuple = ()
    page_keys: tuple = ()
    excluded = None
    answered = None
    after = None
    read = engine.raw_connection()
    try:
        while pages < PREVIEW_MAX_PAGES:
            rows = _fetch_v2_lineage_page(read, plan, after, fetch_rows)
            if not rows:
                break
            complete, dropped = _cut_on_group_boundary(rows, fetch_rows, key=page_key)
            # A page that is ENTIRELY one group cannot be cut down; fetch that group
            # whole, so a molecule is never previewed
            # in halves.
            if not complete and dropped is not None:
                complete = _fetch_v2_lineage_group(read, plan, dropped)
            if not complete:
                break
            pages += 1
            rows_read += len(complete)
            # 🔴 THE FIRST PAGE THAT ANSWERED, AND NO EXTRA READ (S-92). These rows are
            # already in memory; the run used to count them and drop them, which is why
            # the screen could say 「200 rows」 and not 「which 200」.
            if sample_rows and not sampled:
                sampled = _rows_sample(plan, complete, sample_rows)
            # 🔴 THE WHOLE PAGE'S KEYS, SO A REFUSAL CAN BE LOOKED UP (S-92 판정 251). An
            # operator finds a row in their table by its KEY, not by a position in a frame
            # - and a refusal can point at a row past the end of the sample, so the sample
            # alone cannot answer it. Keys only, never the row: this is a lookup aid.
            if sample_rows and not page_keys:
                page_keys = _rows_sample(plan, complete, len(complete))
            frame = _v2_frame(complete)
            subjects = _v2_registration_subjects(plan, frame)
            known = None if subjects is None else ()
            ordered = frame.sort_values(list(plan.driver.cursor_columns))
            last = ordered.iloc[-1]
            cursor_value = {column: last[column]
                            for column in plan.driver.cursor_columns}
            answered = preview_selected_cursor_batch(
                setup, source, frame, cursor_value, _no_join_reader(),
                known_registrations=known)
            refusals.extend(answered.refusals)
            if answered.excluded_rows is not None:
                excluded = (excluded or 0) + answered.excluded_rows
            if answered.molecule_count >= PREVIEW_MIN_MOLECULES:
                break
            if len(rows) < fetch_rows:
                break                       # the relation ended inside this page
            after = complete[-1][page_key]
    finally:
        # Every statement above is a SELECT; ending the transaction rather than leaving it
        # open is the same lock boundary the run keeps before it writes.
        read.rollback()
        read.close()
    return TestRunReading(rows_read=rows_read, pages=pages, preview=answered,
                          refusals=tuple(refusals), excluded_rows=excluded,
                          rows_sample=sampled, page_keys=page_keys)


def count_rows_missing(engine, setup, source, column, fetch_rows=PREVIEW_FETCH_ROWS):
    """Of the page a test run reads, how many rows leave `column` empty. `(missing, read)`.

    🔴 THE TEST RUN COULD ONLY SAY "IT IS EMPTY", AND THE OWNER'S ANSWER WAS "IT IS NOT".
    Both were true: one row of two hundred was empty and the compile stops at the first,
    so a page that is 199 parts fine was reported as a failed declaration. Without a
    count, an operator cannot tell "my declaration is wrong" from "one row of my source is
    blank" - and those need opposite actions. The ledger has not run in production for a
    month (owner, 2026-09-04).

    ⚠️ IT ASKS THE SAME PAGE, THE SAME WAY. Same fetch, same order, same size as
    `preview_first_batch`, so the number describes the rows the refusal came from rather
    than some other reading of the relation.

    ⚠️ AND THE SAME PREDICATE. `is_blank_source_value` is imported from the preparer that
    raised, not respelled here - two spellings of "empty" would disagree on exactly the
    values this question is about. S-91 moved those two lines INTO that function so the
    declaration's `exclude_when` asks with them too, rather than growing a third spelling.
    """
    from .source_preparation import is_blank_source_value

    plan = setup.snapshot.source_plans[source]
    read = engine.raw_connection()
    try:
        rows = _fetch_v2_lineage_page(read, plan, None, fetch_rows)
    finally:
        read.rollback()
        read.close()
    if not rows:
        return 0, 0
    missing = 0
    for row in rows:
        value = row.get(column) if isinstance(row, dict) else None
        if is_blank_source_value(value):
            missing += 1
    return missing, len(rows)


def count_excluded_but_indexed(engine, setup, source, fetch_rows=PREVIEW_FETCH_ROWS):
    """Of the page a test run reads, how many rows the declaration now EXCLUDES are still
    indexed. `(excluded_and_indexed, rows_read)`.

    🔴 THIS IS THE COST OF A DECLARATION CHANGE, MADE VISIBLE (ruling 199). Adding
    `exclude_when` to a live source does not un-write what the source already said: those
    rows keep their atoms until a scope is run over them. Until S-101 a scope could not even
    do it, and there was still no number saying how much was waiting. Zero and 「nobody has
    counted」 are different sentences, and an operator deciding whether to change a
    declaration is deciding about exactly this.

    ⚠️ A SAMPLE, AND IT SAYS SO. The other census numbers are full scans; this one asks the
    SAME PAGE `count_rows_missing` reads, in the same order and the same size, because
    「blank」 is a PYTHON predicate (`is_blank_source_value`, 판정 194 ㉢ made it one function
    on purpose) and asking a whole relation would mean spelling it a second time in SQL. Two
    spellings disagree exactly about the values in dispute, so the number is stamped
    `exact=False` with its method rather than the predicate being duplicated. Ruling of
    2026-09-09: ⓑ, with ⓐ (a scored SQL predicate) waiting for S-104.

    Empty for a source that declares no clause, and for one with no row index - in both the
    question has no subject, which is not the same as an answer of zero.
    """
    from .source_preparation import is_blank_source_value
    from .store import LedgerStore

    plan = setup.snapshot.source_plans[source]
    columns = [clause.get("column")
               for clause in getattr(plan.driver.preparation, "exclude_when", ())
               if isinstance(clause, Mapping) and clause.get("column")]
    if not columns or not plan.frame_row_id:
        return 0, 0
    read = engine.raw_connection()
    try:
        rows = _fetch_v2_lineage_page(read, plan, None, fetch_rows)
    finally:
        read.rollback()
        read.close()
    if not rows:
        return 0, 0
    excluded = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if any(is_blank_source_value(row.get(column)) for column in columns):
            row_id = row.get(plan.frame_row_id)
            if row_id is not None:
                excluded.append(str(row_id))
    if not excluded:
        return 0, len(rows)
    indexed = LedgerStore(engine).indexed_row_ids(plan.relation, excluded, source)
    return len(indexed), len(rows)


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
    on the SYMPTOM (`completed_groups` in the deleted cursor driver) instead of an
    assertion here
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


def _scope_predicate(plan, scope):
    """Validate a scope against the DECLARATION and return `(column, values)` or None.

    🔴 AN UNDECLARED COLUMN IS REFUSED, NOT ANSWERED WITH ZERO. A typo that returns
    "0 rows" reads to the operator as "nothing to correct here", and they walk away
    believing the fix landed - which is the exact shape this tool exists to stop. The
    allow-list is `base_select_columns`, the columns the source's own declaration says it
    reads, so no column name is written in this file.

    `LedgerSetupError` is imported here rather than at module scope for the reason every
    other raise site in this file does it: `ledger.setup` imports back into this module,
    and a module-level import turns that into a cycle.
    """
    if not scope:
        return None
    from .setup import LedgerSetupError
    from .source_preparation import base_select_columns
    column, values = scope
    column = str(column)
    declared = base_select_columns(plan)
    if column not in declared:
        raise LedgerSetupError(
            "scope_column_not_declared", column,
            f"'{column}' is not a column this source reads. Declared: "
            f"{', '.join(declared)}")
    values = list(values or ())
    if not values:
        raise LedgerSetupError(
            "scope_values_empty", column,
            "a scope with no values would select nothing; omit the scope instead")
    return column, values


def _fetch_v2_lineage_rows(connection, plan, *, after=None, group_value=None,
                           limit=None, scope=None):
    """Read physical catalog columns with identifier-safe psycopg2 composition.

    🔴 `scope` NARROWS WHICH ROWS, AND IT IS NOT `limit`. `limit` bounds how much is read
    and already means three different things across the CLIs; this says WHICH rows, by a
    column the declaration names. It is ANDed with the paging predicate rather than
    replacing it, so paging and restartability are untouched - a scoped run still walks
    the page key in order and can resume.
    """
    from psycopg2 import sql

    from .source_preparation import base_select_columns
    columns = base_select_columns(plan)
    scoped = _scope_predicate(plan, scope)
    # The page key leads the ORDER BY so that its groups are CONTIGUOUS -- that
    # contiguity is the whole basis on which `_cut_on_group_boundary` may drop a trailing
    # group, and the caller may resume with `> after`.
    page_key = _page_key(plan)
    order = tuple(dict.fromkeys((page_key, *plan.driver.order_by)))
    select_sql = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    relation_sql = sql.SQL(".").join(
        sql.Identifier(part) for part in plan.relation.split("."))
    clauses = []
    params = []
    if group_value is not None:
        clauses.append(sql.SQL("{} = %s").format(sql.Identifier(page_key)))
        params.append(group_value)
    elif after is not None:
        clauses.append(sql.SQL("{} > %s").format(sql.Identifier(page_key)))
        params.append(after)
    if scoped is not None:
        clauses.append(sql.SQL("{} = ANY(%s)").format(sql.Identifier(scoped[0])))
        params.append(scoped[1])
    where_sql = (sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)
                 if clauses else sql.SQL(""))
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
            # 🔴 `or ""` HERE IS NOT `crud.is_blank_value`, AND ON THIS PATH THE DIFFERENCE
            # IS REACHABLE. `values` comes from `frame[column].tolist()` - the SOURCE
            # ROWS - so whatever the probe column actually holds arrives here. `or ""`
            # swallows every falsy value before `str` sees it, so a probe column holding
            # exactly `0` or `False` reads as blank and the subject is skipped with no
            # error and no log line.
            #
            # NOT A DEFECT TODAY, MEASURED 2026-09-03: every probe column the shipped
            # declaration names is an identifier - `dt_job`, `lot_id`, `waferids` - and an
            # identifier is never `0`. But the grammar constrains `columns` to a list of
            # NAMES and says nothing about their type, so declaring a numeric probe column
            # is one config line away, and the day it happens this loses rows silently.
            # Left as it is on the lead PM's ruling (report it, do not fix it); what makes
            # it safe is the declaration, not this line.
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
    # 🔴 S-88 — THE CLI IS A PROCESS TOO, and it must not need the daemon to have run
    # first: a fresh install driven by `--source X` gets the schema the daemon would have
    # ensured. Here rather than in `run()` for two reasons — `run()` is a LIBRARY function
    # and a caller does not expect DDL from it, and every branch below (`rescope`,
    # `--via-events`, the plain load) writes to the ledger, so one call at the entry
    # point covers what three inside would.
    #
    # ⛔ AND IT CANNOT GO BEFORE THE REFUSALS. `test_v2_backfill_refuses_reset_controls
    # _before_store_access` is right: a refusal that fires after the store has been
    # opened is a report, not a refusal. The parser refuses first; this runs once the
    # arguments are known good.
    # One import for the whole function. Two branches imported `load_setup`
    # themselves under two spellings (`load_setup` and `_load_setup`), which is the
    # 「same thing, two names」 shape -- and a function-local import binds only on the
    # branch that runs, so reading the name anywhere else is an UnboundLocalError.
    from .setup import DEFAULT_ONTOLOGY_ROOT, LedgerSetupError, load_setup

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
    parser.add_argument("--pace", default=None,
                        help="fast (default, unchanged) | slow | trickle - yield between "
                             "pages so the database stays free for everything else. "
                             "Declared in ledger/pacing.json")
    parser.add_argument("--scope-column", default=None,
                        help="redo only the rows whose <column> is one of --scope-values; "
                             "the column must be one this source's read declares")
    parser.add_argument("--scope-values", default=None,
                        help="comma-separated values of --scope-column")
    parser.add_argument(
        "--via-events", action="store_true",
        help="load everything the row index does not yet name by staging CREATE events "
             "(the live path) instead of walking the cursor; the cursor is not touched")
    parser.add_argument("--apply", action="store_true",
                        help="with --scope-column: withdraw and remake for real. Without "
                             "it the scope is a dry-run and writes nothing")
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

    # 🔴 S-88. The arguments are known good by here (the destructive gate above is the
    # one that must precede store access), so the schema can be brought up to date
    # before any branch below writes. Catalogue-first: a run with nothing to add costs
    # one query and takes no lock.
    from .store import LedgerStore

    LedgerStore(engine).ensure_schema()

    if args.scope_column or args.scope_values:
        # A SCOPE IS NOT THE FORWARD SCAN AND DOES NOT SHARE ITS ARGUMENTS. Paging,
        # batching and the cursor all belong to the scan; a scope names rows. Falling
        # through to `run` with a scope it ignores would read as "redid that carrier"
        # while re-reading the whole source from the watermark.
        if not (args.scope_column and args.scope_values):
            raise LedgerSetupError(
                "scope_incomplete", "scope",
                "--scope-column and --scope-values are one argument in two halves; "
                "a column with no values selects nothing and values with no column "
                "cannot be matched")
        values = [item.strip() for item in args.scope_values.split(",") if item.strip()]
        setup = load_setup(args.ontology_root)
        scoped = rescope(engine, setup, args.source, args.scope_column, values,
                         apply=args.apply)
        logger.info("[Ledger] %s", scoped)
        if not args.apply:
            logger.info("[Ledger] dry-run: nothing was written. Re-run with --apply.")
        return 0

    if args.via_events:
        # 🔴 THE LOAD USES THE PATH THAT IS TOLD (판정 163). The cursor path has to work out
        # what the outbox already knows, which is what every repair of the last week was.
        setup = load_setup(args.ontology_root)
        report = load_via_events(engine, setup, args.source, apply=args.apply)
        logger.info("[Ledger] %s", report)
        if not args.apply:
            logger.info("[Ledger] dry-run: nothing was staged. Re-run with --apply.")
        return 0

    result = run(engine, source=args.source, fetch_rows=args.fetch_rows, pace=args.pace,
                 reset_cursor=args.reset_cursor, start_from=args.start_from,
                 max_batches=args.max_batches, ontology_root=args.ontology_root)
    beat(result)

    logger.info("[Ledger] %s", result)
    # 🔴 THREE VALUES, NOT A SILENCE (S-69, 판정 173). `census`, `gate_note`
    # and `lag_note` were the cursor driver's keys; nothing has produced them since
    # 판정 171, so two of those lines printed the word "None" and the third could
    # never fire. And "nothing was staged" ALONE is the very silence S-69 named -- it
    # reads the same whether the table is empty, already translated, or uncountable.
    # The index answers all three at once.
    if result.get("refused"):
        logger.info("[Ledger] not counted (%s): %s",
                    result["refused"], result.get("remedy"))
    elif "relation_rows" in result:
        logger.info("[Ledger] relation rows %s | indexed %s | not yet translated %s",
                    result["relation_rows"], result["indexed_rows"], result["not_yet"])
        if result.get("index_names_absent_rows"):
            logger.warning(
                "[Ledger] the index names %s row(s) the relation no longer holds",
                result["index_names_absent_rows"])
    return 0


if __name__ == "__main__":                                       # pragma: no cover
    sys.exit(main())
