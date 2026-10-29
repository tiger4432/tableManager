# -*- coding: utf-8 -*-
"""Owner 10-29 «파일 인제션하면 서버가 굳네 여전히» · «원인 파악하게 로그를 구성해봐 · 폰으로 쳐서 보내야 하니 구성
잘해» (lead ㄴ): a freeze of the API process leaves ONE line - `STALL 14s L12 T40/40 G6 D9/11s C97 slot2:61 ING
dt_log` - when it ends, one more every 30 s while it goes on, none without one; a reading that fails says «?» in its
own cell only. The cells' sources: the open-request table, the grid pool's waiting count, /health's stall."""
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from runtime import process_pool, request_timing, stall_watch  # noqa: E402


class Readings:
    """What the cells read, set per tick by the test."""

    def __init__(self):
        self.open, self.path, self.lag, self.threads, self.grid = 0.0, None, 0.0, (3, 40), 0
        self.statements, self.cpu, self.pids, self.table = (1, 0.1), (5.0, ("api", 2.0)), {1: "api"}, None

    def watch(self, said):
        def fail_or(value):
            if isinstance(value, Exception):
                raise value
            return value
        return stall_watch.Watch(lambda: fail_or((self.open, self.path)), lambda now: fail_or(self.lag),
                                 lambda: fail_or(self.threads), lambda: fail_or(self.grid),
                                 lambda: fail_or(self.statements), lambda pids: fail_or(self.cpu),
                                 lambda: fail_or((self.pids, self.table)), say=said.append)


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
    r.open, r.path, r.threads, r.grid, r.statements = 7.0, "/dashboard/summary", (40, 40), 6, (9, 11.2)
    r.cpu, r.table = (97.0, ("slot2", 61.3)), "dt_log"
    w.tick(101.0)
    r.open, r.lag, r.grid, r.cpu = 9.0, 12.4, 2, (40.0, ("watcher", 12.0))
    w.tick(103.0)
    assert said == []
    r.open, r.lag = 0.0, 0.0
    w.tick(105.0)
    assert said == ["STALL 11s P /dashboard/summary L12 T40/40 G6 D9/11s C97 slot2:61 ING dt_log"]
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
    assert said == ["STALL 10s L0 T3/40 G0 D? C5 api:2 ING dt_log"]
    assert sum("the D reading failed" in m for m in caplog.messages) == 1, "said once, not every tick"


def test_no_open_claim_leaves_the_ing_cell_out():
    r, said = Readings(), []
    w = r.watch(said)
    r.open = 6.0
    w.tick(1.0)
    r.open = 0.0
    w.tick(2.0)
    assert said == ["STALL 7s L0 T3/40 G0 D1/0s C5 api:2"]


def test_a_beat_file_of_a_gone_process_does_not_blank_the_cpu_cell():
    """Measured: a worker's heartbeat file outlived its process and the whole C cell read «?»."""
    import psutil
    gone = max(psutil.pids()) + 100_000
    cpu = stall_watch.Cpu()
    names = {os.getpid(): "api", gone: "slot9"}
    cpu(names)
    sum(i * i for i in range(200_000))
    machine, top = cpu(names)
    assert 0.0 <= machine <= 100.0 and top[0] == "api"


def test_the_cpu_cell_reads_only_the_named_pids_never_the_whole_process_table(monkeypatch):
    """C 10-29: walking this PC's 541 processes with psutil took 3.5 s - a watch that did it would grow the freeze it
    reads. The cell asks Process(pid) of the heartbeat pids and the API only; the machine's process table is never
    walked, so its cost follows the named pids, not how many processes the PC runs."""
    import psutil

    def walked(*_a, **_k):
        raise AssertionError("the whole process table was walked")
    monkeypatch.setattr(psutil, "process_iter", walked)
    monkeypatch.setattr(psutil, "pids", walked)
    cpu = stall_watch.Cpu()
    cpu({os.getpid(): "api"})
    machine, top = cpu({os.getpid(): "api"})
    assert top[0] == "api" and 0.0 <= machine <= 100.0


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
    seconds, path = request_timing.oldest_open()
    assert seconds >= 0.05 and path == "/x"
    request_timing.end(began, "GET", "/x", None)
    assert request_timing.oldest_open() == (0.0, None)


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
    assert body["stall"] == {"line": said[0], "at": w.last["at"]}
    monkeypatch.setattr(stall_watch, "_watch", [])
    assert client.get("/health").json()["stall"] is None
