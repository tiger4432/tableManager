# QA Review B — Admin Shared-Token Gate: Operational Safety & Secret Leakage

**Reviewer:** qa-reviewer (adversarial) · **Date:** 2026-07-27 · **Scope:** uncommitted working tree
**Target:** `server/admin_auth.py` (new), `server/main.py`, `server/tests/test_admin_auth.py` (new),
`server/tests/conftest.py`, `server/tests/test_dev_env_isolation.py`, `client2/src/admin.js`, 8 living docs.

---

## 1. Verdict

**GO-WITH-FIXES** — the server-side gate is correct, well-tested and provably leak-free under live
runtime probing; but the admin bundle that production actually serves was never rebuilt, so an
operator who follows the new `DEPLOY_SETUP §1-4` will lock themselves out of the admin page with no
in-page recovery. F1 must land in this same commit.

---

## 2. What I ran vs. what I reasoned about

**Ran (measured):**

| # | Command / harness | Result |
|---|---|---|
| 1 | `PYTHONIOENCODING=utf-8 conda run -n assy_manager python -m pytest server/tests/ -q` | **668 passed, 0 failed**, 84.04s — baseline claim confirmed |
| 2 | Same, with `ASSY_ADMIN_TOKEN=Zq7-LEAKPROBE-4417` exported | **668 passed, 0 failed**, 82.67s — conftest pop works |
| 3 | Live uvicorn (`log_level="info"`, `access_log=True`) on :8099, sqlite + isolated `ASSY_DATA_ROOT`, 8 crafted requests, full stdout+stderr+`server.log` captured, scanned for a distinctive value | see §5 |
| 4 | Byte scan of the probe's sqlite DB (contains AuditLog + DatabaseOutbox rows from an **accepted** `reload-configs` and an **accepted** `scripts/code` write) | 0 hits for the token |
| 5 | `grep -rl LEAKPROBE probe_root/` (whole isolated data root incl. `server.log`) | 0 hits |
| 6 | Node harness: verbatim port of `adminFetch`/`askForAdminToken`/`withAdminToken` with a **blocking** modal stand-in and staggered response arrival | see F3 |
| 7 | `node --check client2/src/admin.js` | SYNTAX OK |
| 8 | Route inventory: `grep '^@app\.(get\|post)("/admin' server/main.py` | 16 API routes, all gated; 2 page routes exempt |
| 9 | `grep -c "X-Admin-Token" client2/dist/assets/admin-B35jOmmY.js` | **0** → F1 |

