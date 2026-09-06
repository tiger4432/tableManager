# 흐름 실측 F — ㉑ 접근 통제 · ㉓ 감독→재시작 정책 · ㉔ 자식 stdout→파일 · ㉕ 소급 실행 큐

> **작성:** Server PM (2차 실측) · **대상:** `docs/architecture/SYSTEM_FLOWS.md` §5 에 병합 (총괄이 병합)
> **칸 정의·채우는 규칙:** 그 문서 §1·§3 을 그대로 따름. 「지나가는 것」은 전선에서 잰 값, 「받는 쪽」은 데코레이터·시험·설정문자열을 뺀 소비자 수.
> **측정 기준:** 워킹트리 `main` @ 2026-09-06. ⛔ `.claude/worktrees/` · `.codex_tmp/` · `.test_tmp/` · `server/_archive/` · `node_modules/` 의 사본은 **한 건도 세지 않았다**.
> ⛔ **토큰 값은 이 라운드에서 한 번도 읽지 않았고 어디에도 인쇄하지 않았다.** 코드도 서버도 재기동하지 않았다.

---

## ㉑ 접근 통제 — 토큰 → 게이트 → 내부 IPC → 정적 서빙 봉쇄

**한 줄:** 게이트 자체는 이 저장소에서 «가장 잘 지켜지는» 이음매다 — 라우트 열거 시험이 커버리지를 «집합으로» 못 박고 있어서 새 라우트가 무방비로 나갈 수 없다. 어긋난 것은 전부 **그 게이트를 설명하는 문서와, 게이트를 통과하기 «전» 클라가 스스로 세운 관문**이다.

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| A-1 | 운영자 환경변수 | `admin_auth.configured_token()` (`:147`) | **요청마다** — import 시점이 아니라 호출 시점 | env 읽기 | `ASSY_ADMIN_TOKEN` strip. 공백만이면 `None`, **비-ASCII면 `None`**(latin-1 헤더를 못 통과하므로 「미설정」으로 착지) | **4** — `token_fingerprint`(`:195`) · `_enforce`(`:214`) · `internal_event_headers`(`:261`) · `startup_banner`(`:283`) | 시끄럽다 — 비-ASCII는 기동 배너가 `ERROR`, 미설정은 `WARNING`(무엇이 꺼지는지 «이름»으로) | ✅ 이어짐 |
| A-2 | `admin_auth.startup_banner()` | 웹서버 기동 로그 | 부팅 **1회** — `main.py:330-332` 이 `_admin_auth_banner_logged`(`:284`) 래치로 1회만 | 로그 | `(level, message)` 3상태 + **토큰 지문**(`sha256[:8]` \| `none` \| `unusable-non-ascii`) | 파일 1 (`server.log` + `server_stdout.log`, ㉔ 참조) | 시끄럽다 | ✅ 이어짐 |
| A-3 | 브라우저/워커 요청 | `_enforce(request, fail_closed)` (`:213`) | `/admin/*`·`/internal/*` 라우트 **54개** 진입마다 | HTTP 헤더 | 미설정+strict → **503** `_UNSET_DETAIL`(변수명·재시작을 문장으로) · 헤더 없음 → **401** `_MISSING_DETAIL` · 불일치 → **403** `_MISMATCH_DETAIL`. **401·403 둘 다 `WWW-Authenticate: X-Admin-Token`**(`_GATE_HEADERS`, `:101`). 비교는 `secrets.compare_digest`, 거부 detail은 **전부 상수**라 제시값을 되비추지 않는다 | 라우트 54 (데코레이터 등록이라 규칙상 «호출자»로 세지 않음) · 비라우트 호출자 **2**(`require_admin_token`/`_strict`) | 시끄럽다 — 상태코드 + 챌린지 헤더 둘 다 «기계 판독 가능» | ✅ 이어짐 |
| A-4 | `app.routes` 실측 | `ADMIN_GATES` 커버리지 | — | 라우트 테이블 | 🔴 **module-level `/admin/*` API 35** (`main.py`) + **`/admin/ontology-explorer/*` 15** (`ledger_api/ontology_config_explorer_router.py`, prefix 선언 `:17`) + **`/internal/events/* ` 4** = **54**. 면제는 «페이지 서빙 2»(`main.py:6193-6194`, 한 함수에 겹쳐 붙은 `@app.get("/admin")`·`@app.get("/admin.html")`) | **1** — `tests/test_admin_auth.py::TestEveryAdminRouteIsCovered`. ⚠️ 시험 전용이지만 «규칙 ②의 예외»다: 이 자리에선 시험이 «유일한 계측기»이고 그것이 설계다(문서 셋이 전부 그 시험을 정본으로 지목한다) | 시끄럽다 — 게이트 없는 라우트가 추가되면 스위트가 빨개진다 | ✅ 이어짐 |
| A-5 | strict 게이트 | `STRICT_ADMIN_ROUTES` | — | 라우트 테이블 | 🔴 **실측 12**: `POST /admin/scripts/code` · `POST /admin/auto-update/run-now` · `POST /admin/retroactive/{op}/run` · `POST /admin/ontology-explorer/{drafts,bootstrap,drafts/new}` · `PUT /admin/ontology-explorer/drafts/{draft_id}` · `POST .../drafts/{id}/{review,revise,activate}` · `DELETE .../drafts/{draft_id}` · `DELETE .../declarations/{target_key:path}` | 1 (시험이 **집합 동등**으로 단언 — 은퇴한 라우트가 목록에 남아도 빨개진다) | 시끄럽다 | ✅ 이어짐 |
| A-6 | 게이트 401 + 챌린지 | `admin.js isGateRejection`(`:106`) → `askForAdminToken`(`:117`) | 어드민 페이지의 첫 게이트 거부 | DOM `prompt` → `localStorage` | 판정은 **상태코드가 아니라 헤더**(`WWW-Authenticate` 값에 `X-Admin-Token` 포함, 대소문자 무시). 키는 `admin_token.js`의 `ADMIN_TOKEN_KEY='assy.adminToken'` **한 곳** | **1** — `adminFetch`(`admin.js:173`). 재시도 1회, 세대 카운터로 「in-flight 응답이 새 토큰을 고발」하는 것을 막는다 | 시끄럽다 — 503은 서버 본문을 그대로 토스트로 올린다(`:180-186`) | ✅ 이어짐 |
| A-7 | 그리드 페이지(`main.js`) | `/admin/retroactive/{op}/run` · `/admin/chain/rules` | 헤더의 「다시 돌리기」·규칙 목록 | HTTP 헤더 | 🔴 **`adminFetch` 를 «안 탄다»** — `readAdminToken()` 으로 읽어 `{[ADMIN_TOKEN_HEADER]: token}` 을 **손으로** 붙이는 raw `fetch` 2곳(`main.js:214`·`:241`). 프롬프트 없음 · 챌린지 헤더 판정 없음 · 503 처리 없음 | 2 | 🔴 **조용히 «틀린 사유»를 말한다** — 아래 §㉑-a | ⚠️ 반쪽 |
| A-8 | 런처 env | `internal_event_headers()` (`:252`) | 워커가 `/internal/events/*` 를 부를 때마다 | 함수 반환 dict | `{X-Admin-Token: <token>}` \| `{}`. 상속 경로는 `process_supervisor._default_spawn` 의 `os.environ.copy()`(`:632`) — 런처에 한 번 세팅하면 자식 전부가 받는다 | **2** — `chain_ingestion_worker.py:193` · `run_watcher.py:93` (⚰️ 세 번째였던 `graph_sync_worker` 는 은퇴) | 시끄럽다 | ✅ 이어짐 |
| A-9 | `/internal/events/*` 4xx | `admin_auth.internal_event_failure_note` | 통지 거부마다 | 로그 문자열 | 판별식은 **`WWW-Authenticate` 존재 여부** — 있으면 「우리 게이트」(지문 + 모집단별 REMEDY), 없으면 「앞단이 답했다」 | 2 (같은 두 발신자) | ⚠️ **로그뿐이고 그 로그의 종착지는 ㉔의 `*_stdout.log` + `<name>.log`** — 읽는 화면 0 | ⚠️ 반쪽 (㉔과 «같은» 사각) |
| A-10 | 임의 경로 GET | `main.py:6301 serve_static_or_index` | SPA catch-all | HTTP 응답 | ① 접두 그림자 목록 **10**(`tables`·`ws`·`audit_logs`·`dashboard`·`admin`·`map-editor`·`map_editor`·`map-presets`·`enrichment/`·`api`) → 404 ② `abspath(join(dist_base, file_name))` 결과가 `dist_base` 안인지 — **해결 «후» containment**. `os.path.join` 이 절대경로/드라이브상대 인자에서 베이스를 «버리기» 때문에 문자 블랙리스트로는 못 막는다 ③ 탈출은 **403이 아니라 404**(파싱됐다는 사실조차 확인해 주지 않는다) | 1 (catch-all 하나) | 조용 — 의도다. 탈출을 «구별 가능하게» 답하지 않는 것이 이 설계 | ✅ 이어짐 |
| A-11 | `app.mount("/assets", StaticFiles(...))` (`main.py:6191`) | — | — | mount | `route.methods` 가 `None` 이라 A-4 의 열거가 **건너뛴다**(시험 docstring 이 자기 입으로 적어 둔 KNOWN LIMIT) | — | — | ⚰️ **문서가 경고하는 사각의 «유일한 실물»이고, 그것은 `/admin`·`/internal` «밖»이다** — 즉 오늘 이 사각에 앉아 있는 게이트 대상 라우트는 **0** |
| A-12 | `@app.websocket("/ws")` (`main.py:3173`) | 브라우저 | WS 업그레이드 | WS | `dependencies=` 없음 | N (접속 클라) | ⚠️ 게이트 없음 | ⚠️ 반쪽 — **1차(⑦)에서 이미 보고됨.** 여기서는 ㉑의 «경계»로 다시 적을 뿐 새 발견이 아니다 |
| A-13 | `client2/src/admin_token.js` | 출하 번들 | `npm run build` | 번들 청크 | `X-Admin-Token`·`assy.adminToken` 이 **공유 청크 `admin_token-BrUpdOsE.js`** 로 갈려 나갔고, `admin-eErqdtgQ.js` 와 `main-M6juM_wA.js` 가 **둘 다 그것을 import** 한다 | 2 (두 진입 번들) | 🔴 **판정 «명령»이 무장 해제됐다** — 아래 §㉑-b | ⚠️ 반쪽 (배선은 온전 · 계측기가 거짓) |

