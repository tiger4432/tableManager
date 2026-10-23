# -*- coding: utf-8 -*-
"""소유자 10-21 「소급은 좀 끊고 이어 하기 못 하냐? 작업 끊으면 다 돌려야 하네 다시」 · 총괄 fc1e1e385 안 1: a replay's
page carries its number and where it ends; the run's cursor moves in that page's own SUCCESS commit, only from the page
before it; a cut run (`replay.interrupted_runs`) is resumed by a new run that `continued_from` it - its pages after the
cursor, numbered on - or closed by × or a new whole replay of its rule; a resumed whole replay's tally is its first
run's, judged once at its last run.

  cursor     a page that commits moves it from the page before only - out of order or failed, it stays
  cut        ended with a page staged after the cursor, or cut while staging; none of its events waiting
  resume     a new run continuing it, its pages after the cursor's end, numbered on; refused for a run not cut
  close      × on its line or a new whole replay of its rule - cursor and tally cleared, not swept
  sweep      a cut run's tally stays; a resumed chain is judged at its last run over all its runs' rows
  queue      a replay line's pages, and the cut runs with Resume and ×
"""
import json

import pytest

import event_constants
import mapper_sdk
from chain import ingestion_worker as ciw
from chain import keyset_scan
from chain import replay
from database import crud, models, schemas
from database.context import outbox_mode, request_run_id
from database.models import DatabaseOutbox
from utils.payload_helper import get_payload_dict

SRC, DST = "rsm_src", "rsm_dst"
RULE, MAPPER = "rsm_rule", "rsm_mapper"
TABLES = {name: {"business_key": "key_id", "column_types": {"key_id": "string", "grp": "string", "qty": "number"}}
          for name in (SRC, DST)}
TABLES[DST]["map_key_columns"] = ["grp"]
RULES = [{"name": RULE, "trigger_table": SRC, "target_table": DST, "mapper": MAPPER, "is_batch": True,
          "enabled": True, "allow_replace_map": True}]


@pytest.fixture()
def db(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr(ciw, "_RULES_DOCUMENT", {})
    monkeypatch.setattr(ciw, "loaded_chain_rules", lambda: [dict(r) for r in RULES])
    monkeypatch.setattr(replay, "load_rules", lambda: [dict(r) for r in RULES])
    monkeypatch.setattr(replay, "_WHOLE", {})
    monkeypatch.setattr(replay, "_ROOT", {})
    monkeypatch.setattr(keyset_scan, "FIRST_PAGE", 10 ** 6)       # every page its chunk - not grown from a small first
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, MAPPER, lambda _db, payloads, rule=None: {})
    models.ensure_run_columns(db_session.get_bind())
    yield db_session


def _seed(db, keys, grp=None):
    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"key_id": k, "grp": (grp or {}).get(k, k), "qty": 1.0},
                                      source_name="f.csv", updated_by="t", business_key_val=k) for k in keys],
            transaction_id="seed-%s" % keys[0], silent=True))
    db.query(DatabaseOutbox).update({DatabaseOutbox.processed_chain: True, DatabaseOutbox.status: "SUCCESS"})
    db.commit()


def _stage(db, run, params=None, chunk=3, rule=None):
    """The run row and its pages, as the worker's staging does - `continued_from` from its params."""
    params = params or {"rule": RULE}
    if db.query(models.RetroactiveRun).filter_by(run_id=run).first() is None:
        db.add(models.RetroactiveRun(run_id=run, op="chain_replay", params=json.dumps(params), state="running"))
        db.commit()
    token = request_run_id.set(run)
    try:
        stats = replay.replay_rule(db, dict(rule or RULES[0]), apply=True, chunk_size=chunk,
                                   continued_from=params.get("continued_from"))
    finally:
        request_run_id.reset(token)
    db.query(models.RetroactiveRun).filter_by(run_id=run).update({"state": "done", "result": json.dumps(
        {"rows_staged": stats["rows_staged"], "pages_failed": 0})})
    db.commit()
    return stats


def _pages(db, run):
    """{page number: [event]} of the run's staged events."""
    out = {}
    for event in db.query(DatabaseOutbox).order_by(DatabaseOutbox.id):
        payload = get_payload_dict(event) or {}
        if event_constants.run_of(payload) == run and event_constants.replay_page_of(payload):
            out.setdefault(event_constants.replay_page_of(payload)["n"], []).append(event)
    return out


