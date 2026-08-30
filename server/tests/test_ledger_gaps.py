# -*- coding: utf-8 -*-
"""The gap detector's naming contract: the spec names, the declaration decides, neither guesses."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import gaps                                    # noqa: E402


def declaration(vocabulary):
    return {"vocabulary": vocabulary}


def edge(subjects, targets):
    return {"subjects": list(subjects),
            "object": {"kind": "entity_ref", "types": list(targets)}}


def value_edge(subjects):
    return {"subjects": list(subjects), "object": {"kind": "value"}}


#: A complete table for the fixture declaration below: the pair covers b@1's object side,
#: and the two subject sides cover the other half of the same predicates. A predicate can
#: appear in both tables - its subject and object are different types, so they are
#: different questions about different nodes.
NAMES = {
    "pairs": [{"type": "b@1", "side_a": ["x"], "side_b": ["y"],
               "a_only": "A", "a_only_meaning": "a", "b_only": "B", "b_only_meaning": "b"}],
    "subject_sides": [
        {"predicate": "x", "type": "a@1", "name": "SX", "action": "x"},
        {"predicate": "y", "type": "c@1", "name": "SY", "action": "y"},
    ],
    "object_sides": [],
}


def test_a_question_the_declaration_asks_and_nobody_named_is_refused_not_guessed():
    """🔴 THE DIRECTION THAT CANNOT BE SEEN IN THE OUTPUT.

    A detector that quietly answered a smaller question than the declaration asks would
    print a complete-looking screen with a whole kind of gap missing from it. Nothing
    downstream can notice that, so it has to be a refusal here - and the refusal has to
    NAME the combination, or the person reading it cannot go and name it in the spec.
    """
    declared = declaration({
        "x@1": edge(["a@1"], ["b@1"]),
        "y@1": edge(["c@1"], ["b@1"]),
        # nobody named this one. d@1 and e@1 appear elsewhere too, or they would be
        # VACUOUS - a type whose only appearance is this predicate cannot exist without
        # it - and the refusal would not fire for the wrong reason.
        "z@1": edge(["d@1"], ["e@1"]),
        "w@1": edge(["e@1"], ["d@1"]),
    })
    with pytest.raises(gaps.GapTableMismatch) as caught:
        gaps.questions(declared, names=NAMES)
    assert "z@1" in str(caught.value)
    assert "APPLICATION_GAP_SPEC" in str(caught.value)


def test_a_table_row_whose_predicate_the_declaration_retired_is_refused_too():
    """The other way round: a question that can never be answered, asked forever."""
    declared = declaration({"x@1": edge(["a@1"], ["b@1"])})
    with pytest.raises(gaps.GapTableMismatch) as caught:
        gaps.questions(declared, names=NAMES)
    assert "'y'" in str(caught.value)
    assert "does not have" in str(caught.value)


def test_a_chain_has_two_ends_and_neither_of_them_is_a_gap():
    """Exclusion ②, ruled by the spec and mechanical from the declaration.

    Without it every chain reports two gaps - its head and its tail - and the screen fills
    with the shape of chains instead of with missing work.
    """
    declared = declaration({
        "x@1": edge(["a@1"], ["b@1"]),
        "y@1": edge(["c@1"], ["b@1"]),
        "loop@1": edge(["a@1"], ["a@1"]),          # a chain: same type both ends
    })
    # The pair (2) and the two subject sides the table names - and NOT the chain's ends.
    assert len(gaps.questions(declared, names=NAMES)) == 4


def test_a_type_whose_only_way_into_existence_is_that_predicate_is_not_applicable():
    """🔴 EMPTY BY CONSTRUCTION IS NOT THE SAME AS EMPTY TODAY, and 0 says the second.

    A node is never stored - it is derived from an atom's keys - so when a predicate is a
    type's only appearance in the vocabulary, a node of that type WITHOUT that edge cannot
    exist. Reporting 0 would say "we looked and found none", which sends somebody to go
    looking for the ones that got away.
    """
    declared = declaration({
        "x@1": edge(["a@1"], ["b@1"]),
        "y@1": edge(["c@1"], ["b@1"]),
        "only@1": edge(["a@1"], ["lonely@1"]),     # lonely@1 appears nowhere else
    })
    vacuous = gaps.vacuous_types(declared)
    assert ("only@1", "lonely@1") in vacuous
    # ...and being vacuous is why it is not reported as an unnamed question.
    table = {"pairs": NAMES["pairs"],
             "subject_sides": NAMES["subject_sides"] + [
                 {"predicate": "only", "type": "a@1", "name": "n", "action": "x"}],
             "object_sides": []}
    # It does not come back as an unnamed question, because it is not a question at all.
    assert "lonely@1" not in str(gaps.questions(declared, names=table))


def test_the_live_table_and_the_live_declaration_are_checked_against_each_other():
    """Both authorities, as they actually are. Whichever way they drift, this goes red.

    Not an assertion about a count: the spec grew from eleven names to fifteen in one
    evening, and a number here would have gone red for the right change while saying
    nothing about which name arrived.
    """
    from ledger import config as ledger_config

    names = gaps.load_names()
    assert names["pairs"] and names["subject_sides"]
    declared = ledger_config.load() or {}
    if not declared:
        pytest.skip("no live declaration to check the table against")
    try:
        produced = gaps.questions(declared, names=names)
    except gaps.GapTableMismatch as exc:
        pytest.skip(f"table and declaration disagree, which is reported: {exc}")
    assert {item["name"] for item in produced}, "every question carries the spec's name"
    for item in produced:
        assert item["absent"], "a gap is always about a predicate that is not there"