### 🔴 §㉑-a — 클라가 서버보다 «먼저» 거절하고, 그 사유가 틀리다

```
서버의 전제   토큰이 «설정»돼 있으면 헤더 필수. 미설정이면 ordinary 게이트는 «열려» 있다
클라의 전제   localStorage 에 토큰이 «있어야» 부른다   <- main.js 만. admin.js 는 아니다
어긋나는 자리 「서버 미설정」 상태 하나
```
`main.js:238` `loadChainRuleNames()` 의 첫 줄이 `if (!token) return null;` 이다. `/admin/chain/rules` 는 **ordinary 게이트**라 미설정 서버에서 200을 답하는데, **클라가 물어보지도 않고 `null` 을 만든다.** 그 `null` 을 받는 `redo_banner.js:100 setRules` 는 주석에 이렇게 적어 두었다 — 「`null`(못 읽음)과 `[]`(선언에 없음)은 «다르게» 그립니다 — 합치면 403 과 빈 설정이 같은 픽셀이 됩니다」.
🔴 **그 결함이 한 층 위에서 그대로 재현된다**: 「이 브라우저에 토큰 없음」과 「403」이 같은 `null` 이 되고, **둘 다 실제로 일어난 일이 아니다**(서버는 답할 수 있었다).
⚠️ 같은 파일의 `runRetroactive`(`:212`)는 **strict 라우트**를 향하므로 미설정 서버에서 어차피 503이다 — 거절 자체는 옳고 **문구만** 틀리다(`'no admin token on this browser'`). 두 자리가 «같은 관문»을 공유하는데 정답이 서로 다르다.

### 🔴 §㉑-b — 판정 명령이 건강한 번들에서 «0»을 답한다

`docs/qa/FEATURE_CHECKLIST.md §1.12` 의 「서빙되는 것은 번들이다」 행이 판정으로 지목하는 명령을 **그대로** 돌렸다:
```
$ grep -c X-Admin-Token client2/dist/assets/admin-*.js
0
```
그런데 배선은 **온전하다**. 헤더 이름이 `admin_token.js` 로 분리되면서 vite 가 그것을 공유 청크로 뽑았고, `admin-eErqdtgQ.js` 와 `main-M6juM_wA.js` 가 **둘 다 `admin_token-BrUpdOsE.js` 를 import** 한다(번들 헤더의 import 문에서 실측). 즉 이 명령의 `0` 은 **「번들에 토큰 코드가 없다」가 아니라 「다른 청크에 있다」**이고, 체크리스트가 경고하는 사고(「토큰을 켜는 순간 어드민이 죽는다」)와 **같은 픽셀**이다.
📎 이건 「같아 보이는 다섯 개의 0」 중 **«갈려 나가서»** 부류다. 계측기가 자기 고장에서 눈이 먼 것이 아니라, **모듈을 하나 뽑은 옳은 리팩터가 계측기를 조용히 무장 해제했다.**

---

## ㉓ 감독 → 재시작 정책 — 자식 사망 → `_register_failure` → 포트/동료/DB → `supervisor_status.json`

