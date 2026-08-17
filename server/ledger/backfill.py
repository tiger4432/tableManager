"""The backfill drivers - cursor loops that never cut a molecule in half.

    conda run -n assy_manager python -m ledger.backfill --source lot_event
    conda run -n assy_manager python -m ledger.backfill --source void_obs
    conda run -n assy_manager python -m ledger.backfill --source dt_log

🔴 THREE GRAMMARS, ONE ENTRY POINT (ruling R-2026-08-14-D)
------------------------------------------------------------
`run()` dispatches on the source's declared `kind` and there are three drivers under it:

  * `_run_lineage` - `lot_event` and its kin. A molecule is a GROUP of source rows sharing
    an `event_time`, so the cursor is a world time and the batch has to be cut on a group
    boundary (everything below).
  * `_run_observation` - `void_obs`, `delam_obs`. One row IS one utterance, so there is no
    group to cut; what those sources need instead is a cursor that works when a bulk load
    stamps ONE `updated_at` on ninety thousand rows, which a time cursor cannot. See
    `_run_observation` for the keyset that does.
  * `_run_transfer` - `dt_log`. One row is one DIE and the atom unit is the JOB-RUN, so
    rows are grouped by a DECLARED column and the cursor is that column's value. It is the
    lineage driver's group cut with the group named by the declaration instead of being
    the time column - `_cut_on_group_boundary` is shared between them for exactly that
    reason.

They share everything that carries a rule: the molecule scope is opened by the DRIVER in
all three (ruling R-H-bis 3), registrations are looked up once per page in all three, and
all three write through `store.write_batch`, so "atoms and cursor in one transaction" has
one implementation rather than one per grammar.

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


def run(engine, cfg, source="lot_event", fetch_rows=DEFAULT_FETCH_ROWS,
        reset_cursor=False, start_from=None, max_batches=None, probe_lag=True):
    """Translate everything past the cursor. Returns a `BackfillResult`.

    Dispatches on the source's DECLARED grammar (`kind`), which defaults to `lineage` -
    so every call written before ruling R-2026-08-14-D reaches the same driver it always
    did. An undeclared source is refused here, before either driver runs, because the
    refusal is about the DECLARATION and neither grammar owns it.

    `reset_cursor=True` deliberately re-reads work that is already done - it is how net 2
    of the idempotency argument gets exercised, and how an operator re-translates after a
    rule change (the new `source_translator_ver` makes the new atoms distinct from the
    old ones, which is correct: they are different claims made by different rules).
    """
    from . import config as ledger_config
    from . import gate

    source_cfg = ledger_config.source_config(cfg, source)
    if source_cfg is None:
        gate.refuse(source, gate.REFUSE_UNDECLARED_SOURCE,
                    f"source {source!r} has no declaration in "
                    f"{cfg.get('__origin__', 'ledger_config.json')}; nothing was read")
        return BackfillResult(source=source, refused_source=True, atoms=0, molecules=0)

    if source_cfg.get("kind") == ledger_config.SOURCE_KIND_OBSERVATION:
        return _run_observation(engine, cfg, source, fetch_rows=fetch_rows,
                                reset_cursor=reset_cursor, start_from=start_from,
                                max_batches=max_batches, probe_lag=probe_lag)
    if source_cfg.get("kind") == ledger_config.SOURCE_KIND_TRANSFER:
        return _run_transfer(engine, cfg, source, fetch_rows=fetch_rows,
                             reset_cursor=reset_cursor, start_from=start_from,
                             max_batches=max_batches, probe_lag=probe_lag)
    if source_cfg.get("kind") == ledger_config.SOURCE_KIND_DECLARED:
        return _run_declared(engine, cfg, source, fetch_rows=fetch_rows,
                             reset_cursor=reset_cursor, start_from=start_from,
                             max_batches=max_batches, probe_lag=probe_lag)
    return _run_lineage(engine, cfg, source, fetch_rows=fetch_rows,
                        reset_cursor=reset_cursor, start_from=start_from,
                        max_batches=max_batches, probe_lag=probe_lag)


def _run_lineage(engine, cfg, source="lot_event", fetch_rows=DEFAULT_FETCH_ROWS,
                 reset_cursor=False, start_from=None, max_batches=None, probe_lag=True):
    """The ``lot_event`` reader/cursor, with an opt-in registered mapper boundary."""
    from . import config as ledger_config
    from . import gate, observability, schema
    from .chain_mapper import (
        LedgerMapperContext,
        LedgerMapperError,
        LedgerMapperRefused,
        configured_mapper,
        deterministic_source_event_context,
        mapper_execution_version,
        run_registered_mapper,
    )
    from .envelope import canonical_keys
    from .ledger_frame import atoms_from_ledger_frame
    from .store import LedgerStore
    from mappers.ledger_lot_event_mapper import group_lot_event_frames

    source_cfg = ledger_config.source_config(cfg, source)
    if source_cfg is None:
        gate.refuse(source, gate.REFUSE_UNDECLARED_SOURCE,
                    f"source {source!r} has no declaration in "
                    f"{cfg.get('__origin__', 'ledger_config.json')}; nothing was read")
        return BackfillResult(source=source, refused_source=True, atoms=0, molecules=0)

    translator_ver = ledger_config.translator_version(cfg, source)
    mapper_descriptor = configured_mapper(source_cfg)
    selected_profile = ledger_config.selected_profile(cfg, source)
    if mapper_descriptor is None:
        from .lot_event_translator import LotEventTranslator, group_molecules
    profile_id = ((source_cfg.get("chain_mapper") or {}).get("profile_id")
                  if selected_profile is not None else None)
    execution_ver = mapper_execution_version(
        translator_ver, mapper_descriptor,
        profile_id=profile_id, profile=selected_profile)
    mapper_context = LedgerMapperContext()
    if selected_profile is not None:
        from .profile_lookup_adapters import default_profile_lookup_adapters
        mapper_context = LedgerMapperContext(
            lookups=default_profile_lookup_adapters(engine))
    declared = ledger_config.declared_derivations(cfg, source)
    declared_subjects = ledger_config.declared_subject_types(cfg, source)
    batch_size = int((cfg.get("batch") or {}).get("molecules_per_transaction", 200))

    store = LedgerStore(engine)
    store.ensure_schema()

    columns = dict(source_cfg["columns"])
    columns["event_time_column"] = source_cfg["occurred_at_column"]

    read = store.connection()
    try:
        existing = store.read_cursor(read, source)
        after = start_from if start_from is not None else (
            None if reset_cursor else (existing or {}).get("cursor_value", {}).get(
                "event_time"))

        logger.info(
            "[Ledger] backfill %s | translator_ver=%s | rules=%s | cursor=%r%s",
            source, execution_ver,
            {k: {kk: vv for kk, vv in v.items() if not kk.startswith("__")}
             for k, v in (source_cfg.get("vocabulary") or {}).items()},
            after, " (RESET)" if reset_cursor else "")

        result = BackfillResult(
            source=source, translator_ver=execution_ver, started_from=after,
            molecules=0, refused_molecules=0, incomplete_molecules=0,
            attempted=0, inserted=0, deduped=0, batches=0, blank_wafer_positions=0,
            rows_read=0, cursor=after, seconds=0.0)
        started = time.monotonic()

        translator = (None if mapper_descriptor is not None else
                      LotEventTranslator(source_cfg, translator_ver, declared, who=source))
        mapper_registered = set()
        mapper_blank_wafer_positions = 0
        pending, pending_cursor, pending_molecules = [], after, 0
        pending_refused, pending_incomplete = 0, 0

        # 🔴 THE BASELINE IS TAKEN FROM THE GATE AS IT IS NOW, NOT FROM ZERO.
        # `gate._refusals` lives for the whole PROCESS, so a second `run()` in one
        # process (every test file does this, and so does an operator sweeping two
        # sources) would otherwise re-attribute the first run's refusals to this run's
        # first batch - the breakdown would then exceed the aggregate it explains, which
        # is precisely the disagreement ruling R-2026-08-13-F exists to prevent.
        refusal_baseline = _refusal_totals(gate, source)

        # The page rule - whole groups, and the dropped one comes back - is
        # `walk_group_pages`, shared with the transfer driver. What is left here is what is
        # actually about lineage.
        pages = walk_group_pages(
            lambda position: fetch_page(read, source, columns, position, fetch_rows),
            lambda event_time: fetch_group(read, source, columns, event_time),
            "event_time", after, fetch_rows)
        for complete, next_after, _last_page in pages:
            if max_batches is not None and result["batches"] >= max_batches:
                break
            result["rows_read"] += len(complete)

            molecules = (group_lot_event_frames(complete)
                         if mapper_descriptor is not None
                         else group_molecules(complete))

            # One query for the whole page: which lots/wafers already have a register.
            # Doing it per molecule is what makes a ten-million row backfill quadratic.
            subjects = set()
            for molecule in molecules:
                source_rows = (molecule.to_dict(orient="records")
                               if mapper_descriptor is not None else molecule.rows)
                lots = {row["lot"] for row in source_rows}
                if mapper_descriptor is not None:
                    lots.update(row["parent_lot"] for row in source_rows)
                    lots.update(row["child_lot"] for row in source_rows)
                else:
                    lots.update({molecule.parent, molecule.child})
                for lot in lots:
                    if lot:
                        subjects.add(("Lot", canonical_keys({"lot": lot})))
                for row in source_rows:
                    for wafer in str(row["wafers"] or "").split(
                            source_cfg.get("list_separator", ":")):
                        wafer = wafer.strip()
                        if wafer:
                            subjects.add(("Wafer", canonical_keys({"wafer": wafer})))
            known_registrations = store.existing_registrations(read, subjects)
            if mapper_descriptor is not None:
                mapper_registered |= known_registrations
            else:
                translator.registered |= known_registrations

            # 🔴 END THE READ TRANSACTION BEFORE WRITING ANYTHING.
            # psycopg2 opens one implicitly on the first SELECT and holds it until told
            # otherwise, which means this connection sits idle-in-transaction holding
            # ACCESS SHARE on `ledger_events` for the whole molecule loop below. The
            # first statement of that loop's first write is `CREATE TABLE ... PARTITION
            # OF ledger_events`, which needs ACCESS EXCLUSIVE on the same table - so the
            # process blocks on ITSELF, forever, with no error and no output. That
            # happened on this lane's first run. Rolling back here (nothing to commit -
            # every statement above is a SELECT) releases the lock and costs one round
            # trip per page.
            read.rollback()

            for molecule in molecules:
                atoms, molecule_report = None, None
                source_rows = (molecule.to_dict(orient="records")
                               if mapper_descriptor is not None else molecule.rows)
                event_time = (molecule.iloc[0]["event_time"]
                              if mapper_descriptor is not None else molecule.event_time)
                try:
                    # 🔴 THE MOLECULE SCOPE IS OPENED HERE, BY THE SHARED DRIVER, and
                    # this is the whole of ruling R-H-bis 3. It used to be opened inside
                    # `LotEventTranslator.translate`, which meant a SECOND translator
                    # inherited the all-or-nothing rule only if its author read the first
                    # translator and noticed the `with`. Opened by the loop that walks
                    # molecules, every translator this driver drives is born inside the
                    # scope whether or not anyone tells its author the rule exists.
                    #
                    # SCREENING IS INSIDE THE SAME SCOPE on purpose (R-H-bis 1): since
                    # `screen_molecule` refuses through `gate.refuse` like every other
                    # refusal site, a molecule the GATE rejects unwinds to the handler
                    # below instead of handing back an `[]` that a future edit could
                    # merge away.
                    with gate.building_molecule(source):
                        if mapper_descriptor is not None:
                            input_frame = molecule
                            source_event = deterministic_source_event_context(
                                source, source_rows,
                                identity_fields=("row_identity",))
                            mapper_rule = {
                                "source": source,
                                "source_config": source_cfg,
                                "translator_version": translator_ver,
                                "declared_derivations": declared,
                                "registered_entities": tuple(mapper_registered),
                                "source_event": source_event,
                            }
                            if selected_profile is not None:
                                mapper_rule.update({
                                    "profile_id": profile_id,
                                    "profile": selected_profile,
                                })
                            mapped = run_registered_mapper(
                                mapper_descriptor.mapper_id,
                                mapper_descriptor.version,
                                input_frame,
                                context=mapper_context,
                                rule=mapper_rule,
                            )
                            molecule_report = dict(
                                mapped.attrs.get("mapper_report") or {})
                            atoms = atoms_from_ledger_frame(mapped)
                        else:
                            atoms, molecule_report = translator.translate(molecule)
                        refused = atoms is None
                        if not refused:
                            gate_derivations = declared
                            gate_subject_types = declared_subjects
                            if selected_profile is not None:
                                contract = mapped.attrs.get("gate_contract")
                                if not isinstance(contract, Mapping):
                                    raise LedgerMapperError(
                                        "mapper_gate_contract_missing",
                                        "ledger_frame.attrs.gate_contract",
                                        "canonical Profile mapper must declare its gate contract")
                                gate_derivations = frozenset(
                                    contract.get("declared_derivations") or ())
                                gate_subject_types = frozenset(
                                    contract.get("declared_subject_types") or ())
                                if atoms and (
                                        not gate_derivations or not gate_subject_types):
                                    raise LedgerMapperError(
                                        "mapper_gate_contract_invalid",
                                        "ledger_frame.attrs.gate_contract",
                                        "canonical Profile gate contract must name derivations and subjects")
                            kept, _screen_report = gate.screen_molecule(
                                source, atoms, gate_derivations, gate_subject_types,
                                molecule_ref=(molecule_report or {}).get("molecule"),
                                source_rows=len(source_rows))
                            pending.extend(kept)
                            if mapper_descriptor is not None:
                                for atom in kept:
                                    if atom.predicate == "register":
                                        mapper_registered.add((
                                            atom.subject_type,
                                            canonical_keys(atom.subject_keys),
                                        ))
                                mapper_blank_wafer_positions += int(
                                    molecule_report.get("blank_wafer_positions") or 0)
                except LedgerMapperRefused as refusal:
                    # A converted source treats typed mapper refusal as an execution
                    # failure: no partial pending atoms are flushed and this event's
                    # existing Ledger cursor does not move. Legacy sources keep their
                    # established counted-refusal policy until explicitly migrated.
                    reason = (refusal.code if refusal.code in gate.REFUSAL_REASONS
                              else gate.REFUSE_ATOMICITY)
                    gate.refuse(
                        source, reason, refusal.message,
                        rows=len(source_rows))
                    raise
                except gate.MoleculeRefused:
                    # The gate refused after the translator had already built (and
                    # counted) atoms. Nothing of this molecule is pending - the unwind
                    # happened before `pending.extend` - but its registers must be given
                    # back: nothing was written, so the next molecule that mentions the
                    # same lot has to be free to register it.
                    if mapper_descriptor is not None:
                        raise
                    refused = True
                    _forget_registers(translator, atoms)
                if refused:
                    pending_refused += 1
                    result["refused_molecules"] += 1
                elif molecule_report.get("incomplete"):
                    # Only a molecule that actually LANDED can be incomplete. Counting a
                    # refused one in both buckets makes the two numbers overlap, and an
                    # operator adding them up gets a total larger than the source.
                    gate.record_incomplete(source)
                    pending_incomplete += 1
                    result["incomplete_molecules"] += 1
                pending_molecules += 1
                pending_cursor = event_time

                if pending_molecules >= batch_size:
                    _flush(store, source, execution_ver, pending,
                           {"event_time": _cursor_json(pending_cursor)},
                           pending_molecules, pending_refused, pending_incomplete,
                           result, gate, refusal_baseline)
                    pending, pending_molecules = [], 0
                    pending_refused, pending_incomplete = 0, 0

            if pending_molecules:
                _flush(store, source, execution_ver, pending,
                       {"event_time": _cursor_json(pending_cursor)},
                       pending_molecules, pending_refused, pending_incomplete, result,
                       gate, refusal_baseline)
                pending, pending_molecules = [], 0
                pending_refused, pending_incomplete = 0, 0

            after = next_after
            result["cursor"] = after

        result["seconds"] = round(time.monotonic() - started, 3)
        result["blank_wafer_positions"] = (
            mapper_blank_wafer_positions if mapper_descriptor is not None
            else translator.blank_wafer_positions)
        result["census"] = store.census()
        result["partitions"] = [name for name, _ in schema.partitions(read)]

        cursor_row = store.read_cursor(read, source)
        # Read back rather than reported from memory: the point of the column is that
        # somebody OTHER than this process can see the breakdown, so the run's own log
        # quotes what a reader would actually get.
        result["refusal_reasons"] = (cursor_row or {}).get("refusal_reasons")
        result["lag"] = observability.lag_report(
            store, source, source_cfg, cursor_row,
            probe_interval=(cfg.get("lag") or {}).get("probe_interval_seconds", 60),
            force_probe=probe_lag)
        result["gate_note"] = gate.note()
        result["lag_note"] = observability.lag_note(result["lag"])
        return result
    finally:
        read.close()


# --------------------------------------------------------------- observation driver
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


def _watermark_json(values):
    """The watermark as something `jsonb` can hold and `>` can read back.

    Datetimes go to ISO-8601 text. On resume they are bound straight back into the
    row-value comparison and PostgreSQL coerces them to the column's own type - which is
    why the ISO spelling matters: it is the one text form that means the same instant to
    the database as the value it came from.
    """
    from datetime import datetime as _dt
    return [v.isoformat() if isinstance(v, _dt) else (None if v is None else str(v))
            for v in values]


def _cursor_json(value):
    """A lineage cursor suitable for jsonb while preserving timestamptz ordering."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _run_observation(engine, cfg, source, fetch_rows=DEFAULT_FETCH_ROWS,
                     reset_cursor=False, start_from=None, max_batches=None,
                     probe_lag=True):
    """`void_obs` / `delam_obs` -> `observed` atoms. Ruling R-2026-08-14-D.

    🔴 THE MOLECULE SCOPE IS OPENED HERE, BY THIS DRIVER, exactly as the lineage driver
    opens it (ruling R-H-bis 3). One row is one molecule in this grammar, so the
    all-or-nothing rule is trivially satisfied - and that is precisely why the scope is
    still opened rather than skipped: the day this driver grows a second atom per row, the
    rule is already holding it.
    """
    from . import config as ledger_config
    from . import gate, observability, schema
    from .envelope import canonical_keys
    from .observation_translator import ObservationMolecule, ObservationTranslator
    from .store import LedgerStore

    source_cfg = ledger_config.source_config(cfg, source)
    translator_ver = ledger_config.translator_version(cfg, source)
    declared = ledger_config.declared_derivations(cfg, source)
    declared_subjects = ledger_config.declared_subject_types(cfg, source)
    batch_size = int((cfg.get("batch") or {}).get("molecules_per_transaction", 200))
    finding_kind = source_cfg.get("finding_kind")

    # 🔴 THE CLOSED CLASS SET COMES FROM THE KIND REGISTRY, NOT FROM THIS DECLARATION
    # (§6-quater). `ledger_config` says WHICH COLUMN utters a class; `finding_kinds` says
    # WHICH VALUES a class may take, because that set is a property of the kind and the
    # console builds its slice axis from the same list. Two declarations of one closed set
    # is how a value that is legal on one screen is refused on the other.
    declared_classes = ()
    if (source_cfg.get("columns") or {}).get("class"):
        try:
            import finding_kinds
            declared_classes = finding_kinds.classes(finding_kind)
        except Exception as exc:
            logger.warning("[Ledger] %s declares a class column but the kind registry "
                           "could not be read (%s); every uttered class will be refused",
                           source, exc)

    store = LedgerStore(engine)
    store.ensure_schema()

    read = store.connection()
    try:
        existing = store.read_cursor(read, source)
        if isinstance(start_from, str):
            # `--from "2026-08-14T08:30:02+09:00|019ffd76-…"`. A keyset has as many parts
            # as the declaration has columns, so the operator's string is split rather
            # than guessed at, and a wrong arity is a loud IndexError at the first page
            # instead of a comparison that quietly matches everything.
            start_from = start_from.split("|")
        after = start_from if start_from is not None else (
            None if reset_cursor else (existing or {}).get("cursor_value", {}).get(
                "watermark"))

        logger.info("[Ledger] backfill %s (observation) | translator_ver=%s | "
                    "finding_kind=%s | classes=%s | cursor=%r%s",
                    source, translator_ver, finding_kind, list(declared_classes), after,
                    " (RESET)" if reset_cursor else "")

        result = BackfillResult(
            source=source, kind=ledger_config.SOURCE_KIND_OBSERVATION,
            translator_ver=translator_ver, started_from=after,
            molecules=0, refused_molecules=0, incomplete_molecules=0,
            attempted=0, inserted=0, deduped=0, batches=0, blank_geometry=0,
            rows_read=0, cursor=after, seconds=0.0)
        started = time.monotonic()

        translator = ObservationTranslator(source, source_cfg, translator_ver, declared,
                                           declared_classes=declared_classes)
        refusal_baseline = _refusal_totals(gate, source)

        while True:
            if max_batches is not None and result["batches"] >= max_batches:
                break
            rows = fetch_observation_page(read, source, source_cfg, after, fetch_rows)
            if not rows:
                break
            result["rows_read"] += len(rows)

            runs = fetch_runs(read, source_cfg, {r["run_key"] for r in rows
                                                 if r.get("run_key")})
            subjects = {("Wafer", canonical_keys({"wafer": str(r["wafer"]).strip()}))
                        for r in rows if str(r.get("wafer") or "").strip()}
            translator.registered |= store.existing_registrations(read, subjects)

            # END THE READ TRANSACTION BEFORE WRITING - same reason as the lineage
            # driver: this connection holds ACCESS SHARE on `ledger_events` and the first
            # write may need ACCESS EXCLUSIVE to create a partition, so the process would
            # block on itself.
            read.rollback()

            pending, pending_molecules, pending_refused = [], 0, 0
            pending_cursor = after
            for row in rows:
                molecule = ObservationMolecule(source, row)
                atoms, refused = None, False
                try:
                    with gate.building_molecule(source):
                        atoms, _report = translator.translate(molecule, runs)
                        refused = atoms is None
                        if not refused:
                            kept, _screen = gate.screen_molecule(
                                source, atoms, declared, declared_subjects,
                                molecule_ref=molecule.ref, source_rows=1)
                            pending.extend(kept)
                except gate.MoleculeRefused:
                    refused = True
                    _forget_registers(translator, atoms)
                if refused:
                    pending_refused += 1
                    result["refused_molecules"] += 1
                pending_molecules += 1
                pending_cursor = molecule.watermark

                if pending_molecules >= batch_size:
                    _flush(store, source, translator_ver, pending,
                           {"watermark": _watermark_json(pending_cursor)},
                           pending_molecules, pending_refused, 0, result, gate,
                           refusal_baseline)
                    pending, pending_molecules, pending_refused = [], 0, 0

            if pending_molecules:
                _flush(store, source, translator_ver, pending,
                       {"watermark": _watermark_json(pending_cursor)},
                       pending_molecules, pending_refused, 0, result, gate,
                       refusal_baseline)

            after = _watermark_json(rows[-1]["__watermark__"])
            result["cursor"] = after
            if len(rows) < fetch_rows:
                break

        result["seconds"] = round(time.monotonic() - started, 3)
        result["blank_geometry"] = translator.blank_geometry
        result["census"] = store.census()
        result["partitions"] = [name for name, _ in schema.partitions(read)]

        cursor_row = store.read_cursor(read, source)
        result["refusal_reasons"] = (cursor_row or {}).get("refusal_reasons")
        result["lag"] = observability.lag_report_keyset(
            store, source, source_cfg, cursor_row,
            probe_interval=(cfg.get("lag") or {}).get("probe_interval_seconds", 60),
            force_probe=probe_lag)
        result["gate_note"] = gate.note()
        result["lag_note"] = observability.lag_note(result["lag"])
        return result
    finally:
        read.close()


