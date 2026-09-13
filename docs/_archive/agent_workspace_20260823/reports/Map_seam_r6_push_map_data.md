# map_editor.js refactoring — Round 6: `pushMapData`, decomposed in place

**Author**: map-pm · **Date**: 2026-08-04 · **Base**: `cafd61f` · **Commit**: `4a0c402` (not pushed)

**Verdict: the round is complete and self-contained. TEMPORARY EXPORTS: NONE** — nothing was
exported, no new module was created (§8).

---

## 0. The structural numbers

| measure | before | after |
|---|---|---|
| `pushMapData` total lines | **432** | **328** |
| `pushMapData` code lines (non-blank, non-comment) | 288 | **205** |
| named steps it is written in terms of | 0 | **5** |
| module-state bindings each step reads or writes | — | **0, all five** |
| module-state bindings `pushMapData` still owns | 14 | **14 (unchanged, by design)** |
| longest single step | — | **34 lines / 34 code** (`confirmLogShapedPushTarget`) |
| longest remaining inline run inside the orchestrator | 432 | **174 lines / 104 code** (L5474–5647) |
| `map_editor.js` | 9,334 | **9,420 (+86)** |

`git diff --numstat client2/src/map_editor.js` → **+207 / −121**.

**The +86 is the expected sign** (+90, +81, +86 across R4/R5/R6) and nothing was optimised for
it: five signatures, five return statements, five doc headers, a 32-line banner recording what
must never be cut, and the re-binding lines at five call sites cost more than the braces they
replaced.

**The longest remaining run is the pinned tail, not a shortfall.** L5474–5647 is the final
confirm → button state → `console.group` → the `wafer_map_metadata` PUT → the cell payload →
the cell PUT and its success epilogue. Every one of those blocks is held either by an indented
mutation anchor or by a module write (§2). 104 of its 174 lines are code.

---

## 1. Per-function and per-block write-set measurement, taken before the cut

AST parse via `vite.parseAst` (oxc), scope-aware walker; direct assignment, update expressions,
member assignment rooted at the binding, and mutating method calls each counted. Re-measured on
`cafd61f`; no number inherited.

### 1a. The whole function, before

```
pushMapData  L5320-5751 (432 lines)
  READ   : currentRotation currentSide el gridCells2D gridData legend loadedIdentity
           mapKeyListCache selectedTable tableSchema validDie                     (11)
  WRITE  : framePushed legendDirty serverCellKeys                                  (3)
  MUTATE : el mapKeyListCache                                                      (2)
  STATE# : 14
```

### 1b. Per-block — the table that decided where the cuts go

Ranges on `cafd61f`. `NEEDS` counts the function's own locals a block reads; those become
parameters. `PROVIDES` counts locals it declares that are read after it; those become the
return value.

| block (L) | what | MODULE R / W / M | STATE# | NEEDS | PROVIDES | verdict |
|---|---|---|---|---|---|---|
| 5321–5365 | gate 4: log-shaped push target | `el` `selectedTable` `tableSchema` / — / — | 3 | — | — | → ① |
| 5366–5378 | identity-mismatch confirm | `loadedIdentity` / — / — | 1 | — | — | **inline** (§2e) |
| 5379–5396 | metadata panel read | `tableSchema` / — / — | 1 | — | `metaValues` | → ② |
| 5398–5410 | column + type + frame reads | `el` `tableSchema` / — / — | 2 | — | 11 locals | **inline** (12 lines of `const`) |
| 5412–5439 | grid metadata object | `currentRotation` `currentSide` `el` `validDie` / — / — | 4 | 5 | `gridMetaOut` `gridMetaStr` | → ③ |
| 5441–5470 | the serialization loop | `tableSchema` / — / — | 1 | 8 | `updates` `serializedKeys` | 🔴 **inline** (§2a) |
| 5472–5512 | contrast guard + refusal | `gridData` / — / — | 1 | `updates` | `strayKeys` | 🔴 **inline** (§2b) |
| 5513–5536 | stray cleanup confirm | `gridData` / — / — | 1 | `strayKeys` | — | 🔴 **inline** (§2b) |
| 5538–5541 | empty-payload refusal | — | **0** | `updates` | — | 🔴 **inline** (§2b — it is the END anchor) |
| 5543–5554 | split-description gate | `legend` / — / — | 1 | `updates` `valCol` | — | → ④ |
| 5556–5558 | target map id | `tableSchema` / — / — | 1 | `metaValues` | `targetMapId` | **inline** (3 lines) |
| 5559–5577 | outside-circle note | `currentRotation` `gridCells2D` `gridData` / — / — | 3 | `cols` `rows` | `outsideNote` | → ⑤ |
| 5578–5585 | the Clean Replace confirm | `selectedTable` / — / — | 1 | 3 | — | **inline** (§2e) |
| 5587–5597 | button state + log group | `el` `selectedTable` / — / `el` | 2 | 3 | `mapIdStr` `metaPushFailed` | 🔴 **inline** (§2c) |
| 5599–5631 | `wafer_map_metadata` PUT | `selectedTable` / — / — | 1 | 3 | — | 🔴 **inline** (§2c) |
| 5633–5643 | the cell payload | — | **0** | `updates` | `payload` | 🔴 **inline** (§2c) |
| 5645–5750 | the cell PUT + epilogue | 4 / 3 / 2 | 7 | 5 | — | **inline** (module writes + §2c + §2d) |

