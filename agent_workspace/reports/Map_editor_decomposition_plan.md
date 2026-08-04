# Map Editor — Definition, Invariant Inventory, and Rebuild Recommendation

**Author:** map-pm · **Date:** 2026-08-04 · **Status:** input to a rebuild decision. Nothing executed.
**Constraint honoured:** `client2/src/map_editor.js` was read only, never edited.

**Framing (updated).** This began as a decomposition plan. Following the user's ruling
(*"이거 모으고 맵 에디터 처음부터 다시 개발해보자"*), the definition in §2 is now read as the
**specification of the new system**, and the current code is **evidence**, not the subject.
§§1–12 are retained because they are the measurement that justifies the decision; **§13 is the
invariant inventory, §14 the rebuild recommendation, §15 the switchover bar, §16 the scope fence.**
If you read only one part, read §13 — it is worth more than the code it came from.

All numbers below are measured, not estimated. Method: `rolldown/parseAst` (the same parser the
bundler and `undeclared_identifier_harness.mjs` use) over `client2/src/map_editor.js`, plus a
string-anchor scan of all 43 harness/contract `.mjs` files. Scripts are in the session scratchpad.

---

## 0. Executive summary

**F0 — the finding that outranks the rest. The alignment loop is not slow; it is
information-free, and the code says so explicitly.**

The operator's dominant activity is *alignment search*: hold a frame, try a map against it, and
discover the map's unknown rotation/flip. Measured in code, that search cannot produce information,
and the reason is a single `return null`:

```js
// client2/src/map_editor.js:1976-1977, inside reseatCellsToStoredCoords
if (was.rotation !== now.rotation || was.side !== now.side || was.invertY !== now.invertY
  || was.startX !== now.startX || was.startY !== now.startY) return null;
```

The mechanism that re-interprets stored data under a new frame — "hold the stored coordinate, move
the canvas cell" — is **switched off for exactly the axes the operator is searching over.** Its own
comment (`:1956-1958`) states this is deliberate:

> 🔴 **방향(회전·반전·Y반전)과 START는 반대 연산이다**(규칙 ⑤: 다이를 붙들고 번호를 옮긴다).
> 그 축이 하나라도 다르면 이 반응은 **아무것도 하지 않는다.**

The consequence is exact. `gridData` is keyed in **die-index space** (`map_editor.js:7986`,
`gridData[\`${physical.x}_${physical.y}\`]`), and the valid-die mask is evaluated in that same space
(`isValidDieAt`). The canvas↔die-index mapping is a function of `(rotation, side)`. So turning the
rotation knob applies the **same** transform to the cells and to the mask. Their relative
configuration is invariant. The picture is rigid. **No observation is produced, so no attempt can
distinguish a right answer from a wrong one** — precisely the user's report.

This is not a defect in a function. It is one rule serving two jobs:

| Job | Correct semantics | Today |
|---|---|---|
| **Declare** a *known* orientation | hold the die, renumber the stored coordinate (rule ⑤) | ✅ works |
| **Search** for an *unknown* orientation | hold the observation, vary the interpretation, watch them separate | ❌ inexpressible |

**The honest fixed reference.** The physical wafer does not rotate; the real dies do not move; the
stored `(x, y)` bytes do not change when a knob turns. Those are the **invariants**. Rotation, side,
Y-invert, START and the origin box are the **interpretation**. Today the observation (`gridData`) is
stored *downstream of the interpretation*, in die-index space — so the observation moves whenever
the interpretation moves, and the difference between them can never be displayed. **Separating the
invariant from the interpretation is the architecture; it is not a feature layered on top.**

The seam already exists and is one condition wide (`:1976`). The primitive already exists
(`reseatCellsToStoredCoords`, and the overlay path's `projectCellsToWaferMm` → `seatWaferMmInFrame`,
which anchors a source map in physical mm independently of the target frame — the closest existing
primitive to "hold one, vary the other", and the first thing the execution round should evaluate
before building anything new). **What is missing is not machinery. It is a place to stand.**

Consequences for this plan, and they reorder it:
- The decomposition's organising principle is **invariant vs interpretation**, not "coordinate
  transform vs rendering". §6's module boundary already draws that line by making the resolved
  `spec` an explicit parameter; §9's steps should be judged on whether they widen that seam.
- **A second gate joins the harness gate:** does the step make the alignment loop expressible?
  Scored per step in §9.
- No new mode is needed, and none should be built (§2.0.3).

**F0-bis — the ontology consumes an alignment the editor cannot establish. This outranks every
file-splitting decision in this plan.**

Measured on the server side:

1. **The ontology's atomic identity IS the die, and the key IS the stored x/y.**
   `server/config/ontology_mapping.json` declares four die-granular labels — `CoreCell`
   (`:70-80`, identity `["core_lot","core_slot","core_x","core_y"]`), `DtCell` (`:120-129`),
   `BondCell` (`:193-203`), `DtCellClaim` (`:226-233`). `graph_materializer.compose_identity`
   (`:54-68`) joins them into a primary key string like `LOT-A|05|13|5`, stored UNIQUE as
   `(label, identity_key)` (`database/models.py:311-319`).
2. **Those coordinates are DB coordinates — origin-relative, bounding-box-relative, frame-dependent**
   by the editor's own contract (`MAP_EDITOR_SPEC` §1-bis; `map_overlay.make_frame_transform`
   docstring `:482-487`: `xv = c - box.minC + start_x`).
3. **Different tables are merged by byte equality of those coordinates.** `ontology_mapping.json:152-166`
   declares `FROM_CORE_CELL` on `dt_log`, targeting the same `(CoreCell, lot|slot|x|y)` node that
   `core_wafer_map` produces. The config's **own prose three lines earlier** (`:121`) says the two
   coordinate systems are *"서로 독립인 미지 프레임에 있다"* — independent, unknown frames.
4. **No graph module reads a frame. Zero occurrences** of `wafer_map_metadata`, `grid_metadata`,
   `rotation`, or `map_overlay` in `graph_materializer.py`, `ontology_config.py`,
   `graph_sync_worker.py`, `graph_orphans.py`, `graph_stale_edges.py`.
5. **Nothing checks `auto_registered`.** The correct gate exists and is well built —
   `map_overlay.geometry_declaration` (`:333-353`) tests the flag before the values — but it lives
   only in the overlay/plan path. The graph path cannot even reach it: a `DtCell` node's identity
   contains no map key with which to look the frame up.
6. **The collision is specific, not theoretical.** `map_meta_registrar` synthesizes
   `chip 1x1 / offset 0 / auto_registered: true` for any table with `map_key_columns` and a
   coordinate binding. `core_wafer_map`, `dt_log`, `bonding_log` all qualify — and they are
   **exactly the three tables whose rows become x/y-keyed graph nodes.** The overlay layer refuses
   to align these maps; the graph layer merges them into shared identities without asking.
   Measured: 320 of 668 registered rows (47.9%) carry synthetic geometry.
7. `map_overlay.resolve_align:577-580` treats absent meta as identity alignment
   (`"맵 메타 부재 — identity로 간주"`), so even inside the overlay path "unregistered" and
   "same frame" produce the same answer.

**Stated plainly: the graph is currently asserting that dies are the same die on the basis of
coordinates whose frames are unknown, unequal, or synthetic — and the tool responsible for
establishing those frames has no working mechanism for doing so (F0).** The two halves compound.
This is a correctness problem at the foundation of the ontology, not a refactoring concern, and it
should be triaged as its own lane with `server-pm` and `ontology-pm` before or alongside any step
in §9. Nothing in this decomposition plan fixes it; the decomposition only makes the editor half
*capable* of fixing it.

One adjacent finding worth routing: `virtual_join_config.DEFAULT_UNRESOLVED_LABEL = "미상"`
(`:123`) is written into a cell's `value` slot by `virtual_join_executor.py:497-502`, in the same
`{value, is_overwrite, sources}` shape as real data. The module documents the consequence itself
(`:435`): the two distinct facts — "no matching row" and "row exists but blank" — are unrecoverable
downstream. A presentation word in a data slot, read by the ontology's consumers.

**F1. The harness gate is mostly *not* gated on splitting the file.**
The criterion is "how many harnesses stop slicing source text". Measured: **24 of 34 harnesses do
mutation testing**, which re-evaluates *modified* source text. A plain `import` cannot serve that,
no matter how the file is split. So a pure code-move program would move 785 lines and free
approximately **two** harnesses. The unlock is a **harness-side pattern** that already exists and
is green in this repo: `retroactive_view_harness.mjs` mutates text and then
`import('data:text/javascript;base64,…')`. That pattern generalises. **Step 0 of this program is a
harness change, not a code move.** Without it the ceiling on liberation is ~2; with it the same
code moves free 20+.

