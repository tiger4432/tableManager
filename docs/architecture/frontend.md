# 🖼️ Frontend Architecture

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 (`b35bc9f`+`280ebf0` — §4.1 **band 서술을 zone 모델로 정정**(stack + 1H/MID/TOP, 자동 저장 삭제·Push 유일 기록자) · `openMaterial` LOAD 동등 라우팅. 직전 `90e284f`: §3.1 실시간 동기화 무결성 3문제 이관 · §5 `adminFetch` 게이트 판정 4규칙) | **Owner:** UI / Excel Interaction
> **Source-of-truth:** `client2/src/*`, `client2/vite.config.js`, `client/desktop_wrapper.py`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

---

## 1. 개요: 웹앱 + 얇은 데스크톱 셸

메인 클라이언트는 **`client2`(웹)**이며, 데스크톱 앱은 이를 감싸는 QtWebEngine 셸입니다.

- **`client2/`** — Vite 멀티페이지 앱(6엔트리), **Vanilla ESM JavaScript(프레임워크 없음)**, JS ~13,000줄. 듀얼 테마(기본 라이트, `tokens.css` 토큰 SSOT + `theme.js` 토글).
- **`client/desktop_wrapper.py`** — `http://localhost:8080/?client=desktop`를 로드하는 `QWebEngineView`(:64-65, URL :254). `?client=desktop` 플래그로 `state.isDesktop`(state.js:32) 토글.

> ⚠️ 구 PySide6 데스크톱 클라이언트(`client/main.py`, `client/ui/`, `client/models/table_model.py`)는 **제거되었습니다.** 남은 것은 `desktop_wrapper.py`뿐.

### 데스크톱 셸 네이티브 기능
| 기능 | 구현 |
|---|---|
| OS 드래그앤드롭 업로드 | `DropEventFilter`+`dropEvent`, `window.currentTable` 조회 후 `httpx`로 `/tables/{t}/upload` POST (:129-171) |
| 네이티브 다운로드 다이얼로그 | `handle_download_request` → `QFileDialog` (:173-191) |
| DevTools | F12 인스펙터, 원격 디버깅 :9222 |
| URI 스킴 | `assymanager://` HKCU 등록 (:205-233) |

---

## 2. 진입점 & 빌드

`vite.config.js` **멀티페이지 빌드**(`rollupOptions.input`):

| HTML | ESM 모듈 | 페이지 |
|---|---|---|
| `index.html` | `src/main.js` | 데이터 그리드(메인) — 「🕸️ 추적」 진입점(`trace_launch.js`) 포함 |
| `admin.html` | `src/admin.js` | 어드민 — 파이프라인 생애주기 5탭(§5, Monaco CDN) |
| `map_editor.html` | `src/map_editor.js` | 웨이퍼 맵 에디터 |
| `enrichment.html` | `src/enrichment.js` | Enrichment Queue 컨베이어(결손 보정 워크리스트) |
| `graph.html` | `src/graph_viewer.js` | 지식그래프 서브그래프 뷰어(§6) |
| `trace.html` | `src/trace.js` | 객체 중심 추적 리포트(§6) |

빌드 산출물 `dist/`는 FastAPI(:8080)가 서빙. `define`로 빌드 타임에 `import.meta.env.VITE_USER`(OS 사용자명) 주입 → `config.js`의 `CURRENT_USER`.

```bash
cd client2
npm run dev       # :5173 개발서버 (API/WS는 127.0.0.1:8080 자동 타겟)
npm run build     # dist/ 생성
```

---

## 3. 모듈 구조 (`client2/src`)

