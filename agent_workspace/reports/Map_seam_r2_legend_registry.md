# map_editor.js refactoring — Round 2: the legend-registry seam

**Author**: map-pm · **Date**: 2026-08-04 · **Base**: `689ebb9` (R1)

**Verdict: the round is complete and self-contained. TEMPORARY EXPORTS: NONE** — see §8.

🔴 **The seam was NARROWED, and the measurement is why.** The 30-function "legend-registry"
block is two disjoint halves. One is pure and moved. The other cannot leave without exporting
mutable state, so it stayed. §1 is the measurement that forced that; §2 is what it means for R3+.

---

## 1. The write-set measurement, and the shape it forced

Method: AST parse of `client2/src/map_editor.js` via `vite.parseAst` (oxc), scope-aware walker;
writes counted for direct assignment, update expressions, member assignment rooted at the
variable, and mutating method calls. Re-measured on the working tree at round start — the R1
measurement's numbers were **not** trusted.

### 1a. The two halves

| | functions | module state READ | module state WRITTEN |
|---|---|---|---|
| **Half A — the registry ROW normal form** | 20 | **0** | **0** |
| **Half B — the read/save orchestration** | 12 | 15 distinct bindings | 12 distinct bindings |

**Half A** (`buildSplitKey`, `parseJsonCol`, `normalizeBands`, `normalizeKnobs`, `knobsToObject`,
`serializeKnobs`, `serializeStack`, `serializeMaterials`, `normalizeLegendItem`, `cloneLegend`,
`legendRowPayload`, `canonRegistryRow`, `registryFingerprint`, `buildLegendRegistryUpdates`,
`parseLegendRegistryRows`, `getMissingDescValues`, `formatLegendMetaText`, `legendRowSignature`
+ the consts `SPLIT_KEY_SEP`, `LEGEND_PAYLOAD_COLUMNS`, `FP_UNIT`, `FP_ROW`) is a pure function of
its arguments — every one of them. It is **R1's shape exactly**: nothing is passed that was not
already an argument, and no new parameter was invented.

**Half B** is `defaultLegendRows`, `declaredLegendRow`, `saveLegendToStorage`, `fetchRegistryRows`,
`readRegistryScope`, `reconcileVocabClaims`, `applyRegistryRowsToLegend`, `saveLegendToServer`,
`probeZoneColumns`, `applyLegendSaveResult`, `getPlanSaveState`, `persistLegend`,
`scheduleCellDraft`, `seedEmptyDoe`.

### 1b. The 7-variable legend cluster — writers on both sides of the boundary

This is the number that decided the round. Every one of the seven is written from **inside** the
seam *and* from **outside** it:

| variable | writers INSIDE the seam | writers OUTSIDE the seam |
|---|---|---|
| `legend` | `seedEmptyDoe`, `applyRegistryRowsToLegend` | **6** — `autoAddLegendValue`, `applyDoeDraftRecord`, `renderLegendTable`, `deleteLegendRowForPanel`, `loadExistingMap`, `restoreEditorState` |
| `legendMeta` | `seedEmptyDoe`, `applyRegistryRowsToLegend`, `saveLegendToServer` | **1** — `restoreEditorState` |
| `legendDirty` | `persistLegend`, `scheduleCellDraft` | **3** — `loadExistingMap`, `pushMapData`, `restoreEditorState` |
| `legendConflict` | `saveLegendToServer` | **3** — `loadExistingMap`, `restoreEditorState`, `openMapFrame` |
| `legendReplaceScope` | `saveLegendToServer` | **4** — `loadExistingMap`, `restoreEditorState`, `setLoadedIdentity`, `openMapFrame` |
| `legendSaveState` | `applyLegendSaveResult` | **3** — `loadExistingMap`, `restoreEditorState`, `openMapFrame` |
| `legendVocabularySeed` | `seedEmptyDoe` | **1** — `restoreEditorState` |

Plus five more bindings Half B touches that are owned elsewhere: `activeBrush` (6 outside
writers), `gridData` (20), `draftBase` (1), `frameTouched` (2), `overlayContract` (1, written by
`fetchPaintRules`), `selectedTable` (3, read-only inside the seam).

