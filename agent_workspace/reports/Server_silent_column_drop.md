# Server — Silent undeclared-column drop, made visible

**Scope:** `server/database/crud.py` `apply_row_update_internal`, the single funnel every write path converges on.
**Behaviour change:** none. Only the silence is fixed.
**Suite:** 494 passed before (HEAD `8e80fcc`), **498 passed / 0 failed** after (+4 new tests), 69.4s.
**Not committed.** No live DB, no live `server/config/*.json`, no server restart.

---

## 1. The change

Two hunks, 46 insertions.

`server/database/crud.py` — new module-level registry + emitter, placed beside the existing
`_warn_audit_truncation_once`, which solves the identical problem (per-cell hot path, warn once
per `(table, column)`) and which this deliberately mirrors:

```python
def _warn_undeclared_column_once(table_name: str, col_name: str):
    warned = _undeclared_column_warned.get(table_name)
    if warned is None:
        warned = _undeclared_column_warned[table_name] = set()
    elif col_name in warned or len(warned) >= _MAX_UNDECLARED_WARNED_PER_TABLE:
        return
    warned.add(col_name)
    logger.warning(...)
```

and the call site, at the drop itself (`crud.py:603-610`):

```python
        col_types = config.get("column_types", {})
        if col_name not in col_types:
            # Drop behaviour is deliberately unchanged: rejecting the write would turn a
            # lagging config into an outage. Only the silence is fixed.
            _warn_undeclared_column_once(table_name, col_name)
            continue
```

**Why a dict-of-sets rather than `set[(table, col)]`.** The already-warned path is the one that
can repeat millions of times. A tuple key would allocate on every dropped cell. `dict.get` +
`set.__contains__` allocate nothing, and both operands are interned strings whose hashes are
cached. This is the only reason the shape differs from `_audit_truncation_warned` above it.

**No formatting before the membership check.** The f-strings are constructed after the early
return, so the warmed path never builds a string.

**What bounds the registry.** Keys are `(table name, column name)`; for a correct caller that is
bounded by schema size. But column names come from the *payload*, not the schema — a malformed
header row or a parser emitting values as headers can supply unbounded distinct names. So there
is a per-table budget of 64. On saturation the table stops growing **and** stops warning; the
transition is announced once:

> `[Schema] Reached 64 distinct undeclared columns for table 'X'; further undeclared columns on this table will be dropped WITHOUT a warning.`

That is a deliberate trade: bounded memory and a bounded log, at the cost of returning to silence
in the pathological case — but never silently returning to silence.

Entries are never cleared. A column *added* to the config simply stops reaching the drop branch,
so a stale entry is inert. A column *removed* from the config after it has already warned in this
process will not re-warn; the next process restart re-arms it.

---

## 2. The four proofs

`server/tests/test_undeclared_column_warning.py`, 4 tests, 1.1s.
Warnings are captured with a handler attached directly to the `"Server"` logger rather than
`caplog` — these tests turn on *how many* records are emitted, so capture must not depend on
propagation or on pytest's per-test handler juggling. An autouse-style fixture clears the process
global before and after each test, otherwise a prior test could pre-warm a pair and make
"fires once" pass vacuously.

| # | Proof | Test |
|---|---|---|
| 1 | Fires on the real path; row still saves declared columns | `test_undeclared_column_warns_once_and_row_still_saves` |
| 2 | Fires exactly once on repeat | same test (second PUT) + `test_repeated_rows_in_one_batch_warn_once` |
| 3 | Distinct `(table, column)` pairs each get their own line | `test_distinct_table_column_pairs_each_warn` |
| 4 | Registry is bounded and announces its own silence | `test_registry_is_bounded_and_announces_its_own_silence` |

**Proof 1 — real path.** Driven through `PUT /tables/inventory_master/data/updates` with a
`TestClient`, i.e. the actual endpoint the client calls, not a direct crud call. Payload carries
`part_no`/`category`/`stock_qty` (declared) plus `eventtime` (undeclared). Asserted: HTTP **200**,
the row exists with all three declared values persisted, `eventtime` genuinely absent from the row
(the write really did lose it), and exactly one warning naming both `eventtime` and
`inventory_master`.

