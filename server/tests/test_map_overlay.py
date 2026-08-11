"""범용 맵 오버레이(S1') + 페인트 잠금 선언(S2) 검증.

핵심 계약:
- 임의의 맵을 임의의 맵 위에 겹칠 수 있다(계획 전용 아님, 테이블명 하드코딩 없음).
- 정렬은 각 맵의 wafer_map_metadata(rotation/side) 차이에서 **자동 유도**된다.
- align 선언/유도 근거 부재는 **실패가 아니라 identity**다. 변환을 계산할 근거가 없을 때만
  align_unavailable(총괄 확정 규율).
- 셀 목록 API이므로 상한 필수 + 초과 시 명시 표기(조용한 절단 금지).

[격리] 테이블명은 사용자 config에 실존 불가능한 mov_test_* 접두를 사용한다.
"""
import json
import uuid

import pytest

import map_overlay
from database import crud, models

MOV_TABLES = {
    "mov_test_base_map": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                         "x": "number", "y": "number", "val": "string"},
    },
    "mov_test_eds_map": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                         "x": "number", "y": "number", "val": "string"},
    },
    "mov_test_defect_map": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                         "x": "number", "y": "number", "val": "string"},
    },
    "mov_test_odd_map": {   # 좌표 컬럼명이 다른 맵 (바인딩 선언 경로 검증)
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "tape_lot": "string", "tape_slot": "string",
                         "tx": "number", "ty": "number", "core_lot": "string"},
    },
    # 바인딩 **자동 유도** 검증용: map_key_columns 선언 + 값 컬럼이 'val'이 아님(leg)
    "mov_test_derived_map": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "base": "string",
                         "x": "number", "y": "number", "leg": "string"},
        "map_key_columns": ["base"],
    },
    # value_column_candidates 검증용: 후보 컬럼이 **둘**(val·leg) 있어 탐지 순서가 결과를 가른다
    "mov_test_dual_map": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "base": "string",
                         "x": "number", "y": "number", "val": "string", "leg": "string"},
        "map_key_columns": ["base"],
    },
    # 맵으로 해석 불가(좌표 컬럼 없음) — 명시 실패 검증용
    "mov_test_notamap": {
        "business_key": "row_key",
        "column_types": {"row_key": "string", "memo": "string"},
    },
    # [F2] 값 컬럼이 후보 밖(UPPERCASE) — 유도는 거부, 서빙 바인딩만 fallback_guess 표기
    "mov_test_upper_map": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                         "x": "number", "y": "number", "VAL": "string"},
    },
    # [F2] 추측할 데이터 컬럼조차 없음 — binding null 검증용
    "mov_test_bare_map": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                         "x": "number", "y": "number"},
    },
}

# phys 규격은 **필수**다 — 셀 좌표가 웨이퍼 원으로 자른 바운딩박스 상대값이라
# (클라 저장 규약) 이것 없이는 정렬을 보증할 수 없다(QA B1).
# 300mm/7mm 조합은 6x6 격자가 원 안에 통째로 들어가 bbox 크롭이 없는 기준 케이스다.
PHYS_STD = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
            "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}
# 칩을 크게 잡아 원이 격자를 실제로 자르는 케이스 (bbox minC/minR > 0)
PHYS_CROP = dict(PHYS_STD, phys_chip_x=60.0, phys_chip_y=60.0)
# ⚠️ 위 두 픽스처는 **chip_x == chip_y**라 회전 시 피치 스왑의 유무가 결과에 영향을 주지
# 않는다 — 결함 축이 죽어 있다(QA A1이 지적한 바로 그 구멍).
# 아래는 **이방성(chip_x ≠ chip_y)** + 원 크롭으로 스왑 축을 살린 픽스처다.
PHYS_ANISO = dict(PHYS_STD, phys_chip_x=40.0, phys_chip_y=70.0)
# 오프셋 부호 항까지 살리는 픽스처 (back에서 x 부호가 뒤집힌다)
PHYS_ANISO_OFF = dict(PHYS_ANISO, phys_offset_x=18.0, phys_offset_y=-11.0)

GRID6 = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
         "side": "front", "rotation": 0, **PHYS_STD}


def _add(db, table, **cols):
    model = models.DYNAMIC_TABLES[table]
    bk = MOV_TABLES[table]["business_key"]
    db.add(model(row_id=str(uuid.uuid4()),
                 business_key_val=str(cols.get(bk) or uuid.uuid4()), **cols))


def _meta(db, target_table, map_id, rotation=0, side="front", cols=6, rows=6,
          y_invert=False, start_x=1, start_y=1, phys=None):
    meta = dict(GRID6)
    meta.update(phys or {})
    meta["rotation"] = rotation
    meta["side"] = side
    meta["grid_cols"] = cols
    meta["grid_rows"] = rows
    meta["grid_y_invert"] = y_invert
    meta["grid_start_x"] = start_x
    meta["grid_start_y"] = start_y
    model = models.DYNAMIC_TABLES["wafer_map_metadata"]
    db.add(model(row_id=str(uuid.uuid4()),
                 business_key_val=f"{target_table}_{map_id}",
                 map_pk=f"{target_table}_{map_id}", target_table=target_table,
                 map_id=map_id, grid_metadata=json.dumps(meta)))


META_CFG = {
    "wafer_map_metadata": {
        "business_key": "map_pk",
        "column_types": {"map_pk": "string", "target_table": "string",
                         "map_id": "string", "grid_metadata": "string"},
    },
}


@pytest.fixture()
def mov_env(db_session, tmp_path, monkeypatch):
    tables = dict(MOV_TABLES)
    tables.update(META_CFG)
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(tmp_path / "none.json"))
    return db_session


def _write_cfg(tmp_path, monkeypatch, cfg):
    p = tmp_path / f"mov_{uuid.uuid4().hex[:6]}.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(p))


def _seed(db):
    """타깃 base 맵(rot 0) + eds 맵(rot 180 — 자기 좌표계) + defect 맵(rot 0)."""
    _add(db, "mov_test_base_map", cell_key="B11", lot="L1", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "L1_01", rotation=0)

    # eds: canonical (1,1)·(5,2)를 180° 회전 저장 → (6,6)·(2,5)
    _add(db, "mov_test_eds_map", cell_key="E66", lot="L1", slot="01", x=6, y=6, val="F")
    _add(db, "mov_test_eds_map", cell_key="E25", lot="L1", slot="01", x=2, y=5, val="F")
    _meta(db, "mov_test_eds_map", "L1_01", rotation=180)

    # defect: 타깃과 동일 프레임
    _add(db, "mov_test_defect_map", cell_key="D33", lot="L1", slot="01", x=3, y=3, val="D")
    _meta(db, "mov_test_defect_map", "L1_01", rotation=0)
    db.commit()


# ---------------------------------------------------------------------------
# 1. 자동 유도 정렬 (핵심 요구: map meta가 달라도 붙는다)
# ---------------------------------------------------------------------------

def test_align_derived_from_map_metas(mov_env, client):
    _seed(mov_env)
    res = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_eds_map,mov_test_defect_map",
    })
    assert res.status_code == 200
    body = res.json()
    ov = {o["source_table"]: o for o in body["overlays"]}

    # eds: 메타 rotation 180 vs 타깃 0 → 상대 180이 자동 유도되어 canonical로 정렬
    eds = ov["mov_test_eds_map"]
    assert eds["status"] == "ok"
    assert eds["align_applied"]["rotation"] == 180
    assert eds["align_applied"]["origin"] == "derived"
    got = {(c["x"], c["y"]) for c in eds["cells"]}
    assert got == {(1, 1), (5, 2)}, "180° 정렬이 적용된 타깃 프레임 좌표여야 한다"
    assert all(c["val"] == "F" for c in eds["cells"])   # 원시 val 그대로

    # defect: 동일 프레임 → identity, 좌표 불변
    d = ov["mov_test_defect_map"]
    assert d["align_applied"]["rotation"] == 0
    assert d["align_applied"]["origin"] == "identity"
    assert [(c["x"], c["y"]) for c in d["cells"]] == [(3, 3)]


def test_align_absent_declaration_is_identity_not_failure(mov_env, client):
    """[총괄 확정] 선언 부재를 실패로 만들지 않는다 — 대부분의 맵이 못 붙게 된다."""
    db = mov_env
    _add(db, "mov_test_defect_map", cell_key="X", lot="L9", slot="01", x=2, y=2, val="D")
    db.commit()   # 메타 전혀 없음
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L9_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok", "메타 부재는 align_unavailable이 아니다"
    assert o["align_applied"]["origin"] == "identity"
    assert [(c["x"], c["y"]) for c in o["cells"]] == [(2, 2)]