**한 줄:** 판정 «본체»는 촘촘하고 순서까지 계약으로 적혀 있는데, **그 판정이 무엇을 근거로 났는지가 `/health` 로 가는 길에서 통째로 떨어진다** — 스냅샷 16칸 중 7칸이 복사되지 않고, 그중 둘(`terminal_verdict`·`correlated_evidence`)이 «판정 그 자체»다.

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| S-1 | 자식 프로세스 종료 | `Supervisor.poll_once`(`:957`) → `_register_failure`(`:781`) | **1초 폴**(`POLL_INTERVAL_SEC=1.0`) · `proc.poll()` 이 `None` 이 아님 | 함수 인자 | `(child, exit_code, reason)`. 🔴 **exit code 로 갈래를 틀지 않는다** — 파일 전체에 `code ==` 비교 0건. `code is None` 인지만 본다 | 1 | — | ✅ 이어짐 |
| S-2 | `_register_failure` | 예산 판정 | 매 사망 | 인메모리 | `uptime >= HEALTHY_UPTIME_SEC(60.0)` → `consecutive_failures=1` + **상관 흔적 3칸 초기화**, 아니면 `+1`. 예산 초과 조건은 `> MAX_CONSECUTIVE_FAILURES(5)` → **6번째에서 종단** | 1 | 시끄럽다 — 예산 안에서는 `WARNING` 한 줄 + `_record(restart_scheduled)` | ✅ 이어짐 |
| S-3 | 예산 소진 | `self.port_probe(child.spec)` (기본 `port_conflict`, `:423`) | 🔴 **판정 «첫째»** — 동료보다도, DB 프로브보다도 먼저 | 함수 반환 | `(conflict, detail)`. `detail` 은 점유 PID·프로세스명을 «이름으로» 댄다(`port_owner`, `:256`). 타임아웃 `PORT_PROBE_TIMEOUT_SEC=0.5` | 1 | 시끄럽다 — 프로브가 raise 하면 `WARNING` 후 **아무것도 판정하지 않는다**(종전 경로로 흐른다) | ✅ 이어짐 |
| S-3a | `ChildSpec.ports` | S-3 의 «도달 가능성» | — | 선언 | 🔴 **`ports=` 를 선언한 자식이 «하나»다** — `run_decoupled_app.py:312` 의 Backend FastAPI Server. 나머지 넷(watcher·chain·scheduler·desktop)은 `ports=()` 라 `if child.spec.ports:` 가 **거짓**이고 포트 프로브가 **돌지 않는다** | — | — | ⚠️ **`VERDICT_PORT_CONFLICT` 는 5자식 중 «1»에게만 도달 가능하다.** 그래프 워커(:8090) 은퇴로 둘이 하나가 됐다 |
| S-4 | 예산 소진, 충돌 없음 | `_peers_failed_recently`(`:738`) | S-3 이 거짓일 때 | 인메모리 dict | 창 `CORRELATION_WINDOW_SEC=120.0` 안에서 «다른» 자식의 **마지막** 실패만 센다(무한 성장 방지) | 1 | — | ✅ 이어짐 |
| S-5 | 동료가 부족할 때 | `self.environment_probe()` (기본 `shared_dependency_down`, `:224`) | 🔴 **`len(peers) + 1 < CORRELATED_MIN_CHILDREN(2)` 일 때만** — 즉 동료가 «하나도» 없을 때만 돈다 | TCP connect | `(down, detail)`. detail 실측 문자열: `"the database at {host}:{port} is not accepting connections ({ExcType})"`. URL 은 `paths.resolve_database_url()`, **stdlib `urlsplit`만** 쓴다(sqlalchemy 가 죽은 배포에서도 돌아야 하므로). sqlite·미설정·파싱 실패는 **모르면 healthy** | 1 | 시끄럽다 — raise 하면 `WARNING` 후 아무것도 판정 안 함 | ✅ 이어짐 |
| S-6 | 판정 = 상관 | `_enter_correlated`(`:910`) | `peers+1 >= 2` **또는** `env_down` | 인메모리 → 상태 파일 | `state=STATE_RETRYING_CORRELATED` · `correlated_with=peers` · **`correlated_evidence`** = 동료 문장 \| `env_detail` · `correlated_retries+=1` · `correlated_since`(첫 진입만) · `next_restart_at = now + 60.0`. **영구 실패시키지 않고 무한 재시도** | 1 | 시끄럽다 — 첫 진입은 `ERROR` 배너 7줄, 이후는 `ERROR` 한 줄 | ✅ 이어짐 |
| S-7 | 판정 = 종단 | `_fail_permanently`(`:859`) | 혼자 실패 \| 포트 충돌 | 인메모리 → 상태 파일 | `state=STATE_FAILED` · **`terminal_verdict ∈ {broken_child, port_conflict}`** · `failure_reason` 은 «평결마다 다른 문장»(포트면 detail + "permanent local misconfiguration…", 아니면 "exited N times in a row (last exit code X)…") | 1 | 시끄럽다 — `ERROR` 배너 9~11줄 + 한국어 조치문(`taskkill /PID …`) | ✅ 이어짐 |
| S-8 | `Supervisor.snapshot()`(`:1050`) | `<config>/supervisor_status.json` | `write_status(force)` — 상태 전이마다 `force=True`, 그 외 `STATUS_REFRESH_SEC=5.0` | 파일, `os.replace` **원자적** | 자식마다 **16칸**: `state·pid·heartbeat·restartable·restarts·consecutive_failures·uptime_seconds·last_exit_code·last_exit_at·seconds_until_restart·failure_reason·terminal_verdict·correlated_with·correlated_evidence·correlated_since·correlated_retries` + 최상위 `supervisor_pid·started_at·updated_at·stopping·failed_children·correlated_children·children·events` | 1 (`main.py:264 read_status()`) | 시끄럽다 — 쓰기 실패는 `ERROR`. `updated_at` 이 감독자 자신의 생존 신호 | ✅ 이어짐 |
| S-9 | 상태 파일 16칸 | `/health` `checks.supervisor.children.<n>` | `GET /health` | HTTP JSON | 🔴 **7칸만 복사**(`health.py:163-170`): `state·restarts·pid·last_exit_code·failure_reason·correlated_with·correlated_retries`. 별도로 워커 루프가 `heartbeat`(`:203`)와 `uptime_seconds`(`:229`) **2칸**을 더 쓴다 → **9/16** | 1 | — | ⚠️ 반쪽 |
| S-10 | `terminal_verdict` | `/health` · 화면 · 모니터 | — | — | `"broken_child"` \| `"port_conflict"` (`process_supervisor.py:867`, 스냅샷 `:1069`) | 🔴 **0** — `server/*.py` · `client2/{src,dist}` 전건에서 이 값으로 «분기»하는 코드 0. 히트는 정의 2 + 쓰기 2 + 스냅샷 1 + `tests/test_duplicate_launcher.py` **6** | 🔴 무음 (다만 아래 §㉓-a 참조 — 사실 자체는 «문장으로» 나간다) | 🔴 끊김 |
| S-11 | `correlated_evidence` | `/health` `problems[]` | — | — | 실측 두 모양: `"N other child(ren) failing within 120s (이름들)"` \| **`"the database at {host}:{port} is not accepting connections (…)"`** | 🔴 **0** — health 가 복사 목록에서 뺐고, 대신 «자기 문장»을 짓는다 | 🔴 **거짓말한다** — 아래 §㉓-b | 🔴 끊김 |
| S-12 | `restartable` · `consecutive_failures` · `last_exit_at` · `seconds_until_restart` · `correlated_since` | `/health` | — | — | 스냅샷에 쓰이는 5칸 | **0** (읽는 곳 없음) | 조용 | ⚠️ 반쪽 — 「없으면 무엇을 말할 수 없나」가 각각 다르다(§㉓-c) |
| S-13 | `_record(child, event, **fields)`(`:728`) → `snapshot()["events"]` | — | 상태 전이마다 | 파일(링버퍼 `MAX_EVENTS=100`) | `{ts, child, event}` + 이벤트별 필드. `permanently_failed` 에는 **`verdict=`** 가, `correlated_failure` 에는 `peers`·`evidence`·`attempt`·`retry_in_seconds` 가 실린다 | 🔴 **운영 소비자 0** — 히트는 `process_supervisor.py` 자신 4곳 + `tests/test_process_supervisor.py` 5곳. `health.py` 는 `events` 를 **한 번도 읽지 않는다** | 🔇 완전 무음 — 파일에 앉아 있고 아무도 안 연다 | 🔴 끊김 |
| S-14 | `failed_children` · `correlated_children` | `/health` `problems[]` + `status` | `GET /health` | HTTP JSON | 둘 다 «다른 처방»이라 리스트가 둘이다. `correlated` 를 `failed` **앞에서** 보고한다(운영자가 할 일이 다르므로) | 1 | 시끄럽다 — 둘 다 `UNHEALTHY` + 503 | ✅ 이어짐 |
| S-15 | `supervisor_status.json` | `config_backup` | 백업 잡 | 파일 복사 | `config_backup.py:129` 의 대상 목록에 이름이 있다 | 1 — 🔴 **읽는 것이 아니라 «복사»다.** 판정 소비자가 아니다 | — | ✅ (의도된 사본) |

