# SYSTEM_FLOWS — 클라 담당 세 흐름 실측 (②·④·⑨)

> **입력:** `docs/architecture/SYSTEM_FLOWS.md` §1 칸 정의 · §3 채우는 규칙 그대로.
> **측정 리비전:** **워킹트리**. ⚠️ 측정 «중»에 HEAD 가 `72f5b752` → `d0400f9a` 로 움직였고, 세션 시작 스냅샷이 말한 미커밋 수정 넷(`dt_map_derivation`·`map_alignment`·`map_overlay`·`ledger_config.json.sample`)은 **지금 없다**(`git diff --stat` 공백). 이 문서의 모든 수치는 **움직인 뒤 다시 재서** 확인했다 — 재확인한 것: 라우터 3라우트·낡은 docstring·`createWalkBoxWalk` 구조분해 셋·`rb-walkbox` CSS 0·`truncationReason` 소비자 0·`collect(` 호출부 0·`edge_limit` 0. 「미커밋 diff 에만 있는 이음매」는 **0건**이다.
> **읽은 문서 먼저:** `CODE_MAP.md` §7 · §7-B(4432~4496) · §5-H · `frontend.md` §3~§5.
> **범례:** ✅ 이어짐 / ⚠️ 반쪽 / 🔴 끊김 / ⚰️ 죽은 갈래

---

