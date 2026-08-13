"""The `lot_event` backfill - a cursor loop that never cuts a molecule in half.

    conda run -n assy_manager python -m ledger.backfill --source lot_event

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
        cursor.execute(
            f"SELECT {', '.join(select)} FROM {source} "
            f"WHERE {time_column} > %s "
            f"ORDER BY {time_column}, {identity} "
            f"LIMIT %s", (after or "", limit))
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


def _cut_on_group_boundary(rows, page_limit):
    """`(complete_rows, trailing_event_time_or_None)`.

    Returns the rows that are safe to process now, plus the event_time whose group had to
    be dropped because the page may have cut it. `None` for the second element means the
    page reached the end of the source and nothing was dropped.
    """
    if not rows:
        return [], None
    if len(rows) < page_limit:
        return rows, None
    last_time = rows[-1]["event_time"]
    kept = [r for r in rows if r["event_time"] != last_time]
    return kept, last_time


def run(engine, cfg, source="lot_event", fetch_rows=DEFAULT_FETCH_ROWS,
        reset_cursor=False, start_from=None, max_batches=None, probe_lag=True):
    """Translate everything past the cursor. Returns a `BackfillResult`.

    `reset_cursor=True` deliberately re-reads work that is already done - it is how net 2
    of the idempotency argument gets exercised, and how an operator re-translates after a
    rule change (the new `source_translator_ver` makes the new atoms distinct from the
    old ones, which is correct: they are different claims made by different rules).
    """
    from . import config as ledger_config
    from . import gate, observability, schema
    from .envelope import canonical_keys
    from .lot_event_translator import LotEventTranslator, group_molecules
    from .store import LedgerStore

    source_cfg = ledger_config.source_config(cfg, source)
    if source_cfg is None:
        gate.refuse(source, gate.REFUSE_UNDECLARED_SOURCE,
                    f"source {source!r} has no declaration in "
                    f"{cfg.get('__origin__', 'ledger_config.json')}; nothing was read")
        return BackfillResult(source=source, refused_source=True, atoms=0, molecules=0)

    translator_ver = ledger_config.translator_version(cfg, source)
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
            source, translator_ver,
            {k: {kk: vv for kk, vv in v.items() if not kk.startswith("__")}
             for k, v in (source_cfg.get("vocabulary") or {}).items()},
            after, " (RESET)" if reset_cursor else "")

        result = BackfillResult(
            source=source, translator_ver=translator_ver, started_from=after,
            molecules=0, refused_molecules=0, incomplete_molecules=0,
            attempted=0, inserted=0, deduped=0, batches=0, blank_wafer_positions=0,
            rows_read=0, cursor=after, seconds=0.0)
        started = time.monotonic()

        translator = LotEventTranslator(source_cfg, translator_ver, declared)
        pending, pending_cursor, pending_molecules = [], after, 0
        pending_refused, pending_incomplete = 0, 0

        while True:
            if max_batches is not None and result["batches"] >= max_batches:
                break
            rows = fetch_page(read, source, columns, after, fetch_rows)
            if not rows:
                break
            complete, dropped = _cut_on_group_boundary(rows, fetch_rows)
            if not complete:
                # One event_time group is larger than a page. Read it whole rather than
                # process a fragment of it.
                complete = fetch_group(read, source, columns, dropped)
                dropped = None
            result["rows_read"] += len(complete)

            molecules = group_molecules(complete)

            # One query for the whole page: which lots/wafers already have a register.
            # Doing it per molecule is what makes a ten-million row backfill quadratic.
            subjects = set()
            for molecule in molecules:
                for lot in {r["lot"] for r in molecule.rows} | {molecule.parent,
                                                                molecule.child}:
                    if lot:
                        subjects.add(("Lot", canonical_keys({"lot": lot})))
                for row in molecule.rows:
                    for wafer in str(row["wafers"] or "").split(
                            source_cfg.get("list_separator", ":")):
                        wafer = wafer.strip()
                        if wafer:
                            subjects.add(("Wafer", canonical_keys({"wafer": wafer})))
            translator.registered |= store.existing_registrations(read, subjects)

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
                atoms, molecule_report = translator.translate(molecule)
                refused = atoms is None
                if not refused:
                    kept, screen_report = gate.screen_molecule(
                        source, atoms, declared, declared_subjects,
                        molecule_ref=molecule.ref, source_rows=len(molecule.rows))
                    refused = screen_report["refused"]
                    if refused:
                        # 🔴 A refused molecule must not leave its registers memoised:
                        # nothing was written, so the next molecule that mentions the
                        # same lot has to be free to register it.
                        _forget_registers(translator, atoms)
                    else:
                        pending.extend(kept)
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
                pending_cursor = molecule.event_time

                if pending_molecules >= batch_size:
                    _flush(store, source, translator_ver, pending, pending_cursor,
                           pending_molecules, pending_refused, pending_incomplete,
                           result)
                    pending, pending_molecules = [], 0
                    pending_refused, pending_incomplete = 0, 0

            if pending_molecules:
                _flush(store, source, translator_ver, pending, pending_cursor,
                       pending_molecules, pending_refused, pending_incomplete, result)
                pending, pending_molecules = [], 0
                pending_refused, pending_incomplete = 0, 0

            after = dropped or complete[-1]["event_time"]
            result["cursor"] = after
            if dropped is None and len(rows) < fetch_rows:
                break

        result["seconds"] = round(time.monotonic() - started, 3)
        result["blank_wafer_positions"] = translator.blank_wafer_positions
        result["census"] = store.census()
        result["partitions"] = [name for name, _ in schema.partitions(read)]

        cursor_row = store.read_cursor(read, source)
        result["lag"] = observability.lag_report(
            store, source, source_cfg, cursor_row,
            probe_interval=(cfg.get("lag") or {}).get("probe_interval_seconds", 60),
            force_probe=probe_lag)
        result["gate_note"] = gate.note()
        result["lag_note"] = observability.lag_note(result["lag"])
        return result
    finally:
        read.close()


def _forget_registers(translator, atoms):
    from .envelope import canonical_keys
    for atom in atoms or ():
        if atom.predicate == "register":
            translator.registered.discard(
                (atom.subject_type, canonical_keys(atom.subject_keys)))


def _flush(store, source, translator_ver, atoms, cursor_value, molecules, refused,
           incomplete, result):
    written = store.write_batch(
        source, translator_ver, atoms, {"event_time": cursor_value}, molecules,
        refused=refused, incomplete=incomplete)
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
                        help="start after this event_time instead of the cursor")
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
