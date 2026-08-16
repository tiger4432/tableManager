# -*- coding: utf-8 -*-
"""The fourth grammar — a translator that is a DECLARATION (`ADMIN_SETUP_BRIEF` §6-2).

WHY THIS FILE IS DENSER THAN THE OTHER TRANSLATORS' TESTS
----------------------------------------------------------
The other three grammars have a Python class a reviewer can read, and a reviewer is a real
check. This one's behaviour lives in a config file written through a screen, so the only
reviewer it has is this suite plus the gate. That is the proportionality rule
(R-2026-08-14-J) pointing straight at it: a declarative write path IS a risky place.

Every refusal below is here because the alternative outcome is a WRONG ATOM rather than an
error — a misspelled `when` operator that silently means "always", a `$column` that
silently resolves to nothing, a rule name reused so two claims cannot be told apart. None
of those fail loudly on their own.
"""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config as ledger_config                          # noqa: E402
from ledger import gate                                             # noqa: E402
from ledger.declared_translator import (DeclaredMolecule, DeclaredTranslator,  # noqa: E402
                                        matches, resolve)


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


def row(**overrides):
    base = {"row_identity": "r1", "event_time": "2026-08-15T09:00:00",
            "base": "REF_BASE", "x": 3, "y": 4, "leg": "A", "row_id": "r1",
            "updated_at": "2026-08-15T09:00:00", "__watermark__": ["t", "r1"]}
    base.update(overrides)
    return base


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


# ------------------------------------------------------------- value resolution
def test_a_dollar_token_reads_the_row_and_a_bare_string_is_a_literal():
    r = row()
    assert resolve("$leg", r, "reg", "w") == "A"
    assert resolve("leg", r, "reg", "w") == "leg"
    assert resolve("$$leg", r, "reg", "w") == "$leg"
    assert resolve({"a": "$x", "b": "lit"}, r, "reg", "w") == {"a": 3, "b": "lit"}


def test_a_dollar_token_for_a_column_that_is_not_there_REFUSES():
    """🔴 Not `None`. Resolving to nothing produces an atom that is well formed,
    plausible, and about nothing — which is the failure every other refusal here prevents."""
    with pytest.raises(gate.MoleculeRefused) as caught:
        with gate.building_molecule("reg"):
            resolve("$ghost", row(), "reg", "emit[0].payload.leg")
    assert "ghost" in str(caught.value)
    gate.reset_counters()


@pytest.mark.parametrize("when,leg,fires", [
    ({"column": "leg", "equals": "A"}, "A", True),
    ({"column": "leg", "equals": "A"}, "B", False),
    ({"column": "leg", "not_equals": "A"}, "B", True),
    ({"column": "leg", "in": ["A", "C"]}, "C", True),
    ({"column": "leg", "in": ["A", "C"]}, "B", False),
    ({"column": "leg", "not_in": ["A"]}, "B", True),
    ({"column": "leg", "present": True}, "A", True),
    ({"column": "leg", "present": True}, "", False),
    ({"column": "leg", "absent": True}, "", True),
    (None, "A", True),
])
def test_branching_on_a_column_value(when, leg, fires):
    assert matches(when, row(leg=leg), "reg") is fires


def test_branching_on_a_column_that_is_not_there_REFUSES():
    """A branch on an absent column would take the same arm forever, silently."""
    with pytest.raises(gate.MoleculeRefused):
        with gate.building_molecule("reg"):
            matches({"column": "ghost", "equals": "A"}, row(), "reg")
    gate.reset_counters()


# ----------------------------------------------------------------- the translation
def translate(source, source_row):
    cfg = {"version": 1, "sources": {"reg": source}}
    ledger_config.validate(cfg, origin="<test>")
    translator = DeclaredTranslator(
        "reg", source, ledger_config.translator_version(cfg, "reg"),
        ledger_config.declared_derivations(cfg, "reg"))
    with gate.building_molecule("reg"):
        return translator.translate(DeclaredMolecule("reg", source_row)), translator


def test_one_row_becomes_the_declared_atoms():
    gate.reset_counters()
    (atoms, report), _t = translate(declaration(), row())
    gate.reset_counters()

    assert report["refused"] is False
    by_predicate = sorted(a.predicate for a in atoms)
    assert by_predicate == ["has_param", "register"]

    claim = next(a for a in atoms if a.predicate == "has_param")
    assert claim.subject_type == "Product"
    assert claim.subject_keys == {"product": "REF_BASE"}
    assert claim.object_kind == "value"
    assert claim.object_payload["param"] == "A"       # $leg
    assert claim.object_payload["value"] == 3         # $x, type preserved
    assert claim.object_payload["unit"] == "cell"     # literal
    assert claim.derivation == "coordinate_leg"
    assert claim.source_translator_ver.endswith("#coordinate_leg")
    assert claim.source_raw_ref == 'reg:["r1"]'


def test_the_time_basis_rides_in_the_payload_so_it_is_readable_FROM_THE_ATOM():
    """R-2026-08-15-N ② with an enforcement point. A declaration stating "this is only the
    row's creation time" in a file nobody reads at query time would bind nothing."""
    gate.reset_counters()
    (atoms, _r), _t = translate(declaration(occurred_at_basis="row_created"), row())
    gate.reset_counters()
    claim = next(a for a in atoms if a.predicate == "has_param")
    assert claim.object_payload["occurred_at_basis"] == "row_created"