## ② 원장 → 화면 (원자 → walk → 클라 모델 → 좌석/부품)

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `ledger_events` 테이블 | `ledger_api/ledger_subgraph.py::SqlEvidenceLookup.claims_for_entities` (~205) | `subgraph()` 의 홉 루프가 프론티어마다 호출 | SQL (psycopg, `jsonb_to_recordset` 프론티어) | `frontier`(=`[{type,keys}]` JSONB) · `fetch`=limit+1 · **`follow` 가 있으면 `e.predicate = ANY(%(follow)s)` 로 WHERE 절에 들어간다**(~236). direction 이 `outgoing`/`incoming`/`both` 에 따라 UNION 팔 1~2개 | 1 — `ledger_subgraph.subgraph()` (~774) | 🔊 **시끄럽다.** 관계 부재는 `_relation_absent()` → **503 + `{reason:"ledger_relation_absent", state:"absent", relation, message:"원장 테이블 … 마이그레이션 미실행"}`. 컬럼/인덱스 넷 중 하나라도 없으면 `_subgraph_contract_state` → **503 + `missing:[…]` + 실행할 명령 문자열** | ✅ |
| `ledger_trace_router.py::evidence_subgraph` (`GET /api/ledger/subgraph`, 84) | `ledger_subgraph.subgraph()` (774) | 브라우저 HTTP GET | 함수 인자 | 받는 쿼리 **아홉**: `id`(필수) · `hops`(기본 **12**, 1–40) · `direction`(기본 **both**) · `node_limit`(기본 **400**) · `edge_limit`(기본 **1200**) · `positive[]` · `negative[]` · `follow[]` · `backbone_hops`. `follow` 는 `_split_follow` 로 `이름:키` 를 갈라 `follow_keys` 로 따로 나른다 | 1 | 🔊 선언에 없는 술어는 **422 `{reason:"predicate_not_declared", unknown:[…], declared:[…]}`** — 빈 그래프로 답하지 않는다. 씨앗이 못 지니는 키는 **422 `subgraph_request_invalid`** | ✅ |
| `ledger_subgraph.subgraph()` | HTTP 응답 | 같은 요청 | JSON 바디 | 최상위 키 **열셋**: `schema_version:3` · `state` · `generated_at` · `seed` · `nodes[]` · `edges[]` · `seeds[]` · `propagation` · `walk{mode,direction,start{positive,negative},hops_requested,hops_reached,claims_scanned,actions_scanned,enrich_actions,raw_claims,resolver_applied}` · `limits{nodes,edges,claims,actions,max_hops}` · `truncated{depth,nodes,edges,claims,actions,reason}` · `message` (1217) | 2 클라 경로 — `api.js::subgraphModel`(499) · `api.js::createWalkBoxWalk`(1712) | 🔊 `state:"empty"` + `message` 문장. 예산 절단은 `truncated` 로 «별도» 표기 | ✅ |
| `rnd_board/main.js` 좌석 선언(`BOARD`) | `rnd_board/main.js::bindLoaders` (~649) | 부팅 시 `boot()` 1회 | 함수 인자 | 좌석의 다섯 칸만 «질문»으로 올라간다(676–687): `follow` · `direction` · `hops` · `node_limit` · `backbone_hops`. 적힌 것만 실린다 — 빈 선언이면 `walkHere === walk` | 1 (`createWalk` 로 감싼 `walkHere`) | 🔇 **조용.** 좌석이 칸을 빠뜨리면 서버 기본값이 먹는다. 오류도 로그도 없다 | ✅ |
| `api.js::createWalk`(1516) / `COLLECTS`(1434) | `api.js::fetchSubgraph`(337) | 부품의 `this.walk(spec)` 또는 `bound.load()` | 함수 인자 | `{start, collect, ...rest}` 로 갈라 `collect` 가 없으면 `WALK`(=`fetchSubgraph`). 같은 key 는 `inflight` Map 으로 합류. **선언 안 된 `collect` 는 빈 답이 아니라 `Promise.reject`** | 7 좌석 경로 | 🔊 `walk: 선언되지 않은 collect — {name}` 로 reject → 부품이 `refused` 로 그린다 | ✅ |
| `api.js::fetchSubgraph` | `GET /api/ledger/subgraph` | 위와 같음 | HTTP 쿼리스트링 | 실제로 조립되는 것(340–398): `id` · `positive[]` · `negative[]` · `node_limit`(있을 때) · `hops`(있을 때) · `backbone_hops`(있을 때) · `follow[]` · `direction`(있을 때). **`edge_limit` 은 «한 글자도» 안 실린다** | 서버 1 | 🔊 씨앗 없음/스탬프 id 는 요청 «전»에 막고 `{ok:false, reason:'no_seed_chosen'\|'seed_is_not_a_server_node'}` 로 되돌린다 | ✅ |
| 응답 `truncated.edges` | 어떤 클라 코드도 | — | — | 🔴 **`edge_limit` 은 `client2/src/` 전량 grep «0 히트»다.** 서버 기본 1200 이 언제나 적용된다. api.js:369–372 주석이 「이 경계가 둘(nodes·hops)을 «떨어뜨렸다» — 부품이 절단을 «부를 수는» 있는데 «더 달라고 할 수는» 없었다」고 그 결함을 적고 고쳤는데, **`edge_limit` 은 그 수리에서 빠졌다** | 0 (요청 쪽) · 배너는 `truncated.edges` 를 «이름으로» 찍는다 | 🔇 **조용한 반쪽.** 배너가 「edges 에서 잘림」을 말하지만 운영자가 올릴 손잡이가 없다 | ⚠️ |
| 응답 `truncated{}` | `api.js::truncationNames`(494) → `subgraphModel.truncated` | 응답 도착 | 함수 반환 | `Object.keys(raw).filter(k => raw[k] === true)` → 배열. **`null` 이면 `null` 을 돌려준다** (「안 왔다」 ≠ 「안 잘렸다」) | **7** — 부품 배너 2(`candidate_list_panel.js:127` · `rank_list_panel.js:121`) + api.js 재해석 5(`mapModel:1045` · `compositionFromWalk:1126` · `waferFactsFromWalk:1165` · `peerCountFromWalk:1208` · `trendFromWalk:1330`) | 🔊 `{names} 에서 잘림 — 더 있을 수 있습니다` (후보·순위표) · `이 걷기는 예산에서 끊겼습니다` (트렌드 `state:'truncated'`) | ✅ |
| `subgraphModel.truncationReason`(580) | — | — | 모델 필드 | `body.truncated.reason` 을 그대로 올린다 | **0** — 전량 grep 결과 정의 줄 «하나»뿐(`client2/src/`·`client2/tests/`) | 🔇 **조용.** 만들어 놓고 아무도 안 읽는다. 서버가 이 문자열을 바꿔도 화면이 아무 말도 안 한다 | ⚠️ |
| `walk_box_panel.js::run()`(211) | `api.js::createWalkBoxWalk`(1712) | 「걷기」 버튼 클릭 | 함수 인자 | 부품이 **네 칸**을 실어 보낸다: `{type, keys, follow?, hops?}` — `spec.hops = this.hops`(230) 는 «명시적으로» 세워지고, 소스 주석이 「hops 는 고른 경로가 «요구하는» 값」이라 그 이유까지 적는다 | 1 | — | 🔴 (다음 행) |
| `createWalkBoxWalk` 내부 | `GET /api/ledger/subgraph` | 같은 클릭 | HTTP 쿼리스트링 | 🔴 **구조분해가 «셋»이다: `const { type, keys, follow } = spec` (1716).** 조립되는 쿼리는 `id=entitySeedId(type,keys)` + `follow[]` **둘뿐**(1717–1720). **`hops` 가 여기서 «증발한다».** 화면은 `경로 A · 3홉 · wafer → …` 라고 «찍고»(`walk_box_panel.js:366`), `useRoute()`(387)가 `this.hops = route.hops` 로 «세우고», `run()` 이 «싣는데», 경계가 «버린다** → 서버가 자기 기본 `hops=12` 로 답한다. `direction`·`node_limit`·`edge_limit`·`backbone_hops`·`positive`/`negative` 도 마찬가지로 안 실린다(부품이 계산조차 안 함) | 서버 1 | 🔴 **완전히 조용.** 200 이 오고 결과가 «더 많이» 나온다. 3홉을 물었다고 화면이 말하는데 12홉 답을 그린다. 오류·로그·배너 «0» | 🔴 |
| `/api/ledger/subgraph` 응답 | `createWalkBoxWalk` 반환 | 응답 도착 | 함수 반환 | 🔴 **응답 열셋 중 «둘»만 살아남는다**: `nodes` 를 `{id, type, label}` 로 «세 칸으로 깎아» 담고 `truncated` 를 원본 객체 그대로 담는다(1732–1734). **`edges` 가 버려진다** — 걷기 검색창은 「무엇이 나왔나」는 보여 주고 「어떻게 이어졌나」는 «구조적으로» 못 보여 준다. `seed`·`seeds`·`walk`(hops_reached 포함)·`limits`·`propagation`·`state`·`message` 도 버려진다 | 1 (`walk_box_panel.this.result`) | 🔇 **조용.** 「몇 홉까지 실제로 갔나」(`walk.hops_reached`)가 응답에 «있는데» 화면이 못 받아, 위 행의 hops 유실을 화면에서 검출할 방법도 같이 사라진다 | 🔴 |
| `GET /api/ledger/declaration`(400) | `api.js::fetchDeclaration`(1687) | `WalkBoxPanel.mount()` → `loadDecl()`(159) · `ControlBarPanel` | HTTP GET(무인자) | 서버가 내는 것: `state` · `entities[{type,keys}]` · `predicates[{name,subjects,object,origin}]` · `sources[{source,relation,emits,scope_columns}]`. 클라가 읽는 것: `entities` · `predicates` · **`collect`(1698) — 서버가 «안 보내는» 키**. `sources` 는 이 경로에서 «안 읽는다**(그리드 쪽 `grid_source_label.js` 가 따로 읽는다) | 3 — `rnd_board/main.js:701`(walkBox) · `:706`(controlBar) · `walk/main.js:36` | 🔊 `{ok:false, message}` 한 모양 → 「서버가 아직 선언을 못 줍니다 — 걷기 상자는 그 답 위에 섭니다」(walk_box_panel:352). 실패는 «캐시 안 한다** | ⚠️ `collect` 는 서버에 없는 키를 읽는 잔재 — 언제나 `[]` |
| `fetchDeclaration` 결과 | `api.js::typeGraph`(1586) → `pathsBetween`(1611) → `useRoute`(387) | 도착지 드롭다운 `change` | 함수 인자 | 원장을 «한 줄도» 안 읽는다 — 선언의 `predicates[].subjects × object.types` 로 무방향 그래프를 만들고 단순경로를 «follow 집합»으로 접는다. `useRoute` 가 `this.follow = new Set(route.follow)` · `this.hops = route.hops` 를 «둘 다» 세운다 | 1 | 🔊 이어지지 않으면 「{A} 과 {B} 은 «선언상» 안 이어집니다」(351) — 「없다」와 「못 봤다」를 가른다 | ⚠️ **`follow` 만 전선을 건넌다.** 같은 함수가 낳은 `hops` 는 위 행에서 버려진다 — 「그 함수가 있나」로는 통과하고 「무엇이 지나가나」로는 반쪽 |
| `walk_box_panel::_resultBox` 행 클릭(526) | `MarkingStore`(`marking:2`) → 좌석 재걷기 | 사람 클릭 | 함수 호출 → 구독 emit | `this.mark(id, SIGN.CASE, 'replace')` → `Panel.mark`(panel.js:139)가 `markings.clear(writes)` 후 `set(...)`. 그 emit 을 `walk_box_panel.mount()`(144)의 구독이 받아 `push(outside)` 로 이력 칸을 «자식으로» 붙인다. `marking:2` 를 읽는 좌석(후보·순위·트렌드2·맵2)이 각자 `startFor()` 로 다시 걷는다 | 4 좌석(`reads:'marking:2'`) + 이력 구독 1 | 🔇 조용(정상 경로) | ✅ |
| `walk_box_panel.js::collect(nodeId, sign)`(120) | — | — | — | 저장소 전량 grep: **호출부 0** (`client2/src/`·`client2/tests/` 에서 `collect(` 히트는 «정의 줄 하나»뿐). 찍기-재걷기 고리는 위 행의 `mark()` 가 «다른 철자»로 담당한다 | **0** | — | ⚰️ 죽은 메서드 |
| `WalkBoxPanel` 이 그리는 CSS 클래스 | `rnd_board/board.css` | 렌더 | 클래스명 | 🔴 **부품이 `rb-walkbox*` 클래스 «15개»를 찍는데**(`rb-walkbox` · `-history` · `-history-head` · `-step` · `-select` · `-route` · `-note` · `-field` · `-label` · `-key` · `-follow` · `-run` · `-go` · `-result` · `rb-part-title`) **`board.css` 의 `rb-walkbox` 규칙은 «0»이다**(`grep -c` = 0). 저장소 전량에서 그 문자열을 든 파일은 `walk_box_panel.js` «하나». `dist/assets/*.css` 에도 «없다**(빌드본 확인) — 반면 `rb-part-title` 은 board.css:289 에 있다 | **0** | 🔇 **완전히 조용.** 브라우저 기본 스타일로 그려진다. `walk.html` 의 주석이 「부품의 스타일은 `board.css` 에 삽니다 — 사본을 만들면 두 화면이 달라집니다」라고 «단언하는데 그 문장이 거짓»이다. 휴대폰 타깃인데 스타일 없는 `<button>`/`<select>` 는 44px 터치 타깃에 못 미친다 | 🔴 |
| `walk.html` → `src/walk/main.js::boot` | `WalkBoxPanel` | 페이지 로드 | 생성자 인자 | `reads:'marking:1'` · `writes:'marking:1'` · `loadDeclaration` · `walk: createWalkBoxWalk(...)`. vite 엔트리 `walk` 존재, **`dist/walk.html` 빌드본도 존재** | 1 | 🔊 `#wk-host` 없으면 부팅 안 함(무해) | ⚠️ 위 CSS 행 때문에 «페이지는 서는데 모양이 없다» |
| R&D 보드 walkBox 좌석(`main.js:635`) | `WalkBoxPanel` | 부팅 | 좌석 선언 | `reads: null` · `writes:'marking:2'`. 🔴 그래서 `TablePart` 에 넘어가는 `reads`(516) 도 `null` → `Panel.signOf()` 가 «언제나 ABSENT» → **결과 표가 「어느 행이 마킹됐는지」를 보드에서는 못 그린다**. `walk.html` 은 `reads === writes` 라 그려진다 — 같은 부품, 두 화면, 다른 동작 | 1 | 🔇 조용 | ⚠️ |
| R&D 보드 walkBox 좌석 제목 | 화면 | 렌더 | 문자열 | 좌석 제목이 `'걷기 -- 타입 · 키 · 따라갈 술어 · **모을 것**'`(main.js:637). 부품이 그리는 줄은 `_typeRow`·`_keyRow`·`_destinationRow`·`_followRow`·`_runRow` 다섯 — **COLLECT 칸은 «없다»**. `frontend.md` §4 가 「COLLECT 는 2026-08-28 에 라우트에서 빠졌다 — 화면에 그 칸이 남아 있으면 결함이다」라고 적어 뒀는데, 칸은 갔고 «제목만» 남았다 | — | 🔇 조용 | ⚠️ |
| `COLLECTS.trend_y` → `fetchTrends` → `GET /api/ledger/trends` | 서버 | — | — | 🔴 **그 라우트가 없다.** `ledger_trace_router.py` 의 `@router` 는 «셋»뿐: `/subgraph`(84) · `/gaps`(353) · `/declaration`(400). 그리고 `collect:'trend_y'` 를 대는 좌석이 **0** — `main.js:218` 이 그 줄이 떠난 자리를 적고 있고, `main_trend_panel.js:85` 는 폴백을 `options.collect \|\| null` 로 «닫아 놨다** | **0** | 🔇 조용 | ⚰️ |
| `COLLECTS.map` → `fetchLotMap` · `COLLECTS.basis` → `fetchComposition` · `COLLECTS.peer` → `fetchSiblings` · `COLLECTS.wafer_process` → `fetchComposition` | 서버 | — | — | 넷 다 없는 라우트(`/lot_map`·`/composition`·`/siblings`). 도달성 실측: **`collect:'map'` 은 `if (!options.question)` 의 «else» 안에만 있고(main.js:872·877·881) — `question:` 을 선언하는 좌석이 «0»이다**(rnd_board 전량 grep, 주석 제외 0 히트) · **`decl.part==='map' && decl.collect`(811) 도 map 좌석 셋 중 `collect` 를 대는 것이 0** · **`collect:'basis'`(805) 는 `options.basisChipId` 가드 아래인데 그 옵션을 대는 좌석이 0** · `wafer_process` 는 세 부품의 «생성자 기본값»으로만 살아 있고 좌석이 `follow` 를 대는 한 `bound.load` 가 먼저 이긴다 · `peer` 는 호출부 0 | **0** (넷 다) | 🔇 조용 — grep 에는 «살아 보인다**. `slotPagesFromLotMap` 은 grep 히트 2라 살아 보이지만 그 한 호출이 죽은 갈래(881) 안이다 | ⚰️ |
| `api.js::fetchMapGrid` → `GET /tables/wafer_map_metadata/data` | `main.py:1793 @app.get("/tables/{table_name}/data")` | `map_panel` 의 `loadGrid` | HTTP 쿼리 | 원장 라우트가 «아니다** — 선언된 관계의 범용 리더. 라우트 실재 확인 | 1 (`map_panel.js:231` → `mapModel`) | 🔊 표준 표 라우트의 거절 | ✅ |

### ② 에서 나온 문서 정정 (상태 칸에 못 담은 것)

