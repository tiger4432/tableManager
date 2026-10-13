"""총괄 8af4d378c ①: a walk process's first walk compiled the ledger declaration inside the request (~1.3 s on the box,
9f1be4122). The body's registration says what it fills before its first request (`in_pool(warm=)`) and the pool process
runs it before it says ready, logging one line; the walk's warm fills the one seat it reads (`_compiled_setup`), whose
file stamp still recompiles a changed declaration."""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER_DIR)

from runtime import process_pool  # noqa: E402

MARK = "ASSY_TEST_WARM_MARK"


def _warm_marker():
    with open(os.environ[MARK], "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return "warmed the marker"


def _body(db=None):
    return {"pid": os.getpid()}


TEST_POOL = process_pool.Pool("warmtest", "warmtest_processes", 1, None, None, "WarmTest", "warm_test.log", "tests")
process_pool.in_pool(_body, pool=TEST_POOL, warm=_warm_marker)


def test_a_pool_process_runs_its_bodies_warm_before_it_is_ready(tmp_path, monkeypatch):
    monkeypatch.setenv(MARK, str(tmp_path / "warm.pid"))
    worker = process_pool._start(60, TEST_POOL)
    try:
        assert (tmp_path / "warm.pid").read_text(encoding="utf-8") == str(worker[0].pid), \
            "the warm ran in that process before it said ready"
    finally:
        process_pool._end(worker, pool=TEST_POOL)


def test_the_walk_warms_every_declared_world_and_names_one_that_fails(monkeypatch):
    from ledger import schema, worker
    from ledger_api import ledger_subgraph

    asked = []

    def compiled(world):
        asked.append(world)
        if world == "w_x":
            raise ValueError("boom: no such table\nsecond line")
        return object()

    monkeypatch.setattr(schema, "world_listing", lambda: {"worlds": ["default", "w_x"], "operating": "default"})
    monkeypatch.setattr(worker, "_compiled_setup", compiled)
    said = ledger_subgraph.warm_declarations()
    assert asked == ["default", "w_x"], asked
    assert said.startswith("warmed 1 world(s) in ") and said.endswith(" · not compiled - w_x: boom: no such table"), said


def test_a_declaration_changed_after_the_warm_is_compiled_again(monkeypatch, tmp_path):
    from ledger import setup, worker
    from ledger_api import ledger_subgraph
    from tests.support.declaration import use_committed_declaration

    root = use_committed_declaration(monkeypatch, tmp_path)
    monkeypatch.setattr(worker, "_COMPILED", {})
    compiles = []
    monkeypatch.setattr(setup, "load_setup", lambda path: compiles.append(path) or object())
    said = ledger_subgraph.warm_declarations()
    assert said.startswith("warmed 1 world(s)") and len(compiles) == 1, (said, compiles)
    worker._compiled_setup("default")
    assert len(compiles) == 1, "a warm declaration is not compiled again"
    declaration = root / "ontology" / "ledger_config.json"
    declaration.write_text(declaration.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    stamp = os.stat(declaration).st_mtime + 5
    os.utime(declaration, (stamp, stamp))
    worker._compiled_setup("default")
    assert len(compiles) == 2, "a changed declaration is compiled again"


def test_the_walk_route_registers_the_warm():
    from ledger import trace_router  # noqa: F401 - its registration
    from ledger_api import ledger_subgraph

    assert ("ledger_api.ledger_subgraph", "warm_declarations") in process_pool.WALK.warms
    assert ledger_subgraph.warm_declarations.__module__ == "ledger_api.ledger_subgraph"
    assert not process_pool.GRID.warms, "the grid pool warms nothing"
