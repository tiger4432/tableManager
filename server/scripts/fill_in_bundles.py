"""Fill a source in BUNDLES, waiting for the chain between them (ruling 209).

🔴 WHY BUNDLES AND NOT ONE POUR. Measured 2026-09-09: the door writes about 900 rows a second
and the chain drains about 34, so a continuous ten-million-row pour finishes writing in about
three hours and then leaves the queue draining for roughly three days. A bundle that waits for
its own drain keeps the backlog bounded by ONE bundle, makes the queue depth a value somebody
can read while it runs, and gives a place to stop: if a bundle's drain time grows, the next one
has not started yet.

🔴 IT DOES NOT WRITE ANYTHING ITSELF. Rows go through `generate_source_rows.py`, which goes
through `product_door.py` - the same door production uses. This file is a loop, a clock and a
count; it opens the database only to READ the outbox depth and the atom count.

⛔ DRY RUN IS THE DEFAULT and `--apply` alone is not enough: `--apply` needs
`--i-accept-a-long-running-fill` beside it, because the thing this schedules is measured in
hours and the operator should have said so twice. The same shape S-77's scripts use.

WHAT IT REPORTS, per bundle and in total:
    sent / changed     `changed` is the server's `updated_count`. A bundle whose `changed` is
                       zero re-sent rows that already existed and measured nothing - the run
                       stops rather than reporting a fast bundle that did no work.
    requests, max s    the gate is stated per request, so the slowest request is the number
    drain s            wall time from the last request until the outbox is empty
    peak depth         the highest backlog seen, sampled every second
    atoms delta        counted from the ledger, so the declared multiplier is checked rather
                       than assumed
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.abspath(os.path.join(_HERE, ".."))
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import product_door                                                  # noqa: E402

#: Measured 2026-09-09 on this box, and used only to REFUSE a run that cannot fit.
#: atoms 1,626 B each x the source's multiplier + source row 899 B + five cell-layer rows
#: at 739 B + the row-ref index at 1,150 B. Stated per SOURCE ROW so the arithmetic below
#: reads in the same unit the operator asked for.
BYTES_PER_ROW_ESTIMATE = 899 + 5 * 739 + 1150 + 2 * 1626
DEFAULT_BUNDLES = 10
DEFAULT_ROWS = 1_000_000
DRAIN_POLL_SECONDS = 1.0


class FillRefusal(Exception):
    """A refusal that names what is wrong, rather than starting something that runs for days."""


def _engine():
    import paths
    from sqlalchemy import create_engine

    return create_engine(paths.DEFAULT_PG_URL, pool_pre_ping=True)


def outbox_depth(engine) -> int:
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SET statement_timeout = '30s'"))
        depth = connection.execute(text(
            "SELECT count(*) FROM database_outbox WHERE status <> 'SUCCESS'")).scalar()
        connection.rollback()
    return int(depth or 0)


def atom_count(engine, source: str) -> int:
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SET statement_timeout = '120s'"))
        count = connection.execute(text(
            "SELECT count(*) FROM ledger_events WHERE source_who = :source"),
            {"source": source}).scalar()
        connection.rollback()
    return int(count or 0)


def deletion_cost(*, rows_sent: int, atoms_per_row: int, atoms_gained: int) -> dict:
    """What this bundle's write cost in DELETIONS, from numbers that exist (판정 210).

    🔴 THE CURSOR'S COUNTERS CANNOT ANSWER THIS, and the first version of this file read them
    anyway. A door write reaches the ledger by the LIVE path, and `runtime_v2` passes
    `advance_cursor=False` there, so `atoms_written` and `atoms_deduped` do not move for these
    bundles at all: `written - deduped - gained` would have printed a large NEGATIVE
    "replaced" every time. Measured before the first bundle rather than after.

    So the shortfall is stated in the two numbers that are real - what the declaration says
    this many rows produce, and what the ledger actually gained:

        expected = rows x atoms_per_row      (the declared multiplier, not a guess)
        shortfall = expected - gained

    A fill of NEW rows should show 0. Anything else means those rows were translated before
    and this bundle replaced or deduplicated them - the deletion whose price ruling 210 asked
    to keep visible. It does NOT separate "replaced" from "deduplicated": both are a write
    that did not become a new row, and the store reports neither to a caller out here.
    """
    expected = int(rows_sent or 0) * int(atoms_per_row or 0)
    return {"atoms_expected": expected, "atoms_gained": int(atoms_gained),
            "atoms_shortfall": expected - int(atoms_gained)}


def wait_for_drain(engine, *, limit_seconds: float, log=print):
    """Block until the outbox is empty. Returns (seconds, peak depth, timed_out)."""
    started, peak = time.monotonic(), 0
    while True:
        depth = outbox_depth(engine)
        peak = max(peak, depth)
        elapsed = time.monotonic() - started
        if depth == 0 and elapsed > 3:
            return round(elapsed, 1), peak, False
        if elapsed > limit_seconds:
            log("    drain did not finish in %.0fs; depth is %d" % (limit_seconds, depth))
            return round(elapsed, 1), peak, True
        time.sleep(DRAIN_POLL_SECONDS)


def refuse_without_room(rows_total: int, *, data_directory: str) -> dict:
    """Refuse a fill the volume cannot hold, and say both numbers either way."""
    free = shutil.disk_usage(data_directory).free
    needed = rows_total * BYTES_PER_ROW_ESTIMATE
    room = {"free_bytes": free, "estimate_bytes": needed,
            "free_gb": round(free / 1e9, 1), "estimate_gb": round(needed / 1e9, 1)}
    if needed > free:
        raise FillRefusal(
            "this fill is estimated at %.1f GB and the volume holding %s has %.1f GB free. "
            "Lower --bundles (each is %.1f GB) or free space first."
            % (needed / 1e9, data_directory, free / 1e9,
               needed / 1e9 / max(1, rows_total // DEFAULT_ROWS)))
    return room


def data_directory(engine) -> str:
    from sqlalchemy import text

    with engine.connect() as connection:
        path = connection.execute(text("SHOW data_directory")).scalar()
        connection.rollback()
    return str(path)


def run_bundle(args, index: int, start: int, log=print) -> dict:
    """One bundle through the generator. Returns its summary, or raises."""
    command = [sys.executable, os.path.join(_HERE, "generate_source_rows.py"),
               "--source", args.source, "--rows", str(args.rows),
               "--months", str(args.months), "--start", str(start),
               "--url", args.url]
    if args.maps:
        command += ["--maps", str(args.maps)]
    command += ["--apply"] if args.apply else ["--dry-run", "--json"]
    started = time.monotonic()
    finished = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    text_out = (finished.stdout or "") + (finished.stderr or "")
    if "REFUSED" in text_out:
        raise FillRefusal("bundle %d refused: %s" % (
            index, next(line for line in text_out.split("\n") if "REFUSED" in line)))
    if finished.returncode != 0:
        raise FillRefusal("bundle %d failed: %s" % (index, text_out.strip()[:400]))
    # 🔴 TWO SHAPES, AND THE FIRST DRAFT READ ONLY ONE. `--dry-run --json` prints the whole
    # PLAN, whose `column_types` puts braces after the ones that matter, so slicing from the
    # LAST `{` parsed a fragment and every field came back `None` - a table that printed and
    # said nothing. `--apply` prints a short summary at the END, after human-readable lines,
    # so slicing from the first `{` fails there instead. Both are tried, widest first.
    summary = {}
    for slice_text in (text_out[text_out.find("{"):text_out.rfind("}") + 1]
                       if "{" in text_out and "}" in text_out else "",
                       text_out[text_out.rfind("{"):] if "{" in text_out else ""):
        try:
            candidate = json.loads(slice_text)
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate:
            summary = candidate
            break
    if not summary:
        raise FillRefusal(
            "bundle %d produced no readable summary; the generator said: %s"
            % (index, text_out.strip()[:300]))
    summary["wall_seconds"] = round(time.monotonic() - started, 2)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source", default="dt_job",
                        help="ledger source id to fill (default dt_job)")
    parser.add_argument("--bundles", type=int, default=DEFAULT_BUNDLES)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                        help="rows per bundle")
    parser.add_argument("--months", type=int, default=1)
    parser.add_argument("--maps", type=int, default=0,
                        help="20x20 maps per bundle, each of a different material")
    parser.add_argument("--start", type=int, required=True,
                        help="first row index; must clear every row already generated")
    parser.add_argument("--url", default=product_door.DEFAULT_BASE_URL)
    parser.add_argument("--drain-limit", type=float, default=3600.0,
                        help="seconds to wait for one bundle's drain before saying so")
    parser.add_argument("--apply", action="store_true",
                        help="actually write; needs the acceptance flag too")
    parser.add_argument("--i-accept-a-long-running-fill", dest="accepted",
                        action="store_true")
    args = parser.parse_args(argv)

    if args.apply and not args.accepted:
        print("REFUSED: --apply needs --i-accept-a-long-running-fill beside it. "
              "This schedules hours of writing and days of chain work.")
        return 2

    engine = _engine()
    total_rows = args.bundles * args.rows
    try:
        room = refuse_without_room(total_rows, data_directory=data_directory(engine))
    except FillRefusal as refusal:
        print("REFUSED: %s" % refusal)
        return 2

    print("source        %s" % args.source)
    print("bundles       %d x %d rows = %d" % (args.bundles, args.rows, total_rows))
    print("start         %d .. %d" % (args.start, args.start + total_rows - 1))
    print("disk          estimate %.1f GB   free %.1f GB" % (
        room["estimate_gb"], room["free_gb"]))
    print("mode          %s" % ("APPLY" if args.apply else "dry run -- nothing is written"))
    print("")

    results, start = [], args.start
    for index in range(1, args.bundles + 1):
        try:
            summary = run_bundle(args, index, start)
        except FillRefusal as refusal:
            print("REFUSED: %s" % refusal)
            return 1
        if not args.apply:
            print("  bundle %2d  start %-9d rows %-8s atoms/row %-3s -> atoms %s"
                  % (index, start, summary.get("rows"), summary.get("atoms_per_row"),
                     (summary.get("rows") or 0) * (summary.get("atoms_per_row") or 0)))
            results.append(summary)
            start += args.rows
            continue

        sent = summary.get("rows_sent")
        changed = summary.get("rows_changed")
        if not changed:
            print("  bundle %2d  sent %s but CHANGED 0 -- these rows already existed, so "
                  "this bundle measured nothing. Stopping." % (index, sent))
            return 1
        before = atom_count(engine, args.source)
        drained, peak, timed_out = wait_for_drain(
            engine, limit_seconds=args.drain_limit)
        after = atom_count(engine, args.source)
        gained = after - before
        cost = deletion_cost(rows_sent=sent or 0,
                             atoms_per_row=summary.get("atoms_expected", 0) // max(sent or 1, 1),
                             atoms_gained=gained)
        print("  bundle %2d  sent %-8s changed %-8s requests %-4s max %-6ss  "
              "drain %-7ss peak %-5d atoms %+d%s"
              % (index, sent, changed, summary.get("requests"),
                 summary.get("seconds_max"), drained, peak, gained,
                 "  (drain unfinished)" if timed_out else ""))
        # 🔴 판정 210's condition: withdrawal stays a deletion, so the price of deleting is
        # printed beside every bundle instead of being reconstructed later. 0 is the value a
        # fill of new rows should show; anything else is a write that did not become a row.
        print("             atoms expected %-9d gained %-9d shortfall %-7d in %.1fs"
              % (cost["atoms_expected"], cost["atoms_gained"], cost["atoms_shortfall"],
                 (summary.get("wall_seconds") or 0) + drained))
        results.append({**summary, **cost, "drain_seconds": drained,
                        "peak_depth": peak, "atoms_delta": gained})
        start += args.rows

    if args.apply:
        print("")
        print("totals  rows %d   requests %d   drain %.0fs   peak depth %d"
              % (sum(r.get("rows_sent") or 0 for r in results),
                 sum(r.get("requests") or 0 for r in results),
                 sum(r.get("drain_seconds") or 0 for r in results),
                 max((r.get("peak_depth") or 0) for r in results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
