# 🖼️ Frontend Architecture

> **Status:** 🟢 Living | **Last-verified:** 2026-08-27 | **Owner:** Client
> **Source-of-truth:** `client2/src/*` · `client2/vite.config.js` · `client/desktop_wrapper.py`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 라우트 계약: [backend §2](./backend.md)

> 🔴 **이 헤더에 라운드 기록을 쌓지 마십시오.** 변경 이력은 [`docs/history/`](../history/)가 소유합니다.
> 이 문서는 «지금 무엇이 있고 어떻게 도는가»만 적습니다.

---

## 1. 개요 — 웹앱 + 얇은 데스크톱 셸

메인 클라이언트는 **`client2`(웹)**이고, 데스크톱 앱은 그것을 감싸는 QtWebEngine 셸입니다.

- **`client2/`** — Vite 멀티페이지 앱. 바닐라 ESM + AG-Grid. 프레임워크 없음
- **`client/desktop_wrapper.py`** — `{해석된 서버}/?client=desktop` 를 로드하는 `QWebEngineView`.
  그 플래그가 `state.isDesktop` 을 켜고, 웹앱은 그때만 네이티브 경로를 씁니다

실측 규모(2026-08-27 `wc -l`): `src/*.js` 최상위 **39 파일 · 37,121줄** ·
`src/map2/` **18 · 10,437** · `src/rnd_board/` **19 · 6,183**.
숫자는 정확성이 아니라 **무게중심**을 읽는 열입니다.

### 1.1 데스크톱 셸이 «하는 것»

| 기능 | 구현 |
|---|---|
| OS 드래그앤드롭 업로드 | `DropEventFilter` → `window.currentTable` 조회 → `httpx` 로 `{base}/tables/{t}/upload` POST |
| 폴더 드롭 | 디렉터리를 떨어뜨리면 하위 파일을 걷어 **한 번에** 올리고 알림은 «끝에 한 번» |
| 네이티브 다운로드 다이얼로그 | `handle_download_request` → `QFileDialog` |
| DevTools | F12 인스펙터, 원격 디버깅 :9222 |
| URI 스킴 | `assymanager://` HKCU 등록. 등록 커맨드는 **서버 주소를 담지 않습니다** |

### 1.2 서버 주소 해석 — 셸이 «어느 서버를 보는지»의 유일한 결정 지점

`resolve_server_target()` 하나가 결정하고 `base_url()` 이 URL 문자열을 만드는 유일한 자리입니다.
소비자는 각자 경로만 붙입니다.

| 순위 | 원천 | 이유 |
|---|---|---|
| 1 | `--server` 인자 | 한 번 다른 서버에 붙이는 일이 파일 편집을 요구해선 안 된다 |
| 2 | `ASSY_SERVER` 환경변수 | 배포 스크립트·바로가기용. **빈 값은 미선언으로 취급** |
| 3 | `client_settings.json` | 사람이 편집하는 자리 |
| 4 | 기본값 `127.0.0.1:8080` | 파일이 없어도 이전과 같은 동작(무회귀) |

🔴 **선언이 있는데 잘못되면 «조용히 기본값으로 내려가지 않고» 거절합니다**
(`ServerTargetError` → stderr + `QMessageBox` + `exit 2`).

- **시작 로그 한 줄**이 `source: arg|env|client_settings.json|default` 를 찍습니다 —
  그게 없으면 운영자가 「내 편집이 먹었나」를 알 수 없습니다
- `--print-target` — 해석·출력 후 종료하는 헤드리스 점검 경로(GUI·HKCU 미접촉)
- `extend_no_proxy()` — 해석된 호스트가 LAN 주소면 `NO_PROXY` 에 더합니다.
  기준값이 루프백뿐이라 사내 프록시가 있는 곳에서 업로드가 403 이 되는 것을 막습니다
- ⚠️ **exe 는 재빌드가 필요합니다** — `client/dist/`·`client/build/`·`client/*.spec` 은
  의도적으로 gitignore 입니다. 소스를 바꿨으면 exe 는 낡습니다

---

## 2. 진입점 & 빌드

`vite.config.js` 의 `rollupOptions.input` 이 멀티페이지 빌드를 정합니다.

