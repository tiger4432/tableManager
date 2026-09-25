# -*- coding: utf-8 -*-
"""총괄 8a1f32f99 ① · 3d03bc819 · 45410384c · 80d61ae05 — a CLI's write runs in the CLI's own
process, and through the admin button's run record, gate, cancel and ending: it shows in
the run list, a closed gate refuses it, a screen cancel stops it between pages, and a
killed one leaves a lock the screen can release."""
import json

import pytest

from admin import retroactive
from database import models
from tests.test_retroactive_admin import retro_env  # noqa: F401  - its session and tables


def _probe(monkeypatch, on_page):
    """An operation whose pages the test drives. `on_page(page)` runs before each page's
    checkpoint, the one place a real operation can stop."""
    def run(db, params, log, control=None):
        hook = retroactive._checkpoint(control)
        done = 0
        for page in range(params.get("pages", 3)):
            on_page(page)
            done += 1
            if hook and hook(done):
                break
        retroactive._final_progress(control, done, {"pages_done": done, "own": "answer"})
        return {"pages_done": done}

    monkeypatch.setitem(retroactive.OPERATIONS, "probe_op", {
        "label": "probe", "what_is_missing": "", "count": None, "run": run,
        "params": [retroactive._p("pages", required=False, kind="int")],
        "cli": "", "cli_only": [], "deletes": None, "reads_as": "number",
        "cancellable": True, "restartable": True, "commit_granularity": ""})


def _row(db):
    return db.query(models.RetroactiveRun).filter(
        models.RetroactiveRun.op == "probe_op").one()


def test_it_is_a_record_the_list_shows_and_no_daemon_can_claim(retro_env, monkeypatch):
    seen = {}

    def on_page(page):
        if page == 0:
            row = _row(retro_env)
            seen.update(state=row.state, gate=retroactive.gate_refusal(retro_env),
                        queued=retroactive.next_queued(retro_env, "probe_op"),
                        owner=retroactive._runner_state(row.runner), run_id=row.run_id)

    _probe(monkeypatch, on_page)
    out = retroactive.run_here("probe_op", {"pages": 2}, log=lambda *_: None)

    row = _row(retro_env)
    assert seen["state"] == retroactive.RUN_RUNNING and seen["queued"] is None
    assert seen["run_id"] in seen["gate"], "the admin button must be blocked while it runs"
    assert seen["owner"] == "owned" and row.runner.startswith(
        retroactive.RUN_HERE_HEARTBEAT + "/")
    assert (row.state, json.loads(row.result)) == (retroactive.RUN_DONE, {"pages_done": 2})
    assert out["stats"] == {"pages_done": 2, "own": "answer"}
    assert retroactive.runs(retro_env)[0]["run_id"] == row.run_id
    assert not retro_env.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.event_type == retroactive.RUN_EVENT_TYPE).count(), \
        "no doorbell - a daemon must not pick it up"


def test_a_closed_gate_refuses_before_anything_is_written(retro_env, monkeypatch):
    from datetime import datetime, timezone

    _probe(monkeypatch, lambda page: None)
    retro_env.add(models.RetroactiveRun(
        run_id="held-by-another", op="chain_replay", params="{}",
        state=retroactive.RUN_RUNNING, runner="scheduler/h/42",
        started_at=datetime.now(timezone.utc)))
    retro_env.commit()
    monkeypatch.setattr("utils.heartbeat.read_all",
                        lambda *a, **k: {"scheduler": {"pid": 42, "stale": False}})

    with pytest.raises(retroactive.RetroactiveRefused, match="held-by-another"):
        retroactive.run_here("probe_op", {}, log=lambda *_: None)
    assert not retro_env.query(models.RetroactiveRun).filter(
        models.RetroactiveRun.op == "probe_op").count()


def test_a_screen_cancel_stops_it_between_pages(retro_env, monkeypatch):
    def on_page(page):
        if page == 0:
            retroactive.request_cancel(retro_env, _row(retro_env).run_id)

    _probe(monkeypatch, on_page)
    with pytest.raises(retroactive.RunCancelled):
        retroactive.run_here("probe_op", {"pages": 3}, log=lambda *_: None)
    row = _row(retro_env)
    assert (row.state, json.loads(row.result)) == (retroactive.RUN_CANCELLED,
                                                   {"pages_done": 1})


def test_ctrl_c_ends_the_record_and_reaches_the_terminal(retro_env, monkeypatch):
    def on_page(page):
        if page == 1:
            raise KeyboardInterrupt

    _probe(monkeypatch, on_page)
    with pytest.raises(KeyboardInterrupt):
        retroactive.run_here("probe_op", {}, log=lambda *_: None)
    row = _row(retro_env)
    assert row.state == retroactive.RUN_CANCELLED and "interrupted" in row.error
    assert retroactive.gate_refusal(retro_env) is None, "a stopped CLI must not hold the lock"


def test_a_failure_is_recorded_and_its_own_exception_reaches_the_terminal(retro_env,
                                                                          monkeypatch):
    def on_page(page):
        raise ValueError("boom")

    _probe(monkeypatch, on_page)
    with pytest.raises(ValueError, match="boom"):
        retroactive.run_here("probe_op", {}, log=lambda *_: None)
    assert (_row(retro_env).state, _row(retro_env).error) == (retroactive.RUN_FAILED, "boom")


def test_resolve_is_an_operation_the_admin_counts_and_a_cli_runs(retro_env):
    """총괄 b39604b58 — R3 (recompute shown values) is a retroactive operation: counted
    exactly on a table the budget covers, and run through the same record."""
    counted = retroactive.count(retro_env, "resolve", {"table": "retro_test_target"})
    assert (counted["affected"], counted["absence"], counted["count_kind"]) == (
        0, retroactive.ABSENCE_TRULY_NONE, retroactive.COUNT_EXACT)

    out = retroactive.run_here("resolve", {"table": "retro_test_target"},
                               log=lambda *_: None)
    row = retro_env.query(models.RetroactiveRun).filter(
        models.RetroactiveRun.op == "resolve").one()
    assert (row.state, json.loads(row.result)["cells_changed"]) == (retroactive.RUN_DONE, 0)
    assert out["stats"]["table"] == "retro_test_target"


def test_a_killed_one_is_nobodys_and_a_cancel_releases_it(retro_env, monkeypatch):
    """The CLI died without its ending: its heartbeat goes stale, and the gate says the
    cancel releases the lock rather than 「cannot be judged」."""
    said = {}

    def on_page(page):
        if page == 0:
            monkeypatch.setattr("utils.heartbeat.read_all", lambda *a, **k: {
                retroactive.RUN_HERE_HEARTBEAT: {"pid": -1, "stale": True}})
            said["gate"] = retroactive.gate_refusal(retro_env)

    _probe(monkeypatch, on_page)
    retroactive.run_here("probe_op", {"pages": 1}, log=lambda *_: None)
    assert "NOT alive" in said["gate"] and "RELEASES" in said["gate"]