ODD_BINDING = {"table_bindings": {"mov_test_odd_map": {"columns": {
    "x": "tx", "y": "ty", "val": "core_lot", "key_columns": ["tape_lot", "tape_slot"]}}}}


def test_align_unavailable_only_when_transform_incomputable(mov_env, client,
                                                            tmp_path, monkeypatch):
    """align_unavailable은 '각도를 모른다'가 아니라 '변환을 계산할 근거가 없다'일 때만."""
    db = mov_env
    _seed(db)
    # 소스 메타를 rot 90으로 두되 격자를 비정방 모순으로 만들어 계산 불가를 유도
    _add(db, "mov_test_odd_map", cell_key="O", tape_lot="L1", tape_slot="01",
         tx=1, ty=1, core_lot="C")
    _meta(db, "mov_test_odd_map", "L1_01", rotation=90, cols=4, rows=6)
    db.commit()
    _write_cfg(tmp_path, monkeypatch, ODD_BINDING)
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_odd_map",
    }).json()
    o = body["overlays"][0]
    # 타깃은 6x6, 소스 4x6을 90도 돌리면 6x4 → 타깃과 불일치 → 계산 불가 명시 실패
    assert o["status"] == "align_unavailable"
    assert o["cells"] == []          # 조용히 raw 좌표를 주지 않는다
    assert o["align_applied"]["rotation"] == 90


def test_flip_derived_from_side_difference(mov_env, client, tmp_path, monkeypatch):
    db = mov_env
    _seed(db)
    _add(db, "mov_test_odd_map", cell_key="OF", tape_lot="L1", tape_slot="01",
         tx=1, ty=3, core_lot="C")
    _meta(db, "mov_test_odd_map", "L1_01", rotation=0, side="back")
    db.commit()
    _write_cfg(tmp_path, monkeypatch, ODD_BINDING)
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_odd_map",
    }).json()
    o = body["overlays"][0]
    assert o["align_applied"]["flip"] == "x"
    assert o["align_applied"]["origin"] == "derived"
    assert [(c["x"], c["y"]) for c in o["cells"]] == [(6, 3)]   # x 반전


# ---------------------------------------------------------------------------
# 2. 선언 레이어(align_overrides)는 제거됐다 — 메타가 유일한 근거
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stale_override", [
    {"rotation": 0, "flip": "none"},                                    # 단순형
    {"default": {"rotation": 0}, "by_eqp": {"METRO-A": {"rotation": 90}}},  # 확장형
])
def test_stale_align_overrides_in_config_are_ignored(mov_env, client, tmp_path,
                                                     monkeypatch, stale_override):
    """사용자 config에 `align_overrides`가 남아 있어도 **무시**하고 메타로 유도한다.

    폐기 키는 조용히 무시하는 것이 정답이다 — 500으로 죽으면 config를 아직 안 지운
    사용자의 오버레이가 전부 멎고, 반대로 적용하면 정렬 근거가 둘로 갈라진다.
    소스 메타는 rot 180이므로 선언(rot 0)이 이겼다면 셀이 저장좌표 그대로 나온다.
    """
    _seed(mov_env)
    _write_cfg(tmp_path, monkeypatch, {"align_overrides": {"mov_test_eds_map": stale_override}})
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_eds_map", "eqp": "METRO-A",
    }).json()
    o = body["overlays"][0]
    assert o["align_applied"]["origin"] == "derived"      # declared/default는 더 이상 없다
    assert o["align_applied"]["rotation"] == 180          # 메타 델타
    assert {(c["x"], c["y"]) for c in o["cells"]} == {(1, 1), (5, 2)}


def test_declared_align_origins_are_gone_from_the_module(mov_env):
    """상수 자체가 사라졌는지 — 코드가 아직 declared/default를 만들 수 있으면 제거가 아니다."""
    assert not hasattr(map_overlay, "ALIGN_ORIGIN_DECLARED")
    assert not hasattr(map_overlay, "ALIGN_ORIGIN_DEFAULT")
    for src_rot, dst_rot in ((0, 0), (90, 0), (180, 0), (270, 90)):
        _a, origin, _n = map_overlay.resolve_align(_meta_of(rotation=src_rot),
                                                   _meta_of(rotation=dst_rot))
        assert origin in ("derived", "identity"), origin


# ---------------------------------------------------------------------------
# 3. 범용성 (임의 테이블/컬럼 바인딩) + 페이로드 상한
# ---------------------------------------------------------------------------

def test_custom_column_binding_arbitrary_table(mov_env, client, tmp_path, monkeypatch):
    """좌표·키 컬럼명이 관례와 달라도 config 바인딩으로 붙는다(테이블명 하드코딩 없음)."""
    db = mov_env
    _seed(db)
    _add(db, "mov_test_odd_map", cell_key="O1", tape_lot="L1", tape_slot="01",
         tx=2, ty=4, core_lot="CORE-9")
    db.commit()
    _write_cfg(tmp_path, monkeypatch, {
        "table_bindings": {"mov_test_odd_map": {"columns": {
            "x": "tx", "y": "ty", "val": "core_lot",
            "key_columns": ["tape_lot", "tape_slot"]}}},
    })
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_odd_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["cells"] == [{"x": 2, "y": 4, "val": "CORE-9"}]


def test_source_key_can_differ_from_target_key(mov_env, client):
    db = mov_env
    _seed(db)
    _add(db, "mov_test_defect_map", cell_key="DZ", lot="L2", slot="09", x=4, y=4, val="D")
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_defect_map:L2_09",
    }).json()
    o = body["overlays"][0]
    assert o["source_key"] == "L2_09"
    assert [(c["x"], c["y"]) for c in o["cells"]] == [(4, 4)]


def test_cell_cap_truncation_is_explicit(mov_env, client):
    db = mov_env
    _seed(db)
    for i in range(1, 7):
        _add(db, "mov_test_defect_map", cell_key=f"C{i}", lot="LB", slot="01",
             x=i, y=1, val="D")
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LB_01",
        "sources": "mov_test_defect_map", "limit": 3,
    }).json()
    o = body["overlays"][0]
    assert o["count"] == 3
    assert o["truncated"] is True and o["cap"] == 3   # 조용한 절단 금지


def test_missing_source_table_is_reported_not_crashed(mov_env, client):
    _seed(mov_env)
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_nope",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "source_missing"
    assert o["cells"] == []


def test_sources_required_and_capped(mov_env, client):
    assert client.get("/api/maps/overlay", params={
        "target_table": "t", "target_key": "k", "sources": "",
    }).status_code == 400
    too_many = ",".join(f"tbl{i}" for i in range(map_overlay.MAX_OVERLAY_SOURCES + 2))
    assert client.get("/api/maps/overlay", params={
        "target_table": "t", "target_key": "k", "sources": too_many,
    }).status_code == 400


# ---------------------------------------------------------------------------
# 3-bis. side × 타깃 회전 조합 — 프레임 합성 (구 QA B3 한계의 근본 수정)
#
# 배경: 예전에는 rel_rot + 단일 flip을 **하나의** 변환기로 합성했는데, back 반전 축이 프레임
# 자신의 회전에 따라 달라져(90/270이면 행, 아니면 열) 두 프레임의 반전 축을 표현할 수 없었다
# (전수 대조 64조합 중 16개가 status=ok인 채 거울상 오답 → 당시엔 명시 거절로 봉인).
# 현재는 각 맵을 자기 메타로 물리 좌표에 사상 후 타깃 프레임으로 역사상하므로 **정상 처리**된다.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target_rot", [90, 270])
@pytest.mark.parametrize("source_rot", [0, 90, 180, 270])
def test_side_mismatch_with_rotated_target_composes_correctly(
        mov_env, client, target_rot, source_rot):
    """면 반전 + 타깃 rot 90/270 — 거절하지 않고 **프레임 합성으로 올바르게** 그린다.

    검증은 구현을 되풀이하지 않고 **불변식 3종**으로 한다:
      ① 타깃 프레임 격자 범위 안에 든다(범위 밖 = 조용한 오답)
      ② 소스 프레임 전역이 타깃 프레임으로 **단사(중복 없음)** 사상된다
      ③ 역방향 사상과 왕복하면 원좌표로 돌아온다(거울상이면 깨진다)
    """
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="TB", lot="LR", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LR_01", rotation=target_rot, side="back")
    _add(db, "mov_test_defect_map", cell_key="SD", lot="LR", slot="01", x=1, y=1, val="D")
    _meta(db, "mov_test_defect_map", "LR_01", rotation=source_rot, side="front")
    db.commit()

    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LR_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok", o.get("detail")
    assert o["count"] == 1
    for c in o["cells"]:
        assert 1 <= c["x"] <= 6 and 1 <= c["y"] <= 6, f"타깃 격자 밖: {c}"   # ①

    src_meta = map_overlay.load_map_meta(db, "mov_test_defect_map", "LR_01")
    tgt_meta = map_overlay.load_map_meta(db, "mov_test_base_map", "LR_01")
    fwd = map_overlay.make_frame_transform(src_meta, tgt_meta)
    back = map_overlay.make_frame_transform(tgt_meta, src_meta)
    frame = [(x, y) for x in range(1, 7) for y in range(1, 7)]
    mapped = [fwd(x, y) for (x, y) in frame]
    assert len(set(mapped)) == len(frame), "두 셀이 같은 타깃 셀로 겹쳤다(사상이 단사가 아님)"  # ②
    assert all(back(*fwd(x, y)) == (x, y) for (x, y) in frame), "왕복이 항등이 아니다"        # ③


