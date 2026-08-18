from __future__ import annotations

import json
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
    _IndexBuilder,
    build_explorer_index,
    definition_diff,
    explorer_view,
    reference_diff,
)
from ledger.config_explorer_service import OntologyExplorerService
from ledger.setup import DEFAULT_ONTOLOGY_ROOT, load_setup
from ledger.implementations import trusted_implementations
from ledger.setup_bundle import require_ready_bundle, validate_bundle
from ledger.setup_registry import compile_setup_snapshot
import ontology_config_explorer_router as explorer_router
from tests.support.ontology_explorer_sample import load_transfer_sample_setup


@pytest.fixture(scope="module")
def active_setup():
    return load_setup()


@pytest.fixture
def copied_root(tmp_path):
    target = tmp_path / "ontology"
    shutil.copytree(DEFAULT_ONTOLOGY_ROOT, target)
    return target


@pytest.fixture(scope="module")
def transfer_sample_setup():
    return load_transfer_sample_setup()


def test_actual_snapshot_enumerates_every_registry_and_claim(active_setup):
    index = build_explorer_index(active_setup)
    bundle = active_setup.bundle.to_mapping()
    by_kind = {
        kind: {node.canonical_id for node in index.nodes.values() if node.kind == kind}
        for kind in {
            "predicate", "entity", "pack", "claim", "profile", "mapping",
            "binding", "preparer", "mapper", "source_plan", "verified_join", "table",
        }
    }
    assert by_kind["predicate"] == set(active_setup.snapshot.registries["vocabulary"])
    assert by_kind["entity"] == set(active_setup.snapshot.registries["entities"])
    assert by_kind["pack"] == set(active_setup.snapshot.registries["packs"])
    assert by_kind["profile"] == set(active_setup.snapshot.registries["profiles"])
    assert by_kind["preparer"] == set(active_setup.snapshot.registries["source_preparers"])
    assert by_kind["mapper"] == set(active_setup.snapshot.registries["mappers"])
    assert by_kind["source_plan"] == set(active_setup.snapshot.registries["sources"])
    assert by_kind["verified_join"] == set(active_setup.snapshot.registries["verified_joins"])
    assert by_kind["table"] == set(bundle["tables"])
    assert len(by_kind["claim"]) == sum(
        len(pack["claims"]) for pack in bundle["packs"].values())
    assert len(by_kind["mapping"]) == sum(
        len(profile["mappings"]) for profile in bundle["profiles"].values())
    assert len(by_kind["binding"]) == sum(
        len(mapping["bind"])
        for profile in bundle["profiles"].values()
        for mapping in profile["mappings"])
    expected = {
        "predicate|slot_map@1",
        "entity|Lot@1",
        "pack|lot-lineage@1",
        "claim|lot-lineage@1/slot_map",
        "profile|lot-event@1",
        "mapping|lot-event@1#mapping:slot_preserving",
        "preparer|lot-event-live-frame@1",
        "mapper|lot-event-role@1",
        "source_plan|lot_event",
        "binding|lot-event@1#mapping:slot_preserving#binding:subject",
        "table|lot_event",
    }
    assert expected.issubset(index.nodes)
    # 🔴 DERIVED, not a magic total. This was `== 47`, a literal that went stale the moment
    # the config's packs were reshaped -- and it went stale INVISIBLY, because the
    # assertion above it failed first and this line never ran. A number nobody can re-derive
    # is a number nobody notices is wrong.
    # What the test's name actually promises is a BIJECTION: every declaration becomes one
    # node and nothing else does. Summing the sections says that, and it keeps saying it
    # when a section grows.
    assert len(index.nodes) == (
        len(bundle["vocabulary"]) + len(bundle["entities"]) + len(bundle["packs"])
        + sum(len(pack["claims"]) for pack in bundle["packs"].values())
        + len(bundle["profiles"])
        + sum(len(profile["mappings"]) for profile in bundle["profiles"].values())
        + sum(len(mapping["bind"])
              for profile in bundle["profiles"].values()
              for mapping in profile["mappings"])
        + len(bundle["source_preparers"]) + len(bundle["mappers"])
        + len(bundle["sources"]) + len(bundle["tables"])
        + len(active_setup.snapshot.verified_joins))


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
                 edge.from_key == "claim|lot-lineage@1/slot_map"
                 and edge.reference_kind == "emits_predicate")
    assert split.to_key == "predicate|slot_map@1"
    assert split.json_pointer == (
        "/packs/lot-lineage@1/claims/slot_map/emit/predicate")


