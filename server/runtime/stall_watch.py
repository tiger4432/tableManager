"""The one line a freeze of this server leaves (owner 10-29 «파일 인제션하면 서버가 굳네 여전히» · «원인 파악하게
로그를 구성해봐 · 폰으로 쳐서 보내야 하니 구성 잘해», lead ㄴ):

    STALL 14s P /dashboard/summary L12 T40/40 G6 D9/11s INSERT cell_sources B3 AUTOVACUUM public.x X412s/18234 UPDATE
    pfab_metro C97 ours:66 api:4 grid:61 pg:30 AUTOANALYZE public.x other:2 IO r180w420MB/s 950iops pgIO7 ING dt_log

D: active statements / the longest one's seconds and head; B: sessions held up by another / the head of the one
holding up the most (owner 11-09 «거의 모든 stall 에 autovacuum» - an autovacuum worker named with its table); X: the
oldest open transaction's seconds / its snapshot's xmin age in transactions (what vacuum cannot clean past) and its
statement's head - «X0» none open (lead 11-09). C: the machine's CPU % and, on that one scale, this product's named
processes together («ours»), the API's own, the busiest named process (a pool child, a heartbeat's worker),
PostgreSQL's processes together with what the busiest of them runs (lead 11-10: its statement's head, or its kind -
«checkpointer» - when it runs none) and the rest; IO: the disks'
read and write MB/s and IOs a second, and sessions of this database waiting on IO (owner 11-09: a
CPU-low stall is IO, a lock or a pool start - lead).

A thread of the API process looks once a second. A freeze is a request open longer than `STALL_SECONDS`, or the event
loop not answering that long. While one lasts the readings' highest values are kept; its end writes the line, and one
more every `MID_EVERY` seconds while it goes on («+» after the seconds). The last line rides on /health.

The watch only watches (CLAUDE.md 계측): each reading is its own try and a failed one prints «?» in its cell; the
database is asked on a connection of its own with a one-second statement limit, never one of the server's pools.
"""
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

from error_said import told

logger = logging.getLogger("Server")

STALL_SECONDS = 5
MID_EVERY = 30
TICK_SECONDS = 1.0
UNREAD = "?"

OLDEST_TRANSACTION = ("SELECT extract(epoch FROM now() - xact_start), age(backend_xmin), query FROM pg_stat_activity "
                      "WHERE xact_start IS NOT NULL AND pid <> pg_backend_pid() AND datname = current_database() "
                      "ORDER BY xact_start LIMIT 1")
ACTIVE_STATEMENTS = ("SELECT count(*) OVER (), extract(epoch FROM now() - query_start), query, "
                     "count(*) FILTER (WHERE wait_event_type = 'IO') OVER () "
                     "FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid() "
                     "AND datname = current_database() ORDER BY query_start LIMIT 1")
#: What one PostgreSQL process runs - any database's, a background one's too (its kind then).
PG_DOING = "SELECT query, backend_type FROM pg_stat_activity WHERE pid = :pid"
#: A PostgreSQL process, by its image name - the C cell's «pg».
_PG_IMAGE = re.compile(r"postgres", re.I)
_NOT_NAMES = re.compile(r"'(?:[^']|'')*'|/\*.*?\*/|--[^\n]*", re.S)      # literals and comments - never on the line
_TABLE = re.compile(r'\b(?:FROM|INTO|UPDATE|VACUUM(?:\s+ANALYZE)?|ANALYZE)\s+"?([\w.]+)', re.I)


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


_SNAPSHOT_BUFFER = []


