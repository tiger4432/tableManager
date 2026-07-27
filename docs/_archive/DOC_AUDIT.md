# 📋 AssyManager 문서·개발체계 진단서 (Documentation Audit & Governance Proposal)

> 🗄️ **SUPERSEDED** by [process/CONTRIBUTING](../process/CONTRIBUTING.md) · [process/DOC_OWNERSHIP](../process/DOC_OWNERSHIP.md) · [README](../README.md) on 2026-07-27. 히스토리 추적용으로만 보존됩니다.
>
> **아카이브 근거:** 실행이 끝난 **1회성 계획서**입니다(P1~P5 반영 완료). 여기 제안됐던 규율 — 배지 표준·docs-as-code·아카이브 처리 방식·소유 매핑 — 은 전부 위 세 문서로 옮겨졌고 **그쪽이 정본**입니다. 새 작업에서 이 파일을 읽을 이유는 없습니다.

> **Status:** ✅ Executed (2026-07-24 — P1~P5 반영 완료)
> **작성일:** 2026-07-24
> **범위:** 현황 진단 + 정비 목표 구조 + 개발 체계(거버넌스) 규칙 + 단계별 실행 계획
> **근거:** `docs/` 전수 검토 + `server/` · `client2/` · `client/` 코드 직접 매핑(2026-07-24 기준)
> **본 문서의 성격:** 이 문서는 *진단과 계획*만 담습니다. 실제 문서 이동·재작성·인덱스 재생성 등 **실행은 별도 승인 후** 진행합니다.

---

## 0. 한눈에 보기 (Executive Summary)

- AssyManager의 **코드는 웹(client2) + 데스크톱 셸(QtWebEngine) + 백엔드 5개 프로세스** 체제로 성숙했으나, **최상위 "권위 문서"들은 2026년 4~6월 PySide6 시대에 멈춰 있습니다.**
- 히스토리(`docs/history/`, 168개)와 서브시스템 가이드(map_editor, ingestion, chain, auto_update)는 **7월까지 성실히 관리**되고 있습니다. 문제는 이 최신 지식을 묶어주는 **단일 진실 원천(SSOT)과 갱신 규율의 부재**입니다.
- **핵심 처방:** ① 현재 아키텍처를 반영한 SSOT 신설, ② 낡은 문서를 `_archive/`로 이관해 혼선 제거, ③ 히스토리 인덱스 자동화, ④ "docs-as-code" 갱신 규율을 SOP에 명문화.

---

## 1. 현재 시스템의 실제 아키텍처 (Verified Ground Truth)

> 아래 내용은 문서가 아니라 **실제 코드**를 매핑한 결과입니다. 향후 SSOT 작성의 사실 기준(fact base)으로 사용합니다.

### 1.1 프로세스 토폴로지 (멀티프로세스)

`run_decoupled_app.py`가 다음 5개 프로세스를 통합 기동합니다.

| 프로세스 | 진입점 | 역할 |
|---|---|---|
| **Web API + WS 허브** | `server/main.py` (3,036줄) | REST/WebSocket, `127.0.0.1:8080`. `DECOUPLED=True` 환경변수로 인라인 워커 비활성화 |
| **File Ingestion Watcher** | `run_watcher.py` → `parsers/directory_watcher.py` | `ingestion_workspace/*/raws/` 감시, 파이프라인 파서 매칭·적재·아카이빙 |
| **Auto-Update Scheduler** | `run_auto_update.py` | `auto_update/*.py` 주석기반 크론 실행 → `raws/`에 CSV 드롭 |
| **Chain Ingestion Worker** | `run_chain_worker.py` → `chain_ingestion_worker.py` | outbox 폴링, `chain_rules.json` 규칙별 맵퍼 실행으로 파생 데이터 생성 |
| **Graph Sync Worker** | `run_graph_sync.py` → `graph_sync_worker.py` | **독립 FastAPI 서비스(포트 8090)**. Neo4j 또는 `virtual_graph.json`으로 동기화 |

**프로세스 간 통신:** PostgreSQL **Transactional Outbox** 패턴 — `database_outbox` 테이블 + `LISTEN/NOTIFY` 채널 `outbox_event`. 워커→웹서버 콜백은 HTTP `POST /internal/events/*`. 설정 변경은 `SYSTEM_RELOAD` outbox 이벤트로 전 데몬에 전파.

### 1.2 프론트엔드 (client2 — 웹이 메인)

