# 그날 밤 «효과가 가장 큰» 규칙에 시험이 없었고, 내가 그것에 처음 쓴 시험은 «공허»했다

> **커밋:** `12a94097` (23:16) · `afc79ac3` (23:19) · `8bf670b8` (23:27) · `caae8e9f` (23:29)
> · `290bb1af` (23:32)
> | **일자:** 2026-08-29 밤
> **레인:** 서버(걷기 시험) + 판정 색인 + 보드 기록
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 소유자가 「걷기와 대조는 끝났나」를 물었고, 답 대신 «쟀다»

`290bb1af` 에 그 결정이 적혔다. 답한 게 아니라 **가드를 하나씩 무력화해 보고 스위트가 어떻게 되는지 봤다.**

```
_expand_atom 의 arrivals 검사를 no-op 으로  ->  원장 스위트 «전부 초록» (445 passed · 기존 빨강 9 그대로)
그 가드가 라이브에서 한 일               ->  결함 199 -> 10 · 다이 115 -> 4
```

**그날 밤 «행동 변화가 가장 컸던» 규칙이, 가져오는 쪽에서는 아무것에도 안 재지고 있었다.**

## 🔴 그리고 내가 그것에 처음 쓴 시험도 가드를 꺼도 «통과»했다

`"D2" not in labels` 라고 단언했다. 다이의 라벨은 `mat_id`/`x`/`y` 로 **조립**되는데
픽스처가 그 칸을 안 채워서 **모든 다이가 맨 낱말 "die" 로 그려진다.** 그러니 그 단언은
D2 가 그래프에 있든 없든 **참이다.**

```python
# server/tests/test_ledger_subgraph.py — 고친 뒤
# 🔴 COUNT THE DIES, DO NOT LOOK FOR THEIR LABELS. A die's label is built from
# `mat_id`/`x`/`y`, so this fixture's dies all render as the bare word "die" and
# `"D2" not in labels` is true whether or not D2 is in the graph -- the first version
# of this test asserted exactly that and passed with the guard turned off.
dies = [node for node in body["nodes"] if node["type"] == "die"]
assert len(dies) == 1, (
    "the walk climbed `inspected` and walked it back down into the seed's siblings: "
    f"{len(dies)} dies came back where only the seed should have")
```

이유를 **그 자리에 적었다** — 다음 픽스처가 같은 함정을 밟지 않도록.
가드를 끄면 빨강, 되돌리면 16 passed. 넓은 집합 50 passed.

## 가져오는 쪽은 «돌아온 그래프»로는 볼 수 없다 — 인자를 봐야 한다

`12a94097`. `grep static_types server/tests/` 가 두 줄, 둘 다 `_reach`/`_propagation` 을
직접 부르는 것이었다. 이름을 «정적↔정적» 술어로 좁혀서 **부르는** 쪽은 아무것도 안 재고 있었다.

```
지우고 스위트  초록
지우고 라이브  홉 2 에서 claims 6,000 · 노드 13     (좁힘 없음)
좁힘 있음     홉 4 에서 claims 371 · 노드 315
```

🔴 **돌아온 그래프에 대한 시험으로는 이 차이를 못 본다.** `_expand_atom` 이 어느 쪽이든 그 스텝을
거절하므로 **가져온 뒤 거르면 정확히 같은 노드가 돌아온다.** 가르는 것은 **조회를 어떤 인자로 불렀나**다.
그래서 `RecordingLookup` 이 `(entities, follow)` 를 전부 보관하고 시험이 그것에 단언한다.

```
정적 프런티어가 «좁힌 follow 로» 불린다 — 그리고 Q2 는 여전히 도착한다(정적↔정적이 같이 잘리지 않는다)
교집합이 «비면» 호출을 «건너뛴다» — [] 를 넘기면 조회 계약이 그걸 «모든 술어»로 읽는다
```

둘 다 착지 «전»에 각자의 변이로 깨웠다 — 정적 그룹을 전체 `follow` 로 보내면 첫째만 빨강,
빈 교집합 갈래를 도달 불가로 만들면 둘째만 빨강. 되돌려 15 passed.

**같은 커밋이 낡은 docstring 을 고쳤다.** `_followable_predicates` 가 「`in_container` 는 어휘에
«없는» 참조 엣지」라고 적고 있었는데 **그날 밤 양쪽 절반이 다 거짓이 됐다.**

