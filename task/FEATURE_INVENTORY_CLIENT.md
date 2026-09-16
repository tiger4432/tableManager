# 기능 인벤토리 — 클라이언트 절반

> **무엇인가.** 「화면 · 그 화면이 할 수 있는 일 · 그것이 부르는 라우트 · 배선 여부」의 **소스 인구조사**.
> **무엇이 아닌가.** 런타임 관측이 아니다. 브라우저를 한 번도 안 열었다 — 그려 봐야만 답이 나오는 것은
> 전부 §E 「못 잰 것」에 있고, **그 목록은 산출물이지 실패가 아니다.**
>
> 기준 커밋 `dcb444ae` (2026-09-16 21:20). ⚠️ 측정 중 다른 레인이 `client2/` 를 세 번 착지시켰다
> (`b892e8e5` → `f56414ae` → `dcb444ae`) — 줄 수는 밀렸을 수 있고, **자리는 심볼로 다시 짚어라.**
>
> **읽은 순서(상설).** ① `docs/architecture/CODE_MAP.md` §7 · §7-A · §7-B · §5-H-bis · §5-I 의 클라 절,
> `docs/overview/SYSTEM_OVERVIEW.md` §3, `docs/architecture/frontend.md` → ② **그다음** 오늘 소스에 대고 검증.
> 인용한 문서 문장은 근거가 아니다. **오늘도 참인지가 근거이고, 어긋난 것은 §D 에 있다.**
>
> **「죽었다」를 말한 자리는 «전부» 주변 열 줄을 읽고 주석을 원문으로 인용했다.** 이 저장소는
> 소유자 판정을 주석으로 적어 두고 «되돌릴 수 있게» 남기는 일이 잦아서, 「호출자 0」과
> 「일부러 남김」이 **코드에서 똑같이 생겼다.** 가르는 것은 주석뿐이다.

---

## 0. 화면은 여섯이고, 여섯 다 빌드에 있다

`client2/vite.config.js` 의 `rollupOptions.input` 이 정본이다. **오늘 실측 여섯:**

| 화면 | 엔트리 JS | html 줄 | JS 줄 | dist 자산 | dist 도달? |
|---|---|---|---|---|---|
| `index.html` (메인 그리드) | `src/main.js` | 656 | 2,135 | `assets/main-C4qt5VD4.js` | **O** |
| `admin.html` | `src/admin.js` | 2,578 | 4,996 | `assets/admin-3qohHdWj.js` | **O** |
| `map_editor.html` | `src/map_editor.js` | 467 | 11,220 | `assets/map_editor-BUFYjTTb.js` | **O** |
| `map_editor2.html` | `src/map_editor2.js` | 880 | 496 | `assets/map_editor2-CC1RFNop.js` | **O** |
| `rnd-board.html` | `src/rnd_board/main.js` | 37 | 997 | `assets/rnd_board-BN0xgd8y.js` | **O** |
| `walk.html` | `src/walk/main.js` | 66 | 535 | `assets/walk-C13EnbZ3.js` | **O** |

`git status client2/dist` 는 깨끗하고, dist 는 **소스와 같은 커밋에 착지한다**. 신선도 실측:
`replayable_rules.js` 가 만드는 `/admin/chain/rules/replayable` 리터럴이 `main-C4qt5VD4.js` 에 **있다**
(그 모듈은 09-16 10:47 신설) → **dist 는 낡지 않았다.**

### 화면에서 화면으로 — 진입 지도 (전수 grep)

```
index.html  ──🧭 Menu 드롭다운──→  map_editor.html · map_editor2.html · admin.html
map_editor.html ──「← Back to Grid」──→ index.html
map_editor2.html ──「메인」──→ /
admin.html ──「Return to Main」──→ /
rnd-board.html   ← 들어오는 링크 «0»
walk.html        ← 들어오는 링크 «0»
```
🔴 **`rnd-board.html` 과 `walk.html` 은 어떤 화면에서도 «닿을 수 없다».** URL 을 직접 쳐야 한다.
rnd-board 는 그것이 **기록된 사실**이다 — `SYSTEM_OVERVIEW.md:131`:
「**R&D 진단 보드** — 조립식 부품의 격자. **nav 링크가 없고 직접 엽니다**」.
walk 은 **어느 문서에도 그 문장이 없다** — SSOT 의 엔트리 표에 `walk.html` **행 자체가 없다**(§D-1).

⚠️ 그리고 index.html 의 은퇴 주석(`:294-303`)이 「두 화면이 하던 질문은 **R&D 보드의 walk 이 답한다**」로
사용자를 보내는데, **그 보드로 가는 링크가 메뉴에 없다.**

---

## 1. `index.html` — 메인 데이터 그리드

id 76개 전수. **모든 id 가 `client2/src` 어딘가에서 참조된다** (미참조 0).
DOM 핸들은 `src/dom.js` 의 `elements` 게터가 «한 자리»에서 소유한다.

| 사용자 행동 | 그리는 코드 | 부르는 라우트/이벤트 | 배선? |
|---|---|---|---|
| 표 고르기 `#table-select` | `main.js` change | `GET /tables/{t}/schema` · `/tables/{t}/data` (`api.js switchTable`) | O |
| 새로고침 `#refresh-grid-btn` | `main.js` click | `GET /tables/{t}/data` | O |
| 행 추가 `#add-row-btn` | `main.js` click | `POST /tables/{t}/rows` (`api.js addRows`) | O |
| 행 삭제 `#delete-row-btn` | `main.js` click | `POST /tables/{t}/rows/batch_delete` | O |
| 폴더 업로드 `#folder-upload-btn` | `main.js` click → `#toolbar-folder-input` | `POST /tables/{t}/upload` | O |
| 파일 끌어놓기 `#drop-overlay` | `main.js setupDragAndDrop` :1380 | `POST /tables/{t}/upload` | O (C-57 에서 수리됨) |
| 데스크톱 받기 `#desktop-download-btn` | `main.js:362` | `GET /api/desktop/download` (먼저 GET 으로 묻고 헤더에서 끊음) | O |
| **⚡ Graph Sync `#graph-sync-btn`** | `main.js:301-344` | `POST /api/graph/sync` | **X — §A-1** |
| 검색 `#global-search` / 컬럼 `#search-cols` | `main.js` input/change | `GET /tables/{t}/data?q=&cols=` | O |
| 필터 칩 · 접기 `#filter-chips-more` | `grid.js:447` | 클라 | O (조건부 표시) |
| 필터 전체 해제 `#filter-clear-all` | `grid.js:457` | 클라 (`setFilterModel(null)`) | O (칩 2개 이상일 때만 노출, `grid.js:454`) |
| 트랜잭션 모드 `#tx-mode-toggle` / 적용 `#tx-apply-btn` / 버림 `#tx-discard-btn` | `main.js` | `PUT /tables/{t}/data/updates` (`main.js:2052`) | O |
| 트랜잭션 필터 해제 `#clear-tx-filter-btn` | `main.js` | 클라 | O |
| 셀 편집 (그리드) | `api.js handleCellEdit` :~249 | `PUT /tables/{t}/data/updates` (`api.js:541`) | O |
| 복사/붙여넣기 (엑셀형 범위) | `clipboard.js` copy/paste 리스너 | `PUT …/data/updates` (`clipboard.js:612`) | O |
| 선택 셀 비우기 | `clipboard.js:861` | `PUT …/data/updates` | O |
| 헤더 포함 복사 `#copy-header-toggle` · `#copy-header-menu-toggle` | `main.js:834` (`copyHeaderToggles()` 한 자리) | `localStorage['copyHeader']` | O |
| 스마트 페이스트 `#menu-smart-paste` · Ctrl+Shift+V | `main.js:~1607/1662` | `POST /tables/{t}/upload` | O (단축키가 본동선 — 주석 `:1489-1506`) |
| 컬럼 선택기 `#column-selector-btn` · 전체/해제 | `main.js` | 클라 | O |
| 최신순 정렬 `#sort-latest-toggle` | `main.js` change | `GET …/data?order_by=` | O |
| 페이지 이동 `#prev/next-page-btn` · `#page-input` | `main.js` | `GET …/data?skip=` | O |
| 보기 모드 `#view-mode-select` · 전량 `#load-all-btn` | `main.js` | `GET …/data?limit=` | O |
| CSV 내려받기 `#load-csv-btn` | `main.js:1124` | `GET /tables/{t}/export?…` (`:1189`) | O |
| 이력 탭 Global `#tab-global` | `main.js:532` | `GET /audit_logs/recent` | O |
| 이력 탭 Row `#tab-row` | `main.js:560` | `GET /tables/{t}/rows/{row_id}/history` (`timeline.js:104`) | O |
| **이력 탭 Cell** | `main.js:550` (`?.` 로 등록) | `GET /tables/{t}/rows/{row_id}/cells/{col}/history` (`timeline.js:102`) | **X — §A-2** |
| 참조뷰 탭 `#tab-reference` | `main.js:571` → `enrichment_reference_view.js` | `GET /enrichment/rules/{r}/references/{i}` | O (규칙 있을 때만 노출) |
| 감사 필터 3종 `#audit-filter-user/kind/when` | `timeline.js:865-948` | 클라 필터 | O |
| 이력 새로고침 `#refresh-history-btn` | `main.js` | 위 이력 라우트 | O |
| 우클릭 → 소스 `#menu-sources` | `main.js:842` | `POST /tables/{t}/cells/sources/query` · `DELETE …/sources/{name}` · `PUT …/priority` | O |
| 우클릭 → 삭제 `#menu-delete` | `main.js:848` | `POST …/rows/batch_delete` | O |
| **다시 돌리기 배너** `#redo-banner-host` | `redo_banner.js` ← `main.js:199 runRetroactive` | `POST /admin/retroactive/{op}/run` · `GET /admin/chain/rules/replayable` | O — **단 §C-1** |
| 원장 소스 라벨 `#grid-source-label-host` | `grid_source_label.js` ← `main.js loadLedgerDeclaration` | `GET /api/ledger/declaration` | O |
| 범위 넘기기 `#rescope-menu-host` | `rescope_handoff.js putRescopeHandoff` | 라우트 없음 — `sessionStorage` 로 admin 에 인계 | O |
| 테마 전환 `[data-theme-toggle]` | `theme.js` | 클라 | O |
| 실시간 수신 | `websocket.js` | WS — 이벤트 6종 | O (§B 참조: 서버 6 : 클라 6, **정확히 일치**) |