def process_times():
    """{pid: (image name, CPU seconds)} of every process, from ONE NtQuerySystemInformation call (Windows) - 14-19 ms
    for ~690 processes on the box's machine (11-09). psutil opens a process to read it; PostgreSQL's run as a service
    account it may not open, and then it takes a whole snapshot per process: 1-2 s for 52 postgres processes."""
    import ctypes
    from ctypes import wintypes

    class Name(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]

    class Entry(ctypes.Structure):       # SYSTEM_PROCESS_INFORMATION's head: user time at 40, kernel time at 48
        _fields_ = [("NextEntryOffset", wintypes.ULONG), ("NumberOfThreads", wintypes.ULONG),
                    ("Head", ctypes.c_byte * 48), ("ImageName", Name), ("BasePriority", ctypes.c_long),
                    ("UniqueProcessId", ctypes.c_void_p)]

    query = ctypes.WinDLL("ntdll").NtQuerySystemInformation
    if not _SNAPSHOT_BUFFER:                                                      # kept: the next call reuses it
        _SNAPSHOT_BUFFER.append(ctypes.create_string_buffer(4 << 20))
    while True:
        buf, needed = _SNAPSHOT_BUFFER[0], wintypes.ULONG(0)
        status = query(5, buf, len(buf), ctypes.byref(needed)) & 0xFFFFFFFF      # 5: SystemProcessInformation
        if status != 0xC0000004:                                                  # not «a bigger buffer»
            break
        _SNAPSHOT_BUFFER[0] = ctypes.create_string_buffer(max(len(buf) * 2, needed.value + (64 << 10)))
    if status:
        raise OSError("NtQuerySystemInformation status 0x%08X" % status)
    times, base, offset = {}, ctypes.addressof(buf), 0
    while True:
        entry = Entry.from_address(base + offset)
        head = bytes(entry.Head)
        name = ctypes.wstring_at(entry.ImageName.Buffer, entry.ImageName.Length // 2) if entry.ImageName.Buffer else ""
        times[entry.UniqueProcessId or 0] = (name, (int.from_bytes(head[32:40], "little")
                                                    + int.from_bytes(head[40:48], "little")) / 1e7)
        if not entry.NextEntryOffset:
            return times
        offset += entry.NextEntryOffset


class Cpu:
    """`(machine %, (name, %) of the busiest named process but the API, {"pg", "api", "ours", "other": %, "pg_top":
    (pid, %) of the busiest PostgreSQL process or None})` since the last call - every share of the whole machine, one
    scale; «ours» is the named processes together; «other» is the machine less the rest, never under 0.

    One process snapshot (`process_times`, Windows) reads them all: every process's CPU time since the last snapshot
    together is the machine (98-99 % of cores x seconds on the box's machine, 11-09 - the rest is processes that ended
    between), pid 0's is its idle. Elsewhere, or once the snapshot failed (said once), each named pid is read through
    psutil and «pg» is «?». The first call, and a process first seen, give their share from the next call on."""

    def __init__(self, snapshot=None):
        import psutil
        self.psutil, self.seen, self.cores = psutil, {}, psutil.cpu_count() or 1
        self.snapshot = snapshot if snapshot is not None else process_times if os.name == "nt" else None
        self.held = None
        psutil.cpu_percent(None)

    def __call__(self, names):
        if self.snapshot is not None:
            try:
                return self._from_snapshot(names)
            except Exception as exc:                   # the C cell goes on from psutil, pg says «?»
                logger.warning("[Stall] the process snapshot failed: %s - the C cell reads each named process, "
                               "pg says ?", told(exc))
                self.snapshot = None
        return self._said(self.psutil.cpu_percent(None), names, self._psutil_shares(names), UNREAD)

    def _from_snapshot(self, names):
        times = self.snapshot()
        held, self.held = self.held, times
        spent = {pid: max(seconds - held[pid][1], 0.0) for pid, (image, seconds) in times.items()
                 if held and pid in held and held[pid][0] == image}
        whole = sum(spent.values())
        if not whole:
            return self.psutil.cpu_percent(None), None, {"pg": None, "api": None, "ours": None, "other": None,
                                                         "pg_top": None}
        share = {pid: 100.0 * seconds / whole for pid, seconds in spent.items()}
        pgs = {pid: s for pid, s in share.items() if pid and _PG_IMAGE.match(times[pid][0])}
        said = self._said(100.0 - share.get(0, 0.0), names, {pid: share[pid] for pid in names if pid in share},
                          sum(pgs.values()))
        said[2]["pg_top"] = max(pgs.items(), key=lambda pid_share: pid_share[1]) if pgs else None
        return said

    def _psutil_shares(self, names):
        shares = {}
        for pid, name in names.items():
            try:
                held = self.seen.get(pid)
                if held is None or held[0] != name:
                    self.seen[pid] = (name, self.psutil.Process(pid))
                    self.seen[pid][1].cpu_percent(None)
                    continue
                shares[pid] = held[1].cpu_percent(None) / self.cores
            except self.psutil.Error:                  # a worker's beat file outlives its process
                self.seen.pop(pid, None)
        return shares

    def _said(self, machine, names, shares, pg):
        top = None
        for pid, share in shares.items():
            if pid != os.getpid() and (top is None or share > top[1]):
                top = (names[pid], share)
        ours = sum(shares.values())
        counted = ours + (0.0 if pg == UNREAD else pg)
        return machine, top, {"pg": pg, "api": shares.get(os.getpid()), "ours": ours,
                              "other": max(machine - counted, 0.0), "pg_top": None}


class Disk:
    """`(read MB/s, write MB/s, IOs a second)` of the machine's disks since the last call - None on the first. Not the
    ms an IO took: the disks' time counters stood still on the box's machine (11-09: 0 ms over 97 IOs, 31,731 ms over
    77 M reads in all) - the next landing reads Windows' own average (lead ㄷ); a busy % is Linux-only in psutil."""

    def __init__(self):
        import psutil
        self.psutil, self.held = psutil, None

    def __call__(self):
        clock, now = time.monotonic(), self.psutil.disk_io_counters()
        if now is None:
            raise OSError("no disk counters on this machine")
        held, self.held = self.held, (clock, now)
        if held is None or clock <= held[0]:
            return None
        span, was = clock - held[0], held[1]
        return ((now.read_bytes - was.read_bytes) / span / 1e6, (now.write_bytes - was.write_bytes) / span / 1e6,
                (now.read_count - was.read_count + now.write_count - was.write_count) / span)


_engine = []


def _kept():
    """The watch's one kept connection of its own (a new one each reading was 100 ms on the box, 10-29); None off
    PostgreSQL."""
    from sqlalchemy import create_engine
    if not _engine:
        from database.database import SQLALCHEMY_DATABASE_URL
        if not SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
            return None
        _engine.append(create_engine(SQLALCHEMY_DATABASE_URL, pool_size=1, max_overflow=0, pool_timeout=1,
                                     pool_pre_ping=True, connect_args={
                                         "connect_timeout": 2, "options": "-c statement_timeout=1000"}))
    return _engine[0]


def active_statements():
    """(active statements but this one, the longest one's seconds) of this database - on its own connection."""
    from sqlalchemy import text
    engine = _kept()
    if engine is None:
        return None
    with engine.connect() as conn:
        row = conn.execute(text(ACTIVE_STATEMENTS)).first()
    return (0, 0.0, None, 0) if row is None else (int(row[0]), float(row[1] or 0), statement_head(row[2]),
                                                   int(row[3] or 0))


def blocked():
    """(sessions of this database another one holds up, the head of the one holding up the most - an autovacuum worker
    too) - `db_waits.backend_waits` on the watch's own connection (owner 11-09: almost every stall had an autovacuum).
    (0, None) when none is held up."""
    import db_waits
    engine = _kept()
    if engine is None:
        return None
    with engine.connect() as conn:
        rows = db_waits.backend_waits(conn.connection.dbapi_connection, chars=200)
    held, holders = set(), {}
    for row in rows:
        if row["blocker"] is not None:
            held.add(row["pid"])
            count, query = holders.get(row["blocker"]["pid"], (0, row["blocker"]["query"]))
            holders[row["blocker"]["pid"]] = (count + 1, query)
    if not held:
        return 0, None
    return len(held), statement_head(max(holders.values(), key=lambda held_up: held_up[0])[1])


def oldest_transaction():
    """(seconds, xmin age or None, head) of this database's oldest open transaction but this one, None when none is
    open - on the watch's own connection."""
    from sqlalchemy import text
    engine = _kept()
    if engine is None:
        return None
    with engine.connect() as conn:
        row = conn.execute(text(OLDEST_TRANSACTION)).first()
    return None if row is None else (float(row[0] or 0), None if row[1] is None else int(row[1]), statement_head(row[2]))


def pg_doing(pid):
    """What PostgreSQL process `pid` runs: its statement's head, or its kind when it has none («checkpointer») - on
    the watch's own connection; None when the process is not in pg_stat_activity (the postmaster)."""
    from sqlalchemy import text
    engine = _kept()
    if engine is None:
        return None
    with engine.connect() as conn:
        row = conn.execute(text(PG_DOING), {"pid": pid}).first()
    if row is None:
        return None
    return statement_head(row[0]) if (row[0] or "").strip() else (row[1] or "").replace(" ", "-") or None


def statement_head(query):
    """«INSERT cell_sources» - a statement's first word and the first name after FROM / INTO / UPDATE at bracket depth
    0, nothing else (owner 11-06 ㄱ: which statement the D seconds are). An autovacuum worker: «AUTOVACUUM»,
    «AUTOVACUUM+ANALYZE» or «AUTOANALYZE», «-WRAP» when it prevents wraparound, and its table. Literals and comments are cut first, and a text
    cut short inside a literal ends at its quote, so no value rides the line. The word alone without a name (a name
    only inside brackets too); None without a word."""
    kept = _NOT_NAMES.sub(" ", query or "").split("'", 1)[0]
    word = re.search(r"[A-Za-z]+", kept)
    if word is None:
        return None
    depth, outer = 0, []                    # the name is read at bracket depth 0: «extract(epoch FROM x)» is no table
    for ch in kept:
        if depth == 0:
            outer.append(ch)                # a bracket opened stays - «FROM (SELECT ...) s» names nothing
        depth += (ch == "(") - (ch == ")")
    table = _TABLE.search("".join(outer))
    head = word.group(0).upper()
    if head == "AUTOVACUUM":                # what the worker does (lead 11-09): analyze mixed in; wraparound - it yields to no one
        does = re.search(r":\s*(VACUUM(?:\s+ANALYZE)?|ANALYZE)\b", kept, re.I)
        does = " ".join(does.group(1).upper().split()) if does else "VACUUM"
        head = {"VACUUM": "AUTOVACUUM", "VACUUM ANALYZE": "AUTOVACUUM+ANALYZE", "ANALYZE": "AUTOANALYZE"}[does]
        if "to prevent wraparound" in kept.lower():
            head += "-WRAP"
    return head + (" " + table.group(1) if table else "")


def workers():
    """`({pid: name}, table)` - this process as «api», every worker heartbeat's pid by its name, this process's pool
    children by their pool's (owner 11-06 ㄱ: a grid page's body runs in one), and the table an open claim of theirs
    names (the watcher's file, `note_work(table=)`)."""
    from runtime import process_pool
    from utils import heartbeat
    names, table = {os.getpid(): "api"}, None
    for pool in process_pool.POOLS:
        for pid in [worker[0].pid for worker in list(pool.idle)] + list(pool.busy):
            if pid:
                names[pid] = pool.name
    for name, entry in heartbeat.read_all().items():
        if entry.get("pid"):
            names[int(entry["pid"])] = name
        table = ((entry.get("work") or {}).get("facts") or {}).get("table") or table
    return names, table


class Watch:
    """One freeze at a time: `tick(now)` once a second; readers are the cells' sources (tests hand their own)."""

    def __init__(self, open_requests, loop_lag, threads, grid_waiting, statements, cpu, named, blocked, oldest, disk,
                 say=None, pg_doing=None):
        self.open_requests, self.loop_lag, self.threads, self.grid_waiting = open_requests, loop_lag, threads, grid_waiting
        self.statements, self.cpu, self.named, self.blocked, self.oldest = statements, cpu, named, blocked, oldest
        self.disk, self.pg_doing = disk, pg_doing
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
            f = self.freeze = {"start": now - longest, "said": now, "L": 0.0, "T": None, "G": 0, "D": None, "B": None,
                               "X": None, "C": None, "top": None, "ING": None, "open": 0.0, "P": None,
                               "pg": None, "api": None, "ours": None, "other": None, "IO": None, "pgIO": None,
                               "pg_top": 0.0, "pg_head": None}
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
            held = f["D"] if f["D"] not in (None, UNREAD) else (0, 0.0, None)
            f["D"] = (max(held[0], statements[0]), max(held[1], statements[1]),
                      statements[2] if statements[1] >= held[1] else held[2])      # the longest one's head
            f["pgIO"] = _most(f["pgIO"], statements[3])
        elif f["D"] is None:
            f["D"] = f["pgIO"] = UNREAD
        held_up = self._read("B", self.blocked)
        if held_up not in (None, UNREAD):
            if f["B"] in (None, UNREAD) or held_up[0] >= f["B"][0]:
                f["B"] = held_up                    # the most sessions held up in this freeze, and who held them
        elif f["B"] is None:
            f["B"] = UNREAD
        oldest = self._read("X", self.oldest)
        if oldest != UNREAD:
            oldest = oldest or (0.0, None, None)
            if f["X"] in (None, UNREAD) or oldest[0] >= f["X"][0]:
                f["X"] = oldest                     # the oldest open transaction seen in this freeze
        elif f["X"] is None:
            f["X"] = UNREAD
        named = self._read("ING", self.named)
        pids = {}
        if named != UNREAD:
            pids, table = named
            f["ING"] = table or f["ING"]
        elif f["top"] is None:
            f["top"] = UNREAD
        cpu = self._read("C", self.cpu, pids)
        if cpu != UNREAD:
            f["C"] = max(f["C"] if f["C"] not in (None, UNREAD) else 0.0, cpu[0])
            if cpu[1] is not None and (f["top"] in (None, UNREAD) or cpu[1][1] > f["top"][1]):
                f["top"] = cpu[1]
            for part in ("pg", "api", "ours", "other"):
                f[part] = _most(f[part], cpu[2].get(part))
            busiest = cpu[2].get("pg_top")
            if busiest and self.pg_doing and busiest[1] > f["pg_top"]:
                f["pg_top"] = busiest[1]            # what the busiest PostgreSQL process ran at its busiest tick
                f["pg_head"] = self._read("pg head", self.pg_doing, busiest[0])
        elif f["C"] is None:
            f["C"] = UNREAD
        disk = self._read("IO", self.disk)
        if disk not in (None, UNREAD):
            held = f["IO"] if f["IO"] not in (None, UNREAD) else (0.0, 0.0, 0.0)
            f["IO"] = tuple(max(a, b) for a, b in zip(held, disk))
        elif f["IO"] is None and disk == UNREAD:
            f["IO"] = UNREAD
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
                 "D%s" % (UNREAD if f["D"] in (None, UNREAD) else "%d/%ds%s" % (
                     f["D"][0], round(f["D"][1]), " " + f["D"][2] if f["D"][2] else "")),
                 "B%s" % (UNREAD if f["B"] in (None, UNREAD) else "%d%s" % (
                     f["B"][0], " " + f["B"][1] if f["B"][1] else "")),
                 "X%s" % (UNREAD if f["X"] in (None, UNREAD) else "0" if not f["X"][0] else "%ds%s%s" % (
                     round(f["X"][0]), "" if f["X"][1] is None else "/%d" % f["X"][1],
                     " " + f["X"][2] if f["X"][2] else "")),
                 "C%s" % _int(f["C"])]
        cells += ["%s:%s" % (part, _int(f[part])) for part in ("ours", "api") if f[part] is not None]
        if f["top"] == UNREAD:
            cells.append(UNREAD)
        elif f["top"] is not None:
            cells.append("%s:%d" % (f["top"][0], round(f["top"][1])))
        if f["pg"] is not None:
            cells.append("pg:%s%s" % (_int(f["pg"]), " " + f["pg_head"] if f["pg_head"] else ""))
        if f["other"] is not None:
            cells.append("other:%s" % _int(f["other"]))
        if f["IO"] is not None:
            cells.append("IO" + (UNREAD if f["IO"] == UNREAD else " r%dw%dMB/s %diops" % tuple(round(v) for v in f["IO"])))
        if f["pgIO"] is not None:
            cells.append("pgIO%s" % _int(f["pgIO"]))
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
                        lambda: process_pool.GRID.waiting[0], active_statements, cpu, workers, blocked,
                        oldest_transaction, Disk(), pg_doing=pg_doing))

    def run():
        while True:
            began = time.monotonic()
            try:
                _watch[0].tick(began)
            except Exception as exc:                    # never the server's: say it, keep watching
                logger.warning("[Stall] a tick failed - this freeze is not watched until the next: %s", told(exc))
            time.sleep(max(TICK_SECONDS - (time.monotonic() - began), 0.05))

    threading.Thread(target=run, name="stall-watch", daemon=True).start()
