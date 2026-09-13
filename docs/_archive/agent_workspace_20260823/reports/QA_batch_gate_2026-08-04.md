# QA Batch Gate — 28 commits, `6b150d3` → `cb184a7`

**Date:** 2026-08-04 · **Reviewer:** qa-reviewer (adversarial) · **Scope:** final gate before push to `main`

---

## 0. VERDICT: **GO-WITH-FIXES**

One shipping defect must be fixed before the push (§2, F1 — a committed doc links to an untracked
file). Nothing else found is both *introduced by this batch* and *live-reachable today*.

The batch's largest risk surface — the 10-commit refactoring — was attacked directly at the blind
spot named in the brief and **held**. I could not produce a behaviour change in it.

The serious findings (§3) are real but each is latent, pre-existing-and-untouched, or bounded to a
low-volume manual path whose entire historical corpus is verified byte-identical. They are
follow-ups, not blockers. One of them (F5) is a hazard this batch made *reachable* and should be
boarded immediately.

---

## 1. The three numbers — measured by me, not accepted

| Gate | Claimed | **Measured** | Verdict |
|---|---|---|---|
| Server suite | 1958 passed, 2 skipped | **1958 passed, 2 skipped, 0 failed** | ✅ exact match |
| Client harnesses | 23 / 19 gated green / 4 known-red / exit 0 | **23 / 19 gated green / 4 known-red / exit 0** | ✅ exact match |
| Contracts | 6/6 | **6 contracts, no divergence** | ✅ exact match |
| dist ↔ source | consistent | **byte-identical to a fresh rebuild** | ✅ verified |

**Method notes.**
- Suite run in `server/` under `conda run -n assy_manager` with `PYTHONIOENCODING=utf-8`. No live
  pytest existed at start (only the 5-process decoupled server). **Warning for the next run:** a
  daemon thread in `directory_watcher` emits `--- Logging error ---` tracebacks *after* pytest
  closes its capture, and `conda run` then reports `execute(125)`. That exit code and that trailing
  noise are **not** the test result — my first attempt lost the summary to a `| tail` pipeline.
  Capture the whole stream to a file and read the summary line.
- dist verified by rebuilding to a scratch dir with `--emptyOutDir` and `diff -r` against the tracked
  `client2/dist`. **All 20 emitted asset filenames matched the committed content hashes, and
  `diff -r` reported no differences and no orphan files.** The tracked bundle is exactly what the
  committed source produces.
- **Known-red set compared as a SET, not a count** (count checks miss swaps). Pre-batch: 5 —
  `effort_instrument`, `reposition_regime_probe`, `split_registry`, `valid_die_authoring`,
  `valid_die_frame_adoption`. Now: those 4 minus `effort_instrument`, which **recovered** (`ef153c0`).
  Strict shrink, nothing quietly demoted from gated to known-red. ✅