---

## 2. `admin.html` — 어드민 (탭 **일곱**)

> 출처: 이 절의 표는 서브 인구조사(어드민 전담)의 것이고, **§C·§A·§B 에 올린 판정 넷은 내가 직접 다시 쟀다**
> (`refreshHealthStrip` 호출자 · `extraButtons` 호출자 · 줄 수 · `fetch(\`${API_BASE}/admin/` 0건).

**탭은 일곱이다.** `admin.js:2` 주석 · `admin.html:1984` 주석 · `CODE_MAP.md:5170` **셋 다 「5탭」이라 적고 있다** (§D-2).

| # | 탭 | 렌더 | 주요 라우트 |
|---|---|---|---|
| 1 | Overview | `renderOverview` :3719 + `RuntimePanel`·`ChainQueuePanel`·`ChainGraphPanel` | `/admin/file-ingestion/{failed,workspaces,active}` · `/admin/outbox/failed` · `/admin/chain/{rules,queue}` · `/admin/mappers/list` · `/admin/auto-update/status` · `/dashboard/summary` · `/runtime` · `/chain/graph` |
| 2 | **Tables** | `TableConfigPanel` → `RawRegistryPanel` | `GET/POST /admin/tables/config/raw` · `GET /admin/ledger/relations` |
| 3 | File Ingestion | `renderFileTable` :1481 등 | `/admin/file-ingestion/{logs,workspaces,active,retry-failed}` |
| 4 | Chain | `renderChainTable` :1706 · `ChainRulePanel` · `ChainQueuePanel` | `GET/POST /admin/chain/rules/raw` · `/admin/chain/{rules,queue}` · `/admin/outbox/{failed,retry-failed}` · `/admin/mappers/list` |
| 5 | Auto Update | `renderAutoUpdateTable` :1808 | `/admin/auto-update/{status,run-now,toggle}` |
| 6 | Enrichment | `renderEnrichmentTable` :1905 | `GET /enrichment/rules` + 규칙별 `GET /tables/{derived}/data` |
| 7 | **Ontology Explorer** | `ontology_explorer{,_view,_store}.js` 전담 + `LedgerSourcesPanel` | `/admin/ontology-explorer/*` **15 라우트 전부 소비** · `GET /api/ledger/declaration` · `/admin/ledger/sources` |

주요 컨트롤 (발췌 — 전 항목은 위 탭별 라우트가 덮는다):

| 사용자 행동 | 그리는 코드 | 라우트 | 배선? |
|---|---|---|---|
| Reload Configs & Code | `admin.js:832 → :4466` | `POST /admin/reload-configs` | O |
| 표 등록 저장 | `raw_registry_panel.js:611 → admin.js:1260` | `POST /admin/tables/config/raw` | O |
| 규칙 등록 저장 | `raw_registry_panel.js:611 → admin.js:1180` | `POST /admin/chain/rules/raw` | O |
| 소급: 건수 확인 → 실행 → 확인 | `admin.js:3416 / :3459 / :3492` | `GET /admin/retroactive/{op}/count` → `POST …/run` | O |
| 실행 중단 × | `admin.js:2930 → :2792` | `POST /admin/retroactive/runs/{id}/cancel` | O (**`cancellable` 일 때만 그린다** — 주석: 「못 멈추는 것에는 «아무것도» 안 그립니다. 죽은 × 는 화면이 하는 거짓말입니다」) |
| 인제션/체인 실패 Retry | `admin.js:4406 / :4379 / :4437` | `POST /admin/{file-ingestion,outbox}/retry-failed` | O |
| 🛠️ Edit (매퍼·파서·수집기) → 💾 Save Code | `admin.js:4678 / :4655` | `GET/POST /admin/scripts/code` | **조건부 — §A-5** |
| 온톨로지 초안 만들기/저장/활성화/삭제/시험실행 | `ontology_explorer.js` | `/admin/ontology-explorer/{drafts,drafts/new,test-run,view,columns,authoring/*,deletion-preview,declarations/*}` | O |
| 설정 반영 · 조인 승인 · 공백 카탈로그 · 이관 드라이런 | `config_resolve_view.js` · `join_verification.js` · `gap_catalogue.js` · `plan_dry_run.js` | `/admin/config/resolve` · `/admin/config/virtual-join/verify` · `/api/ledger/gaps` · `/admin/transfer-plan/dry-run` | O (표시 전용) |
| Enrichment 규칙 **편집** | — | — | **X — 편집 UI 가 «없다».** `admin.html:2444-2448` 이 「수기 편집 후 Reload Configs」라고 **산문으로 안내**한다 |

---

## 3. `map_editor.html` — 웨이퍼 맵 에디터

> 출처: 맵 전담 인구조사. 이 절의 라우트 집합(14)은 그쪽 실측이다.

