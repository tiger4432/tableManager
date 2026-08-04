# Server - launcher startup diagnosis and broadcast recovery

Six defects fixed: the four behind "the server takes a minute to come up, or
never does", plus the two notification gaps that lose announcements whenever the
hub is briefly unreachable.

**Suite: 2066 passed, 2 skipped, 0 failed** (`conda run -n assy_manager python -m
pytest server/tests/ -q`, 373 s). The run immediately before the fixes landed
collected the same 2066 with 3 failing, so nothing was added or removed by
accident; the 3 were mine and are green.

**The running production stack was never touched.** Same PIDs before and after
(launcher 12836, backend 8444, watcher 5968, graph 31396, chain 27404, scheduler
2484). Every port probe in the tests uses a throwaway port bound by the test
itself. The one thing pointed at the live ports was `--preflight-only`, which
starts nothing.

---

## (1) Pre-flight single-instance guard

`run_decoupled_app.py` now test-binds the API port and the graph sync port before
`start_all()`, and refuses if either is taken. Both ports are read from the
environment (`ASSY_API_PORT`, `GRAPH_SYNC_PORT`), so an isolated stack checks
:8081/:8091 rather than production's. The graph port is probed on `127.0.0.1`
because that is what `run_graph_sync.py` binds - on Windows a bind to
`0.0.0.0:8090` succeeds while another process holds `127.0.0.1:8090`, which is
why the probe is a bind test OR a connect test rather than either alone.

### The message an operator actually sees

Run live against the running stack (`--preflight-only`, nothing spawned):

```
====================================================================
 기동을 중단합니다: 필요한 포트를 이미 다른 프로세스가 쓰고 있습니다.
 REFUSING TO START - required ports are already in use.

   TCP port 8080 is already held by PID 8444 (python.exe) [bind failed (OSError)]
   TCP port 8090 is already held by PID 31396 (python.exe) [bind failed (OSError)]

 이 서버 스택이 이미 실행 중일 가능성이 가장 높습니다.
 이미 떠 있는 스택이라면 그대로 사용하십시오. 새로 띄울 필요가 없습니다.
 정말로 재시작하려면 위 PID 를 먼저 종료하십시오:
     taskkill /PID <pid> /T /F

 (아무것도 기동하지 않았습니다. 기존 프로세스는 그대로 살아 있습니다.)
 Nothing was started. The processes that own these ports are untouched.
====================================================================
```

Every line is ERROR level, so it is red on the console and also lands in
`launcher.log` (verified: the Korean survives the file handler and the cp949
console - no line was dropped when run with `PYTHONIOENCODING` unset, the
production configuration). Exit code 1. Elapsed: under a second.

The "Starting AssyManager Enterprise" banner was moved to AFTER the guard.
"Starting..." followed by "REFUSING TO START" is a contradiction an operator has
to stop and reread.

`--preflight-only` was added: it asks the question and exits without starting
anything. It is a real operator convenience and it is what makes the end-to-end
test safe - a regression in the guard cannot spawn a second stack on top of the
live one.

## (2) A port conflict is not an environment outage

`server/process_supervisor.py`. At the giving-up point there are now three
questions, asked in this order:

1. **Is a port this child must bind already held?** Terminal. `STATE_FAILED`,
   `terminal_verdict="port_conflict"`, a banner naming the port and the PID, and
   the remedy. Never restarted again.
2. Is it failing alongside peers, or is the database down? Unchanged - correlated
   retry, indefinitely.
3. Failing alone in a healthy environment? Unchanged - broken child.

The port question is asked FIRST specifically because the duplicate-launcher case
kills *both* port binders at once, so the peer rule cheerfully called it a shared
cause and retried on `CORRELATED_BACKOFF_SEC = 60.0` with no limit. That ordering
is the fix.

`ChildSpec` gained `ports=` / `port_host=`; only the two children that bind
anything declare them, and `test_the_probe_is_not_consulted_for_a_child_that_binds_nothing`
holds that line. The probe runs only at the giving-up decision, like the existing
environment probe, and a probe that raises decides nothing.

### Both branches, proved

