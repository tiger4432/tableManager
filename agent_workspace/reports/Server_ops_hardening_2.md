# Ops hardening 2 — shared-cause failure, ingestion heartbeats, load headroom, psutil, B3

- Executed by: server-pm · 2026-07-27 07:05–09:00 KST
- Base commit: `8117456` (suite measured green there before any edit: **540 passed**)
- Environment: **isolated only**. A private data root `dev_env/ops2_root`, API `127.0.0.1:8086`,
  graph `:8096`, database `assy_qa` reached through a **killable TCP proxy on :55432**. The user's
  live PostgreSQL service was never stopped and `server/config` was never written. §10 proves it.
- **Nothing committed.**

## Verdict

| item | result | the number that decides it |
|---|---|---|
| 1 shared-cause failure | **done** | 4 children crash-looping together: spawned **8×** each (old cap 6), `failed_children` stayed `[]`, recovered **16.1 s** after the fix, no manual restart |
| 1b lone child + dead database | **done** | same scenario before/after: **`failed` at t+94.4 s** → **`retrying_correlated` at t+98.4 s**, recovered **20.1 s** after the database returned |
| 2 watcher beats from ingestion | **done** | wedged inside the parser, both lanes claimed: **503 `stalled` at t+311.9 s** while the beat was **fresh (age 1.01 s, 153 beats)** |
| 3 load headroom | **done** | worst beat gap under a live 100k ingestion **7.01 s** → **8.6× headroom**; 60 s **confirmed, unchanged** |
| 4 psutil | **done** | declared in both manifests; absent → **WARNING on stdout *and* in `launcher.log`** |
| 5 B3 log wiring | **done** | `crud.py`'s undeclared-column warning found in the **watcher's own log file** during the 100k ingestion |
| injected defects | **done** | 13 defects injected, **13 caught**; sources byte-identical after restore |
| suite | **576 passed / 0 failed** | **38** tests added by me (see the note below the table) |

**On the suite arithmetic, because it is not a clean delta.** Baseline was **540** at `8117456`.
Another agent then committed three times during this session (`cdcddee` M2.6, `d411386`, `87cbf35`),
so the base moved under me. My own contribution counted per file:
`test_process_supervisor.py` 14 → **28** (+14), `test_health_endpoint.py` 28 → **39** (+11),
`test_ingestion_heartbeat.py` **+6** (new), `test_process_logging.py` **+7** (new) = **38 added**.
540 + 38 = 578 against a final total of 576, i.e. the other agent's commits are net −2. I am not
claiming their delta as mine.

Three findings are the most important things in this report. A database outage under a *running*
stack kills **no child at all** (§1.1). The outage that does hurt kills exactly **one** (§1.2), which
a peer-only correlation rule would not have caught. And adding a heartbeat to the ingestion path made
**the test suite write into the user's live config directory** — found, fixed structurally, and
written up in §8.1 rather than buried.

---

## 1. Shared-cause failure

### 1.1 The premise was wrong, and measuring it first is what caught that

