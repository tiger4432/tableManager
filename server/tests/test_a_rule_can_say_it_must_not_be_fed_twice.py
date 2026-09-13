# -*- coding: utf-8 -*-
"""S-155 (판정 384). 재시도는 «같은 봉투»를 그대로 다시 먹인다 — 그것을 견디는지는 아무 데도 없었다.

🔴 MEASURED, NOT ASSUMED. The drain filters `processed_chain == False` and NOTHING ELSE, a
failed group keeps that flag, and its payload is not touched - so the next sweep hands the
mapper the same bytes. Whether a mapper survives that was in its author's head, and its body
is in a gitignored file.

🔴 AND WHAT MAKES A RETRY SAFE TODAY IS THE BUSINESS KEY, NOT THE MAPPER.
`crud._get_or_create_row` finds a row by `row_id` or `business_key_val` and MINTS one when
neither is there, so a mapper emitting rows without an identity grows the table on every
retry. That is S-226, queued; this round is the cell that lets a rule say 「do not do that to
me」.

⚠️ IT IS AN OPT-OUT, AND THAT IS THE WHOLE SHAPE. The default has to be today's behaviour, so
「this mapper is idempotent」 would change nothing - a cell whose declared value does nothing
is the defect S-152 and S-221 each closed once. Only `false` is an instruction.

⚠️ AND IT GOES THROUGH THE CAP THAT ALREADY EXISTS. A second seat comparing `idempotent`
against a retry count of its own would be the two-paths defect on the very axis this closes:
the verdict, the isolation reason and the log all read `max_group_attempts`.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings                                                  # noqa: E402
from chain import ingestion_worker as worker                           # noqa: E402
from chain import replay                                               # noqa: E402
from chain.cell_layer import ReplayRefused                             # noqa: E402
from database import crud                                              # noqa: E402
from test_chain_hol_scheduling import FakeDB, FakeEvent                # noqa: E402

TRIGGER = "s155_src"
REPEATS_BADLY = {"name": "repeats_badly", "trigger_table": TRIGGER,
                 "target_table": "s155_out", "enabled": True, "idempotent": False}
SAFE = dict(REPEATS_BADLY, name="safe", idempotent=True)
SAYS_NOTHING = {"name": "plain", "trigger_table": TRIGGER, "target_table": "s155_out",
                "enabled": True}


# ---------------------------------------------------------------------------
# 🔴 gate ⓐ - the cap, through the ONE function
# ---------------------------------------------------------------------------

def test_a_rule_that_is_not_idempotent_gets_one_attempt():
    assert worker.max_group_attempts(REPEATS_BADLY, {"max_group_attempts": 9}) == 1


@pytest.mark.parametrize("rule", [SAYS_NOTHING, SAFE], ids=["absent", "true"])
def test_saying_nothing_and_saying_true_are_the_same_answer(rule):
    """⚠️ THE NO-REGRESSION AND THE SHAPE AT ONCE. If `true` did something, the cell would
    have two meanings and the default would no longer be today's behaviour."""
    assert worker.max_group_attempts(rule, {"max_group_attempts": 9}) == 9
    assert worker.max_group_attempts(rule, {}) == 1


def test_only_false_is_an_instruction():
    """⚠️ `is False`, NOT FALSINESS. `0` and `''` are a typo, not a declaration that a mapper
    repeats badly - and the refusal below is where a typo is answered."""
    assert worker.max_group_attempts(dict(REPEATS_BADLY, idempotent=0),
                                     {"max_group_attempts": 9}) == 9


# ---------------------------------------------------------------------------
# 🔴 gate ⓑ - the seat, RUN: one failure and the group is out
# ---------------------------------------------------------------------------

def _failing_group(monkeypatch, document=None):
    async def always_fails(tx_id, events, db, rules):
        return False, f"boom:{tx_id}", []

    monkeypatch.setattr(worker, "process_chain_transaction_group", always_fails)
    monkeypatch.setattr(worker, "_RULES_DOCUMENT", document or {"max_group_attempts": 9})
    event = FakeEvent("s155_uuid", TRIGGER, "s155_tx")
    return ["s155_tx"], {"s155_tx": [event]}, event


@pytest.mark.anyio
async def test_the_group_of_a_non_idempotent_rule_is_isolated_on_the_first_failure(monkeypatch):
    """🔴 THE BEHAVIOUR. The document says nine attempts and the rule still gets one."""
    order, groups, event = _failing_group(monkeypatch)

    await worker.process_pending_groups(FakeDB(), order, groups, [REPEATS_BADLY],
                                        lambda: FakeDB())

    assert (event.retry_count, event.status) == (1, "FAILED")
    assert event.processed_chain is True


