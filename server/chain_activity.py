# -*- coding: utf-8 -*-
"""What a chain mapper is doing RIGHT NOW, in this process, for the queue view.

Same shape as `ingestion_activity`: an in-memory registry that the thing doing the work
updates, and a route that READS it. No broadcast, no database column, no route of its
own - `GET /admin/chain/queue` already answers "what is the chain doing" and this is the
half of that answer the outbox cannot give. The outbox says what is WAITING; only the
process running the mapper knows what is IN it.

🔴 IT IS UPDATED BY A DIRECT CALL, NOT OVER HTTP, and that is a deliberate difference
from `ingestion_activity`. The watcher is always a separate process, so its state has to
travel; the chain loop is started inside the web server's own startup
(`main.py`, `start_chain_ingestion_worker`), so in that deployment the mapper and the
route share a process and an HTTP hop between them would be a hop to itself.

🔴 AND WHEN THEY DO NOT SHARE A PROCESS, THIS SAYS SO. Run `run_chain_worker.py`
separately and the loop updates ITS registry while the API serves an empty one - and an
empty list would read as "nothing is running" when the truth is "I cannot see it". That
is the same lying zero this repository spent the day removing elsewhere, so `attached`
is published beside the list: it is True only in the process whose own chain loop
started, and a reader that gets `attached: false` knows the list is blind rather than
empty.
"""

import threading
import time


class ChainActivityRegistry:
    """Mapper executions in flight in THIS process. Thread-safe, bounded by concurrency."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running = {}
        self._attached = False
        self._attached_at = None
        self._reloaded_at = None
        self._purged_at = None
        self._purged_rows = None
        self._purge_capped = None
        self._seq = 0

    def attach(self):
        """Called by the chain loop as it starts. Marks this process as the one that runs
        mappers, which is what makes an empty list mean "idle" instead of "blind"."""
        with self._lock:
            self._attached = True
            self._attached_at = time.time()

    def note_reload(self):
        """A SYSTEM_RELOAD re-imported the mapper modules in THIS process.

        🔴 IT WAS ALREADY RECORDED AND COULD NOT LEAVE. `QueueHeadWatch.note_reload` has
        kept this instant since the stall watcher landed, and it leaves only as TEXT
        inside a sentence the loop logs -- and only once the queue head has already been
        stuck for a minute. So the one question this answers ("is the state in this
        process rather than in the data?") could be asked only by someone already reading
        the log of a system already stalled.

        ⚠️ NEVER-RELOADED STAYS `None`. `0` would read as "just now", which is the
        opposite fact, and the loop starting is not a reload.
        """
        with self._lock:
            self._reloaded_at = time.time()

    def note_outbox_purge(self, deleted, capped):
        """The last outbox retention purge in this process: how many rows went, and
        whether it stopped at its PER-CYCLE cap with more still expired.

        🔴 THE COUNT ALONE CANNOT SAY IT. The purge deletes in chunks up to
        `OUTBOX_PURGE_MAX_CHUNKS` and carries the remainder to the next cycle, so
        "the cap bound" and "that is all there was" arrive as the SAME number. A
        deployment whose arrival rate outruns the purge rate therefore grows a
        backlog whose only symptom is disk, and nothing in the system says so.

        ⚠️ `capped=None` IS A THIRD STATE, not a shy False. The cycle raised partway,
        so the count is partial and the question has no answer yet -- exactly the
        distinction `mapper_reload_age_seconds` keeps with its own `None`.
        """
        with self._lock:
            self._purged_at = time.time()
            self._purged_rows = int(deleted or 0)
            self._purge_capped = None if capped is None else bool(capped)

    @property
    def attached(self) -> bool:
        with self._lock:
            return self._attached

    def start(self, rule, mapper, target_table, rows_in):
        """Record an execution and return the token that ends it."""
        with self._lock:
            self._seq += 1
            token = self._seq
            self._running[token] = {
                "rule": rule, "mapper": mapper, "target_table": target_table,
                "rows_in": rows_in, "started": time.time(),
            }
        return token

    def finish(self, token):
        """Idempotent, and never raises: a registry that can fail must not be able to take
        down the mapper it is describing."""
        with self._lock:
            self._running.pop(token, None)

    def snapshot(self) -> list:
        now = time.time()
        with self._lock:
            entries = sorted(self._running.values(), key=lambda e: e["started"])
            return [{"rule": e["rule"], "mapper": e["mapper"],
                     "target_table": e["target_table"], "rows_in": e["rows_in"],
                     "running_seconds": round(now - e["started"], 3)}
                    for e in entries]

    def ages(self) -> dict:
        """How long this process's loop has been up, and how long since it re-imported.

        Ages rather than instants: the reader is comparing them with each other and with
        `oldest_waiting_seconds`, and a clock string would have to be reconciled against
        the reader's own clock first.
        """
        now = time.time()
        with self._lock:
            attached_at, reloaded_at = self._attached_at, self._reloaded_at
            purged_at = self._purged_at
            purged_rows, purge_capped = self._purged_rows, self._purge_capped
        return {
            "loop_uptime_seconds": (None if attached_at is None
                                    else round(now - attached_at, 3)),
            "mapper_reload_age_seconds": (None if reloaded_at is None
                                          else round(now - reloaded_at, 3)),
            # [P-6] Flat, like the two above, so the route that spreads this dict does
            # not change. `outbox_purge_capped` is the one that carries the fact the
            # row count cannot: True = stopped at the per-cycle cap with more expired
            # rows waiting, False = drained everything expired, None = never ran, or
            # the last cycle raised before it could tell.
            "outbox_purge_age_seconds": (None if purged_at is None
                                         else round(now - purged_at, 3)),
            "outbox_purge_deleted": purged_rows,
            "outbox_purge_capped": purge_capped,
        }

    def clear(self):
        with self._lock:
            self._running.clear()
            self._attached_at = None
            self._reloaded_at = None
            self._purged_at = None
            self._purged_rows = None
            self._purge_capped = None
            self._seq = 0


#: Process singleton, the same shape `ingestion_activity` publishes.
registry = ChainActivityRegistry()