**Total: 21 write edges into the 7-variable cluster from outside the seam, from 8 distinct
functions in 4 other seams** (map-load, frame-stack, draft-restore, legend-panel-ui) — plus `push`
for `legendDirty`.

### 1c. The decision

Moving **Half B** would require `map_editor.js` to import a *writable* binding, or a
getter/setter pair per variable. Per the round's stop condition, **that was not shipped.** Moving
**Half A** requires neither: it exports 10 plain functions, every one of which takes everything it
needs as an argument.

**Shipped: Half A only, as `client2/src/split_registry_row.js`.** This is not a half-finished
seam left for a later round to clean up — it is a **permanent boundary in the right place**: the
row normal form does not need session state and never did, and the orchestration cannot be
separated from the state it mutates. The two halves meet through function calls with arguments,
which is the only interface either side needs.

## 2. What R3+ should do with Half B (for lead-PM adjudication)

Half B is **not a cheaper seam waiting to be taken** — it is the legend cluster's owner, and the
cluster's other 21 write edges are in the orchestrators (`loadExistingMap` 663 LOC,
`restoreEditorState`, `openMapFrame`). Extracting it means moving the state with it, and the state
is written by four other seams. Concretely, the line would have to be drawn around **the legend
cluster and every writer of it**, which is `map-load` + `draft-restore` + `frame-stack` +
`legend-panel-ui` — i.e. the orchestrators the board has already deferred to the ⓑ decision.

**Recommendation: do not re-attempt Half B as a "seam". Fold it into the orchestrator judgement
the board scheduled for after R8.** R3 should take `paint-lock` (121 LOC, 1 outgoing call) as the
board's order already says.

## 3. What moved

New module **`client2/src/split_registry_row.js`** (366 lines), imported by `map_editor.js`.

| source in `map_editor.js` @689ebb9 | lines | what |
|---|---|---|
| 295–297 | 3 | `SPLIT_KEY_SEP` + its comment |
| 322–649 | 328 | `buildSplitKey` … `formatLegendMetaText` — one contiguous block: the whole DOE/ZONE normal-form section, `LEGEND_PAYLOAD_COLUMNS`, `FP_UNIT`/`FP_ROW`, the payload builder and the response parser |
| 3983–3991 | 9 | `legendRowSignature` + its comment (the third reader of `LEGEND_PAYLOAD_COLUMNS`; it belongs with the list) |

**Byte-identity proof.** `git diff -U0` removes **343** lines from `map_editor.js` and adds **11**.
**342 of the 343 removed lines appear byte-identical in the new module** (the check allows only a
leading `export ` on the ten exported declarations). The 343rd is the
`import … from './transfer_plan.js'` line, whose only change is dropping the now-unused
`bandToState` specifier — its replacement is one of the 11 added lines. The other 10 added lines
are the new import statement and its comment. **No moved line was edited.**

`map_editor.js`: **9,495 → 9,163 lines (−332).** Cumulative over R1+R2: 9,632 → 9,163 (−469).

### 3a. Exports — 10, each with a real importer today

`normalizeBands`, `normalizeKnobs`, `normalizeLegendItem`, `cloneLegend`, `registryFingerprint`,
`buildLegendRegistryUpdates`, `parseLegendRegistryRows`, `getMissingDescValues`,
`formatLegendMetaText`, `legendRowSignature`.

The other 8 functions and all 4 consts stay **module-private**, exactly as they were — a public
surface wider than its importers is a surface nobody holds to anything. Notably
**`LEGEND_PAYLOAD_COLUMNS` is not exported**: nothing outside the module reads it. That fact
changes landmine #1 — see §6.

### 3b. Module-load smoke (the class a text slicer is structurally blind to)

`import('client2/src/split_registry_row.js')` resolves and executes in node (with only `.css`
imports and `import.meta.env` shimmed, both of which are Vite build-time features; the real JS
graph `split_registry_row → transfer_plan → doe_bands/config/utils/tsv` loads unmodified). All 10
exports are functions, and end-to-end:

