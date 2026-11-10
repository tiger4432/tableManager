# -*- coding: utf-8 -*-
"""Owner 10-29 «파일 인제션하면 서버가 굳네 여전히» · «원인 파악하게 로그를 구성해봐 · 폰으로 쳐서 보내야 하니 구성
잘해» (lead ㄴ): a freeze of the API process leaves ONE line - `STALL 14s L12 T40/40 G6 D9/11s C97 slot2:61 ING
dt_log` - when it ends, one more every 30 s while it goes on, none without one; a reading that fails says «?» in its
own cell only. The cells' sources: the open-request table, the grid pool's waiting count, /health's stall."""
import os
import re
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from runtime import process_pool, request_timing, stall_watch  # noqa: E402


#: The C cell's parts a reading gives by default - PostgreSQL's processes, the API, the rest.
PARTS = {"pg": 1.0, "api": 2.0, "other": 2.0}


class Readings:
    """What the cells read, set per tick by the test."""

    def __init__(self):
        self.open, self.path, self.lag, self.threads, self.grid = 0.0, None, 0.0, (3, 40), 0
        self.key, self.pid, self.doing = 1, None, {}
        self.statements, self.pids, self.table = (1, 0.1, None, 0), {1: "api"}, None
        self.cpu = (5.0, None, PARTS)
        self.blocked = (0, None)
        self.oldest = None
        self.disk = (1.0, 2.0, 3.0)

    def watch(self, said):
        def fail_or(value):
            if isinstance(value, Exception):
                raise value
            return value
        return stall_watch.Watch(lambda: fail_or((self.open, self.path, self.key, self.pid)),
                                 lambda now: fail_or(self.lag),
                                 lambda: fail_or(self.threads), lambda: fail_or(self.grid),
                                 lambda: fail_or(self.statements), lambda pids: fail_or(self.cpu),
                                 lambda: fail_or((self.pids, self.table)), lambda: fail_or(self.blocked),
                                 lambda: fail_or(self.oldest), lambda: fail_or(self.disk), say=said.append,
                                 pg_doing=lambda pid: fail_or(self.doing[pid]))


def test_no_freeze_says_nothing():
    r, said = Readings(), []
    w = r.watch(said)
    for second in range(120):
        r.open = 4.9 if second % 7 == 0 else 0.3
        w.tick(float(second))
    assert said == [] and w.last is None


def test_a_freeze_ends_in_one_line_of_its_highest_readings():
    r, said = Readings(), []
    w = r.watch(said)
    w.tick(100.0)
    r.open, r.path, r.threads, r.grid, r.statements = 7.0, "/dashboard/summary", (40, 40), 6, (9, 11.2, None, 4)
    r.cpu, r.table = (97.0, ("slot2", 61.3), {"pg": 30.0, "api": 4.0, "other": 2.0}), "dt_log"
    w.tick(101.0)
    r.open, r.lag, r.grid = 9.0, 12.4, 2
    r.cpu, r.disk = (40.0, ("watcher", 12.0), {"pg": 20.0, "api": 1.0, "other": 7.0}), (180.4, 420.0, 950.0)
    w.tick(103.0)
    assert said == []
    r.open, r.lag = 0.0, 0.0
    w.tick(105.0)
    assert said == ["STALL 11s P /dashboard/summary L12 T40/40 G6 D9/11s B0 X0 C97 api:4 slot2:61 pg:30 other:7 "
                    "IO r180w420MB/s 950iops pgIO4 ING dt_log"]
    assert w.last["line"] == said[0] and w.last["at"]
    w.tick(106.0)
    assert len(said) == 1, "one freeze, one line"


def test_a_long_freeze_says_so_every_30_s_and_once_at_its_end():
    r, said = Readings(), []
    w = r.watch(said)
    r.lag = 6.0
    for second in range(0, 70):
        r.lag = 6.0 + second
        w.tick(float(second))
    r.lag = 0.0
    w.tick(70.0)
    assert [line.split()[1] for line in said] == ["36s+", "66s+", "76s"], said   # it began 6 s before the first tick
    assert all(line.startswith("STALL ") for line in said)


def test_a_failed_reading_says_question_mark_in_its_cell_only(caplog):
    r, said = Readings(), []
    w = r.watch(said)
    r.open, r.statements, r.table = 8.0, RuntimeError("no database"), "dt_log"
    w.tick(1.0)
    w.tick(2.0)
    r.open = 0.0
    w.tick(3.0)
    assert said == ["STALL 10s L0 T3/40 G0 D? B0 X0 C5 api:2 pg:1 other:2 IO r1w2MB/s 3iops pgIO? ING dt_log"]
    assert sum("the D reading failed" in m for m in caplog.messages) == 1, "said once, not every tick"


def test_no_open_claim_leaves_the_ing_cell_out():
    r, said = Readings(), []
    w = r.watch(said)
    r.open = 6.0
    w.tick(1.0)
    r.open = 0.0
    w.tick(2.0)
    assert said == ["STALL 7s L0 T3/40 G0 D1/0s B0 X0 C5 api:2 pg:1 other:2 IO r1w2MB/s 3iops pgIO0"]


