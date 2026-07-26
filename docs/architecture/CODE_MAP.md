# 🗺️ CODE_MAP — 압축 구조 지도 (파일 전량 읽기 방지용)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-26 (HEAD 251dbfd) | **Owner:** 전 에이전트 공용 | **Source-of-truth:** 각 표의 코드 경로
> 상위: [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md)

**⚠️ 사용 규칙 — 이 문서가 존재하는 이유:**
- **소스 파일을 통째로 Read하지 말 것.** 이 지도에서 함수·라인을 찾은 뒤 **해당 섹션만** `Read(offset, limit)`로 읽는다.
- 라인 앵커는 HEAD `251dbfd` 기준 **±20줄 오차 허용**. 정확 위치는 Grep으로 확정.
- `client2/*` 앵커는 **`client2/src/`**(원본) 기준이다 — `client2/dist/assets/map_editor-*.js`는 vite 산출물이라 파일명 해시가 빌드마다 바뀐다. **dist 번들명을 문서에 고정 인용하지 말 것.**
- 이 문서는 **지도이지 교과서가 아니다** — 구현 설명은 각 리빙 문서([backend](./backend.md)·[data_model](./data_model.md)·[frontend](./frontend.md)·[event_driven_backend](./event_driven_backend.md)) 참조.

**유지보수 규율:** 코드맵 갱신은 **doc-keeper 전담** — 총괄이 코드 배치를 병합·커밋한 뒤 doc-keeper에 위임하면, doc-keeper가 **타 에이전트들의 수정 이력(history 문서·보고서·커밋 diff)을 요약**해 해당 모듈 맵을 갱신한다(구현 에이전트는 맵을 직접 수정하지 않음 — 보고서에 변경 함수/시그니처 목록만 남긴다). 정기 정합 감사도 doc-keeper. 라인 앵커는 대략치로 충분 — 시그니처·역할 서술의 정확성이 우선.

---

## 목차

