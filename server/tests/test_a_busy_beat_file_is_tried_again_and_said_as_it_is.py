# -*- coding: utf-8 -*-
"""A beat file busy on Windows (lead 10-28 ㄷ, 10-29 ㄱ): a reader's open and a writer's replace of the same file refuse
each other there (PermissionError) - 7-11 ms idle, up to 478 ms with every CPU busy (measured). Both sides wait once
through `heartbeat._when_free`. A beat still unread is not a stopped one: `read_all` ages it by its file (mtime), keeps
`error` and no pid, and every reader follows - C's ingestion run served one 503 «chain slot … unreadable heartbeat».

    branch          the file                                     read_all
    read            fresh, reads                                 stale False
    unread fresh    refuses the open, written just now           stale False, error, pid None
    unread old      refuses the open, written an hour ago        stale True, error
    absent          none                                         no entry

Every reader of `read_all` x every branch below, no cell left out; then `runner_state`'s readers - «unknown» does nothing.
"""
import asyncio
import json
import os
import socket
import time
from types import SimpleNamespace

import pytest

from tests.test_health_endpoint import fresh, run, running, supervisor_status
from utils import heartbeat

BRANCHES = ("read", "unread fresh", "unread old", "absent")


@pytest.fixture(name="put")
def fixture_put(tmp_path, monkeypatch):
    """put(name, branch, payload): the beat file of that branch."""
    beats, refused, real = tmp_path / "beats", set(), heartbeat._load
    beats.mkdir(exist_ok=True)
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(beats))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(beats / (name + ".json")))
    monkeypatch.setattr(heartbeat, "BUSY_WAIT_SECONDS", 0)

    def load(path):
        if os.path.basename(path) in refused:
            raise PermissionError(13, "Permission denied", path)
        return real(path)

    monkeypatch.setattr(heartbeat, "_load", load)

    def put(name, branch, payload):
        if branch == "absent":
            return
        path = beats / (name + ".json")
        ts = time.time() - (3600 if branch == "unread old" else 0)
        path.write_text(json.dumps(dict(payload, ts=ts)))
        os.utime(path, (ts, ts))
        if branch != "read":
            refused.add(path.name)

    return put


def _busy(monkeypatch, module, name, times):
    real, left = getattr(module, name), [times]

    def busy(*args, **kwargs):
        if left[0]:
            left[0] -= 1
            raise PermissionError(13, "Permission denied")
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, busy)


def test_a_busy_replace_is_tried_once_more_and_the_beat_is_written(put, tmp_path, monkeypatch):
    _busy(monkeypatch, os, "replace", 1)
    assert heartbeat._write("scheduler", {"pid": 1, "ts": 1.0}) is True
    assert json.loads((tmp_path / "beats" / "scheduler.json").read_text())["pid"] == 1


def test_a_busy_open_is_tried_once_more_and_the_beat_is_read(put, monkeypatch):
    put("scheduler", "read", {"pid": 7})
    _busy(monkeypatch, heartbeat, "_load", 1)
    assert heartbeat.read_all()["scheduler"]["pid"] == 7


# ---- every reader of read_all ----------------------------------------------------------------------------------------

SUP = supervisor_status({"Scheduler": running("scheduler")})
SLOT = "chain-slot-1"


def _read_all(put, b, _mp):
    put("w", b, {"pid": 7})
    entry = heartbeat.read_all().get("w")
    return None if entry is None else (entry["stale"], "error" in entry, entry["pid"])


def _health_worker(put, b, _mp):
    put("scheduler", b, {"pid": 101, "beats": 5})
    payload, code = run(hbs=heartbeat.read_all(), sup=SUP)
    return payload["checks"]["workers"]["scheduler"]["status"], code


def _health_slot(put, b, _mp):
    put(SLOT, b, {"pid": 7, "beats": 5})
    payload, code = run(hbs=dict(heartbeat.read_all(), scheduler=fresh()), sup=SUP)
    return (payload["checks"]["workers"].get(SLOT) or {}).get("status"), code


def _health_on_demand(put, b, _mp):
    put("retroactive", b, {"pid": 7})
    payload, code = run(hbs=dict(heartbeat.read_all(), scheduler=fresh()), sup=SUP)
    return (payload["checks"]["workers"].get("retroactive") or {}).get("status"), code


class _Db:
    """A session that says its dialect and records what it was asked to cancel."""

    def __init__(self, dialect):
        self.dialect, self.pids = dialect, None

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect))

    def execute(self, _sql, params):
        self.pids = params["pids"]
        return []

    def commit(self):
        pass


def _loops(put, b, _mp):
    from runtime import loops

    put("retroactive", b, {"pid": 7})
    [item] = [i for i in loops.runtime_loops(_Db("sqlite"))["loops"] if i["process"] == "retroactive"]
    return item.get("alive"), item.get("status")


