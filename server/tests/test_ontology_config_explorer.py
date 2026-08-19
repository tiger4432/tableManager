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
    node_key,
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


def referenced_relations(bundle):
    """The relations a setup REFERENCES: every source's `relation`, plus both sides of
    every declared virtual join.

    This is what the explorer now turns into `table` nodes.  The physical schema moved out
    of `ledger_config.json` into `table_config.json`, which declares EVERY table in the
    system -- ingestion's, the grid's, the chain workers' -- so a node per catalog entry
    would fill the ledger's graph with tables it has nothing to say about.  The referenced
    set is exactly what the retired `tables` section used to hold, which is why the node
    counts below did not move: one table node on the live root, two on the transfer sample.
    """
    relations = {
        raw["relation"] for raw in bundle["sources"].values()
        if isinstance(raw.get("relation"), str)
    }
    for raw in bundle.get("virtual_joins", {}).values():
        for field in ("left_table", "right_table"):
            if isinstance(raw.get(field), str):
                relations.add(raw[field])
    return relations


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
    # WAS `== set(bundle["tables"])`. That section no longer exists -- the ledger stopped
    # keeping a copy of the physical schema -- so the subject of this assertion is now the
    # set of relations the setup REFERENCES, resolved against the carried catalog.
    tables = referenced_relations(bundle)
    assert tables, "a setup that references no relation would make this vacuous"
    assert by_kind["table"] == tables
    # And every one of them really came from the physical catalog, not from thin air --
    # payload and source file both, so "table nodes come from `table_config.json`" is a
    # claim this test can falsify rather than restate.
    assert tables <= set(active_setup.catalog)
    for table_id in tables:
        node = index.nodes[f"table|{table_id}"]
        assert node.config_file == "table_config.json"
        assert dict(node.raw) == dict(active_setup.catalog[table_id])
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
        + len(bundle["sources"]) + len(tables)
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
    # The fixture bundle is judged against the SAME physical catalog the live setup was
    # loaded with, and carries it onto the stand-in setup -- `build_explorer_index` refuses
    # a setup with no catalog rather than reaching for the live file behind the caller's
    # back.
    catalog = active_setup.catalog
    bundle = require_ready_bundle(validate_bundle(logical, catalog=catalog))
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(),
        tuple(active_setup.snapshot.verified_joins.values()), catalog=catalog)
    fixture_setup = SimpleNamespace(
        config_root=active_setup.config_root, bundle=bundle, snapshot=snapshot,
        catalog=catalog)
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


def test_authorable_sections_match_where_the_index_actually_puts_things(active_setup):
    """The create path builds a `bundle_path` from a kind; the index builds one from a
    declaration it already found. Nothing forces those two to agree, and a disagreement
    would not fail loudly -- it would write a new `mapper` into the wrong section, where
    the loader would refuse it with an error naming neither the screen nor the mistake.

    So score the map against the index rather than trusting both to be edited together.
    """
    from ledger.config_explorer import (AUTHORABLE_SECTIONS, authorable_bundle_path,
                                        build_explorer_index)

    index = build_explorer_index(active_setup)
    observed: dict[str, set[str]] = {}
    for node in index.nodes.values():
        observed.setdefault(node.kind, set()).add(node.bundle_path[0])

    for kind, section in AUTHORABLE_SECTIONS.items():
        if kind not in observed:
            continue          # nothing of this kind declared today; the map is still a claim
        assert observed[kind] == {section}, (
            f"the index files {kind!r} under {sorted(observed[kind])} but the authoring "
            f"path would create it in {section!r}")
        assert authorable_bundle_path(kind, "probe@1") == (section, "probe@1")

    # Non-vacuous: the live setup really does exercise several of these kinds, so the loop
    # above is comparing things rather than skipping everything.
    assert len(set(AUTHORABLE_SECTIONS) & set(observed)) >= 4

    # And the two kinds deliberately left out must NOT become creatable by accident.
    for excluded in ("table", "verified_join"):
        assert excluded not in AUTHORABLE_SECTIONS


def test_referenced_declaration_refuses_removal_and_names_who_points_at_it(active_setup):
    """A delete or rename of a referenced declaration must refuse BY NAME.

    Writing it anyway does not fail at write time -- the file is written, and the breakage
    surfaces later as a loader error about a reference nobody remembers making.  So the
    guard is scored on two things a count could not give: that it refuses at all, and that
    the refusal hands back rows an operator can act on (id + the exact json pointer).
    """
    from ledger.config_explorer import referrers, require_no_referrers

    index = build_explorer_index(active_setup)
    resolved_inbound = {
        key: [edge for edge in edges if edge.status == "resolved"]
        for key, edges in index.inbound.items()
    }
    referenced = sorted(
        (key for key, edges in resolved_inbound.items() if edges),
        key=lambda key: (-len(resolved_inbound[key]), key),
    )
    # Non-vacuous: the live setup really does have referenced declarations, so the rest of
    # this test is comparing things rather than iterating an empty list.
    assert referenced

    subject = referenced[0]
    rows = referrers(index, subject)
    assert len(rows) == len(resolved_inbound[subject])
    # The rows must BE the inbound edges, not a plausible-looking summary of them.
    assert {(row["key"], row["json_pointer"]) for row in rows} == {
        (edge.from_key, edge.json_pointer) for edge in resolved_inbound[subject]
    }
    assert all(row["canonical_id"] and row["json_pointer"].startswith("/") for row in rows)
    assert list(rows) == sorted(
        rows, key=lambda row: (row["kind"], row["canonical_id"], row["json_pointer"]))

    for action in ("delete", "rename"):
        with pytest.raises(ConfigExplorerError) as refused:
            require_no_referrers(index, subject, action)
        mapping = refused.value.to_mapping()
        assert mapping["code"] == "declaration_is_referenced"
        # The refusal names the ACTION, not only the fault: "this is referenced" does not
        # tell an operator which of their two buttons just refused them.
        assert mapping["message"].startswith(f"{action} refused:")
        assert index.node(subject).canonical_id in mapping["message"]
        assert mapping["details"] == [dict(row) for row in rows]