**F2. Rendering is not a domain. Two of the user's four axes do not survive contact with the code.**
`좌표 변환` is real and is the most cohesive unit in the file (27 functions, 601 lines, **1**
module-state write). `렌더링` is not a peer domain — `renderGridCanvas` is a 326-line *consumer*
that reads 11 module bindings; the genuinely separable drawing primitives total ~25 lines.
`저장 및 키 관리` splits in two: the key half **already left** (`map_key.js`, R1), and the save half
(`pushMapData` 325L/15 bindings, `saveMapSpecOnly` 162L) can never leave. `DOE` has **already
largely left** — it lives in `transfer_plan.js`, `split_registry_row.js`, `doe_bands.js`. Details in §3.

**F3. The editor→planning seam is already the target architecture, and it carries no geometry.**
`map_editor.js` imports five named functions from `transfer_plan.js` and pushes context through a
controller-injection interface. `transfer_plan.js` has **5** module `let/var` against the editor's
**48**. But `notifyMapContext` passes `table · mapKey · loaded · depth · parent` — **no coordinate
or geometry data at all**. So "planning shares the coordinate system" describes a *future* state.
The extracted coordinate module is precisely the artifact that would make that sharing possible
without sharing state, which under the ontology framing is the strongest single argument for it.

---

## 1. Measurements

### 1.1 The file as it stands

| Metric | Value |
|---|---|
| Total lines | **10,814** |
| Top-level functions | **252** |
| Lines inside top-level functions | 8,470 (78.3%) |
| Module-level `let`/`var` (the ceiling metric) | **48** — ceiling 48, **headroom 0** |
| Module-level `const` | 39 |
| Top-level non-declaration statements | 2 |
| Transitively pure functions (no module state, no `el`) | **78**, totalling 1,354 lines |

### 1.2 Largest functions

| Lines | Range | Function | module r/w | `el.*` | calls |
|---|---|---|---|---|---|
| 428 | 409–836 | `initDOMElements` | 4/3 | 61 | 35 |
| 419 | 8640–9058 | `resolveValidDie` | 9/4 | 5 | 20 |
| 390 | 4840–5229 | `loadExistingMap` | 17/13 | 9 | 31 |
| 326 | 3236–3561 | `renderGridCanvas` | 11/2 | 9 | 16 |
| 325 | 5754–6078 | `pushMapData` | 12/3 | 4 | 17 |
| 291 | 10047–10337 | `addOverlayLayer` | 4/2 | 2 | 21 |
| 255 | 6782–7036 | `copyGridToExcel` | 5/0 | 1 | 16 |
| 209 | 4402–4610 | `renderLegendTable` | 5/1 | 2 | 8 |
| 162 | 9434–9595 | `saveMapSpecOnly` | 7/2 | 1 | 8 |
| 75 | 7855–7929 | `restoreEditorState` | **21/21** | 17 | 10 |

`restoreEditorState` reads **and writes 21 of the 48** module bindings — it is the frame stack's
serialiser. Any binding that exists is a line in this function. This is why the ceiling is the
right instrument and why it is currently the binding constraint.

### 1.3 MODULE_STATE — which of the 48 can go, and what it costs

Verified against source, not inferred:

| Binding | Evidence | Removal |
|---|---|---|
| `tables` (L56) | **0 readers, 0 writers.** Every other occurrence in the file is `data.tables`, a `/tables` URL string, or a local `tableName`. | delete — 1 line |
| `isMouseDown` (L62) | Assigned at 1011/1085 only, **never read anywhere**. Write-only. | delete — 3 lines |
| `editorFrames` (L7736) | 5 readers, **0 writers** — never reassigned, only mutated in place. | `let` → `const` — 1 word |
| `isRenderScheduled` (L3197) | 1 reader / 1 writer, both inside `scheduleRenderGridCanvas`. | closure-encapsulate |

`MAP_EDITOR_SPEC.md:165` already names `tables` and `isMouseDown`; this measurement confirms both
independently and adds two more. **48 → 44 with zero behaviour change and zero harness impact** —
none of these four names is a slice anchor in any harness (`tables`/`isMouseDown` appear only in
prose comments inside `check_harnesses.mjs`).

Four further single-owner caches (`zoneColumnsPresent`, `cellDraftTimer`, `seatKeyCache`,
`themeColors`) are also encapsulable, but each sits inside a function that **is** a slice anchor
(`probeZoneColumns`, `scheduleCellDraft`, `canvasSeatKeys`) — they belong after Step 0, not in it.

> **Warning against gaming the metric.** The counter deliberately excludes `const` holding a
> mutable container, and its own header calls that "the honest weakness". Converting
> `let x = {}` to `const x = {}` would lower the number while changing nothing. **Do not do it.**
> Equally, moving state into a new file lowers *this file's* count without reducing global mutable
> state. Every reduction claimed in this plan is a genuine deletion or a genuine scope reduction;
> where a step merely relocates state, it is labelled as such.

---

## 2. What the map editor is for — definition first

Written as jobs, from the spec/guides, the board's user requests, and the UI, with the code used
last as a check. The user's own reframing sets the order: **this is ontology infrastructure.**

### 2.1 The founding statement

> The map editor is where a wafer's **coordinate frame is declared, aligned, and inspected**, so
> that a die observed through one data source can be identified with the same die observed through
> another. Editing, painting, rendering and planning are operations performed *on top of* that
> frame. **The coordinate system is the product.**

Two consequences the user stated explicitly and that this plan treats as functional requirements,
not conveniences:

- **R-FIND** — a map must be findable fast, by identity rather than by transcription.
- **R-SEE** — the transform in force must be inspectable fast.

### 2.2 The jobs

**J0 is the primary job. Everything below it is done afterwards.**

| # | Job | Starts with | Ends with |
|---|---|---|---|
| **J0** | **Alignment search** — discover a map's unknown rotation/flip by holding a frame and trying maps against it, repeatedly | a candidate map and a frame hypothesis | a frame under which the map's dies land on the real dies. **Today: not expressible (F0).** Each trial also costs a full reload, because reload is the only operation that re-derives cell placement through a changed box |
| **J1** | Open a map and restore its frame | target table (must declare `map_key_columns`) + a map key | canvas restored from `wafer_map_metadata`; legacy maps get a 3-way restore choice |
| **J2** | Declare the physical geometry | diameter, chip X/Y pitch, offset X/Y, edge margin — or a geometry preset | `grid_metadata` phys_* fields; grid dims **derived** from geometry |
| **J3** | Declare grid topology and orientation | rotation 0/90/180/270, FRONT/BACK, Invert Y, START X/Y | `rotation`, `side`, `grid_y_invert`, `grid_start_x/y`, `grid_cols/rows` |
| **J4** | Declare the valid-die basis | circle geometry, or a reference to another map (`valid_die_ref`) | `valid_die_ref`; basis is one of `circle` / `ref` / `refused` |
| **J5** | Author a valid-die template map | one of three seeds (from circle / whole grid / open for re-edit) | an ordinary map; "painted cells *are* the valid die" |
| **J6** | Paint the map | a legend value as brush | painted cells in `gridData`; `'F'` cells refused by every edit path |
| **J7** | Push the map | painted grid + map key + target table | `replace_map` purge-and-reinsert; three refusal gates |
| **J8** | Save the geometry row only | whatever key is currently typed | a `wafer_map_metadata` row; **zero cells written** |
| **J9** | Plan the experiment on the map (DOE) | legend values, STACK integer, materials | split-registry rows; quantities never stored, always derived |
| **J10** | Read the material roll-up | material tokens `lot[_slot][:BIN]` | derived availability table; `unknown` is not `0` |
| **J11** | Round-trip the company bonding form via Excel | COPY HEADER MODE → Excel → Ctrl+V | screen-only replacement after one confirm |
| **J12** | Overlay another map for comparison | source table + source key | dots placed by wafer-mm alignment, coloured by their own value |
| **R-FIND** | Find the right map fast | a table | an ordered, labelled candidate list |
| **R-SEE** | See the transform in force | the open map | rotation/side/notch/origin legible without computation |

### 2.2.1 Judging the current design against J0

