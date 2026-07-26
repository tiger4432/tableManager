# B1 + B2 — process supervision and a real health endpoint

- Executed by: server-pm · 2026-07-27 05:55–06:35 KST
- Base commit: `08d2b12` (suite measured green there before any edit: **498 passed**)
- Environment: **isolated only** — a private data root `dev_env/sup_root`, API `127.0.0.1:8085`,
  graph `:8095`, database `assy_qa`. Production (`:8080`, `server/config`, `assy_manager`) was
  never written to; §9 proves it.
- **Nothing committed.**

## Verdict

| | result | the number that decides it |
|---|---|---|
| **B1** supervision | **done** | each of 5 children killed individually: detected in **0.21–0.81 s**, restarted, recorded |
| **B1** restart storms | **done** | backoff **2/4/8/16/32 s**, cap at 6 consecutive failures, then **0 further spawns in 90 s** |
| **B2** health route | **done** | `/health` → JSON; bogus path → HTML. Non-200 measured in 3 distinct failure modes |
| **B2** progress-based | **done** | a **suspended but alive** worker → **503 at 58.7 s**; supervisor still said `running`, restarts still 0 |
| clean shutdown | **done** | 5 descendants → **0 orphans**; production and a third stack unaffected |
| injected defects | **done** | 4 defects injected, **all 4 caught**; sources byte-identical after restore |
| suite | **540 passed / 0 failed** | baseline 498 + **42** new |

Two defects were found by drilling rather than by design, and both are fixed: a stray same-role
process could mask a wedged worker (§5.1), and `stop_all()` orphaned grandchildren (§7.2).

---

## 1. The premise, verified before building anything

`/health` was not a route, so it fell through the SPA catch-all at `server/main.py:3945`.
Measured against the isolated server running the unmodified code:

```
/health                                -> 200  json=False  ctype=text/html  '<!doctype html> <html lang="ko"...'
/healthz                               -> 200  json=False  ctype=text/html  '<!doctype html> <html lang="ko"...'
/definitely-not-a-real-path-9c41ab7e   -> 200  json=False  ctype=text/html  '<!doctype html> <html lang="ko"...'
/tables                                -> 200  json=True   ctype=application/json
```

An external monitor pointed at `/health` would have called this server alive in every state it
could possibly be in. That is B2's whole justification, and it is my own measurement, not a claim
inherited from the checklist.

---

## 2. B1 — the supervisor

`run_decoupled_app.py` no longer ends in `while True: time.sleep(1)`. The policy lives in
`server/process_supervisor.py` (a library, so it is testable without spawning anything) and the
launcher supplies the child list.

### 2.1 Restart policy

```
child exits (and we are not shutting down)
  ├─ was it up >= HEALTHY_UPTIME_SEC (60 s)?  -> consecutive := 1     (not a crash loop)
  └─ otherwise                                -> consecutive += 1
  ├─ consecutive > MAX_CONSECUTIVE_FAILURES (5) -> FAILED, never respawned, loud banner
  └─ otherwise -> BACKOFF for min(2 * 2**(n-1), 60) s, then respawn
```

Three decisions worth defending:

- **`HEALTHY_UPTIME_SEC` exists so the budget cannot leak away.** Without it, a system running for
  months would accumulate five unrelated one-off deaths and then refuse to restart anything. A child
  that ran an hour before dying is not in a crash loop.
- **A `spawn()` that raises is treated as a failure, not an exception.** A bad interpreter path or a
  missing script would otherwise take down the launcher itself, or spin.
- **A permanently failed child does not stop the system.** The other four children keep running
  (measured, §4.3). Killing everything because one child is broken is the opposite of
  near-continuous operation. The failure is surfaced through `/health` instead.

### 2.2 Why auto-restarting a mid-ingestion watcher is safe

This design depends on P2's checkpoint resume holding, so I read the evidence rather than assuming
it: under a real `taskkill /F` at 30,000 of 100,000 rows the committed offset matched the actual row
count **exactly**, the resume skipped the completed rows in **275 ms**, and a `generate_series`
anti-join found zero missing keys and zero duplicates
(`agent_workspace/reports/QA_p2_drills_isolated.md` §2). Without that, auto-restart would be a data
integrity feature, not an availability one.

