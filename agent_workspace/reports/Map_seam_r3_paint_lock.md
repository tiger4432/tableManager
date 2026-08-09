# map_editor.js refactoring — Round 3: the paint-lock seam

**Author**: map-pm · **Date**: 2026-08-04 · **Base**: `ed9cfdb` (HEAD; R2 = `636f867`, rebuild = `ed9cfdb`)

## VERDICT: 🔴 **STOP — the paint-lock seam does not have an extractable boundary this round.**

**No code was changed. TEMPORARY EXPORTS: NONE (nothing was exported at all).**
`client2/src/map_editor.js` is **9,163 lines before and after — measured reduction 0.**

This is the pre-authorized stop outcome, not an abandoned round. The per-function write set below
is the evidence, and §6 proposes where the split line actually belongs. §7–§8 are two defects the
measurement surfaced (one of them is exactly the class the brief told me to look for), reported and
not fixed.

---

## 1. Re-measurement on current HEAD — the seam did not move, only its offsets did

The original measurement (`Map_seam_measurement.md`) named `paint-lock (L60–260)`. On HEAD the block
is **L77–257**: a uniform **+18 line shift** from the two import blocks R1 and R2 added at the top of
the file. **Not one line of the seam's own text changed in R1 or R2** — every function has the same
LOC it had at measurement time, so the "121 LOC" figure survives re-measurement exactly.

| fn | measured L | HEAD L | LOC |
|---|---|---|---|
| `isLockedValue` | 71–78 | **89–96** | 8 |
| `isOverlayLocked` | 81–86 | **99–104** | 6 |
| `paintLockMessage` | 88–90 | **106–108** | 3 |
| `isProtectedFCell` | 93–95 | **111–113** | 3 |
| `applyPaintLockConfig` | 98–110 | **116–128** | 13 |
| `normalizeServedBinding` | 132–142 | **150–160** | 11 |
| `fetchServedBinding` | 148–156 | **166–174** | 9 |
| `fetchPaintRules` | 168–214 | **186–232** | 47 |
| `updatePaintLockIndicator` | 217–231 | **235–249** | 15 |
| `recomputeLockedCells` | 234–239 | **252–257** | 6 |
| | | | **121** |

Contiguous block incl. comments and the four state declarations: **L77–257 = 181 lines.**

## 2. The write set, measured per FUNCTION (the R2 standing rule)

Method: AST parse of `client2/src/map_editor.js` via `vite.parseAst` (oxc), scope-aware walker.
Direct assignment, update expressions, member assignment rooted at the binding, and mutating method
calls are each counted. Same tool as R2, re-run on HEAD; no number was inherited.

| fn | module state READ | WRITTEN | member-MUTATED | outgoing calls |
|---|---|---|---|---|
| `isLockedValue` | `paintLockConfig` | — | — | — |
| `isOverlayLocked` | `paintLockConfig`, **`overlayLayers`** | — | — | — |
| `paintLockMessage` | `paintLockConfig` | — | — | — |
| `isProtectedFCell` | **`loadedFCells`** | — | — | `isOverlayLocked` |
| `applyPaintLockConfig` | `paintLockConfig` | **`paintLockConfig`** | — | — |
| `normalizeServedBinding` | **(none)** | — | — | **(none)** |
| `fetchServedBinding` | `servedBindingCache` | — | **`servedBindingCache`** | `normalizeServedBinding` |
| `fetchPaintRules` | **`selectedTable`**, `paintLockConfig`, `NO_PAINT_LOCK`, `overlayContract`, `servedBindingCache` | **`paintLockConfig`, `overlayContract`** | **`servedBindingCache`** | `applyPaintLockConfig`, `normalizeServedBinding`, `updatePaintLockIndicator`, **`recomputeLockedCells`** |
| `updatePaintLockIndicator` | `paintLockConfig` | — | — | — (DOM) |
| `recomputeLockedCells` | **`gridData`**, `paintLockConfig`, `loadedFCells` | **`loadedFCells`** | `loadedFCells` | **`scheduleRenderGridCanvas`**, `isLockedValue` |

