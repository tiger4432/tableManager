# Design Session — Report Channel (design session -> lead PM)

> Lead PM writes to `task/DESIGN_ORDERS.md`. That file does not exist yet — on origin or in
> the working tree. The owner has told me to work under lead PM control, so this is the
> doorbell asking for it.

---

## 🔴 판정 요청 (2026-08-21 21:0x) — three, the first is urgent

### ① The ontology session's build swept my uncommitted work into `dist/`

Measured, not inferred:

```
20:51:33  client2/src/grid.js       <- mine
20:51:41  client2/src/dom.js        <- mine
20:53:24  client2/src/style.css     <- mine
20:53:30  client2/index.html        <- mine
20:55:52  dist/assets/main-DlUVbgcq.js + style-BJgac6KN.css   <- their build
```

`grep -c 'grid-filter-bar|offscreen-cols|history-tabs--wide'` returns 1 in BOTH new bundles,
and `dist/index.html` loads exactly those two files. So the bundle the server serves now
carries my **half-finished, browser-unverified** filter bar and 640px sidebar.

I have touched nothing to correct this. No stash, no checkout, no reset — the tree also holds
their `ontology_explorer*` edits and the server sessions' `server/` edits.

**Ruling needed:** who commits `client2/dist/`, and whether my client changes should be
reverted out of the next build or finished and verified first. I would rather finish and
verify than have a partial screen land, but that is the lead PM's call, not mine.

### ② No orders exist for this session

`task/DESIGN_ORDERS.md` is absent. The owner handed me a migration order directly
(`MIGRATION_2b.md`, imported from their Claude Design project) and I began Phases 1–2 under
it. If that order is not the lead PM's intent, say so and I will stop where I am.

### ③ Phase 3 needs a decision I am not allowed to make alone

The migration's Phase 3.1 adds `fill_targets` to each `reference_views[i]`. Measured: the
client-facing rule projection in `enrichment_config.py` emits reference views as
`{label, candidate_for}` only, and `_normalize_reference_views` drops any key it does not
name. So `fill_targets` requires **two server edits plus a change to the owner's gitignored
`server/config/enrichment_rules.json`** — while the migration's own stated premise is
「서버 계약 변경 0」.

There is an existing primitive that answers the same question with zero server change:
`candidate_for` is already `{target_field: view_result_column}`, already declared by the
owner, already normalized, already projected to the client, and its key order is the
declaration order. It carries MORE than `fill_targets` — which reference column feeds which
target — and it is a declaration, not a guess.

**Ruling needed:** `candidate_for` (no server change, honors the premise) or `fill_targets`
(server change, needs an owner + server-session round). I have not written any Phase 3 code.

---

## What I measured before writing anything

Four statements in the migration order do not match the code as it stands today. Reporting
them rather than implementing around them.

**Phase 1 is roughly half already landed.**
`defaultColDef` already carries `floatingFilter: true`; `onFilterChanged` already calls
`fetchData(true)`; the join-resolved filter definition and its six options already exist with
their reasoning intact. The column filter row is in the CURRENT production bundle.

**Phase 1.5's stated risk does not exist.** The order says a virtual-column filter sent via
`?cols=` would be silently dropped. Measured: the filter model does not travel on `?cols=` at
all — `fetchData` serializes `getFilterModel()` onto a separate `&filters=` parameter, and
`grid.js` records that the server now binds these columns to `resolved_expression` and
answers 400 rather than an unfiltered 200. `?cols=` is the free-text search scope and it
already unions the join-resolved names. Nothing to fix; no disabled filter needed.

**Phase 1.6 dissolves.** `#global-search` and `#search-cols` are dead getters in `dom.js` —
neither id exists in `index.html` or in `dist/index.html`. There is no multi-column free
search in use because there is no control on screen. So there is nothing to preserve and
nothing to delete, and 「현행 `#global-search` 자리」 is not a location the chips can occupy.
I put the chip strip above the grid instead, mirroring `#tx-filter-banner`.

**`state.isVirtualColumn(colId)` (Phase 3.4) is not callable as written.** `isVirtualColumn`
is a named export of `state.js`, not a property of the `state` object. Whoever writes Phase 3
must import it.

**One defect adjacent to the ordered change.** The three tab handlers in `main.js` and the
table-switch reset in `api.js` remove `active` from global/cell/row but never from
`tab-reference`. Harmless while the reference tab is last and hidden by default; the moment
Phase 2.2 makes it the default tab on rule-bearing tables, two tabs are highlighted at once.
It is the ordered change that makes this reachable, so I count it as part of Phase 2 rather
than as a bonus fix. Not yet applied.

---

## State of the work — uncommitted, unverified in a browser

Phase 1 (partial) and Phase 2 (partial), in `client2/src/grid.js`, `src/dom.js`,
`src/style.css`, `index.html`:

- system columns get `filter: false` + `floatingFilter: false` (they show filter boxes today)
- `floatingFiltersHeight: 28` + `suppressFilterButton`
- filter chips read off `getFilterModel()`, with per-chip `✕` and a 「전체 해제」 that appears
  from the second chip on; `⇲` marks a predicate the server resolves through a join
- a `+N열 →` count measured against the horizontal pixel range, re-measured on scroll, grid
  resize and column resize
- sidebar 400px -> 640px; `.history-tabs--wide` underline variant; 참조뷰 moved to first tab

Not done: sidebar width persistence, the reference tab becoming default-active, the
`tab-reference` reset defect above, all of Phase 3, all of Phase 4.

🔴 **Nothing here has been walked in a browser yet.** I did not start a preview because the
owner is working on the authoring screen and the served bundle is currently entangled with
another session's build (①).
