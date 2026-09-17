# -*- coding: utf-8 -*-
"""S-244. 저장 관문과 로더가 «같은 입력»을 본다 — 같은 판정자였는데 다른 것을 먹고 있었다.

🔴 THE JUDGE WAS ALREADY SHARED; ITS INPUT WAS NOT. `save_chain_rule_raw` scored the RAW
entry while the loader translated first, so a unified declaration (`name·on·derive·into`)
was refused at the save button - no `trigger_table`, unknown `derive`/`on`/`into`,
`unresolvable_mapper` - and accepted from the same file at boot. S-204's sentence 「저장
관문과 로더가 같은 판정자」 stayed true of the judge and had gone false about what it judged,
which is the 「같은 기능에 두 경로」 defect one level down.

🔴 AND THE RESOLVER WAS HALF. `MAPPER_REGISTRY.get` does not know the `builtin:` kinds, so a
translated rule naming `builtin:join_into` was refused here while running there.

⚠️ WHAT IS SAVED IS THE OPERATOR'S TEXT. The translation is what gets JUDGED; the file keeps
the declaration as written, because the document belongs to whoever has to read it next.
"""
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import main                                                       # noqa: E402
from admin.auth import require_admin_token                        # noqa: E402
from chain import ingestion_worker as worker                      # noqa: E402
from chain import rule_shape                                      # noqa: E402
from ledger import admin                                          # noqa: E402

ROUTE = "/admin/chain/rules/raw"
LEFT = "s244_left"
RIGHT = "s244_right"

JOIN_DECLARATION = {
    "on": {"table": LEFT},
    "into": {"table": LEFT},
    "derive": {"kind": "join",
               "join": {"right_table": RIGHT,
                        "on": [{"left": "job", "right": "job"}],
                        "take": [{"from": "lot", "into": "lot_confirmed"}]}},
}

DECIDE_DECLARATION = {
    "on": {"table": LEFT},
    "into": {"table": RIGHT},
    "derive": {"kind": "decide",
               "decide": {"key": ["job"], "fields": ["lot"], "auto_confirm": True}},
}


@pytest.fixture(name="catalogue", autouse=True)
def fixture_catalogue(monkeypatch):
    from database import crud

    monkeypatch.setitem(crud.TABLE_CONFIG, LEFT, {
        "business_key": "job",
        "column_types": {"job": "string", "lot": "string", "lot_confirmed": "string"}})
    monkeypatch.setitem(crud.TABLE_CONFIG, RIGHT, {
        "business_key": "job", "column_types": {"job": "string", "lot": "string"}})


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch):
    """⛔ NEVER the box's file — a test that writes the operator's `chain_rules.json` edits
    what the running worker reads."""
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    return path


@pytest.fixture(name="client")
def fixture_client():
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.add_api_route(ROUTE, main.get_chain_rule_raw, methods=["GET"])
    app.add_api_route(ROUTE, main.post_chain_rule_raw, methods=["POST"])
    return TestClient(app)


@pytest.fixture(name="no_synthesis", autouse=True)
def fixture_no_synthesis(monkeypatch):
    from chain import builtins as chain_builtins

    monkeypatch.setattr(chain_builtins, "synthesize_chain_rules", lambda **kwargs: [])


def _save(client, path, name, declaration):
    base = client.get(ROUTE).json()["base"]
    return client.post(ROUTE, json={"name": name, "base": base,
                                    "declaration": dict(declaration, enabled=True)})


def _saved(path):
    return {r["name"]: r for r in json.loads(path.read_text(encoding="utf-8"))["rules"]}


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the route accepts what the loader accepts (gate ①)
# ---------------------------------------------------------------------------

def test_a_unified_join_declaration_can_be_saved_and_then_stands_two_rules(client,
                                                                           rules_file):
    """🔴 THE ROUTE IS CALLED, not a signature inspected. 「the gate would accept it」 is the
    claim that was false before, and only a real POST can say otherwise."""
    answer = _save(client, rules_file, "s244_join", JOIN_DECLARATION)

    assert answer.status_code == 200, answer.text
    # ⚰️ THE ORDER FLIPPED WITH S-278 AND THAT IS THE POINT OF THE ORDERING WALK. Both
    # halves are on the trigger path now (the owner's 2026-09-16 ruling), so the reference
    # rule - which WRITES the table the target rule triggers on - is ordered first,
    # producer before consumer. While it stood `follow_up` the walk skipped it and the two
    # kept file order. This asserts the SET by name either way; the order is the walk's.
    assert sorted(r.get("name") for r in worker.load_chain_rules()) == sorted([
        "s244_join", "s244_join" + rule_shape.REFERENCE_SUFFIX])


def test_a_unified_decide_declaration_can_be_saved_too(client, rules_file):
    answer = _save(client, rules_file, "s244_decide", DECIDE_DECLARATION)

    assert answer.status_code == 200, answer.text
    assert sorted(r.get("name") for r in worker.load_chain_rules()) == [
        "enrichment_auto_confirm:s244_decide", "enrichment_dedup:s244_decide"]