- Measured assertion total across the 19 gated-green harnesses: **18,926** (the brief's "18,193" and
  the board's "18,042" are earlier snapshots; the set grew during the batch). Not a defect — noting
  the current figure so it is not re-copied stale.

---

## 2. Confirmed defects that should be fixed before the push

### F1 — [MEDIUM] A committed doc links to an untracked file; the push ships a dead link
`docs/process/PROJECT_STATUS.md:75` (in `HEAD`) links to `../../server/scripts/wf_spelling_census.sql`.

- `git show HEAD:docs/process/PROJECT_STATUS.md` contains the link (1 occurrence).
- `git ls-files server/scripts/wf_spelling_census.sql` → **0**. The file exists on disk (11,285 bytes,
  untracked).

**Failure scenario:** the push lands; anyone who clones or pulls opens the board, follows the
"측정 쿼리" link that the board says defines the target column list, and gets a 404. The board's
STEP-0 instruction becomes unfollowable for everyone except this workstation.

**Fix:** `git add server/scripts/wf_spelling_census.sql` and amend/append a commit, **or** remove the
link. (`docs/process/image/` is also untracked but nothing committed references it — no action needed
unless it was meant to ship.)

---

## 3. Confirmed defects — follow-ups, not blockers

Ordered by severity. For each I state explicitly whether **this batch** introduced it.

### F2 — [HIGH] The parser's central safety premise is false: a refused shape is silent, not loud
**Introduced by this batch: the premise, yes. The silent path, no (pre-existing).**

`server/parsers/html_topology_parser.py:576-578` — the `_ruler_row` docstring justifies its strictness:

> "The guard is deliberately strict in this direction: a shape it refuses yields zero records, **which
> is loud**, whereas the failure it replaces was a silently wrong map key…"

I verified the caller myself. Zero records is **not** loud:

- `server/parsers/directory_watcher.py:1163-1164` — `if has_rows:` guards `_send_to_upsert`. Zero rows
  ⇒ nothing is written.
- `:1170` archives the file anyway; `:1177-1184` logs `✅ Successfully processed and archived` and
  fires the completion callback with **`"SUCCESS"`** and an empty detail.
- `server/parsers/directory_watcher.py:1673-1675` — `rows = self._discover_and_execute_pipeline(...)`;
  `if rows is not None: return rows`. An empty list is **not** `None`, so the std-parser fallback at
  `:1678` never runs.

**Failure scenario:** an HTML smart-paste file whose ruler the new predicate refuses is moved to
`archives/`, recorded `FileIngestionLog.status = "SUCCESS"` with no error text, no warning, and zero
rows ingested. It is indistinguishable from a healthy ingest. The operator has no signal at all.

This is core value #3 inverted — "quietly wrong" beating "loudly slow". The strictness was traded
against a safety property the system does not have.

**Fix:** make a zero-row pipeline result a distinct outcome (WARNING status or a populated `detail`),
so the guard's premise becomes true. This is one change that also covers every other parser.

### F3 — [MEDIUM] The ruler predicate rejects whole files on a single merged cell
**Introduced by this batch: yes (behaviour narrowed).**

`server/parsers/html_topology_parser.py:579-594`, verified by reading the predicate:

- `:580-581` — a merged **corner** (`col_span != 1 or row_span != 1`) disqualifies the row.
- `:590-591` — **any** merged tick disqualifies the entire row.
- `:586-587` — missing cells are `continue`d, so gaps do not disqualify.
- `:594` — only `len(ticks) >= 2` is required: **no contiguity, monotonicity, distinctness, or
  start-value check.**
- `:602-609` — "the topmost qualifying row wins."

Sub-agent measurement (synthetic shapes against the real `HTMLMatrixTableParser`, old vs new):
merged ticks → old **66 records**, new **0**; one single merged tick among many → new **0**; merged
corner → old 10, new **0**. Combined with F2, each of those is a silent `SUCCESS` with no data.

Also proven: a full-width all-integer unmerged row **above** the real ruler (e.g. a `SLOT` row —
and the commit itself cites the "`slot` is always int" ruling as why numeric header cells are now
normal) is selected as the ruler and **relabels the X axis while producing the correct record count
and correct header keys**. Nothing downstream can see it. Whether that specific shape is a
regression or was equally broken before was still being measured when this report was written; it is
flagged for the board either way.

**Bounding — why this is not a blocker.** The parser has exactly **one** consumer:
`server/ingestion_workspace/bonding_map/scripts/bonding_map_parser.py:4`. And the HTML path is
low-volume: `archives/` holds **3,179 `.csv` and 16 `.html`**; `err/` holds 18 `.csv` and 3 `.html`.
The CSVs go through the std parser and are untouched by `53b30f9`. The whole historical HTML corpus
was re-parsed old-vs-new: **grid cell payload identical on all 19 files**, headers identical on 15,
one corrected map key, three phantom `F_AAA` keys removed — the claimed result, reproduced.

**Corpus label correction:** the "19 archived files" are **16 in `archives/` plus 3 in `err/`**
(files that *failed* ingestion). Within `archives/` alone it is 12 identical / 1 corrected / 3
de-phantomed. The commit message and any doc repeating "19 archived files" should be corrected.

### F4 — [HIGH, latent] O2's declaration check passes when the declaration is *missing*
**Introduced by this batch: no. Neither `ontology_config.py` nor `graph_orphans.py` was touched
(`git diff --name-only 6b150d3..HEAD` — neither appears).**

`server/ontology_config.py:436-446`: when `ontology_mapping.json` does not exist, `os.path.exists` is
False, `raw_config = {}`, and `_record` is never called — **no rejection**. `synthesize_enrichment_mappings`
(`:451`) then repopulates `mappings` from `enrichment_rules.json`, so `graph_orphans.declaration_blockers`
(`server/graph_orphans.py:125-146`) finds neither `not mappings` nor any `rejections`. **Zero blockers.**

Proven by execution against the live config tree: with a non-existent mapping path, `MAPPINGS` = the
2 enrichment-synthesised tables, `REJECTIONS` = `[]`, `BLOCKERS` = `[]` — the sweep runs. Live
`plan_sweep` under that reduced dict puts **89,027 non-user edges on the sweepable side**, held back
only by the per-type fraction guard (which `--max-fraction 1.0`, recommended by the CLI's own usage
text at `graph_stale_edge_sweep.py:15`, disables globally).

**Why it does not block:** O2 itself is safe as shipped — `apply_deletions: bool = False`
(`server/graph_stale_edges.py:485`), no HTTP route, no scheduler entry, no worker, no config
reference (repo-wide grep including `server/config/*.json`, `server/mappers/`,
`server/ingestion_workspace/`, `server/scripts/`). The only `apply=True` callers are two tests behind
the isolated-DB guard. The scheduled sibling `graph_orphans` is gated by
`GRAPH_ORPHAN_SWEEP_ENABLED` (`server/graph_orphans.py:91`), which is **not set** in this environment.

**Board before anything schedules O2:** (a) `_record` a rejection for an absent/empty
`ontology_mapping.json`; (b) add a **global** ceiling to `plan_sweep` (the per-type guard cannot see
"the declaration collapsed", and `min_population = 10` exempts small types from any check); (c) make
the apply gate `apply_deletions is True`, not truthy — `graph_stale_edges.py:537` is a truthiness
test and the string `"false"` is truthy; (d) add `ENABLE_ENV`/`sweep_enabled()` and an
isolation gate to the module (they currently exist only in the CLI).

**Also confirmed on O2 (attacked, found safe):** the human-confirmed protection is on the single
delete path — `graph_stale_edges.py:364` → `grouped:372` → `sweepable:404` → `delete_ids:421`, no
second branch; `crud.USER_SOURCE = "user"` (`server/database/crud.py:139`) is compared exactly and
matches the only live spelling (327 edges); `source_name` is `NOT NULL` in live
`information_schema`, so a NULL cannot fall on the delete side. A truncated scan declines **every**
type (`:379-391`), verified live: `scan_limit=5000` → `truncated True, delete_ids 0`. No `try/except`
exists in the planning path, so no partial verdict set can proceed.
*Residual:* an edge whose target identity mixes a human-corrected column with a file-sourced one is
minted with the **file's** `source_name` (`server/graph_materializer.py:181-192`, `max()` picks the
least authoritative), so it is **not** protected. Board it.

