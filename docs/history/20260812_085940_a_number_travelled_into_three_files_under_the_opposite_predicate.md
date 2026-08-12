# A number travelled into three files under the opposite predicate, and was removed rather than replaced

**Date:** 2026-08-12 08:59 · **Domain:** Server (체인 키 게이트 / 가이드 문서) · **Status:** 착지 — `c315662`

> `e9fd8a6`(23분 전 착지)의 정정이다. 게이트의 **동작은 한 줄도 안 바뀌었다** — 바뀐 것은
> 그 동작을 정당화하려고 인용한 수 하나다.
> 원 항목: [체인은 닫혔고 인제션은 안 닫혔다](./20260812_083609_the_chain_is_closed_and_ingestion_is_not_because_the_gate_landed_one_level_below.md)

---

## 술어가 반대였다

`chain_key_gate.py`, 그 테스트, 그리고 `docs/guide/chain_ingestion_guide.md` **셋 다**
운영이 「그런 행 ~170,000개」를 실측했다고 적고 있었다. 여기서 「그런 행」은 **업무키가 없는**
행이다.

그 수는 `add_business_key_unique_index.py`의 `duplicate_census`가 내놓는 `surplus`다:

```
surplus = rows_in_duplicate_groups - number_of_groups
```

그리고 **양쪽 항이 모두 `WHERE business_key_val IS NOT NULL`로 계산된다.** 즉 그 수는
**키가 «있는데» 중복된** 행의 수다 — 그것이 떠받치던 주장과 **정확히 반대되는 술어**다.

## 왜 바꿔 넣지 않고 빼냈는가

키 «없는» 행의 수는 같은 census의 **다른 필드**(`null_keys` / `nullbk`)이고, **그 운영
값은 추적되는 산출물 어디에도 기록되어 있지 않다.**

그래서 옳은 수가 존재하지 않는다. 두 번째 수를 지어내면 같은 결함을 되풀이하는 것이다.
**수를 빼고, 각 자리에 그 수가 실제로 무엇을 세는지 적어 두었다** — 다음 사람이 그것을
집으려다 멈추게 하려고.

```python
🔴 DO NOT ATTACH THE FIGURE "~170,000" TO THIS PARAGRAPH. It was here and it was wrong.
That number is ``duplicate_census``'s ``surplus`` in ``add_business_key_unique_index.py``:
``rows_in_duplicate_groups - number_of_groups``, and BOTH terms are computed
``WHERE business_key_val IS NOT NULL``. It counts rows that were KEYED AND DUPLICATED -
the opposite predicate to the one this paragraph is about.
```

## 논증은 원래 그 수가 필요 없었다

남은 것은 **기전**과 **한 건의 실증**이다 — 키 없는 행은 지목할 수 없으므로 같은 데이터의
다음 배송이 하나를 더 만든다, 그리고 그런 행 **하나**가
`GET /api/maps/alignment/worklist`를 요청 전체 500으로 만들었다(`c4a3159`).

**한 행으로 충분했다는 문장이 빌려 온 계수보다 강하다.** 수가 논증을 떠받치고 있던 게
아니라 논증 옆에 얹혀 있었고, 얹혀 있는 동안 세 파일로 복사됐다.

## 어떻게 잡혔는가 — 다시 읽어서가 아니다

이 커밋 본문이 스스로 적고 있다: **하루에 두 번째로 내 주장이 그 밑의 측정보다 멀리 갔다.**
그리고 잡힌 방식이 요점이다 — 재독으로 잡힌 것이 아니라, **한 레인에 「인구 전체를 훑어
버킷으로 분류하라」고 지시했고 그 레인에 건네준 전제가 자기 스윕을 통과하지 못했다.**

## 검증 — 돌리지 않았고 그 이유를 적었다

파이썬 두 파일은 **실행이 아니라 구문 검사만** 했다. 그 시점에 `crud.py`를 다른 레인이
쓰고 있었고, **그 트리에서 나온 빨강은 이 변경에 대해 아무것도 말하지 않기 때문이다.**
동작 변경이 0이므로 스위트 수치는 이 항목에 없다.

## 그때 남아 있던 것

- **키 없는 행의 운영 수는 여전히 어디에도 기록돼 있지 않다.** 이 커밋은 틀린 수를
  없앴을 뿐 옳은 수를 만들지 않았다.
- 원 항목(`e9fd8a6`)의 본문은 **그대로 남아 있다** — 히스토리는 불변 기록이라 문장을
  지우지 않고, 대신 그 항목 머리에 이 정정으로 가는 표시를 달았다.
- `c4a3159`가 만든 사실(한 행이 요청 전체를 죽였다)은 이 정정으로 **아무 영향도 받지
  않는다.** 그것은 계수가 아니라 관측이다.
