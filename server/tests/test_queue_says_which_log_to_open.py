# -*- coding: utf-8 -*-
""""Which log file do I open" has to be answerable from the response.

The mapper lines carry `[mapper@<file>]`, but that tag is only visible to somebody who
already opened the right file - it cannot help you choose one. Two lanes measured the
same gap independently: nothing in the admin surface names a log file, and hardcoding
one would be false twice over, because the data root can move the path and because which
file is written depends on whether the chain loop shares the web server's process.

⛔ READ FROM THE LOGGER, NEVER A CONSTANT. A constant was exactly how the mapper tag
came to say `chain_worker.log` on lines sitting in `server.log`.

🔴 THE LOOP'S FILE, NOT THIS PROCESS'S (총괄 3c3f2b1f2). The API's own `server.log` is not
where chain work is logged when the worker runs on its own, so the name comes from the
chain worker's heartbeat lap then, and an unknown name drops the key - no 「Log」 line.
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402
from chain import activity                                       # noqa: E402
from utils import heartbeat                                      # noqa: E402
from utils import logger as process_logging                      # noqa: E402


@pytest.fixture
def loop_here(monkeypatch):
    monkeypatch.setattr(activity.registry, "_attached", True)


@pytest.fixture
def beats(tmp_path, monkeypatch):
    """A heartbeat directory of this test's own, and a writer for the chain worker's file.
    This process runs no loop - set, not assumed: a test elsewhere that attaches the
    registry and does not detach it turned these red in a wide run (2026-09-25)."""
    monkeypatch.setattr(activity.registry, "_attached", False)
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path))
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: os.path.join(str(tmp_path), "%s.json" % name))

    def write(lap, age=0.0):
        ts = time.time() - age
        with open(os.path.join(str(tmp_path), "chain.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": "chain", "pid": 1, "ts": ts, "beats": 1, "started_at": ts,
                       "note": None, "work": {}, "laps": {"chain": dict(lap, at=ts)}}, fh)
    return write


def test_the_queue_says_which_file_the_loop_in_this_process_writes(db_session, loop_here):
    out = main.get_chain_queue_depth(db=db_session)
    assert out["loop_seen_via"] == "this_process"
    assert out.get("log_filename") == process_logging.active_log_filename()


def test_it_is_a_name_and_not_a_path(db_session, loop_here):
    """The server's disk layout is not something to put on a screen, and the path moves
    with the data root anyway."""
    name = main.get_chain_queue_depth(db=db_session).get("log_filename")
    if name is None:
        pytest.skip("no process logger configured in this run")
    assert os.sep not in name and "/" not in name, f"a path leaked out: {name!r}"
    assert name.endswith(".log")


def test_an_unconfigured_process_names_no_file_rather_than_a_guess(db_session, loop_here,
                                                                    monkeypatch):
    """🔴 «모를 때의 기본값» IS THE DEFECT. Unknown drops the key: no line, not a guess."""
    monkeypatch.setattr(process_logging, "active_log_filename", lambda: None)
    assert "log_filename" not in main.get_chain_queue_depth(db=db_session)


def test_it_follows_the_logger_rather_than_a_constant(db_session, loop_here, monkeypatch):
    monkeypatch.setattr(process_logging, "active_log_filename", lambda: "somewhere_else.log")
    assert main.get_chain_queue_depth(db=db_session)["log_filename"] == "somewhere_else.log"


def test_a_worker_of_its_own_is_read_from_its_heartbeat_lap(db_session, beats):
    started = time.time() - 90
    beats({"log_filename": "chain_worker.log", "attached_at": time.time() - 3600,
           "reloaded_at": time.time() - 60,
           "running": [{"rule": "r1", "mapper": "m", "target_table": "t", "rows_in": 3,
                        "started": started}],
           "outcomes": {"r1": {"outcome": "ran", "reason": None, "at": time.time() - 5}}},
          age=2.0)
    out = main.get_chain_queue_depth(db=db_session)

    assert out["loop_in_this_process"] is False, "this process still runs no loop"
    assert out["loop_seen_via"] == "chain_worker_heartbeat"
    assert out["loop_seen_age_seconds"] >= 2.0
    assert out["log_filename"] == "chain_worker.log", "the worker's file, not server.log"
    assert [r["rule"] for r in out["running"]] == ["r1"]
    assert out["running"][0]["running_seconds"] >= 90, "aged at read time, not at write"
    assert out["rule_outcomes"]["r1"]["last_outcome"] == "ran"
    assert 3500 < out["loop_uptime_seconds"] < 3700
    assert 50 < out["mapper_reload_age_seconds"] < 70


@pytest.mark.parametrize("lap, age", [
    ({"log_filename": "chain_worker.log", "outcomes": {}}, 120.0),   # stale
    ({"log_filename": "chain_worker.log"}, 0.0),                     # a lap from before
])
def test_a_stale_or_older_lap_is_not_sight(db_session, beats, lap, age):
    beats(lap, age=age)
    out = main.get_chain_queue_depth(db=db_session)
    assert out["loop_seen_via"] is None and out["loop_seen_age_seconds"] is None
    assert "log_filename" not in out
    assert out["running"] == [] and out["rule_outcomes"] == {}
