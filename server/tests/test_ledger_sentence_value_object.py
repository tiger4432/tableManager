"""A mapper says a sentence whose object is a VALUE, end to end.

Before this, ``ProfileSentences.say()`` assembled the object unconditionally as an Entity
reference, so a Claim declaring ``"object": {"kind": "value", ...}`` could not be produced
by any mapper: the assembly refused every non-entity binding by name.  It was a missing
path rather than a broken one -- every shipped sentence happened to have an entity object,
so the branch was never written.

The mapper below is the whole point of the file.  It runs through the production path
(``map_event_frame`` -> ``compile_role_frame``) and the assertions read the atom, not the
branch: a unit test of ``_object_value`` would pass against a ``say()`` that never called
it.
"""
from __future__ import annotations

import pytest

from ledger.roleframe import (
    BaseLedgerMapper,
    ProfileSentences,
    RoleFrameError,
    SentenceShape,
    compile_role_frame,
    map_event_frame,
    mapper_context,
)
from test_ledger_roleframe import constant, event_frame, implementations
from test_ledger_setup_bundle import logical_bundle, source_profile
from test_ledger_setup_registry import snapshot


#: What the Profile's binding for the object Role says.  The mapper says something else.
BOUND_COUNT = 1.0
#: What the MAPPER hands to ``say(obj=...)``.  The atom must carry this one -- otherwise
#: the test would pass on a declarative path that never entered the mapper at all.
SAID_COUNT = 12.5


class CountingSentenceMapper(BaseLedgerMapper):
    """Says exactly one sentence, and its object is a number rather than an identity."""

    #: "this thing counted N" -- an object, no qualifiers.
    COUNT = SentenceShape(has_object=True)

    def interpret_unit(self, context, unit, profile):
        row = unit.iloc[0]
        sentences = ProfileSentences(context, profile, occurred_at=row["event_at"])
        return [sentences.say(
            self.COUNT, row["source_id"], (unit.attrs["source_raw_ref"],),
            obj=SAID_COUNT)]


def value_object_bundle(*, object_kind="value", role_kind="quantity"):
    """The fixture bundle, respoken so its one sentence has a scalar object.

    The object Role is bound to a CONSTANT on purpose.  An entity assembly cannot be built
    from a constant binding, so a ``say()`` that still took the entity path refuses this
    bundle by name instead of quietly producing something -- which is what makes the
    mutation below visible.
    """
    raw = logical_bundle()
    raw["vocabulary"]["moves_to@1"]["object"] = {
        "kind": object_kind,
        "qualifiers": {"required": [], "optional": []},
    }
    claim = raw["packs"]["movement@1"]["claims"]["transition"]
    claim["roles"].pop("target")
    claim["roles"].pop("event_key")
    claim["roles"]["result"] = {"kind": role_kind, "required": True}
    claim["emit"]["object"] = {"kind": object_kind, "value": "$result"}
    mapping = source_profile(raw)["mappings"][0]
    mapping["bind"].pop("target")
    mapping["bind"].pop("event_key")
    mapping["bind"]["result"] = constant(BOUND_COUNT)
    return raw


def test_a_mapper_can_say_a_sentence_whose_object_is_a_value():
    compiled = snapshot(value_object_bundle())
    context = mapper_context(compiled, "input_rows")

    role_frame = map_event_frame(
        context, event_frame(compiled), implementations(CountingSentenceMapper))
    ledger_frame = compile_role_frame(context, role_frame)

    # The Role carries the bare value: no {'type', 'keys'} envelope was invented for it.
    assert role_frame.iloc[0]["roles"]["result"] == SAID_COUNT
    assert ledger_frame.iloc[0]["object_kind"] == "value"
    assert ledger_frame.iloc[0]["object_payload"] == {"value": SAID_COUNT}
    # ...and it is the MAPPER's number, not the one the Profile binding declares.
    assert ledger_frame.iloc[0]["object_payload"] != {"value": BOUND_COUNT}


def test_a_mapper_can_say_a_sentence_whose_object_is_an_event_reference():
    """``event_ref`` is the other scalar object kind the Vocabulary allows.

    It is answered deliberately rather than left to fall through, so it gets its own
    execution here instead of a comment claiming it works.
    """
    compiled = snapshot(
        value_object_bundle(object_kind="event_ref", role_kind="identity"))
    context = mapper_context(compiled, "input_rows")

    class EventRefMapper(CountingSentenceMapper):
        def interpret_unit(self, context, unit, profile):
            row = unit.iloc[0]
            sentences = ProfileSentences(
                context, profile, occurred_at=row["event_at"])
            return [sentences.say(
                self.COUNT, row["source_id"], (unit.attrs["source_raw_ref"],),
                obj="EVENT-42")]

    ledger_frame = compile_role_frame(context, map_event_frame(
        context, event_frame(compiled), implementations(EventRefMapper)))

    assert ledger_frame.iloc[0]["object_kind"] == "event_ref"
    assert ledger_frame.iloc[0]["object_payload"] == {"event": "EVENT-42"}


def test_the_entity_object_path_is_untouched():
    """The shipped sentences all have Entity objects; none of them may change shape."""
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")

    ledger_frame = compile_role_frame(
        context, map_event_frame(context, event_frame(compiled), implementations()))

    assert ledger_frame.iloc[0]["object_kind"] == "entity_ref"
    assert ledger_frame.iloc[0]["object_payload"] == {
        "type": "OutputEntity",
        "keys": {"output_id": "OUT-1"},
        "qualifiers": {"event_key": "E-1"},
    }


def test_an_object_kind_say_does_not_answer_is_refused_by_name(monkeypatch):
    """The failure class the refusal exists for: a FIFTH object kind arrives.

    ``none``/``entity_ref``/``value``/``event_ref`` are each answered deliberately, so the
    only way to reach the fall-through is to widen the Vocabulary's closed set -- which is
    exactly what a later feature does.  Widening it here proves the guard is live: without
    it the new kind would take the entity path and mint an atom whose object was assembled
    as an identity it never was.

    (``none`` cannot reach ``say()`` at all: ``_validate_emission`` refuses a ``none``
    object that names a Role, so a validated bundle can never hand the method a ``none``
    emission with an object Role.  That is why this is the kind simulated and not that
    one.)
    """
    from ledger import setup_bundle as bundle_module

    monkeypatch.setattr(
        bundle_module, "_OBJECT_KINDS",
        frozenset(bundle_module._OBJECT_KINDS | {"tally"}))
    raw = value_object_bundle(object_kind="tally", role_kind="quantity")
    compiled = snapshot(raw)
    context = mapper_context(compiled, "input_rows")

    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            context, event_frame(compiled), implementations(CountingSentenceMapper))

    assert caught.value.code == "unsupported_object_kind"
    assert caught.value.path == (
        "bundle.packs.movement@1.claims.transition.emit.object.kind")
    assert "'tally'" in caught.value.message
