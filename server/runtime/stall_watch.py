"""The one line a freeze of this server leaves (owner 10-29 «파일 인제션하면 서버가 굳네 여전히» · «원인 파악하게
로그를 구성해봐 · 폰으로 쳐서 보내야 하니 구성 잘해», lead ㄴ):

    STALL 14s P /dashboard/summary L12 T40/40 G6 D9/11s C97 slot2:61 ING dt_log

A thread of the API process looks once a second. A freeze is a request open longer than `STALL_SECONDS`, or the event
loop not answering that long. While one lasts the readings' highest values are kept; its end writes the line, and one
more every `MID_EVERY` seconds while it goes on («+» after the seconds). The last line rides on /health.

The watch only watches (CLAUDE.md 계측): each reading is its own try and a failed one prints «?» in its cell; the
database is asked on a connection of its own with a one-second statement limit, never one of the server's pools.
"""
import logging
import os
import threading
import time
from datetime import datetime, timezone

from error_said import told

logger = logging.getLogger("Server")

STALL_SECONDS = 5
MID_EVERY = 30
TICK_SECONDS = 1.0
UNREAD = "?"

ACTIVE_STATEMENTS = ("SELECT count(*), coalesce(max(extract(epoch FROM now() - query_start)), 0) "
                     "FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid() "
                     "AND datname = current_database()")


class LoopProbe:
    """Seconds the event loop has left a stamp unanswered - 0 when it answered the last one."""

    def __init__(self, loop):
        self.loop, self.sent = loop, None

    def __call__(self, now):
        if self.sent is None:
            self.sent = now
            self.loop.call_soon_threadsafe(self._back)
            return 0.0
        return now - self.sent

    def _back(self):
        self.sent = None


class Cpu:
    """`(machine %, (name, %) of the busiest named process)` since the last call - a process's share is of the whole
    machine, so the two read on one scale. A process first seen gives its share from the next call on."""

    def __init__(self):
        import psutil
        self.psutil, self.seen, self.cores = psutil, {}, psutil.cpu_count() or 1
        psutil.cpu_percent(None)

    def __call__(self, names):
        top = None
        for pid, name in names.items():
            try:
                held = self.seen.get(pid)
                if held is None or held[0] != name:
                    self.seen[pid] = (name, self.psutil.Process(pid))
                    self.seen[pid][1].cpu_percent(None)
                    continue
                share = held[1].cpu_percent(None) / self.cores
            except self.psutil.Error:                  # a worker's beat file outlives its process
                self.seen.pop(pid, None)
                continue
            if top is None or share > top[1]:
                top = (name, share)
        return self.psutil.cpu_percent(None), top


_engine = []


def active_statements():
    """(active statements but this one, the longest one's seconds) of this database - on its own connection."""
    from sqlalchemy import create_engine, text
    if not _engine:
        from database.database import SQLALCHEMY_DATABASE_URL
        if not SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
            return None
        # one kept connection of its own (a new one each reading was 100 ms on the box, 10-29)
        _engine.append(create_engine(SQLALCHEMY_DATABASE_URL, pool_size=1, max_overflow=0, pool_timeout=1,
                                     pool_pre_ping=True, connect_args={
                                         "connect_timeout": 2, "options": "-c statement_timeout=1000"}))
    with _engine[0].connect() as conn:
        count, longest = conn.execute(text(ACTIVE_STATEMENTS)).one()
    return int(count), float(longest or 0)


def workers():
    """`({pid: name}, table)` - this process as «api», every worker heartbeat's pid by its name, and the table an
    open claim of theirs names (the watcher's file, `note_work(table=)`)."""
    from utils import heartbeat
    names, table = {os.getpid(): "api"}, None
    for name, entry in heartbeat.read_all().items():
        if entry.get("pid"):
            names[int(entry["pid"])] = name
        table = ((entry.get("work") or {}).get("facts") or {}).get("table") or table
    return names, table