The brief (and the previous report's §8.4) says a database outage takes all five children down at
once and ~80 s later every one is permanently failed. I induced it before building anything:
a full stack under the real launcher, then the database path killed for **5 minutes**.

```
07:13:07 >>> KILLING THE DATABASE PATH <<<
07:13:07   t+   0.0s  all five: running/r0
   ... 300 s ...
07:18:07 spawn counts during outage: {Server:1, Watcher:1, Graph:1, Chain:1, Scheduler:1}
07:18:07 failed_children     = []
07:18:07 correlated_children = []
07:18:09 /health during outage -> 200 degraded   problems: ['database probe timed out']
07:18:11 >>> RESTORING <<<
07:18:56 /health after recovery -> 200 ok
```

**Zero exits. Zero restarts.** Every worker loop catches `OperationalError` and retries internally:

```
[Watcher]   ERROR - Error in retry poller loop: (psycopg2.OperationalError) ... Connection refused
[GraphSync] ERROR - [Graph] materializer loop error: (psycopg2.OperationalError) ...
[Chain]     ERROR - Error in Chain Worker execution loop: (psycopg2.OperationalError) ...
[Scheduler] WARNING - Database outbox polling failed inside scheduler: ...
```

`/health` behaved exactly as designed: **200 degraded**, database row down, worker rows still ok —
the separation between "the database is down" and "the workers are wedged" doing its job.

So the scenario as stated does not happen. Building only for it would have produced a guard for a
failure mode that does not exist.

### 1.2 The outage that does hurt kills exactly one child

The shape that does break things is a **start or restart while the database is unreachable** — a
power blip where PostgreSQL comes up slower than the app. `server/main.py:46` runs
`models.Base.metadata.create_all(bind=engine)` at import, so uvicorn cannot boot. Measured against
the peer-only rule:

```
t+ 7.0s  Backend FastAPI Server backoff/r1     (four workers: running/r0)
t+14.1s                         backoff/r2
t+23.1s                         backoff/r3
t+36.2s                         backoff/r4
t+57.2s                         backoff/r5
t+94.4s                         failed         failed=['Backend FastAPI Server']
```

**The web server permanently dead 94 s in, and it fails *alone*** — the four workers survive, so
there are no peer failures to correlate with. The UI stays down until a human restarts the launcher,
including after the database comes back. This is both the most likely real version of the incident
and the worst outcome, and a rule that counts only peer failures does not catch it.

### 1.3 The rule

Permanent failure is reserved for a child that fails **alone**, per the decision. A child has
company in either of two ways, checked only at the moment the budget runs out:

| evidence | test | why it counts |
|---|---|---|
| **peers** | another child failed within `CORRELATION_WINDOW_SEC = 120 s` | several children down at once points at what they share |
| **shared dependency** | a TCP connect to the database host:port from `DATABASE_URL` is refused | a closed port says the same thing a peer failure says: the fault is not in this child |

Either way the child enters `retrying_correlated`: a **flat 60 s** backoff, retried
**indefinitely**, never permanently failed, `/health` **unhealthy** the whole time.

Three choices worth defending:

- **Time, not exit code.** On Windows every unhandled Python exception exits 1, so an exit-code
  signature would call almost any pair of failures correlated and prove nothing.
- **120 s window.** The decision is made when a child exhausts `2+4+8+16+32 s`, i.e. ~90 s after its
  first death. Measured in the live drill, peers' most recent failures were 20–60 s old at that
  moment. 120 s covers it with room for children that die at different rates.
- **2 of 5 children.** The loosest threshold above "alone", chosen deliberately.

The second row is an **extension of the evidence beyond peer failures**, and I want it read as a
decision to review rather than something smuggled in. The delegated part was what "together" means
("a time window, a count, a shared error signature"); §1.2 is why a probe of the shared dependency
had to be one of the signatures. **If you disagree, the veto is one argument:**
`Supervisor(environment_probe=lambda: (False, None))` restores the peer-only rule and the tests for
both behaviours already exist.

### 1.4 False-positive direction

It errs toward **correlated**, i.e. toward continuing to retry, in three distinct ways:

1. two genuinely independent deaths landing within 120 s are read as a shared cause;
2. a database that is down for a reason unrelated to the child excuses a child that really is broken;
3. `CORRELATED_MIN_CHILDREN = 2` is the loosest possible peer threshold.

The cost of each is an indefinite retry loop on a broken child — loud (an ERROR banner on entry and
one ERROR line per retry), visible (`/health` 503, `supervisor_status.json`, `launcher.log`), and
self-correcting. The cost of the opposite error is a healthy system needing a human during an
outage, discovered whenever someone next looks. The first is strictly better, so the bias is
deliberate.

Two guards stop it becoming a blanket amnesty:

- **Unknown counts as healthy.** No `DATABASE_URL`, sqlite, an unparseable URL, or a probe that
  raises all mean "no evidence". The probe can only ever *add* evidence.
  (`test_unknown_environments_count_as_healthy`, `test_a_probe_that_raises_decides_nothing`)
- **Correlated is not permanent.** It is re-evaluated on every subsequent failure. Once the peers
  recover and the database answers, a child still failing on its own becomes `failed`.
  (`test_correlated_is_not_a_permanent_escape_from_the_budget`)

### 1.5 Proof — four children failing together, real processes

Induced with a **broken shared dependency**, i.e. a bad deploy: a shadowing `sqlalchemy.py` first on
`PYTHONPATH` that raises `ImportError`. Nothing was uninstalled; the conda environment is untouched
and the launcher itself is unaffected (it does not import it). The database was **healthy** for this
one, so the peer rule is what is being tested.

```
t+ 71.5s  Server, Graph, Chain -> retrying_correlated   correlated=[3 children]
t+ 72.6s  Watcher joins                                 correlated=[4 children]
t+131.8s  all four respawn, die, -> retrying_correlated (c2)
t+193.1s  ... (c3)
t+300.0s  spawn counts: Server 8, Watcher 8, Graph 8, Chain 8   <- old cap was 6
          failed_children     = []
          correlated_children = [all four]
          correlated_failure events recorded: 16
```

The `Auto Update Scheduler` stayed up throughout (it does not import sqlalchemy at start), which is
the sensitivity control: the correlation is among the children that actually failed, not "everything
goes correlated once anything does".

Recovery — the shadow file deleted, **launcher not restarted**:

```
07:35:39 >>> the cause clears <<<
07:35:55 ALL FIVE RUNNING AGAIN 16.1s later - NO MANUAL RESTART
07:35:56 settled: failed=[] correlated=[]
07:35:56 /health -> 200 ok
```

### 1.6 Proof — the lone child, before and after

The same scenario as §1.2, re-run against the finished code:

```
t+ 98.4s  Backend FastAPI Server  retrying_correlated   restarts=7  correlated_retries=2
          correlated_with = []                          <- no peer failed; this is env evidence
          evidence = the database at 127.0.0.1:55432 is not accepting connections (TimeoutError)
          failed_children = []      spawn count = 7     <- past the 6-attempt cap
>>> DATABASE COMES UP (nothing else touched) <<<
          all children running 20.1s later - NO MANUAL RESTART
          /health -> 200 ok
```

`failed` at t+94.4 s → `retrying_correlated` at t+98.4 s, same induced condition, same drill script
shape. That before/after pair is the strongest evidence in this report.

---

## 2. The watcher now beats from the ingestion path

### 2.1 Why the beat did not simply move

The watcher's beat came from its 3 s retry-poller thread, so a watcher wedged **inside ingestion**
kept beating and `/health` said ok. Moving the beat into the ingestion path would only move the
hole: ingestion is idle most of the time, so an ingestion-only beat is stale most of the time and
says nothing.

So the two facts are separated. The ingestion path opens a **work claim** around each file and
refreshes it as it progresses; the claim's age is published *inside whatever beat is written next,
by whichever thread writes it*. The poller therefore stops being able to mask a wedged ingestion and
becomes **the thing that reports it**: it is alive, so it beats, and its beat carries "a file has
been claimed for 400 s with no progress".

```
supervisor: running + beat fresh + claim advancing        -> ok
supervisor: running + beat fresh + claim not advancing    -> stalled   (503)   <- new
supervisor: running + beat stale                          -> wedged    (503)
supervisor: not running                                   -> down      (503)
```

Claims are **thread-affine**: a beat only refreshes claims opened on its own thread, so a healthy
heavy-lane job cannot refresh a wedged inline job's claim. Both lanes are covered by one claim site
(`process_with_retry`, which both funnel through) plus a second on the retry path
(`process_archived_file_sync`, which runs on the poller thread — the very thread that would
otherwise keep beating).

Beats are emitted at every stage the watcher controls: file hashed, file parsed, **every committed
chunk**, and claim open/close.

### 2.2 The stall threshold, and why it is not 60 s

`DEFAULT_STALL_AFTER_SEC = 300.0`, deliberately much larger than the 60 s beat staleness, because
the two numbers bound different things. A missed beat means a 2–5 s loop did not run. A missed claim
progress means a chunk of real work did not finish, and chunks are not uniform.

The floor is set by the part that **cannot** be instrumented: a custom pipeline parser is a user
script that reads a whole file in one opaque call and reports nothing. 300 s clears every measured
case by a wide margin (§4) and still surfaces a genuinely wedged ingestion inside five minutes.

**False-positive direction: toward silence.** This fires a 503 on an operator dashboard, and a
health check that cries wolf during exactly the operation people care about gets muted — which costs
more than five minutes of detection delay. The trade is stated so it can be revisited if 5 minutes
turns out to be too long for the team.

### 2.3 Proof — wedged inside ingestion, poller still healthy

The wedge is a **custom pipeline parser that blocks in `parse()`** — the real shape of the failure
(a user script on a hung network call or a lock), and one that wedges *only* the ingestion path: the
poller thread, the observer thread and the web server all keep running. Two files dropped at once so
both lanes are covered:

```
ophard_wedge_h  11,554,012 B -> HEAVY lane (its own worker thread)
ophard_wedge_n     106,012 B -> normal, inline on the observer dispatch thread
```

```
 t+   0.0s  http=200 worker=ok  beats=1    beat_age=0.38  claims=None  no_progress=None
 t+  10.0s  http=200 worker=ok  beats=8    beat_age=1.10  claims=2     no_progress=8.05
 t+  50.9s  http=200 worker=ok  beats=22   beat_age=1.13  claims=2     no_progress=48.51
 t+ 150.9s  http=200 worker=ok  beats=55   beat_age=0.67  claims=2     no_progress=148.94
 t+ 251.5s  http=200 worker=ok  beats=88   beat_age=2.02  claims=2     no_progress=249.53
 t+ 301.8s  http=200 worker=ok  beats=107  beat_age=0.01  claims=2     no_progress=299.87
 t+ 311.9s  http=503 worker=STALLED beats=153 beat_age=1.01 claims=2   no_progress=309.95

problem: worker 'watcher' is beating but its work has not progressed for 309.95s
         (threshold 300.0s): ingest wedge_ophard_wedge_n.csv
```

The three columns that make this the right case and not something else:

- **`claims=2` throughout** — both lanes claimed, so the heavy lane's own worker thread is covered
  and not merely the inline one.
- **`beats` climbed 1 → 153 and `beat_age` never exceeded 3 s.** The beat was *fresh at the moment
  of the 503*. The old signal, on its own, said "fine" for the entire 312 s. That is the hole,
  reproduced and then closed.
- **31 consecutive `200/ok` samples before the threshold.** A guard that fired early would have
  shown up here; a legitimately slow ingestion is not an alarm.

On release, `/health` returned to 200 in **2.0 s** and claims dropped to `open: 0` — the recovery is
the ingestion resuming, not a restart papering over it.

**First attempt failed, and it is worth recording why.** The drill originally reached the database
through the same killable proxy used by the outage drills. Under load the proxy dropped a
connection, `/health` returned 503 on the *database* row at t+10 s, and the drill's "first 503"
logic scored that as detection. It was re-run against the database directly and re-scored on
`worker_status == "stalled"` specifically. A 503 is not evidence on its own; the reason has to
match.

---

## 3. B3 — module loggers reach the process log file

`get_process_logger` attached its handlers to a logger named after the process and stripped the root
logger on the way. Loggers that happened to be *children* of that name inherited a handler
(`Watcher.DirectoryWatcher` under `Watcher`); every other module logger did not. `crud.py` logs to
`logging.getLogger("Server")`, which in a worker process has no handlers, propagates to a
handler-less root, and falls to `logging.lastResort` — bare stderr, absent from the worker's own log
file.

**Fix: the handlers go on the root logger; the named process logger keeps none and reaches them by
propagation.** Every logger in the process therefore lands in the file exactly once, and `%(name)s`
keeps the origin, so a `[Server]` line inside `watcher.log` is still identifiable as one.

Two consequences handled:

- **Duplication.** Handlers on root *and* on the named logger would print every process-logger line
  twice. `test_no_line_is_written_twice` asserts `named_handlers == 0` and `root_handlers == 2`.
- **Third-party flood.** Handlers on root means every library logs here too. `NOISY_THIRD_PARTY`
  pins sqlalchemy/watchdog/urllib3/asyncio/etc. to WARNING.
  `test_third_party_info_chatter_is_not_promoted_into_the_log` asserts their INFO is gone **and**
  that their ERRORs still get through — over-correcting into silence is its own defect.

The launcher's banners moved from `print()` to the same logger, so the permanent-failure and
shared-cause banners are now durable in `launcher.log` while console output is unchanged.

**Proof, live, in the exact scenario the warning exists for.** The 100k drill's isolated table
declares `orphan_col` in `display_columns` but *not* in `column_types` — a config that lags its
producer, which is how `map_doe` lost `eventtime`. Every one of the 100,000 rows carried it, the
watcher passed it through, and `crud.py` dropped it. From `dev_env/ops2_root/watcher.log`:

```
[Server] [2026-07-27 07:42:35,401] WARNING - [Schema] Column 'orphan_col' is not declared in
column_types for table 'ophard_100k' and was DROPPED from the update; the write still succeeded
for the declared columns. Add it to config/table_config.json to persist it.
```

`[Server]` inside `watcher.log` is the whole point: the line originates from `crud.py`'s logger and
lands in the log of the process that actually ran the ingestion. Before this it went to
`logging.lastResort`.

What each process log now carries, measured over the same drill:

| file | lines | distinct logger names present | sqlalchemy/watchdog/urllib3 lines |
|---|---|---|---|
| `watcher.log` | 549 | `Watcher`, `Watcher.DirectoryWatcher`, `Watcher.StdParser`, `Watcher.ConfigWatcher`, **`Server`**, **`PipelineBase`** | **0** |
| `server.log` | 397 | `Server`, `Chain`, `Chain.enrichment_dedup`, `Watcher.ConfigWatcher`, `sqlalchemy.pool.impl.QueuePool` | 4 |
| `chain_worker.log` | 346 | `Chain`, `Chain.enrichment_dedup`, `GraphMaterializer`, `GraphSync`, `Watcher.ConfigWatcher`, `sqlalchemy.pool.impl.QueuePool` | 6 |

The `Server` and `PipelineBase` rows in `watcher.log` are the fix. The third-party count is 0 in the
watcher and single digits elsewhere, and those are **ERROR**-level:

```
[sqlalchemy.pool.impl.QueuePool] ERROR - Exception during reset or similar
```

Connection-pool exceptions that were previously invisible. That is a bonus, not the goal, but it is
the kind of thing this blocker was hiding.

---

## 4. Load measurement — is 60 s still right?

The 60 s staleness threshold rested on a worst observed gap of 10.26 s on a **mostly idle** stack.
Re-measured under a live **100,000-row, 35 MB, heavy-lane** ingestion driven through the real
launcher (all five children supervised), sampling every heartbeat file at 100 ms and recording the
interval between actual changes of each worker's beat counter — the same instrument as the idle
measurement, so the numbers are comparable.

Ingestion: **893.6 s** end to end, **100,000 rows / 100,000 distinct keys** verified in `assy_qa`.
The auto-update scheduler was live throughout and dropped collector files into other workspaces
mid-run, so this is a loaded stack, not a single file in isolation.

| worker | phase | n | min | p50 | p95 | **max** | headroom (60 s ÷ max) |
|---|---|---|---|---|---|---|---|
| chain | idle | 19 | 0.73 | 1.98 | 3.00 | 3.00 | 20.0× |
| **chain** | **load** | **405** | 0.33 | 1.99 | 4.16 | **7.01** | **8.6×** |
| chain | drain | 42 | 0.82 | 2.08 | 2.91 | 2.99 | 20.0× |
| graph | load | 446 | 0.44 | 2.00 | 2.72 | 3.02 | 19.9× |
| scheduler | load | 176 | 1.17 | 5.01 | 5.49 | 6.61 | 9.1× |
| watcher | load | 386 | 0.11 | 2.94 | 3.54 | 4.24 | 14.1× |

**Verdict: 60 s is confirmed, unchanged.** The worst gap across all four workers under load is
**7.01 s** — the chain worker, as predicted, and *better* than the 10.26 s outlier previously seen
on an idle stack. Load did not eat the headroom; 8.6× remains. Every p50 still lands on its designed
loop period, so the beats are coming from the work loops and not from some incidental timer.

Pinned by `test_stale_threshold_survives_the_measured_load`, so a future change that tightens the
threshold below this measurement fails the suite instead of producing false 503s in production.

### 4.1 The other number: claim progress

The stall threshold is bounded by a different quantity — how long a *claim* may go without
advancing. Derived from committed row counts, which are exact and monotonic:

```
per-1000-row chunk interval, 42 unambiguous single-chunk intervals:
  min 8.10   p50 9.20   p95 9.70   max 12.50 s
end-to-end average: 893.63 s / 100 chunks = 8.94 s per chunk   (agrees)
```

**Worst instrumented claim-progress gap: 12.50 s**, i.e. 24× headroom against the 300 s stall
threshold. Note this measurement does *not* by itself justify 300 s — on the chunk cadence alone
60 s would have been defensible at 4.8×. What sets the floor is the **uninstrumented** stage: a
custom pipeline parser reads a whole file in one opaque call and reports nothing while it does.
That is stated plainly in the constant's comment so the next person does not tighten it thinking the
chunk numbers are the binding constraint.

**Instrument caveat, since it changes a number I first reported to myself.** A first reduction over
the drill log gave a worst claim gap of 45.56 s. That was an artifact: the sampler only logged when
the heartbeat's `note` string *changed*, and `beat()` throttles file writes to 1/s, so a chunk beat
that was throttled advanced the claim in memory without ever appearing in the log. Inspecting the
worst case showed it spanned chunks 92,000 → 97,000 — five chunks at 9.1 s, not one 45 s stall. The
row-count derivation above has no such blind spot, which is why it is the number quoted.

---

## 5. psutil

Declared in **both** manifests — `environment.yml` (the real environment definition) and
`pyproject.toml` — because grandchild cleanup silently degrading to a no-op is how orphaned
collector subprocesses accumulate unnoticed.

It still degrades rather than crashing without it, but **loudly**, announced at boot rather than
discovered at shutdown:

```
CONTROL  - psutil present
  stdout        [Launcher] INFO - psutil 7.2.2 - grandchild cleanup armed
  launcher.log  [Launcher] INFO - psutil 7.2.2 - grandchild cleanup armed

DEGRADED - psutil unimportable (shadowed on PYTHONPATH; nothing uninstalled)
  stdout        [Launcher] WARNING - psutil is not importable (No module named 'psutil') -
                grandchild cleanup is DISABLED: stopping the launcher will terminate its five
                children but not the subprocesses they spawned (auto-update collector scripts),
                leaving orphans behind. Install it: conda install -n assy_manager psutil
  launcher.log  (same line)

VERDICT: LOUD
```

The degraded code path also complains once per process the first time it is actually used, and only
once — a warning that repeated on every call at shutdown would be noise
(`test_psutil_absence_is_announced_not_silent` asserts both halves).

---

## 6. Injected-defect run

Thirteen defects, each removing exactly one guard. Edits and restores done in **bytes** from a
pristine copy taken first, then sha256-verified — a text-mode rewrite would silently convert line
endings while `git diff` stayed clean.

```
BASELINE  79 passed

CAUGHT  D1  correlated rule removed - always give up
CAUGHT  D2  environment evidence ignored (peer rule only)
CAUGHT  D3  unreachable database reported as reachable
CAUGHT  D4  psutil degradation silent again
CAUGHT  D5  correlated state not published to /health
CAUGHT  D6  ingestion opens no work claim
CAUGHT  D7  chunk loop no longer beats
CAUGHT  D8  claims are not thread-affine
CAUGHT  D9  /health ignores a stalled claim
CAUGHT  D10 stall age measured at write time, not read time
CAUGHT  D11 console handler back on the named logger only
CAUGHT  D12 file handler back on the named logger only
CAUGHT  D13 third-party noise no longer pinned

VERDICT: 13/13 caught; sources byte-identical after restore: True
  process_supervisor.py 26c2bd54cb4c3811   heartbeat.py  678efc55a9491180
  health.py             fd53496055844ab2   logger.py     d475b1bf1b9eff85
  directory_watcher.py  a86b6920bc9b19a1
```

D2 is the load-bearing one for §1.3: with the environment evidence ignored,
`test_a_lone_child_is_spared_while_its_database_is_down` fails with *"the web server was permanently
failed while its database was down"* — the exact production outcome from §1.2.

**The first run scored 11/13, and the two gaps were not misses.** D6 and D7 reported
`anchor matched 0 times` because those multi-line anchors were written with `\n` while
`directory_watcher.py` is CRLF on disk, so the defect was never injected and the tests were never
challenged. A run that only reads the verdict line would have called that "11 caught, 2 tests too
weak". The injector now tries both line endings and reports a skip distinctly from a miss.

A fourteenth guard was verified separately because it lives in `conftest.py`: disabling the
heartbeat isolation fixture (`autouse=True` → `False`) makes
`test_the_suite_can_never_beat_into_the_live_tree` fail with *"the suite is beating into the live
config directory"*. See §8.1.

---

## 7. Files

| file | change |
|---|---|
| `server/process_supervisor.py` | correlated-failure state + policy, `shared_dependency_down` probe, loud psutil degradation |
| `server/health.py` | `correlated_children` surfaced; a stalled work claim escalates to 503 |
| `server/utils/heartbeat.py` | `work_claim` / `open_claims`, thread-affine claim refresh, `work` in the beat payload, `DEFAULT_STALL_AFTER_SEC` |
| `server/utils/logger.py` | **B3** — handlers on root, named logger handler-free, third-party noise pinned |
| `server/parsers/directory_watcher.py` | claim around both ingestion entry points, stage beats, per-chunk beat |
| `server/run_watcher.py` | comment only — the poller beat's role changed, the code did not |
| `run_decoupled_app.py` | launcher output through the process logger; psutil announced at boot |
| `environment.yml`, `pyproject.toml` | `psutil` declared |
| `server/tests/conftest.py` | **session autouse fixture** — the suite can no longer beat into the live tree (§8.1) |
| `server/tests/test_process_supervisor.py` | +14 tests (correlation, environment evidence, psutil) |
| `server/tests/test_health_endpoint.py` | +11 tests (stall, correlated reporting, both thresholds vs measurement) |
| `server/tests/test_ingestion_heartbeat.py` | **new** — 6 tests |
| `server/tests/test_process_logging.py` | **new** — 7 tests |
| `server/tests/test_dev_env_isolation.py` | log probe now walks the effective handler chain |

Not mine: `server/product_tables.py`, `server/config/table_config.json.sample`,
`server/tests/test_install_product_tables.py`, `client2/**`. Another agent's concurrent M2.6 work,
which they **committed mid-session** (`cdcddee`, `d411386`, `87cbf35`) — so my working tree is now
those commits plus my uncommitted changes, and `git status` shows only my files.

No boundary contract changed: no REST signature, no WS event, no cell shape, no schema contract.
`/health`'s payload gains fields only (`checks.supervisor.correlated_children`,
`checks.workers.*.work`); nothing in `client2` consumes `/health` (grepped).

