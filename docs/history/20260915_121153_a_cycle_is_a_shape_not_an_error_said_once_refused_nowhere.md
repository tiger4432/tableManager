# 고리는 «모양»이지 오류가 아니다 — 한 번 말하고, 어디서도 거절하지 않는다

> **커밋:** `2504fbde` — fix(chain): a cycle is a shape, not an error - said once, refused nowhere (판정 402)
> **일자:** 2026-09-15 12:11
> **레인:** 구현자(서버) — 판정 `6337b151` → 소유자 「사이클 오류도 없애줘」로 «첫 커밋»으로 당김 `83ea78f4` → 착지 → 보고 `32d830cb` → 총괄 닫힘 `cd32f9ca`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 다섯 파일의 고리 단언이 「거절」→「이름 대기」로 · 신설 «한 번만 말하기»·«선언 순»·«저장 통과»·«그래프에 고리» · `rule_order`·캐스케이드 검증기·`order_rules`·로더·체인 그래프 모집단 **340 passed** (구현자 보고). 총괄 확인 「88 passed · 부팅 ERROR 0 · 체인 17 · 재기동 PID 32136」(`cd32f9ca`).

## ① 왜 — 소유자 「사이클은 어차피 max depth 로 막혔는데 에러 띄울 이유가 있어? 사이클 오류 계속 뜨네」

```
총괄 실측    홉 상한은 «이미 있다» — event_constants.max_chain_depth(_RULES_DOCUMENT)를 드레인이 «강제»한다
            (「[Chain Depth] … refusing it and marking it finished」)
            => 고리는 «유한»이고, 로드 시점 «거절»은 남는 이유가 없다
고리를 말하던 자리 «셋»
 ① rule_order.order_rules -> RuleCycleRefused  로더가 잡아 logger.error. «순서를 못 정한다»는 뜻뿐, 규칙은 선다.
                                               드레인이 «매 배치» load_chain_rules 를 다시 부르므로 이 ERROR 가 «반복» — 소유자가 본 것
 ② _validate_chain_cascade_graph -> ValueError  «안 잡음» -> 로드가 «죽는다»
 ③ ledger/admin.py 저장 라우트                 ②를 잡아 chain_cycle 로 «저장 거절»
```
🔴 판정: `dt_log → dt_inventory` 맵퍼 + `dt_inventory → dt_log` 조인은 «의도된 고리»다. 그것을 유한하게 만드는 것은 홉 상한이고, 로드 시점 거절은 «돌아가는 선언»을 거절하는 것이었다 — 운영자가 가진 «유일한 문»(저장 라우트)에서.
📌 부류: **「같은 기능에 두 경로」** — 고리를 «막는» 기제가 둘(로드 시점 거절 · 실행 시점 홉 상한)이었고, 하나만 «맞는 답»이었다.

## ② 변경 — 셋 다 «거절 없음», 줄은 «한 번»

```python
# server/chain/rule_order.py
_SAID = set()                                   # 이 프로세스에서 이미 말한 고리, trail 별

def cycle_note(trail, ceiling=None) -> str:      # S-247 이 모든 운영자 줄에 준 모양
    return ("[ChainRules] 고리: %s (순서는 선언 순 · 홉 상한 max_chain_depth=%s 이 막습니다). "
            "다음: 없음. 상한을 바꾸려면 chain_rules.json 의 max_chain_depth" % (...))

def say_cycle_once(logger_, trail, ceiling=None) -> bool: ...   # 처음 만난 trail 만 INFO

def order_rules(rules: list, on_cycle=None) -> list:
    ...
        if state.get(name) == 0:
            found_cycle.append(True)
            if on_cycle is not None: on_cycle(path + [name])
            return                                  # <- 던지지 않는다
    ...
    if found_cycle:
        return list(rules)                          # <- «선언 순». 부분 걷기가 푸는 순서는 «아무도 안 적은 셋째 순서»다
    return ordered
```
```python
# server/chain/ingestion_worker.py
def _validate_chain_cascade_graph(rules) -> list:   # «돌려준다». 어드민 그래프가 이 값을 보여 준다
    ...
            rule_order.say_cycle_once(logger, found, event_constants.max_chain_depth(_RULES_DOCUMENT))
            cycles.append("allow_chain_trigger cycle: " + " -> ".join(found))
            return
    ...
    return cycles
```
```python
# server/chain/graph.py — 예외를 잡던 자리가 «값을 읽는» 자리로. 화면은 «전과 똑같이» 고리를 보여 준다
cycles = list(worker._validate_chain_cascade_graph(chain_rules) or ())
```
🔵 `RuleCycleRefused` 클래스는 «지웠다» — 던지는 곳 0 이면 잔해다. `replay.order_rules` 가 그것을 `ReplayRefused` 로 번역하던 블록도 같이 사라졌다(번역할 것이 없다).
🔴 **검증기가 «로그만» 했으면 어드민 그래프가 조용히 비었을 것이다** — 그래서 raise 를 «return» 으로 바꿨지 «logger.error» 로 바꾸지 않았다. 「고리는 운영자가 다른 어디서도 못 보는 것」이 그 화면의 존재 이유였다.

## ③ 옆 단언 하나가 «산문을 채점»하고 있었다

```
test_the_static_cycle_check_is_untouched  「이 검증기가 depth 칸을 읽나」를 «소스 문자열»로 물었다
=> 구현자가 「raise 를 왜 뺐나」를 설명한 docstring 이 그 낱말을 «들고» 있어 검사를 건드렸다
고침                                      코드 객체(co_names · co_consts)를 묻는다
```
📌 부류: **드리프트 오라클이 «금지를 설명하는 주석»을 읽는다.** 빨강을 푸는 가장 쉬운 길이 «설명을 지우는 것»이 되는 자리 — 같은 날 S-248 이 `failure_cause` 를 함수로 뺀 이유와 «같은 병».

## ④ 아키텍처 영향

- 「고리가 유한하다」는 판정은 `max_chain_depth` 의 드레인 강제 «한 자리»에 산다. 로드 시점엔 이제 «말하기»만 있다.
- `order_rules` 의 계약이 바뀌었다: 고리가 있으면 «선언 순»을 돌려준다. 호출자(로더·리플레이)는 예외를 잡을 것이 없다.

## ⑤ 그때 남아 있던 것

- 총괄이 재기동(PID 32136)하고 「고리 줄이 사라졌다」를 확인했다 — 그러나 **소유자의 「무한 실행」은 이 커밋과 «무관»하다.** 판정 402 는 «로그의 오류 줄»을 없앤 것이고, 고리가 «상한에 안 걸리는» 자리(뒤따르기 랩)는 같은 시각 총괄 실측(`e1b6bb0b`)이 「원인 확정」으로 적어 S-249 ⓒ 가 «바로 다음»이었다.
- 판정 402 가 S-249 ⓒ 를 «정정»했다: 홉 상한은 «새 칸이 아니다» — `max_chain_depth` 가 그것이다. 지시서의 「기본 3」 칸은 만들어지지 않았다.
- 이 채널의 미답 «둘»: S-242 ②의 격리 범위 · S-249 ㉠/㉡/㉢(구현자 픽스처가 «랩 3 에 수렴»해 원인을 못 봄).

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 순서(`rule_order`)의 탄생과 판정 387→388: `20260915_093113_the_day_strictness_invalidated_what_was_already_running.md` §③ · 고리를 닫던 «못 도는 규칙»: `20260915_093316_a_rule_that_cannot_fire_was_closing_cycles.md`.
