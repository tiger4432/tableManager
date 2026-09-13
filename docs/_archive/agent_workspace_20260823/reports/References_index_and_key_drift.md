# `GET /api/maps/alignment/references` — the missing index and the key-column drift

Round: 2026-08-14 · server-pm · measurement on `assy_qa`, facts read from `assy_manager`.

---

## 0. WHAT I REFUTED, FIRST

### 0.1 🔴 The index is worth ~1%, not 78%. It is not one of "the two dominant costs."

Measured, best of 3, `ANALYZE` before each cell:

```
S0  key=wafer_id  no index      218 statements   0.184 s
S1  key=wafer_id  + btree       218 statements   0.182 s     -1.1 %
```

The prior lane's "index = 78 % of wall time" was true when it was measured and is
false now. Between then and today **`_count_cells_bulk` landed**
(`map_alignment.py`, called from `resolve_reference_catalog`). It answers every
candidate's size in one `GROUP BY`, seeds `ref_cache`, and `_cells_of`
short-circuits on `known_count == 0`. In the `wafer_id` state every candidate
counts 0, so the 400 per-candidate sequential scans the old report attributed to
the missing index **are not issued at all any more**. `core_wafer_map` is touched
by exactly one statement today: the bulk `GROUP BY`, which is a full scan under
any index.

