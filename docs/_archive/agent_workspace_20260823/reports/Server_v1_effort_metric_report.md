# Server — V1 core-value instrument: interaction score to completion

**Status: complete.** Both lead addenda applied. Not committed (parallel agents are editing the same tree; lead integrates).

## What changed

- New instrument end-to-end: optional `effort:{session_id,key,mouse,nav,nav_preserved}` on `PUT /tables/{t}/data/updates` → `interaction_effort_logs` (one row per `AuditLog.transaction_id`, **raw counts only**) → `/dashboard/summary` → `effort{avg_score,tx_count,session_count,weights,measured_ratio,window_days,unavailable_reason}`, aggregated per-session then across sessions.
- New `GET /api/effort/config` serves `{weights, context_preserving_transitions}` from new config `effort_metric.json` (weights 1/3/5 + `nav_preserved: 0`; allowlist ships EMPTY).
- Both indices added to `setup_db_performance.py` **and** `models.py`, plus an idempotent `ALTER` guard for `nav_preserved_count`.

## Files

| Path | Change |
|---|---|
| `server/effort_metric.py` | **new** — config load + weight/transition resolution (wildcards rejected) |
| `server/config/effort_metric.json.sample` | **new** — tracked sample; real file is gitignored, absence = defaults |
| `server/database/models.py` | **new** `InteractionEffortLog` + 2 indices |
| `server/database/schemas.py` | `EffortReport` (extra="allow" for named-400), `GeneralUpdateBatch.effort`, `EffortStat`, `DashboardSummaryResponse.effort` |
| `server/database/crud.py` | `EFFORT_WINDOW_DAYS`, `record_interaction_effort`, `get_effort_stats` |
| `server/main.py` | `_validate_effort`, recording in the PUT endpoint, `_get_effort_stat` + cache/timeout, `GET /api/effort/config`, summary wiring |
| `server/scripts/setup_db_performance.py` | Step 3.7 — 2 indices `CREATE INDEX CONCURRENTLY IF NOT EXISTS` + column ALTER guard |
| `server/tests/test_effort_metric.py` | **new** — 53 tests |
| docs | SSOT §1+§4, `data_model` §1.1+§2.4, `backend`, `CONFIG_GUIDE`, `config/README` + **new** `config/effort_metric.md`, `POSTGRES_OPERATIONS_GUIDE` §3.1, history entry + `gen_index.py` |

## Side-effect checklist (StableDevelopmentProtocol §1)

- **Signature/contract**: `crud.apply_batch_updates` 4-tuple return **unchanged**. `GeneralUpdateBatch` gained one optional field — all 20+ call sites (watcher, chain worker, map_meta_registrar, backfill script, tests) construct it without `effort` and are unaffected. `record_interaction_effort`'s `nav_preserved` is a defaulted param.
- **Server↔client contract**: cell shape, WS event names/payloads, existing REST paths **untouched**. `DashboardSummaryResponse.effort` is additive+Optional; old clients ignore it. Two new endpoints only.
- **Non-human paths**: watcher/chain/scripts call `crud` directly, never through HTTP — structurally cannot emit `effort`. That is the "unmeasured" case working as designed.
- **`silent: true`**: recording sits outside the broadcast branch, so map-editor silent saves are still measured. Correct — silent suppresses broadcast, not measurement.
- **Timing/session**: recording runs **after** the correction commits, in `run_in_threadpool`, in its own transaction; failure logs and returns False, request still 200. Placed after `msg_items` is materialised because `db.commit()` expires ORM instances — pinned in a code comment so a future edit doesn't reintroduce a reload on the response path.
- **Shared state**: `EFFORT_CACHE` mirrors `RECORRECTION_CACHE` exactly (worst case is a stale read, as today).
- **Scale**: aggregate is windowed (7d) behind a covering index; `measured_ratio`'s denominator **reuses the existing `idx_audit_user_recorrection`** (`timestamp` + INCLUDE `transaction_id` WHERE `source_name='user'`) — no new audit index. 60s TTL cache + 1500ms `statement_timeout`; on failure `avg_score`/`measured_ratio` go null with a reason. Both instruments run last and roll back independently (test pins that one failing doesn't take the other down).