async def _process(db, events):
    gid = ciw.group_id(events[0], RULES)
    await ciw.process_pending_groups(db, [gid], {gid: events}, RULES, None)


def _cursor(db, run):
    from sqlalchemy import text
    return tuple(db.execute(text("SELECT cursor_page, cursor_end, cursor_rows, staged_page, continued_by "
                                 "FROM retroactive_runs WHERE run_id = :r"), {"r": run}).first())


def _set_aside(db, events):
    for event in events:
        event_constants.mark_cancelled(event, "test", "set aside")
    db.commit()


# ---------------------------------------------------------------- cursor
@pytest.mark.anyio
async def test_a_page_moves_its_runs_cursor_only_from_the_page_before_it(db):
    _seed(db, ["K%02d" % i for i in range(12)])
    stats = _stage(db, "c1")
    pages = _pages(db, "c1")
    assert stats["pages"] == 4 and sorted(pages) == [1, 2, 3, 4]
    first = get_payload_dict(pages[1][0])[event_constants.REPLAY_PAGE_KEY]
    assert (first["n"], first["rows"], first["part"], first["parts"]) == (1, 3, 1, 1)
    assert first["end"] == max(get_payload_dict(pages[1][0])["row_ids"])
    assert _cursor(db, "c1")[:4] == (0, None, 0, 4), "staged 4, none committed"
    await _process(db, pages[1])
    assert _cursor(db, "c1")[0] == 1 and _cursor(db, "c1")[2] == 3
    await _process(db, pages[3])
    assert _cursor(db, "c1")[0] == 1, "page 3 committed before page 2 - the cursor stays at 1"
    await _process(db, pages[2])
    assert _cursor(db, "c1")[:3] == (2, get_payload_dict(pages[2][0])[event_constants.REPLAY_PAGE_KEY]["end"], 6)


@pytest.mark.anyio
async def test_a_page_that_fails_holds_the_cursor(db, monkeypatch):
    _seed(db, ["K%02d" % i for i in range(6)])
    _stage(db, "c2")
    pages = _pages(db, "c2")
    await _process(db, pages[1])

    def fails(_db, payloads, rule=None):
        raise ValueError("boom")
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, MAPPER, fails)
    await _process(db, pages[2])
    assert _cursor(db, "c2")[0] == 1


def test_a_page_of_several_events_moves_the_cursor_at_its_last_when_the_others_succeeded(db):
    db.add(models.RetroactiveRun(run_id="c3", op="chain_replay", params=json.dumps({"rule": RULE}), state="done"))
    db.commit()
    replay._cursor_start(db, "c3", None)

    def event(part, status):
        e = DatabaseOutbox(event_uuid="c3-%d" % part, event_type="EDIT", table_name=SRC, status=status,
                           processed_chain=status == "SUCCESS",
                           payload={"run_id": "c3", "replay": True, "row_ids": ["x"],
                                    event_constants.REPLAY_PAGE_KEY: {"n": 1, "end": "e", "rows": 2000,
                                                                      "part": part, "parts": 2}})
        db.add(e)
        db.commit()
        return e
    one = event(1, "FAILED")
    two = event(2, "PENDING")
    assert replay.advance_cursors(db, [one]) == 0, "not the page's last event"
    assert replay.advance_cursors(db, [two]) == 0, "its other event failed"
    event_constants.mark_cancelled(one, "t", "set aside")              # ends SUCCESS, with its mark
    db.commit()
    assert one.status == "SUCCESS" and replay.advance_cursors(db, [two]) == 0, "its other event was set aside"
    one.payload = {k: v for k, v in one.payload.items() if k != event_constants.CANCEL_MARK}
    db.commit()
    assert replay.advance_cursors(db, [two]) == 1 and _cursor(db, "c3")[:3] == (1, "e", 2000)