The number I was given to build on (928 ms, owner's stack) is real, but its
composition is not what the old report says.

### 0.2 🔴 Task B makes the route SLOWER. The index does not pay for itself — it pays for Task B.

```
S0 -> S2   0.184 s -> 1.128 s     the drift fix ALONE, +513 %
S0 -> S3   0.184 s -> 0.332 s     drift fix + index, still +80 % vs today
```

Fixing the drift is what creates the work: 201 floors stop being refused and each
one then issues the cell read it should always have issued. Today's route is fast
because it is doing nothing. **Neither repair is a performance win over today.**
The index's entire value is conditional — it removes 71 % of the cost the
correctness fix adds (76 % on the owner's data shape, §3.2).

So, answering the question as posed: if one of them carried the whole win the
other would need its own reason. In fact *neither* is justified by performance.
The drift fix is justified by correctness (201 registered floors are invisible to
the operator). The index is justified as **the thing that makes the drift fix
affordable**, and it must land first (§4).

### 0.3 🔴 `server/migrations/migrate_map_meta_to_wafer_id.py` states a fact that is false today, and its own guard now blocks it.

Its docstring says the 2026-08-10 correction landed in **both** identity configs:

> `table_config.json` (`core_wafer_map.map_key_columns`) and `map_overlay_config.json`
> (`table_bindings.core_wafer_map.columns.key_columns`) -- to `["wafer_id"]`.

`table_config.json` says `["core_lot", "core_slot"]` — live **and** `.sample`. You
restored it yourself in `272da5b` on 2026-08-13, on grounds that outrank
performance: `wafer_id` is not in `composite_key_source`, and its own column
comment calls it **deliberately sparse** ("absence is the enrichment work item").
Measured today: `wafer_id` is blank on **9,674 of 24,749** `core_wafer_map` rows.

Consequence: `main()` in that migration cross-checks `table_config` and returns
`REFUSED` unless it reads `["wafer_id"]`. **The "move the data to wafer_id" route
is already closed by a ruling you made yesterday.** Task B is not a reversal of a
2026-08-10 decision — it is the last unfinished half of the 2026-08-13 one.

That script is now obsolete and actively misleading. Ruling needed (§6, F1).

### 0.4 The offered-floor count does change, but not by 201, and 3 maps LOSE their place.

Measured, not reasoned (§5). On `assy_manager`: **11 → 209**. Three maps that are
offered today become refused — a named, loud refusal, not a silent one.

### 0.5 Everything else you told me is correct.

204 meta rows; 3/204 on `wafer_id`; 201/204 on `core_lot||'_'||core_slot`; nine
indexes on `core_wafer_map`, none covering the map key. All re-measured, all true.

---

## 1. Where the live lookup is actually keyed (Task A justification)

It is **not** hardcoded and it is **not** `map_overlay_config` alone. Per key:

```
local declaration (map_overlay_config.table_bindings.<t>.columns)
  >  table_config.<t>.map_key_columns
  >  refuse by name
```
(`map_overlay.resolve_binding_parts`, `BINDING_KEYS`)

`map_alignment._binding_of` -> `map_overlay.resolve_binding` -> that precedence.
`_cells_of`, `_count_cells`, `_count_cells_bulk` and `_no_cell_refusal` all
decompose the map id through `map_overlay.map_key_parts` and bind through
`build_key_filters`, so the predicate every map read issues is literally

```sql
WHERE core_lot = ? AND core_slot = ?
```

**This is the drift's whole mechanism, and it is a writer/reader split:**

| role | reads | value | effect |
|---|---|---|---|
| WRITER `map_meta_registrar.MetaCollector` | `table_config.map_key_columns` | `[core_lot, core_slot]` | registers `CL-2601-001_01` |
| READER `map_overlay.resolve_binding` | `map_overlay_config...key_columns` (wins) | `[wafer_id]` | looks up `wafer_id = 'CL-2601-001_01'` |

The writer never agreed with the reader. That is why 201 of 204 registered floors
answer `no_cells` while their cells sit in the table.

Three statement shapes read through the map key, all in `map_alignment`:

| site | statement | per |
|---|---|---|
| `_cells_of` | `SELECT core_x, core_y, c_bn ... WHERE <key> ORDER BY core_y, core_x, row_id LIMIT cap+1` | candidate |
| `_count_cells` | `SELECT count(*) ... WHERE <key>` | candidate (only when bulk declines) |
| `_count_cells_bulk` | `SELECT core_lot, core_slot, count(*) ... GROUP BY 1,2` | floor table |

`EXPLAIN (ANALYZE, BUFFERS)` on `assy_qa`, `ANALYZE` before each plan:

| statement | no index | `(core_lot, core_slot)` | covering* |
|---|---|---|---|
| cell read `LIMIT 2` | 3.615 ms | **0.082 ms** | 0.110 ms |
| `COUNT(*)` one key | 3.727 ms | **0.050 ms** | 0.114 ms |
| `GROUP BY` key | 7.899 ms | **4.782 ms** (GroupAgg) | 8.129 ms (HashAgg) |

\* `(core_lot, core_slot, core_y, core_x, row_id) INCLUDE (c_bn)`

**The two-column index is the right column list, measured.** The covering variant
additionally serves the `ORDER BY` and makes the read index-only, and it is
*worse*: the sort it removes is a top-N heapsort over ~121 rows, and it pushed the
`GROUP BY` back to a HashAggregate. End to end 0.329 s vs 0.332 s — inside the
spread. Six columns of write amplification on an ingestion target, bought with
nothing. The number that would change this verdict is rows-per-map (~121 today).

**Migration:** `C:\Users\kk980\Developments\assyManager\server\migrations\add_core_wafer_map_key_index.sql`
**Reverse:** `C:\Users\kk980\Developments\assyManager\server\migrations\add_core_wafer_map_key_index_reverse.sql`

Shape follows `add_bonding_base_join_index.sql` / `add_void_schema_indexes.sql`:
`CREATE INDEX CONCURRENTLY IF NOT EXISTS`, header carrying ORDER / wrong-database
/ INVALID-index recovery / REVERSE pointer, and the not-taken options argued with
their measurements. Forward and reverse were both executed against `assy_qa` and
then undone — the DDL is valid and idempotent. **Not run against `assy_manager`.**

---

## 2. Every copy of the declaration (Task B.1)

Eight live copies across four files-shapes. Worktrees and `.bak` files excluded;
`.claude/worktrees/**` carries ~40 more stale copies that nothing reads.

| # | path | key | value | verdict |
|---|---|---|---|---|
| 1 | `server/config/map_overlay_config.json` | `table_bindings.core_wafer_map.columns.key_columns` | `["wafer_id"]` | 🔴 **WRONG — changed by me** |
| 2 | `server/config/map_overlay_config.json.sample` | same | `["wafer_id"]` | 🔴 **WRONG — changed by me** |
| 3 | `server/config/table_config.json` | `core_wafer_map.map_key_columns` | `["core_lot","core_slot"]` | ✅ already right |
| 4 | `server/config/table_config.json.sample` | same | `["core_lot","core_slot"]` | ✅ fixed in `272da5b` |
| 5 | `dev_env/config/map_overlay_config.json` | `...columns.key_columns` | `["core_lot","core_slot"]` | ✅ already right |
| 6 | `dev_env/config/table_config.json` | `map_key_columns` | `["core_lot","core_slot"]` | ✅ already right |
| 7 | `docs/guide/config_reference/map_overlay_config.json` | `...columns.key_columns` | `["core_lot","core_slot"]` | ✅ already right |
| 8 | `docs/guide/config_reference/table_config.json` | `map_key_columns` | `["core_lot","core_slot"]` | ✅ already right |

Your premise about `dev_env` is confirmed (#5). But the important discovery is the
**shape** of the drift: **only the `server/config` pair was wrong, and only in the
overlay file.** So —

🔴 **The `:8081` shared stack has been serving 200 offered floors this whole time
while the owner's `:8080` served 11.** Any earlier comparison between the two
stacks on this screen was comparing two different declarations, not two databases.

### Arity assumptions of every reader (Task B.2)

None assumes a single column. One is arity-sensitive in a way that matters.

| reader | arity handling |
|---|---|
| `map_overlay.map_key_parts` | general; last column absorbs the remainder |
| `map_overlay.build_key_filters` | general; one filter per part |
| `map_overlay.canonical_map_key` | general |
| `map_alignment._no_cell_refusal` | explicitly branches `len(key_cols) >= 2`; the single-key case is *deliberately* exempted from the ambiguity check |
| `map_alignment._count_cells_bulk` | general `n`, **but declines the whole table if any map id does not split into exactly `n` parts** — see §3.2 |
| `map_overlay.resolve_binding_info` -> `GET /api/maps/paint-rules` | serves a list; client `client2/src/map_editor.js:161` does `Array.isArray(b.key_columns) ? ... : []` |
| `ontology_config._map_identity_columns` | reads `derive_binding_parts` (table_config only) — unaffected by this change |
| `config_resolve_report` | display only |

**No client change is needed and none was made** (`client2/**` untouched). The
client's other map-key path reads `map_key_columns` from `/tables/{t}/schema`,
which was already composite.

### What I changed

Both files, identically, plus a `__key_columns_comment` carrying the reason into
the live file (the pattern you used in `272da5b`, because the operator's box never
reads `.sample`):

```json
"key_columns": ["core_lot", "core_slot"]
```

Verified: both parse; the two declarations now agree; `resolve_binding` returns
`{'x':'core_x','y':'core_y','val':'c_bn','key_columns':['core_lot','core_slot']}`;
the other six declared bindings still resolve unchanged.

⚠️ **`map_overlay.load_overlay_config` re-reads the file on every call — there is
no cache and no restart.** This change is already live on the owner's `:8080`
stack. That is why the index must land first (§4).

---

## 3. Per-repair attribution (Task C)

`assy_qa` only. Best of 3. `ANALYZE core_wafer_map/valid_die_ref/wafer_map_metadata`
before every cell. Exactly one probe index alive per cell, **asserted** before
timing (see §3.3 — the first run of this harness was wrong for exactly this).

### 3.1 The four cells

| | key_columns | index | statements | wall (best of 3) | sql time | vs S0 |
|---|---|---|---|---|---|---|
| **S0** | `wafer_id` | none | 218 | **0.184 s** | 0.092 s | — |
| **S1** | `wafer_id` | btree(`wafer_id`) | 218 | **0.182 s** | 0.086 s | −1.1 % |
| **S2** | `core_lot, core_slot` | none | 418 | **1.128 s** | 0.913 s | +513 % |
| **S3** | `core_lot, core_slot` | btree(`core_lot,core_slot`) | 418 | **0.332 s** | 0.164 s | +80 % |
| S3c | `core_lot, core_slot` | covering (5 cols + INCLUDE) | 418 | 0.329 s | 0.161 s | +79 % |

Run spreads: S0 `[0.329, 0.204, 0.184]` · S1 `[0.199, 0.183, 0.182]` ·
S2 `[1.128, 1.136, 1.137]` · S3 `[0.379, 0.392, 0.332]` · S3c `[0.391, 0.363, 0.329]`.

**Attribution, each half on its own:**

| repair | on its own | conditional |
|---|---|---|
| missing index | **−1.1 %** (S0→S1) — worth nothing | **−71 %** once the drift is fixed (S2→S3) |
| key-column drift | **+513 %** (S0→S2) — it costs | correctness only |
| both | +80 % vs today (S0→S3), and correct | |

Statement counts move only with the drift fix (218 → 418): +200 cell reads, one
per floor that now resolves. The index changes no statement count at all.

### 3.2 🔴 The owner's box is a different cell, and it is worse

`_count_cells_bulk` refuses to answer when a map id cannot be split into exactly
`len(key_columns)` parts, and it refuses **for the whole table**, not per row.
`assy_manager` holds three such rows — `SYN-CORE-WAFER-01/02/03`, no `_` in them.

Measured directly against `assy_manager`'s real ids (read-only):

```
key_columns=['wafer_id']              ids=204  no-separator=3  bulk complete=True
key_columns=['core_lot','core_slot']  ids=204  no-separator=3  bulk complete=False   <-- declines
```

`assy_qa` has 200 ids and **zero** without a separator, so it does *not* decline.
The owner's box therefore lands in this row instead:

| | key_columns | index | statements | wall | sql |
|---|---|---|---|---|---|
| S2d | composite, bulk **declines** | none | 623 | **1.993 s** | 1.651 s |
| S3d | composite, bulk **declines** | btree(`core_lot,core_slot`) | 623 | **0.481 s** | 0.224 s |
| S3cd | composite, bulk declines | covering | 623 | 0.465 s | 0.215 s |

The index is worth **−76 %** there, and without it the drift fix costs
**10.8× today** rather than 6.1×. This is the strongest argument for the index and
it is invisible on `assy_qa`.

⚠️ **Extrapolation, flagged as such:** applying the `assy_qa` S0→S2d ratio to your
measured 928 ms suggests ~10 s without the index and ~2.4 s with it. A ratio
carried from another box is a hypothesis about the owner's box, not a fact about
it. What is a fact: the decline is real there and is not reproduced on `assy_qa`.

### 3.3 What I got wrong first, and why the numbers above are not the first ones

Two harness faults, both caught before they reached this table:

1. **All eight cells reported 0.000 s / 0 statements.** `models.init_dynamic_models`
   was never called, so `DYNAMIC_TABLES` was empty and the catalog returned
   `CATALOG_UNAVAILABLE` — which is indistinguishable from "the repair worked".
   The harness now raises `SystemExit` unless `state == served` and
   `examined > 0` and `statements > 0`.
2. **`cell()` dropped only the indexes it was about to create**, so S3c/S2d/S3d ran
   with the previous cell's index still standing. That produced the impossible
   reading `S2d (623 statements) faster than S2 (418 statements)`. It now drops
   every probe index and **asserts the live set equals the expected set** before
   timing. After the fix the ordering is coherent (more statements = slower) and
   matches the per-statement `EXPLAIN` costs.

### 3.4 Row counts differ between the boxes — both reported

| | `assy_manager` | `assy_qa` |
|---|---|---|
| `core_wafer_map` rows | 24,749 | 24,200 |
| `wafer_map_metadata` rows for it | 204 | 200 |
| distinct `(core_lot, core_slot)` | 203 | 200 |
| rows with blank `wafer_id` | 9,674 | 9,674 |
| `valid_die_ref` rows / meta | 4,598 / 8 | 4,337 / 7 |
| indexes on `core_wafer_map` | 9 (identical set) | 9 (identical set) |
| `relpages` / `reltuples` | 587 / 24,203 | 586 / 24,200 |

2 % apart in size with an identical index set, so the timing transfers in shape.
The difference that *does* matter is not size, it is the three no-separator ids
(§3.2).

### 3.5 Probe cleanup, proven

```
assy_qa        probe indexes=[]   migration index present=False
assy_manager   probe indexes=[]   migration index present=False
```

`SELECT indexname FROM pg_indexes WHERE indexname LIKE 'zz_probe%'` returns empty
on both. `assy_manager` was opened read-only (`conn.set_session(readonly=True)`)
for every fact query and received no DDL and no DML at any point.

⚠️ **One honesty note on that belt.** For the two catalog runs against
`assy_manager` (§5) I tried to force read-only through the DSN
(`options=-c default_transaction_read_only=on`); it did **not** take —
`SHOW transaction_read_only` printed `off`. Those runs were still write-free, but
the guarantee rests on the code path rather than on the belt I intended:
`resolve_reference_catalog` issues five statement shapes and the full census shows
all five are `SELECT`, the session is `autocommit=False` with nothing added to it,
and it was closed without commit.

---

## 4. 🔴 Sequencing — the two halves are one repair, and the order is fixed

`map_overlay_config.json` is re-read on every call. **Task B is already live on the
owner's stack; Task A is a manual `psql` run that has not happened.** Right now the
owner's box is in cell **S2d** — the slowest cell in the whole table.

Recommended order:

1. `psql "$DATABASE_URL" -f server/migrations/add_core_wafer_map_key_index.sql`
   against `assy_manager` (CONCURRENTLY, no lock, additive).
2. Confirm `idx_core_wafer_map_map_key` is `indisvalid`.
3. Then the config change is already in place and the route lands in **S3d**.

If you want the config change held until the index exists, revert lines
`server/config/map_overlay_config.json` `key_columns` to `["wafer_id"]` — it takes
effect on the next request, same as the change did.

---

## 5. Offered floors, before and after (Task D)

Measured by running the real `resolve_reference_catalog` against each database,
once per declaration. Not reasoned.

### `assy_manager` (the owner's box) — **11 → 209**

| | offered | breakdown | not offered |
|---|---|---|---|
| BEFORE (`wafer_id`) | **11** | `valid_die_ref` 8 + `core_wafer_map` 3 | 201 × `no_cells` |
| AFTER (composite) | **209** | `valid_die_ref` 8 + `core_wafer_map` 201 | 3 × `key_unsplit` |

### `assy_qa` — **7 → 207**

| | offered | breakdown | not offered |
|---|---|---|---|
| BEFORE (`wafer_id`) | **7** | `valid_die_ref` 7 | 200 × `no_cells` |
| AFTER (composite) | **207** | `valid_die_ref` 7 + `core_wafer_map` 200 | 0 |

The count changes, so the drift *is* the cause of the refusals and the premise
holds. Two details it does not cover:

- The three offered today are `SYN-CORE-WAFER-01/02/03` — the only rows registered
  under the `wafer_id` spelling. After the change they are refused
  `REF_REFUSAL_KEY_UNSPLIT`, whose message names the key columns and the bound
  values, so the operator is told *why* rather than silently losing them. Net +198.
- Those same three are what makes `_count_cells_bulk` decline (§3.2). Re-registering
  them under the composite spelling would both restore them and put the owner's box
  in cell S3 instead of S3d. That is a data ruling, not a code one — F2 below.

---

## 6. Findings for you to rule on — NOT fixed

**F1 — `server/migrations/migrate_map_meta_to_wafer_id.py` is obsolete and its
docstring asserts something false.** It documents a 2026-08-10 `table_config`
change that does not exist in the tree (you reverted the `.sample` half in
`272da5b`), and its own guard refuses to run because of that. It is a 656-line
script whose header would convince a future reader that `wafer_id` is the intended
identity. Retire it, or rewrite the header to record that the direction was
reversed. I did not touch it.

**F2 — three meta rows on `assy_manager` carry the retired spelling** and, as a
side effect, disable bulk counting for the whole table (§3.2). Re-registering
`SYN-CORE-WAFER-01/02/03` under `core_lot||'_'||core_slot` would recover both.
They look like seed/synthetic rows (`SYN-` prefix); `assy_qa` has none.

**F3 — the duplicate declaration is still a duplicate.** I restated the composite
in `map_overlay_config.json` as instructed. The file's own `__derived_note` says to
declare a binding *only* where the coordinate columns depart from convention —
`key_columns` is not a coordinate column, and the per-key inheritance built on
2026-08-11 (`test_omitted_key_inherits_map_key_columns_not_lot_slot`) exists
precisely so this key can be deleted. **Measured: deleting it resolves identically**,
including the client-facing `/api/maps/paint-rules` payload —

```
(a) restate  key_columns=['core_lot','core_slot']  origin='declared'   from=map_overlay_config
(b) delete   key_columns=['core_lot','core_slot']  origin='inherited'  from=table_config
    resolve_binding(a) == resolve_binding(b)  ->  True
    resolve_binding_info identical, both source='declared'
```

Only `/admin/config/resolve`'s provenance line differs. Deleting the key leaves one
copy of the identity instead of two, which is the class of defect this whole round
is about. Your call; I did not do it unasked.

**F4 — 5 pre-existing test failures, not mine.** `test_map_alignment_columns.py`
(4) and `test_map_alignment_single_key.py` (1), all failing with
`Enrichment rule '<x>_test_rule' is not an alignment rule`
(`server/alignment_view_service.py:28`). Proven pre-existing by A/B: I built a
copy of `server/config` with `key_columns` restored to `["wafer_id"]`, pointed the
suite at it via `ASSY_DATA_ROOT`, and got the **identical 5 failures**.
`alignment_view_service.py` is committed and unmodified (mtime 08-10). The rest of
the round is green: **154 passed** across `test_map_alignment_references.py`,
`test_map_overlay.py`, `test_binding_refusal.py`, `test_map_alignment_columns.py`,
`test_alignment_batched_reads.py`, `test_map_alignment_single_key.py`.

**F5 — `valid_die_ref` has the same missing index**, keyed `(product, type)` from
`table_config` (it declares no overlay binding). Only 7–8 candidates and 4.3k rows,
so it costs ~7 ms today and I left it alone. It grows the same way
`core_wafer_map` did.

**F6 — 7 leftover `ZZ3PATH*` / `ZZR4*` meta rows on `assy_qa`** (`dt_log`, created
2026-08-11 17:54–18:27) from an earlier lane. Not mine, not on the path I measured.

---

## 7. Files changed (working tree — not committed, not staged)

```
M  server/config/map_overlay_config.json          (gitignored; live, already in effect)
M  server/config/map_overlay_config.json.sample   (tracked twin, identical change)
?? server/migrations/add_core_wafer_map_key_index.sql
?? server/migrations/add_core_wafer_map_key_index_reverse.sql
```

`client2/**` untouched. No commit, no `git add`, no push, no stash. Neither stack
restarted. No migration run against `assy_manager`.

**Living documents this touches, not updated** (outside Tasks A/B, handing over):
`guide/CONFIG_GUIDE.md` already carries a 함정 A-4 about this exact file from
`272da5b` and now needs its sibling — the overlay half of the same drift;
`architecture/data_model.md` for the new index; `guide/DEPLOY_SETUP.md` and
`process/PRODUCTION_READINESS.md` for the manual migration step;
`qa/FEATURE_CHECKLIST.md` for the offered-floor behaviour change.

## 8. Proposed memory entries (server-pm) — for your review, not added

- **함정**: 성능 귀속표를 **다른 커밋 시점의 보고서에서 인용**한다. 「인덱스가 78%」는
  측정 당시 참이었고 그 뒤 `_count_cells_bulk`가 착지하면서 거짓이 됐다 — 후보마다 돌던
  스캔이 아예 발행되지 않는다. **올바른 방법**: 귀속은 인용하지 말고 다시 잰다. 옛 표를
  근거로 쓸 때는 그 사이에 들어온 커밋을 먼저 센다.
- **함정**: 프로브 인덱스를 **자기가 만들 것만 드롭**한다. 앞 셀의 인덱스가 살아남아
  「문장이 더 많은 셀이 더 빠르다」는 불가능한 표가 나왔다. **올바른 방법**: 매 셀에서
  프로브 접두 전체를 드롭하고, **타이밍 직전에 살아 있는 집합이 기대 집합과 같은지
  단언**한다.
