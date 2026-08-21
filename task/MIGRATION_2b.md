# 2b 마이그레이션 지시문 — 우측 광폭 참조 그리드 + 컬럼별 필터 행

> **출처:** 소유자가 claude.ai/design 프로젝트 「데이터 그리드 UI 목업」에서 준 지시문.
> 이 파일은 그 정본의 **사본**이다 (2026-08-21, 디자인 세션이 받아 적음).
> 원본 목업 정본은 같은 프로젝트의 `Main Grid Mockup.dc.html` 의 2b.

대상: `client2` 메인 그리드 화면(`index.html` + `src/main.js` 계열).
목업 정본: `Main Grid Mockup.dc.html` 의 2b.
전제: **서버 계약 변경 0** 을 목표로 한다. 새 엔드포인트를 만들지 않고, 이미 있는 `/schema`·`/data`·`/enrichment/rules/{r}/references/{i}`·`PUT /tables/{t}/data/updates` 만 쓴다.

원칙 셋 (설계 의도이므로 구현 중 흔들리면 여기로 돌아온다):

1. **참조뷰는 읽는 패널이 아니라 «또 하나의 그리드»다.** 값을 넣는 수단은 버튼이 아니라 범위 선택 → `Ctrl+C` → 메인 그리드에서 `Ctrl+V` 다. 채우기 버튼·확정 버튼을 만들지 않는다.
2. **열 순서가 계약이다.** 참조 그리드의 후보 열 이름·순서 = 붙여넣기 대상 열 순서. 어긋나면 붙여넣기 전에 화면이 말한다.
3. **검색은 컬럼별이다.** 전역 입력 하나가 아니라 컬럼 헤더 아래 floating filter 행이고, 걸린 필터는 헤더의 칩으로 남는다.

---

## Phase 1 — 컬럼별 필터 행 (AG-Grid floating filter)

**손대는 파일:** `src/grid.js` · `src/api.js` · `index.html` · `src/style.css`

1. `buildColumnDefs()` 의 `colDef` 에 `floatingFilter: true` 를 추가한다. 시스템 컬럼(`isSystem`)은 `filter: false` + `floatingFilter: false` — 지금 `editable: false` 로만 막혀 있어 필터 칸이 생기면 «읽기 전용인데 필터는 된다»는 두 번째 어휘가 생긴다.
2. `defaultColDef` 에 `floatingFilterComponentParams: { suppressFilterButton: true }`. 헤더 높이는 `floatingFiltersHeight: 28` 로 고정한다(목업 실측값).
3. **가상 조인 컬럼(`joinResolvedColumn`)의 필터 정의는 손대지 않는다.** 이미 `JOIN_RESOLVED_FILTER_OPTIONS` 6종 + `agTextColumnFilter` 로 옳고, 그 이유(서버가 `cast(..., String)` 로 평가하므로 숫자 술어는 거짓말이 된다 / `blank`·`notBlank` 는 아무것도 못 고른다)는 그대로 유효하다. floating filter 는 그 정의를 그대로 상속하므로 **추가 작업 0**이다.
4. **필터 칩.** `onFilterChanged` 에서 `api.getFilterModel()` 을 읽어 헤더 좌측(현행 `#global-search` 자리)에 칩을 렌더한다. 칩 문구는 `<COLUMN> <filterType> <값>`, 가상 조인 컬럼은 이름 뒤에 `⇲`. 칩의 `✕` 는 `api.setColumnFilterModel(colId, null)` → `api.onFilterChanged()`. 「전체 해제」는 `api.setFilterModel(null)`.
5. **서버 왕복.** 필터 모델 → 서버 질의 변환은 **기존 검색 경로를 재사용**한다. ⚠️ 확인 필요: `api.js` 의 검색 드롭다운(`?cols=`)은 `state.currentColumns` 만 훑으므로 가상 조인 이름이 그 목록에 없다(`frontend.md` §3.4). 즉 **가상 컬럼 필터는 `?cols=` 로 보내면 조용히 빠진다** — 서버의 override 경로(`main.get_column_filter_condition`)로 가는 파라미터에 실어야 한다. 이 한 갈래를 먼저 실측하고, 안 되면 그 컬럼의 floating filter 를 disabled 로 두되 **이유를 헤더 툴팁에 적는다**(작동하지 않는 필터 칸이 있는 것이 없는 것보다 나쁘다).
6. `#global-search` 는 **삭제하지 않고** 칩 영역으로 대체하되, 다중 컬럼 자유 검색이 실제로 쓰이고 있는지 먼저 확인한다(로그/사용자). 쓰이고 있으면 칩 영역 우측에 좁게 남긴다.

**수락 기준:** 컬럼 12개에 각각 값을 넣어 `Matches:` 가 바뀐다 · 가상 조인 컬럼에서 `equals 미상` 이 미해결 행 수(현재 4,052)를 낸다 · 칩 `✕` 로 그 필터만 해제된다 · 시스템 컬럼에는 필터 칸이 없다.

---

## Phase 2 — 사이드바를 640px 4탭으로