```
buildLegendRegistryUpdates('bonding_map','MAPB',[row],'tester','2026-08-04 00:00:00')[0]
  .business_key_val === 'bonding_map|MAPB|1'
  .updates === {"split_key":"bonding_map|MAPB|1","ref_table":"bonding_map","map_key":"MAPB",
                "value":"1","split_desc":"A","color":"#10b981","knobs":"{\"temp\":\"200\"}",
                "stack":"3","mat_1h":"[]","mat_mid":"[\"LOT_A1\"]","mat_top":"[]",
                "eventtime":"2026-08-04 00:00:00"}
legendRowSignature(row) === '1A#10b981{"temp":"200"}3[]["LOT_A1"][]'
```

## 4. What deliberately did NOT move or change

- **Coordinate math: not one line.** No file under the coordinate contract was opened for edit.
- **The whole of Half B**, and every one of the 12 module-state bindings it writes.
- `SPLIT_REGISTRY_TABLE`, `REGISTRY_SCOPES`, `ZONE_COLUMNS`, `LEGEND_SAVE_MESSAGE`,
  `EMPTY_DOE_SEED` — all read by Half B, all still in `map_editor.js`.
- **The dead module state `tables` (:46) and `isMouseDown` (:52)** — untouched, per the ruling.
- **No bug was fixed.** One found while moving is reported in §9.

## 5. Oracles — before and after

Baseline captured at round start; a second "after" capture was taken at the end because other
lanes landed work in the shared tree mid-round (`transfer_plan.js`, `server/transfer_plan.py`,
a new harness). **The two after-captures are byte-identical for all 22 harnesses and all 6
contracts**, so nothing below is another lane's delta.

### 5a. Stored coordinates — 0 cells moved

Method (unchanged from R1): **cells carry their own coordinates as values**; no key matching
anywhere. Every harness and contract was run before and after and its **complete stdout compared
byte-for-byte**, so every `dbX`/`dbY` (and every mm/mask/seat) assertion is compared against its
recorded literal on both sides.

**Result: byte-identical for all 22 harnesses and all 6 contracts, with exactly three
exceptions, none of which is a coordinate:**

| file | before → after | why |
|---|---|---|
| `undeclared_identifier_harness` | `1136 declared, 1170 referenced` → `1109, 1143` | the 20 declarations left the file (and their locals). **`0 undeclared` on both sides**, all 6 checks green |
| `contract config_resolve_report` | `31 files scanned` → `32` | it globs `client2/src/*.js`; the new module is the 32nd. Still green |
| `split_registry_harness` **[known red, dead]** | `Error: const DEFAULT_LEGEND not found` → `Error: const SPLIT_KEY_SEP not found` | see §7 — a finding, not a re-baseline |

Coordinate/geometry value assertions inside that byte-identical set: `valid_die_head_parity_oracle`
17,498 · `valid_die_frame_adoption` 228 · `valid_die_origin_alignment` 153 · `overlay_wafer_mm` 69 ·
`geometry_origin_reseat` 46 · `startxy_probe` 29 · `standard_frame_origin` 19 = **18,042
assertions, all identical.**

### 5b. Per-harness ASSERTIONS — before / after

`node client2/scripts/check_harnesses.mjs`, **exit 0 both runs**. Gate/debt split unchanged:
**22 harnesses ― 17 gated, 5 known-red (5 still red, 0 recovered); every gated harness green.**
No `[BLOCKING]`, no `MISSING ASSERTIONS`, no floor complaint in either run.

| harness | before | after | Δ |
|---|---|---|---|
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
| **split_registry [known red]** | no ASSERTIONS line | no ASSERTIONS line | — (message changed, §7) |
| standard_frame_origin | 19 / 0 | 19 / 0 | — |
| startxy_probe | 29 / 0 | 29 / 0 | — |
| undeclared_identifier | 6 / 0 | 6 / 0 | — |
| valid_die_authoring **[known red]** | 99 / 1 | 99 / 1 | — |
| valid_die_frame_adoption **[known red]** | 228 / 42 | 228 / 42 | — |
| valid_die_head_parity_oracle | 17498 / 0 | 17498 / 0 | — |
| valid_die_origin_alignment | 153 / 0 | 153 / 0 | — |
| value_suggest_keys | 94 / 0 | 94 / 0 | — |
| virtual_column_render | 59 / 0 | 59 / 0 | — |

