# QA Review — N7 virtual-join numeric (5be96f5) + bonding availability relaxation (2c2a777)

Reviewer: qa-reviewer (adversarial) · Date: 2026-08-04 · Tier T2 · Gates the push of `main`.
Scope: `5be96f5`, `2c2a777` (both on `main`, unpushed). `efc4514` / `db46525` not in scope.

---

## 0. The suite number the Lead PM asked for

Run in the MAIN checkout, `conda run -n assy_manager`, single pytest process (verified no
other pytest live before starting):

```
cd server && conda run -n assy_manager python -m pytest tests/ -q

1859 passed, 2 skipped, 93 warnings in 377.44s (0:06:17)
```

Exit code 0. `grep -cE "^(FAILED|ERROR)"` over the full captured stdout → **0**.
(First attempt's summary line was lost to teardown log noise; rerun with full capture.
No other pytest process was live at either start — checked `Win32_Process`. The 5-process
decoupled server was up, which is normal.)

Reconciliation of the two lane claims:

| Lane claim | Reality in the main checkout |
|---|---|
| N7: `1849 passed / 2 skipped / 0 failed` | **Consistent.** 1859 − 1849 = 10 = the bonding lane's new `test_availability_relaxation.py` (10 tests). The N7 number was measured before `2c2a777` landed. Skips unchanged at 2. |
| Bonding: `1836 passed / 7 failed / 5 skipped` in its WORKTREE, "all 7 pre-existing worktree-baseline ingestion failures" | **Assertion holds.** All 7 are absent here; 0 failures in the main checkout. The worktree lacked the gitignored user assets those ingestion/watcher tests need. Its skip count (5 vs 2) is the same artifact. |

---

## 1. Verdicts

| Commit | Verdict | One-line reason |
|---|---|---|
| `5be96f5` N7 numeric virtual join | **GO** | The crash is genuinely fixed and the PG dialect claim survives independent re-measurement; the residual disagreements are outside the fixed axis and none is a regression. |
| `2c2a777` bonding relaxation | **GO-WITH-FIXES** | Engine arithmetic and the guard side are sound, but the change's own stated safety mechanism (`inactive_subtractions`) is absent from the one surface that hands an operator a go/no-go judgement (`validate_plan`), and no doc the change invalidated was updated. |

---

## 2. Confirmed defects — severity ranked

### [HIGH] B1 · A gross availability reaches the plan-validation verdict with no marker at all
`server/transfer_plan.py:3290-3330` (`validate_plan`, def at `:2928`), return shape at `server/transfer_plan.py:3412-3424` (`"status"` at `:3420`)

`validate_plan` gates on exactly one thing:

```python
if not chips_block.get("remaining_reliable", True):
    ... WARN_AVAILABILITY_UNRELIABLE ...  # "판정 불가"
    continue
any_doe_checked = True
available = int(chips_block.get("remaining") or 0)
if required > available:  WARN_QTY_SHORTAGE
```

After the relaxation, `_status_is_degraded` (`server/transfer_plan.py:485`, new
`or status == STATUS_NOT_DECLARED` at `:502`) returns False for `not_declared`, so `assess_degradation` yields
`remaining_reliable = True` on a wholly un-subtracted number. The gate passes,
`available` is the GROSS count, and the returned dict
(`ref_table / map_key / stage / map_status / doe_count / painted_values / status /
availability_checked / warnings`) carries **no** `inactive_subtractions` and **no**
warning of any kind about the skipped subtractions. `grep -n inactive_subtractions
server/transfer_plan.py` → 1128, 1130, 1322, 1324, 1353, 1358, 1407, 1447, 1779, 1784,
1980, 2018. Nothing in the 2900-3424 validate range.

Failure scenario: a site declares `total_chips` (a chip table listing every chip on the
tape) and never declares `transfer_log`. Tape holds 8 chips, 6 already transferred
(marked on the map object, not in a table). A plan needs 5.
- Before: `remaining_reliable = false` → `availability_unreliable` → status `warnings`,
  operator sees 판정 불가 and checks by hand.
- After: `remaining = 8`, `remaining_reliable = true`, `5 <= 8` → **`status: "ok"`, zero
  warnings**. The plan is approved for material that does not exist.