---

## 8. What this does not cover

### 8.1 A leak I caused, found and closed — read this one first

Adding a heartbeat to the ingestion path made **the test suite write into the user's live tree**.
`test_std_parser.py` and `test_workspace_config_deprecation.py` both drive `process_with_retry`, and
with no `ASSY_DATA_ROOT` set that resolves to `server/config/worker_heartbeats/watcher.json`. I found
it during the post-run production check, not by design:

```
{"name":"watcher","pid":23844,"ts":...,"beats":45,"note":"done: ingest drop.csv","work":{"open":0}}
```

Attributable to me beyond doubt: `work` is a field that exists only in my uncommitted code, and the
process lived 14 seconds. Nothing was destroyed — it creates a new file — but it is **not harmless**:
`/health` reads heartbeats off disk, so a dead pytest process's beat sitting in production would be
reported as a stale worker and serve a **503 on a perfectly healthy system**.

Fixed structurally rather than per-test: a session-scoped autouse fixture in `conftest.py` redirects
the heartbeat directory for the whole suite, in the same spirit as the existing `DATABASE_URL` pin.
The leaked file was removed, the directory no longer exists, and two full suite runs since produce
no `server/config/worker_heartbeats/` at all.

### 8.2 Item 1 — shared-cause failure

1. **The web server is the one child whose failure `/health` cannot report**, because it *is* the
   endpoint. During §1.5's outage `/health` was unreachable for 300 s. The durable record is
   `supervisor_status.json` and now `launcher.log`; an external monitor sees a connection refusal
   rather than a JSON reason.
