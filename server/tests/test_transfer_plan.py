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
    # legend 행 하나 = DOE 조건 하나. [ZONE] 층 구조는 zone 컬럼 넷이다.
    # `stack`은 **string**이다 — 읽을 수 없는 원문(`'0x10'`)을 보존해야 V5가 말할 것이 있고,
    # number로 선언하면 crud의 형변환이 그 값에서 예외를 던져 저장 자체가 실패한다.
    # `bands`는 폐기됐지만 실계획이 남아 있어 읽기 전용으로 계속 선언한다.
    # 구 `tp_test_map_doe` / `tp_test_map_doe_source`는 폐기됐다.
    "tp_test_split_registry": {
        "business_key": "split_key",
        "column_types": {
            "split_key": "string", "ref_table": "string", "map_key": "string",
            "value": "string", "split_desc": "string", "color": "string",
            "knobs": "string", "stack": "string", "mat_1h": "string",
            "mat_mid": "string", "mat_top": "string", "bands": "string",
        },
    },
    # [BIN 축] BIN을 지는 맵. **`tp_test_dt_map`과 별개의 테이블인 것이 요점이다** —
    # 그쪽 `val`은 이 시나리오에서 이미 출신 코어 식별자(`CORE-A_01`)이고, 그래서
    # "맵의 val이 곧 BIN"으로 박은 구현은 이 픽스처에서 즉시 틀린다.
    "tp_test_bin_map": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "lot": "string", "slot": "string",
            "x": "number", "y": "number", "bin": "string",
        },
        "map_key_columns": ["lot", "slot"],
    },
    # [로트 전개] 자재 대장 — 로트에 **전산상** 속한 슬롯. 맵과 별개인 것이 요점이다:
    # 맵이 없는 슬롯이야말로 사용자가 봐야 하는 행이라(랏 스플릿 후 정리 누락) 맵에서
    # 슬롯을 세면 진단이 조용히 "깨끗함"을 보고한다.
    "tp_test_lot_wafers": {
        "business_key": "wafer_key",
        "column_types": {
            "wafer_key": "string", "lot": "string", "slot": "string",
        },
    },
    # [F2] 값 컬럼이 후보 밖(UPPERCASE) — 바인딩 유도가 (과거처럼 추측하는 대신)
    # 거부하는 맵. `_painted_values`의 정직한 강등 검증용 (qa_ovl_valcase류 재현).
    "tp_test_valless_map": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                         "x": "number", "y": "number", "VALCASE": "string"},
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
                    "bin_map": {
                        "table": "tp_test_bin_map",
                        "columns": {"lot": "lot", "slot": "slot",
                                    "x": "x", "y": "y", "bin": "bin"},
                    },
                    "lot_membership": {
                        "table": "tp_test_lot_wafers",
                        "columns": {"lot": "lot", "slot": "slot"},
                    },
                },
                "target_map": {"preset": "BASE", "table": "tp_test_bonding_map"},
            },
        },
        "plan_store": {
            "registry": {"table": "tp_test_split_registry",
                         "columns": {"ref_table": "ref_table", "map_key": "map_key",
                                     "value": "value", "stack": "stack",
                                     "mat_1h": "mat_1h", "mat_mid": "mat_mid",
                                     "mat_top": "mat_top", "bands": "bands"}},
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


def _seed_bins(db, cells=None, commit=True):
    """[BIN 축] TAPE-X/01 위에 BIN을 칠한다 — y=1행이 BIN 1, y=2행이 BIN 2.

    _seed_scenario의 8칩 배치 위에 얹으면 기대치는 이렇게 나온다:
      fail∪ = {(1,1),(2,1),(1,2),(2,2)}  ·  기전사 = {(3,1),(4,2),(2,1)}
      BIN 1 = y=1행 {(1,1),(2,1),(3,1),(4,1)} → blocked {(1,1),(2,1),(3,1)} → 가용 1
      BIN 2 = y=2행 {(1,2),(2,2),(3,2),(4,2)} → blocked {(1,2),(2,2),(4,2)} → 가용 1
    **(2,1)이 fail이면서 동시에 기전사**라는 것이 이 픽스처의 결함 축이다: 합집합이 아니라
    `total − fail − used`로 빼면 BIN 1이 0이 되어, 남아 있는 다이 한 칸을 "다 썼다"로
    보고한다. 정확히 이 모듈이 막으려는 실패다.

    BIN 1의 절반은 `'1'`, 절반은 `'01'`로 칠한다 — 문자열로 직접 비교하는 구현이라면
    `'01'` 두 칸이 사라져 BIN 1의 셀 수가 4가 아니라 2로 나온다.
    """
    if cells is None:
        cells = ([((x, 1), "1" if x <= 2 else "01") for x in range(1, 5)]
                 + [((x, 2), "2") for x in range(1, 5)])
    for ((x, y), b) in cells:
        _add(db, "tp_test_bin_map", cell_key=f"BM_{x}_{y}",
             lot="TAPE-X", slot="01", x=x, y=y, bin=b)
    if commit:
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

def _seed_plan(db, map_key, value, stack="", mat_1h=(), mat_mid=(), mat_top=(),
               ref_table=MAP_T):
    """[ZONE] 레지스트리 행 1건 = legend 값 1개 = DOE 조건 1개.

    저장되는 것은 **STACK 하나와 세 구역의 원문 토큰 배열**뿐이다 — 층 수·소요·자재당
    배분은 전부 유도된다(`qty_total`·`qty`는 존재하지 않는다). zone 컬럼은 클라
    (`map_editor.js legendRowPayload`)가 쓰는 그대로 `JSON.stringify([...])` 형태다.
    `stack`은 문자열로 그대로 저장한다 — 읽을 수 없는 값도 원문이 보존돼야 한다.
    """
    _add(db, "tp_test_split_registry",
         split_key=f"{ref_table}|{map_key}|{value}", ref_table=ref_table,
         map_key=map_key, value=value, split_desc=None, color="#6b7280",
         knobs="{}", stack="" if stack is None else str(stack),
         mat_1h=json.dumps(list(mat_1h)), mat_mid=json.dumps(list(mat_mid)),
         mat_top=json.dumps(list(mat_top)), bands=None)


def _seed_legacy_plan(db, map_key, value, bands, ref_table=MAP_T):
    """폐기 모델로 쓰인 행 — zone 컬럼은 비고 `bands`만 있다.

    실제 production 행이 정확히 이 모양이다(2026-07-28 라이브 DB). 서버가 이것을 읽지
    못하면 그 맵의 계획이 화면에서 비고, legend 저장은 `replace_map`이라 다음 편집 한
    번이 계획을 빈 집합으로 지운다.
    """
    _add(db, "tp_test_split_registry",
         split_key=f"{ref_table}|{map_key}|{value}", ref_table=ref_table,
         map_key=map_key, value=value, split_desc=None, color="#6b7280",
         knobs="{}", stack="", mat_1h=None, mat_mid=None, mat_top=None,
         bands=bands if isinstance(bands, str) else json.dumps(bands))


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
    _seed_plan(tp_env, "BASE-OK", "A", stack=1, mat_mid=["TAPE-X_01"])
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
    """[ZONE] 수량은 저장돼 있지 않다 — painted × layers로 **유도된 값**이 비교 대상이다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_plan(tp_env, "BASE-1", "A", stack=2, mat_mid=["TAPE-X_01"])
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
    _seed_plan(tp_env, "BASE-DRIFT", "A", stack=1, mat_mid=["TAPE-X_01"])
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
    _seed_plan(tp_env, "BASE-2", "A", stack=1,
               mat_mid=["TAPE-X_01"])                              # 페인팅 없음 → unpainted
    _paint(tp_env, "BASE-2", [(1, 1, "C")])                        # DOE 정의 없음 → undefined
    tp_env.commit()
    body = _validate(client, "BASE-2")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_UNDEFINED_DOE_VALUE in types
    assert transfer_plan.WARN_DOE_VALUE_UNPAINTED in types
    undefined = [w for w in body["warnings"]
                 if w["type"] == transfer_plan.WARN_UNDEFINED_DOE_VALUE][0]
    assert undefined["value"] == "C"


def test_legend_row_without_a_layer_structure_is_not_yet_a_doe(tp_env, client):
    """색만 정해둔 legend 행은 DOE가 아니다 — 안 칠했다고 경고하면 편집 내내 시끄럽다.

    🔴 **그리고 V5도 나오면 안 된다.** 클라 패널은 화면의 legend 행 전부를
    `validateZonePlan`에 넘기므로 STACK이 빈 행마다 V5가 뜬다. 이 엔드포인트가 같은 짓을
    하면 계획을 세운 적 없는 맵의 값마다 경고가 하나씩 나가 진짜 신호를 덮는다 — 자기
    자신을 무시하도록 가르치는 검증기가 이 계약이 막으려는 바로 그것이다. 규칙은 그대로고,
    **적용 범위**만 클라의 `hasZone`과 같은 판정으로 좁힌다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-COLORONLY", "A")      # STACK도 자재도 없음
    tp_env.commit()
    body = _validate(client, "BASE-COLORONLY")
    assert body["doe_count"] == 0
    assert transfer_plan.WARN_DOE_VALUE_UNPAINTED not in _types(body["warnings"])
    assert transfer_plan.WARN_ZONE_RULE_VIOLATION not in _types(body["warnings"])


# ---- 차단 규칙 V1~V5 — 판정은 `validate_zone_plan`(공유 벡터)이 하고, 여기서는
#      **그 판정이 엔드포인트를 통해 나오는지**와 적용 범위를 고정한다 ----

def test_zone_rule_violations_are_surfaced_with_the_rule_id(tp_env, client):
    """규칙 위반이 `rule` 필드를 달고 나온다 — 패널이 사유를 **그 행 위에** 적을 수 있어야 한다."""
    _seed_scenario(tp_env)
    # V5: STACK을 읽을 수 없다 (원문이 보존돼 있어야 이 판정이 가능하다)
    _seed_plan(tp_env, "BASE-V", "X", stack="0x10", mat_mid=["TAPE-X_01"])
    # V1: MID 구역이 15층인데 비어 있다
    _seed_plan(tp_env, "BASE-V", "C", stack=16, mat_top=["TAPE-X_01"])
    # V2: STACK 1인데 두 끝이 같은 1층을 잡는다
    _seed_plan(tp_env, "BASE-V", "D", stack=1, mat_1h=["TAPE-X_01"], mat_top=["TAPE-Y_01"])
    _paint(tp_env, "BASE-V", [(1, 1, "X"), (2, 1, "C"), (3, 1, "D")])
    tp_env.commit()
    body = _validate(client, "BASE-V")
    got = {(w["value"], w["rule"]) for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_ZONE_RULE_VIOLATION}
    assert got == {("X", "V5"), ("C", "V1"), ("D", "V2")}, got
    # V5가 난 행에서 V1이 함께 나오면 안 된다 — 구역을 계산할 수 없는데 계산한 척이 된다.
    assert ("X", "V1") not in got


def test_unreadable_stack_text_survives_the_round_trip(tp_env, client):
    """🔴 `stack`이 number 컬럼이면 이 테스트는 저장 단계에서 죽는다.

    `crud.cast_value_by_type`가 `'0x10'`에서 ValueError를 던지고, `'7.5'`는 조용히 7.5로
    고쳐져 다음 읽기에서 7층이 된다 — "화면은 멀쩡, 값은 짧음"이 정확히 이 모델이 닫으려는
    결함이다. 그래서 선언은 string이고, 판독 여부는 컬럼 타입이 아니라 정수 판정기가 정한다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-RAW", "A", stack="7.5", mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-RAW", [(1, 1, "A")])
    tp_env.commit()
    row = client.get(f"/tables/tp_test_split_registry/data", params={"limit": 50}).json()
    stacks = [r["data"]["stack"]["value"] for r in row["data"]
              if r["data"]["value"]["value"] == "A"]
    assert stacks == ["7.5"], f"원문이 보존되지 않았다: {stacks}"
    body = _validate(client, "BASE-RAW")
    rules = {w["rule"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_ZONE_RULE_VIOLATION}
    assert rules == {"V5"}


def test_plan_of_only_unreadable_heights_is_unverified(tp_env, client):
    """높이를 못 읽으면 판정에 도달한 수요가 0이다 — 'ok'가 아니라 'unverified'다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-ALLBAD", "A", stack="", mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-ALLBAD", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-ALLBAD")
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


# ---- 폐기 모델(`bands`) 읽기 — 실계획이 아직 그 컬럼에 있다 ----

def test_legacy_band_row_is_migrated_and_verified(tp_env, client):
    """🔴 폐기 행을 못 읽으면 그 맵을 여는 순간 계획이 비고, legend 저장은 `replace_map`이라
    다음 편집 한 번이 계획을 **빈 집합으로 지운다**. 읽는 것은 호의가 아니라 불변식이다."""
    _seed_scenario(tp_env)
    # production 형태(2026-07-28 라이브 DB): 1층 / 2~15층 / 16층
    _seed_legacy_plan(tp_env, "BASE-LEG", "A", [
        _band(1, ["TAPE-X_01"], seq=1),
        _band(15, ["TAPE-Y_01"], seq=2),
        _band(16, ["TAPE-X_01"], seq=3),
    ])
    _paint(tp_env, "BASE-LEG", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-LEG")
    assert body["doe_count"] == 1, "폐기 행이 '계획 없음'으로 읽혔다"
    assert transfer_plan.WARN_LAYER_RANGE_INVALID not in _types(body["warnings"])
    # 1H는 정확히 1층, MID는 2~15층(14층)이다. painted 1이므로 MID 수요 14 > 가용 2.
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    assert short["A[MID]@TAPE-Y_01"] == 14, short
    assert body["availability_checked"] is True


def test_legacy_bands_that_cannot_be_expressed_as_zones_are_refused_not_collapsed(tp_env, client):
    """🔴 이 계약의 가장 중요한 한 줄. 구간 4개를 3구역으로 접은 뒤 그 접은 결과를
    `replace_map`으로 되쓰면 서버의 진짜 계획이 우리 손실 읽기로 덮인다."""
    _seed_scenario(tp_env)
    _seed_legacy_plan(tp_env, "BASE-4B", "A", [
        _band(1, ["TAPE-X_01"], seq=1),
        _band(5, ["TAPE-X_01"], seq=2),
        _band(15, ["TAPE-X_01"], seq=3),
        _band(16, ["TAPE-X_01"], seq=4),
    ])
    _paint(tp_env, "BASE-4B", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-4B")
    bad = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID]
    assert len(bad) == 1 and bad[0]["reason"] == "not_convertible" and bad[0]["value"] == "A"
    # 접어서 통과시키지 않았으므로 이 계획은 검증되지 않은 것이다.
    assert body["status"] == "unverified"
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(body["warnings"])


def test_unreadable_bands_blob_is_not_read_as_no_plan(tp_env, client):
    """손상된 blob은 '구조 없음'이 아니라 '계획을 못 읽음'이다 — 둘을 합치면 장애가 숨는다."""
    _seed_scenario(tp_env)
    _seed_legacy_plan(tp_env, "BASE-BAD", "A", "{oops")
    _paint(tp_env, "BASE-BAD", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BAD")
    bad = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID]
    assert len(bad) == 1 and bad[0]["reason"] == "unreadable" and bad[0]["value"] == "A"
    assert body["status"] == "unverified"


def test_zone_columns_win_over_a_legacy_bands_value(tp_env, client):
    """두 모델이 한 행에 다 있으면 zone이 이긴다 — `bands`는 writer가 없는 폐기 컬럼이다.

    반대로 읽으면 사용자가 방금 저장한 계획이 옛 blob으로 되돌아간다.
    """
    _seed_scenario(tp_env)
    _add(tp_env, "tp_test_split_registry",
         split_key=f"{MAP_T}|BASE-BOTH|A", ref_table=MAP_T, map_key="BASE-BOTH",
         value="A", split_desc=None, color="#6b7280", knobs="{}",
         stack="2", mat_1h="[]", mat_mid=json.dumps(["TAPE-X_01"]), mat_top="[]",
         bands=json.dumps([_band(9, ["TAPE-Y_01"])]))
    _paint(tp_env, "BASE-BOTH", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BOTH")
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    # zone: painted 1 × 2층 = 2 (가용 2 → 부족 없음). bands를 읽었다면 9층 = 9로 부족이 난다.
    assert short == {}, f"폐기 컬럼이 zone을 이겼다: {short}"


def test_removed_overlap_and_gap_checks_stay_removed_as_behaviour(tp_env, client):
    """제거된 검사가 **어떤 이름으로도** 되살아나지 않도록 동작으로 못을 박는다.

    `hasattr` 단언은 파이썬 속성명 하나만 잡는다 — 다른 이름으로 같은 검사를 다시 넣으면
    그대로 통과한다. 그래서 **경고 목록 자체**를 본다.

    zone 모델에서 겹침·공백은 완화된 것이 아니라 **말할 수 없는 상태**다: 세 구역이
    `1..STACK`을 구성적으로 덮으므로, 어떤 배치도 한 층을 두 번 덮거나 비워 둘 수 없다.
    """
    assert not hasattr(transfer_plan, "WARN_LAYER_COVERAGE_GAP")
    _seed_scenario(tp_env)
    # 1H와 TOP만 있고 MID가 비어 있다 — 구 모델이라면 '중간에 구멍'으로 보이는 배치다.
    # zone에서는 STACK 2에서 두 구역이 두 층을 정확히 덮으므로 **정상**이다.
    _seed_plan(tp_env, "BASE-GAP", "A", stack=2,
               mat_1h=["TAPE-X_01"], mat_top=["TAPE-Y_01"])
    _paint(tp_env, "BASE-GAP", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-GAP")
    revived = [w for w in body["warnings"]
               if "coverage" in str(w.get("type", "")) or "gap" in str(w.get("type", ""))
               or "overlap" in str(w.get("type", ""))]
    assert revived == [], f"제거된 검사가 다른 이름으로 되살아났다: {revived}"
    # MID가 비어 있는 것도 V1으로 잡히면 안 된다 — 그 구역은 0층이다.
    rules = {w.get("rule") for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_ZONE_RULE_VIOLATION}
    assert rules == set(), rules


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
    seen = 0
    for c in spec["to_cases"]:
        if "band" not in c:
            continue                      # $comment 항목
        seen += 1
        val, state = transfer_plan._band_to(c["band"])
        assert state == c["state"], f"{c['name']}: state {state} != {c['state']}"
        assert val == c["value"], f"{c['name']}: value {val} != {c['value']}"
    assert seen >= 5, "to 벡터가 사라졌다"


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


def test_band_materials_match_the_shared_contract():
    """양쪽이 합의하고 **패널이 실제로 만들 수 있는** 자재 규칙만 고정한다.

    빈 값 제거·중복 제거가 여기 있는 이유는 서식이 아니라 파생값이기 때문이다 —
    `share = ceil(total / len(materials))`의 분모가 바뀐다.
    """
    spec = _vectors()
    seen = 0
    for c in spec["materials_cases"]:
        if "name" not in c:
            continue                      # $comment 항목
        seen += 1
        band = {"seq": 1, "to": 1}
        if "materials" in c:
            band["materials"] = c["materials"]
        kept, refused = transfer_plan._band_materials(band)
        assert kept == c["expect"], c["name"]
        assert refused == [], f"{c['name']}: 합의 케이스는 거부가 없어야 한다"
    assert seen >= 6, "materials 벡터가 사라졌다"


# ---- 구조 거부 (서버 전용 — 계약 벡터가 아니다) ----
#
# 문자열이 아닌 자재 원소, 객체가 아닌 구간 원소는 **제네릭 그리드로만** 들어올 수 있다.
# 패널은 텍스트 입력으로 문자열을, `normalizeBands`로 객체를 쓴다. 그래서 이 입력에는
# 맞출 상대가 없고, 옳은 답은 "클라와 같은 방식으로 잘못 읽기"가 아니라 "읽을 수 없다"다.
# 양쪽 동작이 **의도적으로 다르므로** 공유 벡터가 아니라 여기서 고정한다.

def test_non_string_material_is_refused_not_stringified():
    for bad in (42, 42.0, True, False, ["a"], {"a": 1}):
        kept, refused = transfer_plan._band_materials({"materials": ["A_1", bad]})
        assert kept == ["A_1"], f"{bad!r}가 자재로 둔갑했다"
        assert refused == [bad]


def test_refused_material_blocks_verification_and_says_so(tp_env, client):
    """남은 자재만으로 배분하면 분모가 틀린 채 그럴듯한 수가 나온다 — 구간을 통째로 뺀다."""
    _seed_scenario(tp_env)
    _add(tp_env, "tp_test_split_registry",
         split_key=f"{MAP_T}|BASE-BADMAT|A", ref_table=MAP_T, map_key="BASE-BADMAT",
         value="A", split_desc=None, color="#6b7280", knobs="{}",
         bands='[{"seq":1,"to":2,"materials":["TAPE-X_01",42]}]')
    _paint(tp_env, "BASE-BADMAT", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BADMAT")
    unres = [w for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_SOURCE_UNRESOLVED]
    assert len(unres) == 1 and unres[0]["refused"] == 1
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(body["warnings"])
    assert body["availability_checked"] is False and body["status"] == "unverified"


def test_non_object_band_element_is_refused_and_reported(tp_env, client):
    """배열 길이가 바뀌면 뒤 구간의 시작 층이 밀린다 — 조용히 버리면 파생값이 조용히 움직인다."""
    _seed_scenario(tp_env)
    _add(tp_env, "tp_test_split_registry",
         split_key=f"{MAP_T}|BASE-BADBAND|A", ref_table=MAP_T, map_key="BASE-BADBAND",
         value="A", split_desc=None, color="#6b7280", knobs="{}",
         bands='[{"seq":1,"to":1,"materials":["TAPE-X_01"]},[],{"seq":2,"to":2,"materials":["TAPE-X_01"]}]')
    _paint(tp_env, "BASE-BADBAND", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BADBAND")
    bad = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID
           and w.get("reason") == "not_a_band"]
    assert len(bad) == 1 and bad[0]["dropped"] == 1
    assert body["availability_checked"] is False and body["status"] == "unverified"


def test_one_bad_row_does_not_invalidate_the_readable_ones(tp_env, client):
    """한 값의 손상이 나머지 값의 검증을 죽이지 않는다.

    ⚠️ 폐기 모델의 구분(빈 `to` = 편집 중, 구조 거부 = 손상)은 **여기서 끝났다.**
    band를 편집하는 패널이 없으므로 "편집 중인 blob"이라는 상태가 존재하지 않고, 저장된
    blob의 빈 `to`는 그냥 마이그레이션 불가다 — 건너뛰면 스택이 조용히 짧아진다.
    """
    _seed_scenario(tp_env)
    _seed_legacy_plan(tp_env, "BASE-MIX", "A", [_band(None, ["TAPE-X_01"], seq=1),
                                                _band(2, ["TAPE-X_01"], seq=2)])
    _seed_plan(tp_env, "BASE-MIX", "B", stack=1, mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-MIX", [(1, 1, "A"), (2, 1, "B")])
    tp_env.commit()
    body = _validate(client, "BASE-MIX")
    bad = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID]
    assert len(bad) == 1 and bad[0]["value"] == "A" and bad[0]["reason"] == "not_convertible"
    assert body["availability_checked"] is True, "B는 정상적으로 검증됐어야 한다"


# 이 모듈이 **소비하는** 벡터 그룹. 그룹이 추가됐는데 소비하는 테스트가 없으면 계약이
# 조용히 그 축을 놓친다 — `seq` 타입 축이 정확히 그렇게 빠져 있었다.
# 클라 하네스에도 같은 관문이 있다(`client_harness.mjs`의 unwired 검사).
_CONSUMED_VECTOR_GROUPS = {
    "to_cases", "sequence_cases", "normalization_cases",
    "material_split_cases", "materials_cases",
}


def test_every_vector_group_is_consumed_by_a_test():
    present = {k for k in _vectors() if k.endswith("_cases")}
    assert present == _CONSUMED_VECTOR_GROUPS, (
        "벡터 그룹 구성이 바뀌었다. 새 그룹을 추가했다면 그것을 소비하는 테스트를 쓰고 "
        "여기에 등록하라 — 등록만 지우면 계약이 그 축을 조용히 놓친다. "
        f"파일: {sorted(present)} · 등록: {sorted(_CONSUMED_VECTOR_GROUPS)}")


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
    _seed_legacy_plan(tp_env, "BASE-HUGE", "A",
                      '[{"seq":1,"to":1e400,"materials":["TAPE-X_01"]}]')
    _seed_plan(tp_env, "BASE-HUGE", "B", stack=1, mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-HUGE", [(1, 1, "A"), (2, 1, "B")])
    tp_env.commit()
    body = _validate(client, "BASE-HUGE")           # 500이 아니다
    bad = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID and w["value"] == "A"]
    assert len(bad) == 1 and bad[0]["reason"] == "not_convertible"
    assert body["availability_checked"] is True, "B는 정상적으로 검증됐어야 한다"
    # 같은 크기가 STACK 컬럼으로 들어와도 500이 아니라 V5여야 한다.
    _seed_plan(tp_env, "BASE-HUGE", "C", stack="1" + "0" * 400, mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-HUGE", [(3, 1, "C")])
    tp_env.commit()
    rules = {(w["value"], w["rule"]) for w in _validate(client, "BASE-HUGE")["warnings"]
             if w["type"] == transfer_plan.WARN_ZONE_RULE_VIOLATION}
    assert ("C", "V5") in rules, rules


def test_parse_bands_separates_absent_from_unreadable():
    assert transfer_plan._parse_bands(None) == ([], True, 0)   # 아직 DOE 없음 — 정상
    assert transfer_plan._parse_bands("") == ([], True, 0)
    assert transfer_plan._parse_bands("[]") == ([], True, 0)
    assert transfer_plan._parse_bands('[{"seq":1,"to":3,"materials":[]}]')[1] is True
    assert transfer_plan._parse_bands("not json") == ([], False, 0)
    assert transfer_plan._parse_bands('{"seq":1}') == ([], False, 0)   # 배열이 아님
    # 원소 하나가 객체가 아니어도 **나머지로 계속 유도**한다 —
    # 다만 조용히 버리지 않는다: 몇 개를 거부했는지 호출자에게 돌려준다
    kept, readable, dropped = transfer_plan._parse_bands('[{"to":5}, 42, {"to":10}]')
    assert readable is True and len(kept) == 2 and dropped == 1
    # 통째로 못 읽는 것은 blob 자체가 배열이 아닐 때뿐이다
    assert transfer_plan._parse_bands("[1,2]") == ([], True, 2)


def test_oversized_blob_is_refused_before_parsing():
    """`json.loads`는 어떤 캡보다 먼저 실행된다 — 크기는 파싱 **전에** 봐야 한다."""
    huge = "[" + ",".join(['{"seq":1,"to":1,"materials":[]}'] * 40000) + "]"
    assert len(huge) > transfer_plan.MAX_BANDS_BLOB_BYTES
    assert transfer_plan._parse_bands(huge) == ([], False, 0)


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


# ---- 값당 다중 구역 (STACK 하나 · 1H / MID / TOP) ----

def test_one_value_can_have_different_materials_per_zone(tp_env, client):
    """[E1] 한 값이 세 구역을 갖고, 구역마다 **다른 자재**가 붙는다.

    구역은 별도 행이 아니라 한 행의 세 컬럼이다 — 그래서 doe_count는 구역 수가 아니라
    **값의 수**를 센다.
    """
    _seed_scenario(tp_env)
    # STACK 4 · 1H 있음 · TOP 없음 → 1H는 1층, MID는 2~4층(3층)
    _seed_plan(tp_env, "BASE-MB", "A", stack=4,
               mat_1h=["TAPE-X_01"], mat_mid=["TAPE-Y_09"])
    _seed_plan(tp_env, "BASE-MB", "B", stack=1, mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-MB", [(1, 1, "A"), (2, 1, "B")])
    tp_env.commit()

    body = _validate(client, "BASE-MB")
    assert body["doe_count"] == 2, "값 하나 = DOE 하나 (구역 수가 아니다)"
    assert body["painted_values"] == {"A": 1, "B": 1}

    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    # A의 두 구역이 **서로 다른 자재**를 본다 — 자재가 값이 아니라 구역에 붙는 증거
    assert short["A[MID]@TAPE-Y_09"] == 3      # painted 1 × layers 3, TAPE-Y 가용 0
    assert "A[1H]@TAPE-X_01" not in short      # 소요 1 ≤ 가용 2
    assert "B[MID]@TAPE-X_01" not in short     # 소요 1 ≤ 가용 2


def test_zone_order_is_the_model_not_an_array_position(tp_env, client):
    """[제거된 축] `seq`·배열 위치·`prevTo` 걷기는 **구역에 존재하지 않는다.**

    구 모델은 배열 위치가 순서를 지고 `seq`는 정체만 졌다 — 정렬해 읽으면 자재가 남의
    구간으로 따라가는 결함이 있었고 그 축을 고정하는 테스트가 있었다. 구역에는 순서를
    담는 자료구조가 아예 없다: 1H는 언제나 1층, TOP은 언제나 STACK층, MID는 그 사이다.
    그래서 그 결함은 **표현할 수 없는 상태**이며, 여기서는 그 사실 자체를 못 박는다 —
    두 자재의 층 수가 컬럼 이름만으로 결정되는지 확인한다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-SEQ", "A", stack=4,
               mat_1h=["TAPE-X_01"], mat_mid=["TAPE-Y_09"])
    _paint(tp_env, "BASE-SEQ", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-SEQ")
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    assert short == {"A[MID]@TAPE-Y_09": 3}
    assert transfer_plan.WARN_LAYER_RANGE_INVALID not in _types(body["warnings"])


def test_zones_of_same_value_aggregate_on_shared_material(tp_env, client):
    """같은 자재를 여러 **구역**이 나눠 쓰면 구역을 가로질러 합산된다(F4 규율 승계).

    벡터 `same_material_in_two_zones_is_legitimate`가 이 배치를 정상이라고 못박는다 —
    바닥과 중간은 서로 다른 층의 수요이므로 중복이 아니다. 다만 **합계**는 봐야 한다.
    """
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    # STACK 3 · 1H 1층(1) + MID 2~3층(2) = 3 > 2
    _seed_plan(tp_env, "BASE-BA", "A", stack=3,
               mat_1h=["TAPE-X_01"], mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-BA", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BA")
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(body["warnings"])  # 1<=2, 2<=2
    over = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_SOURCE_OVERALLOCATED]
    assert len(over) == 1
    assert over[0]["required_total"] == 3 and over[0]["available"] == 2
    assert set(over[0]["doe_values"]) == {"A[1H]@TAPE-X_01", "A[MID]@TAPE-X_01"}


# ---- 자재 묶음 — 사용자 확정: "한 매당 500칩이면 4매 묶어서 투입" ----

def test_zone_total_is_split_evenly_across_materials(tp_env, client):
    """매별 소요는 지정 대상이 아니라 **구역 총 소요의 균등 배분**이다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2, TAPE-Y/09는 데이터 없음(가용 0)
    _seed_plan(tp_env, "BASE-P", "A", stack=4,
               mat_mid=["TAPE-X_01", "TAPE-Y_09"])
    _paint(tp_env, "BASE-P", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-P")
    short = [w for w in body["warnings"] if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    # 총 소요 = painted 1 × layers 4 = 4, 2매로 나눠 매당 2 → TAPE-X(2) 통과, TAPE-Y(0) 부족
    assert len(short) == 1
    assert short[0]["required"] == 2, "배분하지 않았다면 4가 나온다"
    assert short[0]["demand"] == "A[MID]@TAPE-Y_09"


def test_share_rounds_up_so_shortage_is_never_understated(tp_env, client):
    """배분은 **올림**이다 — 내림/반올림은 부족분을 숨긴다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-CEIL", "A", stack=3,
               mat_mid=["TAPE-X_01", "TAPE-Y_09"])
    _paint(tp_env, "BASE-CEIL", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-CEIL")
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    # 총 3을 2매로 → ceil(3/2) = 2 (내림이면 1이라 TAPE-Y 부족이 숨는다)
    assert short == {"A[MID]@TAPE-Y_09": 2}


def test_shares_aggregate_per_source_across_values(tp_env, client):
    """[QA F4 승계] 여러 값이 같은 자재를 나눠 쓰면 합산 초과배정을 검출한다."""
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    _seed_plan(tp_env, "BASE-OVER", "A", stack=1, mat_mid=["TAPE-X_01"])   # 1
    _seed_plan(tp_env, "BASE-OVER", "B", stack=2, mat_mid=["TAPE-X_01"])   # 2
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


def test_a_stack_with_no_materials_at_all_is_blocked_and_unverified(tp_env, client):
    """자재를 하나도 붙이지 않은 계획은 검증할 것이 없다 — V1이 이유를 말한다.

    구 모델의 "자재 없는 구간"(`source_unresolved`)은 구역 모델에서 **V1**이 됐다: MID
    구역이 5층인데 비어 있다는 것이 더 정확한 진단이고, 사용자를 고쳐야 할 칸으로 보낸다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-NP", "A", stack=5)
    _paint(tp_env, "BASE-NP", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-NP")
    rules = {w["rule"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_ZONE_RULE_VIOLATION}
    assert rules == {"V1"}
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


def test_unreadable_material_token_is_blocked_not_silently_skipped(tp_env, client):
    """해석 못 한 자재는 **검사한 것으로 치지 않는다** — 침묵이 이 모듈의 실패 형태다.

    ⚠️ 무엇이 '해석 불가'인지가 바뀌었다. 분리자 없는 `TAPEX01`은 이제 **로트 전체**라는
    뜻이고(공유 벡터 `bare_lot_means_the_whole_lot`), 진짜 malformed한 것은 매달린
    분리자다. 아래 test가 그 둘을 나눠 고정한다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-MID", "A", stack=1, mat_mid=["TAPE-X_"])   # 매달린 분리자
    _paint(tp_env, "BASE-MID", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-MID")
    v4 = [w for w in body["warnings"]
          if w["type"] == transfer_plan.WARN_ZONE_RULE_VIOLATION and w["rule"] == "V4"]
    assert len(v4) == 1
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


def test_a_whole_lot_token_is_legal_but_is_not_priced_here(tp_env, client):
    """🔴 `TAPEX01`(분리자 없음)은 이제 문법상 정상이다 — 그러나 이 엔드포인트는 로트
    전체의 가용을 **확정 숫자로 내지 않는다**(`scope=lot` 응답에 `chips`가 없는 것과 같은
    이유: 로트 하나의 `remaining`을 지어내지 않는다).

    그래서 "해석 실패"도 "이상 없음"도 아닌 **"판정하지 않았다"**로 이름 붙여 내보내고,
    계획은 unverified로 남는다. 0으로 접으면 "다 썼다"로 읽힌다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-LOT", "A", stack=1, mat_mid=["TAPEX01"])
    _paint(tp_env, "BASE-LOT", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-LOT")
    # V4는 나오면 안 된다 — 이 토큰은 malformed가 아니다.
    assert transfer_plan.WARN_ZONE_RULE_VIOLATION not in _types(body["warnings"])
    unpriced = [w for w in body["warnings"]
                if w["type"] == transfer_plan.WARN_SOURCE_SCOPE_UNPRICED]
    assert len(unpriced) == 1 and unpriced[0]["material"] == "TAPEX01"
    assert unpriced[0]["scope"] == "lot" and unpriced[0]["required"] == 1
    assert body["availability_checked"] is False
    assert body["status"] == "unverified"


def test_bin_suffix_does_not_leak_into_the_slot(tp_env, client):
    """🔴 `ADFE1H_01:3`을 마지막 `_` 기준으로 자르면 슬롯이 `01:3`이 된다 — 존재하지 않는
    슬롯을 물어보고 **멀쩡한 자재에 대해 확신에 찬 0**을 낸다. 공유 벡터
    `slot_with_explicit_bin`이 이것을 못박고, 여기서는 그 파싱이 실제 조회 파라미터까지
    이어지는지 확인한다(가용 2인 TAPE-X/01을 정확히 찾아내면 부족이 나지 않는다)."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-BIN", "A", stack=1, mat_mid=["TAPE-X_01:3"])
    _paint(tp_env, "BASE-BIN", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-BIN")
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(body["warnings"]), \
        "슬롯을 '01:3'으로 읽었다면 가용 0이 되어 부족이 난다"
    assert body["availability_checked"] is True


def test_missing_material_identity_rule_blocks_every_check(tp_env, client, tmp_path, monkeypatch):
    """규칙 미선언은 '해석 규칙 없음'이지 '이상 없음'이 아니다.

    ⚠️ 이 선언은 이제 **게이트**다. 토큰 문법 자체는 공유 계약이고 config가 아니다 —
    클라는 config를 읽지 못하므로 파싱 규칙이 config에 살면 양쪽이 갈리고, 갈리는 순간
    한 화면에 두 개의 가용치가 생긴다. 그래도 선언이 없으면 이 배포의 자재 문자열이
    lot/slot 모양이라는 근거가 없으므로 아무것도 조회하지 않는다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-NOR", "A", stack=1, mat_mid=["TAPE-X_01"])
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


def test_the_overallocation_gate_counts_demands_not_labels(tp_env, client):
    """[B1] 합산 판정의 게이트는 **수요 건수**여야 한다 — 표시 라벨의 유일성이 아니라.

    [제거된 축] 이 규칙이 필요했던 이유는 `seq` 중복이었다: 두 구간이 seq를 공유하면 라벨이
    하나로 뭉쳐 `len(labels) < 2`가 되고, required는 이미 합산됐는데 초과배정 검사만 조용히
    꺼져 **경고 0건 + status ok**가 났다. 구역 모델에는 `seq`가 없고 라벨은
    `값[구역]@자재`라 (값, 구역, 자재)당 유일하다 — 즉 **그 충돌은 표현할 수 없는 상태**다.
    그래도 게이트 자체는 남겨 둔다(라벨 수로 세는 구현으로 되돌아가는 것을 막는다):
    아래는 라벨 2개·수요 2건이고, 개별로는 어느 쪽도 가용을 넘지 않는다.
    """
    _seed_scenario(tp_env)          # TAPE-X/01 가용 2
    # STACK 2 · 1H(1층) + MID(2~2층, 1층) · painted 2 → 각각 2, 2 ≤ 가용 2, 합 4 > 2
    _seed_plan(tp_env, "BASE-DUP", "A", stack=2,
               mat_1h=["TAPE-X_01"], mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-DUP", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-DUP")

    # 개별 수요는 각각 2 ≤ 가용 2라 qty_shortage로는 절대 안 잡힌다 — 합산만이 잡는다
    assert transfer_plan.WARN_QTY_SHORTAGE not in _types(body["warnings"])
    assert body["status"] != "ok", "안전망이 꺼졌다"
    over = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_SOURCE_OVERALLOCATED]
    assert len(over) == 1
    assert over[0]["demand_count"] == 2
    assert over[0]["required_total"] == 4 and over[0]["available"] == 2
    assert set(over[0]["doe_values"]) == {"A[1H]@TAPE-X_01", "A[MID]@TAPE-X_01"}


def test_two_zones_over_the_cap_both_report_shortage(tp_env, client):
    """[B1] 검수자가 측정한 형태 그대로: 두 수요 합이 가용을 크게 넘는데 경고 0건이었다."""
    _seed_scenario(tp_env)
    # STACK 11 · 1H(1층) + MID(2~11층, 10층) · painted 3 → 3, 30
    _seed_plan(tp_env, "BASE-DUP2", "A", stack=11,
               mat_1h=["TAPE-X_01"], mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-DUP2", [(1, 1, "A"), (2, 1, "A"), (3, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-DUP2")
    assert body["status"] == "warnings"
    assert body["availability_checked"] is True
    short = {w["demand"]: w["required"] for w in body["warnings"]
             if w["type"] == transfer_plan.WARN_QTY_SHORTAGE}
    assert short == {"A[1H]@TAPE-X_01": 3, "A[MID]@TAPE-X_01": 30}, short


# ---- [B2] painted 읽기가 수량의 근거다 — 못 읽으면 판정하지 않는다 ----

def test_unreadable_painted_never_reads_as_zero_demand(tp_env, client, tmp_path, monkeypatch):
    """[B2] painted를 못 읽으면 required가 전부 0이 되어 부족이 영원히 발화하지 않는다.

    이건 **회귀**다: 구 모델은 qty_total을 저장에서 읽어 이 실패에 면역이었다. 수량을
    painted에서 유도하도록 바꾸면서 그 읽기가 하중을 받게 됐는데 게이트가 없었다.
    회귀 형태: 50,000칩을 요구하는 DOE가 3칩짜리 소스에 대해 `doe_value_unpainted`
    하나만 냈다 — 그것도 "칠해지지 않았다(수량 0)"고 **사실을 단정하는** 문구로.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-NOPAINT", "A", stack=10, mat_mid=["TAPE-X_01"])
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
    _seed_plan(tp_env, "BASE-PTRUNC", "A", stack=2, mat_mid=["TAPE-X_01"])
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
    _seed_legacy_plan(tp_env, "BASE-UNREAD", "A", "{oops")
    _paint(tp_env, "BASE-UNREAD", [(1, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-UNREAD")
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
        _seed_plan(tp_env, "BASE-ROWCAP", v, stack=1, mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-ROWCAP", [(1, 1, "A"), (2, 1, "B"), (3, 1, "C")])
    tp_env.commit()
    monkeypatch.setattr(transfer_plan, "MAX_DOE_PER_PLAN", 2)
    body = _validate(client, "BASE-ROWCAP")
    caps = _cap_types(body)
    assert [w["role"] for w in caps] == ["plan_registry"]
    assert body["availability_checked"] is False and body["status"] == "unverified"


def test_the_band_cap_now_only_guards_the_legacy_reader(tp_env, client, monkeypatch):
    """[제거된 축] `MAX_BANDS_PER_PLAN`은 계획 전개의 상한이 **아니게 됐다.**

    구역은 행당 정확히 셋이고 행 수는 이미 `MAX_DOE_PER_PLAN`이 묶으므로, 구간 수가 폭주할
    자리가 zone 경로에는 없다 — 그러니 `bands` 역할의 절단 경고도 거기서는 나올 수 없다.
    남은 쓰임은 **폐기 blob 하나가 거대할 때** 그것을 걷지 않고 거부하는 것뿐이고, 그 결과는
    절단이 아니라 `not_convertible` 거부다(접어서 통과시키지 않는다).
    """
    _seed_scenario(tp_env)
    _seed_legacy_plan(tp_env, "BASE-BANDCAP", "A", [
        _band(1, ["TAPE-X_01"], seq=1), _band(2, ["TAPE-X_01"], seq=2),
        _band(3, ["TAPE-X_01"], seq=3),
    ])
    _paint(tp_env, "BASE-BANDCAP", [(1, 1, "A")])
    tp_env.commit()
    monkeypatch.setattr(transfer_plan, "MAX_BANDS_PER_PLAN", 2)
    body = _validate(client, "BASE-BANDCAP")
    assert [w["role"] for w in _cap_types(body)] == [], "zone 경로에는 구간 절단이 없다"
    bad = [w for w in body["warnings"]
           if w["type"] == transfer_plan.WARN_LAYER_RANGE_INVALID]
    assert len(bad) == 1 and bad[0]["reason"] == "not_convertible"
    assert body["status"] == "unverified"


def test_material_cap_reports_materials(tp_env, client, monkeypatch):
    """진단이 거짓말을 하면 안 된다 — 자재를 64에서 잘라 놓고 '구간 2000'이라 보고했다."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-MATCAP", "A", stack=1,
               mat_mid=["TAPE-X_01", "TAPE-Y_09", "TAPE-Z_07"])
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
    _seed_plan(tp_env, "BASE-FAN", "A", stack=1,
               mat_mid=["TAPE-X_01", "TAPE-Y_09", "TAPE-Z_07"])
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
    _seed_plan(tp_env, "BASE-FAILCACHE", "A", stack=3,
               mat_1h=["TAPE-X_01"], mat_mid=["TAPE-X_01"], mat_top=["TAPE-X_01"])
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
    _seed_plan(tp_env, "BASE-SOLO", "A", stack=2, mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-SOLO", [(1, 1, "A"), (2, 1, "A")])
    tp_env.commit()
    body = _validate(client, "BASE-SOLO")
    types = _types(body["warnings"])
    assert transfer_plan.WARN_QTY_SHORTAGE in types
    assert transfer_plan.WARN_SOURCE_OVERALLOCATED not in types


def test_validate_overallocation_skipped_when_degraded(tp_env, client, tmp_path, monkeypatch):
    """[F1 규율] 강등 입력에서는 합산 판정도 하지 않는다(오염된 가용치 사용 금지)."""
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-OVD", "A", stack=1, mat_mid=["TAPE-X_01"])
    _seed_plan(tp_env, "BASE-OVD", "B", stack=2, mat_mid=["TAPE-X_01"])
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
    _seed_plan(tp_env, "BASE-DEG", "A", stack=2, mat_mid=["TAPE-X_01"])   # 2칩 × 2층 = 4
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


@pytest.mark.parametrize("role", ["stack", "mat_1h", "mat_mid", "mat_top"])
def test_registry_without_a_zone_column_is_404_not_a_quiet_pass(tp_env, client, tmp_path,
                                                                monkeypatch, role):
    """zone 역할 미선언은 '구조 없음'이 아니라 **계획을 읽을 수단이 없음**이다.

    조용히 통과시키면 라이브에서 정확히 이 상태(선언 누락)가 "DOE가 하나도 없는 계획"으로
    보인다 — 미선언 컬럼이 200과 함께 드롭되는 것과 같은 계열의 침묵이다.
    네 역할을 **각각** 확인한다: 하나만 검사하면 나머지 셋은 조용히 필수에서 빠질 수 있다.
    """
    cfg = _tp_config()
    del cfg["plan_store"]["registry"]["columns"][role]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    res = client.get("/api/transfer-plan/validate",
                     params={"ref_table": MAP_T, "map_key": "BASE-1"})
    assert res.status_code == 404
    assert client.get("/api/transfer-plan/stages").json()["plan_store"]["registry"] == "missing"


def test_registry_without_the_legacy_bands_column_still_works(tp_env, client, tmp_path,
                                                              monkeypatch):
    """🔴 이 변경의 요점. `bands`는 폐기됐고 writer가 없으므로 **필수 역할일 수 없다.**

    그 컬럼 하나가 필수로 남아 있는 동안 `bands`를 지우려는 모든 사이트에서
    GET /api/transfer-plan/validate가 404였다 — 그래서 컬럼은 "폐기됐지만 선언은 유지"라는
    상태에 묶여 있었다. 여기서 그 매듭이 풀린다: 없으면 폐기 계획을 못 읽을 뿐 200이다.
    """
    _seed_scenario(tp_env)
    _seed_plan(tp_env, "BASE-NOLEG", "A", stack=1, mat_mid=["TAPE-X_01"])
    _paint(tp_env, "BASE-NOLEG", [(1, 1, "A")])
    tp_env.commit()
    cfg = _tp_config()
    del cfg["plan_store"]["registry"]["columns"]["bands"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    assert client.get("/api/transfer-plan/stages").json()["plan_store"]["registry"] == "connected"
    body = _validate(client, "BASE-NOLEG")
    assert body["doe_count"] == 1
    assert body["availability_checked"] is True


def test_validate_unresolvable_map_binding_is_surfaced(tp_env, client, tmp_path, monkeypatch):
    """대상 맵의 좌표 바인딩을 유도할 수 없으면 `map_status: missing`으로 알린다."""
    cfg = _tp_config()
    cfg["stages"]["bonding"]["target_map"]["table"] = "tp_test_bonding_log"   # x/y 없음
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = _validate(client, "BASE-X", ref_table="tp_test_bonding_log")
    assert body["map_status"] == "missing"
    assert body["painted_values"] == {}


def test_painted_values_degrades_honestly_when_derivation_refuses(tp_env):
    """[F2] 값 컬럼이 후보 밖이라 유도가 **거부**하는 맵 — 과거에는 첫 데이터 컬럼을
    추측해 그 분포를 'connected'로 보고했다(미끼 수량). 지금은 x/y 부재와 동일하게
    ({}, 'missing', False)로 강등한다 — crash도, 조용한 추측도 아니다. 'missing'의
    하류 효과(WARN_PAINTED_UNAVAILABLE, unverified)는 위 테스트들이 이미 고정한다."""
    _add(tp_env, "tp_test_valless_map", cell_key="V1", lot="L1", slot="01",
         x=1, y=1, VALCASE="A")
    tp_env.commit()
    painted, status, truncated = transfer_plan._painted_values(
        tp_env, "tp_test_valless_map", "L1_01", {})
    assert (painted, status, truncated) == ({}, "missing", False)


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


# ---------------------------------------------------------------------------
# 6. BIN 축 — `(자재, BIN)` 단위 가용 (DOE_BAND_MODEL §4-bis)
#
# 이 절이 고정하는 것은 숫자 하나가 아니라 **`0`을 쓰지 않는다**는 규칙이다. `0`은
# "다 썼다"로 읽히고, 없는 BIN을 `0`으로 돌려주면 클라가 아무리 조심해도
# "신뢰할 수 없는 `가용`에서 확정 `잔여`를 만들지 않는다"는 계약을 지킬 수 없다.
# ---------------------------------------------------------------------------

def _bins(client, **params):
    p = {"stage": "bonding", "lot": "TAPE-X", "slot": "01"}
    p.update(params)
    res = client.get("/api/transfer-plan/source-summary", params=p)
    assert res.status_code == 200, res.text
    return res.json()


def _entry(body, b):
    got = [e for e in (body["bins"]["entries"] or []) if e["bin"] == b]
    assert len(got) == 1, f"BIN {b} 항목이 {len(got)}개다: {body['bins']['entries']}"
    return got[0]


def test_bins_are_absent_from_the_response_until_asked(tp_env, client):
    """`bins` 파라미터가 없으면 블록도 없다 — 기존 소비자의 응답이 커지지 않는다."""
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    body = _bins(client)
    assert "bins" not in body
    assert body["chips"]["remaining"] == 2      # 기존 계약 그대로


def test_bin_availability_uses_union_semantics_not_subtraction(tp_env, client):
    """[결함 축] BIN 1의 (2,1)은 fail이면서 동시에 기전사다.

    합집합이면 가용 1, `total − fail − used`면 0 — 그리고 0은 "다 썼다"로 읽힌다.
    이 픽스처가 아니면(중복이 없으면) 두 식이 같은 답을 내서 아무것도 증명하지 못한다.
    """
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    body = _bins(client, bins="")
    assert body["bins"]["axis"] == "connected"

    b1 = _entry(body, 1)
    assert b1["status"] == "ok" and b1["reliable"] is True
    assert b1["cells"] == 4                       # '1' 2칸 + '01' 2칸이 한 BIN으로 접힌다
    assert b1["total"] == 4
    assert b1["fail_breakdown"]["all_fail"] == 2  # (1,1),(2,1)
    assert b1["transferred"] == 2                 # (3,1),(2,1)
    assert b1["remaining"] == 1, "감산식이면 0 — 남은 다이를 '다 썼다'로 보고한다"

    b2 = _entry(body, 2)
    assert (b2["cells"], b2["total"], b2["remaining"]) == (4, 4, 1)

    # BIN별 가용의 합은 헤드라인 잔여와 일치한다 (두 숫자가 갈리지 않는다)
    assert b1["remaining"] + b2["remaining"] == body["chips"]["remaining"]


def test_missing_bin_is_bin_absent_and_never_zero(tp_env, client):
    """🔴 이 스펙에서 타협 불가능한 한 줄."""
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    e = _entry(_bins(client, bins="3"), 3)
    assert e["status"] == "bin_absent"
    assert e["remaining"] is None and e["total"] is None
    assert e["reliable"] is False
    assert "3" in e["reason"]          # BIN을 **이름으로** 말한다
    assert e["cells"] == 0             # 맵이 그 BIN을 한 칸도 칠하지 않았다는 사실 자체는 0


def test_bin_that_exists_but_is_fully_consumed_is_a_real_zero(tp_env, client):
    """부재와 소진은 **서로 다른 답**이다 — 소진은 진짜 `0`이고 `reliable`이다."""
    _seed_scenario(tp_env)
    _seed_bins(tp_env, cells=[((1, 1), "5"), ((2, 1), "5")])   # 둘 다 blocked
    e = _entry(_bins(client, bins="5"), 5)
    assert e["status"] == "ok" and e["reliable"] is True
    assert e["cells"] == 2 and e["total"] == 2 and e["remaining"] == 0


def test_bin_spelling_is_normalised_through_the_shared_integer_reader(tp_env, client):
    """`'01'`과 `'1'`은 같은 BIN이다 — 그리고 `'0x10'`은 BIN이 아니다.

    문자열 비교 구현이라면 `'01'` 칸이 통째로 사라지고, 두 번째 숫자 파서를 들이면
    `'0x10'`이 BIN 16이 된다(스펙 §4-bis가 이름으로 지목한 사고).
    """
    _seed_scenario(tp_env)
    _seed_bins(tp_env, cells=[((1, 1), " 7 "), ((2, 1), "07"),
                              ((3, 1), "0x10"), ((4, 1), "CORE-A_01")])
    body = _bins(client, bins="")
    assert _entry(body, 7)["cells"] == 2, "' 7 '과 '07'이 한 BIN으로 접히지 않았다"
    assert [e["bin"] for e in body["bins"]["entries"]] == [7]
    assert body["bins"]["unbinned_cells"] == 2      # '0x10'·'CORE-A_01' — 조용히 버리지 않는다
    assert body["bins"]["cells_total"] == 4


def test_requested_bins_are_all_answered_even_when_absent(tp_env, client):
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    body = _bins(client, bins="1,3,2")
    assert [e["bin"] for e in body["bins"]["entries"]] == [1, 3, 2]   # 요청 순서 보존
    assert body["bins"]["requested"] == [1, 3, 2]
    assert _entry(body, 3)["status"] == "bin_absent"


def test_unreadable_bin_request_is_refused_not_folded_to_one(tp_env, client):
    """`:abc`가 BIN 1로 폴백하면 사용자는 엉뚱한 풀의 수를 본다 (클라 규칙과 같다)."""
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    body = _bins(client, bins="1,abc,0,-2")
    assert [e["bin"] for e in body["bins"]["entries"]] == [1]
    assert set(body["bins"]["refused"]) == {"abc", "0", "-2"}


def test_bin_axis_is_declared_not_guessed(tp_env, client, tmp_path, monkeypatch):
    """선언이 없으면 **못 한다고 말한다** — 아무 val 컬럼이나 BIN으로 추측하지 않는다.

    이 시나리오의 `tp_test_dt_map.val`은 출신 코어 식별자(`CORE-A_01`)다. "맵의 val이
    곧 BIN"으로 박은 구현은 여기서 코어 이름을 BIN으로 세거나 전부 `unbinned`로 접는다.
    """
    cfg = _tp_config()
    del cfg["stages"]["bonding"]["source"]["bin_map"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    body = _bins(client, bins="1")
    assert body["bins"]["axis"] == "unavailable"
    assert body["bins"]["entries"] is None, "빈 배열은 'BIN이 하나도 없다'로 읽힌다"
    assert any(w["type"] == transfer_plan.WARN_BIN_AXIS_UNAVAILABLE
               for w in body["warnings"])


def test_core_kind_stage_says_it_cannot_build_the_axis(tp_env, client):
    """M1 위임 경로는 좌표 집합이 없다 — 감산 없는 셀 수를 `가용`으로 둔갑시키지 않는다."""
    _seed_scenario(tp_env)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "dt", "lot": "CORE-A", "slot": "01",
                              "bins": "1"}).json()
    assert body["bins"]["axis"] == "unavailable"
    assert body["chips"]["remaining"] == 33          # 기존 계약은 그대로
    assert any(w["type"] == transfer_plan.WARN_BIN_AXIS_UNAVAILABLE
               for w in body["warnings"])


def test_degraded_source_makes_every_bin_unreliable_with_no_number(tp_env, client,
                                                                   tmp_path, monkeypatch):
    """🔴 `가용`을 신뢰할 수 없으면 숫자를 내보내지 않는다 — 플래그로 취소하지 않는다."""
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["transfer_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    body = _bins(client, bins="1")
    assert body["chips"]["remaining_reliable"] is False
    e = _entry(body, 1)
    assert e["reliable"] is False and e["remaining"] is None
    assert e["status"] == "unknown"          # 부재도 0도 아니다
    assert e["reason"]


def test_bin_population_mismatch_is_named_not_silent(tp_env, client):
    """맵이 칩 하나를 칠하지 않으면 `Σ BIN 총계 < 총칩`이 된다 — 조용히 넘어가지 않는다."""
    _seed_scenario(tp_env)
    _seed_bins(tp_env, cells=[((x, 1), "1") for x in range(1, 5)]
                             + [((x, 2), "2") for x in range(1, 4)])   # (4,2) 미도색
    body = _bins(client, bins="")
    assert any(w["type"] == transfer_plan.WARN_BIN_POPULATION_MISMATCH
               for w in body["warnings"])


def test_partial_bin_request_does_not_report_a_population_mismatch(tp_env, client):
    """요청한 BIN만 물으면 부분합이 작은 게 당연하다 — 그걸 불일치라 부르면 늑대다."""
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    body = _bins(client, bins="1")
    assert not any(w["type"] == transfer_plan.WARN_BIN_POPULATION_MISMATCH
                   for w in body["warnings"])


# ---- 로트 전체 (`scope=lot`) — 토큰 `MID1:2`의 정의된 뜻 ----

def _seed_second_slot(db):
    """TAPE-X/**02** — CORE-A 출신 2칩. (3,3)은 defect라 tape (1,1)에 투영된다.

    슬롯 01과 달리 BIN 2가 **없다** — 한 슬롯에만 있는 BIN이 로트 수준에서 '부재'로
    접히지 않는지를 이 비대칭이 검사한다.
    """
    for i, (cx, cy, tx, ty) in enumerate([(3, 3, 1, 1), (4, 4, 2, 1)]):
        _add(db, "tp_test_dt_log", dt_id=f"DT2-{i}", tape_lot="TAPE-X", tape_slot="02",
             tx=tx, ty=ty, core_lot="CORE-A", core_slot="01", cx=cx, cy=cy)
        _add(db, "tp_test_bin_map", cell_key=f"BM2_{tx}_{ty}",
             lot="TAPE-X", slot="02", x=tx, y=ty, bin="1")
    for s in ("01", "02"):
        _add(db, "tp_test_lot_wafers", wafer_key=f"TAPE-X_{s}", lot="TAPE-X", slot=s)
    db.commit()


def test_whole_lot_sums_every_slot(tp_env, client):
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    _seed_second_slot(tp_env)
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "bonding", "lot": "TAPE-X",
                             "scope": "lot", "bins": ""})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["identity"] == {"lot": "TAPE-X", "slot": None}
    assert body["slots"] == ["01", "02"]
    # 로트 단위 헤드라인 잔여는 아무도 요청하지 않은 숫자다 — 만들지 않는다.
    assert "chips" not in body

    b1 = _entry(body, 1)
    assert b1["cells"] == 4 + 2
    assert b1["remaining"] == 1 + 1, "슬롯 02의 (2,1) 한 칸이 더해져야 한다"
    # BIN 2는 슬롯 01에만 있다 — 로트 수준에서는 **존재**한다
    b2 = _entry(body, 2)
    assert b2["status"] == "ok" and b2["remaining"] == 1


def test_whole_lot_absence_requires_absence_in_every_slot(tp_env, client):
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    _seed_second_slot(tp_env)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X",
                              "scope": "lot", "bins": "9"}).json()
    e = _entry(body, 9)
    assert e["status"] == "bin_absent" and e["remaining"] is None


def test_whole_lot_and_a_slot_together_is_refused(tp_env, client):
    """B10과 같은 규율 — 두 형태를 한 질의로 섞으면 그 슬롯이 두 번 계산된다."""
    _seed_scenario(tp_env)
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "bonding", "lot": "TAPE-X", "slot": "01",
                             "scope": "lot", "bins": ""})
    assert res.status_code == 400


def test_whole_lot_refuses_to_sum_when_one_slot_is_unreliable(tp_env, client,
                                                              tmp_path, monkeypatch):
    """신뢰 가능한 슬롯만 더한 부분합은 **잔여 과소 → 부풀린 소요**다."""
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["transfer_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    _seed_second_slot(tp_env)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X",
                              "scope": "lot", "bins": "1"}).json()
    e = _entry(body, 1)
    assert e["status"] == "unknown" and e["remaining"] is None and e["reliable"] is False


def test_bad_scope_is_refused(tp_env, client):
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "bonding", "lot": "TAPE-X", "scope": "wafer"})
    assert res.status_code == 400


# ---- 로트 전개 — 자재 리스트가 슬롯 단위로 펼쳐진다 (사용자 확정 2026-07-27) ----
#
# 이것은 표시 편의가 아니라 **로트 데이터 품질의 진단면**이다. 랏이 스플릿됐는데 전산에
# 자재가 그대로 남아 있으면 사람이 그 어긋남을 여기서 보고 그리드에서 고친다(핵심가치 ①).
# 그래서 전개 목록은 **실제로 기록된 것**을 보여야 한다 — 맵이 있는 것만 세면 안 된다.

def _lot(client, **params):
    p = {"stage": "bonding", "lot": "TAPE-X", "scope": "lot", "bins": ""}
    p.update(params)
    res = client.get("/api/transfer-plan/source-summary", params=p)
    assert res.status_code == 200, res.text
    return res.json()


def test_lot_expands_to_one_row_per_slot(tp_env, client):
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    _seed_second_slot(tp_env)
    body = _lot(client)
    assert body["slots_origin"] == "membership"
    assert [e["slot"] for e in body["by_slot"]] == ["01", "02"]
    assert all(e["map_exists"] for e in body["by_slot"])
    # 슬롯 행마다 자기 BIN 수치를 든다 (로트 합계 하나로 접히지 않는다)
    s1 = {e["bin"]: e for e in body["by_slot"][0]["bins"]}
    assert s1[1]["remaining"] == 1 and s1[2]["remaining"] == 1


def test_slot_recorded_without_a_map_is_shown_not_dropped(tp_env, client):
    """🔴 진단의 핵심 행 — 전산에는 있는데 맵이 없는 슬롯.

    맵에서 슬롯을 세면 이 행이 **아예 없어져** 화면이 조용히 '깨끗함'을 보고한다.
    그것이 정확히 사용자가 잡고 싶어하는 상태(랏 스플릿 후 자재가 OVER하게 남음)다.
    """
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    _seed_second_slot(tp_env)
    # 03은 대장에만 있고 맵이 없다 — 랏 스플릿 뒤 정리되지 않은 자재
    _add(tp_env, "tp_test_lot_wafers", wafer_key="TAPE-X_03", lot="TAPE-X", slot="03")
    tp_env.commit()

    body = _lot(client)
    slots = {e["slot"]: e for e in body["by_slot"]}
    assert "03" in slots, "대장에 있는 슬롯이 전개에서 사라졌다 — 진단이 죽는다"
    assert slots["03"]["map_exists"] is False
    warn = [w for w in body["warnings"]
            if w["type"] == transfer_plan.WARN_LOT_SLOT_MAP_MISSING]
    assert warn and warn[0]["slots"] == ["03"]


def test_membership_falls_back_to_the_map_and_says_so(tp_env, client, tmp_path, monkeypatch):
    """대장 미선언은 조용한 폴백이 아니다 — 한계를 이름으로 말한다."""
    cfg = _tp_config()
    del cfg["stages"]["bonding"]["source"]["lot_membership"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    _seed_second_slot(tp_env)
    _add(tp_env, "tp_test_lot_wafers", wafer_key="TAPE-X_03", lot="TAPE-X", slot="03")
    tp_env.commit()

    body = _lot(client)
    assert body["slots_origin"] == "map"
    assert [e["slot"] for e in body["by_slot"]] == ["01", "02"]   # 03은 맵이 없어 안 보인다
    assert any(w["type"] == transfer_plan.WARN_LOT_MEMBERSHIP_DEGRADED
               for w in body["warnings"]), "강등을 말하지 않으면 진단이 거짓 음성이 된다"


def test_unenumerable_lot_is_unknown_never_an_empty_list(tp_env, client,
                                                         tmp_path, monkeypatch):
    """🔴 빈 목록은 '자재가 없다'로 읽힌다 — 알 수 없으면 알 수 없다고 해야 한다."""
    cfg = _tp_config()
    del cfg["stages"]["bonding"]["source"]["lot_membership"]
    del cfg["stages"]["bonding"]["source"]["bin_map"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(tp_env)
    body = _lot(client)
    assert body["slots"] is None and body["by_slot"] is None
    assert body["slots_status"] == "unknown"
    assert any(w["type"] == transfer_plan.WARN_LOT_MEMBERSHIP_UNKNOWN
               for w in body["warnings"])


def test_pooled_figure_is_labelled_a_sufficiency_check_not_an_allocation(tp_env, client):
    """균등배분처럼 보이는 수를 배분이라 부르면, 아무도 지키지 않는 배분을 지킨다고 믿는다."""
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    _seed_second_slot(tp_env)
    assert _lot(client)["bins"]["basis"] == "pool_sufficiency"


# ---------------------------------------------------------------------------
# 16. count-only transfer_log + declared-but-unresolved columns (FIX 2026-07-28)
# ---------------------------------------------------------------------------
# Bug pinned here: transfer_log bound WITHOUT usable x/y on the origin_log-connected
# path left used_set empty while `transferred` displayed the count, so
# remaining = total - |fail ∪ used_set| never subtracted the transferred chips
# (phantom remaining, remaining_reliable true, by_core.used serving a fake 0).

def _summary(client, **params):
    res = client.get("/api/transfer-plan/source-summary", params=params)
    assert res.status_code == 200
    return res.json()


def test_count_only_transfer_log_demotes_and_serves_upper_bound(tp_env, client,
                                                                tmp_path, monkeypatch):
    _seed_scenario(tp_env)
    # Control first: fully bound -> plain connected, exact union remaining.
    body = _summary(client, stage="bonding", lot="TAPE-X", slot="01")
    assert body["sources"]["transfer_log"] == "connected"
    assert body["chips"]["remaining"] == 2 and body["chips"]["remaining_reliable"] is True

    # Drop x/y from transfer_log (count survives, chip identity does not).
    cfg = _tp_config()
    for k in ("x", "y"):
        del cfg["stages"]["bonding"]["source"]["transfer_log"]["columns"][k]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)

    body = _summary(client, stage="bonding", lot="TAPE-X", slot="01")
    assert body["sources"]["transfer_log"] == "connected(count_only)"
    chips = body["chips"]
    assert chips["transferred"] == 4          # row count is real and stays displayed
    assert chips["remaining"] is None         # never the phantom 4
    assert chips["remaining_reliable"] is False
    # Upper bound is genuine: total - |fail_union| = 8 - 4 = 4 >= true remaining 2.
    assert chips["remaining_upper_bound"] == 4
    warns = [w for w in body["warnings"]
             if w.get("type") == transfer_plan.WARN_SOURCE_DEGRADED
             and w.get("role") == "transfer_log"]
    assert warns and warns[0]["effect"] == transfer_plan.EFFECT_REMAINING_OVERSTATED

    # by_core (log path): per-core used is unknowable -> null, never a fake 0,
    # and the remaining derived from it is null too (a bare total-fail number
    # would be the same phantom at per-core level, with no unreliable label).
    assert body["by_core_origin"] == "log"
    by_core = {(r["core_lot"], r["core_slot"]): r for r in body["by_core"]}
    for core in (("CORE-A", "01"), ("CORE-B", "02")):
        assert by_core[core]["used"] is None
        assert by_core[core]["remaining"] is None
        assert by_core[core]["fail"] == 2     # fail projection is unaffected


def test_count_only_by_core_area_map_used_is_null_too(tp_env, client, tmp_path,
                                                      monkeypatch):
    """Fallback by_core (area_map) derives used/remaining from used_set as well —
    in count-only state both must be null, not 0/total."""
    _seed_scenario(tp_env)
    cfg = _tp_config()
    for k in ("x", "y"):
        del cfg["stages"]["bonding"]["source"]["transfer_log"]["columns"][k]
    cfg["stages"]["bonding"]["source"]["origin_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = _summary(client, stage="bonding", lot="TAPE-X", slot="01")
    assert body["sources"]["transfer_log"] == "connected(count_only)"
    assert body["by_core_origin"] == "area_map"
    for row in body["by_core"]:
        assert row["used"] is None and row["remaining"] is None


def test_typo_transfer_log_column_carries_both_markers(tp_env, client, tmp_path,
                                                       monkeypatch):
    """Declared "x": "cxx" (typo) is not an omission: the status must name the
    unresolved column on top of the count-only demotion, and /stages must show it."""
    _seed_scenario(tp_env)
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["transfer_log"]["columns"]["x"] = "cxx"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)

    body = _summary(client, stage="bonding", lot="TAPE-X", slot="01")
    assert body["sources"]["transfer_log"] == "connected(count_only,column_unresolved:x)"
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_upper_bound"] == 4
    assert body["chips"]["transferred"] == 4

    stages = client.get("/api/transfer-plan/stages").json()["stages"]
    bd = next(s for s in stages if s["name"] == "bonding")
    assert bd["roles"]["transfer_log"] == "connected(column_unresolved:x)"


def test_typo_fail_val_column_refuses_the_unfiltered_count(tp_env, client, tmp_path,
                                                           monkeypatch):
    """defect "val": "vall" with fail_values declared: projecting without the filter
    would mark every origin chip as fail (remaining understated — would break the
    upper-bound invariant in the other direction). Must serve 0 + demoted status."""
    _seed_scenario(tp_env)
    cfg = _tp_config()
    cfg["stages"]["bonding"]["source"]["fail_sources"]["defect"]["columns"]["val"] = "vall"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    body = _summary(client, stage="bonding", lot="TAPE-X", slot="01")
    assert body["sources"]["defect"] == "connected(column_unresolved:val)"
    assert body["chips"]["fail_breakdown"]["defect"] == 0
    assert body["chips"]["remaining"] is None
    # eds ∪ used = {(1,1),(2,2)} ∪ {(3,1),(4,2),(2,1)} = 5 -> upper bound 8-5 = 3 >= true 2
    assert body["chips"]["remaining_upper_bound"] == 3


def test_dt_reshape_carries_the_unresolved_demotion(tp_env, client, tmp_path,
                                                    monkeypatch):
    """M1-delegated (dt) path: a typo in the bonding_plan config must surface through
    the reshape with the same reliability consequences."""
    _seed_scenario(tp_env)
    bp = _bp_config()
    bp["sources"]["defect"]["columns"]["val"] = "vall"
    _write_cfg(tmp_path, monkeypatch, bp_cfg=bp)
    body = _summary(client, stage="dt", lot="CORE-A", slot="01")
    assert body["sources"]["defect"] == "connected(column_unresolved:val)"
    assert body["chips"]["fail_breakdown"]["defect"] == 0
    assert body["chips"]["remaining"] is None
    # M1 subtraction with the corrupted term zeroed: 36 - 0 - 1 - 0 = 35 (upper bound)
    assert body["chips"]["remaining_upper_bound"] == 35


def test_omitted_optional_columns_still_plain_connected(tp_env, client):
    """Regression guard for the ⓑ boundary: bindings that never declare optional
    columns keep their exact statuses (no column_unresolved noise anywhere)."""
    _seed_scenario(tp_env)
    body = _summary(client, stage="bonding", lot="TAPE-X", slot="01")
    assert "column_unresolved" not in json.dumps(body["sources"])
    assert body["chips"]["remaining"] == 2
