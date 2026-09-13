# Client — N4 (`?cols=` dropdown) and H3 (admin init on the grid page)

**Commits:** `b54b7b4` (N4). **H3: no commit — see below, it does not reproduce.**
**Files touched:** `client2/src/api.js`, `client2/src/state.js`,
`client2/tests/virtual_column_render_harness.mjs`, `client2/scripts/check_harnesses.mjs`.
Nothing under `server/`, `docs/`, `client2/dist`, `map_editor.js`, `map_key.js`,
`split_registry_row.js`, `client2/tests/map_key_*` or `contracts/map_seam` was opened or edited.

---

## N4 — done, but it is inert until a missing control comes back

### Where the list comes from now

`loadSchema` (`client2/src/api.js`) builds the scope select in two passes: the stored
columns exactly as before, then the entries of `/schema`'s **`join_resolved_columns`** that
are not already in `state.currentColumns`.

**Why that announcement and not `virtual_columns`.** I checked the server rather than
trusting either the board or the existing comment. `?cols=` is scoped by
`apply_search_filter` (`server/main.py:1412`), and at `main.py:1440` a column is resolved
through the join iff `col in binder`, where the binder's vocabulary is
`virtual_join_executor.exposed_columns` (`main.py:1355`) — collide **and** virtual_only.
That is the exact set `/schema` publishes as `join_resolved_columns` (`main.py:2128`).
`virtual_columns` is the narrower key and says nothing about any `collide` name. This is
the same choice `grid.js:456` already makes for the column filter, for the same stated
reason, so N4 follows an existing precedent instead of inventing a rule.

**The stale comment that said the opposite.** `api.js:134-137` claimed virtual names have
"no storage for the SQL to reach", and `state.js:12-13` listed the search dropdown as a
consumer of `currentColumns` for that reason. Both were true before `cd3e0f4` and are false
now. Both were corrected; leaving them would have been a documented lie in the two files
that define this rule.

### What happens when the announcement is absent

Nothing is fabricated, and the fallback is the pre-change behaviour: stored columns only.
That is not a stylistic preference — a name the client invents is one the server has no
expression for, and such a scope is **refused with HTTP 400**, not answered with the whole
table. Measured against the live server: `?cols=no_such_col` → `HTTP 400`.

Three absence shapes are handled and each is scored: key absent (old server), key present
but `[]` (no join on this table), and malformed entries (`null`, no `name`, empty `name`) —
skipped individually rather than allowed to produce an option whose value is `undefined`.
The non-array case was already normalised to `[]` at `api.js:130`.

### Read-only-ness is not affected

The select is read by exactly four sites — `fetchData` (`api.js`), the export in `main.js`
(x2) and `timeline.js` — and every one puts the value into `?cols=` of a **READ**. There is
no edit path on this element. Editability is decided by `isVirtualColumn` inside the write
funnels (`clipboard.js` x3, `ui.js`), which never look at this select, and enforced by
`crud.refuse_virtual_join_columns` on the server. Widening the select therefore cannot make
a read-only column look editable anywhere. To make the read-only-ness *visible* rather than
merely harmless, the joined entries carry the `🔗` marker `grid.js` already uses in the
column header — on the **label only**; `option.value` stays the bare name sent to the
server, and that separation is scored.

Also handled: the announcement is **wider** than what is missing, so it is differenced
against the stored list. A `collide` name is a stored column already emitted by the first
pass; appending the announcement wholesale would put two identical options in the select
that build the identical query.

### 🔴 The finding that matters more than the fix: the control does not exist

The brief located the defect at `api.js:134-140`, and that code is now correct. But **the
dropdown it builds is not on the grid page at all.**

- `client2/index.html` contains no `#search-cols` **and no `#global-search`** — a
  case-insensitive grep for "search" over the file returns nothing, and `git log -S` shows
  `search-cols` was never in that file.
- Verified in the live DOM after full init (`http://localhost:5173/index.html`):
  `getElementById('search-cols')` → `null`, `getElementById('global-search')` → `null`.
