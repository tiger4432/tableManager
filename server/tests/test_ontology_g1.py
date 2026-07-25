"""[Ontology G1] 그래프 기반 구축 검증 (docs/spec/ONTOLOGY_GRAPH_SPEC.md §2·§3·§5).

검증 범위:
- 매핑 config v2 로더/검증 — description 필수(테이블/엣지), 잘못된 컬럼 참조 거부,
  공간 속성 선언(§7.5), 해당 테이블만 스킵(전체 실패 금지), v1 형식 무시
- enrichment rule → RESOLVED_AS 자동 승격 (사용자 노드 매핑 병합 + 기본 합성)
- materializer — 멱등성(같은 배치 2회 → 수 불변), 청킹 경계, DELETE 스킵,
  엣지 provenance(user 승격 엣지 고정), identity 미해석 스킵
- 전체 재동기화(resync_table) — 키셋 청킹(C-7), is_graph_synced 스탬프, 멱등
- outbox 소비 커서(graph_sync_state) 초기화/전진
- E2E: 데모 형태 3종 인제션 → 노드/엣지 수 → enrichment target 채움 → RESOLVED_AS 생성

[격리] 테이블명은 사용자 실 config에 실존 불가능한 onto_test_* 접두를 사용한다
(conftest가 import 시점에 실 config를 선점하는 공유 sqlite 함정 — 교훈 파일 참조).
"""
import json
import uuid

import pytest

import enrichment_config
import ontology_config
import graph_materializer
from database import crud, models, schemas
from database.models import DatabaseOutbox, GraphNode, GraphEdge

# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

ONTO_TABLES = {
    "onto_test_bonding": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string",
            "eventtime": "string",
            "base_id": "string",
            "bx": "number",
            "by": "number",
            "core_lot": "string",
            "core_slot": "string",
            "cx": "number",
            "cy": "number",
        },
    },
    "onto_test_wafer_hist": {
        "business_key": "hist_id",
        "column_types": {
            "hist_id": "string",
            "step": "string",
            "lot": "string",
            "slot": "string",
            "wafer_id": "string",
            "event_time": "string",
        },
    },
    "onto_test_core_map": {
        "business_key": "core_key",
        "composite_key_source": ["core_lot", "core_slot"],
        "composite_key_separator": "_",
        "column_types": {
            "core_key": "string",
            "core_lot": "string",
            "core_slot": "string",
            "wafer_id": "string",
            "chip_count": "number",
            "eventtime": "string",
        },
    },
}

MAPPING_FILE = {
    "onto_test_bonding": {
        "description": "본딩 설비가 chip 1개를 base에 실장한 이벤트",
        "node": {
            "label": "Chip",
            "identity": "log_id",
            "props": [
                {"col": "bx", "spatial": {"coord_system": "base_grid", "axis": "x"}},
                {"col": "by", "spatial": {"coord_system": "base_grid", "axis": "y"}},
                {"col": "cx", "spatial": {"coord_system": "wafer_grid", "axis": "x"}},
                {"col": "cy", "spatial": {"coord_system": "wafer_grid", "axis": "y"}},
            ],
        },
        "edges": [
            {
                "type": "BONDED_FROM",
                "target_label": "Wafer",
                "target_identity_from": ["core_lot", "core_slot"],
                "description": "이 chip이 잘려 나온 원판 wafer(lot|slot 표기)",
            },
            {
                "type": "PLACED_ON",
                "target_label": "Base",
                "target_identity_from": ["base_id"],
                "props": ["eventtime"],
                "description": "실장된 대상 지그",
            },
        ],
    },
    "onto_test_wafer_hist": {
        "description": "wafer가 공정 step을 통과한 이력",
        "node": {"label": "Wafer", "identity": "wafer_id", "props": ["lot", "slot"]},
        "edges": [
            {
                "type": "WENT_THROUGH",
                "target_label": "Step",
                "target_identity_from": ["step"],
                "props": ["event_time"],
                "description": "wafer가 이 step을 통과함",
            }
        ],
    },
    "onto_test_core_map": {
        "description": "lot/slot 표기를 실제 wafer로 해석한 사람 교정 결과",
        "node": {
            "label": "Wafer",
            "identity": ["core_lot", "core_slot"],
            "props": ["chip_count"],
        },
        "edges": [],
    },
}