**The rule the table produced is R4's, unchanged**: a block with `STATE# 0`, or whose module
reads can be named as parameters, becomes a step; a block that *writes* module state stays
where the write is visible.

🔴 **By that rule alone, six more blocks were eligible** — 5441–5470, 5472–5536, 5538–5541,
5587–5597, 5599–5631 and 5633–5643 are all read-only or `STATE# 0`. §2 is what stopped them,
and **none of it is visible in this table**. Third round running.

### 1c. After the cut, re-measured with the same tool

```
pushMapData                     L5320-5647 (328)  READ 11 · WRITE 3 · MUTATE 2 · STATE# 14
confirmLogShapedPushTarget      L5700-5733 ( 34)  STATE# 0 · calls: logShapedPushDecision
collectMetaFieldValues          L5739-5759 ( 21)  STATE# 0 · calls: —
buildPushGridMetadata           L5773-5795 ( 23)  STATE# 0 · calls: validDieRefForPush
                                                    validDieRefPayload
confirmMissingSplitDescriptions L5800-5813 ( 14)  STATE# 0 · calls: getMissingDescValues
outsideCircleNoteForPush        L5819-5837 ( 19)  STATE# 0 · calls: validDieBasis
                                                    isCellInsideWafer
```

`pushMapData`'s STATE# is 14 both sides because the call sites still *read* every binding the
moved blocks read — they pass them in. Nothing left the orchestrator's ownership.

---

## 2. What the harnesses forced to stay inline — the standing rule from R4/R5, applied

Before cutting, every string literal ≥ 20 chars in `client2/tests/**`, `client2/scripts/**`
and `contracts/*/**` was matched against `pushMapData`'s body text, and every mutation body of
every harness that mutates `map_editor.js` was read for *what identifiers its injected code
needs, and at what indentation*.

### 2a. 🔴 The serialization loop (L5441–5470) — CANNOT move (a SOURCE-TEXT region assertion)

`copy_header_count_harness.pushLoopUsesSharedPredicate()`:

```js
const i = src.indexOf('const updates = [];');
const j = src.indexOf(GATE_START, i);          // GATE_START = 'const nonEmptyOnGrid = Object.keys(gridData)'
const body = src.slice(i, j);
return { callsShared: /eachSavableCell\(/.test(body), retypesInside: /\.inside\b/.test(body) };
```
scored by
```js
chk('INV-F2', 'pushMapData builds `updates` through eachSavableCell', w.callsShared, true);
chk('INV-F2', 'pushMapData does not re-type an `inside` predicate of its own', w.retypesInside, false);
```

The assertion is about **a region of the file between two landmarks**, not about a function.
Move the loop into a step and the region stops being the push loop — the two assertions go
**vacuous while staying green**, which is the "화면 34 · DB 33" class (invariant ⑥) the shared
predicate was introduced to close. This is the R5 §2e hostage kind, in its most dangerous
form yet: the harness never names the loop, never slices it, and greps for `pushMapData`
return only comments.

**Consequence for the step placement**: the five step definitions had to go **after**
`pushMapData` in the file, or `src.indexOf('const updates = [];')` would find a step's copy
first. Verified: all nine load-bearing anchors still resolve to exactly 1 occurrence, at the
original site (§4a).

### 2b. 🔴 The contrast gate + stray cleanup + empty check (L5472–5541) — CANNOT move

The SAME harness slices this region **as text between two exact anchors** and RUNS it verbatim:

```js
const GATE_START = 'const nonEmptyOnGrid = Object.keys(gridData)';
const GATE_END   = 'if (updates.length === 0) {';
... `\nfunction runPushGate(updates) {\n${gateSlice(src, label)}\n  return 'PROCEED';\n}`
```

`return;` inside the slice therefore means "refused", exactly as in the app, and **the alert /
confirm text is scored byte for byte** — 24 assertions across INV-F2b, INV-F2b-③ and
INV-F2b-H2, plus `copy_header_count`'s M7 mutation which anchors
`const strayKeys = unsavable.outsideStray;` inside it. Every identifier between the anchors
must exist in that sandbox: a name it does not define is `die()` — *"nothing was compared"* —
on a **green, floor-enforced** harness (floor 151).

`if (updates.length === 0) {` is the END anchor. It cannot move, be reworded, or acquire an
earlier twin.

### 2c. 🔴 The `wafer_map_metadata` PUT, the payload and the epilogue — CANNOT move

`effort_instrument_harness`'s mutations anchor on **indented** text inside them:

| mutation | anchor | indent |
|---|---|---|
| M3 | `updated_by: CURRENT_USER` / `}]` / `};` | 8 / 6 / 4 |
| M3b | `grid_metadata: gridMetaStr` / `},` | 10 / 8 |
| M1, M8 | `effortCommitIfRecorded(result);` | 6 |
| M2 | `effort: effortSnapshot()` / `};` | 4 / 2 |
| M1 | `el.btnPushMap.textContent = '⚡ Pushing...';` | 2 |

Lifting the metadata PUT to module scope re-indents M3 by one level (8→6) and M3b (10→8);
lifting the success epilogue re-indents M1/M8 (6→2). And this harness is the one that treats a
missed anchor as **fatal**, not silent:

```js
if (mutated === SRC) { fail++; console.error(`  FAIL ${m.name}: mutation did not apply (source drifted)`); continue; }
```

