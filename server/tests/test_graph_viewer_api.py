"""[Ontology 뷰어] read-only 그래프 조회 API 검증 (서브그래프 미니 뷰어 지시서 — Server 섹션).

검증 범위:
- GET /graph/stats — 빈 그래프 / label·edge_type 카운트 / last_sync(graph_sync_state)
- GET /graph/neighbors — depth 1·2 이웃 확장, 엣지 provenance(source_name/updated_by/event_time),
  limit 캡·하드캡(truncated=True, 잘린 노드의 엣지 제외 — C-7 무제한 로드 금지),
  404(미존재 노드)·400(잘못된 depth)
- GET /graph/nodes/search — 시작일치·label 필터·limit 캡·LIKE 메타문자 이스케이프

[격리] 그래프 시스템 테이블(graph_nodes/edges/sync_state)에 직접 시딩 —
API는 read-only이므로 materializer 경유가 불필요하다.
"""
import pytest

# ⚰️ [R-2026-08-14-H] 이 파일이 검증하던 세 라우트는 은퇴했다.
# `/graph/stats`·`/graph/neighbors`·`/graph/nodes/search`는 이제 첫 줄에서
# `_graph_branch_retired()`(410)를 raise하고, 이 파일이 시딩하던
# `graph_nodes`/`graph_edges`/`graph_sync_state`는 DROP 대상이다.
#
# 🔴 왜 «삭제»가 아니라 스킵인가. 이 테스트들이 서술하는 동작과 그 동작을 담은
# 라우트 몸통은 «같은 변경»에서 죽어야 한다 — 판정 ④(구 그래프 전용 코드 경로
# 제거)가 둘 다 소유한다. 지금 테스트만 지우면 아직 저장소에 살아 있는 600여 줄의
# 라우트 코드가 «아무도 서술하지 않는 코드»로 남고, 다음 라운드가 그걸 지울 때
# 무엇을 잃는지 읽을 곳이 없어진다.
# 새 계약(거절의 모양)은 `test_graph_branch_retired.py`가 단언한다.
pytest.skip(
    "R-2026-08-14-H retired the old graph branch; these routes now refuse with "
    "410 old_graph_branch_retired. Removed together with the route bodies in "
    "ruling item 4. New contract: test_graph_branch_retired.py",
    allow_module_level=True,
)

import datetime  # noqa: E402

import main  # noqa: E402
from database.models import GraphNode, GraphEdge, GraphSyncState  # noqa: E402

EVENT_TIME = datetime.datetime(2026, 7, 25, 10, 0, 0)


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
def graph_env(db_session):
    """데모 형태 미니 토폴로지:

    Chip1 ─BONDED_FROM→ WaferP(LOTA|3) ─RESOLVED_AS(user)→ WaferR(W123) ─WENT_THROUGH→ Step1
    Chip2 ─BONDED_FROM→ WaferP
    Chip1 ─PLACED_ON→ Base1
    """
    db = db_session
    chip1 = _add_node(db, "Chip", "LOG0001", {"cx": 1})
    chip2 = _add_node(db, "Chip", "LOG0002", {"cx": 2})
    wafer_p = _add_node(db, "Wafer", "LOTA|3", {"chip_count": 2})
    wafer_r = _add_node(db, "Wafer", "W123")
    base1 = _add_node(db, "Base", "B1")
    step1 = _add_node(db, "Step", "STEP1")

    _add_edge(db, chip1, wafer_p, "BONDED_FROM")
    _add_edge(db, chip2, wafer_p, "BONDED_FROM")
    _add_edge(db, chip1, base1, "PLACED_ON")
    _add_edge(db, wafer_p, wafer_r, "RESOLVED_AS",
              source_name="user", updated_by="tester", event_time=EVENT_TIME)
    _add_edge(db, wafer_r, step1, "WENT_THROUGH")
    db.commit()
    return db


def _node_keys(body):
    return {(n["label"], n["identity_key"]) for n in body["nodes"]}