| branch | fixture | verdict |
|---|---|---|
| port conflict | two port binders dying together, port probe says taken | both `failed`, `terminal_verdict=port_conflict`, `failure_reason` names PID 8444, spawns stop dead (`test_a_port_conflict_is_terminal_and_names_the_owner`) |
| database outage | **the same two children dying together**, ports free, database probe says down | both `retrying_correlated`, `failed_children == []`, spawn count keeps climbing past the cap (`test_a_database_outage_still_gets_the_correlated_retry`) |
| lone binder + database down | the measured real outage (only the web server dies) | `retrying_correlated`, evidence names the database (`test_a_lone_port_binder_with_a_down_database_still_retries`) |
| broken child + free port + healthy DB | control | `failed`, `terminal_verdict=broken_child`, no PORT CONFLICT banner |

The first two use an identical fixture and differ only in what the probes say, so
the difference in verdict is attributable to the probe and nothing else.

The real probe is exercised against a real listening socket too
(`test_the_real_probe_sees_a_real_socket`): it reports the conflict and names the
test process's own PID. Confirmed on this box that `psutil.net_connections`
returns the owning PID without administrator rights.

## (3) Child stdout/stderr is captured

Each child's merged stdout/stderr is tee'd: byte-for-byte to the launcher's
console exactly as before, and appended to `<DATA_ROOT>/<name>_stdout.log`.

A pipe plus a reader thread, not `stdout=<file>` - redirecting straight to a file
would have silenced the console, and five children's interleaved output in one
window is how an operator watches this system start. Bytes are passed through
undecoded, so the console gets exactly the bytes it got before and no decode step
exists that could raise and lose a line. `PYTHONUNBUFFERED=1` is set for captured
children: with stdout on a pipe CPython block-buffers it, and the one line this
capture exists for could otherwise sit in an 8 KB buffer while the process dies.
The file rotates at 20 MB with one `.1` backup (uvicorn's access log is the volume
driver).

### The acceptance test: the bind error, in a file

Live, through the real spawn path, with a real uvicorn on a real occupied
throwaway port (:10802 held by the demo script):

```
=== Backend FastAPI Server started 2026-08-04 12:27:07 pid=11936 cmd=...python.exe -m uvicorn tinyapp:app --host 127.0.0.1 --port 10802 ===
INFO:     Started server process [11936]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
ERROR:    [Errno 10048] error while attempting to bind on address ('127.0.0.1', 10802): [winerror 10048] 각 소켓 주소(프로토콜/네트워크 주소/포트)는 하나만 사용할 수 있습니다
```

All four of the lines that previously existed in no file on disk are there,
including the header that answers "which run was this" - the question that two
launcher banners with no shutdown between them made unanswerable.

In pytest the same thing is asserted with a real child that really fails to bind
(`test_a_childs_bind_error_lands_in_a_file`): the file must contain `Traceback`,
`OSError` and `10048`.

Note on encoding: the captured file holds whatever bytes the child wrote, which
in production is cp949 (same as the console). The decisive lines are ASCII up to
the OS's own Korean message. Forcing UTF-8 was rejected because it would make the
operator's console mojibake.

## (4) 503 is exempt from the proxy verdict

`server/internal_event_client.check_api_reachable`. The trigger is narrowed, not
removed. The discriminator is the response BODY: `own_health_payload()` returns
the parsed body only when it carries `status` AND a `checks` dict - the shape
`health.compute_health` produces and a proxy cannot accidentally satisfy.

- our own 503 -> level `warning`, "answered by THIS application reporting
  status='unhealthy'", followed by the actual `problems` list. No proxy essay.
- 503 with an HTML body -> unchanged ERROR proxy essay with `Server:` header,
  `NO_PROXY` prohibition and the Korean guidance.
- 403 from squid -> unchanged.
- `{"status": "error"}` with no `checks` -> proxy essay (a proxy must not be able
  to impersonate us with a one-key body).

`server/main.py` was NOT touched - the health payload shape already existed.

---

## (5) The sweep that consumed the marker and announced nothing

`chain_ingestion_worker.sweep_undelivered_broadcasts`. The refresh target set is
now `(chain rule targets) UNION (the table each stale row was written to)`.

