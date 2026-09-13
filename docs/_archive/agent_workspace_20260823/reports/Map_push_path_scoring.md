# The ⚡ Push path, scored — reviving the only end-to-end scorer and putting nine defects under it

**Author**: map-pm · **Date**: 2026-08-04 · **Base**: `6b150d3` · **Commit**: `ef153c0` (not pushed)

**Nine of nine are scored.** Each goes red individually, is named when it does, and escapes
every assertion that existed before this round. Two control mutants escape everything.
**No product code changed.**

| measure | before | after |
|---|---|---|
| `effort_instrument_harness` | **DEAD** (no `ASSERTIONS` line) | **PASS — 71 passed, 0 failed** |
| its place in the runner | `KNOWN_RED { ran: 0, failed: 0 }` | `FLOORS 71` |
| gated harnesses | 18 | **19** |
| known-red debt list | 5 | **4** |
| of the nine R6 defects caught by anything | **0** | **9** |
| control mutants caught (must be 0) | — | **0** |
| files changed | — | 2 (`effort_instrument_harness.mjs`, `check_harnesses.mjs`) |

---

## 1. Task 1 — the scorer is alive, and it is floored

`extractFunction(src, 'pushBlockingCount')` added to the slice list. That is the whole
revival. Its `KNOWN_RED` entry is gone and `FLOORS` carries `['effort_instrument_harness.mjs', 71]`.
The `why` string went with the entry; the floor is structured data, per the debt-list rule.

### 1a. `node client2/scripts/check_harnesses.mjs`, before and after — the diff is two lines

```
4c4
< ✗ effort_instrument_harness.mjs  [known red] (no ASSERTIONS line) sandbox build crashes ...
---
> ✓ effort_instrument_harness.mjs  (ran 71, failed 0)
25c25
< 23 harnesses ― 18 gated, 5 on the known-red debt list (5 still red, 0 recovered).
---
> 23 harnesses ― 19 gated, 4 on the known-red debt list (4 still red, 0 recovered).
```

**Exit 0 both sides. Every other harness's line is byte-identical** — same counts for
`copy_header_count` 151, `valid_die_head_parity_oracle` 17498, `virtual_column_render` 65, and
the four remaining known-red entries at their recorded numbers. No `[BLOCKING]`, no floor
complaint, no re-baseline note. `node client2/scripts/check_contracts.mjs` → **6 contracts, no
divergence**, exit 0.

### 1b. 🔴 The revival alone catches NONE of the nine

Measured, not assumed. Each of the nine was applied and scored against **only** the harness's
original A+B assertions (11 + 8 = 19), in a scratch copy:

```
I1    ESCAPED  (all 19 unchanged)     I3b   ESCAPED  (all 19 unchanged)
I1b   ESCAPED  (all 19 unchanged)     I4    ESCAPED  (all 19 unchanged)
I2    ESCAPED  (all 19 unchanged)     I5    ESCAPED  (all 19 unchanged)
I2b   ESCAPED  (all 19 unchanged)     I5b   ESCAPED  (all 19 unchanged)
I3    ESCAPED  (all 19 unchanged)
```

So R6 §7d's estimate was right about the revival and wrong about what it buys: the missing
name was the reason the file measured *nothing*, but the 28 assertions it restores are about
the **effort instrument** and the **frame stack**, not about the orchestration. Group G below
is doing all of the new work. (Scratch copy only; no repository file was mutated on disk —
`git hash-object client2/src/map_editor.js` is unchanged at `a77378e6…`.)

---

## 2. Task 2 — the nine red/green pairs

Group **G**, 19 assertions, all inside the revived harness (no new file: a second scorer for
the same path is a second thing to keep alive). Every mutation is an in-memory string
transform of the source — the working tree is never written, so the **green side of every
pair is the harness's own headline run** (`PASS — 71 passed, 0 failed`) and the **red side is
the line printed for that mutant**. Both are produced on every invocation, which is what
makes them a standing pair rather than a one-time measurement.

