# QA — V1 core-value instrument, LANE B (browser E2E, isolated stack :8081)

**Verdict: GO-WITH-FIXES** — the instrument is arithmetically faithful, invisible, gate-safe,
reload-durable and correct on failure/retry, all proven live. It is **blind on three of the six
screens**, and every one of those blind spots under-counts, i.e. flatters the score — the one
direction the module's own invariant #3 forbids, on a baseline that can never be recollected.

Reviewer: qa-reviewer (LANE B). Contract/server analysis intentionally left to LANE A.
Environment: `devenv.py up` → `ASSY_DATA_ROOT=dev_env/`, DB `assy_qa`, API `127.0.0.1:8081`.
Live `:8080` and `server/config/` were never touched. Baseline for "introduced vs pre-existing": `b697d34`.

---

## 0. WHAT I ACTUALLY TESTED — read this before using the rest

The working tree **changed underneath this review, mid-run**:

| artifact | mtime | contains |
|---|---|---|
| `client2/dist/assets/effort_meter-BLrYbTcJ.js` (served) | 08:03:45 | `commit()` on `res.ok` |
| `client2/src/effort_meter.js` | 08:30:36 | `commitIfRecorded(resBody)` gated on `effort_recorded` |
| `client2/src/api.js`, `map_editor.js` | 08:30–08:31 | `commitIfRecorded` call sites |

All browser evidence below is against the **08:03 build**, which is what the server serves and what
`npm run build` produced. It is not the current `src/`. See finding **F2**.

Also: `client2/src/admin.js` and `client2/admin.html` are now modified (+60/+21). They were **not**
in the scope I was given and they do **not** import `effort_meter`. Scope drift — attribute before merge.

---

## 1. Mandatory standard scenario — step-by-step result

| # | Step | Result |
|---|---|---|
| 1 | Create a bonding map + DOE | **PASS** |
| 2 | Edit the dt map | **PASS** |
| 3 | Remaining quantities + map presence reflected in rollup | **PASS (qualified)** — see below |

**Step 1.** Created `bonding_map · QALB01` through the real UI: triple-clicked the map-key field,
retyped the key, pressed `⚡ Push Map Data`. Both confirms fired in the correct order; 67 cells
landed. The DOE/legend panel rebound to `bonding_map · QALB01` and the split-registry write followed.
The rows are visible in the grid afterwards (`QALB01_17_17`, `base=QALB01`, …) and in Audit History.

**Step 2.** Opened the material row `LOT-A_05:1` from the rollup → the `dt_map` material frame pushed
(breadcrumb `bonding_map · AAA › dt_map · LOT-A_05`), drag-painted a region with a real trusted
mouse drag (canvas pixel signature changed 4958654 → 5154273), pushed 1323 cells. Persisted.

**Step 3 — qualified PASS.** The rollup renders exactly what the server answers and does not
fabricate. `GET /api/transfer-plan/source-summary?stage=bonding&lot=LOT-A&scope=slot&bins=1&slot=05`
returns `200` with `chips.total=0, transferred=540, remaining=null, remaining_reliable=false`; the UI
shows `잔여 미상` plus the explicit "미상은 0이 아닙니다" note — the honest, core-value-#3-correct
rendering. `MAP 0` is likewise truthful: the painted legend value `F` has no material token bound to
that pool in this snapshot. **This is a data/declaration state of the isolated snapshot, not a
regression** — `client2/src/transfer_plan.js`, which owns rollup rendering, is not in this diff at
all. I did **not** manufacture a non-null `잔여`; the `bonding` stage (not `dt`) drives this rollup
and only the `dt` stage carries a `bin_map` in the isolated env. Flagged as **not fully proven**
rather than claimed as green — see §4.

No console errors on any page except the two I injected myself.

---

## 2. Confirmed defects (severity order)

### F1 — HIGH · Three screens have no collector; every return trip is silently free
`client2/src/graph_viewer.js`, `client2/src/admin.js`, `client2/src/trace.js` do not import
`effort_meter.js`. Only `main.js:104`, `map_editor.js:666`, `enrichment.js:753` install counting.