| 파일 | 줄(≈) | 책임 |
|---|---|---|
| `main.js` | 1793 | 메인 페이지 오케스트레이터: init(+`initTraceEntry`), 이벤트 바인딩, 소스 모달, 스마트 페이스트, Tx 모드 apply/discard |
| `state.js` | 49 | **단일 싱글턴 상태 저장소**(gridApi, 현재 테이블/스키마, ws, 선택/드래그, 페이지캐시, `pendingTxEdits`) |
| `dom.js` | 55 | `getElementById` 지연 게터 모음(`elements`) |
| `api.js` | 422 | REST 계층: health, loadTables, switchTable(테이블 전환 시 `refreshTraceEntry` 재판정), loadSchema, fetchData(페이지캐시), handleCellEdit(Tx 스테이징+숫자검증), addRows, deleteSelectedRows |
| `websocket.js` | 249 | 실시간 동기화: 지수 백오프 재연결, `batch_row_{create,upsert,delete}`/`batch_refresh_required`를 AG-Grid 트랜잭션으로 적용(셀 플래시) |
| `grid.js` | 526 | AG-Grid 설정/렌더: `buildColumnDefs`, `renderGrid`, `ensureCellObject`(중첩 셀 `{value,is_overwrite,priority_source}` 정규화) |
| `clipboard.js` | 788 | 엑셀형 범위 선택/클립보드: hit-test, `commitDragSelection`, `getRangeSelectedTSV`, paste, `clearSelectedCells` |
| `timeline.js` | 718 | 감사 히스토리 패널: `loadHistory`, `appendHistoryLocally`, 로그→그리드 점프 네비게이터 |
| `ui.js` | 408 | 공용 UI 반영: `updateTxModeUI`, `setTransactionFilter`, `applyValueToSelectedRange`, Enrichment 배지(`updateEnrichmentBadge`), 페이지캐시 유지, unload 경고 |
| `utils.js` | 307 | `getLocalTimeString`, **전역 토스트**(`showToast` — window 부착), 인제션 진행 위젯. 토스트는 **벽시계 `expireAt` 기준 만료**(백그라운드 탭 setTimeout 스로틀링으로 무한 누적되던 원인 제거) · 상한 4(퇴거는 비-에러 오래된 것 우선, 방금 삽입분 면제) · TTL info/success 5s·warning 9s·**error 15s** · `visibilitychange`/`focus` 스윕 · `dedupeKey` 합치기(**에러 제외** — 건별 원인이 중요) |
| `theme.js` | 92 | 듀얼 테마 전환(`initTheme`/`toggleTheme`/`syncAgGridThemeClasses`) — 토큰 SSOT는 `tokens.css` |
| `config.js` | 5 | 환경 설정: `API_BASE`/`WS_URL`(5173→8080), `CURRENT_USER`, `pageLimit=1000` |
| `admin.js` | 2437 | 어드민 5탭(§5) |
| `map_editor.js` | 4209 | 맵 에디터 + 페인트 잠금 + **오버레이 레이어**(§4) |
| `transfer_plan.js` | 1405 | **전사 계획 사이드바**(§4.1) — map_editor.html에서 소비. 구 `bonding_plan.js`(M1 Info 패널)를 대체·삭제 |
| `enrichment.js` | 754 | Enrichment 컨베이어: 규칙 선택(`loadRules/selectRule`), 워크리스트(`fetchWorklist`), 입력 흐름(`onInputKeydown/saveCurrent` → PUT `/data/updates`), 참조 패널(`initReferencePanel/loadActiveReference`, stale 가드) |
| `graph_viewer.js` | 927 | 그래프 서브그래프 뷰어(§6): stats 카드, 자동완성 검색, BFS 동심원 캔버스(무라이브러리), 팬·줌, Node Inspector, `?label=&identity=` 딥링크 |
| `trace.js` | 454 | trace.html 오케스트레이터(§6): `runTrace`(POST `/graph/trace`, seq 가드) → `renderReport`(그룹+타임라인 청크 렌더), 시드 칩·depth·시간범위, URL 동기화 |
| `trace_core.js` | 234 | 추적 순수 로직(무의존): `composeIdentity`(서버 G1 미러), `capSeeds`(상한 20), `buildTraceRequest`, `groupNodesByLabel`, `splitTimeline` |
| `trace_launch.js` | 107 | index 진입점: `initTraceEntry`/`refreshTraceEntry`(mapping-summary 판정), `openTraceForSelection`(선택 행→시드 변환) |

