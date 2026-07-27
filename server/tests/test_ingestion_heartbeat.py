"""The watcher's progress beat must come from the ingestion path.

THE HOLE THIS CLOSES
--------------------
The watcher's heartbeat was published by its retry-poller thread. That thread
does a database query every 3 s and nothing else, so a watcher wedged *inside
ingestion* - a parser blocked on a lock, a hung network call, a deadlock in the
heavy lane - kept beating and /health reported `ok`. That is a hole in precisely
the property the endpoint was built for: the production incident was a process
that was alive and not progressing.

Moving the beat into the ingestion path alone would only move the hole, because
ingestion is idle most of the time. So the ingestion path opens a *work claim*
and refreshes it as it progresses, and whichever thread beats next publishes the
claim's age. The poller stops being able to mask a wedged ingestion and becomes
the thing that reports it.

Every test here drives the real `IngestionHandler` code path. The upsert is
stubbed (no database), the workspace is a tmp_path, and nothing touches the live
config, the live workspace or the live heartbeat directory - the `hb_dir`
fixture redirects heartbeat writes into tmp_path, so a failing guard cannot
damage anything real.

Table names use the `ophb_test_` prefix so they cannot collide with a table in
the user's gitignored config.
"""
import os
import sys
import time
import threading

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import directory_watcher
from directory_watcher import IngestionHandler
from utils import heartbeat
import health as health_mod


TBL_INFO = {
    "business_key": "item_id",
    "column_types": {"item_id": "string", "c1": "string"},
    "display_columns": ["item_id", "c1"],
}


def test_the_suite_can_never_beat_into_the_live_tree():
    """Guards the session fixture in conftest.py.

    Found by inspection after the fact: adding a heartbeat to the ingestion path
    made every test that drives `process_with_retry` write a real
    `server/config/worker_heartbeats/watcher.json` into the user's live tree. A
    dead pytest process's beat sitting there makes /health report a stale worker
    and serve 503 on a healthy system.

    This asserts the effective directory during a test run is NOT under the live
    server tree, whatever redirection is in force.
    """
    live = os.path.normcase(os.path.join(server_dir, "config", "worker_heartbeats"))
    effective = os.path.normcase(os.path.abspath(heartbeat.heartbeat_dir()))
    assert effective != live, "the suite is beating into the live config directory"
    assert not effective.startswith(os.path.normcase(server_dir) + os.sep), \
        f"heartbeat directory {effective} is inside the live server tree"


@pytest.fixture
def hb_dir(tmp_path, monkeypatch):
    """Redirect every heartbeat write into tmp_path."""
    d = str(tmp_path / "worker_heartbeats")
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: d)
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: os.path.join(d, f"{name}.json"))
    heartbeat._state.clear()
    heartbeat._claims.clear()
    yield d
    heartbeat._state.clear()
    heartbeat._claims.clear()


