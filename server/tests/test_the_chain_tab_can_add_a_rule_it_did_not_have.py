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

#: 🔴 WHAT MAKES A RULE RUNNABLE (판정 326). The save now asks `rule_refusals` before
#: writing, and a rule naming no mapper is one the boot loader drops — so a case about
#: 「registering a name」 has to register a rule that would actually run, or it is measuring
#: the refusal instead of the registration.
RUNNABLE = {"mapper_module": "m", "mapper_function": "f"}


@pytest.fixture
def rules_file(tmp_path, monkeypatch):
    """A rules file of this test's own. ⛔ NEVER the box's — a test that writes the
    operator's `chain_rules.json` edits what the running worker reads."""
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [
        {"name": "live_one", "trigger_table": "a", "target_table": "b",
         "mapper_module": "m", "mapper_function": "f", "enabled": True},
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
        "declaration": {"trigger_table": "x", "target_table": "y", **RUNNABLE}})

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
                             "declaration": {"trigger_table": "x", **RUNNABLE}})

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
                                     "declaration": {"trigger_table": "x", **RUNNABLE}})
    assert first.status_code == 200, first.text

    second = client.post(ROUTE, json={"name": "fresh_one", "base": base,
                                      "declaration": {"trigger_table": "z", **RUNNABLE}})

    assert second.status_code >= 400, second.text
    assert rules_of(rules_file)["fresh_one"]["trigger_table"] == "x", (
        "the refused save wrote anyway")


def test_the_refusal_names_the_base_rather_than_failing_namelessly(rules_file, client):
    """⚠️ A REFUSAL AN OPERATOR CANNOT ACT ON IS A CRASH WITH BETTER MANNERS. They need to
    know it was the base, so the next move is 「reopen and look」 rather than 「try again」."""
    base = client.get(ROUTE).json()["base"]
    client.post(ROUTE, json={"name": "fresh_one", "base": base,
                             "declaration": {"trigger_table": "x", **RUNNABLE}})
    refused = client.post(ROUTE, json={"name": "fresh_one", "base": base,
                                       "declaration": {"trigger_table": "z", **RUNNABLE}})

    detail = json.dumps(refused.json(), ensure_ascii=False)
    assert "stale_base" in detail, detail


def test_saving_again_on_the_base_the_first_save_returned_goes_through(rules_file, client):
    """⚠️ THE OTHER HALF: the lock must not be a wall. The save HANDS BACK the new
    fingerprint, so an editor that stays open can keep working without re-opening."""
    base = client.get(ROUTE).json()["base"]
    first = client.post(ROUTE, json={"name": "fresh_one", "base": base,
                                     "declaration": {"trigger_table": "x", **RUNNABLE}}).json()

    again = client.post(ROUTE, json={"name": "fresh_one", "base": first["base"],
                                     "declaration": {"trigger_table": "z", **RUNNABLE}})

    assert again.status_code == 200, again.text
    assert again.json()["created"] is False
    assert rules_of(rules_file)["fresh_one"]["trigger_table"] == "z"


# ---------------------------------------------------------------------------
# (3) the loader's own judgement, before the write (판정 326)
# ---------------------------------------------------------------------------
#: 🔴 A MAPPER OF THIS TEST'S OWN. The box's mappers live in a gitignored directory, so a
#: case naming one of them would be measuring this box rather than the product -- and the
#: same test would refuse on a machine whose `mappers/` holds something else.
FAKE_MAPPER = "a_mapper_this_test_registered"


@pytest.fixture
def registered_mapper(monkeypatch):
    import mapper_sdk

    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, FAKE_MAPPER, lambda *a, **k: None)
    monkeypatch.setitem(mapper_sdk.MAPPER_PARAMS, FAKE_MAPPER, ())
    return FAKE_MAPPER


def test_a_rule_naming_a_registered_mapper_saves(rules_file, client, registered_mapper):
    """⚠️ THE HALF THAT MUST NOT REGRESS. The judge only earns its seat if it lets through
    what the loader would run; a gate that refuses everything is not strict, it is broken."""
    base = client.get(ROUTE).json()["base"]

    saved = client.post(ROUTE, json={
        "name": "one_cell", "base": base,
        "declaration": {"trigger_table": "x", "mapper": registered_mapper}})

    assert saved.status_code == 200, saved.text
    assert rules_of(rules_file)["one_cell"]["mapper"] == registered_mapper


def test_a_rule_naming_a_mapper_nothing_implements_is_refused_by_name(rules_file, client):
    """🔴 THE SAVE THAT USED TO SUCCEED AND DO NOTHING. The boot loader drops such a rule,
    so the operator got it back from this editor every time and never saw it run -- the
    screen blinder than the log, which 판정 315 exists to forbid."""
    base = client.get(ROUTE).json()["base"]

    refused = client.post(ROUTE, json={
        "name": "ghost_mapper", "base": base,
        "declaration": {"trigger_table": "x", "mapper": "nothing_implements_this"}})

    assert refused.status_code >= 400, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "unresolvable_mapper", detail
    assert "ghost_mapper" not in rules_of(rules_file), "the refused rule was written anyway"