**How the infinite re-sweep is still prevented.** The guard was never the
"broadcast nothing" part - what actually terminates the sweep is *stamping*
`broadcast_at` after a successful announcement. `table_name` is NOT NULL, so the
union is never empty, so every sweep now ends in fire-then-stamp and a stamped row
can never be selected again. The old early-return is kept only for the
pathological case of a row naming no table at all, and it logs a warning instead
of being silent.

Unchanged: a broadcast that fails leaves `broadcast_at` NULL and is retried next
sweep (eventual delivery), one dedup'd refresh per table however many rows, the
`batch_refresh_required` contract, the LIMIT 500 + 5 s grace + partial index.

## (6) The watcher's log-and-drop notification path

`run_watcher.post_event` now leaves a durable marker when a notification does not
arrive - on an exception and on any non-ok status. The marker is written by
`internal_event_client.record_undelivered_notification`, i.e. **the marker the
chain worker already sweeps**, not a second mechanism:

```
event_type = BROADCAST_RECOVERY   (event_constants; added to CONTROL_EVENT_TYPES)
table_name = the table whose announcement was lost
status     = 'SUCCESS'      the DATA succeeded; only the notification failed
processed_chain = True      never re-run as a data transaction, no mapper
broadcast_at    = NULL      the marker itself
payload    = {endpoint, reason, marker}   small scalars only
```

The next sweep (<= 5 s) fires `batch_refresh_required` for `table_name` and stamps
it. This is why (5) had to be fixed first: a BROADCAST_RECOVERY row maps to no
chain target, which is exactly the case the old sweep swallowed.

Inert everywhere else by construction: the chain worker's queue only reads
`processed_chain = False`; the graph materializer only acts on `CREATE`/`EDIT`;
the 7-day outbox purge collects it like any processed row. A marker write that
fails is logged and swallowed - a recovery path must not take down the ingestion
it was trying to announce.

Notifications with no `table_name` leave no marker: there is nothing to refresh.

## Red/green pairs (mutation checks)

Every fix was reverted in place and the tests re-run. Reverted mutations left no
trace (`grep MUTATION` over the tree is clean; `git diff --stat` shows only the
intended files).

| mutation | result |
|---|---|
| (5) `source_tables = set()` + (6) calls removed to `pass` | **9 red**, 3 green. The 3 green are the controls: nothing-to-sweep is silent, a delivered notification leaves no marker, the marker type is a declared control event. |
| (5) broadcast unconditionally, never stamp (`if True: return` before the stamp) | **`test_the_sweep_cannot_spin_forever` red**: `assert 6 == 1` - "the sweep re-announced rows it had already delivered - infinite re-sweep". This is the mutation the brief asked for and it lands on exactly the intended test. |
| (1) `preflight_port_check` returns `[]` | `test_preflight_names_the_pid_that_owns_the_port`, `test_the_launcher_refuses_to_start_and_starts_nothing` red |
| (2) port branch disabled | `test_a_port_conflict_is_terminal_and_names_the_owner` red with `assert 'running' == 'failed'` - i.e. under the mutation the child is being retried forever, the production bug exactly |
| (3) `log_file` ignored in `_default_spawn` | `test_a_childs_bind_error_lands_in_a_file` red |
| (4) `own_health_payload` result ignored | `test_our_own_503_is_not_reported_as_a_proxy` red |

Under mutation (1)+(2)+(3)+(4) together, `test_a_database_outage_still_gets_the_correlated_retry`
stayed **green** - as it must: the correlated policy is untouched by all four.

## Files changed

| file | why |
|---|---|
| `run_decoupled_app.py` | pre-flight refusal, `--preflight-only`, `ports=`/`log_file=` on the specs, banner moved after the guard |
| `server/process_supervisor.py` | port probes, port-conflict terminal verdict, `terminal_verdict` in the status file, child output tee |
| `server/internal_event_client.py` | `own_health_payload`, narrowed proxy verdict, `record_undelivered_notification` |
| `server/run_watcher.py` | `_record_undelivered` on both failure paths |
| `server/chain_ingestion_worker.py` | sweep refreshes source tables too |
| `server/event_constants.py` | `EVENT_BROADCAST_RECOVERY` |
| `server/tests/test_duplicate_launcher.py` | new - (1)(2)(3)(4) |
| `server/tests/test_broadcast_recovery.py` | new - (5)(6) |
| `server/tests/test_process_supervisor.py` | one-line scope fix: the heartbeat guard searched the WHOLE launcher file for `run_graph_sync.py` and matched a new comment above `main()`. Now scoped to the spec list. |

