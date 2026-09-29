# -*- coding: utf-8 -*-
"""A chain group at its attempt limit goes FAILED whole, writes no new event, and says why once.

🔴 [총괄 c9ee06b34 · ba0860575] 소유자 09-29 「체인 에러나면 쪼개는게 빼자 그냥」 ·
「차라리 에러를 잘남기는게 나음」. A failed chunk used to be halved into two new events, each
half failed and was halved again - one failing chunk wrote about 2N events, and an error on
every row walked every half to the end. Now the group's own events carry one record and the
log says it in one line.

🔴 [총괄 45f5da3f5] THE RECORD'S RULES AND TABLES ARE THE FAILING SEAT'S - the one that writes
the reason's `[rules=.. target=..]` head. A seat that names none leaves them None; the rules
the group woke never stand in. `row` is the ids the error names, or None.

⚠️ THE CONTROL IS THE OLD SYMPTOM, KEPT AS THE ANSWER: one poison row takes its whole chunk
FAILED with it (`test_one_poison_row_takes_its_chunk_failed_with_it`).
"""
import json
import logging

import pytest

import event_constants
import mapper_sdk
from chain import ingestion_worker as ciw
from database import crud, models, schemas
from database.context import outbox_mode
from database.models import DatabaseOutbox
from utils.payload_helper import get_payload_dict

COLLAPSED = event_constants.OUTBOX_MODE_COLLAPSED
SRC, DST = "obxwhole_src", "obxwhole_dst"
RULE, MAPPER = "obxwhole_rule", "obxwhole_mapper"
TABLES = {
    name: {"business_key": "key_id",
           "column_types": {"key_id": "string", "lot": "string", "qty": "number"}}
    for name in (SRC, DST)
}
RULES = [{"name": RULE, "trigger_table": SRC, "target_table": DST, "mapper": MAPPER,
          "is_batch": True, "enabled": True}]
HEAD = "[rules=%s target=%s] " % (RULE, DST)


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


def _mapper(monkeypatch, answer):
    """The rule's mapper, where the product looks for one - the real group runs around it."""
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, MAPPER,
                        lambda _db, payloads, rule=None: answer(payloads))


def _raises(text):
    def answer(_payloads):
        raise ValueError(text)
    return answer


async def _run(db, tx_id, events, caplog):
    with caplog.at_level(logging.WARNING):
        await ciw.process_pending_groups(db, [tx_id], {tx_id: events}, RULES, None)
    return [r.getMessage() for r in caplog.records if "permanently failed" in r.getMessage()]


def _record(event):
    return get_payload_dict(event)["error_log"]


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
    _mapper(monkeypatch, _raises("every row broke"))
    before = len(_all(db))

    lines = await _run(db, tx_id, events, caplog)

    assert len(_all(db)) == before, "a failed group writes no new event"
    assert [(e.status, e.processed_chain) for e in events] == [("FAILED", True)] * len(events)
    records = [_record(e) for e in events]
    record = records[0]
    assert all({k: v for k, v in r.items() if k != "failed_at"}
               == {k: v for k, v in record.items() if k != "failed_at"} for r in records)
    assert (record["rules"], record["tables"], record["rows"], record["row"]) \
        == ([RULE], [DST], rows, None)
    assert record["reason"].startswith(HEAD) and "ValueError: every row broke" in record["reason"]
    assert event_constants.counts_as_failure(get_payload_dict(events[0]))
    assert len(lines) == 1, "one line per group, not one per event: %r" % lines
    assert ("%d row(s)" % rows in lines[0] and "rules=%s tables=%s" % (RULE, DST) in lines[0]
            and "row=" + ciw.ROW_NOT_GIVEN in lines[0]), lines[0]


