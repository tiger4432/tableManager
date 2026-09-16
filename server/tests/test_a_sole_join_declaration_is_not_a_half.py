# -*- coding: utf-8 -*-
"""S-270. A join the loader did NOT split is not a half, and a row-scoped replay never
needed hiding.

🔴 THE OWNER'S REPORT: 「조인 체인이 리플레이 리스트에 안 뜨는데」 · 「조인이 참조하는게
트리거잖아」. Both true. A unified declaration may put the REFERENCE table in `on.table`,
which is `trigger_table` — and then `companion_rules` makes no companion, because a second
rule on the same trigger would run the join twice per event. The rule that stands is the
only one there is.

⛔ AND `is_reference_side` READ IT AS A HALF, because it asked the SHAPE
(`trigger == right_table != target`) instead of the fact. That shape is satisfied by a
companion AND by that sole declaration, so the only join on the owner's grid was dropped
from `replayable_rules_for` and refused by `find_rule` with a pointer at a target-side rule
THAT DOES NOT EXIST.

⚠️ THE SECOND HALF IS ABOUT SCOPE. S-242 refused the companion because replaying it
re-finds every reference row's targets, which the target side already covers — an argument
about replaying a WHOLE table. The grid's banner always sends `row_ids`; with rows picked,
re-deriving their targets is exactly what the live chain does when they move, and the
target-side rule triggers on a table that grid cannot select.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import replay, rule_shape                                  # noqa: E402

TARGET = "s270_log"
REFERENCE = "s270_inventory"

#: The owner's shape: `on.table` IS the reference table. Legal, sole, and what the old
#: predicate called a half.
SOLE = {
    "name": "s270_sole", "enabled": True,
    "on": {"table": REFERENCE},
    "derive": {"kind": "join", "join": {"right_table": REFERENCE,
                                        "on": [{"left": "job", "right": "job"}],
                                        "take": [{"column": "lot", "as": "lot_confirmed"}]}},
    "into": {"table": TARGET},
}

#: The canonical shape: `on.table` is the target, so the loader stands a companion too.
SPLIT = dict(SOLE, name="s270_split", on={"table": TARGET})


def _stood(declaration):
    internal = rule_shape.from_declaration(declaration)
    return [rule_shape.as_chain_rule(internal)] + rule_shape.companion_rules(internal)


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the companion says what it is; nothing else re-derives it
# ---------------------------------------------------------------------------

def test_a_sole_declaration_stands_one_rule_and_it_is_not_a_reference_side():
    """🔴 THE GATE, AND IT IS THE OWNER'S DECLARATION. One rule, and the predicate that
    decides 「is this a half」 must say no — there is no other half to send them to."""
    stood = _stood(SOLE)

    assert len(stood) == 1, [r["name"] for r in stood]
    assert stood[0]["trigger_table"] == REFERENCE
    assert (stood[0].get("params") or {}).get("right_table") == REFERENCE
    assert stood[0]["target_table"] == TARGET
    assert replay.is_reference_side(stood[0]) is False, (
        "the shape `trigger == right != target` is true of a SOLE declaration too")


def test_the_companion_carries_the_cell_and_the_primary_does_not():
    """⚠️ THE LOADER IS THE ONLY THING THAT KNOWS. `companion_of` names the declaration it
    was made from, so a reader never has to infer it — and the suffix stays a label."""
    primary, companion = _stood(SPLIT)

    assert companion[rule_shape.COMPANION_CELL] == "s270_split"
    assert rule_shape.COMPANION_CELL not in primary
    assert replay.is_reference_side(companion) is True
    assert replay.is_reference_side(primary) is False


def test_the_name_suffix_is_not_what_decides():
    """⛔ A NAME IS SOMETHING AN OPERATOR MAY WRITE. Parsing `:reference` out of it would
    hand a meaning only the loader may assign to whoever types that suffix — the same
    mistake as reading the property off three other cells, one layer over."""
    impostor = dict(_stood(SOLE)[0], name="s270_sole" + rule_shape.REFERENCE_SUFFIX)

    assert replay.is_reference_side(impostor) is False


# ---------------------------------------------------------------------------
# 🔴 ⓑ — one predicate: the refusal, the list and the route cannot split
# ---------------------------------------------------------------------------

def test_a_companion_is_refused_whole_and_accepted_with_rows():
    """🔴 S-242'S ARGUMENT IS ABOUT SCOPE, SO THE ANSWER IS TOO. Without rows the refusal
    stands byte for byte; with rows picked, the operator gets the one rule that can do what
    they asked."""
    stood = _stood(SPLIT)
    companion = stood[1]

    with pytest.raises(replay.ReplayRefused) as raised:
        replay.find_rule(companion["name"], stood)
    assert "follow-up half" in str(raised.value)
    assert "pick the rows" in str(raised.value), (
        "the refusal must name the way out, not only the wall")

    found = replay.find_rule(companion["name"], stood, row_scoped=True)
    assert found["name"] == companion["name"]


def test_the_sole_rule_is_never_refused_not_even_without_rows():
    """⚠️ IT IS NOT A HALF, so scope has nothing to do with it — a whole-table replay of
    the owner's join is a legitimate request and always was."""
    stood = _stood(SOLE)

    assert replay.find_rule("s270_sole", stood)["name"] == "s270_sole"
    assert replay.find_rule("s270_sole", stood, row_scoped=True)["name"] == "s270_sole"


def test_the_new_cell_is_a_cell_the_grammar_KNOWS():
    """🔴 MEASURED BEFORE IT WAS REGISTERED, AND IT WAS A LINE PER JOIN PER BOOT. A cell the
    grammar does not know is read as a mapper argument by `flat_param_cells`, so the loader
    said 「a mapper argument still written at the top level — move it under 'params'」 about
    a cell the loader itself had stamped, on every load, forever.

    ⛔ 「A permanent error line is how a real one stops being read」 — the sentence this
    repository already has in `models.py`. And ONE author for the name: `rule_shape` reads
    it off `chain_bindings`, so a rename cannot leave the grammar behind."""
    import chain_bindings

    companion = _stood(SPLIT)[1]

    assert rule_shape.COMPANION_CELL is chain_bindings.COMPANION_CELL_NAME
    assert rule_shape.COMPANION_CELL in chain_bindings.routing_keys()
    assert chain_bindings.flat_param_cells(companion) == ()
    assert chain_bindings.rule_warnings(companion) == []


def test_the_list_and_the_refusal_pass_through_one_predicate():
    """⛔ THE S-250 DEFECT IS A LIST THAT DISAGREES WITH AN EXECUTION. Asserted on the
    behaviour of the shared predicate across all four combinations rather than on either
    seat alone, because a second spelling passes any test of one seat."""
    primary, companion = _stood(SPLIT)
    sole = _stood(SOLE)[0]

    assert replay.replay_is_refused(companion, row_scoped=False) is True
    assert replay.replay_is_refused(companion, row_scoped=True) is False
    assert replay.replay_is_refused(primary, row_scoped=False) is False
    assert replay.replay_is_refused(sole, row_scoped=False) is False
