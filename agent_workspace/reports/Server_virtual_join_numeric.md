# Server Report — N7: virtual join dies on numeric expose columns

Date: 2026-08-04 · Owner: server-pm · Board item: N7 (user report 2026-08-02, live)

## Verdict

Fixed, red-first, both spellings agree on every dialect, full suite green
(1849 passed / 2 skipped). Write refusal funnel untouched. No incompatibility
found — the two-spelling contract PASSES; no Lead PM escalation needed on the
contract itself. One process finding for the Lead PM at the bottom (stale doc
sweep from the `cd3e0f4` round, now done).

## 1. The red repro (part of the deliverable)

New file `server/tests/test_virtual_join_numeric.py` (tables `vjn_test_*`,
numeric `virtual_only` column `slot_no` + numeric `collide` column `core_thk`).
Run BEFORE the fix: **6 failed, 6 passed**.

- Failure shape on the suite dialect (SQLite is dynamically typed, so the
  expression does not crash — it resolves to the RAW FLOAT):
  `AssertionError: slot_no/L1: grid displays '3', search compares 3.0`, and
  `equals '3.0'` found the row while `equals '3'` did not.
- Failure shape on the PRODUCTION dialect, reproduced with read-only scalar
  probes against live PG 18.3 (no table named, nothing written):
  - `blank_to_null` arm: `InvalidTextRepresentation` — invalid input syntax for
    type double precision: `""` (the `col = ''` inside `blank_to_null`, i.e. the
    violation of `blank_sql_condition`'s documented text-typed precondition).
  - `COALESCE(double precision, text)`: `DatatypeMismatch`.
  This is the user-reported class: every read naming the column (column filter,
  `?q=`, CSV export SELECT) was a 500.

Why nothing was red at ship time: the trace fixture had no numeric expose
column and the live measurement was "0 numeric expose columns" — the axis did
not exist. The new file activates it permanently. (Measured today: the live
declarations in `server/config/virtual_join_rules.json` are again all
string-typed — presumably the user worked around the crash — so without this
fixture the axis would be empty again.)

## 2. The fix (user-ruled direction, implemented as ruled)

- `server/database/crud.py` — new `numeric_text_sql(col_expr)` (+ constant
  `BIGINT_SAFE_NUMERIC_TEXT_BOUND = 9.2e18`): the SQL twin of
  `clean_str_value`'s numeric branch. Renders a numeric column to canonical
  comparison text with INT spelling for integral values, on EVERY dialect:
  `CASE WHEN col BETWEEN ±9.2e18 THEN (CASE WHEN CAST(col AS BIGINT) = col THEN
  CAST(CAST(col AS BIGINT) AS VARCHAR) ELSE CAST(col AS VARCHAR) END) ELSE
  CAST(col AS VARCHAR) END`. NULL propagates through every branch (no NULL arm,
  and deliberately NOT wrapped in `blank_to_null` — a number is never `''`; the
  contract's own wording: "numbers are not text; the SQL blank arm is IS NULL").
  The magnitude guard keeps `CAST AS BIGINT` from raising on PG for |v| >= 2^63;
  beyond it the plain cast runs (same reach as the declared FLOAT_EXPONENT
  divergence, out of range of every measured production column).
- `server/virtual_join_executor.py` — `resolved_expression` routes each part
  (left collide part AND right parts) through `_text_part`: numeric model
  columns (same `isinstance(col.type, (Numeric, Float, Integer))` test as
  `main.get_column_filter_condition`) go through `crud.numeric_text_sql`;
  everything else stays `crud.blank_to_null` — string columns compile
  byte-identically to before.
- `server/main.py` — `get_column_filter_condition`: when an override (join-
  resolved column) is in play and the filter value arrives as a NUMBER (AG-Grid
  does this for number-typed columns), bridge it through `clean_str_value`
  (3.0 -> '3'). Strings pass through untouched — a type bridge, not a trim.

Not touched: `_resolve_one` / `attach` (payload path was already correct: raw
number in the cell, label for both faces of 미상), `refuse_virtual_join_columns`
(behavior pinned by a test in the new file), `/schema` announcements (the
number-column-may-carry-the-label caveat was already honest and stays).

## 3. Two-spelling contract evidence

Extended `contracts/blank_predicate`: the resolution-seam fixture gained
`slot_no: "number"` in `expose`, helpers gained a `column` parameter, and the
new `test_the_two_resolutions_agree_on_a_numeric_column` scores every number
corpus case through BOTH spellings (funnel AND bypass writes) plus the NULL ->
label fold. `vectors.json` registers the new symbol
(`numeric_sql_render` -> `crud.numeric_text_sql`, live) so a rename is loud.
Fault-injection verified: reverting `_text_part` to `blank_to_null` turns the
contract test red (done and reverted).

Value in DB (Float column) -> SQL path spelling -> payload path (raw payload
value -> displayed render, `clean_str_value`):

| stored              | SQL `resolved_expression` | payload value | payload render | agree |
|---------------------|---------------------------|---------------|----------------|-------|
| 3.0 (integral)      | `'3'`                     | 3.0           | `'3'`          | yes   |
| 7.0 (integral)      | `'7'`                     | 7.0           | `'7'`          | yes   |
| 0.0 (declared zero) | `'0'` (NOT the label)     | 0.0           | `'0'`          | yes   |
| 2.5 / 7.5 (frac)    | `'2.5'` / `'7.5'`         | 2.5 / 7.5     | `'2.5'`/`'7.5'`| yes   |
| -3.0                | `'-3'`                    | -3.0          | `'-3'`         | yes   |
| 1e16                | `'10000000000000000'`     | 1e16          | same           | yes   |
| NULL (blank)        | `'미상'` (label)           | `'미상'`       | `'미상'`        | yes   |
| no right row        | `'미상'`                   | `'미상'`       | `'미상'`        | yes   |

Dialect check: the SQL column was verified on BOTH dialects — SQLite via the
suite, PostgreSQL 18.3 via the implementation's OWN compiled SQL (literal
binds, scalar SELECT, read-only; not a hand-typed copy). Identical spellings on
both. Note `1e16` now agrees with Python inside the resolved expression even
though PG's plain `cast` would say `'1e+16'` — the declared FLOAT_EXPONENT
divergence is untouched (it pins `clean_str_value` vs plain PG cast, both of
which still answer as recorded).

Known limit (documented in code + `virtual_join_rules.md §4-ter`): |v| beyond
~9.2e18 falls back to the dialect's plain cast (possible exponent notation).
Same reach class as FLOAT_EXPONENT; no measured production column approaches it.

## 4. Read-surface verification (all in the new test file)

- Grid payload: numeric values + both faces of 미상 (`test_the_payload_carries_...`).
- Column filters: equals int spelling / fractional / label / numeric collide
  absent-only / numeric filter values (3 and 3.0 as JSON numbers).
- `?q=` search: scoped (`?cols=slot_no`) and unscoped both reach the column.
- The float spelling `'3.0'` matches NOTHING (pinned — that string is never displayed).
- CSV export: virtual numeric column present, cells `'3'` / `'2.5'` / `'미상'`,
  collide `'4'` from the left value.
- `/schema`: `virtual_columns` still announces `type: "number"` with
  `unresolved_label`; `join_resolved_columns` kinds correct.
- Write refusal: PUT to the numeric virtual_only column is still 400 naming the column.

## 5. Test runs

- Red first: `server/tests/test_virtual_join_numeric.py` -> 6 failed / 6 passed (pre-fix).
- Post-fix: same file 12/12; `contracts/blank_predicate/` 22 passed / 1 skip
  (the pre-existing opt-in PG axis skip, unchanged).
- Full suite: `conda run -n assy_manager python -m pytest server/tests/ -q`
  -> **1849 passed, 2 skipped** (302s).
- Fault injections actually run: route tests red pre-fix (by construction);
  contract numeric test red under re-injected defect (verified, reverted).

## 6. Living docs (per DOC_OWNERSHIP rows for the touched code)

- `docs/guide/config/virtual_join_rules.md` — new §4-ter (numeric spelling
  contract), header note, §9 updated.
- `docs/architecture/backend.md` §2.2 — numeric comparison-text bullet.
- `docs/guide/CONFIG_GUIDE.md` §1 row + `docs/qa/FEATURE_CHECKLIST.md`
  §1.1/§2.2-bis — see finding below.
- History entry `docs/history/20260804_062339_the_label_is_text_so_the_number_must_speak_text.md`
  + `gen_index.py` run (300 entries).

## 7. Finding for the Lead PM (process, not code)

The `cd3e0f4` round (2026-07-31: virtual-column search/filter/CSV export)
resolved two of `virtual_join_rules.md §9`'s open items but the documented
three-place sweep (§9 · CONFIG_GUIDE §1 row · FEATURE_CHECKLIST §1.1/§2.2-bis)
was never executed — for three days those docs told operators "no filter
exists, CSV lacks the columns", both false. I executed the sweep in this round
(measured against tests + client `grid.js:261-276` for the filter-def claims).
FEATURE_CHECKLIST §2.2-bis item "검색 드롭다운에 안 뜬다" I deliberately did NOT
touch — it is a client toolbar claim I did not re-measure; worth a client-lane check.

Also: `architecture/PRIMITIVES.md` should gain `numeric_text_sql` (canonical
numeric-to-text SQL render) — PRIMITIVES maintenance is doc-keeper-owned, so
flagged here instead of edited.

## 8. Proposed memory entries (for lead review — not self-added)

- 함정: 술어가 참조하는 모집단이 이 환경에 0개면 그 술어의 그물은 존재하지 않는다 —
  「이 환경에 없다」는 출하 근거가 못 된다. 올바른 방법: 선언 하나로 생길 수 있는 축은
  픽스처가 상시 활성화한다 (N7: 숫자 expose 컬럼).
- 함정: SQLite의 동적 타이핑은 타입 결함(운영 PG에서는 크래시)을 조용한 오답으로
  변장시킨다. 올바른 방법: 타입이 걸린 SQL 식은 구현이 직접 컴파일한 SQL을 운영 방언에
  읽기 전용 스칼라 SELECT로 한 번 실측한다 (손 사본 프로브는 채점이 아니라 복사다).

## 9. Handover

- Changed: `server/database/crud.py` (new `numeric_text_sql`),
  `server/virtual_join_executor.py` (`resolved_expression` numeric parts),
  `server/main.py` (override filter-value bridge),
  `server/tests/test_virtual_join_numeric.py` (new),
  `contracts/blank_predicate/{test_predicate_contract.py, vectors.json}`,
  4 living docs, 1 history entry + index.
- Not merged/pushed; committed on main working tree with explicit paths only.
- Unresolved: none in scope. Optional follow-ups: PRIMITIVES entry (doc-keeper);
  client-lane re-measure of the search-dropdown checklist line; numeric range
  operators (`lessThan`/`inRange`) on join-resolved columns still compare as
  text — pre-existing, documented behavior, ruled out of scope in the search round.
