# Server — Virtual-column search & filter, and the write-boundary normalization

Round: 2026-07-31. Sorting explicitly out of scope (user ruling: "정렬은 안해도되고 검색만되게해").
Mid-round ruling that reshaped the fix: "그냥 \t 같은데 안들어가게 막아".

---

## PART 0 — GATE 1 MEASUREMENT (read-only, before any implementation)

### Verdict: the divergent set is EMPTY. **No backfill is needed.**

Every query below ran in a `SET SESSION READ ONLY` psycopg2 session
(`conn.set_session(readonly=True)`). No DDL, no writes, no DROP.

### Method

Python's `str.strip()` removes every codepoint where `str.isspace()` is true. I built that
set rather than typing it out — a hand-written list is one more chance to be wrong:

```python
PY_WS = "".join(chr(c) for c in range(0x110000) if chr(c).isspace())
```

**29 codepoints**: U+0009 U+000A U+000B U+000C U+000D U+001C U+001D U+001E U+001F U+0020
U+0085 U+00A0 U+1680 U+2000–U+200A U+2028 U+2029 U+202F U+205F U+3000.
Postgres `btrim(x)` with no second argument strips exactly one of them (U+0020), so
**28 codepoints are the divergence**.

Detection avoids regex-escape ambiguity entirely by using `translate()` to delete the
whole class and asking whether anything is left:

```sql
SELECT count(*) FROM "<table>"
 WHERE "<col>" IS NOT NULL
   AND btrim("<col>"::text) <> ''            -- SQL says: non-empty
   AND translate("<col>"::text, :py_ws, '') = ''   -- Python says: empty
```

### Result 1 — the six declared join columns (as briefed)

Live declaration is `bonding_log_wafer_id`: `bonding_log ⋈ core_wafer_map` on
`(core_lot, core_slot)`, exposing `wafer_id`. `wafer_id` exists on **both** sides, so it is
a `collide` column and `virtual_only` is empty.

| table | column | role | physical type | divergent | rows |
|---|---|---|---|---|---|
| bonding_log | core_lot | join_key left | character varying | **0** | 15,434 |
| bonding_log | core_slot | join_key left | character varying | **0** | 15,434 |
| bonding_log | wafer_id | expose COLLIDE (left) | character varying | **0** | 15,434 |
| core_wafer_map | core_lot | join_key right | character varying | **0** | 80 |
| core_wafer_map | core_slot | join_key right | character varying | **0** | 80 |
| core_wafer_map | wafer_id | expose (right) | character varying | **0** | 80 |

### Result 2 — broad sweep, every configured column of every configured table

Because the normalization fix is a funnel fix, the backfill question is system-wide, not
join-column-only. **20 tables, 2,340,938 rows: divergent = 0. Zero columns with hits.**

`bonding_log` 15,434 · `bonding_map` 1,760,871 · `core_defect_map` 103,040 ·
`core_wafer_map` 80 · `dt_log` 768 · `dt_map` 2,922 · `eds_fail_map` 103,040 ·
`inventory_master` 339,297 · `large_table_100` 1,000 · `line_model_registry` 3 ·
`map_doe` 0 · `map_doe_source` 0 · `map_split_registry` 144 · `parts` 0 ·
`production_plan` 505 · `sample_map` 447 · `test` 124 · `wafer_map_metadata` 217 ·
`wafer_process` 13,039 · `wafer_slot_history` 7.

### Result 3 — `cell_sources.value`, the layering source of truth

13,156,161 rows, `json` column, extracted with `value #>> '{}'`. A 1% `TABLESAMPLE`
returned 0/134,678 in 0.7s; I ran the **exact full scan anyway** (a 1% sample cannot prove
absence) — **20.5s, divergent = 0.**

### Result 4 — the wider set the normalization ruling implies

Gate 1 as briefed asks for whitespace-*only* values. The write-normalization ruling implies
a bigger question: how many stored values would *change* if the boundary stripped them
(i.e. `str(v).strip() != v` — any leading/trailing whitespace)?

**Also 0**, across all 20 tables plus every `business_key_val`, and 0 across all
13,156,161 `cell_sources` rows.

### Result 5 — the second divergence (float fold), as asked

`clean_str_value(7.0)` is `"7"`; a `7.0` stored into a varchar renders `"7.0"`.

- **Is any declared expose column numeric?** No. `core_wafer_map.wafer_id` is declared
  `string` and is physically `character varying`. So this does not affect capability (2)
  for the current declaration.
- **Do any string-declared columns hold an `N.0`-shaped value today?** I scanned every
  non-`number` column of every configured table for `^-?[0-9]+\.0+$`: **0**.
- contract-keeper measured the render side independently and its skip message records:
  *PostgreSQL 18.3 renders float 7.0 as `'7'`, matching `clean_str_value`, while SQLite
  renders `'7.0'` and does not.* So on the production dialect this divergence does not
  arise; it is a SQLite-only artefact, and it is unscored on PG until someone runs the
  contract with `ASSY_CONTRACT_PG_URL`.

### Why it is empty — the structural reason, not luck

`crud.cast_value_by_type` has always had `if value is None or str(value).strip() == "":
return None` as its **first line**, and `apply_row_update_internal` (whose only caller is
the `apply_batch_updates` funnel) runs every value through it. A bare tab could already
never be stored. The user's ruling was therefore **already half-implemented**; what was
missing was the other half — a *non-empty* value kept its surrounding whitespace verbatim
(`" WF-1 "` → stored `" WF-1 "`), because the string branch was `return
sanitize_to_utf8(value)`. Result 4 shows nothing has actually exercised that hole (the
parsers happen to strip), so the invariant held **by accident, not by construction**.

**This distinction is the whole finding**: nothing to backfill, but nothing enforcing it
either. The change below makes it structural.

---

## PART 1 — Write-boundary normalization (the primary fix)

`server/database/crud.py`

