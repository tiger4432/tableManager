# -*- coding: utf-8 -*-
"""총괄 b30fbd38c ㄱ — 바인딩을 column 에서 constant 로 바꾸면 raw 에 "column": "" 이 남아 저장 검증에서
걸렸다(소유자). 스켈레톤이 칸마다 든 `when` 으로, 지금 고른 것에 해당 안 하는 칸을 저장과 저장 없는
계획이 «같은 함수»(config_authoring.filled_declaration)에서 걷고, 걷은 칸을 `dropped_fields` 로 돌려준다.
표본(추적되는 선언)의 wafer_process_recipe · step 역할로 잰다.
"""
import copy
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.auth import require_admin_token, require_admin_token_strict
from ledger.config_explorer_service import OntologyExplorerService
from ledger.setup import load_setup
from ledger.setup_bundle import load_physical_catalog
from ledger_api import ontology_config_explorer_router as explorer_router

SHIPPED = Path(__file__).resolve().parent.parent / "config" / "sample"
SOURCE, SENTENCE = "wafer_process_recipe", "wafer-processed-with-recipe"
DRAFTS, PLAN = "/admin/ontology-explorer/drafts", "/admin/ontology-explorer/authoring/plan"
ROLE = "bundle.sources.%s.bind.mappings.%s.bind.step" % (SOURCE, SENTENCE)
SAMPLE = json.loads((SHIPPED / "ledger_config.json.sample").read_text(encoding="utf-8"))
TARGET = SAMPLE["sources"][SOURCE]["bind"]["mappings"][SENTENCE]["bind"]["target"]

SWITCHES = {
    "column_to_constant": ({"kind": "constant", "value": "S1", "column": ""},
                           [("column", "")]),
    "constant_to_column": ({"kind": "column", "column": "step", "value": "S1"},
                           [("value", "S1")]),
    "entity_to_column": ({"kind": "column", "column": "step", "attributes": {},
                          "entity_type": TARGET["entity_type"], "keys": TARGET["keys"]},
                         [("attributes", {}), ("entity_type", TARGET["entity_type"]),
                          ("keys", TARGET["keys"])]),
}


@pytest.fixture(name="client")
def fixture_client(tmp_path):
    root = tmp_path / "ontology"
    root.mkdir()
    (root / "ledger_config.json").write_bytes(
        (SHIPPED / "ledger_config.json.sample").read_bytes())
    catalog = load_physical_catalog(SHIPPED / "table_config.json.sample")
    service = OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts",
        setup_loader=lambda r: load_setup(r, catalog=catalog), catalog_loader=lambda: catalog,
        convergence_probe=lambda expected: {"ontology-explorer-api": expected,
                                            "ledger-persistent-reader": expected})
    explorer_router.configure_service(service)
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[require_admin_token_strict] = lambda: None
    app.include_router(explorer_router.router)
    http = TestClient(app)
    _, index, _ = service.active()
    draft = http.post(DRAFTS, json={"target_key": "source_plan|" + SOURCE,
                                    "base_snapshot_hash": index.snapshot_hash}).json()
    return http, draft


def _with_step(draft, binding):
    raw = copy.deepcopy(draft["raw"])
    raw["bind"]["mappings"][SENTENCE]["bind"]["step"] = binding
    return raw


@pytest.mark.parametrize("switch", list(SWITCHES))
def test_a_switch_saves_with_the_switched_off_fields_dropped_and_named(client, switch):
    http, draft = client
    binding, gone = SWITCHES[switch]
    raw = _with_step(draft, binding)
    expected_raw = _with_step(draft, {k: v for k, v in binding.items()
                                      if k not in {key for key, _ in gone}})
    expected_dropped = [{"path": "%s.%s" % (ROLE, key), "value": value} for key, value in gone]

    plan = http.post(PLAN, json={"selection": "source_plan|" + SOURCE,
                                 "draft_id": draft["draft_id"], "raw": json.dumps(raw)})
    saved = http.put("%s/%s" % (DRAFTS, draft["draft_id"]),
                     json={"expected_revision": 0, "raw": json.dumps(raw)})

    assert plan.status_code == 200 and saved.status_code == 200, (plan.text, saved.text)
    assert saved.json()["lifecycle_status"] == "saved", saved.json()["validation_errors"]
    assert saved.json()["dropped_fields"] == expected_dropped
    assert plan.json()["dropped_fields"] == expected_dropped
    assert saved.json()["raw"] == expected_raw          # nothing else moved


def test_a_binding_that_has_not_chosen_keeps_what_it_holds(client):
    """No `kind` yet: nothing is switched off - the save refuses by name, nothing is dropped."""
    http, draft = client
    raw = _with_step(draft, {"column": "step", "value": "S1"})
    saved = http.put("%s/%s" % (DRAFTS, draft["draft_id"]),
                     json={"expected_revision": 0, "raw": json.dumps(raw)}).json()

    assert saved["dropped_fields"] == []
    assert saved["raw"] == raw
    assert saved["lifecycle_status"] == "invalid" and saved["validation_errors"]
