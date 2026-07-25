# 🖼️ Frontend Architecture

> **Status:** 🟢 Living | **Last-verified:** 2026-07-25 | **Owner:** UI / Excel Interaction
> **Source-of-truth:** `client2/src/*`, `client2/vite.config.js`, `client/desktop_wrapper.py`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

---

## 1. 개요: 웹앱 + 얇은 데스크톱 셸

메인 클라이언트는 **`client2`(웹)**이며, 데스크톱 앱은 이를 감싸는 QtWebEngine 셸입니다.

- **`client2/`** — Vite 멀티페이지 앱(4엔트리), **Vanilla ESM JavaScript(프레임워크 없음)**, JS ~10,300줄.
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
| `index.html` | `src/main.js` | 데이터 그리드(메인) |
| `admin.html` | `src/admin.js` | 어드민 대시보드(Monaco CDN) |
| `map_editor.html` | `src/map_editor.js` | 웨이퍼 맵 에디터 |
| `enrichment.html` | `src/enrichment.js` | Enrichment Queue 컨베이어(결손 보정 워크리스트) |

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
| `main.js` | 1791 | 메인 페이지 오케스트레이터: init, 이벤트 바인딩, 소스 모달, 스마트 페이스트, Tx 모드 apply/discard |
| `state.js` | 49 | **단일 싱글턴 상태 저장소**(gridApi, 현재 테이블/스키마, ws, 선택/드래그, 페이지캐시, `pendingTxEdits`) |
| `dom.js` | 55 | `getElementById` 지연 게터 모음(`elements`) |
| `api.js` | 418 | REST 계층: health, loadTables, switchTable, loadSchema, fetchData(페이지캐시), handleCellEdit(Tx 스테이징+숫자검증), addRows, deleteSelectedRows |
| `websocket.js` | 249 | 실시간 동기화: 지수 백오프 재연결, `batch_row_{create,upsert,delete}`/`batch_refresh_required`를 AG-Grid 트랜잭션으로 적용(셀 플래시) |
| `grid.js` | 526 | AG-Grid 설정/렌더: `buildColumnDefs`, `renderGrid`, `ensureCellObject`(중첩 셀 `{value,is_overwrite,priority_source}` 정규화) |
| `clipboard.js` | 788 | 엑셀형 범위 선택/클립보드: hit-test, `commitDragSelection`, `getRangeSelectedTSV`, paste, `clearSelectedCells` |
| `timeline.js` | 718 | 감사 히스토리 패널: `loadHistory`, `appendHistoryLocally`, 로그→그리드 점프 네비게이터 |
| `ui.js` | 408 | 공용 UI 반영: `updateTxModeUI`, `setTransactionFilter`, `applyValueToSelectedRange`, Enrichment 배지(`updateEnrichmentBadge`), 페이지캐시 유지, unload 경고 |
| `utils.js` | 195 | `getLocalTimeString`, `showToast`(window 부착), 인제션 진행 위젯 |
| `theme.js` | 92 | 듀얼 테마 전환(`initTheme`/`toggleTheme`/`syncAgGridThemeClasses`) — 토큰 SSOT는 `tokens.css` |
| `config.js` | 5 | 환경 설정: `API_BASE`/`WS_URL`(5173→8080), `CURRENT_USER`, `pageLimit=1000` |
| `admin.js` | 1433 | 어드민(§5) |
| `map_editor.js` | 2771 | 맵 에디터(§4) |
| `enrichment.js` | 754 | Enrichment 컨베이어: 규칙 선택(`loadRules/selectRule`), 워크리스트(`fetchWorklist`), 입력 흐름(`onInputKeydown/saveCurrent` → PUT `/data/updates`), 참조 패널(`initReferencePanel/loadActiveReference`, stale 가드) |

> `counter.js`는 Vite 템플릿 잔재(미사용).
> **상태 관리 주의:** `state.js`는 리액티브 스토어가 아닌 **평범한 싱글턴**. 변조 후 명시적 UI 리프레셔를 호출하는 수동 패턴. `admin.js`/`map_editor.js`는 `state.js`를 임포트하지 않고 자체 모듈 지역 변수를 사용.

---

## 4. 맵 에디터 (`map_editor.js`, ~2771줄)

| 영역 | 대표 함수 |
|---|---|
| 렌더링 | `renderGridCanvas`/`scheduleRenderGridCanvas`, `updateCellStyles`, `renderLegendTable`, `updateNotchPosition` |
| 좌표 변환 | `getPhysicalCoords`/`getCellFromPhysicalCoords`, `getVisualCoords`, `getWaferBoundingBox`, `getTransformedPhysicalConfig`, `isCellInsideWafer{,Fast}` |
| 드래그 선택/페인팅 | `initMouseDragEvents`, `handleCellClick`, `fillSelectedCells`, `remapGridValues`, `autoPaintE1E2` |
| 엑셀 복사 | `copyGridToExcel()` (~2616) — TSV 클립보드 |
| 메타/레전드 | `renderMetadataInputs`, 프리셋 `/api/map-presets`, 레전드 `localStorage`(`map_legend_{table}`) |
| 데이터 동기화 | `loadExistingMap()`(REST pull), `pushMapData()`(REST push) |

> **정정:** 맵 에디터는 **WebSocket을 사용하지 않습니다.** REST pull/push + localStorage. 실시간 WS는 메인 그리드(`websocket.js`)에만.

상세 규격: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) · [map_editor/](../map_editor/README.md)

---

## 5. 어드민 (`admin.js`, ~1433줄)

탭 구동 대시보드(`currentTab`: outbox · file · workspace · chain · mapper · autoupdate · editor):

- **Ingestion Outbox** — 실패/대기 트랜잭션 목록 + 재시도(`retryTransaction`, `retryAllFailed`)
- **File / Workspace / Chain / Mapper** — 각 목록 렌더 + 선택
- **Auto-update** — 스크립트 목록 + `runAutoUpdateNow(table, script)`
- **Code editor** — **Monaco**(cdnjs `monaco-editor@0.39.0`), 파일트리 브라우저, `saveScriptCode`
- **System configs** — `reloadSystemConfigs()`

---

## 6. 백엔드 계약

- REST + WebSocket at `127.0.0.1:8080` (FastAPI). 엔드포인트: [backend.md](./backend.md)
- 셀 데이터 형태: `data[col] = {value, is_overwrite, priority_source}` (grid.js `ensureCellObject`가 정규화)
