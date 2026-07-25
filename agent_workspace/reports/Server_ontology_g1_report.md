# 보고서: 온톨로지 G1 — 그래프 기반 구축 (QA GO-WITH-FIXES 수정 완료)

발신: Server PM / 수신: 총괄 PM
브랜치: `worktree-agent-a859dc3b96d4212cc` — 1차 `6da2276` + QA 수정 커밋(본 보고서 포함). main 병합 금지 준수.
스펙: `docs/spec/ONTOLOGY_GRAPH_SPEC.md` §2·§3·§5·§7.5·§4

## 0. QA 재지시 수정 결과 (판정: GO-WITH-FIXES → 전 항목 반영)

| 항목 | 수정 | 검증 |
|---|---|---|
| **[높음-1] 엣지 provenance 위조** | 엣지 소스를 이벤트 source_name이 아닌 **셀 레이어 진실**로 통일: `attach_col_sources`(증분·resync 공용 단일 지점)가 target_identity_from 컬럼들의 CellSource winner를 로드하고, `extract_graph_items`가 그중 **최저 서열(보수적)**을 날인. 무관 컬럼 user 편집이 user를 위조 날인하는 경로 제거, 두 경로가 키 필드까지 동일 레코드 산출 | `test_h1_no_user_forgery_on_unrelated_edit`(무관 컬럼 user 편집 → 엣지 수 불변·pipeline_parser 유지), `test_h1_multi_column_conservative_and_retarget`(일부 교정→보수적 유지, 전부 교정→user), `test_h1_path_equivalence_incremental_vs_resync`(증분 vs resync 엣지 서명 집합 완전 일치) |
| **[높음-2] 재교정 구 엣지 잔존** | `_retarget_stale_edges`: 같은 원본 로우(source_row_ref)가 과거에 주장했으나 이번 산출 타깃 집합에 없는 (from_node, type) 엣지를 **삭제 후 UPSERT**. 신규 인덱스 `idx_graph_edges_row_ref`로 인덱스 룩업 + id 청크 삭제. **주의(설계 편차)**: QA 문안의 (from,type,source_name) 매칭 키에서 source_name을 제외 — 사용자 교정은 winner 소스도 함께 바꾸므로(pipeline→user) source를 키에 넣으면 구 소스 엣지가 잔존한다. 로우=주장 단위로 스코핑하면 다른 로우의 엣지는 구조적으로 안전 | E2E 5단계(W123→W124 재교정 → RESOLVED_AS 1개·구 엣지 소멸), `test_h2_retarget_preserves_other_rows`(같은 from 노드 공유하는 타 로우 엣지 보존), `test_h1_multi_column_conservative_and_retarget`(식별 컬럼 교정 시 구 타깃 정리) |
| **[중간-3] 이벤트 루프 기아** | 배치 처리 본체를 `_run_one_batch`(동기)로 추출해 `asyncio.to_thread`로 격리 — 백로그 연속 소진 중에도 /sync HTTP 서빙 루프 자유 | 전체 스위트 green(기능 회귀 없음). 루프 내 이벤트 루프상 동기 DB 호출 0건 |
| **[낮음-4] rollback 신호원 정합** | `crud.get_ontology_mapping`이 v2 검증+`synthesize_enrichment_mappings` 적용 결과를 캐시(v1 키는 원본 보존 폴백) — materializer와 같은 매핑을 봄 | `test_check_needs_rollback_v2_with_promotion`(승격 RESOLVED_AS의 target 컬럼 wafer_id 변경이 신호에 잡힘) |
| **[낮음-5] row_ids 슬라이스** | `resync_table` row_ids 모드: 정렬·중복제거 후 청크 크기 슬라이스 단위 IN 조회(청크마다 전량 IN 반복 제거) | `test_resync_partial_row_ids_sliced`(5 id, chunk 2 → chunks==3) |
| **[낮음-6] 서열 단일 원천** | materializer의 하드코딩 `_SOURCE_PRIORITY` 제거 → `crud.resolve_priority_map`/`get_source_priority` 신설(테이블별 source_priority 커스텀 포함, compute_priority_value와 공유). `SOURCE_PRIORITY`에 `chain_ingestion: 4` 등재(기존 4대 소스와 상대 서열 불변 4>3 — 표시 레이어링 결과 유지, 미등재 소스 대비만 승격. 이견 시 지적 바람) | `test_source_priority_single_origin`(chain_ingestion=4, 커스텀 맵 반영) |
| **[낮음-7] identity 이스케이프** | `compose_identity`: `"\\"→"\\\\"`, `"|"→"\\|"` 이스케이프 — ("A\|B","C")≠("A","B\|C"). float 정수 안정화는 `_normalize_identity_part`로 일원화 | `test_compose_identity_normalization` 경계 케이스 확장(파이프/백슬래시/혼합, 3.0≡"3", 3.5) |

