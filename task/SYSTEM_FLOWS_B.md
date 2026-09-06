# 흐름 실측 B — ⑤ 거절 · ⑥ 관측 · ⑦ 통지 · ⑩ 백업·복원

> **작성:** Server PM · **대상:** `docs/architecture/SYSTEM_FLOWS.md` §5 에 병합 (총괄이 병합)
> **칸 정의·채우는 규칙:** 그 문서 §1·§3 을 그대로 따름. 「지나가는 것」은 전선에서 잰 값, 「받는 쪽」은 데코레이터·시험·설정문자열을 뺀 소비자 수.
> **측정 기준:** 워킹트리 `main` @ 2026-09-06. ⛔ `.claude/worktrees/` · `.codex_tmp/` · `.test_tmp/` · `server/_archive/` 의 사본은 **한 건도 세지 않았다** — 이 저장소에서 grep 이 거짓 신호를 내는 첫 번째 원인이다.

---

## ⑤ 거절 → 운영자 — 실패 → 사유 → 주소 → 표본 → 화면

**한 줄:** 주소는 이제 «만들어지고 실려서 백필 결과까지» 간다. 그런데 **그 결과를 화면으로 나르는 유일한 호출자가 세 칸을 버린다.** 그리고 작성 화면 쪽은 «완전히 배선돼 있는데», 그 화면이 받기로 돼 있는 예외가 그 경로에서는 **발생할 수 없다.**

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `ledger/envelope.py:317 check_envelope` | `ledger/gate.py:602 screen_compiled_molecule` | 분자 1건마다 — `runtime_v2.py:303` 의 `for result, atoms in zip(...)` 루프 | 함수 반환값 (list[dict]) | `[{code, path, message}]` — 코드 4종 매핑은 `gate.py:387 _ENVELOPE_REASONS`, 미매핑 코드는 `REFUSE_NOT_TRUE_ALONE` 로 폴백(`gate.py:403`) | **1** — `gate.py:610` 이 `report["violation_details"]` 로 적재 | 조용 — 위반이 없으면 빈 리스트라 구분 불가. 다만 뒤 칸이 곧 시끄러워진다 | ✅ 이어짐 |
| `gate.py:610` `report["violation_details"]` | `gate.py:630-634 refuse(addresses=)` | 같은 루프, `report["refused"]` 가 참일 때 | 함수 인자 | `report.get("violation_details") or ()` — dict 리스트 그대로 | **1** — `gate.py:406 refuse` | 조용 — `or ()` 라 빈 튜플이 되고 거절 자체는 그대로 발생 | ✅ 이어짐 |
| `gate.py:427 _record(addresses=)` | `gate.py:232 _samples` (프로세스 전역 list) | 매 거절 | 모듈 전역 상태 | `{source, reason, atoms, rows, detail, addresses:[{code,path}]}` — **`code`·`path` 만 추림**(`gate.py:365`), 상한 `MAX_REFUSAL_SAMPLES=20`(`gate.py:210`) | **1** — `gate.py:255 samples()` | 조용 — 21번째부터 «말없이» 안 담긴다. 다만 잘림 여부는 다음 칸이 수로 낸다 | ✅ 이어짐 |
| `gate.py:255 samples()` · `gate.py:235 refusals()` | `ledger/backfill.py:544-547` 실행 결과 dict | `backfill.run()` 종료 직전 (매 실행 1회) | 함수 반환값 (dict) | `refused_total`(int) · `refused_samples`(list) · `refused_samples_capped`(bool) — 잘림을 «수 두 개»로 말한다 | **0 (운영)** — `server/` 전건 grep 에서 이 셋을 읽는 코드가 없다. 히트는 `backfill.py` 자신과 `tests/test_a_refusal_says_which_field_to_fix.py:117`(소스 텍스트 단언) 뿐 | 🔴 **완전 무음** — 값이 만들어지고 아무도 안 읽고 사라진다. 오류도 로그도 없다 | 🔴 끊김 |
| `backfill.run()` 결과 dict | `retroactive.py:387-390 _run_ledger_backfill` 반환 dict | 운영자가 어드민에서 `POST /admin/retroactive/ledger_backfill/run` | 함수 반환값 | **7칸만 통과**: `rows_read`·`batches`·`inserted`·`deduped`·`molecules`·`stopped`·`cursor_after`. 🔴 `refused_total`·`refused_samples`·`refused_samples_capped` 는 **여기서 버려진다** | 1 (`retroactive.py:1477` → `RetroactiveRun.result` JSON) | 🔴 **무음** — 화면은 「분자 N개 만들었다」만 보고, 몇 건이 왜 거절됐는지는 «응답에 아예 없다» | 🔴 끊김 |
| `RetroactiveRun.result` | `client2/src/admin.js:2551` → 소급 실행 화면 | 어드민 소급 탭 열기 / 폴링 | HTTP `GET /admin/retroactive/runs?limit=50` (`retroactive.py:1127 runs()`) | `{run_id, op, label, params, state, processed_rows, total_rows, result, error, …}` — `result` 는 위 7칸 | 1 | 화면이 조용히 「성공」으로 읽는다 — 거절된 행이 있어도 `state` 는 성공이다 | ⚠️ 반쪽 |
| `gate.py:371-380 logger.warning/info` | 스케줄러 프로세스 stdout | 매 거절 (1·10·100·… 번째는 WARNING, 나머지 INFO — `gate.py:211 _ANNOUNCE_AT`) | 로그 | `[LedgerGate] source=%s REFUSED a source event at the door \| reason=%s \| …` | 파일 1 — 🔴 **uvicorn 이 아니다.** 소급 백필은 `run_auto_update.py:758 start_retroactive_run` 이 «스케줄러 프로세스의 별도 스레드»에서 돌린다 → `run_decoupled_app.py:330-331` 의 `log_file=paths.log_path("auto_update_stdout.log")` 로 tee 된다 | ⚠️ 조용 — 아무 화면도 그 파일을 읽지 않는다. 「로그에 찍힌다」는 참이지만 «운영자가 보는 자리»는 아니다 | ⚠️ 반쪽 |
| `gate.py:525` `report["violation_details"]` (v1 팔 `screen_molecule`) | — | — | — | 같은 dict 리스트를 «쓰기는 쓴다» | **0** — `gate.py:554 refuse(...)` 가 `addresses=` 를 **안 넘긴다**. 그리고 `screen_molecule` 자체의 운영 호출자가 **0**(히트 전부 `server/scripts/seed_syn_*.py` 6종 + 시험) | 조용 | ⚰️ 죽은 갈래 |
| `gate.py:528-530` · `gate.py:613-616` | — | — | — | `break` **뒤에** 놓인 `report.update(...)` 3~4줄 | 0 — 도달 불가 | 조용 | ⚰️ 죽은 갈래 (양쪽 팔에 같은 모양이 하나씩) |
| `backfill.py:1298` `result["gate_note"]` | CLI stderr | `python server/ledger/backfill.py --source …` | 로그 | — | **읽는 쪽 1 · 쓰는 쪽 0.** `gate_note` 는 `server/` 전건에서 이 두 줄(1298·1299)에만 있고 **어디서도 설정되지 않는다** → 이 `if` 는 항상 거짓 | 조용 | ⚰️ 죽은 갈래 |
| `gate.py:310 note()` → `observability.py:44 note()` | `heartbeat.beat("ledger", note=…)` | `backfill.py:1294 beat(result)` | 하트비트 파일 `worker_heartbeats/ledger.json` | 거절 digest 문자열 (`molecules=` / `source_rows=` / `built_atoms_discarded=` + 상위 5) | **CLI 전용.** `beat(result)` 는 `backfill.py:1223 main()` 안(1294행)에 있다 → 어드민에서 돌린 백필은 **비트를 아예 안 찍는다** | 🔴 조용 — 화면에서 돌린 백필의 거절 digest 는 «어디에도 안 실린다» | 🔴 끊김 |
| `worker_heartbeats/ledger.json` 의 `note` | `/health` 응답 | `GET /health` | HTTP JSON | `heartbeat.py:290` 이 `note` 를 읽어 entry 에 담는다 | **0** — `health.py` 의 워커 루프(`:226~:352`)가 만드는 entry 칸은 `heartbeat·supervisor_state·pid·restarts·status·detail·age_seconds·beats·error·work·stale_after_seconds·beat_pid·detail_beat`. **`note` 가 없다** | 🔴 무음 — 읽혀서 dict 에 담기고 그다음 칸에서 «조용히 떨어진다» | 🔴 끊김 |
| `POST /admin/ontology-explorer/test-run` (`ontology_config_explorer_router.py:121`) | `config_explorer_service.py:673 _test_run_refusal` | 운영자가 「시험 실행」 버튼 (`ontology_explorer.js:1110`) | HTTP body `{source_id}` → 응답 dict | `{code, path, message, form_path}` + 조건부 `rows_read`·`rows_missing`·`column`·`partial_apply` | **1** — `ontology_explorer_view.js:745 renderTestRunRefusal` | 시끄럽다 — 500 을 안 낸다(`config_explorer_service.py:618 except Exception`). 거절이 «답»으로 나간다 | ✅ 이어짐 |
| 위 응답 | 화면 픽셀 | 같은 클릭 | DOM | `form_path` 있으면 폼으로 가는 **버튼**(`map-goto`), 없으면 `path` 를 `<code>` 로. `rows_read/rows_missing/column` 셋이 다 있을 때만 「N행 중 M행 · 컬럼」. `partial_apply === false` 일 때만 「좋은 행도 안 들어갑니다」 | **1** — 그리고 «출하본에 들어 있다»: `client2/dist/assets/admin-eErqdtgQ.js` 에 `oe-testrun-refusal` · `form_path`(2) · `rows_missing`(1) · `partial_apply`(1) 존재 | 시끄럽다 | ✅ 이어짐 |
| `gate.py:122-123 MoleculeRefused.code/.path` | `_test_run_refusal` 의 `getattr(exc,"code")` | — | 예외 속성 | 첫 주소의 `code`·`path` | **0 (이 경로에서 도달 불가)** — 아래 ⚰️ 근거 참조 | — | ⚰️ 죽은 갈래 |
| `gate.py:275 captured()` | — | — | contextmanager | 프로세스 카운터를 격리해 미리보기가 라이브 거절 총계를 오염시키지 않게 함 | **0 (운영)** — 히트는 `tests/test_ledger_admin_setup.py:240·254` 뿐. `ledger/dry_run.py:190 preview()` 는 «첫 실행 문장에서 `DryRunUnavailable` 을 raise» 하므로 그것을 부를 자리 자체가 없다 | — | ⚰️ 죽은 갈래 |