ENRICH_RULES_FILE = {
    "onto_test_attribution": {
        "source_table": "onto_test_bonding",
        "derived_table": "onto_test_core_map",
        "decision_key": ["core_lot", "core_slot"],
        "target_fields": ["wafer_id"],
        "aggregations": {"chip_count": "count"},
    }
}


@pytest.fixture()
def onto_env(db_session, tmp_path, monkeypatch):
    """conftest 기본 환경에 온톨로지 테스트 테이블 + 매핑/enrichment 파일을 추가한다."""
    models.init_dynamic_models(ONTO_TABLES)
    crud.TABLE_CONFIG.update(ONTO_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    mapping_path = tmp_path / "ontology_mapping.json"
    mapping_path.write_text(json.dumps(MAPPING_FILE), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(mapping_path))

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps(ENRICH_RULES_FILE), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))

    return db_session


def _load_mappings():
    return ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)


def _seed(db, table, rows, tx_id, source_name="pipeline_parser"):
    updates = [
        schemas.GeneralUpdateItem(updates=dict(row), source_name=source_name, updated_by="tester")
        for row in rows
    ]
    batch = schemas.GeneralUpdateBatch(updates=updates, transaction_id=tx_id, silent=True)
    crud.apply_batch_updates(db, table, batch)


def _events_for(db, table, tx_id=None):
    q = db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == table)
    events = q.order_by(DatabaseOutbox.id.asc()).all()
    if tx_id:
        events = [e for e in events if (e.safe_payload or {}).get("transaction_id") == tx_id]
    return events


def _bonding_rows(n, lot="LOTA", slot="3", base="B1"):
    return [
        {
            "log_id": f"LOG{i:04d}",
            "eventtime": f"2026-07-25 10:{i % 60:02d}:00",
            "base_id": base,
            "bx": 1, "by": 2, "cx": i, "cy": i + 1,
            "core_lot": lot, "core_slot": slot,
        }
        for i in range(n)
    ]


def _counts(db):
    return db.query(GraphNode).count(), db.query(GraphEdge).count()


# ---------------------------------------------------------------------------
# 1) 매핑 로더/검증
# ---------------------------------------------------------------------------

def test_loader_valid_config(onto_env):
    mappings = _load_mappings()
    assert set(MAPPING_FILE.keys()) <= set(mappings.keys())

    bonding = mappings["onto_test_bonding"]
    # identity 단일 컬럼 → 리스트 정규화
    assert bonding["node"]["identity"] == ["log_id"]
    # 공간 속성 선언 보존 (§7.5)
    cx = next(p for p in bonding["node"]["props"] if p["col"] == "cx")
    assert cx["spatial"] == {"coord_system": "wafer_grid", "axis": "x"}
    assert len(bonding["edges"]) == 2

    core = mappings["onto_test_core_map"]
    assert core["node"]["identity"] == ["core_lot", "core_slot"]


def test_loader_missing_description_rejected(onto_env, tmp_path, monkeypatch):
    bad = json.loads(json.dumps(MAPPING_FILE))
    del bad["onto_test_bonding"]["description"]
    p = tmp_path / "bad1.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(p))

    mappings = ontology_config.load_ontology_mappings(
        known_tables=crud.TABLE_CONFIG, include_enrichment=False
    )
    # 해당 테이블만 스킵 — 나머지는 살아있어야 한다(전체 기동 실패 금지)
    assert "onto_test_bonding" not in mappings
    assert "onto_test_wafer_hist" in mappings


def test_loader_missing_edge_description_rejected(onto_env, tmp_path, monkeypatch):
    bad = json.loads(json.dumps(MAPPING_FILE))
    del bad["onto_test_bonding"]["edges"][0]["description"]
    p = tmp_path / "bad2.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(p))

    mappings = ontology_config.load_ontology_mappings(
        known_tables=crud.TABLE_CONFIG, include_enrichment=False
    )
    assert "onto_test_bonding" not in mappings
    assert "onto_test_wafer_hist" in mappings


def test_loader_unknown_column_rejected(onto_env, tmp_path, monkeypatch):
    bad = json.loads(json.dumps(MAPPING_FILE))
    bad["onto_test_wafer_hist"]["node"]["identity"] = "no_such_col"
    p = tmp_path / "bad3.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(p))

    mappings = ontology_config.load_ontology_mappings(
        known_tables=crud.TABLE_CONFIG, include_enrichment=False
    )
    assert "onto_test_wafer_hist" not in mappings
    assert "onto_test_bonding" in mappings