- **`normalize_stored_text(value)`** — strips a `str`, returns anything else untouched.
  Lists/dicts (the JSON columns; `map_doe.mat_*` where "the token text IS the identity")
  are containers, not text, and are not this boundary's business.
- **`cast_value_by_type`** now ends `return sanitize_to_utf8(normalize_stored_text(value))`.

Placed at the funnel, per the precedent of `refuse_virtual_join_columns`: a per-call-site
rule is one the next author has to remember.

### The paired spellings, in one place (`crud.py`, adjacent by design)

| name | side | meaning |
|---|---|---|
| `is_blank_value(val)` | Python | `clean_str_value(val) == ""` — names what `_resolve_one`, `AutoConfirmCollector.flush` and `enrichment_candidates` each spelled out inline |
| `blank_sql_condition(col)` | SQL | `col IS NULL OR col = ''` — **no `btrim`** |
| `not_blank_sql_condition(col)` | SQL | `col IS NOT NULL AND col <> ''` |
| `blank_to_null(col)` | SQL | `CASE WHEN blank_sql_condition(col) THEN NULL ELSE col END` |

`blank_to_null` is deliberately **not** `NULLIF(col,'')`: that would be a third spelling of
"blank", identical today and free to drift tomorrow. Deriving it means the resolved value
cannot disagree with the emptiness test it is built from.

`blank_sql_condition` carries the note that it is *only correct because storage is
canonical*, and that a `btrim` added here means the real bug is upstream.

### What each of `apply_batch_updates`' non-HTTP callers sees (asked for explicitly)

Normalization happens inside `cast_value_by_type`, i.e. **below** all of them — none passes
a flag, none can opt out, none needs changing.

| caller | what changes |
|---|---|
| `chain_ingestion_worker.process_chain_transaction_group` | chained values land stripped. Downstream comparisons already used `clean_str_value`, so the chain's own equality checks are unaffected; storage now matches what they compute. |
| `chain_replay` | replay re-applies through the same path **and** calls `cast_value_by_type` directly (`chain_replay.py:583`), so a replayed value is normalized identically to the original write — replay stays byte-reproducible. |
| `enrichment_candidates.confirm_keys` (auto-confirm) | writes are stripped. Its absent-only gate asks `cell_sources` for provenance, not for text, so gate behaviour is unchanged. |
| `map_meta_registrar` | map identity values are stripped. `map_key_canonicalization` already folded `' 1 '`→`'1'` for `number`-declared columns; string-declared identity columns now agree with it instead of trailing behind. |
| `parsers/directory_watcher` (ingestion) | the largest volume path. Parsers already stripped, which is why Result 4 is 0 — this makes it enforced rather than assumed. `rel_path`-carried values are filesystem paths and have no significant edge whitespace (asserted, see below). |
| `enrichment_backfill` script | same as ingestion. |

### Verification that nothing depended on preserved whitespace (asked for explicitly)

I checked the three paths this project deliberately round-trips raw text through, and
pinned each as an assertion rather than a claim:

1. **The `'0x10'` / `'7.5'` map-push case** (`transfer_plan` `stack`, declared `string`
   precisely so `cast_value_by_type` cannot raise on `'0x10'` or silently repair `'7.5'`).
   Stripping touches only the edges; neither value moves.
   `test_unreadable_text_still_survives_the_round_trip` asserts `0x10`, `7.5`, `nope`,
   `1.0`, `01`, `a b  c` all come back byte-identical.
   `test_transfer_plan.py` (the canonical version) passes unchanged.
2. **The folder-structure-preserving ingestion**, where the relative path is the carrier
   (`directory_watcher` `rel_path`, POSIX-separated, computed once per file).
   `test_interior_whitespace_is_never_touched` asserts `" sub dir/a  b/c.csv "` →
   `"sub dir/a  b/c.csv"` — edges only, interior runs and separators intact. Windows
   forbids trailing spaces in path components, so the edges carry nothing.
3. **The JSON array columns** (`map_doe.mat_1h/mat_mid/mat_top`, raw material tokens where
   `product_tables` records what happened the last time a token's text was assumed
   reformattable). `test_a_list_value_is_returned_untouched` asserts lists, dicts, floats
   and `None` pass through `normalize_stored_text` unchanged.

I also confirmed there is **no bulk write path that bypasses the funnel**:
`grep bulk_insert_mappings|bulk_save_objects|bulk_update_mappings|copy_from|copy_expert`
over `server/` returns exactly one hit, `crud.py:469`, and it targets `AuditLog`, not a
dynamic table.

---

## PART 2 — Search & filter on virtual-join columns

### `server/virtual_join_executor.py`

- **`exposed_columns(db, left_table) -> set`** — every column a verified join contributes,
  `collide` **and** `virtual_only`. Deliberately wider than `announced_columns`, which
  answers the narrower "what must `/schema` *add*" and therefore omits collide columns.
  Searching only the stored half of a collide column is exactly the
  "rows look filtered while the count does not" defect.
- **`resolved_expression(db, left_model, left_table, col_name, query) -> (query, expr, label)`**
  — returns the query with one LEFT OUTER JOIN added per contributing rule, plus
  `COALESCE(blank_to_null(left)?, blank_to_null(right₁), …, label)`.

`attach`'s rule translated, not re-derived: left value if non-empty, else first non-empty
joined value **in rule order**, else the label. `COALESCE` *is* "first non-null wins";
`blank_to_null` is what turns "non-empty" into "non-null" using the one shared declaration.
The label comes from the first rule exposing the column, matching `attach`'s
`labels.setdefault` and `announced_columns`.

Right sides are `aliased()` per rule — two declarations may name the same right table.

### Why a JOIN and not a correlated subquery

The expression sits in `WHERE`, so it is evaluated against the whole left table, not one
page. A correlated scalar subquery is one index probe **per left row** — 10 million on a
10-million-row table. A LEFT JOIN lets the planner hash the right side once.

