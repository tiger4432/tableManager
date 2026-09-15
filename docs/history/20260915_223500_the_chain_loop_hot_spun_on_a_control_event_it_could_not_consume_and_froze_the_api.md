# 박스 장애 — 체인 루프가 «소비 못 하는» CONTROL 행 하나로 await 없는 고리가 되어 API 전체를 굶겼다. 스케줄러를 띄우자 재기동 «없이» 풀렸다

> **커밋:** «없음» — 이것은 총괄이 «잰» 장애 기록이다. 출처는 `docs/process/PROJECT_STATUS.md` 의 **[22:3x~22:4x 박스 장애]** 블록(`795ac1e6`), 구현자 채널 S-252 지시(`f41f67d8`), 판정 406(`795ac1e6`).
> **일자:** 2026-09-15 22:3x ~ 22:5x
> **레인:** 총괄 실측(py-spy) → 판정. 구현자 S-252 는 이 시점에 «미착지»(공유 트리에 23:00 부터 미커밋 편집, 초인종 `c904b389`).
> **측정 상자:** 이 워크스테이션. **운영이 아니다.** 다만 아래 ③의 구조는 «코드»의 것이라 어느 설치에서나 참이다.
> **스위트:** 해당 없음 — 착지한 코드가 없다.

## ① 무슨 일 — 소유자 「조인 리플레이 안 돌고, audit log 새로고침에 굳음」

```
소유자가 박스에서 조인 소급을 누름
  -> RETROACTIVE_RUN 아웃박스 행 #5137807 하나
  -> 그 행을 소비하는 «스케줄러 프로세스»(run_auto_update.py, SCHEDULER_OWNED_EVENT_TYPES)가 박스에 «없었다»
  -> 체인 루프가 매 틱 그 행을 «가져와서» CONTROL 이라 «건너뛰고», pending 이 «비어 있지 않아» 기다림을 «안 탔다»
  -> await 없는 고리. 이 루프는 «이벤트 루프 스레드»에서 동기로 돈다 -> uvicorn 의 «모든» 요청(정적 html 포함)이 «영원히» 안 돌아왔다
DB 막힘 0 (pg_blocking_pids)
```
**py-spy 두 덤프(3 초 간격):** MainThread 가 `start_chain_ingestion_worker` 안에서 **active+gil**, 프레임이 «다른 줄» — 막힌 것이 아니라 «도는» 것.
**진단 증명:** `run_auto_update.py` 를 띄우자 이벤트가 소비되고 **재기동 없이 HTTP 200**. 소급이 실행됐다(단 `rows_scanned 0` — 아래 ④).

## ② 코드 — 그 시점 HEAD(`8cab58da` 의 `server/chain/ingestion_worker.py`)의 세 줄

```python
# Fetch pending outbox records                      <- 표·종류 필터 «없음». 남의 행도 가져온다
pending_events = db.query(DatabaseOutbox).filter(
    DatabaseOutbox.processed_chain == False
).order_by(DatabaseOutbox.id.asc()).limit(200).all()
...
if not pending_events:                               <- 기다림은 「가져온 행 0」일 때 «만»
    loop_wake_ts = None
    if await listener.wait(2.0):
        loop_wake_ts = time.monotonic()
    continue
...
for event in pending_events:
    ...
    if event.event_type in event_constants.CONTROL_EVENT_TYPES:
        continue                                     <- CONTROL 은 건너뛴다. processed_chain 은 그대로 False
```
```python
# server/event_constants.py — 두 집합이 «이미» 있었다. 루프가 그것을 «안 지났다»
SCHEDULER_OWNED_EVENT_TYPES = frozenset({EVENT_SCHEDULER_RUN_NOW, EVENT_RETROACTIVE_RUN})   # run_auto_update.py 가 비운다
CHAIN_OWNED_EVENT_TYPES     = frozenset({"CREATE", "EDIT", "DELETE"})                      # chain 워커가 비운다
```
🔴 「가져온 행이 있다」와 「할 일이 있다」는 «다른 사실»이고, 그 둘이 같다고 가정한 것이 이 고리다.

## ③ 판정 406 — 「API 프로세스는 체인 루프를 «돌리지 않는다»」(총괄, 22:5x)

소유자: 「과연 이런 문제 요소가 한두 개일까? 운영에서는 수십 개 체인·인제션·서버 요청이 도는데」.
```
이벤트 루프에 오래 사는 태스크는 «하나»   main.py:584  chain_task = main_loop.create_task(start_chain_ingestion_worker(SessionLocal))
그 루프 본체는 «동기 DB»                  -> «어떤» 틱이든 느리면(질의 하나·맵퍼 하나·고리 하나) API 전체가 그 시간만큼 굳는다
                                        S-252 는 그 부류의 «한 사례»다
런처(run_decoupled_app.py)              ChildSpec("Chained Ingestion Worker", [python_exe, "run_chain_worker.py"]) · ChildSpec("Auto Update Scheduler", [python_exe, "run_auto_update.py"])
                                        그런데 uvicorn 자식에 ASSY_CHAIN_WORKER=0 을 «안 건다»(그 리터럴이 런처에 0 회)
                                        -> 런처로 도는 설치는 체인 루프가 «둘»이고 그중 하나가 API 안에 있다
ASSY_CHAIN_WORKER 스위치                 2026-09-14 장애 때 «킬 스위치»로 생겼다(main.py 주석). 스위치는 있었고 런처가 그것을 «안 썼다»
```
```
판정 406 ① 런처가 uvicorn 자식에 ASSY_CHAIN_WORKER=0 을 «건다»(한 줄)
        ② uvicorn 단독 기동(박스·개발)은 안에서 돌되 «경고 한 줄»(「API 와 한 프로세스 — 운영은 런처」)
        ③ S-252 ①②(자기 소유 종류만 가져온다 · 처리 0 이면 «반드시» 기다린다)는 그대로 — 별 프로세스여도 자기 자신을 굶기지 않게
S-252-b(틱 본체를 executor 로)는 406 으로 «닫는다» — 두 경로 금지, 프로세스 «하나»가 답
```

