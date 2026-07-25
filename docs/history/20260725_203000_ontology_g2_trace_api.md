# Ontology G2 — 추적(trace) API + 매핑 요약 API 신설 (Server 섹션)

- **일시:** 2026-07-25 20:30
- **주체:** Server PM (총괄 위임 — G2 추적 API 지시서)
- **영역:** server (main.py + tests)
- **커밋:** (미커밋 — 총괄 검수 후 커밋 예정)

## 무엇이 바뀌었나

킬러 유스케이스("불량 wafer들 선택 → 연관 전체 추적")의 서버 절반. 뷰어 API(c63b881)의
방향별 인덱스 BFS를 공용 헬퍼로 추출·일반화하고, 그 위에 추적 API 2종을 얹었다.
계약은 총괄 고정(클라이언트 병렬 개발 중) — 그대로 구현, 임의 변경 없음.

- **공용 BFS 코어 추출** `_expand_graph_subgraph(db, seed_nodes, depth, node_cap,
  edge_types?, time_from?, time_to?)` — 기존 `get_graph_neighbors`의 루프를 그대로
  옮기고(방향별 2쿼리 인덱스 룩업, 엣지 페치 캡 2000, 노드 500청크 IN 로드, 절단 시
  잘린 노드의 엣지 제외) 3가지를 일반화: ① 멀티 시드(frontier 초기값) ② `edge_types`
  타입 필터(빈 리스트/None은 무필터) ③ `event_time` 범위 필터 — **NULL event_time
  엣지는 구조 엣지로 항상 통과**(`OR event_time IS NULL` — 경계 계약).
  `_serialize_graph_nodes` 노드 직렬화도 공용화. **뷰어 API 동작 불변**(기존 뷰어
  테스트 12건 무수정 통과).
- **`POST /graph/trace`** (`post_graph_trace`) — pydantic `GraphTraceRequest`
  `{seeds:[{label,identity}], depth=2(1..3), time_from?, time_to?, edge_types?,
  limit=500}`. 시드는 요청 순서 보존 dedup 후 label 그룹별 (label,identity_key)
  인덱스 조회(500 청킹). 미존재 시드는 무시하고 `missing_seeds`로 보고, **전부
  미존재여도 200 + 빈 nodes**(404 아님). 노드 하드캡 `GRAPH_TRACE_NODE_CAP=1000`,
  depth 하드캡 3 — 시드 수가 limit을 넘으면 시드부터 절단(truncated). 검증 실패
  400: 빈 seeds / depth 범위 밖 / ISO 시간 형식 오류(시간은 문자열로 받아
  `_parse_trace_time`에서 파싱 — pydantic 422가 아닌 계약대로 400을 주기 위함).
  응답 `{nodes, edges, seed_ids, missing_seeds, truncated}` — 노드/엣지 형태는
  뷰어와 동일 계약.
- **`GET /graph/mapping-summary`** (`get_graph_mapping_summary`) — 현재 로드된
  온톨로지 매핑 요약 `{tables:[{table, node_label, identity_columns}]}`.
  materializer와 같은 로더(`ontology_config.load_ontology_mappings(known_tables=
  crud.TABLE_CONFIG)`)를 태워 **enrichment RESOLVED_AS 자동 승격 포함** 동일
  신호원 보장. 파일이 작으므로 요청 시마다 디스크 로드(무중단 반영 — enrichment
  라우트 패턴). 매핑 없는 테이블 미포함.

경계 계약: 기존 REST/WS/셀 형태/스키마 무변경 — 신규 경로 2개는 지시서의 총괄
고정 계약 그대로.

## 검증

- 신규 테스트 19건 `server/tests/test_graph_trace_api.py` — 멀티 시드 합집합·시드
  dedup, depth 기본값 2·depth3 도달·범위 밖 400, 시간 필터(NULL 통과·창 밖 배제·
  단측 경계·형식 오류 400), edge_types 필터(홉마다 적용 포함), missing_seeds
  (부분/전부 미존재 200), truncated(limit 절단+dangling 엣지 제외·하드캡
  monkeypatch·시드 초과 절단), 빈 seeds 400, mapping-summary(사용자 매핑 +
  enrichment 승격 합성 노드 `TraceTestCoreMap`·미매핑 테이블 미포함·매핑 전무 시
  빈 목록). 테이블명은 `trace_test_*` 고유 접두(교훈 파일 — 사용자 config 충돌 방지).
- 전체 스위트 `conda run -n assy_manager python -m pytest server/tests/ -q`:
  **177 passed / 1 failed** — 실패는 기허용 `test_map_presets_api` 1건뿐
  (PROJECT_STATUS 열린문제 #4에 기록된 기존 실패).

## 잔여/미해결

- 추적 리포트 UI(그리드 선택 → 시드 변환 → /graph/trace)는 클라이언트 병렬 트랙.
- CODE_MAP §1.4 갱신은 doc-keeper 전담 — main.py 그래프 구간이 공용 헬퍼+신규
  라우트로 약 +230줄 이동(뷰어 구간 :1849 이후 전체 재앵커 필요).
- time_from/to의 타임존 해석: 파서는 ISO 오프셋(`Z` 포함)을 수용하나 비교는 DB에
  저장된 event_time 값 기준 — naive/aware 혼용 데이터 정책은 G2.5 직렬화 설계 시
  함께 확정 권장(현재 데모 데이터는 naive).