# ---------------------------------------------------------------- cut
@pytest.mark.anyio
@pytest.mark.parametrize("state, commit, aside, waiting, cut", [
    ("done", 2, True, False, True),        # pages 3-4 set aside (× on its line)
    ("done", 4, False, False, False),      # every page ran
    ("done", 2, False, True, False),       # pages 3-4 still wait - they run
    ("cancelled", 4, False, False, True),  # cut while staging
    ("failed", 2, True, False, True),      # the worker died staging
])
async def test_a_cut_run_is_one_that_ended_short_with_nothing_waiting(db, state, commit, aside, waiting, cut):
    _seed(db, ["K%02d" % i for i in range(12)])
    _stage(db, "x1")
    pages = _pages(db, "x1")
    for n in range(1, commit + 1):
        await _process(db, pages[n])
    if aside:
        _set_aside(db, [e for n in range(commit + 1, 5) for e in pages[n]])
    db.query(models.RetroactiveRun).filter_by(run_id="x1").update({"state": state})
    db.commit()
    found = replay.interrupted_runs(db)
    assert [f["run_id"] for f in found] == (["x1"] if cut else [])
    if cut:
        assert found[0]["pages"] == {"done": commit, "staged": 4, "rows_done": 3 * commit}
        row = db.query(models.RetroactiveRun).filter_by(run_id="x1").one()
        assert (found[0]["op"], found[0]["cursor_end"], found[0]["total_rows"]) \
            == ("chain_replay", _cursor(db, "x1")[1], row.total_rows)
        assert found[0]["cursor_end"] is not None, "canary: a cut run has a committed page's end"


@pytest.mark.anyio
async def test_what_a_cut_runs_pages_wrote_still_draining_does_not_hide_the_cut(db):
    """Its pages' writes stage events carrying its run (board: the sweep judged a cut run «failed» while they drained
    and dropped the tally its Resume counts into)."""
    _seed(db, ["K%02d" % i for i in range(6)])
    _stage(db, "x2")
    pages = _pages(db, "x2")
    await _process(db, pages[1])
    _set_aside(db, pages[2])
    db.query(models.RetroactiveRun).filter_by(run_id="x2").update({"state": "failed"})
    db.add(DatabaseOutbox(event_uuid="woke", event_type="EDIT", table_name=DST, status="PENDING",
                          processed_chain=False, payload={"run_id": "x2", "row_ids": ["r"]}))
    db.commit()
    assert [f["run_id"] for f in replay.interrupted_runs(db)] == ["x2"]
    assert replay.sweep_finished_replays(lambda _l: None, session_factory=lambda: _Kept(db)) == 0
    assert db.query(models.ReplayNamedMap).filter_by(run_id="x2").count() == 1


@pytest.mark.anyio
async def test_a_replay_its_worker_died_staging_is_released_by_the_next_and_shows_cut(db, monkeypatch):
    """총괄 fc1e1e385 답: no × first - the next chain worker releases it (`failed`, why on the row)."""
    from admin import retroactive
    _seed(db, ["K%02d" % i for i in range(6)])
    _stage(db, "d1")
    pages = _pages(db, "d1")
    await _process(db, pages[1])
    _set_aside(db, pages[2])
    db.query(models.RetroactiveRun).filter_by(run_id="d1").update({"state": "running", "runner": "chain/h/1"})
    db.add(models.RetroactiveRun(run_id="d2", op="chain_replay", params=json.dumps({"rule": RULE}),
                                 state="running", runner="chain/h/2"))
    db.add(models.RetroactiveRun(run_id="d3", op="withdraw", params="{}", state="running", runner="sched/h/1"))
    db.commit()
    monkeypatch.setattr(retroactive, "_runner_state", lambda r: "owned" if r == "chain/h/2" else "orphaned")
    monkeypatch.setattr("database.database.SessionLocal", lambda: _Kept(db))   # the run row's own session
    assert replay.interrupted_runs(db) == []
    assert ciw.release_dead_replays(db) == ["d1"]
    states = {r.run_id: (r.state, r.error) for r in db.query(models.RetroactiveRun)}
    assert states["d1"][0] == "failed" and "not alive" in states["d1"][1]
    assert states["d2"][0] == "running" and states["d3"][0] == "running", "a live one, and another op's"
    assert [f["run_id"] for f in replay.interrupted_runs(db)] == ["d1"]


@pytest.mark.anyio
async def test_a_run_released_with_pages_still_waiting_is_judged_only_once_they_ran(db):
    _seed(db, ["K%02d" % i for i in range(6)])
    _stage(db, "w1")
    pages = _pages(db, "w1")
    await _process(db, pages[1])
    db.query(models.RetroactiveRun).filter_by(run_id="w1").update({"state": "failed"})
    db.commit()
    assert replay.sweep_finished_replays(lambda _l: None, session_factory=lambda: _Kept(db)) == 0
    assert db.query(models.ReplayNamedMap).filter_by(run_id="w1").count() == 1, "page 2 still waits"
    await _process(db, pages[2])
    assert replay.sweep_finished_replays(lambda _l: None, session_factory=lambda: _Kept(db)) == 0
    assert [f["run_id"] for f in replay.interrupted_runs(db)] == ["w1"], "failed - cut, kept for its Resume"
    assert db.query(models.ReplayNamedMap).filter_by(run_id="w1").count() == 1