### ⚰️ 근거 — 「게이트 거절은 시험 실행 화면에 도달할 수 없다」

`MoleculeRefused` 는 `gate.py:428 molecule_is_open()` 이 참일 때만 raise 된다. 그 스코프를 여는 자리는 **`server/ledger/runtime_v2.py:306` 하나**(`server/ledger/` 전건 grep).

```
시험 실행   test_run → backfill.preview_first_batch(:904)
           → setup.preview_selected_cursor_batch(:191)
           → runtime_v2.preview_cursor_batch(:72)      <- `_screened_atoms` 를 «안 부른다»
백필 실행   backfill.run → execute_selected_cursor_batch(:208)
           → runtime_v2.execute_cursor_batch(:115) -> `_screened_atoms`(:146) -> building_molecule(:306)
```
`_screened_atoms`(`runtime_v2.py:293`)의 호출자는 `:146`·`:226` 둘뿐이고 **둘 다 execute 계열**이다. 즉 미리보기는 게이트를 통과하지 않으므로 `MoleculeRefused` 가 나올 수 없고, `gate.py:109-114` 가 이 리더를 위해 붙인 `code`/`path` 는 이 경로에서 한 번도 쓰이지 않는다. (백필 경로에서는 raise 되지만 그쪽 리더는 `_test_run_refusal` 이 아니다.)