def test_a_beat_file_of_a_gone_process_does_not_blank_the_cpu_cell():
    """Measured: a worker's heartbeat file outlived its process and the whole C cell read «?»."""
    import psutil
    gone = max(psutil.pids()) + 100_000
    for cpu in (stall_watch.Cpu(), stall_watch.Cpu(snapshot=_failing)):
        names = {os.getpid(): "api", gone: "slot9"}
        cpu(names)
        sum(i * i for i in range(200_000))
        machine, top, parts = cpu(names)
        assert 0.0 <= machine <= 100.0 and top is None and parts["api"] is not None


def test_the_cpu_cell_never_walks_the_process_table_through_psutil(monkeypatch):
    """C 10-29: walking this PC's 541 processes with psutil took 3.5 s - a watch that did it would grow the freeze it
    reads. The snapshot reads every process in one system call (13-19 ms for ~700 on the box's machine, 11-09); the
    fallback asks Process(pid) of the heartbeat pids and the API only. Neither walks psutil's process table."""
    import psutil

    def walked(*_a, **_k):
        raise AssertionError("the whole process table was walked")
    monkeypatch.setattr(psutil, "process_iter", walked)
    monkeypatch.setattr(psutil, "pids", walked)
    for cpu in (stall_watch.Cpu(), stall_watch.Cpu(snapshot=_failing)):
        cpu({os.getpid(): "api"})
        machine, top, parts = cpu({os.getpid(): "api"})
        assert top is None and parts["api"] is not None and 0.0 <= machine <= 100.0


def _failing():
    raise OSError("NtQuerySystemInformation status 0xC0000022")


class Snapshots:
    """`process_times` read from a list of tables, one a call - {pid: (image, CPU seconds)}."""

    def __init__(self, *tables):
        self.tables = list(tables)

    def __call__(self):
        return self.tables.pop(0)


def test_one_snapshot_reads_the_machine_postgres_the_api_the_busiest_and_the_rest_on_one_scale():
    """Lead 11-09 «C83 인데 가장 바쁜 이름 있는 프로세스는 chain.slot.1 6 %»: the CPU was the unnamed processes'. Every
    share is of all processes' CPU time between two snapshots; pid 0 is the idle; «other» is what is left."""
    me = os.getpid()
    # 10 s of CPU between the two: idle 4, the API 0.5, a slot 1, postgres 2 + 1, explorer 1.5; pid 11 started between
    # (no share yet), pid 12 is a new process on a reused pid (its image changed - no share)
    cpu = stall_watch.Cpu(snapshot=Snapshots(
        {0: ("", 100.0), me: ("python.exe", 10.0), 7: ("python.exe", 5.0), 8: ("postgres.exe", 1.0),
         9: ("postgres.exe", 2.0), 10: ("explorer.exe", 3.0), 12: ("postgres.exe", 0.5)},
        {0: ("", 104.0), me: ("python.exe", 10.5), 7: ("python.exe", 6.0), 8: ("postgres.exe", 3.0),
         9: ("postgres.exe", 3.0), 10: ("explorer.exe", 4.5), 11: ("postgres.exe", 9.0), 12: ("chrome.exe", 1.0)}))
    names = {me: "api", 7: "chain.slot.1"}
    first = cpu(names)
    assert first[1:] == (None, {"pg": None, "api": None, "ours": None, "other": None, "pg_top": None}), \
        "the first snapshot has none to compare"
    machine, top, parts = cpu(names)
    assert machine == pytest.approx(60.0) and top == ("chain.slot.1", pytest.approx(10.0))
    assert parts == {"pg": pytest.approx(30.0), "api": pytest.approx(5.0), "ours": pytest.approx(15.0),
                     "other": pytest.approx(15.0), "pg_top": (8, pytest.approx(20.0))}
    assert parts["ours"] + parts["pg"] + parts["other"] == pytest.approx(machine), "the three are the machine"


def test_the_line_says_ours_and_what_the_busiest_postgres_process_ran_at_its_busiest():
    """Lead 11-10 (a)(b): «C83 ours:23 api:17 chain.slot.1:6 pg:61 AUTOANALYZE public.database_outbox other:12» - the
    product's processes together, and pg's CPU named by what its busiest process ran (its kind when no statement)."""
    r, said, asked = Readings(), [], []
    doing = {8: ("AUTOANALYZE public.database_outbox", 3.0, "cpu"), 9: ("checkpointer", 0.0, "cpu")}

    def pg_doing(pid):
        asked.append(pid)
        return doing[pid]
    w = stall_watch.Watch(lambda: (r.open, r.path, 1, None), lambda now: 0.0, lambda: (3, 40), lambda: 0,
                          lambda: (1, 0.1, None, 0), lambda pids: r.cpu, lambda: ({1: "api"}, None),
                          lambda: (0, None), lambda: None, lambda: (1.0, 2.0, 3.0), say=said.append, pg_doing=pg_doing)
    r.open = 8.0
    r.cpu = (83.0, ("chain.slot.1", 6.0), {"pg": 61.0, "api": 17.0, "ours": 23.0, "other": 12.0, "pg_top": (8, 40.0)})
    w.tick(1.0)
    r.cpu = (70.0, ("chain.slot.1", 3.0), {"pg": 50.0, "api": 10.0, "ours": 13.0, "other": 7.0, "pg_top": (9, 20.0)})
    w.tick(2.0)
    r.open = 0.0
    w.tick(3.0)
    assert said == ["STALL 10s L0 T3/40 G0 D1/0s B0 X0 C83 ours:23 api:17 chain.slot.1:6 "
                    "pg:61 AUTOANALYZE public.database_outbox other:12 IO r1w2MB/s 3iops pgIO0"]
    assert asked == [8], "asked only when a busier PostgreSQL process is seen"


