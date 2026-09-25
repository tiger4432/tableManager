# -*- coding: utf-8 -*-
"""총괄 e573a6edf ①②④ · 756c54d68 ⑤⑥ — the unit of failure is the row that still fails.

A grouped row the worker split is FAILED with `reexpanded_into`; its rows are back in the
queue as its children. Counting both counted one edit twice and left the parent FAILED with
no way out. A split leaf carries its row as it was when its group failed, so its retry has
to read the row now. And a refusal is not a success."""
import datetime
import uuid

import pytest

import event_constants
import main
import outbox_expand
from database import models
from utils.payload_helper import get_payload_dict
from tests.test_retroactive_admin import _seed, retro_env  # noqa: F401

TABLE = "retro_test_target"


def _event(db, payload, status="FAILED", processed_at=None):
    row = models.DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), event_type="EDIT", table_name=TABLE, payload=payload,
        status=status, processed_chain=True, retry_count=1,
        created_at=datetime.datetime(2026, 9, 25, 9, 0), processed_at=processed_at)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("payload", [
    {}, {"error_log": {}}, {"error_log": {"reexpanded_into": 3}},
    {"error_log": {"reexpanded_into": 0}}, {"error_log": {"reexpanded_into": None}},
    {"error_log": {"reason": "x"}, "reexpanded_from": {"depth": 1}},
])
def test_the_sql_and_the_python_reading_agree(retro_env, payload):
    row = _event(retro_env, payload)
    by_sql = retro_env.query(models.DatabaseOutbox.id).filter(
        event_constants.failure_clause(models.DatabaseOutbox),
        models.DatabaseOutbox.id == row.id).count() == 1
    assert by_sql is event_constants.counts_as_failure(get_payload_dict(row))


def test_one_split_edit_is_one_failure(retro_env):
    """The parent and its failing leaf were two lines, 「EDIT 2」, for one edit."""
    _event(retro_env, {"transaction_id": "tx1", "row_ids": ["r1"],
                       "error_log": {"reason": "boom", "reexpanded_into": 1}})
    _event(retro_env, {"transaction_id": "tx1#row#r1", "row_id": "r1", "data": {},
                       "reexpanded_from": {"depth": 1}, "error_log": {"reason": "boom"}})
    out = main.get_failed_outbox_events(page=1, limit=10, db=retro_env)
    assert out["total"] == 1
    assert [line["count"] for line in out["summary"]] == [1]


def test_retrying_a_split_parent_is_refused_not_a_success(retro_env):
    parent = _event(retro_env, {"transaction_id": "tx2", "row_ids": ["r1", "r2"],
                                "error_log": {"reason": "boom", "reexpanded_into": 2}})
    out = main.retry_failed_outbox_events(event_id=parent.id, db=retro_env)
    assert out["status"] == "refused" and out["skipped_reexpanded"] == 1
    assert parent.status == "FAILED"


def _leaf_of(db, note):
    _seed(db, TABLE, [{"part_no": "P-LEAF", "note": note}])
    model = models.DYNAMIC_TABLES[TABLE]
    row = db.query(model).filter(model.business_key_val == "P-LEAF").one()
    payload = outbox_expand._synthesize_payload(
        row, outbox_expand._data_columns(model), {"transaction_id": "tx3", "source_name": "s"})
    payload.update(transaction_id="tx3#row#%s" % row.row_id,
                   reexpanded_from={"event_uuid": "p", "depth": 1},
                   error_log={"reason": "note was bad"})
    return row, _event(db, payload)


def test_a_split_leaf_retry_reads_the_row_as_it_is_now(retro_env):
    """Fix the data, press retry - the retry has to carry the fix."""
    row, leaf = _leaf_of(retro_env, "bad")
    assert get_payload_dict(leaf)["data"]["note"]["value"] == "bad"
    _seed(retro_env, TABLE, [{"part_no": "P-LEAF", "note": "fixed"}])

    out = main.retry_failed_outbox_events(event_id=leaf.id, db=retro_env)

    retro_env.refresh(leaf)
    got = get_payload_dict(leaf)
    assert out["status"] == "success" and leaf.status == "PENDING"
    assert got["data"]["note"]["value"] == "fixed"
    assert (got["transaction_id"], got["reexpanded_from"]["depth"]) == (
        "tx3#row#%s" % row.row_id, 1)
    assert got["error_log"]["resolved_at"]


def test_a_leaf_whose_row_is_gone_is_left_and_named(retro_env):
    row, leaf = _leaf_of(retro_env, "bad")
    retro_env.delete(row)
    retro_env.flush()
    out = main.retry_failed_outbox_events(event_id=leaf.id, db=retro_env)
    assert leaf.status == "FAILED" and "no longer exists" in out["message"]


def test_failed_at_is_when_it_failed_not_when_it_was_born(retro_env):
    at = datetime.datetime(2026, 9, 25, 18, 30)
    _event(retro_env, {"transaction_id": "tx4"}, processed_at=at - datetime.timedelta(hours=1))
    _event(retro_env, {"transaction_id": "tx4"}, processed_at=at)
    group, = main.get_failed_outbox_events(page=1, limit=10, db=retro_env)["data"]
    assert group["failed_at"] == at.isoformat()
