# -*- coding: utf-8 -*-
"""S-118 ①: split ONE watcher ingestion of N rows, in this process, stage by stage.

🔴 WHY IT IS IN-PROCESS AND NOT "DROP A FILE AND WATCH THE CLOCK". The watcher runs as
its own process, so a file dropped into `raws/` gives exactly one number - how long the
whole thing took - and that number cannot say whether the time went to hashing, parsing,
normalising, upserting cells, writing audit rows or committing. What is being decided
here is WHICH STAGE to fix, so the split is the measurement, not the total.

🔴 WHY IT CALLS THE REAL HANDLER. `IngestionHandler.process_with_retry` is the seat the
watcher's own event callback calls; a re-implementation here would be a second spelling of
the ingestion path and would drift from it silently. So this builds a workspace, writes a
file into its `raws/`, and hands that file to the real handler. Nothing in the product is
changed: the stage clock is a set of wrappers installed on module attributes in THIS
process and removed in a `finally`.

⚠️ WHAT THE "parse" LINE IS AND IS NOT. The standard parser is two-pass and streaming:
pass 1 counts rows and validates the header (inside `_resolve_rows`, which is what the
parse line times), pass 2 decodes each row lazily as the chunk loop pulls it. So pass 2's
cost is charged to the write stage's remainder, NOT to the parse line. Reading the parse
line as "parsing costs this much" would be reading a proxy as the property.

🔴 WHY THE FILE IS BUILT FROM THE DECLARATION. The columns, the key group and the map
identity are read from the catalogue entry - `display_columns`, `composite_key_source` or
`business_key`, `map_key_columns`, `column_types`. No column name appears in this file. A
box declaring something else gets a file shaped for that instead, with no code change.

⚠️ IT WRITES ROWS AND DELETES NOTHING. Every run leaves its rows in the target table, on
purpose (deleting is destructive, and a measurement is not a reason to delete). The run
prints the marks it left - table, key prefix, row count, transaction id - so they can be
named in a report rather than found later by somebody else.

Usage (nothing runs at import):
    python scripts/probe_ingestion_stages.py --table dt_log --rows 20000
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import shutil
import sys
import tempfile
import time
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.abspath(os.path.join(_HERE, ".."))
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

#: The owner's production shape: a map is 20x20 (`CLAUDE.md`, 2026-09-08).
MAP_SIDE = 20
DEFAULT_ROWS = 20000


class ProbeRefusal(Exception):
    """A refusal that names what is missing, rather than measuring something else."""


# ── the stage clock ──────────────────────────────────────────────────────────

class Clock:
    """Named wall-clock totals and call counts, with wrappers that undo themselves.

    Deliberately not a profiler: a profiler charges per-call overhead to whichever site
    makes the most calls, which is how a cheap function called a million times reads as
    the bottleneck. Here only a dozen coarse seats are wrapped, each called at most once
    per 1,000-row chunk, so the wrapper's own cost cannot decide the answer.
    """

    def __init__(self):
        self.seconds: dict[str, float] = {}
        self.calls: dict[str, int] = {}
        self._undo: list = []
        #: The labels currently on the call stack. One list answers "am I inside that
        #: stage" for every seat, so no caller has to keep a counter of its own.
        self.stack: list[str] = []

    def record(self, label: str, seconds: float):
        self.seconds[label] = self.seconds.get(label, 0.0) + seconds
        self.calls[label] = self.calls.get(label, 0) + 1

    def wrap(self, owner, attribute: str, label: str, on_call=None):
        """Time `owner.attribute` under `label`. Missing attribute is a refusal, not a skip.

        A silently skipped wrapper would leave a stage at 0.000 s, and a zero reads as
        "this costs nothing" rather than "this was not measured".
        """
        original = getattr(owner, attribute, None)
        if original is None:
            raise ProbeRefusal(
                f"{getattr(owner, '__name__', owner)}.{attribute} does not exist - the "
                f"probe would have reported stage {label!r} as 0.000 s")

        def timed(*args, **kwargs):
            if on_call is not None:
                try:
                    on_call(args, kwargs)
                except Exception:                                       # noqa: BLE001
                    pass
            self.stack.append(label)
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.stack.pop()
                self.record(label, time.perf_counter() - started)

        setattr(owner, attribute, timed)
        self._undo.append((owner, attribute, original))
        return original

    def wrap_split_by_caller(self, owner, attribute: str, cases, otherwise: str):
        """One seat, several labels, chosen by which stage is on the stack.

        🔴 A SHARED SEAT CHARGED TO ONE PARENT MAKES THE TREE STOP ADDING UP.
        `Session.commit` is called by `apply_batch_updates`, by the chunk loop after it
        returns, AND by the checkpoint, heartbeat and ingestion-record steps outside the
        write entirely. Summed under the write, the write's remainder went NEGATIVE -
        measured, first run - which is the arithmetic saying the seat had been charged to
        a parent that did not call it.

        `cases` is an ordered list of (stage label, label to charge), innermost first.
        """
        original = getattr(owner, attribute)

        def timed(*args, **kwargs):
            label = otherwise
            for stage, charged in cases:
                if stage in self.stack:
                    label = charged
                    break
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.record(label, time.perf_counter() - started)

        setattr(owner, attribute, timed)
        self._undo.append((owner, attribute, original))

    def restore(self):
        for owner, attribute, original in reversed(self._undo):
            setattr(owner, attribute, original)
        self._undo = []


# ── the file, built from the declaration ─────────────────────────────────────

def key_columns(entry: dict) -> list:
    """The columns a row needs a value in, or the standard parser skips it."""
    composite = [str(c) for c in (entry.get("composite_key_source") or []) if str(c).strip()]
    if composite:
        return composite
    business_key = str(entry.get("business_key") or "").strip()
    return [business_key] if business_key else []


def plan_file(entry: dict):
    """(columns, key columns, map columns, axis columns) for one probe file.

    The map columns are the key columns the catalogue also names as map identity; the
    axis columns are the rest of the key. That is the whole domain model this file has,
    and it is read, not written.
    """
    columns = [str(c) for c in (entry.get("display_columns") or []) if str(c).strip()]
    if not columns:
        raise ProbeRefusal("the catalogue entry declares no `display_columns` - there is "
                           "no file to write")
    keys = key_columns(entry)
    if not keys:
        raise ProbeRefusal("the catalogue entry declares neither `composite_key_source` "
                           "nor `business_key` - every row would be skipped for a missing key")
    missing = [c for c in keys if c not in columns]
    if missing:
        raise ProbeRefusal(
            f"key column(s) {missing} are not in `display_columns`, so the write path "
            f"would drop them and every row would land without a key")
    map_columns = [c for c in keys if c in (entry.get("map_key_columns") or [])]
    axis_columns = [c for c in keys if c not in map_columns]
    return columns, keys, map_columns, axis_columns


def write_probe_file(path: str, entry: dict, rows: int, label: str, number_start: int):
    """Write one file of `rows` rows and return (map count, first key, last key)."""
    columns, keys, map_columns, axis_columns = plan_file(entry)
    types = entry.get("column_types") or {}
    per_map = MAP_SIDE * MAP_SIDE if len(axis_columns) == 2 else rows
    stamp = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

    def value(column, n):
        # The key columns carry identity; everything else carries a value of the
        # declared type, because a blank column is not what an ingested file looks like.
        if column in map_columns:
            return f"{label}-{n // per_map:04d}"
        if column in axis_columns:
            inside = n % per_map
            axis = axis_columns.index(column)
            return inside % MAP_SIDE if axis == 0 else inside // MAP_SIDE
        kind = str(types.get(column) or "string").lower()
        if kind == "number":
            return number_start + n
        if kind == "datetime":
            return stamp
        return f"{label}-{column}"

    first_key = last_key = None
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for n in range(rows):
            row = [value(column, n) for column in columns]
            writer.writerow(row)
            key = "|".join(str(row[columns.index(c)]) for c in keys)
            first_key = first_key if first_key is not None else key
            last_key = key
    maps = (rows + per_map - 1) // per_map
    return maps, first_key, last_key


# ── the run ──────────────────────────────────────────────────────────────────

def build_workspace(root: str, table: str) -> str:
    """A workspace whose folder name IS the table name - the watcher's own convention."""
    workspace = os.path.join(root, table)
    for sub in ("raws", "archives", "err", "scripts"):
        os.makedirs(os.path.join(workspace, sub), exist_ok=True)
    return workspace


