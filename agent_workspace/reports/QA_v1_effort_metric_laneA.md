# QA — V1 core-value instrument, LANE A (contract + server + API)

**Reviewer:** qa-reviewer (adversarial) · **Date:** 2026-07-29 · **Baseline:** `b697d34` → uncommitted working tree
**Scope:** `server/effort_metric.py`, `server/main.py`, `server/database/{schemas,models,crud}.py`,
`server/scripts/setup_db_performance.py`, `server/config/effort_metric.json.sample`,
`server/tests/test_effort_metric.py`; client read for contract symmetry only (lane B exercises it).

## Verdict

**GO-WITH-FIXES — F1 and F2 are blocking for the BASELINE WINDOW, not for the merge.**

The server implementation is careful and the test suite is unusually honest. But two defects both
push the score DOWN (flattering), both are silent, and both corrupt the one thing this round exists
to produce: a "before" baseline that cannot be recollected. Merging the code is fine. Treating the
data it collects as the baseline is not, until F1 and F2 land.

Method note: all probe results below were produced by a temporary pytest file run against the real
FastAPI app via the project's `client`/`db_session` fixtures, then deleted. No source was modified.

---

## 1. Confirmed defects

### F1 [HIGH] A no-op save erases the effort it cost — the instrument is blindest exactly where friction is highest

**Where:** `server/main.py:2089-2097` (record only when `created_logs` contains a `source_name == 'user'`
entry) · `server/database/crud.py:925-941` (`has_changed` guard emits no audit log for a no-op) ·
client resets unconditionally on `res.ok`: `client2/src/api.js:318-322`, `client2/src/ui.js:225-226`,
`client2/src/clipboard.js:527-528` and `:771-772`, `client2/src/main.js:1763-1769`,
`client2/src/enrichment.js:490-491`, `client2/src/map_editor.js:4388-4401`.

**Probe (measured, not inferred):** two identical PUTs. The second returns

```
200 {'status': 'success', 'updated_count': 1, 'change_count': 0, 'deleted_row_ids': [], 'created_logs': [], 'scope': None}
```

`InteractionEffortLog` rows delta = **0**. The client sees `res.ok === true` and calls `commit()`.

**Failure scenario:** an operator spends 20 keystrokes and 5 clicks correcting a cell. The value they
type equals what is already stored (or the guard filters it — stale grid, whitespace/numeric
normalisation at `crud.py:935-939`). Server: 200, no audit row, no effort row. Client: counters → 0.
The operator sees nothing changed, re-does the correction properly with 3 keystrokes and 1 click.
That tx is recorded with score 6. True cost of the correction: ~40. **The two-attempt correction —
the highest-friction event in the product, and the precise thing core value #1 exists to detect —
reports the LOWEST score in the dataset.**

**Direction:** flatters. **Recoverable later:** no.

**Fix:** return `effort_recorded: bool` from `PUT /tables/{t}/data/updates` and have the client call
`commit()` only when it is true. (`change_count` is already in the response, so the client *could*
gate on `result.change_count > 0` — but that needs `commit()` moved after `await res.json()` in
api.js/clipboard.js/ui.js. Prefer the explicit server field: the decision belongs to the side that
knows whether a row was written.)

---

### F2 [HIGH] An all-zero snapshot is recorded as a genuine score-0 correction and halves the session average

**Where:** explicit zeros are accepted as MEASURED — `server/main.py:_validate_effort` passes them and
`server/tests/test_effort_metric.py:478-483` asserts this as intended. The client sends `snapshot()`
unconditionally: `api.js:307`, `ui.js:219`, `clipboard.js:522` and `:765`, `main.js:1736`,
`enrichment.js:474`, `map_editor.js:4375`.

**Probe:** one session, one real correction (20 key / 4 mouse / 1 nav = score 37) followed by one
zero-effort correction:

```
{'avg_score': 18.5, 'tx_count': 2, 'session_count': 1, 'measured_ratio': 1.0}
```

**Reachability:** F1's aftermath is the certain path — right after any successful save, and right
after any no-op save, the counters are 0. Any subsequent data PUT before the human touches the
keyboard again reports a legitimate-looking zero. `map_editor.js` deliberately avoids this (only one
of its three PUTs carries effort — see the reasoning at `:4347`, `:2969`, `:4370-4375`); the grid,
clipboard, range-apply, tx-mode and enrichment paths have no equivalent guard.

