# 이름은 «좁은 follow»로 가져온다, 가져와서 버리지 않는다 — 그리고 대조 규칙 ①은 한 시간 만에 폐기됐다

> **커밋:** `5290292c` (18:42) · `1ad8b406` (18:59) · `3987ef8a` (19:30) · `66fbe1b9` (19:32)
> · `c278df63` (19:39) · `bcb393a2` (19:43)
> | **일자:** 2026-08-29 저녁
> **레인:** 서버(원장 walk · 대조 랭킹) + 보드 기록
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 랭킹을 규칙 «셋»으로 적었고, 그중 하나가 소유자의 질문 하나에 무너졌다

`5290292c`. 소유자와 왕복하며 대조(랭킹) 알고리즘을 세 줄로 정리했다.

```
① 물감은 «선언이 허용한 걸음»으로만 흐른다
② 나누지 않는다. 닿으면 «1»
③ 「안 닿음」과 「안 쟀음」을 가른다 — 0 을 그대로 내놓지 않는다
```

①을 적을 때 **「경로는 자기 출발 타입으로 돌아가지 않는다」는 구조적 사실**이라고 썼다.
근거는 wafer → defect_kind 경로 70개의 깊이별 허용 걸음을 합집합해도 `die → wafer` 가
안 나온다는 것이었다.

## 🔴 소유자가 «같은 타입 질문»을 던지자 ①이 두 방향으로 틀렸다

`1ad8b406`. 소유자:
「a 스텝이 디펙이 이전 스텝의 디펙과 연관있는지 보기위해 **defect collect defect** 을 하면
역방향 걷기 가능성 있음」.

```
defect -> defect   그때 규칙            «0» 경로   역방향이 아니라 «조용한 빈 답»
                   출발 타입 재진입 허용   180 경로   그중 «53»이 정적 허브 통과 <- 지적하신 그것
                   재진입 + 정책 ④       127 경로   정적 허브 통과 «0»
살아남는 경로  defect -observed-> die -transfer*-> die -observed-> defect
```

**새 축이 필요하지 않았다** — 선언에 이미 있는 정적/동적이 그 일을 한다. 옳은 문장은
「출발 타입으로 안 돌아간다」가 아니라 **「정적 노드에서 «나가지» 않는다」**였다.

## 🔴 같은 측정이 내 수치 «둘»을 함께 무효로 만들었다

18:42 에 보드에 적은 「오염 157 → 0 · 1층 395 → 1」은 **허용 걸음의 효과가 아니었다.**

```
① 기준선이 «방향»이었다   그 비교는 «무방향 + 선언 무시» 대 «허용 걸음»이었다
                       방향을 고정하고 허용 걸음만 켜고 꺼면 «아무것도 안 바뀐다»
                       후보 996 · 1층 1 · 씨앗 둘 다 닿음 17 — 세 모드가 전부 «동일»
② 예산이 답을 정하고 있었다   node_limit 상한 «1000» · hops_reached «2»
                       3홉 이상에서만 생기는 다이 오염은 이 라우트로 «관측 자체가» 안 된다
```

**두 후보 중 하나를 고르는 표였는데, 그 표가 재어진 조건이 결론을 이미 정하고 있었다.**

## 걷기 ② — 이름을 «가져와서 버리는» 대신 «좁게 가져온다»

`3987ef8a`. 정책 ④(정적 노드는 다른 정적으로 갈 수 있어도 세상으로 나가지 못한다)는
**이미 구현돼 있었다.** `_expand_atom` 안에, **한 층 늦게**.

```
씨앗 결함 하나 · hops=4
  `of_kind` 를 따라감    claims 6,000 (상한) ·  13 노드 · 홉 2 에서 멈춤
  `of_kind` 를 뺌        claims   371        · 315 노드 · 홉 4 도달
`defect_kind` 는 원자 103,841 개를 «구별되는 목적어 하나»에 대해 이고 있다
```

