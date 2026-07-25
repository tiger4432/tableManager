# FEATURE_CHECKLIST client-pm TODO 10건 실확인 보강 + frontend.md 4엔트리 동기화

- **일시:** 2026-07-25 16:00
- **주체:** client-pm (총괄 위임)
- **영역:** 문서 전용 (코드 무변경)
- **산출물:** `docs/qa/FEATURE_CHECKLIST.md` 보강, `docs/architecture/frontend.md` 동기화

## 배경

doc-keeper가 신설한 `docs/qa/FEATURE_CHECKLIST.md`에 클라이언트 UI 세부 동작을 확신할 수 없어 남긴 `<!-- TODO: client-pm 확인 -->` 10건을, client-pm이 소스(CODE_MAP §7 → 해당 구간만 Read) 기준으로 실확인해 정확한 절차/조건으로 교체.

## 확인 결과 요약 (소스 근거)

1. **소스 모달 트리거** — 셀/범위 **우클릭** → 컨텍스트 메뉴 "📚 데이터 원천(Sources) 관리" (`grid.js` onCellContextMenu ~468, `main.js` ~516, `index.html` #custom-context-menu).
2. **핀 UI** — 모달 내 소스 행별 "📍 Pin" 버튼 토글(핀 시 "📌 Pinned"), 범위 선택 시 배치 핀 (`main.js` refreshSourcesList ~1219/~1350).
3. **소스 삭제** — 소스 행별 "🗑️ Delete" → `confirm()` → 삭제, 범위면 배치 삭제. **실패 표출은 하단 상태 로그(performanceLog) "❌ Failed to delete cell source"** — 토스트/모달 아님 (~1253/~1385).
4. **범위 일괄 적용** — 범위 선택 상태에서 셀 편집 중 **Ctrl+Enter** (`grid.js` defaultColDef.suppressKeyboardEvent ~287 → `ui.applyValueToSelectedRange`).
5. **스마트 페이스트** — **행 수 임계 없음, 자동 발동 아님.** 우클릭 메뉴 "📋 파서로 붙여넣기" 수동 실행. 모달은 클립보드에 텍스트 계열 MIME이 2개 이상일 때 **포맷 선택**(Plain/HTML/RTF/CSV/JSON) 용도. (`main.js` ~1425; toolbar `smart-paste-btn`은 HTML에 미존재 — 컨텍스트 메뉴가 유일 트리거)
6. **컬럼 선택 유지 범위** — `gridApi.setColumnsVisible`만 사용, localStorage 미저장 → 새로고침 시 초기화, 테이블 전환 시 유지 비보장 (`main.js` ~604-674).
7. **view-mode-select** — `pagination`("📄 Paging") / `infinite`("♾️ Scroll", 스크롤 하단 청크 추가 로드) 2종 (`index.html` :123, `grid.js` updateViewModeUI).
8. **결손 배지** — 현재 테이블이 규칙의 **source_table 또는 derived_table 어느 쪽과 일치해도** 표시(원본 화면 포함), blank 카운트>0 조건, 실패 시 무음 숨김 (`ui.js` findEnrichmentRule ~325/updateEnrichmentBadge ~331).
9. **맵 에디터 버튼** — 로드 "📂 Load Existing Map"(+방식 선택 모달 Standard/Current/Cancel), 저장 "⚡ Push Map Data" → 메타 미입력 alert 차단 + `confirm("...덮어쓰기 적재(Clean Replace)...")`. 엣지: "🔍 Select Tools" 드롭다운(Select E1/E2, Auto-Paint E1/E2). 엑셀 복사: "🛠️ Edit Grid" 드롭다운 → "📋 Copy to Excel" (`map_editor.html`, `map_editor.js` pushMapData ~2243/confirm ~2340).
10. **테마 토글** — **4개 페이지(index/admin/map_editor/enrichment) 전부** 헤더/툴바에 `data-theme-toggle` 버튼 존재 (각 html 실확인).

문서 서술이 실제와 달랐던 2곳(스마트 페이스트 "대량 붙여넣기 시 자동 모달" 서술, 결손 배지 "파생 테이블 선택 시" 한정 서술)은 실제 동작에 맞춰 정정.

## frontend.md 동기화 (Client PM 소유 리빙 문서)

- §2 진입점 표 3→**4엔트리**(`enrichment.html`/`src/enrichment.js` 추가 — `vite.config.js` 실확인).
- §3 모듈 표 줄수 CODE_MAP 동기화 + `enrichment.js`(754)·`theme.js`(92) 행 추가, `ui.js` 책임에 Enrichment 배지 반영.
- §1 총 줄수 ~9,200 → JS ~10,300, §4/§5 헤더 줄수·`copyGridToExcel` 라인 참조 정정.
- Last-verified 2026-07-24 → **2026-07-25**.

## 아키텍처 영향

없음(문서 전용, 코드·config 무접촉).

## 다음 단계

1. 첫 QA 점검 회차 실행(체크리스트 사본 운용).
2. SSOT §3 "진입점 3개" 문구는 총괄 소유 — doc-keeper 보고서의 4엔트리 정정 초안 반영 대기.
