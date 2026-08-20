"""A SentenceShape carries the name of the sentence it says.

Two shape-identical sentences used to be told apart by a string the mapper declared
TWICE -- once as a class constant, once again at the call site -- beside the same word a
third time in the Profile.  Two of those three are the mapper's own vocabulary, and Python
already records the one that matters: the class attribute the shape was bound to.
``SentenceShape.__set_name__`` takes it instead of asking for it again.

What the declaration says is unchanged, and that is the property these tests pin hardest:
the auto name is a TIEBREAK, never a filter.  A shape whose match is already unique
resolves exactly as before even when no mapping mentions its name -- otherwise every
existing mapper would need a config edit to keep working, and one of them is being written
by its owner today.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ledger.roleframe import (
    ProfileSentences,
    RoleFrameError,
    SentenceShape,
    mapper_context,
)
from mappers.ledger_v2_lot_event_role_mapper import LotEventRoleMapper
from test_ledger_v2_lot_event_parity import (
    NOW,
    compiled_lot_event,
    lot_event_bundle,
    preview,
    split_rows,
)


def merge_rows():
    """The merge half of the ambiguous pair -- `split_rows()` covers the other half.

    Wafers W1/W2 sit in the parent's slots 1/2 and land in the child's slots 5/6, so the
    slot map genuinely MOVES them.  A merge whose slots happened to match the parent's
    would produce the same atoms as a split carry and prove nothing about which sentence
    was resolved.
    """
    return pd.DataFrame([
        {"lot": "P", "event_type": "merge", "slots": "1:2",
         "wafers": "W1:W2", "parent_lot": "", "child_lot": "C",
         "row_identity": "M1", "event_time": NOW},
        {"lot": "C", "event_type": "merge", "slots": "5:6",
         "wafers": "W1:W2", "parent_lot": "P", "child_lot": "",
         "row_identity": "M2", "event_time": NOW},
    ], dtype=object)


def slot_map_derivations(frame):
    return sorted({item["derivation"] for item in preview(frame, known=()).candidate_semantics
                   if item["predicate"] == "slot_map"})


def test_a_shape_is_named_by_the_attribute_it_was_bound_to():
    """...and the two names the mapper needs are the ones the Profile already declares.

    Read from the fixture rather than restated, because the whole reason this change
    touches no config is that these strings already agree.  Asserting the pair against a
    literal here would still be green on the day the declaration changed and the mapper
    stopped resolving.
    """
    declared = {mapping["sentence"]
                for mapping in lot_event_bundle()["sources"]["lot_event"]["profile"]["mappings"]
                if mapping.get("sentence")}

    assert LotEventRoleMapper.SPLIT_SLOT_CARRY.sentence == "split_slot_carry"
    assert LotEventRoleMapper.MERGE_SLOT_JOIN.sentence == "merge_slot_join"
    assert declared == {LotEventRoleMapper.SPLIT_SLOT_CARRY.sentence,
                        LotEventRoleMapper.MERGE_SLOT_JOIN.sentence}
    # The shapes are otherwise identical: the NAME is the only thing telling them apart,
    # which is what makes this the tiebreak and not decoration.
    assert (LotEventRoleMapper.SPLIT_SLOT_CARRY.has_object
            == LotEventRoleMapper.MERGE_SLOT_JOIN.has_object)
    assert (LotEventRoleMapper.SPLIT_SLOT_CARRY.qualifiers
            == LotEventRoleMapper.MERGE_SLOT_JOIN.qualifiers)


def test_the_shapes_own_name_breaks_the_tie_the_call_sites_no_longer_declare():
    """End to end: the mapper passes no `sentence=` anywhere and still lands the right
    mapping, which is what each atom's `derivation` records."""
    assert slot_map_derivations(split_rows()) == ["slot_preserving"]
    assert slot_map_derivations(merge_rows()) == ["shared_wafer"]


def test_one_shape_bound_to_two_attribute_names_is_refused_at_class_creation():
    """🔴 The failure class this project keeps getting bitten by, refused where it starts.

    A shared instance would carry ONE name, so one of the two call sites would say a
    sentence it did not mean -- silently, and correctly for exactly as long as the two
    happen to resolve the same way.  This is what the mapper did before the change, so
    the refusal has to fire at class creation rather than at the call that guesses wrong.
    """
    shared = SentenceShape(has_object=True, qualifiers=("from", "to", "wafer"))

    with pytest.raises(RoleFrameError) as caught:
        class TwoSentencesOneShape:
            SPLIT_SLOT_CARRY = shared
            MERGE_SLOT_JOIN = shared

    assert caught.value.code == "ambiguous_sentence_shape"
    assert caught.value.path.endswith("TwoSentencesOneShape.MERGE_SLOT_JOIN")
    assert "'split_slot_carry'" in caught.value.message
    assert "'merge_slot_join'" in caught.value.message


def sentences_for_lot_event():
    context = mapper_context(compiled_lot_event(), "lot_event")
    return ProfileSentences(
        context, context.source_plan.profile, occurred_at=NOW)


def test_an_explicit_sentence_still_wins_over_the_shapes_own_name():
    """The auto name is a DEFAULT, not a replacement -- a caller can still overrule it."""
    class Misnamed:
        #: No mapping declares this word, so the shape's own name cannot resolve the tie.
        MISLABELLED = SentenceShape(
            has_object=True, qualifiers=("from", "to", "wafer"))

    shape = Misnamed.MISLABELLED
    assert shape.sentence == "mislabelled"
    said = dict(obj="C", qualifiers={"from": "1", "to": "5", "wafer": "W1"},
                subject_type="Lot@1", object_type="Lot@1")
    sentences = sentences_for_lot_event()

    with pytest.raises(RoleFrameError) as caught:
        sentences.say(shape, "P", ("R1",), **said)
    assert caught.value.code == "unresolved_sentence"

    assert sentences.say(
        shape, "P", ("R1",), sentence="merge_slot_join", **said
    ).mapping_id == "shared_wafer"


def test_a_unique_shape_resolves_even_though_no_mapping_names_it():
    """The property that keeps this change config-free.

    `pair_field` declares no `sentence` -- its shape is already unique, and restating the
    obvious is how declarations rot.  If the auto name filtered instead of breaking ties,
    every such mapping would resolve to nothing and every existing mapper would need a
    config edit to keep working.
    """
    class NamedAfterNothingInTheConfig:
        DESCENT = SentenceShape(has_object=True)

    shape = NamedAfterNothingInTheConfig.DESCENT
    assert shape.sentence == "descent"
    assert not any(mapping.sentence == shape.sentence
                   for mapping in mapper_context(
                       compiled_lot_event(), "lot_event").source_plan.profile.mappings)

    assert sentences_for_lot_event().say(
        shape, "C", ("R1",), obj="P",
        subject_type="Lot@1", object_type="Lot@1").mapping_id == "pair_field"
