# R2 - Map lens: what in the current editor serves the purpose

> Analysis only. No code changed, no build, no commit, no `dist` touch.
> Purpose chain used (product owner, corrected): **coordinate system confirmed -> align multiple
> defect sources -> die map confirmed (a DECISION) -> bonding plan.**
> Measurement scope: `client2/src/map_editor.js` (10,867 lines), `client2/src/transfer_plan.js`
> (1,876), `client2/map_editor.html` (461).

---

## 0. The number that reframes "the code is too long"

| | lines | share |
|---|---|---|
| file total | 10,867 | |
| blank | 782 | |
| **comment** | **3,729** | **37.0% of non-blank** |
| code | 6,356 | 63.0% of non-blank |

The editor is **6,356 code lines**, not 10,814. The other 3,729 lines are the accumulated
rationale - measured counts, refuted hypotheses, and named defects. Module level alone is 2,331
lines of which **1,858 are comment and 169 are code**.

This matters for the rebuild decision in both directions:
- "Too long to fix in one round" is not primarily a code-volume problem (see Q4).
- A rebuild that starts from a clean file discards 3,729 lines of measurement that nobody
  re-derives cheaply. Most of those comments cite a number that was obtained once, at cost.

Method: `strip_code` removes strings/comments, brace-balanced spans from each top-level
declaration (paren-skipping so `function f(opts = {}) {` is not closed by its own default).
249 top-level functions found (the brief said 252; the delta is regex shape, not substance).

---

## Q1. Census against the seven layers

**Primary-layer assignment.** Every one of the 249 top-level functions is assigned; the
"unclassified" bucket is explicit and reported at full size. Nothing was dropped
(`UNMAPPED: []`).

| layer | fns | lines | % of fn lines |
|---|---:|---:|---:|
| 1 declaration | 40 | 1,077 | 12.6% |
| 2 decision (pure geometry) | 35 | 876 | 10.3% |
| 3 index (finding maps) | 28 | 605 | 7.1% |
| 4 correspondence | 27 | 1,309 | 15.3% |
| 5 plan (legend/DOE/paint) | 44 | 1,094 | 12.8% |
| 6 join (write to system of record) | 8 | 1,001 | 11.7% |
| 7 view | 24 | 1,326 | 15.5% |
| **-- unclassified: clipboard** | 23 | 765 | 9.0% |
| **-- unclassified: frame stack / undo** | 9 | 297 | 3.5% |
| **-- unclassified: paint lock** | 9 | 106 | 1.2% |
| **-- unclassified: pure util** | 2 | 80 | 0.9% |
| **TOTAL (top-level fns)** | **249** | **8,536** | 100% |
| outside any function (module level) | - | 2,331 | (1,858 comment / 169 code / 304 blank) |

**Unclassified total: 43 functions, 1,248 lines, 14.6%.** The largest piece is the Excel
clipboard round trip (`copyGridToExcel` 6835-7089, `onMapGridPaste` 7645-7776,
`readCompanyMapBlock` 7184-7245, `readCoordTableBlock` 7482-7579). It is not any of the seven
layers, and it is not decoration: it is the only path by which a map arrives from outside the
system. The seven-layer proposal has no home for it. Either add a layer or state that the
clipboard leaves with the old editor.

**The census's real finding is the cross-layer bucket.** 20 functions span more than one layer:

| function | lines | primary | also touches |
|---|---:|---|---|
| `loadExistingMap` 4853-5282 | 430 | join | 1,2,3,4,5,7 (all seven) |
| `initDOMElements` 409-836 | 428 | view | 1,3,5,7 + controller wiring |
| `resolveValidDie` 8693-9111 | 419 | correspondence | 1,2,3,7 |
| `renderGridCanvas` 3249-3574 | 326 | view | 2,4,6 (produces the save payload domain) |
| `pushMapData` 5807-6131 | 325 | join | 1,2,5 |
| `addOverlayLayer` 10100-10390 | 291 | correspondence | 2,3,7 |
| `copyGridToExcel` 6835-7089 | 255 | (unclassified) | 2,5,7 |
| `renderLegendTable` 4415-4623 | 209 | plan | 7 |
| `saveMapSpecOnly` 9487-9648 | 162 | join | 1,3 |
| `onMapGridPaste` 7645-7776 | 132 | (unclassified) | 1,2,5 |
| + 10 more (53-84 lines each) | | | |

