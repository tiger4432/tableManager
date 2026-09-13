# Map 7b / 7c / M4 phase 1 — client half

**Agent:** map-pm · **Baseline:** `2a9f6c4` · **Date:** 2026-07-29
**Files:** `client2/src/map_editor.js`, `client2/src/transfer_plan.js`, `client2/src/transfer_plan.css`
(+ `client2/tests/map_key_canonical_harness.mjs`, `client2/tests/seam_7b_oracle.py` new;
one 4-line stub added to `client2/tests/effort_instrument_harness.mjs` — see §5)
**Not committed.** Not a single write reached a live database; every check below is offline.

---

## 1. What changed (3 lines)

- **7b** — one client-side canonicaliser (`canonicalKeyValue`, mirror of `map_overlay.canonical_key_value`) now backs every map-identity composition and decomposition in the client: `getMapIdFromMeta`, `buildKeyFilters`, `addOverlayForSource`, `addOverlayLayer`, and the panel's material→map routing.
- **7c** — the material rollup reads the server's `transfer_untracked` / `remaining_upper_bound` and renders `≤N` for both 가용 and 잔여, through one pair of functions shared by both render paths; the client performs no bound arithmetic of its own.
- **M4①** — `valid_die_ref` is parsed, resolved through the existing overlay primitives, and consulted at the three valid-die decision points; `getWaferBoundingBox` deliberately stays on circle geometry, and Push now carries the declaration forward instead of erasing it.

---

## 2. StableDevelopmentProtocol §1 side-effect checklist

**Coordinate system / geometry — the one that mattered.**
`getWaferBoundingBox` computes the bbox by scanning the valid-cell set, and `getVisualCoords` turns that bbox into **the x/y values written to the database**. Feeding the valid-die mask into it would silently reinterpret every stored coordinate — screen fine, values wrong. So the mask is applied at the three *consumer* sites (`getGridCellObject`, `renderGridCanvas`, `getEdgeClassification`) and **never** in `getWaferBoundingBox`, which still calls `isCellInsideWaferFast` directly (verified: `map_editor.js:1703`). Escalated as a phase-2/3 decision (§6-C).

**Frame window (`physFrameOverride`).** `isValidDieAt` suspends the mask whenever a frame window is open. Inside `withPhysFrame` the code is solving the *source* map's coordinates; applying this map's stencil there would cut one map with another's. Pinned by a mutation (`M10`) and by a harness assertion.