def test_a_run_staged_before_the_cursor_existed_is_never_cut(db):
    db.add(models.RetroactiveRun(run_id="old", op="chain_replay", params=json.dumps({"rule": RULE}),
                                 state="cancelled"))
    db.commit()
    assert replay.interrupted_runs(db) == []


# ---------------------------------------------------------------- resume
@pytest.mark.anyio
async def test_resume_stages_the_pages_after_the_cursor_numbered_on_and_new_rows_at_the_end(db):
    _seed(db, ["K%02d" % i for i in range(12)])
    _stage(db, "r1")
    pages = _pages(db, "r1")
    for n in (1, 2):
        await _process(db, pages[n])
    _set_aside(db, pages[3] + pages[4])
    ran = {r for n in (1, 2) for e in pages[n] for r in get_payload_dict(e)["row_ids"]}
    _seed(db, ["K99"])                                                  # a row after the cut
    answer = replay.resume_run(db, "r1", by="t")
    assert answer["continued_from"] == "r1" and answer["from_page"] == 3
    new = answer["run_id"]
    assert _cursor(db, "r1")[4] == new
    assert json.loads(db.query(models.RetroactiveRun).filter_by(run_id=new).one().params) == {
        "rule": RULE, "continued_from": "r1"}
    with pytest.raises(Exception, match="not a cut replay"):
        replay.resume_run(db, "r1", by="t")
    stats = _stage(db, new, params={"rule": RULE, "continued_from": "r1"})
    resumed = _pages(db, new)
    assert sorted(resumed) == [3, 4, 5] and stats["first_page"] == 3
    staged = [r for n in sorted(resumed) for e in resumed[n] for r in get_payload_dict(e)["row_ids"]]
    model = models.DYNAMIC_TABLES[SRC]
    by_id = {r.row_id: r.business_key_val for r in db.query(model)}
    assert not set(staged) & ran and [by_id[r] for r in staged][-1] == "K99" and len(staged) == 7
    assert _cursor(db, new)[:3] == (2, _cursor(db, "r1")[1], 6), "it starts at the cut run's cursor"


def test_a_run_that_is_not_cut_is_refused_resume(db):
    db.add(models.RetroactiveRun(run_id="n1", op="chain_replay", params=json.dumps({"rule": RULE}), state="running"))
    db.commit()
    with pytest.raises(Exception, match="not a cut replay"):
        replay.resume_run(db, "n1")
    with pytest.raises(Exception, match="unknown run_id"):
        replay.resume_run(db, "nope")