### ⚠️ 낡은 서술 (「상태」에 기록해야 할 발견)

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| `gate.py:256` docstring | 「…for the report and for **`/health`**」 | `/health` 는 게이트를 **안 읽는다**. `health.py:432-443` payload 의 `checks` 는 `database·workers·outbox·supervisor·config_backup` 다섯뿐 |
| `gate.py:146` docstring | 「With **`backfill.run`** holding the `with`」 | 실제 스코프 보유자는 `runtime_v2.py:306`. 같은 드라이버 밑이라 결론은 유효하지만 **이름이 낡았다** |
| `SYSTEM_FLOWS.md` §0 표 「거절 주소 — 캐리어 3, 읽는 쪽 0」 | 고쳐진 것으로 읽히기 쉽다 | 절반만 고쳐졌다: 작성 화면 팔은 ✅, 백필 팔은 캐리어가 «하나 더 늘고» 읽는 쪽은 **여전히 0** |

---

## ⑥ 관측 — 프로세스 → 심박/명부 → `/health` → 화면

**한 줄:** 서버 쪽은 이 저장소에서 가장 촘촘하게 지어진 흐름이다 — 그리고 **마지막 칸이 없다.** `/health` 를 읽는 화면이 «하나도» 없다.

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| 워커 루프 | `utils/heartbeat.py:157 beat(name)` | 루프 반복마다 (워처 3.0s · 체인 2.0s · 스케줄러 5.0s) | 파일 `<config>/worker_heartbeats/<name>.json`, `os.replace` 원자적 | `{ts, pid, beats, note, work{…}}`, 200B, 초당 1회 상한(`:83`) | 1 (`read_all`) | 🔴 **아무것도 안 울린다 — 의도다.** 디스크 오류를 전부 삼키고 카운트만 한다(`:157` docstring): 모니터링이 새 장애 모드가 되면 안 되므로. 부재는 다음 칸이 판정 | ✅ 이어짐 |
| 런처 `run_decoupled_app.py:351` | `heartbeat.py:327 write_roster` → `_roster.json` | 부팅 1회 (`Supervisor` 생성 직전) | 파일 | `{"written_at": t, "processes": {name: t}}` — 실측 이름 **셋**: `watcher`·`chain`·`scheduler`. 🔴 **웹서버는 `heartbeat=` 가 없어 명부에 «없다»**(`:310-314`), 데스크톱도 없다 | **1** — `health.py:219 _hb.read_roster()` | 시끄럽다 — 실패 시 WARNING 한 줄(`run_decoupled_app.py:355`) 후 «디스크 폴백». 명부가 비면 「존재하는 비트 전부」로 떨어진다(`health.py:220-221`) | ✅ 이어짐 |
| `process_supervisor.Supervisor.write_status` | `<config>/supervisor_status.json` | 1초 폴 / 5초 강제 갱신 (`STATUS_REFRESH_SEC`) | 파일 | `{supervisor_pid, updated_at, children{…state, restarts, pid, last_exit_code, failure_reason, correlated_with, correlated_retries, **terminal_verdict**}, failed_children, correlated_children}` | 1 (`main.py:262 _supervisor_mod.read_status()`) | 시끄럽다 — `updated_at` 이 감독자 자신의 생존 신호. 낡으면 `health.py:174-181` 이 UNHEALTHY + 문장 | ✅ 이어짐 |
| `supervisor_status.json` 의 `terminal_verdict` | `/health` 응답 | — | — | `broken_child` / `port_conflict` (`process_supervisor.py:867`, 스냅샷 `:1069`) | **0** — `health.py:158-167` 의 `sup_check["children"]` 이 복사하는 칸 7개에 **없다.** `server/*.py`·`client2/src/*.js` 전건에서 이 값으로 분기하는 코드 0 | 🔴 무음 — 「포트를 누가 점유했다」는 판정이 파일에만 앉는다 | 🔴 끊김 |
| `heartbeat.read_all` + `read_status` + `read_roster` + DB/outbox 프로브 | `health.py:107 compute_health` | `GET /health` 요청마다 | 함수 인자 | 워커 판정 = 감독자 뷰 × 비트 뷰 조인. `expected` 결정 순서 **감독자 → 명부 → 디스크**(`:213-221`), `uptime` 없으면 명부 시작시각에서 채움(`:229`) — 이 한 줄이 재기동 503 이었다 | 1 | — | ✅ 이어짐 |
| `compute_health` | HTTP 응답 | `GET /health` (`main.py:238`, 게이트 **없음** — 의도) | HTTP JSON + 상태코드 | **실측 페이로드**(`health.py:432-443`): `{status, checked_at, problems[], checks:{database, workers, outbox, supervisor, config_backup}}`. `workers.<n>` = `heartbeat·supervisor_state·pid·restarts·status·detail·age_seconds·beats·work·stale_after_seconds`(+상황별 `error`·`beat_pid`·`detail_beat`). `status ∈ ok\|degraded\|unhealthy`, unhealthy 만 503(`:444`) | 아래 두 행 | 라우트가 catch-all 아래로 밀리면 `index.html` 을 200 으로 답한다 — `tests/test_health_endpoint.py` 가 그것을 막는다 | ✅ 이어짐 |
| `GET /health` | **화면** | — | — | — | 🔴 **0** — `client2/src` · `client2/*.html` 전건에서 `/health` 를 부르는 코드가 **없다.** `api.js:38 checkServerHealth()` 는 이름과 달리 **`${API_BASE}/tables` 를 친다**(`api.js:39`) | 🔴 **완전 무음.** 워커 wedged · 감독자 사망 · outbox 백로그 · 미전달 브로드캐스트 — 이 판정 전부가 «운영자 화면에 도달하는 경로가 없다» | 🔴 끊김 |
| `GET /health` | 데몬 기동 배너 | 데몬 부팅 **1회** — `chain_ingestion_worker.py:1629` · `run_watcher.py:317` 의 `startup_lines(...)` → `internal_event_client.py:241 check_api_reachable` | 로그 | 판별자는 상태코드가 아니라 **BODY**(`own_health_payload`, `:218`): `status` 키 + dict 인 `checks` 가 있으면 WARNING(앱이 살아 있고 스스로 unhealthy), 없으면 ERROR(앞단) | 파일 (`*_stdout.log`) | ⚠️ 조용 — 기동 시 1회뿐이라 «떠 있는 동안» 나빠지는 것은 이쪽으로 안 나온다 | ⚠️ 반쪽 |
| 어드민 「파이프라인 헬스 스트립」 | 화면 | **없다 — `admin.js:4555 refreshHealthStrip` 의 호출자가 0** (히트는 정의 1줄과 `:538` 주석뿐) | HTTP | 🔴 `/health` 와 **무관**. `admin.js:4650` 주석이 자기 입으로 적었다 — 「기존 API만 조합: `/admin/file-ingestion/failed` · `/admin/outbox/failed` · `/admin/auto-update/status` · `/enrichment/rules`」 | 0 | 실패 경로가 카드를 `'loading'`+`'상태 조회 실패'` 로 두지만, 그 함수가 안 불린다 | ⚰️ 죽은 갈래 |
| 같은 스트립 | 픽셀 | — | DOM | — | 0 | `admin.js:539` — `healthStripEl.style.display = 'none';` ⚠️ **결함이 아니라 소유자 판정이다** — `:536-538` 「소유자: 「띄 다 빼」(2026-09-05). 카드 넷이 하던 일 둘 중 «이동»은 탭 바가 이미 하고, «수»는 각 탭의 절이 다시 말합니다. 마크업과 `refreshHealthStrip` 은 남깁니다 — 되돌리는 것이 한 줄이어야 하기 때문입니다」 | ⚰️ 의도된 죽은 갈래 |
| `heartbeat.work_claim` | `/health` `checks.workers.<n>.work` | 파일 인제션 1건을 `with` 로 감쌈 (`directory_watcher` 2곳) | 하트비트 파일의 `work` 블록 | `{open, what, no_progress_seconds, held_seconds, stalled, stall_after_seconds}` — 나이가 아니라 **절대 타임스탬프**를 publish 해서 독자가 «지금»에서 잰다 | 1 (`health.py:337-352`) | 시끄럽다 — `stalled` 면 UNHEALTHY + 문장. 「루프는 도는데 일이 안 간다」를 잡는 유일한 축 | ✅ 이어짐 (단 마지막 칸은 위와 같이 화면 0) |

