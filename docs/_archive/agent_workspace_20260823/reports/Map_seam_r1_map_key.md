# map_editor.js refactoring — Round 1: the map-key seam

**Author**: map-pm · **Date**: 2026-08-04 · **Base**: `efc4514` (rebased mid-round — client-pm landed the
assertion-floor runner while this work was in progress; every "after" number below is against `efc4514`).

**Verdict: the round is complete and self-contained. NO temporary export remains** — see §6.

---

## 1. What moved

New module **`client2/src/map_key.js`** (158 lines), imported by `client2/src/map_editor.js`.

| symbol | was | now | exported |
|---|---|---|---|
| `CANON_INT_RE` | map_editor.js:665 | map_key.js:37 | no (module-private, as before) |
| `CANON_FLOAT_RE` | map_editor.js:669 | map_key.js:41 | no (module-private, as before) |
| `canonIntString` | map_editor.js:672 | map_key.js:44 | no (module-private, as before) |
| `canonicalKeyValue` | map_editor.js:686 | map_key.js:58 | **yes** |
| `composeMapId` | map_editor.js:712 | map_key.js:84 | **yes** |
| `decomposeMapKey` | map_editor.js:723 | map_key.js:95 | **yes** |
| `canonicalMapKey` | map_editor.js:743 | map_key.js:115 | **yes** |
| `getMapIdFromMeta` | map_editor.js:758 | map_key.js:130 | **yes** |

Source lines 643–786 of `map_editor.js` (144 lines incl. the `[7b]` comment block) were removed verbatim
and are byte-identical in the new file apart from the two edits in §2. `map_editor.js`: **9,632 → 9,496 lines**.

## 2. The only two edits to moved code (both mechanically forced by the move)

1. **`export` on the five symbols map_editor.js calls.** The other three stay module-private, exactly as
   they were — a public surface wider than its importers is a surface nobody holds to anything.
2. **`getMapIdFromMeta(metaDict)` → `getMapIdFromMeta(metaDict, tableSchema)`.** Re-measured on HEAD before
   moving: `tableSchema` is **read 3× inside the function and written 0×** (`.map_key_columns`,
   `.composite_key_source`, `.column_types`); no other seam member touches it. The parameter is named
   `tableSchema` so the function **body is byte-identical** — the harnesses that slice this text and
   evaluate it in a vm see the same code either way. Three call sites now pass it, all in map_editor.js
   and all already holding the live module value at the moment of call:
   `map_editor.js:3925` (`getCurrentMapKey`), `:4887` (`loadExistingMap`), `:5800` (`pushMapData`).
   Null-safety is **unchanged** — a null `tableSchema` still throws exactly where it threw before. That is
   a pre-existing condition, deliberately not fixed here.

## 3. What deliberately did NOT move or change

- **Coordinate math: not one line.** No file under the coordinate contract was opened for edit.
- **`buildKeyFilters`** (map_editor.js:8830) — a *consumer* of `decomposeMapKey`, not a member of the seam.
  It stays and now calls the import. Its contract vector still names `client2/src/map_editor.js`.
- **The two dead module-state declarations `tables` (map_editor.js:38) and `isMouseDown` (:44)** are
  untouched, per the ruling. Both re-confirmed still dead at `efc4514`.
- **No null guard, no defensive default, no rename, no reordering.** Zero behavior change.

## 4. Oracles — before and after

### 4a. `client2/tests/seam_7b_oracle.py` (client vs LIVE `server/map_overlay.py`, key→value)

Run: `conda run -n assy_manager python client2/tests/seam_7b_oracle.py`. A `conda run … pytest server/tests/`
was live in another lane throughout; this is a single script invocation, not a second pytest.

| run | compared | declared-type differential | verdict | exit |
|---|---|---|---|---|
| **before** | 30 vectors (21 canonical + 9 decompose) | 5 | PASS — agree on every vector | 0 |
| **after** | 30 vectors (21 canonical + 9 decompose) | 5 | PASS — agree on every vector | 0 |

**The oracle was shown to fail after the re-point** (a green oracle nobody has seen go red is not evidence).
`SEAM_CLIENT_ROOT` pointed at a copy of the working tree with the declared-type branch of
`canonicalKeyValue` disabled (`if (false && colType === 'number' …)`, i.e. the pre-7b raw behaviour):