> `counter.js`는 Vite 템플릿 잔재(미사용).
> **클립보드는 `document`의 `copy`/`paste` 이벤트 + `e.clipboardData`가 정본이다**(`clipboard.js` `setupClipboardHandlers`). `navigator.clipboard`는 **보안 컨텍스트(HTTPS 또는 localhost/127.0.0.1)에서만 존재**하며, 운영은 사내망 평문 HTTP라 그곳에선 `undefined`다. 과거 `main.js`의 keydown에서 Ctrl+C를 가로채 `navigator.clipboard.writeText`로 복사하던 분기가 있었는데, ① 운영에서 `TypeError`(동기 throw라 `.catch()`도 못 받음)로 죽고 ② `preventDefault()`가 먼저 실행돼 정상 동작하던 `copy` 핸들러까지 굶겼다 → **삭제**(2026-07-27). **Ctrl+C/Ctrl+V를 keydown에서 가로채지 말 것.**
> ⚠️ 같은 결함이 남아 있는 곳(평문 HTTP에서 실패): `admin.js`(페이로드/트랜잭션 ID 복사), `map_editor.js` `copyGridToExcel`, `main.js` `smartPasteViaIngestion`(우클릭 Smart Paste).
> **상태 관리 주의:** `state.js`는 리액티브 스토어가 아닌 **평범한 싱글턴**. 변조 후 명시적 UI 리프레셔를 호출하는 수동 패턴. `admin.js`/`map_editor.js`는 `state.js`를 임포트하지 않고 자체 모듈 지역 변수를 사용.

### 3.1 실시간 동기화 무결성 — **되풀이되는 세 문제** (2026-07-27 이관)

> **출처·이관 사유:** 아래 세 문제는 ⚪ [spec/DATA_SYNC_SPEC §3](../spec/DATA_SYNC_SPEC.md)에서 옮겨 왔다. 그 문서의 **해결책 서술은 제거된 PySide6 클라이언트의 것이라 전부 폐기**됐지만, **문제 자체는 프레임워크와 무관하게 되풀이된다** — "페이지 단위로 나눠 읽는 목록"에 "밖에서 들어오는 변경"이 겹치면 언제나 같은 세 가지가 생긴다. 문제 서술을 여기로 옮김으로써 원 문서에 남은 마지막 유효 내용이 없어졌다.

**문제 ①: 중복 행** — 가상/페이지 로딩으로 이미 들고 있는 행과 WS로 새로 들어온 같은 행이 겹쳐, 한 행이 두 번 보인다.
- **올바른 형태**: 행의 **정체를 명시적으로 선언**하고, 유입을 *삽입*이 아니라 **정체 기준 교체**로 처리한다. 로컬 배열 인덱스를 정체로 쓰면 반드시 어긋난다.
- **현행**: `grid.js`가 `getRowId: params => params.data?.row_id || params.data?.id`(:282)를 선언하므로 **AG-Grid가 정체를 강제**하고 `applyTransaction`이 같은 `row_id`를 갱신으로 흡수한다. 즉 이 문제는 **구조적으로 닫혀 있다** — 단 `row_id`가 항상 실려 온다는 전제 위에서다.

**문제 ②: 늦게 도착한 응답이 현재 화면을 오염시킨다** — 필터·검색·페이지를 빠르게 바꾸면 먼저 떠난 요청의 응답이 **나중에** 도착해 이미 바뀐 화면을 덮는다.
- **올바른 형태**: 요청마다 **세대(시퀀스/세션 id)**를 부여하고, **현재 세대가 아닌 응답은 전량 폐기**한다. "마지막에 도착한 것이 최신"이라는 가정이 이 부류의 원인이다.
- **현행**: 이 형태가 실제로 있는 곳은 `trace.js`(`runTrace` seq 가드)와 `enrichment.js`(참조 패널 stale 가드)다. ⚠️ **메인 그리드 `api.fetchData` 경로에서는 대응 장치를 찾지 못했다**(2026-07-27 확인) — `state.pageCache`는 캐시일 뿐 세대 가드가 아니다. **미검증 항목**이며 판정은 [doc-auditor 소관](../process/DOC_OWNERSHIP.md).