### 2.3 Failure modes of the supervisor itself

| mode | what happens | covered? |
|---|---|---|
| supervisor restarts a child we are deliberately stopping | `stop_all()` sets `_stopping` **before** the first `terminate()` | yes — unit test |
| child dies during backoff window | state stays `backoff`, timer unaffected | yes |
| status file write fails | logged, supervision continues (monitoring must not break the thing it monitors) | yes |
| event log grows unbounded | ring capped at `MAX_EVENTS = 100` | yes — unit test |
| launcher process itself dies | **not covered** — nothing supervises the supervisor; `/health` reports it (§3.3) | see §8 |

---

## 3. B2 — the health contract

`GET /health` → `application/json`, `Cache-Control: no-store`.

```jsonc
{
  "status": "ok" | "degraded" | "unhealthy",     // 200      200      503
  "checked_at": "2026-07-27T06:22:09.813274+09:00",
  "problems": ["human-readable, empty when ok"],
  "checks": {
    "database":   {"status": "ok|timeout|down", "latency_ms": 1.6},
    "workers":    {"<name>": {"status": "ok|starting|wedged|down|missing|foreign_beat|stale",
                              "supervisor_state": "running", "pid": 30084,
                              "age_seconds": 0.76, "beats": 63, "restarts": 0,
                              "stale_after_seconds": 60.0}},
    "outbox":     {"status": "...", "pending": 0, "pending_capped": false,
                   "oldest_age_seconds": null, "count_cap": 10000},
    "supervisor": {"status": "ok|stale|absent|failed_children",
                   "updated_age_seconds": 1.2, "failed_children": [], "children": {...}}
  }
}
```

`degraded` returns 200 deliberately: the system is still serving, and an operator dashboard should
show amber rather than page. Everything that means *data has stopped flowing* is `unhealthy`/503.

### 3.1 The per-worker signal is progress, not existence

Each worker calls `heartbeat.beat(name)` **from inside its own work loop**:

| worker | beat site | loop period |
|---|---|---|
| watcher | `server/run_watcher.py` — top of the retry-poller loop | 3 s |
| chain | `server/chain_ingestion_worker.py` — top of `while True` | 2 s (LISTEN timeout) |
| graph | `server/graph_sync_worker.py` — top of the materializer loop | 2 s (LISTEN timeout) |
| scheduler | `server/run_auto_update.py` — top of `while True` | 5 s |

