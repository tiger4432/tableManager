# Server — M2.6 rebind of `transfer_plan.py` to the `bands` contract

**Agent:** server-pm · **Date:** 2026-07-27 · **Queue item:** 1
**Suite:** 602 passed / 0 failed (baseline 576; net +26 tests)
**Status:** fix round complete — see §9 for the response to the NO-GO review.

---

## 1. What changed

| File | Change | Tracked? |
|---|---|---|
| `server/transfer_plan.py` | Plan store rebound to `map_split_registry`; quantities derived, not read | yes |
| `server/tests/test_transfer_plan.py` | Validate section rewritten for the `bands` model | yes |
| `server/config/transfer_plan_config.json.sample` | `doe`/`doe_source` → `registry` + `material_identity` | yes |
| `server/config/transfer_plan_config.json` | same, applied to live | **no — gitignored** |
| `server/config/table_config.json` | `knobs`+`bands` declared via `install_product_tables.py` | **no — gitignored** |
| `server/scripts/setup_transfer_plan_indexes.py` | added `map_split_registry (ref_table, map_key)` | yes |

`docs/process/PROJECT_STATUS.md` also shows as modified — that is the lead PM's dispatch edit, not mine. Untouched.

### Config binding (live and `.sample` are byte-equivalent apart from `__comment`)

```json
"plan_store": {
  "registry": { "table": "map_split_registry",
                "columns": {"ref_table":"ref_table","map_key":"map_key",
                            "value":"value","bands":"bands"} },
  "material_identity": { "compose": ["lot","slot"], "separator": "_" }
}
```

`bands` is a **required** role. If it is undeclared, `validate` returns 404 rather than reading an
empty plan — the failure mode this module exists to prevent.

### Derivation (mirrors `client2/src/transfer_plan.js:171-205`)

`prevTo(i)` = `to` of the nearest **preceding array element that has one**, 0 before the first ·
`layers = to − prevTo` · `total = painted(value) × layers` · `share = ceil(total / len(materials))`.
Array position carries order; `seq` is identity only and is never sorted on or renumbered.

### `install_product_tables.py` diff (dry run, before apply)

```
[DRIFT] map_split_registry  3 difference(s)  (BLOCKING)
          missing  column_types.knobs   product wants "string"
          missing  column_types.bands   product wants "string"
          changed  display_columns  (product adds knobs, bands before eventtime)
```

Applied with `--apply --overwrite-drift`; backup at `table_config.json.bak.20260727-094410`.
Re-scan reports all 4 product tables matching, 0 drift.

---

## 2. Warning-type disposition

| Type | Disposition |
|---|---|
| `layer_coverage_gap` | **removed.** `from(i) = prevTo(i)+1` makes coverage contiguous by construction, so a gap is no longer expressible. Client grep: the only reference is `__HELD_WARN_SEVERITY` in `client2/src/transfer_plan.js:1086` — held/dead code (`eslint-disable no-unused-vars`), and `grep -c "transfer-plan/validate"` over `client2/dist/assets/*.js` is **0 in every bundle**. Nothing live consumes it. A regression test asserts the constant stays gone. |
| `layer_range_invalid` | **repurposed** to "band structure that cannot yield a layer count", with a `reason` field: `unreadable` (bands blob unparseable), `incomplete` (`to` blank mid-edit), `not_increasing` (`to` ≤ previous `to`). No client reference existed at all, even in held code. |

---

## 3. Invariants

- `availability_checked` is now a single expression: `any_doe_checked` — true only when at least one
  demand reached a real comparison. Unknown stage, empty plan, all-unresolvable materials, all-defective
  bands and truncated reads all collapse into `unverified` through that one line instead of separate guards.
  **This is a tightening**: previously an empty plan returned `status: "ok"`.
- Response key set unchanged: `ref_table, map_key, stage, map_status, doe_count, painted_values,
  status, availability_checked, warnings` — asserted against live data in §4.
- `doe_count` now means **values carrying at least one band** (M2.6 unit), not band rows.
  A colour-only legend row is not yet a DOE and raises no `doe_value_unpainted` noise.
- `map_key` is still never parsed — `map_overlay.build_key_filters` only.
- Config still snapshotted once per request and passed down.
- Caps: `MAX_DOE_PER_PLAN` 500 rows, `MAX_SOURCES_PER_DOE` 64 materials/band, new
  `MAX_BANDS_PER_PLAN` 2000. Truncation surfaces `result_truncated` **and** forces `unverified`.
- No test writes to the live tree; `_seed_plan` uses the `tp_test_*` fixture table.

