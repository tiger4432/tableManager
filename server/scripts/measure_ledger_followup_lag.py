"""How far the ledger follow-up and the census fall behind a real chain load (S-95, ruling 232).

WHAT IT MEASURES, and in which mode each number means something:

    follow-up lag     an outbox event's queue instant -> the instant that event is handled.
                      This is the number S-94 is about: measured 2026-09-10 it steps by
                      ~35s per event in INTEGRATED mode and ~43s DECOUPLED, so separating
                      the processes does not help it - the cost is the chain group's own
                      work. Compare before/after a chain change with this, not with a
                      single event's time.
    census staleness  the oldest `census.measured_at` the declaration route reports. This
                      one IS contention: 81s integrated against ~60s decoupled on the same
                      load, over an idle ceiling of one full pass (15 sources x ~3.1s).
                      Production runs decoupled, so the integrated figure is this box's.
    queue remainder   the chain's own downstream events left unhandled when the window
                      closes. Zero is not expected under a burst; a number that grows run
                      to run is the finding.

⚠️ "handled" IS BATCH-ASSIGNED. Watching a drain shows pending climb and then drop to zero
at once, so an event's handled instant is when the GROUP it belongs to finished, not when
that event alone was processed. Read the per-event steps as group boundaries.

🔴 IT REFUSES TO START ON A DIRTY QUEUE, and that refusal is the whole reason this is a
script rather than a scratch file. The first decoupled comparison ran while the previous
run's backlog was still draining and read +110s for its first event - a number about the
leftover queue, not about the mode. The check is one SELECT; the mistake cost a re-run and
nearly cost a wrong conclusion.

Everything here is a SELECT or a GET. The load goes through the product door
(`generate_source_rows.py`), which is the path production writes by.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.abspath(os.path.join(_HERE, ".."))
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import product_door                                                  # noqa: E402

DEFAULT_ROWS = 10000
DEFAULT_WATCH = 300.0
SAMPLE_SECONDS = 1.0
SOURCE = "dt_job"


class MeasurementRefusal(Exception):
    """A refusal that names what would have made the numbers meaningless."""


def _engine():
    import paths
    from sqlalchemy import create_engine

    return create_engine(paths.DEFAULT_PG_URL, pool_pre_ping=True)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def outbox_depth(engine) -> int:
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SET statement_timeout = '30s'"))
        depth = connection.execute(text(
            "SELECT count(*) FROM database_outbox WHERE status <> 'SUCCESS'")).scalar()
        connection.rollback()
    return int(depth or 0)


def atom_count(engine, source: str = SOURCE) -> int:
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SET statement_timeout = '120s'"))
        count = connection.execute(text(
            "SELECT count(*) FROM ledger_events WHERE source_who = :source"),
            {"source": source}).scalar()
        connection.rollback()
    return int(count or 0)


def census_oldest(base_url: str):
    """(seconds stale, source) for the oldest `census.measured_at`, or (None, None)."""
    opener = product_door.opener()
    try:
        with opener.open(base_url.rstrip("/") + "/api/ledger/declaration",
                         timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None, None
    worst, who = None, None
    for source in body.get("sources") or []:
        stamp = (source.get("census") or {}).get("measured_at")
        if not stamp:
            continue
        age = (_now() - datetime.datetime.fromisoformat(stamp)).total_seconds()
        if worst is None or age > worst:
            worst, who = age, source.get("source")
    return worst, who


def refuse_dirty_queue(engine, *, allow_backlog: bool) -> int:
    depth = outbox_depth(engine)
    if depth and not allow_backlog:
        raise MeasurementRefusal(
            "the outbox holds %d unhandled event(s), so this run's lag would be about that "
            "backlog rather than about this load. Wait for it to drain (the chain clears a "
            "group at a time), or pass --allow-backlog if a loaded queue is the subject."
            % depth)
    return depth


def _refuse_a_load_that_wrote_nothing(load, output: str) -> None:
    """A run whose load wrote nothing has no lag to measure, and it LOOKS like success.

    🔴 TWO WAYS TO WRITE NOTHING, AND BOTH USED TO PRINT A TIDY EMPTY TABLE. A `--start`
    over rows that already exist re-sends identical upserts, so the server answers 200 with
    `updated_count` 0 and no event is queued: the report then reads "handled 0 of 0", which
    is the shape of a clean fast run rather than of a run that did not happen. A refused
    connection does the same thing from the other end. Named here, before the table.
    """
    if load.poll() not in (0, None):
        # 🔴 THE CHILD'S BYTES MUST NOT REACH THIS CONSOLE UNCHANGED, at read OR at print.
        # Reading with `errors="replace"` stopped the parent dying on cp949 Korean, and then
        # the U+FFFD it produced killed the parent AT THE PRINT instead - the same fault
        # moved four lines down. What identifies the failure (`URLError`, `WinError 10061`)
        # is ASCII, so the quoted tail is forced to ASCII and the rest costs a dot.
        tail = " / ".join(line.strip() for line in (output or "").split("\n")
                          if line.strip())[-300:]
        raise MeasurementRefusal(
            "the load failed (exit %s), so nothing was written. It said: %s"
            % (load.poll(), tail.encode("ascii", "replace").decode("ascii")))
    changed = None
    if "{" in (output or ""):
        try:
            changed = json.loads(output[output.rindex("{"):]).get("rows_changed")
        except ValueError:
            changed = None
    if changed == 0:
        raise MeasurementRefusal(
            "the load sent its rows and the server changed NONE of them - this --start is "
            "over rows that already exist, so no event was queued and there is no lag to "
            "measure. Raise --start past every generated index.")


def run(engine, args) -> dict:
    started_at = _now()
    load = subprocess.Popen(
        [sys.executable, os.path.join(_HERE, "generate_source_rows.py"),
         "--source", args.source, "--rows", str(args.rows), "--months", "1",
         "--start", str(args.start), "--apply", "--url", args.url],
        # 🔴 `errors="replace"`: the child's refusals are Korean and this console is cp949,
        # so a strict decode raised in the PARENT and killed a measurement that had already
        # run. A byte this cannot decode must cost one glyph, never the run.
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace")

    base_atoms = atom_count(engine, args.source)
    stales, t0 = [], time.monotonic()
    while time.monotonic() - t0 < args.watch_seconds:
        depth = outbox_depth(engine)
        gained = atom_count(engine, args.source) - base_atoms
        stale, who = census_oldest(args.url)
        if stale is not None:
            stales.append((stale, who))
        if load.poll() is not None and depth == 0:
            break
        time.sleep(SAMPLE_SECONDS)
    output = load.communicate()[0] if load.poll() is not None else ""
    _refuse_a_load_that_wrote_nothing(load, output)

    from sqlalchemy import text
    with engine.connect() as connection:
        connection.execute(text("SET statement_timeout = '60s'"))
        events = connection.execute(text(
            "SELECT event_type, table_name, created_at, processed_at "
            "FROM database_outbox WHERE created_at >= :since ORDER BY created_at"),
            {"since": started_at}).fetchall()
        connection.rollback()
    return {"events": events, "stales": stales, "load": output or "",
            "atoms": atom_count(engine, args.source) - base_atoms,
            "remaining": outbox_depth(engine)}


def report(result, args) -> None:
    events = result["events"]
    load_table = [row for row in events if row[1] == args.relation]
    downstream = [row for row in events if row[1] != args.relation]

    print("")
    print("  event                     queued     handled")
    previous, handled = None, 0
    for row in load_table:
        queued, done = row[2], row[3]
        if done is None:
            print("  %-24s %s   not in the window" % (row[1], queued.strftime("%H:%M:%S")))
            continue
        seconds = (done - queued).total_seconds()
        step = "" if previous is None else "   step %+.1fs" % (seconds - previous)
        print("  %-24s %s   %+.1fs%s"
              % (row[1], queued.strftime("%H:%M:%S"), seconds, step))
        previous, handled = seconds, handled + 1

    steps = []
    times = [(r[3] - r[2]).total_seconds() for r in load_table if r[3] is not None]
    for earlier, later in zip(times, times[1:]):
        steps.append(later - earlier)
    print("")
    print("  handled in the window     %d of %d" % (handled, len(load_table)))
    if steps:
        print("  seconds per event         %.1f  (mean of %d steps)"
              % (sum(steps) / len(steps), len(steps)))
    stales = [value for value, _ in result["stales"]]
    if stales:
        worst = max(result["stales"], key=lambda pair: pair[0])
        print("  census staleness          max %.1fs (%s)   median %.1fs"
              % (worst[0], worst[1], sorted(stales)[len(stales) // 2]))
    print("  atoms gained              %+d" % result["atoms"])
    print("  downstream events queued  %d  (handled %d)"
          % (len(downstream), sum(1 for row in downstream if row[3] is not None)))
    print("  queue remainder           %d" % result["remaining"])
    print("")
    # 🔴 ASCII ON STDOUT. This console is cp949 and an emoji here raised
    # `UnicodeEncodeError` AFTER the whole table had printed - a run that looks finished and
    # exits non-zero. The docstring keeps its marks; what goes to the terminal does not.
    print("  NOTE 'handled' is when that event's GROUP finished - see the module docstring.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("rows", nargs="?", type=int, default=DEFAULT_ROWS,
                        help="rows to write through the door (the door cuts at 1,000, so "
                             "this is also the event count x 1,000)")
    parser.add_argument("start", nargs="?", type=int, default=None,
                        help="first row index; must clear every row already generated")
    parser.add_argument("watch_seconds", nargs="?", type=float, default=DEFAULT_WATCH)
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--relation", default="dt_log",
                        help="the table the load writes, to tell it from the chain's own events")
    parser.add_argument("--url", default=product_door.DEFAULT_BASE_URL)
    parser.add_argument("--allow-backlog", action="store_true",
                        help="measure anyway on a non-empty queue (see the refusal's text)")
    args = parser.parse_args(argv)

    if args.start is None:
        print("REFUSED: a --start is required, and it must clear every row already "
              "generated - re-sending existing rows changes nothing and measures nothing.")
        return 2

    engine = _engine()
    try:
        depth = refuse_dirty_queue(engine, allow_backlog=args.allow_backlog)
    except MeasurementRefusal as refusal:
        print("REFUSED: %s" % refusal)
        return 2

    stale, who = census_oldest(args.url)
    print("source        %s -> %s" % (args.source, args.relation))
    print("load          %d rows from index %d" % (args.rows, args.start))
    print("before        queue %d   oldest census %s"
          % (depth, ("%.1fs (%s)" % (stale, who)) if stale is not None else "-"))
    try:
        result = run(engine, args)
    except MeasurementRefusal as refusal:
        print("REFUSED: %s" % refusal)
        return 2
    report(result, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
