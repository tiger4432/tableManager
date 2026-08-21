# Design Session — Report Channel (design session -> lead PM)

---

# 🔵 인수 블록 — 컴팩트 시점 상태 (2026-08-22 00:xx). **새 세션은 여기부터**

## 환경 — 이걸 안 맞추면 전부 404가 난다

```
워크트리   C:/Users/kk980/Developments/assyManager-design   브랜치 design
dev 서버   cd <워크트리>/client2 && npm run dev -- --port 5173 --strictPort
API        8080 = 메인 트리(총괄 관리). 재기동 금지
```
🔴 **포트가 반드시 5173.** `config.js`가 `location.port === '5173'` 으로 API를 판별한다.
5174로 밀리면 API를 «자기 자신»에게 걸어 전부 404가 되고, 화면은 멀쩡해 보인다.

```
목업 원본  소유자가 zip 으로 준다: C:/Users/kk980/Downloads/데이터 그리드 UI 목업.zip
           풀어서 `Main Grid Mockup.dc.html` (1106줄). 2a=73행 · 2b=270행 · 2c=437행
지시서     task/MIGRATION_2b.md (저장소 사본, Phase 0 + 실측표 포함)
채널       총괄→나 task/DESIGN_ORDERS.md(main) · 나→총괄 task/design_session_report.md(design)
```

## 🔴 판정 규칙 A/B/C — 「목업대로」의 범위 (소유자)

```
A 픽셀까지 똑같이   실측표 수치 · 열 순서와 폭 · 정렬 띠/칩/①② 존재와 배치 ·
                    탭 순서와 기본 활성 · 하단 단축키 줄의 항목과 순서
B 뜻만 같으면 됨    DOM 구조 · 클래스 이름 · 상태 관리 · 렌더 방식
C 목업의 허구       모든 데이터 값 · TL26-*/CW-*/EQP07 · 신뢰도 % · 「미저장 6」·「15,489」·
                    「4,052」 · 규칙 이름 · 참조 그리드 7행 → 전부 실제 API 응답에서 온다
```
애매하면 **A로 간주.** A에서 벗어나려면 지시서를 «먼저» 고친다.

## ✅ 착지 완료 (전부 main 병합됨, 브라우저로 직접 확인함)

```
Phase 1   컬럼별 필터 · 시스템 컬럼 필터 없음 · 칩(⇲ 조인 표시) · 칩 ✕ 개별 해제
Phase 2   사이드바 640px · 폭 영속(+ 복원 시 clamp) · 탭 밑줄형 · 참조 탭 기본 활성
Phase 3.1 열 순서 = 규칙의 target_fields «배열» (candidate_for 키 순서 아님) · ①②
    3.2   참조뷰가 그리드 (거터 · 30/28px · 드래그+Shift방향키 한 모델 · custom-range-selected)
    3.3   copy → tsv.js 재사용 · clipboard.js «import 안 함» · 가드는 clipboard.js 쪽에 이미 있었음
    3.4   정렬 띠 (알린다, 막지 않는다)
Phase 4.1 client2/tests/reference_grid_paste_harness.mjs · FLOORS 22 · 변이 4/4 · 대조군 2/2
    4.3   frontend.md §3.6 신설 + 모듈표 · docs/history/20260821_232730_*.md
밀도     헤더바 52 · 탭 34 · 그리드 헤더 30 · 데이터행 28 · 셀 mono 11.5 ·
         헤더 sans 600 10.5 자간.4 uppercase · 필터칸 3px/1px/r3px/10.5 · 배너 30
형태     칩 → 상단 헤더 바 «안» · 밀린 열 수 → 그리드 헤더 우단 · 정렬 띠 → 탭 아래 30px 플러시
```
🔴 **4.4(빌드·dist 커밋)는 내 것이 아니다.** 총괄이 굽는다. 소스만 커밋한다.

## ▶ 다음에 할 것 — 2b 남은 넷, 그다음 2c

```
1  메인 그리드의 채울 열 두 개에 ①② + accent 배경 + inset 0 -2px 0
   ⚠️ 규칙은 «비동기»로 온다 — buildColumnDefs 시점엔 아직 없다.
      syncReferenceViewRule 이 규칙을 잡은 뒤 setGridOption('columnDefs', buildColumnDefs()) 재적용 필요
2  사이드바 하단 30px 단축키 줄
      Shift+↑↓ 범위 · Ctrl Enter 일괄 · Ctrl Shift V Smart Paste · 우측 Copy Header
   🔴 Copy Header 는 «새로 만들지 말고» 기존 #copy-header-toggle 을 DOM 에서 옮긴다
      (index.html 180행 근처. id 조회라 위치를 옮겨도 JS 는 그대로 돈다)
   `.kbd` 키캡 클래스는 이미 style.css 에 있다
3  참조 그리드 아래 LOT_EVENT 근거 표 (목업은 «탭»이 아니라 아래에 «쌓인» 표)
4  참조 그리드 열 폭  # 32 · dt_job 1fr · x 46 · y 46 · dt_lot 132 · dt_slot 74 · 신뢰도 66
그다음 2c  Global 탭을 카드 타임라인 → «표»로 (timeline.js 전면)
      필터줄: 사용자 전체▾ · 종류 전체▾ · 오늘▾ · 우측 「50건 중 18」
      헤더:  시각58 · 사용자62 · 종류74 · 대상·컬럼 1fr · 변경150 · TX84
      행:    종류 알약(MANUAL/PASTE/INGEST/OVERWRITE/BATCH/DELETE/SYNC) ·
             대상은 두 줄(키+컬럼) · 변경은 「옛값 취소선 → 새값」
      하단:  행 클릭→그 셀로 이동 · Tx 클릭→그 트랜잭션만 · 우측 「더 보기」
```

## ⚠️ 아는 함정 — 다시 밟지 말 것

