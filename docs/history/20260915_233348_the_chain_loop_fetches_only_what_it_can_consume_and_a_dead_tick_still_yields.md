# 체인 루프는 «자기가 소비할 수 있는 행»만 가져오고, 진행 0 인 틱도 «기다린다» — 22:3x 장애의 두 수리, 그리고 둘째가 «모양»을 없앤다

> **커밋:** `07143bbe` — fix(chain): the loop fetches only rows it can consume, and a dead tick still yields (S-252)
> **일자:** 2026-09-15 23:33
> **레인:** 구현자(서버) — 총괄 실측·지시 `f41f67d8` → 착지 → 보고 `af0ae0a8` → 총괄 닫힘 `b382e9eb`(「재기동 PID 45712」 · **박스 재현**)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.** 아래 ①의 장애 기제는 «코드»의 것이라 어느 설치에서나 참이다.
> **스위트:** 신설 **15** · 변이 **5/5 빨강** · `--collect-only` **6,763** 에러 0 (구현자 보고). 총괄 확인 「체인 루프 모집단 **344 passed**」 + 박스 재현: 스케줄러를 «끈 채» `retroactive.publish` 로 CONTROL 행 하나를 넣고 30 초 동안 `admin.html` **6/6 «200»**(어제 모양이면 000) → 스케줄러를 다시 띄워 그 행 소비.

## ① 왜 — 한 시간 전 API 가 굳은 자리

22:3x 장애(`20260915_223500_the_chain_loop_hot_spun_on_a_control_event_it_could_not_consume_and_froze_the_api.md`)의 코드 수리다. 소급 버튼 하나가 `RETROACTIVE_RUN` 아웃박스 행을 «하나» 썼고, 그 행의 소비자(스케줄러 프로세스)가 박스에 없었다. 체인 루프는 그 행을 매 틱 «가져와서» CONTROL 이라 «건너뛰고», `pending_events` 가 비어 있지 않아 «기다림을 안 탔다» — `await` 없는 고리가 이벤트 루프 스레드에서 돌아 uvicorn 의 모든 요청이 멎었다. DB 막힘 0, 재기동 불필요 — 스케줄러를 띄우자 HTTP 가 돌아왔고 그것이 진단의 증명이었다.

## ② 변경 — 둘이고, «둘째가 중요한 쪽»이다

```python
# server/chain/ingestion_worker.py — ① 남의 데몬 행은 이 루프의 대기열이 아니다
def pending_chain_events(db, limit: int = 200) -> list:
    from database.models import DatabaseOutbox
    return db.query(DatabaseOutbox).filter(
        DatabaseOutbox.processed_chain == False,          # noqa: E712
        ~DatabaseOutbox.event_type.in_(tuple(event_constants.CONTROL_EVENT_TYPES))
    ).order_by(DatabaseOutbox.id.asc()).limit(limit).all()
```
이 필터는 «새 판단이 아니다» — 루프가 몇 줄 뒤에서 «이미 적용하던» 그 멤버십 검사를 SQL 로 옮긴 것이다. `event_type` 은 NOT NULL 이라 `NOT IN` 이 행을 삼킬 수 없다. 함수로 뺀 이유: 게이트가 «진짜 세션·진짜 행»에 대고 같은 질문을 하기 위해 — 질의를 산문으로 읽는 시험은 «더는 안 도는 질의»에도 초록이다.

```python
# ② 아무것도 안 한 틱은 «그래도» 기다린다 — 막다른 출구 «둘»이 한 자리를 지난다
async def idle_wait():
    nonlocal loop_wake_ts
    loop_wake_ts = None
    if await listener.wait(2.0):
        loop_wake_ts = time.monotonic()
...
if not pending_events:
    await idle_wait()
    continue
...
if not normalized_events:
    # ⛔ [S-252] THIS `continue` WAS THE HOT LOOP. 가져온 행이 «전부» 걸러졌을 때(CONTROL 건너뛰기 · 깊이 거절)
    await idle_wait()
    continue
```
🔴 「가져온 행이 있다」와 「할 일이 있다」는 «다른 사실»이고, 그 둘을 같다고 본 것이 이 고리였다. ①은 오늘의 «원인»을, ②는 «모양»을 없앤다 — 이 루프가 «다음에» 가져오고 못 쓰는 종류의 행은 «기다림 한 번»을 치르지 «굶은 프로세스»를 치르지 않는다. 셋째 출구가 나중에 생기면 양보를 «물려받는다».

## ③ EXPLAIN — 지시대로 «재서» 적었다

