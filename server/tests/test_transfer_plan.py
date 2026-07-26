"""Universal Transfer Plan M2 — stage 로더/가용 엔진/validate 검증 (Server_transfer_plan_m2_task).

검증 범위:
- stages API: 선언 stage 목록 + 역할 연결 상태(missing 부분 가동)
- core-kind(dt stage): M1 core-summary의 내부 통합(reshape — fail_breakdown/transferred)
- tape-kind(bonding stage): dt_log total, 코어 fail의 투영 조인(align 180 포함 — 네거티브
  대조군으로 align 실효 증명), by_core 분해, transferred distinct, 합집합 remaining(이중
  감산 없음), align_unavailable 명시 실패, origin_missing 부분 가동
- validate: 수량 부족(칩×층×개당 vs 가용)·층 커버리지·DOE 값-맵 정합·소스 fail 경고·404

[격리] 테이블명은 사용자 실 config에 실존 불가능한 tp_test_* 접두를 사용한다
(conftest가 import 시점에 실 config로 초기화하므로 실존 테이블명과 겹치면 격리 실패).
"""
import json
import uuid

import pytest

import bonding_plan
import transfer_plan
from database import crud, models

# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

TP_TABLES = {
    "tp_test_dt_log": {
        "business_key": "dt_id",
        "column_types": {
            "dt_id": "string", "tape_lot": "string", "tape_slot": "string",
            "tx": "number", "ty": "number",
            "core_lot": "string", "core_slot": "string", "cx": "number", "cy": "number",
        },
    },
    "tp_test_dt_map": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "lot": "string", "slot": "string",
            "x": "number", "y": "number", "val": "string",
        },
    },
    "tp_test_core_defect_map": {
        "business_key": "chip_key",
        "column_types": {
            "chip_key": "string", "lot": "string", "slot": "string",
            "x": "number", "y": "number", "val": "string",
        },
    },
    "tp_test_eds_fail_map": {
        "business_key": "chip_key",
        "column_types": {
            "chip_key": "string", "lot": "string", "slot": "string",
            "x": "number", "y": "number", "val": "string",
        },
    },
    "tp_test_bonding_log": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "core_lot": "string", "core_slot": "string",
            "cx": "number", "cy": "number",
        },
    },
    "tp_test_map_meta": {
        "business_key": "map_pk",
        "column_types": {
            "map_pk": "string", "target_table": "string",
            "map_id": "string", "grid_metadata": "string",
        },
    },
    "tp_test_wafer_process": {
        "business_key": "proc_id",
        "column_types": {
            "proc_id": "string", "lot": "string", "slot": "string",
            "step": "string", "eqp_id": "string", "start_time": "string",
            "result": "string", "recipe_id": "string", "knobs": "string",
        },
    },
    "tp_test_plan": {
        "business_key": "plan_id",
        "column_types": {
            "plan_id": "string", "stage": "string", "target_lot": "string",
            "target_slot": "string", "status": "string", "memo": "string",
        },
    },
    "tp_test_plan_doe": {
        "business_key": "doe_key",
        "column_types": {
            "doe_key": "string", "plan_id": "string", "doe_value": "string",
            "source_lot": "string", "source_slot": "string", "qty_per_unit": "number",
            "layer_from": "number", "layer_to": "number",
            "knobs": "string", "description": "string",
        },
    },
    "tp_test_plan_map": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "plan_id": "string",
            "x": "number", "y": "number", "val": "string",
        },
    },
    "tp_test_plan_region": {   # ② — 소스 사용 영역 (자유 페인팅 셀 집합)
        "business_key": "region_key",
        "column_types": {
            "region_key": "string", "plan_id": "string",
            "source_lot": "string", "source_slot": "string",
            "x": "number", "y": "number", "val": "string",
        },
    },
    "tp_test_plan_doe_layer": {   # S3 — DOE 층별 세분화
        "business_key": "layer_key",
        "column_types": {
            "layer_key": "string", "doe_key": "string", "layer": "number",
            "source_lot": "string", "source_slot": "string", "qty": "number",
            "note": "string",
        },
    },
}

GRID = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
        "grid_y_invert": False, "side": "front",
        "phys_wafer_dia": 300, "phys_chip_x": 7, "phys_chip_y": 7,
        "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3}


def _bp_config():
    """M1-shape config (dt stage의 source_config_ref가 참조 — tp_test_* 바인딩)."""
    return {
        "core_identity": {"compose": ["lot", "slot"]},
        "map_metadata": {
            "table": "tp_test_map_meta",
            "columns": {"target_table": "target_table", "map_id": "map_id",
                        "grid_metadata": "grid_metadata"},
        },
        "sources": {
            "process_history": {
                "table": "tp_test_wafer_process",
                "columns": {"step": "step", "eqp": "eqp_id", "result": "result",
                            "time": "start_time", "recipe": "recipe_id",
                            "knobs": "knobs", "lot": "lot", "slot": "slot"},
            },
            "defect": {
                "mode": "map", "table": "tp_test_core_defect_map",
                "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val"},
                "fail_values": ["D"],
            },
            "eds_fail": {
                "mode": "map", "table": "tp_test_eds_fail_map",
                "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val"},
                "fail_values": ["F"],
                "align": {"default": {"rotation": 180}, "by_eqp": {}},
            },
            "used_chips": {
                "table": "tp_test_bonding_log",
                "columns": {"lot": "core_lot", "slot": "core_slot", "x": "cx", "y": "cy"},
            },
            "total_chips": {
                "mode": "map", "table": "tp_test_core_defect_map",
                "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y"},
            },
        },
        "warnings": {"result_fail_values": ["FAIL"]},
    }


