"""Lead 11-10 ㄴ: the pools' processes start WARM_AT_ONCE at a time over both pools - as many at once as the two pools'
one each did - taking turns, so each pool's first is in the first turn (the grid's first is up no later than before)."""
import threading
import time

from runtime import process_pool


class _Process:
    pid = None

    def is_alive(self):
        return True

    def terminate(self):
        pass


class _Connection:
    def close(self):
        pass


def test_six_processes_start_two_at_a_time_each_pools_first_in_the_first_turn(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setattr(process_pool, "_warmed", [False])
    monkeypatch.setattr(process_pool, "size", lambda settings=None, pool=None: {"walk": 2, "grid": 4}[pool.name])
    started, running, most, lock = [], [0], [0], threading.Lock()

    def start(seconds, pool):
        with lock:
            started.append(pool.name)
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.2)
        with lock:
            running[0] -= 1
        return [_Process(), _Connection(), pool.generation[0]]

    monkeypatch.setattr(process_pool, "_start", start)
    try:
        process_pool.warm()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and sum(len(pool.idle) for pool in process_pool.POOLS) < 6:
            time.sleep(0.05)
        assert sorted(started[:2]) == ["grid", "walk"], started
        assert sorted(started) == ["grid"] * 4 + ["walk"] * 2
        assert most[0] == process_pool.WARM_AT_ONCE == 2
        assert [len(pool.idle) for pool in process_pool.POOLS] == [2, 4]
    finally:
        for pool in process_pool.POOLS:
            process_pool._drain(pool)