This is only safe because `virtual_join_config` refuses to verify a declaration whose right
side lacks a UNIQUE index covering the join key, so output rows == input rows —
which is what keeps `query.count()` honest and pagination undisturbed. Measured, not
assumed (below), and asserted by `test_the_join_cannot_change_the_row_count`.

### `server/main.py`

- `get_column_filter_condition(..., col_expr_override=None)` — an override evaluates the
  filter against that expression instead of a model lookup, reusing the **entire** operator
  vocabulary (contains/notContains/equals/notEqual/startsWith/endsWith/inRange/blank/…)
  rather than growing a second, thinner translator. Recursion passes it through, so
  compound AND/OR filters work on virtual columns too. The two other callers
  (`enrichment_analysis._queue_condition`, `export_table_csv`) are unaffected — the param
  is optional. Grepped: 4 call sites, all accounted for.
- `get_table_data` resolves `virtual_cols` once per request and memoizes each column's
  expression, so `?filters=` and `?q=` naming the same column pay for one join, not two.
- **Unscoped `?q=`** now unions in `virtual_only` columns. They are not in
  `column_types` (they are not stored), so the default column list skipped them — the grid
  displayed a column that the all-columns search could not see.

### How much simpler the SQL got, thanks to the normalization (asked for explicitly)

The emptiness arm is `col IS NULL OR col = ''` — **no `trim()` anywhere in the generated
SQL**. Without canonical storage it would have had to be either `btrim(col)` (wrong: 1 of
29 codepoints — the under-report the round exists to prevent) or a 29-character
`translate()`/character-class that every schema change silently invalidates. Concretely,
here is the whole predicate as Postgres received it:

```
COALESCE(
  CASE WHEN ((l.wafer_id IS NULL) OR ((l.wafer_id)::text = ''::text))
       THEN NULL ELSE l.wafer_id END,
  CASE WHEN ((r.wafer_id IS NULL) OR ((r.wafer_id)::text = ''::text))
       THEN NULL ELSE r.wafer_id END,
  '미상')
```

**Residual divergence surviving normalization** — one, and it is not reachable in
production: the float fold (`clean_str_value(7.0)=='7'` vs a rendered `'7.0'`).
It cannot affect the *emptiness* test at all, only capability (2)'s equality on a
`number`-declared expose column. No declared expose column is numeric (Gate 1 result 5),
no string column holds an `N.0` value (0 rows), and PostgreSQL renders `7.0` as `'7'`
anyway. It is scored as a pending axis by contract-keeper, not by me.

---

## PART 3 — The pre-existing `?cols=` defect

**Confirmed and reproduced.** `?cols=<column that builds no condition>` appended nothing,
and because the route only applies `or_(*conditions)` when at least one survives, a scope
consisting entirely of such columns **skipped filtering and returned the whole table with
200** while implying that column had been searched.

Defect-injection output, verbatim: `expected a refusal, got 200 with 5 rows`.

Fixed by refusing:
- scope has **nothing** searchable → **400**, naming the offending columns.
- scope is **partly** searchable → search the rest, log-and-drop the unknown. Refusing the
  whole request would turn a stale client column list into an outage, and the
  honest-response property is already satisfied.
- unscoped `?q=` cannot reach the refusal (it always contributes `row_id` and
  `business_key_val`).

I also closed the same hole in the `?filters=` path: a column known to be virtual whose
expression could not be built now refuses rather than silently dropping the condition and
returning **more** rows than asked. The surrounding `except Exception` re-raises
`HTTPException` so a deliberate refusal is not swallowed back into the silent 200.

---

## PART 4 — Measurements (EXPLAIN ANALYZE, live DB, read-only)

Prose about plans is not data, so: `EXPLAIN (ANALYZE, BUFFERS)`, queries built **through
`resolved_expression` itself** so the plan measured is the plan production gets.

### A. The declared join — `bonding_log` (15,469 rows) ⋈ `core_wafer_map` (80)

| query | plan | exec | buffers | rows out |
|---|---|---|---|---|
| baseline: stored `wafer_id ILIKE '%WF%'`, no join | Seq Scan | 4.4 ms | 654 | **0** |
| cap 2: resolved `ILIKE '%WF%'` | Hash Left Join | 16.7 ms | 658 | **9,184** |
| cap 1: resolved `= '미상'` | Hash Left Join | 9.2 ms | 658 | **4,051** |

**Fan-out: 15,469 → 15,469, ratio 1.000000.**

🔴 **The headline number.** Searching `wafer_id` for `%WF%` returned **0 rows** before and
**9,184 rows** now. The grid was displaying 9,184 rows whose `wafer_id` contains "WF" while
the search insisted none existed. 4,051 rows (26.2%) resolve to `미상` — which independently
reproduces the 26.27% the executor's docstring measured for this same pair.

### B. Scale probe — `core_defect_map` (103,040 rows) ⋈ `core_wafer_map` (80), virtual_only shape

Raw `EXPLAIN` only; declares nothing, writes nothing. 6.7× the left rows, and the *other*
half of the shape (`core_defect_map` has no `wafer_id` of its own).

| query | plan | exec | buffers |
|---|---|---|---|
| baseline: no join, seq scan + ILIKE | Seq Scan | 54.6 ms | 2,100 |
| cap 2: resolved `ILIKE '%WF%'` | Hash Left Join | 104.8 ms | 2,104 |
| cap 1: resolved `= '미상'` | Hash Left Join | 44.1 ms | 2,104 |
| cap 1 `count(*)` (what `total` runs) | Hash Left Join over **Index Only Scan** | 44.6 ms | **314** |

**Fan-out: 103,040 → 103,040, ratio 1.000000.** 87,584 rows (85.0%) resolve to `미상`.

