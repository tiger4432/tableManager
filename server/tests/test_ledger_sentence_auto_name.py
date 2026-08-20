"""A SentenceShape carries the name of the sentence it says, and that name IS the wiring.

Two shape-identical sentences used to be told apart by a string the mapper declared
TWICE -- once as a class constant, once again at the call site -- beside the same word a
third time in the Profile.  Two of those three are the mapper's own vocabulary, and Python
already records the one that matters: the class attribute the shape was bound to.
``SentenceShape.__set_name__`` takes it instead of asking for it again.

🔴 WHAT CHANGED ON 2026-08-21, and why half this file is a retirement notice.  The name
used to be the LAST discriminator -- structure first (object-ness, qualifier names, two
entity-type spellings), the name only to break a tie.  The owner's ruling made it the
first and only one: 「맵퍼 구조를 문장에 별명을 붙여 부르게 만들고 그 별명에 바인드를 한다면?」.
So the properties this file pinned about tiebreak behaviour do not have weaker versions;
they have no subject.  They are retired by name, next to what replaced them.
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
    """...and every name the mapper has is a key the Profile files a mapping under.

    Read from the fixture rather than restated: the two sides agreeing is the whole
    mechanism, and a literal here would still be green on the day the declaration stopped
    matching and the mapper stopped resolving.
    """
    declared = set(lot_event_bundle()["sources"]["lot_event"]["bind"]["mappings"])
    said = {shape.sentence for shape in vars(LotEventRoleMapper).values()
            if isinstance(shape, SentenceShape)}

    assert LotEventRoleMapper.SPLIT_SLOT_CARRY.sentence == "split_slot_carry"
    assert LotEventRoleMapper.MERGE_SLOT_JOIN.sentence == "merge_slot_join"
    assert said == declared, (
        "every sentence the mapper can say is a mapping key, and nothing else is")
    # The two slot-map shapes are otherwise identical: the NAME is the only thing telling
    # them apart, which is what makes it selection rather than decoration.
    assert (LotEventRoleMapper.SPLIT_SLOT_CARRY
            == LotEventRoleMapper.MERGE_SLOT_JOIN), (
        "the two are EQUAL as values -- `sentence` is compare=False -- so nothing but "
        "the name they were bound to can separate them")
    assert (LotEventRoleMapper.SPLIT_SLOT_CARRY.sentence
            != LotEventRoleMapper.MERGE_SLOT_JOIN.sentence)


def test_the_shapes_own_name_selects_the_mapping_end_to_end():
    """The mapper passes no selector anywhere and still lands the right mapping, which is
    what each atom's `derivation` records -- and the `derivation` is now the sentence."""
    assert slot_map_derivations(split_rows()) == ["split_slot_carry"]
    assert slot_map_derivations(merge_rows()) == ["merge_slot_join"]


def test_one_shape_bound_to_two_attribute_names_is_refused_at_class_creation():
    """🔴 The failure class this project keeps getting bitten by, refused where it starts.

    A shared instance would carry ONE name, so one of the two call sites would say a
    sentence it did not mean -- silently, and correctly for exactly as long as the two
    happen to resolve the same way.  This is what the mapper did before the change, so
    the refusal has to fire at class creation rather than at the call that guesses wrong.
    """
    shared = SentenceShape(qualifiers=("from", "to", "wafer"))

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


# RETIRED: test_an_explicit_sentence_still_wins_over_the_shapes_own_name.
# It passed `sentence="merge_slot_join"` to override the shape's own name. `say()` takes
# no selector of any kind since 2026-08-21 -- there is one name and the call site cannot
# disagree with it -- so the property has no subject rather than a weaker form.
#
# RETIRED: test_a_unique_shape_resolves_even_though_no_mapping_names_it.
# Its premise was a mapping that declares no sentence, which kept the change config-free
# while the name was a tiebreak. `mappings` is a map keyed by the sentence now, so a
# mapping with no name is not a document that can be written.
#
# What both of them were really protecting -- that a shape the declaration does not know
# fails LOUDLY rather than resolving to whichever mapping happened to match -- is the one
# property that survives them both, so it is asserted here.
def test_a_sentence_no_mapping_realizes_is_a_named_refusal_that_lists_the_ones_that_are():
    class NamedAfterNothingInTheConfig:
        MISLABELLED = SentenceShape(qualifiers=("from", "to", "wafer"))

    shape = NamedAfterNothingInTheConfig.MISLABELLED
    assert shape.sentence == "mislabelled"

    with pytest.raises(RoleFrameError) as caught:
        sentences_for_lot_event().say(
            shape, "P", ("R1",), obj="C",
            qualifiers={"from": "1", "to": "5", "wafer": "W1"})

    assert caught.value.code == "unresolved_sentence"
    assert "'mislabelled'" in caught.value.message
    # The refusal has to name what IS declared, or an author cannot tell a typo from a
    # sentence that was never wired.
    assert "'merge_slot_join'" in caught.value.message


def test_an_unbound_shape_says_nothing_rather_than_matching_by_structure():
    """A shape built inline has no name, and a name is now the whole of selection.

    While structure decided, such a shape resolved perfectly well -- it is exactly how
    `say()` was called before names existed.  It must refuse now, by its own code, rather
    than reach a mapping through a resemblance.
    """
    unbound = SentenceShape(qualifiers=("from", "to", "wafer"))
    assert unbound.sentence is None

    with pytest.raises(RoleFrameError) as caught:
        sentences_for_lot_event().say(
            unbound, "P", ("R1",), obj="C",
            qualifiers={"from": "1", "to": "5", "wafer": "W1"})
    assert caught.value.code == "unnamed_sentence"