def test_frame_compose_golden_rot90_back_target(mov_env, client):
    """[손계산 골든] 소스 rot0/front (1,1) → 타깃 rot90/back 에서는 (6,6)이다.

    소스 (1,1)=0-based(0,0) → 물리 (0,0). 타깃(rot90·back) 역사상:
    c_m=(6-1)-yp=5, r_m=xp=0 → back·회전이므로 r=(6-1)-r_m=5 → (5,5) → 1-based (6,6).
    """
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="G1", lot="LG", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LG_01", rotation=90, side="back")
    _add(db, "mov_test_defect_map", cell_key="G2", lot="LG", slot="01", x=1, y=1, val="D")
    _meta(db, "mov_test_defect_map", "LG_01", rotation=0, side="front")
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LG_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["cells"] == [{"x": 6, "y": 6, "val": "D"}]


def test_same_map_id_in_two_tables_uses_each_own_spec(mov_env, client):
    """[회귀] 같은 map_id를 여러 테이블이 쓸 때 **각자 자기 규격**을 집는다.

    라이브 실데이터 재현: map_id 'AAA'가 base 맵(rot 0)과 defect 맵(rot 270)에 동시에 존재.
    메타 조회가 map_id만으로 매칭하면 남의 회전을 집어 좌표가 어긋난다.
    """
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="A1", lot="AAA", slot="", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "AAA", rotation=0, side="front")
    _add(db, "mov_test_defect_map", cell_key="A2", lot="AAA", slot="", x=1, y=1, val="D")
    _meta(db, "mov_test_defect_map", "AAA", rotation=270, side="front")
    db.commit()

    assert map_overlay.load_map_meta(db, "mov_test_base_map", "AAA")["rotation"] == 0
    assert map_overlay.load_map_meta(db, "mov_test_defect_map", "AAA")["rotation"] == 270

    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "AAA",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    # 소스 270 − 타깃 0 = 270이 유도돼야 한다 (남의 0°를 집었다면 identity가 된다)
    assert o["align_applied"]["rotation"] == 270
    assert o["align_applied"]["origin"] == "derived"
    assert o["status"] == "ok"


@pytest.mark.parametrize("target_rot", [0, 180])
def test_side_mismatch_with_unrotated_target_still_works(mov_env, client,
                                                         target_rot):
    """[대조군] 타깃이 0/180이면 면 반전만으로는 모호하지 않다 — 정상 처리(과잉 거절 방지)."""
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="TB2", lot="LS", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LS_01", rotation=target_rot, side="back")
    _add(db, "mov_test_defect_map", cell_key="SD2", lot="LS", slot="01", x=1, y=3, val="D")
    _meta(db, "mov_test_defect_map", "LS_01", rotation=target_rot, side="front")
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LS_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["align_applied"]["flip"] == "x"
    assert o["cells"] == [{"x": 6, "y": 3, "val": "D"}]


def test_same_side_rotated_target_is_not_refused(mov_env, client):
    """[대조군] side가 같으면 타깃이 90이어도 거절하지 않는다 — 가드가 과하지 않은지."""
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="TB3", lot="LT", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LT_01", rotation=90, side="front")
    _add(db, "mov_test_defect_map", cell_key="SD3", lot="LT", slot="01", x=1, y=1, val="D")
    _meta(db, "mov_test_defect_map", "LT_01", rotation=90, side="front")
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LT_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["align_applied"]["origin"] == "identity"   # 상대 회전 0, 반전 없음


def test_nonsquare_grid_rotation_is_handled_or_refused(mov_env, client, tmp_path,
                                                       monkeypatch):
    """[B3 후속 기준] 비정방 격자 + 회전 — 조용한 오답만 아니면 된다(ok든 거절이든).

    근본 수정 시 이 케이스가 올바른 좌표를 내도록 만드는 것이 목표다.
    """
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="NB", lot="LN", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LN_01", rotation=0, side="front", cols=6, rows=4)
    _add(db, "mov_test_odd_map", cell_key="NO", tape_lot="LN", tape_slot="01",
         tx=1, ty=1, core_lot="C")
    _meta(db, "mov_test_odd_map", "LN_01", rotation=90, side="front", cols=4, rows=6)
    db.commit()
    _write_cfg(tmp_path, monkeypatch, ODD_BINDING)
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LN_01",
        "sources": "mov_test_odd_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] in ("ok", "align_unavailable")
    if o["status"] == "ok":
        # 그렸다면 타깃 격자(6x4) 안에 들어와야 한다 — 범위 밖이면 조용한 오답이다
        for c in o["cells"]:
            assert 1 <= c["x"] <= 6 and 1 <= c["y"] <= 4, f"타깃 격자 밖: {c}"
    else:
        assert o["cells"] == []


# ---------------------------------------------------------------------------
# 3-quater. 나머지 두 좌표축 — grid_y_invert / grid_start_x·y (QA O3)
#
# 사용자 요구: "회전, 거울상, Y축 뒤집힘, START X,Y 모두 고려해서 오버레이 기준 좌표계에 올려".
# 회전·면은 프레임 합성으로 이미 처리되지만, y반전과 시작좌표는 **지름길(identity 판정)이
# 통째로 건너뛰던** 축이었다 — 전 셀이 균일하게 어긋나는데 status는 ok(조용한 오답).
# ---------------------------------------------------------------------------

def _meta_of(rotation=0, side="front", y_invert=False, start_x=1, start_y=1,
             cols=6, rows=6, phys=None):
    return {"grid_cols": cols, "grid_rows": rows, "rotation": rotation, "side": side,
            "grid_y_invert": y_invert, "grid_start_x": start_x, "grid_start_y": start_y,
            **(phys or PHYS_STD)}


def test_y_invert_alone_is_applied(mov_env, client):
    """[축 단독] y반전만 다른 두 맵 — 행이 뒤집혀 올라와야 한다.

    손계산: 소스 (1,2) → 셀 (0,1) → y반전 해제 r=(6-1)-1=4 → 물리 (0,4)
            → 타깃(반전 없음) 셀 (0,4) → 1-based (1,5)
    """
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="YT", lot="LY", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LY_01", y_invert=False)
    _add(db, "mov_test_defect_map", cell_key="YS", lot="LY", slot="01", x=1, y=2, val="D")
    _meta(db, "mov_test_defect_map", "LY_01", y_invert=True)
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LY_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["align_applied"]["origin"] == "derived", "지름길을 타면 identity가 된다"
    assert o["cells"] == [{"x": 1, "y": 5, "val": "D"}]
    assert "y반전" in (o["align_applied"].get("note") or "")


def test_start_offset_alone_is_applied(mov_env, client):
    """[축 단독] 시작좌표만 다른 두 맵 — 균일 평행이동이 보정돼야 한다.

    손계산: 소스 start(0,0)의 (2,3) → 셀 (2,3) → 물리 (2,3)
            → 타깃 start(1,1) 셀 (2,3) → (3,4)
    """
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="ST", lot="LS2", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LS2_01", start_x=1, start_y=1)
    _add(db, "mov_test_defect_map", cell_key="SS", lot="LS2", slot="01", x=2, y=3, val="D")
    _meta(db, "mov_test_defect_map", "LS2_01", start_x=0, start_y=0)
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LS2_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["align_applied"]["origin"] == "derived"
    assert o["cells"] == [{"x": 3, "y": 4, "val": "D"}]
    # 순수 평행이동이므로 offset을 실제 수치로 싣는다
    assert o["align_applied"]["offset"] == {"x": 1, "y": 1}
    assert "시작좌표" in (o["align_applied"].get("note") or "")


def test_identity_shortcut_requires_all_four_axes(mov_env):
    """[핵심 규율] 지름길은 **네 축이 전부 같을 때만**. 하나라도 다르면 derived다."""
    base = _meta_of()
    assert map_overlay.frame_axes(base) == map_overlay.frame_axes(_meta_of())
    for differing in (_meta_of(rotation=90), _meta_of(side="back"),
                      _meta_of(y_invert=True), _meta_of(start_x=0),
                      _meta_of(start_y=-12)):
        _align, origin, _note = map_overlay.resolve_align(differing, base)
        assert origin == "derived", f"축이 다른데 지름길을 탔다: {differing}"