| 사용자 행동 | 그리는 코드 | 라우트/이벤트 | 배선? |
|---|---|---|---|
| 대상 테이블 고르기 `#map-table-select` | `map_editor.js:568 → switchTable :1281` | `GET /tables/{t}/schema` · `GET /api/maps/paint-rules?table=` | O |
| 맵 열기 `#btn-load-map` | `:710 → loadExistingMap :5108` | `GET /tables/{t}/data` · `/tables/wafer_map_metadata/data` · `/tables/map_split_registry/data` · `/api/maps/preset-routing` | O |
| 메타 칸 값 제안 | `:10330 → :10264` | `GET /tables/{t}/columns/{c}/values` | O |
| 오버레이 ＋겹치기 / 토글 / 가져오기 / 모두 해제 | `:11155` · `:10754` · `:10943` · `:10763` | `GET /tables/{src}/data` + 메타 2회 | O |
| 회전 0/90/180/270 · 앞/뒤 · Invert Y · START | `:892-910`, `:666` | 클라 (`reseatForSeparationMode :2192`) | O |
| **Width / Height `#grid-cols`·`#grid-rows`** | `:666`, 분기 `:668-694` | 클라 | **X — 마크업이 `readonly`이고 `dispatchEvent` 0건. §A-3** |
| 물리 규격 6칸 → ⚡ Apply | `:843`, `:782 → applyPhysicalGeometry :2870` | 클라 | O |
| 프리셋 저장 / 불러오기 / 삭제 | `:3181` · `:3156` · `:3233` | `POST /api/map-presets` · `GET /api/map-presets` · `DELETE /api/map-presets/{k}` | O (삭제는 `is_custom` 일 때만 노출) |
| 유효 다이 맵 키 지정 | `:9783` (Enter) · `:654` (select) | `GET /tables/wafer_map_metadata/data` + `GET /tables/{ref}/data` | O |
| X/Y/Value 컬럼 매핑 | `:878/:882/:886` | 클라 (목록은 schema) | O |
| 캔버스 칠하기·드래그·우클릭 지우기 | `initMouseDragEvents :1087` | 클라 | O |
| 원점 지정 · E1/E2 선택 · 자동 칠하기 | `:744` · `:871/:872` · `:873` | 클라 | O |
| Fill/Clear (전체·선택) | `:759/:758/:874/:875` | 클라 | O |
| 📋 Copy to Excel · Ctrl+V 되붙이기 | `:7167` · `:7965` | 클라 (클립보드) | O |
| 헤더 포함 `#map-copy-header-toggle` | `:777` | `localStorage['mapCopyHeader']` | O — **§C-4** |
| **⚡ Push Map Data** | `:6101` | `PUT /tables/wafer_map_metadata/data/updates` (`:6299`) + `PUT /tables/{t}/data/updates` (`:6328`) | O |
| **📐 규격만 저장** | `:9840` | `PUT /tables/wafer_map_metadata/data/updates` (`:9956`) | O |
| 「2. Legend & DOE」 패널 전체 | `transfer_plan.js` (1,953줄) | `GET /api/transfer-plan/stages` · `/api/transfer-plan/source-summary` | O |
| ↻ 가용 자재 · 자재 맵 열기 · ← 돌아가기 | `transfer_plan.js:1478` 등 | 위 + 맵 로드 경로 | O (depth>0 조건부) |
| **⇄ 엑셀** 표시 | `transfer_plan.js:1743` | — | **X — 컨트롤이 «아니다».** 주석 `:1758`: 「`⇄ 엑셀`은 표시이지 버튼이 아니다 — 클릭 핸들러가 없다(비보안 컨텍스트 제약)」 → **의도적** |
| **「선언 거절 진단」 줄** | `transfer_plan.js:1733` | — | **X — 정적 안내.** 주석 `:1731`: 「정적이다. 부르지도 않고 받지도 않는다」 → **의도적** |
| 분리 모드 `#separate-from-background` | change 리스너 **0건**, `:2193` 에서 읽기만 | 클라 | **조건부** — 켠 직후 화면에 아무 변화 없음. 소스가 그 사실을 안 적었다 |

---

## 4. `map_editor2.html` — 맵 정렬(좌표계 확정)

| 사용자 행동 | 그리는 코드 | 라우트/이벤트 | 배선? |
|---|---|---|---|
| 정렬 규칙 고르기 `#me2-rule-select` | `map2/main.js:1971 → map_editor2.js:287` | `GET /tables` · `/tables/{t}/schema` · `/api/maps/paint-rules` · `/api/maps/alignment/references` | O |
| 대상 테이블 `#me2-table-select` | `map2/main.js:1981` | `GET /api/maps/alignment/worklist` | O |
| x·y·값 컬럼 `#me2-col-x/y/value` | `map2/main.js:1991/1993/1995` | 질문 갱신 → `GET /api/maps/alignment/view` | O |
| 제안 확인 `#me2-columns-confirm` | `map2/main.js:1999` | 클라 | 조건부 (`bindingIsGuess` 일 때만 unhide) |
| 워크리스트 검색 / 행 선택 | `map2/main.js:2018 / :1967` | `GET /api/maps/alignment/worklist?q=` · `/api/maps/alignment/view` | O |
| 후보 8칸 중 고르기 | `map2/main.js:2038` | 클라 | O |
| 기준 맵 `#me2-reference-select` | `map2/main.js:1998` | `GET /api/maps/alignment/view` | O |
| 순번 색 `#me2-index-colour` | `map2/main.js:2026` | 클라 | 조건부 |
| **확정 `#me2-confirm-btn`** (Enter 포함) | `map2/main.js:2027 / :2044` | `POST /api/maps/alignment/confirm` | O |
| **양식 내보내기 `#me2-export-btn`** | `map2/main.js:2112-2118` | — | **X — click 핸들러 0건. 🔵 09-17 판정 455 로 «화면에서 내려갔습니다» — `hidden = !artifactImplemented()`. 빚이 사라진 게 아니라 «화면이 약속하지 않는 상태로 대기»합니다. §A-4** |
| **붙여넣기 결과 `#me2-paste-result`** | `showArtifactResult` (`map2/main.js:2219`) | — | **X — 호출자 0건, 페이지에 `paste` 리스너 0건. §A-4** |
| (자동) 정렬 임계값 | `map2/api.js:106` `config: null` | **라우트가 없다는 사실이 값으로 적혀 있다** | 의도적 (항상 `RouteNotServedError`) |

---

## 5. `rnd-board.html` — R&D 진단 보드

HTML 은 37줄이고 컨트롤이 **0**이다. 화면은 `main.js` 의 `BOARD` 선언이 격자에 앉히는 **좌석 열여섯**이다.

| 좌석(`id` · `title`) | 부품 | 부르는 것 | 배선? |
|---|---|---|---|
| `head-summary` 머리 요약 | `head_summary_panel.js` | walk (`follow: ['bonded_from']`) → `GET /api/ledger/subgraph` | O |
| `marking-status` 마킹 | `marking_status_panel.js` | 클라 (`MarkingStore`) | O |
| `control-bar` 제어 · 축 선택 | `control_bar_panel.js` | 축을 `axis:y` 마킹에 쓴다 | O |
| `main-trend` 메인 트렌드 | `main_trend_panel.js` | walk (`follow: ['inspected','observed','of_kind']`) | O |
| `trend-declaration` 축 / `composition-declaration` 축·구성 | `declaration_panel.js` | 표시 전용 | O |
| `candidate-trend` 마킹한 후보 트렌드 · 마킹 2 | `main_trend_panel.js` | walk | O |
| `composition` 구성 · **SYN-CX-CHIP-001** | `composition_panel.js` | walk (`follow: ['bonded_from']`) | O — **§C-6** |
| `map-bond-a` 본딩 맵 · `chip-zoom` 칩 확대 · `map-core` 코어 맵 | `map_panel.js` | walk + `GET /tables/wafer_map_metadata/data` | O |
| `expanded-layer` 펼친 층 | `expanded_layer_panel.js` | walk | O |
| `candidate-list` 원인 후보 · **SYN-CX-BW-001** | `candidate_list_panel.js` | walk (`legacyRoute:'candidate'` → subgraph) | O |
| `rank-list` 순위 · **SYN-CX-BW-001** | `rank_list_panel.js` | walk | O |
| `reach` 닿는 곳 · 마킹 1 에서 한 홉 | `reach_panel.js` | `legacyRoute:'reach'` → `GET /api/ledger/subgraph` | O |
| `walkBox` 걷기 — 타입·키·follow·collect | `walk_box_panel.js` (651줄) | `GET /api/ledger/declaration` + `GET /api/ledger/subgraph` | O — **§C-3** |
| 클릭 = 마킹 / Shift+클릭 = 컨트롤(−) | `panel.js markingIntent` | 클라 (`MarkingStore`, 부호 셋) | O |

🔴 **그러나 `api.js` 의 `ROUTES` 다섯 중 «넷»이 서버에 없는 라우트다 — §A-6.**

---

## 6. `walk.html` — 걷기 검색 (휴대폰 대상)

HTML 은 66줄이고 컨트롤이 **0**이다 (`#wk-host` 하나). 전부 `src/walk/main.js` 가 그린다.

| 사용자 행동 | 그리는 코드 | 라우트 | 배선? |
|---|---|---|---|
| 노드 타입 고르기 | `walk/main.js:161` | 목록은 `GET /api/ledger/declaration` | O |
| 주어 고르기 (값 목록) | `walk/main.js:205` | `GET /api/ledger/key-values?…` | O |
| 키 직접 입력 | `walk/main.js:233` | — | O |
| `collect` 체크박스 | `walk/main.js:255` | 선언에서 | O |
| 경로 고르기 (선언이 아는 길) | `walk/main.js:283` (`pathsBetween`) | 선언에서 | O |
| `follow` 체크박스 | `walk/main.js:308` | 선언에서 | O |
| 걸음: 방향 · hops · node_limit | `walk/main.js:330`·`:342` | — | O |
| **날리기** | `walk/main.js:352 → createWalkBoxWalk` | `GET /api/ledger/subgraph` | O |
| 실패 시 「다시」 | `walk/main.js:484` | 위 | O |