def test_loader_ignores_v1_format(onto_env, tmp_path, monkeypatch):
    v1 = {"default": {"node_label": "Row"}, "tables": {"assemblies": {"node_label": "Assembly"}}}
    p = tmp_path / "v1.json"
    p.write_text(json.dumps(v1), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(p))

    mappings = ontology_config.load_ontology_mappings(
        known_tables=crud.TABLE_CONFIG, include_enrichment=False
    )
    assert mappings == {}


# ---------------------------------------------------------------------------
# 2) enrichment rule → RESOLVED_AS 자동 승격
# ---------------------------------------------------------------------------

def test_enrichment_promotion_merges_into_user_mapping(onto_env):
    mappings = _load_mappings()
    core = mappings["onto_test_core_map"]
    # 사용자 노드 정의 유지
    assert core["node"]["label"] == "Wafer"
    assert core["node"]["identity"] == ["core_lot", "core_slot"]
    # RESOLVED_AS 승격 엣지 합성 — provenance는 user 고정
    resolved = [e for e in core["edges"] if e["type"] == "RESOLVED_AS"]
    assert len(resolved) == 1
    assert resolved[0]["target_label"] == "Wafer"          # wafer_id → Wafer
    assert resolved[0]["target_identity_from"] == ["wafer_id"]
    assert resolved[0]["source_override"] == "user"
    assert resolved[0]["description"]


def test_enrichment_promotion_synthesizes_default_node(onto_env, tmp_path, monkeypatch):
    # 매핑 파일에서 파생 테이블 정의 제거 → 기본 노드 합성 확인
    partial = json.loads(json.dumps(MAPPING_FILE))
    del partial["onto_test_core_map"]
    p = tmp_path / "partial.json"
    p.write_text(json.dumps(partial), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(p))

    mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)
    core = mappings.get("onto_test_core_map")
    assert core is not None
    assert core["node"]["label"] == "OntoTestCoreMap"       # PascalCase 기본 라벨
    assert core["node"]["identity"] == ["core_lot", "core_slot"]
    assert any(e["type"] == "RESOLVED_AS" for e in core["edges"])


def test_enrichment_promotion_respects_user_defined_edge(onto_env):
    mappings = _load_mappings()
    user_defined = {
        "onto_test_core_map": {
            **mappings["onto_test_core_map"],
            "edges": [{
                "type": "RESOLVED_AS",
                "target_label": "CustomWafer",
                "target_identity_from": ["wafer_id"],
                "props": [],
                "description": "사용자 정의",
            }],
        }
    }
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    merged = ontology_config.synthesize_enrichment_mappings(user_defined, rules)
    edges = merged["onto_test_core_map"]["edges"]
    resolved = [e for e in edges if e["type"] == "RESOLVED_AS"]
    assert len(resolved) == 1                               # 사용자 정의가 이긴다(중복 합성 없음)
    assert resolved[0]["target_label"] == "CustomWafer"


# ---------------------------------------------------------------------------
# 3) materializer — 멱등성/청킹/스킵 규칙
# ---------------------------------------------------------------------------

def test_materialize_idempotent(onto_env):
    db = onto_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_bonding", _bonding_rows(3), tx)
    events = _events_for(db, "onto_test_bonding", tx)
    assert events

    mappings = _load_mappings()
    stats = graph_materializer.materialize_events(db, events, mappings)
    db.commit()
    n1, e1 = _counts(db)
    # Chip×3 + Wafer(LOTA|3) + Base(B1) = 5 / BONDED_FROM×3 + PLACED_ON×3 = 6
    assert n1 == 5
    assert e1 == 6
    assert stats["rows"] == 3

    # 같은 배치 2회 → 노드/엣지 수 불변 (멱등 UPSERT)
    graph_materializer.materialize_events(db, events, mappings)
    db.commit()
    n2, e2 = _counts(db)
    assert (n2, e2) == (n1, e1)


def test_materialize_node_props_and_spatial(onto_env):
    db = onto_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_bonding", _bonding_rows(1), tx)
    mappings = _load_mappings()
    graph_materializer.materialize_events(db, _events_for(db, "onto_test_bonding", tx), mappings)
    db.commit()

    chip = db.query(GraphNode).filter(GraphNode.label == "Chip").first()
    assert chip is not None
    assert chip.props.get("cx") == 0
    assert chip.props.get("_spatial", {}).get("cx") == {"coord_system": "wafer_grid", "axis": "x"}

    # 엣지 provenance = 이벤트 source_name(pipeline_parser)
    edge = db.query(GraphEdge).filter(GraphEdge.type == "PLACED_ON").first()
    assert edge is not None
    assert edge.source_name == "pipeline_parser"
    assert edge.props.get("eventtime")
    assert edge.source_row_ref.startswith("onto_test_bonding:")


