# map_editor.js refactoring — Round 4: `loadExistingMap`, decomposed in place

**Author**: map-pm · **Date**: 2026-08-04 · **Base**: `cc36ef4` · **Commit**: `2f3fa6f` (not pushed)

**Verdict: the round is complete and self-contained. TEMPORARY EXPORTS: NONE** — nothing was
exported at all, and no new file was created (§8).

---

## 0. The structural numbers (lead with these, not the line delta)

| measure | before | after |
|---|---|---|
| `loadExistingMap` total lines | **663** | **358** |
| `loadExistingMap` code lines (non-blank, non-comment) | 331 | **182** |
| named steps it is written in terms of | 0 | **7** |
| module-state bindings each step reads or writes | — | **0, all seven** |
| module-state bindings `loadExistingMap` still owns | 19 | **19 (unchanged, by design)** |
| longest single step | — | **93 lines / 61 code lines** (`resolveDeclaredGridMeta`) |
| longest remaining inline run inside the orchestrator | 663 | **115 lines / 56 code lines** |
| `map_editor.js` | 9,163 | **9,253 (+90)** |

**The +90 is the expected sign.** Seven signatures, seven return statements, seven doc headers
and three harness re-points cost more lines than the braces they replaced. Nothing was optimised
for the reduction number.

**What "the next fix is faster" means concretely here**: the write set of the load path did not
move — it could not, that is the ⓑ question — but it is now *legible*. Every one of the 13
assignments to module state is in the 358-line orchestrator, and each of the seven steps can be
read, understood and changed without holding any module state in your head, because none of them
can touch any.

---

## 1. Per-FUNCTION write-set measurement, taken before the cut

Method unchanged from R2/R3: AST parse of `client2/src/map_editor.js` via `vite.parseAst` (oxc),
scope-aware walker; direct assignment, update expressions, member assignment rooted at the binding,
and mutating method calls each counted. Re-measured on `cc36ef4`; no number inherited.

### 1a. The whole function, before

```
loadExistingMap  L4433-5095 (663 lines)
  READ   : LEGEND_PALETTE currentRotation currentSide el gridData legend loadedFCells
           overlayLayers selectedTable tableSchema                                (10)
  WRITE  : activeBrush boundingBoxCache currentRotation currentSide draftBase gridData
           legend legendConflict legendDirty legendReplaceScope legendSaveState
           serverCellKeys validDie                                                (13)
  MUTATE : el gridData loadedFCells                                                (3)
  CALLS  : 31 module functions
  STATE# : 19 distinct bindings
```

### 1b. Per-BLOCK, which is what decided where the cuts go

This is the measurement the brief asked for and it is the whole design. Ranges are on `cc36ef4`.

| block (L) | what | READ | WRITE | MUTATE | STATE# | verdict |
|---|---|---|---|---|---|---|
| 4435–4440 | validDie reset | — | `validDie` | — | 1 | **inline** (module write) |
| 4441–4462 | meta inputs → filter | — | — | — | **0** | → ① |
| 4464–4471 | column reads, button, url | `el` `selectedTable` | — | `el` | 2 | inline |
| 4498–4522 | coordinate bbox pre-scan | — | — | — | **0** | → ② |
| 4524–4621 | wafer_map_metadata resolution | `selectedTable` `tableSchema` | — | — | 2 (both read-only) | → ③ |
| 4623–4705 | choice modal | `el` `selectedTable` | — | `el` | 2 | → ④ |
| 4707–4796 | frame from choice + panel sync | `currentRotation` `currentSide` `el` | `boundingBoxCache` `currentRotation` `currentSide` | `el` | 4 | **split**: decision → ⑤, sync stays inline |
| 4798–4826 | valid-die → origin → dims | `el` `selectedTable` | `boundingBoxCache` | — | 3 | **inline** (§4) |
| 4828–4868 | cell placement loop | `gridData` `loadedFCells` | — | `gridData` `loadedFCells` | 2 | **inline** (§4 — this is the one that matters) |
| 4870–4887 | serverCellKeys capture | `gridData` `selectedTable` | `serverCellKeys` | — | 3 | **inline** (module write, 6 code lines) |
| 4889–4952 | legend from cell values | `LEGEND_PALETTE` `legend` | `activeBrush` `legend` | — | 3 | **split**: derivation → ⑥, assignment stays inline |
| 4954–5056 | registry read + draft precedence | `gridData` `selectedTable` | `draftBase` `legendConflict` `legendDirty` `legendReplaceScope` `legendSaveState` | — | 7 | **split**: draft precedence → ⑦, the 5 writes stay inline |
| 5058–5085 | render / identity / notify | `selectedTable` | — | — | 1 | **inline** (§4 — mutation anchor) |