def _edge_types(body):
    return sorted(e["type"] for e in body["edges"])


# ---------------------------------------------------------------------------
# 1) /graph/stats
# ---------------------------------------------------------------------------

def test_stats_empty_graph(client):
    res = client.get("/graph/stats")
    assert res.status_code == 200
    body = res.json()
    assert body == {"labels": [], "edge_types": [], "last_sync": None}


def test_stats_counts_and_last_sync(client, graph_env):
    graph_env.add(GraphSyncState(id=1, last_outbox_id=42))
    graph_env.commit()

    body = client.get("/graph/stats").json()
    labels = {r["label"]: r["count"] for r in body["labels"]}
    assert labels == {"Chip": 2, "Wafer": 2, "Base": 1, "Step": 1}
    types = {r["type"]: r["count"] for r in body["edge_types"]}
    assert types == {"BONDED_FROM": 2, "PLACED_ON": 1, "RESOLVED_AS": 1, "WENT_THROUGH": 1}
    assert body["last_sync"] is not None


# ---------------------------------------------------------------------------
# 2) /graph/neighbors
# ---------------------------------------------------------------------------

def test_neighbors_depth1(client, graph_env):
    res = client.get("/graph/neighbors", params={
        "label": "Wafer", "identity": "LOTA|3", "depth": 1,
    })
    assert res.status_code == 200
    body = res.json()
    # 중심 + 직접 이웃(Chip×2, WaferR) — 2-hop인 Base/Step은 제외
    assert _node_keys(body) == {
        ("Wafer", "LOTA|3"), ("Chip", "LOG0001"), ("Chip", "LOG0002"), ("Wafer", "W123"),
    }
    assert _edge_types(body) == ["BONDED_FROM", "BONDED_FROM", "RESOLVED_AS"]
    assert body["truncated"] is False

    # 노드 형태 계약: {id, label, identity_key, props}
    center = next(n for n in body["nodes"] if n["identity_key"] == "LOTA|3")
    assert center["props"] == {"chip_count": 2}

    # 엣지 provenance 계약: source_name / updated_by / event_time
    resolved = next(e for e in body["edges"] if e["type"] == "RESOLVED_AS")
    assert resolved["source_name"] == "user"
    assert resolved["updated_by"] == "tester"
    assert resolved["event_time"].startswith("2026-07-25T10:00")
    bonded = next(e for e in body["edges"] if e["type"] == "BONDED_FROM")
    assert bonded["source_name"] == "pipeline_parser"
    assert bonded["updated_by"] is None
    assert bonded["event_time"] is None


def test_neighbors_depth2_full_topology(client, graph_env):
    body = client.get("/graph/neighbors", params={
        "label": "Wafer", "identity": "LOTA|3", "depth": 2,
    }).json()
    assert len(body["nodes"]) == 6                      # 전 토폴로지 도달
    assert _edge_types(body) == [
        "BONDED_FROM", "BONDED_FROM", "PLACED_ON", "RESOLVED_AS", "WENT_THROUGH",
    ]
    assert body["truncated"] is False


def test_neighbors_limit_truncates_and_drops_dangling_edges(client, graph_env):
    body = client.get("/graph/neighbors", params={
        "label": "Wafer", "identity": "LOTA|3", "depth": 2, "limit": 2,
    }).json()
    assert body["truncated"] is True
    assert len(body["nodes"]) == 2                      # 중심 + 1 (limit=노드 총수 상한)
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:                             # 잘린 노드로 향하는 엣지는 응답에 없다
        assert e["from"] in node_ids and e["to"] in node_ids


def test_neighbors_limit_hardcap(client, graph_env, monkeypatch):
    """limit=999999 같은 과대 요청도 하드캡으로 강제 클램프된다 (C-7 무제한 로드 금지)."""
    monkeypatch.setattr(main, "GRAPH_NEIGHBOR_NODE_CAP", 3)
    body = client.get("/graph/neighbors", params={
        "label": "Wafer", "identity": "LOTA|3", "depth": 2, "limit": 999999,
    }).json()
    assert len(body["nodes"]) <= 3
    assert body["truncated"] is True


