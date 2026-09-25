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


@pytest.mark.parametrize("case, status, reset", [
    ("parents only", "refused", 0), ("row-less leaf only", "refused", 0),
    ("mixed", "success", 1), ("nothing matches", "refused", 0)])
def test_the_status_says_whether_anything_was_reset(retro_env, case, status, reset):
    """총괄 ec99f75a6 - one place decides: nothing reset is refused, whichever branch left it
    at zero; a mix says what it did and what it did not."""
    parent = _event(retro_env, {"transaction_id": "txp", "row_ids": ["r1", "r2"],
                                "error_log": {"reason": "boom", "reexpanded_into": 2}})
    row, leaf = _leaf_of(retro_env, "bad")
    retro_env.delete(row)
    plain = _event(retro_env, {"transaction_id": "txq", "error_log": {"reason": "boom"}})
    retro_env.flush()
    target = {"parents only": dict(event_id=parent.id),
              "row-less leaf only": dict(event_id=leaf.id),
              "mixed": {}, "nothing matches": dict(event_id=10 ** 9)}[case]

    out = main.retry_failed_outbox_events(db=retro_env, **target)

    assert (out["status"], out["reset"]) == (status, reset), out["message"]
    if case == "mixed":
        assert plain.status == "PENDING"
        assert (out["skipped_reexpanded"], out["skipped_missing_row"]) == (1, 1)
        assert "Skipped" in out["message"] and "Reset 1" in out["message"]


def test_attempts_are_named_for_the_round_they_count(retro_env):
    """총괄 bb6795759 ③ - the count a retry sets back to 0 is this round's attempts."""
    first = _event(retro_env, {"transaction_id": "tx5"})
    first.retry_count = 3
    retro_env.flush()
    group, = main.get_failed_outbox_events(page=1, limit=10, db=retro_env)["data"]
    assert (group["attempts_this_round"], group["events"][0]["attempts_this_round"]) == (3, 3)
    main.retry_failed_outbox_events(event_id=first.id, db=retro_env)
    assert first.retry_count == 0, "the retry still gives a fresh round"


def test_failed_at_is_when_it_failed_not_when_it_was_born(retro_env):
    at = datetime.datetime(2026, 9, 25, 18, 30)
    _event(retro_env, {"transaction_id": "tx4"}, processed_at=at - datetime.timedelta(hours=1))
    _event(retro_env, {"transaction_id": "tx4"}, processed_at=at)
    group, = main.get_failed_outbox_events(page=1, limit=10, db=retro_env)["data"]
    assert group["failed_at"] == at.isoformat()
