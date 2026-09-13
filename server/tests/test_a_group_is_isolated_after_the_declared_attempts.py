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

import pytest

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
# 🔴 S-225 (판정 380) - the seat, RUN. Not read.
#
# 「가장 엄한 상한이 이긴다」 was held by a SOURCE ORACLE, and a source oracle measures the
# shape of a line rather than what the line does - the standing 「텍스트가 «대리»면 금지」.
# The oracle S-139 put there was a bridge; this is the thing itself, and the bridge comes
# out in the same commit, because two oracles for one property are two paths.
# ---------------------------------------------------------------------------

# ⚠️ ONE SPELLING OF THE FAKES. `test_chain_hol_scheduling` already drives this same
# function with them; a second copy here would be a second outbox event shape, and the day
# the real one grows a field only one of them would learn.
from test_chain_hol_scheduling import FakeDB, FakeEvent                   # noqa: E402

STRICT, LAX = 2, 5

#: TWO RULES, ONE GROUP. Same trigger table, so one event wakes both - which is the only
#: arrangement in which 「whose cap」 is a real question.
CAP_RULES = [
    {"name": "strict", "trigger_table": "s225_src", "target_table": "s225_target",
     "enabled": True, "max_group_attempts": STRICT},
    {"name": "lax", "trigger_table": "s225_src", "target_table": "s225_target",
     "enabled": True, "max_group_attempts": LAX},
]


def _one_failing_group(monkeypatch):
    async def always_fails(tx_id, events, db, rules):
        return False, f"boom:{tx_id}", []

    monkeypatch.setattr(worker, "process_chain_transaction_group", always_fails)
    monkeypatch.setattr(worker, "_RULES_DOCUMENT", {})
    event = FakeEvent("s225_uuid", "s225_src", "s225_tx")
    return ["s225_tx"], {"s225_tx": [event]}, event


@pytest.mark.anyio
async def test_the_strictest_rules_cap_is_the_one_that_isolates_the_group(monkeypatch):
    """🔴 THE BEHAVIOUR, IN ORDER. Attempt 1 must NOT quarantine (so the cap is not 1, the
    built-in value) and attempt 2 MUST (so the cap is 2 and not 5). Either half alone is
    satisfied by a wrong answer."""
    group_order, groups, event = _one_failing_group(monkeypatch)
    factory = lambda: FakeDB()                                      # noqa: E731

    await worker.process_pending_groups(FakeDB(), group_order, groups, CAP_RULES, factory)
    assert (event.retry_count, event.status) == (1, "RETRYING")

    await worker.process_pending_groups(FakeDB(), group_order, groups, CAP_RULES, factory)
    assert (event.retry_count, event.status) == (2, "FAILED")
    assert event.processed_chain is True, "quarantined means out of the worker's queries"


@pytest.mark.anyio
async def test_the_log_says_the_same_number_the_verdict_used(monkeypatch, caplog):
    """🔴 THE OTHER HALF OF S-139, ALSO RUN NOW. A log that is wrong about 「how many tries
    are left」 lies quietly, so the number it prints is read off the line it printed."""
    import logging

    group_order, groups, _event = _one_failing_group(monkeypatch)

    with caplog.at_level(logging.WARNING):
        await worker.process_pending_groups(FakeDB(), group_order, groups, CAP_RULES,
                                            lambda: FakeDB())

    said = " ".join(r.getMessage() for r in caplog.records)
    assert f"(1/{STRICT})" in said, said
    assert f"/{LAX})" not in said, said


@pytest.mark.anyio
async def test_a_group_that_woke_no_rule_still_gets_a_number(monkeypatch):
    """⚠️ THE FALLBACK, RUN. With no rule matching, the document answers - and without this
    the seat would be reading `min([])`."""
    group_order, groups, event = _one_failing_group(monkeypatch)
    monkeypatch.setattr(worker, "_RULES_DOCUMENT", {"max_group_attempts": 1})
    strangers = [{"name": "elsewhere", "trigger_table": "not_s225_src",
                  "target_table": "s225_target", "enabled": True}]

    await worker.process_pending_groups(FakeDB(), group_order, groups, strangers,
                                        lambda: FakeDB())

    assert (event.retry_count, event.status) == (1, "FAILED")


def test_the_row_expansion_at_the_quarantine_boundary_is_untouched():
    """⚠️ OUTBOX-4 STAYS. A collapsed event covers up to 1,000 rows, so the boundary
    re-expands into per-row events to narrow the poison - that now happens on the FIRST
    failure, which makes it more useful rather than less."""
    import inspect

    body = inspect.getsource(worker.process_pending_groups)

    assert "is_collapsed_payload" in body
    assert "OUTBOX-4" in body