def test_neighbors_center_only_when_isolated(client, db_session):
    _add_node(db_session, "Chip", "LONELY")
    db_session.commit()
    body = client.get("/graph/neighbors", params={
        "label": "Chip", "identity": "LONELY", "depth": 2,
    }).json()
    assert _node_keys(body) == {("Chip", "LONELY")}
    assert body["edges"] == []
    assert body["truncated"] is False


def test_neighbors_not_found_and_bad_depth(client, graph_env):
    res = client.get("/graph/neighbors", params={
        "label": "Wafer", "identity": "NO_SUCH", "depth": 1,
    })
    assert res.status_code == 404

    res = client.get("/graph/neighbors", params={
        "label": "Wafer", "identity": "LOTA|3", "depth": 3,
    })
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# 3) /graph/nodes/search
# ---------------------------------------------------------------------------

def test_search_prefix_match(client, graph_env):
    body = client.get("/graph/nodes/search", params={"q": "LOT"}).json()
    assert [(r["label"], r["identity_key"]) for r in body["results"]] == [("Wafer", "LOTA|3")]

    body = client.get("/graph/nodes/search", params={"q": "LOG"}).json()
    assert {r["identity_key"] for r in body["results"]} == {"LOG0001", "LOG0002"}


def test_search_label_filter_and_limit(client, graph_env):
    body = client.get("/graph/nodes/search", params={"q": "W", "label": "Wafer"}).json()
    assert [r["identity_key"] for r in body["results"]] == ["W123"]

    # label 불일치 → 빈 결과 (시작일치는 label 스코프 안에서만)
    body = client.get("/graph/nodes/search", params={"q": "W123", "label": "Chip"}).json()
    assert body["results"] == []

    body = client.get("/graph/nodes/search", params={"q": "LOG", "limit": 1}).json()
    assert len(body["results"]) == 1


def test_search_escapes_like_wildcards(client, graph_env):
    # '%'가 와일드카드로 새면 전 노드가 매치된다 — 리터럴 취급 확인.
    # [F3] 이제 LIKE 자체가 없다(바이트 순서 범위 비교) — 이스케이프할 메타문자가
    # 없는 것이 리터럴성의 근거다. 여기엔 파이썬 측 재검사가 없으므로 이 테스트는
    # SQL 술어를 직접 겨눈다.
    body = client.get("/graph/nodes/search", params={"q": "%"}).json()
    assert body["results"] == []
    body = client.get("/graph/nodes/search", params={"q": "_"}).json()
    assert body["results"] == []


def test_search_prefix_stays_case_insensitive(client, graph_env):
    """[F3] `ILIKE 'q%'` → 바이트 순서 범위로 교체하면서 **대소문자 무시 의미론은
    그대로**여야 한다 (저장 키는 전부 대문자다 — 소문자 입력이 안 먹으면 자동완성이
    죽는다). 범위를 `lower()` 없이 걸면 'lot' >= 'LOT'가 거짓이라 이 테스트가 깨진다.
    """
    body = client.get("/graph/nodes/search", params={"q": "lot"}).json()
    assert [(r["label"], r["identity_key"]) for r in body["results"]] == [("Wafer", "LOTA|3")]

    body = client.get("/graph/nodes/search", params={"q": "log000"}).json()
    assert {r["identity_key"] for r in body["results"]} == {"LOG0001", "LOG0002"}