The anchor graph is asymmetric:
- `index.html` → `/graph.html`, `/admin.html` — **counted** (grid side owns the delegated listener)
- `graph.html` → `/`, `admin.html` → `/`, `trace.html` → `/` and `graph.html` — **not counted**

**Proven live, trusted mouse click.** On `/graph.html` with counters `{key:0, mouse:1, nav:1}` I
physically clicked `🏠 Main` at (663,34). The browser landed on `/`. Counters afterwards:
`{key:0, mouse:1, nav:1}` — **unchanged**. The full page load that destroyed the entire working
context scored **0**, and the physical press was not even counted as a mouse event.

Failure scenario: an operator mid-correction jumps to the graph viewer to check a lot's lineage,
clicks around for 30 presses, returns, and saves. Truth = 2 navs + 30 mouse = 10 + 90 = 100 points.
Recorded = 1 nav + 0 mouse = 5 points. The correction is billed at **5% of its real cost**.
Direction is always flattering, never inflating. `effort_meter.js:39` explicitly forbids exactly this.

Recommendation: either instrument the three pages (`startSession` + `installGlobalListeners` +
`installNavLinkCounting` is three lines each and adds no UI), or — if they are declared out of scope
as non-correction surfaces — make that a written declaration in `docs/guide/config/effort_metric.md`
so the baseline's known blind spot is on the record rather than discovered later. Silence is the one
option that cannot be repaired, because this metric is not retroactively computable.

### F2 — HIGH · Tracked `dist/` no longer matches `src/`
`client2/dist/assets/main-CCAUl23m.js` and `map_editor-s-0h_UdU.js` contain **0** occurrences of
`commitIfRecorded` / `effort_recorded`, while `client2/src/effort_meter.js:438` and its call sites
(`api.js:325`, `map_editor.js:4403`, `enrichment.js:496`) use them. `dist/` is a git-tracked build
artifact, so committing this tree ships instrumentation that differs from its source of record — and
the newer `commitIfRecorded` gate (the fix for "server returned 200 but did not persist the effort")
would be **absent in production while present in the code everyone reads**.

Failure scenario: the server accepts a batch but skips the effort write; the shipped bundle still
calls the ungated `commit()`, wipes the counters, and that correction's cost is lost forever.

Recommendation: rebuild before commit, and re-run LANE B against the rebuilt bundle — the browser
evidence in this report does not cover `commitIfRecorded`.

### F3 — MEDIUM · `getConfig()` is tree-shaken out; the instrument's health is unobservable in the field
`effort_meter.js:229` documents `getConfig()` as "Diagnostics only. Lets QA distinguish 'config
arrived and is empty' from 'config failed'." **No file imports it.** Rollup drops it: the built chunk's
export map is `export{T as a,E as i,b as n,y as o,v as r,h as s,n as t}` — seven exports, all consumed
(ROUTES, startSession, installGlobalListeners, installNavLinkCounting, countNav, snapshot, commit).
`grep -c "loaded:" dist/assets/effort_meter-BLrYbTcJ.js` = **0**. Confirmed at runtime: calling the
export throws `TypeError: EM.t is not a function` (`t` is `ROUTES`).

Consequence: in production nobody can tell "the served allowlist really is empty" from "the config
fetch failed and we silently fell back to empty." Both look identical from the outside, and the whole
stated purpose of the export is to separate them. On a metric that cannot be recollected, losing the
only self-diagnostic is worse than it sounds.

Recommendation: expose it on one page (`window.__effort = getConfig` behind the existing debug
console, or a `console.debug` line at boot). No UI — the invisibility rule is not threatened.

### F4 — MEDIUM · The "query-time re-interpretation" claim is over-stated, and self-transitions are unresolvable
`effort_meter.js:41-44` claims classification "is a query-time interpretation rather than an
irreversible collection-time decision." Only half true. The **bucket** (`nav` vs `nav_preserved`) is
chosen at collection time and only two aggregate integers are stored — the transition identity is
not. So you can re-**weight** the two buckets later, but you can never re-**classify** an individual
transition.