def test_an_already_dangling_inbound_edge_does_not_make_a_declaration_undeletable():
    """Only `resolved` inbound edges are referrers.

    This is the case the two candidate rules disagree on.  An inbound edge whose status is
    not `resolved` names a target it did not actually reach -- it is ALREADY broken, and
    counting it would make a declaration permanently undeletable because something else is
    wrong.  A fixture with only healthy edges cannot tell the two rules apart, so build one
    that has exactly the awkward edge and nothing else.

    The healthy half at the bottom is what makes the first half a decision rather than a
    guard that never fires: on the live root every declaration is referenced, so a guard
    that always returned "no referrers" would look identical there.
    """
    from ledger.config_explorer import referrers, require_no_referrers

    def two_node_index(status):
        builder = _IndexBuilder("a" * 64, "b" * 64)
        source = builder.add_node(
            "mapping", "source@1", {}, {}, ("source",),
            config_file="ledger_config.json", json_pointer="/source", version=1)
        builder.add_node(
            "entity", "Target@1", {"keys": ["id"]}, {"keys": ["id"]},
            ("entities", "Target@1"), config_file="ledger_config.json",
            json_pointer="/entities/Target@1", version=1)
        builder.add_edge(
            source, "Target@1", "entity", "subject", "/ref/subject", status=status)
        return builder.finish()

    dangling = two_node_index("signature_mismatch")
    # The edge really is inbound on the target -- otherwise this proves nothing.
    assert [edge.status for edge in dangling.inbound["entity|Target@1"]] == [
        "signature_mismatch"]
    assert referrers(dangling, "entity|Target@1") == tuple()
    require_no_referrers(dangling, "entity|Target@1", "delete")

    healthy = two_node_index(None)
    assert [edge.status for edge in healthy.inbound["entity|Target@1"]] == ["resolved"]
    with pytest.raises(ConfigExplorerError) as refused:
        require_no_referrers(healthy, "entity|Target@1", "rename")
    assert refused.value.to_mapping()["details"] == [{
        "key": "mapping|source@1",
        "canonical_id": "source@1",
        "kind": "mapping",
        "reference_kind": "subject",
        "json_pointer": "/ref/subject",
    }]


def test_a_source_plan_and_its_profile_reference_each_other_in_both_directions(active_setup):
    """🔴 A REFERENTIAL GUARD ALONE CANNOT DELETE A SOURCE PLAN OR ITS PROFILE.

    Found by RUNNING the guard over the live index rather than reading it: every single
    declaration there has at least one resolved referrer, and for this pair the reason is
    structural rather than incidental.  `build_explorer_index` extracts an edge in each
    direction -- `profiles.<id>.source` names the source plan, and
    `sources.<id>.profile_id` names the profile -- so each is the other's only referrer.

    "Refuse while referenced, repoint first" therefore deadlocks: neither can be deleted
    until the other is, and the other cannot be deleted either.  Whoever wires delete and
    rename needs an owner ruling here (exempt a mutual pair? accept a set of declarations
    in one draft? require the profile's `source` to be repointed first?).  It is asserted
    rather than written in a comment because a future edge change that breaks the deadlock
    should make this test speak up rather than pass silently.
    """
    index = build_explorer_index(active_setup)
    pairs = [
        (node.key, node_key("profile", node.raw["profile_id"]))
        for node in index.nodes.values() if node.kind == "source_plan"
    ]
    assert pairs, "no source plan declared; this test would otherwise be vacuous"
    for source_key, profile_key in pairs:
        assert profile_key in index.nodes
        assert profile_key in {edge.from_key for edge in index.inbound[source_key]}
        assert source_key in {edge.from_key for edge in index.inbound[profile_key]}


#: kind -> the `bundle_path` `build_explorer_index` actually builds for it.
#:
#: 🔴 A FIXTURE THAT INVENTS THIS SCORES A SHAPE THAT DOES NOT EXIST.  `deletion_plan` reads
#: `bundle_path[0]` to decide whether a declaration lives in a section this screen can
#: write, so a fixture that puts the KIND there (`("pack", "p")` instead of
#: `("packs", "p")`) makes every synthetic node look un-authorable and every assertion
#: below meaningless -- green or red for a reason that has nothing to do with the subject.
#: `test_the_fixture_bundle_paths_match_the_ones_the_index_builds` scores this map against
#: a real index rather than trusting it.
_FIXTURE_BUNDLE_PATH = {
    "predicate": lambda i: ("vocabulary", i),
    "entity": lambda i: ("entities", i),
    "pack": lambda i: ("packs", i),
    "claim": lambda i: ("packs", i.split("/")[0], "claims", i.split("/", 1)[1]),
    "preparer": lambda i: ("source_preparers", i),
    "mapper": lambda i: ("mappers", i),
    "profile": lambda i: ("profiles", i),
    "source_plan": lambda i: ("sources", i),
    "verified_join": lambda i: ("virtual_joins", i),
    "table": lambda i: ("__physical_catalog__", i),
}


def _linked_index(nodes, edges, *, config_files=None):
    """A hand-built index with exactly the shape under test and nothing else.

    The live root has one source and one profile, so it cannot tell "the pair is exempt"
    apart from "the component is computed".  These fixtures can.
    """
    from ledger.config_explorer import pointer

    config_files = config_files or {}
    builder = _IndexBuilder("a" * 64, "b" * 64)
    for kind, canonical_id in nodes:
        bundle_path = _FIXTURE_BUNDLE_PATH[kind](canonical_id)
        builder.add_node(
            kind, canonical_id, {}, {}, bundle_path,
            config_file=config_files.get(kind, "ledger_config.json"),
            json_pointer=pointer(*bundle_path))
    for from_kind, from_id, to_kind, to_id, reference_kind in edges:
        builder.add_edge(
            node_key(from_kind, from_id), to_id, to_kind, reference_kind,
            pointer(from_kind, from_id, reference_kind))
    return builder.finish()


def test_deleting_a_source_with_the_profile_only_it_uses_succeeds(transfer_sample_setup):
    """🔴 THE REGRESSION GUARD.  A suite that only asserts refusals stays green while the
    instrument is broken -- that is exactly how this defect would come back.

    The ruling (2026-08-18): in-degree is the wrong instrument, the deletable unit is the
    reference component, and the question is reachability AFTER the deletion.  So the
    scoring case is a SUCCESS: a source and the profile only it uses go together, and the
    screen must let them.

    The contrast at the bottom is what makes this a test about the instrument rather than
    about this config: on the very same subject the in-degree fallback still refuses.  If
    someone ever wires that as the gate, this test fails and says why.

    Scored on the transfer SAMPLE, not the live root: the live `ledger_config.json` is
    gitignored and hand-edited, so a test that pins its exact component would go red for a
    reason that has nothing to do with this instrument.  The sample carries the same mutual
    pair (`sources.dt_log.profile_id` and `profiles.dt-transfer@1.source`), which is the
    property under test, and the assertions below derive the pair rather than name it.
    """
    from ledger.config_explorer import (
        deletion_plan, require_deletable, require_no_referrers)

    index = build_explorer_index(transfer_sample_setup)
    source = next(
        node.key for node in index.nodes.values() if node.kind == "source_plan")
    profile = node_key("profile", index.nodes[source].raw["profile_id"])
    # Non-vacuous: this really is the mutual pair that defeats in-degree.
    assert source in {edge.from_key for edge in index.inbound[profile]}
    assert profile in {edge.from_key for edge in index.inbound[source]}

    plan = deletion_plan(index, [source])
    assert plan.blocked == tuple(), (
        "a delete whose only referrers are inside the deletion set must SUCCEED")
    require_deletable(index, plan, "delete")            # must not raise

    removed = plan.removed_keys
    assert source in removed and profile in removed
    rows = {row["key"]: row for row in plan.removed}
    assert rows[source]["reason"] == "selected"
    assert rows[profile]["reason"] == "orphaned"
    # The plan says WHY the profile is going, by naming what was holding it up.
    assert source in rows[profile]["held_by"]
    # Every mapping and binding of that profile goes with it -- the component, not the node.
    assert {key for key in removed if key.startswith("mapping|")}
    assert all(key in removed for key, node in index.nodes.items()
               if node.kind in {"mapping", "binding"})

    # And the in-degree fallback, on the same subject, still refuses. This is the exact
    # wiring the ruling forbids; the two must not be confused.
    with pytest.raises(ConfigExplorerError) as refused:
        require_no_referrers(index, source, "delete")
    assert refused.value.code == "declaration_is_referenced"


