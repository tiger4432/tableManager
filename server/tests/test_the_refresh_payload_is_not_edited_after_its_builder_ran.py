# -*- coding: utf-8 -*-
"""S-279 · 판정 427. The `batch_refresh_required` builder stands, and nobody walks past it.

🔴 THE BUILDER ALREADY EXISTED AND FIVE SENDERS WENT AROUND IT. Each called
`event_constants.batch_refresh_message(...)` and then edited the returned dict:

    msg = event_constants.batch_refresh_message(table, count)
    if created_logs and len(created_logs) <= 5000:
        msg["created_logs"] = created_logs

That is worse than not having a builder, because it looks like it has one. All five carried the
same rule and the same two consequences: over the limit the list was dropped WHOLE, and
`total_log_count` was never sent by any of them. The client's contract says 「absent is not
complete」 - with no total it cannot compare, so it neither appends nor reloads and the
timeline silently falls behind a change the operator can see in the grid. The 5,000 dates to
2026-06-02 (`3006b58b`), before that contract existed.

⚠️ THE GATE IS A DATAFLOW CHECK, NOT A KEYWORD BAN. Two places legitimately hold these keys
without being this message: `/internal/events/broadcast` re-truncates a payload it RECEIVED
from the chain worker, and `run_watcher` builds the HTTP body that becomes this call. Banning
the key names would be red on both and would need an exception list - and an exception list is
where the next real one hides. So this asks the question that actually matters: does anything
subscript the object THIS BUILDER returned?
"""
import ast
import io
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402

BUILDER = "batch_refresh_message"
#: The cells the five senders were writing by hand. `truncated` and `transaction_id` are on the
#: same envelope and are included so this does not have to be revisited per key.
OWNED = ("created_logs", "total_log_count", "truncated", "transaction_id",
         "change_count", "table_name", "event")


def _files():
    for folder, dirs, files in os.walk(SERVER_DIR):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".tmp", "tests")]
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def _edits_after_the_builder(path):
    """Names assigned from the builder, then subscripted with a cell the builder owns."""
    with io.open(path, encoding="utf-8") as handle:
        try:
            tree = ast.parse(handle.read(), path)
        except SyntaxError:                                            # pragma: no cover
            return []

    built = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        called = getattr(node.value.func, "attr", None) or getattr(node.value.func, "id", None)
        if called != BUILDER:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                built.add(target.id)

    offences = []
    if not built:
        return offences
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue
            holder = getattr(target.value, "id", None)
            key = getattr(target.slice, "value", None)
            if holder in built and key in OWNED:
                offences.append("%s:%d  %s[%r] = ..."
                                % (os.path.relpath(path, SERVER_DIR).replace(os.sep, "/"),
                                   node.lineno, holder, key))
    return offences


def test_nothing_edits_the_message_after_the_builder_returned_it():
    """🔴 THE GATE. A sender that needs a cell passes it as an ARGUMENT, so the rule for that
    cell is decided once - and five senders cannot each decide it differently again."""
    offences = []
    for path in _files():
        offences.extend(_edits_after_the_builder(path))

    assert offences == [], (
        "these edit the payload after %s built it, which is how five senders came to carry "
        "five copies of one truncation rule: %s" % (BUILDER, offences))


# ---------------------------------------------------------------------------
# what the rule now IS, measured rather than read off the source
# ---------------------------------------------------------------------------

def test_a_long_list_is_cut_and_the_cut_is_reported():
    """⛔ THE DEFECT IN ONE OBJECT. The old rule dropped the whole list past its limit and said
    nothing, so the client saw no `created_logs` and no `total_log_count` - indistinguishable
    from a sender that has nothing to report."""
    logs = [{"row_id": "r%d" % n} for n in range(event_constants.MAX_NOTIFY_CREATED_LOGS + 700)]

    message = event_constants.batch_refresh_message("t", 1200, created_logs=logs)

    assert len(message["created_logs"]) == event_constants.MAX_NOTIFY_CREATED_LOGS
    assert message["total_log_count"] == len(logs), (
        "the cut was not reported, so the client cannot tell a sample from the population")
    assert len(message["created_logs"]) < message["total_log_count"], (
        "this is the exact comparison the client makes to decide between appending and "
        "reloading")


def test_a_short_list_says_it_is_complete():
    logs = [{"row_id": "r1"}, {"row_id": "r2"}]

    message = event_constants.batch_refresh_message("t", 2, created_logs=logs)

    assert message["created_logs"] == logs
    assert message["total_log_count"] == 2, "a complete list still says how many"


def test_a_caller_that_already_cut_keeps_its_own_total():
    """🔴 THE CHAIN WORKER SLICES BEFORE IT CALLS, and re-deriving the total from the list it
    handed over would report the SAMPLE's size as the population's - which is the very fact
    `total_log_count` exists to carry."""
    sample = [{"row_id": "r%d" % n} for n in range(500)]

    message = event_constants.batch_refresh_message(
        "t", 9000, created_logs=sample, total_log_count=9000)

    assert message["total_log_count"] == 9000
    assert len(message["created_logs"]) == 500


def test_no_logs_at_all_says_neither():
    """⚠️ 「말 안 함」과 「없음」은 다른 사실이다. A sender with nothing to report must not look
    like a sender reporting zero, which is what an unconditional key would do."""
    message = event_constants.batch_refresh_message("t", 5)

    assert "created_logs" not in message
    assert "total_log_count" not in message