- **exit 1, DIVERGENCE — 7 of 30 vectors**, printed key→value:
  `'01'|'1.0'|'007'|'-01'|'+01' number → client keeps the spelling, server says `1`/`1`/`7`/`-1`/`1`;
  `decompose('LOT_01') → client {lot:'LOT',slot:'01'}` vs `server {lot:'LOT',slot:'1'}`;
  `decompose('A_02') → client {lot:'A',slot:'02'}` vs `server {lot:'A',slot:'2'}`.
- A second control: pointing `SEAM_CLIENT_ROOT` at a tree that has `map_editor.js` but **no** `map_key.js`
  exits **2 (ORACLE FAILURE)**, not green. A re-point that silently stopped finding the code is impossible.

### 4b. Stored coordinates — 0 cells moved

Method: **cells carry their own coordinates as values**; no key matching anywhere. Every harness in
`client2/tests/` was run before and after and its **complete stdout compared byte-for-byte**, so each
`dbX`/`dbY` (and each mm/mask/seat) assertion is compared against its recorded literal on both sides.

**Result: byte-identical output for all 22 harnesses and all 6 contracts, with exactly two exceptions,
neither of which is a coordinate:**

| file | before → after | why |
|---|---|---|
| `undeclared_identifier_harness` | `1148 declared, 1182 referenced` → `1136, 1170` | the 8 declarations left the file (and their locals); **`0 undeclared` on both sides**, all 6 checks green |
| `contract config_resolve_report` | `30 files scanned` → `31 files scanned` | it globs `client2/src/*.js`; the new module is the 31st file. Still green |

Coordinate/geometry value assertions covered by that byte-identical set: `valid_die_head_parity_oracle`
17,498 · `valid_die_frame_adoption` 228 · `valid_die_origin_alignment` 153 · `overlay_wafer_mm` 69 ·
`geometry_origin_reseat` 46 · `startxy_probe` 29 · `standard_frame_origin` 19 = **18,042 assertions, all
identical**. `map_key_canonical_harness --emit-7b` (the raw 7b canonicalisation matrix, values not counts)
is also byte-identical.

**Differential — does the fixture set activate the defect axis?** Yes, and the numbers are named rather
than assumed: the canonical harness asserts `drift == 3` ("3 of 5 number spellings were composed wrong
before"), the oracle asserts `declared-type differential == 5` and refuses to pass at 0, and the injected
defect above moved **7 of 30** oracle vectors. None of these is 0.

## 5. Per-harness ASSERTIONS — before / after

Runner: `node client2/scripts/check_harnesses.mjs`. **Both runs exit 0.** Gate/debt split unchanged:
**22 harnesses ― 17 gated, 5 known-red (5 still red, 0 recovered); every gated harness green.**
No `[BLOCKING]`, no `MISSING ASSERTIONS`, no floor complaint in either run.

| harness | before (ran/failed) | after (ran/failed) | Δ |
|---|---|---|---|
| company_roundtrip | 84 / 0 | 84 / 0 | — |
| copy_header_count | 151 / 0 | 151 / 0 | — |
| effort_instrument **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| effort_meter | 131 / 0 | 131 / 0 | — |
| geometry_origin_reseat | 46 / 0 | 46 / 0 | — |
| m4_symbol_extractability_probe | 15 / 0 | 15 / 0 | — |
| **map_key_canonical** ⟵ re-pointed | **116 / 0** | **116 / 0** | — |
| map_key_datalist | 53 / 0 | 53 / 0 | — |
| overlay_wafer_mm | 69 / 0 | 69 / 0 | — |
| push_gate | 15 / 0 | 15 / 0 | — |
| reposition_regime_probe **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| retroactive_view | 263 / 0 | 263 / 0 | — |
| split_registry **[known red]** | no ASSERTIONS line | no ASSERTIONS line | — |
| standard_frame_origin | 19 / 0 | 19 / 0 | — |
| startxy_probe | 29 / 0 | 29 / 0 | — |
| undeclared_identifier | 6 / 0 | 6 / 0 | — |
| **valid_die_authoring [known red]** ⟵ re-pointed | **99 / 1** (19/19 mutants caught) | **99 / 1** (19/19 mutants caught) | — |
| valid_die_frame_adoption **[known red]** | 228 / 42 | 228 / 42 | — |
| valid_die_head_parity_oracle | 17498 / 0 | 17498 / 0 | — |
| valid_die_origin_alignment | 153 / 0 | 153 / 0 | — |
| value_suggest_keys | 94 / 0 | 94 / 0 | — |
| virtual_column_render | 59 / 0 | 59 / 0 | — |

Contracts (`node client2/scripts/check_contracts.mjs`, exit 0 before and after; 6 contracts, no divergence):
**`contracts/map_seam` compared 482 assertions before and 482 after**, `result: MATCHES the contract`.

**Nothing was re-baselined. No recorded expectation, floor, or KNOWN_RED entry was edited**, and
`client2/scripts/check_harnesses.mjs` was not touched (client-pm's lane).

### 5a. The re-pointed scorers were each shown to go RED

The defect from §4a was injected into the real `client2/src/map_key.js`, all three scorers run, then the
file restored (SHA-256 verified identical to the pre-injection copy, and the full gate re-run green):

| scorer | clean | with the defect back in |
|---|---|---|
| `map_key_canonical_harness` | 116 ran / **0** failed | 116 ran / **15** failed |
| `valid_die_authoring_harness` | 99 ran / **1** failed | 99 ran / **2** failed |
| `contracts/map_seam/client_harness.mjs` | exit **0** | exit **1** |

## 6. Temporary exports: NONE

`client2/src/map_key.js` exports exactly five names — `canonicalKeyValue`, `composeMapId`,
`decomposeMapKey`, `canonicalMapKey`, `getMapIdFromMeta` — and **every one of them has a real importer in
`map_editor.js` today**. No mutable state is exported, no accessor pair was created, nothing is exported
"for the harnesses" (they slice source text, they do not import), and nothing is left for a later round to
clean up. `map_editor.js` exports nothing, as before. The commit is independently deployable.

Module-load smoke (possible for the first time, because this is the first importable module carved out):
`import('./client2/src/map_key.js')` resolves in node, exports the five names, and
`getMapIdFromMeta({lot:'LOT',slot:'01'}, {map_key_columns:['lot','slot'], column_types:{lot:'string',slot:'number'}})`
returns `LOT_1`.

## 7. Hostage files re-pointed — and a correction to my own measurement

My measurement (`Map_seam_measurement.md` §4) said **3** hostage files. **The real number is 5.**
`contracts/map_seam/` was under-counted: `vectors.json` names the source file per symbol and
`client_harness.mjs` reads a fixed path dictionary, so both had to move with the seam.

| # | file | what changed |
|---|---|---|
| 1 | `client2/tests/map_key_canonical_harness.mjs` | added a second extractor `K` over `../src/map_key.js`; the 7 x 7b slices now come from it. Slice list and every assertion unchanged. |
| 2 | `client2/tests/valid_die_authoring_harness.mjs` | `fn`/`keyFn` split over the two sources; the 5 x 7b slices and the `reSrc` regex reads come from `map_key.js`. Slice list, fixture and mutation set unchanged. |
| 3 | `client2/tests/seam_7b_oracle.py` | `CLIENT_SRC` → `client2/src/map_key.js` (one line + comment). |
| 4 | `contracts/map_seam/vectors.json` | 6 `client_symbols` + 2 `client_consts` re-pathed; `compose_from_meta.$why` updated to state the new signature. No vector value, case, or expectation changed. |
| 5 | `contracts/map_seam/client_harness.mjs` | `map_key.js` added to `SRC`; `sliceFunction` now tolerates a leading `export ` **and excludes it from the slice** (an `export` statement inside `vm.runInContext` is a SyntaxError); `composeApp` passes the sandbox schema it was already building as the new second argument. |

**Also corrected: `getMapIdFromMeta` was NOT a coverage gap.** My measurement claimed no harness slices it;
`contracts/map_seam` does, as role `compose_from_meta`, and scores it against every `compose_cases` vector.
No assertions were added this round, so nothing here is a coverage claim I have not measured.

Two things I found and did **not** touch, worth knowing before round 2:
- `contracts/map_seam`'s `sliceConst` still anchors `const` at column 0 with no `export` tolerance. It is
  fine today (the two regexes stayed module-private), and I reverted my tolerance edit rather than ship an
  unexercised change. **Round 2 (legend-registry) will hit it** the moment it exports a sliced const
  (`LEGEND_PAYLOAD_COLUMNS`, `LEGEND_SAVE_MESSAGE`, `REGISTRY_SCOPES`, `ZONE_COLUMNS` are all in that shape).
- `client2/tests/valid_die_authoring_harness.mjs`'s one long-standing failure is `[INV-6] resolveValidDie
  runs the chain check before projecting the cells` — a source-text ordering assertion over
  `resolveValidDie` in `map_editor.js`. It failed identically before and after this round; it is untriaged
  debt, not a casualty of the move.

## 8. Duplication / primitives check (done before moving anything)

`PRIMITIVES.md` and `DUPLICATION_LEDGER.md` read in full. **Clean — the move creates no third spelling.**
- `PRIMITIVES §2` ("키 값은 선언 타입으로 캐노니컬화") describes this operation and names the server half;
  the client half was already the single implementation and remains exactly one implementation.
- `DUPLICATION_LEDGER §3` rules this class **out** of the ledger explicitly: a server/client pair that must
  give the same answer is a **seam, not a duplicate** (same ruling as `_split_material` ↔ `splitMaterialId`).
  `D-8` records the two *server-side* `compose_map_id` spellings; nothing on the client is implicated, and
  the client did not gain a copy.

## 9. Complexity budget (UI)

**Net added controls: 0. Net removed: 0.** No panel, mode, modal, confirm, toast or user-visible string was
added, removed or altered. This round is invisible to the user.

## 10. Constraints honoured

- No DB write of any kind; no server process touched; no `server/config/*.json` modified.
- `npm run build` **not** run; `client2/dist/**` **not** touched (`dist/map_editor.html` was already dirty
  when this round started and is untouched by it).
- Not touched: `server/**`, `contracts/blank_predicate/`, `client2/scripts/check_harnesses.mjs`,
  `docs/process/PROJECT_STATUS.md`.
- `git add` with explicit paths only — never `-a`/`-A`. Not pushed.

## 11. Doc update points (doc-keeper's lane — listed, not edited)

Found by looking up my changed **code paths** in `docs/process/DOC_OWNERSHIP.md`, not by enumeration:

- **Row 58 「웨이퍼 맵 에디터」** and **row 74 「범용 맵 오버레이」** name `client2/src/map_editor.js` as the
  code path; `client2/src/map_key.js` now holds the identity half. Living docs:
  `docs/map_editor/README.md`, `docs/spec/MAP_EDITOR_SPEC.md §1~§5`.
- **Row 75 「맵 정렬 메타」** — `getMapIdFromMeta`/`composeMapId` are the client side of what
  `map_meta_registrar` registers; the file reference moves. Living doc: `MAP_EDITOR_SPEC §5.0`.
- **Row 59 「유효 다이 맵(M4)」** cites `canonicalMapKey` usage inside `resolveValidDie` — the *call* stays in
  `map_editor.js`, only the *definition* moved; the row needs the new path for the definition.
- **Row 43 「교차 구현 계약 벡터」** — no count change (still 6 contracts); `map_seam`'s client file list gains
  `client2/src/map_key.js`.
- `docs/architecture/CODE_MAP.md` anchors for the 8 moved symbols (code-mapper's lane).

## 12. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. **The hostage set of a symbol is not `client2/tests/` plus the obvious contract harness.**
   `contracts/<name>/vectors.json` names the **source file per symbol** and is scanned by nobody's grep for
   the function name in the form you expect. Enumerate hostages by grepping the **file path**
   (`client2/src/<file>.js`) as well as each symbol name, across `client2/tests`, `contracts/*`, and
   `server/tests`. My own measurement under-counted this seam 3 → 5 having done only the name scan.
2. **Slicing harnesses are blind to `export`.** Every text-slicer in this repo anchors on
   `function NAME(` or `const NAME =`; three of five accept a leading `export` by accident (no line
   anchor) and two do not. Any extraction round must run each hostage **before** assuming the re-point is
   just a path change, and any tolerance added must exclude `export` from the slice — an `export` statement
   inside `vm.runInContext` is a SyntaxError, so a naive fix turns a green harness into a hard failure.
3. **A byte-for-byte diff of every harness's full stdout is the cheapest 0-cell-movement oracle available.**
   It compares 18k coordinate assertions against their recorded literals with no new machinery, no key
   matching, and no chance of the "matched by physical key" error that once fabricated 183/255 violations.
