# ✅ FEATURE_CHECKLIST — 기능 인벤토리 + QA 수동 점검 체크리스트

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (🔴 **§1.7 M4 행 재정정 + §2.9 유효 다이 점검 3건 신설 + §1.12/§2.16 내부 통지 진단 신설** — ① **§1.7 M4 행이 같은 날 두 번째로 거짓이 됐다**: 같은 날 아침 「치수는 참조가 이기고 좌표는 보존·재배치」로 고쳤는데 오후에 **채택 자체가 폐기**됐다(`61440e6`+`94b9baa`, 사용자 지시). 지금 계약은 **아무것도 채택하지 않음** — 거절도 확인창도 없고 마스크가 밀려 보이는 것이 정상. 점검축을 ①Push x/y 불변 ②격자·셀 불변(움직이면 채택 부활 = 회귀) ③info 토스트 1회 ④**치수 차이로 거절하면 회귀** ⑤치수 정의역 `1~100`로 재작성. 하네스 수 정정 **206 → 192 단언 · 변이 16/16**(실행 실측 — 206은 F6 하네스의 수였다). 코드 열의 삭제 심볼 7종에 「소스에 없음」 명기. ② **§2.9에 유효 다이 점검 3건 신설** — 이 기능은 §2.9에 **수동 점검이 한 건도 없었다**. 🎯 핵심은 **"Push가 쓰는 x/y가 지정 전과 같은가"**이고, 그것을 **눈으로 보는 법 3가지**(구조적 확인 / DevTools `replace_map` 페이로드 대조 / 메인 그리드 x/y 컬럼)를 적었다 — ⚠️ **물리 키로 대조하면 이 축은 원리적으로 안 보인다.** ③ **§1.12에 2행 신설**(`23a346d`) — 통지 4xx의 `admin-gate=yes|no` 판별과 `internal_event_session()`의 `trust_env=False`. **`admin-gate=no`면 토큰을 만져도 안 고쳐진다**가 요점. ④ **§2.16에 D절 4건 신설** — 지문·모집단별 REMEDY·기동 프로브·`test_no_sender_builds_its_own_client`(선택자 실행 확인: 4 passed). 직전 **F3 값 제안 2절 신설 + 거짓이 된 3곳 정정** — 소스 대조: `client2/src/value_suggest.js`(`handleEditorKey`의 Escape 갈래·`suggestionsEngaged`), `client2/src/grid.js`(`suppressKeyboardEvent` 첫 분기), `client2/src/api.js:70-71`, `client2/package.json`(`prebuild`), `client2/src/map_editor.js`(`storedCoordRepositionPlan`/`repositionRefusalReason`/`frameDimError`) + 하네스 실행. ① **§1.1에 값 제안 셀 에디터 기능 행 신설** — 이 기능은 인벤토리에 **한 행도 없었다**. ② **§2.1에 F3 점검 11건 신설** — 판정을 키스트로크 수로 쓰고, ⚠️ **`switchTable`이 `txModeActive`를 강제 복귀**시킨다는 절차 경고를 맨 앞에 뒀다(이 함정으로 에이전트 두 명이 각각 한 회차를 날렸다). 🔴 **`Esc` 점검은 두 타이밍을 모두 밟는다** — 목록이 뜬 상태와 안 뜬 상태가 **같아야 하고**, 그 둘이 갈리는 것이 `d5f75a8`이 고친 원래 결함이다. ③ **§2.0 게이트 정정** — `prebuild`가 2행이 아니라 **3행**(`check:suggest-keys` 추가)이고, 판정은 "통과"가 아니라 **APPLIED == CAUGHT**다(변이가 적용조차 안 되면 조용한 무장 해제 — `cb8f01a`에서 18개 중 8개). ⚠️ 게이트 목록의 정본은 `package.json`이고 이 문서는 사본임을 명기. ④ **§1.7 M4 행 정정** — *"저장 좌표가 움직이면 거절"*은 `7873070` 이후 **거짓**(치수는 참조가 이기고 좌표는 **보존·재배치**되며 **표현 불가일 때만** 거절), 점검축을 Push 페이로드 좌표 불변 / 한 수량 한 수 / 치수 정의역 `1~100`로 재작성. ⑤ **§2.9 프리셋 라우팅 항목 정정** — *"HEAD `c9bf2c7` 기준 에디터 동작 불변(클라 절반 미착지)"*은 `73b5925` 이후 거짓. 직전 **문서 없던 기능 5행 신설 + 거짓이 된 2행 정정** — 소스 대조: `server/main.py`(`get_chip_trace`·`get_graph_mapping_summary`·`execute_manual_sync`), `server/graph_orphans.py`, `client/desktop_wrapper.py`(`resolve_server_target`/`base_url`), `client2/src/map_editor.js`(`applyRoutedPreset`·`adoptionCoordinateCost`·`notchMarkCell`). ① **§1.7 프리셋 라우팅 행 정정** — *"HEAD `c9bf2c7` 기준 클라 소비자 없음"*은 `73b5925` 이후 **거짓**(`applyRoutedPreset`가 `loadExistingMap`의 모달보다 앞에서 로드당 1회). ② **§1.7 유효 다이 맵(M4) 행 신설** — 이 기능은 여태 인벤토리에 **한 행도 없었다**. `ae2811c`의 거절 규율(치수 비교가 아니라 **좌표 비교**) 점검 포함. ③ **§1.7 Ctrl+V 행 정정** — 거부 4갈래→**5갈래**(지문 부재는 경고가 아니라 거부), ⚠️ **179개 중 27개만 노치 on-grid = 152개에서 거부되는 것이 정상**. ④ **§1.9 칩 추적 행 신설**(`GET /graph/chip-trace` — depth 없음·다리별 닫힌 어휘 5종·`mapping_unavailable`/`not_reached`의 회귀 점검법). ⑤ **§1.9 재동기화 알림·고아 스윕 2행 신설**(`530fdfd` — 스윕의 요점은 삭제가 아니라 **거절**). ⑥ **§1.9 승격 행에 셀 체인 반영**(폐기 `Chip` 12,468개가 스윕 대상). ⑦ **§1.10 셸 서버 주소 해석 행 신설**(`e9b3a36` — `--server`>`ASSY_SERVER`>`client_settings.json`>기본값, 잘못된 선언은 `exit 2`, **부재는 정상**, 거절 문구가 ASCII여야 하는 이유). 직전 **§1.6에 ①②④ 3건 + §2.8-bis Chain Replay 신설** — 후보 1개 자동 확정(기본 OFF)·결손 원인 분류·룰 승격 제안, R1 재적용/R2 레이어 철회의 시나리오 게이트. 같은 날 **§2.0 「자동 게이트」 신설** — `5a14e77` 실측: `npm run build`의 `prebuild`가 계약 하네스 4종을 돌린다(그전엔 **아무것도 실행하지 않았다** — pytest는 서버 절반만 채점). 발견식 스캔·**빈 스캔은 실패**·개수를 눈으로 확인. **§1.7에 3행 신설**(COPY HEADER MODE 열 폭 병합 · **회사 양식 Ctrl+V 되붙이기** `c9bf2c7` · **프리셋 라우팅 서버 절반** `50bddda` — 클라 소비자 없음 명기), **§2.9에 점검 9건 추가**(왕복 항등 바이트 동일 · 병합 압축 회귀 INV-F1ⓑ-3 · **프레임 지문 노치** · **노치는 데이터가 아니다**(Push 영구 거절 회귀) · **삭제 권한 없음** · 왕복하지 않는 것(자재·COLOR) · 남의 클립보드는 조용히 · 로스터 13개 집합 단언 + **롤업 8단어는 예비** · 프리셋 라우팅 status 6종). 직전 2026-07-29 **7b/7c/M3 `ab6ac02` + 미반영 F1/F2 `17f65bd`** — §1.3에 **맵 메타 자동 등록** 기능 행 신설 + §2.5 점검 3건(양방향 토글·absent-only 불변식·실패 격리/비용), §1.7 오버레이 행에 **서빙되는 바인딩**·전사 계획 행에 **7c untracked / 7b 캐노니컬 바인드** 반영, §2.9 점검 5건 추가(**서빙 바인딩 선언만으로 로드** · **`fallback_guess` 오버레이 거부** · 행 있고 셀 0개 경고 · **`transfer_log: "none"` 어휘 엄격성** · **패딩 키 바인드 양방향**), §2.9 오버레이 기본 흐름의 **정렬 칩 어휘 오기 정정**(`declared`는 정렬 어휘가 아님 — 바인딩 출처 어휘와 혼동). 직전 Gate4/U6/self-frame `deed6d2` — §2.9 점검 4건: **로그형 대상 Push 거부(컬럼명 명시)** · **`map_push_ok` 선언 = 소실 confirm 1회(문자열 오타는 불해제)** · **replace_map 무음 no-op 폐기(400 + 응답 scope)** · **self-frame fail count_only = 미상-not-틀린숫자**, §1.7 게이트 서술 3종→4종·Push 행에 Gate 4/scope 반영. 직전 같은 날: 5b/5c/flatten `0052d76`+`1fefd12`+`0c6ac1a` — §2.5 평탄화 점검 4건(충돌 양쪽 생존·잠긴 가지 보존·토글 오프·force 토큰) + §1.3 기능 행, §2.9 점검 3건: **메타 없는 맵 기본 선택 Push 가능** · **보기만 한 프레임 뒤로가기 무확인** · **count_only 강등 = 미상-not-0**, §1.6 결손 배지 술어를 서버 조성 `queue_filters`로 정정. 직전 같은 날: U6/U7/U3 `95bf072`+`a98dc72` — §2.9 점검 4건 추가: **같은 테이블 연속 빈 맵 로드 = 시드 한 행**(legend 유출 회귀) · **선언 default_legend 색 우선**(autopaint) · **토스트 하단 중앙 배너**(rise 금지) · **브레드크럼 좁은 폭 말줄임**, §1.7 레전드 행에 U6 서버 선언 기본값 반영. 직전 같은 날: U9/U8/H1/H2 — §2.9 **STACK 0 마커·↻ 가용 피드백·적재 대조 게이트 점검 3건 추가** + 새로고침 생존 점검을 **비어 있지 않은 맵 전제**로 강화(`2baf9ff`+`6db517d`), 기능표의 검증 규칙 서술을 **V1~V6 + 게이트 3종**으로 정정. 직전 같은 날: §2.9 맵 라운드 점검 5건(`b35bc9f`+`280ebf0`) + §1.7/§2.9의 band 서술을 zone 모델로 정정. 직전 같은 날: §2.15 C3 config 백업·복원 점검 4건) | **Owner:** Integrity/QA (유지: doc-keeper) | **Source-of-truth:** [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md) · [CODE_MAP](../architecture/CODE_MAP.md)
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
| 범위 일괄 적용 | 범위 선택 후 값 1개를 범위 전체에 적용 | 범위 선택(**마우스 드래그 / Shift+클릭 / `Shift`+방향키** — 2026-07-30 키보드 경로 추가) → 셀 편집 시작(더블클릭/타이핑) → **Ctrl+Enter** 로 편집값을 범위 전체에 적용(시스템 컬럼 제외, Tx 모드면 스테이징) | `ui.applyValueToSelectedRange`(§7) · `grid.js` `defaultColDef.suppressKeyboardEvent` · `grid.js` `extendRangeByKeyboard` |
| 키보드 범위 선택 (2026-07-30) | **손이 키보드를 떠나지 않고** 범위를 잡는다 — 마우스 누름은 공수 계기에서 키 1점 대비 3점이라, 드래그가 필요한 일괄 채우기는 이득 대부분을 반납한다 | 셀에 포커스 → `Shift`+방향키로 사각형 확장(앵커는 포커스 셀, 가장자리에서 클램프) → 값 타이핑 → **Ctrl+Enter**. **평범한 방향키는 범위를 해제**(해제하지 않으면 사용자가 떠난 사각형이 다음 Ctrl+Enter를 받아 의도 밖 셀을 덮어쓴다) · `Esc`도 해제 | `grid.js` `extendRangeByKeyboard`/`visibleRangeColIds` — 선택 모델은 기존 `state.dragStartCell`/`dragEndCell` 재사용(두 번째 범위 구현을 만들지 않음), 렌더는 `clipboard.isCellInRange`/`refreshSelectedRangeDiff` |
| **값 제안 셀 에디터** (F3 · `77a2c15` → Escape 시정 `d5f75a8` · 2026-07-30) | `string` 선언 컬럼의 셀 에디터가 **접두 제안 목록**을 띄우고 **`Enter` 한 번이 후보 채택과 셀 확정을 동시에** 한다(타이머 아님 — AG-Grid가 `suppressKeyboardEvent`를 `cellCtrl.onKeyDown`보다 먼저 부르므로 **같은 이벤트가 확정까지** 수행). 여는 최소 접두 **1**(서버 기본 `min_prefix_length: 0`보다 엄격 — 빈 접두의 첫 후보는 임의 표본이라 `Enter`의 뜻이 사라진다), 요청 한도 **12**, 표시 8행, 디바운스 90ms 트레일링. 컬럼별 학습(플로어·4연속 4xx 비활성·쿨다운)은 **TTL 60초로 만료**(핫리로드되는 `table_config`를 클라 래치가 면제받지 않게) | 그리드 셀 편집 시작 → 1글자 이상 타이핑 | `value_suggest.SuggestCellEditor`/`handleEditorKey` · `grid.buildColumnDefs`(`cellEditor` 갈아끼움) + `defaultColDef.suppressKeyboardEvent` 첫 분기 · `server/value_suggest.py` · [frontend §3.3](../architecture/frontend.md) |
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
| 폴더 드롭 평탄화 (2026-07-28 `0c6ac1a`) | `raws/`에 다중 층위 폴더로 들어온 파일을 뽑아 루트로 승격, 폴더 계층은 제거(**평탄화 후 폐기** — 폴더는 영구 구조로 감시하지 않음). 트리 정온 게이트(1s 스냅샷 연속 2회 동일, 최대 600s), 충돌은 덮어쓰지 않고 상대 경로 `~` 접두 개명(`__` 금지 — `force` 폴더명이 `__force__` 토큰을 조작함), 빈 폴더만 `os.rmdir`(내용물 있는 폴더는 구조적으로 삭제 불가), 잠긴 파일은 가지째 보존+경고 후 300s 스윕 재시도, 정크(`Thumbs.db`/`desktop.ini`/`.DS_Store`/`._*`) 폐기. 핫 토글 `flatten_nested_dirs`(기본 on). 하류 파이프라인(heavy 레인·파서·체크포인트/dedup·archives/err) 무변경 | (자동) `raws/`에 폴더 드롭 | `IngestionHandler.request_flatten/_flatten_directory`(§3) · [INGESTION_GUIDE §1.9](../guide/INGESTION_GUIDE.md) |
| **맵 메타 자동 등록 (M3, 2026-07-29 `ab6ac02`)** | 인제션(**파일 워처·체인 워커 양쪽**)이 `map_key_columns` 선언 + 좌표 바인딩 해석 가능한 테이블에 적재하면, 배치의 **각 distinct 맵 키**에 대해 `wafer_map_metadata` 행을 **부재일 때만** 생성. 종전에는 수동 에디터 push만 메타를 등록해 `bonding_map` 39만 키에 메타 9행이었고 실사용 대부분이 '화면기준' 폴백으로 떨어졌다. 등록 내용은 **정직한 최소치**(배치 x/y bbox 격자·회전 0·마스크 중립 물리 어휘 — 실제 웨이퍼 원은 **추측하지 않음**, M4 방향), 소스 `auto_map_meta` = **최하위 우선순위**라 사용자 편집이 항상 이김. **절대 덮어쓰지 않음.** 확장성은 distinct 키당 인덱스 존재확인 1회 + 프로세스 수명 캐시. 실패해도 데이터 적재는 정상 완료(격리). 끄는 법 `ingestion_settings.json` `auto_register_map_meta: false`(기본 true, 핫리로드). ⚠️ **기존 메타 없는 키의 소급 백필은 미실행(M4 결정)** | (자동) 맵 테이블에 파일/체인 적재 | `server/map_meta_registrar.py` `MapMetaCollector`(§5) · `_send_to_upsert`(§3) · `process_chain_transaction_group` · [INGESTION_GUIDE §1.10](../guide/INGESTION_GUIDE.md) |
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
| 결손 배지 | 메인 그리드에 "🧩 결손 N건" 배지 → 클릭 시 해당 규칙 컨베이어로 진입. 표시 조건: 현재 테이블이 규칙의 **source_table 또는 derived_table 어느 쪽과 일치해도** 표시(원본 테이블 화면 포함), 결손 카운트 > 0일 때만. **[2026-07-28 `1fefd12`] 결손 술어는 서버 단일 조성 `queue_filters`**(모든 판단키 notBlank AND 모든 target blank — 빈 판단키 행은 큐 제외, [ENRICHMENT_QUEUE_SPEC §5.1](../spec/ENRICHMENT_QUEUE_SPEC.md)) — 워크리스트·어드민 카운트·배지가 같은 객체를 소비해 수치가 갈릴 수 없음. 규칙 API 부재/카운트 0/조회 실패 시 무음 숨김(TTL 캐시 + WS 디바운스 갱신) | 메인 툴바 `enrichment-badge` | `ui.updateEnrichmentBadge/notifyEnrichmentTableEvent`(§7) |
| 레이어링 보존 | 사람이 채운 값은 source=user(priority 0) — 재인제션·dedup 재실행이 덮지 못함 | (불변식) | `compute_priority_value`(§2) · 스펙 §6 |
| **① 후보 1개 자동 확정 (2026-07-30)** | 참조뷰에 `candidate_for: {target: 뷰_컬럼}`이 **선언된** 경우에만, 그 뷰가 판단키에 대해 **유일값 하나**를 낼 때 체인 워커가 target을 **부재 시에만** 채움. 규칙별 노브 `auto_confirm` **기본 OFF**(이 필드의 blank가 큐 소속을 정의하므로 오확정은 항목을 워크리스트에서 빼버린다 — M3 `auto_register_map_meta`와 형태는 같고 기본값만 다름). 소스 `enrichment_auto_confirm` = `SOURCE_PRIORITY` 미등재 = **최하위(99)** 라 사람 편집이 항상 이김. **컬럼명 유추 없음** — 같은 규칙의 두 뷰가 모두 `wafer_id`를 갖고 한쪽은 후보 N개인 실제 config가 그 근거. 거절은 전부 이름 있음(`ambiguous`=사람의 판단 · `view_error`/`missing_bind`=평가 불가 → 살아남은 뷰가 값 1개를 내도 **거절** · `cell_has_provenance`=사람이 지운 값 보호 · `over_cap`). 작업 단위 상한 `enrichment_auto_confirm_max_keys`(기본 200) 초과분은 **큐에 남고 건수 로그** | (자동) 원본 인제션 시 · 측정은 `enrichment_insights.py confirm --ignore-knob` | `enrichment_candidates.resolve_target_candidate/AutoConfirmCollector` · 체인 훅 `process_chain_transaction_group` · [ENRICHMENT_QUEUE_SPEC §5.2](../spec/ENRICHMENT_QUEUE_SPEC.md) · [config/enrichment_rules §7](../guide/config/enrichment_rules.md) |
| **④ 결손 원인 분류 (2026-07-30, 읽기 전용)** | 큐를 원인별로 나눔: `mapping_gap_same_name`(**소스에 값이 있는데 안 옮겨졌다 = 파이프라인 버그**, 사람이 갚을 일이 아님) · `resolvable_from_reference`(①이 처리) · `ambiguous_reference`(진짜 사람의 판단) · `no_evidence`(소스에 원래 없다) · `no_source_rows` · `unprobed`(탐색 예산 초과 — 다른 분류로 접어넣지 않음). 한계 명시: 버그 분류는 **소스의 같은 컬럼명**으로만 판정하며 다른 이름은 **추측하지 않음** | `enrichment_insights.py classify <규칙>` | `enrichment_analysis.classify_queue` · [ENRICHMENT_QUEUE_SPEC §5.4](../spec/ENRICHMENT_QUEUE_SPEC.md) |
| **② 반복 판단 → 룰 승격 제안 (2026-07-30, 제안만)** | 사람이 채운 셀(`CellSource.source_name == 'user'`)만 훑어 `decision_key`의 **진부분집합 → target** 함수적 종속을 찾고 **`reference_views` 항목 + `candidate_for`** 형태로 제안(이 시스템이 이미 실행하는 형태 — 새 맵퍼 없음, ①이 실행). **config는 절대 쓰지 않음.** 충돌(같은 선행부 → 서로 다른 값)이 하나라도 있으면 제안하지 않고 **거절 이유를 보고**. 단일 컬럼 판단키는 `no_proper_subset` | `enrichment_insights.py propose <규칙> --min-support N` | `enrichment_analysis.analyze_promotions` · [ENRICHMENT_QUEUE_SPEC §5.3](../spec/ENRICHMENT_QUEUE_SPEC.md) |

