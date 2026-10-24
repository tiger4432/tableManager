# -*- coding: utf-8 -*-
"""총괄 3de34d292 (소유자 10-21 「화면에 좀 띄워, 로그 언제 찾아보냐」): the chain queue answer says, per line, its rules
with their rows in and out; for a line to be tried again, the stage it broke in; and the newest failed groups - rule ·
stage · rows in · rows out · the failure's one sentence · when. From the seats that already hold them: the group's
claim (the stage), the rule's activity record (the [ChainRule] line's numbers), `failure_cause`, `failure_clause`.
"""
import inspect
import logging
import os

import pytest

import event_constants
import mapper_sdk
from chain import activity
from chain import ingestion_worker as ciw
from database import crud, models, schemas
from database.context import outbox_mode
from database.models import DatabaseOutbox
from utils.payload_helper import get_payload_dict

SRC, DST = "qwhy_src", "qwhy_dst"
RULE, MAPPER = "qwhy_rule", "qwhy_mapper"
TABLES = {name: {"business_key": "key_id", "column_types": {"key_id": "string", "qty": "number"}}
          for name in (SRC, DST)}
RULES = [{"name": RULE, "trigger_table": SRC, "target_table": DST, "mapper": MAPPER,
          "is_batch": True, "enabled": True}]
#: the stage a group is in while its rule's mapper runs - the claim's word, the one a running line shows
MAPPER_STAGE = "mapper"


@pytest.fixture()
def db(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr(ciw, "_RULES_DOCUMENT", {})                   # one attempt
    monkeypatch.setattr(ciw, "loaded_chain_rules", lambda: [dict(r) for r in RULES])
    activity.registry.clear()
    activity.registry.attach()                                       # the loop runs in this process
    yield db_session
    activity.registry.clear()


def _seed(db, n, tx):
    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"key_id": "K%d" % i, "qty": float(i)}, source_name="f.csv",
                                      updated_by="t", business_key_val="K%d" % i) for i in range(n)],
            transaction_id=tx, silent=True))
    return [e for e in db.query(DatabaseOutbox).order_by(DatabaseOutbox.id).all()
            if get_payload_dict(e).get("transaction_id") == tx]


def _raises(monkeypatch, text):
    def answer(_db, _payloads, rule=None):
        raise ValueError(text)
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, MAPPER, answer)


