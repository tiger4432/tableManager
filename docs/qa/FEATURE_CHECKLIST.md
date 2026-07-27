# ✅ FEATURE_CHECKLIST — 기능 인벤토리 + QA 수동 점검 체크리스트

> **Status:** 🟢 Living | **Last-verified:** 2026-07-27 (`0f8d35f` — 전사 계획 항목을 M2.6 1테이블·`bands` 모델로 재작성) | **Owner:** Integrity/QA (유지: doc-keeper) | **Source-of-truth:** [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md) · [CODE_MAP](../architecture/CODE_MAP.md)
>
> **유지 규율:** 새 기능이 병합·커밋되면 총괄이 doc-keeper에 위임하는 **코드맵 갱신과 같은 사이클**로 이 문서에도 해당 기능 행(§1)과 점검 항목(§2)을 추가한다. 구현 에이전트는 이 문서를 직접 수정하지 않는다.
> **사용법:** §1은 "무엇이 있는가"(기능 지도), §2는 "어떻게 확인하는가"(릴리스 전/회귀 수동 점검). 체크박스는 점검 회차마다 복사해 사용하고 이 원본은 비워 둔다.

---

## 1. 기능 인벤토리 (서브시스템별)

> 진입 경로의 페이지: 메인 그리드 `/`(index.html) · 어드민 `/admin.html` · 맵 에디터 `/map_editor.html` · 인리치먼트 `/enrichment.html` · 그래프 뷰어 `/graph.html` · 추적 리포트 `/trace.html`. 페이지 간 이동은 메인 그리드 우상단 **🧭 Menu** 드롭다운(추적은 「🕸️ 추적」 버튼/메뉴). 코드 열은 [CODE_MAP](../architecture/CODE_MAP.md)의 섹션 참조(소스 전량 읽기 금지).

### 1.1 데이터 그리드 (메인 페이지 `/`)

| 기능 | 설명 | 진입 경로 | 코드 (CODE_MAP) |
|---|---|---|---|
| 테이블 조회 | 테이블 선택 → 페이지네이션+필터+정렬 조회, 셀 객체 `{value,is_overwrite,priority_source}` 병합 표시 | 툴바 `table-select` 드롭다운 | `api.fetchData` → GET `/tables/{t}/data` → `fetch_and_merge_metadata`(§1.1/1.2) · `grid.ensureCellObject`(§7) |
| 셀 편집 | 셀 더블클릭 → 값 입력 → Enter. source=user(priority 0)로 저장되어 자동값을 이김 | 그리드 셀 직접 편집 | `api.handleCellEdit` → PUT `/tables/{t}/data/updates` → `crud.apply_batch_updates`(§2) |
| 범위 일괄 적용 | 드래그로 범위 선택 후 값 1개를 범위 전체에 적용 | 범위 드래그 선택 → 셀 편집 시작(더블클릭/타이핑) → **Ctrl+Enter** 로 편집값을 범위 전체에 적용(시스템 컬럼 제외, Tx 모드면 스테이징) | `ui.applyValueToSelectedRange`(§7) · `grid.js` defaultColDef.suppressKeyboardEvent |
| 셀 소스 레이어링 조회 | 한 셀에 겹친 소스(파일명·user·collision_merge 등) 목록 확인 | 셀(또는 드래그 범위) **우클릭** → 컨텍스트 메뉴 "📚 데이터 원천(Sources) 관리" — 단일 셀은 소스별 값/타임스탬프, 범위는 배치 모드(소스별 통합 뷰) | `main.openSourcesModal/refreshSourcesList`(§7) · GET `/tables/{t}/{r}/{c}/sources`(§1.3) |
| 수동 우선순위 핀(Pin) | 특정 소스를 표시값으로 강제 고정(우선순위 무시) | 소스 모달의 소스 행별 "📍 Pin" 버튼 — 클릭 시 핀("📌 Pinned" 표시), 핀 상태에서 재클릭 시 해제(토글). 범위 선택이면 선택 셀 전체 일괄 핀 | PUT `.../priority`(단일/배치) → `crud.set_cell_manual_priority_batch`(§1.3/§2) |
| 소스 삭제 | 셀에서 특정 소스 레이어 제거 → 표시값이 차순위 소스로 재계산 | 소스 모달의 소스 행별 "🗑️ Delete" 버튼 → `confirm()` 확인창 → 삭제. 범위 선택이면 같은 버튼이 선택 셀 전체 배치 삭제 | DELETE `.../sources/{s}` · POST `.../sources/delete/batch` → `crud.delete_cell_source_batch` → `compute_priority_value`(§1.3/§2) |
| 행 추가/삭제 | 빈 행 N개 생성 / 선택 행 일괄 삭제(감사 로그 포함) | 툴바 `add-row-btn` / `delete-row-btn` | `api.addRows`/`deleteSelectedRows` → POST `rows`·`rows/batch_delete`(§1.2) |
| 엑셀형 클립보드 | 드래그 범위 선택 → Ctrl+C(TSV 복사)/Ctrl+V(붙여넣기). 헤더 포함 복사 토글 | 그리드 드래그 + Ctrl+C/V, 설정 메뉴 `copy-header-toggle` | `clipboard.setupClipboardHandlers/getRangeSelectedTSV`(§7) |
| 스마트 페이스트(인제션 경유) | 클립보드 내용을 임시 파일(`web_smart_paste_*.{txt,html,csv,json,rtf}`)로 만들어 파일 인제션 경로로 업로드(파서 처리). 행 수 임계 없음 — 자동 발동 아닌 수동 실행 | 그리드 **우클릭** → 컨텍스트 메뉴 "📋 파서로 붙여넣기 (Smart Paste)". 클립보드에 텍스트 계열 포맷이 2개 이상이면 유형 선택 모달(Plain Text/HTML Table/RTF/CSV/JSON — 전송할 클립보드 포맷 선택), 1개면 즉시 진행 | `main.smartPasteViaIngestion/showClipboardTypeModal`(§7) · POST `/tables/{t}/upload` |
| 파일 업로드 | 브라우저에서 파일 선택 → 해당 테이블 워크스페이스로 투입(이후 인제션 파이프라인) | 툴바 파일 업로드(`toolbar-file-input`) | POST `/tables/{t}/upload`(§1.2) |
| 컬럼 선택(표시 토글) | 표시할 컬럼 선택/전체/해제. 선택 상태는 AG-Grid 인메모리 컬럼 상태에만 유지(localStorage 미저장) — **새로고침 시 전체 표시로 초기화**, 테이블 전환 시 컬럼 정의 재구축으로 유지 비보장 | 툴바 `column-selector-btn` → 드롭다운 체크리스트(`col-select-all/none-btn`) | `main.setupEventListeners`(§7) — `gridApi.setColumnsVisible` |
| 페이징/뷰 모드 | 페이지 이동(이전/다음/번호 입력), 뷰 모드 전환, 전체 로드, CSV export. 뷰 모드 2종: `📄 Paging`(pagination — 하단 페이지 컨트롤 표시) / `♾️ Scroll`(infinite — 페이지 컨트롤 숨김, 스크롤 하단 도달 시 다음 청크 자동 로드) | 하단 `prev/next-page-btn`·`page-input`·`view-mode-select`·`load-all-btn`·`load-csv-btn` | `state.currentSkip/pageCache`·`grid.updateViewModeUI`(§7) · GET `/tables/{t}/export`(§1.2) |
| 컬럼 필터/정렬 | 컬럼 헤더 아래 플로팅 필터(텍스트/숫자 타입별), 헤더 클릭 정렬, 최신순 토글 | AG-Grid 헤더 필터 행, 설정 메뉴 `sort-latest-toggle` | `grid.buildColumnDefs`(floatingFilter) · `main.get_column_filter_condition`(서버, §1.1) |
| 트랜잭션 모드 | 편집을 로컬 스테이징 후 일괄 커밋/롤백 | 설정 메뉴 `tx-mode-toggle` → `tx-apply-btn`/`tx-discard-btn` | `main.applyPendingTxEdits/discardPendingTxEdits` · `ui.updateTxModeUI/setTransactionFilter`(§7) |
| 그래프 수동 동기화 | 현재 데이터를 그래프 워커로 수동 동기화 트리거 | 툴바 `graph-sync-btn` | POST `/api/graph/sync` → graph_sync_worker(§1.4/§6) |