*(A 23rd harness, `availability_gross_marker_harness.mjs`, appeared in the tree mid-round from
another lane. It is not this round's and is not counted above; the final gate run reports
`23 harnesses ― 18 gated`, exit 0.)*

**Nothing was re-baselined.** `client2/scripts/check_harnesses.mjs` was **not touched** — no floor,
no `KNOWN_RED` entry, no expectation edited.

### 5c. Contracts — `node client2/scripts/check_contracts.mjs`, exit 0 before and after

| contract | before | after |
|---|---|---|
| **legend_map_scope** ⟵ re-pointed | 71 assertions, exit 0 | **71**, exit 0 |
| **band_arithmetic** ⟵ re-pointed | 82 assertions, exit 0 | **82**, exit 0 |
| **doe_band_rules** ⟵ re-pointed | 396 assertions, exit 0 | **396**, exit 0 |
| map_seam | 482 assertions, MATCHES | 482, MATCHES (**file untouched**) |
| blank_predicate | 9/9, 0 divergences | 9/9, 0 divergences |
| config_resolve_report | green, 31 files | green, 32 files |

## 6. The `export` slicer landmine — corrected, then fixed and PROVEN

**The briefed landmine was `contracts/map_seam`'s `sliceConst`. Measured: it does not fire.**
`map_seam`'s `client_consts` are `CANON_INT_RE`, `CANON_FLOAT_RE` (map_key.js) and
`UNTRACKED_REASON` (transfer_plan.js) — **no legend const is in that contract**, and none of its
`client_symbols` is a legend function. `contracts/map_seam` was **not opened this round.**
Three of the four named consts (`LEGEND_SAVE_MESSAGE`, `REGISTRY_SCOPES`, `ZONE_COLUMNS`) never
left `map_editor.js`, and the fourth (`LEGEND_PAYLOAD_COLUMNS`) moved **without an `export`**
because nothing outside the module reads it. **Shipping a const tolerance would have been an
unexercised change — the same one I reverted in R1.** It was not shipped.

**What DID fire is `extractFunction`, in two other harnesses**, because ten moved functions are
now spelled `export function NAME(`:

| harness | slicer before | after |
|---|---|---|
| `contracts/legend_map_scope/client_harness.mjs` | `(^\|\n)\s*(?:async\s+)?function\s+NAME\s*\(` | `(^\|\n)\s*(?:export\s+)?((?:async\s+)?function\s+NAME\s*\()` — the `export ` is **excluded from the slice** (an export statement inside `vm.runInContext` is a SyntaxError) |
| `contracts/band_arithmetic/client_harness.mjs` | `(^\|\n)\s*function\s+NAME\s*\(` | `(^\|\n)\s*(?:export\s+)?(function\s+NAME\s*\()` — same |

### 6a. The proof that the fixed slicer is not vacuous

Each injection was applied to the **real** `client2/src/split_registry_row.js`, scored, restored,
and the restore SHA-256-verified against the pre-injection file (`7c97e550f03c8fcd…`).

| # | defect put back | spelling | scorer | clean | with defect |
|---|---|---|---|---|---|
| T1 | `normalizeBands` seq fallback `(i+1)` → `(i)` | `export function` | band_arithmetic | exit 0, 82 assertions, MATCHES | **exit 1 — 3 DIVERGENCES** (`missing_seq_falls_back_to_position` contract `[1,2]` vs client `[0,2]`; `position_fallback_can_collide` `[2,3]` vs `[2,1]`; `invalid_seq_types_fall_back_to_position`) |
| T2 | **the same defect**, `export` keyword removed | `function` | band_arithmetic | — | **exit 1** (identical divergences) |
| T3 | clean source, `export` keyword removed (control) | `function` | band_arithmetic | — | **exit 0** — the tolerance did not break the old spelling |
| T4 | clean source, **pre-tolerance slicer restored** | `export function` | band_arithmetic | — | **exit 2, HARNESS FAILURE: could not extract function 'normalizeBands'** — loud, never silently green |