@pytest.mark.anyio
async def test_a_failed_write_names_the_table_it_was_writing(db, monkeypatch, caplog):
    """The other seat that writes the head - the write door, not the mapper."""
    events = _seed(db, 4, "tx-write")
    _mapper(monkeypatch, lambda payloads: {"updates": [
        {"business_key_val": "D%d" % i, "updates": {"key_id": "D%d" % i, "qty": 1.0},
         "source_name": "chain_ingestion"} for i in range(len(payloads))]})
    real = crud.apply_batch_updates

    def broken(db_, table_name, *args, **kwargs):
        if table_name == DST:
            raise RuntimeError("disk full on %s" % table_name)
        return real(db_, table_name, *args, **kwargs)

    monkeypatch.setattr(crud, "apply_batch_updates", broken)

    lines = await _run(db, "tx-write", events, caplog)

    record = _record(events[0])
    assert (events[0].status, record["rules"], record["tables"]) == ("FAILED", [RULE], [DST])
    assert record["reason"].startswith(HEAD) and "disk full on %s" % DST in record["reason"]
    assert len(lines) == 1 and "rules=%s tables=%s" % (RULE, DST) in lines[0], lines


@pytest.mark.anyio
async def test_a_failure_whose_seat_names_no_rule_leaves_the_record_unknown(
        db, monkeypatch, caplog):
    """🔴 NOT THE RULES THE GROUP WOKE. Rows the event names cannot be read, so the group is
    refused before any rule runs - it woke `RULE`, and nothing says `RULE` failed."""
    monkeypatch.setattr(ciw, "_RULES_DOCUMENT", {"max_rows_not_visible_defers": 1})
    ciw._ROWS_NOT_VISIBLE_DEFERS.clear()
    events = _seed(db, 3, "tx-blind")
    named = list(get_payload_dict(events[0])["row_ids"])
    model = models.DYNAMIC_TABLES[SRC]
    with outbox_mode(COLLAPSED):
        for row in db.query(model).filter(model.row_id.in_(named)).all():
            db.delete(row)
        db.commit()
    assert ciw._rules_for_group(events, RULES) == (RULE,), "the group did wake the rule"

    lines = await _run(db, "tx-blind", events, caplog)

    record = _record(events[0])
    assert events[0].status == "FAILED"
    assert (record["rules"], record["tables"], record["row"]) == (None, None, None)
    assert record["reason"].startswith(ciw.ROWS_NOT_VISIBLE), record["reason"]
    assert len(lines) == 1 and "rules=(unknown) tables=(unknown)" in lines[0], lines


@pytest.mark.anyio
async def test_one_poison_row_takes_its_chunk_failed_with_it(db, monkeypatch, caplog):
    """⚠️ THE CONTROL - the symptom the split existed for, now the intended answer."""
    events = _seed(db, 4, "tx-poison")
    poison = get_payload_dict(events[0])["row_ids"][2]

    def answer(payloads):
        if poison in json.dumps(payloads, default=str):
            raise ValueError("row %s: qty is not a number" % poison)
        return {"updates": []}

    _mapper(monkeypatch, answer)
    before = len(_all(db))

    lines = await _run(db, "tx-poison", events, caplog)

    assert len(_all(db)) == before
    record = _record(events[0])
    assert (events[0].status, record["rows"], record["row"]) == ("FAILED", 4, [poison])
    assert len(lines) == 1 and "row=" + poison in lines[0], lines


@pytest.mark.anyio
async def test_a_chunk_that_succeeds_is_left_as_it_is(db, monkeypatch, caplog):
    events = _seed(db, 4, "tx-fine")
    _mapper(monkeypatch, lambda payloads: {"updates": []})
    before = len(_all(db))

    lines = await _run(db, "tx-fine", events, caplog)

    assert len(_all(db)) == before and lines == []
    assert (events[0].status, events[0].processed_chain) == ("SUCCESS", True)
    assert "error_log" not in get_payload_dict(events[0])


@pytest.mark.anyio
async def test_retry_puts_the_failed_chunk_back_once_and_writes_nothing_new(
        db, client, monkeypatch, caplog):
    events = _seed(db, 4, "tx-again")
    _mapper(monkeypatch, _raises("every row broke"))
    await _run(db, "tx-again", events, caplog)
    assert events[0].status == "FAILED"
    before = len(_all(db))

    body = client.post("/admin/outbox/retry-failed", params={"event_id": events[0].id}).json()

    db.expire_all()
    assert (body["status"], body["reset"], body["skipped_reexpanded"]) == ("success", 1, 0)
    assert len(_all(db)) == before, "a retry writes no new event"
    assert (events[0].status, events[0].processed_chain, events[0].retry_count) \
        == ("PENDING", False, 0)