# ------------------------------------------------------------------ declared driver
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


def _run_declared(engine, cfg, source, fetch_rows=DEFAULT_FETCH_ROWS,
                  reset_cursor=False, start_from=None, max_batches=None, probe_lag=True):
    """A source whose row -> atom mapping is DECLARED (`ADMIN_SETUP_BRIEF` §6-2).

    Structurally the observation driver: keyset cursor, one row per molecule, molecule
    scope opened HERE by the driver (ruling R-H-bis 3). What differs is only that the
    translator reads its rules from the config instead of from its own source.
    """
    from . import config as ledger_config
    from . import gate, observability, schema
    from .declared_translator import DeclaredMolecule, DeclaredTranslator
    from .envelope import canonical_keys
    from .store import LedgerStore

    source_cfg = ledger_config.source_config(cfg, source)
    translator_ver = ledger_config.translator_version(cfg, source)
    declared = ledger_config.declared_derivations(cfg, source)
    declared_subjects = ledger_config.declared_subject_types(cfg, source)
    batch_size = int((cfg.get("batch") or {}).get("molecules_per_transaction", 200))

    store = LedgerStore(engine)
    store.ensure_schema()

    read = store.connection()
    try:
        existing = store.read_cursor(read, source)
        if isinstance(start_from, str):
            start_from = start_from.split("|")
        after = start_from if start_from is not None else (
            None if reset_cursor else (existing or {}).get("cursor_value", {}).get(
                "watermark"))

        logger.info("[Ledger] backfill %s (declared) | translator_ver=%s | rules=%s | "
                    "cursor=%r%s", source, translator_ver,
                    [r.get("rule") for r in (source_cfg.get("emit") or [])], after,
                    " (RESET)" if reset_cursor else "")

        result = BackfillResult(
            source=source, kind=ledger_config.SOURCE_KIND_DECLARED,
            translator_ver=translator_ver, started_from=after,
            molecules=0, refused_molecules=0, incomplete_molecules=0,
            attempted=0, inserted=0, deduped=0, batches=0, rows_matching_nothing=0,
            rows_read=0, cursor=after, seconds=0.0)
        started = time.monotonic()

        translator = DeclaredTranslator(source, source_cfg, translator_ver, declared)
        refusal_baseline = _refusal_totals(gate, source)

        while True:
            if max_batches is not None and result["batches"] >= max_batches:
                break
            rows = fetch_declared_page(read, source, source_cfg, after, fetch_rows)
            if not rows:
                break
            result["rows_read"] += len(rows)

            # The subjects this page could register, read from the DECLARATION rather than
            # from a literal - a declared source may speak about any entity type it named.
            subjects = set()
            for row in rows:
                for rule in (source_cfg.get("emit") or []):
                    subject = rule.get("subject") or {}
                    subject_type = subject.get("type")
                    if subject_type not in translator.register_types:
                        continue
                    try:
                        keys = {k: _plain(v, row)
                                for k, v in (subject.get("keys") or {}).items()}
                    except KeyError:
                        continue        # the translator will refuse this row by name
                    if all(str(v or "").strip() for v in keys.values()):
                        subjects.add((subject_type, canonical_keys(keys)))
            translator.registered |= store.existing_registrations(read, subjects)

            read.rollback()

            pending, pending_molecules, pending_refused = [], 0, 0
            pending_cursor = after
            for row in rows:
                molecule = DeclaredMolecule(source, row)
                atoms, refused = None, False
                try:
                    with gate.building_molecule(source):
                        atoms, _report = translator.translate(molecule)
                        refused = atoms is None
                        if not refused:
                            kept, _screen = gate.screen_molecule(
                                source, atoms, declared, declared_subjects,
                                molecule_ref=molecule.ref, source_rows=1)
                            pending.extend(kept)
                except gate.MoleculeRefused:
                    refused = True
                    _forget_registers(translator, atoms)
                if refused:
                    pending_refused += 1
                    result["refused_molecules"] += 1
                pending_molecules += 1
                pending_cursor = molecule.watermark

                if pending_molecules >= batch_size:
                    _flush(store, source, translator_ver, pending,
                           {"watermark": _watermark_json(pending_cursor)},
                           pending_molecules, pending_refused, 0, result, gate,
                           refusal_baseline)
                    pending, pending_molecules, pending_refused = [], 0, 0

            if pending_molecules:
                _flush(store, source, translator_ver, pending,
                       {"watermark": _watermark_json(pending_cursor)},
                       pending_molecules, pending_refused, 0, result, gate,
                       refusal_baseline)

            after = _watermark_json(rows[-1]["__watermark__"])
            result["cursor"] = after
            if len(rows) < fetch_rows:
                break

        result["seconds"] = round(time.monotonic() - started, 3)
        result["rows_matching_nothing"] = translator.rows_matching_nothing
        result["census"] = store.census()
        result["partitions"] = [name for name, _ in schema.partitions(read)]

        cursor_row = store.read_cursor(read, source)
        result["refusal_reasons"] = (cursor_row or {}).get("refusal_reasons")
        result["lag"] = observability.lag_report_keyset(
            store, source, source_cfg, cursor_row,
            probe_interval=(cfg.get("lag") or {}).get("probe_interval_seconds", 60),
            force_probe=probe_lag)
        result["gate_note"] = gate.note()
        result["lag_note"] = observability.lag_note(result["lag"])
        return result
    finally:
        read.close()


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