| # | defect re-injected | assertion that bites | red value it produced |
|---|---|---|---|
| **I1** | ① the log-shaped **BLOCK** never refuses | `G1` requests, `G3` confirms | `G1 became 2; G3 became 1` |
| **I1b** | ① a declined `map_push_ok` confirm proceeds anyway | `G19` requests\|confirms | `G19 became "2\|2"` |
| **I2** | ② an empty metadata panel is accepted | `G5` requests\|alerts | `G5 became "2\|1"` |
| **I2b** | ② number-declared metadata columns written as strings | `G7` typed value on the wire | `G7 became "string:\"7\""` |
| **I3** | ③ the pushed spec loses the frame origin | `G9` the whole `grid_metadata` record | `grid_start_x:0, grid_start_y:0` (was `3`, `-2`) |
| **I3b** | ③ the declaration is destroyed (`valid_die_ref` raw not carried) | `G11` | `G11 became undefined` |
| **I4** | ④ the split-description gate never refuses | `G12` requests\|confirms | `G12 became "2\|2"` |
| **I5** | ⑤ the outside-circle note is never produced | `G16` | `G16 became false` |
| **I5b** | ⑤ the note counts with the axes swapped under rotation | `G14` visual frame, `G15` coordinate list | `G14 became "11x9"`; `G15` mask redrawn |

Green side, same run: `G1..G19` all `ok`, `A1..A11` all `ok`, `B1..B8` all `ok`, `K1..K6` all `ok`.

### 2a. What each assertion actually compares — evidence, not verdicts

- **G1/G2/G3** — with `logShapedPushDecision` returning `{mode:'block'}`, the push must produce
  **0 requests, 1 alert, 0 confirms**. The zero-confirm term is the ordering claim: gate 4 is
  first *so that the operator answers nothing on a push that cannot be allowed*. Under I1 the
  block falls through, the Clean Replace confirm fires, and two requests go out.
- **G4/G19** — the declared exception (`map_push_ok`), accepted and declined. **G19 is why
  A7 was not enough**: A7 declines *every* confirm, so a gate that ignores its own answer is
  still stopped one dialog later and the request list never moves — A7 stayed green against
  I1b. `G19` uses `confirmSeq: [false]`, which answers the gate's question **by position** and
  lets every later dialog through, so the gate's answer is the only variable. (This is the one
  place I found where an existing assertion *looked* like coverage and was not.)
- **G5/G6** — declared-but-blank stops; **no declared fields at all does not**. G6 is the
  anti-vacuity term: without it, "always refuse" satisfies G5.
- **G7/G8** — the coercion, read **off the wire**: `typeof` + value of `updates[0].updates.slot`
  in the actual cell request body. `number:7` vs `string:"7"`. G8 pins the complement (a
  string-declared column must survive untouched), so "always coerce" is not a passing fix.
- **G9** — the pushed `wafer_map_metadata` record, parsed back out of the request body and
  compared **field by field as a mapping** (key order is not behaviour). This is the record the
  next load and every overlay align through, and R6 §7e's point stands: 18,193 stored-coordinate
  assertions elsewhere cannot see it, because they compare the coordinates a cell *carries*,
  not the frame those coordinates are later read *through*.
- **G10/G11** — `valid_die_ref` **absent** when nothing is declared (the INV-1 byte-identity
  claim), and carried **verbatim** when a declaration exists and the operator did not touch the
  controls. Dropping it re-locks the map to `refused` on the next read and there is no UI that
  undoes that.
- **G12/G13** — the split gate declined and accepted. Answered by position, never by matching
  the Korean confirm text.
- **G14/G15/G16/G17** — ⑤, using the **real** transform chain (`physNum` →
  `getTransformedPhysicalConfig` → `getScreenShift` → `isCellInsideWaferFast` →
  `isCellInsideWafer`), wrapped in a recorder that adds no arithmetic. Invariant ①: there is
  one transform implementation, and stubbing it would have scored a second one.
- **G18** — the epilogue (see §2c).

### 2b. 🔴 The fixture activates every axis, and I can say by how much

Group G runs its own frame, because the A/B fixture kills three defect axes by construction
(`grid_cols == grid_rows`, `start_x == start_y == 0`):

```
cols 11 != rows 9 · chipX 2 != chipY 3 · rot 90 · side back
startX 3 != startY -2, neither zero · dia 20mm, edge margin 1mm
-> visual frame 9 x 11, 99 painted cells, all authored valid dies (M4② template state)
```

The wafer silhouette the real chain draws over that frame (`.` inside, `X` outside):

```
XXXXXXXXX   XXX...XXX   XX.....XX   XX.....XX   XXX...XXX
XXXXXXXXX   XXX...XXX   XX.....XX   XX.....XX   XXXX.XXXX   XXXXXXXXX
```
(11 rows; 30 of 99 cells inside.)

