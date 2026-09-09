# -*- coding: utf-8 -*-
"""S-99. One relation, two predicates, and the declaration says which rows mean which.

🔴 THE GRAMMAR HAD NOWHERE TO PUT THIS. A single event relation can hold rows meaning one
thing and rows meaning its opposite, and every sentence a source declared was said for
EVERY row. The only workaround was a qualifier, which does not answer it: `follow` selects
by PREDICATE, so both sentences would still be uttered and the walk would still see both.

Two lines an operator can act on:
    「소스의 `bind.mappings.<문장>.when` 에 {event_type: split} 을 적으면 됩니다.」

⚠️ NOT A REFUSAL AND NOT AN EXCLUSION. A row that does not match says nothing for THIS
sentence and stays free to say another - which is what separates it from S-91's
`exclude_when`, where the row is not the source's at all. It shows up as the per-sentence
atom count of a test run, never as an error.

⛔ EQUALITY ONLY, AS A MAP. Keys are ANDed; no list, no range, no OR, no comparison - the
same shape `entities.references[].from.when` already has, which ruling 195 named as the
model.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.roleframe import _unit_says, map_event_frame              # noqa: E402
from ledger.source_preparation import locked_select_columns          # noqa: E402
from test_ledger_setup_bundle import (                               # noqa: E402
    logical_bundle, logical_catalog, source_profile, validate_bundle_errors)
from test_ledger_setup_registry import snapshot                      # noqa: E402
from test_ledger_roleframe import (                                  # noqa: E402
    event_frame, implementations, mapper_context)


def paths_of(bundle):
    return {issue.path for issue in
            validate_bundle_errors(bundle, catalog=logical_catalog())}


def _mappings(bundle):
    return bundle["sources"]["input_rows"]["bind"]["mappings"]


def _with_when(when, sentence=None):
    raw = logical_bundle()
    mappings = _mappings(raw)
    name = sentence or sorted(mappings)[0]
    mappings[name]["when"] = when
    return raw


# ----------------------------------------------------------------- the judgement

def test_every_row_of_the_unit_must_match_before_the_sentence_is_said():
    """🔴 판정 195's GROUP RULE, and it is the only new judgement in this round.

    One expression covers both unit kinds on purpose. A row-unit source has a single row
    here, so this reads as "this row matches"; a GROUP-unit source has the whole group and
    the sentence is said only when the group agrees. Two spellings would be free to
    disagree exactly where a group is MIXED - the case nobody would have written a fixture
    for.
    """
    agreeing = {"event_type": ("split", "split")}
    mixed = {"event_type": ("split", "merge")}

    assert _unit_says(agreeing, {"event_type": "split"}) is True
    assert _unit_says(mixed, {"event_type": "split"}) is False, (
        "a group that disagrees with itself must not utter the sentence")
    assert _unit_says({"event_type": ("split",)}, {"event_type": "split"}) is True


def test_the_clauses_are_anded_and_a_missing_column_says_nothing():
    unit = {"event_type": ("split",), "reason": ("planned",)}

    assert _unit_says(unit, {"event_type": "split", "reason": "planned"}) is True
    assert _unit_says(unit, {"event_type": "split", "reason": "other"}) is False

    # Declared and absent from THIS unit: the validator already refused unknown columns at
    # load, so a sentence about a value that is not here is simply not said.
    assert _unit_says(unit, {"absent": "x"}) is False


def test_equality_is_spelled_once_so_one_matches_one_point_zero():
    """⑤. `clean_str_value` folds both sides - the same function the business key and the
    preparer's key parts are built with. A second spelling here would disagree with them
    about exactly these values: `1` against `1.0`, and padding."""
    assert _unit_says({"n": (1.0,)}, {"n": 1}) is True
    assert _unit_says({"n": ("1",)}, {"n": 1.0}) is True
    assert _unit_says({"code": ("  A  ",)}, {"code": "A"}) is True
    assert _unit_says({"code": ("B",)}, {"code": "A"}) is False


# --------------------------------------------------------------------- the read

def test_a_column_named_only_by_a_when_still_reaches_the_read():
    """The same gap S-91 opened, one clause over: a `when` column is neither an identity, a
    key, nor anybody's declared input, so nothing else would select it."""
    without = locked_select_columns(identity=["event_key"])
    assert "named_only_by_when" not in without

    with_clause = locked_select_columns(
        identity=["event_key"], condition_columns=["named_only_by_when"])
    assert "named_only_by_when" in with_clause
    assert set(without) <= set(with_clause), "the term ADDS; it may not take anything away"


def test_a_when_naming_a_preparer_output_is_not_asked_of_the_relation():
    """⛔ A preparer OUTPUT is produced, not selected. Asking the relation for it would be
    `UndefinedColumn` on the cursor path."""
    columns = locked_select_columns(
        identity=["event_key"], preparer_outputs=["made_here"],
        condition_columns=["made_here"])

    assert "made_here" not in columns


# ----------------------------------------------------------------- the refusals

def test_a_column_the_prepared_frame_does_not_have_is_refused_by_name():
    new = paths_of(_with_when({"not_a_column": "x"})) - paths_of(logical_bundle())

    assert any(path.endswith("when.not_a_column") for path in new), sorted(new)


def test_an_empty_condition_and_a_non_scalar_value_are_refused():
    """⛔ An empty map is not "no condition" - it is a sentence whose author meant to write
    one. And a nested value is the beginning of the query language this grammar is not."""
    before = paths_of(logical_bundle())

    assert paths_of(_with_when({})) - before, "an empty condition must not be accepted"
    assert paths_of(_with_when({"event_key": ["a", "b"]})) - before, (
        "a list is a comparison operator wearing a value's clothes")
    assert paths_of(_with_when({"event_key": {"gt": 1}})) - before


