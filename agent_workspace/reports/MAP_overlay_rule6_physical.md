# Map rule 6 — overlay by WF-internal physical position (client-only)

**Round:** 2026-07-31 · map-pm · client only, `server/map_overlay.py` untouched
**Files changed:** `client2/src/map_editor.js` (+311/-52) · `client2/tests/overlay_wafer_mm_harness.mjs` (new, 500 lines) · `client2/tests/geometry_origin_reseat_harness.mjs` (+5/-2, symbol list) · `client2/tests/valid_die_authoring_harness.mjs` (+3/-1, symbol list) · `client2/dist/**` (build)
**Not committed.** Nothing staged.

---

## 1. The design

### 1.1 Where the millimetre space lives

It lives **inside `getDieIndex`**, and it got there by that function returning a value it had
already computed and was discarding.

`getDieIndex` ends with

```js
const xp = Math.round(xRot + (Math.abs(Math.round(cols)) % 2 === 0 ? 0.5 : 0));
```

`xRot` is the cell's position from the wafer centre, **de-rotated, un-mirrored, offset
applied, in units of `chipX`** — continuous. Rounding it produces the die index. The round
now returns both:

```js
return { x: xp, y: yp, xCells: xRot, yCells: yRot };
```

`xCells * chipX` is millimetres from the wafer centre in the wafer's own axes. That is the
whole mm space. There is **no new transform**: rotation, side flip and offset are still
implemented exactly once, in `getDieIndex`, and the addition is a multiplication by the
declared (unrotated) chip pitch.

> **This is not the multiplication rule ⑤ forbids.** Rule ⑤ (`docs/spec/MAP_EDITOR_SPEC.md`
> §0) forbids `dbX * pitch`, and it is right to: a stored coordinate is
> `c − box.minC + startX`, an origin-relative cell count carrying a bounding box and a START
> declaration. A die index is a different quantity — since `35e84c3` its origin is the wafer
> centre and its unit *is* the chip pitch. The renderer already performs the identical
> conversion when it draws the wafer circle at `effectiveRadius / chipX` cells.

### 1.2 Why the rounded index is not enough — the sub-cell residual

My first implementation reconstructed mm as `(ix − parity) * chipX` and it was wrong on
**1789 of 1836** cells. The reason is worth recording because it is invisible:

`xRot + parity` equals `c + K` for a per-frame constant `K`, so the die index is
`c + round(K)`. The residual `K − round(K)` — the part of the physical offset smaller than
one chip — is swallowed by the rounding and **cannot be recovered from the index**.
Rebuilding it would mean writing the rotation/side offset sign table a second time. That
table is exactly what `server/map_overlay._frame_phys_params` needed a QA round and a proof
table to get right; a second copy in the client is the defect this domain exists for.

So the client asks `getDieIndex` instead. One call on canvas cell `(0,0)` per frame yields
the whole lattice, because a die lattice is spaced exactly 1:

```js
function frameDieLattice(frame)   // -> { ix0, iy0, ux0, uy0, chipX, chipY }
function dieIndexToWaferMm(ix, iy, L)          // die centre -> absolute wafer mm
function waferMmToDieCell(mmX, mmY, L)         // -> { ix, iy, rx, ry }
```

`waferMmToDieCell` contains no parity term, no rotation branch and no offset branch. All
three live in the reference it was handed.

### 1.3 The projected payload

```
layer.mmItems : [ { srcX, srcY, ix, iy, mm:{mmX,mmY}, val } ]     // frame-invariant
      ↓ seatWaferMmInFrame(mmItems, resolveFrame(currentFrame()))
layer.items   : Map( "ix_iy" -> [ { val, rx, ry, mmX, mmY, srcX, srcY } ] )
layer.cells   : Map( "ix_iy" -> val | null )       // null == several values, no representative
layer.count / cellCount / fanout / multiCells / outside / seatNote / seatAxes / seatChip
```

`mmItems` is absolute wafer millimetres and is computed **once**, at add time. The seat is a
function of the on-screen frame and is recomputed by `reseatOverlayLayer` — the same function
`addOverlayLayer` and `syncOverlayGeometry` both call, so the numbers reported on the layer
row can never describe a frame that is no longer on screen.