- Both `dom.js` getters (`dom.js:3`, `dom.js:4`) are therefore **residual** — the same
  `smart-paste-btn` pattern already in the client-pm memory file. A sweep of all 55 `dom.js`
  getters against `index.html` finds exactly four residuals: `globalSearch`, `searchCols`,
  `ingestFileBtn`, `smartPasteBtn`.

Consequences: `elements.searchCols` is always null, so the builder body (old and new) never
runs on the grid page; and because `elements.globalSearch` is null too, `q` is always empty,
so the `?q=`/`?cols=` search feature has **no UI whatsoever**. Grid searching today happens
only through AG-Grid column filters (`?filters=`), which already handle virtual columns
correctly (`grid.js:456`, server `apply_column_filters`).

So the board's symptom — "a user cannot pick a joined column to search on" — is real, but
the cause is not the list-building code. **Restoring the search box + scope select is a UI
decision I did not take unilaterally**: it is a new visible control, which the standing "UI
simplicity first" rule and the ui-designer split both put outside my lane. Requesting a
ruling from the Lead PM.

**I proved my new lines actually execute** rather than declaring victory on an unrun path.
Injecting a `#search-cols` element into the live page (the `dom.js` getter resolves lazily,
so the next `loadSchema` populates it) and switching to `dt_log` — the one live table with a
declared join — produced, in order:

```
"" | All Columns
dt_cell_key … graph_synced_at            (19 stored columns, unchanged, no marker)
dt_lot_confirmed | dt_lot_confirmed 🔗
dt_slot_confirmed | dt_slot_confirmed 🔗
core_frame | core_frame 🔗
dt_frame | dt_frame 🔗
```

And the resulting scope is a real filter, not a silent full-table answer — measured on live
`dt_log` (8700 rows):

| request | total |
|---|---|
| no scope | 8700 |
| `q=미상&cols=dt_lot_confirmed` | **8340** |
| `q=zzzznope&cols=dt_lot_confirmed` | **0** |
| `q=x&cols=no_such_col` | **HTTP 400** |

---

## H3 — not reproducible; I did not fabricate a guard

The brief asked for a page guard on admin bootstrap code that "runs on a page that has no
admin DOM, and throws". **That code does not exist in the current tree, and the throw does
not occur on any page.** Adding a guard to an entry point that never runs would have been a
fix to nothing, so I stopped and am reporting instead.

Evidence:

1. **`admin.js` is loaded by exactly one page.** Mapping every HTML entry point to its
   scripts: `admin.html → src/admin.js`, `index.html → src/main.js`,
   `enrichment.html → enrichment.js`, `graph.html → graph_viewer.js`,
   `trace.html → trace.js`, `map_editor.html → map_editor.js`. One script per page, no
   sharing. `admin.js`'s bootstrap is a `DOMContentLoaded` handler at `admin.js:305`, which
   the grid page never loads.
2. **No admin bootstrap leaks into a shared module.** A case-insensitive grep for `admin`
   across `client2/src/` outside `admin.js` returns only comments, the `ROUTES.ADMIN` route
   id, and the `/admin.html` path key in `effort_meter.js`. All admin-token code
   (`X-Admin-Token`, `assy.adminToken`, the gate) is confined to `admin.js`.
3. **The one admin-conditional block on the grid page is already guarded and its DOM
   exists.** `main.js:121-127` computes `isAdmin` and enters only `if (isAdmin &&
   elements.graphSyncBtn)`; `#graph-sync-btn` is present at `index.html:47`.
4. **Browser-verified clean consoles**, errors-only filter, six page loads:
   grid, grid with `?user=admin` (which forces `isAdmin` true), admin, enrichment, graph,
   trace — plus the built bundle served at `http://127.0.0.1:8080/`. Zero errors on all of
   them. (The grid page's only console noise is pre-existing AG-Grid v32 deprecation
   warnings, unrelated.)