- **Vite 멀티페이지 앱(Vanilla ESM, 프레임워크 없음, ~9,200줄).** 3개 진입점: `index.html`→`main.js`(그리드), `admin.html`→`admin.js`(어드민, Monaco CDN), `map_editor.html`→`map_editor.js`(맵 에디터).
- **그리드 라이브러리: AG-Grid Community `^35.3.0`** (유일한 런타임 의존성). 맵 에디터는 AG-Grid 미사용 — 커스텀 캔버스 렌더링.
- **상태 관리:** `state.js`의 **단일 싱글턴 객체**를 직접 변조. 리액티브/옵저버블 아님 — 변조 후 명시적 UI 리프레셔 호출(수동 반응성). Tx 편집 버퍼 `pendingTxEdits`가 트랜잭션 모드를 구동.
- **모듈 12종:** main(오케스트레이터)/state/dom/api/websocket/grid/clipboard(엑셀형 범위선택)/timeline(감사 히스토리)/admin/map_editor/ui/utils.

### 1.3 데스크톱 셸 (얇은 래퍼)

- `client/desktop_wrapper.py` (259줄) = **QtWebEngine 래퍼**. `http://localhost:8080/?client=desktop` 로드(내장 FastAPI). `?client=desktop` 플래그로 데스크톱 전용 동작 토글.
- 네이티브 기능: OS 드래그앤드롭 업로드(`httpx`로 `/tables/{t}/upload` POST), 네이티브 다운로드 다이얼로그, F12 DevTools(원격 디버깅 9222), `assymanager://` URI 스킴(HKCU) 등록.
- ⚠️ **구 PySide6 데스크톱 클라이언트(`client/main.py`, `ui/navigation_rail.py`, `models/table_model.py`)는 존재하지 않습니다** — 여러 문서가 아직 이들을 참조 중.

### 1.4 데이터 모델 (`server/database/models.py`)

| 모델 | 테이블 | 용도 |
|---|---|---|
| `DataRow` | `data_rows` | **레거시** JSON blob 저장(GIN/트라이그램 인덱스). 동적 정규화 테이블로 대체됨 |
| `AuditLog` | `audit_logs` | 셀 단위 변경 이력(old/new, source, tx_id) |
| `DatabaseOutbox` | `database_outbox` | 트랜잭셔널 아웃박스(event_uuid, status, processed_chain) |
| `FileIngestionLog` | `file_ingestion_logs` | 파일 적재 로그(FAILED/SUCCESS/PENDING_RETRY) |
| `CellOverwrite` | `cell_overwrites` | 셀 오버라이트/핀 상태(is_overwrite, manual_priority_source) |
| `CellSource` | `cell_sources` | **다중 소스 레이어링 저장소** — (table,row,col,source)당 1행 |
| *동적 모델* | table_config 기반 | 네이티브 타입 컬럼 + 공용 메타(row_id, business_key_val, graph 플래그). `ALTER TABLE`로 핫스왑 |

### 1.5 핵심 비즈니스 로직 (`server/database/crud.py`, 1,781줄)

- **소스 우선순위** `SOURCE_PRIORITY = {user:0, collision_merge:1, pipeline_parser:2, custom_script:3}` (낮을수록 우선). 테이블별 `source_priority` 오버라이드 지원.
- `compute_priority_value()` — 수동 핀 우선 → 우선순위 맵 정렬 → 표시값 결정.
- `apply_batch_updates()` — 통합 업서트 코어. `replace_map` 모드(맵 저장 시 `map_key_columns` 기준 기존 행/소스 bulk purge 후 재적재), `collision_merge`(비즈니스 키 충돌 시 사용자 오버라이트 보존 + 이중 추적).

### 1.6 설정 주도 (`server/config/`)

`table_config.json`(현재 6개 테이블: bonding_map, inventory_master, production_plan, large_table_100, parts, wafer_map_metadata)이 스키마·타입·비즈니스키·복합키·map_key_columns를 구동. `chain_rules.json`(체인 규칙), `ontology_mapping.json`(그래프 매핑), `maps.json`(맵 프리셋), `scheduler_status.json`(스케줄러 실시간 상태). `config_watcher.py` + `SYSTEM_RELOAD`로 무중단 반영.

### 1.7 맵 에디터 백엔드 유틸

- `utils/physical_wafer_engine.py` — SEMI 표준 웨이퍼 지오메트리(유효 반경, 격자 산출, 원형 내부 판정, 마스크 생성).
- `utils/coordinate_transformer.py` — 셀↔물리↔시각 좌표 양방향 변환(회전/면반전/Y반전/오프셋), 표준좌표 정규화, E1/E2 외곽층 분류.
- `parsers/html_topology_parser.py` — HTML `<table>`→구조화 데이터(rowspan/colspan 복원, 인접 그래프, 매트릭스 맵 레코드 평탄화).