# ---------------------------------------------------------------------------
# 독립 정답(oracle) — 클라 저장 규약을 **산술 그대로** 옮겨 쓴 것.
#
# [왜 필요한가 — QA B1의 뼈아픈 교훈] 이전 회귀는 단사·범위·**왕복 항등**만 봤다. 셋 다
# 같은 함수의 자기 대조라 **균일 오프셋에는 전부 참**이다(f가 통째로 +4 밀려 있어도
# 단사이고 왕복도 항등이다). 그래서 라이브 12쌍이 조용히 틀린 것을 못 잡았다.
# 정답은 반드시 **바깥에서** 와야 한다 — 아래는 map_overlay를 일절 호출하지 않는다.
# ---------------------------------------------------------------------------

def _oracle_frame_dims(m):
    rot = int(m.get("rotation", 0) or 0) % 360
    cols, rows = int(m["grid_cols"]), int(m["grid_rows"])
    return (rows, cols) if rot in (90, 270) else (cols, rows)


def _oracle_frame_phys(m):
    """물리 규격 → 프레임 축 규격. **클라 산술을 그대로 옮긴 것**(서버 코드 미참조).

    회전 90/270에서 칩 피치 스왑, back에서 offset x 부호 반전.
    """
    cx, cy = float(m["phys_chip_x"]), float(m["phys_chip_y"])
    ox, oy = float(m["phys_offset_x"]), float(m["phys_offset_y"])
    oox = -ox if str(m.get("side", "front") or "front") == "back" else ox
    rot = int(m.get("rotation", 0) or 0) % 360
    if rot == 90:
        return cy, cx, oy, -oox
    if rot == 180:
        return cx, cy, -oox, -oy
    if rot == 270:
        return cy, cx, -oy, oox
    return cx, cy, oox, oy


def _oracle_bbox(m):
    """웨이퍼 원 밖 셀을 제외한 바운딩박스 — **원 판정 산술을 직접 구현**한다.

    ⚠️ `PhysicalWaferEngine`을 쓰지 않는다. 이전 오라클은 검증 대상과 **같은 파라미터로
    같은 엔진**을 만들어서, 합성 계층에서만 독립이고 bbox 계층에서는 검증 대상의 복사본이었다
    — 결함이 정확히 그 계층에 있었으므로 원리적으로 통과했다(QA A1). 정답지는 검증 대상과
    **어떤 계층도 공유해선 안 된다.**
    """
    vc, vr = _oracle_frame_dims(m)
    chip_x, chip_y, off_x, off_y = _oracle_frame_phys(m)
    eff = max(0.0, float(m["phys_wafer_dia"]) / 2.0 - float(m["phys_edge_margin"]))
    rsq = eff * eff
    cc, cr = (vc - 1) / 2.0, (vr - 1) / 2.0
    hw, hh = chip_x / 2.0, chip_y / 2.0
    cs, rs = [], []
    for r in range(vr):
        for c in range(vc):
            x = (c - cc) * chip_x + off_x
            y = (cr - r) * chip_y + off_y
            if all((px * px + py * py) <= rsq
                   for px in (x - hw, x + hw) for py in (y - hh, y + hh)):
                cs.append(c)
                rs.append(r)
    if not cs:
        return 0, 0, 0, 0
    return min(cs), max(cs), min(rs), max(rs)


def _oracle_cell_to_stored(m, c, r):
    min_c, _max_c, min_r, max_r = _oracle_bbox(m)
    sx, sy = int(m.get("grid_start_x", 1)), int(m.get("grid_start_y", 1))
    xv = c - min_c + sx
    yv = (max_r - r + sy) if m.get("grid_y_invert") else (r - min_r + sy)
    return xv, yv


def _oracle_stored_to_cell(m, xv, yv):
    min_c, _max_c, min_r, max_r = _oracle_bbox(m)
    sx, sy = int(m.get("grid_start_x", 1)), int(m.get("grid_start_y", 1))
    c = xv - sx + min_c
    r = (max_r - (yv - sy)) if m.get("grid_y_invert") else (yv - sy + min_r)
    return c, r


def _oracle_cell_to_phys(m, c, r):
    rot = int(m.get("rotation", 0) or 0) % 360
    vc, vr = _oracle_frame_dims(m)
    cm, rm = c, r
    if str(m.get("side", "front") or "front") == "back":
        if rot in (90, 270):
            rm = (vr - 1) - r
        else:
            cm = (vc - 1) - c
    if rot == 0:
        return cm, rm
    if rot == 90:
        return rm, (vc - 1) - cm
    if rot == 180:
        return (vc - 1) - cm, (vr - 1) - rm
    return (vr - 1) - rm, cm


def _oracle_phys_to_cell(m, xp, yp):
    rot = int(m.get("rotation", 0) or 0) % 360
    vc, vr = _oracle_frame_dims(m)
    if rot == 0:
        cm, rm = xp, yp
    elif rot == 90:
        cm, rm = (vc - 1) - yp, xp
    elif rot == 180:
        cm, rm = (vc - 1) - xp, (vr - 1) - yp
    else:
        cm, rm = yp, (vr - 1) - xp
    c, r = cm, rm
    if str(m.get("side", "front") or "front") == "back":
        if rot in (90, 270):
            r = (vr - 1) - rm
        else:
            c = (vc - 1) - cm
    return c, r


def oracle_overlay(src_meta, dst_meta, x, y):
    """소스 저장좌표 → 타깃 저장좌표 (같은 물리 칩을 가리키도록). 정답지."""
    c, r = _oracle_stored_to_cell(src_meta, x, y)
    xp, yp = _oracle_cell_to_phys(src_meta, c, r)
    c2, r2 = _oracle_phys_to_cell(dst_meta, xp, yp)
    return _oracle_cell_to_stored(dst_meta, c2, r2)


def oracle_stored_cells(meta):
    """이 프레임의 **웨이퍼 안** 저장 좌표 전부 — 정답지 산술로만 만든다.

    다른 테스트 모듈이 픽스처를 만들 때 쓴다. 픽스처를 검증 대상 함수로 만들면 시드와
    복원이 서로 상쇄해, 균일 오프셋 결함이 통째로 보이지 않는다(자기 대조 함정).
    """
    vc, vr = _oracle_frame_dims(meta)
    chip_x, chip_y, off_x, off_y = _oracle_frame_phys(meta)
    eff = max(0.0, float(meta["phys_wafer_dia"]) / 2.0 - float(meta["phys_edge_margin"]))
    rsq = eff * eff
    cc, cr = (vc - 1) / 2.0, (vr - 1) / 2.0
    hw, hh = chip_x / 2.0, chip_y / 2.0
    out = []
    for r in range(vr):
        for c in range(vc):
            x = (c - cc) * chip_x + off_x
            y = (cr - r) * chip_y + off_y
            if all((px * px + py * py) <= rsq
                   for px in (x - hw, x + hw) for py in (y - hh, y + hh)):
                out.append(_oracle_cell_to_stored(meta, c, r))
    return out


def oracle_bbox(meta):
    """`_oracle_bbox` 공개 별칭 — 다른 모듈이 픽스처의 결함 축 활성화를 단언할 때 쓴다."""
    return _oracle_bbox(meta)


def _oracle_cells(m):
    """그 맵이 실제로 저장하는 좌표들(원 안 셀만)."""
    min_c, max_c, min_r, max_r = _oracle_bbox(m)
    return [_oracle_cell_to_stored(m, c, r)
            for c in range(min_c, max_c + 1)
            for r in range(min_r, max_r + 1)]


def test_transform_matches_independent_oracle_all_axis_combos(mov_env):
    """[전수 대조 — 독립 정답] 모든 축 조합에서 **오라클과 좌표가 일치**해야 한다.

    회전 4 × 면 2 × y반전 2 × 시작좌표 2 = 32 프레임, 쌍 1024개.
    자기 왕복이 아니라 바깥 정답과 맞춘다 — 균일 오프셋도 여기서는 즉시 잡힌다.
    """
    frames = [_meta_of(rotation=rot, side=side, y_invert=inv, start_x=sx, start_y=sy)
              for rot in (0, 90, 180, 270)
              for side in ("front", "back")
              for inv in (False, True)
              for (sx, sy) in ((1, 1), (0, -2))]
    assert len(frames) == 32

    bad = []
    for src in frames:
        cells = _oracle_cells(src)
        for dst in frames:
            fwd = map_overlay.make_frame_transform(src, dst)
            for (x, y) in cells:
                got = tuple(fwd(x, y))
                want = oracle_overlay(src, dst, x, y)
                if got != want:
                    bad.append((src, dst, (x, y), got, want))
                    break
    assert not bad, f"오라클 불일치 {len(bad)}쌍. 예: {bad[0]}"