def test_materialize_skips_unmapped_and_delete(onto_env):
    db = onto_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    # conftest 기본 테이블(raw_table_1)은 매핑이 없다 — 무시 경로
    _seed(db, "raw_table_1", [{"EQP_ID": f"EQP_X_{uuid.uuid4().hex[:6]}"}], tx)
    events = _events_for(db, "raw_table_1", tx)
    mappings = _load_mappings()
    stats = graph_materializer.materialize_events(db, events, mappings)
    db.commit()
    assert stats["rows"] == 0
    assert stats["nodes"] == 0

    # DELETE 이벤트는 G1에서 스킵(카운트만)
    class _FakeDelete:
        event_type = "DELETE"
        table_name = "onto_test_bonding"
        payload = {}
    stats = graph_materializer.materialize_events(db, [_FakeDelete()], mappings)
    assert stats["skipped_deletes"] == 1


def test_materialize_skips_unresolvable_identity(onto_env):
    db = onto_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    rows = _bonding_rows(1)
    rows[0]["core_lot"] = None          # BONDED_FROM 타깃 identity 미해석
    _seed(db, "onto_test_bonding", rows, tx)
    mappings = _load_mappings()
    graph_materializer.materialize_events(db, _events_for(db, "onto_test_bonding", tx), mappings)
    db.commit()
    assert db.query(GraphEdge).filter(GraphEdge.type == "BONDED_FROM").count() == 0
    assert db.query(GraphEdge).filter(GraphEdge.type == "PLACED_ON").count() == 1


def test_materialize_chunking_boundary(onto_env):
    db = onto_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_bonding", _bonding_rows(25), tx)
    mappings = _load_mappings()
    # 청크(10)보다 큰 배치 — 청크 경계에서 유실 없이 전량 반영
    stats = graph_materializer.materialize_events(
        db, _events_for(db, "onto_test_bonding", tx), mappings, chunk_size=10
    )
    db.commit()
    assert stats["rows"] == 25
    assert db.query(GraphNode).filter(GraphNode.label == "Chip").count() == 25
    assert db.query(GraphEdge).filter(GraphEdge.type == "BONDED_FROM").count() == 25


def test_compose_identity_normalization():
    assert graph_materializer.compose_identity(["LOTA", "3"]) == "LOTA|3"
    assert graph_materializer.compose_identity(["LOTA", 3.0]) == "LOTA|3"   # float 정수 안정화
    assert graph_materializer.compose_identity(["LOTA", None]) is None
    assert graph_materializer.compose_identity(["", "3"]) is None


# ---------------------------------------------------------------------------
# 4) E2E — 데모 3종 흐름: 인제션 → 그래프 → enrichment 교정 → RESOLVED_AS
# ---------------------------------------------------------------------------