전/후 모두 `Index Scan using idx_outbox_unprocessed`, 종류 검사는 그 위의 Filter — 순차 스캔 없음. 비용 수치는 «이 박스» 것이고 사실은 «플랜 모양»이다.

## ④ 시험의 판정 둘 — 결함이 픽스처의 모양을 «강제»했다

```
시계로 못 묶는다     `asyncio.wait_for` 는 루프가 «양보해야» 취소할 수 있다. 시계로 묶으면 이 결함에서
                    시험이 «빨개지는 대신 멈춘다». 그래서 「양보 3 번」이면 초록, 「질의 400 번 동안 양보 0」이면
                    빨강 — 둘 다 밀리초. 멈춤 신호는 `BaseException` 이다: 루프가 `Exception` 을 잡아
                    «3 초 잔다»(그것도 양보) — 보통 예외로 끝내면 «부재를 재려던 그것을 하고» 끝난다
물러남에 답을 준다   루프는 다른 루프가 살아 있으면 «물러난다». 개발 박스엔 대개 하나 살아 있어서, 실측하니
                    `start_chain_ingestion_worker` 가 «첫 질의 전에» 돌아왔고 이 파일이 «코드가 아니라
                    기계»에 따라 초록/빨강이었다 — 픽스처가 `another_chain_loop_is_running` 의 답을 «말한다»
```
그리고 CONTROL 행이 «필터를 뚫고 루프에 닿았어도» 모양이 서는지를 ⓑ 절이 따로 잰다 — 필터가 유일한 도착 경로가 아니다.

## ⑤ 실패담 — 초인종이 늦은 이유 (구현자 자기 보고, 그대로 남긴다)

변이 채점기를 «두 번» 중간에 죽였고(느려서), 그때마다 «복원하는 finally 가 안 돌아» 변이가 트리에 남았다. 첫 번째는 잡았고, 두 번째는 못 잡고 «자기가 주입한 결함을 진단하느라» 한참을 썼다 — 그 가짜 증상에 맞춰 시험을 «약하게» 고치기까지 했다(행동 시험 → 구조 시험). 원래 시험이 옳았고 빨간 이유도 옳았다. 구현자가 적은 재발 방지: 채점기를 죽이면 «즉시» `git status`/앵커 수로 트리를 확인한다.

## ⑥ 아키텍처 영향

- 아웃박스의 «소유 집합»(`CONTROL_EVENT_TYPES`)이 이제 pending 질의를 «지난다» — 남의 행은 이 루프의 대기열이 아니다.
- 루프의 «양보 자리»가 하나(`idle_wait`)로 모였다. 「처리 0」의 출구가 몇이든 그 자리를 지난다.
- 그대로인 것: 루프가 이벤트 루프 스레드에서 «동기 DB» 로 도는 구조. 느린 틱 하나가 API 를 그 시간만큼 굳히는 «부류»는 이 커밋이 안 건드린다 — 그것은 판정 406(다음 커밋)의 일이다.

## ⑦ 그때 남아 있던 것

- **판정 406 ① 미착지.** 런처로 도는 설치는 여전히 체인 루프가 «둘»(uvicorn 안 + `run_chain_worker.py`)이었다.
- S-253(소급 버튼이 「소비자 없음」을 말하지 않음) · S-254(배너의 `business_keys` 가 composite 표에서 0 행) «미착지». 소유자가 누른 그 버튼은 이 커밋 뒤에도 `rows_scanned 0` 을 냈을 것이다 — 화면이 보내는 키가 아직 그대로였다.
- 박스 재현은 «스케줄러를 끈» 상태에서 했고, 재현 뒤 스케줄러를 다시 띄웠다. 총괄이 재기동한 PID 는 45712.
- 구현자 채널의 미답 질문 «하나»: PG 실행 시험(SQLite 가 PG 가 거절하는 것을 받는다 — 급하지 않음).

---
📎 이 항목의 수(15 · 5/5 · 6,763 · 344 · 6/6 · PID)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다 — ①의 기제는 코드에서 나온다.
📎 장애 기록: `20260915_223500_the_chain_loop_hot_spun_on_a_control_event_it_could_not_consume_and_froze_the_api.md` · 같은 부류의 앞선 사고(09-04 크론 수집기 인라인): `20260904_174600_a_collector_doing_its_job_took_the_monitoring_down_and_one_bad_row_held_the_whole_queue.md` · 다음 커밋(체인 루프의 «집»): `20260915_233809_the_launcher_stands_the_apis_chain_loop_down_and_the_off_switch_had_never_run.md`.