def test_actual_round_trip_source_profile_claim_predicate(active_setup):
    index = build_explorer_index(active_setup)
    edges = {(edge.from_key, edge.to_key, edge.reference_kind) for edge in index.edges}
    assert ("source_plan|lot_event", "profile|lot-event@1", "source_profile") in edges
    assert (
        "mapping|lot-event@1#mapping:slot_preserving",
        "claim|lot-lineage@1/slot_map",
        "mapping_claim",
    ) in edges
    assert (
        "claim|lot-lineage@1/slot_map", "predicate|slot_map@1",
        "emits_predicate",
    ) in edges
    assert (
        "mapping|lot-event@1#mapping:slot_preserving",
        "binding|lot-event@1#mapping:slot_preserving#binding:subject",
        "mapping_binding",
    ) in edges


def test_reference_statuses_are_closed_and_version_aware():
    builder = _IndexBuilder("a" * 64, "b" * 64)
    source = builder.add_node(
        "mapping", "source@1", {}, {}, ("source",),
        config_file="ledger_config.json", json_pointer="/source", version=1)
    builder.add_node(
        "entity", "Target@1", {"keys": ["id"]}, {"keys": ["id"]},
        ("entities", "Target@1"), config_file="ledger_config.json",
        json_pointer="/entities/Target@1", version=1)
    builder.add_node(
        "predicate", "WrongKind@1", {}, {}, ("vocabulary", "WrongKind@1"),
        config_file="ledger_config.json", json_pointer="/vocabulary/WrongKind@1",
        version=1)
    builder.add_edge(source, "Target@2", "entity", "version", "/ref/version")
    builder.add_edge(source, "WrongKind@1", "entity", "kind", "/ref/kind")
    builder.add_edge(source, "Missing@1", "entity", "missing", "/ref/missing")
    builder.add_edge(
        source, "Target@1", "entity", "signature", "/ref/signature",
        status="signature_mismatch")
    index = builder.finish()

    statuses = {edge.reference_kind: edge.status for edge in index.edges}
    assert statuses == {
        "kind": "wrong_kind",
        "missing": "unresolved",
        "signature": "signature_mismatch",
        "version": "wrong_version",
    }
    assert all(edge.message for edge in index.edges)


