"""Typed selection resolution and evidence-only group comparison."""
from datetime import datetime, timezone
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from ledger_api import ledger_selection  # noqa: E402
from ledger_api import ledger_identity  # noqa: E402
import ledger_trace_router  # noqa: E402
import seed_syn_complex_composite as fixture  # noqa: E402


def _rows_for(chips):
    transfers = [a for a in fixture.transfer_atoms()
                 if a.object_payload["component"]["final_chip_id"] in chips]
    candidate = []
    for index, atom in enumerate(transfers):
        target = atom.object_payload["to"]
        if target["type"] != "bond_layer":
            continue
        candidate.append((target["keys"]["base_wafer_id"],
                          target["keys"]["bonding_leg"], f"candidate-{index}",
                          atom.subject_keys["wafer"],
                          atom.object_payload["component"]["final_chip_id"],
                          atom.object_payload["component"]["component_id"],
                          f"assignment-{index}"))
    paths = [(f"path-{index}", atom.subject_keys["wafer"], atom.object_payload,
              atom.occurred_at, atom.source_raw_ref)
             for index, atom in enumerate(transfers)]
    used_wafers = {atom.subject_keys["wafer"] for atom in transfers}
    process = [(f"process-{index}", atom.subject_keys["wafer"], atom.object_payload,
                atom.occurred_at, atom.source_raw_ref)
               for index, atom in enumerate(fixture.process_atoms())
               if atom.subject_keys["wafer"] in used_wafers]
    analysis_process = [(f"analysis-process-{index}", atom.subject_keys["wafer"],
                         atom.object_payload["bonding_leg"], atom.object_payload,
                         atom.occurred_at, atom.source_raw_ref)
                        for index, atom in enumerate(fixture.bonding_leg_process_atoms())
                        if (atom.subject_keys["wafer"], atom.object_payload["bonding_leg"])
                        in {(fixture.aggregation_unit(chip)["wafer"],
                             fixture.aggregation_unit(chip)["bonding_leg"])
                            for chip in chips}]
    return candidate, paths, process, analysis_process


def _measurement_rows_for(chips):
    transfers = [a for a in fixture.transfer_atoms()
                 if a.object_payload["component"]["final_chip_id"] in chips]
    used_wafers = {atom.subject_keys["wafer"] for atom in transfers}
    return [(f"measurement-{index}", atom.subject_keys["wafer"], atom.object_payload,
             atom.occurred_at, atom.source_raw_ref)
            for index, atom in enumerate(fixture.measurement_atoms())
            if atom.subject_keys["wafer"] in used_wafers]


def test_route_is_additive_and_post():
    routes = {(route.path, next(iter(route.methods or ()), None))
              for route in ledger_trace_router.router.routes}
    assert ("/api/ledger/selection/resolve", "POST") in routes


def test_noncanonical_experiment_unit_id_is_refused_as_422_contract():
    try:
        ledger_selection._normalize({
            "selection": [{"kind": "entity_set",
                           "selector": {"ids": [ledger_identity.MARK_PREFIX + "broken"]}}]})
    except ledger_selection.SelectionRequestError as exc:
        assert exc.detail["reason"] == "bad_analysis_mark"
    else:
        raise AssertionError("malformed canonical mark must not reach SQL")


