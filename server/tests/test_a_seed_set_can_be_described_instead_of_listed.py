# -*- coding: utf-8 -*-
"""S-148-a. 「전체 ∖ 사례」 — a seed set said by TYPE rather than shipped as ids.

🔴 THE CONTROL GROUP'S NATURAL DEFINITION COULD NOT BE ASKED. 「전체 ∖ 사례」 needed 「전체」 to
be enumerated into the query string, and at 10⁸ that list does not fit — so 「the client can
do it」 was not true within spec, and neither was the server: nothing enumerated a type's
instances at all (measured, S-148).

🔴 AND STORING A MARKING WAS ALREADY RULED OUT (총괄 2026-08-24): a saved derivation has no
owner of truth once its sources move. A DESCRIPTION does not — it is re-evaluated per
request, so the ledger stays the only place the answer lives. That is why this is a
description and not a stored set.

⚠️ NO SET OPERATOR IS BUILT. `seed_type` plus `negative[]` IS set difference — two arguments
the walk already reads. Intersection stays where the 08-24 ruling put it: computed at the
reading site.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_explorer                                             # noqa: E402
from ledger_api import ledger_subgraph                             # noqa: E402

NOW = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)


def _atom(number, predicate, subject_type="wafer", wid="W0", kind=None, payload=None):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type,
        subject_keys={"wid": wid}, predicate=predicate, object_kind=kind,
        object_payload=payload, occurred_at=NOW, source_who="w",
        source_translator_ver="v1", source_raw_ref="row:%d" % number, supersedes=None,
        source_event_id=str(uuid.UUID(int=900 + number)),
        source_event_state="source_molecule")


def _registered(count, subject_type="wafer"):
    return [_atom(10 + i, "register", subject_type=subject_type, wid="W%d" % i,
                  payload={"qualifiers": {"product": "A"}})
            for i in range(count)]


def _walk(atoms, **kwargs):
    return ledger_subgraph.subgraph(
        None, ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=1, **kwargs)


# ---------------------------------------------------------------------------
# 🔴 the description
# ---------------------------------------------------------------------------

def test_a_type_names_every_registered_subject_of_it():
    body = _walk(_registered(4), seed_type="wafer")

    assert len(body["seeds"]) == 4
    assert all(seed["sign"] == "+" for seed in body["seeds"])


def test_only_REGISTERED_subjects_are_named():
    """⚠️ THE SAME RULE AS EXISTENCE (A1). A subject that only ever appeared as somebody
    else's object was never registered, and seeding from it would walk from something the
    declaration does not say exists."""
    atoms = _registered(2) + [_atom(50, "inspected", wid="ghost")]

    assert len(_walk(atoms, seed_type="wafer")["seeds"]) == 2


def test_the_version_does_not_have_to_be_spelled():
    assert len(_walk(_registered(3), seed_type="wafer@1")["seeds"]) == 3


def test_a_type_nothing_registered_is_refused_by_name():
    """⛔ AN EMPTY WALK WOULD READ AS 「이 타입에 아무 증거가 없다」, which is a different and
    much stronger claim than 「그런 씨앗이 없다」."""
    with pytest.raises(ValueError) as refused:
        _walk(_registered(2), seed_type="defect")

    assert "defect" in str(refused.value)


# ---------------------------------------------------------------------------
# 🔴 set difference without a set operator
# ---------------------------------------------------------------------------

def test_the_description_and_negatives_are_the_whole_of_set_difference():
    """🔴 THE POINT OF THE ROUND. Two arguments, no algebra: the walk gets 「everything of
    this type」 and 「except these」, which is what a control group has always meant."""
    atoms = _registered(4)
    case = ledger_explorer.entity_id("wafer", {"wid": "W0"})

    body = ledger_subgraph.subgraph(
        {"positive": [], "negative": [case]},
        ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=1, seed_type="wafer")

    signs = {seed["id"]: seed["sign"] for seed in body["seeds"]}
    assert signs[case] == "-", "the named case is the control side"
    # 🔴 THREE, NOT FOUR: the excepted subject LEFT the described side. That subtraction is
    # the set difference, and doing it is what let this round build no operator.
    assert sum(1 for sign in signs.values() if sign == "+") == 3
    assert case not in {seed["id"] for seed in body["seeds"] if seed["sign"] == "+"}


def test_the_two_sides_come_back_as_a_pair_exactly_as_they_do_today():
    """⚠️ NO NEW SHAPE. `_propagation` already reports reach as a signed pair; a described
    seed set must not invent a second way of saying which side a number came from."""
    atoms = _registered(3)
    body = ledger_subgraph.subgraph(
        {"positive": [], "negative": [ledger_explorer.entity_id("wafer", {"wid": "W0"})]},
        ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=1, seed_type="wafer")

    assert body["walk"]["start"]["positive"] == 2
    assert body["walk"]["start"]["negative"] == 1


# ---------------------------------------------------------------------------
# 🔴 the budget, on the pair that already exists
# ---------------------------------------------------------------------------

def test_the_ceiling_rides_the_limits_map_that_is_already_there():
    body = _walk(_registered(3), seed_type="wafer", seed_limit=50)
    assert body["limits"]["seeds"] == 50


def test_seeds_left_out_are_COUNTED_and_the_walk_says_it_is_incomplete():
    """🔴 A WALK THAT STARTED FROM A FIFTH OF THE CONTROLS ANSWERED A NARROWER QUESTION.
    A contrast computed over that is the skew `complete` exists to name, so a seed cut is a
    truncation like every other one."""
    body = _walk(_registered(5), seed_type="wafer", seed_limit=2)

    assert body["truncated"]["seeds"] == 3
    assert "seeds" in body["truncated"]["reason"]
    assert body["propagation"]["complete"] is False


def test_a_count_not_a_flag_because_the_number_is_what_narrows_the_question():
    """⚠️ `interval_excluded` BESIDE IT IS A COUNT FOR THE SAME REASON — 「how much was left
    out」 is what tells an operator whether to ask something smaller."""
    body = _walk(_registered(9), seed_type="wafer", seed_limit=4)
    assert body["truncated"]["seeds"] == 5


def test_an_enumerated_walk_carries_neither_key():
    """⛔ ABSENT, NOT ZERO. A listed seed set has no ceiling of its own, and `seeds: 0` would
    state one that was never applied."""
    seed = ledger_explorer.entity_id("wafer", {"wid": "W0"})
    body = ledger_subgraph.subgraph(
        seed, ledger_subgraph.InMemoryEvidenceLookup(_registered(3)), hops=1)

    assert "seeds" not in body["limits"]
    assert "seeds" not in body["truncated"]


# ---------------------------------------------------------------------------
# ⛔ one question, one definition of its seeds
# ---------------------------------------------------------------------------

def test_the_route_refuses_an_id_and_a_description_together():
    """⛔ SILENTLY PREFERRING ONE WOULD MAKE THAT PREFERENCE THE ANSWER, and the caller
    would read a walk from subjects they did not ask for."""
    import inspect

    import ledger_trace_router

    body = inspect.getsource(ledger_trace_router.evidence_subgraph)
    assert "seeds_defined_twice" in body
    assert body.index("seeds_defined_twice") < body.index("_evidence_graph("), (
        "the refusal must come before the walk, or the walk happens anyway")


def test_the_route_declares_both_arguments():
    import inspect

    import ledger_trace_router

    signature = inspect.signature(ledger_trace_router.evidence_subgraph)
    assert "seed_type" in signature.parameters
    assert "seed_limit" in signature.parameters


def test_the_enumeration_reads_the_seat_that_already_records_existence():
    """⛔ SCORED ON THE SOURCE. The query must go through the PARTIAL index the schema
    already keeps — on (subject_type, subject_keys) where the predicate is the register one,
    which is O(entities) rather than O(atoms). A scan of the whole ledger for this would be
    the cost the description exists to avoid, and it would not show up as a failure
    anywhere."""
    class _Cursor:
        def __init__(self, seen):
            self.seen = seen

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, statement, params):
            self.seen.append((" ".join(statement.split()), params))

        def fetchall(self):
            return []

    class _Connection:
        def __init__(self):
            self.seen = []

        def cursor(self):
            return _Cursor(self.seen)

    connection = _Connection()
    lookup = ledger_subgraph.SqlEvidenceLookup.__new__(ledger_subgraph.SqlEvidenceLookup)
    lookup.connection = connection
    lookup.subjects_of_type("wafer@1", 25)

    # ⚠️ THE STATEMENT THAT RAN, not the source text. Measured: an oracle reading the source
    # passed when the LIMIT was commented OUT, because the word survived in the comment —
    # the same trap as a drift check reading the note that forbids the defect.
    statement, params = connection.seen[0]
    assert "WHERE predicate = %s AND subject_type = %s" in statement, statement
    assert "--" not in statement, (
        "a commented-out clause still READS as present; measured — `-- LIMIT %s` passed an "
        "endswith check, which is the same trap as an oracle reading a comment")
    assert statement.rstrip().endswith("LIMIT %s"), statement
    assert params[0] == "register", "the predicate name comes from the constant"
    assert params[1] == "wafer", "the version is folded before the index is asked"
    assert params[2] == 26, "one row past the budget, so 「there were more」 is a fact"