| 파일 | 라인수 | 섹션 |
|---|---|---|
| `server/main.py` | ~3,934 | [§1](#1-servermainpy--api--ws-허브) |
| `server/database/crud.py` | ~1,890 | [§2](#2-serverdatabasecrudpy--레이어링-코어) |
| `server/parsers/directory_watcher.py` | ~1,712 | [§3](#3-serverparsersdirectory_watcherpy--파일-인제션) |
| `server/chain_ingestion_worker.py` | ~965 | [§4](#4-serverchain_ingestion_workerpy--체인-워커) |
| 소형 서버 모듈 (models/std_parser/enrichment_*/ingestion_activity/ingestion_checkpoint/bonding_plan/**map_overlay**/**transfer_plan**) + 그래프 트랙(graph_sync_worker/graph_materializer/ontology_config) | ~6,120 | [§5](#5-소형-서버-모듈) |
| 기타 서버 모듈 (한줄 요약) | — | [§6](#6-기타-서버-모듈-한줄-요약) |
| `client2/src/*` | ~16,000 | [§7](#7-client2src--웹-클라이언트) |
| 주요 호출 흐름 | — | [§8](#8-주요-호출-흐름-요약) |

---

## 1. `server/main.py` — API + WS 허브

FastAPI 웹서버. 모든 REST/WS의 단일 진입점. 워커·워처와는 outbox + `/internal/events/*`로 통신.

### 1.1 기동·미들웨어·공용 헬퍼

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `db_context_middleware(request, call_next)` | 요청별 DB 세션 수명 관리 미들웨어 | ~55 |
| `startup_event()` | 기동: 테이블 준비, 워처 스레드, 콜백 배선, 캐시 워밍 | ~99 |
| ├ `trigger_ws_refresh(table_name, count, created_logs, total_log_count)` | (내부·임베디드 모드 전용) 인제션 완료 → WS 갱신 브로드캐스트 콜백 (⚠️ C-5 절단 미적용 레거시 경로 — 드릴 관찰, 저순위) | ~179 |
| ├ `trigger_ws_file_processed(table_name, filename, status, error_msg)` | (내부) 파일 처리 상태 → WS 통지 콜백 | ~199 |
| └ (임베디드 ingestion-state 배선) | [P1] 비-DECOUPLED 시 HTTP 없이 `ingestion_activity_registry`에 직접 반영, file-processed 시 제거 | ~227–244 |
| `shutdown_event()` | 종료 정리 | ~271 |
| `class ConnectionManager` — `connect/disconnect/broadcast` | WS 연결 풀 + 전체 브로드캐스트 | ~287 |
| `invalidate_table_cache(table_name)` | 테이블 count 캐시 무효화 | ~354 |
| `inject_system_columns(row)` | 응답 행에 시스템 컬럼 주입 | ~388 |
| `fetch_and_merge_metadata(db, table_name, rows, user_cols, include_sources=True) -> list` | 행들에 CellSource/Overwrite 메타 병합 → 셀 객체 `{value,is_overwrite,priority_source}` 생성 (조회 응답의 핵심) | ~473 |
| `get_deleted_row_business_key(db, table_name, row_id)` / `..._bulk(...) -> dict` | 삭제 행의 비즈니스 키 역추적(감사 표시용) | ~601/624 |
| `check_rows_exist(db, row_keys) -> set` | (table,row_id) 존재 일괄 확인 | ~662 |
| `from ingestion_activity import registry as ingestion_activity_registry` | [P1] 진행 스냅샷 레지스트리 싱글턴 import([§5](#5-소형-서버-모듈)) | ~681 |
| `get_column_filter_condition(table_model, col_name, f_info)` | 컬럼 필터 → SQLAlchemy 조건 변환(타입별) | ~851 |
| `reload_local_process_cache()` | 웹서버 config 핫리로드 — `models.refresh_dynamic_models(engine)` 위임(싱글턴·ORM·신규 테이블 물리 CREATE, 이슈 #7) + `crud._ontology_cache` 무효화 | ~2773 |
| `load_maps_config() / save_maps_config(data)` | 맵 프리셋 JSON 파일 IO | ~2858/2867 |

### 1.2 API 라우트 표 — 데이터 조회/편집

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| GET `/` | `read_root` | index 서빙 | ~316 |
| GET `/api/download/client` | `download_desktop_client` | 데스크톱 셸 배포 | ~329 |
| GET `/tables` | `list_tables` | 테이블 목록 | ~594 |
| GET `/tables/{t}/data` | `get_table_data` | **메인 조회** — 페이지네이션+필터+정렬+메타 병합 | ~954 |
| GET `/tables/{t}/schema` | `get_table_schema` | 스키마 계약(`table_config.json` 기반) | ~1525 |
| GET `/tables/{t}/{row_id}` | `get_row_data` | 단일 행 조회 | ~1563 |
| GET `/tables/{t}/export` | `export_table_csv` | CSV 스트리밍 export | ~1330 |
| POST `/tables/{t}/rows` | `create_row` | 빈 행 N개 생성(+WS 통지) | ~1651 |
| PUT `/tables/{t}/data/updates` | `apply_batch_updates_endpoint` | **메인 편집** — crud.apply_batch_updates 호출 후 병합·브로드캐스트 | ~1713 |
| DELETE `/tables/{t}/rows/{row_id}` | `delete_row` | 단일 삭제 | ~1164 |
| POST `/tables/{t}/rows/batch_delete` | `delete_rows_batch_endpoint` | 일괄 삭제(+WS) | ~1187 |
| POST `/tables/{t}/row_ids/target` | `get_target_row_ids` | 필터 조건 → row_id 목록(범위 작업용) | ~1242 |
| POST `/tables/{t}/upload` | `upload_file` | 파일 업로드 → 워크스페이스 투입 | ~2225 |

### 1.3 API 라우트 표 — 이력/레이어링(소스·우선순위)

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| GET `/audit_logs/recent` | `get_recent_audit_logs` | 최근 트랜잭션 그룹 이력 | ~683 |
| GET `/audit_logs/transaction/{tx_id}` | `get_transaction_logs` | 트랜잭션 상세 로그 | ~728 |
| GET `/dashboard/summary` | `get_dashboard_summary` | 대시보드 통계 | ~807 |
| GET `/tables/{t}/rows/{r}/history` | `get_row_history` | 행 이력 | ~1598 |
| GET `/tables/{t}/rows/{r}/cells/{c}/history` | `get_cell_history` | 셀 이력 (⚠️ ~2381에 동일 경로 중복 정의 — 선등록인 ~1624가 유효) | ~1624 |
| GET `/tables/{t}/{r}/{c}/sources` | `get_cell_sources` | 셀의 레이어(소스) 목록 | ~2252 |
| DELETE `/tables/{t}/{r}/{c}/sources/{s}` | `delete_cell_source` | 단일 소스 삭제(+재계산·WS) | ~2296 |
| PUT `/tables/{t}/{r}/{c}/priority` | `set_cell_priority` | 단일 셀 수동 우선순위(Pin) | ~2329 |
| PUT `/tables/{t}/cells/priority/batch` | `set_cell_priority_batch_endpoint` | Pin 일괄 | ~2393 |
| POST `/tables/{t}/cells/sources/delete/batch` | `delete_cell_source_batch_endpoint` | 소스 삭제 일괄 | ~2464 |
| POST `/tables/{t}/cells/sources/query` | `query_cells_sources` | 셀 범위 소스 일괄 조회 | ~2525 |

### 1.4 API 라우트 표 — 어드민/운영/그래프/맵·인리치먼트

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| POST `/api/graph/sync` | `manual_graph_sync` | 그래프 **백필/복구** 트리거(:8090 프록시 — 주 경로는 materializer) | ~1814 |
| POST `/admin/outbox/retry-failed` | `retry_failed_outbox_events` | outbox 실패 재시도 | ~2609 |
| GET `/admin/outbox/failed` | `get_failed_outbox_events` | outbox 실패 목록(페이징) | ~2648 |
| GET `/admin/file-ingestion/logs` · `/failed` | `get_file_ingestion_logs` 등 | 파일 인제션 로그/실패 목록 | ~2718/2753 |
| GET `/admin/file-ingestion/active` | `get_active_file_ingestions` | **[P1 신설]** 진행 중 인제션 스냅샷(레지스트리 `snapshot()` — 인메모리, TTL 퇴거 포함) — admin File 탭/헬스 스트립 소비 | ~2759 |
| POST `/admin/file-ingestion/retry-failed` | `retry_failed_file_ingestion` | 아카이브 파일 재처리(동기 콜백 배선 포함, 내부 `sync_refresh_callback` ~3241) — 워크스페이스는 `resolve_workspace_root` 역조회(별칭 대응) | ~3208 |
| GET `/admin/file-ingestion/workspaces` | `get_ingestion_workspaces` | 워크스페이스 현황 — 표시 table_name에 글로벌 별칭(`find_workspace_alias`) 우선 적용 | ~2985 |
| POST `/admin/reload-configs` | `reload_system_configs` | config 핫리로드 — 동기 CREATE(1차 DDL 소유자)가 outbox 발화보다 선행 (+SYSTEM_RELOAD outbox 발화) | ~2807 |
| GET `/admin/chain/rules` · `/admin/mappers/list` | `get_chain_rules` / `get_mappers` | 체인 룰·맵퍼 목록 | ~3066/3088 |
| GET `/admin/auto-update/status` | `get_auto_update_status` | 스케줄러 상태 — 항목별 `active` 부가(제어 파일 실시간 계산) | ~3318 |
| POST `/admin/auto-update/toggle` | `toggle_auto_update_script` | 수집기 active 토글 — `config/auto_update_control.json` 갱신(핫 반영, 404/400 명시) | ~3349 |
| POST `/admin/auto-update/run-now` | `trigger_auto_update_run_now` | 즉시 실행(**active 무관** — 수동 실행은 명시적 의도) | ~3381 |
| GET/POST `/admin/scripts/list|code` | `list_admin_scripts` 등 | Monaco 에디터용 스크립트 IO | ~3556–3655 |
| GET/POST/DELETE `/map-presets` (+`/api/` 별칭) | `_save_map_preset_impl` 등 | 맵 프리셋 CRUD | ~2889–2949 |
| GET `/api/bonding-plan/core-summary` | `get_bonding_plan_core_summary` | **[본딩 M1]** 코어(lot,slot) 역할별 집계 — `bonding_plan.get_core_summary` 위임([§5](#5-소형-서버-모듈)), `region` 파라미터(rects — 현 클라 미사용), 잘못된 region 400 | ~2957 |
| GET `/api/maps/overlay` | `get_map_overlay(target_table, target_key, sources, eqp=None, limit=None)` | **[M2 신설 · 맵 인프라]** 임의의 맵들을 타깃 맵 프레임 좌표로 정렬해 `overlays[]` 반환. `sources`는 `table` 또는 `table:key`의 CSV(키 생략 시 target_key 승계, 최대 8종). `map_overlay.get_overlay` 위임([§5](#5-소형-서버-모듈)), `parse_sources` ValueError → 400, 셀 상한 `MAX_OVERLAY_CELLS=20,000`(초과 시 `truncated:true`) | ~2990 |
| GET `/api/maps/paint-rules` | `get_map_paint_rules(table=None)` | **[M2 신설]** 페인트 잠금 선언 정본(**기존엔 클라 하드코딩 `'F'`**) — `map_overlay.get_paint_rules`. 응답 `{table, rules{enabled, blocking_values, from_overlay, message}}` | ~3026 |
| GET `/api/transfer-plan/stages` | `get_transfer_plan_stages` | **[M2 신설]** 선언된 전사 stage 목록 + 역할 연결 상태(config 해석만 — 행 조회 없음). `transfer_plan.list_stages` | ~3040 |
| GET `/api/transfer-plan/source-summary` | `get_transfer_plan_source_summary(stage, lot, slot, ref_table=None, map_key=None)` | **[M2 신설]** 단계별 소스 (lot,slot) 가용 집계 — `transfer_plan.get_stage_source_summary`. 미선언 stage 404. **칩 좌표 목록은 반환하지 않는다**(집계만 — 페이로드 상한 규율). `(ref_table, map_key)` 지정 시 `region_chips` 동봉(v2에서 구 `plan_id` 대체) | ~3054 |
| GET `/api/transfer-plan/validate` | `validate_transfer_plan(ref_table, map_key)` | **[M2 신설 · v2 모델]** 계획 검증 — **계획 정체성 = 지금 열어 편집 중인 맵**(`plan_id` 폐기). stage는 `stages.*.target_map.table` 역인덱스로 유도, 미선언 맵은 404가 아니라 `stage_unknown` 경고 + `status:"unverified"`. `plan_store.doe` 미구성만 404 | ~3084 |
| GET `/enrichment/rules` · `.../references/{index}` | `get_enrichment_rules` / `get_enrichment_reference` | 인리치먼트 규칙 공개본·참조 뷰 조회 | ~3140/3151 |
| WS `/ws` | `websocket_endpoint` | WS 접속(ConnectionManager) | ~2213 |
| POST `/internal/events/batch-refresh` · `/broadcast` · `/file-processed` | `internal_event_*` | **워커/워처 → 웹서버 브로드캐스트 위임 (경계 계약)** — 수신부는 `total_log_count`(실건수) 우선 + `MAX_NOTIFY_CREATED_LOGS` 방어 절단(인시던트 `cc57b64`). [P1] batch-refresh는 msg 재구성 시 `total_log_count` 동봉(~3447 — 체인 passthrough 경로와 대칭화), broadcast는 `file_ingestion_progress`를 레지스트리에 인터셉트, file-processed는 레지스트리 제거 인터셉트 | ~3421–3540 |
| POST `/internal/events/ingestion-state` | `internal_event_ingestion_state` | **[P1 신설]** watcher → 진행 스냅샷 push(QUEUED/PROCESSING/FINISHED — heavy 파일만 명시 통지). **WS 브로드캐스트 없음** — 레지스트리 전용 내부 이벤트 | ~3542 |
| GET `/admin`·`/map-editor`·`/enrichment`·`/{path}` | `serve_*` | 정적 페이지 서빙(`graph.html`/`trace.html`은 catch-all `serve_static_or_index` 경유) | ~3737–3789 |

### 1.5 그래프 조회 구간 (read-only — `graph_nodes/edges` 직접 조회, 워커 미경유)

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| (상수) | `GRAPH_NEIGHBOR_NODE_CAP=500` / `GRAPH_LABEL_LIST_LIMIT_CAP=200` / `GRAPH_TRACE_NODE_CAP=1000` / `GRAPH_TRACE_DEPTH_CAP=3` 등 | 하드캡(C-7 무제한 로드 금지) | ~1864–1868 |
| (헬퍼) | `_escape_like_term(term)` | LIKE 메타문자 이스케이프 | ~1873 |
| (헬퍼) | `_expand_graph_subgraph(db, seed_nodes, depth, node_cap, edge_types=None, time_from=None, time_to=None)` | 뷰어/추적 **공용 BFS 코어** — 방향별 (from,type)/(to,type) 인덱스 2쿼리, 홉·방향당 엣지 페치 캡 2000, 노드 500청크 IN, 캡 절단 시 dangling 엣지 제외 | ~1878 |
| (헬퍼) | `_serialize_graph_nodes(nodes)` | 노드 `{id,label,identity_key,props}` 직렬화 | ~1971 |
| GET `/graph/stats` | `get_graph_stats` | label/edge_type GROUP BY 카운트 + last_sync | ~1979 |
| GET `/graph/neighbors` | `get_graph_neighbors` | k-hop(1\|2) 서브그래프 — `_expand_graph_subgraph([center])` 위임, truncated | ~2004 |
| GET `/graph/nodes/search` | `search_graph_nodes` | identity 시작일치 ILIKE 자동완성(limit 캡 50) + **빈 q + label = 라벨 전체 리스팅**(`df63f3a` — identity 오름차순, limit/offset, 캡 200. 전 테이블 덤프 금지 유지) | ~2039 |
| (헬퍼) | `_parse_trace_time(value, field)` | ISO 8601 파싱(`Z` 허용), 실패 시 400 | ~2100 |
| POST `/graph/trace` | `post_graph_trace(req: GraphTraceRequest, db)` | **[G2]** 멀티 시드 BFS 합집합 — 시드 순서보존 dedup→(label,identity) 인덱스 조회→missing_seeds 분리→공용 BFS. depth 1..3, 시간·타입 필터, 의미 검증 400 | ~2112 |
| GET `/graph/mapping-summary` | `get_graph_mapping_summary` | `ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)` — materializer와 동일 신호원, 요청 시 디스크 로드 | ~2189 |

---

## 2. `server/database/crud.py` — 레이어링 코어

셀 단위 소스 레이어링(CellSource/CellOverwrite/priority) + 배치 업서트의 단일 구현. **시그니처 변경 시 전수 Grep 연쇄 갱신 필수**([규율](../guide/data_preservation_and_signature_change.md)).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `transaction_context(user, tx_id, source)` | 컨텍스트매니저 — 감사·outbox용 트랜잭션 식별 주입 | ~8 |
| `class LightCellSource` / `LightCellOverwrite` | ORM 미경유 경량 메타 객체(성능) | ~28/39 |
| `_warn_audit_truncation_once(table_name, col_name)` | [P2] 감사 값 절단 경고 dedup(테이블·컬럼당 1회) | ~43 |
| `sanitize_to_utf8(data)` | cp949 등 오염 문자열 정화 | ~90 |
| `load_table_config()` / `update_table_config(new_config)` | table_config.json IO | ~112/121 |
| `cast_value_by_type(value, col_type, col_name)` | 컬럼 타입 캐스팅 | ~137 |
| `get_row_by_business_key(db, table_name, key_value)` | 비즈니스 키로 행 조회 | ~164 |
| `resolve_priority_map(table_name=None) -> dict` / `get_source_priority(source_name, table_name=None) -> int` | **소스 서열 단일 원천**(테이블별 오버라이드 포함) — compute_priority_value·graph materializer 공용. `SOURCE_PRIORITY`에 `chain_ingestion: 4` 등재 | ~178/193 |
| `compute_priority_value(sources, manual_priority_source, table_name)` | **표시값 결정** — user:0 < collision_merge:1 < pipeline_parser:2 < custom_script:3 < chain_ingestion:4 + 수동 Pin | ~198 |
| `create_audit_log(db, ..., transaction_id, business_key, add_to_cache)` | 감사 로그 1건 생성. [P2] `old_val`/`new_val`은 `event_constants.truncate_audit_value`로 **4096자 상한**(~240) — 절단본이 DB 저장본과 통지 dict **양쪽에** 동일 적용되고, 절단 사실은 값 내부 마커(`…[truncated: 총 N자]`)로 명시 | ~220 |
| `bulk_insert_audit_logs(db, logs)` | 감사 로그 벌크 삽입 | ~279 |
| `bulk_upsert_cell_sources(db, mappings)` / `bulk_upsert_cell_overwrites(db, mappings)` | 메타 테이블 벌크 업서트(ON CONFLICT) | ~299/331 |
| `bulk_delete_cell_overwrites(db, delete_keys)` | overwrite 벌크 삭제 | ~364 |
| `_get_or_create_row(db, table_model, update_item, row_cache, table_name) -> (row, is_new)` | row_id/비즈니스키로 행 확보(캐시 활용) | ~380 |
| `_load_metadata_row_cell(...) -> (sources_list, overwrite)` | 셀 메타 로드(캐시·업서트 큐 연동) | ~436 |
| `apply_row_update_internal(db, table_name, update_item, row_cache, sources_cache, overwrites_cache, transaction_id, logs_to_cache, cell_sources_to_upsert, cell_overwrites_to_upsert, cell_overwrites_to_delete, deleted_row_ids) -> (row, is_new, changed_cols)` | **[통합 코어]** 단일 행 업데이트 + 레이어링 재계산. 모든 쓰기 경로가 여기로 수렴 | ~500 |
| `apply_batch_updates(db, table_name, batch: GeneralUpdateBatch)` | **배치 진입점** — tx 컨텍스트, 캐시 프리로드, 행별 코어 호출, 벌크 flush, outbox 발화. 반환 `(results, changed_cells, created_logs, deleted_row_ids)`. [P2] 워처가 이 함수의 commit에 오프셋 갱신을 동승시킨다 | ~980 |
| `create_empty_row(s)_batch(db, table_name, count, user_name)` | 빈 행 생성 | ~1173/1178 |
| `delete_row(db,...)` / `delete_rows_batch(db, table_name, row_ids, user_name)` | 행 삭제(+감사·메타 정리) | ~1222/1226 |
| `delete_cell_source_batch(db, table_name, cells, source_name)` | 소스 레이어 일괄 삭제 + 표시값 재계산 | ~1290 |
| `delete_cell_source(db, ...)` | 단일 소스 삭제(배치 위임) | ~1446 |
| `set_cell_manual_priority_batch(db, table_name, updates, source_name, updated_by)` | 수동 Pin 일괄(§크고 복잡 — 표시값 재계산·감사 포함) | ~1451 |
| `set_cell_manual_priority(db, ...)` | 단일 Pin(배치 위임) | ~1810 |
| `get_ontology_mapping()` / `check_needs_rollback(table_name, modified_cols)` | 그래프 보조 — v2 검증+enrichment 승격 적용 결과 캐시 / v2 매핑 인식 rollback 신호(v1 폴백) | ~1819/1862 |

---

## 3. `server/parsers/directory_watcher.py` — 파일 인제션

워크스페이스별 폴더 감시 → 파서 실행 → **HTTP 아닌 직접 DB**(`crud.apply_batch_updates`) 업서트 → 웹서버에 `/internal/events/*` 콜백. 2026-07-25 std parser(무스크립트 표준 파싱)·기동/주기 스윕 통합, **워크스페이스 config.json 폐지**(`5fac5f0`).

- **[P1] heavy 레인**(`4fd8ac9`+`8b0fd03`) — 크기 임계(기본 10MB, `config/ingestion_settings.json` 파일 경계 핫리로드) 초과 파일을 전용 큐/워커로 이관해 observer 디스패치 스레드 HOL 제거. 워크스페이스 내 FIFO는 backlog 카운터+직렬화 락+논블로킹 재라우팅 3중 장치로 보존.
- **[P2] 체크포인트 재개 + 해시 dedup**(`f78ab0a`) — 파일 전체 sha256 시그니처(`sha256:<size>:<digest>`)를 계산해 ① 동일 시그니처 `DONE`이면 skip ② 미완이면 오프셋 재개. 저장소는 신규 테이블 `file_ingestion_checkpoints`([`ingestion_checkpoint.py` §5](#5-소형-서버-모듈)). **오프셋 갱신은 청크 upsert와 같은 트랜잭션** — "커밋된 행 수 == 기록된 오프셋"이 원자적으로 성립. 재개는 시그니처+`total_rows`+`source_kind`+오프셋 범위가 **전부** 일치할 때만. heavy/normal·스윕·관리자 재시도 4경로 동일 동작.
- 통지 로그 상한 `MAX_NOTIFY_CREATED_LOGS`는 `event_constants.py` 공용 상수 import.
- 테스트: `tests/test_workspace_config_deprecation.py`(21개) · `tests/test_heavy_lane.py`(27개, `hvy_test_*`) · `tests/test_ingestion_checkpoint.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `load_global_table_config() -> dict` | table_config.json 로드 | ~57 |
| `warn_legacy_workspace_config(config_path)` | 레거시 config.json 발견 시 경로당 1회 deprecation WARNING | ~74 |
| `_log_alias_conflict_once` / `warn_invalid_std_parse_once` | 별칭 충돌·std_parse 비-bool 경고 dedup(키별 1회 — QA D5/D6) | ~98/106 |
| `DEFAULT_HEAVY_FILE_MB=10` / `INGESTION_SETTINGS_PATH` | [P1] heavy 임계 기본값·설정 파일 경로(`server/config/ingestion_settings.json`, `.sample` tracked) | ~124/125 |
| `load_ingestion_settings()` / `warn_invalid_heavy_threshold_once` / `get_heavy_threshold_bytes()` | [P1] 임계 로더 — **파일 이벤트(라우팅 결정)당 1회 디스크 읽기**(파일 경계 핫리로드), 양수만 유효·그 외 기본 10MB+1회 경고 | ~130/144/156 |
| `DEFAULT_DEDUP_BY_SIGNATURE=True` / `DEFAULT_RESUME_FROM_CHECKPOINT=True` / `_bool_setting(key, default)` | [P2] dedup·재개 기본값과 설정 판독기(같은 `ingestion_settings.json`) | ~170/171/174 |
| `dedup_by_signature_enabled()` / `resume_from_checkpoint_enabled()` | [P2] 게이트 — `dedup_by_signature: false`가 **전역 강제 재처리 스위치**(파일명 `__force__`와 관리자 재시도가 나머지 2경로) | ~189/197 |
| `get_workspace_serial_lock(workspace_path) -> Lock` | [P1] **워크스페이스 직렬화 락 — 모듈 레벨 경로 키 레지스트리**(핸들러 복수여도 공유). heavy 워커/인라인/run_watcher 재처리 폴러가 공용 | ~211 |
| `class HeavyIngestionLane` — `submit/_ensure_running/_worker_loop/stop` | [P1] FIFO `queue.Queue` + 데몬 워커 스레드 `watcher-heavy-lane` **1개**(첫 제출 시 지연 기동). WorkspaceWatcher가 1개 생성해 전 핸들러 주입. heavy끼리는 직렬(escalation §6-3) | ~221–273 |
| `find_workspace_alias(folder_name, table_config) -> str\|None` | 폴더명↔`workspace_name` 명시 별칭 매칭 — 섀도잉·중복 선언 별칭은 무효+ERROR 1회(QA D3) | ~275 |
| `resolve_workspace_root(base_dir, table_name, table_config) -> str` | 테이블→워크스페이스 루트 **역조회 공용 함수**(별칭 포함) — 결과 기반 경로 검사(base 직속 자식만, 드라이브 상대경로 탈출 차단, QA D2). main.py `retry-failed`·run_watcher 폴러가 사용 | ~316 |
| `resolve_workspace_table(folder_name, table_config) -> str\|None` | 폴더→테이블 해석: 별칭 > 폴더명 규약 | ~349 |
| `_register_legacy_import_shim()` | 구식 사용자 파이프라인 스크립트의 import 호환 shim | ~363 |
| `class IngestionHandler(FileSystemEventHandler)` | **워크스페이스 1개 담당 핸들러** — 생성자 말단 kwargs `on_ingestion_state_callback`/`heavy_lane`(기본 None=종전 인라인 경로, 하위호환) | ~437 |
| ├ `_load_legacy_config()` | [deprecated] 레거시 워크스페이스 config.json 파싱(이것만 캐시) | ~468 |
| ├ `_resolve_table_name(global_cfg)` | 테이블명 해석: 글로벌 `workspace_name` 별칭 > 레거시 `table_name` > 폴더명 규약 | ~490 |
| ├ `_snapshot_table_context() -> (t_name, table_info)` | **파일당 1회 config 스냅샷**(QA D1) | ~505 |
| ├ `_std_parse_enabled_for(t_name, table_info) -> bool` | std_parse 게이트: 글로벌(JSON bool만 유효) > 레거시 폴백 > 기본 true | ~516 |
| ├ `table_name` / `std_parse_enabled` / `errors_path` (property) | 즉석 해석 래퍼 — **글로벌 조회 비캐시**(핫리로드 반영) | ~536–548 |
| ├ `on_created/on_moved → _handle_event(file_path)` | 파일 이벤트 수신(processing_files check-then-add 락 원자화) → [P1] `_route_and_process` 위임으로 재구성 | ~551–589 |
| ├ `_classify_lane(abs_path)` / `_heavy_backlog_nonzero()` | [P1] 이벤트 시점 `os.stat` 1회 크기 분류 / 워크스페이스 heavy backlog 잔여 확인 | ~591/605 |
| ├ `_route_and_process(abs_path, uploader) -> bool` | [P1] **레인 라우팅 본체** — heavy(크기)·backlog(>0이면 크기 무관 큐 후미=FIFO 보존)·인라인은 직렬화 락 **논블로킹 try-acquire**(실패 시 큐 후미 재라우팅 — HOL 방지+순서 보존 동시 만족) | ~609 |
| ├ `_submit_to_heavy_lane(abs_path, uploader, lane, size_bytes)` | [P1] 큐 제출 — QUEUED 통지를 **submit 이전 선발신**(드릴 결함1: 즉시 픽업 역전 경합 제거), submit 실패 시 FINISHED 정리 통지 후 인라인 폴백. `lane`은 분류 실값(재라우팅 소형은 "normal" — QA F4) | ~643 |
| ├ `_run_lane_job(...)` / `_notify_ingestion_state(state)` | [P1] heavy 워커 잡 본체(직렬화 락 획득→`process_with_retry`→finally 정리) / 상태 push 콜백 래퍼 | ~681/711 |
| ├ `process_with_retry(file_path, uploader, retries=3, delay=1.0)` | 처리 본체 — 스냅샷→파싱→[P2] 시그니처 계산(~743)→dedup skip→`_plan_checkpoint`(~759)→`_send_to_upsert`→`_finalize_checkpoint`→아카이브/에러 이동, 재시도 | ~722 |
| ├ `_compose_detail(skipped_no_key, plan)` (staticmethod) | [P2] 완료 통지 `detail` 조립 — 키 결측 스킵 수 + 재개/재시작 사유 | ~814 |
| ├ `_try_dedup_skip(file_path, basename, t_name, signature) -> bool` | [P2] 동일 시그니처 `DONE`이면 skip — **무음 skip 금지**: WARNING + archive + `FileIngestionLog(status="SKIPPED")` + 콜백 status는 `"SUCCESS"`(수신부가 비-SUCCESS를 실패로 렌더링하므로 오표기 방지) + 사유 detail | ~823 |
| ├ `_plan_checkpoint(...)` / `_finalize_checkpoint(plan, processed_rows)` | [P2] `ingestion_checkpoint.plan_ingestion` 게이트 래퍼(실패 시 `CheckpointPlan.disabled(note=...)`) / `mark_done` — 실패 시 "dedup will not apply" 경고 | ~877/903 |
| ├ `_log_ingestion_record(...)` / `_log_ingestion_failure/success(..., t_name=None)` | FileIngestionLog 기록(직접 DB, 스냅샷 테이블명). `error_message`는 SUCCESS/SKIPPED에서 **detail 슬롯**으로 겸용 | ~916/941/946 |
| ├ `_retry_should_restart(t_name, signature) -> bool` | [P2] 재시도 시 완료 체크포인트가 있으면 처음부터 재시작 판정 | ~954 |
| ├ `process_archived_file_sync(log_entry, db, uploader)` | 어드민 재처리 경로(아카이브 파일 동기 재실행 — 스냅샷 진입점, 내부에서 락 안 잡음). [P2] 체크포인트는 태우되 **dedup skip은 미적용**(재시도는 명시적 의도) | ~970 |
| ├ `_move_to_err_folder` / `_archive_file` | 파일 이동 | ~1019/1047 |
| ├ `_discover_and_execute_pipeline(file_path, meta=None) -> list[dict]\|None` | 사용자 파이프라인 스크립트(pipeline_*.py) 탐색·실행 | ~1074 |
| ├ `_resolve_rows(file_path, t_name=None, table_info=None, ...)` | **파서 라우팅** — 파이프라인 우선, 없으면 std parser 폴백(스냅샷 인자 전파). `source_kind`(`"std"` / `"pipeline:<Class>"`)의 산출처 | ~1168 |
| ├ `_try_std_parse(file_path, t_name, table_info)` | std_parser 호출 래퍼(게이트·에러 처리) | ~1206 |
| └ `_send_to_upsert(rows, uploader, filename, total_rows, t_name=None, table_info=None, checkpoint=None)` | list 또는 스트리밍 이터레이터 → 청킹 → `crud.apply_batch_updates` 직접 호출 + 진행률 콜백. [P2] `checkpoint`로 `resume_from` 스킵(~1303)·오프셋 초과 경고(~1310)·**청크마다 `record_chunk_progress`(~1368, 같은 트랜잭션)**, created_logs는 `MAX_NOTIFY_CREATED_LOGS` 잔여분만 누적(~1381) | ~1247 |
| `class WorkspaceWatcher` | 전체 워크스페이스 관리자 — [P1] `HeavyIngestionLane` 1개 생성(~1415)·전 핸들러 주입 + `on_ingestion_state_callback` 배선 | ~1407 |
| ├ `_provision_workspaces()` | 폴더 스캐폴딩 — **config.json 신설 중단**(폴더만 보충), `workspace_name` 별칭 폴더명 지원(unsafe 별칭 무시) | ~1435 |
| ├ `_register_workspace(raws_root, table_config)` | 핸들러 등록(+`handlers_by_raw_path` 레지스트리, `heavy_lane` 주입) — 레거시 config 발견 시 1회 경고(QA D4) | ~1464 |
| ├ `discover_and_watch()` / `sync_new_workspaces()` | 기동 스캔·신규 워크스페이스 동기화(신규 raws는 등록 직후 스윕) | ~1523/1539 |
| ├ `sweep_existing_files(raw_paths)` / `_sweep_safely` / `sweep_existing_files_async(...)` | **[Startup Sweep]** raws/ 직속 기존 파일을 mtime 오름차순으로 `_handle_event` 경로 재사용 처리 — [P1] 스윕도 자동으로 heavy 라우팅을 탐. (mtime,size) 시그니처로 무한 재시도 차단, err/·하위 dir 제외 | ~1569/1630/1636 |
| ├ `_periodic_sweep_loop()` / `_ensure_periodic_sweep_running()` | 이벤트 유실 안전망 — 300s 주기 잔류 재스캔 데몬 | ~1645/1649 |
| └ `_ensure_observer_running()` / `stop()` / `start(blocking)` | watchdog Observer 수명 관리 — start()가 observer 기동 후 기동 스윕+주기 스윕 킥, stop()이 heavy 레인도 정지(~1676) | ~1658–1712 |

---

## 4. `server/chain_ingestion_worker.py` — 체인 워커

outbox LISTEN/NOTIFY 소비 → 체인 룰 매칭 → 맵퍼 실행 → 파생 테이블 업서트 → `/internal/events/broadcast`로 WS 위임. 지연 SLO 100ms(2026-07-25 F1–F3 + warmup 완료).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `class OutboxListener` — `_ensure_connection/_reset_connection/_wait_blocking/wait(timeout)/close` | psycopg2 LISTEN 전용 커넥션 + async 대기 | ~23–103 |
| `_get_http_session()` / `post_event_async(endpoint, payload) -> bool` | 웹서버 `/internal/events/*` POST(커넥션 재사용) | ~113/129 |
| `purge_expired_outbox_sync(db_session_factory, retention_days, ...)` | 처리 완료 outbox 보존기간 청소 | ~163 |
| `_stamp_broadcast_at_sync(db_session_factory, event_ids)` | 브로드캐스트 완료 스탬프(F1 전달 확정) | ~203 |
| `_dispatch_broadcasts(pending_broadcasts, db_session_factory)` | 커밋 후 인라인 브로드캐스트 발사 + 스탬프 | ~224 |
| `load_chain_rules()` | chain_rules 설정 로드(+enrichment 룰 병합) | ~268 |
| `_mapper_accepts_rule(mapper_func) -> bool` | 맵퍼가 rule 인자를 받는지 시그니처 검사 | ~297 |
| `execute_custom_mapper(module_name, function_name, db, payload, rule=None)` | mappers/ 동적 로드·실행 | ~308 |
| `_group_target_tables(events_in_tx, rules)` | tx 내 이벤트 → 타깃 테이블 그룹핑 | ~326 |
| `process_chain_transaction_group(tx_id, events, db, rules) -> (ok, err, broadcast_messages)` | **핵심** — 순환 차단(source=chain_ingestion 제외), 맵퍼 실행, 업서트, 브로드캐스트 큐 반환. broadcast 구성부(~458)는 created_logs를 **직렬화 전** `MAX_NOTIFY_CREATED_LOGS`(500)로 절단 + `total_log_count`(실건수) 동봉 — 양 분기(`batch_refresh_required`/`batch_row_upsert`) 공통(인시던트 `cc57b64`, C-5 계약 확장) | ~352 |
| `reload_worker_process_cache()` | SYSTEM_RELOAD 수신 시 config 캐시 리로드 | ~509 |
| `warmup_worker(rules, db_session_factory)` | 콜드스타트 제거 — 맵퍼·커넥션 프리로드 | ~525 |
| `process_pending_groups(db, group_order, groups, rules, db_session_factory, batch_wake_ts)` | 배치 내 그룹 순차 처리 — 실패 그룹 skip(HOL 블로킹 제거, F5) | ~573 |
| `sweep_undelivered_broadcasts(db, rules, db_session_factory)` | 통지 미확정 행 안전망 스윕(F1) | ~690 |
| `start_chain_ingestion_worker(db_session_factory)` | **메인 루프** — LISTEN 대기, 리로드 체크(1s 간격), 스윕, purge 스케줄. SYSTEM_RELOAD 블록(~834)에서 `models.refresh_dynamic_models(engine)`(지연 import) 호출 — 신규 테이블 CREATE 보충 안전망(이슈 #7) | ~768 |

---

## 5. 소형 서버 모듈

### `server/database/models.py` (~478줄) — ORM + 동적 모델/런타임 DDL
정적 ORM 클래스(`DataRow`/`AuditLog`/`DatabaseOutbox`/`FileIngestionLog`/`CellOverwrite`/`CellSource`, ~7–180)와 **그래프 3모델**, config 주도 동적 테이블 관리 함수.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `class GraphNode` | 그래프 노드 — `(label, identity_key)` UNIQUE, props JSONB | ~182 |
| `class GraphEdge` | 그래프 엣지 — (from,type)/(to,type) 인덱스, `(from,type,to,source_name)` UNIQUE, `idx_graph_edges_row_ref(source_row_ref)` | ~199 |
| `class GraphSyncState` | materializer outbox 소비 커서(id=1 단일 행, `last_outbox_id`) | ~227 |
| `DYNAMIC_TABLES` | 동적 테이블 싱글턴(`sys._dynamic_tables_singleton`) | ~245 |
| `init_dynamic_models(config_dict)` | config → 동적 ORM 클래스 생성·등록 | ~248 |
| `sync_dynamic_tables_schema(engine)` | ⚠️ 이름과 달리 **존재하는 테이블의 ALTER 전용**(`has_table` 아니면 skip — 신규 CREATE 안 함). 부팅 경로에서만 호출 | ~335 |
| `_runtime_ddl_lock` | in-process DDL 직렬화 락(watchdog 스레드 vs reload-configs 요청 스레드) | ~372 |
| `create_missing_dynamic_tables(engine) -> list[str]` | **신규 테이블 한정 물리 CREATE**(이슈 #7) — information_schema 게이트 + `checkfirst=True` + 테이블별 독립 트랜잭션(실패 자체 rollback). 기존 테이블 런타임 ALTER는 범위 밖(C-8) | ~375 |
| `ensure_graph_tables(engine) -> list` | 그래프 3테이블 생성(#7 패턴: 게이트+checkfirst+락+실패 격리) | ~416 |
| `refresh_dynamic_models(engine=None) -> list[str]` | **핫리로드 공용 진입점** — config 디스크 재로드 → `crud.TABLE_CONFIG` 싱글턴 갱신(빈/손상 config 시 기존 보존) → `init_dynamic_models` → engine 지정 시 물리 CREATE(+그래프 테이블 보장). 호출처: main `reload_local_process_cache` / config_watcher(간접) / run_watcher·chain worker·graph worker SYSTEM_RELOAD | ~453 |

### `server/ontology_config.py` (~305줄) — 온톨로지 매핑 v2 로더/검증
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `validate_ontology_mapping(raw_config, known_tables=None) -> dict` | v2 검증 — description 필수(테이블/엣지), 컬럼 존재 검증, 테이블 단위 스킵, 공간 속성 파싱, v1/`__`키 무시 | ~179 |
| `synthesize_enrichment_mappings(mappings, enrichment_rules) -> dict` | enrichment rule → `RESOLVED_AS` 엣지 자동 승격(`source_override="user"`, 사용자 정의 우선) | ~218 |
| `load_ontology_mappings(path=None, known_tables=None, include_enrichment=True) -> dict` | 로드 진입점(materializer·`/graph/mapping-summary` 공용 신호원) | ~280 |

### `server/graph_materializer.py` (~575줄) — 그래프 승격 코어
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `compose_identity(values) -> str\|None` | identity 조립 — `"\|"` 조인 + 이스케이프(`\`→`\\`, `\|`→`\\\|`) + float 정수 안정화 | ~54 |
| `flatten_payload_data(data)` / `extract_graph_items(table_name, rows, mapping, ...)` | 이벤트 행 → 노드/엣지 산출. 엣지 소스 = source_override 또는 식별 컬럼 winner들의 **최저 서열(보수적)** | ~89/100 |
| `bulk_upsert_nodes(db, node_map, chunk_size=1000) -> dict` | 방언별 ON CONFLICT + props shallow-merge(PG `\|\|`) | ~208 |
| `_retarget_stale_edges(db, rows, chunk_size) -> int` | 재교정 시 `(from_node, type, source_row_ref)` 스코프 stale 타깃 삭제 | ~249 |
| `bulk_upsert_edges(db, edges, node_ids, chunk_size=1000) -> int` | 엣지 벌크 UPSERT | ~301 |
| `materialize_rows(...)` / `materialize_events(db, events, mappings, chunk_size) -> stats` | 증분 소비 본체(DELETE 스킵+카운트) | ~358/373 |
| `_load_best_cell_sources(...)` / `attach_col_sources(db, table_name, rows, mapping)` | provenance 결정 단일 지점 — CellSource winner 로드(crud 서열, row_id IN 청킹). 증분·resync 공용 | ~441/473 |
| `resync_table(db, table_name, mappings, chunk_size=1000, row_ids=None, chunk_hook=None, stamp_synced=True) -> stats` | 백필/복구 — 키셋 청킹(C-7), row_ids 슬라이스 모드, Neo4j 청크 훅 | ~491 |

### `server/graph_sync_worker.py` (~994줄) — 그래프 워커 (materializer 루프 + 백필 API :8090)
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_load_graph_mappings()` / `_get_or_init_graph_cursor(db)` / `_reload_graph_worker_configs()` | 매핑 로드 / 커서 초기화(최초=현재 최대 outbox id) / SYSTEM_RELOAD 리로드(이슈 #8) | ~474/482/521 |
| `run_graph_materializer_loop()` | **메인 루프** — LISTEN/NOTIFY + keyset 커서, 배치 본체 `_run_one_batch`를 `asyncio.to_thread` 격리, `[GraphLatency]` 계측 | ~545 |
| `get_row_data_for_sync(db, table_name, row_ids)` | ⚠️ DEPRECATED(신규 배선 금지) | ~642 |
| `_neo4j_chunk_hook_factory(table_name)` | Neo4j 병행 경로 청크 훅(G3 인터페이스 보존) | ~822 |
| `execute_manual_sync(table_name, row_ids) -> dict` | `/sync` 백필 — 키셋 청킹 + 테이블당 `batch_refresh_required` 1건 + to_thread, `"all"` 지원 | ~845 |
| `startup_event()` | TABLE_CONFIG 동기화 + `ensure_graph_tables` + 루프 기동(`GRAPH_MATERIALIZER_ENABLED`) | ~964 |

### `server/parsers/std_parser.py` (~222줄) — 무스크립트 표준 파서
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `is_std_supported(file_path) -> bool` | 확장자 게이트(csv/tsv/txt) | ~31 |
| `_resolve_delimiter` / `_build_header_map` / `_resolve_key_groups` / `_row_has_key` / `_map_record` | 구분자 추정·헤더↔컬럼 매핑·키 검증 | ~36–127 |
| `_iter_rows(file_path, encoding, delimiter, header_map, key_groups)` | 스트리밍 행 이터레이터 | ~144 |
| `parse_std_file(file_path, table_info, table_name) -> (row_iter, total_rows, skipped_no_key)` | **진입점** — 키 결측 행은 스킵 카운트(파일 전체 거부 안 함), 헤더 실패 시 ValueError | ~155 |

### `server/enrichment_config.py` (~299줄) — 인리치먼트 규칙 로더/검증
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_resolve_view_query` / `_validate_view_sql(sql, decision_key)` | 참조 뷰 SQL 검증(SELECT 전용 등) | ~59/81 |
| `_normalize_reference_views` / `_validate_rule(name, raw, known_tables)` | 규칙 정규화·검증 | ~103/139 |
| `validate_enrichment_rules(raw_config, known_tables) -> list` | 전체 검증 진입점 | ~231 |
| `load_enrichment_rules(path, known_tables)` / `load_enrichment_chain_rules(...)` | 로드 / **체인 룰 형태로 변환**(rule["enrichment"] 내장) | ~250/264 |
| `to_public_rule(rule) -> dict` | 클라이언트 공개용 필드만 추출 | ~286 |

### `server/enrichment_mapper.py` (~177줄) — 인리치먼트 dedup 맵퍼
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_recount_affected_keys(db, source_table, decision_key, key_raw_values) -> dict` | 영향 키의 소스 행 재집계 | ~33 |
| `map_enrichment_dedup(db, payloads, rule=None)` | **진입점**(체인 워커가 호출) — 배치 payload → decision_key당 1행 upsert 목록 생성 | ~64 |

### `server/ingestion_activity.py` (~149줄) — [P1 신규] 인제션 진행 스냅샷 레지스트리
웹서버 인메모리(스레드 안전). 유입 3종: ① `/internal/events/ingestion-state`(heavy 명시 통지) ② `file_ingestion_progress` 브로드캐스트 인터셉트(normal 엔트리는 이 경로로만 생성 — lane 비오염) ③ file-processed 시 제거. 파일명 키는 `get_basename` 정규화로 일치. 모듈 싱글턴 `registry`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `STALE_ENTRY_TTL_SECONDS=30분` / `STALE_QUEUED_TTL_SECONDS=24h` | 고아 퇴거 TTL — 상태별 차등(QA F1: QUEUED는 24h, watcher 재기동 스윕이 자가 치유) | ~25/33 |
| `class IngestionActivityRegistry` | 레지스트리 본체(생성자에 ttl 주입 가능 — 테스트용) | ~36 |
| ├ `apply_state(state)` | QUEUED/PROCESSING/FINISHED 상태 반영(FINISHED=제거, 멱등) | ~67 |
| ├ `apply_progress(table_name, filename, progress, processed_rows, total_rows)` | 진행률 병합(없으면 normal 엔트리 생성) | ~95 |
| ├ `remove(table_name, filename)` | 멱등 제거 | ~115 |
| └ `_ttl_for(entry)` / `snapshot() -> list` / `clear()` | 상태별 TTL / **조회 스냅샷(+TTL 퇴거)** — `/admin/file-ingestion/active`가 서빙 / 초기화 | ~122/126/143 |

### `server/bonding_plan.py` (~410줄) — [본딩 M1] 역할 바인딩 config 로더 + 집계 코어
`config/bonding_plan_config.json`(gitignored, `.sample` tracked) — 역할(process_history/defect/eds_fail/used_chips/total_chips)→실테이블·컬럼 바인딩. 테스트: `tests/test_bonding_plan.py`(20개, `bdp_test_*`).

> **좌표 변환은 이 모듈에 없다 (2026-07-27 일원화).** 구 `normalize_align`/`make_align_transform`/`align_status_label`은 **삭제**됐고 정렬은 `map_overlay.resolve_map_transform`(메타 델타 유도)을 경유한다. `sources[].align` config 선언도 폐기 — 정렬의 근거는 `wafer_map_metadata` 하나뿐이다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `load_bonding_plan_config(path=None) -> dict` | config 로드·검증(미연결 역할은 부분 가동) | ~44 |
| `CANONICAL_FRAME_ROLES` (상수) | canonical(CORE) 프레임 후보 순서 `("total_chips","defect","eds_fail")` — **좌표를 바인딩한 첫 역할**이 기준을 정의하며 그 역할에 메타가 없으면 canonical은 None(뒤 역할로 넘어가지 않는다 — 넘어가면 회전된 계측 맵이 기준을 참칭해 조용히 identity가 된다) | ~45 |
| `parse_region(region_str)` / `clamp_rects(rects, grid)` | region rects 파서(잘못된 형식 → 400 소재) / canonical 메타 치수로 클램프(완전 밖 rect 제거) | ~213/239 |
| `load_map_meta(db, config, target_table, map_id, cache=None)` | wafer_map_metadata의 **grid_metadata 원본 dict** 조회(config `map_metadata` 바인딩 경유). 정렬 유도의 근거이므로 격자 치수만 잘라 쓰면 안 된다. `cache`는 요청 경계 스냅샷(N+1 금지) | ~137 |
| `load_grid_meta(db, config, target_table, map_id, cache=None)` | 격자 규격만 필요한 호출자용 축약(region rect 클램프 전용) | ~180 |
| `get_core_summary(db, lot, slot, rects=None, config=None) -> dict` | **집계 진입점** — 역할별 카운트(맵 모드 fail_values 필터, used_chips distinct), `remaining = total − defect − eds_fail − used`(음수 가능 — 과도기), history 50건+warnings, region 교차(좌표 하드캡 100k, 응답 미포함) | ~344 |

> ✅ **A2 해소 (2026-07-27)** — bbox 항 없는 사본은 삭제됐다. 착수 전제였던 "휴면"은 사실이 아니었다 — `bonding_plan_config.json`·`transfer_plan_config.json` 둘 다 `eds_fail`에 `rotation:180`을 라이브로 선언하고 있었고, 그 값은 `eds_fail_map` 메타의 rotation과 동일했다(선언이 메타의 중복). 라이브 규격(40×40)은 bbox가 0이라 두 구현 결과가 1288셀 전건 일치 → **가용량 수치 변화 없음**. [히스토리](../history/20260727_004500_align_consolidation_meta_single_source.md)

### `server/ingestion_checkpoint.py` (~258줄) — [P2 신규] 오프셋 체크포인트 + 파일 해시 dedup
저장소는 신규 테이블 **`file_ingestion_checkpoints`**(`UNIQUE(table_name, file_signature)` = `idx_fic_identity`). `FileIngestionLog`에 컬럼을 붙이지 않은 이유는 `create_all`이 ALTER를 하지 않아 **조회 프로세스보다 먼저 도는 마이그레이션**이 필요해지기 때문(운영 DB `UndefinedColumn` 500 회피 — 총괄 승인 판단). 테스트: `tests/test_ingestion_checkpoint.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `SIGNATURE_ALGO="sha256"` / `STATUS_IN_PROGRESS` / `STATUS_DONE` / `FORCE_REINGEST_TOKEN="__force__"` | 시그니처 알고리즘·상태 어휘·강제 재처리 파일명 토큰 | ~51/53/54/58 |
| `compute_file_signature(file_path) -> str\|None` | **전체 파일** 1MB 스트리밍 해시 → `sha256:<size>:<digest>`. 샘플링 아님 — 500MB 0.535초 실측(드릴 총 415초의 0.004%)이라 정확성을 택했다. `OSError`면 경고 후 None(체크포인트·dedup 비활성), `PermissionError`는 **재raise**(호출자 재시도 경로로) | ~61 |
| `is_force_reingest(filename) -> bool` | 파일명에 `__force__` 토큰(대소문자 무시) | ~88 |
| `class CheckpointPlan` (+`disabled(note)` classmethod, `is_resume` property) | 파일 1건의 계획 값 객체 — 비활성 사유(note)도 detail·이력에 노출 | ~93/116/122 |
| `find_checkpoint(db, table_name, file_signature)` / `find_completed_ingestion(...)` | UNIQUE 인덱스 단일행 조회 / 동일 내용 `DONE` 여부(dedup 판정) | ~132/142 |
| `plan_ingestion(db, table_name, file_signature, filename, filepath, total_rows, source_kind, force_restart=False) -> CheckpointPlan` | **재개 판정** — `force_restart` 아님 ∧ `status != DONE` ∧ `source_kind` 일치 ∧ `total_rows` 일치 ∧ `0 ≤ processed_rows ≤ total_rows`가 **전부** 성립할 때만 `resume_from = processed_rows`. 하나라도 어긋나면 0부터 + `[resume-abort] … 사유:` note를 WARNING·`row.note`에 남긴다(조용한 재처리 금지) | ~150 |
| `record_chunk_progress(db, plan, processed_rows, chunk_index)` | **청크 적재와 같은 세션·같은 트랜잭션**에서 오프셋 Core UPDATE — "커밋된 행 수 == 기록된 오프셋" 원자성의 근거 | ~218 |
| `mark_done(db, plan, processed_rows=None, note=None)` | 성공 확정(`status=DONE`) — 이후 dedup skip 대상 | ~243 |

### `server/map_overlay.py` (~698줄) — [M2 신규] 범용 맵 오버레이 (계획 전용 아님 — 맵 인프라)
`config/map_overlay_config.json`(gitignored, `.sample` tracked) — 키 구조만: `table_bindings.{table}.columns{x,y,val,key_columns}`, `paint_lock.{"*"|table}{enabled,blocking_values,from_overlay,message}`. `APIRouter` 없음 — `main.py`가 `@app.get`으로 직접 등록해 위임한다. 테스트: `tests/test_map_overlay.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `MAX_OVERLAY_CELLS=20,000` / `MAX_OVERLAY_SOURCES=8` | 오버레이 1종당 셀 상한(초과 시 `truncated:true`) / 요청당 소스 상한 | ~68/69 |
| `STATUS_OK\|ALIGN_UNAVAILABLE\|SOURCE_MISSING\|NO_DATA` / `ALIGN_ORIGIN_DERIVED\|IDENTITY` | 엔트리 status 어휘 / align 결정 출처 마커. **`DECLARED`/`DEFAULT`는 선언 레이어와 함께 삭제됐다**(2026-07-27) | ~71–77 |
| `ALIGN_ORIGIN_UNRESOLVABLE` | 구 QA-B3 가드 유물 — **프레임 합성(A1) 도입 후 더 이상 발화하지 않는다**(상수만 잔존) | ~82 |
| `load_overlay_config(path=None)` / `load_map_meta(db, target_table, map_id)` | config 로드(부재·손상 시 `{}` — 에러 아님) / `wafer_map_metadata`의 `grid_metadata` 조회 | ~85/106 |
| `_rotation_of` / `_side_of` / `_y_invert_of` / `_phys_signature` | 메타 정규화 헬퍼 — `_phys_signature`는 `phys_*` 6값 튜플(하나라도 없으면 None = bbox 재현 불가) | ~128/165/169/177 |
| `_grid_of(meta)` | 메타 선언 그대로의 **물리(canonical) 격자 규격**. (`_frame_grid_of`는 선언 경로 전용이었으므로 함께 삭제) | ~133 |
| `frame_axes(meta)` | 프레임 정의 8축 튜플 `(rot, side, y_invert, start_x, start_y, cols, rows, phys_sig)` — identity 지름길 판정·transformer 캐시 키 | ~187 |
| **`_frame_phys_params(meta)`** | **[A1 신설 — 이 배치의 핵심]** 물리 규격 → **프레임 축 규격**. `is_cell_inside_wafer(c, r, …)`는 프레임 인덱스를 받으므로 rot 90/270에서 **칩 피치를 스왑**하고 back에서 `off_x` 부호를 뒤집는다. 유일 호출자는 `_frame_transformer`. **보정을 이 모듈 안에 가둔 것이 계약** — `WaferMapCoordinateTransformer`·`PhysicalWaferEngine`은 무수정(`bonding_plan.py`가 같은 클래스를 공유) | ~205 |
| `_frame_transformer(meta, grid)` | transformer(+engine) 생성 후 `frame_axes` 키로 캐시(`_FRAME_TF_CACHE`, 상한 512 초과 시 전체 clear) | ~256 |
| `make_frame_transform(source_meta, target_meta)` | **소스 프레임 → 물리 → 타깃 프레임** 합성 변환기. 메타/격자/phys 부재·물리 치수 불일치 시 `ValueError` | ~286 |
| `_align_summary(rotation, flip)` / `align_status_label(align)` | 표시용 요약 dict(변환에는 안 쓰인다) / 상태 문자열 마커 `aligned:180` 등 — **`bonding_plan`에서 이관**(변환 소유 모듈이 마커도 소유) | ~322/331 |
| `resolve_align(source_meta, target_meta) -> (align\|None, origin, note)` | **align 결정 규율** — 메타 델타 유도 > **identity**(메타 부재는 실패가 아니라 등록 누락 신호). origin은 `derived`/`identity` 둘뿐 | ~350 |
| **`resolve_map_transform(source_meta, target_meta) -> (transform\|None, align, origin, note)`** | **서버의 단일 좌표 변환 진입점.** 오버레이(그리기)와 가용량 산출(`bonding_plan`/`transfer_plan`)이 **같은 이 함수**를 쓴다. transform None = identity, 계산 불가 시 `ValueError`(호출자가 `align_unavailable`로 표면화) | ~390 |
| `_pure_translation(...)` / `align_applied_payload(align, origin, note, translation)` | derived이고 rot/side/y_invert/격자/phys가 전부 같을 때만 `(dx,dy)` / 클라 표시용 `{rotation, flip, offset, origin, note?}` | ~396/412 |
| `parse_sources(spec) -> [(table, key\|None)]` | `"table"` / `"table:key"` CSV 파싱 — 8종 초과·빈 값은 `ValueError`(→400) | ~435 |
| `derive_table_binding(table)` / `resolve_binding(cfg, table)` | `table_config`에서 x/y/val·key_columns 자동 유도(`VAL_CANDIDATES` 순, 시스템 컬럼 제외) / **선언 우선 + 유도 폴백** | ~467/505 |
| `build_key_filters(model, binding, map_key)` | `_` 조인 복합 map_key를 key_columns로 분해해 ORM equality 필터 생성(마지막 컬럼이 나머지 흡수) | ~517 |
| `get_overlay(db, cfg, target_table, target_key, sources, cell_cap=…) -> dict` | **메인 진입점** — 소스별 바인딩·align 해결 → 셀 조회 → 타깃 프레임 좌표 변환 → `{target, overlays[], cell_cap}`. `eqp` 인자는 `by_eqp`와 함께 제거(엔드포인트 쿼리 파라미터는 no-op으로 존치 — 축소는 총괄 승인 사항) | ~520 |
| `get_paint_rules(cfg, table=None) -> dict` | `paint_lock`의 `"*"` 기본 + 테이블별 선언 머지 → `{enabled, blocking_values, from_overlay, message}` | ~679 |

> `resolve_binding`·`build_key_filters`는 **`transfer_plan.py`도 재사용**한다(모듈 간 공용 헬퍼 2개).
>
> **소비자 지도 (2026-07-27 정렬 일원화 이후)**: 이 모듈의 정렬 함수군을 쓰는 것은 ① `/api/maps/overlay` 엔드포인트 ② **`bonding_plan.get_core_summary`** ③ **`transfer_plan._canonical_fail_set`** ④ `test_map_overlay.py`다. ②③이 이번에 배선됐고(구 A2), 그 결과 **정확한 구현이 운영 소비자를 갖게 됐다** — 종전에는 맞는 구현이 엔드포인트에서만 돌고 가용량은 안 고쳐진 사본으로 계산됐다. **맵 에디터 클라는 이 엔드포인트를 더 이상 호출하지 않는다**(변환은 클라 단일 구현 — [§7 `map_editor.js`](#7-client2src--웹-클라이언트)). `transfer_plan.py`는 정렬 함수 외에 바인딩·config 헬퍼 3개(`resolve_binding`/`build_key_filters`/`load_overlay_config`)도 쓴다.
>
> **구현 개수**: 서버 1(이 모듈) + 클라 1(렌더) = **2**. 가용량이 서버에서 계산되는 한 이것이 하한이다.

### `server/transfer_plan.py` (~1,429줄) — [M2 신규] Universal Transfer Plan 엔진 (v2 = 계획 정체성이 곧 맵 정체성)
`config/transfer_plan_config.json`(gitignored, `.sample` tracked) — `stages.{name}.{source_kind, target_kind, target_map{table,preset}, source{...} \| source_config_ref}` + `plan_store.{doe, doe_source, source_region}`. 테스트: `tests/test_transfer_plan.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `MAX_ORIGIN_POINTS/MAX_FAIL_POINTS=100k` · `MAX_BY_CORE=500` · `MAX_DOE_PER_PLAN=500` · `MAX_PLAN_VALUES=1000` · `MAX_SOURCES_PER_DOE=64` · `MAX_REGION_CELLS=100k` | 하드캡 일습(무제한 로드 금지) | ~76–83 |
| `WARN_*` 12종 / `EFFECT_*` 4종 | validate·강등 경고 타입과 **효과 분류**(`remaining_overstated`/`total_unknown`/`by_core_degraded`/`history_incomplete`) | ~88–112 |
| `load_transfer_plan_config(path=None)` / `get_stages(cfg)` | config 로드(부재·손상 시 부분 가동) / stages dict 추출 | ~119/136 |
| `_resolve(src_cfg, required)` / `_binding_status(...)` / `_stage_role_statuses(stage_cfg)` / `_plan_store_statuses(cfg)` | 바인딩 → (model, 컬럼맵) / `connected`\|`missing` / stage 역할별·plan_store 역할별 상태 | ~150/162/169/200 |
| **`stage_of_table(cfg, ref_table)`** | **[v2 핵심] `stages.*.target_map.table` 역인덱스** — 열린 테이블에서 stage를 유도한다(별도 stage 선택 UI 폐기의 근거) | ~225 |
| `list_stages(cfg)` | `GET /api/transfer-plan/stages` 응답 `{stages[], plan_store}` | ~242 |
| `_status_is_degraded` / `_degradation_effect(role, fail_roles)` / `assess_degradation(statuses, fail_roles)` | **[QA F1 1층]** 역할 강등 탐지 → `(경고 리스트, remaining_reliable, total_reliable)` | ~263/276/290 |
| `build_chips_block(total, fail_breakdown, transferred, remaining, remaining_reliable, total_reliable)` | **[QA F1 3층]** chips 블록 조립 + **음수 remaining 불변식**(전 역할 connected여도 음수면 신뢰 박탈). 신뢰불가면 `remaining: null`을 내려 **오표시를 구조적으로 차단**하고, `total_reliable ∧ remaining≥0`일 때만 `remaining_upper_bound` 부가 | ~329 |
| `load_source_region(...)` / `_region_block(...)` / `_core_region_counts(...)` | 계획이 이 소스에서 쓸 셀 집합 로드(**현재 휴면** — 라이브 config에 `plan_store.source_region` 미선언이라 항상 None) / 영역 내 집계 / core-kind 어댑터 | ~370/404/430 |
| `_reshape_m1_summary(m1, stage_name, stage_cfg)` | M1 `bonding_plan.get_core_summary` 응답을 M2 공통 형태로 재성형(같은 강등 규율 적용) | ~480 |
| `_canonical_origin_meta(...)` / `_canonical_fail_set(...)` | origin-frame 원천의 **canonical 맵 메타** 로드 — 좌표를 바인딩한 **첫** 원천이 기준을 정의하고 그 원천에 메타가 없으면 None(뒤로 넘어가지 않는다. 넘어가면 회전된 계측 맵이 기준을 참칭해 조용한 과소 집계) · 코어당 1회 캐시 / 코어 1장 fail 좌표를 `map_overlay.resolve_map_transform`으로 canonical 프레임 set에 사상(미해결이면 `(None, "align_unavailable", False)`; **소스 메타만 있고 canonical이 없는 비대칭도 거절**) | ~545/580 |
| `_collect_history(db, source_cfg, lot, slot)` | process_history 최근 N건(시간 오름차순) + result fail 경고 | ~607 |
| **`_summarize_inline(db, stage_name, stage_cfg, lot, slot, region=None)`** | **가용 엔진 정본(tape-kind)** — `origin_log` 연결 시 `remaining = total − \|fail_union ∪ used_set\|`(칩 단위 합집합 — 이중 감산 없음), 미해석 시 M1식 감산 폴백. `by_core` 7키(`core_id, core_lot, core_slot, total, fail, used, remaining`) + `by_core_origin` 마커 `"log"`(정확) \| `"area_map"`(강등 — `fail=None`으로 0 위장 금지) | ~654 |
| `get_stage_source_summary(db, cfg, stage_name, lot, slot, bp_config=None, ref_table=None, map_key=None)` | **핸들러 진입점** — M1 ref 경로(reshape) / inline 경로 분기, 미선언 stage는 `KeyError`(→404) | ~1010 |
| `_band_range(band)` / `_painted_values(db, ref_table, map_key, overlay_cfg)` | STACK 구간 표기(`1`/`2-11`/`H1~H2`) 파싱(못 읽으면 경고 없이 불참) / **대상 맵 자신**의 셀 값 분포 group-by(`map_overlay.resolve_binding`·`build_key_filters` 재사용) | ~1066/1088 |
| `validate_plan(db, cfg, ref_table, map_key, overlay_cfg=None)` | **핸들러 진입점** — `remaining_reliable=False`면 부족·fail 판정을 **전부 생략**하고 `availability_unreliable`만 발행(오염된 과대 remaining으로 "부족 아님"을 판정하지 않는다). 최종 `status`는 `ok`/`warnings`/**`unverified`** 3값 — **"검사 안 함"과 "이상 없음"을 같은 값으로 내지 않는다.** `plan_store.doe` 미구성은 `LookupError`(→404) | ~1126 |

---

## 6. 기타 서버 모듈 (한줄 요약)

라인 앵커 미수록 — 필요 시 해당 파일에서 Grep.

| 파일 | 책임 |
|---|---|
| `server/database/models.py` | ORM — 정적 + `DYNAMIC_TABLES` + 런타임 DDL(핫리로드 CREATE) — **함수 앵커는 [§5](#5-소형-서버-모듈)**. [P2] `class FileIngestionCheckpoint`(~112, `__tablename__="file_ingestion_checkpoints"` ~132) — `table_name/file_signature/filename/filepath/source_kind/total_rows/processed_rows/chunk_index/status/note/started_at/updated_at`, `Index("idx_fic_identity", table_name, file_signature, unique=True)`(~154) + `idx_fic_signature`. 준비 함수 `ensure_ingestion_checkpoint_table(engine)`(~469, information_schema 게이트 + `checkfirst` + `_runtime_ddl_lock`) |
| `server/audit_cache.py` | 최근 감사 로그 인메모리 캐시. [P2/이슈 #10] `add_logs_batch(logs_list, message_total_count=None)`(~109) — 인자 의미가 "이 메시지 1건이 나르는 **절단 전 실건수**"이고 `group["total_count"] += contribution`으로 **누적**한다(구 `override_total_count`는 SET 대입이라 멀티 target-table tx에서 마지막 메시지가 총계를 지웠다). 한 배치에 tx가 2개 이상 섞이면 귀속 불가로 `len(logs)` 폴백 + 1회 경고 |
| `server/database/schemas.py` | Pydantic — `GeneralUpdateItem/Batch` 등 API·배치 계약 |
| `server/database/database.py` | 엔진·SessionLocal·outbox 발화(`database_outbox` + NOTIFY) |
| `server/database/config_watcher.py` | table_config.json 변경 감시 → 동적 테이블 재구성. engine 분기(~44)에서 `create_missing_dynamic_tables` 선(先)호출 후 기존 sync(ALTER) — 직접 파일 편집 경로의 신규 테이블 CREATE(이슈 #7) |
| `server/graph_sync_worker.py` · `graph_materializer.py` · `ontology_config.py` | 온톨로지 그래프 트랙 — **함수 앵커는 [§5](#5-소형-서버-모듈)** |
| `server/run_auto_update.py` | 스케줄 기반 사용자 스크립트 자동 실행. 매 틱 제어 파일(`auto_update_control.json`)을 읽어 disabled 수집기는 실행 스킵+`last_status="SKIPPED"`+next_run 전진(핫 반영, 재활성화 시 백로그 폭주 없음). run-now는 active 무관 실행 |
| `server/event_constants.py` | 프로세스 간 내부 이벤트(`/internal/events/*`) 공용 상수 — `MAX_NOTIFY_CREATED_LOGS=500`(~14, 발신측 created_logs 절단 상한: 워처 `directory_watcher:1381` · 체인 워커 `:467` · 수신 `main.py:3564/3612` 공유) · [P2] `MAX_AUDIT_VALUE_CHARS=4096`(~22)과 `truncate_audit_value(value, max_chars)`(~25 — 반환 `(값, 절단여부)`, str은 `…[truncated: 총 N자]` 마커, dict/list는 타입·길이 플레이스홀더)를 `crud.create_audit_log`가 소비 |
| `server/scripts/setup_ingestion_checkpoint.py` | [P2] `file_ingestion_checkpoints`를 **프로세스 재기동 없이** 미리 생성(멱등) — 직접 SQL 없이 `models.ensure_ingestion_checkpoint_table(engine)` 호출 후 컬럼·인덱스 출력 |
| `server/scripts/setup_transfer_plan_indexes.py` | [M2] 전사 계획 엔진 진입 필터용 복합 인덱스 8종 `CREATE INDEX IF NOT EXISTS`(테이블별 information_schema 존재 게이트) — `dt_log(tape_lot,tape_slot)`·`dt_log(core_lot,core_slot)`·`dt_map(lot,slot)`·`map_doe(ref_table,map_key)`·`map_doe_source(ref_table,map_key)`·`map_source_region(...)`(휴면)·**`bonding_map(base)`**(Seq Scan 214ms → 0.345ms)·`sample_map(base)`. M1 인덱스는 `setup_bonding_plan_indexes.py` 담당 |
| `server/utils/auto_update_control.py` | auto-update 수집기 active 제어 파일(`config/auto_update_control.json`, gitignored) 공용 IO — `read_disabled_scripts`(fail-open)/`set_script_active`(tmp+`os.replace` 원자적 쓰기)/`validate_script_key`(경로 탈출 차단)/`resolve_script_file`. 웹서버 toggle·스케줄러 공유 |
| `run_decoupled_app.py`(루트) / `server/run_watcher.py` / `run_chain_worker.py` / `run_graph_sync.py` / `run_auto_update.py` | 프로세스 런처(5-프로세스 토폴로지). **API 서버는 전용 런처 파일이 없다** — `run_decoupled_app.py`가 `python -m uvicorn main:app --port 8080`을 직접 띄운다(`run_decoupled_app.py:42`). ~~`server/run_api.py`~~는 **존재하지 않는다**(2026-07-26 정정). run_watcher: `trigger_ws_ingestion_state`(~103 — [P1] 파일명 정규화 후 `/internal/events/ingestion-state` push, WorkspaceWatcher에 배선 ~261) · SYSTEM_RELOAD/재처리 폴러 `poll_pending_retries`(~136)는 `refresh_dynamic_models(engine)` 보충(이슈 #7) + `resolve_workspace_root` 역조회(별칭 대응) + 재처리를 `get_workspace_serial_lock`으로 감쌈(~215 — [P1 QA F3] heavy와 순서 계약 편입) |
| `server/utils/physical_wafer_engine.py` · `coordinate_transformer.py` | 웨이퍼 물리 좌표 엔진(맵 에디터 서버측) |
| `server/mappers/*` (gitignored) | 사용자 커스텀 체인 맵퍼 — **전수 Grep 시 반드시 포함** |
| `server/config/*.json` (gitignored) | table_config·chain_rules·enrichment_rules·ontology_mapping(v2 — `.sample`은 tracked) 등 사용자 설정 |

---

## 7. `client2/src/` — 웹 클라이언트

Vite + Vanilla ESM + AG-Grid. 멀티페이지 **6엔트리**(index/admin/map_editor/enrichment/graph/trace). 상태는 `state.js` 싱글턴(리액티브 아님 — 변조 후 명시적 리프레셔 호출).

### `state.js` (~49줄) — 전역 싱글턴
- `state` 객체: gridApi, currentTable/Columns/Types, 비즈니스키(`currentBusinessKey`/`currentCompositeKeySources`), ws, 셀 선택(`selectedCell`/`selectedCellsMap`/드래그), 이력 탭 데이터, 페이징(`currentSkip`/`pageCache`/`viewMode`), 트랜잭션 모드(`txModeActive`/`pendingTxEdits`), `isDesktop`.
- export: `updateVisibleColIndexMap()` (~37).

### `main.js` (~1,793줄) — index 페이지 오케스트레이터
- 진입 `init()`(~66, `initTraceEntry()` 호출 포함) → `setupEventListeners()`(~100, 거대 — 툴바·모달·키보드 전체 배선), `setupDragAndDrop()`(~1020).
- 셀 범위 `getSelectedCells()`(~1105), 소스 모달 `openSourcesModal/refreshSourcesList`(~1152/1177).
- 스마트 페이스트 `smartPasteViaIngestion()`(~1425) + `showClipboardTypeModal`(~1518).
- 트랜잭션 모드 커밋/롤백 `applyPendingTxEdits()`/`discardPendingTxEdits()`(~1692/1765).
- export 없음(엔트리) — 다른 모듈을 소비만 한다.

### `api.js` (~422줄) — REST 소비 계층 (경계 계약의 클라이언트측)
- export: `checkServerHealth`(~11) `loadTables`(~28) `switchTable`(~56, 말미에 `refreshTraceEntry()` fire-and-forget) `loadSchema`(~96) `fetchData(resetSkip)`(~124, 메인 조회+세션가드) `handleCellEdit(event)`(~217, 셀 편집→PUT updates) `addRows`(~364) `deleteSelectedRows`(~383).
- 소비 API: `/tables*`, `/tables/{t}/data`, `/schema`, PUT `/data/updates`, POST `rows`, `batch_delete`.

### `grid.js` (~526줄) — AG-Grid 구성
- export: `updateGridSortState`(~17) `updateLoadedCount`(~42) `updateViewModeUI`(~66) `updatePaginationUI`(~74) **`ensureCellObject(dataObj, colId)`**(~94, 셀 형태 `{value,is_overwrite,priority_source}` 정규화 — 셀 계약의 단일 관문) `buildColumnDefs`(~112) `renderGrid(initialRows)`(~254).

### `websocket.js` (~249줄) — 실시간 수신
- export: `initWebSocket`(~11, 재접속 백오프) `handleWebSocketMessage(msg)`(~72).
- 소비 이벤트: `file_ingestion_progress`(~73) `file_ingestion_completed`(~84) `batch_row_create`(~131) `batch_row_upsert`(~147) `batch_row_delete`(~229) `batch_refresh_required`(~244) → 델타 반영(`applyTransaction`)·페이지캐시 갱신.

### `ui.js` (~408줄) — 그리드 밖 UI 갱신
- export: `setupBeforeUnloadWarning`(~8) `updateSelectedCellUI`(~18) `updateTxModeUI`(~33) `setTransactionFilter`(~79) `applyValueToSelectedRange(newValue)`(~106, 범위 일괄 적용→배치 PUT) `updatePageCacheOnUpsert`(~260) `updateEnrichmentBadge`(~331) `notifyEnrichmentTableEvent`(~381) `updatePageCacheOnDelete`(~391).

### `clipboard.js` (~788줄) — 엑셀형 범위 선택/복붙
- export: `isCellInRange`(~8) `refreshRange`(~29) `refreshSelectedRangeDiff`(~57) `clearRangeSelection`(~92) `commitDragSelection`(~144) `getRangeSelectedTSV`(~172) `setupClipboardHandlers`(~281, copy/paste 이벤트 본체) `clearSelectedCells`(~617).

### `timeline.js` (~718줄) — 이력 타임라인 + 내비게이션
- export: `loadHistory`(~9) DOM 빌더 `createTimelineItemDom`/`createGlobalTimelineItemDom`(~50/103) 증분 렌더 `renderTimeline*`(~271–346) `renderSubDetails`(~362) `appendHistoryLocally`(~445) 로그→셀 점프 `navigateToLog`(~507)+`navigatorStep2/3`/`navigatorFinalScroll`/`releaseNavigationGuard`(~566–709).
- 소비 API: `/audit_logs/recent`, `/audit_logs/transaction/{tx}`.

### `map_editor.js` (~4,533줄) — 웨이퍼 맵 에디터 (단일 페이지 스크립트, export 없음)
- 좌표 변환 코어: `getPhysicalCoords`(~973) `getCellFromPhysicalCoords`(~1023) `getCellFromVisualCoords`(~1063) `getVisualCoords`(~1132) `getTransformedPhysicalConfig`(~1147) `getWaferBoundingBox`(~1080) `getScreenShift`(~1182) `isCellInsideWaferFast`/`isCellInsideWafer`(~1208/1246) — 회전/면반전 불변식은 [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md).
  - **[7d931dc] 프레임 창(frame window)** — `physFrameOverride`(~946) + `physNum`(~949)/`gridDimNum`(~958)/`withPhysFrame(frame, fn)`(~967). 변환 함수가 규격을 DOM에서 읽는 지점을 잠깐 갈아끼우는 장치로, **주입 지점은 `getTransformedPhysicalConfig`·`getWaferBoundingBox` 두 곳뿐**이다. `withPhysFrame`은 **동기 전용**(내부 `await` 금지 — `try/finally` 복원이 새면 조용한 오답). 기존 `parseFloat(v) || dflt` 규약(0 → 기본값) 보존.
- 캔버스 렌더: `renderGridCanvas`(~1598, 본체) `scheduleRenderGridCanvas`(~1561) `fitGridToWorkspace`(~1583) `updateNotchPosition`(~1939).
- 데이터 IO(REST — WS 아님): `loadExistingMap`(~2501) `pushMapData`(~2898, 저장 본체) `fetchGridMetaFor(table, mapId)`(~2468) 프리셋 `fetchAndRenderPresets`/`saveCustomPreset`/`deleteCustomPreset`(~1303/1409/1459) + `applyPresetObject`(~1359, `loadSelectedPreset` ~1392에서 추출한 공용 함수).
  - `fetchGridMetaFor`는 **404/405만 "규격 미등록"(null)**으로 읽고 그 외 실패는 **throw**한다(`[M2 fix]` — 종전엔 모든 실패가 null이라 오버레이가 조용히 identity로 폴백했다). `loadExistingMap`의 셀 레벨 `grid_metadata` 폴백(~2594–2604)은 **폐기 스킴**이며 어떤 맵 테이블도 스키마에 그 컬럼을 노출하지 않아 라이브에서 사문이다.
- 레전드/브러시: `renderLegendTable`(~2141) `selectBrush`(~2328) + `localStorage` 동기화 `load/saveLegendToStorage`(~1994/2012). `getCurrentMapKey`(~2019)는 **로드된 맵이 아니라 현재 메타 입력 필드**를 읽는다(오버레이 관문 F2의 근원).
- 편집 도구: `fillGrid`(~2869) `getEdgeClassification`(~3139) `selectEdgeCells`(~3219) `autoPaintE1E2`(~3246) `copyGridToExcel`(~3334).
- 프레임 스택: `snapshotEditorState`(~3506) `restoreEditorState`(~3549) `openMapFrame`(~3757) `popMapFrame`(~3808).
- **[M2] 페인트 잠금**(~36–148, 서버 선언 소비 — 구 `'F'` 하드코딩 대체): `isLockedValue`(~41) `isOverlayLocked`(~51) **`isProtectedFCell`(~63 — 편집 불가 판정의 단일 관문, 전 편집 경로가 여기로 수렴)** `applyPaintLockConfig`(~68) `fetchPaintRules`(~92, GET `/api/maps/paint-rules`) `updatePaintLockIndicator`(~126) `recomputeLockedCells`(~143). 404/405만 "선언 없음"(해제)이고 네트워크·5xx는 **직전 잠금 유지** + `source:'stale'` + 툴바 칩. ⚠️ **[QA C4 미해소] 콜드 스타트는 여전히 fail-open** — "직전 값"이 페이지 로드 직후엔 기본값 `NO_PAINT_LOCK{enabled:false}`(~37)라 첫 조회가 실패하면 8개 강제 지점이 열린 채 시작한다(칩은 뜨므로 **조용한** fail-open은 아님). 테이블 전환 시 실패하면 **이전 테이블의 잠금 값**을 새 테이블에 계속 적용한다(fail-closed 방향이라 안전하나 의미상 부정확).
- **[7d931dc] 오버레이 레이어**(~3850–4533) — **변환은 클라 단일 구현**이다. 계약은 [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md):
  - 상태 `OVERLAY_COLORS`(~3850) / `overlayLayers`(~3851, 레이어당 `{id, sourceTable, sourceKey, rawCells, frame, cells:Map(physKey→val), count, outside, color, visible, status, align, alignApplied, alignText, truncated, cap, failed, reason, targetOverride}`) / `activeOverlayLayers`(~3852) / `overlaySeq`(~3853) / `recomputeActiveOverlays`(~3855, 렌더 루프 내 재계산 금지) / `drawOverlayMarkers`(~3860, 렌더 호출 ~1760).
  - **프레임 계산**: `frameFromMeta(meta)`(~3884, `grid_metadata` JSON → 프레임 기술자. **없는 물리 항목은 undefined로 남겨** 현재 화면 값 폴백) / `currentFrame()`(~3911) / `resolveFrame(frame)`(~3924, 축 전부를 실값으로 확정) / `frameAxesKey(rf)`(~3941, 회전·면·y반전·START·치수·물리 6종 = identity/derived 판정의 유일한 근거).
  - **`projectCellsToPhys(cells, frame)`(~3952)** — 구 `overlayCellsToPhysMap`의 대체. `getCellFromVisualCoords` → `getPhysicalCoords`를 **소스 프레임을 씌운 채** 호출한다. `loadExistingMap` 셀 루프와 **같은 함수·같은 인자 순서**이며 다른 점은 규격을 소스 메타에서 읽는다는 것뿐 — **오버레이 전용 기하식은 0줄**이다.
  - `pushFailedOverlay`(~3971) — 실패도 목록 행으로 남긴다(같은 소스 중복은 갱신).
  - 소스 읽기: `OVERLAY_CELL_LIMIT=2000`(~3992, 메인 로드와 동일 상한) `fetchTableSchemaCached`(~3995) `deriveMapBinding(schema)`(~4010, 서버 `derive_table_binding` 규약을 `/tables/{t}/schema`에서 유도) `buildKeyFilters(keyColumns, mapKey)`(~4027, 서버 `build_key_filters`와 동일 — 마지막 컬럼이 나머지 흡수).
  - `addOverlayLayer(sourceTable, sourceKey, targetOverride)`(~4046) — **메인 로드와 코드 경로 완전 분리**. 흐름: ① 바인딩 유도 → ②③ `Promise.allSettled`로 셀 + 소스/타깃 메타 병렬 조회(셀 실패와 규격 실패를 다른 사유로 분리) → ④ 프레임 확정 → ⑤ `cols×rows` 호환성 관문 → ⑥ 정렬 요약 + 격자 밖 셀 카운트. 명명된 실패 status **4종**: `meta_unavailable` `binding_unavailable` `align_unavailable` `no_data`(+ 스키마·셀 조회 IO 실패는 일반 `error`). **구 `probeAlignDeclaration` 관문과 `align_unconfirmed`/`align_override_declared` 두 status는 서버 선언 레이어와 함께 삭제됐다**(2026-07-27) — 물어볼 선언이 없어졌다. 오버레이 추가의 REST 왕복도 하나 줄었다.
  - `removeOverlayLayer`(~4265) `toggleOverlayLayer`(~4272) `clearOverlayLayers`(~4281).
  - `overlayGeomSig`(~4294) / `currentGeomSignature`(~4296) / `syncOverlayGeometry`(~4313, 서명 변경 시 `rawCells`+`o.frame`에서 재투영, 렌더에서 훅 ~1637). ✅ **[QA C7 해소]** 서명이 `cols|rows|startX|startY|yInvert|rotation|side` + **물리 6종(`phys_wafer_dia/chip_x/chip_y/offset_x/offset_y/edge_margin`)**을 담는다. 단 소스 메타가 완비되면 재투영은 항등이라, 이 6종이 실제로 일하는 곳은 **물리 규격 미등록 폴백 경로**뿐이다.
  - `overlayAlignChip(o)`(~4336) — 정렬 상태 칩. 판정은 **`align.origin`으로만** 한다(rotation/flip/offset으로 판단 금지 — y반전·START만 다른 보정을 "무보정"으로 오표시한다).
  - `importOverlayToGrid(id)`(~4362) — 유일한 의도적 교차: 오버레이 셀을 `gridData`로만 가져온다(**서버 쓰기 없음**, `isProtectedFCell` 존중, 웨이퍼 밖 셀 스킵, 정체성 불변). `ensureLegendValues`(~4418)는 **로컬 legend 캐시만** 갱신한다(Push 전 서버 무접촉).
  - `renderOverlayList`(~4433) `handleAddOverlayClick`(~4487) `addOverlayForSource(sourceTable, lot, slot)`(~4520) `listOverlayLayers`(~4527) — 뒤 둘은 `transfer_plan.js`에 넘기는 컨트롤러 표면(~296–302). 세션 저장·복원에 `overlayLayers`+`overlayGeomSig` 포함(~3516/3589).
  - **오버레이 해제 지점 3곳**: 맵 로드 `loadExistingMap`(~2545, 토스트) · **테이블 전환 `switchTable`(~814, 토스트 — `251dbfd` 신설)** · 프레임 진입 `openMapFrame`(~3765, 무음). ⚠️ `251dbfd` 이전에는 **테이블 전환에서 해제되지 않았고**, 남아 있던 오버레이의 `가져오기`가 이전 테이블 값을 새 테이블에 써 넣을 수 있었다.
- [M2-v2] 전사 계획 배선: `initTransferPlan({...})`(~277, import ~6) + `notifyMapContext`(~821/2847/3102/3796–3820) `notifyLegendChanged`(~2110/2142/2342) `notifyPaintCounts`(~1513). rect 영역 선택 모드는 **전면 폐기**(값 페인팅이 정본 — 코드 부재).

### `transfer_plan.js` (~1,405줄) — [M2-v2] 전사 계획 사이드바 (map_editor.html에서 소비)
**「계획 = 지금 열어 편집 중인 그 맵」.** 계획 정체성은 `(ref_table, map_key)`이며 `plan_id`도 계획 맵 사본도 없다. 스타일은 `transfer_plan.css`. (구 M1 `bonding_plan.js`/`.css`는 `8e34804`에서 **삭제**됐다.)

- 상태 `S`(~58–83): `stages`/`stagesStatus` · `ctx{table,mapKey,loaded,depth,parent}` · `legendRows` · `doe: Map<value, Band[]>`(`Band = {seq, stack, need, materials[], knobs[]}`) · `openValue` · `counts` · `summaries` · `matMapState` · `keyColumns` · `savedAt`/`serverSavedAt` · `planTablesSupported` · **`doeServerLoaded`(~74)** · **`serverKeys{doe:Set, source:Set}`(~76)** · `saveError` · **`loadSeq`(~79)** · `matSeq` · `flash` · `navBusy`.
- 진입/통지 export: `initTransferPlan(paintController)`(~1302) `notifyMapContext(info={})`(~1220, 로드 오케스트레이션) `notifyLegendChanged`(~1284) `notifyPaintCounts(counts)`(~1293, **`textContent`만 패치** — 대형 그리드 페인팅 성능).
- **키 조립 유일 지점**: `doeRowKey(value, seq)`(~187) = `` `${table}|${mapKey}|${value}|${seq}` `` · `doeSourceRowKey(value, seq, lot, slot)`(~190) = 거기에 `|${lot}|${slot||''}`. 이 문자열이 `business_key_val`·`keep`·`serverKeys`를 **모두** 채운다. 테이블 상수 `map_doe`/`map_doe_source`(~40/41).
- **밴드(STACK)**: `band_seq`가 정수 **정체**, `stack_band`는 **자유 텍스트 라벨**(다중 구간 `1, 2-15, 16` — 파싱하지 않는다). `blankBand`(~196) `getBands`(~199) `nextBandSeq`(~206, `max+1` — **삭제 시 재번호 금지**: 재번호는 자식 `map_doe_source`를 전부 고아로 만든다) `getBand`(~217) `addBand`(~210).
- 서버 왕복: `putUpdates`(~888) `scheduleServerSave`(~912, 1200ms 디바운스) **`saveDoeToServer`(~919)** `pruneScoped(table, keyCol, keep, knownKeys)`(~1057, 3중 가드) **`loadDoeFromServer`(~1098 — 조회만 한다. `keys`를 반환할 뿐 권한을 세우지 않는다)** **`adoptServerDoe(r)`(~1189)**.
  - **[C1 불변식] `doeServerLoaded === true` ⇒ `S.doe`는 서버본에서 유래했다.** prune 권한(`serverKeys`/`doeServerLoaded`)이 생기는 **유일한 지점이 `adoptServerDoe`**이며 서버본 채택과 **원자적으로** 일어난다. 호출 지점은 둘뿐 — 맵 컨텍스트 로드(~1262, seq 가드 통과 후)와 저장 회복(~946).
  - 회복 사이클(~927–953)은 **쓰기 0건**으로 끝나고 로컬 초안을 보존한다(삭제뿐 아니라 **쓰기도 보류** — 로드 실패 후 편집하면 `band_seq`가 1부터 다시 매겨져 서버 행을 덮어썼다).
  - 절단 응답(`data.total > rows.length`)은 **로드 실패로 강등**한다(~1119/1150) — "안다"고 주장하지 않는다. ⚠️ **[QA C3 미해소] 조회 `limit=500`(~1068/1104)이 `map_doe`·`map_doe_source` 양쪽에 걸려 있어, 자재 행이 500을 넘는 계획은 매번 절단 → 매번 로드 실패 → 저장이 영구 보류된다**(20값 × 3구간 × 10자재 = 600행이면 도달). 회복 수단은 경고 토스트뿐. 서버 캡 `MAX_DOE_PER_PLAN=500`과의 정합·페이지네이션이 필요하다.
  - `loadSeq` 가드(~928/931, ~1230/1249/1272): 맵 전환 중 늦게 도착한 응답을 채택하지 않는다.
- 소스 요약: `getSourceSummary(lot, slot, force)`(~310, GET `/api/transfer-plan/source-summary`) `availableOf`(~339) `summaryStatusOf`(~347) `refreshMaterials`(~823) `rewardAfterReturn`(~790).
- 렌더: `renderPlanHead`(~380) `renderDoeList`(~418) `renderBand`(~469) `renderDoeDetail`(~498) `bindDoeList`(~530) `materialGroups`(~650) `renderMaterialPane`(~670) `renderAll`(~1199) `buildWorkspace`(~1205).
- 이동 허브: `openMaterial(lot, slot)`(~766) — **맵 간 이동의 유일 지점**(브레드크럼·뒤로가기 프레임 스택).
- 자재 수량 분배는 **`Math.ceil`**(서버 규약 일치 — `round`면 100/3매가 33×3=99로 부족이 숨는다).
- ⚠️ **`__held_*` 6함수(~1324–1405)는 명시적 보류 구역** — 호출자 없음. 검증/경고 UI는 사용자 지시로 미구현이다.

### `admin.js` (~2,643줄) — 어드민 페이지 (2026-07-25 전면 재작성 — 파이프라인 5탭, export 없음)
- 라우팅: `parseRoute`(~237) `applyRoute`(~249) — `#overview/#file/#chain/#autoupdate/#enrichment` + 구 별칭(`#outbox→chain` 등) + `#editor=<path>`. `switchTab(tabName, opts)`(~294, 해시 동기·Overview 전폭 레이아웃).
- 탭 데이터: `fetchData(options)`(~614, 탭당 병렬 fetch를 한 seq로 묶어 stale 렌더 차단 — [P1] File 탭은 `/admin/file-ingestion/active`도 병렬 수집 ~641) → 각 `render*Table` + 섹션 카운트 배지(`setSectionCount`), `clearRowHighlights`/`clearSelections`.
- [P1] File 탭 진행 중 섹션: `renderActiveIngestions`(~922, `#sec-active-ingestions` — HEAVY=badge-warning/normal=badge-success 배지·진행률 바·행 카운트·경과 + **재기동 경고 배너**, 항목 0이면 섹션 숨김) `scheduleActiveRefresh`(~904, 진행 항목 존재+File 탭 표시 중 한정 5s 경량 타이머 — `document.hidden` 시 스킵) `formatElapsed`(~892). 헬스 스트립 File 카드 warn·Overview 카드 진행 메트릭 통합.
- Overview: `fetchOverview`(~1301) `renderOverview`(~1427, 4카드+최근 이벤트+딥링크).
- 유기 연계: `renderLinkedFailTable`(~1209, AutoUpdate §오류 — 산출물 인제션 실패 교집합) `showEventDiagnostics`(~1998, +Edit Mapper 딥링크) `selectFileRow`(~1775, 파서 편집 딥링크).
- AutoUpdate 토글: `renderAutoUpdateTable`(~1128, 수집기별 Active 스위치·비활성 행 dim) `toggleCollectorActive`(~1671, POST `/admin/auto-update/toggle` — 낙관 갱신+실패 원복, fetchSeq 가드 table+script 키 재조회) `runAutoUpdateNow`(~1644, active 무관+툴팁). Overview 카드·헬스 스트립에 active/total 표기.
- Enrichment 탭: `renderEnrichmentTable`(~1238) `fetchEnrichmentStatus`(~2464, 15s TTL 캐시 — 스트립·탭·Overview 3소비처 공용).
- 에디터(공용 뷰): `initMonacoEditor`(~2183, pending open) `populateEditorPicker`(~2240) `selectEditorFile`(~2286, dirty confirm) `openInlineEditor`(~2366). (구 좌측 파일트리 `renderEditorTree` 일습은 피커로 대체·삭제됨)
- 소비 API: `/admin/*` 전역 + `/enrichment/rules` + `/tables/{t}/data`(결손 카운트).

### `enrichment.js` (~754줄) — 인리치먼트 컨베이어 페이지 (export 없음)
- 규칙: `loadRules`(~69) `selectRule`(~116) `rebuildGrid`(~151). 워크리스트: `fetchWorklist`(~190) `fetchTotalAll`(~241) `refillIfNeeded`(~257).
- 입력 흐름: `renderDetail`(~310) `onInputKeydown`(~384) `moveSelection`(~402) `saveCurrent`(~427, PUT `/data/updates`).
- 참조 패널: `initReferencePanel`(~517) `loadActiveReference`(~580) `renderRefTable`(~637).
- 소비 API: `/enrichment/rules`, `/enrichment/rules/{r}/references/{i}`, `/tables/{t}/data`, PUT `/data/updates`.

### `graph_viewer.js` (~1,244줄) — 지식그래프 서브그래프 뷰어 (graph.html 엔트리, 무라이브러리)
- 조회·URL: `syncUrl`(~343, `?label=&identity=` pushState — 동일 URL 중복 push 방지) `explore(label, identity, opts)`(~354, `/graph/neighbors` 조회→BFS 동심원 레이아웃. `opts.history: 'push'|'replace'|'none'`) `renderStats`(~158, `/graph/stats` 카운트 카드+라벨 색 팔레트 — **라벨 카드 클릭 → 노드 리스트**).
- **라벨 노드 리스트**(`df63f3a` 신설): `openLabelNodes`(~220) `closeLabelNodes`(~228, back → Stats 복귀) `fetchLabelNodesPage`(~234, 빈 q + label 서버 리스팅 — `LABEL_LIST_PAGE=200`(~24, 서버 캡과 동일)·offset "더 보기"·seq 가드) `renderLabelNodesBlock`(~264, 로드수/총수 헤더·행 클릭 → `explore` 연동). `showStatsView/showGraphView`(~315/321).
- 렌더: `layoutGraph`(~432) `renderCanvas`(~537, 캔버스 본체 — 테마 색 1회 캐싱+`themechange` 재캐싱, 상시 rAF 없음).
- **Connections 테이블**(`18218da` 신설): `connectionRows(nodeId, edges, nodesById)`(~707) `propsSummary`(~731) `selectNode(node, opts)`(~745, 선택 확립+`connSeq` stale 가드) `fetchNodeConnections`(~766, 비중심 노드 depth-1 재조회 보강 — label+identity 파라미터) `renderConnBlock`(~796, `CONN_PAGE=80` 단위 "더 보기"·행 클릭 시드 연동) `renderNodePanel`(~864) `setPanelCollapsed`(~933, 패널 접기).
- 이벤트: `onNodeClick`(~963, **선택만** — 중심 이동은 더블클릭/시드 버튼) `initCanvasEvents`(~967, 팬·줌·dblclick 재중심) `exploreFromInput`(~1129) `initSearchBar`(~1161, `/graph/nodes/search` 자동완성+200ms debounce+seq 가드) `init`(~1197, popstate 복원·접기 버튼·초기 쿼리 replaceState — trace 크로스링크).
- user provenance 엣지는 `--overwrite` 색 강조(테이블은 `.conn-user`). truncated 배지. 소비 API: `/graph/stats·neighbors·nodes/search`.

### `trace_core.js` (~234줄) — G2 추적 순수 로직 (무의존, node 테스트 가능)
- export: `SEED_CAP=20`(~10) `composeIdentity`(~38, 서버 G1 `compose_identity` 미러 — `|` 조인+이스케이프+float 안정화) `capSeeds`(~57) `parseSeedsParam`(~73) `normalizeMissingSeeds`(~98) `buildTraceRequest`(~128) `groupNodesByLabel`(~146) `splitTimeline`(~187) 표시 헬퍼(`propsSummary`/`fmtEventTime` 등, ~211–228).

### `trace.js` (~454줄) — 추적 리포트 (trace.html 엔트리)
- `runTrace`(~103, POST `/graph/trace`, seq 가드, 실패 시 기존 리포트 유지+토스트) → `renderReport`(~213, 라벨별 그룹 테이블 100행 청크 + event_time 타임라인 300건 청크, user provenance 강조, 구조 엣지 접이식) `initControls`(~403, 시드 칩·depth 즉시 재실행·시간범위 재실행 버튼) `init`(~425, URL `replaceState` 동기화).

### `trace_launch.js` (~107줄) — index 「🕸️ 추적」 진입점
- export: `updateTraceEntryVisibility`(~25) `refreshTraceEntry`(~35, `GET /graph/mapping-summary`로 활성 판정) `openTraceForSelection`(~54, 선택 행→identity 조립 시드, 상한 20 토스트, 새 탭) `initTraceEntry`(~96).

### 보조 모듈
| 파일 | 책임 |
|---|---|
| `theme.js` (~92) | 라이트/다크 토큰 전환 — export `getTheme/applyTheme/toggleTheme/syncAgGridThemeClasses/initTheme` |
| `tokens.css` (~287) | 디자인 토큰(색·타이포·간격) — 듀얼 테마 CSS 변수의 SSOT. 2026-07-25 다크 세트 심화(Ground L* 9.2, WCAG AA 유지) |
| `style.css` (~1,844) | index 페이지 스타일 본체(맵 에디터와 공유). app-header는 `position:relative; z-index:200` — split-resizer(z:100) 위 스태킹 보장(드롭다운 가림 수정) |
| `transfer_plan.css` | [M2-v2] 전사 계획 사이드바 스타일 — tokens.css 시맨틱 토큰만 사용(듀얼 테마 자동 대응). 구 `bonding_plan.css`를 대체 |
| `utils.js` (~307) | `getLocalTimeString`(~2) / **전역 토스트 재작성**(~29–164) / `getCleanFilename`(~166) / 인제션 진행 토스트 `showIngestionProgress`(~182)·`finishIngestionProgress`(~255). **토스트 규율(전 페이지 영향)**: 만료는 **벽시계 `expireAt`** 기준(`sweepToasts`가 `now >= expireAt` 비교 — 백그라운드 탭 `setTimeout` 스로틀링으로 무한 누적되던 원인 제거, 타이머는 스윕을 깨우는 힌트일 뿐) · 상한 `TOAST_MAX_VISIBLE=4`(~29)이고 퇴거는 **비-에러 오래된 것 우선**, 방금 삽입분은 `keep` 인자로 면제 · TTL `{info:5s, success:5s, warning:9s, error:15s}`(~30 — **에러 15초는 성공 알림에 밀려나지 않게 하는 의도적 예외**) · 스윕 트리거는 타이머 + `visibilitychange` + `window.focus` + 삽입 전후(~101–105) · `dedupeKey` 합치기는 **에러 제외**(건별 원인이 중요), 같은 키+타입이면 `count+=1`·만료 연장·`… · N건` 표기 · 본문은 `textContent`(HTML 해석 금지) |
| `dom.js` (~57) | DOM 참조 일원화 — `elements` 게터 객체(+`traceBtn`/`menuTrace`) |
| `config.js` (~5) | `API_BASE`/`CURRENT_USER`/`pageLimit` |
| `clipboard.js`·`counter.js` | counter.js는 Vite 템플릿 잔재(미사용) |

---

## 8. 주요 호출 흐름 요약

1. **파일 인제션**: 폴더 투입 → `IngestionHandler._handle_event` → **[P1] `_route_and_process`**(임계 초과·backlog 잔여 → heavy 큐 / 인라인은 직렬화 락 try-acquire, 실패 시 큐 재라우팅) → `process_with_retry` → `_snapshot_table_context`(파일당 1회 config 스냅샷 — 테이블 해석은 글로벌 별칭 > 레거시 config.json > 폴더명) → `_resolve_rows`(파이프라인 우선 → std parser 폴백) → **[P2] `compute_file_signature` → `_try_dedup_skip`(동일 시그니처 `DONE`이면 skip+archive+`SKIPPED` 로그) → `_plan_checkpoint`(재개 오프셋 결정)** → `_send_to_upsert` → **`crud.apply_batch_updates` 직접 호출**(HTTP 아님, 청크마다 `record_chunk_progress`가 **같은 트랜잭션**에 동승) → `_finalize_checkpoint(mark_done)` → 웹서버 `/internal/events/batch-refresh|file-processed` → WS 브로드캐스트.
   - [P1] 진행 가시화(push-캐시-서빙): watcher `_notify_ingestion_state` → `run_watcher.trigger_ws_ingestion_state` → POST `/internal/events/ingestion-state` → `IngestionActivityRegistry`(+ 기존 progress/file-processed 인터셉트) → GET `/admin/file-ingestion/active` → admin File 탭 진행 섹션·재기동 경고. WS 이벤트 계약 무변경.
2. **수동 편집**: client `handleCellEdit`/`applyValueToSelectedRange` → PUT `/tables/{t}/data/updates` → `apply_batch_updates_endpoint` → `crud.apply_batch_updates` → outbox 발화 + WS `batch_row_upsert` → 전 클라이언트 `handleWebSocketMessage` 델타 반영.
3. **체인 인제션**: `apply_batch_updates`의 outbox 발화 → NOTIFY → `start_chain_ingestion_worker` 루프 → `process_pending_groups` → `process_chain_transaction_group`(맵퍼 실행, 예: `map_enrichment_dedup`) → 파생 테이블 `apply_batch_updates`(source=chain_ingestion, 순환 차단) → `_dispatch_broadcasts` → `/internal/events/broadcast`(created_logs 500건 절단 + `total_log_count` 실건수) → WS.
4. **조회**: client `fetchData` → GET `/tables/{t}/data` → `get_table_data` → `get_column_filter_condition` + `fetch_and_merge_metadata`(셀 객체 병합) → client `ensureCellObject` 정규화 → AG-Grid.
5. **레이어링 조작**: 소스 모달/Pin → `/tables/{t}/cells/*` 라우트 → `crud.delete_cell_source_batch`/`set_cell_manual_priority_batch` → `compute_priority_value` 재계산 → WS 반영.
6. **설정 핫리로드**: 어드민 `reloadSystemConfigs` → POST `/admin/reload-configs` → 웹서버 `reload_local_process_cache` → `models.refresh_dynamic_models(engine)`(싱글턴·ORM·**신규 테이블 물리 CREATE** — 1차 DDL 소유자, outbox 발화보다 선행) → SYSTEM_RELOAD outbox → 워커들 `reload_worker_process_cache` + `refresh_dynamic_models`(게이트+checkfirst로 무해한 보충 안전망). 직접 파일 편집 시엔 `config_watcher`가 동일 CREATE 수행. graph 워커도 배치 내 SYSTEM_RELOAD 감지로 매핑·테이블 리로드(이슈 #8 해소).
7. **맵 에디터**: `loadExistingMap` → GET `/tables/{t}/data`(REST) → 편집 → `pushMapData` → PUT `/data/updates`. 프리셋은 `/map-presets` CRUD. 페인트 잠금은 기동 시 GET `/api/maps/paint-rules` → `applyPaintLockConfig` → 전 편집 경로가 `isProtectedFCell` 단일 관문 통과. (WS 미사용)
   - **[7d931dc] 오버레이(맵 인프라 — 계획 전용 아님) — 변환은 클라 단일 구현**: `handleAddOverlayClick`/`addOverlayForSource` → `addOverlayLayer` → ① GET `/api/maps/overlay?…&limit=1`(**좌표가 아니라 `align_applied.origin`만** 읽는 보정 선언 관문) → ② GET `/tables/{src}/schema`(`deriveMapBinding`) → ③④ GET `/tables/{src}/data`(**원본 좌표**) + `wafer_map_metadata` 소스/타깃 2건 병렬 → ⑤ `frameFromMeta`로 프레임 확정(부재 시 현재 화면 = identity 폴백) → ⑥ `cols×rows` 관문 → ⑦ `projectCellsToPhys`(소스 프레임 → 물리 키) → 캔버스 마커. 화면 규격이 바뀌면 `syncOverlayGeometry`가 `rawCells`에서 재투영. `importOverlayToGrid`만 `gridData`로 넘어온다(서버 쓰기 없음).
     - **서버 경로는 삭제되지 않았다** — `map_overlay.get_overlay`(`resolve_map_transform` + `make_frame_transform` + `_frame_phys_params`)는 엔드포인트에서 그대로 살아 있고 `test_map_overlay.py`가 계약을 지킨다. 바뀐 것은 **맵 에디터가 그 좌표를 소비하지 않는다**는 것뿐이다. 2026-07-27부터 `bonding_plan.py`·`transfer_plan.py`의 **가용량 산출이 이 서버 구현을 소비**한다(자체 사본은 삭제) — 서버 구현은 하나뿐이다.
   - **[M2-v2] 전사 계획(계획 = 그 맵 자체)**: 맵 로드 → `notifyMapContext` → `transfer_plan.js`가 `stage_of_table` 역인덱스로 stage 유도 → GET `/api/transfer-plan/{stages,source-summary}` → DOE 편집(값 페인팅) → PUT `/tables/map_doe|map_doe_source/data/updates` + `pruneScoped`. **prune 권한은 `adoptServerDoe` 한 지점에서만** 서버본 채택과 원자적으로 획득한다. 검증은 GET `/api/transfer-plan/validate?ref_table=&map_key=` → `status: ok|warnings|unverified`.
8. **그래프 자동 승격**: `apply_batch_updates`의 outbox 발화 → `run_graph_materializer_loop`(keyset 커서) → `materialize_events` → `attach_col_sources`(provenance=식별 컬럼 winner 최저 서열) → `extract_graph_items` → 노드/엣지 UPSERT + `_retarget_stale_edges` → 커서 전진. 백필은 POST `/api/graph/sync` → `execute_manual_sync` → `resync_table`.
9. **그래프 조회/추적**: index 그리드 선택 → `openTraceForSelection`(`composeIdentity` 시드) → `trace.html` `runTrace` → POST `/graph/trace`(`_expand_graph_subgraph` 공용 BFS) → 그룹+타임라인 렌더. 뷰어는 `graph.html` `explore` → GET `/graph/neighbors`. 양방향 크로스링크(`?label=&identity=`).