### F5 — [HIGH, latent] A *deleted* optional `val` silently makes every row a FAIL
**Introduced by this batch: the hazard existed; this batch made it reachable by actively advising
deletion.**

`server/transfer_plan.py:1743-1753`. Three forms of an optional `val` role, executed:

| form | dry-run | guard `:1743` | guard `:1745` | outcome |
|---|---|---|---|---|
| A `val`→ real column | accepted | **True** | False | correct |
| B `val`→ typo | accepted | False | **True** | demoted, safe |
| C `val` **deleted** | accepted | **False** | **False** | **falls through** |

Form C reaches `cnt = db.query(model).filter(*identity_filters).count()` at `:1753` **with no
fail-value predicate**, and returns `status="connected"`, not degraded, `reliable: true`.

**Failure scenario, quantified on live `dt_log`** (8,700 rows; `c_bn` ∈ {`'1'`: 8618, `'0'`: 82};
zero `'F'`). For lot `DT-2601-001` slot `22` (144 rows): `fail_breakdown` **0 → 144**, `remaining`
**144 → 0**, `reliable` stays **true**, warnings **none**. `WARN_NEGATIVE_REMAINING`
(`:776`) does not fire because the result is 0, not negative.

The asymmetry is inverted: the **typo** is caught with an explicit comment explaining why
(`:1746-1749`), the **deletion** is not. And `_role_dry_run` (`:548`) iterates
`required + declared extras`, so a deleted optional role appears **nowhere** in the report — form A
shows 5 columns, form C shows 4, and no field says one is missing. Both return `accepted`, `reason: null`.

