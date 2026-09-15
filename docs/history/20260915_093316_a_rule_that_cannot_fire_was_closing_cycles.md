# 발화할 수 없는 규칙이 고리를 «닫고» 있었다 — 순서 걷기가 트리거 경로와 «같은 질문»을 하게 됐다

> **커밋:** `ea8f91d2` — fix(chain): a rule that cannot fire cannot order anything, so it cannot close a cycle
> **일자:** 2026-09-15 09:33
> **레인:** 총괄 측 직접 착지(D-38 보고 시점 구현자는 «정지» 상태 — 커밋 트레일러는 Opus 4.8)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.** 다만 «계기»는 운영 신고다 — 수는 여기서 낸 것이 없다.
> **스위트:** 순서·재생·조인·로더 모집단 **69 passed** (커밋 메시지 기재. 제가 다시 돌리지 않았다).

## ① 왜 — 소유자의 질문 하나가 정확히 그 자리를 찍었다

운영에서 체인 규칙 «고리»가 신고됐다. 소유자가 물은 것: **「enable false 여도 고리 인식하나?」** — 답은 «예, 그랬다».

```
트리거 경로   규칙을 «돌리기 전» 두 가지를 묻는다
              · follow_up 종류   -> `_rule_accepts_event` 가 False
              · enabled: false   -> SKIPPED_DISABLED
순서 걷기     (`chain/rule_order.py`, 09-13 S-156)  둘 다 «안 물었다»
결과          꺼 둔 규칙이 이웃을 계속 «순서 짓고» 있었고,
              통합 join(S-237)이 내는 오른쪽 규칙(right -> left, follow_up, 트리거 경로에 «절대» 안 오름)이
              살아 있는 left -> right 규칙 «아무것»과 만나 «발화 못 하는 엣지 하나»짜리 고리가 됐다
```
🔴 **판정 387·388(09-13 밤)의 «셋째 판»이다.** 387 이 예외를 이름에서 성질로, 388 이 그 성질의 넓이를 좁혔는데,
빠진 성질이 하나 더 있었다 — «발화 가능성». 순서는 「무엇을 읽고 쓰나」만 봤고 「돌기는 하나」를 안 봤다.

## ② 변경 — 걷기가 트리거 경로의 질문을 «그대로» 묻는다

```python
# server/chain/rule_order.py  order_rules()
for producer in by_target.get(trigger, []):
    if not producer.get("enabled", True) or producer.get("follow_up"):
        continue  # not on the trigger path: it fires nothing, it orders nothing
    if (producer.get("trigger_table") == trigger
            and rule.get("target_table") == trigger):
        continue  # both ends live on `trigger`: no order exists between them
```
열한 줄. 두 live·non-paced 규칙이 표를 건너 서로를 먹이는 «진짜» 고리는 여전히 이름 대어 거절된다
(`test_a_real_cycle_between_two_live_rules_is_still_refused_by_name`).

## ③ 시험 «둘»이 뒤집혔고, 둘 다 «시험이» 틀렸었다

```
join 시험   「paced 참조 규칙이 «먼저» 온다」를 09-13 부터 고정하고 있었다
            -> follow_up 규칙은 트리거 그룹을 «한 번도» 공유하지 않으므로 「먼저/뒤」에 조작적 내용이 «없다».
               게다가 «바로 그 엣지»(right -> left, paced)가 운영의 유령 고리였다
            -> 지금은 «파일 순서 그대로»를 단언하고, 이유를 주석에 남겼다
새 시험     뒤집은 입력에 뒤집은 출력을 기대했다 -> 틀렸다. 걷기는 post-order DFS 라 답은 «그래프의 성질»이지
            «파일 순서의 성질»이 아니다. 이제 `forward == reverse` 를 단언한다
```
📌 부류: **「이 축을 이미 단언하는 시험이 무엇을 «고정»하고 있나」** — 단언이 틀린 성질을 고정하면 옳은 수리가
빨개지고, 그 빨강을 「회귀」로 읽으면 수리를 되돌리게 된다. 둘 다 «왜 뒤집었나»가 시험 본문에 있다.

범위 고정(388 의 규율 그대로): `test_a_switched_off_producer_no_longer_orders_its_consumer` — `t` 를 쓰는
꺼진 규칙이 `t` 를 읽는 live 규칙 «앞»에 오던 것이 이제 안 온다. 되돌아가면 «일부러» 빨개진다.

## ④ 그때 남아 있던 것

- **「current transaction is aborted」는 이 커밋으로 안 풀렸다.** 커밋 메시지가 스스로 적었다 — 그것은 «오염된
  트랜잭션»이고 자기 롤백 경로가 필요하다. 유령 고리는 그 장애의 «방아쇠»였을 뿐이다. 8분 뒤 `1497ea3e`,
  14분 뒤 `e88cb2be` 가 그 자리다(각각 별 항목).
- 순서 걷기와 트리거 경로는 여전히 «두 자리»에서 «같은 질문»을 «각자» 묻는다(`enabled`·`follow_up` 을 두 곳이
  읽는다). 이 커밋은 답을 «맞춘» 것이지 자리를 «합친» 것이 아니다.

---
📎 「운영」이라 적은 줄은 소유자 신고를 옮긴 것뿐이고, 수를 낸 줄은 없다.
📎 판정 387·388 의 항목: `20260913_235436_the_order_landed_twice_and_a_view_pages_by_its_composite.md`.
