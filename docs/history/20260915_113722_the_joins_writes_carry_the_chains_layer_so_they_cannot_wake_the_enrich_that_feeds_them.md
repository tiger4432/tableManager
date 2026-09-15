# 조인의 쓰기가 «체인의 층»을 달게 됐다 — 규칙 이름을 층에 적은 것이 깨우기 필터를 «지나치고» 있었다

> **커밋:** `1aa50d3d` — fix(join_into): the join's writes carry the chain's layer, so they cannot wake the enrich that feeds them
> **일자:** 2026-09-15 11:37
> **레인:** 총괄(S-249 산정 중 «문 셋» 가운데 ③ 을 바로 고침, 큐 `815` 행)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 기존 시험 **1** 수정(`test_the_written_layer_is_the_rules_own_name` — 단언이 «층 = 규칙 이름»에서 «층 = 체인 · 저자 = 규칙 이름»으로). 커밋 메시지에 모집단 수 «없음».

## ① 왜 — 소유자 「핑퐁은 제대로 고쳐 이거때문에 어제부터 운영 동작 제대로 못함」

```
소유자 원문    inventory -> join 으로 log 에 -> enrich -> inventory -> … 반복
워커의 깨우기  아웃박스 payload 의 `source_name` 을 읽는다:
              `chain_ingestion` 이면  -> allow_chain_trigger 를 «선언한» 규칙만 깨운다
              그 밖의 라벨이면       -> 그 표의 «모든» 규칙을 깨운다 (사람 편집으로 본다)
S-237 의 join  «읽기 좋으라고» 규칙 이름을 «층»에 적었다  (`source_name=<규칙 이름>`)
=> 이 종류의 «모든» 쓰기가 필터에겐 사람 편집으로 보였고, dt_log 를 읽는 dedup 이 join 이 dt_log 에 쓸 때마다 다시 돌았다
```
🔴 부류: **「한 이름이 두 뜻」** — `source_name` 은 «층 이름»이면서 «깨우기 필터의 판별 키»였다. 층에 이름을 적는 «좋은 뜻»이 필터의 «다른 뜻»을 건드렸다.

## ② 변경 — 층은 체인의 것, 저자는 규칙의 것

```python
# server/chain/join_into.py
CHAIN_LAYER = "chain_ingestion"     # 모든 체인 쓰기가 다는 «하나»의 층. 워커의 깨우기 필터가 정확히 이것을 읽는다
...
schemas.GeneralUpdateItem(
    row_id=..., updates=...,
    source_name=CHAIN_LAYER,        # <- 층: 체인
    updated_by=source_name)         # <- 저자: 규칙 이름 (규칙마다 상수라 같은 값은 no-op 쓰기로 남는다)
```
```python
# 시험
assert seen[0].updates[0].source_name == join_into.CHAIN_LAYER
assert seen[0].updates[0].updated_by == DECLARATION["name"]
```
🔵 운영자가 「누가 이 셀을 썼나」를 잃지 않는다 — `updated_by` 가 규칙 이름을 그대로 든다. 옵트인(`allow_chain_trigger`)이 체인 쓰기가 규칙을 깨우는 «유일한» 문으로 돌아왔다.

## ③ 아키텍처 영향

- 「체인이 쓴 행은 체인을 다시 깨우지 않는다 — 선언으로 켠 것만 예외」가 join 종류에도 걸리게 됐다. 이 원칙은 «라벨 하나»로 강제된다(`source_name == chain_ingestion`) — 라벨을 다르게 적는 새 종류가 생기면 같은 자리에서 «같은 모양»으로 깨진다.

## ④ 그때 남아 있던 것 — 고리의 «한 변»만 닫혔다

- 커밋 메시지가 스스로 적었다: **「이것은 소유자가 보고한 고리의 «한 변»을 닫는다.」** 다른 문 — 뒤따르기 랩(`_run_builtin_followups`)이 «모든» 아웃박스 이벤트에 «라벨도 옵트인도 없이» follow_up 종류 전부를 돌린다 — 는 그대로였고, S-249 로 구현자에게 «수렴 게이트»와 함께 지시됐다.
- 큐 S-249 의 실측이 문 «셋»을 셌다: ① 이벤트 술어는 라벨로 거른다 ② 뒤따르기 랩은 큐 «전부»를 옵트인 없이 받는다 ③ join_into 의 층 이름이 ①을 지나쳤다. 이 커밋은 ③ 이다. ②는 별 항목(`20260915_125527`).
- 12:3x 총괄 실측(`e1b6bb0b`)이 「③ 은 이 고리의 «입구»였고, 어제부터의 고리는 auto_confirm(inventory 자기 뒤따르기)이 «같은 자리(②)»에서 돈다」고 적었다 — 즉 이 커밋만으로는 소유자의 「무한 실행」이 멎지 않았다.
- 재기동은 이 커밋 단독으로 없었다. 뒤 첫 재기동은 S-248 의 PID 22964(12:0x).

---
📎 「운영」이라 적은 줄은 소유자 원문뿐이다. 수를 낸 줄은 없다.
📎 S-237 이 층에 규칙 이름을 적은 «이유»(운영자가 누가 썼는지 보게): `20260915_093113_the_day_strictness_invalidated_what_was_already_running.md` §②.