**The seating frame is the current screen frame, not the registered target spec.** The render
loop reads the screen; seating anywhere else puts markers on keys the canvas never produces.
`tgtResolved` is now used only for the alignment report.

**N:1 is ⓒ "list them all".** `layer.items` maps a target cell to an **array**. `layer.cells`
keeps the old shape for membership tests (paint lock, marker hit-test) and holds `null` — not
a representative — when the array has more than one entry. `importOverlayToGrid` skips those
cells and counts them; `gridData` holds one value per cell, so importing would require
choosing, which is the discard the user ruled out.

### 1.4 How the remainder is carried

`waferMmToDieCell` returns the division intact: `ix` is the quotient, `rx` is the remainder in
`[0, chipX)` **millimetres**. Every item keeps `rx`/`ry` (in-chip) *and* `mmX`/`mmY`
(absolute), even though the current build renders only position.

The remainder is scaled to mm rather than left as a fraction on purpose: it is an absolute
length, so 3 mm inside a 7 mm chip is not the place 3 mm inside a 15 mm chip is. Harness
assertion **A5** executes that statement — the same wafer point yields different remainders in
the two frames — so a later round cannot "optimise away" the absolute-mm round trip and carry
in-chip coordinates directly between maps.

### 1.5 The gate that changed

Old (`map_editor.js`, removed): refuse when `srcResolved.cols/rows !== tgtResolved.cols/rows`,
`"같은 웨이퍼 규격이 아니면 물리 좌표를 맞출 근거가 없습니다"`. Under rule 6 different cell
sizes imply different grid dims, so that gate refused precisely the case the rule is about.

New: refuse only when a chip pitch cannot be established (`chipX > 0 && chipY > 0` on both
sides). Without a pitch there is no length, and therefore no "physical position in the wafer".

### 1.6 Rendering, and the UI checkpoint

**No new panel, mode, modal or control was added. Net control delta: 0** (`git diff | grep`
for `document.getElementById|addEventListener|<button|<input|<select|confirm(` over
`map_editor.js` returns **zero** added or removed lines; `map_editor.html` is untouched).

- **1:1 draws exactly as before** — one dot per layer, top-right corner, unchanged pixel for
  pixel.
- **A target cell receiving several source chips draws one dot per chip, at each chip's own
  in-chip position.** Same marker layer, same colour, more dots. This is the "list" — 4 chips
  from a 7 mm source inside a 15 mm target cell appear as a 2×2 arrangement spaced 7 mm and
  5 mm apart, which is where they physically are.
- Screen placement of the sub-dots does **not** re-implement rotation. `reseatOverlayLayer`
  reads the 2×2 physical→screen matrix off `getCanvasCellFromDieIndex` by differencing its
  answers for `(0,0)`, `(1,0)`, `(0,1)`. Entries are 0/±1 and the parity term cancels.
- Cells too small to hold several dots (`cellW < 10px`) fall back to the single existing dot
  rather than inventing positions.
- Status only, no interaction: the layer row shows `2478칩→600칸` and a `최대 6:1` chip using
  the existing `ov-chip` class. **+1 status label, +0 controls.**

**🔴 THE ONE THING I AM ESCALATING.** Positions and counts are visible; the **values** are
not. A dot is coloured by *layer*, so an operator sees that a coarse cell received 6 chips and
where they sat, but cannot read what those 6 values were. Options, none of which I built:

| | Option | Cost |
|---|---|---|
| **(a)** | Colour the sub-dots by the value's legend colour (`cellFillColor`) instead of the layer colour, in fan-out cells only | 0 new surface. Colour changes meaning inside those cells (layer identity → value); ambiguous with two layers overlapping |
| **(b)** | Hover readout of the item list | Requires a text surface the canvas does not have today — **a new surface**, so I stopped |
| **(c)** | Ship as-is: position + count visible, values in `layer.items` only | 0 new surface, 0 new anything. What is in the tree now |

I shipped (c). (a) is a one-function change if you want it; (b) needs your ruling first.

---

