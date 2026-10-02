# -*- coding: utf-8 -*-
"""총괄 04cecc30f (가) — 초안은 «파일의 그 선언»에서 시작한다(로더의 v5 -> v6 읽기 `upgrade_setup` 그대로).

색인의 node.raw 는 제품 기본값(`source_defaults`)이 이미 채운 묶음이라, 거기서 시작한 초안은 read 를 안 적은
소스에도 read 칸 다섯을 들고 열렸다 — 한 번 고치면 계획이 그 칸을 «적은 것»으로 읽어 접힌 read 가 펼쳐지고,
저장하면 안 고친 기본값이 파일에 적혔다. 표본의 die_inspection 에서 read 를 빼고 잰다.
"""
import copy
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.auth import require_admin_token, require_admin_token_strict
from ledger.config_explorer_service import OntologyExplorerService
from ledger.setup import load_setup
from ledger.setup_bundle import load_physical_catalog
from ledger_api import ontology_config_explorer_router as explorer_router

SHIPPED = Path(__file__).resolve().parent.parent / "config" / "sample"
CATALOG = load_physical_catalog(SHIPPED / "table_config.json.sample")
DRAFTS, PLAN = "/admin/ontology-explorer/drafts", "/admin/ontology-explorer/authoring/plan"
SLIM, KEY = "die_inspection", "source_plan|die_inspection"


def _document():
    document = json.loads((SHIPPED / "ledger_config.json.sample").read_text(encoding="utf-8"))
    source = document["sources"][SLIM]
    del source["read"]
    source["bind"]["mappings"]["die-inspected"]["bind"]["occurred_at"]["timezone"] = "Asia/Seoul"
    return document


def _version_5():
    """The same file as setup_version 5: the slim source carries the `direct-join` preparer the
    loader drops in memory."""
    document = _document()
    document["setup_version"] = 5
    document["sources"][SLIM]["prepare"] = {"implementation_id": "direct-join",
                                            "implementation_version": 1}
    return document


def _opened(tmp_path, document=None):
    root = tmp_path / "ontology"
    root.mkdir(parents=True)
    (root / "ledger_config.json").write_text(json.dumps(document or _document()), encoding="utf-8")
    service = OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts",
        setup_loader=lambda r: load_setup(r, catalog=CATALOG),
        catalog_loader=lambda: CATALOG,
        convergence_probe=lambda expected: {"ontology-explorer-api": expected,
                                            "ledger-persistent-reader": expected})
    explorer_router.configure_service(service)
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[require_admin_token_strict] = lambda: None
    app.include_router(explorer_router.router)
    http = TestClient(app)
    setup, index, _ = service.active()
    draft = http.post(DRAFTS, json={"target_key": KEY, "base_snapshot_hash": index.snapshot_hash})
    assert draft.status_code == 200, draft.text
    return http, service, root, index, setup, draft.json()


def test_a_slim_source_opens_its_draft_as_the_file_holds_it(tmp_path):
    _, _, _, index, _, draft = _opened(tmp_path)
    assert "read" in index.node(KEY).raw           # the filled bundle the draft used to start from
    assert draft["raw"] == _document()["sources"][SLIM]


def test_a_version_5_file_opens_its_draft_as_the_loader_reads_it(tmp_path):
    """The file's text would carry `prepare`, which the save refuses as `prepare_retired`."""
    http, _, _, _, _, draft = _opened(tmp_path, _version_5())
    assert draft["raw"] == _document()["sources"][SLIM]
    saved = http.put("%s/%s" % (DRAFTS, draft["draft_id"]),
                     json={"expected_revision": 0, "raw": json.dumps(draft["raw"])})
    assert saved.status_code == 200 and saved.json()["lifecycle_status"] == "saved", saved.text


def test_an_edit_outside_read_leaves_every_read_row_a_default(tmp_path):
    http, _, _, _, _, draft = _opened(tmp_path)
    raw = copy.deepcopy(draft["raw"])
    raw["bind"]["mappings"]["die-inspected"]["bind"]["occurred_at"]["timezone"] = "UTC"
    plan = http.post(PLAN, json={"selection": KEY, "draft_id": draft["draft_id"],
                                 "raw": json.dumps(raw)})
    assert plan.status_code == 200, plan.text
    read = {f["path"].split(".read.", 1)[1]: (f["state"], f["disposition"])
            for f in plan.json()["fields"] if ".%s.read." % SLIM in f["path"]}
    assert read and not [path for path, (state, _) in read.items() if state == "answered"], read