def _tp_config(align_eds=True):
    cfg = {
        "stages": {
            "dt": {
                "description": "core→tape 전사",
                "source_kind": "core", "target_kind": "tape",
                "source_config_ref": "bonding_plan",
                "target_map": {"preset": "TAPE", "table": "tp_test_dt_map"},
            },
            "bonding": {
                "description": "tape→base 본딩",
                "source_kind": "tape", "target_kind": "base",
                "source": {
                    "identity": {"compose": ["lot", "slot"]},
                    "map_metadata": {
                        "table": "tp_test_map_meta",
                        "columns": {"target_table": "target_table", "map_id": "map_id",
                                    "grid_metadata": "grid_metadata"},
                    },
                    "total_chips": {
                        "table": "tp_test_dt_log",
                        "columns": {"lot": "tape_lot", "slot": "tape_slot", "x": "tx", "y": "ty"},
                    },
                    "transfer_log": {
                        "table": "tp_test_bonding_log",
                        "columns": {"lot": "core_lot", "slot": "core_slot", "x": "cx", "y": "cy"},
                    },
                    "origin_log": {
                        "table": "tp_test_dt_log",
                        "columns": {"lot": "tape_lot", "slot": "tape_slot", "x": "tx", "y": "ty",
                                    "origin_lot": "core_lot", "origin_slot": "core_slot",
                                    "origin_x": "cx", "origin_y": "cy"},
                    },
                    "origin_area_map": {
                        "table": "tp_test_dt_map",
                        "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val"},
                    },
                    "process_history": {
                        "table": "tp_test_wafer_process",
                        "columns": {"step": "step", "eqp": "eqp_id", "result": "result",
                                    "time": "start_time", "recipe": "recipe_id",
                                    "knobs": "knobs", "lot": "lot", "slot": "slot"},
                    },
                    "fail_sources": {
                        "defect": {
                            "frame": "origin", "table": "tp_test_core_defect_map",
                            "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val"},
                            "fail_values": ["D"],
                        },
                        "eds_fail": {
                            "frame": "origin", "table": "tp_test_eds_fail_map",
                            "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val"},
                            "fail_values": ["F"],
                        },
                    },
                    "warnings": {"result_fail_values": ["FAIL"]},
                },
                "target_map": {"preset": "BASE", "table": "tp_test_bonding_map"},
            },
        },
        "plan_store": {
            "plan": {"table": "tp_test_plan",
                     "columns": {"plan_id": "plan_id", "stage": "stage",
                                 "target_lot": "target_lot", "target_slot": "target_slot",
                                 "status": "status", "memo": "memo"}},
            "doe": {"table": "tp_test_plan_doe",
                    "columns": {"plan_id": "plan_id", "doe_value": "doe_value",
                                "source_lot": "source_lot", "source_slot": "source_slot",
                                "qty_per_unit": "qty_per_unit", "layer_from": "layer_from",
                                "layer_to": "layer_to", "knobs": "knobs",
                                "description": "description"}},
            "map": {"table": "tp_test_plan_map",
                    "columns": {"plan_id": "plan_id", "x": "x", "y": "y", "val": "val"}},
            "source_region": {"table": "tp_test_plan_region",
                              "columns": {"plan_id": "plan_id", "source_lot": "source_lot",
                                          "source_slot": "source_slot", "x": "x", "y": "y",
                                          "val": "val"}},
            "doe_layer": {"table": "tp_test_plan_doe_layer",
                          "columns": {"doe_key": "doe_key", "layer": "layer",
                                      "source_lot": "source_lot", "source_slot": "source_slot",
                                      "qty": "qty", "note": "note"}},
        },
    }
    if align_eds:
        cfg["stages"]["bonding"]["source"]["fail_sources"]["eds_fail"]["align"] = {
            "default": {"rotation": 180}, "by_eqp": {},
        }
    return cfg


def _add(db, table, **cols):
    model = models.DYNAMIC_TABLES[table]
    bk = TP_TABLES[table]["business_key"]
    row = model(row_id=str(uuid.uuid4()),
                business_key_val=str(cols.get(bk) or uuid.uuid4()), **cols)
    db.add(row)
    return row


def _add_meta(db, target_table, map_id, rotation=0, cols=6, rows=6):
    meta = dict(GRID)
    meta["rotation"] = rotation
    meta["grid_cols"] = cols
    meta["grid_rows"] = rows
    _add(db, "tp_test_map_meta",
         map_pk=f"{target_table}_{map_id}", target_table=target_table,
         map_id=map_id, grid_metadata=json.dumps(meta))


def _write_cfg(tmp_path, monkeypatch, tp_cfg=None, bp_cfg=None):
    tp_path = tmp_path / f"tp_{uuid.uuid4().hex[:6]}.json"
    tp_path.write_text(json.dumps(tp_cfg if tp_cfg is not None else _tp_config()),
                       encoding="utf-8")
    monkeypatch.setattr(transfer_plan, "CONFIG_PATH", str(tp_path))
    bp_path = tmp_path / f"bp_{uuid.uuid4().hex[:6]}.json"
    bp_path.write_text(json.dumps(bp_cfg if bp_cfg is not None else _bp_config()),
                       encoding="utf-8")
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(bp_path))


