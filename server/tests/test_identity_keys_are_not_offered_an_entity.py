# -*- coding: utf-8 -*-
"""The form recommended a binding the validator refuses, and the skeleton said so on purpose.

An entity binding names its subject by `keys`, and each of those keys is itself a binding.
The skeleton pointed that slot at the SAME `binding` def the outer square uses, so the form
offered `entity` there -- and `_validate_binding` answers `invalid_binding` for exactly
that shape: "entity identity keys allow only column or constant bindings".

🔴 SO NOTHING IS BEING TAKEN AWAY. The narrowing does not remove a capability; it stops the
document from RECOMMENDING one that has never existed. The skeleton is what a config is
made of, and a document that recommends what the checker refuses is a false document.

⛔ AND IT IS STILL A BINDING RECORD, ONE LAYER. `kind` plus `column` or `value` -- the same
object the outer square holds, minus the branch that could nest. The recursion the old
comment meant to protect was never more than one layer deep, because `column` and
`constant` have no `keys` to go down into.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import setup_bundle                                  # noqa: E402
from ledger.config_authoring import closed_lists, skeleton       # noqa: E402

OUTER_LIST = "binding_kinds"
IDENTITY_LIST = "identity_binding_kinds"


def binding_of(kind):
    return {"column": {"kind": "column", "column": "c"},
            "constant": {"kind": "constant", "value": "v"},
            "entity": {"kind": "entity", "entity_type": "thing@1",
                       "keys": {"k": {"kind": "column", "column": "c"}}}}[kind]


def refusals_for_identity_key(kind):
    """Ask the VALIDATOR what it thinks of this kind used as an identity key."""
    problems = setup_bundle._Problems()
    setup_bundle._validate_binding(
        {"kind": "entity", "entity_type": "thing@1", "keys": {"k": binding_of(kind)}},
        "probe", problems)
    return [issue for issue in problems.items
            if issue.path.startswith("probe.keys.k")]


def identity_node():
    return skeleton()["defs"]["identity_binding"]


# ------------------------------------------------------- the list is MEASURED, not typed

def test_the_offered_kinds_are_the_ones_the_validator_accepts_there():
    """🔴 THE LITERAL IS SCORED AGAINST THE CHECKER RATHER THAN TRUSTED. A kind that lands
    in `binding_kinds` later is either accepted here too -- and this goes red until the
    narrow list learns it -- or refused, which is the case this exists for."""
    published = closed_lists()
    accepted = [kind for kind in published[OUTER_LIST]
                if not refusals_for_identity_key(kind)]
    assert published[IDENTITY_LIST] == accepted
    assert set(published[IDENTITY_LIST]) == {"column", "constant"}


def test_the_kind_that_was_offered_is_the_one_that_is_refused():
    """⚠️ NOT VACUOUS. If the validator stopped refusing nested entities, the narrowing
    would be a real loss of capability and this says so."""
    refused = refusals_for_identity_key("entity")
    assert refused, "the narrowing now removes a shape the validator would accept"
    assert refused[0].code == "invalid_binding"
    assert "column or constant" in refused[0].message


def test_the_outer_square_still_offers_all_three():
    """The narrowing is for ONE slot. An entity binding as a ROLE's material is ordinary."""
    assert set(closed_lists()[OUTER_LIST]) == {"column", "constant", "entity"}


# ------------------------------------------------------------------- the slot is rewired

def test_the_identity_slot_points_at_the_narrowed_node():
    keys = next(field for field in skeleton()["defs"]["binding"]["fields"]
                if field["key"] == "keys")
    assert keys["node"]["of"] == {"use": "identity_binding"}, (
        "the identity slot reuses the wide node again, so the form offers `entity`")


def test_the_narrowed_node_is_still_a_binding_record_of_one_layer():
    """⛔ GATE 3. Not a bare string, not a different object: the same record, one layer."""
    node = identity_node()
    assert node["kind"] == "record"
    keys = [field["key"] for field in node["fields"]]
    assert keys == ["kind", "column", "value"]
    assert node["fields"][0]["node"]["list"] == IDENTITY_LIST
    for field in node["fields"][1:]:
        assert field["when"]["field"] == "kind"
        assert field["node"]["kind"] == "leaf"


def test_it_takes_fields_away_and_never_adds_any():
    wide = {field["key"] for field in skeleton()["defs"]["binding"]["fields"]}
    narrow = {field["key"] for field in identity_node()["fields"]}
    assert narrow < wide
    assert wide - narrow == {"entity_type", "keys"}


def test_nothing_under_it_can_nest_another_binding():
    """The one layer the old comment meant to protect: `column` and `constant` carry no
    `keys`, so there was never a second level to lose."""
    for field in identity_node()["fields"]:
        assert "of" not in field["node"] and "use" not in field["node"]


# ---------------------------------------------------------------- no declaration breaks

@pytest.mark.parametrize("kind", ["column", "constant"])
def test_every_shape_the_narrow_list_offers_still_validates(kind):
    """🔴 GATE 1, stated as the property rather than as a count: what the form may now
    produce is exactly what the checker accepts, so no writable declaration is lost."""
    assert not refusals_for_identity_key(kind)