The `payload` literal (M2) is the one block whose indentation *would* survive the move — a
module function body is 2-space, same as `pushMapData`'s top level. It stayed anyway: it is 11
lines of literal under a 7-line comment stating that this is *the one place the map editor
reports effort*, and moving `effortSnapshot()` out of `pushMapData` would weaken a claim about
location that the comment makes on purpose.

### 2d. `mapKeyListCache.delete(selectedTable)` — NOT relocated, per the brief

It sits at **L5595** (was ~5699 pre-round; ~5609 at R3), inside `try { … if (res.ok) { … } }`,
between `notifyMapContext({ serverRead: true })` / `recordLastOpenMap()` and the Split Registry
save. Cache invalidation living inside the write path is exactly the coupling that made the
cheap seams expensive, and the source already carries the incident that proves it (`dde342c`
renamed the cache, missed this call site, and every successful Push threw a `ReferenceError`
here so the legend save never ran — found by the user in the live editor, by no harness).
**Noted, not moved.**

### 2e. Two blocks left inline by judgement, not by a harness

- **the identity-mismatch confirm (L5366–5378)** — 13 lines, one module read, and it *is* the
  write gate the brief protects. A step here would be a step whose only content is "ask the
  question", and its position relative to gate 4 is the behaviour.
- **the Clean Replace confirm (L5578–5585)** — 8 lines that consume `targetMapId`,
  `outsideNote` and `updates.length`. ⑤ took the *deciding* half (the count) and the printing
  stayed, the same split R4 made at its legend block and R5 at its operator log.

---

## 3. The step list

| # | step | lines / code | takes | returns | module state |
|---|---|---|---|---|---|
| ① | `confirmLogShapedPushTarget(tableSchema, el, selectedTable)` | 34 / 34 | the schema + the column controls | `false` = do not push | **0** |
| ② | `collectMetaFieldValues(tableSchema)` | 21 / 19 | the schema (for column types) | `{ ok, metaValues }` | **0** |
| ③ | `buildPushGridMetadata(cols, rows, startX, startY, invertY, el, currentRotation, currentSide, validDie)` | 23 / 23 | the frame + the panel + the orientation + the declaration | `{ gridMetaOut, gridMetaStr }` | **0** |
| ④ | `confirmMissingSplitDescriptions(updates, valCol, legend)` | 14 / 14 | the payload + the bound value column + the plan | `false` = the operator declined | **0** |
| ⑤ | `outsideCircleNoteForPush(cols, rows, currentRotation, gridCells2D, gridData)` | 19 / 19 | the frame + the cells | the confirm line, `''` when silent | **0** |

Six parameter names deliberately **shadow** the module binding of the same name (`el`,
`tableSchema`, `selectedTable`, `currentRotation`, `currentSide`, `validDie`, `gridCells2D`,
`gridData`, `legend`). That is the R1 trick and it buys the same two things as in R4/R5: the
moved bodies stay byte-identical, and the signature says out loud what the step depends on.
**Not one new free identifier was introduced.**

### 3a. What had to be hoisted to the caller

1. ① and ④ turn `return;` into `return false;` and gain a trailing `return true;`; the caller
   does `if (!confirmLogShapedPushTarget(...)) return;`. **The order of the two gates and the
   position of gate 4 before every dialog are unchanged** — that ordering is the behaviour,
   and the call site carries a comment saying so.
2. ② turns its `alert(...); return;` into `return { ok:false, metaValues }`; the caller does
   `const metaRead = collectMetaFieldValues(tableSchema); if (!metaRead.ok) return;` and then
   `const metaValues = metaRead.metaValues;`. The `metaInputs.length > 0` second term stayed
   inside the step, so a table with no metadata fields is still not stopped.
3. ③ returns a pair; the caller re-binds `gridMetaOut` and `gridMetaStr` under the same names,
   so the 4 downstream reads are byte-identical.
4. ⑤ returns the note; `let outsideNote = ''` became `const outsideNote = ...`. The `''` return
   is explicit so the confirm text is byte-identical when there is nothing to say (INV-1).

---

## 4. Zero behaviour change

| class | count | what |
|---|---|---|
| indentation only | **0** | ⚠️ every moved block was already at 2-space inside `pushMapData` and is at 2-space in a module function — **the five bodies are byte-identical, not merely equivalent** |
| `return;` → `return false;` + trailing `return true;` | 2 + 2 | ① and ④ |
| `return;` → `return { ok:false, metaValues }` | 1 | ② |
| new `return` statements | 3 | ②'s success exit, ③, ⑤ |
| `let outsideNote` → `const outsideNote` at the call site | 1 | ⑤ |
| signature + closing brace | 10 | one pair per step, ③'s signature wraps |
| call + re-binding lines at the 5 call sites | 11 | |
| comment blocks moved with their block | 4 | gate-4 rationale, M4①→②, M4②, Split Registry |
| comment text added | 1 | the 32-line "what did NOT move" banner (§2) |

**No math line was touched.** No null guard, default, rename or reordering was introduced.

### 4a. The strongest single oracle of the round: the literal multiset

Every string literal and template quasi of `map_editor.js`, compared as a multiset via AST
against `cafd61f`:

```
literals: A=2498 B=2498 distinct=1118 differing=0
Korean-bearing literals: 426 distinct, 0 differing
```

**Not one byte of user-visible text — alert, confirm, toast, console — moved.** Comments are
not literals, so the comment moves do not mask anything here.

