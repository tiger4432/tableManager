# -*- coding: utf-8 -*-
"""S-278 (소유자 2026-09-16). A join runs through the same door as every other chain rule —
the outbox event for a write to its trigger table — and its own writes never wake it.

🔴 THE OWNER'S RULING. A unified join used to stand `follow_up: True`, which put it on the
paced follow-up lap instead of the trigger path. S-151's 70,800-row measurement is about
how far ONE reference row can reach and it stands; which lap the work belongs on is a
different question and the owner has answered it.

⛔ AND THE PROPERTY THAT MAKES THAT SAFE IS PINNED HERE, NOT IN A COMMENT. `dt_log`'s
confirmed join is a SELF LOOP - trigger and target are the same table - so the moment it
is on the trigger path, the rows it writes produce outbox events for the table it watches.
What stops the loop is that a chain-produced event only reaches a rule that declared
`allow_chain_trigger`, and a join declares no such thing. Without that, the owner's
「인벤토리→로그 조인→다시 enrich 무한반복」 comes straight back.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                           # noqa: E402
from chain import rule_shape                                           # noqa: E402

LEFT = "s278_log"
RIGHT = "s278_inventory"

#: The self-loop shape: `on.table` is the table the join also WRITES.
SELF_LOOP = {
    "name": "s278_confirmed", "enabled": True,
    "on": {"table": LEFT},
    "derive": {"kind": "join", "join": {"right_table": RIGHT,
                                        "on": [{"left": "job", "right": "job"}],
                                        "take": [{"column": "lot", "as": "lot_confirmed"}]}},
    "into": {"table": LEFT},
}


def _stood(declaration):
    internal = rule_shape.from_declaration(declaration)
    return [rule_shape.as_chain_rule(internal)] + rule_shape.companion_rules(internal)


def _event(source_name, table=LEFT):
    return {"payload": {"source_name": source_name, "table_name": table}}


# ---------------------------------------------------------------------------
# 🔴 ⓐ — on the trigger path, both halves
# ---------------------------------------------------------------------------

def test_neither_half_of_a_join_stands_as_a_follow_up():
    """🔴 THE RULING, AS THE CELL THE DISPATCHER READS. `_rule_accepts_event` returns False
    for a follow-up kind before it looks at anything else, so this cell IS which lap the
    rule runs on."""
    primary, companion = _stood(SELF_LOOP)

    assert not primary.get("follow_up"), primary
    assert not companion.get("follow_up"), companion
    assert primary["trigger_table"] == LEFT
    assert companion["trigger_table"] == RIGHT, "the reference half watches the right table"


def test_an_ordinary_write_to_the_trigger_table_reaches_both_halves():
    """A write somebody else made is what a join is for. Asserted through the dispatcher's
    own predicate rather than by reading the cell back."""
    primary, companion = _stood(SELF_LOOP)

    assert worker._rule_accepts_event(primary, _event("file_ingestion")) is True
    assert worker._rule_accepts_event(companion, _event("file_ingestion", RIGHT)) is True


# ---------------------------------------------------------------------------
# ⛔ ⓑ — and its own writes do not wake it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("half", [0, 1], ids=["target-side", "reference-side"])
def test_a_joins_own_write_does_not_wake_it_again(half):
    """🔴 THE PING-PONG GATE, AND IT IS WHY THIS ROUND IS SAFE. `s278_confirmed` writes to
    `s278_log`, the very table its target half watches, with
    `source_name=chain_ingestion`. A chain-produced event reaches a rule ONLY if that rule
    declared `allow_chain_trigger`; a join declares none, so the loop closes here.

    ⛔ THE OWNER HAS MET THE OTHER OUTCOME: 「인벤토리→로그 조인→다시 enrich 무한반복」.
    That is what this assertion is standing in front of."""
    rule = _stood(SELF_LOOP)[half]

    assert "allow_chain_trigger" not in rule, (
        "a join that opted into chain-produced events would feed itself")
    assert worker._rule_accepts_event(rule, _event("chain_ingestion")) is False
    assert worker._rule_accepts_event(rule, _event("chain_ingestion", RIGHT)) is False


def test_the_opt_in_still_works_for_a_rule_that_declares_it():
    """⚠️ THE SENSITIVITY CONTROL. An assertion that chain events are always refused would
    pass on a build with the opt-in removed entirely, and that opt-in is what lets a
    declared cascade run at all."""
    primary = dict(_stood(SELF_LOOP)[0], allow_chain_trigger=True)

    assert worker._rule_accepts_event(primary, _event("chain_ingestion")) is True
