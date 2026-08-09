"""Contract tests for the automatic DT alignment metadata chain."""
from __future__ import annotations

import importlib
from pathlib import Path


mapper = importlib.import_module("mappers.dt_alignment_metadata_mapper")


def _payload(dt_job="DT-J1"):
    return {"row_id": "r1", "data": {"dt_job": {"value": dt_job}}}


def _view(*, index_axis="ranking", geometry_assumed=False, source_geometry="declared"):
    return {
        "state": "scored",
        "ruling": {
            "winner": "rot90_front",
            "metric": "index",
            "index_axis": index_axis,
            "geometry_assumed": geometry_assumed,
            "thresholds_defaulted": False,
            "by_frame": {
                "rot90_front": {
                    "shift": {"dx": 0, "dy": 0},
                    "anchor": {"anchor_src": [1, 1], "anchor_ref": [1, 1]},
                }
            },
        },
        "reference": {"state": "resolved", "table": "valid_die_ref", "map_id": "QA_MAP2", "truncated": False},
        "sources": {"truncated": False, "maps": [{"map_id": "DT-J1", "geometry": source_geometry}]},
        "stats": {"truncated": False},
    }


def _rule():
    return {
        "alignment_rule": "dt_frame_confrimation",
        "map_table": "dt_log",
        "metadata_target_table": "dt_log",
    }


def _wire_success(monkeypatch, view=None):
    monkeypatch.setattr(mapper.alignment_view_service, "declared_alignment_rule",
                        lambda _name: {"decision_key": ["dt_job"]})
    monkeypatch.setattr(mapper.alignment_view_service, "resolve_alignment_view",
                        lambda *_a, **_kw: view or _view())
    monkeypatch.setattr(mapper.map_overlay, "load_overlay_config", lambda: {})
    monkeypatch.setattr(mapper.map_overlay, "load_map_meta", lambda *_a: {"grid_cols": 2})
    monkeypatch.setattr(mapper, "_basis_cells_for", lambda *_a: [(1, 1)])
    monkeypatch.setattr(mapper.map_alignment, "_load_metas", lambda *_a: {})
    monkeypatch.setattr(mapper.map_meta_registrar, "meta_business_key",
                        lambda table, map_id: "%s_%s" % (table, map_id))


def test_winner_becomes_one_dt_log_metadata_update(monkeypatch):
    _wire_success(monkeypatch)
    seen = {}

    def project(existing, basis_meta, basis, frame, mark, shift, **kwargs):
        seen.update(existing=existing, basis_meta=basis_meta, basis=basis, frame=frame,
                    mark=mark, shift=shift, kwargs=kwargs)
        return {"rotation": 90, "side": "front", "frame_confirmed_from": mark}

    monkeypatch.setattr(mapper.map_alignment, "confirmed_meta_for", project)
    out = mapper.build_dt_alignment_metadata_batch(None, [_payload()], _rule())

    assert len(out["updates"]) == 1
    item = out["updates"][0]
    assert item["business_key_val"] == "dt_log_DT-J1"
    assert item["updates"]["target_table"] == "dt_log"
    assert item["updates"]["map_id"] == "DT-J1"
    assert item["source_name"] == "chain_ingestion"
    assert seen["basis"] == {"table": "valid_die_ref", "map_id": "QA_MAP2"}
    assert seen["frame"] == "rot90_front"
    assert seen["shift"]["anchor_src"] == [1, 1]
    assert seen["mark"]["source"] == "chain_alignment"


def test_replay_shaped_payload_keeps_the_dt_job_decision_key(monkeypatch):
    _wire_success(monkeypatch)
    monkeypatch.setattr(mapper.map_alignment, "confirmed_meta_for",
                        lambda *_a, **_kw: {"rotation": 90, "side": "front"})

    out = mapper.build_dt_alignment_metadata_batch(None, [_payload()], _rule())

    assert len(out["updates"]) == 1
    assert out["updates"][0]["updates"]["map_id"] == "DT-J1"


def test_index_axis_absent_is_a_noop(monkeypatch):
    _wire_success(monkeypatch, _view(index_axis="absent"))
    monkeypatch.setattr(mapper.map_alignment, "confirmed_meta_for",
                        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("must not project")))
    out = mapper.build_dt_alignment_metadata_batch(None, [_payload()], _rule())
    assert out == {"updates": []}


def test_reference_geometry_bootstrap_is_explicit_and_absent_only():
    assumed_absent = _view(geometry_assumed=True, source_geometry="absent")
    bootstrap_rule = dict(_rule(), geometry_bootstrap="reference_only")

    assert not mapper._automatic_gate(assumed_absent, _rule(), "valid_die_ref:PRD-A_DT13")
    assert not mapper._automatic_gate(assumed_absent, bootstrap_rule, None)
    assert mapper._automatic_gate(assumed_absent, bootstrap_rule, "valid_die_ref:PRD-A_DT13")
    assert not mapper._automatic_gate(
        _view(geometry_assumed=True, source_geometry="declared"),
        bootstrap_rule,
        "valid_die_ref:PRD-A_DT13",
    )


def test_syn_job_uses_declared_valid_die_reference(monkeypatch):
    _wire_success(monkeypatch)
    got = {}
    monkeypatch.setattr(mapper.alignment_view_service, "resolve_alignment_view",
                        lambda *_a, **kw: (got.update(reference_spec=kw["reference_spec"]) or _view()))
    monkeypatch.setattr(mapper.map_alignment, "confirmed_meta_for",
                        lambda *_a, **_kw: {"rotation": 90, "side": "front"})
    rule = dict(_rule(), reference_by_job_pattern=[
        {"contains": "SYN", "reference_spec": "valid_die_ref:PRD-A_DT13"},
    ])
    mapper.build_dt_alignment_metadata_batch(None, [_payload("SYN-IDX-FULL-R90")], rule)
    assert got["reference_spec"] == "valid_die_ref:PRD-A_DT13"


def test_live_mapper_and_tracked_sample_are_byte_identical():
    root = Path(__file__).resolve().parents[1] / "mappers"
    assert (root / "dt_alignment_metadata_mapper.py").read_bytes() == \
           (root / "dt_alignment_metadata_mapper.py.sample").read_bytes()