**Proof 2 — once.** The identical PUT is repeated; warning count stays at 1. Separately,
`test_repeated_rows_in_one_batch_warn_once` sends **500 rows in one batch** all carrying the same
undeclared column — the drop is a per-cell branch, so this is the case that would produce 500
lines without the guard. It produces 1.

**Proof 3 — distinct pairs.** `(inventory_master, ghost_a)`, `(inventory_master, ghost_b)`,
`(production_plan, ghost_a)` → 3 lines, each asserted individually. This pins that the key is the
pair, not the table and not the column.

**Proof 4 — required defect injection.** Backed up `crud.py` byte-exact first
(SHA256 `A9BD7377…624CFD`), injected, ran, restored, re-verified the hash — no CRLF drift, and the
restore was confirmed by hash equality rather than by an absent `git diff`.

- **Defect A — warning suppressed** (call removed, `continue` kept): **all 4 tests fail.**
- **Defect B — once-guard removed** (fires on every cell): **2 tests fail** — precisely the two
  once-tests (`…warns_once_and_row_still_saves`, `…repeated_rows_in_one_batch_warn_once`). The
  other two still pass, correctly: they write one row per pair and do not exercise repetition.
  The failure output also shows the 500-line log flood the guard exists to prevent.

The two injections fail *different* subsets, which is the useful signal: the tests discriminate
between "does it fire" and "does it fire once", rather than all keying off one assertion.

---

## 3. Hot-path measurement

Script: `<scratchpad>/bench_undeclared.py`, conda `assy_manager`, isolated (`TESTING=True`,
`DATABASE_URL=sqlite:///:memory:`, `ASSY_DATA_ROOT` → scratchpad).

**Part 1 — isolated per-call cost on the already-warned path** (`timeit`, 2,000,000 iterations,
best of 7):

| | ns/call |
|---|---|
| `_warn_undeclared_column_once` (pair already warned) | 160.7 |
| bare 2-arg function call | 109.0 |
| baseline (`lambda: None`) | 56.9 |
| **added per dropped cell vs. the pre-fix bare `continue`** | **≈ 105.8 ns** |
| — of which is the Python call frame itself | 52.1 ns |

So the logic I added costs ~52 ns; the other half is the cost of it being a function at all.
**Per 1,000,000 dropped cells: ~106 ms.** A 100,000-row file with ten undeclared columns —
a badly wrong config — pays about a tenth of a second across the whole file.

**Part 2 — end-to-end ingest A/B** (3,000 rows × 6 declared columns, 1000-row chunks through
`crud.apply_batch_updates`, 5 alternating reps, warm-up chunk discarded):

| variant | median | min | max | within-variant spread | delta vs. declared-only |
|---|---|---|---|---|---|
| declared only | 8.191s | 7.974s | 8.872s | 11.0% | — |
| with undeclared column | 8.759s | 7.791s | 9.881s | 23.9% | +6.93% |
| with undeclared column, warn no-op'd | 8.404s | 8.157s | 8.897s | 8.8% | +2.60% |

**I cannot separate the cost from noise, and it is not close.** Predicted effect from Part 1:
3,000 dropped cells × 105.8 ns = **0.32 ms** against a median of 8,191 ms = **0.0039%**. The
noise floor — the within-variant spread on repeated runs of *identical* code — is 8.8%–23.9%,
i.e. **2,300×–6,200× larger than the effect being looked for**. The A/B deltas above are noise
and should not be read as measurements: the warn-disabled variant landing *between* the other two
(rather than at the bottom, where a real cost ordering would put it) is the tell. Machine noise
was elevated because a second agent was working concurrently on this host.

Two caveats that both cut in the fix's favour: sqlite in-memory is the cheapest possible per-cell
environment (~2.7 ms of real work per row here), so this is the *most* adversarial setting for the
overhead ratio — on PostgreSQL the fraction shrinks further. And the measured path is the only one
that can repeat: the cold path (first sighting) runs once per `(table, column)` per process.

---

## 4. Should the warning reach the API response?

