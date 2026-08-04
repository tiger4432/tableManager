# Map 1-f — OFFSET/ORIGIN drift, and the C1 meta-vs-formula measurement

Date 2026-08-04 · map-pm · branch `main` · **not pushed**

- Part 1 changes behaviour (one guard, zero new controls).
- Part 2 changed nothing. Read-only measurement, run against the shipped code.

---

## Part 1 — the OFFSET/ORIGIN defect

### 1.1 The semantics, established before anything was changed

`phys_offset_x/y` **displaces the die lattice, in physical millimetres, against a wafer
circle that stays nailed to the canvas centre.** Nothing about that is ambiguous, and — this
is the part the brief expected to go the other way — **the two consumers do not disagree.**

Canonical statement (server, `server/utils/physical_wafer_engine.py:53`):

```python
x_mm = (c - center_c) * self.chip_size_x_mm + self.offset_x_mm
y_mm = (center_r - r) * self.chip_size_y_mm + self.offset_y_mm
```

with the per-rotation frame mapping in `server/map_overlay.py::_frame_phys_params` (its own
docstring carries the 4-rotation table; `oox = -off_x` on `back`).

Client: `getScreenShift` (`client2/src/map_editor.js:1898`) produces the same displacement in
frame-cell units, and `renderGridCanvas` applies it as `x0 = c * cellW + shiftX` while drawing
the wafer circle at a fixed `width/2` (`:3083`, "FIXED at Wafer Center").

**Measured, all 8 rotation x side combinations** (fixture `chipX 11 != chipY 13`,
`offX 7 != offY 3`, so an axis swap or a dropped sign cannot pass by coincidence):

| rot | side | client `getScreenShift` (cells) | server table, transcribed |
|---|---|---|---|
| 0 | front | (+0.6364, -0.2308) | (+0.6364, -0.2308) |
| 0 | back | (-0.6364, -0.2308) | (-0.6364, -0.2308) |
| 90 | front | (+0.2308, +0.6364) | (+0.2308, +0.6364) |
| 90 | back | (+0.2308, -0.6364) | (+0.2308, -0.6364) |
| 180 | front | (-0.6364, +0.2308) | (-0.6364, +0.2308) |
| 180 | back | (+0.6364, +0.2308) | (+0.6364, +0.2308) |
| 270 | front | (-0.2308, -0.6364) | (-0.2308, -0.6364) |
| 270 | back | (-0.2308, +0.6364) | (-0.2308, +0.6364) |

8/8 identical. And in absolute millimetres, the client's mm space (added in `cd3e0f4`) equals
the server's formula exactly: canvas cell (14,12) of a 29x25 grid resolves to wafer mm
**0.000 / 5.000 / 11.000** at `phys_offset_x` = 0 / 5 / 11, against the server's
`(c - cc)*chip_x + off_x` = 0.000 / 5.000 / 11.000.

**Which space is the offset applied in?** One, consistently: the *frame/canvas* space, in
cells, obtained by dividing the declared mm by the **frame-axis** pitch (swapped at 90/270).
`getDieIndex` folds it in before rounding (`:1407`), which is why `getDbCoords` (stored) and
`getCanvasCellFromDieIndex` stay exact inverses. There is no second application and no
overlay-only variant.

### 1.2 So what did the user actually see?

The drift is real, and its cause is **not** the offset's meaning. It is the window the origin
box is scanned over.

- `getWaferBoundingBox` scans **only the declared grid**: `r < visualRows`, `c < visualCols`
  (`:1677`). The server does exactly the same
  (`WaferMapCoordinateTransformer.get_wafer_bounding_box`, `for r in range(self.visual_rows)`).
- `renderGridCanvas` **extends** the lattice to cover the canvas —
  `startC = min(-visualCols, floor(-shiftX/cellW) - 2)`, `endC = max(2*visualCols, ...)`
  (`:2986`).