**문제 ③: `total`이 외부 삭제 후 드리프트한다** — 다른 클라이언트나 인제션이 행을 지우면, 클라가 로컬로 카운트를 가감하는 순간 **현재 필터에 매칭되던 행이었는지**를 알 수 없어 총계가 틀어진다.
- **올바른 형태**: 총계를 **로컬에서 계산하지 말고**, 현재 필터를 실어 **서버에 다시 묻는다.** 이 값은 클라가 알 수 있는 종류의 값이 아니다.
- **현행**: 조회 경로(`api.fetchData`)는 매 요청 **서버가 준 `result.total`을 그대로 쓴다**(:200-209 — 올바른 형태). ⚠️ 반면 WS 삭제 수신부(`websocket.js` :236-240)는 `applyTransaction({remove})`만 하고 **`total` 재조회를 하지 않는 것으로 보인다** — 하단 `Matches: N`이 낡은 채 남는 경로다. **미검증 항목**, 위와 같이 doc-auditor 소관.

---

## 4. 맵 에디터 (`map_editor.js`, ~4,209줄)

| 영역 | 대표 함수 |
|---|---|
| 렌더링 | `renderGridCanvas`/`scheduleRenderGridCanvas`, `updateCellStyles`, `renderLegendTable`, `updateNotchPosition` |
| 좌표 변환 | `getPhysicalCoords`/`getCellFromPhysicalCoords`, `getVisualCoords`, `getWaferBoundingBox`, `getTransformedPhysicalConfig`, `isCellInsideWafer{,Fast}` |
| 드래그 선택/페인팅 | `initMouseDragEvents`, `handleCellClick`, `fillSelectedCells`, `remapGridValues`, `autoPaintE1E2` |
| 엑셀 복사 | `copyGridToExcel()` — TSV 클립보드 |
| 메타/레전드 | `renderMetadataInputs`, 프리셋 `/api/map-presets`, 레전드 `localStorage`(`map_legend_{table}`) |
| 데이터 동기화 | `loadExistingMap()`(REST pull), `pushMapData()`(REST push) |
| **페인트 잠금** (M2) | `fetchPaintRules`(GET `/api/maps/paint-rules` — 선언 정본이 서버로 이동, 구 `'F'` 하드코딩 대체), **`isProtectedFCell`**(편집 가능 판정의 **단일 관문** — 모든 편집 경로가 여기로 수렴), `updatePaintLockIndicator`. 404/405만 "선언 없음", 네트워크·5xx는 직전 잠금 유지(**조용한 fail-open 제거**). ⚠️ 콜드 스타트(첫 조회 실패)는 아직 열린 채 시작 — QA C4 미해소 |
| **오버레이 레이어** (`7d931dc`) | **좌표 변환은 클라 단일 구현이다** — `소스 원본(x,y) →[소스 메타 프레임]→ 물리 →[현재 화면 컨트롤]→ 셀`. `addOverlayLayer`가 `/tables/{src}/data`(원본 좌표) + `wafer_map_metadata` 2건을 읽고 `projectCellsToPhys`로 투영한다. 오버레이 전용 기하 코드는 없다 — `withPhysFrame`(프레임 창)으로 규격 읽기 지점만 갈아끼운 채 메인 로드와 **같은 두 함수**를 돌린다. `currentGeomSignature`(물리 6종 포함)/`syncOverlayGeometry`가 화면 규격 변경을 추종하고, `overlayAlignChip`은 `align.origin`으로만 판정한다. `importOverlayToGrid`는 `gridData`로만 반영(서버 쓰기 없음). **메인 로드와 코드 경로 완전 분리** — `selectedTable`·`gridData`·legend·규격·brush를 쓰지 않고 `switchTable`을 경유하지 않는다. 기준이 바뀌면 오버레이는 **해제**된다(맵 로드·테이블 전환·프레임 진입 3곳) |

