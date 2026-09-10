# -*- coding: utf-8 -*-
"""Ⓐ 자리 (S-75). Four sentences an operator had nowhere to write, and the defaults spelled.

The completeness table (`docs/architecture/LEDGER_SCHEMA_COMPLETENESS.md`) counts a slot as a
DEFECT when there is no place to write it -- because the way that defect shows up is not an
error, it is an operator inventing a workaround: a number where a string belonged, a second
entity to hold a piece of text, a deleted declaration where a retirement belonged.

    Ⓐ1 value type   `object.value_type`     -- the compiler read every value as a quantity
    Ⓐ2 cardinality  `cardinality`           -- nothing said a subject may hold only one
    Ⓐ3 lifecycle    `status` on entity/source -- only the PREDICATE could say "retired"
    Ⓐ4 decision key `decision_key`          -- the judgement unit, ruling 151

⛔ THE READING SIDE IS NOT BUILT (owner, 2026-09-09 08:34: 「자리만」). Nothing emits or walks
on these yet, and that is deliberate: the grammar is what freezes, and building a reader
against a slot the operator cannot yet write is how a field ends up with a consumer and no
author -- the ③′ class this round exists to stop creating.

🔴 EVERY ONE IS OPTIONAL, AND ITS DEFAULT IS WRITTEN DOWN. A default nobody can read is a
hardcoding with a nicer name; `DEFAULT_VALUE_TYPE`, `DEFAULT_CARDINALITY` and
`DEFAULT_LIFECYCLE` are the values every declaration on disk already means. `decision_key`
has NO default on purpose (ruling 151): a wrong judgement unit is a wrong answer that looks
right, so a reader that needs one must refuse by name rather than assume the row.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import setup_bundle                                      # noqa: E402
from test_ledger_setup_bundle import (                               # noqa: E402
    logical_bundle, logical_catalog, validate_bundle_errors)


def paths_of(bundle):
    return [issue.path for issue in
            validate_bundle_errors(bundle, catalog=logical_catalog())]


def clean(bundle):
    """Every issue this bundle already has, so a new one is visible as a DIFFERENCE."""
    return set(paths_of(bundle))


def only_new(before, bundle):
    return sorted(set(paths_of(bundle)) - before)


def predicate_of(bundle):
    return bundle["vocabulary"][sorted(bundle["vocabulary"])[0]]


def entity_of(bundle):
    return bundle["entities"][sorted(bundle["entities"])[0]]


def source_of(bundle):
    return bundle["sources"][sorted(bundle["sources"])[0]]


# --------------------------------------------------------------- Ⓐ1 value type

def test_the_defaults_are_named_values_rather_than_behaviour_nobody_can_read():
    assert setup_bundle.DEFAULT_VALUE_TYPE == "number"
    assert setup_bundle.DEFAULT_CARDINALITY == "many"
    assert setup_bundle.DEFAULT_LIFECYCLE == "active"
    assert setup_bundle.DEFAULT_VALUE_TYPE in setup_bundle.VALUE_TYPES
    assert setup_bundle.DEFAULT_CARDINALITY in setup_bundle.CARDINALITIES
    assert setup_bundle.DEFAULT_LIFECYCLE in setup_bundle.LIFECYCLE_STATES
    # ⛔ decision_key has no default, and its absence must not acquire one by accident.
    assert not hasattr(setup_bundle, "DEFAULT_DECISION_KEY")


def test_the_emitter_now_honours_the_whole_grammar():
    """⚰️ 판정 178 NARROWED THE FORM BECAUSE THE EMITTER HONOURED LESS THAN THE GRAMMAR
    ACCEPTED - a word offered and then refused is a trap. S-84 and S-84-b closed the gap
    from the other side, so what this case pins has changed shape rather than gone away:
    the two sets are EQUAL, and a type added to the grammar without the emitter turns this
    red - the same guard, pointing forward.

    ⛔ THE REFUSAL IT USED TO EXERCISE IS STILL THERE and still says S-84, because the
    day someone declares a fifth type it is the sentence they need: 「declared, but the
    emitter does not read it yet」 is a debt with a number, not a spelling mistake.
    """
    assert setup_bundle.EMITTABLE_VALUE_TYPES == setup_bundle.VALUE_TYPES
    assert setup_bundle.DEFAULT_VALUE_TYPE in setup_bundle.EMITTABLE_VALUE_TYPES

    bundle = logical_bundle()
    predicate = predicate_of(bundle)
    predicate["object"] = {"kind": "value", "qualifiers": {"required": [], "optional": []}}
    before = clean(bundle)
    for value_type in sorted(setup_bundle.VALUE_TYPES):
        predicate["object"]["value_type"] = value_type
        assert only_new(before, bundle) == [], f"{value_type} is emittable now"


def test_the_form_offers_only_what_the_emitter_can_honour():
    """The screen recommending a refusal is worse than the screen offering nothing."""
    from ledger import config_authoring

    offered = set(config_authoring.closed_lists()["value_type"])
    assert offered == set(setup_bundle.EMITTABLE_VALUE_TYPES)


def test_a_value_type_outside_the_closed_set_is_refused_by_path():
    bundle = logical_bundle()
    predicate = predicate_of(bundle)
    predicate["object"] = {"kind": "value", "qualifiers": {"required": [], "optional": []}}
    before = clean(bundle)
    predicate["object"]["value_type"] = "numeric"
    new = only_new(before, bundle)
    assert len(new) == 1 and new[0].endswith(".object.value_type")


def test_a_non_value_object_must_not_declare_a_value_type():
    """⚠️ SCORED LIKE `types` IS. A field that is merely ignored on the other kinds is a
    place an author can write a sentence nothing reads."""
    bundle = logical_bundle()
    predicate = predicate_of(bundle)
    predicate["object"] = {"kind": "none", "qualifiers": {"required": [], "optional": []}}
    before = clean(bundle)
    predicate["object"]["value_type"] = "string"
    new = only_new(before, bundle)
    assert len(new) == 1 and new[0].endswith(".object.value_type")


# ------------------------------------------------------------- Ⓐ2 cardinality

def test_a_predicate_may_say_a_subject_holds_only_one():
    bundle = logical_bundle()
    before = clean(bundle)
    predicate_of(bundle)["cardinality"] = "one"
    assert only_new(before, bundle) == []


def test_a_cardinality_outside_the_closed_set_is_refused():
    bundle = logical_bundle()
    before = clean(bundle)
    predicate_of(bundle)["cardinality"] = "single"
    new = only_new(before, bundle)
    assert len(new) == 1 and new[0].endswith(".cardinality")


# --------------------------------------------------------------- Ⓐ3 lifecycle

def test_an_entity_may_be_retired_instead_of_deleted():
    """🔴 DELETION REMOVES THE NAME EVERY STORED ATOM POINTS AT. 「투영은 지워도 기록은
    안 된다」, applied to the grammar rather than to the ledger.

    ⚠️ AND RETIRING ONE A LIVE SOURCE STILL SPEAKS ABOUT IS REFUSED BY NAME (S-103).
    This case used to assert that retiring produced NOTHING, which was true only while
    nothing checked - and a retirement that silently leaves a source translating into the
    retired type is the deletion this test exists to prevent, wearing a softer word. What
    the grammar owes an author is the NAME of the type and the mapping that still uses
    it, which is what it now says.
    """
    bundle = logical_bundle()
    before = clean(bundle)
    entity_of(bundle)["status"] = "retired"

    raised = [i for i in validate_bundle_errors(bundle, catalog=logical_catalog())
              if i.code == "inactive_entity_type"]
    assert raised, "retiring a type a source still binds must not pass in silence"
    assert all("retired" in i.message for i in raised), [i.message for i in raised]

    # ⛔ AND IT IS THE ONLY THING RAISED: retirement is not deletion, so the grammar must
    # not also start reporting the type as unknown, missing or malformed.
    assert {i.code for i in validate_bundle_errors(bundle, catalog=logical_catalog())}
    assert only_new(before, bundle) == [i.path for i in raised]


def test_a_source_may_be_retired_instead_of_deleted():
    bundle = logical_bundle()
    before = clean(bundle)
    source_of(bundle)["status"] = "retired"
    assert only_new(before, bundle) == []


def test_the_three_places_spell_the_lifecycle_the_same_way():
    """⛔ NOT THREE VOCABULARIES. The predicate has said `active`/`retired` since the
    grammar existed; an operator must not learn a second pair of words for the same idea."""
    for holder, path_tail in ((entity_of, ".status"), (source_of, ".status")):
        bundle = logical_bundle()
        before = clean(bundle)
        holder(bundle)["status"] = "disabled"
        new = only_new(before, bundle)
        assert len(new) == 1 and new[0].endswith(path_tail), new
    bundle = logical_bundle()
    before = clean(bundle)
    predicate_of(bundle)["status"] = "disabled"
    new = only_new(before, bundle)
    assert len(new) == 1 and new[0].endswith(".status")


# ------------------------------------------------------------ Ⓐ4 decision key
#
# ⚰️ IT IS NOT ON THE LEDGER SOURCE (ruling, 2026-09-09 08:54). The first draft put it there
# and the lead PM moved it: the judgement unit is a property of the TABLE, and the readers
# that will need it -- the virtual join, the enrichment resolver -- read the CATALOG rather
# than this bundle. Declaring it on the source would have made two places for one fact.


#: A `table_config.json` entry, in the shape the ADAPTER reads -- which is not the shape
#: `logical_catalog()` returns. That fixture is already adapted (`columns`), so testing the
#: adapter through it would have scored nothing at all.
def raw_table(**extra):
    return {"parts": dict({"column_types": {"lot": "string", "slot": "number"}}, **extra)}


def adapt(**extra):
    return setup_bundle._adapt_physical_catalog(raw_table(**extra))


def refusal_for(decision_key):
    try:
        adapt(decision_key=decision_key)
    except setup_bundle.LedgerSetupValidationError as caught:
        return caught
    return None


def test_a_table_may_name_the_columns_its_judgement_is_made_on():
    built = adapt(decision_key=["lot", "slot"])
    assert built["parts"]["decision_key"] == ["lot", "slot"]


def test_a_decision_key_naming_an_undeclared_column_is_refused_by_path():
    """⛔ A COLUMN NOBODY DECLARED selects nothing while reading as a decision -- the
    permanently-false filter, wearing an operator's intent."""
    caught = refusal_for(["lot", "wafer"])
    assert caught is not None
    assert caught.code == "invalid_catalog" and caught.path.endswith(".decision_key")
    assert "wafer" in caught.message