🔴 **요청을 짓는 것은 이 화면이 아니다** — `createWalkBoxWalk`(`rnd_board/api.js:1977`)가 `fetchSubgraph` 에 위임한다.
그 파일 머리가 이유를 적는다: 「걷기 요청을 짓는 함수가 둘이라 한쪽만 `hops` 를 안 실었고,
화면이 「3홉」이라 쓰는 동안 서버는 12홉을 걸었습니다. 오류도 경고도 «0» 이었습니다.
=> 그래서 이 페이지는 «폼»만 갖고, 요청은 `createWalkBoxWalk` «하나»가 짓습니다.」 **오늘도 참이다.**

---

# A. 「기능이 없는 UI」

> 컨트롤이 있는데 그 끝에 답하는 것이 «없는» 자리. **전부 주변 주석을 원문으로 읽었다.**

### A-1. ⚡ Graph Sync — **의도적 보존 · 라우트는 정말로 없다**
```
자리      client2/index.html:82  (마크업) · client2/src/main.js:301-344 (핸들러)
라우트    POST /api/graph/sync  ->  서버 라우트 표 118개에 «없다» (410 스텁도 없다)
게이트    const GRAPH_SYNC_RETIRED = true;  // R-2026-08-14-H   (main.js:306)
```
주변 주석 원문 (`main.js:299-305`):
> 「⚰️ [판정 R-2026-08-14-H] 구 그래프 갈래 은퇴 — 이 버튼은 더 이상 노출하지 않는다. … 서버가 그 라우트를
> 410으로 거절하므로 버튼을 두면 누를 때마다 실패 토스트만 뜬다 — **눌러도 되는 것처럼 보이는 죽은 버튼은
> 화면이 사용자에게 하는 거짓말이다.** 마크업(index.html)의 기본값이 이미 `display: none`이라 …
> 버튼 마크업과 이 핸들러 몸통은 판정 ④의 코드 제거 라운드 몫.」

**판정: 의도적 보존.** 그리고 **dist 실측이 이것을 확인한다** — `GRAPH_SYNC_RETIRED` 가 상수라
번들러가 `if(false)` 가지를 통째로 지운다: `api/graph/sync` 는 `main-C4qt5VD4.js` 에 **0건**.
마크업만 dist/index.html 에 남아 있고 `display:none` 이다. **사용자에게는 존재하지 않는다.**
⚠️ 다만 주석의 「410으로 거절하므로」는 **오늘 거짓**이다 — 스텁까지 삭제돼 404 다.

### A-2. 이력 「Cell」 탭 — **의도적 보존 · 그 탓에 서버 라우트 하나가 도달 불가**
```
자리      main.js:550  elements.tabCellBtn?.addEventListener(...)
요소      #tab-cell 이 index.html 에 «없다» (id 76개 전수 확인). dist/index.html 에도 0건
결과      state.activeHistoryTab = 'cell' 을 세우는 자리가 main.js:556 «하나»뿐이고
          그 줄은 영원히 안 돈다  ->  timeline.js:102 의 셀 이력 URL 분기가 «도달 불가»
```
주변 주석 원문 (`main.js:547-549`):
> 「The Cell History tab is off the row (**owner, 2026-08-21: it has no function**). The listener is
> GUARDED rather than deleted: `activeHistoryTab === 'cell'` is still read in five places in
> timeline.js, so removing the branch is a different change from taking the tab off the screen,
> and **doing both at once would make the second one hard to undo.**」

**판정: 의도적 보존.** ⚠️ 부수 효과는 §B-8 에 있다 — 서버 라우트
`GET /tables/{t}/rows/{row_id}/cells/{col}/history` 가 이 탭 말고는 입구가 없다.
⚠️ 그리고 주석의 「five places」는 오늘 **timeline.js 안에 네 자리**(:102 · :595 · :699 · :1079)다.

### A-3. 맵 에디터 Width / Height — **모름**
```
자리      map_editor.html:129/:134  (둘 다 readonly) · 핸들러 map_editor.js:666, 분기 :668-694
발화 경로 파일 전체에 dispatchEvent «0건»  ->  이 change 분기는 발화할 수 없다
```
주변 주석(`:679-694`)은 길지만 **「이 입력칸은 readonly 다」를 한 줄도 안 적는다** — 대신 기하 편집 규칙과
2026-07-31 실측(36건 중 16건 어긋남)을 적는다. **판정: 모름.**
기능 손실은 없다 — 같은 반응(`reseatCellsToStoredCoords`)이 `applyPhysicalGeometry:2902` 에 살아 있다.
readonly 가 풀릴 날의 보험인지 지나간 배선의 잔해인지 **소스가 말하지 않는다.**

### A-4. map_editor2 「양식 내보내기」 · 「붙여넣기 결과」 — **하나는 판정으로 닫혔고, 하나는 여전히 모름**
```
#me2-export-btn      map_editor2.html:309 · click 리스너 0건 · hidden = !artifactImplemented()
                     (판정 455, 09-17 — 그 전에는 disabled 였고 사유가 «콘솔»로 갔습니다)
#me2-paste-result    map_editor2.html:660 · showArtifactResult 호출자 0건 · 페이지에 paste 리스너 0건
```
`artifact_gateway.js:184-191` 원문:
> 「🔴 **IT STAYS `false` UNTIL THE WIRING LANE FLIPS IT, AND THAT IS DELIBERATE.** The two functions
> above are implemented and scored … this flag does not report whether a module works -- it reports
> whether the SHELL may offer the affordance, and no control has been driven end to end yet.
> … **Flipping this is a one-line change for whoever scores the button.**」

내보내기 → **의도적 보존**(비활성으로 «보이는 것»이 계약).
붙여넣기 결과 → **모름**: HTML 주석 `:658` 이 「컨트롤 없음(**키보드로 그림에 직접 붙여넣는다**)」라고
**단언**하는데 그 키보드 경로가 소스에 없다. 보존인지 미배선인지 주석이 안 가른다.

⚠️ 같은 파일 안에서 **주석 둘이 모순**이다: `artifact_gateway.js:4` 는
「The functions below throw `NOT_IMPLEMENTED`」라고 적는데 `readArtifact`(:121)·`writeArtifact`(:168)는
**오늘 구현돼 있고** `NOT_IMPLEMENTED`(:82)는 **읽는 곳이 0**이다. §D-6.

### A-5. 어드민 「💾 Save Code」 — **서버가 조건부로 «거절만» 한다**
읽기(`GET /admin/scripts/code`)는 통과해 **에디터가 정상으로 열리고 코드가 보인다.**
저장을 누른 그 순간에만 갈린다:
```
① ASSY_ADMIN_TOKEN 미설정  ->  503  (require_admin_token_strict, server/main.py:6771)
② 격리 데이터 루트          ->  403 Refused, 그리고 «mappers/ 경로에만» (main.py:6691)
```
🔴 ②가 특히 조용하다 — Chain 탭 「🛠️ Edit Mapper Code」 · Mappers 탭 「🛠️ Edit」 · tx 진단
「🛠️ Edit Mapper」 **셋 다 `mappers/…` 를 연다.** 같은 게이트가 `POST /admin/auto-update/run-now`·
`POST /admin/retroactive/{op}/run` 에도 걸린다(①만).
⚠️ 실제로 오늘 503/403 인지는 **프로세스 환경의 사실**이라 소스로 못 잰다 → §E.

### A-6. R&D 보드 — **`ROUTES` 다섯 중 넷이 서버에 없다**
```
클라 선언 (client2/src/rnd_board/api.js:49-59)     서버 실측 (/api/ledger 접두, trace_router.py)
  lotMap      /api/ledger/lot_map        404      서버가 여는 것은 «넷»:
  composition /api/ledger/composition    404        /subgraph · /key-values · /gaps · /declaration
  subgraph    /api/ledger/subgraph        O
  trends      /api/ledger/trends         404
  siblings    /api/ledger/siblings       404
```
`LEGACY_ROUTES` 일곱 중 살아 있는 라우트로 가는 것은 **둘**(`candidate`·`reach` → subgraph).
나머지 다섯(`trend_y`·`wafer_process`·`map`·`basis`·`peer`)은 **죽은 라우트로 간다.**