def test_deleting_a_profile_alone_is_blocked_and_names_the_surviving_reacher(transfer_sample_setup):
    """The fallback's real job: a reacher that SURVIVES the deletion.

    Deleting the profile without its source would leave `sources.<id>.profile_id` naming
    a declaration that no longer exists -- the silent dangling reference this whole thing
    exists to prevent.  The refusal has to name the source, because "add it to the
    selection" is the operator's next move and a count cannot carry it.
    """
    from ledger.config_explorer import deletion_plan, require_deletable

    index = build_explorer_index(transfer_sample_setup)
    source = next(
        node.key for node in index.nodes.values() if node.kind == "source_plan")
    profile = node_key("profile", index.nodes[source].raw["profile_id"])

    plan = deletion_plan(index, [profile])
    assert [row["key"] for row in plan.blocked] == [profile]
    reachers = plan.blocked[0]["reached_by"]
    assert [row["key"] for row in reachers] == [source]
    assert reachers[0]["json_pointer"].endswith("/profile_id")

    with pytest.raises(ConfigExplorerError) as refused:
        require_deletable(index, plan, "delete")
    mapping = refused.value.to_mapping()
    assert mapping["code"] == "declaration_is_referenced"
    assert mapping["message"].startswith("delete refused:")
    assert mapping["details"][0]["blocked_key"] == profile
    assert mapping["details"][0]["key"] == source

    # Selecting BOTH is the move the refusal describes, and it must then succeed.
    both = deletion_plan(index, [profile, source])
    assert both.blocked == tuple()
    require_deletable(index, both, "delete")


def test_a_third_kind_in_the_cycle_goes_with_it_without_a_pair_special_case():
    """🔴 The mutual reference is STRUCTURAL, so a hardcoded source-profile check dies
    the day a third kind joins the cycle.  This is that day, built on purpose.

    source -> profile -> mapper -> source.  No node has in-degree zero, so an in-degree
    gate refuses all three and a pair exemption saves only two.  Reachability from the
    remaining roots takes the whole cycle, and the procedure never mentions a kind.
    """
    from ledger.config_explorer import deletion_plan, self_standing_keys

    index = _linked_index(
        [("source_plan", "s"), ("profile", "p"), ("mapper", "m")],
        [("source_plan", "s", "profile", "p", "source_profile"),
         ("profile", "p", "mapper", "m", "profile_pack"),
         ("mapper", "m", "source_plan", "s", "mapper_emits")],
    )
    assert self_standing_keys(index) == frozenset(), (
        "every node must have a referrer or this fixture proves nothing")

    plan = deletion_plan(index, ["source_plan|s"])
    assert plan.blocked == tuple()
    assert set(plan.removed_keys) == {"source_plan|s", "profile|p", "mapper|m"}


def test_a_half_wired_declaration_survives_an_unrelated_deletion():
    """Two things a deletion must NOT take: a declaration shared with a survivor, and a
    declaration nothing points at yet.

    The second is the normal state of the screen this feeds -- an author creates a pack
    minutes before any profile uses it.  If in-degree zero were not a walk root, the first
    unrelated deletion would find that pack unreachable and quietly sweep it.
    """
    from ledger.config_explorer import deletion_plan

    index = _linked_index(
        [("source_plan", "a"), ("profile", "pa"), ("source_plan", "b"),
         ("profile", "pb"), ("mapper", "shared"), ("pack", "fresh"),
         ("claim", "fresh/one")],
        [("source_plan", "a", "profile", "pa", "source_profile"),
         ("profile", "pa", "source_plan", "a", "profile_source"),
         ("source_plan", "a", "mapper", "shared", "source_mapper"),
         ("source_plan", "b", "profile", "pb", "source_profile"),
         ("profile", "pb", "source_plan", "b", "profile_source"),
         ("source_plan", "b", "mapper", "shared", "source_mapper"),
         ("pack", "fresh", "claim", "fresh/one", "contains_claim")],
    )

    plan = deletion_plan(index, ["source_plan|a"])
    assert plan.blocked == tuple()
    assert set(plan.removed_keys) == {"source_plan|a", "profile|pa"}, (
        "the shared mapper and the half-wired pack are held up by survivors")

    # And deleting the half-wired pack ITSELF must still take what it holds up.  This is
    # the half that needs the zero-in-degree walk root: without it the pack is outside
    # every walk, the plan reports only the pack, and the claim inside it disappears from
    # the file having never been named on the confirm screen.
    fresh = deletion_plan(index, ["pack|fresh"])
    assert fresh.blocked == tuple()
    assert set(fresh.removed_keys) == {"pack|fresh", "claim|fresh/one"}


def test_pre_existing_garbage_is_not_swept_into_an_unrelated_deletion():
    """A deletion may only take what it is actually holding up.

    An orphaned cycle -- unreachable from any root BEFORE the deletion too -- is already
    garbage, and it is somebody else's problem.  Subtracting the after-walk from every
    node instead of from the before-walk would hand it to whoever deletes next, in a list
    they have no reason to expect.
    """
    from ledger.config_explorer import deletion_plan

    index = _linked_index(
        [("source_plan", "s"), ("profile", "p"),
         ("entity", "GhostA"), ("entity", "GhostB")],
        [("source_plan", "s", "profile", "p", "source_profile"),
         ("profile", "p", "source_plan", "s", "profile_source"),
         ("entity", "GhostA", "entity", "GhostB", "subject_entity"),
         ("entity", "GhostB", "entity", "GhostA", "subject_entity")],
    )

    plan = deletion_plan(index, ["source_plan|s"])
    assert set(plan.removed_keys) == {"source_plan|s", "profile|p"}
    assert not any(key.startswith("entity|Ghost") for key in plan.removed_keys)


def test_a_table_is_released_rather_than_deleted_and_cannot_be_selected(transfer_sample_setup):
    """`table_config.json` is read here and written elsewhere.

    A table that stops being referenced is not a casualty -- nothing is written for it, and
    folding it into `removed` would tell the author their physical schema is about to be
    deleted.  Selecting one outright is refused by the file it lives in, not by its kind.
    """
    from ledger.config_explorer import deletion_plan

    index = build_explorer_index(transfer_sample_setup)
    source = next(
        node.key for node in index.nodes.values() if node.kind == "source_plan")
    table = node_key("table", index.nodes[source].raw["relation"])
    assert index.nodes[table].config_file == "table_config.json"

    plan = deletion_plan(index, [source])
    assert table in {row["key"] for row in plan.released}
    assert table not in plan.removed_keys
    assert all(row["config_file"] == "ledger_config.json" for row in plan.removed)

    with pytest.raises(ConfigExplorerError) as refused:
        deletion_plan(index, [table])
    assert refused.value.to_mapping()["code"] == "undeletable_declaration"

    with pytest.raises(ConfigExplorerError) as empty:
        deletion_plan(index, [])
    assert empty.value.to_mapping()["code"] == "empty_deletion"

    with pytest.raises(ConfigExplorerError) as unknown:
        deletion_plan(index, ["entity|NoSuchThing@9"])
    assert unknown.value.to_mapping()["code"] == "unknown_selection"