T1+T2 are the requested both-spellings proof. **T4 is the one that matters most**: without the
fix the slicer does not silently match nothing — it dies at exit 2. So the fix was necessary and
its absence would have been visible, which is the opposite of the vacuity class.

### 6b. The re-pointed scorers each go RED with a defect put back

Same protocol (real file, restore SHA-verified). `legend_map_scope` scores **71** assertions clean.

| # | defect put back in `split_registry_row.js` | kind | legend_map_scope | doe_band_rules |
|---|---|---|---|---|
| D1 | `normalizeBands`: seq fallback `(i+1)`→`(i)` | exported fn | 0 (out of its axis) | — |
| D3 | `serializeStack`: blank → `'0'` | **module-private fn** | **exit 1 — 1 of 71** | — |
| D4 | `LEGEND_PAYLOAD_COLUMNS`: drop `mat_mid` | **const** | **exit 1 — 10 of 70** | 0 |
| D5 | `SPLIT_KEY_SEP`: `'\|'` → `'#'` | **const** | **exit 1 — 1 of 71** | — |
| D6 | `function serializeBands(` re-added | retired writer | — | **exit 2 — "split_registry_row.js has a `serializeBands` again"** |
| D7 | `LEGEND_PAYLOAD_COLUMNS` renamed away | const | **exit 2 — could not extract const** | **exit 2 — "split_registry_row.js lost LEGEND_PAYLOAD_COLUMNS"** |
| D8 | `buildLegendRegistryUpdates`: drop the `vocab` filter | exported fn | **exit 1 — 4 of 71** | — |
| D9 | `registryFingerprint`: return a constant | exported fn | **exit 1 — 2 of 71** | — |
| D10 | `parseLegendRegistryRows`: drop `mat_mid` from the read | exported fn | **exit 1 — 5 of 71** | — |
| D11 | `legendRowSignature`: sign only the first column | exported fn | **exit 1 — 20 of 71** | — |

D3/D4/D5 also prove `extractConst` and the **non-exported** function path are live in the
re-pointed file — the const slicer was not touched and is demonstrably not matching nothing.

## 7. Hostage files — re-measured, not inherited

Enumerated by grepping **the file path** (`client2/src/map_editor.js`) as well as every symbol
name, across `client2/tests/`, `contracts/*/`, `server/tests/` and `client2/scripts/` — the R1
lesson. **5 files hold this seam; 4 were re-pointed and 1 was deliberately left alone.**

| # | file | what changed |
|---|---|---|
| 1 | `contracts/legend_map_scope/client_harness.mjs` | reads `split_registry_row.js` as a second source; the 16 row-normal-form functions and 4 consts slice from it, the 7 stateful functions and 3 consts still slice from `map_editor.js`; `extractFunction` gained the `export` tolerance. **Scenario list, fixture and every assertion unchanged — 71 before, 71 after.** |
| 2 | `contracts/band_arithmetic/client_harness.mjs` | `SRC_EDITOR`→`SRC_ROW` (`normalizeBands` moved); `extractFunction` gained the `export` tolerance. **82 before, 82 after.** |
| 3 | `contracts/doe_band_rules/client_harness.mjs` | the retired-`serializeBands` guard now scans **both** files (a `serializeBands` would now naturally be written beside the other serialisers — scanning only the file it left would leave the guard pointing at empty ground); the `LEGEND_PAYLOAD_COLUMNS` presence check follows the list to the new file. **396 before, 396 after.** |
| 4 | `server/tests/test_install_product_tables.py:683` | `"map_split_registry": ("map_editor.js", "split_key")` → `("split_registry_row.js", "split_key")`. See §7a — this test **skips** on a wrong filename, so it was verified to actually run. |
| 5 | `client2/tests/split_registry_harness.mjs` **[KNOWN_RED, dead since 2026-07-30]** | **not touched.** See below. |

