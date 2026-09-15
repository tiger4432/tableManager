# 런처가 API 자식의 체인 루프를 «물러나게» 한다 — 그리고 그 끄는 스위치는 «한 번도 돈 적이 없었다» (판정 406)

> **커밋:** `86016d10` — fix(launcher): the chain loop runs in its own process, and the off switch now works · `f7f89ab9` — fix(launcher): move the 406 comment above the spec list - two oracles read this file as text
> **일자:** 2026-09-15 23:38 · 23:44
> **레인:** 구현자(서버) — 판정 406(`795ac1e6`) → 착지 → 보고 `4d446597` → 총괄이 빨강 둘 실측(`76ec2a16`) → 주석 이동 → 총괄 닫힘 `79f92844`(「재기동 PID 30600」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.** ①의 구조는 코드의 것이다.
> **스위트:** 신설 **6** · `--collect-only` **6,769** 에러 0 (구현자 보고). `86016d10` 위에서 총괄이 잰 빨강 **둘**(런처를 «텍스트로» 읽는 기존 오라클) → `f7f89ab9` 뒤 런처·수퍼바이저·406 모집단 **58 passed**(구현자) · 총괄 「런처·감독 모집단 초록 · 단독 기동 WARNING 한 줄 박스 부팅에서 실측」.

## ① 왜 — 소유자 「과연 이런 문제 요소가 한두 개일까?」

S-252 는 «사례»였다. 구조는: 체인 루프의 본체가 «동기 DB 작업»이고 `main.py` 가 그것을 `create_task` 로 이벤트 루프에 «얹는다» — 그러면 «어떤» 느린 틱(질의 하나·맵퍼 하나·고리 하나)이든 그 시간만큼 «모든» HTTP 요청이 굳는다. 그 행 하나만 고치면 모양이 그대로 선다.

그리고 답은 «런처에 반쯤 이미 있었다»: `run_decoupled_app.py` 는 `run_chain_worker.py` 를 «자기 자식»으로 띄우면서 API 자식에게 물러나라고 «안 했다». 런처로 도는 설치는 체인 루프가 «둘», 그중 하나가 uvicorn 안이었다.

## ② 변경 — 런처 한 줄, 그리고 그 한 줄이 «정상 경로»로 만드는 갈래

```python
# run_decoupled_app.py
ChildSpec("Backend FastAPI Server", server_cmd, server_dir,
          env={"DECOUPLED": "True", "ASSY_CHAIN_WORKER": "0"},     # <- 판정 406 ①
          ...)
```
```python
# server/main.py — startup_event
if _chain_switch in ("0", "false", "off", "no"):
    logger.info("[Chain Worker] NOT started in this process: ASSY_CHAIN_WORKER=%s. Under the launcher this is CORRECT ...")
else:
    chain_task = main_loop.create_task(start_chain_ingestion_worker(SessionLocal))
    logger.warning("[Chain Worker] running INSIDE the API process - a slow tick blocks every HTTP request for that long. ...")
# ⛔ ONLY IF ONE WAS STARTED. 종전엔 조건 없이 돌았다 — off 갈래에서 chain_task 는 None
if chain_task is not None:
    chain_task.add_done_callback(_log_chain_worker_exit)
    logger.info("Chained Ingestion Worker background task spawned.")
```

## ③ 🔴 끄는 갈래는 «한 번도 돈 적이 없었다» — 가드는 도달 가능해지는 날 틀린다

`ASSY_CHAIN_WORKER` 는 09-14 장애 때 «킬 스위치»로 생겼다. 그런데 off 갈래에서 `chain_task` 가 `None` 인 채 `add_done_callback` 이 «조건 없이» 돌아 `AttributeError` 를 던졌고, 그것이 아래 핸들러에서 「Startup step failed (watcher/chain worker)」로 보고됐다. 아무도 그 스위치를 «안 써서» 아무도 못 만났다. 판정 406 ① 이 바로 그 갈래를 «모든 런처 설치의 정상 경로»로 만드는 날이었다 — 한 커밋 차이로 운영에서 터질 뻔한 자리.

**로그 등급이 뒤집혔다:** 물러남은 `info`(런처 아래선 «올바른» 상태 — warning 이면 정상 기동마다 경고가 난다). 반대로 «API 안에서 도는» 경우가 `warning` 이다 — 단독 기동(박스·개발)은 그대로 두되, 그 사실이 «조용했던» 것이 운영에 루프를 들여놓은 병이었다.

**executor 로 안 옮겼다** — 그러면 체인을 돌리는 길이 «둘»이다. S-252-b 는 판정 406 으로 여기서 닫혔다.

## ④ `f7f89ab9` — 옳은 코드가 «주석 자리» 때문에 빨개졌다

총괄이 `86016d10` 에서 빨강 둘을 쟀고, 구현자의 코드가 낸 것이 아니었다. 새 주석이 `ChildSpec("Backend FastAPI Server", …)` «안»에 있었고, 기존 시험 둘이 이 파일을 «텍스트로» 읽는다 — 하나는 `ChildSpec(` 뒤 «420 자 창»을 잡고, 다른 하나는 `run_chain_worker.py` 의 «첫 언급»을 정규식으로 잡는다. 주석이 `log_file=` 을 창 밖으로 밀었고, 정규식에는 «주석 안의» 낱말을 줬다.
```
수리      문장은 그대로, 자리만 `specs = [` «위»로 — 창이 닿지 않는 곳
안 한 것   오라클 둘을 값(import 한 spec 목록의 `log_file`/`heartbeat`)으로 고치는 것 — S-255 로 큐.
          «텍스트 대리»는 금지 모양이 맞지만, 그 재작성을 «주석 이동» 안에 넣으면 라운드가 둘이 된다
```

## ⑤ 게이트가 재는 것은 «텍스트»다 — 구현자가 그대로 말했다

런처의 자식 명세는 «설정»이라 그것을 읽는 것은 주어를 읽는 것이다. 그러나 `main.py` 쪽 두 단언은 `inspect.getsource` 로 «소스»를 읽는다 — FastAPI 기동을 세우지 않고는 못 몰았다. 진짜 증거는 «런처 기동 뒤 API 자식의 환경에 그 변수가 있고 체인 심박이 둘이 아니라 하나» — 그것은 재기동이고 총괄 몫이다. 이 커밋 시점의 새 시험 파일 하나가 «그 자리에서» 이 사실을 자기 docstring 에 적어 두었다.

## ⑥ 아키텍처 영향

- 체인 루프의 «집»이 코드에 박혔다: 런처 아래서는 «자기 프로세스», API 안은 «단독 기동의 편의»이고 그렇게 «말한다».
- 「같은 기능에 두 경로」의 한 사례가 닫혔다 — 런처 설치에서 «같은 아웃박스를 두 루프가 읽던» 상태.
- 그대로인 것: 루프 본체(동기 DB) · `run_chain_worker.py` · 09-14 의 킬 스위치 이름과 값 어휘.

## ⑦ 그때 남아 있던 것

- 「체인 심박이 둘이 아니라 하나」를 «본» 기록은 닫힘 줄에 없다. 총괄이 잰 것은 시험 모집단 초록과 «단독 기동의 WARNING 한 줄»(박스 부팅). 재기동 PID 30600 이 런처 모양이었는지는 닫힘 줄이 적지 않았다.
- S-255(런처를 텍스트로 읽는 오라클 둘 → 값으로) «큐».
- S-254 · S-251 · S-241 · S-234 순으로 «미착지». 소유자가 누른 소급은 이 시점에도 화면에서 `rows_scanned 0` 이었다(다음 커밋).

---
📎 이 항목의 수(6 · 6,769 · 58 · 420 자 · PID)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 ①·③의 «구조 주장»뿐이고, 그것은 코드에서 나온다.
📎 앞 커밋(사례 수리): `20260915_233348_the_chain_loop_fetches_only_what_it_can_consume_and_a_dead_tick_still_yields.md` · 킬 스위치가 태어난 장애: `20260915_094114_off_still_touched_the_database_and_a_probe_poisoned_the_read.md` · 「가드는 도달 가능해지는 날 틀린다」의 앞선 사례들은 2026-08-19 계열.