def test_e2e_demo_flow_resolved_as(onto_env):
    db = onto_env
    mappings = _load_mappings()

    # 1) bonding 인제션 (chip 2개, 같은 lot/slot)
    tx1 = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_bonding", _bonding_rows(2), tx1)
    graph_materializer.materialize_events(db, _events_for(db, "onto_test_bonding", tx1), mappings)
    db.commit()

    # 2) wafer 이력 인제션 — 실개체 Wafer(W123) 노드 + WENT_THROUGH
    tx2 = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_wafer_hist", [{
        "hist_id": "H1", "step": "STEP1", "lot": "LOTA", "slot": "3",
        "wafer_id": "W123", "event_time": "2026-07-25 09:00:00",
    }], tx2)
    graph_materializer.materialize_events(db, _events_for(db, "onto_test_wafer_hist", tx2), mappings)
    db.commit()

    # 3) enrichment 파생 행 생성(chain — target 미기입) → RESOLVED_AS 아직 없음
    tx3 = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_core_map", [{
        "core_key": "LOTA_3", "core_lot": "LOTA", "core_slot": "3", "chip_count": 2,
    }], tx3, source_name="chain_ingestion")
    graph_materializer.materialize_events(db, _events_for(db, "onto_test_core_map", tx3), mappings)
    db.commit()
    assert db.query(GraphEdge).filter(GraphEdge.type == "RESOLVED_AS").count() == 0

    # 4) 사람 교정 — target(wafer_id) 채움(user 소스) → RESOLVED_AS 승격
    tx4 = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_core_map", [{
        "core_key": "LOTA_3", "core_lot": "LOTA", "core_slot": "3", "wafer_id": "W123",
    }], tx4, source_name="user")
    graph_materializer.materialize_events(db, _events_for(db, "onto_test_core_map", tx4), mappings)
    db.commit()

    resolved = db.query(GraphEdge).filter(GraphEdge.type == "RESOLVED_AS").all()
    assert len(resolved) == 1
    assert resolved[0].source_name == "user"

    # 그래프 연결성: Chip -BONDED_FROM-> Wafer(LOTA|3) -RESOLVED_AS-> Wafer(W123) <-WENT_THROUGH
    proxy = db.query(GraphNode).filter(
        GraphNode.label == "Wafer", GraphNode.identity_key == "LOTA|3"
    ).first()
    real = db.query(GraphNode).filter(
        GraphNode.label == "Wafer", GraphNode.identity_key == "W123"
    ).first()
    assert proxy is not None and real is not None
    assert resolved[0].from_node == proxy.id
    assert resolved[0].to_node == real.id
    assert proxy.props.get("chip_count") == 2      # core_map props가 스텁을 덮지 않고 병합됨
    assert db.query(GraphEdge).filter(
        GraphEdge.type == "BONDED_FROM", GraphEdge.to_node == proxy.id
    ).count() == 2
    assert db.query(GraphEdge).filter(
        GraphEdge.type == "WENT_THROUGH", GraphEdge.from_node == real.id
    ).count() == 1


# ---------------------------------------------------------------------------
# 5) 전체 재동기화 (C-7 키셋 청킹) + 커서
# ---------------------------------------------------------------------------

def test_resync_table_keyset_chunking(onto_env):
    db = onto_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_bonding", _bonding_rows(25), tx)

    mappings = _load_mappings()
    stats = graph_materializer.resync_table(db, "onto_test_bonding", mappings, chunk_size=10)
    assert stats["chunks"] == 3                     # 25행 → 10/10/5 키셋 청크
    assert stats["rows"] == 25
    assert db.query(GraphNode).filter(GraphNode.label == "Chip").count() == 25

    # is_graph_synced 스탬프 확인
    model = models.DYNAMIC_TABLES["onto_test_bonding"]
    assert db.query(model).filter(model.is_graph_synced == True).count() == 25  # noqa: E712

    # 멱등: 재실행해도 수 불변
    n1, e1 = _counts(db)
    graph_materializer.resync_table(db, "onto_test_bonding", mappings, chunk_size=10)
    assert _counts(db) == (n1, e1)

    # provenance: 셀 레이어 최우선 소스(pipeline_parser)로 복원
    edge = db.query(GraphEdge).filter(GraphEdge.type == "BONDED_FROM").first()
    assert edge.source_name == "pipeline_parser"


def test_resync_table_partial_row_ids(onto_env):
    db = onto_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_bonding", _bonding_rows(5), tx)
    model = models.DYNAMIC_TABLES["onto_test_bonding"]
    target_ids = [r.row_id for r in db.query(model).limit(2).all()]

    mappings = _load_mappings()
    stats = graph_materializer.resync_table(
        db, "onto_test_bonding", mappings, row_ids=target_ids
    )
    assert stats["rows"] == 2
    assert db.query(GraphNode).filter(GraphNode.label == "Chip").count() == 2


def test_graph_cursor_init_and_advance(onto_env):
    db = onto_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed(db, "onto_test_bonding", _bonding_rows(1), tx)

    from graph_sync_worker import _get_or_init_graph_cursor, _advance_graph_cursor
    from sqlalchemy import func as sa_func

    max_id = db.query(sa_func.max(DatabaseOutbox.id)).scalar() or 0
    cursor = _get_or_init_graph_cursor(db)
    assert cursor == max_id                          # 최초 초기화 = 현재 최대 id (백로그 스킵)

    _seed(db, "onto_test_bonding", _bonding_rows(1, lot="LOTB"), f"tx_{uuid.uuid4().hex[:8]}")
    new_max = db.query(sa_func.max(DatabaseOutbox.id)).scalar()
    assert new_max > cursor                          # 새 이벤트는 커서 뒤에 있다

    _advance_graph_cursor(db, new_max)
    db.commit()
    assert _get_or_init_graph_cursor(db) == new_max
