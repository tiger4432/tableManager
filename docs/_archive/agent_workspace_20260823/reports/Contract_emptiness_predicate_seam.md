# Contract: the emptiness-predicate seam (`contracts/blank_predicate/`)

> ## CORRECTION, later on 2026-07-31 -- §5.1 and §5.2 are CLOSED
>
> Both mismatches this report opened were **fixed by server-pm in the same session**, after the
> report was written. Re-measured against the live tree:
>
> | | when reported | re-measured |
> |---|---|---|
> | **DUP1** SQL blank spellings in `server/` | 2 | **1** (`crud.blank_sql_condition`) |
> | **DUP1** SQL notBlank spellings | 3 | **1** (`crud.not_blank_sql_condition`) |
> | **NUM1** `cast_value_by_type(1e16, "number")` | `REFUSED(...올바른 숫자 형식이 아닙니다)` | **`1e+16`** |
>
> `main.get_column_filter_condition` and `enrichment_analysis` now delegate; the int-vs-float
> decision no longer keys on `"." in str(value)`.
>
> **The pins did their job and then had to go.** Both were self-cancelling, so once the defects
> closed they went RED IN THE OTHER DIRECTION (`test_exactly_one_sql_blank_spelling_exists_in_
> server` and `test_the_write_boundary_removes_every_divergent_input`, 2 failed) demanding their
> own removal -- which is the whole point of a pin that expires by itself. They have been removed
> from `vectors.json` per their own `clears_when`, and the contract is **21 passed, 1 skipped**.
>
> Items 1 and 2 of §8 no longer need a decision. Items 3, 4 and 5 still do.
>
> One process note, and it is mine to own: I briefly overwrote `contracts/blank_predicate/
> vectors.json` while investigating what looked like data loss (`known_defects` had gone empty).
> It was not loss -- it was the correct promotion. The file has been restored to exactly the
> indexed content, byte for byte, via `git cat-file -p :<path>`, and re-verified green. I should
> have measured the defects before concluding the file was damaged.


**contract-keeper, 2026-07-31.** Dispatched during server-pm's virtual-column search/filter
round, not after it.

Everything below is measured. No count is quoted from a commit message or the board.

---

## 1. What landed

| File | Role |
|---|---|
| `contracts/blank_predicate/vectors.json` | corpus, expected verdicts, sources, named pins |
| `contracts/blank_predicate/test_predicate_contract.py` | server scorer (pytest) |
| `contracts/blank_predicate/client_harness.mjs` | client scorer (node) |
| `server/tests/test_blank_predicate_contract.py` | shim -- puts the contract in the default suite |

**Side:** the seam is server-internal (Python vs SQL), so the **server scorer is the primary
half** and it reaches the default suite through the shim, exactly like `map_seam` and
`config_resolve_report`. A **client harness exists too** and is discovered by
`client2/scripts/check_contracts.mjs`; it scores the two smaller client obligations on this
seam (do not ask a filter the server cannot answer; do not write the label down). It does
**not** score the emptiness rule -- the harness says so in its own output.

The shim is the one file I created outside `contracts/`. It is a new file, it conflicts with
nothing server-pm holds, and charter rule 6 requires the wiring: a contract the default suite
does not run is dead within a week. Drop it if you would rather it were not there.

**Nothing was committed. Nothing under `docs/` was touched. `main.py`,
`virtual_join_executor.py` and `crud.py` were read only.**

---

## 2. Was it a generated pair or two hand-written spellings?

**Two hand-written spellings, with one shared building block.** Not a generator.

Server-pm landed (uncommitted, in `server/database/crud.py`):

- `is_blank_value(val)` -- `clean_str_value(val) == ""`, the Python spelling, now named.
- `blank_sql_condition(col_expr)` -- `or_(col.is_(None), col == "")`, the SQL spelling.
- `not_blank_sql_condition(col_expr)`.
- `blank_to_null(col_expr)` -- a `CASE` **derived from** `blank_sql_condition`, which is the
  good part: the virtual-join resolved value cannot disagree with the emptiness test it is
  built on, and the docstring says why it is not `NULLIF` (that would be a third spelling).