2. **A shared cause that kills children slowly is not detected.** The window is 120 s from a child's
   *own* budget exhaustion. If a cause takes 10 minutes to kill the second child, the first has
   already been permanently failed alone.
3. **Only the database is probed.** A full disk, an exhausted file-handle table, a broken network
   share holding `ingestion_workspace` — all are shared causes with no probe. They are still caught
   if two children fail together; a lone child dying of a full disk is not.
4. **The probe checks reachability, not usability.** A database that accepts connections but rejects
   authentication, or is missing the schema, reads as healthy — deliberately, because a retry loop
   does not fix a configuration fault. A database in that state while a child crash-loops will
   permanently fail that child.
5. **`retrying_correlated` retries forever by design.** If the cause never clears, the loop never
   stops. It is loud and unhealthy the whole time, but it will not escalate further, and nothing
   pages anyone.
6. **Nothing supervises the supervisor** (unchanged from the previous report).
7. **The correlation state is per-launcher-process.** A launcher restart resets every counter, so
   the evidence window does not survive it.

### 8.3 Item 2 — the ingestion heartbeat

1. **Up to 300 s to notice.** That is the deliberate bias (§2.2), but a wedge is invisible for five
   minutes and the operator sees `ok` the whole time.
2. **A stalled claim is reported at worker granularity, not per claim.** With two files in flight,
   `/health` names the *oldest* claim. A second job wedging while the first progresses is caught (the
   oldest becomes the wedged one), but the payload shows one entry, not a list.