def run(table: str, rows: int, label: str, number_start: int, work_root: str,
        keep_workspace: bool):
    from database import crud, models
    from database.database import engine
    import ingestion_checkpoint
    from parsers import directory_watcher as dw
    from sqlalchemy import text
    from sqlalchemy.engine import Connection as EngineConnection
    from sqlalchemy.orm import Session as OrmSession
    from utils import heartbeat

    entry = (dw.load_global_table_config() or {}).get(table)
    if not isinstance(entry, dict) or not entry:
        raise ProbeRefusal(
            f"table {table!r} is not declared in the catalogue, so the watcher cannot "
            f"route a file to it - a workspace folder alone is not enough")

    # The dynamic ORM models are built at boot; a bare process has none, and the write
    # path refuses BY NAME when it cannot find the table's model.
    models.refresh_dynamic_models()

    workspace = build_workspace(work_root, table)
    file_name = f"{label}.csv"
    file_path = os.path.join(workspace, "raws", file_name)
    maps, first_key, last_key = write_probe_file(
        file_path, entry, rows, label, number_start)
    size = os.path.getsize(file_path)
    print(f"file      {file_name} | {rows:,} rows | {size:,} B | {maps} map(s) of "
          f"{MAP_SIDE}x{MAP_SIDE}")
    print(f"keys      {first_key}  ..  {last_key}")

    with engine.connect() as connection:
        outbox_before = connection.execute(
            text("SELECT COALESCE(MAX(id), 0) FROM database_outbox")).scalar()

    clock = Clock()
    transactions = set()

    def note_transaction(args, kwargs):
        batch = kwargs.get("batch") or (args[2] if len(args) > 2 else None)
        if batch is not None and getattr(batch, "transaction_id", None):
            transactions.add(batch.transaction_id)

    try:
        # The outer path, in the order `_process_with_retry` walks it.
        clock.wrap(dw, "compute_file_signature", "file signature (sha256)")
        clock.wrap(dw.IngestionHandler, "_try_dedup_skip", "dedup lookup")
        clock.wrap(dw.IngestionHandler, "_resolve_rows", "parse pass 1 (count+header)")
        clock.wrap(dw.IngestionHandler, "_plan_checkpoint", "checkpoint plan")
        clock.wrap(dw.IngestionHandler, "_send_to_upsert", "WRITE (whole file)")
        clock.wrap(dw.IngestionHandler, "_archive_file", "archive file")
        clock.wrap(dw.IngestionHandler, "_finalize_checkpoint", "checkpoint finalize")
        clock.wrap(dw.IngestionHandler, "_log_ingestion_success", "ingestion record")

        # Inside the write, per 1,000-row chunk.
        clock.wrap(ingestion_checkpoint, "record_chunk_progress", "  checkpoint offset")
        clock.wrap(heartbeat, "beat", "  heartbeat")

        clock.wrap(crud, "apply_batch_updates", "  apply_batch_updates",
                   on_call=note_transaction)
        clock.wrap(crud, "bulk_upsert_cell_sources", "    bulk_upsert_cell_sources")
        clock.wrap(crud, "bulk_upsert_cell_overwrites", "    bulk_upsert_cell_overwrites")
        clock.wrap(crud, "bulk_insert_audit_logs", "    bulk_insert_audit_logs")
        # 🔴 THE SAME SEAT, SPLIT BY WHO CALLED IT - which is what says whether a stage
        # is waiting on the database or spending its time in Python. Without this split a
        # stage that is 90 % SQL and one that is 90 % dict-building look identical, and
        # they take opposite fixes.
        clock.wrap_split_by_caller(
            OrmSession, "execute",
            [("    bulk_upsert_cell_sources", "      SQL in cell-source upsert"),
             ("    bulk_insert_audit_logs", "      SQL in audit insert"),
             ("  apply_batch_updates", "      SQL elsewhere in apply"),
             ("WRITE (whole file)", "  SQL elsewhere in the write")],
            "SQL outside the write")

        # ⚠️ THE BULK UPSERT DOES NOT GO THROUGH `Session.execute` AT ALL - measured, the
        # seat above counted ZERO calls inside it. It sends one multi-row statement per
        # chunk straight at the driver, so the seat that says "waiting on the database"
        # for this stage is `Connection.exec_driver_sql`, and reading the Session seat's
        # zero as "no SQL here" would have been reading the instrument, not the code.
        clock.wrap_split_by_caller(
            EngineConnection, "exec_driver_sql",
            [("    bulk_upsert_cell_sources", "      driver send (cell sources)"),
             ("    bulk_upsert_cell_overwrites", "      driver send (cell overwrites)"),
             ("    bulk_insert_audit_logs", "      driver send (audit logs)"),
             ("  apply_batch_updates", "      driver send (elsewhere in apply)")],
            "driver send (outside apply)")

        clock.wrap_split_by_caller(
            OrmSession, "commit",
            [("  apply_batch_updates", "    commit (inside apply)"),
             ("WRITE (whole file)", "  commit (chunk)")],
            "commit (outside the write)")

        handler = dw.IngestionHandler(
            workspace_path=workspace,
            config_path=None,
            archives_path=os.path.join(workspace, "archives"),
            default_table_name=table)

        started = time.perf_counter()
        # delay=0: the 1 s debounce is a fixed constant that waits for a file copy to
        # finish, not a per-row cost, and this file was written by this process.
        handler.process_with_retry(file_path, uploader="probe", delay=0.0)
        total = time.perf_counter() - started
    finally:
        clock.restore()

    with engine.connect() as connection:
        outbox_after = connection.execute(
            text("SELECT COALESCE(MAX(id), 0) FROM database_outbox")).scalar()
        landed = connection.execute(
            text(f'SELECT COUNT(*) FROM "{table}" WHERE business_key_val LIKE :p'),
            {"p": f"{label}%"}).scalar()
        cells = connection.execute(
            text('SELECT COUNT(*) FROM cell_sources WHERE row_id IN '
                 f'(SELECT row_id FROM "{table}" WHERE business_key_val LIKE :p)'),
            {"p": f"{label}%"}).scalar()
        audits = 0
        for tx in transactions:
            audits += connection.execute(
                text("SELECT COUNT(*) FROM audit_logs WHERE transaction_id = :t"),
                {"t": tx}).scalar() or 0

    report(clock, total, rows)
    print()
    print("MARKS LEFT ON THIS BOX (nothing was deleted)")
    print(f"  table            {table}")
    print(f"  business keys    {label}%   ({landed:,} row(s) present)")
    print(f"  cell sources     {cells:,}")
    print(f"  audit logs       {audits:,}  (transaction(s): {', '.join(sorted(transactions))})")
    print(f"  outbox rows      {outbox_after - outbox_before:,} "
          f"(id {outbox_before} -> {outbox_after})")
    print(f"  workspace        {workspace}"
          + ("" if keep_workspace else "  (removed)"))
    if not keep_workspace:
        shutil.rmtree(work_root, ignore_errors=True)


