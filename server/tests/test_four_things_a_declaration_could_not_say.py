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


def test_a_value_object_may_say_it_holds_text():
    bundle = logical_bundle()
    before = clean(bundle)
    predicate = predicate_of(bundle)
    if predicate["object"]["kind"] != "value":
        predicate["object"] = {"kind": "value", "qualifiers":
                               {"required": [], "optional": []}}
        before = clean(bundle)
    predicate["object"]["value_type"] = "string"
    assert only_new(before, bundle) == []


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
    안 된다」, applied to the grammar rather than to the ledger."""
    bundle = logical_bundle()
    before = clean(bundle)
    entity_of(bundle)["status"] = "retired"
    assert only_new(before, bundle) == []


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

def test_a_source_may_name_the_columns_its_judgement_is_made_on():
    bundle = logical_bundle()
    before = clean(bundle)
    source_of(bundle)["decision_key"] = ["lot", "slot"]
    assert only_new(before, bundle) == []


def test_a_decision_key_that_repeats_a_column_is_refused():
    bundle = logical_bundle()
    before = clean(bundle)
    source_of(bundle)["decision_key"] = ["lot", "lot"]
    new = only_new(before, bundle)
    assert len(new) == 1 and new[0].endswith(".decision_key")


def test_a_blank_decision_key_column_is_refused():
    bundle = logical_bundle()
    before = clean(bundle)
    source_of(bundle)["decision_key"] = ["lot", "  "]
    assert only_new(before, bundle), "a blank column name must not pass as a decision unit"


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