def test_the_fixture_bundle_paths_match_the_ones_the_index_builds(transfer_sample_setup):
    """The fixtures above decide their own `bundle_path`, so they can be wrong on purpose
    without anybody noticing -- and every deletion assertion is scored through it.

    So score the map against a real index.  Any kind the sample actually declares must land
    at exactly the path `_FIXTURE_BUNDLE_PATH` claims for it; the day `build_explorer_index`
    moves a section, this goes red here instead of quietly making the synthetic tests
    measure a shape the product does not have.
    """
    index = build_explorer_index(transfer_sample_setup)

    seen = set()
    for node in index.nodes.values():
        builder = _FIXTURE_BUNDLE_PATH.get(node.kind)
        if builder is None:          # sub-declarations the fixtures never build by hand
            continue
        seen.add(node.kind)
        assert node.bundle_path == builder(node.canonical_id), (
            f"the fixture builds {node.kind} at {builder(node.canonical_id)} but the index "
            f"builds it at {node.bundle_path}")

    assert {"source_plan", "profile", "pack", "claim", "entity", "table"} <= seen, (
        "the sample stopped declaring a kind this map covers -- the check went vacuous")


def test_the_deletable_set_is_contained_in_the_creatable_one(transfer_sample_setup):
    """🔴 THE INVARIANT, NOT A MEMBERSHIP LIST.  Ruling (2026-08-19).

    The bug was an asymmetry: `verified_join` could be DELETED on this screen and not
    CREATED on it.  The cheap test would name `verified_join` and assert it is refused --
    and that test goes red for the wrong reason on the day `virtual_joins` is legitimately
    added to `AUTHORABLE_SECTIONS`, and stays green if a FOURTH un-authorable section shows
    up.  It scores the example instead of the property.

    So assert the property over every node the index actually holds: anything this screen
    will delete is something it could have written.  Nothing here names a kind, so a new
    section added to one side only cannot slip past.
    """
    from ledger.config_explorer import (
        AUTHORABLE_SECTION_NAMES, deletion_plan, owning_section, undeletable_reason)

    index = build_explorer_index(transfer_sample_setup)
    assert index.nodes, "an empty index would make this vacuous"

    for node in index.nodes.values():
        if undeletable_reason(node) is None:
            assert owning_section(node) in AUTHORABLE_SECTION_NAMES, (
                f"{node.key} is deletable but lives in a section this screen cannot write")

    # And the containment holds for CASUALTIES too, which is the half a check on the
    # selection alone cannot see: nothing is selected there, the node merely stops being
    # reachable, and the write path would have taken it anyway.
    source = next(
        node.key for node in index.nodes.values() if node.kind == "source_plan")
    plan = deletion_plan(index, [source])
    for row in plan.removed:
        assert owning_section(index.nodes[row["key"]]) in AUTHORABLE_SECTION_NAMES


def test_a_verified_join_is_retained_rather_than_deleted():
    """The asymmetry itself, on a fixture, because the live root cannot show it.

    🔴 THE LIVE ROOT DECLARES ZERO `verified_join`s.  That is why this defect was invisible:
    every deletion answered correctly, and would have gone on answering correctly until the
    day somebody declared the first one.  A condition that is false today is not safe -- it
    is untested.  So the fixture declares one.

    Two directions, and the second is the one a selection-only guard misses:
      * selecting it outright is refused, and the refusal says where to go instead;
      * losing its last referrer does NOT delete it -- it lands in `retained`, still in the
        file, named on the plan, because this screen could not write it back.
    """
    from ledger.config_explorer import deletion_plan

    index = _linked_index(
        [("source_plan", "s"), ("profile", "p"), ("verified_join", "j")],
        [("source_plan", "s", "profile", "p", "source_profile"),
         ("profile", "p", "source_plan", "s", "profile_source"),
         ("source_plan", "s", "verified_join", "j", "source_verified_join")],
    )

    with pytest.raises(ConfigExplorerError) as refused:
        deletion_plan(index, ["verified_join|j"])
    mapping = refused.value.to_mapping()
    assert mapping["code"] == "undeletable_declaration"
    assert "virtual_joins" in mapping["message"], (
        "the refusal has to name the section, or the operator has no next move")

    plan = deletion_plan(index, ["source_plan|s"])
    assert set(plan.removed_keys) == {"source_plan|s", "profile|p"}
    assert [row["key"] for row in plan.retained] == ["verified_join|j"]
    assert plan.retained[0]["reason"] == "unauthorable_here"


def test_a_sub_declaration_still_goes_with_the_declaration_that_owns_it():
    """🔴 THE MIRROR FAULT, and the one that nearly shipped: scoring deletability on the
    KIND instead of the SECTION.

    `claim`, `mapping` and `binding` have no entry in `AUTHORABLE_SECTIONS` -- they own no
    section, they are written as part of their owner.  A kind-membership rule calls them
    un-authorable and strands them in the file when their owner goes, which is the exact
    orphan `deletion_plan` exists to prevent, arrived at by way of a fix for the opposite
    bug.  `verified_join` is un-authorable because its SECTION is; a claim's section is
    `packs`, and `packs` is authorable.
    """
    from ledger.config_explorer import deletion_plan

    index = _linked_index(
        [("pack", "fresh"), ("claim", "fresh/one")],
        [("pack", "fresh", "claim", "fresh/one", "contains_claim")],
    )

    plan = deletion_plan(index, ["pack|fresh"])
    assert set(plan.removed_keys) == {"pack|fresh", "claim|fresh/one"}
    assert plan.retained == tuple(), "a claim is not stranded; it goes with its pack"

    # Selecting the claim ON ITS OWN is a different question, and the answer today is
    # "blocked": the surviving pack still points at it, so the reachability instrument
    # refuses exactly as it would for any other live reference.  Asserted here because it
    # is the behaviour, not because it is obviously the right product decision -- removing
    # one claim from a pack is an ordinary authoring move, and today it can only be done by
    # editing the pack.  That gap is raised as an open item; this test pins what the code
    # does so a future change to it is deliberate rather than incidental.
    alone = deletion_plan(index, ["claim|fresh/one"])
    assert alone.removed_keys == tuple()
    assert [row["key"] for row in alone.blocked] == ["claim|fresh/one"]
    assert [r["key"] for r in alone.blocked[0]["reached_by"]] == ["pack|fresh"]