```
목업 열 이름 13개 중 8개가 «실제 dt_log 에 없다»
   없는 것: dt_cell_key · dt_job · dt_eqp · product · dt_x · dt_y · core_wafer · core_product
   🔴 소유자 판정: 「열순서는 그냥 지금 로직으로 해」 → 이름으로 매칭, 없는 건 건드리지 않는다. 종결됨
Cell 탭은 소유자가 «빼라»고 했다 (목업엔 4탭이지만 3탭이 맞다). 리스너는 가드만 하고 남겨 뒀다
   — activeHistoryTab === 'cell' 을 timeline.js 가 다섯 군데서 읽는다
CSS 는 «#myGrid» 로 건다. theme.js 가 ag-theme-quartz ↔ -dark 를 뒤집어서
   테마 클래스로 걸면 한쪽 모드에서만 맞고 반대쪽에선 «조용히» 없다 (실제로 한 번 당했다)
변이 앵커는 CRLF 를 탄다. 
 으로 적으면 이 체크아웃에서 «아무 데도» 안 맞는다
grid.js 를 참조뷰에서 import 하면 «순환»이다 (grid.js 가 이미 그 모듈을 import 한다)
   → 공용 헬퍼는 state.js 로 (visibleRangeColIds 가 그렇게 갔다)
buildColumnDefs 를 고치면 virtual_column_render_harness 의 «슬라이스»도 같이 고쳐야 한다
   (새 헬퍼/상수를 sandbox 에 안 넣으면 ReferenceError 로 죽는다 — 한 번 그랬다)
```

## 🔴 아직 못 잰 것 (「없다」가 아니라 「못 쟀다」)

```
정렬 띠의 «불가» 판정과 그 뒤 서버 거절
   총괄이 dt_inventory 에 가상조인(dt_lot_confirmed·dt_slot_confirmed)을 «만들어 뒀다».
   그런데 서버가 config 를 아직 «다시 안 읽었다» — 실측: /tables/dt_inventory/schema 의
   virtual_columns 가 여전히 []. 총괄이 리로드를 눌러 주면 그때 걸어서 보고할 것
   (백그라운드 감시 task biobq1eck 가 그 순간을 잡도록 걸려 있었다 — 컴팩트 후엔 다시 걸 것)
```

## 감시

`origin/main` 폴링 모니터(task bgpt8wdma)가 걸려 있고 `task/DESIGN_ORDERS.md` 변경을 따로 표시한다.
컴팩트 후 끊겼으면 다시 건다.

---

> Channel per the 2026-08-21 21:0x brief: lead PM writes `task/DESIGN_ORDERS.md` on **main**;
> this file is committed on the **design** branch and pushed. Commits are the doorbell.

**인수 완료 · 워크트리 `C:/Users/kk980/Developments/assyManager-design` (branch `design`) 에서 대기 중.**

---

## ✅ 2026-08-21 22:0x — Phase 3's screen is real now. Walked it. Three things to rule on.

Orders received (`aa4b5ffc`), merged, acted on. The fixtures work — the wall I measured is gone.

### The fixture holds, and it closed a criterion I could not test before

```
dt_inventory   참조뷰 tab appears · panel opens · 3 views · 176 rows of real data
               "이 job 의 원본 행 (dt_log)" / "관측된 좌표 범위" / "같은 장비의 다른 job 들"
dt_log         all six virtual columns render with 🔗
               🔴 I nearly recorded them ABSENT — AG-Grid virtualizes columns and they are
                  appended last, so the first header read returned nothing. Scrolled, then read.
```

**Phase 1's join-column criterion — previously NOT MEASURED — now PASSES:**

```
DT_X_BASE 🔗 filtered on 미상   Matches 34,939 -> 29,830   (server narrowed on a VIRTUAL column)
chip reads                      "DT_X_BASE⇲ contains 미상"  (the ⇲ mark works, keyed off the announcement)
```

That is the exact round-trip the migration order feared would be dropped. It is not dropped.

### 🔴 ⑤ `candidate_for` is EMPTY on all six new views — Phase 3.1 has no source at all

```
dt_frame_confrimation  view[0..2]  candidate_for = {}
core_frame_review      view[0..2]  candidate_for = {}
```

Neither `fill_targets` nor `candidate_for` exists on the new fixtures, so the column-order
contract has nothing to read from. This is not an objection to the fixtures — the views are
display-only by design and the lead said so. It means ㉮/㉯ is still the live question and
**whichever way it is ruled, a declaration has to be written** before Phase 3.1 can start.

### 🔴 ⑥ The panel's decision key is not on screen, and the grid reads as 401 blank rows

Both new rules key on `dt_job`. Measured against `/schema` and the row payload:

```
dt_job          populated on 401/401 rows   —   NOT in /schema.columns, so no grid column
dt_job_id  🗝️     0/401 non-null            <- the business key column, empty on every row
dt_eqp            0/401
dt_lot / dt_slot  1/401
dt_frame        126/401      core_frame     6/401
dt_x_* / dt_y_* 126/401      core_*         6/401
```

So the operator sees 401 rows whose first four visible columns are blank, the identity of
each row is carried by a column the grid is never told about, and the panel silently keys off
it. The panel WORKS — `valueOf` reads the row payload, not the column list — but the screen
cannot tell you which job you are looking at.

🔴 This is the owner's own rule from the brief: 「사람이 «밖에서» 알아야 하는 것이 있으면
그건 화면이 덜 된 것이다」. Adding `dt_job` to that table's declaration is a server-side
change, so I am reporting it rather than doing it.

### 🔴 ⑦ The order's `suppressFilterButton` line is inert on AG-Grid 35.3.0 — and I think that is lucky

I added `floatingFilterComponentParams: { suppressFilterButton: true }` as instructed.
Measured: **14 funnel buttons are still in the DOM.** In 35.3.0 the key moved to
`colDef.suppressFloatingFilterButton`; the spelling the order specifies is silently ignored.

I did **not** switch to the working spelling, because making it work would break something:

```
the funnel button is the ONLY path to the operator list (contains -> equals)
and joinResolvedFilterDef's own header tooltip tells the operator to use it:
   "미해결 행 보기: 필터를 Equals로 두고 '미상' 입력"
```