### 이 흐름에서 「끊기면 시끄러운가」의 진짜 답

```
서버 안쪽   촘촘하다 — 판정 하나하나에 문장이 붙고, 모르면 「모른다」로 답한다
경계        /health 는 JSON 도 상태코드도 정직하다
화면        «없다». 이 제품의 어떤 화면도 /health 를 부르지 않는다
=> 이 흐름의 청중은 «외부 모니터»뿐이고, 저장소 안에 그 모니터를 세우는 것은 없다
```

---

## ⑦ 통지 — 쓰기 → 브로드캐스트 → WebSocket → 화면 델타

**한 줄:** 이름은 양쪽이 «정확히» 맞는다(집합 차 0). 어긋나는 것은 **페이로드 칸**이다 — 같은 이벤트가 발신 자리마다 다른 칸 수로 나가고, 잘림을 알리려고 만든 칸들은 읽는 쪽이 0 이다.

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `database/database.py:128 auto_stage_database_outbox` | `database_outbox` 행 | ORM `before_flush` — 동적 행의 new/dirty/deleted | DB 행 (같은 트랜잭션) | `stage_event`(`:263`) 또는 `stage_collapsed_event`(`:205`). 축약은 명시 opt-in(`request_outbox_mode`), 켜는 곳 둘 | 2 (체인 워커 · 스케줄러) | 리스너가 이중 등록되면 **×2 중복**(과거 실측 중복 그룹 126만). 그물 `tests/test_contention_fixes.py` | ✅ 이어짐 |
| `database.py:311 _notify_outbox_once` | PostgreSQL 채널 | 같은 flush, 트랜잭션당 1회 | `NOTIFY` | 실측 SQL: `text("NOTIFY outbox_event;")` (`:337`). 래치 `_OUTBOX_NOTIFY_SENT`(`:90`), 해제는 `after_transaction_end`(`:93`)이되 **`SUBTRANSACTION` 제외**(`:122-123`) | 1 (`OutboxListener`) | 🔴 **완전 무음** — `:331`·`:339-341` 이 `except Exception: pass`. NOTIFY 유실의 증상은 데이터 유실이 아니라 «2초 폴백 폴링» | ⚠️ 반쪽 |
| `chain_ingestion_worker.py:286 _dispatch_broadcasts` | `POST /internal/events/broadcast` | 배치의 모든 그룹 커밋 «직후» 인라인 `await`(`:1353`) | HTTP | `post_event_async`(`:176`) → `.post(...)`(`:191-193`). 세션은 `internal_event_client.internal_event_session()`(`trust_env=False`, `:90`). ⚠️ **타임아웃은 상수가 아니라 인라인 리터럴 `timeout=3`**(`:192`) — 워처 쪽은 `timeout=5`(`run_watcher.py:91`)로 «다르다» | 1 | 시끄럽다 — `logger.error` 2종(`:203-205` 상태코드 + `admin_auth.internal_event_failure_note` 로 «누가 거절했는지», `:209` 전송예외), 그리고 **아무것도 raise 안 한다**(`:206`·`:210` 이 `False` 반환) | ✅ 이어짐 |
| 통지 실패 | `broadcast_at` 이 NULL 로 «남음» | 위 실패 | DB 행 (부재) | `_stamp_broadcast_at_sync` 가 `if all_ok and event_ids:` 로 가드(`:314`) → 안 찍는다 | 1 (`sweep_undelivered_broadcasts:1357`) | 🔴 **체인 워커는 `record_undelivered_notification` 을 «부르지 않는다»**(그 파일 히트 0). durable 신호가 «부재»(`broadcast_at IS NULL`)라는 것이 설계다 — 그래서 스윕이 멎으면 아무것도 안 말한다 | ✅ 이어짐 (⑥의 `undelivered_oldest_age_seconds` 가 그 사각을 메운다) |
| `run_watcher.py:78 post_event` 실패 | `database_outbox` 마커 행 | 워처 통지 실패 | DB 행 | `internal_event_client.py:135-147`: `event_type="BROADCAST_RECOVERY"` · `status="SUCCESS"` · `processed_chain=True` · `broadcast_at=NULL` · payload `{endpoint, reason[:500], marker}` — **실패한 통지의 페이로드는 «복사하지 않는다»** | 1 (같은 스윕) | 시끄럽다 — 못 쓰면 ERROR 한 줄 + `False`, 절대 raise 안 함(`:150-161`). ⚠️ 단 `table_name` 이 없으면 **말없이 bail**(`run_watcher.py:70-72`) | ✅ 이어짐 |
| `event_constants.py:300-302` 미전달 마커 3종 | 쓰는 쪽 / 줍는 쪽 | — | 상수 | `UNDELIVERED_MARKER_STATUS="SUCCESS"` · `_PROCESSED_CHAIN=True` · `_TAG="undelivered_notification"` | STATUS **2**(`internal_event_client.py:145` 쓰기 / `chain_ingestion_worker.py:1383` 줍기) · PROCESSED_CHAIN **2**(`:146` / `:1382`) · **TAG 1 — 쓰기뿐**(`:144`). 스윕 필터(`:1381-1386`)는 `payload["marker"]` 를 «안 본다» | — | ⚠️ 반쪽 — 철자를 묶은 것은 옳고, `TAG` 만 여전히 「쓰고 아무도 안 읽는」 칸이다 |
| `broadcast_at` | — | — | — | 상수 묶음에 **일부러 없다**(`event_constants.py:298-299`) — 쓰는 값이 아니라 «줍는 쪽이 찾는 부재» | — | — | ✅ 의도된 부재 (이름을 주면 누군가 «쓰게» 된다) |
| `main.py:5839 POST /internal/events/broadcast` | `ConnectionManager.broadcast` | 위 POST | HTTP → WS | 🔴 **`payload: dict = Body(...)` — 모델 없음.** 캐시 무효화 → 인제션 진행 반영 → `created_logs` 를 **제자리에서 `[:MAX_NOTIFY_CREATED_LOGS]` 로 절단**(`:5870-5871`) → `json.dumps` → 팬아웃. `event` 키를 **검증도 재작성도 안 하는 순수 릴레이** | 1 (`main.py:566 manager`) | 게이트 있음(`Depends(require_admin_token)`). 실패는 HTTP 오류로 발신자에게 돌아간다 | ✅ 이어짐 |
| `main.py:540 ConnectionManager.broadcast` | 브라우저 | 메시지 1건 | WebSocket `/ws`(`main.py:3140`) | `send_text` 순회, 실패한 소켓은 `failed_connections` 로 모아 루프 뒤 정리(`:556-564`) | N (접속 클라) | ⚠️ `/ws` 에는 **`dependencies=` 도 인증도 없다** — `/internal/events/*` 넷은 전부 게이트인데 나가는 쪽만 열려 있다 | ⚠️ 반쪽 |
| 서버 이벤트 이름 6종 | `client2/src/websocket.js:305 handleWebSocketMessage` | WS `onmessage`(`:294`) | WS JSON | `batch_refresh_required` · `batch_row_upsert` · `batch_row_delete` · `batch_row_create` · `file_ingestion_completed` · `file_ingestion_progress` | **6 / 6 — 집합 차 «양쪽 다 0»**(`:306·317·366·382·464·479`). 출하본도 일치(`dist/assets/main-M6juM_wA.js` 에 6종 전부) | 시끄럽다 | ✅ 이어짐 |
| 같은 메시지 | 그리드 델타 | — | — | 🔴 **뒤 네 갈래는 `msg.table_name === state.currentTable` 이 아니면 도달 불가**(`websocket.js:361`), `state.gridApi` 없으면도(`:362`). `created_logs` 만 그 관문 «앞»에서 소비(`:342-358`) | — | 조용 — 다른 표를 보고 있으면 통지가 «정상적으로» 버려진다(설계) | ✅ 이어짐 |
| `main.py:3018 deleted_row_ids_omitted` | 화면 | `PUT /data/updates` 의 삭제 id 가 `BROADCAST_ITEM_LIMIT` 초과 | WS `batch_refresh_required` | 잘린 개수(int). 발신 자리 **1곳뿐**(`:3001` 분기 안) | 🔴 **0** — `client2/` 전건(`src`+`dist`) 히트 0. 그리고 `batch_refresh_required` 핸들러(`websocket.js:479-485`)는 **`event` 말고 아무 칸도 안 읽는다**(캐시 클리어 + 이력 리로드만) | 🔴 무음 — 「잘렸다는 사실을 같이 보낸다」가 발신까지만 참이다 | 🔴 끊김 |
| `total_log_count` | 화면 | 대량 tx | WS | 발신: `chain_ingestion_worker.py:1092·1102` · `main.py:5828`. **`main.py` 의 `batch_row_upsert` 5곳 전부에 없다** | 🔴 **0** (`client2/src` 히트 0) | 🔴 무음 | 🔴 끊김 |
| `change_count` | 화면 | 모든 refresh | WS | 발신 자리마다 있음(스윕은 하드코딩 `0`, `:1437`) | 🔴 **0** — 위와 같은 이유(핸들러가 안 읽는다) | 조용 | 🔴 끊김 |

