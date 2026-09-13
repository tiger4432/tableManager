# client-pm 보고 — FEATURE_CHECKLIST TODO 10건 실확인 + frontend.md 동기화 (2026-07-25)

본체 main 트리, 문서 전용 작업. 코드·config·`tokens.css` 무접촉. 빌드 불필요. **커밋 안 함(총괄 수행).**

## 1. TODO별 확인 결과 (각 1줄, 소스 근거)

| # | 항목 | 확인 결과 | 근거 |
|---|---|---|---|
| 1 | 소스 모달 트리거 | 셀/드래그 범위 **우클릭** → 커스텀 컨텍스트 메뉴 "📚 데이터 원천(Sources) 관리" (버튼/단축키 없음) | `grid.js` onCellContextMenu ~468 · `main.js` ~516 · `index.html` #custom-context-menu |
| 2 | 핀 UI 절차 | 모달 내 소스 행별 "📍 Pin" 버튼 — 클릭=핀("📌 Pinned"), 재클릭=해제(토글); 범위 선택 시 선택 셀 전체 배치 핀 | `main.js` ~1219/~1350 |
| 3 | 소스 삭제/실패 표출 | 소스 행별 "🗑️ Delete" → `confirm()` → 삭제(범위면 배치 API); **실패는 하단 상태 로그(performanceLog)에 "❌ Failed to..." 텍스트** — 토스트/모달 아님 | `main.js` ~1253/~1385 |
| 4 | 범위 일괄 적용 트리거 | 범위 선택 → 셀 편집 시작 → **Ctrl+Enter** 로 편집값을 범위 전체 적용(시스템 컬럼 제외, Tx 모드면 스테이징) | `grid.js` suppressKeyboardEvent ~287 → `ui.applyValueToSelectedRange` |
| 5 | 스마트 페이스트 | **행 수 임계 없음·자동 발동 아님** — 우클릭 메뉴 수동 실행; 모달은 클립보드 MIME 2개 이상일 때 **전송 포맷 선택**(Plain/HTML/RTF/CSV/JSON) 용도; 선택 내용을 파일화해 `/upload` 인제션 경로 전송. (`smart-paste-btn` 툴바 버튼은 HTML에 미존재 — dom.js 게터만 잔존) | `main.js` smartPasteViaIngestion ~1425/모달 ~1518 |
| 6 | 컬럼 선택 유지 범위 | `gridApi.setColumnsVisible`만 사용(localStorage 미저장) — **새로고침 시 초기화**, 테이블 전환 시 columnDefs 재구축으로 유지 비보장 | `main.js` ~604–674 |
| 7 | view-mode 옵션 | 2종: `pagination`("📄 Paging" — 페이지 컨트롤 표시) / `infinite`("♾️ Scroll" — 컨트롤 숨김, 스크롤 하단 도달 시 청크 추가 로드) | `index.html` :123 · `grid.js` updateViewModeUI :66 |
| 8 | 결손 배지 표시 조건 | 현재 테이블이 규칙의 **source_table 또는 derived_table 어느 쪽이든 일치하면 표시(원본 화면 포함)** + target_fields blank 카운트>0; 실패/0건은 무음 숨김(TTL 캐시+WS 디바운스) | `ui.js` findEnrichmentRule ~325 / updateEnrichmentBadge ~331 |
| 9 | 맵 에디터 버튼 | 로드 "📂 Load Existing Map"(좌측 패널, 방식 선택 모달: Standard/Current/Cancel) · 저장 "⚡ Push Map Data"(작업영역 툴바) → 메타 미입력 시 alert 차단 + **`confirm("총 N건... 덮어쓰기 적재(Clean Replace)...")`** · 엣지: "🔍 Select Tools" 드롭다운(Select E1/E2, ⚡ Auto-Paint E1/E2) · 엑셀 복사: "🛠️ Edit Grid" 드롭다운 → "📋 Copy to Excel" | `map_editor.html` :53/:214–234 · `map_editor.js` ~2243/~2340 |
| 10 | 페이지별 테마 토글 | **4페이지(index/admin/map_editor/enrichment) 전부** 헤더/툴바에 `data-theme-toggle` 버튼 존재 | 각 html grep 실확인(:83/:501/:22/:764) |

**문서가 실제와 달랐던 2곳 정정**: (a) 스마트 페이스트 — "대량 Ctrl+V 시 자동 모달" 서술을 수동 트리거+포맷 선택 모달로 교체(§1.1·§2.3). (b) 결손 배지 — "파생 테이블 선택 시" 한정 서술을 원본/파생 양쪽 표시로 교체(§1.6). TODO 주석 16개소 전량 제거(grep 0건 확인).

## 2. frontend.md 변경 요지 (Client PM 소유 리빙 문서)

- §2 진입점 표 **3→4엔트리**: `enrichment.html`/`src/enrichment.js` 행 추가 (`vite.config.js` 실확인).
- §3 모듈 표: 줄수 CODE_MAP §7 동기화(main 1791·api 418·ws 249·ui 408·admin 1433·map_editor 2771 등) + `enrichment.js`(754)·`theme.js`(92) 행 추가, ui.js 책임에 Enrichment 배지 반영.
- §1 총 줄수 ~9,200→JS ~10,300(4엔트리 표기), §4/§5 헤더 줄수·`copyGridToExcel` 라인 참조(:2495→~2616) 정정.
- Last-verified **2026-07-25** 스탬프.

## 3. 부수 갱신

- 히스토리 기록: `docs/history/20260725_160000_feature_checklist_client_todos_verified.md` + `gen_index.py` 재생성(**187 entries**).
- `docs/README.md` 이력 건수 186→187 정정(하드코딩 카운트 — doc-keeper의 "건수 표기 제거 고려" 제안에 동의).

## 4. PROJECT_STATUS 반영 초안 (직접 수정 안 함 — 총괄 반영)

```markdown
| 2026-07-25 | 문서/QA | **FEATURE_CHECKLIST client-pm TODO 10건 소스 실확인 보강** — 소스 모달(우클릭 메뉴)·핀/삭제 UI·Ctrl+Enter 범위 적용·스마트 페이스트(수동 트리거, 포맷 선택 모달)·결손 배지(원본/파생 양쪽 표시) 등 정정 + frontend.md 4엔트리 동기화(Last-verified 07-25) | [20260725_160000](../history/20260725_160000_feature_checklist_client_todos_verified.md) |
```

## 5. 교훈 제안 (총괄 검수 후 memory 반영)

- **제안**: `dom.js` 게터가 있어도 실제 HTML에 해당 id가 없을 수 있다(예: `smart-paste-btn` — `if` 가드로 무음 스킵). UI 트리거를 문서화할 때는 dom.js/JS 핸들러만 믿지 말고 **html에 id 실존 여부까지 grep**으로 확정할 것.

## 6. 인계 요약

체크리스트는 이제 클라 UI 10건 모두 실측 절차 기준. 남은 연관 건: SSOT §3 "진입점 3개" 문구 정정(총괄 소유 — doc-keeper 초안 대기), 첫 QA 회차 실행 방식 확정.