def test_one_row_can_become_SEVERAL_atoms_and_branching_selects_which():
    source = declaration()
    source["emit"].append({
        "rule": "leg_a_note",
        "predicate": "has_param",
        "class": "observation",
        "subject": {"type": "Product", "keys": {"product": "$base"}},
        "object": {"kind": "value",
                   "payload": {"param": "note", "value": "leg A", "unit": "text"}},
        "when": {"column": "leg", "equals": "A"},
    })
    gate.reset_counters()
    (atoms_a, _), _ = translate(source, row(leg="A"))
    (atoms_b, _), _ = translate(source, row(leg="B", row_identity="r2"))
    gate.reset_counters()

    # A fires both rules (+ one register); B fires only the unconditional one.
    assert sorted(a.derivation for a in atoms_a) == ["coordinate_leg", "first_sight",
                                                     "leg_a_note"]
    assert sorted(a.derivation for a in atoms_b) == ["coordinate_leg", "first_sight"]


def test_a_row_matching_no_rule_is_COUNTED_rather_than_refused():
    """A registry whose rules cover a subset is a legitimate declaration. But a
    declaration matching NOTHING looks identical to one that works until somebody counts,
    so the number exists and the dry run turns it into a sentence."""
    source = declaration()
    source["emit"][0]["when"] = {"column": "leg", "equals": "ZZZ"}
    gate.reset_counters()
    (atoms, report), translator = translate(source, row(leg="A"))
    gate.reset_counters()

    assert atoms == []
    assert report["refused"] is False
    assert translator.rows_matching_nothing == 1


def test_an_unparseable_time_is_REFUSED_never_replaced_with_now():
    """The brief's risk 2 — arrival time standing in for world time is the defect that
    never announces itself, because every atom stays well formed and only the ORDER of
    history is wrong."""
    gate.reset_counters()
    (atoms, report), _t = translate(declaration(), row(event_time="not a timestamp"))
    gate.reset_counters()
    assert atoms is None
    assert report["refused"] is True
    assert report["reason"] == gate.REFUSE_MISSING_OCCURRED_AT


def test_a_refused_row_gives_its_registrations_BACK():
    """Otherwise the next row mentioning the same product emits no register either, and
    the entity is registered nowhere while the memo says it was."""
    gate.reset_counters()
    source = declaration()
    cfg = {"version": 1, "sources": {"reg": source}}
    ledger_config.validate(cfg, origin="<test>")
    translator = DeclaredTranslator("reg", source,
                                    ledger_config.translator_version(cfg, "reg"),
                                    ledger_config.declared_derivations(cfg, "reg"))
    with gate.building_molecule("reg"):
        atoms, report = translator.translate(
            DeclaredMolecule("reg", row(event_time="broken")))
    assert atoms is None and report["refused"] is True
    assert translator.registered == set(), "a refused row left its product marked registered"

    with gate.building_molecule("reg"):
        atoms, _report = translator.translate(DeclaredMolecule("reg", row()))
    assert any(a.predicate == "register" for a in atoms)
    gate.reset_counters()


def test_the_gate_refuses_a_declaration_that_makes_an_ILLEGAL_atom():
    """🔴 THE SAFETY NET THE BRIEF PROMISES. This grammar has no Python reviewer, so a
    declaration naming a predicate that does not accept its subject must end in a REFUSAL
    rather than in a written atom. Proven end to end: the declaration validates, the
    translator builds, and the gate throws it out by name."""
    from ledger import vocabulary

    source = declaration()
    # `observed` accepts Wafer / WaferLeg, never Product.
    source["emit"][0]["predicate"] = "observed"
    source["emit"][0]["object"] = {
        "kind": "value",
        "payload": {"finding_kind": "void", "method": "map", "run_uid": "$row_id"}}
    cfg = {"version": 1, "sources": {"reg": source}}
    ledger_config.validate(cfg, origin="<test>")     # the GRAMMAR is fine

    gate.reset_counters()
    translator = DeclaredTranslator("reg", source,
                                    ledger_config.translator_version(cfg, "reg"),
                                    ledger_config.declared_derivations(cfg, "reg"))
    molecule = DeclaredMolecule("reg", row())
    with pytest.raises(gate.MoleculeRefused) as caught:
        with gate.building_molecule("reg"):
            atoms, _r = translator.translate(molecule)
            # The REAL ref, not a placeholder: the gate checks that every atom belongs to
            # the transaction unit it is screened under, and it refuses a mismatch first.
            gate.screen_molecule("reg", atoms,
                                 ledger_config.declared_derivations(cfg, "reg"),
                                 ledger_config.declared_subject_types(cfg, "reg"),
                                 molecule_ref=molecule.ref, source_rows=1)
    assert "does not accept subject type 'Product'" in caught.value.detail
    gate.reset_counters()
    assert vocabulary.is_declared("observed")        # the word is fine; the USE was not


def test_the_fourth_kind_is_registered_as_a_grammar():
    assert ledger_config.SOURCE_KIND_DECLARED in ledger_config.SOURCE_KINDS
    assert ledger_config.SOURCE_KIND_DECLARED == "declared"


def test_it_is_NOT_named_derivation_and_that_is_deliberate():
    """R-2026-08-15-M ⑤'s `derivation` evaluates conditions against the LEDGER and emits
    class-3 inference carrying evidence ids. This kind translates a source row it is
    looking straight at — the same epistemic act the other three perform. Sharing the name
    would have given class-3 rules' discipline to class-2 claims."""
    assert "derivation" not in ledger_config.SOURCE_KINDS
