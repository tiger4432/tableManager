# -*- coding: utf-8 -*-
"""총괄 791c0f45e 1 — 원장 선언 창에서 역할을 엔티티로 고르고 키를 아직 안 적은 채 저장하면 500 이었다
(setup_bundle._binding_columns 의 binding["keys"] KeyError). 반쪽 바인딩은 저장이 «거절로 답»하고,
엔티티를 고른 순간 «저장 없이» 그 키 칸이 폼에 뜬다 — 저장 뒤 폼과 같은 답으로.

소유자 재현: 소스 die_inspection · mappings.die-inspected 에 역할 하나 더 · entity · die@1 · 키 없음 · Save.
표본(추적되는 선언)으로 잰다 — 이 박스의 선언은 안 읽는다. 표본의 술어(inspected@1)는 역할이 더 없어서
선언된 역할 target 을 키 없이 다시 고른다 — 같은 자리(_binding_columns)를 지난다.
"""
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
SOURCE, SENTENCE, ENTITY = "die_inspection", "die-inspected", "die@1"
PLAN = "/admin/ontology-explorer/authoring/plan"


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
    return TestClient(app), service, root


def _draft(client, binding):
    """A draft of the source whose mapping's declared role `target` is bound as `binding`."""
    http, service, _root = client
    _, index, _ = service.active()
    draft = http.post("/admin/ontology-explorer/drafts", json={
        "target_key": "source_plan|" + SOURCE,
        "base_snapshot_hash": index.snapshot_hash}).json()
    raw = json.loads(json.dumps(draft["raw"]))
    raw["bind"]["mappings"][SENTENCE]["bind"]["target"] = binding
    return draft, json.dumps(raw)


def _rows(plan, prefix):
    return [row for row in plan["fields"] if row["path"].startswith(prefix)]


ROLE = "bundle.sources.%s.bind.mappings.%s.bind.target" % (SOURCE, SENTENCE)
KEYS = sorted(json.loads((SHIPPED / "ledger_config.json.sample").read_text(
    encoding="utf-8"))["entities"][ENTITY]["keys"])

HALF_BUILT = [
    {"kind": "entity", "entity_type": ENTITY},                                   # the owner's
    {},                                                                          # no kind
    {"kind": "column"},                                                          # no column
    {"kind": "entity", "entity_type": ENTITY, "keys": None},
    {"kind": "entity", "entity_type": ENTITY, "keys": list(KEYS)},               # wrong shape
    {"kind": "entity", "entity_type": ENTITY, "keys": {KEYS[0]: "a_column"}},    # not a dict
    {"kind": "entity", "entity_type": ENTITY, "attributes": ["x"]},
]


@pytest.mark.parametrize("binding", HALF_BUILT, ids=[
    "no_keys", "no_kind", "no_column", "keys_none", "keys_list", "key_not_dict",
    "attributes_list"])
def test_a_half_built_binding_is_saved_with_named_refusals(client, binding):
    draft, raw = _draft(client, binding)
    saved = client[0].put("/admin/ontology-explorer/drafts/%s" % draft["draft_id"],
                          json={"expected_revision": 0, "raw": raw})

    assert saved.status_code == 200, saved.text
    assert saved.json()["lifecycle_status"] == "invalid"
    assert saved.json()["validation_errors"], "the refusal is named, not a 500"


def test_the_key_squares_come_up_before_the_save_as_they_do_after_it(client):
    http, service, root = client
    draft, raw = _draft(client, {"kind": "entity", "entity_type": ENTITY})
    before_file = (root / "ledger_config.json").read_bytes()
    before_draft = json.dumps(service.draft_store.get(draft["draft_id"]), sort_keys=True)

    unsaved = http.post(PLAN, json={"selection": "source_plan|" + SOURCE,
                                    "draft_id": draft["draft_id"], "raw": raw})
    assert unsaved.status_code == 200, unsaved.text
    squares = sorted(row["path"] for row in _rows(unsaved.json(), ROLE + ".keys."))

    assert squares == ["%s.keys.%s.column" % (ROLE, key) for key in KEYS]
    assert (root / "ledger_config.json").read_bytes() == before_file, "nothing written"
    assert json.dumps(service.draft_store.get(draft["draft_id"]), sort_keys=True) == before_draft

    saved = http.put("/admin/ontology-explorer/drafts/%s" % draft["draft_id"],
                     json={"expected_revision": 0, "raw": raw}).json()
    service.activate_draft(draft["draft_id"], expected_revision=saved["revision"],
                           reload_callback=lambda: None)
    after = http.get(PLAN, params={"selection": "source_plan|" + SOURCE})

    assert _rows(after.json(), ROLE) == _rows(unsaved.json(), ROLE)
    assert _rows(after.json(), ROLE + ".keys.")


def test_the_unsaved_read_refuses_what_the_save_refuses(client):
    draft, _raw = _draft(client, {"kind": "entity", "entity_type": ENTITY})
    for raw, code in (("{not json", "invalid_json"), ("[1, 2]", "invalid_json_type")):
        answer = client[0].post(PLAN, json={"draft_id": draft["draft_id"], "raw": raw})
        assert answer.json()["detail"]["code"] == code
    unknown = client[0].post(PLAN, json={"draft_id": "no-such-draft", "raw": "{}"})
    assert unknown.status_code >= 400 and unknown.json()["detail"]["code"] in (
        "invalid_draft_id", "unknown_draft")


def test_a_square_the_save_fills_is_filled_in_the_unsaved_answer(client):
    """The save writes the plan's derived values into the gaps; the unsaved answer is read
    over the body as the save would store it, or the two answers part on every such square."""
    http, service, _root = client
    draft, raw = _draft(client, {"kind": "entity", "entity_type": ENTITY})
    prefix = "bundle.sources.%s." % SOURCE
    whole = http.get(PLAN, params={"selection": "source_plan|" + SOURCE}).json()
    filled = [row["path"] for row in whole["fields"] if row["path"].startswith(prefix)
              and row["state"] == "derived" and row["disposition"] != "shape"
              and row.get("declared") not in (None, [], {})]
    assert filled, "the fixture must have a square the save fills"
    body = json.loads(raw)
    steps = filled[0][len(prefix):].split(".")
    holder = body
    for step in steps[:-1]:
        holder = holder[step]
    del holder[steps[-1]]
    body = json.dumps(body)

    unsaved = http.post(PLAN, json={"selection": "source_plan|" + SOURCE,
                                    "draft_id": draft["draft_id"], "raw": body}).json()
    saved = http.put("/admin/ontology-explorer/drafts/%s" % draft["draft_id"],
                     json={"expected_revision": 0, "raw": body}).json()
    service.activate_draft(draft["draft_id"], expected_revision=saved["revision"],
                           reload_callback=lambda: None)
    after = http.get(PLAN, params={"selection": "source_plan|" + SOURCE}).json()

    assert _rows(unsaved, filled[0]) == _rows(after, filled[0])


def test_the_plan_marks_the_leaf_that_lays_out_the_key_squares(client):
    """The screen asks again when a marked leaf changes - it names no path itself."""
    http, _service, _root = client
    draft, raw = _draft(client, {"kind": "entity", "entity_type": ENTITY})
    rows = {row["path"]: row for row in http.post(PLAN, json={
        "selection": "source_plan|" + SOURCE, "draft_id": draft["draft_id"],
        "raw": raw}).json()["fields"]}

    assert rows[ROLE + ".entity_type"]["reshapes"] is True
    assert rows[ROLE + ".kind"]["reshapes"] is True
    assert {rows["%s.keys.%s.column" % (ROLE, key)]["reshapes"] for key in KEYS} == {False}