Verified by clicking it: the menu opens and shows the operator selector. Suppressing it would
delete the path the app's own instruction depends on — a control that says "do X" next to a
screen where X is unreachable.

**Ruling needed:** leave the button (drop that line from the order), or suppress it and move
the operator choice somewhere reachable. I have left the inert line in place and touched
nothing, so today's behaviour is the safe one either way.

### Watch

A monitor is armed on `origin/main`, flagging `task/DESIGN_ORDERS.md` changes separately from
ordinary commits, so a new order reaches me without polling.

### Standing

Phase 1–2: awaiting the lead's merge. Phase 3: not started, awaiting ㉮/㉯.

---

## ▶ Phase boundary — 3.1 landed (`895658ea`), 3.2 not started

Orders `f41bcef7` received. ⑥ fixed on your side (`dt_job` now leads `display_columns`), ⑤
answered with a declaration that carries both targets in one view. Phase 3.1 is in.

**I did not read the order off `candidate_for`'s keys, and that is deliberate.**

You asked me to weigh whether key order survives the loader and to write the assumption into
a comment if I leaned on it. I measured it end to end — over real HTTP, `target_fields` is
`['dt_lot','dt_slot']` and `view[0].candidate_for` arrives in that same order — and then did
not lean on it. `target_fields` is an **array**: JSON guarantees its order outright. Key order
only survives while no column is named something integer-like, because `Object.keys` hoists
those to the front numerically. Nothing is named `1` today; the day something is, a paste
lands in the wrong column with no error and no refusal. Reading the array removes the
assumption instead of documenting it. `candidate_for` still supplies the mapping — which view
column feeds which target — which is the half `fill_targets` never had.

**Contract verified against real payloads**, not fixtures:

```
view[0]  cols ['dt_lot','dt_slot','cells']   candidate_for {'dt_lot':'dt_lot','dt_slot':'dt_slot'}
         -> renders dt_lot ① · dt_slot ② first and adjacent, cells after.  1 row (the candidate)
view[1]  cols 8, candidate_for {}  -> FALLBACK: original order, 72 rows, untouched
```

One correctness detail worth naming: rows arrive as **positional arrays**, so reordering the
header alone would have shifted every value one column sideways and still looked plausible.
The original index is carried through.

Harnesses: 28 · 59 · 72 · 594, zero failures. ⚠️ A grep for this module's filename found
**zero** harnesses; a wider grep found four. I nearly reported it uncovered.

### 🔴 Blocker for walking it — I cannot serve this branch

```
8080          serves the MAIN tree's bundle — does not contain this branch's client
preview tool  refuses a dev server whose cwd is outside the project root, and the
              worktree is a sibling directory -> tried, "cwd must be a relative path
              within the project root", reverted the config byte-exact
```

So Phase 3.1's **render is not walked**. The data contract is measured; the pixels are not.
Options are yours: merge `design` so 8080 can serve it, or approve a launch entry pointing at
the worktree. I have not touched the shared config beyond the one test above, which I undid.

### ⑦ still open (not blocking)

`floatingFilterComponentParams: { suppressFilterButton: true }` remains inert on AG-Grid
35.3.0 and I have left it inert on purpose — the funnel button is the only route to the
`equals` operator that the join column's own tooltip instructs. Ruling welcome whenever.

---

## ✅ 22:2x — served my own branch, walked it. Two phases verified, one new blocker.

`90a11941` was right and the blocker was mine to clear: `npm run dev -- --port 5173
--strictPort` in the worktree, API resolving to 8080 by port. Held 5173. Confirmed by marker
that the served code is **this branch** (`fillPlan`, `FILL_ORDINALS`, `SIDEBAR_WIDTH_KEY`,
`tabReferenceBtn`, `reference-view-fill` all present) before trusting anything on screen.

### Verified for the first time — both were untestable until now

```
Phase 2.2  selecting dt_inventory auto-selects 참조뷰 and opens the panel
           (no rule -> unchanged, Global stays)
Phase 2.1  drag 640 -> 900, reload -> 900 survives (CSS default is 640)
           corrupt value: stored 99999 -> restored 2269 = the cap, grid still 635px wide.
           The clamp-on-the-way-BACK-IN is what stops a stored width from swallowing the grid
⑥ (yours) dt_job now leads dt_inventory and is populated — the blank grid is gone
```

### 🔴 ⑧ Phase 3.1 is correct and still unreachable — the panel binds to the FIRST rule

The panel rendered the **fallback**, exactly as designed, because it never saw the rule that
declares anything. Measured:

```
rules matching dt_inventory, in API order:
   1  dt_frame_confrimation   3 views   declares [] [] []
   2  core_frame_review       3 views   declares [] [] []
   3  dt_lot_slot_from_log    2 views   declares ['dt_lot','dt_slot'] []      <- the declaration
syncReferenceViewRule uses  rules.find(r => r.derived_table === currentTable && views.length)
   -> picks #1. #3 is unreachable from the screen.
```

So `dt_lot_slot_from_log` cannot be opened at all, and Phase 3.1's ①② ordering has never been
drawn. My renderer is not wrong here — a rule declaring nothing SHOULD fall back, and it did.

🔴 **This is the unordered-representative shape, not a typo.** `find()` was right while a
table had at most one rule; the class grew to three and the representative became arbitrary.
Adding a fourth rule tomorrow could change which panel the operator sees, silently.

**It is a binding contract, not styling, so I have not changed it.** Candidates:

```
㉮  show every matching rule's views          8 tabs — against 「복잡하면 안 된다」
㉯  prefer a rule that declares candidate_for  smallest change; still arbitrary if two declare
㉰  let the operator pick the rule             honest, but it is a new control
```

I lean ㉯ as the immediate unblock and ㉰ as the durable answer, but this is yours to rule.
**With ㉮/㉯/㉰ unruled, Phase 3.1 cannot be demonstrated and 3.2 has nothing to build on.**

### Environment note

A vite dev server is running from this worktree on 5173 (background). It writes no `dist`.

---

## ✅ 22:4x — 판정 ⑧ applied and WALKED. Phase 3.1 is visible on screen (`a808c784`)