### 1.7 웨이퍼 맵 에디터 (`/map_editor.html`)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 맵 로드/저장 | 테이블 데이터 → 캔버스 맵(REST pull), 편집 후 저장(REST push, 배치 업서트). **WS 미사용** | 로드: 좌측 패널 "📂 Load Existing Map" → 로드 방식 선택 모달(📐 Standard / ⚙️ Use Current Left Panel Settings / ❌ Cancel). 저장: 작업영역 툴바 "⚡ Push Map Data" → **[Gate 4 `deed6d2`] 대상이 로그형(맵 계약 밖 데이터 컬럼 보유)이면 모든 다이얼로그 이전에 거부**(table_config `map_push_ok: true` 선언 테이블만 소실 confirm 1회로 완화) → 메타데이터 필드 미입력 시 `alert` 차단, 이후 `confirm("총 N건의 활성 맵 데이터를 '{table}' 테이블에 덮어쓰기 적재(Clean Replace)하시겠습니까?")` 확인 후 전송. 서버 응답 `scope: {filters, deleted, inserted}`가 실제 purge 범위 보고(범위 미파생 = 400, 무음 no-op 폐기) | `loadExistingMap/pushMapData`(§7) · [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) |
| 지오메트리 프리셋 | 웨이퍼 지오메트리 프리셋 저장/불러오기/삭제 | 프리셋 UI | `/map-presets` CRUD · `fetchAndRenderPresets/saveCustomPreset`(§1.4/§7) |
| 브러시 페인팅/레전드 | 셀 값 브러시 페인팅, 레전드 편집(localStorage `map_legend_{table}` 유지). **[U6 `95bf072`] 빈 맵 시드·자동 추가 값의 색/설명·값 컬럼 자동 탐지 목록이 전부 서버 선언**(paint-rules의 `default_legend`/`value_column_candidates` — [MAP_EDITOR_SPEC §5.6](../spec/MAP_EDITOR_SPEC.md)) — 클라 builtin 목록·고정 E1/E2 색 삭제 | 레전드 테이블·브러시 선택 | `selectBrush/renderLegendTable/load·saveLegendToStorage/autoAddLegendValue`(§7) |
| 좌표 변환(회전/면반전) | FRONT/BACK 전환·회전 시 물리 좌표 불변(칩 스탬프, 워터마크 표시) | FRONT/BACK 툴바 칩·회전 컨트롤 | `getPhysicalCoords` 계열(§7) · [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) 불변식 |
| 엣지 자동 페인팅 | 엣지 셀 분류·선택·E1/E2 자동 페인팅 | 작업영역 툴바 "🔍 Select Tools" 드롭다운 → "✔️ Select E1" / "✔️ Select E2" / "⚡ Auto-Paint E1/E2" (같은 드롭다운에 "📍 Set Origin (0,0)") | `getEdgeClassification/selectEdgeCells/autoPaintE1E2`(§7) |
| 엑셀 복사 (+ **COPY HEADER MODE**) | 그리드를 클립보드로 복사 — `text/plain`(TSV)과 `text/html`(서식) **둘 다** 싣는다. **COPY HEADER MODE 토글**(`localStorage['mapCopyHeader']`)을 켜면 사용자 회사 본딩맵 양식으로 나간다: 상단 `TITLE`(`테이블 · 맵키`) + 열 그룹 띠(맵키 그룹·1H·MID·TOP) + 우측 보조표 `VALUE \| COUNT \| STACK \| DESC`. `COUNT`는 범례 뱃지·DOE 패널·Push와 **같은 집계**(`eachSavableCell`). **[`5a14e77`] 열 폭은 글자 수 비례 병합**(`headerSpanFor`+`distributeSpans`, 최대 잔여법으로 모든 행의 열 합계 일치) — 종전에는 헤더 칸 = 맵 셀 하나(32px)라 `MIDLOT_01`이 잘렸다 | 작업영역 툴바 "🛠️ Edit Grid" 드롭다운 → "📋 Copy to Excel" (+ COPY HEADER 체크박스) | `copyGridToExcel`(§7) · [MAP_EDITOR_SPEC §4-ter](../spec/MAP_EDITOR_SPEC.md) |
| **회사 양식 되붙이기 (Ctrl+V)** (F1ⓑ, `c9bf2c7` 2026-07-30) | 위 양식을 **격자로 되읽는다** — 왕복의 나머지 절반. 격자는 **빈 칸까지** 복원, DOE는 `VALUE`·`STACK`·`DESC`만 복원. **`COUNT`는 알아보되 버리고**(칠한 셀 수는 격자에서 센다), **자재(1H/MID/TOP)·COLOR는 왕복하지 않는다**(상단 그룹 띠는 의도적으로 읽지 않음 — 평문에서 "빈 그룹"과 "병합 연장"이 같은 문자라 구별 불가). 🔴 **붙여넣기는 값을 지우지 않는다**(복사본에 없는 값 = "말하지 않은 것"). 거부 **다섯** 갈래: 열 수 · 행 수 · 정체(TITLE) · **프레임 지문 불일치** · **프레임 지문 부재**(`ae2811c` 신설) — 노치 `D`는 치수가 같은 채 회전/면만 바뀐 경우를 잡는 유일한 신호이고, **자리가 격자 밖이면 대조 자체가 불가능하므로 거부한다**(종전에는 통과 후 확인창 경고 한 줄이었고, 실측 12×10 마스크 없는 격자에서 rot 0 복사본을 rot 180에 붙여 **물리 키 120개 전부의 값이 바뀌었다**). 🔴 **점검 시 반드시 확인**: 선언 맵 **179개 중 노치 on-grid는 27개** — **나머지 152개에서 붙여넣기는 정상적으로 거부되는 것이 맞다**(고장 아님). 지문 술어는 복사·붙여넣기 공유(`notchMarkCell` — **칠해진 노치 셀은 지문 없음**이라 "회전·면이 다릅니다"가 아니라 부재 사유로 거부되고, 값이 진짜 `D`인 셀은 **비워지지 않는다**). 노치는 적용 시 **버려진다**(안 그러면 저장 불가 셀이 생겨 적재 대조 게이트가 그 맵을 영구 거절) | **Ctrl+V** — 새 버튼·메뉴 **0개**(운영은 평문 HTTP라 `navigator.clipboard` 부재, `execCommand('paste')` 차단 → 네이티브 `paste` 이벤트가 유일). 확인창 **1회**, **서버 쓰기 0** | `onMapGridPaste`/`readCompanyMapBlock`/`checkPasteAgainstFrame`/`applyPastedGridRows`/`applyPastedAuxRows`(§7) · [MAP_EDITOR_SPEC §4-ter](../spec/MAP_EDITOR_SPEC.md) · 사용자 안내 [DOE_GUIDE §4.2](../guide/DOE_GUIDE.md) |
| **로드 시 프리셋 라우팅** (F5 서버 `50bddda` + **클라 `73b5925`** 2026-07-30) | `(table, map_key)` → 이 맵을 열 물리 규격(프리셋)을 **선언에서** 결정. 순서가 계약: ①제품코드 조회 테이블 → ②순서 있는 텍스트 패턴(첫 매치 승리) → ③라우팅 없음. **절대 우선순위 `wafer_map_metadata` > 라우팅 > 패널**을 서버가 강제(등록된 규격이 있으면 `meta_present` + preset `null`). ①의 미선언·miss·테이블 부재는 **전부 정상 경로**(조회 테이블은 운영에만 있고 불완전) — 경고 아님, 결과는 `lookup.status`로만. ✅ **클라 절반 착지(`73b5925`)** — 소비자는 `loadExistingMap` **한 곳**(`applyRoutedPreset`), `!loadedGridMeta`일 때 **좌표계 선택 모달·`standard`/`current` 분기보다 앞**에서 호출(그 분기가 패널을 읽으므로 그 순서여야 "라우팅 > 패널"이 성립). **로드당 1회.** 점검할 것: ① 메타 있는 맵은 요청 자체가 안 나가는가 ② 메타 없는 맵에서 **좌표계 선택 모달은 여전히 뜨는가**(폐기되지 않았고 ⚙️의 뜻만 "라우팅이 채운 규격"으로 바뀜) ③ 적용 시 **알림이 남는가**(`c24d47b` 토스트 정리에서 명시적으로 유지 — 적용은 눈에 보이는 변화다) ④ HTTP 실패·`status != ok`가 **강등 없이 조용히** 종전 동작(패널 그대로)으로 가는가 | 맵 로드(📂 Load) — 새 컨트롤 0개, 끄는 스위치 없음(라우팅은 첫 열기 기본값이고 실제로 만드는 것은 첫 ⚡ Push) | `server/map_preset_routing.py` · `applyRoutedPreset`(§7) · `GET /api/maps/preset-routing`(§1.2) · [MAP_EDITOR_SPEC §5.8/§5.8-bis](../spec/MAP_EDITOR_SPEC.md) · 선언 절차 [config/map_overlay_config §2-bis](../guide/config/map_overlay_config.md) |
| **유효 다이 맵 (M4 — 원이 아닌 모양)** (`4d973d6`+`91386f0` → 채택 `73b5925`→`ae2811c`→`7873070`→`d4b9660` → 🔴 **채택 전량 철회 `61440e6`+`94b9baa`**) | "이 셀이 유효한가"의 근거를 **원 기하 대신 다른 맵 하나**로 둔다(`valid_die_ref`). 지정 없는 맵은 **완전 무변경**(순 가산). 저작은 프리셋 드롭다운의 `🧩 유효 다이 맵 만들기` → 평소처럼 칠하고 `⚡ Push` → 쓸 맵의 `🎯 유효 다이 맵` 칸에 키 넣고 `⚡ Push`. 참조는 **1단계까지**(순환·자기참조 거부), 참조가 안 풀리면 **조용히 원으로 돌아가지 않고 사유와 함께 거부**. 🔴 **점검의 핵심 — 참조 맵과 격자 치수가 다를 때: 아무것도 채택하지 않는다**(사용자 지시 2026-07-30). 치수도 물리 규격도 회전·면도 가져오지 않으므로 **거절도 확인창도 없고**, 마스크가 참조 자신의 격자 기준으로 그려져 **화면에서 밀려 보이는 것이 정상**이다. 확인할 것: ① 🎯 **`⚡ Push`가 쓰는 x/y가 지정 전과 완전히 같은가** — 이 라운드에서 유일하게 중요한 축이다(눈으로 보는 법은 §2.9). ② 격자 크기 입력칸·칠한 셀 위치가 **한 픽셀도 안 움직이는가**(움직이면 채택이 되살아난 것 = 회귀) ③ 밀림 알림이 **info 토스트 1회**인가(확인창이면 회귀 · 같은 지정 반복에 중복 안 뜸 — `dedupeKey`) ④ 치수가 다르다는 이유로 **거절하지 않는가**(거절하면 회귀 — 사용자가 두 번 뒤집은 동작이다) ⑤ 참조 메타의 `grid_cols/rows`가 **1~100 정수 밖**이면 셀 조회 전에 거절하는가(1024×1024 메타 행으로 확인 — clamp하면 회귀. **이것이 살아 있는 유일한 거절이다**) | 프리셋 드롭다운 `🧩 템플릿 만들기` · 물리 규격 블록 `🎯 유효 다이 맵`(맵 키 칸 클릭 시 자동완성, 상한 500) · 되돌리기 = 키 칸 비우고 `⚡ Push` | `resolveValidDie`/`frameDimBounds`/`frameDimError`/`projectCellsToPhys`/`isValidDieAt`(§7) · `map_overlay.resolve_valid_die_basis`(§5) · [MAP_EDITOR_SPEC §5.7/§5.7-bis](../spec/MAP_EDITOR_SPEC.md) · 사용자 안내 [VALID_DIE_MAP_GUIDE](../guide/VALID_DIE_MAP_GUIDE.md) · 회귀 그물 `client2/tests/valid_die_frame_adoption_harness.mjs`(**192 단언 · 변이 16/16**, 2026-07-30 실행 실측) · 양측 채점 `contracts/map_seam/`. ⚠️ `adoptFrameSpec`/`storedCoordRepositionPlan`/`applyStoredCoordReposition`/`repositionRefusalReason`/`adoptionCoordinateCost`/`dbCoordsByPhysKey`/`announceFrameAdoption`은 **소스에 없다**(`client2/src/` 0건) |
| 테이블 간 맵 이월 | 테이블 A→B 전환 시 유지/초기화 확인창(컬럼명 상이 시 Advanced Column Mapping 수동 확인 필요 — 이슈 #2) | 테이블 전환 시 자동 확인창 | history `a41007e` |
| 페인트 잠금 (M2, 2026-07-26) | 특정 값(기본 `F`)의 셀을 편집 불가로 잠금. **선언 정본이 서버**(`config/map_overlay_config.json`의 `paint_lock`)로 이동 — 종전 클라 하드코딩 `'F'` 대체. **조용한 fail-open 제거**: 404/405만 "선언 없음"(해제), 네트워크·5xx는 직전 잠금 유지 + `⚠ 잠금 규칙 미확인` 툴바 칩 + 경고 토스트. 모든 편집 경로가 `isProtectedFCell` 단일 관문 통과. ⚠️ **콜드 스타트(페이지 로드 후 첫 조회 실패)는 아직 잠금 없이 시작**(QA C4 미해소 — 칩은 뜨나 잠기지는 않음) | (자동) 맵 로드 시 규칙 조회 · 툴바 잠금 칩 | `fetchPaintRules/isProtectedFCell`(§7) · GET `/api/maps/paint-rules`(§1.2) · `map_overlay.get_paint_rules`(§5) |
| **범용 맵 오버레이** (M2 → `7d931dc` 클라 일원화, 2026-07-26) | 임의의 맵을 임의의 맵 위에 겹쳐 본다(계획 전용 아님, **맵 인프라**). **좌표 변환은 클라 단일 구현** — 소스 원본 좌표를 소스 자신의 `wafer_map_metadata` 프레임으로 해석해 물리 키로 투영하므로, 사용자가 화면 규격(회전·면·치수·물리값)을 바꾸면 **메인 맵과 오버레이가 함께 움직인다**. 셀 상한 2,000(메인 로드와 동일, 초과 시 `truncated`). 레이어별 색점 마커·표시 토글·정렬 상태 칩(`align.origin` 기준 — `무보정`/`정렬됨 N°`). 명명된 실패 status **4종**(`meta_unavailable`/`binding_unavailable`/`align_unavailable`/`no_data`, + IO 실패는 일반 `error`) 전부 **그리지 않고 목록에 행으로 남음**(재시도 버튼 유지). *(구 `align_unconfirmed`·`align_override_declared`는 서버 선언 레이어와 함께 2026-07-27 삭제 — 물어볼 선언이 없어졌고 REST 왕복도 하나 줄었다)* **[F1/F2 `17f65bd`] 좌표 바인딩은 이제 서버가 해석해 서빙한다**(paint-rules의 `binding` — 선언 > 유도, `{x,y,val,key_columns,source}`): 클라 자체 유도 ~40줄과 대소문자 무시 x/y 매칭기가 **삭제**됐고, 그래서 `table_bindings`에 선언만 있으면 대문자·한글·숫자 시작 테이블명이나 `tx`/`ty` 좌표도 **선언만으로 로드·오버레이된다**(사용자가 보고한 "오버레이 설정이 안 먹는다"의 실제 원인 — 서버는 존중하는데 클라가 읽지 않았다). 값 컬럼이 후보에 하나도 안 맞아 **추측**된 경우 `source: "fallback_guess"`로 표기되며 **오버레이 경로는 거부**한다(로드 경로는 경고 후 진행) — 추측 컬럼을 칠하면 미끼 셀이 된다 `📥 가져오기`는 `gridData`로만 반영(서버 쓰기 없음, 잠금 존중, 격자 밖 제외). **메인 맵 로드와 코드 경로 완전 분리**. **기준이 바뀌면 해제**(맵 로드·테이블 전환·프레임 진입). ⚠️ 정렬은 `wafer_map_metadata` 등록 맵에서만 실제로 일한다(§5.0 — 미등록은 `무보정` 폴백) | 맵 에디터 오버레이 블록 `＋ 겹치기` | `addOverlayLayer/projectCellsToPhys/syncOverlayGeometry/importOverlayToGrid`(§7) · GET `/api/maps/overlay`(§1.2 — **맵 에디터 클라는 이 엔드포인트를 호출하지 않는다**. 선언 probe가 사라지면서 마지막 호출처가 없어졌고, 서버 경로는 `bonding_plan`/`transfer_plan` 가용량 산출이 쓴다) · `server/map_overlay.py`(§5) · [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md) |
| **전사 계획 사이드바** (M2-v2, 2026-07-26) | **「계획 = 지금 열어 편집 중인 그 맵」** — `bonding_map`을 열면 본딩 계획, `dt_map`을 열면 DT 계획. stage는 열린 테이블에서 유도(선택 UI 없음), `plan_id`·계획 맵 사본 없음. legend = **DOE 아코디언**(값 = 조건군 = `map_split_registry` 행 하나). **[ZONE 2026-07-28 `b35bc9f` — band 모델 대체]** 층 구조는 행의 **`stack`(총 층수) + 고정 구역 셋**(`mat_1h`=1층 · `mat_top`=STACK층 · `mat_mid`=그 사이 전부, 1H/TOP이 비면 MID가 그 끝까지)이고, 수량은 저장하지 않고 파생한다(`칠한 셀 수 × 구역 층 수`, 매당 `ceil` — 합을 먼저 내고 나눔). **[U9 2026-07-28] STACK `0` = 상태 표시 값(마커)** — 구역 해당 없음·소요 0·롤업 부재, 마커 행은 V6(구역에 자재가 남은 모순) 하나에만 답한다. 검증 규칙은 V1~V6(정본 `contracts/doe_band_rules/vectors.json` v3)이며 **보고만 하고 저장을 막지 않는다** — 저장을 막는 것은 데이터 보호 게이트 4종(zone 컬럼 없음 · legacy 해석 불가 · 적재 대조 · 로그형 대상, [MAP_EDITOR_SPEC §6.0-ter](../spec/MAP_EDITOR_SPEC.md)). 🗄️ `bands`는 폐기·읽기 전용(표현 불가 레거시 행은 접지 않고 거부). 패널은 서버에 직접 쓰지 않고 legend 저장 경로 하나로 씁니다. 자재 목록 DOE별 그룹 + `openMaterial`이 맵 간 이동의 유일 허브(브레드크럼·뒤로가기). 자재 가용은 `가용 = 총 − (fail ∪ 기전사)`. **서버가 degraded면 `remaining`이 `null`로 오고 클라는 이를 초록으로 뒤집지 않는다.** **[7c `ab6ac02`] 소모 기록이 아예 없는 사이트는 `transfer_log: "none"`을 선언**해 `connected(untracked)`(강등 아님)로 갈 수 있다 — `transferred`는 가짜 0이 아니라 `null`, `remaining`은 `null` + 진짜 상한 `remaining_upper_bound` + 경고 `transfer_untracked`(클라는 `미상` 대신 `≤N` 렌더 가능). **정확히 문자열 `"none"`만 선언이고 JSON `null`·키 삭제는 종전 `missing` 그대로**. **[7b `ab6ac02`] 풀 바인드·맵 정체성 조합은 선언 컬럼 타입으로 캐노니컬화**된다(`number` 선언이면 `'01'`=`' 1 '`=`1.0`=`'1'`) — 패딩 어긋남으로 가용이 0으로 보이거나 메타를 못 찾던 결함의 수리. 검증/경고 UI는 **미구현**(사용자 지시 보류 — `__held_*` 구역) | 맵 에디터 우측 사이드바(맵 로드 시 자동) | `transfer_plan.js`(§7) · GET `/api/transfer-plan/{stages,source-summary,validate}`(§1.2) · `server/transfer_plan.py`(§5) · [MAP_EDITOR_SPEC §6](../spec/MAP_EDITOR_SPEC.md) |
| 본딩 실험계획 (M1) — **UI 대체됨** | M1의 조회 전용 Info 패널(`bonding_plan.js`/`.css`)은 `8e34804`에서 **삭제**되고 위 전사 계획 사이드바로 대체됐습니다. **서버 API `GET /api/bonding-plan/core-summary`와 `server/bonding_plan.py`는 존치**하며, `transfer_plan`의 core-kind 경로가 여기에 위임합니다 | (직접 UI 없음 — 전사 계획 경유) | `server/bonding_plan.py`(§5) · GET `/api/bonding-plan/core-summary`(§1.2) |

### 1.8 어드민 대시보드 (`/admin.html`) — 파이프라인 생애주기 5탭 IA (2026-07-25 재편)

탭 축은 **파이프라인 생애주기 5탭**(`#overview/#file/#chain/#autoupdate/#enrichment`) + 코드 에디터 **공용 뷰**(`#editor=<path>` 딥링크). 구 해시 별칭(`#outbox→#chain` 등) 호환 유지.

> 🔒 **2026-07-27(`90e284f`)부터 아래 탭이 부르는 `/admin/*` API는 전부 공유 토큰 게이트 뒤에 있다.** 페이지(`GET /admin.html`) 자체는 열려 있으므로 화면은 뜨지만, 토큰이 없으면 **모든 표가 비어 있고** 클라가 토큰을 한 번 묻는다. 게이트 자체와 점검 절차는 **§1.12 / §2.16**에 있고, 이 절은 게이트를 통과한 뒤의 기능만 다룬다.

| 탭/기능 | 설명 | 코드 |
|---|---|---|
| Overview | 파이프라인 4카드(File/Chain/AutoUpdate/Enrichment) 헬스 요약 + 최근 이벤트 + 각 탭 딥링크. 상단 파이프라인 헬스 스트립 공용 | `fetchOverview/renderOverview` · `parseRoute/applyRoute/switchTab`(§7) |
| Overview 상단 **핵심가치 #1 두 줄** | **재교정률**(사람이 같은 셀을 두 번 이상 고친 비율 — 보조 계기) + **교정 공수**(한 교정 완료까지의 상호작용 점수 = 정본 계기, 2026-07-29 신설). 두 줄이 `/dashboard/summary` **한 응답**을 공유하고 5분 스로틀 하나를 쓴다(무거운 엔드포인트라 Overview 자동 갱신 루프에 태우지 않음). 점검 시 확인할 것: ① 값 옆에 **분모/커버리지가 항상 함께** 있는가 ② 값이 없을 때 `0`이 아니라 **`—` + 사유**인가 — 특히 `measured_ratio === 0`(사람 교정은 있는데 계측 0건 = **수집 중단**)이 danger 톤 경고로 뜨는가, 응답에 `effort` 필드가 아예 없을 때 "교정 없음"이 아니라 "**서버가 보고하지 않음**"이라고 하는가 ③ 카드·패널·차트·새 탭이 생기지 않았는가(한 줄 유지) | `renderRecorrection`/`renderEffort`/`refreshCoreValueLines`(§7) · [frontend §5](../architecture/frontend.md) |
| File | 파일 인제션 로그/실패 목록·재처리 + 워크스페이스 현황 + 파서 스크립트 편집 딥링크 | `renderFileTable/retryFileIngestion/renderWorkspaceTable/selectFileRow` · `/admin/file-ingestion/*` |
| Chain | outbox 실패/대기 트랜잭션 재시도 + 체인 룰·맵퍼 목록 + 이벤트 진단(Edit Mapper 딥링크) | `renderOutboxTable/renderChainTable/renderMapperTable/showEventDiagnostics` · `/admin/outbox/*`·`/admin/chain/rules`·`/admin/mappers/list` |
| AutoUpdate | 수집기 상태·즉시 실행·**Active 토글**(§1.4) + 산출물 인제션 실패 교집합(`renderLinkedFailTable`) | `renderAutoUpdateTable/toggleCollectorActive/runAutoUpdateNow` · `/admin/auto-update/*` |
| Enrichment | 규칙별 결손 현황(15s TTL 캐시 — 스트립·탭·Overview 공용) + 컨베이어 딥링크 | `renderEnrichmentTable/fetchEnrichmentStatus` · `/enrichment/rules` |
| Code Editor(공용 뷰) | Monaco(CDN) 파일 피커 + 스크립트 편집·저장(인라인 폴백, dirty confirm) — 각 탭에서 `#editor=<path>` 딥링크 진입 | `initMonacoEditor/populateEditorPicker/selectEditorFile/saveScriptCode` · `/admin/scripts/*` |
| Config Reload | `table_config.json` 등 핫리로드(+SYSTEM_RELOAD 전파로 워커도 리로드, 신규 테이블 물리 CREATE 포함) | `reloadSystemConfigs` → POST `/admin/reload-configs`(§1.4) |

### 1.9 온톨로지 그래프 (승격·뷰어·추적)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 온톨로지 그래프 승격 | outbox 증분 소비 → `ontology_mapping.json` v2 매핑대로 PG 엣지 스토어(graph_nodes/edges) 자동 materialize(provenance 포함). 수동 트리거는 백필/복구용. **[`aea4700` 2026-07-30] 현행 선언은 「셀 체인」이다** — `CoreCell(core_lot,core_slot,cx,cy)`가 `bonding_log`·`dt_log` 양쪽의 행 노드이고 `BONDED_TO→BaseCell` · `TRANSFERRED_TO→DtCell` · `FROM_CORE→Core`. **폐기 형태**(`Chip`/`log_id` · `BONDED_FROM→Wafer` · `PLACED_ON→Base`)의 노드가 라이브에 잔존하며(`Chip` 12,468개) 아래 고아 스윕 대상이다 | (자동) + 메인 툴바 `graph-sync-btn`(백필) | `graph_sync_worker.py`+`graph_materializer.py`(:8090) · [event_driven_backend §4](../architecture/event_driven_backend.md) · [ONTOLOGY_GRAPH_SPEC §3](../spec/ONTOLOGY_GRAPH_SPEC.md) |
| **재동기화가 자기 선언을 알린다** (`530fdfd` 2026-07-30) | `execute_manual_sync`는 매 호출마다 파일을 다시 읽지만 materializer 루프는 **자기 메모리 사본**을 들고 있고 그 사본은 outbox의 `SYSTEM_RELOAD`로만 교체된다 — 그래서 "매핑 고치고 재동기화했다"가 **루프를 옛 선언에 남겨 두었다**(라이브 실측: 40분간 파일에서 사라진 라벨로 노드 25개 계속 생성). 지금은 **파일을 읽어 반영한 모든 경로**에서 `SYSTEM_RELOAD`를 직접 발행한다 — 완료된 재동기화 **그리고 `no_mapping` 두 갈래 모두**(선언을 지우고 돌리는 것이 같은 구멍이다). 없는 테이블 이름의 400은 발행하지 않는다(읽어서 반영된 것이 없다). 점검: **검증 계기는 노드 라벨이지 엣지 타입이 아니다** — 폐기된 엣지 타입은 그 재동기화의 `_retarget_stale_edges`가 지워 버려 "결함이 있어도 깨끗하게" 나온다. ⏱️ **남는 창은 재동기화 소요 시간**(재동기화는 백그라운드 작업이고 알림은 끝날 때 나간다 — 격리 실측 4초. **40분이 4초가 된 것이고 0초는 아니다**) | `POST /api/graph/sync` · `POST /admin/reload-configs`(같은 행을 쓴다) | `main.py execute_manual_sync` · [ONTOLOGY_GRAPH_SPEC §7.5e ①](../spec/ONTOLOGY_GRAPH_SPEC.md) |
| **고아 노드 스윕 (스케줄)** (`530fdfd` 2026-07-30) | `_retarget_stale_edges`는 **엣지**를 지우고 남은 **노드**를 지우는 코드는 없었다 — 라벨 폐기만의 문제가 아니라 **정체를 바꾸는 셀 편집마다 노드 한 개가 샌다**(라이브 degree-0 12,761개). auto-update 스케줄러 틱에서 **1일 주기**로 돈다(수집기가 아니라 유지보수 작업 — 근거는 config 백업과 동일). 고아 = **엣지 0개 AND 현재 어떤 매핑도 그 `(label, identity_key)`를 생산 불가**(생산 가능성은 materializer와 **같은 `compose_identity`**). 🔴 **점검의 요점은 삭제가 아니라 거절이다**: ① 선언에 **거부가 하나라도** 있으면(또는 매핑이 0개면) `status: "refused"`로 **전체를 거절**하는가 — rename으로 한 테이블이 죽으면 그 테이블이 생산하던 모든 라벨이 생산 불가로 보이고, 예산 가드는 `min_population`(10) 미만 라벨을 **막지 못한다** ② 인구의 절반 초과를 잃는 라벨이 삭제가 아니라 **거절**되는가 ③ 매 주기 로그가 **가져간 것과 거절한 것을 개수·비율로 함께** 말하는가(건너뛴 집합이 안 보이는 스윕은 "할 일 없음"으로 읽힌다) ④ degree-0만으로 지우지 않는가(`SplitCondition` 평균 degree 0.2 — DOE 어휘가 통째로 날아간다) | 노브 `GRAPH_ORPHAN_SWEEP_ENABLED=false` · 운영자 문 `server/scripts/graph_orphan_sweep.py`(**dry run 기본**, `--apply`는 격리 밖에서 `--allow-production` 필요) | `server/graph_orphans.py` · `run_auto_update.maybe_sweep_graph_orphans` · [AUTO_UPDATE_GUIDE §4-ter](../guide/AUTO_UPDATE_GUIDE.md) · [ONTOLOGY_GRAPH_SPEC §7.5e ②](../spec/ONTOLOGY_GRAPH_SPEC.md) |
| 서브그래프 뷰어 | stats 카운트 카드 + identity 자동완성 검색 + k-hop(1\|2) 이웃 탐색을 BFS 동심원 캔버스로 렌더(무라이브러리). 팬·줌, truncated 배지, user provenance 엣지 강조. **노드 클릭=선택**(Connections 테이블), **중심 이동은 더블클릭/시드 버튼**(2026-07-25 `18218da`부터 UX 변경) | `/graph.html`(🧭 Menu 또는 추적 리포트 크로스링크 `?label=&identity=`) | `graph_viewer.js`(§7) · GET `/graph/stats·neighbors·nodes/search`(§1.5) |
| 뷰어 Connections 테이블 + 검색 시드 연동 | 노드 클릭 → 우측 패널에 선택 노드 정보 + 관계 테이블(방향 →/←/⟲·엣지 type·상대 노드 요약·event_time). 비중심 노드는 서브그래프 단면 즉시 표시 후 depth-1 재조회로 전체 이웃 보강, 80행 단위 "더 보기". **행 클릭 → 해당 노드 중심 재조회 + URL `?label=&identity=` push + 검색바 반영**(뒤로가기 복원 지원). 패널 접기 토글 | 뷰어 캔버스 노드 클릭 | `selectNode/fetchNodeConnections/renderConnBlock/syncUrl`(§7 graph_viewer.js) |
| 뷰어 라벨 노드 리스트 | stats 라벨 카드 클릭 → 그 라벨의 노드 목록 테이블(identity 오름차순, 서버 페이지 200 + "더 보기", 로드수/총수 헤더) → 행 클릭 시 중심 탐색, back으로 Stats 복귀. 서버는 빈 q + label 리스팅(캡 200 — 자동완성 캡 50 불변, 전 테이블 덤프 금지) | 뷰어 첫 화면 라벨 카드 클릭 | `openLabelNodes/fetchLabelNodesPage/renderLabelNodesBlock`(§7 graph_viewer.js) · GET `/graph/nodes/search`(§1.5) |
| 객체 중심 추적 리포트 | 멀티 시드(≤20) BFS 합집합 → 라벨별 그룹 테이블 + event_time 타임라인. depth 1..3·시간 범위·타입 필터, missing seeds 분리 표시, 뷰어 양방향 크로스링크 | `/trace.html` — 메인 그리드 행 선택 → 「🕸️ 추적」 버튼(새 탭, 선택 행→identity 시드) | `trace.js`/`trace_core.js`/`trace_launch.js`(§7) · POST `/graph/trace`·GET `/graph/mapping-summary`(§1.5) |
| 추적 진입점 자동 표시 | `mapping-summary`로 현재 테이블의 매핑 활성 여부를 판정해 「🕸️ 추적」 버튼 노출/숨김. **[`530fdfd`] 같은 응답이 `rejected[]`·`rejected_count`·`source{path, exists}`를 함께 싣는다** — 컬럼 하나 rename에 그 테이블의 온톨로지가 통째로 사라지던 것이 표면에 안 나왔기 때문. 점검: **정상 상태에서 `rejected`는 반드시 비어 있어야** 하고(늘 뭔가 들어 있는 사유 목록은 곧 무시당한다), **파일 부재는 거부가 아니라 `source.exists: false`로만** 나오는가 | (자동) 메인 그리드 툴바 | `trace_launch.refreshTraceEntry`(§7) · GET `/graph/mapping-summary`(§1.5) |
| **칩 추적 (`GET /graph/chip-trace`)** — 경계 계약 (`8670e3b`+`ae2811c` 2026-07-30) | 칩(`CoreCell`) 1개의 이력을 **웨이퍼 스코프**로 추적. **BFS가 아니라 고정 형상**이고 **depth 파라미터가 없다** — 같은 시드의 `POST /graph/trace` depth 2는 1,000 노드 캡을 태우고 그중 **994개가 형제 CoreCell**(남의 칩)이며, 엣지 타입 필터로 막으면 홍수가 **더 커진다**(1,341→11,549, `Eqp` degree 10,284로 우회). 3다리: ① 칩 자신(`BONDED_TO→BaseCell`·`TRANSFERRED_TO→DtCell`) ② 웨이퍼(`FROM_CORE→Core` ← `PERFORMED_ON`) ③ 잎(`USED_KNOB`/`USED_RECIPE`/`EXECUTED_BY` — **되확장 금지**). 실측 234노드/694엣지·57ms·무관 노드 0. 🔴 **점검의 핵심은 "빈 홉이 없는가"다** — 다리마다 `recorded`·`none_recorded`(선언 있고 행 0)·`not_declared`(매핑이 그 쌍을 더는 선언 안 함)·**`mapping_unavailable`**(선언을 **읽지 못했다** — 매핑 파일 저장 중/거부/부재. 확인: 파일을 잠깐 깨뜨리면 `not_declared`가 아니라 이쪽이 나오는가, 그리고 `recorded`/`none_recorded`는 **강등되지 않는가**)·**`not_reached`+`blocked_by`**(앵커 다리가 죽어 **묻지 않았다**. 확인: `PERFORMED_ON`을 rename하면 잎이 `USED_KNOB: none_recorded, count 0`이 **아니라** `not_reached`로 나오는가 — 종전 버그가 "이 웨이퍼는 knob을 쓰지 않았다"고 주장했다) 중 하나를 말한다. 스코프는 `scope_unresolved`(Core 주장 0개 또는 2개 이상, **또는 그 다리가 잘림** — 라이브 2,687셀이 소스 파일별 복수 `FROM_CORE`를 가진다). **절단은 상태가 아니라 다리별 `truncated`+`capped_at`**이고 `count`(주장 수)≠`node_ids`(개체 수)는 **의도**다 | 아직 전용 UI 없음 — REST 직접 호출(`?identity=<CoreCell identity>`). 시드 부재 404 | `main.py get_chip_trace`/`_chip_trace_leg`/`_chip_trace_declaration`(§1.5) · [ONTOLOGY_GRAPH_SPEC §7.5d](../spec/ONTOLOGY_GRAPH_SPEC.md) · [backend §2 그래프 조회](../architecture/backend.md) |

### 1.10 듀얼 테마 / 실시간 동기화 / 데스크톱 래퍼

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 듀얼 테마(라이트/다크) | 토큰 SSOT `tokens.css` + `theme.js`. 기본 라이트, localStorage로 페이지 간 유지, AG-Grid 무재생성 재도색, FOUC 방지 스탬프 | 테마 토글 버튼(`data-theme-toggle`) — **4개 페이지(index/admin/map_editor/enrichment) 모두** 각 헤더/툴바에 존재 | `theme.js`·`tokens.css`(§7) |
| WS 실시간 반영 | 편집·인제션·체인 결과를 전 클라이언트에 델타 반영(`batch_row_create/upsert/delete`, `batch_refresh_required`) + 셀 플래시, 지수 백오프 재연결. 행 정체는 `getRowId`(`row_id`)가 강제 — 중복 행이 구조적으로 막힌다 | (자동) 메인 그리드 | `websocket.js`(§7) · `ConnectionManager`(§1.1) · **[frontend §3.1](../architecture/frontend.md)**(무결성 3문제 — 구 `DATA_SYNC_SPEC`은 아카이브 대기) |
| 데스크톱 래퍼 | QtWebEngine 셸(`?client=desktop`): OS 드래그앤드롭 업로드, 네이티브 다운로드 다이얼로그, F12 DevTools, `assymanager://` URI | `python run_decoupled_app.py`(셸 포함 기동) · 배포는 GET `/api/download/client` | `client/desktop_wrapper.py` · [frontend §1](../architecture/frontend.md) |
| **셸의 서버 주소 해석** (`e9b3a36` 2026-07-30) | 셸이 어느 서버를 보는지의 **유일한 결정 지점**. 종전에는 주소가 **두 곳에 하드코딩돼 서로 달랐고**(업로드 `127.0.0.1:8080` / 페이지 `localhost:8080`), git에 추적되던 `client/client_settings.json`(`server_host`/`server_port` 보유)은 **한 번도 읽히지 않았다.** 지금 순서는 **`--server` → `ASSY_SERVER` → `client_settings.json` → `127.0.0.1:8080`**이고 조립 지점은 `base_url()` 하나다(페이지와 업로드가 같은 `self.server_base`를 읽는다). 점검할 것: ① **시작 로그 1줄**에 해석 주소 + `source`(`arg`\|`env`\|`client_settings.json`\|`default`)가 나오는가 — `source`가 없으면 운영자는 "내 편집이 무시됐다"를 알 수 없다 ② **잘못된 선언은 조용한 강등이 아니라 거절**(stderr + QMessageBox + `exit 2`)인가: 파싱 불가 JSON(줄·열 지목) · 비숫자/범위 밖 포트(**`0` 포함 — 미상 ≠ 0**) · 빈 host · `bool` 포트(`bool`은 `int` 하위형이라 명시 배제) · `https` 스킴(조용한 다운그레이드 금지) ③ **파일 부재·빈 파일·서버 키 미선언은 정상 설정**이라 조용히 기본값을 쓰는가(무회귀) ④ 빈 `ASSY_SERVER`가 **미선언으로** 취급되는가(`set ASSY_SERVER=`가 Windows의 해제 방식) ⑤ 거절 문구가 **ASCII**인가 — 이 프로세스의 stdout은 런처 아래 cp949 파이프라 비-ASCII `print`는 거절을 `UnicodeEncodeError` 트레이스백으로 바꾼다(한국어는 QMessageBox에 있다) | `--print-target`(해석·출력 후 종료, GUI·HKCU 미접촉 — **헤드리스 점검 경로**) | `resolve_server_target`/`base_url`/`settings_file_path`(`client/desktop_wrapper.py`) · **[frontend §1.1](../architecture/frontend.md)**(정본) · 설정 파일 소유는 [DOC_OWNERSHIP](../process/DOC_OWNERSHIP.md) |
| **상호작용 계측기**(핵심가치 #1 정본 계기 수집) | 키·마우스·화면이동 원시 카운트를 기존 `PUT .../data/updates`에 선택 필드 `effort`로 편승(별도 요청 0건, 화면 표시 0건). 교정 쓰기 **7경로**(그리드 5 + Enrichment 1 + 맵 Push 1) + **읽기 화면 3개**(admin·graph·trace — `effort` 페이로드 없이 이동만 계측). 점검할 불변식 6가지 — ① **실패 저장은 리셋하지 않는다**(재시도 공수는 진짜 공수) ② **200이어도 서버가 기록 안 했으면 리셋하지 않는다**(`effort_recorded=false` = no-op 저장; 리셋하면 두 번 시도한 교정이 가장 싸게 기록된다) ③ **누적 0이면 `effort` 필드를 아예 안 보낸다**(0을 보내면 "측정된 0점 교정"으로 기록돼 기준선이 유령으로 내려간다) ④ **존재하지 않는 라우트를 지목한 허용목록 항목은 콘솔 에러**로 뜬다(조용히 무력화되면 오타와 정상이 구별되지 않는다) ⑤ **이동은 대칭이어야 한다** — `grid→graph`만 세고 `graph→grid`를 안 세면 왕복이 절반 값으로 남는다(읽기 화면에서 「메인으로」를 눌러 카운터가 실제로 늘어나는지 확인) ⑥ **`window.__assyEffort.getConfig().loaded`가 운영 빌드에서 읽혀야 한다**(트리셰이킹으로 사라지면 "목록이 빔"과 "설정 못 받음"을 구별할 수 없다). ⚠️ 새 서브컨텍스트로 `countNav`를 부르면 같은 변경에서 `ROUTE_IDS`에도 등록 | (자동·비가시) 전 페이지 · 집계 결과는 어드민 Overview 「교정 공수」 줄(§1.8) | `effort_meter.js`(§7) · [frontend §3.2](../architecture/frontend.md) · [guide/config/effort_metric](../guide/config/effort_metric.md) · 하니스 `client2/tests/effort_meter_harness.mjs`(110 단언·변이 6종), `effort_instrument_harness.mjs`(28 검사·변이 9종) |

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

### 1.12 접근 통제 (어드민 토큰 · 내부 IPC · 정적 서빙 봉쇄) — 2026-07-27 신설 (`90e284f`)

> **로그인 화면도 사용자 계정도 없다.** 사내 2~5명 공유 전제라 **공유 비밀 하나**를 헤더로 제시하는 형태다(SSOT §8 · [PRODUCTION_READINESS C1](../process/PRODUCTION_READINESS.md)).
> ⚠️ **이 절은 반드시 사내망 평문 HTTP 주소(`http://<사내IP>:8080`)에서 점검한다.** 게이트를 뚫는 쪽도, 뚫린 것을 보는 쪽도 그 주소로 들어온다. `localhost`에서만 확인한 결과는 이 절의 어떤 항목도 증명하지 못한다.

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 어드민 공유 토큰 게이트 | `/admin/*` **API 16개 전부**가 `ASSY_ADMIN_TOKEN` 환경변수 + `X-Admin-Token` 헤더 필요(비교 `secrets.compare_digest`). **조회도 포함** — 소스 코드 반환·파이프라인 열거도 유출이다. 미제시 **401**, 불일치 **403**. 예외는 페이지 서빙 `GET /admin`·`/admin.html` 2개(브라우저 내비게이션이라 헤더를 붙일 수 없고, 표시 데이터는 전부 게이트된 JSON에서 온다) | 서버 환경변수 | `server/admin_auth.py` · [backend §API](../architecture/backend.md) · [DEPLOY_SETUP §1-4](../guide/DEPLOY_SETUP.md) |
| 미설정 시 **부분** fail-closed | 토큰이 없으면 코드 실행 2라우트(`POST /admin/scripts/code`·`POST /admin/auto-update/run-now`)만 **503**, 나머지는 **열린 채 동작**. 전부 잠그면 운영자가 **고치러 들어갈 페이지에서 잠긴다** — 의도된 비대칭이다 | (자동) 기동 시 | `require_admin_token{,_strict}` |
| 비-ASCII 토큰 거부 | HTTP 헤더는 latin-1 디코딩이라 **한글·이모지 토큰은 구조적으로 인증 불가**. 서버가 기동 시 **거부하고 미설정 상태로 취급**하며 배너를 `ERROR`로 남긴다. 조용히 16라우트를 죽이고 "토큰이 틀렸다"고 답하는 **복구 불능 상태**를 만들지 않기 위함 | 기동 로그 `[admin-auth]` | `token_is_unusable`/`startup_banner` |
| `/internal/events/*` 게이트 | 워커→웹서버 IPC 4개도 **같은 토큰**. `broadcast`는 임의 dict를 **접속 중인 전 클라이언트 그리드에 중계**하고 `audit_cache`에 주입하므로, 조회 admin만 잠그는 것은 거꾸로였다. 워커 3종은 **런처 환경을 상속**해 자동으로 헤더를 붙인다 | (자동) 워커 기동 | `internal_event_headers()` · `run_watcher`/`chain_ingestion_worker`/`graph_sync_worker` |
| **통지 4xx가 누가 거절했는지 말한다** (2026-07-30 `23a346d`) | `/internal/events/*`의 401/403 로그에 **`admin-gate=yes\|no`**가 붙는다. 판정은 게이트가 **자기 거부에만** 다는 `WWW-Authenticate: X-Admin-Token` 헤더 하나이고(대소문자 무시 **정확 일치** — 프록시의 `WWW-Authenticate: Basic realm=…`이 우리 것으로 읽히면 안 된다), `admin-gate=yes`면 **토큰 지문**과 모집단별 REMEDY가 함께 나온다(403 = 양쪽 토큰 다름 / 401+지문 있음 = 전송 중 탈락 / 401+`none` = 이 프로세스에 변수 없음 / 401+`unusable-non-ascii` = 비-ASCII라 헤더를 못 만듦). 🔴 **`admin-gate=no`면 토큰을 아무리 만져도 안 고쳐진다** — 앞단(프록시·방화벽·포트를 뺏은 다른 프로세스)이 답한 것이다. 2026-07-30 인시던트의 3시간이 이 한 줄이 없어서 들었다 | 워커 로그 | `admin_auth.internal_event_failure_note` · [DEPLOY_SETUP §1-4/§1-5](../guide/DEPLOY_SETUP.md) |
| **loopback HTTP는 프록시를 참조하지 않는다** (2026-07-30 `23a346d`) | 워커→웹서버 호출의 세션은 **`internal_event_client.internal_event_session()` 하나**에서만 나오고 `trust_env=False`다(환경변수·Windows 프록시 레지스트리 **둘 다** 차단, 스레드 로컬). 웹서버→GraphSync의 `httpx`도 같다. 원 사고: 레지스트리 `ProxyOverride`의 `<local>`은 **점 없는 호스트명만** 우회시켜 `localhost`는 통과하고 **`127.0.0.1`은 프록시로 나갔다** → 사설 주소 중계 거부 403(게이트 없는 `/health`까지). 🔴 **네 번째 발신자가 기억해야 하는 규칙이 아니라 테스트다** — 같은 결함이 발신자별로 세 번 재발해, 이제 발신자가 세션을 직접 만들면 `test_admin_auth.py`가 실패한다. 기동 시 데몬 3종이 `/health` 프로브 + `proxy-env` 요약을 찍는다 | (자동) 데몬 기동 로그 `[internal-events]` | `server/internal_event_client.py` · `test_admin_auth.py::test_no_sender_builds_its_own_client` · [PRIMITIVES §6](../architecture/PRIMITIVES.md) |
| 정적 폴백 봉쇄 (traversal 차단) | SPA catch-all이 **결과 기반 containment 검사** 후에만 파일을 낸다. 이전에는 **무인증으로 임의 파일**(`table_config.json`, `Windows/win.ini`, 게이트 자신의 소스)이 200이었다 — 잠근 조회 라우트가 지키던 바로 그 바이트가 옆문으로 나가고 있었다. 탈출은 **403이 아니라 404**(탈출이 파싱됐다는 사실조차 확인해 주지 않는다) | `GET /{경로}` | `main.py serve_static_or_index` · `_resolve_admin_script_path`(재사용된 원형) |
| 클라 토큰 흐름 | 게이트 거부에만 붙는 **`WWW-Authenticate: X-Admin-Token`** 헤더로 판정 → `prompt` 1회 → `localStorage['assy.adminToken']` 보관 → 이후 `X-Admin-Token` 헤더 전송. **새 화면·탭·설정 패널 없음**(구현은 `adminFetch()` 하나) | 어드민 페이지 최초 진입 | `client2/src/admin.js adminFetch` · [frontend §5](../architecture/frontend.md) |
| 서빙되는 것은 **번들**이다 | 서버가 보내는 것은 `client2/src/admin.js`가 아니라 git에 올라간 `client2/dist/assets/admin-*.js`다. 소스만 고치고 번들을 안 올리면 **토큰을 켜는 순간 어드민이 죽는다**(401은 오는데 물어보는 코드가 서빙 파일에 없어 프롬프트가 안 뜬다) | `cd client2 && npm run build` | 판정: `grep -c X-Admin-Token client2/dist/assets/admin-*.js` |
| 회귀 방어(범위 있음) | `test_admin_auth.py`가 FastAPI 라우트 테이블을 **열거**해 커버리지를 단언 — 나중에 추가되는 admin 라우트는 무방비 배포 대신 스위트를 빨갛게 만든다. ⚠️ **WebSocket 라우트와 mount는 걸리지 않는다**(`route.methods`가 `None`) — 그 축은 사람이 봐야 한다(§2.16) | `pytest server/tests/test_admin_auth.py` | `ADMIN_GATES` |

---

## 2. QA 수동 점검 체크리스트

> **사전 조건:** `python run_decoupled_app.py`로 전체 스택 기동(웹 :8080 + 워커 4종). 체인/인리치먼트 항목은 로컬 스모크 규칙(`line_model_owner_attribution`: `production_plan` → `line_model_registry`, gitignored config) 기준 — 환경에 규칙이 없으면 해당 항목은 N/A 처리.
> **핵심가치 직결 항목**은 🎯로 표시(실시간 SLO·멱등성·레이어링 보존 — 실패 시 릴리스 블로커).

### 2.0 자동 게이트 — 손으로 점검하기 **전에** 통과시킬 것

> 수동 점검은 자동 게이트가 초록일 때만 의미가 있습니다. **채점은 두 갈래이고, 한쪽만 돌리면 절반만 검증됩니다.**

- [ ] 🎯 **서버 절반**: `conda run -n assy_manager pytest server/tests/` 통과. ⚠️ **시스템 `python`으로 돌리지 말 것** — `psycopg2` 부재 등으로 거짓 실패가 납니다.
- [ ] 🎯 **클라 절반 = 빌드 게이트**(`5a14e77` 2026-07-30 신설 · `77a2c15`에서 **3행으로 늘었습니다**): `cd client2 && npm run build` 성공. `prebuild`가 `check:clipboard && check:contracts && check:suggest-keys`를 먼저 돌리고, 하나라도 발산하면 **`dist/`가 생성되지 않습니다.**
  ```bash
  cd client2 && npm run check:contracts       # ✓ 4 contracts, no divergence.
  cd client2 && npm run check:suggest-keys    # 값 제안 키보드 계약 + 변이 스윕
  ```
  - ⚠️ **게이트 목록의 정본은 `client2/package.json`의 `prebuild` 한 줄입니다.** 이 체크리스트의 목록은 사본이고, 실제로 한 번 낡았습니다(2행이라고 적힌 채 3행이 됐습니다). 항목 수가 늘었는지는 `prebuild`를 보고 확인하십시오.
  - 🔴 **`check:suggest-keys`의 판정은 "통과"가 아니라 "APPLIED == CAUGHT"입니다.** 모든 점검에 변이(mutation)가 짝지어져 있는데, **변이가 소스 드리프트로 적용되지 않으면 조용한 무장 해제**입니다(`cb8f01a`: 18개 중 8개가 적용조차 안 되면서 베이스라인은 초록이었습니다). 출력의 APPLIED와 CAUGHT 수를 **둘 다** 확인하십시오.
  - ⚠️ 이 하네스는 AG-Grid 키보드 파이프라인의 **모델** 위에서 돕니다. AG-Grid가 호출 순서를 바꾸면 하네스는 초록인 채 제품이 깨지므로, **브라우저 실측 키스트로크 수가 1차 증거**이고 이것은 그 아래의 회귀 그물입니다(§2.1의 F3 항목).
  - **2026-07-30 이전에는 계약 클라 하네스를 아무것도 실행하지 않았습니다** — `pytest`는 서버 절반만 채점하고 `client2`에 스크립트가 없었습니다. 그 조건이 `split_registry_harness.mjs`를 심볼 개명 이후 **몇 주 동안 예외로 죽어 있게** 두었습니다(부르는 사람이 없어 실패가 보이지 않음).
  - 🔴 **"0개, 전부 초록"은 통과가 아닙니다.** 러너는 `contracts/*/client_harness.mjs`를 **발견식으로 스캔**하며 하나도 못 찾으면 `exit 1`입니다 — 출력의 계약 **개수**를 눈으로 확인하십시오(현재 **4**: `band_arithmetic`·`doe_band_rules`·`legend_map_scope`·`map_seam`).
  - 계약이 발산하면 **벡터를 고쳐 통과시키지 말 것**. 구현을 고치거나, 계약이 바뀐 것이면 총괄에 가져갑니다.
- [ ] **빌드 성공 ≠ 번들 커밋**: 서버가 서빙하는 것은 `dist/`입니다. 소스를 고쳤으면 빌드 후 `client2/dist/`를 함께 커밋했는지 확인(§2.16 A의 번들 선행 확인과 같은 규율).

### 2.1 데이터 그리드 — 조회/편집

- [ ] **조회 정상**: `/` 접속 → `table-select`에서 테이블 선택 → 그리드에 데이터 표시, 하단에 페이지/건수 표시.
- [ ] **편집 정상**: 셀 더블클릭 → 값 변경 → Enter → 값 반영 + 셀에 오버라이트 표시(스타일 변화) + History 패널에 이력 즉시 추가.
- [ ] **편집 에지 — 숫자 검증**: 숫자 타입 컬럼에 문자열 입력 → 거부(토스트/원복)되고 서버에 저장되지 않음.
- [ ] 🎯 **편집 에지 — 자동값 우선순위**: 파일 인제션으로 채워진 셀을 수동 편집 → 같은 파일 재드롭 → 수동 값이 유지됨(user가 parser를 이김).
- [ ] **필터/정렬**: 컬럼 플로팅 필터에 조건 입력 → 결과 축소, 헤더 클릭 → 정렬 토글. 필터+페이지 이동 조합 시 결과 일관.
- [ ] **페이징**: 다음/이전 페이지 이동, 페이지 번호 직접 입력, 마지막 페이지에서 다음 버튼 동작(비정상 점프 없음).
- [ ] **CSV export**: `load-csv-btn` → 현재 테이블 CSV 다운로드, 행 수가 화면 총계와 일치.

#### 값 제안 셀 에디터 (F3 `77a2c15` + Escape 시정 `d5f75a8`) 🎯

> ⚠️ **점검 전에 반드시**: `switchTable`이 **`txModeActive`를 강제로 다시 켭니다**(`client2/src/api.js:70-71` — 대기 편집 폐기와 한 쌍). 편집 E2E는 **표를 바꾼 뒤마다 토글을 다시 끌 것.** 이 함정으로 에이전트 두 명이 각각 한 회차를 날렸습니다: 편집이 스테이징만 되고 서버에 안 가는데 화면은 정상처럼 보입니다.
>
> 판정은 **키스트로크 수**로 씁니다("동작했다"가 아니라 "몇 번 눌렀나"). 계수 규칙은 `effort_meter`와 같습니다 — 단독 수식키 제외.

- [ ] 🎯 **1글자 → 목록 + `Enter` 1회로 확정**: `string` 컬럼 셀에서 **1글자** 입력 → 목록이 뜨고 **첫 후보가 하이라이트** → `Enter` **한 번**에 그 후보가 셀에 확정된다. **두 번 필요하면 결함입니다**(채택과 확정이 갈렸다는 뜻 — `suppressKeyboardEvent`가 `'accepted'`를 못 돌려주고 있습니다).
- [ ] **`↓` 이동 후 `Enter`**: `↓`로 후보를 옮기고 `Enter` → 하이라이트된 그 후보로 확정. 화살표는 캐럿을 입력 앞/뒤로 튕기지 않는다.
- [ ] 🎯 **`Esc` 1회는 목록만 닫고 글자를 보존한다 — 그리고 타이밍에 무관해야 한다**: ⓐ 빠르게 타이핑해 **목록이 뜬 상태**에서 `Esc` → 목록만 닫히고 **타이핑한 글자가 남는다**(그 상태에서 `Enter`면 내가 친 값이 저장). ⓑ **느리게 타이핑해 목록이 아직 안 뜬 상태**에서 `Esc` → **ⓐ와 같아야 한다.** 🔴 **이 두 타이밍이 갈리는 것이 원래 결함이었습니다** — 종전에는 `listOpen`을 물어서, 목록이 화면에 있었는지가 디바운스+왕복시간의 함수였고 한쪽은 글자를 **버렸습니다**.
- [ ] **`Esc` 2회는 편집 취소**: engaged된 셀에서 `Esc` 두 번 → 두 번째가 AG-Grid의 평범한 편집 취소(원래 값 복귀). ⚠️ **취소에 두 번이 필요한 것은 의도된 대가**입니다(결정성을 그 키 하나보다 값어치 있게 봤습니다). 다만 **제안이 한 번도 engaged되지 않은 컬럼**(미선언·서버 플로어 미달·쿨다운)에서는 **첫 `Esc`가 곧 취소**이고 화면에는 그 차이가 보이지 않습니다 — 알려진 비균일성이므로 결함으로 올리지 마십시오.
- [ ] **`Esc` 후 `↓`는 목록을 다시 연다**: `Esc`로 닫은 뒤 `↓` → 추가 타이핑 없이 목록 재개. `↑`는 열지 않는다(자기가 쓴 글자를 지키려는 사람에게 안전한 방향 하나).
- [ ] **`Tab`은 채택 + 이동**: 하이라이트 상태에서 `Tab` → 후보가 확정되고 다음 셀로 이동(한 번 누름).
- [ ] **`Ctrl+Enter`는 채택값으로 범위 일괄**: 범위를 잡고 편집 시작 → 타이핑 → `Ctrl+Enter` → **하이라이트된 후보값**이 범위 전체에 채워진다(입력에 남은 부분 접두가 아님).
- [ ] **한글 IME**: 한글을 조합하는 중의 `Enter`는 **IME 것**(음절 확정)이라 후보를 대입하지 않는다. 조합이 끝난 뒤의 `Enter`부터 제안 계약이 적용된다.
- [ ] **제안 불가 컬럼은 평범히 동작**: 미선언 컬럼·`number`·`datetime` 컬럼에서 편집 → **목록 없이** 종전 그대로. 토스트도 에러도 뜨지 않는다(제안할 수 없는 컬럼의 망가진 드롭다운은 없는 것보다 나쁩니다).
- [ ] **진단 창이 실제로 존재한다**: 콘솔에서 `window.__assySuggest.getSuggestStats()` → 요청/로컬 축소/중단/거부/불가 카운트가 나온다. `undefined`면 계측이 dist에 없는 것이므로 그 자체가 결함입니다(`847ceaf`).

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
  - ⚠️ **반드시 사내망 평문 HTTP 주소(`http://<사내IP>:8080`)에서 점검**할 것. `localhost`/`127.0.0.1`은 보안 컨텍스트라 `navigator.clipboard`가 살아 있어 **운영 결함이 재현되지 않는다**(2026-07-27 실제 사례).
- [ ] **행 단위 복사**: 셀 범위 선택을 해제한 상태에서 행 체크박스로 행 선택 → Ctrl+C → 행 전체 TSV. ⚠️ 셀 범위/단일 셀 선택이 남아 있으면 범위 복사가 우선(`clipboard.js:569`)이라 행 복사가 실행되지 않는다.
- [ ] **클립보드 붙여넣기**: 엑셀에서 복사한 2×2 범위를 그리드에 Ctrl+V → 해당 범위 셀 값 갱신 + 이력 기록.
- [ ] **스마트 페이스트**: 엑셀에서 표 복사 → 그리드 우클릭 → "📋 파서로 붙여넣기 (Smart Paste)" → (엑셀 복사본은 다중 포맷이므로) 유형 선택 모달에서 포맷 선택 → 업로드 성공 토스트 → 인제션 파이프라인 경유 적재·그리드 반영.
  - ⚠️ 이 기능만 `navigator.clipboard.readText()`에 의존한다(`main.js:1463`). **평문 HTTP에서는 항상 실패**하고 "❌ 스마트 붙여넣기 중 오류가 발생했습니다." 토스트로 끝난다 — 미해결(2026-07-27 확인). 위 **클립보드 붙여넣기**(Ctrl+V)는 별개 경로이며 평문 HTTP에서도 정상.
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
- [ ] **폴더 드롭 평탄화(`0c6ac1a`)**: 2층 이상 중첩 폴더(파일 수 개 포함)를 `raws/`에 드롭 → 파일이 루트로 승격돼 전부 적재·아카이브, 폴더는 제거. 루트에 동명 파일을 미리 두고 재드롭 → **둘 다 생존**(폴더 쪽이 `상위~하위~파일` 개명 — 덮어쓰기 0건), 개명 로그 확인.
- [ ] **평탄화 — 잠긴 파일 가지 보존**: 폴더 내 파일 하나를 다른 프로세스로 잠근 채 드롭 → 나머지는 승격·적재되고 **잠긴 파일과 그 폴더 가지는 삭제되지 않고 남으며** warning 로그, 잠금 해제 후 300s 주기 스윕이 잔여분을 마저 처리. (내용물 있는 폴더가 지워졌다면 rmdir-only 계약 위반 — 즉시 결함.)
- [ ] **평탄화 — 토글 오프 핫 반영**: `ingestion_settings.json`에 `"flatten_nested_dirs": false` → **재기동 없이** 다음 폴더 드롭부터 종전 동작(폴더 무시)으로 복귀, `true` 복원 시 재개.
- [ ] **평탄화 — force 토큰 조작 금지**: `force`라는 이름의 폴더에 평범한 파일을 넣어 드롭 → 개명 결과에 `__force__` 토큰이 **합성되지 않아** dedup skip이 정상 동작(파일명 자체에 사용자가 적은 `__force__`는 유지).
- [ ] **맵 메타 자동 등록 — 양방향 토글(M3 `ab6ac02`)** 🎯: `auto_register_map_meta: true`(기본)에서 **새 맵 키**를 파일로 적재 → 맵 에디터에서 그 키를 열면 **좌표계 선택 모달 없이** 바로 열린다(메타가 생겼다는 관찰 가능한 증거). `false`로 바꾸고 또 다른 새 키를 적재 → **모달이 돌아온다**. 체인 워커 경로(체인 룰 타깃이 맵 테이블)도 같은 결과인지 별도로 확인 — 양쪽에 훅이 붙어 있다.
- [ ] **맵 메타 자동 등록 — absent-only 불변식(M3)** 🔴: 에디터에서 회전·물리 규격을 **손으로 등록/수정한** 맵 키에 같은 키의 데이터를 다시 적재 → **메타가 절대 바뀌지 않아야 한다**(사용자 등록이 정본, 생성 소스는 `auto_map_meta` = 최하위 우선순위). 자동 생성된 메타를 나중에 사용자가 고치면 그 편집이 이긴다. 그리고 **`wafer_map_metadata` 자신에 적재해도 자기 등록이 유발되지 않는다**(재귀 가드).
- [ ] **맵 메타 자동 등록 — 실패 격리·비용(M3)**: 메타 등록이 실패하도록 만들어도(예: 메타 테이블 권한 회수) **파일/체인 적재 자체는 정상 완료**되고 로그만 남는다. 대량 적재 시 존재 확인이 **행마다가 아니라 distinct 키당 1회**인지 쿼리 로그로 확인(같은 맵 재적재는 추가 쿼리 0회 — 프로세스 수명 캐시).

### 2.6 Auto-Update

- [ ] **크론 실행**: `# schedule: */5 * * * *` 스크립트 배치 → 주기 도래 시 `raws/`에 CSV 생성 → 인제션까지 연쇄 완료.
- [ ] **핫 리로드 에지**: 스크립트의 schedule 주석 변경 → 재기동 없이 다음 실행 타이밍이 변경(스케줄러 로그 확인).
- [ ] **즉시 실행**: 어드민 AutoUpdate 탭에서 run-now → 즉시 수집·드롭·적재.
- [ ] **Active 토글**: AutoUpdate 탭에서 수집기 Active 스위치 OFF → 다음 주기에 실행되지 않고 상태가 SKIPPED(next_run은 전진), 행 dim 표시 + Overview 카드 active/total 감소. **OFF 상태에서도 run-now는 실행됨**(툴팁 확인). ON 복귀 → 다음 주기 정상 실행 1회(밀린 주기 몰아 실행 없음). 재기동 없이 전 과정 핫 반영.
- [ ] **토글 에지 — 제어 파일 부재**: `config/auto_update_control.json` 삭제 후 status 조회 → 전 수집기 active(fail-open), 에러 없음.
- [ ] **[2026-07-27] 헬퍼 함수 수집기**: 헬퍼를 **다른 함수 안에서** 호출하는 스크립트(`def a(): ...` / `def b(): return a()` / `out = b()`) 배치 → 주기 도래 시 CSV 정상 생성. (모듈 레벨 호출은 결함 축이 아니므로 반드시 함수 안에서 호출할 것.)
- [ ] **[2026-07-27] 실패는 실패로**: 예외를 던지는 수집기 배치 → 어드민 AutoUpdate 탭 상태가 **FAIL**, `last_error`에 트레이스백 노출. "Skipping file generation" 후 SUCCESS로 끝나지 않는지 확인.
- [ ] **[2026-07-27] print 수집기 회귀**: `out` 없이 `print(...)`만 하는 수집기 → 여전히 stdout 폴백으로 CSV 생성, 로그에 **ERROR 없음**.
- [ ] **[2026-07-27] `sys.exit(0)` 격리**: `out` 설정 후 `sys.exit(0)`으로 끝나는 수집기 → CSV 정상 생성 + **스케줄러 데몬이 죽지 않음**(이후 주기 계속 동작, `/health` 스케줄러 하트비트 유지).
- [ ] **[2026-07-27] `out = None`은 실패**: fetch 실패 시 `out = None`을 대입하는 수집기(예: `bonding_map/fetch_data.py`의 네트워크를 끊고 실행) → 어드민 상태 **FAIL** + `last_error`에 사유. **스크립트가 재실행되지 않는지**(외부 API 2차 호출 없음) 스크립트 자체 로그/카운터로 확인. `SUCCESS`로 끝나면 회귀.
- [ ] **[2026-07-27] 0건 관용구**: `out = []` / `out = ""` 수집기 → 파일 미생성이지만 **SUCCESS**(실패로 뒤집히지 않았는지 확인).
- [ ] **[2026-07-27] 부작용 2회 실행**: 실행 횟수를 파일에 기록하는 print 수집기(`out` 미사용, 헬퍼 함수 포함) 1주기 → 카운터 **2 증가**가 정상임을 확인. ack POST·커서 전진형 수집기는 `out` 방식으로 이전해야 함을 경고.

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
- [ ] 🎯 **① 자동 확정 — 양방향 토글**: 규칙의 뷰에 `candidate_for`를 선언하고 `auto_confirm: true` → 후보가 1개인 판단키의 새 원본을 적재하면 target이 **자동으로 채워져 워크리스트에서 빠진다**. `auto_confirm`을 `false`로 바꾸고 다른 새 키를 적재 → **빈 채로 워크리스트에 남는다**(꺼짐/켜짐의 관찰 지점).
- [ ] 🎯 **① 모호는 자동 확정하지 않는다**: 같은 판단키에 후보가 2개인 키는 노브가 켜져 있어도 **빈 채로 큐에 남는다**(선언한 뷰를 하나 더 늘려 일부러 모호하게 만들어 확인 — 자동 확정이 판단을 대신하지 않는다는 증거).
- [ ] **① 사람이 지운 값은 재확정하지 않는다**: 자동 확정된 셀을 사람이 **비우면** 표시는 blank가 되어 큐에 돌아오지만, 그 셀은 provenance가 있어 **다시 자동 확정되지 않는다**(`cell_has_provenance`).
- [ ] **① 켜기 전 측정**: `enrichment_insights.py confirm <규칙> --ignore-knob` → 아무것도 쓰지 않고 「몇 건이 사람 없이 해소되는가」가 나온다. 실행 후 DB가 변하지 않았는지 확인.
- [ ] **④ 분류 수치의 정합**: `classify <규칙>`의 분류 합계 = 워크리스트 잔여 건수(= 배지 N). 어긋나면 큐 술어(`queue_filters`)가 갈린 것이다.
- [ ] **② 제안은 config를 쓰지 않는다**: `propose <규칙>` 실행 전후로 `enrichment_rules.json`이 **바이트 단위로 동일**해야 한다. 제안된 `reference_views` 항목을 사람이 붙여넣으면 ①이 그것을 실행한다.

### 2.8-bis Chain Replay (R1 재적용 / R2 stale 소스 철회)

- [ ] **R1 dry-run은 쓰지 않는다**: `chain_replay_cli.py replay <룰>` → 보고만 나오고 타깃 테이블 행수·값이 변하지 않는다. 보고에 **`cells a human protects`** 수치가 함께 나온다.
- [ ] 🎯 **R1은 사람 값을 못 덮는다**: 타깃 셀을 사람이 편집한 뒤 `replay <룰> --apply` → **표시값이 그대로**다. 셀 이력/소스에는 `chain_ingestion` 레이어가 추가되지만 `user`(priority 0)가 계속 이긴다.
- [ ] 🎯 **R1은 빈 값을 쓰지 않는다**: 룰이 어떤 셀에 값을 더는 만들지 않으면 그 셀은 **기존 값이 유지**되고 보고에 **철회 후보**로 뜬다(빈 값 덮어쓰기 금지 — 그 진술은 R2의 것).
- [ ] **R1 자기 트리거 종료**: `trigger_table == target_table`인 룰(현 config의 `inv`)을 `replay --apply` → **시작 시점 행수만 스캔**하고 끝난다(자기 산출물을 다시 읽지 않는다). 보고에 `SELF-TRIGGERING` 표기.
- [ ] **R1 재적용 순서**: `chain_replay_cli.py list` → 생산자(`→ inventory_master`)가 소비자보다 먼저 나온다. `replay-all`은 각 룰을 **정확히 1회**만 실행.
- [ ] 🎯 **R2는 구멍을 남기지 않는다**: 셀에 소스가 둘인 상태(예: `pipeline_parser` + `custom_script`)에서 상위 소스를 `withdraw <테이블> <소스> --columns <컬럼> --apply` → **아래 레이어의 값이 드러난다**(빈칸이 되지 않는다).
- [ ] 🎯 **R2는 사람 값을 못 지운다**: `withdraw <테이블> user` → **거부**(에러 메시지가 이유를 말한다). 사람이 `manual_priority_source`로 핀한 셀은 `pinned_skipped`로 건너뛴다.
- [ ] **R2 철회는 무음이 아니다**: 값이 바뀐 셀을 그리드에서 눌러 **셀 이력 타임라인**에 `chain_replay_withdraw` / `withdraw:<소스명>` 항목이 보이는지 확인(빈칸이 데이터 유실과 구별되는 유일한 근거).
- [ ] **R2 범위**: `--columns`로 지정하지 않은 컬럼은 **손대지 않는다**. 선언되지 않은 컬럼명을 주면 거부.

### 2.9 맵 에디터

- [ ] **로드/편집/저장**: 페이지 진입 → 테이블 선택 → 기존 맵 로드 → 브러시로 셀 페인팅 → 저장 → 재진입 시 편집 결과 유지 + 메인 그리드에서 동일 값 확인(배치 업서트 경유).
- [ ] **회전/면반전 불변식**: 회전·FRONT/BACK 전환 후에도 특정 칩의 물리 위치 표시가 일관(스펙 불변식). FRONT/BACK 워터마크·툴바 칩 표시.
- [ ] **프리셋**: 커스텀 지오메트리 프리셋 저장 → 목록 표시 → 삭제 동작.
- [ ] **레전드 유지**: 레전드 편집 → 새로고침 후 유지(localStorage). 테이블별로 분리 저장.
- [ ] **맵 이월 에지**: 편집 중 테이블 A→B 전환 → 유지/초기화 확인창 표시. (⚠️ 컬럼명이 크게 다르면 자동 정합 안 됨 — 이슈 #2, 저장 전 수동 매핑 확인.)
- [ ] **엑셀 복사**: 맵 그리드를 엑셀로 복사 → 셀 배치 일치.
- [ ] **COPY HEADER MODE — 열 폭(`5a14e77`)**: 토글을 켜고 `MIDLOT_01`처럼 **긴 라벨**이 나오는 맵을 복사 → 엑셀에서 라벨이 **잘리지 않고** 읽히며, **맵 셀 폭은 그대로**다(소스 상수 `HDR_COL_PX = 32` = `<td width: 32px>`. 긴 헤더 한 칸이 그 아래 그리드 열을 통째로 넓히면 회귀 — 종전 결함. `5a14e77`은 브라우저에서 실측: 344px 헤더가 더 이상 344px 그리드 열을 만들지 않는다). 표의 **모든 행이 같은 열 수**인지 확인(하나라도 어긋나면 엑셀이 표 전체를 민다). `1H`와 `MIDLOT_01`이 **같은 폭**이면 균등 분배 회귀다.
- [ ] 🎯 **회사 양식 왕복 — 항등(F1ⓑ `c9bf2c7`)**: COPY HEADER MODE로 실맵 복사 → `🧹 Clear Grid` → **Ctrl+V** → 확인창 1회 승인 → **다시 복사** → 두 클립보드 내용이 **바이트 동일**해야 한다(빈 칸 포함). ⚠️ 붙여넣기 도중·직후 **서버 요청이 0건**인지 네트워크 탭으로 확인(저장은 `⚡ Push`뿐 — INV-F1ⓑ-4).
- [ ] 🔴 **회사 양식 왕복 — 병합 압축 회귀(INV-F1ⓑ-3)**: 보조표에서 **STACK이 빈** DOE 행이 있는 복사본을 되붙인다 → DESC가 **STACK 칸으로 들어가면 안 된다**(빈 칸을 걷어내고 압축해 읽으면 그렇게 된다 — 화면은 멀쩡하고 값만 틀리는 부류). 읽기는 머리줄에서 배운 열 위치로만 해야 한다.
- [ ] 🔴 **회사 양식 왕복 — 프레임 지문(노치 `D`)**: rot **270**에서 복사 → 화면을 rot **90**으로 바꾼 뒤 붙여넣기 → **치수가 같은데도 거부**되고 사유가 노치 위치를 지목한다. 같은 축으로 rot 0↔180, front↔back도 확인. 노치가 격자 밖인 규격에서는 거부 대신 확인창이 *"회전·면은 대조하지 못했습니다"*라고 말한다(조용히 통과시키면 회귀).
- [ ] 🔴 **회사 양식 왕복 — 노치는 데이터가 아니다**: 붙여넣기 후 그 노치 자리에 **값이 생기지 않았는지** 확인하고, 이어서 `⚡ Push` → **적재 대조 게이트에 걸리지 않아야 한다**. 걸리면 노치를 데이터로 되쓴 회귀이며, 그 맵은 **영구 Push 거절 상태**가 된다. 확인창이 말한 "값 있는 셀 N칸"과 실제 놓인 칸 수도 일치해야 한다(노치 1칸 차이가 원 결함).
- [ ] 🔴 **회사 양식 왕복 — 삭제 권한 없음**: 값 3개짜리 DOE에서 복사 → 엑셀에서 **한 행을 지우고** 되붙이기 → 그 값이 **legend에서 사라지면 안 된다**(복사본에 없는 값 = "이 복사본이 말하지 않은 것"). 삭제는 DOE 패널 삭제 버튼만 한다.
- [ ] **회사 양식 왕복 — 왕복하지 않는 것**: 자재(1H/MID/TOP)를 채운 맵을 복사 → 표①의 자재를 지우고 되붙이기 → **자재는 복원되지 않는다**(상단 그룹 띠는 읽지 않으므로 — 결함이 아니라 명시된 계약). COLOR도 마찬가지로, 기존 값은 **자기 색을 유지**하고 새 값만 팔레트가 배정한다.
- [ ] **회사 양식 왕복 — 남의 클립보드는 조용히**: 다른 화면·다른 앱에서 긁은 표를 맵 화면에서 Ctrl+V → **토스트 없이 그냥 지나간다**(아무 붙여넣기에나 경고가 뜨면 회귀). 반대로 DOE 패널 안에서의 붙여넣기는 **패널이 처리**하고 격자가 가로채지 않는다. 입력 칸 포커스 중의 붙여넣기도 그 칸의 것이다.
- [ ] **머리줄 로스터 = 집합(`5a14e77`)**: `contracts/doe_band_rules` 하네스가 `IGNORED_HEADERS`를 **13개 정확히**로 단언한다(§2.0에서 함께 통과). 14번째를 넣거나 하나를 빼면 하네스가 빨개져야 한다 — 표본 단언이던 시절에는 `COUNT` 추가에 331 단언이 전부 초록이었다. ⚠️ 롤업 8단어(`MAT`·`BIN`·`MAP`·`가용`·`사용`·`사용≈`·`잔여`·`잔여≈`)는 **예비**다: `rollupToGrid`는 importer 0건이라 표②→표① 왕복은 **배선돼 있지 않다**. 그 단어들이 목록에 있다는 이유로 "②를 붙여넣을 수 있다"고 점검하지 말 것.
- [ ] **프리셋 라우팅 — 서버 단독(F5 `50bddda`)**: `map_overlay_config.json`에 `preset_routing`을 선언하고 `curl "…/api/maps/preset-routing?table=<t>&map_key=<k>"` → ⓐ 규칙에 맞는 랏은 `status: ok` + `preset_key`, ⓑ **`wafer_map_metadata`가 있는 맵은 `meta_present` + `preset_key: null`**(저장된 규격을 라우팅이 못 덮는다 — 뒤집히면 회귀), ⓒ 선언 없는 테이블은 `not_declared`, ⓓ 어느 규칙에도 안 걸리면 `no_match`. **`ok`가 아닌 모든 응답에서 `preset_key`/`preset`이 `null`**인지 확인(그럴듯한 프리셋을 지어내면 회귀 — 틀린 규격은 저장 가능 집합을 바꾼다). ①의 조회 테이블이 없거나 miss여도 **경고 로그가 뜨지 않고** 조용히 ②로 떨어지며 결과는 `lookup.status`에만 나온다. ✅ **이 항목은 서버 절반만 봅니다.** 종전에 여기 있던 *"HEAD `c9bf2c7` 기준 에디터 동작은 변하지 않는다(클라 절반 미착지)"*는 `73b5925` 이후 **거짓**입니다 — `applyRoutedPreset`가 `loadExistingMap`에서 로드당 1회 부르므로 **맵을 열면 규격이 실제로 바뀌고 알림이 남습니다**(그것이 정상). 화면 쪽 점검은 §1.7 프리셋 라우팅 행의 ①~④를 쓰십시오.
- [ ] 🔴 **유효 다이 — 크기가 다른 참조를 지정해도 저장 좌표가 안 움직인다 (F8 `61440e6`)**: 셀이 칠해진 맵(예: 45×45)을 열고, **격자 크기가 다른** 유효 다이 템플릿(예: 29×25)을 `🎯 유효 다이 맵` 칸에 지정. 기대 동작 — **거절 없음 · 확인창 없음 · 격자 크기 입력칸 불변 · 셀이 화면에서 안 움직임**, 마스크만 **눈에 띄게 밀려** 보이고 **info 토스트 1회**. 🎯 **핵심 축(눈으로 보는 법 3가지 — 하나만 해도 되지만 ⓑ가 가장 직접적이다)**:
  - ⓐ **구조적 확인(가장 쉬움)**: 좌측 패널의 `Grid Cols`/`Rows`가 그대로이고 셀이 캔버스에서 안 움직였으면 **저장 좌표도 안 움직인 것**이다 — DB x/y는 Push 시점에 **셀의 캔버스 칸**에서 유도되므로, 칸이 그대로면 좌표가 그대로다. 반대로 격자 크기 칸이 참조 값으로 바뀌었으면 **그 자체가 회귀**(채택 부활)다.
  - ⓑ **페이로드 직접 대조**: DevTools Network를 켜고 **지정 전에 한 번** `⚡ Push` → `replace_map` 요청 페이로드 저장. 지정 후 다시 `⚡ Push` → 두 페이로드의 x/y 집합이 **바이트 단위로 같아야** 한다. ⚠️ **물리 키로 대조하면 이 축은 원리적으로 보이지 않는다**(물리 키는 프레임이 바뀌어도 불변이다) — 반드시 **페이로드의 x/y**로 볼 것.
  - ⓒ **DB 확인**: 지정+Push 후 메인 그리드에서 그 맵 테이블의 x/y 컬럼을 열어 **지정 전 값과 대조**.
- [ ] **유효 다이 — 치수 차이로 거절하지 않는다**: 위와 같은 조합에서 *"격자 규격이 다릅니다"* 류 **거절이 뜨면 회귀**다(사용자가 두 번 뒤집은 동작 — `73b5925` 이전으로 되돌아간 것). 확인창이 떠도 회귀다: 읽기는 무마찰이 규율이고, 알림은 **토스트 1회**뿐이다.
- [ ] **유효 다이 — 살아 있는 유일한 거절(치수 정의역, H5)**: 참조 맵의 `wafer_map_metadata`에 `grid_cols=1024, grid_rows=1024`(또는 `0`·`45.5`) 행을 만들고 지정 → **참조 셀을 한 건도 조회하기 전에** 사유와 함께 거절되고 **에디터 격자는 그대로**여야 한다. Network 탭에 그 참조 테이블의 `/data` 요청이 **없어야** 한다(있으면 가드가 조회 뒤로 밀린 회귀). **clamp해서 통과시키면 회귀** — 잘린 치수로 만든 마스크는 화면이 멀쩡한 채 판정만 틀린다.
- [ ] **페인트 잠금**: 맵 로드 → 잠금 값(기본 `F`) 셀에 브러시·Fill·Auto-Paint·오버레이 가져오기 시도 → 전부 차단. `/api/maps/paint-rules`를 500으로 막고 재로드 → **잠금이 풀리지 않고** `⚠ 잠금 규칙 미확인` 칩 + 경고 토스트(fail-open 금지).
- [ ] **오버레이 — 기본 흐름**: `＋ 겹치기`로 다른 테이블/키 맵 추가 → 셀 마커 표시, 표시 토글·제거 동작, 정렬 상태 칩이 **`무보정`(identity) 또는 `정렬됨 N°`(derived)**로 표기. ⚠️ **`declared`는 정렬 어휘가 아니다** — 선언 정렬 레이어는 2026-07-27에 삭제됐고 `declared`가 나오는 곳은 **바인딩 출처**(`binding.source`)뿐이다. 두 어휘가 `derived`를 공유하니 무엇을 보고 있는지 먼저 확인할 것. **메인 맵의 테이블·규격·legend·brush가 하나도 변하지 않는지** 확인(경로 분리 불변식).
- [ ] **오버레이 — 서빙되는 바인딩(F1 `17f65bd`)** 🔴: `map_overlay_config.json`의 `table_bindings`에 **관례 밖 좌표 컬럼**(`dt_log`의 `tx`/`ty`)과 **대문자/한글/숫자 시작 테이블명**을 선언 → 맵 에디터에서 그 테이블을 **선언만으로** 로드·오버레이할 수 있어야 한다(클라가 별도 유도를 하지 않는다). 드롭다운이 선언된 컬럼으로 **미리 선택**되는지 확인. 종전에는 서버만 존중하고 클라가 리터럴 소문자 `x`/`y`를 요구해 "설정이 안 먹는" 상태였다.
- [ ] **오버레이 — 추측 바인딩 거부(F2 `17f65bd`)** 🔴: 값 컬럼 후보(`value_column_candidates`)에 **하나도 맞지 않는** 맵 테이블을 준비 → `GET /api/maps/paint-rules?table=<t>`의 `binding.source`가 **`fallback_guess`**인지 확인 → ⓐ **로드** 경로는 미리 선택하되 **추측 경고**를 낸다 ⓑ **오버레이** 경로는 **거부**한다(추측 컬럼을 칠하면 미끼 셀). 같은 상태에서 `GET /api/maps/overlay`는 `source_missing`으로 답해야 하고 **셀을 하나도 내려보내면 안 된다**.
- [ ] **오버레이 — 행은 있는데 셀 0개**: 소스 맵에 행은 있으나 격자 밖/값 없음으로 그릴 셀이 0개인 상황 → **초록 성공 토스트가 아니라 원인을 이름 붙인 경고**가 떠야 한다.
- [ ] **오버레이 — 좌표 정확성** ⚠️: 회전 90/270 + **비등방 칩**(chip_x ≠ chip_y) + **bbox ≠ 0인 실데이터**(29×25, 27×21 등)로 확인할 것. 40×40(`minC=0`)은 결함이 원리적으로 발현하지 않는 구간이라 통과해도 아무 의미가 없다(과거 2회 이 사각지대에서 "해소" 오판정). 오라클은 앱의 변환 함수를 쓰지 말고 독립 계산으로.
- [ ] **오버레이 — 규격 변경 추종**: 오버레이가 떠 있는 상태에서 회전·면반전·start 좌표 **및 물리값(`phys_chip_*`/`phys_offset_*`)** 변경 → 마커가 메인 맵과 **같은 칸에서 함께** 이동(`syncOverlayGeometry`). ⚠️ **판정은 "오버레이가 움직였는가"가 아니라 "메인 맵과 같은 칸에 있는가"다** — invertY·START는 `(c,r)↔물리` 사상에 개입하지 않으므로 **양쪽 다 안 움직이는 것이 정답**이다(구 설계에서는 이 두 축에서 오버레이만 움직였고, 그것이 사용자가 본 어긋남의 한 갈래였다).
- [ ] **오버레이 — 실패 표면화**: 존재하지 않는 소스 맵 추가 → 목록에 **실패 행으로 남고** 사유 표시(조용히 사라지지 않음). 규격 조회를 5xx로 막아 `meta_unavailable`이 뜨고 **마커가 0개**인지 확인("확인 못 함"이지 "미등록"이 아니다 — 폴백해서 그리면 결함). *(구 `align_unconfirmed` 점검 항목은 선언 probe 삭제로 2026-07-27 폐기)*
- [ ] **오버레이 — 기준 변경 시 해제**: 오버레이를 띄운 채 ⓐ 다른 맵 로드 ⓑ **다른 테이블로 전환** ⓒ 프레임 진입 → 세 경우 모두 오버레이가 사라진다. 특히 ⓑ에서 목록이 비었는지 확인 — 남아 있으면 `가져오기`로 **이전 테이블 값이 새 테이블에 써진다**(`251dbfd`가 닫은 경로).
- [ ] **오버레이 — 캔버스 측정 함정**: 비표시(백그라운드) 창에서는 `requestAnimationFrame`이 멈춰 캔버스가 얼어붙는다. "마커 0개"를 결함으로 판정하기 전에 **탭을 앞으로 꺼내고 명시적 재렌더를 유발**할 것. `phys-*` 입력은 재렌더 예약 목록에 없어 값만 바꾸면 화면이 낡은 채로 남는다.
- [ ] **전사 계획 — 기본 흐름(ZONE)**: `bonding_map` 로드 → 사이드바에 stage가 **자동 유도**되어 표시(선택 UI 없음) → DOE 값 행 펼침 → **STACK 숫자 하나 + 구역 셋(1H/MID/TOP) 자재 입력**(FROM/TO·구간 행·순서 개념 없음) → ⚡ Push 후 재로드 시 유지. `dt_map`은 STACK=1·MID만인 퇴화형이 **조용히 통과**해야 한다.
- [ ] **전사 계획 — 개명 생존(ZONE)**: DOE 값 이름을 바꿔도 층 구조(STACK·구역 자재)가 같은 행에 그대로 붙어 온다 — zone 모델에는 값을 이름으로 가리키는 참조가 없다(구간 모델의 `seq`·`values[]` 폐기).
- [ ] **전사 계획 — replace 권한(C1 회귀)** 🔴: `map_split_registry` **GET만** 500으로 1회 막았다가 **복구**시킨 뒤 편집 → 서버 행이 삭제·덮어쓰기되지 않아야 한다. 지속 실패만 시험하면 **회복 분기를 한 번도 실행하지 않으므로 이 항목은 검증되지 않은 것**이다. 절단 응답(`total > rows.length`)·맵 전환 중 늦은 응답도 같은 방식으로 확인.
- [ ] **전사 계획 — 동시 편집 거부(M2.6 신설)**: 두 세션에서 같은 맵을 열고 A가 저장 → B가 저장 시도 → **upsert로 강등되지 않고 거부**되며 리로드 전까지 그 맵의 쓰기가 막힌다. 강등되면 B의 낡은 층 구조가 A의 것을 덮는다.
- [ ] **전사 계획 — 읽을 수 없는 STACK(V5)**: `stack` 컬럼에 `0x10` 같은 값이 저장된 상태로 로드 → 화면에 **원문 그대로** 표시되고 V5 사유가 뜬다. **재저장해도 값이 `16`이나 빈칸으로 바뀌지 않아야 한다**(정규화기가 값을 고쳐 저장하면 화면에는 아무 잘못도 안 보인다).
- [ ] **전사 계획 — 자재 토큰(ZONE 문법)**: 진짜 malformed 토큰(`ABC_`, `_01`, `_`)은 **조회 요청 자체가 나가지 않고** `미상`으로 표시된다(숫자 `0`이 뜨면 실패 — "조회 못 함"과 "잔여 0"은 다르다). 반면 분리자 없는 `MID1`은 해석 실패가 **아니라 로트 전체 토큰**이다 — `scope=lot`으로 조회되고 슬롯 전개(by_slot)가 뜬다.
- [ ] **전사 계획 — 초과 배정 경고가 죽지 않는가** 🔴: 한 자재에 두 구간이 각각 요구를 걸어 **합계만 초과**하게 만든다(개별로는 부족하지 않게). `validate`가 `status: ok` + 경고 0건을 내면 실패 — 집계 게이트가 라벨 가짓수를 세고 있다는 뜻이다.
- [ ] **전사 계획 — degraded 표기**: 역할 바인딩을 하나 끊고 자재 요약 조회 → `remaining`이 숫자가 아니라 **미상**으로 표시되고 경고가 뜬다. **초록/정상으로 뒤집히면 실패.**
- [ ] **전사 계획 — STACK 0 마커(U9, `2baf9ff`)**: 값의 STACK에 `0` 입력 → 입력이 오류(빨강)로 칠해지지 않고 구역 셀 셋이 **해당 없음**으로 잠기며, 자재 롤업 표에 그 값의 행이 **아예 없다**(「사용 0」으로 존재하면 실패). 구역에 자재가 남은 채 0을 넣으면 그 행에는 **V6 메시지 하나만** 뜬다(V4·V5 동반 금지). 엑셀 복사/붙여넣기 왕복에서 `0`이 적은 그대로 돌아온다. **빈칸은 마커가 아니다** — 여전히 V5.
- [ ] **전사 계획 — ↻ 가용 피드백(U8, `2baf9ff`)**: BIN 축 미선언 등으로 결과가 전부 `미상`인 상태에서 [↻ 가용] 클릭 → 숫자는 그대로여도 **토스트가 조회 완료 사실과 지배적 미상 사유**를 말한다(아무 반응 없이 같은 화면이면 회귀 — "버튼이 죽어 보임"이 원 결함). 사유는 각 `미상` 셀 툴팁에도 남는다.
- [ ] **맵 Push — 적재 대조 게이트(H2, `6db517d`)** 🔴: 메타 미등록 맵을 기본 프레임으로 열어 일부 셀이 격자 범위·원 밖에 놓인 상태에서 ⚡ Push → **confirm 창이 뜨기 전에 거부**되고, 메시지에 "값 있는 셀 N개 중 M개 삭제 예정" 수치가 명시된다. 거부 시 서버 PUT **0건**(DB 행 수 불변). 화면과 페이로드가 동수인 정상 맵(사용자가 지운 셀 포함)은 무마찰 통과.
- [ ] **맵 Push — 로그형 대상 게이트(Gate 4, `deed6d2`)** 🔴: 로그형 테이블(dt_log처럼 맵 계약 밖 데이터 컬럼을 가진 테이블 — `map_push_ok` 미선언)을 맵으로 열고 ⚡ Push → **어떤 다이얼로그도 뜨기 전에 거부**되고, 메시지에 **파괴될 컬럼명이 명시**된다(dt_id·eventtime·장비 컬럼 등). 거부 시 서버 쓰기 **0건**(DB 행 수·값 불변). 맵 **조회**(로드·오버레이 소스)는 계속 정상 동작해야 한다 — 게이트는 Push에만 걸린다. 합성 bk 테이블(bonding_map의 pkg_id)은 로그형으로 오판되지 않고 무마찰 통과.
- [ ] **맵 Push — `map_push_ok` 선언 = 소실 confirm 1회(Gate 4, `deed6d2`)**: 로그형 테이블의 table_config에 `map_push_ok: true`(JSON boolean) 선언 후 Push → 차단 대신 **소실될 컬럼명을 명시한 확인창 1회**가 뜨고, 취소하면 쓰기 0건, 승인하면 진행된다. 선언 값을 문자열 `"true"`/`"false"`로 바꾸면 **여전히 차단**되어야 한다(오타가 파괴를 해제하면 회귀 — 서버 `is True` 판정). 맵 계약 안에 다 들어오는 깨끗한 테이블에 선언해도 **추가 confirm이 생기지 않는다**(inert).
- [ ] **replace_map — 무음 no-op 폐기(U6, `deed6d2`)** 🔴: `map_key_columns` 미선언(그리고 페이로드에서 범위 파생 불가) 테이블에 `replace_map` 요청 → **200이 아니라 400 + 사유**로 거부된다(종전에는 아무것도 안 지우면서 200 — 행이 조용히 누적). 정상 Push의 응답에는 `scope: {filters, deleted, inserted}`가 실려 실제 purge 필터·건수와 일치해야 한다. 명시적 `scope` 필드 + 빈 `updates`는 그 범위 전량 소거로 동작하고 `inserted: 0`이 정직하게 내려온다. 셀 없는 순수 소거 후에도 그리드 행 수 표시가 낡지 않아야 한다(count 캐시 무효화 — 순수 wipe 경로).
- [ ] **메타 없는 맵 — 기본 선택으로 Push 가능(5b `0052d76`)**: `wafer_map_metadata`가 없는 맵 로드 → 좌표계 모달에서 **📐 표준(기본)** 선택 → 데이터 전체가 사각 bbox 격자에 그려지고(마스크로 빠지는 모서리 셀 없음), 편집 없이 ⚡ Push → **적재 대조 게이트에 걸리지 않고** 화면 셀 수 그대로 confirm·적재된다(로드 N건 = Push N건). 종전에는 원 마스크가 살아 있어 기본 선택이 전량 거부됐다(1293→379 거부 회귀). 원형 규격이 필요하면 ⚙️ 좌측 패널 선택이 여전히 동작. Push 후 재로드 → 모달 없이 열림(합성 규격이 메타로 등록됨).
- [ ] **자재 프레임 — 보기만 한 뒤로가기는 조용히(5b `0052d76`)**: 비어 있지 않은 자재 맵에 들어가 **아무 편집 없이** ← 뒤로 → 확인창 **없이** 즉시 복귀. 셀 하나 칠하거나 legend를 고친 뒤 ← 뒤로 → "저장하지 않았습니다" 확인창이 뜬다. 부모 맵이 미저장(`● 저장 안 됨`)인 상태로 자재 왕복 → 복귀 후에도 칩이 **그대로 남아 있다**(왕복이 dirty를 지우면 회귀). 프레임 진입 중 좌표계 모달에서 ❌ 취소 → 빈 격자가 아니라 **이전 화면으로 롤백** + info 토스트 1개(추가 "열기 실패" 에러 토스트가 겹치면 회귀).
- [ ] **전사 계획 — count_only 강등 = 미상이지 0이 아님(5c `1fefd12`)** 🔴: `transfer_log` 바인딩에서 x/y를 빼고(또는 좌표가 null인 로그로) 자재 요약 조회 → `sources.transfer_log`가 `connected(count_only)`, **기전사 카운트는 숫자로 유지**되되 잔여는 `미상`(+상한)으로 표시되고 코어별 분해의 used/remaining도 미상이다. **잔여가 `total − 0`짜리 맨숫자로 나오면 유령 잔여 회귀**(+101 재현으로 실증된 원 결함 — log·area_map 양 경로 모두 확인). `fail_sources`의 `val` 컬럼명을 오타로 바꾸면 fail이 전-행-count로 뛰지 않고 **0 + `connected(column_unresolved:val)`**로 강등된다.
- [ ] **전사 계획 — self-frame fail도 count_only = 미상이지 틀린 숫자가 아님(`deed6d2`)** 🔴: `origin_log`가 connected인 상태에서 `frame: "self"`인 fail 원천을 x/y 없이(또는 좌표가 null인 원천으로) 바인딩하고 자재 요약 조회 → 그 원천 status가 `connected(count_only)`, **fail 카운트는 `fail_breakdown`에 숫자로 유지**되되 잔여는 `미상`(+상한)이고 코어별 분해의 fail·remaining도 미상(used는 숫자 유지)이다. **잔여가 맨숫자로 나오면 유령 잔여 회귀**(원 결함 재현: 256/256 칩이 'fail'인데 remaining 209가 `reliable: true`로 정상 표시). `origin_log`를 끊은 폴백 경로에서는 같은 원천이 강등 없이 count 감산으로 동작해야 한다(폴백은 감산이 정확 — 과잉 강등도 회귀).
- [ ] **전사 계획 — 선언된 미추적 소비(7c `ab6ac02`)** 🔴: stage의 `source.transfer_log`를 **정확히 문자열 `"none"`**으로 선언하고 자재 요약 조회 → `sources.transfer_log`가 **`connected(untracked)`**이고 `source_degraded` 경고는 **뜨지 않는다**(강등이 아님). `transferred`는 **`null`**(0이면 실패 — "한 칩도 안 썼다"로 읽힌다), `remaining`은 `null` + `remaining_upper_bound`(= 총 − fail) + 경고 `transfer_untracked`. `?bins=`의 각 항목도 `transfer_untracked: true` + 상한, `by_core`의 used/remaining은 **양 경로 모두 null**. ⚠️ **어휘 엄격성 회귀 시험**: 같은 자리를 JSON `null` / 키 삭제 / `"None"` / `"NONE"`으로 바꾸면 **전부 종전 `missing`**이어야 한다(하나라도 untracked로 통과하면 오타가 깨진 바인딩을 자신만만한 숫자로 바꾼다).
- [ ] **전사 계획 — 캐노니컬 키 바인드(7b `ab6ac02`)** 🔴: `number` 선언 slot 컬럼을 가진 풀에서, 자재 토큰을 **패딩된 형태**(`LOT_01`)로 주고 조회 → **패딩 없는 `LOT_1`과 같은 수**가 나와야 한다(0이나 `미상`이면 회귀 — 운영에서 실제로 가용이 0으로 보이던 결함). 같은 축으로 ⓐ `' 1 '`(공백) ⓑ Float 컬럼의 `1.0` 왕복 ⓒ `map_id` 조합(메타 조회가 실제로 히트하는지 — `align_unavailable`로 떨어지면 실패)까지 확인. **반대 방향도 시험할 것**: `string` 선언 컬럼에서는 `'01'`과 `'1'`이 **서로 다른 키로 남아야** 한다(패딩이 유의미한 사이트를 뭉개면 회귀). 읽을 수 없는 값(`'A1'`)은 지어낸 키가 아니라 원문으로 조회돼 정직하게 빗나간다.
- [ ] **전사 계획 — 이동 허브**: 자재 행 클릭 → 해당 자재 맵으로 이동, 브레드크럼·뒤로가기로 복귀 후 그 자재만 재조회.
- [ ] **브레드크럼 좁은 폭 생존(U7, `a98dc72`)**: 자재 프레임에 들어가 브레드크럼 바를 띄운 채 창 폭을 좁힌다 → 긴 crumb가 **말줄임(…)** 되고, ← 뒤로 버튼은 찌그러지지 않으며, 힌트 문구는 제 줄로 내려간다(바가 가로로 넘치거나 민짜 텍스트로 보이면 `.map-breadcrumb`/`.bc-*` 룰 소실 회귀 — `b35bc9f` CSS 재작성이 실제로 떨궜던 것).
- [ ] **없는 풀 클릭 = 빈 프레임(LOAD 동등성, `280ebf0`)**: 아직 맵이 없는 dt_map 풀(분해 안 되는 원문 ID 포함) 행 클릭 → 에러 토스트가 아니라 **빈 격자 프레임**으로 이동하고, ⚡ Push하면 그 키가 생성된다. 단 목록의 존재 표시는 여전히 `미상`/없음을 유지해야 한다(라우팅은 추측해도 **존재 주장은 추측하지 않는다**).
- [ ] **같은 테이블 연속 빈 맵 로드 = 시드 한 행(U6-1, `95bf072`)** 🔴: legend가 여러 값인 맵을 로드한 뒤 **테이블 전환 없이** 같은 테이블에서 레지스트리 행이 없는 빈 키를 로드 → legend가 **정확히 VALUE 1 한 행**으로 리셋된다(이전 맵의 값들이 남아 있으면 legend 유출 회귀 — 그 상태로 Push하면 이전 맵의 계획이 새 키에 써진다). 반대로 레지스트리 **조회를 5xx로 막고** 로드하면 행이 **보존**되어야 한다(읽기 실패는 "비어 있음"이 아니다).
- [ ] **선언 legend 색 우선(U6, `95bf072`)**: `map_overlay_config.json`의 `default_legend`에 `E1` 행을 색·설명과 함께 선언하고 ⚡ Auto-Paint E1/E2 → E1이 **선언된 색·설명**으로 legend에 추가된다(고정 hex `#8b5cf6`가 아니라). 선언 없는 값(E2)은 팔레트 규칙으로 미사용 색을 받는다. 빈 맵을 열 때의 초기 legend도 선언 행 그대로다(미선언 서버는 VALUE 1 한 행).
- [ ] **페인팅 새로고침 생존(`b35bc9f`+H1 `6db517d`)**: ⚠️ **서버에 이미 행이 있는(비어 있지 않은) 맵에서** 검증할 것 — H1 이전에는 로드 경로가 서버 상태를 초안에 먼저 되써 **비어 있지 않은 맵에서만 전멸**했다(빈 맵 검증은 이 회귀를 못 잡는다). 드래그로 수백 셀 페인팅(클릭 편집만으론 불충분 — 드래그·fill·paste 경로 검증) → 1초쯤 기다렸다 새로고침 → **그림이 돌아오고** 「복구했습니다」 토스트와 함께 패널 헤더에 `● 저장 안 됨 · [⚡ Push]로 저장` 칩이 떠 있다(복구된 편집은 여전히 미저장). Push 성공 후 새로고침 → 칩이 사라지고(초안 삭제) **유령 「복구」 토스트가 뜨지 않는다**(복구 = 화면이 실제로 바뀐 경우만). 다른 세션이 그 사이 저장했다면 서버본이 뜨고 초안은 **조용히 버려지지 않고** 토스트로 드러난다.
- [ ] **새로고침이 마지막 맵을 다시 연다(`280ebf0`)**: 맵 로드 → 새로고침 → 초기 화면이 아니라 **같은 테이블·같은 맵**이 다시 열린다(메타 입력 복원 포함). 자재 프레임에 들어간 채 새로고침 → 프레임이 아니라 **루트 맵**으로 복귀. 테이블이 사라진 뒤엔 조용히 초기 화면(에러 다이얼로그 금지). 메타 미등록 맵은 복원 시에도 좌표계 선택 모달이 다시 뜨는 것이 **정답**(조용히 추측하면 회귀).
- [ ] **DOE 입력 즉응(`280ebf0`)**: DOE 값 행의 STACK·자재 입력을 **첫 클릭**에 커서가 잡히고 즉시 타이핑된다(두 번 클릭 필요하거나 ~0.3초 배경 램프가 보이면 회귀 — 행 선택이 목록 innerHTML 재빌드나 전체 격자 카운트 스캔을 유발하고 있다는 뜻).
- [ ] **오버레이 블록 스타일(`280ebf0` 회귀 방지)**: 좌측 「겹치기」 오버레이 블록이 로드 패널과 같은 스타일로 렌더된다(민짜 HTML로 보이면 `.overlay-box`/`.ov-*` 룰 소실 회귀 — `b35bc9f`의 CSS 재작성이 실제로 떨궜던 것).
- [ ] **전역 토스트**(전 페이지): 에러 토스트 4개를 띄운 뒤 성공 토스트 1개 → **새 토스트가 즉시 사라지지 않고** 가장 오래된 에러가 밀려난다. 토스트를 띄운 채 탭을 30초 이상 백그라운드로 두었다 복귀 → **만료된 토스트가 즉시 정리**된다(누적 없음). 같은 `dedupeKey`의 비-에러 알림 반복 → `… · N건`으로 합쳐진다. 에러는 **합쳐지지 않는다**.
- [ ] **토스트 위치 = 하단 중앙 배너(U3, `a98dc72`)**: 토스트가 **하단 중앙**에 배너로 뜨고, 등장·퇴장이 **opacity만**이다(위로 떠오르는 rise 애니메이션이 보이면 회귀). 우하단에 뜨거나 자재 패널 우하단을 가리면 구 배치 회귀(`--toast-inset-right` 워크어라운드는 삭제됨 — 참조 0 확인 후 제거).

### 2.10 어드민 대시보드 (5탭 IA)

> 🔒 **선행: §2.16을 먼저 통과시킬 것.** 2026-07-27부터 이 절의 모든 화면은 토큰 게이트 뒤에 있다 — 게이트가 막고 있는 빈 표를 "렌더 결함"으로 오진하기 쉽다.

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
- [ ] **config 백업이 살아 있다**(C3, 2026-07-28): `backup_config.py check` → `ok`. `/health`의 `checks.config_backup.status`도 `ok`이고 `problems`에 백업 줄이 없다.
- [ ] 🎯 **멈춘 백업이 보인다**: 최신 스냅샷을 잠시 다른 이름으로 옮긴다 → `/health`가 **`degraded`(HTTP는 200 유지)** + `problems`에 `config backup: ...` 한 줄. 되돌리면 사라진다(캐시 60초). ⚠️ **503이 되면 회귀다** — 백업 부재로 멀쩡한 스택을 재기동시키면 안 된다.
- [ ] 🎯 **복원이 실제로 된다**(격리 환경에서만): 스냅샷을 뜬 뒤 `transfer_plan_config.json`을 깨뜨리고 → `restore <파일> --yes` → `GET /api/transfer-plan/stages`의 `target_map.table`이 **되돌아오는지**. 실측 0.17초. *(파일이 바뀐 것은 증거가 아니다 — 도메인 응답으로 판정한다)*
- [ ] **연속 저장이 버려지지 않는지**(2026-07-29 H2로 해소된 함정의 회귀 점검): `table_config.json`을 고친 직후(1초 이내) 곧바로 복원한 뒤, **`information_schema`의 물리 컬럼이 최종 디스크 선언과 일치**하는지 확인. 예전에는 두 번째 쓰기가 통째로 버려져 파일은 옳은데 시스템이 옛 선언을 서빙했다. 반영은 **마지막 쓰기 후 약 1초**이므로 즉시 확인하지 말고 1초 기다린다.
- [ ] **저장 방식 무관**(#9/H3): 제자리 저장 · 같은 폴더 temp+rename · **다른 폴더 temp+rename** 세 가지 모두에서 ALTER가 반영되는지. 세 번째는 `moved` 이벤트가 아예 없어 예전에는 무음 누락이었다.
- [ ] **BOM 붙은 config로 재기동**(H1): PowerShell `Set-Content -Encoding utf8`(UTF-8 BOM) 또는 `>` 리다이렉트(UTF-16)로 저장한 `table_config.json`으로 웹서버가 **정상 기동**하는지. 예전에는 이 상태로 영영 안 떴다.
- [ ] **설치 스크립트 안전성**: `install_product_tables.py`(인자 없음) → **아무것도 쓰지 않고** 할 일만 출력. `--apply` 후 현장 항목의 키 순서·들여쓰기가 그대로인지.

### 2.16 접근 통제 🎯 — 2026-07-27 신설 (`90e284f`)

> 🚨 **전 항목을 사내망 평문 HTTP 주소(`http://<사내IP>:8080`)에서 점검한다.** `localhost`/`127.0.0.1`에서 통과한 것은 **아무것도 증명하지 않는다** — 공격면도 사용자도 그 주소에 있지 않다. 이 절이 닫는 결함 중 하나는 실제로 라이브에서 열려 있었고, 로컬에서는 보이지 않았다.
> **순서가 있다.** 번들 확인(첫 항목) → 미설정 상태 → 설정 상태. 번들 확인을 건너뛰고 토큰을 켜면 어드민에서 잠기고, 되돌리려면 보안 조치를 취소해야 한다.

**A. 토큰을 켜기 전에**

- [ ] 🎯 **번들 선행 확인**: `grep -c X-Admin-Token client2/dist/assets/admin-*.js` → **1 이상**. **0이면 여기서 멈추고** `cd client2 && npm run build` 후 `dist/` 커밋. 0인 채로 토큰을 켜면 어드민 페이지가 401만 받고 **프롬프트조차 뜨지 않는다**(서버가 서빙하는 것은 소스가 아니라 번들이다).
- [ ] 🎯 **traversal은 404다**(토큰 설정 여부와 무관 — **인증 없이** 확인할 것):
  ```bash
  # 🚨 --path-as-is 가 없으면 curl이 클라이언트에서 ../를 접어 버린다.
  #    그 경우 서버에는 traversal이 도착조차 하지 않고, 404를 보고 "닫혔다"고 오판한다.
  H=http://<사내IP>:8080
  curl -si --path-as-is "$H/../../server/config/table_config.json"  | head -1   # 404
  curl -si --path-as-is "$H/../../../../../../Windows/win.ini"      | head -1   # 404
  curl -si --path-as-is "$H/../../server/admin_auth.py"             | head -1   # 404
  curl -si --path-as-is "$H/%2e%2e%2f%2e%2e%2fserver/admin_auth.py" | head -1   # 404 (인코딩 변형)
  curl -si "$H/index.html"                                          | head -1   # 200 (정상 서빙은 살아 있어야 한다)
  ```
  ⚠️ **상태코드만 보지 말고 본문을 볼 것.** 200에 SPA HTML이 오는 것은 catch-all의 정상 동작이고, **파일 내용이 오면 실패**다. 위 4종 외에 `..%5c`(백슬래시)·절대경로 `/C:/Windows/win.ini`·드라이브 상대 `C:server/admin_auth.py`도 던진다 — **문자 denylist로 막은 구현이라면 바로 여기서 갈린다.**
  ⚠️ **403이 와도 회귀다.** 탈출이 파싱됐다는 사실조차 확인해 주면 안 된다.
  > 브라우저 주소창으로는 이 점검을 할 수 없다(브라우저도 `../`를 접는다). `curl --path-as-is` 또는 raw 소켓으로만 가능하다.

**B. 토큰 미설정 상태 (`ASSY_ADMIN_TOKEN` 없이 기동)**

- [ ] **배너가 상태를 말한다**: 기동 로그 첫머리에 `[admin-auth] ... is NOT set`이 **WARNING**으로, 무엇이 꺼졌고 어떤 변수를 설정해야 하는지 담겨 있다.
- [ ] 🎯 **위험한 둘만 막힌다**: 어드민 코드 에디터 저장(`POST /admin/scripts/code`)·AutoUpdate Run Now → **503**, 본문에 "환경변수를 설정하고 재시작하라"는 문장. **그 문장이 화면 토스트로 보이는지** 확인(삼키면 "저장 중 오류"만 남아 503 분기의 존재 이유가 사라진다).
- [ ] **나머지는 열려 있다**: 5탭 전부 정상 렌더 + 토큰 프롬프트가 **뜨지 않음**. (첫 재기동에 운영자가 어드민 전체에서 잠기지 않게 한 의도된 상태다.)

**C. 토큰 설정 상태 (스택 전체 재기동 후)**

- [ ] **배너 `INFO`**: `[admin-auth] ... is set`.
- [ ] 🎯 **헤더 없이는 안 된다**: `curl -si http://<사내IP>:8080/admin/chain/rules | head -1` → **401**, 응답에 `WWW-Authenticate: X-Admin-Token`. 틀린 토큰 → **403** + 같은 헤더. 올바른 토큰(`-H "X-Admin-Token: <값>"`) → 200.
- [ ] **`/health`는 계속 무인증**: 헤더 없이 `curl -i .../health` → **JSON 200**. 401이 오면 회귀다(잠그면 감시가 무의미해진다).
- [ ] 🎯 **비-ASCII 토큰은 잠그지 않고 거부된다**: `ASSY_ADMIN_TOKEN=관리자토큰` 으로 기동 → 배너가 **`ERROR`**, 그리고 상태는 **미설정과 동일**(코드 실행 2개 503, 나머지 열림). **"is set"이라고 안심시켜 놓고 올바른 토큰에 403을 돌려주면 실패** — 이게 복구 불능 상태를 만드는 경로다.
- [ ] 🎯 **워커가 토큰을 못 받으면 조용히 멈춘다**: 워커를 런처 밖에서 **변수 없는 셸**로 띄우고 파일 드롭 → 워커 로그에 `API notification failed: ... -> 401`이 쌓이고 **그리드가 갱신되지 않는다**. 런처(`run_decoupled_app.py`)로 정상 기동하면 워커가 환경을 상속해 별도 설정 없이 동작.
- [ ] **어드민 프롬프트 1회**: 어드민 페이지 최초 진입 → 프롬프트 1회 → 붙여넣기 → 5탭 정상. 새로고침해도 다시 묻지 않음(`localStorage`).
- [ ] 🎯 **정상 토큰이 파괴되지 않는다**(가장 비싸게 산 항목): 격리 서버(`devenv.py up`)에서 **라이브 트리로 쓰기**를 시도해 `_resolve_admin_script_path`의 **격리 403**을 유발 → 토큰 프롬프트가 **뜨면 안 된다**(그 403에는 `WWW-Authenticate`가 없다). 뜬 뒤 아무거나 입력하면 **멀쩡한 토큰이 덮어써진다.**
- [ ] **동시 401 → 프롬프트 1회**: 토큰을 지우고 Overview 진입(동시 요청 다수) → 모달이 **하나만** 뜬다. 두 번째 모달이 **올바른 토큰을 두고** "거부되었습니다"라고 말하면 세대 카운터 회귀.
- [ ] **취소가 토큰을 지우지 않는다**: 프롬프트에서 취소(Esc) → 토스트 안내 후 **더 묻지 않음**. 30초 갱신 타이머가 모달을 반복해 띄우면 실패. 저장돼 있던 토큰이 빈 문자열로 덮어써져도 실패.
**D. 내부 통지 진단 (2026-07-30 `23a346d`)** — 이 넷은 **실패했을 때 무엇을 봐야 하는지**를 점검한다. 원 사고에서 세 시간이 든 판별이다.

- [ ] 🎯 **4xx가 누가 거절했는지 말한다**: 워커를 **변수 없는 셸**로 띄우고 파일 드롭 → 워커 로그의 통지 실패 줄에 **`admin-gate=yes token-fingerprint=none`** + "이 프로세스에 변수가 없다"는 REMEDY가 함께 나온다. 이어서 **다른 토큰**을 든 셸로 띄우면 `admin-gate=yes` + **403** + "서버가 다른 토큰을 쥐고 있다, 지문을 배너와 대조하고 **트리 전체**를 한 셸에서 재기동하라". 숫자만 있고 진단이 없으면 회귀.
- [ ] 🎯 **`admin-gate=no`는 우리가 아니다**: `/internal/events/*`를 가로채는 것(프록시·다른 프로세스)을 앞에 두고 통지 → 로그가 **`admin-gate=no`** + *"NOT AN ADMIN-TOKEN FAILURE"* + 본 헤더 에코. 🔴 이 상태에서 **토큰을 고치라고 안내하면 회귀**다 — 실제 사고에서 그 오안내가 진단을 몇 시간 늦췄다. 판정 근거는 `WWW-Authenticate: X-Admin-Token`의 **정확 일치**이므로, 프록시가 `WWW-Authenticate: Basic realm=…`을 붙여도 `no`로 읽혀야 한다.
- [ ] **기동 로그가 프록시를 먼저 말한다**: 데몬 3종(`run_watcher`·`chain_ingestion_worker`·`graph_sync_worker`) 기동 로그에 `[internal-events] http://127.0.0.1:8080/health -> 200, direct (proxy bypassed). proxy-env=…`가 **정상일 때도** 찍힌다. `/health`가 **200이 아닌 HTTP 상태**로 답하면 `ERROR`(게이트가 없는 경로라 상태가 온다는 것 자체가 "우리가 아니다"의 증거), **연결 거부는 `INFO`**(기동 순서상 정상 — 여기에 경고를 울리면 아무도 안 읽는다).
- [ ] **발신자가 자기 세션을 만들지 않는다**: `conda run -n assy_manager pytest server/tests/test_admin_auth.py -k "own_client or trust_the_environment"` → 통과. 새 워커가 `requests.post(`를 직접 쓰면 **여기서 빨개져야** 한다(같은 결함이 발신자별로 세 번 재발한 자리라, 규칙이 아니라 테스트로 못박혀 있다). ⚠️ **`NO_PROXY` 환경변수를 이 문제의 처방으로 쓰지 마라** — 그 트리의 모든 자식이 프록시를 못 타게 되어 자동 업데이트가 죽는다([DEPLOY_SETUP §1-5](../guide/DEPLOY_SETUP.md)).

**E. 그 밖**

- [ ] **맨 `fetch` 잔존 없음**: `client2/src/`에서 `adminFetch`를 거치지 않고 `/admin/` 경로를 직접 부르는 곳이 **0건**이어야 한다.
  ```bash
  grep -rn 'fetch(`${API_BASE}/admin/' client2/src/     # 0건
  ```
  남은 호출부는 **미설정 서버에서 멀쩡히 동작하다가 운영에서만** 401이 난다 — 개발 환경에서 절대 안 잡히는 부류다.
- [ ] **라우트 커버리지 회귀**: `pytest server/tests/test_admin_auth.py` 통과.
- [ ] ⚠️ **열거가 못 잡는 축은 사람이 본다**: `grep -rn '@app.websocket\|app.mount' server/main.py` → `/admin` 접두 라우트가 새로 생겼는지 눈으로 확인. `route.methods`가 `None`이라 **위 테스트는 이것을 통과시킨다**.

*이 문서는 기능 병합 시마다 doc-keeper가 갱신한다 — [CONTRIBUTING](../process/CONTRIBUTING.md) · 소유 매핑: [DOC_OWNERSHIP](../process/DOC_OWNERSHIP.md).*