**What the buffer numbers say**: the join adds **exactly 4 shared buffers** at both 15k and
103k left rows — the right table's 4 pages, hashed once (`Buckets: 1024 Batches: 1 Memory
Usage: 12kB`). The join's I/O cost is a function of the **right** table's size, not the
left's. The left scan is a Seq Scan in the baseline too, because `ILIKE '%…%'` is not
indexable either way — the join is not what forces the scan.

The count query planned **better** than the row query (314 buffers vs 2,104): only
`(lot, slot)` are needed, so Postgres chose an index-only scan.

### What these numbers do NOT prove — stated rather than extrapolated

- **No live table pair exceeds 103,040 left rows on a declared join key.** I did not
  extrapolate to 10M. The structural argument (cost scales with the right table) is
  supported by the buffer deltas being identical at two left-table sizes, but that is an
  argument, not a 10M measurement.
- **The right table here is 80 rows.** `Batches: 1` at 12 kB. If a right table were large
  enough that the hash exceeds `work_mem`, Postgres would spill to multiple batches and
  these numbers would not transfer. The verification gate makes the right side unique on
  the join key — a dimension table by construction — but "dimension" does not bound size.
  **This is the number I would most want re-measured** if a declaration ever names a large
  right table.
- Execution-time comparisons between baseline and cap 2 are **not like-for-like**: the
  baseline emitted 0 rows and cap 2 emitted 9,184 / 12,880.

---

## PART 5 — Tests

`conda run -n assy_manager python -m pytest server/tests/ -q -rs`
→ **1788 passed, 1 skipped** (the skip is contract-keeper's documented pending axis).

New: `server/tests/test_stored_text_normalization.py` (8) ·
`server/tests/test_virtual_column_search.py` (12).

### Defect injection — every "this was broken" claim was actually run

| injection | RED |
|---|---|
| A: `cast_value_by_type` → `return sanitize_to_utf8(value)` | 3 — `test_surrounding_whitespace_never_reaches_storage` (`'\tWF-1 ' != 'WF-1'`), `test_interior_whitespace_is_never_touched`, `test_business_key_and_column_agree_after_normalization` (`'  K1  ' != 'K1'`) |
| B: whitespace-only→NULL weakened to `value == ""` | 5, incl. `test_a_whitespace_only_value_is_stored_as_null` (`U+0009 reached storage`) and the corpus test: *"C001: stored '\t' — Python says blank=True, SQL says blank=False. Storage is no longer canonical."* |
| C: collide column routed back to the stored column | `test_search_on_a_collide_column_sees_the_JOINED_value` → `assert set() == {'L2'}` |
| D: `?cols=` refusal branch removed | `test_cols_naming_a_column_that_cannot_be_searched_is_refused` → *"expected a refusal, got 200 with 5 rows"* — the pre-existing defect, exactly |

🔴 **One honest correction.** My first draft of the corpus test's docstring claimed it was
RED before this round. Injection A proved it **green** — padding changes a value's
*equality*, not its *blankness*, so blankness-agreement cannot detect a missing strip. I
rewrote the docstring to say so and to record which injection each assertion actually
answers. Without running the injection I would have shipped a false coverage claim.

### One existing test needed a fixture change, and it caught the change itself

`test_enrichment_candidates.test_a_clipped_distinct_read_is_refused_even_when_it_folds_to_one_value`
depends on `'WF01 '` being **stored with its trailing space** so the clipped GROUP BY
results fold to one value. Normalization removed that storage route, and the test failed
**with its own self-guard message** — *"fixture no longer activates the defect axis"* —
rather than quietly becoming a test of `ambiguous`. That guard is why this was a two-minute
diagnosis.

Fixed with a `_seed_raw` helper that writes to the model directly, mirroring
`test_virtual_join_executor._seed_raw`. **This is legitimate, not a workaround**: that
module probes a **user-declared reference VIEW**, which is arbitrary SQL and can synthesize
values that never passed the write boundary (a concatenation, a CAST, a join against a
table nobody here manages). `enrichment_candidates` must not lean on a normalization
invariant it does not own.

---

## PART 6 — Coordination, scope, and open items

### contract-keeper (parallel)

It landed `contracts/blank_predicate/` + `server/tests/test_blank_predicate_contract.py`
and is scoring exactly the names I introduced — `is_blank_value`, `blank_sql_condition`,
`not_blank_sql_condition`, `normalize_stored_text`. Its vectors pass against this
implementation. **I did not duplicate its corpus**; my corpus test asserts the narrower
"nothing a *write* can produce diverges", which is the write-boundary property, while the
contract scores the two spellings against the shared vector file.
**I do not disagree with the split.**

### CSV export — left alone deliberately, and now DIVERGENT

`export_table_csv` contains a **verbatim copy** of the search block (its own comment says
"get_table_data와 검색 로직 동기화"). It therefore still has the `?cols=` whole-table defect
and still cannot filter a virtual column. Per the round's explicit scope I did not touch it,
and I did **not** add a per-chunk attach (that path streams through one server-side cursor;
a mid-stream failure would arrive after 200 OK and hand the user a truncated CSV that looks
complete).

**What export can reuse when its round comes**: `exposed_columns`, `resolved_expression`
(it pushes into the WHERE of the single streamed query and adds **no** per-chunk query —
safe for the cursor), and `get_column_filter_condition(..., col_expr_override=)`. Flagged
as a background task (`task_f39d708f`), including the note that the real root cause is the
duplicated block.

### Boundary contracts — none changed

No REST signature, path, WS event name or payload, cell shape, or `/schema` response
changed. `get_column_filter_condition` gained an **optional** kwarg (internal, not
client-facing). The only externally visible change is a **new 400** where the route
previously answered 200 with unfiltered rows — which is the fix.

⚠️ **One item for the Client PM, via 총괄.** `blank`/`notBlank` on a virtual column now
match **nothing** / **everything**, because the resolved value COALESCEs to a non-empty
label and no cell in that column ever *displays* as blank. That is the honest answer, and
"show me the unresolved rows" is `equals <unresolved_label>`. If AG-Grid offers a "Blank"
option on those columns the user will find it useless — worth a client-side decision.

### Also changed, and worth a look

`SET LOCAL work_mem = '64MB'` in `get_table_data` is now dialect-guarded. It is
Postgres-only and raised `OperationalError: near "SET": syntax error` on SQLite, which made
the **entire `?q=` path unreachable from the test suite** — no test could reach a search, so
nothing about search behaviour was pinned. Production is unaffected (always Postgres); what
changed is that the path is now testable. This was blocking capability (2)'s tests.

### Files

`server/database/crud.py` · `server/main.py` · `server/virtual_join_executor.py` ·
`server/tests/test_enrichment_candidates.py` (fixture) ·
`server/tests/test_stored_text_normalization.py` (new) ·
`server/tests/test_virtual_column_search.py` (new). Not committed — for review.

### CODE_MAP anchor drift observed (against HEAD, before my edits)

| symbol | CODE_MAP says | actual | drift |
|---|---|---|---|
| `get_column_filter_condition` | ~1158 | 1175 | +17 |
| `export_table_csv` | ~1637/1638 | 1655 | +17 |
| `cast_value_by_type` / `clean_str_value` | ~309/326 | 309/326 | exact |
| `virtual_join_config.py` length | 475 lines | 512 | +37 |

### Proposed memory entries (for 총괄 review — not added directly)

1. **함정**: 두 구현이 같은 판정을 해야 할 때 SQL 쪽을 파이썬에 맞춰 흉내내면
   (`btrim` vs `str.strip()`: 1 codepoint vs 29) 조용한 과소보고가 된다.
   **올바른 방법**: 흉내내지 말고 **쓰기 경계에서 정규화**해 저장을 정본으로 만든다 —
   그러면 두 철자가 "맞춰서"가 아니라 **구조적으로** 일치하고, SQL이 짧아진다.
   경계는 호출부마다가 아니라 깔때기(`cast_value_by_type`/`apply_batch_updates`)에 둔다.
2. **함정**: "이 테스트는 고치기 전에 빨갰다"를 **돌려보지 않고** 보고서에 적는다.
   실제로 이번에 corpus 테스트가 초록이었다 — 패딩은 *동등성*을 바꾸지 *공백성*을 바꾸지
   않기 때문. **올바른 방법**: 주장할 결함마다 주입을 **실제로 실행**하고, 어느 주입이
   어느 단언을 빨갛게 만드는지 테스트 docstring에 적는다.
3. **교훈(좋은 사례)**: `test_..._folds_to_one_value`처럼 **픽스처가 결함 축을 여전히
   활성화하는지 테스트 자신이 단언**하면, 무관해 보이는 상류 변경(쓰기 정규화)이
   테스트를 조용히 무력화하는 대신 자기 진단 메시지와 함께 빨개진다. 진단이 2분에 끝났다.

---
---

# ROUND 2 — CSV export carries the join, and the DUP1 funnel fold

Appended rather than split into `Server_virtual_column_csv_export.md`: the export section
leans on Round 1's measurements throughout, and the DUP1 finding is a correction to
Round 1's own work. One file, one narrative. **Nothing committed.**

## Headline

🔴 **The `wafer_id` column in the `bonding_log` extract was blank for 100% of rows while
the screen showed a value for 74% of them and `미상` for the rest.** 15,504 rows compared
against `/tables/{t}/data`, **0 value mismatches, 0 row-alignment errors** after the fix.

🔴 **DUP1 was a real miss in my Round 1 work, and contract-keeper's proof is the part that
matters**: patching `crud.blank_sql_condition` did not change the operator's AG-Grid
"Blank" filter, because `main.get_column_filter_condition` — the busiest caller of the
rule — never folded onto the spelling I extracted. I built the funnel and left the main
road around it. Now folded; re-running that same injection turns the filter tests red.

---

## PART 7 — The export (`/tables/{t}/export`)

### The shape that made this more than an append

`exposed_columns` returns two kinds, and only handling one would have shipped a no-op:

| kind | header | what changes |
|---|---|---|
| `collide` | **already there** | the *expression* filling it. Selecting the raw stored column is the "empty cell where the screen said 미상" lie |
| `virtual_only` | **new slot** | the column did not exist in the extract at all |

The production declaration was `collide` when I started this round and `virtual_only` by
the time I finished (below), so both paths are exercised on live data.

### Implementation

The join is in the **same statement** — one `LEFT OUTER JOIN` per rule folded into the
single streamed query via `resolved_expression`, exactly as the WHERE path does.
No per-chunk attach. Measured: **3 SELECTs total** (10-row sample, count, stream), and
**still 3 at 12,005 rows** — i.e. across 3 `yield_per` chunks, where a per-chunk attach
would have shown up as extra statements. That flatness is asserted at two sizes, because
one size cannot tell a constant from a small multiple.

`select_entities` and the sample query are built from **one list**, so the size estimate
cannot silently under-report — the thing the brief asked me to check. Measured:
`X-Estimated-Content-Length` 1,894,679 vs actual 1,856,347 bytes → **+2.07% over**.
A sample missing the resolved column would have landed far under.

**Header order.** Virtual columns go after the business columns and **before**
`created_at`/`updated_at`, keeping the system pair last — which the row writer depends on
positionally (`row[-2]`, `row[-1]`). Their relative order is `announced_columns`', the
same source and order `/schema` gives the grid.

⚠️ **A pre-existing order discrepancy I did NOT change**: the extract sorts business
columns **alphabetically** (`sorted(col_types)`), while the grid uses `display_columns`
order. So the CSV never matched the screen's column order and still does not. Reordering
would break every downstream consumer of the extract, so I left it and am flagging it
rather than fixing it silently. What I did guarantee is that header cells and selected
values cannot drift apart — `len(header) != len(select_entities)` is now a hard 500,
because a shifted extract *opens fine* and is simply wrong under the wrong headings.

**`select_entities` has no `row_id`** — confirmed it no longer matters. It mattered for a
post-hoc attach keyed on row_id; the in-SQL form joins on the declared key and never needs
it. Not added (it would change the extract's column set).

### The `?cols=`/`?filters=` duplication — answered, not noted

**They can share one implementation, and now do.** `main.py` gained `VirtualColumnBinder`,
`apply_column_filters` and `apply_search_filter`; both routes call them.

The proof that the unification is real rather than cosmetic: **one injection (removing the
`?cols=` refusal) now turns BOTH routes red** —
`test_cols_naming_a_column_that_cannot_be_searched_is_refused` (grid, *"got 200 with 5
rows"*) and `test_cols_naming_an_unsearchable_column_is_refused_in_the_export_too`
(export, *"got 200 with 6 lines"* = header + all 5 rows). Before this round the export
copy had no refusal at all.

### Live verification (read-only, route functions called directly — no app startup)

Extracted `bonding_log` and diffed the virtual column against `/tables/{t}/data` page by
page.

⚠️ **The comparison could not be keyed on the business key** — my own guard caught that
`log_id` is **not unique** (129 duplicates in 15,504 rows). Both routes default to
`order_by=row_id asc` and `row_id` is the primary key, so the ordering is a *total* order
and positional alignment is exact — which is also what an operator comparing file to
screen actually does. Row-alignment errors: **0**, checked per row.

| | |
|---|---|
| rows compared | **15,504** |
| value mismatches | **0** |
| row-alignment errors | **0** |
| rows carrying `미상` | 4,055 (26.15%) |
| non-empty in the pre-round extract | **0 / 15,504** |
| non-empty now | **15,504 / 15,504** |
| cells the extract now reports differently | **15,504 / 15,504 (100.00%)** |

🔴 **The config changed under me mid-round and that turned into the strongest evidence I
have.** First run measured `collide=['wafer_id'], virtual_only=[]`; the last measured
`collide=[], virtual_only=['wafer_id']` — `wafer_id` was removed from `bonding_log`'s
`table_config` while I worked. **Both runs produced 0 mismatches**, so the implementation
is verified on live data across *both* declaration shapes, and the header landed in the
same position either way. I did not plan this and would not have covered it as well
deliberately.

⚠️ **Row counts move between measurements** (15,469 → 15,489 → 15,499 → 15,504): the
watcher is ingesting. Every number above is re-derived within a single run; do not
reconcile them across runs.

---

## PART 8 — DUP1: the fold I should have done in Round 1

### What was wrong

Round 1 extracted `crud.blank_sql_condition` / `not_blank_sql_condition` and then left
`main.get_column_filter_condition` spelling both out inline. AST count: **2 blank, 3
notBlank**. The third was `enrichment_analysis._human_resolved_cells`.

contract-keeper's fault injection is what makes this worth more than a lint: patching the
extracted helper **changed nothing** in the AG-Grid blank filter. The rule had a home and
the one path an operator touches was not living in it.

### What I changed

| site | before | now |
|---|---|---|
| `main.get_column_filter_condition` `blank` | `or_(col.is_(None), col == "")` | `crud.blank_sql_condition(col_expr)` |
| `main.get_column_filter_condition` `notBlank` | `and_(col.isnot(None), col != "")` | `crud.not_blank_sql_condition(col_expr)` |
| `enrichment_analysis.py:175` | `and_(tgt.isnot(None), cast(tgt, String) != "")` | `crud.not_blank_sql_condition(cast(tgt, String))` |

**Is `enrichment_analysis` the same predicate? Yes** — the only difference was the explicit
`cast(tgt, String)`, which is load-bearing there because `target_field` can name a numeric
column and PostgreSQL rejects `double precision = ''`. Passing the cast expression in makes
it byte-for-byte the same predicate. I did **not** move the cast inside the helper: a
`CAST` wrapped around an already-varchar column can cost the planner an index. The helper
now documents "caller owns making the expression text-typed", and both callers do.

**The `is_numeric` special-case in `get_column_filter_condition` is gone, not moved.**
`blank`/`notBlank` are deliberately absent from `numeric_operators`, so `col_expr` on that
path is *always* already `cast(raw_col, String)`. A cast numeric is never `''` when
non-NULL, so `IS NULL OR = ''` returns exactly the rows `IS NULL` did — one redundant
disjunct, one fewer spelling.

**Verified by re-running contract-keeper's own injection**: with
`crud.blank_sql_condition` patched, `test_bypass_rows_diverge_exactly_as_recorded` and
`test_the_two_resolutions_diverge_on_a_bypassed_row_exactly_as_recorded` — both of which
build the condition through `main.get_column_filter_condition` — now go **red**. That is
the assertion that failed to fire when DUP1 was written.

### NUM1 — taken

`cast_value_by_type` decided int-vs-float from whether the **repr** contains `'.'`.
`str(1e16)` is `'1e+16'` and `str(1e-05)` is `'1e-05'` — neither has one — so both went to
`int()` and were refused, for ordinary doubles the `double precision` column holds exactly.

Fixed as a fallback arm: **strictly additive** — every input that already parsed takes the
original branch and returns the same type it always did; this only converts a refusal into
a value. **`nan`/`inf` stay refused** (`math.isfinite`), because a NaN in a numeric column
is a row no filter can ever find again.

### FLOAT_EXPONENT — not chased, and I agree with the ruling

It was **already** a proper `declared_divergences` entry with both measured sides
(`'10000000000000000'` vs `'1e+16'`), the mechanism, and the reach. It cannot rot into a
meaningless green because the contract asserts *both sides still give the recorded
answers*. Nothing needed doing; I confirmed rather than changed it.

### ⚠️ I edited contract-keeper's `contracts/blank_predicate/vectors.json`

Flagging this explicitly since it is another agent's file. I removed the `DUP1` and `NUM1`
entries from `known_defects`, which is what each entry's own `clears_when` instructs
("Then delete this entry"), and the contract had gone **red in the other direction**
(*"pinned 2, found 1 ... update or delete the entry"*) — a stale pin asserts nothing. I
replaced them with a `$comment` recording what cleared each, how it was verified, and that
FLOAT_EXPONENT was deliberately left. `known_defects` is now empty.

I briefly broke that file's JSON with a dangling comma while removing the last entry and
repaired it in place — worth knowing because the file is **untracked**, so `git checkout`
could not have restored it. Validated: parses, 21 corpus cases, `declared_divergences`
intact.

### The `7.0` correction, recorded where it would be re-derived

Noted in `crud.clean_str_value`'s docstring, because that is where a future reader hits it:
the fold does **not** diverge from PostgreSQL (`number`→`Float`→`double precision`, and PG
renders `cast(7.0 AS varchar)` as `'7'`). **It is the SQLite test dialect that diverges**,
so a green SQLite suite is exactly what makes people believe in a bug that is not there.

---

## Tests & results

`conda run -n assy_manager python -m pytest server/tests/ -q -rs`
→ **1802 passed, 1 skipped** (contract-keeper's documented PG-render axis).
`node contracts/blank_predicate/client_harness.mjs` → **4/4, 0 divergences**.

New: `server/tests/test_virtual_column_export.py` (14).

| injection | RED |
|---|---|
| collide column selects the raw stored column | 3 export tests — `extract='' grid='WF-1'`, `'' == '미상'` |
| `?cols=` refusal removed (shared function) | **both** routes: grid *"got 200 with 5 rows"*, export *"got 200 with 6 lines"* |
| `crud.blank_sql_condition` patched | AG-Grid blank-filter tests — **the injection that used to prove nothing** |

Not vacuous: the no-per-chunk test also asserts a statement *carried* the join, so an
empty listener list cannot pass it.

## Files (all uncommitted)

`server/main.py` · `server/database/crud.py` · `server/enrichment_analysis.py` ·
`server/virtual_join_executor.py` · `server/tests/test_enrichment_candidates.py` ·
new `server/tests/test_virtual_column_export.py` · `contracts/blank_predicate/vectors.json`
(contract-keeper's — see above).

Untouched as instructed: `docs/**`,
`client2/src/{map_editor,admin,retroactive_view,config_resolve_view}.js`, no `npm run build`.

## Numbers to re-measure

1. **15,504 rows compared, 0 mismatches, 0 alignment errors** — and **100.00%** of that
   column's cells changed.
2. **3 SELECTs** for the whole export, flat from 5 rows to 12,005.
3. Estimate **+2.07%** over actual (1,894,679 vs 1,856,347 bytes).
4. Blank spellings **2 → 1**, notBlank **3 → 1** (AST, scored by the contract).
5. `bonding_log` is now **virtual_only** for `wafer_id`, not collide — the config changed
   on 2026-07-31 mid-round. Worth confirming that was intended.

## Next round (queued, NOT started)

`/schema` gains `join_resolved_columns`. Per your instruction I did not interleave it; I
have read the brief and will start from `contracts/join_resolved_columns` once you have
this. One note in advance: the set is `exposed_columns()`, which the config flip above just
demonstrated changes shape at runtime — so the `kind` field will be computed per request
from `rules_for`, not cached.

---
---

# ROUND 3 — `/schema` gains `join_resolved_columns`

Last round of the week. Started only after the CSV round was finished, as instructed.
**Nothing committed.**

## The exact response shape, captured (client-pm handoff)

Real `GET /tables/bonding_log/schema` against the **live production database**, verbatim.
Not a schematic.

```json
{
  "table_name": "bonding_log",
  "columns": ["log_id", "eventtime", "base_id", "bx", "by", "core_lot", "core_slot",
              "cx", "cy", "created_at", "updated_at", "is_graph_synced",
              "needs_graph_rollback", "graph_synced_at"],
  "column_types": { "log_id": "string", "eventtime": "string", "base_id": "string",
                    "bx": "number", "by": "number", "core_lot": "string",
                    "core_slot": "string", "cx": "number", "cy": "number",
                    "is_graph_synced": "boolean", "needs_graph_rollback": "boolean",
                    "graph_synced_at": "datetime" },
  "business_key": "log_id",
  "composite_key_source": [],
  "map_key_columns": [],
  "map_push_ok": false,
  "virtual_columns": [
    { "name": "wafer_id", "type": "string", "editable": false,
      "right_table": "core_wafer_map", "rule": "bonding_log_wafer_id",
      "unresolved_label": "미상" }
  ],
  "join_resolved_columns": [
    { "name": "wafer_id", "kind": "virtual_only", "rule": "bonding_log_wafer_id",
      "right_table": "core_wafer_map", "unresolved_label": "미상" }
  ]
}
```

🔴 **`kind` is `virtual_only`, NOT `collide` as your brief's example showed** — and that is
not a disagreement, it is the config change I flagged in Round 2. `wafer_id` was removed
from `bonding_log`'s `table_config` during this session, so it is no longer a stored
column on that table. Your measurement was taken before the change and was correct then.
**Worth confirming the config change was intended**, because it also means the live
`bonding_log` no longer exercises the collide path at all — the collide path is covered by
the test fixture only.

### Where you can see it

**Not on :8080 yet.** That process is running the pre-change code; the key appears after a
restart. I captured the above by calling `main.get_table_schema` directly against the live
DB in a read-only transaction (no app startup, no writes) rather than by restarting your
running server. Cross-check printed alongside it:
`exposed_columns(bonding_log) == ['wafer_id'] == announced names`.

## Implementation

`virtual_join_executor.resolved_column_announcements(db, left_table)` — new, returns the
full entries. `exposed_columns` is now **derived from it** (`{e["name"] for e in ...}`) so
the key and the set the search path actually resolves cannot drift; that removes the place
the drift could live rather than testing for it.

`/schema` gains the key, always present, `[]` when no verified join touches the table.

Design constraints, all honoured: additive · no writability field · `kind` **stated** ·
`unresolved_label` per entry · verified declarations only (`rules_for`, never
`load_virtual_join_rules`).

## Obligations S1–S10, carried here

`server/tests/test_join_resolved_columns.py` (15 tests), fixture regenerated from the
design note including all three weight-bearing decisions and the vacuity guard.

| | verified by |
|---|---|
| S1 additive | `columns`/`column_types`/`virtual_columns` byte-stable; asserted as **"the only differing keys are the two announcements"**, which also catches a third key appearing |
| S2 key on every table | `[]` on `jrc_test_plain`, `jrc_test_wafer`, `jrc_test_site` |
| S3 equals `exposed_columns`, both directions | ⚠️ **rewritten mid-round** — see below |
| S4 `kind` stated, both values occur | `wafer_id`=collide, `fab_site`/`line_code`=virtual_only |
| S5 label per entry | `NO-WAFER` vs `라인미지정`, and both asserted ≠ `DEFAULT_UNRESOLVED_LABEL` |
| S6 rule + right_table | every entry, every table |
| S7 collide-only leaves `virtual_columns` empty | `jrc_test_collide_only` |
| **S8 marker is not the write guard** | behavioural **and** structural — below |
| S9 collide stays writable | write lands: `row.wafer_id == "WF-OVERRIDE"` |
| S10 no name in both lists | every table |

### S8 — the NO-GO detector fired correctly

Injected: write guard rewired to read `resolved_column_announcements` instead of
`virtual_only_columns`. **All three axes went red on that one injection:**

```
🔴 NO-GO CONDITION MET.
  A write to the virtual_only column 'line_code' SUCCEEDED while the announcement was suppressed.
```
```
🔴 the write guard now reads the ANNOUNCEMENT: {'resolved_column_announcements'}.
```
plus S9 (the collide column became unwritable). The design note's prediction, reproduced.

The structural half is not redundant: behaviour can be right by accident, a call graph
cannot.

## Three things I got wrong and corrected — all found by injection, not review

**1. S3 was tautological as I first wrote it.** It compared the key against
`vjx.exposed_columns` — which I had just derived *from the function under test*. Injection
proved it: making the announcement omit collide columns turned six other assertions red
and left S3 green. Self-comparison of one function cannot detect a uniform error in it.
Rewritten to score against an **independent oracle** recomputed straight from `rules_for`.
Re-injected: 7 red instead of 6.

**2. An inherited docstring claim in `test_schema_virtual_columns.py` was false.** It said
*"drop the `virtual_only` filter and this goes red"*. Measured: it does **not**. Two
independent layers each suppress a collide announcement —
`announced_columns` iterating `virtual_only`, and `get_table_schema` filtering against
`known = set(columns)` — and removing **either alone leaves it green**. Only both together
make it red (verified). Defence in depth is a good property; a docstring naming one
falsifier when there are two teaches the next reader that removing that layer is safe.
Corrected, with both layers named. contract-keeper's §6 predicted exactly this.

**3. The structural test I added for layer 2 asserted its own powerlessness.** My first
version accepted *any* list comprehension with a `not in` test, and `get_table_schema`
contains others (the `columns` fallback). It passed with the filter deleted. Tightened to
name the iterable (`announced`); it goes red now — verified.

## Two existing tests narrowed — flagging loudly, because this is the dangerous move

`test_schema_virtual_columns.py` asserted the `/schema` body was **byte-identical** for a
collide-only declaration. This round deliberately supersedes that: a collide column *is*
resolved through a join and the client cannot know it without being told.

I did **not** delete the assertions. Each test now asserts what the original was
*protecting*, and only the byte-identity was relaxed:

- `virtual_columns` must still be **empty** for a collide-only declaration (the "two
  answers about whether it is stored" defect) — asserted directly rather than implied;
- `columns`/`column_types` must not move;
- the **only** differing key may be `join_resolved_columns`.

`join_resolved_columns` cannot reintroduce the ambiguity because it carries **no
writability field** — editability still lives only in `columns[].editable` and
`virtual_columns[].editable`.

## Tests

`conda run -n assy_manager python -m pytest server/tests/ -q -rs`
→ **1818 passed, 1 skipped** (the skip is contract-keeper's PG-render axis, unchanged).
Verified no injection strings remain in `server/main.py`, `crud.py`,
`virtual_join_executor.py`, `enrichment_analysis.py`.

New: `server/tests/test_join_resolved_columns.py` (15).
Modified: `server/tests/test_schema_virtual_columns.py` (2 narrowed + 1 new structural).

## Is my tree functionally complete on its own? — YES, with one named gap

Everything I touched works as a unit. `main.py`, `crud.py`, `virtual_join_executor.py`,
`enrichment_analysis.py` have no dependency on any client change, and no scaffolding for
work that has not landed.

🔴 **The named gap, for the board:** virtual-column search and filtering now work
server-side and are carried in the CSV extract, but **client2 sets `filter: false` on
virtual columns, so none of it is reachable from the UI this week** — an operator cannot
type in the filter box for those columns. `join_resolved_columns` is what lets client-pm
lift that honestly; until they do, the capability is real but unexposed.

## Numbers to re-measure

1. **1818 passed, 1 skipped** — full suite, run by me, `conda run -n assy_manager`.
2. `bonding_log.wafer_id` announces `kind: "virtual_only"` — **not** `collide`, because
   the config changed mid-session. Confirm that was intended.
3. One injection (guard → announcement) turns **S8, S8b and S9** red together.
4. Removing **either** collide-suppression layer alone leaves the collide test green;
   both together turn it red.