@pytest.fixture
def handler(tmp_path):
    ws = tmp_path / "ophb_test_tbl"
    for sub in ("raws", "archives", "err"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    return IngestionHandler(workspace_path=str(ws), config_path=None,
                            archives_path=str(ws / "archives"),
                            default_table_name="ophb_test_tbl")


class _FakeSession:
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


# --------------------------------------------------------------------------
# The claim brackets the whole unit of work, including the opaque parse.
# --------------------------------------------------------------------------
def test_the_ingestion_path_holds_a_claim_across_the_parse(hb_dir, handler,
                                                           monkeypatch, tmp_path):
    """The parse is one opaque call into a user script - the longest stretch
    with no instrumentation. If the claim did not already cover it, a parser
    that hangs would be invisible."""
    seen = {}

    def fake_resolve(self, file_path, t_name=None, table_info=None, meta=None):
        seen["claims"] = heartbeat.open_claims()
        raise ValueError("stop here - the claim is what is under test")

    monkeypatch.setattr(IngestionHandler, "_resolve_rows", fake_resolve)
    monkeypatch.setattr(IngestionHandler, "_snapshot_table_context",
                        lambda self: ("ophb_test_tbl", TBL_INFO))
    monkeypatch.setattr(IngestionHandler, "_move_to_err_folder", lambda self, p: p)
    monkeypatch.setattr(IngestionHandler, "_log_ingestion_failure",
                        lambda self, *a, **k: None)

    src = tmp_path / "ophb_test_tbl" / "raws" / "f.csv"
    src.write_text("item_id,c1\n1,a\n", encoding="utf-8")

    handler.process_with_retry(str(src), delay=0.0)

    assert seen.get("claims"), "no work claim was open while the parser ran"
    assert seen["claims"][0]["name"] == directory_watcher.HEARTBEAT_NAME
    assert "f.csv" in seen["claims"][0]["what"], \
        "the claim does not name the file, so /health cannot say what is stuck"
    # And it is released even though the parse raised.
    assert heartbeat.open_claims() == [], "a failed ingestion leaked its claim"


def test_the_retry_path_holds_its_own_claim(hb_dir, handler, monkeypatch, tmp_path):
    """A third way into ingestion, on the poller thread itself. Without a claim
    here, a wedged retry is invisible - the poller is the very thread that would
    otherwise keep beating."""
    seen = {}

    def fake_resolve(self, file_path, t_name=None, table_info=None, meta=None):
        seen["claims"] = heartbeat.open_claims()
        raise ValueError("stop here")

    monkeypatch.setattr(IngestionHandler, "_resolve_rows", fake_resolve)
    monkeypatch.setattr(IngestionHandler, "_snapshot_table_context",
                        lambda self: ("ophb_test_tbl", TBL_INFO))

    src = tmp_path / "ophb_test_tbl" / "archives" / "r.csv"
    src.write_text("item_id,c1\n1,a\n", encoding="utf-8")

    class _Log:
        filepath = str(src)
        status = "PENDING"
        error_message = None
        retry_count = 0

    assert handler.process_archived_file_sync(_Log(), _FakeSession()) is False
    assert seen.get("claims"), "the retry path opened no work claim"
    assert "r.csv" in seen["claims"][0]["what"]
    assert heartbeat.open_claims() == []


# --------------------------------------------------------------------------
# The chunk loop is what advances during a large ingestion.
# --------------------------------------------------------------------------
def test_every_committed_chunk_beats(hb_dir, handler, monkeypatch):
    """Beats must track committed rows, so they stop exactly when the upsert
    stops - not when some unrelated timer stops."""
    monkeypatch.setattr(directory_watcher, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates",
                        lambda db, t, batch: ([], [], [], []))

    rows = [{"item_id": str(i), "c1": "x"} for i in range(2500)]  # 3 chunks of 1000
    before = heartbeat._state.get("watcher", {}).get("beats", 0)
    handler._send_to_upsert(rows, filename="big.csv", total_rows=2500,
                            t_name="ophb_test_tbl", table_info=TBL_INFO)
    after = heartbeat._state["watcher"]["beats"]
    assert after - before >= 3, \
        f"3 committed chunks produced only {after - before} beat(s)"


def test_a_chunk_loop_that_stops_stops_the_beats(hb_dir, handler, monkeypatch):
    """The sensitivity control for the test above: if the upsert raises on the
    second chunk, the beats stop there. A beat driven by anything other than
    committed progress would keep counting."""
    calls = {"n": 0}

    def exploding(db, t, batch):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("database went away")
        return ([], [], [], [])

    monkeypatch.setattr(directory_watcher, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates", exploding)

    rows = [{"item_id": str(i), "c1": "x"} for i in range(5000)]  # 5 chunks
    before = heartbeat._state.get("watcher", {}).get("beats", 0)
    with pytest.raises(RuntimeError):
        handler._send_to_upsert(rows, filename="big.csv", total_rows=5000,
                                t_name="ophb_test_tbl", table_info=TBL_INFO)
    after = heartbeat._state["watcher"]["beats"]
    assert after - before == 1, \
        f"beats kept advancing after the upsert died ({after - before} beats)"


# --------------------------------------------------------------------------
# The end-to-end shape: wedged inside ingestion, poller still healthy.
# --------------------------------------------------------------------------
def test_a_watcher_wedged_inside_ingestion_goes_unhealthy(hb_dir, handler,
                                                          monkeypatch, tmp_path):
    """The exact hole, reproduced: the poller keeps beating, the ingestion
    thread is stuck in the parser, and /health must return 503.

    The stall threshold is passed in rather than waited out - the production
    value is 300 s and this test is about the decision, not the clock.
    """
    wedged = threading.Event()
    release = threading.Event()

    def hanging_parse(self, file_path, t_name=None, table_info=None, meta=None):
        wedged.set()
        release.wait(20.0)
        raise ValueError("released")

    monkeypatch.setattr(IngestionHandler, "_resolve_rows", hanging_parse)
    monkeypatch.setattr(IngestionHandler, "_snapshot_table_context",
                        lambda self: ("ophb_test_tbl", TBL_INFO))
    monkeypatch.setattr(IngestionHandler, "_move_to_err_folder", lambda self, p: p)
    monkeypatch.setattr(IngestionHandler, "_log_ingestion_failure",
                        lambda self, *a, **k: None)

    src = tmp_path / "ophb_test_tbl" / "raws" / "stuck.csv"
    src.write_text("item_id,c1\n1,a\n", encoding="utf-8")

    t = threading.Thread(target=handler.process_with_retry,
                         args=(str(src),), kwargs={"delay": 0.0}, daemon=True)
    t.start()
    assert wedged.wait(10.0), "fixture broken: ingestion never reached the parser"

    def health_now(stall_after):
        # The retry poller, doing its 3 s tick while ingestion is stuck.
        heartbeat.beat("watcher", force=True)
        hbs = heartbeat.read_all(stall_after=stall_after)
        sup = {"supervisor_pid": 1, "updated_at": time.time(),
               "failed_children": [], "correlated_children": [],
               "children": {"File Ingestion Watcher": {
                   "state": "running", "heartbeat": "watcher", "pid": os.getpid(),
                   "restarts": 0, "uptime_seconds": 3600.0,
                   "last_exit_code": None, "failure_reason": None}},
               "events": []}
        return health_mod.compute_health(
            {"status": "ok", "latency_ms": 1.0}, hbs, sup,
            {"pending": 0, "oldest_age_seconds": None}, 60.0,
            # This case is about a wedged watcher; skip the config-backup probe so
            # the verdict cannot depend on what is on this machine's disk.
            backup_result=None)

    try:
        # Control first: with a generous threshold this is a legitimately slow
        # ingestion, and a health check that pages for that would be useless.
        payload, status = health_now(stall_after=3600.0)
        assert status == 200, "a slow-but-progressing ingestion must not alarm"

        # Now the same instant judged against a threshold it has exceeded.
        payload, status = health_now(stall_after=0.001)
        assert status == 503, "a watcher wedged inside ingestion reported healthy"
        assert payload["checks"]["workers"]["watcher"]["status"] == "stalled"
        assert any("stuck.csv" in p for p in payload["problems"])
        # The beat itself is fresh - i.e. the old signal alone still says "fine".
        assert payload["checks"]["workers"]["watcher"]["work"]["open"] == 1
        assert heartbeat.read_all()["watcher"]["stale"] is False
    finally:
        release.set()
        t.join(10.0)

    assert heartbeat.open_claims() == []
