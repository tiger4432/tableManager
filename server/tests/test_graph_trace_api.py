"""[Ontology G2] 추적(trace) API 검증 (G2 서버 지시서 — 경계 계약 총괄 고정).

검증 범위:
- POST /graph/trace — 멀티 시드 BFS 합집합, depth 캡(1..3, 400),
  시간 필터(null event_time 통과 포함), edge_types 필터,
  missing_seeds(전부 미존재여도 200), truncated(limit·하드캡, 잘린 노드 엣지 제외),
  시드 dedup, 검증 실패 400(빈 seeds / 잘못된 ISO 시간)
- GET /graph/mapping-summary — 로드된 매핑 요약(enrichment RESOLVED_AS 자동 승격 포함),
  매핑 없는 테이블 미포함

[격리] 그래프 시스템 테이블(graph_nodes/edges)에 직접 시딩 — API는 read-only이므로
materializer 경유가 불필요하다(뷰어 테스트와 동일 패턴).
테이블명은 사용자 config에 실존 불가능한 고유 접두(trace_test_*)를 사용(교훈 파일).
"""
import pytest

# ⚰️ [R-2026-08-14-H] 이 파일이 검증하던 두 라우트는 은퇴했다.
# `POST /graph/trace`와 `GET /graph/mapping-summary`가 이제 410으로 거절한다.
# 삭제가 아니라 스킵인 이유는 `test_graph_viewer_api.py` 상단과 같다 —
# 서술과 코드는 같은 변경(판정 ④)에서 함께 죽는다.
# 새 계약은 `test_graph_branch_retired.py`가 단언한다.
pytest.skip(
    "R-2026-08-14-H retired the old graph branch; these routes now refuse with "
    "410 old_graph_branch_retired. Removed together with the route bodies in "
    "ruling item 4. New contract: test_graph_branch_retired.py",
    allow_module_level=True,
)

import datetime  # noqa: E402
import json  # noqa: E402

import main  # noqa: E402
import ontology_config  # noqa: E402
import enrichment_config  # noqa: E402
from database import crud  # noqa: E402
from database.models import GraphNode, GraphEdge  # noqa: E402

T09 = datetime.datetime(2026, 7, 25, 9, 0, 0)
T10 = datetime.datetime(2026, 7, 25, 10, 0, 0)
T12 = datetime.datetime(2026, 7, 25, 12, 0, 0)


def _add_node(db, label, identity_key, props=None):
    n = GraphNode(label=label, identity_key=identity_key, props=props or {})
    db.add(n)
    db.flush()
    return n


def _add_edge(db, from_n, to_n, edge_type, source_name="pipeline_parser",
              updated_by=None, event_time=None):
    e = GraphEdge(
        type=edge_type, from_node=from_n.id, to_node=to_n.id,
        source_name=source_name, updated_by=updated_by, event_time=event_time,
    )
    db.add(e)
    db.flush()
    return e


@pytest.fixture()
def trace_env(db_session):
    """추적용 미니 토폴로지 (시간 속성 포함):

    Chip1 ─BONDED_FROM(t=None)→ WaferP(LOTA|3) ─RESOLVED_AS(user, t=10:00)→ WaferR(W123)
    Chip2 ─BONDED_FROM(t=None)→ WaferP
    Chip1 ─PLACED_ON(t=10:00)→ Base1
    WaferR ─WENT_THROUGH(t=09:00)→ Step1
    WaferR ─WENT_THROUGH(t=12:00)→ Step2
    """
    db = db_session
    nodes = {
        "chip1": _add_node(db, "Chip", "LOG0001", {"cx": 1}),
        "chip2": _add_node(db, "Chip", "LOG0002", {"cx": 2}),
        "wafer_p": _add_node(db, "Wafer", "LOTA|3", {"chip_count": 2}),
        "wafer_r": _add_node(db, "Wafer", "W123"),
        "base1": _add_node(db, "Base", "B1"),
        "step1": _add_node(db, "Step", "STEP1"),
        "step2": _add_node(db, "Step", "STEP2"),
    }
    _add_edge(db, nodes["chip1"], nodes["wafer_p"], "BONDED_FROM")
    _add_edge(db, nodes["chip2"], nodes["wafer_p"], "BONDED_FROM")
    _add_edge(db, nodes["chip1"], nodes["base1"], "PLACED_ON", event_time=T10)
    _add_edge(db, nodes["wafer_p"], nodes["wafer_r"], "RESOLVED_AS",
              source_name="user", updated_by="tester", event_time=T10)
    _add_edge(db, nodes["wafer_r"], nodes["step1"], "WENT_THROUGH", event_time=T09)
    _add_edge(db, nodes["wafer_r"], nodes["step2"], "WENT_THROUGH", event_time=T12)
    db.commit()
    return nodes