| HTML | ESM | 페이지 | nav 도달 |
|---|---|---|---|
| `index.html` | `src/main.js` | 데이터 그리드(메인) | — (첫 화면) |
| `admin.html` | `src/admin.js` | 어드민 — 파이프라인 생애주기 탭 (Monaco) | ✅ |
| `map_editor.html` | `src/map_editor.js` | 웨이퍼 맵 에디터 | ✅ |
| `map_editor2.html` | `src/map_editor2.js` + `src/map2/*` | 맵 정렬 화면. 레거시 에디터를 **대체하지 않고 «옆에»** 섭니다 | ✅ |
| `rnd-board.html` | `src/rnd_board/*` | **R&D 진단 보드** — 조립식 부품의 격자 (§4) | ⛔ 링크 없음 · 직접 연다 |
| `graph.html` | `src/graph_viewer.js` | 데이터 소스가 은퇴한 페이지. **묘비**를 그립니다 | ⛔ |
| `trace.html` | `src/trace.js` | 같은 은퇴. 서버가 410 을 냅니다 | ⛔ |

🔴 **묘비는 상태코드가 아니라 `detail.reason` 을 봅니다** — 410 은 다른 사정으로도 오고,
그때 「은퇴했다」고 쓰면 거짓말이 됩니다.

```bash
cd client2
npm run dev       # :5173 개발서버 (API/WS 는 127.0.0.1:8080 을 봅니다)
npm run build     # prebuild(§2.1) 통과 후 dist/ 생성
```

빌드 산출물 `dist/` 는 FastAPI(:8080)가 서빙합니다. `define` 이 빌드 타임에
`import.meta.env.VITE_USER`(OS 사용자명)를 넣고 `config.js` 의 `CURRENT_USER` 가 그것을 읽습니다.

🔴 **클라 변경은 빌드 전엔 안 끝났습니다.** 소스에 있고 `dist/` 에 없으면 사용자에겐 «없는 것»입니다.
그리고 **빌드 판정은 종료코드가 아니라 `dist` 해시**로 합니다 — `npm run build` 가 exit 0 을 내면서
`dist` 가 그대로인 경우가 실제로 있었습니다.

### 2.1 빌드 게이트 — 클라 절반을 채점하는 유일한 자리

`package.json` 의 `prebuild` 가 `check:clipboard && check:contracts && check:harnesses` 를
순서대로 돌리고, **하나라도 실패하면 `vite build` 에 도달하지 않습니다.**

| 스크립트 | 무엇을 채점하나 |
|---|---|
| `check:clipboard` | 클립보드 관례 (`scripts/check_clipboard_convention.mjs`) |
| `check:contracts` | `contracts/*/client_harness.mjs` **발견식 스캔** — 이음새의 클라 절반을 `vectors.json` 에 채점 |
| `check:harnesses` | `client2/tests/*.mjs` **발견식 스캔** (`scripts/check_harnesses.mjs`) |
| `check:suggest-keys` | 값 제안 셀 에디터의 키보드 계약. `prebuild` 에는 없고 위 스캔에 «흡수»돼 있습니다 |

실측 2026-08-27: 하네스 **60** · 계약 **8**.
🔴 **이 문서는 그 수를 게이트로 쓰지 않습니다** — 러너가 스캔한 것을 찍고, 여기 적힌 수는 사본입니다.

#### 이 게이트가 스스로에게 거는 네 규칙

```
① 발견식이지 목록이 아니다   러너가 디렉터리를 «스캔»한다. 하드코딩 목록은 「추가했는데 안 돌았다」를 만든다
② 빈 스캔은 «실패»다         하네스가 하나도 안 잡히면 「0개, 전부 초록」이 아니라 exit 1 이다
③ ASSERTIONS 프로토콜        종료코드는 «근거 없는 판결»이다. 하네스는 `ASSERTIONS <ran> <failed>` 를 찍는다
④ 플로어와 천장              FLOORS 는 「이만큼은 채점해야 한다」 · CEILINGS 는 「이 수는 여기서 더 못 자란다」
```

