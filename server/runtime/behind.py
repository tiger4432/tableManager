"""Work behind the reads (owner 11-09 «읽기는 쓰기에 영향 안 받음», lead 11-10 ㄴ): a read answers what was last made and
when, and the work that makes it again runs on the worker threads of its own `Behind` - one run at a time per key.

    the grid's whole counts     main.WHOLE_COUNTS     one worker, each table at most once per count_recount_seconds
    the rules' queue counts     main.QUEUE_COUNTS     one worker, the same keys and pacing (owner 11-10 «1 ㄱ»)
    the recent history          audit_cache._behind   one worker, a catch-up at most every CATCH_UP_GAP_SECONDS
    the column picker's counts  column_stats.COUNTS   one worker, a key counted once - again only when asked

A key asked is due; a worker takes a due key once `pacing()` seconds passed since its last run ended, runs `work()` and
keeps what it returned with when (`at`, `seconds`) - a run that raised keeps the last result and says `failed`. Every run
is on «running now» (`runtime.running`) while it runs.
"""
import logging
import threading
import time
import weakref
from datetime import datetime, timezone

from error_said import told

logger = logging.getLogger("Server")

#: Every Behind of this process - what «running now» reads.
_ALL = weakref.WeakSet()


class Behind:
    def __init__(self, name, pacing, said, workers=1, named=str):
        """`name`: its workers' thread name (`<name>-<n>` past one); `pacing()`: seconds a key rests after its run;
        `said`: the failure line's head, `%s` the key's `named(key)`."""
        self.name, self._pacing, self._said, self._workers, self._named = name, pacing, said, workers, named
        self._cond = threading.Condition()
        self._kept = {}             # key -> dict(the last result, at, seconds, began, ended, failed, work)
        self._due = {}              # key -> work, to run (again)
        self._now = {}              # key -> (work, began monotonic, began at) - running
        self._threads = []
        _ALL.add(self)

    def ask(self, key, work, again=None, wait=0.0):
        """`key` is due unless it runs now, or it has a kept run and `again(kept)` is not true. Waits up to `wait`
        seconds for a due key a worker takes at once. -> the kept run of `key`, or None (never run)."""
        with self._cond:
            kept = self._kept.get(key)
            if key not in self._now and (kept is None or (again is not None and again(kept))):
                self._due.setdefault(key, work)
            while len(self._threads) < self._workers:
                thread = threading.Thread(target=self._work, daemon=True, name=(
                    self.name if self._workers == 1 else "%s-%d" % (self.name, len(self._threads) + 1)))
                self._threads.append(thread)
                thread.start()
            self._cond.notify_all()
            if wait and key in self._due and self._paced(key, self._pacing(), time.monotonic()):
                began = (kept or {}).get("began")
                self._cond.wait_for(lambda: (self._kept.get(key) or {}).get("began") != began, wait)
            return self._kept.get(key)

    def busy(self, key):
        """Is `key` running, or due with nothing but a worker to wait for."""
        with self._cond:
            return key in self._now or (key in self._due and self._paced(key, self._pacing(), time.monotonic()))

    def again(self, which):
        """Every kept or running key `which(key)` says is due again - the one running too: what it read may be from
        before the change."""
        with self._cond:
            for key, work in ([(key, kept["work"]) for key, kept in self._kept.items()]
                              + [(key, now[0]) for key, now in self._now.items()]):
                if which(key):
                    self._due[key] = work
            self._cond.notify_all()

    def forget(self):
        """Nothing kept, nothing due (a test's start)."""
        with self._cond:
            self._kept.clear()
            self._due.clear()

    def running(self):
        """[(named key, began at, seconds so far)] of the runs now."""
        with self._cond:
            return [(self._named(key), at, time.monotonic() - began) for key, (_work, began, at) in self._now.items()]

    def _paced(self, key, pacing, now):
        kept = self._kept.get(key)
        return kept is None or now - kept["ended"] >= pacing

    def _work(self):
        while True:
            with self._cond:
                while True:
                    pacing, now = self._pacing(), time.monotonic()
                    ready = [key for key in self._due if key not in self._now and self._paced(key, pacing, now)]
                    if ready:
                        key = ready[0]
                        work = self._due.pop(key)
                        self._now[key] = (work, now, datetime.now(timezone.utc).isoformat())
                        break
                    waits = [pacing - (now - self._kept[key]["ended"]) for key in self._due
                             if key in self._kept and key not in self._now]
                    self._cond.wait(max(min(waits), 0.05) if waits else None)
            began, result, failed = time.monotonic(), None, None
            try:
                result = work()
            except Exception as exc:                                # noqa: BLE001 - one line, the next run goes on
                logger.error("%s: %s: %s", self._said % (self._named(key),), type(exc).__name__, told(exc))
                failed = {"reason": ("%s: %s" % (type(exc).__name__, told(exc).strip().split("\n")[0]))[:200],
                          "at": datetime.now(timezone.utc).isoformat()}
            with self._cond:
                kept = {k: v for k, v in (self._kept.get(key) or {}).items()
                        if k not in ("began", "ended", "failed", "work")}
                if failed is None:
                    kept = dict(result or {}, at=datetime.now(timezone.utc).isoformat(),
                                seconds=round(time.monotonic() - began, 3))
                self._kept[key] = dict(kept, began=began, ended=time.monotonic(), failed=failed, work=work)
                del self._now[key]
                self._cond.notify_all()


def running_now():
    """[(Behind name, named key, began at, seconds so far)] of every Behind of this process."""
    return [(behind.name,) + run for behind in list(_ALL) for run in behind.running()]
