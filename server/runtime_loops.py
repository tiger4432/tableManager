# -*- coding: utf-8 -*-
"""S-176. What the nine loops of this deployment last did — values, never a verdict.

🔴 THIS IS NOT `/health`, AND THE SPLIT IS THE POINT (판정 282). `/health` JUDGES: it
answers ok / degraded / unhealthy and an HTTP status, because a monitor needs one number
to alert on. This answers WHAT THE VALUES ARE, because an operator asking 「is the chain
moving?」 needs the lap and the queue, not a verdict someone else computed from them. Two
routes with two jobs; one of them deciding for the other is how a screen comes to show a
green light beside a queue that has not moved in an hour.

🔴 AND IT MEASURES NOTHING. Every number here was already computed by the loop that owns
it — the laps ride the process heartbeat that loop already writes (`heartbeat.record_lap`),
the outbox depth is the query `/admin/chain/queue` already runs, the pace comes from
`pacing.json` and the knob is a path. The one thing this file adds is the assembly.

⚠️ AN ABSENT CELL IS OMITTED, NEVER ZEROED. 「that loop has not reported a lap」 and
「that loop's last lap took 0 s」 are different facts, and a screen that renders them alike
is exactly the silence this round exists to remove.
"""
from __future__ import annotations

import time

from utils import heartbeat


#: The nine, in the order the board numbers them (①~⑦ with ③ split three ways).
#: `process` is which heartbeat carries it — several loops live in one process, which is
#: why the loop and the process are two columns rather than one.
LOOPS = (
    # (loop, process, board)
    ("web", "web", "1"),
    ("watcher", "watcher", "2"),
    ("chain", "chain", "3"),
    ("outbox_purge", "chain", "3-a"),
    ("listen", "chain", "3-b"),
    ("ledger_followup", "chain", "4"),
    ("ledger_census", "chain", "5"),
    ("scheduler", "scheduler", "6"),
    ("postgres", "postgres", "7"),
)

#: The knob an operator turns for each loop, when it has one. A path, not a value: the
#: value is the deployment's and this route does not read the owner's files.
KNOBS = {
    "watcher": "config/ingestion_settings.json",
    "chain": "config/chain_rules.json",
    "outbox_purge": "config/chain_rules.json",
    "ledger_followup": "config/pacing.json",
    "ledger_census": "config/pacing.json",
    "scheduler": "config/auto_update.json",
    "postgres": "server/scripts/tune_layer_tables.py",
}


def _lap_cells(entry, loop):
    """The lap this loop last recorded, flattened into the route's column names."""
    lap = ((entry or {}).get("laps") or {}).get(loop)
    if not isinstance(lap, dict):
        return {}
    out = {}
    if lap.get("at"):
        out["last_at"] = round(float(lap["at"]), 3)
    if lap.get("age_seconds") is not None:
        out["last_age_seconds"] = lap["age_seconds"]
    if lap.get("seconds") is not None:
        out["last_seconds"] = lap["seconds"]
    if lap.get("depth") is not None:
        out["depth"] = lap["depth"]
    if lap.get("pace") is not None:
        out["pace"] = lap["pace"]
    # Anything else the loop chose to carry (`state`, `reconnects`, `table`, `items` ...)
    # rides through by name. A carrier that only passed a fixed four would make the next
    # loop's own fact unreportable without editing this file.
    for key, value in lap.items():
        if key not in ("at", "age_seconds", "seconds", "depth", "pace"):
            out[key] = value
    return out


def _outbox_depth(db):
    """The chain's backlog — the same question `/admin/chain/queue` asks, asked once."""
    from sqlalchemy import func as _f
    from database import models

    outbox = models.DatabaseOutbox
    return db.query(_f.count()).select_from(outbox).filter(
        outbox.processed_chain == False).scalar()          # noqa: E712 (partial index)


def _vacuum_phase(db):
    """`{alive, phase, relation}` when PostgreSQL is vacuuming something, else idle.

    ⚠️ THE STARTUP `LayerHealth` LINE IS DELIBERATELY NOT HERE (판정 282). It is a value
    from boot, not a state, and publishing it beside live ones would let a screen read a
    fact from hours ago as 「now」.
    """
    from sqlalchemy import text

    if db.get_bind().dialect.name != "postgresql":
        return {"alive": None}
    row = db.execute(text(
        "SELECT relid::regclass::text AS relation, phase, heap_blks_scanned, "
        "       heap_blks_total FROM pg_stat_progress_vacuum LIMIT 1")).fetchone()
    if row is None:
        return {"alive": True, "state": "idle"}
    cells = {"alive": True, "state": "vacuuming", "phase": row.phase,
             "relation": row.relation}
    if row.heap_blks_total:
        cells["depth"] = int(row.heap_blks_total) - int(row.heap_blks_scanned or 0)
    return cells


def runtime_loops(db, *, heartbeats=None, now=None):
    """The nine entries. `db` is used for exactly two questions, both already asked
    elsewhere: the outbox backlog and whether a vacuum is running."""
    beats = heartbeat.read_all() if heartbeats is None else heartbeats
    now = time.time() if now is None else now

    out = []
    for loop, process, board in LOOPS:
        item = {"loop": loop, "process": process, "board": board}
        if loop == "web":
            # ① has no heartbeat and needs none: this route IS the web process answering.
            # A lap would be a number invented for the table's sake.
            item["alive"] = True
        elif process == "postgres":
            item.update(_vacuum_phase(db))
        else:
            entry = beats.get(process)
            if entry is not None:
                # ⛔ `alive` IS THE PROCESS'S, AND SAYS SO by sitting beside `process`.
                # A loop inside a live process can still be wedged; that is what its lap
                # age is for, and conflating the two would publish a green light for a
                # loop that stopped an hour ago.
                item["alive"] = not entry.get("stale")
                item["beat_age_seconds"] = entry.get("age_seconds")
                item.update(_lap_cells(entry, loop))
        if loop == "chain":
            try:
                item["depth"] = _outbox_depth(db)
            except Exception as exc:                        # noqa: BLE001
                item["depth_error"] = f"{type(exc).__name__}"
        knob = KNOBS.get(loop)
        if knob:
            item["knob"] = knob
        out.append(item)
    return {"generated_at": round(now, 3), "loops": out}
