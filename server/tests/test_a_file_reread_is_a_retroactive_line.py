# -*- coding: utf-8 -*-
"""A file re-read is a retroactive line (소유자 10-28 «ㄱ» · C 렉 판: 파일 110 «Read all again» 이 한 표를 한 줄로 세움):
a press writes a done run for each (table, source) it hands, the watcher reads the files under the newest, so their
chain events carry its run_id - queued apart, paced, given within the retroactive share of the slots. The run holds no
gate (총괄 a4d135a06 retired the run that did).

    seat                                    gate
    retry-failed + the watcher (DECOUPLED)  the read's events carry the press's run; the first read's carry none
    retry-failed read in the request        the same run, the same events
    a second press on the same table        the newer run takes what is read after it
    the gate                                a re-read run standing refuses no retroactive run
    the op                                  file_reread, never started from the retroactive form
    the dispatcher                          retroactive lines hold at most their share; a live line takes the rest
    a retroactive line's batch              cut at its rows - the chain's first, then the page time at its last
                                            batch's seconds a row (총괄 10-28); a live line's at the chain's
    a re-read's own writes                  events of REREAD_EVENT_ROWS rows; every other write's of 1,000
"""
import asyncio
import os
from types import SimpleNamespace

import pytest

import directory_watcher
import paths
import run_watcher
from admin import retroactive
from chain import slots
from database import models
from ingestion import reread
from tests.test_a_failed_external_file_retries_on_its_own_handler import env  # noqa: F401
from tests.test_files_are_read_again_by_the_watcher import _the_watcher_reads

TABLE = "rt_parts"


def _retry(Session, **params):
    import main

    db = Session()
    try:
        asked = dict(log_id=None, folder=None, preview=False, statuses="SUCCESS", since=None, until=None)
        return asyncio.run(main.retry_failed_file_ingestion(**dict(asked, **params), db=db))
    finally:
        db.close()


def _runs_of_events(Session):
    db = Session()
    try:
        return [run for (run,) in db.query(models.DatabaseOutbox.run_id).filter(
            models.DatabaseOutbox.table_name == TABLE).order_by(models.DatabaseOutbox.id)]
    finally:
        db.close()


def _rows_of_events(Session):
    db = Session()
    try:
        return [len(payload.get("row_ids") or ()) for (payload,) in db.query(models.DatabaseOutbox.payload).filter(
            models.DatabaseOutbox.table_name == TABLE).order_by(models.DatabaseOutbox.id)]
    finally:
        db.close()


def _reread_runs(Session):
    db = Session()
    try:
        return [(r.run_id, r.state, r.params) for r in db.query(models.RetroactiveRun).filter(
            models.RetroactiveRun.op == retroactive.FILE_REREAD_OP).order_by(models.RetroactiveRun.queued_at)]
    finally:
        db.close()


def _changed(Session, qty):
    """The archived parts.csv with a new stock, and 449 parts more - a re-read that changes nothing stages no event,
    and its events are cut finer than 450 rows."""
    db = Session()
    try:
        where = db.query(models.FileChecklist.filepath).filter_by(filename="parts.csv").scalar()
    finally:
        db.close()
    with open(where, "w", encoding="utf-8", newline="") as f:
        f.write("part_no,category,stock_qty\nP-1,Cap,%d\n" % qty + "".join("P-%d,Cap,1\n" % n for n in range(2, 451)))


