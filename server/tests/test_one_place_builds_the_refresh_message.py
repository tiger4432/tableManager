# -*- coding: utf-8 -*-
"""Nine senders each wrote the `batch_refresh_required` payload by hand.

A payload written nine times is a payload that will differ nine ways, and this one differs
SILENTLY: the client guards on `msg.table_name` and then reads this event's body not at all
(`websocket.js` clears the page cache and returns), so a sender that dropped or misspelled a
key produces no error, no warning and no visible change. That is the owner's fourth
cleanliness rule -- one capability must not have two paths -- and this event had nine.

⛔ THE PAYLOAD IS UNCHANGED. Not one key added or removed: seven senders produce
`{event, table_name, change_count}`, one adds `truncated`, one adds the audit
trio. Unifying the SHAPES would be a boundary-contract decision and is NOT this change.
"""
import ast
import inspect
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                           # noqa: E402

EVENT = "batch_refresh_required"


def hand_built(module_file):
    """Dict literals that spell this event by hand, parsed so nesting cannot leak."""
    tree = ast.parse(io.open(module_file, encoding="utf-8").read())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if "event" not in keys or len(node.keys) != len(node.values):
            continue
        value = node.values[keys.index("event")]
        if isinstance(value, ast.Constant) and value.value == EVENT:
            found.append(node.lineno)
    return found


def test_no_sender_builds_it_by_hand_any_more():
    """🔴 THE POINT. Drifting apart now takes editing the one function."""
    from chain import ingestion_worker
    import main

    for module in (main, ingestion_worker):
        left = hand_built(module.__file__)
        assert not left, "%s still spells the payload at lines %s" % (
            os.path.basename(module.__file__), left)


# ------------------------------------------------------ every shape is still reproducible

def test_the_seven_bare_senders_are_byte_for_byte_what_they_were():
    assert event_constants.batch_refresh_message("dt_map", 7) == {
        "event": EVENT, "table_name": "dt_map", "change_count": 7}


def test_the_omitted_deletes_sender_is_what_it_was():
    assert event_constants.batch_refresh_message(
        "dt_map", 12, deleted_row_ids_omitted=12) == {
            "event": EVENT, "table_name": "dt_map", "change_count": 12,
            "truncated": {"deleted_row_ids": {
                "cut": True, "omitted": 12,
                "reason": "deleted ids beyond BROADCAST_ITEM_LIMIT"}}}


def test_the_chain_sender_is_what_it_was():
    assert event_constants.batch_refresh_message(
        "dt_map", 3, transaction_id="tx1", created_logs=[{"a": 1}],
        total_log_count=9) == {
            "event": EVENT, "table_name": "dt_map", "change_count": 3,
            "transaction_id": "tx1", "created_logs": [{"a": 1}], "total_log_count": 9}


# --------------------------------------------------------------- the omissions are honest

def test_an_optional_that_was_not_given_is_absent_rather_than_null():
    """A sender that never reported omissions must not start claiming it omitted nothing --
    `null` and "this sender does not say" are different facts on the wire."""
    message = event_constants.batch_refresh_message("dt_map", 1)
    for optional in ("transaction_id", "created_logs", "total_log_count",
                     "truncated"):
        assert optional not in message


#: 🔴 인자 이름은 «발신자의 말»이고 전선의 이름은 «정본»이다 — S-5 이후 그 둘이 다르다.
#:    그래서 읽는 자리를 따로 받는다. 단언의 뜻은 그대로다: 0 도 «간다».
@pytest.mark.parametrize("field,value,on_wire", [
    ("created_logs", [], lambda m: m["created_logs"]),
    ("total_log_count", 0, lambda m: m["total_log_count"]),
    ("deleted_row_ids_omitted", 0,
     lambda m: m["truncated"]["deleted_row_ids"]["omitted"]),
])
def test_an_empty_or_zero_optional_still_travels(field, value, on_wire):
    """⚠️ `is not None`, NOT truthiness. An empty list and a zero are things a sender MEANT
    to say; dropping them would make "nothing was omitted" look like "this sender does not
    report omissions" -- the absence-versus-zero confusion this repository keeps closing."""
    assert on_wire(event_constants.batch_refresh_message("t", 1, **{field: value})) == value


def test_change_count_zero_is_carried_not_dropped():
    """The sweep's recovery message sends 0 deliberately; a missing key is a different
    object from `{change_count: 0}`."""
    assert event_constants.batch_refresh_message("t", 0)["change_count"] == 0


def test_the_event_name_has_one_spelling():
    assert event_constants.EVENT_BATCH_REFRESH_REQUIRED == EVENT
    body = inspect.getsource(event_constants.batch_refresh_message)
    assert '"%s"' % EVENT not in body, "the builder spells the name instead of naming it"
