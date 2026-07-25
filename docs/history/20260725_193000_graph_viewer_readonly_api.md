# 서브그래프 미니 뷰어 — read-only 그래프 조회 API 3종 신설 (Server 섹션)

- **일시:** 2026-07-25 19:30
- **주체:** Server PM (총괄 위임 — 온톨로지 서브그래프 뷰어 지시서)
- **영역:** server (main.py + tests)
- **커밋:** (미커밋 — 총괄 검수 후 커밋 예정)

## 무엇이 바뀌었나

G1 그래프(graph_nodes/graph_edges)를 확인하는 뷰어용 read-only API 3개를 웹서버
(main.py, :8080)에 신설했다. read-only이므로 워커 경유 없이 직접 조회하며, 응답
형태는 뷰어와 G2 추적 리포트가 공유할 최소형(총괄 승인된 경계 계약 추가).

- `GET /graph/stats` (`get_graph_stats`) — label별/edge_type별 카운트(GROUP BY,
  (label,identity_key)·(from,type) 인덱스 프리픽스 스캔) + `last_sync`
  (graph_sync_state.updated_at, 없으면 null).
- `GET /graph/neighbors?label=&identity=&depth=1|2&limit=200`
  (`get_graph_neighbors`) — 중심 노드에서 k-hop BFS. 방향별 2쿼리
  (idx_graph_edges_from_type / idx_graph_edges_to_type 프리픽스 룩업)만 사용,
  재귀 CTE 불사용(2회 반복). **limit = 응답 노드 총수 상한(중심 포함), 하드캡
  `GRAPH_NEIGHBOR_NODE_CAP=500`** + 홉·방향당 엣지 페치 상한
  `GRAPH_NEIGHBOR_EDGE_FETCH_CAP=2000`(수퍼노드 방어) — 무제한 로드 금지(C-7).
  상한 도달 시 `truncated=true`, 캡으로 잘린 노드로 향하는 엣지는 응답에서 제외.
  노드 배치 로드는 500개 청크 IN 조회. 응답: 노드 `{id,label,identity_key,props}`,
  엣지 `{from,to,type,source_name,updated_by,event_time}`(provenance 포함).
  depth∉{1,2}→400, 중심 미존재→404.
- `GET /graph/nodes/search?q=&label=&limit=20` (`search_graph_nodes`) — identity_key
  시작일치 ILIKE 자동완성(`_escape_like_term`으로 `%`/`_`/`\` 이스케이프,
  label 지정 시 (label,identity_key) 인덱스 스코프). limit 캡 50.

경계 계약(기존 REST/WS/셀 형태/스키마) 무변경 — 신규 read-only 경로 추가만.
라우트는 정적 catch-all(`/{file_name:path}`)보다 앞서 등록됨.

## 검증

- 신규 테스트 12건 `server/tests/test_graph_viewer_api.py` — 그래프 시스템 테이블
  직접 시딩(read-only API라 materializer 미경유): stats 빈 그래프/카운트/last_sync,
  neighbors depth1·2 확장, provenance 필드, limit 절단(+잘린 노드의 엣지 제외),
  하드캡 강제 클램프(monkeypatch), 고립 노드, 404/400, search 시작일치·label
  필터·limit·와일드카드 이스케이프·공백 질의.
- 전체 스위트 `conda run -n assy_manager python -m pytest server/tests/ -q`:
  **158 passed / 1 failed** — 실패는 기허용 `test_map_presets_api` 1건뿐.

## 잔여/미해결

- 클라이언트(뷰어 페이지 `client2/graph.html`)는 후속 위임(ui-designer) 대상.
- CODE_MAP §1.4 갱신은 doc-keeper 전담 — main.py :1848 이후 라인 앵커가 약 +164줄
  이동(신설 구간 :1851–2012). 보고서에 변경 함수 목록 기재.