**Why this batch matters here:** `8817dde`/`12c1d2e` add `removable_declarations` and
`deletion_hints` — the tooling now *recommends deleting* declarations. It turns a rare accident into
a guided action while the deletion path stays silent.

**Mitigation today:** I verified the live `server/config/transfer_plan_config.json` declares **no**
`fail_sources` — the single string match is inside a `__comment`. Latent, not firing.

**Fix:** treat `fail_values` declared without a resolvable `val` as a refusal, symmetric to `:1745`.

### F6 — [MEDIUM, latent] `Time` is a recognised type and it is a hard 500
**Introduced by this batch: yes (the funnel `9e02e3f` widened names `Time` explicitly).**

`server/database/crud.py:704` routes `Time` into `temporal_text_sql`, so the CAST fallback at `:710`
never runs. `temporal_text_sql` (`:618-622`) emits `to_char(timezone('UTC', c), …)`;
`timezone('UTC', <time>)` promotes `time` → `timetz`, and **no `to_char(timetz, text)` exists**.
Executed against live PG 18.3: `ProgrammingError: to_char(time with time zone, unknown) does not
exist`, on both the SELECT list and the WHERE clause ⇒ **HTTP 500 on the grid read**, not a safe
fallback. The Python twin `temporal_text_value` (`:642`) tests `isinstance(value, (datetime, date))`
and `datetime.time` subclasses neither, so the three seam implementations disagree three ways.

**The commit's headline claim is still true** — an *unknown* type gets a CAST, not a 500. The hole is
inside a class the funnel claims to **know**.

**Reachability: 0 today.** Live `public` schema has no `time`, no `timestamp without time zone`, no
`date` columns; `init_dynamic_models` (`server/database/models.py:394-399, 422-427`) only produces
`Float` / `DateTime(timezone=True)` / `String`. One `column_types` entry would arm it.

Related (same latency): for a **naive** `timestamp` or a `date`, `timezone('UTC', ts)` runs the
*inverse* conversion, so the rendered text follows the session TZ GUC — measured `2026-08-04
06:23:39` (UTC) vs `15:23:39` (Asia/Seoul) vs `02:23:39` (New_York) for the same stored value. That
is verbatim the defect the commit says it eliminated, surviving for the two types nobody has yet.

**Attacked and found safe (F6-negative):** I tried to produce a fifth class and could not. All **8**
distinct `(data_type, udt_name)` pairs in live `public` (varchar 297, float8 98, timestamptz 91,
bool 52, int4 14, int8 8, jsonb 3, json 3) were fed through the funnel and executed — all OK, NULL
folds to the label in every case. `interval`, `uuid`, `text[]`/ARRAY, `bytea`, SQLAlchemy `Enum`,
PG native `ENUM`, `Numeric`, `SmallInteger`, `BigInteger` all resolve correctly. **No cast Postgres
refuses was found.**
**No expression-index regression:** 279 indexes in `public`, 7 with expressions/predicates, **none**
on a table reachable from `virtual_join_rules.json`; all four live `expose` columns are `"string"` →
`blank_to_null(col)`, byte-identical to the pre-N8 `_text_part`. **N8 changes zero live query plans.**

### F7 — [MEDIUM] Two live `transfer_plan` config bindings are broken on disk right now
**Introduced by this batch: no — the batch's new dry-run tool *revealed* them.**