def test_deleting_the_last_source_is_allowed_and_reports_itself_as_a_reset():
    """Ruling (2026-08-19): do not block it -- RENAME it, with a computed number.

    Blocking would leave the config creatable but not un-creatable, the mirror of the
    asymmetry above.  What is refused instead is calling it "delete": with no source left
    there is nothing to walk from, so what remains is an empty bundle wearing its old
    declarations.

    🔴 THE MAGNITUDE IS COMPUTED, NOT FROZEN.  "44 of 45" was one measurement on one day.
    The second half of this test adds a declaration and asserts the number MOVED -- a
    hard-coded 44 passes the first half and fails here, which is the only way to tell a
    rendered count from a remembered one.

    The predicate is structural, not a percentage: `sources_after == 0`, not "over 90%".
    """
    from ledger.config_explorer import deletion_plan

    nodes = [("source_plan", "s"), ("profile", "p"), ("mapper", "m")]
    edges = [("source_plan", "s", "profile", "p", "source_profile"),
             ("profile", "p", "source_plan", "s", "profile_source"),
             ("profile", "p", "mapper", "m", "profile_mapper")]
    index = _linked_index(nodes, edges)

    plan = deletion_plan(index, ["source_plan|s"])
    assert plan.blocked == tuple(), "the last source is deletable, not blocked"
    assert plan.is_reset is True
    assert plan.sources_before == 1 and plan.sources_after == 0
    assert plan.authored_total == 3
    assert len(plan.removed) == 3
    assert plan.to_mapping()["is_reset"] is True

    # One more declaration, and the number the confirm screen renders must move with it.
    wider = _linked_index(nodes + [("entity", "Wafer")], edges)
    assert deletion_plan(wider, ["source_plan|s"]).authored_total == 4, (
        "authored_total is rendered from the index at plan time; a frozen count would "
        "still say 3 here and would lie on the confirm screen without anybody touching it")

    # A deletion that leaves a source standing is an ordinary delete, and must NOT wear the
    # reset wording -- otherwise every confirm shouts and the shouting stops meaning
    # anything.
    two = _linked_index(
        nodes + [("source_plan", "t"), ("profile", "q")],
        edges + [("source_plan", "t", "profile", "q", "source_profile"),
                 ("profile", "q", "source_plan", "t", "profile_source")],
    )
    ordinary = deletion_plan(two, ["source_plan|t"])
    assert ordinary.is_reset is False
    assert ordinary.sources_after == 1


def test_the_screen_can_author_a_declaration_that_does_not_exist_yet(
    transfer_sample_setup, tmp_path,
):
    """🔴 THE LAST HOLE IN THE WRITE PATH. The screen could EDIT a declaration and could
    not MAKE one, so a new source had to be typed into `ledger_config.json` by hand -- which
    is exactly what the owner spent two hours doing.

    The cause was one line: every path into the draft machinery resolved its target with
    `index.node(key)`, which refuses an id the snapshot has never seen. Everything else
    already worked -- `_set_path` walks to the section and ASSIGNS the leaf, so it creates
    a missing key, and the only fields the preview and the activation read off the target
    are `config_file` and `bundle_path`.

    The scoring assertion is the second one: the new declaration must land in the RIGHT
    SECTION of a real bundle. A draft that resolved to the wrong place would still create
    happily and fail much later, somewhere that does not name it.
    """
    service = OntologyExplorerService(
        config_root=tmp_path / "absent", draft_root=tmp_path / "drafts",
        setup_loader=lambda root: transfer_sample_setup)
    explorer_router.configure_service(service)
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[require_admin_token_strict] = lambda: None
    app.include_router(explorer_router.router)
    client = TestClient(app)

    _, index, _ = service.active()
    snapshot = index.snapshot_hash
    assert node_key("pack", "brand-new@1") not in index.nodes, "fixture must not have it"

    made = client.post("/admin/ontology-explorer/drafts/new", json={
        "kind": "pack", "canonical_id": "brand-new@1", "base_snapshot_hash": snapshot})
    assert made.status_code == 200, made.text
    draft = made.json()
    assert draft["target_key"] == "pack|brand-new@1"
    assert draft["creates_declaration"] is True

    # 🔴 The path has to reach the wire. `public()` is a WHITELIST, so a field added to the
    # record is invisible until it is named there -- and invisible reads to the screen as
    # absent, not as missing. Measured: the first version answered `null` here.
    assert draft["target_bundle_path"] == ["packs", "brand-new@1"], (
        "the draft must know where it will be written, and say so")

    # It lands in the real bundle at that path: saving an EMPTY pack must be refused by the
    # validator naming this pack, which is only possible if it actually landed there.
    saved = client.put(f"/admin/ontology-explorer/drafts/{draft['draft_id']}", json={
        "expected_revision": 0, "raw": "{}"})
    assert saved.status_code == 200, saved.text
    errors = saved.json()["validation_errors"]
    assert any("brand-new@1" in str(item.get("path", "")) for item in errors), (
        f"the refusal must name the new declaration; got {errors}")


def test_authoring_a_declaration_refuses_the_three_ways_it_can_be_wrong(
    transfer_sample_setup, tmp_path,
):
    """Each refusal is a different mistake, and a shared code would hide which one.

    🔴 `unauthorable_kind` COMES FROM `authorable_bundle_path` -- the same map
    `deletion_plan` reads. So "what this screen can create" and "what it can delete" have
    one author, and the invariant landed on 2026-08-19 holds from the create side for free
    rather than by a second check that could drift.
    """
    service = OntologyExplorerService(
        config_root=tmp_path / "absent", draft_root=tmp_path / "drafts",
        setup_loader=lambda root: transfer_sample_setup)
    explorer_router.configure_service(service)
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[require_admin_token_strict] = lambda: None
    app.include_router(explorer_router.router)
    client = TestClient(app)

    _, index, _ = service.active()
    snapshot = index.snapshot_hash
    # `_refusal` wraps the mapping in HTTPException.detail -- taken from the router, not
    # from memory of it.
    post = lambda kind, cid: client.post(
        "/admin/ontology-explorer/drafts/new",
        json={"kind": kind, "canonical_id": cid, "base_snapshot_hash": snapshot})
    code = lambda response: response.json()["detail"]["code"]

    existing = next(node for node in index.nodes.values() if node.kind == "pack")
    assert code(post("pack", existing.canonical_id)) == "declaration_exists", (
        "creating over a live declaration is an edit wearing a create's clothes")

    for kind in ("verified_join", "table"):
        assert code(post(kind, "brand-new@1")) == "unauthorable_kind", (
            f"{kind} is deletable-or-not by the same map; it must not be creatable here")

    assert post("pack", "twice@1").status_code == 200
    assert code(post("pack", "twice@1")) == "declaration_being_created", (
        "two open drafts on one name means the second activation discards the first")

    stale = client.post("/admin/ontology-explorer/drafts/new", json={
        "kind": "pack", "canonical_id": "other@1", "base_snapshot_hash": "0" * 64})
    assert code(stale) == "stale_base_snapshot"


