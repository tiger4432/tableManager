# ME2-SETUP — the set-up row now re-asks the request it changes

Lane: map-pm · Tier T2 · 2026-08-07
Scope touched: `client2/` only. No `server/` file was read for edit and none was modified.

---

## 1. What was wrong, and what exactly was wrong

`me2-table-select` (대상 테이블) wrote `mapTable` into the question and re-asked
`/api/maps/alignment/view`, but **nothing re-asked `/api/maps/alignment/worklist`**. The only
callers of `fetchWorklist` were `adoptRule` (once, at bootstrap) and the search box.

The consequence is not a stale list. It is **two tables on one screen**: the column pickers
repopulate from `/tables/{t}/schema` immediately, so `dt_x` / `dt_y` / `dt_index` appear
correctly, while the rows and their map counts still belong to the previous table — and nothing
on screen says which half is which.

**No server change is needed and none was made.** `server/main.py:4645` already takes
`rule` + `map_table` (required) and `params`, `q`, `sort`, `order`, `limit`, `offset`
(optional). The route was serving the right answer to a question the client never asked.

---

## 2. The three other set-up controls — decided from the route's contract, not from symmetry

| control | re-asks `/worklist`? | why |
|---|---|---|
| 대상 테이블 `me2-table-select` | **yes (this fix)** | `map_table` is a REQUIRED parameter of the route |
| 기준 `me2-reference-select` | **no — and it was never broken** | the route takes **no `reference` parameter at all** |
| `me2-col-x` / `-y` / `-value` | **no** | the route takes no column parameter; columns decide how ONE unit is read, not which units exist |

**Answer to "does 기준 have the same defect": no.** Measured, not assumed. In the live browser
the 기준 select re-issued `/view` with the new floor and issued no `/worklist`:

```
GET /api/maps/alignment/view?...&map_table=dt_log&...&reference=valid_die_ref%3A5N_BASE   200
GET /api/maps/alignment/view?...&map_table=dt_log&...&reference=valid_die_ref%3ACORE_1X   200
(worklist request count over both changes: unchanged)
```

That is the correct behaviour for both halves: the floor changes what one unit is scored
against, and `setQuestion` already re-asks `/view`. Nothing about that control was touched.

---

## 3. The change

**`client2/src/map2/main.js`**

- new closure binding `worklistInflight` (beside `confirmInFlight`, same rationale: a fact
  about one request, not about the session).
- `fetchWorklist` aborts the previous request and passes the signal to the loader. An
  `AbortError` returns **without** going to `withWorklistError` — the operator superseded their
  own question, and painting an outage that did not happen is a second defect.
  The shape is `value_suggest.js:400`, reused rather than re-invented; **no new pattern**, and
  the project's one-timeout / 82-fetch-site count is unchanged.
- the table binding:

```js
bindSelect(el.tableSelect, v => {
  const before = session.question.mapTable;
  setQuestion({ mapTable: v });
  if (session.question.mapTable !== before) fetchWorklist();
});
```

Compared **after** normalisation on both sides: `resolveQuestion` may refuse a table the catalog
does not carry, and re-picking the table already in force must cost nothing.

**`client2/src/map_editor2.js`** — the loader seam now forwards the signal:
`app.setWorklistLoader((query, signal) => api.loadWorklist(query, signal))`. `loadWorklist`
already accepted a `signal`; without this hop the shell would hold a controller that cancels
nothing.

**ONE supersession mechanism, not two.** A sequence guard on top of the abort would be a second
overlapping guard, and a "one list" assertion would then score the pair rather than either of
them (map-pm lesson, 2026-08-06). The abort is sufficient because the transport passes the
signal to `fetch`, so a superseded request cannot resolve at all.

### Complexity budget

- net controls added: **0**. No new panel, no mode, no modal, **no 새로고침 button**.
- controls removed: 0.
- reading stays frictionless (no confirmation anywhere on this path); the one write is untouched.

---

## 4. Verification

### 4a. Harness — `client2/tests/map_editor2_shell_harness.mjs`, new section R (16 assertions)

Registered: floor raised **544 → 560** in `client2/scripts/check_harnesses.mjs` with the reason
recorded there, so the new gates cannot silently disappear. Full gate run (both stages, via
`prebuild`): `check:contracts` ✓ 7 contracts, `check:harnesses` ✓ **48 harnesses, 44 gated, all
green**, 4 on the pre-existing known-red debt list (unchanged by this round).

- **R0 worthlessness check** — the two fixtures must paint DIFFERENT map counts, or the section
  verifies nothing.
- **R1/R1b/R1c** — bootstrap asks once, with the catalog's table, and paints its population.
- **R2/R2b/R2c/R2d** — the switch re-issues, names `dt_log`, and the rows become the new
  population.
- **R3/R3b negative controls** — 기준 and the column pickers must NOT re-ask.
- **R4** — re-picking the same table asks nothing.
- **R5/R5b/R5c/R6/R6b** — supersession: the older request is ABORTED, the newer rows stand, and
  an abort is not an error.

**Mutation-measured, both ways** (the only self-check worth anything):

| mutation | result |
|---|---|
| remove `fetchWorklist()` from the table binding | **6 red** — incl. `R2c … expected "…맵 40 …맵 6", got "…맵 191 …맵 1"` — the harness reproduces the reported symptom verbatim |
| remove `worklistInflight.abort()` | **2 red** — R5b (no abort) and R5c (the older answer paints) |

R5c is deliberately not vacuous: the newer answer is settled FIRST, so removing the abort makes
the older one land last and the assertion fails. Resolving them in the other order would have
left it green either way.

### 4b. Build — the bundle :8081/:8080 serves is the new one