### 🔴 §㉓-a — `terminal_verdict` 의 소비자 0 은 «빼기»가 아니라 «퍼뜨리기»다

KNOWN 을 **확인했다.** 다만 「소비자 0 = 값이 사라진다」로 읽으면 틀린다. 가르는 물음(「이 키가 «없으면» 무엇을 말할 수 없게 되나」)을 실제로 태웠다:
```
사람이 읽는 쪽   «말할 수 있다». `failure_reason` 이 복사되고, 그 문장이 평결마다 다르다
                포트 충돌: "<PID·프로세스명>. That is a permanent local misconfiguration…"
                고장난 자식: "exited N times in a row (last exit code X)…"
                -> health.py:196 이 그 문장을 그대로 problems[] 에 넣는다
기계가 읽는 쪽   «말할 수 없다». 두 평결을 가르는 «안정된» 값이 이것뿐이다.
                `failure_reason` 은 자유 문장이고 한국어 조치문까지 섞여 있어
                모니터가 그것을 정규식으로 가르는 순간 다음 문구 수정에서 죽는다
```
🔴 **그러므로 처방은 「7키 복사에 한 줄 추가」이고, 「지운다」가 아니다.** 그리고 2-bis 의 판별식(「`/health` 응답에 들어 있나」)으로 재면 이 항목은 **여전히 «아니오»**다.

### 🔴 §㉓-b — 「N children are failing together」가 «혼자 죽은 자식»에게 붙는다

`shared_dependency_down` 이 존재하는 이유가 docstring 에 적혀 있다 — **PostgreSQL 불통 콜드스타트에서 죽는 자식은 «정확히 하나»(웹서버)** 이고, 동료만 세는 규칙은 그것을 94초 뒤 영구 실패시킨다. 그 경로를 실제로 따라가면:
```
peers = []                      동료가 없다 (그것이 이 프로브가 존재하는 사유다)
env_down = True                 DB 포트가 안 열린다
_enter_correlated(peers=[])     correlated_with = []
                                correlated_evidence = "the database at host:5432 is not
                                                       accepting connections (…)"
supervisor_status.json          correlated_children: ["Backend FastAPI Server"]
                                children.<n>.correlated_with: []          <- 복사됨
                                children.<n>.correlated_evidence: "…DB…"  <- 🔴 «안» 복사됨
/health problems[]              "1 children are failing together (Backend FastAPI Server)
                                 - treated as a shared-cause outage. … Check the database,
                                 the disk and the network first."
```
🔴 **감독자는 「DB 가 host:5432 에서 연결을 안 받는다」를 «이미 알고 있는데»**, `/health` 는 **「셋 중 하나를 찾아보라」**고 답한다. 그리고 같은 응답 안에서 `correlated_with: []` 가 「아무와도 상관 없음」이라고 말해, 「함께 실패 중」이라는 문장과 **서로 어긋난다.**
⚠️ 이건 「값이 없어서 0」이 아니라 **「값이 있는데 안 실려서 0」**이다 — 문장 하나 고치는 문제가 아니라 «복사 목록»의 문제다.

### §㉓-c — 안 복사되는 다섯의 「없으면 못 하는 말」

```
consecutive_failures   「예산 몇 개 남았나」 -> 영구 실패가 «임박»했는지 못 본다 (지금은 실패한 뒤에만 안다)
seconds_until_restart  「언제 다시 뜨나」   -> backoff 중인 자식이 down 과 «같은 픽셀»이다
correlated_since       「얼마나 오래」      -> 상관 재시도는 «무한»이라 시작 시각이 유일한 진척 축이다
last_exit_at           「언제 죽었나」      -> restarts 수는 «누적»이라 지금 진행 중인지 못 가른다
restartable            「이건 죽으면 전체 종료」 -> 데스크톱 셸의 down 이 워커 down 과 같아 보인다
```
🔴 다섯 다 「빼기」가 아니라 「퍼뜨리기」 쪽으로 보인다 — 다만 우선순위는 §㉓-a·b 뒤다.

---

## ㉔ 자식 stdout → 파일

**한 줄:** 다른 흐름 넷의 「끊기면 시끄럽다」가 **전부 이 파일로 떨어지는데**, 이 파일을 여는 코드가 저장소 전체에 **0개**다. 그리고 같은 경계에 **모양이 둘**이다.

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| C-1 | `ChildSpec(log_file=)` | `Supervisor._default_spawn`(`:631`) | 자식 spawn 마다 | `subprocess.Popen` 인자 | `log_file` 이 «있으면» `stdout=PIPE, stderr=STDOUT` + `merged.setdefault("PYTHONUNBUFFERED","1")`. 🔴 **버퍼 해제가 장식이 아니다** — 파이프에서 CPython 이 블록 버퍼링하면 이 캡처가 존재하는 사유인 «bind 에러 한 줄»이 8 KB 버퍼에 앉은 채 프로세스가 죽는다 | 1 | — | ✅ 이어짐 |
| C-2 | `run_decoupled_app.py` | `log_file=` 선언 | 부팅 | 선언 | 🔴 **실측 5**: `server_stdout.log`(`:313`) · `watcher_stdout.log`(`:317`) · `chain_worker_stdout.log`(`:328`) · `auto_update_stdout.log`(`:331`) · `desktop_client_stdout.log`(`:338`, `--server-only` 가 아닐 때만) | 1 (`Supervisor`) | — | ✅ 이어짐 |
| C-3 | 자식 파이프 | `_attach_log_pump`(`:647`) | `_start(child)` 직후 | 데몬 스레드 `logpump-<name>` | 헤더 `=== <name> started <YYYY-mm-dd HH:MM:SS> pid=<pid> cmd=<…> ===` (UTF-8), 그다음 **`iter(stream.readline, b"")` 바이트 그대로** — 디코드 «없음». 줄마다 파일 `flush()`, 그리고 `sys.stdout.buffer` 로 tee. 🔴 **바이트 통과가 설계다**: 자식이 cp949 로 찍어도 재해석하지 않으므로 디코드 예외로 «줄이 사라질» 수 없다 | 1 | ⚠️ 캡처 실패는 `WARNING` 한 줄 + 자식은 계속 돈다(치명적이지 않음). 다만 **그 이후 그 자식의 출력은 파일에 «안 남는다»** | ✅ 이어짐 |
| C-4 | 누적 바이트 | 회전 | `written > CHILD_LOG_MAX_BYTES(20 MiB)` | 파일 rename | `os.replace(path, path + ".1")` — 백업 «하나». 즉 자식당 최대 **40 MiB**. rename 실패는 `except: pass` 후 원본을 다시 열어 «출력을 버리지 않는다» | 1 | 🔇 **조용** — 회전도, 회전 실패도 로그가 없다. 20 MiB 이전 내용은 `.1` 로 밀리고 그다음 회전에서 «말없이» 사라진다 | ⚠️ 반쪽 |
| C-5 | `*_stdout.log` | **화면 · 라우트 · 스크립트** | — | — | — | 🔴 **0.** 저장소 전건 grep(`--include=*.py,*.js,*.mjs,*.bat,*.ps1,*.html`, 아카이브·워크트리 제외)에서 이 이름을 언급하는 «비-쓰기» 히트는 `process_supervisor.py:99` docstring 과 `tests/test_duplicate_launcher.py:435` 픽스처뿐. **여는 코드 0** | 🔴 **완전 무음** — 이 흐름의 마지막 홉이 없다 | 🔴 끊김 |
| C-6 | 같은 프로세스의 `logging` | `<name>.log` | `get_process_logger(name, file)` | 파일 핸들러 | 🔴 **두 번째 싱크다.** `utils/logger.py:244-270` 이 루트 로거에 `ConsoleSafeHandler(sys.stdout)` **와** `FileHandler(paths.log_path(file))` 를 «둘 다» 단다. 호출 5: `Server/server.log` · `Chain/chain_worker.log` · `Scheduler/auto_update.log` · `Watcher/watcher.log` · `Launcher/launcher.log` | 파일 5 | — | ✅ 이어짐 |
| C-7 | C-5 와 C-6 의 «차집합» | — | — | — | 🔴 **`logger.*` 로 나간 줄은 «두 파일»에 남는다**(콘솔 핸들러 → stdout → 파이프 → `*_stdout.log`, 그리고 파일 핸들러 → `*.log`). **로깅을 안 타는 출력은 «한 파일»에만 남는다** — uvicorn 자기 배너, 미처리 traceback, 맨 `print`, **그리고 bind `OSError`** | — | 🔴 **그 한 파일이 읽는 쪽 0 인 쪽이다.** ㉓-S3a 의 포트 충돌 판정이 74건의 «통계»로 재구성돼야 했던 사유가 이것이고, 캡처가 생긴 뒤에도 «읽는 자리»는 안 생겼다 | 🔴 끊김 |
| C-8 | `/admin/chain/queue` | 화면 | 어드민 폴링 | HTTP JSON | `log_filename` — **로거에서 «읽어»** 보낸다(`main.py:3927-3932`, 상수로 적으면 거짓이 되므로). ⚠️ **이름이지 경로도 내용도 아니고, 가리키는 것은 C-6 계열(`chain_worker.log`)이지 C-5 계열이 아니다** | **1** — `chain_queue_panel.js:191-193`(`'log_filename' in payload` 로 «키 없음»까지 3상태) | 시끄럽다 | ✅ 이어짐 — 🔴 **다만 「가장 가까운 독자」가 «다른 파일 가족»에 대해 답한다** |
| C-9 | `devenv.py:290` | `dev_env/logs/watcher_stdout.log` | `devenv.py watcher-up` | `Popen(stdout=f, stderr=f)` | 🔴 **같은 이름 규약, 다른 기제.** 펌프 없음 · 헤더 없음 · **회전 없음** · 콘솔 tee 없음 · 바이트 통과는 우연히 같음(파일 핸들 직결) | 0 (읽는 쪽 없음) | 🔴 무음 + **무한 성장** | ⚠️ 반쪽 — 「한 경계에 모양이 둘」 |

