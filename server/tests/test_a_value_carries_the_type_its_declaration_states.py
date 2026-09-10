# -*- coding: utf-8 -*-
"""값은 «선언이 말한 타입»으로 실린다 (S-84, 판정 249).

🔴 WHAT WAS BROKEN. The grammar and the authoring form accepted `string`, `boolean` and
`timestamp` as a value object's type, and the compiler pinned EVERY value object to a
`quantity` Role. So a source declaring any of the three had every atom refused as an
invalid quantity - the word was offered, taken, and then rejected. 판정 178 narrowed the
FORM to `number` to stop the trap; this widens the emitter instead, which is what the
narrowing was waiting for.

⛔ `string` MAPS TO `attribute` AND NOT TO `symbolic`, and that is a measurement rather
than a naming taste. `roleframe`'s scalar branch carries one extra condition for `symbolic`
alone - the value must be in `role.allowed_values` - and nothing in the system writes
`allowed_values`. Its own comment says the day the first half becomes reachable with the
second still empty, EVERY symbolic value is refused. Mapping `string` there would have been
that day.

⚠️ `timestamp` IS STILL OUT, by measurement too: a `time` Role must be a timezone-aware
datetime, the one function that makes one out of a source string needs the timezone
declared on `occurred_at`, and reaching it from the emitter means importing across a
boundary that runs the other way. That is a round, not a line, and the validator goes on
naming it with a number.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest                                                          # noqa: E402

from ledger import roleframe                                           # noqa: E402
from ledger.setup_bundle import (                                      # noqa: E402
    DEFAULT_VALUE_TYPE,
    EMITTABLE_VALUE_TYPES,
    VALUE_TYPES,
    predicate_claim,
)


def _value_role(value_type):
    predicate = {"subjects": ["thing@1"], "object": {"kind": "value"}}
    if value_type is not None:
        predicate["object"]["value_type"] = value_type
    return predicate_claim("says@1", predicate)["roles"]["value"]


def test_a_number_is_a_quantity_exactly_as_before():
    """⚠️ THE HALF THAT MUST NOT MOVE. Every declaration on disk means `number`, and an
    atom built from one has to be the same bytes it was."""
    assert _value_role("number") == {"kind": "quantity", "required": True}


def test_an_undeclared_type_is_a_number_and_so_are_its_bytes():
    """Absence has always meant `number`; a claim built from a predicate that says nothing
    must not start saying something."""
    assert _value_role(None) == _value_role(DEFAULT_VALUE_TYPE)
    assert _value_role(None)["kind"] == "quantity"


def test_a_string_is_an_attribute_because_symbolic_would_refuse_every_one():
    """🔴 THE TRAP THIS AVOIDED, PINNED SO NOBODY 'TIDIES' THE NAME LATER.

    `symbolic` reads like the right word for a text value. It is the one Role kind whose
    branch adds a condition - membership in `allowed_values` - and nothing writes that, so
    the check would refuse every string it was introduced to admit.
    """
    assert _value_role("string") == {"kind": "attribute", "required": True}
    assert _value_role("string")["kind"] != "symbolic"


def test_a_boolean_is_an_attribute_too():
    assert _value_role("boolean") == {"kind": "attribute", "required": True}


def test_the_roles_these_map_to_accept_the_values_they_are_for():
    """🔴 THE MAPPING IS ONLY RIGHT IF THE VALIDATOR AGREES, so it is asked directly - a
    Role kind that refuses its own type would reproduce the defect under a new name."""
    class _Role:
        def __init__(self, kind):
            self.kind = kind
            self.allowed_values = ()

    for kind, value in (("quantity", 7.5), ("attribute", "some text"),
                        ("attribute", True)):
        roleframe._validate_role_value(None, _Role(kind), value, path="p")

    # And the old pin is what refused them: a string was never a quantity.
    with pytest.raises(roleframe.RoleFrameError):
        roleframe._validate_role_value(None, _Role("quantity"), "some text", path="p")
    with pytest.raises(roleframe.RoleFrameError):
        roleframe._validate_role_value(None, _Role("quantity"), True, path="p")


def test_timestamp_is_declarable_and_not_yet_emittable():
    """⚠️ TWO SENTENCES, KEPT APART ON PURPOSE. 「that is not a word」 tells an author they
    made a typo; 「declared, but the emitter does not read it yet (S-84)」 names a debt with
    a number. Folding them would lose the difference."""
    assert "timestamp" in VALUE_TYPES
    assert "timestamp" not in EMITTABLE_VALUE_TYPES


def test_the_emittable_set_is_exactly_the_three_that_landed():
    assert EMITTABLE_VALUE_TYPES == frozenset({"number", "string", "boolean"})


def test_the_authoring_form_offers_what_the_emitter_honours():
    """🔴 판정 178 IS REVERTED BY THIS AND NOT BESIDE IT. The form was narrowed to
    `number` because it was offering words the emitter refused; it reads the emittable set
    itself, so widening the set IS the revert - there is no second place to change, which
    is why there is no second place to forget."""
    from ledger import config_authoring

    lists = config_authoring.closed_lists()

    assert set(lists["value_type"]) == set(EMITTABLE_VALUE_TYPES)
    assert "string" in lists["value_type"]