> **정정 사항:** `map_editor.js`는 **WebSocket 동기화를 사용하지 않습니다.** 맵 데이터는 REST(`loadExistingMap`/`pushMapData`)로 pull/push하고, 레전드는 브라우저 `localStorage`에 저장합니다. 실시간 WS 동기화는 메인 그리드 페이지(`websocket.js`)에만 존재합니다.

---

## 2. 문서 드리프트 감사 (Documentation Drift Audit)

범례: 🔴 STALE(현실과 상충) · 🟠 부분 최신/불완전 · 🟢 최신 · ⚪ 참고용

### 2.1 최상위 "권위" 문서 — 🔴 최우선 정비 대상

| 문서 | 버전/일자 | 문제점 |
|---|---|---|
| `ASSY_MANAGER_BIBLE.md` | v1.5 / 06-09 | "PySide6 프론트엔드 / ApiLazyTableModel" 서술. 5개 워커·맵에디터·체인·복합키·outbox 전량 누락 |
| `guide/TECHNICAL_GUIDE.md` | v2.2 / 06-09 | 위와 동일. "Thin Client-Thick Server(PySide6)" 프레이밍 |
| `analysis/ARCHITECTURE_ANALYSIS.md` | v2.0 | "SQLite/JSON DB", `client/main.py`·`navigation_rail.py` 참조 — **모두 실존하지 않음** |
| `CLIENT_FEATURE_CHECKLIST.md` | v1.4 / 04-20 | QTableView/QMessageBox 기준. 웹 UI·맵에디터·어드민 미반영 |
| `agentic_environment.md` | 04-12 | `technical_manual.md`, `task.md`, `client/models/table_model.py` 참조 — **셋 다 실존하지 않음** |
| `PROJECT_RECAP.md` | 07-12 | Phase 80까지 갱신되어 비교적 최신이나 "PySide6 프론트엔드"·"SQLite" 잔재 서술 존재 |

### 2.2 인덱스/진입점 — 🟠

| 문서 | 문제점 |
|---|---|
| `history/README.md` | Phase 73.6(04-20)에서 정지. 이후 **~130개 히스토리 파일 미인덱싱**(맵에디터·체인·어드민·auto-update 전량) |
| `docs/` 루트 | **유일한 진입점(README) 부재.** BIBLE·TECHNICAL_GUIDE·ARCHITECTURE_ANALYSIS·PROJECT_RECAP가 각자 "마스터"를 자처 |

### 2.3 서브시스템 스펙/가이드 — 🟢 (양호, 정비 시 SSOT 하위로 재배치)

| 문서 | 일자 | 비고 |
|---|---|---|
| `spec/MAP_EDITOR_SPEC.md` | 07-22 | 최신. 정비 템플릿 모범 사례 |
| `map_editor/*` (4종) | 07월 | 아키텍처·철학·스펙 잘 분리됨 |
| `guide/INGESTION_GUIDE.md` | 07-17 | 최신 |
| `guide/chain_ingestion_guide.md` | 07-16 | 최신 |
| `guide/AUTO_UPDATE_GUIDE.md` | 07-15 | 최신 |
| `guide/data_preservation_and_signature_change.md` | 07-17 | 최신 (SOP가 참조) |
| `guide/HTML_TOPOLOGY_PARSER_GUIDE.md` | 06-20 | 양호 |
| `spec/batch_update_technical_specification.md` | 06-15 | 양호 |
| `spec/FAILURE_MANAGEMENT_SPEC.md` | 06-09 | 양호 |

### 2.4 오래됐지만 대체로 유효 — 🟠/⚪ (검증 후 유지)

`spec/{DATA_SYNC_SPEC, BUSINESS_LOGIC_SPEC, DEBUGGING_GUIDE, BATCH_INGESTION_SPEC, BATCH_PROCESSING_SPEC, TABLE_ENGINE_SPEC, api_documentation, graph_db_integration_plan}.md`, `guide/{CONDA_SETUP, NATIVE_POSTGRES_SETUP, POSTGRES_OPERATIONS}_GUIDE.md`, `ICON_DIAGNOSIS_REPORT.md`, `integration_guide.md`, `starting_guide.md`, `analysis/*`(SCALABILITY 등) — 일부 개념은 유효하나 프론트엔드/DB 서술 재검증 필요.

---

## 3. 근본 원인 (Root Causes)