### 🔴 ㉔ 의 핵심 — 「시끄럽다」가 «어디서» 시끄러운지 이 문서가 처음 답한다

1차 실측의 「끊기면」 칸에서 **파일이 종착지**라고 적힌 자리를 이 흐름이 받는다:
```
⑤ 거절     gate.py 의 REFUSED 경고           -> auto_update_stdout.log  (소급 백필은 스케줄러 스레드)
⑥ 관측     데몬 기동 배너 · 프록시 요약        -> 각 데몬의 *_stdout.log
⑦ 통지     internal_event_failure_note 401/403 -> chain_worker_stdout.log · watcher_stdout.log
㉑ 접근통제  admin-auth 배너 (지문 · 3상태)      -> server_stdout.log
㉓ 감독     ERROR 배너 9~11줄 (평결 · 조치문)    -> launcher 콘솔 + launcher.log  ← ⚠️ 예외
```
🔴 **㉓만 다르다** — 감독자 배너는 «런처 자신»이 찍으므로 `launcher.log` 로 가고, 자식 `*_stdout.log` 로는 안 간다. 즉 「자식이 왜 죽었나」(자식의 stdout)와 「감독자가 무엇이라 판정했나」(런처의 로그)가 **다른 파일**에 있고 **둘 다 읽는 화면이 0**이다.
📎 그래서 ㉔은 「로그 파일 하나」가 아니라 **이 저장소의 모든 「조용하지 않다」 주장의 «공통 종착지»**이고, 그 종착지에 문이 없다.

---

## ㉕ 소급 실행 큐 — `POST /admin/retroactive/{op}/run` → outbox → 스케줄러 → 스레드 → 실행 행 → 화면

