# S1A - Frame as a value (MAP_ALIGNMENT_SPEC 0.3 step 1, with step 0 folded in)

> **REVISION 3 (2026-08-05).** Namespace moved to `map2/` and the start-axis ruling applied;
> see section 10. **REVISION 2 (2026-08-05, after two T1 QA lanes and a scope cut).** Four fixes applied; the
> rest of the QA findings were deferred by the lead PM and are listed in section 8 so they are
> not lost. **Section 0 of revision 1 was wrong and is corrected in section 0 below** - I was
> right about the stored types and wrong about the conclusion. The 516 is real.

Stage A only. **No existing call site was rerouted. `map_editor.js` was not modified. No build
was run, `client2/dist/` was not touched, nothing was committed.**

Files created / changed:

| path | state |
|---|---|
| `client2/src/map2/declaration.js` | NEW - the module |
| `client2/tests/frame_declaration_harness.mjs` | NEW - import-based harness, 3866 assertions |
| `client2/tests/fixtures/prod_frame_metas.json` | NEW - 66 distinct production shapes covering all 668 rows |
| `client2/scripts/check_harnesses.mjs` | MODIFIED - one `FLOORS` entry (3866) + its rationale |

Database access was read-only throughout (`SET TRANSACTION READ ONLY`, `SQLALCHEMY_DATABASE_URL`
from `database.database`; resolved source `default`, database `assy_manager`, 668 rows, which
matches the count the spec records). No write of any kind was issued.

---

## 0. PREMISES vs MEASUREMENT - INCLUDING ONE OF MY OWN THAT WAS WRONG

### P1. "516 of 668 rows sit on that ambiguity" - **the number is right; only the mechanism was wrong. I over-retracted it, and that was my error.**

Revision 1 of this report said the extension was **0** and recommended the board drop the
number. That conclusion does not follow from what I measured, and the server lane re-derived
516 independently. Both things are true at once:

- **What I measured and stand by:** every one of the 668 rows stores all 13 axes with the
  right type. So `absent` = 0 rows and `unparsable` = 0 rows. Nothing collapses for the reason
  the brief originally gave (`|| 0` eating a missing or unreadable key).
- **What I wrongly concluded:** that therefore nothing is ambiguous. The collapse is real and
  it is a different one - **a stored `0` and a defaulted `0` are the same bytes.** 516 rows
  carry `rotation: 0`, and on all 516 nobody chose it:

  ```
  rotation provenance over 668 rows (scored by the module, pinned by the harness):
      auto_registered = 320     the registrar wrote it (synthesize_grid_meta:168-196
                                writes rotation 0 / side "front" / y_invert False flatly)
      indeterminate   = 196     a generator's literal 0, no marker, nobody's choice
      declared        = 152     somebody actually turned the map
                                320 + 196 = 516
  ```

**The lesson, and it is mine to carry:** I disproved the stated *mechanism* and reported the
*number* as dead. Refuting an explanation is not refuting the fact it was offered for. The
board should keep 516 and replace its reason.

This is also why `raw`/`legacy` cannot substitute for the fifth token, which I had argued in
revision 1. It works client-side only because the DOM hands you strings, so raw `'0'` and raw
`''` are distinguishable. Server-side they are the same bytes. Measured by the server lane: 83
rows carry a numeric, typed, unmarked `"rotation": 0` written by a generator, and raw-vs-legacy
yields `(0, 0)` for all 83. `legacy` stays - it is the honest record of what the old path
produced - but it answers a different question.

### The two premises that did NOT survive (unchanged from revision 1)

### P2. "20 places re-parse it" / "6 named functions" - the 6 is right, the 20 is 15.

Blocks in `map_editor.js` that read the grid controls directly (`parseInt(el.grid*.value, 10) || N`):

```
:603 :839 :883 :1943* :3252 :5575 :5695 :6262* :6346 :6419* :7586* :8026 :8517* :8736
```

14 blocks, of which 5 (starred) are inside the named functions. Plus `currentGeomSignature:10486`,
which reads the same controls as **raw strings** and so does not match that pattern. Total **15**
blocks answering "what frame are we on"; **9** of them are raw re-reads outside any named
function. The six named functions and their line numbers in the brief are all correct.

### P3. "visual grid dimensions is answered at 11 sites, and 10 of them bypass the primitive" - the count is 12, and **6 of the 12 are not bypasses**.

```
derives visualCols/visualRows inline, from the MODULE GLOBAL currentRotation:
  :885  :2411  :3258  :5698  :6348           (5 sites - these ARE bypasses)
  :6419                                       (the primitive itself)
derives inline from an EXPLICIT rotation ARGUMENT:
  :1567 :1626 :1813 :6326 :6801 :8662         (6 sites)
calls getVisualGridDimensions():
  :6431 :6467 :6508 :6530 :6847 :7584 :7667   (7 call sites)
```

The 6 frame-parametric sites are **not** bypassing a primitive; they physically cannot call it,
because `getVisualGridDimensions:6418` reads `currentRotation` off the module. `:6801` says so
in a comment: the axis is taken from the argument on purpose. Filing them as "bypasses" would
have led stage B to reroute them into a global-reading function - the opposite of the fix.

This is why `visualDimensions(frame)` in the new module takes the frame as an argument.

---

## 1. THE MODULE - `client2/src/map2/declaration.js`

Pure ES module. **No `document`, no `window`, no `el`, no fetch, no impure import** (verified by
grep; the only line matching `config` is a comment saying it does not import config.js).
**Zero top-level `let`/`var`** - verified by grep, and the `MODULE_STATE` ceiling of 48 is
unchanged (the runner reports neither an exceedance nor a shrink).

### Exported surface

```
tokens        DECLARED  AUTO_REGISTERED  ABSENT  UNPARSABLE   (map_overlay.py:314-317, verbatim)
              INDETERMINATE                                   (map_overlay.py:420, adopted)
              DECLARATION_TOKENS  AUTO_REGISTERED_KEY  PHYS_KEYS
constants     FRAME_DEFAULTS  AXIS_META_KEY  AXIS_NAMES  ROTATIONS  SIDES
              ORIENTATION_AXES  START_AXES
functions     frameFromDeclaration(meta, opts?) -> frozen Frame
              noEvidenceValue(axis, opts?)   -> what the reader invents for a missing key
              visualDimensions(frame)        -> {visualCols, visualRows}
              visualDimensionsLegacy(frame)  -> same, from the legacy numbers
              geometryDeclaration(meta)      -> one of the four shared tokens
              axesWithSource(frame, tokens)  -> axis names
              foldedAxes(frame)              -> axes where `value !== legacy`
              isFrameUsable(frame)           -> {ok, reasons[]}   (reasons are TOKENS)
              frameDimBounds()               -> {min:1, max:100}
```

### The Frame record

Designed from the **union of what the 6 named functions read**, not from what looked tidy.

```
frame.<axis>          the DECLARED value for all 13 axes - NOT a drop-in for the 6 (see below)
frame.axes.<axis>     { name, raw, value, source, legacy }
frame.legacy.<axis>   what the SHIPPED code answers today, + visualCols/visualRows
frame.visualCols/Rows derived from the frame argument, never a global
frame.autoRegistered  the marker
frame.noEvidence      the invented-value table this frame was scored against
frame.geometry        whole-meta verdict, a port of server geometry_declaration:333
frame.present         whether a meta was supplied at all
```

**FIX 2 - `frame.<axis>` is not a drop-in for what the six return, and revision 1's comment
said it was.** `frame.<axis>` is the declared value; the six return the value *after* the
`|| dflt` fold. The drop-in is `frame.legacy.*`, which is the only thing parity is scored
against. On a meta declaring `grid_cols: 0`, `frame.cols` is 0 and `frame.legacy.cols` is 10.

That comment was not cosmetic. QA showed that replacing `flat[name] = axes[name].value` with
`.legacy` - one word - deleted the entire reason the module exists and still scored
**3438 assertions, 0 failures**, because stage B's plan is to read `frame.<axis>` while every
parity assertion is deliberately scored against `legacy`. Section E of the harness now pins
the two surfaces apart. **It could not be pinned on production**: 0 of 668 rows fold a declared
value, so `value === legacy` on every axis of every production row and asserting their identity
there would be 858 assertions that cannot fail. The pin is built on the six axes whose
substitute is non-zero (`cols`, `rows`, `waferDia`, `chipX`, `chipY`, `edgeMargin`); the five
whose substitute is 0 cannot diverge and are deliberately excluded.

### Vocabulary - copied, not invented

The first four are byte-identical to `server/map_overlay.py:314-317` (`GEOMETRY_DECLARED` /
`GEOMETRY_AUTO_REGISTERED` / `GEOMETRY_ABSENT` / `GEOMETRY_UNPARSABLE`) - the server lane
confirms that block is untouched, so the seam still holds. `geometryDeclaration()` is a
straight port of `geometry_declaration:333-355` including the **marker-before-values**
ordering, which the server's docstring flags as load-bearing.

**FIX 1 - the fifth token, `indeterminate`.** Revision 1 argued that `raw`/`legacy` made a
fifth token unnecessary. That is wrong for the reason in section 0, and in any case one
already existed on the other side of the seam (`map_overlay.py:420
ORIENTATION_INDETERMINATE`), so adopting it is copying rather than inventing. Two vocabularies
for one question is precisely the defect class this module exists to close.

The harness pins the four and the fifth as **separate** facts, so a change to the shared four
fails differently from a change to the fifth.

### The tainting rule, implemented rather than transcribed

One sentence, from the server lane:

> A stored value equal to what the reader invents when the key is missing is not evidence that
> anyone chose it.

Applied to a present, readable value: not equal to the invented value -> `declared`; equal and
marked -> `auto_registered`; equal and unmarked -> `indeterminate`.

**The invented value is not written down twice.** `noEvidenceValue(axis)` asks this module's own
reader what it produces for an absent key, and the tainting pass uses that. A hardcoded second
table would diverge from the defaults the first time anyone moved one - the same two-spellings
defect, one layer down. `frame.noEvidence` exposes the table actually used. Mutant M14 restates
the table instead of reading it back and is caught.

**One place the uniform rule is not enough, and I am flagging it as a deliberate departure from
the one-sentence version.** The marker means "the registrar wrote this", so it can only explain
values the registrar was *able* to write. `synthesize_grid_meta:168-196` writes
rotation/side/y_invert as unconditional constants but writes `grid_start_x/y` as the **observed
minimum coordinate** - any integer. Applying the uniform rule literally would call a marked
map's `start_x: 37` a *declaration*, promoting the registrar's bbox scan to a human choice on
320 production rows. The server's own implementation guards against exactly this and its
comment says so. So the rule is implemented as "the marker explains any value the registrar
could have written", with rotation/side/invertY constrained to the constants and everything
else unconstrained. Mutants M12 and M13 test both directions of that boundary.

### The seam disagrees about `grid_start_x/y` and this module cannot settle it

The rule says "what the **reader** invents", and the two readers invent different numbers:
every client path defaults an absent start to **0** (`frameFromMeta:8462` and all 9 raw
re-reads, `parseInt(...) || 0`); `map_overlay._grid_of:249` defaults it to **1**. Same row,
opposite verdicts. Over production that inverts the answer on **660 of 668 rows** (403 stored
at 0, 257 at 1).

This module implements **its own** reader's invention - transcribing the other side's table is
what the rule forbids - and exposes `opts.defaults` so the seam can be settled deliberately.
Both conventions are asserted in the harness. **It is not settled, and someone must settle it
before step 6 (consume).**

One deliberate NON-adoption, reported rather than silently reconciled: `physDeclaration:1509`
also emits `'frame'` and `'screen'`. Those are not declaration states, they are **read
locations** - "which of the two places I looked answered". A pure module has one input and no
DOM, so those tokens have no meaning here and are absent. If stage B wants them, they belong on
the assembly layer's read, not on the axis record.

---

## 2. DIVERGENCE FOUND AMONG THE SIX (findings about the OLD code)

These are recorded in the module header as D1-D6.

**D1. Two different dimension readers.** `seatingSnapshot:1937-1938` reads dimensions through
`gridDimNum` (frame-window aware); `readGridFrameControls:6262`, `getVisualGridDimensions:6419`,
`currentCoordFrame:7586` and `currentFrame:8517` read `parseInt(el.gridCols.value, 10) || 10`
directly. Inside a `withPhysFrame` window the first answers with the **source map's**
dimensions and the other four with the **screen's**. Not live today only because
`seatingSnapshot:1935` bails (`if (physFrameOverride) return null`) - i.e. the divergence is
held off by a guard, not by design.

**D2. `readGridFrameControls` carries no rotation and no side**, although its own header at
:6257 calls itself the single reading of the grid frame controls. Its caller
`buildPushGridMetadata:6269` takes `currentRotation`/`currentSide` as separate arguments. The
"single reading" covers 5 of 7 grid axes.

**D3. Three spellings of one null guard** on `grid_y_invert`:

```
readGridFrameControls:6266   el.gridYInvert.checked                     <- THROWS if absent
currentCoordFrame:7590       el.gridYInvert ? el.gridYInvert.checked : false
currentFrame:8521            !!(el.gridYInvert && el.gridYInvert.checked)
```