@pytest.fixture(name="read_once")
def fixture_read_once(env, monkeypatch):  # noqa: F811
    """The watcher's handlers, and parts.csv read once as a file that lands is - a live read, no run."""
    w = directory_watcher.WorkspaceWatcher(str(env["workspace"]))
    w.discover_and_watch()
    monkeypatch.setattr(run_watcher, "workspace_watcher", w)
    raws = w.raws_root_for(TABLE)
    path = os.path.join(raws, "parts.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("part_no,category,stock_qty\nP-1,Cap,5\n")
    w.handlers_by_raw_path[raws].process_with_retry(path, delay=0.01)
    first = _runs_of_events(env["Session"])
    assert first and set(first) == {None}, "control: a first read is a live line"
    _changed(env["Session"], 7)
    return env, len(first)


def test_a_retry_the_watcher_reads_is_a_line_of_the_presses_run(read_once, monkeypatch):
    env, live = read_once
    monkeypatch.setenv("DECOUPLED", "True")
    _retry(env["Session"])
    (run, state, params), = _reread_runs(env["Session"])
    _the_watcher_reads(env["Session"])

    after = _runs_of_events(env["Session"])[live:]
    assert after and set(after) == {run}, after
    assert (state, params) == (retroactive.RUN_DONE, reread._run_params(TABLE, "raws"))
    assert max(_rows_of_events(env["Session"])[live:]) == reread.REREAD_EVENT_ROWS


def test_a_retry_read_in_the_request_is_the_same_line(read_once, monkeypatch):
    env, live = read_once
    monkeypatch.delenv("DECOUPLED", raising=False)
    monkeypatch.setattr(paths, "WORKSPACE_DIR", str(env["workspace"]))
    said = _retry(env["Session"])
    (run, _state, _params), = _reread_runs(env["Session"])

    assert "Success: 1" in said["message"], said
    after = _runs_of_events(env["Session"])[live:]
    assert after and set(after) == {run}, after
    assert max(_rows_of_events(env["Session"])[live:]) == reread.REREAD_EVENT_ROWS


def _press_again(Session):
    """A second press on the pair - the door's own call, as Read now of another of its files makes it."""
    db = Session()
    try:
        return reread.open_runs(db, [(TABLE, "raws")])[(TABLE, "raws")]
    finally:
        db.close()


def test_a_second_press_before_the_first_drained_is_the_same_line(read_once, monkeypatch):
    """총괄 10-28: two runs of one pair were two lines a slot ran by turns, the first's tail after the second's - and
    decide's re-count of old keys reads that order. A press while the pair's files or its run's events still wait
    takes that run again: one line, one order."""
    env, live = read_once
    monkeypatch.setenv("DECOUPLED", "True")
    _retry(env["Session"])
    (first, *_), = _reread_runs(env["Session"])
    assert _press_again(env["Session"]) == first, "its file waits to be read"
    _the_watcher_reads(env["Session"])
    assert _press_again(env["Session"]) == first, "its events wait in the chain"

    assert [run for run, *_ in _reread_runs(env["Session"])] == [first]
    assert set(_runs_of_events(env["Session"])[live:]) == {first}


def test_a_press_after_the_run_drained_opens_a_new_one(read_once, monkeypatch):
    env, _live = read_once
    monkeypatch.setenv("DECOUPLED", "True")
    monkeypatch.setattr(paths, "WORKSPACE_DIR", str(env["workspace"]))      # the second press finds the file in its root
    _retry(env["Session"])
    _the_watcher_reads(env["Session"])
    db = env["Session"]()
    try:
        db.query(models.DatabaseOutbox).update({"processed_chain": True})      # the chain ran them
        db.commit()
    finally:
        db.close()
    (first, *_), = _reread_runs(env["Session"])
    _changed(env["Session"], 9)
    before = len(_runs_of_events(env["Session"]))
    _retry(env["Session"])
    _the_watcher_reads(env["Session"])

    runs = [run for run, *_ in _reread_runs(env["Session"])]
    assert len(runs) == 2 and runs[0] == first, runs
    assert set(_runs_of_events(env["Session"])[before:]) == {runs[1]}, "read under the newest"


def _states(Session):
    db = Session()
    try:
        return {(row.table_name, row.filename): row.status for row in db.query(models.FileChecklist)}
    finally:
        db.close()


def test_a_cross_on_a_reread_line_stops_that_tables_reread_and_no_other(read_once, monkeypatch):
    """Owner 10-08 «체인 멈춤은 stop_line 하나»: × on the line stops the re-read - its files still waiting are put back,
    so none of them lines up again; another (table, source)'s re-read waits on."""
    from chain import control
    from ingestion import checkpoint

    env, live = read_once
    monkeypatch.setenv("DECOUPLED", "True")
    monkeypatch.setattr(slots, "stop_slot", lambda db, key: None)
    _retry(env["Session"])
    (run, *_), = _reread_runs(env["Session"])
    db = env["Session"]()
    try:   # two other re-reads waiting: another table under the same source word, the same table under another source
        for table, name, source in (("void_obs", "x.json", "raws"), (TABLE, "y.csv", str(env["external"]))):
            checkpoint.note_file(db, table, str(env["external"] / name), status=reread.REREAD_STATUS,
                                 status_before="SUCCESS", source=source)
        db.commit()
        assert set(_states(env["Session"]).values()) == {reread.REREAD_STATUS}, "canary: all three wait"
        said = control.stop_line(db, run, "tester")
    finally:
        db.close()

    assert said["reread"]["count"] == 1, said
    assert _states(env["Session"]) == {(TABLE, "parts.csv"): "SUCCESS", ("void_obs", "x.json"): reread.REREAD_STATUS,
                                       (TABLE, "y.csv"): reread.REREAD_STATUS}
    _the_watcher_reads(env["Session"])
    assert _runs_of_events(env["Session"])[live:] == [], "nothing of the stopped re-read lines up again"


def test_a_reread_run_standing_refuses_no_retroactive_run(read_once, monkeypatch):
    env, _live = read_once
    monkeypatch.setenv("DECOUPLED", "True")
    _retry(env["Session"])
    _the_watcher_reads(env["Session"])
    assert _reread_runs(env["Session"]), "canary: a re-read run stands"
    db = env["Session"]()
    try:
        assert retroactive.gate_refusal(db) is None
        assert retroactive.in_flight(db) is None
    finally:
        db.close()


def test_a_read_now_and_a_glob_s_read_these_open_one_run_a_press(env, monkeypatch):  # noqa: F811
    """The other two doors: Read now (one file) and a glob's Read these (its files a page at a time) - one run for the
    press, not one a page."""
    from runtime import system_reload

    handed = []
    monkeypatch.setattr(reread, "hand_files", lambda db, table, source, files: (
        handed.append(list(files)) or {"ids": [len(handed)], "being_read": []}))
    monkeypatch.setattr(reread, "read_now_owners", lambda db, path: {
        "path": path, "on_disk": True, "owners": [{"table": TABLE, "source": "raws", "why_not": ""}]})
    monkeypatch.setattr(reread, "glob_matched", lambda table, source, pattern: (
        "root", None, [("a.csv", "/r/a.csv"), ("b.csv", "/r/b.csv")], 2))
    monkeypatch.setattr(reread, "MARK_PAGE", 1)
    monkeypatch.setattr(system_reload, "publish_reload", lambda *a, **k: None)
    monkeypatch.setattr(reread, "SessionLocal", env["Session"], raising=False)
    monkeypatch.setattr("database.database.SessionLocal", env["Session"])
    db = env["Session"]()
    try:
        reread.read_now(db, "/r/a.csv", apply=True)
    finally:
        db.close()
    assert len(_reread_runs(env["Session"])) == 1

    job = {"table": "ext_t", "source": "/share", "pattern": "*.csv", "ids": [], "being_read": 0}
    reread._hand_glob(job, None)
    assert len(handed) == 3, "canary: the glob handed its two files a page each"
    runs = _reread_runs(env["Session"])
    assert [params for _run, _state, params in runs[1:]] == [reread._run_params("ext_t", "/share")]


def test_the_op_is_a_record_never_started_from_the_retroactive_form():
    assert retroactive.FILE_REREAD_OP != "reread_files", "the retired op's running rows held the gate (10-11)"
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate(retroactive.FILE_REREAD_OP, {"table": TABLE})
    assert str(refused.value) == retroactive.FILE_REREAD_STARTED_BY


class _Slot:
    def __init__(self, index):
        self.index, self.pid, self.line, self.ready, self.leaving = index, 100 + index, None, False, False

    def ask(self, line, rows=None):
        self.line, self.ready, self.rows = line, False, rows
        return True

    def release(self):
        self.line = None


def _line(key, run):
    return {"line": key, "run": run, "orders": False, "events": [], "touches": {"t_" + key}}


def _given(monkeypatch, waiting, settings, held=()):
    """One tick of a two-slot dispatcher over `waiting` -> {slot: the line it holds}."""
    from chain import control

    pool = slots.SlotPool(spawn=lambda index: None)
    pool.slots = {1: _Slot(1), 2: _Slot(2)}
    for index, line in held:
        pool.slots[index].line, pool.slots[index].ready = slots._held(line), False
    monkeypatch.setattr(control, "paused", lambda: None)
    monkeypatch.setattr(slots, "chain_slots", lambda settings=None: 2)
    monkeypatch.setattr("parsers.directory_watcher.load_ingestion_settings", lambda: settings)
    monkeypatch.setattr(pool, "_size", lambda wanted: setattr(pool, "_wanted", wanted))
    monkeypatch.setattr(pool, "_read_answers", lambda db: False)
    monkeypatch.setattr(pool, "_givable", lambda db, rules, held, wanted: (list(waiting), 0))
    pool.tick(None, [], notified=True)
    return {index: slot.line and slot.line["line"] for index, slot in pool.slots.items()}


def test_retroactive_lines_hold_their_share_of_the_slots_and_a_live_line_the_rest(monkeypatch):
    runs = [_line("run-a", True), _line("run-b", True)]
    assert _given(monkeypatch, runs, {}) == {1: "run-a", 2: None}, "unset: all slots but one"
    assert _given(monkeypatch, runs, {slots.RETROACTIVE_SLOTS_SETTING: 2}) == {1: "run-a", 2: "run-b"}
    assert _given(monkeypatch, runs + [_line("live", False)], {}) == {1: "live", 2: "run-a"}, "live first"
    # a slot running a retroactive batch holds the share: the free slot takes the live line, never a second run
    assert _given(monkeypatch, [_line("run-b", True), _line("live", False)], {},
                  held=[(1, _line("run-a", True))]) == {1: "run-a", 2: "live"}
    assert _given(monkeypatch, [_line("run-b", True)], {}, held=[(1, _line("run-a", True))]) == {1: "run-a", 2: None}


# --- a retroactive line's batch, in rows (총괄 10-28 ㄱ: the page time · the line's last batch · the chain's budget first)

def test_the_next_batch_is_the_page_time_at_the_last_batch_s_seconds_a_row(monkeypatch):
    import pacing

    monkeypatch.setattr(pacing, "page_seconds", lambda path=None: 3.0)
    assert slots.next_row_budget(2000, 4.0) == 1500
    assert slots.next_row_budget(2000, 4.0, target=2) == 1000
    assert slots.next_row_budget(20000, 0.5) == 20000, "never above the chain's budget"
    assert slots.next_row_budget(1, 100.0) == 1
    assert slots.next_row_budget(10, 0.0) is None
    assert slots.next_row_budget(0, 1.0) is None, "nothing ran: the line keeps its budget"
    assert slots.next_row_budget(200, 0.15) == 400, "at most double"


def test_the_dispatcher_keeps_a_retroactive_line_s_rows_wherever_its_slot(monkeypatch):
    """A line moves between slots between batches - its rows go with the dispatcher, not the slot; a drained line
    starts over; a live line is never given rows, whatever is kept under its key."""
    import queue

    from chain import control

    pool = slots.SlotPool(spawn=lambda index: None)
    pool.slots = {1: _Slot(1), 2: _Slot(2)}
    for slot in pool.slots.values():
        slot.answers = queue.Queue()
    waiting = []
    monkeypatch.setattr(control, "paused", lambda: None)
    monkeypatch.setattr(slots, "chain_slots", lambda settings=None: 2)
    monkeypatch.setattr("parsers.directory_watcher.load_ingestion_settings", lambda: {})
    monkeypatch.setattr(pool, "_size", lambda wanted: setattr(pool, "_wanted", wanted))
    monkeypatch.setattr(pool, "_givable", lambda db, rules, held, wanted: (list(waiting), 0))
    monkeypatch.setattr(pool, "_rest_by_pace", lambda db, key, now: None)

    def tick(*lines):
        waiting[:] = lines
        pool.tick(None, [], notified=True)
        return {slot.line["line"]: slot.rows for slot in pool.slots.values() if slot.line is not None}

    def answer(index, outcome, rows=None):
        pool.slots[index].answers.put({"line": pool.slots[index].line["line"], "outcome": outcome, "rows": rows})

    pool._rows["live"] = 5
    assert tick(_line("run", True), _line("live", False)) == {"live": None, "run": None}, "first: the chain's"
    answer(1, slots.RAN)
    answer(2, slots.RAN, 700)
    assert tick() == {"live": None, "run": 700}, "its slot keeps it"
    pool.slots[1].line = pool.slots[2].line = None                              # both let go: the line moves
    assert tick(_line("run", True)) == {"run": 700}
    assert pool.slots[1].line["line"] == "run", "canary: another slot"
    answer(1, slots.DRAINED)
    assert tick(_line("run", True)) == {"run": None}, "drained: the chain's again"


def _batch(monkeypatch, Session, ask, ran, read_rows=(300, 300, 300), took=2.0):
    """One slot batch of `ask` over waiting events of `read_rows` rows, of which the batch marks the first `ran` done,
    taking `took` s -> (the row budget drain_events was given, the batch's answer)."""
    import pacing
    from chain import control, ingestion_worker
    from utils import heartbeat

    db = Session()
    try:
        db.query(models.DatabaseOutbox).delete()
        for n in read_rows:
            db.add(models.DatabaseOutbox(event_uuid=os.urandom(8).hex(), event_type="UPDATE", table_name="t",
                                         payload={"row_ids": list(range(n)), "row_count": n}))
        db.commit()
    finally:
        db.close()
    given = []
    clock = iter([0.0, took, took])

    async def step(db, stage, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def drain(db, evs, rules, factory, batch_wake_ts=None, row_budget=None):
        given.append(row_budget)
        for event in evs:
            event._parsed_payload = event.payload
        ids = [event.id for event in evs[:ran]]
        db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id.in_(ids)).update(
            {"processed_chain": True}, synchronize_session=False)
        db.commit()
        return False

    monkeypatch.setattr(control, "paused", lambda: None)
    monkeypatch.setattr(control, "with_rules_off", lambda rules: rules)
    monkeypatch.setattr(ingestion_worker, "_step_beating", step)
    monkeypatch.setattr(ingestion_worker, "reload_at_boundary", lambda who, seen: (False, seen))
    monkeypatch.setattr(ingestion_worker, "pending_chain_events", lambda db, line=None: db.query(
        models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain == False)  # noqa: E712
                        .order_by(models.DatabaseOutbox.id).all())
    monkeypatch.setattr(ingestion_worker, "drain_events", drain)
    monkeypatch.setattr("database.database.SessionLocal", Session)
    monkeypatch.setattr(heartbeat, "record_lap", lambda *a, **k: None)
    monkeypatch.setattr(slots, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(pacing, "page_seconds", lambda path=None: 3.0)
    outcome, _rules, _seen, rows = asyncio.run(slots._run_batch(ask, [], None))
    return given[0], (outcome, rows)


def test_a_slot_cuts_a_retroactive_batch_at_its_rows_and_a_live_batch_at_the_chain_s(env, monkeypatch):  # noqa: F811
    S = env["Session"]
    assert _batch(monkeypatch, S, {"line": "live", "run": False, "rows": 40}, 3) == (None, (slots.RAN, None))
    # first: the chain's budget; 900 rows ran in 2 s -> 3 s is 1,350
    assert _batch(monkeypatch, S, {"line": "r", "run": True, "rows": None}, 3) == (20000, (slots.RAN, 1350))
    # its rows: one 300-row event of the 900 ran in 2 s -> 450
    assert _batch(monkeypatch, S, {"line": "r", "run": True, "rows": 500}, 1) == (500, (slots.RAN, 450))


def test_a_short_batch_that_ran_little_does_not_size_the_next_past_double(env, monkeypatch, caplog):  # noqa: F811
    """C 10-28 (16:25:28): a batch cut at 247 rows ran a cheap event in 0.146 s, the budget was counted as run, and the
    next was 3 x 247 / 0.146 = 5,292 rows - it took 26.9 s. What ran is what the batch marked done, and the next is at
    most double it; a batch that ran nothing keeps the line's budget."""
    S = env["Session"]
    ask = {"line": "r", "run": True, "rows": 247}
    assert _batch(monkeypatch, S, ask, 1, read_rows=(200, 200), took=0.146) == (247, (slots.RAN, 400))
    assert _batch(monkeypatch, S, ask, 0, read_rows=(200, 200), took=0.146) == (247, (slots.RAN, None))
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Chain] line r:")]
    assert said == ["[Chain] line r: this batch ran 200 ingested rows in 0.1 s - the next covers ~400 ingested rows.",
                    "[Chain] line r: this batch ran 0 ingested rows in 0.1 s - the next covers ~247 ingested rows."]


def test_drain_events_cuts_at_the_row_budget_and_a_rule_s_rows_per_run_still_cuts_under_it(monkeypatch):
    from chain import ingestion_worker

    kept = []
    monkeypatch.setattr(ingestion_worker, "group_events", lambda evs, rules: (kept.append(len(evs)) or ([], {})))
    monkeypatch.setattr(ingestion_worker, "merge_consecutive_groups", lambda order, groups, rules: (order, groups))

    async def none(*_a, **_k):
        return False

    monkeypatch.setattr(ingestion_worker, "process_pending_groups", none)

    def drain(row_budget, cap=None):
        monkeypatch.setattr(ingestion_worker, "_rows_cap", lambda event, rules: cap)
        events = [SimpleNamespace(id=i, event_type="UPDATE", table_name="t",
                                  payload={"row_ids": list(range(300)), "row_count": 300}) for i in range(3)]
        asyncio.run(ingestion_worker.drain_events(None, events, [], None, row_budget=row_budget))
        return kept.pop()

    assert drain(None) == 3, "control: the chain's budget holds the three"
    assert drain(650) == 2
    assert drain(650, cap=300) == 1, "a rule's rows_per_run under the line's budget"


def test_a_reread_s_own_writes_are_events_of_its_rows_and_every_other_write_of_a_thousand(env):  # noqa: F811
    from database import context
    from database.database import stage_collapsed_event

    staged = []
    session = SimpleNamespace(add=staged.append)
    db = env["Session"]()
    try:
        run = reread.open_runs(db, [(TABLE, "raws")])[(TABLE, "raws")]
        with reread.reading_under(db, TABLE, "raws"):
            assert (context.request_run_id.get(), context.request_event_rows.get()) == (run, reread.REREAD_EVENT_ROWS)
            stage_collapsed_event(session, "UPDATE", TABLE, list(range(450)))
        under = [len(e.payload["row_ids"]) for e in staged]
        staged.clear()
        stage_collapsed_event(session, "UPDATE", TABLE, list(range(1450)))
    finally:
        db.close()
    assert under == [200, 200, 50]
    assert [len(e.payload["row_ids"]) for e in staged] == [1000, 450]
    assert (context.request_run_id.get(), context.request_event_rows.get()) == (None, None)