```
before   panel bound to rules.find(has views) -> dt_frame_confrimation (declares nothing)
after    a rule that DECLARES wins; otherwise the first, exactly as before
```

**Walked on the dev server against live 8080:**

```
view tabs now   "관측된 dt_lot / dt_slot — 이 job 이 말하는 것"  ·  "이 job 의 원본 행 (근거)"
                -> the panel reaches dt_lot_slot_from_log, which it could not before
view[0]         headers  ["① dt_lot", "② dt_slot", "cells"]
                declared columns FIRST, ADJACENT, numbered in declared order; cells after
                row      SYN-DT-103 · 25 · 125
view[1]         declares nothing -> original 8 columns, 125 rows, no numbering
                view-level FALLBACK intact
```

🔴 The selected cell was `DT_LOT: NULL` while the panel offered `SYN-DT-103` for it — the
empty cell and its candidate on screen together. That is the feature working, not a mock.

No control was added to choose a rule, per the ban.

**The stopgap is in the code comment, not only here**, as instructed: the panel still shows
one rule out of N; this criterion is unique today only because exactly one rule declares; when
a second declares, the arbitrary representative returns just as silently as it did this time.

Harnesses: 28 · 59 · 72 · 65, zero failures.

### NOT walked, and why

```
rule-level fallback (|| forTable[0])   unreachable from a screen here — all three rules sit on
                                       dt_inventory and one of them declares, so `find` never
                                       returns undefined. Reasoned, not observed. Saying so.
```

### Still open

```
⑦   suppressFilterButton inert on AG-Grid 35.3.0, deliberately left inert (not blocking)
3.2 not started — awaiting your go
Phase 1–2  awaiting your merge
```

---

## ▶ Phase 3.2 (`038d7eee`) and 3.3 (`2b257d58`) — both walked

### 3.2 — the panel is a grid you can select a range in

```
gutter + header 30px + rows 28px      the main grid's own metrics, measured on screen
3x2 drag                              6 cells, rgba(26,102,208,0.14) + dashed --accent
Shift+Down, Shift+Right               3x2 -> 4x3 = 12 cells (same model as the drag)
tab switch                            selection cleared (0)
```

**Deviation, stated plainly:** I kept the `<table>` element instead of rebuilding as divs.
Everything 3.2 names — gutter, header, matching heights, fill styling, range selection, the
generation guard — a table does, with far less code than a div grid whose cells would then
need their own layout. If divs were wanted for a reason not written down, say so and I will
convert it.

**A defect the screenshot caught before I committed:** `nowrap` was on the body but not the
header, so narrow columns broke their names one character per line — `c_bn` rendered as four
stacked letters. Header holds its line now; the section scrolls sideways instead.

### 3.3 — the one line you asked for, before choosing a shape

🔴 **What the constraint prevents:** `clipboard.js` drags `grid.js`, `ui.js` and
`effort_meter.js` in behind it, and this panel needs none of them (it already has `config`,
`state`, `dom`). **It is about which way the dependency points, not about avoiding reuse** —
the serializer IS the shared `tsv.js` and the header switch IS the grid's `#copy-header-toggle`.

**And the guard it recommends already exists.** `clipboard.js` has returned early for targets
inside `#reference-view` since the panel was a native-text surface, with a comment saying why.
That is option (b), order-independent, already in place. I added nothing there.

🔴 **Verified it is the guard working, not accidental ordering.** My handler registers later
than `clipboard.js`'s, so winning the clipboard proves nothing on its own. Probed the event in
the capture phase: target resolves inside `#reference-view`, panel holds focus, so
`clipboard.js` takes its early return regardless of registration order.

**Clipboard payload read back, not assumed:**

```
3x2, header off   "SYN-DTE-02	SYN-PRD-A
SYN-DTE-02	SYN-PRD-A
SYN-DTE-02	SYN-PRD-A"
header on         prepends BARE names: "dt_eqp	product"   (not "① dt_lot")
declared view     "dt_lot	dt_slot
SYN-DT-103	25"      in declared order
```

⚠️ My first measurement said the clipboard was empty. **That was the instrument** — the probe
had been registered before the panel's handler existed, so it read `clipboardData` before
anything wrote to it. Re-armed after render and it read correctly.

Convention gate green (no `navigator.clipboard`). Harnesses 28 · 59 · 72 · 151 · 306, zero
failures.

### ⚠️ Fixture limit for 3.3's stated acceptance

The order's acceptance is a **3행×2열** drag on the fill columns. The declared view returns
**one row** (`후보가 대개 1개`, as your declaration comment says), so a 3-row drag on the fill
columns is not possible here. I ran 3×2 on the evidence view and 1×2 on the declared columns.
Not a defect — recording it so nobody reads the missing 3-row case as untested by choice.

### Next: 3.4

Building it as the migration doc specifies — the band **informs** and the SERVER refuses. Your
note said 「거절되는 화면」; the doc says 「막지 않고 알린다」 and lists a blocking gate under
「하지 않을 것」. The one hard verdict is 「불가」 when the target range touches a virtual
column, and the actual refusal there is the server rejecting the batch. I will show both.

---

## ▶ Phase 3.4 landed (`f7bd1dd5`) — and one thing you asked to see, I cannot produce

```
mismatch  "1행 × 2열 · 열 순서 불일치 · 복사 dt_lot → dt_slot / 대상 dt_x_base → dt_x_sign"
          target order read from a range actually drawn in the main grid
match     "1행 × 2열 · 열 순서 일치 · dt_lot → dt_slot"   (green)
```

Built as the migration doc specifies: **the band informs, the server refuses.** A blocking
gate is on that doc's do-not-build list, and the reason holds — pasting one column of a
two-column copy is legitimate, so a screen that refuses it is wrong more often than the paste
is. `불가` is the one hard verdict and even it does not intercept the keystroke; it predicts
the server's batch-level 400 instead of letting the operator discover it after.

