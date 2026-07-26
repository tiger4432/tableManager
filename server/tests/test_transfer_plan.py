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
    # [v2] 계획 맵 사본은 없다 — bonding stage의 target_map 자체가 계획 캔버스다.
    "tp_test_bonding_map": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "base": "string",
            "x": "number", "y": "number", "leg": "string",
        },
        "map_key_columns": ["base"],
    },
    "tp_test_map_doe": {   # bk = ref_table|map_key|doe_value|band_seq
        "business_key": "doe_key",
        "column_types": {
            "doe_key": "string", "ref_table": "string", "map_key": "string",
            "doe_value": "string", "band_seq": "number", "stack_band": "string",
            "qty_total": "number", "knobs": "string", "note": "string",
        },
    },
    # bk = ref_table|map_key|doe_value|band_seq|source_lot|source_slot
    "tp_test_map_doe_source": {
        "business_key": "source_key",
        "column_types": {
            "source_key": "string", "ref_table": "string", "map_key": "string",
            "doe_value": "string", "band_seq": "number",
            "source_lot": "string", "source_slot": "string",
            "qty": "number", "note": "string",
        },
    },
    "tp_test_plan_region": {   # ② — 소스 사용 영역 (자유 페인팅 셀 집합, 휴면)
        "business_key": "region_key",
        "column_types": {
            "region_key": "string", "ref_table": "string", "map_key": "string",
            "source_lot": "string", "source_slot": "string",
            "x": "number", "y": "number", "val": "string",
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


def _tp_config():
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
            "doe": {"table": "tp_test_map_doe",
                    "columns": {"ref_table": "ref_table", "map_key": "map_key",
                                "doe_value": "doe_value", "band_seq": "band_seq",
                                "stack_band": "stack_band", "qty_total": "qty_total",
                                "knobs": "knobs", "note": "note"}},
            "doe_source": {"table": "tp_test_map_doe_source",
                           "columns": {"ref_table": "ref_table", "map_key": "map_key",
                                       "doe_value": "doe_value", "band_seq": "band_seq",
                                       "source_lot": "source_lot",
                                       "source_slot": "source_slot", "qty": "qty",
                                       "note": "note"}},
            "source_region": {"table": "tp_test_plan_region",
                              "columns": {"ref_table": "ref_table", "map_key": "map_key",
                                          "source_lot": "source_lot",
                                          "source_slot": "source_slot", "x": "x", "y": "y",
                                          "val": "val"}},
        },
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
    # 오버레이 config는 비워 둔다 — 계획 맵의 좌표 바인딩이 **table_config 유도만으로**
    # 해석되는지(선언 의존이 남아 있지 않은지) 함께 고정하기 위함.
    import map_overlay
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(tmp_path / "no_overlay.json"))


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

    # [v2] plan(헤더)·map(계획 맵 사본) 역할은 폐기 — DOE와 그 소스 묶음만 남는다
    assert body["plan_store"] == {"doe": "connected", "doe_source": "connected",
                                  "source_region": "connected"}


def test_stage_reverse_index_from_target_map_table(tp_env):
    """[v2 핵심] stage는 고르는 것이 아니라 **열린 맵 테이블에서 유도**된다."""
    cfg = _tp_config()
    assert transfer_plan.stage_of_table(cfg, "tp_test_bonding_map") == "bonding"
    assert transfer_plan.stage_of_table(cfg, "tp_test_dt_map") == "dt"
    assert transfer_plan.stage_of_table(cfg, "tp_test_core_defect_map") is None
    assert transfer_plan.stage_of_table(cfg, None) is None