So once the offset slides the lattice far enough, dies inside the circle keep being *drawn*
at `c < 0`, but the box stops at 0. `box.minC` is the origin — `dbX = c - box.minC + startX` —
so the ORIGIN walks right while the valid dies stay in the circle. Exactly the report.

**Measured** (BASE_OFFSET spec: dia 300, chip 11x13, margin 3, grid 29x25, start 1,1;
"lattice.minC" from an unbounded scan of `isCellInsideWaferFast`, the render's own predicate):

| `phys_offset_x` | in pitches | `box.minC` | lattice `minC` | drift | stored coords moved |
|---|---|---|---|---|---|
| 0 | 0.00 | 2 | 2 | 0 | — (baseline) |
| 2 | 0.18 | 1 | 1 | 0 | — |
| 5 | 0.45 | 1 | 1 | 0 | — |
| 10 | 0.91 | 1 | 1 | 0 | — |
| 11 | 1.00 | 1 | 1 | 0 | — |
| 33 | 3.00 | 0 | -1 | **1** | 63/63, uniformly -1 |
| 50 | 4.55 | 0 | -3 | **3** | 63/63, uniformly -3 |
| 80 | 7.27 | 0 | -6 | **6** | 63/63, uniformly -5 |

The last column is the part that matters more than the drawing: **every stored coordinate is
silently re-numbered by one shared constant.** A uniform offset passes injectivity, range and
round-trip alike (map-pm memory, trap #1) — the map looks perfect and every row in the
database is wrong by the same amount. Concretely, die (-3,-2) stores `x=10` at offset 0 and
`x=7` at offset 50.

(The re-numbering is *not* always equal to the box drift — at 80mm the box drifts 6 while the
stored value moves 5, because the cell rounding and the box clamp round independently. The
harness asserts uniformity and non-zero-ness, not equality, because equality is not true.)

### 1.3 Why the cap is the right guard — and it is, but for a reason the user did not give

The user proposed capping the offset at CHIP X,Y. After measuring, **that is the correct
guard**, on three grounds that the proposal did not state:

1. **The lattice is periodic in the offset, with period = chip pitch.** Measured: at
   `off = 0 / 11 / 22` with `chipX = 11`, canvas cell 14 carries die index **0 / 1 / 2** and
   wafer mm **0 / 11 / 22**; 28 of 29 mm positions are byte-identical between `off = 0` and
   `off = 11`. Adding one pitch does not move a single die — it re-labels every index by 1.
   **Every geometry the offset can express already lives inside `|off| <= pitch`.** What lies
   beyond is not new geometry; it is the re-labelling, and the re-labelling is what pushes
   the origin box off the declared grid.

2. **The alternative fix breaks the seam.** Widening the client's box scan to the drawn
   lattice would make client and server disagree about `minC`, hence about every stored
   coordinate (invariant (1); `contracts/map_seam` scores exactly this pair). The bounded scan
   is the canonical definition, not an oversight.

3. **One pitch is precisely the headroom the canonical grid derivation grants.** Both
   `applyPhysicalGeometry` (client `:2302`) and `calculate_grid_dimensions` (server) derive
   `cols = ceil(2R/chip) + 2` — **one spare cell per side**, and neither budgets for the
   offset. The measured drift onset for this spec is **2 pitches (~23.7mm)**, so a 1-pitch cap
   keeps a factor-2 margin. Live presets already comply: the largest stored offset in
   `server/config/maps.json` is 10mm against `chip_x` 11mm.

Rejected alternatives, for the record: widening the box (breaks the seam, above); widening the
*derived grid* to `ceil((2R + 2|off|)/chip) + 2` (the server's derivation would disagree, and
every existing offset map's `cols` — hence its stored coordinates — would change).

### 1.4 What changed

One file, one guard, inside the existing physical-input listener.
`client2/src/map_editor.js`, in `initDOMElements`:

```js
  const clampOffsetToPitch = (input, pitchInput, label, pitchLabel) => { ... };

  const onPhysicalGeometryEdit = (ev) => {
    if (!ev || ev.type === 'change') { /* cap, then one toast if anything was capped */ }
    reseatCellsToStoredCoords(cellsSeatedUnder);
    scheduleRenderGridCanvas();
  };
```

Decisions inside it, each of which a mutant scores:

- **`change` only, never `input`.** Guarding per keystroke would cut a half-typed "50" down to
  "11" under the cursor.
- **Clamped to the pitch, sign preserved** (`-40` -> `-13`), per axis against its **own**
  declared pitch (`OFFSET Y` vs `CHIP Y`).
- **`|off| == pitch` is allowed.** The cap is the budget, not one step inside it.
- **A declared frame is never rewritten.** `applyPresetObject` / metadata application do not
  pass through this guard, so a stored offset of 50 loads exactly as declared — silently
  capping a server-supplied frame would re-interpret that map's stored coordinates
  (invariant (3)). Only what the operator commits by hand is capped.
- **The clamp runs before the re-seat**, so the cells are re-seated under the capped frame.
  Measured: 425 painted cells, 0 lost, **0 reading a different stored coordinate** after a
  50mm entry is capped. Order matters here — moving the re-seat ahead of the clamp destroys
  63 cells, and that mutant is scored.
- **DOM read, not `physNum`.** This is a screen-control guard; it must never reach into a
  frame window and rewrite a source map's spec.

Also touched: `client2/scripts/check_harnesses.mjs` — one FLOORS line for the new harness.

**Complexity budget: +0 controls, +0 modals, +0 panels, +0 confirmations.** The read path is
untouched. The only new user-visible surface is one toast on an out-of-range write:

> OFFSET은 CHIP 크기를 넘을 수 없습니다 — OFFSET X 50 → 11 (CHIP X 11mm) / OFFSET Y -40 → -13
> (CHIP Y 13mm). 칩 피치를 넘는 오프셋은 같은 격자에 번호만 다시 매기고, ORIGIN을 유효 다이
> 영역 밖으로 밀어냅니다.

### 1.5 Evidence

New harness `client2/tests/offset_pitch_guard_harness.mjs` — **94 assertions, 0 failures**,
mutation controls **11/11 scored as intended** (10 killed + 1 inert control survived, as it
must). It enters through `dispatchEvent` on the real `#phys-offset-x` node after running the
shipped `initDOMElements`, so an unwired guard is red rather than quietly green.

Groups: **S** the shift table vs a hand-transcribed copy of the *server's*
`_frame_phys_params`; **P** periodicity, per cell; **D** the drift, against an unbounded scan
of the render's own predicate, scored per die key -> stored value; **G** the guard, including
the "declared frame untouched" and "0 cells moved" cases.

Mutants killed: `guard-removed` (the defect version put back — 8 failures),
`guard-clamps-to-zero`, `guard-uses-chipX-for-both-axes`, `guard-drops-the-sign`,
`guard-rejects-exactly-one-pitch`, `guard-also-runs-on-input`, `guard-is-silent`,
`clamp-runs-after-the-reseat`, plus two semantics mutants
(`shift-table-drops-the-back-negation`, `shift-table-swaps-rot90-axes`) that prove group S is
not self-comparing.

Gates:

- `node client2/scripts/check_harnesses.mjs` -> **24 harnesses, 20 gated, 4 known-red, exit 0,
  every gated harness green.** (Was 23/19/4. The rise is the new harness; its floor is
  recorded at 94.) No existing floor moved, no existing count dropped.
- `node client2/scripts/check_contracts.mjs` -> **6/6, no divergence.**

Mutation anchors checked before editing, as required: `geometry_origin_reseat_harness.mjs`
pins the two `input.addEventListener(... onPhysicalGeometryEdit)` lines byte-for-byte
(`physical-inputs-are-not-wired`) and the
`reseatCellsToStoredCoords(cellsSeatedUnder);\n\n  renderGridCanvas();` pair in
`applyPhysicalGeometry` (`derive-the-grid-but-do-not-re-seat`). **Neither was touched** — the
guard lives inside the handler body, which is why the wiring lines are still byte-identical.
Every harness fixture's offset was checked against its own pitch first; all are far inside the
cap (largest 2.0mm against 10mm), so the guard is a no-op for every existing fixture.

No build run, `client2/dist` untouched, no `server/`, no `docs/`.

---

## Part 2 — C1: is meta <-> formula lossy, and in which direction?

Read-only. Nothing was built, no meta semantics changed, the ontology track untouched.

### 2.0 First, the two "offsets" are different things — keep them apart

| | what it is | units | where it lands |
|---|---|---|---|
| `grid_start_x/y` | the **origin**: which stored number the first valid column/row carries | **lattice indices (cells)** | `dbX = c - box.minC + start_x` |
| `phys_offset_x/y` | the **physical nudge**: how far the die lattice sits from the wafer centre | **millimetres** | `x_mm = (c - cc)*chip_x + off_x`, and thence into `box.minC` |

The formula's `OFFSET` corresponds to `grid_start_x/y`. Part 1 is about the other one. They
are not two spellings of one field, and — see 2.4 — they both leak into the same formula
parameter, which is the crux of the synchronisation answer.

### 2.1 Method

The RAW coordinate of a die is what it stores under the users' normal form
(rotation 0, front, `invertY` false, start = 1,1). For each meta state I computed the same
121 physical dies' stored coordinates through the shipped `getCanvasCellFromDieIndex` +
`getDbCoords`, then **fitted** `DT_axis = RAW_base * sign + offset` exactly — the fit either
holds for all 121 dies or the state is reported unfittable. Fixture `chipX 11 != chipY 13`,
`cols 29 != rows 25`, so a transpose is visible.

### 2.2 The full mapping — all 16 meta states (start = 1,1)

| rotation | side | invertY | DT_X | DT_Y |
|---|---|---|---|---|
| 0 | front | false | +RAW_X + 0 | +RAW_Y + 0 |
| 0 | front | true | +RAW_X + 0 | -RAW_Y + 22 |
| 0 | back | false | -RAW_X + 26 | +RAW_Y + 0 |
| 0 | back | true | -RAW_X + 26 | -RAW_Y + 22 |
| 90 | front | false | -RAW_Y + 22 | +RAW_X + 0 |
| 90 | front | true | -RAW_Y + 22 | -RAW_X + 26 |
| 90 | back | false | -RAW_Y + 22 | -RAW_X + 26 |
| 90 | back | true | -RAW_Y + 22 | +RAW_X + 0 |
| 180 | front | false | -RAW_X + 26 | -RAW_Y + 22 |
| 180 | front | true | -RAW_X + 26 | +RAW_Y + 0 |
| 180 | back | false | +RAW_X + 0 | -RAW_Y + 22 |
| 180 | back | true | +RAW_X + 0 | +RAW_Y + 0 |
| 270 | front | false | +RAW_Y + 0 | -RAW_X + 26 |
| 270 | front | true | +RAW_Y + 0 | +RAW_X + 0 |
| 270 | back | false | +RAW_Y + 0 | +RAW_X + 0 |
| 270 | back | true | +RAW_Y + 0 | -RAW_X + 26 |

**Every one of the 16 fits exactly.** No meta state produces something the formula cannot name.

### 2.3 The six parameters

| # | parameter | expressible in meta? | by which field |
|---|---|---|---|
| 1 | `X_TRANSFORM_BASE` | **yes** | `rotation` alone — 90/270 transpose, 0/180 do not |
| 2 | `X_SIGN` | **yes** | `rotation` (180) and `side` (`back` negates the physical x) |
| 3 | `X_OFFSET` | **yes** | `grid_start_x` — one-for-one (see 2.4) |
| 4 | `Y_TRANSFORM_BASE` | **yes** | `rotation`, the same bit as #1 |
| 5 | `Y_SIGN` | **yes** | `rotation` (180), `grid_y_invert`, and `side` via composition |
| 6 | `Y_OFFSET` | **yes** | `grid_start_y` — one-for-one |

`TRANSFORM_BASE` is **not** per-axis independent in meta: `rotation` transposes both axes at
once. That is only a limitation for rank-deficient formulas (both output axes fed by the same
raw axis), which are projections rather than orientations and would destroy data. For every
formula that is a bijection of the plane — which is every real DT frame — it is not a gap.

### 2.4 State-space count, and the direction of the loss

**The meta orientation space is 16 spellings of 8 orientations — exactly 2-to-1, and the
aliases are *identical*, offsets included:**

| orientation (X_BASE,X_SIGN / Y_BASE,Y_SIGN) | meta spellings | offsets |
|---|---|---|
| +X / +Y | rot0/front/— , rot180/back/invY | (0,0) both |
| +X / -Y | rot0/front/invY , rot180/back/— | (0,22) both |
| -X / +Y | rot0/back/— , rot180/front/invY | (26,0) both |
| -X / -Y | rot0/back/invY , rot180/front/— | (26,22) both |
| -Y / +X | rot90/front/— , rot90/back/invY | (22,0) both |
| -Y / -X | rot90/front/invY , rot90/back/— | (22,26) both |
| +Y / -X | rot270/front/— , rot270/back/invY | (0,26) both |
| +Y / +X | rot270/front/invY , rot270/back/— | (0,0) both |

`grid_y_invert` is therefore **pure redundancy** given `rotation` x `side`: flipping it is the
same map as rotating 180 and flipping the side. All 8 formula orientations are reachable; no
formula orientation is unreachable from meta; no meta state is unnameable by the formula.

`grid_start_x/y` -> `X_OFFSET`/`Y_OFFSET` is one-for-one, in the **output** axis (measured at
rot 90 / back / invertY, where DT_X is fed by RAW_Y and yet its constant still tracks
`start_x`):

| start_x, start_y | DT_X | DT_Y |
|---|---|---|
| (1, 1) | -RAW_Y + 22 | +RAW_X + 0 |
| (3, -2) | -RAW_Y + 24 | +RAW_X - 3 |
| (0, 0) | -RAW_Y + 21 | +RAW_X - 1 |
| (17, 40) | -RAW_Y + 38 | +RAW_X + 39 |

Deltas track exactly: `Delta start = (+2,-3)` -> `Delta offset = (+2,-3)`.

### 2.5 🔴 The finding that decides synchronisation

**Orientation: bijective up to the known 2-to-1 alias — a pure function in both directions,
once you pick a canonical spelling (`invertY = false`).**

**Offset: NOT a pure function of the formula row, and NOT invertible from meta.** Two
independent measurements:

**(a) The constant carries a bounding-box term that depends on the *physical spec*.** Same
orientation (rot 90 / front / no invert), same `start = 1,1`, three real presets:

| spec | DT_X | DT_Y |
|---|---|---|
| chip 11x13, grid 29x25 (BASE) | -RAW_Y + **22** | +RAW_X + **0** |
| chip 7x7, grid 45x45 (CORE) | -RAW_Y + **32** | +RAW_X + **8** |
| chip 15x15, grid 21x21 (TAPE) | -RAW_Y + **21** | +RAW_X + **-3** |

So a formula row cannot be converted to `grid_start_x/y` (or back) **without also reading that
map's chip pitch, wafer diameter, edge margin and grid dimensions.** The formula row is not
self-describing.

**(b) `phys_offset_x` leaks into the same single parameter.** Same rotation/side/invertY, same
`start = 1,1`, only the mm nudge changes:

| `phys_offset_x` | DT_X |
|---|---|
| 0mm | +RAW_X + 0 |
| 2mm | +RAW_X + **1** |
| 5mm | +RAW_X + **1** |
| 10mm | +RAW_X + 0 |
| 11mm | +RAW_X + 0 |

Two distinct meta fields (`grid_start_x`, `phys_offset_x`) both feed the one formula parameter
`X_OFFSET`, non-monotonically (it is a `box.minC` quantisation). **meta -> formula is
many-to-one on the offset: given a formula row you cannot recover which field produced the
constant.** And the practical hazard for a two-store design: a formula row synchronised from
meta goes **silently stale by one cell** the moment anyone edits `phys_offset_x` within the
cap — no orientation changed, no error, one column off.

**Verdict.** meta -> formula is **total and exact but lossy** (16 -> 8 on orientation,
many-to-one on offset). formula -> meta is **not a function at all without the physical spec
as a second input**. So the two stores can be kept consistent only by treating meta plus the
physical spec as the source and the formula row as a **derived projection** — a formula row
is not a frame, it is a frame *evaluated against a specific geometry*.

### 2.6 The "just adjust the offset to match the cell count" attraction

Cheap answer, since it fell out: on the meta side the origin is a plain number input —
`#grid-start-x` / `#grid-start-y` in `client2/map_editor.html:131,135` — plus a
`📍 Set Origin (0,0)` click mode that sets it by picking a cell. Editing it is *not* harder
than editing a number in a row; arguably easier, because clicking the intended origin cell
computes it for you.

The real asymmetry is elsewhere and it is worth naming: editing `start_x` means loading that
map in the editor and pushing it, **one map at a time**, whereas the DT inventory rows are
per-jobid and bulk-editable in the grid, and joinable in SQL at analysis time without a
metadata lookup. That is a *workflow and joinability* gap, not an expressiveness gap — meta
can say everything the formula says. If the ruling goes to meta, the gap to close is bulk
editing plus a joinable projection, not new meta fields.

---

## Living-doc update points (for doc-keeper — not edited here)

Found via `docs/process/DOC_OWNERSHIP.md` rows matching `client2/src/map_editor.js`:

- **`docs/spec/MAP_EDITOR_SPEC.md`** §1~§4 (editor contract) and §5.0 (the alignment
  invariant): record that `phys_offset_x/y` is capped at the declared chip pitch on the
  operator-edit path, that the cap is derived from the `ceil(2R/chip) + 2` grid budget, and
  that offsets beyond one pitch are re-labellings rather than geometries.
- **`docs/map_editor/README.md`**: the physical-geometry panel now refuses out-of-range
  offsets with a toast.
- **`docs/guide/VALID_DIE_MAP_GUIDE.md`**: the ownership row warns that quoted UI strings go
  stale — a new toast string was added and this guide is the operator-facing one for the
  origin-box reaction.
- **`docs/qa/FEATURE_CHECKLIST.md`** §1.7 / §2.9 (origin-box axis): add the offset cap as a
  checkable item.

## Proposed lessons for `agent_workspace/memory/map-pm.md` (proposal only)

1. **A "drift" is not automatically a disagreement between consumers.** Measure the two
   definitions against each other *first*: here client and server agreed 8/8 and the defect
   was a scan-window clamp, not a semantics split. Had I assumed the split the brief
   suggested, I would have "fixed" the shift table and broken the seam.
2. **When a coordinate transform has a periodic parameter, the period is the guard.** The
   offset repeats with the chip pitch, so the whole expressible space lives inside one pitch
   and everything outside is a re-labelling. Capping at the period loses nothing — that is
   what makes a cap a real fix rather than a symptom fix, and it has to be *measured*
   (index shift exactly 1, mm set identical) rather than argued.
3. **Assert uniformity, not the predicted magnitude.** I first asserted "stored coordinates
   move by exactly the box drift" and it was false at 80mm (drift 6, shift 5) because the cell
   rounding and the box clamp round independently. The dangerous property is that the shift is
   *uniform* (invisible to injectivity/range/round-trip); the magnitude is incidental.
4. **A mutant that the design absorbs is not a defect.** `clamp-runs-after-the-reseat` first
   survived because duplicating the re-seat is harmless — the reaction re-reads
   `cellsSeatedUnder` and the two steps compose. Only *moving* it is a defect. A surviving
   mutant is a question about the mutant as often as about the assertion.