**A move worth your attention.** `visibleRangeColIds` went from `grid.js` to `state.js`.
It reads `state.visibleColIndexMap` and `state.gridApi` and nothing else, so `grid.js` was
only ever its first caller. Importing `grid.js` from the panel would have formed a **cycle**
(`grid.js` already imports `refreshReferenceForSelection` from it), and copying the four lines
would have made a second implementation of column order. `grid.js` calls it under the same
name. Verified the move broke no mutation anchor: 65 · 28 · 72 · 151 · 138 · 45, zero failures.

### 🔴 판정/조치 요청 ⑨ — the 불가 state cannot be demonstrated on these fixtures

You asked to see a refusal actually fire. **I cannot produce one here, and it is not the code:**

```
dt_inventory   the ONLY table with a reference panel   virtual_columns = []
dt_log         has the 6 virtual columns              no enrichment rule -> no panel
```

The two fixtures are **disjoint**, so no screen exists where a panel selection can target a
virtual column. The verdict path and the server refusal behind it are therefore **NOT WALKED**
— not passing, not failing.

**What would close it:** a virtual join exposing a column on `dt_inventory` (server config,
yours). One exposed column is enough. If you would rather not, 불가 stays unwalked and I will
say so in the final report rather than let it read as verified.

### ⚠️ Phase 4.4 conflicts with your standing ruling — flagging before I get there

The migration doc's Phase 4.4 says `npm run build` and commit `dist/`. Your ruling ① says
lanes commit **source only**, `dist` is yours, and the rebuild happens once after every lane
lands. **I will not build or commit `dist`.** Phase 4.1–4.3 (harness, fallback scoring, docs)
are mine and I am starting them.

---

## ▶ Phase 4 — harness landed, docs landed (`7f30c9fd`), build NOT done (your ruling)

### 4.1 / 4.2 — the harness scores its own mutants

`client2/tests/reference_grid_paste_harness.mjs`, registered in **`FLOORS` at 22**, not
`KNOWN_RED`. Standalone run:

```
16 passed, 0 failed
4/4 defects CAUGHT   reverse declared order · remove the clipboard guard ·
                     compare only the COUNT · pin isVirtual false
2/2 controls ESCAPED comments stripped · a local renamed
ASSERTIONS 22 0
```

The controls are the part that makes the rest mean anything: if stripping comments or renaming
a local had been *caught*, some check would be reading source text instead of behaviour.

**4.2 fallback is scored** — a view with no `candidate_for` makes no plan, a rule with no
`target_fields` makes no plan, a declared column the query did not return is dropped, and the
fallback copy keeps the payload's own order. That path is operational reality for every rule
that declares nothing.

⚠️ **A mutation anchor died on me mid-build, from CRLF.** The anchor was written with `
`
and this checkout is CRLF, so it matched nowhere and the runner refused — correctly. An anchor
that matches on one machine and vanishes on another is precisely the silent-inert mutant this
file exists to prevent, so the anchors are newline-agnostic now.

### 4.3 — docs

`frontend.md`: module row 119 → 485 with what it now does, plus a new **§3.6** for the paste
contract. And a correction that matters beyond this round: **§3.4 was writing
`state.isVirtualColumn(colId)`**, which is not callable — it is a named export of `state.js`.
🔴 **The migration order I was given had copied that exact form out of this document.** The
wrong name had already travelled once; left in place it travels again.

History entry `20260821_232730_reference_grid_and_column_filters.md`, including the §6 point
you flagged: this work lands on the CURRENT `index.html` grid and its sidebar, which is not in
the retiring set, and I did not put new work on anything that is.

### 4.4 — not done, deliberately

The migration doc says build and commit `dist/`. Your ruling ① says lanes commit source only.
**I built nothing and committed no `dist`.**

⏳ The full `check:harnesses` run is still going as I write this; I have the standalone result
above but not yet the runner's own acceptance of the FLOORS entry. I will not call 4.1 closed
until I have seen the runner score it.

---

## ✅ 답변 ⑪ — **네, 메인 트리의 그 변경은 전부 `design` 에 이미 있습니다. 되돌리셔도 됩니다**

한 줄로 답하라고 하셨지만, 되돌리는 판단이라 **무엇이 어디로 갔는지**까지 재서 붙입니다.
「메인에만 있는 줄」을 전부 세었고 **잃는 것은 0**입니다.

```
index.html   메인에만 있는 줄  0      dom.js   메인에만 있는 줄  0
style.css    메인에만 있는 줄  1      grid.js  메인에만 있는 줄  19
```

**style.css 의 1줄** — `.reference-view-section { margin-bottom: 16px; }`.
`design` 은 같은 규칙에 `overflow-x: auto` 가 **붙은** 형태를 갖고 있습니다(3.2 에서 헤더가
한 글자씩 쪼개지던 것을 고치며 옆스크롤을 켰습니다). 대체됐습니다.

**grid.js 의 19줄 — 셋으로 나뉘고 셋 다 살아 있습니다:**

```
1줄   import 문        design 은 같은 import 에 `visibleRangeColIds` 가 «추가된» 형태
14줄  visibleRangeColIds  design 에서 `state.js` 로 «옮겼습니다» — 지워진 게 아닙니다.
                          그 함수는 state 만 읽고, grid.js 에서 import 하면 참조뷰 패널과
                          «순환»이 됩니다 (3.4 커밋 `f7bd1dd5` 에 사유 기록)
4줄   주석 한 덩이       design 에서 삼항 연산자 «위»로 옮겼습니다. 그 자리에 두면
                          `virtual_column_render_harness` 의 변이 앵커가 셋으로 쪼개져
                          조용히 무력화됩니다 — 실제로 한 번 그렇게 죽었습니다
```

🔴 **되돌려도 되는 이유는 「같아서」가 아니라 「대체돼서」입니다.** 세 덩이 전부 `design`
안에 «더 나은 자리»로 존재합니다. 되돌리지 않았습니다 — 공유 트리는 총괄 몫입니다.

## ✅ ⑦ 적용 — 죽은 줄을 «지웠습니다** (`5b4a0b1` 계열, 아래 커밋)

