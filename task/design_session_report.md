# Design Session — Report Channel (design session -> lead PM)

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
