# 🗺️ CODE_MAP — 압축 구조 지도 (파일 전량 읽기 방지용)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-27 (HEAD be58210) | **Owner:** 전 에이전트 공용 | **Source-of-truth:** 각 표의 코드 경로
> 상위: [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md)

**⚠️ 사용 규칙 — 이 문서가 존재하는 이유:**
- **소스 파일을 통째로 Read하지 말 것.** 이 지도에서 함수·라인을 찾은 뒤 **해당 섹션만** `Read(offset, limit)`로 읽는다.
- 라인 앵커는 HEAD `be58210` 기준 **±20줄 오차 허용**. 정확 위치는 Grep으로 확정.
- `client2/*` 앵커는 **`client2/src/`**(원본) 기준이다 — `client2/dist/assets/map_editor-*.js`는 vite 산출물이라 파일명 해시가 빌드마다 바뀐다. **dist 번들명을 문서에 고정 인용하지 말 것.**
- 이 문서는 **지도이지 교과서가 아니다** — 구현 설명은 각 리빙 문서([backend](./backend.md)·[data_model](./data_model.md)·[frontend](./frontend.md)·[event_driven_backend](./event_driven_backend.md)) 참조.

**유지보수 규율:** 코드맵 갱신은 **code-mapper 전담**(2026-07-27 문서 에이전트 분할 — 리빙 문서·`PRIMITIVES.md`는 doc-keeper, 히스토리는 doc-historian, 정합 감사는 doc-auditor). code-mapper는 **커밋된 소스와 직접 대조**해 갱신한다(보고서 요약이 아니라 `git show <hash>:<path>` 실측 — 워킹트리는 타 에이전트가 동시 편집 중일 수 있다). 구현 에이전트는 맵을 직접 수정하지 않고 보고서에 변경 함수/시그니처 목록만 남긴다. 라인은 보조 식별자이고 **함수명·시그니처가 1차 식별자**다.

---

## 목차

