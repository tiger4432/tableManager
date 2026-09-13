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

from ledger import explorer                                             # noqa: E402
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
    case = explorer.entity_id("wafer", {"wid": "W0"})

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
        {"positive": [], "negative": [explorer.entity_id("wafer", {"wid": "W0"})]},
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
    seed = explorer.entity_id("wafer", {"wid": "W0"})
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

    from ledger import trace_router

    body = inspect.getsource(trace_router.evidence_subgraph)
    assert "seeds_defined_twice" in body
    assert body.index("seeds_defined_twice") < body.index("_evidence_graph("), (
        "the refusal must come before the walk, or the walk happens anyway")


def test_the_route_declares_both_arguments():
    import inspect

    from ledger import trace_router

    signature = inspect.signature(trace_router.evidence_subgraph)
    assert "seed_type" in signature.parameters
    assert "seed_limit" in signature.parameters


def test_the_enumeration_goes_through_this_class_own_runner():
    """🔴 ONE CLASS, ONE WAY OF EMITTING SQL — and this is scored because the first landing
    did NOT. It called `self.connection.cursor()`, a DBAPI call, while the connection this
    class holds in the product is a SQLAlchemy `Connection` with no `cursor`: the route
    answered 500 on the box and every test passed, because the tests handed it a connection
    of a different kind. 「시험이 여는 문서 ≠ 제품이 여는 문서」.

    `_execute` is the sibling path (`ledger_trace._fetch`), and it is what handles BOTH
    connection shapes — so going through it is what makes this work for the product rather
    than only for a fixture.
    """
    import inspect

    source = inspect.getsource(ledger_subgraph.SqlEvidenceLookup.subjects_of_type)
    tokens = _code_without_prose(source)

    assert "self._execute(" in tokens, "the class's own runner is not used"
    assert ".cursor(" not in tokens, (
        "a DBAPI cursor is a second way of emitting SQL, and the product's connection "
        "does not have one")