### 같은 이름, 다른 칸 — 실측

```
batch_row_upsert        발신 6곳 · 칸 집합 «셋»    7칸(체인) / 7칸(main 3044, total_log_count 없음) / 4칸 / 5칸
batch_row_delete        발신 6곳 · 칸 집합 «셋»    4칸(체인) / 3칸 / 5칸
batch_refresh_required  발신 9곳 · 칸 집합 «넷»    4칸(omitted 팔) / 3~4칸(created_logs 조건부) / 6칸(체인) / 3칸(스윕)
```
🔴 **그리고 `created_logs` 를 «통째로 버리는» 가드가 넷 있는데(`main.py:436·3035·3467·3534·5609`, `<= 5000`) 버렸다는 수를 아무도 안 싣는다.** `deleted_row_ids_omitted` 가 없애려던 침묵과 «같은 모양»이 한 층 위에 그대로 있다.

⚠️ `event_constants.py:125` 의 주석이 `MAX_AUDIT_VALUE_TRUNCATION_SUFFIX` 를 상수처럼 부르는데 **그 이름은 파일에 없다**(`truncate_audit_value` 가 f-string 으로 인라인, `:268`·`:277-279`).
⚠️ WS 이벤트 이름 6종은 `event_constants.py` 에 **하나도 없다** — 발신 자리마다 맨 문자열이다. 자체 재측정(`"event": "<이름>"` 전건, 시험·`_archive` 제외): `batch_refresh_required` **9** · `batch_row_upsert` **6** · `batch_row_delete` **6** · `batch_row_create` **1** · `file_ingestion_completed` **3** · `file_ingestion_progress` **1** = **26곳**. ⑦의 「경계 계약」이 공유 심볼로 묶여 있지 않다 — 미전달 마커 3종이 `event_constants` 로 모인 것과 «정반대»의 상태이고, 그 마커를 모은 사유(「한쪽이 바뀌면 오류 없이 안 주워진다」)가 여기 26곳에 그대로 적용된다.

