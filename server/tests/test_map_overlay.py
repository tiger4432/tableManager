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
}

GRID6 = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
         "side": "front", "rotation": 0}


def _add(db, table, **cols):
    model = models.DYNAMIC_TABLES[table]
    bk = MOV_TABLES[table]["business_key"]
    db.add(model(row_id=str(uuid.uuid4()),
                 business_key_val=str(cols.get(bk) or uuid.uuid4()), **cols))


def _meta(db, target_table, map_id, rotation=0, side="front", cols=6, rows=6):
    meta = dict(GRID6)
    meta["rotation"] = rotation
    meta["side"] = side
    meta["grid_cols"] = cols
    meta["grid_rows"] = rows
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
# 2. 선언 override / by_eqp 폴백 (차단 금지)
# ---------------------------------------------------------------------------

def test_declared_override_wins_over_derivation(mov_env, client, tmp_path, monkeypatch):
    _seed(mov_env)
    _write_cfg(tmp_path, monkeypatch, {
        "align_overrides": {"mov_test_eds_map": {"rotation": 0, "flip": "none"}},
    })
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_eds_map",
    }).json()
    o = body["overlays"][0]
    assert o["align_applied"]["origin"] == "declared"
    assert o["align_applied"]["rotation"] == 0
    assert {(c["x"], c["y"]) for c in o["cells"]} == {(6, 6), (2, 5)}  # 변환 없음


def test_by_eqp_missing_key_falls_back_to_default_without_blocking(mov_env, client,
                                                                   tmp_path, monkeypatch):
    """by_eqp에 장비 키가 없어도 차단하지 않고 default로 폴백 + note로 알린다."""
    _seed(mov_env)
    _write_cfg(tmp_path, monkeypatch, {
        "align_overrides": {"mov_test_eds_map": {
            "default": {"rotation": 180}, "by_eqp": {"METRO-A": {"rotation": 90}},
        }},
    })
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_eds_map", "eqp": "METRO-ZZ",
    }).json()
    o = body["overlays"][0]
    assert o["status"] == "ok"
    assert o["align_applied"]["origin"] == "default"
    assert o["align_applied"]["rotation"] == 180
    assert "METRO-ZZ" in o["align_applied"]["note"]


def test_by_eqp_hit_uses_declared_eqp_align(mov_env, client, tmp_path, monkeypatch):
    _seed(mov_env)
    _write_cfg(tmp_path, monkeypatch, {
        "align_overrides": {"mov_test_eds_map": {
            "default": {"rotation": 0}, "by_eqp": {"METRO-A": {"rotation": 180}},
        }},
    })
    body = client.get("/api/maps/overlay", params={
        "target_table": "mov_test_base_map", "target_key": "L1_01",
        "sources": "mov_test_eds_map", "eqp": "METRO-A",
    }).json()
    o = body["overlays"][0]
    assert o["align_applied"]["origin"] == "declared"
    assert {(c["x"], c["y"]) for c in o["cells"]} == {(1, 1), (5, 2)}


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
# 3-bis. [QA B3] side × 타깃 회전 조합 — 조용한 거울상 오답 차단 가드
#
# 배경: rel_rot + 단일 flip을 하나의 변환기로 합성하는데, back 반전 축이 프레임 자신의
# 회전에 따라 달라진다(90/270이면 행, 아니면 열). 따라서 두 프레임의 반전 축을 표현할 수
# 없고 QA 전수 대조에서 64조합 중 16개가 status=ok인 채 거울상으로 틀렸다.
# 현행 조치는 **명시 거절**이며, 근본 수정 시 아래 테스트가 기준이 된다.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target_rot", [90, 270])
@pytest.mark.parametrize("source_rot", [0, 90, 180, 270])
def test_side_mismatch_with_rotated_target_is_refused(mov_env, client, tmp_path,
                                                      monkeypatch, target_rot, source_rot):
    """면 반전 + 타깃 rot 90/270 → 그리지 않고 align_unavailable로 거절한다."""
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
    assert o["status"] == "align_unavailable", "거울상 오답을 조용히 내보내면 안 된다"
    assert o["cells"] == []
    assert o["align_applied"]["origin"] == "unresolvable"
    assert "면 반전" in (o["detail"] or "")


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