def test_definition_and_reference_diff_keep_all_four_normalized_states():
    def make_index(specs, edges=()):
        nodes = {
            key: ExplorerNode(
                key=key, canonical_id=key.split("|", 1)[1], kind=key.split("|", 1)[0],
                version=1, config_file="ledger_config.json", json_pointer=f"/{key}",
                config_path=f"ledger_config.json#/{key}", raw={}, compiled={},
                definition_hash=digest, bundle_path=(key,),
            )
            for key, digest in specs.items()
        }
        outbound = {key: [] for key in nodes}
        inbound = {key: [] for key in nodes}
        for edge in edges:
            outbound[edge.from_key].append(edge)
            if edge.to_key:
                inbound[edge.to_key].append(edge)
        return ExplorerIndex(
            snapshot_hash="a" * 64, bundle_hash="b" * 64,
            nodes=MappingProxyType(nodes), edges=tuple(edges),
            outbound=MappingProxyType({key: tuple(value) for key, value in outbound.items()}),
            inbound=MappingProxyType({key: tuple(value) for key, value in inbound.items()}),
        )

    shared = ReferenceEdge(
        edge_id="shared", from_key="entity|same@1", to_key="entity|changed@1",
        target_id="changed@1", expected_kind="entity", reference_kind="test",
        json_pointer="/shared", status="resolved")
    removed = ReferenceEdge(
        edge_id="removed", from_key="entity|same@1", to_key="entity|removed@1",
        target_id="removed@1", expected_kind="entity", reference_kind="test",
        json_pointer="/removed", status="resolved")
    added = ReferenceEdge(
        edge_id="added", from_key="entity|same@1", to_key="entity|added@1",
        target_id="added@1", expected_kind="entity", reference_kind="test",
        json_pointer="/added", status="resolved")
    modified_active = ReferenceEdge(
        edge_id="modified-active", from_key="entity|same@1",
        to_key="entity|removed@1", target_id="removed@1",
        expected_kind="entity", reference_kind="test",
        json_pointer="/modified", status="resolved")
    modified_preview = ReferenceEdge(
        edge_id="modified-preview", from_key="entity|same@1",
        to_key="entity|added@1", target_id="added@1",
        expected_kind="entity", reference_kind="test",
        json_pointer="/modified", status="signature_mismatch",
        message="target signature changed")
    active = make_index({
        "entity|same@1": "1", "entity|changed@1": "2", "entity|removed@1": "3",
    }, (shared, removed, modified_active))
    preview = make_index({
        "entity|same@1": "1", "entity|changed@1": "9", "entity|added@1": "4",
    }, (shared, added, modified_preview))

    assert dict(definition_diff(active, preview)) == {
        "entity|added@1": "added",
        "entity|changed@1": "modified",
        "entity|removed@1": "removed",
        "entity|same@1": "unchanged",
    }
    assert dict(reference_diff(active, preview)) == {
        "added": "added",
        "modified-preview": "modified",
        "removed": "removed",
        "shared": "unchanged",
    }
    preview_view = explorer_view(
        preview, context_token="draft:d1:1:preview",
        selection="entity|same@1", edge_diff=reference_diff(active, preview),
    )
    assert next(
        edge for edge in preview_view["outbound"]
        if edge["edge_id"] == "modified-preview"
    )["change_status"] == "modified"
    assert {
        item["edge_id"]: item["change_status"]
        for item in preview_view["edge_changes"]
    }["modified-preview"] == "modified"


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
    assert all(item["context_token"] == token for item in payload["path_candidates"])
    assert all(item["context_token"] == token for item in payload["integrity"])
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
        bundle, trusted_implementations(),
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