def test_transform_matches_oracle_when_wafer_circle_crops_the_grid(mov_env):
    """[B1 직격] 웨이퍼 원이 격자를 **실제로 자를 때**(bbox minC/minR > 0) 대조.

    이 케이스가 없었기 때문에 바운딩박스 항 누락이 통과했다. 칩을 크게 잡아
    모서리 셀이 원 밖으로 나가도록 만든 뒤, 거울(면 반전)이 끼는 조합을 함께 본다.
    """
    assert _oracle_bbox(_meta_of(phys=PHYS_CROP))[0] > 0, "이 픽스처는 크롭이 있어야 의미가 있다"

    frames = [_meta_of(rotation=rot, side=side, phys=PHYS_CROP)
              for rot in (0, 90, 180, 270) for side in ("front", "back")]
    for src in frames:
        cells = _oracle_cells(src)
        for dst in frames:
            fwd = map_overlay.make_frame_transform(src, dst)
            for (x, y) in cells:
                assert tuple(fwd(x, y)) == oracle_overlay(src, dst, x, y), \
                    f"{src['rotation']}/{src['side']} -> {dst['rotation']}/{dst['side']} @{(x, y)}"


@pytest.mark.parametrize("phys_name", ["PHYS_ANISO", "PHYS_ANISO_OFF"])
def test_anisotropic_chip_pitch_swaps_on_rotated_frames(mov_env, phys_name):
    """[A1 직격] **이방성 칩 피치**(chip_x ≠ chip_y) × 회전 90/270 × front/back.

    회전 프레임에서는 프레임 x축이 물리 y축이므로 피치가 스왑돼야 한다. 스왑을 빠뜨리면
    bbox가 통째로 달라지고 전 셀이 어긋난다. `chip_x == chip_y` 픽스처로는 이 축이
    죽어 있어 영원히 안 잡힌다.
    """
    phys = {"PHYS_ANISO": PHYS_ANISO, "PHYS_ANISO_OFF": PHYS_ANISO_OFF}[phys_name]
    frames = [_meta_of(rotation=rot, side=side, phys=phys)
              for rot in (0, 90, 180, 270) for side in ("front", "back")]

    # 픽스처가 결함 축을 실제로 활성화하는지 먼저 확인한다(죽은 픽스처 방지).
    assert _oracle_bbox(_meta_of(rotation=0, phys=phys)) != \
        _oracle_bbox(_meta_of(rotation=90, phys=phys)), \
        "회전으로 bbox가 안 바뀌면 이 픽스처는 스왑 축을 검사하지 못한다"

    for src in frames:
        cells = _oracle_cells(src)
        assert cells, "빈 bbox면 아무것도 검사하지 못한다"
        for dst in frames:
            fwd = map_overlay.make_frame_transform(src, dst)
            for (x, y) in cells:
                assert tuple(fwd(x, y)) == oracle_overlay(src, dst, x, y), (
                    f"{src['rotation']}/{src['side']} -> {dst['rotation']}/{dst['side']} "
                    f"@{(x, y)}")


def test_nonsquare_grid_with_anisotropic_pitch(mov_env):
    """[A1 조합] 비정방 격자 + 이방성 피치 + 회전 — 치수와 피치가 함께 스왑되는지."""
    frames = [_meta_of(rotation=rot, side=side, cols=9, rows=5,
                       phys=dict(PHYS_ANISO, phys_chip_x=30.0, phys_chip_y=55.0))
              for rot in (0, 90, 180, 270) for side in ("front", "back")]
    for src in frames:
        cells = _oracle_cells(src)
        for dst in frames:
            if _oracle_frame_dims(src) != _oracle_frame_dims(dst):
                continue          # 프레임 치수가 다르면 겹칠 대상이 아니다
            fwd = map_overlay.make_frame_transform(src, dst)
            for (x, y) in cells:
                assert tuple(fwd(x, y)) == oracle_overlay(src, dst, x, y), \
                    f"{src['rotation']}/{src['side']} -> {dst['rotation']}/{dst['side']}"


def test_frame_phys_params_match_independent_derivation(mov_env):
    """[표 고정] 프레임 규격 변환표를 오라클(독립 이식)과 직접 대조한다."""
    for rot in (0, 90, 180, 270):
        for side in ("front", "back"):
            m = _meta_of(rotation=rot, side=side, phys=PHYS_ANISO_OFF)
            _dia, cx, cy, ox, oy, _mar = map_overlay._frame_phys_params(m)
            assert (cx, cy, ox, oy) == _oracle_frame_phys(m), f"rot{rot}/{side}"


def test_missing_phys_spec_fails_explicitly(mov_env, client):
    """[규율] phys 규격이 없으면 바운딩박스를 재현할 수 없다 → **명시 실패**(조용히 그리지 않는다)."""
    no_phys = {k: v for k, v in _meta_of(rotation=90).items() if not k.startswith("phys_")}
    with pytest.raises(ValueError, match="phys"):
        map_overlay.make_frame_transform(no_phys, _meta_of())

    db = mov_env
    _add(db, "mov_test_base_map", cell_key="NP1", lot="LP", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LP_01", rotation=0)
    _add(db, "mov_test_defect_map", cell_key="NP2", lot="LP", slot="01", x=1, y=1, val="D")
    model = models.DYNAMIC_TABLES["wafer_map_metadata"]
    db.add(model(row_id=str(uuid.uuid4()), business_key_val="mov_test_defect_map_LP_01",
                 map_pk="mov_test_defect_map_LP_01", target_table="mov_test_defect_map",
                 map_id="LP_01", grid_metadata=json.dumps(
                     {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
                      "rotation": 90, "side": "front"})))
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LP_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "align_unavailable"
    assert o["cells"] == []
    assert "phys" in (o["detail"] or "")


def test_identity_shortcut_blocked_by_grid_dim_mismatch(mov_env):
    """[M4] 치수가 다르면 지름길을 타면 안 된다 — 규격 검사를 우회하게 된다."""
    a = _meta_of(cols=6, rows=6)
    b = _meta_of(cols=8, rows=8)
    _align, origin, _note = map_overlay.resolve_align(a, b)
    assert origin == "derived", "치수 불일치가 identity로 통과했다"
    with pytest.raises(ValueError, match="dims differ"):
        map_overlay.make_frame_transform(a, b)


def test_identity_shortcut_blocked_by_phys_spec_mismatch(mov_env):
    """[M4] 웨이퍼 규격이 다르면 바운딩박스가 달라 무보정으로 붙이면 안 된다."""
    _align, origin, _note = map_overlay.resolve_align(
        _meta_of(phys=PHYS_CROP), _meta_of(phys=PHYS_STD))
    assert origin == "derived"


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_y_invert_combined_with_rotation(mov_env, rotation):
    """[조합] y반전 × 회전 — 반전 축이 회전 뒤 프레임 기준으로 잡혀야 한다."""
    src = _meta_of(rotation=rotation, y_invert=True)
    dst = _meta_of(rotation=rotation, y_invert=False)
    fwd = map_overlay.make_frame_transform(src, dst)
    # 같은 회전 + y반전만 차이 → 프레임 행 수 기준 순수 상하 반전이어야 한다
    frame_rows = 6   # 정방 격자라 회전과 무관
    for x in range(1, 7):
        for y in range(1, 7):
            assert fwd(x, y) == (x, (frame_rows + 1) - y), f"rot={rotation} ({x},{y})"


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_start_offset_combined_with_rotation(mov_env, rotation):
    """[조합] 시작좌표 × 회전 — 회전이 같으면 start 차이는 순수 평행이동으로 남는다."""
    src = _meta_of(rotation=rotation, start_x=0, start_y=0)
    dst = _meta_of(rotation=rotation, start_x=1, start_y=1)
    fwd = map_overlay.make_frame_transform(src, dst)
    for x in range(0, 6):
        for y in range(0, 6):
            assert fwd(x, y) == (x + 1, y + 1), f"rot={rotation} ({x},{y})"


def test_nonsquare_grid_y_invert_uses_rotated_row_count(mov_env):
    """[비정방] y반전 축 길이는 **회전 반영 후** 프레임 행 수다(물리 rows가 아니다).

    물리 6x4를 90° 돌리면 프레임은 4x6 — 반전은 6행 기준이어야 한다.
    """
    src = _meta_of(rotation=90, y_invert=True, cols=6, rows=4)
    dst = _meta_of(rotation=90, y_invert=False, cols=6, rows=4)
    fwd = map_overlay.make_frame_transform(src, dst)
    # 프레임: cols=4, rows=6 → y는 1..6, 반전이면 y -> 7-y
    for x in range(1, 5):
        for y in range(1, 7):
            assert fwd(x, y) == (x, 7 - y), f"({x},{y})"


def test_start_offset_survives_mirror_and_rotation_end_to_end(mov_env, client):
    """[전 축 동시] 회전 + 거울상 + y반전 + 시작좌표가 한꺼번에 달라도 격자 안에 든다."""
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="AT", lot="LA", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LA_01", rotation=270, side="back",
          y_invert=True, start_x=1, start_y=1)
    for i in range(1, 7):
        _add(db, "mov_test_defect_map", cell_key=f"AS{i}", lot="LA", slot="01",
             x=i - 3, y=i - 3, val="D")
    _meta(db, "mov_test_defect_map", "LA_01", rotation=90, side="front",
          y_invert=False, start_x=-2, start_y=-2)
    db.commit()
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LA_01",
        "sources": "mov_test_defect_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["count"] == 6
    got = {(c["x"], c["y"]) for c in o["cells"]}
    assert len(got) == 6, "겹쳐 떨어진 셀이 있다"
    for (x, y) in got:
        assert 1 <= x <= 6 and 1 <= y <= 6, f"타깃 격자 밖: {(x, y)}"