**Direction:** flatters.

**Correction to a stated assumption:** the known limitation map-pm recorded (two concurrent non-Tx
saves attributing the same effort twice) **inflates**, which is the safe direction. But sequencing
**deflates**. So "the bias is always conservative" is not true as shipped — the two effects run in
opposite directions and the deflating one is the more common.

**Fix:** the client should omit `effort` entirely when the snapshot is all-zero. That reuses the
contract's own existing primitive — absence means NOT MEASURED — instead of inventing a new rule, and
needs no server change.

---

### F3 [MEDIUM] A typo'd or invented route name is inert, is served back verbatim, and therefore reads as live

**Where:** `server/effort_metric.py:112-156` validates entry *shape* and rejects wildcards, but has no
route vocabulary to validate *against*. `GET /api/effort/config` (`server/main.py:get_effort_config`)
echoes the entry. The client matches exactly (`client2/src/effort_meter.js:275-282`) and never fires.

**Failure scenario:** the lead approves the transition the SSOT itself names — `{"from": "doe", "to":
"dt_map"}`. No route id `doe` or `dt_map` exists; the real ids are `map_editor` and
`map_editor:material` (`client2/src/map_editor.js:4842-4846`). The entry passes validation, is served,
logs no warning, and exempts nothing. The nav penalty stays applied while the lead believes it was
removed. This is functionally identical to the wildcard case the module was written to prevent — and
worse, `docs/guide/config/effort_metric.md:39` tells the author to verify via the endpoint, which
returns the bad entry. **The recommended verification produces a false positive.**

Note the guide (`:39`, `:75`) documents wildcard rejection but never lists the valid route ids, so an
author has no way to get this right except by reading `effort_meter.js`.

**Direction:** inflates (safe), but silently, and it defeats the stated purpose of the wildcard rule.

**Fix:** serve the known route vocabulary from `GET /api/effort/config` and reject unknown route ids
the same way wildcards are rejected. Minimum viable: list the ids in the config guide.

---

### F4 [MEDIUM] A malformed `effort` blob rejects the user's data correction outright

**Where:** `server/main.py:1979-1981` — `_validate_effort` runs before `apply_batch_updates`; every
failure raises 400 and nothing is written (`test_effort_metric.py:469-475` asserts this as a feature).

**Probe:** `effort` without `session_id` returns **422**, not 400:

```
422 {'detail': [{'type': 'missing', 'loc': ['body', 'effort', 'session_id'], ...}]}
```

Two problems. First, this contradicts the module's own stated invariant — `crud.record_interaction_effort`'s
docstring ("계측은 계측 대상을 절대 깨뜨리지 않는다") and `effort_meter.js:45-47` invariant 4 both
promise the instrument cannot break what it measures. As shipped, the instrument is the *only* thing
in the request that can. A future client counter, a manipulated sessionStorage entry, or any
session-id edge case yielding `""` turns into **every save from that browser returning 400/422** —
a total data-entry outage caused by the metric.

Second, it is a deviation from the contract you specified: `session_id` is **not** optional inside
`effort` (`server/database/schemas.py` `EffortReport.session_id: str`), and its absence is a pydantic
422 that never reaches `_validate_effort`, so the "400 naming the offending key" contract does not
hold uniformly.

**Fix (your call on the first half):** keep 400-on-unknown-key — the loudness is the point — but
decouple the consequence: apply the correction, skip the effort row, and report the rejection in the
response body. At minimum, make `session_id` `Optional[str] = None` in the schema so `_validate_effort`
owns the rejection and the status code is uniformly 400.

---

### F5 [MEDIUM] The instrument has no display surface, so a collection failure during the only baseline window is invisible

`/dashboard/summary → effort` is served, but nothing in `client2/src` reads `effort`, `avg_score` or
`measured_ratio` (verified by grep across all of `client2/src`). The recorrection rate has an admin
Overview line; this does not.

Combined with F1/F2 and with `crud.record_interaction_effort` swallowing every exception
(`except Exception: print(...); return False`), a total collection outage — missing table, a DB whose
`interaction_effort_logs` predates `nav_preserved_count` and never had `setup_db_performance.py` run
against it, unique-constraint pathology — produces **zero user-visible signal**. You would discover it
by curling the endpoint, or not at all.