And the nine load-bearing anchor strings, each still matching exactly once, at the original
site (line numbers on the post-round file):

```
1x L5412  'const nonEmptyOnGrid = Object.keys(gridData)'      (GATE_START)
1x L5462  'if (updates.length === 0) {'                        (GATE_END)
1x L5365  'const updates = [];'                                (INV-F2 region start)
1x L5414  'const strayKeys = unsavable.outsideStray;'          (copy_header M7)
1x L5566  '      effortCommitIfRecorded(result);'              (effort M1/M8)
1x L5483  "  el.btnPushMap.textContent = '⚡ Pushing...';"      (effort M1)
1x L5538  '    effort: effortSnapshot()\n  };'                 (effort M2)
1x L5507  '        updated_by: CURRENT_USER\n      }]\n    };' (effort M3)
1x L5504  '          grid_metadata: gridMetaStr\n        },'   (effort M3b)
```

The banner in §2 deliberately **describes** those anchors rather than reproducing them — a
second copy of an anchor in the same file is a landmine for the next `String.replace`.

---

## 5. Hostage harnesses — enumerated by PATH as well as by symbol

Grep for `pushMapData` **and** `client2/src/map_editor.js` across `client2/tests/`,
`contracts/*/`, `client2/scripts/`, `server/`, plus the literal-matching sweep (§2).

| file | relationship | action |
|---|---|---|
| `client2/tests/effort_instrument_harness.mjs` | **slices and executes** `pushMapData` whole | **re-pointed** — 5 names (§5b) |
| `client2/tests/copy_header_count_harness.mjs` | slices two source REGIONS by text anchor; runs one of them | **not touched** — §2a/§2b are exactly the blocks I did not cut |
| `client2/tests/standard_frame_origin_harness.mjs` | re-types `gridMeta`'s shape and **cites the source landmark in a comment** | **comment re-pointed** to name `buildPushGridMetadata` (no assertion involved) |
| `client2/tests/push_gate_harness.mjs` | slices `PUSH_SYSTEM_COLUMNS` / `getUnprotectedPushColumns` / `logShapedPushDecision` — none of which moved | not touched |
| `client2/tests/company_roundtrip_harness.mjs` | asserts `onMapGridPaste`'s text does not contain `pushMapData` | not touched (still true) |
| `client2/tests/geometry_origin_reseat_harness.mjs` | **stubs** `pushMapData() {}` | not touched |
| `client2/tests/split_registry_harness.mjs` | slices `getMissingDescValues` (unmoved) | not touched |
| `contracts/*/`, `server/`, `client2/scripts/` | no reference to `pushMapData` | not touched |

`client2/scripts/check_harnesses.mjs` was **not touched** — no floor, no `KNOWN_RED` entry, no
recorded expectation edited.

### 5a. The re-point had to keep the known-red harness dead for the SAME reason

`effort_instrument_harness` is `KNOWN_RED` with the recorded cause *"sandbox build crashes
(`pushBlockingCount` is not sliced into the vm context)"*. Without the re-point it would have
died one statement earlier, at `confirmLogShapedPushTarget is not defined` — the runner's
recorded reason would have become false without any number moving. With the re-point it dies
at **exactly the same statement as before** (`ReferenceError: pushBlockingCount is not
defined`, at the `const blocking = pushBlockingCount(unsavable);` line). Its stdout is
byte-identical; only the stack-trace line numbers in stderr move (`:304` → `:344`).

That the crash still lands *there* is itself evidence: ①②③ and the serialization loop all
executed successfully in that sandbox before it.

### 5b. Proof that the five new slice names are load-bearing

Each name was removed from the list in turn (against the revived harness of §7, so the proof
is not masked by the pre-existing death) and the harness run:

```
omit confirmLogShapedPushTarget      -> exit 1  ReferenceError: confirmLogShapedPushTarget is not defined
omit collectMetaFieldValues          -> exit 1  ReferenceError: collectMetaFieldValues is not defined
omit buildPushGridMetadata           -> exit 1  ReferenceError: buildPushGridMetadata is not defined
omit confirmMissingSplitDescriptions -> exit 1  ReferenceError: confirmMissingSplitDescriptions is not defined
omit outsideCircleNoteForPush        -> exit 1  ReferenceError: outsideCircleNoteForPush is not defined
```

**Loud, named, exit 1, never silently green.** File restored and re-run: `ASSERTIONS 28 0`.

---

## 6. Oracles — before and after

### 6a. `node client2/scripts/check_harnesses.mjs` — exit 0, stdout **BYTE-IDENTICAL**

`23 harnesses ― 18 gated, 5 on the known-red debt list (5 still red, 0 recovered). ✓ every
gated harness is green.` No `[BLOCKING]`, no `MISSING ASSERTIONS`, no floor complaint. Run
three times (base, after the cut, after all injections were restored) — identical each time.

