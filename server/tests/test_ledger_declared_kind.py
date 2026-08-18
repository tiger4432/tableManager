# -*- coding: utf-8 -*-
"""The fourth grammar — a source declaration `ledger/config.py` must refuse or accept.

`ledger/declared_translator.py` was deleted on 2026-08-18, taking the value-resolution and
translation halves of this file with it. What remains is the DECLARATION GRAMMAR, and that
code still exists and still runs — so these tests die in the commit that deletes
`ledger/config.py`, not before it.

Every refusal below is here because the alternative outcome is a WRONG ATOM rather than an
error — a misspelled `when` operator that silently means "always", a `$column` that
silently resolves to nothing, a rule name reused so two claims cannot be told apart. None
of those fail loudly on their own, which is why the grammar is checked here even though
the thing that used to execute it is gone.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config as ledger_config                          # noqa: E402


def declaration(**overrides):
    """A COMPLETE declared source. Tests break exactly one thing at a time."""
    base = {
        "kind": "declared",
        "occurred_at_column": "assigned_at",
        "occurred_at_format": "%Y-%m-%dT%H:%M:%S",
        "occurred_at_timezone": "Asia/Seoul",
        "occurred_at_basis": "claim_time",
        "subject_types": ["Product", "Wafer"],
        "register_entity_types": ["Product"],
        "watermark": {"columns": ["updated_at", "row_id"]},
        "columns": {"row_identity": "row_id"},
        "emit": [{
            "rule": "coordinate_leg",
            "predicate": "has_param",
            "class": "observation",
            "subject": {"type": "Product", "keys": {"product": "$base"}},
            "object": {"kind": "value",
                       "payload": {"param": "$leg", "value": "$x", "unit": "cell"}},
        }],
    }
    base.update(overrides)
    return base


def validate(source):
    return ledger_config.validate({"sources": {"reg": source}}, origin="<test>")


def refusal_of(source):
    with pytest.raises(ledger_config.LedgerConfigError) as caught:
        validate(source)
    return str(caught.value)


# --------------------------------------------------------------- the grammar's shape
def test_the_complete_declaration_validates():
    assert validate(declaration())


def test_the_time_basis_must_be_declared_and_has_no_default():
    """🔴 R-2026-08-15-N ②. A registry's `created_at` is when the ROW appeared, not when
    the claim was made. Both are legal; passing the second off as the first turns every
    「when did this become true」into「when did this get loaded」, silently."""
    source = declaration()
    source.pop("occurred_at_basis")
    assert "occurred_at_basis" in refusal_of(source)

    source["occurred_at_basis"] = "whenever"
    assert "claim_time" in refusal_of(source)

    for legal in ("claim_time", "row_created"):
        assert validate(declaration(occurred_at_basis=legal))


def test_an_emit_rule_must_name_its_derivation():
    source = declaration()
    source["emit"][0].pop("rule")
    assert "derivation" in refusal_of(source)


def test_two_rules_cannot_share_a_derivation_name():
    source = declaration()
    source["emit"].append(dict(source["emit"][0]))
    assert "declared twice" in refusal_of(source)


def test_the_declared_rule_names_become_the_legal_derivations():
    """The gate refuses a derivation the config did not declare, so this IS the link
    between「what the operator wrote」and「what may land」."""
    cfg = {"version": 1, "sources": {"reg": declaration()}}
    assert ledger_config.declared_derivations(cfg, "reg") == frozenset(
        {"coordinate_leg", "first_sight"})

    without_register = declaration(register_entity_types=[])
    cfg = {"version": 1, "sources": {"reg": without_register}}
    assert ledger_config.declared_derivations(cfg, "reg") == frozenset({"coordinate_leg"})


def test_every_emit_rule_must_CHOOSE_its_resolution_class():
    """🔴 THE OPERATOR CLASSIFIES, BECAUSE ONLY THE OPERATOR KNOWS.

    Design §6 ranks `2 관측` above `3 추론`, and which one an atom is depends on where its
    CONTENT came from - the row in front of the rule's author, or a convention the row
    never uttered. That is not a developer's knowledge, and a developer clearing a CI
    failure later would be guessing at somebody else's intent.

    No default, for the same reason `traversable` has none: the ledger never updates, so
    this stamp is permanent, and the resolution order TRUSTS it. An assumption labelled as
    an observation outranks a real measurement silently and forever.
    """
    source = declaration()
    source["emit"][0].pop("class")
    refusal = refusal_of(source)
    assert "class" in refusal
    assert "observation" in refusal and "inference" in refusal

    source = declaration()
    source["emit"][0]["class"] = "probably_fine"
    assert "must be declared as" in refusal_of(source)

    for legal in ("observation", "inference"):
        source = declaration()
        source["emit"][0]["class"] = legal
        assert validate(source)


def test_a_rule_declared_class_3_reaches_the_RESOLVER_not_just_the_test():
    """🔴 The two consumers must read ONE declaration.

    If the classification test read the operator's choice but the resolver did not, the
    test would go green while the resolver ranked those atoms as observations - a check
    that certifies the opposite of what runs, which is worse than no check at all.
    """
    source = declaration()
    source["emit"][0]["class"] = "inference"
    cfg = {"version": 1, "sources": {"reg": source}}
    ledger_config.validate(cfg, origin="<test>")

    assert ledger_config.declared_inference_derivations(cfg) == frozenset(
        {"coordinate_leg"})

    observation = declaration()          # the same rule, declared class 2
    cfg2 = {"version": 1, "sources": {"reg": observation}}
    assert ledger_config.declared_inference_derivations(cfg2) == frozenset()


def test_only_the_declared_grammar_can_classify_from_config():
    """The other three grammars mint their derivations in Python, so their class stays a
    code-side judgement a reviewer can see. A `class` key on those sources would be a
    declaration with no enforcement point."""
    lineage = {"occurred_at_column": "t", "occurred_at_timezone": "Asia/Seoul",
               "subject_types": ["Lot"],
               "columns": {"row_identity": "b", "lot": "l", "event_type": "e",
                           "slots": "s", "wafers": "w", "parent_lot": "p",
                           "child_lot": "c"},
               "vocabulary": {"split": {"lineage": "parent_child",
                                        "slot_pairing": "slot_preserving"}}}
    cfg = {"version": 1, "sources": {"lot_event": lineage}}
    assert ledger_config.declared_inference_derivations(cfg) == frozenset()


def test_a_partial_subject_identity_is_refused():
    """Design §3's concatenation incident, one column over: a key part left out produces
    an identity that looks complete and is not."""
    source = declaration()
    source["emit"][0]["subject"]["keys"] = {}
    assert "EXACTLY the key parts" in refusal_of(source)

    source = declaration()
    source["emit"][0]["subject"]["keys"] = {"product": "$base", "extra": "$x"}
    assert "EXACTLY the key parts" in refusal_of(source)


def test_an_undeclared_entity_type_cannot_be_minted_by_a_source():
    source = declaration()
    source["emit"][0]["subject"]["type"] = "Cassette"
    assert "not a declared entity type" in refusal_of(source)


def test_a_value_object_must_actually_say_something():
    source = declaration()
    source["emit"][0]["object"] = {"kind": "value", "payload": {}}
    assert "non-empty" in refusal_of(source)


@pytest.mark.parametrize("when,expected", [
    ({"column": "leg"}, "EXACTLY ONE operator"),                      # zero operators
    ({"column": "leg", "equals": "A", "in": ["A"]}, "EXACTLY ONE operator"),
    ({"column": "leg", "eq": "A"}, "EXACTLY ONE operator"),           # misspelled
    ({"equals": "A"}, "when.column"),                                 # no column
    ({"column": "leg", "in": "A"}, "must be a list"),
])
def test_a_when_clause_that_could_silently_always_fire_is_refused(when, expected):
    """🔴 The sharpest one in this file. A misspelled operator that got ignored would make
    the clause vacuously true and emit atoms nobody asked for — and it would do that while
    every test that did not think to check the branch stayed green."""
    source = declaration()
    source["emit"][0]["when"] = when
    assert expected in refusal_of(source)


def test_the_lineage_vocabulary_block_is_refused_here():
    assert "LINEAGE declaration" in refusal_of(declaration(vocabulary={"split": {}}))


def test_a_column_map_this_grammar_does_not_read_is_refused():
    """R-2026-08-13-D: a mapping nothing consumes teaches a contract nobody enforces."""
    source = declaration()
    source["columns"]["wafer"] = "base"
    assert "does not read" in refusal_of(source)



def test_the_fourth_kind_is_registered_as_a_grammar():
    assert ledger_config.SOURCE_KIND_DECLARED in ledger_config.SOURCE_KINDS
    assert ledger_config.SOURCE_KIND_DECLARED == "declared"


def test_it_is_NOT_named_derivation_and_that_is_deliberate():
    """R-2026-08-15-M ⑤'s `derivation` evaluates conditions against the LEDGER and emits
    class-3 inference carrying evidence ids. This kind translates a source row it is
    looking straight at — the same epistemic act the other three perform. Sharing the name
    would have given class-3 rules' discipline to class-2 claims."""
    assert "derivation" not in ledger_config.SOURCE_KINDS