| 문서/주석 | 적힌 것 | 실측 |
|---|---|---|
| `server/ledger_trace_router.py` **모듈 docstring 1~5행** | 「The ledger read routes — **ten of them** … `subgraph`, `subgraph/table`, `siblings`, `trends`, `composition`, `selection/resolve`, `kinds`, `declaration`, `structure`, `lot_map`」 | 🔴 **`@router` 는 셋뿐**(84·353·400). 열 중 «일곱»이 없는 이름이다. CODE_MAP §5-H 는 「라우트는 «셋»이다」로 맞게 적혀 있다 — **틀린 것은 소스 주석 쪽**이고, 이 파일을 여는 사람이 제일 먼저 읽는 줄이다 |
| `CODE_MAP.md` §7-B `api.js` 표 마지막 행 | 「`main.js` 의 죽은 import — **다섯**(`fetchLotMap`·`fetchComposition`·`fetchTrends`·`fetchSiblings`·`fetchSubgraph`)」 | 🔴 **열이다.** import 문 외 히트 0인 것 실측: 위 다섯 + `trendsModel` · `subgraphModel` · `basisCountsFromComposition` · `peerCountFromSiblings` · `waferFactsFromLotMap`. 모델 변환기 다섯이 목록에서 빠져 있었다 |
| `CODE_MAP.md` §7-B 머리 | 「`api.js` **1,567줄**」(⑬) / 「1,733줄」(⑭ 정정) | `api.js` **1,739줄**(워킹트리). `walk_box_panel.js` 는 §7-B 가 **544**, `frontend.md` §4 표가 **352** 로 «서로 다르고» 실측은 **544** — frontend.md 쪽이 낡았다. `main.js` 는 §7-B 812 / frontend.md 686 / 실측 **921** — 둘 다 낡았다 |
| `walk_box_panel.js` 클래스 주석(70행) | 「쓰는 곳은 `goto` «하나»입니다. **다른 어떤 경로도 저장소에 안 씁니다**」 | ⚠️ 거짓. `_resultBox` 의 `onRowClick`(526)이 `Panel.mark()` 를 부르고 그것이 `markings.clear/set` 으로 «직접 쓴다**. 기제 자체는 성립한다(그 쓰기의 emit 을 구독이 받아 `push`→`goto` 로 되돌아온다) — 틀린 것은 «주장»이지 동작이 아니다. 다만 이 주석을 근거로 「저장소 쓰기는 한 줄」이라 진단하면 틀린다 |
| `frontend.md` §4 `api.js` 행 | 「`COLLECTS` … 일곱 중 다섯이 은퇴한 라우트를 부르는 fetch 함수로 간다」 | ✅ 참이고, **더 정확히는 그 다섯 중 «넷»이 오늘 호출부 0 이라 요청 자체가 안 나간다.** 「404 하나가 남는다」(main.js:218 주석)는 «이제 거짓»이다 — `trend_y` 도 호출부 0 이다 |

### ② 좌석 인구조사 — 「라우트가 여럿일 이유가 없다」는 **실제로 지켜지고 있다**

```
좌석 16   그중 걷기에 닿는 것 «13»  ->  전부 «같은 라우트» GET /api/ledger/subgraph
          표시 전용 «3»          markingStatus · declaration ×2 (질의를 안 낸다)
          부품 종류 «11»          같은 부품이 좌석 둘·셋으로 서는 것이 map(3)·mainTrend(2)·declaration(2)
```
✅ 늘어난 것이 «선언»이지 갈래가 아니다 — 부품 13이 한 라우트를 나눠 쓴다.
🔴 예외가 «하나**: `walkBox` 만 `createWalkBoxWalk` 라는 «두 번째 경계 함수**를 통과하고, 그 함수가 위 표의 두 🔴 를 낳는다.
   같은 라우트인데 «경계가 둘»이라, 한쪽에서 고친 것이 다른 쪽에 안 온다 — `hops` 가 정확히 그 자리다
   (좌석 `map`(main.js:481)은 `hops: 8` 을 «전선까지 보낸다**. 같은 파일, 같은 라우트, 다른 결과).

### ② 절단(truncation) 배선 — 「끝까지 이어졌나」 판정: **이어졌다. 다만 «한 경계에 모양이 셋»이다**

```
서버       truncated {depth, nodes, edges, claims, actions, reason}      한 모양
클라 ①     subgraphModel.truncated    = 배열  (truncationNames)          후보·순위·트렌드 → 배너
클라 ②     reachModel.cut             = 배열  («cut» 이라는 다른 이름)    reach_panel:165 「잘림 …」
클라 ③     createWalkBoxWalk.truncated = 원본 객체 (`.reason` 을 읽는다)   walk_box_panel:505
```
✅ **화면에 절단을 «말하는» 부품은 다섯**(candidate_list · rank_list · main_trend · reach · walk_box) — 지시서의 「다섯 소비자」는 **참**이다.
⚠️ 다만 셋이 «다른 모양»이라, 서버가 `truncated` 의 모양을 바꾸면 **셋 중 하나만 조용히 죽는다**.
   `reachModel` 이 `depth` 를 «일부러» 뺀 것은 옳다(hops=1 이 질문 자체) — 그건 이름이 다른 «이유»이지 우연이 아니다.
   그래도 세 철자가 한 경계에 서 있다는 사실은 남는다.

### ② 의 «왜 안 잡혔나» — 채점기가 그 이음매를 안 본다

```
rnd_board_walk_box_harness.mjs (464줄)   `hops` 히트 «0»
rnd_board_walk_harness.mjs     (329줄)   `hops` 히트 2 — 둘 다 픽스처 행(`evidence[].hops`)이고 쿼리 단언이 아니다
```
🔴 **부품이 `spec.hops` 를 세우는 것도, 경계가 그것을 버리는 것도 «아무도 안 잰다».** 하니스가 재는 것은
씨앗 id 의 base64url(S3 절)이지 쿼리 «전체»가 아니다. 그래서 이 결함은 「코드가 있나」로도, 「하니스가 초록인가」로도
안 보이고 **「무엇이 전선을 건너나」로만** 보인다 — 이 문서가 그 질문지인 이유 그대로다.

### ② 에서 목록이 놓친 흐름

- **선언 → 화면의 «어휘»** (`GET /api/ledger/declaration`). ②는 「원자 → 화면」인데 이 라우트는 **원장을 한 줄도 안 읽는다.** 드롭다운·타입그래프·경로 목록·그리드의 원장 라벨이 전부 여기서 나오고, 끊기면 걷기 화면 «전체»가 안 선다. ②와 ④ 사이의 «셋째» 흐름으로 세는 편이 맞다.
- **`/api/ledger/gaps`**(353) — 「선언이 있어야 한다고 말한 자리 중 원장이 비어 있는 곳」. 인자 없으면 선언만(즉시), `name=` 이면 그 하나를 «센다»(~1초). 클라 소비자 **2**: `client2/src/admin.js:2115` · `client2/src/gap_catalogue.js`. R&D 보드 쪽 소비자는 «0** — 「무엇이 비어 있나」는 어드민에만 있고 걷는 화면엔 없다.
- **선언 라우트의 «두 청중»** — `GET /api/ledger/declaration` 을 부르는 자리가 클라에 **둘**이고 서로를 모른다: `client2/src/main.js:178`(그리드의 원장 소스 라벨 — `sources[]` 를 읽는다) · `rnd_board/api.js:1691`(걷기 — `entities`/`predicates` 를 읽는다). **`sources` 와 `entities` 는 «다른 반쪽»이라 한쪽이 비어도 다른 쪽은 정상으로 보인다** — 서버가 `sources` 키를 «빼서» 답하는 갈래(setup 이 컴파일 안 될 때)가 실제로 있고, 그러면 걷기는 멀쩡한데 그리드 라벨만 「못 읽음」이 된다.
- **마킹 체인 자체**(마킹1 → walk → 찍기 → 마킹2 → walk). 부품 간 이음매가 아니라 «저장소 하나»를 통과하는데, 열 흐름 목록에는 그 축이 없다. `marking_intersection.js::intersectMarkings` 는 `boot()`(main.js:908)에서 좌석 «뒤에» 설치된다.

---

## ④ 작성(선언) — 폼 → 스켈레톤 → 검증 → 저장 → 발효