# ---------------------------------------------------------------------------
# 3-ter. 바인딩 자동 유도 — "선언된 맵만 겹칠 수 있다"는 구조를 깬다
# ---------------------------------------------------------------------------

def test_binding_derived_from_table_config_without_declaration(mov_env, client):
    """`map_overlay_config`에 **선언이 전혀 없어도** table_config에서 유도해 겹친다.

    라이브 사고: `test` 테이블이 table_bindings에 없어 "소스 맵을 찾을 수 없습니다"로
    실패했다. 맵의 좌표계는 이미 table_config가 선언하고 있으므로 거기서 유도한다.
    """
    db = mov_env
    _seed(db)
    _add(db, "mov_test_derived_map", cell_key="R1", base="BASE-7", x=3, y=5, leg="D2")
    db.commit()

    derived = map_overlay.derive_table_binding("mov_test_derived_map")
    assert derived == {"x": "x", "y": "y", "val": "leg", "key_columns": ["base"]}

    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_derived_map:BASE-7",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["cells"] == [{"x": 3, "y": 5, "val": "D2"}]


def test_declaration_still_overrides_derivation(mov_env, client, tmp_path, monkeypatch):
    """선언은 **예외 보정용**으로 남아 유도보다 우선한다(관례 밖 컬럼명 구제)."""
    db = mov_env
    _seed(db)
    _add(db, "mov_test_derived_map", cell_key="R2", base="BASE-8", x=2, y=2, leg="IGNORED")
    db.commit()
    _write_cfg(tmp_path, monkeypatch, {"table_bindings": {"mov_test_derived_map": {
        "columns": {"x": "x", "y": "y", "val": "cell_key", "key_columns": ["base"]}}}})
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_derived_map:BASE-8",
    }).json()
    assert body["overlays"][0]["cells"] == [{"x": 2, "y": 2, "val": "R2"}]


def test_underivable_table_fails_explicitly(mov_env, client):
    """유도 불가(좌표 컬럼 없음)는 **명시 실패** — 관례로 추측해 0건을 정상처럼 내지 않는다."""
    _seed(mov_env)
    assert map_overlay.derive_table_binding("mov_test_notamap") is None
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_notamap",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "source_missing"
    assert "map_key_columns" in (o["detail"] or "")


def test_fallback_guess_refused_in_data_path(mov_env, client):
    """[F2] 후보 밖 값 컬럼(UPPERCASE 등)은 데이터 경로에서 **조용히 추측하지 않는다**.

    과거: 후보가 안 맞으면 첫 데이터 컬럼을 잡아 그 컬럼 값으로 셀을 내보냈다 — 클라는
    엉뚱한 컬럼을 진짜인 양 렌더했다. 지금: 유도는 x/y 부재와 같은 명시 거부(None)이고
    오버레이는 source_missing으로 표면화한다. 추측은 paint-rules의 `binding` 필드에서만
    `fallback_guess`로 표기되어 나간다(별도 테스트)."""
    db = mov_env
    _seed(db)
    _add(db, "mov_test_upper_map", cell_key="U1", lot="L1", slot="01",
         x=2, y=2, VAL="DECOY")
    db.commit()

    assert map_overlay.derive_table_binding("mov_test_upper_map") is None
    assert map_overlay.resolve_binding({}, "mov_test_upper_map") is None

    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_upper_map",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "source_missing", "추측 렌더 대신 명시 거부여야 한다"
    assert o["cells"] == []
    assert "value_column_candidates" in (o["detail"] or "")

    # 선언으로 구제하면 그대로 동작한다 (거부는 추측에만 적용, 선언 경로 무손상)
    declared = {"table_bindings": {"mov_test_upper_map": {"columns": {
        "x": "x", "y": "y", "val": "VAL", "key_columns": ["lot", "slot"]}}}}
    assert map_overlay.resolve_binding(declared, "mov_test_upper_map")["val"] == "VAL"


# ---------------------------------------------------------------------------
# 4. 페인트 잠금 선언 (S2)
# ---------------------------------------------------------------------------

def test_paint_rules_default_is_unlocked(mov_env, client):
    """선언이 없으면 잠금 없음 — '' F면 못 칠한다''가 코드에 박히면 안 된다."""
    body = client.get("/api/maps/paint-rules", params={"table": "anything"}).json()
    assert body["rules"]["enabled"] is False
    assert body["rules"]["blocking_values"] == []


def test_paint_rules_merge_wildcard_and_table(mov_env, client, tmp_path, monkeypatch):
    _write_cfg(tmp_path, monkeypatch, {"paint_lock": {
        "*": {"enabled": False, "blocking_values": ["X"], "message": "기본"},
        "mov_test_base_map": {"enabled": True, "blocking_values": ["F", "D"],
                              "from_overlay": ["mov_test_eds_map"]},
    }})
    generic = client.get("/api/maps/paint-rules", params={"table": "other"}).json()["rules"]
    assert generic["enabled"] is False and generic["blocking_values"] == ["X"]

    specific = client.get("/api/maps/paint-rules",
                          params={"table": "mov_test_base_map"}).json()["rules"]
    assert specific["enabled"] is True
    assert specific["blocking_values"] == ["F", "D"]
    assert specific["from_overlay"] == ["mov_test_eds_map"]
    assert specific["message"] == "기본"     # 와일드카드 값 승계


# ---------------------------------------------------------------------------
# 5. default_legend / value_column_candidates (U6) — no client-side hardcoding:
#    the paint-rules response is the single source for both map defaults.
# ---------------------------------------------------------------------------

def test_resolve_candidates_precedence_unit():
    """Declared list wins; absent/empty/non-list declarations fall back to the default."""
    default = list(map_overlay.DEFAULT_VAL_CANDIDATES)
    assert map_overlay.resolve_value_column_candidates({}) == default
    assert map_overlay.resolve_value_column_candidates(
        {"value_column_candidates": ["grade", "val"]}) == ["grade", "val"]
    # Honest fallback: an unusable declaration must not half-apply
    assert map_overlay.resolve_value_column_candidates(
        {"value_column_candidates": []}) == default
    assert map_overlay.resolve_value_column_candidates(
        {"value_column_candidates": "val"}) == default
    assert map_overlay.resolve_value_column_candidates(
        {"value_column_candidates": [42, "  "]}) == default


def test_paint_rules_response_shape_and_resolved_defaults(mov_env, client):
    """Response always carries the RESOLVED candidates; default_legend is null when
    undeclared (honest absence — the server never invents legend rows)."""
    body = client.get("/api/maps/paint-rules", params={"table": "anything"}).json()
    assert set(body.keys()) == {"table", "rules", "binding", "default_legend",
                                "value_column_candidates"}
    assert body["value_column_candidates"] == list(map_overlay.DEFAULT_VAL_CANDIDATES)
    assert body["default_legend"] is None
    assert body["binding"] is None, "미지 테이블은 바인딩 해석 불가 — 정직한 null"
    assert set(body["rules"].keys()) == {"enabled", "blocking_values", "from_overlay", "message"}