3. **Nothing is claimed outside ingestion.** The chain worker, graph materializer and scheduler still
   publish liveness beats only. A chain worker wedged mid-transaction with a fresh beat is not
   covered — the same hole this closed for the watcher, still open for the other three.
4. **The opaque parse is uninstrumented.** A custom pipeline parser that blocks for 4 minutes is
   indistinguishable from one that is working. Nothing inside a user script reports progress and
   nothing here can make it.
5. **A claim leaked by a hard-killed process is not cleaned up** by the next process — but the beat
   itself goes stale, so the worker reads as `wedged`/`down`, which is louder. No hole, but the
   reported reason will be the stale beat, not the orphaned claim.

### 8.4 Item 3 — the load measurement

1. **One machine, one file shape, one run.** 100,000 rows, 35 MB, 14 columns, CSV, std parser, on a
   machine simultaneously running the user's production stack and another agent's stack. A
   100-column table or an Excel workbook would have a different chunk cost.
2. **The claim-gap reduction had a blind spot** (§4.1) and the first number I derived from it was
   wrong by 3.6×. The row-count derivation replaced it; the beat-gap numbers were always taken from
   the raw 100 ms samples and are unaffected.
3. **Not measured at 10,000,000 rows.** The chunk cadence is per-1000-row and should be flat, but
   that is reasoning, not measurement.