---

## 4. Verified by running (vs. reasoned)

**Ran:**
- Full suite before (576) and after (584), plus the module suite (62 passed).
- `install_product_tables.py` dry run, then apply; re-scan clean.
- `information_schema.columns`: `map_split_registry` physically has `knobs` and `bands`,
  appended after `eventtime` (the ALTER signature).
- `pg_indexes`: `map_split_registry` had **no** `(ref_table, map_key)` index while the retired
  `map_doe` did. Added and applied.
- New `validate_plan` against live PostgreSQL on three real plans — key set asserted, no spurious
  warnings on the 102 existing rows (all have `bands IS NULL`, correctly read as "no DOE yet",
  not as "unreadable").
- Two independent probes of the config-watcher path (see §5).

**Reasoned, not run:** the client's rendering of the new `reason` field — the validate endpoint has
no live client consumer yet, so there is nothing to render it.

---

## 5. Restart: required for the code, NOT for the columns

The two questions have different answers and the distinction matters.

- **Physical columns — no restart needed. Already applied.** The web server's config watcher fired
  on the installer's write and ran `sync_dynamic_tables_schema`. Proof: `GET /tables/map_split_registry/schema`
  on the running server (booted 05:32, when `bands` did not exist) returns `knobs` and `bands`;
  that route reads the `crud.TABLE_CONFIG` **singleton** (`main.py:1608`), which only the watcher
  updates. `information_schema` confirms the physical columns.
- **Code — restart required.** The running uvicorn holds the pre-change `transfer_plan.py`.
  Measured: `GET /api/transfer-plan/validate?ref_table=dt_map&map_key=1H` → **404
  `plan store is not configured (plan_store.doe unresolved)`**, and `/stages` → `plan_store: {doe: missing}`.
  **The DOE panel stays broken until the web server process is restarted.**

### Observability gap found while verifying

The watcher's own log lines are **not landing in `server/server.log`** for the web server. A
byte-identical re-save of `table_config.json` at 09:47:36 produced `Configuration change detected`
in `watcher.log` (from `run_watcher.py`, which passes `engine=None` and issues no DDL) but **nothing**
in `server.log`, `chain_worker.log` or `graph_sync.log` — even though `server.log` was live
(broadcasts at 09:47:04). Separately, `sync_dynamic_tables_schema` uses `print()`, not the logger,
so its `[Schema Sync] Altering table ...` output is captured nowhere. The DDL that production
depends on is invisible after the fact. This is the same class as B3 worker-log wiring.

---

## 6. Where I disagree with / correct the brief

1. **`prevTo` skips blank bands.** The brief said "`prevTo(i)` = `to` of the preceding array element".
   The client (authoritative, `transfer_plan.js:178-184`) walks *back past* elements whose `to` is
   blank to the nearest one that has a value. I mirrored the client. It matters whenever a
   mid-edit band sits between two filled ones.
2. **Material split conventions genuinely disagree, and I followed the client.**
   `map_overlay.build_key_filters` has the **last** field absorb extra separators; the client's
   `splitMaterialId` (`lastIndexOf('_')`) has the **first** absorb. For `TAPE-A_01` both agree;
   for `LOT_A_01` they do not. The panel and `validate` call the same `source-summary` endpoint for
   the same material, so matching the client is what keeps one screen from showing two availability
   numbers. Flagged in the code comment. This is PRIMITIVES §3 "do not implement a derivation twice"
   — worth a decision on whether to unify later.
3. **`/api/transfer-plan/validate` has no live consumer.** All client code that read it is
   `__held_*` and absent from every built bundle. The endpoint is currently server-only; whoever
   re-wires it should be told the `reason` field exists.
4. **Mid-edit blank `to` does emit a warning** (`reason: "incomplete"`). The brief said a blank `to`
   "is not an error" — it is not treated as one (no rejection, no 500, layers 0), but staying
   silent would let an unchecked band sit inside a plan that otherwise looks clean. Reversible if
   you consider it too noisy during editing.

---

## 7. Follow-ups (not done — out of scope)

1. **`docs/guide/CONFIG_GUIDE.md` is now stale** — lines 200, 448-479 document
   `plan_store.{doe,doe_source}` and tell operators the `.sample` matches. doc-keeper's file; I did
   not edit it.
2. **Live registry has 102 rows, none with bands** — client writes were dropped until 09:44. No data
   migration is possible or needed; users re-enter bands in the panel. Pre-existing `map_doe` (9 rows)
   / `map_doe_source` (8 rows) content is now unreachable by code.