@pytest.fixture()
def tp_env(db_session, tmp_path, monkeypatch):
    """tp_test_* 테이블 등록 + config 스냅샷 경로 monkeypatch."""
    models.init_dynamic_models(TP_TABLES)
    crud.TABLE_CONFIG.update(TP_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    _write_cfg(tmp_path, monkeypatch)
    return db_session


def _seed_scenario(db):
    """기준 시나리오.

    코어 프레임 6x6 (start 1,1). 코어 2장:
    - CORE-A/01: defect 풀맵 36칩, (2,2)·(3,3)="D". eds fail canonical (1,1) →
      저장좌표 (6,6) (자기 프레임 180° 회전 — meta rotation 180).
    - CORE-B/02: defect fail (1,1)="D" 1행. eds fail canonical (4,4) → 저장 (3,3).

    테이프 TAPE-X/01 (8칩 — 두 코어 혼재, 불량 칩도 전사됨):
    - CORE-A origins (1,1)(2,2)(1,2)(2,1) → tape (1,1)(2,1)(3,1)(4,1)
    - CORE-B origins (1,1)(4,4)(5,5)(6,6) → tape (1,2)(2,2)(3,2)(4,2)
    투영 기대: defect → tape {(2,1) [A(2,2)], (1,2) [B(1,1)]},
              eds(align 180) → tape {(1,1) [A(1,1)], (2,2) [B(4,4)]}
    기전사(bonding_log, tape identity): (3,1), (4,2), (2,1)+중복 → distinct 3 ((2,1)은 fail과 중복)
    remaining = 8 − |fail∪used| = 8 − 6 = 2 (감산식이면 1 — 합집합 의미론 검증점)
    """
    # CORE-A defect 풀맵
    for y in range(1, 7):
        for x in range(1, 7):
            val = "D" if (x, y) in ((2, 2), (3, 3)) else "P"
            _add(db, "tp_test_core_defect_map",
                 chip_key=f"A_{x}_{y}", lot="CORE-A", slot="01", x=x, y=y, val=val)
    # CORE-B defect fail 1행
    _add(db, "tp_test_core_defect_map",
         chip_key="B_1_1", lot="CORE-B", slot="02", x=1, y=1, val="D")
    # canonical(core) 프레임 메타 — align 미선언 원천이 dst_grid 원천이 된다 (QA F6).
    # 라이브에서도 generate_core_defect.py가 동일 관례로 등록한다.
    _add_meta(db, "tp_test_core_defect_map", "CORE-A_01", rotation=0)
    _add_meta(db, "tp_test_core_defect_map", "CORE-B_02", rotation=0)

    # eds (자기 프레임 180° — 저장 = 7 − canonical)
    _add(db, "tp_test_eds_fail_map", chip_key="EA", lot="CORE-A", slot="01",
         x=6, y=6, val="F")  # canonical (1,1)
    _add(db, "tp_test_eds_fail_map", chip_key="EB", lot="CORE-B", slot="02",
         x=3, y=3, val="F")  # canonical (4,4)
    _add_meta(db, "tp_test_eds_fail_map", "CORE-A_01", rotation=180)
    _add_meta(db, "tp_test_eds_fail_map", "CORE-B_02", rotation=180)

    # dt_log — TAPE-X/01
    chips = [
        ("CORE-A", "01", 1, 1, 1, 1), ("CORE-A", "01", 2, 2, 2, 1),
        ("CORE-A", "01", 1, 2, 3, 1), ("CORE-A", "01", 2, 1, 4, 1),
        ("CORE-B", "02", 1, 1, 1, 2), ("CORE-B", "02", 4, 4, 2, 2),
        ("CORE-B", "02", 5, 5, 3, 2), ("CORE-B", "02", 6, 6, 4, 2),
    ]
    for i, (cl, cs, cx, cy, tx, ty) in enumerate(chips):
        _add(db, "tp_test_dt_log", dt_id=f"DT-{i}", tape_lot="TAPE-X", tape_slot="01",
             tx=tx, ty=ty, core_lot=cl, core_slot=cs, cx=cx, cy=cy)
        # dt_map: 테이프 좌표 → 출신 코어 식별(영역 귀속 — origin_log 강등 시 by_core 원천)
        _add(db, "tp_test_dt_map", cell_key=f"TAPE-X_01_{tx}_{ty}",
             lot="TAPE-X", slot="01", x=tx, y=ty, val=f"{cl}_{cs}")

    # 기전사 (tape identity로 기록 — 스펙: bonding_log의 core_*는 실제로는 tape)
    for i, (tx, ty) in enumerate([(3, 1), (4, 2), (2, 1), (2, 1)]):
        _add(db, "tp_test_bonding_log", log_id=f"TBL-{i}",
             core_lot="TAPE-X", core_slot="01", cx=tx, cy=ty)

    # 테이프 이력 1건 (FAIL — warnings 검증)
    _add(db, "tp_test_wafer_process", proc_id="TP-H1", lot="TAPE-X", slot="01",
         step="DT", eqp_id="DT-01", start_time="2026-07-26 08:00", result="FAIL",
         recipe_id="R-DT-01", knobs=json.dumps({"tension": 1.1}))
    db.commit()


# ---------------------------------------------------------------------------
# 1. stages API
# ---------------------------------------------------------------------------

def test_stages_listing_and_role_status(tp_env, client):
    res = client.get("/api/transfer-plan/stages")
    assert res.status_code == 200
    body = res.json()
    names = {s["name"]: s for s in body["stages"]}
    assert set(names) == {"dt", "bonding"}

    dt = names["dt"]
    assert dt["source_kind"] == "core" and dt["target_kind"] == "tape"
    assert dt["target_map"]["preset"] == "TAPE"
    assert dt["roles"]["total_chips"] == "connected"
    assert dt["roles"]["transfer_log"] == "connected"
    assert dt["roles"]["defect"] == "connected"

    bd = names["bonding"]
    assert bd["roles"]["origin_log"] == "connected"
    assert bd["roles"]["eds_fail"] == "connected"

    assert body["plan_store"] == {"plan": "connected", "doe": "connected",
                                  "map": "connected", "doe_layer": "connected",
                                  "source_region": "connected"}


def test_stages_missing_roles_partial(tp_env, client, tmp_path, monkeypatch):
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    del cfg["plan_store"]["map"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/stages").json()
    bd = {s["name"]: s for s in body["stages"]}["bonding"]
    assert bd["roles"]["origin_log"] == "missing"
    assert body["plan_store"]["map"] == "missing"


def test_stages_empty_config(tp_env, client, tmp_path, monkeypatch):
    monkeypatch.setattr(transfer_plan, "CONFIG_PATH", str(tmp_path / "none.json"))
    body = client.get("/api/transfer-plan/stages").json()
    assert body["stages"] == []


# ---------------------------------------------------------------------------
# 2. core-kind (dt stage) — M1 내부 통합 reshape
# ---------------------------------------------------------------------------

def test_dt_stage_reshapes_m1_summary(tp_env, client):
    _seed_scenario(tp_env)
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "dt", "lot": "CORE-A", "slot": "01"})
    assert res.status_code == 200
    body = res.json()
    assert body["stage"] == "dt" and body["source_kind"] == "core"
    assert body["identity"] == {"lot": "CORE-A", "slot": "01"}
    # M1 집계의 재성형: total 36, defect 2, eds 1(F행 1), used 0 → remaining 33
    assert body["chips"] == {
        "total": 36,
        "fail_breakdown": {"defect": 2, "eds_fail": 1},
        "transferred": 0,
        "remaining": 33,
        "remaining_reliable": True,   # 전 역할 정상 → 신뢰 가능(상한 필드 없음)
    }
    assert body["sources"]["transfer_log"] == "connected"
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"
    assert "by_core" not in body


def test_unknown_stage_404(tp_env, client):
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "nope", "lot": "L", "slot": "1"})
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 3. tape-kind (bonding stage) — 투영·by_core·합집합 remaining
# ---------------------------------------------------------------------------

def test_tape_summary_projection_and_by_core(tp_env, client):
    _seed_scenario(tp_env)
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"})
    assert res.status_code == 200
    body = res.json()
    assert body["source_kind"] == "tape"
    assert body["chips"]["total"] == 8
    assert body["chips"]["fail_breakdown"] == {"defect": 2, "eds_fail": 2}
    assert body["chips"]["transferred"] == 3          # distinct (3,1)(4,2)(2,1)
    # 합집합 의미론: fail∪used = 6 → remaining 2 (감산식이면 1 — 이중 감산 없음 검증)
    assert body["chips"]["remaining"] == 2

    assert body["sources"]["total_chips"] == "connected"
    assert body["sources"]["origin_log"] == "connected"
    assert body["sources"]["defect"] == "connected"
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"

    assert body["by_core_origin"] == "log"
    by_core = {(r["core_lot"], r["core_slot"]): r for r in body["by_core"]}
    assert by_core[("CORE-A", "01")] == {
        "core_id": "CORE-A|01", "core_lot": "CORE-A", "core_slot": "01",
        "total": 4, "fail": 2, "used": 2, "remaining": 1,
    }
    assert by_core[("CORE-B", "02")] == {
        "core_id": "CORE-B|02", "core_lot": "CORE-B", "core_slot": "02",
        "total": 4, "fail": 2, "used": 1, "remaining": 1,
    }
    # 이력 경고 (테이프 자체 이력)
    assert body["warnings"] and body["warnings"][0]["type"] == "result_fail"
    assert body["history"][0]["step"] == "DT"


def test_tape_projection_align_negative_control(tp_env, client, tmp_path, monkeypatch):
    """eds align 미선언 → 저장(회전) 좌표 그대로 조인되어 투영 0 — align 실효 대조군."""
    _seed_scenario(tp_env)
    _write_cfg(tmp_path, monkeypatch, tp_cfg=_tp_config(align_eds=False))
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert body["chips"]["fail_breakdown"]["eds_fail"] == 0
    assert body["chips"]["fail_breakdown"]["defect"] == 2  # 무회전 소스는 불변
    assert body["sources"]["eds_fail"] == "connected"


def test_tape_projection_align_unavailable(tp_env, client):
    """align 선언 + grid meta 부재 코어 → 조용히 raw 계산하지 않고 명시 실패 (QA F2 승계)."""
    db = tp_env
    _add(db, "tp_test_eds_fail_map", chip_key="EC", lot="CORE-C", slot="03",
         x=6, y=6, val="F")  # meta 미등록
    _add(db, "tp_test_dt_log", dt_id="DT-C0", tape_lot="TAPE-Y", tape_slot="01",
         tx=1, ty=1, core_lot="CORE-C", core_slot="03", cx=1, cy=1)
    db.commit()
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-Y", "slot": "01"}).json()
    assert body["sources"]["eds_fail"] == "connected(align_unavailable)"
    assert body["chips"]["fail_breakdown"]["eds_fail"] == 0
    assert body["chips"]["total"] == 1


