# -*- coding: utf-8 -*-
"""S-216. The catalogue says which predicate is the examination, so a screen need not guess.

🔴 THE COLUMN'S POPULATION IS THE DECLARATION, NOT THE DATA (판정 366). S-149 folds an
`absence` verdict onto every node, and a screen drawing that column from the nodes alone shows
the predicates that happened to ARRIVE - which is exactly the misreading the verdict exists to
prevent. `/api/ledger/declaration` is where a client reads the population, and it was handing
over `{name, subjects, object, origin}` with no way to tell a confirmer from anything else.

⚠️ OMITTED, NEVER EMPTIED. The key is absent when no confirmer is declared, the same
discipline `class` and `attributes` already follow on this route: 「this predicate declares no
confirmer」 and 「this deployment predates the axis」 are different facts, and an empty string
would collapse them into one.

⚠️ DRIVEN THROUGH THE MOUNTED ROUTE, not by calling the handler. This route's own siblings
call the function directly, which is fine for what they assert; the gate this round was given
says 「라우트 실호출」, and a handler test is true of a route nobody can reach.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config as _config                                 # noqa: E402
from ledger import trace_router                                      # noqa: E402

PREDICATE = {"subjects": ["wafer@1"], "object": {"kind": "none"}}


@pytest.fixture
def client():
    """The real router, mounted alone. ⚠️ The token half belongs to `test_admin_auth.py`,
    which parametrises over every gated route; a second copy here would be a second answer."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from admin.auth import require_admin_token

    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.include_router(trace_router.router)
    return TestClient(app)


@pytest.fixture
def declared(monkeypatch):
    def declare(vocabulary):
        monkeypatch.setattr(_config, "load", lambda: {
            "entities": {"wafer@1": {"keys": ["wid"]}},
            "vocabulary": vocabulary})
    return declare


def _predicates(client):
    # 🔴 THE MOUNTED PATH, prefix and all - the address a client actually types.
    answer = client.get("/api/ledger/declaration")
    assert answer.status_code == 200, answer.text
    return {row["name"]: row for row in answer.json()["predicates"]}


# ---------------------------------------------------------------------------
# 🔴 the declared confirmer, and only it
# ---------------------------------------------------------------------------

def test_the_confirming_predicate_is_named_on_the_one_that_declares_it(declared, client):
    """🔴 THE ROUND. A screen can now ask 「which predicate examines for this one」 without
    reading the data or holding a list of its own."""
    declared({"inspected@1": dict(PREDICATE),
              "observed@1": dict(PREDICATE, absence_confirmed_by="inspected@1")})

    rows = _predicates(client)

    assert rows["observed@1"]["absence_confirmed_by"] == "inspected@1"


def test_the_predicate_that_declares_none_has_no_key_at_all(declared, client):
    """⚠️ ABSENT, NOT EMPTY. `""` would say 「declared, and it is nothing」."""
    declared({"inspected@1": dict(PREDICATE),
              "observed@1": dict(PREDICATE, absence_confirmed_by="inspected@1")})

    rows = _predicates(client)

    assert "absence_confirmed_by" not in rows["inspected@1"], rows["inspected@1"]


def test_a_declaration_with_no_confirmer_anywhere_publishes_no_such_key(declared, client):
    """⚠️ TODAY'S SHIPPED DECLARATION NAMES NO CONFIRMER, so this is the state the product is
    in right now - and the absence of the key is what tells a client the axis is unused here
    rather than unsupported."""
    declared({"inspected@1": dict(PREDICATE), "observed@1": dict(PREDICATE)})

    rows = _predicates(client)

    assert rows, "the fixture declared nothing; this would prove nothing"
    assert all("absence_confirmed_by" not in row for row in rows.values())


def test_the_rest_of_the_row_is_unchanged(declared, client):
    """⛔ NOTHING ELSE MOVED. The four keys a client already reads are still there and still
    spelled the same way - a new cell must not be a silent rename of an old one."""
    declared({"observed@1": dict(PREDICATE, absence_confirmed_by="inspected@1")})

    row = _predicates(client)["observed@1"]

    assert row["subjects"] == ["wafer@1"]
    assert row["object"] == {"kind": "none"}
    assert row["origin"] == "vocabulary"