> 표면: `/admin/ontology-explorer/*` **라우트 15**(비-strict 6 · strict 9) · 클라 `ontology_explorer{,_store,_view}.js` + `ontology_skeleton.js` · `closed_list.js` · `uniqueness.js`.

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `admin.js::switchTab`(580) | `ontology_explorer.js::refreshOntologyExplorer` | 운영자가 어드민 「온톨로지」 탭 클릭 | 함수 호출(무인자) | `controller?.refresh()` → `load({allowContextSwitch:true, editorCheckpoint: state.dirty ? checkpoint() : null})`. `initOntologyExplorer`(admin.js:368)는 컨트롤러만 만들고 **적재하지 않는다** | 1 (`ontology_explorer.js:1350`) | 🔇 `controller` 가 null 이면 `?.` 가 삼킨다 — 빈 `#ontology-explorer-root`(admin.html:2148) | ✅ |
| `ontology_explorer.js::load` | `GET /admin/ontology-explorer/view` | 위 refresh · 모든 성공한 쓰기 뒤 `readMirror` | HTTP 쿼리 | `new URLSearchParams({q, page, limit:'100', view_mode})` + 조건부 `selection`·`context_token`·`draft_id`·`revision`. `mode = draft?.draft_id ? viewMode : 'active'` — 초안 없이 `draft_preview` 가 못 나가게 한 곳에서 접는다. ⚠️ 라우터가 받는 **`reference_limit` 을 클라가 한 번도 안 싣는다**(항상 서버 기본 200) | 1 (`:704`) | 🔊 throw → `REQUEST_FAILED` + 패널의 `errorSentence(error)`(토스트 아님) | ⚠️ |
| `config_explorer_service.view` | `ontology_explorer_store.js::reduceExplorerState` | `/view` 200 | HTTP JSON | 응답 12키: `items`·`nodes`·`outbound`·`used_by`·`integrity`·`changes`·`edge_changes`·`selection`·`view_context`·`draft`·`total`·`verification`. `verification` 은 `test_runs.json` 을 `definition_hash` 로 대조해 만든 `{target_key,status,ran_at,rows_read,molecules,atoms,stale}` | 2 (`store.js:178` 저장 · `view.js:742` `verificationOf`) | 🔇 키가 없으면 `p.verification \|\| {}` → 배지가 「모름」 | ✅ |
| `ontology_explorer.js::loadAuthoring` | `GET /authoring/plan?selection=` | `load` 성공 직후 `void loadAuthoring(...)` (await 안 함) | HTTP 쿼리 | `params.set('selection', selection)` 하나. 인자는 `payload.draft?.target_key ?? payload.selection?.key ?? selection ?? null` — 🔴 초안이 선택보다 이긴다 | 1 (`:768`) | 🔊 `console.warn('[ontology] authoring plan unavailable')` + `AUTHORING_FAILED` → 패널이 사유를 그린다(비우지 않는다) | ✅ |
| `config_authoring.authoring_plan` | `ontology_explorer_view.js` | 위 응답 | HTTP JSON | 반환 8키 + 서비스가 `config_source` 추가 | **6/9.** 읽힘: `steps`·`sections`·`fields`·`force_summary.grammar_requires_it`·`unattached_refusals`·`physical_schema_file`·`config_source`. 🔴 **`counts` 소비자 0**(view 가 `plan.steps` 로 재계산) · 🔴 **최상위 `refusals` 소비자 0**(행별 `row.refusals` 로 나뉘어 소비) | 🔇 조용 — 안 읽는 키라 부재가 안 보인다 | ⚠️ |
| `config_authoring.closed_lists(sources)` | `ontology_explorer_view.js` | `GET /authoring/schema` (세션 1회, `state.authoringSchema===null` 일 때만) | HTTP JSON | 🔴 **발행 키 «23»** = `setup_bundle.public_bundle_schema()` **8** + 본문 **15**. CODE_MAP 의 23 은 **맞다** | 🔴 **이름으로 읽히는 것 «11/23»** — 스켈레톤 `list:` 이름 9개가 `view.js:1822 context.schema[node.list]` 로 간접 소비 + 명시 2(`skeleton`·`authorable_kinds`). **나머지 12는 이름으로 읽는 곳 0**; 그중 7(`setup_version`·`config_file`·`physical_schema_file`·`column_universes`·`steps`·`implementations`·`tiers`)은 **어느 경로로도 도달 불가** | 🔇 조용 — 발행만 되고 화면에 안 뜬다 | ⚠️ |
| `closed_lists["tiers"]` (한국어 라벨) | 화면 | — | HTTP JSON | 서버가 `{"id":"TIER_STRUCTURAL","label":"구조적 제거"}` 꼴로 낸다 | **0** — `view.js:1203/1662/1777` 은 `row.tier` 의 **영문 id 원문**을 그대로 찍는다 | 🔇 조용 — 운영자가 `TIER_STRUCTURAL` 이라는 «배관 낱말»을 본다 | ⚰️ |
| `closed_lists["column_universes"]` | 화면 | — | HTTP JSON | `[{id, note}]` | **0** — `view.js:1271` 은 `row.universe`/`row.universe_note` 를 읽는다(`Field.to_mapping` 이 `_UNIVERSE_NOTE` 로 이미 실어 보냄, `config_authoring.py:278`). 같은 값의 두 번째 사본 | 🔇 조용 | ⚰️ |
| `closed_lists["implementations"]`(`options`·`counts`·`default`) | 화면 | — | HTTP JSON | 「기본값이 «무엇을 세어서» 나왔나」를 `counts` 로 같이 낸다 | **0** — 클라 전량 grep 히트는 무관한 주석 1건. 드롭다운은 문자열 목록인 `prepare_implementation`/`map_implementation` 만 쓴다 | 🔇 조용 — 「무엇을 세어서 나온 default 인가」가 화면에 없다 | ⚠️ |
| `config_authoring.skeleton()`(`lru_cache`) → `ledger_skeleton.json` | `ontology_skeleton.js` | `closed_lists` 가 `"skeleton": skeleton()` 으로 실어 보냄 | 파일 → HTTP JSON | **761줄** 실측. `hint` 분포: `free` 27 · **`choice` 9** · `ref` 6 · `flag` 4 · `number` 3. `list:` 이름도 정확히 **9** — `choice` 수와 일치 | 다수 (`shapeAt`/`declarationShape`/`emptyOf`; `view.js:295,446,2049` · `ontology_explorer.js:310,969`) | 🔊 안 오면 `shapeForPath` 가 null → **폼이 안 그려진다**. `closed_list.js` 의 `loaded` 판정이 「모름」과 「없음」을 가른다 | ✅ |
| 스켈레톤 `hint:"choice"` 잎 | `closed_list.js::closedListChoice` | 폼 렌더 | 함수 인자 | `closedListChoice(context.schema[node.list], text, {loaded, name: node.list})` — **이름 문자열로 인덱싱**. 클라가 목록 이름을 «하나도» 안 갖는다 | 2 (`view.js:1339` 플랜 행 `candidates` · `view.js:1822` 스켈레톤 잎). `oe-field-select` 잔존 **0** | 🔊 미도착 시 `loaded=false` → `LIST_UNREAD` 픽셀(「없음」과 다른 글자) | ✅ |
| `ontology_explorer.js::loadAuthoring` | `GET /columns?relation=` | 플랜에 `\.relation$` 로 끝나고 값이 문자열인 행이 있을 때, relation 당 1회 | HTTP 쿼리 | 🔴 **`/columns?relation=${enc(relation)}` 뿐이다.** 라우터가 받는 `combination: list[str]` 을 **클라가 한 번도 안 싣는다** → 서버의 `payload["combination"]` 이 UI 요청에서는 **항상 None** | 1 (`:800`) | 🔊 `COLUMNS_FAILED` → `stats.failed` 문장이 행 옆에 | ⚠️ |
| `column_stats` population | `ontology_explorer_view.js::renderUniqueness` | `/columns` 200 | HTTP JSON | 응답 6키: `relation`·`total_rows`·`columns`·`estimated_rows`·`ordering`·`combination` | 🔴 **1/6.** `view.js:1163` 의 `orderingVerdicts(stats?.ordering, …)` 뿐. 게다가 `renderUniqueness` 는 `row.ground.rule !== 'ordering_default_from_catalog_key'` 면 즉시 `null` — 그려지는 행이 사실상 하나 | 🔇 조용. 🔴 **라우터 docstring 이 「EXPENSIVE by design · the population counts are exact and cost one table scan」이라 선언한 그 전수 스캔의 결과가 화면에 한 자도 안 나온다** | ⚠️ |
| `column_stats.combination_uniqueness` | 화면 | 사람이 조합 지정 | — | 서버 경로는 살아 있다(`config_explorer_service.py:537`) | **0/0 — 양끝 다 없다.** 보내는 쪽 0 · 읽는 쪽 0(`stats.combination` grep 0). `uniqueness.js::uniquenessVerdict` 는 export 되지만 **외부 호출자 0** | 🔇 조용 | ⚰️ |
| 폼 입력(`edit-shape`·`edit-field`·`edit-shape-flag`·`add/remove-field-item`) | `state.editorText` | 운영자 타이핑/클릭/선택 | DOM 이벤트 → 문자열 | `JSON.parse(state.editorText)` → `setAtPath`/`deleteAtPath` → `dispatch({type:'EDITOR_CHANGED', text: JSON.stringify(next,null,2)})`. 🔴 **두 번째 저장소가 없다** — 모든 폼 조작이 저장 버튼이 보낼 «그 버퍼»를 고친다 | 1 (리듀서 `EDITOR_CHANGED`) | 🔇 `editorText` 가 falsy 면 writer 들이 조기 return — **버튼이 눌리는데 아무 일도 안 남는다** | ✅ |
| 「Save」(`view.js:672`) | `PUT /drafts/{id}` | 운영자 클릭 | HTTP 본문 | `{expected_revision: state.draft.revision, raw: state.editorText}` — 🔴 **`raw` 가 «문자열»**(서버가 `json.loads`). 폼이 계산한 값 중 `editorText` 에 안 들어간 것은 **한 개도 안 건넌다** | 1 (`:1175`, + 생성 경로 `:431`) | 🔊 `showToast(errorMessage(error),'error')` — 코드+경로+문장 | ✅ |
| `config_drafts.save`(`:426`) | `config_authoring.filled_declaration` | 위 PUT | 함수 인자 | 🔴 **저장 시점에 «유도된 값»을 문서에 실제로 앉힌다.** 규칙: `prefix = "bundle." + ".".join(steps) + "."`(끝의 점이 `user_test`/`user_test_2` 를 가른다) · `state=="derived"` 이고 `disposition!="shape"` 인 행만 · `value is None` 이면 건너뜀 · `_fill_leaf` 가 **빈 칸만 채우고 덮어쓰지 않는다**(`false`·`0` 은 답이라 안 덮음). 🔴 **채움이 프리뷰 «앞»에 있다** — 프리뷰가 채점하는 것이 파일이 들 것과 같아야 하므로 | 1 (`config_drafts.py:426`). 되읽는 쪽: `activate` 가 `record["raw"]` 를 **그대로** 파일에 쓴다(`:619`) | 🔊 안 채워지면 `missing_field` 거절문이 「채움」이라 그린 칸에 뜬다 (`validation_errors`) | ✅ |
| Save 두 번째 호출 | `POST /drafts/{id}/activate` | 같은 클릭(PUT 성공 직후, 같은 try) | HTTP 본문 | `{expected_revision: record.revision}` — 🔴 PUT 응답이 돌려준 **새 revision** 을 쓴다(`state.draft.revision` 아님) | 1 (`:1183`) | 🔊 실패해도 **PUT 은 이미 착지** — 초안은 저장됨, 파일은 안 바뀜 | ✅ |
| `config_drafts.activate` | `server/config/ontology/ledger_config.json` | 위 POST | 파일 쓰기 | `_activate_file(config_path, [(node.bundle_path, record["raw"])])` + 백업. 🔴 컴파일 실패가 쓰기를 막지 않는다 — `preview` 는 계산만 하고 판정하지 않는다 | 1 (`:619`) | ⚠️ 아래가 실패해도 **쓰기는 남는다**(주석 명시: 「THE WRITE STAYS, EVEN IF WHAT FOLLOWS FAILS」). 백업은 취하지만 자동 되돌림 아님 | ✅ |
| `config_drafts.activate` | `system_reload.reload_system_configs(db)` | 파일 쓰기 직후 | 콜백 | 🔴 **라우터가 실제로 배선한다**: `ontology_config_explorer_router.py:261` `reload_callback=lambda: system_reload.reload_system_configs(db)`(삭제 경로도 `:243`) → `ledger_authoring.skeleton.cache_clear()`·`ledger_trace.reset_walk_cache()`·`load_resolver_config(force_reload=True)`·`virtual_join_executor.reset_cache()`·`notation_norm.reset_cache()`·`models.refresh_dynamic_models(engine)`·`sys.modules` 의 `mappers.*` 제거 | 2 비시험 (`:243`·`:261`) | ⚠️ 던지면 `_refusal` 이 안 잡아 **FastAPI 500** → 클라 `요청 실패 (500)`. 파일은 이미 쓰였고 프로세스 캐시만 낡음 — **소리는 나지만 사유를 이름 대지 않는다** | ✅ |
| `system_reload` | outbox 행 + `NOTIFY outbox_event` | 위 | DB 행 + PG NOTIFY | `DatabaseOutbox(event_type="SYSTEM_RELOAD")` commit 후 `NOTIFY`. 🔴 **NOTIFY 는 bare `except:` 로 통째로 삼킨다** — 실패해도 폴러가 나중에 잡는다 | `chain_ingestion_worker.py:1698`(`SYSTEM_RELOAD` 를 `id desc` 로, 스로틀) · `run_watcher.py` 폴러. ⚠️ **원장 v2 소비자는 이 이벤트를 안 읽는다** | 🔇 NOTIFY 실패는 완전 조용(폴링이 커버) | ✅ |
| `activate` → `convergence_probe(actual_hash)` | `convergence_unproven`/`convergence_mismatch` 거절 | reload 직후 | 함수 반환 | 🔴 **운영 주입 «0».** 기본값이 `convergence_probe or (lambda expected: {"ontology-explorer-api": expected})`(`config_explorer_service.py:89`) — **자기가 받은 값을 그대로 돌려준다**. 라우터는 `OntologyExplorerService(config_root=DEFAULT_ONTOLOGY_ROOT)` 로만 만든다(`router:18`) → `consumer_hashes` 는 절대 안 비고 `mismatched` 는 절대 안 찬다 | 비시험 주입 **0** (`convergence_probe=` 를 넘기는 자리는 `server/tests/test_ontology_config_explorer.py:722,778` 둘뿐 — 규칙대로 «시험 전용»을 빼면 0) | 🔇 응답의 `runtime_convergence.status:"confirmed"` 가 **자기 입력을 «측정»으로 보고한다**. 두 거절문은 409 목록에 등재돼 있으나 운영에서 도달 불가 | ⚰️ |
| 「시험 실행」(`view.js:855`) | `POST /test-run` | 운영자 클릭 | HTTP 본문 | `{source_id: state.selection.canonical_id}` | 🔴 **호출자 1 — 있다.** `ontology_explorer.js:1120` 발신 · `view.js:855` 렌더. **CODE_MAP 이 의심하도록 지시한 「폼이 그리는데 읽는 쪽이 없다」 부류가 «아니다»** | 🔊 `TEST_RUN_FAILED` + `error.detail.code` 가 `oe-tree-why-code` 에 자기 칸으로 | ✅ |
| `test_run` 응답 | `state.testRun` | 위 | HTTP JSON | 15키 | **13/15.** 🔴 `ran_at` 소비자 0 · 🔴 `fetch_rows`(=`PREVIEW_FETCH_ROWS` 200) 소비자 0 — 「200행 중 몇」의 **분모가 화면에 없다** | 🔇 조용 | ⚠️ |
| `test_run status=="passed"` | `draft_store.root/test_runs.json` | 통과했을 때만 | 파일 쓰기 | `definition_hash` 를 키로 9키. 🔴 원장 아님 · `ledger_config.json` 안도 아님 — **선언 파일 옆의 두 번째 저장소** | 1 (`_test_runs()` → `_verification_view` → `/view.verification`) | 🔇 읽기 실패는 `except (OSError, ValueError): return {}` → 전부 `unverified` | ✅ |
| 삭제 (`deleteDeclaration`) | `GET /deletion-preview?targets=` → `DELETE /declarations/{key}` | 「삭제」 클릭 | HTTP 쿼리 ×2 | 🔴 **`context_token` 을 안 싣는다**(라우터가 받고 `stale_context` 로 거절할 수 있는 축인데 클라가 안 쓴다) | 🔴 **응답 14키 중 «1»** — `plan.unread_after` 만(`:499`). `released`·`blocked`·`retained`·`is_reset`·`sources_before/after`·`*_total` 등 13 소비자 0 | 🔴 **위험하게 조용.** `is_reset`(「소스가 하나도 안 남는다」)이 **안 읽혀서** 번들을 통째로 비우는 삭제가 `window.confirm` 에 「영향 없음」으로 뜰 수 있다 | ⚠️ |
| 컨트롤러 `review-draft`·`revise-draft`·`activate-draft`·`discard-draft` 분기 | `POST /drafts/{id}/review`·`/revise`·`/activate`, `DELETE /drafts/{id}` | (없음) | — | 네 분기가 `ontology_explorer.js:1212·1218·1227·1242` 에 살아 있다 | 🔴 **생산자 0.** 그 넷을 «만드는» 자리가 `client2/src/` 어디에도 없다(전량 grep: 소비 분기 4줄 + `client2/tests/dom_patch_harness.mjs:223` 시험 전용 1 — 규칙대로 빼면 **0**). `view.js` 의 `button(...)` 이 내는 액션은 `save-draft`(672)·`test-run`(855)·`create-draft`(870) 셋 | 🔇 조용 — 서버 라우트 넷이 서 있고 **누를 버튼이 없다**. `POST /review`·`/revise` 는 클라 호출자 0 | ⚰️ |