def test_tape_origin_missing_falls_back_to_area_map(tp_env, client, tmp_path, monkeypatch):
    """origin_log 미해석 → fail 투영은 unavailable, by_core는 dt_map 영역 귀속으로 강등 제공."""
    _seed_scenario(tp_env)
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert body["sources"]["origin_log"] == "missing"
    assert body["sources"]["defect"] == "unavailable(origin_missing)"
    assert body["sources"]["origin_area_map"] == "connected(area_only)"
    assert body["chips"]["fail_breakdown"] == {"defect": 0, "eds_fail": 0}
    assert body["chips"]["total"] == 8
    assert body["chips"]["transferred"] == 3

    # [QA F1 회귀] 강등 시 과대 remaining(5)을 정답으로 고정하지 않는다.
    # origin_log가 무너져 fail 투영이 0이 됐으므로 remaining은 신뢰 불가여야 한다.
    assert body["chips"]["remaining"] is None, "강등 상태의 remaining을 숫자로 내면 안 된다"
    assert body["chips"]["remaining_reliable"] is False
    # total은 여전히 신뢰 가능 → 계산값 5는 '상한'으로만 제공 (실제 정답 2 ≤ 5)
    assert body["chips"]["remaining_upper_bound"] == 5

    # 강등이 warnings로 표면화돼야 한다 (sources 문자열만으로는 부족)
    deg = [w for w in body["warnings"] if w["type"] == "source_degraded"]
    roles = {w["role"] for w in deg}
    assert "origin_log" in roles
    assert any(w["effect"] == "remaining_overstated" for w in deg)

    assert body["by_core_origin"] == "area_map"
    # 영역 귀속 분해: fail은 투영 불가라 null(0으로 위장하지 않는다)
    by_core = {r["core_id"]: r for r in body["by_core"]}
    assert set(by_core) == {"CORE-A_01", "CORE-B_02"}
    assert by_core["CORE-A_01"]["total"] == 4 and by_core["CORE-A_01"]["used"] == 2
    assert by_core["CORE-A_01"]["fail"] is None
    assert by_core["CORE-A_01"]["remaining"] == 2
    # lot/slot 분해 근거가 없으므로 추측 파싱하지 않는다
    assert by_core["CORE-A_01"]["core_lot"] is None
    assert by_core["CORE-A_01"]["core_slot"] is None


