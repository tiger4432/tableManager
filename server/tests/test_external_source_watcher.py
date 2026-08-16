"""External read-only directory ingestion and voids.json path contract."""
import json
import os
import sys
import time

import pytest

test_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(test_dir, ".."))
parsers_dir = os.path.join(server_dir, "parsers")
for path in (server_dir, parsers_dir):
    if path not in sys.path:
        sys.path.insert(0, path)

import directory_watcher
from database import crud
from directory_watcher import (
    ExternalSourceEventHandler,
    IngestionHandler,
    WorkspaceWatcher,
    validate_external_source_specs,
)
from voids_json_format import parse_relative_source_path, parse_voids_json


RUN_INFO = {
    "business_key": "run_uid",
    "composite_key_source": [
        "method", "base_wafer_id", "base_x", "base_y", "stack_gate", "observed_at",
    ],
    "composite_key_separator": "|",
    "column_types": {
        "run_uid": "string", "method": "string", "base_wafer_id": "string",
        "base_x": "number", "base_y": "number", "stack_gate": "number",
        "recipe_id": "string", "eqp_id": "string", "observed_at": "datetime",
    },
    "display_columns": [
        "run_uid", "method", "base_wafer_id", "base_x", "base_y", "stack_gate",
        "recipe_id", "eqp_id", "observed_at",
    ],
}
VOID_INFO = {
    "business_key": "void_uid",
    "composite_key_source": ["run_uid", "inchip_x", "inchip_y"],
    "composite_key_separator": "|",
    "column_types": {
        "void_uid": "string", "run_uid": "string", "base_wafer_id": "string",
        "base_x": "number", "base_y": "number", "stack_gate": "number",
        "inchip_x": "number", "inchip_y": "number", "radius_x": "number",
        "radius_y": "number", "unit": "string",
    },
    "display_columns": [
        "void_uid", "run_uid", "base_wafer_id", "base_x", "base_y", "stack_gate",
        "inchip_x", "inchip_y", "radius_x", "radius_y", "unit",
    ],
}
TABLES = {"inspection_run": RUN_INFO, "void_obs": VOID_INFO}


@pytest.fixture(autouse=True)
def canonical_void_config(monkeypatch):
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", TABLES)


def _specs(root):
    return {
        "external_sources": [
            {
                "path": str(root), "table_name": "void_obs", "parser": "voids_json",
                "recursive": True, "options": {"filename": "voids.json"},
            },
            {
                "path": str(root), "table_name": "inspection_run", "parser": "voids_json",
                "recursive": True, "options": {"filename": "voids.json"},
            },
        ]
    }