- **플로어** — 초록 하네스도 최소 `ran` 을 기록하고, 그 아래로 떨어지면 하네스 자신이 exit 0 이어도 BLOCKING
- **천장** — 지금 걸린 항목은 `undeclared_identifier_harness.mjs` 의 `MODULE_STATE`(최대 48).
  세는 규칙은 **세는 쪽에 삽니다**: 러너는 세지 않고 하네스가 찍는 `MODULE_STATE <n>` 줄을 «읽습니다» —
  채점자가 둘이 되지 않게. 🔴 **줄이 없으면 BLOCKING입니다** — 조용한 천장은 천장이 아닙니다
- ⚠️ **git worktree 에서는 그 하네스가 UNAVAILABLE 입니다**(`rolldown/parseAst` 를 임포트하므로
  `client2/node_modules` 가 있어야 합니다)
- ⚠️ **worktree 는 CRLF 로 체크아웃될 수 있습니다.** 하네스 앵커는 `\n` 이라 «여러 줄» 앵커가
  그 트리에서만 안 맞습니다 — 손대지도 않은 파일이 빨개지면 이것부터 의심하십시오

---

## 3. 모듈 구조 (`client2/src`)

층으로 읽습니다. 파일 이름 목록은 이 표의 유지 주기보다 빨리 낡습니다.

| 층 | 모듈 | 책임 |
|---|---|---|
| 진입/상태 | `main.js` (2,182) · `state.js` · `config.js` · `theme.js` | 부팅, 전역 상태, API 주소, 테마 |
| 통신 | `api.js` · `websocket.js` | REST 호출과 WS 수신·델타 반영 |
| 그리드 | `grid.js` (1,142) · `clipboard.js` (897) · `tsv.js` · `push_columns.js` | AG-Grid 배선, 엑셀형 복사·붙여넣기 |
| 값 편집 | `value_suggest.js` (1,003) · `enrichment*.js` · `timeline.js` (1,148) | 셀 제안, 보정, 이력 타임라인 |
| 맵(레거시) | `map_editor.js` (11,060) · `map_key.js` · `split_registry_row.js` | 웨이퍼 맵 캔버스·좌표·오버레이 |
| 맵2 | `map_editor2.js` + `src/map2/*` (18 파일 · 10,437) | 정렬 화면. 층 경계로 읽습니다 — `view_model` 은 DOM 없이 채점됩니다 |
| 계획 | `transfer_plan.js` (1,875) · `doe_bands.js` (753) | DOE·STACK 구간과 자재 |
| 온톨로지 작성 | `ontology_explorer*.js` (합 ~3,600) · `ontology_path.js` · `ontology_skeleton.js` | 선언 초안 → 검토 → 활성화 |
| R&D 보드 | `src/rnd_board/*` (19 파일 · 6,183) | §4 |
| 어드민 | `admin.js` (3,773) | 파이프라인 생애주기 |
| 묘비 | `graph_viewer.js` (1,274) · `trace.js` · `trace_core.js` · `trace_launch.js` | 은퇴한 데이터 소스를 «은퇴했다고» 말하는 화면 |

---

## 4. R&D 진단 보드 (`src/rnd_board/`)

이 화면이 이 저장소의 **UI 상설 규칙이 적용된 첫 화면**입니다.

### 4.1 조립식 — 규칙 다섯

```
클래스     생성자가 «자기 mount 와 deps»를 받는다. 모듈 수준 상태 «금지»
고유 div   부품마다 자기 div 하나. 남의 div 안을 그리지 않는다
그리드     화면은 그 div 들을 격자에 앉힌다. 배치는 부품 «밖»에 있다
마킹 공유  마킹은 어느 부품에도 속하지 않는다. 밖의 «저장소» 하나에 산다
마킹 여럿  그 저장소가 «이름 붙은 마킹»을 여럿 담는다. 부품은 «읽을 이름»과 «쓸 이름»을 선언한다
```

🔴 **시험은 「같은 화면에 두 인스턴스를 놓고 간섭이 없다」입니다** — 그게 「끼워넣을 수 있다」의 정의입니다.