> **정정:** 맵 에디터는 **WebSocket을 사용하지 않습니다.** REST pull/push + localStorage. 실시간 WS는 메인 그리드(`websocket.js`)에만.
> **오버레이와 서버의 관계 (2026-07-27 정정)**: 맵 에디터 클라는 `GET /api/maps/overlay`를 **전혀 호출하지 않습니다** — `client2/src/**` 전수 grep 0건(2026-07-27 실측). `7d931dc` 직후 남아 있던 `limit=1` 선언 probe가 **서버 선언 오버레이 레이어와 함께 삭제되면서 마지막 호출처가 없어졌습니다.** 엔드포인트와 `server/map_overlay.py`는 살아 있으나 소비자는 `bonding_plan`/`transfer_plan`의 가용량 산출 쪽입니다.
> 실패 상태는 **명명된 4종**(`meta_unavailable`·`binding_unavailable`·`align_unavailable`·`no_data`) + IO 실패의 일반 `error`이며, 전부 **그리지 않고 목록에 실패 행으로 남습니다.** *(구 `align_unconfirmed`·`align_override_declared`는 서버·클라 양쪽 어디에도 없습니다 — 선언 레이어와 함께 2026-07-27 삭제.)* 계약은 [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md).

### 4.1 전사 계획 사이드바 (`transfer_plan.js`, ~1,405줄)

**「계획 = 지금 열어 편집 중인 그 맵」** — `bonding_map`을 열면 본딩 계획, `dt_map`을 열면 DT 계획. stage는 열린 테이블에서 유도되며 `plan_id`도 계획 맵 사본도 없습니다.

| 영역 | 내용 |
|---|---|
| 배선 | `map_editor.js`가 `initTransferPlan(paintController)`로 초기화하고 `notifyMapContext`/`notifyLegendChanged`/`notifyPaintCounts`로 통지(단방향) |
| 관리 단위 | **DOE = value**(맵에 칠한 값 하나 = `map_split_registry` 행 하나 = 조건군 하나). **[ZONE 2026-07-28 `b35bc9f` — band 모델 대체]** 층 구조는 그 행의 `stack`(총 층수) + **고정 구역 셋**(`mat_1h`=1층 · `mat_top`=STACK층 · `mat_mid`=그 사이 전부). FROM/TO·`bands` 행·`seq`·배열 순서는 **없습니다**(🗄️ `bands`는 폐기·읽기 전용) |
| **쓰기 소유권** | ⭐ **[M2.6] `transfer_plan.js`는 서버에 쓰지 않습니다.** 레지스트리 행의 유일한 기록자는 `map_editor.js`(⚡ Push 경로 — **자동 저장은 `b35bc9f`에서 삭제**)이고, 패널은 `controller.getLegend()`로 읽고 `controller.updateLegendRow(value, {stack, mat_1h, mat_mid, mat_top, knobs, …})`로만 씁니다 — 저장·삭제·동시성 가드가 **한 경로**에 모입니다. Push 전 편집은 지문 게이트 로컬 초안에만 존재합니다([MAP_EDITOR_SPEC §4-bis](../spec/MAP_EDITOR_SPEC.md)) |
| 파생값 | **저장하지 않습니다.** 구역 소요 = `칠한 셀 수 × 그 구역의 층 수`, 자재당 = `ceil(소요/자재 수)`(합을 먼저 내고 나눔). 식의 구현은 각각 하나뿐입니다(저장 `ceil`/표시 `round`로 갈려 DB 34·화면 33이던 결함) — 정본은 `doe_bands.js`의 순수 zone 모델 + `contracts/doe_band_rules/vectors.json` |
| 서버 왕복 | GET `/api/transfer-plan/{stages,source-summary,validate}` + PUT `/tables/map_split_registry/data/updates`(`replace_map`). ~~`map_doe`/`map_doe_source`~~는 M2.6에서 폐기 |
| **replace 권한 불변식** | `legendReplaceScope`(= `{table, mapKey, fingerprint}`) — "이 화면은 **이 맵의 행**에서 왔고 읽었을 때 이랬다"는 **하나의 주장**. `replace_map` 권한이자 동시성 검사의 기준선이며, 테이블 전환·조회 실패·**절단 응답**·맵 언로드에서 **소거**됩니다. 쓰기 직전 재읽기해 서버가 달라졌으면 upsert로 강등하지 않고 **거부**합니다(`legendConflict`) — 강등하면 낡은 층 구조가 남의 것을 덮습니다 |
| 이동 | `openMaterial(id)` — 맵 간 이동의 유일 허브(브레드크럼 + 뒤로가기 프레임 스택). **[`280ebf0`] 분해 안 되는 ID는 `{첫 맵 키 컬럼: 원문}` 폴백으로 LOAD와 같은 라우팅** — 없는 키는 빈 프레임으로 열리고 Push 시 생성. 존재 probe는 여전히 추측하지 않고 `미상`([MAP_EDITOR_SPEC §6.4](../spec/MAP_EDITOR_SPEC.md)) |

