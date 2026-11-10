"""A line waiting for a table names the work holding it (owner 11-10): «waiting for t» + «slot 2 · r9 · 0 s» /
«replay 77 · 0 s». The holder writes what it holds on its own claim (`ingestion_worker._holding_the_tables`, the
replay sweep passes the same on_held); so a beat carries EVERY open claim (`works`), not the oldest only (총괄 11-10) -
a replay judged on the chain's beat beside a group must not hide the group from the readers that act on its facts.

    reader x branch         one work      line + replay (line oldest)      replay oldest
    pause cancel pids       line pid      line pid                         line pid
    db pid -> work          line          line                             line
    stall watch table       line's        line's                           line's
    queue line facts        line's stage  line's stage                     line's stage

Real claims on real beat files through `read_all` - no cell left out.
"""
import json
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import event_constants
from chain import ingestion_worker, table_locks
from database import models
from utils import heartbeat

LINE_PID, LINE_STAGE = 4242, "mapper · m"
BRANCHES = ("one work", "line + replay", "replay oldest")


@pytest.fixture(autouse=True)
def beats(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / (name + ".json")))
    monkeypatch.setattr(heartbeat, "MIN_WRITE_INTERVAL_SEC", 0, raising=False)


@contextmanager
def claim(name, what, act=None):
    """A claim held open on a thread of its own - `act()` runs on that thread inside it."""
    opened, done, failed = threading.Event(), threading.Event(), []

    def run():
        try:
            with heartbeat.work_claim(name, what):
                if act is not None:
                    act()
                heartbeat.beat(name, force=True)
                opened.set()
                done.wait(10)
        except BaseException as error:  # noqa: BLE001 - said by the test's own thread
            failed.append(error)
            opened.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    opened.wait(10)
    assert not failed, failed
    try:
        yield
    finally:
        done.set()
        thread.join(10)


def _line(stage=LINE_STAGE):
    heartbeat.note_work(db_pid=LINE_PID, line_keys=["line-1"], table="t_line")
    heartbeat.progress(stage)


@contextmanager
def _branch(branch):
    if branch == "one work":
        with claim("chain", "tx line", _line):
            yield
    elif branch == "line + replay":
        with claim("chain", "tx line", _line):
            time.sleep(0.02)
            with claim("chain", "replay 77"):
                yield
    else:
        with claim("chain", "replay 77"):
            time.sleep(0.02)
            with claim("chain", "tx line", _line):
                yield


class _Db:
    def __init__(self):
        self.pids = None

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def execute(self, _sql, params):
        self.pids = params["pids"]
        return []

    def commit(self):
        pass


def _pause_pids():
    from chain import control
    db = _Db()
    control.cancel_running_group(db)
    return db.pids


def _pid_work():
    import db_waits
    return db_waits.work_on(LINE_PID)


def _stall_table():
    from runtime import stall_watch
    return stall_watch.workers()[1]


def _line_stage():
    from runtime import running
    return running.chain_lines_running()["line-1"]["stage"]


READERS = {"pause cancel pids": (_pause_pids, [LINE_PID]),
           "db pid -> work": (_pid_work, "chain · tx line"),
           "stall watch table": (_stall_table, "t_line"),
           "queue line facts": (_line_stage, LINE_STAGE)}


@pytest.mark.parametrize("branch", BRANCHES)
@pytest.mark.parametrize("reader", sorted(READERS))
def test_every_reader_finds_the_line_in_every_branch(reader, branch):
    read, expected = READERS[reader]
    with _branch(branch):
        oldest = heartbeat.read_all()["chain"]["work"]["what"]
        assert oldest == ("replay 77" if branch == "replay oldest" else "tx line")   # the branch is what it says
        assert read() == expected


def test_work_is_the_first_of_works_and_counts_them():
    with _branch("replay oldest"):
        beat = heartbeat.read_all()["chain"]
        assert [w["what"] for w in beat["works"]] == ["replay 77", "tx line"]
        assert beat["work"] == dict(beat["works"][0], open=2)


