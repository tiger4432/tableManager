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


# RETIRED 2026-09-07 with the sentences they served: `merge_rows()` and
# `slot_map_derivations()`. Both existed only to drive `split_slot_carry` /
# `merge_slot_join`, which left the mapper on 2026-08-30. A helper kept past its only
# caller is a branch nothing takes, and the next reader has to prove that before deleting
# it - so it goes here, with where it went.


def test_a_shape_is_named_by_the_attribute_it_was_bound_to():
    """...and every name the mapper has is a key the Profile files a mapping under.

    Read from the fixture rather than restated: the two sides agreeing is the whole
    mechanism, and a literal here would still be green on the day the declaration stopped
    matching and the mapper stopped resolving.
    """
    declared = set(lot_event_bundle()["sources"]["lot_event"]["bind"]["mappings"])
    said = {shape.sentence for shape in vars(LotEventRoleMapper).values()
            if isinstance(shape, SentenceShape)}

    assert said == declared, (
        "every sentence the mapper can say is a mapping key, and nothing else is")

    # 🔴 THE NAME IS THE ONLY DISCRIMINATOR, ASSERTED OVER THE WHOLE SET RATHER THAN A
    # CHOSEN PAIR. This named `SPLIT_SLOT_CARRY` and `MERGE_SLOT_JOIN`, and both retired
    # on 2026-08-30 - so the assertion died with a declaration rather than with the
    # property, which is the failure this round exists to stop. Every shape the mapper
    # declares is equal to every other as a VALUE (`sentence` is compare=False), so the
    # attribute each was bound to is the only thing telling any two apart; a shape that
    # ever stopped being interchangeable would redden here without anything being renamed.
    shapes = [shape for shape in vars(LotEventRoleMapper).values()
              if isinstance(shape, SentenceShape)]
    assert len(shapes) > 1, "one shape cannot show that the name is what separates them"
    for other in shapes[1:]:
        assert shapes[0] == other, (
            "the shapes are EQUAL as values -- nothing but the name they were bound to "
            "can separate them")
    assert len({shape.sentence for shape in shapes}) == len(shapes)


def test_the_shapes_own_name_selects_the_mapping_end_to_end():
    """The mapper passes no selector anywhere and still lands the right mapping, which is
    what each atom's `derivation` records -- and the `derivation` is now the sentence.

    🔴 RE-AIMED, NOT WEAKENED (2026-09-07). It rode `split_slot_carry`/`merge_slot_join`,
    both retired 2026-08-30 with the `slot_map@1` predicate they said. The mechanism is
    untouched, so it is pointed at the sentences the mapper says TODAY - and read off the
    class rather than listed here, so the next retirement changes this test's expectation
    without changing this test."""
    said = {shape.sentence for shape in vars(LotEventRoleMapper).values()
            if isinstance(shape, SentenceShape)}
    landed = {item["derivation"]
              for item in preview(split_rows(), known=()).candidate_semantics}

    assert landed, "the fixture must produce atoms or this asserts nothing"
    assert landed <= said, (
        "every derivation is a sentence the mapper declared - a derivation from anywhere "
        "else would mean a selector crept back in")
    assert len(landed) > 1, (
        "one sentence cannot show that the NAME selected it rather than the only mapping")


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
    #
    # 🔴 READ FROM THE DECLARATION, NOT NAMED HERE (2026-09-07). This asserted
    # `'merge_slot_join'`, a sentence that retired on 2026-08-30 - so it stopped testing
    # "the refusal lists what is declared" and started testing "the fixture still says
    # this one word". Asking the bundle means the assertion survives the next retirement
    # and still fails if the refusal ever stops listing anything.
    declared = set(lot_event_bundle()["sources"]["lot_event"]["bind"]["mappings"])
    assert declared, "the fixture must declare something or this asserts nothing"
    for sentence in declared:
        assert repr(sentence) in caught.value.message


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
