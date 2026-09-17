# -*- coding: utf-8 -*-
"""S-249 ⓒ. 뒤따르기 랩도 «홉»이고, 한 원인은 «한 번»만 받는다.

🔴 MEASURED BEFORE BUILDING, AND IT IS THE WHOLE REASON THIS EXISTS. `request_chain_depth` is
set in exactly ONE place - the chain group step - and the follow-up drain runs in its own
thread outside that scope. So everything this lap wrote carried NO hop at all, and
`max_chain_depth` could never see it: a loop that went through the follow-up lap was
UNBOUNDED while the same loop inside the group step was bounded. One ceiling, two answers.

🔴 AND THE GROUP STEP'S PRINCIPLE HAD NO COUNTERPART HERE. 「체인이 쓴 행은 체인을 다시 깨우지
않는다 — 선언으로 켠 것만 예외」 is enforced in the group step; on this lap a rule could be
handed the same row for the same original transaction again and again, because every pass
looked like a fresh batch.

⚠️ THE EXCEPTION STAYS AN EXCEPTION. A rule may still see a row again under a DIFFERENT
cause - that is the ordinary case, and it is why the memory is keyed by the transaction
rather than by the row.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                       # noqa: E402
from ledger import followup                                        # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    worker.forget_followups()
    followup._queue.clear()
    yield
    worker.forget_followups()
    followup._queue.clear()


# ---------------------------------------------------------------------------
# 🔴 ⓐ — one cause, one helping
# ---------------------------------------------------------------------------

def test_a_rule_is_handed_the_rows_of_one_cause_exactly_once():
    first = worker.followup_already_served("tx-1", "t", "rule_a", ["r1", "r2"])
    again = worker.followup_already_served("tx-1", "t", "rule_a", ["r1", "r2"])

    assert first == ["r1", "r2"]
    assert again == [], "the same cause was served twice"


def test_a_row_that_joins_the_same_cause_later_is_still_served():
    """⚠️ 「ALREADY SERVED」 IS ABOUT ROWS, NOT ABOUT THE BATCH. A row that reaches the lap
    later under the same cause has not been answered for, and dropping it because its
    neighbours were would be the S-227 defect wearing the other face."""
    worker.followup_already_served("tx-1", "t", "rule_a", ["r1"])

    assert worker.followup_already_served("tx-1", "t", "rule_a", ["r1", "r2"]) == ["r2"]


def test_another_rule_and_another_cause_are_not_the_same_helping():
    """🔴 THE KEY IS (CAUSE, TABLE, RULE). Two rules watching one table are two answers to
    give, and the same row under a NEW cause is a new question - that is the ordinary case
    this must not break."""
    worker.followup_already_served("tx-1", "t", "rule_a", ["r1"])

    assert worker.followup_already_served("tx-1", "t", "rule_b", ["r1"]) == ["r1"]
    assert worker.followup_already_served("tx-2", "t", "rule_a", ["r1"]) == ["r1"]
    assert worker.followup_already_served("tx-1", "other", "rule_a", ["r1"]) == ["r1"]


def test_a_batch_with_no_cause_is_never_remembered():
    """⚠️ NO TRANSACTION, NO MEMORY. A backfill or retroactive filler queues rows with no
    transaction id; remembering those under one shared key would make the second backfill of
    a row look like a repeat of the first."""
    assert worker.followup_already_served(None, "t", "rule_a", ["r1"]) == ["r1"]
    assert worker.followup_already_served(None, "t", "rule_a", ["r1"]) == ["r1"]


def test_the_memory_is_bounded_rather_than_growing_for_the_life_of_the_process():
    """🔴 A CAUSE IS FINISHED WHEN ITS CASCADE STOPS. An unbounded memo on a paced path that
    runs forever is a leak with a nice name - the oldest causes are evicted."""
    for n in range(worker.MAX_REMEMBERED_CAUSES + 20):
        worker.followup_already_served("tx-%d" % n, "t", "rule_a", ["r1"])

    assert len(worker._FOLLOWUP_SERVED) <= worker.MAX_REMEMBERED_CAUSES


# ---------------------------------------------------------------------------
# 🔴 ⓑ — the lap carries the cause and the hop
# ---------------------------------------------------------------------------

def test_the_queue_carries_the_cause_and_the_hop_to_the_lap():
    assert followup.enqueue("t", ["r1"], "EDIT", "tx-7", 3)
    table, row_ids, event_type, _at, transaction_id, chain_depth = followup._take()

    assert (table, row_ids, event_type) == ("t", ("r1",), "EDIT")
    assert transaction_id == "tx-7" and chain_depth == 3


def test_an_ordinary_edit_carries_no_hop_and_that_absence_is_kept():
    """⚠️ ABSENT STAYS ABSENT. A change that is not the chain's has no hop, and inventing a
    zero for it would make every ordinary edit look like the first step of a cascade."""
    assert followup.enqueue("t", ["r1"], "EDIT", "tx-7")

    assert followup._take()[5] is None


def test_the_dispatcher_runs_the_lap_inside_the_next_hop(monkeypatch):
    """🔴 THE LAP IS A STEP. Everything the follow-up writes is stamped one hop past the
    change that caused it, so the next pass meets `max_chain_depth` exactly as a write from
    the group step would - which is what makes a loop through this lap finite at all."""
    from chain import builtins
    from database.context import request_chain_depth

    seen = []
    rule = {"name": "s249_rule", "trigger_table": "t", "mapper": "builtin:s249",
            "follow_up": True}
    monkeypatch.setattr(worker, "_rules_for_the_follow_up_pass", lambda: [rule])
    monkeypatch.setitem(builtins.BUILTIN_KINDS, "builtin:s249",
                        lambda db, r, **kw: seen.append(request_chain_depth.get()) or
                        {"written": 0})

    worker._run_the_follow_up_pass(None, {"table": "t", "row_ids": ["r1"],
                                         "transaction_id": "tx-1", "chain_depth": 4})

    assert seen == [5], "the lap did not run one hop past its cause"
    assert request_chain_depth.get() is None, "the hop leaked out of the lap"


def test_a_lap_with_no_incoming_hop_still_counts_as_the_first(monkeypatch):
    """⚠️ AN ORDINARY EDIT STARTS THE CASCADE AT HOP 1, not at hop 0: the write this lap makes
    IS one step, and calling it zero would give the first chain write a free hop."""
    from chain import builtins
    from database.context import request_chain_depth

    seen = []
    rule = {"name": "s249_rule", "trigger_table": "t", "mapper": "builtin:s249",
            "follow_up": True}
    monkeypatch.setattr(worker, "_rules_for_the_follow_up_pass", lambda: [rule])
    monkeypatch.setitem(builtins.BUILTIN_KINDS, "builtin:s249",
                        lambda db, r, **kw: seen.append(request_chain_depth.get()) or
                        {"written": 0})

    worker._run_the_follow_up_pass(None, {"table": "t", "row_ids": ["r1"],
                                         "transaction_id": "tx-1"})

    assert seen == [1]


def test_the_dispatcher_skips_a_cause_it_already_served(monkeypatch, caplog):
    """⛔ AND IT SAYS SO. A skip nobody can see is the silence every refusal in this product
    exists to break - 「로그에만 있는 스킵은 아무도 보지 못하는 스킵이다」 one level up."""
    import logging

    from chain import builtins

    calls = []
    rule = {"name": "s249_rule", "trigger_table": "t", "mapper": "builtin:s249",
            "follow_up": True}
    monkeypatch.setattr(worker, "_rules_for_the_follow_up_pass", lambda: [rule])
    monkeypatch.setitem(builtins.BUILTIN_KINDS, "builtin:s249",
                        lambda db, r, **kw: calls.append(kw.get("row_ids")) or
                        {"written": 0})
    done = {"table": "t", "row_ids": ["r1"], "transaction_id": "tx-1", "chain_depth": 1}

    with caplog.at_level(logging.INFO):
        worker._run_the_follow_up_pass(None, dict(done))
        worker._run_the_follow_up_pass(None, dict(done))

    assert calls == [["r1"]], "the second pass ran the rule again"
    assert "이미 한 번 받았습니다" in " ".join(r.getMessage() for r in caplog.records)


def test_a_different_cause_still_reaches_the_rule(monkeypatch):
    """🔴 GATE Ⅲ: 따라가기가 죽지 않았다. The whole risk of this change is that it silences a
    follow-up that should have run."""
    from chain import builtins

    calls = []
    rule = {"name": "s249_rule", "trigger_table": "t", "mapper": "builtin:s249",
            "follow_up": True}
    monkeypatch.setattr(worker, "_rules_for_the_follow_up_pass", lambda: [rule])
    monkeypatch.setitem(builtins.BUILTIN_KINDS, "builtin:s249",
                        lambda db, r, **kw: calls.append(kw.get("row_ids")) or
                        {"written": 0})

    worker._run_the_follow_up_pass(None, {"table": "t", "row_ids": ["r1"],
                                         "transaction_id": "tx-1"})
    worker._run_the_follow_up_pass(None, {"table": "t", "row_ids": ["r1"],
                                         "transaction_id": "tx-2"})

    assert calls == [["r1"], ["r1"]]


# ---------------------------------------------------------------------------
# 🔴 ⓔ — the lap collapses its events, and one line says why it ran
# ---------------------------------------------------------------------------

def test_the_lap_writes_inside_the_collapsed_outbox_mode(monkeypatch):
    """🔴 [ⓔ-1] ONE EVENT, NOT ONE PER ROW. Per-row events made 1,000 follow-up writes into
    1,000 outbox events, 1,000 queue items, 1,000 laps and 1,000 lines - the owner's
    「한 행당 로그 하나」. The group path has collapsed its writes since OUTBOX-4; the lap had
    not, and it is the same context manager for the same reason."""
    import event_constants
    from chain import builtins
    from database.context import request_outbox_mode

    seen = []
    rule = {"name": "s249_rule", "trigger_table": "t", "mapper": "builtin:s249",
            "follow_up": True}
    monkeypatch.setattr(worker, "_rules_for_the_follow_up_pass", lambda: [rule])
    monkeypatch.setitem(builtins.BUILTIN_KINDS, "builtin:s249",
                        lambda db, r, **kw: seen.append(request_outbox_mode.get()) or
                        {"written": len(kw.get("row_ids") or ())})
    # 🔴 [판정 497 ⓒ] THE ENVELOPE FOLLOWS THE REGISTERED FACT, NOT THE `builtin:` PREFIX.
    #    A kind is self-writing because it SAID SO at registration, so a probe that reaches
    #    the table without saying it gets no envelope - correctly. Declared here rather than
    #    inferred, which is the property that lets a PROPOSING kind be added tomorrow without
    #    every seat being edited.
    monkeypatch.setattr(builtins, "SELF_WRITING_KINDS",
                        builtins.SELF_WRITING_KINDS | {"builtin:s249"})

    worker._run_the_follow_up_pass(None, {"table": "t", "row_ids": ["r%d" % n
                                                                  for n in range(1000)],
                                         "transaction_id": "tx-1", "chain_depth": 1})

    assert seen == [event_constants.OUTBOX_MODE_COLLAPSED]
    assert request_outbox_mode.get() != event_constants.OUTBOX_MODE_COLLAPSED, (
        "the collapsed mode leaked out of the lap")


def test_the_line_says_what_woke_it_and_at_which_hop(caplog):
    """🔴 [ⓔ-2] 「WHY DID THIS RUN」 WAS NOT IN THE LINE. rule, kind, table and counts were
    there - everything except the change that woke it - so an operator watching a cascade
    could not tell which edit was still echoing."""
    import logging

    from chain import rule_run

    worker.forget_followup_lines()
    with caplog.at_level(logging.INFO):
        worker.log_followup_folded(worker.logger, "rule_a", "t", 2, "t#tx-1", 2, 8)

    said = " ".join(r.getMessage() for r in caplog.records)
    assert "woke_by=t#tx-1" in said and "hop=2/8" in said
    # [500 ⓓ] `table` left the message: `woke_by` carries it, so the line said it twice.
    assert "rule=rule_a" in said and "woke_by=t#tx-1" in said
    assert "table=" not in said
    # [499] ONE VOCABULARY. This line used to be tagged `[ChainBuiltin]` - a KIND's name -
    #   and the round that landed the seat made that name FALSE as well as split: the lap
    #   selects on `writes_itself` now, so a file mapper that registered it would have been
    #   logged as a builtin. The counts left too: `run_rule` says `rows_in`/`written` for
    #   this very run, under the same tag, so this line saying them was two authors.
    assert "[%s]" % rule_run.RULE_LOG_TAG in said
    assert "ChainBuiltin" not in said


def test_a_lap_that_wrote_nothing_is_debug_rather_than_noise(caplog):
    """⚠️ NOTHING WRITTEN IS THE ORDINARY CASE ON EVERY LAP. At INFO it is the noise that
    hides the laps that DID something."""
    import logging

    worker.forget_followup_lines()
    with caplog.at_level(logging.INFO):
        worker.log_followup_folded(worker.logger, "rule_a", "t", 0, "t#tx-1", 1, 8)

    assert not caplog.records, "a lap that wrote nothing spoke at INFO"


def test_a_refusal_is_said_even_when_nothing_was_written(caplog):
    """⛔ A REFUSAL IS NOT 「nothing happened」. It is the one thing an operator has to see."""
    import logging

    worker.forget_followup_lines()
    with caplog.at_level(logging.INFO):
        worker.log_followup_folded(worker.logger, "rule_a", "t", 0, "t#tx-1", 1, 8,
                                   "right table is not declared")

    assert "REFUSED: right table is not declared" in " ".join(
        r.getMessage() for r in caplog.records)


def test_the_same_pair_folds_after_the_first_line(caplog):
    """🔴 THE FIRST IS THE DIAGNOSIS, THE REST ARE A COUNT - the same hand
    `log_failure_folded` already has, for the same reason: a log that floods stops being a
    diagnosis and becomes the thing being diagnosed."""
    import logging

    worker.forget_followup_lines()
    with caplog.at_level(logging.INFO):
        for _ in range(worker.FOLLOWUP_LOG_EVERY + 1):
            worker.log_followup_folded(worker.logger, "rule_a", "t", 1, "t#tx", 1, 8)

    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 2, lines
    assert "(x%d)" % worker.FOLLOWUP_LOG_EVERY in lines[1]