| 파일 | 라인수 | 섹션 |
|---|---|---|
| `server/main.py` | ~4,045 | [§1](#1-servermainpy--api--ws-허브) |
| `server/database/crud.py` | ~1,952 | [§2](#2-serverdatabasecrudpy--레이어링-코어) |
| `server/parsers/directory_watcher.py` | ~1,714 | [§3](#3-serverparsersdirectory_watcherpy--파일-인제션) |
| `server/chain_ingestion_worker.py` | ~972 | [§4](#4-serverchain_ingestion_workerpy--체인-워커) |
| 소형 서버 모듈 (models/std_parser/enrichment_*/ingestion_activity/ingestion_checkpoint/bonding_plan/**map_overlay**/**transfer_plan**) + 그래프 트랙(graph_sync_worker/graph_materializer/ontology_config) + **운영 5종**(paths/process_supervisor/health/heartbeat/product_tables) | ~7,400 | [§5](#5-소형-서버-모듈) |
| 기타 서버 모듈 (한줄 요약) + 설치·개발환경 스크립트 | — | [§6](#6-기타-서버-모듈-한줄-요약) |
| `client2/src/*` | ~16,300 | [§7](#7-client2src--웹-클라이언트) |
| 주요 호출 흐름 | — | [§8](#8-주요-호출-흐름-요약) |

> **경로의 단일 원천 (2026-07-27):** `server/config/**`·`server/ingestion_workspace/**`·프로세스 로그는 이제 전부 **`server/paths.py`**([§5](#5-소형-서버-모듈))를 경유한다. 소스에서 `os.path.dirname(__file__)`로 config/워크스페이스 경로를 조립하는 코드를 보면 **누락**이다. 이 맵의 경로 표기는 모두 `paths.*` 기준.

---

## 1. `server/main.py` — API + WS 허브

FastAPI 웹서버. 모든 REST/WS의 단일 진입점. 워커·워처와는 outbox + `/internal/events/*`로 통신.

### 1.1 기동·미들웨어·공용 헬퍼

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `config_path = paths.config_path("table_config.json")` / `logger.info(paths.describe())` | **[신설]** 부팅 첫 줄에 데이터 루트를 찍는다 — 로그만 보고 이 프로세스가 격리 환경인지 라이브인지 판별 가능 | ~36/37 |
| `db_context_middleware(request, call_next)` | 요청별 DB 세션 수명 관리 미들웨어 | ~58 |
| `startup_event()` | 기동: 테이블 준비, 워처 스레드, 콜백 배선, 캐시 워밍 | ~179 |
| ├ `trigger_ws_refresh(table_name, count, created_logs, total_log_count)` | (내부·임베디드 모드 전용) 인제션 완료 → WS 갱신 브로드캐스트 콜백 (⚠️ C-5 절단 미적용 레거시 경로 — 드릴 관찰, 저순위) | ~257 |
| ├ `trigger_ws_file_processed(table_name, filename, status, error_msg)` | (내부) 파일 처리 상태 → WS 통지 콜백 | ~277 |
| └ (임베디드 ingestion-state 배선) | [P1] 비-DECOUPLED 시 HTTP 없이 `ingestion_activity_registry`에 직접 반영, file-processed 시 제거 | ~305–322 |
| `shutdown_event()` | 종료 정리 | ~350 |
| `class ConnectionManager` — `connect/disconnect/broadcast` | WS 연결 풀 + 전체 브로드캐스트 | ~365 |
| `invalidate_table_cache(table_name)` | 테이블 count 캐시 무효화 | ~432 |
| `inject_system_columns(row)` | 응답 행에 시스템 컬럼 주입 | ~466 |
| `fetch_and_merge_metadata(db, table_name, rows, user_cols, include_sources=True) -> list` | 행들에 CellSource/Overwrite 메타 병합 → 셀 객체 `{value,is_overwrite,priority_source}` 생성 (조회 응답의 핵심) | ~551 |
| `get_deleted_row_business_key(db, table_name, row_id)` / `..._bulk(...) -> dict` | 삭제 행의 비즈니스 키 역추적(감사 표시용) | ~679/702 |
| `check_rows_exist(db, row_keys) -> set` | (table,row_id) 존재 일괄 확인 | ~740 |
| `from ingestion_activity import registry as ingestion_activity_registry` | [P1] 진행 스냅샷 레지스트리 싱글턴 import([§5](#5-소형-서버-모듈)) | ~759 |
| `get_column_filter_condition(table_model, col_name, f_info)` | 컬럼 필터 → SQLAlchemy 조건 변환(타입별) | ~929 |
| `reload_local_process_cache()` | 웹서버 config 핫리로드 — `models.refresh_dynamic_models(engine)` 위임(싱글턴·ORM·신규 테이블 물리 CREATE, 이슈 #7) + `crud._ontology_cache` 무효화 | ~2850 |
| `load_maps_config() / save_maps_config(data)` | 맵 프리셋 JSON 파일 IO (`MAPS_CONFIG_PATH = paths.config_path("maps.json")` ~2933) | ~2935/2944 |

### 1.1-bis 헬스 블록 (`8117456` 신설 — 파일 상단 ~88–176)

**등록 위치가 계약이다.** FastAPI는 등록 순서로 매칭하므로 이 블록은 파일 맨 아래 SPA catch-all `@app.get("/{file_name:path}")`(~4022)보다 **위에** 있어야 한다. 이 라우트가 없던 시절 `/health`는 catch-all로 떨어져 **HTML을 200으로** 반환했다 — 외부 모니터가 죽은 서버를 살아 있다고 불렀다. `tests/test_health_endpoint.py`가 양쪽(‌`/health`는 JSON · 엉뚱한 경로는 여전히 HTML)을 단언하므로, 재배치로 라우트가 다시 가려지면 조용히 죽지 않고 테스트가 깨진다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_HEALTH_DB_TIMEOUT_SEC=2.0` / `_health_probe_inflight` | DB 프로브 시간 상한 / **동시 프로브 1개 제한** — DB가 멎으면 `wait_for`는 요청만 놓아주고 워커 스레드는 못 놓아준다. 10초 폴링 모니터가 행마다 스레드를 쌓지 않도록 하는 플래그(해제는 대기를 포기한 요청이 아니라 **스레드 자신**이 한다) | ~103/108 |
| `_health_probe_db_sync()` / `_health_probe_and_release()` | 동기 DB 프로브(+`health.probe_outbox`) / inflight 해제 래퍼 | ~111/124 |
| GET `/health` → `health_check()` | `heartbeat.read_all()` + `process_supervisor.read_status()` + DB/outbox 프로브를 `health.compute_health`에 넘겨 **JSONResponse + 실제 HTTP 상태**(unhealthy면 503)로 반환 | ~132/133 |

### 1.2 API 라우트 표 — 데이터 조회/편집

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| GET `/` | `read_root` | index 서빙 | ~394 |
| GET `/api/download/client` | `download_desktop_client` | 데스크톱 셸 배포 | ~407 |
| GET `/tables` | `list_tables` | 테이블 목록 | ~672 |
| GET `/tables/{t}/data` | `get_table_data` | **메인 조회** — 페이지네이션+필터+정렬+메타 병합 | ~1032 |
| GET `/tables/{t}/schema` | `get_table_schema` | 스키마 계약(`table_config.json` 기반) | ~1603 |
| GET `/tables/{t}/{row_id}` | `get_row_data` | 단일 행 조회 | ~1641 |
| GET `/tables/{t}/export` | `export_table_csv` | CSV 스트리밍 export | ~1408 |
| POST `/tables/{t}/rows` | `create_row` | 빈 행 N개 생성(+WS 통지) | ~1729 |
| PUT `/tables/{t}/data/updates` | `apply_batch_updates_endpoint` | **메인 편집** — crud.apply_batch_updates 호출 후 병합·브로드캐스트. 배치의 `replace_map:true`(schemas.py ~87)는 **동일 맵 기존 행 클린 삭제 후 재기록** — DOE 저장이 이 연산을 쓴다([§7 transfer_plan.js](#7-client2src--웹-클라이언트)) | ~1791 |
| DELETE `/tables/{t}/rows/{row_id}` | `delete_row` | 단일 삭제 | ~1242 |
| POST `/tables/{t}/rows/batch_delete` | `delete_rows_batch_endpoint` | 일괄 삭제(+WS) | ~1265 |
| POST `/tables/{t}/row_ids/target` | `get_target_row_ids` | 필터 조건 → row_id 목록(범위 작업용) | ~1320 |
| POST `/tables/{t}/upload` | `upload_file` | 파일 업로드 → 워크스페이스 투입(`paths.workspace_path(table,"raws")` ~2310) | ~2303 |

### 1.3 API 라우트 표 — 이력/레이어링(소스·우선순위)

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| GET `/audit_logs/recent` | `get_recent_audit_logs` | 최근 트랜잭션 그룹 이력 | ~761 |
| GET `/audit_logs/transaction/{tx_id}` | `get_transaction_logs` | 트랜잭션 상세 로그 | ~806 |
| GET `/dashboard/summary` | `get_dashboard_summary` | 대시보드 통계 | ~885 |
| GET `/tables/{t}/rows/{r}/history` | `get_row_history` | 행 이력 | ~1676 |
| GET `/tables/{t}/rows/{r}/cells/{c}/history` | `get_cell_history` | 셀 이력 (⚠️ ~2458에 동일 경로 중복 정의 — 선등록인 ~1702가 유효) | ~1702 |
| GET `/tables/{t}/{r}/{c}/sources` | `get_cell_sources` | 셀의 레이어(소스) 목록 | ~2329 |
| DELETE `/tables/{t}/{r}/{c}/sources/{s}` | `delete_cell_source` | 단일 소스 삭제(+재계산·WS) | ~2373 |
| PUT `/tables/{t}/{r}/{c}/priority` | `set_cell_priority` | 단일 셀 수동 우선순위(Pin) | ~2406 |
| PUT `/tables/{t}/cells/priority/batch` | `set_cell_priority_batch_endpoint` | Pin 일괄 | ~2470 |
| POST `/tables/{t}/cells/sources/delete/batch` | `delete_cell_source_batch_endpoint` | 소스 삭제 일괄 | ~2541 |
| POST `/tables/{t}/cells/sources/query` | `query_cells_sources` | 셀 범위 소스 일괄 조회 | ~2602 |

### 1.4 API 라우트 표 — 어드민/운영/그래프/맵·인리치먼트

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| POST `/api/graph/sync` | `manual_graph_sync` | 그래프 **백필/복구** 트리거(:8090 프록시 — 주 경로는 materializer) | ~1892 |
| POST `/admin/outbox/retry-failed` | `retry_failed_outbox_events` | outbox 실패 재시도 | ~2686 |
| GET `/admin/outbox/failed` | `get_failed_outbox_events` | outbox 실패 목록(페이징) | ~2725 |
| GET `/admin/file-ingestion/logs` · `/failed` | `get_file_ingestion_logs` 등 | 파일 인제션 로그/실패 목록 | ~2795/2830 |
| GET `/admin/file-ingestion/active` | `get_active_file_ingestions` | **[P1 신설]** 진행 중 인제션 스냅샷(레지스트리 `snapshot()` — 인메모리, TTL 퇴거 포함) — admin File 탭/헬스 스트립 소비 | ~2836 |
| POST `/admin/file-ingestion/retry-failed` | `retry_failed_file_ingestion` | 아카이브 파일 재처리(동기 콜백 배선 포함, 내부 `sync_refresh_callback` ~3441) — 워크스페이스는 `resolve_workspace_root` 역조회(별칭 대응) | ~3408 |
| GET `/admin/file-ingestion/workspaces` | `get_ingestion_workspaces` | 워크스페이스 현황 — 표시 table_name에 글로벌 별칭(`find_workspace_alias`) 우선 적용 | ~3187 |
| POST `/admin/reload-configs` | `reload_system_configs` | config 핫리로드 — 동기 CREATE(1차 DDL 소유자)가 outbox 발화보다 선행 (+SYSTEM_RELOAD outbox 발화) | ~2884 |
| GET `/admin/chain/rules` · `/admin/mappers/list` | `get_chain_rules` / `get_mappers` | 체인 룰·맵퍼 목록 | ~3267/3288 |
| GET `/admin/auto-update/status` | `get_auto_update_status` | 스케줄러 상태 — 항목별 `active` 부가(제어 파일 실시간 계산) | ~3517 |
| POST `/admin/auto-update/toggle` | `toggle_auto_update_script` | 수집기 active 토글 — `config/auto_update_control.json` 갱신(핫 반영, 404/400 명시) | ~3550 |
| POST `/admin/auto-update/run-now` | `trigger_auto_update_run_now` | 즉시 실행(**active 무관** — 수동 실행은 명시적 의도) | ~3582 |
| GET/POST `/admin/scripts/list|code` | `list_admin_scripts` 등 | Monaco 에디터용 스크립트 IO (경로 검사 `_resolve_admin_script_path` ~3817) | ~3757–3893 |
| GET/POST/DELETE `/map-presets` (+`/api/` 별칭) | `_save_map_preset_impl` 등 | 맵 프리셋 CRUD | ~2966–3026 |
| GET `/api/bonding-plan/core-summary` | `get_bonding_plan_core_summary` | **[본딩 M1]** 코어(lot,slot) 역할별 집계 — `bonding_plan.get_core_summary` 위임([§5](#5-소형-서버-모듈)), `region` 파라미터(rects — 현 클라 미사용), 잘못된 region 400 | ~3034 |
| GET `/api/maps/overlay` | `get_map_overlay(target_table, target_key, sources, eqp=None, limit=None)` | **[M2 신설 · 맵 인프라]** 임의의 맵들을 타깃 맵 프레임 좌표로 정렬해 `overlays[]` 반환. `sources`는 `table` 또는 `table:key`의 CSV(키 생략 시 target_key 승계, 최대 8종). `map_overlay.get_overlay` 위임([§5](#5-소형-서버-모듈)), `parse_sources` ValueError → 400, 셀 상한 `MAX_OVERLAY_CELLS=20,000`(초과 시 `truncated:true`). ⚠️ **`eqp` 쿼리 파라미터는 no-op으로 존치** — `map_overlay.get_overlay`의 `eqp` 인자는 `by_eqp` 분기와 함께 삭제됐다(축소는 총괄 승인 사항). **맵 에디터 클라는 이 엔드포인트를 호출하지 않는다** | ~3067 |
| GET `/api/maps/paint-rules` | `get_map_paint_rules(table=None)` | **[M2 신설]** 페인트 잠금 선언 정본(**기존엔 클라 하드코딩 `'F'`**) — `map_overlay.get_paint_rules`. 응답 `{table, rules{enabled, blocking_values, from_overlay, message}}` | ~3105 |
| GET `/api/transfer-plan/stages` | `get_transfer_plan_stages` | **[M2 신설]** 선언된 전사 stage 목록 + 역할 연결 상태(config 해석만 — 행 조회 없음). `transfer_plan.list_stages` | ~3119 |
| GET `/api/transfer-plan/source-summary` | `get_transfer_plan_source_summary(stage, lot, slot, ref_table=None, map_key=None)` | **[M2 신설]** 단계별 소스 (lot,slot) 가용 집계 — `transfer_plan.get_stage_source_summary`. 미선언 stage 404. **칩 좌표 목록은 반환하지 않는다**(집계만 — 페이로드 상한 규율). `(ref_table, map_key)` 지정 시 `region_chips` 동봉(v2에서 구 `plan_id` 대체) | ~3133 |
| GET `/api/transfer-plan/validate` | `validate_transfer_plan(ref_table, map_key)` | **[M2 신설 · v2 모델]** 계획 검증 — **계획 정체성 = 지금 열어 편집 중인 맵**(`plan_id` 폐기). stage는 `stages.*.target_map.table` 역인덱스로 유도, 미선언 맵은 404가 아니라 `stage_unknown` 경고 + `status:"unverified"`. `plan_store.doe` 미구성만 404 | ~3163 |
| GET `/enrichment/rules` · `.../references/{index}` | `get_enrichment_rules` / `get_enrichment_reference` | 인리치먼트 규칙 공개본·참조 뷰 조회 | ~3340/3351 |
| WS `/ws` | `websocket_endpoint` | WS 접속(ConnectionManager) | ~2291 |
| POST `/internal/events/batch-refresh` · `/broadcast` · `/file-processed` | `internal_event_*` | **워커/워처 → 웹서버 브로드캐스트 위임 (경계 계약)** — 수신부는 `total_log_count`(실건수) 우선 + `MAX_NOTIFY_CREATED_LOGS` 방어 절단(인시던트 `cc57b64`). [P1] batch-refresh는 msg 재구성 시 `total_log_count` 동봉(~3648 — 체인 passthrough 경로와 대칭화), broadcast는 `file_ingestion_progress`를 레지스트리에 인터셉트(~3673), file-processed는 레지스트리 제거 인터셉트(~3736) | ~3622–3742 |
| POST `/internal/events/ingestion-state` | `internal_event_ingestion_state` | **[P1 신설]** watcher → 진행 스냅샷 push(QUEUED/PROCESSING/FINISHED — heavy 파일만 명시 통지). **WS 브로드캐스트 없음** — 레지스트리 전용 내부 이벤트 | ~3743 |
| GET `/admin`·`/map-editor`·`/enrichment`·`/{path}` | `serve_*` | 정적 페이지 서빙(`graph.html`/`trace.html`은 catch-all `serve_static_or_index` ~4023 경유). **catch-all이 파일 최하단인 것이 계약** — `/health`가 이보다 위에 등록돼야 한다(§1.1-bis) | ~3971–4023 |

### 1.5 그래프 조회 구간 (read-only — `graph_nodes/edges` 직접 조회, 워커 미경유)

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| (상수) | `GRAPH_NEIGHBOR_NODE_CAP=500` / `GRAPH_LABEL_LIST_LIMIT_CAP=200` / `GRAPH_TRACE_NODE_CAP=1000` / `GRAPH_TRACE_DEPTH_CAP=3` 등 | 하드캡(C-7 무제한 로드 금지) | ~1942–1948 |
| (헬퍼) | `_escape_like_term(term)` | LIKE 메타문자 이스케이프 | ~1951 |
| (헬퍼) | `_expand_graph_subgraph(db, seed_nodes, depth, node_cap, edge_types=None, time_from=None, time_to=None)` | 뷰어/추적 **공용 BFS 코어** — 방향별 (from,type)/(to,type) 인덱스 2쿼리, 홉·방향당 엣지 페치 캡 2000, 노드 500청크 IN, 캡 절단 시 dangling 엣지 제외 | ~1956 |
| (헬퍼) | `_serialize_graph_nodes(nodes)` | 노드 `{id,label,identity_key,props}` 직렬화 | ~2049 |
| GET `/graph/stats` | `get_graph_stats` | label/edge_type GROUP BY 카운트 + last_sync | ~2057 |
| GET `/graph/neighbors` | `get_graph_neighbors` | k-hop(1\|2) 서브그래프 — `_expand_graph_subgraph([center])` 위임, truncated | ~2082 |
| GET `/graph/nodes/search` | `search_graph_nodes` | identity 시작일치 ILIKE 자동완성(limit 캡 50) + **빈 q + label = 라벨 전체 리스팅**(`df63f3a` — identity 오름차순, limit/offset, 캡 200. 전 테이블 덤프 금지 유지) | ~2117 |
| (헬퍼) | `_parse_trace_time(value, field)` | ISO 8601 파싱(`Z` 허용), 실패 시 400 | ~2178 |
| POST `/graph/trace` | `post_graph_trace(req: GraphTraceRequest, db)` | **[G2]** 멀티 시드 BFS 합집합 — 시드 순서보존 dedup→(label,identity) 인덱스 조회→missing_seeds 분리→공용 BFS. depth 1..3, 시간·타입 필터, 의미 검증 400 | ~2190 |
| GET `/graph/mapping-summary` | `get_graph_mapping_summary` | `ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)` — materializer와 동일 신호원, 요청 시 디스크 로드 | ~2267 |

---

## 2. `server/database/crud.py` — 레이어링 코어

셀 단위 소스 레이어링(CellSource/CellOverwrite/priority) + 배치 업서트의 단일 구현. **시그니처 변경 시 전수 Grep 연쇄 갱신 필수**([규율](../guide/data_preservation_and_signature_change.md)).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `transaction_context(user, tx_id, source)` | 컨텍스트매니저 — 감사·outbox용 트랜잭션 식별 주입 | ~8 |
| `_warn_audit_truncation_once(table_name, col_name)` | [P2] 감사 값 절단 경고 dedup(테이블·컬럼당 1회). 호출부 ~294 | ~43 |
| **`_warn_undeclared_column_once(table_name, col_name)`** | **[`08d2b12` 신설] 미선언 컬럼 드롭의 침묵을 없앤다.** `column_types`에 없는 컬럼은 종전대로 **조용히 버려졌다** — 쓰기는 성공을 반환하므로 호출자는 데이터가 사라진 줄 몰랐다. **드롭 동작 자체는 의도적으로 그대로**(거부하면 뒤처진 config가 장애가 된다) — 고친 것은 침묵뿐. 경고는 (테이블,컬럼)당 **프로세스 1회**. 레지스트리 키가 페이로드에서 오므로(깨진 헤더 행·값을 헤더로 뱉는 파서) 테이블당 `_MAX_UNDECLARED_WARNED_PER_TABLE=64`(~73) 상한이 있고, **포화 시 다시 침묵한다는 사실 자체를 1회 경고**한다. 호출부는 `apply_row_update_internal` 내부 ~608 | ~76 |
| `class LightCellSource` / `LightCellOverwrite` | ORM 미경유 경량 메타 객체(성능) | ~97/108 |
| `sanitize_to_utf8(data)` | cp949 등 오염 문자열 정화 | ~141 |
| `load_table_config()` / `update_table_config(new_config)` | table_config.json IO | ~163/172 |
| `cast_value_by_type(value, col_type, col_name)` / `clean_str_value(val)` | 컬럼 타입 캐스팅 | ~188/205 |
| `get_row_by_business_key(db, table_name, key_value)` | 비즈니스 키로 행 조회 | ~215 |
| `resolve_priority_map(table_name=None) -> dict` / `get_source_priority(source_name, table_name=None) -> int` | **소스 서열 단일 원천**(테이블별 오버라이드 포함) — compute_priority_value·graph materializer 공용. `SOURCE_PRIORITY`에 `chain_ingestion: 4` 등재 | ~229/244 |
| `compute_priority_value(sources, manual_priority_source, table_name)` | **표시값 결정** — user:0 < collision_merge:1 < pipeline_parser:2 < custom_script:3 < chain_ingestion:4 + 수동 Pin | ~249 |
| `create_audit_log(db, ..., transaction_id, business_key, add_to_cache)` | 감사 로그 1건 생성. [P2] `old_val`/`new_val`은 `event_constants.truncate_audit_value`로 **4096자 상한** — 절단본이 DB 저장본과 통지 dict **양쪽에** 동일 적용되고, 절단 사실은 값 내부 마커(`…[truncated: 총 N자]`)로 명시 | ~271 |
| `bulk_insert_audit_logs(db, logs)` | 감사 로그 벌크 삽입 | ~330 |
| `bulk_upsert_cell_sources(db, mappings)` / `bulk_upsert_cell_overwrites(db, mappings)` | 메타 테이블 벌크 업서트(ON CONFLICT) | ~350/382 |
| `bulk_delete_cell_overwrites(db, delete_keys)` | overwrite 벌크 삭제 | ~415 |
| `_get_or_create_row(db, table_model, update_item, row_cache, table_name) -> (row, is_new)` | row_id/비즈니스키로 행 확보(캐시 활용) | ~431 |
| `_update_row_business_key(row, key_col, update_item, row_cache)` | 비즈니스 키 갱신 | ~467 |
| `_load_metadata_row_cell(...) -> (sources_list, overwrite)` | 셀 메타 로드(캐시·업서트 큐 연동) | ~487 |
| `apply_row_update_internal(db, table_name, update_item, row_cache, sources_cache, overwrites_cache, transaction_id, logs_to_cache, cell_sources_to_upsert, cell_overwrites_to_upsert, cell_overwrites_to_delete, deleted_row_ids) -> (row, is_new, changed_cols)` | **[통합 코어]** 단일 행 업데이트 + 레이어링 재계산. 모든 쓰기 경로가 여기로 수렴. 미선언 컬럼 드롭 지점 ~605–609 | ~551 |
| `apply_batch_updates(db, table_name, batch: GeneralUpdateBatch)` | **배치 진입점** — tx 컨텍스트, 캐시 프리로드, 행별 코어 호출, 벌크 flush, outbox 발화. 반환 `(results, changed_cells, created_logs, deleted_row_ids)`. [P2] 워처가 이 함수의 commit에 오프셋 갱신을 동승시킨다. **`batch.replace_map`(~1050)** — 지정 시 `updates[0]`이 정하는 스코프의 기존 행을 클린 삭제 후 재기록(**차집합 계산 없는 집합 교체** 연산. 소비자: 맵 Push·DOE 저장) | ~1034 |
| `create_empty_row(s)_batch(db, table_name, count, user_name)` | 빈 행 생성 | ~1227/1232 |
| `delete_row(db,...)` / `delete_rows_batch(db, table_name, row_ids, user_name)` | 행 삭제(+감사·메타 정리) | ~1276/1280 |
| `delete_cell_source_batch(db, table_name, cells, source_name)` | 소스 레이어 일괄 삭제 + 표시값 재계산 | ~1344 |
| `delete_cell_source(db, ...)` | 단일 소스 삭제(배치 위임) | ~1500 |
| `set_cell_manual_priority_batch(db, table_name, updates, source_name, updated_by)` | 수동 Pin 일괄(§크고 복잡 — 표시값 재계산·감사 포함) | ~1505 |
| `set_cell_manual_priority(db, ...)` | 단일 Pin(배치 위임) | ~1864 |
| `get_ontology_mapping()` / `check_needs_rollback(table_name, modified_cols)` | 그래프 보조 — v2 검증+enrichment 승격 적용 결과 캐시 / v2 매핑 인식 rollback 신호(v1 폴백) | ~1873/1915 |

---

## 3. `server/parsers/directory_watcher.py` — 파일 인제션

워크스페이스별 폴더 감시 → 파서 실행 → **HTTP 아닌 직접 DB**(`crud.apply_batch_updates`) 업서트 → 웹서버에 `/internal/events/*` 콜백. 2026-07-25 std parser(무스크립트 표준 파싱)·기동/주기 스윕 통합, **워크스페이스 config.json 폐지**(`5fac5f0`).

> **경로 (2026-07-27):** config·워크스페이스 루트는 전부 `paths.config_path(...)` / `paths.WORKSPACE_DIR` 경유다. 아래 앵커는 HEAD `be58210` 실측(구 값 대비 일괄 +3줄).

- **[P1] heavy 레인**(`4fd8ac9`+`8b0fd03`) — 크기 임계(기본 10MB, `config/ingestion_settings.json` 파일 경계 핫리로드) 초과 파일을 전용 큐/워커로 이관해 observer 디스패치 스레드 HOL 제거. 워크스페이스 내 FIFO는 backlog 카운터+직렬화 락+논블로킹 재라우팅 3중 장치로 보존.
- **[P2] 체크포인트 재개 + 해시 dedup**(`f78ab0a`) — 파일 전체 sha256 시그니처(`sha256:<size>:<digest>`)를 계산해 ① 동일 시그니처 `DONE`이면 skip ② 미완이면 오프셋 재개. 저장소는 신규 테이블 `file_ingestion_checkpoints`([`ingestion_checkpoint.py` §5](#5-소형-서버-모듈)). **오프셋 갱신은 청크 upsert와 같은 트랜잭션** — "커밋된 행 수 == 기록된 오프셋"이 원자적으로 성립. 재개는 시그니처+`total_rows`+`source_kind`+오프셋 범위가 **전부** 일치할 때만. heavy/normal·스윕·관리자 재시도 4경로 동일 동작.
- 통지 로그 상한 `MAX_NOTIFY_CREATED_LOGS`는 `event_constants.py` 공용 상수 import.
- 테스트: `tests/test_workspace_config_deprecation.py`(21개) · `tests/test_heavy_lane.py`(27개, `hvy_test_*`) · `tests/test_ingestion_checkpoint.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `load_global_table_config() -> dict` | table_config.json 로드 (`paths.config_path` ~65) | ~60 |
| `warn_legacy_workspace_config(config_path)` | 레거시 config.json 발견 시 경로당 1회 deprecation WARNING | ~78 |
| `_log_alias_conflict_once` / `warn_invalid_std_parse_once` | 별칭 충돌·std_parse 비-bool 경고 dedup(키별 1회 — QA D5/D6) | ~102/110 |
| `DEFAULT_HEAVY_FILE_MB=10` / `INGESTION_SETTINGS_PATH` | [P1] heavy 임계 기본값·설정 파일 경로 — `paths.config_path("ingestion_settings.json")`(`.sample` tracked) | ~128/130 |
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
| `start_chain_ingestion_worker(db_session_factory)` | **메인 루프** — LISTEN 대기, 리로드 체크(1s 간격), 스윕, purge 스케줄. SYSTEM_RELOAD 블록에서 `models.refresh_dynamic_models(engine)`(지연 import) 호출 — 신규 테이블 CREATE 보충 안전망(이슈 #7). **[`8117456`] 루프 안에서 `heartbeat.beat("chain")`(~822)** — `/health`가 "살아 있음"이 아니라 **"진척이 있음"**으로 판정하는 근거(`server/utils/heartbeat.py`, [§5](#5-소형-서버-모듈)) | ~780 |

---

## 5. 소형 서버 모듈

### `server/paths.py` (70줄) — 데이터 루트 단일 오버라이드 지점
**`4ba13ae` 신설.** `DATABASE_URL`이 DB를 갈아끼울 수 있게 하듯, 디스크 위의 사용자 소유 트리를 갈아끼운다. **약 21개 모듈이 각자 `os.path.dirname(__file__)`로 조립하던 경로를 전부 여기로 모았다** — 데이터가 어디 있는지 결정하는 곳이 정확히 하나다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `SERVER_DIR` | 이 파일의 위치 = server 패키지 디렉터리 | ~33 |
| **`DATA_ROOT`** | `os.environ["ASSY_DATA_ROOT"]` **또는** `SERVER_DIR`. **미설정이 프로덕션이고 그때 레이아웃은 바이트 단위로 종전과 같다** | ~36 |
| `CONFIG_DIR` / `WORKSPACE_DIR` | `<DATA_ROOT>/config` / `<DATA_ROOT>/ingestion_workspace` | ~38/39 |
| `IS_ISOLATED` | `normcase(DATA_ROOT) != normcase(SERVER_DIR)` — 격리 환경 판별 | ~42 |
| `config_path(*parts)` / `workspace_path(*parts)` | 하위 경로 조립 | ~45/50 |
| `log_path(filename)` | 프로세스 로그는 **데이터 루트 직속**(종전 `server/server.log` 자리 그대로). 격리 프로세스가 사용자의 라이브 로그에 append하지 않게 하는 것이 요점 — 인시던트를 재구성하려고 읽는 파일에 드릴의 줄이 섞이면 안 된다 | ~55 |
| `describe()` | `data_root=… isolated=… db=…` 한 줄 — 각 프로세스가 부팅 로그에 찍는다 | ~68 |

> **의도적 제외**: `server/mappers/**`는 데이터가 아니라 **코드**이고 `sys.path`의 `mappers` 패키지로 해석되므로 이 모듈이 다루지 않는다.
> import 규약은 `event_constants.py`와 동일 — 모든 엔트리포인트에서 `server/`가 `sys.path`에 있으므로 `import paths`로 해석된다(그렇지 않을 수 있는 호출자는 `crud.py`와 같은 try/except 폴백).

### `server/process_supervisor.py` (431줄) — 자식 프로세스 감독
**`8117456` 신설.** 구 `run_decoupled_app.py`는 5프로세스를 띄우고 `while True: time.sleep(1)`을 돌았다 — 워처나 체인 워커가 죽어도 **아무도 탐지하지 않고 아무도 재시작하지 않았다.** 웹서버는 살아 있으니 UI는 멀쩡해 보이고 데이터만 조용히 멎었다. 테스트: `tests/test_process_supervisor.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `BACKOFF_BASE_SEC=2.0` / `BACKOFF_MAX_SEC=60.0` / `MAX_CONSECUTIVE_FAILURES=5` / `HEALTHY_UPTIME_SEC` | **재시도 예산** — 연속 n번째 실패는 `min(base·2^(n-1), max)` 대기, 예산 초과 시 `FAILED`로 **영구 정지**(배너 로그 + `/health` 비-200). 즉사하는 자식을 무한 재시작하면 CPU를 태우고 로그를 덮고 **무엇보다 감독이 동작하는 것처럼 보인다** | ~57–62 |
| `HEALTHY_UPTIME_SEC` | 이만큼 살아 있었다면 크래시 루프가 아니므로 **연속 카운터를 0으로 리셋**한다 — 이게 없으면 한 달에 한 번 재시작하는 시스템이 결국 아무것도 재시작하지 않게 된다 | ~61 |
| `STATE_RUNNING\|BACKOFF\|FAILED\|STOPPED` | 자식 상태 어휘 | ~68–71 |
| `status_path()` | `paths.config_path("supervisor_status.json")` | ~74 |
| `_descendant_pids(pid)` / `_kill_pids(pids)` | 종료 시 손자 프로세스까지 수거 | ~78/97 |
| `class ChildSpec(name, cmd, cwd, env, restartable=True, heartbeat=None, start_delay=0.0)` | 자식 1개의 기동법 + 죽었을 때의 처분. **`restartable=False`는 "이게 죽으면 전체를 멈춘다"**(데스크톱 창 닫기), **`heartbeat=`는 그 자식이 발행하는 비트 이름** — `/health`가 프로세스 관점(감독자)과 진척 관점(비트)을 조인하는 열쇠 | ~116/123 |
| `class Supervisor(specs, status_file, log, spawn, clock, sleep, …)` | `spawn`/`clock`/`sleep` 주입 가능 — **실제 프로세스를 띄우지 않고 실제 초를 기다리지 않고** 재시작 정책을 결정론적으로 테스트하기 위함(프로덕션은 아무것도 넘기지 않는다) | ~151/159 |
| ├ `start_all()` / `_start(child)` | 순차 기동(+`start_delay`). **spawn 예외도 즉사와 동일한 실패로 계산**한다 — 아니면 잘못된 커맨드라인에서 영원히 돈다 | ~208/215 |
| ├ `_register_failure(child, exit_code, reason=None)` | **정책 본체** — uptime ≥ `healthy_uptime`이면 연속 카운터 1로 리셋, 아니면 +1. 예산 초과 시 `FAILED` + `failure_reason` 기록 | ~233 |
| ├ `poll_once()` / `run()` | 1틱 점검(종료 감지·백오프 만료 재기동·상태 파일 갱신) / **`run_decoupled_app.py`의 sleep 루프를 대체한 메인 루프** | ~287/322 |
| ├ `stop_all(timeout=3.0)` / `snapshot()` | 종료(자손 포함) / `/health`가 읽는 상태 dict | ~331/375 |
| └ `write_status(force=False)` | `supervisor_status.json` 기록. **`updated_at`이 감독자 자신의 생존 신호** — 감독자가 죽으면 자식들은 계속 비트를 찍지만 이 타임스탬프가 멈추고 `/health`가 그걸 말한다 | ~406 |
| `read_status(path=None)` | 상태 파일 판독(`main.py` 헬스가 소비) | ~424 |

> 미드-인제션 워처를 재시작해도 안전하다는 것이 이 설계의 전제다 — P2 체크포인트 재개가 10만 행 중 3만 행 지점 `taskkill /F` 하에서 드릴됐고 커밋된 오프셋이 실제 행수와 정확히 일치했다(`agent_workspace/reports/QA_p2_drills_isolated.md` §2). **자동 재시작이 허용되는 근거는 그것 하나다.**

### `server/health.py` (280줄) — `/health` 판정표 (순수 함수)
**`8117456` 신설.** 테스트: `tests/test_health_endpoint.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `STATUS_OK\|DEGRADED\|UNHEALTHY` / `HTTP_OK=200` / `HTTP_UNHEALTHY=503` | 상태 어휘와 HTTP 사상 | ~38–43 |
| `STARTUP_GRACE_SEC=60.0` | 갓 뜬 워커는 모듈 import 후 루프에 닿아야 비트를 찍는다. 이 유예가 없으면 부팅마다 503이 나가고, **부팅 때마다 틀리는 헬스체크는 무시당한다** | ~48 |
| `OUTBOX_AGE_DEGRADED_SEC=300` / `OUTBOX_AGE_UNHEALTHY_SEC=900` / `OUTBOX_COUNT_CAP=10000` | **백로그는 크기가 아니라 나이로 잰다.** 정상적인 10만 행 인제션 1건이 outbox 약 11.6만 행을 만든다(P2 드릴 실측) — 멎은 워커를 잡을 만큼 낮은 크기 임계는 대용량 파일마다 오발화한다. "바쁨"과 "멈춤"을 가르는 건 큐가 **빠지는가**이고, 빠지고 있으면 뒤에 몇 행이 쌓였든 가장 오래된 미처리 행은 젊게 유지된다 | ~55–59 |
| **`compute_health(db_result, heartbeats, supervisor_status, outbox_result, stale_after, now=None) -> (payload, http_status)`** | **판정표 본체 — I/O 없음**(DB·감독자·워커 없이 직접 테스트 가능). 워커 판정은 감독자 뷰 × 비트 뷰의 조인: `not running→down` · `running + 비트 낡음→wedged` · `running + 비트 없음 + 어림→starting` · `running + 비트 신선→ok`. **비트의 pid가 감독 대상 pid와 다르면 비트를 없는 것으로 친다**(~169–177) — 손으로 띄운 유령 워커나 같은 데이터 루트를 공유하는 두 번째 스택이 wedged된 진짜 워커를 가리는 것이 **실제로 관측됐다**. 재시작 직후 죽은 전임자의 신선한 비트가 후임을 대신 살아 있게 만드는 경우도 같은 가드로 막는다 | ~66 |
| `probe_outbox(db)` | 백로그 나이 + (상한된) 크기. 둘 다 부분 인덱스 `idx_outbox_unprocessed`를 타고, 나이는 `ORDER BY id ASC LIMIT 1`로 **테이블 크기와 무관한 O(1)**, 카운트는 `LIMIT cap+1`로 감싸 1천만 행 테이블에서도 ~1만 인덱스 엔트리를 넘지 않는다 | ~250 |

### `server/utils/heartbeat.py` (174줄) — 워커 진척 비트
**`8117456` 신설.** 프로덕션 인시던트는 이벤트 루프 프리즈였다 — 프로세스는 내내 살아 있었고 수십 초간 아무것도 서빙하지 못했다. **pid 점검은 그걸 healthy라고 답한다.** 그래서 워커는 **자기 루프 안에서** 진척을 발행한다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `HEARTBEAT_DIRNAME="worker_heartbeats"` / `heartbeat_dir()` / `heartbeat_path(name)` | 저장 위치 — **`paths.config_path("worker_heartbeats")/<name>.json`** | ~56/85/89 |
| `MIN_WRITE_INTERVAL_SEC=1.0` | 워커당 초당 1회 초과 디스크 접촉 금지(비트 1건 ≈ 200바이트 원자 replace) | ~60 |
| `DEFAULT_STALE_AFTER_SEC=60.0` | **감으로 고른 숫자가 아니다** — 자연 루프 주기(워처 3.0s · 체인 2.0s · 그래프 2.0s · 스케줄러 5.0s) 기준 **가장 느린 루프로도 연속 12회 이상 결번**. 1회 결번으로 알람이 울리면(GC 정지·느린 디스크) 헬스체크는 음소거되고, 그건 없느니만 못하다 | ~79 |
| `beat(name, note=None, force=False)` | **워커의 실제 작업 루프 안에서 반복마다 호출.** 반환값은 테스트용이고 호출자는 무시한다. 고정 temp 파일명 + `os.replace`로 **원자적**(독자가 부분 파일을 보지 않는다). **모니터링 기능이 새 장애 모드가 되면 안 되므로 모든 디스크 오류는 삼키고 카운트만 한다** — 워커 루프로 예외를 올리지 않는다 | ~93 |
| `read_all(stale_after, now=None) -> {name: {...}}` | 전 비트 판독(+`age_seconds`/`stale`). **읽을 수 없거나 깨진 파일은 건너뛰지 않고 `error` 필드를 단 stale로 보고한다** — 침묵은 헬스체크가 절대 주면 안 되는 답이다 | ~135 |

> **비트 이름 4종**: `watcher`(`run_watcher.poll_pending_retries` ~154) · `chain`(`chain_ingestion_worker` ~822) · `graph`(`graph_sync_worker` ~621) · `scheduler`(`run_auto_update` ~515). 이 이름이 `run_decoupled_app.py`의 `ChildSpec(heartbeat=…)`와 짝을 이룬다.

### `server/product_tables.py` (189줄) — 제품 소유 테이블 선언 정본
**`8e80fcc` 신설.** 소유권 경계: **제품 소유**(assyManager 자신의 저장소 — 이름·컬럼을 제품이 정하고 사이트가 바꿀 이유가 없다)는 여기 선언, **사이트 소유**(고객 공장 데이터 — 배포마다 이름이 다르다)는 여기 절대 등재하지 않고 설치기도 건드리지 않는다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `ANNOTATION_KEYS = ("__comment",)` | 문서용 키. `models.init_dynamic_models`가 읽지 않으므로 런타임 동작을 바꿀 수 없다 → 설치기는 이 키의 차이를 **drift가 아니라 note**로 처리한다(주석 한 줄 고친다고 기존 사이트 전부가 drift로 뜨면 안 된다) | ~35 |
| **`PRODUCT_TABLES`** | **4종**: `wafer_map_metadata`(~39, 맵 격자 규격 정본 — bk `target_table_map_id`) · `map_split_registry`(~60) · `map_doe`(~92) · `map_doe_source`(~133). 딕셔너리 순서가 config 파일에 append되는 순서다 | ~38 |
| `PRODUCT_TABLE_NAMES` | `tuple(PRODUCT_TABLES.keys())` | ~178 |
| `effective_declaration(entry)` | 주석을 걷어낸 **동작 유발 부분**만 남긴다(drift 판정용) | ~181 |

> **왜 두 번째 JSON이 아니라 Python 모듈인가**: `server/config/**`는 gitignored(`*.sample`만 tracked)라 그 안의 정본 JSON은 배포되지 않는다. 이 모듈은 코드이고 tracked이며 소비자는 정확히 둘 — ① `scripts/install_product_tables.py` ② `config/table_config.json.sample`(같은 설치기가 `--sample --apply`로 **생성**하고 `tests/test_install_product_tables.py`가 둘의 일치를 단언하므로 샘플이 조용히 어긋날 수 없다).
>
> ⚠️ **M2.6 진행 중 (2026-07-27)** — 보드 결정(`82d4e8e`)으로 **밴드가 두 정수가 되고 `map_doe`가 없어진다.** 위 4종은 HEAD `be58210` 기준 **커밋된** 상태이며 이 절과 [§7 `transfer_plan.js`](#7-client2src--웹-클라이언트)의 DOE 저장 모델은 곧 다시 바뀐다.

### `server/database/models.py` (~529줄) — ORM + 동적 모델/런타임 DDL
정적 ORM 클래스(`AuditLog` ~11 / `DatabaseOutbox` ~30 / `FileIngestionLog` ~98 / `FileIngestionCheckpoint` ~112 / `CellOverwrite` ~159 / `CellSource` ~176)와 **그래프 3모델**, config 주도 동적 테이블 관리 함수.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `class GraphNode` | 그래프 노드 — `(label, identity_key)` UNIQUE, props JSONB | ~198 |
| `class GraphEdge` | 그래프 엣지 — (from,type)/(to,type) 인덱스, `(from,type,to,source_name)` UNIQUE, `idx_graph_edges_row_ref(source_row_ref)` | ~215 |
| `class GraphSyncState` | materializer outbox 소비 커서(id=1 단일 행, `last_outbox_id`) | ~243 |
| `DYNAMIC_TABLES` | 동적 테이블 싱글턴(`sys._dynamic_tables_singleton`) | ~259 |
| `init_dynamic_models(config_dict)` | config → 동적 ORM 클래스 생성·등록. `column_types`/`business_key`/`composite_key_*`만 읽는다(그 외 키는 무시 — `product_tables.ANNOTATION_KEYS`의 근거) | ~264 |
| `sync_dynamic_tables_schema(engine)` | ⚠️ 이름과 달리 **존재하는 테이블의 ALTER 전용**(`has_table` 아니면 skip — 신규 CREATE 안 함). 부팅 경로에서만 호출 | ~351 |
| `_runtime_ddl_lock` | in-process DDL 직렬화 락(watchdog 스레드 vs reload-configs 요청 스레드) | ~388 |
| `create_missing_dynamic_tables(engine) -> list[str]` | **신규 테이블 한정 물리 CREATE**(이슈 #7) — information_schema 게이트 + `checkfirst=True` + 테이블별 독립 트랜잭션(실패 자체 rollback). 기존 테이블 런타임 ALTER는 범위 밖(C-8) | ~391 |
| `ensure_graph_tables(engine) -> list` | 그래프 3테이블 생성(#7 패턴: 게이트+checkfirst+락+실패 격리) | ~432 |
| `ensure_ingestion_checkpoint_table(engine)` | [P2] `file_ingestion_checkpoints` 생성(동일 패턴) | ~469 |
| `refresh_dynamic_models(engine=None) -> list[str]` | **핫리로드 공용 진입점** — config 디스크 재로드 → `crud.TABLE_CONFIG` 싱글턴 갱신(빈/손상 config 시 기존 보존) → `init_dynamic_models` → engine 지정 시 물리 CREATE(+그래프 테이블 보장). 호출처: main `reload_local_process_cache` / config_watcher(간접) / run_watcher·chain worker·graph worker SYSTEM_RELOAD | ~502 |

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

### `server/graph_sync_worker.py` (~1,003줄) — 그래프 워커 (materializer 루프 + 백필 API :8090)
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `ONTOLOGY_PATH` / **`VIRTUAL_GRAPH_PATH`** | `paths.config_path("ontology_mapping.json")` / **`<paths.DATA_ROOT>/database/virtual_graph.json`**. 후자가 `paths` 경유인 것은 이 파일이 **쓰기 대상**이기 때문 — `save_virtual_graph()`(~293)가 통째로 덮어쓰므로, `__file__`에서 조립하던 종전 코드로는 격리 워커가 **라이브 파일을 덮어썼다** | ~16/282 |
| `_load_graph_mappings()` / `_get_or_init_graph_cursor(db)` / `_reload_graph_worker_configs()` | 매핑 로드 / 커서 초기화(최초=현재 최대 outbox id) / SYSTEM_RELOAD 리로드(이슈 #8) | ~480/488/527 |
| `run_graph_materializer_loop()` | **메인 루프** — LISTEN/NOTIFY + keyset 커서, 배치 본체 `_run_one_batch`를 `asyncio.to_thread` 격리, `[GraphLatency]` 계측. 루프 안 `heartbeat.beat("graph")` ~621 | ~551 |
| `get_row_data_for_sync(db, table_name, row_ids)` | ⚠️ DEPRECATED(신규 배선 금지) | ~651 |
| `_neo4j_chunk_hook_factory(table_name)` | Neo4j 병행 경로 청크 훅(G3 인터페이스 보존) | ~831 |
| `execute_manual_sync(table_name, row_ids) -> dict` | `/sync` 백필 — 키셋 청킹 + 테이블당 `batch_refresh_required` 1건 + to_thread, `"all"` 지원 | ~854 |
| `startup_event()` | TABLE_CONFIG 동기화 + `ensure_graph_tables` + 루프 기동(`GRAPH_MATERIALIZER_ENABLED`) | ~973 |

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

### `server/bonding_plan.py` (~442줄) — [본딩 M1] 역할 바인딩 config 로더 + 집계 코어
`paths.config_path("bonding_plan_config.json")`(gitignored, `.sample` tracked) — 역할(process_history/defect/eds_fail/used_chips/total_chips)→실테이블·컬럼 바인딩. 테스트: `tests/test_bonding_plan.py`(20개, `bdp_test_*`).

> **좌표 변환은 이 모듈에 없다 (2026-07-27 일원화).** 구 `normalize_align`/`make_align_transform`/`align_status_label`은 **삭제**됐고 정렬은 `map_overlay.resolve_map_transform`(메타 델타 유도)을 경유한다. `sources[].align` config 선언도 폐기 — 정렬의 근거는 `wafer_map_metadata` 하나뿐이다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `ROLES` / `HISTORY_LIMIT=50` / `MAX_REGION_RECTS=50` / `MAX_REGION_POINTS=100k` | 역할 어휘·이력 상한·region 하드캡 | ~37–40 |
| `CANONICAL_FRAME_ROLES` (상수) | canonical(CORE) 프레임 후보 순서 `("total_chips","defect","eds_fail")` — **좌표를 바인딩한 첫 역할**이 기준을 정의하며 그 역할에 메타가 없으면 canonical은 None(뒤 역할로 넘어가지 않는다 — 넘어가면 회전된 계측 맵이 기준을 참칭해 조용히 identity가 된다) | ~44 |
| `load_bonding_plan_config(path=None) -> dict` / `_valid_source(src)` | config 로드·검증(미연결 역할은 부분 가동) | ~51/68 |
| `parse_region(region_str)` / `clamp_rects(rects, grid)` / `_point_in_rects(x, y, rects)` | region rects 파서(잘못된 형식 → 400 소재) / canonical 메타 치수로 클램프(완전 밖 rect 제거) / 점 포함 판정 | ~80/106/126 |
| `load_map_meta(db, config, target_table, map_id, cache=None)` | wafer_map_metadata의 **grid_metadata 원본 dict** 조회(config `map_metadata` 바인딩 경유). 정렬 유도의 근거이므로 격자 치수만 잘라 쓰면 안 된다. `cache`는 요청 경계 스냅샷(N+1 금지) | ~137 |
| `load_grid_meta(db, config, target_table, map_id, cache=None)` | 격자 규격만 필요한 호출자용 축약(region rect 클램프 전용) | ~182 |
| `_resolve_model_columns(source_cfg, required)` / `_fetch_points(db, cols, filters, distinct_pairs=False)` | 바인딩 해석 / 좌표 페치(하드캡 적용) | ~197/216 |
| `get_core_summary(db, lot, slot, rects=None, config=None) -> dict` | **집계 진입점** — 역할별 카운트(맵 모드 fail_values 필터, used_chips distinct), `remaining = total − defect − eds_fail − used`(음수 가능 — 과도기), history 50건+warnings, region 교차(좌표 하드캡 100k, 응답 미포함). 좌표 정렬은 `map_overlay.resolve_map_transform`(~293) + `map_overlay.align_status_label`(~306) 위임 | ~227 |

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

### `server/map_overlay.py` (~695줄) — [M2 신규] 범용 맵 오버레이 (계획 전용 아님 — 맵 인프라)
`paths.config_path("map_overlay_config.json")`(gitignored, `.sample` tracked) — 키 구조만: `table_bindings.{table}.columns{x,y,val,key_columns}`, `paint_lock.{"*"|table}{enabled,blocking_values,from_overlay,message}`. `APIRouter` 없음 — `main.py`가 `@app.get`으로 직접 등록해 위임한다. 테스트: `tests/test_map_overlay.py`.

> **삭제된 선언 레이어 (2026-07-27, `4ba13ae`)** — `align_overrides`(config 선언)·`by_eqp` 분기·`align_override_declared` status·`_frame_grid_of`가 **전부 제거**됐다. 정렬의 근거는 이제 `wafer_map_metadata` 하나뿐이며 `resolve_align`은 **메타만** 받는다. config에 `align_overrides`나 `sources[].align`을 다시 쓰는 코드를 보면 그것은 부활이 아니라 **오류**다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `MAX_OVERLAY_CELLS=20,000` / `MAX_OVERLAY_SOURCES=8` | 오버레이 1종당 셀 상한(초과 시 `truncated:true`) / 요청당 소스 상한 | ~70/71 |
| `STATUS_OK` / `STATUS_ALIGN_UNAVAILABLE` / `STATUS_SOURCE_MISSING` / `STATUS_NO_DATA` | 엔트리 status 어휘 | ~73–76 |
| `ALIGN_ORIGIN_DERIVED` / `ALIGN_ORIGIN_IDENTITY` | align 결정 출처 마커 — **둘뿐이다.** `DECLARED`/`DEFAULT`는 선언 레이어와 함께 삭제됐다 | ~78/79 |
| `ALIGN_ORIGIN_UNRESOLVABLE` | 구 QA-B3 가드 유물 — **프레임 합성(A1) 도입 후 더 이상 발화하지 않는다**(상수만 잔존) | ~82 |
| `load_overlay_config(path=None)` / `load_map_meta(db, target_table, map_id)` | config 로드(부재·손상 시 `{}` — 에러 아님) / `wafer_map_metadata`(`META_TABLE` ~103)의 `grid_metadata` 조회 | ~85/106 |
| `_rotation_of` / `_grid_of` / `_side_of` / `_y_invert_of` / `PHYS_KEYS` / `_phys_signature` | 메타 정규화 헬퍼 — `_grid_of`는 메타 선언 그대로의 **물리(canonical) 격자 규격**, `_phys_signature`는 `phys_*` 6값 튜플(하나라도 없으면 None = bbox 재현 불가) | ~128/135/150/154/158/162 |
| `frame_axes(meta)` | 프레임 정의 8축 튜플 `(rot, side, y_invert, start_x, start_y, cols, rows, phys_sig)` — identity 지름길 판정·transformer 캐시 키 | ~172 |
| **`_frame_phys_params(meta)`** | **[A1]** 물리 규격 → **프레임 축 규격**. `is_cell_inside_wafer(c, r, …)`는 프레임 인덱스를 받으므로 rot 90/270에서 **칩 피치를 스왑**하고 back에서 `off_x` 부호를 뒤집는다. 유일 호출자는 `_frame_transformer`. **보정을 이 모듈 안에 가둔 것이 계약** — `WaferMapCoordinateTransformer`·`PhysicalWaferEngine`은 무수정(`bonding_plan.py`가 같은 클래스를 공유) | ~190 |
| `_FRAME_TF_CACHE` / `_frame_transformer(meta, grid)` | transformer(+engine) 생성 후 `frame_axes` 키로 캐시(상한 512 초과 시 전체 clear) | ~237/241 |
| `make_frame_transform(source_meta, target_meta)` | **소스 프레임 → 물리 → 타깃 프레임** 합성 변환기(내부 `to_target(x, y)` ~314). 메타/격자/phys 부재·물리 치수 불일치 시 `ValueError` | ~271 |
| `_align_summary(rotation, flip)` / `align_status_label(align)` | 표시용 요약 dict(변환에는 안 쓰인다) / 상태 문자열 마커 `aligned:180` 등 — **`bonding_plan`에서 이관**(변환 소유 모듈이 마커도 소유). 소비자: `bonding_plan.get_core_summary` ~306 · `transfer_plan._canonical_fail_set` ~620 | ~324/335 |
| `resolve_align(source_meta, target_meta) -> (align\|None, origin, note)` | **align 결정 규율 — 인자는 메타 둘뿐이다.** 메타 델타 유도 > **identity**(메타 부재는 실패가 아니라 등록 누락 신호). origin은 `derived`/`identity` 둘뿐 | ~354 |
| **`resolve_map_transform(source_meta, target_meta) -> (transform\|None, align, origin, note)`** | **서버의 단일 좌표 변환 진입점.** 오버레이(그리기)와 가용량 산출(`bonding_plan`/`transfer_plan`)이 **같은 이 함수**를 쓴다. transform None = identity, 계산 불가 시 `ValueError`(호출자가 `align_unavailable`로 표면화) | ~394 |
| `_pure_translation(source_meta, target_meta, origin)` / `align_applied_payload(align, origin, note=None, translation=None)` | derived이고 rot/side/y_invert/격자/phys가 전부 같을 때만 `(dx,dy)` / 클라 표시용 `{rotation, flip, offset, origin, note?}` | ~413/429 |
| `parse_sources(spec) -> [(table, key\|None)]` | `"table"` / `"table:key"` CSV 파싱 — 8종 초과·빈 값은 `ValueError`(→400) | ~452 |
| `VAL_CANDIDATES` / `_SYSTEM_COLUMNS` / `derive_table_binding(table)` / `resolve_binding(cfg, table)` | `table_config`에서 x/y/val·key_columns 자동 유도(후보 순, 시스템 컬럼 제외) / **선언 우선 + 유도 폴백** | ~475/478/484/522 |
| `build_key_filters(model, binding, map_key)` | `_` 조인 복합 map_key를 key_columns로 분해해 ORM equality 필터 생성(마지막 컬럼이 나머지 흡수) | ~534 |
| `get_overlay(db, cfg, target_table, target_key, sources, cell_cap=MAX_OVERLAY_CELLS) -> dict` | **메인 진입점** — 소스별 바인딩·align 해결 → 셀 조회 → 타깃 프레임 좌표 변환 → `{target, overlays[], cell_cap}`. **`eqp` 인자는 `by_eqp` 분기와 함께 삭제됐다**(엔드포인트 쿼리 파라미터만 no-op으로 존치 — 축소는 총괄 승인 사항) | ~559 |
| `get_paint_rules(cfg, table=None) -> dict` | `paint_lock`의 `"*"` 기본 + 테이블별 선언 머지 → `{enabled, blocking_values, from_overlay, message}` | ~676 |

> `resolve_binding`·`build_key_filters`는 **`transfer_plan.py`도 재사용**한다(모듈 간 공용 헬퍼 2개).
>
> **소비자 지도 (2026-07-27 정렬 일원화 이후)**: 이 모듈의 정렬 함수군을 쓰는 것은 ① `/api/maps/overlay` 엔드포인트 ② **`bonding_plan.get_core_summary`** ③ **`transfer_plan._canonical_fail_set`** ④ `test_map_overlay.py`다. ②③이 이번에 배선됐고(구 A2), 그 결과 **정확한 구현이 운영 소비자를 갖게 됐다** — 종전에는 맞는 구현이 엔드포인트에서만 돌고 가용량은 안 고쳐진 사본으로 계산됐다. **맵 에디터 클라는 이 엔드포인트를 더 이상 호출하지 않는다**(변환은 클라 단일 구현 — [§7 `map_editor.js`](#7-client2src--웹-클라이언트)). `transfer_plan.py`는 정렬 함수 외에 바인딩·config 헬퍼 3개(`resolve_binding`/`build_key_filters`/`load_overlay_config`)도 쓴다.
>
> **구현 개수**: 서버 1(이 모듈) + 클라 1(렌더) = **2**. 가용량이 서버에서 계산되는 한 이것이 하한이다.

### `server/transfer_plan.py` (~1,454줄) — [M2 신규] Universal Transfer Plan 엔진 (v2 = 계획 정체성이 곧 맵 정체성)
`paths.config_path("transfer_plan_config.json")`(gitignored, `.sample` tracked) — `stages.{name}.{source_kind, target_kind, target_map{table,preset}, source{...} \| source_config_ref}` + `plan_store.{doe, doe_source, source_region}`. 테스트: `tests/test_transfer_plan.py`.

> **좌표 변환 사본 없음 (2026-07-27)** — 구 `bonding_plan.make_align_transform`은 저장 좌표의 바운딩박스 규약을 반영하지 않아 삭제됐고, 이 모듈은 `map_overlay.resolve_map_transform` **하나만** 쓴다(~614).
> ⚠️ **M2.6 진행 중** — `map_doe`가 없어지고 밴드가 두 정수가 되는 결정(`82d4e8e`)이 곧 착지한다. 아래 `plan_store`·DOE 관련 서술은 HEAD `be58210`의 **커밋된** 상태다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `MAX_ORIGIN_POINTS/MAX_FAIL_POINTS=100k` · `MAX_BY_CORE=500` · `CORE_ID_SEP="\|"` · `MAX_DOE_PER_PLAN=500` · `MAX_PLAN_VALUES=1000` · `MAX_SOURCES_PER_DOE=64` · `MAX_REGION_CELLS=100k` | 하드캡 일습(무제한 로드 금지) | ~80–87 |
| `WARN_*` **14종** | validate·강등 경고 타입(`qty_shortage`·`layer_range_invalid`·`layer_coverage_gap`·`undefined_doe_value`·`doe_value_unpainted`·`source_fail_chips`·`source_history_fail`·`stage_unknown`·`source_unresolved`·`source_degraded`·`availability_unreliable`·`source_overallocated`·`result_truncated`·`negative_remaining`) | ~92–109 |
| `EFFECT_*` **5종** | **효과 분류** — `population_mismatch`(~110) / `remaining_overstated`(~113) / `total_unknown`(~114) / `by_core_degraded`(~115) / `history_incomplete`(~116) | ~110–116 |
| `load_transfer_plan_config(path=None)` / `get_stages(cfg)` / `_valid_binding(src)` | config 로드(부재·손상 시 부분 가동) / stages dict 추출 | ~123/140/145 |
| `_resolve(src_cfg, required)` / `_binding_status(...)` / `_stage_role_statuses(stage_cfg)` / `_plan_store_statuses(cfg)` | 바인딩 → (model, 컬럼맵) / `connected`\|`missing` / stage 역할별·plan_store 역할별 상태 | ~154/166/173/204 |
| **`stage_of_table(cfg, ref_table)`** | **[v2 핵심] `stages.*.target_map.table` 역인덱스** — 열린 테이블에서 stage를 유도한다(별도 stage 선택 UI 폐기의 근거) | ~229 |
| `list_stages(cfg)` | `GET /api/transfer-plan/stages` 응답 `{stages[], plan_store}` | ~246 |
| `_status_is_degraded` / `_degradation_effect(role, fail_roles)` / `assess_degradation(statuses, fail_roles)` | **[QA F1 1층]** 역할 강등 탐지 → `(경고 리스트, remaining_reliable, total_reliable)` | ~267/280/294 |
| `build_chips_block(total, fail_breakdown, transferred, remaining, remaining_reliable, total_reliable)` | **[QA F1 3층]** chips 블록 조립 + **음수 remaining 불변식**(전 역할 connected여도 음수면 신뢰 박탈). 신뢰불가면 `remaining: null`을 내려 **오표시를 구조적으로 차단**하고, `total_reliable ∧ remaining≥0`일 때만 `remaining_upper_bound` 부가 | ~333 |
| `load_source_region(...)` / `_region_block(...)` / `_core_region_counts(...)` | 계획이 이 소스에서 쓸 셀 집합 로드(**현재 휴면** — 라이브 config에 `plan_store.source_region` 미선언이라 항상 None) / 영역 내 집계 / core-kind 어댑터 | ~374/408/434 |
| `_reshape_m1_summary(m1, stage_name, stage_cfg)` | M1 `bonding_plan.get_core_summary` 응답을 M2 공통 형태로 재성형(같은 강등 규율 적용) | ~492 |
| `_fetch_pairs(...)` / `_origin_map_id(source_cfg, origin_lot, origin_slot)` | 좌표쌍 페치(캡 적용) / origin map_id 조립 | ~528/544 |
| `_canonical_origin_meta(...)` / `_canonical_fail_set(...)` | origin-frame 원천의 **canonical 맵 메타** 로드 — 좌표를 바인딩한 **첫** 원천이 기준을 정의하고 그 원천에 메타가 없으면 None(뒤로 넘어가지 않는다. 넘어가면 회전된 계측 맵이 기준을 참칭해 조용한 과소 집계) · 코어당 1회 캐시 / 코어 1장 fail 좌표를 `map_overlay.resolve_map_transform`(~614)으로 canonical 프레임 set에 사상(미해결이면 `(None, "align_unavailable", False)`; **소스 메타만 있고 canonical이 없는 비대칭도 거절**) | ~550/587 |
| `_collect_history(db, source_cfg, lot, slot)` | process_history 최근 N건(시간 오름차순) + result fail 경고 | ~629 |
| **`_summarize_inline(db, stage_name, stage_cfg, lot, slot, region=None)`** | **가용 엔진 정본(tape-kind)** — `origin_log` 연결 시 `remaining = total − \|fail_union ∪ used_set\|`(칩 단위 합집합 — 이중 감산 없음), 미해석 시 M1식 감산 폴백. `by_core` 7키(`core_id, core_lot, core_slot, total, fail, used, remaining`) + `by_core_origin` 마커 `"log"`(정확) \| `"area_map"`(강등 — `fail=None`으로 0 위장 금지) | ~676 |
| `get_stage_source_summary(db, cfg, stage_name, lot, slot, bp_config=None, ref_table=None, map_key=None)` | **핸들러 진입점** — M1 ref 경로(reshape) / inline 경로 분기, 미선언 stage는 `KeyError`(→404) | ~1035 |
| `_plan_store_binding(cfg, role, required)` / `_num(v, default=None)` | plan_store 역할 바인딩 / 수치 파싱 | ~1075/1081 |
| `_band_range(band)` / `_painted_values(db, ref_table, map_key, overlay_cfg)` | STACK 구간 표기(`1`/`2-11`/`H1~H2`) 파싱(못 읽으면 경고 없이 불참) / **대상 맵 자신**의 셀 값 분포 group-by(`map_overlay.resolve_binding`·`build_key_filters` 재사용) | ~1091/1113 |
| `validate_plan(db, cfg, ref_table, map_key, overlay_cfg=None)` | **핸들러 진입점** — `remaining_reliable=False`면 부족·fail 판정을 **전부 생략**하고 `availability_unreliable`만 발행(오염된 과대 remaining으로 "부족 아님"을 판정하지 않는다). 최종 `status`는 `ok`/`warnings`/**`unverified`** 3값 — **"검사 안 함"과 "이상 없음"을 같은 값으로 내지 않는다.** `plan_store.doe` 미구성은 `LookupError`(→404). 내부 `_doe_get`(~1195)·`_get_summary`(~1293) | ~1151 |

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
| `run_decoupled_app.py`(루트) / `server/run_watcher.py` / `run_chain_worker.py` / `run_graph_sync.py` / `run_auto_update.py` | 프로세스 런처(5-프로세스 토폴로지). **API 서버는 전용 런처 파일이 없다** — `run_decoupled_app.py`의 `main()`(~22)이 `server_cmd = [python_exe, "-m", "uvicorn", "main:app", "--port", api_port]`(~39)를 직접 띄우며, 포트는 **`ASSY_API_PORT` 환경변수로 오버라이드 가능**(기본 `"8080"`, ~32 — 런처 자신을 격리 스택 :8081에 걸어 감독 정책까지 실검증하기 위함). ~~`server/run_api.py`~~는 **존재하지 않는다**(2026-07-26 정정, 2026-07-27 재확인). **[`8117456`] sleep 루프가 `Supervisor`로 대체됐다** — `specs`(~50)는 `ChildSpec(..., heartbeat=…)` 5개(+ 비-server-only일 때 `restartable=False`인 데스크톱 셸 ~65), `supervisor.start_all()`(~97) 후 `supervisor.run()`(~105). run_watcher: `trigger_ws_ingestion_state`(~112 — [P1] 파일명 정규화 후 `/internal/events/ingestion-state` push) · 재처리 폴러 `poll_pending_retries`(~145, 루프 안 `heartbeat.beat("watcher")` ~154)는 `refresh_dynamic_models(engine)` 보충(이슈 #7) + `resolve_workspace_root` 역조회(별칭 대응) + 재처리를 `get_workspace_serial_lock`으로 감쌈([P1 QA F3] heavy와 순서 계약 편입) |
| `server/utils/physical_wafer_engine.py` · `coordinate_transformer.py` | 웨이퍼 물리 좌표 엔진(맵 에디터 서버측) |
| `server/utils/logger.py` (~103줄) | 프로세스별 로거 — `get_process_logger(process_name, log_filename)`(~66)의 파일 핸들러가 **`paths.log_path(log_filename)`**(~96)를 쓴다. 격리 프로세스가 사용자의 라이브 로그에 append하지 않는 근거 |
| `server/mappers/*` (gitignored) | 사용자 커스텀 체인 맵퍼 — **전수 Grep 시 반드시 포함**. ⚠️ **`paths.py`가 의도적으로 다루지 않는 트리**(데이터가 아니라 코드 — `sys.path`의 패키지로 해석) |
| `server/config/*.json` (gitignored) | table_config·chain_rules·enrichment_rules·ontology_mapping(v2 — `.sample`은 tracked) 등 사용자 설정. 실값을 이 문서에 옮겨 적지 말 것 — 구조만 기술한다 |

### 6-1. 설치·개발환경 스크립트 (`8e80fcc`·`4ba13ae`·`47c20f3` 신설)

| 파일 | 책임 |
|---|---|
| `server/scripts/install_product_tables.py` (653줄) | **[제품 소유 테이블 설치기]** `product_tables.PRODUCT_TABLES`를 사이트의 라이브 `table_config.json`에 설치한다. 대상이 **gitignored 사용자 자산**이라 규칙 전부가 그 파일을 지키기 위해 존재한다 — 사이트 소유 엔트리는 **재직렬화하지 않고 바이트 단위 스플라이스**로만 편집해(키 순서·들여쓰기·개행까지 보존) 스크립트가 추가하지 않은 것은 바이트 동일하게 나온다. 부재→추가 / 동일→**무쓰기** / 다름→drift 보고 후 방치(`--overwrite-drift` 필요). **드라이런이 기본**이고 쓰기는 `--apply`, 쓰기 전 타임스탬프 백업, 쓴 뒤 재스캔해 미변경 멤버를 원본과 바이트 비교하고 어긋나면 **백업 복원**. DDL·DB 접속·재기동은 하지 않는다(어느 리로드 경로가 적용되는지 안내만 출력). 종료코드 `0` 할 일 없음 / `1` 조치 필요 / `2` 오류. 핵심 함수: `scan_top_level_members`(~141) `detect_style`(~197) `apply_edits`(~221) `diff_declaration`(~258) `evaluate`(~295) `build_edits`(~330) `verify_untouched`(~521) `run`(~544). `--sample --apply`는 tracked 템플릿 `config/table_config.json.sample`을 **생성**한다 |
| `server/scripts/dev_env/devenv.py` (372줄) | **[격리 개발환경 CLI]** `DEV_ROOT=<repo>/dev_env`, `isolated_env()`(~71)가 `ASSY_DATA_ROOT`+격리 DB URL을 조립한다. 포트는 `ASSY_DEV_API_PORT`(기본 8081)·`ASSY_DEV_GRAPH_PORT`(기본 8091). 동사: `cmd_bootstrap`(~108, config/워크스페이스 복제 — `SKIP_CONTENT_DIRS={raws,archives,err}`는 구조만 뜨고 내용은 안 뜬다) `cmd_snapshot`(~145) `cmd_up`/`cmd_down`(~217/249) **`cmd_watcher_up`/`cmd_watcher_down`(~256/311 — 워처만 별도 기동)** `cmd_status`(~316) `cmd_env`(~335) |
| `server/scripts/dev_env/iso_watcher.py` (308줄) | **[격리 게이트]** 워처를 띄우기 **전에** 격리를 단언하고, 어긋나면 기동을 거부한다(`EXIT_REFUSED=9`, `REFUSED_MARKER` ~51). `check_static_isolation(...)`(~94, data_root·config·workspace 경로가 `server/` 밖인지) + `check_live_isolation(live_database, engine_url)`(~146, 실제 접속된 DB 이름이 `PRODUCTION_DB_NAMES={"assy_manager"}` ~55에 걸리는지 · 포트가 `PRODUCTION_API_PORTS={"8080","8090"}` ~58인지). 통과 시에만 `GATE_PASSED_MARKER`(~50)를 찍고 `_start_watcher`(~250) |
| `server/scripts/dev_env/snapshot_db.py` (420줄) | **[DB 스냅샷]** 라이브 → QA DB 복제. `open_source_readonly(url)`(~65)로 **소스는 읽기 전용 세션**, `CHUNK=1000`(~42) 라운드트립(10M행 규율 — 테이블 전량 로드 금지), `EMPTY_TABLES={"database_outbox"}`(~48)는 스키마만, `ROW_SCOPED`(~53)는 행 한정 복제. `build_target_schema`(~153) `copy_rows`(~181) `fix_sequences`(~217) `run`(~242) |
| `server/scripts/dev_env/manifest.py` (188줄) | **[변경 매니페스트]** 드릴 전후 파일·DB 상태를 떠서 비교 — `capture_files(root, label)`(~41, `CHURN_DIR_NAMES={raws,archives,err}` ~30 제외) `capture_db(db_url)`(~68) `cmd_capture`(~93) `cmd_diff`(~115) |

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

### `websocket.js` (~255줄) — 실시간 수신
- export: `initWebSocket`(~11, 재접속 백오프) `handleWebSocketMessage(msg)`(~72).
- 소비 이벤트: `file_ingestion_progress`(~73) `file_ingestion_completed`(~84) `batch_row_create`(~131) `batch_row_upsert`(~147) `batch_row_delete`(~229) `batch_refresh_required`(~244) → 델타 반영(`applyTransaction`)·페이지캐시 갱신.

### `ui.js` (~408줄) — 그리드 밖 UI 갱신
- export: `setupBeforeUnloadWarning`(~8) `updateSelectedCellUI`(~18) `updateTxModeUI`(~33) `setTransactionFilter`(~79) `applyValueToSelectedRange(newValue)`(~106, 범위 일괄 적용→배치 PUT) `updatePageCacheOnUpsert`(~260) `updateEnrichmentBadge`(~331) `notifyEnrichmentTableEvent`(~381) `updatePageCacheOnDelete`(~391).

### `clipboard.js` (~788줄) — 엑셀형 범위 선택/복붙
- export: `isCellInRange`(~8) `refreshRange`(~29) `refreshSelectedRangeDiff`(~57) `clearRangeSelection`(~92) `commitDragSelection`(~144) `getRangeSelectedTSV`(~172) `setupClipboardHandlers`(~281, copy/paste 이벤트 본체) `clearSelectedCells`(~617).

### `timeline.js` (~718줄) — 이력 타임라인 + 내비게이션
- export: `loadHistory`(~9) DOM 빌더 `createTimelineItemDom`/`createGlobalTimelineItemDom`(~50/103) 증분 렌더 `renderTimeline*`(~271–346) `renderSubDetails`(~362) `appendHistoryLocally`(~445) 로그→셀 점프 `navigateToLog`(~507)+`navigatorStep2/3`/`navigatorFinalScroll`/`releaseNavigationGuard`(~566–709).
- 소비 API: `/audit_logs/recent`, `/audit_logs/transaction/{tx}`.

### `map_editor.js` (~4,563줄) — 웨이퍼 맵 에디터 (단일 페이지 스크립트, export 없음)
- 좌표 변환 코어: `getPhysicalCoords`(~978) `getCellFromPhysicalCoords`(~1028) `getCellFromVisualCoords`(~1068) `getVisualCoords`(~1137) `getTransformedPhysicalConfig`(~1152) `getWaferBoundingBox`(~1085) `getScreenShift`(~1187) `isCellInsideWaferFast`/`isCellInsideWafer`(~1213/1251) — 회전/면반전 불변식은 [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md).
  - **[7d931dc] 프레임 창(frame window)** — `physFrameOverride`(~951) + `physNum`(~954)/`gridDimNum`(~963)/`withPhysFrame(frame, fn)`(~972). 변환 함수가 규격을 DOM에서 읽는 지점을 잠깐 갈아끼우는 장치로, **주입 지점은 `getTransformedPhysicalConfig`·`getWaferBoundingBox` 두 곳뿐**이다. `withPhysFrame`은 **동기 전용**(내부 `await` 금지 — `try/finally` 복원이 새면 조용한 오답). 기존 `parseFloat(v) || dflt` 규약(0 → 기본값) 보존.
- 캔버스 렌더: `renderGridCanvas`(~1603, 본체) `scheduleRenderGridCanvas`(~1566) `fitGridToWorkspace`(~1588) `updateNotchPosition`(~1944).
- 데이터 IO(REST — WS 아님): `loadExistingMap`(~2519) `pushMapData`(~2931, 저장 본체) `fetchGridMetaFor(table, mapId)`(~2486) 프리셋 `fetchAndRenderPresets`/`saveCustomPreset`/`deleteCustomPreset`(~1308/1414/1464) + `applyPresetObject`(~1364, `loadSelectedPreset` ~1397에서 추출한 공용 함수).
  - `fetchGridMetaFor`는 **404/405만 "규격 미등록"(null)**으로 읽고 그 외 실패는 **throw**한다(`[M2 fix]` — 종전엔 모든 실패가 null이라 오버레이가 조용히 identity로 폴백했다). `loadExistingMap`의 셀 레벨 `grid_metadata` 폴백은 **폐기 스킴**이며 어떤 맵 테이블도 스키마에 그 컬럼을 노출하지 않아 라이브에서 사문이다.
- 레전드/브러시: `renderLegendTable`(~2156) `selectBrush`(~2343) + `localStorage` 동기화 `load/saveLegendToStorage`(~1999/2017) + 서버 레지스트리 `fetchLegendFromServer`/`loadLegend`/`saveLegendToServer`(~2036/2054/2089). `getCurrentMapKey`(~2024)는 **로드된 맵이 아니라 현재 메타 입력 필드**를 읽는다(오버레이 관문 F2의 근원).
- 편집 도구: `fillGrid`(~2902) `getEdgeClassification`(~3172) `selectEdgeCells`(~3252) `autoPaintE1E2`(~3279) `copyGridToExcel`(~3367).
- 프레임 스택: `snapshotEditorState`(~3539) `restoreEditorState`(~3586) `openMapFrame`(~3804) `popMapFrame`(~3856). **복원 대상에 `overlayLayers`·캔버스 스크롤이 포함된다**(~3535 주석).
- **[M2] 페인트 잠금**(~36–148, 서버 선언 소비 — 구 `'F'` 하드코딩 대체): `isLockedValue`(~41) `isOverlayLocked`(~51) **`isProtectedFCell`(~63 — 편집 불가 판정의 단일 관문, 전 편집 경로가 여기로 수렴)** `applyPaintLockConfig`(~68) `fetchPaintRules`(~92, GET `/api/maps/paint-rules`) `updatePaintLockIndicator`(~126) `recomputeLockedCells`(~143). 404/405만 "선언 없음"(해제)이고 네트워크·5xx는 **직전 잠금 유지** + `source:'stale'` + 툴바 칩. ⚠️ **[QA C4 미해소] 콜드 스타트는 여전히 fail-open** — "직전 값"이 페이지 로드 직후엔 기본값 `NO_PAINT_LOCK{enabled:false}`(~37)라 첫 조회가 실패하면 8개 강제 지점이 열린 채 시작한다(칩은 뜨므로 **조용한** fail-open은 아님). 테이블 전환 시 실패하면 **이전 테이블의 잠금 값**을 새 테이블에 계속 적용한다(fail-closed 방향이라 안전하나 의미상 부정확).
- **[7d931dc] 오버레이 레이어**(~3899–4563) — **변환은 클라 단일 구현**이다. 계약은 [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md):
  - 상태 `OVERLAY_COLORS`(~3899) / `overlayLayers`(~3900, 레이어당 `{id, sourceTable, sourceKey, rawCells, frame, cells:Map(physKey→val), count, outside, color, visible, status, align, alignApplied, alignText, truncated, cap, failed, reason, targetOverride}`) / `activeOverlayLayers`(~3901) / `overlaySeq`(~3902) / `recomputeActiveOverlays`(~3904, 렌더 루프 내 재계산 금지) / `drawOverlayMarkers`(~3909, 렌더 호출 ~1765).
  - **프레임 계산**: `frameFromMeta(meta)`(~3933, `grid_metadata` JSON → 프레임 기술자. **없는 물리 항목은 undefined로 남겨** 현재 화면 값 폴백) / `currentFrame()`(~3960) / `resolveFrame(frame)`(~3973, 축 전부를 실값으로 확정) / `frameAxesKey(rf)`(~3990, 회전·면·y반전·START·치수·물리 6종 = identity/derived 판정의 유일한 근거).
  - **`projectCellsToPhys(cells, frame)`(~4001)** — 구 `overlayCellsToPhysMap`의 대체. `getCellFromVisualCoords` → `getPhysicalCoords`를 **소스 프레임을 씌운 채** 호출한다. `loadExistingMap` 셀 루프와 **같은 함수·같은 인자 순서**이며 다른 점은 규격을 소스 메타에서 읽는다는 것뿐 — **오버레이 전용 기하식은 0줄**이다.
  - `pushFailedOverlay`(~4020) — 실패도 목록 행으로 남긴다(같은 소스 중복은 갱신).
  - 소스 읽기: `OVERLAY_CELL_LIMIT=2000`(~4041, 메인 로드와 동일 상한) `fetchTableSchemaCached`(~4044) `OVERLAY_SYSTEM_COLS`/`OVERLAY_VAL_CANDIDATES`(~4053/4055) `deriveMapBinding(schema)`(~4059, 서버 `derive_table_binding` 규약을 `/tables/{t}/schema`에서 유도) `buildKeyFilters(keyColumns, mapKey)`(~4076, 서버 `build_key_filters`와 동일 — 마지막 컬럼이 나머지 흡수).
  - `addOverlayLayer(sourceTable, sourceKey, targetOverride)`(~4096) — **메인 로드와 코드 경로 완전 분리**. 흐름: ① 바인딩 유도 → ②③ `Promise.allSettled`로 셀 + 소스/타깃 메타 병렬 조회(셀 실패와 규격 실패를 다른 사유로 분리) → ④ 프레임 확정 → ⑤ `cols×rows` 호환성 관문 → ⑥ 정렬 요약 + 격자 밖 셀 카운트. 명명된 실패 status **4종**: `meta_unavailable` `binding_unavailable` `align_unavailable` `no_data`(+ 스키마·셀 조회 IO 실패는 일반 `error`). **구 `probeAlignDeclaration` 관문과 `align_unconfirmed`/`align_override_declared` 두 status는 서버 선언 레이어와 함께 삭제됐다**(2026-07-27, 근거 주석 ~3897) — 물어볼 선언이 없어졌다. **이 함수는 `/api/maps/overlay`를 호출하지 않는다**(REST 왕복 1회 감소).
  - `removeOverlayLayer`(~4290) `toggleOverlayLayer`(~4297) `clearOverlayLayers`(~4306).
  - `overlayGeomSig`(~4319) / `currentGeomSignature`(~4321) / `syncOverlayGeometry`(~4338, 서명 변경 시 `rawCells`+`o.frame`에서 재투영. 훅 2곳 — 렌더 ~1642 · 프레임 복원 ~3627). ✅ **[QA C7 해소]** 서명이 `cols|rows|startX|startY|yInvert|rotation|side` + **물리 6종(`phys_wafer_dia/chip_x/chip_y/offset_x/offset_y/edge_margin`)**을 담는다. 단 소스 메타가 완비되면 재투영은 항등이라, 이 6종이 실제로 일하는 곳은 **물리 규격 미등록 폴백 경로**뿐이다.
  - `overlayAlignChip(o)`(~4361) — 정렬 상태 칩. 판정은 **`align.origin`으로만** 한다(rotation/flip/offset으로 판단 금지 — y반전·START만 다른 보정을 "무보정"으로 오표시한다).
  - `importOverlayToGrid(id)`(~4392) — 유일한 의도적 교차: 오버레이 셀을 `gridData`로만 가져온다(**서버 쓰기 없음**, `isProtectedFCell` 존중, 웨이퍼 밖 셀 스킵, 정체성 불변). `ensureLegendValues`(~4448)는 **로컬 legend 캐시만** 갱신한다(Push 전 서버 무접촉).
  - `renderOverlayList`(~4463) `handleAddOverlayClick`(~4517) `CORE_CANONICAL_TABLE='core_defect_map'`(~4546) `addOverlayForSource(sourceTable, lot, slot)`(~4548) `listOverlayLayers`(~4557) — 뒤 둘은 `transfer_plan.js`에 넘기는 컨트롤러 표면(~307 `clearOverlays: clearOverlayLayers` 포함).
  - **오버레이 해제 지점은 2곳이다** — 맵 로드 `loadExistingMap`(호출 ~2563, 토스트) · **테이블 전환 `switchTable`(호출 ~819, 토스트 — `251dbfd` 신설)**. 둘 다 `overlayLayers.length > 0`일 때만 실행한다. ⚠️ **`openMapFrame`은 오버레이를 해제하지 않는다**(과거 지도의 "3곳" 서술은 오류였다) — 프레임 스택은 반대로 오버레이를 **보존**하며, 구 모드 전환이 진입/이탈 양쪽에서 전멸시키던 것을 해소한 것이 재설계 v2의 요지다(~3532 주석). 툴바 버튼 배선은 ~469.
- [M2-v2] 전사 계획 배선: `initTransferPlan({...})`(~282, import ~6) + `notifyMapContext`(~826/2880/3135/3844–3868) `notifyLegendChanged`(~2140/2157/2357) `notifyPaintCounts`(~1518). rect 영역 선택 모드는 **전면 폐기**(값 페인팅이 정본 — 코드 부재).

### `transfer_plan.js` (~1,425줄) — [M2-v2] 전사 계획 사이드바 (map_editor.html에서 소비)
**「계획 = 지금 열어 편집 중인 그 맵」.** 계획 정체성은 `(ref_table, map_key)`이며 `plan_id`도 계획 맵 사본도 없다. 스타일은 `transfer_plan.css`. (구 M1 `bonding_plan.js`/`.css`는 `8e34804`에서 **삭제**됐다 — 파일 자체가 없으므로 앵커를 달지 말 것.)

> **⚠️ M2.6로 곧 다시 바뀐다** — 보드 결정(`82d4e8e`)에 따라 `map_doe`가 없어지고 밴드가 두 정수가 된다. 아래는 HEAD `be58210`의 **커밋된** 상태이며 DOE 저장 모델 서술은 다음 배치에서 통째로 교체될 예정이다.

- **[`3ebd38e`] 삭제는 차집합이 아니라 집합 교체로 한다.** 구 `pruneScoped(table, keyCol, keep, knownKeys)`(클라측 차집합-후-삭제 기계장치)와 그 권한 근거였던 **`S.serverKeys{doe:Set, source:Set}`가 함께 삭제**됐다. 플랫폼이 이미 같은 연산을 갖고 있었다 — **`replace_map`**(`crud.apply_batch_updates`, 맵 Push가 쓰던 것). 삭제 근거 주석은 ~1103–1118.
- 상태 `S`(~58–89): `stages`/`stagesStatus` · `ctx{table,mapKey,loaded,depth,parent}` · `legendRows` · `doe: Map<value, Band[]>`(`Band = {seq, stack, need, materials[], knobs[]}`) · `openValue` · `counts` · `activeBrush` · `summaries` · `matMapState` · `keyColumns` · `savedAt`/`serverSavedAt` · `planTablesSupported` · **`doeServerLoaded`(~75)** · **`serverRows{doe:0, source:0}`(~79 — 구 `serverKeys`의 대체. "지울 게 없다"와 "지우겠다는 표현을 못 했다"를 구분하는 **카운트일 뿐**, 무엇을 지울지 결정하는 데는 쓰지 않는다)** · `saveError` · **`deleteUnsent`(~84)** · **`loadSeq`(~85)** · `matSeq` · `flash` · `navBusy`.
- 진입/통지 export: `initTransferPlan(paintController)`(~1322) `notifyMapContext(info={})`(~1238, 로드 오케스트레이션) `notifyLegendChanged`(~1304) `notifyPaintCounts(counts)`(~1313, **`textContent`만 패치** — 대형 그리드 페인팅 성능).
- **키 조립 유일 지점**: `doeRowKey(value, seq)`(~193) = `` `${table}|${mapKey}|${value}|${seq}` `` · `doeSourceRowKey(value, seq, lot, slot)`(~196) = 거기에 `|${lot}|${slot||''}`. 테이블 상수 `map_doe`/`map_doe_source`(~40/41), 초안 저장 `DRAFT_PREFIX`/`DRAFT_VERSION=5`(~36/37).
- **밴드(STACK)**: `band_seq`가 정수 **정체**, `stack_band`는 **자유 텍스트 라벨**(다중 구간 `1, 2-15, 16` — 파싱하지 않는다). `blankBand`(~202) `getBands`(~205) `nextBandSeq`(~212, `max+1` — **삭제 시 재번호 금지**: 재번호는 자식 `map_doe_source`를 전부 고아로 만든다) `addBand`(~216) `getBand`(~223).
- 서버 왕복: **`putUpdates(table, updates, replaceMap)`(~944 — 3번째 인자가 `replace_map`)** `scheduleServerSave`(~968, 디바운스) **`saveDoeToServer`(~975)** **`loadDoeFromServer`(~1124 — 조회만 한다. 권한을 세우지 않는다)** **`adoptServerDoe(r)`(~1207)**.
  - **DOE 저장 1회 = 계획의 완전한 집합 1회 쓰기**라서 `replace_map: true`로 나간다(~1067/1068). 스코프는 `updates[0]`이 정하므로 **빈 집합은 서버가 실행할 수 있는 쓰기가 아니다** — 그건 "표현하지 못한 삭제"이며 완료된 저장으로 보고하면 안 된다. `cannotExpress`(~1063) 판정이 그것이고, 결과는 `S.deleteUnsent`(~1079)로 남아 헤더에 표면화된다(~438). 도달 경로: 모든 밴드의 마지막 자재를 지우면 `srcUpdates`가 빈다.
  - **[C1 불변식] `doeServerLoaded === true` ⇒ `S.doe`는 서버본에서 유래했다.** replace 권한이 생기는 **유일한 지점이 `adoptServerDoe`**이며 서버본 채택과 **원자적으로** 일어난다. 호출 지점은 둘뿐 — 저장 회복(~1002)과 맵 컨텍스트 로드(~1281, seq 가드 통과 후).
  - 회복 사이클은 **쓰기 0건**으로 끝나고 로컬 초안을 보존한다(삭제뿐 아니라 **쓰기도 보류** — 로드 실패 후 편집하면 `band_seq`가 1부터 다시 매겨져 서버 행을 덮어썼다).
  - 절단 응답(`data.total > rows.length`)은 **로드 실패로 강등**한다(~1145/1172) — "안다"고 주장하지 않는다. ⚠️ **[QA C3 미해소] 조회 `limit=500`(~1130)이 `map_doe`·`map_doe_source` 양쪽에 걸려 있어, 자재 행이 500을 넘는 계획은 매번 절단 → 매번 로드 실패 → 저장이 영구 보류된다**(20값 × 3구간 × 10자재 = 600행이면 도달). 회복 수단은 경고 토스트뿐. 서버 캡 `MAX_DOE_PER_PLAN=500`과의 정합·페이지네이션이 필요하다.
  - `loadSeq` 가드(~984/987, ~1014/1079, ~1248/1268/1292): 맵 전환 중 늦게 도착한 응답을 채택하지 않는다.
- 소스 요약: `getSourceSummary(lot, slot, force)`(~327, GET `/api/transfer-plan/source-summary`) `availabilityOf`(~364, 구 `summaryStatusOf` **없음**) `availableOf`(~391) `probeMaterialMap`(~413) `refreshMaterials`(~876) `rewardAfterReturn`(~846).
- 렌더: `renderPlanHead`(~424) `renderDoeList`(~465) `doeLine2`(~501) `renderBand`(~516) `renderDoeDetail`(~545) `bindDoeList`(~577) `materialRollup`(~703) `renderMaterialPane`(~727) `renderAll`(~1217) `buildWorkspace`(~1223).
- 이동 허브: `openMaterial(lot, slot)`(~822) — **맵 간 이동의 유일 지점**(브레드크럼·뒤로가기 프레임 스택).
- 자재 수량 분배는 **`Math.ceil`**(서버 규약 일치 — `round`면 100/3매가 33×3=99로 부족이 숨는다). `bandShare`(~247).
- ⚠️ **`__held_*` 함수군(~1344–1425)은 명시적 보류 구역** — 호출자 없음. 검증/경고 UI는 사용자 지시로 미구현이다.

### `admin.js` (~2,624줄) — 어드민 페이지 (2026-07-25 전면 재작성 — 파이프라인 5탭, export 없음)
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
| `tokens.css` (~290) | 디자인 토큰(색·타이포·간격) — 듀얼 테마 CSS 변수의 SSOT. 2026-07-25 다크 세트 심화(Ground L* 9.2, WCAG AA 유지) |
| `style.css` (~1,844) | index 페이지 스타일 본체(맵 에디터와 공유). app-header는 `position:relative; z-index:200` — split-resizer(z:100) 위 스태킹 보장(드롭다운 가림 수정) |
| `transfer_plan.css` (~793) | [M2-v2] 전사 계획 사이드바 스타일 — tokens.css 시맨틱 토큰만 사용(듀얼 테마 자동 대응). 구 `bonding_plan.css`를 대체(그 파일은 삭제됨) |
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
   - **[7d931dc] 오버레이(맵 인프라 — 계획 전용 아님) — 변환은 클라 단일 구현**: `handleAddOverlayClick`/`addOverlayForSource` → `addOverlayLayer` → ① GET `/tables/{src}/schema`(`deriveMapBinding`) → ②③ GET `/tables/{src}/data`(**원본 좌표**) + `wafer_map_metadata` 소스/타깃 2건 병렬 → ④ `frameFromMeta`로 프레임 확정(부재 시 현재 화면 = identity 폴백) → ⑤ `cols×rows` 관문 → ⑥ `projectCellsToPhys`(소스 프레임 → 물리 키) → 캔버스 마커. 화면 규격이 바뀌면 `syncOverlayGeometry`가 `rawCells`에서 재투영. `importOverlayToGrid`만 `gridData`로 넘어온다(서버 쓰기 없음).
     - ⚠️ **구 선행 단계였던 GET `/api/maps/overlay?…&limit=1`(보정 **선언** 관문 `probeAlignDeclaration`)은 삭제됐다**(2026-07-27) — 서버 선언 레이어가 없어져 물어볼 대상이 사라졌다. 오버레이 추가 경로에서 이 엔드포인트를 호출하는 코드를 보면 그것은 되살아난 것이 아니라 **오류**다.
     - **서버 경로는 삭제되지 않았다** — `map_overlay.get_overlay`(`resolve_map_transform` + `make_frame_transform` + `_frame_phys_params`)는 엔드포인트에서 그대로 살아 있고 `test_map_overlay.py`가 계약을 지킨다. 바뀐 것은 **맵 에디터가 그 좌표를 소비하지 않는다**는 것뿐이다. 2026-07-27부터 `bonding_plan.py`·`transfer_plan.py`의 **가용량 산출이 이 서버 구현을 소비**한다(자체 사본은 삭제) — 서버 구현은 하나뿐이다.
   - **[M2-v2] 전사 계획(계획 = 그 맵 자체)**: 맵 로드 → `notifyMapContext` → `transfer_plan.js`가 `stage_of_table` 역인덱스로 stage 유도 → GET `/api/transfer-plan/{stages,source-summary}` → DOE 편집(값 페인팅) → **PUT `/tables/map_doe|map_doe_source/data/updates` with `replace_map: true`**(계획의 **완전한 집합 1회 쓰기** — 클라측 차집합 계산 없음. 구 `pruneScoped`는 `3ebd38e`에서 삭제). **replace 권한은 `adoptServerDoe` 한 지점에서만** 서버본 채택과 원자적으로 획득한다. 빈 집합은 `replace_map`이 스코프를 잡을 수 없어 **표현 못 한 삭제**로 남고 `S.deleteUnsent`로 표면화된다. 검증은 GET `/api/transfer-plan/validate?ref_table=&map_key=` → `status: ok|warnings|unverified`.
8. **그래프 자동 승격**: `apply_batch_updates`의 outbox 발화 → `run_graph_materializer_loop`(keyset 커서) → `materialize_events` → `attach_col_sources`(provenance=식별 컬럼 winner 최저 서열) → `extract_graph_items` → 노드/엣지 UPSERT + `_retarget_stale_edges` → 커서 전진. 백필은 POST `/api/graph/sync` → `execute_manual_sync` → `resync_table`.
9. **그래프 조회/추적**: index 그리드 선택 → `openTraceForSelection`(`composeIdentity` 시드) → `trace.html` `runTrace` → POST `/graph/trace`(`_expand_graph_subgraph` 공용 BFS) → 그룹+타임라인 렌더. 뷰어는 `graph.html` `explore` → GET `/graph/neighbors`. 양방향 크로스링크(`?label=&identity=`).
10. **[`8117456`] 감독 + 헬스 (프로세스 생존 ≠ 진척)**: `run_decoupled_app.main()` → `ChildSpec(…, heartbeat=)` 5종 → `Supervisor.start_all()` → `Supervisor.run()` 폴 루프 → 자식 종료 감지 시 `_register_failure`(백오프 재기동, 예산 초과 시 `FAILED` 영구 정지) → `write_status()`가 `config/supervisor_status.json` 갱신.
    - 병렬로 각 워커가 **자기 루프 안에서** `heartbeat.beat(name)` → `config/worker_heartbeats/<name>.json` 원자적 replace.
    - GET `/health` → `heartbeat.read_all()` + `process_supervisor.read_status()` + DB/outbox 프로브 → **`health.compute_health`(순수 함수)** → `{status, problems[], checks{database,workers,outbox,supervisor}}` + unhealthy면 **503**. 워커 판정은 두 신호의 조인이므로 `down`/`wedged`/`starting`/`foreign_beat`/`ok`를 구분해 이름 붙일 수 있다.
11. **[`4ba13ae`] 격리 개발환경**: `devenv.py bootstrap`(config·워크스페이스 **구조만** 복제) → `snapshot_db.py`(라이브 → QA DB, 읽기 전용 소스·1000행 청크) → `devenv.py up`이 `ASSY_DATA_ROOT=<repo>/dev_env` + QA DB URL로 프로세스 기동(API :8081, graph :8091) → 모든 모듈이 `paths.py`를 통해 격리 트리를 읽고 쓴다. 워처만은 `iso_watcher.py` 게이트를 지나며, **정적(경로)·라이브(실접속 DB 이름·포트) 단언에 하나라도 걸리면 기동을 거부**한다(exit 9). 드릴 전후 비교는 `manifest.py capture|diff`.