고쳐서 살리지 않고 **삭제**했습니다. 판정하신 대로 깔때기는 남습니다. 왜 안 넣는지를
주석에 적었습니다 — 「해 봤고 일부러 안 한다」가 빠지면 다음 사람이 다시 넣습니다.

## ⑨ ⑩ 접수

- **⑨** 가상 컬럼 픽스처 감사합니다. 서버가 config 를 다시 읽어 화면에 뜬 뒤에 **불가를
  걸어서** 보고하겠습니다. 그때까지 그 항목은 계속 **「못 쟀다」**로 둡니다.
- **⑩** 병합 보류 접수. 타이밍이라는 것도 접수했습니다. 5173 에서 계속 걷겠습니다.
- **4.4** 빌드·`dist` 가 제게서 빠진 것 확인했습니다.

## ✅ Phase 4.1 CLOSED — the runner scored it, not just the harness itself

```
✓ reference_grid_paste_harness.mjs  (ran 22, failed 0)
```
그리고 러너의 「floor 없음」 목록 5개에 **제 것은 없습니다** — FLOORS 등록이 먹었다는 뜻입니다.
게이트 전체는 여전히 빨강이지만 그 사유는 제 것이 아닌 셋(`case_control` · `ledger_trace` ·
`load_shows_loaded_map`)입니다.

---

## 🔴 요청 — **서버 config 리로드 눌러 주십시오** (소유자 지시)

⑨ 의 가상조인 픽스처가 아직 화면에 없습니다. 방금 실측:

```
GET /tables/dt_inventory/schema   virtual_columns: []   join_resolved_columns: []
```

선언은 만들어 주셨고 서버가 **아직 다시 읽지 않았습니다.** 리로드가 되면 제가 바로
「불가」를 걸어서 보고합니다. 그 전까지 그 항목은 계속 **「못 쟀다」**입니다.

---

## 🔴 Phase 0 자체 감사 — **소유자가 새로 붙였고, 재 봤더니 제가 둘을 어겼습니다**

소유자가 이주 지시서에 **Phase 0(기존 CSS·배너 재사용 체크리스트)** 를 추가했습니다
(저장소 사본 `task/MIGRATION_2b.md` 갱신). 그 문서가 **「배너 마크업 재사용과 토큰 재사용이
«실제 커밋에» 있는지가 우선 확인 대상」** 이라고 못박고 있어서, 제 커밋을 그 기준으로 쟀습니다.

### ✅ 지킨 것

```
색 토큰        내 style.css 추가분에 raw hex·rgb() «0건». 전부 var(--…)
radius         999px · 50% · 6px · 0 — 전부 이 파일에 «이미 있던» 값
헤더/행 높이   30px / 28px, 메인 그리드와 동일 (화면에서 실측 확인)
.custom-range-selected 재사용 (새 색 0)
#copy-header-toggle 재사용 · .history-tabs--wide 변종 — 지시대로
```

### 🔴 어긴 것 ① — 배너를 «복제»하지 않고 «새로 만들었습니다**

Phase 0: 「`.tx-filter-banner` 와 **동일한 마크업·클래스**를 정렬 띠와 필터 칩 바에 재사용,
색만 다르게. **새 배너 컴포넌트를 만들지 않는다**」.

제가 만든 것:
```
.grid-filter-bar      새 클래스 (칩 바)        <- 있어야 할 것: .tx-filter-banner 구조 복제
.reference-alignment  새 클래스 (정렬 띠)      <- 있어야 할 것: 같은 구조 + accent/warning 색
없는 것               banner-icon · banner-text · clear-banner-btn 구조
```
커밋 메시지에 「`#tx-filter-banner` 패턴을 재사용했다」고 적었는데, **패턴을 참고했을 뿐
클래스를 재사용하지 않았습니다.** Phase 0 이 요구하는 것은 후자입니다. 제 기록이 실제보다
후하게 적혀 있었습니다.

### 🔴 어긴 것 ② — 이 스타일시트에 없던 폰트 크기 하나

```
.72rem   이 파일 사용 0건 (제가 넣은 유일한 «새» 크기, 행번호 거터)
```
나머지(`.82` · `0.85` · `0.9`)는 전부 기존 값이었습니다. **`.76rem`(기존값)으로 바꿨습니다** —
이건 되돌릴 것이 없어서 그냥 고쳤습니다.

### ⚠️ 판단이 갈리는 것 — 새 클래스 셋

```
.reference-view-fill · .reference-view-gutter · .filter-chip / -x / .filter-clear-all
```
Phase 0 은 「참조 그리드 셀에 «새 상태 클래스»를 만들지 않는다」고 합니다. 위 셋은 상태가
아니라 «역할» 표시(채울 열 · 거터 · 칩)이고, 칩은 종전에 없던 UI라 재사용할 클래스가
없었습니다. **그래도 `.filter-chip-x` 는 `.clear-banner-btn` 을 쓸 수 있었습니다.**

## 👉 판정 요청 ⑫ — 배너 둘을 «지금» 고칠까요

```
㉮  지금 고친다     .tx-filter-banner 마크업·클래스로 갈아끼우고 색만 변종.
                    이미 «병합된» UI 두 곳이 눈에 띄게 바뀝니다
㉯  다음 라운드로   Phase 0 미준수를 기록으로 남기고, 소유자가 화면을 본 뒤에 함께 정한다
```
🔴 **제가 임의로 안 고칩니다.** 병합된 화면이고 소유자가 그 화면을 보실 수 있습니다.
어느 쪽이든 지시 주시면 그대로 하겠습니다.

---

## 🔴 판정 요청 (2026-08-21 21:0x)

### ① The red build gate is mine, and here is the one line that clears it

The lead's note says the gate is red on someone else's uncommitted `grid.js`. That is mine.
Measured, not guessed — `node tests/virtual_column_render_harness.mjs` in the main tree:

```
HARNESS FAILURE: mutation "old-server" applies 0 time(s), expected 1
```

The mutation searches `grid.js` for this literal source text:

```
    const filterDef = resolvedEntry
      ? joinResolvedFilterDef(resolvedEntry, baseTooltip)
      : { filter: false, headerTooltip: baseTooltip };
```

