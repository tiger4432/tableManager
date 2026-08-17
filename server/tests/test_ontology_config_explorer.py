from __future__ import annotations

import json
from pathlib import Path
import shutil
import time
from types import MappingProxyType
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from admin_auth import require_admin_token, require_admin_token_strict
from ledger.config_explorer import (
    ConfigExplorerError,
    ExplorerIndex,
    ExplorerNode,
    ReferenceEdge,
    build_explorer_index,
    definition_diff,
    explorer_view,
)
from ledger.config_explorer_service import OntologyExplorerService
from ledger.cutover_v2 import (
    DEFAULT_ONTOLOGY_ROOT,
    load_cutover_setup,
    trusted_cutover_implementations,
)
from ledger.setup_bundle import require_ready_bundle, validate_bundle
from ledger.setup_registry import compile_setup_snapshot
import ontology_config_explorer_router as explorer_router


@pytest.fixture(scope="module")
def active_setup():
    return load_cutover_setup()


@pytest.fixture
def copied_root(tmp_path):
    target = tmp_path / "ontology"
    shutil.copytree(DEFAULT_ONTOLOGY_ROOT, target)
    return target


def test_actual_snapshot_enumerates_every_registry_and_claim(active_setup):
    index = build_explorer_index(active_setup)
    expected = {
        "predicate|slot_map@1",
        "entity|Lot@1",
        "pack|lot-lineage@1",
        "claim|lot-lineage@1/split_slot",
        "profile|lot-event@1",
        "mapping|lot-event@1#mapping:slot_preserving",
        "preparer|lot-event-live-frame@1",
        "mapper|lot-event-role@1",
        "source|lot_event",
        "table|lot_event",
    }
    assert expected.issubset(index.nodes)
    assert len(index.nodes) == 24


def test_every_resolved_edge_has_symmetric_used_by_and_exact_pointer(active_setup):
    index = build_explorer_index(active_setup)
    for edge in index.edges:
        if edge.status != "resolved":
            continue
        assert edge.to_key is not None
        assert sum(candidate.edge_id == edge.edge_id
                   for candidate in index.outbound[edge.from_key]) == 1
        assert sum(candidate.edge_id == edge.edge_id
                   for candidate in index.inbound[edge.to_key]) == 1
        assert edge.json_pointer.startswith("/")

    split = next(edge for edge in index.edges if
                 edge.from_key == "claim|lot-lineage@1/split_slot"
                 and edge.reference_kind == "emits_predicate")
    assert split.to_key == "predicate|slot_map@1"
    assert split.json_pointer == (
        "/packs/lot-lineage@1/claims/split_slot/emit/predicate")


def test_actual_round_trip_source_profile_claim_predicate(active_setup):
    index = build_explorer_index(active_setup)
    edges = {(edge.from_key, edge.to_key, edge.reference_kind) for edge in index.edges}
    assert ("source|lot_event", "profile|lot-event@1", "source_profile") in edges
    assert (
        "mapping|lot-event@1#mapping:slot_preserving",
        "claim|lot-lineage@1/split_slot",
        "mapping_claim",
    ) in edges
    assert (
        "claim|lot-lineage@1/split_slot", "predicate|slot_map@1",
        "emits_predicate",
    ) in edges


def test_view_uses_one_context_token_and_kind_specific_integrity(active_setup):
    index = build_explorer_index(active_setup)
    token = f"active:{index.snapshot_hash}"
    payload = explorer_view(
        index, context_token=token, selection="entity|Lot@1", limit=50)
    assert payload["context_token"] == token
    assert payload["selection"]["context_token"] == token
    assert all(item["context_token"] == token for item in payload["items"])
    assert all(item["context_token"] == token for item in payload["nodes"])
    assert all(item["context_token"] == token for item in payload["outbound"])
    assert all(item["context_token"] == token for item in payload["used_by"])
    assert {item["code"] for item in payload["integrity"]} == {
        "reference_resolution", "entity_identity"}
    assert "predicate_signature" not in {
        item["code"] for item in payload["integrity"]}

    service = OntologyExplorerService(setup_loader=lambda _root: active_setup)
    with pytest.raises(ConfigExplorerError) as stale:
        service.view(expected_context_token="active:" + "0" * 64)
    assert stale.value.to_mapping() == {
        "code": "stale_context",
        "path": "context_token",
        "message": (
            "requested view context no longer matches the compiled response context"),
    }


def test_search_is_server_paged_and_deterministic(active_setup):
    index = build_explorer_index(active_setup)
    first = explorer_view(index, context_token="active:x", query="lot", page=1, limit=2)
    second = explorer_view(index, context_token="active:x", query="lot", page=1, limit=2)
    assert first == second
    assert first["total"] > len(first["items"])
    assert len(first["items"]) == 2


