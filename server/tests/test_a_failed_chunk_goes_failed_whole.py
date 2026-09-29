# -*- coding: utf-8 -*-
"""A chain group at its attempt limit goes FAILED whole, writes no new event, and says why once.

🔴 [총괄 c9ee06b34 · ba0860575] 소유자 09-29 「체인 에러나면 쪼개는게 빼자 그냥」 ·
「차라리 에러를 잘남기는게 나음」. A failed chunk used to be halved into two new events, each
half failed and was halved again - one failing chunk wrote about 2N events, and an error on
every row walked every half to the end. Now the group's own events carry one record
(rules · tables · rows · reason as raised · the row when the error names one) and the log
says it in one line.

⚠️ THE CONTROL IS THE OLD SYMPTOM, KEPT AS THE ANSWER: one poison row takes its whole chunk
FAILED with it (`test_one_poison_row_takes_its_chunk_failed_with_it`).
"""
import json
import logging

import pytest

import event_constants
from chain import ingestion_worker as ciw
from database import crud, models, schemas
from database.context import outbox_mode
from database.models import DatabaseOutbox
from utils.payload_helper import get_payload_dict

COLLAPSED = event_constants.OUTBOX_MODE_COLLAPSED
SRC, DST = "obxwhole_src", "obxwhole_dst"
RULE = "obxwhole_rule"
TABLES = {
    name: {"business_key": "key_id",
           "column_types": {"key_id": "string", "lot": "string", "qty": "number"}}
    for name in (SRC, DST)
}
RULES = [{"name": RULE, "trigger_table": SRC, "target_table": DST, "enabled": True}]
REASON = "[rule=%s target=%s] mapper raised: every row broke" % (RULE, DST)


@pytest.fixture()
def db(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr(ciw, "_RULES_DOCUMENT", {})     # the declared default: one attempt
    return db_session


def _seed(db, n, tx_id, mode=COLLAPSED):
    batch = schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(
            updates={"key_id": "K%d" % i, "lot": "LOT-A", "qty": float(i)},
            source_name="DT_LOG_20260929.csv", updated_by="tester",
            business_key_val="K%d" % i) for i in range(n)],
        transaction_id=tx_id, silent=True)
    if mode is None:
        crud.apply_batch_updates(db, SRC, batch)
    else:
        with outbox_mode(mode):
            crud.apply_batch_updates(db, SRC, batch)
    return [e for e in _all(db) if get_payload_dict(e).get("transaction_id") == tx_id]


def _all(db):
    return db.query(DatabaseOutbox).order_by(DatabaseOutbox.id.asc()).all()


def _fail_with(monkeypatch, reason_for):
    async def group(tx_id, events, db_, rules):
        reason = reason_for(events)
        return (reason is None), reason, []
    monkeypatch.setattr(ciw, "process_chain_transaction_group", group)


async def _run(db, tx_id, events, caplog):
    with caplog.at_level(logging.WARNING):
        await ciw.process_pending_groups(db, [tx_id], {tx_id: events}, RULES, None)
    return [r.getMessage() for r in caplog.records if "permanently failed" in r.getMessage()]


def _old_half(db, events):
    """A half the retired split wrote before c9ee06b34 - collapsed, own group, its lineage."""
    ev = events[0]
    payload = dict(get_payload_dict(ev))
    payload["transaction_id"] = "tx-old#half#a"
    payload["reexpanded_from"] = {"event_uuid": "parent", "depth": 1, "path": "a",
                                  "root_transaction_id": "tx-old"}
    ev.payload = payload
    db.commit()
    return "tx-old#half#a", events


@pytest.mark.anyio
@pytest.mark.parametrize("shape, rows", [
    ("collapsed", 1000),     # the order's gate: a 1,000-row chunk where every row fails
    ("per_row", 3),          # three events in one group: still one line, one record
    ("old_half", 4),         # a half already in a queue: it ends whole, it is not halved again
])
async def test_a_group_where_every_row_fails_goes_failed_whole_and_writes_nothing_new(
        db, monkeypatch, caplog, shape, rows):
    events = _seed(db, rows, "tx-" + shape, mode=None if shape == "per_row" else COLLAPSED)
    tx_id = "tx-" + shape
    if shape == "old_half":
        tx_id, events = _old_half(db, events)
    assert len(events) == (rows if shape == "per_row" else 1)
    _fail_with(monkeypatch, lambda evs: REASON)
    before = len(_all(db))

    lines = await _run(db, tx_id, events, caplog)

    assert len(_all(db)) == before, "a failed group writes no new event"
    assert [(e.status, e.processed_chain) for e in events] == [("FAILED", True)] * len(events)
    records = [get_payload_dict(e)["error_log"] for e in events]
    record = records[0]
    assert all({k: v for k, v in r.items() if k != "failed_at"}
               == {k: v for k, v in record.items() if k != "failed_at"} for r in records)
    assert (record["rules"], record["tables"], record["rows"], record["reason"], record["row"]) \
        == ([RULE], [DST], rows, REASON, ciw.ROW_NOT_GIVEN)
    assert event_constants.counts_as_failure(get_payload_dict(events[0]))
    assert len(lines) == 1, "one line per group, not one per event: %r" % lines
    assert "%d row(s)" % rows in lines[0] and RULE in lines[0] and DST in lines[0], lines[0]


@pytest.mark.anyio
async def test_one_poison_row_takes_its_chunk_failed_with_it(db, monkeypatch, caplog):
    """⚠️ THE CONTROL - the symptom the split existed for, now the intended answer."""
    events = _seed(db, 4, "tx-poison")
    poison = get_payload_dict(events[0])["row_ids"][2]
    _fail_with(monkeypatch, lambda evs: ("row %s: qty is not a number" % poison)
               if poison in json.dumps([get_payload_dict(e) for e in evs]) else None)
    before = len(_all(db))

    lines = await _run(db, "tx-poison", events, caplog)

    assert len(_all(db)) == before
    record = get_payload_dict(events[0])["error_log"]
    assert (events[0].status, record["rows"], record["row"]) == ("FAILED", 4, [poison])
    assert len(lines) == 1 and poison in lines[0], lines


@pytest.mark.anyio
async def test_a_chunk_that_succeeds_is_left_as_it_is(db, monkeypatch, caplog):
    events = _seed(db, 4, "tx-fine")
    _fail_with(monkeypatch, lambda evs: None)
    before = len(_all(db))

    lines = await _run(db, "tx-fine", events, caplog)

    assert len(_all(db)) == before and lines == []
    assert (events[0].status, events[0].processed_chain) == ("SUCCESS", True)
    assert "error_log" not in get_payload_dict(events[0])


@pytest.mark.anyio
async def test_retry_puts_the_failed_chunk_back_once_and_writes_nothing_new(
        db, client, monkeypatch, caplog):
    events = _seed(db, 4, "tx-again")
    _fail_with(monkeypatch, lambda evs: REASON)
    await _run(db, "tx-again", events, caplog)
    assert events[0].status == "FAILED"
    before = len(_all(db))

    body = client.post("/admin/outbox/retry-failed", params={"event_id": events[0].id}).json()

    db.expire_all()
    assert (body["status"], body["reset"], body["skipped_reexpanded"]) == ("success", 1, 0)
    assert len(_all(db)) == before, "a retry writes no new event"
    assert (events[0].status, events[0].processed_chain, events[0].retry_count) \
        == ("PENDING", False, 0)
