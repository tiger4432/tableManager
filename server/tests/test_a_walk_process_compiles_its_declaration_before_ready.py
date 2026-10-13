"""총괄 8af4d378c ①: a walk process's first walk compiled the ledger declaration inside the request (~1.3 s on the box,
9f1be4122). The body's registration says what it fills before its first request (`in_pool(prepare=)`) and the pool
process runs it before it says ready, logging one line; the walk's prepare fills the operating world's entry in the one
seat it reads (`_compiled_setup`), whose file stamp still recompiles a changed declaration."""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER_DIR)

from runtime import process_pool  # noqa: E402

MARK = "ASSY_TEST_PREPARE_MARK"


def _prepare_marker():
    with open(os.environ[MARK], "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return "prepared the marker"


def _body(db=None):
    return {"pid": os.getpid()}


TEST_POOL = process_pool.Pool("preparetest", "preparetest_processes", 1, None, None, "PrepareTest", "prepare_test.log",
                              "tests")
process_pool.in_pool(_body, pool=TEST_POOL, prepare=_prepare_marker)


def test_a_pool_process_runs_its_bodies_prepare_before_it_is_ready(tmp_path, monkeypatch):
    monkeypatch.setenv(MARK, str(tmp_path / "prepare.pid"))
    worker = process_pool._start(60, TEST_POOL)
    try:
        assert (tmp_path / "prepare.pid").read_text(encoding="utf-8") == str(worker[0].pid), \
            "the prepare ran in that process before it said ready"
    finally:
        process_pool._end(worker, pool=TEST_POOL)


@pytest.mark.parametrize("fails", [False, True])
def test_the_walk_prepares_the_operating_world_only_and_says_why_it_could_not(monkeypatch, fails):
    from ledger import schema, worker
    from ledger_api import ledger_subgraph

    asked = []

    def compiled(world):
        asked.append(world)
        if fails:
            raise ValueError("boom: no such table\nsecond line")
        return object()

    monkeypatch.setattr(schema, "world_listing", lambda: {"worlds": ["default", "w_x"], "operating": "w_x"})
    monkeypatch.setattr(schema, "operating_world", lambda: "w_x")
    monkeypatch.setattr(worker, "_compiled_setup", compiled)
    said = ledger_subgraph.prepare_operating_declaration()
    assert asked == [None], "only the operating world, by the seat's own no-name: %r" % asked
    if fails:
        assert said == "prepared nothing - the operating world's declaration (w_x) did not compile: boom: no such table"
    else:
        assert said.startswith("prepared the operating world's declaration (w_x) in "), said


def test_a_declaration_changed_after_the_prepare_is_compiled_again(monkeypatch, tmp_path):
    from ledger import setup, worker
    from ledger_api import ledger_subgraph
    from tests.support.declaration import use_committed_declaration

    root = use_committed_declaration(monkeypatch, tmp_path)
    monkeypatch.setattr(worker, "_COMPILED", {})
    compiles = []
    monkeypatch.setattr(setup, "load_setup", lambda path: compiles.append(path) or object())
    said = ledger_subgraph.prepare_operating_declaration()
    assert said.startswith("prepared the operating world's declaration") and len(compiles) == 1, (said, compiles)
    worker._compiled_setup(None)
    assert len(compiles) == 1, "a prepared declaration is not compiled again"
    declaration = root / "ontology" / "ledger_config.json"
    declaration.write_text(declaration.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    stamp = os.stat(declaration).st_mtime + 5
    os.utime(declaration, (stamp, stamp))
    worker._compiled_setup(None)
    assert len(compiles) == 2, "a changed declaration is compiled again"


def test_the_walk_route_registers_the_prepare():
    from ledger import trace_router  # noqa: F401 - its registration
    from ledger_api import ledger_subgraph

    assert ("ledger_api.ledger_subgraph", "prepare_operating_declaration") in process_pool.WALK.prepares
    assert ledger_subgraph.prepare_operating_declaration.__module__ == "ledger_api.ledger_subgraph"
    assert not process_pool.GRID.prepares, "the grid pool prepares nothing"