def test_large_registry_search_and_used_by_payload_are_bounded():
    token = "active:" + "a" * 64
    nodes = {}
    outbound = {}
    inbound = {}
    edges = []
    total = 10_000
    for index in range(total):
        key = f"entity|Synthetic{index:05d}@1"
        nodes[key] = ExplorerNode(
            key=key, canonical_id=f"Synthetic{index:05d}@1", kind="entity",
            version=1, config_file="ledger_config.json",
            json_pointer=f"/entities/Synthetic{index:05d}@1",
            config_path=f"bundle.entities.Synthetic{index:05d}@1",
            raw={"keys": ["id"]}, compiled={"keys": ["id"]},
            definition_hash=f"{index:064x}", bundle_path=("entities", key),
        )
        outbound[key] = []
        inbound[key] = []
    target = "entity|Synthetic00000@1"
    for index in range(1, total):
        source = f"entity|Synthetic{index:05d}@1"
        edge = ReferenceEdge(
            edge_id=f"edge-{index:05d}", from_key=source, to_key=target,
            target_id="Synthetic00000@1", expected_kind="entity",
            reference_kind="synthetic_reference",
            json_pointer=f"/entities/Synthetic{index:05d}@1/ref", status="resolved",
        )
        edges.append(edge)
        outbound[source].append(edge)
        inbound[target].append(edge)
    index = ExplorerIndex(
        snapshot_hash="a" * 64, bundle_hash="b" * 64,
        nodes=MappingProxyType(nodes), edges=tuple(edges),
        outbound=MappingProxyType({k: tuple(v) for k, v in outbound.items()}),
        inbound=MappingProxyType({k: tuple(v) for k, v in inbound.items()}),
    )

    started = time.perf_counter()
    payload = explorer_view(
        index, context_token=token, selection=target,
        query="synthetic", limit=100, reference_limit=200)
    elapsed = time.perf_counter() - started
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    assert elapsed < 2.0
    assert payload["total"] == total
    assert payload["used_by_total"] == total - 1
    assert len(payload["used_by"]) == 200
    assert payload["references_truncated"] is True
    assert len(payload["nodes"]) <= 213
    assert len(encoded) < 1_500_000


def test_reference_extraction_is_registry_driven_for_transfer_fixture(active_setup):
    logical = active_setup.bundle.to_mapping()
    logical["entities"].update({
        "CoreDie@1": {"keys": ["core"]},
        "ProcessCell@1": {"keys": ["cell"]},
    })
    logical["vocabulary"]["transferred_to@1"] = {
        "status": "active", "layer": "ontology",
        "subjects": ["CoreDie@1"],
        "object": {
            "kind": "entity_ref", "types": ["ProcessCell@1"],
            "qualifiers": {"required": [], "optional": []},
        },
    }
    logical["packs"]["process-material-flow@1"] = {
        "claims": {
            "material_to_cell": {
                "roles": {
                    "material": {"kind": "entity", "required": True},
                    "cell": {"kind": "entity", "required": True},
                    "occurred_at": {"kind": "time", "required": True},
                },
                "emit": {
                    "predicate": "transferred_to@1",
                    "subject": "$material",
                    "object": {"kind": "entity_ref", "entity": "$cell",
                               "qualifiers": {}},
                    "occurred_at": "$occurred_at",
                },
            },
        },
    }
    bundle = require_ready_bundle(validate_bundle(logical))
    snapshot = compile_setup_snapshot(
        bundle, trusted_cutover_implementations(),
        tuple(active_setup.snapshot.verified_joins.values()))
    fixture_setup = SimpleNamespace(
        config_root=active_setup.config_root, bundle=bundle, snapshot=snapshot)
    index = build_explorer_index(fixture_setup)
    edge = next(edge for edge in index.edges if
                edge.from_key ==
                "claim|process-material-flow@1/material_to_cell"
                and edge.reference_kind == "emits_predicate")
    assert edge.to_key == "predicate|transferred_to@1"
    assert index.inbound[edge.to_key] == (edge,)
    assert index.nodes["entity|CoreDie@1"].kind == "entity"