def _trace(client, **body):
    return client.post("/graph/trace", json=body)


def _node_keys(body):
    return {(n["label"], n["identity_key"]) for n in body["nodes"]}


# ---------------------------------------------------------------------------
# 1) 멀티 시드 합집합
# ---------------------------------------------------------------------------

def test_trace_multi_seed_union(client, trace_env):
    res = _trace(client, seeds=[
        {"label": "Chip", "identity": "LOG0002"},
        {"label": "Base", "identity": "B1"},
    ], depth=1)
    assert res.status_code == 200
    body = res.json()
    # chip2의 이웃(WaferP) ∪ base1의 이웃(Chip1) — 합집합
    assert _node_keys(body) == {
        ("Chip", "LOG0002"), ("Base", "B1"), ("Wafer", "LOTA|3"), ("Chip", "LOG0001"),
    }
    assert sorted(e["type"] for e in body["edges"]) == ["BONDED_FROM", "PLACED_ON"]
    assert body["seed_ids"] == [trace_env["chip2"].id, trace_env["base1"].id]
    assert body["missing_seeds"] == []
    assert body["truncated"] is False

    # 뷰어와 동일한 노드/엣지 형태 계약 + provenance
    placed = next(e for e in body["edges"] if e["type"] == "PLACED_ON")
    assert placed["source_name"] == "pipeline_parser"
    assert placed["event_time"].startswith("2026-07-25T10:00")
    bonded = next(e for e in body["edges"] if e["type"] == "BONDED_FROM")
    assert bonded["event_time"] is None


def test_trace_seed_dedup(client, trace_env):
    body = _trace(client, seeds=[
        {"label": "Chip", "identity": "LOG0001"},
        {"label": "Chip", "identity": "LOG0001"},
    ], depth=1).json()
    assert body["seed_ids"] == [trace_env["chip1"].id]


# ---------------------------------------------------------------------------
# 2) depth — 기본값 2, 하드캡 3
# ---------------------------------------------------------------------------

def test_trace_depth3_reaches_full_chain(client, trace_env):
    seeds = [{"label": "Chip", "identity": "LOG0001"}]
    # depth 2: chip1 → (wafer_p, base1) → (chip2, wafer_r) — step 미도달
    body = _trace(client, seeds=seeds, depth=2).json()
    assert ("Step", "STEP1") not in _node_keys(body)
    # depth 3: wafer_r → step1/step2 도달 (전 토폴로지 7노드)
    body = _trace(client, seeds=seeds, depth=3).json()
    assert len(body["nodes"]) == 7
    assert {("Step", "STEP1"), ("Step", "STEP2")} <= _node_keys(body)


def test_trace_default_depth_is_2(client, trace_env):
    body = _trace(client, seeds=[{"label": "Chip", "identity": "LOG0001"}]).json()
    assert _node_keys(body) == {
        ("Chip", "LOG0001"), ("Wafer", "LOTA|3"), ("Base", "B1"),
        ("Chip", "LOG0002"), ("Wafer", "W123"),
    }


def test_trace_depth_out_of_range_400(client, trace_env):
    seeds = [{"label": "Chip", "identity": "LOG0001"}]
    assert _trace(client, seeds=seeds, depth=0).status_code == 400
    assert _trace(client, seeds=seeds, depth=4).status_code == 400


# ---------------------------------------------------------------------------
# 3) 시간 필터 — null event_time은 구조 엣지로 항상 통과
# ---------------------------------------------------------------------------

def test_trace_time_filter_passes_null_event_time(client, trace_env):
    body = _trace(client, seeds=[{"label": "Wafer", "identity": "LOTA|3"}], depth=1,
                  time_from="2026-07-25T09:30:00", time_to="2026-07-25T11:00:00").json()
    # BONDED_FROM(null) 통과 + RESOLVED_AS(10:00) 창 안 → 전 이웃 도달
    assert _node_keys(body) == {
        ("Wafer", "LOTA|3"), ("Chip", "LOG0001"), ("Chip", "LOG0002"), ("Wafer", "W123"),
    }