## 2. What I measured, and how

Method: the coordinate functions are lifted out of `client2/src/map_editor.js` by source-text
slicing and executed in a `node:vm` sandbox with a fake DOM — the same technique the four
existing coordinate harnesses use. Expectations come from an independent millimetre model
(cells are mm rectangles, the wafer is a mm circle, and the containing target cell is found by
**scanning every target cell**, not by dividing). The model is itself anchored: it reproduces
`getWaferBoundingBox` exactly for both fixture frames (assertion A1), a quantity that predates
this round and already governs stored coordinates.

Fixture, chosen so no defect axis is dead: source **42×59** grid, **7×5 mm** chip, rot **90**,
**back**, start (1,2); target **20×30** grid, **15×10 mm** chip, rot **0**, front, start
(3,−2), invert-Y. Anisotropic chips with different per-axis ratios (15/7 vs 10/5); X parity
even/even but **Y parity odd/even**; offsets non-zero, different, one negative.

**Every number below I measured myself. None is quoted from a commit message, the board, or a
comment.**

### 2.1 The rule-6 hole is real, and it is narrower than "silently wrong everywhere"

| Case | Shipped behaviour | Measured |
|---|---|---|
| different pitch **and** different dims (the 7 mm-over-15 mm pair) | **refused** by the dims gate (`align_unavailable`) | never drawn, so never wrong — it was impossible |
| different pitch, **same declared dims** (20×30, 7×5 mm vs 15×10 mm) | gate **passes**, projects die index → die index | agrees with physical truth on **4 of 600** cells |

So the accurate statement is: the common pair was **refused**, and the coincident-dims pair was
**silently wrong on 596 of 600 cells**. I recommend the board say it that way.

### 2.2 Fan-in is not hypothetical — and the number depends entirely on the configuration

🔴 **Do not pin a single fan-in number.** It is a function of the pitch ratio, the grid
parity and the offsets. Three configurations, each measured, each labelled:

