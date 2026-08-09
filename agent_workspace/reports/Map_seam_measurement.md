# map_editor.js refactoring — Round 1 (first half): seam measurement

**Author**: map-pm · **Date**: 2026-08-04 · **Scope**: read-only measurement of `client2/src/map_editor.js` (9,632 lines at HEAD+worktree). No product code changed. Method: AST parse via `vite.parseAst` (oxc, already in `client2/node_modules` — no install needed), scope-aware reference walker, spot-checked against source by hand (3 functions, see §7).

---

## 1. Headline numbers

| measure | value |
|---|---|
| total lines | 9,632 |
| top-level functions | **235** (7,716 LOC inside functions) |
| module-level state declarations (`let`/`var`/mutable `const`) | **92** (58 genuinely mutable after excluding frozen-shape consts) |
| top-level non-function statements | 2 (`DOMContentLoaded` wiring at L797–866, `themechange` listener at L3332) |
| imports | 9 modules (config, theme, utils, **transfer_plan**, **doe_bands**, tsv, effort_meter, 2 CSS) |
| `fetch(` call sites | **24, scattered across 21 functions in 10 of 17 candidate seams** |
| files that slice `map_editor.js` source by symbol name | **19 test harnesses + 5 contract harnesses + 1 server test** (`test_install_product_tables.py` scans it for `updates:` literals) |

Two dead-state findings (same defect class as the `validDieListCache` incident cited in the ruling):

- `let tables = []` (L38) — **zero readers, zero writers.** Dead declaration.
- `let isMouseDown` (L44) — **written twice in `initMouseDragEvents` (L1361, L1431), never read anywhere.** Write-only state.

Neither needs a round; both are one-line deletions for whichever round first touches their neighborhood.

## 2. Partition — 17 candidate seams, measured