```python
# server/ledger_trace_router.py — _followable_predicates()
#   MEASURED 2026-08-29: `in_container@1` is DECLARED in `vocabulary` now and emitted by two
#   mappings on the `bonded_from` source, and NO entity carries `references` at all. The
#   grammar for `references` still validates in `setup_bundle` and nothing reads it, so the
#   widening this docstring described has no subject left -- it would matter again only on
#   the day a reference edge is declared.
```

## 남은 둘도 못 박았다 — 파생과 두 번째 예산

`caae8e9f`. `server/tests/` 에서 등장 «0» 이던 둘.

**① `_static_step_predicates()` 의 파생.** 이름 하나에 허용되는 «한 걸음»을 갈래로 적지 않고
선언에서 도출한다. 픽스처에 **모양을 하나씩** 담아서 「전부 반환」이나 「첫 매치」로는 못 지나가게 했다.

```
정적->정적 · 정적->동적 · 동적->정적 · 정적->클래스 없는 엔티티 · 엔티티 목적어가 아예 없는 것
결과 == {"s_to_s"}
선언을 «못 읽으면» -> set()   (빈 쪽이 안전한 방향: 스텝을 거절하면 인과 사슬을 잃고,
                            지레짐작하면 «걷기 전체»를 잃는다)
```

**② `backbone_hops`.** 세상을 «떠나지 않는» 스텝에 깊이를 사 준다.
다이 사이 `transfer` 다섯 걸음 — 전부 동적↔동적이라 **backbone 허용치만이** 걷기를 첫 홉 너머로 나른다.

```
backbone_hops=0  ->  노드 2
backbone_hops=4  ->  노드 6 · 최대 depth 5   (depths 는 «모든» 스텝을 계속 센다)
```

각각 따로 깨웠다 — `budget_hops` 를 `hops` 로 고정하면 둘째만, 파생이 모든 술어를 받게 하면
첫째만 빨개진다. 되돌려 52 passed.

## 판정에 «구현보다 오래 사는» 색인을 달았다

`afc79ac3`. 소유자의 「그냥 많이 재면 신호 약해지겠구나」가 `_reach` 의 docstring 과 보드에만
살고 있었는데, **`_reach` 는 그날 밤에만 두 번 다시 쓰였다.**

`R-2026-08-29-P` ~ `-T` 로 등록했고, 각 항목이 **소유자의 말 · 그것을 받친 측정 · 그리고 그것을
강제하는 시험**을 같이 들고 있다.

```
P  닿으면 1 — 분수가 답을 정하고 있었다
Q  걷기가 거절하는 두 스텝. 둘 다 «노드»가 아니라 «스텝»을 키로 삼는다
R  각 쪽이 닿은거/도달가능 — 끊긴 다리는 답을 숨기지 않고 «틀린 1등»을 만든다
S  정적 노드는 씨앗이 아니다
T  액션 방아쇠는 «선언»된다
```

`R-Q` 는 **은퇴한 규칙이 무엇이었는지도** 적었다 — 그것이 살아 있는 문서 어디에도 없었고
보드에만 있었는데, 보드는 총괄의 것이지 전달 경로가 아니다.

## 스위트

```
8bf670b8 시점   가드 끄면 빨강 · 되돌리면 16 passed · 넓은 집합 50 passed
caae8e9f 시점   52 passed
이 항목 작성 시  tests/test_ledger_subgraph.py  ->  «18 passed · 1 skipped»
```

## 아키텍처 영향

- 걷기의 **가져오는 쪽**이 처음으로 시험을 갖는다. 단언의 대상은 돌아온 그래프가 아니라
  **조회에 넘어간 인자**다.
- 판정 다섯이 `docs/process/LEDGER_RULINGS.md` 에 **구현과 분리된 이름**(R-2026-08-29-P..T)으로 산다.

## 그때 남아 있던 것

- 보드에 **정직한 나머지**가 소유자가 받은 그대로 적혔다 — 그중 가장 중요한 것:
  **그날 밤 잰 모든 것이 「답이 존재하도록 내가 심은 픽스처」 위에서 돌았다.**
  즉 기계가 **있는 것을 찾는다**는 것은 보였고, **없는 것을 지어내지 않는다**는 것은 보이지 않았다.
- 시험 셋이 닫혔고, 각각 자기 변이로 깨워졌다. 그 밖의 간극 목록은 이 시점에 보드에만 있다.