**Reading the frame the wrong way round moves 18 of the 99 cells.** That number is the answer
to "일부러 틀린 프레임으로 해석하면 몇 셀이 달라지는가", and it is not zero, so the fixture
proves something.

🔴 **And it moves ZERO from the count.** The swapped frame also leaves exactly 30 cells inside,
so ⑤'s note still reads 「웨이퍼 원 밖 셀: **69건**」 — the same sentence, byte for byte, about a
different 69 cells. An assertion on the count, or on the note text, would have seen **nothing**.
Only the per-cell list tells them apart. This is the "화면이 멀쩡한데 값이 틀린" shape in its
purest form and it is the single most useful thing this round measured.

### 2c. A tenth defect, found by building the ninth — and it was already there

Every "successful" push in this harness was **failing**. `pushMapData`'s success epilogue calls
`mapKeyListCache.delete(selectedTable)` and `console.debug(...)`; neither existed in the
sandbox, so the epilogue threw, `pushMapData`'s own `catch` swallowed it, and the run alerted
「데이터 적재 실패」 — on a push whose cells were already on the server.

**Nothing noticed for as long as the file has existed**, because A1–A11 all read state written
*before* that point (`effortCommitIfRecorded` is deliberately the last thing before the cache
line). That is byte for byte the `dde342c` incident the source comment at that very call site
records — *"every successful Push threw a ReferenceError here and everything below (including
the Split Registry legend save) never ran"* — reproduced inside the harness meant to catch it.

`mapKeyListCache: new Map()` and `console.debug` added; **G18** now scores
`alerts|toast-levels == '0|success'`, so a throw anywhere in the epilogue is red. Groups A and
B are unchanged by the fix (all 19 still green with identical values).

### 2d. Nothing was unscoreable

All nine are scored without touching product code. **I1 and I3 remain real defects** and are
untouched — they now have executable specifications waiting for their own round (§5).

---

## 3. Control mutants — both ESCAPE

| control | A | B | G | K |
|---|---|---|---|---|
| **C1** consistent rename of a `pushMapData` local (`metaRead` → `metaReadResult`, 3 sites) | escapes | escapes | escapes | escapes |
| **C2** comment-only edit inside the write path | escapes | escapes | escapes | escapes |