🔵 **그중 하나는 «이름이 붙은» 404 다.** `api.js:1598-1605` 원문:
> 「🔴 좌석 3 을 걷기로 옮겼다가 «되돌렸습니다» … 옮기면 404 는 사라지는데 «컨트롤 바의 종류 축»이 같이
> 사라집니다 … **404 하나를 지우려고 화면이 «말을 덜 하게» 만드는 것은 오늘 판정에 어긋납니다.**
> ⏭ 먼저 할 일: Y축이 «종류»가 아니라 «집계»를 고르게 되는 것. 그 뒤에야 이 줄이 걷기로 갈 수 있습니다.
> 그때까지 404 하나가 남고, **그 404 는 «무엇을 기다리는지 이름이 붙은» 것입니다.**」

🔴 **오늘 좌석이 실제로 그 다섯을 부르는가 — 실측:**
```
좌석이 legacyRoute 를 «대는» 것        reach(subgraph, OK) · candidate(subgraph, OK)
좌석이 «안 대는» 것                    나머지 열넷 — follow 를 선언하고 bound.load 가 주입된다
                                      => 부품의 폴백 기본값이 «안 산다»
도달 불가 가지 «둘»                    main.js:857 `options.basisChipId` (좌석 «0»이 이 키를 준다)
                                      main.js:946 `options.question`  (좌석 «0»이 이 키를 준다)
                                      -> legacyRoute 'basis'·'map' 이 오늘 «발화하지 않는다» (기준 ③)
잠복                                  composition_panel:33 · expanded_layer_panel:34 ·
                                      head_summary_panel:39 가 `|| 'wafer_process'` 를 «아직» 들고 있다.
                                      bound.load 가 주입되는 동안만 잠잠하다
```
그리고 그 잠복을 **소스가 자기 위험으로 적어 두었다**(`composition_panel.js:34-37`):
> 「좌석이 라우트 이름을 안 대면 … 안 그러면 this.collect 의 기본값 'wafer_process' 가 살아나서,
> 좌석이 이름을 지웠는데도 죽은 라우트를 계속 부릅니다 -- **실측으로 composition 404 가 그렇게
> 한 자리 남아 있었습니다.**」
🔵 `main_trend_panel.js:94` 는 같은 기본값을 **이미 제거했다**(`|| null`) — CODE_MAP §7-B 의
「두 부품 다 `|| 'trend_y'` 로 폴백한다」는 **오늘 거짓**(§D-4).

### A-7. 어드민 `ovCard`의 `extraButtons` — **진짜 죽음(보존 근거가 없다)**
```
자리      admin.js:3651 (인자 선언) · :3666-3673 (구현)
호출자    «0».  `ovCard` 호출부 넷(Overview 카드 4장) 중 어느 것도 이 인자를 안 넘긴다
주변 주석 «0줄». 날짜도, 소유자 지시도, 보존 사유도 없다
```
**판정: 진짜 죽음** — 최소한 「보존 근거가 소스에 없음」.

### A-8. 온톨로지 탐색기의 고아 액션 — **여섯은 진짜 죽음, 넷은 의도적(단 주석이 다른 파일에)**
`ontology_explorer.js` 의 dispatcher 에 분기는 있는데 `client2/src` 어디에서도 그 `data-action` 을 «안 그린다»:
```
의도적 보존 넷   review-draft(:1217) · revise-draft(:1223) · activate-draft(:1232) · discard-draft(:1247)
진짜 죽음 여섯   start-field-text/list/object(:943-951) · add-draft-item(:1005) ·
                remove-draft-item(:1008) · edit-draft-item(:1253)
```
보존 근거 원문 — **핸들러 옆이 아니라 `ontology_explorer_view.js:674-683` 에 있다**:
> 「Review is furniture: the sole operator cannot say what it is for. **The server paths stay; they are
> simply no longer reachable from here.** 🔴 FOUR BUTTONS ON THIS SCREEN, AND ONLY ONE OF THEM IS HERE.
> 　**버튼은 생성, 편집, 저장, 삭제 4가지만 · crud!** (owner, 2026-08-19)」

🔴 **이것이 이 인벤토리가 겨냥한 그 함정의 교과서 사례다** — 「호출자 0」과 「일부러 남김」을 가르는
주석이 **다른 파일에** 산다. 핸들러만 보는 사람에게 넷은 죽어 보이고, 여섯은 **살아 있다는 전제의
주석**(`:945-947` 「The person picked the shape; the screen never guessed it …」)까지 달고 있어
**거꾸로 보인다.**

### A-9. 어드민 `#status-filter` — **딥링크로 들어오면 옵션이 하나뿐**
`applyStatusVocabulary`(admin.js:3554)의 호출자는 `fetchOverview`(:3604) **하나**다.
`admin.html:2179` 의 정적 `<option>` 은 `ALL` 하나뿐이므로, `admin.html#file` 로 «바로» 들어오면
file 분기(:933-938)만 돌고 어휘가 영원히 안 온다(30초 자동 갱신도 같은 분기).
주석 `:3599-3603` 은 반대를 주장한다(「the overview that opens first」) — 그런데 `TAB_ALIASES`(:286)가
`#file`·`?tab=file` 을 받고, `switchTab:601-607` 이 그 상황을 예견해 `console.warn` 을 심어 두었다.
**같은 파일 안의 두 주석이 서로를 반증한다.** 최종 확인은 렌더 → §E.

---

# B. 「UI 가 없는 기능」 — 서버가 내는데 어느 화면도 안 읽는 것

> 방법: 서버 라우트 데코레이터 전수(118) → 라우트마다 `git grep` 으로 클라 소비자를 센다.
> ⚠️ **첫 사흘의 sweep 은 «틀렸었다»** — Git Bash(MSYS)가 `/` 로 시작하는 grep 패턴을 경로로 바꿔 버려
> 존재하는 라우트가 「0건」으로 나왔다. 아래는 **선행 슬래시 없는 패턴으로 다시 잰 수**다.

| # | 라우트 | 서버가 내는 것 | 클라 소비자 | 판정 |
|---|---|---|---|---|
| **B-1** | `GET /health` | `server/runtime/health.py` (498줄) 의 **판정표** — DB·아웃박스·워커 하트비트 | **0** | `client2` 전체(dist 포함)에 fetch 0. `api.js:77 checkServerHealth()` 는 이름과 달리 **`GET /tables`** 를 부른다. 🔴 그런데 클라 주석 «둘»이 그 반대를 적는다 — `admin.js:29` 「판정은 `/health` 가 하고 이 표는 값만 냅니다」 · `runtime_panel.js:6` 「`/health` 는 «판정»을 내고 이 표는 «값»을 냅니다」. 서버 docstring 은 「운영 모니터링용」이라 **화면용이 아닐 수 있다** — 그래도 두 주석은 오늘 거짓이다 |
| **B-2** | `GET /api/maps/overlay` | `server/map_overlay.py` (2,744줄) — **범용 맵 오버레이**(임의 맵들을 타깃 캔버스 좌표로 정렬) | **0** | 맵 에디터의 「＋겹치기」는 이 라우트를 **안 쓴다** — `GET /tables/{src}/data` + 메타로 클라가 직접 겹친다. 저장소에서 가장 큰 서버 모듈 하나가 화면이 없다 |
| **B-3** | `GET /admin/config/notation/preview` | 표기 정규화 선언이 **실제로 무엇을 합치는가**(오병합 점검). docstring: 「`/admin/config/resolve`가 답하지 못하는 절반이다」 | **0** | `/admin/config/resolve` 는 화면이 있다(Overview 「설정 반영」). **그 「나머지 절반」만 화면이 없다** |
| **B-4** | `GET /admin/ledger/config/raw` | `ledger_config.json` 원본. docstring: 「**폼이 유일한 입구가 아니다(소유자 지시 2026-08-15)**」 | **0** | 🔴 **비대칭.** 같은 모양의 원본 편집기가 `chain/rules/raw`(GET+POST)와 `tables/config/raw`(GET+POST)에는 **둘 다 있다**(admin Tables·Chain 탭). 원장만 `LedgerSourcesPanel` 이 **읽기 전용**이고 원본 입구가 없다 |
| **B-5** | `POST /admin/chain/dry-run` | 체인 규칙 하나를 트리거 행 하나에 돌려 보고 결과를 보여 준다. 쓰기 0 | **0** | 화면이 없다. `admin/transfer-plan/dry-run`·`admin/enrichment/auto-confirm/dry-run` 두 드라이런은 화면이 있다 |
| **B-6** | `GET /api/bonding-plan/core-summary` | `server/bonding_plan.py` (1,049줄)의 조회 절반 | **0** | 화면이 없다 |
| **B-7** | `POST /tables/{t}/row_ids/target` | 「Targeted RowID Scanner: 오프셋 리스트 기반 초고속 UUID 추출」 | **0** | 화면이 없다 |
| **B-8** | `GET /tables/{t}/rows/{row_id}/cells/{col}/history` | 셀 단위 이력 | **URL 빌더는 있다 · 도달 불가** | `timeline.js:102` 가 짓지만 그 분기의 스위치(`activeHistoryTab='cell'`)를 세우는 자리가 §A-2 의 죽은 탭 «하나»뿐이다 |
| **B-9** | `GET /api/transfer-plan/validate` | 계획 검증 | **호출부는 있으나 도달 불가** | `transfer_plan.js:1948` 이 부르는데 그 함수 `__held_refreshValidate` 의 호출자가 0. 주석 `:1858-1868`: 「§보류 구역 … 사용자 지시로 이번 범위에서 **미연결** … 재설계 후 다시 붙일 예정이라 **삭제하지 않고** 보관한다」 → **의도적 보존** |
| **B-10** | 온톨로지 탐색기 `POST /drafts/{id}/review` · `/revise` | 검토 요청 / 수정 | **서버 라우트는 산다 · 입구가 닫혔다** | §A-8 — 소유자 판정 2026-08-19 「버튼은 생성, 편집, 저장, 삭제 4가지만」 |
| **B-11** | 저장 계약 모듈 **셋** | `map2/authoring.js`(398) + `brush.js`(316) + `legend.js`(161) = **875줄**. 유효 다이 맵의 **SAVE CONTRACT**(arm→commit, 거절 어휘 8종, 기하 델타, 쓰기 라우트 둘) | **화면 0 · 빌드 0** | 🔴 export 열 개 전부 `client2/src` 안 소비자 **0**. 유일한 소비자는 `client2/tests/map2_authoring_harness.mjs`. 어느 엔트리에서도 도달 불가라 **dist 에 실리지 않는다**(고유 문자열 「기하 변경 - 새 키 필요」 dist 전체 0건). **사용자에게는 존재하지 않는다** |