def test_file_backed_transfer_sample_round_trip_covers_required_registry_kinds(
    transfer_sample_setup,
):
    index = build_explorer_index(transfer_sample_setup)
    required = {
        "predicate|transferred_to@1",
        "entity|CoreDie@1",
        "entity|DTDie@1",
        "entity|DTJob@1",
        "entity|LotSlot@1",
        "pack|dt-assembly@1",
        "claim|dt-assembly@1/core_to_dt",
        "claim|dt-assembly@1/bond_component",
        "profile|dt-transfer@1",
        # The sample names the GENERIC implementations the repository ships.  Before
        # self-registration it named "sample-*" ids no class declared, so this round trip
        # only compiled because the support module carried a private trust list.
        "preparer|direct-join@1",
        "mapper|declarative-role@1",
        "verified_join|dt_job_to_inventory",
        "source_plan|dt_log",
        "table|dt_log",
        "binding|dt-transfer@1#mapping:core_to_dt#binding:subject",
    }
    assert required.issubset(index.nodes)
    edges = {(edge.from_key, edge.to_key, edge.reference_kind) for edge in index.edges}
    assert (
        "source_plan|dt_log", "profile|dt-transfer@1", "source_profile") in edges
    assert (
        "mapping|dt-transfer@1#mapping:core_to_dt",
        "claim|dt-assembly@1/core_to_dt", "mapping_claim") in edges
    assert (
        "claim|dt-assembly@1/core_to_dt",
        "predicate|transferred_to@1", "emits_predicate") in edges
    assert (
        "source_plan|dt_log", "verified_join|dt_job_to_inventory",
        "source_verified_join") in edges
    assert (
        "mapping|dt-transfer@1#mapping:bond_component",
        "claim|dt-assembly@1/bond_component", "mapping_claim") in edges
    assert index.nodes["predicate|transferred_to@1"].config_path == (
        "ledger_config.json#/vocabulary/transferred_to@1")

    logical = transfer_sample_setup.bundle.to_mapping()
    mappings = {
        item["mapping_id"]: item
        for item in logical["profiles"]["dt-transfer@1"]["mappings"]
    }
    lineage = [
        (
            mappings[mapping_id]["bind"]["subject"]["entity_type"],
            mappings[mapping_id]["bind"]["target"]["entity_type"],
        )
        for mapping_id in ("core_to_dt", "dt_to_bond", "bond_component")
    ]
    assert lineage == [
        ("CoreDie@1", "DTDie@1"),
        ("DTDie@1", "BondComponent@1"),
        ("BondComponent@1", "FinalChip@1"),
    ]
    assert ("CoreDie@1", "FinalChip@1") not in lineage
    bond_subject = mappings["bond_component"]["bind"]["subject"]
    assert set(bond_subject["keys"]) == {
        "bond_wafer", "bond_x", "bond_y", "layer",
    }
    assert logical["vocabulary"]["component_of@1"]["subjects"] == [
        "BondComponent@1"]

    token = f"active:{index.snapshot_hash}"
    view = explorer_view(
        index, context_token=token,
        selection="predicate|transferred_to@1", query="transferred")
    assert view["total"] == 1
    assert len(view["path_candidates"]) >= 2
    assert all(path["context_token"] == token for path in view["path_candidates"])


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
        selection="predicate|derived_from@1", view_mode="draft_preview")
    assert view["view_context"]["mode"] == "draft_preview"
    assert view["context_token"].startswith(f"draft:{draft['draft_id']}:1:")
    assert view["active_snapshot"]["snapshot_hash"] == index.snapshot_hash
    assert view["selection"]["change_status"] == "modified"
    assert view["draft"]["affected_definitions"]
    assert all(
        {"key", "canonical_id", "kind", "json_pointer", "change_status"}
        <= set(item) for item in view["changes"])
    assert all(
        item["context_token"] == view["context_token"]
        for item in view["changes"] + view["edge_changes"])

    active_view = service.view(
        draft_id=draft["draft_id"], revision=1,
        selection="predicate|derived_from@1", view_mode="active")
    assert active_view["view_context"]["mode"] == "active"
    assert active_view["context_token"] == f"active:{index.snapshot_hash}"
    assert active_view["draft"]["draft_id"] == draft["draft_id"]
    assert active_view["selection"]["change_status"] == "active"


def test_invalid_signature_is_classified_with_json_pointer(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    _, index, _ = service.active()
    draft = service.create_draft(
        target_key="predicate|has_wafer@1", base_snapshot_hash=index.snapshot_hash)
    raw = json.loads(json.dumps(draft["raw"]))
    raw["object"]["qualifiers"]["required"].append("new_required_value")
    saved = service.save_draft(
        draft["draft_id"], expected_revision=0, raw=json.dumps(raw))

    assert saved["lifecycle_status"] == "invalid"
    classified = [
        item for item in saved["validation_errors"]
        if item.get("reference_status") == "signature_mismatch"
    ]
    assert classified
    assert all(item["json_pointer"].startswith("/") for item in classified)


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
        selection="predicate|derived_from@1", view_mode="draft_preview")
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
        selection="predicate|derived_from@1", view_mode="draft_preview")

    assert view["view_context"]["mode"] == "active_fallback"
    assert view["view_context"]["fallback_reason"] == "stale_draft"
    assert view["draft"]["lifecycle_status"] == "stale"