**손대는 파일:** `index.html` · `src/style.css` · `src/timeline.js` · `src/enrichment_reference_view.js`

1. `.history-sidebar { width: 400px }` → `640px`, 그리고 `#main-split-resizer` 드래그 폭을 `localStorage['assy.sidebarWidth']` 에 영속화한다(F5 후 폭이 돌아가면 넓힌 의미가 없다).
2. 탭 순서를 **참조 그리드 · Global · Cell · Row** 로 바꾼다. 현행 `#tab-reference` 는 마지막이고 `display:none` 기본인데, 2b 에서는 **규칙이 있는 테이블에서 첫 탭이자 기본 활성**이다 — `syncReferenceViewRule()` 이 규칙을 찾으면 탭을 노출하는 것에서 **그 탭을 선택**하는 것까지 가게 한다. 규칙이 없으면 종전대로 숨기고 Global 이 기본.
3. 탭 4개는 `.history-tabs` 의 pill 스타일 대신 640px 폭에 맞는 **밑줄형 세그먼트**(목업: `box-shadow: inset 0 -2px 0`)로 간다. `.tab-btn` 을 고치지 말고 `.history-tabs--wide` 변종을 추가한다 — 같은 클래스가 두 폭을 겸하면 400px 로 되돌릴 때 둘 다 깨진다.
4. 메인 그리드는 이 폭에서 **열 3개가 밀린다**(목업은 `c_bn`·`event_time`·`core_product` 를 밀고 헤더 우단에 `+3열 →` 를 적는다). 이것을 **가리지 말고 표시한다** — 스크롤로 도달 가능하다는 사실을 화면이 말하지 않으면 「열이 사라졌다」로 읽힌다.

**수락 기준:** 640px 에서 탭 4개 라벨이 잘리지 않는다 · 폭이 새로고침 후 유지된다 · 규칙 없는 테이블에서 참조 탭이 없고 Global 이 활성 · 밀린 열 수가 실제 밀린 수와 같다.

---

## Phase 3 — 참조뷰를 그리드로 (여기가 이 마이그레이션의 본체)

**손대는 파일:** `src/enrichment_reference_view.js` · `src/tsv.js`(재사용만) · `src/style.css` · 규칙 선언(`enrichment_rules`)

### 3.1 선언에 «채울 열»을 추가한다

참조뷰 선언(`reference_views[i]`)에 `fill_targets: ["dt_lot", "dt_slot"]` 를 더한다. 이 배열이 **열 순서 계약의 유일한 원천**이다.

- 패널은 `fill_targets` 를 **선언된 순서 그대로, 서로 인접하게** 그린다. 다른 열은 그 앞/뒤에 둔다.
- 정렬 띠 문구도 이 배열에서 만든다. 문구를 만드는 함수 안에 열 수를 가르는 분기를 두지 않는다(arity 는 배열 길이가 곧 답이다 — `map_editor2` 의 `decisionKeyOf` 라운드가 같은 결함을 두 번 고쳤다).
- `fill_targets` 미선언 규칙은 **종전 표 렌더로 폴백**한다. 선언 없이 추측해서 열을 재배치하면 붙여넣기가 조용히 어긋난다.

### 3.2 렌더러 교체

`render(results)` 의 `<table class="reference-view-table">` 를 그리드 마크업으로 바꾼다. 필요한 것만:

- 행 번호 거터 + 헤더 행 + (선택) 컬럼별 필터 행. 헤더/거터/행 높이는 메인 그리드와 같은 30/28px.
- `fill_targets` 열은 헤더에 순번(`①②`)과 accent 배경, 본문은 `font-mono`.
- **범위 선택**: 로컬 모델 하나(`anchor`/`end` = `{row, col}`)로 드래그와 `Shift`+방향키를 받는다. 렌더는 `.custom-range-selected` 를 재사용한다 — 새 색을 만들지 않는다.
- `requestSequence` 세대 가드는 **그대로 유지**한다(늦게 온 응답이 새 선택을 덮는 부류의 결함).

### 3.3 복사 — clipboard.js 를 import 하지 않는다

`enrichment.js` 가 `clipboard.js` 를 부르지 않은 것이 설계였다(그 모듈이 `grid.js`·`state.js`·`dom.js`·`ui.js` 를 직접 import 하므로 앱 모듈 그래프가 딸려 온다). 여기서도 부르지 않는다. 대신:

- 직렬화는 **`tsv.js` 를 재사용**한다. 두 번째 TSV 구현을 만들지 않는다(클립보드 경로와 회사 양식 왕복이 공유하는 유일한 구현이라는 성질을 깨지 말 것).
- `copy` 핸들러는 패널 안에서만 동작한다. 🔴 **`clipboard.js` 의 문서 레벨 `copy` 핸들러는 선택이 남아 있으면 «항상» 자기 TSV 로 덮어쓴다** — `installReferenceKeyboardIsolation` 이 이미 이 이유로 존재한다. 두 방법 중 하나를 고르고 하네스로 고정한다:
  (a) 패널 핸들러에서 `stopImmediatePropagation()` (등록 순서 의존 — 순서를 하네스가 단언해야 한다), 또는
  (b) `clipboard.js` 의 핸들러 첫 줄에 `if (elements.referenceView?.contains(e.target)) return;` 가드. **(b) 를 권한다** — 순서 의존이 없고, 가드가 읽히는 자리에 산다.