### 8.5 Item 4 — psutil

Declared and announced, but **the announcement is at launcher startup only**. A machine that loses
psutil after the launcher started keeps the stale "armed" line; the degraded path then warns once
when it is first used, which is at shutdown — too late to act on. Nothing checks it periodically.

### 8.6 Item 5 — B3

1. **Handlers on root means the log now includes anything any library logs at WARNING+.**
   `NOISY_THIRD_PARTY` covers the libraries this system actually uses; a new dependency that is
   chatty at WARNING would land in the process logs and nothing would notice until someone reads them.
2. **`logging.getLogger("Server")` inside a worker is still a confusing name.** The line is now
   findable, but `crud.py` labelling itself `Server` in `watcher.log` is a naming wart this did not
   fix — renaming it is a signature-style change across every call site and was out of scope.
3. **Log rotation is still absent.** The live `server/*.log` files are already 2–19 MB. Routing more
   loggers into them makes that grow faster. Not introduced here, but made slightly worse.
4. **The launcher's `print("=" * 60)` banner lines still go straight to stdout** — only
   `log_launcher` calls were rerouted.

### 8.7 Environment caveats on the drills

- **The database was reached through a TCP proxy** for the outage drills. It drops connections under
  sustained load, which produced a spurious 503 at the end of the 100k drill and one false detection
  in the first wedge attempt. The ingestion itself completed correctly (100,000 rows / 100,000
  distinct keys verified), so the measurement stands, but the proxy is a drill instrument and not
  production-grade.