def _run_transfer(engine, cfg, source, fetch_rows=DEFAULT_FETCH_ROWS,
                  reset_cursor=False, start_from=None, max_batches=None, probe_lag=True):
    """`dt_log` -> `transferred` atoms. The third grammar.

    🔴 THE MOLECULE SCOPE IS OPENED HERE, BY THIS DRIVER (ruling R-H-bis 3), exactly as the
    other two open it. This grammar is the one where it bites hardest: a job-run folds up
    to 150 source rows into several atoms, so a refusal discovered while building the fifth
    wafer's atom has to unwind the first four - and it does, because every `gate.refuse`
    under this `with` raises.
    """
    from . import config as ledger_config
    from . import gate, observability, schema
    from .envelope import canonical_keys
    from .store import LedgerStore
    from .transfer_translator import TransferTranslator

    source_cfg = ledger_config.source_config(cfg, source)
    translator_ver = ledger_config.translator_version(cfg, source)
    declared = ledger_config.declared_derivations(cfg, source)
    declared_subjects = ledger_config.declared_subject_types(cfg, source)
    batch_size = int((cfg.get("batch") or {}).get("molecules_per_transaction", 200))
    group_column = source_cfg["group"]["column"]

    store = LedgerStore(engine)
    store.ensure_schema()

    read = store.connection()
    try:
        existing = store.read_cursor(read, source)
        after = start_from if start_from is not None else (
            None if reset_cursor else (existing or {}).get("cursor_value", {}).get(
                "group_key"))

        logger.info("[Ledger] backfill %s (transfer) | translator_ver=%s | group=%s | "
                    "container=%s | cursor=%r%s",
                    source, translator_ver, group_column,
                    (source_cfg.get("container") or {}).get("relation"), after,
                    " (RESET)" if reset_cursor else "")

        result = BackfillResult(
            source=source, kind=ledger_config.SOURCE_KIND_TRANSFER,
            translator_ver=translator_ver, started_from=after,
            molecules=0, refused_molecules=0, incomplete_molecules=0,
            attempted=0, inserted=0, deduped=0, batches=0,
            unanchored_rows=0, confirmed_groups=0, unconfirmed_groups=0,
            rows_read=0, cursor=after, seconds=0.0)
        started = time.monotonic()

        translator = TransferTranslator(source, source_cfg, translator_ver, declared)
        refusal_baseline = _refusal_totals(gate, source)

        # 🔴 THE SAME PAGE RULE AS THE LINEAGE DRIVER, FROM THE SAME FUNCTION. A group
        # larger than a page is fetched whole rather than folded as a fragment - and a
        # fragment here would be worse than elsewhere, because it produces a `qty` that is
        # wrong and looks right.
        pages = walk_group_pages(
            lambda position: fetch_transfer_page(read, source, source_cfg, position,
                                                 fetch_rows),
            lambda group_key: fetch_transfer_group(read, source, source_cfg, group_key),
            "group_key", after, fetch_rows)
        for complete, next_after, _last_page in pages:
            if max_batches is not None and result["batches"] >= max_batches:
                break
            result["rows_read"] += len(complete)

            molecules = _group_transfer_rows(source, complete)
            containers = fetch_containers(read, source_cfg,
                                          {m.group_key for m in molecules})
            subjects = {("Wafer", canonical_keys({"wafer": str(r["wafer"]).strip()}))
                        for r in complete if str(r.get("wafer") or "").strip()}
            translator.registered |= store.existing_registrations(read, subjects)

            # END THE READ TRANSACTION BEFORE WRITING - same reason as the other two
            # drivers: this connection holds ACCESS SHARE on `ledger_events` and the first
            # write may need ACCESS EXCLUSIVE to create a partition.
            read.rollback()

            pending, pending_molecules = [], 0
            pending_refused, pending_incomplete = 0, 0
            pending_cursor = after
            for molecule in molecules:
                atoms, molecule_report, refused = None, None, False
                try:
                    with gate.building_molecule(source):
                        atoms, molecule_report = translator.translate(molecule, containers)
                        refused = atoms is None
                        if not refused:
                            kept, _screen = gate.screen_molecule(
                                source, atoms, declared, declared_subjects,
                                molecule_ref=molecule.ref,
                                source_rows=len(molecule.rows))
                            pending.extend(kept)
                except gate.MoleculeRefused:
                    refused = True
                    _forget_registers(translator, atoms)
                if refused:
                    pending_refused += 1
                    result["refused_molecules"] += 1
                elif molecule_report.get("incomplete"):
                    # Only a molecule that actually LANDED can be incomplete - counting a
                    # refused one in both buckets makes an operator's sum exceed the
                    # source.
                    gate.record_incomplete(source)
                    pending_incomplete += 1
                    result["incomplete_molecules"] += 1
                pending_molecules += 1
                pending_cursor = molecule.group_key

                if pending_molecules >= batch_size:
                    _flush(store, source, translator_ver, pending,
                           {"group_key": pending_cursor},
                           pending_molecules, pending_refused, pending_incomplete,
                           result, gate, refusal_baseline)
                    pending, pending_molecules = [], 0
                    pending_refused, pending_incomplete = 0, 0

            if pending_molecules:
                _flush(store, source, translator_ver, pending,
                       {"group_key": pending_cursor},
                       pending_molecules, pending_refused, pending_incomplete, result,
                       gate, refusal_baseline)

            after = next_after
            result["cursor"] = after

        result["seconds"] = round(time.monotonic() - started, 3)
        result["unanchored_rows"] = translator.unanchored_rows
        result["confirmed_groups"] = translator.confirmed_groups
        result["unconfirmed_groups"] = translator.unconfirmed_groups
        result["census"] = store.census()
        result["partitions"] = [name for name, _ in schema.partitions(read)]

        cursor_row = store.read_cursor(read, source)
        result["refusal_reasons"] = (cursor_row or {}).get("refusal_reasons")
        result["lag"] = observability.lag_report_group(
            store, source, source_cfg, cursor_row,
            probe_interval=(cfg.get("lag") or {}).get("probe_interval_seconds", 60),
            force_probe=probe_lag)
        result["gate_note"] = gate.note()
        result["lag_note"] = observability.lag_note(result["lag"])
        return result
    finally:
        read.close()


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