def _waiting():
    _line(table_locks.WAITING_FOR + "t")


def _held_by():
    from runtime import running
    facts = running.chain_lines_running()["line-1"]
    return facts["held_by"], event_constants.chain_state_of(False, None, running=facts)


def test_a_slot_holding_the_table_is_named_with_its_rule_and_seconds():
    def holder():
        heartbeat.note_work(rule_run={"rule": "r9", "started": time.time()})
        ingestion_worker._holding_the_tables(["s", "t"])

    with claim("chain-slot-1", "tx line", _waiting), claim("chain-slot-2", "tx other", holder):
        said, state = _held_by()
    assert said == "slot 2 · r9 · 0 s"
    assert state["state"] == event_constants.CHAIN_STATE_WAITING_FOR_TABLE
    assert state["why"]["table"] == "t" and state["why"]["held_by"] == said


def test_a_replay_holding_the_table_on_the_chain_beat_is_named_by_its_run():
    with claim("chain-slot-1", "tx line", _waiting), \
            claim("chain", "replay 77", lambda: ingestion_worker._holding_the_tables(["t"])):
        said, _state = _held_by()
    assert said == "replay 77 · 0 s"


def test_no_one_holding_it_names_no_one_and_another_table_is_not_it():
    with claim("chain-slot-1", "tx line", _waiting), \
            claim("chain-slot-2", "tx other", lambda: ingestion_worker._holding_the_tables(["u"])):
        said, state = _held_by()
    assert said is None and state["why"]["held_by"] is None


def test_the_seconds_are_since_it_held_them():
    from runtime import running
    holders = [("chain-slot-3", {"what": "tx", "facts": {"holding": {"tables": ["t"], "since": 100.0}}})]
    assert running.held_by("t", holders, now=112.6) == "slot 3 · 12 s"


def test_the_replay_sweep_holds_its_tables_inside_a_claim_on_the_chain_beat(db_session, monkeypatch):
    """The sweep's hold, as a waiting line reads it: a claim «replay <run>» on the chain's beat whose facts say the
    tables - the group's own on_held, and no on_wait (a pause cancels no sweep)."""
    from chain import replay
    from tests.test_a_whole_replay_takes_back_the_maps_it_never_named import RULE, _Kept, _run, _staged

    seen = {}

    @contextmanager
    def hold(db, tables, on_wait=None, on_held=None):
        seen["on_wait"] = on_wait
        on_held(sorted(t for t in tables if t))
        yield

    monkeypatch.setattr(replay, "_WHOLE", {})
    monkeypatch.setattr(table_locks, "hold", hold)
    monkeypatch.setattr(replay, "find_rule", lambda name: RULE)
    monkeypatch.setattr(replay, "_sweep", lambda db, rule, root: seen.setdefault("claims", heartbeat.open_claims())
                        and 0)
    _run(db_session, "w9", {"rule": "r"}, state="running")
    replay.open_tally(db_session, "w9", RULE)
    replay.record_named(db_session, "w9", RULE, [_staged("w9", 3)], [("t", [], {"map_id": "M1"}, None)])
    run = db_session.query(models.RetroactiveRun).filter_by(run_id="w9").one()
    run.state, run.result = "done", json.dumps({"rows_staged": 3, "pages_failed": 0})
    db_session.commit()
    replay.sweep_finished_replays(lambda _line: None, session_factory=lambda: _Kept(db_session))
    [mine] = [c for c in seen["claims"] if c["name"] == ingestion_worker.GROUP_BEAT]
    assert mine["what"] == "replay w9" and mine["facts"]["holding"]["tables"] == ["s", "t"]
    assert seen["on_wait"] is None
    assert [c for c in heartbeat.open_claims() if c["what"] == "replay w9"] == []