| Question | Measured answer |
|---|---|
| Actions per trial fit | Change frame → **reload** (the frame change alone yields nothing, F0) → visually compare. The reload is not an optimisation target; it is the only step that produces any change at all. |
| What makes the loop expensive | In order: **(1) the loop yields no information without a reload** (`:1976`); (2) the load path used to clear the valid-die designation — three sites, fixed today; (3) map-key discovery — improved today (see below); (4) the transform in force is shown only as rotation/side chips and the notch marker, with no statement of *which* frame produced the current placement. |
| Which frame changes can be re-seated without a refetch | **Geometry axes — pitch, diameter, offset, edge margin, and the derived grid dims — already are** (`reseatCellsToStoredCoords`, rule ④), and the valid-die basis rides the same path (its comment at `:1949-1954` states geometry-preset change and reference designation are *the same operation*, not similar ones). **Orientation axes — rotation, side, Y-invert, START — are refused by construction** (`:1976-1977`, rule ⑤). That is the boundary, and it is clean: it is exactly the line between "the origin box moved under the cells" and "the operator redeclared what the numbers mean". |
| Does J0 need a new mode? | **No, and it should not get one.** Rules ④ and ⑤ are two *jobs*, not two modes — and the comment at `:1956-1958` warns that letting rule ④ fire on rotation would have it *overwrite* rule ⑤ (`규칙 ④가 규칙 ⑤를 덮어쓴다`), which would silently rewrite stored coordinates. The zero-control answer is a **read-only second reading** of the same data — the loaded server cells projected through the *stored-coordinate* interpretation and drawn alongside the die-index picture. Rotating then separates them, and the separation is the information. The overlay layer already anchors a source map in physical mm independently of the target frame (`projectCellsToWaferMm` → `seatWaferMmInFrame`); **the execution round must evaluate that existing primitive before building anything**, per the standing rule to check `PRIMITIVES.md` first. Complexity budget: **net +0 controls**. |

**Correction to an earlier brief.** The map-key list was described as having no order and no labels.
That was true before today. `populateMapKeyDatalist` (`:9743-9799`) now sorts via `compareMapKeys`
(numeric-aware `localeCompare`) and labels every candidate with `mapSpecSummary` — `cols×rows`,
rotation, back, Y-invert — built from the `grid_metadata` already in the same response, at **zero
extra requests per candidate**. It also distinguishes `complete` / `truncated` / `unavailable`
rather than letting a failed read read as "no maps exist". Two residual gaps: the ordering is
alphanumeric by key, not by recency or relevance; and the server has **no map ranking at all**
(`order_by` defaults to `row_id` ascending = insertion order, `main.py:1343, 1467-1468`), so the
client sorts whichever arbitrary 500 rows it received. For **R-FIND** as a functional requirement,
that server-side gap is the real one.

### 2.3 Reconciling with the user's four named axes

| User's axis | Verdict | Evidence |
|---|---|---|
| **좌표 변환** | ✅ **Real, and the most cohesive unit in the file.** Closure of 27 functions, 601 lines, reads 6 module bindings, writes **1** (`physFrameOverride`, itself the frame-window mechanism), 11 `el.*` handles — all six geometry inputs plus five grid inputs. | §4.1 |
| **렌더링** | ❌ **Not a domain.** `renderGridCanvas` (326L) reads 11 bindings and writes 2; it consumes coordinates rather than being a peer of them. The separable drawing primitives — `cellFillColor` (5L), `paintOverlayDot` (15L), `markerAxisRadius` (3L), `parseCssColor` (10L), `toExcelHex` (9L) — total ~42 lines. Splitting "rendering" would produce one orchestrator that cannot move and a handful of one-liners. | §4.2 |
| **저장 및 키 관리** | ⚠️ **Two things with opposite prognoses.** The *key* half already left in R1 (`map_key.js`, canonical form, scored by `contracts/map_seam/`). The *save* half is orchestration — `pushMapData` 325L/15 bindings, `saveLegendToServer`, `saveMapSpecOnly` 162L — and `DOC_OWNERSHIP.md:70` already rules that it stays **permanently**. | §4.3 |
| **DOE** | ⚠️ **Already largely outside the file.** It lives in `transfer_plan.js` (1,876L, **5** module bindings), `split_registry_row.js` (R2), `doe_bands.js`. What remains in `map_editor.js` is the legend cluster — 7 module bindings used by map load, frame stack, draft restore and the legend panel — which the spec already rules stays. | §4.4 |

**Cohesive units the user did not name, which the measurement found:**