1. **단일 진실 원천(SSOT) 부재** — 겹치는 "마스터" 문서 4종이 서로 다른 시점의 진실을 주장 → 신규 참여자가 무엇을 믿어야 할지 알 수 없음.
2. **갱신 규율 부재** — 히스토리는 잘 쌓이지만, 아키텍처가 바뀌어도 상위 "리빙 문서"에 역류시키는 규칙이 없음. 문서가 append-only 로그로만 성장.
3. **버전 체계 혼선** — `Phase 73.5/73.6/80`의 불연속 번호 + `v1.x/v2.x`가 혼재해 신선도 판별 불가.
4. **신선도 메타데이터 부재** — 문서 상단에 "언제 기준으로 검증됨"이 없어 STALE 여부를 파일 mtime으로만 추정.

---

## 4. 제안 목표 구조 (Target Structure)

**핵심 원칙: 리빙(살아있는) 문서 ↔ 히스토리(불변)의 명확한 이원화 + 유일 진입점.**

```
docs/
├── README.md                    ★ 유일한 진입점 (문서 지도 + 각 문서 Status 배지)
├── DOC_AUDIT.md                 (본 문서 — 정비 완료 후 _archive 이관)
├── overview/
│   └── SYSTEM_OVERVIEW.md        ★ SSOT: §1의 현재 아키텍처를 정본화
├── architecture/                 (analysis/ 대체)
│   ├── backend.md                (5-프로세스 토폴로지 + outbox 패턴)
│   ├── frontend.md               (client2 웹 + AG-Grid + 데스크톱 래퍼)
│   ├── data_model.md             (models.py 7종 + 동적 테이블)
│   └── layering_and_priority.md  (CellSource/CellOverwrite + compute_priority_value)
├── subsystems/                   (리빙 스펙 — 서브시스템 소유 문서)
│   ├── ingestion_pipeline.md · chain_ingestion.md · auto_update.md
│   ├── map_editor.md · realtime_sync.md · graph_sync.md · admin.md
├── operations/                   (guide/의 setup·postgres·conda 이관)
├── spec/                          (상세 함수/API 레퍼런스 — 유지, 헤더 표준화)
├── history/                      (불변 append-only + 자동 생성 INDEX)
├── process/                      ★ 개발 체계
│   ├── CONTRIBUTING.md           (docs-as-code 갱신 규율)
│   ├── DOC_OWNERSHIP.md          (서브시스템 ↔ 문서 소유 매핑)
│   └── RELEASE_LOG.md            (Phase 번호 대체: 날짜+시맨틱 요약)
└── _archive/                     ★ 낡은 문서 원본 보존(삭제 대신 이관)
```

---

## 5. 개발 체계 규칙 (Governance / Development Framework)

1. **SSOT 원칙** — `overview/SYSTEM_OVERVIEW.md` 하나만 "현재 상태"의 권위. 나머지 문서는 여기서 링크. 중복 서술 금지.
2. **Docs-as-code 갱신 규율** — 히스토리 기록 시 *아키텍처가 바뀌었다면* 해당 서브시스템 리빙 문서도 **같은 커밋**에서 갱신. `docs/prompts/starting_prompt.md`(SOP) §2에 이 조항을 추가한다.
3. **문서 헤더 표준** — 모든 리빙 문서 상단에 배지 삽입:
   ```
   > Status: 🟢 Living | Last-verified: YYYY-MM-DD | Owner: <subsystem> | Source-of-truth: <code path>
   ```
   → mtime 추정이 아니라 명시적 검증일로 신선도 판별.
4. **히스토리 인덱스 자동화** — `history/README.md`를 파일명에서 자동 생성하는 스크립트 도입(수동 관리 종료).
5. **낡은 문서는 삭제가 아니라 `_archive/`로 이관** — 상단에 SUPERSEDED 배지 부착. 링크·히스토리 보존 + 혼선 제거. **(승인된 처리 방식)** → 배지 문구의 정본은 [CONTRIBUTING §5](../process/CONTRIBUTING.md)이며, 여기 있던 사본은 그쪽으로 흡수됐습니다.
6. **버전 체계 통일** — 불연속 `Phase N.x` 폐기, `RELEASE_LOG.md`에 `YYYY-MM-DD | 영역 | 시맨틱 요약` 형식으로 일원화.

---

## 6. 단계별 실행 계획 (승인 후 진행)

> **현재 승인 상태:** 본 진단서(`DOC_AUDIT.md`) 작성까지만 승인됨. 아래 P1~P5는 **차기 승인 대상**입니다.
> **낡은 문서 처리 방식:** `_archive/` 이관 (§5-5, 확정).