def test_syn_cx_final_wafer_marks_resolve_all_paths_and_group_signal(monkeypatch):
    defect, reference = fixture.UI_PRESETS["hero_defect"], fixture.UI_PRESETS["hero_reference"]
    candidate, paths, process, analysis_process = _rows_for({defect, reference})
    measurements = _measurement_rows_for({defect, reference})
    monkeypatch.setattr(ledger_selection, "relation_exists", lambda *_: True)
    metadata = {(row["target_table"], row["map_id"]): row["grid_metadata"]
                for row in fixture.map_metadata_rows()}
    def fetch(_connection, sql, params):
        if "WITH marks AS" in sql:
            return candidate
        if "object_payload->'component'->>'final_chip_id' = ANY" in sql:
            return paths
        if "predicate = 'measured'" in sql:
            return [] if "FROM units u JOIN ledger_events e" in sql else measurements
        if "predicate = 'processed_with'" in sql and "FROM units u JOIN ledger_events e" in sql:
            return analysis_process
        if "predicate = 'processed_with'" in sql:
            return process
        if "SELECT DISTINCT b.base_id, bm.leg::text, concat_ws" in sql:
            return [(fixture.final_wafer(defect), fixture.aggregation_unit(defect)["bonding_leg"],
                     "SYN-CX-BOND-DEFECT_01",
                     "SYN-CX-DT-02_02", "SYN-CX-HBM-MRG_22"),
                    (fixture.final_wafer(reference),
                     fixture.aggregation_unit(reference)["bonding_leg"],
                     "SYN-CX-BOND-REFERENCE_01",
                     "SYN-CX-DT-01_01", "SYN-CX-LOGIC-MRG_11")]
        if "SELECT r.stage" in sql:
            requested = __import__("json").loads(params["requests"])
            return [(r["stage"], r["table_name"], r["map_id"], r["component_id"],
                     r.get("subject_wafer"), r.get("subject_leg"),
                     r.get("selection_id"),
                     metadata[(r["table_name"], r["map_id"])])
                    for r in requested if (r["table_name"], r["map_id"]) in metadata]
        if "JOIN valid_die_ref" in sql:
            return [(fixture.VALID_DIE_MAP_ID, 2, 2)]
        if "hits AS" in sql:
            unit = fixture.aggregation_unit(defect)
            return [("bonding_log", unit["wafer"], unit["bonding_leg"],
                     "SYN-CX-BOND-DEFECT_01", 7, 7, "RUN-1"),
                    ("dt_map", unit["wafer"], unit["bonding_leg"],
                     "SYN-CX-DT-02_02", 7, 7, "RUN-1"),
                    ("core_wafer_map", unit["wafer"], unit["bonding_leg"],
                     "SYN-CX-HBM-MRG_22", 7, 7, "RUN-1")]
        if "SELECT r.map_id" in sql:
            map_id = params["map_ids"][0]
            if "JOIN bonding_log" in sql:
                return [(map_id, 2, 2, "1", "DT", "SYN-CX-DT-01", "01")]
            if "JOIN dt_map" in sql:
                return [(map_id, 2, 2, "1", "Wafer", "SYN-CX-CW-HBM-B-01", None)]
            return [(map_id, 2, 2, "1", "Wafer", "SYN-CX-CW-LOGIC-A-01", None)]
        return []
    monkeypatch.setattr(ledger_selection, "_fetch", fetch)
    payload = {
        "finding_kind": "void", "window": "365d",
        "selection": [
            {"mark_id": "defect", "group_id": "A", "kind": "entity_set",
             "identity": ledger_identity.identity(**fixture.aggregation_unit(defect))},
            {"mark_id": "reference", "group_id": "B", "kind": "entity_set",
             "selector": {"subjects": [ledger_identity.identity(
                 **fixture.aggregation_unit(reference))]}},
        ],
    }
    body = ledger_selection.resolve(object(), payload,
                                     now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert body["resolved_final_chip_ids"] == sorted([defect, reference])
    assert all(row["state"] == "resolved" for row in body["selections"])
    units = [row["aggregation_units"][0] for row in body["selections"]]
    assert units[0]["keys"]["wafer"] == units[1]["keys"]["wafer"]
    assert units[0]["context"]["bonding_leg"] != units[1]["context"]["bonding_leg"]
    assert [row["final_chip_ids"] for row in body["selections"]] == [[defect], [reference]]
    assert all(len(row["paths"]) >= 10 for row in body["selections"])
    assert all(any(path["dt_collections"] for path in row["paths"])
               for row in body["selections"])
    assert all(row["traceability"]["core"]["state"] == "ready"
               for row in body["selections"])
    stages = {row["stage"] for selection in body["selections"]
              for row in selection["maps"]}
    assert stages >= {"bond", "dt", "core"}
    assert {row["stage"] for row in body["maps"]} >= {"bond", "dt", "core"}
    for selection in body["selections"]:
        identity = selection["aggregation_units"][0]
        unit = {"wafer": identity["keys"]["wafer"],
                "bonding_leg": identity["context"]["bonding_leg"]}
        scoped = [row for row in selection["maps"] if row.get("subject_wafer")]
        assert scoped
        assert all((row["subject_wafer"], row["subject_leg"]) ==
                   (unit["wafer"], unit["bonding_leg"]) for row in scoped)
        assert all(row["subject_identity"]["type"] == "Wafer"
                   and row["subject_identity"]["keys"] == {"wafer": unit["wafer"]}
                   and row["subject_identity"]["context"]["bonding_leg"] == unit["bonding_leg"]
                   and row["wafer_mark_key"] == row["subject_identity"]["mark_key"]
                   for row in scoped)
    assert all("supply_material" in row["layers"]
               for selection in body["selections"] for row in selection["maps"])
    assert any(row["stage"] == "core"
               and row["layers"]["valid_die"]["state"] == "ready"
               and row["layers"]["defect"]["state"] == "ready"
               for selection in body["selections"] for row in selection["maps"])
    signatures = [row for row in body["comparison"]["facets"]["process"]
                  if row["signature"].get("core_type") == "HBM"
                  and row["signature"].get("core_branch") == "B"
                  and row["signature"].get("step") == "BOND_PREP"
                  and row["signature"].get("recipe") ==
                      fixture.process_recipe("HBM", "B", "BOND_PREP")]
    assert signatures
    signal = signatures[0]
    frequencies = {row["group_id"]: row["frequency"] for row in signal["groups"]}
    assert frequencies["A"] > 0 and frequencies["B"] == 0
    assert signal["surprise"]["score"] > 0
    assert signal["surprise"]["effect_kind"] == "smoothed_log_odds_difference"
    assert signal["surprise"]["smoothing"] == 0.5
    assert signal["surprise"]["raw_effect"] is not None
    assert signal["surprise"]["binding_state"] == "unknown"
    assert signal["surprise"]["reason"] == "categorical_process_has_no_numeric_binding"
    defect_mark = ledger_identity.encode_mark(**fixture.aggregation_unit(defect))
    assert signal["wafer_mark_keys"] == [defect_mark]
    signal_groups = {row["group_id"]: row for row in signal["groups"]}
    assert signal_groups["A"]["wafer_mark_keys"] == [
        defect_mark]
    assert signal_groups["B"]["wafer_mark_keys"] == []
    assert signal["evidence_ids"]
    assert signal_groups["A"]["evidence_ids"]
    assert all(row["wafer_mark_keys"] for row in body["comparison"]["context"])
    assert all(row["evidence_ids"] for row in body["comparison"]["context"])
    measurement = [row for row in body["comparison"]["facets"]["measurement"]
                   if row.get("signature", {}).get("metric") ==
                      "post_cmp_film_thickness"
                   and row.get("signature", {}).get("step") == "CMP_BULK_02"]
    assert measurement and measurement[0]["predicate"] == "measured"
    measurement_groups = {row["group_id"]: row for row in measurement[0]["groups"]}
    assert measurement_groups["A"]["values"]
    assert measurement_groups["B"]["values"]
    assert measurement[0]["evidence_ids"]
    assert measurement[0]["wafer_mark_keys"]
    assert body["comparison"]["sequence"]["state"] == "ready"
    assert body["comparison"]["sequence"]["differences"]
    assert all(row["wafer_mark_keys"]
               for row in body["comparison"]["sequence"]["clusters"])
    assert all(row["wafer_mark_keys"]
               for row in body["comparison"]["sequence"]["differences"]
               if row["kind"] != "record_absent")
    assert body["comparison"]["surprise"]["state"] in {"ready", "unknown"}
    unit_process = [row for row in body["comparison"]["facets"]["process"]
                     if row["signature"].get("subject_grain") == "bonding_experiment_unit"
                     and row["signature"].get("step") == "FINAL_BOND"]
    assert unit_process
    assert "core_type" not in unit_process[0]["signature"]
    assert "core_branch" not in unit_process[0]["signature"]
    assert all(group["denominator"] == 1 for group in unit_process[0]["groups"])
    assert body["comparison"]["aggregation_unit_sequence"]["coverage"] == {
        "resolved": 2, "total": 2}


def test_map_cell_without_declared_frame_is_not_guessed(monkeypatch):
    monkeypatch.setattr(ledger_selection, "relation_exists", lambda *_: True)
    monkeypatch.setattr(ledger_selection, "_fetch", lambda *_a, **_k: [])
    body = ledger_selection.resolve(object(), {
        "selection": [{"mark_id": "map-1", "kind": "map_cells",
                       "selector": {"map_id": "SYN-MAP", "cells": [{"x": 1, "y": 2}],
                                    "subjects": [{"type": "Wafer",
                                                  "keys": {"wafer": "SYN-WF"}}]}}]},
        now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert body["selections"][0]["state"] == "unresolvable"
    assert body["selections"][0]["reason"] == "map_frame_table_absent_or_unknown"
    assert body["selections"][0]["final_chip_ids"] == []


def test_legacy_wafer_mark_is_explicitly_unresolvable_not_fanned_out(monkeypatch):
    monkeypatch.setattr(ledger_selection, "relation_exists", lambda *_: True)
    monkeypatch.setattr(ledger_selection, "_fetch", lambda *_a, **_k: [])
    body = ledger_selection.resolve(object(), {
        "selection": [{"id": "legacy", "kind": "entity_set",
                       "subjectType": "Wafer",
                       "selector": {"ids": ["wafer:SYN-CX-BW-001"]}}]},
        now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    selected = body["selections"][0]
    assert selected["state"] == "unresolvable"
    assert selected["reason"] == "wafer_mark_requires_experiment_unit"
    assert selected["aggregation_units"] == []


def test_declared_bond_map_cell_resolves_through_source_wafer(monkeypatch):
    chip = fixture.UI_PRESETS["hero_defect"]
    candidate, paths, process, analysis_process = _rows_for({chip})
    monkeypatch.setattr(ledger_selection, "relation_exists", lambda *_: True)
    def fetch(_connection, sql, params):
        if "SELECT r.selection_id" in sql:
            return [("map-1", fixture.final_wafer(chip), fixture.bonding_leg(chip),
                     "SYN-CX-BOND-DEFECT_01",
                     7, 7, "DT", "SYN-CX-DT-02", "02")]
        if "WITH marks AS" in sql:
            return candidate
        if "object_payload->'component'->>'final_chip_id' = ANY" in sql:
            return paths
        if "predicate = 'measured'" in sql:
            return []
        if "predicate = 'processed_with'" in sql and "FROM units u JOIN ledger_events e" in sql:
            return analysis_process
        if "predicate = 'processed_with'" in sql:
            return process
        return []
    monkeypatch.setattr(ledger_selection, "_fetch", fetch)
    body = ledger_selection.resolve(object(), {
        "selection": [{"mark_id": "map-1", "kind": "map_cells",
                       "selector": {"table": "bonding_log",
                                    "map_id": "SYN-CX-BOND-DEFECT_01",
                                    "cells": [{"x": 7, "y": 7}]}}]},
        now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    selected = body["selections"][0]
    assert selected["state"] == "resolved"
    assert selected["final_chip_ids"] == [chip]
    assert selected["wafer_mark_keys"] == [
        ledger_identity.encode_mark(**fixture.aggregation_unit(chip))]
    assert selected["material_ids"] == ["material:DT:SYN-CX-DT-02:02"]


def test_categorical_process_does_not_reintroduce_numeric_parameter_candidates():
    counts = {
        "A": {'{"core_branch":"B","core_type":"HBM","occurrence":1,'
              '"recipe":"RCP-B","step":"BOND"}': {("C1", "L1")}},
        "B": {},
    }
    components = {"A": {("C1", "L1"): {}}, "B": {("C2", "L1"): {}}}
    rows = ledger_selection._facet_rows(counts, components, "process", "void")
    assert rows[0]["signature"] == {"core_branch": "B", "core_type": "HBM",
                                    "occurrence": 1, "recipe": "RCP-B", "step": "BOND"}
    assert rows[0]["surprise"]["binding_state"] == "unknown"
    assert rows[0]["surprise"]["reason"] == "categorical_process_has_no_numeric_binding"


def test_sequence_comparison_preserves_repeat_order_and_ambiguous_evidence():
    stamp = datetime(2026, 8, 15, tzinfo=timezone.utc).isoformat()
    components = {
        "A": {("C-A", "L1"): {"core": {"wafer": "W-A"}}},
        "B": {("C-B", "L1"): {"core": {"wafer": "W-B"}},
              ("C-C", "L1"): {"core": {"wafer": "W-C"}}},
    }
    def event(evidence, step, when=stamp):
        return {"evidence_id": evidence, "occurred_at": when,
                "payload": {"step": step, "recipe": f"RCP-{step}"}}
    process = {
        "W-A": [event("a1", "A", "2026-08-15T00:00:00+00:00"),
                event("a2", "B", "2026-08-15T00:01:00+00:00")],
        "W-B": [event("b1", "B", "2026-08-15T00:00:00+00:00"),
                event("b2", "A", "2026-08-15T00:01:00+00:00")],
        "W-C": [event("c1", "A"), event("c2", "A"), event("c3", "B")],
    }
    body = ledger_selection._sequence_comparison(components, process)
    kinds = {row["kind"] for row in body["differences"]}
    assert "order_change" in kinds
    assert "ambiguous_order" in kinds or "repeat_change" in kinds
    assert all(row["evidence_ids"] for row in body["differences"]
               if row["kind"] != "record_absent")


def test_measurement_facets_preserve_values_missingness_evidence_and_marks():
    def member(wafer, leg, core):
        return {"core": {"wafer": core},
                "bond": {"final_wafer": wafer, "bonding_leg": leg}}

    populations = {
        "A": {("A1", "L1"): member("FW-A1", "LEG-A1", "CW-A1"),
              ("A2", "L2"): member("FW-A2", "LEG-A2", "CW-A2")},
        "B": {("B1", "L1"): member("FW-B1", "LEG-B1", "CW-B1"),
              ("B2", "L2"): member("FW-B2", "LEG-B2", "CW-B2")},
    }
    base = {"metric": "film_thickness", "unit": "nm", "method": "ellipsometry",
            "step": "CMP", "recipe": "RCP-CMP"}
    def event(evidence, state, **extra):
        return {"evidence_id": evidence, "occurred_at": "2026-08-15T00:00:00+00:00",
                "payload": {**base, "state": state, **extra}}
    measurements = {
        "CW-A1": [event("e:a1", "recorded", value=1180.0, run_uid="run:a1")],
        "CW-A2": [event("e:a2", "missing")],
        "CW-B1": [event("e:b1", "not_performed")],
        "CW-B2": [event("e:b2", "unknown")],
    }

    rows = ledger_selection._measurement_facet_rows(
        populations, measurements, ledger_selection._measurements_for_path,
        population_kind="component")
    assert len(rows) == 1
    row = rows[0]
    assert row["predicate"] == "measured"
    assert row["signature"] == {"metric": "film_thickness", "unit": "nm",
                                "method": "ellipsometry", "step": "CMP",
                                "recipe": "RCP-CMP"}
    groups = {group["group_id"]: group for group in row["groups"]}
    assert groups["A"]["state_counts"] == {"missing": 1, "recorded": 1}
    assert groups["A"]["value"] == 1180.0
    assert groups["A"]["values"] == [
        {"value": 1180.0, "count": 1, "evidence_ids": ["e:a1"]}]
    assert groups["B"]["state_counts"] == {"not_performed": 1, "unknown": 1}
    assert "value" not in groups["B"] and groups["B"]["values"] == []
    assert row["evidence_ids"] == ["e:a1", "e:a2", "e:b1", "e:b2"]
    assert len(row["wafer_mark_keys"]) == 4


def test_declared_measurement_without_selected_evidence_is_explicit_absent():
    comparison = ledger_selection._comparison([], {}, {}, None,
                                              measurement_by_subject={})
    assert comparison["facets"]["measurement"] == [{
        "state": "absent", "reason": "measured_evidence_absent",
        "predicate": "measured", "wafer_mark_keys": [], "evidence_ids": []}]


def test_universal_entity_set_ids_resolve_as_one_mark(monkeypatch):
    chip = fixture.UI_PRESETS["hero_defect"]
    candidate, paths, process, analysis_process = _rows_for({chip})
    monkeypatch.setattr(ledger_selection, "relation_exists", lambda *_: True)
    def fetch(_connection, sql, _params):
        if "WITH marks AS" in sql:
            return candidate
        if "object_payload->'component'->>'final_chip_id' = ANY" in sql:
            return paths
        if "predicate = 'measured'" in sql:
            return []
        if "predicate = 'processed_with'" in sql and "FROM units u JOIN ledger_events e" in sql:
            return analysis_process
        if "predicate = 'processed_with'" in sql:
            return process
        return []
    monkeypatch.setattr(ledger_selection, "_fetch", fetch)
    body = ledger_selection.resolve(object(), {
        "schemaVersion": 5,
        "selection": [{"id": "universal", "groupId": "A", "kind": "entity_set",
                       "subjectType": "Wafer",
                       "selector": {"ids": [ledger_identity.encode_mark(
                           **fixture.aggregation_unit(chip))]}}]},
        now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert body["schemaVersion"] == 5
    assert body["schema_version"] == 5
    assert body["selections"][0]["markId"] == "universal"
    assert body["selections"][0]["state"] == "resolved"