**3,673 lines = 43.0% of all function lines sit in functions that span more than one layer.**

That is the census answer to "can the seven layers be lifted out". Layers 2 (decision) and 3
(index) are largely already separable - 63 functions, 1,481 lines, mostly small and
argument-taking. Layers 1/4/5/6/7 are entangled inside ten large functions, and layer 6 (join)
is barely 8 functions because most of the joining happens *inside* `loadExistingMap`.

**`transfer_plan.js`**: 67 real functions, roughly 1,180 lines (the census tool reports a
false 68th - the whole file is one module closure). It contains **zero layer-2 functions**.
There is no coordinate arithmetic in the plan panel at all. See Q3.

**`map_editor.html`**: 28 buttons, 16 inputs, 10 selects, 5 modal containers. `map_editor.js`
raises 13 `confirm()` and 15 `alert()` call sites.

---

## Q2. Features that impersonate the purpose

Listed strongest-first. I dropped four candidates I could not prove (the coordinate-choice
modal, `fitGridToMask`, the overlay align chip's `derived` branch, the preset dropdown) -
notes at the end of this section.

### A. The Wafer Side (Front/Back) radio - same defect as the rotation button, unnamed until now

**Looks like**: `map_editor.html:152-166`, a control group labelled `Wafer Side (앞/뒷면 반전)`
sitting immediately below `Map Rotation (회전)`, with the notch hint baked into each label
(`Front (앞면 / 노치 우측 편향)`). It presents as the second alignment axis.

**Actually does**: it is a declaration written to `grid_metadata.side` on Push. It is not a
search control.

**Evidence it cannot align**: exactly the §1 theorem, at the same three lines as rotation.
In `renderGridCanvas`:
- `map_editor.js:3302` - `physConfig = getTransformedPhysicalConfig(currentRotation, currentSide)`
- `map_editor.js:3361` - `physical = getDieIndex(c, r, cols, rows, currentRotation, currentSide)`
- `map_editor.js:3362-3363` - `completelyInside = isValidDieAt(physical.x, physical.y, isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, ...))`
- `map_editor.js:3366-3367` - `coordKey = physical.x + '_' + physical.y; val = gridData[coordKey]`

The value at a canvas cell and the mask verdict at that canvas cell are both functions of
`(c, r, currentRotation, currentSide)` in the same loop iteration. `side` permutes both. When
`validDieBasis() === 'ref'` it is stronger still: `isValidDieAt` is keyed by **physical**
coordinates, so the valid-die verdict is frame-invariant by construction. Flipping Front/Back
cannot change any agreement. Round 1 named only the rotation button; the side radio is the same
feature wearing a different label, and it is the one operators reach for when rotation "does
not help".

Note for the spec: `MAP_ALIGNMENT_SPEC §1` cites `map_editor.js:3350-3356` for this mechanism.
Those lines have shifted to **3361-3367**. The citation is already stale.

### B. The on-screen notch badge, and the fact that there are two of them

**Looks like**: a wafer notch mark 'D' on the canvas edge, the physical landmark that would tell
you which way the wafer sits.

**Actually does**: it is rendered from `currentRotation` and `currentSide` and reads no stored
declaration (I8, established). What round 1 did not find is that **there are two independent
implementations of "where is the notch"**, and they disagree at the boundary:

| | `updateNotchPosition` 3644-3694 | `computeNotchCell` 6777-6813 |
|---|---|---|
| output | CSS class + px offset on `el.gridNotch` | a canvas cell `{r, c}` or `null` |
| direction table | `map_editor.js:3665-3672` (4-branch if/else on `currentRotation`, `dx = side==='front'?1:-1`) | `map_editor.js:6788-6795` - the **same four branches, written again** |
| off-grid | never - the badge is always painted at the canvas edge | returns `null` (`:6812`, the P0-2 fix) |
| bbox | none (CSS edges) | `getWaferBoundingBox(rotation, side, {circleOnly:true})` `:6785` |

So the clipboard fingerprint says "this frame has no notch in the grid" while the screen paints
a notch anyway. The badge is a claim the system's own contract refuses to make.

### C. `notifyPaintCounts` - the plan gets counts from the renderer, not from the map

**Looks like**: the DOE panel showing how many die each legend value covers - the number a
bonding plan is built on.

**Actually does**: `map_editor.js:3124` calls `notifyPaintCounts(computeLegendCounts())`.
`computeLegendCounts` (`:3103-3108`) iterates `eachSavableCell` (`:3032-3046`), whose domain is
`gridCells2D`, which is populated **only** by the render loop (`:3276` `gridCells2D = {}`,
`:3381-3382` the single registration site).

**Evidence it can be wrong**: `renderGridCanvas:3334` is
`if (x0 + cellW < 0 || x0 > width || y0 + cellH < 0 || y0 > height) continue;` and it sits
**47 lines before** the registration at 3381. Any declared, on-grid cell pushed off the canvas
is never registered, so it is not counted, not drawn, and not saved. The panel shows a
confident number over an incomplete population. This is I5 with a second consumer nobody had
named: it is not only the save payload, it is the plan's arithmetic.

### D. The canvas itself, for the 320 maps with no declared geometry

**Looks like**: a complete, correctly proportioned wafer with a die grid on it.

**Actually does**: `physNum` (`map_editor.js:1435-1442`) ends in `return v || dflt` and is
called with `dflt` = 300 (diameter), 2.5 (chipX), 2.5 (chipY), 3.0 (edge margin) at
`:1945-1950`. It cannot fail. `getScreenShift:2076-2077` carries a **third** copy of the same
2.5 fallback. So a map with zero declared physical spec renders as a clean 300 mm wafer with
2.5x2.5 mm die and is pixel-indistinguishable from a fully declared map. Production: 320 of
668 `wafer_map_metadata` rows are `auto_registered` synthetic (`server/map_overlay.py:302-303`).

**This one is partly mitigated already, and the mitigation is the model to keep.** `cellMetrics`
(`:2127-2190`) does *not* use `physNum` - it uses `physDeclaration` (`:1509-1525`), the honest
twin that returns `{value, source}` and distinguishes absent / unparsable / auto_registered /
declared. When the declaration is missing it falls back to an anisotropic grid-filling layout
and sets `waferAnchored: false`, and the toolbar shows `#cell-aspect-note`
(`map_editor.html:330-333`). So the *scale* is honest. The **circle is still drawn**, and
`DOC_OWNERSHIP.md:83` already records this as an open contradiction: the guidance text says
"we do not draw the wafer circle" while the drawing block is not gated on `waferAnchored` - it
merely happens to fall off-canvas. That is an unresolved impersonation, on the record, awaiting
a lead ruling.

### Candidates I could NOT prove, and am therefore not listing as impersonators

- **`promptCoordinateChoice` / the 📐 표준 button** (`:5443-5498`). It does re-declare START to
  the data bounding box, and `pushMapData` persists it. But the label was already fixed to say
  so out loud (`:5451-5452`: `START를 데이터 최소값으로 재선언, 마스크 없음, Rot 0°`), and it
  has a legitimate use for maps being authored from scratch. This is the precedent worth
  copying: the fix was **a label, not a removal**.
- **`fitGridToMask`** (`:9118-9172`). Grows dimensions one step at a time until the mask fits,
  stops at the editor dimension ceiling, refuses to clip, and logs the residual miss
  (`:9169-9171`). It is honest and load-bearing.
- **The overlay align chip** (`:10527-10548`). The `derived` branch is accurate. The `identity`
  branch renders `무보정` for two different facts - "the frames were compared and agree" and
  "neither map declared anything" (`server/map_overlay.py:577-580` returns identity with note
  `맵 메타 부재`; `_rotation_of/_side_of/_y_invert_of` at `:235-239, 257, 261` default 0 /
  front / False so two silent maps compare equal at `:582-583`). The distinguishing text does
  reach the user - in the `title` tooltip. I judge that under-informative, not impersonating.
  Flagging it as a low-cost improvement (one word in the chip label), not as a defect.
- **The preset dropdown.** `markGeometryAutoRegistered` is *cleared* whenever a human declares
  (preset applied, chip field edited), and the server refuses overlays on auto-registered
  geometry first (`map_overlay.py:345-346`). The gate works.

---

## Q3. What the bonding plan actually needs from the editor

### 3.1 What it needs, as data

Server side confirmed by direct read (all `server/`):

| field | read at | when absent |
|---|---|---|
| `grid_cols`, `grid_rows` | `map_overlay.py:246-247` | **required** - KeyError makes `_grid_of` return None `:253-254` |
| `phys_wafer_dia`, `phys_chip_x/y`, `phys_offset_x/y`, `phys_edge_margin` | `map_overlay.py:265-266, 277-281` | **required** - `make_frame_transform:518-527` raises |
| `rotation` | `map_overlay.py:235-239` | **silently 0** (also on parse failure) |
| `side` | `map_overlay.py:257` | **silently `front`** |
| `grid_y_invert` | `map_overlay.py:261` | **silently False** |
| `grid_start_x`, `grid_start_y` | `map_overlay.py:248-249` | **silently 1** |
| `auto_registered` | `map_overlay.py:312`, judged at `:345-346` | absent = treated as a real declaration |
| notch | not stored at all - derived client-side from rotation/side | - |
| bbox | not stored - recomputed from phys `map_overlay.py:466` | - |
| **valid-die basis (the common floor)** | **does not exist server-side** | - |

Entry point `resolve_map_transform` (`server/map_overlay.py:608`); callers
`server/bonding_plan.py:752`, `server/transfer_plan.py:1591`,
`server/dt_map_derivation.py:642`.

### 3.2 What the editor hands the plan today

`map_editor.js:358-397` is the entire controller surface injected into `initTransferPlan`.
20 members. **Not one carries a coordinate.** `getMapContext` (`:374-380`) returns exactly:

```
{ table, mapKey, loaded: {table, mapKey} | null, depth, parent }
```

`transfer_plan.js:1706-1728` consumes it and stores the same five fields into `S.ctx`. The
other two channels are `notifyLegendChanged` (legend rows) and `notifyPaintCounts` (a
value -> count object). `transfer_plan.js` contains **zero layer-2 functions**.

So: **the editor tells the plan the map's NAME and how many die each value covers, and nothing
about the coordinate system.** Everything in the table above is re-read by the server from
`wafer_map_metadata`, and five of those fields are silently defaulted.

**What the plan assumes because the editor never said:**
1. rotation = 0, side = front, y_invert = False, start = (1,1) when the row is silent. There is
   no marker separating "declared 0" from "nobody said". `rotation: 0` is 516 of 668 rows
   (77.2%, `MAP_ALIGNMENT_SPEC §9ⓒ`).
2. The **bbox basis is the wafer circle** (`map_overlay.py:456-466`). The client uses the
   **valid-die mask bbox** when `valid_die_ref` resolves (`map_editor.js:1829-1832, 1861-1871`,
   via `getWaferBoundingBox:1787-1897`). Measured by the parallel lens: 165/165 cells shift.
   The operator's common floor is a client-only concept.
3. When BOTH sides have no meta, `resolve_align:577-580` returns identity and
   `bonding_plan.py:764` sets `status = "connected"` with no marker. The plan proceeds on raw
   coordinates and says it is connected.

### 3.3 The N-ary requirement changes the shape of the answer

The corrected chain says N defect sources must be laid on ONE floor. The editor already holds
N sources: `overlayLayers` (`:8281`), `addOverlayLayer` (`:10100-10390`), and
`syncOverlayGeometry` (`:10503-10514`) which reseats every layer whenever the canvas frame
changes. **The N-ary machinery exists.** Three things are missing, and they are small next to
a rebuild:

- **The result is never written.** `importOverlayToGrid` (`:10589-10658`) writes source cells
  into `gridData` of the one map being edited. There is no "these N sources agreed on this
  floor" record. The die map decision has nowhere to land.
- **No score is produced.** Round 1's finding that value agreement gives 100% unique winners
  on 4/4 scopes is not wired into anything the operator sees.
- **The floor is not transmitted.** Even when the operator has picked a `valid_die_ref` and
  seated N sources on it, the server-side plan re-derives the bbox from the circle.

### 3.4 Is `bonding_map` product-owned?

**NO. It is site-owned.** Three independent pieces of evidence:

1. `server/product_tables.py` is the single definition of product ownership (docstring `:1-27`).
   `PRODUCT_TABLES` has exactly five keys - `wafer_map_metadata:39`, `map_split_registry:60`,
   `map_doe:104`, `map_doe_source:145`, `valid_die_ref:188`. **`bonding_map` is absent.**
2. `docs/architecture/data_model.md:190` names it explicitly under 현장 소유 (site-owned),
   alongside `inventory_master`, as a `.sample` demo entry.
3. It carries no `[제품 소유 저장소]` `__comment`, unlike `wafer_map_metadata`
   (`server/config/table_config.json:222`).

Ownership axis: `server/config/table_config.json:208-221` - `business_key: "pkg_id"`,
`composite_key_source: ["base","x","y"]`. **`map_key_columns: ["base"]`** - so it IS declared a
map table (the same declaration commit `5e03f85` added for `dt_log`). `base` is a substrate
identifier: the fixture generator sets `base = uuid4()`
(`server/ingestion_workspace/bonding_map/auto_update/fetch_data.py:18,23`). There is no
product, lot, device, or equipment column at all. `bonding_map` is not referenced by
`server/config/bonding_plan_config.json`; its only plan role is
`stages.*.target_map.table` in `server/config/transfer_plan_config.json:55-58`.

A real row count needs a live DB; ingestion is currently disabled
(`server/config/auto_update_control.json:3-4`).

---

## Q4. The three-round failure - the mechanism

### 4.1 The valid-die case was not three copies of one statement

The three sites are still marked in the file:

- `switchTable:1250-1257` - "CLEAR SITE 1 OF 3, DELETED" (two direct statements)
- `loadExistingMap:4887-4888` - "CLEAR SITE 2 OF 3, DELETED" (the `[M4①]` block)
- `loadExistingMap:5034-5038` - "**CLEAR SITE 3 OF 3, GUARDED. This is the one that survives
  naive fixes.**"

The file's own note on site 3 is the diagnosis: *"with both of them suppressed the control was
still blanked, because this call reaches `set('circle', null, '', null)` whenever
`parseValidDieRef` answers null, and `set` ends with `syncValidDieRefControls()`. The wipe
arrived through the resolver."*

So the three rounds were not three copy-pastes. They were **two explicit writes plus one write
that arrives as a resolver's absence branch**. Rounds 1 and 2 removed what `grep` could find;
round 3 required knowing that "resolve" and "reset" are the same code path when the resolve
fails. **No amount of shortening the file finds site 3.** A rebuild that keeps a resolver whose
failure branch writes the same state reproduces this exactly.

### 4.2 The systemic count - mutable module state

48 module-level `let`/`var`. **152 assignment sites.**

| | count |
|---|---:|
| bindings with >1 write site | **37 of 48 (77%)** |
| bindings with >2 write sites | **26 of 48 (54%)** |
| total assignment sites | **152** |

Worst three:

| binding | decl | writes | sites |
|---|---:|---:|---|
| `activeBrush` | `:61` | **10** | `seedEmptyDoe:3737`, `applyRegistryRowsToLegend:4124`, `renderLegendTable:4474`, `renderLegendTable:4598`, `selectBrush:4626`, `updateLegendRowForPanel:4684`, `deleteLegendRowForPanel:4727`, `loadExistingMap:5157`, `loadExistingMap:5159`, `restoreEditorState:7945` |
| `legendReplaceScope` | `:317` | **9** | `saveLegendToServer:4206,4212,4244`, `loadExistingMap:5172,5194,5225`, `restoreEditorState:7955`, `setLoadedIdentity:8083`, `openMapFrame:8150` |
| `boundingBoxCache` | `:1747` | **9** | `applyPresetObject:2834`, `loadExistingMap:5004,5014,5067`, `restoreEditorState:7937,7966`, `applyGridMetaObject:8000`, `resolveValidDie:8786,8799` |

Runners-up: `gridData` 7, `legendDirty` 7, `legendSaveState` 6, `frameTouched` 6,
`legend` 5, `validDie` 5, `framePushed` 5, `overlayLayers` 5.

`boundingBoxCache` is the sharpest one: nine sites each decide independently that the origin
box may now be stale. Miss one and every coordinate on screen is wrong while the picture stays
perfect. `loadExistingMap` alone invalidates it three times (5004, 5014, 5067) and the comment
at `:5006-5008` explains why the first of the three cannot be merged with the others.

### 4.3 The count the lead PM actually asked for - QUESTIONS with more than one answering site

This is the better number, and it is worse.

**"What is the current frame?" has 6 named answering functions with 4 different field sets,
plus 14 raw inline re-reads of the DOM.**

| function | line | fields | cols read as |
|---|---:|---|---|
| `seatingSnapshot` | 1932 | 13 + `box` | `gridDimNum('cols', el.gridCols, 10)` (validated) |
| `readGridFrameControls` | 6260 | **5 - no rotation, no side** | `parseInt(...)\|\|10` |
| `getVisualGridDimensions` | 6418 | 2 | `parseInt(...)\|\|10` |
| `currentCoordFrame` | 7583 | 9 (+ visualCols/Rows) | `parseInt(...)\|\|10` |
| `currentFrame` | 8515 | 7 (no phys) | `parseInt(...)\|\|10` |
| `currentGeomSignature` | 10486 | 13, as a joined **string** | `el.gridCols.value` raw |

Raw inline re-reads at `:603-604, 839-842, 883-884, 1943-1944, 3252-3255, 5575-5578, 5695-5696,
6262-6265, 6346-6347, 6419-6420, 7586-7592, 8026-8029, 8517-8520, 8736-8737`.

**"What are the visual grid dimensions?" has 11 answering sites**: `:886-887, 1568-1569,
1627-1628, 1814-1815, 2412-2413, 3259-3260, 5699-5700, 6326-6327, 6349-6350, 6423-6424,
6809-6810`. A named primitive `getVisualGridDimensions` exists at `:6418` and **10 of the 11
sites bypass it**.

**"Where is the notch?" has 2 answering sites that disagree at the boundary** (Q2.B).

**"What is the chip pitch when undeclared?" has 3 answering sites**: `physNum:1441` (`v || dflt`,
called with 2.5), `getScreenShift:2076-2077` (its own `|| 2.5`), and `physDeclaration:1509`
(the honest one, which refuses).

**"What is this map's rotation?" has 2 answering sites across the client/server line**: the
client DOM control, and `map_overlay._rotation_of:235-239` defaulting 0. Same for side, y_invert
and start. The bbox basis is a fifth (client mask vs server circle).

**This is the mechanism.** There is no `frame` value in this program. There is a DOM panel, and
every reader re-parses it with its own default and its own field subset. A behaviour change is
therefore never one edit - it is an edit plus a search for the other spellings, and the search
has no reliable termination condition because two of the spellings live in another language on
another host. That is the three-round failure, and **it is not caused by file length.** A
6,000-line rewrite with the same "the panel is the state" architecture reproduces it on day one.

Note: the file is already fighting this deliberately and winning in places. `eachSavableCell`
(`:3032`) is the single savable-cell predicate with four consumers; `cellMetrics` (`:2127`) is
the single scale producer with two; `parseValidDieRef` is the single "does this map declare a
valid die" predicate with an explicit **NO SECOND SPELLING** rule (`:5052-5055`);
`pushBlockingCount` (`:3098`) exists solely to keep one sum in one place. Every one of those is
a repair of a shipped defect. The unification discipline is correct and partly applied. It is
not applied to the frame, which is the one that matters most.

---

## Q5. What must survive the rebuild

### The single thing I would fight for: `cellMetrics` (`map_editor.js:2127-2190`)

Not "the isotropic scale" as a bullet. This one function, and specifically its three refusals,
each of which is a shipped defect that was found by measurement and would be re-introduced by
any reasonable-looking reimplementation:

1. **It refuses to invent a diameter.** `:2166-2169` - `physDeclaration('waferDia', ...)`, not
   `physNum`. If the diameter is not declared, `waferAnchored: false` and the layout falls back
   to grid-filling with a visible toolbar note. The comment states the reason in one line worth
   preserving verbatim: an invented physical quantity dominates the whole render and *the screen
   is perfectly aligned while every value is wrong*.
2. **It anchors on the declared diameter, not `effectiveRadius`.** `:2157-2159` - edge margin is
   a process parameter, so anchoring on `effectiveRadius` draws the same 300 mm wafer at two
   sizes for margin 3 vs 5. Measured: at fixed declared diameter 300 mm, the old grid-derived
   scale drew the same wafer at radius 875.000 px and 336.538 px depending on how someone cut
   the grid (`:2148-2154`).
3. **`s = min(sGrid, sWafer)` is a data guarantee, not aesthetics.** `:2160-2165` - it forces
   `padX, padY >= 0`, which is the only reason declared cells stay on the canvas and therefore
   inside `gridCells2D` and therefore inside the save payload.

A rebuild will write `scale = canvasShort / (cols * pitch)` on the first day and lose all three.
Point 3 in particular reads as a rendering nicety and is a data-integrity invariant.

Runner-up, briefly: `drawOverlayMarkers` (`:8369-8444`), specifically `markerAxisRadius` per
axis rather than `min(cellW, cellH)`. Measured: at pitch 2x18 the marker collapsed to the 1.5 px
floor and at 0.6x18 **no marker was drawn at all** (`:8380-8386`). The main grid looked fine
throughout, because only the circle was sized off one axis. Nobody rediscovers that by
inspection.

Also worth a line each because they are invariants disguised as code:
`fitGridToMask:9118` (grow, never clip, report the residual), `computeNotchCell:6812` (return
`null` off-grid rather than a plausible coordinate), `getWaferBoundingBox`'s generation-numbered
cache tag (`:1830-1833` - a count-based tag lets a different reference of the same size inherit
the previous frame's box).

### The one defect that must NOT survive

**`renderGridCanvas:3334`** -
`if (x0 + cellW < 0 || x0 > width || y0 + cellH < 0 || y0 > height) continue;`
sits 47 lines ahead of the only registration site, `:3381-3382`
(`if (!gridCells2D[r]) gridCells2D[r] = {}; gridCells2D[r][c] = cellObj;`).
A declared, on-grid cell that lands off the canvas is never registered, therefore never in
`eachSavableCell`'s domain, therefore silently absent from the Push payload. Measured 480 of
1,600. Confirmed by the file itself at `:8927`: the DB x/y written on Push are
`cellObj.x/.y`, which the render loop produced.

**Is it still reachable?** Yes, and by a narrower path than before. `cellMetrics` closes the
grid-vs-wafer half (`padX, padY >= 0`), and the anisotropic fallback fills the canvas exactly.
The surviving path is **`getScreenShift` (`:2073-2097`)**, which returns
`shiftX = (origOffsetX / chipX) * cellW` with no canvas bound, and `renderGridCanvas:3322-3323`
sets `originX = shiftX + padX`. A declared `phys_offset_x` of 6 mm at 2.5 mm pitch shifts the
grid 2.4 columns; when `sGrid` is binding (grid exactly fills the canvas) those columns fall off
the right edge and are never registered. So the defect is now **gated on a declared nonzero
offset** rather than on grid size. That is a smaller population, not a closed hole, and offsets
are exactly what the 348 declared maps carry.

**Does other code have the same shape?** Yes, two more, both inside the same function:

- `renderGridCanvas:3274` - `cellsSeatedUnder = seatingSnapshot() || cellsSeatedUnder`. The
  record of *which coordinate system the cells are currently seated under* - a data-safety
  record consumed by `reseatCellsToStoredCoords` - is produced by the render loop. Three
  writers total (`:1987, 3274, 8754`). If a frame change does not end in a render, the record
  is stale and the next geometry edit reseats against the wrong baseline.
- `renderGridCanvas:3341` - `syncOverlayGeometry()`. That call runs `reseatOverlayLayer` over
  every overlay (`:10503-10514`), which recomputes overlay cell coordinates. **Overlay data
  reseating is triggered from inside the paint loop**, and its guard is
  `currentGeomSignature()` - a joined string of raw `.value` reads (`:10486-10501`), so
  `"20"` and `" 20"` are different signatures.

The pattern is one sentence: **`renderGridCanvas` is not a renderer. It is the program's only
producer of the cell table, the seating record, and the overlay reseat trigger, and it happens
to paint.** That is what layer 6 of the proposal must break, and it is the strongest single
argument for the rebuild in this report.

---

## Recommendation

**Do not rebuild the whole editor. Extract the frame, and extract layer 2 first - as a decision
pass, not a file move.**

1. **Make `frame` a value.** One producer, one field set, `physDeclaration` semantics
   (`{value, source}`) for every axis so absent / unparsable / auto_registered / declared stay
   distinguishable. Retire the other 5 named readers and the 14 inline re-reads. This is the
   single change that ends the three-round failure, and it is roughly 20 call sites, not 10,000
   lines. **It is measurable before and after**: today "what is the current frame" has 20
   answering sites and "what are the visual dimensions" has 11 - both should be 1.
2. **Split `renderGridCanvas` into decide-then-paint** (spec §6). The decision pass produces
   the cell table with no canvas, no `continue`, no seating write, no overlay trigger. This
   closes I5 at the root instead of gating it on offsets, and it lets the harness score without
   a recording canvas - which is the R7/R8 gate.
3. **Hand the frame to the plan.** `getMapContext` gains the frame and the valid-die basis. The
   plan currently learns a map's name and nothing about its geometry, and the server fills the
   gap with five silent defaults. This is the concrete answer to "what does the bonding plan
   need": it needs the floor the operator chose, and today the floor is client-only.
4. **Keep the old editor running** (spec §8.2) and keep the comments. 3,729 comment lines are
   the measurement record; they are cheaper to port than to re-derive.
5. Retire nothing user-visible yet. Rotation and Side are declarations - the defect is that they
   are *presented* as search controls. The precedent for the fix is `promptCoordinateChoice`'s
   button label: **relabel, do not remove.**

**Complexity budget for this recommendation: net added controls 0. Removed controls 0.**
Items 1-3 are internal. The only user-visible change proposed is text on two existing control
group labels (rotation, side) and one word in the existing overlay chip. No new panel, no new
mode, no new modal, no confirmation added to any read path.

---

## Living-doc update points (for doc-keeper - I changed no docs)

Found via `docs/process/DOC_OWNERSHIP.md` rows matched on the code paths I read:

- **`docs/spec/MAP_ALIGNMENT_SPEC.md` §1** - the mechanism citation `map_editor.js:3350-3356`
  is stale; the lines are now **3361-3367**. Also §1 names only the rotation button; the
  Wafer Side radio has the identical structure (Q2.A) and should be named beside it.
- **`docs/spec/MAP_EDITOR_SPEC.md` §5** (row 98, overlay alignment contract) - §5 does not say
  that the bbox **basis** diverges between client (valid-die mask) and server (circle). That is
  the alignment contract's biggest hole.
- **`docs/spec/MAP_EDITOR_SPEC.md` §6** (row 60/101, plan contract) - should state explicitly
  that the controller surface passes no coordinate data, so the server is the sole frame reader
  for the plan, and list the five silently defaulted fields.
- **`docs/map_editor/README.md`** (row 79) - the file-boundary table should carry the census:
  249 top-level functions, 43% of function lines in cross-layer functions, 6,356 code lines.
- **`DOC_OWNERSHIP.md:83`** already records the open contradiction about drawing the wafer
  circle when geometry is undeclared (`총괄 판단 대기`). Q2.D confirms it is still live.
- **`docs/architecture/PRIMITIVES.md`** - `getVisualGridDimensions` (`:6418`) is a primitive
  with 10 bypassing sites; worth listing so the next round reuses it.

## Proposed lessons for `agent_workspace/memory/map-pm.md` (proposal only)

- **함정**: 「어느 상태가 여러 곳에서 쓰이는가」만 세면 진짜 원인을 못 본다. 유효 다이의 세 번째
  clear site는 대입문이 아니라 **리졸버의 부재 분기**였고 grep으로 안 잡혔다.
  **올바른 방법**: 상태의 쓰기 지점이 아니라 **질문의 답변 지점**을 센다 — 같은 질문에 답하는
  함수가 몇 개이고 필드 집합이 서로 다른가. 실측: 「지금 프레임이 무엇인가」 20곳, 「화면 치수」 11곳.
- **함정**: 파일이 길다는 진단을 줄 수로 내면 틀린다. 10,867줄 중 3,729줄이 주석(비공백의 37%)이고
  코드는 6,356줄이다. **올바른 방법**: 줄 수는 blank/comment/code로 갈라 재고, 재개발 논거는
  코드 줄 수가 아니라 **교차 레이어 비율**(여기서는 함수 줄의 43%)로 낸다.
