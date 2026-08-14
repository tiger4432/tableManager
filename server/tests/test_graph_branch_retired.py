"""The old graph branch is retired, and the retirement has to be VISIBLE.

Ruling R-2026-08-14-H (product owner, 2026-08-14: "실측할 거 없고 그냥 기존
그래프는 날려"). What died is the pipeline that kept a second copy of the source
tables - extract → materialize → store. What lives is the graph VIEWER, which is
being ported to read the ledger walk.

WHY THESE ASSERTIONS AND NOT "the route is gone"
------------------------------------------------
Deleting the routes would have been the obvious move and it is the wrong one, for
a measured reason: this app serves a SPA catch-all at `@app.get("/{file_name:path}")`,
so a path with no route returns **index.html with status 200**. A client asking
`/graph/stats` would get `res.ok === true` and then fail parsing HTML as JSON -
the retirement would surface to the operator as "알 수 없는 오류". So the routes
stay registered and answer with an explicit, structured refusal, and the first
test below is the one that keeps it that way.

The status is 410, not 404: 404 says "there is no such thing", 410 says "there
was, and it was retired on purpose". Only the second is true here.
"""
import pytest

import main

# Every entry point into the retired branch. The write path (`/api/graph/sync`)
# is in this list on purpose: it fed the materializer, so it is part of the
# pipeline that died, not a reader that merely lost its data.
RETIRED_GET_ROUTES = [
    "/graph/stats",
    "/graph/neighbors?label=Core&identity=X",
    "/graph/nodes/search?q=X",
    "/graph/chip-trace?identity=X",
    "/graph/mapping-summary",
]


def _details(response):
    body = response.json()
    assert "detail" in body, f"no structured detail: {body}"
    return body["detail"]


def _code_only(src):
    """Source with whole-line comments removed.

    🔴 Needed because the retirement left TOMBSTONE COMMENTS naming the very
    calls these tests assert are gone - so a naive `"name" not in src` matches
    the tombstone and fails on correct code. This repo has already been bitten
    twice by exactly that (`test_process_supervisor.py`'s heartbeat guard
    matched a comment mentioning `run_graph_sync.py`; the first draft of the
    hot-reload test below matched its own tombstone). Strip once, here, rather
    than tune a substring per site.
    """
    return "\n".join(line for line in src.splitlines()
                     if not line.lstrip().startswith("#"))


@pytest.mark.parametrize("path", RETIRED_GET_ROUTES)
def test_every_retired_get_route_refuses_with_the_retirement_contract(client, path):
    r = client.get(path)
    assert r.status_code == 410, f"{path} answered {r.status_code}"
    d = _details(r)
    # 🔴 The REASON is the load-bearing field, not the status code (ruling
    # R-2026-08-13-C: prose is for humans, anything the screen must branch on
    # goes out as a structured field). The viewer distinguishes "retired" from
    # "temporarily broken" on this string alone - and it must, because the two
    # states differ in whether a retry button should exist at all.
    assert d["reason"] == "old_graph_branch_retired"
    assert d["state"] == "retired"
    assert d["successor"] == "/api/ledger/trace"
    assert d["message"]
    # 410 is CACHEABLE by default, so without this the refusal can outlive the
    # refusal - measured this round: the viewer kept rendering a previous
    # instance's message from cache after the copy was changed. The same
    # mechanism would keep browsers refusing after a future revival.
    assert r.headers.get("cache-control") == "no-store", (
        f"{path} lets the browser cache its retirement notice")


def test_the_write_entry_point_refuses_too():
    """`POST /api/graph/sync` used to forward to the worker on :8090.

    It must not answer 503 ("the sync service is not running"), which reads as a
    transient outage and sends the operator to restart a process that no longer
    exists in the stack.
    """
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        r = c.post("/api/graph/sync", json={"table_name": "all"})
    assert r.status_code == 410
    assert _details(r)["reason"] == "old_graph_branch_retired"


def test_a_retired_path_does_not_fall_through_to_the_spa_catch_all():
    """The defect this whole design avoids, asserted directly.

    If someone later 'cleans up' by deleting the route declarations, this test
    fails with 200 and an HTML body - which is exactly what the operator would
    have seen instead of an honest refusal.
    """
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        r = c.get("/graph/stats")
    assert r.status_code != 200
    assert "text/html" not in r.headers.get("content-type", "")


def test_the_boot_schema_step_will_not_recreate_the_dropped_tables(tmp_path):
    """Without this the DROP script is a no-op with extra steps.

    `Base.metadata.create_all` would remake all three tables EMPTY on the next
    restart, and the viewer would then say "그래프가 아직 비어 있습니다" - turning
    "it was retired" into "it has not filled up yet". The ruling ordered the
    execution sequence specifically to prevent states that lie like that.

    🔴 THIS RUNS THE BOOT STEP; it does not read a constant. An earlier draft
    only asserted the membership of `RETIRED_GRAPH_TABLES`, which would have
    stayed green if `bootstrap_database_schema` stopped passing the filter to
    `create_all` - i.e. it proved the list existed, not that anything used it.
    A landed constant with no consumer is not a landed guard.
    """
    from sqlalchemy import create_engine, inspect

    assert set(main.RETIRED_GRAPH_TABLES) == {
        "graph_nodes", "graph_edges", "graph_sync_state"}

    engine = create_engine(f"sqlite:///{tmp_path / 'boot_probe.db'}")
    main.bootstrap_database_schema(bind=engine)
    tables = set(inspect(engine).get_table_names())

    for name in main.RETIRED_GRAPH_TABLES:
        assert name not in tables, (
            f"boot recreated the retired table '{name}'; the DROP would not stick")
    # Non-vacuous: the boot step really did create things on this engine, so the
    # absences above are an exclusion rather than a create_all that did nothing.
    assert tables, "bootstrap_database_schema created no tables at all"


def test_the_scheduler_no_longer_resurrects_the_storage():
    """The graph worker is out of the stack, but the SCHEDULER is not.

    `graph_orphans.run_scheduled` calls `ensure_graph_tables` before sweeping, so
    a surviving process would have recreated the dropped tables on its next tick.
    That is why stopping the worker was not sufficient on its own.
    """
    import inspect

    import run_auto_update

    src = _code_only(inspect.getsource(run_auto_update.MultiDiscoveryScheduler.run))
    assert "self.maybe_sweep_graph_orphans()" not in src, (
        "the scheduler still sweeps graph orphans; its first act is "
        "ensure_graph_tables, which remakes the dropped tables")


def test_the_hot_reload_path_no_longer_recreates_them_either():
    """`refresh_dynamic_models` is reachable any time an operator hits reload."""
    import inspect

    from database import models

    src = _code_only(inspect.getsource(models.refresh_dynamic_models))
    assert "ensure_graph_tables" not in src, (
        "config hot-reload still ensures the retired graph tables exist")
