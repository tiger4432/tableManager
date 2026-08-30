# 시험 셋이 «어느 디렉터리에서 돌았나»에 답하고 있었고, 출하 상태로 매 배치 거절되는 체인이 나왔다

> **커밋:** `62a809cd` (10:37) · `721c6a6e` (10:37) · `5db3b80c` (10:41) · `5a73021a` (11:01)
> | **일자:** 2026-08-30 오전
> **레인:** 시험 수리 레인 + 계측 노드 레인 + 보드 기록
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## ① 운영 임포트 검사가 «아카이브된 시험»을 훑고 있었다

`62a809cd`. 검사가 「아예 안 풀리는 런타임 임포트」로 둘을 신고했다.

```
server/_archive/tests/test_audit_changeset.py:45     audit_changeset
server/_archive/tests/test_enrichment_actions.py:4   enrichment_actions
```

둘 다 **은퇴한 시험 파일이 자기 옆에 같이 아카이브된 모듈을 임포트**하는 것이다.
어느 프로세스의 경로에서도 안 풀리고, **어느 프로세스의 임포트 그래프에도 없다** —
`_archive/` 밑은 런타임에 로드되지 않는다. 그게 그 디렉터리의 뜻이다.

🔴 **훑기는 이미 `tests/` 를 건너뛰고 있었는데, `rel.startswith(NON_RUNTIME_DIRS)` 가 «최상위»에
앵커돼 있어서 `_archive/tests/` 는 한 번도 덮인 적이 없었다.**

```python
# server/tests/prod_import_check.py
#: `_archive/` is retired code, kept for reference and imported by nothing that runs.
#: ... The prefix match is anchored at the top level, which is why `tests/` above does
#: not already cover `_archive/tests/`.
NON_RUNTIME_DIRS = ("scripts/", "tests/", "setup/", "scratch/", "migrations/",
                    "_archive/")
```

```
전   런타임 파일 155 · 임포트 1,470 · FAIL (미해결 2)
후   런타임 파일 144 · 임포트 1,389 · PASS
```

훑기가 망가지는 것을 막는 가드(`test_the_check_is_actually_looking_at_the_tree`,
파일 >50 · 임포트 >500)는 여유 있게 유지된다. 주입 시험 둘은 `_archive/` 가 없는 임시 트리에서 도니 무관하다.

## ② 런처 검사가 «수집 순서»에 답을 맡기고 있었다

`721c6a6e`.

```
ModuleNotFoundError: No module named 'run_decoupled_app'
```

`run_decoupled_app.py` 는 **레포 루트**에 있다. 스위트의 `sys.path` 는 `server/` 와 `server/parsers` 를
싣는데, 루트는 **다른 시험 모듈이 자기 용도로 넣어 줄 때만** 들어온다.
그래서 이 시험은 **앞에서 형제가 경로를 오염시켰으면 통과하고, 아니면 예외를 던졌다** —
`test_prod_import_env` 의 docstring 이 말하는 바로 그 위험이 **다른 시험 위에 내려앉은 것**이다.

임포트는 애초에 **파일 위치를 찾는 것 말고는 쓰인 적이 없었다**(`# noqa: F401`).

```python
# server/tests/test_dual_stack_bind.py
# BY PATH, NOT BY IMPORT. The launcher lives at the REPOSITORY ROOT, which is on
# no runtime process's `sys.path` ... The import only ever existed to locate the file,
# so ask the filesystem instead.
launcher = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "run_decoupled_app.py")
```

**단언은 한 글자도 안 바뀌었다** — 런처의 기본값은 여전히
`os.environ.get("ASSY_API_HOST", DUAL_STACK_HOST)` 여야 한다.

> 이 항목 작성 시 재측정: `tests/test_prod_import_env.py` + `tests/test_dual_stack_bind.py`
> -> **15 passed.**

## ③ 온톨로지 탐색기가 «엔트리포인트를 통해» 재기동에 닿고 있었다

`5db3b80c`. `ledger_api/ontology_config_explorer_router.py` 가 `delete_declaration` 과
`activate_draft` 안에서 `import main as app_main` 을 하고 있었다.

🔴 **`main` 은 라이브러리가 아니라 프로세스 «엔트리포인트»다.**