Each control is applied and **all four groups are re-run and compared whole**, as a mapping
(key order is the harness's own bookkeeping, not behaviour). A control that fails to apply is
itself a `FAIL` — a control that silently did nothing would "escape" for the wrong reason.

Building these caught one real defect in my own scorer: comparing whole result objects with
`JSON.stringify` made both controls fail on **key order** when `G19` was inserted next to `G4`.
That is precisely the class the controls exist to expose, found on the first run.

---

## 4. 🔴 Source-text anchoring — declared, with what breaks it

**Every mutation in this file anchors on source text**, the nine included. This is the harness's
existing technique (M1–M8 already did it) and the failure mode is loud, not silent: a mutation
that does not apply is a hard `FAIL — mutation did not apply (source drifted)`, never a pass.

The nine new anchors, and what would break each:

| # | anchor | broken by |
|---|---|---|
| I1 | `      );` + `      return false;` + `    }` + `  }` (6-space) in `confirmLogShapedPushTarget` | re-indenting or rewrapping gate 4's `alert(...)` call |
| I1b | `      )) {` + `        return false;` + `      }` (8-space) | re-indenting the `map_push_ok` confirm |
| I2 | `return { ok: false, metaValues };` | renaming `metaValues`, or changing ②'s return shape |
| I2b | `metaValues[col] = colType === 'number' ? Number(val) : val;` | **the fix round for §5 will break this on purpose** |
| I3 | `    grid_start_x: startX,` + `    grid_start_y: startY,` | renaming the locals, reordering the object literal |
| I3b | `const gridMetaOut = validDieRefPayload(gridMeta, validDieDecision,` + `    validDie ? validDie.raw : undefined);` | re-wrapping that call onto one line (the same text appears at two other sites, so the two-line form is what makes it unique) |
| I4 | `    if (!okMissing) return false;` | renaming `okMissing` |
| I5 | `    if (n > 0) outsideNote = ` | renaming `n` or `outsideNote` |
| I5b | the 3-line `isRot` / `visualCols` / `visualRows` run in ⑤ | 🔴 **a near-identical 3-line run exists at L6303–6306** using `rotation` instead of `currentRotation` at 2-space indent — the anchor is unique only because of those two differences. Unifying the two is a legitimate refactor and would silently make this anchor ambiguous |

**Recommendation for the next extraction round**: after any move, re-run this harness first.
Nine of its ten mutants now anchor inside the five step functions, so a step that moves or gets
re-indented shows up here as `mutation did not apply` before anything else notices.

---

## 5. Task 3 — the two spellings of the map key

Scored as group **K**, 6 assertions, **as a recorded defect, not a blessing**. The harness stays
green; the assertions pin the two spellings so they cannot drift further unseen, and **when the
fix lands K4 and K5 go red**, forcing the fix round to collapse each pair deliberately and on
the record.

```
K1  slot='07'    number  ->  push L1_7      | read L1_7        agree
K2  slot='7.0'   number  ->  push L1_7      | read L1_7        agree
K3  slot='1e3'   number  ->  push L1_1000   | read L1_1000     agree
K4  slot='007.5' number  ->  push L1_7.5    | read L1_007.5    🔴 DIVERGES
K5  slot='ABC'   number  ->  push L1_NaN    | read L1_ABC      🔴 DIVERGES
K6  slot='07'    string  ->  push L1_07     | read L1_07       agree (padding is data)
```

Measured against the **real** `map_key.js` (imported, not re-typed — a second implementation here
would have compared this file against itself) and the **real** `collectMetaFieldValues` /
`getCurrentMapKey` sliced out of `map_editor.js`.

**Bite proof**: the candidate fix, injected — making `getCurrentMapKey` type-coerce the way the
push path does — collapses both pairs (`K4 -> L1_7.5|L1_7.5`, `K5 -> L1_NaN|L1_NaN`) and turns
K red. So these assertions are load-bearing in exactly the direction the fix round will push.

### 5a. 🔴 Which spelling is canonical: **the TYPED one** (`L1_7.5`)

Two independent grounds, and they agree:

1. **It is what the column actually stores.** `collectMetaFieldValues`'s output is used *twice*:
   `getMapIdFromMeta(metaValues, …)` composes the identity, **and the same dict is spread into
   every cell row's `rowUpdates`**. So a `number`-declared `slot` typed `007.5` is written to
   the database as the number `7.5`. `canonicalKeyValue(7.5, 'number')` — and the server's
   mirror `map_overlay.canonical_key_value` — then answer `'7.5'`. The untyped spelling
   `'007.5'` corresponds to **no stored value anywhere**. Composing an identity that does not
   match the data is precisely the 2026-07-28 defect `canonicalKeyValue` was introduced to close
   (`map_key.js` header): the cell data opens, the meta lookup misses, and alignment silently
   degrades to identity.
2. **It is what `canonicalKeyValue` documents.** Its own contract says *"A non-integral numeric
   keeps its repr ('7.5')"*. Given the **number** `7.5` it returns `'7.5'`, matching. Given the
   **string** `'007.5'` it matches `CANON_FLOAT_RE`, computes `f = 7.5`, finds
   `Number.isInteger(f)` false, falls past the guard and hits `return s` — returning the padded
   original. `'007.5'` is a **fall-through artifact**, not an intended spelling.

**But neither spelling is right for unreadable input**, and that is a second, separate defect the
fix round must not merge into the first: `slot='ABC'` on a number column ships `Number('ABC')`
= `NaN`, `JSON.stringify` turns that into `null`, so the row stores **NULL** while the identity
reads `L1_NaN` — and *every* unreadable value collides on that one key. The untyped `L1_ABC` is
equally wrong (nothing stores `'ABC'`). `canonicalKeyValue`'s stated policy for this case is
*"an UNREADABLE value keeps its trimmed original — the lookup misses honestly instead of
inventing a key"*, and the push path is inventing one.

**The fix I would build the round on**: `getCurrentMapKey` must stop building its own dict and
call `collectMetaFieldValues` (invariant ⑥ — one reader, and naming ② in R6 is what made a
third reader visible in the first place). Separately, ② must refuse a value that is unreadable
for a `number`-declared column instead of silently writing NULL. `recordLastOpenMap()` is the
**third** reader of the same panel and reads raw strings too — it must move with the other one
or the divergence just relocates.

**This gets worse, not better, under the 2026-08-04 `slot is always int` ruling.** For integer
values the two spellings agree (K1–K3), so the ruling does not create K4/K5 — but it makes
`column_types[col] === 'number'` the common path, which means every one of the three readers now
runs through the branch where they can disagree, and the `NaN`/NULL hole above becomes reachable
by an ordinary typo in the most-used field on the panel.

---

## 6. UI complexity budget

**Net added controls: 0. Net removed: 0.** No product file was opened for writing; no panel,
mode, modal, confirm, toast or user-visible string exists that did not exist before. The read
path is untouched and the write path still asks exactly the questions it asked, in the same
order — G1–G19 are now the proof of that sentence rather than a claim about it.

---

## 7. Constraints honoured

- **No product code changed.** `client2/src/map_editor.js` verified at `a77378e6…` after the
  round; every mutation is an in-memory string transform and no defect version was ever written
  to disk.
- `git add` with **explicit paths only** — the two files above. Three other lanes have work in
  the shared tree (`docs/process/*`, `server/parsers/*`, `server/tests/*`); **none of it was
  staged, opened or touched.**
- `npm run build` **not** run; `client2/dist/**` **not** touched; `docs/**` **not** touched.
- No DB access of any kind, no browser session, no server process, no config read or written.
  No file deleted. Scratch artefacts live in the session scratchpad. **Not pushed.**
- `check_harnesses.mjs` and `check_contracts.mjs` run before and after; the only delta is the
  intended one (§1a).

---

## 8. Doc update points — listed for the doc lanes, not edited

Carried forward unchanged from R6 §14 (none of them moved this round; no product code changed):
`PRIMITIVES.md:316`, `PRIMITIVES.md:623` (gate 4), `MAP_EDITOR_SPEC.md:774`,
`MAP_EDITOR_SPEC.md` §5.0, `CODE_MAP.md`.

Two points this round **adds**:

- **`PRIMITIVES.md:623` (Gate 4)** — R6 asked for `confirmLogShapedPushTarget` to be named as
  the acting half. It can now also record that the action **is scored** (G1–G3, G19), which was
  the open half of that entry.
- **`MAP_EDITOR_SPEC.md` §5.0** — the producer of the alignment record (`buildPushGridMetadata`)
  now has a field-by-field oracle (`G9`). Worth naming beside the readers, since §5.0 is the
  section that says `wafer_map_metadata` is the only alignment basis.

A `doc_sync_pending` counter tripped during this round (45 commits since the last sweep). Not
acted on — docs are out of scope for this round and the board is lead-PM owned.

---

## 9. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. **An assertion on a COUNT cannot see a coordinate defect, even when the coordinates are what
   the count counts.** Reading ⑤'s frame the wrong way round moves 18 of 99 cells and leaves the
   total at exactly 30 inside / 69 outside — the operator sees the identical sentence about a
   different set. The existing lesson says to compare 키→값 and to report how many cells move;
   R6/R7 add the sharp edge: **the "how many move" number and the harness's own assertion must
   be about the same object.** If the assertion is a total and the defect is a permutation, the
   fixture can be perfect and still prove nothing.
2. **A harness's sandbox is a fixture, and a missing global in it is a silently disabled branch.**
   `mapKeyListCache` and `console.debug` were absent, so every "successful" push in the only
   end-to-end scorer of the write path actually threw in its epilogue and alerted failure —
   invisible for months because all 11 assertions read state written before that point.
   **After adding an assertion to a sandboxed harness, ask what the function did AFTER the last
   thing you asserted on**, and whether it got there.
3. **Reviving a dead harness is step one, not the fix.** R6 measured that one missing name left
   the write path unscored and proposed the name as the remedy. Measured this round: the revived
   28 assertions catch **zero of nine**. A dead harness tells you an axis is unscored; it does
   not tell you the axis is the one that harness covers. **Revive first to get the oracle, then
   re-run the defect set against the revived harness before believing the coverage claim.**
4. **A control mutant will find a defect in your scorer before it finds one in the product.**
   Both controls failed on their first run — not on text-pinning, but because I compared whole
   result objects with `JSON.stringify` and a newly inserted key changed the ORDER. That is the
   same class as text-pinning (comparing a representation instead of a meaning) and nothing else
   in the round would have surfaced it.