def _refusal_totals(gate, source):
    """`{reason: molecules}` the gate has counted for `source` SO FAR IN THIS PROCESS."""
    return {reason: total for (src, reason), total in gate.refusals().items()
            if src == source}


def _refusal_delta(gate, source, baseline):
    """This batch's refusals BY NAME - the totals now, minus the baseline.

    Does NOT advance the baseline: `_flush` does that only after the write commits, so a
    batch that raises leaves its refusals to be attributed to the retry rather than
    silently dropped from the breakdown while `molecules_refused` still counts them.
    """
    totals = _refusal_totals(gate, source)
    delta = {reason: total - baseline.get(reason, 0) for reason, total in totals.items()
             if total > baseline.get(reason, 0)}
    return delta, totals


def _flush(store, source, translator_ver, atoms, cursor_value, molecules, refused,
           incomplete, result, gate, refusal_baseline):
    """One batch: atoms, the cursor, the aggregates AND their breakdown, in one commit.

    🔴 The breakdown is computed HERE, immediately before the write, so the names and the
    integer beside them come from the same instant. `sum(delta) == refused` is the
    contract `store.write_batch` documents; where the two could disagree is a defect in
    the refusal PATHS rather than in this arithmetic, so it is asserted by a test against
    the database rather than enforced here - telemetry must never be able to roll back a
    batch of atoms (`observability.lag_report` takes the same stance).
    """
    delta, totals = _refusal_delta(gate, source, refusal_baseline)
    written = store.write_batch(
        source, translator_ver, atoms, cursor_value, molecules,
        refused=refused, incomplete=incomplete, reasons=delta)
    refusal_baseline.clear()
    refusal_baseline.update(totals)
    result["molecules"] += molecules
    result["attempted"] += written["attempted"]
    result["inserted"] += written["inserted"]
    result["deduped"] += written["deduped"]
    result["batches"] += 1


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
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    from database.database import engine
    from . import config as ledger_config

    cfg = ledger_config.load(args.config)
    result = run(engine, cfg, source=args.source, fetch_rows=args.fetch_rows,
                 reset_cursor=args.reset_cursor, start_from=args.start_from,
                 max_batches=args.max_batches)
    beat(result)

    logger.info("[Ledger] %s", {k: v for k, v in result.items() if k != "census"})
    logger.info("[Ledger] census by predicate: %s", result.get("census"))
    if result.get("gate_note"):
        logger.warning("[Ledger] %s", result["gate_note"])
    logger.info("[Ledger] %s", result.get("lag_note"))
    return 0


if __name__ == "__main__":                                       # pragma: no cover
    sys.exit(main())