Live dry-run: `total 18, accepted 2, rejected 2, not_declared 7, not_reached 7`.

- `stages.bonding.bin_map` → `candidate_column_missing`; declares x→`x`, y→`y` on `dt_log` whose real
  columns are `dt_x`/`dt_y`. This is the typo `12c1d2e` names — **still on disk**.
- `stages.bonding.source.total_chips` → **neither commit mentions this one.** It declares
  `lot`/`slot`/`x`/`y` against `dt_log`'s `dt_lot`/`dt_slot`/`dt_x`/`dt_y`; all four
  `exists_on_table: False`. `lot`/`slot` are required and not derivable, so `removable_declarations`
  is empty — **deletion cannot repair it.** Consequence: `statuses["total_chips"] = "missing"`
  (`server/transfer_plan.py:1589`) → `EFFECT_TOTAL_UNKNOWN` → `total_reliable=False` **and**
  `remaining_reliable=False`. **The bonding stage source-summary serves `remaining: null` in
  production today.**

### F8 — [LOW] `12c1d2e`'s named refusal reaches the operator on 2 of 9 role paths
`_bins_unavailable` carries `detail`+`reason` and `client2/src/transfer_plan.js:460` renders it
verbatim — so `bin_map` and `lot_membership` refusals **do** reach the operator, as claimed. But the
seven `_STAGE_SOURCE_ROLES` never call `explain_binding_refusal` on the read path. `total_chips` —
the role actually broken today (F7) — surfaces as the bare word `"missing"`. The named reason exists
only behind `GET /admin/transfer-plan/dry-run` (`server/main.py:4375`, admin-token gated), and no
client code fetches that route. The promise stops one layer short of the operator for the live defect.

### F9 — [LOW] `bin_map` can never receive `BINDING_NOT_REACHED` on a delegating stage
`server/transfer_plan.py:601` builds the `bin_map` entry **before** the `ref in M1_SOURCE_REFS` branch
at `:604`. For stage `dt` the dry-run prints `bin_map → not_declared` with an actionable sentence
telling the operator to declare `table` + `columns`, while `get_source_summary` for an M1-delegated
stage returns `_bins_unavailable(...)` unconditionally (`:2158-2161`) and never calls `_bins_block`.
The sentence invites an edit that does not produce the axis it promises — the exact failure mode
`BINDING_NOT_REACHED` was introduced to prevent.

---

## 4. Attacked and found safe — the refactoring (A)

The brief's thesis: byte-identical harness stdout is a **narrower** guarantee than it reads (M4 — a
mask on the wrong dies moves no stored coordinate; M5/I5b — a frame swap moves 18 of 99 cells while
the count and the sentence hold). I attacked what the oracle cannot see. **I found nothing.**

| Hypothesis | How I tried to break it | Result |
|---|---|---|
| A step reads module state it used to read at a different moment | Wrote an independent AST-ish checker over all **17** extracted steps: collected 49 top-level `let`/`var` bindings, subtracted parameters and locals from each body's free identifiers | **STATE# 0 on all 17.** The commits' claim reproduces independently |
| Extracted bodies are not really verbatim | Brace-matched extraction of each function from `<sha>^` and from `HEAD`, compared modulo comments/whitespace | **14 of 14 module-extracted functions identical.** The only signature change is `getMapIdFromMeta(metaDict)` → `(metaDict, tableSchema)` |
| That new `tableSchema` parameter captures a stale value | Checked all 3 production call sites (`map_editor.js:3603, 4901, 5472`) | All pass the live module binding at call time — same read moment as before. Harness stubs are test-local |
| `boundingBoxCache` invalidation moved out of the `meta` branch | Compared old `2f3fa6f^:4754-4790`: the invalidate was the **last** statement of the branch; nothing between it and the unconditional invalidate reads the cache | Move is a no-op. Comment is accurate |
| `dimsDiffer`/`originDiffer` went conditional → **unconditional** assignment | Traced: declared `let … = null` at `7882`/`7885`, assigned once at `8063`/`8064`; `diagnoseDesignationAlignment` returns `null` when the condition is false | Overwriting `null` with `null`. Equivalent |
| Gate 4 moved, changing *when* a push is refused | The comment admits moving it would be a behaviour change. Compared `4a0c402^:5320` | It was **already first**. Position unchanged |
| A refusal path lost its button-state restoration | Both old and new `loadExistingMap` have the same `finally { el.btnLoadMap… }`; the refusals return from inside the `try` | `finally` runs on every path |
| `resolveGridFrame`'s branches drifted | Line-by-line against `2f3fa6f^:4740-4780`, including the `standard` branch's `applyPresetObject` call and `halfDiag` | Faithful |
| `resolveReferenceSpec`'s three `refuse()` calls became returned reasons | Caller does `if (!rspec.ok) return refuse(ref, rspec.reason)` immediately; `refuse` still owns the module writes | Equivalent |
| `summariseReseat` receives `gridData`/`loadedFCells`/`serverCellKeys` as arguments | These are reassignable module bindings, but the call is at the same point and the reads happen immediately inside | Same object, same moment |

