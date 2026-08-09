# Server report — Bonding plan material-availability relaxation (board request 2)

Date: 2026-08-04 · Lane: server-pm (isolated worktree `worktree-agent-a587fd4df1fe7192c`) · Status: DONE, committed on worktree branch, not pushed/merged.
Location note: the main-checkout `agent_workspace/reports/` path is not writable from this worktree agent (tool isolation), so this report sits at the **worktree root** per the task's fallback instruction.

## What the request actually mapped to

The board said "bonding plan availability gating" and guessed `server/bonding_plan.py`. The gating actually lives in **`server/transfer_plan.py`** (`_summarize_inline` + `assess_degradation` — the M2 availability engine that the bonding stage uses), with the M1 module (`bonding_plan.py`) supplying the core-kind path via `_reshape_m1_summary`. Both paths were relaxed; blast radius stayed inside the two plan modules and their tests.

## Semantics: three states at the config boundary (was two)

| Config state (per auxiliary role) | Before | After |
|---|---|---|
| Key **absent** | `missing` → `source_degraded` → `remaining=null` (availability hidden) | **`not_declared`** — NOT a degradation. Availability computed **without** that subtraction and served as a real number; kind listed in `inactive_subtractions` |
| Key present, binding broken (null, `"None"`, table/column typo) | `missing` / `connected(count_only)` / `column_unresolved` demotions | **unchanged** (guard side) |
| Key present and working | connected, exact numbers | **unchanged** (byte-identical payload — new field only appears when non-empty) |
| `transfer_log: "none"` (7c declaration) | `connected(untracked)` + upper bound | **unchanged** |
| `total_chips` absent | `missing` → `total_unknown` → `remaining=null` | **unchanged — the denominator stays required** |

Roles made optional (M2 inline): `transfer_log`, `origin_log`, `fail_sources` (kind-level: absent or empty dict), `process_history` (not a subtraction — relaxed to `not_declared` without the `history_incomplete` warning noise). `origin_area_map`, `bin_map`, `lot_membership` were already optional with their own named fallbacks — untouched.
Roles made optional (M1 / `GET /api/bonding-plan/core-summary`): `defect`, `eds_fail`, `used_chips`, `process_history`. M1 counts arithmetic unchanged (absent roles contributed 0 before and still do); only the status string and the new field changed.

### Exact conditions removed / made optional

1. `_summarize_inline`: absent `transfer_log` no longer resolves to `missing`; `used_not_declared` axis added — `transferred=null` (never a fake 0), `remaining` stays a number, by_core `used=null` with `remaining` still numeric, region/bins `transferred=null`.
2. `_summarize_inline`: absent `origin_log` no longer demotes; fallback subtraction (`total − Σfail − used`) now serves a **number**. A *declared* `frame:"origin"` fail source with no origin_log still gets `unavailable(origin_missing)` (declared contradiction keeps surfacing — test pinned).
3. `assess_degradation` untouched; instead `_status_is_degraded` returns False for `not_declared` (single choke point, same style as `connected(untracked)`).
4. `bonding_plan.get_core_summary`: the three status sites distinguish absence from breakage via the new shared predicate.
5. `_stage_role_statuses` (`GET /api/transfer-plan/stages`): auxiliary roles show `not_declared` when absent (new `_aux_role_status` helper), both on the inline and the M1-ref path.

Single definitions (no second spelling, per the `transfer_log_is_declared_none` discipline):
- `bonding_plan.STATUS_NOT_DECLARED = "not_declared"`
- `bonding_plan.role_is_declared(block, key)` — key-presence, not truthiness: present-null/garbage stays a (broken) declaration.

## Degradation signal shape (item 4)

Optional field, **present only when non-empty** (fully-declared configs keep an unchanged payload):

```json
{ "chips": {"total": 8, "remaining": 8, "remaining_reliable": true, "transferred": null},
  "sources": {"transfer_log": "not_declared", "origin_log": "not_declared"},
  "inactive_subtractions": ["transfer_log", "origin_log", "fail_sources"] }
```