def test_by_core_key_set_identical_across_paths(tp_env, client, tmp_path, monkeypatch):
    """[경계 계약] log/area_map 두 경로의 by_core 항목 키 집합이 완전히 동일해야 한다.

    클라가 경로별 분기 없이 같은 렌더러를 쓰게 하는 것이 목적 — 경로 구분은
    by_core_origin 마커 하나로만 한다.
    """
    _seed_scenario(tp_env)
    expected_keys = {"core_id", "core_lot", "core_slot", "total", "fail", "used", "remaining"}

    # 경로 1: origin_log (정본)
    log_body = client.get("/api/transfer-plan/source-summary",
                          params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert log_body["by_core_origin"] == "log"
    log_keys = [set(r) for r in log_body["by_core"]]
    assert log_keys and all(k == expected_keys for k in log_keys)

    # 경로 2: origin_area_map (강등)
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    area_body = client.get("/api/transfer-plan/source-summary",
                           params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert area_body["by_core_origin"] == "area_map"
    area_keys = [set(r) for r in area_body["by_core"]]
    assert area_keys and all(k == expected_keys for k in area_keys)

    # 두 경로의 core 개수도 동일(같은 데이터의 두 관점)
    assert len(log_body["by_core"]) == len(area_body["by_core"])


def test_tape_origin_and_area_both_missing(tp_env, client, tmp_path, monkeypatch):
    """영역 맵마저 없으면 by_core 자체를 싣지 않는다(빈 배열로 위장 금지)."""
    _seed_scenario(tp_env)
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    del cfg["stages"]["bonding"]["source"]["origin_area_map"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert "by_core" not in body
    assert "by_core_origin" not in body   # 마커도 함께 부재 (경로 없음)
    assert "origin_area_map" not in body["sources"]


def test_tape_unknown_combo_zero(tp_env, client):
    _seed_scenario(tp_env)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-Z", "slot": "99"}).json()
    assert body["chips"]["total"] == 0
    assert body["chips"]["remaining"] == 0
    assert body["by_core"] == []


# ---------------------------------------------------------------------------
# 3-bis. [QA F1] 역할 강등의 표면화 — "조용한 과대 산출" 차단
# ---------------------------------------------------------------------------

def _degraded_roles(body):
    return {w["role"]: w for w in body["warnings"] if w["type"] == "source_degraded"}


def test_degraded_align_meta_missing_is_surfaced(tp_env, client):
    """QA 실측 시나리오 2: eds grid meta 부재 → fail 과소 → remaining 과대(209→226 유형).

    align_unavailable은 sources에만 적히고 warnings는 비어 있었다 — 그것이 F1의 핵심.
    """
    db = tp_env
    # CORE-A/01의 eds 메타만 제거한 상태를 만들기 위해 메타 없는 코어로 테이프 구성
    for y in range(1, 4):
        _add(db, "tp_test_core_defect_map", chip_key=f"M_{y}", lot="CORE-M", slot="01",
             x=1, y=y, val="D" if y == 1 else "P")
    _add(db, "tp_test_eds_fail_map", chip_key="EM", lot="CORE-M", slot="01",
         x=6, y=6, val="F")            # meta 미등록 → align 해석 불가
    for i, y in enumerate((1, 2, 3)):
        _add(db, "tp_test_dt_log", dt_id=f"DTM-{i}", tape_lot="TAPE-M", tape_slot="01",
             tx=i + 1, ty=1, core_lot="CORE-M", core_slot="01", cx=1, cy=y)
    db.commit()

    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-M", "slot": "01"}).json()
    assert body["sources"]["eds_fail"] == "connected(align_unavailable)"
    # 과대 산출 값을 그대로 내지 않는다
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
    deg = _degraded_roles(body)
    assert "eds_fail" in deg
    assert deg["eds_fail"]["effect"] == "remaining_overstated"
    assert "과대" in deg["eds_fail"]["detail"]


def test_degraded_fail_source_broken_is_surfaced(tp_env, client, tmp_path, monkeypatch):
    """QA 실측 시나리오 3: fail 원천 1종 테이블 파손 → remaining 과대(209→236 유형)."""
    _seed_scenario(tp_env)
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["fail_sources"]["defect"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert body["sources"]["defect"] == "missing"
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
    # total은 정상이므로 상한은 제공된다.
    # defect 투영이 누락돼 fail_union = eds 2칩뿐 → |fail∪used| = |{(1,1),(2,2),(3,1),(4,2),(2,1)}| = 5
    # → 상한 8−5 = 3. 정답 2보다 크므로 진짜 상한이 맞다(과대 방향).
    assert body["chips"]["remaining_upper_bound"] == 3
    assert "defect" in _degraded_roles(body)


def test_negative_remaining_is_flagged_as_population_mismatch(tp_env, client):
    """[QA N1 불변식] remaining < 0은 물리적으로 불가능 — 전 역할 connected여도 신뢰 불가.

    실측 사례(LOT-D/05)는 전 역할 connected + 경고 0 + 음수였다. 감산항이 총칩을 넘었다는
    건 원천 간 모집단이 어긋났다는 뜻이므로 숫자를 그대로 내보내면 안 된다.
    """
    db = tp_env
    # total 1칩인데 기전사가 총칩에 없는 좌표 3개 → remaining 음수 유도
    _add(db, "tp_test_dt_log", dt_id="DTN", tape_lot="TAPE-N", tape_slot="01",
         tx=1, ty=1, core_lot="CORE-A", core_slot="01", cx=1, cy=1)
    for i, (tx, ty) in enumerate([(50, 50), (51, 51), (52, 52)]):
        _add(db, "tp_test_bonding_log", log_id=f"NBL-{i}",
             core_lot="TAPE-N", core_slot="01", cx=tx, cy=ty)
    db.commit()

    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-N", "slot": "01"}).json()
    assert body["chips"]["total"] == 1
    assert body["chips"]["transferred"] == 3
    # 음수(total 1 − |기전사 3| = −2)를 그대로 내지 않는다
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
    # 음수는 상한으로서도 무의미하므로 upper_bound를 싣지 않는다
    assert "remaining_upper_bound" not in body["chips"]
    neg = [w for w in body["warnings"] if w["type"] == "negative_remaining"]
    assert len(neg) == 1
    assert neg[0]["effect"] == "population_mismatch"
    assert neg[0]["computed"] == -2


def test_normal_path_is_reliable_and_quiet(tp_env, client):
    """[대조군] 정상 경로는 신뢰 플래그 true + 강등 경고 0 — 오탐이 없어야 한다.

    align이 정상 적용된 connected(aligned:180)을 강등으로 오분류하면 상시 오탐이 되어
    진짜 경고를 가린다(QA 교훈 4).
    """
    _seed_scenario(tp_env)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"
    assert body["chips"]["remaining"] == 2
    assert body["chips"]["remaining_reliable"] is True
    assert "remaining_upper_bound" not in body["chips"]
    assert _degraded_roles(body) == {}


def test_dt_stage_degradation_also_surfaced(tp_env, client, tmp_path, monkeypatch):
    """core-kind(M1 reshape) 경로도 동일 규율 — 여기만 빠지면 우회로가 남는다."""
    _seed_scenario(tp_env)
    bp = _bp_config()
    del bp["sources"]["defect"]          # 역할 제거 → missing
    _write_cfg(tmp_path, monkeypatch, bp_cfg=bp)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "dt", "lot": "CORE-A", "slot": "01"}).json()
    assert body["sources"]["defect"] == "missing"
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
    assert "defect" in _degraded_roles(body)


def test_degraded_total_has_no_upper_bound(tp_env, client, tmp_path, monkeypatch):
    """total까지 강등되면 계산값은 상한이 아니다 — upper_bound를 싣지 않는다."""
    _seed_scenario(tp_env)
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["total_chips"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
    assert "remaining_upper_bound" not in body["chips"]
    assert _degraded_roles(body)["total_chips"]["effect"] == "total_unknown"


def test_history_degradation_does_not_taint_remaining(tp_env, client, tmp_path, monkeypatch):
    """이력 역할 강등은 remaining과 무관 — 과잉 강등(오탐)으로 번지면 안 된다."""
    _seed_scenario(tp_env)
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["process_history"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert body["chips"]["remaining"] == 2          # 정상 값 유지
    assert body["chips"]["remaining_reliable"] is True
    assert _degraded_roles(body)["process_history"]["effect"] == "history_incomplete"


# ---------------------------------------------------------------------------
# 3-ter. [QA F2] 하드캡 절단 표면화 / [QA F6] align dst_grid 정합
# ---------------------------------------------------------------------------

def test_cap_truncation_is_surfaced_and_taints_remaining(tp_env, client, monkeypatch):
    """[QA F2] 캡에 걸리면 sources는 전부 connected인데 수치만 조용히 틀린다 — 차단.

    total은 count()라 절단되지 않으므로 분자·분모의 모집단이 어긋난다.
    """
    _seed_scenario(tp_env)
    # origin_log 8칩 < 캡이므로, 캡을 3으로 낮춰 절단을 재현한다(QA가 쓴 기법).
    monkeypatch.setattr(transfer_plan, "MAX_ORIGIN_POINTS", 3)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()

    assert body["sources"]["origin_log"] == "connected"   # 상태는 정상으로 보인다
    assert body["chips"]["total"] == 8                    # count()는 절단 안 됨
    # 그래도 조용히 넘어가지 않는다
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
    trunc = [w for w in body["warnings"] if w["type"] == "result_truncated"]
    assert trunc, "절단 사실이 응답에 실려야 한다"
    assert {t["role"] for t in body["truncated"]} & {"origin_log", "transfer_log"}


def test_by_core_truncation_is_flagged(tp_env, client, monkeypatch):
    """by_core 절단은 remaining과 무관하지만 sum(by_core.total) != total을 알려야 한다."""
    _seed_scenario(tp_env)
    monkeypatch.setattr(transfer_plan, "MAX_BY_CORE", 1)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert len(body["by_core"]) == 1
    assert body["by_core_truncated"] is True
    tw = [w for w in body["warnings"]
          if w["type"] == "result_truncated" and w["role"] == "by_core"]
    assert len(tw) == 1 and tw[0]["effect"] == "by_core_degraded"
    # by_core 절단만으로는 remaining을 오염시키지 않는다(과잉 강등 방지)
    assert body["chips"]["remaining_reliable"] is True


def test_no_truncation_field_when_within_caps(tp_env, client):
    """[대조군] 캡 미도달이면 truncated 필드도 경고도 없어야 한다."""
    _seed_scenario(tp_env)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert "truncated" not in body
    assert body["by_core_truncated"] is False
    assert not [w for w in body["warnings"] if w["type"] == "result_truncated"]


def test_align_dst_grid_mismatch_is_explicit_failure(tp_env, client, tmp_path, monkeypatch):
    """[QA F6] canonical(dst) 격자를 넘기므로 프레임 치수 모순이 명시 실패로 잡힌다.

    dst_grid를 생략하면 이 모순 검증(ValueError 가드)이 통째로 건너뛰어져 어긋난 좌표로
    조용히 투영된다 — M1은 막지만 M2는 통과하던 경로.
    """
    db = tp_env
    # canonical(defect)은 4x6, eds 자기 프레임은 4x6인데 rot 90 → 스왑 관계(6x4)와 모순
    _add(db, "tp_test_core_defect_map", chip_key="Z_1_1", lot="CORE-Z", slot="01",
         x=1, y=1, val="P")
    _add_meta(db, "tp_test_core_defect_map", "CORE-Z_01", rotation=0, cols=4, rows=6)
    _add(db, "tp_test_eds_fail_map", chip_key="EZ", lot="CORE-Z", slot="01",
         x=1, y=1, val="F")
    _add_meta(db, "tp_test_eds_fail_map", "CORE-Z_01", rotation=90, cols=4, rows=6)
    _add(db, "tp_test_dt_log", dt_id="DTZ", tape_lot="TAPE-Z9", tape_slot="01",
         tx=1, ty=1, core_lot="CORE-Z", core_slot="01", cx=1, cy=1)
    db.commit()

    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["fail_sources"]["eds_fail"]["align"] = {
        "default": {"rotation": 90}, "by_eqp": {},
    }
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-Z9", "slot": "01"}).json()
    # 조용한 오답이 아니라 명시 실패 + 강등 표면화
    assert body["sources"]["eds_fail"] == "connected(align_unavailable)"
    assert body["chips"]["remaining_reliable"] is False


def test_align_dst_grid_is_passed_to_transform(tp_env, monkeypatch):
    """[QA F6] _canonical_fail_set이 make_align_transform에 dst_grid를 실제로 넘기는지 직접 확인."""
    _seed_scenario(tp_env)
    captured = {}
    import bonding_plan as bp
    orig = bp.make_align_transform

    def spy(align, src_grid, dst_grid=None):
        captured["dst_grid"] = dst_grid
        return orig(align, src_grid, dst_grid)

    monkeypatch.setattr(bp, "make_align_transform", spy)
    cfg = transfer_plan.load_transfer_plan_config()
    transfer_plan.get_stage_source_summary(tp_env, cfg, "bonding", "TAPE-X", "01")
    assert "dst_grid" in captured, "align 변환이 호출되지 않았다"
    # canonical(defect 맵, align 미선언)의 격자가 dst로 전달돼야 한다
    assert captured["dst_grid"] is not None, "dst_grid가 None이면 M1의 정합 검증이 무력화된다"
    assert captured["dst_grid"]["cols"] == 6 and captured["dst_grid"]["rows"] == 6


# ---------------------------------------------------------------------------
# 3-quater. [②] 소스 사용 영역 영속화 — 자유 페인팅 셀 집합 스코프
# ---------------------------------------------------------------------------

def _seed_region(db, plan_id, source, cells, val="USE"):
    for (x, y) in cells:
        _add(db, "tp_test_plan_region",
             region_key=f"{plan_id}|{source[0]}|{source[1]}|{x}|{y}",
             plan_id=plan_id, source_lot=source[0], source_slot=source[1],
             x=x, y=y, val=val)


def test_source_region_scopes_tape_availability(tp_env, client):
    """[②] 테이프 소스 — 영역 셀 집합으로 좁힌 가용이 산출된다.

    전체: total 8, fail∪used 6, remaining 2.
    영역 {(1,1),(2,1),(3,1),(4,1)} (CORE-A 밴드): total 4,
      fail (1,1)eds·(2,1)defect = 2, used (3,1)·(2,1) → 영역 내 used 2,
      fail∪used = {(1,1),(2,1),(3,1)} = 3 → remaining 1.
    """
    _seed_scenario(tp_env)
    _seed_region(tp_env, "PLAN-R", ("TAPE-X", "01"), [(1, 1), (2, 1), (3, 1), (4, 1)])
    tp_env.commit()

    body = client.get("/api/transfer-plan/source-summary", params={
        "stage": "bonding", "lot": "TAPE-X", "slot": "01", "plan_id": "PLAN-R",
    }).json()

    assert body["chips"]["remaining"] == 2          # 전체 집계는 불변
    rc = body["region_chips"]
    assert rc["cells"] == 4
    assert rc["total"] == 4
    assert rc["transferred"] == 2
    assert rc["remaining"] == 1                     # 합집합 의미론 유지
    assert rc["reliable"] is True


def test_source_region_absent_when_no_plan_id(tp_env, client):
    """plan_id 없이는 영역 스코프가 없다(기존 계약 불변)."""
    _seed_scenario(tp_env)
    _seed_region(tp_env, "PLAN-R", ("TAPE-X", "01"), [(1, 1)])
    tp_env.commit()
    body = client.get("/api/transfer-plan/source-summary", params={
        "stage": "bonding", "lot": "TAPE-X", "slot": "01",
    }).json()
    assert "region_chips" not in body


def test_source_region_empty_set_is_zero_not_missing(tp_env, client):
    """저장된 영역이 없으면 빈 집합 → 영역 내 가용 0 (필드는 존재)."""
    _seed_scenario(tp_env)
    body = client.get("/api/transfer-plan/source-summary", params={
        "stage": "bonding", "lot": "TAPE-X", "slot": "01", "plan_id": "PLAN-NONE",
    }).json()
    rc = body["region_chips"]
    assert rc["cells"] == 0 and rc["total"] == 0 and rc["remaining"] == 0


def test_source_region_scopes_core_availability_with_align(tp_env, client):
    """[②] core-kind(M1 위임) 소스도 영역 스코프가 된다 — align 적용 좌표로 교차.

    bonding_plan.py 무수정 불변식을 지키기 위해 M1 config 바인딩을 어댑터로 읽어
    좌표 집합을 직접 구성한다. eds는 저장 좌표가 180° 회전이라 정렬이 필수.
    """
    _seed_scenario(tp_env)
    # CORE-A canonical: defect (2,2)(3,3), eds canonical (1,1)
    _seed_region(tp_env, "PLAN-C", ("CORE-A", "01"), [(1, 1), (2, 2), (5, 5)])
    tp_env.commit()

    body = client.get("/api/transfer-plan/source-summary", params={
        "stage": "dt", "lot": "CORE-A", "slot": "01", "plan_id": "PLAN-C",
    }).json()
    rc = body["region_chips"]
    assert rc["cells"] == 3
    assert rc["total"] == 3                       # 3칸 모두 defect 풀맵에 존재
    assert rc["fail_breakdown"]["defect"] == 1    # (2,2)
    assert rc["fail_breakdown"]["eds_fail"] == 1  # canonical (1,1) — 정렬 적용 증거
    assert rc["remaining"] == 1                   # (5,5)만 가용


def test_source_region_core_align_negative_control(tp_env, client, tmp_path, monkeypatch):
    """align 미선언이면 eds 저장좌표(6,6)로 비교되어 영역 내 eds가 0 — 정렬 실효 대조군."""
    _seed_scenario(tp_env)
    _seed_region(tp_env, "PLAN-C2", ("CORE-A", "01"), [(1, 1), (2, 2), (5, 5)])
    tp_env.commit()
    bp = _bp_config()
    del bp["sources"]["eds_fail"]["align"]
    _write_cfg(tmp_path, monkeypatch, bp_cfg=bp)
    body = client.get("/api/transfer-plan/source-summary", params={
        "stage": "dt", "lot": "CORE-A", "slot": "01", "plan_id": "PLAN-C2",
    }).json()
    assert body["region_chips"]["fail_breakdown"]["eds_fail"] == 0
    assert body["region_chips"]["fail_breakdown"]["defect"] == 1   # 무회전 원천은 불변


def test_source_region_binding_reported_in_plan_store(tp_env, client):
    body = client.get("/api/transfer-plan/stages").json()
    assert body["plan_store"]["source_region"] == "connected"


# ---------------------------------------------------------------------------
# 4. validate
# ---------------------------------------------------------------------------

def _seed_plan(db, plan_id="PLAN-1", stage="bonding"):
    _add(db, "tp_test_plan", plan_id=plan_id, stage=stage,
         target_lot="TB-1", target_slot="01", status="draft", memo="demo")


def _seed_doe(db, plan_id, value, source=("TAPE-X", "01"), qty=1,
              layer_from=None, layer_to=None):
    _add(db, "tp_test_plan_doe", doe_key=f"{plan_id}|{value}", plan_id=plan_id,
         doe_value=value, source_lot=source[0], source_slot=source[1],
         qty_per_unit=qty, layer_from=layer_from, layer_to=layer_to,
         knobs="{}", description=f"DOE {value}")


def _paint(db, plan_id, cells):
    for (x, y, val) in cells:
        _add(db, "tp_test_plan_map", cell_key=f"{plan_id}|{x}|{y}",
             plan_id=plan_id, x=x, y=y, val=val)


def _types(warnings):
    return [w["type"] for w in warnings]


def test_validate_ok_plan(tp_env, client):
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-OK")
    _seed_doe(tp_env, "PLAN-OK", "A", qty=1)          # 층 미선언 → 1층
    _paint(tp_env, "PLAN-OK", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-OK"}).json()
    assert body["plan"]["stage"] == "bonding"
    assert body["doe_count"] == 1
    assert body["painted_values"] == {"A": 2}
    # 필요 2 ≤ 가용 2 → 수량 경고 없음. 단 소스 fail 칩·이력 경고는 정보로 표시된다.
    types = _types(body["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE not in types
    assert transfer_plan.WARN_SOURCE_FAIL_CHIPS in types
    assert transfer_plan.WARN_SOURCE_HISTORY_FAIL in types


def test_validate_qty_shortage_with_layers(tp_env, client):
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-1")
    # 칩 2 × 층 2 × 개당 1 = 필요 4 > 가용 2 → 부족
    _seed_doe(tp_env, "PLAN-1", "A", qty=1, layer_from=1, layer_to=2)
    _paint(tp_env, "PLAN-1", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-1"}).json()
    assert body["status"] == "warnings"
    shortage = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(shortage) == 1
    assert shortage[0]["required"] == 4 and shortage[0]["available"] == 2


def test_validate_doe_map_consistency(tp_env, client):
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-2")
    _seed_doe(tp_env, "PLAN-2", "A")                    # 페인팅 없음 → unpainted
    _paint(tp_env, "PLAN-2", [(1, 1, "C")])             # DOE 정의 없음 → undefined
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-2"}).json()
    types = _types(body["warnings"])
    assert transfer_plan.WARN_UNDEFINED_DOE_VALUE in types
    assert transfer_plan.WARN_DOE_VALUE_UNPAINTED in types
    undefined = [w for w in body["warnings"]
                 if w["type"] == transfer_plan.WARN_UNDEFINED_DOE_VALUE][0]
    assert undefined["value"] == "C"


def test_validate_layer_coverage_and_range(tp_env, client):
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-3")
    _seed_doe(tp_env, "PLAN-3", "L1", layer_from=1, layer_to=1)
    _seed_doe(tp_env, "PLAN-3", "L3", layer_from=3, layer_to=3)   # 2층 공백
    _seed_doe(tp_env, "PLAN-3", "LR", layer_from=5, layer_to=4)   # 역전
    _paint(tp_env, "PLAN-3", [(1, 1, "L1"), (2, 1, "L3"), (3, 1, "LR")])
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-3"}).json()
    types = _types(body["warnings"])
    assert transfer_plan.WARN_LAYER_RANGE_INVALID in types
    gap = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_COVERAGE_GAP]
    assert len(gap) == 1 and "[2]" in gap[0]["detail"]


def _seed_layer(db, plan_id, value, layer, source=None, qty=None, note=None):
    """S3: DOE 층별 배정 1건."""
    _add(db, "tp_test_plan_doe_layer",
         layer_key=f"{plan_id}|{value}|{layer}", doe_key=f"{plan_id}|{value}",
         layer=layer, source_lot=(source or (None, None))[0],
         source_slot=(source or (None, None))[1], qty=qty, note=note)


def test_doe_layer_assignments_drive_quantity(tp_env, client):
    """[S3] 층마다 다른 소스/수량 — 층 배정이 있으면 DOE 기본값 대신 그것이 쓰인다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_plan(tp_env, "PLAN-L")
    # DOE 기본은 층 1~2(=2층)이지만, 층 배정이 우선한다
    _seed_doe(tp_env, "PLAN-L", "A", source=("TAPE-X", "01"), qty=1,
              layer_from=1, layer_to=2)
    _seed_layer(tp_env, "PLAN-L", "A", 1, source=("TAPE-X", "01"), qty=1)
    _seed_layer(tp_env, "PLAN-L", "A", 2, source=("TAPE-X", "01"), qty=5)  # 층2만 5개씩
    _paint(tp_env, "PLAN-L", [(1, 1, "A")])   # 칩 1
    tp_env.commit()

    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-L"}).json()
    assert body["availability_checked"] is True
    # 층1 필요 1(<=2, 통과) / 층2 필요 5(>2, 부족)
    short = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(short) == 1
    assert short[0]["demand"] == "A@L2" and short[0]["required"] == 5


def test_doe_layer_sources_aggregate_per_source(tp_env, client):
    """[S3 x F4] 층별 소스가 같으면 합산이 소스 단위로 누적된다."""
    _seed_scenario(tp_env)          # 가용 2
    _seed_plan(tp_env, "PLAN-LS")
    _seed_doe(tp_env, "PLAN-LS", "A", source=("TAPE-X", "01"), qty=1)
    _seed_layer(tp_env, "PLAN-LS", "A", 1, source=("TAPE-X", "01"), qty=1)
    _seed_layer(tp_env, "PLAN-LS", "A", 2, source=("TAPE-X", "01"), qty=1)
    _paint(tp_env, "PLAN-LS", [(1, 1, "A"), (2, 1, "A")])   # 칩 2
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-LS"}).json()
    # 층1 필요 2, 층2 필요 2 → 각각은 가용 2 이하지만 합 4 > 2
    over = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_SOURCE_OVERALLOCATED]
    assert len(over) == 1
    assert over[0]["required_total"] == 4 and over[0]["available"] == 2
    assert set(over[0]["doe_values"]) == {"A@L1", "A@L2"}


def test_doe_layer_falls_back_to_doe_source(tp_env, client):
    """층 배정에 소스가 비면 DOE 기본 소스를 승계한다(부분 선언 허용)."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-LF")
    _seed_doe(tp_env, "PLAN-LF", "A", source=("TAPE-X", "01"), qty=1)
    _seed_layer(tp_env, "PLAN-LF", "A", 3, source=None, qty=None)   # 전부 승계
    _paint(tp_env, "PLAN-LF", [(1, 1, "A")])
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-LF"}).json()
    assert body["availability_checked"] is True
    assert transfer_plan.WARN_SOURCE_UNRESOLVED not in _types(body["warnings"])
    # 층 3만 배정 → 1,2층 공백 경고
    gap = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_COVERAGE_GAP]
    assert len(gap) == 1


def test_plan_store_reports_doe_layer_binding(tp_env, client):
    body = client.get("/api/transfer-plan/stages").json()
    assert body["plan_store"]["doe_layer"] == "connected"


def test_validate_detects_source_overallocation(tp_env, client):
    """[QA F4] 여러 DOE가 한 소스를 나눠 쓸 때 합산 초과를 검출한다.

    개별 DOE는 각각 가용 이하라 qty_shortage가 안 나는데 합이 넘는 경우 — DOE 계획의
    가장 흔한 초과 형태인데 아무도 보지 않던 구멍.
    """
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_plan(tp_env, "PLAN-OVER")
    _seed_doe(tp_env, "PLAN-OVER", "A", qty=1)   # 칩 1 → 필요 1 (<= 2)
    _seed_doe(tp_env, "PLAN-OVER", "B", qty=1)   # 칩 2 → 필요 2 (<= 2)
    _paint(tp_env, "PLAN-OVER", [(1, 1, "A"), (2, 1, "B"), (3, 1, "B")])
    tp_env.commit()

    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-OVER"}).json()
    types = _types(body["warnings"])
    # 개별 부족은 없다 (1<=2, 2<=2)
    assert transfer_plan.WARN_QTY_SHORTAGE not in types
    # 그러나 합산 3 > 가용 2 → 초과배정 검출
    over = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_SOURCE_OVERALLOCATED]
    assert len(over) == 1
    assert over[0]["required_total"] == 3 and over[0]["available"] == 2
    assert set(over[0]["doe_values"]) == {"A", "B"}
    assert over[0]["source_lot"] == "TAPE-X"


def test_validate_no_overallocation_warning_for_single_doe(tp_env, client):
    """단독 DOE 소스는 qty_shortage가 이미 같은 사실을 말한다 — 중복 경고 금지."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-SOLO")
    _seed_doe(tp_env, "PLAN-SOLO", "A", qty=1, layer_from=1, layer_to=2)  # 필요 4 > 2
    _paint(tp_env, "PLAN-SOLO", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-SOLO"}).json()
    types = _types(body["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE in types
    assert transfer_plan.WARN_SOURCE_OVERALLOCATED not in types


def test_validate_overallocation_skipped_when_degraded(tp_env, client, tmp_path, monkeypatch):
    """[F1 규율] 강등 입력에서는 합산 판정도 하지 않는다(오염된 가용치 사용 금지)."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-OVD")
    _seed_doe(tp_env, "PLAN-OVD", "A", qty=1)
    _seed_doe(tp_env, "PLAN-OVD", "B", qty=1)
    _paint(tp_env, "PLAN-OVD", [(1, 1, "A"), (2, 1, "B"), (3, 1, "B")])
    tp_env.commit()
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-OVD"}).json()
    types = _types(body["warnings"])
    assert transfer_plan.WARN_SOURCE_OVERALLOCATED not in types
    assert transfer_plan.WARN_AVAILABILITY_UNRELIABLE in types
    assert body["status"] == "unverified"


def test_validate_refuses_to_judge_on_degraded_source(tp_env, client, tmp_path, monkeypatch):
    """[QA F1] 오염된 remaining으로 qty_shortage를 판정하지 않는다.

    강등 시 remaining이 과대라 '부족 아님'으로 조용히 통과하던 경로 — 안전망 붕괴 지점.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-DEG")
    # 정상이면 필요 4 > 가용 2로 qty_shortage가 나야 하는 계획
    _seed_doe(tp_env, "PLAN-DEG", "A", qty=1, layer_from=1, layer_to=2)
    _paint(tp_env, "PLAN-DEG", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()

    # 대조군: 정상 config에서는 qty_shortage가 발화한다
    ok = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-DEG"}).json()
    assert transfer_plan.WARN_QTY_SHORTAGE in _types(ok["warnings"])
    assert ok["availability_checked"] is True

    # 강등: origin_log 파손 → remaining 과대(5) → 예전이라면 4 <= 5로 "부족 아님" 통과
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    deg = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-DEG"}).json()
    types = _types(deg["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE not in types, "오염값으로 부족 여부를 판정하면 안 된다"
    assert transfer_plan.WARN_AVAILABILITY_UNRELIABLE in types, "판정 불가를 명시해야 한다"
    # "검사 안 함"이 "이상 없음"으로 읽히지 않아야 한다
    assert deg["status"] == "unverified"
    assert deg["availability_checked"] is False
    unrel = [w for w in deg["warnings"]
             if w["type"] == transfer_plan.WARN_AVAILABILITY_UNRELIABLE][0]
    assert unrel["required"] == 4
    assert "origin_log" in unrel["degraded_roles"]
    # fail 칩 경고도 오염값 기반으로 내지 않는다
    assert transfer_plan.WARN_SOURCE_FAIL_CHIPS not in types


def test_validate_stage_unknown_is_unverified_not_ok(tp_env, client):
    """[QA F1] stage 미선언으로 검증을 통째로 스킵했으면 status가 ok/warnings여선 안 된다."""
    _seed_plan(tp_env, "PLAN-SKIP", stage="unknown_stage")
    _seed_doe(tp_env, "PLAN-SKIP", "A")
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-SKIP"}).json()
    assert body["status"] == "unverified"
    assert body["availability_checked"] is False
    sw = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_STAGE_UNKNOWN][0]
    assert sw["effect"] == "validation_skipped"


def test_validate_ok_status_only_when_actually_checked(tp_env, client):
    """정상 경로에서만 availability_checked=True — 대조군(오탐 방지)."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "PLAN-CHK")
    _seed_doe(tp_env, "PLAN-CHK", "A", qty=1)
    _paint(tp_env, "PLAN-CHK", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-CHK"}).json()
    assert body["availability_checked"] is True
    assert body["status"] in ("ok", "warnings")


def test_validate_stage_unknown_warning(tp_env, client):
    _seed_plan(tp_env, "PLAN-4", stage="unknown_stage")
    tp_env.commit()
    body = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-4"}).json()
    assert _types(body["warnings"]) == [transfer_plan.WARN_STAGE_UNKNOWN]


def test_validate_plan_not_found_404(tp_env, client):
    res = client.get("/api/transfer-plan/validate", params={"plan_id": "NOPE"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


def test_validate_plan_store_unbound_404(tp_env, client, tmp_path, monkeypatch):
    cfg = _tp_config()
    del cfg["plan_store"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    res = client.get("/api/transfer-plan/validate", params={"plan_id": "PLAN-1"})
    assert res.status_code == 404
    assert "plan store" in res.json()["detail"]


# ---------------------------------------------------------------------------
# 5. M1 하위호환 (외부 계약 불변 확인 — dt stage 통합이 M1 API를 건드리지 않음)
# ---------------------------------------------------------------------------

def test_m1_core_summary_contract_unchanged(tp_env, client):
    _seed_scenario(tp_env)
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "CORE-A", "slot": "01"}).json()
    # M1 §C 계약 형태 그대로 (fail_breakdown/transferred 아님)
    assert body["chips"] == {"total": 36, "defect": 2, "eds_fail": 1,
                             "used": 0, "remaining": 33}
    assert set(body["sources"]) == set(bonding_plan.ROLES)