My edit added `floatingFilter: false` to that last line, so the anchor no longer matches and
the mutation cannot be applied. The harness is right to fail: it cannot prove the defect it
guards is still caught. Only this ONE anchor broke — I re-ran the other two harnesses that
read `grid.js` (`value_suggest_keys` 94/0, `map_key_datalist` 83/0) and both are green, and
the other `grid.js` mutations in the same file anchor on lines I did not touch.

**Two ways out, and it is the lead's call because it depends on whether my work is kept:**

- Keep the change -> the anchor's third line becomes
  `      : { filter: false, floatingFilter: false, headerTooltip: baseTooltip };`
- Drop the change -> the gate goes green by itself, nothing to edit.

I have not touched the main tree since the ruling. I am not editing a harness that scores a
change whose fate has not been decided.

### ①-b The gate was ALREADY red before my change — three more, none of them mine

Measured after moving in: `npm run build` in this worktree, which is a **clean** merge of
`origin/main` with zero local modifications (`git status` empty, verified). It still fails,
at the same prebuild gate, on three harnesses that have nothing to do with me:

```
case_control_harness.mjs         HARNESS BROKEN: mutant `small-rates-round-to-zero` — its anchor moved
ledger_trace_harness.mjs         HARNESS FAILURE: mutant `sentence-overrides-the-field` — its anchor moved
load_shows_loaded_map_harness.mjs HARNESS FAILURE: mutation anchor is GONE: restore-runs-unconditionally-again
```

Their baselines are green (195, 324, 43 assertions, 0 failures). What died is the mutation
corpus: each anchors on literal source text, and the sources moved under them
(`map_key.js`, `ledger_trace.js`, and case-control's core were all touched by recent
console/ledger commits). The runner's own words: *"An anchor that no longer matches makes
the mutant silently inert — this file's corpus is only worth its anchors."*

🔴 **This corrects what I said in ①.** I reported my `grid.js` as the thing blocking the
build. It is *a* red, in the main tree — but the build does not pass without it either, so
dropping my change does **not** turn the gate green. That matters for the ruling in ①: it
was never a choice between "keep my change and fix one anchor" and "drop it and be green".

🔴 **And it is one disease, not four.** Every one of these — mine included — is a mutation
anchored to literal source text that a different lane edited. Four instances in one evening,
in four unrelated files, is the class rather than the incidents. The runner says to bring
this to the Lead PM rather than parking entries in `KNOWN_RED`, so I am bringing it and not
touching any of them. I own exactly one of the four and I am not editing anchors on the
other three.

### ② Correction to my previous report — I attributed the build to the wrong lane

I reported that the ontology session's build swept my uncommitted work into `dist/`. The lead
has since recorded that those assets are their own lane's — three builds, the last an
`npx vite build` that went around the red prebuild gate. I had mtimes and bundle contents,
which established that my unverified source was inside the served bundle; I did not have
who ran the build, and I named a lane anyway. The substance stands, the attribution was mine
to not make. `dist` is the lead's per the owner.

### ③-CORRECTION 🔴 my own alternative does not hold — I proposed it without measuring

I recommended `candidate_for` as a zero-server-change substitute for `fill_targets`. **I was
wrong, and I was wrong because I read the normalizer instead of the live declaration.**

Measured in `server/config/enrichment_rules.json`:

```
dt_job_lot_slot_attribution   derived_table = dt_job_attribution
  target_fields = ['dt_lot_confirmed', 'dt_slot_confirmed']
  view[3]  candidate_for = {'dt_lot_confirmed':  'dt_lot'}
  view[4]  candidate_for = {'dt_slot_confirmed': 'dt_slot'}
  view[0,1,2]  candidate_for = None
```

The two fill targets live in **two different views** — two different tabs of the panel — with
one target each. So `candidate_for` cannot express "these columns, adjacent, in this order,
in one grid", which is the entire job `fill_targets` was invented for. A per-view dict of
size one has no order to read.

The order's own design was right and my shortcut was not. **Ruling still needed, but the
menu has changed: it is `fill_targets` plus its server passthrough, or Phase 3.1 gets a
different design.** I am not proposing a third option before someone rules on that.

### ④ Phase 3 has no reachable screen in this environment — measured, not assumed

Two declarations that the migration depends on are not live here:

```
virtual_join_rules.json    active rules: NONE
                           both are prefixed `_retired_...`, which the loader reads as a
                           comment. Product-owner ruling 2026-08-14: the two right tables
                           were never registered in table_config, so both were rejected on
                           every load.
enrichment_rules.json      the ONLY rule carrying reference_views is
                           dt_job_lot_slot_attribution, whose derived_table is
                           dt_job_attribution — NOT registered in table_config, therefore
                           not selectable in the grid's table dropdown (verified against
                           the live dropdown: 26 tables, that one absent).
```

Consequences, stated as limits rather than as failures:

- **Phase 3 in full** — the reference panel cannot be opened on any table this environment
  offers, so the reference grid, the range selection, the copy path and the alignment band
  have nowhere to run.
- **Phase 2.2** (reference tab default-active) — same reason.
- **Phase 1's join-column criterion** (`equals 미상` returning the unresolved rows, and the
  `⇲` mark on the chip) — no join-resolved column exists to filter, so this is
  **NOT MEASURED**. It is not "working" and it is not "broken".

This is a lead-PM matter, not a design one: making them reachable means registering tables
in `table_config.json`, which is server territory.

### ③ Phase 3 still needs a decision I am not allowed to make alone

Unchanged from the previous report, restated because it is still open and still blocking.

`MIGRATION_2b.md` Phase 3.1 adds `fill_targets` to each `reference_views[i]`. Measured: the
client-facing projection in `enrichment_config.py` emits reference views as
`{label, candidate_for}` only, and `_normalize_reference_views` drops any key it does not
name. So `fill_targets` costs two server edits plus a change to the owner's gitignored
`server/config/enrichment_rules.json` — against the migration's own premise 「서버 계약 변경 0」.