def test_an_absent_target_is_normal_for_a_create_and_a_conflict_for_an_edit(
    transfer_sample_setup, tmp_path,
):
    """🔴 THE STALENESS RULE INVERTS, and reading the edit rule onto a create reports a
    conflict on EVERY create.

    For an edit, an absent target means somebody deleted what we are editing -- a conflict.
    For a create, absent is the normal state and the entire point; what is a conflict there
    is the target having APPEARED, because somebody else authored the same name while we
    typed and activating would overwrite them.

    Left unsplit, the screen answers "conflict" to every attempt to make something, which
    reads to the operator as "this screen cannot create declarations" -- the defect being
    fixed, restated as a status string.
    """
    from ledger.config_drafts import OntologyDraftStore

    store = OntologyDraftStore(tmp_path / "drafts")
    index = build_explorer_index(transfer_sample_setup)

    created = store.create_new(transfer_sample_setup, index, "pack", "absent@1")
    record = store.get(created["draft_id"])
    assert store.stale_status(record, index) == "stale", (
        "the declaration it is authoring is absent BY DESIGN")

    # Same record, but now something occupies the name: that IS the conflict.
    existing = next(node for node in index.nodes.values() if node.kind == "pack")
    occupied = dict(record, target_key=existing.key)
    assert store.stale_status(occupied, index) == "conflict"

    # And the edit rule is untouched: an edit whose target vanished is still a conflict.
    edit = dict(record, creates_declaration=False, target_key="pack|vanished@1")
    assert store.stale_status(edit, index) == "conflict"


def test_deletion_preview_endpoint_names_the_casualties_and_shows_the_blockage(
    transfer_sample_setup, tmp_path,
):
    """The screen has to render the list, so the API has to carry it.

    A blocked target comes back 200 WITH its reacher rather than as a refusal: an operator
    who gets only a 400 cannot see the list they were asked to confirm, and the whole point
    of this preview is that the casualties are visible before the confirm.

    Served from the sample rather than a copy of the live root, whose `ledger_config.json`
    is hand-edited and gitignored -- `setup_loader` is the seam that makes that possible
    without the service reaching for a file at all.
    """
    service = OntologyExplorerService(
        config_root=tmp_path / "absent", draft_root=tmp_path / "drafts",
        setup_loader=lambda root: transfer_sample_setup)
    explorer_router.configure_service(service)
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[require_admin_token_strict] = lambda: None
    app.include_router(explorer_router.router)
    client = TestClient(app)

    _, index, _ = service.active()
    source = next(
        node.key for node in index.nodes.values() if node.kind == "source_plan")
    profile = node_key("profile", index.nodes[source].raw["profile_id"])

    ok = client.get(
        "/admin/ontology-explorer/deletion-preview", params={"targets": [source]})
    assert ok.status_code == 200
    plan = ok.json()
    assert plan["blocked"] == []
    keys = {row["key"] for row in plan["removed"]}
    assert source in keys and profile in keys
    assert plan["removed_total"] == len(plan["removed"]) > 1
    assert plan["context_token"] == f"active:{index.snapshot_hash}"
    for field in ("removed", "released", "blocked"):
        assert all(row["context_token"] == plan["context_token"]
                   for row in plan[field])

    blocked = client.get(
        "/admin/ontology-explorer/deletion-preview",
        params={"targets": [profile]}).json()
    assert [row["key"] for row in blocked["blocked"]] == [profile]
    assert [row["key"] for row in blocked["blocked"][0]["reached_by"]] == [source]

    # Both together is the operator's next move, and the API must accept the pair.
    pair = client.get(
        "/admin/ontology-explorer/deletion-preview",
        params={"targets": [profile, source]}).json()
    assert pair["blocked"] == []
    assert {row["key"] for row in pair["removed"]} == keys

    stale = client.get(
        "/admin/ontology-explorer/deletion-preview",
        params={"targets": [source], "context_token": "active:" + "0" * 64})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_context"

    empty = client.get("/admin/ontology-explorer/deletion-preview")
    assert empty.status_code == 400
    assert empty.json()["detail"]["code"] == "empty_deletion"


# --------------------------------------------------------------------- authoring plan


def test_derivations_rebuild_by_force_what_the_operator_typed_by_hand(active_setup):
    """The acceptance question: does the screen produce the live artifact with less work?

    Every field the plan calls `derived` with `comparison == "equal"` is deleted from the
    live bundle and put back from the plan alone.  The result must validate.  What this
    measures is not "the code runs" but "these fields had no degrees of freedom", which
    is the entire claim behind removing them from the screen.
    """
    import copy

    from ledger.config_authoring import authoring_plan
    from ledger.setup import live_physical_catalog
    from ledger.setup_bundle import validate_bundle_errors

    catalog = live_physical_catalog()
    original = json.loads(
        (DEFAULT_ONTOLOGY_ROOT / "ledger_config.json").read_text(encoding="utf-8"))
    assert not validate_bundle_errors(original, catalog=catalog)

    reduced = copy.deepcopy(original)
    for profile in reduced["profiles"].values():
        profile.pop("packs", None)
        profile.pop("source", None)
    for mapper in reduced["mappers"].values():
        mapper.pop("emits", None)
        mapper.pop("input_columns", None)
    for pack in reduced["packs"].values():
        for claim in pack["claims"].values():
            claim["emit"]["object"].pop("kind", None)

    plan = authoring_plan(reduced, catalog)
    derived = {row["path"]: row for row in plan["fields"] if row["state"] == "derived"}
    assert derived, "a bundle missing its forced fields must still derive them"

    for path, row in derived.items():
        assert row["ground"], f"{path} filled a value without naming what filled it"
        assert row["ground"]["text"] and row["ground"]["from_paths"]

    rebuilt = copy.deepcopy(reduced)
    for profile_id, profile in rebuilt["profiles"].items():
        profile["packs"] = derived[f"bundle.profiles.{profile_id}.packs"]["value"]
        profile["source"] = derived[f"bundle.profiles.{profile_id}.source"]["value"]
    for mapper_id, mapper in rebuilt["mappers"].items():
        mapper["emits"] = derived[f"bundle.mappers.{mapper_id}.emits"]["value"]
        mapper["input_columns"] = derived[
            f"bundle.mappers.{mapper_id}.input_columns"]["value"]
    for pack_id, pack in rebuilt["packs"].items():
        for claim_id, claim in pack["claims"].items():
            claim["emit"]["object"]["kind"] = derived[
                f"bundle.packs.{pack_id}.claims.{claim_id}.emit.object.kind"]["value"]

    assert not validate_bundle_errors(rebuilt, catalog=catalog)


def test_a_derivation_that_cannot_state_its_ground_refuses_to_fill():
    """The rule that keeps a screen from repeating the grouped-event `basis` defect.

    A quietly chosen default becomes data.  `Field` therefore cannot be constructed in
    the `derived` state without a ground, and this is the assertion that keeps that
    constructor honest rather than decorative.
    """
    from ledger.config_authoring import AuthoringGroundError, Field, Ground

    with pytest.raises(AuthoringGroundError):
        Field(path="bundle.x", step="sources", label="c", state="derived",
              tier="structural", value=["a"])
    with pytest.raises(AuthoringGroundError):
        Field(path="bundle.x", step="sources", label="c", state="derived",
              tier="structural", value=["a"],
              ground=Ground("r", "", ("bundle.y",)))
    with pytest.raises(AuthoringGroundError):
        Field(path="bundle.x", step="sources", label="c", state="derived",
              tier="structural", value=["a"], ground=Ground("r", "fill", ()))
    ok = Field(path="bundle.x", step="sources", label="c", state="derived",
               tier="structural", value=["a"],
               ground=Ground("r", "fill", ("bundle.y",)))
    assert ok.to_mapping()["ground"]["from_paths"] == ["bundle.y"]