def report(clock: Clock, total: float, rows: int):
    order = [
        "file signature (sha256)",
        "dedup lookup",
        "parse pass 1 (count+header)",
        "checkpoint plan",
        "WRITE (whole file)",
        "  apply_batch_updates",
        "    bulk_upsert_cell_sources",
        "      SQL in cell-source upsert",
        "      driver send (cell sources)",
        "    bulk_upsert_cell_overwrites",
        "    bulk_insert_audit_logs",
        "      SQL in audit insert",
        "      driver send (audit logs)",
        "      SQL elsewhere in apply",
        "      driver send (elsewhere in apply)",
        "    commit (inside apply)",
        "  checkpoint offset",
        "  commit (chunk)",
        "  heartbeat",
        "  SQL elsewhere in the write",
        "archive file",
        "commit (outside the write)",
        "SQL outside the write",
        "checkpoint finalize",
        "ingestion record",
    ]
    print()
    print(f"{'stage':34s} {'seconds':>9s} {'% file':>7s} {'calls':>7s} {'ms/row':>8s}")
    print("-" * 70)
    for label in order:
        if label not in clock.seconds:
            continue
        seconds = clock.seconds[label]
        print(f"{label:34s} {seconds:9.3f} {seconds / total * 100:6.1f}% "
              f"{clock.calls[label]:7d} {seconds / rows * 1000:8.3f}")

    # The remainders are the point of a tree: what is left when the named children are
    # taken out of their parent is a stage too, and it is usually where the surprise is.
    def left_over(parent, children):
        if parent not in clock.seconds:
            return None
        return clock.seconds[parent] - sum(clock.seconds.get(c, 0.0) for c in children)

    print("-" * 70)
    inside_apply = left_over("  apply_batch_updates", [
        "    bulk_upsert_cell_sources", "    bulk_upsert_cell_overwrites",
        "    bulk_insert_audit_logs", "    commit (inside apply)",
        "      SQL elsewhere in apply", "      driver send (elsewhere in apply)"])
    inside_write = left_over("WRITE (whole file)", [
        "  apply_batch_updates", "  checkpoint offset", "  commit (chunk)", "  heartbeat",
        "  SQL elsewhere in the write"])
    inside_cells = left_over("    bulk_upsert_cell_sources",
                             ["      SQL in cell-source upsert",
                              "      driver send (cell sources)"])
    if inside_cells is not None:
        print(f"{'      REST OF cell upsert (python)':34s} {inside_cells:9.3f} "
              f"{inside_cells / total * 100:6.1f}% {'':7s} {inside_cells / rows * 1000:8.3f}")
    if inside_apply is not None:
        print(f"{'    REST OF apply_batch_updates':34s} {inside_apply:9.3f} "
              f"{inside_apply / total * 100:6.1f}% {'':7s} {inside_apply / rows * 1000:8.3f}")
    if inside_write is not None:
        print(f"{'  REST OF WRITE (normalise+parse2)':34s} {inside_write:9.3f} "
              f"{inside_write / total * 100:6.1f}% {'':7s} {inside_write / rows * 1000:8.3f}")
    named = sum(clock.seconds.get(l, 0.0) for l in order if not l.startswith(" "))
    print(f"{'OUTSIDE EVERY NAMED STAGE':34s} {total - named:9.3f} "
          f"{(total - named) / total * 100:6.1f}%")
    print("-" * 70)
    print(f"{'FILE TOTAL':34s} {total:9.3f} {100.0:6.1f}% {'':7s} "
          f"{total / rows * 1000:8.3f}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Split one watcher ingestion into stages, in this process.")
    parser.add_argument("--table", required=True,
                        help="the declared table to ingest into")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--label", default=None,
                        help="business-key prefix for the rows this run writes; the "
                             "default carries a fresh run id so two runs never collide")
    parser.add_argument("--number-start", type=int, default=0,
                        help="where the numeric columns start, so a run can be aimed at "
                             "a range nothing has written")
    parser.add_argument("--work-dir", default=None,
                        help="where the throwaway workspace is built (default: a temp dir)")
    parser.add_argument("--keep-workspace", action="store_true",
                        help="leave the workspace and its archived file on disk")
    args = parser.parse_args(argv)

    label = args.label or f"PROBE-S118-{uuid.uuid4().hex[:8].upper()}"
    work_root = args.work_dir or tempfile.mkdtemp(prefix="probe_ingestion_")
    os.makedirs(work_root, exist_ok=True)
    try:
        run(args.table, args.rows, label, args.number_start, work_root,
            args.keep_workspace)
    except ProbeRefusal as refusal:
        print(f"REFUSED: {refusal}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