---

## ⑩ 백업·복원 — «있는지부터»

**답: config 는 «있다»(단 복원은 CLI 전용) · 데이터베이스는 «없다».**

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `run_auto_update.py:995 maybe_backup_configs` | `config_backup.py:411 run_scheduled` | 스케줄러 루프 5초 틱 → 1800초 게이트(`run_auto_update.py:714`) → 디스크 기준 7일 기한(`config_backup.py:357 due`) | 함수 호출 | 「신선도를 cron 슬롯이 아니라 디스크 최신 스냅샷 나이로 판정」 — 놓친 주가 다음 틱에 자가 치유 | 1 | 예외를 삼킨다(`run_auto_update.py:719-722`) — 백업 실패가 수집기를 죽이지 않게. 부재는 `/health` 가 판정 | ✅ 이어짐 |
| `config_backup.py:285 take_snapshot` | `<DATA_ROOT>/config/backup/<stem>_<yymmdd>[a-z].json.bak` | 위 | 파일 (`shutil.copy` → `os.replace`, `:338-339`) | 바이트 동일하면 «안 쓴다»(`_same_bytes:253`). FIFO 31일 + 최신 4개 바닥(`RETENTION_MIN_KEEP=4`) | 3 (`run_scheduled` · `probe` · CLI) | 조용 | ✅ 이어짐 |
| `config_backup.py:366 probe` | `health.py:80 probe_config_backups` | `GET /health` (60초 캐시, `health.py:70`) | 함수 반환값 | `ok\|missing\|stale\|unknown` + detail. import 실패·예외는 **`unknown`** — 확인 불가를 이상 없음으로 내지 않는다 | 1 (`health.py:419`) | 시끄럽다 | ✅ 이어짐 |
| `health.py:420-430` | `/health` `checks.config_backup` | 위 | HTTP JSON | `missing`/`stale`/`unknown` → `escalate(STATUS_DEGRADED)`(`:426`) + `problems[]` 문장. 🔴 **절대 503 이 아니다**(`:444`) — 백업 부재는 「다음 인시던트가 어려워진다」이지 「지금 장애」가 아니고, 503 이면 모니터가 멀쩡한 스택을 재시작한다 | 위 ⑥ 참조 | 🔴 **무음** — 상태코드로는 안 보이고 200 안의 문자열이다. 그리고 그 문자열을 읽는 화면이 **0** | 🔴 끊김 (마지막 칸) |
| `/health` `checks.config_backup` | 화면 | — | — | — | **0** — `client2/` 전건에서 `config_backup` 도 `/health` 도 히트 0 | 🔴 무음 | 🔴 끊김 |
| `scripts/backup_config.py:92 cmd_restore` | 라이브 `config/<stem>.json` | **사람이 CLI 를 친다.** 그것뿐 | 파일 | ① 스냅샷 이름 검증(`_parse`, 아니면 exit 2) ② 되돌리기 전 사본 `<name>.prerollback.<ts>` ③ **기본이 dry-run** — `--yes` 없으면 아무것도 안 쓴다(`:123-125`) ④ 🔴 **in-place `open(dest,"wb")`, `os.replace` 를 «일부러» 안 쓴다**(`:127-132`) — 원자적 rename 은 config watcher 의 `on_modified` 를 «안 깨우기» 때문 | 1 (사람) | 시끄럽다 (종료코드 + 문장) | ✅ 이어짐 (단 트리거가 사람뿐) |
| 복원 | HTTP 라우트 | — | — | — | **0 — 없다.** `server/` 에서 `(backup\|restore\|rollback\|snapshot)` 경로를 등록하는 라우트 데코레이터 **0건** | — | 🔴 **없음** |
| 복원 | UI 컨트롤 | — | — | — | **0 — 없다.** `client2/` 히트는 낙관적 UI 상태 되돌리기(`admin.js:2458·3191`) 와 시험 헬퍼뿐 | — | 🔴 **없음** |
| 복원 절차 | 운영자 | 사람이 문서를 편다 | 문서 | `docs/guide/ROLLBACK_PROCEDURE.md` §3.1-bis(`:115~`), 실행 줄 `:205-206`. 「깨진 파일은 자동으로 `.prerollback.<ts>` 로 남으므로 증거를 잃지 않는다」(`:203`) | 1 (문서) | — | ✅ 이어짐 (수동) |
| **DB 백업** | — | — | — | — | **없다.** `pg_dump\|pg_restore` 저장소 전건 히트 **2** — 하나는 문서의 수동 한 줄(`docs/guide/POSTGRES_OPERATIONS_GUIDE.md:267`), 하나는 마이그레이션 **주석**(`drop_redundant_layering_indexes.py:215`). 스크립트·스케줄러 잡·헬스체크 **0** | — | 🔴 무음 — `/health` 에 DB 백업 축이 «아예 없다» | 🔴 **없음** |
| **`ingestion_workspace/` 백업** | — | — | — | — | **없다.** `run_auto_update.py:125` 의 `shutil.copy2` 는 `raws/` 로의 인제션 «이동»이지 스냅샷이 아니다 | — | 조용 | 🔴 **없음** |

