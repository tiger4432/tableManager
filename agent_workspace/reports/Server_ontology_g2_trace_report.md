# 보고서: Ontology G2 서버 — 추적(trace) API

발신: Server PM / 수신: 총괄 PM
지시서: `agent_workspace/tasks/Server_ontology_g2_trace_api_task.md`
작업 트리: 본체 main, **미커밋**(총괄 검수 후 커밋)

## 1. 결과 요약

지시서 계약 그대로 구현 완료. 계약 변경·에스컬레이션 사항 없음(§4의 해석 메모 1건만 확인 요망).

- `POST /graph/trace` — 멀티 시드 BFS 합집합, depth 1..3(기본 2), 시간 필터(NULL
  event_time 통과), edge_types 필터, 노드 하드캡 1000, missing_seeds, truncated.
- `GET /graph/mapping-summary` — 로드된 매핑 요약(enrichment RESOLVED_AS 자동 승격 포함).
- 뷰어 BFS를 공용 헬퍼로 추출 — **기존 뷰어 API 동작 불변**(뷰어 테스트 12건 무수정 green).

## 2. 변경 함수 목록 (`server/main.py`, 그래프 뷰어 구간)

| 구분 | 함수/심볼 | 내용 |
|---|---|---|
| 신설 | `_expand_graph_subgraph(db, seed_nodes, depth, node_cap, edge_types=None, time_from=None, time_to=None)` | 뷰어/추적 공용 BFS 코어. 방향별 (from,type)/(to,type) 인덱스 2쿼리, 홉·방향당 엣지 페치 캡 2000, 노드 500청크 IN 로드, 캡 절단 시 dangling 엣지 제외 — 기존 뷰어 루프를 그대로 이동 후 멀티 시드·타입 필터·시간 필터만 추가 |
| 신설 | `_serialize_graph_nodes(nodes)` | 노드 형태 계약 `{id,label,identity_key,props}` 직렬화 공용화 |
| 신설 | `_parse_trace_time(value, field)` | ISO 8601 파싱(`Z`→`+00:00` 허용), 실패 시 **400**(계약: 검증 실패 400) |
| 신설 | `class GraphTraceSeed` / `class GraphTraceRequest` | pydantic 요청 스키마 (time_from/to는 `Optional[str]` — §4 참조) |
| 신설 | `post_graph_trace(req, db)` — `POST /graph/trace` | 시드 순서보존 dedup → label 그룹별 (label,identity_key) 인덱스 조회(500 청킹) → missing_seeds 분리 → 시드가 limit 초과 시 시드부터 절단(truncated) → 공용 BFS |
| 신설 | `get_graph_mapping_summary()` — `GET /graph/mapping-summary` | `ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)` — materializer(`_load_graph_mappings`)와 동일 신호원, 요청 시 디스크 로드(무중단 반영) |
| 수정 | `get_graph_neighbors` | BFS 본문을 `_expand_graph_subgraph(db, [center], depth, limit)` 호출로 치환 — 로직·응답 동일(순수 리팩터) |
| 상수 | `GRAPH_TRACE_NODE_CAP=1000` / `GRAPH_TRACE_DEPTH_CAP=3` / `GRAPH_TRACE_DEFAULT_LIMIT=500` | 지시서 수치 고정 |

신규 테스트: `server/tests/test_graph_trace_api.py` (19건). 그 외 파일 무변경.

## 3. 검증

- 신규 19건: 멀티 시드 합집합·seed_ids 순서·시드 dedup / depth 기본 2·depth 3 도달·0·4→400 /
  시간 필터(NULL 통과, 창 밖 배제, time_from·time_to 단측, 형식 오류→400) /
  edge_types(단일 홉 + 매 홉 적용) / missing_seeds(부분·전부 미존재 200 빈 nodes) /
  truncated(limit 절단+dangling 엣지 부재, 하드캡 monkeypatch, 시드 초과 절단) /
  빈 seeds→400 / mapping-summary(사용자 매핑 + 승격 합성 노드 `TraceTestCoreMap`
  identity=decision_key, 미매핑 테이블 미포함, 매핑 전무 시 `{"tables": []}`).
- 테스트 테이블명 `trace_test_*` 고유 접두 사용(교훈 파일 — 사용자 config 동명 충돌 방지).
- 전체 스위트: `conda run -n assy_manager python -m pytest server/tests/ -q` →
  **177 passed / 1 failed** — 실패는 기허용 `test_map_presets_api` 1건뿐(열린문제 #4).
- 경계 계약 영향: 기존 REST/WS/셀 형태/스키마 무변경. CRUD/공용 시그니처 변경 없음 →
  전수 Grep 연쇄 갱신 해당 없음(`_expand_graph_subgraph`는 신규 내부 헬퍼, main.py 전용).

## 4. 계약 해석 메모 (확인 요망 — 변경 아님)

1. **400 vs 422**: "POST 본문은 pydantic 스키마, 검증 실패 400" — 의미 검증(빈 seeds,
   depth 범위, ISO 형식)은 전부 400으로 구현. 단 **구조 위반**(seeds 필드 누락,
   depth에 비정수 등)은 FastAPI 표준인 422로 남는다. 전역 422→400 변환은 타 엔드포인트
   계약에 파급되어 하지 않았다. 클라이언트가 422도 400과 동일 취급하면 무영향.
2. **edge_types 빈 배열 `[]`**: "지정 시 해당 타입만 확장" — 빈 배열은 미지정(무필터)과
   동일 취급으로 구현(전면 차단이 필요하면 클라이언트가 요청 자체를 안 보내는 게 자연스러움).
3. **시드 수 > limit**: 계약에 미정의 — 하드캡 우선 원칙(C-7)에 따라 시드부터 절단하고
   `truncated=true`. `seed_ids`는 응답에 포함된 시드만.
4. **타임존**: time_from/to는 오프셋 포함 ISO 수용, 비교는 DB 저장값 기준.
   naive/aware 혼용 정책은 G2.5 직렬화 설계와 함께 확정 권장.

## 5. 문서/인계

- 히스토리: `docs/history/20260725_203000_ontology_g2_trace_api.md` + `gen_index.py` 재생성(191건).
- CODE_MAP §1.4: 뷰어 3종 + 신규 2종 라우트가 미등재 상태이며 그래프 구간 라인 앵커가
  약 +230줄 이동 — **doc-keeper 위임 권장**(뷰어 작업 때와 동일 관행).
- PROJECT_STATUS·스펙 파일은 규칙대로 미수정(총괄 일괄).
- 다음 단계: 클라이언트 추적 리포트 UI(그리드 선택→시드 변환에 mapping-summary 사용) 합류 검증,
  G2.5 서브그래프 직렬화.

## 6. 교훈 제안 (server-pm.md 반영은 총괄 검수 후)

- **함정**: FastAPI에서 "검증 실패 400" 계약을 pydantic 필드 제약으로 구현하면 422가
  나가 계약 위반이 된다. **올바른 방법**: 형태는 pydantic으로 받되(구조 오류만 422)
  의미 검증(범위·형식·빈 목록)은 핸들러에서 명시적 `HTTPException(400)`으로 —
  시간 등 파싱 실패를 400으로 줘야 하는 필드는 `Optional[str]`로 받아 직접 파싱.