Line-count trajectory verified: `b322267` 9,611 → `c0a3715` **9,632** (formatter reflow) → `689ebb9`
9,495 → `636f867` 9,163 → `2f3fa6f` 9,253 → `cafd61f` 9,334 → `4a0c402` **9,420** = `HEAD`.
The claim "9,632 → 9,420" is accurate. Note for framing: the **decompositions added 257 lines back**;
the net reduction came from the two module extractions.

**R6's exception class survives the move — unchanged, and still live.** The cell-put epilogue stayed
inline (deliberately, per the comment block at `map_editor.js:5657+`). It remains inside the `try`:
after `replace_map` has committed, `saveLegendToServer` / `applyLegendSaveResult` / `notifyLegendChanged`
run at `:5612-5624`, and a throw there lands in the `catch` at `:5640` which alerts
**"데이터 적재 실패"** on a push that **succeeded**. `saveLegendToServer` returns `{ok:false}` for its
own fetch errors, but its earlier `await`s (`readRegistryScope`, `probeZoneColumns`) sit outside its
`try`, and `notifyLegendChanged()` crosses into `transfer_plan.js`. **Pre-existing, not a regression
from this batch** — recorded so it is not lost.

---

## 5. Runtime verification still needed

1. **F3's realistic-shape question.** Whether any *future* bonding_map HTML export merges its ruler
   corner or ticks. The 19-file corpus does not, but that corpus is 16 files of manual smart-paste.
   One malformed export = a silent zero-row `SUCCESS` (F2).
2. **F3's `SLOT`-row hijack: regression or pre-existing?** Proven to produce silently wrong X labels
   on the new parser; the old-parser comparison for that exact shape was still running at
   report time.
3. **F6/F5/F4 arming.** All three are one config edit away (`time` in `column_types`; a `fail_sources`
   block; an absent `ontology_mapping.json`). None can be settled from code — they need a policy
   decision about whether declaration-time refusal is added.
4. **O2 TOCTOU.** An edge classified `row_gone` whose row is re-created by the ingestion worker
   between plan and apply would be deleted; the materializer should re-mint it on the next outbox
   event. Not exercised (would require writing).
5. **Browser E2E for the map editor.** The refactoring is verified by harnesses and by my static
   analysis, not by a real browser session. Per project rule, client changes get an isolated-env
   (8081) E2E before shipping — that has not been done in this review.

---

## 6. Documentation integrity

**Good:** `DOC_OWNERSHIP.md` was updated in-round with rows for both new modules and an explicit
"이번 라운드 (2026-08-04)" block. `CODE_MAP.md` documents `map_key.js` / `split_registry_row.js`
thoroughly (line counts, extraction commits, full symbol tables) and **honestly declares its own
range** (`1dc761b`→`ed9cfdb`).

**Gaps:**

