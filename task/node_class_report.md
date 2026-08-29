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

---

# ✅ [A 구현자] **정책 ① 착지 — `9f8db5ab`. 치환이 «157 에 정확히» 닿습니다** (2026-08-29 14:4x)

과금 키를 술어 플래그에서 «엔티티 분류»로 옮겼습니다. 인자 이름(`continues_hops`)은 지시대로
«그대로» 두었습니다 — 두 번 안 고칩니다.
```
전   _charge = 0 if 술어 in continuing else 1
후   _charge = 0 if (양 끝이 «둘 다 dynamic») else 1
```

## 게이트 ① — 치환. 지시하신 인자 그대로
씨앗 `wafer SYN-BW-101-16` · hops=1 · outgoing · follow=자재6+`processed_with` · 1000/3000
```
continues_hops=0    nodes  40  · edges  39 · reached 1 · truncated depth
continues_hops=4    nodes «157» · edges 156 · reached 3 · truncated «없음»    ← 기준 충족
continues_hops=6    nodes  157 · edges 156 · reached 3 · truncated 없음
continues_hops=12   nodes  157 · edges 156 · reached 3 · truncated 없음
```
🔴 **157 «이상»이 아니라 «정확히 157»입니다.** 더 크지 않은 이유를 적습니다 —
D→D 가 `continues` 보다 하나 더 갖는 술어가 `observed` 인데, **이 측정의 follow 목록에 `observed`
가 없습니다.** 그래서 더할 것이 없습니다. 조건(≥157)은 충족이고, 「왜 딱 같은가」가 이것입니다.
⚠️ 그러니 「D→D 가 더 넓다」는 것은 이 측정이 «보여 주지 않습니다». follow 에 `observed` 를
   넣은 비교가 필요하시면 재 드립니다 — 다만 그건 지시하신 인자가 아니라 안 했습니다.

## 게이트 ② — 무회귀
`continues_hops` 를 «안 보내면» 과금 규칙이 결과에 닿을 수 없습니다(추가 예산 0이라 루프가
여전히 `hops` 만큼만 돕니다). 그래도 «재서» 확인했습니다 — 이 파일만 HEAD 로 되돌린 대조군:
```
                                    이 커밋            HEAD(술어 플래그 과금)
wafer both · hops6 · 1000/3000      225 / 224 · reached 2 · trunc claims     «동일»
```

## 게이트 ③ — 인과 사슬
```
quantity{bond_pressure} · follow=leads_to · hops=4   ->  nodes 18 · edges 18 · reached «4»
```

## 게이트 ④ — 시험
```
tests/test_ledger_subgraph.py + tests/test_ledger_explorer.py   12 passed · 1 skipped
```

## `continues` — 지시대로 «안 지웠습니다», 다만 이제 «안 쓰입니다**
```
walk 의 `continuing` 인자    받되 과금에 «안 씁니다». 주석에 「치환이 수락되면 제거」라고 적었습니다
지금 지우면                 클라 두 좌석의 `continues_hops` 선언이 «가리킬 것이 없어집니다»
```
⛔ 「깊이 cap 내 무제한」은 구현 «안 했습니다». 두 번째 통은 여전히 «통»입니다.

---

# ✅ [A 구현자] **`continues` 서버 은퇴 + `backbone_hops` 개명 — `35f1963c`** (2026-08-29 15:1x)

## 지운 것 / 남긴 것
```
walk        continuing 매개변수 · _bare_predicate(마지막 호출자와 함께)   «삭제»
router      _continuing_predicates() · subgraph 호출의 continuing 인자    «삭제»
skeleton    술어 레코드의 continues 리프                                  «삭제»
validator   optional=("continues",)  «남김» + bool 검사 «삭제»
예산 계산    «안 건드림» — 이미 D→D 로 키가 바뀌어 있었습니다
```
🔴 **검증기만 남긴 이유는 지시하신 «순서» 그대로입니다.** 라이브 선언에 여섯이 아직 있어서,
지금 거절하게 만들면 총괄이 지우기 «전»에 서버가 선언을 못 읽습니다. 주석에 「선언 정리와 같이
없어진다」라고 적어 뒀습니다. 그 여섯을 지우신 뒤 이 한 줄을 걷어내면 끝입니다.

## 개명 — 별칭 «없음»
```
DEFAULT_CONTINUES_HOPS -> DEFAULT_BACKBONE_HOPS
Query continues_hops   -> backbone_hops
옛 이름 호환층          «안 만들었습니다» (지시대로)
```

## 게이트
```
① 선언에 continues 여섯이 «남아 있는 채로» 걷기 라우트가 200            ✅
   (검증기가 거절하지 않는다는 뜻입니다 — 거절하면 선언 로드 자체가 실패합니다)
② 씨앗 wafer SYN-BW-101-16 · hops=1 · outgoing · 1000/3000
   follow = 자재6 + processed_with
      backbone_hops=0   nodes  40 · reached 1 · truncated depth
      backbone_hops=4   nodes «157» · reached 3 · truncated none
   follow 에 observed 추가
      backbone_hops=4   nodes «246» · reached 3 · truncated none      ← 총괄 수와 일치
③ 옛 이름   continues_hops=4  ->  nodes «40» · reached 1 · truncated depth
   = 예산을 «안 준 것»과 완전히 같습니다. 조용히 옛 동작을 하지 «않습니다» ✅
   (FastAPI 가 선언 안 된 쿼리 인자를 무시합니다 — 지시의 「무시되거나 422」 중 앞쪽)
④ -k "subgraph or setup_bundle or skeleton or explorer or l1_unit"
   218 passed · 2 skipped · 7 failed
   그 일곱은 오늘 아침 HEAD 대조군과 «정렬된 목록이 동일»합니다 (수가 아니라 목록으로 비교)
```

## 곁들여 고친 것 — 낡은 주석 «셋»
```
walk    「예산은 술어에 달렸다」  -> 「양 끝의 분류에 달렸다」  (두 곳)
router  backbone_hops 의 «사용자에게 보이는» description 이
        「`continues: true` 라고 말한 술어를 지나는 걸음」이라고 하고 있었습니다
        -> 「양 끝이 둘 다 dynamic 인 걸음. 정적/동적은 선언의 `class` 가 정한다」
```

## 총괄에게 남은 것
```
라이브·샘플 선언의 continues 여섯 삭제  ->  그 뒤 검증기의 optional 한 줄 제거(제가 합니다)
클라 두 좌석의 continues_hops -> backbone_hops  ->  «클라 레인» 몫
```