전체 스위트: **144 passed / 1 failed(기허용 test_map_presets_api)**.

## 1. 산출물 요약 (1차분 — 유지)

| 지시 항목 | 상태 |
|---|---|
| PG 엣지 스토어(graph_nodes/edges + 인덱스 규율, #7 패턴 DDL) | ✅ |
| ontology_mapping.json v2 로더/검증(+공간 속성, 핫리로드, RESOLVED_AS 자동 승격) | ✅ |
| materializer(outbox 증분 소비, 1000행 청킹, [GraphLatency], C-7, 이슈 #8) | ✅ |
| 데모 3종 매핑 + 멱등성/E2E 테스트, 전체 스위트 green | ✅ |

## 2. 변경 파일·함수/시그니처 목록 (QA 수정 포함 최종본, 코드맵 갱신은 doc-keeper 몫)

### `server/database/models.py`
- 신규 모델 `GraphNode(id, label, identity_key, props, created_at, updated_at)` / `GraphEdge(id, type, from_node, to_node, props, source_name, source_row_ref, updated_by, event_time, created_at)` / `GraphSyncState(id=1, last_outbox_id, updated_at)`
- 인덱스: `idx_graph_nodes_identity(label,identity_key) UNIQUE`, `idx_graph_edges_from_type`, `idx_graph_edges_to_type`, `idx_graph_edges_upsert(from,type,to,source_name) UNIQUE`(source_name NOT NULL default "unknown"), **[QA H2] `idx_graph_edges_row_ref(source_row_ref)`**
- 신규 `ensure_graph_tables(engine) -> list`(#7 패턴: info_schema 게이트+checkfirst+락+실패 격리) / 수정 `refresh_dynamic_models(engine)`(그래프 테이블 보장 동승)

### `server/database/crud.py`
- **[QA ⑥] 신규** `resolve_priority_map(table_name=None) -> dict` / `get_source_priority(source_name, table_name=None) -> int` — 소스 서열 단일 원천. `compute_priority_value` 내부가 이를 사용(동작 불변)
- **[QA ⑥]** `SOURCE_PRIORITY`에 `"chain_ingestion": 4` 등재
- **[QA ④] 수정** `get_ontology_mapping()` — v2 검증+enrichment 승격 적용 결과 캐시(v1 키 원본 보존)
- 수정 `check_needs_rollback(table_name, modified_cols)` — v2 매핑 인식(노드 identity·엣지 target_identity_from), v1 폴백 유지

### `server/ontology_config.py` (신규, ~300줄)
- `validate_ontology_mapping(raw_config, known_tables=None) -> dict` — description 필수(테이블/엣지), 컬럼 존재 검증, 테이블 단위 스킵, 공간 속성 파싱, v1/`__`키 무시
- `synthesize_enrichment_mappings(mappings, enrichment_rules) -> dict` — RESOLVED_AS 승격(`source_override="user"`, 사용자 정의 우선, 기본 노드 합성)
- `load_ontology_mappings(path=None, known_tables=None, include_enrichment=True) -> dict`

### `server/graph_materializer.py` (신규, ~430줄)
- `compose_identity(values) -> str|None` — "|" 조인 + **[QA ⑦] 이스케이프** + float 정수 안정화(`_normalize_identity_part`)
- `flatten_payload_data(data)` / `extract_graph_items(table_name, rows, mapping, node_map=None, edges=None)` — **[QA H1]** 엣지 소스 = source_override 또는 식별 컬럼 winner들의 최저 서열(보수적)
- **[QA H1] 신규** `attach_col_sources(db, table_name, rows, mapping)` — 증분·resync 공용 provenance 결정 단일 지점 / `_load_best_cell_sources(db, table_name, row_ids, columns, chunk_size)` — crud 서열 + row_id IN 청킹
- `bulk_upsert_nodes(db, node_map, chunk_size=1000) -> dict`(방언별 ON CONFLICT + props shallow-merge) / `bulk_upsert_edges(db, edges, node_ids, chunk_size=1000) -> int`
- **[QA H2] 신규** `_retarget_stale_edges(db, rows, chunk_size) -> int` — (from_node, type, source_row_ref) 스코프 stale 타깃 삭제
- `materialize_rows(...)` / `materialize_events(db, events, mappings, chunk_size) -> stats`(DELETE 스킵+카운트, 무매핑 로그 1회)
- `resync_table(db, table_name, mappings, chunk_size=1000, row_ids=None, chunk_hook=None, stamp_synced=True) -> stats` — 키셋 청킹(C-7) + **[QA ⑤] row_ids 슬라이스 모드** + attach_col_sources 공유

### `server/graph_sync_worker.py`
- `run_graph_materializer_loop()` — **[QA M3]** 배치 본체 `_run_one_batch(mappings)`를 `asyncio.to_thread`로 격리. 자체 keyset 커서, LISTEN/NOTIFY, 배치 내 SYSTEM_RELOAD 리로드(이슈 #8), `[GraphLatency] batch= rows= nodes= edges= lag_ms= exec_ms=` 계측
- 신규 `_load_graph_mappings` / `_get_or_init_graph_cursor` / `_advance_graph_cursor` / `_lag_ms_from` / `_reload_graph_worker_configs` / `_neo4j_chunk_hook_factory(table_name)`(§4 인터페이스 보존)
- 개편 `execute_manual_sync(table_name, row_ids)` — C-7 해소(키셋 청킹 + 테이블당 `batch_refresh_required` 1건 + to_thread), `"all"` 지원. `get_row_data_for_sync`는 DEPRECATED 마킹(신규 배선 금지)
- 수정 `startup_event()` — TABLE_CONFIG 동기화 + ensure_graph_tables + 루프 기동(`GRAPH_MATERIALIZER_ENABLED` env)

### `server/main.py`
- `reload_local_process_cache()` — `crud._ontology_cache = None` 무효화 추가. REST/WS 계약 변경 없음(`/api/graph/sync` 응답에 `tables` 필드 추가 — 기존 필드 유지)

### `server/config/ontology_mapping.json.sample` (tracked)
- v2 데모 3종 예시로 전면 갱신(문서 예시 겸용)

### `server/tests/test_ontology_g1.py` (25 tests)
- 1차 18종(로더 검증/승격/멱등/청킹/E2E/커서/resync) + QA 7종(H1 위조 방지·보수적 다중컬럼·경로 동등성, H2 E2E 재교정·타 로우 보존, ④⑤⑥⑦)

## 3. 검증 결과

- `conda run -n assy_manager python -m pytest server/tests/ -q` → **144 passed, 1 failed(기허용 test_map_presets_api)**
  - 참고: worktree에는 gitignored 사용자 config/mappers가 없어 3건이 환경 사유로 실패했었음 → 본 저장소에서 복사 후 전부 통과(코드 원인 아님)
- PG 실환경: `ensure_graph_tables`로 그래프 3테이블 + **인덱스 8종**(idx_graph_edges_row_ref 포함) 생성 확인(pg_indexes 대조). 실 config 매핑 로드 → 4테이블 + core_wafer_map RESOLVED_AS(user) 승격 확인. ON CONFLICT/JSONB `||` 병합/멱등 스모크 통과(데이터는 rollback 폐기)
- 1차 테스트 실행 부수효과로 라이브 PG에 구 스키마(신규 인덱스 없음)로 우발 생성됐던 빈 그래프 테이블은 **드롭 후 신 스키마로 재생성 완료** — 병합 후 추가 마이그레이션 불필요

## 4. 라이브 검증 절차 (총괄 수행용)

1. **사용자 config 반영**: `server/config/ontology_mapping.json.sample`(커밋됨)을 본 저장소 `server/config/ontology_mapping.json`으로 복사(worktree 격리로 직접 반영 불가였음).
2. main 병합 후 전 프로세스 재기동 → `graph_sync.log`: `PG materializer loop task started.` / `materializer cursor initialized at outbox id N` / `4 mapped table(s)` 확인.
3. bonding 인제션(또는 auto_update 주기) 후:
   ```sql
   SELECT label, count(*) FROM graph_nodes GROUP BY label;
   SELECT type, source_name, count(*) FROM graph_edges GROUP BY type, source_name;
   ```
   `[GraphLatency] batch=.. lag_ms=..` SLO(10s) 이내 확인. 엣지 source_name은 셀 레이어 기준(파일 인제션분 pipeline_parser)임을 확인.
4. 백필: `POST /api/graph/sync {"table_name":"all"}` → `[GraphLatency] resync table=.. chunks=..` + 클라이언트 `batch_refresh_required` 수신 + 재실행 시 카운트 불변(멱등).
5. **H2 확인** — enrichment에서 wafer_id 입력 → `RESOLVED_AS(source_name='user')` 생성. 값을 다른 wafer로 재교정 → RESOLVED_AS가 **1개 유지 + to가 새 wafer로 교체**:
   ```sql
   SELECT n1.identity_key AS from_key, n2.identity_key AS to_key, e.source_name
   FROM graph_edges e JOIN graph_nodes n1 ON n1.id=e.from_node JOIN graph_nodes n2 ON n2.id=e.to_node
   WHERE e.type='RESOLVED_AS';
   ```
6. **H1 확인** — 그리드에서 bonding 로우의 무관 컬럼(cx 등)만 user 수정 → BONDED_FROM 엣지 source_name이 user로 바뀌지 **않고** 엣지 수도 불변인지 확인.
7. 핫리로드(이슈 #8): 테이블+매핑 추가 → `/admin/reload-configs` → `[Graph Reload] Reloaded ontology mappings ...` 확인.

## 5. 설계 결정 사항 (이견 시 지적 바람)

1. **커서 테이블 방식**(outbox ALTER 회피), 최초 커서=현재 최대 id(백로그는 전체 재동기화 담당).
2. **identity 정규화**: "|" 조인 + 이스케이프 + float 정수 안정화.
3. **props shallow-merge**(PG `||`/sqlite `json_patch`) — 엣지 타깃 스텁({})이 노드 props를 지우지 않음.
4. **[H1] 엣지 provenance = 식별 컬럼 winner들의 최저 서열(보수적)** — 관계 주장은 가장 신뢰도 낮은 입력만큼만 신뢰. 식별 컬럼 전부가 user winner일 때만 user 날인.
5. **[H2] retarget 매칭 키 = (from_node, type, source_row_ref)** — QA 문안(source_name 포함)에서 의도적 편차: 교정은 winner 소스도 함께 바꾸므로(pipeline→user) source를 키에 넣으면 구 소스 엣지가 잔존한다(step 교정 시나리오로 입증). 로우=주장 단위 스코핑이라 타 로우 엣지는 구조적으로 안전.
6. **chain_ingestion 서열 4 등재** — 기존 4대 소스와 상대 서열 불변(표시 레이어링 결과 유지). 미등재 커스텀 소스와 공존하는 셀에서만 chain_ingestion이 우선하게 되는 미세 변화 있음(레이어링 코어 민감 사항이라 명시 보고).
7. **행 DELETE 이벤트 스킵은 [H2]와 별개의 §8 미결 항목** — H2는 "행이 살아있는 채 target이 바뀌는" 일상 EDIT 흐름으로 retarget으로 **해소 완료**. §8은 "행 자체가 삭제될 때"의 노드/엣지 정리 정책으로 G1 범위 밖 유지.

## 6. 미해결·리스크

- **[미결·스펙 §8 — H2와 별개]** 행 삭제 시 그래프 정리: DELETE 이벤트 스킵 유지. 삭제된 로우의 stale 엣지는 재동기화로도 제거되지 않음(소스 로우 부재로 retarget 스코프 밖). 정책 확정 시 `idx_graph_edges_row_ref`가 정리 구현의 기반.
- **[리스크-저]** 서로 다른 로우가 같은 관계를 다른 provenance로 주장하는 병렬 엣지는 여전히 가능(설계 허용 — §2). H1 수정으로 같은 로우가 소스만 갈아타며 증식하는 경로는 제거됨. 표시 dedup은 G2 쿼리 API 설계 항목.
- **[리스크-저]** outbox 7일 purge보다 materializer 장기 정지 시 증분 유실 → 전체 재동기화로 복구(운영 수칙 문서화 권장).
- **[G2 준비]** 시간 범위 스캔용 엣지 인덱스(event_time)는 G2 쿼리 설계와 함께 추가 권장.

## 7. 이력 초안 (병합 시 기록용)

> **2026-07-25 — Ontology G1 (server)**: PG 엣지 스토어(graph_nodes/graph_edges/graph_sync_state + §2 인덱스 규율) 신설, ontology_mapping v2 로더/검증(description 필수·공간 속성·enrichment RESOLVED_AS 자동 승격), graph_sync_worker에 outbox 증분 materializer 루프(자체 keyset 커서, LISTEN/NOTIFY, SYSTEM_RELOAD 구독=#8, [GraphLatency] 계측, to_thread 격리) 추가, /api/graph/sync를 키셋 청킹 재동기화로 개편(C-7 해소, Neo4j 경로 청크 훅 보존). QA 반영: 엣지 provenance를 셀 레이어 진실(식별 컬럼 winner 최저 서열)로 통일해 증분·재동기화 경로 동등성 확보, 재교정 시 (from,type,source_row_ref) 스코프 retarget으로 모순 엣지 병존 제거(행 삭제 정책 §8과는 별개 항목), 소스 서열 crud 단일 원천화(chain_ingestion=4 등재), identity 이스케이프. 테스트 25종 + 전체 스위트 green(기허용 1건 외).

## 8. 교훈 제안 (총괄 검수 후 memory/server-pm.md 반영)

- **함정**: worktree에는 gitignored 사용자 영역(server/config/*.json, mappers/)이 없어 의존 테스트가 거짓 실패하고 사용자 config에 직접 쓸 수도 없다.
  **올바른 방법**: 착수 시 본 저장소에서 config/mappers를 worktree로 복사, 사용자 config 변경분은 보고서로 총괄 적용 위임. 복사로 tracked 파일(.sample)이 덮이지 않았는지 커밋 전 `git status` 확인.
- **함정**: UPSERT UNIQUE 키에 nullable 컬럼이 끼면 PG에서 NULL 중복이 허용돼 멱등이 깨진다.
  **올바른 방법**: 멱등 키 컬럼은 `nullable=False` + 기본값으로 설계.
- **함정**: `apply_batch_updates`는 단순 business_key 테이블에서 `business_key_val` 미지정 시 기존 행 매칭 없이 **신규 행을 만든다**(composite 테이블만 updates에서 자동 조립) — 테스트/스크립트 시딩이 조용히 중복 행을 만든다.
  **올바른 방법**: 시딩 시 `GeneralUpdateItem(business_key_val=...)`을 명시(API 경로와 동일).