@pytest.mark.anyio
async def test_the_same_group_under_a_rule_that_says_nothing_is_retried(monkeypatch):
    """⚠️ THE CONTROL. Without it the cap could be 1 for everything and the test above would
    still pass."""
    order, groups, event = _failing_group(monkeypatch)

    await worker.process_pending_groups(FakeDB(), order, groups, [SAYS_NOTHING],
                                        lambda: FakeDB())

    assert (event.retry_count, event.status) == (1, "RETRYING")


@pytest.mark.anyio
async def test_the_reason_the_operator_reads_names_the_one_attempt(monkeypatch, caplog):
    """🔴 「이름 대어」. An isolation an operator cannot explain is one they undo by guessing."""
    import logging

    order, groups, _event = _failing_group(monkeypatch)

    with caplog.at_level(logging.WARNING):
        await worker.process_pending_groups(FakeDB(), order, groups, [REPEATS_BADLY],
                                            lambda: FakeDB())

    said = " ".join(record.getMessage() for record in caplog.records)
    assert "repeats_badly" in said, said
    assert "idempotent: false" in said, said


# ---------------------------------------------------------------------------
# 🔴 gate ⓒ - replay refuses, and `force` is the only way past
# ---------------------------------------------------------------------------

def test_replaying_a_non_idempotent_rule_is_refused_by_name():
    """🔴 A REPLAY IS A BIGGER RE-FEED THAN A RETRY - a retry hands back one failed group, a
    replay hands over the trigger table's whole current contents."""
    with pytest.raises(ReplayRefused) as caught:
        replay.replay_rule(None, REPEATS_BADLY)

    assert "repeats_badly" in str(caught.value)
    assert "idempotent: false" in str(caught.value)
    assert "force" in str(caught.value)


@pytest.mark.parametrize("rule", [SAYS_NOTHING, SAFE], ids=["absent", "true"])
def test_replay_does_not_refuse_a_rule_that_did_not_opt_out(rule):
    """⚠️ THE CONTROL, and it must fail for a DIFFERENT reason - these rules declare no
    columns, so the replay stops later and elsewhere."""
    with pytest.raises(Exception) as caught:
        replay.replay_rule(None, rule)

    assert "idempotent" not in str(caught.value), str(caught.value)


def test_force_is_the_only_way_past_and_it_gets_past():
    """⚠️ The refusal must be reachable AND liftable, or it is a wall rather than a gate."""
    with pytest.raises(Exception) as caught:
        replay.replay_rule(None, REPEATS_BADLY, force=True)

    assert "idempotent" not in str(caught.value), str(caught.value)


def test_replay_all_asks_before_it_starts(monkeypatch):
    """🔴 REFUSING INSIDE THE LOOP WOULD STOP THE RUN WITH THE RULES ABOVE IT APPLIED, which
    is a worse state than not starting. The sentinel proves nothing ran."""
    ran = []

    monkeypatch.setattr(replay, "load_rules", lambda: [SAYS_NOTHING, REPEATS_BADLY])
    monkeypatch.setattr(replay, "order_rules", lambda rules: list(rules))
    monkeypatch.setattr(replay, "replay_rule",
                        lambda *a, **k: ran.append(a[1].get("name")) or {})

    with pytest.raises(ReplayRefused):
        replay.replay_all(None, log=lambda *_: None)

    assert ran == [], "a rule ran before the refusal"


# ---------------------------------------------------------------------------
# 🔴 gate ⓓ - the cell is declared, and a value that is not a boolean is refused
# ---------------------------------------------------------------------------

def test_the_cell_is_in_the_grammar_and_the_skeleton_draws_it_as_a_flag():
    assert chain_bindings.IDEMPOTENT_KEY == "idempotent"
    assert chain_bindings.IDEMPOTENT_KEY in chain_bindings.RULE_ROUTING_OPTIONAL
    assert chain_bindings.IDEMPOTENT_KEY in chain_bindings.routing_keys()


def _refusals(rule, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TRIGGER, {"column_types": {"lot": "string"}})
    return [issue.code for issue in chain_bindings.rule_refusals(
        rule, "rule", mapper_resolvable=lambda name: True)]


@pytest.mark.parametrize("written", ["false", "no", 0, 1, None])
def test_a_value_that_is_not_a_boolean_is_refused(monkeypatch, written):
    """🔴 `"false"` IS A YES TO EVERY TRUTH TEST IN PYTHON, and this cell decides whether a
    failed group is handed back to a mapper. A value that cannot be read is not guessed at."""
    rule = dict(REPEATS_BADLY, mapper="m", idempotent=written)

    assert "bad_idempotent" in _refusals(rule, monkeypatch)


@pytest.mark.parametrize("written", [True, False], ids=["true", "false"])
def test_a_boolean_is_accepted(monkeypatch, written):
    """⚠️ THE CONTROL for both values - a branch that refused `false` would refuse the only
    value this cell exists to carry."""
    rule = dict(REPEATS_BADLY, mapper="m", idempotent=written)

    assert _refusals(rule, monkeypatch) == []