원자는 원장에서 «읽히고» `claims_scanned` 에 «과금된 뒤»에야 양 끝이 검사됐다. 그래서
**이름 하나가 claim 예산 전부를 사고 그 원자를 전부 버릴 수 있었다.** 프론티어를 엔터티 클래스로
가르고 각 절반을 **자기 `follow` 로 따로 가져오게** 했다.

```python
# server/ledger_api/ledger_subgraph.py — subgraph()
dynamic_refs = [item for item in full_entity_refs if _bare(item["type"]) not in static_types]
static_refs  = [item for item in full_entity_refs if _bare(item["type"]) in static_types]
# 🔴 빈 리스트는 None 이 «아니다». claims_for_entities 는 falsy follow 를 「모든 술어」로 읽는다
static_step_follow = sorted(static_follow & set(follow)) if follow else sorted(static_follow)
for group, group_follow, group_is_static in (
        (dynamic_refs, follow, False), (static_refs, static_step_follow, True)):
    if not group or remaining <= 0:
        continue
    if group_is_static and not group_follow:
        continue
```

정적이 밟을 수 있는 술어 집합은 **선언에서 도출**한다(`_static_step_predicates()`,
`_static_types()` 와 같은 모양). 읽을 수 없으면 **빈 집합**을 돌려주고, 그러면 정적 노드는
**아예 안 펴진다** — 어느 허브가 안전한지 «추측»하지 않는다.

## 걷기 ③ — 방금 올라온 술어로 되짚어 내려가지 않는다

`c278df63`. 한 술어를 «거슬러» 올라 컨테이너에 닿은 다음 **같은 술어를 «순방향»으로** 걸으면
그 컨테이너의 다른 자식들 — 즉 씨앗 자신의 형제 — 에 앉는다. 구조상 한쪽에만 있고 정보가 «0»이다.

```
결함 씨앗 · direction=both · hops=4
   결함 199 · 다이 115  ->  그중 결함 189 · 다이 111 이
                          die -[inspected 역]-> wafer -[inspected 순]-> die' 로 도착
🔴 대조군 실험   direction=outgoing 에서는 반전이 «불가능»하다
                그 조건의 진짜 계보 = 다이 «4». 수정 뒤 both 도 «4»
```

```python
#: 노드 -> 그 노드에 «도착한» (술어, 방향) 집합. 씨앗은 빈 집합이라 면제가 필요 없다
arrivals = defaultdict(set)
...
# 🔴 `==` 이지 `in` 이 아니다 — 다른 길로도 닿은 노드는 «컨테이너로만» 쓰인 것이 아니다
if (step_dir == "outgoing"
        and not (near_kind in static_types and far_kind in static_types)
        and arrivals.get(near_id) == {(atom.predicate, "incoming")}):
    return
```

**세상에 대한 규칙이지 이름에 대한 규칙이 아니다.** 정적 둘 사이에는 컨테이너가 없으니 형제도 없다 —
`leads_to` 를 거슬러 원인에 갔다가 다시 순방향으로 가면 «그 원인의 다른 결과»에 닿는다.
면제를 안 두면 메커니즘 체인 21 → 19 였고, 잃은 둘 중 하나가 **`delam`** 이었다.

## 🔴 이 라운드에 내가 쓴 게이트가 «잡음을 재고 있었다»

`bcb393a2`. 지시서에 「`transfer` 는 39 그대로여야 한다」고 적어 두었는데,
**그 39 자체가 규칙 ③이 지우는 형제였다.** 안 재 본 수를 게이트에 넣으면 레인이
«맞는 결과»를 보고 멈춘다. 판정을 낸 것은 게이트가 아니라 `direction=outgoing` 대조군이었다.

## 규칙 ①의 폐기 — 그리고 그것이 무너진 «진짜» 이유