This bites because two of the emitted keys are self-transitions:
`map_editor > map_editor` (`map_editor.js:797` — table switch) and the identical key from `btnLoadMap`
(map load); likewise `enrichment > enrichment` (`enrichment.js:759`). A table switch and a map load are
semantically different moves that emit the **same** key, so an operator who exempts one necessarily
exempts the other, and afterwards the data cannot be separated again.

Today this fails safe (shipped allowlist is empty ⇒ both counted). It becomes unrecoverable the moment
someone declares that transition. Recommendation: either give the two moves distinct sub-context ids
(`map_editor:table_switch` / `map_editor:map_load`), or soften the comment to state the real guarantee.

Note also a third convention in the same round: `main.js` uses sub-context ids for within-page moves
(`grid:table`, `grid:viewmode`, `grid:log_jump`) while `map_editor`/`enrichment` use identity
self-transitions. Three conventions for one allowlist is an operator trap.

### F5 — LOW · The client accepts a config shape the server will never serve
`effort_meter.js:81-101` (`parseTransitions`) accepts `["from>to", ...]` string entries as well as
objects. I injected a config containing `"grid>enrichment:rule"` into the isolated env; the served
response dropped it. That branch is unreachable through the real serving path. It fails **safe**
(dropped ⇒ counted), but a config author following the client's own comment gets a silently ignored
line. Recommendation: delete the string branch or document that only the object form is served.

### F6 — LOW · New subsystem has no `DOC_OWNERSHIP` row, and no QA checklist item
`docs/process/DOC_OWNERSHIP.md` has **zero** rows mentioning the effort instrument; its only change
this round is the unrelated `map_meta_registrar` row. A subsystem spanning `client2/src/effort_meter.js`
+ `server/effort_metric.py` + `server/config/effort_metric.json` + `docs/guide/config/effort_metric.md`
now exists with no ownership entry, so the next agent touching a save path has no way to learn which
docs to update. `docs/qa/FEATURE_CHECKLIST.md` was edited this round but gained **0** effort items —
no regression guard for an instrument whose defects are silent by construction.
(`docs/architecture/frontend.md` does cover `effort_meter` — 4 mentions. That part is fine.)

---

## 3. Falsified — attacked and found safe

Each line: the hypothesis, then the evidence that killed it.

**Attack 1 — invisibility. SAFE.** Hypothesis: something rendered. `effort_meter.js` contains zero
DOM-mutating calls; the built chunk has **0** matches for
`createElement|innerHTML|appendChild|preventDefault|stopPropagation` (3441 bytes total). At runtime on
`map_editor.html`: 382 elements, **0** matching `effort|meter|instrument|telemetry|keystroke` on id/class/
testid, and **0** text hits for `effort|키 입력|클릭 수|세션 점수|score` in `document.body.innerText`.
Same on the grid and enrichment pages. No badge, no toast, no panel, no control.

**Attack 2 — behaviour preservation. SAFE.** Hypothesis: capture-phase listeners reorder or swallow input.
- Drag-paint: real `left_click_drag` on the wafer canvas painted (pixel signature changed); the whole
  drag cost **+1 mouse** (mousedown only), not one per cell.
- Hover: `Cursor: (20, 18) = 2` updated on hover, and hover added **0** to any counter.
- Cell selection: `double_click` opened the AG-Grid inline editor (`.ag-cell-inline-editing`,
  `INPUT.ag-input-field-input ag-number` focused) and cost exactly **+2 mouse** (two presses).
- Keyboard entry: pressing `9` put `9` in the editor **and** added exactly **+1 key**. `Enter`
  added +1 and committed the edit into Tx mode. Bare `Shift` added **0** — modifier exclusion works.
- Triple-click = **+3 mouse**. Physically honest, no inflation.
- Console: no errors originating from the instrument.

**Attack 3 — gate order and placement. SAFE.** Hypothesis: instrumentation can be reached past a gate.
`effort: effortSnapshot()` is built at `map_editor.js:4375`, inside the payload literal at 4366 —
after the last gate `return` (4317). Every gate returns before it. Live proof with a dialog recorder:
with the map key changed to `QALB01` while the identity pin held `AAA`, `⚡ Push` fired the
identity-mismatch confirm **first**; declining produced **0 network requests** and left the counters
untouched (`key:2, mouse:6, nav:0`). Accepting produced exactly the documented order
(mismatch confirm → Clean Replace confirm) and then the two writes.
Reporting points are exactly as claimed, verified per-request:
`wafer_map_metadata` PUT → `hasEffort:false`; `map_split_registry` PUT → `hasEffort:false`;
target-table cell PUT → `hasEffort:true`. One human action, billed once.