**Shared mutable state.** New module state `validDie`. Every path that changes which map is on the canvas resets or restores it: `loadExistingMap` (reset at entry, so cancel/0-row/exception paths cannot leave a stale mask), `switchTable` (same reasoning the overlay clear already uses), and `snapshotEditorState`/`restoreEditorState` (a material-map round trip would otherwise return the parent map cut by the child's stencil). Snapshot ordering verified: `openMapFrame` snapshots before the child's load.

**Timing.** `resolveValidDie` is awaited *before* `renderGridCanvas` on the load path — placing it after would paint one frame with the wrong valid-die set. `resolveValidDie` contains `await`s but never runs inside `withPhysFrame` (that restriction is unchanged and still respected).

**Render cost.** `renderGridCanvas` now computes `getPhysicalCoords` before the `isMatrixCell` early-out instead of after. It is pure arithmetic, viewport clipping still runs first, and the duplicate later call was removed — so the net extra work is one cheap call for the visible cells that fall outside the 3×3 matrix window.

**Server/client contract.** No endpoint, payload, or WS event shape changed. `/tables/{t}/schema` is now read for `column_types` as well as `map_key_columns` — same request, same response, one cached call per table (`fetchMapKeySpec`).

**Scale.** Nothing new is unbounded. The `valid_die_ref` cell fetch reuses `OVERLAY_CELL_LIMIT` (2000) and **demotes truncation to a refusal** — a truncated set is a silently *smaller* valid-die set, which is invisible on screen.

**Layering.** `transfer_plan.js` gets the canonicaliser through the injected controller rather than a local copy; a second copy would be a second opinion about map identity, which is the defect this round removes.

---

## 3. Invariants — what was proved and how

Four independent instruments. Counts are assertions, not runs.

| Instrument | Result |
|---|---|
| `client2/tests/map_key_canonical_harness.mjs` | **114 passed, 0 failed** |
| `client2/tests/seam_7b_oracle.py` (imports the **live** `server/map_overlay.py`) | **PASS — 30 vectors**, declared-type differential 5 |
| Client scored against the seam agent's `contracts/map_seam/vectors.json` | **83 matched, 0 diverged**; `missing symbols: none` |
| Mutation check (defect put back, 11 variants) | **11/11 caught** |

**INV-7b-1** — `LOT_01` / `LOT_1` / `LOT_ 1 ` / `LOT_1.0` / numeric `1` all compose to `LOT_1` when slot is number-declared. The fixture is asserted to **activate the defect axis**: exactly 3 of the 5 spellings were composed wrong by the old raw join, and that count is asserted (not `>0`), so a fixture that quietly stops exercising the defect fails rather than going green.

**INV-7b-2** — the two declared types are asserted to **differ**: `'01'`→`'1'` under `number`, `'01'`→`'01'` under `string`, and `'01'`≠`'1'` as map ids under `string`. Undeclared behaves as `string`. Mutation M1 (ignore the declared type) is caught.

**INV-7b-3 — the seam, and the point of the round.** `seam_7b_oracle.py` imports `server/map_overlay.py` and compares **key→value**: 21 canonicalisation vectors, plus 9 decomposition vectors driven through the server's *real* `build_key_filters` (a recording stub model captures what each column was compared against — the server's split and canonicalisation run unmodified). **The oracle was shown to go red**: pointed at a client with the pre-7b canonicaliser it reports 7 divergences, the first being literally the production bug — `client 'LOT_01' vs server 'LOT_1'`. It also refuses to pass if the declared-type differential is 0.

**INV-7b-4** — decompose∘compose is the identity, checked **key→value per column** (not just round-trip, which a defective `f` and its own inverse both survive), plus `canonicalMapKey` idempotence. Verified for the tail-absorption case (`A_B_2`), a lot containing `_`, single-column keys, and undecomposable keys.

**INV-7c-1** — `boundText` renders `≤N`, including `≤0` and negative bounds. The seam contract's own derived negative is satisfied: where a bound exists the text contains `≤` **and** is not equal to the bare number. Mutation M6 (bare number) is caught.

**INV-7c-2** — only the JSON boolean `true` is a declaration. `'true'`, `'false'`, `1`, `'none'`, `'None'`, `'NONE'`, `null`, `''`, `false`, absent — all stay 미상. Every non-`true` vector carries a real bound in the payload precisely so a truthy implementation would render `≤12` and get caught; mutation M5 does exactly that and is caught.

**INV-7c-3** — the client never computes `total − fail`. `untrackedBoundOf`'s only numeric source is `remaining_upper_bound`; a vector supplying `total: 999, fail: 999` alongside `remaining_upper_bound: 34` must still yield 34. For 잔여 the subtraction goes through the **single existing implementation** (`doe_bands.remainingState`), fed a synthetic exact input and labelled `≤` — so the confirmed and bound branches cannot drift apart the way `ceil`/`round` once did. Mutation M7 (client recomputes) is caught.

**INV-M4-1 — zero regression, measured.** Scored against the seam contract's `mask_baseline_cases`, which were **measured out of the `2a9f6c4` git blob**. Two modes were run over the same vectors: the raw circle mask, and `isValidDieAt` with no declaration. **They agree on every single case** — my insertion is the exact identity when nothing is declared. Separately, the harness asserts pass-through over 75 (x, y, verdict) pairs including a state carrying stale keys. Mutation M11 (stale keys leak) is caught.
> 22 matched / 4 diverged in that group: the 4 are 2 cases × 2 modes, both failing **identically in both modes**. Running the same scorer against the `2a9f6c4` blob gives *the same 2 divergences* — they are pre-existing and are a real defect, diagnosed in §6-A.