| harness | before | after |
|---|---|---|
| availability_gross_marker | 48 / 0 | 48 / 0 |
| company_roundtrip | 84 / 0 | 84 / 0 |
| **copy_header_count** ⟵ §2a/§2b hostage | **151 / 0** | **151 / 0** |
| **effort_instrument** **[known red]** ⟵ re-pointed | no ASSERTIONS line | no ASSERTIONS line |
| effort_meter | 131 / 0 | 131 / 0 |
| geometry_origin_reseat | 46 / 0 | 46 / 0 |
| m4_symbol_extractability_probe | 15 / 0 | 15 / 0 |
| map_key_canonical | 116 / 0 | 116 / 0 |
| map_key_datalist | 53 / 0 | 53 / 0 |
| overlay_wafer_mm | 69 / 0 | 69 / 0 |
| push_gate | 15 / 0 | 15 / 0 |
| reposition_regime_probe **[known red]** | no ASSERTIONS line | no ASSERTIONS line |
| retroactive_view | 263 / 0 | 263 / 0 |
| split_registry **[known red]** | no ASSERTIONS line | no ASSERTIONS line |
| **standard_frame_origin** ⟵ comment re-pointed | **19 / 0** | **19 / 0** |
| startxy_probe | 29 / 0 | 29 / 0 |
| undeclared_identifier | 6 / 0 | 6 / 0 |
| valid_die_authoring **[known red]** | 99 / 1 | 99 / 1 |
| valid_die_frame_adoption **[known red]** | 228 / 42 | 228 / 42 |
| valid_die_head_parity_oracle | 17498 / 0 | 17498 / 0 |
| valid_die_origin_alignment | 153 / 0 | 153 / 0 |
| value_suggest_keys | 94 / 0 | 94 / 0 |
| virtual_column_render | 65 / 0 | 65 / 0 |

`virtual_column_render` is **65 on both sides this round** — the concurrent client lane's rise
that R5 had to prove landed before I started, and the runner's floor already reads 65.

### 6b. Contracts — exit 0, stdout **BYTE-IDENTICAL**

`band_arithmetic` · `blank_predicate` · `config_resolve_report` · `doe_band_rules` ·
`legend_map_scope` · `map_seam` — 6 contracts, no divergence. No contract file was opened;
`config_resolve_report` still scans the same file set (no new module this round).

### 6c. Every harness's full stdout, compared byte for byte

All 23 run individually before and after (before captured with HEAD restored **through
`git checkout`**, so the CRLF working-tree convention was preserved — `git show HEAD:` emits LF
and would have compared a different file). Exit codes identical; **22 of 23 stdouts
byte-identical.** The single exception:

| file | before → after | why |
|---|---|---|
| `undeclared_identifier_harness` | `1126 declared, 1160 referenced` → `1133, 1167` | +7 declarations (5 step functions + `metaRead` + `pushMeta`) and +7 references. **`0 undeclared` on both sides**, all 6 checks green, `ASSERTIONS 6 0` unchanged |

One stderr differs: `effort_instrument_harness` (§5a) — same error, same statement, different
stack line numbers.

### 6d. Every `--mutate` suite, byte for byte

| suite | before → after |
|---|---|
| `valid_die_frame_adoption --mutate` | **byte-identical** (26 declared · 18 applied · 8 did not apply · 18 caught by a NAMED assertion · 0 crash-only · 0 undetected) |
| `standard_frame_origin --mutate` | **byte-identical** (7/7) |
| `valid_die_origin_alignment --mutate` | **byte-identical** (10/10) |
| `m4_symbol_extractability_probe --mutate` | **byte-identical** |
| `overlay_wafer_mm --mutate` | **byte-identical** (21/21 caught) |
| `copy_header_count` (mutations run unconditionally) | **byte-identical**, `13/13 defects caught` |
| `geometry_origin_reseat`, `valid_die_authoring` | **byte-identical** |

The 8 mutations that "did not apply" in `valid_die_frame_adoption` were already dead before
this round. **This round neither killed nor revived one.**

### 6e. Stored coordinates — 0 cells moved

Cells carry their own coordinates as **values**; no key matching anywhere. Byte-identical
stdout across the harness set means every `dbX`/`dbY`, mm, mask and seat assertion is compared
against the same recorded literal on both sides:

`valid_die_head_parity_oracle` 17,498 · `valid_die_frame_adoption` 228 ·
`valid_die_origin_alignment` 153 · `copy_header_count` 151 · `overlay_wafer_mm` 69 ·
`geometry_origin_reseat` 46 · `startxy_probe` 29 · `standard_frame_origin` 19 = **18,193
value-for-value assertions, all identical**.

**Do the fixtures activate the defect axes?** Named, not assumed. `copy_header_count` — the one
harness that actually runs a piece of this function — uses `DIA 20, EM 1, CHIP_X 2 != CHIP_Y 3,
COLS 11 != ROWS 9, ROT 90, SIDE back, startX/startY 1`, and asserts `bbox minC != 0`
explicitly. `standard_frame_origin` runs `MIN_X 3 != MIN_Y −2` with one negative. So a pitch
swap, an axis swap and a dropped bbox term all remain visible in the parts of the push path
those harnesses do reach.

### 6f. 🔴 A second end-to-end oracle, obtained by reviving the dead one

`effort_instrument_harness` is the only harness that executes `pushMapData` end to end, and it
is dead (§7). In a **throwaway tree**, adding the one name its slice list is missing revives it
completely, and it then runs the real function against a real fetch log:

```
HEAD (inline pushMapData)   + the one name  ->  PASS — 28 passed, 0 failed   ASSERTIONS 28 0
R6   (decomposed)           + the one name  ->  PASS — 28 passed, 0 failed   ASSERTIONS 28 0
diff of the two full stdouts -> BYTE-IDENTICAL
```