This is precisely the failure the commit message names ("gross must never silently pose
as net"), left open on the highest-stakes consumer. `inactive_subtractions` was placed on
the *summary* payload only.

Recommended fix (do not merge silently): emit a warning type on the validate path when
the summary reports `inactive_subtractions` — e.g. `WARN_AVAILABILITY_GROSS` carrying
`inactive_subtractions` + `available` — so `status` can never be bare `"ok"` on a
subtraction-free number. Lead-PM ruling needed on whether it downgrades `status` or only
appends a warning.

### [HIGH] B2 · The field designed to prevent B1 has zero readers, and the UI renders gross in the typography reserved for exact-net
Client trace (read-only, no edits): `inactive_subtractions` — **0 occurrences in all of
`client2/`** (src, html, tests). `transferred` — **0 occurrences in `client2/src`**.

- `C:\Users\kk980\Developments\assyManager\client2\src\transfer_plan.js:1188-1194`
  (`availCellHtml`): `av.reliable ? '<b>'+av.value+'</b>' : 미상`. A `not_declared` gross
  availability renders as a **bold bare number, byte-identical in presentation to a
  fully-subtracted net one** — no `≤`, no badge, no tooltip. The `≤` convention at
  `:1191` is reserved for `remaining_upper_bound`, which `not_declared` deliberately does
  not set, so the UI actively asserts the number is exact.
- `client2/src/transfer_plan.js:1300` — the column header is 가용 with no qualifier;
  the footnote at `:1303-1309` warns only about 미상 ≠ 0.
- `client2/src/transfer_plan.js:452-454` — the client filters `data.warnings` for
  `source_degraded` / `availability_unreliable` only. `not_declared` is a field, not a
  warning, so the client receives **no signal whatsoever**.
- `client2/src/transfer_plan.js:1521-1537` — the `↻ 가용` toast tallies pools with
  `reliable !== true`; relaxed pools count as fully OK → cheerful `가용 조회 완료`.
- `client2/src/transfer_plan.js:1211-1217` (`remainingIsNegative`) — a gross-derived
  잔여 will **suppress** the red shortage highlight a net computation would have shown.

B1 and B2 are the same hazard seen from the two ends. Either the server must refuse to
serve a bare number on the relaxed path, or the client lane must be commissioned to
render the qualifier. Shipping the server half alone is what makes the number silent.

**Null-safety, separately: CLEAN.** Every live read of `remaining` is explicitly
null-guarded (`transfer_plan.js:470`, `:478`; `doe_bands.js:478-487`), and
`transferred` / per-core `used` are never read by this client. No `"null"` render, no
`NaN`, no `x || 0` coercion. Contract change #1 is safe as written.
`/api/bonding-plan/core-summary` has **zero consumers** in the checked-out `client2`.

### [MEDIUM] N1 · The numeric two-spelling contract was scored against Python, but the operator reads JavaScript — they diverge for every |v| < 1e-4
`server/database/crud.py:481-535` (`BIGINT_SAFE_NUMERIC_TEXT_BOUND` at `:481`,
`numeric_text_sql` at `:484`) vs `server/virtual_join_executor.py:437-455`
(`_resolve_one` returns the RAW number into the payload at `:452`/`:454`).

The SQL surfaces (column filter, `?q=`, CSV export) compare/emit
`numeric_text_sql`'s text. The grid payload carries the raw float, which the browser
stringifies with JS rules — not `clean_str_value`'s. The contract test scored
SQL-vs-`clean_str_value`; those two do agree. The seam that actually decides "does the
user find what they see" is SQL-vs-JS, and it was never scored.

Measured (PG 18.3 live read-only for the SQL column, `node -e` for the JS column):

| stored | SQL / CSV spelling | grid displays | agree |
|---|---|---|---|
| 3.0 / 0.0 / -0.0 / 2.5 / -3.0 | `3` `0` `0` `2.5` `-3` | `3` `0` `0` `2.5` `-3` | yes |
| 1e16 | `10000000000000000` | `10000000000000000` | yes |
| 1e-5 | `1e-05` | `0.00001` | **no** |
| 5.5e-5 | `5.5e-05` | `0.000055` | **no** |
| 1e-7 | `1e-07` | `1e-7` | **no** |

Failure scenario: a numeric expose column holding a leakage measurement `5.5e-5`. The
grid cell reads `0.000055`. The operator types `0.000055` into the column filter →
0 rows. Types it into `?q=` → 0 rows. The CSV extract for the same row says
`5.5e-05`, so the grid and the extract disagree in print.

The contract test states its own seam definition explicitly at
`contracts/blank_predicate/test_predicate_contract.py:779-783`:
"The payload half carries the RAW number …; its comparison text is `clean_str_value`".
That premise — that `clean_str_value` is the render the operator reads — is the one that
does not hold for a raw number crossing JSON into a browser.

Not a regression (on PG every one of these reads was a 500 before the fix), and outside
the corpus the implementer scored — but the commit message's claim "both spellings agree
on every dialect" is broader than what was measured. Recommend: either declare this band
as a divergence next to `FLOAT_EXPONENT` in `contracts/blank_predicate`, or extend the
contract's numeric axis with the JS render as a third scored column.

### [MEDIUM] N2 · The identical crash class is still live for a `datetime` expose column
`server/virtual_join_executor.py:348-353` (`_text_part`) tests
`isinstance(col.type, (Numeric, Float, Integer))` (`:351`) only. `server/database/models.py:395,423`
maps `table_config` type `"datetime"` → `DateTime(timezone=True)`, and
`server/virtual_join_config.py` places **no type restriction on `expose`** (grep: only
column-name existence is checked, `:273-274`).

Measured on live PG 18.3, read-only, using the implementation's own non-numeric branch:

```
coalesce(CASE WHEN (v IS NULL OR v = '') THEN NULL ELSE v END, '미상')
→ psycopg2.errors.InvalidDatetimeFormat: invalid input syntax for type
  timestamp with time zone: ""
```

Failure scenario: an operator adds a `datetime` column to `expose` in
`virtual_join_rules.json`. Every read naming that column — grid page, `?q=`, column
filter, CSV export — 500s. Byte-for-byte the same user report that produced N7.

This is a scope gap, not a defect introduced by the commit, and I do NOT recommend it
block the push. But the N7 round's own stated lesson ("a declarable axis must be
activated permanently by a fixture") applies to `datetime` verbatim, and the round closed
without it. Recommend a board item.

### [LOW] N3 · Undeclared spelling divergence at NaN / ±Infinity
Live PG 18.3, read-only: `NaN` → SQL `'NaN'` vs `clean_str_value` `'nan'`;
`Infinity` → SQL `'Infinity'` vs `'inf'`. Neither is in the contract table nor in
`declared_divergences`; the magnitude guard does not cover them
(PG `NaN <= 9.2e18` is false, so NaN takes the ELSE arm — it does not crash, it just
spells differently).

Reachability is low: `server/parsers/pipeline_base.py:57-69` converts NaN / NaT / ±Inf to
`None` at the Excel/CSV ingestion boundary. Flagged so the contract's "agrees on every
dialect" wording is not read as covering values it never scored.

### [LOW] B3 · A present-but-garbage `fail_sources` is reported as "not declared"
`server/transfer_plan.py:1443-1447` (predicate at `:1444`, append at `:1447`):

```python
fail_sources = source_cfg.get("fail_sources") or {}
if not (isinstance(fail_sources, dict) and fail_sources):
    inactive_subtractions.append("fail_sources")
```

The predicate is truthiness-and-shape, not key presence — the only site in the change
that does not use `role_is_declared`. `"fail_sources": "dt_fail"` (an operator typing a
table name where a dict belongs) or `"fail_sources": []` is a **present, broken**
declaration, and it lands in `inactive_subtractions`, telling the reader "this site keeps
no fail table" when in fact this site tried and failed to declare one. It does not change
the demotion (that path is untouched), so it is a mislabel rather than a wrong number —
but it contradicts the three-state discipline the commit message states as its core rule.

### [LOW] B4 · `not_declared` reaches only dead client code, where it degrades to "알 수 없는 상태"
`client2/src/transfer_plan.js:1706-1718` (`__held_classifySourceStatus`, currently behind
`eslint-disable no-unused-vars`) maps `connected`/`missing`/`unavailable(...)`/
`connected(...)`. `not_declared` falls through to the default at `:1717` → severity
`'unknown'`, label `알 수 없는 상태 — 서버 원문`, and is then filtered out at `:1726`
(which admits only `degraded`/`missing`). If that held source-badge block is ever
re-enabled, the new status will neither label nor flag. Client lane item, not a blocker.

---

## 3. Hypotheses I tried to break and could not

**N7**
- *Negative zero folds to the wrong sign* — `-0.0` → PG `'0'`, Python `'0'`. Agree
  (`CAST(-0.0 AS BIGINT) = 0`, and `0 = -0.0` is true).
- *The BIGINT cast raises past 2^63 on PG* — measured `1e19`, `-1e19`, `9.3e18` against a
  real (non-constant) column: the guard holds, ELSE arm runs, no error. PG evaluates the
  guarded CASE lazily for column references, so the arm is never reached.
- *PG rounding in `CAST(float8 AS bigint)` (3.7→4) corrupts a spelling* — the folded arm
  is used only when the round-trip is EQUAL to the original, so a rounded value can never
  select it. Verified across the fractional corpus.
- *Decimal/NUMERIC columns spell `'3.00'` in Python and `'3'` in SQL* — not reachable:
  `server/database/models.py:392-401,420-427` maps every dynamic `"number"` column to
  `Float`, never `Numeric`. `Numeric` in the isinstance tuple is defensive only.
- *Sorting a numeric virtual column now sorts lexicographically ('10' < '9')* — not
  reachable: `resolved_expression` is called from exactly four sites
  (`main.py:1368` binder, `:1387` filters, `:1441` search, `:1929/:1936` export SELECT).
  ORDER BY (`main.py:1600-1610`) never consults the binder; virtual columns are not
  sortable.
- *The filter bridge corrupts a non-numeric non-string value* — `main.py:1210-1218`.
  A list becomes `'[1, 2]'`, a bool becomes `'True'`. Both previously produced a PG type
  error or a SQLAlchemy failure; both now match nothing. Strictly an improvement.
- *`inRange` bridges `filter` but not `filterTo` → mixed-type comparison* — with an
  override `is_numeric` stays False (`main.py:1224-1226`), so `inRange` falls to the
  string else-branch and `filterTo` is simply unused. No crash. Pre-existing, documented.
- *String columns changed* — `_text_part` returns `crud.blank_to_null(col)` unchanged for
  every non-numeric type; identical call, identical compile. Claim holds.
- *`refuse_virtual_join_columns` changed* — `git show 5be96f5 -- server/database/crud.py`
  is `59 +++++` with **zero deletions**; the write-refusal funnel is byte-identical.

**Bonding**
- *A fully-declared config's payload changed* — it cannot. All three
  `inactive_subtractions.append` sites (`:1358`, `:1407`, `:1447`) are gated on absence,
  the field is emitted only `if inactive_subtractions` (`:1779`), `transferred` is nulled
  only under `used_untracked or used_not_declared` (`:1753`), and `_aux_role_status`
  degenerates to the old `_binding_status(block.get(key))` for any declared key
  (`:372-379`). The byte-identical claim holds.
- *Circular import* — `transfer_plan.py:114` now has a module-level
  `from bonding_plan import STATUS_NOT_DECLARED, role_is_declared`; `bonding_plan.py`
  imports only `json/logging/os/paths` at module level. No cycle.
- *`transfer_log: null` / `"None"` / a typo now escapes demotion* —
  `role_is_declared` is key-presence (`bonding_plan.py:94-104`), so every present-but-
  broken value takes the `elif`/else path. `transfer_log_is_declared_none`
  (`transfer_plan.py:293-311`) is untouched and still admits only the exact `"none"`.
  Guard side verified by code path, not by claim.
- *`total_chips` slipped into the relaxation* — `_stage_role_statuses` still routes it
  through `_binding_status`, never `_aux_role_status` (`transfer_plan.py:398`), and
  `bonding_plan.py:356-361` exempts it explicitly. Denominator stays required.
- *The lot-scope merge sums Nones into a fake 0* — `transfer_plan.py:1002-1005`. If the
  first entry is None the accumulator is None and every later `elif` is skipped; if a
  later entry is None it overwrites. Unknown propagates in both orders. Correct.
- *`a["remaining"] += int(e.get("remaining") or 0)` crashes or fakes 0 on the relaxed
  path* — `_bins_block` (`:933`) sets `remaining` to None only when `not reliable or
  untracked`; `transfer_inactive` sets neither, so the merged entry always carries a
  number (`"reliable": reliable and not untracked` at `:940`). And unreliable entries
  `continue` at `:996` before the arithmetic.
- *by_core `remaining` breaks now that `used` is nulled* —
  `transfer_plan.py:1628-1636` and `:1682-1690` null the PAYLOAD field but keep using the
  accumulator `a["used"]` / `a["blocked"]` for the arithmetic. No TypeError, no fake.
- *A relaxed `origin_log` leaves `cols` unbound and raises later* —
  `transfer_plan.py:1401-1414` sets `model = None` and the entire consuming block is
  behind `if model is not None`. `cols` is never read on that path.
- *A declared `frame:"origin"` fail source silently stops demoting when `origin_log` is
  absent* — the declared-contradiction path is preserved (relaxation only skips the
  `_resolve`, `statuses["origin_log"]` is set explicitly); pinned by the lane's own
  `test_declared_origin_frame_fail_source_without_origin_log_still_surfaces`.
- *M1 `/core-summary` newly serves a gross number* — it always did.
  `bonding_plan.py:538` computes `remaining = total − defect − eds_fail − used` with
  missing roles counted as 0, and the M1 payload has no reliability flag at all. The
  commit only ADDS `inactive_subtractions` there. M1 is improved, not degraded.
- *A `WARN_*` disappeared while the count stayed the same* — checked membership, not
  count. `_collect_history` (`transfer_plan.py:1249-1253`) returned `"missing"` with an
  EMPTY warning list for an absent binding, so no history warning was removed. What does
  change is that `WARN_SOURCE_DEGRADED` entries with `role` in
  {transfer_log, origin_log, process_history} no longer fire on the ABSENT path — that is
  the feature, and they still fire on the broken path.

---

## 4. Needs runtime verification (cannot be settled from code)

1. **B1/B2 end-to-end.** Whether a live relaxed config actually produces
   `status: "ok"` on a gross number needs one run against a config with `total_chips`
   declared and `transfer_log` absent. I did not mutate any config (read-only rule) and
   the live `transfer_plan_config.json` declares the roles, so the relaxed branch is
   currently dormant in production.
2. **Which live sites are actually relaxed.** `server/config/*.json` is gitignored user
   territory; the change's blast radius depends entirely on which auxiliary keys the
   real deployed configs omit. Worth measuring before push so the Lead PM knows whether
   B1 is theoretical or live on day one.
3. **N2 datetime axis** — I proved the SQL fails on PG; I did not exercise the full
   route, because that needs a `datetime` entry in `expose` (a config write).
4. **N1 grid rendering** — I inferred the grid displays the raw JS number because
   `client2/src/grid.js` defines no `valueFormatter` for number columns. A browser check
   on a numeric virtual column with a value below 1e-4 would settle it.

---

## 5. Documentation integrity

**`5be96f5` (N7): compliant.** `virtual_join_rules.md` §4-ter, `backend.md` §2.2,
`CONFIG_GUIDE` §1, `FEATURE_CHECKLIST` §1.1/§2.2-bis, history entry
`docs/history/20260804_062339_the_label_is_text_so_the_number_must_speak_text.md` +
regenerated index. The lane also cleared the three-place sweep the `cd3e0f4` round owed.
One overstatement to correct rather than block on: the commit message's "both spellings
agree on every dialect" is true of the corpus it scored, not of the value domain — see N1
and N3.

**`2c2a777` (bonding): NOT compliant — nothing was updated.** `git show --stat 2c2a777`
touches 9 files, all under `server/`; zero docs, zero history. Measured against
`docs/process/DOC_OWNERSHIP.md:77` (본딩·전사 계획 엔진 → `server/bonding_plan.py`,
`server/transfer_plan.py`, `client2/src/transfer_plan.js`), the owned documents are
`docs/spec/MAP_EDITOR_SPEC.md §6` and `docs/guide/CONFIG_GUIDE.md §3-S6` — **neither was
touched**, and neither appears in the implementer's own follow-up list. The lane's own
list (its report §"Stale doc spots") names 7 further groups it left for others:
`CONFIG_GUIDE` §5.8 status dictionary (~246), ~581, ~237;
`docs/guide/config/transfer_plan_config.md` lines 96/111/118/143/144/150-151/162/168;
`docs/guide/config/bonding_plan_config.md` lines 23/49/67;
`docs/guide/config_reference/{transfer,bonding}_plan_config.json` (now diverged from the
`.sample`s it did edit); `docs/architecture/backend.md`.
`docs/history/` has exactly one entry dated 2026-08-04 — the N7 one. **The bonding commit
has no history entry.**

I did not stop at the implementer's list — I searched `CONFIG_GUIDE.md` by the predicate,
and it names **two more stale statements the lane did not list**:
- `docs/guide/CONFIG_GUIDE.md:524` — "미선언 테이블을 가리키는 바인딩은 … 해당 역할이
  `missing`으로 표면화됩니다" (now only true for a *present* binding).
- `docs/guide/CONFIG_GUIDE.md:635` — "role이 빠지거나 테이블이 없으면 에러가 아니라
  `missing`" — the "role이 빠지거나" half is now false.

And a naming collision the lane did not notice: **`not_declared` already exists in this
same guide as a different vocabulary's status** —
`docs/guide/CONFIG_GUIDE.md:338`, the `config_resolve_report` reason dictionary
("효과에 필요한 선언이 없다"). One guide will now carry the same token with two
meanings. Whoever updates §5.8 must disambiguate, or an operator reading §5.8 will look
it up in the §-338 table and get the wrong domain's answer.

Concretely: `CONFIG_GUIDE.md:246` (§5.8) currently tells an operator "`missing` = 바인딩
선언/테이블 없음". After this commit that sentence is false — absence is `not_declared` and
produces a number, not 미상. An operator reading the shipped doc will misread the very
status that decides whether they trust the availability figure. This is the standing
"living docs must land with the code" rule, and it is the reason for GO-WITH-FIXES rather
than GO.

---

## 6. Recommended gate

- `5be96f5` — push. N1/N3 as declared-divergence doc updates, N2 as a board item.
- `2c2a777` — hold the push until **either** the validate path carries the
  `inactive_subtractions` signal (B1) **or** the Lead PM rules explicitly that a bare
  gross number on `validate` is accepted and records that ruling; and until the
  `DOC_OWNERSHIP:77` documents plus a history entry land. B2 needs a client-lane
  commission either way — the server field currently has no reader anywhere.

---

## 7. Proposed memory entries (for Lead PM review — not self-added)

1. 함정: 새 안전 필드를 「요약 응답」에만 달면, 판정을 내리는 라우트는 그 필드를 모른 채
   숫자만 읽는다. 올바른 방법: 신뢰도 축을 하나 늘렸으면 **그 값을 소비해 판정을 내는 모든
   라우트**를 열거해 각각에서 채점한다(여기선 `validate_plan`이 빠졌다).
2. 함정: 두 철자 계약을 「SQL vs Python」으로 채점하면, **사람이 보는 것은 JavaScript가
   그린 숫자**라는 세 번째 철자가 채점 밖에 남는다. 올바른 방법: 페이로드가 원시 숫자를
   나르면 렌더 언어를 계약의 열로 추가한다.
3. 함정: 타입이 걸린 SQL 결함을 한 타입(숫자)만 고치면, 같은 선언 자리에 앉을 수 있는
   다른 타입(datetime)은 같은 500을 그대로 유지한다. 올바른 방법: 결함을 고칠 때
   **그 자리가 받을 수 있는 타입의 전 집합**을 세고 각각에 픽스처를 만든다.
