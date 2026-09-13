# 보고서: 서브그래프 미니 뷰어 — Server 섹션 (read-only 그래프 조회 API 3종)

- **발신:** Server PM → 총괄 PM
- **일시:** 2026-07-25
- **지시서:** `agent_workspace/tasks/Ontology_subgraph_viewer_task.md` (Server 섹션)
- **작업 트리:** 본체 main (HEAD d130c65 기준), **미커밋** — 총괄 검수 후 커밋

## 1. 변경 요약

웹서버(main.py, :8080)에 read-only 그래프 조회 API 3개 신설. graph_nodes/graph_edges를
직접 조회(워커 미경유), 응답은 뷰어+G2 공유용 최소형. 기존 경계 계약 무변경 —
승인된 신규 경로 추가만.

### 변경 함수 목록 (doc-keeper CODE_MAP 갱신용)

| 파일 | 함수/상수 | 라인 | 내용 |
|---|---|---|---|
| `server/main.py` | `GRAPH_NEIGHBOR_NODE_CAP = 500` | :1853 | neighbors limit 하드캡(C-7 무제한 로드 금지) |
| `server/main.py` | `GRAPH_NEIGHBOR_EDGE_FETCH_CAP = 2000` | :1854 | 홉·방향당 엣지 페치 상한(수퍼노드 방어) |
| `server/main.py` | `GRAPH_SEARCH_LIMIT_CAP = 50` | :1855 | search limit 캡 |
| `server/main.py` | `_escape_like_term(term) -> str` | :1858 | LIKE 메타문자(`%`/`_`/`\`) 이스케이프 (escape='\\'와 짝) |
| `server/main.py` | `GET /graph/stats` → `get_graph_stats(db)` | :1863 | label/edge_type GROUP BY 카운트 + `last_sync`(graph_sync_state.updated_at, 없으면 null) |
| `server/main.py` | `GET /graph/neighbors` → `get_graph_neighbors(label, identity, depth=1, limit=200, db)` | :1888 | k-hop BFS(depth 1\|2). (from,type)/(to,type) 인덱스 프리픽스 룩업 방향별 2쿼리, 재귀 CTE 불사용. limit=응답 노드 총수 상한(중심 포함)·하드캡 클램프. 상한 도달 시 `truncated=true` + 잘린 노드의 엣지 응답 제외. 노드 로드 500개 청크 IN. 400(depth 위반)/404(중심 미존재) |
| `server/main.py` | `GET /graph/nodes/search` → `search_graph_nodes(q, label=None, limit=20, db)` | :1984 | identity_key 시작일치 ILIKE 자동완성, label 필터 시 (label,identity_key) 인덱스 스코프, 공백 질의는 빈 결과 |
| `server/tests/test_graph_viewer_api.py` | (신규 파일, 12 테스트) | — | 아래 §3 |

**주의(라인 앵커 이동):** main.py :1848 이후 전체가 약 **+164줄** 이동
(신설 구간 :1851–2012). CODE_MAP §1.1(load_maps_config 등)·§1.3·§1.4의 :1851 이후
앵커 재조정 필요 — CODE_MAP은 규율상 직접 수정하지 않았음(doc-keeper 전담).

### 응답 계약 (확정 구현형)

```
GET /graph/stats
→ {labels: [{label, count}], edge_types: [{type, count}], last_sync: iso|null}

GET /graph/neighbors?label=&identity=&depth=1|2&limit=200
→ {nodes: [{id, label, identity_key, props}],
   edges: [{from, to, type, source_name, updated_by, event_time}],
   truncated: bool}

GET /graph/nodes/search?q=&label=&limit=20
→ {results: [{id, label, identity_key}]}
```

설계 판단(최소형 유지): edges에 `props`는 미포함(계약 명시 필드만), 중심 노드 id도
별도 필드 없음 — 뷰어는 요청한 (label, identity)와 일치하는 노드로 중심을 식별하면
된다. 라우트는 정적 catch-all(`/{file_name:path}`)보다 앞서 등록됨(FastAPI 등록순 매칭).

## 2. 확장성 근거 (1,000만 행 기준)

- **neighbors**: 전 쿼리가 인덱스 경로 — 중심 조회 (label,identity_key) UNIQUE,
  엣지 확장 idx_graph_edges_from_type/to_type 프리픽스, 노드 로드 PK IN(500 청크).
  홉·방향당 `.limit(2000)` + 노드 하드캡 500 → 최악 페이로드 유계. JSON 풀스캔·OFFSET 없음.
- **stats**: label/type GROUP BY는 각각 (label,identity_key)·(from_node,type) 인덱스
  프리픽스로 커버 가능. 뷰어 첫 화면용 저빈도 호출 — 초대형 그래프에서 count가
  느려지면 G2에서 캐시 검토(현 단계 과설계 배제).
- **search**: LIMIT 강제(캡 50) + 와일드카드 이스케이프로 `%` 단독 질의 같은
  전량 매치 시도 차단. 단, PG에서 ILIKE 프리픽스는 btree를 못 타는 한계 있음(§4).

## 3. 검증

- **신규 12 테스트** `server/tests/test_graph_viewer_api.py` (그래프 시스템 테이블
  직접 시딩 — read-only라 materializer 경유 불필요):
  stats 빈 그래프 / 카운트·last_sync / neighbors depth1(이웃 정확 집합 + 노드·엣지
  형태 계약 + provenance: user·tester·event_time) / depth2 전 토폴로지 / limit=2
  절단(truncated + 잘린 노드행 엣지 부재) / 하드캡 monkeypatch 강제 클램프 /
  고립 노드 / 404·400 / search 시작일치·label 필터·limit·`%`·`_` 이스케이프·공백 질의.
- **전체 스위트**: `conda run -n assy_manager python -m pytest server/tests/ -q`
  → **158 passed / 1 failed** (실패는 기허용 `test_map_presets_api` 1건뿐 — 이슈 #4).

## 4. 미해결 / 다음 단계

1. **Client 후속(ui-designer)**: `client2/graph.html` + `src/graph_viewer.js` —
   본 API 3종만으로 구현 가능(추가 서버 작업 불요).
2. **search 인덱스 한계(관찰)**: PG에서 `ILIKE 'X%'`는 일반 btree 미사용. 자동완성이
   실측에서 느리면 `text_pattern_ops`(대소문자 구분 LIKE 전환) 또는 pg_trgm GIN을
   G2에서 검토 — 현재는 LIMIT 캡으로 유계라 뷰어 용도 충분 판단.
3. **stats count 캐시**: 그래프가 수백만 노드로 성장하면 GROUP BY count 캐시 검토(G2).
4. **doc-keeper 위임**: CODE_MAP §1 앵커 +164줄 이동 반영 + 본 표의 신규 라우트 등재.
   (backend.md §2 라우트 표에는 1행 추가 완료, history 기록·인덱스 재생성 완료.)

## 5. 교훈 제안 (총괄 검수 후 반영)

- 제안 없음 — 기존 교훈(conda run, 테스트 테이블 격리)으로 충분했고 신규 함정 미발견.
  (참고: main.py 신규 라우트는 반드시 catch-all `/{file_name:path}` **앞**에 등록해야
  한다는 점은 함정 후보이나, 이번엔 기존 라우트 블록 중간 삽입으로 자연 회피 — 총괄
  판단에 맡김.)