Not touched: `server/main.py`, `server/database/crud.py`, the map-key/canonical-key
modules, `client2/`, `docs/`.

## Handover

**Not done, and deliberately.** `docs/` was out of scope for this lane. From
`DOC_OWNERSHIP.md`, the rows my code paths land in:

- row 36 (프로세스 감시·헬스: `process_supervisor.py`, `run_decoupled_app.py`) ->
  `architecture/backend.md §1.3`, `process/PRODUCTION_READINESS.md`. Needs: the
  port-conflict verdict as a third terminal state, `terminal_verdict` in
  `supervisor_status.json`, the new `*_stdout.log` files.
- row 33 / `guide/SERVER_STARTUP_GUIDE.md` -> the refusal, `--preflight-only`,
  and "if it refuses, the stack is already up; use it".
- row 51 (loopback IPC: `internal_event_client.py`) -> `architecture/PRIMITIVES §6`,
  `guide/DEPLOY_SETUP §1-5`, `qa/FEATURE_CHECKLIST §1.12/§2.16-D`. The documented
  rule "any HTTP status on /health means something in front of it answered" is now
  false and is quoted in more than one place.
- rows 46/55 (`event_driven_backend.md`, `chain_ingestion_guide.md`) -> the sweep's
  new target set and the BROADCAST_RECOVERY marker.
- `guide/DEPLOY_SETUP` / `ROLLBACK_PROCEDURE` -> the launcher can now exit 1
  before starting anything, which changes what a failed restart looks like.

**No restart is required for any of this**, but none of it is live until the
stack is restarted. When the lead PM decides to restart, the commands are:

```
taskkill /PID 12836 /T /F        # the launcher and its five children
conda activate assy_manager && python run_decoupled_app.py --server-only
```

(or `python run_decoupled_app.py --preflight-only` first, to confirm the ports
came free).

**Left alone, worth boarding.** `graph_sync_worker.py:1040` fires a
`batch_refresh_required` after a manual admin resync with no durable path - the
same class of loss as (6), but operator-triggered and visible, so it was out of
scope here. N1 (backfill paths emit zero notifications) is unchanged and nothing
in this change assumes those events exist: the sweep collects what is in the
outbox, and a table with no marker simply produces no refresh.

**Proposed lesson (server-pm memory)** - not added directly:

> **함정**: 공유 원인(correlated) 판정의 근거가 "DB 포트가 열려 있나" 하나뿐이면,
> **로컬 오설정(포트 점유)이 환경 장애로 오분류되어 무한 재시도**에 들어간다.
> 판정기의 외연을 넓히지 않은 채 "환경 장애면 계속 재시도" 정책만 넣으면, 그
> 정책이 잡아야 할 사고보다 잡지 말아야 할 사고를 더 많이 잡는다(74건 중 100%).
> **올바른 방법**: 재시도가 **원리적으로 해결할 수 없는** 원인(포트 점유, 설정
> 파일 부재 등)을 먼저 물어 종결 판정으로 보내고, "재시도하면 언젠가 낫는" 원인만
> correlated 로 남긴다. 두 분기는 **같은 픽스처에서 프로브 응답만 바꿔** 각각
> 증명한다.

> **함정**: 자식 프로세스의 stdout 을 캡처하지 않으면, 그 프로세스가 죽은 **이유**가
> 디스크 어디에도 남지 않는다(uvicorn 의 bind OSError 가 그렇다). 로그 파일이
> 다섯 개나 있어도 사고 재구성은 통계로 해야 한다.
> **올바른 방법**: 파이프 + 리더 스레드로 **콘솔과 파일 양쪽에 티** 한다
> (`stdout=<file>` 는 콘솔을 죽인다). 자식에는 `PYTHONUNBUFFERED=1` 필수 -
> 파이프로 바뀌는 순간 블록 버퍼링이라 결정적 한 줄이 버퍼째 사라진다.