## ④ 같은 장애에서 «셋»이 더 나왔다

```
S-253 (등급 3)  소급 버튼이 「queued」라 답하고 «소비자가 없다»는 말을 안 한다 — 스케줄러가 없으면 RETROACTIVE_RUN 은 영원히 PENDING
               등록부에 runner_identity/heartbeat 명부가 있다 -> 라우트가 「대기열에 넣었으나 돌릴 프로세스가 없습니다 → 다음: run_auto_update 를 띄우십시오」를 «응답과 줄»에(S-247 모양)
S-254 (등급 2)  스케줄러를 띄우고 소급이 «돌았는데» rows_scanned 0 — 배너가 보낸 business_keys(화면 컬럼 값 `DT_JOB_ID PROBE-…`)와
               composite 표 dt_log 의 저장 업무키(`GEN-dt_cell_key-…`)가 «다른 세계». 그리드는 row_id 를 «이미» 든다
               -> 소급 R1 에 row_ids 선택 칸(서버) + 배너가 row_id 로(클라 C-112)
```
📌 S-254 는 다섯 시간 전 착지한 C-109(`c87080e3`)의 배너에 «그때부터» 있던 것이다 — 그 커밋은 이름과 종류를 고쳤고 «보내는 키»는 안 건드렸다.

## ⑤ 앞선 사고와의 자리 — 「RETROACTIVE_RUN 행이 «범인처럼» 보였을 뿐」이 이번엔 범인의 «자리»였다

2026-09-04 스케줄러 정지 사고(`af744fe3`)의 기록은 「줄 서 있던 RETROACTIVE_RUN 행이 범인처럼 보였을 뿐」이라고 적었다 — 그때 원인은 크론 수집기의 인라인 실행이었다. 이번에는 같은 종류의 행이 «소비자 부재»와 «필터 없는 pending 질의»를 만나 «진짜로» API 를 굳혔다. 같은 행, 다른 기제 — 「원인 하나 찾았다고 멈추지 않는다」.

## ⑥ 아키텍처 영향 (판정으로서 — 구현은 이 시점에 없다)

- 체인 루프의 «집»이 정해졌다: 자기 프로세스. API 프로세스 안의 루프는 «개발 편의»이고 경고를 단다.
- 아웃박스의 «소유 집합»이 루프의 pending 질의를 «지나야» 한다 — 남의 행은 이 루프의 대기열이 아니다.
- 「소급을 눌렀다」의 답은 «소비자가 살아 있나»를 포함해야 한다(S-253).

## ⑦ 그때 남아 있던 것

- **S-252 미착지.** 공유 트리 `server/chain/ingestion_worker.py` 에 23:00 부터 미커밋 편집(+76/−7)이 «놓여 있었고», 총괄 초인종 `c904b389`(「state or landing」)가 답을 기다리고 있었다.
- 판정 406 ①(런처 한 줄)·S-253·S-254·C-112 «전부 미착지». 순서: S-252 → 406① → S-254 → S-251 → S-241 → S-234, 클라 C-112 → C-111.
- 박스에는 «지금» 스케줄러(PID 40728)가 «떠 있다»(런처 모양) — 그래서 이 박스에서는 같은 고리가 «재현되지 않는다». 그것은 수리가 아니라 «소비자가 있는 상태»다.
- 「운영에서도 같은 모양이다 — 스케줄러가 죽거나 늦으면 소급 버튼 한 번에 API 가 굳는다」는 총괄의 «구조» 주장이다(코드 ②③에서 나온다). 운영에서 «일어난» 기록은 없다.

---
📎 이 항목의 수(#5137807 · PID 40728 · 3 초 · 0)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 ⑦ 마지막 줄의 «구조 주장»뿐이다.
📎 09-04 스케줄러 사고: `20260904_174600_a_collector_doing_its_job_took_the_monitoring_down_and_one_bad_row_held_the_whole_queue.md` · 09-14 장애가 만든 킬 스위치의 맥락: `20260915_094114_off_still_touched_the_database_and_a_probe_poisoned_the_read.md` · 「항목은 프로세스마다」(API 안 등록부 vs 워커): `20260915_153723_the_registration_lived_inside_one_of_two_doors_and_the_other_half_was_running.md` §⑥ · rows_scanned 0 의 배너: `20260915_170746_the_grids_replay_list_belongs_to_the_table_and_the_loader_left_main_js.md` §⑦.