| 단계 | 작업 | 완료 검증 |
|---|---|---|
| **P1** | `docs/README.md`(문서 지도) + `overview/SYSTEM_OVERVIEW.md`(SSOT, §1 정본화) 신규 작성 | 모든 링크 유효 · 5개 워커·client2·outbox 정확 반영 |
| **P2** | 🔴 문서 6종을 `_archive/`로 이관 + SUPERSEDED 배지 + SSOT 링크 | 중복 "마스터" 제거 · 데드 링크 0 |
| **P3** | `history/README.md` 인덱스 자동 재생성(스크립트 도입) | 168개 전량 인덱싱 |
| **P4** | `process/` 3종 문서 작성 + SOP §2에 docs-as-code 조항 추가 | 갱신 규율 문서화 |
| **P5** | 서브시스템 리빙 스펙 재배치(최신 guide/spec 이동) + 헤더 배지 표준화 | 소유 매핑 완성 · 전 문서 Status 배지 보유 |

---

## 7. 부록: 전체 문서 인벤토리 (28종)

| 경로 | Status | 처리 방향 |
|---|---|---|
| `ASSY_MANAGER_BIBLE.md` | 🔴 | → `_archive/` (SSOT가 대체) |
| `guide/TECHNICAL_GUIDE.md` | 🔴 | → `_archive/` |
| `analysis/ARCHITECTURE_ANALYSIS.md` | 🔴 | → `_archive/` (내용은 `architecture/`로 리라이트) |
| `CLIENT_FEATURE_CHECKLIST.md` | 🔴 | → `_archive/` (신규 웹 체크리스트로 대체) |
| `agentic_environment.md` | 🔴 | → `process/`로 리라이트(경로 수정) |
| `PROJECT_RECAP.md` | 🟠 | 유지, 잔재 서술 정정 |
| `history/README.md` | 🟠 | 자동 재생성 |
| `history/*.md` (168) | 🟢 | 불변 유지 |
| `map_editor/*` (4) | 🟢 | `subsystems/`로 통합 |
| `spec/MAP_EDITOR_SPEC.md` | 🟢 | 유지, 헤더 표준화 |
| `spec/batch_update_technical_specification.md` | 🟢 | 유지 |
| `spec/FAILURE_MANAGEMENT_SPEC.md` | 🟢 | 유지 |
| `spec/api_documentation.md` | 🟠 | 엔드포인트 재검증(§1.1 대조) |
| `spec/{DATA_SYNC,BUSINESS_LOGIC,BATCH_INGESTION,BATCH_PROCESSING,TABLE_ENGINE}_SPEC.md` | 🟠 | 검증 후 유지/이관 |
| `spec/DEBUGGING_GUIDE.md` | 🟠 | `operations/`로 이관 + 갱신 |
| `spec/graph_db_integration_plan.md` | ⚪ | 계획서 — `subsystems/graph_sync.md`로 현행화 |
| `guide/INGESTION_GUIDE.md` | 🟢 | `subsystems/`로 이관 |
| `guide/chain_ingestion_guide.md` | 🟢 | `subsystems/`로 이관 |
| `guide/AUTO_UPDATE_GUIDE.md` | 🟢 | `subsystems/`로 이관 |
| `guide/data_preservation_and_signature_change.md` | 🟢 | `process/`로 이관(엔지니어링 규율) |
| `guide/HTML_TOPOLOGY_PARSER_GUIDE.md` | 🟢 | `subsystems/`로 이관 |
| `guide/{CONDA_SETUP,NATIVE_POSTGRES_SETUP,POSTGRES_OPERATIONS}_GUIDE.md` | 🟢 | `operations/`로 이관 |
| `integration_guide.md` | 🟠 | 재검증 |
| `starting_guide.md` | 🟠 | `README.md`로 흡수 |
| `ICON_DIAGNOSIS_REPORT.md` | ⚪ | 일회성 리포트 → `_archive/` |
| `analysis/{SCALABILITY_REPORT_10M, Analysis_Report_*}.md` | ⚪ | 분석 스냅샷 — `_archive/analysis/` 보존 |
| `prompts/{CLAUDE,starting_prompt,starting_prompts}.md` | 🟢 | 유지, SOP에 docs-as-code 조항 추가 |
| `spec/DEBUGGING_GUIDE.md` 외 참조 링크 | — | P2에서 데드 링크 전수 점검 |

---

*본 진단서는 2026-07-24 코드 기준으로 작성되었으며, P1(SSOT) 완료 시 상단 배지를 🟢 Superseded로 변경 후 `_archive/`로 이관합니다.*
