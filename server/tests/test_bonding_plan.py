"""본딩 실험계획 M1 — 역할 바인딩 config + 집계 API 검증 (Server_bonding_plan_m1_task §C 계약).

검증 범위:
- 집계 정확성(모의 데이터): total/defect/eds_fail/used(distinct)/remaining
- region 교차: canonical 좌표 rect 합집합 + align(180) 사상 — 변환 없이 겹치면 틀리는
  네거티브 케이스 포함(얼라인 실증), 격자 규격 클램프, 형식 위반 400
- align: 단순형/확장형(by_eqp 파싱 통과), 90°(비정방 격자 스왑 정합 — QA 감사 F1),
  flip, grid meta 부재 시 명시 실패(align_unavailable — QA 감사 F2 취지)
- 역할 missing 부분 가동 / knobs 폴백 / 미존재 조합 200 / history 50건 상한·오름차순 / warnings

[격리] 테이블명은 사용자 실 config에 실존 불가능한 bdp_test_* 접두를 사용한다
(conftest가 import 시점에 실 config로 초기화하므로 실존 테이블명과 겹치면 격리 실패).
"""
import json
import uuid

import pytest

import bonding_plan
from database import crud, models

# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

BDP_TABLES = {
    "bdp_test_wafer_process": {
        "business_key": "proc_id",
        "column_types": {
            "proc_id": "string", "lot": "string", "slot": "string",
            "step": "string", "eqp_id": "string", "start_time": "string",
            "result": "string", "recipe_id": "string", "knobs": "string",
        },
    },
    "bdp_test_core_defect_map": {
        "business_key": "chip_key",
        "composite_key_source": ["lot", "slot", "x", "y"],
        "composite_key_separator": "_",
        "column_types": {
            "chip_key": "string", "lot": "string", "slot": "string",
            "x": "number", "y": "number", "val": "string",
        },
        "map_key_columns": ["lot", "slot"],
    },
    "bdp_test_eds_fail_map": {
        "business_key": "chip_key",
        "composite_key_source": ["lot", "slot", "x", "y"],
        "composite_key_separator": "_",
        "column_types": {
            "chip_key": "string", "lot": "string", "slot": "string",
            "x": "number", "y": "number", "val": "string", "metro_eqp": "string",
        },
        "map_key_columns": ["lot", "slot"],
    },
    "bdp_test_bonding_log": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "core_lot": "string", "core_slot": "string",
            "cx": "number", "cy": "number",
        },
    },
    "bdp_test_map_meta": {
        "business_key": "map_pk",
        "column_types": {
            "map_pk": "string", "target_table": "string",
            "map_id": "string", "grid_metadata": "string",
        },
    },
}

# 테스트 격자: 6x6, start (1,1) — canonical(CORE) 프레임
GRID = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
        "grid_y_invert": False, "side": "front",
        "phys_wafer_dia": 300, "phys_chip_x": 7, "phys_chip_y": 7,
        "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3}


def _bdp_config(align_eds=True):
    cfg = {
        "core_identity": {"compose": ["lot", "slot"]},
        "map_metadata": {
            "table": "bdp_test_map_meta",
            "columns": {"target_table": "target_table", "map_id": "map_id",
                        "grid_metadata": "grid_metadata"},
        },
        "sources": {
            "process_history": {
                "table": "bdp_test_wafer_process",
                "columns": {"step": "step", "eqp": "eqp_id", "result": "result",
                            "time": "start_time", "recipe": "recipe_id",
                            "knobs": "knobs", "lot": "lot", "slot": "slot"},
            },
            "defect": {
                "mode": "map", "table": "bdp_test_core_defect_map",
                "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val"},
                "fail_values": ["D"],
            },
            "eds_fail": {
                "mode": "map", "table": "bdp_test_eds_fail_map",
                "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val"},
                "fail_values": ["F"],
            },
            "used_chips": {
                "table": "bdp_test_bonding_log",
                "columns": {"lot": "core_lot", "slot": "core_slot", "x": "cx", "y": "cy"},
            },
            "total_chips": {
                "mode": "map", "table": "bdp_test_core_defect_map",
                "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y"},
            },
        },
        "warnings": {"result_fail_values": ["FAIL"]},
    }
    if align_eds:
        # 확장형(default + by_eqp) — M1은 default만 적용, by_eqp는 파싱 통과(M2 예약)
        cfg["sources"]["eds_fail"]["align"] = {
            "default": {"rotation": 180, "flip": "none", "offset": {"x": 0, "y": 0}},
            "by_eqp": {"METRO-A": {"rotation": 90}},
        }
    return cfg


