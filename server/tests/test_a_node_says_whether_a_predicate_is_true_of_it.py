# -*- coding: utf-8 -*-
"""S-149. 「이 술어가 이 주어에 대해 참인가」 — three values, and `false` has to be earned.

🔴 THE GAP WAS NEVER THE OPERATOR, IT WAS THE TRUSTWORTHINESS OF ABSENCE (measured, S-149).
`true` was already answerable — a count of 1 is a fact, and truncation cannot manufacture
one. `false` was not: a count of 0 is one of the five zeros (absent · cut · out of hops ·
not followed · not attached), and `truncated` is a WALK-level flag that cannot be narrowed
to one predicate.

🔴 SO `false` IS EARNED BY A DECLARATION. `absence_confirmed_by` (S-147-a) names the
examination; a zero means something only when that examination happened to THIS subject and
the walk was COMPLETE. Anything else is `unknown`, which a guard refuses.

⚠️ THE POPULATION IS THE DECLARATION, NOT THE DATA. `predicates[]` only carries predicates
that were attached, so a `false` verdict — by definition about a predicate with no claims —
has no row there. That is why this is a sibling cell rather than a wider `predicates[]`.

⚠️ AND THE CELL IS EMPTY ON THE SHIPPED DECLARATION, because nothing names a confirmer yet.
These cases declare their own, which is the only honest way to score a cell an operator
fills.
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

NOW = datetime(2026, 9, 13, 3, 0, tzinfo=timezone.utc)
SEED = ledger_explorer.entity_id("wafer", {"wid": "W0"})

PREDICATE = {"status": "active", "subjects": ["wafer@1"],
             "object": {"kind": "none", "qualifiers": {"required": [], "optional": []}}}


@pytest.fixture
def declared(tmp_path, monkeypatch, request):
    """A declaration of this test's own, read through the walk's own cached reader."""
    def declare(vocabulary, entities=None):
        root = tmp_path / "ontology"
        root.mkdir(exist_ok=True)
        (root / "ledger_config.json").write_text(json.dumps({
            "entities": entities or {"wafer@1": {"keys": ["wid"]}},
            "vocabulary": vocabulary,
        }), encoding="utf-8")

        import paths

        monkeypatch.setattr(paths, "config_path",
                            lambda *parts: str(tmp_path.joinpath(*parts)))
        ledger_subgraph.reset_declaration_cache()
    request.addfinalizer(ledger_subgraph.reset_declaration_cache)
    return declare


def _confirmed():
    """`observed` is confirmed absent by `inspected`, and both are declared."""
    return {"inspected@1": dict(PREDICATE),
            "observed@1": dict(PREDICATE, absence_confirmed_by="inspected@1")}


def _atom(number, predicate, kind=None, payload=None):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="wafer", subject_keys={"wid": "W0"},
        predicate=predicate, object_kind=kind, object_payload=payload, occurred_at=NOW,
        source_who="w", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=900 + number)),
        source_event_state="source_molecule")


def _seen(atoms, **kwargs):
    body = ledger_subgraph.subgraph(
        SEED, ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=2, **kwargs)
    node = next(n for n in body["nodes"] if n["id"] == SEED)
    return body, node


def _die(number, name):
    return _atom(number, name, kind="entity_ref",
                 payload={"type": "die", "keys": {"d": "D%d" % number}})


# ---------------------------------------------------------------------------
# 🔴 the three values
# ---------------------------------------------------------------------------

def test_a_predicate_that_happened_is_true(declared):
    declared(_confirmed())

    _body, node = _seen([_die(10, "inspected"), _die(11, "observed")])

    assert node["absence"]["observed"]["verdict"] == "true"
    assert node["absence"]["observed"]["why"] is None


def test_examined_and_not_found_on_a_complete_walk_is_FALSE(declared):
    """🔴 THE ANSWER THAT DID NOT EXIST. The examination happened to this subject, the
    finding did not, and nothing was cut — only then is a zero a fact about the world."""
    declared(_confirmed())

    body, node = _seen([_die(10, "inspected")])

    assert body["propagation"]["complete"] is True
    assert node["absence"]["observed"]["verdict"] == "false"


def test_not_examined_is_UNKNOWN_rather_than_false(declared):
    """⛔ THE WHOLE POINT. Without the examination a zero says nothing, and answering
    `false` would let a guard write on an absence nobody established."""
    declared(_confirmed())

    _body, node = _seen([_die(10, "some_other_predicate")])

    assert node["absence"]["observed"]["verdict"] == "unknown"


def test_a_cut_walk_cannot_say_false(declared):
    """🔴 A ZERO UNDER A BUDGET IS THE BUDGET. The examination may simply not have been
    reached, and `truncated` is a walk-level flag that cannot be narrowed to one predicate —
    which is exactly why `complete` is part of earning `false`."""
    declared(_confirmed())

    body, node = _seen([_die(10, "inspected")] + [_die(20 + i, "inspected")
                                                 for i in range(30)],
                       node_limit=5)

    assert any(body["truncated"].values())
    assert node["absence"]["observed"]["verdict"] == "unknown"
    assert node["absence"]["observed"]["why"] in body["truncated"]["reason"]


# ---------------------------------------------------------------------------
# ⚠️ why, in words that already exist
# ---------------------------------------------------------------------------

def test_an_undeclared_examination_says_so_by_name(declared):
    """⚠️ A CONFIRMER POINTING AT NOTHING IS THE OPERATOR'S TYPO TO FIX, and it must not
    read as 「not examined」 — that would send them looking at the data instead of the
    declaration. (The validator refuses this on save; a declaration written before that
    landed can still be on disk, and the walk must not guess.)"""
    declared({"observed@1": dict(PREDICATE, absence_confirmed_by="nowhere@1")})

    _body, node = _seen([_die(10, "some_other_predicate")])

    assert node["absence"]["observed"] == {"verdict": "unknown",
                                           "why": "not_declared"}


def test_a_complete_walk_that_simply_did_not_examine_says_not_examined(declared):
    """🔴 THE THIRD `why`, AND I ADDED THE WORD. The ruling named two; measuring the cases
    turned up one they do not cover — the confirmer IS declared, the walk IS complete, and
    the examination did not happen for this subject. `not_declared` would be false and a
    truncation key would be false, so mislabelling it would put a wrong reason where an
    operator reads one."""
    declared(_confirmed())

    body, node = _seen([_die(10, "some_other_predicate")])

    assert body["propagation"]["complete"] is True
    assert node["absence"]["observed"]["why"] == "not_examined"


# ---------------------------------------------------------------------------
# 🔴 the population is the declaration
# ---------------------------------------------------------------------------

def test_nothing_declared_leaves_the_cell_absent(declared):
    """⚠️ TODAY'S SHIPPED DECLARATION NAMES NO CONFIRMER, so this is the state the product
    is in right now. The cell fills as operators write, and an empty walk says nothing about
    whether the mechanism works."""
    declared({"observed@1": dict(PREDICATE)})

    _body, node = _seen([_die(10, "observed")])

    assert "absence" not in node


def test_a_predicate_with_no_claims_still_gets_a_verdict(declared):
    """🔴 WHY THIS IS NOT A WIDER `predicates[]`. That array is built from ATTACHED claims,
    so the predicate a `false` verdict is about has no row in it at all."""
    declared(_confirmed())

    _body, node = _seen([_die(10, "inspected")])

    assert "observed" not in {row["predicate"] for row in node["predicates"]}
    assert node["absence"]["observed"]["verdict"] == "false"


def test_the_version_does_not_have_to_be_spelled(declared):
    declared({"inspected@1": dict(PREDICATE),
              "observed@1": dict(PREDICATE, absence_confirmed_by="inspected@1")})

    _body, node = _seen([_die(10, "inspected")])

    assert "observed" in node["absence"], "the finding is keyed bare"


# ---------------------------------------------------------------------------
# 🔴 through the route, on the connection the product holds
# ---------------------------------------------------------------------------

def test_the_envelope_carries_the_cell_through_the_mounted_route(declared, monkeypatch):
    """🔴 THE SEAT S-148-a GOT WRONG THREE TIMES, scored here from the start: the real
    router, and only the STORAGE substituted, so FastAPI's validation and the handler's own
    wiring both run."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import ledger_trace_router
    from admin_auth import require_admin_token
    from database.database import get_db

    declared(_confirmed())
    monkeypatch.setattr(ledger_trace_router.ledger_trace, "relation_exists",
                        lambda *a, **k: True)
    monkeypatch.setattr(ledger_trace_router, "_subgraph_contract_state",
                        lambda *a, **k: [])
    monkeypatch.setattr(
        ledger_subgraph, "SqlEvidenceLookup",
        lambda *a, **k: ledger_subgraph.InMemoryEvidenceLookup([_die(10, "inspected")]))

    class _Db:
        def connection(self):
            return object()

    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[get_db] = lambda: _Db()
    app.include_router(ledger_trace_router.router)

    answer = TestClient(app).get("/api/ledger/subgraph",
                                 params={"id": SEED, "hops": 2})

    assert answer.status_code == 200, answer.text
    node = next(n for n in answer.json()["nodes"] if n["id"] == SEED)
    assert node["absence"]["observed"]["verdict"] == "false"


def test_the_verdict_costs_no_second_walk(declared):
    """⚠️ SAME WALK, SAME BUDGET — scored by the lookup's call count, as every other fold in
    this module is."""
    declared(_confirmed())
    lookup = ledger_subgraph.InMemoryEvidenceLookup([_die(10, "inspected")])
    calls = []
    real = lookup.claims_for_entities

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    lookup.claims_for_entities = spy
    ledger_subgraph.subgraph(SEED, lookup, hops=2)
    with_cell = len(calls)

    ledger_subgraph.reset_declaration_cache()
    calls.clear()
    lookup.claims_for_entities = spy
    ledger_subgraph.subgraph(SEED, lookup, hops=2)

    assert len(calls) == with_cell
