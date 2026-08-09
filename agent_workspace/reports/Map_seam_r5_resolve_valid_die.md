# map_editor.js refactoring — Round 5: `resolveValidDie`, decomposed in place

**Author**: map-pm · **Date**: 2026-08-04 · **Base**: `2f3fa6f` · **Commit**: `cafd61f` (not pushed)

**Verdict: the round is complete and self-contained. TEMPORARY EXPORTS: NONE** — nothing was
exported, no new module was created (§8).

---

## 0. The structural numbers

| measure | before | after |
|---|---|---|
| `resolveValidDie` total lines | **519** | **410** |
| `resolveValidDie` code lines (non-blank, non-comment) | 264 | **191** |
| named steps it is written in terms of | 0 | **5** |
| module-state bindings each step reads or writes | — | **0, all five** |
| module-state bindings `resolveValidDie` still owns | 11 | **11 (unchanged, by design)** |
| longest single step | — | **55 lines / 46 code** (`fitGridToMask`) |
| longest remaining inline run inside the orchestrator | 519 | **136 lines / 48 code** (L7809–7944) |
| `map_editor.js` | 9,253 | **9,334 (+81)** |

`git diff --numstat client2/src/map_editor.js` → **+223 / −142**.

**The +81 is the expected sign** and nothing was optimised for it: five signatures, five
return statements, five doc headers, twenty-two re-binding lines at three call sites, and two
re-pointed comments cost more than the braces they replaced.

**The longest remaining run is not a shortfall — it is the region the harnesses forbid me to
cut.** L7809–7944 is exactly the H5 dimension ceiling → chain guard → cell fetch/parse → the F8
"adopt nothing" essay → `resolveFrame` pair. Every one of those blocks is pinned by a named
mutation or a source-text assertion (§2). 48 of its 136 lines are code; the other 88 are the
three history/decision essays this file is deliberately built out of.

---

## 1. Per-function and per-block write-set measurement, taken before the cut

AST parse via `vite.parseAst` (oxc), scope-aware walker; direct assignment, update expressions,
member assignment rooted at the binding, and mutating method calls each counted. Re-measured on
`2f3fa6f`; no number inherited.

### 1a. The whole function, before

```
resolveValidDie  L7658-8176 (519 lines)
  READ   : OVERLAY_CELL_LIMIT currentRotation currentSide el gridData loadedFCells
           serverCellKeys                                                          (7 pure)
  WRITE  : boundingBoxCache cellsSeatedUnder validDie validDieResolveSeq            (4)
  MUTATE : el                                                                      (1)
  CALLS  : 21 module functions
  STATE# : 11
```

### 1b. Per-block — the table that decided where the cuts go

Ranges on `2f3fa6f`. `NEEDS` counts the enclosing function's own locals/closures a block reads;
those become parameters.

| block (L) | what | MODULE R / W / M | STATE# | NEEDS | verdict |
|---|---|---|---|---|---|
| 7663–7668 | `raw` + generation guard | — / `validDieResolveSeq` / — | 1 | `meta` | **inline** (module write) |
| 7697–7842 | the `set` closure (146 lines) | 6 / 3 / `el` | **9** | 8 | **split** → ① ② (§2a) |
| 7699–7720 | `set` prologue + seat capture | 6 / `cellsSeatedUnder` / — | 7 | — | **inline** (§2a) |
| 7744–7797 | mask-fit grid grow | `currentRotation` `currentSide` `el` / — / `el` | 3 | `maskFitNote` | → ① |
| 7800–7838 | cache clear + re-seat + net move | 5 / `boundingBoxCache` / — | 6 | 4 | **split** → ② |
| 7843–7848 | the `refuse` closure | `validDie` / — / — | 1 | `set` `stale` | **inline** (module write) |
| 7857–7859 | parse the declaration | — | **0** | 4 | **inline** (3 lines) |
| 7865–7886 | spec → binding → meta → frame | — | **0** | `ref` `refuse` | → ③ |
| 7887–7899 | H5 dimension ceiling | — | **0** | `ref` `refuse` | **inline** (§2b) |
| 7906–7912 | home key canon + chain guard | — | **0** | 4 | **inline** (§2e) |
| 7914–7936 | reference cell fetch + parse | `OVERLAY_CELL_LIMIT` / — / — | 1 | `ref` `refuse` | **inline** (§2c) |
| 7950–7951 | the two resolved frames | — | **0** | — | **inline** (2 lines) |
| 8009–8017 | projection + pre-designation screen | `el` / — / — | 1 | `ref` `refuse` | **inline** (§2e) |
| 8018–8037 | mask keys + centre + pinned shift | — | **0** | — | → ④ |
| 8050–8057 | `set('ref', …)` | — | **0** | `ref` `set` | **inline** |
| 8062–8093 | post-designation diagnosis | `currentRotation` `currentSide` `el` / — / — | 3 | 8 | → ⑤ |
| 8094–8113 | the six-point operator log | `currentRotation` `currentSide` `el` | 3 | 15 | **inline** (§2f) |
| 8115–8150 | F8 alignment toast | — | **0** | 4 | **inline** (§2d) |
| 8152–8175 | the catch | — | **0** | `ref` `refuse` | **inline** (§2d) |