Members per seam are in Appendix A. Boundary metrics ("out calls" = call edges leaving the seam; "shared st" = mutable module state the seam touches that at least one other seam also touches; "hostage files" = harness/contract/server-test files that slice at least one of the seam's symbols by name from `map_editor.js` source text — every one of them must be re-pointed in the same round that moves the seam):

| seam | fns | LOC | out calls | in calls | shared st | hostage files |
|---|---|---|---|---|---|---|
| **map-key** (canonical identity, L644–786) | 6 | 97 | **0** | 9 | **1 (read-only)** | 3 (see §4) |
| datalist-suggest (L8659–8873) | 11 | 169 | **0** | 4 | 3 | 1 |
| paint-lock (L60–260) | 10 | 121 | 1 | 17 | 7 | 6 (1 fn each) |
| geometry-presets (L2751–3157) | 9 | 340 | 7 | 12 | 6 | 4 |
| legend-registry (L262–660 + L4087–4480) | 30 | 509 | 9 | 33 | 13 | 3 + 1 server test |
| edge-batch (L6135–6350) | 6 | 198 | 16 | 6 | 6 | 2 (1 fn each) |
| clipboard (L6352–7260) | 23 | 696 | 20 | 2 | 8 | 3 (35 fn slices) |
| legend-panel-ui (L3159–3260 + L3781–4800) | 14 | 381 | 20 | 35 | 8 | 8 |
| draft-restore (L3829–4080 + L7289–7443) | 15 | 315 | 20 | 43 | **25** | 7 |
| canvas-render (L3263–3770) | 12 | 470 | 15 | 37 | 15 | 6 |
| push (L5674–6130) | 3 | 449 | 17 | 1 | 15 | 3 |
| frame-stack (L7261–7694) | 12 | 218 | 24 | 7 | 17 | 2 |
| valid-die (L2455–2750 + L8037–8657 + L8874) | 15 | 794 | 28 | 20 | 15 | **13** |
| overlay (L7696–9632, minus valid-die/suggest) | 30 | 803 | 37 | 28 | 12 | 9 |
| coord-transform (L1762–2445) | 18 | 472 | 3 | **54** | 10 | **10** |
| map-load (L4804–5640) | 8 | 818 | 39 | 15 | 19 | 3 |
| dom-wiring (L788–1770 + DOMContentLoaded) | 13 | 866 | 49 | 8 | 22 | 5 |

Reading notes:

- **coord-transform has only 3 outgoing calls but 54 incoming and 10 hostage harness files** — it is the file's load-bearing wall, confirming the ruling's prohibition on taking it first from a second, independent axis: moving it re-points 10 harnesses in one round, before the re-pointing method has ever been exercised.
- **dom-wiring / map-load / push are orchestrators** — their outgoing references shrink automatically as leaf seams leave (each departed callee becomes an import). They should never be "extracted"; `map_editor.js` remains the orchestrator module.
- `el` (the DOM element registry, 57r/29w) was counted as state but is DOM access, not data; seams whose shared-state count is dominated by `el` (datalist-suggest, edge-batch) are cheaper than the raw number suggests.

## 3. The ruling's bias vs. the measurement

The standing ruling biases round 1 toward **server IO or DOE/legend**. The numbers:

**Server IO is not a chunk — it does not exist as an extractable seam.** 24 `fetch` sites live inside 21 functions spread over 10 seams; the three biggest IO holders are the three biggest functions in the file (`loadExistingMap` 663 LOC, `resolveValidDie` 519, `pushMapData` 432), and their IO is interleaved with orchestration. Extracting "server IO" as round 1 means either (a) a thin wrapper module (~100 LOC moved, near-zero decomposition value, but edits **21 functions across every seam** — the maximal merge-conflict footprint, which is the opposite of what the refactoring is for), or (b) carving IO out of the giant orchestrators, which is the most expensive operation available. **The numbers say: drop server IO as a round-1 candidate.**

**DOE/legend is real and viable but mid-cost**: legend-registry = 509 LOC, 9 outgoing edges (4 into draft-restore: `saveDoeDraft`/`clearDoeDraft`/`cellsDigest`/`getCurrentMapKey`; 3 into renderers), and a 7-variable legend state cluster (`legend`, `legendMeta`, `legendDirty`, `legendConflict`, `legendReplaceScope`, `legendSaveState`, `legendVocabularySeed`) that is **also written from map-load, frame-stack, draft-restore and push** — so the round must export mutable-state accessors, not just functions. Additionally its dedicated tests harness `split_registry_harness.mjs` is **currently on the KNOWN_RED debt list ("throws at its extraction step … since 2026-07-30")**, and the server test `test_install_product_tables.py:687` scans `map_editor.js` for the `split_key` `updates:` literal and must be retargeted in the same round.

**The cheapest seam by every measured axis is map-key** (canonical key values, section "[7b]" L644–786): 6 functions, 97 LOC, **zero outgoing calls** (the six call only each other), one shared-state touch (`getMapIdFromMeta` **reads** `tableSchema`, never writes — becomes one parameter or one imported getter), 9 incoming call edges from 5 seams (become imports), 3 hostage files. It is also "outermost" in the dependency sense that matters: a pure leaf with server parity (`composeMapId`/`decomposeMapKey` mirror `server/map_overlay.compose_map_id`/`build_key_filters`), as far from the coordinate contract as anything in the file.

**Recommendation: round 1 = map-key.** This deviates from the bias's letter ("server IO or DOE/legend") while serving its stated rationale exactly — "prove the method in a cheap spot, then go to the expensive ones." Round 1's real deliverables are the *method*: symbol move + harness re-pointing + the module-load smoke (ruling precondition 2) + per-round oracle run. map-key is the cheapest place in the file to prove all four, and it is the only seam with an **independent cross-side oracle already built** (§5). Lead PM adjudicates; if the bias stands as written, legend-registry is the DOE/legend candidate and its extra costs are itemized above.

## 4. Round-1 (map-key) exact bill of materials

Move: `canonIntString`, `canonicalKeyValue`, `composeMapId`, `decomposeMapKey`, `canonicalMapKey`, `getMapIdFromMeta` + consts `CANON_INT_RE`, `CANON_FLOAT_RE` (L665–786, 97 LOC + comments).

- **State**: `tableSchema` read-only in `getMapIdFromMeta` → pass as parameter (call sites: map-load, push, draft-restore already hold it) or import an accessor. Nothing left behind; nothing taken that others write.
- **Incoming refs to re-import** (9 edges): draft-restore (`getCurrentMapKey`), map-load, push, valid-die (`resolveValidDie`, `enterValidDieAuthoring` area), overlay (`addOverlayLayer`), top-level wiring.
- **Hostage files (3)**: `client2/tests/map_key_canonical_harness.mjs` (slices all 5 pure fns; **116/116 green today, verified this session**), `client2/tests/valid_die_authoring_harness.mjs` (slices the same 5 as dependencies; on the debt list at 98/1 — re-point must not change its count), `client2/tests/seam_7b_oracle.py` (reads `CLIENT_SRC = client2/src/map_editor.js` and delegates to the canonical harness).
- **Coverage gap**: `getMapIdFromMeta` is the one member no harness slices. Round 1 must either extend the canonical harness to it or cover it via the new module-load smoke.
- **Duplication check**: clean. `composeMapId`↔server is a **contract seam, not a duplicate** — `DUPLICATION_LEDGER §3` rules this class out of the ledger explicitly (same-answer seams get vectors, not merging; D-3/D-8 document the server-side pair). Moving the client half to its own module creates no third implementation.
- **Complexity budget**: 0 added controls / 0 removed. No UI change in this or any round.

## 5. Oracle readiness (recommended seam)

- **Per-round stored-coordinate oracle** ("0-cell movement, cells carrying their own coordinates as values — never matched by physical key"): map-key touches no coordinates, so the oracle's expected delta is structurally 0 — which is exactly what makes it a clean first exercise of the per-round routine. The measuring machinery already exists and is value-carrying, not key-matched: `seatingSnapshot`-based harnesses (`standard_frame_origin`, `geometry_origin_reseat`, `valid_die_origin_alignment`) record each cell's `dbX`/`dbY` as values. Round procedure: run `npm run check:harnesses` + `check:contracts` before and after; the green set and per-harness assertion counts must be identical (ruling precondition 1 — the `ASSERTIONS ran/failed` line protocol — should land in this round; it is ~15 runner lines + 1 line per harness).
- **Seam-specific oracle — already independent and mutation-proven**: `client2/tests/seam_7b_oracle.py` imports the **live** `server/map_overlay.py` and compares client vs server canonicalization key→value (no reimplementation on either side), and has a `SEAM_CLIENT_ROOT` switch expressly for pointing it at a deliberately broken client to show it goes red. This is the strongest oracle attached to any seam in the file. Run: `conda run -n assy_manager python client2/tests/seam_7b_oracle.py`.
- **Gate wiring**: both `client2/tests/*.mjs` (via `check_harnesses.mjs`, exit-code only, 5-entry KNOWN_RED debt list) and `contracts/*/client_harness.mjs` (via `check_contracts.mjs`) run at `prebuild` — a broken slicer fails the build loudly. The blind spot is precondition 1's "red with 0 assertions vs red with N": two of this seam's three hostages are green/near-green today, so the re-point is verifiable by exact counts (116/0 and 98/1) even before the protocol lands.
- **Verdict: the recommended seam is the best-covered non-coordinate seam in the file.** No change to what round 1 must include beyond the two ruling preconditions, one of which (module smoke) becomes satisfiable for the first time *because* this round creates the first importable module.

## 6. Decision-ready round order (re-measure after each round — orchestrator numbers shrink as leaves depart)

| round | seam | LOC | out calls | shared mutable | hostage files | note |
|---|---|---|---|---|---|---|
| 1 | **map-key** | 97 | 0 | 1 read-only | 3 | proves method; independent cross-side oracle exists |
| 2 | **legend-registry** | 509 | 9 | 13 (7-var legend cluster needs accessors) | 3 + 1 server test | satisfies DOE/legend bias; must revive debt-listed `split_registry_harness` and retarget `test_install_product_tables.py:687` |
| 3 | paint-lock | 121 | 1 | 7 (`loadedFCells` ownership decision) | 6 (1 fn each) | single-gate lock predicate, mostly read-only |
| 4 | datalist-suggest | 169 | 0 | 3 (DOM-dominated) | 1 | cheap but low value; can swap with 3 |
| 5 | edge-batch | 198 | 16 (all into stable leaves) | 6 | 2 (1 fn each) | |
| 6 | clipboard | 696 | 20 | 8 | 3 (35 fn slices) | big LOC win; hostages are green and enforced |
| 7 | geometry-presets | 340 | 7 | 6 | 4 | |
| 8 | canvas-render | 470 | 15 | 15 | 6 | |
| 9 | valid-die | 794 | 28 | 15 | 13 | contract-covered (`contracts/map_seam`); only after method is routine |
| 10 | coord-transform (+ frame helpers) | 472 | 3 | 10 | 10 | the forbidden-first seam; last of the moves |
| 11 | overlay | 803 | 37 | 12 | 9 | depends on 10 (frame/projection chain) |
| — | dom-wiring, map-load, push, draft-restore, legend-panel-ui, frame-stack | 3,047 | — | — | — | stay in `map_editor.js` as the orchestrator; extracting orchestrators is negative-value until their callees are modules |

## 7. Methodology and self-check

- Parser: `vite.parseAst` (oxc). Walker tracks function/block/loop/catch scopes; writes counted for direct assignment, update expressions, member assignment rooted at the variable, and mutating method calls (`push`/`set`/`splice`/…). Known approximations: member-mutation attribution is at the object root; `el` counted as state though it is the DOM registry.
- Spot-checks against source (key→value, not self-consistency): `composeMapId`/`decomposeMapKey`/`canonicalMapKey` — confirmed 0 out-of-seam calls by reading L712–757; `getMapIdFromMeta` — confirmed reads `tableSchema`, calls only `composeMapId` (L758–786); `saveLegendToServer` — confirmed measured out-edges `clearDoeDraft`, `saveDoeDraft`, `renderLegendMetaOnly`, `cellsDigest` + `draftBase` write against L4340–4358. Dead-state findings (`tables`, `isMouseDown`) confirmed by direct grep.
- Harness hostage counts came from quoted-name scanning of `client2/tests/*.mjs`, `contracts/*/client_harness.mjs`, and `server/tests/*` (the `.py` hostages were found by a separate path-reference grep — the `.mjs`-only scan undercounted map-key's hostages 2→3; corrected).

## 8. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. `vite.parseAst` (oxc) is importable from `client2/node_modules/vite/dist/node/index.js` — full AST measurement without installing anything.
2. Before moving any symbol out of `map_editor.js`, enumerate hostage files first: harnesses slice by name from the source *text*, and one server test (`test_install_product_tables.py`) scans it for write-payload literals — the hostage set is not limited to `client2/tests`.

## 9. Doc update points (doc-keeper's, listed only)

- `DOC_OWNERSHIP.md` rows 42/58/59/74/75 name `client2/src/map_editor.js` as the code path; each extraction round must add the new module path to the affected row (round 1: row 42's "legend 저장 = 유일한 기록자" is untouched; the map-key module joins rows 58/74/75 wherever `getMapIdFromMeta`/`composeMapId` are cited).
- `CODE_MAP.md` anchors for moved symbols (code-mapper's lane).
- `DESIGN_TRACKS.md` refactoring section: replace the 6-hypothesis candidate list with this measured 17-seam table (lead-PM owned board).

---

### Appendix A — Full function inventory (grouped by candidate seam)

**paint-lock** — 10 functions, 121 LOC

| fn | lines | LOC |
|---|---|---|
| `isLockedValue` | 71–78 | 8 |
| `isOverlayLocked` | 81–86 | 6 |
| `paintLockMessage` | 88–90 | 3 |
| `isProtectedFCell` | 93–95 | 3 |
| `applyPaintLockConfig` | 98–110 | 13 |
| `normalizeServedBinding` | 132–142 | 11 |
| `fetchServedBinding` | 148–156 | 9 |
| `fetchPaintRules` | 168–214 | 47 |
| `updatePaintLockIndicator` | 217–231 | 15 |
| `recomputeLockedCells` | 234–239 | 6 |

**legend-registry** — 30 functions, 509 LOC

| fn | lines | LOC |
|---|---|---|
| `defaultLegendRows` | 262–266 | 5 |
| `declaredLegendRow` | 271–275 | 5 |
| `buildSplitKey` | 314–316 | 3 |
| `parseJsonCol` | 338–342 | 5 |
| `normalizeBands` | 344–374 | 31 |
| `normalizeKnobs` | 377–389 | 13 |
| `knobsToObject` | 391–398 | 8 |
| `serializeKnobs` | 400–400 | 1 |
| `serializeStack` | 408–413 | 6 |
| `serializeMaterials` | 417–419 | 3 |
| `normalizeLegendItem` | 431–448 | 18 |
| `cloneLegend` | 452–462 | 11 |
| `legendRowPayload` | 481–493 | 13 |
| `canonRegistryRow` | 498–503 | 6 |
| `registryFingerprint` | 507–513 | 7 |
| `buildLegendRegistryUpdates` | 522–566 | 45 |
| `parseLegendRegistryRows` | 571–628 | 58 |
| `getMissingDescValues` | 631–636 | 6 |
| `formatLegendMetaText` | 638–641 | 4 |
| `saveLegendToStorage` | 3821–3824 | 4 |
| `fetchRegistryRows` | 4087–4108 | 22 |
| `readRegistryScope` | 4112–4118 | 7 |
| `legendRowSignature` | 4123–4128 | 6 |
| `reconcileVocabClaims` | 4144–4160 | 17 |
| `applyRegistryRowsToLegend` | 4169–4211 | 43 |
| `saveLegendToServer` | 4248–4358 | 111 |
| `probeZoneColumns` | 4371–4396 | 26 |
| `applyLegendSaveResult` | 4412–4424 | 13 |
| `getPlanSaveState` | 4439–4445 | 7 |
| `persistLegend` | 4452–4456 | 5 |

**map-key** — 6 functions, 97 LOC

| fn | lines | LOC |
|---|---|---|
| `canonIntString` | 672–678 | 7 |
| `canonicalKeyValue` | 686–707 | 22 |
| `composeMapId` | 712–719 | 8 |
| `decomposeMapKey` | 723–739 | 17 |
| `canonicalMapKey` | 743–756 | 14 |
| `getMapIdFromMeta` | 758–786 | 29 |

**dom-wiring** — 13 functions, 866 LOC

| fn | lines | LOC |
|---|---|---|
| `debounce` | 788–794 | 7 |
| `initDOMElements` | 868–1193 | 326 |
| `getGridCellObject` | 1195–1232 | 38 |
| `getGridCellFromMouseEvent` | 1234–1264 | 31 |
| `planSidebarBounds` | 1285–1293 | 9 |
| `applyPlanSidebarWidth` | 1295–1300 | 6 |
| `initPlanSidebarResizer` | 1302–1355 | 54 |
| `initMouseDragEvents` | 1359–1477 | 119 |
| `loadTablesList` | 1480–1553 | 74 |
| `switchTable` | 1556–1625 | 70 |
| `renderMetadataInputs` | 1627–1702 | 76 |
| `getBaseColumnName` | 1704–1710 | 7 |
| `fillColumnDropdowns` | 1712–1760 | 49 |

**coord-transform** — 18 functions, 472 LOC

| fn | lines | LOC |
|---|---|---|
| `physNum` | 1776–1783 | 8 |
| `gridDimNum` | 1785–1792 | 8 |
| `physDeclaration` | 1809–1820 | 12 |
| `withPhysFrame` | 1822–1826 | 5 |
| `getDieIndex` | 1850–1907 | 58 |
| `getCanvasCellFromDieIndex` | 1909–1948 | 40 |
| `frameDieLattice` | 1978–1988 | 11 |
| `dieIndexToWaferMm` | 1991–1994 | 4 |
| `waferMmToDieCell` | 2004–2014 | 11 |
| `getCanvasCellFromDb` | 2016–2029 | 14 |
| `getWaferBoundingBox` | 2071–2181 | 111 |
| `getDbCoords` | 2183–2196 | 14 |
| `seatingSnapshot` | 2216–2237 | 22 |
| `reseatCellsToStoredCoords` | 2269–2320 | 52 |
| `getTransformedPhysicalConfig` | 2322–2355 | 34 |
| `getScreenShift` | 2357–2381 | 25 |
| `isCellInsideWaferFast` | 2383–2419 | 37 |
| `isCellInsideWafer` | 2421–2426 | 6 |

**valid-die** — 15 functions, 794 LOC

| fn | lines | LOC |
|---|---|---|
| `parseValidDieRef` | 2480–2507 | 28 |
| `validDieBasis` | 2521–2528 | 8 |
| `isValidDieAt` | 2540–2546 | 7 |
| `buildValidDieTemplate` | 2572–2600 | 29 |
| `validDieRefDisplay` | 2605–2617 | 13 |
| `applyValidDieRef` | 2634–2654 | 21 |
| `validDieRefFromControls` | 2670–2677 | 8 |
| `validDieRefForPush` | 2679–2692 | 14 |
| `validDieRefPayload` | 2705–2710 | 6 |
| `validDieChainError` | 2731–2749 | 19 |
| `resolveValidDie` | 8037–8555 | 519 |
| `renderValidDieChip` | 8560–8588 | 29 |
| `syncValidDieRefControls` | 8594–8606 | 13 |
| `onValidDieRefChanged` | 8611–8625 | 15 |
| `enterValidDieAuthoring` | 8874–8938 | 65 |

**geometry-presets** — 9 functions, 340 LOC

| fn | lines | LOC |
|---|---|---|
| `applyPhysicalGeometry` | 2751–2786 | 36 |
| `updateOrientationUI` | 2804–2822 | 19 |
| `fetchAndRenderPresets` | 2824–2839 | 16 |
| `renderPresetDropdown` | 2841–2893 | 53 |
| `applyPresetObject` | 2897–2966 | 70 |
| `applyRoutedPreset` | 2990–3030 | 41 |
| `loadSelectedPreset` | 3032–3055 | 24 |
| `saveCustomPreset` | 3057–3107 | 51 |
| `deleteCustomPreset` | 3109–3138 | 30 |

**canvas-render** — 12 functions, 470 LOC

| fn | lines | LOC |
|---|---|---|
| `rebuildThemeColorCache` | 3263–3287 | 25 |
| `getThemeColors` | 3289–3292 | 4 |
| `cellFillColor` | 3301–3305 | 5 |
| `parseCssColor` | 3310–3319 | 10 |
| `toExcelHex` | 3321–3329 | 9 |
| `scheduleRenderGridCanvas` | 3339–3346 | 8 |
| `updateSideIndicator` | 3350–3356 | 7 |
| `fitGridToWorkspace` | 3361–3374 | 14 |
| `renderGridCanvas` | 3376–3649 | 274 |
| `handleCellClick` | 3651–3703 | 53 |
| `updateCellStyles` | 3705–3714 | 10 |
| `updateNotchPosition` | 3719–3769 | 51 |

**legend-panel-ui** — 14 functions, 381 LOC

| fn | lines | LOC |
|---|---|---|
| `eachSavableCell` | 3159–3173 | 15 |
| `classifyUnsavableCells` | 3192–3211 | 20 |
| `pushBlockingCount` | 3225–3227 | 3 |
| `computeLegendCounts` | 3230–3235 | 6 |
| `updateLegendCounts` | 3237–3252 | 16 |
| `pickUnusedColor` | 3781–3785 | 5 |
| `autoAddLegendValue` | 3790–3800 | 11 |
| `seedEmptyDoe` | 3807–3813 | 7 |
| `renderLegendMetaOnly` | 4483–4490 | 8 |
| `renderLegendTable` | 4500–4686 | 187 |
| `selectBrush` | 4688–4718 | 31 |
| `addLegendRowForPanel` | 4723–4732 | 10 |
| `updateLegendRowForPanel` | 4734–4777 | 44 |
| `deleteLegendRowForPanel` | 4779–4796 | 18 |

**draft-restore** — 15 functions, 315 LOC

| fn | lines | LOC |
|---|---|---|
| `doeDraftKey` | 3829–3829 | 1 |
| `cellsDigest` | 3859–3867 | 9 |
| `serverCellKeySet` | 3885–3890 | 6 |
| `saveDoeDraft` | 3892–3927 | 36 |
| `readDoeDraft` | 3929–3940 | 12 |
| `clearDoeDraft` | 3942–3944 | 3 |
| `recordLastOpenMap` | 3952–3965 | 14 |
| `restoreLastOpenMap` | 3971–3998 | 28 |
| `applyDoeDraftRecord` | 4001–4035 | 35 |
| `applyDraftCells` | 4038–4049 | 12 |
| `getCurrentMapKey` | 4054–4064 | 11 |
| `scheduleCellDraft` | 4474–4479 | 6 |
| `effortRoute` | 7289–7291 | 3 |
| `snapshotEditorState` | 7303–7366 | 64 |
| `restoreEditorState` | 7368–7442 | 75 |

**map-load** — 8 functions, 818 LOC

| fn | lines | LOC |
|---|---|---|
| `fetchMapKeySpec` | 4804–4823 | 20 |
| `fetchMapKeyColumns` | 4825–4827 | 3 |
| `probeMapExists` | 4830–4845 | 16 |
| `remapGridValues` | 4847–4857 | 11 |
| `fetchGridMetaFor` | 4869–4899 | 31 |
| `loadExistingMap` | 4902–5564 | 663 |
| `clearGrid` | 5566–5578 | 13 |
| `fillGrid` | 5580–5640 | 61 |

**push** — 3 functions, 449 LOC

| fn | lines | LOC |
|---|---|---|
| `getUnprotectedPushColumns` | 5674–5685 | 12 |
| `logShapedPushDecision` | 5693–5697 | 5 |
| `pushMapData` | 5699–6130 | 432 |

**edge-batch** — 6 functions, 198 LOC

| fn | lines | LOC |
|---|---|---|
| `getEdgeClassification` | 6135–6206 | 72 |
| `getVisualGridDimensions` | 6208–6216 | 9 |
| `selectEdgeCells` | 6218–6243 | 26 |
| `autoPaintE1E2` | 6245–6289 | 45 |
| `fillSelectedCells` | 6291–6315 | 25 |
| `clearSelectedCells` | 6317–6337 | 21 |

**clipboard** — 23 functions, 696 LOC

| fn | lines | LOC |
|---|---|---|
| `writeClipboardRich` | 6352–6402 | 51 |
| `colHeaderWord` | 6423–6426 | 4 |
| `auxHeadWords` | 6430–6432 | 3 |
| `copyHeaderEnabled` | 6434–6436 | 3 |
| `mapKeyGroupLabel` | 6446–6454 | 9 |
| `copyHeaderGroups` | 6459–6469 | 11 |
| `headerSpanFor` | 6499–6503 | 5 |
| `distributeSpans` | 6509–6521 | 13 |
| `auxColumnSpans` | 6525–6529 | 5 |
| `copyHeaderAuxRows` | 6533–6545 | 13 |
| `copyTitleText` | 6549–6551 | 3 |
| `computeNotchCell` | 6567–6603 | 37 |
| `notchMarkCell` | 6616–6623 | 8 |
| `copyGridToExcel` | 6625–6879 | 255 |
| `pasteBlank` | 6915–6915 | 1 |
| `pasteAt` | 6916–6919 | 4 |
| `auxHeaderInLine` | 6939–6959 | 21 |
| `readCompanyMapBlock` | 6974–7035 | 62 |
| `checkPasteAgainstFrame` | 7044–7100 | 57 |
| `applyPastedGridRows` | 7110–7128 | 19 |
| `pastedCellCount` | 7133–7139 | 7 |
| `applyPastedAuxRows` | 7150–7176 | 27 |
| `onMapGridPaste` | 7181–7258 | 78 |

**frame-stack** — 12 functions, 218 LOC

| fn | lines | LOC |
|---|---|---|
| `applyGridMetaObject` | 7445–7462 | 18 |
| `findPresetByKind` | 7465–7482 | 18 |
| `applyCellsToGrid` | 7485–7503 | 19 |
| `collectPlanCells` | 7508–7516 | 9 |
| `currentIdentityMismatch` | 7527–7532 | 6 |
| `setLoadedIdentity` | 7534–7547 | 14 |
| `frameTitle` | 7550–7553 | 4 |
| `currentFrameTitle` | 7555–7557 | 3 |
| `renderBreadcrumb` | 7559–7572 | 14 |
| `switchTableQuiet` | 7576–7595 | 20 |
| `openMapFrame` | 7600–7671 | 72 |
| `popMapFrame` | 7673–7693 | 21 |

**overlay** — 30 functions, 803 LOC

| fn | lines | LOC |
|---|---|---|
| `recomputeActiveOverlays` | 7732–7734 | 3 |
| `drawOverlayMarkers` | 7743–7792 | 50 |
| `frameFromMeta` | 7798–7822 | 25 |
| `frameDimBounds` | 7843–7843 | 1 |
| `frameDimError` | 7851–7856 | 6 |
| `currentFrame` | 7859–7869 | 11 |
| `resolveFrame` | 7872–7887 | 16 |
| `frameAxesKey` | 7889–7892 | 4 |
| `projectCellsToWaferMm` | 7904–7929 | 26 |
| `projectCellsToPhys` | 7934–7938 | 5 |
| `seatWaferMmInFrame` | 7949–7974 | 26 |
| `canvasSeatKeys` | 7998–8024 | 27 |
| `pushFailedOverlay` | 8942–8958 | 17 |
| `buildKeyFilters` | 8974–8981 | 8 |
| `addOverlayLayer` | 8988–9250 | 263 |
| `removeOverlayLayer` | 9252–9257 | 6 |
| `toggleOverlayLayer` | 9259–9266 | 8 |
| `clearOverlayLayers` | 9268–9273 | 6 |
| `reseatOverlayLayer` | 9282–9335 | 54 |
| `currentGeomSignature` | 9346–9361 | 16 |
| `syncOverlayGeometry` | 9363–9374 | 12 |
| `overlayAlignChip` | 9387–9408 | 22 |
| `overlayFanChip` | 9413–9417 | 5 |
| `importOverlayToGrid` | 9429–9498 | 70 |
| `ensureLegendValues` | 9502–9509 | 8 |
| `renderOverlayList` | 9511–9558 | 48 |
| `escapeHtmlAttr` | 9560–9562 | 3 |
| `handleAddOverlayClick` | 9567–9593 | 27 |
| `addOverlayForSource` | 9602–9624 | 23 |
| `listOverlayLayers` | 9626–9632 | 7 |

**datalist-suggest** — 11 functions, 169 LOC

| fn | lines | LOC |
|---|---|---|
| `markSuggestState` | 8666–8675 | 10 |
| `claimListFill` | 8683–8687 | 5 |
| `fillDatalist` | 8689–8697 | 9 |
| `populateMapKeyDatalist` | 8703–8745 | 43 |
| `populateValidDieRefList` | 8748–8752 | 5 |
| `populateOverlayKeyList` | 8755–8758 | 4 |
| `colValueKey` | 8768–8768 | 1 |
| `dropColumnValueCache` | 8772–8783 | 12 |
| `canReuseComplete` | 8787–8790 | 4 |
| `populateColumnValueDatalist` | 8792–8857 | 66 |
| `onMetaInputSuggest` | 8861–8870 | 10 |

### Appendix B — Module-level mutable state (readers/writers by function)

| state | kind | line | readers (fns) | writers (fns) |
|---|---|---|---|---|
| `el` | const-mutable | 867 | 57 fns | `initDOMElements` `initMouseDragEvents` `loadTablesList` `fillColumnDropdowns` `applyPhysicalGeometry` `renderPresetDropdown` `applyPresetObject` `loadSelectedPreset` `saveCustomPreset` `deleteCustomPreset` `updateSideIndicator` `renderGridCanvas` `handleCellClick` `updateNotchPosition` `restoreLastOpenMap` `renderLegendTable` `selectBrush` `loadExistingMap` `pushMapData` `selectEdgeCells` `fillSelectedCells` `clearSelectedCells` `copyGridToExcel` `restoreEditorState` `applyGridMetaObject` `openMapFrame` `resolveValidDie` `syncValidDieRefControls` `handleAddOverlayClick` |
| `gridData` | let | 41 | 24 fns | `initMouseDragEvents` `switchTable` `reseatCellsToStoredCoords` `handleCellClick` `applyDraftCells` `renderLegendTable` `deleteLegendRowForPanel` `remapGridValues` `loadExistingMap` `clearGrid` `fillGrid` `autoPaintE1E2` `fillSelectedCells` `clearSelectedCells` `applyPastedGridRows` `restoreEditorState` `applyCellsToGrid` `switchTableQuiet` `enterValidDieAuthoring` `importOverlayToGrid` |
| `legend` | let | 42 | 25 fns | `autoAddLegendValue` `seedEmptyDoe` `applyDoeDraftRecord` `applyRegistryRowsToLegend` `renderLegendTable` `deleteLegendRowForPanel` `loadExistingMap` `restoreEditorState` |
| `currentRotation` | let | 48 | 23 fns | `initDOMElements` `loadExistingMap` `restoreEditorState` `applyGridMetaObject` |
| `currentSide` | let | 49 | 23 fns | `initDOMElements` `loadExistingMap` `restoreEditorState` `applyGridMetaObject` |
| `selectedTable` | let | 39 | 21 fns | `switchTable` `restoreEditorState` `switchTableQuiet` |
| `activeBrush` | let | 43 | 11 fns | `seedEmptyDoe` `applyRegistryRowsToLegend` `renderLegendTable` `selectBrush` `updateLegendRowForPanel` `deleteLegendRowForPanel` `loadExistingMap` `restoreEditorState` |
| `overlayLayers` | let | 7728 | 13 fns | `restoreEditorState` `openMapFrame` `pushFailedOverlay` `addOverlayLayer` `removeOverlayLayer` `clearOverlayLayers` |
| `gridCells2D` | let | 54 | 14 fns | `renderGridCanvas` |
| `validDie` | let | 2455 | 10 fns | `switchTable` `loadExistingMap` `restoreEditorState` `resolveValidDie` `enterValidDieAuthoring` |
| `loadedIdentity` | let | 7292 | 10 fns | `restoreEditorState` `setLoadedIdentity` `openMapFrame` |
| `tableSchema` | let | 40 | `getMapIdFromMeta` `renderMetadataInputs` `getBaseColumnName` `fillColumnDropdowns` `pushMapData` `mapKeyGroupLabel` `snapshotEditorState` `restoreEditorState` | `switchTable` `restoreEditorState` `switchTableQuiet` |
| `loadedFCells` | let | 57 | `isProtectedFCell` `reseatCellsToStoredCoords` `snapshotEditorState` `resolveValidDie` | `recomputeLockedCells` `switchTable` `reseatCellsToStoredCoords` `loadExistingMap` `clearGrid` `restoreEditorState` `switchTableQuiet` |
| `legendMeta` | let | 291 | `renderLegendMetaOnly` `renderLegendTable` `updateLegendRowForPanel` `deleteLegendRowForPanel` `snapshotEditorState` | `seedEmptyDoe` `applyRegistryRowsToLegend` `saveLegendToServer` `restoreEditorState` |
| `paintLockConfig` | let | 68 | `isLockedValue` `isOverlayLocked` `paintLockMessage` `fetchPaintRules` `updatePaintLockIndicator` `recomputeLockedCells` | `applyPaintLockConfig` `fetchPaintRules` |
| `legendReplaceScope` | let | 302 | `saveLegendToServer` `snapshotEditorState` `setLoadedIdentity` | `saveLegendToServer` `loadExistingMap` `restoreEditorState` `setLoadedIdentity` `openMapFrame` |
| `physFrameOverride` | let | 1773 | `physNum` `gridDimNum` `physDeclaration` `withPhysFrame` `getWaferBoundingBox` `seatingSnapshot` `isValidDieAt` | `withPhysFrame` |
| `editorFrames` | let | 7271 | `recordLastOpenMap` `effortRoute` `renderBreadcrumb` `openMapFrame` `popMapFrame` `(top-level wiring)` | `openMapFrame` `popMapFrame` |
| `legendConflict` | let | 310 | `saveLegendToServer` `getPlanSaveState` `snapshotEditorState` | `saveLegendToServer` `loadExistingMap` `restoreEditorState` `openMapFrame` |
| `boundingBoxCache` | let | 2031 | `getWaferBoundingBox` | `getWaferBoundingBox` `applyPresetObject` `loadExistingMap` `restoreEditorState` `applyGridMetaObject` `resolveValidDie` |
| `cellsSeatedUnder` | let | 2214 | `initDOMElements` `applyPhysicalGeometry` `renderGridCanvas` `resolveValidDie` | `reseatCellsToStoredCoords` `renderGridCanvas` `resolveValidDie` |
| `legendDirty` | let | 4436 | `getPlanSaveState` `snapshotEditorState` | `persistLegend` `scheduleCellDraft` `loadExistingMap` `pushMapData` `restoreEditorState` |
| `legendSaveState` | let | 312 | `getPlanSaveState` `snapshotEditorState` | `applyLegendSaveResult` `loadExistingMap` `restoreEditorState` `openMapFrame` |
| `serverCellKeys` | let | 3881 | `reseatCellsToStoredCoords` `serverCellKeySet` `resolveValidDie` | `reseatCellsToStoredCoords` `loadExistingMap` `pushMapData` |
| `framePushed` | let | 7293 | `snapshotEditorState` `popMapFrame` | `pushMapData` `restoreEditorState` `setLoadedIdentity` `importOverlayToGrid` |
| `frameTouched` | let | 7301 | `snapshotEditorState` `popMapFrame` | `persistLegend` `scheduleCellDraft` `restoreEditorState` `setLoadedIdentity` |
| `isOriginMode` | let | 50 | `initDOMElements` `initMouseDragEvents` `handleCellClick` | `initDOMElements` `handleCellClick` |
| `selectedEdgeTargetMap` | let | 56 | `fillSelectedCells` `clearSelectedCells` | `selectEdgeCells` `fillSelectedCells` `clearSelectedCells` |
| `validDieResolveSeq` | let | 2472 | `getWaferBoundingBox` `canvasSeatKeys` `resolveValidDie` | `resolveValidDie` `enterValidDieAuthoring` |
| `serverPresets` | let | 2791 | `renderPresetDropdown` `loadSelectedPreset` `deleteCustomPreset` `findPresetByKind` | `fetchAndRenderPresets` |
| `servedBindingCache` | const-mutable | 128 | `fetchServedBinding` `fillColumnDropdowns` | `fetchServedBinding` `fetchPaintRules` |
| `legendVocabularySeed` | let | 306 | `reconcileVocabClaims` `snapshotEditorState` | `seedEmptyDoe` `restoreEditorState` |
| `mapKeyListCache` | const-mutable | 8701 | `populateMapKeyDatalist` | `switchTable` `pushMapData` `populateMapKeyDatalist` |
| `columnValueComplete` | const-mutable | 8764 | `dropColumnValueCache` `populateColumnValueDatalist` | `dropColumnValueCache` `populateColumnValueDatalist` |
| `columnValueRefused` | const-mutable | 8765 | `dropColumnValueCache` `populateColumnValueDatalist` | `dropColumnValueCache` `populateColumnValueDatalist` |
| `columnValueTruncated` | const-mutable | 8766 | `dropColumnValueCache` `onMetaInputSuggest` | `dropColumnValueCache` `populateColumnValueDatalist` |
| `overlayGeomSig` | let | 9344 | `snapshotEditorState` `syncOverlayGeometry` | `restoreEditorState` `syncOverlayGeometry` |
| `isBoxDragging` | let | 51 | `initMouseDragEvents` `renderGridCanvas` | `initMouseDragEvents` |
| `lastSelectionBox` | let | 53 | `initMouseDragEvents` `renderGridCanvas` | `initMouseDragEvents` |
| `dragType` | let | 55 | `initMouseDragEvents` `renderGridCanvas` | `initMouseDragEvents` |
| `overlayContract` | let | 117 | `defaultLegendRows` `declaredLegendRow` | `fetchPaintRules` |
| `currentHoverCell` | let | 1357 | `initMouseDragEvents` `renderGridCanvas` | `initMouseDragEvents` |
| `validDieRefTableTouched` | let | 2464 | `validDieRefFromControls` | `initDOMElements` `syncValidDieRefControls` |
| `draftBase` | let | 3871 | `saveDoeDraft` | `saveLegendToServer` `loadExistingMap` |
| `activeOverlayLayers` | let | 7729 | `renderGridCanvas` `drawOverlayMarkers` | `recomputeActiveOverlays` |
| `isRightDrag` | let | 45 | `handleCellClick` | `initMouseDragEvents` |
| `boxStartCell` | let | 52 | `initMouseDragEvents` | `initMouseDragEvents` |
| `NO_PAINT_LOCK` | const-mutable | 67 | `fetchPaintRules` `(top-level wiring)` | — |
| `LEGEND_PAYLOAD_COLUMNS` | const-mutable | 477 | `registryFingerprint` `legendRowSignature` | — |
| `themeColors` | let | 3261 | `getThemeColors` | `rebuildThemeColorCache` |
| `isRenderScheduled` | let | 3337 | `scheduleRenderGridCanvas` | `scheduleRenderGridCanvas` |
| `LEGEND_PALETTE` | const-mutable | 3778 | `pickUnusedColor` `loadExistingMap` | — |
| `zoneColumnsPresent` | let | 4363 | `probeZoneColumns` | `probeZoneColumns` |
| `LEGEND_SAVE_MESSAGE` | const-mutable | 4399 | `applyLegendSaveResult` `getPlanSaveState` | — |
| `cellDraftTimer` | let | 4473 | `scheduleCellDraft` | `scheduleCellDraft` |
| `mapKeyColumnCache` | const-mutable | 4799 | `fetchMapKeySpec` | `fetchMapKeySpec` |
| `PUSH_SYSTEM_COLUMNS` | const-mutable | 5652 | `renderMetadataInputs` `getUnprotectedPushColumns` | — |
| `overlaySeq` | let | 7730 | — | `pushFailedOverlay` `addOverlayLayer` |
| `seatKeyCache` | let | 7997 | `canvasSeatKeys` | `canvasSeatKeys` |
| `listFillSeq` | const-mutable | 8682 | `claimListFill` | `claimListFill` |
| `isMouseDown` | let | 44 | — | `initMouseDragEvents` |
| `EMPTY_DOE_SEED` | const-mutable | 258 | `defaultLegendRows` | — |
| `VALID_DIE_TEMPLATE_OPTIONS` | const-mutable | 2796 | `renderPresetDropdown` | — |
| `REGISTRY_SCOPES` | const-mutable | 4086 | `fetchRegistryRows` | — |
| `ZONE_COLUMNS` | const-mutable | 4370 | `probeZoneColumns` | — |
| `OVERLAY_COLORS` | const-mutable | 7722 | `addOverlayLayer` | — |
| `tables` | let | 38 | — | — |