**한 줄:** 큐 자체는 **닫혀 있다** — 발행이 한 커밋이고, 줍는 쪽이 at-most-once 이고, 못 파싱한 요청이 뒤를 막던 사고까지 수리돼 있다. 끊긴 것은 **결과의 마지막 홉**이다: `result` 도 `error` 도 화면이 **한 글자도 안 읽는다.**

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| R-1 | 브라우저/curl | `main.py:5511 trigger_retroactive_run` | **`POST /admin/retroactive/{op}/run`**, `Depends(require_admin_token_strict)` | HTTP 바디 | `{"params":{…}, "requested_by": …}`. 🔴 **`requested_by` 를 «지어내지 않는다»** — 없으면 `None`(「admin」은 사람 이름처럼 읽히는 글자다) | 라우트 1 · 클라 발신 **2**(`admin.js:3282` · `main.js:214`) | 🔊 `RetroactiveRefused` → **400** · 그 외 → **500** · 토큰 미설정 → **503** | ✅ 이어짐 |
| R-2 | `retroactive.publish`(`:1288`) | `database_outbox` **+** `retroactive_runs` | R-1 과 같은 요청, 동기 | DB 행 ×2, **한 커밋** | `DatabaseOutbox(event_uuid, table_name="__retroactive__", event_type="RETROACTIVE_RUN", payload={run_id(12자리 hex), op, params, requested_by}, processed_chain=False)` + `RetroactiveRun(run_id, op, params, requested_by, state="queued")`. 🔴 **한쪽만 있으면 둘 다 없느니만 못하다**(이벤트만 = 보이지도 취소도 안 되는 잡 / 행만 = 영원히 `queued`) | 1 (`publish` 가 유일 writer) | 행은 🔊(durable) | ✅ 이어짐 |
| R-3 | 같은 세션 | `NOTIFY outbox_event;` | R-2 커밋 직후, **두 번째 커밋** | PG NOTIFY | `text("NOTIFY outbox_event;")` | 1 (`OutboxListener`) | 🔇 **무음** — `except → logger.debug`. 유실의 증상은 데이터 손실이 아니라 **다음 틱까지의 지연** | ⚠️ 반쪽 (⑦의 같은 부류) |
| R-4 | outbox 행 | `run_auto_update.handle_retroactive_trigger`(`:811`) | **스케줄러 틱** — `PICKER_INTERVAL_SECONDS = 5` | DB SELECT | `event_type == EVENT_RETROACTIVE_RUN AND processed_chain == False`, `ORDER BY id ASC LIMIT 1`. 🔴 **`retroactive_busy()` 가 참이면 질의 자체를 «안 한다»** | 1 | — | ✅ 이어짐 |
| R-5 | `start_retroactive_run`(`:758`) | 스레드 `retroactive-run` (daemon) | R-4 | `threading.Thread` | 🔴 **인라인으로 돌리면 안 되는 사유가 계약이다** — 스케줄러의 `heartbeat.beat("scheduler")` 가 틱마다인데 `DEFAULT_STALE_AFTER_SEC=60` 이라, 인라인 실행은 **`/health` 가 이 데몬을 `wedged` 로 신고하게 만든다**. 즉 「운영자가 제안받은 버튼을 누르면 모니터링이 죽는다」 | 1 | 🔊 스레드가 raise 하면 `logger.error(exc_info=True)` (최후 방어) | ✅ 이어짐 |
| R-6 | 이미 실행 중 | 거절 | `retroactive_busy()` 참 | 로그 + 미처리 행 | `logger.warning("[Retroactive] a run is already in flight (%s, %s); leaving run_id=%s queued for a later tick")` — **in-flight 실행의 `run_id·op·moving·no_progress_seconds` 를 이름으로 댄다**(`retroactive_moving_state()` → `in_flight()`). 행은 **미처리로 남아 다음 틱 재시도** | 파일 1 (`auto_update_stdout.log` · `auto_update.log`, ㉔) | ⚠️ 조용 — 화면은 `queued` 로 보고 그것이 «옳다». 다만 **왜** 기다리는지는 R-11 이 별도로 답한다 | ✅ 이어짐 |
| R-7 | 처리 «전» 마킹 | `processed_chain = True` | `start_retroactive_run` 이 `True` 를 반환한 «직후» | DB UPDATE | 🔴 **at-most-once 가 «고른» 보증이다** — 실행이 여러 틱을 넘겨 살아 있으므로 끝난 뒤 마킹하면 같은 행을 다시 주워 잡을 두 번 돌린다 | 1 | — | ✅ 이어짐 |
| R-8 | 파싱/처리 예외 | `status="FAILED"` + `processed_chain=True` | R-4 의 `except` | DB UPDATE + 로그 | `logger.error("… (outbox#%s, run_id=%s, op=%s); marking it FAILED so the requests behind it can run: %s")` — **행·실행·연산을 이름으로, 페이로드 본문은 «안» 찍는다**(운영 데이터). 마킹까지 실패하면 두 번째 `ERROR` | 파일 1 | 🔊 **그리고 이 자리가 «닫힌» 자리다** — 2026-09-04 에 파싱 안 되는 행 하나가 `ORDER BY id ASC` 로 영원히 첫째가 되어 **뒤의 모든 소급 요청을 막았고 아무것도 raise 하지 않았다** | ✅ 이어짐 (수리됨) |
| R-9 | `retroactive.execute`(`:1343`) | `retroactive_runs.state` | 스레드 시작 | DB UPDATE (**자기 세션**) | `_mark_run(RUNNING, started=True)` → `started_at`·`last_progress_at`·**`runner = host/pid`**. 종료 시 `DONE` \| `CANCELLED` \| `FAILED` + `result` \| `error`(2000자 절단). 🔴 **취소와 완료는 다른 결말이다** — 취소를 `done` 으로 적으면 「전 테이블을 덮었다」고 말하는 것 | 1 | 🔊 **행 갱신 실패는 `ERROR` + 카운트**(`_record_failure`) — 「일은 도는데 행이 그것을 더는 설명하지 않는다」. `debug` 가 아닌 이유가 주석에 실측(2026-09-05, `runner` 컬럼 마이그레이션 미적용 → 모든 UPDATE 가 `UndefinedColumn`) | ✅ 이어짐 |
| R-10 | `_run_ledger_backfill`(`:381`) | `RetroactiveRun.result` JSON | `OPERATIONS["ledger_backfill"]["run"]` | 함수 반환 | 🔴 **7칸만 통과**: `rows_read·batches·inserted·deduped·molecules·stopped·cursor_after`. `backfill.run` 이 `:544-547` 에서 채우는 **`refused_total`·`refused_samples`·`refused_samples_capped` 는 여기서 버려진다** | 1 (`execute` → `_mark_run(result=)`) | 🔇 무음 | 🔴 끊김 (KNOWN **확인**) |
| R-11 | `retroactive.queue_view`(`:780`) | `/admin/chain/queue` 응답 | 어드민 폴링 | HTTP JSON | 9칸: `last_pickup_at`·`last_pickup_age_seconds`·**`picker_interval_seconds`(5)**·`stall_after_seconds`·`waiting_count`·`waiting[]`(`run_id·op·requested_by·queued_at·waiting_seconds·**ahead**`)·`orphaned[]`·`record_failures[]`. 🔴 **`last_pickup` 이 첫 칸인 것이 실측의 결론이다** — 대기가 두 봉우리(3.0s · 320.5s)라 큐 «길이»로는 「곧 돈다」와 「아무도 안 줍는다」가 안 갈린다 | **8/9** — `pickup_state.js`(`:40-77`) + `chain_queue_panel.js`(`:125·242·391·394`) | 시끄럽다 | ⚠️ 반쪽 |
| R-12 | `record_failures` | 화면 | — | — | 🔴 **「아래의 수들이 틀렸을 수 있다」는 플래그.** 코드 주석이 자기 사유를 적어 뒤 — 「Published as a value, not left in a log」 | 🔴 **0** — `client2/src` 히트 **0** · `client2/dist` 히트 **0** | 🔴 무음 — **로그에 안 두려고 값으로 냈는데, 값을 아무도 안 읽어 결국 로그로 돌아갔다** | 🔴 끊김 |
| R-13 | `retroactive.runs`(`:1127`) | `/admin/retroactive/runs?limit=50` | `admin.js:2551 refreshRunning` (3s busy / 30s idle 폴링) | HTTP JSON | **14칸**: `run_id·op·label·params·requested_by·state·processed_rows·total_rows·result·error·queued_at·started_at·last_progress_at·finished_at`. `total_rows` NULL 은 **0 이 아니라 모름**으로 나간다 | 1 (`admin.js`) | 🔊 못 읽으면 `failedSources` 로 **이름 대어** 말한다(빈 배열로 접지 않는다) | ⚠️ 반쪽 |
| R-14 | 위 14칸 | 픽셀 | `retroactive_view.js:409 buildRunsView` | DOM | 🔴 **10칸만 읽는다**: `state`·`finished_at`·`started_at`·`queued_at`·`run_id`·`label`·`op`·`params`·`processed_rows`·`total_rows` | 1 | — | ⚠️ 반쪽 |
| R-15 | `result` (연산이 돌려준 수 전부) | 픽셀 | — | — | `{rows_read, batches, inserted, deduped, molecules, stopped, cursor_after}` | 🔴 **0.** `client2/{src,dist}` 전건에서 `batches`·`cursor_after`·`refused_total`·`refused_samples` 히트 **0**. `rows_read`·`deduped`·`molecules` 히트는 **전부 다른 표면**(`ledger_sources_panel.js` 의 `/admin/ledger/sources` 커서칸 · `ontology_explorer_*` 의 시험 실행 미리보기)이고 실행 행과 무관하다 | 🔴 **완전 무음** | 🔴 끊김 |
| R-16 | `error` (최대 2000자) | 픽셀 | `state=failed` | — | `_mark_run(error=str(e)[:2000])` | 🔴 **0.** `buildRunsView` 는 `run.error` 를 안 읽고 `renderRunning`(`admin.js:2614`)도 안 그린다. **실패한 실행은 「끝난 회색 줄 + state=failed」로만 보이고 사유가 화면 어디에도 없다** | 🔴 **완전 무음** | 🔴 끊김 |
| R-17 | `requested_by` · `last_progress_at` | 픽셀 | — | — | 「누가 걸었나」 · 「마지막 진척 시각」 | 🔴 **0** (`runs()` 경로). ⚠️ 다만 `requested_by` 는 **`queue_view.waiting[]` 을 통해 R-11 쪽으로 «다른 화면»에 도착한다** — 즉 같은 사실이 한 화면엔 가고 한 화면엔 안 간다 | 조용 | ⚠️ 반쪽 |
| R-18 | `POST /admin/retroactive/runs/{run_id}/cancel` | `RunControl` | 화면의 `×` | HTTP → DB 값 | 값 하나를 세울 뿐 **프로세스를 죽이지 않는다**. 연산이 배치 «사이»에서 그 값을 본다. `cancellable:false` 인 연산에는 화면이 `×` 를 «안 그린다»(`retroactive_view.js:443`) | 1 (`admin.js:2599`) | 🔊 이미 끝난 실행은 **이름으로 거절**(끝난 것에 「취소됨」을 주면 운영자가 「반만 처리됐다」로 읽는다) | ✅ 이어짐 |