def _add(db, table, **cols):
    model = models.DYNAMIC_TABLES[table]
    bk = BDP_TABLES[table]["business_key"]
    row = model(row_id=str(uuid.uuid4()),
                business_key_val=str(cols.get(bk) or uuid.uuid4()), **cols)
    db.add(row)
    return row


def _add_meta(db, target_table, map_id, rotation=0, cols=6, rows=6):
    meta = dict(GRID)
    meta["rotation"] = rotation
    meta["grid_cols"] = cols
    meta["grid_rows"] = rows
    _add(db, "bdp_test_map_meta",
         map_pk=f"{target_table}_{map_id}", target_table=target_table,
         map_id=map_id, grid_metadata=json.dumps(meta))


@pytest.fixture()
def bdp_env(db_session, tmp_path, monkeypatch):
    """bdp_test_* 테이블 등록 + config 파일 스냅샷 경로 monkeypatch."""
    models.init_dynamic_models(BDP_TABLES)
    crud.TABLE_CONFIG.update(BDP_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    cfg_path = tmp_path / "bonding_plan_config.json"
    cfg_path.write_text(json.dumps(_bdp_config()), encoding="utf-8")
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(cfg_path))

    return db_session


def _seed_core(db, lot="LOTX", slot="01"):
    """기준 코어: 6x6 풀 defect 맵(불량 2), EDS 180° 회전 맵(불량 2), 사용 칩 3행(distinct 2)."""
    # defect(=total) 풀맵: 36칩, (2,2)·(3,3)만 "D"
    for y in range(1, 7):
        for x in range(1, 7):
            val = "D" if (x, y) in ((2, 2), (3, 3)) else "P"
            _add(db, "bdp_test_core_defect_map",
                 chip_key=f"{lot}_{slot}_{x}_{y}", lot=lot, slot=slot, x=x, y=y, val=val)
    _add_meta(db, "bdp_test_core_defect_map", f"{lot}_{slot}", rotation=0)

    # EDS: 자기 프레임 = 180° 회전 (6x6 start 1 → 저장좌표 = 7 - canonical)
    # canonical fail 위치 (1,1), (5,2) → 저장 (6,6), (2,5). 정상 칩 2개도 저장(카운트 필터 검증).
    for cx, cy in ((1, 1), (5, 2)):
        _add(db, "bdp_test_eds_fail_map",
             chip_key=f"{lot}_{slot}_{7-cx}_{7-cy}", lot=lot, slot=slot,
             x=7 - cx, y=7 - cy, val="F", metro_eqp="METRO-A")
    for sx, sy in ((1, 2), (3, 4)):
        _add(db, "bdp_test_eds_fail_map",
             chip_key=f"{lot}_{slot}_{sx}_{sy}", lot=lot, slot=slot,
             x=sx, y=sy, val="P", metro_eqp="METRO-B")
    _add_meta(db, "bdp_test_eds_fail_map", f"{lot}_{slot}", rotation=180)

    # used: (1,2) 중복 2행 + (4,4) → distinct 2
    for i, (cx, cy) in enumerate([(1, 2), (1, 2), (4, 4)]):
        _add(db, "bdp_test_bonding_log",
             log_id=f"BL-{lot}-{i}", core_lot=lot, core_slot=slot, cx=cx, cy=cy)

    # history: 3건 (중간에 FAIL 1건 — warning), knobs 정상 JSON / 깨진 문자열 혼재
    _add(db, "bdp_test_wafer_process", proc_id="WP-1", lot=lot, slot=slot,
         step="ETCH", eqp_id="EQP-7", start_time="2026-07-26 09:00", result="PASS",
         recipe_id="R-ETCH-01", knobs=json.dumps({"depth_um": 1.2, "gas": "CF4"}))
    _add(db, "bdp_test_wafer_process", proc_id="WP-2", lot=lot, slot=slot,
         step="CMP", eqp_id="EQP-3", start_time="2026-07-26 10:00", result="FAIL",
         recipe_id="R-CMP-01", knobs="{broken json")
    _add(db, "bdp_test_wafer_process", proc_id="WP-3", lot=lot, slot=slot,
         step="DEPO", eqp_id="EQP-1", start_time="2026-07-26 11:00", result="PASS",
         recipe_id="R-DEPO-01", knobs="")
    db.commit()


# ---------------------------------------------------------------------------
# 1. 집계 정확성
# ---------------------------------------------------------------------------

