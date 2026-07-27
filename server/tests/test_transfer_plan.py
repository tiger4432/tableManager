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
    # [M2.6] 계획 저장소는 이 한 테이블이다 — bk = ref_table|map_key|value.
    # legend 행 하나 = DOE 조건 하나이고 구간·자재는 `bands` JSON 안에 있다.
    # 구 `tp_test_map_doe` / `tp_test_map_doe_source`는 폐기됐다.
    "tp_test_split_registry": {
        "business_key": "split_key",
        "column_types": {
            "split_key": "string", "ref_table": "string", "map_key": "string",
            "value": "string", "split_desc": "string", "color": "string",
            "knobs": "string", "bands": "string",
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
            "registry": {"table": "tp_test_split_registry",
                         "columns": {"ref_table": "ref_table", "map_key": "map_key",
                                     "value": "value", "bands": "bands"}},
            "material_identity": {"compose": ["lot", "slot"], "separator": "_"},
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

    # [M2.6] plan(헤더)·map(사본)에 이어 doe·doe_source도 폐기 — 레지스트리 하나만 남는다.
    # material_identity는 테이블이 아니라 문자열 해석 규칙이지만 미선언이면 계획 전체가
    # unverified로 떨어지므로 배선 상태로 함께 노출한다.
    assert body["plan_store"] == {"registry": "connected",
                                  "material_identity": "connected",
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
    cfg["plan_store"]["registry"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = client.get("/api/transfer-plan/stages").json()
    bd = {s["name"]: s for s in body["stages"]}["bonding"]
    assert bd["roles"]["origin_log"] == "missing"
    assert body["plan_store"]["registry"] == "missing"


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

def _seed_plan(db, map_key, value, bands=None, ref_table=MAP_T):
    """[M2.6] 레지스트리 행 1건 = legend 값 1개 = DOE 조건 1개.

    `bands`는 클라가 쓰는 그대로의 JSON 배열이다 — 저장되는 수치는 `to` 하나뿐이고
    `from`·층 수·소요는 전부 유도된다(`qty_total`·`qty`는 존재하지 않는다).
    """
    _add(db, "tp_test_split_registry",
         split_key=f"{ref_table}|{map_key}|{value}", ref_table=ref_table,
         map_key=map_key, value=value, split_desc=None, color="#6b7280",
         knobs="{}", bands=json.dumps(bands if bands is not None else []))


def _band(to, materials, seq=1):
    return {"seq": seq, "to": to, "materials": list(materials)}


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
    _seed_plan(tp_env, "BASE-OK", "A", [_band(1, ["TAPE-X_01"])])
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
    # 유도된 소요 = painted 2 × layers 1 = 2, 자재 1매 → 2 ≤ 가용 2
    types = _types(body["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE not in types
    assert transfer_plan.WARN_SOURCE_FAIL_CHIPS in types
    assert transfer_plan.WARN_SOURCE_HISTORY_FAIL in types
    # [불변식 반대편] 판정에 실제로 도달했으면 checked=True여야 한다 —
    # unverified 쪽으로만 조이다가 정상 경로까지 잠기는 회귀를 여기서 잡는다.
    assert body["availability_checked"] is True


def test_validate_qty_shortage(tp_env, client):
    """[M2.6] 수량은 저장돼 있지 않다 — painted × layers로 **유도된 값**이 비교 대상이다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_plan(tp_env, "BASE-1", "A", [_band(2, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-1", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-1")
    assert body["status"] == "warnings"
    shortage = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(shortage) == 1
    # painted 2 × layers 2 = 4 (저장된 qty_total이 아니라 맵에서 유도된 수)
    assert shortage[0]["required"] == 4 and shortage[0]["available"] == 2


def test_painting_one_more_cell_moves_the_derived_demand(tp_env, client):
    """[M2.6 설계 근거] 파생값을 저장하지 않는 이유 — 맵을 더 칠하면 소요가 따라 움직인다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-DRIFT", "A", [_band(1, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-DRIFT", [(1, 1, "A")])
    tp_env.commit()
    before = _validate(client, "BASE-DRIFT")
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(before["warnings"])   # 1 ≤ 2

    _paint(tp_env, "BASE-DRIFT", [(2, 1, "A"), (3, 1, "A")])                   # → 3칩
    tp_env.commit()
    after = _validate(client, "BASE-DRIFT")
    short = [w for w in after["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(short) == 1 and short[0]["required"] == 3, "저장된 수였다면 1에 머문다"


def test_validate_doe_map_consistency(tp_env, client):
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-2", "A", [_band(1, ["TAPE-X_01"])])   # 페인팅 없음 → unpainted
    _paint(tp_env, "BASE-2", [(1, 1, "C")])                        # DOE 정의 없음 → undefined
    tp_env.commit()
    body = _validate(client, "BASE-2")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_UNDEFINED_DOE_VALUE in types
    assert transfer_plan.WARN_DOE_VALUE_UNPAINTED in types
    undefined = [w for w in body["warnings"]
                 if w["type"] == transfer_plan.WARN_UNDEFINED_DOE_VALUE][0]
    assert undefined["value"] == "C"


def test_legend_row_without_bands_is_not_yet_a_doe(tp_env, client):
    """색만 정해둔 legend 행은 DOE가 아니다 — 안 칠했다고 경고하면 편집 내내 시끄럽다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-COLORONLY", "A", [])      # bands 없음
    tp_env.commit()
    body = _validate(client, "BASE-COLORONLY")
    assert body["doe_count"] == 0
    assert transfer_plan.WARN_DOE_VALUE_UNPAINTED not in _types(body["warnings"])


# ---- 구간 결함 3종 — 전부 "이 구간은 검증되지 않았다"는 같은 말을 한다 ----

def test_band_defects_are_surfaced_with_a_reason(tp_env, client):
    """[M2.6] `layer_range_invalid`의 새 의미: 층 수를 낼 수 없는 구간 구조.

    구 커버리지 공백(`layer_coverage_gap`)은 **제거**됐다 — `from(i) = prevTo(i) + 1`이라
    구간이 정의상 연속이므로 공백이 표현될 수 없다. 지금의 진짜 결함은 끝 층이 비었거나
    앞 구간보다 크지 않은 경우다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-3", "MID", [_band(None, ["TAPE-X_01"])])       # 편집 중
    _seed_plan(tp_env, "BASE-3", "REV", [
        _band(5, ["TAPE-X_01"], seq=1),
        _band(3, ["TAPE-X_01"], seq=2),                                     # 역전
    ])
    _paint(tp_env, "BASE-3", [(1, 1, "MID"), (2, 1, "REV")])
    tp_env.commit()
    body = _validate(client, "BASE-3")
    reasons = {(w["value"], w["reason"]) for w in body["warnings"]
               if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID}
    assert ("MID", "incomplete") in reasons
    assert ("REV", "not_increasing") in reasons
    # 결함 구간은 수요를 내지 않지만 **정상 구간은 그대로 검증된다** — 결함 하나가 계획
    # 전체의 검증을 무효로 만들지는 않는다(REV #1: painted 1 × layers 5 = 5 > 가용 2).
    assert body["availability_checked"] is True
    assert transfer_plan.WARN_QTY_SHORTAGE in _types(body["warnings"])


def test_plan_of_only_defective_bands_is_unverified(tp_env, client):
    """구간이 전부 결함이면 판정에 도달한 수요가 0이다 — 'ok'가 아니라 'unverified'다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-ALLBAD", "A", [_band(None, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-ALLBAD", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-ALLBAD")
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


def test_unreadable_bands_blob_is_not_read_as_no_bands(tp_env, client):
    """손상된 blob은 '구간 없음'이 아니라 '계획을 못 읽음'이다 — 둘을 합치면 장애가 숨는다."""
    _seed_scenario(tp_env)
    _add(tp_env, "tp_test_split_registry",
         split_key=f"{MAP_T}|BASE-BAD|A", ref_table=MAP_T, map_key="BASE-BAD",
         value="A", split_desc=None, color="#6b7280", knobs="{}", bands="{oops")
    _paint(tp_env, "BASE-BAD", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BAD")
    bad = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID]
    assert len(bad) == 1 and bad[0]["reason"] == "unreadable" and bad[0]["value"] == "A"
    assert body["status"] == "unverified"


def test_removed_coverage_gap_stays_removed_as_behaviour(tp_env, client):
    """제거된 검사가 **어떤 이름으로도** 되살아나지 않도록 동작으로 못을 박는다.

    `hasattr` 단언은 파이썬 속성명 하나만 잡는다 — 다른 이름으로 같은 검사를 다시 넣으면
    그대로 통과한다. 공백이 구조적으로 표현 불가하다는 것은 **비어 있는 구간을 사이에 두고도
    커버리지 경고가 나오지 않는다**로만 확인된다.
    """
    assert not hasattr(transfer_plan, "WARN_LAYER_COVERAGE_GAP")
    _seed_scenario(tp_env)
    # 1~3층 / (편집 중) / 4~9층 — 사람 눈에는 '공백'처럼 보이지만 from은 유도되므로 연속이다
    _seed_plan(tp_env, "BASE-GAP", "A", [
        _band(3, ["TAPE-X_01"], seq=1),
        _band(None, ["TAPE-X_01"], seq=2),
        _band(9, ["TAPE-X_01"], seq=3),
    ])
    _paint(tp_env, "BASE-GAP", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-GAP")
    gaps = [w for w in body["warnings"]
            if "coverage" in str(w.get("type", "")) or "gap" in str(w.get("type", ""))]
    assert gaps == [], f"커버리지 공백 검사가 다른 이름으로 되살아났다: {gaps}"
    # 그리고 연속성 자체를 고정한다: 편집 중 구간을 건너뛰어도 마지막 구간은 **4층부터**
    # 세어 6층이다 — 1층부터 다시 세면 9가 나온다(그 회귀를 이 수가 잡는다)
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    assert short["A[#3]@TAPE-X_01"] == 6


# ---- 공유 계약 벡터 (contracts/band_arithmetic/vectors.json) ----
#
# 같은 파일을 클라 하네스(`client_harness.mjs`)도 읽는다. 이전 테스트는 이름만
# "mirrors the client"였고 양쪽이 **우연히 일치하는** 입력 7개를 하드코딩해서, 거울이
# 깨져도 절대 실패할 수 없었다 — 그리고 그 초록색이 일치의 근거로 인용됐다.

def _vectors():
    import pathlib
    p = (pathlib.Path(__file__).resolve().parents[2]
         / "contracts" / "band_arithmetic" / "vectors.json")
    assert p.exists(), f"공유 계약 벡터가 없다: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


def test_band_to_matches_the_shared_contract():
    spec = _vectors()
    assert spec["to_cases"], "벡터가 비면 이 테스트는 아무것도 증명하지 않는다"
    for c in spec["to_cases"]:
        val, state = transfer_plan._band_to(c["band"])
        assert state == c["state"], f"{c['name']}: state {state} != {c['state']}"
        assert val == c["value"], f"{c['name']}: value {val} != {c['value']}"


def test_band_sequence_arithmetic_matches_the_shared_contract():
    spec = _vectors()
    assert spec["sequence_cases"]
    for case in spec["sequence_cases"]:
        bands, painted = case["bands"], case["painted"]
        for i, exp in enumerate(case["expect"]):
            prev = transfer_plan._prev_to(bands, i)
            val, state = transfer_plan._band_to(bands[i])
            layers = max(0, val - prev) if state == transfer_plan.BAND_TO_OK else 0
            total = painted * layers
            mats = bands[i].get("materials") or []
            share = -(-total // len(mats)) if mats else 0
            where = f"{case['name']}[{i}]"
            assert state == exp["state"], f"{where}: state {state} != {exp['state']}"
            assert prev == exp["prev_to"], f"{where}: prev_to {prev} != {exp['prev_to']}"
            assert layers == exp["layers"], f"{where}: layers {layers} != {exp['layers']}"
            assert total == exp["total"], f"{where}: total {total} != {exp['total']}"
            assert share == exp["share"], f"{where}: share {share} != {exp['share']}"


def test_band_seq_normalization_matches_the_shared_contract():
    spec = _vectors()
    assert spec["normalization_cases"]
    for case in spec["normalization_cases"]:
        out = transfer_plan._parse_bands(json.dumps(case["bands"]))[0]
        assert len(out) == case["expect_count"], case["name"]
        assert [b["seq"] for b in out] == case["expect_seqs"], case["name"]


def test_material_split_matches_the_shared_contract():
    spec = _vectors()
    rule = transfer_plan._material_identity_rule(
        {"plan_store": {"material_identity": {"compose": ["lot", "slot"],
                                              "separator": "_"}}})
    seen = 0
    for c in spec["material_split_cases"]:
        if "id" not in c:
            continue                      # $comment 항목
        seen += 1
        got = transfer_plan._split_material(c["id"], rule)
        assert got == (c["lot"], c["slot"]), f"{c['name']}: {got} != {(c['lot'], c['slot'])}"
    assert seen >= 8, "material_split 벡터가 사라졌다"


def test_band_to_rejects_values_json_cannot_carry():
    """NaN/Infinity는 JSON으로 표현할 수 없어 벡터 파일에 없다 — 여기서 따로 막는다."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert transfer_plan._band_to({"to": bad}) == (None, transfer_plan.BAND_TO_INVALID)


def test_huge_int_does_not_abort_the_whole_plan(tp_env, client):
    """[크기] `10**400`은 float 변환에서 OverflowError를 냈고, 그 하나가 계획 전체의
    검증을 500으로 날렸다 — 값 하나의 손상이 나머지 값의 검증을 죽여선 안 된다."""
    assert transfer_plan._band_to({"to": 10 ** 400}) == (None, transfer_plan.BAND_TO_INVALID)
    _seed_scenario(tp_env)
    _add(tp_env, "tp_test_split_registry",
         split_key=f"{MAP_T}|BASE-HUGE|A", ref_table=MAP_T, map_key="BASE-HUGE",
         value="A", split_desc=None, color="#6b7280", knobs="{}",
         bands='[{"seq":1,"to":1e400,"materials":["TAPE-X_01"]}]')
    _seed_plan(tp_env, "BASE-HUGE", "B", [_band(1, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-HUGE", [(1, 1, "A"), (2, 1, "B")])
    tp_env.commit()
    body = _validate(client, "BASE-HUGE")           # 500이 아니다
    bad = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID and w["value"] == "A"]
    assert len(bad) == 1 and bad[0]["reason"] == "unreadable"
    assert body["availability_checked"] is True, "B는 정상적으로 검증됐어야 한다"


def test_parse_bands_separates_absent_from_unreadable():
    assert transfer_plan._parse_bands(None) == ([], True)      # 아직 DOE 없음 — 정상
    assert transfer_plan._parse_bands("") == ([], True)
    assert transfer_plan._parse_bands("[]") == ([], True)
    assert transfer_plan._parse_bands('[{"seq":1,"to":3,"materials":[]}]')[1] is True
    assert transfer_plan._parse_bands("not json") == ([], False)
    assert transfer_plan._parse_bands('{"seq":1}') == ([], False)   # 배열이 아님
    # 원소 하나가 객체가 아니어도 **나머지로 계속 유도**한다 (클라와 동일) —
    # 원소 하나 때문에 그 값의 계획을 통째로 못 읽은 것으로 만들지 않는다
    kept, readable = transfer_plan._parse_bands('[{"to":5}, 42, {"to":10}]')
    assert readable is True and len(kept) == 2
    # 통째로 못 읽는 것은 blob 자체가 배열이 아닐 때뿐이다
    assert transfer_plan._parse_bands("[1,2]") == ([], True)


def test_oversized_blob_is_refused_before_parsing():
    """`json.loads`는 어떤 캡보다 먼저 실행된다 — 크기는 파싱 **전에** 봐야 한다."""
    huge = "[" + ",".join(['{"seq":1,"to":1,"materials":[]}'] * 40000) + "]"
    assert len(huge) > transfer_plan.MAX_BANDS_BLOB_BYTES
    assert transfer_plan._parse_bands(huge) == ([], False)


def test_material_split_is_declared_never_guessed():
    """자재 원문이 정체이고, (lot, slot) 해석은 **선언된 규칙**으로만 성립한다."""
    rule = transfer_plan._material_identity_rule(
        {"plan_store": {"material_identity": {"compose": ["lot", "slot"],
                                              "separator": "_"}}})
    # 규칙이 없으면 아무것도 풀지 않는다
    assert transfer_plan._split_material("TAPE-A_01", None) == (None, None)
    assert transfer_plan._material_identity_rule({}) is None
    assert transfer_plan._material_identity_rule(
        {"plan_store": {"material_identity": {"compose": ["wafer"]}}}) is None
    # [총괄 결정 2026-07-27] 분리자가 없으면 **거부**한다. 클라는 ("ABC", "") 를 돌려주고
    # `source-summary?lot=ABC&slot=` 로 0을 표시하는데 그쪽이 틀렸다 — 조회되지 않은 것과
    # 잔여가 0인 것은 다르고, 후자로 보이면 부족 경고가 조용히 죽는다.
    assert transfer_plan._split_material("ABC", rule) == (None, None)


# ---- 값당 다중 구간 (사용자 스케치: A 1~2층 / A 3~4층 / B 1~3층) ----

def test_one_value_can_have_multiple_bands_with_different_materials(tp_env, client):
    """[E1] 한 값이 여러 구간을 갖고, 구간마다 **다른 자재**가 붙는다.

    구간은 이제 별도 행이 아니라 한 행의 `bands` 배열 원소다 — 그래서 doe_count는
    구간 수가 아니라 **값의 수**를 센다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-MB", "A", [
        _band(1, ["TAPE-X_01"], seq=1),        # 1층까지 — layers 1
        _band(4, ["TAPE-Y_09"], seq=2),        # 2~4층 — layers 3
    ])
    _seed_plan(tp_env, "BASE-MB", "B", [_band(1, ["TAPE-X_01"], seq=1)])
    _paint(tp_env, "BASE-MB", [(1, 1, "A"), (2, 1, "B")])
    tp_env.commit()

    body = _validate(client, "BASE-MB")
    assert body["doe_count"] == 2, "값 하나 = DOE 하나 (구간 수가 아니다)"
    assert body["painted_values"] == {"A": 1, "B": 1}

    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    # A의 두 구간이 **서로 다른 자재**를 본다 — 자재가 값이 아니라 구간에 붙는 증거
    assert short["A[#2]@TAPE-Y_09"] == 3       # painted 1 × layers 3, TAPE-Y 가용 0
    assert "A[#1]@TAPE-X_01" not in short      # 소요 1 ≤ 가용 2
    assert "B[#1]@TAPE-X_01" not in short      # 소요 1 ≤ 가용 2


def test_array_position_is_order_and_seq_is_only_identity(tp_env, client):
    """[M2.6 설계 근거] `seq`로 정렬해 인접성을 잡으면 층 수가 뒤집힌다.

    아래 두 구간은 seq가 역순(2, 1)이다. seq는 자재가 매달린 **정체**일 뿐이고 순서는
    배열 위치가 진다 — 정렬해 읽으면 자재가 조용히 남의 구간으로 따라간다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-SEQ", "A", [
        {"seq": 2, "to": 1, "materials": ["TAPE-X_01"]},   # 배열 첫째 → layers 1
        {"seq": 1, "to": 4, "materials": ["TAPE-Y_09"]},   # 배열 둘째 → layers 3
    ])
    _paint(tp_env, "BASE-SEQ", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-SEQ")
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    assert short == {"A[#1]@TAPE-Y_09": 3}, "seq로 정렬했다면 층 수가 4로 뒤집힌다"
    # 정렬해 읽었다면 뒤 구간이 역전으로 보여 range_invalid가 났을 것이다
    assert transfer_plan.WARN_LAYER_RANGE_INVALID not in _types(body["warnings"])


def test_bands_of_same_value_aggregate_on_shared_material(tp_env, client):
    """같은 자재를 여러 **구간**이 나눠 쓰면 구간을 가로질러 합산된다(F4 규율 승계)."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_plan(tp_env, "BASE-BA", "A", [
        _band(1, ["TAPE-X_01"], seq=1),      # layers 1 × painted 1 = 1
        _band(3, ["TAPE-X_01"], seq=2),      # layers 2 × painted 1 = 2
    ])
    _paint(tp_env, "BASE-BA", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BA")
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(body["warnings"])  # 1<=2, 2<=2
    over = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_SOURCE_OVERALLOCATED]
    assert len(over) == 1
    assert over[0]["required_total"] == 3 and over[0]["available"] == 2
    assert set(over[0]["doe_values"]) == {"A[#1]@TAPE-X_01", "A[#2]@TAPE-X_01"}


# ---- 자재 묶음 — 사용자 확정: "한 매당 500칩이면 4매 묶어서 투입" ----

def test_band_total_is_split_evenly_across_materials(tp_env, client):
    """매별 소요는 지정 대상이 아니라 **구간 총 소요의 균등 배분**이다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2, TAPE-Y/09는 데이터 없음(가용 0)
    _seed_plan(tp_env, "BASE-P", "A", [_band(4, ["TAPE-X_01", "TAPE-Y_09"])])
    _paint(tp_env, "BASE-P", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-P")
    short = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    # 총 소요 = painted 1 × layers 4 = 4, 2매로 나눠 매당 2 → TAPE-X(2) 통과, TAPE-Y(0) 부족
    assert len(short) == 1
    assert short[0]["required"] == 2, "배분하지 않았다면 4가 나온다"
    assert short[0]["demand"] == "A[#1]@TAPE-Y_09"


def test_share_rounds_up_so_shortage_is_never_understated(tp_env, client):
    """배분은 **올림**이다 — 내림/반올림은 부족분을 숨긴다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-CEIL", "A", [_band(3, ["TAPE-X_01", "TAPE-Y_09"])])
    _paint(tp_env, "BASE-CEIL", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-CEIL")
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    # 총 3을 2매로 → ceil(3/2) = 2 (내림이면 1이라 TAPE-Y 부족이 숨는다)
    assert short == {"A[#1]@TAPE-Y_09": 2}


def test_shares_aggregate_per_source_across_values(tp_env, client):
    """[QA F4 승계] 여러 값이 같은 자재를 나눠 쓰면 합산 초과배정을 검출한다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_plan(tp_env, "BASE-OVER", "A", [_band(1, ["TAPE-X_01"])])   # 1
    _seed_plan(tp_env, "BASE-OVER", "B", [_band(2, ["TAPE-X_01"])])   # 2
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


def test_band_without_materials_is_unresolved(tp_env, client):
    """자재를 하나도 붙이지 않은 구간은 수량 검증 불가로 표면화된다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-NP", "A", [_band(5, [])])
    _paint(tp_env, "BASE-NP", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-NP")
    assert transfer_plan.WARN_SOURCE_UNRESOLVED in _types(body["warnings"])
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


def test_unparseable_material_is_unresolved_not_silently_skipped(tp_env, client):
    """해석 못 한 자재는 **검사한 것으로 치지 않는다** — 침묵이 이 모듈의 실패 형태다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-MID", "A", [_band(1, ["TAPEX01"])])   # 분리자 없음
    _paint(tp_env, "BASE-MID", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-MID")
    unres = [w for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_SOURCE_UNRESOLVED]
    assert len(unres) == 1 and unres[0]["material"] == "TAPEX01"
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


def test_missing_material_identity_rule_blocks_every_check(tp_env, client, tmp_path, monkeypatch):
    """규칙 미선언은 '해석 규칙 없음'이지 '이상 없음'이 아니다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-NOR", "A", [_band(1, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-NOR", [(1, 1, "A")])
    tp_env.commit()
    cfg = _tp_config()
    del cfg["plan_store"]["material_identity"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)

    body = _validate(client, "BASE-NOR")
    assert transfer_plan.WARN_SOURCE_UNRESOLVED in _types(body["warnings"])
    assert body["status"] == "unverified"
    # 수요마다 경고를 내기 전에 배선 상태 자체로도 드러난다
    stages = client.get("/api/transfer-plan/stages").json()
    assert stages["plan_store"]["material_identity"] == "missing"


def test_duplicate_seq_does_not_disable_the_overallocation_guard(tp_env, client):
    """[B1] 합산 판정의 게이트는 **수요 건수**여야 한다 — 표시 라벨의 유일성이 아니라.

    구 모델에서 `band_seq`는 복합 business key의 일부라 중복이 구조적으로 불가능했다.
    M2.6에서 `seq`는 브라우저가 쓰는 자유 JSON 안의 필드이고 `bands`는 평범한 varchar라
    제네릭 그리드·`/tables/.../data/updates`로 무엇이든 들어온다 — `map_doe`를 손으로
    옮기는 경로가 정확히 이 충돌을 만든다.

    회귀 형태: 두 구간이 seq를 공유하면 라벨이 하나로 뭉쳐 `len(labels) < 2`가 되고,
    required는 이미 합산됐는데 초과배정 검사만 조용히 꺼져 **경고 0건 + status ok**가 났다.
    """
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_plan(tp_env, "BASE-DUP", "A", [
        {"seq": 1, "to": 2, "materials": ["TAPE-X_01"]},   # 1칩 × 2층 = 2
        {"seq": 1, "to": 4, "materials": ["TAPE-X_01"]},   # 같은 seq · 1칩 × 2층 = 2
    ])
    _paint(tp_env, "BASE-DUP", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-DUP")

    # 개별 수요는 각각 2 ≤ 가용 2라 qty_shortage로는 절대 안 잡힌다 — 합산만이 잡는다
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(body["warnings"])
    assert body["status"] != "ok", "중복 seq가 안전망을 껐다"
    over = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_SOURCE_OVERALLOCATED]
    assert len(over) == 1
    assert over[0]["demand_count"] == 2
    assert over[0]["required_total"] == 4 and over[0]["available"] == 2
    # 두 구간이 각각 살아 있어야 한다 — seq가 유일화되어 라벨도 갈린다
    assert set(over[0]["doe_values"]) == {"A[#1]@TAPE-X_01", "A[#2]@TAPE-X_01"}


def test_duplicate_seq_large_plan_still_reports_shortage(tp_env, client):
    """[B1] 검수자가 측정한 형태 그대로: 두 구간 합이 가용을 크게 넘는데 경고 0건이었다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-DUP2", "A", [
        {"seq": 1, "to": 5, "materials": ["TAPE-X_01"]},    # 3칩 × 5층 = 15
        {"seq": 1, "to": 10, "materials": ["TAPE-X_01"]},   # 3칩 × 5층 = 15
    ])
    _paint(tp_env, "BASE-DUP2", [(1, 1, "A"), (2, 1, "A"), (3, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-DUP2")
    assert body["status"] == "warnings"
    assert body["availability_checked"] is True
    short = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(short) == 2 and all(w["required"] == 15 for w in short)


# ---- [B2] painted 읽기가 수량의 근거다 — 못 읽으면 판정하지 않는다 ----

def test_unreadable_painted_never_reads_as_zero_demand(tp_env, client, tmp_path, monkeypatch):
    """[B2] painted를 못 읽으면 required가 전부 0이 되어 부족이 영원히 발화하지 않는다.

    이건 **회귀**다: 구 모델은 qty_total을 저장에서 읽어 이 실패에 면역이었다. 수량을
    painted에서 유도하도록 바꾸면서 그 읽기가 하중을 받게 됐는데 게이트가 없었다.
    회귀 형태: 50,000칩을 요구하는 DOE가 3칩짜리 소스에 대해 `doe_value_unpainted`
    하나만 냈다 — 그것도 "칠해지지 않았다(수량 0)"고 **사실을 단정하는** 문구로.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-NOPAINT", "A", [_band(10, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-NOPAINT", [(1, 1, "A")])
    tp_env.commit()

    # 대조군: 정상 경로에서는 부족이 잡힌다
    ok = _validate(client, "BASE-NOPAINT")
    assert transfer_plan.WARN_QTY_SHORTAGE in _types(ok["warnings"])

    # painted 조회를 실패시킨다 (맵 바인딩 유도 불가)
    monkeypatch.setattr(transfer_plan, "_painted_values",
                        lambda *a, **k: ({}, "missing", False))
    body = _validate(client, "BASE-NOPAINT")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_PAINTED_UNAVAILABLE in types
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"
    # 사실을 주장하는 두 경고는 나오면 안 된다 — painted를 근거로 하기 때문
    assert transfer_plan.WARN_DOE_VALUE_UNPAINTED not in types
    assert transfer_plan.WARN_UNDEFINED_DOE_VALUE not in types


def test_truncated_painted_read_is_a_checked_failure(tp_env, client, monkeypatch):
    """[B2] `MAX_PLAN_VALUES` 절단은 이 모듈의 네 번째 캡이자 유일하게 조용하던 캡이었다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-PTRUNC", "A", [_band(2, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-PTRUNC", [(1, 1, "A")])
    tp_env.commit()
    monkeypatch.setattr(transfer_plan, "MAX_PLAN_VALUES", 0)
    body = _validate(client, "BASE-PTRUNC")
    pu = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_PAINTED_UNAVAILABLE]
    assert len(pu) == 1 and pu[0]["truncated"] is True
    assert body["availability_checked"] is False and body["status"] == "unverified"


def test_unreadable_value_does_not_also_claim_no_definition(tp_env, client):
    """손상된 값은 '정의가 없다'가 아니다 — 정의는 있고 읽지 못한 것이다."""
    _seed_scenario(tp_env)
    _add(tp_env, "tp_test_split_registry",
         split_key=f"{MAP_T}|BASE-BOTH|A", ref_table=MAP_T, map_key="BASE-BOTH",
         value="A", split_desc=None, color="#6b7280", knobs="{}", bands="{oops")
    _paint(tp_env, "BASE-BOTH", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BOTH")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_LAYER_RANGE_INVALID in types
    assert transfer_plan.WARN_UNDEFINED_DOE_VALUE not in types, \
        "'DOE 정의가 없음'은 거짓이다 — 정의는 있고 손상됐다"


# ---- 캡 4종 — 전부 표면화되고 전부 unverified로 강등된다 ----

def _cap_types(body):
    return [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_RESULT_TRUNCATED]


def test_registry_row_cap_is_surfaced(tp_env, client, monkeypatch):
    _seed_scenario(tp_env)
    for v in ("A", "B", "C"):
        _seed_plan(tp_env, "BASE-ROWCAP", v, [_band(1, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-ROWCAP", [(1, 1, "A"), (2, 1, "B"), (3, 1, "C")])
    tp_env.commit()
    monkeypatch.setattr(transfer_plan, "MAX_DOE_PER_PLAN", 2)
    body = _validate(client, "BASE-ROWCAP")
    caps = _cap_types(body)
    assert [w["role"] for w in caps] == ["plan_registry"]
    assert body["availability_checked"] is False and body["status"] == "unverified"


def test_band_cap_is_surfaced(tp_env, client, monkeypatch):
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-BANDCAP", "A", [
        _band(1, ["TAPE-X_01"], seq=1), _band(2, ["TAPE-X_01"], seq=2),
        _band(3, ["TAPE-X_01"], seq=3),
    ])
    _paint(tp_env, "BASE-BANDCAP", [(1, 1, "A")])
    tp_env.commit()
    monkeypatch.setattr(transfer_plan, "MAX_BANDS_PER_PLAN", 2)
    body = _validate(client, "BASE-BANDCAP")
    assert [w["role"] for w in _cap_types(body)] == ["bands"]
    assert body["status"] == "unverified"


def test_material_cap_reports_materials_not_bands(tp_env, client, monkeypatch):
    """진단이 거짓말을 하면 안 된다 — 자재를 64에서 잘라 놓고 '구간 2000'이라 보고했다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-MATCAP", "A",
               [_band(1, ["TAPE-X_01", "TAPE-Y_09", "TAPE-Z_07"])])
    _paint(tp_env, "BASE-MATCAP", [(1, 1, "A")])
    tp_env.commit()
    monkeypatch.setattr(transfer_plan, "MAX_SOURCES_PER_DOE", 2)
    body = _validate(client, "BASE-MATCAP")
    caps = _cap_types(body)
    assert len(caps) == 1
    assert caps[0]["role"] == "materials" and caps[0]["cap"] == 2
    assert body["status"] == "unverified"


def test_demand_and_distinct_source_caps_bound_the_fanout(tp_env, client, monkeypatch):
    """[팬아웃] 구간 상한 × 자재 상한이 실질 상한이 되면 안 된다 — 둘을 따로 묶는다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-FAN", "A",
               [_band(1, ["TAPE-X_01", "TAPE-Y_09", "TAPE-Z_07"])])
    _paint(tp_env, "BASE-FAN", [(1, 1, "A")])
    tp_env.commit()

    monkeypatch.setattr(transfer_plan, "MAX_DEMANDS_PER_PLAN", 1)
    assert [w["role"] for w in _cap_types(_validate(client, "BASE-FAN"))] == ["demands"]

    monkeypatch.setattr(transfer_plan, "MAX_DEMANDS_PER_PLAN", 5000)
    monkeypatch.setattr(transfer_plan, "MAX_SOURCES_PER_PLAN", 1)
    body = _validate(client, "BASE-FAN")
    assert [w["role"] for w in _cap_types(body)] == ["distinct_sources"]
    assert body["status"] == "unverified"


def test_failing_source_is_queried_once_not_once_per_demand(tp_env, client, monkeypatch):
    """실패도 캐시해야 한다 — 아니면 계속 실패하는 소스가 수요 수만큼 재조회된다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-FAILCACHE", "A",
               [_band(1, ["TAPE-X_01"], seq=1), _band(2, ["TAPE-X_01"], seq=2),
                _band(3, ["TAPE-X_01"], seq=3)])
    _paint(tp_env, "BASE-FAILCACHE", [(1, 1, "A")])
    tp_env.commit()

    calls = []
    real = transfer_plan.get_stage_source_summary

    def boom(db, cfg, stage, lot, slot, **kw):
        calls.append((lot, slot))
        raise RuntimeError("source down")

    monkeypatch.setattr(transfer_plan, "get_stage_source_summary", boom)
    body = _validate(client, "BASE-FAILCACHE")
    assert len(calls) == 1, f"소스가 {len(calls)}회 재조회됐다 (수요마다 1회)"
    assert body["availability_checked"] is False
    assert transfer_plan.WARN_SOURCE_UNRESOLVED in _types(body["warnings"])
    assert real is not boom


def test_validate_no_overallocation_warning_for_single_demand(tp_env, client):
    """단독 수요 소스는 qty_shortage가 이미 같은 사실을 말한다 — 중복 경고 금지."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-SOLO", "A", [_band(2, ["TAPE-X_01"])])
    _paint(tp_env, "BASE-SOLO", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-SOLO")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE in types
    assert transfer_plan.WARN_SOURCE_OVERALLOCATED not in types


def test_validate_overallocation_skipped_when_degraded(tp_env, client, tmp_path, monkeypatch):
    """[F1 규율] 강등 입력에서는 합산 판정도 하지 않는다(오염된 가용치 사용 금지)."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-OVD", "A", [_band(1, ["TAPE-X_01"])])
    _seed_plan(tp_env, "BASE-OVD", "B", [_band(2, ["TAPE-X_01"])])
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
    _seed_plan(tp_env, "BASE-DEG", "A", [_band(2, ["TAPE-X_01"])])   # 2칩 × 2층 = 4
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
    _seed_plan(tp_env, "AAA", "A", [_band(1, ["TAPE-X_01"])],
               ref_table="tp_test_core_defect_map")
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
    # [불변식] 빈 계획은 아무것도 검사하지 않은 것이다 — 절대 'ok'가 아니다
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


def test_validate_plan_store_unbound_404(tp_env, client, tmp_path, monkeypatch):
    cfg = _tp_config()
    del cfg["plan_store"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    res = client.get("/api/transfer-plan/validate",
                     params={"ref_table": MAP_T, "map_key": "BASE-1"})
    assert res.status_code == 404
    assert "plan store" in res.json()["detail"]


def test_registry_without_bands_column_is_404_not_a_quiet_pass(tp_env, client,
                                                              tmp_path, monkeypatch):
    """`bands` 미선언은 '구간 없음'이 아니라 **계획을 읽을 수단이 없음**이다.

    조용히 통과시키면 라이브에서 정확히 이 상태(선언 누락)가 "DOE가 하나도 없는 계획"으로
    보인다 — 미선언 컬럼이 200과 함께 드롭되는 것과 같은 계열의 침묵이다.
    """
    cfg = _tp_config()
    del cfg["plan_store"]["registry"]["columns"]["bands"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    res = client.get("/api/transfer-plan/validate",
                     params={"ref_table": MAP_T, "map_key": "BASE-1"})
    assert res.status_code == 404
    assert client.get("/api/transfer-plan/stages").json()["plan_store"]["registry"] == "missing"


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