def test_stages_missing_roles_partial(tp_env, client, tmp_path, monkeypatch):
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    cfg["plan_store"]["doe"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/stages").json()
    bd = {s["name"]: s for s in body["stages"]}["bonding"]
    assert bd["roles"]["origin_log"] == "missing"
    assert body["plan_store"]["doe"] == "missing"


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


def test_tape_projection_align_negative_control(tp_env, client):
    """eds 메타를 코어와 같은 rot 0으로 바꾸면 저장 좌표 그대로 조인되어 투영 0.

    (정렬 실효 대조군 — 선언 레이어가 없어졌으므로 대조군은 **메타를 바꾸는 것**이다.)
    """
    db = tp_env
    _seed_scenario(db)
    model = models.DYNAMIC_TABLES["tp_test_map_meta"]
    db.query(model).filter(model.target_table == "tp_test_eds_fail_map").delete()
    _add_meta(db, "tp_test_eds_fail_map", "CORE-A_01", rotation=0)
    _add_meta(db, "tp_test_eds_fail_map", "CORE-B_02", rotation=0)
    db.commit()
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"}).json()
    assert body["chips"]["fail_breakdown"]["eds_fail"] == 0
    assert body["chips"]["fail_breakdown"]["defect"] == 2  # 무회전 소스는 불변
    assert body["sources"]["eds_fail"] == "connected"


def test_tape_projection_align_unavailable(tp_env, client):
    """메타는 있는데 phys 규격이 없으면 → 조용히 raw 계산하지 않고 명시 실패 (QA F2 승계).

    메타가 **아예 없는** 경우는 실패가 아니라 identity 폴백이다(등록 누락 신호) —
    아래 별도 테스트가 그 경계를 지킨다.
    """
    db = tp_env
    _add(db, "tp_test_core_defect_map", chip_key="CC", lot="CORE-C", slot="03",
         x=1, y=1, val="P")
    _add_meta(db, "tp_test_core_defect_map", "CORE-C_03", rotation=0)
    _add(db, "tp_test_eds_fail_map", chip_key="EC", lot="CORE-C", slot="03",
         x=6, y=6, val="F")
    bare = {k: v for k, v in dict(GRID, rotation=180).items() if not k.startswith("phys_")}
    _add(db, "tp_test_map_meta", map_pk="eds_bare", target_table="tp_test_eds_fail_map",
         map_id="CORE-C_03", grid_metadata=json.dumps(bare))
    _add(db, "tp_test_dt_log", dt_id="DT-C0", tape_lot="TAPE-Y", tape_slot="01",
         tx=1, ty=1, core_lot="CORE-C", core_slot="03", cx=1, cy=1)
    db.commit()
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-Y", "slot": "01"}).json()
    assert body["sources"]["eds_fail"] == "connected(align_unavailable)"
    assert body["chips"]["fail_breakdown"]["eds_fail"] == 0
    assert body["chips"]["total"] == 1


def test_tape_projection_without_any_meta_is_identity_not_failure(tp_env, client):
    """메타가 아예 없으면 identity로 붙는다 — `align_unavailable`은 '근거가 없다'가 아니라
    '근거는 있는데 계산이 불가능하다'일 때만 낸다(map_overlay 규율과 동일)."""
    db = tp_env
    _add(db, "tp_test_eds_fail_map", chip_key="EN", lot="CORE-N", slot="04",
         x=1, y=1, val="F")
    _add(db, "tp_test_dt_log", dt_id="DT-N0", tape_lot="TAPE-N9", tape_slot="01",
         tx=1, ty=1, core_lot="CORE-N", core_slot="04", cx=1, cy=1)
    db.commit()
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-N9", "slot": "01"}).json()
    assert body["sources"]["eds_fail"] == "connected"
    assert body["chips"]["fail_breakdown"]["eds_fail"] == 1   # (1,1) 그대로 조인


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
    # 정렬을 해석할 수 없는(phys 규격 미등록) eds 메타를 가진 코어로 테이프를 구성한다.
    for y in range(1, 4):
        _add(db, "tp_test_core_defect_map", chip_key=f"M_{y}", lot="CORE-M", slot="01",
             x=1, y=y, val="D" if y == 1 else "P")
    _add_meta(db, "tp_test_core_defect_map", "CORE-M_01", rotation=0)
    _add(db, "tp_test_eds_fail_map", chip_key="EM", lot="CORE-M", slot="01",
         x=6, y=6, val="F")
    bare = {k: v for k, v in dict(GRID, rotation=180).items() if not k.startswith("phys_")}
    _add(db, "tp_test_map_meta", map_pk="eds_bare_M", target_table="tp_test_eds_fail_map",
         map_id="CORE-M_01", grid_metadata=json.dumps(bare))
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
    # [정렬 일원화로 값이 바뀐 지점 — 상한 3 → 5]
    # defect는 canonical(core) 프레임을 정의하는 원천이다. 그것이 파손되면 기준 프레임을
    # 알 수 없고, eds는 자기 프레임(rot 180)만 알 뿐 **기준과의 상대 회전**을 알 수 없다.
    # 종전에는 config의 `align: 180` 선언이 그 상대값을 따로 들고 있어 eds 투영이 계속
    # 됐다(상한 3). 선언 레이어가 사라진 지금은 근거가 없으므로 eds도 명시 실패로 내려간다.
    #   · 상한 5 = total 8 − |used 3|. 정답 2보다 크므로 **여전히 진짜 상한**이다(과대 방향).
    #   · 정보량이 준 것이지 틀린 게 아니다. 그리고 강등된 역할이 하나 더 드러난다 —
    #     종전에는 eds가 조용히 "정상"으로 보였다.
    assert body["sources"]["eds_fail"] == "connected(align_unavailable)"
    assert body["chips"]["remaining_upper_bound"] == 5
    assert body["chips"]["remaining_upper_bound"] > 2      # 진짜 상한 불변식
    deg = _degraded_roles(body)
    assert "defect" in deg and "eds_fail" in deg


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


def test_align_canonical_dims_mismatch_is_explicit_failure(tp_env, client):
    """[QA F6 승계] canonical(dst) 메타를 넘기므로 격자 치수 모순이 명시 실패로 잡힌다.

    dst 메타를 생략하면 이 모순 검증(ValueError 가드)이 통째로 건너뛰어져 어긋난 좌표로
    조용히 투영된다.
    """
    db = tp_env
    # canonical(defect)은 물리 4x6, eds는 물리 6x4 — 같은 웨이퍼 규격이 아니다
    _add(db, "tp_test_core_defect_map", chip_key="Z_1_1", lot="CORE-Z", slot="01",
         x=1, y=1, val="P")
    _add_meta(db, "tp_test_core_defect_map", "CORE-Z_01", rotation=0, cols=4, rows=6)
    _add(db, "tp_test_eds_fail_map", chip_key="EZ", lot="CORE-Z", slot="01",
         x=1, y=1, val="F")
    _add_meta(db, "tp_test_eds_fail_map", "CORE-Z_01", rotation=90, cols=6, rows=4)
    _add(db, "tp_test_dt_log", dt_id="DTZ", tape_lot="TAPE-Z9", tape_slot="01",
         tx=1, ty=1, core_lot="CORE-Z", core_slot="01", cx=1, cy=1)
    db.commit()

    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-Z9", "slot": "01"}).json()
    # 조용한 오답이 아니라 명시 실패 + 강등 표면화
    assert body["sources"]["eds_fail"] == "connected(align_unavailable)"
    assert body["chips"]["remaining_reliable"] is False


def test_canonical_meta_is_passed_to_the_shared_transform(tp_env, monkeypatch):
    """[QA F6 승계] `_canonical_fail_set`이 **공유 변환기**에 canonical 메타를 실제로 넘긴다.

    canonical 메타가 None으로 새면 `resolve_align`이 identity를 돌려주고 정렬이 통째로
    사라진다 — 그래도 status는 `connected`라 조용한 과소 집계가 된다.
    """
    _seed_scenario(tp_env)
    captured = []
    import map_overlay as mo
    orig = mo.make_frame_transform

    def spy(source_meta, target_meta):
        captured.append((source_meta, target_meta))
        return orig(source_meta, target_meta)

    monkeypatch.setattr(mo, "make_frame_transform", spy)
    cfg = transfer_plan.load_transfer_plan_config()
    transfer_plan.get_stage_source_summary(tp_env, cfg, "bonding", "TAPE-X", "01")
    assert captured, "정렬 변환이 한 번도 호출되지 않았다"
    src_meta, dst_meta = captured[0]
    assert dst_meta is not None, "canonical 메타가 None이면 정합 검증이 무력화된다"
    assert dst_meta["grid_cols"] == 6 and dst_meta["grid_rows"] == 6
    assert int(src_meta["rotation"]) == 180 and int(dst_meta["rotation"]) == 0


# ---------------------------------------------------------------------------
# 3-quater. [②] 소스 사용 영역 영속화 — 자유 페인팅 셀 집합 스코프
# ---------------------------------------------------------------------------

MAP_T = "tp_test_bonding_map"     # bonding stage의 target_map = 계획 캔버스 자신


def _seed_region(db, map_key, source, cells, val="USE", ref_table=MAP_T):
    for (x, y) in cells:
        _add(db, "tp_test_plan_region",
             region_key=f"{ref_table}|{map_key}|{source[0]}|{source[1]}|{x}|{y}",
             ref_table=ref_table, map_key=map_key,
             source_lot=source[0], source_slot=source[1], x=x, y=y, val=val)


def _region_params(map_key, **kw):
    return dict({"ref_table": MAP_T, "map_key": map_key}, **kw)


def test_source_region_scopes_tape_availability(tp_env, client):
    """[②] 테이프 소스 — 영역 셀 집합으로 좁힌 가용이 산출된다.

    전체: total 8, fail∪used 6, remaining 2.
    영역 {(1,1),(2,1),(3,1),(4,1)} (CORE-A 밴드): total 4,
      fail (1,1)eds·(2,1)defect = 2, used (3,1)·(2,1) → 영역 내 used 2,
      fail∪used = {(1,1),(2,1),(3,1)} = 3 → remaining 1.
    """
    _seed_scenario(tp_env)
    _seed_region(tp_env, "BASE-R", ("TAPE-X", "01"), [(1, 1), (2, 1), (3, 1), (4, 1)])
    tp_env.commit()

    body = client.get("/api/transfer-plan/source-summary", params=_region_params(
        "BASE-R", stage="bonding", lot="TAPE-X", slot="01")).json()

    assert body["chips"]["remaining"] == 2          # 전체 집계는 불변
    rc = body["region_chips"]
    assert rc["cells"] == 4
    assert rc["total"] == 4
    assert rc["transferred"] == 2
    assert rc["remaining"] == 1                     # 합집합 의미론 유지
    assert rc["reliable"] is True


def test_source_region_absent_without_map_identity(tp_env, client):
    """(ref_table, map_key) 없이는 영역 스코프가 없다 — v2 키로 이동한 계약."""
    _seed_scenario(tp_env)
    _seed_region(tp_env, "BASE-R", ("TAPE-X", "01"), [(1, 1)])
    tp_env.commit()
    body = client.get("/api/transfer-plan/source-summary", params={
        "stage": "bonding", "lot": "TAPE-X", "slot": "01",
    }).json()
    assert "region_chips" not in body


def test_source_region_empty_set_is_zero_not_missing(tp_env, client):
    """저장된 영역이 없으면 빈 집합 → 영역 내 가용 0 (필드는 존재)."""
    _seed_scenario(tp_env)
    body = client.get("/api/transfer-plan/source-summary", params=_region_params(
        "BASE-NONE", stage="bonding", lot="TAPE-X", slot="01")).json()
    rc = body["region_chips"]
    assert rc["cells"] == 0 and rc["total"] == 0 and rc["remaining"] == 0


def test_source_region_scopes_core_availability_with_align(tp_env, client):
    """[②] core-kind(M1 위임) 소스도 영역 스코프가 된다 — align 적용 좌표로 교차."""
    _seed_scenario(tp_env)
    _seed_region(tp_env, "BASE-C", ("CORE-A", "01"), [(1, 1), (2, 2), (5, 5)])
    tp_env.commit()

    body = client.get("/api/transfer-plan/source-summary", params=_region_params(
        "BASE-C", stage="dt", lot="CORE-A", slot="01")).json()
    rc = body["region_chips"]
    assert rc["cells"] == 3
    assert rc["total"] == 3                       # 3칸 모두 defect 풀맵에 존재
    assert rc["fail_breakdown"]["defect"] == 1    # (2,2)
    assert rc["fail_breakdown"]["eds_fail"] == 1  # canonical (1,1) — 정렬 적용 증거
    assert rc["remaining"] == 1                   # (5,5)만 가용


def test_source_region_core_align_negative_control(tp_env, client):
    """eds 메타를 rot 0으로 바꾸면 저장좌표(6,6)로 비교되어 영역 내 eds가 0 — 실효 대조군.

    이 경로(`_core_region_counts`)는 M1 config를 M2 어댑터로 감싸므로, 어댑터가 canonical
    후보를 못 찾으면 정렬이 조용히 identity로 떨어진다 — 그 회귀를 여기서 잡는다.
    """
    db = tp_env
    _seed_scenario(db)
    _seed_region(db, "BASE-C2", ("CORE-A", "01"), [(1, 1), (2, 2), (5, 5)])
    model = models.DYNAMIC_TABLES["tp_test_map_meta"]
    db.query(model).filter(model.target_table == "tp_test_eds_fail_map").delete()
    _add_meta(db, "tp_test_eds_fail_map", "CORE-A_01", rotation=0)
    db.commit()
    body = client.get("/api/transfer-plan/source-summary", params=_region_params(
        "BASE-C2", stage="dt", lot="CORE-A", slot="01")).json()
    assert body["region_chips"]["fail_breakdown"]["eds_fail"] == 0
    assert body["region_chips"]["fail_breakdown"]["defect"] == 1   # 무회전 원천은 불변


def test_source_region_binding_reported_in_plan_store(tp_env, client):
    body = client.get("/api/transfer-plan/stages").json()
    assert body["plan_store"]["source_region"] == "connected"


# ---------------------------------------------------------------------------
# 4. validate — 계획 모델 v2
#
# 계획 정체성은 `(ref_table, map_key)` = 지금 열어 편집 중인 맵. plan_id도, 계획 헤더도,
# 계획 맵 사본도 없다. 페인팅 값 분포는 **대상 맵 자신**에서 group-by로 읽는다.
# ---------------------------------------------------------------------------

def _seed_doe(db, map_key, value, band=None, seq=1, qty_total=None, ref_table=MAP_T):
    """DOE 행 1건 = (값, STACK 구간). 같은 값에 seq를 달리해 구간을 여러 개 둘 수 있다."""
    _add(db, "tp_test_map_doe",
         doe_key=f"{ref_table}|{map_key}|{value}|{seq}", ref_table=ref_table,
         map_key=map_key, doe_value=value, band_seq=seq, stack_band=band,
         qty_total=qty_total, knobs="{}", note=None)


def _seed_source(db, map_key, value, source=("TAPE-X", "01"), seq=1, qty=None, note=None,
                 ref_table=MAP_T):
    """구간의 사용 자재 1매 (묶음의 구성원 — 묶음은 값이 아니라 **구간** 아래 붙는다)."""
    _add(db, "tp_test_map_doe_source",
         source_key=f"{ref_table}|{map_key}|{value}|{seq}|{source[0]}|{source[1]}",
         ref_table=ref_table, map_key=map_key, doe_value=value, band_seq=seq,
         source_lot=source[0], source_slot=source[1], qty=qty, note=note)


def _paint(db, map_key, cells, ref_table=MAP_T):
    """대상 맵 **자신**에 칠한다 (계획 맵 사본 없음)."""
    for (x, y, val) in cells:
        _add(db, ref_table, cell_key=f"{map_key}|{x}|{y}",
             base=map_key, x=x, y=y, leg=val)


def _validate(client, map_key, ref_table=MAP_T):
    return client.get("/api/transfer-plan/validate",
                      params={"ref_table": ref_table, "map_key": map_key}).json()


def _types(warnings):
    return [w["type"] for w in warnings]


def test_validate_reads_painted_values_from_the_map_itself(tp_env, client):
    """[v2 핵심] 값 분포의 출처가 계획 맵 사본이 아니라 **대상 맵 자신**이다."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-OK", "A", qty_total=2)
    _seed_source(tp_env, "BASE-OK", "A")
    _paint(tp_env, "BASE-OK", [(1, 1, "A"), (2, 1, "A")])
    # 다른 맵 키의 셀은 섞이면 안 된다
    _paint(tp_env, "BASE-OTHER", [(1, 1, "Z"), (2, 1, "Z")])
    tp_env.commit()

    body = _validate(client, "BASE-OK")
    assert body["ref_table"] == MAP_T and body["map_key"] == "BASE-OK"
    assert body["stage"] == "bonding"            # 테이블에서 유도 (선택 UI 없음)
    assert body["map_status"] == "connected"
    assert body["doe_count"] == 1
    assert body["painted_values"] == {"A": 2}    # Z는 다른 맵 → 불참
    types = _types(body["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE not in types   # 필요 2 ≤ 가용 2
    assert transfer_plan.WARN_SOURCE_FAIL_CHIPS in types
    assert transfer_plan.WARN_SOURCE_HISTORY_FAIL in types


def test_validate_qty_shortage(tp_env, client):
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_doe(tp_env, "BASE-1", "A", band="1", qty_total=4)
    _seed_source(tp_env, "BASE-1", "A")
    _paint(tp_env, "BASE-1", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-1")
    assert body["status"] == "warnings"
    shortage = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(shortage) == 1
    assert shortage[0]["required"] == 4 and shortage[0]["available"] == 2


def test_validate_doe_map_consistency(tp_env, client):
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-2", "A")                    # 페인팅 없음 → unpainted
    _seed_source(tp_env, "BASE-2", "A")
    _paint(tp_env, "BASE-2", [(1, 1, "C")])             # DOE 정의 없음 → undefined
    tp_env.commit()
    body = _validate(client, "BASE-2")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_UNDEFINED_DOE_VALUE in types
    assert transfer_plan.WARN_DOE_VALUE_UNPAINTED in types
    undefined = [w for w in body["warnings"]
                 if w["type"] == transfer_plan.WARN_UNDEFINED_DOE_VALUE][0]
    assert undefined["value"] == "C"


def test_validate_stack_band_coverage_and_range(tp_env, client):
    """STACK 구간은 자유 텍스트지만 **수치로 읽히면** 커버리지 검증에 참여한다."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-3", "L1", band="1")
    _seed_doe(tp_env, "BASE-3", "L3", band="3")        # 2 구간 공백
    _seed_doe(tp_env, "BASE-3", "LR", band="5-4")     # 역전
    for v in ("L1", "L3", "LR"):
        _seed_source(tp_env, "BASE-3", v)
    _paint(tp_env, "BASE-3", [(1, 1, "L1"), (2, 1, "L3"), (3, 1, "LR")])
    tp_env.commit()
    body = _validate(client, "BASE-3")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_LAYER_RANGE_INVALID in types
    gap = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_COVERAGE_GAP]
    assert len(gap) == 1 and "[2]" in gap[0]["detail"]