### 2a. The good news the aggregate hid: `paintLockConfig` is **100% seam-owned**

| binding | readers | writers | any edge outside the seam? |
|---|---|---|---|
| **`paintLockConfig`** (let L86) | 7 — `isLockedValue` `isOverlayLocked` `paintLockMessage` `applyPaintLockConfig` `fetchPaintRules` `updatePaintLockIndicator` `recomputeLockedCells` | 2 — `applyPaintLockConfig` `fetchPaintRules` | **NO — every one of the 9 is inside** |
| **`NO_PAINT_LOCK`** (const L85) | 1 — `fetchPaintRules` (+ the L86 initializer) | 0 | **NO** |

This is the exact opposite of R2's legend cluster (21 write edges from outside). If `paintLockConfig`
were the only state involved, this seam would move as cleanly as R1's did.

### 2b. The three clusters that block it — each measured, each real

| binding | inside the seam | **outside the seam** |
|---|---|---|
| **`loadedFCells`** (let L75) | read `isProtectedFCell`; write+mutate `recomputeLockedCells` | **8 readers** (`switchTable` `reseatCellsToStoredCoords` `loadExistingMap` `clearGrid` `snapshotEditorState` `restoreEditorState` `switchTableQuiet` `resolveValidDie`) · **6 writers/mutators** (`reseatCellsToStoredCoords` `restoreEditorState` `switchTable` `loadExistingMap` `clearGrid` `switchTableQuiet`) |
| **`overlayContract`** (let L135) | **written by `fetchPaintRules` (sole writer)** | **2 readers** — `defaultLegendRows`, `declaredLegendRow` (the legend seed, i.e. R2's Half B) |
| **`servedBindingCache`** (const Map L146) | mutated by `fetchServedBinding` **and `fetchPaintRules`** | **1 reader** — `fillColumnDropdowns` at :1281, and it reads **synchronously on purpose** (the comment at :1272–1280 says `switchTable` awaits the round-trip first) |
| `overlayLayers` (let L7259) | read by `isOverlayLocked` | 16 readers / 5 writers / 2 mutators, all outside |
| `gridData` (let L59) | read by `recomputeLockedCells` | 33 readers / 21 writers, all outside |
| `selectedTable` (let L57) | read by `fetchPaintRules` | 23 readers / 3 writers, all outside |

## 3. Why every candidate split line fails — the arithmetic

`fetchPaintRules` is the wall. It is simultaneously (a) the second writer of `paintLockConfig`,
(b) the **sole** writer of `overlayContract`, (c) a co-mutator of `servedBindingCache`, and (d) the
caller of `recomputeLockedCells`, which owns none of the seam's state and writes a binding six
outside functions also write.

**Split A — move the rules and predicates, leave `fetchPaintRules` behind.**
`fetchPaintRules` performs three mutations and one read on `paintLockConfig`:
`{...paintLockConfig, source:'stale'}` · `{...NO_PAINT_LOCK, source:'unsupported'}` ·
`applyPaintLockConfig(cfg)` · `paintLockConfig.enabled`. The module would have to export
**three write operations plus a getter** — an accessor set over mutable state. **STOP condition.**

**Split B — take `fetchPaintRules` with it.**
Then the module needs a setter for `overlayContract` (or must swallow `defaultLegendRows` /
`declaredLegendRow` / `EMPTY_DOE_SEED`, which are the legend seed, not paint-lock), a
read accessor for `servedBindingCache` (for `fillColumnDropdowns`'s deliberate synchronous read),
and `recomputeLockedCells` inverted into a callback parameter. **Exported mutable state + an
accessor pair + an inversion of control. STOP condition, three times over.**

**Split C — move only what is pure over its arguments (the R1/R2 shape).**
The genuinely pure members are `normalizeServedBinding` (11 lines, zero module state) plus
`isLockedValue` / `isOverlayLocked` / `paintLockMessage` / `NO_PAINT_LOCK` (~40 lines) if the
config is threaded as a parameter, R1-style. **I measured the cost and declined it. Three reasons,
in order of weight:**

1. **It makes the call sites worse, which is the opposite of the round's purpose.**
   `isOverlayLocked(key)` becomes `isOverlayLocked(key, paintLockConfig, overlayLayers)` and
   `isLockedValue(val)` becomes `isLockedValue(val, paintLockConfig)`. R1 added one parameter to one
   function at three call sites; R2 added none. This adds three parameters across two predicates that
   twelve edit paths gate on.
2. **It takes seven green enforced harnesses hostage for a 0.5% reduction.** `isProtectedFCell` is
   sliced and run in a vm by `company_roundtrip` (84) · `copy_header_count` (151) ·
   `geometry_origin_reseat` (46) · `standard_frame_origin` (19) · `startxy_probe` (29) ·
   `valid_die_frame_adoption` (228, known-red) · `valid_die_origin_alignment` (153), each stubbing
   `isOverlayLocked: () => false`. Adding arguments to that call makes the **arguments** evaluate in
   the sandbox: `paintLockConfig` and `overlayLayers` must be declared in all seven or the slice
   throws `ReferenceError`. Only `valid_die_origin_alignment` declares `paintLockConfig` today
   (`:195`), none declares `overlayLayers`. Separately, `standard_frame_origin` and `startxy_probe`
   slice and run `loadExistingMap`, which is the second `isLockedValue` call site (`:4862`).
3. **~50 of 9,163 lines.** Under the fixed cost of seven harness re-points plus their red-proofs,
   this is churn, not a boundary.

**Not shipping Split C is the same judgement I made twice before**: R1 reverted an unexercised
slicer tolerance, R2 declined one when the briefed landmine did not fire. The rule generalises —
**do not ship a change whose only justification is that the round needed to produce a diff.**

## 4. Oracles — before and after (identical by construction, and verified)

No file was modified, so "after" is "before". Both were nevertheless run so that the round records
the tree's actual state and proves it did not disturb the concurrent lanes.

### 4a. `node client2/scripts/check_harnesses.mjs` — **exit 0**

**23 harnesses ― 18 gated, 5 known-red (5 still red, 0 recovered); every gated harness green.**
No `[BLOCKING]`, no `MISSING ASSERTIONS`, no floor complaint. This matches the briefed baseline
exactly (23 / 18 / 5 / exit 0, `availability_gross_marker` landed in `784a07d`).

| harness | before (ran/failed) | after (ran/failed) | Δ |
|---|---|---|---|
| availability_gross_marker | 48 / 0 | 48 / 0 | — |
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
| split_registry **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| standard_frame_origin | 19 / 0 | 19 / 0 | — |
| startxy_probe | 29 / 0 | 29 / 0 | — |
| undeclared_identifier | 6 / 0 | 6 / 0 | — |
| valid_die_authoring **[known red]** | 99 / 1 | 99 / 1 | — |
| valid_die_frame_adoption **[known red]** | 228 / 42 | 228 / 42 | — |
| valid_die_head_parity_oracle | 17498 / 0 | 17498 / 0 | — |
| valid_die_origin_alignment | 153 / 0 | 153 / 0 | — |
| value_suggest_keys | 94 / 0 | 94 / 0 | — |
| virtual_column_render | 59 / 0 | 59 / 0 | — |

**No floor, no `KNOWN_RED` entry, no recorded expectation was edited.**
`client2/scripts/check_harnesses.mjs` was **not touched** (client-pm's lane).

### 4b. Contracts — `node client2/scripts/check_contracts.mjs`, **exit 0**

`band_arithmetic` · `blank_predicate` · `config_resolve_report` · `doe_band_rules` ·
`legend_map_scope` · `map_seam` — **6 contracts, no divergence.**

### 4c. `client2/tests/undeclared_identifier_harness.mjs`

`PASS -- 6 passed, 0 failed (map_editor.js: 1109 declared, 1143 referenced, **0 undeclared**)`,
`ASSERTIONS 6 0`. Identical to R2's after-state (1109 / 1143), i.e. nothing has drifted since.

### 4d. Stored coordinates — 0 cells moved

**Trivially, and stated as such rather than dressed up**: no source file was modified, so the
coordinate-carrying assertions inside the byte-identical harness set — `valid_die_head_parity_oracle`
17,498 · `valid_die_frame_adoption` 228 · `valid_die_origin_alignment` 153 · `overlay_wafer_mm` 69 ·
`geometry_origin_reseat` 46 · `startxy_probe` 29 · `standard_frame_origin` 19 = **18,042
value-for-value assertions** — are compared against the same recorded literals they were before.
No re-pointed scorer exists this round, so there is no red-proof to show: **a round that changed
nothing has no scorer whose liveness this round could have broken.**

## 5. What deliberately did NOT change

- **Nothing.** No file in `client2/`, `contracts/`, `server/` or `docs/` was edited.
- Board item 19 (`degrade()`'s "last known value" is `{enabled:false}` at cold start, so a
  first-fetch failure leaves all twelve enforcement points open) is **verified still present and
  unchanged** at `map_editor.js:189–197`: `paintLockConfig` initialises to `{...NO_PAINT_LOCK,
  source:'default'}` (`enabled:false`) at `:86`, and `degrade` only stamps `source:'stale'` on it.
  Not fixed, per the brief.
- The dead module state `tables` (`:56`) and `isMouseDown` (`:62`) — untouched, per the ruling. Both
  re-confirmed still dead at `ed9cfdb`.
- No coordinate math was opened.

## 6. Where the split line actually belongs (for lead-PM adjudication)

**Recommendation: do not re-attempt paint-lock as a standalone seam. Fold it into the same
orchestrator judgement R2 recommended for the legend cluster.**

The reason is structural and, I think, the most useful thing this round produced:

> After R1 (a pure leaf) and R2 (a pure row normal form), **every remaining "cheap" seam on the
> board is a cache-owning IO seam whose cache is invalidated by an orchestrator.** The cheap seams
> were cheap because they were *pure*, and the pure ones are now gone.

I verified this is not specific to paint-lock by measuring the next seam in the board's order,
**`datalist-suggest`** (R4, "0 out calls · 3 shared state · 1 hostage" — the cheapest row left):

| binding | inside | outside |
|---|---|---|
| `mapKeyListCache` (const Map L8232) | `populateMapKeyDatalist` | **`switchTable`:1154 and `pushMapData`:5609 call `mapKeyListCache.delete(...)` inline** |
| `columnValueTruncated` (const Set L8297) | `dropColumnValueCache`, `populateColumnValueDatalist` | **`onMetaInputSuggest`:8399 reads it**, and that function also reads `selectedTable` (23 readers / 3 writers outside) so it cannot move |
| `el` (DOM registry) | `populateValidDieRefList`, `populateOverlayKeyList` | written by `initDOMElements` |

Same shape, same wall: a private cache poked by an orchestrator. Extracting it needs an exported
invalidator plus an exported predicate — an accessor pair. Its pure residue (`fillDatalist`,
`claimListFill`, `colValueKey`, `canReuseComplete`, `markSuggestState`) is ~35 lines.

**Two concrete options for the board, in preference order:**

1. **Revisit the ⓐ/ⓑ decision now rather than after R8.** The premise of ⓐ was "eight cheap moves
   build the evidence, and the orchestrators get thinner meanwhile." Two rounds landed **−469 lines
   (9,632 → 9,163, 4.9%)** and the method is proven. But the evidence R1+R2 produced is that the
   file's remaining seams are **not** separable from their state, which is the ⓑ question. Rounds 3–7
   would each land 35–60 lines at the cost of 5–7 harness re-points, and would leave the
   orchestrators exactly as thick. **Recommend re-adjudicating ⓐ vs ⓑ against these two measurements
   rather than spending five rounds to reach the same conclusion.**
2. **If incremental rounds continue, change the unit from "seam" to "cluster + its writers."** The
   line that works is not around a *concern* but around a *binding and everyone who writes it*.
   For paint-lock that cluster is `{paintLockConfig, overlayContract, servedBindingCache,
   loadedFCells}` + `fetchPaintRules` + `recomputeLockedCells` + `switchTable`/`loadExistingMap`/
   `clearGrid`/`restoreEditorState`/`switchTableQuiet` — i.e. the map-load orchestrator again.

## 7. 🔴 Duplication finding — the seam DOES contain a client copy of a server declaration, and it is the class the brief predicted

The brief asked me to check this. It is there, and it is worse than a copy: **the server's declared
`message` is fetched, stored, and never shown to anyone, while the sentence the user actually sees
is a client hardcode.**

Three spellings of one declared rule exist:

| # | where | text | who sees it |
|---|---|---|---|
| 1 | `server/config/map_overlay_config.json` `paint_lock["*"].message` — **the declaration** | `이 셀은 잠금 값이라 페인팅할 수 없습니다.` | **nobody** |
| 1b | `server/map_overlay.py:1447` — the server's own fallback when the key is absent | same string | **nobody** |
| 2 | `client2/src/map_editor.js:107` `paintLockMessage()` fallback | `이 좌표는 잠금 규칙에 의해 칠할 수 없습니다.` | **nobody — see §8** |
| 3 | `client2/src/map_editor.js:248` `updatePaintLockIndicator`'s tooltip — **hardcoded, ignores `paintLockConfig.message` entirely** | `이 값의 셀은 편집할 수 없습니다 (서버 선언).` | **this is the only one a user ever reads** |

`paintLockConfig.message` has **exactly one reader in the whole repo** (`paintLockMessage`, line 107)
and that function has **zero callers** (verified by a repo-wide grep excluding `.git`; the only other
hits are my own R0 measurement report). So an operator who edits `message` in
`map_overlay_config.json` changes nothing on any screen, and the tooltip they cannot edit is the one
that shows.

This is precisely `DUPLICATION_LEDGER` **D-5**'s class — *"두 개이고, 둘째는 답이 다르며, 아무도 안
부른다"* — and D-5's own warning applies verbatim: the danger is not the dead copy, it is that the
next person calls it, and then the wrong sentence ships silently. **Ledger candidate; not fixed
here.** (`PRIMITIVES §서버 선언 서빙` at line 175–176 names `overlayContract` as this seam's
already-correct example of the same rule — the lock message is the arm that was missed.)

**Note for whoever fixes it**: the twelve `isProtectedFCell` enforcement points are all **silent**
(`:985 :3198 :3583 :4380 :5149 :5798 :5835 :5857 :6653 :8458 :8459 :8991` — every one is a bare
`return`/`continue`, and `importOverlayToGrid`:8991 only aggregates a count into an existing toast).
So "wire the declared message up" is a **UI change**, not a cleanup, and it needs the complexity
budget applied. The zero-risk half — deleting the dead `paintLockMessage` or pointing the tooltip at
the declared string — is separable from it.

## 8. Second finding — `paintLockMessage` is dead code

`client2/src/map_editor.js:106–108`. Zero callers repo-wide. It is the only reader of a field the
server declares. It has been dead since the indicator chip took over the user-facing text.
**Reported, not deleted** — deleting it is a one-line change but it is a change, and this round's
contract is zero behavior change. It also should not be deleted in isolation from §7's decision,
because if the declared message is wired up, this is the function that does it.

## 9. Duplication / primitives check (done before any move was attempted)

`PRIMITIVES.md` and `DUPLICATION_LEDGER.md` read. Since nothing moved, no third spelling was created.
Two entries are load-bearing for this round and are cited above: `PRIMITIVES` line 175–176 (server
declaration served, never copied client-side — names `overlayContract` and the `95bf072` default-legend
precedent) and `DUPLICATION_LEDGER` D-5 (the "second one answers differently and nobody calls it"
class, which §7 is a new instance of).

## 10. Complexity budget (UI)

**Net added controls: 0. Net removed: 0.** No panel, mode, modal, confirm, toast or user-visible
string was added, removed or altered. Every Korean UI string in the seam is untouched. This round is
invisible to the user — necessarily, since it changed nothing.

## 11. Constraints honoured

- **No file was written** in `client2/`, `contracts/`, `server/`, or `docs/`. Nothing to commit; **no
  commit was made and nothing was pushed.** `git add` was not invoked.
- No DB write of any kind; no server process touched; `server/config/*.json` **read only** (the
  `paint_lock` declaration in §7 was read with a `json.load`, not modified).
- `npm run build` **not** run; `client2/dist/**` **not** touched.
- `docs/process/PROJECT_STATUS.md` and `docs/process/DESIGN_TRACKS.md` **not** touched — §6's
  proposal is for the lead PM to act on, per the board-ownership rule.
- No pytest was run (nothing in `server/tests` needed re-pointing).

## 12. Doc update points (doc-keeper's lane — listed, not edited)

Found by looking up the changed code paths in `docs/process/DOC_OWNERSHIP.md`. **No code path
changed, so there are no move-driven doc updates.** The two findings do land on owned rows:

- **Row 74 「범용 맵 오버레이(맵 인프라)」** — names `client2/src/map_editor.js` +
  `config/map_overlay_config.json`. Living doc `spec/MAP_EDITOR_SPEC §5`; setting-side
  `guide/config/map_overlay_config.md`. **§7 belongs here**: the `paint_lock.message` key is
  documented as a declaration but has no consumer, so any guide text telling an operator to set it
  is currently false.
- **Row 73 「설정 전반」** → `guide/config/map_overlay_config.md` key dictionary — same key.
- `docs/architecture/DUPLICATION_LEDGER.md` — §7 is a new **D-9** candidate (lead-PM adjudicated;
  the ledger's own §0-bis entry criteria apply).
- Row 57 「웨이퍼 맵 에디터」's rule *「경계는 「순수한가」로 긋는다」* is confirmed by this round and needs
  no edit — it already says the stateful orchestration stays **permanently**.

## 13. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. **A binding being 100%-owned by a seam does not make the seam extractable.** `paintLockConfig` had
   9 edges and all 9 were inside — the cleanest ownership number in the file — and the seam still
   could not move, because its *second writer* was also the sole writer of two other clusters. **Do
   not stop the measurement at the seam's own state; measure what the seam's writers ALSO write.**
   The blocking cluster is never the one the seam is named after.
2. **Adding an argument is cheap in the source and expensive in the harnesses, and the cost scales
   with slices, not call sites.** Threading `paintLockConfig` into `isOverlayLocked` touches **one**
   call site and **seven** vm sandboxes, because arguments are evaluated inside the slice: a stubbed
   callee does not protect you, the *identifier* must be declared. **Count vm sandboxes that slice
   the CALLER, not call sites, before pricing a signature change.**
3. **When the cheap seams run out, that is a measurement, and it is the answer to a bigger question.**
   Two rounds of "extract the pure part" exhausted the pure parts; both remaining candidates measured
   the same shape (a private cache invalidated by an orchestrator). That finding is worth more to the
   ⓐ/ⓑ decision than five more 40-line rounds would be. **A round that produces a decisive
   measurement and no diff is a round that did its job.**
