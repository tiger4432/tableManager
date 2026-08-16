from datetime import datetime, timezone
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ledger_explorer
import ledger_trace


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def claim(atom_id, subject, predicate, target_type=None, target_keys=None,
          supersedes=None):
    payload = None
    kind = None
    if target_type:
        kind = "entity_ref"
        payload = {"type": target_type, "keys": target_keys, "qualifiers": {}}
    return ledger_trace.Claim(
        id=atom_id, subject_type="Lot", subject_keys={"lot": subject},
        predicate=predicate, object_kind=kind, object_payload=payload or {},
        occurred_at=NOW, source_who="fixture", source_translator_ver="1",
        source_raw_ref=atom_id, supersedes=supersedes)


def fixture():
    return [
        claim("r0", "MERGED", "register"),
        claim("e1", "MERGED", "derived_from", "Lot", {"lot": "BRANCH-A"}),
        claim("e2", "MERGED", "derived_from", "Lot", {"lot": "BRANCH-B"}),
        claim("r1", "BRANCH-A", "register"),
        claim("e3", "BRANCH-A", "derived_from", "Lot", {"lot": "ROOT"}),
        claim("w1", "BRANCH-A", "has_wafer", "Wafer", {"wafer": "WF-01"}),
        claim("r2", "BRANCH-B", "register"),
        claim("e4", "BRANCH-B", "derived_from", "Lot", {"lot": "ROOT"}),
        claim("r3", "ROOT", "register"),
    ]


def test_branching_neighbourhood_is_not_resolved_to_one_winner():
    body = ledger_explorer.explore(
        "MERGED", ledger_trace.InMemoryClaimLookup(fixture()), hops=20)
    assert body["state"] == "ready"
    assert body["walk"]["hops_requested"] == 20
    parents = {e["target"] for e in body["edges"]
               if e["predicate"] == "derived_from"
               and e["source"] == body["seed"]["id"]}
    assert len(parents) == 2
    assert {n["label"] for n in body["nodes"]} >= {
        "MERGED", "BRANCH-A", "BRANCH-B", "ROOT", "WF-01"}


def test_caps_are_explicit_and_keep_the_seed():
    claims = fixture()
    for index in range(12):
        leaf = f"LEAF-{index:02d}"
        claims.append(claim(f"x{index}", "MERGED", "derived_from",
                            "Lot", {"lot": leaf}))
        claims.append(claim(f"xr{index}", leaf, "register"))
    body = ledger_explorer.explore(
        "MERGED", ledger_trace.InMemoryClaimLookup(claims),
        hops=20, node_limit=10, edge_limit=20)
    assert body["truncated"]["nodes"] is True
    assert len(body["nodes"]) == 10  # public floor prevents a misleading tiny graph
    assert body["nodes"][0]["id"] == body["seed"]["id"]


def test_unknown_lot_is_a_named_empty_answer():
    body = ledger_explorer.explore(
        "MISSING", ledger_trace.InMemoryClaimLookup(fixture()), hops=20)
    assert body["state"] == "empty"
    assert len(body["nodes"]) == 1
    assert body["edges"] == []
    assert "걷기 가능한" in body["message"]


def test_entity_ids_are_order_independent_and_opaque():
    a = ledger_explorer.entity_id("WaferLeg", {"wafer": "W1", "bonding_leg": "L"})
    b = ledger_explorer.entity_id("WaferLeg", {"bonding_leg": "L", "wafer": "W1"})
    assert a == b
    assert a.startswith("ledger-entity:v1:")