def test_a_new_declaration_saves_armed_but_not_firing(client, rules_file):
    """🔴 「A NEW RULE IS SAVED ARMED BUT NOT FIRING」 MEETS THE NEW GRAMMAR, and the two
    could have collided: this route stamps `enabled: false` on a name it has not seen, and a
    disabled declaration stands NO rule (판정 399). If 「stands nothing」 were reported as a
    REFUSAL, every first save of a unified declaration would be rejected - the operator could
    never write one through the editor at all.

    ⚠️ 「OFF」 IS NOT 「WRONG」. That distinction has no other witness in this file, and a
    mutation found it: turning the OFF outcome into a refusal left every case green."""
    base = client.get(ROUTE).json()["base"]
    answer = client.post(ROUTE, json={"name": "s244_new", "base": base,
                                      "declaration": dict(JOIN_DECLARATION)})

    assert answer.status_code == 200, answer.text
    assert _saved(rules_file)["s244_new"]["enabled"] is False
    assert [r.get("name") for r in worker.load_chain_rules()] == [], (
        "a declaration saved OFF stands no rule"
    )


def test_the_file_keeps_the_declaration_the_operator_wrote(client, rules_file):
    """⚠️ THE TRANSLATION IS JUDGED, THE TEXT IS SAVED. Writing the expansion back would hand
    the operator two rules they did not write, in a grammar they did not choose - and the
    next edit would be of the product's prose rather than their own."""
    _save(client, rules_file, "s244_join", JOIN_DECLARATION)

    entry = _saved(rules_file)["s244_join"]
    assert entry["derive"] == JOIN_DECLARATION["derive"]
    assert "mapper" not in entry and "trigger_table" not in entry
    assert set(entry) == {"name", "enabled", "on", "into", "derive"}


# ---------------------------------------------------------------------------
# 🔴 ⓑ — the two doors give the same answer (gate ②)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("declaration,name", [
    (JOIN_DECLARATION, "s244_join"),
    (DECIDE_DECLARATION, "s244_decide"),
])
def test_both_doors_accept_the_same_declaration(client, rules_file, declaration, name):
    """🔴 SAME INPUT, TWO DOORS, ONE ANSWER. The comparison is what the round is about: a
    declaration that loads from the file must save through the route, and vice versa."""
    through_route = _save(client, rules_file, name, declaration)
    by_hand, refusal, _notes = rule_shape.expand_declaration(
        dict(declaration, name=name, enabled=True), None)

    assert through_route.status_code == 200 and refusal is None
    assert len(by_hand) == 2


def test_a_declaration_both_doors_refuse_gives_the_same_sentence(client, rules_file):
    """⛔ AND THE REFUSAL TRAVELS TOO. A save that refuses for a different reason than the
    loader would is the same defect wearing the opposite sign - the operator fixes the wrong
    thing and the rule still never runs."""
    conflicting = dict(JOIN_DECLARATION,
                       on={"table": LEFT, "columns": ["lot"]})

    answer = _save(client, rules_file, "s244_conflict", conflicting)
    _rules, refusal, _notes = rule_shape.expand_declaration(
        dict(conflicting, name="s244_conflict", enabled=True), None)

    assert answer.status_code >= 400
    assert refusal and "join_trigger_conflict" in refusal
    assert "join_trigger_conflict" in answer.text
    assert "s244_conflict" not in _saved(rules_file), "a refused save wrote nothing"


def test_a_builtin_kind_is_runnable_at_the_save_gate_too():
    """🔴 THE RESOLVER WAS HALF. `MAPPER_REGISTRY.get` alone answers 「not registered」 for
    every `builtin:` kind, which refused at the save button what runs at boot."""
    import mapper_sdk
    from chain import join_into

    assert worker._resolvable_mapper(join_into.JOIN_INTO_MAPPER) is not None
    assert worker._resolvable_mapper("builtin:nothing_claims_this") is None
    # ⚰️ [판정 562] THE KIND TABLE IS GONE; the save gate and the loader read the one
    #   registry, so that is what 「runnable」 is asked of.
    assert join_into.JOIN_INTO_MAPPER in mapper_sdk.MAPPER_REGISTRY


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the old grammar's save path is byte for byte what it was (gate ③)
# ---------------------------------------------------------------------------

def test_a_flat_rule_comes_back_from_the_expander_untouched():
    """⚠️ NO `derive`, NO TRANSLATION. That is the whole of 「옛 경로 무변」: the expander hands
    the entry back as the one rule it stands, so every judgement after it sees exactly what it
    saw before this round."""
    flat = {"name": "old_one", "trigger_table": "a", "target_table": "b",
            "mapper_module": "m", "mapper_function": "f"}

    stood, refusal, notes = rule_shape.expand_declaration(flat, None)

    assert stood == [flat] and stood[0] is flat
    assert refusal is None and notes == []


def test_a_flat_rule_still_saves_through_the_route(client, rules_file):
    answer = _save(client, rules_file, "old_one", {
        "trigger_table": "a", "target_table": "b",
        "mapper_module": "m", "mapper_function": "f"})

    assert answer.status_code == 200, answer.text
    assert _saved(rules_file)["old_one"]["mapper_module"] == "m"
