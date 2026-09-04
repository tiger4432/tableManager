"""본딩 실험계획 M1 — 역할 바인딩 config + 집계 API 검증 (Server_bonding_plan_m1_task §C 계약).

검증 범위:
- 집계 정확성(모의 데이터): total/defect/eds_fail/used(distinct)/remaining
- region 교차: canonical 좌표 rect 합집합 + align(180) 사상 — 변환 없이 겹치면 틀리는
  네거티브 케이스 포함(얼라인 실증), 격자 규격 클램프, 형식 위반 400
- align: **메타 델타에서 유도**(config 선언 레이어 없음). 회전 90/270·비등방 칩 피치·
  back 면·bbox≠0(웨이퍼 원에 잘리는 격자)을 결함 축으로 활성화한 replica 픽스처 포함.
  phys 규격 미등록 시 명시 실패(align_unavailable — QA 감사 F2 취지)
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


def _bdp_config():
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


def test_a_nan_coordinate_is_skipped_instead_of_taking_the_screen_down(
        bdp_env, client, monkeypatch):
    """🔴 `if px is not None` DOES NOT SKIP A NaN. A coordinate column is
    `double precision`, so its missing marker on the ORM path is None - and a NaN walks
    through that guard into `int()`, which raises `cannot convert float NaN to integer`.
    One bad row then 500s the whole count screen.

    The NaN is injected at `_fetch_points` rather than seeded into the table on purpose:
    `crud.cast_value_by_type` REFUSES nan/inf into a numeric column, so the ordinary
    write path cannot produce this row. What can is a writer that did not go through it,
    which this repository knows it has - seed scripts write table rows directly.

    Both call sites are covered here because the route walks both: the `used` count reads
    distinct points, and the region count walks them again.
    """
    _seed_core(bdp_env)
    real_fetch = bonding_plan._fetch_points

    def with_a_bad_point(db, cols, filters, distinct_pairs=False):
        return list(real_fetch(db, cols, filters, distinct_pairs)) + [
            (float("nan"), 2.0), (3.0, float("inf"))]

    monkeypatch.setattr(bonding_plan, "_fetch_points", with_a_bad_point)

    res = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTX", "slot": "01",
        "region": _region([{"x1": 1, "y1": 1, "x2": 2, "y2": 2}]),
    })
    assert res.status_code == 200, res.text
    body = res.json()
    # ⚠️ COUNTS, not merely "it did not raise": a guard that threw everything away
    # would also avoid the exception, and would be a different silent defect.
    assert body["chips"]["used"] == 2
    # 🔴 BOTH SHAPES, because they are two different call sites. `used` is the
    # comprehension; the other region counts come from the loop, and a NaN reaching that
    # one raises inside its `try` - which turns a real count into a zero WITHOUT any
    # error reaching the response. The unchanged numbers are the whole assertion.
    assert body["region_chips"]["used"] == 1
    assert body["region_chips"]["total"] == 4
    assert body["region_chips"]["defect"] == 1
    assert body["region_chips"]["eds_fail"] == 1
    assert body["sources"]["used_chips"] == "connected"


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


def test_region_align_negative_control(bdp_env, client):
    """EDS 메타를 코어와 **같은 회전(0)** 으로 등록하면 정렬이 identity가 되어 0이 나온다.

    (변환 없이 겹치면 틀리는 대조군 — 180 유도가 실제로 일하고 있음을 증명한다.
    종전에는 config에서 `align` 선언을 뺐지만, 선언 레이어가 사라졌으므로 이제 대조군은
    **메타를 다르게 등록하는 것**이다.)
    """
    db = bdp_env
    _seed_core(db)
    # 메타를 rot 0으로 덮어쓴다 — 같은 (target_table, map_id)의 두 번째 행이 아니라 갱신이어야
    # 하므로 기존 행을 지우고 다시 넣는다.
    model = models.DYNAMIC_TABLES["bdp_test_map_meta"]
    db.query(model).filter(model.target_table == "bdp_test_eds_fail_map").delete()
    _add_meta(db, "bdp_test_eds_fail_map", "LOTX_01", rotation=0)
    db.commit()

    body = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTX", "slot": "01",
        "region": _region([{"x1": 1, "y1": 1, "x2": 2, "y2": 2}]),
    }).json()
    # 저장좌표 (6,6)/(2,5)는 rect(1..2)에 없다 — 무보정이면 0
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


def test_region_without_any_meta_falls_back_to_identity(bdp_env, client):
    """메타가 **아예 없으면** identity로 붙는다 — 실패가 아니라 등록 누락의 신호다.

    map_overlay.resolve_align의 규율 그대로다(선언 부재를 실패로 만들면 대부분의 맵이
    못 붙는다). 정렬 실패는 "근거가 없다"가 아니라 "근거는 있는데 계산이 불가능하다"일
    때만 낸다 — 아래 phys 미등록 케이스가 그것이다.
    """
    db = bdp_env
    _add(db, "bdp_test_eds_fail_map", chip_key="LOTN_01_6_6",
         lot="LOTN", slot="01", x=6, y=6, val="F", metro_eqp="METRO-A")
    db.commit()
    body = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTN", "slot": "01",
        "region": _region([{"x1": 1, "y1": 1, "x2": 6, "y2": 6}]),
    }).json()
    assert body["sources"]["eds_fail"] == "connected"
    assert body["region_chips"]["eds_fail"] == 1   # 저장좌표 (6,6) 그대로 rect 안
    assert body["chips"]["eds_fail"] == 1


def test_align_unavailable_when_phys_spec_missing(bdp_env, client):
    """메타는 있는데 phys 규격이 없으면 → 바운딩박스를 못 만든다 → 명시 실패(QA F2 취지).

    조용히 raw 좌표로 계산하면 전 셀이 어긋난 수치가 정상처럼 나간다.
    """
    db = bdp_env
    _seed_core(db)
    model = models.DYNAMIC_TABLES["bdp_test_map_meta"]
    db.query(model).filter(model.target_table == "bdp_test_eds_fail_map").delete()
    bare = {k: v for k, v in dict(GRID, rotation=180).items() if not k.startswith("phys_")}
    _add(db, "bdp_test_map_meta", map_pk="bdp_test_eds_fail_map_bare",
         target_table="bdp_test_eds_fail_map", map_id="LOTX_01",
         grid_metadata=json.dumps(bare))
    db.commit()

    body = client.get("/api/bonding-plan/core-summary", params={
        "lot": "LOTX", "slot": "01",
        "region": _region([{"x1": 1, "y1": 1, "x2": 6, "y2": 6}]),
    }).json()
    assert body["sources"]["eds_fail"] == "connected(align_unavailable)"
    assert body["region_chips"]["eds_fail"] == 0
    assert body["chips"]["eds_fail"] == 2   # 전체 카운트는 변환 불변이라 유효


# ---------------------------------------------------------------------------
# 3. 역할 missing 부분 가동 / 미존재 조합
# ---------------------------------------------------------------------------

def test_missing_role_partial_operation(bdp_env, client, tmp_path, monkeypatch):
    """[relaxation 2026-08-04] Both sides of the absence/breakage boundary at once:
    an ABSENT declaration is a declared non-use (`not_declared`, subtraction
    inactive and NAMED), a PRESENT-but-broken one stays `missing`. The counts
    are identical either way (both contribute 0) — only the honesty differs."""
    _seed_core(bdp_env)
    cfg = _bdp_config()
    del cfg["sources"]["defect"]                                      # 부재 → not_declared
    cfg["sources"]["used_chips"]["table"] = "bdp_test_no_such_table"  # 파손 → missing
    cfg_path = tmp_path / "partial.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(cfg_path))

    res = client.get("/api/bonding-plan/core-summary", params={"lot": "LOTX", "slot": "01"})
    assert res.status_code == 200  # 에러 아님 — 부분 가동
    body = res.json()
    assert body["sources"]["defect"] == "not_declared"
    assert body["sources"]["used_chips"] == "missing"
    assert body["chips"]["defect"] == 0 and body["chips"]["used"] == 0
    assert body["chips"]["remaining"] == 36 - 0 - 2 - 0  # 미참여 역할은 0으로 계산
    # 감산에서 빠진 종류는 이름으로 말한다 — 파손(used_chips)은 부재가 아니므로 없다
    assert body["inactive_subtractions"] == ["defect"]


def test_empty_config_all_missing(bdp_env, client, tmp_path, monkeypatch):
    """빈 config: 분모(total_chips)만 missing으로 남고 보조 역할은 전부 not_declared."""
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(tmp_path / "does_not_exist.json"))
    res = client.get("/api/bonding-plan/core-summary", params={"lot": "L", "slot": "1"})
    assert res.status_code == 200
    body = res.json()
    assert set(body["sources"]) == set(bonding_plan.ROLES)
    assert body["sources"]["total_chips"] == "missing"   # 분모는 계속 필수
    for role in ("process_history", "defect", "eds_fail", "used_chips"):
        assert body["sources"][role] == "not_declared"
    assert body["chips"]["remaining"] == 0
    assert body["inactive_subtractions"] == ["defect", "eds_fail", "used_chips"]


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
# 4. 정렬 — 메타 델타 유도 경로를 **결함 축이 살아 있는 격자로** 검증
#
# [왜 GRID(6x6, chip 7x7, dia 300)로는 부족한가] 그 규격은 웨이퍼 원이 격자를 전혀 자르지
# 않아 bbox=(0,·,0,·)다. 저장 좌표가 bbox 상대값이라는 규약이 **원리적으로 발현할 수 없는**
# 구간이라, bbox 항을 통째로 빠뜨린 구현도 통과한다(삭제된 `make_align_transform`이 정확히
# 그랬고, 그래서 그 사본은 자기 테스트를 전부 통과한 채 틀려 있었다).
# 또 chip_x == chip_y라 회전 90/270의 피치 스왑도 죽는다.
#
# CROP_GRID는 네 축을 **동시에** 살린다:
#   · 비등방 피치 (chip 11 x 13)   · 비정방 격자 (11 x 9 → 회전 시 9 x 11)
#   · bbox != 0 이며 **minC != minR** — rot0/front에서 (1, 8, 2, 7). 두 값이 같으면
#     x/y 축을 혼동한 구현이 그대로 통과한다.
#   · back 면에서 bbox가 실제로 옮겨간다 — rot0/back은 (2, 9, 2, 7)이다. 즉
#     `phys_offset_x` 부호 반전 항이 **관측 가능**하다(off_x=4가 반 피치에 못 미치면
#     bbox가 안 움직여 그 항이 죽는다).
# ---------------------------------------------------------------------------

CROP_GRID = {"grid_cols": 11, "grid_rows": 9, "grid_start_x": 1, "grid_start_y": 1,
             "grid_y_invert": False, "side": "front",
             "phys_wafer_dia": 100, "phys_chip_x": 11, "phys_chip_y": 13,
             "phys_offset_x": 4, "phys_offset_y": 2, "phys_edge_margin": 3}


def _crop_meta(rotation=0, side="front"):
    return dict(CROP_GRID, rotation=rotation, side=side)


def _seed_crop(db, lot, eds_rotation, eds_side="front"):
    """코어(rot 0/front) + EDS(회전·면 지정) — 같은 물리 다이를 각자의 프레임에 기록한다.

    ⚠️ **픽스처는 검증 대상으로 만들지 않는다.** 좌표 대응을 `make_frame_transform`으로
    만들면 시드와 복원이 같은 함수라 서로 상쇄해, bbox 항을 통째로 빼도 테스트가 전부
    통과한다(실측: bbox_less 주입에서 이 파일 20건이 전건 통과했다). 그래서 저장 좌표는
    `test_map_overlay`의 **독립 정답지**(클라 저장 규약을 산술 그대로 옮긴 것, 검증 대상과
    어떤 계층도 공유하지 않음)로 만든다.
    """
    from test_map_overlay import oracle_overlay, oracle_stored_cells

    core_meta = _crop_meta(0, "front")
    eds_meta = _crop_meta(eds_rotation, eds_side)

    core_cells = sorted(oracle_stored_cells(core_meta))
    assert len(core_cells) >= 20, core_cells
    fail_canon = set(core_cells[5:9])          # canonical 기준 fail 4개

    for (x, y) in core_cells:
        _add(db, "bdp_test_core_defect_map", chip_key=f"{lot}_01_{x}_{y}",
             lot=lot, slot="01", x=x, y=y, val="P")
    _add(db, "bdp_test_map_meta", map_pk=f"core|{lot}",
         target_table="bdp_test_core_defect_map", map_id=f"{lot}_01",
         grid_metadata=json.dumps(core_meta))

    for (x, y) in core_cells:
        ex, ey = oracle_overlay(core_meta, eds_meta, x, y)
        _add(db, "bdp_test_eds_fail_map", chip_key=f"{lot}_01_{ex}_{ey}",
             lot=lot, slot="01", x=ex, y=ey,
             val=("F" if (x, y) in fail_canon else "P"), metro_eqp="METRO-A")
    _add(db, "bdp_test_map_meta", map_pk=f"eds|{lot}",
         target_table="bdp_test_eds_fail_map", map_id=f"{lot}_01",
         grid_metadata=json.dumps(eds_meta))
    db.commit()
    return core_cells, sorted(fail_canon)


@pytest.mark.parametrize("eds_rotation,eds_side", [
    (0, "back"),      # 면 반전만 — 거울이라 bbox 항이 상쇄되지 않고 2·minC로 쌓인다
    (90, "front"),    # 피치 스왑 축
    (180, "front"),   # 라이브 EDS와 같은 축
    (270, "back"),    # 회전 × 면 조합
])
def test_region_align_recovers_exact_dies_on_cropped_anisotropic_grid(
        bdp_env, client, tmp_path, monkeypatch, eds_rotation, eds_side):
    """정렬이 옳으면 **정확히 그 다이들**이 region에 잡힌다 — 개수만 보지 않는다.

    개수는 균일 오프셋 오류에도 보존될 수 있다(어긋난 위치가 우연히 다른 유효 다이에
    떨어지면 총 개수가 같다). 그래서 fail 다이 하나만 덮는 1x1 rect로 **동일성**을 본다.
    """
    from test_map_overlay import oracle_bbox

    db = bdp_env
    cfg_path = tmp_path / "crop.json"
    cfg_path.write_text(json.dumps(_bdp_config()), encoding="utf-8")
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(cfg_path))

    lot = f"CROP{eds_rotation}{eds_side[0].upper()}"
    _core_cells, fail_canon = _seed_crop(db, lot, eds_rotation, eds_side)

    # 픽스처가 결함 축을 실제로 켰는지 테스트 자신이 단언한다 (정답지 산술로 확인)
    core_meta, eds_meta = _crop_meta(0, "front"), _crop_meta(eds_rotation, eds_side)
    core_bbox, eds_bbox = oracle_bbox(core_meta), oracle_bbox(eds_meta)
    assert core_bbox[0] > 0 and core_bbox[2] > 0, f"bbox가 0이면 결함 축이 죽는다: {core_bbox}"
    assert core_meta["phys_chip_x"] != core_meta["phys_chip_y"], "비등방 피치가 아니다"
    assert core_bbox[0] != core_bbox[2], f"minC == minR이면 축 혼동을 못 잡는다: {core_bbox}"
    assert eds_bbox != (0, 0, 0, 0)
    # back 면에서 offset 부호 항이 실제로 bbox를 옮기는지 — 안 움직이면 그 축이 죽어 있다
    assert oracle_bbox(_crop_meta(0, "back")) != core_bbox

    for (fx, fy) in fail_canon:
        body = client.get("/api/bonding-plan/core-summary", params={
            "lot": lot, "slot": "01",
            "region": _region([{"x1": fx, "y1": fy, "x2": fx, "y2": fy}]),
        }).json()
        assert body["region_chips"]["eds_fail"] == 1, (
            f"canonical fail 다이 ({fx},{fy})가 자기 자리로 돌아오지 않았다 "
            f"(rot={eds_rotation} side={eds_side})")

    # fail이 아닌 다이 자리에는 잡히지 않아야 한다 (전 셀 균일 이동의 대조군)
    non_fail = next(c for c in _core_cells if c not in set(fail_canon))
    body = client.get("/api/bonding-plan/core-summary", params={
        "lot": lot, "slot": "01",
        "region": _region([{"x1": non_fail[0], "y1": non_fail[1],
                            "x2": non_fail[0], "y2": non_fail[1]}]),
    }).json()
    assert body["region_chips"]["eds_fail"] == 0
    assert body["region_chips"]["total"] == 1


def test_deleted_transform_copy_is_gone():
    """구 사본이 되살아나면(재도입/되돌림) 즉시 실패한다 — 구현은 하나뿐이어야 한다."""
    for name in ("normalize_align", "make_align_transform", "align_status_label",
                 "VALID_ROTATIONS", "VALID_FLIPS"):
        assert not hasattr(bonding_plan, name), f"bonding_plan.{name}이 되살아났다"


def test_align_marker_is_derived_from_meta_not_config(bdp_env, client):
    """상태 마커(aligned:180)는 config 선언이 아니라 메타 델타에서 나온다."""
    _seed_core(bdp_env)   # eds 메타 rot 180, config에는 align 키가 없다
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "LOTX", "slot": "01"}).json()
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"
    assert "align" not in json.dumps(_bdp_config()["sources"]["eds_fail"])


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


# ---------------------------------------------------------------------------
# 6. declared-but-unresolved columns must not vanish silently (FIX 2026-07-28)
# ---------------------------------------------------------------------------

def _cfg_to(tmp_path, monkeypatch, cfg, name):
    cfg_path = tmp_path / name
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(cfg_path))


def test_declared_typo_coordinate_column_demotes_not_silent(bdp_env, client, tmp_path,
                                                            monkeypatch):
    """used_chips "x": "cxx" (config typo) -> demoted status, count kept (row count)."""
    _seed_core(bdp_env)
    cfg = _bdp_config()
    cfg["sources"]["used_chips"]["columns"]["x"] = "cxx"   # no such model column
    _cfg_to(tmp_path, monkeypatch, cfg, "typo_x.json")
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "LOTX", "slot": "01"}).json()
    assert body["sources"]["used_chips"] == "connected(column_unresolved:x)"
    # Coordinate dedup is lost -> row count (3 rows, distinct would be 2). The count
    # is still served; the demoted status is what says "do not trust the refinement".
    assert body["chips"]["used"] == 3


def test_declared_typo_val_column_zeroes_the_fail_count(bdp_env, client, tmp_path,
                                                        monkeypatch):
    """defect "val": "vall" with fail_values declared -> counting without the filter
    would report EVERY chip (36) as fail. Must serve 0 + demoted status instead."""
    _seed_core(bdp_env)
    cfg = _bdp_config()
    cfg["sources"]["defect"]["columns"]["val"] = "vall"
    _cfg_to(tmp_path, monkeypatch, cfg, "typo_val.json")
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "LOTX", "slot": "01"}).json()
    assert body["sources"]["defect"] == "connected(column_unresolved:val)"
    assert body["chips"]["defect"] == 0          # never 36 (unfiltered count)
    # remaining follows the M1 missing-role convention (degraded term counts as 0)
    assert body["chips"]["remaining"] == 36 - 0 - 2 - 2


def test_omitted_optional_columns_stay_connected(bdp_env, client, tmp_path, monkeypatch):
    """Absence of a declaration is NOT a typo — used_chips without x/y at all keeps
    the row-count semantic and the plain connected status (regression guard)."""
    _seed_core(bdp_env)
    cfg = _bdp_config()
    del cfg["sources"]["used_chips"]["columns"]["x"]
    del cfg["sources"]["used_chips"]["columns"]["y"]
    _cfg_to(tmp_path, monkeypatch, cfg, "omitted.json")
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "LOTX", "slot": "01"}).json()
    assert body["sources"]["used_chips"] == "connected"
    assert body["chips"]["used"] == 3            # row count (no dedup without coords)


def test_declared_typo_history_column_demotes_but_rows_survive(bdp_env, client, tmp_path,
                                                               monkeypatch):
    """process_history "time": typo -> ordering refinement lost; rows still served,
    status carries the marker."""
    _seed_core(bdp_env)
    cfg = _bdp_config()
    cfg["sources"]["process_history"]["columns"]["time"] = "start_timee"
    _cfg_to(tmp_path, monkeypatch, cfg, "typo_hist.json")
    body = client.get("/api/bonding-plan/core-summary",
                      params={"lot": "LOTX", "slot": "01"}).json()
    assert body["sources"]["process_history"] == "connected(column_unresolved:time)"
    assert len(body["history"]) == 3