| Configuration | Source cells | → target cells | max fan-in |
|---|---|---|---|
| **synthetic fixture** 7×5 mm @ 42×59, rot 90/back → 15×10 mm @ 20×30, rot 0/front/invertY | 1836 | 458 | **6** |
| **synthetic same-dims** 7×5 mm @ 20×30 → 15×10 mm @ 20×30 (the gate-passing hole) | 600 | 160 | **6** |
| **dominant live pair** (QA's derivation from 217 `wafer_map_metadata` rows: 162 maps 7×7 mm @ 40×40, 23 maps 15×15 mm @ 23×23), rot 0/front both | 1288 | 297 | **9** |

The synthetic fixture is anisotropic and rotated *on purpose* — it exists to keep defect axes
alive, not to model production. The live pair is isotropic at a 15/7 ratio, which is why its
fan-in is higher. My earlier report said "max fan-in 6" without naming the configuration; that
was the synthetic fixture only.

A representative would have discarded up to **8 of 9** values on the live pair while displaying
the ninth confidently.

### 2.3 A pre-existing defect I found on this path and fixed

The `outside` counter in `addOverlayLayer` tested `0 <= px < cols && 0 <= py < rows`. Die
indices have been **wafer-centre-relative since `35e84c3`** — measured range on the 20×30
target: `x[−9..10] y[−14..15]`, and only **176 of 600** canvas cells satisfy that predicate at
all.

Consequence, measured on an **identity** overlay (source frame == target frame, nothing
misaligned): 402 cells, all 402 on real canvas cells, and the chip reported
**`격자 밖 277칩 — 웨이퍼 격자를 벗어나 가져오기에서 제외됩니다`**. Truth: 0. That note has
been false on essentially every overlay in the product.

Replaced by `canvasDieKeySet(frame)` — the set of keys the canvas actually produces — cached
on the full resolved frame-axes key. Assertion **A9d** holds it; mutation "stale predicate
restored" reproduces **277 of 402** exactly.

### 2.4 Discrimination — how much a deliberately wrong frame moves

If these were 0 the fixture would prove nothing:

| Wrong interpretation | Cells that move (of 1836) |
|---|---|
| read the target with the **source** pitch | **1832** |
| swap the target's `chipX`/`chipY` | **1806** |
| flip the target's row **parity** (30 → 31) | **925** |

### 2.5 Mutation sweep — 13 declared, 13 applied, 13 caught

Reverting each defect turns the harness red. The sweep is unconditional (no `--mutate` flag to
forget) and reports APPLIED separately from CAUGHT, so a stale pattern is a visible hole rather
than a pass. Two are worth naming:

- *"mm rebuilt from the rounded die index (sub-cell residual lost)"* → 338 cells wrong. **This
  is the bug I actually shipped into my own first draft**; the harness caught it, which is why
  it is in the list.
- *"frame window never opens (source read with the target spec)"* → 596 cells wrong, canvas
  still draws cleanly.

### 2.6 Regression

- `npm run check:harnesses`: 20 harnesses, **15 gated, all green** (the new one auto-discovered
  and is among them). 5 on the pre-existing known-red debt list, 0 recovered, 0 newly red.
- `npm run check:contracts`: 5 contracts, no divergence (`map_seam` included).
- `npm run check:clipboard`: OK. `npm run build`: clean.
- Two harnesses died with `ReferenceError` when `projectCellsToPhys` gained a dependency —
  **loudly, exit 1, which is the designed failure mode** described in the source comments. Fixed
  by adding `projectCellsToWaferMm` to their symbol lists rather than by duplicating the
  computation. `geometry_origin_reseat_harness` is back to 46 assertions / 8-of-8 mutations.

**One pre-existing red, not mine.** `valid_die_authoring_harness` fails
`[INV-6] resolveValidDie runs the chain check before projecting the cells`. I ran **HEAD's
harness against HEAD's source** and it fails identically. Cause: the assertion is
`indexOf('validDieChainError') < indexOf('projectCellsToPhys')` over the sliced function text,
and `projectCellsToPhys` appears first in a **comment** (`map_editor.js:8117`) while the real
call is at `:8237`, after the chain check at `:8139`. The code's order is correct; the
assertion is reading prose. It is already on the known-red debt list.

---

## 3. Proof that stored target coordinates did not move

Rule 4/5: overlay is a read-only projection. The coordinate `⚡ Push` serialises is
`getDbCoords(...)`, so I snapshot exactly that for **every** canvas cell of the target, run the
full overlay projection and seating, and snapshot again — key by key, no sampling.

The projection opens the frame window on the **source** spec (`withPhysFrame`) and populates
the shared `boundingBoxCache`, so a leaked `try/finally` or a colliding cache slot would land
here and nowhere else.

```
stored target coordinates: 600 canvas cells, 0 moved
  canvas(0,0)  : before 2,26   after 2,26   SAME
  canvas(1,1)  : before 3,25   after 3,25   SAME
  canvas(7,12) : before 9,14   after 9,14   SAME
  canvas(10,15): before 12,11  after 12,11  SAME
  canvas(18,28): before 20,-2  after 20,-2  SAME
  canvas(19,29): before 21,-3  after 21,-3  SAME
physFrameOverride after: null
```

Held in the gated harness as **A10c** (`moved === 0` over 600 cells), **A10d**
(`physFrameOverride === null` after the run), and **A10b** (the snapshot actually covers the
canvas — an empty comparison cannot pass silently).

Structurally, the overlay path writes to `overlayLayers` only. It does not touch `gridData`,
`selectedTable`, the geometry controls, `startX/startY`, `validDie`, or `serverCellKeys`. The
one write path, `importOverlayToGrid`, is unchanged in that respect and now refuses more than
it did (fan-out cells).

For completeness, the same run also shows the fan-out payload — the remainders are the physical
2×2 sub-lattice, not decoration:

```
target die key 10_15 receives 4 source chips:
    src(0,1) in-chip mm (7.700, 7.400) of 15x10   abs mm (144.200, 145.400)
    src(1,1) in-chip mm (7.700, 2.400) of 15x10   abs mm (144.200, 140.400)
    src(0,2) in-chip mm (0.700, 7.400) of 15x10   abs mm (137.200, 145.400)
    src(1,2) in-chip mm (0.700, 2.400) of 15x10   abs mm (137.200, 140.400)
```

7 mm apart on x and 5 mm apart on y — the source pitch, preserved inside the target cell.

---

## 4. What I deliberately did not do

1. **Did not touch the server.** `server/map_overlay.py`'s `_frame_phys_params` /
   `_frame_transformer` / `resolve_align` / `make_frame_transform` are untouched. I read them
   for naming and for the offset sign table's derivation; that reading is why the client asks
   `getDieIndex` for the lattice instead of copying the table.
2. **Did not route valid-die resolution through mm.** `resolveValidDie` still uses
   `projectCellsToPhys` on die-index keys. Rule ① adopts the reference's geometry into the
   canvas, so pitch and dims already match there; sending it through mm would change a settled
   path for no gain. `projectCellsToPhys` keeps its exact signature and collision semantics and
   is now *stated in terms of* the mm projection, so the two cannot disagree.
3. **Did not pick a representative, anywhere.** Not for display, not for import, not for
   `cells`. `null` means "several", and every path treats it as a refusal with a counted reason.
4. **Did not build a UI surface for the value list.** See §1.6 — that is your ruling.
5. **Did not touch `docs/`.** Update points are listed below for doc-keeper.
6. **Did not commit or stage.** The working tree also carries other agents' in-flight changes
   (`server/**`, `client2/src/admin.js`, `config_resolve_view.js`, `retroactive_view.js`).
   ⚠️ **`npm run build` bundles whatever is in the tree**, so `client2/dist/**` now contains
   their in-flight source too. Decide whether `dist` belongs in this commit.
7. **Did not fix the pre-existing `valid_die_authoring` red** (§2.6). It is a test-file claim
   in another round's territory; the diagnosis is above if you want it spun off.
8. **Did not run a browser E2E.** The change is coordinate arithmetic scored by an executing
   harness with an independent oracle; a browser run would have shown a canvas that "looks
   right" — the exact evidence this domain does not accept. Marker rendering at fan-out has not
   been seen on a real canvas, only its inputs verified.

---

## 5. QA round (GO-WITH-FIXES) — what changed

QA report: `agent_workspace/reports/QA_overlay_rule6_review.md`. All five findings addressed.
Harness now **21 declared / 21 applied / 21 caught**, baseline green. **No build was run**
(coordinator constraint); `client2/dist/**` is untouched by this round.

### 5.1 [HIGH] The pitch guard was dead for exactly the inputs it named

QA was right, and the diagnosis matters more than the fix: **a guard downstream of a silent
default can never work.** `physNum` ends `return v || dflt`, so "absent", `""`, `"abc"`,
"declared 0" and "really 15" all arrive at `resolveFrame`'s output as one number. My gate tested
`chipX > 0` on that output. Only a *negative* pitch was ever refused.

Fixed by changing the shape, not the threshold. New `physDeclaration(key, domEl)`
(`map_editor.js`, beside `physNum`) walks the same lookup order but **reports what it found**:
`{ value, source }` with `source ∈ frame | screen | unparsable | absent`. `physNum` itself is
untouched — the whole module rests on its fallback contract.

The gate now reads the fact:

- refuse if either axis has no usable value (`absent` / `unparsable` / `≤ 0`);
- refuse if the source **declared a frame** (`frameFromMeta(sourceMeta)` non-null) but its pitch
  resolved from `'screen'` — a map that declares a grid must declare the pitch that grid is
  measured in. Otherwise the target's pitch is silently adopted as the source's, the canvas
  aligns perfectly and every value is wrong.
- **A source map with no metadata at all is still allowed.** That case is an explicit choice to
  interpret the source in the screen frame (server discipline 3, "absence is not failure") and
  the chip already says so. Blocking it would have broken blank-canvas overlay.

Scored by **A12** with defect reproduction on all four bad declarations: each is asserted to
**pass the old guard** (`resolveFrame(...).chipX > 0`) and to **be refused now**. Worst measured
damage before the fix: **1832 of 1836** cells seated on the wrong target cell. A12e/A12f keep
the guard from degenerating into "always no" (negative still refused, a real declaration still
passes). A12g–A12i read `addOverlayLayer`'s source — **with line comments stripped first**,
because the sibling harness's permanent false red comes from an ordering assertion matching a
symbol inside a comment.

### 5.2 [HIGH] A third harness was dead, and the runner could not tell

`valid_die_frame_adoption_harness.mjs:79` omitted `projectCellsToWaferMm`, so it threw at
`scoreAll` before assertion one. Fixed the extraction list.

**Measured, HEAD vs working tree:** both run **228 assertions with 41 failures**, and the
failing set is **byte-identical** (diffed). So this round caused **zero** regression there — and
separately, the runner's recorded note ("28 of 228") is **stale against HEAD itself**.

**Can the runner distinguish red-with-assertions from red-with-none?** Not today, and the
reason is structural: `check_harnesses.mjs:78` is `const ok = run.status === 0;` — the exit code
is the entire signal. The reassuring text after `[known red]` is a **hardcoded string in the
`KNOWN_RED` map** (`:43-54`) written by a human, never re-measured. That is how a harness moves
from failing-usefully to not-running-at-all with nothing changing on screen, and it is also why
the printed "28" survived the drift to 41.

What it would take, cheapest first:

1. **Honour `exit 2` today (~3 lines).** The harnesses already have a convention: `die()` means
   "nothing was compared" and exits 2, assertion failure exits 1. The runner should treat exit 2
   as **BLOCKING even when known-red** — "did not run" is never acceptable debt. Cheap and
   immediately useful, but it would *not* have caught this case: an uncaught `ReferenceError`
   exits 1, indistinguishable from a failed assertion.
2. **The actual fix — make the count machine-readable (~1 line per harness + ~15 in the
   runner).** Each harness prints a final `ASSERTIONS <ran> <failed>`; `KNOWN_RED` stores the
   expected pair; the runner parses and compares. **A missing line, or `ran` dropping, is
   BLOCKING regardless of known-red status.** This is what separates "41 assertions failed" from
   "0 assertions ran" structurally rather than by prose, and it makes the debt note a measured
   number that cannot go stale. It would have caught the adoption harness on the first run.

I did not build either — you asked only what it would take.

### 5.3 [MED] Source grid dims were unbounded

The dims-*match* refusal I removed had been incidentally serving as the dims-*sanity* bound.
`frameDimError` (already existing, bounds 1..100 integer) is now applied to both the source and
seat frames in `addOverlayLayer`, before any sweep. Measured cost of the seat sweep it protects:
**13 ms at 40×40, 59 ms at 100×100, 6554 ms at 1024×1024** — synchronous, on the UI thread, with
no cancel. Scored by **A13** (oversize / zero / non-integer / negative all refused; the fixture
frames pass, so the gate is not "always no") and mutation *"dimension sanity bound removed"*.

### 5.4 [LOW] `outside` now counts the population its sentence names

The chip promised "excluded from import" while counting grid membership. Import (rule ③) skips
cells whose canvas cell is not `inside` — wafer circle ∩ valid-die mask. `canvasDieKeySet` is
replaced by **`canvasSeatKeys()`** returning `{ all, inside }`, and `outside` is counted against
`inside`.

Two things had to be established first, both measured rather than assumed:

- **The inside predicate is canvas-size invariant** (`cellW` cancels in the normalised
  distance). Verified across 200/431/700/1024/1600 square and 900×380 non-square: **0 of 600
  verdicts differ**. So evaluating at 700×700 gives exactly what the renderer sees. Held by
  **A16**.
- **No frame window may be open.** `isValidDieAt` returns the bare circle whenever
  `physFrameOverride` is set, so computing these keys inside a window silently drops the target's
  own mask. The seat frame *is* the screen, so no window is needed — held by **A14e** with a live
  carved mask, which is what finally caught the mutation *"seat keys computed inside a frame
  window"* (it survived until the fixture had a mask to lose).

Cache key is now `frameAxesKey | basis | validDieResolveSeq` — the mask changes independently of
the frame — and caching is **skipped while authoring** (`template`), because brush strokes do not
bump the generation and so could never invalidate it.

### 5.5 [LOW] Duplicate source rows no longer masquerade as pitch fan-out

Split into two genuinely different cases:

- **Same physical position, same value** → collapsed (`dupCollapsed`). It carries no information;
  the pre-round code kept the last value and a 1:1 map stayed importable. It does again.
- **Same physical position, different values** → a *conflict*, kept as a list, counted as
  `conflictCells`, and the note says `같은 좌표에 서로 다른 값이 있습니다 … (소스 중복 행, 셀
  크기와 무관)`. Choosing here would still be discarding.

The layer chip now reads `최대 N:1` only when `fanCells > 0` and `중복 좌표` otherwise
(`overlayFanChip`), so the label never blames the cell size for something the cell size did not
cause. Scored by **A15a–A15i** and three mutations.

### 5.6 The sentence for the board

> **On the dominant live pair, overlay gives the operator a view, not an import.**

Measured on 7×7 mm @ 40×40 → 15×15 mm @ 23×23 (rot 0 / front both), simulating
`importOverlayToGrid` cell by cell:

```
1288 source chips  ->  297 target cells, max fan-in 9
  293 cells hold several values (null, no representative chosen)
    4 cells hold a single value  --  and 0 of those 4 are inside the wafer
  APPLIED: 0 · skipped as multi-valued: 293 · skipped as outside: 36
```

QA measured "applies 4"; that count is taken before the wafer-inside filter. All four
single-valued cells are edge cells outside the target's wafer circle, which import skips anyway,
so the applied count on this pair is **0, not 4**. Either way the conclusion is the same and it
is the ruled behaviour: fine-pitch-over-coarse is a **reading** of where defects sit, and the
`[↓ 가져오기]` button will move essentially nothing.

**The reverse direction does import.** 15×15 mm @ 23×23 → 7×7 mm @ 40×40 measures 261 chips →
261 cells, fan-in **1**, **261 applied, 0 skipped**. Coarse-over-fine is 1:1 and fully
importable. Worth saying on the board next to the sentence above, because "overlay does not
import" is only true in one direction.

---

## Complexity budget

| | |
|---|---|
| New panels / modes / modals | **0** |
| Net controls added (buttons, inputs, selects, listeners) | **0** (measured by diff grep) |
| Confirmations added to a read path | **0** — adding an overlay is still one click |
| Status labels added | **+1** (`최대 N:1` chip, existing `ov-chip` class, fan-out only) |
| Removed | the `웨이퍼 격자 규격이 다릅니다` refusal — one dead end fewer |

QA round added **0** controls. The `최대 N:1` chip gained a second label (`중복 좌표`) rather
than a second chip, so the count is unchanged at +1 status label.

---

## Doc update points (doc-keeper — I did not edit these)

From `docs/process/DOC_OWNERSHIP.md`, the rows my code paths land on:

- **Row "범용 맵 오버레이(맵 인프라)"** → `docs/spec/MAP_EDITOR_SPEC.md` **§5** (alignment
  contract) and `docs/guide/CONFIG_GUIDE.md` §5.8-bis. §5.1's client pipeline now has a
  millimetre stage; the dims-mismatch refusal it documents no longer exists.
- **Row "웨이퍼 맵 에디터"** → `docs/spec/MAP_EDITOR_SPEC.md` §1~§4 and
  `docs/map_editor/README.md`. §1-bis's naming table and its note **"`mm`은 의도적으로 비어
  있다 — 클라에는 그 공간이 없다"** is now false: the space exists, named `xCells`/`yCells`
  (cell units) and `mmX`/`mmY` (millimetres). The tombstone in `CODE_MAP.md` §0 ⑫ that greps
  for a bare `mm` identifier still holds — I introduced no bare `mm`.
- `docs/spec/MAP_EDITOR_SPEC.md` §0-요약 row **6)** says `⏳ 클라에 mm 공간이 아직 없습니다`.
- `docs/architecture/CODE_MAP.md` §7 `map_editor.js` — the whole section is pinned to blob
  `432b8d6` and HEAD is `9665420`; it was already stale before this round. New symbols:
  `frameDieLattice`, `dieIndexToWaferMm`, `waferMmToDieCell`, `projectCellsToWaferMm`,
  `seatWaferMmInFrame`, `canvasDieKeySet`, `reseatOverlayLayer`, `canvasDieKeyCache`.