### 🔴 §㉕-a — 거절 흐름의 청중은 **거절 이전에** 이미 눈을 감고 있다

1차(⑤)의 판정은 「`_run_ledger_backfill` 이 7키만 복사해 거절 셋을 떨어뜨린다」였다. **확인했다 — 그리고 그것으로 끝이 아니다.**
```
자리 ①   backfill.run 의 10칸 -> _run_ledger_backfill 이 «7칸»만 복사     (R-10, KNOWN)
자리 ②   그 7칸이 RetroactiveRun.result 로 durable 하게 앉는다             (R-9)
자리 ③   GET /admin/retroactive/runs 가 그 result 를 «그대로» 실어 보낸다   (R-13)
자리 ④   🔴 화면이 result 를 «한 번도 안 읽는다»                            (R-14·R-15)
```
🔴 **자리 ①을 고쳐도 픽셀은 «안 바뀐다».** 열 칸을 다 복사해도 `buildRunsView` 가 `run.result` 를 안 보므로 화면은 여전히 「분자 N개」조차 말하지 않는다 — 사실 그것도 안 말한다. 화면이 실행 행에서 그리는 수는 `processed_rows`/`total_rows` **둘뿐**이고, 그 둘은 `RunControl` 이 별도로 찍는 값이지 `result` 가 아니다.
⚠️ **그러므로 이 흐름의 「받는 쪽 0」은 «한 칸»이 아니라 «칸 전체»다.** 수리 순서를 자리 ①부터 잡으면 «착지했는데 배선 0» 이 된다 — 자리 ④가 먼저다.

### 🔴 §㉕-b — 실패한 실행이 «왜» 실패했는지 화면에 없다

`error` 는 durable 하고, 라우트가 싣고, 2000자까지 보존된다. **그런데 화면이 안 읽는다.** 즉 운영자가 보는 것은:
```
[레이블 · 파라미터]  [—]  (회색 줄, × 없음)      state="failed"
```
`state` 자체도 픽셀에 «글자로» 안 나온다 — `renderRunning` 은 `is-finished` **CSS 클래스**로만 구분한다. 사유를 알려면 `auto_update_stdout.log` 를 열어야 하고, **그 파일은 ㉔에서 읽는 쪽 0 이다.** 두 흐름의 사각이 여기서 만난다.

### §㉕-c — 이 큐의 상태를 답하는 라우트는 «체인» 라우트다

`queue_view`·`in_flight` 는 `GET /admin/chain/queue`(`main.py:3724`)의 응답 안 `owners[scheduler].queue`·`.blocked_by` 로 나간다. 소급 실행 «목록»은 `GET /admin/retroactive/runs`, 소급 실행 «큐 상태»는 `GET /admin/chain/queue` — **한 흐름이 라우트 둘에 걸쳐 있고 그중 하나는 다른 흐름의 이름을 달고 있다.**
🔴 **그래서 이것이 «별도 흐름»이다** — 인벤토리에서 ⑧(스케줄러) 안에 접혀 있는 동안, 이 큐가 「누가 줍고 있나」에 답하는 자리가 체인 쪽에 있다는 것이 아무 표에도 안 적혔다.

---

## 🔴 이 라운드가 «찾은» 것 — 인벤토리에도 §2 목록에도 없던 흐름

| # | 흐름 | 왜 «별도» 흐름인가 |
|---|---|---|
| ㉗ | **프로세스 로깅 두 가족** | `*_stdout.log`(감독자 tee)와 `*.log`(`logging.FileHandler`)는 **다른 기제·다른 내용·다른 실패 모드**다. 「로그에 남는다」는 문장이 어느 가족을 뜻하는지에 따라 참·거짓이 갈린다(㉔-C7). 그리고 **`/admin/chain/queue` 의 `log_filename` 은 «둘째 가족»의 이름만 답한다** — 유일한 독자가 다른 파일에 대해 말한다 |
| ㉘ | **그리드 페이지의 어드민 토큰 경로** | `admin.js` 의 `adminFetch` 와 «별개»다 — 프롬프트도, 챌린지 헤더 판정도, 503 처리도 없다. 같은 토큰, 다른 관문, **다른 답**(㉑-a). 인벤토리는 「클라 토큰 흐름」을 «하나»로 적고 있다 |

🔴 **판별식(§2 「한 기능 안에서 다른 물음에 답하는 경로」)이 이번에도 둘을 잡았다.** 둘 다 「같은 이름의 것이 둘」이고, 둘 다 **둘째가 첫째의 규율을 안 물려받았다.**

---

## ⚠️ 낡은 서술 — 「상태」 칸에 담을 문서 정정 (실측 대조)

| 자리 | 적혀 있는 것 | 실측 | 무게 |
|---|---|---|---|
| `docs/qa/FEATURE_CHECKLIST.md §1.12` | 「**strict 3라우트**(`/admin/scripts/code` · `/admin/auto-update/run-now` · `/admin/retroactive/{op}/run`)」 | **12** — 온톨로지 작성 라이프사이클 9개가 더 붙었다 | ⚠️ 낮음 — **같은 행이 「목록의 정본은 `test_admin_auth.STRICT_ADMIN_ROUTES`」라고 «이미» 적어 두었고 그 시험은 최신이다.** 수만 낡았다 |
| 같은 곳 | 「`/admin/*` API 라우트 전부(2026-07-31 실측 **22개**)」 | module-level 35 + 라우터 15 = **50** (+ `/internal` 4 = 54) | ⚠️ 낮음 — 「이 수는 커밋마다 낡는다」가 바로 아래 줄에 적혀 있다 |
| 같은 곳, 「서빙되는 것은 번들이다」 행 | 판정: `grep -c X-Admin-Token client2/dist/assets/admin-*.js` | 🔴 **건강한 번들에서 `0` 을 답한다** — 이름이 공유 청크로 갈렸다(§㉑-b) | 🔴 **높음 — 계측기가 거짓 경보를 낸다.** 판정 대상은 `client2/dist/assets/admin_token-*.js` 이거나, 더 낫게는 「`admin-*.js` 가 `admin_token-*.js` 를 import 하는가」 |
| `docs/architecture/CODE_MAP.md §1.6` | `require_admin_token` = 「`/admin/*` 14곳 + `/internal/*` 4 = **18 라우트**」 · `require_admin_token_strict` = 「**2 라우트** 전용」 | ordinary = `/admin/*` 38 + `/internal/*` 4 = **42** · strict = **12** (합 54) | ⚠️ 중간 — 「손으로 관리하는 목록이 아니다」가 같은 절에 있어 오독 위험은 낮다 |
| `docs/architecture/backend.md:121` | 자식 stdout 파일 **6개**, `graph_sync_stdout.log` 포함 | **5** — 그래프 싱크 워커는 2026-08-14 은퇴(`run_decoupled_app.py:317-325` 가 묘비 주석) | 🔴 **높음 — 없는 파일을 찾으러 보낸다.** 인시던트 중에 「그 로그가 비어 있다」는 «부재의 증거»로 읽힌다 |
| `run_decoupled_app.py:303` (소스 주석) | 「**Only two children bind anything**, and in the 74-death sample those two accounted for 100% of the deaths」 | **하나**(`ports=` 를 선언한 자식은 Backend FastAPI Server 뿐). 74건 표본은 :8080 41 + :8090 33 이었고 **:8090 자식이 없어졌다** | 🔴 **높음 — 그 표본의 45%가 이제 존재하지 않는 자식의 것이다.** 「포트 프로브가 사망의 100%를 덮는다」는 근거가 이 수에 매달려 있다 |
| `docs/process/PRODUCTION_READINESS.md §C1` | 「admin 라우트 **16개** 전부」(×2), §258 「admin 16개 전수」 | 50 | ⚠️ 낮음 — 문맥이 「과거 상태」이고 회귀 방어는 「개수가 아니라 집합」이라 명시 |
| `docs/architecture/CODE_MAP.md §1.6` | `startup_banner` 라인 앵커 **249** | 실측 `_admin_auth_banner_logged` 가 `main.py:284`, 배너 호출이 `main.py:330-332` (CODE_MAP 은 `admin_auth.py` 안의 위치를 말하는 것으로 보이나 두 뜻이 겹쳐 읽힌다) | ⚠️ 낮음 |