- `Copy Header` 토글은 메인 그리드의 것(`#copy-header-toggle`)을 **재사용**한다. 패널 전용 토글을 새로 만들면 같은 뜻의 스위치가 둘이 된다.
- `navigator.clipboard` 를 부르지 않는다(운영은 평문 HTTP). `document` 의 `copy` 이벤트 + `e.clipboardData` 가 정본이고, 이 규약은 `scripts/check_clipboard_convention.mjs` 가 prebuild 에서 강제한다.

### 3.4 정렬 띠 (붙여넣기 전 유일한 관문)

패널 상단 30px 띠에 세 가지를 적는다: 복사 범위 `N행 × M열` · `fill_targets` 열 순서 · 대상 열 순서. 대상 열은 메인 그리드의 현재 범위에서 읽는다(`state.dragStartCell`/`dragEndCell` → `grid.js` 의 `visibleRangeColIds()`).

- 일치 → 초록 `열 순서 일치`.
- 불일치(열 이름·순서·개수 중 하나라도) → 경고 상태. **막지 않고 알린다.** 사람이 의도적으로 한 열만 붙여넣는 경우가 실제로 있다.
- 🔴 대상 범위에 **가상 조인 컬럼이 한 칸이라도 걸리면 «불가»로 단정한다.** 서버 거부가 배치 단위라 그 한 칸 때문에 **붙여넣은 블록 전체가 400** 이 된다(`frontend.md` §3.4). 판정은 `state.isVirtualColumn(colId)`.

**수락 기준:** 참조 그리드에서 3행×2열 드래그 → `Ctrl+C` → 메인 그리드 `Ctrl+V` 로 `dt_lot`·`dt_slot` 6셀이 Tx 스테이징(`.cell-dirty-tx`)된다 · 클립보드 내용이 `TL26-0842\t03\n…` 이다(헤더 토글 off) · 열 순서를 바꾼 규칙으로는 경고 띠가 뜬다 · 대상에 가상 컬럼을 포함시키면 «불가»가 뜨고, 무시하고 붙여넣으면 서버가 배치를 거부한다.

---

## Phase 4 — 게이트·문서 (이 단계를 빼면 위 셋은 다음 라운드에 조용히 죽는다)

1. **하네스 신설** `client2/tests/reference_grid_paste_harness.mjs`. `client2/tests/*.mjs` 는 `check:harnesses` 가 **발견식으로** 훑으므로 파일만 규약대로 놓으면 매 빌드에 돈다. 반드시 자기 요약 지점에서 `ASSERTIONS <ran> <failed>` 한 줄을 찍고, `scripts/check_harnesses.mjs` 의 **`FLOORS`** 에 등록한다(`KNOWN_RED` 가 아니다 — 초록으로 착지시킨다. 한 이름이 양쪽에 있으면 러너가 기동을 거부한다).
   단언 최소 4 + **변이 4종**(변이가 잡히지 않으면 실패):
   - TSV 열 순서가 `fill_targets` 순서와 같다 ↔ 변이: 순서를 뒤집는다.
   - 패널 안의 `copy` 가 `clipboard.js` 의 TSV 로 덮이지 않는다 ↔ 변이: 3.3 의 가드를 제거한다.
   - 열 순서 불일치가 경고를 낸다 ↔ 변이: 비교를 `length` 만 보게 만든다.
   - 대상에 가상 컬럼이 있으면 «불가» ↔ 변이: `isVirtualColumn` 을 `false` 고정.
2. **`fill_targets` 미선언 규칙에서 폴백이 도는지**를 같은 하네스가 채점한다. 선언 하나에 의존하는 기능은 그 선언이 없는 경로가 곧 운영 다수다.
3. **문서.** `docs/architecture/frontend.md` §3 모듈 표의 `enrichment_reference_view.js` 행(책임·줄 수)과 §3.4 를 갱신하고, `docs/history/<YYYYMMDD_HHMMSS>_reference_grid_and_column_filters.md` 를 새로 쓴다. 🔴 §6 배너가 「콘솔 클라이언트 화면은 계승하지 않는다」고 적고 있으므로, 이 작업이 **현행 `client2` 화면에 착지한다는 것**과 그 이유를 히스토리 항목에 명시한다.
4. `npm run build` 로 `dist/` 를 갱신해 커밋한다(서버가 서빙하는 것은 소스가 아니라 번들이다).

---

## 하지 않을 것

- 채우기/확정 **버튼** 패널(목업 `1d`). 폐기한다.
- 참조 패널용 **두 번째 TSV 구현**·두 번째 범위 선택 모델·두 번째 Copy Header 토글.
- 새 서버 엔드포인트, `navigator.clipboard`, 새 색 토큰.
- 붙여넣기를 **막는** 관문. 정렬 띠는 알리는 장치다.