상세 규격: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)(§5 오버레이 정렬 계약 · §6 전사 계획) · [map_editor/](../map_editor/README.md)

---

## 5. 어드민 (`admin.js`, ~2437줄) — 파이프라인 생애주기 5탭

2026-07-25 IA 재편: 탭 축이 메커니즘 7탭에서 **파이프라인 생애주기 5탭**으로 바뀌었습니다. 각 탭 본문은 생애 단계(현황 → 오류 → 수정/실행) 접이식 섹션 스택.

| 탭 | 내용 |
|---|---|
| **Overview** (첫 화면) | **재교정률 한 줄** + 헬스 4카드(File/Chain/AutoUpdate/Enrichment — 상세 수치+최근 이벤트+탭 딥링크), 전폭 레이아웃 |
| **File Ingestion** | 인제션 로그(필터/정렬/페이지) + Workspaces(기본 접힘·요약) + 실패 진단→커스텀 파서 편집 딥링크 |
| **Chain** | Rules 현황 + **Chain 실패(Outbox Transactions)** 재시도 + Mappers(행별 🛠️ Edit) + 실패 진단→맵퍼 편집 딥링크 |
| **Auto Update** | 상태/Run Now + **산출물 인제션 실패 연계**(auto-update 대상 ∩ 파일 실패 교집합) |
| **Enrichment** | 규칙 표 + 결손 카운트 배지 + Queue 딥링크(`enrichment.html?rule=`) — 규칙 편집은 read-only 안내(CRUD API는 백로그) |

- **재교정률 한 줄 (Overview 상단, `renderRecorrection`/`refreshRecorrection`)**: 사람이 같은 셀을 두 번 이상 고친 비율 — 핵심가치 #1의 계기([backend](./backend.md#재교정률-dashboardsummary--recorrection)). **카드도 패널도 모달도 아닌 한 줄**이고, 값 옆에 **분모를 항상 같이 적는다**(표본 100 미만이면 "추세로 읽지 말 것" 문구 + muted 톤). 지켜야 할 두 가지:
  1. **자동 갱신 루프(`fetchOverview`)에 태우지 않는다.** 출처 `/dashboard/summary`는 테이블마다 `count(*)`를 도는 무거운 엔드포인트다(실측 ~1.5s). `await` 없이 던지고 **5분(`RECORRECTION_MIN_INTERVAL_MS`) 간격**으로만 갱신한다 — 본문 카드 렌더가 이 요청을 기다리지 않는다.
  2. **`rate_pct=null`은 "0%"가 아니라 "—"로 렌더한다.** 표본 없음과 조회 실패를 정상 0%로 위장하면 지표가 거짓말을 한다.