- M2 inline vocabulary: `transfer_log` / `origin_log` / `fail_sources` (append order fixed by evaluation order).
- M1 vocabulary (`/api/bonding-plan/core-summary`): `defect` / `eds_fail` / `used_chips`; the dt reshape renames `used_chips`→`transfer_log`.
- `scope=lot` responses carry the union of their slot summaries' lists; the lot bins merge also propagates `transferred=null` (a pooled sum of unknowns is not 0).
- No new warning type, no UI — client may ignore the field (board's instruction).

## Both-sides semantics tests (item 3)

New file `server/tests/test_availability_relaxation.py` (10 tests):
- absent side: `test_absent_declarations_serve_availability` (remaining 8 on the shared fixture whose fully-subtracted truth is 2 — proves the terms were skipped, not applied), bins/lot variants, M1 + reshape variants.
- guard side: `test_declared_but_broken_still_demotes`, `test_m1_broken_used_chips_still_demotes`, `test_m1_total_chips_stays_required`, `test_declared_origin_frame_fail_source_without_origin_log_still_surfaces`, `test_fully_declared_config_payload_unchanged`.

Adjusted existing tests (all were pinning "absence == breakage"):
- `test_transfer_plan.py::test_dt_stage_degradation_also_surfaced` — now breaks the binding instead of deleting the key (keeps guarding the degradation side).
- `test_bonding_plan.py::test_missing_role_partial_operation` — now asserts both sides in one test; `test_empty_config_all_missing` — total `missing`, aux `not_declared`.
- `test_transfer_untracked.py::test_absent_key_stays_missing` → `test_absent_key_is_not_declared_not_untracked` (absent is a third state; null/`"None"` accidental-missing tests unchanged and passing).
- `test_key_canonicalization.py::test_float_stored_slot...` — asserted the old `remaining_upper_bound==0` shape for an undeclared transfer_log; now asserts `remaining==0` + `remaining_reliable=true` (the arithmetic moved into `remaining` itself, which is the point of the request).

## Config / operator action (item 5)

- `server/config/transfer_plan_config.json.sample` and `bonding_plan_config.json.sample`: `__comment` now states the optionality rule (loaders ignore unknown root keys — verified).
- **A live config needs NO change to benefit.** Sites that never declared the auxiliary tables get availability numbers immediately after deploying this server build. Sites that HAVE working declarations keep exact current behavior. The only optional cleanup: a site that had declared a deliberately-broken binding as a workaround may now simply delete the key.

## Stale doc spots (for doc lanes — NOT rewritten by me)

1. `docs/guide/CONFIG_GUIDE.md` §5.8 status dictionary (~line 246): "`missing` = 바인딩 선언/테이블 없음" — absence is now `not_declared`; dictionary needs the new status + `inactive_subtractions` field.
2. `docs/guide/CONFIG_GUIDE.md` ~line 581: "`missing`이면 ①테이블 미선언…" — ① is no longer a cause of `missing`.
3. `docs/guide/CONFIG_GUIDE.md` ~line 237 (M2 role list): should state the auxiliary roles are optional.
4. `docs/guide/config/transfer_plan_config.md`: line 96 (공통 규율 — "역할은 통째로 missing"), 111, 118 함정 ③ (undeclared origin_log no longer degrades bins), 143 (7c bullet: "키 부재 … 전부 종전 그대로 missing" now wrong), 144 (`transfer_log` 미연결 — split absent vs broken), 150-151 (`origin_log` 미연결), 162 (`process_history` 미연결 — no warning when absent), 168 (`fail_sources` 미연결).
5. `docs/guide/config/bonding_plan_config.md`: lines 23, 49, 67 (미선언 = missing claims).
6. `docs/guide/config_reference/transfer_plan_config.json` + `bonding_plan_config.json` — copies now diverge from the updated `.sample`s.
7. Living docs (`docs/architecture/backend.md` / spec sections describing the source-summary contract) should gain the `not_declared` status and `inactive_subtractions` field — doc-keeper lane (not edited here per worktree rules).

## Boundary-contract note for 총괄 → Client PM

Sanctioned by the board request, but the client should be told:
- New `sources.*` status string value `not_declared` (renderable as e.g. "미사용/미선언"; it is NOT an error state).
- New optional top-level field `inactive_subtractions` (slot, lot, and M1 responses) — ignorable.
- `chips.transferred` / bins `transferred` / by_core `used` can now be `null` while `remaining` is a **number** (previously null-transferred implied null-remaining). `remaining_reliable` remains the only reliability authority.
- validate: sources that were previously `availability_unreliable` (판정 불가) can now produce real `qty_shortage` judgements — expected behavior change, this is the feature.

## Verification

- Domain files: `test_availability_relaxation.py`, `test_transfer_untracked.py`, `test_bonding_plan.py`, `test_transfer_plan.py`, `test_key_canonicalization.py` — **200 passed**.
- Full suite (`conda run -n assy_manager python -m pytest server/tests/ -q`): first run 8 failed / 1835 passed; the 1 domain failure was the stale `test_key_canonicalization` assertion (fixed above). The other **7 failures are pre-existing worktree-baseline failures** (ingestion/watcher: `test_api` x2, `test_composite_business_key`, `test_contention_fixes`, `test_map_meta_registrar` x2, `test_trace_fixture`) — **proven by `git stash` + rerun: identical 7 failures without my changes** (worktree lacks gitignored user assets; known lesson). Final post-fix full-suite result recorded in the summary message.
- Concurrent-pytest discipline observed: waited out two other-lane runs (process check) before every run.

## History draft (for 총괄 integration — worktree rule: not written to docs/history by me)

> fix(plan): auxiliary availability declarations are optional — absence is a site statement, not a broken binding. `fail_sources`/`origin_log`/`transfer_log`/`process_history` absent → `not_declared` (no demotion), availability served without those subtractions, skipped kinds named in `inactive_subtractions`; declared-but-broken keeps every demotion; `total_chips` stays required. Real-fab feedback: deductions live on the map object, not in per-lot side tables.

## Lesson proposals (for server-pm memory — 총괄 검수 후 반영)

1. Config-boundary states are three, not two: absent / present-broken / present-working. A falsy check (`cfg.get(k)`) collapses the first two and makes "the site doesn't use this" indistinguishable from "the site misconfigured this" — use key-presence (`k in cfg`) predicates, defined once.
2. Worktree full suite currently has 7 pre-existing ingestion/watcher failures (missing gitignored user assets). Before attributing a red suite to your change, stash-and-rerun the failing subset — it split 8 into 7 baseline + 1 real here.

## Files touched

- `server/transfer_plan.py` — engine relaxation, `_aux_role_status`, `_bins_block(transfer_inactive=)`, lot merge None-propagation, module-header contract note.
- `server/bonding_plan.py` — `STATUS_NOT_DECLARED`, `role_is_declared`, `SUBTRACTION_ROLES`, three status sites, `inactive_subtractions`, header note.
- `server/config/transfer_plan_config.json.sample`, `server/config/bonding_plan_config.json.sample` — optionality comments.
- `server/tests/test_availability_relaxation.py` (new), `test_transfer_plan.py`, `test_bonding_plan.py`, `test_transfer_untracked.py`, `test_key_canonicalization.py`.