def test_the_module_and_function_form_still_saves_with_an_empty_registry(rules_file,
                                                                        client):
    """⚠️ NO REGRESSION FOR THE OLDER SPELLING. `rule_refusals` refuses only when the rule
    names neither a registered mapper NOR both of `mapper_module`/`mapper_function`, so a
    rule written the old way is judged without the registry being consulted at all."""
    base = client.get(ROUTE).json()["base"]

    saved = client.post(ROUTE, json={
        "name": "old_form", "base": base,
        "declaration": {"trigger_table": "x", "mapper_module": "m",
                        "mapper_function": "f"}})

    assert saved.status_code == 200, saved.text
    assert rules_of(rules_file)["old_form"]["mapper_module"] == "m"


def test_a_rule_missing_a_required_cell_is_refused_where_the_loader_refuses(rules_file,
                                                                           client,
                                                                           registered_mapper):
    """⚠️ THE GRAMMAR HALF, not only the mapper half. `trigger_table` is one of the two
    cells the loader requires, and a rule without it is dropped at boot."""
    base = client.get(ROUTE).json()["base"]

    refused = client.post(ROUTE, json={
        "name": "no_trigger", "base": base,
        "declaration": {"mapper": registered_mapper}})

    assert refused.status_code >= 400, refused.text
    assert "no_trigger" not in rules_of(rules_file)


def test_the_save_asks_the_one_judge_rather_than_re_typing_the_grammar():
    """⛔ SCORED ON THE SOURCE, because the defect would be a REIMPLEMENTATION that agrees
    today. The boot loader and `config_resolve_report` already call `rule_refusals`; a
    third spelling here is exactly the drift that let the old preview accept what the
    loader dropped."""
    body = _code_of(ledger_admin.save_chain_rule_raw)
    assert "rule_refusals(" in body
    for retyped in ("problems.exact(", "RULE_ROUTING_REQUIRED", "mapper_module\" in",
                    "unresolvable_mapper\""):
        assert retyped not in body, ("the save re-types the grammar: %s" % retyped)


def test_the_grammar_judge_has_exactly_one_spelling_across_the_product():
    """🔴 THE DRIFT GATE (판정 326). Three seats ask 「can this rule run」 -- the boot loader,
    the resolve report and now this save -- and all three must ask the same function, or
    the one that drifts is whichever was edited last."""
    import subprocess

    server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out = subprocess.run(
        ["git", "grep", "-l", "rule_refusals(", "--", ".", ":!tests"],
        cwd=server_dir, capture_output=True, text=True)
    callers = {line for line in out.stdout.split("\n") if line.strip()}
    assert out.returncode in (0, 1), out.stderr
    # The definition plus its callers - and no file that builds a verdict of its own.
    assert "chain_bindings.py" in " ".join(callers), callers
    for caller in ("chain_ingestion_worker.py", "config_resolve_report.py",
                   "ledger_admin.py"):
        assert any(caller in line for line in callers), (caller, callers)


# ---------------------------------------------------------------------------
# 🔴 the judge's registry must be as fresh as the file it judges (판정 326 (2))
# ---------------------------------------------------------------------------

def test_a_reload_leaves_the_registry_populated_rather_than_emptied():
    """🔴 THE HALF-RELOAD THIS CLOSES. `reload_local_process_cache` evicts `mappers.*` from
    `sys.modules` and resets the registry (S-188 ⓒ) — and then, until now, stopped. The
    chain worker does the same two things AND re-runs `discover()` in its warmup, so its
    registry is as fresh as the files; this process's was empty from the first
    SYSTEM_RELOAD onward.

    🔴 THE ORDER IS THE ASSERTION, not the call. Discovering and THEN resetting is the same
    two lines in the other sequence and leaves the registry empty — a judge that refuses
    every rule written in the one-cell form, which is the failure this round exists to
    avoid. Measured: removing the discover call reds nothing without this test.

    ⚠️ SCORED BY THE CALLS, NOT BY A COUNT. The box's `mappers/` is gitignored, so asserting
    a number here would measure this machine rather than the product.
    """
    import mapper_sdk
    import system_reload

    order = []
    real_reset, real_discover = mapper_sdk.reset_registry, mapper_sdk.discover
    mapper_sdk.reset_registry = lambda: order.append("reset")
    mapper_sdk.discover = lambda *a, **k: (order.append("discover"), ((), {}))[1]
    try:
        system_reload.reload_local_process_cache()
    finally:
        mapper_sdk.reset_registry, mapper_sdk.discover = real_reset, real_discover

    assert order == ["reset", "discover"], (
        "the reload must forget the evicted modules and then find them again, in that order")