- `normalize_stored_text(value)` -- `value.strip()` for `str`, wired into `cast_value_by_type`.

and in `server/virtual_join_executor.py`, `resolved_expression(...)` -- the SQL translation of
`_resolve_one`, built from `crud.blank_to_null` + `COALESCE`.

So the **emptiness rule** has one SQL home. The **resolution rule** has two independent
spellings (`_resolve_one` in Python, `resolved_expression` in SQL). I score that pair
directly, on one corpus, and compare the resolved values row by row.

The vectors are authored from spec / declared-type semantics / the system's pre-existing
identity rule, and each case records which. None were taken from the implementation --
`$blank_source` and `$render_source` are on every case.

---

## 3. Scores, per scorer

| Scorer | Command | Result |
|---|---|---|
| server, standalone | `pytest contracts/blank_predicate/ -q -rs` | **21 passed, 1 skipped** |
| server, via shim | `pytest server/tests/test_blank_predicate_contract.py -q -rs` | **22 passed, 1 skipped** |
| server, with Postgres axis | `ASSY_CONTRACT_PG_URL=... pytest contracts/blank_predicate/` | **22 passed, 0 skipped** |
| client | `node contracts/blank_predicate/client_harness.mjs` | **4/4 assertions, 0 divergence, exit 0** |
| all contracts | `node client2/scripts/check_contracts.mjs` | **6 contracts, no divergence** |
| default suite | `pytest server/tests/ -q` | see §7 |

The one skip is **named**: number-column RENDER on the production dialect, blocking INV-BP-R2
for the three float cases, with the run command and the recorded measurement in the reason
line. It is opt-in on purpose -- a contract that reaches for a database URL on its own is one
edit away from reaching for the wrong one.

**22 corpus cases**, all consumed (`test_every_contract_case_is_consumed` fails otherwise).

---

## 4. Proof the checks can go red

Three faults injected at runtime via a scratch pytest plugin. **No file under `server/` was
edited.**

| Fault | What it simulates | Caught by |
|---|---|---|
| A -- `normalize_stored_text` neutered | the write boundary regresses / a refactor drops the call | `test_the_write_boundary_removes_every_divergent_input`, `test_a_search_for_what_python_renders_finds_the_row` (2 failed) |
| B -- `blank_sql_condition` given a `trim()` | someone "fixes" SQL instead of the input | `test_the_two_resolutions_diverge_on_a_bypassed_row_exactly_as_recorded` (1 failed, in the *other* direction) |
| C -- `clean_str_value` stops stripping | the Python spelling drifts | `test_python_predicate_scores_the_corpus`, `test_python_render_scores_the_corpus` (2 failed) |

The client harness was fault-injected on a **copied tree** (real `grid.js` with `filter: false`
flipped and the server label read replaced by a literal): **exit 1, 2 divergences, both named
with file:line**. Symbol-rename detection was confirmed separately: it exits **2**, never 0.

Fault B is worth reading twice. Patching `crud.blank_sql_condition` did **not** change what
`main.get_column_filter_condition` does, because that function carries its own inline copy.
That is DUP1 below, demonstrated rather than argued.

---

## 5. Mismatches -- both answers, for your ruling

### 5.1 `main.get_column_filter_condition` did not fold into the extracted spelling (DUP1)

AST-counted across `server/` (excluding tests, scripts, migrations), 2026-07-31:

```
blank    spellings: 2  server/database/crud.py:400   (blank_sql_condition -- the extracted one)
                       server/main.py:1250           (inline, in get_column_filter_condition)
notBlank spellings: 3  server/database/crud.py:424   (not_blank_sql_condition)
                       server/enrichment_analysis.py:175
                       server/main.py:1255
```