# --------------------------------------------------------- the per-sentence count

def _two_sentences(when_a=None, when_b=None):
    """One source, the SAME predicate twice, told apart by which rows it is said for."""
    raw = logical_bundle()
    mappings = source_profile(raw)["mappings"]
    import copy as _copy
    mappings["second_transition"] = _copy.deepcopy(mappings["main_transition"])
    if when_a is not None:
        mappings["main_transition"]["when"] = when_a
    if when_b is not None:
        mappings["second_transition"]["when"] = when_b
    return raw


def _say(raw, source_id):
    """One unit - one row - through the real mapper. Returns the sentences it said.

    ⚠️ ONE ROW PER FRAME ON PURPOSE. A frame carrying several rows is ONE mapper unit, not
    several, so a three-row frame would exercise the GROUP reading (pinned separately
    below) rather than the per-row one this count is about. Learned by measuring: the
    first draft handed three rows in and got zero emissions - which was the group rule
    working, not the clause failing.
    """
    compiled = snapshot(raw)
    context = mapper_context(compiled, "input_rows")
    frame = event_frame(compiled, [{
        "source_id": source_id, "target_id": "OUT-1",
        "event_at": None, "event_key": "E-1",
    }])
    out = map_event_frame(context, frame, implementations())
    return sorted(out["sentence"].tolist())


def test_three_rows_two_sentences_and_each_is_said_once():
    """🔴 THE END-TO-END COUNT: 1 + 1 + 0. One sentence names the first row, the other
    names the second, and the third says NOTHING - not refused, not excluded, it simply
    matches neither."""
    raw = _two_sentences({"source_id": "IN-1"}, {"source_id": "IN-2"})

    assert _say(raw, "IN-1") == ["main_transition"]
    assert _say(raw, "IN-2") == ["second_transition"]
    assert _say(raw, "IN-3") == []


def test_without_the_clause_both_sentences_are_said_for_every_row():
    """⛔ THE MUTATION AS A CASE: 3 + 3. Same bundle, same rows, no `when`. If the clause
    stopped being read this would keep passing only if the test above started failing, so
    the pair is what pins the feature rather than either alone."""
    raw = _two_sentences()

    for source_id in ("IN-1", "IN-2", "IN-3"):
        assert _say(raw, source_id) == ["main_transition", "second_transition"]


def test_a_group_unit_says_nothing_unless_the_whole_group_agrees():
    """🔴 판정 195's GROUP RULE, end to end rather than on the predicate alone. A frame of
    several rows is ONE unit; the sentence is said only if every row of it matches."""
    raw = _two_sentences({"source_id": "IN-1"}, {"source_id": "IN-2"})
    compiled = snapshot(raw)
    context = mapper_context(compiled, "input_rows")
    mixed = event_frame(compiled, [
        {"source_id": "IN-1", "target_id": "OUT-1", "event_at": None, "event_key": "E-1"},
        {"source_id": "IN-2", "target_id": "OUT-1", "event_at": None, "event_key": "E-1"},
    ])

    assert map_event_frame(context, mixed, implementations()).empty, (
        "a group that disagrees with itself must utter neither sentence")


# ------------------------------------------------------------- S-105: the self edge

def _entity(column, entity_type="InputEntity@1", key="input_id"):
    return {"kind": "entity", "approval_status": "approved", "entity_type": entity_type,
            "keys": {key: {"kind": "column", "approval_status": "approved",
                           "column": column}}}


def test_a_sentence_may_not_read_the_same_identity_at_both_ends():
    """🔴 S-105. THE SHAPE OF MY OWN DEFECT, pinned.

    The `split`/`merge` example I added in S-99 bound subject AND target to one column, so it
    said a thing came from itself. Every column existed and every type checked - the
    statement was simply empty - and it reached the shipped sample because I copied a working
    mapping and changed only the predicate and the condition.

    ⛔ AVAILABILITY WOULD NOT HAVE CAUGHT IT: the column was one of that source's own preparer
    outputs, so it was perfectly readable. This asks about MEANING, which is a different
    question and needs its own check.
    """
    raw = logical_bundle()
    mapping = _mappings(raw)[sorted(_mappings(raw))[0]]
    mapping["bind"]["subject"] = _entity("source_id")
    mapping["bind"]["target"] = _entity("source_id", "OutputEntity@1", "output_id")

    new = paths_of(raw) - paths_of(logical_bundle())

    assert any(path.endswith("bind.mappings." + sorted(_mappings(logical_bundle()))[0])
               for path in new), sorted(new)


def test_sharing_one_key_column_of_several_is_not_a_self_edge():
    """⚠️ EQUALITY, NOT OVERLAP. Two entities of one type may legitimately share SOME key
    column; refusing on overlap would refuse ordinary declarations."""
    raw = logical_bundle()
    name = sorted(_mappings(raw))[0]
    mapping = _mappings(raw)[name]
    mapping["bind"]["subject"] = _entity("source_id")
    target = _entity("source_id", "OutputEntity@1", "output_id")
    target["keys"]["second"] = {"kind": "column", "approval_status": "approved",
                                "column": "target_id"}
    mapping["bind"]["target"] = target

    new = paths_of(raw) - paths_of(logical_bundle())

    assert not any(path.endswith("bind.mappings." + name) for path in new), sorted(new)