def test_a_failed_pg_head_says_question_mark_after_pg_only(caplog):
    r, said = Readings(), []

    def pg_doing(pid):
        raise RuntimeError("no database")
    w = stall_watch.Watch(lambda: (r.open, None, 1, None), lambda now: 0.0, lambda: (3, 40), lambda: 0,
                          lambda: (1, 0.1, None, 0), lambda pids: r.cpu, lambda: ({1: "api"}, None),
                          lambda: (0, None), lambda: None, lambda: (1.0, 2.0, 3.0), say=said.append, pg_doing=pg_doing)
    r.open, r.cpu = 8.0, (50.0, None, {"pg": 30.0, "api": 5.0, "ours": 5.0, "other": 15.0, "pg_top": (8, 30.0)})
    w.tick(1.0)
    r.open = 0.0
    w.tick(2.0)
    assert said == ["STALL 9s L0 T3/40 G0 D1/0s B0 X0 C50 ours:5 api:5 pg:30 ? other:15 IO r1w2MB/s 3iops pgIO0"]
    assert sum("the pg head reading failed" in m for m in caplog.messages) == 1


def test_a_failed_snapshot_falls_back_to_the_named_pids_and_pg_says_question_mark_said_once(caplog):
    cpu = stall_watch.Cpu(snapshot=_failing)
    names = {os.getpid(): "api"}
    cpu(names)
    sum(i * i for i in range(200_000))
    machine, top, parts = cpu(names)
    assert parts["pg"] == stall_watch.UNREAD and parts["api"] is not None and 0.0 <= machine <= 100.0
    assert sum("the process snapshot failed" in m for m in caplog.messages) == 1, "said once, then psutil"


def test_other_is_the_machine_less_the_rest_never_under_0():
    """psutil reads the machine and each process a moment apart - their sum can pass the machine's."""
    cpu = stall_watch.Cpu(snapshot=_failing)
    me = os.getpid()
    assert cpu._said(10.0, {me: "api", 7: "slot"}, {me: 8.0, 7: 6.0}, stall_watch.UNREAD)[2]["other"] == 0.0
    assert cpu._said(50.0, {me: "api", 7: "slot"}, {me: 8.0, 7: 6.0}, 30.0)[2]["other"] == pytest.approx(6.0)


def test_the_line_says_pg_question_mark_and_io_question_mark_in_their_cells_only():
    r, said = Readings(), []
    w = r.watch(said)
    r.open, r.cpu, r.disk = 8.0, (5.0, None, {"pg": stall_watch.UNREAD, "api": 2.0, "other": 3.0}), OSError("no disk")
    w.tick(1.0)
    r.open = 0.0
    w.tick(2.0)
    assert said == ["STALL 9s L0 T3/40 G0 D1/0s B0 X0 C5 api:2 pg:? other:3 IO? pgIO0"]


def test_the_disks_say_megabytes_and_ios_a_second(monkeypatch):
    """Owner 11-09 «C30 대에 메인 그리드 읽기 stall»: a CPU-low stall is IO, a lock or a pool start - IO had no cell. The
    disks' time counters are not read (they stood still on the box's machine); no IO between two reads says 0."""
    import collections
    import psutil
    Io = collections.namedtuple("Io", "read_count write_count read_bytes write_bytes read_time write_time")
    counters = [Io(100, 200, 0, 0, 1000, 2000), Io(140, 260, 180_000_000, 420_000_000, 1600, 3600),
                Io(140, 260, 180_000_000, 420_000_000, 1600, 3600)]
    clock = [10.0, 12.0, 13.0, 14.0]
    monkeypatch.setattr(psutil, "disk_io_counters", lambda: counters.pop(0))
    disk = stall_watch.Disk()
    monkeypatch.setattr(stall_watch.time, "monotonic", lambda: clock.pop(0))
    assert disk() is None, "the first read has none to compare"
    assert disk() == (pytest.approx(90.0), pytest.approx(210.0), pytest.approx(50.0))      # 40 reads + 60 writes in 2 s
    assert disk() == (0.0, 0.0, 0.0)
    monkeypatch.setattr(psutil, "disk_io_counters", lambda: None)
    with pytest.raises(OSError):
        disk()