### ⑩ 의 나머지 `.bak` 쓰는 자리 — 전부 config 파일 한 겹

| 쓰는 곳 | 지키는 것 | 트리거 |
|---|---|---|
| `config_backup.py:338` | `config/*.json` 전부 | 스케줄러 7일 |
| `scripts/backup_config.py:117` | 덮어써질 라이브 config (증거) | CLI restore |
| `ledger_admin.py:738-744` | 어드민 화면으로 저장되는 config·mapper — 「이것이 유일한 undo 기제」라고 자기 주석이 선언(`:734-736`) | 어드민 저장 |
| `ledger/config_drafts.py:775-780` | 초안 적용 전의 원장/온톨로지 config | 초안 적용 |
| `scripts/install_product_tables.py:510-521` | `--apply` 전의 `table_config.json` | 설치기 CLI |

🔴 **맵퍼·수집기 스크립트·원장·맵 데이터에는 백업 쓰는 자리가 없다.**
⚠️ 이 저장소의 문서가 이미 같은 말을 하고 있다 — `docs/process/PRODUCTION_READINESS.md:194` 「**PostgreSQL 정기 백업**: 없다.」 즉 ⑩은 «몰라서 빈 칸»이 아니라 **알고 비워 둔 칸**이다. 이 표가 더하는 것은 그 부재가 **`/health` 에도 축이 없다**는 사실 하나다.

---

## 총괄에게 — 열 흐름 목록이 놓친 것 · 양끝은 있는데 가운데가 없는 자리

### A. 목록에 없는데 이 영역에 «실재하는» 흐름 넷

| 이름 | 경로 | 왜 별도 흐름인가 |
|---|---|---|
| **감독 → 재시작 정책** | 자식 사망 → `_register_failure` → 포트 프로브 → 동료 규칙 → DB 프로브 → `backoff`/`correlated`/`failed` → `supervisor_status.json` | ⑥의 «부분집합이 아니다». ⑥은 「누가 살아 있나」를 «읽고», 이건 「죽으면 무엇을 하나」를 «판정»한다. 그리고 그 판정 어휘(`terminal_verdict`)의 소비자가 0 인 것이 위 표에서 나왔다 |
| **자식 stdout → 파일** | `ChildSpec(log_file=)` → `_attach_log_pump` → `*_stdout.log`(20MiB 회전, 백업 `.1`) | ⑤·⑥·⑦의 「끊기면」 칸이 **전부 이 파일로 떨어진다**. 이 흐름이 목록에 없으면 「시끄럽다」가 «어디서» 시끄러운지 답할 자리가 없다. 🔴 그리고 이 파일들을 읽는 화면도 **0** |
| **소급 실행 큐** | `POST /admin/retroactive/{op}/run` → `publish` → `database_outbox`(`RETROACTIVE_RUN`) → 스케줄러가 줍기 → 별도 스레드 → `RetroactiveRun` 행 → `GET /runs` → 화면 | ⑧「스케줄·소급」에 접혀 있지만 «⑤의 청중»이 이 흐름이다. ⑤의 거절 주소가 버려지는 자리(`_run_ledger_backfill`)가 바로 여기라, ⑧과 별개로 재야 ⑤이 닫힌다 |
| **인제션 진행 → 화면** | 워처 → `POST /internal/events/broadcast`(`event: file_ingestion_progress`) → `ingestion_activity_registry.apply_progress` → WS → `websocket.js:306` | ⑦의 표에서는 한 행이지만 «다른 레지스트리»(`ingestion_activity.py`)를 지나고 `table_name` 관문 «앞»에서 소비된다. ①(인제션)과 ⑦ 어느 쪽에도 온전히 안 들어간다 |