- `docs/process/PROJECT_STATUS.md` line 84 parks overlay=rule 6 as 미구현 — **lead-PM owned, I
  did not touch it.**

---

## Proposed lessons for `agent_workspace/memory/map-pm.md` (proposal only)

1. **함정**: 반올림된 인덱스에서 물리량을 되만든다. 인덱스는 `round(연속값)`이라 오프셋의 칸
   미만 잔여가 그 안에 삼켜져 있고, 되만들려면 회전·면 부호표를 **두 번째로** 쓰게 된다.
   실측: 1836칸 중 1789칸이 틀린 칸에 앉았고 화면은 멀쩡했다.
   **올바른 방법**: 이미 그 값을 계산하는 함수에게 **반올림 전 값을 돌려달라고** 한다. 격자
   기준점은 그 함수를 칸 하나에 부르는 것으로 끝난다(간격 1의 정수 격자).
2. **함정**: 좌표 원점이 바뀐 뒤 **술어**가 따라오지 않는다. `35e84c3`가 다이 인덱스 원점을
   웨이퍼 중심으로 옮긴 뒤에도 `0 <= px < cols`가 「격자 밖」 판정에 남아, 아무것도 어긋나지
   않은 항등 오버레이에서 402칩 중 277칩을 「격자 밖」으로 보고했다.
   **올바른 방법**: 원점을 옮기면 그 좌표를 **읽는 모든 부등식**을 전건 검색한다. 범위 술어는
   집합 조회(`canvasDieKeySet`)로 바꿀 수 있으면 바꾼다 — 집합은 원점을 갖지 않는다.
