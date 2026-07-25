# 🗺️ CODE_MAP — 압축 구조 지도 (파일 전량 읽기 방지용)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-25 (HEAD 078fb2c) | **Owner:** 전 에이전트 공용 | **Source-of-truth:** 각 표의 코드 경로
> 상위: [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md)

**⚠️ 사용 규칙 — 이 문서가 존재하는 이유:**
- **소스 파일을 통째로 Read하지 말 것.** 이 지도에서 함수·라인을 찾은 뒤 **해당 섹션만** `Read(offset, limit)`로 읽는다.
- 라인 앵커는 HEAD `078fb2c` 기준 **±20줄 오차 허용**. 정확 위치는 Grep으로 확정.
- 이 문서는 **지도이지 교과서가 아니다** — 구현 설명은 각 리빙 문서([backend](./backend.md)·[data_model](./data_model.md)·[frontend](./frontend.md)·[event_driven_backend](./event_driven_backend.md)) 참조.

**유지보수 규율:** 코드맵 갱신은 **doc-keeper 전담** — 총괄이 코드 배치를 병합·커밋한 뒤 doc-keeper에 위임하면, doc-keeper가 **타 에이전트들의 수정 이력(history 문서·보고서·커밋 diff)을 요약**해 해당 모듈 맵을 갱신한다(구현 에이전트는 맵을 직접 수정하지 않음 — 보고서에 변경 함수/시그니처 목록만 남긴다). 정기 정합 감사도 doc-keeper. 라인 앵커는 대략치로 충분 — 시그니처·역할 서술의 정확성이 우선.

---

## 목차