`server/enrichment_analysis.py:175`:

```python
non_blank = and_(tgt.isnot(None), cast(tgt, String) != "")
```

All copies are byte-equivalent **today**. The one the operator's AG-Grid "Blank" filter
actually executes is `main.py`'s, not the named one -- so a fix applied to
`crud.blank_sql_condition` does not reach the user-facing filter (fault B proved this).

Contract wants 1 of each. Pinned as `known_defects.DUP1`, self-cancelling: the moment a count
drops to 1 the contract goes red in the other direction asking for the pin to be removed.

**Line numbers above are measured at run time by the scorer, not stored in the contract.**
`crud.py` moved ~+58 lines and `main.py` ~+23 lines *while I was working*, which is exactly why
`$why` fields in the vectors point at function names.

### 5.2 A float in exponent notation cannot be written to a `number` column at all (NUM1)

Found by the corpus, not by a report.

`crud.cast_value_by_type`, the `col_type == "number"` arm, decides int-vs-float by asking
whether the **string** contains a `.`:

```python
val_str = str(value).strip()
if "." in val_str:  return float(val_str)
else:               return int(val_str)      # int('1e+16') -> ValueError
```

- contract expects: `1e16` stores as `1e16` (a `number` column is `double precision`; it holds
  it exactly)
- implementation: **refuses the write** -- `컬럼 'txt'의 값 '1e+16'은(는) 올바른 숫자 형식이 아닙니다.`

Reach: any `number` value at or above 1e16, and any float small enough to format with a
negative exponent (`str(1e-05)` is `'1e-05'`, also no `.`). **Predates this round** --
`git show 77d27d3:server/database/crud.py` has the same three lines. No production column
measured on 2026-07-31 holds such a value, so it is pinned rather than escalated. Not
server-pm's this round; yours to queue.

### 5.3 Declared divergence: FLOAT_EXPONENT -- render, no ruling made

| side | `1e16` renders as |
|---|---|
| Python `clean_str_value` | `'10000000000000000'` |
| Postgres `cast(col as varchar)` | `'1e+16'` |

Both lossless, both the same number, two different strings -- and a text search compares
strings. The contract **states no verdict** here; it records both answers and asserts each side
still gives its recorded answer. **Decision is yours.** (Reach is the same tiny set as 5.2.)

### 5.4 The dispatch's second divergence does not reproduce in production

The brief said `clean_str_value` renders `7.0` as `'7'` while `col::text` renders `'7.0'`.
Measured:

| | float 7.0 | float 0.0 | float 7.5 |
|---|---|---|---|
| Python `clean_str_value` | `'7'` | `'0'` | `'7.5'` |
| **PostgreSQL 18.3** (production) | `'7'` | `'0'` | `'7.5'` |
| **SQLite** (the pytest suite) | `'7.0'` | `'0.0'` | `'7.5'` |

`models.init_dynamic_models` maps a declared `number` to SQLAlchemy `Float`, which materializes
as `double precision`, and Postgres float8 output is shortest-round-trip. **The claim is true in
the test dialect and false in the production dialect.** A render axis scored only on
`pytest server/tests/` would have reported a divergence production does not have -- and missed
5.3, which it does. This is pinned as `dialect_facts` plus
`test_the_suite_dialect_is_not_production_and_the_difference_is_recorded`.

### 5.5 The emptiness divergence itself: real, currently latent, and pinned as an exposure

On the raw corpus, **8 of 17 text inputs** answer differently between the two spellings when
they reach storage without passing the write boundary:

```
space, tab, lf, crlf, nbsp, ideographic_space, unit_separator, mixed_whitespace
```

Same 8 at the **resolution** seam (`_resolve_one` vs `resolved_expression`) -- i.e. the grid
paints the unresolved label and the search does not find the row.

