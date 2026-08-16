"""Composite CHIP cardinality and reverse-trace contract."""
from datetime import datetime, timezone
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import ledger_composition  # noqa: E402
import seed_syn_composite_chip as fixture  # noqa: E402


def test_fixture_is_many_core_many_dt_many_layer_and_continuous():
    atoms = fixture.build_atoms()
    summary = fixture.validate(atoms)
    assert set(summary) == set(fixture.FINAL_CHIPS)
    for row in summary.values():
        assert row["components"] == 12
        assert len({lot for lot, _slot in row["dt"]}) >= 4
        assert len(row["types"]) >= 3
    metas = [a.object_payload["component"] for a in atoms]
    assert {m["state"] for m in metas} >= {"resolved", "candidate", "unresolvable"}
    paths = {}
    for atom in atoms:
        paths.setdefault(atom.molecule_ref, []).append(atom)
    assert any(len(events) > 2 for events in paths.values()), "no DT-A -> DT-B path"


def test_reverse_contract_preserves_every_dt_and_component(monkeypatch):
    atoms = [a for a in fixture.build_atoms()
             if a.object_payload["component"]["final_chip_id"] == fixture.FINAL_CHIPS[0]]
    movement_rows = [(f"id-{i}", a.subject_keys, a.object_payload, a.occurred_at,
                      a.source_raw_ref) for i, a in enumerate(atoms)]
    process_rows = []
    monkeypatch.setattr(ledger_composition, "relation_exists", lambda *_: True)
    calls = iter((movement_rows, process_rows))
    monkeypatch.setattr(ledger_composition, "_fetch", lambda *_args, **_kw: next(calls))

    body = ledger_composition.composition(
        object(), fixture.FINAL_CHIPS[0], now=datetime(2026, 8, 15,
                                                       tzinfo=timezone.utc))
    assert body["state"] == "ready"
    assert body["summary"]["component_count"] == 12
    assert body["summary"]["dt_collection_count"] >= 12
    assert len(body["summary"]["core_types"]) == 3
    assert len({c["entity_id"] for c in body["components"]}) == 12
    assert all(isinstance(c["transfer_events"], list) for c in body["components"])
    assert any(len(c["dt_collections"]) > 1 for c in body["components"])
    # The summary is a set of every participating collection, not one representative DT.
    union = {dt["entity_id"] for c in body["components"] for dt in c["dt_collections"]}
    assert set(body["summary"]["dt_collection_ids"]) == union


def test_missing_component_identity_is_not_merged(monkeypatch):
    stamp = datetime(2026, 8, 14, tzinfo=timezone.utc)
    payload = {"from": fixture.place("wafer_grid", {"wafer": "SYN-X"}, {"x": 1}),
               "to": fixture.place("dt_slot", {"dt_lot": "SYN-D", "dt_slot": "1"},
                                   {"x": 2}),
               "sequence": 0, "component": {"final_chip_id": "SYN-C"}}
    movement = [("a", {"wafer": "SYN-X"}, payload, stamp, "r1"),
                ("b", {"wafer": "SYN-X"}, payload, stamp, "r2")]
    monkeypatch.setattr(ledger_composition, "relation_exists", lambda *_: True)
    calls = iter((movement, []))
    monkeypatch.setattr(ledger_composition, "_fetch", lambda *_args, **_kw: next(calls))
    body = ledger_composition.composition(object(), "SYN-C", now=stamp)
    assert len(body["components"]) == 2
    assert {c["resolution_state"] for c in body["components"]} == {"unresolvable"}