def test_search_never_degrades_to_everything_from_here_on(client, db_session, graph_env):
    """[F3] 이 라우트에는 파이썬 재검사가 **없다** — 술어가 곧 답이다. 그래서
    `prefix_conditions`가 상한을 못 내면 `>= q` 하나만 남고, 질의는 그 지점부터
    끝까지 전부를 돌려준다. 라이브에서 `q='L\\U0010FFFF'`가 MEAS·PHOTO… 를
    반환했다(옛 ILIKE는 0행). 상한 계산은 마지막 문자에서 포기하지 말고
    **자리올림**해야 한다.

    역주입: `prefix_upper_bound`의 carry 루프를 한 글자 증가로 되돌리면 첫 단언이
    깨진다 — 빈 목록이 아니라 그 지점 이후 전 노드가 온다.
    """
    hit = _add_node(db_session, "Wafer", "L\U0010ffffZZ")
    db_session.commit()

    body = client.get("/graph/nodes/search", params={"q": "M\U0010ffff"}).json()
    assert body["results"] == [], "접두로 시작하는 노드가 없으면 빈 목록이어야 한다"

    # 그리고 자리올림한 상한이 진짜 일치까지 잘라내면 안 된다.
    body = client.get("/graph/nodes/search", params={"q": "L\U0010ffff"}).json()
    assert [r["identity_key"] for r in body["results"]] == [hit.identity_key]


def test_search_blank_query_returns_empty(client, graph_env):
    # 빈 q + label 없음 → 전 테이블 덤프 금지 (기존 계약 유지)
    body = client.get("/graph/nodes/search", params={"q": "   "}).json()
    assert body["results"] == []


# ---------------------------------------------------------------------------
# 3-1) /graph/nodes/search — 빈 q + label 리스팅 & offset 페이지네이션
#      (Stats "Nodes by Label" 카드 → 노드 리스트 테이블)
# ---------------------------------------------------------------------------

def test_search_empty_query_with_label_lists_all(client, graph_env):
    body = client.get("/graph/nodes/search", params={"q": "", "label": "Chip"}).json()
    assert [r["identity_key"] for r in body["results"]] == ["LOG0001", "LOG0002"]

    # 공백-only q도 리스팅으로 동작 (strip 규율 동일)
    body = client.get("/graph/nodes/search", params={"q": "   ", "label": "Wafer"}).json()
    assert [r["identity_key"] for r in body["results"]] == ["LOTA|3", "W123"]

    # q 파라미터 생략도 허용 (신규 기본값 q="")
    body = client.get("/graph/nodes/search", params={"label": "Base"}).json()
    assert [r["identity_key"] for r in body["results"]] == ["B1"]


def test_search_label_list_offset_pagination(client, graph_env):
    # identity 오름차순 안정 정렬 전제의 offset 페이지네이션
    page1 = client.get("/graph/nodes/search",
                       params={"q": "", "label": "Chip", "limit": 1, "offset": 0}).json()
    page2 = client.get("/graph/nodes/search",
                       params={"q": "", "label": "Chip", "limit": 1, "offset": 1}).json()
    page3 = client.get("/graph/nodes/search",
                       params={"q": "", "label": "Chip", "limit": 1, "offset": 2}).json()
    assert [r["identity_key"] for r in page1["results"]] == ["LOG0001"]
    assert [r["identity_key"] for r in page2["results"]] == ["LOG0002"]
    assert page3["results"] == []

    # 음수 offset은 0으로 클램프
    body = client.get("/graph/nodes/search",
                      params={"q": "", "label": "Chip", "limit": 1, "offset": -5}).json()
    assert [r["identity_key"] for r in body["results"]] == ["LOG0001"]


def test_search_prefix_offset_pagination(client, graph_env):
    # offset은 프리픽스 검색 모드에서도 동작
    body = client.get("/graph/nodes/search",
                      params={"q": "LOG", "limit": 1, "offset": 1}).json()
    assert [r["identity_key"] for r in body["results"]] == ["LOG0002"]


def test_search_label_list_limit_hardcap(client, graph_env, monkeypatch):
    """리스팅 모드도 하드캡 클램프 (C-7 무제한 로드 금지)."""
    monkeypatch.setattr(main, "GRAPH_LABEL_LIST_LIMIT_CAP", 1)
    body = client.get("/graph/nodes/search",
                      params={"q": "", "label": "Chip", "limit": 999999}).json()
    assert len(body["results"]) == 1