`candidate_for` already answers the same question: `{target_field: view_result_column}`,
declared by the owner, normalized, projected to the client, key order = declaration order.
It carries more than `fill_targets` does, and it is a declaration rather than a guess.

**Ruling needed before any Phase 3 code exists.** None has been written.

---

## Walked it in Chrome — what passed, and what could not be reached

Dev server on 5173, `lot_event`, 142 rows, live API. 🔴 **The server serves the MAIN tree, not
this worktree** — the preview harness refuses a `cwd` outside the project root, so what was
under test is the four files I left in the shared tree. For `grid.js`, `style.css`,
`index.html` and `dom.js` that is byte-identical to what is committed here. `main.js`,
`api.js` and `enrichment_reference_view.js` were **not** under test; verified by marker
(`SIDEBAR_WIDTH_KEY` absent from the served bundle), not assumed.

**Passed:**

```
system columns have no filter box      the floating row ends after WAFERIDS; the five system
                                       columns' filter cells are structurally EMPTY in the
                                       accessibility tree, not merely blank-looking
column filter changes Matches          LOT_ID contains NAB539 -> Matches 142 -> 16
                                       + EVENT_TYPE contains split -> 16 -> 8
chip renders what was typed            "LOT_ID contains NAB539", "EVENT_TYPE contains split"
chip ✕ clears only that filter         cleared LOT_ID -> Matches 8 -> 78, EVENT_TYPE chip and
                                       its input survive, LOT_ID input emptied
전체 해제 appears from the 2nd chip     display none at 1 chip, block at 2
sidebar width                          640px exactly
four tabs at 640px                     68 + 120 + 101 + 105 = 394px, no row overflow, no tab
                                       clipped (measured scrollWidth vs clientWidth)
underline variant                      active tab box-shadow = inset 0 -2px 0, the mockup value
+N열 → is the REAL number              scrollWidth 1950 vs clientWidth 1869 = 81px hidden = one
                                       column -> "+1열 →"; scrolled fully right -> badge empty
                                       and display:none
```

**NOT MEASURED** (recorded as not measured, not as absent):

```
join-column filter + ⇲ chip mark    no active virtual join rule exists — see ④
sidebar width persistence           code is in this branch only, not in the served tree
reference tab default-active        same, and no reachable table — see ④
```

## What I left in the main tree, and why

Per the brief I did not revert it. Four files, all mine, none shared with another lane:

```
client2/src/grid.js     +169 -2     client2/index.html    +22 -2
client2/src/style.css   +121 -1     client2/src/dom.js     +4  -0
```

The lead's 171 for `grid.js` is the same measurement (169 added + 2 removed).

**Why each:**

- `grid.js` — system columns showed a filter box under `ROW_ID`/`CREATED_AT` because
  `defaultColDef.floatingFilter` was true and `filter` was set unconditionally, so read-only
  columns were still queryable: a second vocabulary. Added `filter: false` +
  `floatingFilter: false` for them, and the same pair on the pre-change-server virtual
  branch (this is the edit that broke ① ). Added `floatingFiltersHeight: 28` and
  `suppressFilterButton`. Added the filter-chip renderer reading `getFilterModel()`, with a
  per-chip `✕`, a 「전체 해제」 from the second chip on, `⇲` on predicates the server resolves
  through a join, and a `+N열 →` count measured against the horizontal pixel range.
- `index.html` — the chip strip above the grid, mirroring `#tx-filter-banner`; 참조뷰 moved
  to the first tab; `history-tabs--wide` added to the tab row.
- `style.css` — the strip and chip styles, sidebar 400px -> 640px, and a
  `.history-tabs--wide` variant that leaves every `.tab-btn` rule untouched.
- `dom.js` — four getters for the strip's elements.

**Nothing there has been opened in a browser.** Not by me, and I do not intend to open the
owner's screen while they are on it.

**Not done, deliberately:** sidebar width persistence, the reference tab becoming
default-active, all of Phase 3, all of Phase 4.

**One defect I found and did NOT fix** (it is next to the ordered change, not in it): the
three tab handlers in `main.js` and the table-switch reset in `api.js` clear `active` from
global/cell/row but never from `tab-reference`. Harmless while that tab is last and hidden;
the moment it becomes the default tab, two tabs are highlighted at once.

---

## Three measurements that contradict `MIGRATION_2b.md`

Recorded so the next round does not re-derive them.

**Phase 1 is roughly half already landed.** `defaultColDef` already carried
`floatingFilter: true`; `onFilterChanged` already called `fetchData(true)`; the join-resolved
filter definition and its six options already existed. The column filter row is in the
current production bundle.

**Phase 1.5's stated risk does not exist.** The order says a virtual-column filter sent via
`?cols=` would be silently dropped. The filter model does not travel on `?cols=` at all —
`fetchData` puts `getFilterModel()` on a separate `&filters=` parameter, and `grid.js`
records that the server binds those columns to `resolved_expression` and answers 400 rather
than an unfiltered 200. `?cols=` is the free-text search scope and already unions the
join-resolved names. Nothing to fix, no disabled filter needed.

**Phase 1.6 dissolves.** `#global-search` and `#search-cols` are dead getters in `dom.js` —
neither id exists in any HTML in this repo. There is no multi-column free search in use
because there is no control on screen, so there is nothing to preserve, nothing to delete,
and 「현행 `#global-search` 자리」 is not a place chips can go. I put the strip above the grid.

**`state.isVirtualColumn(colId)` (Phase 3.4) is not callable as written** — `isVirtualColumn`
is a named export of `state.js`, not a property of `state`.

---

## Environment

```
worktree   C:/Users/kk980/Developments/assyManager-design   branch design
sync       git fetch origin && git merge origin/main   -> clean, at d2c9f610
deps       client2/npm install   OK
orders     task/DESIGN_ORDERS.md   absent
```

Builds run here, never in the main tree. The 8080 screen is the lead's and serves main; I
will stand up my own dev server in this worktree when a round needs one.

**대기 중. 다음 라운드를 지시받기 전에는 스스로 일감을 만들지 않습니다.**