**No — I agree with your instinct, and I would go further: not later either, not in this shape.**

1. **It is a boundary contract.** `PUT /tables/{t}/data/updates` returns a shape client2 consumes;
   adding a field is a Client PM + lead PM decision under §4 of the server charter, not a
   side-effect of a logging fix.
2. **The response is the wrong consumer.** The caller that most needs this is the *ingestion
   watcher*, which does not go through HTTP at all — it calls `crud.apply_batch_updates` directly
   in-process. A response field would miss the highest-volume, least-supervised write path
   entirely, which is exactly where a 100k-row file quietly loses a column.
3. **Per-batch aggregation is unsolved.** A batch is up to 1000 rows; the response would need a
   deduplicated per-batch column set, which means either a per-cell collection allocation (the
   cost this fix was careful to avoid) or a second mechanism.
4. **Nobody would see it.** client2 does not surface unknown response fields, so shipping it
   without matching client work buys nothing but a wider contract.

The right escalation, if this recurs, is a **startup/config-reload validation** that diffs
declared columns against what each parser/mapper is known to emit and fails loudly at load time —
a config problem caught at config time, not per write. That is a separate, larger piece of work
and I did not start it.

---

## 5. Known gaps — deliberately not fixed

**(a) `system_cols` is a second, separate silent skip.** `crud.py:566` skips
`created_at, updated_at, row_id, id, updated_by, is_graph_synced, needs_graph_rollback,
graph_synced_at` *before* the `column_types` check. Of the two columns in your incident, only
`eventtime` is covered by this fix — a payload key `updated_by` is dropped by the system_cols
guard whether or not it is declared. (I confirmed `map_doe` currently declares both `eventtime`
and `updated_by` in `column_types`, so the config side is already repaired; the declared
`updated_by` still never lands via this loop.) I did **not** extend the warning to system_cols:
that skip is deliberate and system-managed, and warning on it would fire for every normal client
write that echoes `updated_at`/`row_id`, producing exactly the noise this design avoids. Whether
a *declared* `updated_by` silently not landing is itself a bug is a real question, but it is a
different one.

**(b) The diagnostic is weaker in the watcher process than in the web server.** `crud.py` logs to
`logging.getLogger("Server")`. I probed a watcher-style process directly
(`<scratchpad>/probe_logger_reach.py`) and confirmed: after `get_process_logger("WATCHER", …)`,
`Server.handlers == []` and `root.handlers == []` (that function strips root handlers by design),
so the record falls through to `logging.lastResort` — a bare, unformatted, untagged line on
**stderr**, and it does **not** reach the watcher's log file. It is visible, but not where an
operator would grep for it.

This is a pre-existing property shared by `_warn_audit_truncation_once` and every other `logger.*`
call in `crud.py`, not something this change introduced. Fixing it means either crud adopting a
proper logger hierarchy or each process configuring the `"Server"` logger — both land in
`server/utils/logger.py`, which is currently owned by another agent. **Per your instruction I
stopped and am reporting instead.** I would rate it worth doing: the ingestion path is precisely
where a lagging config does the most damage, and that is the path where the warning is least
legible.

**(c) Pre-existing micro-inefficiency, untouched.** `col_types = config.get("column_types", {})`
sits *inside* the per-cell loop (`crud.py:602`) and allocates a fresh empty dict on every
iteration when the key is missing. Hoisting it above the loop is free and correct, but it is
outside the scope you set and I left it alone.

---

## 6. Environment / hygiene notes

- All Python via `conda run -n assy_manager`, `PYTHONIOENCODING=utf-8`.
- Untouched, as instructed: `server/paths.py`, `server/utils/logger.py`, `server/scripts/dev_env/**`,
  `server/parsers/directory_watcher.py`. My tests deliberately avoid importing `directory_watcher`
  so they do not couple to that agent's in-flight work.