**INV-M4-2** — with a resolved ref the mask decides in **both directions**: in-mask + circle-says-outside → valid, and not-in-mask + circle-says-inside → **invalid**. Checking one direction only would pass an implementation that ORs or ANDs the two, i.e. "circle still participates". The fixture is asserted to contain a cell where mask and circle disagree. Mutations M9 (OR with circle) and M10 (mask leaks into the frame window) are both caught.

**INV-M4-3** — one rule, so there is no arbitrary line: **only `null`/absent means "no declaration"; everything else is a declaration, and an unreadable one is refused with a stated reason.** `''`, `'   '`, `5`, `true`, `['t','k']`, `{table}` with no map id, `{map_id: '  '}` → refusal, each carrying a non-empty reason. Resolution-time failures (binding unresolved, `fallback_guess`, referenced spec absent, cell fetch failed, truncated, 0 cells, grid-size mismatch) all land in basis `unresolved` with the reason surfaced in **three places** — toast, a persistent status chip, and `console.warn`. Mutation M8 (fold unreadable into absent) is caught.

**Seam-shape agreement (unprompted).** I had to choose the `valid_die_ref` shape without seeing the server half. It converged exactly with `server/map_overlay.parse_valid_die_ref`: `{table, map_id}` with `table` optional, the `{target_table, map_key}` alias, and a bare string inheriting the home table. The seam contract's two **declared** client/server divergences (`object_no_table_no_home`, `string_no_home`) both match my client's recorded expectation.

---

## 4. Complexity budget

| | |
|---|---|
| New interactive controls | **0** (verified: 0 added lines containing `addEventListener`/`<button`/`<input`/`<select`/`confirm(`/`alert(`) |
| New panels / modes / modals | **0** |
| New passive indicators | **+1**, conditional |
| Confirmations added to a read path | **0** |
| Duplicated render logic removed | **−2** |

The one addition is a status chip that reuses the existing `plock-chip` class and sits next to the existing paint-lock chip in the status bar. It is **created only when needed and hidden whenever the basis is `circle`** — so for every map in production today (none declare `valid_die_ref`) the screen is unchanged. The two removals: 가용 and 잔여 were each rendered by duplicated inline expressions in `renderMaterialPane` and `notifyPaintCounts`; both now call one function each, so a bound cannot appear in one path and vanish in the other mid-paint.

No HTML was edited (`map_editor.html` untouched).

---

## 5. Note on `effort_instrument_harness.mjs`

`pushMapData` now reads `validDie` (to carry `valid_die_ref` forward), so that harness's vm sandbox raised `ReferenceError`. I added **4 lines**: `validDie: null` to its state stubs, with a comment. Nothing in the instrumentation logic was touched — `commitIfRecorded` stays gated on `effort_recorded`, and the harness's own mutation suite (M1–M7, including the unconditional-reset mutant) passes: **28 passed, 0 failed**. With `validDie: null` the pushed payload is byte-identical to `2a9f6c4`, which is what every assertion in that file assumes.

---

## 6. Escalated — needs your decision, not mine

### A. 🔴 Pre-existing silent defect: a declared `edge_margin` of **0** becomes **3.0 mm**

Found by the seam contract's measured baseline; **present at `2a9f6c4`, not introduced here.** I did not fix it.

```js
function physNum(key, domEl, dflt) {
  ...
  const v = domEl ? parseFloat(domEl.value) : NaN;
  return v || dflt;          // <- parseFloat('0') === 0 is falsy, so 0 becomes dflt
}
```

`edgeMargin`'s default is `3.0`, and **0 is a legitimate declared value** (no edge exclusion). Measured: `wafer_dia 20, edge_margin 0` should give `effectiveRadius 10`; the client computes **7**. The mask shrinks from a 7-cell disc to a 5-cell diamond.