That is 11 behavioural checks over the request list (A1–A11), 8 over frame transitions
(B1–B8), and **9 mutations all still caught**, including M3/M3b (the metadata PUT anchors) and
M1/M2/M8 (the epilogue and payload anchors) — the very mutations §2c refused to break. **No
repository file was modified to obtain this**; both trees are scratch copies.

This is the strongest zero-behaviour-change evidence the round has: the decomposed write path
produces a byte-identical request list to the inline one.

---

## 7. 🔴 THE FINDING: the write path has one executable scorer, and it covers 50 lines of 432

This is the R6 analogue of R5's M4, and it is larger.

### 7a. Nine defects put back into the five steps. **Zero caught.**

All injections went into the **real** working file, were scored against nine suites plus the
six contracts plus the revived end-to-end harness, then restored; every restore SHA-256
verified against `c6d3937a6e40b9c2…`.

| # | defect put back | copy_hdr | geometry | std_frm | align | authoring | company | push_gate | undecl | contracts | effort* |
|---|---|---|---|---|---|---|---|---|---|---|---|
| — | **baseline (clean)** | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I1 | ① the log-shaped **BLOCK never refuses** | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I1b | ① a declined `map_push_ok` confirm proceeds anyway | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I2 | ② an empty metadata panel is accepted | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I2b | ② number-declared metadata columns written as strings | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I3 | ③ **the pushed spec loses the frame origin** (`grid_start_x/y := 0`) | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I3b | ③ **the declaration is destroyed** (`valid_die_ref` raw not carried) | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I4 | ④ the split-description gate never refuses | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I5 | ⑤ the outside-circle note is never produced | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |
| I5b | ⑤ the note counts with the axes swapped under rotation | 151/0 | 46/0 | 19/0 | 153/0 | 99/1 | 84/0 | 15/0 | 6/0 | ok | 28/0 |

**Not one of the nine moved a single number, in any column, including the revived
end-to-end harness.** (`effort*` is the §6f revival, so this is not the dead harness merely
staying dead.)

### 7b. The gap predates the round — proved against HEAD's inline version

A throwaway `git worktree` at HEAD (`client2/src/map_editor.js` SHA `6cb976c7…`, verified equal
to my base — no client lane landed in between) received the **equivalent nine defects** applied
to the **inline** `pushMapData`, scored by the same suites:

```
CONTROL (HEAD inline)  BASELINE  151/0 46/0 19/0 153/0 99/1 84/0 15/0 · effort* 28/0 · contracts ok
I1 … I5b  inline       ...........  every row identical to the baseline, and identical to the
                                     corresponding R6 row above
```

**Defect for defect, identical.** The decomposition neither created nor widened the gap; it
*named* five unscored pieces. (`undeclared_identifier` reports `DEAD` in the control tree only
because a `git worktree` has no `node_modules` and it imports `rolldown/parseAst`; it is a
static reference check, not a behaviour scorer, and it is green 6/0 in the real tree both
sides.)

### 7c. Why: exactly 50 of `pushMapData`'s lines are executed by any green harness

`copy_header_count_harness`'s `runPushGate` slice is **L5412–5461 = 50 lines / 42 code**. That
is the whole of it. The other 382 lines of the original function — gate 4, the identity
mismatch confirm, the metadata read, the grid-metadata payload, the serialization loop's
typing, the split-description gate, the Clean Replace confirm, **both PUTs**, and the entire
success epilogue (`serverCellKeys` refresh, `framePushed`, `mapKeyListCache` invalidation,
the Split Registry save) — are executed by **nothing that runs**.

The collaborators are well scored — `eachSavableCell`, `classifyUnsavableCells`,
`pushBlockingCount`, `serverCellKeySet`, `getUnprotectedPushColumns`, `logShapedPushDecision`,
`validDieRefPayload`, `getMissingDescValues` all have their own assertions. **The orchestration
between them is not.** `push_gate_harness` scores 15 assertions about what
`logShapedPushDecision` *decides*; nothing scores that `pushMapData` *acts* on a `'block'`
decision. I1 revives exactly the dt_log near-miss the source records — 256 real log rows'
`dt_id`/`eventtime`/`cx`/`cy` replaced by editor cells — and every oracle in the repository
stays green.

### 7d. 🟢 The remedy is measured, and it is one string

```js
// client2/tests/effort_instrument_harness.mjs, in the extract list
extractFunction(src, 'pushBlockingCount'),
```

With that one line, the harness goes from *"sandbox build crashes ― DEAD: never reaches its
assertions"* to **`PASS — 28 passed, 0 failed`**, on HEAD and on this round's tree alike
(§6f). It has presumably been one string away since `pushBlockingCount` was introduced.

**Not applied here — MOVE, DO NOT FIX.** It flips a `KNOWN_RED` entry to green, which the
runner reacts to and which is a decision about the debt list, not a decomposition. Board
candidate, and the cheapest one on this board:

> **M5 (proposed)** — one missing name in a slice list has left the entire ⚡ Push path
> unscored. Adding `pushBlockingCount` to `effort_instrument_harness`'s extract list revives
> 28 assertions and 9 mutations (measured, both trees). Then remove its `KNOWN_RED` entry and
> give it a `FLOORS` entry of 28. Even after that, gate 4's *action*, the pushed
> `wafer_map_metadata` record, and ⑤'s note remain unscored — §7a's I1/I1b/I3/I3b/I5/I5b are
> still green against the revived harness, so a second axis is owed.

### 7e. A note on what "0 cells moved" is worth here