def test_paint_rules_serves_declared_legend_and_candidates(mov_env, client,
                                                          tmp_path, monkeypatch):
    """Declared values are served verbatim (legend rows untouched, declared order kept)."""
    rows = [{"value": "1", "desc": "GOOD", "color": "#10b981", "locked": False},
            {"value": "0", "desc": "FAIL", "color": "#ef4444", "locked": True}]
    _write_cfg(tmp_path, monkeypatch, {"default_legend": rows,
                                       "value_column_candidates": ["leg", "grade"]})
    body = client.get("/api/maps/paint-rules").json()
    assert body["default_legend"] == rows
    assert body["value_column_candidates"] == ["leg", "grade"]


def test_paint_rules_serves_resolved_binding_declared_wins(mov_env, client,
                                                           tmp_path, monkeypatch):
    """[F1] paint-rules가 RESOLVED 바인딩을 서빙한다 — 선언 > 유도, 출처 표기.

    에디터가 자기 나름의 재유도(첫 데이터 컬럼 추측) 대신 이 필드 하나만 소비하게 하는
    단일 소스다 (U6 candidates와 같은 패턴)."""
    _seed(mov_env)

    # 유도 경로: table_config에서 유도 + source=derived
    body = client.get("/api/maps/paint-rules",
                      params={"table": "mov_test_derived_map"}).json()
    # `index`는 언제나 실려 나가고 유도는 그것을 만들지 않는다 — 순번 컬럼에는 이름 관례가
    # 없어서 유도할 근거가 없다. 없는 키와 None은 받는 쪽에서 같아 보이므로 키로 남긴다.
    assert body["binding"] == {"x": "x", "y": "y", "val": "leg", "index": None,
                               "key_columns": ["base"], "source": "derived"}

    # 선언 경로: 관례 밖 이름(tx/ty)의 선언이 유도를 이긴다 + source=declared
    _write_cfg(tmp_path, monkeypatch, ODD_BINDING)
    body = client.get("/api/maps/paint-rules",
                      params={"table": "mov_test_odd_map"}).json()
    assert body["binding"] == {"x": "tx", "y": "ty", "val": "core_lot",
                               "index": None,
                               "key_columns": ["tape_lot", "tape_slot"],
                               "source": "declared"}

    # 해석 불가(좌표 컬럼 없음) → null · table 파라미터 부재 → null
    assert client.get("/api/maps/paint-rules",
                      params={"table": "mov_test_notamap"}).json()["binding"] is None
    assert client.get("/api/maps/paint-rules").json()["binding"] is None


def test_partial_declaration_inherits_and_never_invents_a_convention():
    """[2026-08-11] 선언 바인딩의 **누락 키는 상속된다** — 관례 이름으로 채우지 않는다.

    이 테스트는 뒤집힌 것이다. 종전 계약은 「누락 키를 데이터 경로의 실효 기본값으로
    채워 서빙한다」였고, 그 기본값이 `x`/`y`/`val` 리터럴과 `key_columns=["lot","slot"]`
    이었다. 그 규칙이 **2026-08-10 사고의 기전**이다: `core_wafer_map`의 정체성이
    `["wafer_id"]`로 옮겨간 뒤 「상속시키려고」 `key_columns`를 지우면 상속이 아니라
    **폐기된 정체성 `["lot","slot"]`**을 조용히 받았다. 이제 우선순위는 키마다
    `선언 > table_config 유도 > 이름을 대고 거절`이고 관례 폴백은 없다.
    """
    # table_config가 모르는 테이블 → 상속할 바탕이 없다. 없는 것을 지어내는 대신 거절한다.
    cfg = {"table_bindings": {"some_map": {"columns": {"val": "leg"}}}}
    assert map_overlay.resolve_binding_info(cfg, "some_map") is None
    assert map_overlay.resolve_binding(cfg, "some_map") is None

    binding, prov, _guessed = map_overlay.resolve_binding_parts(cfg, "some_map")
    assert binding is None
    assert prov["val"]["origin"] == map_overlay.ORIGIN_DECLARED
    for key in ("x", "y", "key_columns"):
        assert prov[key]["origin"] == map_overlay.ORIGIN_ABSENT, key
        assert prov[key]["value"] is None, key


def test_omitted_key_inherits_map_key_columns_not_lot_slot(mov_env):
    """[2026-08-11] 정체성 키를 지우면 `table_config.map_key_columns`를 **상속한다**.

    [mutation guard] 이 단언이 지키는 것은 하나다 — 지운 키가 `["lot","slot"]`으로
    돌아오지 않는 것. 그 값이 돌아오면 2026-08-10 사고가 다시 무장된다. 이 픽스처는
    `lot`/`slot` 컬럼을 **갖고 있지도 않아서**, 관례 폴백이 살아나면 실재하지 않는
    컬럼으로 필터를 만든다 — 즉 결함 축이 실제로 활성화돼 있다.
    """
    from database import crud

    table = "mov_test_derived_map"
    declared = crud.TABLE_CONFIG[table].get("map_key_columns")
    assert declared == ["base"], "픽스처가 lot/slot과 다른 정체성을 선언해야 한다"
    types = crud.TABLE_CONFIG[table]["column_types"]
    assert "lot" not in types and "slot" not in types

    # 선언 블록은 있고 정체성 키만 없다 — 종전에 ["lot","slot"]이 나오던 바로 그 모양.
    cfg = {"table_bindings": {table: {"columns": {"x": "x", "y": "y", "val": "leg"}}}}
    info = map_overlay.resolve_binding_info(cfg, table)
    assert info["key_columns"] == ["base"]
    assert info["key_columns"] != ["lot", "slot"]

    _b, prov, _g = map_overlay.resolve_binding_parts(cfg, table)
    assert prov["key_columns"]["origin"] == map_overlay.ORIGIN_INHERITED
    assert prov["key_columns"]["from"] == "table_config"


def test_declared_column_absent_from_table_config_is_refused_by_name(mov_env):
    """[2026-08-11] 선언이 없는 컬럼을 가리키면 **조용히 이기지 않고 거절한다**.

    이것이 2026-08-04 라이브 사고의 형태다(`bin_map.columns.x = "x"` on `dt_log`).
    종전에는 그 선언이 올바른 유도를 이기고 0건을 읽었다. 이제 바인딩 전체가 거절되고
    사유가 키와 컬럼을 이름으로 댄다.
    """
    table = "mov_test_odd_map"
    good = {"x": "tx", "y": "ty", "val": "core_lot",
            "key_columns": ["tape_lot", "tape_slot"]}
    # 온전한 선언은 그대로 해석된다 — 거절이 정상 경로를 잡아먹지 않는 것부터 확인한다.
    assert map_overlay.resolve_binding(cfg_of(table, good), table) is not None

    poisoned = dict(good, x="no_such_column")
    assert map_overlay.resolve_binding(cfg_of(table, poisoned), table) is None
    assert map_overlay.resolve_binding_info(cfg_of(table, poisoned), table) is None

    _b, prov, _g = map_overlay.resolve_binding_parts(cfg_of(table, poisoned), table)
    assert prov["x"]["origin"] == map_overlay.ORIGIN_REFUSED
    assert prov["x"]["value"] == "no_such_column"
    # 나머지 키는 여전히 자기 출처를 말한다 — 거절이 진단을 지우지 않는다.
    assert prov["y"]["origin"] == map_overlay.ORIGIN_DECLARED


def cfg_of(table: str, columns: dict) -> dict:
    return {"table_bindings": {table: {"columns": dict(columns)}}}


def test_paint_rules_marks_fallback_guess_explicitly(mov_env, client):
    """[F2] 후보 밖 값 컬럼의 추측은 서빙되되 **반드시** fallback_guess로 표기된다.

    데이터 경로는 이 추측을 거부하므로(test_fallback_guess_refused_in_data_path),
    이 표지는 클라가 '조용한 미끼 렌더' 대신 경고를 띄울 유일한 근거다."""
    _seed(mov_env)
    body = client.get("/api/maps/paint-rules",
                      params={"table": "mov_test_upper_map"}).json()
    assert body["binding"] == {"x": "x", "y": "y", "val": "VAL", "index": None,
                               "key_columns": ["lot", "slot"],
                               "source": "fallback_guess"}
    # 추측할 데이터 컬럼조차 없으면 표기할 것도 없다 — null
    assert client.get("/api/maps/paint-rules",
                      params={"table": "mov_test_bare_map"}).json()["binding"] is None