Blast radius (all pre-existing):
- `map_editor.js:1680` `getWaferBoundingBox` → **bbox → visual coords → the x/y actually stored**
- `map_editor.js:1741` `getTransformedPhysicalConfig` → the valid-die mask (paintable/pushable cells)
- `map_editor.js:2105`, `:4471` → **writes `phys_edge_margin: 3.0` into `wafer_map_metadata` for a map that declared 0**
- `map_editor.js:5626` `resolveFrame`, and the `physFrameOverride` branch of `physNum` (`ov || dflt`) → a **source map whose stored meta says 0 is read as 3.0**, silently misaligning overlays

Only `edgeMargin` is harmful: `offsetX/offsetY` default to `0` (`0 || 0` is fine), and `waferDia`/`chipX`/`chipY`/`cols`/`rows` are invalid at 0 anyway.

**Why I did not fix it in this round:** the fix changes `effectiveRadius`, which changes `getWaferBoundingBox`, which changes `getVisualCoords`, which changes **the coordinates written to the database**. That is a coordinate-changing edit and must not ride along with an additive round. It also needs a data question answered first: *which stored maps carry `phys_edge_margin: 0`, and were their coordinates written under the 3.0 assumption?* Proposed fix is a one-line `Number.isFinite(v) ? v : dflt` in `physNum`/`gridDimNum` plus the two write sites, but it needs its own round and a data audit. Queuing this is yours.

### B. 🟠 `contracts/map_seam/client_harness.mjs` is broken and cannot score the client

It crashes at line 247 on `spec.client_symbols.remaining_display.fn` — `remaining_display` is **not defined** in its own `vectors.json` v2, whose `$comment` instead says the axis is "scored through the two functions that decide it: `untrackedBoundOf` and `boundText`" (both present, both declared `live`, both passing). The harness code and its vectors are out of sync. I did **not** edit it — it is the seam agent's file. My scoring above used the symbol table the vectors do declare; `missing symbols: none`.

Two coverage gaps in the same file, for the seam agent:
- `client_symbols` has no entry for the client's mask decision point (`isValidDieAt`) or basis reader (`validDieBasis`), so **INV-M4-1 and INV-M4-2 are currently unscored on the client side** by their harness. I scored them by loading those two explicitly.
- `valid_die_basis_cases` specifies `resolve_valid_die_basis(meta, resolver, table) -> {basis, source, reason}` with `source in circle|ref|refused`. My client exposes `validDieBasis() -> circle|map|unresolved` plus the network-bound `resolveValidDie`. **Same three states, different names, and mine is not resolver-injectable.** If the seam wants that exact signature I can refactor `resolveValidDie` to take an injected cell-resolver — say the word.

### C. Two M4 decisions I deliberately left to phase 2/3

1. **The bbox stays circle-derived** when a `valid_die_ref` resolves (reasoning in §2). Phase 3 ("retire the circle from `inside`") has to settle whether the valid-die map should also define the coordinate frame. It cannot be settled additively, because it changes stored coordinates.
2. **`unresolved` does not block Push.** I refuse the *consumption* loudly and persistently, and leave `2a9f6c4` behaviour otherwise, because blanking the wafer would make the map uneditable and "never let a validation path destroy the user's work" outranks loudness. Blocking Push under `unresolved` is defensible and would need a fifth gate in `pushMapData` — which you told me not to disturb. Your call.

### D. Pre-existing, unrelated: `client2/tests/split_registry_harness.mjs` is dead

Fails with `const DEFAULT_LEGEND not found`. `DEFAULT_LEGEND` is absent from `map_editor.js` at `2a9f6c4` too (removed by U6 `95bf072`), so this harness has been silently non-running since then. Not mine, not touched — but it is a harness whose green nobody can cite because it never runs.

---

## 7. Living-doc update points (doc-keeper's, not mine — I edited no docs)