After the write boundary, **0 of 22** diverge. Server-pm's storage invariant holds, on
measurement, for every corpus input. That is what `blank_sql_condition`'s "only correct
because `normalize_stored_text` makes storage canonical" docstring is resting on, and the
contract now checks it instead of trusting it.

**But it is prospective only.** Read-only, timeout-bounded scan of the live database,
2026-07-31 (37 tables in `public`, 36 with text columns, **0 timed out**):

| | rows |
|---|---|
| whitespace-only but not empty (the emptiness divergence) | **0** |
| leading/trailing whitespace (the render divergence) | **13**, all in `file_ingestion_logs` |

So there is **no backfill debt on the emptiness axis today**. There is also nothing in the
schema stopping the next bulk path from creating one --
`server/scripts/dev_env/snapshot_db.py` copies rows verbatim, and every direct
`setattr(row, col, ...)` outside `apply_row_update_internal` is a door. `INV-BP-X1` measures
that exposure every run so the number is written down rather than rediscovered.

---

## 6. Axes I could not score, and why

| Axis | Why | State |
|---|---|---|
| number-column RENDER on Postgres | the suite runs on SQLite and the two dialects differ | **opt-in skip**, named, with the run command in the reason line. Scored green when `ASSY_CONTRACT_PG_URL` is set. |
| whether every write path funnels through `cast_value_by_type` | I read the tree and found no raw-SQL writer into a dynamic table, and the two `setattr` sites outside `apply_row_update_internal` (`delete_cell_source_batch`, `set_cell_manual_priority_batch`) restore values that `cell_sources` already stored through `clean_str_value`. That is an argument, not a check -- an exhaustive one needs a call-graph guard I did not build this round. | **unscored**, stated here |
| `equals` vs `contains` | the render divergence only bites `equals`; `contains` (AG-Grid's default) would match `A` inside `A\t` and hide it. The contract scores `equals` deliberately. | scored, noted |

---

## 7. One thing I broke and fixed -- please re-measure it yourself

My first version left the scratch `bpx_*` tables in the **process-wide** `models.DYNAMIC_TABLES`
and `Base.metadata` (restoring only `crud.TABLE_CONFIG`, which is what the existing suite
fixtures do). In **full-suite order** that made an unrelated test fail:

```
FAILED server/tests/test_config_reload_integrity.py::test_h3_cross_directory_replace_applies_physical_alter
```

Both files passed alone; only the order exposed it. Fixed by `_unregister()` in the fixture
teardown. Measured before/after:

- full suite **without** my shim: `1766 passed`
- full suite **with** my shim, before the fix: `1 failed, 1787 passed, 1 skipped`
- full suite **with** my shim, after the fix: **`1801 passed, 1 skipped, 0 failed`** (5m19s)

The three runs are not directly comparable on count -- server-pm's own new test files
(`test_stored_text_normalization.py`, `test_virtual_column_search.py`) were landing in the same
tree between runs. The load-bearing fact is the failure column: 1 -> 0.

Re-measure it yourself before committing; the tree was moving under all three runs.

---

## 8. What I want you to decide

1. **DUP1** -- fold `main.get_column_filter_condition` (and `enrichment_analysis`) into
   `crud.blank_sql_condition` / `not_blank_sql_condition`? server-pm holds `main.py` this
   round, so this is a scheduling call.
2. **NUM1** -- `cast_value_by_type` refusing exponent-notation floats. Predates this round.
   Queue or accept.
3. **FLOAT_EXPONENT** -- which render is the contract's? No verdict stated; both recorded.
4. **The shim** -- keep `server/tests/test_blank_predicate_contract.py` (charter rule 6) or
   drop it and run the contract as its own command.
5. Whether the render axis should also block trailing whitespace at the write boundary. The
   user ruling covered whitespace-**only** values; `normalize_stored_text` happens to strip
   trailing whitespace too, so the render divergence is closed as a side effect. That is a
   larger promise than the ruling made, and it deserves to be an explicit one.
