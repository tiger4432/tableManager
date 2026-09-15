# 고리 줄은 「S-247 의 모양」이라 «적어 놓고» 그 모양을 손으로 철자하고 있었다 — 저자 하나를 만든 라운드 «안»에서 둘이 됐다

> **커밋:** `d469bacf` — fix(logs): the cycle note goes through the author it claimed to follow (S-247-b)
> **일자:** 2026-09-15 16:30
> **레인:** 구현자(서버) — 발견은 코드맵 정비(`9b4ce014`) → 큐 S-247-b `58d2c9a4` → 착지 → 보고 `9d3d1f8b` → 총괄 닫힘 `94a0eaee`(「재기동 PID 52960」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **2** · 네 자리 파라미터 게이트에 **다섯째 자리** 추가 · 변이 **3 «전부» 빨강** · 고리·캐스케이드·거절 줄 모집단 **134 passed** (구현자 보고). 총괄 확인 「214 passed · 부팅 오류 0 · 체인 17」.

## ① 왜 — 증거가 «읽지 않고도» 잰다

S-247(`3aab7173`, 40분 전)이 거절·알림 줄의 저자를 `operator_line` «하나»로 세웠다. 그 라운드의 `rule_order.cycle_note` docstring 은 「S-247 이 모든 운영자 줄에 준 모양으로」라고 적어 두고, 본문은 그 모양을 **문자열 포맷으로 손으로** 짜고 있었다.
```
operator_line.nothing_to_do   호출자 «0»    <- 읽는 쪽 없는 어휘 칸
rule_order.py                 operator_line import «0»
```
🔴 이 결함은 S-240·S-243 이 잡던 «바로 그 부류»(문법엔 있고 읽는 쪽이 없다)이고, 그 부류를 고치는 라운드 «안»에서 구현자 자신이 만든 것이다. 코드맵 정비가 「호출자 0」으로 잡았다 — 산문을 읽어서가 아니라 «수»로.

## ② 왜 호출자가 0 이었나 — 문장에 «한 호출자의 사실»이 박혀 있었다

```python
# 첫 판 (S-247)
def nothing_to_do() -> str:
    return "없음 — 이 줄은 «건너뛴 것»을 셉니다. 나머지 행은 정상으로 처리됐습니다"
```
「이 줄은 건너뛴 것을 셉니다」는 고리 알림에 «거짓»이다 — 고리 줄은 아무것도 세지 않는다. 그래서 고리 줄이 그 함수를 «부를 수 없었고», 손으로 철자하는 길로 갔다. 어휘 칸이 «한 자리에서만 참인 것»을 말하면 다른 자리는 그 칸을 못 쓴다.

```python
# server/operator_line.py  (이 커밋)
def nothing_to_do(unless: str = "") -> str:
    return ("없음 — 이 줄은 «알림»이고 지금 조치할 것이 없습니다"
            + (" (%s)" % unless if unless else ""))

# server/chain/rule_order.py  cycle_note
import operator_line
return operator_line.line(
    "ChainRules", " -> ".join(str(node) for node in trail),
    "고리 (순서는 선언 순 · 홉 상한 max_chain_depth=%s 이 막습니다)" % (ceiling if ceiling is not None else "기본값"),
    operator_line.nothing_to_do("더 긴 고리가 필요하면 chain_rules.json 의 max_chain_depth"))
```
```
어느 호출자에게나 참인 것만   본문에
그 자리에만 참인 조건         `unless` 로 — 고리 줄은 「더 긴 고리가 필요하면 max_chain_depth」를 «둘째 다음: 절을 지어내지 않고» 지킨다
```

## ③ 시험 — 「한 저자」를 «믿지 않고 잰다»

`test_every_seat_goes_through_the_one_renderer` 파라미터 목록(join_into._write · crud.refuse_virtual_join_duplicates · crud.apply_batch_updates · unique_key.describe)에 `chain.rule_order.cycle_note` 가 **다섯째**로 들어갔다. 그리고 「`nothing_to_do()` 에 «건너뛴» 이 없다」를 따로 단언한다 — 한 호출자의 사실이 다시 박히면 빨개진다.

## ④ 아키텍처 영향

- 부팅 로그의 고리 알림이 다른 거절·알림 줄과 «같은 접두 모양»(`[ChainRules:<trail>] ... → 다음: ...`)이 됐다. 운영자가 로그에서 이 줄을 찾는 방법이 하나로 모였다.
- `nothing_to_do` 가 «자리별 꼬리»를 받는다. 「없음」 행동이 «조건부 없음»을 말할 수 있다.

## ⑤ 그때 남아 있던 것

- 총괄 재기동 PID 52960 은 부팅 확인이다. 실제 고리가 선언된 라이브에서 이 줄이 «새 모양으로 찍힌 것»을 본 기록은 이 시점에 없다(이 박스의 체인 17 에 고리가 있는지 이 항목은 재지 않았다).
- 구현자의 앞선 물음(PG 실행 시험)은 그대로 열려 있었다.
- 다섯 자리 밖에 `operator_line` 을 «지나야 하는데 안 지나는» 줄이 더 있는지는 이 라운드가 세지 않았다 — 이 발견은 코드맵 정비가 «호출자 0» 하나를 본 것이지 전수 훑기가 아니다.

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 저자 하나를 세운 라운드: `20260915_155029_every_refusal_line_says_what_to_do_next_because_nobody_can_ask.md` · 「고리는 모양이지 오류가 아니다」(cycle_note 가 태어난 자리): `20260915_121153_a_cycle_is_a_shape_not_an_error_said_once_refused_nowhere.md`.