def test_process_events_lineage_and_final_wafer_are_evidence_complete(monkeypatch):
    stamp = datetime(2026, 8, 14, tzinfo=timezone.utc)
    component = {
        "final_chip_id": "SYN-CX-CHIP-001", "component_id": "CX-L01",
        "core_type": "HBM", "core_branch": "B", "role": "stack_layer_01",
        "core_lot": "SYN-CX-HBM-MRG", "core_slot": "02", "bond_layer": 1,
        "state": "resolved",
    }
    movement_payload = {
        "from": fixture.place("dt_slot", {"dt_lot": "SYN-CX-DT-01",
                                            "dt_slot": "03"}, {}),
        "to": fixture.place("bond_layer", {"final_chip_id": "SYN-CX-CHIP-001",
                                             "bond_wafer": "SYN-CX-FW-001",
                                             "layer": 1}, {}),
        "sequence": 2, "component": component,
    }
    movement = [("move-1", {"wafer": "SYN-CX-HBM-B-02"}, movement_payload,
                 stamp, "transfer-ref")]
    process_payload = {
        "step": "BOND_PREP", "step_family": "core_fabrication",
        "eqp": "SYN-CX-EQP-2", "recipe": {"id": "R-BOND", "rev": "1"},
        "params_actual": {"plasma_power_W": 505, "enabled": False,
                          "nullable_reading": None},
    }
    lineage_payloads = [
        {"__record_kind": "lineage", "predicate": "has_wafer",
         "subject_keys": {"lot": "SYN-CX-HBM-MRG"},
         "object_payload": {"type": "Wafer", "keys": {"wafer": "SYN-CX-HBM-B-02"}},
         "depth": 0, "path": ["SYN-CX-HBM-MRG"]},
        {"__record_kind": "lineage", "predicate": "derived_from",
         "subject_keys": {"lot": "SYN-CX-HBM-MRG"},
         "object_payload": {"type": "Lot", "keys": {"lot": "SYN-CX-HBM-B-RWK"}},
         "depth": 1, "path": ["SYN-CX-HBM-MRG", "SYN-CX-HBM-B-RWK"]},
    ]
    process = [("proc-1", "SYN-CX-HBM-B-02", process_payload, stamp,
                "process-ref")]
    process.extend((f"lin-{i}", "SYN-CX-HBM-B-02", payload, stamp,
                    f"lineage-ref-{i}") for i, payload in enumerate(lineage_payloads))
    monkeypatch.setattr(ledger_composition, "relation_exists", lambda *_: True)
    calls = iter((movement, process))
    monkeypatch.setattr(ledger_composition, "_fetch",
                        lambda *_args, **_kw: next(calls))

    body = ledger_composition.composition(object(), "SYN-CX-CHIP-001", now=stamp)
    core = body["components"][0]["core"]
    assert core["branch"] == "B"
    assert core["lineage"]["state"] == "resolved"
    assert [event["predicate"] for event in core["lineage"]["events"]] == [
        "has_wafer", "derived_from"]
    upstream = body["components"][0]["upstream_process"]
    assert upstream["evidence_ids"][0]["step"] == "BOND_PREP"
    event = upstream["events"][0]
    assert event["recipe"] == {"id": "R-BOND", "rev": "1"}
    assert event["knobs"] == {"actual": process_payload["params_actual"]}
    assert event["parameters"] == [{"source": "actual",
                                     "values": process_payload["params_actual"]}]
    assert "setpoint" not in event["knobs"]
    assert "params_setpoint" not in event["claims_present"]
    assert "params_actual" in event["claims_present"]
    assert event["payload"] == process_payload
    assert body["final_subject_resolution"]["state"] == "resolved"
    assert body["final_subject_resolution"]["wafer"]["wafer"] == "SYN-CX-FW-001"


def test_final_wafer_resolution_preserves_conflicting_candidates(monkeypatch):
    stamp = datetime(2026, 8, 14, tzinfo=timezone.utc)
    rows = []
    for index, wafer in enumerate(("SYN-FW-A", "SYN-FW-B")):
        payload = {
            "from": fixture.place("dt_slot", {"dt_lot": "SYN-DT",
                                                "dt_slot": str(index)}, {}),
            "to": fixture.place("bond_layer", {"final_chip_id": "SYN-C",
                                                 "bond_wafer": wafer,
                                                 "layer": index + 1}, {}),
            "sequence": 1,
            "component": {"final_chip_id": "SYN-C", "component_id": f"C-{index}"},
        }
        rows.append((f"m-{index}", {"wafer": f"CORE-{index}"}, payload,
                     stamp, f"ref-{index}"))
    monkeypatch.setattr(ledger_composition, "relation_exists", lambda *_: True)
    calls = iter((rows, []))
    monkeypatch.setattr(ledger_composition, "_fetch",
                        lambda *_args, **_kw: next(calls))
    body = ledger_composition.composition(object(), "SYN-C", now=stamp)
    assert body["final_subject_resolution"]["state"] == "contested"
    assert {row["wafer"] for row in body["final_subject_resolution"]["candidates"]} == {
        "SYN-FW-A", "SYN-FW-B"}