| 파일 | 라인수 | 섹션 |
|---|---|---|
| `server/main.py` | ~3,646 | [§1](#1-servermainpy--api--ws-허브) |
| `server/database/crud.py` | ~1,863 | [§2](#2-serverdatabasecrudpy--레이어링-코어) |
| `server/parsers/directory_watcher.py` | ~865 | [§3](#3-serverparsersdirectory_watcherpy--파일-인제션) |
| `server/chain_ingestion_worker.py` | ~955 | [§4](#4-serverchain_ingestion_workerpy--체인-워커) |
| 소형 서버 모듈 (models/std_parser/enrichment_*) + 그래프 트랙(graph_sync_worker/graph_materializer/ontology_config) | ~3,050 | [§5](#5-소형-서버-모듈) |
| 기타 서버 모듈 (한줄 요약) | — | [§6](#6-기타-서버-모듈-한줄-요약) |
| `client2/src/*` | ~13,000 | [§7](#7-client2src--웹-클라이언트) |
| 주요 호출 흐름 | — | [§8](#8-주요-호출-흐름-요약) |

---

## 1. `server/main.py` — API + WS 허브

FastAPI 웹서버. 모든 REST/WS의 단일 진입점. 워커·워처와는 outbox + `/internal/events/*`로 통신.

### 1.1 기동·미들웨어·공용 헬퍼

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `db_context_middleware(request, call_next)` | 요청별 DB 세션 수명 관리 미들웨어 | ~56 |
| `startup_event()` | 기동: 테이블 준비, 워처 스레드, 콜백 배선, 캐시 워밍 | ~100 |
| ├ `trigger_ws_refresh(table_name, count, created_logs, total_log_count)` | (내부) 인제션 완료 → WS 갱신 브로드캐스트 콜백 | ~190 |
| └ `trigger_ws_file_processed(table_name, filename, status, error_msg)` | (내부) 파일 처리 상태 → WS 통지 콜백 | ~210 |
| `shutdown_event()` | 종료 정리 | ~264 |
| `class ConnectionManager` — `connect/disconnect/broadcast` | WS 연결 풀 + 전체 브로드캐스트 | ~279 |
| `invalidate_table_cache(table_name)` | 테이블 count 캐시 무효화 | ~346 |
| `inject_system_columns(row)` | 응답 행에 시스템 컬럼 주입 | ~380 |
| `fetch_and_merge_metadata(db, table_name, rows, user_cols, include_sources=True) -> list` | 행들에 CellSource/Overwrite 메타 병합 → 셀 객체 `{value,is_overwrite,priority_source}` 생성 (조회 응답의 핵심) | ~465 |
| `get_deleted_row_business_key(db, table_name, row_id)` / `..._bulk(...) -> dict` | 삭제 행의 비즈니스 키 역추적(감사 표시용) | ~593/616 |
| `check_rows_exist(db, row_keys) -> set` | (table,row_id) 존재 일괄 확인 | ~654 |
| `get_column_filter_condition(table_model, col_name, f_info)` | 컬럼 필터 → SQLAlchemy 조건 변환(타입별) | ~840 |
| `reload_local_process_cache()` | 웹서버 config 핫리로드 — `models.refresh_dynamic_models(engine)` 위임(싱글턴·ORM·신규 테이블 물리 CREATE, 이슈 #7) + `crud._ontology_cache` 무효화 | ~2735 |
| `load_maps_config() / save_maps_config(data)` | 맵 프리셋 JSON 파일 IO | ~2820/2829 |

### 1.2 API 라우트 표 — 데이터 조회/편집

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| GET `/` | `read_root` | index 서빙 | ~308 |
| GET `/api/download/client` | `download_desktop_client` | 데스크톱 셸 배포 | ~321 |
| GET `/tables` | `list_tables` | 테이블 목록 | ~586 |
| GET `/tables/{t}/data` | `get_table_data` | **메인 조회** — 페이지네이션+필터+정렬+메타 병합 | ~943 |
| GET `/tables/{t}/schema` | `get_table_schema` | 스키마 계약(`table_config.json` 기반) | ~1514 |
| GET `/tables/{t}/{row_id}` | `get_row_data` | 단일 행 조회 | ~1552 |
| GET `/tables/{t}/export` | `export_table_csv` | CSV 스트리밍 export | ~1319 |
| POST `/tables/{t}/rows` | `create_row` | 빈 행 N개 생성(+WS 통지) | ~1640 |
| PUT `/tables/{t}/data/updates` | `apply_batch_updates_endpoint` | **메인 편집** — crud.apply_batch_updates 호출 후 병합·브로드캐스트 | ~1702 |
| DELETE `/tables/{t}/rows/{row_id}` | `delete_row` | 단일 삭제 | ~1153 |
| POST `/tables/{t}/rows/batch_delete` | `delete_rows_batch_endpoint` | 일괄 삭제(+WS) | ~1176 |
| POST `/tables/{t}/row_ids/target` | `get_target_row_ids` | 필터 조건 → row_id 목록(범위 작업용) | ~1231 |
| POST `/tables/{t}/upload` | `upload_file` | 파일 업로드 → 워크스페이스 투입 | ~2203 |

### 1.3 API 라우트 표 — 이력/레이어링(소스·우선순위)

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| GET `/audit_logs/recent` | `get_recent_audit_logs` | 최근 트랜잭션 그룹 이력 | ~672 |
| GET `/audit_logs/transaction/{tx_id}` | `get_transaction_logs` | 트랜잭션 상세 로그 | ~717 |
| GET `/dashboard/summary` | `get_dashboard_summary` | 대시보드 통계 | ~796 |
| GET `/tables/{t}/rows/{r}/history` | `get_row_history` | 행 이력 | ~1587 |
| GET `/tables/{t}/rows/{r}/cells/{c}/history` | `get_cell_history` | 셀 이력 (⚠️ ~2020에 동일 경로 중복 정의 — 선등록인 ~1614가 유효) | ~1613 |
| GET `/tables/{t}/{r}/{c}/sources` | `get_cell_sources` | 셀의 레이어(소스) 목록 | ~2230 |
| DELETE `/tables/{t}/{r}/{c}/sources/{s}` | `delete_cell_source` | 단일 소스 삭제(+재계산·WS) | ~2274 |
| PUT `/tables/{t}/{r}/{c}/priority` | `set_cell_priority` | 단일 셀 수동 우선순위(Pin) | ~2307 |
| PUT `/tables/{t}/cells/priority/batch` | `set_cell_priority_batch_endpoint` | Pin 일괄 | ~2371 |
| POST `/tables/{t}/cells/sources/delete/batch` | `delete_cell_source_batch_endpoint` | 소스 삭제 일괄 | ~2442 |
| POST `/tables/{t}/cells/sources/query` | `query_cells_sources` | 셀 범위 소스 일괄 조회 | ~2503 |

### 1.4 API 라우트 표 — 어드민/운영/그래프/맵·인리치먼트

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| POST `/api/graph/sync` | `manual_graph_sync` | 그래프 **백필/복구** 트리거(:8090 프록시 — 주 경로는 materializer) | ~1804 |
| POST `/admin/outbox/retry-failed` | `retry_failed_outbox_events` | outbox 실패 재시도 | ~2587 |
| GET `/admin/outbox/failed` | `get_failed_outbox_events` | outbox 실패 목록(페이징) | ~2626 |
| GET `/admin/file-ingestion/logs` · `/failed` | `get_file_ingestion_logs` 등 | 파일 인제션 로그/실패 목록 | ~2696/2731 |
| POST `/admin/file-ingestion/retry-failed` | `retry_failed_file_ingestion` | 아카이브 파일 재처리(동기 콜백 배선 포함) | ~3128 |
| GET `/admin/file-ingestion/workspaces` | `get_ingestion_workspaces` | 워크스페이스 현황 | ~2915 |
| POST `/admin/reload-configs` | `reload_system_configs` | config 핫리로드 — 동기 CREATE(1차 DDL 소유자)가 outbox 발화보다 선행 (+SYSTEM_RELOAD outbox 발화) | ~2770 |
| GET `/admin/chain/rules` · `/admin/mappers/list` | `get_chain_rules` / `get_mappers` | 체인 룰·맵퍼 목록 | ~2986/3008 |
| GET `/admin/auto-update/status` · POST `.../run-now` | — | 오토업데이트 상태/즉시실행 | ~3234/3257 |
| GET/POST `/admin/scripts/list|code` | `list_admin_scripts` 등 | Monaco 에디터용 스크립트 IO | ~3391–3530 |
| GET/POST/DELETE `/map-presets` (+`/api/` 별칭) | `_save_map_preset_impl` 등 | 맵 프리셋 CRUD | ~2853–2910 |
| GET `/enrichment/rules` · `.../references/{index}` | `get_enrichment_rules` / `get_enrichment_reference` | 인리치먼트 규칙 공개본·참조 뷰 조회 | ~3060/3071 |
| WS `/ws` | `websocket_endpoint` | WS 접속(ConnectionManager) | ~2191 |
| POST `/internal/events/batch-refresh` · `/broadcast` · `/file-processed` | `internal_event_*` | **워커/워처 → 웹서버 브로드캐스트 위임 (경계 계약)** | ~3298–3355 |
| GET `/admin`·`/map-editor`·`/enrichment`·`/{path}` | `serve_*` | 정적 페이지 서빙(`graph.html`/`trace.html`은 catch-all `serve_static_or_index` 경유) | ~3574–3624 |

### 1.5 그래프 조회 구간 (read-only — `graph_nodes/edges` 직접 조회, 워커 미경유)

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| (상수) | `GRAPH_NEIGHBOR_NODE_CAP=500` / `GRAPH_TRACE_NODE_CAP=1000` / `GRAPH_TRACE_DEPTH_CAP=3` 등 | 하드캡(C-7 무제한 로드 금지) | ~1853–1858 |
| (헬퍼) | `_escape_like_term(term)` | LIKE 메타문자 이스케이프 | ~1861 |
| (헬퍼) | `_expand_graph_subgraph(db, seed_nodes, depth, node_cap, edge_types=None, time_from=None, time_to=None)` | 뷰어/추적 **공용 BFS 코어** — 방향별 (from,type)/(to,type) 인덱스 2쿼리, 홉·방향당 엣지 페치 캡 2000, 노드 500청크 IN, 캡 절단 시 dangling 엣지 제외 | ~1866 |
| (헬퍼) | `_serialize_graph_nodes(nodes)` | 노드 `{id,label,identity_key,props}` 직렬화 | ~1959 |
| GET `/graph/stats` | `get_graph_stats` | label/edge_type GROUP BY 카운트 + last_sync | ~1968 |
| GET `/graph/neighbors` | `get_graph_neighbors` | k-hop(1\|2) 서브그래프 — `_expand_graph_subgraph([center])` 위임, truncated | ~1993 |
| GET `/graph/nodes/search` | `search_graph_nodes` | identity 시작일치 ILIKE 자동완성(limit 캡 50) | ~2028 |
| (헬퍼) | `_parse_trace_time(value, field)` | ISO 8601 파싱(`Z` 허용), 실패 시 400 | ~2077 |
| POST `/graph/trace` | `post_graph_trace(req: GraphTraceRequest, db)` | **[G2]** 멀티 시드 BFS 합집합 — 시드 순서보존 dedup→(label,identity) 인덱스 조회→missing_seeds 분리→공용 BFS. depth 1..3, 시간·타입 필터, 의미 검증 400 | ~2090 |
| GET `/graph/mapping-summary` | `get_graph_mapping_summary` | `ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)` — materializer와 동일 신호원, 요청 시 디스크 로드 | ~2167 |

---

## 2. `server/database/crud.py` — 레이어링 코어

셀 단위 소스 레이어링(CellSource/CellOverwrite/priority) + 배치 업서트의 단일 구현. **시그니처 변경 시 전수 Grep 연쇄 갱신 필수**([규율](../guide/data_preservation_and_signature_change.md)).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `transaction_context(user, tx_id, source)` | 컨텍스트매니저 — 감사·outbox용 트랜잭션 식별 주입 | ~8 |
| `class LightCellSource` / `LightCellOverwrite` | ORM 미경유 경량 메타 객체(성능) | ~28/39 |
| `sanitize_to_utf8(data)` | cp949 등 오염 문자열 정화 | ~60 |
| `load_table_config()` / `update_table_config(new_config)` | table_config.json IO | ~82/91 |
| `cast_value_by_type(value, col_type, col_name)` | 컬럼 타입 캐스팅 | ~107 |
| `get_row_by_business_key(db, table_name, key_value)` | 비즈니스 키로 행 조회 | ~134 |
| `resolve_priority_map(table_name=None) -> dict` / `get_source_priority(source_name, table_name=None) -> int` | **소스 서열 단일 원천**(테이블별 오버라이드 포함) — compute_priority_value·graph materializer 공용. `SOURCE_PRIORITY`에 `chain_ingestion: 4` 등재 | ~151/166 |
| `compute_priority_value(sources, manual_priority_source, table_name)` | **표시값 결정** — user:0 < collision_merge:1 < pipeline_parser:2 < custom_script:3 < chain_ingestion:4 + 수동 Pin | ~171 |
| `create_audit_log(db, ..., transaction_id, business_key, add_to_cache)` | 감사 로그 1건 생성 | ~198 |
| `bulk_insert_audit_logs(db, logs)` | 감사 로그 벌크 삽입 | ~248 |
| `bulk_upsert_cell_sources(db, mappings)` / `bulk_upsert_cell_overwrites(db, mappings)` | 메타 테이블 벌크 업서트(ON CONFLICT) | ~268/300 |
| `bulk_delete_cell_overwrites(db, delete_keys)` | overwrite 벌크 삭제 | ~333 |
| `_get_or_create_row(db, table_model, update_item, row_cache, table_name) -> (row, is_new)` | row_id/비즈니스키로 행 확보(캐시 활용) | ~349 |
| `_load_metadata_row_cell(...) -> (sources_list, overwrite)` | 셀 메타 로드(캐시·업서트 큐 연동) | ~405 |
| `apply_row_update_internal(db, table_name, update_item, row_cache, sources_cache, overwrites_cache, transaction_id, logs_to_cache, cell_sources_to_upsert, cell_overwrites_to_upsert, cell_overwrites_to_delete, deleted_row_ids) -> (row, is_new, changed_cols)` | **[통합 코어]** 단일 행 업데이트 + 레이어링 재계산. 모든 쓰기 경로가 여기로 수렴 | ~469 |
| `apply_batch_updates(db, table_name, batch: GeneralUpdateBatch)` | **배치 진입점** — tx 컨텍스트, 캐시 프리로드, 행별 코어 호출, 벌크 flush, outbox 발화. 반환 `(results, changed_cells, created_logs, deleted_row_ids)` | ~944 |
| `create_empty_row(s)_batch(db, table_name, count, user_name)` | 빈 행 생성 | ~1137/1142 |
| `delete_row(db,...)` / `delete_rows_batch(db, table_name, row_ids, user_name)` | 행 삭제(+감사·메타 정리) | ~1186/1190 |
| `delete_cell_source_batch(db, table_name, cells, source_name)` | 소스 레이어 일괄 삭제 + 표시값 재계산 | ~1254 |
| `delete_cell_source(db, ...)` | 단일 소스 삭제(배치 위임) | ~1410 |
| `set_cell_manual_priority_batch(db, table_name, updates, source_name, updated_by)` | 수동 Pin 일괄(§크고 복잡 — 표시값 재계산·감사 포함) | ~1415 |
| `set_cell_manual_priority(db, ...)` | 단일 Pin(배치 위임) | ~1774 |
| `get_ontology_mapping()` / `check_needs_rollback(table_name, modified_cols)` | 그래프 보조 — v2 검증+enrichment 승격 적용 결과 캐시 / v2 매핑 인식 rollback 신호(v1 폴백) | ~1783/1826 |

---

## 3. `server/parsers/directory_watcher.py` — 파일 인제션

워크스페이스별 폴더 감시 → 파서 실행 → **HTTP 아닌 직접 DB**(`crud.apply_batch_updates`) 업서트 → 웹서버에 `/internal/events/*` 콜백. 2026-07-25 std parser(무스크립트 표준 파싱) 통합됨.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `load_global_table_config() -> dict` | table_config.json 로드 | ~43 |
| `_register_legacy_import_shim()` | 구식 사용자 파이프라인 스크립트의 import 호환 shim | ~56 |
| `class IngestionHandler(FileSystemEventHandler)` | **워크스페이스 1개 담당 핸들러** | ~130 |
| ├ `table_name` / `std_parse_enabled` / `errors_path` (property) | 워크스페이스 설정 해석(std_parse 게이트 포함) | ~147–182 |
| ├ `on_created/on_moved → _handle_event(file_path)` | 파일 이벤트 수신 → 처리 위임 | ~185–195 |
| ├ `process_with_retry(file_path, uploader, retries=3, delay=1.0)` | 처리 본체 — 파싱→업서트→아카이브/에러 이동, 재시도 | ~217 |
| ├ `_log_ingestion_failure/success(...)` | FileIngestionLog 기록(직접 DB) | ~276/296 |
| ├ `process_archived_file_sync(log_entry, db, uploader)` | 어드민 재처리 경로(아카이브 파일 동기 재실행) | ~316 |
| ├ `_move_to_err_folder` / `_archive_file` | 파일 이동 | ~347/375 |
| ├ `_discover_and_execute_pipeline(file_path) -> list[dict]\|None` | 사용자 파이프라인 스크립트(pipeline_*.py) 탐색·실행 | ~402 |
| ├ `_resolve_rows(file_path)` | **파서 라우팅** — 파이프라인 우선, 없으면 std parser 폴백 | ~492 |
| ├ `_try_std_parse(file_path)` | std_parser 호출 래퍼(게이트·에러 처리) | ~517 |
| └ `_send_to_upsert(rows, uploader, filename, total_rows)` | list 또는 스트리밍 이터레이터 → 청킹 → `crud.apply_batch_updates` 직접 호출 + 진행률 콜백 | ~557 |
| `class WorkspaceWatcher` | 전체 워크스페이스 관리자 | ~680 |
| ├ `_provision_workspaces()` / `_register_workspace(raws_root, table_config)` | 폴더 스캐폴딩·핸들러 등록 | ~697/731 |
| ├ `discover_and_watch()` / `sync_new_workspaces()` | 기동 스캔·신규 워크스페이스 동기화 | ~779/795 |
| └ `_ensure_observer_running()` / `stop()` / `start(blocking)` | watchdog Observer 수명 관리 | ~819–839 |

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
| `process_chain_transaction_group(tx_id, events, db, rules) -> (ok, err, broadcast_messages)` | **핵심** — 순환 차단(source=chain_ingestion 제외), 맵퍼 실행, 업서트, 브로드캐스트 큐 반환 | ~349 |
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

---

## 6. 기타 서버 모듈 (한줄 요약)

라인 앵커 미수록 — 필요 시 해당 파일에서 Grep.

| 파일 | 책임 |
|---|---|
| `server/database/models.py` | ORM — 정적 + `DYNAMIC_TABLES` + 런타임 DDL(핫리로드 CREATE) — **함수 앵커는 [§5](#5-소형-서버-모듈)** |
| `server/database/schemas.py` | Pydantic — `GeneralUpdateItem/Batch` 등 API·배치 계약 |
| `server/database/database.py` | 엔진·SessionLocal·outbox 발화(`database_outbox` + NOTIFY) |
| `server/database/config_watcher.py` | table_config.json 변경 감시 → 동적 테이블 재구성. engine 분기(~44)에서 `create_missing_dynamic_tables` 선(先)호출 후 기존 sync(ALTER) — 직접 파일 편집 경로의 신규 테이블 CREATE(이슈 #7) |
| `server/graph_sync_worker.py` · `graph_materializer.py` · `ontology_config.py` | 온톨로지 그래프 트랙 — **함수 앵커는 [§5](#5-소형-서버-모듈)** |
| `server/run_auto_update.py` | 스케줄 기반 사용자 스크립트 자동 실행 |
| `server/run_api.py` / `run_watcher.py` / `run_chain_worker.py` / `run_decoupled_app.py` | 프로세스 런처(5-프로세스 토폴로지). run_watcher의 SYSTEM_RELOAD 폴러(`poll_pending_retries`, ~141)는 `refresh_dynamic_models(engine)` 호출(보충 안전망, 이슈 #7) |
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

### `map_editor.js` (~2,771줄) — 웨이퍼 맵 에디터 (단일 페이지 스크립트, export 없음)
- 좌표 변환 코어: `getPhysicalCoords`(~653) `getCellFromPhysicalCoords`(~706) `getCellFromVisualCoords`(~746) `getVisualCoords`(~813) `getTransformedPhysicalConfig`(~828) `isCellInsideWafer(Fast)`(~889/927) — 회전/면반전 불변식은 [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md).
- 캔버스 렌더: `renderGridCanvas`(~1270, 본체) `scheduleRenderGridCanvas`(~1233) `fitGridToWorkspace`(~1255) `updateNotchPosition`(~1599).
- 데이터 IO(REST — WS 아님): `loadExistingMap`(~1880) `pushMapData`(~2243, 저장 본체) 프리셋 `fetchAndRenderPresets`/`saveCustomPreset`/`deleteCustomPreset`(~984–1166).
- 레전드/브러시: `renderLegendTable`(~1676) `selectBrush`(~1824) + `localStorage` 동기화 `load/saveLegendToStorage`(~1654/1672).
- 편집 도구: `fillGrid`(~2214) `getEdgeClassification`(~2421) `selectEdgeCells`(~2501) `autoPaintE1E2`(~2528) `copyGridToExcel`(~2616).

### `admin.js` (~2,437줄) — 어드민 페이지 (2026-07-25 전면 재작성 — 파이프라인 5탭, export 없음)
- 라우팅: `parseRoute`(~231) `applyRoute`(~243) — `#overview/#file/#chain/#autoupdate/#enrichment` + 구 별칭(`#outbox→chain` 등) + `#editor=<path>`. `switchTab(tabName, opts)`(~288, 해시 동기·Overview 전폭 레이아웃).
- 탭 데이터: `fetchData(options)`(~608, 탭당 병렬 fetch를 한 seq로 묶어 stale 렌더 차단) → 각 `render*Table` + 섹션 카운트 배지(`setSectionCount`), `clearRowHighlights`/`clearSelections`.
- Overview: `fetchOverview`(~1185) `renderOverview`(~1310, 4카드+최근 이벤트+딥링크).
- 유기 연계: `renderLinkedFailTable`(~1093, AutoUpdate §오류 — 산출물 인제션 실패 교집합) `showEventDiagnostics`(~1814, +Edit Mapper 딥링크) `selectFileRow`(파서 편집 딥링크).
- Enrichment 탭: `renderEnrichmentTable`(~1122) `fetchEnrichmentStatus`(~2280, 15s TTL 캐시 — 스트립·탭·Overview 3소비처 공용).
- 에디터(공용 뷰): `initMonacoEditor`(~1999, pending open) `populateEditorPicker`(~2056) `selectEditorFile`(~2102, dirty confirm) `openInlineEditor`(~2182). (구 좌측 파일트리 `renderEditorTree` 일습은 피커로 대체·삭제됨)
- 소비 API: `/admin/*` 전역 + `/enrichment/rules` + `/tables/{t}/data`(결손 카운트). 신규 서버 API 0건.

### `enrichment.js` (~754줄) — 인리치먼트 컨베이어 페이지 (export 없음)
- 규칙: `loadRules`(~69) `selectRule`(~116) `rebuildGrid`(~151). 워크리스트: `fetchWorklist`(~190) `fetchTotalAll`(~241) `refillIfNeeded`(~257).
- 입력 흐름: `renderDetail`(~310) `onInputKeydown`(~384) `moveSelection`(~402) `saveCurrent`(~427, PUT `/data/updates`).
- 참조 패널: `initReferencePanel`(~517) `loadActiveReference`(~580) `renderRefTable`(~637).
- 소비 API: `/enrichment/rules`, `/enrichment/rules/{r}/references/{i}`, `/tables/{t}/data`, PUT `/data/updates`.

### `graph_viewer.js` (~927줄) — 지식그래프 서브그래프 뷰어 (graph.html 엔트리, 무라이브러리)
- `renderStats`(~147, `/graph/stats` 카운트 카드+라벨 색 팔레트) `explore(label, identity)`(~235, `/graph/neighbors` 조회→BFS 동심원 레이아웃) `renderCanvas`(~417, 캔버스 본체 — 테마 색 1회 캐싱+`themechange` 재캐싱, 상시 rAF 없음) `initCanvasEvents`(~671, 팬·줌·노드 클릭 재중심) `exploreFromInput`(~827) `initSearchBar`(~859, `/graph/nodes/search` 자동완성+200ms debounce+seq 가드) `init`(~895, `?label=&identity=` 초기 중심 — trace 크로스링크).
- user provenance 엣지는 `--overwrite` 색 강조. truncated 배지. 소비 API: `/graph/stats·neighbors·nodes/search`.

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
| `utils.js` (~195) | `getLocalTimeString`/`showToast`/`getCleanFilename`/인제션 진행 토스트(`showIngestionProgress`/`finishIngestionProgress`) |
| `dom.js` (~57) | DOM 참조 일원화 — `elements` 게터 객체(+`traceBtn`/`menuTrace`) |
| `config.js` (~5) | `API_BASE`/`CURRENT_USER`/`pageLimit` |
| `clipboard.js`·`counter.js` | counter.js는 Vite 템플릿 잔재(미사용) |

---

## 8. 주요 호출 흐름 요약

1. **파일 인제션**: 폴더 투입 → `IngestionHandler._handle_event` → `process_with_retry` → `_resolve_rows`(파이프라인 우선 → std parser 폴백) → `_send_to_upsert` → **`crud.apply_batch_updates` 직접 호출**(HTTP 아님) → 웹서버 `/internal/events/batch-refresh|file-processed` → WS 브로드캐스트.
2. **수동 편집**: client `handleCellEdit`/`applyValueToSelectedRange` → PUT `/tables/{t}/data/updates` → `apply_batch_updates_endpoint` → `crud.apply_batch_updates` → outbox 발화 + WS `batch_row_upsert` → 전 클라이언트 `handleWebSocketMessage` 델타 반영.
3. **체인 인제션**: `apply_batch_updates`의 outbox 발화 → NOTIFY → `start_chain_ingestion_worker` 루프 → `process_pending_groups` → `process_chain_transaction_group`(맵퍼 실행, 예: `map_enrichment_dedup`) → 파생 테이블 `apply_batch_updates`(source=chain_ingestion, 순환 차단) → `_dispatch_broadcasts` → `/internal/events/broadcast` → WS.
4. **조회**: client `fetchData` → GET `/tables/{t}/data` → `get_table_data` → `get_column_filter_condition` + `fetch_and_merge_metadata`(셀 객체 병합) → client `ensureCellObject` 정규화 → AG-Grid.
5. **레이어링 조작**: 소스 모달/Pin → `/tables/{t}/cells/*` 라우트 → `crud.delete_cell_source_batch`/`set_cell_manual_priority_batch` → `compute_priority_value` 재계산 → WS 반영.
6. **설정 핫리로드**: 어드민 `reloadSystemConfigs` → POST `/admin/reload-configs` → 웹서버 `reload_local_process_cache` → `models.refresh_dynamic_models(engine)`(싱글턴·ORM·**신규 테이블 물리 CREATE** — 1차 DDL 소유자, outbox 발화보다 선행) → SYSTEM_RELOAD outbox → 워커들 `reload_worker_process_cache` + `refresh_dynamic_models`(게이트+checkfirst로 무해한 보충 안전망). 직접 파일 편집 시엔 `config_watcher`가 동일 CREATE 수행. graph 워커도 배치 내 SYSTEM_RELOAD 감지로 매핑·테이블 리로드(이슈 #8 해소).
7. **맵 에디터**: `loadExistingMap` → GET `/tables/{t}/data`(REST) → 편집 → `pushMapData` → PUT `/data/updates`. 프리셋은 `/map-presets` CRUD. (WS 미사용)
8. **그래프 자동 승격**: `apply_batch_updates`의 outbox 발화 → `run_graph_materializer_loop`(keyset 커서) → `materialize_events` → `attach_col_sources`(provenance=식별 컬럼 winner 최저 서열) → `extract_graph_items` → 노드/엣지 UPSERT + `_retarget_stale_edges` → 커서 전진. 백필은 POST `/api/graph/sync` → `execute_manual_sync` → `resync_table`.
9. **그래프 조회/추적**: index 그리드 선택 → `openTraceForSelection`(`composeIdentity` 시드) → `trace.html` `runTrace` → POST `/graph/trace`(`_expand_graph_subgraph` 공용 BFS) → 그룹+타임라인 렌더. 뷰어는 `graph.html` `explore` → GET `/graph/neighbors`. 양방향 크로스링크(`?label=&identity=`).