def test_an_edit_inside_read_leaves_the_other_read_rows_defaults(tmp_path):
    """The unsaved plan fills as the save fills, so a picked exclude_when clause leaves the read
    cells the loader fills derived defaults - only the edited row is answered."""
    http, _, _, _, _, draft = _opened(tmp_path)
    raw = copy.deepcopy(draft["raw"])
    raw["read"] = {"exclude_when": [{"column": "eqp_id", "blank": True}]}
    plan = http.post(PLAN, json={"selection": KEY, "draft_id": draft["draft_id"],
                                 "raw": json.dumps(raw)})
    assert plan.status_code == 200, plan.text
    read = {f["path"].split(".read.", 1)[1]: (f["state"], f["disposition"])
            for f in plan.json()["fields"] if ".%s.read." % SLIM in f["path"]}
    assert read.pop("exclude_when")[0] == "answered"
    assert read and not [path for path, (state, _) in read.items() if state == "answered"], read


def _saved(http, service, root, draft, raw):
    saved = http.put("%s/%s" % (DRAFTS, draft["draft_id"]),
                     json={"expected_revision": 0, "raw": json.dumps(raw)})
    assert saved.status_code == 200 and saved.json()["lifecycle_status"] == "saved", saved.text
    service.activate_draft(draft["draft_id"], expected_revision=1, reload_callback=lambda: None)
    return json.loads((root / "ledger_config.json").read_text(encoding="utf-8"))["sources"][SLIM]


def test_saving_one_read_cell_writes_that_cell_alone_and_hashes_as_the_hand_written_file(tmp_path):
    """총괄 10cea75d5: the save's fill used to write the read defaults beside the one edited cell."""
    http, service, root, _, _, draft = _opened(tmp_path / "form")
    raw = copy.deepcopy(draft["raw"])
    raw["read"] = {"exclude_when": [{"column": "eqp_id", "blank": True}]}
    assert _saved(http, service, root, draft, raw) == raw
    by_hand = _document()
    by_hand["sources"][SLIM]["read"] = copy.deepcopy(raw["read"])
    _, hand, _, _, hand_setup, _ = _opened(tmp_path / "hand", by_hand)
    after, _, _ = service.active(force=True)
    assert after.snapshot.bundle_sha256 == hand_setup.snapshot.bundle_sha256


def test_the_draft_plans_over_the_bundle_its_save_loads(tmp_path):
    """총괄 d4a949a8c ⑦ ⑨ after (가): the unsaved plan's input, loaded, is the bundle the save loads
    - a cell only the plan fills (`implementation_version`) included."""
    from ledger.config_drafts import with_unsaved_body
    from ledger.config_explorer_service import read_config_document

    http, service, root, index, setup, draft = _opened(tmp_path / "form")
    raw = copy.deepcopy(draft["raw"])
    raw["read"] = {"exclude_when": [{"column": "eqp_id", "blank": True}]}
    del raw["map"]["implementation_version"]
    planned, _ = with_unsaved_body(read_config_document(root), setup,
                                   service.draft_store.get(draft["draft_id"]), index, json.dumps(raw))
    planned_root = tmp_path / "planned"
    planned_root.mkdir()
    (planned_root / "ledger_config.json").write_text(json.dumps(planned), encoding="utf-8")
    _saved(http, service, root, draft, raw)
    after, _, _ = service.active(force=True)
    loaded = load_setup(planned_root, catalog=CATALOG)
    assert SLIM in loaded.snapshot.source_plans
    assert after.snapshot.bundle_sha256 == loaded.snapshot.bundle_sha256


def test_the_save_leaves_out_a_cell_the_loader_starts_filling(monkeypatch):
    """The save's fill asks the loader, so a cell `source_defaults` starts filling is left out with
    no change in the fill: `implementation_version` is written today (the plan derives it, the
    loader does not fill it) and is left out the moment the loader fills it."""
    from ledger import setup_bundle
    from ledger.config_authoring import filled_declaration

    document = _document()
    body = copy.deepcopy(document["sources"][SLIM])
    del body["map"]["implementation_version"]
    fill = lambda: filled_declaration(document, CATALOG, ["sources", SLIM], body)[0]["map"]  # noqa: E731
    assert fill()["implementation_version"] == 1
    real = setup_bundle.source_defaults

    def fills_one_more(source, catalog):
        out = real(source, catalog)
        if isinstance(out, dict) and isinstance(out.get("map"), dict):
            out = {**out, "map": {"implementation_version": 1, **out["map"]}}
        return out

    monkeypatch.setattr(setup_bundle, "source_defaults", fills_one_more)
    assert "implementation_version" not in fill()


def test_saving_the_draft_untouched_writes_no_read_cell_and_keeps_the_bundle(tmp_path):
    http, service, root, _, setup, draft = _opened(tmp_path)
    saved = http.put("%s/%s" % (DRAFTS, draft["draft_id"]),
                     json={"expected_revision": 0, "raw": json.dumps(draft["raw"])})
    assert saved.status_code == 200 and saved.json()["lifecycle_status"] == "saved", saved.text
    service.activate_draft(draft["draft_id"], expected_revision=1, reload_callback=lambda: None)
    written = json.loads((root / "ledger_config.json").read_text(encoding="utf-8"))["sources"][SLIM]
    assert "read" not in written
    after, _, _ = service.active(force=True)
    assert after.snapshot.bundle_sha256 == setup.snapshot.bundle_sha256