3. **함정**: 오라클을 **화면 축**에서 쓴다. 회전·면이 다른 두 맵을 화면 mm로 비교하면 같은
   물리 위치가 다른 수가 되어 오라클이 구현보다 먼저 틀린다(이 라운드에서 실제로 그랬다).
   **올바른 방법**: 맵을 넘나드는 오라클은 **웨이퍼 프레임**에서 쓴다. 회전·반전은 보는 사람의
   속성이지 다이의 속성이 아니다.
4. **함정**: **기본값 뒤에 관문을 세운다.** `physNum`처럼 `v || dflt`로 끝나는 리더의 출력에
   `> 0`을 걸면 「선언 없음」·「파싱 불가」·「0 선언」·「진짜 그 값」이 전부 같은 수로 도착해
   관문이 원리적으로 아무것도 못 막는다(실측: 네 가지 나쁜 선언이 전부 통과, 최대 1832/1836칸
   오배치). 임계값을 고쳐도 소용없다 — **모양**이 틀렸다.
   **올바른 방법**: 관문이 읽을 **사실**을 만든다. 같은 조회 순서를 돌되 값이 아니라
   `{value, source}`를 돌려주는 쌍둥이를 두고, 관문은 `source`를 읽는다. 원 리더는 손대지
   않는다(모듈 전체가 그 폴백 규약에 얹혀 있다).
5. **함정**: 슬라이스 하네스가 **죽었는데 러너가 「여전히 빨강」이라고 말한다.**
   `check_harnesses.mjs`의 유일한 신호는 `run.status === 0`이라 「200개 단언 중 41개 실패」와
   「단언이 0번 실행됨」이 구별되지 않고, `[known red]` 뒤의 설명은 **사람이 박아 둔 문자열**이라
   낡는다(HEAD 실측 41인데 28로 적혀 있었다).
   **올바른 방법**: 함수에 모듈 전역 의존을 하나 늘리면 **그 함수를 슬라이스하는 하네스 전건을
   grep해서** 심볼 목록을 함께 고친다(이번 라운드에 셋이 걸렸고 셋째는 QA가 찾았다). 러너에는
   단언 수를 기계가 읽을 수 있게 내보내고 **감소를 BLOCKING으로** 만든다.