def test_core_summary_counts(bdp_env, client):
    _seed_core(bdp_env)
    res = client.get("/api/bonding-plan/core-summary", params={"lot": "LOTX", "slot": "01"})
    assert res.status_code == 200
    body = res.json()

    assert body["identity"] == {"lot": "LOTX", "slot": "01"}
    assert body["chips"] == {
        "total": 36, "defect": 2, "eds_fail": 2, "used": 2,
        "remaining": 36 - 2 - 2 - 2,
    }
    assert body["sources"]["process_history"] == "connected"
    assert body["sources"]["defect"] == "connected"
    assert body["sources"]["total_chips"] == "connected"
    assert body["sources"]["used_chips"] == "connected"
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"
    assert "region_chips" not in body


def test_history_and_warnings(bdp_env, client):
    _seed_core(bdp_env)
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "LOTX", "slot": "01"}).json()
    hist = body["history"]
    assert [h["step"] for h in hist] == ["ETCH", "CMP", "DEPO"]  # 시간 오름차순
    assert hist[0]["knobs"] == {"depth_um": 1.2, "gas": "CF4"}   # 정상 JSON → dict
    assert hist[1]["knobs"] == "{broken json"                    # 폴백 → raw 문자열 (에러 아님)
    assert hist[0]["recipe"] == "R-ETCH-01"
    assert hist[0]["eqp"] == "EQP-7"

    warns = body["warnings"]
    assert len(warns) == 1
    assert warns[0]["type"] == "result_fail"
    assert "CMP" in warns[0]["detail"] and "FAIL" in warns[0]["detail"] and "EQP-3" in warns[0]["detail"]


def test_history_capped_at_50_ascending(bdp_env, client):
    db = bdp_env
    for i in range(60):
        _add(db, "bdp_test_wafer_process", proc_id=f"WP-CAP-{i}", lot="LOTC", slot="09",
             step=f"S{i:02d}", eqp_id="EQP-1", start_time=f"2026-07-25 {i // 60:02d}:{i % 60:02d}",
             result="PASS", recipe_id="R", knobs="")
    db.commit()
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "LOTC", "slot": "09"}).json()
    hist = body["history"]
    assert len(hist) == 50
    times = [h["time"] for h in hist]
    assert times == sorted(times)          # 오름차순
    assert times[-1] == "2026-07-25 00:59"  # 최근 50건 유지 (오래된 10건 탈락)
    assert times[0] == "2026-07-25 00:10"


# ---------------------------------------------------------------------------
# 2. region 교차 (align 실증 포함)
# ---------------------------------------------------------------------------

def _region(rects):
    return json.dumps({"rects": rects})


def test_region_intersection_with_align(bdp_env, client):
    _seed_core(bdp_env)
    # canonical rect (1..2, 1..2): total 4 / defect(2,2) 1 / eds canonical(1,1) 1 / used(1,2) 1
    res = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTX", "slot": "01",
        "region": _region([{"x1": 1, "y1": 1, "x2": 2, "y2": 2}]),
    })
    assert res.status_code == 200
    body = res.json()
    assert body["region_chips"] == {
        "total": 4, "defect": 1, "eds_fail": 1, "used": 1, "remaining": 1,
    }
    # 전체 집계는 region과 무관하게 동일 유지
    assert body["chips"]["total"] == 36


def test_region_align_negative_control(bdp_env, client, tmp_path, monkeypatch):
    """align 미선언 config로 같은 region 조회 → EDS 저장좌표 그대로 비교되어 0이 나와야 한다.

    (변환 없이 겹치면 틀리는 케이스 — align이 실제로 작동함을 증명하는 대조군)
    """
    _seed_core(bdp_env)
    cfg_path = tmp_path / "no_align.json"
    cfg_path.write_text(json.dumps(_bdp_config(align_eds=False)), encoding="utf-8")
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(cfg_path))

    body = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTX", "slot": "01",
        "region": _region([{"x1": 1, "y1": 1, "x2": 2, "y2": 2}]),
    }).json()
    # canonical fail (1,1)은 저장좌표 (6,6) — align 없이는 rect에 안 잡힌다
    assert body["region_chips"]["eds_fail"] == 0
    assert body["sources"]["eds_fail"] == "connected"