| 파일 | 줄 | 역할 |
|---|---|---|
| `main.js` | 686 | 구성 루트 — 부품을 격자에 앉히고 deps 를 주입 |
| `api.js` | 1,073 | `walk({start, collect})` 와 `COLLECTS` 선언표. 요청 중복 제거 포함 |
| `panel.js` | 158 | 부품의 바닥 클래스 — `startFor()` 로 읽을 마킹을 푼다 |
| `grid_shell.js` | 128 | 격자 |
| `marking_store.js` · `marking_intersection.js` | 124 · 87 | 이름 붙은 마킹 여럿과 그 교집합 |
| `table_part.js` | 158 | **표 «한 벌»** — 컬럼 선언 `{key,label,align,width,kind}` 으로 구동 |
| `map_panel.js` | 1,053 | 맵 |
| `main_trend_panel.js` | 420 | 트렌드 |
| `walk_box_panel.js` | 352 | 걷기 검색창 — NODE TYPE · KEY · FOLLOW · COLLECT |
| `head_summary_panel.js` · `control_bar_panel.js` | 324 · 255 | 머리 요약 · 컨트롤 바 |
| `candidate_list_panel.js` · `rank_list_panel.js` | 272 · 225 | 후보 · 순위표 |
| `composition_panel.js` · `expanded_layer_panel.js` | 270 · 169 | 구성 · 펼친 층 |
| `reach_panel.js` | 181 | 「여기서 어디로 갈 수 있나」 — 한 홉, 술어당 한 행 |
| `declaration_panel.js` · `marking_status_panel.js` | 150 · 98 | 선언 · 마킹 상태 |

### 4.2 마킹은 «질의의 주어»다

```
마킹      부호 붙은 «노드 집합». 화면 상태가 아니라 walk 의 «시작점»
데이터    그 노드에서 «걸어서 닿는 하위 그래프» 그 자체
부품      선언하는 것은 둘뿐 — { start = 읽을 마킹,  collect = 무엇을 걷나 }
체인      마킹1 --walk--> 서브그래프 --찍기--> 마킹2 --walk--> …  «계속»
```

🔴 **부품이 «거르면» 어긴 것입니다.** 거르는 것은 walk 이 할 일이고, 고칠 것은 `collect` 입니다.
🔴 **화면이 하나 늘 때 fetch 함수가 하나 늘면 어긴 것입니다.** 늘어야 하는 것은 «선언»이지 갈래가 아닙니다.
🔴 **맵과 트렌드는 «같은 collect»입니다.** 시작점만 다릅니다 — 맵은 다른 데이터가 아니라
«한 그룹으로 좁힌 같은 데이터»입니다.

### 4.3 부품을 더할 때 실제로 무는 것 둘

```
① rnd_board_harness 의 «재작성 목록»에 그 파일을 더하지 않으면
   하네스가 «통째로» 죽습니다 (첫 검사 전에 ERR_INVALID_URL)
② 부품이 `options.start` 를 안 받으면 `startFor()` 가 «항상 null» 이고
   그 부품은 «조용히 아무것도 안 묻습니다»
```

그리고 `TablePart.render()` 는 자기 host 를 «비웁니다» — 같은 상자에 덧붙인 주석은 지워집니다.

---

## 5. 맵 에디터 (`map_editor.js` + `map_key.js` + `split_registry_row.js`)

파일 하나가 아닙니다. 아래는 **기능 영역**이고 파일 경계와 일치하지 않습니다.

| 영역 | 대표 함수 |
|---|---|
| 렌더링 | `renderGridCanvas` · `updateCellStyles` · `renderLegendTable` |
| 좌표 변환 | `getDieIndex` · `getDbCoords` · `getWaferBoundingBox` |
| 웨이퍼 mm | `dieIndexToWaferMm`(다이 인덱스 → 그 다이 «중심»의 절대 mm) / `waferMmToDieCell`(역함수) |
| 드래그 선택·페인팅 | `initMouseDragEvents` · `fillSelectedCells` · `remapGridValues` |
| 엑셀 복사 | `copyGridToExcel()` — TSV 클립보드 |
| 데이터 동기화 | `loadExistingMap()`(REST pull) · `pushMapData()`(REST push) |
| 페인트 잠금 | `fetchPaintRules` — **선언 정본이 서버에 있습니다** |
| 오버레이 점의 색 | `legendColorForValue` → `overlayMarkerFill` → `paintOverlayDot` |
| 유효 다이 | 저장 테이블이 `valid_die_ref` 하나로 «고정»(`VALID_DIE_TABLE`) |
| 규격만 저장 | `saveMapSpecOnly` — `grid_metadata` 한 필드만 쓰고 **셀은 한 건도 안 씁니다** |
| 캔버스 축척 | `cellMetrics()` 가 **축척의 단독 생산자**이고 렌더와 마우스 매핑 «둘 다» 그것을 씁니다 |