1. **`CODE_MAP.md` is stale by 4 commits** — its range ends at `ed9cfdb`, but `2f3fa6f`, `cafd61f`,
   `4a0c402` and `53b30f9` landed after. Measured anchor drift beyond the ±20-line tolerance:

   | symbol | CODE_MAP | actual | drift |
   |---|---|---|---|
   | `resolveValidDie` | ~7568 | **7744** | **+176** |
   | `pushMapData` | ~5230 | **5320** | **+90** |
   | `loadExistingMap` | ~4433 | 4447 | +14 (ok) |

   It also states `map_editor.js` is **9,163** lines; it is **9,420**.
2. **None of the 17 new step-function symbols appears in `CODE_MAP.md`** (`fitGridToMask`,
   `resolveGridFrame`, `resolveDeclaredGridMeta`, `buildPushGridMetadata`,
   `confirmLogShapedPushTarget`, … — all 0 hits). The batch's headline refactoring is invisible in
   the symbol index.
3. **`docs/history/` covers 2 of the batch's ~6 threads.** Entries exist for `9e02e3f` (N8) and the
   bonding-plan relaxation. **No entry** for the 10-commit refactoring, `53b30f9` (parser),
   `55fb19c` (O2), or `8817dde`/`12c1d2e` (derivation). History cites SHAs by convention, so these
   are genuine omissions, not a format difference.
4. **Overstated corpus label** (F3): "19 archived files" is 16 `archives/` + 3 `err/`. The commit
   message and any doc repeating it should be corrected.
5. **False premise in shipped source comment** (F2): the `_ruler_row` docstring's "which is loud"
   should be corrected or made true.

---

## 7. Not re-reported

Confirmed still-open and **not** worsened by this batch: M4; M5 (I1 gate-4 log-shaped BLOCK never
refuses; I3 pushed metadata loses `grid_start_x/y`); M6 (two map-key spellings, `L1_NaN` collision);
N10 (`fail_sources` marker — but see **F5**, which this batch made *reachable* via deletion advice);
N11; N12; N13.

**One pre-existing item worth boarding separately** (found in passing, not a batch regression):
`client2/src/config.js:4` — `CURRENT_USER = import.meta.env.VITE_USER` is injected at **build time**
from the builder's OS username. The tracked, served bundle
`client2/dist/assets/main-CsyI2gyZ.js` has **`kk980` baked in** at 3 sites, e.g.
`` `${API_BASE}/tables/${...}/rows?count=${e}&user_name=kk980` ``. Every browser loading this bundle
attributes its writes to `kk980`, which bears directly on core value #4 (layering / user
attribution). **Verified pre-existing** — the pre-batch bundle `main-DViSXS9R.js` has the same 3
occurrences. Not a blocker; should be boarded.

---

## 8. Proposed lessons for `agent_workspace/memory/qa-reviewer.md`

*(proposal only — not added directly, per the operating rule)*

- **함정:** 백그라운드로 pytest를 돌리며 `| tail -N`을 붙이면 요약 줄이 사라진다. `directory_watcher`의
  데몬 스레드가 pytest 캡처가 닫힌 뒤 `--- Logging error ---` 역추적을 뱉어 마지막 40줄을 채우고,
  `conda run`은 `execute(125)`를 찍는다. **그 125와 그 역추적은 테스트 결과가 아니다.**
  **올바른 방법:** 전체 스트림을 파일로 받고 요약 줄을 직접 grep한다.
- **함정:** 문서가 "무엇을 보장한다"고 적었을 때 그 문장을 검수 근거로 삼는다.
  **올바른 방법:** 보장 문장은 **호출부에서 반증한다.** 이번 라운드의 파서 docstring은
  "거절은 시끄럽다"고 적었고 호출부는 그것을 `SUCCESS`로 기록했다 — 문장과 호출부가 정반대였다.
- **함정:** 추출 리팩터링을 "본문이 동일하다"는 주장으로 통과시킨다.
  **올바른 방법:** `<sha>^`에서 함수를 중괄호 매칭으로 떠내 주석·공백 제외 대조하고,
  **모듈 전역 자유변수**를 파라미터·지역과 차집합해 독립적으로 STATE#를 센다. 두 검사 모두
  스크립트 30줄이면 되고, 17개 단계를 한 번에 판정한다.