def test_trace_time_filter_excludes_out_of_window(client, trace_env):
    body = _trace(client, seeds=[{"label": "Wafer", "identity": "LOTA|3"}], depth=1,
                  time_from="2026-07-25T11:00:00", time_to="2026-07-25T12:00:00").json()
    # RESOLVED_AS(10:00)는 창 밖 → WaferR 미도달. null 엣지(BONDED_FROM)는 여전히 통과
    assert _node_keys(body) == {
        ("Wafer", "LOTA|3"), ("Chip", "LOG0001"), ("Chip", "LOG0002"),
    }
    assert sorted(e["type"] for e in body["edges"]) == ["BONDED_FROM", "BONDED_FROM"]


def test_trace_time_filter_bounds_each_side(client, trace_env):
    seeds = [{"label": "Wafer", "identity": "W123"}]
    # time_from만: 09:00 WENT_THROUGH 제외, 10:00/12:00 통과
    body = _trace(client, seeds=seeds, depth=1, time_from="2026-07-25T09:30:00").json()
    assert _node_keys(body) == {("Wafer", "W123"), ("Wafer", "LOTA|3"), ("Step", "STEP2")}
    # time_to만: 12:00 제외
    body = _trace(client, seeds=seeds, depth=1, time_to="2026-07-25T11:00:00").json()
    assert _node_keys(body) == {("Wafer", "W123"), ("Wafer", "LOTA|3"), ("Step", "STEP1")}


def test_trace_invalid_time_400(client, trace_env):
    res = _trace(client, seeds=[{"label": "Chip", "identity": "LOG0001"}],
                 time_from="not-a-time")
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# 4) edge_types 필터
# ---------------------------------------------------------------------------

def test_trace_edge_types_filter(client, trace_env):
    body = _trace(client, seeds=[{"label": "Wafer", "identity": "LOTA|3"}], depth=1,
                  edge_types=["BONDED_FROM"]).json()
    assert _node_keys(body) == {
        ("Wafer", "LOTA|3"), ("Chip", "LOG0001"), ("Chip", "LOG0002"),
    }
    assert {e["type"] for e in body["edges"]} == {"BONDED_FROM"}


def test_trace_edge_types_filter_applies_every_hop(client, trace_env):
    body = _trace(client, seeds=[{"label": "Wafer", "identity": "LOTA|3"}], depth=3,
                  edge_types=["RESOLVED_AS"]).json()
    # hop1: RESOLVED_AS만 → WaferR. hop2+: WENT_THROUGH/BONDED_FROM 전부 차단
    assert _node_keys(body) == {("Wafer", "LOTA|3"), ("Wafer", "W123")}
    assert {e["type"] for e in body["edges"]} == {"RESOLVED_AS"}


# ---------------------------------------------------------------------------
# 5) missing_seeds — 전부 미존재여도 404 아님
# ---------------------------------------------------------------------------

def test_trace_missing_seeds_partial(client, trace_env):
    body = _trace(client, seeds=[
        {"label": "Chip", "identity": "LOG0001"},
        {"label": "Wafer", "identity": "NO_SUCH"},
        {"label": "Ghost", "identity": "X"},
    ], depth=1).json()
    assert body["missing_seeds"] == [
        {"label": "Wafer", "identity": "NO_SUCH"},
        {"label": "Ghost", "identity": "X"},
    ]
    assert body["seed_ids"] == [trace_env["chip1"].id]
    assert ("Wafer", "LOTA|3") in _node_keys(body)


def test_trace_all_seeds_missing_returns_200_empty(client, trace_env):
    res = _trace(client, seeds=[{"label": "Ghost", "identity": "X"}], depth=2)
    assert res.status_code == 200
    body = res.json()
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["seed_ids"] == []
    assert body["missing_seeds"] == [{"label": "Ghost", "identity": "X"}]
    assert body["truncated"] is False


def test_trace_empty_seeds_400(client, trace_env):
    assert _trace(client, seeds=[], depth=1).status_code == 400


# ---------------------------------------------------------------------------
# 6) truncated — limit·하드캡 (C-7 무제한 로드 금지)
# ---------------------------------------------------------------------------