def test_the_loop_probe_reads_how_long_a_blocked_loop_has_not_answered():
    """L - none of the box's four freezes held the loop (their routes are sync), so a real loop is held here."""
    import asyncio
    loop = asyncio.new_event_loop()
    runner = threading.Thread(target=loop.run_forever, daemon=True)
    runner.start()
    probe = stall_watch.LoopProbe(loop)
    assert probe(time.monotonic()) == 0.0
    time.sleep(0.1)
    assert probe(time.monotonic()) == 0.0, "an answering loop reads 0"
    loop.call_soon_threadsafe(time.sleep, 0.6)            # the loop is held
    time.sleep(0.05)
    probe(time.monotonic())
    time.sleep(0.4)
    assert probe(time.monotonic()) >= 0.35
    loop.call_soon_threadsafe(loop.stop)
    runner.join(2)


def test_the_path_is_the_request_open_longest_not_the_last_one_seen():
    """C's F4 10-29: every STALL was /dashboard/summary while the line showed only «ING lag_wide · watcher:6» and
    read as the ingestion's - the path of the request open longest comes first, after the seconds."""
    r, said = Readings(), []
    w = r.watch(said)
    r.open, r.path = 9.0, "/dashboard/summary"
    w.tick(1.0)
    r.open, r.path, r.table = 6.0, "/tables/dt_log/data", "lag_wide"
    w.tick(2.0)
    r.open, r.path = 0.0, None
    w.tick(3.0)
    assert said[0].startswith("STALL 11s P /dashboard/summary L0 ") and said[0].endswith("ING lag_wide"), said


def test_an_open_request_is_counted_until_it_ends():
    began = request_timing.begin("/x")
    time.sleep(0.05)
    seconds, path, key, pid = request_timing.oldest_open()
    assert seconds >= 0.05 and path == "/x" and key == began[2] and pid is None
    request_timing.end(began, "GET", "/x", None)
    assert request_timing.oldest_open() == (0.0, None, None, None)


class _Driver:
    """A connection whose driver tells its database pid, as psycopg2's does."""

    def __init__(self, pid):
        self.info = {}
        self.connection = type("Fairy", (), {"dbapi_connection": type("Dbapi", (), {
            "get_backend_pid": lambda _self: pid})()})()


def test_a_request_s_database_pid_is_known_while_its_query_runs_and_only_then():
    """Lead 11-10: the stalled request's own statement - the cursor hooks that count its database time note the pid
    its query runs on, and forget it when the query ends (the connection may serve another request next)."""
    began = request_timing.begin("/tables/t/columns")
    conn = _Driver(4242)
    try:
        assert request_timing.oldest_open()[3] is None
        request_timing._query_started(conn, None, "SELECT 1", None, None, False)
        assert request_timing.oldest_open()[2:] == (began[2], 4242)
        request_timing._query_ended(conn, object(), "SELECT 1", None, None, False)
        assert request_timing.oldest_open()[3] is None
    finally:
        request_timing.end(began, "GET", "/x", None)
    request_timing._query_started(conn, None, "SELECT 1", None, None, False)       # outside a request: nothing
    assert request_timing.oldest_open() == (0.0, None, None, None)


def test_p_says_what_its_request_s_query_waits_for_at_its_longest_reading():
    """«P /tables/t/columns SELECT cell_sources 9s Lock:relation»: the longest reading of the P request's own query is
    kept - a tick where it runs Python (no pid) does not wipe it; another request becoming P starts over."""
    r, said = Readings(), []
    w = r.watch(said)
    r.doing = {7: ("SELECT cell_sources", 4.2, "IO:DataFileRead", None),
               8: ("SELECT cell_sources", 9.4, "Lock:relation", "by 4123 AUTOVACUUM public.cell_sources"),
               9: ("UPDATE x", 1.0, "cpu", None)}
    r.open, r.path, r.key, r.pid = 6.0, "/tables/t/columns", 5, 7
    w.tick(1.0)
    r.open, r.pid = 7.0, 8
    w.tick(2.0)
    r.open, r.pid = 7.5, 7                              # a shorter reading later
    w.tick(2.5)
    r.open, r.pid = 8.0, None                           # back in Python
    w.tick(3.0)
    r.open = 0.0
    w.tick(4.0)
    assert said[0].startswith("STALL 9s P /tables/t/columns SELECT cell_sources 9s Lock:relation "
                              "by 4123 AUTOVACUUM public.cell_sources L0 "), said
    r.open, r.path, r.key, r.pid = 6.0, "/a", 6, 9
    w.tick(10.0)
    r.open, r.path, r.key, r.pid = 7.5, "/b", 7, None   # another request is open longest now
    w.tick(11.0)
    r.open = 0.0
    w.tick(12.0)
    assert said[1].startswith("STALL 8s P /b L0 "), said