🔵 **반대로 «완벽히» 맞물린 자리도 있다 — 근거로 적어 둔다.**
WebSocket 이벤트: 서버가 내는 여섯(`batch_refresh_required` · `batch_row_{create,delete,upsert}` ·
`file_ingestion_{progress,completed}`)과 `websocket.js` 가 다루는 여섯이 **정확히 일치**한다.
온톨로지 탐색기 라우트 **15개 전부** 클라 소비자가 있다(내 첫 sweep 이 `/columns`·`/review`·`/revise` 를
「없다」로 읽었는데 **틀렸다** — 셋 다 있다).

---

# C. 🔴 「같은 일에 두 화면 / 두 경로」

> 판별식은 「둘이 «있나»」가 아니라 **「둘이 «갈라질 수» 있나」**다.

### C-1. 🔴🔴 소급 실행 — **요청을 짓는 함수가 «둘»**  (가장 큰 것)
```
같은 라우트  POST /admin/retroactive/{op}/run

① 메인 그리드  client2/src/main.js:199  runRetroactive(op, params)
   맨 fetch + readAdminToken() 으로 헤더를 «직접» 단다
   토큰이 없으면  { ok:false, error:'no admin token on this browser' }  — «묻지 않는다»
   503(토큰 미설정) 분기 «없음»
   실행 «전» 건수 확인 없음

② 어드민       client2/src/admin.js:3505
   adminFetch (:197) 경유 — 401 이면 «토큰을 묻고 저장»하는 기계장치가 붙어 있다 (:28-156)
   503 은 adminFetch 가 이미 토스트를 띄우므로 여기서 두 번 안 띄운다 (:4513-4516)
   실행 «전» GET /admin/retroactive/{op}/count 로 건수를 재고 인라인 확인을 받는다
```
본문 모양은 오늘 **같다**(`{params: <obj>}`). 갈라지는 축은 **토큰·거절·안전장치**다:
브라우저에 토큰이 없는 사용자는 **그리드의 배너가 조용히 죽고, 토큰을 넣을 자리가 어드민에만 있다.**
그리고 CODE_MAP 이 `admin.js` 에 건 불변식(「`fetch(\`${API_BASE}/admin/` 히트가 0이어야 한다 —
히트가 있으면 미설정 서버에선 잘 돌다가 **프로덕션에서만 401** 이 된다」)은 admin.js 에서 **오늘도 0건**인데,
**`main.js:203` 이 정확히 그 모양이다** — 다른 파일이라 그 게이트가 안 본다.

🔵 그리고 같은 라운드의 **부수 사실**: 소급 실행을 «시작할 수 있는 유일한 화면»(어드민)이
그 실행의 **진행 카드를 못 본다** — `progress_card.js`(182줄)는 어드민 번들에 실리지만 그 래퍼 넷의
호출자가 `main.js`·`websocket.js` 둘뿐이고 **어드민은 WS 를 열지 않는다**(`grep -i websocket admin.js` → 0).
어드민은 3초/30초 폴링(`admin.js:2774-2775`)으로만 본다.

### C-2. 🔴 데스크톱 내려받기 — **두 문, 두 산출물, 두 실패 방식**
```
① 툴바 버튼   index.html:75  #desktop-download-btn  ->  main.js:365
   GET /api/desktop/download   ->  desktop/dist/AssyManagerClient.ZIP
   먼저 GET 으로 «묻고» 헤더가 오면 끊는다. 404 면 「데스크톱 빌드가 없습니다」 토스트

② nav 앵커    index.html:308  <a href="/api/download/client" download>📥 Download Desktop</a>
   GET /api/download/client    ->  desktop/dist/AssyManagerClient.EXE  (onefile, 그리고 onedir 폴백)
   맨 앵커. 묻지 않는다. 404 면 브라우저가 «그냥 그 페이지»를 띄운다
```
🔴 **두 라우트가 다른 파일을 서빙한다.** 그리고 `main.js:358-361` 의 주석이 **②의 결함을 이미 묘사한다**:
> 「🔴 그래서 «먼저 물어보고» 이동한다. 바로 이동시키면 404 일 때 브라우저가 JSON 을 띄우거나 아무 일도
> 안 일어난 것처럼 보인다 — **이 프로젝트가 「없는 것을 조용히」로 여러 번 헤맨 그 자리다.**」
같은 주석이 「패키징이 onefile exe → zip 으로 바뀌었다」도 적는다 — 즉 **②는 더 이상 만들어지지 않는
산출물을 가리키고 있을 가능성이 높다.** (박스에서 재지 않았다 — 그건 §E.)
⚠️ 서버 docstring(`main.py:717`)은 「**The button on the admin page**」라 적는데 그 버튼은 **index.html** 에 있다.

### C-3. 걷기 폼 «둘» — **UI 는 둘, 전선은 하나** (양호)
```
walk.html      client2/src/walk/{main,derive,table_view,styles}.js  1,087줄
rnd-board      client2/src/rnd_board/walk_box_panel.js               651줄
```
겹치는 것은 **폼**이고, **요청을 짓는 것은 `createWalkBoxWalk` 하나**다(둘 다 `rnd_board/api.js` 에서 import).
`walk/main.js:1-25` 가 이유를 적어 두었다(§6 인용). **갈라질 수 있는 축은 표현·손잡이뿐이고 전선은 아니다.**
⚠️ 단 **`vite.config.js:38-41` 의 주석이 오늘 거짓**이다: 「부품은 R&D 보드의 `WalkBoxPanel` «그대로»이고
새 부품이 아닙니다」 — walk.html 은 그 부품을 **안 쓴다**(§D-3).

### C-4. 「헤더 포함 복사」 — 두 구현, **두 저장 키**
```
index.html     #copy-header-toggle + #copy-header-menu-toggle  ->  localStorage['copyHeader']
               main.js:834 copyHeaderToggles() 가 «둘을 한 자리»에서 묶는다  (좋은 모양)
map_editor     #map-copy-header-toggle                         ->  localStorage['mapCopyHeader']
               map_editor.js:774, 상수 COPY_HEADER_KEY :6961
```
`map_editor.js:768-773` 이 **의도를 적는다**: 「**새 저장 기계장치를 만들지 않는다** — … 이건 그 프리미티브의
맵 화면 사본이다」. 화면별 설정이라 키가 다른 것은 **설계**일 수 있다. 다만 그 주석의 자리 인용
(`main.js:90` 읽기 / `main.js:528` 쓰기)은 **오늘 틀렸다**(실제 :120 / :836).
**낮은 등급. 갈라질 수는 있고(한쪽 토글이 다른 쪽에 안 보인다), 그것이 의도다.**