- **The working tree is shared and live.** `paths.py` changed *between two of my own runs*:
  `paths.log_path` existed during the logger probe and raised `AttributeError` in a check moments
  later. The 498-pass result is therefore a measurement of the tree as it stood at that minute,
  including another agent's uncommitted changes to `paths.py`, `logger.py`, `devenv.py`,
  `directory_watcher.py`, `graph_sync_worker.py`, `test_dev_env_isolation.py`, `iso_watcher.py`.
  My contribution to the tree is exactly two paths: `server/database/crud.py` (modified) and
  `server/tests/test_undeclared_column_warning.py` (new).
- No history file written and `gen_index.py` not run: another agent is active in the same tree and
  you asked for no commit, so index regeneration would collide. History draft below for lead-PM
  integration.

### History draft (`docs/history/YYYYMMDD_HHMMSS_undeclared_column_warning.md`)

> **Symptom** — A column present in an update payload but absent from `table_config.json`
> `column_types` was discarded in `apply_row_update_internal`, with no log and a 200 response;
> `map_doe`/`map_doe_source` lost `eventtime` this way and it surfaced only via a manual
> config-vs-code audit.
> **Root cause** — The drop branch was a bare `continue`.
> **Fix** — Warn once per `(table, column)` per process at the drop site, allocation-free on the
> already-warned path, with a 64-entry per-table budget because column names originate in the
> payload. Drop behaviour unchanged: rejecting the write would convert a lagging config into an
> outage.
> **Verification** — 4 tests incl. real-path HTTP 200 + declared columns persisted; 500-row batch
> yields 1 line; two defect injections fail disjoint test subsets. Overhead 105.8 ns per dropped
> cell, ~2,300×–6,200× below the end-to-end noise floor. Suite 498 passed.

---

## 7. Proposed lessons (for lead-PM review before landing in `agent_workspace/memory/server-pm.md`)

- **함정**: 페이로드에 있으나 `column_types`에 없는 컬럼은 `apply_row_update_internal`에서
  로그 없이 버려지고 응답은 200이라, 설정이 클라이언트보다 뒤처진 사이트는 저장이 성공한 것처럼
  보이면서 필드를 잃는다. 감사로만 발견되는 무결성 채널이다.
  **올바른 방법**: 드롭 지점에 `(테이블, 컬럼)`당 1회 경고를 둔다. 셀 단위 핫패스이므로 **이미
  경고한 경로는 무할당**이어야 한다 — 튜플 키 대신 테이블별 set을 조회하고, f-string은 조기
  반환 뒤에 만든다. 드롭 자체를 예외로 바꾸지 말 것(설정 지연이 곧 장애가 된다).
- **함정**: warn-once 계열 레지스트리의 키가 **페이로드에서 온다면 스키마 크기로 한정되지 않는다**
  (깨진 헤더 행·값을 헤더로 뱉는 파서). 무한 증가 + 로그 폭주.
  **올바른 방법**: 테이블별 예산을 두고 포화 시 성장·경고를 함께 멈추되, **침묵으로의 전환을 1회
  명시적으로 알린다**. 조용히 조용해지지 말 것.
- **함정**: `crud.py`는 `getLogger("Server")`로 로깅하는데, 워처/체인 프로세스는
  `get_process_logger`가 **root 핸들러를 제거**하므로 `Server` 로거에 핸들러가 없다 →
  `logging.lastResort`로 떨어져 **평문 stderr 한 줄**이 되고 해당 프로세스 로그 파일에는 남지
  않는다. 인제션 경로가 가장 위험한데 경고는 거기서 가장 안 보인다.
  **올바른 방법**: crud에 진단 로그를 추가할 때 "이 프로세스에서 이 로거가 핸들러를 갖는가"를
  실측으로 확인하라(웹서버에서만 확인하면 착시).
- **함정**: 핫패스 오버헤드를 end-to-end A/B로만 측정하면 결론이 안 난다 — 노이즈가 효과의
  수천 배면 어떤 델타가 나와도 의미가 없고, 자칫 노이즈를 측정값으로 보고하게 된다.
  **올바른 방법**: `timeit` 격리 측정으로 **효과 크기를 먼저 산출**하고, end-to-end의 **동일
  변종 반복 산포(노이즈 바닥)**와 비율로 비교하라. 분리 불가면 "분리 불가"가 정답이다.