### B. 「양끝은 있는데 가운데가 없는」 자리 — 이번 라운드 실측 **아홉**

| # | 양끝 | 가운데가 없는 이유 |
|---|---|---|
| 1 | `backfill.run` 이 `refused_*` 셋을 «만든다» ↔ 화면이 소급 결과를 «그린다» | `retroactive._run_ledger_backfill:387-390` 이 7칸만 옮긴다. **한 줄 문제다** |
| 2 | 하트비트가 `note` 를 «싣는다»(`heartbeat.py:290`) ↔ `/health` 가 워커 entry 를 «그린다» | `compute_health` 의 entry 조립에 `note` 칸이 없다 |
| 3 | 감독자가 `terminal_verdict` 를 «쓴다»(`:867`) ↔ `/health` 가 children 을 «싣는다» | `health.py:158-167` 의 복사 목록 7칸에 없다 |
| 4 | `/health` 가 완전한 판정을 «답한다» ↔ 어드민에 헬스 스트립이 «있다» | 스트립이 다른 네 라우트로 조립되고, 게다가 `display:none` 이다 |
| 5 | 서버가 `deleted_row_ids_omitted`·`total_log_count`·`change_count` 를 «싣는다» ↔ 클라가 `batch_refresh_required` 를 «받는다» | 핸들러(`websocket.js:479-485`)가 `event` 외에 아무 칸도 안 읽는다 |
| 6 | `MoleculeRefused` 가 `code`/`path` 를 «든다»(`gate.py:122`) ↔ `_test_run_refusal` 이 그것을 «읽는다» | 시험 실행 경로가 `building_molecule` 을 안 연다 → 그 예외가 그 길로 못 온다 |
| 7 | `gate.captured()` 가 «있다» ↔ 미리보기가 라이브 카운터를 «오염시킨다» | `dry_run.preview()` 가 첫 문장에서 raise → 부를 자리가 사라졌다 |
| 8 | `UNDELIVERED_MARKER_TAG` 를 «쓴다» ↔ 스윕이 마커를 «줍는다» | 스윕 필터가 `payload["marker"]` 를 안 본다 (STATUS·PROCESSED_CHAIN 은 이어져 있다) |
| 9 | config 백업이 «돈다» ↔ 복원 절차가 «있다» | 그 사이에 «백업이 죽은 것을 사람에게 알리는 화면»이 없다. 200 안의 문자열뿐 |

### C. 총괄 판정이 필요한 것 (제안하지 않고 올린다)

1. **B-1 은 한 줄이다.** `_run_ledger_backfill` 이 세 칸을 더 옮기면 ⑤의 백필 팔이 닫힌다. 다만 이건 **화면 계약**(소급 실행 결과의 모양)을 건드리므로 경계 계약으로 올린다.
2. **B-5 는 「누가 진단을 쥐나」를 먼저 정해야 한다.** 서버가 이미 잘림을 세어 보내고 있는데 화면이 안 읽는다 — 화면을 고칠 일인가, 아니면 애초에 그 칸이 필요 없었나. 후자면 ⑦의 발신 자리 여럿을 정리하는 일이 된다.
3. **⑥의 마지막 칸이 통째로 없다.** `/health` 를 읽는 화면을 만들 것인가, 아니면 「이 흐름의 청중은 외부 모니터다」로 선언하고 문서에 박을 것인가. **선언만 해도 이 칸은 닫힌다** — 지금은 어느 쪽인지 아무 데도 안 적혀 있어서 매번 「화면이 있나」를 다시 재게 된다.
4. **⑩의 DB 백업 부재는 이미 `PRODUCTION_READINESS.md:194` 에 적혀 있다.** 새 발견이 아니다. 이 라운드가 더하는 것은 「`/health` 에 그 축이 없다」 하나이고, 이건 축을 만들지 말지의 판정이다.

### D. 낡은 문서 (⑤ 표의 「상태」에도 적었다)

| 문서/주석 | 실측과 어긋나는 곳 |
|---|---|
| `gate.py:256` docstring | 「for `/health`」 — `/health` 는 게이트를 안 읽는다 |
| `gate.py:146` docstring | 「`backfill.run` holding the `with`」 — 실제 보유자는 `runtime_v2.py:306` |
| `event_constants.py:125` 주석 | `MAX_AUDIT_VALUE_TRUNCATION_SUFFIX` — 그 이름의 상수가 없다 |
| `CODE_MAP.md` §5 `config_backup.py` | 소비자 3곳·API 이름은 **맞다**(재확인). 줄 수 440 도 맞다 |
| `CODE_MAP.md` §5 `heartbeat.py` 비트 이름 4종 | 앵커는 이 패스가 재측정하지 않았다 — 다만 **이름은 셋이다**(`watcher`·`chain`·`scheduler`). `graph` 는 은퇴했고, `ledger` 라는 **다섯 번째 이름이 CLI 에서만** 찍힌다(`backfill.py:1217`). 이 지도에 `ledger` 가 없다 |

---

## 부록 — 이 표에 쓴 수가 무엇에 대한 문장인가

```
✅ 코드 측정   grep 히트 수 · 함수 호출자 수 · 페이로드 칸 이름 · 라인 번호
              -> 커밋된 소스에서 잰 것이므로 운영에도 참이다
⚠️ 이 박스     client2/dist/assets/*.js 의 mtime 과 존재
              -> 「이 박스의 출하본에 들어 있다」까지만. 운영 배포본은 다른 빌드일 수 있다
❌ 안 쟀다     /health 를 실제로 호출한 응답 · 실행 중 프로세스 · 외부 모니터의 유무
              -> 정적 측정만 했다. 「돌려 봤다」로 읽지 말 것
```