**The rule the table produced**: a block with `STATE# 0`, or whose state reads are read-only and
can be named as parameters, becomes a step. A block that *writes* module state stays where the
writes are visible. Two blocks that write module state were **split** rather than left whole —
the deciding computation left, the assignment stayed — which is why ⑤/⑥/⑦ exist at all.

### 1c. After the cut, re-measured with the same tool

```
loadExistingMap                L4447-4804 (358)  READ 10 · WRITE 13 · MUTATE 3 · STATE# 19
collectMapKeyFilterModel       L4816-4835 ( 20)  STATE# 0 · calls: —
scanCoordinateBounds           L4839-4865 ( 27)  STATE# 0 · calls: —
resolveDeclaredGridMeta        L4869-4961 ( 93)  STATE# 0 · calls: fetchGridMetaFor getMapIdFromMeta showToast
promptCoordinateChoice         L4965-5020 ( 56)  STATE# 0 · calls: —
resolveGridFrame               L5024-5098 ( 75)  STATE# 0 · calls: applyPresetObject
deriveLegendFromCellValues     L5103-5150 ( 48)  STATE# 0 · calls: declaredLegendRow normalizeLegendItem
restoreDoeDraftWithPrecedence  L5157-5185 ( 29)  STATE# 0 · calls: applyDoeDraftRecord applyDraftCells readDoeDraft showToast
```

`loadExistingMap`'s own STATE# is **19 before and 19 after** — deliberately. Nothing was moved out
of the orchestrator's ownership; only the *deciding* was.

---

## 2. The step list

| # | step | lines / code | takes | returns | module state |
|---|---|---|---|---|---|
| ① | `collectMapKeyFilterModel()` | 20 / 18 | — (reads `document`, a global) | `{ filterModel, hasFilter }` | **0** |
| ② | `scanCoordinateBounds(result, xCol, yCol)` | 27 / 24 | the response | `{ minX, minY, maxX, maxY }` | **0** |
| ③ | `resolveDeclaredGridMeta(selectedTable, tableSchema, filterModel, result)` | 93 / 61 | table, schema, filter, response | `{ ok:true, gridMeta, mapKey }` \| `{ ok:false, refusal }` | **0** |
| ④ | `promptCoordinateChoice(el)` | 56 / 31 | the DOM registry | `Promise<'standard'\|'current'\|'cancel'>` | **0** |
| ⑤ | `resolveGridFrame(userChoice, loadedGridMeta, minX, minY, maxX, maxY, el, currentRotation, currentSide)` | 75 / 40 | the choice + the bbox + the panel | `{ cols, rows, startX, startY, invertY, rotation, side }` | **0** |
| ⑥ | `deriveLegendFromCellValues(uniqueVals, legend, predefinedColors)` | 48 / 34 | the values, the on-screen legend, the palette | a NEW legend array | **0** |
| ⑦ | `restoreDoeDraftWithPrecedence(selectedTable, loadedMapKey, serverFp, serverCellsFp)` | 29 / 25 | the identity + the two server fingerprints | `{ restoredUnsavedEdits, staleDraftKept }` | **0** |