`66fbe1b9`. 소유자가 경로 하나를 주고 평가하라고 했다:
`defect → die → lot_slot → lot_slot → lot_slot → die → defect`.
선언은 그 경로를 나른다(die 와 lot_slot 사이에 wafer 가 한 칸 들어간다).

```
내 경로 열거 (타입 재방문 금지)   경로 255 · lot_slot 지나는 것 «0»   <- 이 경로를 «못 만든다»
타입 재방문 허용                경로 791 · lot_slot 지나는 것 «95»
     + 인접 반전 금지 적용        경로 277 · lot_slot 지나는 것 «23»   <- 소유자 경로가 살아 있다
```

**내 `seen` 이 «타입» 단위였다.** 이 경로는 wafer 를 두 번 지나는데 **서로 다른 웨이퍼**다.
타입으로 막으니 「올라간 컨테이너와 «다른» 컨테이너로 내려오기」가 통째로 사라졌다.
앞서 보고한 「wafer → wafer 경로 0」(실제 36)도 같은 원인이다.

그래서 규칙 ①이 폐기됐다 — **그 일은 원인 자리(걷기 ③)에서 인스턴스 단위로 이미 된다.**
대조는 규칙 «셋»이 아니라 «둘»로 남았다. 상설 지시 「부품이 거른다 → 거르는 것은 walk 이 할 일이다」에
그쪽이 더 맞는다.

## 스위트

```
c278df63 시점 보드 기록   test_ledger_subgraph + test_ledger_trace   22 passed
무회귀 기준선            SYN-BW-101-16 hops=6  ->  노드 285 · 엣지 373 · claims 652 (수정 전과 동일)
3987ef8a 사후 실측       결함 씨앗 381 claims / 316 노드 / 홉 4
                        웨이퍼 씨앗 945 claims / 369 노드 (quantity·defect_kind 종점 여전히 수집)
                        defect_kind{void} + follow=leads_to  ->  인과 사슬 21 노드 그대로
```

## 아키텍처 영향

- 걷기가 **정적 프론티어를 «따로» 가져온다.** 정적이 밟을 술어는 선언에서 도출되고,
  이 시점의 라이브 선언에서 그 집합은 `{leads_to}` 하나다(내가 잼).
- 걷기가 **인접 반전을 거부한다.** 인스턴스 단위이고, 정적↔정적은 면제다.
- 대조의 규칙 ①(허용 걸음 열거)은 **폐기**다. 대조가 걷기의 일을 하고 있던 자리였다.

## 그때 남아 있던 것

- **배포 샘플에는 `class` 선언이 «하나도 없다»**(내가 잼 — `server/config/sample/ledger_config.json.sample`,
  엔터티 9개 전부 `class` 없음, 술어 13). 라이브(`server/config/ontology/ledger_config.json`)에서만
  `defect_kind`·`quantity`·`recipe` 셋이 static 이고 static→static 술어가 `leads_to` 하나다.
  샘플로 폴백해 뜬 스택에서는 이 라운드의 두 집합이 **둘 다 빈 집합**이다.
- 대조 규칙 ③(측정 간극)은 이 시점에 **코드에 없다.** 판정 문장과 실측만 있었다.
- 이날 낮에 잰 대조 수치(후보 796/996 · 1층 1 · reach 값 5가지)는 **홉 2 에서 잘린 서브그래프
  위에서 잰 것**이라 무효로 표시됐다. 살아남은 것은 `thickness_um` 이 원인이 아니라
  «측정 간극»이라는 판정 하나뿐이고, 그건 1홉 비교라 절단·형제와 무관하다.
- `wafer → lot` 경로가 **0**이다 — lot 을 lot_slot·wafer 에 잇는 술어가 선언에 없다. 별건의 구멍으로 적혔다.
- `test_ledger_trace_contract` 에 빨강 «1» 이 있었고, 그 시험은 `ledger_subgraph` 를
  임포트하지 않으므로 이 라운드와 무관하다고 적혔다.