| Unit | Size | Why it is a unit |
|---|---|---|
| **Valid-die designation grammar** | 14 symbols / 238 lines | It is what burned four repair rounds today, and it is the **only** domain with a server contract scoring both sides (`contracts/map_seam/`). |
| **Company Excel form round-trip** | 25 symbols / 464 lines | Fully self-contained; a distinct artifact (the customer's bonding-map form) with its own grammar. 3 harnesses cover it. |
| **Map key discovery / datalists** | 13 symbols / 234 lines | Directly serves **R-FIND**, now a functional requirement. |
| **Frame stack** (`snapshotEditorState` / `restoreEditorState`) | 139 lines | Touches 21 of 48 bindings. Not extractable — but it is *why* the ceiling matters, and it should be named as the reason. |

---

## 3. Where the code disagrees with the definition

The three shapes requested, each measured.

### 3.1 One job implemented in several places

| Job | Spellings | Consequence |
|---|---|---|
| Clear the valid-die designation | **3** — `switchTable`, `loadExistingMap` head, inside `resolveValidDie` | 3 failed repair rounds today; lead found 2, QA found the 3rd |
| "Does this frame hold unsaved work" | **2** — `unsavedWorkNotice` (10L) exists, but the guard `!framePushed && frameTouched` is spelled inline at the doors | Board N35: after a successful Push, one further cell edit is silently discarded, because `scheduleCellDraft`/`persistLegend` never lower `framePushed` |
| Compose the map key | **2** — Push's composer vs `getCurrentMapKey()` | Board M6, measured: `slot="007.5"` → Push writes `L1_7.5`, `getCurrentMapKey()` returns `L1_007.5`; `slot='ABC'` collapses every unreadable value onto `L1_NaN` |
| **Slice a named function out of source text** | **8** independent copies across the harnesses; **6** more for consts | This is the same disease in the test tree, and it is the direct cause of two of today's wrong-function scorings (§7) |

### 3.2 One place implementing several jobs

- **`getWaferBoundingBox`** (111L) answers two different questions behind an `opts.circleOnly`
  flag: "what is the wafer's physical extent" and "what is the coordinate origin box". It calls
  `isValidDieAt`/`validDieBasis`, so **geometry depends on the valid-die mask**. Under the ontology
  frame this is not a smell — it is load-bearing and correct — but it must be *stated*, because a
  doc currently denies it (§3.4).
- **`loadExistingMap`** (390L, 17 reads / 13 writes) — despite the R3 decomposition into 7 named
  stages, the orchestrator still writes 13 bindings.
- **`initDOMElements`** (428L, 61 DOM handles) — binding, wiring, and initial state in one.

### 3.3 A job with no home

- **Origin/offset coherence** (board 1-f): "as OFFSET_X increases the valid die stays inside the
  circle but ORIGIN keeps moving right". No function owns the invariant relating offset to origin;
  it is an emergent property of `getWaferBoundingBox` + `getTransformedPhysicalConfig`.
- **"Is this geometry actually measured?"** — `physDeclaration` was created to own it and its
  comment says "🔴 여기가 유일한 철자다". That is the right shape and should be the template for
  the two rows above.

### 3.4 Doc/code disagreements found while measuring — for doc-keeper, not for me

1. 🔴 **`docs/map_editor/architecture_and_management.md:118` is false.** It states
   "**바운딩 박스는 건드리지 않습니다.** `getWaferBoundingBox`… 계속 원으로 계산합니다".
   The code disagrees at `client2/src/map_editor.js:1816-1819`:
   ```js
   const maskDeclaresTheFrame = !(opts && opts.circleOnly)
     && !physFrameOverride
     && validDieBasis() === 'ref';
   const tag = maskDeclaresTheFrame ? `V${validDieResolveSeq}` : 'C';
   ```
   and `const useMask = (tag !== 'C');` at 1829. `docs/map_editor/philosophy.md:89` is the correct
   version. Under the ontology framing this is the highest-severity doc defect in the set: it
   denies that the mask defines the coordinate origin.
2. `docs/spec/MAP_EDITOR_SPEC.md` §1-bis-2 table needs one row per landed step.
3. `docs/guide/VALID_DIE_MAP_GUIDE.md` §7 (`:222-226`) still instructs users to press 🎯 APPLY /
   💾 SAVE, which §4 (`:66`) records as deleted the same day.
4. `docs/process/PROJECT_STATUS.md:30` still describes APPLY as a shipped control (`컨트롤 순증 +1`)
   after commits `5b15c24`/`d06ac6d` removed it. Board is lead-owned — flagging only.

---

## 4. The domains, and the coupling that decides the order

### 4.1 Coordinate transform — the core

Transitive closure of the 22 seed transform functions: **27 functions, 601 lines**.

```
closure READS  (6): boundingBoxCache currentRotation currentSide physFrameOverride
                    validDie validDieResolveSeq
closure WRITES (1): physFrameOverride
closure el.*  (11): gridCols gridRows gridStartX gridStartY gridYInvert
                    physChipX physChipY physEdgeMargin physOffsetX physOffsetY physWaferDia
```

**The chokepoint.** Every geometry read in the entire file passes through exactly four functions —
`physNum`, `gridDimNum`, `physDeclaration`, `geometryIsAutoRegistered` (40 lines total) — and each
resolves **frame window → DOM element → default**. `getDieIndex` does not read the DOM directly
(its comment forbids it); it calls `getTransformedPhysicalConfig`, which calls `physNum(key, el.x, dflt)`.

So the entire transform stack is pure *except* for one resolution step. Replace that step's two
implicit sources with one explicit `spec` parameter and the stack becomes importable. **This is
not a rewrite** — `withPhysFrame` already proves the frame is substitutable; the change converts
dynamic scoping into a parameter.

**The honest entanglement.** `getWaferBoundingBox` calls `isValidDieAt` and `validDieBasis`, so
geometry depends on the valid-die mask. It is a real, intended dependency (§3.2) and it means
**coordinate transform and valid-die basis are not independent domains**. The coupling is narrow —
one predicate — so it inverts cleanly by injection: the box takes an `isValid(c, r)` predicate.
That is the design, and it is why S2 (valid-die) is sequenced before S3 (origin box).

### 4.2 Rendering

Not separable, per F2. `renderGridCanvas` stays. The ~42 lines of pure drawing primitives ride
along with whichever step needs them; they do not justify a step of their own.

### 4.3 Save and key management

Key half already extracted. Save half stays permanently, per `DOC_OWNERSHIP.md:70`:
> 🔴 **경계는 「순수한가」로 긋는다**: 모듈 상태를 안 건드리는 덩어리만 나가고, 상태를 쓰는
> 오케스트레이션은 **영구히** 남는다(미룬 것이 아니다).

### 4.4 DOE / planning

Already outside. **The seam is already correct and should be the template**: `initTransferPlan(controller)`
injects accessors (`getMapContext`, `getLegend`, `getActiveBrush`); the editor pushes via five named
functions. Result: 1,876 lines with **5** module bindings.

**But it carries no geometry.** `notifyMapContext` passes only identity. Making the coordinate
system available to planning — the user's stated requirement — means the planning side must be able
to `import` the transform module. That is only possible if the module holds no editor state. This
is the ontology framing's concrete demand on the design: **`STATE# 0` is not a style preference
here, it is the requirement that makes the coordinate system consumable.**

---

## 5. The gate — measured honestly

Baseline: **32 harness/contract files** name at least one `map_editor.js` symbol as a string
anchor; **728 slice-edges** in total (one edge = one file naming one symbol).

### 5.1 What the split alone buys

| Step | Symbols / lines | Edges removed | Cumulative | Files fully freed |
|---|---|---|---|---|
| S1 `wafer_geometry.js` | 17 / 317 | 195 | 195/728 (27%) | 0 |
| S2 `valid_die_ref.js` | 14 / 238 | 98 | 293/728 (40%) | **2** — `m4_symbol_extractability_probe`, `map_key_canonical_harness` |
| S3 `wafer_frame.js` | 13 / 335 | 91 | 384/728 (53%) | **2** — `reposition_regime_probe`, `valid_die_head_parity_oracle` |
| S4 `company_form.js` | 25 / 464 | 62 | 446/728 (61%) | **1** — `map_seam/vectors.json` (its single `copyHeaderAuxRows` edge) |
| S5 `map_datalist.js` | 13 / 234 | 14 | 460/728 (63%) | 0 |

**Read this table honestly: 1,588 lines move and five files are fully freed.** If the gate is read
strictly as "files that stop slicing entirely", the split alone scores poorly, and I am not going
to dress that up.

### 5.2 Why — and what actually unlocks the gate

Three structural reasons, all measured:

1. **Harnesses slice *closures*, not functions.** `geometry_origin_reseat_harness` names 51 symbols
   because to run `resolveValidDie` it must reconstruct everything it calls. A file split reduces
   the count but rarely to zero.
2. **24 of 34 harnesses mutate.** Mutation testing requires re-evaluating modified source text;
   `import` cannot do it. This is the dominant blocker.
3. **Some harnesses structurally cannot import, ever**, and should be excluded from the denominator:
   `copy_header_count_harness` and `valid_die_head_parity_oracle` slice **two git revisions**
   (`git show <ref>:client2/src/map_editor.js` — a historical blob has no module);
   `copy_header_count_harness` also slices a *statement region* between `GATE_START`/`GATE_END`;
   `valid_die_dirty_guard_harness` slices two `if (el.…) {…}` **wiring blocks** inside
   `initDOMElements`; `virtual_column_render_harness` slices six anonymous arrow bodies;
   `undeclared_identifier_harness`, `check_clipboard_convention`, `contracts/blank_predicate` and
   `contracts/config_resolve_report` are text-assert **by design**.

**The unlock already exists in this repo.** `retroactive_view_harness.mjs` mutates module text and
then imports it as a data URL:
```js
source.replaceAll("'./config_resolve_view.js'", `'${BASE_URL}'`)
await import(`data:text/javascript;base64,…`)
```
It is green today. Generalising it into one shared helper — call it `client2/tests/_module_probe.mjs`
— gives every mutating harness a way to test a real ES module. **That, not the file split, is what
moves the gate**, and it is why it is Step 0.

With Step 0 in place, the per-step "fully freed" column changes character: a harness whose entire
remaining closure lives in extracted modules can import all of them and mutate via data URLs.
Post-S3 residues measured: `overlay_wafer_mm_harness` 30→3, `valid_die_authoring_harness` 26→5,
`map_seam/client_harness` 14→4, `isotropic_cell_harness` 27→9.

**Immediately convertible with no map_editor.js change at all** (Step 0 alone frees these):
`overlay_provenance_harness` (needs only `escapeHtmlAttr` + `renderOverlayList`),
`push_gate_harness` (`PUSH_SYSTEM_COLUMNS` + 2 pure functions),
`virtual_column_render_harness` (map portion — same two symbols),
`contracts/band_arithmetic` (already touches only ordinary modules).

### 5.3 The two metrics to report per step

Because "fully freed" is coarse, every step below reports both:
- **edges removed** — slice-edges eliminated (the continuous measure);
- **files freed** — files dropping to zero slices (the binary measure).

A step that removes many edges from the *most-churned* symbols is worth more than the raw count
suggests: the top hostages are `physNum` (20 files), `getScreenShift`/`getTransformedPhysicalConfig`
(19), `validDieBasis`/`isValidDieAt` (19), `gridDimNum`/`getDieIndex`/`isCellInsideWaferFast` (17),
`getWaferBoundingBox` (16) — all of which are S1/S2/S3 content.

---

## 6. Import surface

### 6.1 `client2/src/wafer_geometry.js` (S1) — `STATE# 0` achievable

```
readSpec(frame, dom)              -> resolved spec; the ONE frame→DOM→default resolution
declarationOf(spec, key)          -> { value, source }  (frame|screen|unparsable|absent|auto_registered)
isAutoRegistered(spec)            -> boolean
transformedPhysicalConfig(spec, rotation, side)
screenShift(physConfig, cellW, cellH)
dieIndex(colVisual, rowVisual, cols, rows, rotation, side, physConfig)
canvasCellFromDieIndex(...)  dieIndexToWaferMm(...)  waferMmToDieCell(...)
canvasCellFromDb(...)  dbCoords(...)  isCellInsideWaferFast(...)
frameFromMeta(meta)  frameDimBounds()  frameDimError(...)  frameAxesKey(...)
```

**Received as parameters, never read from module scope:** the resolved `spec` (which subsumes
`physFrameOverride` *and* the eleven `el.*` handles), `rotation`, `side`, and the `physConfig`.
**Stays behind in `map_editor.js`:** `physFrameOverride` (the window is editor session state),
`withPhysFrame`, `el`, and thin wrappers preserving today's call shape during the transition.

`STATE# 0` is achievable for S1. The cost is real and should be stated: `withPhysFrame` is
**dynamic scoping**, and converting it to a parameter means threading `spec` through the call chain
— 14 call sites of `withPhysFrame`, and every function between them and the leaf transforms.
The precedent that this is acceptable is `getMapIdFromMeta`, which took `tableSchema` as a second
argument when it moved to `map_key.js` in R1, body byte-identical.

### 6.2 `client2/src/valid_die_ref.js` (S2) — `STATE# 0` achievable

```
parseValidDieRef(raw)  validDieRefDisplay(ref)  applyValidDieRef(meta, ref)
validDieRefPayload(...)  validDieChainError(...)  resolveReferenceSpec(...)
deriveMaskKeys(...)  summariseReseat(...)
basisOf(validDieState)              // was validDieBasis(), reading module `validDie`
isValidDieAt(validDieState, physX, physY, frameOpen)
refFromControls(validDieState, inputValue)   // was reading el.validDieRefKey
refForPush(validDieState, inputValue)
```

The state-reading four (`validDieBasis`, `isValidDieAt`, `validDieRefFromControls`,
`validDieRefForPush`) take `validDie` as a **first parameter**. `m4_symbol_extractability_probe`
already asserts that the module-global path and an explicit `state` argument are the same code path
— **that assertion is the licence for this change and should be kept as the regression net.**

### 6.3 `client2/src/wafer_frame.js` (S3) — `STATE# 0` with one injection

```
waferBoundingBox(spec, rotation, side, { isValid, circleOnly, cache })
cellMetrics(spec, ...)  gridCellObject(...)  visualGridDimensions(...)
projectCellsToWaferMm(...)  projectCellsToPhys(...)  seatWaferMmInFrame(...)
frameDieLattice(...)  resolveFrame(...)  currentFrame(spec, rotation, side)
```

`isValid` is the injected mask predicate — this is the inversion that separates §4.1's entanglement.
`cache` (today `boundingBoxCache` + `validDieResolveSeq`) is passed in, so the module holds no cache
of its own. **This relocates two bindings rather than deleting them** — labelled honestly.

---

## 7. Traps this specific extraction will spring

1. **`export` inside a slice is a `SyntaxError` in `vm`.** Recorded at `MAP_EDITOR_SPEC.md:152`.
   Any temporary `export` added to `map_editor.js` breaks every slicing harness at once.
2. **Eight slicers, and they differ in load-bearing ways.** Only `coord_table_paste_harness`
   line-anchors (`^…`, `gm`) *and* asserts a unique match. The other seven can and do match inside
   comments — that is the `valid_die_authoring_harness` known-red (`projectCellsToPhys` matches a
   comment at offset 8297, ahead of the real call at 9564). Only the "S2" family walks the
   parameter list before looking for `{`; the "S1" family truncates on `loadExistingMap(opts = {})`.
   **Moving a symbol will break a different subset of harnesses depending on which slicer family
   holds it.** The path dictionary must be updated per family, and per `MAP_EDITOR_SPEC.md:152`
   hostages must be counted **by file path, not by symbol name** (R1 counted 3, actual was 5).
3. **A comment mentioning the symbol before its definition scores the wrong function.** Both
   `getWaferBoundingBox` and `physDeclaration` have long doc-comments naming the symbols they call.
   Any move that changes byte offsets can flip which match a non-anchored slicer finds.
4. **Six const-slicers, three different terminators.** `map_seam`'s `sliceConst` and
   `legend_map_scope`'s `extractConst` are **single-line only**; `company_roundtrip`'s counts
   brackets to a `;`. Reformatting a const across lines breaks a different subset.
5. **`split_registry_harness` is already dead and names 12 symbols that no longer exist.** It will
   not get worse, but it must not be counted as a harness this program can free.
6. **The file's own comments are contorted to protect slicers.** At `map_editor.js:1813-1815`:
   > ⚠️ 별도 함수로 빼지 않는다. 이 함수를 슬라이스해 실행하는 하네스가 넷이고, 모듈 전역
   > 의존이 하나 늘 때마다 넷이 전부 ReferenceError로 죽는다

   The source is being shaped by the test harnesses' extraction mechanism. **This is the clearest
   statement in the repo that the current arrangement costs design freedom**, and it should be
   quoted when justifying Step 0.

**Harnesses that go red on the day of each move** (all `known-red`-listable in advance):
S1 → the 20 files naming `physNum`. S2 → the 19 naming `validDieBasis`/`isValidDieAt`, plus
`contracts/map_seam` (a `vectors.json` `file:` field edit). S3 → the 16 naming `getWaferBoundingBox`.
Each is a path-dictionary edit, not a logic change — but they must be edited **in the same commit**
as the move, or the build gate goes red.

---

## 8. The invariant: proving zero behaviour change

### 8.1 What `contracts/map_seam/` gives

It scores 19 `map_editor.js` symbols against the server implementation, keyed by **role** in
`vectors.json` with a `{file, fn, status}` dictionary. Moving a symbol is therefore a **one-field
edit** (`file`), and the `status` vocabulary (`live`/`pending`/`required`) makes a rename fail loudly
rather than silently stop covering an axis. Procedure per step:

1. Run `check_contracts.mjs` before the move; record the matched/diverged counts.
2. Move, update `vectors.json` `file:` fields only.
3. Run again; **require byte-identical counts.** Any change in the *diverged* set is a stop.
4. Re-inject the previous (pre-move) function bodies and confirm the contract still passes — this
   proves the contract is measuring the moved code, not a stale copy.

### 8.2 What it does NOT cover — measured, do not assume completeness

- **M4 (board L312):** re-introducing a mask translation (`shiftX = 1`) leaves **all 23 harnesses
  green**. The harnesses assert "are stored coordinates preserved", and a mask shift does not move
  stored coordinates. **The refactor's safety net is structurally blind to the defect class the
  refactor most risks.** A new axis is needed, not a repair.
- **N24 (board L300):** perturbing `isCellInsideWaferFast` from `normDistSq > 1.0` to `> 1.02`
  leaves `check_contracts.mjs` fully green — `circle_mask` has **no vector within 1% of the boundary**.
- **M7 (board L310):** `standard_frame_origin_harness` cites `buildPushGridMetadata` by name in a
  comment and then re-types the record itself, so it compares its own copy with itself; the producer
  can die and it stays green (injected 19/0 ESCAPED).
- **M1 (board L186):** the `start_x/y` repair's harness (28 assertions, 5/5 mutants red) **is not in
  the repository** — it lives in a scratchpad.

**Recommendation before S3 (the origin-box step).** The mask-placement axis (M4) must exist first.
S3 moves `getWaferBoundingBox`, which is exactly where a mask-placement defect would be introduced,
and today nothing would catch it. **S3 must not run until M4's axis exists.** This is the one
ordering constraint in the plan that is a hard gate rather than a preference.

Per my own standing lesson: every fixture must **activate the defect axis** — anisotropic chip
(`chip_x != chip_y`), rotation 90/270, `back`, and `bbox != 0` simultaneously — and every step must
report "how many cells move if the wrong frame is used". If that number is 0, the fixture proved nothing.

---

## 9. Sequence

Each step is independently mergeable and independently green. The first step moves **no code**.

**Two gates, scored per step.** Gate A = slice-edges removed / files freed. Gate B = does the step
make the alignment loop (J0) expressible? Gate B is the more important of the two.

| Step | Gate A (edges / files freed) | Gate B — alignment loop |
|---|---|---|
| 0 harness unlock | ~8 / **4** | — (enables measurement of everything else) |
| 0a ceiling headroom | 0 / 0 | — (unblocks concurrent repair) |
| **1 `wafer_geometry.js`** | **195** / 0 | 🟢 **Direct.** Makes the resolved `spec` an explicit parameter — the first place "interpretation" becomes a value that can be varied while data is held fixed. This is the seam F0 says does not exist. |
| **2 `valid_die_ref.js`** | 98 / **2** | 🟢 **Direct.** `basisOf(state)` and `isValidDieAt(state, …)` take the mask as a parameter, so two bases can be evaluated against one dataset — the second half of "hold one, vary the other". |
| **3 `wafer_frame.js`** | 91 / **2** | 🟢 **Direct, and the decisive one.** `waferBoundingBox(spec, rot, side, { isValid })` with an injected predicate is exactly the split between invariant and interpretation. J0 becomes expressible here. |
| 4 `company_form.js` | 62 / **1** | ⚪ Neutral |
| 5 `map_datalist.js` | 14 / 0 | 🟡 Indirect — serves R-FIND, which is J0's other cost |

Steps 1→3 are the alignment programme. Steps 4 and 5 are debt reduction that happens to be cheap.
**If the programme is stopped early, stop after step 3, not before it.**

### Step 0 — the harness unlock *(no `map_editor.js` change at all)*
Build `client2/tests/_module_probe.mjs`: one shared helper providing (a) `importModule(path)` and
(b) `importMutated(path, [{find, repl}])` via the data-URL pattern already proven in
`retroactive_view_harness.mjs`, with the uniqueness assertion that `coord_table_paste_harness`
already implements (`if (src.indexOf(find, i+1) >= 0) die(...)`) made mandatory.
Convert the four already-convertible harnesses (`overlay_provenance`, `push_gate`,
`virtual_column_render` map-portion, `contracts/band_arithmetic`) as the proof.
- **edges removed:** ~8 · **files freed: 4** · **`map_editor.js` diff: none**
- **Why first:** without it every later step's liberation count is capped near zero (§5.2).

### Step 0a — ceiling headroom *(≈20 lines, no symbol moves)*
Delete `tables`; delete `isMouseDown`; `editorFrames` `let`→`const`; encapsulate `isRenderScheduled`.
- **MODULE_STATE 48 → 44** · **edges removed: 0** · **files freed: 0**
- **Why now:** headroom 0 currently blocks every concurrent repair lane. Costs one review, touches
  no slice anchor, and is the cheapest thing in this document. It is the step to run **today**.

### Step 1 — `wafer_geometry.js` (S1)
17 symbols / 317 lines. The spec reader becomes a parameter; the pure transforms follow.
- **edges removed: 195 (27%)** · **files freed: 0** (but 20 files shed their most-churned anchors)
- **Not in this step:** the origin box, the frame window, the mask, anything touching `validDie`.

### Step 2 — `valid_die_ref.js` (S2)
14 symbols / 238 lines. State-reading functions take `validDie` as first parameter.
- **edges removed: 98 (cum. 40%)** · **files freed: 2**
- **Contract impact:** `contracts/map_seam` 14→4 slices — the contract that scores this exact domain
  against the server nearly stops slicing. This is the step that best matches the gate's intent.

### Step 3 — `wafer_frame.js` (S3) — **gated on M4's axis existing**
13 symbols / 335 lines. Origin box with injected mask predicate.
- **edges removed: 91 (cum. 53%)** · **files freed: 2**
- **Hard precondition:** the mask-placement axis from §8.2. Do not start without it.

### Step 4 — `company_form.js` (S4)
25 symbols / 464 lines. Fully self-contained; the largest line-count move with the least risk.
- **edges removed: 62 (cum. 61%)** · **files freed: 1**

### Step 5 — `map_datalist.js` (S5)
13 symbols / 234 lines. Serves **R-FIND**.
- **edges removed: 14 (cum. 63%)** · **files freed: 0**
- Low gate value; sequenced last on that basis, and it is the first step I would cut if the program
  is stopped early.

**Explicitly NOT in any step:** `renderGridCanvas`, `loadExistingMap`, `pushMapData`,
`saveMapSpecOnly`, `saveLegendToServer`, `initDOMElements`, `addOverlayLayer`, `restoreEditorState`,
`snapshotEditorState`, the legend cluster's 7 bindings. These are orchestration and stay
**permanently**, per `DOC_OWNERSHIP.md:70` and `MAP_EDITOR_SPEC.md:151`.

---

## 10. Cost while it runs — interleaving with live repairs

| Step | Safe alongside a live repair lane? | Why |
|---|---|---|
| **0** | ✅ Yes — fully parallel | Touches only `client2/tests/**`; zero `map_editor.js` diff |
| **0a** | ✅ Yes | 4 isolated bindings, none a slice anchor; conflicts resolve trivially |
| **1** | ⚠️ Needs exclusivity for one sitting | Changes the signature of `getTransformedPhysicalConfig`, which 19 harnesses name |
| **2** | ⚠️ Exclusive | Valid-die is the hottest area — 7 of the last 21 map commits |
| **3** | 🔴 Exclusive, plus M4 gate | `getWaferBoundingBox` is the origin of the coordinate system |
| **4** | ✅ Yes — fully parallel | Clipboard form touches nothing the repair lanes touch |
| **5** | ✅ Yes | Datalist cluster is isolated |

**Recommended interleave:** run 0 and 0a immediately and concurrently with whatever is live; then
S4 (parallel-safe, biggest line reduction, zero contention) to bank progress; then take exclusivity
for S1→S2; hold S3 until the M4 axis lands. This ordering deliberately **breaks the "smallest
first" rule once** — S4 is larger than S1 — because S4 costs nothing in contention and S1 costs a
lot, and the board records that merge contention, not line count, is what stalls this file.

**Complexity budget: net +0 UI controls across the entire program.** No new panel, mode or modal;
no change to any user-visible string. Read paths gain no confirmation.

---

## 11. `MAP_EDITOR_SPEC.md` as a managed artifact

The user's instruction is that the spec is managed, not trailing. Concretely:

**What it must state** (and be the sole owner of):
1. **The three coordinate spaces** and the exact conversions between them — die index, DB
   coordinates, wafer mm — with the direction of each and which is stored.
2. **The origin box contract**: what defines `box`, that `box` follows the valid-die mask when the
   basis is `ref`, and the four exceptions (frame window, `circleOnly`, template authoring,
   `refused`). This is the clause a doc currently contradicts (§3.4.1).
3. **The frame-window rule**: one transform implementation; overlay substitutes the *reading point*,
   never the formula.
4. **The declaration-vs-default distinction**: that `physNum` folds four different situations onto
   one number, that `physDeclaration` is the only spelling of "is this declared", and that
   `auto_registered` marks a synthesized geometry (measured: 320/668 rows, 47.9%).
5. **The file boundary table** (§1-bis-2), one row per module, updated in the same commit as a move.
6. **What the contract does and does not cover** — §8.2's list belongs in the spec, not only on the
   board, because the board is a work log and the spec is what a future round reads.

**What it must be checked against, mechanically:**
- The `{file, fn}` dictionary in `contracts/map_seam/vectors.json` — the spec's boundary table and
  that dictionary must not disagree; a check comparing them is ~20 lines and would have caught the
  R1 hostage undercount.
- `docs/architecture/CODE_MAP.md` anchors — measured 200–430 lines stale today, 20× tolerance.
  `code-mapper` owns this; the spec should link rather than restate.

**How a change moves the spec first:** the spec clause is the input to the round, not its output.
An editor change that alters any of the six items above states the new clause **in the instruction**,
and the round is not done until the clause and the code agree. The mechanism that makes this stick
is the same one that already works for the contract: a **named owner per clause** and a check that
fails loudly. The recurring failure mode measured today — four separate incidents where a stale
line misled a judgement — is not a discipline problem, it is an absence of a failing check.

**Not written in this round, per instruction.**

---

## 12. Proposed lessons for `agent_workspace/memory/map-pm.md`

Proposals only, for lead review — not added by me.

1. **함정**: 하네스가 함수 하나가 아니라 **호출 폐포**를 잘라 낸다. 심볼 하나를 옮기고
   「하네스가 해방됐다」고 세면 실제로는 51개 중 1개가 준 것이다.
   **올바른 방법**: 게이트는 **파일 단위(0으로 떨어졌는가)와 간선 단위(몇 개가 줄었는가)를 함께**
   보고한다. 인질은 심볼 이름이 아니라 **파일 경로**로 센다.
2. **함정**: 뮤테이션 하네스는 **수정된 소스 텍스트**를 다시 평가해야 하므로 `import`로 옮길 수
   없다 — 34개 중 24개가 여기 해당한다. 파일을 아무리 잘 쪼개도 이 벽은 안 없어진다.
   **올바른 방법**: `data:` URL 모듈 임포트 패턴(`retroactive_view_harness.mjs`에 이미 초록)을
   공용 헬퍼로 만든 뒤에 코드를 옮긴다. **하네스 변경이 0단계이고 코드 이동이 1단계다.**
3. **함정**: 「모듈 상태를 새 파일로 옮겼다」를 「상태를 줄였다」로 보고했다. 천장은 파일 하나만
   재므로 수는 내려가지만 전역 가변 상태는 그대로다.
   **올바른 방법**: 삭제·스코프 축소만 감소로 센다. **이전은 이전이라고 적는다.**
   `let x = {}` → `const x = {}`는 계량기를 속이는 것이므로 절대 쓰지 않는다.
4. **함정**: 소스 주석이 하네스의 슬라이싱 방식을 보호하려고 설계를 제약하고 있었다
   (`map_editor.js:1813` — 「별도 함수로 빼지 않는다」).
   **올바른 방법**: 그런 주석을 발견하면 그것은 **리팩토링의 근거**로 인용한다. 테스트 기제가
   설계를 지시하고 있다는 뜻이다.

---

## 13. Invariant inventory — what a rewrite must not lose

Claims with consequences. A rewrite loses these silently by default; losing them means re-earning
them the way they were earned the first time, which in several cases was a production incident.
**This list is the first harness suite of the new system, and it should be written as tests before
any new editor code exists.** Each row: the claim, the cost of violating it, and how it was
established.

### 13.1 Evidence and measurement (how you know anything is right)

| # | Claim | Cost when violated | How established |
|---|---|---|---|
| **E1** | **A wrong mask is invisible to counts.** Cell-count equality proves nothing about placement. | Four misread frames each produced exactly **854 cells** while disagreeing on **341 / 108 / 41 / 284** dies. | Measured, prior round |
| **E2** | **Set difference is not per-cell evidence either.** | A mirrored map occupies the same dies; only the values move. Scored **1 wrong where the truth was 16**. | Measured |
| **E3** | **Evidence must be key→value against an independent oracle**, and must report "how many cells move if the wrong frame is used". If that number is 0, the fixture proved nothing. | Injective/range/round-trip checks are self-comparison — a defective `f` and its inverse both pass. | `map-pm.md` lesson |
| **E4** | **Fixtures must activate the defect axis.** `chip_x == chip_y` kills pitch-swap defects; `minC == 0` kills bbox-term defects. Require anisotropic chip **and** rot 90/270 **and** `back` **and** `bbox != 0` simultaneously. | Defects become *structurally* undetectable, not merely missed. | `map-pm.md` lesson |
| **E5** | **A green harness that sheds assertions is invisible to exit codes.** | A dead harness masquerades as debt — 3 cases in one week. | Board H1; hence the `ASSERTIONS <ran> <failed>` protocol + floors |
| **E6** | **Count injected failures.** To test recovery after one failure, inject exactly one. | A round blocked both fetches, never executed the recovery branch, and declared it resolved. | `map-pm.md` lesson |
| **E7** | **A repaired mutation proves nothing.** If a later loop restores the mutated value, green means "there was no mutation". | False confidence at the exact point confidence is claimed. | `MEMORY.md` |
| **E8** | **Mutation anchors must be unique and line-anchored.** | First-match landed inside a **comment** and scored a different function — twice in one day. | Board L34 |

### 13.2 The coordinate model

| # | Claim | Cost when violated | How established |
|---|---|---|---|
| **C1** | **Stored coordinates are cell counts from the origin, not millimetres.** Pitch is irrelevant to them. | Multiplying counts by pitch invents defects that do not exist. | `MEMORY.md`; `MAP_EDITOR_SPEC` §1-bis |
| **C2** | **There is exactly one transform implementation.** Overlay substitutes the *reading point* for the spec (a frame window), never the formula. Main load is the special case "frame == current controls". | An overlay-only geometry path drifts from the main path and the screen stays plausible. | Invariant ①; `withPhysFrame` |
| **C3** | **Alignment has exactly one basis: `wafer_map_metadata`.** Cell-level `grid_metadata` is a retired scheme. Grid size is **derived** from orientation and physical spec — never back-computed from the data's coordinate range. | Back-computed dimensions make an empty column silently resize the wafer. | Invariant ②; `philosophy.md:103` |
| **C4** | **`box` follows the valid-die mask when the basis is `ref`.** The origin box is not always the circle. | The doc that denies this (`architecture_and_management.md:118`) is false against `map_editor.js:1816-1819`; believing it means mis-deriving every stored coordinate on a masked map. | Code-verified this round (§3.4.1) |
| **C5** | **Inside a frame window the mask is suspended — the window answers "circle".** | Cutting a source map with the *target's* mask stencils one map with another's: screen fine, stored coordinates wrong. | `map_editor.js:1752-1755`; `MAP_EDITOR_SPEC` §5.1 |
| **C6** | **An empty mask falls back to the circle box.** A collapsed `{0,0,0,0}` box silently moves the entire coordinate system. **Unknown is not zero.** | Whole-map coordinate shift with no visible symptom. | `map_editor.js:1762-1763` |
| **C7** | **Load and render must read the *same* box.** `c − box.minC + startX` and `dbX − startX + box.minC` are inverses only under one box — hence `loadExistingMap` finishes `resolveValidDie` **before** placing cells. | Push writes coordinates that the load did not read: the defect this domain exists for. | `map_editor.js:1765-1768` |
| **C8** | **Wafer-mm must be computed from the pre-rounding continuous value.** | Rebuilding mm from rounded indices drops sub-cell remainder: **1,789 of 1,836 cells** seated wrong. | Measured, `cd3e0f4` |
| **C9** | **mm is a unit conversion, not a third transform.** Rotation/flip/offset finish inside `getDieIndex`. | An overlay-specific geometry formula — a second spelling of C2. | `DOC_OWNERSHIP` line 87 |
| **C10** | **Rotation/side/Y-invert/START and geometry are opposite operations.** Geometry moves the cell under a held stored coordinate (rule ④); orientation holds the die and renumbers (rule ⑤). Firing rule ④ on an orientation change silently rewrites stored coordinates. | Both directions are data loss, in opposite ways. | `map_editor.js:1956-1958`, `:1976-1977` |
| **C11** | 🔴 **The observation must be stored in invariant space, not interpretation space.** Today `gridData` is keyed by die index — downstream of rotation — so cells and mask move in lockstep and alignment search yields no information. | **The tool cannot do its primary job (F0).** | Code-verified this round: `:7986`, `:3350`, `:1976` |

### 13.3 Declaration versus default

| # | Claim | Cost when violated | How established |
|---|---|---|---|
| **D1** | **A default that is a plausible physical value defeats every guard that asks "is this declared".** `physNum` ends `return v \|\| dflt`, folding *absent*, *unparsable*, *declared-zero* and *genuinely that value* onto one number. | Source meta missing `phys_chip_x` folded to the **target's** on-screen pitch: **570 of 600** cells seated wrong, while a `chipX > 0` guard passed. Only negatives were caught. | `map_editor.js:1442-1446` |
| **D2** | **"Is this declared?" has exactly one spelling** (`physDeclaration`, returning `{value, source}` — `frame`/`screen`/`unparsable`/`absent`/`auto_registered`). Guards read `source`, never the value. | Two spellings diverge on the day the screen looks fine and the values are wrong. | `map_editor.js:1502-1503` |
| **D3** | **A synthesized geometry is not a declaration.** `chip 1x1 / offset 0` means "nobody measured this", not "1 mm dies". The marker is the `auto_registered` flag, never the value `1`. | **320 of 668 rows (47.9%)** are synthetic. Reading `1` as a measurement silently swallows a real 1 mm die someday. | `architecture_and_management.md:70-77`; measured |
| **D4** | **The marker lives where the value lives** — in the frame object inside a window, in the input's `dataset` on screen — and dies the moment the operator edits the value. Both axes must carry it. | A marker that outlives its value is a lie; a one-axis marker makes the other axis's code dead and silently stale. | `map_editor.js:1479-1487` |
| **D5** | **Filling an absent physical value from the neighbouring axis produces a perfectly aligned screen with every value wrong.** | Measured 570/600. | Same as D1 |
| **D6** | **A presentation label must never occupy a data slot.** `미상` in a cell's `value` makes "no matching row" and "row exists but blank" unrecoverable downstream. | `virtual_join_executor.py:497-502`; the module documents its own irreversibility at `:435`. | Verified this round |

### 13.4 Writing, and refusing to write

| # | Claim | Cost when violated | How established |
|---|---|---|---|
| **W1** | **You may not write or delete what you cannot prove you read.** Save authority exists only when the screen derives from a server read. | One failed fetch followed by an edit **deleted an entire plan**. | Invariant ③ |
| **W2** | **`replace_map` is destructive on an incomplete set.** A truncated response (`total > rows`) or a failed read must be **demoted to failure**, never treated as the population. | The remainder is purged. | Invariant ④ |
| **W3** | **The off-canvas skip must sit *after* cell registration, not before.** | A declared cell pushed past the canvas never reaches the save payload: **480 of 1600** measured. | Measured |
| **W4** | **Compute a number once.** Save using `ceil` and display using `round` put 34 in the DB and 33 on screen. | Silent, permanent disagreement between what is stored and what was approved. | Invariant ⑥ |
| **W5** | **Identity is the stable thing; labels are free text.** `band_seq` (integer) is the identity; `stack_band` is a label. Keying on the label orphans materials on a one-character edit. | Invariant ⑤ |
| **W6** | **Truncation is not success.** A list that was cut must say so and must not be cacheable as the population. | An operator concludes a map does not exist because the list was cut at 500. | `map_editor.js:9782-9785` (correct today) |
| **W7** | **A failed read must not render as an empty result.** "I could not see" ≠ "there is none". | The operator judges an existing map absent. | `map_editor.js:9755-9758` (correct today) |
| **W8** | **`'F'` (frame/fixed-integrity) cells are refused by every edit path** — click, drag, eraser, fill-all, fill-selected, E1/E2, legend remap — and released only by ALL CLEAR or a new load. | One unguarded path is enough to corrupt the protected set. | `architecture_and_management.md:194-202` |

### 13.5 Structure and process

| # | Claim | Cost when violated | How established |
|---|---|---|---|
| **S1** | **The same question spelled twice always diverges.** Three instances in one day: valid-die clear ×3, "unsaved work?" ×2, map key ×2. | 3 wasted repair rounds; one door protected work and the other discarded it; `L1_7.5` vs `L1_007.5`. | Board L17, N35, M6 |
| **S2** | **Boundaries are drawn by purity.** Only chunks touching no module state leave; stateful orchestration stays **permanently** — that is a ruling, not a deferral. | A half-extracted orchestrator is worse than none. | `DOC_OWNERSHIP:70`; `MAP_EDITOR_SPEC:151` |
| **S3** | **Module-level mutable state is the real ceiling, not file length.** R3–R6 all stopped there, not at line count. Adding a global is always easier than extracting a pure half, so the ceiling must exist or splitting is a net loss. | The 48-binding wall; `restoreEditorState` reads and writes 21 of them. | `undeclared_identifier_harness.mjs:139-166` |
| **S4** | **A metric that can be satisfied by changing an initialiser measures the initialiser.** `let x = {}` → `const x = {}` must not count as a reduction. | The gate is walked under while the problem grows. | Same |
| **S5** | **Count hostages by file path, not symbol name.** | R1 counted 3, the actual number was 5. | `MAP_EDITOR_SPEC:152` |
| **S6** | **Reads are frictionless; writes confirm exactly once.** No new panel, mode or modal. | Standing user constraint. | `ui-simplicity-first` |
| **S7** | **UI strings stay Korean; artefacts are English.** | Standing convention. | `MEMORY.md` |

### 13.6 What `contracts/map_seam/` covers — and what it does not

**Survives a client rewrite.** It is not a test of the current implementation; it is a contract that
client and server must give the same answer, keyed by **role** with a `{file, fn, status}`
dictionary in `vectors.json`. A new client re-points the `file` field and the contract keeps scoring.
It covers 19 client symbols across map-key canonical form, circle mask, physical-spec parse,
screen shift, and the whole valid-die declaration grammar, with a `live`/`pending`/`required`
status vocabulary so a rename fails loudly rather than silently dropping an axis.

**Measured gaps — do not treat it as an acceptance oracle:**
- **The wafer-mask boundary is not pinned at all.** Perturbing `isCellInsideWaferFast` from
  `normDistSq > 1.0` to `> 1.02` left `check_contracts.mjs` **fully green** — no vector sits within
  1% of the boundary (board N24). A 2% mask perturbation left the contract green while six
  harnesses went red.
- **Mask *placement* is unscored by anything.** Re-introducing `shiftX = 1` leaves **all 23
  harnesses green**, because they assert stored coordinates are preserved and a mask shift does not
  move stored coordinates (board M4). This is the blind spot aligned exactly with C11 and F0.
- `standard_frame_origin_harness` compares its own re-typed copy with itself (board M7); the
  `start_x/y` repair harness is not in the repository at all (board M1).

**Three new axes the new suite owes**, none of which exists today: mask **placement**; mask
**boundary** (vectors within 1% of the edge); and **orientation discriminability** — given a map at
a known rotation, does the system produce an observation that distinguishes it from the other seven
orientations? That third one is the direct test of F0 and is the one that would have caught it.

---

## 14. Rebuild versus restructure — my conclusion

**I agree with the rebuild, and my reason is narrower and more checkable than "the file is long".**

The decisive question is whether the existing structure can express "hold this fixed, vary that"
with a contained change. It cannot, and the measurement says why:

- The change required by C11/F0 is to key the observation in invariant space rather than die-index
  space. That means re-keying **`gridData`** — which has **33 readers and 7 writers**, the highest
  of any binding in the file, and its readers include all three orchestrators (`loadExistingMap`
  390L, `pushMapData` 325L, `renderGridCanvas` 326L) plus all 13 `getDieIndex` call sites, the paint
  paths, F-cell protection, legend counts, clipboard, overlay import and the re-seat primitive.
- Those orchestrators are precisely the code that `DOC_OWNERSHIP:70` and `MAP_EDITOR_SPEC:151` rule
  can **never** be extracted (S2). So the change lands entirely in the part of the file that no
  decomposition step is allowed to touch.
- Therefore the decomposition in §9 — which I still believe is correct as far as it goes and which
  scores 63% of slice-edges — **cannot deliver the primary job.** Steps 1–3 build the seam; nothing
  in the plan can then push the observation through it, because the consumer is the orchestrators.

That is a structural argument, not an aesthetic one, and it is the strongest case for rebuilding.

**The honest counterweight, and it is not small.** The rewrite's entire risk is §13. Those 30+
claims were earned through production incidents, and a new implementation re-earns every one it
does not import. The asset in the current file is not its code — it is the *why* in its comments and
the incidents behind them. **So the rebuild is justified conditionally: §13 becomes an executable
suite before the new editor exists, not after.** A rebuild that starts with code is a rebuild that
re-earns D1 and W1 the way they were earned the first time.

**A third option, which I recommend as the actual first move.** Rebuild and restructure are being
posed as alternatives; the smallest thing that produces value is neither. It is to build **the
alignment view that does not exist today** — a new, read-only surface that reads the same server
data in invariant space and shows the observation against a varying interpretation. It is:
- additive, so the running editor is untouched (satisfies "side by side");
- the only deliverable that tests C11/F0 directly, which is the claim the whole rebuild rests on;
- small enough to be wrong cheaply;
- and it becomes the new editor's core if it works — the rest of the new editor is built *around* a
  working alignment surface rather than the alignment surface being retrofitted into a new editor.

If that surface cannot make an unknown orientation determinable, the rebuild's premise is wrong and
we learn it for the cost of one view instead of one editor.

**Steps 0 and 0a of §9 remain worth doing regardless of this decision** — they touch no
`map_editor.js` logic, they unblock every concurrent repair lane by restoring ceiling headroom, and
Step 0's module-probe helper is needed by the new system's harnesses too.

---

## 15. Switchover criterion — a measurement, not a feeling

The new editor replaces the old when **all four** hold. Each is a number.

**① The alignment bar (the primary job).** On a fixture set of **8 real maps** spanning
rotation {0, 90, 180, 270} × side {front, back}, every one satisfying E4 (anisotropic chip,
`bbox != 0`), with the true orientation established independently and sealed before the trial:
- the operator determines the correct orientation on **8 of 8**,
- in **≤ 4 actions** per map,
- in **≤ 30 seconds** per map,
- with **zero database writes** during the search (proved by `updated_at` invariance in SQL, per the
  standing no-live-write rule).

The current editor scores **0 of 8 at any action count** — F0 means no number of attempts converges.
That is the honest baseline and it is what makes this bar meaningful rather than arbitrary.

**② The invariant suite.** Every claim in §13 has a test; every test scores its own mutant red
(E7 — verify by re-inserting the defective version); the suite reports `ASSERTIONS <ran> <failed>`
(E5) and carries floors. **A claim without a red mutant does not count as covered.**

**③ The contract.** `contracts/map_seam/` runs green against the new client with **only `file:` field
edits** to `vectors.json` — no vector changes, no status downgrades. Plus the three new axes from
§13.6 (mask placement, mask boundary, orientation discriminability) exist and score mutants red.

**④ Job parity on the jobs that are actually used.** J1, J2, J3, J4, J6, J7, J8 demonstrated on real
maps in the isolated environment. J9/J10 unchanged (§16). J11 and J12 may lag switchover if the old
editor stays reachable for them — state that explicitly rather than letting it be assumed.

**Until all four hold, the old editor remains the default and the new one is opt-in.** No partial
switchover on the strength of ① alone: ① without ② is a tool that solves the visible problem and
re-earns W1 the expensive way.

---

## 16. What is NOT rebuilt

The rewrite is **client-side only**. Everything below stays and the new client must keep talking to
it unchanged:

| Stays | Note |
|---|---|
| `server/**` in its entirety | Including `map_overlay.py`, `map_meta_registrar.py`, `bonding_plan.py`, `transfer_plan.py` |
| The map seam contract | `contracts/map_seam/` — §13.6; re-point `file:`, change no vectors |
| `wafer_map_metadata` / `grid_metadata` schema | C3: the sole basis for alignment |
| `replace_map` push semantics | Including the three refusal gates and the `scope` response |
| `map_key_columns` as the table gate | And `map_key.js` (R1) — already extracted, already contract-scored |
| `split_registry_row.js` (R2) and the DOE storage model | §4.4 |
| `transfer_plan.js` and the planning data model | **The planning screen is in scope as a consumer, not as a rewrite target.** Its `initTransferPlan(controller)` injection interface is the target architecture and should be preserved verbatim — 1,876 lines on 5 module bindings (F3) |
| The ontology / graph side | **Not fixed by this rebuild.** F0-bis is a separate lane. The new editor must not assume the graph will start reading frames; conversely the graph must stop asserting die identity on unframed coordinates, and that is `server-pm` / `ontology-pm` work |
| `docs/spec/MAP_EDITOR_SPEC.md` | Becomes the managed specification of the **new** system (§11), written before the code |

**Explicitly out of scope for the rebuild, though they touch the editor:** the parser-setup window
(an ingestion-template designer that belongs to the ingestion pipeline), and per-table default
rotation/flip meta (table-level configuration authoring, better served by a bulk-editable grid).

---

## Appendix — provenance

Everything above is measured except where labelled inferred. Board rows are quoted as claims and
independently re-measured where they were load-bearing (`tables`/`isMouseDown` confirmed;
`MODULE_STATE 48` confirmed; APPLY-control staleness confirmed against git). Doc statements were
checked against code, and one was found false (§3.4.1). The three subagent inventories (docs,
board, harnesses) are reflected here; their raw output is not reproduced.