def test_region_multi_rect_union_and_clamp(bdp_env, client):
    _seed_core(bdp_env)
    # rect1: 격자 밖으로 넘치는 rect → 메타 규격(6x6, start 1)으로 클램프되어 전체 격자와 동일
    body = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTX", "slot": "01",
        "region": _region([{"x1": -10, "y1": 0, "x2": 99, "y2": 99}]),
    }).json()
    assert body["region_chips"]["total"] == 36
    assert body["region_chips"]["defect"] == 2
    assert body["region_chips"]["eds_fail"] == 2
    assert body["region_chips"]["used"] == 2

    # 완전히 범위 밖 rect + 유효 rect 합집합 → 유효 rect만 기여 (합집합·중복 미가산)
    body = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTX", "slot": "01",
        "region": _region([
            {"x1": 100, "y1": 100, "x2": 200, "y2": 200},
            {"x1": 2, "y1": 2, "x2": 3, "y2": 3},
            {"x1": 3, "y1": 3, "x2": 3, "y2": 3},  # 중복 rect — 이중 가산 금지
        ]),
    }).json()
    assert body["region_chips"]["total"] == 4
    assert body["region_chips"]["defect"] == 2  # (2,2), (3,3)


def test_region_malformed_returns_400(bdp_env, client):
    for bad in ("not-json", json.dumps({"nope": []}), json.dumps({"rects": [{"x1": 1}]})):
        res = client.get("/api/bonding-plan/core-summary",
                         params={"lot": "LOTX", "slot": "01", "region": bad})
        assert res.status_code == 400, bad


def test_region_align_unavailable_without_grid_meta(bdp_env, client):
    """align 선언 + grid meta 부재 → 조용히 raw 좌표로 계산하지 않고 명시 실패(QA F2 취지)."""
    db = bdp_env
    # 메타 없이 EDS fail 1건만 시딩
    _add(db, "bdp_test_eds_fail_map", chip_key="LOTN_01_6_6",
         lot="LOTN", slot="01", x=6, y=6, val="F", metro_eqp="METRO-A")
    db.commit()
    body = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTN", "slot": "01",
        "region": _region([{"x1": 1, "y1": 1, "x2": 6, "y2": 6}]),
    }).json()
    assert body["sources"]["eds_fail"] == "connected(align_unavailable)"
    assert body["region_chips"]["eds_fail"] == 0
    assert body["chips"]["eds_fail"] == 1  # 전체 카운트는 변환 불변이라 유효


# ---------------------------------------------------------------------------
# 3. 역할 missing 부분 가동 / 미존재 조합
# ---------------------------------------------------------------------------

def test_missing_role_partial_operation(bdp_env, client, tmp_path, monkeypatch):
    _seed_core(bdp_env)
    cfg = _bdp_config()
    del cfg["sources"]["defect"]
    cfg["sources"]["used_chips"]["table"] = "bdp_test_no_such_table"  # 모델 부재 → missing
    cfg_path = tmp_path / "partial.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(cfg_path))

    res = client.get("/api/bonding-plan/core-summary", params={"lot": "LOTX", "slot": "01"})
    assert res.status_code == 200  # 에러 아님 — 부분 가동
    body = res.json()
    assert body["sources"]["defect"] == "missing"
    assert body["sources"]["used_chips"] == "missing"
    assert body["chips"]["defect"] == 0 and body["chips"]["used"] == 0
    assert body["chips"]["remaining"] == 36 - 0 - 2 - 0  # missing 역할은 0으로 계산


def test_empty_config_all_missing(bdp_env, client, tmp_path, monkeypatch):
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(tmp_path / "does_not_exist.json"))
    res = client.get("/api/bonding-plan/core-summary", params={"lot": "L", "slot": "1"})
    assert res.status_code == 200
    body = res.json()
    assert set(body["sources"]) == set(bonding_plan.ROLES)
    assert all(v == "missing" for v in body["sources"].values())
    assert body["chips"]["remaining"] == 0


def test_unknown_combo_all_connected_zero(bdp_env, client):
    _seed_core(bdp_env)
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "NOPE", "slot": "99"}).json()
    assert body["chips"]["total"] == 0
    assert body["chips"]["remaining"] == 0
    assert body["history"] == [] and body["warnings"] == []
    # sources 전부 connected여도 total=0 — 뷰 쪽 "미확인 코어" 표시용 계약
    assert body["sources"]["defect"] == "connected"
    assert body["sources"]["total_chips"] == "connected"


# ---------------------------------------------------------------------------
# 4. align 단위 검증 (M2 재사용 경로 — 외부 주입 파라미터)
# ---------------------------------------------------------------------------

