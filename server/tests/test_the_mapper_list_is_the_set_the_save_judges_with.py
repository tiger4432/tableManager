# -*- coding: utf-8 -*-
"""S-207. The chain tab's mapper choices are the names the save will accept.

🔴 ONE FIELD WAS ANSWERING TWO QUESTIONS. `GET /admin/mappers/list` reads `server/mappers/*.py`
with AST and returns EVERY top-level `def`; what decides whether a rule saves is
`mapper_sdk.MAPPER_REGISTRY`, the names `@mapper(name=…)` handed over. A dropdown filled from
the first offers names the save REFUSES and hides names it would ACCEPT — and neither half
errors, so the operator reads a refusal about a name the screen just recommended.

⚠️ THE OLD FIELDS ARE THE ANSWER TO THE OTHER QUESTION, and they stay exactly as they are.
`admin.js` has two consumers reading the file and function lists, and reading them as 「what
is in these files」 is correct. This adds a field; it does not reinterpret one.

🔴 THE NAMES ARE THE REGISTRY VERBATIM. Filtering or renaming here would be a second spelling
of the set the save judges with, free to drift from it. The API process holds that registry
because S-204 ③ put `discover()` at startup and after every reload.
"""
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                        # noqa: E402
import mapper_sdk                                                  # noqa: E402
from admin.auth import require_admin_token                         # noqa: E402

ROUTE = "/admin/mappers/list"

#: A mapper of this test's own. ⛔ NEVER one of the box's — `server/mappers/` is gitignored,
#: so a case naming a real one would measure this machine rather than the product.
FAKE = "a_mapper_this_test_registered"


@pytest.fixture
def client():
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.add_api_route(ROUTE, main.get_mappers, methods=["GET"])
    return TestClient(app)


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, FAKE, lambda *a, **k: None)
    monkeypatch.setitem(mapper_sdk.MAPPER_PARAMS, FAKE, ())
    return FAKE


# ---------------------------------------------------------------------------
# 🔴 the field is the registry
# ---------------------------------------------------------------------------

def test_the_route_hands_over_the_names_the_save_will_accept(client, registered):
    answer = client.get(ROUTE)

    assert answer.status_code == 200, answer.text
    assert registered in answer.json()["registered"]


def test_the_list_is_the_registry_verbatim_rather_than_a_second_spelling(client,
                                                                        registered):
    """🔴 THE DRIFT GATE. A filtered or renamed copy would be a second answer to 「which
    names may a rule use」, and the one that goes stale is whichever was edited last."""
    assert client.get(ROUTE).json()["registered"] == sorted(mapper_sdk.MAPPER_REGISTRY)


def test_a_name_the_registry_does_not_hold_is_not_offered(client):
    """⛔ THE DEFECT, STATED THE OTHER WAY ROUND. The AST list carries every top-level
    `def` in those files; a name that never registered must not reach the choices."""
    assert FAKE not in client.get(ROUTE).json()["registered"]


def test_the_offered_names_are_exactly_the_ones_the_rule_save_judges_with(client,
                                                                          registered):
    """🔴 SCORED AGAINST THE SAVE ITSELF, not against a literal. `save_chain_rule_raw` asks
    `rule_refusals(..., mapper_resolvable=MAPPER_REGISTRY.get)` (S-204 ③), so a name this
    route offers must be one that seat resolves — and one it withholds must be one that
    seat refuses."""
    import chain_bindings

    offered = client.get(ROUTE).json()["registered"]
    for name in offered:
        issues = chain_bindings.rule_refusals(
            {"name": "r", "trigger_table": "t", "mapper": name}, "rule",
            mapper_resolvable=mapper_sdk.MAPPER_REGISTRY.get)
        assert not issues, ("the list offers %r but the save refuses it" % name)

    refused = chain_bindings.rule_refusals(
        {"name": "r", "trigger_table": "t", "mapper": "never_registered_anywhere"}, "rule",
        mapper_resolvable=mapper_sdk.MAPPER_REGISTRY.get)
    assert refused, "a name outside the registry must still be refused by the save"


# ---------------------------------------------------------------------------
# ⚠️ and the other question keeps its answer
# ---------------------------------------------------------------------------

def test_the_fields_the_two_existing_consumers_read_are_untouched(client, registered):
    """⚠️ `admin.js:962` AND `:3496` read the file and function lists as 「what is in these
    files」, which is a different and correct question. A field was added, not reinterpreted."""
    body = client.get(ROUTE).json()

    assert body["status"] == "success"
    assert isinstance(body["data"], list)
    for entry in body["data"]:
        assert set(entry) == {"filename", "module_name", "functions"}
        for function in entry["functions"]:
            assert set(function) == {"name", "arguments", "summary"}


def test_an_absent_directory_still_says_which_names_are_registered(client, monkeypatch,
                                                                   tmp_path):
    """⚠️ 「THE DIRECTORY IS NOT THERE」 AND 「THIS SERVER IS OLD」 MUST NOT LOOK ALIKE. The
    absence answer keeps its own shape and carries the field too, so a reader never has to
    tell a missing key from a missing directory."""
    import os as _os

    real = _os.path.exists
    monkeypatch.setattr(
        _os.path, "exists",
        lambda path: False if str(path).endswith("mappers") else real(path))

    body = client.get(ROUTE).json()

    assert body["state"] == "absent"
    assert "absent_path" in body
    assert body["registered"] == sorted(mapper_sdk.MAPPER_REGISTRY)


def test_a_reload_moves_the_list_because_it_moves_the_registry(client):
    """🔴 THE SAME WORLD AS THE SAVE (S-204 ③). A reload resets the registry and discovers
    again; this route reads that dictionary at call time rather than a snapshot, so the two
    cannot answer from different revisions."""
    before = client.get(ROUTE).json()["registered"]
    mapper_sdk.register(FAKE, lambda *a, **k: None)
    try:
        assert FAKE in client.get(ROUTE).json()["registered"]
    finally:
        mapper_sdk.MAPPER_REGISTRY.pop(FAKE, None)
        mapper_sdk.MAPPER_PARAMS.pop(FAKE, None)

    assert client.get(ROUTE).json()["registered"] == before