### C-5. FOUC 테마 스탬프 — **같은 세 줄이 «여섯 벌» + 주석 사본 하나**
여섯 HTML `<head>` 전부가 `localStorage['theme']` 를 읽어 `data-theme` 를 찍는 인라인 IIFE 를 갖는다.
`theme.js:18-24` 가 **일곱 번째 사본**을 「참고용」 주석으로 들고 있고, 같은 파일 머리가 「**4페이지 공통**」이라
적는다(오늘은 여섯). 구조적으로 강제된 중복이다 — CSS 보다 먼저 돌아야 해서 모듈이 될 수 없다.
그래도 키(`'theme'`)와 기본값(`'light'`)의 저자가 **일곱**이고, index.html 판은 이미 «다른 서식»이다.
**낮은 등급 · 제약이 실재함.**

### C-6. R&D 보드 좌석이 **이 박스의 식별자를 들고 출하된다**
```
client2/src/rnd_board/main.js 의 «주석 아닌» 자리 열셋:
  :174  finalChipId: 'SYN-CX-CHIP-001'      :417/:571 options.finalChipId 같은 값
  :178  waferQuestion: { row: 'SYN-CX-BW-001' }
  :236  scope: 'bond_lot:SYN-K1-201'        :238  scope: 'bond_eqp:SYN-BD-02'
  :436/:587  start: { groupby:'wafer', value:'SYN-CX-BW-001' }
  :467/:614  mapId: 'SYN-CX-BW-001'
  :413/:625/:639  title: '… · SYN-CX-CHIP-001' / '… · SYN-CX-BW-001'
```
다른 설치에서 이 좌석들은 **씨앗이 없어 아무것도 안 그린다** — 그리고 화면 제목에
이 박스의 웨이퍼 이름이 «찍혀» 나간다. 「완성의 정의」(임의의 스키마에서 두 줄로)와 정면으로 어긋난다.

### C-7. `PUT /tables/{t}/data/updates` — **요청을 짓는 자리 «여덟»**
```
api.js:541 (셀 편집) · clipboard.js:612 (붙여넣기) · clipboard.js:861 (비우기) ·
main.js:2052 (트랜잭션 적용) · map_editor.js:4489 (레지스트리) · :6299 (맵 메타) · :6327 (셀) ·
map2/authoring.js:75-76 (WRITE_ROUTES — 오늘 도달 불가, §B-11)
```
🔵 **다만 이것은 «규율이 도는» 사례다.** 갈라질 수 있는 축(`effort` 블록을 싣나)을 실측했더니
**싣지 않는 세 자리가 «전부 사유를 주석으로 달고 있다»** — 「같은 교정 단위라 두 번/세 번 세게 된다」
(`map_editor.js:6297-6300`·`:6330-6336`, `:4485-4487`). 갈라진 것이 아니라 **선언된 차이**다.
⚠️ 다만 `clipboard.js:868` 만 `silent: false` 를 싣는데 **서버는 그 칸을 어디서도 안 읽는다**(전수 0).
여덟 중 하나만 갖고 있는 죽은 칸이다.

### C-8. map_editor vs map_editor2 — **「옆에 선다」는 오늘도 참이다**
`vite.config.js:20-23` 의 문장(「Map Editor 2 stands BESIDE the legacy editor, it does not replace it」)을
라우트 집합으로 검증:
```
map_editor  라우트 14      map_editor2 라우트 9
교집합 «셋», 전부 읽기:  GET /tables · GET /tables/{t}/schema · GET /api/maps/paint-rules
쓰기 교집합 «0»:  구 화면은 PUT …/data/updates 만, 신 화면은 POST /api/maps/alignment/confirm 만
```
겹치는 «능력»은 여섯(대상 테이블 · x/y/value 컬럼 · 좌표계 정하기 · 기준 맵 겹쳐 보기 · 테마 · 엑셀 양식).
그중 **갈라질 수 있는 것**(각자 사본):
```
「이 표가 맵 표인가」      map_table_list.js  vs  map_editor2.js:436-437 인라인
서빙 바인딩 정규화        map_editor.js:170  vs  map2/session.js:99-102  — 같은 응답, 다른 어휘
회전 목록 [0,90,180,270]  map_editor.html:153 하드코딩 · map2/candidates.js:26 · map2/declaration.js:364  — «세 벌»
면 어휘 front/back        map_editor.html:164 · map2/declaration.js:365
좌표계 변환               map_editor.js 내부(export 0)  vs  map2/seating.js  — 완전 별개
범례(값→색)              map_editor.js:299 + split_registry_row.js  vs  map2/legend.js
엑셀 양식 왕복            map_editor.js:7167/:7965  vs  map2/excel_io.js  — «의도된 재작성»(그 파일 머리)
```
갈라질 «수 없는» 것(둘 다 같은 파일 import): `config.js` · `theme.js` · `truncation.js` · `utils.js` · `tsv.js`.
**판정: 중복이라 부르기 어렵다** — 쓰기 경로가 안 겹쳐 같은 행을 두 화면이 덮을 길이 오늘 없다.
다만 **회전·면 어휘 다섯 벌**은 값의 저자가 여럿이고, 그건 언제든 갈라진다.

---

# D. 문서 ↔ 소스 불일치 (전부 오늘 실측)

| # | 문서가 말하는 것 | 자리 | 오늘의 소스 |
|---|---|---|---|
| **D-1** | SSOT 의 엔트리 표 | `SYSTEM_OVERVIEW.md:118-136` | **`walk.html` 행이 «없다».** 엔트리 여섯 중 하나가 SSOT 에 미등재 |
| **D-2** | 「어드민 — 파이프라인 **5탭**」 | `CODE_MAP.md:5170` · **`admin.js:2`** · **`admin.html:1984`** | **일곱**이다. `Tables` 와 `Ontology Explorer` 가 세 곳 다 이름이 없다 |
| **D-3** | 「walk 의 부품은 R&D 보드의 `WalkBoxPanel` «그대로»이고 새 부품이 아닙니다」 | `vite.config.js:38-41` | **거짓.** `walk/main.js:7-11` 이 「그 부품을 «안 씁니다» … 그 파일은 R&D 보드 것이라 못 고칩니다. 그래서 이 페이지가 자기 폼을 갖습니다」라고 **반대를 적는다** |
| **D-4** | 「`control_bar_panel.js`·`main_trend_panel.js` 둘 다 `collect \|\| 'trend_y'` 로 폴백한다」 | `CODE_MAP.md` §7-B | **거짓.** `main_trend_panel.js:94` 는 `\|\| null` 이다(주석이 제거 라운드를 적는다). 남아 있는 폴백은 `wafer_process` 쪽 **셋** |
| **D-5** | 「vite 엔트리 = main·admin·map_editor·map_editor2·graph·trace(·rnd_board)」 | `CODE_MAP.md` §7 도입부 | **거짓.** 오늘 여섯: main · admin · map_editor · map_editor2 · **rnd_board · walk**. `graph`·`trace`·`enrichment` 는 엔트리도 **모듈 파일도 없다**(`graph_viewer.js`·`trace{,_core,_launch}.js`·`enrichment.js` 전부 부재) — 그런데 §7 에 **행이 남아 있다**(:5231~:5259) |
| **D-6** | 「`artifact_gateway` 의 함수들은 일부러 `NOT_IMPLEMENTED` 를 던진다」 | `artifact_gateway.js:4` **자기 자신** · CODE_MAP §7-A | **거짓.** `readArtifact`(:121)·`writeArtifact`(:168) 둘 다 구현돼 `excel_io` 로 위임하고, `NOT_IMPLEMENTED`(:82)는 **읽는 곳 0**. 같은 파일 `:185-187` 이 「The two functions above are implemented and scored」로 **자기 머리를 반박한다** |
| **D-7** | 「Overview 탭에선 (헬스 스트립을) 숨김」 | `admin.html:1960` | **낡음.** 오늘은 `admin.js:577` 이 `updatePanelLayout` 의 조건 밖에서 **모든 탭에서** 숨긴다. HTML 주석과 JS 주석이 서로 다른 말을 한다 |
| **D-8** | 「서버가 그 라우트를 410으로 거절하므로」(Graph Sync) | `main.js:301` | **낡음.** 거절 스텁까지 삭제돼 오늘은 404 다 |
| **D-9** | `main.js:90` 읽기 / `main.js:528` 쓰기 (copyHeader) | `map_editor.js:770` | **낡음.** 오늘 :120 / :836 |
| **D-10** | 「셀 이력 분기는 timeline.js **다섯 자리**에서 읽힌다」 | `main.js:547` | 오늘 **네 자리**(:102 · :595 · :699 · :1079) |
| **D-11** | 줄 수 | 여러 곳 | `admin.js` 4,118 → **4,996** · `map_editor.js` 11,106 → **11,220** · `transfer_plan.js` 1,875 → **1,953** · `ledger_sources_panel.js` 283 → **425** · `ontology_explorer_store.js` 465 → **578** · `closed_list.js` 92 → **132**(호출부 「둘」 → **셋**) · `rnd_board/api.js` 1,567 → **2,000+** |
| **D-12** | map2 모듈 **18개** | `CODE_MAP.md` §7-A | **21개.** `attestation.js`(49) · `origin_basis.js`(54) · `confirm_ruling.js`(86) **셋이 표에 통째로 없다** — 셋 다 `map2/main.js:49-52` 가 import 하는 살아 있는 모듈 |
| **D-13** | `map_editor2.html:36-38` 의 배선 인계 주석 「모듈 엔트리는 아직 붙이지 않았다 … 배선 레인이 `</body>` 직전에 `<script>` 한 줄을 넣고 vite.config 에 항목을 추가한다」 | 그 파일 | **둘 다 이미 끝났다**(`:877`, `vite.config.js:22`) |
| **D-14** | 「`tables`·`isMouseDown` 은 «의도적으로» 남긴 죽은 선언」 | `CODE_MAP.md:4652-4660` | 실측은 **정확**(읽기 0). 다만 **그 판정이 소스 어디에도 없다** — `map_editor.js:76`·`:82` 둘 다 무주석이라 소스만 보는 사람에겐 「죽음」과 「보존」이 구분 불가 |

