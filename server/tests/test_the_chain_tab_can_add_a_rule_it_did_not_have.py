# -*- coding: utf-8 -*-
"""S-204. The chain tab's 「규칙 등록」 can register a rule that is not there yet.

🔴 THE DOOR IS THIS ROUTE, NOT THE EXPLORER (판정 325). 「체인 선언 창은 기존 창에 체인규칙
추가 버튼하고 각 설정들 ui화」 · 「규칙 등록 영역에 규칙을 추가할 수가 없어」 · 「익스플로러
말고 chain 탭에」. So the server half is `GET/POST /admin/chain/rules/raw`.

🔴 AND THE SERVER DOOR WAS ALREADY OPEN — `save_chain_rule_raw` has taken a NEW name since
the day it was written, and its own tests prove it. What it never handed over is 「what are
the cells of a rule」, so a form could only be built by TYPING the cell names beside the
grammar: a second spelling that goes stale the day `routing_keys()` gains one. `skeleton()`
is generated from that same list, so the form reads the grammar instead of copying it.

⚠️ THESE CALL THE ROUTE, NOT THE FUNCTION. `test_chain_rule_editor_arms_without_firing.py`
already scores `save_chain_rule_raw` directly and stays exactly as it is; every defect it
cannot see lives between the route and the function — a payload key read under another
name, a dependency that turns a body into a required query field, a decorator bound to the
wrong callable. None of those show up in a direct call.
"""
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings                                            # noqa: E402
import ledger_admin                                              # noqa: E402
import main                                                      # noqa: E402
from admin_auth import require_admin_token                       # noqa: E402

ROUTE = "/admin/chain/rules/raw"


@pytest.fixture
def rules_file(tmp_path, monkeypatch):
    """A rules file of this test's own. ⛔ NEVER the box's — a test that writes the
    operator's `chain_rules.json` edits what the running worker reads."""
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [
        {"name": "live_one", "trigger_table": "a", "target_table": "b", "enabled": True},
    ]}), encoding="utf-8")
    monkeypatch.setattr(ledger_admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(ledger_admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))
    return path


@pytest.fixture
def client():
    """⚠️ THE REAL ROUTE OBJECTS, mounted alone. The token half is `test_admin_auth.py`'s —
    it parametrises over every gated `/admin/*` route, and a second copy here would be a
    second answer to 「is this route gated」."""
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.add_api_route(ROUTE, main.get_chain_rule_raw, methods=["GET"])
    app.add_api_route(ROUTE, main.post_chain_rule_raw, methods=["POST"])
    return TestClient(app)


def rules_of(path):
    return {r["name"]: r for r in json.loads(path.read_text(encoding="utf-8"))["rules"]}


# ---------------------------------------------------------------------------
# (1) the shape of a rule, so the form does not have to know it
# ---------------------------------------------------------------------------

def test_the_view_hands_over_the_shape_of_one_rule(rules_file, client):
    answer = client.get(ROUTE)
    assert answer.status_code == 200, answer.text
    assert answer.json()["skeleton"] == chain_bindings.skeleton()


def test_the_shape_arrives_when_no_rule_is_named_which_is_when_it_is_needed(rules_file,
                                                                           client):
    """🔴 THE CREATE CALL HAS NO NAME. A skeleton that only rode along beside an EXISTING
    rule would be absent at the one moment a form is being drawn for a new one."""
    without = client.get(ROUTE).json()
    beside = client.get(ROUTE, params={"rule": "live_one"}).json()
    assert without["skeleton"] == beside["skeleton"]
    assert "name" not in without and beside["name"] == "live_one"


def test_the_shape_is_generated_and_not_a_second_spelling(rules_file, client):
    """⛔ THE DEFECT THIS FORBIDS IS A LITERAL. A hand-written field list beside the route
    would agree today and go stale the day `routing_keys()` gains a cell — and it would go
    stale SILENTLY, because nothing compares the two. So the cells are scored against the
    grammar rather than against a list written here."""
    skeleton = client.get(ROUTE).json()["skeleton"]
    assert [f["key"] for f in skeleton["root"]["fields"]] == list(
        chain_bindings.routing_keys())
    required = {f["key"] for f in skeleton["root"]["fields"] if f["required"]}
    assert required == set(chain_bindings.RULE_ROUTING_REQUIRED)


def _code_of(fn):
    """The function's CODE, with its PROSE removed — comments and docstring both.

    ⚠️ STRIPPING THE DOCSTRING IS NOT ENOUGH, measured here: the comment explaining WHY the
    route must not re-spell `routing_keys()` contains the words `routing_keys(`, so the
    oracle read the sentence forbidding the defect as the defect. A note that turns its own
    seat red teaches the next person to delete the note.

    ⚠️ AND `inspect.getdoc` DOES NOT HELP even for the docstring — it dedents, so the
    dedented text never matches the indented source. Tokens are the only reading of 「this
    is a comment」 that agrees with Python's.
    """
    import inspect
    import io
    import tokenize

    source = inspect.getsource(fn)
    kept, previous_end = [], (0, 0)
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            continue
        if token.start[0] != previous_end[0]:
            kept.append("\n")
        kept.append(token.string)
        previous_end = token.end
    body = "".join(kept)
    doc = inspect.getdoc(fn)
    if doc:
        for line in doc.splitlines():
            body = body.replace(line, "")
    return body