def test_draft_save_keeps_active_bytes_and_valid_preview_is_separate(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    setup, index, _ = service.active()
    active_path = copied_root / "ledger_config.json"
    before = active_path.read_bytes()
    draft = service.create_draft(
        target_key="predicate|derived_from@1",
        base_snapshot_hash=index.snapshot_hash)
    raw = dict(draft["raw"])
    raw["object"] = dict(raw["object"])
    raw["object"]["qualifiers"] = {"required": [], "optional": ["reason"]}
    saved = service.save_draft(
        draft["draft_id"], expected_revision=0,
        raw=json.dumps(raw, ensure_ascii=False))

    assert active_path.read_bytes() == before
    assert saved["lifecycle_status"] == "saved"
    assert saved["preview_valid"] is True
    assert saved["preview_snapshot_hash"] != index.snapshot_hash
    view = service.view(
        draft_id=draft["draft_id"], revision=1,
        selection="predicate|derived_from@1")
    assert view["view_context"]["mode"] == "draft_preview"
    assert view["context_token"].startswith(f"draft:{draft['draft_id']}:1:")
    assert view["active_snapshot"]["snapshot_hash"] == index.snapshot_hash
    assert view["selection"]["change_status"] == "modified"


def test_catalog_declaration_is_read_only_and_unknown_selection_fails_closed(
    copied_root, tmp_path,
):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    _, index, _ = service.active()
    with pytest.raises(ConfigExplorerError) as readonly:
        service.create_draft(
            target_key="table|lot_event", base_snapshot_hash=index.snapshot_hash)
    assert readonly.value.to_mapping() == {
        "code": "unsupported_draft_target",
        "path": "target_key",
        "message": "this declaration is read-only in the current explorer",
    }
    with pytest.raises(ConfigExplorerError) as missing:
        service.view(selection="entity|Removed@1")
    assert missing.value.code == "unknown_selection"
    assert missing.value.path == "selection"


def test_invalid_draft_falls_back_to_active_without_fake_preview(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    _, index, _ = service.active()
    draft = service.create_draft(
        target_key="predicate|derived_from@1",
        base_snapshot_hash=index.snapshot_hash)
    saved = service.save_draft(
        draft["draft_id"], expected_revision=0,
        raw=json.dumps({"status": "active"}))
    assert saved["lifecycle_status"] == "invalid"
    assert saved["preview_valid"] is False
    view = service.view(
        draft_id=draft["draft_id"], revision=1,
        selection="predicate|derived_from@1")
    assert view["context_token"] == f"active:{index.snapshot_hash}"
    assert view["view_context"]["mode"] == "active_fallback"
    assert view["view_context"]["preview_snapshot_hash"] is None
    assert view["draft"]["validation_errors"]


def test_stale_draft_is_labeled_stale_in_active_fallback(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    _, index, _ = service.active()
    draft = service.create_draft(
        target_key="predicate|derived_from@1",
        base_snapshot_hash=index.snapshot_hash)
    record_path = service.draft_store._record_path(draft["draft_id"])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["base_snapshot_hash"] = "0" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")

    view = service.view(
        draft_id=draft["draft_id"], revision=0,
        selection="predicate|derived_from@1")

    assert view["view_context"]["mode"] == "active_fallback"
    assert view["view_context"]["fallback_reason"] == "stale_draft"
    assert view["draft"]["lifecycle_status"] == "stale"


def test_review_revision_is_immutable(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    _, index, _ = service.active()
    draft = service.create_draft(
        target_key="predicate|derived_from@1",
        base_snapshot_hash=index.snapshot_hash)
    saved = service.save_draft(
        draft["draft_id"], expected_revision=0,
        raw=json.dumps(draft["raw"]))
    reviewed = service.review_draft(draft["draft_id"], expected_revision=1)
    assert reviewed["lifecycle_status"] == "review_requested"
    assert reviewed["review_revision"] == 1
    with pytest.raises(ConfigExplorerError) as exc:
        service.save_draft(
            draft["draft_id"], expected_revision=1,
            raw=json.dumps(draft["raw"]))
    assert exc.value.code == "review_revision_locked"


def test_activation_is_cas_atomic_and_matches_reviewed_preview(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    _, index, _ = service.active()
    draft = service.create_draft(
        target_key="predicate|derived_from@1",
        base_snapshot_hash=index.snapshot_hash)
    raw = dict(draft["raw"])
    raw["object"] = dict(raw["object"])
    raw["object"]["qualifiers"] = {"required": [], "optional": ["reason"]}
    saved = service.save_draft(
        draft["draft_id"], expected_revision=0,
        raw=json.dumps(raw))
    service.review_draft(draft["draft_id"], expected_revision=1)
    result = service.activate_draft(
        draft["draft_id"], expected_revision=1, reload_callback=lambda: None)
    assert result["active_snapshot_hash"] == saved["preview_snapshot_hash"]
    assert result["runtime_convergence"]["status"] == "confirmed"
    reloaded, _, _ = service.active(force=True)
    assert reloaded.snapshot.snapshot_sha256 == saved["preview_snapshot_hash"]


def test_api_returns_structured_context_and_strict_draft_contract(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    explorer_router.configure_service(service)
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[require_admin_token_strict] = lambda: None
    app.include_router(explorer_router.router)
    client = TestClient(app)

    view = client.get(
        "/admin/ontology-explorer/view",
        params={"selection": "predicate|slot_map@1"}).json()
    assert view["context_token"].startswith("active:")
    created = client.post("/admin/ontology-explorer/drafts", json={
        "target_key": "predicate|slot_map@1",
        "base_snapshot_hash": view["snapshot_hash"],
    })
    assert created.status_code == 200
    draft = created.json()
    refused = client.put(
        f"/admin/ontology-explorer/drafts/{draft['draft_id']}",
        json={"expected_revision": 9, "raw": json.dumps(draft["raw"])})
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "stale_revision"