**D4. The start default disagrees across the seam.** Client (`frameFromMeta:8462` and every raw
re-read) defaults an absent `grid_start_x/y` to **0**; server `map_overlay._grid_of:249` defaults
it to **1**. On a meta with no start declared the two sides are **one cell apart**. Neither
default is right in isolation, which is why `startX`/`startY` carry a source token: `absent` is
the state a consumer must be able to refuse. The module takes the client convention by default
and accepts `{ defaults: { startX: 1 } }` to take the server's - both are asserted.

**D5. `currentGeomSignature:10486` compares raw strings.** It cannot under-trigger, but it
over-triggers on `"10"` vs `"10.0"`, and it omits both the auto-registered marker and
`validDieResolveSeq` - **both of which ARE in `getWaferBoundingBox`'s cache key (:1832)**. So
changing the valid-die reference moves the bounding box without moving the overlay geometry
signature. Out of scope for stage A; flagged for the board.

**D6.** covered as P3 above.

---

## 3. A3 - THE PROOF

### 3a. Parity against the REAL shipped functions (one-off, scratchpad)

`scratchpad/parity_oracle.mjs` slices the six named functions plus `frameFromMeta`,
`resolveFrame`, `physNum`, `gridDimNum`, `withPhysFrame`, `geometryIsAutoRegistered`,
`physDeclaration` out of `map_editor.js`, runs them in a `node:vm` with a DOM stub filled from
each production meta, and compares field by field with the module.

```
shapes 66   rows 668   field comparisons 3366
IDENTICAL rows 668     DIVERGENT rows 0
no divergence on any field
```

**Every production row produces identical values on every field every old function actually
computes.** Zero divergence. That is the migration-safety result stage B needs.

### 3b. Parity inside the gated harness (permanent)

