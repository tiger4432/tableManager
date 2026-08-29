# 「한 사실은 한 엣지다」 — claim 이 «자리»이기를 그만뒀고, 그 뒤 11시간 41분 동안 술어가 사라져 있었다

> **커밋:** `a75f8043` (07:31) · `55ff0166` (07:41) · `caed3be2` (07:57) · `6a31cd30` (08:59)
> · `acc20615` (09:26) · `9cc709fa` (10:32) · `f2e44ae0` (11:20) · `86abbbc7` (22:13)
> | **일자:** 2026-08-25 하루 종일
> **레인:** 서버(walk) + 클라(보드 자취)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 예산이 «세상에 있는 것»이 아니라 «사실의 부품»을 세고 있었다

소유자의 체인이 레시피에 못 닿았다. 벽은 홉이 아니라 **노드 예산**이었고, 그 예산을
**claim·event·value** — 즉 사실을 접었다 폈다 하는 «부품»들이 쓰고 있었다.

세 걸음으로 걷어냈다:

```
a75f8043   claim 이 예산을 안 쓴다      add_node 가 len(nodes) 대신 budgeted 를 센다
55ff0166   event 가 합류               _UNBUDGETED_KINDS = {"claim", "event"}
caed3be2   value 가 합류 + «엣지»까지    규칙이 모듈 수준으로 올라간다
```

```python
# server/ledger_api/ledger_subgraph.py  (caed3be2)
_WORLDLESS_KINDS = frozenset({"claim", "event", "value"})

def _edge_spends_budget(row):
    return (_spends_budget(nodes[row["source"]])
            and _spends_budget(nodes[row["target"]]))
```

**엣지 반쪽이 필요했던 이유가 수로 남았다: 엣지 1,200 중 1,100이 claim → entity 였다.**

```
씨앗 SYN-BW-101-16   레시피 0 -> 0 -> «5»   (SYN-R-CMP-01 포함)
                    세상 노드 193 / 상한 1,000
비용                응답이 약 8배 — 노드 8,244 중 8,051이 «사실의 부품»
```

## `follow`가 SQL 에서 좁아졌고, 거절이 «자기 술어를 거절할» 뻔했다

`6a31cd30`. `follow`가 가져온 뒤에 거르고 있었다. SQL 로 내리면서 붙인 422 가드가
**v1 코드 목록 열셋**만 보고 있어서, 하마터면 `bonded_from`·`inspected`·`transfer`·`has_netdie`
— **원자 151,321을 든 술어 넷**을 거절할 뻔했다. 그중 하나는 `follow`가 존재하는 이유인 엣지다.
게이트가 통과한 이유도 기록됐다 — **`subgraph()`를 직접 불러서 라우트 검사를 건너뛰었기 때문.**

그리고 그 커밋이 **500을 냈다.** 응답 본문이 아직 정의되지 않은 이름 `declared`를 읽고 있었다.
**27분 뒤 `acc20615`가 고쳤다** — 「거절이 다시 422 를 내고, 시험이 그것을 «서술»하는 대신
«실행»한다」.

## 🔴 한 사실은 한 엣지다 — claim 노드가 목적지이기를 그만뒀다

`9cc709fa`. claim 프런티어 단계가 통째로 사라졌다:

```diff
-        claim_refs = [refs[item] for item in frontier_ids
-                      if refs[item]["kind"] in {"claim", "value"}]
-    def add_claim(atom, depth): ...
+    def _claim_edge(atom, source_id, target_id, edge_type):
+        edge = _edge(edge_type, source_id, target_id, original_predicate=atom.predicate)
+        edge["claim_id"] = atom.id
```

한 원자가 **claim 노드로 depth+1 에 주차됐다가 다음 반복에서 펴져서** 주어·목적어가
depth+2 에 앉던 것이, **가져온 그 BFS 레벨에서 바로 엣지**가 된다. 한 단언이 **두 홉**을
먹던 것이 하나가 됐다.

```
노드 5,644 -> 1,805 · claim 0 · event 0
절단 [claims] -> [depth]
레시피 자취 «3홉» [entity, entity, entity] · 레시피 5 · 발견점 89
```

**claim id 를 seed 로 주면 거절된다** — 이건 코드로 확인된다:

```python
# server/ledger_api/ledger_subgraph.py  decode_node_id
if text.startswith("ledger-claim-atom:v1:"):
    raise ValueError(
        "claim ids are no longer seeds -- a claim is an edge, seed its subject instead")
```

라우터가 그것을 **422 `subgraph_request_invalid`**로 바꾼다.

## 🔴 그리고 «11시간 41분» 동안 모든 엔터티가 술어 0을 보고했다

`claim_count`/`predicates` 루프가 여전히 **`node_kind == "claim"`인 노드로 걸어가서** 술어를
풀고 있었다. 그런 노드가 없으니 조회가 **모든 엣지에서 `None`**을 냈다 — 보드에서 **82 중 0.**

```diff
-        if nodes[edge["source"]].get("node_kind") == "claim":
-            claim_id = edge["source"]
+        claim_id = edge.get("claim_id")
+        if not claim_id:
             continue
```

**9cc709fa 10:32:43 → 86abbbc7 22:13:43 = 11시간 41분 00초.** 같은 날이다.
고친 뒤: 씨앗 `claim_count` 77 · `bonded_from` 29 · `inspected` 39 · `processed_with` 9 ·
엔터티 69/69가 채워짐.

`f2e44ae0`이 클라 쪽 자취 시험에서 **이제 불가능한 `claim` 갈래**를 지웠다 —
옛 「21/21 실측」은 **아무것도 안 세고 있었고**, 화면은 이제 0 / 21 을 읽는다.

## 아키텍처 영향

- **claim 은 노드가 아니라 엣지다.** claim id 는 seed 가 아니고 그렇게 말하며 거절된다.
- 노드·엣지 예산이 **세상에 있는 것**만 센다. 사실의 부품은 예산을 안 쓴다.
- `follow`가 SQL 에서 좁힌다. 거절의 술어 목록이 **코드 집합 ∪ 라이브 선언**(`@N` 벗겨서)이다.
- `MAX_EDGE_LIMIT` 3000 → 6000, `MAX_CLAIM_SCAN` 5000 → 6000. **노드 상한은 일부러 안 움직였다.**

## 그때 남아 있던 것

- `decode_node_id` 바로 밑의 `prefixes` dict 가 여전히 `"ledger-claim-atom:v1:" -> "claim"`을
  들고 있다 — **이제 닿을 수 없는 줄**이다.
- `test_ledger_trace_contract.py`의 시험 **둘이 빨갛고**, 변경 없이 HEAD 에서도 빨갛다.
- `6a31cd30` 시점에 `observed`는 **`follow`로 닿을 수 없다.** `9cc709fa`가 그 자리를
  `include_observed`라고 이름 댔다.
- 클라의 자취 표시는 **0 / 21**이다 — 세던 것이 애초에 없었다는 것이 드러난 상태.
