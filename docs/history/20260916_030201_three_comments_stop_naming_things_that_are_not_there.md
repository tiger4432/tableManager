# 주석 «셋»이 오늘 참인 것을 말한다 — 런처는 uvicorn 안에서 고리를 돌린 «적이 없고», PG 러너의 거절은 2 가 아니라 64 이며, 원장 라우터의 절 머리글이 «은퇴한 라우트»를 부르고 있었다

> **커밋:** `585adbc5` — docs(code): two docstrings say what is true … · `fcabe5ff` — docs(main): the ledger router's section header names a route that still exists
> **일자:** 2026-09-16 03:02 · 07:01
> **레인:** `585adbc5` — 밤 문서 정비 패스 «사이»에 착지(히스토리 동기화 `4d818349` 03:00 ↔ 리빙 문서 `5309ceb1` 03:06). 커밋 본문에 공동 저자 표기도 게이트 줄도 «없다». · `fcabe5ff` — 구현자, S-259 «검수 중» 발견 → 총괄 닫힘 `ce56b2d1` 흐름에 포함
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** `fcabe5ff` — `test_health_endpoint` · `test_ledger_subgraph` **84 passed / 1 skipped**(이 파일의 «등록 순서»를 단언하는 둘). `585adbc5` — 커밋 본문에 «없다».

## ① 왜 — 주석은 «의도»의 증거이지 «동작»의 증거가 아니다

셋 다 «틀린 자리로 사람을 보내는» 문장이었다. 코드는 옳았고 코드 옆의 설명이 틀렸으며, 그래서 검토로는 안 보인다 — 읽는 사람이 그 문장을 «전제»로 들고 다음 걸음을 뗄 때만 값이 나온다. 그리고 이 셋 중 하나는 **그 값이 이미 치러진 뒤에** 잡혔다.

## ② 런처 — 「고리가 둘이었고 하나가 uvicorn 안에 살았다」가 거짓이었다

```python
# server/runtime/launcher_specs.py
#  전: "without that, a launcher-run deployment had TWO chain loops and one of them lived
#       inside uvicorn"
#  후: "⚠️ This is a SECOND, explicit guard, not the first: `main.py` already returned
#       before the chain start when `DECOUPLED=True` (which the launcher passes), so a
#       launcher-run deployment never had the loop inside uvicorn - the board corrected
#       that claim on 2026-09-16 02:1x."
```
`ASSY_CHAIN_WORKER=0` 은 **첫째 가드가 아니라 둘째**다. 그것이 막는 모양(체인 고리가 uvicorn 의 이벤트 루프 스레드를 느린 틱마다 붙든다)은 **손으로 띄운 uvicorn** 에 대해서는 여전히 실재하고 S-252 가 그 한 사례다 — 다만 런처로 띄운 배치에 대해서는 «참인 적이 없었다». 주석은 그 구분을 적는 쪽으로 바뀌었고, 판정 406 의 근거가 아니라 «환경으로 그 사실을 말하는 줄»이 됐다.

## ③ PG 러너 — 거절 코드가 2 가 아니라 64

```python
# server/scripts/run_pg_tests.py — 산문 두 자리의 "exit 2" -> "exit 64"
REFUSED = 64      # pytest 의 0·1·2·3·4·5 «어느 것과도» 안 겹치게 고른 값
```
`64` 를 고른 이유가 「pytest 의 종료 코드와 겹치지 않게」인데, 같은 파일의 머리 산문이 두 자리에서 «2» 라고 적고 있었다 — 즉 문서가 그 선택의 «이유를 스스로 지우고» 있었다. 거절을 skip 이 아니라 «종료 코드»로 내는 이유(S-104 · S-115 — 건너뛰기가 그 증명들을 몇 달 조용하게 만들었다)는 그대로다.

## ④ `main.py` — 절 머리글이 은퇴한 라우트를 부르고 있었다

```python
# 전: # --- Ledger lineage trace (GET /api/ledger/trace) --------------------------
# 후: # --- Ledger read routes (GET /api/ledger/subgraph and nine others) ---------
#     # ⚠️ THIS LINE USED TO NAME `/api/ledger/trace`, WHICH IS RETIRED. ...
#     #    S-259 spent a pass finding out it was gone.
```
`/api/ledger/trace` 는 은퇴했고 `ledger/trace_router.py` 자신의 docstring 이 «오늘 여는 열 개»를 적는다. 🔴 **이 문장의 값은 이미 치러졌다** — S-259 가 「이 주어가 아직 있나」를 알아내는 데 한 패스를 썼고, 그 끝에 없어졌다는 결론에 닿았다. 등록 순서와 그 이유(FastAPI 가 등록 순서로 매칭하므로 SPA 캐치올보다 «먼저» 서야 한다)는 한 글자도 안 바뀌었다.

## ⑤ 아키텍처 영향 — «없다»

셋 다 주석이다. 런처의 자식 스펙 · PG 러너의 종료 코드 · `main.py` 의 라우터 등록과 순서는 그대로다. 바뀐 것은 **읽는 사람이 어디로 가나**다.

## ⑥ 그때 남아 있던 것

- `585adbc5` 에는 «게이트가 적혀 있지 않다». 주석만 바꾼 커밋이고 스위트 결과가 본문에 없으며, 공동 저자 표기도 없다.
- 런처 주석의 정정은 «보드의 정정을 따라간» 것이다. 손으로 띄운 uvicorn 에서 그 모양이 실재한다는 것을 이 커밋이 «다시 재지는 않았다» — S-252 를 인용한다.
- `main.py` 머리글의 「열 개」는 `trace_router` 자신의 docstring 에 기대는 수다. 이 커밋이 그 수를 다시 세지 않았다.
- 같은 부류(코드 옆 문장이 낡음)가 이 날 «다른 자리»에도 남아 있었다 — 보드 `54727036` 가 문서 정비를 「커밋 11+」로 적는다.

---
📎 이 항목에는 측정 수가 «둘»뿐이다(84/1 · 64). 「운영」이라 적은 줄은 없다.
📎 런처 주장의 정정이 난 자리: `20260916_021201_the_launcher_roster_is_a_value_the_oracles_import_and_it_carried_a_premise_the_board_had_already_refuted.md`(S-255) · PG 러너가 생긴 날: `20260916_022404_the_postgresql_only_proofs_get_a_seat_and_the_first_run_showed_what_skipping_had_hidden.md`(S-256).
📎 부류: 「주석은 «의도»의 증거이지 «동작»의 증거가 아니다」(2026-09-04).
