# -*- coding: utf-8 -*-
"""체인 그룹의 시도 상한은 «선언 칸»이고 기본은 1 (S-139, 소유자 09-10 21:35 「3회 없애, 1회면 끝」).

🔴 THE CAP WAS SPELLED TWICE. `retry_count >= 3` decided, and a separate log line said
「(N/3)」 - so moving the cap moved one and not the other, and a log that is wrong about
「how many tries are left」 lies quietly. Verdict, reason and log now read one function.

⚠️ THE MECHANISM IS NOT REMOVED, THE DEFAULT MOVED. Declaring `max_group_attempts: 3`
restores the old behaviour exactly, which is what makes this a declaration rather than a
deletion.

🔴 AND THE CELL WAS OPEN ON THE RULE WITH NOBODY READING IT (S-221, 판정 378). It is in
`RULE_ROUTING_OPTIONAL`, the skeleton types it `number`, and the chain graph screen
publishes `rule["max_group_attempts"]` - while the reader looked at the DOCUMENT only. An
operator could write it on a rule, watch the form draw it and the screen show it, and change
nothing. The reader now takes both and answers rule → document → value.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                              # noqa: E402


# ---------------------------------------------------------------------------
# S-139 — the document layer and the floor
# ---------------------------------------------------------------------------

def test_an_undeclared_cap_is_one_attempt():
    assert worker.DEFAULT_MAX_GROUP_ATTEMPTS == 1
    assert worker.max_group_attempts(None, {}) == 1
    assert worker.max_group_attempts({}, {}) == 1


def test_the_old_behaviour_is_one_line_of_declaration_away():
    assert worker.max_group_attempts(None, {"max_group_attempts": 3}) == 3


def test_a_cap_below_one_would_isolate_a_group_that_never_ran():
    """⛔ 0 이하는 「한 번도 안 시도한다」가 되어 그룹이 영원히 격리된다."""
    for bad in (0, -5):
        assert worker.max_group_attempts(None, {"max_group_attempts": bad}) == 1
        assert worker.max_group_attempts({"max_group_attempts": bad}, {}) == 1


def test_a_cap_that_is_not_a_number_warns_and_falls_back():
    """A settings typo must not stop the chain - the same rule the ingestion pace follows."""
    assert worker.max_group_attempts(None, {"max_group_attempts": "three"}) == 1
    assert worker.max_group_attempts({"max_group_attempts": "three"}, {}) == 1


# ---------------------------------------------------------------------------
# S-221 — the rule layer, and what happens when a layer cannot be used
# ---------------------------------------------------------------------------

def test_the_rule_wins_over_the_document():
    """🔴 THE POINT OF S-221. The cell the operator edits is the rule's."""
    assert worker.max_group_attempts({"max_group_attempts": 5},
                                     {"max_group_attempts": 2}) == 5


def test_a_rule_that_says_nothing_leaves_the_document_answering():
    """⚠️ THE NO-REGRESSION. Every rule on this box declares nothing, so the document (and
    then the value) has to keep giving exactly today's answer."""
    assert worker.max_group_attempts({"name": "r"}, {"max_group_attempts": 2}) == 2
    assert worker.max_group_attempts({"name": "r"}, {}) == 1


def test_an_unusable_rule_value_falls_THROUGH_rather_than_to_the_floor():
    """⚠️ A LAYER THAT CANNOT ANSWER IS SKIPPED, not replaced by the default: the document
    still declared something and it is still the better answer than the built-in value."""
    assert worker.max_group_attempts({"max_group_attempts": "three"},
                                     {"max_group_attempts": 4}) == 4
    assert worker.max_group_attempts({"max_group_attempts": 0},
                                     {"max_group_attempts": 4}) == 4


def test_the_reader_holds_no_module_state(monkeypatch):
    """🔴 BOTH SOURCES ARE ARGUMENTS. If the loaded document could still leak in, the two
    cases above would be decided by whatever the process last loaded."""
    monkeypatch.setattr(worker, "_RULES_DOCUMENT", {"max_group_attempts": 9})

    assert worker.max_group_attempts(None, {}) == 1


# ---------------------------------------------------------------------------
# The seat: one number for the verdict, the reason and the log
# ---------------------------------------------------------------------------

def test_the_verdict_the_reason_and_the_log_read_one_number():
    """🔴 THE POINT OF S-139. Three spellings of one cap is how a log comes to disagree with
    the behaviour it describes."""
    import inspect

    body = inspect.getsource(worker.process_pending_groups)

    assert "attempts_cap = min(_caps)" in body
    assert "max_group_attempts(r, _RULES_DOCUMENT)" in body
    assert "event.retry_count >= attempts_cap" in body
    assert "{max_retry_num}/{attempts_cap}" in body
    assert ">= 3" not in body, "the literal cap must be gone from the verdict"
    assert "/3)" not in body, "and from the log"


def test_the_seat_asks_the_rules_this_group_woke():
    """🔴 S-221. A group that woke no enabled rule still needs a number, and the strictest of
    the ones it did wake is the only cap that is true for all of them at once - the same
    reading `merge_consecutive_groups` makes about its row ceiling."""
    import inspect

    body = inspect.getsource(worker.process_pending_groups)

    assert "_woke = _rules_for_group(events_in_tx, rules)" in body
    assert "max_group_attempts(None, _RULES_DOCUMENT)" in body, "the no-rule fallback"


def test_the_row_expansion_at_the_quarantine_boundary_is_untouched():
    """⚠️ OUTBOX-4 STAYS. A collapsed event covers up to 1,000 rows, so the boundary
    re-expands into per-row events to narrow the poison - that now happens on the FIRST
    failure, which makes it more useful rather than less."""
    import inspect

    body = inspect.getsource(worker.process_pending_groups)

    assert "is_collapsed_payload" in body
    assert "OUTBOX-4" in body