def _cancel_running_group(put, b, _mp):
    from chain import control

    now = time.time()
    put(SLOT, b, {"pid": 7, "work": {"open": 1, "oldest_facts": {"db_pid": 55}, "oldest_progress_ts": now,
                                     "oldest_started_ts": now}})
    db = _Db("postgresql")
    control.cancel_running_group(db)
    return db.pids


def _ledger_warning(put, b, mp):
    from chain import ingestion_worker

    said = []
    mp.setattr(ingestion_worker.logger, "warning", lambda *a, **k: said.append(a))
    put("ledger", b, {"pid": 7})
    asyncio.run(ingestion_worker._say_if_no_ledger_beats(after=0))
    return bool(said)


def _holding(put, b, mp):
    from chain import slots

    mp.setattr(slots, "HOLDING_READ_SECONDS", 0)
    put(SLOT, b, {"pid": 7, "laps": {slots.HOLDS: {"line": "K", "at": time.time()}}})
    return slots.holding("K")


def _stop_retroactive_child(put, b, _mp):
    from runtime import process_supervisor

    put("retroactive", b, {"pid": os.getpid()})
    return process_supervisor.stop_retroactive_child(grace=0.1)


def _chain_lines_running(put, b, _mp):
    from chain import slots
    from runtime import running as running_now

    put(SLOT, b, {"pid": 7, "laps": {slots.HOLDS: {"line": "K", "at": time.time()}}})
    return sorted(running_now.chain_lines_running())


def _chain_sight(put, b, _mp):
    from runtime import running as running_now

    put("chain", b, {"pid": 7, "laps": {"chain": {"outcomes": {}, "at": time.time()}}})
    return running_now.chain_sight()["via"]


def _running_now(put, b, mp):
    from runtime import running as running_now

    seen = []
    for name in ("_chain", "_retroactive", "_ingestions"):
        mp.setattr(running_now, name, lambda *a, **k: [])
    mp.setattr(running_now, "_collectors", lambda pid: seen.append(pid) or [])
    put("scheduler", b, {"pid": 7})
    running_now.running_now(None, sight={})
    return seen


def _end_process(put, b, mp):
    from admin import retroactive
    from scripts import stop_retroactive

    mp.setattr(stop_retroactive.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="ok", stderr="", returncode=0))
    put(retroactive.RUN_HERE_HEARTBEAT, b, {"pid": os.getpid()})
    stop_retroactive._end_process("%s/%s/%s" % (retroactive.RUN_HERE_HEARTBEAT, socket.gethostname(), os.getpid()))
    return os.path.exists(heartbeat.heartbeat_path(retroactive.RUN_HERE_HEARTBEAT))


def _another_process_beats(put, b, _mp):
    put("chain", b, {"pid": os.getppid()})
    return heartbeat.another_process_beats("chain") is not None


def _runner_state(put, b, _mp):
    from runtime import running as running_now

    put("chain", b, {"pid": 7})
    return heartbeat.runner_state("chain/h/7"), running_now.run_state("chain/h/7")


#         reader                       read                       unread fresh                  unread old                     absent
READERS = {
    "read_all":                (_read_all,               (False, False, 7),         (False, True, None),          (True, True, None),            None),
    "health, worker":          (_health_worker,          ("ok", 200),               ("unreadable", 200),          ("wedged", 503),               ("missing", 503)),
    "health, chain slot":      (_health_slot,            ("ok", 200),               ("unreadable", 200),          ("wedged", 503),               (None, 200)),
    "health, on demand":       (_health_on_demand,       ("running", 200),          ("running", 200),             ("orphaned", 200),             (None, 200)),
    "loops table":             (_loops,                  (True, "running"),         (True, "running"),            (False, "orphaned"),           (None, None)),
    "cancel_running_group":    (_cancel_running_group,   [55],                      None,                         None,                          None),
    "no-ledger warning":       (_ledger_warning,         False,                     False,                        True,                          True),
    "slots.holding":           (_holding,                (1, 7),                    "unread",                     "unread",                      None),
    "stop_retroactive_child":  (_stop_retroactive_child, "not_ours",                "unreadable",                 "none",                        "none"),
    "chain_lines_running":     (_chain_lines_running,    ["K"],                     [],                           [],                            []),
    "chain_sight":             (_chain_sight,            "chain_worker_heartbeat",  None,                         None,                          None),
    "running_now collectors":  (_running_now,            [7],                       [None],                       [None],                        [None]),
    "stop_retroactive script": (_end_process,            False,                     True,                         True,                          False),
    "another_process_beats":   (_another_process_beats,  True,                      False,                        False,                         False),
    "runner_state, run_state": (_runner_state,           ("owned", "running"),      ("unknown", "unknown"),       ("orphaned", "orphaned"),      ("orphaned", "orphaned")),
}