@pytest.mark.anyio
async def test_a_group_by_replay_resumes_after_its_last_keys_first_row_new_keys_at_the_end(db):
    rule = dict(RULES[0], group_by=["grp"])
    groups = {"K%02d" % i: "G%d" % (i // 2) for i in range(8)}          # four keys, two rows each
    _seed(db, list(groups), grp=groups)
    _stage(db, "g1", chunk=4, rule=rule)
    pages = _pages(db, "g1")
    assert sorted(pages) == [1, 2]
    await _process(db, pages[1])
    _set_aside(db, pages[2])
    _seed(db, ["K50", "K51"], grp={"K50": "G9", "K51": "G0"})          # a new key, and a row of an old key
    new = replay.resume_run(db, "g1")["run_id"]
    _stage(db, new, params={"rule": RULE, "continued_from": "g1"}, chunk=4, rule=rule)
    model = models.DYNAMIC_TABLES[SRC]
    grp_of = {r.row_id: r.grp for r in db.query(model)}
    staged = [grp_of[r] for n in sorted(_pages(db, new)) for e in _pages(db, new)[n]
              for r in get_payload_dict(e)["row_ids"]]
    assert staged == ["G2", "G2", "G3", "G3", "G9"], "keys after the cut's last key, the new key at the end"


# ---------------------------------------------------------------- close
@pytest.mark.anyio
async def test_x_on_a_cut_runs_line_closes_it_and_clears_its_tally(db):
    from chain import control
    _seed(db, ["K%02d" % i for i in range(6)])
    _stage(db, "z1")
    pages = _pages(db, "z1")
    await _process(db, pages[1])
    _set_aside(db, pages[2])
    assert db.query(models.ReplayNamedMap).filter_by(run_id="z1").count() == 1
    answer = control.stop_line(db, "z1", "t")
    assert answer["closed"] == "not continued"
    assert replay.interrupted_runs(db) == [] and _cursor(db, "z1")[0] is None
    assert db.query(models.ReplayNamedMap).filter_by(run_id="z1").count() == 0


@pytest.mark.anyio
async def test_a_new_whole_replay_of_the_rule_closes_its_cut_runs(db):
    _seed(db, ["K%02d" % i for i in range(6)])
    _stage(db, "z2")
    pages = _pages(db, "z2")
    _set_aside(db, pages[1] + pages[2])
    assert [f["run_id"] for f in replay.interrupted_runs(db)] == ["z2"]
    _stage(db, "z3")
    assert replay.interrupted_runs(db) == [] and _cursor(db, "z2")[0] is None
    assert db.query(models.ReplayNamedMap).filter_by(run_id="z2").count() == 0


# ---------------------------------------------------------------- sweep
@pytest.mark.anyio
async def test_a_cut_runs_tally_stays_and_a_resumed_chain_is_judged_once_at_its_last_run(db):
    _seed(db, ["K%02d" % i for i in range(9)])
    _stage(db, "s1")
    pages = _pages(db, "s1")
    await _process(db, pages[1])
    _set_aside(db, pages[2] + pages[3])
    lines = []
    assert replay.sweep_finished_replays(lines.append, session_factory=lambda: _Kept(db)) == 0
    assert db.query(models.ReplayNamedMap).filter_by(run_id="s1").count() == 1, "kept for its Resume"
    new = replay.resume_run(db, "s1")["run_id"]
    _stage(db, new, params={"rule": RULE, "continued_from": "s1"})
    for n, events in sorted(_pages(db, new).items()):
        await _process(db, events)
    tally = db.query(models.ReplayNamedMap).filter_by(run_id="s1", scope=replay.TALLY).one()
    assert tally.rows == 9 and db.query(models.ReplayNamedMap).filter_by(run_id=new).count() == 0
    assert replay.sweep_finished_replays(lines.append, session_factory=lambda: _Kept(db)) == 1
    assert lines[-1] == "[ReplaySweep] run %s <- s1 %s: 0 map(s) its batches never named emptied in %s" % (
        new, RULE, DST), lines[-1]
    assert db.query(models.ReplayNamedMap).filter_by(run_id="s1").count() == 0


class _Kept:
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


# ---------------------------------------------------------------- queue
@pytest.mark.anyio
async def test_the_queue_says_a_replays_pages_and_lists_cut_runs_with_resume_and_x(db, client):
    _seed(db, ["K%02d" % i for i in range(9)])
    _stage(db, "q1")
    pages = _pages(db, "q1")
    await _process(db, pages[1])
    answer = client.get("/admin/chain/queue").json()
    [line] = [l for l in answer["waiting_transactions"] if l["run_id"] == "q1"]
    assert line["pages"] == {"done": 1, "staged": 3, "rows_done": 3}
    assert answer["interrupted_runs"] == []
    _set_aside(db, pages[2] + pages[3])
    db.query(models.RetroactiveRun).filter_by(run_id="q1").update({"total_rows": 9})
    db.commit()
    answer = client.get("/admin/chain/queue").json()
    [cut] = answer["interrupted_runs"]
    assert {k: cut[k] for k in ("run_id", "op", "rule", "state", "pages", "total_rows", "resume", "cancel")} == {
        "run_id": "q1", "op": "chain_replay", "rule": RULE, "state": "done",
        "pages": {"done": 1, "staged": 3, "rows_done": 3}, "total_rows": 9,
        "resume": {"run_id": "q1"}, "cancel": {"key": "q1"}}
    assert cut["cursor_end"] == _cursor(db, "q1")[1] is not None          # the run row's own, never empty here
    resumed = client.post("/admin/retroactive/runs/q1/resume")
    assert resumed.status_code == 200 and resumed.json()["from_page"] == 2
    refused = client.post("/admin/retroactive/runs/q1/resume")
    assert refused.status_code == 400 and "not a cut replay" in refused.json()["detail"]