def test_value_column_follows_declared_candidate_order(mov_env, client,
                                                       tmp_path, monkeypatch):
    """[mutation guard] Reordering the declared candidates flips which column is
    detected — proves derive_table_binding consumes the resolved list, not its own
    hardcode. The fixture has BOTH 'val' and 'leg' so the order axis is live: the
    two halves of this test must return different values."""
    db = mov_env
    _seed(db)
    _add(db, "mov_test_dual_map", cell_key="D1", base="BASE-9", x=4, y=4,
         val="FROM_VAL", leg="FROM_LEG")
    db.commit()
    params = {"target_table": "mov_test_base_map", "target_key": "L1_01",
              "sources": "mov_test_dual_map:BASE-9"}

    # Default order: 'val' precedes 'leg'
    body = client.get("/api/maps/overlay", params=params).json()
    assert body["overlays"][0]["cells"] == [{"x": 4, "y": 4, "val": "FROM_VAL"}]

    # Declared order reverses precedence -> detection must follow the declaration
    _write_cfg(tmp_path, monkeypatch, {"value_column_candidates": ["leg", "val"]})
    body = client.get("/api/maps/overlay", params=params).json()
    assert body["overlays"][0]["cells"] == [{"x": 4, "y": 4, "val": "FROM_LEG"}]


# ---------------------------------------------------------------------------
# [D1 2026-08-04] Auto-registered geometry is SYNTHETIC, and synthetic is not declared.
#
# `map_meta_registrar.synthesize_grid_meta` writes chip 1x1 to say "no circle mask" in the
# mask predicate's own vocabulary. That is deliberate and it keeps such maps pushable. What
# was missing is the READING side: a synthesized signature is PRESENT and WELL-FORMED, so
# `make_frame_transform`'s only gate ("refuse when the signature is MISSING") passed it, and
# the server aligned a map nobody measured against a real one at a 1mm pitch.
#
# Measured on the production database 2026-08-04 (read-only): 668 metadata rows, 320 carry
# chip 1x1, ALL 320 carry the flag, flagless 1x1 rows = 0. So the discriminator is the FLAG,
# never the value - 1 is a legal pitch, and a marker that is also a datum can never be told
# apart from a measurement.
# ---------------------------------------------------------------------------

AUTO_PHYS = {"phys_wafer_dia": 300, "phys_chip_x": 1, "phys_chip_y": 1,
             "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3}


def _synthetic_of(**kw):
    """A meta shaped exactly like `synthesize_grid_meta`'s output (mark included)."""
    m = _meta_of(phys=dict(AUTO_PHYS), **kw)
    m["auto_registered"] = True
    return m


def test_geometry_declaration_is_one_predicate_with_four_tokens(mov_env):
    """The single spelling of "is this geometry a declaration", and its vocabulary.

    THE LOAD-BEARING CASE is the unflagged 1x1: a map that really is 1mm per die and carries
    NO mark must answer `declared`. An implementation that sniffs the chip VALUE instead of
    the mark passes every other case here and fails only that one.
    """
    assert map_overlay.geometry_declaration(_meta_of()) == map_overlay.GEOMETRY_DECLARED
    assert map_overlay.geometry_declaration(
        _meta_of(phys=dict(AUTO_PHYS))) == map_overlay.GEOMETRY_DECLARED
    assert map_overlay.geometry_declaration(
        _synthetic_of()) == map_overlay.GEOMETRY_AUTO_REGISTERED
    bare = {k: v for k, v in _meta_of().items() if not k.startswith("phys_")}
    assert map_overlay.geometry_declaration(bare) == map_overlay.GEOMETRY_ABSENT
    assert map_overlay.geometry_declaration(
        _meta_of(phys=dict(PHYS_STD, phys_chip_x="seven"))) == map_overlay.GEOMETRY_UNPARSABLE
    assert map_overlay.geometry_declaration(None) == map_overlay.GEOMETRY_ABSENT
    # `auto_registered: false` is a LEGITIMATE declaration, not a marker.
    assert map_overlay.geometry_declaration(
        dict(_meta_of(), auto_registered=False)) == map_overlay.GEOMETRY_DECLARED
    # The mark is read BEFORE the values. Values first and the mark does nothing.
    assert map_overlay.geometry_declaration(
        dict(_synthetic_of(), phys_chip_x=14.3)) == map_overlay.GEOMETRY_AUTO_REGISTERED


def test_synthetic_fixture_would_otherwise_align(mov_env):
    """FIXTURE ACTIVITY, asserted rather than assumed.

    Every refusal below is evidence only if the same pair WOULD have aligned without the
    mark. If the fixture were refused for some other reason (dims, absent phys) the refusal
    assertions would pass against code that does nothing.
    """
    src, tgt = _synthetic_of(rotation=90), _meta_of()
    unflagged = {k: v for k, v in src.items() if k != "auto_registered"}
    tf = map_overlay.make_frame_transform(unflagged, tgt)      # must NOT raise
    assert tf(1, 1) is not None
    assert map_overlay.resolve_align(unflagged, tgt)[1] == "derived", (
        "the fixture must reach the transform, not stop at the identity shortcut")


def test_auto_registered_source_refuses_by_name(mov_env):
    """A named refusal that says WHICH map and WHY - never an empty or plausible result."""
    with pytest.raises(ValueError) as e:
        map_overlay.make_frame_transform(_synthetic_of(rotation=90), _meta_of())
    msg = str(e.value)
    assert "소스" in msg and "타깃" not in msg, msg
    assert "자동 등록" in msg, msg
    assert "chip 1x1" in msg, "the operator cannot act on a refusal that hides the value"


def test_auto_registered_target_refuses_by_name(mov_env):
    """The gate is symmetric: the seat's geometry is as load-bearing as the source's."""
    with pytest.raises(ValueError) as e:
        map_overlay.make_frame_transform(_meta_of(rotation=90), _synthetic_of())
    msg = str(e.value)
    assert "타깃" in msg and "소스" not in msg, msg
    assert "자동 등록" in msg, msg


def test_both_sides_synthetic_names_both(mov_env):
    """Both halves synthetic - both are named. A refusal naming one map sends the operator
    to fix one of the two things that need fixing."""
    with pytest.raises(ValueError) as e:
        map_overlay.make_frame_transform(_synthetic_of(rotation=90), _synthetic_of())
    msg = str(e.value)
    assert "소스" in msg and "타깃" in msg, msg


def test_declared_1x1_geometry_still_aligns(mov_env):
    """The magic-number implementation dies here. A real 1mm-per-die map carries no mark and
    must keep aligning."""
    real_1x1 = _meta_of(rotation=90, phys=dict(AUTO_PHYS))
    tf = map_overlay.make_frame_transform(real_1x1, _meta_of(phys=dict(AUTO_PHYS)))
    assert tf(1, 1) is not None


def test_overlay_api_surfaces_the_refusal_by_name(mov_env, client):
    """END TO END. `align_unavailable` plus a Korean reason naming the cause.

    An empty `cells` list is NOT what this asserts - an accidentally-empty result has passed
    as an intended refusal in this repository before, so the status and the reason carry the
    claim and the emptiness is only a corollary.
    """
    db = mov_env
    _add(db, "mov_test_base_map", cell_key="AR1", lot="LAR", slot="01", x=1, y=1, val="P")
    _meta(db, "mov_test_base_map", "LAR_01", rotation=0)
    _add(db, "mov_test_defect_map", cell_key="AR2", lot="LAR", slot="01", x=1, y=1, val="D")
    model = models.DYNAMIC_TABLES["wafer_map_metadata"]
    db.add(model(row_id=str(uuid.uuid4()), business_key_val="mov_test_defect_map_LAR_01",
                 map_pk="mov_test_defect_map_LAR_01", target_table="mov_test_defect_map",
                 map_id="LAR_01",
                 grid_metadata=json.dumps(_synthetic_of(rotation=90))))
    db.commit()
    o = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "LAR_01",
        "sources": "mov_test_defect_map",
    }).json()["overlays"][0]
    assert o["status"] == map_overlay.STATUS_ALIGN_UNAVAILABLE
    detail = o["detail"] or ""
    assert "자동 등록" in detail, detail
    assert "소스" in detail, detail
    assert o["cells"] == []          # corollary, not the claim


def test_circle_mask_still_honours_synthetic_geometry(mov_env):
    """THE DELIBERATE CARVE-OUT, pinned so a later tidy-up cannot erase it silently.

    `circle_die_mask` asks a DIFFERENT question than the alignment gate: not "may I move
    coordinates on this evidence" but "which cells does this geometry admit". The synthetic
    spec was built to answer exactly that - mask-neutral, every cell valid - and the client
    (`isCellInsideWaferFast`) answers the same. Returning None here would throw away the one
    thing the synthetic spec says correctly AND open a new seam disagreement.
    """
    m = _synthetic_of(cols=6, rows=6)
    mask = map_overlay.circle_die_mask(m)
    assert mask is not None, "the alignment rule leaked into the mask question"
    assert len(mask) == 36, "the synthetic spec is mask-neutral: every cell is admitted"
    basis = map_overlay.resolve_valid_die_basis(m)
    assert basis["source"] == map_overlay.SOURCE_CIRCLE
    assert basis["basis"] is not None and len(basis["basis"]) == 36