🔴 **위 일곱 중 「낡아서 위험한」 것은 셋**이고, 셋 다 **같은 모양**이다 — 「없는 것을 찾으러 보내거나(`graph_sync_stdout.log`), 있는 것을 없다고 말하거나(`grep -c … = 0`), 사라진 표본에 근거를 매단다(`two children`)」.

---

## 못 밝힌 것

```
① `/assets` mount(StaticFiles)의 containment 를 «직접 재지 않았다» — Starlette 내부 구현이고
   이번 라운드의 대상(catch-all 봉쇄)과 다른 코드다. 오늘 게이트 대상 라우트가 그 사각에
   0 개라는 것만 실측했고, 그 mount 자체가 안전한지는 «안 쟀다»
② `test_admin_auth.py` 를 «실행하지 않았다» — `main.py` import 가 `create_all` 을 돌려 DB 에
   닿고, 이 라운드의 계약(⛔ 재기동 금지)에 걸린다. 커버리지 판정은 «소스에 적힌 집합»과
   «라우트 데코레이터 전건 grep» 을 대조해 냈다. 즉 「FastAPI 가 실제로 해석한 dependant 트리」는
   안 봤다 — 라우터 수준 `dependencies=` 나 파라미터 기본값으로 붙은 게이트가 있다면 내 수가
   «적게» 나왔을 수 있다(많게는 아니다)
③ `*_stdout.log` 의 «실제 파일»을 열지 않았다 — 그것은 이 박스의 데이터이고, 읽는 쪽 0 이라는
   판정에 필요한 것은 «코드»뿐이다
④ 회전(`CHILD_LOG_MAX_BYTES`)이 실제로 도는지 «재현하지 않았다» — 20 MiB 를 만들어야 한다.
   경로는 읽었고, 회전 실패의 폴백(원본 재개방)도 코드로 확인했다
⑤ ㉓의 S-5(DB 프로브 → 상관) 경로를 «태워 보지 않았다» — 서버 재기동이 필요하다.
   §㉓-b 의 결론은 «세 파일의 코드 경로»(process_supervisor `_enter_correlated` ·
   snapshot · health `problems[]`)를 이어 읽어 낸 것이고, 실행으로 확인한 것이 아니다
⑥ `queue_view.waiting[].ahead` 를 화면이 «어떻게» 그리는지는 `pickup_state.js` 까지만 봤다.
   `chain_queue_panel.js` 의 렌더 분기 전수는 안 셌다
```

---

## §4 규칙대로 «뽑은» 체크리스트 — 2차분 (발명 없음)

### ㉠ 선언된 것이 «실제로» 지나가나 — 아니오
```
🔴 감독자 스냅샷 16칸 중 «7칸»이 /health 복사 목록에 없다 (terminal_verdict · correlated_evidence 포함)
🔴 소급 백필 결과 10칸 중 «3칸»(거절 셋)이 _run_ledger_backfill 에서 떨어진다   ← 1차 확인
⚠️ 그리드 페이지가 토큰 없이 «요청을 안 보낸다» — 서버가 답할 수 있는 상태에서도
```
### ㉡ 받는 쪽이 «있나» — 아니오
```
🔴 supervisor 의 terminal_verdict — 0 (퍼뜨리기: 사람은 failure_reason 으로 읽지만 기계는 못 가른다)
🔴 supervisor 의 correlated_evidence — 0, 그리고 그 부재가 /health 를 «틀리게» 말하게 한다
🔴 supervisor 의 events 링버퍼(100) — 0. 파일에 쓰이고 아무도 안 연다
🔴 자식 stdout 파일 5종 — 읽는 코드 0 (다른 흐름 넷의 「끊기면」이 전부 여기로 떨어진다)
🔴 RetroactiveRun.result 7칸 «전부» — 화면 소비자 0.  ⚠️ 1차의 판정(「7키 복사가 거절을 떨어뜨린다」)보다
   «한 홉 더 앞»이 끊겨 있다 — 복사를 고쳐도 픽셀은 안 바뀐다
🔴 RetroactiveRun.error(2000자) — 화면 소비자 0. 실패한 실행에 사유가 없다
🔴 queue_view.record_failures — 0. 「로그에 두지 않으려고 값으로 냈다」는 값이 로그로 돌아갔다
⚠️ requested_by 는 «한 화면엔 가고 한 화면엔 안 간다»(queue_view ✅ / runs ❌)
```
### ㉢ 끊기면 «시끄러운가» — 아니오(조용함)
```
🔴 열림  자식 로그 회전이 «말없이» 20 MiB 를 밀어낸다 (회전도 회전 실패도 로그 0)
🔴 열림  devenv 의 격리 워처 로그는 회전이 «아예 없다» — 무한 성장
🔴 열림  NOTIFY 유실이 debug 침묵 (소급 큐가 다음 틱까지 «이유 없이» 늦는다)   ← ⑦과 같은 부류
🔴 열림  실패한 소급 실행이 화면에서 «회색 줄»과 구분되지 않는다 (사유는 읽는 쪽 0인 파일에)
⚠️ 열림  admin-auth 배너·통지 거부 주석이 전부 *_stdout.log / *.log 로만 — 읽는 화면 0
```
### ⚰️ 도달 불가 / 사실상 도달 불가
```
⚰️  VERDICT_PORT_CONFLICT 는 5자식 중 «1»에게만 도달 가능 (ports= 선언이 하나뿐)
⚰️  라우트 열거의 「WS·mount 사각」은 «실물 0» — 유일한 mount 가 /assets 로 게이트 대상 밖이다
     (문서가 경고하는 사각은 «모양»으로는 실재하고 «인스턴스»로는 오늘 비어 있다)
```

### 🔴 우선순위 — 「운영을 멈추는 것」 > 「거짓을 말하는 것」 > 「안 들리는 것」
```
✅ 멈춤     닫힘 — 못 파싱한 소급 요청이 큐를 영원히 막던 것(R-8, 2026-09-04 수리)
🔴 거짓     /health 가 「N children failing together」로 «혼자 죽은 자식»을 말하고,
           DB 를 이미 프로브해 놓고 「DB·디스크·네트워크를 찾아보라」고 답한다      <- 여기가 첫째
🔴 거짓     번들 판정 명령이 «건강한 번들»에 0 을 답한다 (계측기가 거짓 경보)
🔴 거짓     backend.md 가 없는 로그 파일을 이름으로 대고 있다 (부재가 증거로 읽힌다)
🔴 안 들림  실패한 소급 실행의 사유 · 감독자 평결 · 자식 stdout 전부 — 값은 있고 «볼 자리»가 없다
```