def test_a_failed_p_reading_says_question_mark_after_the_path_only(caplog):
    r, said = Readings(), []
    w = r.watch(said)
    r.open, r.path, r.pid, r.doing = 6.0, "/x", 7, {}
    w.tick(1.0)
    r.open = 0.0
    w.tick(2.0)
    assert said[0].startswith("STALL 7s P /x ? L0 "), said
    assert sum("the P db reading failed" in m for m in caplog.messages) == 1


def test_health_s_stall_carries_the_slow_line_its_p_request_left(monkeypatch, caplog):
    """Owner 11-10 «노란 띠에는 없음»: the [Slow] line of the freeze's P request rides with the STALL line - the same
    sentence the log has; none while the request is open."""
    import logging
    monkeypatch.setattr(request_timing, "slow_request_ms", lambda: 0)
    monkeypatch.setattr(stall_watch, "STALL_SECONDS", 0.0)
    said = []
    w = stall_watch.Watch(request_timing.oldest_open, lambda now: 0.0, lambda: (1, 40), lambda: 0, lambda: None,
                          lambda pids: (5.0, None, PARTS), lambda: ({}, None), lambda: None, lambda: None,
                          lambda: None, say=said.append)
    monkeypatch.setattr(stall_watch, "_watch", [w])
    began = request_timing.begin("/tables/t/columns")
    w.tick(time.perf_counter() + 6.0)                    # six seconds on

    class Answered:
        status_code, headers = 200, {"content-length": "12"}
    w.tick(time.perf_counter() + 36.0)                   # a mid line: the request is still open
    assert said and stall_watch.last()["slow"] is None
    with caplog.at_level(logging.WARNING, logger="Server"):
        request_timing.end(began, "GET", "/tables/t/columns", Answered)
    w.tick(time.perf_counter() + 37.0)
    slow = [m for m in caplog.messages if m.startswith("[Slow] GET /tables/t/columns 200 - ")]
    assert len(slow) == 1 and stall_watch.last() == dict(w.last, slow=slow[0])
    assert stall_watch.last()["line"].startswith("STALL ") and " P /tables/t/columns " in stall_watch.last()["line"]


def test_the_slow_lines_kept_are_the_last_ones(monkeypatch):
    monkeypatch.setattr(request_timing, "slow_request_ms", lambda: 0)
    monkeypatch.setattr(request_timing, "_slow_said", type(request_timing._slow_said)())

    class Answered:
        status_code, headers = 200, {"content-length": "1"}
    keys = []
    for _ in range(request_timing.SLOW_KEPT + 2):
        began = request_timing.begin("/x")
        keys.append(began[2])
        request_timing.end(began, "GET", "/x", Answered)
    assert request_timing.slow_line(keys[0]) is None and request_timing.slow_line(keys[1]) is None
    assert request_timing.slow_line(keys[2]).startswith("[Slow] GET /x 200 - ")
    assert len(request_timing._slow_said) == request_timing.SLOW_KEPT


@pytest.mark.pg
def test_on_postgresql_p_names_the_stalled_request_s_own_statement_and_its_wait(pg_engine, monkeypatch, caplog):
    """The board the lead asked (11-10): a request whose query sleeps on PostgreSQL - the line's P names its statement,
    its seconds and «Timeout:PgSleep», read off pg_stat_activity by the pid the cursor hook noted; then its [Slow]
    line rides with it."""
    import contextvars
    import logging
    from sqlalchemy import text
    monkeypatch.setattr(request_timing, "slow_request_ms", lambda: 0)
    monkeypatch.setattr(stall_watch, "_engine", [pg_engine])
    monkeypatch.setattr(stall_watch, "STALL_SECONDS", 0.0)
    said = []
    w = stall_watch.Watch(request_timing.oldest_open, lambda now: 0.0, lambda: (1, 40), lambda: 0, lambda: None,
                          lambda pids: (5.0, None, PARTS), lambda: ({}, None), lambda: None, lambda: None,
                          lambda: None, say=said.append, pg_doing=stall_watch.pg_doing)
    monkeypatch.setattr(stall_watch, "_watch", [w])
    began = request_timing.begin("/tables/t/columns")

    def query():
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT pg_sleep(3)"))
    worker = threading.Thread(target=contextvars.copy_context().run, args=(query,))
    worker.start()
    for _ in range(40):                                  # until the hook has noted its pid
        if request_timing.oldest_open()[3]:
            break
        time.sleep(0.05)
    time.sleep(1.2)
    w.tick(time.perf_counter() + 6.0)
    worker.join()

    class Answered:
        status_code, headers = 200, {"content-length": "2"}
    with caplog.at_level(logging.WARNING, logger="Server"):
        request_timing.end(began, "GET", "/tables/t/columns", Answered)
    w.tick(time.perf_counter() + 7.0)
    assert re.match(r"^STALL \d+s P /tables/t/columns SELECT [12]s Timeout:PgSleep L0 ", said[0]), said
    slow = [m for m in caplog.messages if m.startswith("[Slow] GET /tables/t/columns 200 - ")]
    assert stall_watch.last()["slow"] == slow[0]


