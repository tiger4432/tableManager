# -*- coding: utf-8 -*-
"""총괄 b30fbd38c ㄱ — 바인딩을 column 에서 constant 로 바꾸면 raw 에 "column": "" 이 남아 저장 검증에서
걸렸다(소유자). 스켈레톤이 칸마다 든 `when` 으로, 지금 고른 것에 해당 안 하는 칸을 저장과 저장 없는
계획이 «같은 함수»(config_authoring.filled_declaration)에서 걷고, 걷은 칸을 `dropped_fields` 로 돌려준다.
표본(추적되는 선언)의 wafer_process_recipe · step 역할로 잰다.
"""
import copy
import json
from collections.abc import Mapping
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
VIEW = "/admin/ontology-explorer/view"
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


CATALOG = load_physical_catalog(SHIPPED / "table_config.json.sample")


@pytest.fixture(name="client")
def fixture_client(tmp_path):
    return _client(tmp_path, (SHIPPED / "ledger_config.json.sample").read_bytes(), CATALOG)


def _client(tmp_path, config_bytes, loader_catalog):
    """The explorer over `config_bytes`; the setup compiles with the sample's catalog and the
    service's catalog loader answers `loader_catalog`."""
    root = tmp_path / "ontology"
    root.mkdir()
    (root / "ledger_config.json").write_bytes(config_bytes)
    service = OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts",
        setup_loader=lambda r: load_setup(r, catalog=CATALOG),
        catalog_loader=lambda: loader_catalog,
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


def _plain(value):
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


_BROKEN_OTHER = copy.deepcopy(SAMPLE)
# A LIVE neighbour breaks: a retired one (lot_event, setup_version 6) is not read, so its
# content is not judged and it would not be left out.
_BROKEN_OTHER["sources"]["transfer_event"]["read"]["table"] = "no_such_table"
APART = {
    # the file holds a declaration the active setup left out
    "a_declaration_left_out": (_BROKEN_OTHER, CATALOG,
                               lambda document, catalog: "transfer_event" not in document["sources"]),
    # the catalog loader answers what the setup did not compile with
    "a_catalog_changed_since": (SAMPLE, {**CATALOG, "added_since": CATALOG["lot_event"]},
                                lambda document, catalog: "added_since" not in catalog),
}


@pytest.mark.parametrize("apart", list(APART))
def test_the_unsaved_plan_fills_from_what_the_save_fills_from(tmp_path, monkeypatch, apart):
    """총괄 d4a949a8c ⑦ — 저장 없는 계획은 작성 파일 + 카탈로그 로더로, 저장은 활성 셋업 + 그 카탈로그로
    채웠다. 둘이 다를 때 「저장처럼 채운다」가 거짓. 두 호출이 filled_declaration 에 넘기는 넷이 같다."""
    from ledger import config_authoring

    document, loader_catalog, save_side_differs = APART[apart]
    http, draft = _client(tmp_path, json.dumps(document).encode("utf-8"), loader_catalog)
    fills, real = [], config_authoring.filled_declaration

    def recording(bundle, catalog, bundle_path, raw):
        fills.append(_plain((bundle, catalog, bundle_path, raw)))
        return real(bundle, catalog, bundle_path, raw)

    monkeypatch.setattr(config_authoring, "filled_declaration", recording)
    raw = json.dumps(draft["raw"])
    plan = http.post(PLAN, json={"selection": "source_plan|" + SOURCE,
                                 "draft_id": draft["draft_id"], "raw": raw})
    saved = http.put("%s/%s" % (DRAFTS, draft["draft_id"]),
                     json={"expected_revision": 0, "raw": raw})

    assert plan.status_code == 200 and saved.status_code == 200, (plan.text, saved.text)
    assert len(fills) == 2
    assert save_side_differs(*fills[1][:2])          # the box sets the two inputs apart
    assert fills[0] == fills[1]


def test_a_plan_without_a_draft_id_is_refused_as_the_draft_preview_refuses_it(client):
    """총괄 d4a949a8c ⑨ — draft_id 없는 POST 가 "" 로 draft_store.get("") 을 불러 invalid_draft_id 였다."""
    http, _draft = client
    plan = http.post(PLAN, json={"selection": "source_plan|" + SOURCE, "raw": "{}"})
    view = http.get(VIEW, params={"view_mode": "draft_preview"})

    assert plan.status_code == view.status_code == 400, (plan.text, view.text)
    assert plan.json()["detail"] == view.json()["detail"]
    assert plan.json()["detail"]["code"] == "draft_required"
    assert plan.json()["detail"]["message"].startswith("Next: ")      # true at both seats


def test_a_config_file_gone_under_a_draft_is_refused_by_name_next_action_first(client, tmp_path):
    """총괄 d4a949a8c ⑨ — 초안 길은 active() 를 지나고, 파일이 없으면 LedgerSetupValidationError 가
    라우터를 빠져나가 500 이었다. view 도 같은 자리에서 같은 거절."""
    http, draft = client
    (tmp_path / "ontology" / "ledger_config.json").unlink()
    plan = http.post(PLAN, json={"selection": "source_plan|" + SOURCE,
                                 "draft_id": draft["draft_id"], "raw": json.dumps(draft["raw"])})
    view = http.get(VIEW)

    assert plan.status_code == view.status_code == 400, (plan.text, view.text)
    assert plan.json()["detail"] == view.json()["detail"]
    assert plan.json()["detail"]["code"] == "missing_config_file"
    assert plan.json()["detail"]["message"].startswith("Next: ")


@pytest.mark.parametrize("text, code", [("{ not json", "invalid_json"), ("[]", "invalid_type")],
                         ids=["broken_json", "root_is_a_list"])
def test_a_file_that_cannot_be_read_is_one_refusal_at_the_plan_and_at_view(client, tmp_path,
                                                                           text, code):
    """총괄 d4a949a8c ⑨ 후속 — 작성 계획은 자기 읽기로 unreadable_config, view 는 invalid_json ·
    invalid_type(path bundle) 이었다. 한 사실에 한 낱말."""
    http, _draft = client
    (tmp_path / "ontology" / "ledger_config.json").write_text(text, encoding="utf-8")
    plan = http.get(PLAN, params={"selection": "source_plan|" + SOURCE})
    view = http.get(VIEW)

    assert plan.status_code == view.status_code == 400, (plan.text, view.text)
    assert plan.json()["detail"] == view.json()["detail"]
    assert plan.json()["detail"]["code"] == code
    assert plan.json()["detail"]["message"].startswith("Next: ")


def test_a_file_with_a_repeated_key_is_still_read_by_the_plan_and_by_view(client, tmp_path):
    """The lenient read stays (총괄 (나)): the loader refuses a repeated key, the explorer shows it."""
    http, _draft = client
    sample = (SHIPPED / "ledger_config.json.sample").read_text(encoding="utf-8")
    repeated = sample.replace('"setup_version"', '"setup_version": 0, "setup_version"', 1)
    assert repeated != sample
    (tmp_path / "ontology" / "ledger_config.json").write_text(repeated, encoding="utf-8")

    plan = http.get(PLAN, params={"selection": "source_plan|" + SOURCE})
    view = http.get(VIEW)
    assert plan.status_code == view.status_code == 200, (plan.text, view.text)