def test_normalize_align_simple_and_extended():
    simple = bonding_plan.normalize_align({"rotation": 180, "flip": "x", "offset": {"x": 1, "y": -2}})
    assert simple["rotation"] == 180 and simple["flip"] == "x"
    assert simple["offset_x"] == 1 and simple["offset_y"] == -2
    assert not simple["is_identity"]

    ext = bonding_plan.normalize_align({
        "default": {"rotation": 90},
        "by_eqp": {"METRO-A": {"rotation": 270}},
    })
    assert ext["rotation"] == 90
    assert ext["by_eqp"] == {"METRO-A": {"rotation": 270}}  # 파싱 통과·보존 (M2 예약)

    assert bonding_plan.normalize_align(None) is None
    assert bonding_plan.normalize_align({"rotation": 45})["rotation"] == 0  # 무효값 → 0 강등
    assert bonding_plan.normalize_align({})["is_identity"]


def test_align_transform_180_roundtrip():
    align = bonding_plan.normalize_align({"rotation": 180})
    grid = {"cols": 6, "rows": 6, "start_x": 1, "start_y": 1}
    t = bonding_plan.make_align_transform(align, grid)
    assert t(6, 6) == (1, 1)
    assert t(2, 5) == (5, 2)
    # 전 셀 전단사(자기 자신 격자로)
    cells = {t(x, y) for x in range(1, 7) for y in range(1, 7)}
    assert cells == {(x, y) for x in range(1, 7) for y in range(1, 7)}


def test_align_transform_90_nonsquare_grid():
    """rot 90 + 비정방 격자 — 소스 자기 프레임 치수는 canonical의 스왑(QA 감사 F1 정합)."""
    align = bonding_plan.normalize_align({"rotation": 90})
    src_grid = {"cols": 3, "rows": 4, "start_x": 1, "start_y": 1}   # 소스 자기 프레임
    dst_grid = {"cols": 4, "rows": 3, "start_x": 1, "start_y": 1}   # canonical
    t = bonding_plan.make_align_transform(align, src_grid, dst_grid)
    # 전단사: 소스 3x4 → canonical 4x3
    out = {t(x, y) for x in range(1, 4) for y in range(1, 5)}
    assert out == {(x, y) for x in range(1, 5) for y in range(1, 4)}
    assert t(1, 1) == (1, 3)  # cell_to_physical(rot 90) 관례: xp=r, yp=(visual_cols-1)-c


def test_align_transform_flip_and_offset():
    grid = {"cols": 6, "rows": 6, "start_x": 1, "start_y": 1}
    fx = bonding_plan.make_align_transform(bonding_plan.normalize_align({"flip": "x"}), grid)
    assert fx(1, 3) == (6, 3)
    fy = bonding_plan.make_align_transform(bonding_plan.normalize_align({"flip": "y"}), grid)
    assert fy(3, 1) == (3, 6)
    off = bonding_plan.make_align_transform(
        bonding_plan.normalize_align({"rotation": 180, "offset": {"x": 1, "y": 0}}), grid)
    assert off(6, 6) == (2, 1)


def test_align_transform_dims_mismatch_raises():
    """rot 90인데 자기 프레임 치수가 스왑 관계가 아니면 명시 실패(ValueError)."""
    align = bonding_plan.normalize_align({"rotation": 90})
    with pytest.raises(ValueError):
        bonding_plan.make_align_transform(
            align, {"cols": 3, "rows": 4}, {"cols": 3, "rows": 4})


# ---------------------------------------------------------------------------
# 5. region 파서/클램프 단위 검증
# ---------------------------------------------------------------------------

def test_parse_region_normalizes_and_limits():
    rects = bonding_plan.parse_region(json.dumps({"rects": [{"x1": 5, "y1": 6, "x2": 2, "y2": 3}]}))
    assert rects == [(2, 3, 5, 6)]  # 좌표 정규화 (x1<=x2, y1<=y2)

    with pytest.raises(ValueError):
        bonding_plan.parse_region(json.dumps({"rects": [
            {"x1": 0, "y1": 0, "x2": 1, "y2": 1}] * (bonding_plan.MAX_REGION_RECTS + 1)}))


def test_clamp_rects_respects_grid_and_drops_empty():
    grid = {"cols": 6, "rows": 6, "start_x": 1, "start_y": 1}
    assert bonding_plan.clamp_rects([(-5, 0, 99, 99)], grid) == [(1, 1, 6, 6)]
    assert bonding_plan.clamp_rects([(10, 10, 20, 20)], grid) == []  # 완전 범위 밖 → 제거
    assert bonding_plan.clamp_rects([(2, 2, 3, 3)], None) == [(2, 2, 3, 3)]  # 메타 없으면 원본