def _write_voids(root, body=None):
    path = root / "WF-001" / "WORK_20260817_031405" / "voids.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = body if body is not None else {
        "unit": "um",
        "recipe_id": "SAT-R1",
        "voids": [{
            "base_x": 3, "base_y": 4, "gate": 2,
            "inchip_x": 10.5, "inchip_y": 20.25,
            "radius_x": 1.5, "radius_y": 2.5,
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_path_parser_extracts_wafer_and_source_time():
    got = parse_relative_source_path("WF-001/WORK_20260817_031405/voids.json")
    assert got["base_wafer_id"] == "WF-001"
    assert got["observed_at"] == "2026-08-17T03:14:05+09:00"


@pytest.mark.parametrize("bad", [
    "voids.json",
    "WF-001/voids.json",
    "extra/WF-001/WORK_20260817_031405/voids.json",
    "WF-001/WORK_not-a-time/voids.json",
    "WF-001/WORK_20261301_000000/voids.json",
])
def test_path_parser_refuses_ambiguous_or_invalid_layout(bad):
    with pytest.raises(ValueError):
        parse_relative_source_path(bad)


def test_void_parser_receives_full_filename_and_injects_path_wafer(tmp_path):
    file_path = _write_voids(tmp_path)
    rel = "WF-001/WORK_20260817_031405/voids.json"
    rows, total, refused = parse_voids_json(
        str(file_path), rel_path=rel, table_name="void_obs")
    assert total == 1 and refused == 0
    row = rows[0]
    assert row["base_wafer_id"] == "WF-001"
    assert row["observed_at"] == "2026-08-17T03:14:05+09:00"
    assert row["stack_gate"] == 2
    assert row["run_uid"].startswith("sat|WF-001|3")


def test_same_json_produces_the_run_denominator(tmp_path):
    file_path = _write_voids(tmp_path)
    rows, total, refused = parse_voids_json(
        str(file_path),
        rel_path="WF-001/WORK_20260817_031405/voids.json",
        table_name="inspection_run",
    )
    assert total == 1 and refused == 0
    assert rows == [{
        "method": "sat", "base_wafer_id": "WF-001", "base_x": 3.0,
        "base_y": 4.0, "stack_gate": 2,
        "observed_at": "2026-08-17T03:14:05+09:00",
        "recipe_id": "SAT-R1", "eqp_id": None,
    }]


def test_missing_unit_refuses_observation_but_keeps_independent_run_fact(tmp_path):
    file_path = _write_voids(tmp_path, body={
        "voids": [{
            "base_x": 3, "base_y": 4, "gate": 2,
            "inchip_x": 10, "inchip_y": 20, "radius_x": 1, "radius_y": 2,
        }],
    })
    rel = "WF-001/WORK_20260817_031405/voids.json"
    runs, total, refused = parse_voids_json(
        str(file_path), rel_path=rel, table_name="inspection_run")
    assert total == 1 and refused == 0 and runs[0]["base_wafer_id"] == "WF-001"
    with pytest.raises(ValueError, match="unit must be one of"):
        parse_voids_json(str(file_path), rel_path=rel, table_name="void_obs")


def test_explicit_runs_must_cover_every_package_layer_found_in_void_rows(tmp_path):
    file_path = _write_voids(tmp_path, body={
        "unit": "um",
        "runs": [{"base_x": 99, "base_y": 4, "gate": 2}],
        "voids": [{
            "base_x": 3, "base_y": 4, "gate": 2,
            "inchip_x": 10, "inchip_y": 20, "radius_x": 1, "radius_y": 2,
        }],
    })
    with pytest.raises(ValueError, match="omit 1 package layer"):
        parse_voids_json(
            str(file_path), rel_path="WF-001/WORK_20260817_031405/voids.json",
            table_name="inspection_run")


def test_clean_scan_requires_and_accepts_explicit_run(tmp_path):
    file_path = _write_voids(tmp_path, body={
        "unit": "um", "voids": [],
        "runs": [{"base_x": 1, "base_y": 2, "gate": 3}],
    })
    rel = "WF-001/WORK_20260817_031405/voids.json"
    runs, total, _ = parse_voids_json(
        str(file_path), rel_path=rel, table_name="inspection_run")
    voids, void_total, _ = parse_voids_json(
        str(file_path), rel_path=rel, table_name="void_obs")
    assert total == 1 and runs[0]["stack_gate"] == 3
    assert void_total == 0 and voids == []


def test_empty_file_and_wafer_conflict_are_loud(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty voids.json"):
        parse_voids_json(
            str(empty), rel_path="WF-001/WORK_20260817_031405/voids.json",
            table_name="void_obs")

    conflict = _write_voids(tmp_path, body={
        "unit": "um",
        "voids": [{
            "base_wafer_id": "WF-OTHER", "base_x": 1, "base_y": 2, "gate": 3,
            "inchip_x": 4, "inchip_y": 5, "radius_x": 6, "radius_y": 7,
        }],
    })
    with pytest.raises(ValueError, match="conflicts with path wafer id"):
        parse_voids_json(
            str(conflict), rel_path="WF-001/WORK_20260817_031405/voids.json",
            table_name="void_obs")


def test_external_config_allows_one_root_to_feed_both_tables(tmp_path):
    external = tmp_path / "outside" / "void"
    workspace = tmp_path / "data" / "ingestion_workspace"
    specs, errors = validate_external_source_specs(_specs(external), TABLES, str(workspace))
    assert errors == []
    assert {spec["table_name"] for spec in specs} == {"void_obs", "inspection_run"}
    assert all(spec["root"] == os.path.realpath(str(external)) for spec in specs)


def test_external_config_rejects_unkeyed_target_and_workspace_overlap(tmp_path):
    workspace = tmp_path / "data" / "ingestion_workspace"
    unkeyed = {"legacy_void": {"display_columns": ["base_wafer_id"]}}
    settings = {"external_sources": [{
        "path": str(tmp_path / "outside"), "table_name": "legacy_void",
        "parser": "voids_json",
    }]}
    _spec, errors = validate_external_source_specs(settings, unkeyed, str(workspace))
    assert any("unkeyed table" in error for error in errors)

    overlap = _specs(workspace / "void_obs" / "raws")
    _spec, errors = validate_external_source_specs(overlap, TABLES, str(workspace))
    assert len(errors) == 2
    assert all("overlaps the managed ingestion workspace" in error for error in errors)


def test_recursive_sweep_dispatches_same_file_once_per_table_and_keeps_source(
        tmp_path, monkeypatch):
    workspace = tmp_path / "ingestion_workspace"
    external = tmp_path / "external" / "void"
    workspace.mkdir()
    file_path = _write_voids(external)
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings", lambda: _specs(external))

    calls = []
    monkeypatch.setattr(
        IngestionHandler, "_handle_event",
        lambda self, path: calls.append((self.table_name, os.path.abspath(path))),
    )
    monkeypatch.setattr(IngestionHandler, "settle_already_terminal", lambda self, entries: set())

    watcher = WorkspaceWatcher(str(workspace))
    watcher.discover_and_watch()
    assert len(watcher.external_targets) == 2
    assert watcher.sweep_external_sources() == 2
    assert sorted(table for table, _path in calls) == ["inspection_run", "void_obs"]
    assert file_path.exists(), "external source must never be archived/deleted"
    assert watcher.sweep_external_sources() == 0

    file_path.write_text(file_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    os.utime(file_path, (time.time() + 2, time.time() + 2))
    assert watcher.sweep_external_sources() == 2
    assert len(calls) == 4


def test_modified_event_is_enabled_only_for_external_adapter(tmp_path, monkeypatch):
    workspace = tmp_path / "ingestion_workspace"
    external = tmp_path / "external"
    raws = workspace / "void_obs" / "raws"
    archives = workspace / "void_obs" / "archives"
    raws.mkdir(parents=True)
    archives.mkdir(parents=True)
    file_path = _write_voids(external)
    spec, errors = validate_external_source_specs(
        {"external_sources": [_specs(external)["external_sources"][0]]},
        TABLES, str(workspace))
    assert not errors
    handler = IngestionHandler(
        str(workspace / "void_obs"), None, str(archives), default_table_name="void_obs")
    handler.register_external_source(spec[0])
    calls = []
    monkeypatch.setattr(handler, "_handle_event", lambda path: calls.append(path))
    adapter = ExternalSourceEventHandler(handler, spec[0])

    event = type("Event", (), {"is_directory": False, "src_path": str(file_path)})()
    adapter.on_modified(event)
    assert calls == [str(file_path)]
    assert handler._consume_external_force_hash(str(file_path)) is True
    assert handler._consume_external_force_hash(str(file_path)) is False


def test_external_relative_path_is_the_parser_metadata(tmp_path):
    workspace = tmp_path / "ingestion_workspace" / "void_obs"
    external = tmp_path / "external"
    (workspace / "raws").mkdir(parents=True)
    (workspace / "archives").mkdir()
    file_path = _write_voids(external)
    spec, errors = validate_external_source_specs(
        {"external_sources": [_specs(external)["external_sources"][0]]},
        TABLES, str(tmp_path / "ingestion_workspace"))
    assert not errors
    handler = IngestionHandler(
        str(workspace), None, str(workspace / "archives"), default_table_name="void_obs")
    handler.register_external_source(spec[0])
    meta = handler._parse_meta_for(str(file_path))
    assert meta["rel_path"] == "WF-001/WORK_20260817_031405/voids.json"
    assert meta["external_source"]["source_root"] == os.path.realpath(str(external))
    assert handler.is_managed_source(str(file_path)) is False


def test_handler_passes_external_full_path_and_relative_path_to_builtin_parser(tmp_path):
    workspace = tmp_path / "ingestion_workspace" / "void_obs"
    external = tmp_path / "external"
    (workspace / "raws").mkdir(parents=True)
    (workspace / "archives").mkdir()
    file_path = _write_voids(external)
    spec, errors = validate_external_source_specs(
        {"external_sources": [_specs(external)["external_sources"][0]]},
        TABLES, str(tmp_path / "ingestion_workspace"))
    assert not errors
    handler = IngestionHandler(
        str(workspace), None, str(workspace / "archives"), default_table_name="void_obs")
    handler.register_external_source(spec[0])

    meta = handler._parse_meta_for(str(file_path))
    rows, total, refused = handler._resolve_rows(
        str(file_path), t_name="void_obs", table_info=VOID_INFO, meta=meta)
    assert total == 1 and refused == 0
    assert rows[0]["base_wafer_id"] == "WF-001"
    assert meta["source_kind"] == "external:voids_json:v1"