class Watch:
    """One freeze at a time: `tick(now)` once a second; readers are the cells' sources (tests hand their own)."""

    def __init__(self, open_requests, loop_lag, threads, grid_waiting, statements, cpu, named, say=None):
        self.open_requests, self.loop_lag, self.threads, self.grid_waiting = open_requests, loop_lag, threads, grid_waiting
        self.statements, self.cpu, self.named = statements, cpu, named
        self.say = say or logger.warning
        self.freeze, self.last, self._broke = None, None, set()

    def _read(self, cell, reader, *args):
        try:
            return reader(*args)
        except Exception as exc:                        # the watch alone goes quiet - its cell says «?»
            if cell not in self._broke:
                self._broke.add(cell)
                logger.warning("[Stall] the %s reading failed: %s - its cell says ?", cell, told(exc))
            return UNREAD

    def tick(self, now):
        opened = self._read("P", self.open_requests)
        open_s, path = (UNREAD, None) if opened == UNREAD else opened
        lag = self._read("L", self.loop_lag, now)
        longest = max(v for v in (open_s, lag, 0.0) if v != UNREAD)
        if longest <= STALL_SECONDS:
            if self.freeze is not None:
                self._line(now, going=False)
                self.freeze = None
            return
        f = self.freeze
        if f is None:
            f = self.freeze = {"start": now - longest, "said": now, "L": 0.0, "T": None, "G": 0, "D": None,
                               "C": None, "top": None, "ING": None, "open": 0.0, "P": None}
        if open_s != UNREAD and path and open_s >= f["open"]:
            f["open"], f["P"] = open_s, path        # the path of the request open longest in this freeze
        f["L"] = _most(f["L"], lag)
        threads = self._read("T", self.threads)
        if threads != UNREAD and (f["T"] in (None, UNREAD) or threads[0] > f["T"][0]):
            f["T"] = threads
        elif f["T"] is None:
            f["T"] = UNREAD
        f["G"] = _most(f["G"], self._read("G", self.grid_waiting))
        statements = self._read("D", self.statements)
        if statements not in (None, UNREAD):
            held = f["D"] if f["D"] not in (None, UNREAD) else (0, 0.0)
            f["D"] = (max(held[0], statements[0]), max(held[1], statements[1]))
        elif f["D"] is None:
            f["D"] = UNREAD
        named = self._read("ING", self.named)
        pids = {}
        if named != UNREAD:
            pids, table = named
            f["ING"] = table or f["ING"]
        cpu = self._read("C", self.cpu, pids)
        if cpu != UNREAD:
            f["C"] = max(f["C"] if f["C"] not in (None, UNREAD) else 0.0, cpu[0])
            if cpu[1] is not None and (f["top"] is None or cpu[1][1] > f["top"][1]):
                f["top"] = cpu[1]
        elif f["C"] is None:
            f["C"] = UNREAD
        if now - f["said"] >= MID_EVERY:
            self._line(now, going=True)
            f["said"] = now

    def _line(self, now, going):
        f = self.freeze
        cells = ["STALL", "%ds%s" % (round(now - f["start"]), "+" if going else "")]
        if f["P"]:
            cells.append("P %s" % f["P"])
        cells += ["L%s" % _int(f["L"]),
                 "T%s" % (UNREAD if f["T"] in (None, UNREAD) else "%d/%d" % f["T"]),
                 "G%s" % _int(f["G"]),
                 "D%s" % (UNREAD if f["D"] in (None, UNREAD) else "%d/%ds" % (f["D"][0], round(f["D"][1]))),
                 "C%s" % _int(f["C"])]
        if f["top"] is not None:
            cells.append("%s:%d" % (f["top"][0], round(f["top"][1])))
        if f["ING"]:
            cells.append("ING %s" % f["ING"])
        line = " ".join(cells)
        self.last = {"line": line, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.say(line)


def _most(held, value):
    if value in (None, UNREAD):
        return held if held is not None else value
    if held in (None, UNREAD):
        return value
    return max(held, value)


def _int(value):
    return UNREAD if value in (None, UNREAD) else "%d" % round(value)


_watch = []


def last():
    """The last STALL line and when it was said - /health carries it; None before the first."""
    return _watch[0].last if _watch else None


def start(loop, limiter):
    """Watch this process from a daemon thread - the API's start, after its loop runs (`limiter`: anyio's default
    thread limiter, which is only reachable from inside that loop)."""
    from runtime import process_pool, request_timing
    if _watch:
        return
    cpu = Cpu()
    _watch.append(Watch(request_timing.oldest_open, LoopProbe(loop),
                        lambda: (limiter.borrowed_tokens, limiter.total_tokens),
                        lambda: process_pool.GRID.waiting[0], active_statements, cpu, workers))

    def run():
        while True:
            began = time.monotonic()
            try:
                _watch[0].tick(began)
            except Exception as exc:                    # never the server's: say it, keep watching
                logger.warning("[Stall] a tick failed - this freeze is not watched until the next: %s", told(exc))
            time.sleep(max(TICK_SECONDS - (time.monotonic() - began), 0.05))

    threading.Thread(target=run, name="stall-watch", daemon=True).start()