def test_a_repeated_a_blank_and_an_empty_decision_key_are_all_refused():
    for bad in (["lot", "lot"], ["  "], [], "lot"):
        assert refusal_for(bad) is not None, bad


def test_a_table_that_names_none_carries_no_decision_key_at_all():
    """⛔ NOT AN EMPTY LIST EITHER. 「없음」 and 「없다고 선언함」 must stay different, because
    a reader that needs one has to refuse by name rather than read an empty unit."""
    assert "decision_key" not in adapt()["parts"]


# ------------------------------------------------- the promise F-0 made about drift

def test_a_declaration_that_uses_none_of_them_is_scored_exactly_as_before():
    """🔴 THE GATE, AND IT IS WHY ALL FOUR ARE OPTIONAL. Every declaration on disk predates
    this round; if adding the slots changed how one of them is judged, the freeze would cost
    a retranslation of everything -- and the whole reason these are 「자리만」 is that they
    cost nothing until an operator writes one."""
    bundle = logical_bundle()
    untouched = copy.deepcopy(bundle)
    assert paths_of(bundle) == paths_of(untouched)
    for issue in validate_bundle_errors(bundle, catalog=logical_catalog()):
        for word in ("value_type", "cardinality", "decision_key"):
            assert word not in issue.path


def test_cardinality_reaches_the_compiled_predicate_instead_of_being_dropped():
    """🔴 STEP ZERO OF S-133 (판정 256), AND IT IS A STEP THE RULING DID NOT NAME.

    The grammar has accepted `cardinality` since the vocabulary existed and the authoring
    form has offered it, but `predicate_claim` returns only `{emit, roles}` - so the value
    was validated, shown to an author, and then DROPPED before the compiler. Measured
    2026-09-10: zero readers, and nowhere for one to stand.

    It now rides on `PredicateDescriptor` the way `status` does (S-103, ruling 198), which
    is the same shape for the same reason: a word the declaration carries that the runtime
    must be able to act on.
    """
    import dataclasses

    from ledger.setup_bundle import CARDINALITIES, DEFAULT_CARDINALITY
    from ledger.setup_registry import PredicateDescriptor

    fields = {f.name: f for f in dataclasses.fields(PredicateDescriptor)}

    assert "cardinality" in fields
    assert fields["cardinality"].default == DEFAULT_CARDINALITY
    assert DEFAULT_CARDINALITY == "many", "every declaration on disk means this"
    assert set(CARDINALITIES) == {"one", "many"}


def test_a_predicate_that_declares_one_compiles_carrying_it(tmp_path):
    """⚠️ THE VALUE, NOT JUST THE FIELD. A default that never changes is the same as no
    field at all, so the declared word has to arrive."""
    from ledger import setup_registry
    from ledger.setup_bundle import DEFAULT_CARDINALITY

    import inspect

    body = inspect.getsource(setup_registry)

    assert 'cardinality=item.get("cardinality", DEFAULT_CARDINALITY)' in body, \
        "the builder reads the declaration rather than defaulting unconditionally"
    assert DEFAULT_CARDINALITY == "many"