Rows found in `docs/process/DOC_OWNERSHIP.md` by the code paths I touched.
`docs/spec/MAP_EDITOR_SPEC.md` and `docs/map_editor/architecture_and_management.md` are **already modified in the working tree by another agent** — these are additions to coordinate with, not conflicts to resolve.

| Code path (DOC_OWNERSHIP row) | Living doc | What now needs saying |
|---|---|---|
| 맵 정렬 메타 (`wafer_map_metadata`) | `spec/MAP_EDITOR_SPEC.md` **§5.0** | The 7b note's closing line — "클라 측 대응은 별도 착지 예정" — **has landed.** Client implementation is `canonicalKeyValue` + `composeMapId`/`decomposeMapKey`/`canonicalMapKey` in `map_editor.js`, mirroring `map_overlay.canonical_key_value`; the client key now arrives canonical rather than opaque. Worth recording the two deliberate JS/Python deviations (boolean stringification; Python's `1_0` digit separator) since a future reader will otherwise treat them as drift. |
| 웨이퍼 맵 에디터 | `spec/MAP_EDITOR_SPEC.md` §1~§4 · `map_editor/README.md` | **New M4① section**: the valid-die basis is now tri-state (`circle`/`map`/`unresolved`); the decision point is `isValidDieAt` and it is consulted at exactly three sites; **`getWaferBoundingBox` deliberately stays circle-derived** and why (bbox → visual coords → stored x/y). §2 state-variable list gains `validDie`. |
| 맵 정렬 메타 | `map_editor/architecture_and_management.md` **§2.3** (`grid_metadata` 표준 필드 표) | Add the `valid_die_ref` row: type `object \| string`, `{table?, map_id}` with the `{target_table, map_key}` alias, bare string inherits the map's own table; `null`/absent = no declaration; anything else unreadable is refused, never folded into absence. Also: Push preserves the field verbatim (it is not editable in the UI this round). |
| 범용 맵 오버레이 | `spec/MAP_EDITOR_SPEC.md` §5.1 | The source key is canonicalised before use in `addOverlayLayer`, which is what makes the cell filter and the meta lookup agree — the asymmetry that produced "data opens, metadata looks absent". |
| 본딩·전사 계획 엔진 | `spec/MAP_EDITOR_SPEC.md` **§6.2-bis** · `guide/DOE_GUIDE.md` | §6.2-bis says "클라는 `미상` 대신 `≤N`을 렌더할 수 있습니다" — it now **does**, in both 가용 and 잔여, via `untrackedBoundOf`/`boundText`, and only on the exact boolean `true`. DOE_GUIDE is user-facing and should show what the operator sees: `≤N` plus the tooltip "기전사 미차감이라 실제 잔여는 이 값 이하입니다". |
| — (new test assets) | — | `client2/tests/map_key_canonical_harness.mjs` and `client2/tests/seam_7b_oracle.py` are new and unlisted; the oracle is the only thing in the repo that compares client and server canonicalisation against the live server implementation, so it is worth a line wherever the other harnesses are catalogued. |

---

## 8. Proposed memory entries (for your review — not self-applied)

- **Trap:** a `|| default` guard on a numeric DOM/config read silently discards a legitimate **0**. Where 0 is a meaningful declared value (edge margin, offsets, thresholds), this is a silent data defect, and if the value feeds a bounding box it reaches stored coordinates.
  **Right way:** `Number.isFinite(v) ? v : dflt`. Audit every `|| dflt` on a parsed number by asking "is 0 a legal declaration here?"
- **Trap:** a shared canonicaliser is worthless if only one side has it. Self-consistent round-trip tests on the client passed throughout the 7b outage.
  **Right way:** an oracle that **imports the other side's real implementation** and compares key→value — and it must be shown to go red against the known-defective version before its green counts.
- **Trap:** inserting a decision function in front of an existing predicate looks additive but silently changes every consumer of that predicate, including ones that derive coordinates.
  **Right way:** enumerate the predicate's call sites and classify each as "asks the question I am changing" or "derives the coordinate system". Never change the second kind in an additive round.