🔴 **맵 에디터는 WebSocket 을 쓰지 않습니다.** REST pull/push + localStorage 입니다.
실시간 WS 는 메인 그리드(`websocket.js`)에만 있습니다.
🔴 **좌표 변환은 클라 단일 구현입니다.** 저장 좌표는 «오리진 기준 칸수»이고 피치와 무관합니다 —
칸수 × 피치로 mm 를 만들어 없는 결함을 세우지 마십시오.
실패 상태는 **명명된 것들**입니다(`meta_unavailable` · `binding_unavailable` · `align_unavailable` · `no_data`).

상세: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) · [map_editor/](../map_editor/README.md)

### 5.1 전사 계획 사이드바 (`transfer_plan.js`)

**「계획 = 지금 열어 편집 중인 그 맵」** — `bonding_map` 을 열면 본딩 계획, `dt_map` 이면 DT 계획입니다.

| 영역 | 내용 |
|---|---|
| 배선 | `map_editor.js` 가 `initTransferPlan(paintController)` 로 초기화하고 통지만 보냅니다 (단방향) |
| 관리 단위 | **DOE = value** — 맵에 칠한 값 하나 = `map_split_registry` 행 하나 = 조건군 하나 |
| ⭐ 쓰기 소유권 | **`transfer_plan.js` 는 서버에 쓰지 않습니다.** 레지스트리 행의 유일한 기록자는 `map_editor.js` 입니다 |
| 파생값 | **저장하지 않습니다.** 구역 소요 = 칠한 셀 수 × 층 수, 자재당 = `ceil(소요 / 자재 수)` |
| replace 권한 불변식 | `legendReplaceScope` = `{table, mapKey, fingerprint}` — 「이 화면은 이 맵의 행에서 왔고 읽었을 때 이랬다」 |
| 이동 | `openMaterial(id)` — 맵 간 이동의 «유일» 허브 (브레드크럼 + 뒤로가기 프레임 스택) |

### 5.2 Map Editor 2 (`src/map2/*`) — 정렬 화면, 레거시 «옆에» 섭니다

**왜 별개 페이지인가:** 레거시 에디터는 매일 운영 데이터 위에서 돌고 있습니다.
새 화면이 그 위에서 실험하면 사고가 그쪽으로 갑니다.

층 경계가 이 디렉터리의 존재 이유입니다 — 순수 층은 **인자로 받고 값을 돌려주며 모듈 상태를 갖지 않습니다.**
그래서 `view_model` 이 DOM 없이 node 로 채점됩니다.

```
신원 · 선언(declaration) · 좌석(seating — 등록만 하고 그리지 않는다) · 채점(candidates)
· 판정(verdict) · 그리기(painter) · 세션(session) · 입출력(excel_io)
```

- 🔴 **웨이퍼 테두리·마스크는 이 캔버스에 그려지지 않습니다.** 옛 점선 원은 하드코딩된 장식이었습니다
- 🔴 **확정은 «한 동작»입니다** — 무장 단계도 두 번째 확인창도 없습니다
- 🔴 **확정 버튼의 유일한 관문은 「무언가 골랐는가」입니다** — 막는 것이 일이 아닙니다
- 🔴 **후보의 두 번째 축은 「앞면/뒷면」이 아니라 「좌상단/우상단 시작」입니다.**
  걸음 축은 거울 반쪽의 **대체**이지 추가가 아니라서, **후보가 16 이 나오면 그것이 결함입니다**
  (레거시 `_back` 철자는 계속 읽히고 「뒷면」으로 그려집니다 — `parseCandidateId` → `spellFrame`)