**Attack 4 — reload survival + tab death. SAFE.** Hypothesis: a mid-correction reload restarts the human.
Before reload `{session_id: 856cfb2b-…, key:0, mouse:3, nav:1}`; after a full page reload of
`map_editor.html`, **byte-identical**, same `session_id`. The reload itself was not miscounted as a nav.
A brand-new tab on the same origin got a **different** `session_id` (`9faa070e-…`) with zeroed
counters — session scope is the tab, so closing it ends the session.
(Sub-note, benign: `trace_launch.js` uses `window.open`, and Chrome copies `sessionStorage` into a
window opened that way, so the trace tab briefly carries the opener's `session_id` and counters.
Harmless — `trace.js` has no collector, so it can never commit them.)

**Attack 5 — reset only on success. SAFE.** Hypothesis: a failed save erases the effort, or a retry
double-bills. Forced a `TypeError` on the `dt_map` cell PUT. Result: alert `데이터 적재 실패`, counters
**preserved** at `{key:0, mouse:4, nav:1}`. Removed the block, pressed Push again: success, counters
reset to 0, and the DB gained **exactly one** row — `(id=2, key=0, mouse=5, nav=1, nav_preserved=0)`,
i.e. the accumulated effort including the failed attempt's click, billed **once**. Not twice, not zero.

**Attack 6 — draft survival. SAFE.** Hypothesis: instrumentation disturbed `scheduleCellDraft` or the
load-path precedence. Painted cells → `map_doe_draft::bonding_map::QALB01` changed (1239 → 1182 bytes).
Reloaded → key still present at 1182 bytes, map key restored to `QALB01`, and the DOE panel came back
showing `bonding_map · QALB01` with legend value `F` (43 cells) and the material rollup intact.

**Attack 7 — counting sanity. SAFE (within the covered pages).** Every count I could attribute was
1:1 with a physical act. The decisive end-to-end proof is DB row 3:
`(key=2, mouse=7, nav=3, nav_preserved=1)` — exactly the sequence I performed (2 keydowns `9`+`Enter`;
6 presses + the Apply click; frame push + pop + one uncounted-config-era move; one preserved transition).
No double-counting on a single click anywhere; no keystroke attributed to the wrong unit.
Boot paths correctly abstain: `restoreLastOpenMap`, `loadTablesList`'s initial pick and the
`?rule=` deep link all call the shared functions directly and scored **0**. Re-selecting the *same*
enrichment rule via `refresh-btn` scored **0**, as documented, while a genuine rule change scored **+1**.
A cancelled/failed map load scores 0 — `loadExistingMap` returns `{cancelled:true}` / `{error:true}` /
`{empty:true}` / `{count, mapKey}` and the handler's `if (r && !r.cancelled && !r.error)` covers all four.

**Attack 8 — config fail-closed. SAFE, proven live.** Hypothesis: a broken config fails open into
"score 0". Two layers verified.
- *Server:* corrupt JSON, and a directory in place of the file, both return **HTTP 200** with
  `context_preserving_transitions: []` — i.e. everything counted. Hot-reload works with no restart.
  A `{"from":"*","to":"grid"}` entry was **rejected**, not silently kept as an inert literal.
- *Client, the real test:* I served a config that **declares** `map_editor ↔ map_editor:material` as
  context-preserving (verified: with it live, a frame push landed in `nav_preserved`, `nav` unchanged).
  Then I loaded the actual production chunk into a same-origin `srcdoc` realm with `fetch` forced to
  **reject** for `/api/effort/config`, and fired those same two declared-preserving transitions.
  Result: `nav 1 → 3`, `nav_preserved` **unchanged at 1**. Both declared-preserving moves fell back to
  **context-losing**. The score inflates, never deflates; nothing was discarded; the page did not break.

---

