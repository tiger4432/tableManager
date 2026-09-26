# -*- coding: utf-8 -*-
"""A join whose target is a derived table must build that table's key from its join key.

소유자 2026-09-26 「비즈니스키가 조인키보다는 좁아야함」 · 「파생표가 조인대상」 · 「A만 일단하고 ㄱ」.
Incident: a derived table's key was declared wider than the join key; the join wrote key
columns, every row of the rule failed on the unique key for one reason, and the failed
bundle was halved into hundreds of one-row pieces. Reproduced (d99d329e7): PostgreSQL
refuses the write only when `take` writes a key column; a wider key alone writes fine - and
the owner chose to refuse the wider key on a derived table regardless.

🔴 ONE JUDGE, THREE DOORS. `chain_bindings.rule_refusals` is what the loader, the save gate
and the Declarations report call, so every cell below asks all three and expects one verdict
and one sentence. The sentence is the derived-row key contract's own
(`enrichment.config.key_contract_refusal`), named for the join's key.
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

import config_resolve_report                                      # noqa: E402
import main                                                       # noqa: E402
from admin.auth import require_admin_token                        # noqa: E402
from chain import ingestion_worker as worker                      # noqa: E402
from ledger import admin                                          # noqa: E402

ROUTE = "/admin/chain/rules/raw"
SOURCE, DERIVED, REFERENCE, PLAIN = ("akc_source", "akc_derived", "akc_reference", "akc_plain")
COLUMNS = {"lot": "string", "slot": "string", "extra": "string", "info": "string",
           "slot2": "string"}

DECIDE = {"name": "akc_decide", "enabled": True,
          "on": {"table": SOURCE}, "into": {"table": DERIVED},
          "derive": {"kind": "decide", "decide": {"key": ["lot", "slot"], "fields": ["info"]}}}


def join(into, on, take):
    return {"on": {"table": REFERENCE}, "into": {"table": into},
            "derive": {"kind": "join", "join": {
                "on": [{"left": column, "right": column} for column in on], "take": take}}}


INFO = [{"from": "info", "into": "info"}]
#: (cell, declaration, stands) - the target key is [lot, slot] on both targets
CELLS = [
    ("key inside the join key", join(DERIVED, ["lot", "slot", "extra"], INFO), True),
    ("key equal to the join key", join(DERIVED, ["lot", "slot"], INFO), True),
    ("key wider, take into a non-key column", join(DERIVED, ["lot"], INFO), False),
    ("key wider, take into a key column (the incident)",
     join(DERIVED, ["lot"], [{"from": "slot2", "into": "slot"}]), False),
    ("key wider, target is not a derived table (lookup join)", join(PLAIN, ["lot"], INFO), True),
]


@pytest.fixture(name="catalogue", autouse=True)
def fixture_catalogue(monkeypatch):
    from database import crud

    monkeypatch.setitem(crud.TABLE_CONFIG, SOURCE, {
        "business_key": "lot", "column_types": dict(COLUMNS)})
    monkeypatch.setitem(crud.TABLE_CONFIG, DERIVED, {
        "business_key": "d_key", "composite_key_source": ["lot", "slot"],
        "column_types": dict(COLUMNS)})
    monkeypatch.setitem(crud.TABLE_CONFIG, PLAIN, {
        "business_key": "p_key", "composite_key_source": ["lot", "slot"],
        "column_types": dict(COLUMNS)})
    monkeypatch.setitem(crud.TABLE_CONFIG, REFERENCE, {
        "business_key": "lot", "column_types": dict(COLUMNS)})


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch):
    """⛔ NEVER the box's file - the running worker reads it."""
    path = tmp_path / "chain_rules.json"
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


def _write(path, *declarations):
    path.write_text(json.dumps({"rules": list(declarations)}), encoding="utf-8")


@pytest.mark.parametrize("cell,declaration,stands", CELLS, ids=[c[0] for c in CELLS])
def test_the_loader_the_save_and_the_report_give_one_verdict(
        cell, declaration, stands, client, rules_file, monkeypatch):
    name = "akc_join"

    # the save gate - the decide declaration is already in the file
    _write(rules_file, DECIDE)
    base = client.get(ROUTE).json()["base"]
    saved = client.post(ROUTE, json={"name": name, "base": base,
                                     "declaration": dict(declaration, enabled=True)})

    # the loader and the report read the file with both declarations in it
    _write(rules_file, DECIDE, dict(declaration, name=name, enabled=True))
    logged = []
    monkeypatch.setattr(worker.logger, "error",
                        lambda msg, *args, **kw: logged.append(msg % args if args else msg))
    loaded = {rule.get("name") for rule in worker.load_chain_rules()}
    chain = config_resolve_report._resolve_chain()
    rejected = [e for e in chain["rejected"] if e["subject"] == name]
    effective = [e for e in chain["effective"] if e["subject"] == name]

    assert "enrichment_dedup:akc_decide" in loaded, "the derived-row rule itself stands"
    if stands:
        assert saved.status_code == 200, saved.text
        assert name in loaded
        assert effective and not rejected
        return
    assert saved.status_code == 400, saved.text
    detail = saved.json()["detail"]
    assert detail["code"] == "join_key_contract"
    assert name not in loaded
    assert rejected and not effective
    issue = rejected[0]["fields"]["issues"][0]
    assert issue["code"] == "join_key_contract"
    # one sentence at every door - the derived-row contract's, named for the join key
    assert issue["message"].startswith("derived table composite_key_source must be a subset of ")
    assert issue["message"] in detail["message"]
    assert any(issue["message"] in line for line in logged), logged