def test_changed_target_is_labeled_conflict_not_plain_stale(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts")
    _, index, _ = service.active()
    draft = service.create_draft(
        target_key="predicate|derived_from@1", base_snapshot_hash=index.snapshot_hash)
    record_path = service.draft_store._record_path(draft["draft_id"])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["base_snapshot_hash"] = "0" * 64
    record["base_definition_hash"] = "1" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")

    view = service.view(
        draft_id=draft["draft_id"], revision=0,
        selection="predicate|derived_from@1", view_mode="draft_preview")
    assert view["view_context"]["mode"] == "active_fallback"
    assert view["view_context"]["fallback_reason"] == "conflict_draft"
    assert view["draft"]["lifecycle_status"] == "conflict"


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
    repeated = service.review_draft(draft["draft_id"], expected_revision=1)
    assert len(repeated["review_history"]) == 1
    with pytest.raises(ConfigExplorerError) as exc:
        service.save_draft(
            draft["draft_id"], expected_revision=1,
            raw=json.dumps(draft["raw"]))
    assert exc.value.code == "review_revision_locked"
    revised = service.revise_draft(
        draft["draft_id"], expected_revision=1)
    assert revised["revision"] == 2
    assert revised["lifecycle_status"] == "editing"
    assert revised["review_revision"] is None
    assert revised["review_history"][0]["revision"] == 1


def test_activation_is_cas_atomic_and_matches_reviewed_preview(copied_root, tmp_path):
    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts",
        convergence_probe=lambda expected: {
            "ontology-explorer-api": expected,
            "ledger-persistent-reader": expected,
        })
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
    assert result["runtime_convergence"]["confirmed_consumers"] == [
        "ledger-persistent-reader", "ontology-explorer-api"]
    reloaded, _, _ = service.active(force=True)
    assert reloaded.snapshot.snapshot_sha256 == saved["preview_snapshot_hash"]


@pytest.mark.parametrize(
    ("probe_mode", "expected_code"),
    (("empty", "convergence_unproven"), ("mismatch", "convergence_mismatch")),
)
def test_activation_rolls_back_until_every_declared_consumer_converges(
    copied_root, tmp_path, probe_mode, expected_code,
):
    def convergence(expected):
        if probe_mode == "empty":
            return {}
        return {"ontology-explorer-api": expected, "ledger-worker": "0" * 64}

    service = OntologyExplorerService(
        config_root=copied_root, draft_root=tmp_path / "drafts",
        convergence_probe=convergence)
    _, index, _ = service.active()
    active_path = copied_root / "ledger_config.json"
    before = active_path.read_bytes()
    draft = service.create_draft(
        target_key="predicate|derived_from@1", base_snapshot_hash=index.snapshot_hash)
    raw = json.loads(json.dumps(draft["raw"]))
    raw["object"]["qualifiers"]["optional"] = ["reason"]
    service.save_draft(
        draft["draft_id"], expected_revision=0, raw=json.dumps(raw))
    service.review_draft(draft["draft_id"], expected_revision=1)

    with pytest.raises(ConfigExplorerError) as refused:
        service.activate_draft(
            draft["draft_id"], expected_revision=1, reload_callback=lambda: None)
    assert refused.value.code == expected_code
    assert active_path.read_bytes() == before


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
    saved = client.put(
        f"/admin/ontology-explorer/drafts/{draft['draft_id']}",
        json={"expected_revision": 0, "raw": json.dumps(draft["raw"])})
    assert saved.status_code == 200
    reviewed = client.post(
        f"/admin/ontology-explorer/drafts/{draft['draft_id']}/review",
        json={"expected_revision": 1})
    assert reviewed.status_code == 200
    revised = client.post(
        f"/admin/ontology-explorer/drafts/{draft['draft_id']}/revise",
        json={"expected_revision": 1})
    assert revised.status_code == 200
    assert revised.json()["revision"] == 2
    assert revised.json()["lifecycle_status"] == "editing"