5. **The "harness sandbox" reading was tested too**, since H3 sits in the board's
   harness/structure section beside H1 and H2. Only two harnesses mention admin
   (`effort_meter_harness.mjs`, `retroactive_view_harness.mjs`); neither loads `admin.js`
   into a DOM-less sandbox and both are green (131 and 263 assertions).

The board's H3 row points at "위 진단 참조" — a diagnosis that is no longer anywhere in
`PROJECT_STATUS.md`. Given board item P1 (the board carries stale lines, and one already
caused a reversed risk call), the most likely reading is that H3 is stale. **Recommend
closing it, or re-opening it with a reproduction.**

---

## Verification

**Harnesses — before and after are identical, with one deliberate rise.**

| | before | after |
|---|---|---|
| total / gated / known-red / exit | 23 / 18 green / 5 / 0 | 23 / 18 green / 5 / 0 |
| `virtual_column_render_harness.mjs` | 59 | **65** (+6) |
| every other harness | — | ASSERTIONS identical |

No floor was lowered and no harness was moved onto the debt list. The one floor edit raises
`virtual_column_render_harness.mjs` 59 → 65 so the new coverage is protected, which is what
the runner itself prompts for on a rise.

**New scoring** (7 checks added, 1 replaced): `1d` stored-then-announced ordering, `1e` no
name offered twice, `1f` absent announcement → stored only, `1g` empty announcement →
stored only, `1h` malformed entries skipped, `1i` values carry no decoration, `1j` only
join-resolved names are marked. The old `1c` ("stored columns only") asserted the behaviour
the board asked to change and was replaced, not deleted silently.

**Five new mutants, all caught**, keeping this file's rule that a check which cannot fail
proves nothing: regression to stored-only; appending the announcement without differencing
it; building from `virtual_columns` instead of the announcement; letting a malformed entry
through; leaking the `🔗` marker into `option.value`. Both control mutants (local rename,
comment stripping) still escape. Total: 28/28 defects caught, 0 escaped.

**All 6 contracts pass** (exit 0): `band_arithmetic` (82), `blank_predicate`,
`config_resolve_report` (32 files), `doe_band_rules`, `legend_map_scope` (71), `map_seam`.

### ⚠️ A transient red from the concurrent map lane — not mine

One mid-run sweep showed `valid_die_frame_adoption_harness.mjs` flip from its known-red
`ran 228, failed 42` to **BLOCKING** with `HARNESS FAILURE: 'fitGridToMask' is gone from
map_editor.js`. Attribution: that harness reads **only** `client2/src/map_editor.js`
(`SRC_PATH`, line 36) and cannot see any file I touched; `map_editor.js` was modified at
`08:50:21`, after my `api.js` edit at `08:47:40`, by the live refactoring lane. The final
sweep shows it back at `ran 228, failed 42` — it was a mid-save snapshot. Flagging it
because the map lane should know its harness goes dark between saves.

## Notes for the Lead PM

- **Decision needed (N4):** restore the search box + scope select to `index.html`, or accept
  that `?q=`/`?cols=` has no UI and retire the four residual `dom.js` getters. As it stands
  the N4 fix is correct but unreachable by a user.
- **Decision needed (H3):** close as stale, or supply a reproduction.
- `dist` was not rebuilt and not touched, per instruction — `api.js` and `state.js` changed,
  so `client2/dist` is now behind on this round.
- A `doc-keeper` hook fired during this session (37 commits since the last doc pass). I did
  not touch `docs/` per instruction; flagging it for scheduling.
- **Proposed memory lesson (client-pm):** *"보드가 지목한 줄이 맞아도 그 UI가 실존하는지
  먼저 확인하라."* The existing `smart-paste-btn` lesson says a `dom.js` getter does not
  prove the UI exists; this round shows the same trap one level up — a task can name a
  correct file and line while the control it describes is absent from the page, so the fix
  lands on a path no user reaches. Confirm the element in the HTML **and** in the live DOM
  before accepting the framing of the defect.