**#5 is a finding, not a re-baseline.** The harness dies at its extraction step because five
symbols it slices (`DEFAULT_LEGEND`, `loadLegend`, `fetchLegendFromServer`,
`maybeOfferLegendMigration`, `loadLegendFromStorage`) no longer exist — `DEFAULT_LEGEND` went to
the server in `95bf072`. After this round it dies **one const earlier**, on `SPLIT_KEY_SEP`,
which moved. Its score is unchanged (`ran 0, failed 0`, no ASSERTIONS line), the runner's
`KNOWN_RED` entry still describes it correctly ("throws at its extraction step"), and reviving it
is a different job than moving code. **`check_harnesses.mjs` was not edited.**

### 7a. The Python test — verified to RUN, and to go RED

⚠️ `test_written_columns_are_all_declared` calls `pytest.skip` when the filename does not exist,
so a wrong re-point reads exactly like a pass. That is why it was checked rather than assumed.
A comment saying so was added beside `WRITERS`.

Run: `conda run -n assy_manager python -m pytest tests/test_install_product_tables.py -q
--no-header -p no:cacheprovider -k written_columns -rs` (from `server/`). The QA lane's full
suite was waited out first; this is the only pytest that ran, and only after
`Get-CimInstance Win32_Process` reported zero live pytest processes.

| # | state | result |
|---|---|---|
| A | **clean, re-pointed** | **2 passed, 0 skipped** — both parametrised tables actually ran |
| B | defect put back: `WRITERS` still says `map_editor.js` | **1 failed** — `AssertionError: no write payload found for map_split_registry: no 'updates:' literal in map_editor.js sets 'split_key'` |
| C | 🔴 the trap: filename typo'd to `split_registry_row_TYPO.js` | **1 passed, 1 skipped** — silently. This is exactly why A was checked for `skipped: 0` rather than for "not failed" |
| D | an undeclared column added to the moved payload literal | **1 failed** — `map_split_registry: client writes ['bogus_undeclared_col'] but product_tables.py does not declare them` |
| E | restored | **2 passed** |

D is the proof that the test is scoring the *moved* literal: the injection went into
`buildLegendRegistryUpdates` inside `split_registry_row.js`, and the static reader found it there.
Both files were restored and verified (`split_registry_row.js` SHA-256 `7c97e550f03c8fcd…`
unchanged; `git diff --numstat` on the Python file shows `8 1`, i.e. only the intended hunk).

## 8. Temporary exports: NONE

`client2/src/split_registry_row.js` exports exactly ten names, and **every one has a real
importer in `map_editor.js` today** (§3a). No mutable state is exported. No accessor/setter pair
was created. No writable binding is shared across the boundary. Nothing is exported "for the
harnesses" — they slice source text, they do not import. Nothing is left for a later round to
clean up: the stateful half stayed with its state, which is where it belongs permanently, not
where it is parked. `map_editor.js` exports nothing, as before. **The commit is independently
deployable**, including the Python test.

## 9. Found while moving — NOT fixed (per the discipline)

