# -*- coding: utf-8 -*-
"""총괄 b3a4334db (소유자 「소급 잡이 하나인데 하나만 떠야지」 · 「배치별로 다뜨는듯」): one retroactive job
is ONE line in the chain queue, whatever transactions its operations and the chain's writes went
out in.

The job's identity is the run (`retroactive_runs.run_id`): every event staged while a run runs
carries it (`admin.retroactive._run_to_the_end` opens it, `database._outbox_envelope` stamps it),
and what the chain writes because the run's events woke a rule carries it on
(`ingestion_worker._replay_ask` -> both write seats). The queue folds by the run when there is one,
by the transaction when not - in SQL, BEFORE the list is cut, and the cap is on lines.
"""
import json
import os
import sys
import types
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                                # noqa: E402
from admin import retroactive                                         # noqa: E402
from chain import ingestion_worker as worker, replay, rule_run        # noqa: E402
from database import database as dbmod, models                        # noqa: E402
from database.context import request_run_id                           # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

from test_a_chain_write_reads_as_the_chain_whatever_its_layer import (  # noqa: E402,F401
    PA, PB, _bumpers, _drain, _events, _finish, _pending, _write, fixture_db)

RUN = "b3a4334dc0de"


# ------------------------------------------------------------------ the run rides the events

@pytest.mark.parametrize("cascade", [False, True])
def test_a_runs_trigger_events_and_what_they_woke_carry_the_run(db, monkeypatch, cascade):
    _write(db, PA, [{"k": "K", "n": "0"}])
    _finish(db, _pending(db))
    rules = _bumpers(opt_in=True)
    monkeypatch.setattr(replay, "load_rules", lambda: rules)

    out = retroactive.execute(
        {"run_id": RUN, "op": "chain_replay",
         "params": dict({"rule": "pp_a_to_b"}, **({"cascade": True} if cascade else {}))},
        log=lambda m: None)
    assert out["status"] == "ok", out["error"]
    staged = [get_payload_dict(e) for e in _pending(db)]
    assert staged and {event_constants.run_of(p) for p in staged} == {RUN}

    _drain(db, rules, max_depth=3)

    wrote = [p for p in _events(db, PA) + _events(db, PB) if p.get("source_name") == rule_run.CHAIN_SOURCE]
    assert wrote, "the replay wrote nothing, so the run's carry is not asked"
    assert {event_constants.run_of(p) for p in wrote} == {RUN}, wrote


def test_a_write_outside_a_run_carries_no_run(db):
    _write(db, PA, [{"k": "K", "n": "0"}])
    _drain(db, _bumpers(opt_in=False))

    events = _events(db, PA) + _events(db, PB)
    assert len(events) >= 2 and not any(event_constants.RUN_KEY in p for p in events)


def test_a_rules_own_write_carries_the_run_its_envelope_is_given(db):
    model = models.DYNAMIC_TABLES[PA]
    with rule_run.chain_envelope(depth=0, woken_by_a_replay=True, run=RUN):
        dbmod.stage_event(db, "EDIT", PA, model(row_id="r-env", business_key_val="K", k="K"))
        dbmod.stage_collapsed_event(db, "EDIT", PA, ["r-env"])
    staged = [o.payload for o in db.new if isinstance(o, models.DatabaseOutbox)]
    assert len(staged) == 2 and {p.get(event_constants.RUN_KEY) for p in staged} == {RUN}
    db.rollback()


def test_every_run_ends_inside_its_run(db):
    out = retroactive._run_to_the_end(
        "r-ends-here", "probe", {"run": lambda db, params, log, control: request_run_id.get()},
        {}, lambda m: None, types.SimpleNamespace(stopped=False, run_id="r-ends-here"))
    assert out["result"] == "r-ends-here"
    assert request_run_id.get() is None, "the run leaked past its end"


def test_two_runs_groups_are_never_folded_into_one(db):
    rules = [dict(r, **{"max_group_rows": 1000}) for r in _bumpers(opt_in=False)]

    def replayed(n, run):
        return types.SimpleNamespace(id=n, table_name=PA, event_type="EDIT", payload={
            "row_ids": ["r%d" % n], "only_rule": "pp_a_to_b",
            event_constants.REPLAY_KEY: True, event_constants.RUN_KEY: run})

    groups = {"t1": [replayed(1, "run-one")], "t2": [replayed(2, "run-two")],
              "t3": [replayed(3, "run-two")]}
    order, _ = worker.merge_consecutive_groups(["t1", "t2", "t3"], groups, rules)
    assert order == ["t1", "t2"], "two runs' groups folded into one would name one run"


# ------------------------------------------------------------------ the queue: one job, one line

