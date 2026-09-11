# -*- coding: utf-8 -*-
"""S-142 ②. A dead supervisor's record stops speaking for the living.

Measured on this box before the change: `/health` said, in `problems`, 「supervisor status is
145365s old - the supervisor itself is not running」 — and in the SAME response gave every
worker `supervisor_state: "running"` with pids 31940, 18776 and 7956. The only python
process was 42240. The record had been written 09-10 07:55, about forty hours earlier.

🔴 SO THE DEFECT WAS NOT 「A LEFTOVER FILE」 BUT 「ONE ANSWER CONTRADICTING ITSELF」. An
operator reads the workers table, sees a state and a pid, and concludes the process is
alive; only someone who cross-checks the problems list learns otherwise.

The rule (판정 297): the file's age governs EVERY value that came out of it, and what is
missing is reported as missing rather than invented. Only a heartbeat can say a thing runs.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import health as health_mod                                          # noqa: E402

NOW = 1_000_000.0
FRESH = {
    "supervisor_pid": 100,
    "updated_at": NOW - 1.0,
    "children": {"Chain": {"heartbeat": "chain", "state": "running", "pid": 31940,
                           "restarts": 2, "uptime_seconds": 50.0}},
}
STALE = dict(FRESH, updated_at=NOW - 145_365.0)
BEATS = {"chain": {"age_seconds": 1.0, "stale": False, "note": "parsed f.csv"}}


def _health(supervisor_status, heartbeats=None):
    payload, _status = health_mod.compute_health(
        db_result={"status": "ok"},
        heartbeats=BEATS if heartbeats is None else heartbeats,
        supervisor_status=supervisor_status,
        outbox_result={"status": "ok"},
        stale_after=60.0,
        now=NOW,
    )
    return payload


# ---------------------------------------------------------------------------
# Gate ⓐ — a stale record supplies nothing
# ---------------------------------------------------------------------------

def test_a_stale_record_gives_no_worker_a_state_or_a_pid():
    """🔴 THESE THREE ARE WHAT AN OPERATOR READS AS 「it is alive」."""
    worker = _health(STALE)["checks"]["workers"]["chain"]
    for field in ("supervisor_state", "pid", "restarts"):
        assert field not in worker, (field, worker)


def test_absent_is_absent_not_false_or_zero():
    """⛔ `restarts: 0` and `pid: None` would be INVENTED values — 「nothing was said」 and
    「it said zero」 are different answers, and this surface is read by machines."""
    worker = _health(STALE)["checks"]["workers"]["chain"]
    assert worker.get("restarts", "ABSENT") == "ABSENT"
    assert worker.get("pid", "ABSENT") == "ABSENT"


def test_a_stale_record_publishes_no_children():
    supervisor = _health(STALE)["checks"]["supervisor"]
    assert supervisor["children"] == {}
    assert supervisor["status"] == "stale"


# ---------------------------------------------------------------------------
# Gate ⓑ — 🔴 THE REGRESSION LINE: a fresh record is untouched
# ---------------------------------------------------------------------------

def test_a_fresh_record_still_carries_everything_it_carried_before():
    worker = _health(FRESH)["checks"]["workers"]["chain"]
    assert worker["supervisor_state"] == "running"
    assert worker["pid"] == 31940
    assert worker["restarts"] == 2
    assert _health(FRESH)["checks"]["supervisor"]["children"]["Chain"]["pid"] == 31940


# ---------------------------------------------------------------------------
# Gate ⓒ — a heartbeat still speaks for itself
# ---------------------------------------------------------------------------

def test_a_worker_alive_on_its_heartbeat_alone_is_still_ok():
    """The supervisor is gone, but `chain` is beating from inside the live server — which
    is the ONE thing that can still say it runs."""
    worker = _health(STALE)["checks"]["workers"]["chain"]
    assert worker["status"] == "ok"
    assert worker["note"] == "parsed f.csv", "the beat's own words survive"


# ---------------------------------------------------------------------------
# Gate ⓓ — 🔴 the two halves of one answer agree
# ---------------------------------------------------------------------------

def test_problems_and_workers_stop_contradicting_each_other():
    """🔴 THE GATE THAT MATTERS (판정 297). Before: `problems` said the supervisor was not
    running while `workers` reported `running` and a pid for each child."""
    payload = _health(STALE)
    said_not_running = any("not running" in p for p in payload["problems"])
    claims_running = [name for name, w in payload["checks"]["workers"].items()
                      if w.get("supervisor_state") == "running"]
    assert said_not_running, payload["problems"]
    assert claims_running == [], claims_running


# ---------------------------------------------------------------------------
# The roster is not a worker
# ---------------------------------------------------------------------------

def test_the_roster_file_is_not_read_as_a_heartbeat(tmp_path, monkeypatch):
    """⚠️ It is published INTO the heartbeat directory on purpose, so a walk of that
    directory picks it up and invents a process named `_roster`. It surfaced the moment a
    stale supervisor stopped supplying the expected list and the disk fallback took over."""
    import json

    from utils import heartbeat as hb

    monkeypatch.setattr(hb, "heartbeat_dir", lambda: str(tmp_path))
    (tmp_path / "chain.json").write_text(
        json.dumps({"name": "chain", "at": NOW}), encoding="utf-8")
    (tmp_path / hb.ROSTER_FILENAME).write_text(
        json.dumps({"processes": {"chain": NOW}}), encoding="utf-8")

    assert sorted(hb.read_all(now=NOW)) == ["chain"]
    # ...and it is still readable AS a roster, which is the point of it living there
    assert sorted(hb.read_roster()) == ["chain"]