**The rule the table produced is R4's, unchanged**: a block with `STATE# 0`, or whose module
reads can be named as parameters, becomes a step; a block that *writes* module state stays where
the write is visible. **The table alone would have licensed six more cuts than I made.** §2 is
what stopped them, and none of it is visible here.

### 1c. After the cut, re-measured with the same tool

```
resolveValidDie               L7658-8067 (410)  READ 7 · WRITE 4 · MUTATE 0 · STATE# 11
fitGridToMask                 L8074-8128 ( 55)  STATE# 0 · calls: frameDimBounds
                                                  getCanvasCellFromDieIndex gridDimNum
summariseReseat               L8134-8150 ( 17)  STATE# 0 · calls: —
resolveReferenceSpec          L8158-8184 ( 27)  STATE# 0 · calls: fetchMapKeySpec
                                                  fetchServedBinding fetchGridMetaFor frameFromMeta
deriveMaskKeys                L8190-8212 ( 23)  STATE# 0 · calls: —
diagnoseDesignationAlignment  L8220-8257 ( 38)  STATE# 0 · calls: getWaferBoundingBox
                                                  gridDimNum getCanvasCellFromDb
```

The orchestrator's `MUTATE: el` went to **0** — the two `el.gridCols/Rows.value` writes moved
into ① **as writes through a parameter of the same name**, not as module writes. Its STATE# is
11 both sides because it still *reads* `el`.

---

## 2. What the mutations forced to stay inline — the standing rule from R4, applied

**Before cutting I read every mutation body of every harness that mutates `map_editor.js`**
(`valid_die_frame_adoption` 26, `geometry_origin_reseat` 8, `standard_frame_origin` 7,
`valid_die_origin_alignment` 10, `valid_die_authoring` 22, `m4_symbol_extractability_probe` 6,
`overlay_wafer_mm` 1, `valid_die_head_parity_oracle` 1) and asked, for each one landing inside
L7658–8176, *what identifiers does its injected code need and at what indentation*.

**The write-set table showed none of this.** Six of the seven refusals below are invisible in §1b.

### 2a. 🔴 The `set` closure (146 lines) — CANNOT become a module function

`geometry_origin_reseat_harness`'s `designation-caches-the-record` is **two** anchored edits that
must land in **one lexical scope**:

```js
once(once(s,
  '    if (!cellsSeatedUnder) cellsSeatedUnder = seatingSnapshot();',      // L7719, 4-space
  '    if (!cellsSeatedUnder) cellsSeatedUnder = seatingSnapshot();\n    const staleRecord = cellsSeatedUnder;'),
  '    const placed = reseatCellsToStoredCoords(cellsSeatedUnder);',       // L7820, 4-space
  '    const placed = reseatCellsToStoredCoords(staleRecord);')
```

`staleRecord` is **declared at the first anchor and read at the second**. Promote `set` to a
module function and its body is 2-space, so both anchors miss; `once()` calls `die()` — exit 2,
"nothing was compared", on a **green, floor-enforced** harness. Split `set` anywhere between
those two lines and `staleRecord` is out of scope at the read.

So `set` stays a closure and both lines keep their indentation. What could leave was the 54 lines
*between* them (①) and the 14 lines *after* the second (②) — neither moves either anchor.

### 2b. The H5 dimension ceiling (L7887–7899) — LEFT INLINE

`valid_die_frame_adoption`'s **H5a** and **H5d** both anchor
`    const dimErr = frameDimError(refFrame);` at 4-space. Folding it into ③ makes it 2-space; a
plain-string `.replace` that misses does not throw — the runner prints `MUTATION DID NOT APPLY
(harness bug — this axis is unscored)` and the applied count would drop 18 → 16.

### 2c. 🔴 The reference cell fetch and parse (L7914–7936) — LEFT INLINE

Two independent locks, and the second is the R4 lesson repeating exactly:

- **N6** anchors `    if (rows.length > OVERLAY_CELL_LIMIT) {` — invariant ④, truncation demoted
  to a failure — at 4-space.
- **H5d** injects, at `    const cells = [];\n    rows.forEach(row => {`:
  ```js
  const lateErr = frameDimError(refFrame);
  if (lateErr) return refuse(ref, `${ref.table} · ${ref.mapKey}: ${lateErr}`);
  ```
  `refuse` and `ref` are a closure and a local of `resolveValidDie`. Extract the block and that
  injected code is a `ReferenceError` — H5d stops being *"the ceiling moved after the read"* and
  becomes a crash, i.e. `caught only by a crash 0` would become `1` and the axis would no longer
  be attributable to a named assertion.

### 2d. The F8 alignment toast (L8115–8150) and the catch (L8152–8175) — LEFT INLINE

`    if ((originDiffer || dimsDiffer) && !stale()) {` at 4-space is the anchor of **three**
mutations (N4, O2, and M5's third replace). `    const internal = !!e && (e.name === 'TypeError'
…` at 4-space is the anchor of **M9b** and **M9c** — the "a crash must not wear the costume of an
honest refusal" pair. Both blocks also need four `resolveValidDie` locals each.

### 2e. The chain guard and the projection call — LEFT INLINE, forced by SOURCE-TEXT assertions

`valid_die_authoring_harness` slices `resolveValidDie` **as text** and asserts on it:

```js
const resolveSrc = fn('resolveValidDie');
chk('INV-1', …, /['"]template['"]/.test(resolveSrc), false);
chk('INV-6', 'resolveValidDie runs the chain check before projecting the cells',
  resolveSrc.indexOf('validDieChainError') > 0
  && resolveSrc.indexOf('validDieChainError') < resolveSrc.indexOf('projectCellsToPhys'), true);
chk('INV-7', …, /canonicalMapKey\s*\(/.test(resolveSrc), true);
```

Move `validDieChainError(…)` or `projectCellsToPhys(…)` into a step and INV-6 stops being an
ordering claim about anything. ③ *does* take the reference-key canonicalisation with it — INV-7
survives because the **home**-key canonicalisation at L7909 sits beside the chain guard and
stayed. That was checked, not assumed: the harness is still **99 / 1**, the same single
pre-existing failure.

### 2f. The six-point operator log (L8094–8113) — LEFT INLINE, and this one is my judgement

Not forced by a harness. It is 20 lines of straight-line formatting over **25** already-computed
values; a signature that honest would be worse than the wall, and grouping them into two literal
objects would be new code rather than a move. ⑤ took the *deciding* half (the two difference
axes) and the printing stayed — the same split R4 made at its legend block.

---

## 3. The step list

| # | step | lines / code | takes | returns | module state |
|---|---|---|---|---|---|
| ① | `fitGridToMask(keys, el, currentRotation, currentSide)` | 55 / 46 | the mask + the panel + the orientation | `{ from, to, off, total }` | **0** |
| ② | `summariseReseat(seatsBefore, placed, nc, nr, gridData, loadedFCells, serverCellKeys)` | 17 / 14 | the before-set + the re-seat result + the three seat sources | `{ netMoved, note }` | **0** |
| ③ | `resolveReferenceSpec(ref)` | 27 / 19 | the reference identity (canonicalised in place) | `{ ok:true, spec, binding, refMeta, refFrame }` \| `{ ok:false, reason }` | **0** |
| ④ | `deriveMaskKeys(rawKeys)` | 23 / 13 | the projected keys | `{ maskCx, maskCy, shiftX, shiftY, keys }` | **0** |
| ⑤ | `diagnoseDesignationAlignment(refResolved, hereResolved, refMinX, refMinY, hereInvertY, el, currentRotation, currentSide)` | 38 / 27 | both resolved frames + the reference minimum + the panel | `{ box, postCols, postRows, gridCx, gridCy, dimsDiffer, originDiffer, sx, sy, zero, startRow }` | **0** |

Four parameter names deliberately **shadow** the module binding of the same name (`el`,
`currentRotation`, `currentSide`, `gridData`/`loadedFCells`/`serverCellKeys`). That is the R1
trick and it buys the same two things as in R4: the moved bodies stay byte-identical, and the
signature says out loud what the step depends on. **Not one new free identifier was introduced**,
so neither sandbox needed a new declaration — the re-point was purely additive to a name list.

### 3a. What had to be hoisted to the caller

1. `maskFitNote = fitGridToMask(…)` — ① returns the note, the caller assigns it. The
   `if (keys && keys.size > 0)` guard stayed at the call site, so a `null` note still means
   "no mask, nothing measured", exactly as before.
2. `placementNote` — ② returns `{ netMoved, note }` and the caller keeps
   `if (moved.netMoved > 0) { placementNote = moved.note; if (basis !== 'ref') console.log(…); }`.
   **The `netMoved > 0` branch was deliberately not collapsed into `if (note)`**; that would have
   been an equivalence argument rather than a move (R4 §4c).
3. Three `return refuse(ref, …)` in ③ became `return { ok:false, reason }`, and the caller does
   `if (!rspec.ok) return refuse(ref, rspec.reason);`. `refuse` writes module state and stays with
   the orchestrator that owns those writes.
4. `dimsDiffer` / `originDiffer` — ⑤ computes both, the caller assigns both. Their `let`
   declarations and the comment explaining that the two axes are independent stayed at the top of
   the function, where the F8 toast reads them.

---

## 4. Zero behaviour change

Every removed line reappears apart from indentation, with these classes of forced edit and no
others:

| class | count | what |
|---|---|---|
| indentation only | ~155 | blocks moved from 4–10 spaces inside a closure to 2–6 at module scope |
| `return refuse(ref, X)` → `return { ok:false, reason: X }` | 3 | ③'s refusals |
| `maskFitNote = {…}` → `const maskFitNote = {…}` | 1 | ① now declares it locally and returns it |
| `placementNote = …` → `note = …` + `let note = ''` | 2 | ② returns instead of assigning a closure variable |
| `let dimsDiffer/originDiffer = null` inserted | 2 | ⑤ declares what it used to assign into a closure |
| new `return` statements | 5 | one per step |
| signature + closing brace | 11 | one pair per step, ⑤'s signature wraps |
| call + re-binding lines at the 5 call sites | 27 | |
| comment text edited | 2 | ① 's "must stay inline" note re-pointed (§5a); ③'s call site gained a one-line pointer |

**No math line was touched.** No null guard, default, rename, or reordering was introduced. The
placement of `getCanvasCellFromDb`, `getCanvasCellFromDieIndex`, `projectCellsToPhys`,
`getWaferBoundingBox` and `resolveFrame` calls is unchanged relative to each other.

---

## 5. Hostage harnesses — enumerated by PATH as well as by symbol

Grep for `resolveValidDie` **and** `client2/src/map_editor.js` across `client2/tests/`,
`contracts/*/`, `client2/scripts/`, `server/`.

| file | relationship | action |
|---|---|---|
| `client2/tests/geometry_origin_reseat_harness.mjs` | **slices and executes** it (`SYMBOLS`, `die()` on missing) | **re-pointed** — 5 names |
| `client2/tests/valid_die_frame_adoption_harness.mjs` | **slices and executes** it (`SYMBOLS`, `die()` on missing) | **re-pointed** — 5 names |
| `client2/tests/valid_die_authoring_harness.mjs` | slices its **source text** for INV-1/6/7 | **not touched** — the three assertions were kept true by §2e |
| `client2/tests/standard_frame_origin_harness.mjs`, `startxy_probe.mjs`, `valid_die_origin_alignment_harness.mjs` | **stub** it (`resolveValidDie: async () => sandbox.validDie`) | not touched |
| `client2/tests/valid_die_origin_alignment_harness.mjs` | its `RESOLVE_FIRST` anchors the **call** in `loadExistingMap`, not the body | not touched |
| `client2/tests/virtual_column_render_harness.mjs` | slices `PUSH_SYSTEM_COLUMNS` / `getUnprotectedPushColumns` only | not touched |
| `contracts/*/`, `server/tests/`, `client2/scripts/` | no reference to `resolveValidDie` | not touched |

`client2/scripts/check_harnesses.mjs` was **not touched** — no floor, no `KNOWN_RED` entry, no
recorded expectation edited.

**No mutation anchor had to move.** Unlike R4 (which had to re-indent `FIXED_ORIGIN`), every
anchored line inside `resolveValidDie` kept its exact text and indentation, because §2 is
precisely the list of blocks I did not cut.

### 5a. The one comment that had to be re-pointed

The source itself carried the claim I was about to break:

```
// ⚠️ **인라인이다.** 헬퍼 함수로 빼면 `resolveValidDie`를 슬라이스해 실행하는 하네스가
//    모듈 전역 의존 하나 때문에 ReferenceError로 죽는다(§getDieIndex 의 같은 경고).
```

It is replaced, not deleted: the new note quotes the old claim, names the two SYMBOLS lists that
pay for it, and records that omitting a name is **loud** rather than silently green.

### 5b. Proof that the re-pointed slice lists are load-bearing

The five names were removed from each list in turn and the harness run:

```
geometry_origin_reseat_harness   -> exit 1
  ReferenceError: summariseReseat is not defined
      at set (evalmachine.<anonymous>:1182:19)
      at refuse (evalmachine.<anonymous>:1199:12)
      at Object.resolveValidDie (evalmachine.<anonymous>:1469:14)

valid_die_frame_adoption_harness -> ReferenceError: summariseReseat is not defined
```

**Loud, named, never silently green** — and note the frame: it fires inside `refuse`, so even the
refusal path cannot swallow it into a plausible-looking reason string. Both files restored and
SHA-256 verified.

---

## 6. Oracles — before and after

### 6a. `node client2/scripts/check_harnesses.mjs` — exit 0 both runs

`23 harnesses ― 18 gated, 5 on the known-red debt list (5 still red, 0 recovered). ✓ every gated
harness is green.` No `[BLOCKING]`, no `MISSING ASSERTIONS`, no floor complaint.

| harness | before | after | Δ |
|---|---|---|---|
| availability_gross_marker | 48 / 0 | 48 / 0 | — |
| company_roundtrip | 84 / 0 | 84 / 0 | — |
| copy_header_count | 151 / 0 | 151 / 0 | — |
| effort_instrument **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| effort_meter | 131 / 0 | 131 / 0 | — |
| **geometry_origin_reseat** ⟵ re-pointed | **46 / 0** | **46 / 0** | — |
| m4_symbol_extractability_probe | 15 / 0 | 15 / 0 | — |
| map_key_canonical | 116 / 0 | 116 / 0 | — |
| map_key_datalist | 53 / 0 | 53 / 0 | — |
| overlay_wafer_mm | 69 / 0 | 69 / 0 | — |
| push_gate | 15 / 0 | 15 / 0 | — |
| reposition_regime_probe **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| retroactive_view | 263 / 0 | 263 / 0 | — |
| split_registry **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| standard_frame_origin | 19 / 0 | 19 / 0 | — |
| startxy_probe | 29 / 0 | 29 / 0 | — |
| undeclared_identifier | 6 / 0 | 6 / 0 | — |
| valid_die_authoring **[known red]** | 99 / 1 | 99 / 1 | — |
| **valid_die_frame_adoption** **[known red]** ⟵ re-pointed | **228 / 42** | **228 / 42** | — |
| valid_die_head_parity_oracle | 17498 / 0 | 17498 / 0 | — |
| valid_die_origin_alignment | 153 / 0 | 153 / 0 | — |
| value_suggest_keys | 94 / 0 | 94 / 0 | — |
| virtual_column_render | 59 / 0 | **65 / 0** | **+6 — NOT MINE, §6e** |

### 6b. Contracts — exit 0, stdout BYTE-IDENTICAL

`band_arithmetic` · `blank_predicate` · `config_resolve_report` · `doe_band_rules` ·
`legend_map_scope` · `map_seam` — 6 contracts, no divergence. No contract file was opened;
`config_resolve_report` still scans the same file set (no new module this round, which is the
point).

### 6c. Every harness's full stdout, compared byte for byte

All 23 run individually before and after; exit codes identical; **22 of 23 stdouts
byte-identical.** The single exception:

| file | before → after | why |
|---|---|---|
| `undeclared_identifier_harness` | `1118 declared, 1152 referenced` → `1126, 1160` | +8 declarations (5 step functions + 3 net new locals) and +8 references. **`0 undeclared` on both sides**, all 6 checks green, `ASSERTIONS 6 0` unchanged |

### 6d. Every `--mutate` suite, byte for byte

| suite | before → after |
|---|---|
| `valid_die_frame_adoption --mutate` | **byte-identical**: `26 declared · 18 applied · 8 did not apply \| caught by a NAMED assertion 18 · caught only by a crash 0 · undetected 0` |
| `standard_frame_origin --mutate` | **byte-identical** (7/7) |
| `valid_die_origin_alignment --mutate` | **byte-identical** (10/10) |
| `m4_symbol_extractability_probe --mutate` | **byte-identical** |
| `overlay_wafer_mm --mutate` | **byte-identical** |
| `geometry_origin_reseat` (mutations run unconditionally) | **byte-identical**, `8/8 defects caught` |
| `valid_die_authoring` (mutations run unconditionally) | **byte-identical**, 22 mutations |

The 8 mutations that "did not apply" in `valid_die_frame_adoption` (N1 N2 N3 N5 O1 O3 O4 O5) were
already dead before this round — their anchor text was replaced by `da8f390`/`61440e6`. **This
round neither killed nor revived one.** That is a pre-existing debt item, not a finding of R5.

### 6e. The one harness delta that is NOT mine, proved rather than asserted

`virtual_column_render_harness` moved 59 → 65 assertions *between* my per-harness sweep and my
runner sweep. A concurrent client-pm lane edited that harness file (+77 lines) in the shared tree.
Proof, not inference: with **`2f3fa6f`'s `map_editor.js` restored** and the lane's harness in
place, it still reports `ASSERTIONS 65 0`. My working file was restored and SHA-256 verified
(`6cb976c7eaf632e1…`). The runner classifies it as *"not a failure — raise the floor when
convenient"*, and I did **not** touch `check_harnesses.mjs`.

### 6f. Stored coordinates — 0 cells moved

Cells carry their own coordinates as **values**; no key matching anywhere. Byte-identical stdout
across the harness set means every `dbX`/`dbY`, mm, mask and seat assertion is compared against
the same recorded literal on both sides:

`valid_die_head_parity_oracle` 17,498 · `valid_die_frame_adoption` 228 ·
`valid_die_origin_alignment` 153 · `overlay_wafer_mm` 69 · `geometry_origin_reseat` 46 ·
`startxy_probe` 29 · `standard_frame_origin` 19 = **18,042 value-for-value assertions, all
identical**.

The designation path's own evidence lines, unchanged:

```
3/A2<-DT_TEST   : grid 23x23 -> 25x25, painted 273, disagree 0/273, canvas seats re-taken 27
4/DTWWER<-BASE_4E: grid 33x25 -> 33x25, painted 461, disagree 0/461, canvas seats re-taken 117
[F6/C] 45x45 <- 46x46 (identical spec, ODD -> EVEN): 2025 stored coordinates byte-identical
[F6/E] 33x25(start -4,-3) <- 29x25: 66 Push coordinates byte-identical, served set still 825
```

**Do the fixtures activate the defect axes?** Named, not assumed.
`geometry_origin_reseat` runs production metadata with `chipX != chipY` on three of five fixtures
(14.3/15.2, 9.7/13.8, 13.6/13.7), `rot 90` on DT_TEST, `offsetX 0.1`, negative starts (−3,−2),
`minC != 0`. `valid_die_frame_adoption` runs `chipX 11 != chipY 13`, `rot 90 + back`, offsets at
exactly one chip pitch (a sub-cell offset would round away and unscore the offset term), and its
own liveness guard reports **"wrong-frame reinterpretation moves 186 of 93 mask cells"** — the
count of cells that land on a different die if the reference is read with the panel's frame. That
number is not 0, on both fixtures.

---

## 7. Every step shown RED with a defect put back — and the honest result

Ten defects were injected into the **real** working file, scored against five suites plus the
contracts, then restored; every restore SHA-256-verified against `6cb976c7eaf632e1…`.

| # | defect put back | geometry | adoption | authoring | origin_align | std_frame | contracts |
|---|---|---|---|---|---|---|---|
| — | **baseline (clean)** | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I1 | ① never writes the derived dimensions to the panel | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I1b | ① never grows the grid to hold the mask (rule 1-b gone) | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I2 | ② always reports 0 seats moved | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I2b | ② measures the wrong direction (seats gained) | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I3 | ③ accepts a guessed coordinate binding | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I3b | ③ skips the 7b canonicalisation of the reference key | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I4 | ④ revives the mask translation (`shiftX = 1`) | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I4b | ④ reports the mask centre with the axes swapped | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| I5b | ⑤ solves the diagnosis with the reference grid | 46/0 | 228/42 | 99/1 | 153/0 | 19/0 | exit 0 |
| **I5** | **⑤ goes blind on the origin axis** | 46/0 | **228/44** | 99/1 | 153/0 | 19/0 | exit 0 |

🔴 **One of five steps is live in a scorer. Four are scored by nothing.** That is reported, not
hidden — and it is measured as a **differential**, per the R4 lesson.

### 7a. The gap predates the round — proved against `git show HEAD:`'s inline version

`git archive HEAD client2/src client2/tests` was unpacked into a scratch tree and the **same ten
defects** applied to the **inline** (pre-R5) `resolveValidDie`, with HEAD's harnesses:

```
HEAD BASELINE (inline, clean)  geometry=46/0 adoption=228/42 authoring=99/1 align=153/0 std=19/0
I1   inline                    ... identical
I1b  inline                    ... identical
I2   inline                    ... identical
I2b  inline                    ... identical
I3   inline                    ... identical
I3b  inline                    ... identical
I4   inline                    ... identical
I4b  inline                    ... identical
I5b  inline                    ... identical
I5   inline                    geometry=46/0 adoption=228/44 ...  ← the same one, caught
```

**Defect for defect, identical.** The decomposition neither created nor widened the gap; it
*named* four unscored pieces, which is the first thing anyone would need to close them.

### 7b. The most alarming of the four, stated plainly

**I4 — reviving the mask translation puts the mask on the wrong dies and nothing notices.** The
source comment beside `const shiftX = 0` records the measurement: with the translation, "262칸 중
21칸이 틀린 다이에 앉았다". `geometry_origin_reseat` runs exactly that fixture
(`DTWWER <- BASE_4E`) and stays 46/0 — because it asserts that **stored coordinates** hold, and a
mask shift does not move a stored coordinate. It moves the origin box, the cells re-seat, and the
coordinates are preserved by design. **The mask sitting on the wrong dies is not measured by
anything in the repository.** Board candidate; not fixed here (MOVE, DO NOT FIX).

The other three: ① 's grid growth is masked by `applyPhysicalGeometry`'s own re-derivation (the
`grid-re-derives` assertion is satisfied without it); ②'s output is a `console.log` and every
sandbox stubs `console`; ③'s two refusals need `fetchServedBinding` to answer `fallback_guess` and
`canonicalMapKey` to be more than the identity, and every sandbox stubs both.

---

## 8. Temporary exports: NONE

Nothing was exported. **No new module was created**, deliberately: extracting a step into its own
file is a later judgement, made only once a step is demonstrably pure *and scored*. All five now
measure `STATE# 0`, but §7 says four of them are unscored — moving an unscored function into a new
file would move it further from the fixtures that would have to reach it. `map_editor.js` exports
nothing, as before. No accessor pair, no writable binding crosses any boundary, nothing is
exported "for the harnesses" (they slice source text). **The commit is independently deployable**,
including both harness re-points.

---

## 9. What deliberately did NOT change

- **Coordinate math: not one line.** `getCanvasCellFromDb`, `getCanvasCellFromDieIndex`,
  `projectCellsToPhys`, `getWaferBoundingBox`, `resolveFrame`, `frameFromMeta` — every call site
  moved verbatim or did not move at all.
- **The dead module state `tables` and `isMouseDown`** — untouched, per the ruling. Both
  re-confirmed still dead at `cafd61f`.
- **No bug was fixed.** The three carried forward are still open and untouched: `normalizeBands`
  silently dropping non-object band entries (R2 §9), the dead `paintLockMessage` (R3 §7–§8), and
  the unscored `restoreDoeDraftWithPrecedence` (R4 §7b). §7b adds a fourth.
- `client2/scripts/check_harnesses.mjs`, every `contracts/**` file, `server/**`,
  `client2/dist/**`, `docs/**` — **not opened for writing**. `npm run build` **not** run.

---

## 10. Duplication / primitives check (done before cutting)

`PRIMITIVES.md` and `DUPLICATION_LEDGER.md` read. **Clean — no new spelling of anything exists,
because no new logic was written**: all five steps are single moves of a single implementation.

Two near-misses checked explicitly rather than assumed:

- `fitGridToMask` is **not** a second spelling of `applyPhysicalGeometry`. The latter *derives*
  cols/rows from the physical spec; the former *widens* an already-derived grid until a given key
  set fits, and it does so through `getCanvasCellFromDieIndex` — the very inverse the renderer and
  the re-seater use (invariant ①: one transform implementation). Neither can be expressed in the
  other's terms; they run one after the other inside `set`.
- `diagnoseDesignationAlignment` is **not** a second spelling of the deleted `adoptedFrameOf` /
  `announceFrameAdoption`. It compares and reports; it adopts nothing and writes nothing.

Each of the five names occurs exactly once as a definition, and only in the three files this
commit touches.

---

## 11. Complexity budget (UI)

**Net added controls: 0. Net removed: 0.** No panel, mode, modal, confirm, toast or user-visible
string was added, removed or altered. Every Korean UI string on the designation path is
byte-identical — the two refusal messages in ③, the F8 alignment toast with its `dedupeKey`, the
six-point `[유효다이]` operator log, and the `console.warn` about a mask that does not fit. The read
path still has exactly one confirm-free flow. **This round is invisible to the user.**

---

## 12. Constraints honoured

- No DB write of any kind; no server process touched; no `server/config/*.json` read or modified.
- `npm run build` **not** run; `client2/dist/**` **not** touched.
- `git add` with **explicit paths only** — the three files above; never `-a`/`-A`.
- 🔴 **Two other lanes committed into the shared tree during this round** (`b54b7b4`,
  `8817dde` — client search scope and `server/transfer_plan.py`). `8817dde` landed *while my
  index was staged*; it used explicit paths, so my three files were not swept into it — verified
  by `git show --stat 8817dde`. `cafd61f` contains three files and nothing else.
- No file deleted. Scratch artefacts live in the session scratchpad, not the repo. **Not pushed.**

---

## 13. Doc update points (doc-keeper's / code-mapper's lane — listed, not edited)

Found by looking up the changed **code path** (`client2/src/map_editor.js`) in
`docs/process/DOC_OWNERSHIP.md`, per the standing rule.

- 🔴 **`docs/architecture/PRIMITIVES.md:304`** — still queued from R4 (names `loadExistingMap`
  for a branch that is now `resolveGridFrame`). **Unchanged by this round; still owed.**
- **`docs/spec/MAP_EDITOR_SPEC.md:774`** (row 「참조 → 셀 집합」) maps the client operation to
  `resolveValidDie`. Still correct, but the operation now has five named sub-steps worth naming
  beside it — `resolveReferenceSpec` is literally the
  `fetchMapKeySpec → fetchServedBinding → fetchGridMetaFor → frameFromMeta` chain the spec header
  describes in prose.
- **`MAP_EDITOR_SPEC.md:858–860` (§5.7-bis)** — 「반응은 함수 하나입니다 —
  `reseatCellsToStoredCoords(was)`」 and the four call sites. **Still accurate**: `set()` still
  exists and still makes that call; only the *summary* of it moved. No edit owed.
- **`MAP_EDITOR_SPEC.md:799–800, 808`** — the `boundingBoxCache` clearing rule and the "①→②→③"
  history block. Both stayed inline verbatim. No edit owed.
- 🔴 **`docs/architecture/CODE_MAP.md`** (code-mapper's lane, live) — five new module-scope
  symbols; and its `resolveValidDie` entry cites line anchors `~7568`, `~7722–7723`, `~7730`,
  `~7741` that were already stale before this round and are further out now.
- **`CODE_MAP.md:1462`** attributes `valid_die_authoring`'s single failure to INV-6's
  `indexOf`-based ordering check. **Re-confirmed still the same single failure at `cafd61f`** —
  worth recording that §2e of this round is exactly why that assertion still measures what it
  claims to.
- `docs/process/DESIGN_TRACKS.md:150` (the R5 row) — lead-PM owned board, not touched.

---

## 14. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. **The write-set table licenses cuts; only the mutation bodies veto them.** In R5 the per-block
   table showed six more `STATE# 0` blocks than I cut. Six refusals came from reading mutations:
   two anchored lines that must share a scope (`staleRecord`), an injected `return refuse(ref, …)`
   that needs a closure and a local, three anchors that must keep a 4-space indent, and three
   **source-text** assertions (`indexOf`, `RegExp`) on the sliced function. R4 found this once and
   called it a standing rule; R5 confirms it generalises — **the veto is never in the write set.**
2. **A source-text assertion is a third kind of hostage, and grep for the symbol will not find it.**
   `valid_die_authoring_harness` never executes `resolveValidDie`; it slices its text and asserts
   `indexOf('validDieChainError') < indexOf('projectCellsToPhys')`. That pins two call sites into
   one function body forever, and neither `SYMBOLS` nor a stub list mentions it. **Before cutting,
   grep the harnesses for the function name used as a STRING, not only as a slice target.**
3. **"Which steps are scored" is only meaningful as a differential against the pre-cut source.**
   Four of five R5 steps are scored by nothing. Read alone that is "the refactor lost coverage";
   applying the same ten defects to `git archive HEAD`'s inline version returned *identical*
   numbers, so the gap predates the round. **A decomposition's true product is often a coverage
   map, and the map is worthless without the control run.** (R4 learned this on one step; R5 on
   four, using a throwaway HEAD tree rather than in-place restores — safer in a shared tree where
   two other lanes were committing.)
4. **In a shared tree, an unexplained oracle delta is a lane, not a bug — but prove it.**
   `virtual_column_render` moved 59 → 65 between two of my own runs. The cheap proof is to restore
   the base version of *my* file and re-run: if the number does not move, it was never mine.
