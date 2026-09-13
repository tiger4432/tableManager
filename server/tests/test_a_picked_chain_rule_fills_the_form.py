# -*- coding: utf-8 -*-
"""S-212. A rule picked in the chain tab fills the form, because one word has one spelling.

🔴 THE SEAM WAS ONE WORD IN TWO SPELLINGS. The screen asks `GET
/admin/chain/rules/raw?name=<rule>` (`client2/src/admin.js:1120`, and the panel's own
`nameKey: 'name'`); the route declared `rule`, so FastAPI dropped a query it did not know,
`chain_rule_raw_view(None)` answered without a `declaration`, and the form was ALWAYS
empty. Nothing threw and nothing logged - the two ends were asking and answering different
questions.

🔴 WHY S-204'S ROUTE CASES DID NOT SEE IT: they do drive the route, but they drive it with
the SERVER's spelling (`params={"rule": ...}`). A case that types the same word the handler
types cannot find a seam - the only reading that decides it is the one the CLIENT puts on
the wire. So these spell the query the way `admin.js` spells it, and nothing else.

⚠️ AND THEY MOUNT THE ROUTE THE DECORATOR REGISTERED, lifted out of `main.app`, rather than
re-mounting the function under the path by hand: a decorator bound to the wrong callable is
a defect of this same class, and a hand mount would quietly answer for it.
"""
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_admin                                              # noqa: E402
import main                                                      # noqa: E402
from admin_auth import require_admin_token                       # noqa: E402

ROUTE = "/admin/chain/rules/raw"

#: 🔴 THE WORD THE SCREEN PUTS ON THE WIRE. `admin.js` builds `?name=<rule>` and the panel
#: spec that reads the answer is `nameKey: 'name'`; this constant is the client half of the
#: seam, so a rename on either end has to move it.
CLIENT_QUERY_KEY = "name"


@pytest.fixture
def rules_file(tmp_path, monkeypatch):
    """⛔ NEVER THE BOX'S `chain_rules.json` - the running worker reads that file."""
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [
        {"name": "live_one", "trigger_table": "a", "target_table": "b",
         "mapper_module": "m", "mapper_function": "f", "enabled": True},
        {"name": "other_one", "trigger_table": "c", "target_table": "d",
         "mapper_module": "m", "mapper_function": "g", "enabled": False},
    ]}), encoding="utf-8")
    monkeypatch.setattr(ledger_admin, "chain_rules_path", lambda: str(path))
    return path


@pytest.fixture
def client(monkeypatch):
    """The registered route object, mounted alone.

    ⚠️ THE OVERRIDE GOES ON THE PRODUCT APP, not on the bare one: a route built by
    `@app.get` carries `main.app` as its overrides provider, so an override set anywhere
    else is never consulted.
    """
    registered = [route for route in main.app.routes
                  if getattr(route, "path", None) == ROUTE
                  and "GET" in (getattr(route, "methods", None) or ())]
    assert len(registered) == 1, registered

    app = FastAPI()
    app.router.routes.extend(registered)
    monkeypatch.setitem(main.app.dependency_overrides, require_admin_token, lambda: None)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 🔴 the round: the query the screen sends fills the form
# ---------------------------------------------------------------------------

def test_the_query_the_screen_sends_fills_the_declaration(rules_file, client):
    """🔴 THE ASK: 「규칙 로딩하면 칸 채워져야지」."""
    answer = client.get(ROUTE, params={CLIENT_QUERY_KEY: "live_one"})

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["name"] == "live_one"
    assert body["declaration"]["trigger_table"] == "a"
    assert json.loads(body["raw"])["mapper_function"] == "f"
    assert body["enabled"] is True


def test_it_answers_about_the_rule_that_was_asked_for(rules_file, client):
    """⚠️ 「채워진다」 IS NOT 「그 규칙이 채워진다」. A query read at all but read into the
    wrong seat would fill the form with a neighbour, and that is worse than empty."""
    body = client.get(ROUTE, params={CLIENT_QUERY_KEY: "other_one"}).json()

    assert body["name"] == "other_one"
    assert body["declaration"]["trigger_table"] == "c"
    assert body["enabled"] is False


def test_no_name_answers_with_the_list_and_no_declaration(rules_file, client):
    """⚠️ THE OTHER STATE THE SCREEN DRIVES. The picker's first draw asks with no name, and
    the key has to be ABSENT rather than null - 「not asked」 and 「asked, no such rule」 are
    different answers to a form."""
    answer = client.get(ROUTE)

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["rules"] == ["live_one", "other_one"]
    assert "declaration" not in body and "name" not in body


def test_the_old_spelling_is_gone_rather_than_joined_by_a_second_one(rules_file, client):
    """⛔ ONE WORD, ONE SPELLING. Accepting `?rule=` as well would leave two ways to ask the
    same question, and two ways is where the two drift apart - the route would keep
    answering while the screen and the handler disagreed about which one is the contract."""
    body = client.get(ROUTE, params={"rule": "live_one"}).json()

    assert "declaration" not in body, "a second query key still fills the form"