@pytest.mark.pg
def test_on_postgresql_p_names_who_holds_the_stalled_request_s_statement(pg_engine, monkeypatch):
    """Log hole 2 (lead 11-10): a × whose statement waits on a row another session holds - the P cell names the holder
    and what it ran: «… Lock:transactionid by <pid> idle-in-transaction UPDATE stall_hold»."""
    import contextvars
    from sqlalchemy import text
    monkeypatch.setattr(stall_watch, "_engine", [pg_engine])
    monkeypatch.setattr(stall_watch, "STALL_SECONDS", 0.0)
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS stall_hold (id int PRIMARY KEY, v int)"))
        conn.execute(text("INSERT INTO stall_hold VALUES (1, 0) ON CONFLICT DO NOTHING"))
    holder = pg_engine.connect()
    holding = holder.begin()
    holder_pid = holder.execute(text("SELECT pg_backend_pid()")).scalar()
    holder.execute(text("UPDATE stall_hold SET v = v + 1 WHERE id = 1"))     # idle in its transaction after this
    said = []
    w = stall_watch.Watch(request_timing.oldest_open, lambda now: 0.0, lambda: (1, 40), lambda: 0, lambda: None,
                          lambda pids: (5.0, None, PARTS), lambda: ({}, None), lambda: None, lambda: None,
                          lambda: None, say=said.append, pg_doing=stall_watch.pg_doing)
    began = request_timing.begin("/admin/chain/queue/cancel")

    def query():
        with pg_engine.connect() as conn:
            conn.execute(text("SET lock_timeout = '5s'"))
            conn.execute(text("UPDATE stall_hold SET v = v + 1 WHERE id = 1"))
            conn.commit()
    worker = threading.Thread(target=contextvars.copy_context().run, args=(query,))
    try:
        worker.start()
        # the watch reads from a thread of its own - outside the request, or its probe is the request's statement
        apart = contextvars.Context().run
        for _ in range(60):                              # until the hook has noted its pid and it waits
            pid = request_timing.oldest_open()[3]
            if pid and (apart(stall_watch.pg_doing, pid) or (None, 0, ""))[2].startswith("Lock:"):
                break
            time.sleep(0.05)
        apart(w.tick, time.perf_counter() + 6.0)
    finally:
        holding.rollback()
        holder.close()
        worker.join()
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE stall_hold"))

    class Answered:
        status_code, headers = 200, {"content-length": "2"}
    request_timing.end(began, "POST", "/admin/chain/queue/cancel", Answered)
    w.tick(time.perf_counter() + 7.0)
    assert re.match(r"^STALL \d+s P /admin/chain/queue/cancel UPDATE stall_hold \d+s Lock:\w+ by %d idle-in-transaction UPDATE stall_hold L0 "
                    % holder_pid, said[0]), said


def test_a_request_waiting_for_a_grid_process_is_counted_while_it_waits():
    pool = process_pool.Pool("probe", "s", 1, "w", 1, "Probe", "probe.log", "probes")
    pool.taken[0] = 1                                   # every process busy
    seen = []

    def wait():
        with pytest.raises(Exception):
            process_pool._run(lambda: None, {}, 1, 0.4, pool=pool)
    waiter = threading.Thread(target=wait)
    waiter.start()
    time.sleep(0.15)
    seen.append(pool.waiting[0])
    waiter.join()
    assert (seen, pool.waiting[0]) == ([1], 0)


def test_health_carries_the_last_stall_line(client, monkeypatch):
    r, said = Readings(), []
    w = r.watch(said)
    r.open = 6.0
    w.tick(1.0)
    r.open = 0.0
    w.tick(2.0)
    monkeypatch.setattr(stall_watch, "_watch", [w])
    body = client.get("/health").json()
    assert body["stall"] == {"line": said[0], "at": w.last["at"], "slow": None}
    monkeypatch.setattr(stall_watch, "_watch", [])
    assert client.get("/health").json()["stall"] is None


# Owner 11-06 ㄱ: «stall 6s P /tables/split_table/data ... C41 watcher:4» - the grid page's body runs in a pool child
# that had no name on the line; «D10/121s» named no statement.

def test_a_pool_child_busiest_names_its_pool(monkeypatch):
    """The pool children are named from the pools this process holds - an idle one's process, a busy one's pid."""
    from utils import heartbeat

    class Child:
        pid = 424242
    monkeypatch.setattr(heartbeat, "read_all", lambda: {})
    monkeypatch.setattr(process_pool.GRID, "busy", {515151})
    monkeypatch.setattr(process_pool.WALK, "idle", [[Child(), None, 0]])
    names, _table = stall_watch.workers()
    assert names == {os.getpid(): "api", 515151: "grid", 424242: "walk"}

    said = []
    w = stall_watch.Watch(lambda: (8.0, "/tables/split_table/data", 1, None), lambda now: 0.0, lambda: (1, 40), lambda: 0,
                          lambda: (1, 0.0, None, 0), lambda pids: (41.0, (pids[515151], 38.0), {
                              "pg": 0.0, "api": 1.0, "other": 2.0}), stall_watch.workers,
                          lambda: (0, None), lambda: None, lambda: None, say=said.append)
    w.tick(1.0)
    w.tick(2.0)
    assert said == [] and w.freeze is not None
    w.open_requests = lambda: (0.0, None, None, None)
    w.tick(3.0)
    assert said == ["STALL 10s P /tables/split_table/data L0 T1/40 G0 D1/0s B0 X0 C41 api:1 grid:38 pg:0 other:2 "
                    "pgIO0"], "no disk reading yet: no IO cell"