### ④ 에서 목록이 놓친 흐름

- **`GET /authoring/plan` 이 «두 번» 나간다.** `loadAuthoring` 이 `Promise.all` 로 필터된 플랜(`?selection=`)과 **필터 없는 전량 플랜**을 같이 부른다(`:768-773`). 뒤엣것은 「이 파일이 여기서 이미 무엇을 쓰나」 전용이고 `state.authoringAll` 에 한 번만 캐시된다. **라우트는 하나인데 질문이 둘**이라 라우트를 세면 안 보인다.
- **`filled_declaration` 은 «저장할 때 문서를 바꾸는» 유일한 자리**인데, 흐름도상 「검증」과 「저장」 사이가 아니라 **프리뷰보다 앞**에 있다(`config_drafts.py:426` → `:427`). 순서가 계약이다.
- **`test_runs.json` 이라는 두 번째 저장소.** ④의 산출물이 `ledger_config.json` «하나»가 아니다. `definition_hash` 로 걸려 있어 편집과 함께 죽는다(`stale`).
- **`system_reload` 가 스켈레톤 캐시를 비운다**(`skeleton.cache_clear()`). 즉 `ledger_skeleton.json` 을 고치면 «재기동 없이» **폼 자신의 모양**이 바뀐다 — 발효가 운영자 데이터뿐 아니라 폼에도 걸려 있다.
- **어드민 토큰이 두 갈래.** 라우트 15 중 읽기 6은 `require_admin_token`, 쓰기 9는 `require_admin_token_strict`. 클라는 `adminFetch` 하나로 둘 다 태우고 503(토큰 미설정)만 별도 토스트로 가른다(`admin.js:180`) — **strict 거부와 일반 거부를 화면이 구분하지 않는다**.

### ④ 양끝이 다 있는데 아무것도 잇지 않는 이음매 (일곱)

| # | 이음매 | 양끝 | 가운데 |
|---|---|---|---|
| 1 | `/columns` 의 `combination` 축 | 서버 인자·`combination_uniqueness` 구현·클라 판정기 `uniquenessVerdict` | 쿼리에 안 싣고 응답에서 안 읽는다. `uniquenessVerdict` **외부 호출자 0** |
| 2 | `/columns` 의 population 절반 | docstring 이 「THE NUMBERS ARE THE FEATURE」라 선언하고 전수 스캔 비용을 감수 | `columns`·`total_rows`·`estimated_rows` 를 읽는 클라 코드 **0** |
| 3 | `convergence_probe` | 검사 코드 · 거절문 둘 · 409 매핑 | 운영 주입 0 → **자기 입력을 되돌려받는다** |
| 4 | `closed_lists["tiers"]` 한국어 라벨 | 서버가 「구조적 제거」 등을 낸다 | 화면은 `row.tier` 의 영문 id 를 찍는다 |
| 5 | `POST /drafts/{id}/review` · `/revise` | 라우트 · 서비스 메서드 · 컨트롤러 분기 | **누를 버튼이 없다** |
| 6 | `deletion_preview` 의 `is_reset`·`blocked`·`released` | 계산되고 발행된다 | 클라가 `unread_after` 하나만 읽는다 |
| 7 | `/view` 의 `reference_limit` | 라우터가 쿼리로 받는다 | 클라가 안 싣는다(항상 기본 200) |

### ④ 에서 나온 문서 정정

| 문서 | 적힌 것 | 실측 |
|---|---|---|
| `CODE_MAP.md` §5-H-bis `ledger_skeleton.json` 항목의 **🆕⑮ [2026-08-30] 블록** | 「`references` … 작성 폼 그림(**여기, 신설**)」 | 🔴 **거짓이 됐다.** `git show HEAD:server/ledger/ledger_skeleton.json \| grep -c references` = **0**(`5a73021a` 에서는 1). `b143e162`(「the form stops offering `references`, and the grammar keeps accepting it」)가 그 노드를 들어냈다. 그 블록이 센 다섯 층 중 **넷이 0**이다. 🔴 같은 절의 «헤더»는 줄 수를 761로 갱신했는데(`328a5c20`) 이 문단은 안 따라와서 **한 절이 서로 모순되는 두 상태를 들고 있다.** 정정 문장: 「`references` 는 검증기 문법만 남았다(`setup_bundle._validate_references`). 폼은 `b143e162` 이후 «묻지 않는다» — 다섯 층 중 하나만 살아 있다」 |
| `CODE_MAP.md` §5-H-bis 클라 표 줄 수 넷 | `8d1e6c4c` 기준 | 드리프트(표가 기준을 밝히므로 «틀림»은 아님): `ontology_explorer.js` 1,323→**1,367** · `_store.js` 465→**485** · `_view.js` 2,277→**2,415** · `config_explorer_service.py` 989→**1,004** |
| `server/scripts/audit_authoring_form.py` `_skeleton_leaves` docstring | 「`ontology_explorer_view.js:1062`」(후보 목록) · 「`:975`」(한 멤버 접기) | ⚠️ **줄 번호가 죽었다** — 실제 그 줄은 `renderGround(row)` 와 `const list = h('span','oe-value')`. 규칙 자체는 `closed_list.js` 로 옮겨가 살아 있으니 **위치가 아니라 술어로 다시 적어야** 한다 |