def test_a_wider_declaration_is_not_a_conflict_when_the_rule_is_containment():
    """`input_columns` is a derived MINIMUM; calling a legal wider one red is a false red.

    Measured on the live root: `lot-event-role@1` declares ten input columns and the
    profile binds four, because a custom mapper reads columns no binding names.  An
    equality comparison painted that legal declaration as a defect.
    """
    from ledger.config_authoring import Field, Ground

    ground = Ground("r", "fill", ("bundle.y",))
    wider = Field(path="p", step="implementations", label="input_columns",
                  state="derived", tier="derivation", value=["a", "b"],
                  declared=["a", "b", "c"], ground=ground, comparison="superset")
    short = Field(path="p", step="implementations", label="input_columns",
                  state="derived", tier="derivation", value=["a", "b"],
                  declared=["a"], ground=ground, comparison="superset")
    exact = Field(path="p", step="profiles", label="packs", state="derived",
                  tier="structural", value=["a"], declared=["a", "b"], ground=ground)
    assert not wider.conflicts
    assert short.conflicts
    assert exact.conflicts


def test_authoring_answers_on_a_blank_root_where_the_compiled_view_cannot(tmp_path):
    """The from-scratch entry: no config file at all must name the absence, not 500."""
    from ledger.config_authoring import closed_lists

    empty = tmp_path / "ontology"
    empty.mkdir()
    service = OntologyExplorerService(
        config_root=empty, draft_root=tmp_path / "drafts")
    plan = service.authoring()
    assert plan["config_source"]["state"] == "absent"
    assert plan["config_source"]["file"].endswith("ledger_config.json")
    # Members, not a magnitude: `6` here would become a lie the day a step is added,
    # and it would lie silently. The step list is the payload's own.
    assert {step["status"] for step in plan["steps"]} == {"empty"}
    assert [step["id"] for step in plan["steps"]] == [
        step["id"] for step in closed_lists()["steps"]]
    # The deficits are NAMED, not implied by an empty panel.
    named = {issue["path"] for issue in plan["unattached_refusals"]}
    assert "bundle.entities" in named and "bundle.sources" in named

    (empty / "ledger_config.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(ConfigExplorerError) as broken:
        service.authoring()
    assert broken.value.code == "unreadable_config"


def test_closed_lists_come_from_the_validators_own_constants():
    """A list the screen offers must be the list the validator enforces, not a copy."""
    from ledger.config_authoring import closed_lists
    from ledger import setup_bundle

    lists = closed_lists()
    assert set(lists["object_kind"]) == set(setup_bundle._OBJECT_KINDS)
    assert set(lists["role_kind"]) == set(setup_bundle._ROLE_KINDS)
    assert set(lists["source_unit"]) == set(setup_bundle._SOURCE_UNITS)
    assert set(lists["mapper_unit"]) == set(setup_bundle._MAPPER_UNITS)
    assert set(lists["occurred_at_basis"]) == set(setup_bundle._OCCURRED_AT_BASES)
    assert set(lists["approval_status"]) == set(setup_bundle._APPROVAL_STATUSES)
    assert set(lists["binding_origin"]) == set(setup_bundle._BINDING_ORIGINS)
    # Steps ship with their labels so the step bar carries no list of its own.
    assert [step["id"] for step in lists["steps"]] == [
        "entities", "vocabulary", "packs", "implementations", "profiles", "sources"]
    assert all(step["label"] for step in lists["steps"])


def test_every_deficit_lands_on_a_field_rather_than_a_loose_error_list(active_setup):
    """Holes the operator actually made on 2026-08-18, and where the screen puts them."""
    from ledger.config_authoring import authoring_plan
    from ledger.setup import live_physical_catalog

    catalog = live_physical_catalog()
    bundle = json.loads(
        (DEFAULT_ONTOLOGY_ROOT / "ledger_config.json").read_text(encoding="utf-8"))
    del bundle["profiles"]["dt-job@1"]["mappings"][1]["bind"]["count"]
    del (bundle["packs"]["lot-lineage@1"]["claims"]["membership"]
         ["emit"]["object"]["qualifiers"]["slot"])

    plan = authoring_plan(bundle, catalog)
    by_path = {row["path"]: row for row in plan["fields"]}
    role = by_path["bundle.profiles.dt-job@1.mappings[1].bind.count"]
    assert role["state"] == "missing"
    assert [item["code"] for item in role["refusals"]] == ["missing_required_role"]
    qualifier = by_path[
        "bundle.packs.lot-lineage@1.claims.membership.emit.object.qualifiers.slot"]
    assert qualifier["state"] == "missing"
    assert "missing_required_payload" in [
        item["code"] for item in qualifier["refusals"]]
    # The candidate is offered ALREADY SPELLED, so the `?` is never typed by hand.
    assert "$slot" in qualifier["candidates"]
    assert not plan["unattached_refusals"], plan["unattached_refusals"]
    blocked = {step["id"] for step in plan["steps"] if step["status"] == "blocked"}
    assert blocked == {"packs", "profiles"}


def test_column_candidates_are_three_universes_and_not_one(active_setup):
    """A preparer-made column is legal in `identity` and refused in `order_by`."""
    from ledger.config_authoring import authoring_plan
    from ledger.setup import live_physical_catalog

    catalog = live_physical_catalog()
    bundle = json.loads(
        (DEFAULT_ONTOLOGY_ROOT / "ledger_config.json").read_text(encoding="utf-8"))
    plan = authoring_plan(bundle, catalog)
    by_path = {row["path"]: row for row in plan["fields"]}
    identity = by_path["bundle.sources.lot_event.driver.identity"]
    ordering = by_path["bundle.sources.lot_event.driver.order_by"]
    assert identity["universe"] == "PREPARED"
    assert ordering["universe"] == "RELATION"
    made = set(bundle["source_preparers"]["lot-event-live-frame@1"]["output_columns"])
    assert made & set(identity["candidates"]), "preparer output must be offered here"
    assert not (made & set(ordering["candidates"])), "and never offered here"


def test_remaining_counts_what_a_person_still_has_to_decide():
    """🔴 `missing` AND `unanswered` ARE NOT THE SAME EMPTY, and only the first is work.

    `config_authoring` spells them `state="missing" if required else "unanswered"`, so
    `unanswered` means OPTIONAL AND ABSENT -- a question nobody is obliged to answer, and
    an absence that is itself a decision ("not using it").

    Measured on the live root, which is complete and valid: counting `unanswered` reports
    **1 remaining** (`source_preparers.direct-join@1.output_columns`), i.e. a finished
    setup telling the operator there is work left on the first screen they see. An
    indicator that cries wolf once gets ignored forever after, which is worse than no
    indicator -- it still costs a glance.

    The last case is the one a state check alone would miss: a field with a VALUE that
    something refused is still remaining, because the value is one somebody must revisit.
    """
    from ledger.config_authoring import is_remaining

    assert is_remaining({"state": "missing"}) is True
    assert is_remaining({"state": "unanswered"}) is False, (
        "optional-and-absent is a decision already made, not work outstanding")
    assert is_remaining({"state": "answered"}) is False
    assert is_remaining({"state": "derived"}) is False

    # A derived field is never a person's work even when it is in conflict -- the fix is
    # at the declaration it came from, and counting it would send them to the wrong screen.
    assert is_remaining({"state": "derived", "conflicts": True}) is False
    assert is_remaining({"state": "derived", "refusals": [{"code": "x"}]}) is False

    assert is_remaining({"state": "answered", "refusals": [{"code": "x"}]}) is True
    assert is_remaining({"state": "answered", "conflicts": True}) is True


def test_a_complete_config_reports_no_remaining_work_and_a_broken_one_reports_where(
    transfer_sample_setup,
):
    """The sanity check that decides whether the predicate is right at all.

    A valid, fully declared setup must read **0 남음 in every layer**; a declaration
    showing work outstanding means the predicate is wrong, not the config. Then removing
    ONE required value must move **exactly the layer that owns it** -- a count that moves
    everywhere is measuring the file rather than the decision.
    """
    import copy
    from ledger.config_authoring import authoring_plan

    bundle = copy.deepcopy(transfer_sample_setup.bundle.to_mapping())
    catalog = transfer_sample_setup.catalog

    before = authoring_plan(bundle, catalog)
    assert all(step["remaining"] == 0 for step in before["steps"]), (
        f"a complete setup must have nothing outstanding: "
        f"{[(s['id'], s['remaining']) for s in before['steps']]}")

    broken = copy.deepcopy(bundle)
    victim = next(name for name, source in broken["sources"].items()
                  if isinstance(source, dict) and "profile_id" in source)
    del broken["sources"][victim]["profile_id"]

    after = authoring_plan(broken, catalog)
    moved = [step["id"] for step in after["steps"] if step["remaining"]]
    assert moved == ["sources"], f"expected only the sources layer to move, got {moved}"
    assert sum(step["remaining"] for step in after["steps"]) == 1


def test_a_setup_can_be_started_from_nothing(tmp_path, monkeypatch):
    """🔴 THE BLANK-ROOT TRIP. Until this existed the screen could not be used from an empty
    root at all: every authoring path needs a config to read, so the FIRST declaration had
    to be typed into a text editor by hand. That is the trip this removes.

    The scoring assertion is not that a file appeared -- it is that the file appeared and
    VALIDATES, because a skeleton that does not is a file handed back to the operator to
    repair, which is the thing being removed. The counter-check lives in
    `test_the_starting_file_is_the_smallest_one_that_validates`.
    """
    from ledger.config_explorer_service import OntologyExplorerService
    from ledger.setup_bundle import CONFIG_FILENAME, validate_bundle_errors

    root = tmp_path / "ontology"
    service = OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts",
        catalog_loader=lambda: {})
    assert not (root / CONFIG_FILENAME).exists()

    result = service.bootstrap_config()
    written = root / CONFIG_FILENAME
    assert written.is_file(), "the offer has to actually produce the file"

    bundle = json.loads(written.read_text(encoding="utf-8"))
    # `validate_bundle_errors` answers with a TUPLE; asserting `== []` compares the
    # shape rather than the emptiness and fails on a green result.
    assert not validate_bundle_errors(bundle, catalog={}), (
        "a starting file that does not validate is a file handed back to be repaired")
    assert bundle["setup_version"] == 3
    assert set(result["sections"]) <= set(bundle), "every section it names must be present"

    # And the plan reads it afterwards, which is what the operator sees next.
    plan = service.authoring()
    assert plan["config_source"]["state"] == "present"