```
run_auto_update.py           수집기마다 «자기 디렉터리»를 sys.path[0] 에 넣고 «안 뺀다»
parsers/directory_watcher.py 표마다 그 표의 scripts/ 를 같은 방식으로 넣는다
그 디렉터리들은 «사용자 소유»다
=> 첫 삽입 이후 그 프로세스에서 `main` 은 «안정된 이름이 아니다» —
   사용자가 둔 main.py 가 먼저 바인딩된다
```

이것이 `test_entrypoint_import_isolation` 이 겨냥해 쓰인 결함이고, **그 시험의 메시지가 이 처방을
이름 붙이고 있었다** — 공유 심볼을 엔트리포인트 밖 모듈로 옮기고 재export 하라.

`server/system_reload.py` 가 새로 추적되며 `reload_local_process_cache` 와 재기동 본문을
**바이트 그대로** 들고 갔다. `main.py` 는 라우트를 유지하고(같은 경로 · 같은 `require_admin_token`
의존 · 같은 응답) 위임하며, 심볼을 재export 한다.

**같이 못 간 것이 «하나»였고, 그것이 이 커밋의 위험한 부분이다** — `global_watcher` 는
`main` 의 모듈 전역에 산다.

```python
# server/main.py — startup_event()
# 반환 직후, start() 「전」에 할당한다
system_reload.active_watcher = global_watcher
global_watcher.discover_and_watch()
global_watcher.start(blocking=False)
```

🔴 사이의 두 호출은 핸들러의 `except` 로 던질 수 있고, **옛 코드는 다음 재기동에서
`global_watcher` 를 어차피 읽었다 — 이미 바인딩돼 있었으니까.**
나중에 할당했으면 **정확히 그 경로에서 워크스페이스 동기화가 조용히 사라졌을 것이다.**

검토가 아니라 **실행**으로 확인했다.

```
워처 없음   status=success · outbox rows=1 · event_type=SYSTEM_RELOAD
워처 있음   status=success · outbox rows=1 · sync_new_workspaces() 호출됨
그리고 test_admin_auth 가 POST /admin/reload-configs 를 «라우트를 통해» 200 까지 몬다
여섯 파일 197 passed
```

> 이 항목 작성 시 재측정: `tests/test_entrypoint_import_isolation.py` +
> `tests/test_config_reload_integrity.py` -> **34 passed.**

⚠️ 이 시점에 라우터는 여전히 «비한정» 임포트를 쓴다 — 바뀐 것은 **그 이름이 `main` 이 아니라는 것**이다.

## 시험 레인 1차 — 기준선은 21 이 아니라 «20» 이었다

`5a73021a` 가 기록했다.

```
수리 «3» (위의 셋) · 새 빨강 «0» · 단언 재작성 «0»
기준선     제 21 이 아니라 «20» — h3 하나가 «플레이크»다 (같은 코드에서 양쪽 답)
검증       두 진행 스트림을 문자 단위로 대조: 4,261 중 «3» 만 다르고 전부 F -> pass
결과       20 -> 17
```

**남은 17 중 «10» 은 수리가 아니라 «판정»**이다 — 핀이 가리키던 것이 움직인 것들이고,
레인이 단언을 하나도 안 고쳤다. 그중 하나는 **총괄 소관**으로 표시됐다.

## 🔴 시험 둘을 고치려다 «출하 상태의 운영 사실»이 나왔다

이 박스만의 문제가 아니다 — 라이브와 `.sample` 이 동일하다.

```
chain_rules   dt_metadata_to_dt_inventory   enabled: true · job-column 키 «0 / 2»
table_config  dt_inventory                  business_key dt_job_id
                                            composite_key_source ['dt_job']
chain_bindings.identity_column
              business_key 경로를 «composite_key_source 의 부재»로 게이트한다
=> composite_key_source 가 «있으므로» business_key 경로가 안 열리고,
   target_job_column 은 선언이 없어 «파생도 못 한다»  ->  ColumnBindingRefused
   즉 이 체인은 «출하 상태 그대로 매 배치 거절»된다
```

레인 판단이 그대로 기록됐다 — **「시험에 규칙을 쥐여 주면 초록이 되는데, 그건 «경보를 끄는» 것이다」.**

## 🔴 계측 레인은 «시각»에서 멈췄다 — 그리고 아무것도 선언하지 않고 돌아왔다

지시서의 멈춤 조건 ①이 걸렸다. 라이브·샘플 둘 다 바이트 무변경, 원자 «0».

