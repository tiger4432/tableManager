"""소유자 10-21 「리플레이 맵이 다 안 거두네 체인층이 남아 있음」 · 총괄 c67aa93bb ㄴ: a replay stages only the trigger rows there
are now, so a map whose rows all went is never named and keeps its chain layers. A WHOLE replay of a rule that answers for
whole maps (`allow_replace_map` · `allow_retraction`) keeps the maps its batches named (`replay_named_maps`) and, once
every staged row ran, takes back the maps its rule's layers sit on that were never named (`replay.sweep_finished_replays`).

  whole     only a chain_replay with no row_ids, business_keys or limit - a selection never sweeps
  record    a whole replay's batches keep their maps and jobs, and its staged rows count into the tally - no other run's
  judged    a run cancelled, failed, short of staged rows or with a failed page is not swept, says why, and its rows go
  waiting   a run with events still waiting is not judged yet

The sweep itself runs through the chain's write door on a real chain worker - measured on a scratch schema (박스 판).
"""
import json
from types import SimpleNamespace

import pytest

from chain import replay
from database import models

RULE = {"name": "r", "allow_replace_map": True, "target_table": "t", "trigger_table": "s"}


@pytest.fixture(autouse=True)
def _runs_asked_again(monkeypatch):
    monkeypatch.setattr(replay, "_WHOLE", {})


def _run(db, run_id, params, op="chain_replay", state="done", result=None):
    db.add(models.RetroactiveRun(run_id=run_id, op=op, params=json.dumps(params), state=state,
                                 result=json.dumps(result) if result is not None else None))
    db.commit()


def _staged(run_id, rows, rule="r"):
    return SimpleNamespace(payload={"replay": True, "run_id": run_id, "only_rule": rule, "row_ids": ["x"] * rows,
                                    "row_count": rows})


def _rows(db, run_id):
    M = models.ReplayNamedMap
    return sorted((m.scope, m.rows) for m in db.query(M).filter(M.run_id == run_id))


@pytest.mark.parametrize("params, whole", [
    ({"rule": "r"}, "r"),
    ({"rule": "r", "row_ids": ["a"]}, None),
    ({"rule": "r", "business_keys": ["k"]}, None),
    ({"rule": "r", "limit": 10}, None),
])
def test_only_a_whole_chain_replay_sweeps(db_session, params, whole):
    _run(db_session, "w1", params, state="running")
    assert replay.whole_replay_of(db_session, "w1") == whole


def test_another_operation_never_sweeps(db_session):
    _run(db_session, "w2", {"rule": "r"}, op="withdraw", state="running")
    assert replay.whole_replay_of(db_session, "w2") is None


def test_a_whole_replay_keeps_what_its_batches_named_and_counts_its_staged_rows(db_session):
    _run(db_session, "w3", {"rule": "r"}, state="running")
    replay.open_tally(db_session, "w3", RULE)
    batches = [("t", [], {"map_id": "M1"}, None), ("t", [{"x": 1}], {"map_id": "M2"}, None),
               ("t", [], None, ("map_id", "J1"))]
    replay.record_named(db_session, "w3", RULE, [_staged("w3", 3), _staged("w3", 2, rule="other")], batches)
    replay.record_named(db_session, "w3", RULE, [_staged("w3", 4)], batches[:1])
    db_session.commit()
    assert _rows(db_session, "w3") == [(replay.TALLY, 7), ('{"map_id": "J1"}', None), ('{"map_id": "M1"}', None),
                                       ('{"map_id": "M2"}', None)]


@pytest.mark.parametrize("params", [{"rule": "r", "row_ids": ["a"]}, {"rule": "r", "business_keys": ["k"]}])
def test_a_selected_replay_keeps_nothing(db_session, params):
    _run(db_session, "w4", params, state="running")
    replay.open_tally(db_session, "w4", RULE)
    replay.record_named(db_session, "w4", RULE, [_staged("w4", 3)], [("t", [], {"map_id": "M1"}, None)])
    db_session.commit()
    assert _rows(db_session, "w4") == []


def test_a_rule_that_does_not_answer_for_whole_maps_keeps_nothing(db_session):
    _run(db_session, "w5", {"rule": "r"}, state="running")
    plain = dict(RULE, allow_replace_map=False)
    replay.open_tally(db_session, "w5", plain)
    replay.record_named(db_session, "w5", plain, [_staged("w5", 3)], [("t", [], {"map_id": "M1"}, None)])
    db_session.commit()
    assert _rows(db_session, "w5") == []


@pytest.mark.parametrize("state, result, rows, why", [
    ("cancelled", {"rows_staged": 3}, 3, "not swept - the run cancelled"),
    ("failed", None, 3, "not swept - the run failed"),
    ("done", {"rows_staged": 3, "pages_failed": 1}, 3, "not swept - 1 page(s) failed to stage"),
    ("done", {"rows_staged": 5, "pages_failed": 0}, 3, "not swept - the rule ran on 3 of the 5 staged row(s)"),
])
def test_a_run_that_did_not_end_whole_is_judged_without_a_sweep(db_session, state, result, rows, why):
    _run(db_session, "w6", {"rule": "r"}, state="running")
    replay.open_tally(db_session, "w6", RULE)
    replay.record_named(db_session, "w6", RULE, [_staged("w6", rows)], [("t", [], {"map_id": "M1"}, None)])
    run = db_session.query(models.RetroactiveRun).filter_by(run_id="w6").one()
    run.state, run.result = state, json.dumps(result) if result is not None else None
    db_session.commit()
    lines = []
    assert replay.sweep_finished_replays(lines.append, session_factory=lambda: _Kept(db_session)) == 1
    assert lines == ["[ReplaySweep] run w6 r: " + why]
    assert _rows(db_session, "w6") == []


def test_a_run_still_running_or_still_waiting_is_not_judged_yet(db_session):
    _run(db_session, "w7", {"rule": "r"}, state="running")
    replay.open_tally(db_session, "w7", RULE)
    lines = []
    assert replay.sweep_finished_replays(lines.append, session_factory=lambda: _Kept(db_session)) == 0
    run = db_session.query(models.RetroactiveRun).filter_by(run_id="w7").one()
    run.state, run.result = "done", json.dumps({"rows_staged": 0, "pages_failed": 0})
    db_session.add(models.DatabaseOutbox(event_uuid="e-w7", event_type="EDIT", table_name="s", processed_chain=False,
                                         status="PENDING", payload={"run_id": "w7", "row_ids": ["x"]}))
    db_session.commit()
    assert replay.sweep_finished_replays(lines.append, session_factory=lambda: _Kept(db_session)) == 0
    assert lines == [] and _rows(db_session, "w7") == [(replay.TALLY, 0)]


class _Kept:
    """The test's session, not closed by the judge that borrows it."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass
