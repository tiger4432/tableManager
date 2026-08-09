# R2 - Client lens: how the layer table lands as code

> Round 2, design lens 5-of-5 (client). Analysis only. No code changed, no build run, no commit.
> Every number below is measured today against the working tree at `client2/`. Method is given
> next to each count so a later reader can re-run it rather than trust it.

---

## 0. Baseline reconciliation (three numbers in the brief, re-measured)

| brief said | measured | method | note |
|---|---|---|---|
| `map_editor.js` 10,814 lines | **10,866** | `awk 'END{print NR}'` | 52 lines of drift; file mtime 2026-08-04 22:21, after the brief was written |
| 252 functions | **252** = 248 + 4 | `grep -cE "^(async )?function "` = 248; `grep -cE "^const \w+ = (async )?\("` = 4 | reconciles exactly |
| 48 module-level `let`/`var` | **48** | `grep -cE "^(let\|var) "` | exact, and all 48 are at column 0 |
| `map_editor.js` exports | **0** | `grep -c "^export"` | this is the root of Q3 |

Two further facts that carry most of this report:

- **Only 70 of 248 top-level functions read the `el` DOM cache** (28%). Method:
  `awk` walk marking each column-0 `function` and flagging the first `el.` inside it.
- **The canvas surface is 2 functions.** `renderGridCanvas` (`map_editor.js:3249`, canvas
  calls concentrated in 3291-3550) and `paintOverlayDot` (`map_editor.js:8344`, 8346-8357).
  That is roughly **272 of 10,866 lines, 2.5%**. `document.` appears 143 times but almost
  none of it is drawing.

The file is not a canvas file with logic in it. It is a logic file with a canvas in it.

---

## Q1. How the layers become modules

### 1.1 First, four refutations of the layer table

I was asked to disagree with evidence. Four of the seven rows are wrong as **module**
boundaries. Two of the four are wrong in ways that would cost a rewrite later.

**R1. Layer 3 (index) is not layer 3. It is layer 0, and it already exists.**
`client2/src/map_key.js` is 231 lines, 5 exports, and measures **0** on
`grep -cE "document\.|window\.|fetch\(|localStorage"`. It imports nothing. It is imported by
`map_editor.js:44`, by `client2/tests/effort_instrument_harness.mjs:21`, and pinned by
`contracts/map_seam/vectors.json`. Numbering it 3 asserts that 4 depends on 3 depends on 2
depends on 1. That is false in both directions: layer 1 cannot fetch a declaration without
composing the map key first, and layer 5 (`transfer_plan.js`) consumes `canonicalKeyValue`
directly through the injected controller without touching 1, 2 or 4. The dependency shape is
a **DAG with identity at the root**, not a stack. Renumber it 0 or the module graph will be
drawn wrong on the first day.

**R2. Layer 4 as stated ("the transform BETWEEN two maps") does not exist in the code, should
not be built, and the coordinator's N-ary correction is what kills it.**
There is no map-to-map transform anywhere in `map_editor.js`. What exists is a **unary**
transform per map (`getDieIndex(colVisual, rowVisual, cols, rows, rotation, side)` at
`map_editor.js:1566`) and an overlay path that converts a foreign map into the same space
independently (`addOverlayForSource` at 10836, `drawOverlayMarkers` at 8369). With N defect
sources, a binary `correspondence` module is N(N-1)/2 edges that must stay mutually
consistent; N unary frames into one shared space is N edges and consistency is free.
**Split layer 4 into two modules**: `frame.js` (unary, map -> canonical space) and
`compare.js` (n-ary set algebra over frame images). This is the one boundary the N-ary
correction actually moves, and it is cheap to get right now and expensive later.

**R3. Layer 5 is not a canvas layer.** `transfer_plan.js` measures **0** on
`grep -cE "getContext|canvas"`. It is 32 `getElementById`/`querySelector` calls and no
drawing. Marking it "canvas: yes" in the table would justify handing the plan surface a
drawing dependency it has never had. Only layer 7 is canvas.

**R4. Layer 6 (join) should not become a client module at all.** There is essentially no
client code for it; per `MAP_ALIGNMENT_SPEC.md` §5 the ontology consumes an enrichment
confirmation that the enrichment screen (`client2/src/enrichment.js`, 38 KB) already writes.
Creating `map/join.js` would be inventing a client file for a server concern. Layer 6 is a
**consumer of layer 2's output record**, not a module.

### 1.2 The module table

Everything below lives under a new `client2/src/map/` directory except where noted. The
`FORBIDDEN` column is the load-bearing one and section 1.4 makes it mechanical.

| # | module | owns | imports | FORBIDDEN to import |
|---|---|---|---|---|
| **M0** | `map/identity.js` (today's `src/map_key.js`, moved unchanged) | `canonicalKeyValue`, `composeMapId`, `decomposeMapKey`, `canonicalMapKey`, `getMapIdFromMeta` | **nothing** | everything. Zero imports is its contract and its only defence |
| **M1** | `map/declaration.js` (layer 1) | parse `grid_metadata` into a `Declaration` record with **provenance per field** (declared / defaulted / unreadable) - the three-way `_rotation_of` collapses today (spec §9 ⓒ) | M0 | `dom.js`, `config.js`, `fetch`, `map/transport.js`, canvas, plan |
| **M2** | `map/frame.js` (layer 4a, unary) | `Declaration -> Frame`; `getDieIndex`, `getDbCoords`, `getCanvasCellFromDb`, cell/visual/physical round trips, **`waferBoundingBox(frame, physSpec, mask)`** | M1 | `dom.js`, `config.js`, transport, canvas, overlay, plan, M4-M6 |
| **M3** | `map/seat.js` (spec §6 (1), the pure judging layer) | given cells + `Frame` + physSpec: which die exists, which cell each stored coordinate seats in, what is out of grid. **Registration, never drawing** | M2 | `dom.js`, `config.js`, transport, canvas |
| **M4** | `map/candidates.js` (layer 2a) | enumerate the 8 grid transforms, solve the integer shift per candidate, fold to canonical spelling **for scoring only** (spec §2.1 (3)) | M2, M3 | `dom.js`, `config.js`, transport, canvas, plan |
| **M5** | `map/compare.js` (layer 4b, **N-ARY**) | set algebra over **N** seatings in one space: discriminating subset, footprint difference, value agreement, margin-to-runner-up, and the **refusal** verdict (spec §3 rules 2 and 5) | M3 | `dom.js`, `config.js`, transport, canvas, M2 internals |
| **M6** | `map/decision.js` (layer 2b + the layer 6 handoff) | `candidates x reference -> ranked \| refused`; produces the **record that gets written** through enrichment | M0, M4, M5 | `dom.js`, `config.js`, transport, canvas, plan |
| **T** | `map/transport.js` | every map REST call (`fetchMapKeySpec` 4741, `fetchMapKeyColumns` 4762, `probeMapExists` 4767, `loadExistingMap` 4853, `pushMapData` 5807). **The only `fetch` under `map/`** | `src/http.js` (new, Q5), `config.js` | M1-M6. Data flows one way: transport returns raw JSON, callers parse |
| **S** | `map/store.js` | `createMapSession()` **factory** returning a plain object, plus the narrow mutation API | nothing | everything |
| **V** | `map/view_grid.js` (layer 7) | `renderGridCanvas` + `paintOverlayDot`; paints M3's seating result | M3, S, `dom.js` | M1, M2, M4, M5, M6, T. **It must not be able to fetch or to decide** |
| **C** | `map/controls.js` | the `el` cache, the form <-> `Declaration` adapter, event wiring, composition root | everything above + `config.js` | nothing. This is the only file allowed to know all of it |
| **P** | `src/transfer_plan.js` (layer 5, **stays where it is**) | plan authoring | `doe_bands.js`, `tsv.js`, `utils.js`, `config.js` | **all of `map/`**. Keeps the injected controller (Q4) |

### 1.3 Can layers 1-4 and 6 be pure ES modules with no DOM at all?

**Yes, all of them, and there is exactly one function that has to be split to get there.**

- The blocker is `resolveGridFrame` (`map_editor.js:5502`). It takes `el` as its 7th parameter
  and it does DOM in **both directions**: it reads the form (`el.gridCols.value`,
  `el.gridRows.value`, `el.gridStartX.value`, `el.gridStartY.value`, `el.gridYInvert.checked`
  at 5575-5579) and it **writes six inputs back** (`el.physWaferDia.value = ...` through
  `el.physEdgeMargin.value = ...`, 5564-5569). Both halves are adapter work: the read is "what
  the user currently declares", the write is "publish the resolved declaration to the form".
  Move both into `controls.js`, have `declaration.js` take and return a plain record, and
  layer 1 is pure. That is the first extraction of the rebuild and everything else waits on it.
- No other case was found. Only 2 of 248 functions touch canvas and both are layer 7.
- The genuine non-purity in layers 1-4 is **network, not DOM**: the declaration arrives over
  REST. That is why `transport.js` is a separate module and why M1 is forbidden from importing
  it. A harness feeds M1 a literal; production feeds it what transport returned.

### 1.4 A forbidden list that is a document will be gone in six months

The brief is right that the forbidden column is what keeps the split from collapsing. A table
in a markdown file does not do that. Make it a gate, and **reuse the primitive that already
exists** rather than inventing one: `client2/scripts/` already holds
`check_clipboard_convention.mjs` and `check_contracts.mjs`, both wired into `prebuild`
(`package.json`). Add a third of the same shape:

- `client2/scripts/check_module_layering.mjs` reads **`client2/module_layers.json`** (config,
  not hardcoded - per the standing rule), which declares the allowed import edges per module.
- It parses each `map/*.js` file's import specifiers with a regex (no parser, no
  `node_modules` - see Q3 on why that matters) and fails on any edge not declared.
- It additionally forbids, under `map/**`: `import '*.css'`, `import.meta.env`, bare
  `fetch(` outside `transport.js`, and `document`/`window` outside `view_grid.js` and
  `controls.js`.

**One consequence must be stated because it looks like a violation of the standing "config
over hardcode" rule and is not.** `config.js:1` reads `window.location.port` and `config.js:4`
reads `import.meta.env.VITE_USER`. It is therefore **not importable in node**. So no pure map
module may import `config.js` - which does not mean values get hardcoded. The composition root
(`controls.js`) imports `config.js` and **passes the values in**. Tunables stay in config; the
pure layers stay importable. Both rules hold; only the delivery changes.

---

## Q2. Module state

### 2.1 The ceiling, cited

`client2/scripts/check_harnesses.mjs:241-244`:

```js
const CEILINGS = new Map([
  ['undeclared_identifier_harness.mjs', { key: 'MODULE_STATE', max: 48,
    what: 'module-level mutable bindings in client2/src/map_editor.js' }],
]);
```

Supporting machinery:
- **Counting rule** documented at `check_harnesses.mjs:233-234`: top-level `let`/`var`
  declarators, per bound name. `const`, `function`, `class`, and anything inside a body are
  **not** counted; `export let` **is**.
- **Emitter**: `client2/tests/undeclared_identifier_harness.mjs:260` -
  `console.log(\`MODULE_STATE ${stateNames.length}\`)`. The runner never counts; it reads.
- **Comparison and BLOCKING verdict**: `check_harnesses.mjs:331-349`, including the
  "a ceiling that stopped reporting is not a pass" branch at 337-341.
- **Known slack**: `check_harnesses.mjs:236-238` records that 2 of the 48 (`tables`,
  `isMouseDown`) are already dead, so the first re-baseline is expected.

Independently re-measured today: `grep -cE "^(let|var) " client2/src/map_editor.js` = **48**.
Headroom **0**, confirmed.

### 2.2 Where state lives in the new structure

**A factory, not a store singleton.** `map/store.js` exports `createMapSession()` which
returns a plain object. Nothing in the module is declared at module scope.

The reason this is not pedantry: a store singleton is module-level mutable state wearing a
different noun, and it would **defeat the ceiling by construction**, because
`export const S = { ... }` is a `const` and the counting rule at `check_harnesses.mjs:233-234`
does not count it. The state would survive the split unchanged while the number went to zero.
That is the single most likely way this rebuild silently buys back what it was meant to remove.

Modules M0-M6 never see the session object at all. They are functions of their arguments.
Only `controls.js` (which creates it) and `view_grid.js` (which receives it as a parameter,
not as an import) hold a reference.

### 2.3 What it costs at the call sites

Honestly: **parameter counts go up, and today's code already shows how bad that gets if it is
done naively.** `resolveGridFrame` already has 9 parameters. `getWaferBoundingBox`'s cache key
at `map_editor.js:1833` concatenates 11 values. Adding a state argument to functions shaped
like that produces 12-argument signatures nobody can call correctly.

The convention that prevents it: **one frozen record per layer boundary.** `Declaration`,
`Frame`, `Seating`, `Candidate[]`, `Decision`. Every function in M1-M6 takes at most
`(record, options)`. That is 2 arguments, it is self-documenting, and it is exactly what a
harness needs to construct - which is the same property Q3 needs.

Second cost, and it is the real one: the standing client-pm trap is that `state.js` is not
reactive, so state mutation without an explicit refresher call leaves the screen stale. A
factory store makes that worse if every caller is responsible for refreshing. Mitigation:
`view_grid.render(seating, session)` becomes the **only** writer of the canvas, and
`controls.js` calls it after every mutation. One refresh call site to audit, not 48.

### 2.4 Does the ceiling survive the split? No. Three ways it breaks.

1. **Per-file scaling.** Ten files at 48 each is 480. A per-file ceiling is scale-blind.
2. **It goes quiet.** The ceiling is keyed by harness name and scoped by a hardcoded path in
   its `what` string. When `map_editor.js` stops existing, the counter counts zero and reports
   green forever while the new tree accumulates freely. The runner's own comment at
   `check_harnesses.mjs:338-341` says a ceiling that stopped reporting is not a pass - but it
   only catches a **missing line**, not a line that truthfully reports 0 about a dead file.
3. **`const` laundering.** Section 2.2 above.

**Redefinition, four clauses:**

- **One number, summed over a globbed tree.** `MODULE_STATE` becomes the total across
  `client2/src/map/**/*.js` plus `map_editor.js` while it still exists. Sum, never per-file.
- **Glob, do not enumerate.** The counter must discover files by walking the directory, not by
  reading a registered list. A list is a place to forget, and forgetting reads as green.
- **Extend the rule to mutable containers.** Count `export const NAME = {` and
  `export const NAME = [` (and `new Map(` / `new Set(`) at module scope. A mutable container at
  module scope is shared mutable state regardless of the binding keyword. Without this clause,
  the split's cheapest first move is a rename.
- **Start at 48 and only ever fall.** The rebuild's own gate: it must publish a number at
  every milestone, and the number must be monotone downward. A rebuild that ends at 47 has
  not done the thing it was approved for.

---

## Q3. The harness problem

### 3.1 Counts

**`client2/tests/`**: 36 files - 35 `.mjs` + 1 `.py` (`seam_7b_oracle.py`).

| property | count | of 35 | method |
|---|---|---|---|
| read source text with `readFileSync` | **35** | 100% | `grep -ln readFileSync tests/*.mjs` |
| evaluate sliced text in `node:vm` | **32** | 91% | `grep -ln "node:vm"` |
| slice `map_editor.js` | **28** | 80% | `grep -ln "map_editor\.js"` |
| slice `transfer_plan.js` | **2** | 6% | `grep -ln "transfer_plan\.js"` |
| `import` anything from `../src` | **1** | 3% | `grep -ln "from '\.\./src"` |
| **import-only (no slicing)** | **0** | 0% | intersection |

The single importer is `client2/tests/effort_instrument_harness.mjs:21`, which imports
`getMapIdFromMeta` from `../src/map_key.js` **and also slices** `map_editor.js`. Its own
comment at line 20 states the enabling condition precisely: "`map_key.js` imports nothing, so
this needs no node_modules."

**`contracts/`**: 7 contract directories; 6 have a `client_harness.mjs`
(`band_arithmetic`, `blank_predicate`, `config_resolve_report`, `doe_band_rules`,
`legend_map_scope`, `map_seam`; `notation_fold` is Python-only). **6 of 6 slice text. 0 of 6
import.** Combined client total: **41 harnesses, 41 slicing, 1 importing, 0 import-only.**

Two findings that matter more than the counts:

**(a) The slicing habit has already outlived its necessity by one module.**
`contracts/map_seam/client_harness.mjs:48` reads `client2/src/map_key.js` **as text** and
brace-slices it, and the harness's own comment at :58-62 explicitly acknowledges that the file
exports its symbols. Every function in that file is importable. Nothing forced the slice
except the surrounding technique. If the rebuild produces importable modules but does not
change the harnesses, this is what happens to all of them.

**(b) The slicing technique now has a VETO over the source structure, and it has already used
it.** `client2/src/map_editor.js:1826-1828`, a comment in production source, translated:

> Do not extract this into a separate function. Four harnesses slice this function, and every
> added module-global dependency kills all four with `ReferenceError` - measured: three
> harnesses died that way this round, and `loadExistingMap`'s `catch` swallowed it as a
> "0-cell load".

That is the test technique dictating that a function stay inlined inside `getWaferBoundingBox`.
**Any rebuild that keeps slicing inherits that veto**, and it is a veto pointed directly at the
decomposition this round exists to perform.

**(c) Brace-scanner fragility, named in three places.** `standard_frame_origin_harness.mjs:46`,
`valid_die_dirty_guard_harness.mjs:82`, and `valid_die_origin_alignment_harness.mjs:52` each
carry a warning that `indexOf('{')` catches the default-parameter brace in
`loadExistingMap(opts = {})`. Six harness files define their own regex-plus-brace extractor.
Six copies of a parser that is known wrong.

### 3.2 What must be true of the new modules for a harness to import them

Four conditions, in order of how easily each is violated:

1. **The module must `export`.** `map_editor.js` has **0** exports. That single fact is the
   entire reason slicing exists. Nothing else on this list matters until it is fixed.
2. **No bundler-only import spellings.** Concretely, banned under `map/**`:
   - `import './x.css'` - `map_editor.js:1-2` does exactly this; node cannot resolve a bare
     CSS specifier and the import fails before any test code runs.
   - `import.meta.env` - `vite.config.js:5-12` defines `VITE_USER` at build time; in node it
     is undefined. This is why **`config.js` is not node-importable** (`config.js:1` also
     reads `window.location.port`) and why no pure module may import it.
   - `ag-grid-community` or any `node_modules` package.
3. **`node_modules` must NOT be needed.** This is a hard requirement, not a preference, and
   section 3.3 explains why. `map_key.js` satisfies all three conditions today and is the
   existence proof that the property is reachable.
4. **Build tooling and entry points: nothing changes.** `vite.config.js:14-23` declares 6 HTML
   entries. `map/*.js` are internal modules reached from `map_editor.html`'s existing script
   tag. **The split does not touch the build graph and needs no new entry point.** That is
   worth stating explicitly because it is the cheapest part of the whole proposal.

### 3.3 The UNAVAILABLE third state, and the trap it sets for this exact rebuild

`check_harnesses.mjs:269-282` defines the third verdict. `HAS_NODE_MODULES` at :281;
claimable only when `client2/node_modules` is demonstrably absent **and** the failure is
specifically module resolution (`UNRESOLVED_IMPORT_RE` at :282); reported at :319-325.

**The trap:** the `MODULE_STATE` ceiling rides on `undeclared_identifier_harness.mjs`, which is
**the one harness that needs an installed package** (`rolldown/parseAst`). So in every git
worktree the ceiling is unenforced. The runner already says so, at :323-325:

> AND THE CEILING RODE ON IT ... You can add module state here and still see a green gate; the
> main checkout will refuse it.

This repository does parallel work in worktrees. A multi-lane rebuild would run for months with
**no lane able to see the state ceiling**, discovering breaches only at merge.

**Recommendation:** the redefined counter of section 2.4 must not need a parser. A
column-0 regex over `^(let|var|export let|export var|export const \w+ = [\[{])` is sufficient
for a file set that the layering gate already keeps flat, and it makes the ceiling enforceable
in a worktree. That one change converts the ceiling from advisory to real during exactly the
months when it is load-bearing. `rolldown/parseAst` can stay for the undeclared-identifier
check, which is a different question and can remain UNAVAILABLE.

### 3.4 Where the seam contract sits in the new structure

`contracts/map_seam/` stays where it is and stays the oracle - `MAP_ALIGNMENT_SPEC.md` §8.4 is
right that it survives a client rewrite because it is a claim about **agreement**, not about an
implementation. What changes is the client half's technique.

`contracts/map_seam/client_harness.mjs` is **1,286 lines** today. `sliceFunction` is at :63-77,
`sliceConst` at :80-84, and the module-state stub block begins at :154. After the split it
becomes roughly 40 lines of `import { ... } from '../../client2/src/map/frame.js'` plus the
same vector loop. **The vm sandbox and every stub inside it disappear along with the slicing,
because a pure module has no globals to stub.** That is the concrete, measurable payoff of the
importability gate, and it is the same shape for all 6 contract harnesses.

**And the coordinate gap the lead measured is a direct consequence of the slicing.**
`getWaferBoundingBox` cannot be pinned by the contract today because slicing it drags in
`physFrameOverride` (`map_editor.js:1432`), `boundingBoxCache` (`:1747`),
`validDieResolveSeq` (`:2295`), plus `validDieBasis()`, `getTransformedPhysicalConfig()`,
`isCellInsideWaferFast()`, `getDieIndex()` and `isValidDieAt()` - 3 module-level bindings and
5 functions, every one of which must be stubbed correctly or the vector scores a stub instead
of the code. **That is why the vectors pin only the inputs to the bounding box and not the
box.** It is not an oversight in the vector file; it is the technique refusing.

Once M2 exports `waferBoundingBox(frame, physSpec, mask)` as a function of its arguments, the
vector group that catches the measured 165/165-cell divergence is **writable as data** - one
more group in `vectors.json`, not a new harness. It should be the **first** coordinate group
added, and it must carry a case where the client side has a resolving `valid_die_ref` (mask
bbox, `map_editor.js:1829-1832` and 1861-1871) against the server's circle
(`map_overlay.py:456-466`), because that is precisely the pair that diverges. A coordinate
group that omits that case would go green and prove nothing.

Per the coordinator's correction I have not used `MAP_ALIGNMENT_SPEC.md` §2's fixture
parenthetical or §2.1's delta claim anywhere in this report.

---

## Q4. The plan surface

### 4.1 Size

| file | lines | bytes |
|---|---|---|
| `client2/src/transfer_plan.js` | **1,875** | 111,172 |
| `client2/src/transfer_plan.css` | **921** | 40,768 |

### 4.2 Coupling, counted in both directions

**`map_editor.js` -> `transfer_plan.js`: 1 import + 14 call sites.**
Import at `map_editor.js:6` (5 names: `initTransferPlan`, `notifyMapContext`,
`notifyLegendChanged`, `notifyPaintCounts`, `stageTargetTables`). Call sites at
`map_editor.js:358, 1185, 1277, 3124, 4338, 4393, 4399, 4416, 5257, 6069, 8182, 8201, 8208,
8244`. (A 16th grep hit at :4639 is a comment explaining why a call is deliberately absent.)

**`transfer_plan.js` -> `map_editor.js`: ZERO direct references.**
No import. No `window.<map symbol>` - the only `window.` uses are 2 x `window.getSelection`.
No `localStorage` at all (0 occurrences). No shared module state.

**Every crossing goes through one injected object**, built at `map_editor.js:358-399`:
**20 members injected**, **14 referenced by name** in `transfer_plan.js`, across **27 lines**
containing `controller.` and **34 name occurrences**. The 6 injected and never referenced
(0 occurrences each): `getCounts`, `listOverlays`, `removeOverlay`, `toggleOverlay`,
`clearOverlays`, `fetchMapKeyColumns`.

### 4.3 Decision: it stays separate, and it must NOT import layers 1-4

Four reasons, strongest first:

1. **It is already the cleanest seam in this client, and it was built deliberately.**
   `map_editor.js:355-357` states the design in the source. 20-member injection with zero
   back-references is better than anything else in `client2/src/`. The rebuild should
   **copy this pattern outward**, not dissolve the one place it already works.
2. **Letting it import `frame.js` / `compare.js` destroys the cleanest layering rule.** With
   the plan surface kept controller-injected, the gate can say: *no `map/*` module may be
   imported by any DOM authoring surface other than the composition root*. That single rule is
   checkable by regex. Break it here and the plan surface gains the ability to compute
   alignment, which is how a second opinion about coordinates gets born - the defect class
   `map_key.js`'s header (lines 24-27) was written to prevent.
3. **The purpose chain says the plan is the terminus.** A terminus consumes; it does not
   derive. What it needs is a **decided** frame, not the machinery to decide one.
   `getMapContext()` at `map_editor.js:374-380` already delivers exactly that shape
   (`{table, mapKey, loaded, depth, parent}`).
4. **Moving it out of the map editor is refused on measurement and on the UI constraint.**
   14 of the 20 injected members are legend/brush/overlay operations on the **currently open
   map**; the panel is an editor of that map's legend, not an independent screen. Moving it out
   would require re-establishing that controller across a page boundary, and it would be a new
   pane - which the standing UI constraint forbids outright.

**One change I would make.** The controller should be a **declared shape validated at
injection**, not an ad-hoc object literal. Six dead members accumulated unnoticed because
nothing checks. Cheapest form, no new machinery: put the member list in
`client2/module_layers.json` alongside the import edges and have `check_module_layering.mjs`
assert that every declared member is referenced at least once in the consumer. That deletes the
current 6 and prevents the next 6.

---

## Q5. The build and the shipping hazard

### 5.1 What the split does to the hazard: WORSE, for two measurable reasons

1. **The reviewer's question stops having an answer.** Today one source file maps to one chunk
   and the question is "did `map_editor.js` change?". After the split it is "did **any** of
   ~12 files change?", which no human answers reliably. The failure that already happened
   (source landed, `dist` stale) gets 12 chances instead of 1.
2. **`client2/dist/` is tracked, and the diff gets worse.** Verified: `.gitignore:40` ignores
   `client/dist/` only; `git ls-files dist` returns tracked files. Vite emits content-hashed
   asset names - `dist/assets` holds **14** files today. More source modules means more chunks
   means more renames per build, so the eight-builds-in-a-day churn grows with the split.

### 5.2 The smallest mechanical guard

Two parts. Neither is a process rule; both are code.

**(a) Build stamp plus a gate that can be run as one command.**

- A vite `closeBundle` plugin writes `client2/dist/.source-stamp.json`: a SHA-256 over the
  sorted manifest of the exact input set - `client2/src/**/*.{js,css}`, `client2/*.html`,
  `vite.config.js`, `package-lock.json`.
- `client2/scripts/check_dist_fresh.mjs` recomputes the same hash and exits non-zero on
  mismatch. About 60 lines across two files, same shape as the three existing `check_*.mjs`.

Where it runs is the part that is easy to get wrong:

- **Not in `prebuild`.** `package.json`'s `prebuild` runs *before* `vite build`, so a
  freshness check there would be stale by construction on every single build.
- **In a repo-level `pre-commit` hook**, installed with `git config core.hooksPath .githooks`.
  Verified today: `core.hooksPath` is **unset** and there is **no `.githooks` directory** - so
  this is new, not a modification of something in use. `core.hooksPath` lives in the shared
  `.git/config`, so it applies in **every worktree automatically**. In a worktree (which cannot
  build - no `node_modules`) the hook refuses a commit that touches `client2/src/**` without a
  matching stamp and says "build in the main checkout". That is the existing written worktree
  rule made mechanical.
- **Also as `npm run check:dist`**, so the lead or CI can ask in one command.

**(b) The stamp must be visible from the running page, or "I rebuilt" is still a claim.**
The mechanism already exists: `vite.config.js:5-12` defines `import.meta.env.VITE_USER` and
`config.js:4` consumes it. Add `VITE_BUILD_STAMP` the same way, export it from `config.js`, and
emit it on the **existing** startup console line in `main.js`. Then "is the user running the
code I wrote" is answerable from a screenshot instead of from trust.
**This satisfies the UI constraint**: no new pane, no new mode, no modal, nothing new shown to
a user - it is a console line.