3. **`dev_env/config/{table_config,transfer_plan_config}.json`** still carry the old bindings — the
   isolated env will 404 on validate until re-snapshotted.
4. `map_doe` / `map_doe_source` physical DROP still awaits user approval; their index entries are
   flagged in `setup_transfer_plan_indexes.py` to be removed with them.

## 8. History draft

> **M2.6 server rebind — the plan store becomes one table.** `transfer_plan.py` now reads
> `map_split_registry.bands` instead of the retired `map_doe`/`map_doe_source`, and derives every
> quantity (`layers = to − prevTo`, `total = painted × layers`, `share = ceil(total/materials)`)
> mirroring `client2/src/transfer_plan.js` rather than reading stored `qty_total`/`qty`. Material
> IDs stay opaque; resolving one to a source `(lot, slot)` is a declared rule
> (`plan_store.material_identity`) and an unresolvable material is reported, never guessed.
> `layer_coverage_gap` removed (contiguous derivation makes a gap inexpressible);
> `layer_range_invalid` repurposed to band-structure defects with a `reason`. `availability_checked`
> reduced to one expression so an empty or unresolvable plan can no longer return `ok`.
> `knobs`/`bands` declared in the live `table_config.json` via `install_product_tables.py`;
> the config watcher applied the ALTER without a restart, but the web server must be restarted to
> pick up the code. Suite 602 passed.

---

# 9. Fix round — response to the NO-GO review (2026-07-27)

**Suite: 602 passed / 0 failed** (was 584; +18 tests this round, +26 vs the 576 baseline).

## B1 — duplicate `seq` disabling the over-allocation guard: FIXED

Two changes, because either alone is insufficient.

1. **The counter no longer depends on labels.** `source_alloc[...]` carries `demands` (a count)
   separately from `labels` (display), and the gate is `acc["demands"] < 2`. Response gains
   `demand_count`.
2. **`seq` is made unique on parse** (`_assign_band_seqs`), mirroring the panel's rule, so the
   *display* collision goes away too. This also removes the positional-fallback collision
   (`seq: 2` plus a missing `seq` at index 1 both proposing `#2`).

Tests: `test_duplicate_seq_does_not_disable_the_overallocation_guard` (two demands of 2 against
available 2 — neither individually short, so only the aggregate can catch it) and
`test_duplicate_seq_large_plan_still_reports_shortage`.

## B2 — an incomplete `painted` read zeroing every quantity: FIXED

`_painted_values` returns `(dict, status, truncated)` and fetches `cap + 1` to detect truncation.
`painted_reliable` gates the entire demand derivation, so:

- new `painted_unavailable` warning carrying `map_status`, `truncated`, `cap`;
- `availability_checked` false, `status: unverified`;
- **`undefined_doe_value` and `doe_value_unpainted` are suppressed** — both assert a fact about
  painting, and we do not have the counts to assert it.

Your framing that this was a regression introduced by deriving rather than reading is correct and
is now recorded in the code comment at the constant.

Tests: `test_unreadable_painted_never_reads_as_zero_demand` (with a control run proving shortage
fires normally first), `test_truncated_painted_read_is_a_checked_failure`.

## B3 — `_band_to`, and the test that could not fail: FIXED, contract narrowed

`_band_to` returns `(value, state)` with `state` in `ok | blank | invalid`, implementing the spec
as written — **not** a port of JS coercion. `_prev_to` stops only on `ok`, so **blank and invalid
are skipped identically**. That is the structural fix; `invalid` is still reported as
`layer_range_invalid(reason="unreadable")`.

**Shared vector file: `contracts/band_arithmetic/vectors.json`**
**Client harness: `contracts/band_arithmetic/client_harness.mjs`**

- pytest consumes the vectors in four tests (`_band_to`, sequence arithmetic, seq normalization,
  material split). These pass.
- The harness slices the client's private functions out of `transfer_plan.js` and `map_editor.js`
  by brace matching and evaluates them in a `vm` sandbox. **Nothing under `client2/` was touched.**
  It **fails loudly** (exit 2, "could not extract") if a function is renamed or reshaped — a
  harness that silently passes is the defect being corrected here.
- Current result: **111 assertions, 27 divergences** — `to_cases` 10, `sequence` 11,
  `material_split` 6. Including the motivating case: `[10, "  ", 20]` gives 10 layers under the
  contract and 20 in the client. Run `node contracts/band_arithmetic/client_harness.mjs`.

One vector of mine was wrong and the client was right (`missing_seq_falls_back_to_position` expects
`[1, 2]`, not `[1, 3]`) — the harness caught it, which is some evidence it works.