**`normalizeBands` silently drops non-object band entries but `parseLegendRegistryRows` treats
that as "no legacy bands".** `normalizeBands` skips any element that is not a plain object
(`if (!b || typeof b !== 'object') return;`). A stored `bands` array of, say, `["3","5"]` therefore
normalises to `[]`, `migrated` stays `null`, `legacyReason` stays `''`, and the row loads as a
plan with **no layer structure and no refusal** — the "screen is fine, the value is wrong" shape,
and the next save replaces the server's real bands with it. Pre-existing at `689ebb9`; moved
verbatim; not touched. Worth a triage round of its own. *(Not scored anywhere today: neither
`contracts/band_arithmetic`'s `sequence_cases` nor `legend_map_scope` feeds a non-object band.)*

## 10. Duplication / primitives check (done before moving anything)

`PRIMITIVES.md` and `DUPLICATION_LEDGER.md` read in full. **Clean — the move creates no third
spelling.** Neither document names any of the 20 moved symbols. `DUPLICATION_LEDGER §1` lists
D-1…D-8; none is implicated (D-8 is the *server-side* `compose_map_id` pair). The move keeps
exactly one implementation of each function and, by keeping `LEGEND_PAYLOAD_COLUMNS` with its
three readers, keeps the "a saved field is necessarily a compared field" property in one file
rather than splitting it across two.

## 11. Complexity budget (UI)

**Net added controls: 0. Net removed: 0.** No panel, mode, modal, confirm, toast or user-visible
string was added, removed or altered. Every Korean UI string in the moved block
(`'서버 미저장'`, the `LEGEND_SAVE_MESSAGE` texts — which did not move) is byte-identical. This
round is invisible to the user.

## 12. Constraints honoured

- No DB write of any kind; no server process touched; no `server/config/*.json` modified.
- `npm run build` **not** run; `client2/dist/**` **not** touched (`dist/map_editor.html` was
  already dirty when this round started and is untouched by it).
- `server/**` touched only for the required test re-point (`test_install_product_tables.py`).
- `client2/scripts/check_harnesses.mjs`, `docs/process/PROJECT_STATUS.md`, `contracts/map_seam/`,
  `contracts/blank_predicate/`, `contracts/config_resolve_report/` — **not touched**.
- Other lanes had uncommitted work in the shared tree throughout
  (`client2/src/transfer_plan.js`, `server/transfer_plan.py`, `server/tests/…`, docs, a new
  harness). **`git add` with explicit paths only — never `-a`/`-A`.** Not pushed.
- One pytest repo-wide: the QA lane's full server suite was live for most of the round and was
  waited out before §7a ran.

## 13. Doc update points (doc-keeper's lane — listed, not edited)

Found by looking up the changed **code paths** in `docs/process/DOC_OWNERSHIP.md`:

- **Row 42 「DOE 저장 분해도」** — names `client2/src/map_editor.js` as *「legend 저장 = 유일한
  기록자」*. That is now split: the **row normal form** (payload, parse, fingerprint, signature) is
  `client2/src/split_registry_row.js`; the **write itself** (`saveLegendToServer`) is still
  `map_editor.js`. Living docs: `spec/MAP_EDITOR_SPEC.md §6`, `guide/CONFIG_GUIDE.md §5.8`,
  `guide/DOE_GUIDE.md`.
- **Row 58 「웨이퍼 맵 에디터」** — code-path list gains `client2/src/split_registry_row.js`.
  Living docs: `map_editor/README.md`, `spec/MAP_EDITOR_SPEC.md §1~§4`.
- **Row 43 「교차 구현 계약 벡터」** — contract count unchanged (6); `legend_map_scope` and
  `band_arithmetic` now name a second client file.
- `docs/architecture/CODE_MAP.md` anchors for the 20 moved symbols (code-mapper's lane).
- `docs/process/DESIGN_TRACKS.md` R2 row — the seam's measured LOC (509) covered both halves;
  the moved half is 340 lines and the rest is not extractable (§2). Lead-PM owned board.

## 14. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. **A seam's LOC number can hide two seams.** "legend-registry, 509 LOC, 13 shared state" was one
   row in the measurement table and turned out to be a pure half (0 state) and a stateful half
   (12 written bindings, 21 write edges from outside). **Before extracting, measure reads and
   writes per FUNCTION, not per seam** — the aggregate hides the split line, and the split line is
   the whole decision.
2. **A briefed landmine is a hypothesis; re-measure it before fixing it.** The briefed `sliceConst`
   export problem did not fire (no const needed exporting); the real one was `extractFunction`, in
   two *different* harnesses. Fixing the briefed one would have shipped an unexercised change and
   left the real one unfixed.
3. **A test that `skip`s on a missing file is a re-point trap.**
   `test_install_product_tables.py::test_written_columns_are_all_declared` skips when its filename
   does not resolve — a typo in a re-point reads exactly like a pass. Any test whose target is a
   path must be shown to have RUN, not just to have not-failed.