A beat is a ~200 byte atomic file replace under `<DATA_ROOT>/config/worker_heartbeats/`, throttled
to at most one per second. This reuses the `scheduler_status.json` pattern rather than inventing a
third mechanism, and it buys two things: `ASSY_DATA_ROOT` relocates it for free (so an isolated
stack cannot overwrite production's beats), and it **does not depend on the database** — a heartbeat
stored in PostgreSQL would go stale for every worker at once during a database outage, conflating
"database down" with "workers wedged". Those are separate rows in `/health` precisely so they can be
told apart.

The supervisor's process view is joined to the beat, because the two facts have different owners and
need different responses:

```
supervisor: not running                     -> down          (B1 restarts it)
supervisor: running + beat stale            -> wedged        (alive, not progressing)
supervisor: running + beat from another pid -> foreign_beat  (§5.1)
supervisor: running + no beat yet, young    -> starting      (grace; 503 on every boot would train
                                                              the operator to ignore this endpoint)
```

### 3.2 The staleness threshold: 60 s, and why

`DEFAULT_STALE_AFTER_SEC = 60.0`. Two constraints bound it.

**Lower bound — one missed beat must never trip an alarm.** A GC pause, a slow disk, or a busy
database will occasionally cost a beat, and a health check that cries wolf gets muted, which is
worse than not having one. 60 s is ≥ 12 consecutive missed beats for the slowest loop (the 5 s
scheduler) and 20–30 for the others.

**Empirically**, measured over 150 s against the live isolated stack — the interval between actual
changes in each worker's beat counter:

| worker | intervals | min | p50 | p95 | max | headroom (60 s ÷ max) |
|---|---|---|---|---|---|---|
| chain | 62 | 0.26 | **2.04** | 4.14 | 10.26 | **5.8×** |
| graph | 75 | 0.54 | **2.04** | 2.06 | 2.08 | 28.8× |
| scheduler | 30 | 3.35 | **5.11** | 5.16 | 5.18 | 11.6× |
| watcher | 49 | 1.06 | **3.07** | 3.09 | 5.88 | 10.2× |

Every p50 lands on its designed loop period, so the beats are coming from the loops and not from
some incidental timer. The chain worker's 10.26 s outlier is the tightest case and still leaves
5.8× headroom.

**Upper bound — how long data may silently stop flowing before someone finds out.** 60 s is well
inside "near-continuous operation" for a 2–5 person intranet, and `/health` also publishes the raw
`age_seconds` per worker, so a monitor may alarm earlier on its own without changing the server.

### 3.3 The database probe cannot hang

The route is `async def`; the probe runs via `asyncio.to_thread` under `wait_for(timeout=2.0)`. A
timeout frees the request but not the thread, so a module-level in-flight flag — cleared by the
thread that owns it, not by the request that gave up — caps hung probes at **one**, no matter how
often a monitor polls. A timed-out probe reports `degraded`, not silence.

### 3.4 Outbox backlog is measured by **age**, not size

The obvious check is wrong here. A single legitimate 100,000-row ingestion creates ~116,000 outbox
rows (P2 drill, §6.4 of that report), so any size threshold low enough to catch a stuck chain worker
fires on every large file. What separates *busy* from *stuck* is whether the queue drains: if the
chain worker is keeping up, the oldest unprocessed row stays young no matter how many are behind it.

- `oldest_age_seconds > 300` → degraded, `> 900` → unhealthy.
- `pending` is reported for context, counted under `LIMIT 10001` so the query cost cannot grow with
  the table.

Measured against `assy_qa` with a deliberately 40-minute-old unprocessed event seeded (§6):

```
probe_outbox() -> {'oldest_age_seconds': 2400.03, 'pending': 1, 'pending_capped': False, ...}
compute_health -> HTTP 503, status=unhealthy
  problems: ['outbox backlog is not draining: oldest unprocessed event is 2400s old']
```

Both queries ride the partial index `idx_outbox_unprocessed`:

```
[oldest unprocessed event]
  Limit (actual time=0.017..0.017 rows=1)  Buffers: shared hit=2
    ->  Index Scan using idx_outbox_unprocessed on database_outbox
  Execution Time: 0.029 ms

[capped backlog count]
  Aggregate (actual time=0.010..0.010)  Buffers: shared hit=3
    ->  Limit  ->  Index Only Scan using idx_outbox_unprocessed
  Execution Time: 0.023 ms
```

Index scan, 2–3 buffer hits, no sequential scan — the work is proportional to the *backlog*, not to
the table, which is what makes this safe to poll continuously against a table allowed to reach
10,000,000 rows. Caveat in §8.9: `assy_qa.database_outbox` held 225 rows, so this proves the plan
*shape*, not behaviour at scale.

---

## 4. Proofs

All drills ran the **real** `run_decoupled_app.py --server-only`, not a reimplementation of it —
`ASSY_API_PORT` (new, defaults to 8080) let the production launcher be pointed at the isolated stack.

### 4.1 PROOF 1 + 3 — kill each child individually

`taskkill /F` (a hard kill, not a polite signal) on every child in turn:

| child | detect | restart | `/health` while down | recover | restarts |
|---|---|---|---|---|---|
| File Ingestion Watcher | 0.81 s | 2.02 s | **503** `worker 'watcher' is down` | 0.05 s | 1 |
| Chained Ingestion Worker | 0.42 s | 2.02 s | **503** `worker 'chain' is down` | 0.06 s | 1 |
| Graph DB Sync Worker | 0.21 s | 2.02 s | **503** `worker 'graph' is down` | 0.05 s | 1 |
| Auto Update Scheduler | 0.21 s | 2.02 s | **503** `worker 'scheduler' is down` | 0.05 s | 1 |
| Backend FastAPI Server | 0.41 s | 2.0 s backoff | connection refused (it *is* the endpoint) | 2.12 s | 1 |

Each restart came back under a **new pid**, verified alive from the OS, and each is recorded where an
operator can find it:

```json
{"ts": ..., "child": "File Ingestion Watcher", "event": "exited", "exit_code": 1,
 "uptime_seconds": 223.33, "consecutive_failures": 1}
{"ts": ..., "child": "File Ingestion Watcher", "event": "restart_scheduled", "delay_seconds": 2.0, "attempt": 1}
{"ts": ..., "child": "File Ingestion Watcher", "event": "started", "pid": 40432}
```

### 4.2 PROOF 2 — crash on startup, repeatedly

Cause taken from the real list: **the port is already taken**. The drill held `:8095` itself, so
`run_graph_sync.py`'s uvicorn could not bind and the process exited *every* time.

```
      t     state  attempt  restarts  backoff  exit
    0.0   running        0         0     None  None
    2.8   backoff        1         1      2.0     1
    7.8   backoff        2         2      4.0     1
   14.9   backoff        3         3      8.0     1
   25.9   backoff        4         4     16.0     1
   44.8   backoff        5         5     32.0     1
   80.0    failed        6         5     None     1

backoff schedule used: [2.0, 4.0, 8.0, 16.0, 32.0]
reason: exited 6 times in a row (last exit code 1) without staying up 60s
```

Loud:

```
[Launcher] ERROR - ====================================================================
[Launcher] ERROR - CHILD PERMANENTLY FAILED: Graph DB Sync Worker
[Launcher] ERROR -   Giving up - this child will NOT be restarted again.
[Launcher] ERROR -   /health now reports unhealthy until it is fixed and the launcher restarted.
[Launcher] ERROR - ====================================================================
```

And it **stays** failed. Observed for a further 90 s: `state=failed` throughout, `restarts` stayed
5, and the count of `started` events stayed at **6 → 6**. A spin would have shown as either climbing.

```
/health -> 503 (application/json) status=unhealthy
problems: [
  "child 'Graph DB Sync Worker' permanently failed: exited 6 times in a row ...",
  "worker 'graph' is down (supervisor state: failed)"
]
```

### 4.3 One broken child does not take the system down

```
Backend FastAPI Server     state=running   restarts=0
File Ingestion Watcher     state=running   restarts=0
Graph DB Sync Worker       state=failed    restarts=5
Chained Ingestion Worker   state=running   restarts=0
Auto Update Scheduler      state=running   restarts=0
```

### 4.4 PROOF 4 — alive but wedged (the case that matters)

`psutil.suspend()` → `NtSuspendProcess`: every thread stops while the process object stays in the OS
process table. Target: the watcher.

```
 elapsed  tasklist     psutil  sup.state  restarts   beats   hb_age  http   verdict
     0.0      True    running    running         0       5      2.7   200        ok
    16.7      True    running    running         0       5     19.5   200        ok
    42.0      True    running    running         0       5     44.7   200        ok
    58.7      True    running    running         0       5     61.4   503    wedged
    75.5      True    running    running         0       5     78.2   503    wedged

problems: ["worker 'watcher' has made no progress for 78.22s (threshold 60s)
            although its process is alive"]
```

The three columns that make this the wedged case and not something else:

- `tasklist` said **True** in all 10 samples — the process was there the whole time.
- **`psutil.status()` itself returned `running`** while suspended. Windows does not distinguish it.
  An existence check — any existence check — sees nothing wrong here.
- The supervisor said `running` with `restarts=0` throughout. A pid-based supervisor would have
  taken no action, correctly by its own logic.

Only the beat noticed: frozen at **5** for the entire 78 s.

On resume, `/health` returned to 200/ok in **0.03 s**, beats advanced 5 → 6, **same pid**,
`restarts` still 0 — the process was never replaced, so the recovery is the worker resuming
progress, not a restart papering over it.

### 4.5 PROOF 5 — clean shutdown, no orphans

Ctrl+Break (what Windows delivers for a console stop; the launcher now registers `SIGBREAK`
alongside `SIGINT`/`SIGTERM`, without which the graceful path was simply unreachable for that key).

```
descendants BEFORE shutdown: 5   (chain, watcher, uvicorn:8085, auto_update, graph)
  supervised pids not in OS tree: none
  OS tree pids not supervised   : none
launcher exited after 0.88s
ORPHAN CHECK - of 5 descendants, still alive: 0
[Launcher] WARNING - Signal 21 received. Cleaning up all background processes...
 AssyManager has stopped cleanly.
```

Scoped strictly to this launcher's tree, because the machine was simultaneously running the user's
production stack and a third stack from another agent — a global "count python processes" check
would have been meaningless. Both bystanders were unaffected:

```
pid=1840   ppid=44024  .\run_decoupled_app.py --server-only        <- user's production launcher
pid=43636  ppid=1840   -m uvicorn main:app --port 8080             <- production web server
pid=49488  ppid=44360  -m uvicorn main:app --port 8081             <- the other agent's stack
```

### 4.6 PROOF 6 — routed, not shadowed

```
/health                                -> 200  application/json   {"status":"ok",...}
/healthz                               -> 200  text/html          <!doctype html> ...
/definitely-not-a-real-path-9c41ab7e   -> 200  text/html          <!doctype html> ...
```

The bogus path still returns HTML, which is the control: it proves the catch-all is active, so
`/health` returning JSON means it is genuinely routed above it rather than the catch-all having been
disabled. `test_health_is_json_while_a_bogus_path_is_still_html` asserts both halves, so a future
reorder that re-shadows the route fails the suite instead of failing silently in production.

---

## 5. Two defects found by drilling, not by design

### 5.1 A stray same-role process masked a wedged worker

The first wedge attempt **failed to detect anything**: the chain worker was suspended for 92 s and
`/health` reported `ok` the whole time, because its `beats` counter kept climbing — 36 → 150 → 197.

The cause was another agent running `devenv up` against the same `dev_env/` data root. Their chain
worker (pid 48780) was writing the same `chain.json` as my supervised one (pid 34944). Heartbeat
files are keyed by **role**, so a healthy stray masked the wedged real one.

That is not a test-environment artifact; it is a production hole. Two ways it bites:

- someone starts `run_watcher.py` by hand to debug while the supervised watcher is wedged;
- **worse**: right after a restart, the *dead predecessor's* beat is still fresh, so a replacement
  that crashes before reaching its loop looks healthy for a whole 60 s window.

**Fix**: a beat only counts if the pid that wrote it is the pid the supervisor started. A mismatch
is treated as no beat at all (→ `starting` inside the grace window, `foreign_beat` after it). Four
tests, including a matching-pid control so the failures are attributable to the mismatch and nothing
else.

The re-run, against a worker the other agent does not run, is §4.4.

### 5.2 `stop_all()` orphaned grandchildren

Measured with the real `Supervisor` driving real processes that each spawn a subprocess:

```
before fix: survivors after stop_all(): 2 of 4   ORPHAN GRANDCHILD pid=44124 / pid=48620
after  fix: survivors after stop_all(): 0 of 4
```

`terminate()` on Windows is `TerminateProcess`, which does not walk the tree, so a child that exits
*cleanly* still leaves its own subprocesses behind. This is not hypothetical: `run_auto_update.py`
runs collector scripts as subprocesses, so stopping the launcher while a collector is mid-run is
exactly this shape. The Ctrl+Break drill could not have found it — a console event reaches every
process in the group, so everything dies whether `stop_all()` works or not.

**Fix**: capture the subtree *before* terminating (once the parent exits the link back to it is
gone), terminate gracefully, then kill any captured descendant still alive. Guarded by a real-process
regression test.

---

## 6. Injected-defect run (required)

Four defects, each aimed at one claim. Edits and reverts done in **bytes** from a copy taken first,
then verified by sha256 — a text-mode rewrite would silently convert line endings while `git diff`
stayed clean.

```
BASELINE   test_process_supervisor.py  rc=0  14 passed
           test_health_endpoint.py     rc=0  28 passed

D-A  restart disabled          -> rc=1  7 failed   (dead_child_is_detected_restarted_and_recorded,
                                                    backoff_grows, backoff_is_capped, crash_loop_hits_the_cap,
                                                    spawn_that_raises, healthy_uptime_resets, short_uptime)
D-B  backoff removed           -> rc=1  2 failed   (backoff_grows_between_attempts, backoff_is_capped)
D-D  grandchild cleanup removed-> rc=1  1 failed   (stop_all_leaves_no_orphans_including_grandchildren)
D-C  existence-based check     -> rc=1  2 failed   (worker_alive_but_wedged_is_unhealthy,
                                                    no_supervisor_still_flags_a_stale_beat)

VERDICT: CAUGHT × 4

final byte check:
  process_supervisor.py  sha=47d2333acfbb51e5  pristine=47d2333acfbb51e5  identical=True
  health.py              sha=a9a6858040b2ac8b  pristine=a9a6858040b2ac8b  identical=True
```

D-C is the load-bearing one: replacing the progress check with an existence check makes exactly the
wedged-worker test fail, which is the difference between this endpoint meeting the hard requirement
and not.

---

## 7. Files

| file | change |
|---|---|
| `run_decoupled_app.py` | supervisor replaces `while True: sleep(1)`; child specs carry `heartbeat=`; `SIGBREAK`; `ASSY_API_PORT` override |
| `server/process_supervisor.py` | **new** (431) — restart policy, status file, shutdown |
| `server/health.py` | **new** (280) — decision table (pure), `probe_outbox` |
| `server/utils/heartbeat.py` | **new** (174) — `beat()` / `read_all()` |
| `server/main.py` | `+77` — `/health` route above the catch-all, bounded DB probe |
| `server/run_watcher.py` | `+8` — beat in the retry-poller loop |
| `server/chain_ingestion_worker.py` | `+6` — beat at the top of the work loop |
| `server/graph_sync_worker.py` | `+4` — beat at the top of the materializer loop |
| `server/run_auto_update.py` | `+4` — beat at the top of the scheduler loop |
| `server/tests/test_process_supervisor.py` | **new** (375) — 14 tests |
| `server/tests/test_health_endpoint.py` | **new** (349) — 28 tests |

No boundary contract changed: no REST signature, no WS event, no cell shape, no schema contract.
`/health` is a new path only.

**Suite: 540 passed / 0 failed** (63.5 s), against a measured baseline of **498** at `08d2b12`.

---

## 8. What this does not cover

1. **The watcher's beat comes from its retry-poller thread, not from the ingestion path.** A
   deadlock confined to the observer or heavy-lane threads, while the poller keeps polling, would
   not be caught. Beating from the ingestion path would mean editing
   `server/parsers/directory_watcher.py`, which another agent owns this session.
2. **Same loop, the false-positive direction**: the poller takes the workspace serial lock when a
   `PENDING_RETRY` log exists. If that lock is held by a long heavy-lane ingestion (the P2 drill saw
   a 28-minute file), the watcher would be reported `wedged` while working correctly. It errs toward
   alarming rather than toward silence, but it is a false alarm.
3. **The web server's own event loop is not heartbeated.** The actual production incident was a
   freeze of *this* loop; if it freezes, `/health` does not answer at all and the monitor's timeout
   catches it — but `/health` cannot report "I froze for 40 s and recovered". There is no post-hoc
   record of a transient freeze.
4. **Restart budgets are per-child and do not know about systemic causes.** If PostgreSQL goes down,
   every worker fails at once, each burns its own budget, and ~80 s later all of them are
   permanently failed — requiring a manual launcher restart even after the database returns. That is
   the deliberate consequence of "fail loudly and stay failed", but it is a real operational edge.
5. **Nothing supervises the supervisor.** `/health` reports `supervisor: stale` if the launcher dies,
   but cannot restart it. No Windows service wrapper / auto-start.
6. **`/health` is unauthenticated** and exposes pids, worker names and restart counts. Consistent
   with the rest of the system (blocker C1), but it is new surface.
7. **Heartbeat ages use wall-clock across processes**, because `time.monotonic()` is not comparable
   between processes. An NTP step could produce a spurious stale or fresh reading.
8. **`psutil` is not a declared project dependency** (there is no `requirements.txt`). It is present
   in the `assy_manager` conda env, and grandchild cleanup degrades to a no-op without it — silently.
   Worth declaring.
9. **Query plans were proven on 225 rows.** The plan *shape* (index scan on the partial index, no
   sequential scan) is what generalises; behaviour at 10,000,000 rows is reasoned, not measured.
10. **No drill ran under a real large ingestion.** The chain worker's worst observed beat gap was
    10.26 s on a mostly idle stack; under a 100k-row heavy-lane ingestion it could be longer, which
    would eat into the 5.8× headroom. Re-measuring the beat cadence during a heavy ingestion is the
    single most useful follow-up.
11. **The loud banner is `print()` to stdout.** The durable record is `supervisor_status.json` and
    `/health`, but if the user runs the launcher detached with stdout discarded, the ERROR banner is
    lost. This is coupled to blocker **B3** (`server/utils/logger.py`, owned by another agent this
    session) — see §10.
12. `--reload` mode is untested under supervision; uvicorn's reloader spawns its own child, so the
    supervisor would be watching the reloader rather than the server.

---

## 9. Production untouched

```
server/config/worker_heartbeats/        exists: False   <- production never ran this code
server/config/supervisor_status.json    exists: False

production stack, same pids as at session start, all ppid=1840:
  1840  run_decoupled_app.py --server-only     47780  run_chain_worker.py
 43636  uvicorn main:app --port 8080           42036  run_auto_update.py
 50156  run_watcher.py                         46588  run_graph_sync.py
```

The absence of `worker_heartbeats/` and `supervisor_status.json` under `server/config/` is the
strongest single line here: both are created on first use, so their absence proves no process
carrying this code ever resolved its paths to the production root.

`server/config/scheduler_status.json` did change (mtime 1785101522) — that is the **live scheduler's
own cron**, and it is the sensitivity control: it shows the instrument was awake, so the flat
readings on `table_config.json`, `chain_rules.json` and `auto_update_control.json` mean "never
opened", not "instrument dead".

Drill cleanup: `dev_env/sup_root` removed, seeded outbox row deleted (residual 0), the isolated
`auto_update_control.json` restored, 0 drill processes left running.

---

## 10. Coupling and coordination

- **`server/graph_sync_worker.py`** is also being edited by the other agent (their change is at
  line ~274, `VIRTUAL_GRAPH_PATH`; mine is at ~617, the materializer loop). Their edit landed in a
  commit mid-session and did not conflict, but the file has two authors right now.
- **`server/utils/logger.py` was not touched**, per instruction. §8.11 is the coupling: the
  launcher's restart banners go to stdout via `print()`, and B3's fix is what would make them land
  in a file. The durable record (`supervisor_status.json` + `/health`) does not depend on it.
- **The isolated environment is a single shared slot.** Two agents ran `devenv up` against the same
  `dev_env/` and `assy_qa` simultaneously; that is what produced §5.1. I worked around it with a
  private root under `dev_env/sup_root` and ports 8085/8095. `devenv` would benefit from either a
  named-instance concept or a lock.

---

## 11. Proposed lessons (for review — not applied)

**server-pm section:**

> - **함정**: 헬스/하트비트를 **역할 이름으로만 키잉**하면, 같은 역할의 다른 프로세스(수동 기동, 동시
>   실행 중인 격리 스택, **재시작 직전에 죽은 이전 프로세스**)가 남긴 신선한 비트가 실제로 멈춘
>   워커를 가린다. 2026-07-27 실측: 체인 워커를 92초간 suspend했는데 `beats`가 36→197로 계속 올라
>   `/health`가 내내 `ok`를 반환했다(다른 에이전트의 `devenv up`이 같은 `chain.json`을 썼다).
>   **올바른 방법**: 비트는 **감독자가 띄운 pid가 쓴 것만 유효**로 취급한다. pid 불일치는 "비트 없음"과
>   동일하게 처리하고, 재시작 직후 유예창 안에서만 degraded로 낮춘다.
> - **함정**: Windows에서 `Popen.terminate()`는 `TerminateProcess`라 **트리를 타지 않는다**. 자식이
>   정상 종료해도 그 자식의 서브프로세스는 살아남는다(실측: 2/2 손자 고아). 콘솔 Ctrl+Break 드릴은
>   그룹 전체에 이벤트가 가므로 **이 결함을 절대 발견하지 못한다**.
>   **올바른 방법**: 종료 전에 `psutil`로 하위 트리 pid를 **먼저 수집**하고(부모가 죽으면 역참조 불가),
>   graceful terminate 후 생존자를 정리한다. 고아 검증은 반드시 `stop_all()` 단독 경로로 한다.
> - **함정**: outbox 적체를 **건수**로 판정하면 대형 인제션 1건이 정상적으로 11.6만 행을 만들어
>   상시 오경보가 된다.
>   **올바른 방법**: **가장 오래된 미처리 행의 나이**로 판정한다(바쁨 vs 막힘의 구분). 나이 질의는
>   `ORDER BY id LIMIT 1`로 부분 인덱스를 타 O(1)이고, 건수는 `LIMIT cap`으로 상한을 건다.
> - **함정**: 프로세스 감시의 staleness 임계값을 근거 없이 정하면, 한 번의 GC 정지에도 경보가 울려
>   결국 무시당한다.
>   **올바른 방법**: 임계값은 **실측 비트 간격 분포**(p50/max)로 정당화하고, 최저 조건은 "연속 10회
>   이상 누락"으로 잡는다. `/health`에 raw `age_seconds`도 함께 실어 모니터가 자체 임계를 쓰게 한다.

**Shared section:**

> - **함정**: 격리 환경(`dev_env/`)은 **단일 슬롯**이다. 두 에이전트가 동시에 `devenv up`을 하면 같은
>   데이터 루트·같은 DB·같은 포트를 공유해 서로의 측정을 오염시킨다(2026-07-27: 상대 스택의 워커가
>   내 하트비트 파일을 갱신해 wedge 드릴이 무효화됨).
>   **올바른 방법**: 착수 시 `dev_env/pids.json`과 `netstat` LISTENING으로 **선점 여부를 먼저 확인**하고,
>   점유 중이면 `dev_env/` 하위에 전용 루트(+전용 포트)를 만들어 쓴다.
> - **함정**: Windows에서 `os.kill(pid, CTRL_BREAK_EVENT)`는 **콘솔을 공유하지 않으면 WinError 87**로
>   실패하고, `FreeConsole()`/`AttachConsole()`을 쓰면 그 뒤로 **자기 프로세스의 subprocess 호출이
>   WinError 6**으로 깨진다(`tasklist` 등).
>   **올바른 방법**: 대상 콘솔에 attach해 `GenerateConsoleCtrlEvent`를 쓰되, attach 이후의 생존 확인은
>   `subprocess`가 아니라 `psutil`로만 한다.

---

## 12. Handover

**Changed** — `run_decoupled_app.py`, `server/main.py`, and one beat line each in the four worker
loops; three new modules and two new test files (§7). Nothing committed. No boundary contract
touched.

**Verified** — 6/6 proofs with the failure actually induced in each; 4/4 injected defects caught;
suite 498 → **540 passed / 0 failed**; production byte-identical with a live sensitivity control.

**Open / next**

1. **Re-measure the beat cadence during a heavy-lane ingestion** (§8.10). If the chain worker's beat
   gap approaches 60 s under load, the threshold needs raising or the beat needs to move inside the
   chunk loop. This is the one open question that could make `/health` wrong in production.
2. **Declare `psutil`** as a dependency (§8.8) — grandchild cleanup silently degrades without it.
3. **B3 coupling** (§8.11) — once `server/utils/logger.py` is free, route the launcher's output
   through the process logger so the permanent-failure banner is durable.
4. **Decide the systemic-failure policy** (§8.4): whether a database outage should be allowed to
   burn every child's restart budget.
5. Watcher beat placement (§8.1/§8.2) needs a follow-up once `directory_watcher.py` is free.
6. `devenv` needs a named-instance or lock (§10) so two agents cannot share one isolated slot.
7. Docs not updated (shared tree, nothing committed): `SYSTEM_OVERVIEW`, `architecture/backend.md`
   and a `docs/history/` entry for supervision + `/health` are owed once this is merged.