def test_trace_limit_truncates_and_drops_dangling_edges(client, trace_env):
    body = _trace(client, seeds=[{"label": "Wafer", "identity": "LOTA|3"}],
                  depth=2, limit=2).json()
    assert body["truncated"] is True
    assert len(body["nodes"]) == 2
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:   # 잘린 노드로 향하는 엣지는 응답에 없다
        assert e["from"] in node_ids and e["to"] in node_ids


def test_trace_limit_hardcap(client, trace_env, monkeypatch):
    monkeypatch.setattr(main, "GRAPH_TRACE_NODE_CAP", 3)
    body = _trace(client, seeds=[{"label": "Wafer", "identity": "LOTA|3"}],
                  depth=3, limit=999999).json()
    assert len(body["nodes"]) <= 3
    assert body["truncated"] is True


def test_trace_seeds_over_limit_are_capped(client, trace_env):
    body = _trace(client, seeds=[
        {"label": "Chip", "identity": "LOG0001"},
        {"label": "Chip", "identity": "LOG0002"},
        {"label": "Base", "identity": "B1"},
    ], depth=1, limit=2).json()
    assert body["truncated"] is True
    assert len(body["seed_ids"]) == 2
    assert len(body["nodes"]) <= 2


# ---------------------------------------------------------------------------
# 7) /graph/mapping-summary — 승격 포함 매핑 요약
# ---------------------------------------------------------------------------

SUMMARY_TABLES = {
    "trace_test_bonding": {
        "business_key": "log_id",
        "column_types": {"log_id": "string", "core_lot": "string", "core_slot": "string"},
    },
    "trace_test_core_map": {
        "business_key": "core_lot",
        "composite_key_source": ["core_lot", "core_slot"],
        "column_types": {"core_lot": "string", "core_slot": "string", "wafer_id": "string"},
    },
}

SUMMARY_MAPPING_FILE = {
    "trace_test_bonding": {
        "description": "본딩 이벤트 (trace 테스트)",
        "node": {"label": "Chip", "identity": "log_id"},
        "edges": [
            {
                "type": "BONDED_FROM",
                "target_label": "Wafer",
                "target_identity_from": ["core_lot", "core_slot"],
                "description": "chip이 잘려 나온 wafer 표기",
            }
        ],
    },
}

SUMMARY_RULES_FILE = {
    "trace_test_attribution": {
        "source_table": "trace_test_bonding",
        "derived_table": "trace_test_core_map",
        "decision_key": ["core_lot", "core_slot"],
        "target_fields": ["wafer_id"],
    }
}


@pytest.fixture()
def summary_env(db_session, tmp_path, monkeypatch):
    crud.TABLE_CONFIG.update(SUMMARY_TABLES)

    mapping_path = tmp_path / "ontology_mapping.json"
    mapping_path.write_text(json.dumps(SUMMARY_MAPPING_FILE), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(mapping_path))

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps(SUMMARY_RULES_FILE), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    return db_session


def test_mapping_summary_includes_promoted(client, summary_env):
    res = client.get("/graph/mapping-summary")
    assert res.status_code == 200
    by_table = {t["table"]: t for t in res.json()["tables"]}

    # 사용자 선언 매핑
    assert by_table["trace_test_bonding"] == {
        "table": "trace_test_bonding",
        "node_label": "Chip",
        "identity_columns": ["log_id"],
    }
    # enrichment rule 자동 승격 — 파생 테이블 노드 합성(라벨=PascalCase, identity=decision_key)
    assert by_table["trace_test_core_map"] == {
        "table": "trace_test_core_map",
        "node_label": "TraceTestCoreMap",
        "identity_columns": ["core_lot", "core_slot"],
    }
    # 매핑 없는 테이블(conftest 기본 테이블)은 미포함
    assert "raw_table_1" not in by_table
    assert "inventory_master" not in by_table


def test_mapping_summary_empty_when_no_mapping(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(tmp_path / "none.json"))
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(tmp_path / "none2.json"))
    body = client.get("/graph/mapping-summary").json()
    assert body["tables"] == []
    # 2026-07-30: 응답에 rejected/source가 추가됐다(거부된 매핑을 표면에 올림). 선언 파일이
    # 아예 없는 상태는 **거부가 아니라 부재**이므로 rejected는 비어야 한다 — 정상 상태에서
    # 비어있지 않은 사유 목록은 곧 무시당한다. 상세 검증은
    # test_ontology_reload_and_sweep.py의 §7.
    assert body["rejected"] == [] and body["rejected_count"] == 0
    assert body["source"]["exists"] is False