---

# E. 🔴 못 잰 것

## E-1. 그려 봐야만 답이 나오는 것
1. **여섯 화면이 실제로 뜨는가.** 번들 파싱·런타임 오류 0건을 이 패스는 «안 쟀다». 이 저장소는
   `loadCensus is not defined` 가 운영 번들로 나간 전례(C-56)가 있고, 그 부류는 정적 읽기로 안 잡힌다.
2. **Monaco 가 뜨는가.** `admin.html:14` 가 cdnjs 를 부른다. 망이 막히면 `initMonacoEditor`(:4495)가
   `typeof require === 'undefined'` 로 그냥 `return` 하고 **🛠️ Edit 계열 버튼 다섯이 빈 패널을 연다 — 토스트 없이.**
3. **A-9 의 딥링크 결함.** `admin.html#file` 로 들어가 상태 필터를 펴 봐야 옵션이 하나뿐인지 확인된다.
4. **A-3 의 `readonly`.** 브라우저별 number input 스피너/화살표가 change 를 만드는지는 실행으로만 갈린다.
5. **map_editor2 가 오늘 무엇이든 확정할 수 있는가.** `map_editor2.js:387-395` 가 스스로 경고한다 —
   규칙이 `alignment: true` 를 선언 안 하면 `buildCatalog` 가 안 돌고 규칙 피커가 빈 채로 남는다.
6. **조건부 렌더 컨트롤 전부**: `.btn-retry-file`(FAILED 행) · `.running-x`(`cancellable`) ·
   `.tx-event-pill`(events>1) · `#me2-columns-confirm`(`bindingIsGuess`) · `#me2-index-control` ·
   `#tab-reference`(활성 규칙) · 자재 롤업 패널(stage 선언 + pools>0) — 전부 **데이터가 있어야 존재한다.**
7. **CSS 로 인한 비가시.** 이 인구조사는 인라인 `style.display` 와 `hidden` 만 쟀다.
   z-index·overflow·높이 0 으로 「있는데 안 보이는」 것은 **한 건도 안 쟀다.**
8. **「보이는데 안 눌리는」 컨트롤.** 온톨로지 탐색기는 잠금을 `disabled` 가 아니라
   「`data-action` 을 안 다는」 방식으로 하는 자리가 있어 **원리상 정적 grep 으로 못 가른다.**
9. **C-2 의 ② 가 오늘 404 인가.** `desktop/dist/AssyManagerClient.exe` 의 존재 여부는 «이 박스»의 사실이고,
   운영에 대해 아무 말도 안 한다. **재지 않았다.**

## E-2. 이 인구조사가 «원리상» 못 재는 것
10. **A-5 의 세 라우트가 오늘 503 인가 403 인가.** `ASSY_ADMIN_TOKEN` 설정 여부와 `paths.IS_ISOLATED` 는
    **프로세스 환경의 사실**이다. 소스로 못 잰다.
11. **운영의 값 전부.** 이 문서의 수는 전부 «선언·코드»에서 온 것이고, 행 수·건수는 하나도 안 썼다.
    「없다」로 적은 곳은 **소스에 호출부가 없다**는 뜻이지 운영에서 안 쓴다는 뜻이 아니다.
12. **gitignore 된 것.** `server/config/*.json`(원장·체인·가상조인 선언) · `server/mappers/*.py` ·
    `.claude/settings.local.json`. 🔴 **이 인벤토리의 「이 화면이 무엇을 보여 주나」 중 상당수가 그 선언에 달렸다** —
    좌석의 `follow`, 표의 컬럼, 스켈레톤의 폼 모양, 규칙 목록이 전부 거기서 온다.
    **화면의 «껍데기»는 쟀고 «내용»은 못 쟀다.**
13. **다른 레인이 동시에 착지 중이었다.** 측정 중 `client2/` 가 세 번 바뀌었다 — 줄 수는 밀렸을 수 있다.
    **자리는 심볼로 다시 짚어라.**

## E-3. 세지 «않은» 것 (범위 밖이라고 판단)
14. `client2/tests/**` 하니스 안의 컨트롤·픽스처. 화면이 아니다.
15. `desktop/desktop_wrapper.py` (QtWebEngine 셸). 클라이언트 «화면»의 밖이다.
16. 서버 라우트의 **응답 필드 단위** 소비. 라우트 단위로만 셌다 —
    「라우트는 부르는데 응답의 칸 하나를 아무도 안 읽는다」는 이 패스가 안 쟀다(WebSocket 이벤트만 예외).

---

## 부록: 고아 모듈 — 어느 엔트리에서도 도달 불가한 `client2/src/**.js`

여섯 엔트리의 import 클로저를 계산해 차집합을 냈다. **다섯 개.**

| 파일 | 줄 | 주변 주석 | 판정 |
|---|---|---|---|
| `src/counter.js` | 9 | **없음** — Vite 스캐폴드의 `setupCounter` 데모 그대로 | **진짜 죽음** (잔해) |
| `src/map2/authoring.js` | 398 | 「THE SAVE CONTRACT FOR A VALID-DIE MAP. PURE -- builds and gates a request; sends nothing.」 — **「아직 화면에 안 붙었다」는 말이 없다** | **모름** (§B-11) |
| `src/map2/brush.js` | 316 | 위의 것만 import 한다 | 같은 섬 |
| `src/map2/legend.js` | 161 | 위의 것만 import 한다 | 같은 섬 |
| `src/map2/verdict_placeholder.js` | 108 | 「🔴🔴 **DEAD CODE. DO NOT IMPORT THIS FROM ANYTHING THAT SHIPS.** … **IT IS KEPT ON DISK FOR EXACTLY ONE REASON**: `alignment_verdict_harness.mjs` imports it as the BEFORE side … ⚠️ **IT CONTAINS A REAL DEFECT, LEFT IN PLACE ON PURPOSE**」 | **의도적 보존** (교과서적) |

클로저 크기: index 34 · admin 48 · map_editor 18 · map_editor2 27 · rnd-board 24 · walk 5 모듈.
**어느 화면도 「필요한데 클로저에 없는」 파일을 갖고 있지 않다** — 실측: 여섯 화면 통틀어
인라인 `on*=` 속성 **0건**, 그리고 **모듈 스크립트 태그가 화면당 «하나»**다
(그 밖은 FOUC 테마 인라인 IIFE 하나씩 · admin 만 Monaco CDN 로더 하나 더).
즉 **엔트리 JS 하나가 그 화면의 모든 컨트롤을 소유한다** — 위 클로저가 곧 그 화면의 전부다.