**Fix:** surface `avg_score` + `measured_ratio` + `unavailable_reason` on the admin Overview in this
round, before the DOE overhaul starts consuming the window. `measured_ratio` is the outage detector
you already built; nothing currently reads it.

---

### F6 [LOW] `unavailable_reason` is a canned string that names the wrong cause

`server/main.py:_get_effort_stat` sets `"집계 시간 초과 또는 실패 (idx_effort_window 인덱스 확인)"` for
*any* exception. A missing table or a missing `nav_preserved_count` column reports "check the index".
The actual exception goes only to stdout. Degradation is honest (the field reads unavailable, never a
wrong number) but the reason misdirects the operator.

### F7 [LOW] Batch-level unknown keys are still silently ignored

**Probe:** `{"updates": [...], "efort": {...}}` → **200**, no effort row, no warning.
`GeneralUpdateBatch` has no `extra="forbid"`. The strictness you demanded inside `effort` stops one
level up, at the field that carries it — a rename or typo of `effort` itself is exactly the
"dropped value indistinguishable from a value never sent" shape, and it is unguarded. Detectable via
`measured_ratio` → 0, but only if someone is looking (see F5).

### F8 [LOW] `GeneralUpdateItem.source_name` defaults to `"user"` — the denominator's honesty rests on callers remembering

The `measured_ratio` denominator is `source_name == 'user'` (`crud.get_effort_stats`). I re-searched
the gitignored user area per the 2026-07-25 shim lesson: all three shipped automated writers declare
`custom_script` — `server/ingestion_workspace/core_defect_map/auto_update/generate_core_defect.py:147`,
`.../dt_map/auto_update/generate_dt_map.py:103`, `.../eds_fail_map/auto_update/generate_eds_fail.py:155`.
**The denominator is currently honest.** But any future automated caller that omits `source_name`
silently inflates it and depresses coverage. Pre-existing default; newly load-bearing.

---

## 2. Hypotheses attacked and found safe

