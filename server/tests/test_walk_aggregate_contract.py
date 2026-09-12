# -*- coding: utf-8 -*-
"""S-146. The walk folds its own population — scored against the shared contract vector.

🔴 THE AXIS MOVED BECAUSE THE POPULATION DID (판정 331). `group`/`aggregate` are not new
generators — BASIS §3.5 already says they exist and that the defect is 「자리의 문제」. The
client has folded these seven since the board was built, and measured: `trendFromWalk`
REFUSES to fold a truncated walk. So at 10⁸ the screen does not show a skewed number, it
shows nothing at all. Counting where the population is whole is the fix.

🔴 THE SEVEN ARE THE CLIENT'S SEVEN, VERBATIM. Inventing an eighth, or renaming one, would
make the screen and the answer disagree about what 「mean」 means; `contracts/walk_aggregate/`
scores both sides against one expectation, and the client half is C-90.

⚠️ ONE WALK AND ONE BUDGET. A second traversal for the aggregate would put two populations
in one answer, and a reader could not tell which number came from which. Whether the number
stands on a whole population is said by the envelope's own `truncated`/`complete` — one
spelling for one fact rather than a second absence word inside `groups`.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_explorer                                             # noqa: E402
from ledger_api import ledger_subgraph                             # noqa: E402

VECTORS = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "contracts", "walk_aggregate", "vectors.json"))


def _contract():
    with open(VECTORS, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 🔴 the shared vector, scored on the server side
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vector", _contract()["vectors"],
                         ids=[v["name"] for v in _contract()["vectors"]])
def test_the_server_folds_the_shared_vector(vector):
    groups = ledger_subgraph.group_nodes(
        vector["nodes"], vector["group_by"], vector["measure"])
    assert groups == vector["groups"]


@pytest.mark.parametrize("case", _contract()["refusals"],
                         ids=[c["name"] for c in _contract()["refusals"]])
def test_a_refusal_is_named_and_carries_the_choices(case):
    """⛔ A MISSPELLED MEASURE MUST NOT FALL BACK TO `count`. That would answer a question
    nobody asked, with a number that looks exactly like a right one."""
    with pytest.raises(ledger_subgraph.AggregateRefused) as refused:
        ledger_subgraph.group_nodes(
            case.get("nodes") or [{"id": "a", "type": "w", "attributes": {}}],
            case["group_by"], case["measure"])

    assert refused.value.code == case["code"]
    assert refused.value.detail


def test_the_seven_are_the_clients_seven():
    """🔴 THE VOCABULARY HAS ONE AUTHOR. The client's table is the one an operator has been
    choosing from; this asserts the server did not quietly gain an eighth or rename one."""
    assert ledger_subgraph.AGGREGATE_MEASURES == (
        "count", "distinct", "sum", "mean", "min", "max", "median")
    assert ledger_subgraph.NUMERIC_MEASURES == {"sum", "mean", "min", "max", "median"}


def test_the_contract_vector_exercises_every_measure():
    """⚠️ A VECTOR FILE IS ONLY AS GOOD AS ITS COVERAGE, and a measure nobody wrote a case
    for is a measure the two sides may already disagree about."""
    contract = _contract()
    used = {str(v["measure"]).partition(":")[0] for v in contract["vectors"]}
    used |= {str(c["measure"]).partition(":")[0] for c in contract["refusals"]}
    missing = set(ledger_subgraph.AGGREGATE_MEASURES) - used
    assert not missing, "no contract vector folds: %s" % sorted(missing)


# ---------------------------------------------------------------------------
# 🔴 through the walk, on one budget
# ---------------------------------------------------------------------------

NOW = datetime(2026, 9, 13, 1, 0, tzinfo=timezone.utc)
SEED = ledger_explorer.entity_id("wafer", {"wid": "W1"})


def _atom(number, predicate, *, payload=None, kind=None):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="wafer", subject_keys={"wid": "W1"},
        predicate=predicate, object_kind=kind, object_payload=payload, occurred_at=NOW,
        source_who="wafer", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=900 + number)),
        source_event_state="source_molecule")


def _walk(**kwargs):
    return ledger_subgraph.subgraph(
        SEED, ledger_subgraph.InMemoryEvidenceLookup(
            [_atom(1, "register", payload={"qualifiers": {"product": "A"}})]),
        hops=1, **kwargs)


def test_without_the_argument_the_envelope_has_no_such_key():
    """🔴 THREE STATES, NOT TWO. 「안 물었다」·「물었는데 무리가 없다」·「무리가 있다」 —
    a `null` collapses the first two, and a reader cannot recover the difference."""
    assert "groups" not in _walk()


def test_asking_puts_the_fold_in_the_same_envelope():
    body = _walk(group_by="type", measure="count")

    assert "groups" in body
    assert {row["key"] for row in body["groups"]} == {
        str(node.get("type") or "") for node in body["nodes"]}
    assert sum(row["n"] for row in body["groups"]) >= len(body["nodes"])


def test_the_fold_rides_the_walk_that_already_ran():
    """🔴 ONE WALK, ONE BUDGET (판정 331). A second traversal for the aggregate would put two
    populations in one answer. Scored by counting the lookup's calls: asking for a fold must
    not ask the store anything the same walk did not already ask."""
    lookup = ledger_subgraph.InMemoryEvidenceLookup(
        [_atom(1, "register", payload={"qualifiers": {"product": "A"}})])
    calls = []
    real = lookup.claims_for_entities

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    lookup.claims_for_entities = spy
    ledger_subgraph.subgraph(SEED, lookup, hops=1)
    without = len(calls)

    calls.clear()
    lookup.claims_for_entities = spy
    ledger_subgraph.subgraph(SEED, lookup, hops=1, group_by="type", measure="count")

    assert len(calls) == without, "the fold walked again"


def test_a_truncated_walk_still_answers_and_says_it_is_truncated():
    """🔴 판정 331 ②ⓑ. The number comes out AND the same envelope says the population was
    cut — rather than the client's posture of refusing, which at operating scale is a
    permanently blank screen. The skew is named where truncation is already named; a second
    word inside `groups` would be two spellings for one fact."""
    lookup = ledger_subgraph.InMemoryEvidenceLookup(
        [_atom(1, "register", payload={"qualifiers": {"product": "A"}})]
        + [_atom(10 + n, "inspected", kind="entity_ref",
                 payload={"type": "die", "keys": {"d": "D%d" % n}})
           for n in range(40)])

    body = ledger_subgraph.subgraph(SEED, lookup, hops=2, node_limit=10,
                                    group_by="type", measure="count")

    assert body["groups"], "a truncated walk still states what it counted"
    assert any(body["truncated"].values()), "and the same envelope says it was cut"
    assert "absence" not in json.dumps(body["groups"]), "no second spelling inside groups"


# ---------------------------------------------------------------------------
# 🔴 the route names the refusal (판정 331)
# ---------------------------------------------------------------------------

def test_the_handler_turns_the_refusal_into_a_named_422_with_the_choices():
    """⛔ NOT `subgraph_request_invalid`. That tells a caller their request was wrong and
    not WHICH WORD — and a screen that offers measures cannot repair a refusal it cannot
    read. The same posture as `node_type_not_declared`, which hands back `declared`.

    ⚠️ SCORED AT THE HANDLER'S OWN TRANSLATION, because reaching the route needs a live
    ledger relation; what this pins is the branch that exists solely to keep the generic
    `ValueError` arm from swallowing a refusal that has a name. `AggregateRefused` IS a
    `ValueError`, so without that branch it would 422 with the wrong reason and nothing
    would fail.
    """
    import inspect

    import ledger_trace_router

    body = inspect.getsource(ledger_trace_router.evidence_subgraph)
    assert "AggregateRefused" in body, (
        "the named refusal has no arm, so it falls into the generic ValueError one")

    # ⚠️ ANCHORED TO THE TRY BLOCK THAT WALKS. Measured while writing this: the handler has
    # an EARLIER `except ValueError` guarding interval parsing, in a different try, and a
    # naive first-occurrence comparison read that as the generic arm winning. The number
    # was real and it was counting the wrong thing.
    walked = body.index("_evidence_graph(")
    named = body.index("AggregateRefused", walked)
    generic = body.index("except ValueError", walked)
    assert named < generic, (
        "the generic arm is first, so it swallows the named refusal before it is reached")


def test_the_refusal_carries_what_to_choose_instead():
    """⚠️ A REFUSAL AN OPERATOR CANNOT ACT ON IS A CRASH WITH BETTER MANNERS."""
    with pytest.raises(ledger_subgraph.AggregateRefused) as refused:
        ledger_subgraph.group_nodes([], "type", "avg")

    assert refused.value.choices == ledger_subgraph.AGGREGATE_MEASURES
    assert "avg" in refused.value.detail


def test_the_route_declares_both_arguments():
    """⚠️ A PRIMITIVE NO ROUTE EXPOSES IS 「착지는 배선이 아니다」. This round's whole point is
    that the fold happens where the population is, which it cannot if nobody can ask."""
    import inspect

    import ledger_trace_router

    signature = inspect.signature(ledger_trace_router.evidence_subgraph)
    assert "group_by" in signature.parameters
    assert "measure" in signature.parameters


# ---------------------------------------------------------------------------
# 🔴 S-146-c — several measures, a time, and one shape per cell (판정 336)
# ---------------------------------------------------------------------------

def test_the_value_is_a_map_even_for_one_measure():
    """🔴 ONE CELL, ONE SHAPE. A number for one measure and a map for two is a cell a reader
    has to type-check before using — the class this channel has been bitten by twice."""
    groups = ledger_subgraph.group_nodes(
        [{"id": "a", "type": "w", "attributes": {}}], "type", "count")

    assert groups[0]["value"] == {"count": 2 - 1}
    assert isinstance(groups[0]["value"], dict)


def test_a_group_carries_the_newest_time_of_the_edges_that_reached_it():
    """🔴 AN ENTITY HAS NO INSTANT AND SHOULD NOT. Measured: only edges carry `occurred_at`;
    entity nodes carry none, because a thing has no single time and its facts do."""
    nodes = [{"id": "a", "type": "w", "attributes": {"g": "x"}},
             {"id": "b", "type": "w", "attributes": {"g": "x"}}]
    edges = [{"source": "a", "target": "z", "occurred_at": "2026-09-13T01:00:00Z"},
             {"source": "b", "target": "z", "occurred_at": "2026-09-13T03:00:00Z"}]

    groups = ledger_subgraph.group_nodes(nodes, "g", "count", edges)

    assert groups[0]["at"] == "2026-09-13T03:00:00Z"


def test_a_group_whose_nodes_carry_no_dated_edge_has_NO_at_key():
    """⛔ ABSENT, NOT `null`. 「this group has no fact with a time」 and 「the caller did not
    ask for grouping at all」 must not collapse into one value."""
    groups = ledger_subgraph.group_nodes(
        [{"id": "a", "type": "w", "attributes": {"g": "x"}}], "g", "count")

    assert "at" not in groups[0]
    assert set(groups[0]) == {"key", "n", "value"}


def test_the_envelope_says_where_a_measure_name_is_looked_up():
    """⚠️ THE ORDER IS DECLARED, NOT GUESSED. The screen has to be able to explain an
    `ambiguous_value_name` refusal, which it cannot if it does not know the order."""
    body = _walk(group_by="type", measure="count")

    assert body["value_sources"] == list(ledger_subgraph.VALUE_SOURCES)
    assert "predicates" in body["value_sources"], (
        "a predicate id must be a value name, or the ratio axis has nowhere to go")


def test_asking_for_a_time_does_not_walk_again():
    """🔴 EDGES ARE AN INPUT, NOT A SECOND POPULATION (판정 336). They come from the walk that
    already ran; scored by the lookup's call count, as the one-budget rule is."""
    lookup = ledger_subgraph.InMemoryEvidenceLookup(
        [_atom(1, "register", payload={"qualifiers": {"product": "A"}})])
    calls = []
    real = lookup.claims_for_entities

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    lookup.claims_for_entities = spy
    ledger_subgraph.subgraph(SEED, lookup, hops=1)
    without = len(calls)

    calls.clear()
    lookup.claims_for_entities = spy
    ledger_subgraph.subgraph(SEED, lookup, hops=1, group_by="type",
                             measure=["count", "distinct"])

    assert len(calls) == without, "asking for two measures and a time walked again"
