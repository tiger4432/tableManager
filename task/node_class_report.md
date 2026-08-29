# ✅ [A 구현자] **정적/동적 착지 — `2f0251e4`. 다만 규칙을 «노드»가 아니라 «걸음»에 걸었습니다** (2026-08-29 14:1x)

## 🔴 먼저 — 지시 ②를 «글자 그대로» 짜면 게이트 ③이 무너집니다. 재서 확인했습니다
지시 본문: 「그 노드의 타입이 static 이면 «펴지 않는다»」
```
그대로 구현하고 게이트 ③을 재 봤습니다 (씨앗 quantity{bond_pressure} · follow=leads_to · hops=4)
   정적 집합 «없음»            nodes 18 · edges 18 · hops_reached 4
   정적 집합 {q, dk, recipe}   nodes «1» · edges «0» · hops_reached «0»    ← 사슬이 통째로 죽습니다
이유   leads_to 는 S→S 이고, 「정적 노드를 안 편다」는 S→S 도 같이 자릅니다
```
그런데 같은 지시서에 소유자 말씀이 그대로 적혀 있습니다 — **「s→s 는 허용이고 s→d 가 금지잖아」.**
그래서 규칙을 «걸음»에 걸었습니다: **near 가 static 이고 far 가 dynamic 이면 그 걸음을 안 갑니다.**
```
옮긴 뒤   정적 집합 {q, dk, recipe}   nodes 18 · edges 18 · hops_reached 4   ← 오늘과 «동일» ✅
```
⚠️ 지시 문장과 다르게 짠 것이라 먼저 올립니다. 되돌리라 하시면 되돌립니다 — 다만 되돌리면
   게이트 ③이 빨강입니다.

## 게이트 ① — 무회귀 (선언에 `class` 가 «하나도 없는» 지금 상태)
지시대로 총괄이 선언을 쓰기 «전»에 쟀습니다. `_static_types()` 가 «빈 집합»을 냅니다.
```
                                     전(HEAD)                    후(2f0251e4)
wafer SYN-BW-101-16 · hops=6 · both · 1000/3000
   nodes / edges                     1000 / 3000                 1000 / 3000
   walk.hops_reached                 2                           2
   truncated                         claims, edges, nodes        claims, edges, nodes
quantity{bond_pressure} · follow=leads_to · hops=4
   nodes / edges                     18 / 18                     18 / 18
   walk.hops_reached                 4                           4
   depths                            {0:1,1:2,2:2,3:6,4:7}       {0:1,1:2,2:2,3:6,4:7}
```

## 게이트 ② — 효과. **선언에 아직 `class` 가 없으므로 «인자로 직접» 먹여 쟀습니다**
라이브 선언은 총괄 것이라 안 열었습니다. 대신 `subgraph(..., static_types=…)` 로 통제 실험을 했습니다.
씨앗 `wafer SYN-BW-101-16` · hops=6 · **both** · node_limit=1000 · edge_limit=3000:
```
                    nodes   edges   walk.hops_reached   truncated
정적 «없음»(오늘)    1000    3000    2                   claims, edges, nodes
정적 {q,dk,recipe}    225     224    2                   claims
타입 분포
   전   wafer «776» · die 117 · defect 89 · quantity 18
   후   wafer «1»   · die 117 · defect 89 · quantity 18
```
🔴 **남의 웨이퍼 775장이 사라집니다** — 지시서가 지목한 그 경로(`quantity`·`defect_kind` 를 거쳐
거꾸로 나가던 S→D)입니다. **노드·엣지 절단이 «꺼집니다».**

### ⚠️ 그런데 `defect_kind` 는 여전히 «안 닿습니다» — 맞춰 놓지 않고 그대로 적습니다
```
후에도 truncated 에 «claims» 가 남습니다. 그 상한은 min(MAX_CLAIM_SCAN=6000, edge_limit×2) 라
edge_limit 을 올려도 «6000 에서 고정»입니다 -> 이 씨앗에서 of_kind 원자까지 못 갑니다
=> 「defect_kind 에 못 닿는다」의 원인이 ④ «하나»가 아니었습니다. ④를 고치니 벽이 «클레임»으로
   좁혀졌고, 남은 것은 별개입니다
```

## 게이트 ③ — 인과 사슬
```
씨앗 quantity{bond_pressure} · follow=leads_to · hops=4 · 정적 집합 적용
   nodes 18 · edges 18 · hops_reached «4» · depths {0:1, 1:2, 2:2, 3:6, 4:7}
   1홉에서 «안 끊깁니다» ✅   (bond_pressure -> die_stress/interface_unfill -> void/delam -> …)
⛔ 정책 ①②③ 은 «구현 안 했습니다». 특히 「1홉」 강제 «없음»
```

## 게이트 ④ — 시험
```
-k "subgraph or setup_bundle or skeleton or explorer"   164 passed · 2 skipped · «7 failed»
🔴 그 일곱은 «제 것이 아닙니다» — 수가 아니라 «목록»으로 확인했습니다:
   네 파일을 HEAD 로 되돌리고 같은 선택으로 돌린 뒤 FAILED 줄을 정렬해 비교 -> «차이 0».
   같은 일곱입니다 (그중 하나가 총괄이 이미 보드에 올린 skeleton↔validator 드리프트 게이트)
```
그 드리프트 게이트가 이미 빨강이라 «제 추가가 가려질 수» 있어, 검증기와 스켈레톤이 실제로
같은 낱말을 아는지 «직접» 태웠습니다:
```
class="static"   -> 통과      class="dynamic" -> 통과
class="sideways" -> invalid_entity_ref  "must be static or dynamic"   (이름 대어 거절)
스켈레톤 엔티티 필드   keys · key_types · allow_null · «class»
```

## 선언에 무엇을 쓰면 되는지 (총괄 몫)
```
"defect_kind@1": { …, "class": "static" }     · quantity@1 · recipe@1 도 같은 값
나머지 여섯(lot·lot_slot·wafer·die·defect·dtjob)은 «아무것도 안 씁니다» — 부재가 dynamic 입니다
```

## ③ `continues` — 지시대로 «안 지웠습니다**
클라 두 좌석의 `continues_hops` 선언이 죽은 채 남는 것을 피하기 위해, ②의 도달 범위가
같거나 넓다는 것이 측정된 «뒤에» 별도로 걷어내는 것으로 두었습니다.