- **Code Editor는 독립 탭 폐지** → 편집 딥링크 공용 뷰(Monaco cdnjs, 파일 피커, dirty 가드). `#editor=<encoded path>`로 직접 오픈 가능.
- **해시 라우터**: `#overview/#file/#chain/#autoupdate/#enrichment` + 구 탭 별칭 호환(`#outbox→Chain`, `#workspace→File`, `#mapper→Chain`).
- 신규 서버 API 0건 — 기존 `/admin/*`·`/enrichment/rules`만 소비. 함수 목록: [CODE_MAP §7](./CODE_MAP.md#7-client2src--웹-클라이언트).
- **🔒 어드민 토큰 (2026-07-27)**: 서버가 `/admin/*`을 공유 토큰으로 잠근다([backend §API](./backend.md)). 클라 측 구현은 `admin.js`의 `adminFetch()` 하나뿐 — **로그인 화면도, 새 탭·모드·설정 패널도 없다.** `localStorage['assy.adminToken']`에 보관하고 `X-Admin-Token` 헤더로 전송한다. 서버에 토큰이 미설정이면 게이트가 열려 있어 프롬프트 자체가 뜨지 않는다. 판정 규칙 4가지가 **모두 필요**하다(각각 실제 오작동을 막는다):
  1. **상태코드가 아니라 `WWW-Authenticate: X-Admin-Token` 헤더로 판정한다.** `_resolve_admin_script_path`가 격리 사유로 내는 403이 있어, 상태코드만 보면 그것을 "토큰이 틀렸다"로 오해해 **정상 토큰을 사용자 입력으로 덮어썼다.**
  2. **토큰 세대 카운터** — 프롬프트 도중 이미 교체된 토큰에 대해 **먼저 날아간 응답**이 뒤늦게 도착하면 조용히 재시도한다. 이게 없으면 "동시 7건 → 프롬프트 1회"는 타이밍 운이고, 두 번째 모달이 **올바른 토큰을 두고** "거부되었습니다"라고 말한다.
  3. **취소(`prompt`→`null`)는 저장된 토큰을 지우지 않는다** — 지우면 30초 갱신 타이머가 영원히 모달을 띄운다. 취소 후에는 더 묻지 않고 토스트로 "새로고침하면 다시 물어봅니다"를 알린다.
  4. **503 본문을 토스트로 노출한다** — 서버가 `ASSY_ADMIN_TOKEN`을 설정하고 재기동하라고 정확히 알려주는데, 삼키면 화면엔 "저장 중 오류 발생"만 남아 503 분기의 존재 이유가 사라진다.
  ⚠️ **`/admin/*` 호출은 반드시 `adminFetch`로** — `grep 'fetch(\`${API_BASE}/admin/'`가 0건이어야 한다. 맨 `fetch`로 남은 호출부는 미설정 서버에서 멀쩡히 동작하다가 운영에서만 401이 난다.
  ⚠️ **서빙되는 것은 `dist/assets/admin-*.js`다.** 소스만 고치고 번들을 안 올리면 토큰을 켜는 순간 어드민이 잠긴다 — 판정은 `grep -c X-Admin-Token client2/dist/assets/admin-*.js` > 0.

---

## 6. 지식그래프 뷰어 & 추적 리포트 (온톨로지 트랙 UI)

| 페이지 | 역할 |
|---|---|
| `graph.html` + `graph_viewer.js` | **서브그래프 뷰어** — 첫 화면 `/graph/stats` 카운트 카드, label+identity 자동완성 검색, `/graph/neighbors` 1/2-hop 서브그래프를 무라이브러리 BFS 동심원 캔버스로 렌더. 노드 클릭=재중심 탐색, user provenance 엣지 강조(`--overwrite` 색), truncated 배지. 테마 색은 1회 캐싱+`themechange` 재캐싱(상시 rAF 없음) |
| `trace.html` + `trace.js`/`trace_core.js` | **추적 리포트** — 시드 칩(상한 20)·depth 1–3·시간 범위로 `POST /graph/trace` → 라벨별 엔티티 그룹 테이블 + event_time 시간순 타임라인(user provenance 강조, 구조 엣지 접이식). URL 동기화(`replaceState`), 청크 렌더(그룹 100행/타임라인 300건) |
| 진입 흐름 | 메인 그리드에서 행 선택 → 「🕸️ 추적」(`trace_launch.js`, `/graph/mapping-summary`로 활성 판정) → 선택 행을 identity로 조립(서버 `compose_identity` 미러 — `\|` 조인+이스케이프+float 안정화)해 시드로 전달. graph.html ↔ trace.html 양방향 크로스링크 |

---

## 7. 백엔드 계약

- REST + WebSocket at `127.0.0.1:8080` (FastAPI). 엔드포인트: [backend.md](./backend.md)
- 셀 데이터 형태: `data[col] = {value, is_overwrite, priority_source}` (grid.js `ensureCellObject`가 정규화)
- 그래프 조회: `GET /graph/{stats,neighbors,nodes/search,mapping-summary}` + `POST /graph/trace` (read-only)
