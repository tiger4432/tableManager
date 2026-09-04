# -*- coding: utf-8 -*-
"""The six envelope refusals must say WHERE, like every other refusal in this system.

These six are checked per ATOM, so an operator meets them more often than any other - and
they were the only refusals here with no code and no address, while the three validators
around them all answer (code, path, message). A screen could render the sentence and
nothing else, so "which field do I fix" had no answer.

🔴 AND THE GATE USED TO BRANCH ON THE SENTENCE. It searched the message for "raw_ref" and
"occurred_at", and matched three phrases lifted from another module's exception text - so
rewording a message would silently change which refusal an atom received, and nothing kept
those phrases in step with the module that produced them.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import envelope, gate                                # noqa: E402


class _Atom:
    """The envelope fields `check_envelope` reads, and nothing else."""

    def __init__(self, occurred_at=None, who="src", ver="v1", raw_ref="row:1",
                 payload=None):
        self.occurred_at = (datetime(2026, 1, 1, tzinfo=timezone.utc)
                            if occurred_at == "ok" else occurred_at)
        self.source_who = who
        self.source_translator_ver = ver
        self.source_raw_ref = raw_ref
        self.object_payload = payload


def codes(atom):
    return [v["code"] for v in envelope.check_envelope(atom)]


def test_every_violation_carries_a_code_a_path_and_a_message():
    """🔴 THE SHAPE. Not a new vocabulary - the one the validators beside it already use."""
    violations = envelope.check_envelope(_Atom(occurred_at=None, who="", ver="",
                                               raw_ref=""))
    assert violations
    for item in violations:
        assert set(item) == {"code", "path", "message"}, item
        assert item["code"] and item["path"] and item["message"]


@pytest.mark.parametrize("atom, expected, where", [
    (_Atom(occurred_at=None), envelope.ENVELOPE_OCCURRED_AT_MISSING, "atom.occurred_at"),
    (_Atom(occurred_at=datetime(2026, 1, 1)), envelope.ENVELOPE_OCCURRED_AT_NAIVE,
     "atom.occurred_at"),
    (_Atom(occurred_at="ok", who="  "), envelope.ENVELOPE_SOURCE_WHO_EMPTY,
     "atom.source.who"),
    (_Atom(occurred_at="ok", ver=""), envelope.ENVELOPE_TRANSLATOR_VER_EMPTY,
     "atom.source.translator_ver"),
    (_Atom(occurred_at="ok", raw_ref=""), envelope.ENVELOPE_RAW_REF_EMPTY,
     "atom.source.raw_ref"),
])
def test_each_refusal_names_the_field_the_operator_has_to_fix(atom, expected, where):
    found = [v for v in envelope.check_envelope(atom) if v["code"] == expected]
    assert found, envelope.check_envelope(atom)
    assert found[0]["path"] == where


def test_a_healthy_envelope_refuses_nothing():
    assert envelope.check_envelope(_Atom(occurred_at="ok")) == []


# ------------------------------------------------------- the gate reads the CODE

def test_the_gate_maps_the_code_rather_than_searching_the_sentence():
    """🔴 The mapping is by code, so a reworded message cannot change which refusal an
    atom gets. Driven through the gate's own helper with the envelope's own output."""
    missing = envelope.check_envelope(_Atom(occurred_at=None))
    assert gate._envelope_reason(missing) == gate.REFUSE_MISSING_OCCURRED_AT

    no_ref = envelope.check_envelope(_Atom(occurred_at="ok", raw_ref=""))
    assert gate._envelope_reason(no_ref) == gate.REFUSE_NO_RAW_REF


def test_a_naive_time_is_the_same_refusal_as_a_missing_one():
    """Both are "the world time is not usable", and the old substring chain also gave
    them one reason - by accident, because both sentences contain "occurred_at". Now it
    is a decision written in the mapping."""
    naive = envelope.check_envelope(_Atom(occurred_at=datetime(2026, 1, 1)))
    assert gate._envelope_reason(naive) == gate.REFUSE_MISSING_OCCURRED_AT


def test_an_unmapped_code_still_gets_a_truthful_refusal():
    """⚠️ A new envelope check must not raise KeyError here. The old chain fell through to
    NOT_TRUE_ALONE for anything it did not recognise, and so does this."""
    assert gate._envelope_reason([{"code": "something_added_later",
                                   "path": "atom.x", "message": "..."}]) == \
        gate.REFUSE_NOT_TRUE_ALONE


def test_every_code_the_envelope_can_emit_is_either_mapped_or_deliberately_not():
    """The mapping is small and the fallback is honest, so this asserts the pair rather
    than demanding a row per code: two of the six share a reason, and the two source
    fields fall through to NOT_TRUE_ALONE exactly as before."""
    every = {envelope.ENVELOPE_OCCURRED_AT_MISSING, envelope.ENVELOPE_OCCURRED_AT_NAIVE,
             envelope.ENVELOPE_SOURCE_WHO_EMPTY, envelope.ENVELOPE_TRANSLATOR_VER_EMPTY,
             envelope.ENVELOPE_RAW_REF_EMPTY, envelope.ENVELOPE_PAYLOAD_NOT_PRESERVABLE}
    for code in every:
        reason = gate._envelope_reason([{"code": code, "path": "p", "message": "m"}])
        assert reason in gate.REFUSAL_REASONS, (code, reason)