def _said(text):
    """The sentence of a failure `_raises` makes - its last line and where: the raise in this file, a product file
    (`event_constants.failure_place`), said from the server folder."""
    lines, first = inspect.getsourcelines(_raises)
    line = first + next(i for i, source in enumerate(lines) if "raise ValueError" in source)
    here = os.path.relpath(os.path.abspath(__file__), os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return "ValueError: %s at %s:%d in answer" % (text, here, line)


async def _run(db, tx, events, caplog):
    with caplog.at_level(logging.INFO):
        await ciw.process_pending_groups(db, [tx], {tx: events}, RULES, None)
    return [r.getMessage() for r in caplog.records]


def _queue(client):
    answer = client.get("/admin/chain/queue")
    assert answer.status_code == 200, answer.text
    return answer.json()


@pytest.mark.anyio
async def test_a_failed_group_says_its_stage_and_its_rules_rows_and_the_queue_lists_it(db, client, monkeypatch, caplog):
    events = _seed(db, 5, "tx-f")
    _raises(monkeypatch, "every row broke")
    said = await _run(db, "tx-f", events, caplog)
    record = get_payload_dict(db.query(DatabaseOutbox).get(events[0].id))["error_log"]
    assert (record["rules"], record["stage"], record["rows_in"], record["rows_out"]) == ([RULE], MAPPER_STAGE, 5, None)
    rule_line = [line for line in said if line.startswith("[ChainRule] rule=%s " % RULE)]
    assert len(rule_line) == 1 and " rows_in=5 rows_out=None " in rule_line[0], "the record's rows are not the log's"

    [failure] = _queue(client)["recent_failures"]
    assert failure == {"transaction_id": "tx-f", "rules": [RULE], "tables": [DST], "stage": MAPPER_STAGE,
                       "rows_in": 5, "rows_out": None, "rows": 5, "failure": _said("every row broke"),
                       "failed_at": failure["failed_at"]} and failure["failed_at"]
    assert _queue(client)["recent_failures_listed"] == {"cap": 20, "capped": False}
    [summary] = client.get("/admin/outbox/failed").json()["summary"]
    assert summary["last_failure"] == failure["failure"], "the failed list's line says the sentence another way"
    row = db.query(DatabaseOutbox).get(events[0].id)
    assert event_constants.chain_state_of(row.processed_chain, row.status, payload=row.payload)["why"] == {
        "failure": _said("every row broke"), "stage": MAPPER_STAGE}


@pytest.mark.anyio
async def test_a_statement_timeout_names_the_stage_its_record_carries(db, client, monkeypatch, caplog):
    """총괄: the timeout sentence's «stage <word>» and the record's stage are one word - the claim's."""
    events = _seed(db, 3, "tx-t")
    _raises(monkeypatch, "QueryCanceled: canceling statement due to statement timeout")
    monkeypatch.setattr(ciw, "_limit_that_stopped", lambda error, ran: 30)
    await _run(db, "tx-t", events, caplog)
    record = get_payload_dict(db.query(DatabaseOutbox).get(events[0].id))["error_log"]
    assert record["stage"] == MAPPER_STAGE and "statement timeout · 30 s · stage %s " % MAPPER_STAGE in record["reason"]
    assert _queue(client)["recent_failures"][0]["stage"] == MAPPER_STAGE


@pytest.mark.anyio
async def test_a_line_to_be_tried_again_says_the_stage_it_broke_in_and_its_rules_last_rows(
        db, client, monkeypatch, caplog):
    monkeypatch.setattr(ciw, "_RULES_DOCUMENT", {"max_group_attempts": 2})
    events = _seed(db, 4, "tx-r")
    _raises(monkeypatch, "broke once")
    await _run(db, "tx-r", events, caplog)
    row = db.query(DatabaseOutbox).get(events[0].id)
    assert row.status == "RETRYING" and get_payload_dict(row)[event_constants.LAST_FAILURE_STAGE] == MAPPER_STAGE
    [line] = [line for line in _queue(client)["waiting_transactions"] if line["transaction_id"] == "tx-r"]
    assert line["chain_state"]["state"] == event_constants.CHAIN_STATE_RETRYING
    assert (line["chain_state"]["why"]["stage"], line["chain_state"]["why"]["last_failure"]) == (
        MAPPER_STAGE, _said("broke once"))
    assert line["rules"] == [{"rule": RULE, "rows_in": 4, "rows_out": None, "running_seconds": None}]
    assert _queue(client)["recent_failures"] == [], "a group still to be tried is not a failure"


def test_a_running_rule_says_its_rows_in_and_seconds_and_a_ran_one_its_last_rows(db, client):
    from utils import heartbeat

    _seed(db, 2, "tx-run")
    activity.registry.record_outcome(RULE, event_constants.RULE_OUTCOME_RAN_CHANGED, rows_in=9, rows_out=7)
    [line] = [line for line in _queue(client)["waiting_transactions"] if line["transaction_id"] == "tx-run"]
    assert line["rules"] == [{"rule": RULE, "rows_in": 9, "rows_out": 7, "running_seconds": None}]

    def line_now():
        [line] = [line for line in _queue(client)["waiting_transactions"] if line["transaction_id"] == "tx-run"]
        return line

    # a chain group's claim, its beat written once - the run below is not beaten for: it reaches the file as it starts
    cm = heartbeat.work_claim("chain", "tx tx-run", acted_on=True)
    cm.__enter__()
    try:
        heartbeat.note_work(line_keys=["tx-run"])
        heartbeat.progress(MAPPER_STAGE)
        heartbeat.beat("chain", force=True)
        assert line_now()["chain_state"]["why"]["rule_run"] is None
        with activity.running(RULE, MAPPER, DST, 2) as entry:
            during = line_now()
            entry.rows_out = 5
        after = line_now()
    finally:
        cm.__exit__(None, None, None)
    [rule] = during["rules"]
    assert (rule["rule"], rule["rows_in"], rule["rows_out"]) == (RULE, 2, None) and rule["running_seconds"] >= 0
    assert during["chain_state"]["why"]["stage"] == MAPPER_STAGE
    assert during["chain_state"]["why"]["rule_run"] == {"rule": RULE, "rows_in": 2, "rows_out": None,
                                                        "running_seconds": rule["running_seconds"]}
    # ended: the claim keeps the finished run's rows until the claim ends (총괄 fc1e1e385) - no blink to nothing
    assert after["chain_state"]["why"]["rule_run"] == {"rule": RULE, "rows_in": 2, "rows_out": 5,
                                                       "running_seconds": None}
    assert after["rules"] == [{"rule": RULE, "rows_in": 2, "rows_out": 5, "running_seconds": None}]


def test_the_rows_are_the_groups_only_and_only_for_one_named_rule():
    """`_failed_at`: a record older than the group's claim, or a failure naming two rules, says None."""
    activity.registry.clear()
    activity.registry.record_outcome(RULE, event_constants.RULE_OUTCOME_FAILED, "x", rows_in=3)
    at = activity.registry.instants()["outcomes"][RULE]["at"]
    one = ciw.named_failure([RULE], [DST], "boom")
    assert (ciw._failed_at(one, {"stage": "s", "started": at}).rows_in,
            ciw._failed_at(one, {"stage": "s", "started": at + 1}).rows_in) == (3, None)
    both = ciw._failed_at(ciw.named_failure([RULE, "other"], [DST], "boom"), {"stage": "s", "started": at})
    assert (both.stage, both.rows_in, both.rules) == ("s", None, [RULE, "other"])
    assert str(both) == str(ciw.named_failure([RULE, "other"], [DST], "boom")), "the reason was reworded"
    activity.registry.clear()


def test_the_newest_failures_stop_at_the_cap_and_say_they_were_cut(db, client):
    for k in range(22):
        db.add(DatabaseOutbox(event_uuid="u%d" % k, event_type="EDIT", table_name=SRC, status="FAILED",
                              processed_chain=True, payload={"transaction_id": "tx-%02d" % k,
                                                             "error_log": {"reason": "Traceback\nE%d" % k}}))
    db.add(DatabaseOutbox(event_uuid="u-twin", event_type="EDIT", table_name=SRC, status="FAILED",
                          processed_chain=True, payload={"transaction_id": "tx-21", "error_log": {"reason": "E21"}}))
    db.commit()
    answer = _queue(client)
    assert answer["recent_failures_listed"] == {"cap": 20, "capped": True}
    assert [f["transaction_id"] for f in answer["recent_failures"]] == ["tx-%02d" % k for k in range(21, 1, -1)]
    assert answer["recent_failures"][0]["failure"] == "E21" and answer["recent_failures"][0]["stage"] is None