`test_layer_coverage_gap_warning_is_gone` is replaced by
`test_removed_coverage_gap_stays_removed_as_behaviour`: it keeps the `hasattr` line but adds the
behavioural claim — a plan with a blank band between two filled ones produces no coverage warning
under any type name, and the last band is pinned at 6 layers (counting from 4, not from 1).

## Also-fix items

| Item | Done |
|---|---|
| `OverflowError` to 500 | `_band_to` checks integer magnitude before any `float()`; `abs > MAX_LAYER (2^53)` is invalid. `test_huge_int_does_not_abort_the_whole_plan` proves one corrupt value no longer kills the others' verification. |
| One non-object element voiding the value | Dropped, deriving continues (matches the panel). |
| Unreadable value also claiming "no definition" | `undefined_doe_value` subtracts `unreadable`. `test_unreadable_value_does_not_also_claim_no_definition`. |
| `MAX_SOURCES_PER_DOE` reporting the wrong knob | Truncation is a list of `(role, cap)`; roles `plan_registry` / `bands` / `materials` / `demands` / `distinct_sources` report separately and are no longer conflated. |
| Material split | Refuses on no separator, leading/trailing separator, separator-only; both fields trimmed. Decision stated in the docstring, the vectors, and `PRIMITIVES.md`. The old test comment claiming client equivalence is gone; the code comment now says "same direction only, deliberately different on unresolvable input". |
| Fan-out | New `MAX_DEMANDS_PER_PLAN` (5000, checked inside the material loop too), `MAX_SOURCES_PER_PLAN` (200 distinct summaries), `MAX_BANDS_BLOB_BYTES` (256 KB, checked **before** `json.loads`), `MAX_LAYER`. `_get_summary` caches failures — `test_failing_source_is_queried_once_not_once_per_demand` asserts exactly one call for three demands. |
| `ORDER BY` on both `.limit()` calls | Registry ordered by `value`; painted group-by ordered by the value column. |
| `not_increasing` wording | Now says the *next* band's demand is over-counted, naming the stack-overflow consequence. |
| `main.py` route docstring | No longer advertises STACK coverage; says `plan_store.registry`. |

### New installer flag: `--sync-comments`

The installer treats `__comment` as an annotation and never rewrites it — correct by default, since
an operator may have annotated it, but it meant the live file kept telling operators that
`plan_store.doe` points at `map_doe`. `strict=True` (whole-entry comparison) already existed for
`--sample`; `--sync-comments` exposes it for a live config. Opt-in, still requires
`--overwrite-drift`, and all existing safety (dry-run default, backup, byte re-verify of untouched
members, restore on mismatch) is unchanged because `strict` only affects `evaluate()`.

Applied: `map_doe` and `map_doe_source` now carry the DEPRECATED banner, and `wafer_map_metadata`
gained the `__comment` it was missing entirely. Backup at `table_config.json.bak.20260727-103736`.
Two tests added, one asserting site-owned entries stay byte-identical through this path.

## Cap coverage (was: none)

`test_registry_row_cap_is_surfaced`, `test_band_cap_is_surfaced`,
`test_material_cap_reports_materials_not_bands`,
`test_demand_and_distinct_source_caps_bound_the_fanout`,
`test_truncated_painted_read_is_a_checked_failure`, `test_oversized_blob_is_refused_before_parsing`.
Every cap surfaces `result_truncated` with its own role and forces `unverified`.

## Two things worth your attention

1. **A caught gap in my own fix.** `MAX_DEMANDS_PER_PLAN` was initially checked only per band, so
   one band could still emit 64 demands past the cap. `test_demand_and_distinct_source_caps_bound_the_fanout`
   failed and I moved the check inside the material loop. The cap tests you asked for found a real
   hole on their first run.
2. **I wrote an `or True` into a first draft of the B1 test** (`assert x == 4 and y == 2 or True`),
   which would have made that assertion unfailable — precisely the defect class this round is
   about. It is gone; the test now pins `required_total == 4`, `available == 2`,
   `demand_count == 2`. Noting it because the pattern is evidently easy to produce and worth
   watching for in review.

## Re-verified after the fix round

- Full suite 602/0, run three times across the round.
- New `validate_plan` against live PostgreSQL on the same three real plans: unchanged behaviour,
  response key set still asserted.
- Live and `.sample` `plan_store` still identical; live `table_config.json` still declares
  `knobs`/`bands`; nothing under `server/config/` is tracked by git.

## Still open