@pytest.mark.parametrize("branch", BRANCHES)
@pytest.mark.parametrize("reader", sorted(READERS))
def test_every_reader_of_a_beat_answers_each_branch(put, monkeypatch, reader, branch):
    answer, *expected = READERS[reader]
    assert answer(put, branch, monkeypatch) == expected[BRANCHES.index(branch)]


def test_an_unread_slot_beat_is_said_with_its_error_and_its_files_age(put):
    put(SLOT, "unread fresh", {"pid": 7})
    payload, code = run(hbs=dict(heartbeat.read_all(), scheduler=fresh()), sup=SUP)
    [said] = payload["problems"]
    assert code == 200 and said == payload["checks"]["workers"][SLOT]["detail"]
    assert said.startswith("chain slot '%s': unreadable heartbeat: PermissionError" % SLOT)
    assert "its file was written 0." in said and said.endswith("(threshold 60s)")


def test_an_unread_beat_inside_the_startup_grace_is_a_worker_starting(put):
    put("scheduler", "unread old", {"pid": 101})
    payload, code = run(hbs=heartbeat.read_all(),
                        sup=supervisor_status({"Scheduler": running("scheduler", uptime=5.0)}))
    assert code == 200 and payload["problems"] == []
    assert payload["checks"]["workers"]["scheduler"]["status"] == "starting"


# ---- runner_state's readers: «unknown» does nothing ------------------------------------------------------------------

from tests.test_a_formula_on_a_column_is_a_join_onto_its_own_row import fixture_db  # noqa: E402,F401


def _run_row(db):
    from datetime import datetime, timezone

    from database import models

    db.add(models.RetroactiveRun(run_id="r1", op="chain_replay", params="{}", state="running", runner="chain/h/7",
                                 started_at=datetime.now(timezone.utc)))
    db.commit()


def _released(db):
    from chain import ingestion_worker

    return ingestion_worker.release_dead_replays(db)


def _cancelled(db):
    from admin import retroactive

    answer = retroactive.request_cancel(db, "r1")
    return answer["state"], answer["released"]


def _gate_refusal(db):
    from admin import retroactive

    said = retroactive.gate_refusal(db)
    return next(word for word in ("NOT alive", "did not read just now", "is alive") if word in said)


def _queue_view(db):
    from admin import retroactive

    return [run["owner"] for run in retroactive.queue_view(db)["orphaned"]]


#         reader                     read                          unread fresh                  unread old              absent
OWNERS = {
    "release_dead_replays": (_released,     [],                           [],                           ["r1"],                 ["r1"]),
    "request_cancel":       (_cancelled,    ("cancel_requested", False),  ("cancel_requested", False),  ("failed", True),       ("failed", True)),
    "gate_refusal":         (_gate_refusal, "is alive",                   "did not read just now",      "NOT alive",            "NOT alive"),
    "queue_view orphaned":  (_queue_view,   [],                           ["unknown"],                  ["orphaned"],           ["orphaned"]),
}


def test_the_file_tables_route_reads_the_watchers_sweeps_only_off_a_beat_that_read(db, put, monkeypatch):
    import main
    from ingestion import reread
    from parsers import directory_watcher

    monkeypatch.setattr(main, "_kept_count", lambda *a, **k: None)
    monkeypatch.setattr(reread, "validated_sources", lambda: ({}, []))
    lap = {directory_watcher.SWEEP_LAP_PREFIX + "s": {"table": "zz_t", "source": "s", "state": "idle", "at": 1.0}}
    said = {}
    for branch in BRANCHES:
        put(directory_watcher.HEARTBEAT_NAME, branch, {"pid": 7, "laps": lap})
        data = main.get_file_ingestion_tables(db)["data"]
        said[branch] = [bool(e.get("sweep")) for row in data if row["table_name"] == "zz_t" for e in row["sources"]]
        path = heartbeat.heartbeat_path(directory_watcher.HEARTBEAT_NAME)          # the next branch starts with none
        if os.path.exists(path):
            os.remove(path)
    assert said == {"read": [True], "unread fresh": [], "unread old": [], "absent": []}


@pytest.mark.parametrize("branch", BRANCHES)
@pytest.mark.parametrize("reader", sorted(OWNERS))
def test_a_run_whose_runner_beat_did_not_read_is_left_as_it_is(db, put, reader, branch):
    answer, *expected = OWNERS[reader]
    _run_row(db)
    put("chain", branch, {"pid": 7})
    assert answer(db) == expected[BRANCHES.index(branch)]