- 🔴 **확정 키는 화면이 조립하지 않고 «룰의 선언»을 읽습니다** — `decisionKeyOf(declaration, decision)`.
  확정 문구의 주어도 슬롯 «하나»입니다. arity 를 아는 분기가 없습니다
- 🔴 **룰 채택 실패는 침묵 대신 «사유»를 말합니다** — `selectAlignmentRules`
- **룰을 고르면 테이블·바인딩·목록이 따라옵니다.** 거절은 이 화면이 좁히는 것이 아니라
  «서빙받는 사실»입니다 — 테이블 레코드의 `selectable`/`reason` 은 서버의 것입니다
- **워크리스트는 테이블마다 묻습니다** — `map_table` 이 라우트의 «필수» 파라미터입니다

서버 절반: `server/map_alignment.py`(채점·판정) · `server/map_overlay.py`(기하) ·
`server/frame_confirmation.py`(확정 기록). 이음새는 `contracts/map2_seam/` 이 채점합니다.

---

## 6. 어드민 (`admin.js`) — 파이프라인 생애주기 탭

탭 축은 «메커니즘»이 아니라 **파이프라인 생애 단계**입니다. 실측 탭 여섯:

| 탭 | 내용 |
|---|---|
| **overview** (첫 화면) | 재교정률 · 교정 공수 · 설정 반영 + 헬스 카드 |
| **file** | 인제션 로그(필터·정렬·페이지) + Workspaces + 실패 진단 → 커스텀 파서 편집 딥링크 |
| **chain** | Rules 현황 + Outbox 실패 재시도 + Mappers + 실패 진단 → 맵퍼 편집 딥링크 |
| **autoupdate** | 스케줄러 상태와 실행 이력 |
| **enrichment** | 보정 규칙과 큐 |
| **ontology** | 선언 작성 — 초안 → 검토 → 활성화 (`ontology_explorer*.js`) |

`overview` 와 `ontology` 는 `FULL_BLEED_TABS` 라 헬스 스트립을 숨깁니다.
편집기는 Monaco(CDN)입니다.

---

## 7. 백엔드 계약

라우트·파라미터·응답 계약의 정본은 [backend §2](./backend.md) 입니다. 이 문서는 배선만 적습니다.

- `config.js` 가 주소를 «한 곳»에서 만듭니다 — dev 는 `127.0.0.1:8080`, 프로덕션 빌드는
  `window.location.origin`. WS 도 같은 host 기준이라 데스크톱 셸이 로드한 origin 이 전체로 전파됩니다
- WS 재접속은 «지수 백오프 + 하향 지터 + 연결 워치독»입니다. 상수는 전부 `config.js` 에 있고
  각각 왜 그 값인지가 그 옆에 적혀 있습니다 — `onclose` 가 «안 오는» 행 hang 이 실재했기 때문입니다
- 🔴 **한 경계에 응답 모양이 둘이면 조용히 실패합니다.** body 를 그냥 주는 함수와 `{ok, body}` 로
  감싸는 함수가 섞이면 오류 없이 «빈 값»이 되고 컨트롤이 안 나타납니다

---

## 8. 화면이 「없다」를 말하는 법

🔴 **「없음」은 한 가지가 아닙니다.** 섞어 쓰면 사용자가 «고장»과 «진행 중»과 «정상적으로 비었음»을
구분할 수 없습니다.

```
안 골랐다  ·  그런 종류가 없다  ·  서버가 답할 수 없다  ·  걸었는데 비었다  ·  «잘렸다»
```

마지막이 특히 그렇습니다 — `node_limit` 에 걸린 «잘림»을 «부재»로 읽으면 없는 결론이 섭니다.

UI 문구 규율: **기호·짧은 영어·명사형.** 번역체 문장은 쓰지 않고, 전체 문장은 «확정 한 곳»에만 씁니다.

---

## 관련 문서

- [backend](./backend.md) — 라우트·응답 계약
- [LEDGER_GUIDE](../guide/LEDGER_GUIDE.md) — 원장 소스 붙이기·운영
- [PRIMER](../guide/ledger/PRIMER.md) — 한 행이 원자가 되기까지
- [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) — SSOT