```
dist/assets/map_editor2-BqCR0yKX.js   deleted   (mtime 08-06 23:44, the pre-round artifact)
dist/assets/map_editor2-fLD7UO_y.js   built     2026-08-07 03:34:38   <- newer than every source edit
dist/map_editor2.html                 references map_editor2-fLD7UO_y.js   (only hash it names)
```

`npm run build` exit 0 (prebuild gates ran and passed). Only the `map_editor2` assets changed;
no other page's hash moved.

### 4c. Real browser, network log — the request is the claim

`:8080` was **not running** (nothing listening; the lead PM's session had since ended). Ran the
sanctioned isolated env instead — `devenv.py up`, API `127.0.0.1:8081`, DB `assy_qa`, and
refreshed the snapshot from live through `snapshot_db.py`, whose source connection is opened
READ ONLY and self-tests that guard before reading a row (`[snapshot] source READ ONLY guard
verified (assy_manager)`). **Zero writes to the live database.** The env has been taken down
again.

The refreshed snapshot reproduces the lead PM's own populations exactly, so the numbers below
are the ones in the brief and not adjusted ones.

```
[7560.59] GET /api/maps/alignment/worklist?rule=eqp_product_frame_attribution&map_table=core_wafer_map  200
   rendered: DT-EQP-02|PRD-A=맵 191  DT-EQP-01|PRD-A=맵 160  DT-EQP-01|PRD-B=맵 97
             DT-EQP-02|PRD-B=맵 96   SYN-EQP|SYNTHETIC=맵 1

   -- 대상 테이블 -> dt_log --

[7560.60] GET /api/maps/alignment/worklist?rule=eqp_product_frame_attribution&map_table=dt_log        200
   rendered: DT-EQP-02|PRD-A=맵 40   DT-EQP-01|PRD-A=맵 40   DT-EQP-01|PRD-B=맵 20
             DT-EQP-02|PRD-B=맵 20   SYN-EQP|SYNTHETIC=맵 6
```

**191 · 160 · 97 · 96 · 1 → 40 · 40 · 20 · 20 · 6.** Exactly the figures in the brief.

Supersession, three switches back to back in one tick:

```
[7560.65] GET ...&map_table=core_wafer_map   [FAILED: net::ERR_ABORTED]
[7560.67] GET ...&map_table=dt_map           [FAILED: net::ERR_ABORTED]
[7560.69] GET ...&map_table=dt_log           200 OK
```

and afterwards `worklist.served === true`, `worklist.error === null`, rows = the `dt_log`
population. No console errors.

---

## 5. The declared binding not being adopted — SEPARATE FINDING, and now diagnosed

**Decision: out of scope this round, reported not fixed** (propose-before-fixing). Nothing about
it was silently changed.

It is no longer a hypothesis. Measured in the same browser session:

```
GET /api/maps/paint-rules?table=dt_log
  -> {"x":"dt_x","y":"dt_y","val":"c_bn","index":"dt_index","key_columns":["dt_job"],"source":"declared"}

after switching to dt_log:
  me2-col-x = core_x     me2-col-y = core_y
  me2-col-x options      = [dt_index, dt_x, dt_y, core_x, core_y]      <- THE CAUSE
  and the /view request went out as  ...&map_table=dt_log&x_col=core_x&y_col=core_y
```

**`dt_log`'s own schema contains `core_x` and `core_y`.** `session.resolveQuestion` adopts the
new table's declared binding only when the carried-over pick is *not a column of the new table*
(`known(asked.x)`), and here it is one — so the previous table's pick survives and the
declaration is never consulted. The rule's comment anticipates a half-carried pair; it does not
anticipate a **fully** carried one that happens to be valid in both tables.

Candidate repair, for a ruling rather than for this round: a table switch is a change of subject,
so the declared binding for the table now in force should win over a carried pick, with the
carried pick surviving only where the new table declares nothing. That changes what gets scored,
so it wants its own round and its own negative control.

**My harness fixture did NOT reproduce it, and that is recorded here on purpose**: R2d passed
green under the defect because my `dt_log` fixture had no `core_x` column — the fixture killed
the defect axis. A follow-up round must give the two tables **overlapping** column names or it
will verify nothing (map-pm lesson, 2026-07-30).

---

## 6. Documents (per `DOC_OWNERSHIP.md`, not edited here — doc-keeper's)

- `docs/spec/MAP_ALIGNMENT_SPEC.md` — the set-up row's request contract: worth stating that
  `map_table` is the **only** set-up field carried by `/worklist`, so it is the only control that
  re-asks the list, and that 기준 and the column pickers re-ask `/view` only.
- `docs/architecture/PRIMITIVES.md` — "in-flight request supersession" now has a second call
  site (`value_suggest.js:400`, `map2/main.js fetchWorklist`); worth listing so the third one
  reuses it instead of inventing a timeout.

## 7. Proposed lesson for `agent_workspace/memory/map-pm.md` (proposal only)

> **함정:** 질문을 바꾸는 컨트롤이 **자기 요청 중 일부만** 다시 던진다. `me2-table-select`는
> `/view`는 다시 물었고 `/worklist`는 안 물었다 — 화면 절반은 새 테이블, 절반은 옛 테이블이고
> **양쪽 다 그럴듯해서** 아무 표시도 나지 않는다. 스크린샷으로는 원리적으로 안 보인다.
> **올바른 방법:** 컨트롤 하나가 여러 요청에 실리면 **라우트 시그니처로 표를 만들어** 어느
> 요청이 그 필드를 필수로 받는지 확인하고, 대칭성으로 정하지 마라 — 여기서 기준·컬럼 셋은
> 다시 물으면 **안 되는** 것이 정답이었다. 그리고 증거는 **네트워크 로그**로 낸다.