Three parameter names deliberately **shadow** the module binding of the same name
(`selectedTable`, `tableSchema`, `el`, `currentRotation`, `currentSide`). That is the R1
`getMapIdFromMeta` trick and it buys two things: the moved body stays **byte-identical**, so the
vm-sliced text is the same text; and the signature says out loud what the step depends on.

**The consequence that made the harness re-point safe**: because every step takes what it needs,
none of them introduces a free identifier that `loadExistingMap` did not already have. Not one new
name had to be declared in any of the three vm sandboxes.

### 2a. The three assignments that had to be hoisted to the caller

Each is a module-state write that lived inside a block whose *decision* moved. All three are
called out in the source at their new position.

1. `boundingBoxCache = {}` (was inside ⑤'s `meta` branch) → the caller now does
   `if (userChoice === 'meta') boundingBoxCache = {};` immediately after the call. Nothing between
   that point and the unconditional invalidate 20 lines later reads the cache.
2. `legend = newLegend` / `activeBrush = …` (was the tail of the ⑥ block) → stayed inline, byte
   for byte, including the H1 comment about why the load path does not persist here.
3. `legendDirty = true` (was inside ⑦'s draft branch) → ⑦ returns `restoredUnsavedEdits` and the
   caller sets the flag. Verified nothing between the old and new position reads `legendDirty`:
   the intervening calls are `showToast`, `readDoeDraft`, `applyDoeDraftRecord`, `applyDraftCells`,
   and none of the four references the binding (`legendDirty` has exactly 12 sites repo-wide,
   listed by grep; none is in those four functions).

---

## 3. Zero behavior change — what is byte-identical and what is not

`git diff --numstat` on `map_editor.js`: **+423 / −333**. Every removed line reappears in the new
text apart from indentation, with these classes of forced edit and no others:

| class | count | what |
|---|---|---|
| indentation only | ~250 | a block moved from inside `try {` inside a function (4–12 spaces) to a module-scope function body (2–4) |
| `result.data` → parameter | 0 | avoided: ② and ③ take `result` itself, so `if (result && result.data)` is byte-identical |
| `return X` → `return { ok:false, refusal: X }` | 2 | ③'s two refusal exits, so the caller can `return declared.refusal` |
| new `return` statements | 7 | one per step |
| signature + closing brace | 14 | one pair per step |
| step-call lines replacing the block | 7 | |
| comment text edited | 2 | ③ dropped a stale line-number citation (`:5721·:5729`); ④'s pointer to `startX = minX` now names `resolveGridFrame` instead of "아래" |

**No math line was touched.** No null guard, default, rename or reordering was introduced.

---

## 4. What resisted decomposition, and why — the important half of this report

### 4a. 🔴 The cell-placement loop (L4828–4868, 39 lines) — LEFT INLINE

This is the block a reader would most want named, and extracting it is **wrong**, for a reason the
per-block measurement did not show and only the harness reading did:

`client2/tests/standard_frame_origin_harness.mjs` injects two of its seven defects **into this
loop's scope**:

```js
const OLD_SHIFT = `            const cell = getCanvasCellFromDb(xNum, yNum, cols, rows, rotation, side, invertY, startX, startY);`;
// D0 and D2 both prepend:
//   if (userChoice === 'standard') { xNum = xNum - minX; yNum = yNum - minY; }
```

`userChoice`, `minX` and `minY` are locals of `loadExistingMap`. Move the loop into
`placeCellsIntoGrid(...)` and that injected code is a `ReferenceError` — the mutation stops being
*the shipped defect restored in full* and becomes a crash, i.e. **the round's single most important
defect axis (D0) would be silently unscored while the baseline stayed green.** The harness's own
comment names this failure mode ("8 of 18 mutations went unapplied while the baseline stayed
green"). Re-pointing the anchor is not available either: there is no spelling of "renumber the cell
by the data minimum" inside a function that cannot see the data minimum.

It also carries the invariant-① note (NO SHIFT — the frame's origin carries the offset). It stays,
under the section banner it already had.

### 4b. The valid-die → origin → cells ordering block (L4798–4826) — LEFT INLINE

`valid_die_origin_alignment_harness`'s **D8** anchors on this block verbatim, including its Korean
comment and its 4-space indentation (`RESOLVE_FIRST`), and its second `.replace` anchors on the
`// [M4②]` comment plus `    renderGridCanvas();` in the epilogue. Both were kept byte-identical.
Independently: this block *is* the ordering contract ("유효 다이 → 오리진 → 셀 위치, 이 순서가
사용자 지시다"), and an ordering contract belongs in the function whose order it constrains.

### 4c. Three module-state write blocks — LEFT INLINE

- **the panel sync** (`el.grid*`, `currentRotation`, `currentSide`, `boundingBoxCache`,
  `updateOrientationUI()`): 8 assignments, 5 of them to module state. A step here would be a step
  that exists to write module state, which is the shape this round is trying to remove.
- **the `serverCellKeys` capture** (invariant ④, truncation demoted to unknown): 6 code lines under
  12 lines of comment. Extracting it would mean returning `null` on truncation and assigning it,
  which is *provably* equivalent but is an equivalence argument rather than a move. Not worth it
  for 6 lines.
- **the registry read/branch skeleton**: 5 module bindings written across two branches. Returning a
  5-tuple from each branch (including an identity pass-through of `legendConflict`, which the
  failure branch does not write) would be a wider interface than the code it replaced. The *inner*
  33 lines that genuinely compute something did leave, as ⑦.

**This is the round's honest boundary and it is stated as such**: the load orchestrator's
irreducible core is ~180 code lines of "write this binding, in this order, for this reason", and
that is not a decomposition problem. It is the ⓑ question, unchanged since R2 §2.

---

## 5. Hostage harnesses — enumerated by PATH as well as by name (the R1 lesson)

`grep -rn` for both `loadExistingMap` **and** `client2/src/map_editor.js` across `client2/tests/`,
`contracts/*/`, `client2/scripts/` and `server/tests/`.

| file | relationship | action |
|---|---|---|
| `client2/tests/standard_frame_origin_harness.mjs` | **slices and executes** it (`SYMBOLS`, `die()` on missing) | **re-pointed** — 7 names added; `FIXED_ORIGIN` anchor re-indented (§5a) |
| `client2/tests/startxy_probe.mjs` | **slices and executes** it (`WANTED`, tolerates missing) | **re-pointed** — 7 names added |
| `client2/tests/valid_die_origin_alignment_harness.mjs` | **slices and executes** it (`SYMBOLS`, `die()` on missing) | **re-pointed** — 7 names added |
| `client2/tests/valid_die_frame_adoption_harness.mjs` | mentions it in a comment only; its `SYMBOLS` does **not** contain it | not touched |
| `client2/tests/effort_instrument_harness.mjs` | **stubs** it (`loadExistingMap: async () => …`) | not touched |
| `client2/tests/geometry_origin_reseat_harness.mjs` | **stubs** it | not touched |
| `client2/tests/company_roundtrip_harness.mjs`, `reposition_regime_probe.mjs` | comments only | not touched |
| `contracts/*/`, `server/tests/`, `client2/scripts/` | **no reference to `loadExistingMap` at all** | not touched |

`client2/scripts/check_harnesses.mjs` was **not touched** — no floor, no `KNOWN_RED` entry, no
recorded expectation edited.

### 5a. The one anchor that had to move, and why exactly

`standard_frame_origin_harness` mutates source text by exact string match. `String.replace` with a
string literal is verbatim, indentation included, and a mutation that does not apply prints
`MUTATION DID NOT APPLY (harness bug — this axis is unscored)` rather than failing.

```
const FIXED_ORIGIN = `      startX = minX;      // was: 6-space, inline in loadExistingMap
      startY = minY;`;
const FIXED_ORIGIN = `    startX = minX;        // now: 4-space, inside resolveGridFrame
    startY = minY;`;
```

The four replacement strings that pair with it (D1/D3/D4/D5) were re-indented to match. `OLD_SHIFT`
was **not** touched — see §4a. A comment was added above the anchors stating that they are
indentation-sensitive and why `OLD_SHIFT` stayed put.

### 5b. Proof that the re-pointed slice list is load-bearing (the R2 T4-class check)

The seven names were removed from `standard_frame_origin_harness`'s `SYMBOLS` and it was run:

```
exit 1
ReferenceError: collectMapKeyFilterModel is not defined
    at Object.loadExistingMap (evalmachine.<anonymous>:894:38)
```

**Loud, named, never silently green.** (Step ① is called *before* the `try` block, so a missing
slice cannot be swallowed by `loadExistingMap`'s own catch and reported as a 0-cell load.) File
restored, SHA-256 `0bacfe1f…` re-verified.

---

## 6. Oracles — before and after

### 6a. `node client2/scripts/check_harnesses.mjs` — **exit 0 both runs, stdout BYTE-IDENTICAL**

`23 harnesses ― 18 gated, 5 on the known-red debt list (5 still red, 0 recovered); every gated
harness is green.` No `[BLOCKING]`, no `MISSING ASSERTIONS`, no floor complaint.

| harness | before (ran/failed) | after (ran/failed) | Δ |
|---|---|---|---|
| availability_gross_marker | 48 / 0 | 48 / 0 | — |
| company_roundtrip | 84 / 0 | 84 / 0 | — |
| copy_header_count | 151 / 0 | 151 / 0 | — |
| effort_instrument **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| effort_meter | 131 / 0 | 131 / 0 | — |
| geometry_origin_reseat | 46 / 0 | 46 / 0 | — |
| m4_symbol_extractability_probe | 15 / 0 | 15 / 0 | — |
| map_key_canonical | 116 / 0 | 116 / 0 | — |
| map_key_datalist | 53 / 0 | 53 / 0 | — |
| overlay_wafer_mm | 69 / 0 | 69 / 0 | — |
| push_gate | 15 / 0 | 15 / 0 | — |
| reposition_regime_probe **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| retroactive_view | 263 / 0 | 263 / 0 | — |
| split_registry **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| **standard_frame_origin** ⟵ re-pointed | **19 / 0** | **19 / 0** | — |
| **startxy_probe** ⟵ re-pointed | **29 / 0** | **29 / 0** | — |
| undeclared_identifier | 6 / 0 | 6 / 0 | — |
| valid_die_authoring **[known red]** | 99 / 1 | 99 / 1 | — |
| valid_die_frame_adoption **[known red]** | 228 / 42 | 228 / 42 | — |
| valid_die_head_parity_oracle | 17498 / 0 | 17498 / 0 | — |
| **valid_die_origin_alignment** ⟵ re-pointed | **153 / 0** | **153 / 0** | — |
| value_suggest_keys | 94 / 0 | 94 / 0 | — |
| virtual_column_render | 59 / 0 | 59 / 0 | — |

### 6b. Contracts — `node client2/scripts/check_contracts.mjs`, **exit 0, stdout BYTE-IDENTICAL**

`band_arithmetic` · `blank_predicate` · `config_resolve_report` · `doe_band_rules` ·
`legend_map_scope` · `map_seam` — 6 contracts, no divergence. No contract file was opened.
(`config_resolve_report` still scans **32** files — no new module this round, which is the point.)

### 6c. Every harness's full stdout, compared byte for byte

All 23 run individually before and after; exit codes identical; **22 of 23 stdouts byte-identical.**
The single exception:

| file | before → after | why |
|---|---|---|
| `undeclared_identifier_harness` | `1109 declared, 1143 referenced` → `1118, 1152` | +9 declarations (7 step functions + 2 net new locals) and +9 references. **`0 undeclared` on both sides**, all 6 checks green, `ASSERTIONS 6 0` unchanged |

That harness is the specific guard against the failure mode a decomposition creates — a dangling
reference — and it is green with a *larger* population than before.

### 6d. Stored coordinates — 0 cells moved

Method unchanged from R1/R2: **cells carry their own coordinates as VALUES**; no key matching
anywhere. Byte-identical stdout across the harness set means every `dbX`/`dbY` (and every mm, mask
and seat) assertion is compared against the same recorded literal on both sides:

`valid_die_head_parity_oracle` 17,498 · `valid_die_frame_adoption` 228 ·
`valid_die_origin_alignment` 153 · `overlay_wafer_mm` 69 · `geometry_origin_reseat` 46 ·
`startxy_probe` 29 · `standard_frame_origin` 19 = **18,042 value-for-value assertions, all
identical**.

**Does the fixture set activate the defect axes?** Named, not assumed:
`standard_frame_origin` MIN_X=3 / MIN_Y=−2, SPAN 13x9 (`13 != 9`, `3 != −2`, one negative — a
transpose or an axis swap cannot pass by coincidence, and the harness asserts
`std/axes-are-distinguishable` explicitly). `startxy_probe` declared frame 21x21 at (1,−6) with
painted bbox at (5,−1) — `dx=4 dy=5`, deliberately unequal — and its case D measures that forcing
the origin to the bbox **moves 41 of 46 cells to a different physical die**. That number is not 0.
`valid_die_origin_alignment` runs 4 rotations x 2 sides x 2 inverts with `chipX=9 != chipY=11` and
four different mask insets.

---

## 7. Every re-pointed scorer shown RED with a defect put back

Two independent proofs. All injections went into the **real** working files, were scored, then
restored, and each restore was SHA-256-verified against the pre-injection digest
(`map_editor.js` = `e7f2b20f711a6156…`, re-verified after all seven).

### 7a. The existing mutation suites — byte-identical reports, so no axis was lost

| suite | before | after |
|---|---|---|
| `standard_frame_origin --mutate` | 7 declared · 7 applied · **0 did not apply** · caught by a NAMED assertion **7** · crash-only 0 · undetected 0 | **byte-identical**, including D0's full damage-report line list |
| `valid_die_origin_alignment --mutate` | 10 mutations, **all caught** | **byte-identical** |

D0 — *the shipped defect restored in full (startX=0 + the minX/minY subtraction)* — still applies
across the new boundary: its first `.replace` lands in `resolveGridFrame`, its second in the loop
that stayed inline, and it is still caught by a named assertion with 7 failures.

### 7b. A defect put into each of the seven NEW steps

| # | defect put back | standard_frame_origin | startxy_probe | valid_die_origin_alignment | contracts |
|---|---|---|---|---|---|
| I1 | ② returns the two axes swapped | **19 / 7 failed** | **29 / 4 failed** — `B standard frame derives start_x from the data` | 153 / 0 | exit 0 |
| I2 | ③ lets an unconfirmed read degrade to "no declaration" (the pre-`aee05b1` defect) | 19 / 0 | **29 / 6 failed** — `E start_x untouched by the failed read` | 153 / 0 | exit 0 |
| I3 | ① never reports the filter as present | **19 / 9 failed** | **29 / 16 failed** | **153 / 5 failed** | exit 0 |
| I4 | ④ stops honouring 📐 표준 and always keeps the panel | **19 / 6 failed** | **29 / 4 failed** | 153 / 0 | exit 0 |
| I5 | ⑤ zeroes the declared spec's START in the `meta` branch | **19 / 1 failed** | **29 / 5 failed** | **153 / 1 failed** — `load/every-die-is-savable: expected 44, got 11` | exit 0 |
| I6 | ⑥ returns an empty legend | **19 / 5 failed** | **29 / 4 failed** | 153 / 0 | exit 0 |
| I7 | ⑦ applies a stale draft anyway | 19 / 0 | 29 / 0 | 153 / 0 | exit 0 |

**Six of the seven steps are demonstrably live in the re-pointed scorers.**

🔴 **I7 is a coverage gap and it is reported, not hidden.** No harness feeds a draft — all three
stub `readDoeDraft: () => null` — so the draft-precedence branch never executes. **It was equally
unscored before this round**, and that is measured rather than asserted: HEAD's pre-decomposition
`map_editor.js` was extracted to a scratch file, the *same* defect applied to the inline version
(`const restoredDoe = doeFresh ? … : false` → `const restoredDoe = applyDoeDraftRecord(draft);`,
anchor matched exactly 1 time), and `startxy_probe` run against both:

```
pre-decomposition source, defect applied : PASS -- 29 passed, 0 failed
pre-decomposition source, clean (control): PASS -- 29 passed, 0 failed
```

Identical. The decomposition neither created nor widened the gap; it **named** the unscored piece,
which is the first thing anyone would need to close it. Board candidate, not fixed here.

---

## 8. Temporary exports: NONE

Nothing was exported. **No new module was created**, deliberately: per the brief, extracting a step
into its own file is a later judgement, made only once a step is demonstrably pure. Five of the
seven now measure `STATE# 0` *and* call nothing but pure siblings — they are candidates for a later
round — but that judgement is not this round's and no export was left standing to prepare for it.
`map_editor.js` exports nothing, as before. No accessor pair, no writable binding crosses any
boundary, nothing is exported "for the harnesses" (they slice source text). **The commit is
independently deployable**, including all three harness re-points.

---

## 9. What deliberately did NOT change

- **Coordinate math: not one line.** The bbox scan and the frame branches moved verbatim; the
  placement loop did not move at all (§4a).
- **The dead module state `tables` and `isMouseDown`** — untouched, per the ruling. Both
  re-confirmed still dead at `2f3fa6f`.
- **No bug was fixed.** The two carried forward from earlier rounds are still open and still
  untouched: `normalizeBands` silently dropping non-object band entries (R2 §9) and the dead
  `paintLockMessage` / unwired declared lock message (R3 §7–§8).
- `client2/scripts/check_harnesses.mjs`, every `contracts/**` file, `server/**`,
  `client2/dist/**`, `docs/process/PROJECT_STATUS.md`, `docs/process/DESIGN_TRACKS.md`,
  `docs/architecture/CODE_MAP.md` — **not opened**. `npm run build` **not** run.

## 10. Duplication / primitives check (done before cutting)

`PRIMITIVES.md` and `DUPLICATION_LEDGER.md` read. **Clean — no new spelling of anything exists,
because no new logic was written**: all seven steps are single moves of a single implementation.

One near-miss checked explicitly rather than assumed: `scanCoordinateBounds` is **not** a second
spelling of `getWaferBoundingBox` (`map_editor.js:1669`, which also carries `9999` sentinels). They
work in different spaces — `getWaferBoundingBox` bounds **canvas cells under the wafer/valid-die
mask**, `scanCoordinateBounds` bounds **stored DB coordinates in a query response**. Neither can be
expressed in the other's terms. Each of the seven names occurs exactly once as a definition, and
only in the four files this commit touches.

## 11. Complexity budget (UI)

**Net added controls: 0. Net removed: 0.** No panel, mode, modal, confirm, toast or user-visible
string was added, removed or altered. Every Korean UI string on the load path is byte-identical,
including the 📐 표준 button label, the four load toasts and the two draft toasts. The read path
still has exactly one confirm-free flow. **This round is invisible to the user.**

## 12. Constraints honoured

- No DB write of any kind; no server process touched; no `server/config/*.json` read or modified.
- `npm run build` **not** run; `client2/dist/**` **not** touched.
- `git add` with **explicit paths only** — the four files above; never `-a`/`-A`. Other lanes had
  uncommitted work in the shared tree throughout (`docs/process/*`, `server/bonding_plan.py`) and
  none of it is in `2f3fa6f`. **Not pushed.**
- No pytest run (nothing under `server/tests` references `loadExistingMap`).
- No file deleted. Scratch artefacts live in the session scratchpad, not the repo.

## 13. Doc update points (doc-keeper's lane — listed, not edited)

Found by looking up the changed **code path** (`client2/src/map_editor.js`) in
`docs/process/DOC_OWNERSHIP.md`, per the standing rule.

- **Row 57 「웨이퍼 맵 에디터」** — its rule *「경계는 「순수한가」로 긋는다」* now has a second form
  worth recording: **the boundary can be drawn without a new file.** Living docs
  `map_editor/README.md`, `spec/MAP_EDITOR_SPEC §1~§4` (§1-bis-2 is the file-boundary table and
  needs **no** change — no file boundary moved).
- **Row 74 「범용 맵 오버레이」** and **row 75 「맵 정렬 메타」** — both name `map_editor.js` for the
  load path; `fetchGridMetaFor` is unchanged but its *caller* is now `resolveDeclaredGridMeta`, and
  the "확인 못 함 ≠ 선언 없음" contract (`MAP_EDITOR_SPEC §5.0`) now has a single named home.
- **Row 58 「유효 다이 맵(M4)」** — the ordering block stayed inline and is unchanged; no edit owed.
- 🔴 **`docs/architecture/PRIMITIVES.md:304`** says *「`loadExistingMap`의 메타 없는 맵 📐 표준
  분기 — … 지금은 `startX = minX`」*. That branch is now **`resolveGridFrame`**. The sentence is
  still true of the load path but names the wrong function; it is the one line this round made
  stale.
- `docs/architecture/CODE_MAP.md` — 7 new module-scope symbols and a re-anchored `loadExistingMap`
  (code-mapper's lane; that lane is live and was not touched).
- `docs/process/DESIGN_TRACKS.md` R4 row — lead-PM owned board, not touched.

## 14. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. **A mutation anchor is a scope, not just a string.** `standard_frame_origin`'s D0/D2 inject code
   that reads `userChoice`, `minX` and `minY`. Any refactor that changes what is *in scope* at an
   injection point breaks the mutation even when the anchor text is re-pointed perfectly — and the
   harness reports it as `MUTATION DID NOT APPLY`, i.e. an unscored axis while the baseline stays
   green. **Before moving a block, read the mutations that anchor inside it and ask what identifiers
   their injected code needs, not just whether the anchor string survives.** That question, and not
   the write-set table, is what kept the cell-placement loop where it is.
2. **"Pass module state in as a parameter of the same name" is what makes a vm-sliced refactor
   safe, not just clean.** Because every step took what it needed, the decomposition introduced
   **zero** new free identifiers, so not one of the three sandboxes needed a new declaration — the
   re-point was purely additive to a list of names. R3 measured the opposite cost (threading a
   binding into a *callee* makes seven sandboxes evaluate a new identifier). The difference is
   direction: **pulling state down into a parameter is free in the sandboxes; pushing it out into a
   callee's argument list is not.**
3. **When a decomposition names a piece, check whether the newly-named piece was ever scored — and
   prove the answer against the OLD source.** `restoreDoeDraftWithPrecedence` turned out to be
   unscored by every harness and every contract. The temptation is to read that as "the refactor
   lost coverage". Running the same defect against `git show HEAD:`'s inline version showed the gap
   was already there. **A coverage claim about a refactor is only meaningful as a differential.**