def test_no_pool_child_leaves_the_line_as_it_was(monkeypatch):
    from utils import heartbeat
    monkeypatch.setattr(heartbeat, "read_all", lambda: {"watcher": {"pid": 77}})
    for pool in process_pool.POOLS:
        monkeypatch.setattr(pool, "idle", [])
        monkeypatch.setattr(pool, "busy", set())
    assert stall_watch.workers() == ({os.getpid(): "api", 77: "watcher"}, None)


def test_a_failed_name_reading_says_question_mark_in_the_name_cell():
    r, said = Readings(), []
    w = r.watch(said)
    r.open, r.cpu = 8.0, (5.0, None, PARTS)        # no pid named - no busiest one
    w.named = lambda: (_ for _ in ()).throw(RuntimeError("pool list changed"))
    w.tick(1.0)
    r.open = 0.0
    w.tick(2.0)
    assert said == ["STALL 9s L0 T3/40 G0 D1/0s B0 X0 C5 api:2 ? pg:1 other:2 IO r1w2MB/s 3iops pgIO0"]


@pytest.mark.parametrize("query, head", [
    ("INSERT INTO cell_sources (row_id, value) VALUES ('비밀', 'from secret_table')", "INSERT cell_sources"),
    ("SELECT extract(epoch FROM now() - q) FROM pg_stat_activity", "SELECT pg_stat_activity"),
    ("select a from public.audit_logs where b = 'x'", "SELECT public.audit_logs"),
    ('UPDATE "cell_sources" SET v = 1', "UPDATE cell_sources"),
    ("DELETE FROM job_queue WHERE id = 3", "DELETE job_queue"),
    ("/* from hidden */ SELECT 1", "SELECT"),
    ("SELECT * FROM (SELECT a FROM inner_t) s", "SELECT"),
    ("INSERT INTO t VALUES ('a text cut short from k", "INSERT t"),
    ("SELECT 'a value cut short from secret_name", "SELECT"),
    ("", None), (None, None), ("  -- only a comment", None),
    ("autovacuum: VACUUM public.pfab_metro", "AUTOVACUUM public.pfab_metro"),
    ("autovacuum: VACUUM ANALYZE public.cell_sources (to prevent wraparound)", "AUTOVACUUM+ANALYZE-WRAP public.cell_sources"),
    ("autovacuum: VACUUM public.audit_logs (to prevent wraparound)", "AUTOVACUUM-WRAP public.audit_logs"),
    ("autovacuum: ANALYZE public.dt_log", "AUTOANALYZE public.dt_log"),
    ("VACUUM (VERBOSE) audit_logs", "VACUUM"),
    ("ANALYZE dt_log", "ANALYZE dt_log"),
])
def test_the_statement_head_is_a_word_and_a_table_and_never_a_value(query, head):
    assert stall_watch.statement_head(query) == head
    if query:
        assert "비밀" not in (head or "") and "secret" not in (head or "")


def test_the_d_cell_carries_the_head_of_the_longest_statement_of_the_freeze():
    r, said = Readings(), []
    w = r.watch(said)
    r.open, r.statements = 8.0, (3, 5.0, "SELECT audit_logs", 1)
    w.tick(1.0)
    r.statements = (2, 9.4, "INSERT cell_sources", 6)
    w.tick(2.0)
    r.statements = (10, 2.0, "UPDATE job_queue", 2)
    w.tick(3.0)
    r.open = 0.0
    w.tick(4.0)
    assert said == ["STALL 11s L0 T3/40 G0 D10/9s INSERT cell_sources B0 X0 C5 api:2 pg:1 other:2 IO r1w2MB/s 3iops pgIO6"]


def test_the_b_cell_says_the_most_sessions_held_up_and_who_held_them():
    """Owner 11-09 «거의 모든 stall 에 autovacuum»: an autovacuum worker holding three sessions is named; the most held
    up in the freeze is kept; a reading that fails says «?» in its cell only."""
    r, said = Readings(), []
    w = r.watch(said)
    r.open, r.blocked = 8.0, (1, "UPDATE job_queue")
    w.tick(1.0)
    r.blocked = (3, "AUTOVACUUM public.pfab_metro")
    w.tick(2.0)
    r.blocked = (0, None)
    w.tick(3.0)
    r.open = 0.0
    w.tick(4.0)
    assert said == ["STALL 11s L0 T3/40 G0 D1/0s B3 AUTOVACUUM public.pfab_metro X0 C5 api:2 pg:1 other:2 IO r1w2MB/s 3iops pgIO0"]
    said.clear()
    r.open, r.blocked = 8.0, RuntimeError("no database")
    w.tick(10.0)
    r.open = 0.0
    w.tick(11.0)
    assert said == ["STALL 9s L0 T3/40 G0 D1/0s B? X0 C5 api:2 pg:1 other:2 IO r1w2MB/s 3iops pgIO0"]