def _code_without_prose(source):
    """The code, with comments and docstring stripped.

    ⚠️ MEASURED TWICE TODAY: a source oracle passes on text that sits in a comment, in both
    directions — a note that names the forbidden thing, and a clause commented OUT.
    """
    import io as _io
    import tokenize

    kept, previous_end = [], (0, 0)
    for token in tokenize.generate_tokens(_io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        if token.start[0] != previous_end[0]:
            kept.append(chr(10))
        kept.append(token.string)
        previous_end = token.end
    return "".join(kept)


# ---------------------------------------------------------------------------
# 🔴 THROUGH THE MOUNTED ROUTE — the layer a direct call cannot see
# ---------------------------------------------------------------------------
#
# 🔴 THIS IS THE GATE I OWED AND SUBSTITUTED. The first landing of S-148-a asserted the
# handler's SIGNATURE instead of calling the route, and the defect was one layer above the
# handler: `id` was `Query(...)`, so FastAPI refused `seed_type=wafer` with
# `{"loc": ["query", "id"], "msg": "Field required"}` before any of this code ran. I wrote
# the rule myself in S-204 ② -- 「every defect a direct call cannot see lives BETWEEN the
# route and the function」 -- and then tested the function.

@pytest.fixture
def route_client(monkeypatch):
    """The real router, mounted. Only the STORAGE is substituted, so FastAPI's own
    validation layer -- the one that held this defect -- runs for real."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ledger import trace_router
    from admin.auth import require_admin_token
    from database.database import get_db

    monkeypatch.setattr(trace_router.trace, "relation_exists",
                        lambda *a, **k: True)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state",
                        lambda *a, **k: [])
    monkeypatch.setattr(
        ledger_subgraph, "SqlEvidenceLookup",
        lambda *a, **k: ledger_subgraph.InMemoryEvidenceLookup(_registered(4)))

    class _Db:
        def connection(self):
            return object()

    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[get_db] = lambda: _Db()
    app.include_router(trace_router.router)
    return TestClient(app)


def test_a_description_alone_reaches_the_walk(route_client):
    """🔴 THE FIRST LINE OF THIS ROUND'S GATE, finally scored where it lives."""
    answer = route_client.get("/api/ledger/subgraph",
                              params={"seed_type": "wafer", "hops": 1})

    assert answer.status_code == 200, answer.text
    assert len(answer.json()["seeds"]) == 4


def test_naming_no_seeds_at_all_is_refused_by_name(route_client):
    """⚠️ MADE REACHABLE BY THIS FIX. While `id` was required FastAPI answered this with a
    generic 「Field required」; now the three states are ours to say."""
    answer = route_client.get("/api/ledger/subgraph", params={"hops": 1})

    assert answer.status_code == 422
    assert answer.json()["detail"]["reason"] == "seeds_not_defined"


def test_naming_seeds_twice_is_refused_by_name(route_client):
    answer = route_client.get("/api/ledger/subgraph", params={
        "id": explorer.entity_id("wafer", {"wid": "W0"}),
        "seed_type": "wafer", "hops": 1})

    assert answer.status_code == 422
    assert answer.json()["detail"]["reason"] == "seeds_defined_twice"


def test_an_enumerated_seed_still_answers_exactly_as_before(route_client):
    """⚠️ THE HALF THAT MUST NOT MOVE. `id` became optional so a description could arrive;
    a caller that passes one must see no change at all."""
    answer = route_client.get("/api/ledger/subgraph", params={
        "id": explorer.entity_id("wafer", {"wid": "W0"}), "hops": 1})

    assert answer.status_code == 200, answer.text
    assert len(answer.json()["seeds"]) == 1


# ---------------------------------------------------------------------------
# 🔴 THE PRODUCT'S CONNECTION KIND — the shape that 500'd on the box
# ---------------------------------------------------------------------------

class _SqlAlchemyShapedConnection:
    """A connection with `exec_driver_sql` and NO `cursor` — what the route actually holds.

    🔴 THIS IS THE BOX'S FAILURE, REPRODUCED. `db.connection()` hands the walk a SQLAlchemy
    `Connection`; the first landing called `.cursor()` on it and the route answered 500 with
    `AttributeError: 'Connection' object has no attribute 'cursor'`. Every test passed,
    because every test handed it a connection of the OTHER kind.

    ⚠️ `cursor` IS ABSENT RATHER THAN RAISING, because that is how `ledger_trace._fetch`
    chooses its branch — `hasattr(conn, "cursor")`. A fake that merely raised would take the
    psycopg2 path and prove nothing.
    """

    def __init__(self, rows):
        self.rows = rows
        self.seen = []

    def exec_driver_sql(self, sql, params=None):
        self.seen.append((" ".join(sql.split()), params))
        return list(self.rows)


def test_the_description_resolves_on_the_connection_the_route_actually_holds():
    """🔴 THE GATE THAT WAS MISSING. Not 「does the query look right」 but 「does it run on
    the thing the product hands it」."""
    connection = _SqlAlchemyShapedConnection(
        [("wafer", '{"wid": "W0"}'), ("wafer", '{"wid": "W1"}')])
    lookup = ledger_subgraph.SqlEvidenceLookup(connection)

    described = lookup.subjects_of_type("wafer@1", 10)

    assert described.cut == 0
    assert described.ids == [explorer.entity_id("wafer", {"wid": "W0"}),
                             explorer.entity_id("wafer", {"wid": "W1"})]


def test_the_budget_reaches_the_database_and_asks_for_one_more():
    """⚠️ SCORED ON THE STATEMENT THAT RUNS, not on the source — measured today that a
    source oracle passes a commented-out clause."""
    connection = _SqlAlchemyShapedConnection([])
    ledger_subgraph.SqlEvidenceLookup(connection).subjects_of_type("wafer", 25)

    statement, params = connection.seen[0]
    assert "--" not in statement, "a commented-out clause still reads as present"
    assert statement.rstrip().endswith("LIMIT %(fetch)s"), statement
    assert params["fetch"] == 26, "one row past the budget makes 「there were more」 a fact"
    assert params["predicate"] == "register"
    assert params["subject_type"] == "wafer", "the version is folded before the index"


def test_subject_keys_arrive_as_text_or_as_a_mapping():
    """⚠️ TWO DRIVERS, TWO SHAPES — the same two-shaped handling `_atom_from_row` does. A
    reader that assumed one would work on one deployment and not the other."""
    as_text = ledger_subgraph.SqlEvidenceLookup(
        _SqlAlchemyShapedConnection([("wafer", '{"wid": "W0"}')])).subjects_of_type("wafer", 5)
    as_mapping = ledger_subgraph.SqlEvidenceLookup(
        _SqlAlchemyShapedConnection([("wafer", {"wid": "W0"})])).subjects_of_type("wafer", 5)

    assert as_text.ids == as_mapping.ids


def test_an_undeclared_type_is_refused_before_the_query_runs(route_client, monkeypatch):
    """⛔ ASKING THE LEDGER FOR A TYPE THE DECLARATION NEVER NAMED RETURNS ZERO ROWS, which
    would read as 「that type has no subjects」 — a fact about the data rather than about the
    request. The walk already refuses an undeclared `collect` this way."""
    monkeypatch.setattr(ledger_subgraph, "_declared_entity_facts_names",
                        lambda: frozenset({"wafer"}))

    answer = route_client.get("/api/ledger/subgraph",
                              params={"seed_type": "nosuchtype", "hops": 1})

    assert answer.status_code == 422, answer.text
    assert answer.json()["detail"]["reason"] == "seed_type_not_declared"
    assert "wafer" in answer.json()["detail"]["choices"]