- **Another agent committed three times during this session**, so the 576-test figure is measured on
  a base that moved under me. Their files are named in §7 and their delta is excluded from my count.
- **The live `server/*.log` files were being appended to throughout** by the user's running stack, so
  any log-based check here was scoped to the isolated root, never to those files.

---

## 9. Proposed lessons (for review — not applied)

**server-pm section:**

> - **함정**: 인시던트 시나리오를 **검증 없이 전제로 받아** 그것만 막는 가드를 만든다. 2026-07-27 실측:
>   "DB 장애가 자식 5개를 동시에 죽인다"는 전제가 **틀렸다** — 실행 중 스택에서 DB를 5분간 끊어도
>   exit 0건·restart 0건(워커 루프가 OperationalError를 자체 재시도)이고, 실제로 죽는 건 **콜드 스타트
>   시 웹서버 1개뿐**이다(main.py 임포트의 `create_all`). 즉 "함께 실패"만 보는 규칙은 정작 제일 흔한
>   장애(t+94초에 웹서버 영구 실패)를 못 잡는다.
>   **올바른 방법**: 가드를 만들기 전에 **그 장애를 먼저 유발해 무슨 일이 실제로 벌어지는지 측정**하라.
>   측정이 설계를 바꾼다.
> - **함정**: 프로세스에 새 부작용(하트비트·상태파일 쓰기)을 심으면, 그 코드 경로를 타는 **기존 테스트가
>   사용자 라이브 트리에 파일을 쓴다**. 2026-07-27: 인제션 경로에 beat를 넣자 `test_std_parser` 등이
>   `server/config/worker_heartbeats/watcher.json`을 실제로 생성했고, 죽은 pytest 프로세스의 비트는
>   `/health`에서 stale worker로 읽혀 **정상 시스템에 503**을 만든다.
>   **올바른 방법**: 새 쓰기 경로를 추가하면 그 즉시 `conftest.py`에 **세션 autouse 격리 픽스처**를 넣어
>   전 테스트를 한 번에 막고(개별 테스트 패치 금지), 작업 종료 전 라이브 트리에 산출물이 생겼는지 확인한다.
> - **함정**: 스레드가 여럿인 프로세스에서 **하트비트를 하나만 두면 "가장 부지런한 스레드"가 멈춘
>   스레드를 가린다**. 워처의 3초 재시도 폴러가 인제션 웨지를 300초 넘게 가렸다.
>   **올바른 방법**: 살아있음(beat)과 진행(work claim)을 **분리**하고, claim은 **스레드 귀속**으로 갱신한다.
>   그러면 폴러는 가림막이 아니라 **웨지의 신고자**가 된다(다른 스레드의 정체를 자기 비트에 실어 보낸다).
> - **함정**: 임계값 근거를 **측정 전에 주석·테스트에 적어두면** 그대로 거짓이 되어 남는다. 실측 전
>   "worst chunk gap 2.06s"라고 써둔 값이 실측 결과 **12.50s**였다(6배 오차).
>   **올바른 방법**: 숫자를 코드에 적기 전에 측정하고, 측정 방법의 맹점까지 함께 적는다(로그 기반 축약이
>   throttle된 비트를 놓쳐 45.56s로 3.6배 부풀렸다 — 행 카운트 기반으로 교차검증해서야 잡혔다).
> - **함정**: 결함 주입 스크립트의 앵커가 **매칭 0건이면 "주입 실패"인데 verdict만 보면 "미검출"과
>   구분이 안 된다**. `\n` 앵커가 CRLF 파일에 안 맞아 2건이 조용히 스킵됐다.
>   **올바른 방법**: 주입기는 앵커 매칭 수를 검증하고 **skip과 miss를 다른 문자열로 보고**한다. 앵커는
>   양쪽 개행을 모두 시도.