def test_the_holder_holding_up_the_most_is_read_off_backend_waits(monkeypatch):
    """`blocked` reads `db_waits.backend_waits` - one row per (held up, holder); an autovacuum worker holder counts like
    any (backend_waits does not filter by backend type)."""
    import db_waits

    class Conn:
        connection = type("C", (), {"dbapi_connection": object()})()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(stall_watch, "_kept", lambda: type("E", (), {"connect": lambda self: Conn()})())
    holder = lambda pid, query: {"pid": pid, "query": query}              # noqa: E731
    monkeypatch.setattr(db_waits, "backend_waits", lambda conn, chars=60: [
        {"pid": 11, "blocker": holder(90, "autovacuum: VACUUM public.pfab_metro")},
        {"pid": 12, "blocker": holder(90, "autovacuum: VACUUM public.pfab_metro")},
        {"pid": 12, "blocker": holder(91, "UPDATE job_queue SET a = 1")},
        {"pid": 13, "blocker": holder(90, "autovacuum: VACUUM public.pfab_metro")}])
    assert stall_watch.blocked() == (3, "AUTOVACUUM public.pfab_metro")
    monkeypatch.setattr(db_waits, "backend_waits", lambda conn, chars=60: [])
    assert stall_watch.blocked() == (0, None)


def test_the_x_cell_says_the_oldest_open_transaction():
    """Lead 11-09: the oldest open transaction in the freeze - its seconds, its snapshot's xmin age, its statement's
    head; none open «X0»; a reading that fails «X?» in its cell only."""
    r, said = Readings(), []
    w = r.watch(said)
    r.open, r.oldest = 8.0, (30.2, 900, "UPDATE job_queue")
    w.tick(1.0)
    r.oldest = (412.4, 18234, "UPDATE pfab_metro")
    w.tick(2.0)
    r.oldest = (5.0, None, "SELECT cell_sources")
    w.tick(3.0)
    r.open = 0.0
    w.tick(4.0)
    assert said == ["STALL 11s L0 T3/40 G0 D1/0s B0 X412s/18234 UPDATE pfab_metro C5 api:2 pg:1 other:2 IO r1w2MB/s 3iops pgIO0"]
    said.clear()
    r.open, r.oldest = 8.0, (6.0, None, None)
    w.tick(10.0)
    r.open = 0.0
    w.tick(11.0)
    assert said == ["STALL 9s L0 T3/40 G0 D1/0s B0 X6s C5 api:2 pg:1 other:2 IO r1w2MB/s 3iops pgIO0"]
    said.clear()
    r.open, r.oldest = 8.0, RuntimeError("no database")
    w.tick(20.0)
    r.open = 0.0
    w.tick(21.0)
    assert said == ["STALL 9s L0 T3/40 G0 D1/0s B0 X? C5 api:2 pg:1 other:2 IO r1w2MB/s 3iops pgIO0"]


def test_the_oldest_transaction_is_read_off_pg_stat_activity(monkeypatch):
    """One row ordered by xact_start: (seconds, xmin age or None, head) - no value rides the head; None with no row."""
    rows = [(412.4, 18234, "UPDATE pfab_metro SET x = 'secret' WHERE id = 1")]

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, statement):
            assert str(statement).endswith("ORDER BY xact_start LIMIT 1")         # the oldest
            return type("R", (), {"first": lambda self: rows[0] if rows else None})()

    monkeypatch.setattr(stall_watch, "_kept", lambda: type("E", (), {"connect": lambda self: Conn()})())
    assert stall_watch.oldest_transaction() == (412.4, 18234, "UPDATE pfab_metro")
    rows[0] = (3.0, None, "idle")
    assert stall_watch.oldest_transaction() == (3.0, None, "IDLE")
    rows.clear()
    assert stall_watch.oldest_transaction() is None


def test_the_active_statements_and_those_waiting_on_io_are_read_off_one_row(monkeypatch):
    """The D cell's one query carries the sessions waiting on IO in its fourth column (lead 11-09) - no new query; no
    active statement but this one, (0, 0.0, None, 0)."""
    rows = [(5, 12.6, "SELECT v FROM cell_sources WHERE v = 'secret'", 3)]
    asked = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, statement):
            asked.append(str(statement))
            return type("R", (), {"first": lambda self: rows[0] if rows else None})()

    monkeypatch.setattr(stall_watch, "_kept", lambda: type("E", (), {"connect": lambda self: Conn()})())
    assert stall_watch.active_statements() == (5, 12.6, "SELECT cell_sources", 3)
    rows.clear()
    assert stall_watch.active_statements() == (0, 0.0, None, 0)
    assert asked == [stall_watch.ACTIVE_STATEMENTS] * 2 and "wait_event_type = 'IO'" in asked[0]