R5 established that the round oracle is narrower than it reads. R6 sharpens it in the other
direction: **`pushMapData` writes to the server, and the stored-coordinate oracle only covers
the coordinates.** I3 shows the pushed `wafer_map_metadata` record — the thing that decides how
the *next* load and every overlay aligns — can be zeroed with 18,193 coordinate assertions
still identical, because those assertions compare the coordinates a cell carries, not the frame
the map is later read through.

---

## 8. Temporary exports: NONE

Nothing was exported. **No new module was created**, deliberately: §7 says five of five steps
are unscored, and moving an unscored function into a new file would move it further from the
fixtures that would have to reach it. `map_editor.js` exports nothing, as before. No accessor
pair, no writable binding crosses any boundary. **The commit is independently deployable**,
including both harness re-points.

---

## 9. A second finding, reported not fixed: two spellings of the same map identity

Naming ② surfaced this. The metadata panel has **three** readers, and they do not agree:

| reader | dict it builds | key it composes |
|---|---|---|
| `collectMetaFieldValues` (the push path, ②) | **type-coerced** per `tableSchema.column_types` (`Number(val)`) | `getMapIdFromMeta(typed, schema)` |
| `getCurrentMapKey()` (L3595) | raw trimmed strings | `getMapIdFromMeta(untyped, schema)` |
| `recordLastOpenMap()` (L3496) | raw trimmed strings | (stored, not composed) |

`canonicalKeyValue` absorbs the difference for every integer-shaped value, which is why this
has never been noticed. It does **not** absorb two reachable shapes (measured, running the real
`map_key.js` in a vm):

```
slot="07"     push=L1_7      getCurrentMapKey=L1_7        same
slot="7.0"    push=L1_7      getCurrentMapKey=L1_7        same
slot="1e3"    push=L1_1000   getCurrentMapKey=L1_1000     same
slot="007.5"  push=L1_7.5    getCurrentMapKey=L1_007.5    <<< DIVERGES
slot="ABC"    push=L1_NaN    getCurrentMapKey=L1_ABC      <<< DIVERGES
```

Why it matters: `currentIdentityMismatch()` (L7234, the Push guard) compares
`getCurrentMapKey()` against `loadedIdentity.mapKey`, and `loadedIdentity.mapKey` after a push
is the **typed** spelling. On a `number`-declared map-key column holding a zero-padded
non-integer, the guard fires *"로드한 맵과 적재 대상이 다릅니다"* on the map the operator just
pushed — a confirm on the read/retry path, which is a UI-discipline violation as well as a
correctness one. The registry read/write scopes (`getCurrentMapKey` vs `mapIdStr`) split the
same way.

This is invariant ⑥ (*"같은 수를 두 곳에서 계산하지 마라"*) applied to the map key rather than a
count. **Not fixed** — it is a behaviour question about which spelling is canonical, and the
answer belongs with `map_key.js`'s owner. Board candidate.

---

## 10. What deliberately did NOT change

- **Coordinate math: not one line.** ⑤ moved `isCellInsideWafer(co.c, co.r, visualCols,
  visualRows)` and its rotation swap verbatim; nothing else in the round touches a transform.
- **The write refusal / gate behaviour.** Gate 4 is still first; the identity confirm is still
  second; the contrast gate, the stray cleanup, the empty check, the split-description gate and
  the Clean Replace confirm are in the same order with the same texts (§4a proves the texts).
- **`mapKeyListCache.delete`** — not relocated (§2d).
- **The dead module state `tables` and `isMouseDown`** — untouched, per the ruling. Both
  re-confirmed still dead at `4a0c402`.
- **No bug was fixed.** The four carried forward are still open: `normalizeBands` silently
  dropping non-object band entries (R2 §9), the dead `paintLockMessage` (R3 §7–§8), the
  unscored `restoreDoeDraftWithPrecedence` (R4 §7b), and the unmeasured mask translation
  (R5 §7b = board M4). §7d and §9 add two more.
- `client2/scripts/check_harnesses.mjs`, every `contracts/**` file, `server/**`,
  `client2/dist/**`, `docs/**` — **not opened for writing**. `npm run build` **not** run.

---

## 11. Duplication / primitives check (done before cutting)

`PRIMITIVES.md` and `DUPLICATION_LEDGER.md` read. **Clean — no new spelling of anything exists,
because no new logic was written**: all five steps are single moves of a single implementation.
Each of the five names occurs exactly once as a definition, and only in the three files this
commit touches.

Three near-misses checked explicitly rather than assumed:

- `buildPushGridMetadata` is **not** a second spelling of `frameFromMeta` (that is the
  inverse — meta → frame) nor of `applyPhysicalGeometry` (that derives cols/rows from the
  physical spec). `grid_start_x:` occurs **exactly once** in `client2/src/**`, so this really is
  the only place the record is built.
- `outsideCircleNoteForPush` is **not** a second spelling of `classifyUnsavableCells`. That
  function partitions by *savability and provenance* (off-grid / outside-retained /
  outside-stray); this one counts cells that are **inside the valid dies but outside the
  wafer circle** — a population that only exists when the basis is not the circle, and which
  `classifyUnsavableCells` does not name at all.
- `collectMetaFieldValues` IS a third reader of the same panel — see §9. That is a finding, not
  a duplication I introduced: the third reader existed inline in `pushMapData` before the
  round; naming it is what made the divergence measurable.

---

## 12. Complexity budget (UI)