**Shared section:**

> - **함정**: 공유 인프라(PostgreSQL 서비스)를 멈춰서 장애를 유발하면 **사용자 운영 스택까지 같이 죽는다.**
>   **올바른 방법**: 격리 스택만 **killable TCP 프록시**(예: :55432 → :5432)를 경유시키고 프록시를 죽인다.
>   실 서비스는 무손상, 격리 스택만 진짜 "connection refused"를 본다. 단 프록시는 부하에서 연결을 떨구므로
>   **부하 드릴은 DB 직결**로 돌릴 것(부하 드릴에서 프록시발 503을 웨지 검출로 오판한 사례 있음).
> - **함정**: 드릴에서 "503이 떴다"를 곧바로 검출 성공으로 채점하면, **다른 이유로 뜬 503**에 속는다.
>   **올바른 방법**: 채점 조건은 상태코드가 아니라 **원인 필드**로 한다(`worker_status == "stalled"`).

---

## 10. Production untouched

```
server/config/worker_heartbeats/      exists: False
server/config/supervisor_status.json  exists: False
server/launcher.log                   exists: False
```

All three are created on first use, so their absence after two full suite runs and six live drills
is the strongest single line here — and `worker_heartbeats/` is the one that *did* appear once, from
the suite, which is why §8.1 exists. It was removed and has not come back.

`server/config/table_config.json` mtime `Jul 27 06:49` — before this session's first edit (07:05).
The isolated drills wrote their drill tables into `dev_env/ops2_root/config/table_config.json` only.

The user's live stack was running throughout (`server/*.log` still being appended at 08:14 by pids
that were never mine) and its ports are untouched:

```
127.0.0.1:8080  pid 43636   <- user's production web server
127.0.0.1:8090  pid 46588   <- user's production graph sync
127.0.0.1:8081  pid 47716   <- another agent's isolated stack
127.0.0.1:8091  pid 47904   <- another agent's isolated graph
```

My drill ports (8086 / 8096 / 55432) are all free — **zero drill processes left running**.

**Drill cleanup:** `dev_env/ops2_root` removed; the shadowing `broken_env/` removed; the three
`ophard_*` drill tables dropped from `assy_qa` along with 1,400,004 `cell_sources`, 100,002
`audit_logs`, 100,002 `database_outbox` and 3 checkpoint/log rows. `assy_qa` outbox is back to
3,987 rows.

**The contaminated window in the user's live `server/*.log` was not touched** — those lines were left
exactly as found, per instruction.

---

## 11. Handover

**Changed** — the correlated-failure policy and environment probe in `process_supervisor.py`; work
claims in `heartbeat.py` wired into both ingestion entry points in `directory_watcher.py`; the stall
verdict and correlated reporting in `health.py`; the B3 handler wiring in `logger.py`; the launcher's
output routed through it; `psutil` declared. Four test files touched, two new, plus a `conftest.py`
isolation fixture. **Nothing committed. No boundary contract touched.**

**Verified** — every condition induced rather than asserted: a real database outage (nothing died),
a real cold start with no database (one child died, permanently, before the fix and not after), a
real four-child crash loop from a broken shared dependency, a real parser wedge behind a healthy
poller, a real 100,000-row ingestion, a real psutil-less launcher, and the real `crud.py` warning in
the real worker log. 13/13 injected defects caught, sources byte-identical. Suite **576 passed / 0
failed**, of which **38 tests are mine** (arithmetic in §Verdict — the base moved mid-session).

**Needs a decision from you**

1. **§1.3 row 2 — the environment probe.** I widened the evidence for "not alone" beyond peer
   failures to include a verifiably-down database, because §1.2 showed the peer-only rule misses the
   most likely real outage. The delegated part was the definition of "together", but this is the
   piece most worth a second opinion. Veto is one argument:
   `Supervisor(environment_probe=lambda: (False, None))`.
2. **300 s stall threshold** (§2.2). Biased toward silence. If five minutes of invisible wedge is too
   long for this team, the number moves; the measurement supports anything above ~130 s.

**Open / next**

3. **The other three workers have no work claims** (§8.3.3). The chain worker is the strongest
   candidate — it is the one with a measured 7.01 s worst gap under load and the one that drains the
   outbox.
4. **`server/main.py:46` runs `create_all` at import**, which is *why* the web server is the child
   that dies on a cold start. Making that lazy or retried would remove the failure rather than
   tolerate it, and is a smaller change than it sounds.
5. **Log rotation** (§8.6.3) — live logs are 2–19 MB and now grow faster.
6. **Docs owed once merged**: `SYSTEM_OVERVIEW`, `architecture/backend.md`, a `docs/history/` entry,
   and `PRODUCTION_READINESS.md` **B3 can be struck** (§3 is the evidence). `PRIMITIVES.md` should
   gain "worker progress heartbeat / work claim" — it currently has no entry for heartbeats, health
   or supervision, which is why I had to rediscover the mechanism by reading source.
7. **`devenv` still has no named-instance or lock** (carried over): I again had to hand-build a
   private root and ports because `:8081/:8091` were occupied.