**Reasoned about (not executed):** real-browser task scheduling for the multi-prompt case (the Node
harness is a faithful port of the two functions, but Chrome's task-source priority is the variable);
Windows launcher env-var provisioning; behaviour of a non-ASCII token in a real browser (`fetch`
throws on non-ISO-8859-1 header values — inferred from spec, not measured).

---

## 3. Confirmed defects

### F1 · 심각도 높음 — The served admin bundle is stale; enabling the token bricks the admin page

`client2/dist/assets/admin-B35jOmmY.js` (git-**tracked**, unchanged in this diff, mtime 18:17 vs.
`client2/src/admin.js` 18:47) contains **zero** occurrences of `X-Admin-Token`. It has no
`adminFetch`, no prompt, no header. `client2/dist/admin.html` references exactly that bundle, and
`server/main.py:4001-4013` (`serve_admin_page`) serves `client2/dist/admin.html`.

**Failure scenario (input → wrong result):** operator follows `DEPLOY_SETUP §6` steps 7-8 — sets
`ASSY_ADMIN_TOKEN`, restarts, confirms the `[admin-auth]` banner is not a WARNING, gets `/health`
200. They open `/admin.html`. The old bundle fires 7 requests **with no header** →
7× `401` → every tab renders "❌ ... 로드 실패". **No prompt ever appears**, because the code that
prompts is not in the served file. There is no way to enter the token from the page. Recovery is
either unsetting the variable and restarting (undoing the security fix) or rebuilding and
redeploying the client. This is exactly the "잠긴 척하는 실패" that `PROJECT_STATUS` row 2 raised
the priority for, and it violates the "무중단에 가깝게" premise.

**조치:** `cd client2 && npm run build`, commit the regenerated `client2/dist/`, and gate on
`grep -c X-Admin-Token client2/dist/assets/admin-*.js` returning > 0. Add "클라이언트 빌드 재배포"
as an explicit step in `DEPLOY_SETUP §1-4` — the section currently never mentions it.

---

### F2 · 심각도 높음 — A wrong or cancelled token re-prompts every 30 seconds, forever

`client2/src/admin.js:240-247` installs `setInterval(..., AUTO_REFRESH_MS)` with
`AUTO_REFRESH_MS = 30000` (`admin.js:135`), which calls `fetchData({silent:true})` → 3-7
`adminFetch` calls. `adminFetch` (`admin.js:76-88`) prompts on 401/403, retries **once**, and then
returns the failed response. Nothing records "this token was rejected".

The cancel path is worse: `window.prompt` → `null` → `(entered || '').trim()` → `''` →
`storeAdminToken('')` **deletes** the stored token (`admin.js:22-27`) → `resolve('')` → `if (token)`
is false → no retry. Verified in the harness: cancelling yields `storedToken=""` and 7× 401.

**Failure scenario:** operator mistypes the token, or ops rotated it. A modal appears every 30
seconds in perpetuity on a foreground tab. Cancelling does not stop it — it *guarantees* the next
tick prompts again from scratch. The only exits are closing the tab or backgrounding it (the
`document.hidden` guard at `admin.js:242`).

**조치:** hold a session-scoped `tokenRejected` flag. Once a presented token comes back 403, stop
prompting from the background refresh path and surface a persistent inline banner with a
"토큰 재입력" action; prompt only from user-initiated calls.

---

### F3 · 심각도 중 — "7 concurrent 401s produce exactly 1 prompt" is timing luck, not structure

`askForAdminToken` (`admin.js:47-64`) defers the modal one tick so siblings can attach to
`tokenPromptInFlight`. But the flag is cleared **before** `resolve()`, so any response that lands
*after* the modal opened finds `tokenPromptInFlight === null` and opens a second modal.

Measured with a verbatim port of the three functions and a blocking modal stand-in:

| Response stagger | 30 ms modal | 2500 ms modal (realistic) |
|---|---|---|
| same tick | 1 prompt | 1 prompt |
| ~1 ms | 1 | 1 |
| ~5 ms | 1 | **2** |
| ~20 ms | **2** | **2** |
| ~60 ms | **3** | — |

On a real server `/admin/file-ingestion/failed?page=1&limit=100` and `/admin/mappers/list` (which
walks the mappers tree) will not land in the same millisecond as `/admin/chain/rules`.

**Failure scenario:** operator opens the locked page, gets a prompt, pastes the correct token — and
is immediately shown a **second** prompt reading "관리자 토큰이 거부되었습니다. 다시 입력해 주세요."
That message is false; the token was fine, the response merely predated it. The operator now
believes their token is wrong.

**조치:** carry a token *generation* counter. In `adminFetch`, capture the generation before the
request; on 401/403, if the generation has already advanced, retry silently instead of prompting.

---

### F4 · 심각도 중 — `adminFetch` swallows the 503, so the message written for the operator never arrives

`adminFetch` (`admin.js:76-88`) branches only on 401/403. A 503 falls through to callers, all of
which do `if (!res.ok) throw new Error(...)` and show a generic toast:
`saveScriptCode` (`admin.js:2397-2410`) → "❌ 코드 저장 중 오류 발생";
`runAutoUpdateNow` (`admin.js:1719-1740`) → "❌ 강제 수집 구동 요청 실패".

`admin_auth.py:70-73` carefully composes `_UNSET_DETAIL` naming `ASSY_ADMIN_TOKEN` and instructing a
restart — and the client discards it.

**Failure scenario:** operator restarts into the new build **without** setting the variable — the
deliberately-supported first-restart state — opens the code editor, edits a parser, clicks Save, and
gets a generic red toast. Nothing on screen mentions `ASSY_ADMIN_TOKEN`. They must read the server
log or the source. The whole point of the 503-split was operator self-diagnosis; the client defeats it.

**조치:** in `adminFetch`, on 503 parse `detail` and surface it in the toast (it is a constant
string, safe to display).

---

### F5 · 심각도 중 — A non-ASCII token can never authenticate, and the banner claims it is working

`configured_token()` (`admin_auth.py:78-89`) accepts any value after `.strip()`. `_matches`
(`admin_auth.py:92-101`) compares `presented.encode("utf-8")` against `expected.encode("utf-8")`,
where `presented` is what **Starlette decoded from the header as latin-1**.

**Failure scenario:** `ASSY_ADMIN_TOKEN=비밀번호1234`. Startup logs
`[admin-auth] ASSY_ADMIN_TOKEN is set - all /admin/* routes require the X-Admin-Token header`
(verified live, level `info`) — the operator believes they are configured. A browser cannot even
send the value (`fetch` rejects non-ISO-8859-1 header values). A curl client sends UTF-8 bytes →
Starlette latin-1-decodes → `_matches` re-encodes to UTF-8 → different bytes → **403, always**.
Every admin route is locked, including the two strict ones. Recovery is unset + restart.

**조치:** `configured_token()` should treat a non-ASCII value as a misconfiguration — either return
`None`, or (better) keep it configured but emit an ERROR-level banner naming the problem, so the
operator is not told "is set" about a token nothing can present.

---

### F6 · 심각도 낮음 — Windows `set VAR="abc"` keeps the quotes; `.strip()` does not remove them

`configured_token()` strips whitespace only. `cmd.exe`'s `set ASSY_ADMIN_TOKEN="abc"` produces the
literal value `"abc"` (PowerShell's `$env:` form does not). The operator then types `abc` at the
prompt and gets a 403 saying the token is wrong — true, but they will not guess why.

`DEPLOY_SETUP §1-4` shows only a bash-style `ASSY_ADMIN_TOKEN=<...>` fenced block; the production
host is Windows.

**조치:** document the Windows form explicitly (`setx` / `$env:`), and/or strip a single pair of
surrounding quotes in `configured_token()`.

---

### F7 · 심각도 낮음 — `devenv.py isolated_env()` does not neutralise the secret, but claims completeness

`server/scripts/dev_env/devenv.py:71-85`: `env = os.environ.copy()` under the docstring
*"The complete set of overrides that redirect a process away from production."* `ASSY_ADMIN_TOKEN`
is not in the override dict, so the isolated dev server on :8081 runs with the **production** admin
secret live in a second process.

Confirmed **not** a disk duplication: `_copy_tree` (`devenv.py:89-105`) copies `server/config/**`
only, the secret is env-only (no dotenv loading anywhere in `server/` — grepped), and `cmd_env`
(`devenv.py:335-340`) prints only values that differ from the ambient env, so it does not echo the
token. F1 also applies to the isolated server, which serves the same stale `client2/dist`.

**조치:** set a distinct dev value (or `""`) for `ASSY_ADMIN_TOKEN` in `isolated_env()`.

---

### F8 · 심각도 낮음 — `POST /admin/auto-update/toggle` is not strict, though it also makes the scheduler run a script

The stated rationale for `run-now` being fail-closed is "makes the scheduler run the named script"
(`main.py:3604-3606`). `toggle` (`main.py:3572`) flips a collector's `active` to `true`, which the
scheduler reads every cycle (its own docstring: "재기동 없이 핫 반영") — same end state, delayed by
one cron tick. On an unconfigured server it is open.

Genuinely low: the script is already on disk and cannot be written (the write route is 503). But the
asymmetry deserves either a one-line justification in `admin_auth.py`'s "The two states" section, or
`toggle` joining `STRICT_ADMIN_ROUTES`.

---

### F9 · 심각도 낮음 — Query-string tokens are rejected but still land in the console access log

Measured live: `GET /admin/chain/rules?token=Zq7-LEAKPROBE-4417` → correctly `401`, and uvicorn's
access line carries the full value:

```
INFO:     127.0.0.1:14096 - "GET /admin/chain/rules?token=Zq7-LEAKPROBE-4417 HTTP/1.1" 401 Unauthorized
```

It did **not** reach `server.log` (uvicorn.access does not propagate to the root logger that
`get_process_logger` decorates — verified: 0 hits in the file), and
`process_supervisor.py:360` `subprocess.Popen(spec.cmd, cwd=spec.cwd, env=merged)` does not redirect
child stdout, so it stays on the transient console. An operator who launches with `> out.log`
persists it. The code comment and `DEPLOY_SETUP §1-4` already warn against query params.
Not blocking; noted so the warning is understood to be load-bearing rather than decorative.

---

## 4. Hypotheses attempted and falsified — these are safe

| # | Hypothesis | Why it is safe |
|---|---|---|
| 1 | Context middleware picks up the token into audit rows | `main.py:59-73` reads only `X-User` / `X-Transaction-ID` / `X-Source` and their **query** fallbacks (`user`, `transaction_id`, `source`). `X-Admin-Token` shares no name and has no query fallback. |
| 2 | Token reaches an AuditLog row or an outbox payload | Byte-scanned the probe sqlite DB (1 MB, holds rows produced by an **accepted** `reload-configs` and an **accepted** `scripts/code` write): **0 hits**. |
| 3 | Token reaches the persisted log | `probe_root/server.log` contains `/admin` lines and the `[admin-auth]` banner but **0 hits** for the distinctive value. |
| 4 | Malformed header produces a traceback that renders the operand | Live `X-Admin-Token: pässwörd-9f3a` (as UTF-8 bytes) → clean `403`; **0 hits** for `9f3a` and `sswörd` across stdout+stderr+log. |
| 5 | Rejection bodies echo the presented or expected value | `_UNSET_DETAIL` / `_MISSING_DETAIL` / `_MISMATCH_DETAIL` are constants; confirmed in the live 401/403/503 bodies. |
| 6 | `reload-configs` re-reads the secret, or unloads the gate | `reload_local_process_cache` (`main.py:2860-2900`) pops only `pipeline_plugin_*` and mapper modules from `sys.modules`; `admin_auth` is untouched and `os.environ` is unchanged. No hot rotation is possible — `CONFIG_GUIDE` states this honestly. |
| 7 | An `/admin` route slipped through ungated | All 16 `@app.*("/admin/...")` decorators carry a gate. The only ungated registrations are `GET /admin` and `/admin.html` (`main.py:4001-4002`), one function serving HTML. `test_admin_auth.py` walks `app.routes` and the resolved `Dependant` tree, asserting a **set**, not a count. |
| 8 | `/health` got swept into the gate | Ungated; the live probe answered it with no header. |
| 9 | Whitespace-only / empty value creates a guessable secret | `configured_token()` strips and returns `None`; strict routes then 503 and an empty/whitespace header is not accepted. |
| 10 | Suite behaviour depends on whose shell it runs in | Ran the **whole suite with `ASSY_ADMIN_TOKEN` exported**: 668 passed, identical to the clean run. `conftest.py:17-26` pops it from the process env, so spawned subprocesses inherit the popped env too. |
| 11 | `devenv snapshot` duplicates the secret onto disk | Copies `server/config/**` via `shutil.copy2` only; no dotenv loading anywhere in `server/`. The secret exists only in process env. (See F7 for the in-process inheritance.) |
| 12 | `test_dev_env_isolation` now passes for the wrong reason | The `admin_client` fixture (`test_dev_env_isolation.py:41-49`) configures the env **and** attaches the header, so the request reaches the handler; the added `assert "isolated data root" in res.json()["detail"]` pins the 403 to the isolation guard, not to the gate. Both must hold and the suite is green — the guard is genuinely exercised. |
| 13 | Path/case tricks bypass the prefix check | FastAPI paths are case-sensitive (`/Admin/...` → 404) and `/admin/../admin/scripts/code` matches no route → 404. Redirect-slash variants re-present the same headers. |

Minor note on #12: `test_reads_still_work_when_isolated` (`test_dev_env_isolation.py:330-340`) still
uses the plain `client`, so that read is exercised only in the token-**unset** state. Acceptable —
`test_admin_auth.py::TestConfiguredTokenIsEnforced` covers the gated read — but it means the
isolation read path has no coverage under an enforcing gate.

---

## 5. Live runtime probe — full result

Real uvicorn, `log_level="info"`, `access_log=True`, distinctive token `Zq7-LEAKPROBE-4417`.

```
accepted   GET  /admin/chain/rules        200   (handler ran, real data returned)
missing    GET  /admin/chain/rules        401   {"detail":"관리자 토큰이 필요합니다."}
wrong      GET  /admin/chain/rules        403   {"detail":"관리자 토큰이 올바르지 않습니다."}
accepted   POST /admin/reload-configs     200   (writes an outbox row + audit context)
accepted   POST /admin/scripts/code       200   (strict route, real file written)
querystr   GET  /admin/chain/rules?token= 401   (rejected — but see F9)
non-ascii  GET  /admin/chain/rules        403   (no traceback, no echo)
           GET  /health                   503   (sqlite dialect artefact — ungated, as designed)

startup banner (level=info, verified in server.log AND stdout):
  [admin-auth] ASSY_ADMIN_TOKEN is set - all /admin/* routes require the X-Admin-Token header.

LEAK SCAN across stdout + stderr + server.log + the sqlite DB + the whole data root:
  'Zq7-LEAKPROBE-4417' : 1 hit  — the deliberate query-string request only (F9)
  '9f3a'               : 0 hits
  'sswörd'             : 0 hits
  in server.log        : 0 hits
  in probe.db          : 0 hits
```

**Conclusion on leakage: the header path is clean.** Not one accepted or rejected header-borne
request put the secret into a log line, an audit row, an error body, a traceback, or an outbox
payload. The only exposure is a hand-crafted query string, which the server rejects and the client
never produces.

---

## 6. Runtime verification still needed

1. Real-browser prompt count against a real server (the Node harness is a faithful port, but
   Chrome's task-source scheduling is the uncontrolled variable). Reproduce by throttling the
   network and opening `/admin.html` against a token-enabled server.
2. Whether the operator's actual launch method (a `.bat`, a service, a scheduled task) provisions
   `ASSY_ADMIN_TOKEN` in a form that survives reboot, and whether it introduces quotes (F6).
3. End-to-end behaviour after `npm run build` — F1 blocks any real verification of the client today.
4. WebSocket surface: the gate is HTTP-only. No WS route is under `/admin`, but confirm no WS
   message handler exposes admin-equivalent operations.

---

## 7. Documentation consistency

**Method:** located the changed code paths in `docs/process/DOC_OWNERSHIP.md` rather than trusting
the implementer's follow-up list. Rows :10 (`server/main.py` → SYSTEM_OVERVIEW), :15 (프로덕션 게이트
→ PRODUCTION_READINESS), :18 (백엔드 API → backend.md), :20/:34 (`client2/src/*`, 어드민 →
frontend.md), :36 (설정 → CONFIG_GUIDE) are all updated and accurate. Two rows are **not**:

### D1 · `docs/qa/FEATURE_CHECKLIST.md` — gap is real, route it
Zero occurrences of the token, the header, or any auth concept. §1.8 (lines 104-116) still describes
the admin dashboard as if there is no gate, and its `Last-verified` is `0f8d35f` (pre-change).
`DOC_OWNERSHIP:40` assigns it to doc-keeper, so the routing target is unambiguous. Confirmed worth
routing.

### D2 · `docs/architecture/CODE_MAP.md` — new module absent (not flagged by the implementer)
`grep -c admin_auth docs/architecture/CODE_MAP.md` → **0**; `adminFetch` → **0**. A whole new server
module (`server/admin_auth.py`) and a new client primitive are missing from the code map.
`DOC_OWNERSHIP:17` assigns CODE_MAP to code-mapper. The `admin.js` anchor is at
`CODE_MAP.md:729` and its line count (`~2,624줄`) is now stale (the file grew by 74 lines).

### D3 · `DEPLOY_SETUP §1-4` — self-sufficient on the server side, silent on the step that breaks things
An operator can configure the variable without reading source: the table, the banner excerpt and the
query-param warning are all good. But the section **never says the client bundle must be rebuilt and
redeployed**, which is the omission that makes F1 bite. Following §6 steps 7-8 exactly produces a
broken admin page. Also: "운영자가 할 일은 처음 한 번 붙여넣기뿐이다" is false against the shipped
bundle (no prompt at all) and optimistic even after a rebuild (F3, F4). The fenced example is
bash-form on a Windows host (F6). No rotation guidance — `CONFIG_GUIDE` is honest that a restart is
required, but `DEPLOY_SETUP` does not mention rotation at all.

### D4 · `PRODUCTION_READINESS` "C1 접근 통제 — ✅ 해소" overstates, on two counts
(a) The deployment path is broken (F1): the control exists but cannot be switched on without
breaking the admin UI. (b) The item is titled **접근 통제**, not **어드민 접근 통제**, and
`POST /internal/events/{batch-refresh,broadcast,file-processed,ingestion-state}`
(`main.py:3647`, `:3684`, `:3726`, `:3768`) remain **completely unauthenticated write surfaces** —
anyone who can route a packet can push arbitrary WebSocket broadcasts to every connected client, or
forge ingestion state. The section's "남는 것" note mentions only the bind address.
**조치:** retitle to "어드민 접근 통제", and name the `/internal/*` surface as a remaining item.

### D5 · `frontend.md` — "직렬화된다" reads stronger than it is
"프롬프트는 in-flight 프로미스로 **직렬화**된다" is accurate as a mechanism (one modal at a time)
but will be read as "one prompt total". Add a clause: responses that arrive after the modal opened
start a new one (F3).

**Accurate and worth keeping as-is:** `CONFIG_GUIDE`'s "⚠️ 예외: `ASSY_ADMIN_TOKEN`은 요청마다 다시
읽히지만, 프로세스 환경을 바깥에서 바꿀 수는 없으므로 운영상으로는 동일하게 재기동이 필요하다" —
this is exactly right and resists the obvious over-claim.

---

## 8. Proposed additions to `agent_workspace/memory/qa-reviewer.md`

(Proposal only — not written to the file, per the operating rule.)

- **함정:** 클라이언트 소스(`client2/src/`)만 검수하면 운영이 실제로 서빙하는 것을 놓친다.
  `client2/dist/`는 git 추적 대상이고 `main.py`가 그것을 서빙하므로, 소스가 고쳐져도 번들이
  낡으면 운영에서만 깨진다.
  **올바른 방법:** 클라 변경 검수 시 `grep -c "<새 문자열>" client2/dist/assets/<page>-*.js`로
  번들 반영 여부를 반드시 확인하고, `dist` mtime을 `src` mtime과 대조한다.
- **함정:** 비밀값 유출 검수에서 흔한 단어로 grep하면 정상 메시지에 걸려 판정이 무의미해진다.
  **올바른 방법:** 유출 프로브는 **구별 가능한 무의미 값**(예: `Zq7-LEAKPROBE-4417`)으로 하고,
  실제 uvicorn을 `--log-level info`(access log ON)로 띄워 stdout·stderr·`server.log`·DB 파일
  전체를 스캔한다. `warning` 레벨 실행은 아무것도 증명하지 않는다.
- **함정:** "동시 요청 N개가 프롬프트 1개를 만든다"는 주장은 코드만 보면 맞아 보인다.
  **올바른 방법:** 해당 함수를 그대로 포팅해 **응답 도착 시각을 흩뜨리고 모달을 블로킹으로**
  모사한 하네스로 최악값을 측정한다. 같은 틱에 몰리면 1개지만 5ms만 흩어져도 2개가 된다.

---

## 9. Fix priority

| Priority | Item | Blocking? |
|---|---|---|
| 1 | **F1** — rebuild + commit `client2/dist`, add the step to `DEPLOY_SETUP §1-4` | **Yes — must land in this commit** |
| 2 | F2 — stop the 30s refresh from re-prompting on a rejected token | Before production enablement |
| 3 | F4 — surface the 503 `detail` in the toast | Before production enablement |
| 4 | F3 — token generation counter | Should |
| 5 | F5, F6 — non-ASCII rejection + Windows env-var doc | Should |
| 6 | D1, D2 — route `FEATURE_CHECKLIST` (doc-keeper) and `CODE_MAP` (code-mapper) | Should |
| 7 | D3, D4, D5 — doc corrections | Should |
| 8 | F7, F8, F9 | Nice to have |