## 4. Needs runtime verification I could not complete

1. **The 08:30 revision is entirely untested in a browser.** `commitIfRecorded` gated on the server's
   `effort_recorded` flag changes the reset condition — the single most safety-critical line in the
   module. `dist/` was never rebuilt, so no browser has ever run it. Re-run attacks 3/5/7 after a build.
2. **Server-side effort on a *server-rejected* batch.** I could only force a client-side network
   throw. The case "server returns 500/400 *after* accepting the effort" is LANE A's contract; if the
   server can persist effort on a batch it then rolls back, the retry double-bills. `main.py:2089-2096`
   gates on `tx_for_effort`, which looks correct, but I did not exercise it.
3. **Step 3 of the standard scenario with a non-null `잔여`.** The isolated snapshot has
   `chips.total=0` for `LOT-A_05` on the `bonding` stage, and only the `dt` stage carries a `bin_map`.
   I verified the rollup faithfully renders the server's `remaining:null / remaining_reliable:false`
   and refuses to print `0`; I did **not** see a numeric remaining change in response to my edit.
   Someone with a seeded tape-total identity should close this.
4. **Auto-repeat keystroke cost.** Every `keydown` does a synchronous `JSON.stringify` +
   `sessionStorage.setItem`. At ~30 Hz auto-repeat that is 30 blocking writes/second. I saw no
   perceptible latency, but I did not profile it on the target intranet hardware.
5. **Real multi-tab operator behaviour.** Two tabs = two sessions = two rows in a "per-session
   average". Semantically defensible, but it is a measurement decision nobody has ratified.

---

## 5. Documentation consistency

- `docs/architecture/frontend.md` covers `effort_meter` — good.
- `docs/process/DOC_OWNERSHIP.md` — **no row for the new subsystem** (F6).
- `docs/qa/FEATURE_CHECKLIST.md` — edited this round, **0** effort entries (F6).
- Over-claim: `effort_meter.js:41-44` "query-time interpretation rather than an irreversible
  collection-time decision" (F4). The bucket choice *is* made at collection time.
- Over-claim: `effort_meter.js:13-16` "THIS IS THE ONLY COLLECTOR IN THE CODEBASE." Accurate as
  written, but it reads as "everything is collected." Three of six screens collect nothing (F1).
  Recommend the header state the covered set explicitly.

---

## 6. Proposed lessons for `agent_workspace/memory/qa-reviewer.md`
(proposal only — not written by me)

- **함정**: 클라 계측을 검수할 때 계측이 *설치된* 파일만 보면, 계측이 *없는* 화면이 만드는 비대칭
  누락을 놓친다. 왕복 이동의 절반만 세면 점수는 조용히 좋아진다.
  **올바른 방법**: 페이지 간 앵커 그래프를 전수로 그려 **양방향** 모두 수집기가 있는지 대조한다
  (`grep -l effort_meter src/*.js` 와 각 HTML의 `<a href>` 목록을 교차).
- **함정**: 브라우저 E2E 도중 구현 에이전트가 소스를 고치면, 서버가 서빙하는 `dist/`와 `src/`가
  갈라진 채 "검증 완료"로 보고하게 된다.
  **올바른 방법**: 착수 시각과 종료 시각에 대상 파일 mtime을 기록하고, 보고서 첫 문단에
  **어떤 빌드를 실측했는지** 명시한다.
- **함정**: 번들러가 호출부 없는 export를 tree-shake 하므로, "QA용 진단 훅"이 소스에는 있는데
  프로덕션 번들에는 존재하지 않는다.
  **올바른 방법**: 진단 API는 소스가 아니라 **빌드 산출물에서** 존재를 확인한다.

---

## 7. Environment left as found

Isolated stack still up on `:8081`. My injected `dev_env/config/effort_metric.json` was **removed**;
the endpoint is back to serving defaults with an empty allowlist. Isolated *data* was intentionally
mutated by the scenario: `bonding_map · QALB01` created, `dt_map · LOT-A_05` replaced (1323 cells),
one `bonding_map` cell edited via Tx mode, and three rows in `interaction_effort_logs`.
Live `:8080` and `server/config/` untouched throughout.
