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
        self._seq = 0

    def attach(self):
        """Called by the chain loop as it starts. Marks this process as the one that runs
        mappers, which is what makes an empty list mean "idle" instead of "blind"."""
        with self._lock:
            self._attached = True

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

    def clear(self):
        with self._lock:
            self._running.clear()
            self._seq = 0


#: Process singleton, the same shape `ingestion_activity` publishes.
registry = ChainActivityRegistry()