### ④ 에서 CODE_MAP 이 맞았던 것

라우트 **15**·비-strict **6** ✅ · `closed_lists` 발행 키 **23** ✅ · `implementation_choices` 가 클라 무변경으로 배선된다 ✅ · `oe-field-select` 잔존 **0**, `closed_list.js` 호출처 **2** ✅ · `preparer_output_columns` 의 `value` 가 «매핑»이고 런타임이 안 읽는다 ✅.

### ④ 못 밝힌 것

- `/columns` 응답의 `columns` 배열이 **구조분해나 다른 이름으로** 넘겨받는 경로로 렌더될 가능성은 전수로 배제하지 못했다(`stats.` 접근 두 건만 확인).
- 워커 쪽에서 `SYSTEM_RELOAD` 를 받아 **원장 v2 선언**을 다시 읽는 소비자가 있는지 — 「백필이 run boundary 마다 컴파일한다」는 것은 `activate` 응답의 `note` 문자열이 하는 «주장»이고, 백필 코드로 직접 재지 않았다.

---

## ⑨ 맵 편집·확정 — 화면 편집 → 저장 → 정렬/규격 → 확정 이력

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `map_editor.js::loadExistingMap` | `main.py` 제네릭 표 라우트 | `#btnLoadMap` 클릭(`:664`) · 부팅 복원(`:4109`) · 프레임 진입(`:8423`) | HTTP GET 쿼리 | `` `/tables/${selectedTable}/data?limit=2000&filters=${enc(JSON.stringify(filterModel))}` `` — `defer_total` 을 **일부러 안 붙인다**(응답 `total` 로 셀 절단을 판정하므로) | 호출처 3 | 🔊 `alert('맵 로드 실패 · 테이블·맵 키 확인')` / quiet 모드면 같은 문구 토스트. 행은 왔는데 셀 0이면 별도로 `'${selectedTable}: ${fetchedRows}행 중 좌표로 읽힌 셀 0개 — X/Y 컬럼을 확인하십시오.'` | ✅ |
| `map_editor.js::fetchGridMetaFor` | `wafer_map_metadata` | `resolveDeclaredGridMeta:5617` · `diagnoseDesignationAlignment:9506` · `saveMapSpecOnly:9789` · 오버레이 쌍 `:10464-65` | HTTP GET 쿼리 | `` `/tables/wafer_map_metadata/data?limit=2&defer_total=true&filters=…` `` — **`limit=2` 로 「둘 이상인가」를 행 수로 판정** | 5 | 🔊 404/405 → `null`(「선언 없음」) · 그 외 `throw new Error('맵 규격 조회 실패 (HTTP N)')` — 호출자가 결정 | ✅ |
| `map_editor.js::pushMapData` (1/2) | `PUT /tables/wafer_map_metadata/data/updates` | `#btnPushMap` 클릭(`:707` 유일 리스너) | HTTP PUT 본문 | `{updates:[{business_key_val:`${selectedTable}_${mapIdStr}`, updates:{map_pk, target_table, map_id, grid_metadata}, source_name:'user', updated_by}]}` — 🔴 `effort` **없음**(주석이 사유 명시: 같은 배치 엔드포인트라 두 번 청구됨) | 1 (`crud.apply_batch_updates`) | 🔊 실패 시 `metaPushFailed` 를 물고 가 `:6352` 에서 `'셀 N건 적재 · 맵 규격 저장 실패 (HTTP N) — 다시 Push하십시오.'` | ✅ |
| `map_editor.js::pushMapData` (2/2) | `PUT /tables/{selectedTable}/data/updates` (`main.py:2863`) | 같은 클릭, 1/2 직후 | HTTP PUT 본문 | `{updates, silent:false, replace_map:true, effort: effortSnapshot()}` — **이 화면에서 `effort` 가 실리는 유일한 요청** | `_validate_effort` → `crud.record_interaction_effort` (1) | 🔊 `'적재 완료 — N건'` / `console.error('❌ [API Response 2/2] …')`. `effortCommitIfRecorded(result)` 가 `res.ok` 가 아니라 **서버가 기록했다고 답할 때만** 카운터를 비운다 | ✅ |
| `map_editor.js::saveMapSpecOnly` | `PUT /tables/wafer_map_metadata/data/updates` | `#btnSaveMapSpec` 클릭(`:708` 유일) | HTTP PUT 본문 + `AbortController` | `{updates:[{business_key_val, updates:{target_table, map_id, grid_metadata}, source_name:'user', updated_by}]}` — 🔴 `effort` **없음**, 셀 0건 | 1 | 🔊 **세 갈래로 가른다** — `!res.ok`: `'…아무것도 기록되지 않았습니다.'` / 타임아웃: `'…N초 안에 응답이 오지 않았습니다. 저장됐는지 확인이 필요합니다…'` / 예외: `'응답을 받지 못했습니다'` | ✅ |
| `map_editor.js::saveLegendToServer` | `PUT /tables/map_split_registry/data/updates` | `pushMapData:6333` 의 `await` — **호출처 1** | HTTP PUT 본문 | `{updates, replace_map:true}` — 🔴 `effort` 없음(같은 사람 동작의 후반부). 쓰기 전 관문 넷: `probeZoneColumns()` · `legacyBands` 미판독 행 · `readRegistryScope` · 지문 대조 | 1 | ⚠️ 저장 실패는 🔊 `'DOE·split 서술 registry 저장 실패 · 오프라인 캐시에만 보관됨'`. 그러나 **관문 거절 넷은 🔇 조용** — `{ok:false, reason:'zone-columns-missing'\|'adopted'\|'conflict'\|'empty'}` 를 «반환만» 하고 화면에 안 뜬다 | ⚠️ |
| `map_editor.js::saveDoeDraft` | `localStorage` | 범례 편집 | localStorage 키 | `doeDraftKey(selectedTable, mapKey)` + 별도 `LAST_OPEN_KEY`(`:4078`) | 1 (`restoreDoeDraftWithPrecedence:5927`) | 🔇 `try/catch` 로 삼킨다(`/* 무해 */`) | ✅ |
| `map_editor.js::resolveValidDie` | `GET /tables/{ref.table}/data` | 유효 다이 참조 해석 | HTTP GET 쿼리 | `` `?limit=${OVERLAY_CELL_LIMIT+1}&defer_total=true&filters=…` `` — 절단을 `rows.length > 2000` 으로 판정하고 `total` 은 안 쓴다 | 1 | 🔊 `refuse(ref, '${ref.table}: 참조 맵 셀 조회 실패 (HTTP N).')` · 절단은 **실패로 강등**해 이름을 댄다 | ✅ |
| `map_editor2.js::start` → `map2/api.js::loadWorklist` | `GET /api/maps/alignment/worklist` (`main.py:4503`) | 페이지 부팅(`map_editor2.html:877`) · 검색어 입력 | HTTP GET 쿼리 | `?rule&map_table&q&sort&order&limit&offset` — 🔴 **`q`·정렬·페이징이 전부 서버**(클라에 「전량 로드」 함수가 없다 — 확장성 상설 준수) | 1 (abort 신호까지 통과) | 🔊 `withWorklistError` → 목록 영역 사유 문구. 라우트 미배선이면 `RouteNotServedError('worklist')` 로 **이름을 대고** 거절 | ✅ |
| `map2/api.js::loadReferenceView` | `GET /api/maps/alignment/view`(`main.py:4292`) → `alignment_view_service.resolve_alignment_view` → `map_alignment.build_alignment_view` | 목록 행 선택 | HTTP GET 쿼리 | `{rule, map_table, params: JSON.stringify(r.params)}` + 조건부 `reference`·`x_col`·`y_col`·`value_col`·`include_cells='false'`. 🔴 **`assume_reference_geometry` 를 어느 방향으로도 안 보낸다** → 서버 기본 `True` 가 항상 성립 | 1 (`decode.js::decodeReferenceView`) | 🔊 400/404 는 서버 문장 그대로. `params` 없으면 **요청 전에** reject | ⚠️ |
| `map2/api.js::loadAlignConfig` | (없음) | 임계값이 필요할 때 | — | `ROUTES.config = null` 이 **의도된 부재** → `Promise.reject(new RouteNotServedError('config'))` | 0 (서버 라우트 0) | 🔊 `"no server route exists for 'config'…"` 를 던진다. 판정층은 임계값이 없으면 **순위를 안 매긴다** | ⚰️ (의도적·명명됨) |
| `map2/main.js::onConfirm`(`:1830`) | `POST /api/maps/alignment/confirm`(`main.py:4403`) | `#me2-confirm-btn` 클릭 또는 Enter — **무장 단계 없음**(제품 소유자 2026-08-06) | HTTP POST 본문 | `{rule, decision_key, frames: r.frames \|\| {}, map_table, columns:{x,y,val}, frame, sources, ruling, state, reference, confirmed_by}`. 🔴 `frames` 를 **일부러 `{}`** 로 · 🔴 `shift_dx/dy` 삭제됨(상수 0을 배치로 실어 보내던 결함) · `enrichment_row_id` 안 보냄 | 1 (`map_editor2.js:104` 이 `live.confirmFrame` 위임) | 🔊 서버 문장을 `#me2-confirm-note` 에 그대로 + `#me2-confirmbar[data-me2-confirm-state="failed"]`. 결정키 미충족은 **요청 전에** 같은 슬롯으로 거절 | ✅ — 🔴 **map2 는 확정할 수 있다**(vite 주석의 전제는 이미 충족) |
| `main.py::confirm_map_alignment` | `frame_confirmation.record_confirmation` → `FrameConfirmation` + `FrameConfirmationSource` 행 | 위 POST | 함수 인자 → DB 행 | `models.FrameConfirmation(… frames=dict(frames), core_frame=frames.get('core_frame'), dt_frame=frames.get('dt_frame') …)` | **1 운영 호출처**(`main.py:4441`. 나머지 12건은 `server/tests/*` — 규칙대로 뺀다) | 🔊 `ConfirmationRefused` → 400 + 한국어 문장. `_resolve_frames` 가 **`frames` 도 `frame` 도 비면 거절**(「확정된 프레임이 없습니다」) | ✅ |
| `frame_confirmation._write_confirmed_meta` | `wafer_map_metadata.grid_metadata` | `record_confirmation` 내부 | DB 배치 upsert | `map_alignment.confirmed_meta_for` 가 만든 `meta` 에 `base[FRAME_CONFIRMED_KEY]=dict(mark)` + `apply_valid_die_ref` 를 찍는다. `transaction_id=confirmation_uid`, `silent=True` | 1 | 🔴 **사용자에게는 조용.** 메타 표가 미선언이면 `logger.warning("[frame_confirm] '%s' is not a declared table — the confirmed coordinate system was not stored")` 만 남고 **확정은 200 으로 성공**. `valid_die_ref` 미도장도 `logger.info` 뿐 | ⚠️ 사슬이 끊겨도 화면은 「확정됨」 |
| `frame_confirmation.as_payload`(`main.py:4448` 응답) | `map2/main.js::onConfirm` 의 `.then()` | 응답 도착 | HTTP 응답 본문 | 서버가 **전부** 실어 보낸다: `{confirmation_uid, version, unit, frames, confirmed{frame,map_table,columns}, reference, ruling, weakest, confirmed_by, confirmed_at, supersedes, sources[]}` | 🔴 **0** — `.then(() => { confirmInFlight=false; setSession(withConfirmed(session)); })` 가 **인자를 안 받는다**. `map2/api.js:358` 이 「Returns the WHOLE created record… **Render that.** NEVER re-fetch after a write.」라고 «자기 파일에» 적어 뒀다 | 🔇 조용 — 화면은 `#me2-confirm-hint` 가 `'확정됨'` 이 될 뿐. `confirmation_uid`·`version`·`supersedes` 가 **브라우저에 도착했다가 버려진다** | ⚠️ |
| `FrameConfirmation.superseded_by` / `supersedes_uid` 사슬 | (없음) | `record_confirmation:622` 이 `prev.superseded_by = uid; header.supersedes_uid = prev.confirmation_uid` | DB 컬럼 | 마이그레이션 `add_frame_confirmation.py` 가 append-only 로 깔고, 재확정마다 version+1 로 사슬을 **쓴다** | 🔴 **0** — 읽는 곳은 `.is_(None)` 필터 «셋»(`frame_confirmation.py:141,174` · `map_alignment.py:6649`)뿐이고 전부 「현행만 고르려고」 읽는다. **이력을 내는 GET 라우트 0건**(`main.py` 의 `/api/maps/*` 전건 열거로 확인) | 🔇 조용 — 아무 화면도 「이 단위가 세 번 확정됐고 두 번 뒤집혔다」를 말하지 못한다 | 🔴 **흐름 ⑨ 의 「확정 이력」 절반이 쓰기만 있고 읽기가 없다** |
| `map_alignment._live_confirmations`(`:6641`) | 워크리스트 행 `confirmation` | 워크리스트 요청(`:6812`) | DB 조회 → HTTP 응답 | `filter(rule_name, unit_key.in_(part), superseded_by.is_(None)).order_by(version.desc())` → 행에 `{version, confirmed_by, confirmed_at}` **셋만** | 1 (`map2/view_model.js:1313` `confirmed: !!row.confirmation`) | 🔇 확정이 없으면 `pending`(정상 상태) | ✅ — 다만 **현행 1건만이고 이력이 아니다** |
| `map2/view_model.js` 「이 세션 확정」 배지 | `#me2-badge-session` | 확정 성공 | 클라 메모리 | `confirmedThisSession: session.confirmedCount` ← `session.js:491` 의 `+1` | 1 | 🔇 새로고침하면 0. **서버가 세어 준 수가 아니다** | ⚠️ 「확정 이력」으로 읽히지만 세션 카운터 |
| `frame_confirmation.derived_cell_scope` | `models.CellSource` 질의 | (없음) | — | `filter(CellSource.confirmation_uid == confirmation_uid)` | **0 운영 호출처** — 히트 2건은 `server/tests/test_frame_confirmation.py:209`(시험) 과 `bonding_plan.py:276`(**주석**) | 🔇 조용 | ⚰️ |
| `bonding_plan.py:283` | `frame_confirmation.live_confirmation_for_maps` → `warrant_of` | 본딩/전사 계획 조회 | 함수 인자 → DB 행 | `basis = {"kind": BASIS_CONFIRMATION, "confirmation_uid", "version", "reference", "warrant": warrant_of(header), "weakest"}` | 1 (`bonding_plan`·`transfer_plan` 두 경로가 같은 함수) | 🔊 `logger.warning("[BondingPlan] frame confirmation lookup failed: %s")` + 이름 붙은 상태(`not_declared`/`mapping_unavailable`)로 물러난다 | ✅ **확정을 실제로 읽는 유일한 운영 소비자** |
| 확정 → `map_editor.js::parseValidDieRef` | 레거시 에디터 | 확정 뒤 사람이 레거시에서 맵 로드 | DB 행(`grid_metadata`) | 확정이 `apply_valid_die_ref` 로 `grid_metadata.valid_die_ref` 를 찍고(`map_alignment.py:799`) 레거시가 같은 키를 읽는다(`map_editor.js:2489`). 유도가 하나이고 `contracts/map_seam` 이 양쪽을 채점 | 1 | 🔇 도장을 못 찍으면 `logger.info("[MapAlignment] valid_die_ref NOT stamped…")` 뿐 | ⚠️ 🔴 **레거시는 `frame_confirmed_from` 을 읽지 않는다**(`map_editor.js` grep 0) — 확정된 회전·면은 «값»으로만 들어가고 「확정됨」 표지는 레거시에 없다 |
| `chain_ingestion_worker` → `mappers/dt_alignment_metadata_mapper` | `wafer_map_metadata` | 체인 규칙(`alignment_rule`·`map_table`·`metadata_target_table`)이 걸린 표에 행이 적재될 때 | 함수 인자 → DB 배치 | `resolve_alignment_view(...)` → 게이트 통과 시 `confirmed_meta_for(..., mark={source:UPDATED_BY, rule, decision_key, winner, input_fingerprint})` → `grid_metadata` upsert | 1 | 🔴 시끄러움이 **엉뚱한 방식으로** — `print('------------------- AUTO ALIGNMENT IS RUNNING------------------')` + `print(rule)` 이 raw stdout 으로 나간다(`logger` 아님). 게이트 미통과는 `continue` 로 🔇 | ⚠️ **`FrameConfirmation` 행을 안 만든다.** `mark` 에 `confirmation_uid` 가 없어 사람 확정과 «같은 표지 자리»를 쓰면서 재검 가능성이 없다 |
| `chain_ingestion_worker` → `mappers/core_alignment_mapper` | `dt_inventory.core_frame` | 같은 체인 | 함수 인자 → DB 배치 | `resolve_alignment_view(..., alignment_thresholds, source_filters, source_table, ignore_source_metadata=True)` — **HTTP 라우트가 안 보내는 인자 넷을 이쪽만 쓴다** | 1 | 🔇 게이트 미통과·`placement is None` 은 `continue`. 미선언 컬럼은 배치가 경고 남기고 200 | ⚠️ |
| `mappers/dt_map_mapper` → `dt_map_derivation.join_rule` | 가상 조인 선언 | 체인 적재 | 함수 인자 | `join_rule(db, "dt_log_confirmed_attribution")` / `join_rule(db, "dt_log_frame_attribution")`(`dt_map_derivation.py:103-104`, 호출 `:561-562`) | 1 | 🔊 `DerivationRefused(REFUSE_JOIN_RULE_MISSING, "virtual join rule '%s' is absent or was not verified…")` | 🔴 **끊김** — 커밋된 `virtual_join_rules.json.sample` 에서 그 두 이름은 **`_retired_` 접두**다(`:5`·`:22` 실측). 로더가 선언이 아니라 주석으로 건너뛰므로 **출하 샘플 기준 이 두 조회는 항상 거절** |
| `POST /confirm` 의 `frames` | `dt_map_derivation.FRAME_COLUMN`(`"dt_frame"`) | — | — | 화면이 `frames:{}` 를 보냄 → `header.dt_frame = frames.get('dt_frame')` = **NULL**. 그리고 `dt_map_derivation` 은 `dt_frame` 을 «가상 조인»에서 읽지 `FrameConfirmation` 에서 읽지 않는다(`grep frame_confirmation server/dt_map_derivation.py` = **0**) | **0** | 🔇 조용 | 🔴 양쪽 다 존재하는데 잇는 것이 없다 |
| `GET /api/maps/overlay`(`main.py:4254`) | (없음) | — | HTTP GET | `map_overlay.get_overlay(...)` · `parse_sources` · `MAX_OVERLAY_CELLS` | 🔴 **0 소스 소비자** — `client2/` 전량에서 `api/maps/overlay` 히트 0(재확인). 유일 히트는 `server/auto_update.log` 의 **과거 시험 실행 로그** | 🔇 조용 | ⚰️ (HTTP 표면만. `map_overlay` **모듈**은 `bonding_plan`·`transfer_plan`·`map_alignment` 가 활발히 쓴다) |