- **The web server still needs a restart** to load the new module — it currently 404s with
  `plan_store.doe unresolved`. The physical columns need nothing.
- Client-side divergences are map-pm's, against the vector file above.
- `CONFIG_GUIDE.md` / `CODE_MAP.md` left to you as instructed.

---

# 10. Shrink round — constrain the writer, stop pinning garbage (2026-07-27)

**pytest 608 passed / 0 failed · harness 110 assertions / 0 divergences** (was 604 / 185).

## The write path really is constrained — verified, not taken on trust

The panel's end-layer field is `<input type="number" min="1" step="1">`, and its change handler
(`transfer_plan.js:691-700`) runs the typed text through `bandToState` and **refuses** anything
invalid before it can reach state. `serializeBands` then writes `to` as `null` or a number.
So `'0x10'`, `'1_0'`, `'1e3'`, `true`, `[]` — and out-of-range magnitudes — cannot arrive through
the panel at all. The 25-entry coercion table was pinning agreement on values that cannot be stored.

## What the contract is now

| group | before | after |
|---|---|---|
| `to_cases` | 25 | **6** |
| `normalization_cases` | 12 | **5** |
| `materials_cases` | 10 | **6** |
| `sequence_cases` | 7 | 7 (untouched) |
| `material_split_cases` | 10 | 10 (untouched) |
| `$known_divergences` | present | **removed** |

`to_cases` is now `null`, `absent_key`, `empty_string`, `int`, one `unreadable` representative,
and `over_max_layer`. Each carries a `$why`, and the file header explains why the axis is small so
nobody "restores coverage" later.

## One deviation, stated

**I kept `over_max_layer`** as a sixth case. It is not coercion: it is the second branch of the
rule — readable as an integer but out of range — and it guards a server-side consequence that
exists regardless of who wrote the value, since `to` feeds `painted × layers` and an unbounded
magnitude puts a 301-digit integer into `required`. Delete it and `MAX_LAYER` can be removed with
the suite still green. Stated as a decimal string so both sides parse it exactly.

## The refusal decision, and a conflict in the instruction

The server now **refuses** rather than stringifies:

- `_band_materials` returns `(kept, refused)`. A non-string element is refused (`None`, `""` and
  whitespace are still dropped silently — that means "no material", not corruption). The band is
  skipped entirely, because deriving `share` from a divisor we know is wrong produces a
  plausible-looking number.
- `_parse_bands` returns `(bands, readable, dropped)`. A non-object band element is dropped **and
  counted**, then reported as `layer_range_invalid(reason="not_a_band")` — silence there would let
  array length change, which shifts positional `seq` and every later band's `prevTo`.
- Either refusal forces `availability_checked = False` for the whole plan.

**The conflict:** your keep-list named ten material cases including `integer_element_stringified`
(`42` → `"42"`) and `non_integral_float_element` (`4.5` → `"4.5"`). Those two cannot survive the
refusal rule — `42` is not a string, so it is now refused, not stringified. I applied the
principle and dropped those two vectors, keeping the other eight minus `null_element_dropped`,
`empty_string_dropped` and `whitespace_only_dropped`, which I collapsed into one
`empty_values_dropped`. Result is six. Say if you wanted the other reading.

Refusal behaviour is covered by **server-only pytest tests**, not vectors — the two sides do
different things with unreachable input by design, so it does not belong in a shared contract:
`test_non_string_material_is_refused_not_stringified`,
`test_refused_material_blocks_verification_and_says_so`,
`test_non_object_band_element_is_refused_and_reported`, and
`test_to_defects_do_not_invalidate_the_whole_plan_but_refusals_do` — the last pins the deliberate
asymmetry: a blank `to` is normal editing and must not invalidate other bands, a structural
refusal is corruption and does.

## Also done

- Dropped the seq type expansion (7 vectors) entirely; `invalid_seq_types_fall_back_to_position`
  carries the axis with one case and a `$why` telling the next reader not to expand it.
- Kept the `_band_seq` integral-float acceptance — harmless, removes a real difference, no vectors.
- Kept `sequence_cases`, `invalid_between_is_skipped_exactly_like_blank`, `normalize_roundtrip`
  and `material_split_cases` untouched.
- No `client2/` changes.
- Re-verified both unconsumed-group guards by injecting `bogus_cases`: harness prints
  `HARNESS FAILURE ... never scored` and pytest fails `test_every_vector_group_is_consumed_by_a_test`.
  Restored and re-confirmed 110/0.
- Live `validate_plan` against real PostgreSQL: unchanged, response key set still asserted.
