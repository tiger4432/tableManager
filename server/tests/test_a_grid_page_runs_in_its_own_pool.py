"""총괄 e570dcda5 ㄴ: the grid page's body runs in a pool of its own (`process_pool.GRID`, `grid_processes`) - the same
seat as the walk's (`in_pool`), its own size and its own processes, and a wait for a process (`grid_wait_seconds`) but
none for the answer (a plain grid read has none). The
/data route is the one door: the count is taken there, in the server process (`grid_count` - the kept counts, their
worker and their invalidation live there), and the page is read in the pool (`grid_page`)."""
import logging
import os
import sys
import threading
import time

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER_DIR)

from database.database import get_db                                     # noqa: E402
from runtime import process_pool                                          # noqa: E402
from runtime.offloop_json import OffLoopJSONRoute                       # noqa: E402

router = APIRouter(route_class=OffLoopJSONRoute)


def _head():
    """What a line of the logger `Server` heads with in this process."""
    return logging.getLogRecordFactory()("Server", logging.INFO, "", 0, "", (), None).name


def grid_body(hold: float = 0, db: Session = Depends(get_db)):
    time.sleep(hold)
    return {"pid": os.getpid(), "head": _head()}


def walk_body(db: Session = Depends(get_db)):
    return {"pid": os.getpid(), "head": _head()}


router.get("/grid")(process_pool.in_pool(grid_body, pool=process_pool.GRID))
router.get("/walk")(process_pool.in_pool(walk_body))
app = FastAPI()
app.router.route_class = OffLoopJSONRoute
app.include_router(router)


@pytest.fixture
def pools(monkeypatch):
    settings = {}
    monkeypatch.setattr(process_pool, "_settings", lambda: dict(settings))
    monkeypatch.setattr(process_pool, "_warmed", [False])
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, settings
    for pool in process_pool.POOLS:
        with pool.cond:
            taken = pool.taken[0]
            pool.generation[0] += 1
            process_pool._drain_locked(pool)
        assert taken == 0, "a request left its %s slot taken" % pool.name


@pytest.mark.parametrize("grid, walk", [(1, 0), (0, 1)])
def test_each_pool_runs_by_its_own_size(pools, grid, walk):
    client, settings = pools
    settings.update(grid_processes=grid, walk_processes=walk, walk_seconds_max=60)
    answered = {name: client.get("/" + name).json()["pid"] for name in ("grid", "walk")}
    assert (answered["grid"] != os.getpid()) == bool(grid), answered
    assert (answered["walk"] != os.getpid()) == bool(walk), answered
    busy = [pool.name for pool in process_pool.POOLS if pool.idle]
    assert busy == [name for name, size in (("walk", walk), ("grid", grid)) if size], busy


def test_a_grid_page_has_no_deadline(pools):
    """walk_seconds_max is the walk's, and grid_wait_seconds is the wait for a grid process, not for its answer: a grid
    page that takes longer than both still answers."""
    client, settings = pools
    settings.update(grid_processes=1, walk_processes=1, walk_seconds_max=1)
    assert client.get("/grid").status_code == 200            # started: a start is a wait for a process
    settings.update(grid_wait_seconds=1)
    answer = client.get("/grid", params={"hold": 2.5})
    assert answer.status_code == 200 and answer.json()["pid"] != os.getpid(), answer.text


def test_a_grid_request_waits_for_a_busy_grid_process_grid_wait_seconds(pools):
    """Lead, after 6f34a1320: grid processes stuck on plain reads (no statement limit) queued every grid request without
    end - the wait for one is bounded and said; the body it waited behind still answers."""
    client, settings = pools
    settings.update(grid_processes=1)
    assert client.get("/grid").status_code == 200            # started: a start is a wait for a process
    settings.update(grid_wait_seconds=1)
    out = {}
    holding = threading.Thread(target=lambda: out.setdefault("hold", client.get("/grid", params={"hold": 4})))
    holding.start()
    for _ in range(300):
        if process_pool.GRID.busy:
            break
        time.sleep(0.1)
    waited = client.get("/grid")
    holding.join(30)
    assert waited.status_code == 503 and waited.json()["detail"] == {
        "reason": "grid_pool_busy",
        "message": "Every grid process stayed busy for 1 s - try again, or raise grid_processes in "
                   "ingestion_settings.json"}, waited.text
    assert out["hold"].status_code == 200, out["hold"].text


def test_a_pool_process_s_lines_head_with_its_pool(pools):
    """Lead, 10-13: a page line in grid_pool.log headed «[Server]» - which process wrote it was not said."""
    client, settings = pools
    settings.update(grid_processes=1, walk_processes=1)
    heads = {name: client.get("/" + name).json()["head"] for name in ("grid", "walk")}
    assert heads == {"grid": "GridPool.Server", "walk": "WalkPool.Server"}, heads


def test_a_reload_renews_both_pools(pools, monkeypatch):
    client, settings = pools
    settings.update(grid_processes=1, walk_processes=1, walk_seconds_max=60)
    before = {name: client.get("/" + name).json()["pid"] for name in ("grid", "walk")}
    monkeypatch.setattr(process_pool, "_warmed", [True])
    monkeypatch.setattr(process_pool, "warm", lambda: None)
    process_pool.recycle()
    after = {name: client.get("/" + name).json()["pid"] for name in ("grid", "walk")}
    assert all(after[name] != before[name] for name in before), (before, after)


# ── the /data door ─────────────────────────────────────────────────────────────────────────────────────────────────

def _door_spy(monkeypatch):
    import main

    seen = []
    real = main.grid_page

    def spy(**kwargs):
        seen.append({"counted": kwargs["counted"], "thread": threading.current_thread().name})
        return real(**kwargs)

    monkeypatch.setattr(main, "grid_page", spy)
    return seen


def test_the_door_counts_here_and_hands_the_count_to_the_page(client, monkeypatch):
    import main

    seen = _door_spy(monkeypatch)
    counts = []
    real_count = main.grid_count
    monkeypatch.setattr(main, "grid_count", lambda *a, **k: counts.append(1) or real_count(*a, **k))
    page = client.get("/tables/raw_table_1/data").json()
    deferred = client.get("/tables/raw_table_1/data", params={"defer_total": "true"}).json()

    assert counts == [1], "the count is taken once, at the door, and only when it is not deferred"
    assert seen[0]["counted"]["total"] == page["total"] == page["count"]["total"]
    assert seen[1]["counted"] is None and deferred["total"] is None


def test_the_door_refuses_a_sort_it_cannot_make_before_counting(client, monkeypatch):
    import main

    counts = []
    monkeypatch.setattr(main, "grid_count", lambda *a, **k: counts.append(1))
    answer = client.get("/tables/raw_table_1/data", params={"order_by": "no_such_column"})
    assert answer.status_code == 422 and "cannot sort by 'no_such_column'" in answer.text and counts == []


def test_the_page_body_is_the_grid_pool_s():
    import main

    assert main.grid_page.__pool_body__.__wrapped__.__name__ == "grid_page"
    assert "main" in process_pool.GRID.modules and "main" not in process_pool.WALK.modules