```
server/ledger/roleframe.py:1093  _scalar
   받는 것  bool · 정수 · 유한 실수 · 문자열
   eventtime 은 timestamptz -> tz-aware datetime 으로 도착 -> invalid_scalar_role
```

🔴 **레인이 원인을 «2×2» 로 격리했다** — 「이름 충돌인가 타입인가」를 안 섞었다.

```
키 이름        묶는 컬럼                 결과
occurred_at   eventtime (timestamptz)   거절
at_time       eventtime (timestamptz)   거절     <- 이름 문제가 «아니다»
occurred_at   role      (varchar)       OK · 196
at_time       role      (varchar)       OK · 196
```

그리고 **선언으로 도는 길을 각각 닫은 뒤에** 멈췄다 — 바인딩 종류는 셋뿐이고 캐스트가 없다,
`key_types` 는 번역 시점에 아무도 안 읽는다(심볼로 훑음), 두 소스가
`accepts_verified_join_rules: false` 라 `prepare` 를 못 쓴다, 문자로 든 시각 컬럼이 없다.
**대체 키를 지어내지 않았다.**

**그리고 이번 라운드의 «목적»은 안 막혔다.**

```
시각 키만 뺀 진단   199행 -> 199분자 -> 796원자 (performed·at·produced·measures 각 199)
🔴 station 만      199행 -> 398원자. 깨끗하게 돈다
=> 막힌 것은 «run» 하나이고, «분모»는 막히지 않았다
```

시각을 그냥 뺄 수 없다는 것도 수로 나왔다 — 빼면 **서로 다른 계측 5,648 묶음이 한 노드로 합쳐진다.**
`param_id` 의 uuid 접두도 대체물이 아니다(접두 24,184 vs 묶음 24,070, 묶음이 접두를 넘는 경우 «114»).

보드에 적힌 판정은 **길 넷과 그중 총괄 권고**였다 — station 을 먼저 착지시키고 `_scalar` 를 나중에 넓힌다.
`_scalar` 는 «넓히는» 변경이라 기존 통과 값의 동작이 안 바뀐다는 것도 같이 적혔다.

## 🔴 총괄의 지시서가 «없는 씨앗»을 검증에 지정하고 있었다

```
지시서    ZZ-DOE-BW-01..04 로 확인하라
실제      그 넷은 계측 «표»에 행이 «0». DOE 계측 웨이퍼는 CW-01..08 이다
왜        그 씨앗을 «walk»(API)으로만 확인하고 «표»에서 안 봤다.
         웨이퍼는 코어를 «거쳐» 물리량에 닿으므로 walk 으로는 참인데,
         레인이 태울 «번역 경로»에는 그 행이 없다
```

**한 층에서 참인 씨앗이 다른 층에서는 없을 수 있다.**

## 아키텍처 영향

- 운영 임포트 검사가 `_archive/` 를 런타임 밖으로 센다.
- 런처 검사가 **파일시스템으로** 파일을 찾는다 — 수집 순서가 답을 정하는 자리 하나가 닫혔다.
- **`server/system_reload.py` 가 새로 생겼다.** 재기동은 엔트리포인트 밖에 살고,
  `main.py` 는 라우트와 재export 만 남는다 — 그래서 그 심볼을 가리키는 문서 여섯 자리가 그대로 참이다.
- 워크스페이스 워처 참조가 `system_reload.active_watcher` 에 있고, **생성자 반환 직후**에 할당된다.

## 그때 남아 있던 것

- 전수 빨강 **17**. 그중 «10» 이 판정 대기이고 «3» 이 `in_slot`, «1» 이 총괄 소관이다.
  총괄 소관 하나는 **지시서에 적은 원인이 낡았다** — 라이브 번들은 오류 0 이고 깨지는 것은 «재생성된» 번들이다.
- **`dt_metadata_to_dt_inventory` 체인은 출하 상태로 매 배치 거절된다.** 선언을 고칠지 게이트를
  고칠지는 이 시점에 판정 대기다.
- **계측 `run` 은 선언되지 않았다.** `station` 은 깨끗하게 번역되는 것이 확인됐지만 착지하지 않았다.
- 기준선 20 중 **h3 하나가 플레이크**로 관측됐다 — 같은 코드에서 양쪽 답이 나왔다.