### ⑨ 에서 목록이 놓친 흐름

- **자동 정렬이 «두 갈래 더» 있다.** 사람 확정(`POST /confirm`) 말고 체인 매퍼 둘이 같은 채점기를 태워 좌표계를 쓴다 — `dt_alignment_metadata_mapper`(→`wafer_map_metadata`) · `core_alignment_mapper`(→`dt_inventory.core_frame`). 🔴 **둘 다 `FrameConfirmation` 행을 안 만든다** → 「확정 이력」에도, `bonding_plan` 의 warrant 조회에도 안 잡힌다.
- **자동 메타 등록**(`map_meta_registrar.py`, `MapMetaCollector`) — `directory_watcher:2635` · `chain_ingestion_worker:993` 이 트리거. **`DEFAULT_ENABLED = False`**(2026-08-30 이후)라 선언으로 켜야 돈다. 켜지면 `source='auto_map_meta'`(우선순위 99)로 합성 프레임을 만들고, 그 행을 `map_alignment.make_frame_transform` 이 거절한다 — **워크리스트 `unscorable` 의 큰 원천**.
- 🔴 **`wafer_map_metadata` 에 기록자가 «다섯»이다**: 레거시 Push(1/2) · 레거시 규격 저장 · 확정(`_write_confirmed_meta`) · 체인 자동 정렬 · 자동 등록. **다섯이 같은 `grid_metadata` 한 칸을 쓴다.**
- **범례/DOE 계획**은 별도 표(`map_split_registry`)에 `replace_map:true` 로 간다. `transfer_plan.js` 는 서버에 **쓰지 않는다** — fetch 3건 전부 GET(`/api/transfer-plan/stages`·`/source-summary`·`/validate`). `frontend.md` §5.1 의 「쓰기 소유권」 문장 ✅ 정확.
- ⚠️ **`map2/main.js` 에 리터럴 NUL 바이트가 있다**(오프셋 28521, `join('\x00')`). 그래서 ripgrep·Grep 도구가 이 파일을 **binary 로 보고 건너뛴다** — **grep 기반 감사가 map2 의 합성 루트 2,610줄을 통째로 못 본다.** 이번 측정도 `grep -a`/`sed` 로만 읽혔다. 🔴 이건 「도구가 이 파일에서 눈이 먼다」는 뜻이라, 이 저장소의 감사 전반에 걸리는 사각이다.