**Net added controls: 0. Net removed: 0.** No panel, mode, modal, confirm, toast or
user-visible string was added, removed or altered — proved as a multiset, not asserted: 2,498
string literals, 426 Korean-bearing, **zero differing** (§4a). The write path still asks
exactly the questions it asked, in the same order. The read path is untouched. **This round is
invisible to the user.**

---

## 13. Constraints honoured

- No DB write of any kind; no server process touched; no `server/config/*.json` read or
  modified. No browser session.
- `npm run build` **not** run; `client2/dist/**` **not** touched.
- `git add` with **explicit paths only** — the three files above; never `-a`/`-A`.
- 🔴 **Three other lanes committed into the shared tree during this round** (`ba65c59`,
  `9e02e3f`, `55fb19c` — a transfer_plan doc guide, a server label-type fix, and the graph
  re-derivation). `git diff --stat cafd61f..55fb19c -- client2/` is **empty**, so no client
  file moved under me; `4a0c402` contains three files and nothing else.
- The control `git worktree` was created read-only, used, and **removed** (`git worktree list`
  verified). No build inside it.
- No file deleted. Scratch artefacts live in the session scratchpad, not the repo. **Not
  pushed.**

---

## 14. Doc update points (doc-keeper's / code-mapper's lane — listed, not edited)

Found by looking up the changed **code path** (`client2/src/map_editor.js`) in
`docs/process/DOC_OWNERSHIP.md`, per the standing rule (rows 57, 58, 74, 75 and the DOE row 41).

- 🔴 **`docs/architecture/PRIMITIVES.md:316`** — still queued from R4/R5 (says *「`loadExistingMap`의
  메타 없는 맵 📐 표준 분기」* for a branch that is now `resolveGridFrame`; the anchor has drifted
  from :304 to :316). **Unchanged by this round; still owed.**
- **`PRIMITIVES.md:623` (Gate 4)** names `logShapedPushDecision` / `getUnprotectedPushColumns` /
  `PUSH_SYSTEM_COLUMNS` — all still correct and unmoved. Worth adding that the **acting** half
  is now `confirmLogShapedPushTarget`, because §7a shows the decision is scored and the action
  is not.
- **`PRIMITIVES.md:612` (contrast guard)** names `pushMapData` for the H2 refusal. Still exactly
  right — that block is the one `copy_header_count` executes and the one §2b forbids moving.
- **`PRIMITIVES.md:47`** (`eachSavableCell`'s four consumers) still correct: consumer ① is still
  `pushMapData`'s `updates`, still inline.
- **`docs/spec/MAP_EDITOR_SPEC.md:774`** (row 「참조 → 셀 집합」) — R5's owed point, unchanged.
- **`MAP_EDITOR_SPEC.md` §5.0** (`wafer_map_metadata` is the only alignment basis) — the record
  the client writes now has a named producer, `buildPushGridMetadata`. Worth naming beside the
  reader (`fetchGridMetaFor` / `frameFromMeta`), since §7a I3 shows the producer is unscored.
- 🔴 **`docs/architecture/CODE_MAP.md`** (code-mapper's lane) — five new module-scope symbols;
  its `pushMapData` entry and any line anchors into it are now off by ~100 lines.
- `docs/process/DESIGN_TRACKS.md` / `PROJECT_STATUS.md` — lead-PM owned board, not touched.
  Two new board candidates are proposed in §7d and §9.

---

## 15. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. **A source-text assertion can be about a REGION, not a function — and then the veto is a
   placement rule.** `copy_header_count`'s INV-F2 slices `src.indexOf('const updates = [];')`
   → `src.indexOf(GATE_START, i)` and asserts on that span. It never names the loop, never
   slices it, and grepping the harnesses for `pushMapData` returns only comments. Two
   consequences generalise: the loop cannot move, **and the new step definitions had to be
   placed after the orchestrator** so no earlier copy of a landmark string exists. **After any
   in-place decomposition, re-count every anchor string's occurrences in the whole file and
   check the first one is still the original.** (R5 lesson 2 said "grep the harnesses for the
   function name used as a STRING"; R6 adds: also grep them for *the source lines themselves*.)
2. **A dead harness is not a harness you can ignore — it is the one you must revive to get an
   oracle.** `effort_instrument_harness` is the only end-to-end scorer of the write path and
   has been dead for one missing name. Reviving it *in a throwaway tree* produced this round's
   strongest evidence — byte-identical request lists from HEAD's inline and R6's decomposed
   `pushMapData`, 28 assertions and 9 mutations — **without changing one repository file**.
   **Before declaring an axis unscored, check whether a KNOWN_RED harness would have scored it,
   and revive it in scratch to find out.**
3. **When the round oracle is "0 cells moved", ask what the write path writes BESIDES cells.**
   18,193 coordinate assertions stayed identical while `grid_start_x/y` in the pushed
   `wafer_map_metadata` record was zeroed. Coordinates are values a cell carries; the frame is
   the thing the *next* read interprets them through, and no coordinate assertion can see it.
   **On a write path, enumerate the payloads, not the entities.**
4. **Naming a block is how a duplicate reader becomes visible.** ② is the third reader of the
   metadata panel and the only one that type-coerces; the divergence in §9 (`007.5` → `7.5` vs
   `007.5`) has been reachable the whole time and is invisible while the code is a nameless run
   of lines inside a 432-line function. **A decomposition's second product, after the coverage
   map, is a duplication census.**
