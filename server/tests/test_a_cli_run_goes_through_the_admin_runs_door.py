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
        "cancellable": True, "restartable": True, "commit_granularity": "",
        "judge": None})


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


@pytest.mark.parametrize("ending", ["done", "cancelled", "failed", "interrupted"])
def test_an_ended_run_takes_its_heartbeat_file_with_it(retro_env, monkeypatch, ending):
    """총괄 f453968fe ⓑ — a file left after a normal end reads as a stale worker forever.
    Only a killed process leaves one, and that one is what marks its run nobody's."""
    import os

    from utils import heartbeat

    def on_page(page):
        if ending == "cancelled":
            retroactive.request_cancel(retro_env, _row(retro_env).run_id)
        elif ending == "failed":
            raise ValueError("boom")
        elif ending == "interrupted":
            raise KeyboardInterrupt

    _probe(monkeypatch, on_page)
    try:
        retroactive.run_here("probe_op", {"pages": 1}, log=lambda *_: None)
    except (retroactive.RunCancelled, ValueError, KeyboardInterrupt):
        pass
    assert _row(retro_env).state != retroactive.RUN_RUNNING
    assert not os.path.exists(heartbeat.heartbeat_path(retroactive.RUN_HERE_HEARTBEAT))


def test_forget_leaves_a_file_another_process_wrote():
    import json
    import os

    from utils import heartbeat

    heartbeat.beat("forget_probe", force=True)
    path = heartbeat.heartbeat_path("forget_probe")
    with open(path, encoding="utf-8") as f:
        mine = json.load(f)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(mine, pid=os.getpid() + 1), f)
    assert heartbeat.forget("forget_probe") is False and os.path.exists(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mine, f)
    assert heartbeat.forget("forget_probe") is True and not os.path.exists(path)


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


def test_resolve_stops_between_its_own_page_commits(retro_env):
    """총괄 7ed82bd78 — no checkpoint meant no resume, not no place to stop: each page
    commits, so the boundary before the next page is where a screen cancel lands."""
    from chain import replay
    from tests.test_retroactive_admin import _seed

    _seed(retro_env, "retro_test_target", [{"part_no": "P%d" % i, "note": "n"}
                                           for i in range(3)])
    asked = []

    def stop_after_one_page(rows_so_far):
        asked.append(rows_so_far)
        return rows_so_far >= 1

    s = replay.recompute_display_values(retro_env, "retro_test_target", apply=True,
                                        chunk_size=1, checkpoint=stop_after_one_page,
                                        log=lambda *_: None)
    assert (s["pages"], s["rows_scanned"], s["stopped"]) == (1, 1, True)
    assert asked == [0, 1]
    whole = replay.recompute_display_values(retro_env, "retro_test_target", apply=True,
                                            chunk_size=1, log=lambda *_: None)
    assert (whole["rows_scanned"], whole["stopped"]) == (3, False), "a re-run starts over"


def test_two_claims_at_once_leave_one_running(monkeypatch):
    """총괄 f453968fe ⓒ — the gate check and the write are one transaction under one lock.
    A holds the lock with its running row not yet committed; B's claim must wait, then see
    A's row and refuse - not read an empty table and write a second running row."""
    import threading

    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from tests.support.isolated_pg import scratch_connect_args, scratch_schema

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    scratch = scratch_schema("assy_pytest_gate_lock_f453")
    with _declared_as_test_database(url):
        maker = create_engine(url, poolclass=NullPool)
        try:
            with maker.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
                conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        except OperationalError as exc:
            pytest.skip("PostgreSQL is not reachable: %s" % str(exc).strip().splitlines()[0])
        engine = create_engine(url, poolclass=NullPool,
                               connect_args=scratch_connect_args(scratch))
        try:
            models.RetroactiveRun.__table__.create(engine)
            monkeypatch.setattr("database.database.SessionLocal", sessionmaker(bind=engine))
            answer, done = {}, threading.Event()

            def b():
                try:
                    answer["run_id"] = retroactive.claim("withdraw", {})
                except retroactive.RetroactiveRefused as exc:
                    answer["refused"] = str(exc)
                finally:
                    done.set()

            a = engine.connect()
            tx = a.begin()
            try:
                a.execute(text("SELECT pg_advisory_xact_lock(hashtext(:n))"),
                          {"n": retroactive.GATE_LOCK_NAME})
                a.execute(text("INSERT INTO retroactive_runs (run_id, op, params, state) "
                               "VALUES ('held', 'withdraw', '{}', 'running')"))
                threading.Thread(target=b, daemon=True).start()
                waited = not done.wait(0.5)
                tx.commit()
            finally:
                # A must end before the cleanup drops the schema, or the drop waits on it.
                if tx.is_active:
                    tx.rollback()
                a.close()
            assert waited, "B did not wait for A's lock: %s" % answer
            assert done.wait(10)
            assert "held" in answer.get("refused", ""), answer
            with engine.connect() as c:
                assert c.execute(text("SELECT count(*) FROM retroactive_runs "
                                      "WHERE state = 'running'")).scalar() == 1
        finally:
            with maker.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            engine.dispose()
            maker.dispose()


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


def test_the_record_says_which_os_account_ran_it(retro_env, monkeypatch):
    """총괄 d34247b3d ㉢ — a CLI run's `requested_by` was empty. It is the OS account that ran
    it; an account that cannot be read stays absent rather than invented."""
    import getpass

    _probe(monkeypatch, lambda page: None)
    monkeypatch.setattr(getpass, "getuser", lambda: "op_kim")
    retroactive.run_here("probe_op", {"pages": 1}, log=lambda *_: None)
    assert _row(retro_env).requested_by == "op_kim"

    retro_env.query(models.RetroactiveRun).delete()
    retro_env.commit()
    monkeypatch.setattr(getpass, "getuser", lambda: (_ for _ in ()).throw(OSError()))
    retroactive.run_here("probe_op", {"pages": 1}, log=lambda *_: None)
    assert _row(retro_env).requested_by is None