### ⑨ 양끝이 다 있는데 아무것도 잇지 않는 이음매 (다섯)

| # | 이음매 | 양끝 | 가운데 |
|---|---|---|---|
| 1 | **확정 이력 ↔ 아무 화면** | `superseded_by`/`supersedes_uid` 를 `record_confirmation:622` 가 쓰고 append-only 스키마가 받친다 | **이력을 내는 GET 라우트 0건.** 읽는 곳은 「현행만 고르는」 `.is_(None)` 셋뿐 |
| 2 | `as_payload` 응답 ↔ `onConfirm().then()` | 서버가 `confirmation_uid`·`version`·`supersedes`·소스 행 전부를 보낸다 | 클라가 `.then(() => …)` 로 **인자 없이** 받는다 (`api.js:358` 이 「Render that」이라 적어 두고) |
| 3 | `POST /confirm` 의 `frames` ↔ `dt_map_derivation.FRAME_COLUMN` | 화면이 `frames:{}` 를 «일부러» 비워 보내고, 파생기는 `dt_frame` 을 가상 조인에서 읽는다 | 두 이름이 만나는 자리가 코드에 없다 |
| 4 | `derived_cell_scope` ↔ 회수 경로 | 함수·질의 존재 | 운영 호출처 0 |
| 5 | `GET /api/maps/overlay` ↔ 클라 | 라우트·엔진 존재 | 소스 소비자 0 |

### ⑨ 에서 나온 문서·주석 정정

| 자리 | 적힌 것 | 실측 |
|---|---|---|
| 🔴 `client2/src/map2/api.js:277-283` | 「THE COLUMNS ARE SENT AND ARE NOT YET HONOURED … the route takes no column parameter at all (`server/main.py:4160-4168`)」 | **거짓이다.** `main.py:4292 get_map_alignment_view` 가 `x_col`·`y_col`·`value_col` 을 받아 `resolve_alignment_view` → `build_alignment_view(:5609-13)` 까지 넘긴다. 응답도 `unit.columns.{x,y,value}.{column, origin}` 으로 에코하고, 클라 `main.js:2345-50` 의 `answeredColumns` 가 `a.origin === 'chosen'` 으로 **이미 읽고 있다** |
| 🔴 `client2/src/map2/main.js:1402-04` | 콘솔 진단 「the fix is `unit.x_col` / `unit.y_col` on the wire」 | 같은 이유로 낡았다. 서버는 `unit.x_col` 을 «낸 적이 없고** `unit.columns` 를 낸다 |
| ⚠️ `client2/map_editor2.html:36-38` | 「모듈 엔트리는 아직 붙이지 않았다 … 배선 레인이 `</body>` 직전에 한 줄을 넣고」 | `:877` 에 **이미 있고** `vite.config.js:22` 에도 등재돼 있다. 같은 파일 `:876` 이 스스로 반박한다 |
| ⚠️ `CODE_MAP.md` §7-A 줄 수 3건 | (다른 15개 모듈은 정확) | `main.js` 2,489 → **2,610** · `view_model.js` 1,395 → **1,548** · `session.js` 485 → **535** |
| 🔴 `CODE_MAP.md` §7-A 「모듈 의존」 | `authoring` → `brush`·`legend` 가 살아 있는 갈래처럼 적혀 있다 | `authoring.js`(394)를 `src/` 안에서 import 하는 곳 **0건**(유일 히트는 `client2/tests/map2_authoring_harness.mjs` — 시험 전용이라 뺀다). `brush.js`(316)·`legend.js`(161)의 유일한 importer 가 그 `authoring.js` 다 → **871줄이 화면에서 도달 불가** |
| ✅ `frontend.md` §5 | 「맵 에디터는 WebSocket 을 쓰지 않는다. REST pull/push + localStorage」 | **정확하다.** `map_editor.js` fetch 27자리 전건 확인 · WebSocket 0건 · `localStorage` 는 `copyHeader`·사이드바 폭·DOE 초안·최근 열람 넷 |
| ⚠️ `docs/spec/MAP_EDITOR_SPEC.md` §5.2 | 「맵 에디터 클라는 이 엔드포인트를 더 이상 호출하지 않는다」는 **정확**하다 | 다만 절 제목 「엔드포인트는 살아 있다」와 소비자 표가 오해를 부른다: 표의 `bonding_plan.py`·`transfer_plan.py` 는 `map_overlay` **모듈**의 소비자이지 **라우트**의 소비자가 아니다. 라우트의 소스 소비자는 시험 하나(`server/tests/test_map_overlay.py`)뿐 |
| ✅ `vite.config.js:20-21` | 「until the new screen can actually confirm a frame」 | **그 전제는 이미 충족됐다** — map2 는 확정 호출처를 가진다(`map2/main.js:1830`). 「왜 아직 병렬인가」의 진짜 사유는 `CODE_MAP` §7-A 가 밝힌 `artifact_gateway.isImplemented()` 하드코딩 `return false` + 엑셀 in/out 미구현이고, 그 서술은 ✅ 정확 |

---

## 세 흐름 총평 — 이 라운드가 찾은 「반쪽」의 부류

```
① 계산됐고 · 화면에 «찍히고» · 전선을 «안 건넌다»
   ②  walk_box 의 hops (화면: 「경로 A · 3홉」  전선: 없음  서버: 기본 12)
   ⑨  map2 의 assume_reference_geometry (안 보냄 → 서버 기본 True 가 항상)
   ④  /view 의 reference_limit · /columns 의 combination · deletion-preview 의 context_token

② 서버가 «보냈는데» 읽는 쪽이 0
   ②  edges (walk_box) · walk.hops_reached · truncationReason
   ④  closed_lists 23키 중 12 · /columns 6키 중 5 · deletion-preview 14키 중 13 · plan 의 counts·refusals
   ⑨  as_payload 전량(confirmation_uid·version·supersedes) — 「Render that」이라 적힌 채로

③ 쓰기는 «있는데» 읽기가 0
   ⑨  FrameConfirmation 의 supersede 사슬 — 흐름 ⑨ 의 이름 「확정 이력」이 가리키는 바로 그 절반

④ 검사·거절문이 «있는데» 도달 불가
   ④  convergence_probe(자기 입력을 되돌려받음) · review/revise 라우트(누를 버튼 없음)
   ②  COLLECTS 일곱 중 다섯 · options.question 갈래

⑤ 양끝이 다 있는데 «가운데가 아예 없다»
   ②  rb-walkbox 클래스 15 ↔ CSS 규칙 0
   ⑨  frames{} ↔ dt_map_derivation.FRAME_COLUMN · overlay 라우트 ↔ 클라
   ⑨  dt_map 의 두 조인 규칙 ↔ 샘플의 `_retired_` 접두
```

🔴 **셋 다 「함수가 있나」로는 통과한다.** 갈린 것은 전부 「무엇이 이 이음매를 실제로 지나가나」를 물었을 때다 —
`SYSTEM_FLOWS.md` §1 의 「반쪽이 핵심 발견 단위」가 이 라운드에서 **19건**을 냈고, 그중 **⚰️ 죽은 갈래가 11**이다.

---

## ⚠️ 도구 사각 — grep 기반 감사가 `map2/main.js` 2,610줄을 «한 줄도 못 본다»

⑨ 측정 중에 나온 것이지만 **⑨만의 문제가 아니라 이 저장소의 감사 전반에 걸린다.** 재현 가능하다:

```
실측   client2/src/map2/main.js  =  156,321 바이트, 오프셋 «28521» 에 «리터럴 NUL 바이트»
       원인은 소스가  join('<NUL>')  을 «이스케이프가 아니라 진짜 0x00 바이트»로 들고 있다는 것

$ rg -n "confirmFrame" client2/src/map2/main.js
  binary file matches (found "\0" byte around offset 28521)      <- 줄을 «안 보여 준다»

$ grep -an "confirmFrame" client2/src/map2/main.js
  1769: ... 1796: ... 1830:  Promise.resolve(api.confirmFrame({   <- «세 줄» 있다
```
🔴 **Grep 도구로 `client2/src/map2` 에서 `confirmFrame` 을 찾으면 결과가 `api.js` «하나»다.**
   호출부가 있는 `main.js` 는 목록에서 «조용히» 빠진다 — 0 히트가 아니라 «파일이 없는 것처럼» 보인다.
🔴 그래서 「map2 는 확정을 못 한다」 같은 결론이 **grep 만으로는 정직하게 도출된다.** 실제로 그 파일에 호출부가 있다.
   이 문서의 ⑨ 표에서 map2 관련 줄은 전부 `grep -a` / `sed` 로 다시 읽어 확인했다.

**권고(판정은 총괄):** 그 한 바이트를 `' '` 로 적으면 사각이 사라진다 — **동작은 동일하고 도구가 눈을 뜬다.**
다만 코드 수정이라 이 라운드 범위 밖이고, 이 문서는 «사실만» 남긴다.
