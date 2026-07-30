# 🖼️ Frontend Architecture

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (**§2.1 빌드 게이트 신설** — `client2/package.json`의 `prebuild` = `check:clipboard` + **`check:contracts`**(`client2/scripts/check_contracts.mjs`) 실측. 2026-07-30 이전에는 **계약 클라 하네스 4개를 아무것도 실행하지 않았고**(pytest는 서버 절반만 채점), 그것이 `split_registry_harness.mjs`가 몇 주 동안 죽어 있게 둔 조건이다. 러너는 **목록이 아니라 발견식 스캔**이고 **빈 스캔은 실패**이며 판정은 **종료코드 하나**다. 실측: 4계약 전부 통과. 직전 2026-07-29 **계기 수리 라운드** — 어드민·그래프·추적 **3화면 배선**(왕복 이동의 절반만 세던 비대칭 해소) · 불변식 7 추가(진단이 트리셰이킹으로 dist에서 사라짐 → `window.__assyEffort`) · 허용목록 항목 형식을 **서버가 받는 것만** 수용. 불변식 5·6 추가: *부재는 0이 아니다*(빈 스냅샷은 `undefined` → 필드 생략, 유령 0점 교정 차단) · *존재하지 않는 라우트를 지목한 허용목록 항목은 거절+큰 소리로 보고*(`ROUTE_IDS`). 불변식 1에 **"서버가 기록했을 때만 리셋"** 게이트 추가(`commitIfRecorded` — no-op 저장이 공수를 지우던 결함). **§5 어드민 Overview에 「교정 공수」 한 줄 신설**(정본 계기 + 커버리지 = 수집 중단 감지기). 직전 — **§3.2 상호작용 계측기 신설**: `effort_meter.js` 유일 수집기 + 그리드/Enrichment 배선(교정 쓰기 6경로). **분류는 버리지 않는다**(`nav`/`nav_preserved` 분리 — allowlist가 수집 시점 결정이 아니라 조회 시점 해석). 직전 `b35bc9f`+`280ebf0` — §4.1 **band 서술을 zone 모델로 정정**(stack + 1H/MID/TOP, 자동 저장 삭제·Push 유일 기록자) · `openMaterial` LOAD 동등 라우팅. 직전 `90e284f`: §3.1 실시간 동기화 무결성 3문제 이관 · §5 `adminFetch` 게이트 판정 4규칙) | **Owner:** UI / Excel Interaction
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
npm run build     # prebuild(클립보드 관례 + 계약 하네스 4종) → dist/ 생성
```

### 2.1 빌드 게이트 — **클라 절반을 채점하는 유일한 자리** (`5a14e77` · 2026-07-30)

`package.json`의 `prebuild`가 `check:clipboard` → `check:contracts` 순으로 돌고, **하나라도 실패하면 `vite build`에 도달하지 않습니다.**

- **왜 생겼나**: `contracts/<name>/client_harness.mjs`는 이음매(seam)의 **클라 절반**을 `vectors.json`에 채점하는데, 2026-07-30까지 **아무것도 그것들을 실행하지 않았습니다** — `pytest server/tests/`는 **서버 절반만** 채점하고 `client2/package.json`에는 스크립트가 없었습니다. 그 결과 `split_registry_harness.mjs`가 심볼 5개 개명 뒤 추출 단계에서 **몇 주 동안 예외로 죽어 있었고**, 부르는 사람이 없어 실패가 보이지 않았습니다. **아무도 돌리지 않는 계약은 주석입니다.**
- **발견식이지 목록이 아닙니다**: 러너(`client2/scripts/check_contracts.mjs`)는 `contracts/*/client_harness.mjs`를 **스캔**합니다. 하드코딩 목록은 이 결함을 그대로 재생산합니다 — 계약 #5가 착지하고 아무도 목록에 추가하지 않으면 빌드는 초록인 채 그 계약이 죽어 있습니다.
- 🔴 **빈 스캔은 실패입니다.** `contracts/`가 사라지거나 하네스가 하나도 안 잡히면 "0개, 전부 초록"이 아니라 **exit 1**입니다 — 없는 커버리지를 있다고 보고하는 것은 배선 안 된 종전 상태보다 나쁩니다.
- **판정은 종료코드 하나**로 읽습니다. 하네스의 산문을 러너가 재해석하면 채점자가 둘이 됩니다(`map_seam`은 이름 붙은 기대 발산을 출력하면서 exit 0입니다 — contract-keeper 헌장 규칙 5 "익명의 영구 빨강 금지").
- **현재 상태**(실측 2026-07-30): `band_arithmetic` · `doe_band_rules` · `legend_map_scope` · `map_seam` **4계약 전부 통과**.

> ⚠️ 이 게이트는 **소스**를 채점합니다. 서버가 서빙하는 것은 `dist/` 번들이므로, 소스 변경 후 `npm run build`로 `dist/`를 갱신하고 커밋하는 규율은 그대로입니다([DEPLOY_SETUP](../guide/DEPLOY_SETUP.md) · [FEATURE_CHECKLIST §2.16 A](../qa/FEATURE_CHECKLIST.md)).

---

## 3. 모듈 구조 (`client2/src`)

| 파일 | 줄(≈) | 책임 |
|---|---|---|
| `main.js` | 1793 | 메인 페이지 오케스트레이터: init(+`initTraceEntry`), 이벤트 바인딩, 소스 모달, 스마트 페이스트, Tx 모드 apply/discard |
| `state.js` | 49 | **단일 싱글턴 상태 저장소**(gridApi, 현재 테이블/스키마, ws, 선택/드래그, 페이지캐시, `pendingTxEdits`) |
| `dom.js` | 55 | `getElementById` 지연 게터 모음(`elements`) |
| `api.js` | 422 | REST 계층: health, loadTables, switchTable(테이블 전환 시 `refreshTraceEntry` 재판정), loadSchema, fetchData(페이지캐시), handleCellEdit(Tx 스테이징+숫자검증), addRows, deleteSelectedRows |
| `websocket.js` | 249 | 실시간 동기화: 지수 백오프 재연결, `batch_row_{create,upsert,delete}`/`batch_refresh_required`를 AG-Grid 트랜잭션으로 적용(셀 플래시) |
| `grid.js` | 643 | AG-Grid 설정/렌더: `buildColumnDefs`, `renderGrid`, `ensureCellObject`(중첩 셀 `{value,is_overwrite,priority_source}` 정규화), `extendRangeByKeyboard`(§2.1-bis `Shift`+방향키 범위 선택) |
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
| `effort_meter.js` | 320 | **상호작용 계측기(§3.2)** — 핵심가치 #1 정본 계기의 **유일한 수집기**. 키·마우스·화면이동(상실/유지 분리) 원시 카운트 + 세션 id(`sessionStorage`), `PUT .../data/updates`에 선택 필드로 편승. 그리드·Enrichment·맵 에디터 3개 진입점이 공유(빌드에서 전용 청크로 분리 — 단일성 실측 가능) |

> `counter.js`는 Vite 템플릿 잔재(미사용).
> **클립보드는 `document`의 `copy`/`paste` 이벤트 + `e.clipboardData`가 정본이다**(`clipboard.js` `setupClipboardHandlers`). `navigator.clipboard`는 **보안 컨텍스트(HTTPS 또는 localhost/127.0.0.1)에서만 존재**하며, 운영은 사내망 평문 HTTP라 그곳에선 `undefined`다. 과거 `main.js`의 keydown에서 Ctrl+C를 가로채 `navigator.clipboard.writeText`로 복사하던 분기가 있었는데, ① 운영에서 `TypeError`(동기 throw라 `.catch()`도 못 받음)로 죽고 ② `preventDefault()`가 먼저 실행돼 정상 동작하던 `copy` 핸들러까지 굶겼다 → **삭제**(2026-07-27). **Ctrl+C/Ctrl+V를 keydown에서 가로채지 말 것.**

#### §2.1-bis 범위 선택은 키보드로도 된다 (`Shift`+방향키, 2026-07-30)

> **원칙: 손이 키보드를 떠나지 않게 한다.** 공수 계기(§계기 절)의 배점은 키 1 / 마우스 3이므로, **범위 드래그가 필요한 일괄 채우기는 이득의 대부분을 반납한다**. 그래서 `Shift`+방향키로 사각형을 잡는 경로를 추가했다(`grid.js` `extendRangeByKeyboard`). 격리 스택 실측: 같은 3셀 교정이 **셀별 개별 저장 4점×3건 = 12점 → 일괄 채우기 1건 6점**, 두 경우 모두 **마우스 0점**. N셀로 확장하면 개별 ≈ 5N, 일괄 ≈ N+3(N=100에서 500점 대 103점).
>
> **두 번째 범위 구현을 만들지 않았다.** 앵커는 기존 `state.dragStartCell`, 이동단은 `state.dragEndCell`이고 렌더는 `clipboard.isCellInRange`/`refreshSelectedRangeDiff`가 이미 그 사각형을 그린다. 쓰기 엔진도 기존 `ui.applyValueToSelectedRange`(Ctrl+Enter 경로)를 그대로 쓴다 — 새로 만든 것은 **선택 수단 하나뿐**이다.
>
> ⚠️ **`selectedCellsMap`에 확정(commit)하지 않는다** — Shift+클릭도 하지 않는 동작이고, `applyValueToSelectedRange`는 **맵을 먼저** 읽고 사각형은 폴백으로만 읽는다. 방향키마다 맵에 확정하면 낡은 키보드 사각형이 나중의 Shift+클릭 사각형을 **이겨서**, 사용자가 보는 선택과 실제 덮어쓰는 선택이 달라진다.
>
> ⚠️ **평범한 방향키는 범위를 해제한다**(정리 취향이 아니라 데이터 보호다). 해제하지 않으면 사용자가 방향키로 떠난 사각형이 살아남아 다음 `Ctrl+Enter`가 **본인이 선택했다고 믿지 않는 셀들을 덮어쓴다**. 마우스 경로는 이미 그렇게 동작한다(평범한 mousedown → `clearRangeSelection`) — 키보드가 맞추지 않으면 두 경로가 선택 상태를 두고 서로 다른 말을 한다.
>
> **알려진 한계**: 앵커는 사각형이 없을 때만 포커스 셀에서 새로 잡힌다. 사각형이 살아 있는 채 **프로그램적으로**(`element.focus()`) 포커스를 옮기면 재앵커되지 않는다 — 사람 조작(클릭·방향키)은 둘 다 해제 경로를 타므로 실사용에서는 드러나지 않지만, 스크립트 검증에서는 드러난다(2026-07-30 E2E에서 관측).
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

### 3.2 상호작용 계측기 (`effort_meter.js`) — 핵심가치 #1의 정본 계기

SSOT §1의 정본 계기 **「완료까지의 상호작용 점수」**를 수집하는 **유일한 수집기**입니다. 점수는 `키 1 · 마우스 3 · 컨텍스트 상실 이동 5`, 낮을수록 좋습니다.

> ⚠️ **이 파일이 클라이언트 유일의 수집기입니다.** 다른 페이지에 카운터·세션 id 생성기·라우트 표를 **복제하지 마십시오.** (중복 상수 목록은 U6 라운드에서 6건을 삭제한 전력이 있는 반복 함정입니다.) 페이지별 번들은 각자 모듈 인스턴스를 갖되 **`sessionStorage`를 통해 같은 세션을 공유**합니다.

| 항목 | 내용 |
|---|---|
| 계약 API | `startSession()` · `countKey(n=1)` · `countMouse(n=1)` · `countNav(from,to)` · `snapshot()` · `commit()` · **`commitIfRecorded(응답본문)`**(2026-07-29 수리 라운드) — **총괄 소유**. 이름·형태 변경 금지 |
| 계약 API (2026-07-29 승격) | `installGlobalListeners()`(페이지 전역 키/마우스 수집, 멱등) · `installNavLinkCounting(from)`(`<a href>` 위임 카운트) · `routeFromHref()`/`currentRoute()`/`ROUTES`/**`ROUTE_IDS`**(경로↔라우트 매핑과 **라우트 id 어휘**의 단일 표) · `getConfig()`(진단). **부가 export가 아니라 계약입니다** — 이것들이 없으면 페이지마다 리스너와 경로표를 손으로 복제하게 되고, 그게 바로 이 모듈이 막으려는 중복입니다 |
| 저장 | `sessionStorage['assy.effort']` = `{session_id, key, mouse, nav, nav_preserved}`. **원시 카운트만** 저장하고 배점은 서버가 조회 시점에 적용 — 배점을 바꿔도 과거 데이터가 새 배점으로 재해석됩니다 |
| 전송 | 기존 `PUT /tables/{t}/data/updates`에 **선택 필드** `effort`로 편승. **별도 텔레메트리 요청 없음.** 미계측(필드 없음)은 정상이며 `0`이 아닙니다 — 그래서 **누적이 하나도 없으면 `snapshot()`이 `undefined`를 반환**해 필드가 본문에서 아예 사라집니다(불변식 5) |
| 선언 원천 | `GET /api/effort/config` → `{weights, context_preserving_transitions}`. 페인트 규칙이 `binding`을 서버에서 받는 것과 같은 규율 — **서버가 유일 원천**. 단 **라우트 id 어휘는 클라 소유**(`ROUTE_IDS`)이므로, 서빙된 항목이 존재하지 않는 라우트를 지목하면 클라가 거절하고 큰 소리로 보고합니다(불변식 6) |

**깨지기 쉬운 불변식 6가지:**

1. **성공에만, 그리고 서버가 기록했을 때만 리셋.** 저장 실패 시 카운터를 유지해 계속 누적합니다 — 재시도 공수도 사람의 진짜 공수이기 때문입니다. 시도 시점에 리셋하면 **실패하는 저장이 싸 보입니다.** 2026-07-29 수리 라운드에서 게이트가 하나 늘었습니다: **200도 교정의 증거가 아닙니다.** 이미 같은 값이 들어 있는 셀에 같은 값을 다시 쓰면 서버는 `200 {change_count: 0}`을 주고 **공수 행을 쓰지 않습니다**. 거기서 리셋하면 그 시도에 든 공수가 지워지고, 화면이 안 바뀌는 걸 본 작업자가 제대로 다시 하면 **두 번 시도한 교정 — 제품에서 마찰이 가장 큰 사건이자 이 계기의 존재 이유 — 이 데이터셋에서 가장 낮은 점수를 기록합니다.** 그래서 `commitIfRecorded(응답본문)`이 서버의 `effort_recorded`를 보고 판단하고, 필드가 없으면(구 서버) 종전 동작으로 되돌아갑니다 — 영영 리셋하지 않으면 카운터가 무한히 자라는 그 자체가 결함이기 때문입니다.
2. **같은 탭 새로고침에서 생존.** 교정 도중 새로고침이 사람의 작업을 되돌리지는 않으므로 `sessionStorage`를 씁니다(탭이 닫히면 세션 종료).
3. **기본은 "상실(계산됨)".** 서빙 설정이 없거나·404거나·파싱 불가면 **모든 전이를 계산**합니다. 절대 "0점"으로 fail-open 하지 않습니다 — 목록에서 빠진 전이는 점수를 나쁘게만 만들지만, 잘못 포함된 전이는 **조용히 점수를 미화**합니다. 같은 이유로 **와일드카드(`*`)는 거부**합니다(무해한 리터럴로 남겨두면 설정 작성자가 적용됐다고 오해합니다).
3-bis. **분류는 절대 버리지 않는다** (2026-07-29 총괄 계약 보정). 면제된 전이도 `nav_preserved`로 **계속 셉니다** — `nav`(상실, 점수 대상)와 `nav_preserved`(유지, 현재 0점) 둘 다 원시 카운트입니다. 이 계기는 소급 산출이 불가능하므로, 수집 시점에 조용히 버린 전이는 나중에 판단이 바뀌어도 **영영 복구할 수 없습니다.**
   ⚠️ **여기서 정확히 무엇을 얻는지 (2026-07-29 QA 레인 B 정정 — 종전 서술은 과장이었습니다):** 어느 **버킷**에 들어갈지는 **수집 시점에** 그때의 허용목록으로 확정됩니다. 허용목록을 나중에 바꿔도 **이미 기록된 행은 재분류되지 않습니다.** 조회 시점에 재해석되는 것은 **배점뿐**입니다 — 두 버킷 다 원시 카운트이므로 `weights.nav_preserved`를 올려 과거 데이터를 **재채점**할 수 있습니다. 버리지 않는 것이 지키는 것은 그 재채점 가능성이지, 분류의 되돌림이 아닙니다.
4. **수집은 사용자에게 보이지 않음.** 새 UI·배지·토스트가 없습니다(집계 결과 한 줄은 어드민 Overview에 있습니다 — §5). 리스너는 전부 `capture` + `passive:true`라 **`preventDefault`를 호출할 수 없고**, `stopPropagation`도 하지 않습니다 — 과거 Ctrl+C keydown 분기가 `copy` 핸들러를 굶겼던 사고(§3 주석)를 구조적으로 차단합니다.
5. **부재는 0이 아니다 (보내는 쪽에서도).** 누적이 하나도 없으면 `snapshot()`이 **`undefined`**를 반환하고, `effort: snapshot()`은 `JSON.stringify`에서 키째 사라집니다. 서버는 명시적 0을 **측정된 0점 교정**으로 받아들이므로(그건 의도된 동작입니다 — 진짜 무공수 교정은 의미가 있습니다), 상호작용 없이 나간 저장은 **진짜 0점으로 기록되어 기준선을 유령으로 끌어내립니다**(실측: 진짜 교정 1건 37점 + 유령 1건 → `avg_score` 18.5). 가드를 7개 호출 지점이 아니라 **수집기 안**에 둔 이유는 여덟 번째 호출 지점이 잊을 수 없게 하기 위해서입니다. 판정은 **원시 4카운트**로 하며 점수로 하지 않습니다 — `nav_preserved`만 있는 세션은 오늘 0점이지만 실제로 일어난 일이고, 그 원시 카운트가 바로 재채점의 근거이기 때문입니다.
6. **존재하지 않는 라우트를 지목한 허용목록 항목은 조용히 죽지 않는다.** 서버는 항목의 *형태*만 검증하고 라우트 어휘를 모르므로 오타를 그대로 되돌려줍니다. SSOT가 예시로 든 `{"from":"doe","to":"dt_map"}`은 **아무것도 면제하지 못합니다**(실제 id는 `map_editor`·`map_editor:material`). 문제는 그 효과 — "전부 계속 계산됨" — 가 **정상 동작과 똑같이 보인다**는 점입니다. 그래서 클라가 `ROUTE_IDS`로 대조해 **거절 + `console.error` + `getConfig().rejected_transitions` 노출**을 합니다. 거절된 항목은 계산 쪽에 남으므로 편향은 과대계상(안전) 방향입니다. ⚠️ 새 서브컨텍스트로 `countNav`를 부르면 **같은 변경에서 `ROUTE_IDS`에도 등록**해야 합니다.
   같은 규율로 **항목 형식은 서버가 받는 것만 받습니다** — `{"from":..., "to":...}` 객체뿐이고, `"from>to"` 문자열 축약은 **거절**합니다. 서버(`resolve_context_preserving_transitions`)가 dict만 받고 나머지를 버리므로, 클라만 관대하면 **작성자가 쓴 항목을 한쪽은 지키고 한쪽은 버리면서 아무도 알려주지 않는** 상태가 됩니다. 생산자보다 관대한 소비자는 관용이 아니라 **선언되지 않은 두 번째 계약**입니다.
7. **관측 가능성은 소스가 아니라 빌드 산출물에 있어야 한다.** `getConfig()`는 `client2/src` 안에 호출자가 없어 번들러가 **트리셰이킹으로 dist에서 지워 버렸습니다**(실측: dist에서 `loaded:` 0건). 그러면 운영 현장에서 "허용목록이 비었다"와 "설정을 못 받았다"를 구별할 수 없는데, 그 구별이야말로 fail-closed 설계가 기대는 유일한 근거입니다. 이제 `startSession()`이 `window.__assyEffort = { getConfig, snapshot, ROUTE_IDS }`를 게시합니다(실제 참조이므로 셰이킹 불가) + 설정 fetch 실패 시 `console.warn` 1줄. 화면 요소는 여전히 0개입니다.

**계측 지점 — 교정 쓰기 경로 전부**에 `effort` 첨부 + **서버가 기록했을 때만** `commitIfRecorded()`:

| 페이지 | 쓰기 경로 |
|---|---|
| 메인 그리드 | `api.js`(단건 편집) · `main.js`(Tx 일괄 적용) · `ui.js`(범위 값 채우기) · `clipboard.js`(붙여넣기, 셀 비우기) — **5경로** |
| Enrichment 컨베이어 | `enrichment.js` `saveCurrent` — **1경로**(2026-07-29 추가. 결손 보정도 교정 쓰기이므로 범위 안이며, 여기가 제품에서 **가장 공수가 적은 교정 표면**일 가능성이 높은데 미계측이면 그걸 증명할 수단이 없습니다) |
| 맵 에디터 | `map_editor.js` Push — **1경로**(map-pm 소관) |
| 읽기 전용 화면 (2026-07-29 추가) | `admin.js` · `graph_viewer.js` · `trace.js` — **교정 쓰기 0경로**이므로 `effort` 페이로드를 싣는 곳이 없습니다. 대신 `startSession`+`installGlobalListeners`+`installNavLinkCounting`만 배선합니다. 이유는 **대칭**입니다: 종전에는 `grid → graph`는 세고 `graph → grid`는 안 세서, 읽기 화면으로 나갔다 돌아오는 왕복이 **실제 비용의 절반만** 기록됐습니다(실측: `/graph.html`에서 🏠 Main 클릭 → 카운터 바이트 단위로 동일). 미화 방향이고, 다시 모을 수 없는 기준선에서 그건 불변식 3이 금지하는 방향입니다 |

**이동 계측:** 그리드 — 내비 앵커 4건(위임) + Enrichment 배지 + 테이블 전환 + 뷰모드 전환 + `navigateToLog` + 추적 새 탭. Enrichment — 「메인으로」 앵커 2건(위임) + 규칙 전환. 어드민·그래프·추적 — 내비 앵커(위임) 전량.

> ⚠️ **테이블/규칙 전환은 `switchTable()`·`selectRule()` 안이 아니라 사용자 핸들러에서 셉니다.** 두 함수는 부팅 자동선택·딥링크·`navigateToLog`에서도 호출되는데 그건 사용자가 이동한 것이 아니라서, 함수 안에서 세면 오계수가 납니다. (새로고침 버튼처럼 같은 대상을 다시 읽는 것도 이동이 아니므로 세지 않습니다.)

> 카운트 규칙(둘 다 **미화되지 않는 방향**으로 선택): 마우스는 `click`이 아니라 **`mousedown`**(범위 드래그는 `click`을 발생시키지 않지만 실제 누름 1회입니다), 키는 **자동 반복 포함 전부**이되 **단독 수식키**(Shift/Ctrl/Alt/Meta)는 제외(코드는 비수식키에서 1회 계산).
>
> 검증 하니스: `client2/tests/effort_meter_harness.mjs` (vm 샌드박스, node_modules 불필요, **131 단언**). **변이 검사 8종 포함** — ① `snapshot()`이 리셋하도록 ② 설정 실패 시 fail-open 하도록 ③ 면제 전이를 버리도록 ④ 빈 스냅샷을 0으로 실어 보내도록 ⑤ `effort_recorded`를 무시하고 항상 리셋하도록 ⑥ 미지의 라우트 id를 조용히 받아들이도록 ⑦ 문자열 축약을 다시 받아들이도록 ⑧ 진단을 `window`에 게시하지 않도록 일부러 고장 낸 버전을 넣어, 하니스가 **실제로 잡아내는지** 확인합니다. 별도로 **§8b 배선 감사**가 소스 레벨에서 전 페이지를 훑습니다 — 교정 경로가 bare `commit`을 다시 import 하는가, 어떤 페이지가 수집기를 아예 import 하지 않는가(B-F1 재발), 읽기 화면이 자기 라우트가 아닌 id로 세는가. 이 감사도 세 가지 역주입으로 자기 점검합니다. 변이가 소스 드리프트로 적용되지 않으면 **에러를 던집니다** — 조용한 no-op이 되면 "고장 난 버전이 통과"해 검사가 무의미해지기 때문입니다(실제로 한 번 발생해 이 가드를 넣었습니다). 맵 에디터 배선은 `client2/tests/effort_instrument_harness.mjs`(28 검사, 변이 9종 — 실제 `pushMapData` 본문을 소스에서 들어올려 실행).

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
| **Overview** (첫 화면) | **재교정률 한 줄 + 교정 공수 한 줄** + 헬스 4카드(File/Chain/AutoUpdate/Enrichment — 상세 수치+최근 이벤트+탭 딥링크), 전폭 레이아웃 |
| **File Ingestion** | 인제션 로그(필터/정렬/페이지) + Workspaces(기본 접힘·요약) + 실패 진단→커스텀 파서 편집 딥링크 |
| **Chain** | Rules 현황 + **Chain 실패(Outbox Transactions)** 재시도 + Mappers(행별 🛠️ Edit) + 실패 진단→맵퍼 편집 딥링크 |
| **Auto Update** | 상태/Run Now + **산출물 인제션 실패 연계**(auto-update 대상 ∩ 파일 실패 교집합) |
| **Enrichment** | 규칙 표 + 결손 카운트 배지 + Queue 딥링크(`enrichment.html?rule=`) — 규칙 편집은 read-only 안내(CRUD API는 백로그) |

- **핵심가치 #1 계기 두 줄 (Overview 상단, `renderRecorrection` + `renderEffort`, 갱신은 `refreshCoreValueLines` 하나)**: 두 줄은 **같은 `/dashboard/summary` 응답 한 번**에서 나온다.
  - **재교정률**: 사람이 같은 셀을 두 번 이상 고친 비율 — **보조 계기**([backend](./backend.md#재교정률-dashboardsummary--recorrection) · 2026-07-29 강등).
  - **교정 공수** (2026-07-29 수리 라운드 신설): 한 교정을 끝내기까지의 상호작용 점수 = SSOT §1의 **정본 계기**. `avg_score`와 함께 **커버리지(`measured_ratio`)를 같은 줄에** 적는다 — 이 계기는 클라가 보내 줄 때만 쌓이고 서버는 기록 예외를 삼키므로, **커버리지가 화면에 없으면 수집이 통째로 끊겨도 아무 신호가 없다.** 기준선을 잴 창이 한 번뿐이라 그 신호가 전부다. 상태별 문구가 서로 다른 것이 요점이다: `unavailable_reason`이 오면 **그 사유를 그대로**, `measured_ratio === 0`(사람 교정은 있는데 계측 0건)이면 **수집 중단 경고**(danger — 이 줄에 한해 사유 문장까지 붉게), 응답에 `effort` 필드 자체가 없으면 "**서버가 보고하지 않음**"(구 서버 — "교정이 없었다"고 지어내지 않는다), 표본이 정말 없으면 "교정 없음". 커버리지 50% 미만 또는 미상이면 "대표값으로 읽지 말 것" + warn 톤.
  - 둘 다 **카드도 패널도 모달도 아닌 한 줄**이고, 값 옆에 **분모를 항상 같이 적는다**(재교정률은 표본 100 미만이면 "추세로 읽지 말 것" + muted 톤). 지켜야 할 두 가지:
  1. **자동 갱신 루프(`fetchOverview`)에 태우지 않는다.** 출처 `/dashboard/summary`는 테이블마다 `count(*)`를 도는 무거운 엔드포인트다(실측 ~1.5s). `await` 없이 던지고 **5분(`RECORRECTION_MIN_INTERVAL_MS`) 간격**으로만 갱신한다 — 본문 카드 렌더가 이 요청을 기다리지 않는다. 두 줄이 한 요청을 공유하므로 스로틀도 하나다.
  2. **`rate_pct=null`·`avg_score=null`은 "0"이 아니라 "—"로 렌더한다.** 표본 없음과 조회 실패를 정상 0으로 위장하면 지표가 거짓말을 한다. 그리고 **"—"에는 반드시 사유가 붙는다** — 사유 없는 대시는 정상(표본 없음)과 장애(수집 중단)를 구별하지 못하는데, 이 둘은 정반대 대응을 요구한다.
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