def test_validate_free_text_band_does_not_break_coverage(tp_env, client):
    """수치로 못 읽는 표기(`H1~H2`)는 조용히 불참한다 — 표기를 강제하지 않는다."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-FT", "A", band="바닥", qty_total=1)
    _seed_source(tp_env, "BASE-FT", "A")
    _paint(tp_env, "BASE-FT", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-FT")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_LAYER_COVERAGE_GAP not in types
    assert transfer_plan.WARN_LAYER_RANGE_INVALID not in types


def test_band_range_parsing():
    assert transfer_plan._band_range("1") == (1, 1)
    assert transfer_plan._band_range("2-11") == (2, 11)
    assert transfer_plan._band_range(" 3 ~ 5 ") == (3, 5)
    assert transfer_plan._band_range("H1~H2") is None
    assert transfer_plan._band_range("바닥") is None
    assert transfer_plan._band_range("") is None
    assert transfer_plan._band_range(None) is None


# ---- 값당 다중 STACK 구간 (사용자 스케치: A|H1~H2, A|H2~H3, B|H1~H3) ----

def test_one_value_can_have_multiple_stack_bands(tp_env, client):
    """[E1] 한 값이 **여러 구간 행**을 갖고, 구간마다 **다른 자재 묶음**이 붙는다.

    스케치 그대로:
        A | H1~H2 | DT(TAPE-X)
        A | H2~H3 | DT(TAPE-Y)
        B | H1~H3 | DT(TAPE-X)
    """
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-MB", "A", band="H1~H2", seq=1, qty_total=2)
    _seed_source(tp_env, "BASE-MB", "A", seq=1, source=("TAPE-X", "01"))
    _seed_doe(tp_env, "BASE-MB", "A", band="H2~H3", seq=2, qty_total=6)
    _seed_source(tp_env, "BASE-MB", "A", seq=2, source=("TAPE-Y", "09"))
    _seed_doe(tp_env, "BASE-MB", "B", band="H1~H3", seq=1, qty_total=1)
    _seed_source(tp_env, "BASE-MB", "B", seq=1, source=("TAPE-X", "01"))
    _paint(tp_env, "BASE-MB", [(1, 1, "A"), (2, 1, "B")])
    tp_env.commit()

    body = _validate(client, "BASE-MB")
    assert body["doe_count"] == 3, "구간 행이 각각 살아 있어야 한다(값당 1행으로 뭉개지면 2)"
    assert body["painted_values"] == {"A": 1, "B": 1}

    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    # A의 두 구간이 **서로 다른 자재**를 본다 — 묶음이 값이 아니라 구간에 붙는 증거
    assert "A[H2~H3]@TAPE-Y|09" in short and short["A[H2~H3]@TAPE-Y|09"] == 6
    assert "A[H1~H2]@TAPE-X|01" not in short          # 소요 2 ≤ 가용 2
    assert "B[H1~H3]@TAPE-X|01" not in short          # 소요 1 ≤ 가용 2


def test_bands_of_same_value_aggregate_on_shared_material(tp_env, client):
    """같은 자재를 여러 **구간**이 나눠 쓰면 구간을 가로질러 합산된다(F4 규율 승계)."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_doe(tp_env, "BASE-BA", "A", band="1", seq=1, qty_total=1)
    _seed_source(tp_env, "BASE-BA", "A", seq=1, source=("TAPE-X", "01"))
    _seed_doe(tp_env, "BASE-BA", "A", band="2-3", seq=2, qty_total=2)
    _seed_source(tp_env, "BASE-BA", "A", seq=2, source=("TAPE-X", "01"))
    _paint(tp_env, "BASE-BA", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BA")
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(body["warnings"])  # 1<=2, 2<=2
    over = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_SOURCE_OVERALLOCATED]
    assert len(over) == 1
    assert over[0]["required_total"] == 3 and over[0]["available"] == 2
    assert set(over[0]["doe_values"]) == {"A[1]@TAPE-X|01", "A[2-3]@TAPE-X|01"}