## Tests

- **997 passed, 0 failed** (944 baseline + 53 new), `conda run -n assy_manager python -m pytest tests/ -q`.
- **Fault injection first** — every load-bearing decision was proven to fail on a broken implementation before I trusted the green:

| Injected defect | Result |
|---|---|
| per-session average → flat per-tx average | 2 fail |
| absent effort coerced to `(unknown,0,0,0)` | 1 fail |
| 400 rejection → `max(0, int(v))` clamp | 8 fail |
| `extra="allow"` → `"ignore"` (reproduces map-pm's live defect) | 1 fail |
| `nav_preserved_count` discarded (stored as 0) | 1 fail |

- **DDL compiled against the PostgreSQL dialect** and diffed against the perf script — `models.py` and `setup_db_performance.py` emit identical definitions.

## Lead's confirmation items

1. **`measured_ratio` present and honest** — yes. Denominator = `count(DISTINCT transaction_id)` over `audit_logs` with **positive** `source_name == USER_SOURCE` match, so parser/chain traffic is excluded (parsers use the ingested filename as source name, so a blacklist is impossible — same reasoning as §2.3). Numerator/denominator populations are aligned by construction: an effort row is written **only if the tx produced at least one user-source audit log**, so the ratio can never exceed 1.
2. **Index in `setup_db_performance.py`, not only `models.py`** — yes, Step 3.7, `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, gated on table existence, plus `ANALYZE`. Documented next to the recorrection index in `POSTGRES_OPERATIONS_GUIDE` §3.1.

## Escalations / decisions needing you

1. **Response has 2 fields beyond your spec**: `unavailable_reason` (required by your own degradation clause) and `window_days` (7d, mirrors the recorrection window — the numbers are unreadable without it). Your 5 named fields are all present. Flagging rather than assuming.
2. **Config home**: surveyed all 12 existing config files; every one is domain-scoped (ingestion/chain/ontology/maps/schema/plan/db). None owns UX instrumentation, so I added a small `effort_metric.json` rather than forcing it into an unrelated file.
3. **Production DB write is NOT done** — same gate as queue item 5. New installs get the table+indices from `create_all`; a DB where the table already exists needs `setup_db_performance.py` (Step 3.7). `uq_effort_transaction` failing there means duplicate tx rows exist and must be cleaned first — the guide gives the query.
4. **Known bias, documented not hidden**: a tx where the human worked but nothing changed (all `has_changed`-guarded) records no effort — there is no completed correction, so the unit doesn't apply.
5. **Wildcard rejection is drop+WARNING log**, and the entry is absent from `GET /api/effort/config`. I did not fail the whole config on one bad entry (that would take the endpoint down); rejection is observable in the log and in the served list. Say the word if you want it harder.
6. Untouched by me and left to their owners: `PRIMITIVES.md`, `CODE_MAP.md`, `FEATURE_CHECKLIST.md`, `PROJECT_STATUS.md`, all `client2/**`.

## Proposed memory lessons (do not add directly)

- **Trap**: pydantic silently drops undeclared keys, so a client field the server hasn't declared vanishes with no error and no 422 — and if the rest of the payload is valid, nothing looks broken. **Fix**: for any payload where a dropped value is indistinguishable from an unsent one, take `extra="allow"` and reject unknown keys explicitly by name (`extra="forbid"` yields 422, not the 400 most contracts specify).
- **Trap**: an allowlist applied at COLLECTION time bakes the classification into stored data. For metrics that cannot be recomputed retroactively, a misclassification is then permanently unfixable. **Fix**: store both sides of the split as raw counts and express the classification as a query-time weight (defaulting to 0 keeps today's number identical).