def test_bootstrap_never_overwrites_a_file_that_merely_fails_to_parse(tmp_path):
    """🔴 ABSENT AND UNREADABLE ARE NOT THE SAME CASE, and conflating them is destructive.

    A config that will not parse is almost never an absence -- it is a file somebody spent
    hours on with one bad comma in it. A screen that "helpfully" writes a skeleton over it
    destroys that work and looks like a feature while doing so.

    So the guard is `exists()`, NOT "does it parse". This test is the one that would catch
    a future refactor rewriting the check as "load it; if that fails, treat as absent",
    which reads reasonable and is the destructive version.
    """
    from ledger.config_explorer_service import OntologyExplorerService
    from ledger.setup_bundle import CONFIG_FILENAME

    root = tmp_path / "ontology"
    root.mkdir(parents=True)
    hand_written = '{"setup_version": 3, "vocabulary": {},,}'      # one bad comma
    (root / CONFIG_FILENAME).write_text(hand_written, encoding="utf-8")

    service = OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts", catalog_loader=lambda: {})

    with pytest.raises(ConfigExplorerError) as refused:
        service.bootstrap_config()
    assert refused.value.to_mapping()["code"] == "config_already_present"
    assert (root / CONFIG_FILENAME).read_text(encoding="utf-8") == hand_written, (
        "🔴 THE OPERATOR'S FILE MUST BE BYTE-IDENTICAL AFTER THE REFUSAL")

    # And the operator is told what is wrong with it rather than left guessing.
    with pytest.raises(ConfigExplorerError) as unreadable:
        service.authoring()
    assert unreadable.value.to_mapping()["code"] == "unreadable_config"

    # A valid file is refused for the same reason, by the same code.
    (root / CONFIG_FILENAME).write_text('{"setup_version": 3}', encoding="utf-8")
    with pytest.raises(ConfigExplorerError) as present:
        service.bootstrap_config()
    assert present.value.to_mapping()["code"] == "config_already_present"


def test_the_starting_file_is_the_smallest_one_that_validates(tmp_path):
    """The skeleton is measured against the validator, not composed by hand.

    Two halves, and the second is what stops the first being vacuous: the written object
    validates, AND an empty object does not. Without the counter-check, a validator that
    accepted anything would make this test pass while the screen wrote garbage.

    Nothing extra is written either. Every additional field would be a guess, and a guess
    the validator later refuses turns the starting file into a repair job.
    """
    from ledger.config_explorer_service import OntologyExplorerService
    from ledger.setup_bundle import (
        CONFIG_FILENAME, LOGICAL_SECTIONS, validate_bundle_errors)

    root = tmp_path / "ontology"
    service = OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts", catalog_loader=lambda: {})
    service.bootstrap_config()
    bundle = json.loads((root / CONFIG_FILENAME).read_text(encoding="utf-8"))

    assert not validate_bundle_errors(bundle, catalog={})
    assert validate_bundle_errors({}, catalog={}), (
        "if an empty object also validated, the assertion above would prove nothing")
    assert set(bundle) == {"setup_version", *LOGICAL_SECTIONS}, (
        "anything beyond the required keys is a guess the validator may refuse")
    assert all(bundle[name] == {} for name in LOGICAL_SECTIONS)
