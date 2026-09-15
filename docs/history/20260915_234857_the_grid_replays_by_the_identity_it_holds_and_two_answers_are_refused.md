# 그리드는 «자기가 든 신원»(`row_id`)으로 소급을 건다 — 그리고 «한 물음에 두 답»은 교집합이 아니라 «거절»이다 (S-254 서버 절반)

> **커밋:** `fe2d0c6c` — feat(replay): the grid replays by the identity it holds - row_id
> **일자:** 2026-09-15 23:48
> **레인:** 구현자(서버) — 22:3x 장애의 셋째 발견 S-254 → 착지 → 보고 `69149d38` → 총괄 닫힘 `2cb960e1`(「S-254 서버 절반 닫힘 · C-112 초인종」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **7** · 변이 **6/7**(일곱째는 «무해», 아래 ⑤) · `--collect-only` **6,776** 에러 0 (구현자 보고). 기존 시험 «하나»가 이 라운드의 구멍을 잡았다(④).

## ① 왜 — 오류 없는 0

소유자가 dt_log 행에서 「다시 돌리기」를 눌렀고 결과는 `rows_scanned 0` — 오류 없음, 돌아간 것 없음, 아무 말 없음. dt_log 는 `composite_key_source` 표라 저장된 `business_key_val` 은 «조립된 문자열»(`GEN-dt_cell_key-…`)로 «어느 컬럼에도» 없다. 배너는 «보이는 것»(`DT_JOB_ID PROBE-…`)을 업무 키로 보냈다. 두 세계가 만난 적이 없다.

🔴 「없어서 0」과 「못 찾아서 0」은 화면에서 «같아 보이고», 둘 다 다음 행동이 「다시 누른다」다 — 다섯 개의 0 중 최악.

## ② 변경 — `row_ids` 를 «옆에» 둔다, «대신»이 아니라

```python
# server/chain/replay.py — replay_rule(..., business_keys=None, row_ids=None, ...)
if row_ids is not None and business_keys is not None:
    raise ReplayRefused("both row_ids and business_keys were given; they are two answers to 「which rows」. Send one - the grid holds row_ids, the CLI takes business keys.")
if row_ids is not None:
    ids = [str(value).strip() for value in row_ids if str(value).strip()]
    if not ids:
        raise ReplayRefused("row_ids was given but empty; an empty selection would replay the whole rule instead of nothing. Omit it to replay everything, on purpose.")
    selection = trg_model.row_id.in_(ids)
elif business_keys is not None:
    ...                                         # 종전 그대로
```
```python
# server/admin/retroactive.py — chain_replay 연산: 파라미터 선언 + «두 좌석» 모두 전달
_p("row_ids", required=False, kind="csv", help="replay only these rows, by row_id - the identity a grid holds for every table. ... Sending both is refused"),
"cli": ("server/scripts/chain_replay_cli.py replay <rule> [--business-keys a,b,c] [--row-ids r1,r2] [--pace slow] --apply"),
```
`row_id` 는 그리드가 «모든 표»에서 드는 «하나»의 신원이다(평키든 composite 든). `business_keys` 는 그대로다 — CLI 가 받고, 평키 표 운영자는 그것으로 생각한다.

## ③ 왜 «거절»인가 — AND 도, 한쪽 우선도 아니다

둘은 「어느 행이냐」에 대한 «두 답»이다. AND 하면 «둘 다 아닌» 교집합을 돌리고, 한쪽을 조용히 이기게 하면 다른 칸이 «거짓»이 된다 — 둘 다 이 라운드가 없애러 온 «조용히 틀린 답» 모양. 빈 목록도 거절이다(「필터 없음」으로 읽히면 «표 전체»를 돌린다 — 소급이 비싼 바로 그 방식으로). 공백만 든 항목(`["", "  "]`)은 «길이를 두른 빈 선택»이라 strip 뒤에 센다.

## ④ 기존 시험이 구멍을 잡았다 · 첫 판은 «가짜를 재고» 있었다

```
잡힌 구멍   `test_every_parameter_a_button_takes_is_findable_in_the_cli_line_it_promises` 가 빨강 —
           버튼에는 넣고 CLI 에는 «안 넣어서», 화면이 «약속한 명령줄이 표현 못 하는» 것을 내밀 뻔했다.
           플래그(`--row-ids`)와 약속 줄 둘 다 넣었다
첫 판의 결함  선택 조건을 재는 시험이 모델을 «가짜»로 만들어 조건이 튜플로 돌아왔다 — «가짜를 재는» 것.
           바뀐 것은 «어느 컬럼을 거르나»이고 그것은 «컴파일된 SQLAlchemy 절»에 보인다. 그쪽으로 고쳤다
```

## ⑤ 일곱째 변이는 «무해»이지 «탈출»이 아니다

`row_ids` 가 `business_keys` 를 조용히 이기게 해도 «위의 거절이 먼저» 걸려 아무것도 안 바뀐다. 두 가드가 겹치는 것은 의도(belt and braces)이고 구멍이 아니다 — 변이 채점의 어휘로 INERT.

## ⑥ 아키텍처 영향

- 소급의 «행 선택» 축이 둘이 됐고(업무 키 · row_id), 둘의 «동시»는 거절이다. 선택 축의 «이름»은 연산 선언(`OPERATIONS["chain_replay"]["params"]`)이 갖는다.
- 버튼과 CLI 가 «같은 인자»를 든다 — 그 계약은 기존 시험이 이미 강제하고 있었고 이번에 «걸렸다».
- 그대로인 것: `business_keys` 경로 · `limit`(«몇 행을 훑나»는 여전히 별도 축) · `find_rule` · pace.

## ⑦ 그때 남아 있던 것

- **클라 C-112 미착지.** 배너는 이 시점에도 `business_keys` 를 보내고 있었다 — 서버가 받을 수 있게 됐을 뿐, 소유자가 누른 그 버튼은 여전히 `rows_scanned 0` 이었다.
- «두 좌석 전달» 단언은 `inspect.getsource` 로 소스 문자열을 읽는다 — 시그니처가 아니라 «호출 인자»를 잰다는 점에서 목적은 맞지만 텍스트 대리다. 이 커밋은 그것을 그대로 두었다.
- 「row_ids 의 행이 이 규칙의 트리거 표가 아닐 때」의 답은 안 쟀다(클라 보고가 뒤에 같은 미지를 적는다).

---
📎 이 항목의 수(7 · 6/7 · 6,776)는 구현자 보고의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 장애 기록 §④(S-254 의 발견): `20260915_223500_the_chain_loop_hot_spun_on_a_control_event_it_could_not_consume_and_froze_the_api.md` · 클라 절반: `20260916_000955_the_banner_sends_row_ids_and_names_the_rows_that_have_none.md` · 「다섯 개의 0」·「없어서 0 은 무해해서 0 이 아니다」(2026-08-06 계열).