- **Index reality (your #6).** `uq_effort_transaction` and `idx_effort_window` in
  `setup_db_performance.py:143-166` match `models.py:63-77` **exactly** — `(transaction_id)` UNIQUE and
  `(timestamp) INCLUDE (session_id, key_count, mouse_count, nav_count, nav_preserved_count)` — both
  `CONCURRENTLY IF NOT EXISTS`. The connection is `execution_options(isolation_level="AUTOCOMMIT")`
  (`setup_db_performance.py:14`), so CONCURRENTLY is legal. The denominator query
  (`count(distinct transaction_id) WHERE source_name='user' AND timestamp >= cutoff`) is genuinely
  covered by the existing partial index `idx_audit_user_recorrection` (`models.py:42-47`): leading key
  `timestamp`, predicate matches, `transaction_id` in INCLUDE. The comment's claim that no new index is
  needed is correct.
- **Absence never becomes zero on the server (your #1).** Probe: a write declaring
  `source_name='chain_worker'` that *does* carry an effort blob records **nothing** — `main.py:2090-2093`
  requires a user-source audit log. Absent `effort` records nothing. No server path coerces absence to 0.
- **`measured_ratio` cannot exceed 1 (your #4).** Probe: 3 measured txs / 3 user audit txs → ratio 1.0,
  zero orphan effort txs. `created_logs` entries always carry `source_name` (`crud.py:327`) and the batch
  path persists them via `bulk_insert_audit_logs` (`add_to_cache=(logs_to_cache is None)` at
  `crud.py:949/979/1095/1237`), so the numerator stays a subset of the denominator. Only residual is a
  millisecond-wide window boundary where the effort row's `server_default=func.now()` lands inside the
  cutoff while the audit row's Python-side `ts` lands outside — negligible.
- **Retry idempotency (your #2).** `uq_effort_transaction` + `IntegrityError` → rollback → first write
  wins. A retry that generates a new `transaction_id` is a genuinely new tx and bills once. Counters are
  preserved on every failure path (verified at all seven client call sites: reset is on the success
  branch only).
- **Event-loop safety.** `record_interaction_effort` runs via `run_in_threadpool` (`main.py:2095`);
  `_get_effort_stat` and `get_effort_config` are sync defs (threadpooled). No sync DB call on the loop.
- **Dirty-state flush — refuted.** I expected the new `db.commit()` to persist the synthesized
  `row.data` that `inject_system_columns` writes after `apply_batch_updates` already committed. `data`
  is **not** a mapped column on the dynamic models (`models.py:389-392` column list; the class is built
  by `type(class_name, (object,), {...})` at `:431`), so setting it does not dirty the session. Nothing
  reads `row.*` after the effort commit — `main.py:2099-2104` returns only `len(results)` and
  pre-built dicts. The comment at `main.py:2086-2088` correctly identifies why the placement matters.
- **Weight config hardening (your #8, first half).** Negative, non-finite, bool and non-numeric weights
  fall back per-key with a warning (`effort_metric.py:95-109`). The metric cannot be inverted by config.
  Wildcards are rejected, not kept as inert literals, and valid neighbours survive.
- **Raw counts only, weights at query time.** Confirmed. `nav` and `nav_preserved` are stored separately
  (`models.py:69-70`) and weighted in `get_effort_stats`, so the allowlist remains a query-time
  interpretation. The re-scoring path genuinely works.

## 3. Requires runtime verification (cannot be settled from code)

- That `SET LOCAL statement_timeout` actually fires on the live PostgreSQL session — the branch is
  dialect-gated and the suite runs on SQLite.
- `EXPLAIN` on live `audit_logs` (2.6M rows) plus a populated `interaction_effort_logs`, confirming
  Index Only Scan on both halves of the summary query.
- The real `measured_ratio` under production usage. Code cannot tell you what fraction of actual
  corrections carry effort; only observation can, and F5 means nothing currently shows it.
- Whether AG-Grid emits multiple `cellValueChanged` events for a single gesture on this build — that
  would multiply F2. Lane B's browser run can settle it.

## 4. Documentation integrity

- **`docs/overview/SYSTEM_OVERVIEW.md` §1 overstates, in the flattering direction.** It now claims the
  score is what the human spent "한 교정 트랜잭션이 완료될 때까지". As shipped it is *everything since
  the last successful save*, which (a) attributes browsing and reading between corrections to the next
  correction, and (b) **deletes** the effort spent on an attempt that turned out to be a no-op.
  `main.py:2083` documents (b) as a known bias — "not captured by this instrument" — which understates
  it: the effort is not merely unattributed, it is erased from the baseline (F1). The SSOT should carry
  the caveat, not only a code comment.
- **`docs/guide/config/effort_metric.md:39,75`** documents wildcard rejection but omits the route
  vocabulary, and recommends a verification method that returns a false positive for typo'd routes (F3).
- **`docs/process/DOC_OWNERSHIP.md`** has no row for `server/effort_metric.py`,
  `interaction_effort_logs`, or `/api/effort/config`. I checked the ownership table by changed code
  path rather than by the implementers' follow-up lists: the recorrection metric has no row either, so
  this is consistent with existing (imperfect) convention rather than a regression — but a new module,
  a new config file, a new table and a new endpoint landing with no ownership row means the next agent
  grepping by path finds nothing.
- Otherwise the doc set is genuinely in sync: `data_model`, `backend`, `frontend`, `CONFIG_GUIDE`,
  `guide/config/README`, `POSTGRES_OPERATIONS_GUIDE`, `PROJECT_STATUS`, `FEATURE_CHECKLIST` and three
  history entries all reflect the change.

## 5. Proposed lesson for `agent_workspace/memory/qa-reviewer.md` (for lead approval — not self-added)

> **함정:** 계측(instrument) 검수에서 서버의 "0을 저장하지 않는다"만 확인하면, **클라이언트가 0을
> 만들어 보내는 경로**를 놓친다. 서버는 absence/zero를 정확히 구분하는데 클라가 성공 직후 카운터를
> 리셋하고 다음 요청에 0을 실어 보내면, 서버 입장에선 완벽하게 정상인 "측정된 0"이 된다.
> **올바른 방법:** 수집 계약은 **양쪽 끝에서** 검증한다 — ① 서버가 absence를 0으로 만드는가 ②
> 클라가 0을 만들어 absence로 보내야 할 것을 measured로 보내는가 ③ 서버가 **기록하지 않기로 한**
> 요청(no-op·비사람 소스)에 대해 클라가 카운터를 리셋하는가. ③이 성립하면 공수는 조용히 소멸한다.
