"""Contract tests for the complex SYN composite R&D world."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import pytest  # noqa: E402

from ledger_api import finding_kinds  # noqa: E402
from ledger_api import ledger_selection  # noqa: E402
import seed_syn_complex_composite as fixture  # noqa: E402


@pytest.fixture(autouse=True)
def _fixture_finding_kinds():
    """This world's finding kinds, declared BY THE FIXTURE.

    `finding_kinds` used to ship these two in a dict inside the module; that catalogue is
    gone (2026-08-27) and the registry is now whatever `config/finding_kinds.json`
    declares - a file the operator materializes from `config/sample/`, and which a test
    box has no business writing. So the fixture that plants these findings also declares
    them, and the shape asserted below is the shape the seeder actually writes.
    """
    finding_kinds.set_registry({
        "void": {"label": "보이드", "observed_by": ["sat"],
                 "observation_table": "void_obs",
                 "extent_columns": ["radius_x", "radius_y"], "unit_column": "unit",
                 "classes": []},
        "delam": {"label": "박리", "observed_by": ["scat"],
                  "observation_table": "delam_obs",
                  "extent_columns": ["extent_x", "extent_y"], "unit_column": "unit",
                  "classes": ["die-to-die", "die-to-substrate"]},
    })
    yield
    finding_kinds.set_registry(None)


def test_lot_split_rework_resort_and_multi_parent_merge_cardinality():
    atoms = fixture.lineage_atoms()
    derived = [a for a in atoms if a.predicate == "derived_from"]
    parents = defaultdict(set)
    for atom in derived:
        parents[atom.subject_keys["lot"]].add(atom.object_payload["keys"]["lot"])
    for core_type in fixture.CORE_TYPES:
        merged = fixture.core_lot(core_type, "MRG")
        assert len(parents[merged]) == 3
        assert fixture.core_lot(core_type, "B") in parents[fixture.core_lot(core_type, "B-RWK")]
        assert fixture.core_lot(core_type, "C") in parents[fixture.core_lot(core_type, "C-RST")]


def test_transfer_continuity_variable_dt_count_and_no_representative_dt_collapse():
    atoms = fixture.transfer_atoms()
    paths = defaultdict(list)
    per_chip_dt = defaultdict(set)
    for atom in atoms:
        meta = atom.object_payload["component"]
        paths[meta["component_id"]].append(atom)
        for endpoint in (atom.object_payload["from"], atom.object_payload["to"]):
            if endpoint["type"] == "dt_slot":
                per_chip_dt[meta["final_chip_id"]].add((endpoint["keys"]["dt_lot"],
                                                        endpoint["keys"]["dt_slot"]))
    hop_counts = set()
    for component, events in paths.items():
        events.sort(key=lambda a: a.object_payload["sequence"])
        hop_counts.add(len(events) - 1)
        for left, right in zip(events, events[1:]):
            assert left.object_payload["to"] == right.object_payload["from"], component
    assert hop_counts == {0, 1, 2, 3}
    assert all(len(collections) > 1 for collections in per_chip_dt.values())


def test_dt_slots_are_heterogeneous_and_every_chip_has_variable_many_layers():
    types_by_dt = defaultdict(set)
    components_by_chip = defaultdict(set)
    for atom in fixture.transfer_atoms():
        meta = atom.object_payload["component"]
        components_by_chip[meta["final_chip_id"]].add(meta["component_id"])
        for endpoint in (atom.object_payload["from"], atom.object_payload["to"]):
            if endpoint["type"] == "dt_slot":
                types_by_dt[(endpoint["keys"]["dt_lot"],
                             endpoint["keys"]["dt_slot"])].add(meta["core_type"])
    assert any(len(types) >= 2 for types in types_by_dt.values())
    assert {len(v) for v in components_by_chip.values()} == {10, 11, 12, 13, 14, 15}


def test_processes_share_long_spans_diverge_sparsely_and_reconverge():
    by_wafer = defaultdict(list)
    for atom in fixture.process_atoms():
        by_wafer[atom.subject_keys["wafer"]].append(atom.object_payload["step"])
    a = by_wafer[fixture.core_wafer("LOGIC", "A", 1)]
    b = by_wafer[fixture.core_wafer("LOGIC", "B", 1)]
    c = by_wafer[fixture.core_wafer("LOGIC", "C", 1)]
    assert a[:len(fixture.COMMON_PREFIX)] == list(fixture.COMMON_PREFIX)
    assert b[:len(fixture.COMMON_PREFIX)] == list(fixture.COMMON_PREFIX)
    assert c[:len(fixture.COMMON_PREFIX)] == list(fixture.COMMON_PREFIX)
    assert "REWORK_CLEAN" in b and "RESORT" in c and "INLINE_SCAN" not in c
    assert a[-len(fixture.COMMON_SUFFIX):] == list(fixture.COMMON_SUFFIX)
    assert b[-len(fixture.COMMON_SUFFIX):] == list(fixture.COMMON_SUFFIX)
    assert c[-len(fixture.COMMON_SUFFIX):] == list(fixture.COMMON_SUFFIX)


def test_every_core_wafer_has_twenty_plus_ordered_photo_etch_cmp_cln_events():
    by_wafer = defaultdict(list)
    for atom in fixture.process_atoms():
        by_wafer[atom.subject_keys["wafer"]].append(atom)
    assert len(by_wafer) == len(fixture.CORE_TYPES) * len(fixture.BRANCHES) * 3
    required = {"PHOTO", "ETCH", "CMP", "CLN"}
    for wafer, events in by_wafer.items():
        assert len(events) >= 20, wafer
        assert [atom.occurred_at for atom in events] == sorted(
            atom.occurred_at for atom in events), wafer
        assert required <= {
            prefix for atom in events for prefix in required
            if atom.object_payload["step"].startswith(prefix + "_")}, wafer


def test_every_processed_with_payload_exposes_only_step_and_recipe():
    for atom in fixture.process_atoms():
        payload = atom.object_payload
        assert set(payload) == {"step", "recipe"}
        assert set(payload["recipe"]) == {"id", "rev"}
    for atom in fixture.bonding_leg_process_atoms():
        assert atom.subject_type == "Wafer"
        assert set(atom.subject_keys) == {"wafer"}
        assert set(atom.object_payload) == {"step", "recipe", "bonding_leg"}


def test_void_correlated_recipes_are_sparse_while_most_process_claims_stay_common():
    by_wafer_step = {
        (atom.subject_keys["wafer"], atom.object_payload["step"]): atom.object_payload
        for atom in fixture.process_atoms()
    }
    normal = fixture.core_wafer("HBM", "A", 1)
    excursion = fixture.core_wafer("HBM", "B", 1)
    for step in fixture.VOID_CORRELATED_RECIPE_STEPS:
        assert by_wafer_step[(normal, step)]["recipe"]["rev"] == "1"
        assert by_wafer_step[(excursion, step)]["recipe"]["rev"] == "2"
        assert by_wafer_step[(normal, step)]["recipe"] != \
               by_wafer_step[(excursion, step)]["recipe"]

    excursion_atoms = [
        atom for atom in fixture.process_atoms()
        if atom.object_payload["recipe"]["rev"] == "2"]
    assert len(excursion_atoms) == 3 * len(fixture.VOID_CORRELATED_RECIPE_STEPS)
    assert len(excursion_atoms) / len(fixture.process_atoms()) < 0.02


def test_measurements_are_separate_numeric_evidence_with_explicit_absence_states():
    atoms = fixture.measurement_atoms()
    assert len(atoms) == 4 * 3 * 3 * len(fixture.MEASUREMENT_SPECS)
    assert all(atom.predicate == "measured" and atom.subject_type == "Wafer"
               for atom in atoms)
    state_counts = defaultdict(int)
    for atom in atoms:
        payload = atom.object_payload
        state_counts[payload["state"]] += 1
        assert {"metric", "unit", "method", "state", "step", "step_family",
                "eqp", "recipe", "stat"} <= set(payload)
        if payload["state"] == "recorded":
            assert isinstance(payload["value"], (int, float))
            assert payload["run_uid"].startswith("SYN-CX-MET:")
        else:
            assert "value" not in payload and "run_uid" not in payload
    assert state_counts == {"recorded": 141, "missing": 1,
                            "not_performed": 1, "unknown": 1}


def test_measurement_excursions_are_sparse_and_common_values_dominate():
    by_wafer_metric = {
        (atom.subject_keys["wafer"], atom.object_payload["metric"]): atom.object_payload
        for atom in fixture.measurement_atoms()
    }
    normal = fixture.core_wafer("HBM", "A", 1)
    excursion = fixture.core_wafer("HBM", "B", 1)
    for spec in fixture.MEASUREMENT_SPECS:
        assert by_wafer_metric[(normal, spec["metric"])]["value"] == spec["normal"]
        assert by_wafer_metric[(excursion, spec["metric"])]["value"] == spec["excursion"]
    recorded = [atom for atom in fixture.measurement_atoms()
                if atom.object_payload["state"] == "recorded"]
    sparse = [atom for atom in recorded
              if atom.object_payload["value"] == next(
                  spec["excursion"] for spec in fixture.MEASUREMENT_SPECS
                  if spec["metric"] == atom.object_payload["metric"])]
    assert len(sparse) == 3 * len(fixture.MEASUREMENT_SPECS)
    assert len(sparse) / len(recorded) < 0.1


def test_selection_comparison_retains_twenty_plus_sequence_and_knob_ab_evidence():
    defect = fixture.UI_PRESETS["hero_defect"]
    reference = fixture.UI_PRESETS["hero_reference"]
    paths_by_group = {"A": {}, "B": {}}
    selected = {defect: "A", reference: "B"}
    for atom in fixture.transfer_atoms():
        meta = atom.object_payload["component"]
        group_id = selected.get(meta["final_chip_id"])
        if not group_id:
            continue
        key = (meta["final_chip_id"], meta["component_id"])
        paths_by_group[group_id].setdefault(key, {
            "final_chip_id": meta["final_chip_id"],
            "component_id": meta["component_id"],
            "core": {"wafer": atom.subject_keys["wafer"],
                     "lot": meta["core_lot"], "slot": meta["core_slot"],
                     "type": meta["core_type"], "branch": meta["core_branch"]},
            "bond": {"final_wafer": meta["final_wafer_id"],
                     "bonding_leg": meta["bonding_leg"],
                     "layer": meta["bond_layer"]},
            "transfer_steps": 1, "evidence_ids": [atom.source_raw_ref],
        })
    used_wafers = {row["core"]["wafer"] for rows in paths_by_group.values()
                   for row in rows.values()}
    process_by_wafer = defaultdict(list)
    for index, atom in enumerate(fixture.process_atoms()):
        wafer = atom.subject_keys["wafer"]
        if wafer in used_wafers:
            process_by_wafer[wafer].append({
                "evidence_id": f"evidence:{index}",
                "payload": atom.object_payload,
                "occurred_at": atom.occurred_at.isoformat(),
            })
    measurement_by_subject = defaultdict(list)
    for index, atom in enumerate(fixture.measurement_atoms()):
        wafer = atom.subject_keys["wafer"]
        if wafer in used_wafers:
            measurement_by_subject[wafer].append({
                "evidence_id": f"measurement-evidence:{index}",
                "payload": atom.object_payload,
                "occurred_at": atom.occurred_at.isoformat(),
            })
    answers = [{"group_id": group_id, "paths": list(rows.values())}
               for group_id, rows in paths_by_group.items()]
    body = ledger_selection._comparison(
        answers, {}, process_by_wafer, "void", measurement_by_subject)
    allowed_process_keys = {
        "core_type", "core_branch", "subject_grain", "step", "recipe", "occurrence"}
    assert all(set(row["signature"]) <= allowed_process_keys
               for row in body["facets"]["process"])
    assert all(set(token) == {"step", "recipe", "occurrence"}
               for cluster in body["sequence"]["clusters"] for token in cluster["tokens"])
    assert body["sequence"]["state"] == "ready"
    assert min(len(row["tokens"]) for row in body["sequence"]["clusters"]) >= 20
    steps = {token["step"] for row in body["sequence"]["clusters"]
             for token in row["tokens"]}
    assert all(any(step.startswith(prefix + "_") for step in steps)
               for prefix in ("PHOTO", "ETCH", "CMP", "CLN"))
    signal = next(row for row in body["facets"]["process"]
                  if row["signature"].get("core_type") == "HBM"
                  and row["signature"].get("core_branch") == "B"
                  and row["signature"].get("step") == "ETCH_PATTERN_02"
                  and row["signature"].get("recipe") ==
                      fixture.process_recipe("HBM", "B", "ETCH_PATTERN_02"))
    frequencies = {row["group_id"]: row["frequency"] for row in signal["groups"]}
    assert frequencies["A"] > 0 and frequencies["B"] == 0
    assert signal["evidence_ids"]
    measurement = next(row for row in body["facets"]["measurement"]
                       if row.get("signature", {}).get("metric") == "etched_cd"
                       and row.get("signature", {}).get("recipe") ==
                           fixture.process_recipe("HBM", "B", "ETCH_PATTERN_02"))
    measurement_groups = {row["group_id"]: row for row in measurement["groups"]}
    assert any(item["value"] == 48.8 for item in measurement_groups["A"]["values"])
    assert all(item["value"] != 48.8 for item in measurement_groups["B"]["values"])
    assert measurement["evidence_ids"] and measurement["wafer_mark_keys"]


def test_all_twelve_experiment_aggregates_trace_real_measurements_for_all_four_metrics():
    metrics_by_wafer = defaultdict(set)
    for atom in fixture.measurement_atoms():
        metrics_by_wafer[atom.subject_keys["wafer"]].add(
            atom.object_payload["metric"])
    expected_metrics = {spec["metric"] for spec in fixture.MEASUREMENT_SPECS}
    assert all(metrics == expected_metrics for metrics in metrics_by_wafer.values())

    component_wafers_by_chip = defaultdict(set)
    for atom in fixture.transfer_atoms():
        component_wafers_by_chip[
            atom.object_payload["component"]["final_chip_id"]].add(
                atom.subject_keys["wafer"])
    assert set(component_wafers_by_chip) == set(fixture.FINAL_CHIPS)
    for chip, wafers in component_wafers_by_chip.items():
        assert wafers and all(metrics_by_wafer[wafer] == expected_metrics for wafer in wafers), chip


def test_answer_key_names_resolution_and_absence_semantics_without_fake_values():
    atoms = fixture.build_atoms()
    key = fixture.validate(atoms)
    assert set(key["resolution_states"]) == {
        "resolved", "candidate", "contested", "unresolvable"}
    assert set(key["absence_cases"].values()) == {
        "missing_record", "not_performed", "unknown"}
    missing = fixture.core_wafer("LOGIC", "A", 2)
    missing_steps = [a.object_payload["step"] for a in atoms
                     if a.predicate == "processed_with"
                     and a.subject_keys.get("wafer") == missing]
    assert "INLINE_SCAN" not in missing_steps


def test_dt_output_job_lot_slot_cases_are_distinct_and_recovery_evidence_is_explicit():
    atoms = fixture.transfer_atoms()
    key = fixture.answer_key(atoms)
    assert {row["state"] for row in key["dt_output_cases"].values()} == set(
        fixture.DT_OUTPUT_CASES)
    payloads = [a.object_payload for a in atoms]
    assert any(p.get("output_identity_evidence", {}).get("resolution") == "indirect"
               for p in payloads)
    assert any(p.get("output_identity_evidence", {}).get("resolution") ==
               "candidate_conflict" for p in payloads)
    first_by_component = {}
    for atom in atoms:
        component = atom.object_payload["component"]["component_id"]
        first_by_component.setdefault(component, atom)
    lot_missing = next(component for component, row in key["dt_output_cases"].items()
                       if row["state"] == "output_lot_missing")
    output = first_by_component[lot_missing].object_payload["to"]["output"]
    assert output["job"] and output["lot"] is None and output["slot"]
    slot_missing = next(component for component, row in key["dt_output_cases"].items()
                        if row["state"] == "output_slot_missing")
    output = first_by_component[slot_missing].object_payload["to"]["output"]
    assert output["job"] and output["lot"] and output["slot"] is None


def test_observation_to_composite_bridge_is_explicit_but_not_identity_collapsed():
    transfers = fixture.transfer_atoms()
    observations = fixture.observation_atoms()
    key = fixture.answer_key(transfers + observations)
    for wafer, chips in key["wafer_to_final_chips"].items():
        assert len(chips) == 2
        assert {fixture.bonding_leg(chip) for chip in chips} == {
            fixture.CAUSE_LEG, fixture.REFERENCE_LEG}
        for chip in chips:
            matching_bonds = [a for a in transfers
                              if a.object_payload["component"]["final_chip_id"] == chip
                              and a.object_payload["to"]["type"] == "bond_layer"]
            assert matching_bonds
            assert all(a.object_payload["to"]["keys"]["base_wafer_id"] == wafer
                       and a.object_payload["to"]["keys"]["bonding_leg"] ==
                       fixture.bonding_leg(chip) for a in matching_bonds)
    for atom in observations:
        if atom.predicate == "observed":
            if "final_chip_id" in atom.object_payload:
                chip = atom.object_payload["final_chip_id"]
                assert atom.subject_type == "Wafer"
                assert atom.subject_keys == {"wafer": fixture.final_wafer(chip)}
                assert atom.object_payload["bonding_leg"] == fixture.bonding_leg(chip)
            else:
                assert atom.object_payload["method"] == "SYN_CX_CORE_WF_MAP"
                assert atom.subject_keys["wafer"] == \
                       fixture.CORE_SPATIAL_WAFERS[fixture.CORE_SPATIAL_MAPS[1]]
            assert "answer_key" not in atom.object_payload


def test_root_cause_signal_is_shared_by_every_defect_and_absent_from_references():
    atoms = fixture.transfer_atoms()
    key = fixture.answer_key(atoms)
    cause = key["expected_root_causes"][0]
    assert set(cause["affected"]) == set(fixture.DEFECT_CHIPS)
    assert cause["clean_contrast"]["exact_combination_present"] is False
    for chip, rows in cause["affected"].items():
        assert rows, chip
        assert all(row["core_type"] == "HBM" and row["core_branch"] == "B"
                   for row in rows)
    reference_signals = [a for a in atoms
                         if a.object_payload["component"]["final_chip_id"] in
                         fixture.REFERENCE_CHIPS
                         and fixture.is_designed_cause(a.object_payload["component"])]
    assert reference_signals == []
    per_cause_component = {}
    for atom in atoms:
        meta = atom.object_payload["component"]
        if fixture.is_designed_cause(meta):
            per_cause_component.setdefault(meta["component_id"], []).append(atom)
    assert per_cause_component
    assert all(sum(a.object_payload["to"]["type"] == "dt_slot" for a in events) >= 2
               for events in per_cause_component.values())
    process = fixture.process_atoms()
    cause_wafers = {row["core_wafer"] for rows in cause["affected"].values() for row in rows}
    cause_process = [a.object_payload for a in process
                     if a.subject_keys["wafer"] in cause_wafers]
    assert any(p["step"] == "REWORK_CLEAN" for p in cause_process)
    assert any(p["step"] in fixture.VOID_CORRELATED_RECIPE_STEPS
               and p["recipe"]["rev"] == "2" for p in cause_process)
    expected = key["expected_root_causes"][0]["process_evidence"]
    assert set(expected["recipe_excursions"]) == fixture.VOID_CORRELATED_RECIPE_STEPS
    assert fixture.UI_PRESETS["hero_defect"] in fixture.DEFECT_CHIPS
    assert fixture.UI_PRESETS["hero_reference"] in fixture.REFERENCE_CHIPS


def test_persisted_atoms_contain_no_answer_shortcut_keys_or_cause_operation_tag():
    import json
    forbidden = ('"answer_population"', '"root_cause_signal"', '"cause_regroup"')
    for atom in fixture.build_atoms():
        encoded = json.dumps(atom.object_payload, sort_keys=True)
        assert all(token not in encoded for token in forbidden), atom.source_raw_ref


def test_spatial_contract_has_two_maps_per_axis_and_one_declared_valid_die_floor():
    key = fixture.spatial_answer_key()
    assert all(len(maps) >= 2 for maps in key["axes"].values())
    assert key["coordinate_unit"] == "cells_from_origin"
    assert key["grid"]["grid_start_x"] == key["grid"]["grid_start_y"] == 1
    assert key["grid"]["grid_y_invert"] is False
    assert key["grid"]["valid_die_ref"]["map_id"] == fixture.VALID_DIE_MAP_ID
    assert key["counts"] == {
        "valid_die": 132, "process_area_per_bond_map": 64,
        "defect_on_hero": 9, "defect_on_reference": 0}
    metadata = fixture.map_metadata_rows()
    assert sum(row["target_table"] == "bonding_log" for row in metadata) == \
           len(fixture.BOND_SPATIAL_MAPS) + len(fixture.DT_SPATIAL_MAPS) + \
           len(fixture.CORE_SPATIAL_MAPS)
    assert sum(row["target_table"] == "dt_map" for row in metadata) == 2
    assert sum(row["target_table"] == "core_wafer_map" for row in metadata) == 2
    assert sum(row["target_table"] == "valid_die_ref" for row in metadata) == 1
    assert sum(row["target_table"] == "bonding_map" for row in metadata) == 6


def test_spatial_source_rows_layer_valid_process_used_and_defect_without_guessing():
    rows = fixture.spatial_source_rows()
    assert len(rows["valid_die_ref"]) == len(fixture.valid_die_cells()) == 132
    all_valid_x = [row["x"] for row in rows["valid_die_ref"]]
    all_valid_y = [row["y"] for row in rows["valid_die_ref"]]
    assert min(all_valid_x) == min(all_valid_y) == 1
    assert max(all_valid_x) == max(all_valid_y) == 12
    assert len(rows["bonding_log"]) == len(fixture.BOND_SPATIAL_MAPS) * 64 == 768
    assert len(rows["bonding_map"]) == 6 * 2 * 64 == 768
    assert len(rows["dt_map"]) == len(fixture.process_area_cells()) == 128
    assert len(rows["core_wafer_map"]) == 2 * len(fixture.process_area_cells()) == 256
    assert len(rows["inspection_run"]) == 12 * 2 * 64 == 1536
    assert len(rows["void_obs"]) == len(fixture.DEFECT_CHIPS) * \
           len(fixture.defect_area_cells()) == 54
    assert all(row["run_uid"] for row in rows["void_obs"])
    assert {row["run_uid"] for row in rows["void_obs"]} <= {
        row["run_uid"] for row in rows["inspection_run"]}
    denominators = {}
    for row in rows["inspection_run"]:
        denominators.setdefault((row["base_wafer_id"], row["method"]), 0)
        denominators[(row["base_wafer_id"], row["method"])] += 1
    assert set(denominators) == {
        (fixture.final_wafer(chip), method)
        for chip in fixture.FINAL_CHIPS for method in ("sat", "scat")}
    assert set(denominators.values()) == {128}
    for table, x_name, y_name in (("bonding_log", "bond_x", "bond_y"),
                                  ("dt_map", "dt_x", "dt_y"),
                                  ("core_wafer_map", "core_x", "core_y")):
        assert all(1 <= row[x_name] <= 12 and 1 <= row[y_name] <= 12
                   for row in rows[table])
    defect_wafer = fixture.final_wafer(fixture.UI_PRESETS["hero_defect"])
    defect_bond = {(int(row["bond_x"]), int(row["bond_y"])): row
                   for row in rows["bonding_log"] if row["base_id"] == defect_wafer}
    for cell in fixture.defect_area_cells():
        row = defect_bond[cell]
        assert (row["dt_lot"], row["dt_slot"]) == fixture.DT_SPATIAL_MAPS[1]
        assert (row["core_lot"], row["core_slot"]) == fixture.CORE_SPATIAL_MAPS[1]
        assert row["b_bn"] == "0"
    assert all(row["b_bn"] == "1" for row in rows["bonding_log"]
               if row["bond_lot"] == "SYN-CX-BOND-REFERENCE")
    core_by_map = {}
    for row in rows["core_wafer_map"]:
        core_by_map.setdefault((row["core_lot"], row["core_slot"]), []).append(row)
    assert sum(row["c_bn"] == "0" for row in core_by_map[fixture.CORE_SPATIAL_MAPS[1]]) == 9
    assert all(row["c_bn"] == "1" for row in core_by_map[fixture.CORE_SPATIAL_MAPS[0]])


def test_all_twelve_experiment_aggregates_have_bond_dt_and_logic_hbm_map_sources():
    rows = fixture.spatial_source_rows()
    specs_by_unit = {
        (fixture.final_wafer(spec["chip"]), spec["bonding_leg"]): spec
        for spec in fixture.BOND_SPATIAL_MAPS}
    assert set(specs_by_unit) == {
        (fixture.final_wafer(chip), fixture.bonding_leg(chip))
        for chip in fixture.FINAL_CHIPS}
    assert len(specs_by_unit) == 12
    for unit, spec in specs_by_unit.items():
        cells = [row for row in rows["bonding_log"]
                 if row["bond_lot"] == spec["bond_lot"]
                 and row["bond_slot"] == spec["bond_slot"]]
        assert len(cells) == 64, unit
        assert {(row["dt_lot"], row["dt_slot"]) for row in cells} == \
               set(fixture.DT_SPATIAL_MAPS)
        assert {(row["core_lot"], row["core_slot"]) for row in cells} == \
               set(fixture.CORE_SPATIAL_MAPS)
        assert all(row["base_id"] == unit[0] for row in cells)

    dt_by_map = defaultdict(list)
    for row in rows["dt_map"]:
        dt_by_map[(row["dt_lot"], row["dt_slot"])].append(row)
    assert set(dt_by_map) == set(fixture.DT_SPATIAL_MAPS)
    assert all(map_rows and all(row["core_wafer"] and row["core_lot"]
                                and row["core_slot"] for row in map_rows)
               for map_rows in dt_by_map.values())
    metadata = {(row["target_table"], row["map_id"])
                for row in rows["wafer_map_metadata"]}
    assert all(("bonding_log", f"{spec['bond_lot']}_{spec['bond_slot']}") in metadata
               for spec in fixture.BOND_SPATIAL_MAPS)
    assert all(("dt_map", f"{lot}_{slot}") in metadata
               for lot, slot in fixture.DT_SPATIAL_MAPS)
    assert all(("core_wafer_map", f"{lot}_{slot}") in metadata
               for lot, slot in fixture.CORE_SPATIAL_MAPS)


def test_spatial_rows_are_deterministic_and_have_unique_declared_business_keys():
    first, second = fixture.spatial_source_rows(), fixture.spatial_source_rows()
    assert first == second
    key_fields = {
        "wafer_map_metadata": ("target_table", "map_id"),
        "valid_die_ref": ("product", "type", "x", "y"),
        "bonding_log": ("bond_lot", "bond_slot", "bond_x", "bond_y"),
        "bonding_map": ("base", "x", "y"),
        "dt_map": ("dt_lot", "dt_slot", "dt_x", "dt_y"),
        "core_wafer_map": ("core_lot", "core_slot", "core_x", "core_y"),
        "inspection_run": ("method", "base_wafer_id", "base_x", "base_y",
                           "stack_gate", "observed_at"),
        "void_obs": ("run_uid", "inchip_x", "inchip_y"),
    }
    for table, rows in first.items():
        fields = key_fields[table]
        keys = [tuple(row[field] for field in fields) for row in rows]
        assert len(keys) == len(set(keys)), table


def test_trend_population_has_six_found_and_six_explicit_scanned_clean_wafers():
    rows = fixture.spatial_source_rows()
    leg_by_cell = {(row["base"], row["x"], row["y"]): row["leg"]
                   for row in rows["bonding_map"]}
    scanned_void = {
        (row["base_wafer_id"], leg_by_cell[(row["base_wafer_id"],
                                            row["base_x"], row["base_y"])])
        for row in rows["inspection_run"] if row["method"] == "sat"}
    observed_void = {
        (atom.subject_keys["wafer"], atom.object_payload["bonding_leg"])
        for atom in fixture.observation_atoms()
        if atom.predicate == "observed"
        and atom.object_payload["finding_kind"] == "void"
        and atom.object_payload["method"] == "SYN_CX_INSPECTION"}
    assert scanned_void == {(fixture.final_wafer(chip), fixture.bonding_leg(chip))
                            for chip in fixture.FINAL_CHIPS}
    assert observed_void == {(fixture.final_wafer(chip), fixture.bonding_leg(chip))
                             for chip in fixture.DEFECT_CHIPS}
    assert scanned_void - observed_void == {
        (fixture.final_wafer(chip), fixture.bonding_leg(chip))
        for chip in fixture.REFERENCE_CHIPS}


def test_same_base_wafer_has_two_disjoint_string_legs_and_end_to_end_bridge():
    rows = fixture.spatial_source_rows()
    by_base = {}
    for row in rows["bonding_map"]:
        by_base.setdefault(row["base"], {}).setdefault(row["leg"], set()).add(
            (row["x"], row["y"]))
    assert set(by_base) == set(fixture.BASE_WAFERS)
    for leg_regions in by_base.values():
        assert set(leg_regions) == {fixture.CAUSE_LEG, fixture.REFERENCE_LEG}
        assert all(isinstance(leg, str) for leg in leg_regions)
        assert all(len(cells) == 64 for cells in leg_regions.values())
        assert leg_regions[fixture.CAUSE_LEG].isdisjoint(
            leg_regions[fixture.REFERENCE_LEG])

    transfers = fixture.transfer_atoms()
    for chip in fixture.FINAL_CHIPS:
        unit = fixture.aggregation_unit(chip)
        component_events = [a for a in transfers
                            if a.object_payload["component"]["final_chip_id"] == chip]
        assert component_events
        assert all(a.object_payload["component"]["base_wafer_id"] == unit["wafer"]
                   and a.object_payload["component"]["bonding_leg"] ==
                   unit["bonding_leg"] for a in component_events)
        assert any(a.object_payload["to"]["type"] == "bond_layer"
                   and a.object_payload["to"]["keys"]["base_wafer_id"] == unit["wafer"]
                   and a.object_payload["to"]["keys"]["bonding_leg"] ==
                   unit["bonding_leg"] for a in component_events)

    conditions = {(a.subject_keys["wafer"], a.object_payload["bonding_leg"]):
                  a.object_payload
                  for a in fixture.bonding_leg_process_atoms()}
    assert len(conditions) == 12
    assert all(payload == {
        "step": "FINAL_BOND",
        "recipe": {"id": f"SYN-CX-RCP-{leg}", "rev": "1"},
        "bonding_leg": leg}
        for (_wafer, leg), payload in conditions.items())

    leg_by_cell = {(row["base"], row["x"], row["y"]): row["leg"]
                   for row in rows["bonding_map"]}
    for spec in fixture.BOND_SPATIAL_MAPS:
        map_rows = [row for row in rows["bonding_log"]
                    if row["bond_lot"] == spec["bond_lot"]
                    and row["bond_slot"] == spec["bond_slot"]]
        assert len(map_rows) == 64
        assert all(leg_by_cell[(row["base_id"], row["bx"], row["by"])] ==
                   spec["bonding_leg"] for row in map_rows)
        assert all(row["dt_lot"] and row["dt_slot"] and row["core_lot"]
                   and row["core_slot"] for row in map_rows)


def test_every_experiment_aggregate_resolves_all_components_to_core_process_evidence():
    processed_wafers = {atom.subject_keys["wafer"] for atom in fixture.process_atoms()}
    transfers = fixture.transfer_atoms()
    for chip in fixture.FINAL_CHIPS:
        components = {}
        for atom in transfers:
            meta = atom.object_payload["component"]
            if meta["final_chip_id"] == chip:
                components.setdefault(meta["component_id"], atom.subject_keys["wafer"])
        assert len(components) == fixture.layers_for_chip(fixture.FINAL_CHIPS.index(chip))
        assert set(components.values()) <= processed_wafers


def test_sorting_layers_colour_cells_by_stable_supply_material_identity():
    layers = fixture.spatial_answer_key()["layers"]["supply_material"]
    assert set(layers) == {"bond", "dt"}
    assert set(layers["bond"]) == {f"{row['bond_lot']}_{row['bond_slot']}"
                                   for row in fixture.BOND_SPATIAL_MAPS}
    assert set(layers["dt"]) == {f"{lot}_{slot}"
                                 for lot, slot in fixture.DT_SPATIAL_MAPS}
    assert sum(map(len, layers["bond"].values())) == \
           len(fixture.BOND_SPATIAL_MAPS) * 64
    assert sum(map(len, layers["dt"].values())) == 128
    assert all(cell["material_id"].startswith("DT:")
               for cells in layers["bond"].values() for cell in cells)
    assert all(cell["material_id"].startswith("CORE:")
               for cells in layers["dt"].values() for cell in cells)
    # The designed defect cluster remains one selectable Core supply group.
    cause_map = f"{fixture.DT_SPATIAL_MAPS[1][0]}_{fixture.DT_SPATIAL_MAPS[1][1]}"
    cause_cells = layers["dt"][cause_map]
    assert set(fixture.defect_area_cells()) <= {
        (cell["x"], cell["y"]) for cell in cause_cells}
    assert {cell["material_id"].split(":")[1] for cell in cause_cells} == {
        fixture.CORE_SPATIAL_MAPS[1][0]}


def test_core_wf_defect_layer_matches_physical_map_and_ledger_finding_coordinates():
    key = fixture.spatial_answer_key()
    cause_map = f"{fixture.CORE_SPATIAL_MAPS[1][0]}_{fixture.CORE_SPATIAL_MAPS[1][1]}"
    clean_map = f"{fixture.CORE_SPATIAL_MAPS[0][0]}_{fixture.CORE_SPATIAL_MAPS[0][1]}"
    layer = key["map_payloads"][cause_map]["layers"]["defect"]
    assert {(cell["x"], cell["y"]) for cell in layer} == set(fixture.defect_area_cells())
    assert key["map_payloads"][clean_map]["layers"]["defect"] == []
    findings = [a for a in fixture.observation_atoms()
                if a.predicate == "observed"
                and a.object_payload["method"] == "SYN_CX_CORE_WF_MAP"]
    assert {(a.object_payload["position"]["x"], a.object_payload["position"]["y"])
            for a in findings} == set(fixture.defect_area_cells())
    assert all("answer_key" not in a.object_payload for a in findings)


def test_browser_fixture_events_are_not_future_dated_at_acceptance_time():
    atoms = fixture.build_atoms()
    assert max(atom.occurred_at for atom in atoms) <= fixture.ACCEPTANCE_NOW
    observed = [atom for atom in atoms if atom.predicate == "observed"]
    assert observed
    assert min(atom.occurred_at for atom in observed) >= (
        fixture.ACCEPTANCE_NOW - timedelta(days=90))


def test_deterministic_second_build_has_identical_semantic_rows():
    def semantic(atom):
        return (atom.subject_type, repr(sorted(atom.subject_keys.items())), atom.predicate,
                atom.object_kind, repr(atom.object_payload), atom.occurred_at,
                atom.source_who, atom.source_translator_ver, atom.source_raw_ref)
    first = [semantic(atom) for atom in fixture.build_atoms()]
    second = [semantic(atom) for atom in fixture.build_atoms()]
    assert first == second
    assert len(first) == len(set(first))