`client2/tests/frame_declaration_harness.mjs` re-runs the same comparison against
**transcriptions** of the six (transcribed, not imported, not derived from the module under
test - the discipline `offset_pitch_guard_harness` already uses for the server's phys table).
Transcription fidelity is exactly what 3a proves, and 3a is the reason the transcriptions can
be trusted.

```
A. parity: 66 shapes / 668 production rows; identical on every field: 668; divergent: 0
B. production rows with a folded declared value: 0 of 668
B. production rows with any absent/unparsable axis: 0 of 668
B. auto_registered rows: 320 of 668
B. rotation provenance over 668 rows: auto_registered=320 declared=152 indeterminate=196
PASS baseline: 3866 assertions, 0 failure(s)
ASSERTIONS 3866 0
```

The rotation line is the 516, reproduced by the module and pinned by the harness as four
separate assertions (320 / 196 / their sum / the 152 that really were declared).

### 3c. Fixture axis liveness (a green on a dead axis proves nothing)

Measured in production ROWS over the 66 shapes:

```
chipX != chipY .......... 36 rows / 25 shapes   (a pitch swap cannot pass)
rotation 90 or 270 ...... 52 rows / 13 shapes   (a dropped quarter-turn cannot pass)
rotation 180 ............ 100 rows /  2 shapes
side back ...............  55 rows / 11 shapes
grid_y_invert true ......   2 rows /  2 shapes
startX != 0 ............. 265 rows / 44 shapes  (a start-default change cannot pass)
startX != startY ........  52 rows / 16 shapes  (an axis swap on start cannot pass)
cols != rows ............  94 rows / 35 shapes
offsetX != 0 ............  14 rows / 12 shapes
offsetX != offsetY ......   5 rows /  4 shapes
auto_registered ......... 320 rows / 22 shapes  (the marker cannot be dropped unnoticed)
```

Every axis is live. `absent` and `unparsable` are the two that production **cannot** exercise
(extension 0, section 0), so they are covered by 16 clearly-labelled SYNTHETIC fixtures which
are never counted as evidence about production.

### 3d. Mutation - and one fake catch that I found and closed

Mutants are applied to the module's source **in memory** and imported as `data:` URIs. Nothing
is written to disk, so there is no CRLF and no stale-artefact hazard.

```
CAUGHT   M1  visual dims never swap on a quarter turn       32 failures, first: prod[sample_map] getVisualGridDimensions.visualCols: got 29 want 25
CAUGHT   M2  side falls back to back                         5 failures
CAUGHT   M3  declared zero is not folded                     9 failures
CAUGHT   M4  rotation legacy ignores the declared value     88 failures, first: prod[eds_fail_map] seatingSnapshot.rotation: got 0 want 180
CAUGHT   M5  chipX and chipY swapped                        36 failures, first: prod[bonding_map] seatingSnapshot.chipX: got 13 want 11
CAUGHT   M6  the auto_registered marker is ignored          29 failures, first: rot_marked_zero rotation.source: got "indeterminate" want "auto_registered"
CAUGHT   M7  absent and unparsable collapse to one token     1 failure
CAUGHT   M8  startX default becomes the server convention  170 failures, first: prod[core_wafer_map] seatingSnapshot.startX: got 1 want 0
CAUGHT   M9  the frame is not frozen                         1 failure
CAUGHT   M10 flat surface sourced from legacy not value     15 failures, first: E. cols: the flat surface carries the DECLARED zero: got 10 want 0
CAUGHT   M11 indeterminate collapses back into declared      9 failures, first: rot_stored_zero_unmarked rotation.source: got "declared" want "indeterminate"
CAUGHT   M12 marker explains a rotation registrar never writes  2 failures, first: rot_marked_ninety: got "auto_registered" want "declared"
CAUGHT   M13 marker explains only constants, so a scanned start becomes a declaration  1 failure, first: startx_marked_37: got "declared" want "auto_registered"
CAUGHT   M14 no-evidence table restated instead of read back  2 failures
SURVIVED CONTROL a comment change must NOT be caught
15/15 scored as intended.
```

**M10 is the QA finding, and it is the one that mattered.** Before section E existed it
survived at 3438/0.

**Two stale anchors were caught by the guard during this revision, which is the guard doing its
job.** M6's anchor pointed at the marker block that fix 1 replaced, and the CONTROL's pointed
at a comment heading that fix 1 renamed. Both stopped the run with `HARNESS FAILURE: mutant
"..." could not be applied. An unapplied mutant is not a caught mutant.` (exit 2) rather than
being scored as kills. That guard was itself added in revision 1 after I found the same class
of fake catch, and it has now paid for itself twice.

Every mutant that touches an axis is killed by **production** rows, not only by synthetics -
M1/M4/M5/M8 name a real production table in their first failure.

### 3e. Runner integration

`FLOORS` entry `['frame_declaration_harness.mjs', 3866]` added to
`client2/scripts/check_harnesses.mjs` with its rationale. Full run:

```
frame_declaration_harness.mjs  (ran 3866, failed 0)
36 harnesses - 32 gated, 4 on the known-red debt list (4 still red, 0 recovered).
every gated harness is green.
```

The harness needs no `node_modules` (it imports only a relative source path and reads one JSON
fixture), so it does not enter the UNAVAILABLE third state in a worktree.

**Pre-existing, not mine, worth the board's attention:** the runner reports
`enrichment_queue_partition_harness.mjs` as having no recorded floor.

---

## 4. A4 - HARNESS CONVERSION CENSUS (stage B's work order)

Baseline, re-measured on this tree (42 `.mjs` across `client2/tests/` 35 + `contracts/` 6, plus
my new one = 36 in `client2/tests/`): **28 read a `.js` source with `readFileSync`, 37 use
`node:vm`, 33 slice `map_editor.js`, 2 import a `src/` module.** The brief's "41 of 41 slice as
text; 0 import" is directionally right but two harnesses already import:
`effort_instrument_harness.mjs:21` imports `map_key.js` (while also slicing), and now mine.

**15 harnesses slice at least one frame symbol.** For each: total symbols in its slice roster,
and the frame symbols within it.

| harness | sliced total | frame symbols sliced | pure ones | converts by `import`? |
|---|---|---|---|---|
| `geometry_origin_reseat_harness.mjs` | 47 | 12 | 4 | PARTIAL |
| `offset_pitch_guard_harness.mjs` | 49 | 12 | 4 | PARTIAL |
| `valid_die_frame_adoption_harness.mjs` | 86 | 12 | 4 | PARTIAL (KNOWN_RED, 228/41) |
| `overlay_wafer_mm_harness.mjs` | 30 | 11 | 4 | PARTIAL |
| `isotropic_cell_harness.mjs` | 37 | 7 | 1 | PARTIAL |
| `standard_frame_origin_harness.mjs` | 55 | 7 | 1 | PARTIAL |
| `startxy_probe.mjs` | 41 | 7 | 1 | PARTIAL |
| `valid_die_origin_alignment_harness.mjs` | 80 | 7 | 1 | PARTIAL |
| `marker_shape_wafer_anchor_harness.mjs` | 30 | 6 | 0 | NO - blocked |
| `map_spec_only_save_harness.mjs` | 19 | 4 | 0 | NO - blocked |
| `valid_die_dirty_guard_harness.mjs` | 31 | 4 | 0 | NO - blocked |
| `company_roundtrip_harness.mjs` | 41 | 3 | 0 | NO - blocked |
| `copy_header_count_harness.mjs` | 40 | 3 | 0 | NO - blocked |
| `coord_table_paste_harness.mjs` | 44 | 3 | 0 | NO - blocked |
| `valid_die_head_parity_oracle.mjs` | 11 | 3 | 0 | NO - blocked |
| `reposition_regime_probe.mjs` | - | 6 | 1 | DEAD (KNOWN_RED, ran 0) |

### The blocker, and it is structural

**0 of 15 can convert to pure `import`, and the reason is not roster size - it is that the
frame symbols harnesses slice are precisely the DOM-reading ones.**

Split the 16 frame symbols:

```
PURE (meta in, value out) - CAN move into declaration.js:
  frameFromMeta  frameDimError  frameDimBounds  frameAxesKey          (4)

DOM-READING (read `el` and/or the module globals currentRotation/currentSide/physFrameOverride)
- CANNOT move into a pure module; they can only become thin adapters that call it:
  seatingSnapshot  readGridFrameControls  getVisualGridDimensions  currentCoordFrame
  currentFrame  currentGeomSignature  resolveFrame  physNum  gridDimNum
  physDeclaration  geometryIsAutoRegistered  withPhysFrame           (12)
```

Every one of the 15 slices between 3 and 8 **DOM-reading** symbols. And a hybrid - `import` the
frame symbols and inject them into the vm sandbox alongside the sliced rest - **does not work
for those 12**, because an imported function closes over its own module scope and would never
see the sandbox's `el` / `physFrameOverride`. That is not a style objection, it is a scoping
fact, and it is the single most important thing stage B needs to know before planning.

### Consequence for the board's acceptance bar

"How many harnesses stop slicing text" is the right bar but it **cannot be met by extracting
the frame alone**. Realistically:

1. `declaration.js` (done, stage A) plus rerouting the 4 pure symbols removes 4 slices from
   each of `geometry_origin_reseat`, `offset_pitch_guard`, `valid_die_frame_adoption`,
   `overlay_wafer_mm`, and 1 each from `isotropic_cell`, `standard_frame_origin`,
   `startxy_probe`, `valid_die_origin_alignment`. That is **20 slices removed across 8
   harnesses, and 0 harnesses fully converted.**
2. Full conversion needs the DOM readers to become adapters thin enough that a harness can
   stub the DOM and import them - i.e. it needs the ASSEMBLY layer to exist. That is the
   `MAP_ALIGNMENT_SPEC` 0.2 "assembly" box, and it is not scheduled anywhere in 0.3.
3. One text-anchor case is immune to all of this: `coord_table_paste_harness.mjs:646` asserts
   on the **presence of the substring** `'currentCoordFrame('` in the source. Renaming or
   moving that function breaks it whether or not anything is importable. There may be more of
   this class; I only searched for the 16 frame symbols.

Recommendation: schedule step 0 as **its own step with the assembly layer inside it**, or
restate the acceptance bar as "slices removed", which is measurable now and honest.

---

## 5. UI COMPLEXITY BUDGET

**Net added controls: 0. Net removed: 0.** Stage A adds no panel, no mode, no modal, no toast,
no string a user can see. No file under `client2/dist/` was touched and no build was run, so
nothing reached a browser. Read paths are untouched, so no confirmation was introduced into a
read flow.

---

## 6. LIVING DOCUMENTS TO UPDATE (doc-keeper's call, not mine - I changed nothing under `docs/`)

Per `docs/process/DOC_OWNERSHIP.md`, looked up by the code paths I touched:

- `docs/spec/MAP_EDITOR_SPEC.md` - a new section for the declaration layer, and section 5
  (overlay alignment contract) should point at `frame.axes.<axis>.source` as the thing a
  refusal reads. **Nothing in section 5 is wrong today**; this is an addition.
- `docs/architecture/PRIMITIVES.md` - new entry: "what frame is this map declaring, with
  provenance" -> `client2/src/map2/declaration.js`. It should say out loud that the token
  vocabulary is shared with `server/map_overlay.py` so a third spelling is not started.
- `docs/spec/MAP_ALIGNMENT_SPEC.md` - three corrections, all in section 0:
  (a) the 516-row claim (section 0 of this report);
  (b) section 0.3 step 0's framing - the harness conversion cannot be folded into step 1,
      measurement in section 4;
  (c) the incidental "`client2/src/map_key.js` 231 lines" in the 0.2 table: the file is
      **158 lines**, and 3 of its top-level symbols are not exported, so the brief's
      "every symbol in it is exported" is also slightly off.
- `docs/architecture/CODE_MAP.md` - new module + its exported surface. NOTE: this file was
  being modified by another agent while I worked; coordinate before editing.

---

## 7. PROPOSED LESSONS for `agent_workspace/memory/map-pm.md` (proposal only)

1. **An unapplied mutant scores as a kill if you let a throw mean "caught".** Anchor-not-found
   and code-under-test-threw are different events and must be counted differently. Measured
   here: a 10/10 mutation score in which one mutant had never been introduced. Sibling of the
   existing "a repaired mutation proves nothing" lesson, from the other end.
2. **Before claiming a code-level ambiguity is a data-level problem, feed the predicate to
   production and count the extension.** `_rotation_of` collapses three states into one; the
   number of `wafer_map_metadata` rows actually sitting on that collapse is **0**, not 516.
   Same shape as the existing "class name is not the predicate's extension" lesson.
3. **"Bypasses the primitive" and "takes the value as an argument" are opposite findings.**
   6 of the 12 inline visual-dimension derivations pass rotation explicitly - the correct
   pattern. Counting them as bypasses would have led stage B to reroute them into a
   global-reading function.
4. **A pure module cannot absorb a DOM reader, so "extract it" does not free the harness that
   slices it.** Split the symbol list into pure / DOM-reading before promising a harness
   conversion count. Measured: 12 of 16 frame symbols read the DOM; 0 of 15 harnesses convert.

---

## 8. DEFERRED BY THE LEAD PM (revision 2) - real findings, none of them fixed here

The scope cut named four fixes and explicitly deferred the rest. Recording them so they are not
lost, with what each would cost.

| # | finding | source | why it was deferred |
|---|---|---|---|
| 1 | **Ten independent mutants survive at green**: `isFrameUsable` always refusing; `visualCols/Rows` undefined; `axis.raw` undefined; `axis.name` undefined; `present` always false; `axesWithSource` always empty; `autoRegistered` always false; the rotation-domain refusal deleted; the side-unparsable refusal deleted | QA lane | none of them changes what ships while the module has zero call sites; stage B will show which are reachable |
| 2 | Of the axis record's 5 fields, `name` and `raw` have **0** assertions; `isFrameUsable` has **1** and nothing constrains `axesWithSource`'s output - and stage B's refusal path reads `isFrameUsable().reasons` | QA lane | same; but this one is the most likely to bite stage B, and should be first back on |
| 3 | **The fixture is unconstrained.** QA substituted 66 degenerate shapes (all rotation 0, side front, square, `chipX == chipY`, start 0) summing to 668 with 320 marked and got exit 0, identical assertion count, and byte-identical evidence lines. The liveness census is prose; only `marked === 320` was pinned | QA lane | *partly closed as a side effect*: revision 2 pins `rotation` provenance at 320 / 196 / 516 / 152, so an all-rotation-0 fixture now fails. The other nine liveness axes are still prose |
| 4 | **The parity run against the real sliced functions is not in the tree** (`scratchpad/parity_oracle.mjs`), so the gated 668/668 is against transcriptions whose own fidelity cannot be asserted | QA lane | landing it as a companion harness was deferred; see the caveat below |
| 5 | A mutant that runs **fewer** assertions than the baseline only warns; it does not fail | QA lane | deferred |
| 6 | `enrichment_queue_partition_harness.mjs` has no recorded floor | the runner itself | pre-existing, not this round's |

🔴 **Caveat the board should carry on #4.** Section 3a's "668 rows / 3366 field comparisons, 0
divergences against the REAL sliced functions" **was really run** and its result is real, but
the script is in a scratchpad and not reproducible from the tree. What the *gate* proves is
parity against transcriptions. The harness header says so at its own `:28-30`. Anyone quoting
the 668/668 upward should quote it as "measured once on 2026-08-05, not continuously gated".

---

## 9. WHAT REVISION 2 CHANGED (the four fixes)

1. **The fifth token and the tainting rule** - `INDETERMINATE` adopted from
   `map_overlay.py:420`; the rule implemented via `noEvidenceValue()` reading the module's own
   defaults rather than a restated table; the start-axis exception preserved with its reason;
   the seam disagreement about start reported and both conventions asserted. Anchor corrected
   to `map_overlay.py:314-317`. Four new mutants (M11-M14) score it.
2. **`declaration.js`'s "drop-in" comment** corrected, plus harness section E, which pins the
   value surface apart from the legacy surface on the six axes where they can differ. Mutant
   M10 (the QA finding) now dies.
3. **The 516** - reason replaced, number kept, and now *derived by the module and pinned by the
   harness* rather than quoted. Report section 0 carries my own over-retraction.
4. **Census numbers deleted** from `declaration.js`, `frame_declaration_harness.mjs` and
   `check_harnesses.mjs` (including the wrong `3416`). No count replaced them; the deletion is
   the fix. Counts live here, dated.

Plus one comment-accuracy fix in the same class, not on the list: `declaration.js`'s
MODULE_STATE claim was **vacuously true** - `CEILINGS` scopes that check to `map_editor.js` and
never looks at this file. The comment now says the discipline is deliberate rather than
enforced.

**Gate re-run once after all fixes: `36 harnesses - 32 gated`, `every gated harness is green`,
exit 0, `frame_declaration_harness.mjs (ran 3844, failed 0)`. Mutation set 15/15.**

---

## 10. REVISION 3 - namespace move and the start-axis ruling

### 10a. Moved to `client2/src/map2/`

`declaration.js` now lives at `client2/src/map2/declaration.js`, alongside the parallel lane's
`candidates.js` / `seating.js` / `session.js` / `painter.js` / `verdict_bridge.js` /
`verdict_placeholder.js` / `view_model.js`. `client2/src/map/` is gone.

The harness stays at `client2/tests/frame_declaration_harness.mjs` - it has to, because
`check_harnesses.mjs` scans `client2/tests/*.mjs` non-recursively and a harness in a
subdirectory would be silently undiscovered, which is the failure mode that runner exists to
prevent. What moved with the module is everything that points at it: the harness's `import`,
its `MODULE_PATH` (used only by `--mutate`), its header, and the `check_harnesses.mjs` comment.
Verified no stale `src/map/` reference remains anywhere under `client2/`.

### 10b. The ruling: start's VALUE never indicates provenance; only the marker does

Applied. The value test now runs on exactly the three axes where
`synthesize_grid_meta:168-196` writes a known constant, and the module says so by name:

```js
export const VALUE_CAN_INDICATE_PROVENANCE = Object.freeze(['rotation', 'side', 'invertY']);
```

Everywhere else - start, dimensions, pitch, diameter - the marker is the only witness:
marked -> `auto_registered`, unmarked -> `declared`, whatever the value.

**What changed in behaviour:** an unmarked start whose stored value happened to equal the
reader's invented default used to come back `indeterminate`; it is now `declared`. Nothing else
moved - production rotation provenance is unchanged at `auto_registered=320 declared=152
indeterminate=196`.

**The payoff, asserted rather than asserted-about.** The client/server default disagreement
(0 vs 1) no longer touches provenance at all. B3 scores this directly: for stored starts of
0, 1 and 37, marked and unmarked, `defaults: {startX: 0}` and `defaults: {startX: 1}` must
produce the **same** token. The 660-row inversion is gone. `opts.defaults` stays, because the
disagreement still governs coordinate arithmetic, and it stays boarded.

I had this half-right and half-wrong in revision 2, in the same file: I refused to promote a
marked `start_x: 37` to `declared` (right, and for the right reason - the registrar writes a
measurement) while simultaneously letting an unmarked `start_x: 0` fall to `indeterminate`
(wrong, same premise, opposite direction). The ruling is the general form of the half I got
right. The module's comment now carries both halves so the next person does not re-derive only
one of them.

### 10c. Mutation - three anchors moved, and the guard caught all three

Repointed with the ruling: **M6** (marker ignored on measurement axes), **M11**
(`indeterminate` collapses into `declared`), **M12** (marker explains a rotation the registrar
never writes). **M13 was rewritten into the ruling-regression mutant** - it puts `startX/startY`
back under the value test, i.e. restores exactly the pre-ruling shape, and dies with 11
failures.

```
15/15 scored as intended (14 caught, CONTROL survived).
```

One note for deferred item #5: **M13 is the first mutant to trip the assertion-count warning**
(`ran 3862 of 3866`). It is legitimate here - widening `VALUE_CAN_INDICATE_PROVENANCE` shortens
a loop that iterates over the complement, so the count drop is a *consequence* of the mutation,
not a crash, and M13 is caught by real assertion failures first. If item #5 is implemented as a
hard failure, this mutant needs a stable-count loop or an exemption, or it will fail for the
wrong reason.

### 10d. Result

```
baseline                     ASSERTIONS 3866 0
mutation                     15/15 scored as intended
FLOORS entry                 ['frame_declaration_harness.mjs', 3866]
```