### 1.2 변경 이력 (타임라인)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 글로벌 타임라인 | 최근 트랜잭션 그룹 이력 + 상세 펼침 | 메인 우측 History 패널 `tab-global` | `timeline.loadHistory` → GET `/audit_logs/recent`·`/transaction/{tx}`(§1.3/§7) |
| 셀/행 타임라인 | 선택 셀·행의 변경 계보 | 셀 선택 후 `tab-cell` / `tab-row` | GET `/tables/{t}/rows/{r}/history`·`.../cells/{c}/history`(§1.3) |
| 로그→셀 점프 | 이력 항목 클릭 시 해당 셀로 그리드 내비게이션(페이지 이동 포함) | 타임라인 항목 클릭 | `timeline.navigateToLog` + navigator 단계 함수(§7) |
| DELETE/CREATE 이력 영속 | 행 생성·삭제·소스 삭제·핀 변경도 DB AuditLog에 영속(재시작 후 보존, 이슈 #6 수정) | (내부) | `crud.bulk_insert_audit_logs` 적재 경로(§2) |

### 1.3 파일 인제션 파이프라인

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 커스텀 파서 인제션 | `raws/` 드롭 → `scripts/*.py`의 `match()` 매칭 파서로 파싱·적재 → `archives/` 이동 | `server/ingestion_workspace/<table>/raws/`에 파일 드롭(또는 웹 업로드) | `IngestionHandler.process_with_retry/_discover_and_execute_pipeline`(§3) · [INGESTION_GUIDE](../guide/INGESTION_GUIDE.md) |
| 표준(std) 파서 폴백 | 무스크립트 CSV/TSV/TXT — 헤더가 `display_columns`와 일치하면 스트리밍 적재. 키 결측 행은 스킵+카운트 | 커스텀 파서 무매칭 시 자동 | `std_parser.parse_std_file` · `_resolve_rows/_try_std_parse`(§3/§5) · [INGESTION_GUIDE §1.5](../guide/INGESTION_GUIDE.md) |
| err 격리 + 실패 로그 | 처리 불가 파일은 `err/`로 이동 + `FileIngestionLog` FAILED 기록 | (자동) 어드민 File 탭에서 확인 | `_move_to_err_folder/_log_ingestion_failure`(§3) · [FAILURE_MANAGEMENT_SPEC](../spec/FAILURE_MANAGEMENT_SPEC.md) |
| 실패 재시도(재처리) | 아카이브/실패 파일을 어드민에서 동기 재실행 | 어드민 File 탭 재시도 버튼 | POST `/admin/file-ingestion/retry-failed` → `process_archived_file_sync`(§1.4/§3) |
| 워크스페이스 자동 생성 | `table_config.json` 등록만으로 폴더 스캐폴딩 + 런타임 감시 등록(SYSTEM_RELOAD). 신규 워크스페이스에 config.json은 **더 이상 생성하지 않음**(2026-07-25 폐지) | config 등록 → 자동 | `WorkspaceWatcher._provision_workspaces/sync_new_workspaces`(§3) · [INGESTION_GUIDE §1.6](../guide/INGESTION_GUIDE.md) |
| 워크스페이스 별칭·std_parse 글로벌화 | 폴더명≠테이블명 매핑은 `table_config.json` 테이블 항목의 `workspace_name` 별칭으로, std 파서 옵트아웃은 같은 항목의 `std_parse: false`로 선언(**핫리로드 — 파일 단위 스냅샷 반영**). 무효 별칭(섀도잉·중복·경로 탈출)은 무시+ERROR 1회. 레거시 워크스페이스 `config.json`은 하위호환 읽기+deprecation 경고, 충돌 시 글로벌 승리 | config 등록만 (워크스페이스 config.json 폐지) | `find_workspace_alias/resolve_workspace_root/_snapshot_table_context`(§3) · [INGESTION_GUIDE §1.5](../guide/INGESTION_GUIDE.md) |
| 인제션 진행 토스트 | 파싱·적재 진행률/완료가 그리드 화면에 실시간 표시 | (자동) 메인 페이지 | `utils.showIngestionProgress` · WS `file_ingestion_progress/completed`(§7) |
| 기동/주기 스윕 (이벤트 유실 안전망) | 기동 시·신규 워크스페이스 등록 시 `raws/` 직속 기존 파일을 mtime 순으로 자동 처리 + 300s 주기 잔류 재스캔. (mtime,size) 시그니처로 잔류 파일 무한 재시도 차단, 이벤트 경로와 동일 처리(`_handle_event` 재사용, 락으로 이중 진입 가드) | (자동) 서버 기동만 | `WorkspaceWatcher.sweep_existing_files(_async)/_periodic_sweep_loop`(§3) |
| 대형 파일 heavy 레인 (P1, 2026-07-26) | 크기 임계(기본 10MB, `config/ingestion_settings.json` `heavy_file_mb` — 파일 경계 핫리로드) 초과 파일을 전용 큐/워커(`watcher-heavy-lane` 1개)로 격리 — 대형 파일이 **타 테이블 파일을 막지 않음**(드릴 실측 180배 개선). 같은 워크스페이스 후속 파일은 크기 무관 큐 후미(FIFO 보존), 스윕 경로도 자동 라우팅. heavy끼리는 직렬(알려진 제약) | (자동) 임계 초과 파일 드롭 | `HeavyIngestionLane/_route_and_process/get_workspace_serial_lock`(§3) · [INGESTION_GUIDE §1.7](../guide/INGESTION_GUIDE.md) |
| 오프셋 체크포인트 재개 (P2, 2026-07-26) | 재기동/중단 후 **중단 지점부터** 이어서 적재(종전에는 0행부터 전량 재처리). 오프셋 갱신이 청크 upsert와 **같은 트랜잭션**이라 "커밋된 행 수 == 기록된 오프셋" 성립. 재개는 시그니처+`total_rows`+`source_kind`+오프셋 범위가 전부 일치할 때만 하고, 불일치는 0부터 + **사유를 로그·`FileIngestionLog.detail`·완료 통지에 명시**(조용한 재처리 금지). heavy/normal·스윕·관리자 재시도 4경로 동일. ⚠️ **라이브 드릴 미실행(재기동 대기)** | (자동) 대형 파일 처리 중 서버 중단 후 재기동 | `server/ingestion_checkpoint.py`(§5) · `_plan_checkpoint/_send_to_upsert`(§3) · [INGESTION_GUIDE §1.8](../guide/INGESTION_GUIDE.md) |
| 파일 해시 dedup (P2, 2026-07-26) | 파일 전체 sha256(`sha256:<size>:<digest>`, 500MB 0.535s 실측)로 **동일 내용 재투입을 skip** — archives 이동 + `FileIngestionLog(SKIPPED, 사유)`. ⚠️ **WS 통지의 `status`는 `SUCCESS`**(수신부가 비-SUCCESS를 일괄 실패로 렌더링하므로 오표기 방지), 사유는 `detail`. 강제 재처리 3경로: 파일명 `__force__` / `dedup_by_signature:false` / 관리자 재시도. ⚠️ **라이브 드릴 미실행** | (자동) 같은 파일 재투입 | `ingestion_checkpoint.compute_file_signature` · `_try_dedup_skip`(§3) · [INGESTION_GUIDE §1.8](../guide/INGESTION_GUIDE.md) |
| 진행 중 인제션 가시화 + 재기동 경고 (P1) | watcher가 상태(QUEUED/PROCESSING/FINISHED)를 push → 웹서버 인메모리 레지스트리 → `GET /admin/file-ingestion/active`. admin File 탭 진행 섹션(HEAVY/normal 배지·진행률 바·경과, 5s 경량 갱신) + 재기동 경고 배너("재기동 시 처음부터 재처리") + 헬스 스트립/Overview warn. WS 계약 무변경 | 어드민 File 탭 (진행 중일 때 자동 표시) | `ingestion_activity.py`(§5) · `admin.renderActiveIngestions`(§7) · `/internal/events/ingestion-state`(§1.4) |

### 1.4 Auto-Update 스케줄러

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 주석 기반 크론 수집 | `auto_update/*.py` 상단 `# schedule:` 주석대로 주기 실행 → `out` 변수(또는 stdout)를 CSV로 `raws/` 드롭 | 스크립트 배치(무설정) | `run_auto_update.py`(§6) · [AUTO_UPDATE_GUIDE](../guide/AUTO_UPDATE_GUIDE.md) |
| 핫 리로드 | 스크립트/스케줄 주석 수정 시 재기동 없이 다음 실행에 반영(mtime 폴링) | 파일 저장만 | 동상 |
| 즉시 실행/상태 | 어드민에서 스크립트 상태 확인·즉시 실행. **즉시 실행은 active 여부 무관**(수동 실행은 명시적 의도) | 어드민 AutoUpdate 탭 | GET `/admin/auto-update/status` · POST `.../run-now`(§1.4) |
| 수집기 Active 토글 | 수집기별 스케줄 활성/비활성 스위치 — 제어 파일(`config/auto_update_control.json`, 원자적 쓰기·fail-open)에 영속, 스케줄러가 매 틱 읽어 비활성은 SKIPPED 스킵+next_run 전진(**핫 반영, 재기동 불필요**·재활성화 시 백로그 폭주 없음). 비활성 행은 dim 표시, Overview 카드·헬스 스트립에 active/total | 어드민 AutoUpdate 탭 행별 Active 스위치 | `admin.toggleCollectorActive`(§7) · POST `/admin/auto-update/toggle`(§1.4) · `utils/auto_update_control.py`(§6) |

### 1.5 체인 인제션 (파생 데이터)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 규칙 기반 파생 | 원본 테이블 변경(outbox NOTIFY) → `chain_rules.json` 매칭 맵퍼 실행 → 파생 테이블 업서트 → WS 위임 | (자동) 원본 테이블 인제션/편집 | `chain_ingestion_worker.process_chain_transaction_group`(§4) · [chain_ingestion_guide](../guide/chain_ingestion_guide.md) |
| 지연 SLO 100ms | 원본 커밋 → 파생 반영·통지까지 100ms 목표(정상 실측 31ms). `[Latency]`/`[Warmup]` 상시 계측 | (자동) 워커 로그 | `_dispatch_broadcasts/warmup_worker`(§4) · 이슈 #0 종결 기록 |
| 순환 차단 | source=chain_ingestion 이벤트는 재트리거하지 않음(무한 체인 방지) | (내부 불변식) | `process_chain_transaction_group`(§4) |
| 실패 그룹 격리 | 실패 tx 그룹은 skip하고 후속 그룹 진행(HOL 블로킹 제거), 미전달 통지는 스윕 안전망 | (자동) | `process_pending_groups/sweep_undelivered_broadcasts`(§4) |

### 1.6 Enrichment Queue (결손 보정 워크리스트)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| dedup 파생(워크리스트 소스) | 대량 원본 → 판단키당 1행 파생 테이블 투영(체인 룰 자동 파생, 멱등 count 집계) | (자동) 원본 인제션 시 | `enrichment_mapper.map_enrichment_dedup` · `enrichment_config.load_enrichment_chain_rules`(§5) · [ENRICHMENT_QUEUE_SPEC](../spec/ENRICHMENT_QUEUE_SPEC.md) |
| 컨베이어 입력 | 결손(blank) 판단키만 순차 제시 → target 입력 → Enter 저장 → 자동 다음 항목 | `/enrichment.html` — `rule-select`로 규칙 선택 → 입력칸(`target-input-block`)·`save-btn` | `enrichment.fetchWorklist/onInputKeydown/saveCurrent`(§7) |
| 참조뷰 탭 | 선택 항목의 판단키로 서버측 SQL 참조뷰 조회(탭별, LIMIT 강제, stale 가드) | 컨베이어 우측 참조 패널 탭 | `enrichment.initReferencePanel/loadActiveReference` · GET `/enrichment/rules/{r}/references/{i}`(§1.4/§5/§7) |
| 결손 배지 | 메인 그리드에 "🧩 결손 N건" 배지 → 클릭 시 해당 규칙 컨베이어로 진입. 표시 조건: 현재 테이블이 규칙의 **source_table 또는 derived_table 어느 쪽과 일치해도** 표시(원본 테이블 화면 포함), target_fields blank 카운트 > 0일 때만. 규칙 API 부재/카운트 0/조회 실패 시 무음 숨김(TTL 캐시 + WS 디바운스 갱신) | 메인 툴바 `enrichment-badge` | `ui.updateEnrichmentBadge/notifyEnrichmentTableEvent`(§7) |
| 레이어링 보존 | 사람이 채운 값은 source=user(priority 0) — 재인제션·dedup 재실행이 덮지 못함 | (불변식) | `compute_priority_value`(§2) · 스펙 §6 |

### 1.7 웨이퍼 맵 에디터 (`/map_editor.html`)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 맵 로드/저장 | 테이블 데이터 → 캔버스 맵(REST pull), 편집 후 저장(REST push, 배치 업서트). **WS 미사용** | 로드: 좌측 패널 "📂 Load Existing Map" → 로드 방식 선택 모달(📐 Standard / ⚙️ Use Current Left Panel Settings / ❌ Cancel). 저장: 작업영역 툴바 "⚡ Push Map Data" → 메타데이터 필드 미입력 시 `alert` 차단, 이후 `confirm("총 N건의 활성 맵 데이터를 '{table}' 테이블에 덮어쓰기 적재(Clean Replace)하시겠습니까?")` 확인 후 전송 | `loadExistingMap/pushMapData`(§7) · [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) |
| 지오메트리 프리셋 | 웨이퍼 지오메트리 프리셋 저장/불러오기/삭제 | 프리셋 UI | `/map-presets` CRUD · `fetchAndRenderPresets/saveCustomPreset`(§1.4/§7) |
| 브러시 페인팅/레전드 | 셀 값 브러시 페인팅, 레전드 편집(localStorage `map_legend_{table}` 유지) | 레전드 테이블·브러시 선택 | `selectBrush/renderLegendTable/load·saveLegendToStorage`(§7) |
| 좌표 변환(회전/면반전) | FRONT/BACK 전환·회전 시 물리 좌표 불변(칩 스탬프, 워터마크 표시) | FRONT/BACK 툴바 칩·회전 컨트롤 | `getPhysicalCoords` 계열(§7) · [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) 불변식 |
| 엣지 자동 페인팅 | 엣지 셀 분류·선택·E1/E2 자동 페인팅 | 작업영역 툴바 "🔍 Select Tools" 드롭다운 → "✔️ Select E1" / "✔️ Select E2" / "⚡ Auto-Paint E1/E2" (같은 드롭다운에 "📍 Set Origin (0,0)") | `getEdgeClassification/selectEdgeCells/autoPaintE1E2`(§7) |
| 엑셀 복사 | 그리드를 TSV로 클립보드 복사 | 작업영역 툴바 "🛠️ Edit Grid" 드롭다운 → "📋 Copy to Excel" | `copyGridToExcel`(§7) |
| 테이블 간 맵 이월 | 테이블 A→B 전환 시 유지/초기화 확인창(컬럼명 상이 시 Advanced Column Mapping 수동 확인 필요 — 이슈 #2) | 테이블 전환 시 자동 확인창 | history `a41007e` |
| 페인트 잠금 (M2, 2026-07-26) | 특정 값(기본 `F`)의 셀을 편집 불가로 잠금. **선언 정본이 서버**(`config/map_overlay_config.json`의 `paint_lock`)로 이동 — 종전 클라 하드코딩 `'F'` 대체. **조용한 fail-open 제거**: 404/405만 "선언 없음"(해제), 네트워크·5xx는 직전 잠금 유지 + `⚠ 잠금 규칙 미확인` 툴바 칩 + 경고 토스트. 모든 편집 경로가 `isProtectedFCell` 단일 관문 통과. ⚠️ **콜드 스타트(페이지 로드 후 첫 조회 실패)는 아직 잠금 없이 시작**(QA C4 미해소 — 칩은 뜨나 잠기지는 않음) | (자동) 맵 로드 시 규칙 조회 · 툴바 잠금 칩 | `fetchPaintRules/isProtectedFCell`(§7) · GET `/api/maps/paint-rules`(§1.2) · `map_overlay.get_paint_rules`(§5) |
| **범용 맵 오버레이** (M2 → `7d931dc` 클라 일원화, 2026-07-26) | 임의의 맵을 임의의 맵 위에 겹쳐 본다(계획 전용 아님, **맵 인프라**). **좌표 변환은 클라 단일 구현** — 소스 원본 좌표를 소스 자신의 `wafer_map_metadata` 프레임으로 해석해 물리 키로 투영하므로, 사용자가 화면 규격(회전·면·치수·물리값)을 바꾸면 **메인 맵과 오버레이가 함께 움직인다**. 셀 상한 2,000(메인 로드와 동일, 초과 시 `truncated`). 레이어별 색점 마커·표시 토글·정렬 상태 칩(`align.origin` 기준 — `무보정`/`정렬됨 N°`). 명명된 실패 status **4종**(`meta_unavailable`/`binding_unavailable`/`align_unavailable`/`no_data`, + IO 실패는 일반 `error`) 전부 **그리지 않고 목록에 행으로 남음**(재시도 버튼 유지). *(구 `align_unconfirmed`·`align_override_declared`는 서버 선언 레이어와 함께 2026-07-27 삭제 — 물어볼 선언이 없어졌고 REST 왕복도 하나 줄었다)* `📥 가져오기`는 `gridData`로만 반영(서버 쓰기 없음, 잠금 존중, 격자 밖 제외). **메인 맵 로드와 코드 경로 완전 분리**. **기준이 바뀌면 해제**(맵 로드·테이블 전환·프레임 진입). ⚠️ 정렬은 `wafer_map_metadata` 등록 맵에서만 실제로 일한다(§5.0 — 미등록은 `무보정` 폴백) | 맵 에디터 오버레이 블록 `＋ 겹치기` | `addOverlayLayer/projectCellsToPhys/syncOverlayGeometry/importOverlayToGrid`(§7) · GET `/api/maps/overlay`(§1.2 — **맵 에디터 클라는 이 엔드포인트를 호출하지 않는다**. 선언 probe가 사라지면서 마지막 호출처가 없어졌고, 서버 경로는 `bonding_plan`/`transfer_plan` 가용량 산출이 쓴다) · `server/map_overlay.py`(§5) · [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md) |
| **전사 계획 사이드바** (M2-v2, 2026-07-26) | **「계획 = 지금 열어 편집 중인 그 맵」** — `bonding_map`을 열면 본딩 계획, `dt_map`을 열면 DT 계획. stage는 열린 테이블에서 유도(선택 UI 없음), `plan_id`·계획 맵 사본 없음. legend = **DOE 아코디언**(값 = 조건군 = `map_split_registry` 행 하나). **[M2.6 2026-07-27]** 구간·자재는 그 행의 **`bands` JSON** 안에 있고(`seq` 정체 · 배열 위치가 순서 · 입력값은 구간당 **끝 층 하나**), 수량은 저장하지 않고 파생한다(`칠한 셀 수 × 층 수`, 매당 `ceil`). 패널은 서버에 직접 쓰지 않고 legend 저장 경로 하나로 씁니다. 자재 목록 DOE별 그룹 + `openMaterial`이 맵 간 이동의 유일 허브(브레드크럼·뒤로가기). 자재 가용은 `가용 = 총 − (fail ∪ 기전사)`. **서버가 degraded면 `remaining`이 `null`로 오고 클라는 이를 초록으로 뒤집지 않는다.** 검증/경고 UI는 **미구현**(사용자 지시 보류 — `__held_*` 구역) | 맵 에디터 우측 사이드바(맵 로드 시 자동) | `transfer_plan.js`(§7) · GET `/api/transfer-plan/{stages,source-summary,validate}`(§1.2) · `server/transfer_plan.py`(§5) · [MAP_EDITOR_SPEC §6](../spec/MAP_EDITOR_SPEC.md) |
| 본딩 실험계획 (M1) — **UI 대체됨** | M1의 조회 전용 Info 패널(`bonding_plan.js`/`.css`)은 `8e34804`에서 **삭제**되고 위 전사 계획 사이드바로 대체됐습니다. **서버 API `GET /api/bonding-plan/core-summary`와 `server/bonding_plan.py`는 존치**하며, `transfer_plan`의 core-kind 경로가 여기에 위임합니다 | (직접 UI 없음 — 전사 계획 경유) | `server/bonding_plan.py`(§5) · GET `/api/bonding-plan/core-summary`(§1.2) |

### 1.8 어드민 대시보드 (`/admin.html`) — 파이프라인 생애주기 5탭 IA (2026-07-25 재편)

탭 축은 **파이프라인 생애주기 5탭**(`#overview/#file/#chain/#autoupdate/#enrichment`) + 코드 에디터 **공용 뷰**(`#editor=<path>` 딥링크). 구 해시 별칭(`#outbox→#chain` 등) 호환 유지.

| 탭/기능 | 설명 | 코드 |
|---|---|---|
| Overview | 파이프라인 4카드(File/Chain/AutoUpdate/Enrichment) 헬스 요약 + 최근 이벤트 + 각 탭 딥링크. 상단 파이프라인 헬스 스트립 공용 | `fetchOverview/renderOverview` · `parseRoute/applyRoute/switchTab`(§7) |
| File | 파일 인제션 로그/실패 목록·재처리 + 워크스페이스 현황 + 파서 스크립트 편집 딥링크 | `renderFileTable/retryFileIngestion/renderWorkspaceTable/selectFileRow` · `/admin/file-ingestion/*` |
| Chain | outbox 실패/대기 트랜잭션 재시도 + 체인 룰·맵퍼 목록 + 이벤트 진단(Edit Mapper 딥링크) | `renderOutboxTable/renderChainTable/renderMapperTable/showEventDiagnostics` · `/admin/outbox/*`·`/admin/chain/rules`·`/admin/mappers/list` |
| AutoUpdate | 수집기 상태·즉시 실행·**Active 토글**(§1.4) + 산출물 인제션 실패 교집합(`renderLinkedFailTable`) | `renderAutoUpdateTable/toggleCollectorActive/runAutoUpdateNow` · `/admin/auto-update/*` |
| Enrichment | 규칙별 결손 현황(15s TTL 캐시 — 스트립·탭·Overview 공용) + 컨베이어 딥링크 | `renderEnrichmentTable/fetchEnrichmentStatus` · `/enrichment/rules` |
| Code Editor(공용 뷰) | Monaco(CDN) 파일 피커 + 스크립트 편집·저장(인라인 폴백, dirty confirm) — 각 탭에서 `#editor=<path>` 딥링크 진입 | `initMonacoEditor/populateEditorPicker/selectEditorFile/saveScriptCode` · `/admin/scripts/*` |
| Config Reload | `table_config.json` 등 핫리로드(+SYSTEM_RELOAD 전파로 워커도 리로드, 신규 테이블 물리 CREATE 포함) | `reloadSystemConfigs` → POST `/admin/reload-configs`(§1.4) |

### 1.9 온톨로지 그래프 (승격·뷰어·추적)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 온톨로지 그래프 승격 | outbox 증분 소비 → `ontology_mapping.json` v2 매핑대로 PG 엣지 스토어(graph_nodes/edges) 자동 materialize(provenance 포함). 수동 트리거는 백필/복구용 | (자동) + 메인 툴바 `graph-sync-btn`(백필) | `graph_sync_worker.py`+`graph_materializer.py`(:8090) · [event_driven_backend §4](../architecture/event_driven_backend.md) · [ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md) |
| 서브그래프 뷰어 | stats 카운트 카드 + identity 자동완성 검색 + k-hop(1\|2) 이웃 탐색을 BFS 동심원 캔버스로 렌더(무라이브러리). 팬·줌, truncated 배지, user provenance 엣지 강조. **노드 클릭=선택**(Connections 테이블), **중심 이동은 더블클릭/시드 버튼**(2026-07-25 `18218da`부터 UX 변경) | `/graph.html`(🧭 Menu 또는 추적 리포트 크로스링크 `?label=&identity=`) | `graph_viewer.js`(§7) · GET `/graph/stats·neighbors·nodes/search`(§1.5) |
| 뷰어 Connections 테이블 + 검색 시드 연동 | 노드 클릭 → 우측 패널에 선택 노드 정보 + 관계 테이블(방향 →/←/⟲·엣지 type·상대 노드 요약·event_time). 비중심 노드는 서브그래프 단면 즉시 표시 후 depth-1 재조회로 전체 이웃 보강, 80행 단위 "더 보기". **행 클릭 → 해당 노드 중심 재조회 + URL `?label=&identity=` push + 검색바 반영**(뒤로가기 복원 지원). 패널 접기 토글 | 뷰어 캔버스 노드 클릭 | `selectNode/fetchNodeConnections/renderConnBlock/syncUrl`(§7 graph_viewer.js) |
| 뷰어 라벨 노드 리스트 | stats 라벨 카드 클릭 → 그 라벨의 노드 목록 테이블(identity 오름차순, 서버 페이지 200 + "더 보기", 로드수/총수 헤더) → 행 클릭 시 중심 탐색, back으로 Stats 복귀. 서버는 빈 q + label 리스팅(캡 200 — 자동완성 캡 50 불변, 전 테이블 덤프 금지) | 뷰어 첫 화면 라벨 카드 클릭 | `openLabelNodes/fetchLabelNodesPage/renderLabelNodesBlock`(§7 graph_viewer.js) · GET `/graph/nodes/search`(§1.5) |
| 객체 중심 추적 리포트 | 멀티 시드(≤20) BFS 합집합 → 라벨별 그룹 테이블 + event_time 타임라인. depth 1..3·시간 범위·타입 필터, missing seeds 분리 표시, 뷰어 양방향 크로스링크 | `/trace.html` — 메인 그리드 행 선택 → 「🕸️ 추적」 버튼(새 탭, 선택 행→identity 시드) | `trace.js`/`trace_core.js`/`trace_launch.js`(§7) · POST `/graph/trace`·GET `/graph/mapping-summary`(§1.5) |
| 추적 진입점 자동 표시 | `mapping-summary`로 현재 테이블의 매핑 활성 여부를 판정해 「🕸️ 추적」 버튼 노출/숨김 | (자동) 메인 그리드 툴바 | `trace_launch.refreshTraceEntry`(§7) |

### 1.10 듀얼 테마 / 실시간 동기화 / 데스크톱 래퍼

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 듀얼 테마(라이트/다크) | 토큰 SSOT `tokens.css` + `theme.js`. 기본 라이트, localStorage로 페이지 간 유지, AG-Grid 무재생성 재도색, FOUC 방지 스탬프 | 테마 토글 버튼(`data-theme-toggle`) — **4개 페이지(index/admin/map_editor/enrichment) 모두** 각 헤더/툴바에 존재 | `theme.js`·`tokens.css`(§7) |
| WS 실시간 반영 | 편집·인제션·체인 결과를 전 클라이언트에 델타 반영(`batch_row_create/upsert/delete`, `batch_refresh_required`) + 셀 플래시, 지수 백오프 재연결 | (자동) 메인 그리드 | `websocket.js`(§7) · `ConnectionManager`(§1.1) · [DATA_SYNC_SPEC](../spec/DATA_SYNC_SPEC.md) |
| 데스크톱 래퍼 | QtWebEngine 셸(`?client=desktop`): OS 드래그앤드롭 업로드, 네이티브 다운로드 다이얼로그, F12 DevTools, `assymanager://` URI | `python run_decoupled_app.py`(셸 포함 기동) · 배포는 GET `/api/download/client` | `client/desktop_wrapper.py` · [frontend §1](../architecture/frontend.md) |

### 1.11 운영 감시 (프로세스 감시 · 헬스 · 격리 환경) — 2026-07-27 신설

> UI가 아니라 **운영 표면**이다. 화면이 멀쩡한데 데이터가 안 들어오는 상태를 밖에서 알아채는 것이 목적.

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 자식 프로세스 감시·자동 재시작 | 런처가 5~6개 자식을 1초 주기로 감시. 죽으면 백오프 재시작(2/4/8/16/32초), **6번째 연속 실패에서 영구 `FAILED`**(배너 로그 + `/health` 503). 60초 이상 살아 있었으면 예산 회복. 데스크톱 셸 종료 = 전체 종료 | `python run_decoupled_app.py` (상태 파일 `config/supervisor_status.json`) | `server/process_supervisor.py` · [backend §1.3](../architecture/backend.md) |
| 워커 진행 박동 | 워커 4종(`watcher`/`chain`/`graph`/`scheduler`)이 **자기 작업 루프 안에서** 박동. pid가 아니라 진행이 신호라 **살아 있는 채 멈춘 워커**(`wedged`)를 잡는다. 정체 임계 60초. 상태값은 **8종**(`ok`·`starting`·`missing`·`foreign_beat`·`wedged`·`stale`·`stalled`·`down` — [backend §1.3](../architecture/backend.md)). ⚠️ **`stalled`는 별개 검출기**: 박동은 신선한데 claim한 작업이 **300초** 무진행인 경우로, 워처의 재시도 폴러가 계속 박동하는 동안 인제션이 멈춰 있던 실제 사고를 잡는다 | (자동) `config/worker_heartbeats/*.json` | `server/utils/heartbeat.py` |
| 헬스 엔드포인트 | **항상 JSON**, 정상 200 / `unhealthy` 503. `checks{database, workers, outbox, supervisor}` + 사람이 읽는 `problems[]`. DB 프로브 2초 타임아웃·중복 프로브 차단 | `GET /health` | `server/health.py` · `main.py` |
| outbox 적체 판정 | **크기가 아니라 나이**(5분 degraded / 15분 unhealthy). 정상적인 10만 행 적재가 outbox 11.6만 행을 만들기 때문에 크기 임계는 큰 파일마다 오경보한다 | 위 응답의 `checks.outbox` | `health.probe_outbox` |
| 격리 개발/검증 환경 | 스냅샷 DB(`assy_qa`) + 별도 포트(:8081/:8091) + 별도 데이터 루트(`dev_env/`). `up`은 워처·스케줄러를 **일부러 안 띄운다**. 드릴용 워처는 별도 동사이며 **운영을 향하면 기동을 거부** | `python server/scripts/dev_env/devenv.py {snapshot,up,status,env,down,watcher-up,watcher-down}` | `server/scripts/dev_env/devenv.py` · `iso_watcher.py` · `server/paths.py` · [DEPLOY_SETUP §5](../guide/DEPLOY_SETUP.md) |
| 제품 소유 테이블 설치 | 제품이 정의하는 4종을 사이트 `table_config.json`에 **바이트 스플라이스 병합**(현장 항목 무접촉, dry run 기본, 백업, 드리프트는 보고만) | `python server/scripts/install_product_tables.py [--apply]` | `server/product_tables.py` · `server/scripts/install_product_tables.py` · [CONFIG_GUIDE §5.8-ter](../guide/CONFIG_GUIDE.md) |

---

## 2. QA 수동 점검 체크리스트

> **사전 조건:** `python run_decoupled_app.py`로 전체 스택 기동(웹 :8080 + 워커 4종). 체인/인리치먼트 항목은 로컬 스모크 규칙(`line_model_owner_attribution`: `production_plan` → `line_model_registry`, gitignored config) 기준 — 환경에 규칙이 없으면 해당 항목은 N/A 처리.
> **핵심가치 직결 항목**은 🎯로 표시(실시간 SLO·멱등성·레이어링 보존 — 실패 시 릴리스 블로커).

### 2.1 데이터 그리드 — 조회/편집

- [ ] **조회 정상**: `/` 접속 → `table-select`에서 테이블 선택 → 그리드에 데이터 표시, 하단에 페이지/건수 표시.
- [ ] **편집 정상**: 셀 더블클릭 → 값 변경 → Enter → 값 반영 + 셀에 오버라이트 표시(스타일 변화) + History 패널에 이력 즉시 추가.
- [ ] **편집 에지 — 숫자 검증**: 숫자 타입 컬럼에 문자열 입력 → 거부(토스트/원복)되고 서버에 저장되지 않음.
- [ ] 🎯 **편집 에지 — 자동값 우선순위**: 파일 인제션으로 채워진 셀을 수동 편집 → 같은 파일 재드롭 → 수동 값이 유지됨(user가 parser를 이김).
- [ ] **필터/정렬**: 컬럼 플로팅 필터에 조건 입력 → 결과 축소, 헤더 클릭 → 정렬 토글. 필터+페이지 이동 조합 시 결과 일관.
- [ ] **페이징**: 다음/이전 페이지 이동, 페이지 번호 직접 입력, 마지막 페이지에서 다음 버튼 동작(비정상 점프 없음).
- [ ] **CSV export**: `load-csv-btn` → 현재 테이블 CSV 다운로드, 행 수가 화면 총계와 일치.

### 2.2 데이터 그리드 — 소스 레이어링/핀

- [ ] **소스 목록**: 여러 소스가 쌓인 셀(파일 2회 상이 값 인제션 + 수동 편집으로 준비)을 **우클릭 → "📚 데이터 원천(Sources) 관리"** → 모달에 소스별 값 표시(값에 마우스 오버 시 갱신자/시각 툴팁).
- [ ] 🎯 **소스 삭제 → 차순위 폴백**: 최우선 소스(user)의 "🗑️ Delete" → confirm 승인 → 표시값이 차순위 소스(예: pipeline_parser) 값으로 즉시 재계산되어 표시됨.
- [ ] **소스 삭제 에지 — 없는 소스**: 이미 삭제된(또는 존재하지 않는) 소스를 다시 삭제 시도 → 하단 상태 로그에 "❌ Failed to delete cell source" 표시(토스트/모달 아님 — 무음 실패는 아님), 그리드 값 불변.
- [ ] **핀 설정**: 하위 우선순위 소스의 "📍 Pin" 클릭 → 표시값이 핀 소스 값으로 전환("📌 Pinned" 활성 표시). 재클릭으로 핀 해제 → 기본 우선순위 규칙으로 복귀.
- [ ] **핀 이력**: 핀 설정/해제가 History 패널과 셀 이력에 기록됨(서버 재시작 후에도 조회됨 — 이슈 #6 회귀 확인).

### 2.3 데이터 그리드 — 행/클립보드/컬럼/Tx 모드

- [ ] **행 추가**: `add-row-btn` → 빈 행 생성 → 비즈니스 키 입력 → 저장됨. 다른 브라우저 창에도 행 추가 반영.
- [ ] **행 삭제**: 행 선택 → `delete-row-btn` → 삭제 + 글로벌 타임라인에 DELETE 이력(비즈니스 키 표시).
- [ ] **클립보드 복사**: 셀 범위 드래그 → Ctrl+C → 엑셀에 붙여넣기 시 TSV 형태 일치. `copy-header-toggle` 켜면 헤더 포함.
- [ ] **클립보드 붙여넣기**: 엑셀에서 복사한 2×2 범위를 그리드에 Ctrl+V → 해당 범위 셀 값 갱신 + 이력 기록.
- [ ] **스마트 페이스트**: 엑셀에서 표 복사 → 그리드 우클릭 → "📋 파서로 붙여넣기 (Smart Paste)" → (엑셀 복사본은 다중 포맷이므로) 유형 선택 모달에서 포맷 선택 → 업로드 성공 토스트 → 인제션 파이프라인 경유 적재·그리드 반영.
- [ ] **컬럼 선택**: `column-selector-btn` → 일부 컬럼 해제 → 그리드에서 숨김. 전체 선택/해제 버튼 동작.
- [ ] **Tx 모드**: 설정 메뉴 `tx-mode-toggle` ON → 셀 2~3개 편집(서버 미반영 스테이징 표시) → `tx-apply-btn` → 일괄 커밋(단일 트랜잭션 이력). ON 상태에서 `tx-discard-btn` → 편집 전량 원복.
- [ ] **Tx 모드 에지 — 이탈 경고**: Tx 편집 pending 상태에서 페이지 새로고침 시도 → 이탈 경고(beforeunload) 표시.

### 2.4 변경 이력

- [ ] **글로벌 타임라인**: 편집 직후 History 패널 `tab-global`에 트랜잭션 그룹 표시, 펼치면 셀 단위 old→new 표시.
- [ ] **셀/행 타임라인**: 셀 선택 → `tab-cell`에 해당 셀 계보만, `tab-row`에 해당 행 변경만 표시.
- [ ] **로그→셀 점프**: 다른 페이지에 있는 행의 이력 항목 클릭 → 해당 페이지로 이동 + 대상 셀 하이라이트/스크롤.
- [ ] **이력 영속 에지**: 행 삭제 후 서버 재시작 → 글로벌 타임라인에 DELETE 이력이 여전히 조회됨.

### 2.5 파일 인제션

- [ ] **커스텀 파서 정상**: 커스텀 스크립트가 있는 워크스페이스 `raws/`에 매칭 파일 드롭 → 파싱·적재 → `archives/` 이동 + 그리드에 진행 토스트→완료.
- [ ] **std 폴백 정상**: 스크립트 없는(또는 무매칭) 테이블에 스키마 헤더와 일치하는 CSV 드롭 → 적재 성공. 미지 컬럼이 섞인 파일도 알려진 컬럼만 적재.
- [ ] **std 에지 — 키 결측 행**: 비즈니스 키가 빈 행(소계/각주)이 섞인 CSV 드롭 → 해당 행만 스킵되고 완료 메시지에 "키 결측으로 N행 스킵" 표시. 재드롭해도 고아 행 미생성.
- [ ] **err 격리**: 헤더에 비즈니스 키 컬럼이 없는 CSV 드롭 → `err/`로 이동 + 어드민 File 탭에 FAILED 로그.
- [ ] 🎯 **멱등성 — 재드롭 무중복**: 동일 파일을 `raws/`에 2회 드롭 → 행 수 불변(비즈니스 키 업서트), 신규/변경 셀만 이력 추가. 중복 행·중복 outbox 브로드캐스트 없음.
- [ ] **실패 재시도**: err 원인(예: 스크립트 버그) 수정 후 어드민 File 탭에서 재시도 → 성공 전환 + 데이터 적재.
- [ ] **워크스페이스 자동 생성**: `table_config.json`에 테이블 추가 → `/admin/reload-configs` → 워크스페이스 폴더 자동 생성·감시 시작 + 물리 테이블 즉시 CREATE(이슈 #7 해소 — 재기동 없이 조회 정상).
- [ ] **기동 스윕**: 서버 정지 상태에서 `raws/`에 파일을 미리 넣고 기동 → 기동 직후 자동 처리·아카이브(이벤트 없이도 적재). 신규 워크스페이스 런타임 등록 시에도 기존 파일 스윕.
- [ ] **워크스페이스 별칭**: 테이블 항목에 `workspace_name` 별칭 지정 + 리로드 → 별칭 폴더로 워크스페이스 생성·감시, 그 폴더 드롭이 해당 테이블로 적재. 어드민 File 탭 워크스페이스 현황에 테이블명 정상 표시. 실패 재시도(retry-failed)도 별칭 워크스페이스를 정확히 역조회.
- [ ] **별칭 에지 — 섀도잉 무효**: 별칭을 다른 실존 테이블명과 동일하게(또는 두 테이블이 같은 별칭을) 선언 → 별칭 무시 + ERROR 로그 1회(로그 홍수 없음), 폴더명 규약으로 동작.
- [ ] **std_parse 옵트아웃 핫리로드**: 테이블 항목에 `"std_parse": false` 추가 + 리로드 → **재기동 없이** 다음 파일부터 std 폴백 비활성(무매칭 파일은 err/ 격리). 처리 도중이던 파일은 시작 시점 config로 완결. 문자열 `"false"` 등 비-bool 값은 무시 + 경고 1회.
- [ ] **레거시 config.json 하위호환 에지**: 워크스페이스 `config/config.json`이 있는 기존 워크스페이스 → 계속 동작하되 기동 로그에 deprecation WARNING **1회**(sensor_config.json 등 다른 파일에는 미발화). 글로벌 `table_config.json`과 충돌 시 글로벌 값 승리. 신규 자동 생성 워크스페이스에는 config.json이 생성되지 않음.
- [ ] **스윕 에지 — 잔류 파일 무한 재시도 없음**: 처리 불가 파일이 `raws/`에 남아도 300s 주기 스윕이 동일 (mtime,size) 파일을 반복 재시도하지 않음(워커 로그 확인). 파일 수정(mtime 변경) 시에는 재처리됨.
- [ ] 🎯 **heavy 레인 — 교차 비차단**: 임계 초과 대형 CSV(>10MB) 투입 → watcher 로그 `🐘 Routed to heavy lane queue (size, ...)` → heavy 진행 중 **다른 테이블** 소형 CSV 투입 → 수 초 내 완료(분 단위 대기 없음 — 드릴 기준 ~2.3s).
- [ ] 🎯 **heavy 레인 — 같은 테이블 순서 보존**: heavy 진행 중 **같은 테이블**에 소형 파일 투입 → `(workspace-order)` 재라우팅 로그 → heavy 완료 후 처리(추월 없음), 최종 행 수·bk 중복 0 확인.
- [ ] **heavy 진행 가시화**: heavy 진행 중 admin File 탭 → 진행 중 섹션에 HEAVY 배지(재라우팅 소형은 normal 배지)·진행률 바·행 카운트 표시 + 재기동 경고 배너 + 헬스 스트립 File 카드 warn. 완료 시 목록 자동 소거·경고 소멸.
- [ ] **heavy 임계 핫리로드**: `config/ingestion_settings.json`의 `heavy_file_mb` 변경 → 재기동 없이 **다음 파일부터** 반영. 무효값(문자열/0 이하)은 기본 10MB + 경고 1회.
- [ ] **heavy 스윕 라우팅**: watcher 정지 → raws/에 대형+소형 배치 → 기동 → 스윕이 대형만 heavy로 보내고 소형·타 테이블이 선완료.
- [ ] 🎯 **[P2] 체크포인트 재개**(재기동 후 최초 드릴): 대형 파일 처리 도중 watcher 강제 종료 → 재기동 → 로그에 `[resume]`과 재개 오프셋 → **처음부터가 아니라 이어서** 적재되고 최종 행 수·bk 중복 0. `file_ingestion_checkpoints`의 `processed_rows`가 실제 커밋 행 수와 일치.
- [ ] **[P2] 재개 거부 표면화**: 같은 파일명으로 **내용이 다른** 파일 투입(시그니처·total_rows 불일치) → 0부터 재처리 + 로그·`FileIngestionLog.detail`·완료 통지에 `[resume-abort] … 사유:` 명시(조용히 재처리되면 실패).
- [ ] 🎯 **[P2] 해시 dedup**: 이미 적재 완료한 파일을 그대로 재투입 → skip + archives 이동 + `FileIngestionLog(SKIPPED)` + 사유 detail. **클라 알림이 "실패"로 보이지 않는지** 확인(통지 status는 SUCCESS).
- [ ] **[P2] 강제 재처리 3경로**: ① 파일명에 `__force__` 포함 ② `ingestion_settings.json`의 `dedup_by_signature: false` ③ 어드민 재시도 — 셋 다 skip을 우회해 재적재.
- [ ] **[P2] 감사 총계(이슈 #10)**: 멀티 target-table 체인이 걸린 트랜잭션 유발 → 타임라인의 tx 총건수가 **마지막 메시지 값이 아니라 누적 합**으로 표시.

### 2.6 Auto-Update

- [ ] **크론 실행**: `# schedule: */5 * * * *` 스크립트 배치 → 주기 도래 시 `raws/`에 CSV 생성 → 인제션까지 연쇄 완료.
- [ ] **핫 리로드 에지**: 스크립트의 schedule 주석 변경 → 재기동 없이 다음 실행 타이밍이 변경(스케줄러 로그 확인).
- [ ] **즉시 실행**: 어드민 AutoUpdate 탭에서 run-now → 즉시 수집·드롭·적재.
- [ ] **Active 토글**: AutoUpdate 탭에서 수집기 Active 스위치 OFF → 다음 주기에 실행되지 않고 상태가 SKIPPED(next_run은 전진), 행 dim 표시 + Overview 카드 active/total 감소. **OFF 상태에서도 run-now는 실행됨**(툴팁 확인). ON 복귀 → 다음 주기 정상 실행 1회(밀린 주기 몰아 실행 없음). 재기동 없이 전 과정 핫 반영.
- [ ] **토글 에지 — 제어 파일 부재**: `config/auto_update_control.json` 삭제 후 status 조회 → 전 수집기 active(fail-open), 에러 없음.

### 2.7 체인 인제션 + 실시간 SLO

- [ ] **파생 정상**: 원본 테이블(스모크: `production_plan`)에 행 인제션/편집 → 파생 테이블(`line_model_registry`)에 규칙대로 파생 행 생성/갱신.
- [ ] 🎯 **SLO 100ms**: 원본 편집 커밋 → 파생 반영 WS 통지까지 워커 `[Latency]` 로그 기준 100ms 이내(정상 상태 기대치 ~31ms). 재기동 직후 첫 체인은 ~600ms까지 허용(웜업 잔여, 알려짐).
- [ ] 🎯 **순환 차단**: 파생 테이블 갱신이 다시 체인을 트리거하지 않음(워커 로그에 재귀 처리 없음, outbox 무한 증가 없음).
- [ ] **멱등성 — 체인 재실행**: 동일 원본 재드롭 → 파생 테이블 행 수 불변, count류 집계값 정확(중복 가산 없음).
- [ ] **실패 격리 에지**: 맵퍼 예외를 유발하는 그룹 발생 시 해당 그룹만 실패(어드민 Chain 탭 outbox FAILED)하고 이후 정상 그룹은 계속 처리됨.
- [ ] **대형 tx 통지 비동결(인시던트 `cc57b64` 회귀)**: 수만 행 파일 재인제션 등 대형 tx 발생 시 :8080이 동결되지 않고(`[Latency] notify=` 정상), 히스토리 패널 트랜잭션 총계는 실건수(`total_log_count`) 표기 — 로그 항목 자체는 500건까지만 보존(부분 보존이 정상). ⚠️ 알려진 잔여: 멀티 target-table tx 총계 과소(이슈 #10, D-1).

### 2.8 Enrichment Queue

- [ ] **워크리스트 정상**: 원본 인제션(결손 target 포함) → `/enrichment.html` → 규칙 선택 → 결손 판단키만 목록에 표시(dedup — 원본 5행 → 유니크 3행 등 압축 확인).
- [ ] **컨베이어 저장**: 항목 선택 → target 입력 → Enter → 저장 + 자동으로 다음 항목 포커스. 채운 항목은 워크리스트에서 사라짐.
- [ ] **참조뷰**: 항목 선택 시 참조 탭에 판단키 기반 조회 결과 표시. 빠르게 항목을 연속 이동해도 이전 항목의 참조 결과가 뒤늦게 덮어쓰지 않음(stale 가드).
- [ ] **참조뷰 에지 — 오류 상태**: 참조뷰 파라미터 불충분/규칙 부재 시 로딩/빈/오류 상태 UI가 구분 표시(빈 화면 방치 금지).
- [ ] **결손 배지**: 메인 그리드에서 파생 테이블 선택 → "🧩 결손 N건" 배지 표시, N이 워크리스트 잔여와 일치. 클릭 → 해당 규칙 컨베이어로 진입. 규칙 API 부재 환경에서는 배지 무음 비활성.
- [ ] 🎯 **레이어링 보존**: 컨베이어로 채운 값 위에 원본 재드롭(체인 dedup 재실행) → 사람 값 유지(user > chain_ingestion).

### 2.9 맵 에디터

- [ ] **로드/편집/저장**: 페이지 진입 → 테이블 선택 → 기존 맵 로드 → 브러시로 셀 페인팅 → 저장 → 재진입 시 편집 결과 유지 + 메인 그리드에서 동일 값 확인(배치 업서트 경유).
- [ ] **회전/면반전 불변식**: 회전·FRONT/BACK 전환 후에도 특정 칩의 물리 위치 표시가 일관(스펙 불변식). FRONT/BACK 워터마크·툴바 칩 표시.
- [ ] **프리셋**: 커스텀 지오메트리 프리셋 저장 → 목록 표시 → 삭제 동작.
- [ ] **레전드 유지**: 레전드 편집 → 새로고침 후 유지(localStorage). 테이블별로 분리 저장.
- [ ] **맵 이월 에지**: 편집 중 테이블 A→B 전환 → 유지/초기화 확인창 표시. (⚠️ 컬럼명이 크게 다르면 자동 정합 안 됨 — 이슈 #2, 저장 전 수동 매핑 확인.)
- [ ] **엑셀 복사**: 맵 그리드를 엑셀로 복사 → 셀 배치 일치.
- [ ] **페인트 잠금**: 맵 로드 → 잠금 값(기본 `F`) 셀에 브러시·Fill·Auto-Paint·오버레이 가져오기 시도 → 전부 차단. `/api/maps/paint-rules`를 500으로 막고 재로드 → **잠금이 풀리지 않고** `⚠ 잠금 규칙 미확인` 칩 + 경고 토스트(fail-open 금지).
- [ ] **오버레이 — 기본 흐름**: `＋ 겹치기`로 다른 테이블/키 맵 추가 → 셀 마커 표시, 표시 토글·제거 동작, 정렬 상태 칩이 `declared`/`derived`/`identity` 중 하나로 표기. **메인 맵의 테이블·규격·legend·brush가 하나도 변하지 않는지** 확인(경로 분리 불변식).
- [ ] **오버레이 — 좌표 정확성** ⚠️: 회전 90/270 + **비등방 칩**(chip_x ≠ chip_y) + **bbox ≠ 0인 실데이터**(29×25, 27×21 등)로 확인할 것. 40×40(`minC=0`)은 결함이 원리적으로 발현하지 않는 구간이라 통과해도 아무 의미가 없다(과거 2회 이 사각지대에서 "해소" 오판정). 오라클은 앱의 변환 함수를 쓰지 말고 독립 계산으로.
- [ ] **오버레이 — 규격 변경 추종**: 오버레이가 떠 있는 상태에서 회전·면반전·start 좌표 **및 물리값(`phys_chip_*`/`phys_offset_*`)** 변경 → 마커가 메인 맵과 **같은 칸에서 함께** 이동(`syncOverlayGeometry`). ⚠️ **판정은 "오버레이가 움직였는가"가 아니라 "메인 맵과 같은 칸에 있는가"다** — invertY·START는 `(c,r)↔물리` 사상에 개입하지 않으므로 **양쪽 다 안 움직이는 것이 정답**이다(구 설계에서는 이 두 축에서 오버레이만 움직였고, 그것이 사용자가 본 어긋남의 한 갈래였다).
- [ ] **오버레이 — 실패 표면화**: 존재하지 않는 소스 맵 추가 → 목록에 **실패 행으로 남고** 사유 표시(조용히 사라지지 않음). 규격 조회를 5xx로 막아 `meta_unavailable`이 뜨고 **마커가 0개**인지 확인("확인 못 함"이지 "미등록"이 아니다 — 폴백해서 그리면 결함). *(구 `align_unconfirmed` 점검 항목은 선언 probe 삭제로 2026-07-27 폐기)*
- [ ] **오버레이 — 기준 변경 시 해제**: 오버레이를 띄운 채 ⓐ 다른 맵 로드 ⓑ **다른 테이블로 전환** ⓒ 프레임 진입 → 세 경우 모두 오버레이가 사라진다. 특히 ⓑ에서 목록이 비었는지 확인 — 남아 있으면 `가져오기`로 **이전 테이블 값이 새 테이블에 써진다**(`251dbfd`가 닫은 경로).
- [ ] **오버레이 — 캔버스 측정 함정**: 비표시(백그라운드) 창에서는 `requestAnimationFrame`이 멈춰 캔버스가 얼어붙는다. "마커 0개"를 결함으로 판정하기 전에 **탭을 앞으로 꺼내고 명시적 재렌더를 유발**할 것. `phys-*` 입력은 재렌더 예약 목록에 없어 값만 바꾸면 화면이 낡은 채로 남는다.
- [ ] **전사 계획 — 기본 흐름**: `bonding_map` 로드 → 사이드바에 stage가 **자동 유도**되어 표시(선택 UI 없음) → DOE 값 아코디언 펼침 → 구간 추가 후 **끝 층만 입력**(시작 층은 앞 구간에서 유도되어 편집 불가) → 자재 추가(lot\|slot 자동완성) → 서버 저장 후 재로드 시 유지.
- [ ] **전사 계획 — 정체 보존(M2.6)**: 구간의 **끝 층을 고쳐 순서가 바뀌어도** `seq`가 재번호되지 않고 자재가 따라온다. 구간 삭제 후 추가 → 기존 구간의 `seq` **불변**. (구 `stack_band` 자유 텍스트 라벨은 M2.6에서 폐기 — 지금 사용자가 넣는 값은 구간당 끝 층 하나뿐이다.)
- [ ] **전사 계획 — replace 권한(C1 회귀)** 🔴: `map_split_registry` **GET만** 500으로 1회 막았다가 **복구**시킨 뒤 편집 → 서버 행이 삭제·덮어쓰기되지 않아야 한다. 지속 실패만 시험하면 **회복 분기를 한 번도 실행하지 않으므로 이 항목은 검증되지 않은 것**이다. 절단 응답(`total > rows.length`)·맵 전환 중 늦은 응답도 같은 방식으로 확인.
- [ ] **전사 계획 — 동시 편집 거부(M2.6 신설)**: 두 세션에서 같은 맵을 열고 A가 저장 → B가 저장 시도 → **upsert로 강등되지 않고 거부**되며 리로드 전까지 그 맵의 쓰기가 막힌다. 강등되면 B의 낡은 `bands`가 A의 것을 덮는다.
- [ ] **전사 계획 — 읽을 수 없는 끝 층**: 끝 층 컬럼에 `0x10` 같은 값이 저장된 상태로 로드 → 화면에 **원문 그대로** 표시되고 0층으로 세는 이유가 문장으로 뜬다. **재저장해도 값이 `16`이나 빈칸으로 바뀌지 않아야 한다**(정규화기가 값을 고쳐 저장하면 화면에는 아무 잘못도 안 보인다).
- [ ] **전사 계획 — 못 푸는 자재 ID**: 분리자 없는 자재 ID(`ABC`, `ABC_`, `_01`) → **조회 요청 자체가 나가지 않고** `미상`으로 표시된다. 숫자 `0`이 뜨면 실패다("조회 못 함"과 "잔여 0"은 다르다).
- [ ] **전사 계획 — 초과 배정 경고가 죽지 않는가** 🔴: 한 자재에 두 구간이 각각 요구를 걸어 **합계만 초과**하게 만든다(개별로는 부족하지 않게). `validate`가 `status: ok` + 경고 0건을 내면 실패 — 집계 게이트가 라벨 가짓수를 세고 있다는 뜻이다.
- [ ] **전사 계획 — degraded 표기**: 역할 바인딩을 하나 끊고 자재 요약 조회 → `remaining`이 숫자가 아니라 **미상**으로 표시되고 경고가 뜬다. **초록/정상으로 뒤집히면 실패.**
- [ ] **전사 계획 — 이동 허브**: 자재 행 클릭 → 해당 자재 맵으로 이동, 브레드크럼·뒤로가기로 복귀 후 그 자재만 재조회.
- [ ] **전역 토스트**(전 페이지): 에러 토스트 4개를 띄운 뒤 성공 토스트 1개 → **새 토스트가 즉시 사라지지 않고** 가장 오래된 에러가 밀려난다. 토스트를 띄운 채 탭을 30초 이상 백그라운드로 두었다 복귀 → **만료된 토스트가 즉시 정리**된다(누적 없음). 같은 `dedupeKey`의 비-에러 알림 반복 → `… · N건`으로 합쳐진다. 에러는 **합쳐지지 않는다**.

### 2.10 어드민 대시보드 (5탭 IA)

- [ ] **탭 전환**: Overview/File/Chain/AutoUpdate/Enrichment 5탭 모두 렌더 + 콘솔 에러 없음. 해시 라우팅(`#file` 등) 직접 진입 동작, 구 별칭(`#outbox`)이 Chain 탭으로 리다이렉트.
- [ ] **Overview**: 4카드에 헬스 상태·핵심 지표 표시, 최근 이벤트 목록, 카드 클릭 → 해당 탭 딥링크 이동. 파이프라인 헬스 스트립이 탭 전환에도 유지.
- [ ] **Outbox 재시도**(Chain 탭): 실패 outbox 이벤트 단건 재시도 → 상태 전환. "전체 재시도" 동작. 이벤트 진단 → Edit Mapper 딥링크로 에디터 뷰 진입.
- [ ] **코드 에디터(공용 뷰)**: 파일 피커에서 파서 스크립트 열기 → Monaco 편집 → 저장 → 다음 인제션에 반영. `#editor=<path>` 딥링크 직접 진입 동작. dirty 상태에서 다른 파일 선택 시 confirm. (오프라인 등 Monaco CDN 실패 시 인라인 에디터 폴백.)
- [ ] **Config 리로드**: `table_config.json` 수정 → Reload Configs → 웹서버·워커 캐시 리로드(SYSTEM_RELOAD), 신규 테이블 물리 CREATE + 워크스페이스 감시 시작(이슈 #7 해소 확인).

### 2.11 온톨로지 그래프 (승격·뷰어·추적)

- [ ] 🎯 **자동 승격**: 매핑 대상 테이블 셀 교정 → 재조회 없이 graph_nodes/edges에 반영(워커 `[GraphLatency]` 로그 lag 확인, 실측 기대 ~수백 ms). 교정값 엣지는 provenance=user.
- [ ] **수동 백필**: 메인 툴바 그래프 동기화 버튼(또는 POST `/api/graph/sync`) → 성공 응답 + 테이블 노드/엣지 수 stats 반영.
- [ ] **뷰어 — 탐색**: `/graph.html` 진입 → stats 카운트 카드 표시 → 검색창에 identity 일부 입력 → 자동완성 → 선택 → k-hop 동심원 서브그래프 렌더. 팬·줌 동작, **노드 더블클릭 → 재중심 탐색**, 노드 캡 초과 시 truncated 배지.
- [ ] **뷰어 — Connections 테이블**: 노드 **단일 클릭** → 우측 패널에 선택 노드 정보 + Connections 테이블(방향·엣지 type·상대 노드) 표시, 캔버스 중심은 유지. 비중심 노드는 "서브그래프 단면" 배지 → 전체 이웃 보강 후 배지 제거. 이웃 80행 초과 시 "더 보기"로 증분 렌더(프리징 없음).
- [ ] **뷰어 — 행 클릭 시드 연동**: Connections 테이블 행 클릭 → 해당 노드 중심 재조회 + URL `?label=&identity=` 갱신 + 검색바(label·identity) 반영. 브라우저 뒤로가기 → 이전 중심(URL·검색바·그래프) 복원. 패널 접기(`»`) 토글 후 노드 클릭 시 자동 펼침.
- [ ] **뷰어 — user 강조**: 사람이 교정한 값에서 유래한 엣지가 강조색(`--overwrite`)으로 구분 표시(Connections 테이블 행에도 동일 강조).
- [ ] **뷰어 — 라벨 노드 리스트**: stats 라벨 카드 클릭 → 그 라벨의 노드 목록(identity 오름차순, 로드수/총수 헤더) 표시, 200행 초과 시 "더 보기" 증분 로드. 행 클릭 → 해당 노드 중심 탐색, back → Stats 복귀.
- [ ] **추적 리포트**: 메인 그리드에서 매핑 대상 행 1~여러 개 선택 → 「🕸️ 추적」 → 새 탭 trace.html에 시드 칩 + 라벨별 그룹 테이블 + 타임라인 렌더. depth 변경 → 즉시 재실행, 시간 범위 입력 → 재실행 버튼 동작.
- [ ] **추적 에지 — missing seeds**: 그래프에 없는 시드 포함 시 missing 구분 표시(전체 실패 아님). 시드 21개 이상 선택 시 상한 20 토스트.
- [ ] **크로스링크**: 추적 리포트 노드 → 뷰어(`?label=&identity=`) 이동, 뷰어 → 추적 리포트 역방향 이동.
- [ ] **진입점 자동 표시**: 매핑 없는 테이블에서는 「🕸️ 추적」 버튼 숨김, 매핑 대상 테이블 전환 시 노출.

### 2.12 듀얼 테마

- [ ] **토글**: 메인 툴바 테마 버튼 → 라이트↔다크 전환, AG-Grid 포함 전 영역 재도색(그리드 재생성/데이터 소실 없음).
- [ ] **유지/전파**: 전환 후 새로고침·타 페이지(enrichment 등) 이동 시 테마 유지(localStorage). 첫 로드 시 흰 화면 깜빡임(FOUC) 없음.
- [ ] **전 페이지 렌더**: admin/map_editor/enrichment 각 페이지가 양 테마에서 가독성 유지 — 각 페이지 헤더의 자체 토글 버튼(`data-theme-toggle`, 4페이지 모두 존재)으로 직접 전환하며 확인.

### 2.13 WS 실시간 반영

- [ ] 🎯 **다중 클라이언트 반영**: 브라우저 창 2개에서 같은 테이블 열기 → A창 편집 → B창에 체감 즉시(100ms 수준) 델타 반영 + 변경 셀 플래시. 전체 리프레시(스크롤 위치 소실) 아님.
- [ ] **행 생성/삭제 반영**: A창 행 추가/삭제 → B창 그리드에 행 추가/제거 + 총계 갱신.
- [ ] **재연결 에지**: 서버 재시작 → 클라이언트가 백오프 재연결 → 재연결 후 편집·수신 정상(수동 새로고침 불필요).
- [ ] **인제션 브로드캐스트**: 파일 드롭 → 열려 있는 모든 창에 진행/완료 토스트 + 그리드 갱신.

### 2.14 데스크톱 래퍼

- [ ] **기동**: `python run_decoupled_app.py` → QtWebEngine 셸에 메인 그리드 로드(`?client=desktop`).
- [ ] **OS 드래그앤드롭**: 파일을 셸 창에 드롭 → 현재 테이블로 업로드·인제션 완료.
- [ ] **네이티브 다운로드**: CSV export → OS 파일 저장 다이얼로그 표시·저장.
- [ ] **다운로드 배포**: 웹에서 GET `/api/download/client` → 셸 패키지 다운로드.

### 2.15 운영 감시 🎯

> ⚠️ **아래 정지·종료 항목은 격리 환경에서 하십시오** — `devenv.py up`(:8081) + `ASSY_API_PORT=8081`. 운영 스택에서 워커를 죽여 보는 것은 실데이터 유입을 끊는 행위입니다.

- [ ] **헬스 기본**: `curl -i http://localhost:8080/health` → **200 + `Content-Type: application/json`**. 본문 `status: ok`, `checks.workers`에 워커 4종이 모두 있고 전부 `ok`.
- [ ] **catch-all과 구분**: 아무 오타 경로(`/healthz` 등) → **HTML 200**이 온다. `/health`만 JSON인지 확인(감시 대상 경로를 틀리면 죽은 서버가 살아 보인다).
- [ ] 🎯 **죽으면 되살아난다**: 워커 프로세스 하나를 강제 종료 → 로그에 재시작 줄 + `supervisor_status.json`의 `restarts` 증가 → 수십 초 내 `/health` 다시 `ok`.
- [ ] 🎯 **살아 있는데 멈춘 것을 잡는다**: 워커를 **정지(suspend)**시킨다(kill 아님) → **약 1분 뒤**(마지막 박동 기준 60초) `/health`가 **503**, 해당 워커 `status: wedged`. 재개하면 곧(초 단위) `ok`, pid 불변. *(pid만 보는 감시로는 절대 안 잡히는 케이스 — 이 항목이 이 절의 핵심이다)*
- [ ] 🎯 **박동하는데 일이 안 되는 것을 잡는다**(`stalled`): 인제션 작업을 claim한 상태에서 **작업만** 멈춘다(워커 루프는 계속 돌게 둘 것) → **약 5분 뒤**(300초) 해당 워커 `status: stalled` + 503. ⚠️ **`wedged` 시험으로 이 항목을 대신할 수 없다** — 임계도 조건도 다르고, 실제 사고는 워처의 3초 재시도 폴러가 계속 박동하는 동안 인제션이 멈춘 형태였다. 또 더 구체적인 판정을 덮지 않는지 확인: `down`/`wedged`인 워커는 `stalled`로 바뀌면 안 된다.
- [ ] **박동 pid 위조 방지**(`foreign_beat`): 같은 역할 이름으로 다른 프로세스가 박동 파일을 쓰게 한 뒤 → 감시자가 띄운 pid와 불일치하므로 `ok`가 아니라 `foreign_beat`가 뜬다(유령 프로세스가 정체를 가리지 못한다).
- [ ] **영구 실패는 조용히 넘어가지 않는다**: 자식이 즉사하도록 만들면(예: 잘못된 config) 5회 재시작 후 **`FAILED` 배너 로그** + `/health` 503이 **계속** 유지된다(무한 재시작 금지).
- [ ] **적체는 나이로 본다**: 대형 파일(수만 행) 적재 중 `/health`가 `ok`를 유지하는지. 건수가 많다는 이유만으로 경보가 뜨면 회귀다.
- [ ] **격리 워처 관문**: `DATABASE_URL`을 운영으로 둔 채 `devenv.py watcher-up` → **REFUSED로 기동 거부**(워처 프로세스가 뜨지 않음). 로그 파일이 새로 생기지 않는 것까지 확인.
- [ ] **격리 로그 누수 없음**: 격리 스택을 돌린 전후로 `server/*.log` 5종의 크기·mtime이 불변인지.
- [ ] **설치 스크립트 안전성**: `install_product_tables.py`(인자 없음) → **아무것도 쓰지 않고** 할 일만 출력. `--apply` 후 현장 항목의 키 순서·들여쓰기가 그대로인지.

---

*이 문서는 기능 병합 시마다 doc-keeper가 갱신한다 — [CONTRIBUTING](../process/CONTRIBUTING.md) · 소유 매핑: [DOC_OWNERSHIP](../process/DOC_OWNERSHIP.md).*