def test_band_label_is_not_part_of_identity(tp_env, client):
    """[설계 근거] 구간 라벨은 **비키 컬럼**이다 — 고쳐도 자재 묶음이 따라온다.

    자유 텍스트를 bk에 넣었다면 라벨 수정이 곧 re-key라 하위 자재 행이 고아가 된다
    (`crud.py`의 composite key는 키 컬럼이 바뀌면 business_key_val을 다시 만든다).
    여기서는 라벨만 바꿔도 (값, band_seq) 조인이 유지되는지 고정한다.
    """
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-RN", "A", band="2-11", seq=1, qty_total=9)
    _seed_source(tp_env, "BASE-RN", "A", seq=1, source=("TAPE-X", "01"))
    _paint(tp_env, "BASE-RN", [(1, 1, "A")])
    tp_env.commit()
    before = _validate(client, "BASE-RN")
    assert "A[2-11]@TAPE-X|01" in {w.get("demand") for w in before["warnings"]}

    # 라벨만 수정 (band_seq·doe_value 불변 = 정체성 불변)
    model = models.DYNAMIC_TABLES["tp_test_map_doe"]
    row = tp_env.query(model).filter(model.doe_value == "A").first()
    row.stack_band = "2~12층"
    tp_env.commit()

    after = _validate(client, "BASE-RN")
    short = [w for w in after["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(short) == 1, "자재가 고아가 됐다면 source_unresolved로 바뀐다"
    assert short[0]["demand"] == "A[2~12층]@TAPE-X|01"
    assert short[0]["required"] == 9


def test_pipe_in_band_label_does_not_corrupt_identity(tp_env, client):
    """구분자(`|`)가 섞인 라벨도 안전하다 — 라벨이 키에 들어가지 않기 때문."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-PIPE", "A", band="H1|H2", seq=1, qty_total=9)
    _seed_source(tp_env, "BASE-PIPE", "A", seq=1, source=("TAPE-X", "01"))
    _paint(tp_env, "BASE-PIPE", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-PIPE")
    short = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(short) == 1 and short[0]["required"] == 9


# ---- 소스 묶음(pool) — 사용자 확정: "한 매당 500칩이면 4매 묶어서 투입" ----

def test_pool_splits_total_demand_evenly(tp_env, client):
    """[v2] 매별 소요는 지정 대상이 아니라 **묶음 총 소요의 균등 배분**이다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2, TAPE-Y/09는 데이터 없음(가용 0)
    _seed_doe(tp_env, "BASE-P", "A", qty_total=4)
    _seed_source(tp_env, "BASE-P", "A", source=("TAPE-X", "01"))
    _seed_source(tp_env, "BASE-P", "A", source=("TAPE-Y", "09"))
    _paint(tp_env, "BASE-P", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-P")
    short = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    # 총 4를 2매로 나눠 매당 2 → TAPE-X(가용 2)는 통과, TAPE-Y(가용 0)만 부족
    assert len(short) == 1
    assert short[0]["required"] == 2, "배분하지 않았다면 4가 나온다"
    assert short[0]["demand"] == "A[1]@TAPE-Y|09"


def test_pool_row_qty_overrides_even_share(tp_env, client):
    """행에 수량이 명시돼 있으면 균등 배분보다 우선한다(부분 선언 허용)."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-Q", "A", qty_total=4)
    _seed_source(tp_env, "BASE-Q", "A", source=("TAPE-X", "01"), qty=9)
    _seed_source(tp_env, "BASE-Q", "A", source=("TAPE-Y", "09"))
    _paint(tp_env, "BASE-Q", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-Q")
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    assert short["A[1]@TAPE-X|01"] == 9      # 명시값
    assert short["A[1]@TAPE-Y|09"] == 2      # 균등 배분


def test_pool_shares_aggregate_per_source_across_does(tp_env, client):
    """[QA F4 승계] 여러 DOE가 같은 자재를 나눠 쓰면 합산 초과배정을 검출한다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_doe(tp_env, "BASE-OVER", "A", qty_total=1)
    _seed_source(tp_env, "BASE-OVER", "A", source=("TAPE-X", "01"))
    _seed_doe(tp_env, "BASE-OVER", "B", qty_total=2)
    _seed_source(tp_env, "BASE-OVER", "B", source=("TAPE-X", "01"))
    _paint(tp_env, "BASE-OVER", [(1, 1, "A"), (2, 1, "B")])
    tp_env.commit()
    body = _validate(client, "BASE-OVER")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE not in types   # 1<=2, 2<=2 각각은 통과
    over = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_SOURCE_OVERALLOCATED]
    assert len(over) == 1
    assert over[0]["required_total"] == 3 and over[0]["available"] == 2
    assert over[0]["source_lot"] == "TAPE-X"


def test_doe_without_pool_is_unresolved(tp_env, client):
    """자재를 하나도 선언하지 않은 DOE는 수량 검증 불가로 표면화된다."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-NP", "A", qty_total=10)
    _paint(tp_env, "BASE-NP", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-NP")
    assert transfer_plan.WARN_SOURCE_UNRESOLVED in _types(body["warnings"])
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


def test_validate_no_overallocation_warning_for_single_demand(tp_env, client):
    """단독 수요 소스는 qty_shortage가 이미 같은 사실을 말한다 — 중복 경고 금지."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-SOLO", "A", qty_total=4)
    _seed_source(tp_env, "BASE-SOLO", "A")
    _paint(tp_env, "BASE-SOLO", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-SOLO")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE in types
    assert transfer_plan.WARN_SOURCE_OVERALLOCATED not in types


def test_validate_overallocation_skipped_when_degraded(tp_env, client, tmp_path, monkeypatch):
    """[F1 규율] 강등 입력에서는 합산 판정도 하지 않는다(오염된 가용치 사용 금지)."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-OVD", "A", qty_total=1)
    _seed_source(tp_env, "BASE-OVD", "A")
    _seed_doe(tp_env, "BASE-OVD", "B", qty_total=2)
    _seed_source(tp_env, "BASE-OVD", "B")
    _paint(tp_env, "BASE-OVD", [(1, 1, "A"), (2, 1, "B")])
    tp_env.commit()
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = _validate(client, "BASE-OVD")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_SOURCE_OVERALLOCATED not in types
    assert transfer_plan.WARN_AVAILABILITY_UNRELIABLE in types
    assert body["status"] == "unverified"


def test_validate_refuses_to_judge_on_degraded_source(tp_env, client, tmp_path, monkeypatch):
    """[QA F1] 오염된 remaining으로 qty_shortage를 판정하지 않는다."""
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "BASE-DEG", "A", qty_total=4)
    _seed_source(tp_env, "BASE-DEG", "A")
    _paint(tp_env, "BASE-DEG", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()

    # 대조군: 정상 config에서는 qty_shortage가 발화한다
    ok = _validate(client, "BASE-DEG")
    assert transfer_plan.WARN_QTY_SHORTAGE in _types(ok["warnings"])
    assert ok["availability_checked"] is True

    # 강등: origin_log 파손 → remaining 과대 → 예전이라면 "부족 아님"으로 통과
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    deg = _validate(client, "BASE-DEG")
    types = _types(deg["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE not in types, "오염값으로 부족 여부를 판정하면 안 된다"
    assert transfer_plan.WARN_AVAILABILITY_UNRELIABLE in types, "판정 불가를 명시해야 한다"
    assert deg["status"] == "unverified"
    assert deg["availability_checked"] is False
    unrel = [w for w in deg["warnings"]
             if w["type"] == transfer_plan.WARN_AVAILABILITY_UNRELIABLE][0]
    assert unrel["required"] == 4
    assert "origin_log" in unrel["degraded_roles"]
    assert transfer_plan.WARN_SOURCE_FAIL_CHIPS not in types


def test_validate_unmapped_table_is_unverified_not_404(tp_env, client):
    """[v2] stage를 유도할 수 없는 맵도 **열 수 있어야 한다** — 404가 아니라 unverified.

    임의의 맵을 편집 대상으로 여는 것이 새 모델의 전제이므로, 전사 대상이 아닌 맵은
    거절이 아니라 "검증 안 됨"으로 표면화한다.
    """
    _seed_scenario(tp_env)
    _seed_doe(tp_env, "AAA", "A", ref_table="tp_test_core_defect_map")
    tp_env.commit()
    body = _validate(client, "AAA", ref_table="tp_test_core_defect_map")
    assert body["stage"] is None
    assert body["status"] == "unverified"
    assert body["availability_checked"] is False
    sw = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_STAGE_UNKNOWN][0]
    assert sw["effect"] == "validation_skipped"


def test_validate_unknown_map_key_is_empty_not_404(tp_env, client):
    """[v2] 계획 헤더가 없으므로 '계획 미존재' 404도 없다 — 빈 계획일 뿐이다."""
    _seed_scenario(tp_env)
    body = _validate(client, "BASE-NEVER-PAINTED")
    assert body["doe_count"] == 0
    assert body["painted_values"] == {}
    assert body["stage"] == "bonding"


def test_validate_plan_store_unbound_404(tp_env, client, tmp_path, monkeypatch):
    cfg = _tp_config()
    del cfg["plan_store"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    res = client.get("/api/transfer-plan/validate",
                     params={"ref_table": MAP_T, "map_key": "BASE-1"})
    assert res.status_code == 404
    assert "plan store" in res.json()["detail"]


def test_validate_unresolvable_map_binding_is_surfaced(tp_env, client, tmp_path, monkeypatch):
    """대상 맵의 좌표 바인딩을 유도할 수 없으면 `map_status: missing`으로 알린다."""
    cfg = _tp_config()
    cfg["stages"]["bonding"]["target_map"]["table"] = "tp_test_bonding_log"   # x/y 없음
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = _validate(client, "BASE-X", ref_table="tp_test_bonding_log")
    assert body["map_status"] == "missing"
    assert body["painted_values"] == {}


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