def _queue(client):
    return client.get("/admin/chain/queue",
                      headers={"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}).json()


def _event(db, payload, event_type="EDIT", table="raw_table_1"):
    db.add(models.DatabaseOutbox(event_uuid=str(uuid.uuid4()), table_name=table,
                                 event_type=event_type, payload=payload, processed_chain=False))
    db.flush()


def _lines(body, **match):
    return [g for g in body["waiting_transactions"]
            if all(g.get(k) == v for k, v in match.items())]


def test_one_run_is_one_line_whatever_its_transactions(client, db_session):
    run = "a1b2c3d4e5f6"
    db_session.add(models.RetroactiveRun(run_id=run, op="chain_replay", state="running"))
    _event(db_session, {"transaction_id": "replay_x", "row_ids": ["a"] * 300, "row_count": 300,
                        event_constants.RUN_KEY: run})
    _event(db_session, {"transaction_id": "chain_replay_x", event_constants.RUN_KEY: run})
    _event(db_session, {"transaction_id": "chain_group_by:k", event_constants.RUN_KEY: run})
    _event(db_session, {"run_id": run, "op": "chain_replay", "params": {},
                        "requested_by": "kim"},
           event_type=event_constants.EVENT_RETROACTIVE_RUN,
           table=retroactive.RUN_EVENT_TABLE)
    _event(db_session, {"transaction_id": "tx-plain-b3a"})

    body = _queue(client)
    [line] = _lines(body, run_id=run)
    assert line["op"] == "chain_replay" and line["transaction_id"] is None
    assert (line["events"], line["rows"]) == (4, 303), line
    assert [r["run_id"] for r in line["retroactive"]] == [run]
    assert line["tables"] == ["raw_table_1"], "the control row's placeholder is not a table"
    [plain] = _lines(body, transaction_id="tx-plain-b3a")
    assert (plain["run_id"], plain["events"], plain["rows"]) == (None, 1, 1)


def test_the_fold_comes_before_the_cut(client, db_session):
    """⚰️ It cut the first 200 EVENTS and folded after: a job of 250 hid every job behind it."""
    run = "f01dbe4c0000"
    for _ in range(250):
        _event(db_session, {"transaction_id": "replay_big", event_constants.RUN_KEY: run})
    _event(db_session, {"transaction_id": "tx-behind-the-big-job"})

    body = _queue(client)
    assert [g["events"] for g in _lines(body, run_id=run)] == [250]
    assert _lines(body, transaction_id="tx-behind-the-big-job"), "the job behind it is hidden"


def test_a_cut_list_says_how_many_lines_there_are(client, db_session):
    for n in range(201):
        _event(db_session, {"transaction_id": "tx-many-%03d" % n})

    listed = _queue(client)["listed"]
    assert listed["lines"] == listed["cap"] == 200
    assert listed["capped"] is True and listed["lines_total"] >= 201


def test_a_control_row_left_as_text_is_its_own_line_and_still_says_what_it_is(client, db_session):
    """Rows written before the control payload became an object stay text in the outbox; the
    SQL cannot read their run, so each is its own line - and still says which job it is."""
    _event(db_session, json.dumps({"run_id": "legacy0000a1", "op": "withdraw",
                                   "requested_by": "kim"}),
           event_type=event_constants.EVENT_RETROACTIVE_RUN, table=retroactive.RUN_EVENT_TABLE)

    lines = [g for g in _queue(client)["waiting_transactions"]
             if any(r.get("run_id") == "legacy0000a1" for r in g.get("retroactive", []))]
    assert len(lines) == 1 and lines[0]["transaction_id"].startswith("(no tx · outbox#")
    assert lines[0]["retroactive"][0]["op"] == "withdraw"


@pytest.mark.pg
def test_the_fold_reads_the_same_in_postgres(pg_session):
    """The fold is SQL now - JSONB `->>`, a text cast, a window count. The SQLite tests above do
    not speak PostgreSQL's dialect, and the box does."""
    import main
    from fastapi.testclient import TestClient

    run = "9a5f01d00001"
    pg_session.add(models.RetroactiveRun(run_id=run, op="chain_replay", state="running"))
    _event(pg_session, {"transaction_id": "replay_pg", "row_ids": ["a"] * 40, "row_count": 40,
                        event_constants.RUN_KEY: run})
    _event(pg_session, {"transaction_id": "chain_replay_pg", event_constants.RUN_KEY: run})
    _event(pg_session, {"transaction_id": "tx-plain-pg"})
    _event(pg_session, json.dumps({"run_id": "legacy0000b2", "op": "withdraw"}),
           event_type=event_constants.EVENT_RETROACTIVE_RUN, table=retroactive.RUN_EVENT_TABLE)
    pg_session.commit()

    def override():
        yield pg_session
    main.app.dependency_overrides[main.get_db] = override
    try:
        body = _queue(TestClient(main.app))
    finally:
        main.app.dependency_overrides.pop(main.get_db, None)

    [line] = _lines(body, run_id=run)
    assert (line["op"], line["events"], line["rows"]) == ("chain_replay", 2, 41), line
    assert _lines(body, transaction_id="tx-plain-pg")
    # ⚠️ Not pinned to 3: other PG tests' waiting rows share the schema within a run.
    assert body["listed"]["lines_total"] >= 3 and body["listed"]["capped"] is False