def test_the_route_reads_the_skeleton_rather_than_assembling_one():
    """⛔ SCORED ON THE SOURCE. A view that built the field list itself would be the second
    author the skeleton exists to prevent; `test_chain_skeleton.py` counts the skeleton
    against the loader, and that count means nothing if the route ships a different one."""
    body = _code_of(ledger_admin.chain_rule_raw_view)
    assert "chain_bindings.skeleton()" in body
    for rebuilt in ("routing_keys(", "RULE_ROUTING_REQUIRED", "fields"):
        assert rebuilt not in body, ("the view assembles a shape of its own: %s" % rebuilt)


# ---------------------------------------------------------------------------
# (2) registering a name the file did not have - through the route
# ---------------------------------------------------------------------------

def test_a_name_the_file_never_had_is_registered_through_the_route(rules_file, client):
    """🔴 THE ASK, MEASURED WHERE THE SCREEN TOUCHES IT: 「규칙 등록 영역에 규칙을 추가할
    수가 없어」. The function accepted a new name all along; nothing had ever driven the
    ROUTE with one."""
    base = client.get(ROUTE).json()["base"]

    saved = client.post(ROUTE, json={
        "name": "fresh_one", "base": base,
        "declaration": {"trigger_table": "x", "target_table": "y"}})

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["created"] is True
    # 🔴 ARMED, NOT FIRING. A saved rule is re-read on the next SYSTEM_RELOAD and RUNS,
    # so a new one lands switched off and the operator turns it on deliberately.
    assert body["enabled"] is False
    assert rules_of(rules_file)["fresh_one"]["enabled"] is False
    assert rules_of(rules_file)["fresh_one"]["trigger_table"] == "x"
    assert rules_of(rules_file)["live_one"]["trigger_table"] == "a", "a neighbour moved"


def test_the_new_rule_is_listed_and_readable_the_moment_it_is_saved(rules_file, client):
    """⚠️ 「저장됐다」 IS NOT 「보인다」. The picker draws from `rules`, so a name that saved
    but did not appear there would read to an operator as a save that did nothing."""
    base = client.get(ROUTE).json()["base"]
    client.post(ROUTE, json={"name": "fresh_one", "base": base,
                             "declaration": {"trigger_table": "x"}})

    listed = client.get(ROUTE).json()
    assert "fresh_one" in listed["rules"]
    read_back = client.get(ROUTE, params={"rule": "fresh_one"}).json()
    assert read_back["declaration"]["trigger_table"] == "x"
    assert read_back["enabled"] is False


def test_a_second_save_on_the_base_it_already_moved_is_refused(rules_file, client):
    """🔴 THE COMPARE-AND-SWAP, THROUGH THE ROUTE. Two people with the tab open is the
    ordinary case; the second save must not silently overwrite the first. The first save
    MOVES the fingerprint, so re-using the one the screen was opened with is exactly the
    stale write this refuses."""
    base = client.get(ROUTE).json()["base"]
    first = client.post(ROUTE, json={"name": "fresh_one", "base": base,
                                     "declaration": {"trigger_table": "x"}})
    assert first.status_code == 200, first.text

    second = client.post(ROUTE, json={"name": "fresh_one", "base": base,
                                      "declaration": {"trigger_table": "z"}})

    assert second.status_code >= 400, second.text
    assert rules_of(rules_file)["fresh_one"]["trigger_table"] == "x", (
        "the refused save wrote anyway")


def test_the_refusal_names_the_base_rather_than_failing_namelessly(rules_file, client):
    """⚠️ A REFUSAL AN OPERATOR CANNOT ACT ON IS A CRASH WITH BETTER MANNERS. They need to
    know it was the base, so the next move is 「reopen and look」 rather than 「try again」."""
    base = client.get(ROUTE).json()["base"]
    client.post(ROUTE, json={"name": "fresh_one", "base": base,
                             "declaration": {"trigger_table": "x"}})
    refused = client.post(ROUTE, json={"name": "fresh_one", "base": base,
                                       "declaration": {"trigger_table": "z"}})

    detail = json.dumps(refused.json(), ensure_ascii=False)
    assert "stale_base" in detail, detail


def test_saving_again_on_the_base_the_first_save_returned_goes_through(rules_file, client):
    """⚠️ THE OTHER HALF: the lock must not be a wall. The save HANDS BACK the new
    fingerprint, so an editor that stays open can keep working without re-opening."""
    base = client.get(ROUTE).json()["base"]
    first = client.post(ROUTE, json={"name": "fresh_one", "base": base,
                                     "declaration": {"trigger_table": "x"}}).json()

    again = client.post(ROUTE, json={"name": "fresh_one", "base": first["base"],
                                     "declaration": {"trigger_table": "z"}})

    assert again.status_code == 200, again.text
    assert again.json()["created"] is False
    assert rules_of(rules_file)["fresh_one"]["trigger_table"] == "z"