**What I would NOT do:** unhash the asset filenames to shrink the dist diff. It would make
review easier and it would break cache busting on a page the factory keeps open for hours, and
a stale cached chunk is the *same defect class* (user runs old code) this guard exists to kill.
The stamp fixes the reporting problem without touching caching.

### 5.3 The fetch survey

**Measured: 78 real call sites in `client2/src/*.js`.** Method: 83 word-boundary `fetch(`
occurrences (`grep -oE "(^|[^A-Za-z0-9_.])fetch\("`), minus 5 that are inside comments
(`admin.js:40`, `admin.js:127`, `admin.js:1077`, `config.js:87`, `map_editor.js:9582`).
The brief said 82; I measure **78** and give the method so the difference is auditable rather
than argued. `*.html` contributes 0.

| file | sites | | file | sites |
|---|---|---|---|---|
| `map_editor.js` | 25 | | `transfer_plan.js` | 3 |
| `main.js` | 14 | | `ui.js` | 3 |
| `api.js` | 7 | | `clipboard.js` | 2 |
| `enrichment.js` | 6 | | `value_suggest.js` | 1 |
| `admin.js` | 5 | | `trace.js` | 1 |
| `graph_viewer.js` | 5 | | `trace_launch.js` | 1 |
| `timeline.js` | 4 | | `effort_meter.js` | 1 |

**Exactly one has a deadline: confirmed, 1 of 78.** `map_editor.js:9588-9600` -
`AbortController` plus a timer driven by `MAP_SPEC_SAVE_TIMEOUT_MS` from `config.js`.
`value_suggest.js:393-400` also constructs an `AbortController` but attaches **no timer**; it
is a supersede guard for a stale in-flight request, not a timeout. Counting it would be the
second wrong number in this file's history and the code says so.

**Does the split change where a shared wrapper should live? Yes - and the answer is not
`api.js`.** `api.js` is not a transport module: its 8 exports (`checkServerHealth`,
`loadTables`, `switchTable`, `loadSchema`, `fetchData`, `handleCellEdit`, `addRows`,
`deleteSelectedRows`) are **grid-screen operations that happen to fetch**. Putting the
primitive there makes the map tree depend on the grid screen. `admin.js:128` already holds a
second partial wrapper (`adminFetch` - attaches the token, re-asks once on GATE rejection). So
there are two half-wrappers and no primitive.

Correct home: a new **`client2/src/http.js`** - no DOM, no app knowledge, one exported
`request(url, {method, body, timeoutMs, signal})` that **always** attaches a deadline sourced
from `config.js` by its caller. Its three consumers become `api.js`, `adminFetch`, and
`map/transport.js`. Put it **outside `map/`**, because 53 of the 78 sites are outside the map
editor; placing the primitive inside the map tree would invert the dependency.

**Scale caveat, stated so this is not mis-scheduled:** 78 call sites is not a rebuild-round
refactor. The rebuild creates `http.js` and routes the map tree's 25 through
`map/transport.js`; the other 53 migrate opportunistically. The layering gate should therefore
forbid raw `fetch` **only under `map/**`** at first - a repo-wide ban would block every
unrelated round for months and would be repealed rather than obeyed.

---

## 6. Proposed lessons for `agent_workspace/memory/client-pm.md`

Proposals only, per the operating rule; not added directly.

1. **A test technique that slices source text acquires a veto over source structure.**
   Evidence: `map_editor.js:1826-1828` forbids an extraction because four harnesses would die.
   When a comment in production source refuses a refactor for the tests' sake, the tests are
   the thing to fix.
2. **A ceiling on `let`/`var` is defeated by `export const OBJ = {}`.** Any state ceiling must
   count mutable containers at module scope, or the first move of any split is a rename.
3. **`config.js` is not node-importable** (`config.js:1` reads `window.location.port`, `:4`
   reads `import.meta.env`). A module that imports it can never be imported by a harness.
   Config values must be **passed in** to pure modules, which keeps "config over hardcode" and
   importability from being in conflict.
