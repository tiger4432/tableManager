# Ledger Evidence Subgraph — 걷기 하나가 답한다

> **Status:** 🟢 Living · **Last verified:** 2026-08-29 밤 · `290bb1af` 기준 재측정 (걷기 규칙 셋 · 대조 규칙 둘. **§5.1 이 걷기 규칙의 유일한 정본**)
> **정본 코드:** `server/ledger_api/ledger_subgraph.py` · `server/ledger_trace_router.py` ·
> `server/ledger/envelope.py` · `server/ledger/schema.py`
> **선언 정본:** `server/config/ontology/ledger_config.json` (`entities` · `vocabulary` · `sources`)
> **범위:** 원장 증거를 보는 읽기 모델. 증거의 «양»은 인과가 아니다.

## 0. 한 문장

`GET /api/ledger/subgraph` 는 원장 사본을 만들지 않고 `ledger_events` 를 직접 읽어,
**선언된 엔터티 하나를 시작점으로 삼는 유계 증거 그래프**를 반환한다.

## 1. 노드 종류는 «하나»다

```
노드    선언된 엔터티. 이것뿐이다
엣지    원장 원자 하나. 이것뿐이다
좁히기  follow (선언된 술어 이름). 이것뿐이다
```

**원자 하나가 엣지 하나이고, 그 원자가 인출된 «그 깊이»에서 바로 펼쳐진다.** 주장이
「거쳐 가는 자리」가 아니라 「이랬다는 사실」이기 때문이다 — 그 자리를 노드로 두면 한 단언이
걷기의 «두 층»을 쓴다. 주장의 id·시각·출처·수식어는 사라지지 않고 **엣지에 실린다**:
세상의 것이 노드인 그래프에서 「누가 언제 그렇게 말했나」가 있어야 할 자리가 거기다.

**목적어가 «값»인 원자는 노드를 만들지 않는다.** 값은 자기 주어에 대한 진술이지 설 자리가
아니다. ✅ **[2026-08-28 착지] 그래서 발견을 «노드로» 바꿨다** — `defect@1` 엔터티가 선언됐고
`observed@1` 의 목적어가 `entity_ref` → `defect@1` 이 됐다. **코드에는 분기가 하나도 추가되지
않았고**, 이미 있던 `entity_ref` 갈래가 그대로 그린다. 🔴 **종전 이 자리는 「발견은 오늘 걷기에
나타나지 않는다」였고 그것은 이제 거짓이다** — 발견은 노드이고, 거기서 `of_kind@1` 로
`defect_kind@1` 까지 «걸어 나갈 수» 있다.

📌 **실측 2026-08-29 밤** (라이브 선언 `server/config/ontology/ledger_config.json` 의 `vocabulary`
전수): 선언된 술어는 **열넷**이고 그중 목적어가 `entity_ref` 인 것은 **열둘**이다 —
`has_netdie@1` 은 `value`, `register@1` 은 `none`(등록 술어라 목적어가 ∅). 🔴 **종전 이 자리의
「열셋이고 전부 `entity_ref` 다」는 «둘 다» 틀렸다** — 그때도 `has_netdie@1` 은 `value` 였다.
위 규칙(값 목적어는 노드를 만들지 않는다)은 계약이면서 **오늘 실제로 발화하는 갈래**다.
⚠️ 그 술어가 «원자를 몇 개» 이고 있나는 여기서 세지 않는다 — 그 수는 원장(`ledger_events`)
`GROUP BY predicate` 에서만 나오고, 선언에서는 나오지 않는다.

📌 **열넷 중 하나는 이번에 새로 든 것이다** — `in_container@1`(`die@1` → `wafer@1`). 이 술어는
`bonded_from` 소스에 매핑 «둘»(`core-die-in-core-wafer` · `base-die-in-base-wafer`)로 실려 있고,
다이가 자기 웨이퍼에 닿는 **다리**다. 🔴 종전 이 다리는 `entities.<type>.references[].edge` 라는
«원자 없는» 합성 엣지였고, 지금은 **원자를 가진 선언된 술어**라 `follow` 로 좁힐 때도
어휘에서 그대로 나온다.

✅ **라이브 선언과 `.sample` 이 같다** (실측 2026-08-29 밤, `0fe0ec09` 이후 재측정: 어휘 **14 대 14**,
차집합 «양쪽 0», `class: "static"` 셋도 동일, `bonded_from` 매핑 셋도 동일). ⚠️ **종전 이 자리에
「`.sample` 은 아직 열셋이라 새로 설치한 환경은 이 다리를 못 건넌다」고 적혀 있었고 그것은
«그때만» 참이었다** — 몇 분 뒤 `.sample` 이 따라왔다. 배포 사실은 «커밋 하나 뒤»에 뒤집히므로,
이 문단을 인용하기 전에 두 파일을 다시 대조하라.

| 엣지에 실리는 것 | 뜻 |
|---|---|
| `predicate` | 원장 술어 그대로. 투영이 지어낸 이름은 없다 |
| `claim_id` | 이 엣지«가» 되는 원자의 id |
| `occurred_at` · `source_who` · `basis` | 그 원자의 시각·출처·원문 참조 |
| `qualifiers` | `object_payload.qualifiers` 그대로 |

## 2. 저장 계약

`ledger_events` 에 구조 상관 컬럼 둘이 있다.

| 컬럼 | 타입 | 뜻 |
|---|---|---|
| `source_event_id` | UUID | 한 소스 발화 묶음의 불투명 안정 신원 |
| `source_event_state` | TEXT | `source_molecule` \| `source_record` \| `legacy_atom` (CHECK 제약) |

둘은 주장 의미나 dedupe 에 참여하지 않는다 — `uq_ledger_atom` 키에 없다. 번역기 버전이
바뀌었다는 이유로 같은 주장이 두 번 착지하면 안 되기 때문이다.

```text
source_molecule = UUIDv5(ns, canonical[source_who, "source_molecule", molecule_ref, occurred_at_utc])
source_record   = UUIDv5(ns, canonical[source_who, "source_record",   source_raw_ref, occurred_at_utc])
```

- 분자 번역기는 `molecule_ref` 를, 한 행이 곧 사건인 생산자는 `source_raw_ref` 를 쓴다.
- UTC 발생시각이 들어가므로 소스가 나중에 같은 표지를 재사용해도 사건이 합쳐지지 않는다.
- 원시 `molecule_ref` 문자열은 저장하지 않는다. 소비자가 읽는 것은 비가역 UUID 뿐이다.
- 네임스페이스 UUID 는 저장 계약이다. 바꾸면 재적재 때 같은 사건이 둘이 된다.

⚠️ **`legacy_atom` 은 오늘 «0» 이다** (실측 2026-08-27, 원자 645,203 전부가 `source_molecule`).
그 상태를 재는 단언은 태울 표본이 없다 — 초록이 「지켜졌다」가 아니라 「못 쟀다」다.

## 3. 노드 ID 계약

ID 는 클라이언트가 조립하거나 고치지 않는 불투명 문자열이다. 서버는 디코드한 뒤 같은 규칙으로
재인코딩해 **철자가 정확히 같을 때만** 받는다.

| 노드 | 접두 | 내부 앵커 |
|---|---|---|
| 선언된 엔터티 | `ledger-entity:v1:` | `[entity_type, structured_keys]` |

접두는 **하나**다. `decode_node_id` 는 이 모양을 풀거나 «올린다» — 갈래가 없다.

🔴 **엔터티 라벨의 키 «순서»는 라이브 `entities` 선언에서 온다** (버전 접미사 `@N` 은 떼고
맞춘다). 선언된 순서를 얹는 것은 `_declared_key_order` 이고, 그 한 층이 이 사실의 «유일한
독자»다. `die` 가 그 예다 — payload JSON 의 삽입 순서는 `x`·`y` 를 앞에 놓아 자재 이름을
두 칸짜리 라벨 밖으로 밀어내는데, 선언은 이미 답을 갖고 있다. **선언에 없는 유형의 라벨은
손대지 않는다** — 그건 코드의 구멍이 아니라 선언의 구멍이라 «선언되는 날» 코드 0줄로 고쳐진다.
읽기는 한 번·캐시·**절대 예외를 올리지 않는다**.

## 4. API

**이 문서가 소유하는 것은 `GET /api/ledger/subgraph` «하나»다** — 데이터에 답하는 유일한 라우트.
`/api/ledger` 아래의 나머지는 **선언에 대해** 답하며(`declaration` 은 원장을 한 줄도 안 읽고,
`gaps` 는 선언을 순회해 「무엇이 아직 없나」를 답한다), **목록의 정본은 [backend §2](../architecture/backend.md)**
이고 **여기에 수를 적지 않는다** — 🔴 **[2026-08-31] 종전 이 자리의 「둘」이 `gaps` 신설로 거짓이 됐다.**

### 4.1 요청

```http
GET /api/ledger/subgraph
  ?id=<opaque-node-id>
  &hops=12
  &direction=both
  &node_limit=400
  &edge_limit=1200
  &follow=inspected&follow=bonded_from
  &backbone_hops=0
```

| 파라미터 | 필수 | 기본 | 허용 범위 | 의미 |
|---|---:|---:|---|---|
| `id` | 예 | — | 엔터티 id | 시작 노드. 응답의 어떤 노드 id 든 그대로 재사용 |
| `hops` | 아니오 | 12 | 1..40 | 구조 홉 |
| `direction` | 아니오 | `both` | `outgoing`·`incoming`·`both` | 주어 쪽·목적어 쪽 중 어느 arm 을 인출할지 |
| `node_limit` | 아니오 | 400 | 10..1000 | 응답 노드 하드캡 |
| `edge_limit` | 아니오 | 1200 | 20..6000 | 응답 엣지 하드캡 |
| `positive` | 아니오 | — | 노드 id, 반복 가능 | 추가 관측 씨앗. `id` 는 항상 positive 다 |
| `negative` | 아니오 | — | 노드 id, 반복 가능 | 대조군 씨앗. **목록에 없는 주어는 미검사이지 대조군이 아니다** |
| `follow` | 아니오 | — | 선언된 술어 이름, **반복 가능** | 이 술어만 따라간다. 없으면 전부. **SQL 에서 좁힌다**(§5 규칙 ①) |
| `backbone_hops` | 아니오 | 0 | 0..40 | 같은 자재에 머무는 걸음에 주는 «둘째» 예산. **양 끝이 둘 다 dynamic 인 걸음만** 여기서 빠진다 |

🔴 **`backbone_hops` 는 「어느 술어가 공짜냐」를 «묻지» 않는다.** 그 판정은 선언의
**엔터티 `class`** 가 하고 요청은 예산만 준다. 종전 철자 `continues_hops`(술어마다
`continues: true` 를 보던 것)는 **2026-08-29 에 은퇴**했고 **별칭을 받지 않는다** —
소비자가 둘 다 우리 것이라 남겨 둘 이유가 없었다.

🔴 **「기본이 0」과 「아무도 안 켠다」는 «다른 문장»이다.** 앞의 것은 코드에서 읽고, 뒤의 것은
**호출자를 세어야** 한다. 실측 2026-08-29 밤: 안 넘기면 동작은 종전 그대로이고(기본 0),
**켜는 호출자는 «넷»이다** — `client2/src/rnd_board/main.js` 의 좌석 선언 넷이
`backbone_hops: 2`(셋) · `1`(하나)을 준다. ⚠️ 종전 이 자리와 다른 문서 셋이 「아직 이것을
켜는 화면이 없다」고 적고 있었고, 그것은 **앞 문장에서 뒤 문장을 추론한 결과**였다.

🔴 **`class` 도 `static_follow` 도 요청 파라미터가 «아니다».** 둘 다 라우트가 매 요청 «선언에서
읽는다»(`_static_types()` · `_static_step_predicates()`) — 호출자가 무엇이 허브인지 고를 수 없다.
읽을 수 없는 선언은 **빈 집합**으로 떨어지고, 그 뜻은 「정적 노드를 아예 안 펼친다」이지
「전부 펼친다」가 아니다.

🔴 **`follow` 는 반복 파라미터다** — `follow=a&follow=b`. 쉼표 목록(`follow=a,b`)은 **422**
`predicate_not_declared` 이고 `unknown` 에 그 «문자열 통째»가 실린다. 선언에 없는 이름도 같은
거절이다 — 절대 «빈 그래프»로 답하지 않는다. 못 맞추는 필터와 「여기 아무것도 없다」가 같은
바이트를 내면 호출자가 오타와 사실을 못 가른다.

파이썬을 직접 부르면 기본이 하나 다르다: `edge_limit=6000` (라우트가 자기 기본 1200 을 따로 준다).

```python
subgraph(id, lookup, hops=12, direction="both", follow=["inspected"])
subgraph({"positive": [id, ...], "negative": [id, ...]}, lookup)
```

**부호는 셋이고 셋이다.**

```
+           관측됐다
−           «봤는데 안 났다» — 대조군
목록에 없음   미검사. − 와 같은 사실이 아니다
```

### 4.2 응답 골격

```json
{
  "schema_version": 3,
  "state": "ready",
  "seed": {"id": "...", "node_kind": "entity"},
  "seeds": [{"id": "...", "sign": "+", "node_kind": "entity"}],
  "nodes": [{"id": "...", "type": "wafer", "label": "...", "depth": 0,
             "claim_count": 7, "predicates": [{"predicate": "inspected", "count": 1}]}],
  "edges": [{"id": "...", "source": "...", "target": "...", "predicate": "inspected",
             "claim_id": "...", "occurred_at": "...", "source_who": "...", "qualifiers": {}}],
  "propagation": {
    "contrast": "contrasted", "complete": true, "state": "ranked",
    "ranked": [{"id": "...", "type": "recipe", "label": "SYN-R-CMP-01",
                "reach": [2, 0], "reachable": [2, 2],
                "rank": 1, "top": true, "tied": false, "incomparable": false,
                "evidence": [{"seed": "...", "sign": "+",
                              "hops": [{"id": "...", "node_kind": "entity",
                                        "label": "...", "atom": null, "ref": "..."}]}]}],
    "top_set": ["..."], "message": null
  },
  "walk": {"mode": "evidence_graph", "direction": "both",
           "start": {"positive": 1, "negative": 0},
           "hops_requested": 12, "hops_reached": 3, "claims_scanned": 60,
           "actions_scanned": 0, "enrich_actions": false,
           "raw_claims": true, "resolver_applied": false},
  "limits": {"nodes": 400, "edges": 1200, "claims": 2400, "actions": 1200, "max_hops": 40},
  "truncated": {"depth": false, "nodes": false, "edges": false,
                "claims": false, "actions": false, "reason": null},
  "message": null
}
```

- `state` 는 `ready` 또는 `empty` 다. `empty` 는 「씨앗은 유효한데 연결 증거가 없다」이고,
  씨앗 하나와 설명을 그대로 돌려준다.
- 승자만 남기는 해결기를 이 경로는 부르지 않는다. 정정 전 원자가 그대로 보인다.

#### 4.2-bis `propagation` — 대조 블록 (🔴 «항상» 계산된다)

⚠️ **종전 이 자리는 「`propagation` 은 오늘 항상 `not_requested` 다 — 깨울 인자가 없다」였고,
그것은 거짓이 됐다.** 응답 조립이 `_propagation(...)` 을 **무조건** 부른다. 깨우는 인자는
없고, 있을 필요도 없다 — 씨앗이 하나뿐이면 `contrast: "unexamined"` 로 «대조를 안 했다»고
말할 뿐 블록은 그대로 나온다.

| 필드 | 값 | 뜻 |
|---|---|---|
| `contrast` | `contrasted` \| `unexamined` | 대조군 씨앗이 하나라도 있었나. `unexamined` 는 「둘째 축을 아예 안 봤다」이지 「봤는데 0」이 아니다 |
| `complete` | bool | 어느 예산도 안 끊겼나. **끊긴 그래프 위의 순위는 잠정**이다 |
| `state` | `ranked` \| `empty` | `empty` 는 씨앗 밖 노드에 한 번도 안 닿았다 |
| `ranked[]` | 아래 | **씨앗을 뺀, 걸어서 «닿은» 노드 전부.** 타입 필터가 없다 |
| `top_set[]` | 노드 id | 1층(dominance 최상위) 전원. 「1등」이 하나라는 보장은 없다 |

**`ranked[]` 항목 하나가 드는 것** — `id` · `type`(선언된 엔터티 타입) · `label` ·
`reach` · `reachable` · `rank` · `top` · `tied` · `incomparable` · `evidence[]`.

```
reach       [관측 씨앗 몇이 닿았나, 대조군 씨앗 몇이 닿았나]      «정수» 쌍
reachable   [관측 씨앗 몇이 이 «타입»에 닿았나, 대조군 쪽 같은 수]  «정수» 쌍 — 분모
```

- 🔴 **닿으면 «1» 이다.** 갈래가 몇이든 나누지 않고, 거리로 감쇠하지도 않는다. 종전의
  **분수 분배(사슬은 감쇠 없음 · 3갈래는 1/3 씩)는 2026-08-29 에 은퇴했다.** 소유자 판정:
  「그냥 많이 재면 신호 약해지겠구나」 — 나누면 **더 많이 «관측된» 주어가 더 약한 점수**를
  받고, 그건 불량 분석에서 거꾸로다. 정수라 동점이 **정확**하고 허용오차를 지어낼 일이 없다.
- 🔴 **`reachable` 이 «분모»다. `reach` 만 읽으면 안 된다.** 0 은 두 가지를 같은 바이트로
  말한다 — ① 길은 있었는데 그 요인을 안 이고 있었다 ② **그 타입까지 갈 길이 아예 없었다.**
  `reach 0 / reachable 0` 은 ②이고 **차이가 아니라 미검사**다. `reach 0 / reachable 2` 라야
  「대조군은 닿을 수 있었는데 이건 아니었다」는 **진짜 대조**다.
- ⚠️ **분모는 «타입»이지 «항목»이 아니다.** 대조군이 다른 물리량 열여섯을 쟀으면 그쪽도
  `quantity` 에 닿은 것이라, 한 번도 안 잰 그 항목이 `0/2` 로 나와 진짜 차이처럼 보인다.
  항목 단위 분모는 **아직 없는 별개 질문**이다.
- **순위는 dominance 이지 한 수가 «아니다».** A 가 B 를 이기려면 관측 쪽이 «이상» 이고
  대조 쪽이 «이하» 이며 한쪽에서 «엄격히» 나아야 한다. 서로 한 축씩 이기면 **순위를 안
  매기고** 둘 다 1층에 두며 `incomparable: true` 를 단다. 같은 좌표면 `tied: true`.
  🔴 **두 수를 하나로 접는 규칙은 «없다»** — 접는 순간 그 발명이 답을 정한다.
- `evidence[]` 는 **모든 등수에** 붙는다. 「관측에서만 닿았다」와 「1등이 아니다」는 다른
  답이고, 그것을 나르는 것은 항목마다의 `evidence[].sign` 이다.

**소비 현황** (실측 2026-08-29 밤, `client2/src/rnd_board/` + `client2/dist/rnd-board.html` 이
싣는 번들):

```
읽힌다     propagation · state · message · contrast · complete · top_set
           ranked[] 의  id · label · rank · top · tied · incomparable · evidence[]
안 읽힌다   ranked[] 의  reach · reachable          <- 오늘의 «진짜» 잔여
```
🔴 **「이 블록은 소비자가 없다」로 뭉뚱그리지 마라.** 종전 이 사실이 문서 셋에 그렇게 적혀
있었고 **틀렸다** — `api.js` 가 `body.propagation` 을 풀어 `tied`·`incomparable` 로 화면에
낱말을 띄우고(`候補 목록`·`순위표`) `top_set` 을 그대로 나른다. **필드 넷을 한 문장에서
부정하면 그중 하나가 소비되는 순간 문장 전체가 거짓이 된다.** 잔여는 «항목마다의 두 수»이고,
그 둘이 안 읽히는 동안 화면은 「미검사」와 「진짜 차이」를 **구별할 재료를 안 받는다.**

### 4.3 실패와 빈 결과

| HTTP/상태 | `reason` 또는 뜻 | 처리 |
|---|---|---|
| 200 `ready` | 연결 증거 있음 | 그래프 렌더 |
| 200 `empty` | 씨앗은 유효하지만 연결 증거 없음 | 씨앗 1개와 설명을 렌더 |
| 422 | `subgraph_request_invalid` | id 철자·방향·범위 오류를 이름 대어 표시 |
| 422 | `predicate_not_declared` | `unknown[]` 과 `declared[]` 을 같이 돌려준다 |
| 503 | 원장 relation absent | 배포 부재를 «이름 대어» 답한다 |

## 5. 탐색 알고리즘

유계 BFS 이며 홉마다 프론티어를 **한 번** 질의한다. 노드별 N+1 질의를 하지 않는다.

1. `id` 를 엄격 디코드하고 씨앗 노드를 깊이 0 에 둔다.
2. 같은 깊이의 프론티어는 **선언된 엔터티**들이다 — 갈라야 할 종류가 없다.
3. 그 신원 배열을 `jsonb_to_recordset` 으로 **한 번** 조인한다. arm 은 둘이다:
   프론티어가 «주어»인 원자와, 프론티어가 «목적어»인 원자.
4. 인출된 원자는 «그 자리에서» 엣지 하나로 펼쳐진다. 다음 반복까지 세워 두지 않는다.
5. 🔴 **먼 쪽이 전진한다.** 프론티어에 «없는» 쪽이 `depth + 1` 을 받는다 — 들어오는 arm 에서는
   그 먼 쪽이 «주어»다. 양쪽 다 프론티어면 둘 다 `depth` 이고 전진할 것이 없다.
6. 목적어가 값인 원자는 노드를 만들지 않는다. 주어만 자리에 남는다.
7. 이미 본 노드·엣지는 id 로 dedupe 한다. **깊이는 최초 최소값을 유지한다.**
8. 어느 예산이든 닿으면 즉시 `truncated.<budget>=true` 와 사유를 남긴다. 조용히 끝나지 않는다.

🔴 **⑤ 가 없으면 걷기가 «한 홉»에서 조용히 멈춘다.** 주어에 늘 `depth` 를 주면 들어오는 arm 으로
찾은 먼 쪽이 «이미 지나간 깊이»에 앉아 다음 프론티어에 안 들어간다. 예산 플래그는 전부 false 라
그 멈춤은 「거기 아무것도 없다」와 구별되지 않는다. 실측(2026-08-28): 씨앗 `defect_kind{void}` ·
`follow=leads_to` · `hops=6` 이 노드 8 개를 «전부 깊이 0» 으로 돌려주었고, 같은 그래프를 한 노드
안쪽에서 씨앗으로 잡으면 `bond_pressure -> interface_unfill -> void` 가 보였다. 고친 뒤 같은 요청이
노드 21 · `hops_reached` 3 · `bond_pressure` 를 깊이 2 에 놓는다.

### 5.1 걷기 규칙 셋 (2026-08-29 착지) — 🔴 **이 절이 걷기 규칙의 «유일한 정본»이다**

> 🔴 **다른 문서는 이 절을 «링크»하고 규칙을 다시 적지 않는다.** 2026-08-29 밤 실측에서
> 이 사실이 **여섯 곳에 산문으로** 복사돼 있었고, 그중 **넷이 같은 거짓 문장**을 들고 있었다
> (「인출 쪽은 시험이 없다」 — 그날 밤 시험이 붙었는데 사본 넷이 몰랐다). 사본이 여섯이면
> 다음에도 여섯을 고쳐야 하고, 그러면 다음에도 넷이 남는다.
> 각 문서가 «자기 것»만 든다 — 정책 등급은 [ONTOLOGY_GRAPH_SPEC §7.5c](./ONTOLOGY_GRAPH_SPEC.md),
> 라우트 계약은 [backend §2](../architecture/backend.md), 재사용 방아쇠는
> [PRIMITIVES §3](../architecture/PRIMITIVES.md), 점검 항목은 [FEATURE_CHECKLIST](../qa/FEATURE_CHECKLIST.md).
> **판정 자체**의 정본은 [LEDGER_RULINGS R-2026-08-29-Q](../process/LEDGER_RULINGS.md) 이고,
> 이 절은 그 판정의 **계약·기전**을 소유한다.

위의 유계 BFS 위에 **거절 규칙 셋**이 얹힌다. 셋 다 「이 걸음을 갈 것인가」이고, 셋 다
**엔터티 «클래스»와 술어 이름**만 보며 도메인 낱말이 코드에 하나도 없다.

| # | 규칙 | 어디서 강제되나 | 끄면 빨개지는 시험 |
|---|---|---|---|
| ① | **`follow` 는 SQL 에서 좁힌다.** 안 따라가는 술어는 «인출조차» 안 된다 | `SqlEvidenceLookup.claims_for_entities` 의 `e.predicate = ANY(%(follow)s)` | `test_a_name_is_FETCHED_with_the_narrower_follow_rather_than_filtered_after` · `test_an_empty_static_intersection_skips_the_fetch_instead_of_passing_an_empty_list` |
| ② | **정적 노드는 «모으되 펼치지 않는다».** 예외는 «양 끝이 둘 다 정적»인 술어 | **자리 셋** — `subgraph()` 의 프론티어 클래스 분할 · `_expand_atom` 의 가드 · `_reach` 의 가드. 술어 목록은 `_static_step_predicates()` | 위의 둘(인출) · `test_the_static_step_predicates_are_DERIVED_from_the_declaration`(유도) · `test_reach_obeys_the_two_walk_rules_the_fetch_obeys`(대조) |
| ③ | **방금 «거꾸로» 타고 올라온 술어로 다시 «내려가지» 않는다.** 양 끝이 둘 다 정적이면 면제 | **자리 둘** — `_expand_atom` 의 `arrivals` 대조 · `_reach` 의 같은 검사 | `test_the_fetch_does_not_climb_a_container_and_come_back_down_to_its_siblings`(인출) · `test_reach_obeys_the_two_walk_rules_the_fetch_obeys`(대조) |

🔴 **「무엇이 이걸 재나」는 «시험 이름»으로 적는다 — grep 건수로 적지 않는다.** 이 표의
오른쪽 칸이 2026-08-29 밤에 «비어 있다»고 쓰인 적이 있고, 그 근거가 «`static_types` 를 grep 해
두 줄」이었다. 인출 쪽 시험 셋은 **`lookup.calls` 에 기록된 «인자»를 단언**하기 때문에 그
grep 에 안 걸린다 — 응답 그래프만 보면 「인출 후 필터」와 「인출 전 좁히기」가 **같은 노드를
돌려주므로** 애초에 그렇게 쓸 수밖에 없는 시험이다. **부재를 주장하려면 「이걸 끄면 빨개질
시험」의 «이름»을 대고, 못 찾았으면 못 찾았다고 적는다.**

- **① 이 규칙 «둘째»의 자리를 정한다.** ② 는 원래 `_expand_atom` 에서 «인출한 뒤» 버리고
  있었고, 그 자리는 한 층 늦다 — 원자를 이미 읽었고 `claims_scanned` 를 이미 태운 뒤다.
  📌 실측 2026-08-29(발견 하나를 씨앗, `hops=4`): `of_kind` 를 따라가면 claim **6,000**(천장) ·
  노드 **13** · 홉 **2** 에서 죽고, 안 따라가면 claim **371** · 노드 **315** · 홉 **4** 를 간다.
  `defect_kind` 는 원자 **103,841** 개를 «구별되는 목적어 하나»에 걸고 있어서, 걷기가 **버릴
  원자를 사느라 씨앗에서 두 홉 거리에서 죽고 있었다.**
- **② 는 노드가 아니라 «걸음»에 대한 규칙이다.** `정적 → 정적` 은 허용, `정적 → 동적` 은
  금지. 「정적 노드를 펼치지 마라」로 적으면 `s → s` 까지 잘리고, 그러면 인과 사슬 전체가
  사라진다 — 그 사슬은 링크마다 quantity↔quantity 다.
  🔴 **오늘 그 술어 집합은 `{leads_to}` 이고, 그것은 «선언에서 유도된» 값이다.** 정적 엔터티는
  `quantity@1` · `defect_kind@1` · `recipe@1` 셋(실측 2026-08-29, 라이브 선언의 `class: "static"`)이고,
  주어와 목적어가 «전부» 그 안에 드는 술어가 `leads_to@1` 하나다. 새 술어가 그 조건을 만족하면
  **코드 0줄로** 목록에 든다.
- **③ 은 「올라간 그 술어로 바로 내려가기」만 막는다.** `incoming(P) → outgoing(P)` 가 그
  모양이고, 그것이 닿는 곳은 **컨테이너의 다른 자식들** — 씨앗 자신의 형제라 구성상 한쪽뿐이고
  아무 말도 못 한다. 📌 실측 2026-08-29(발견 하나 · `direction=both` · `hops=4`): 돌아온 발견
  **199** 중 **189** 가 `die -[inspected 역방향]-> wafer -[inspected 정방향]-> die'` 로 왔다.
  🔴 **반대 모양 `outgoing(P) → incoming(P)` 은 «남긴다»** — 「내가 가리키는 것을 가리키는 것
  전부」이고, 그것이 「같은 레시피를 탄 웨이퍼들」을 묻는 방식이다. `P → Q → P` 도 남는다.
  검사는 **바로 붙은 한 쌍**에 대해서만, 그리고 그 방향에 대해서만 한다.

🔴 **규칙 ② 는 «세 자리», 규칙 ③ 은 «두 자리»에 적혀 있고 그게 비용이다.** ② 는 인출 «전»
(`subgraph()` 의 클래스 분할) · 인출 «후»(`_expand_atom`) · 대조(`_reach`) 셋이고, ③ 은
`_expand_atom` 과 `_reach` 둘이다. ② 가 하나 더 많은 것은 **정본이 옮겨 간 것이 아니라 층이
늘어난 것**이다 — 분할은 「안 사는」 일을(예산), `_expand_atom` 은 「안 그리는」 일을 한다.
✅ **분할이 선 뒤 `_expand_atom` 의 사본은 «오늘 발화하지 않는다» — 이제 실측이다**(총괄,
2026-08-29). 셋으로 확정했다: ⑴ **구조** — 정적 프론티어는 양 끝이 다 정적인 술어로만
인출되므로 far 가 정적이고, 동적 프론티어는 near 가 동적이라, 어느 쪽에서도
`near 정적 ∧ far 비정적` 이 성립하지 않는다. ⑵ **데이터** — 오늘 `static_follow` 는
`{leads_to}` 하나이고 그 원자 **22개 전부** 주어 `quantity`, 목적어 `quantity` 13 ·
`defect_kind` 9 로 **양 끝이 정적**이다. ⑶ **변이** — 이 가드를 no-op 으로 만들어도 ledger
시험군이 그대로다(448 passed, 빨강은 기존 9).

🔴 **그래서 이것은 «죽은 코드»가 아니라 «백스톱»이다.** 목적어 타입은 «선언»이 아니라 «원자»가
들고 오므로, `leads_to` 원자 하나가 동적 목적어를 들고 들어오는 날 이 가드가 «유일한» 방어가
된다. 지우려면 그 경우를 먼저 막아라. 대조가 자기 사본을 드는 이유는
그래프를 «다시» 걷기 때문이다 — 안 그러면 씨앗이 이름에서 기어 나오거나 컨테이너를 넘어 남의
자식으로 내려가, 분수를 뗀 순간 후보 996 개가 **전부 `[2, 2]`** 로 나왔다(실측 2026-08-29).
규칙이 넷째로 늘면 **여기가 먼저 지울 중복**이다.

📌 **`backbone_hops` 는 이 셋과 «다른 축»이다** — 걸음을 거절하지 않고 «어느 예산에서 빼나»만
정한다. 그래서 §4.1 에 있고 이 표에 없다. 시험은
`test_backbone_hops_buys_depth_for_steps_that_stay_inside_the_world`(0 이면 노드 2, 4 면 노드 6).

역방향 목적어 탐색은 payload 를 문자열로 훑지 않는다. 정확 표현식 인덱스를 쓴다.

| 인덱스 | 소비 질의 |
|---|---|
| `idx_ledger_object_entity ((object_payload->>'type'), (object_payload->'keys'))` partial | 엔터티 ← 목적어 원자 |
| `idx_ledger_subject_entity (subject_type, subject_keys)` | 엔터티 ← 주어 원자 |

내부 Claim scan 상한은 `min(6000, max(200, edge_limit × 2))` 이고 요청자가 직접 늘릴 수 없다.

## 6. 화면

이 문서는 라우트 계약만 소유한다. 걷기를 그리는 화면의 계약은
[`docs/architecture/frontend.md`](../architecture/frontend.md) 가 소유한다.
⚠️ 종전 이 절이 가리키던 `/ledger-graph.html` 은 `client2/` 에 **없다**(실측 2026-08-28).

## 7. 검증 기준

정본은 `server/tests/test_ledger_subgraph.py` 이고, 그 파일이 못 박는 것은 다음이다.
(문장을 여기에 옮겨 적으면 두 벌이 되고, 두 벌은 어긋난다.)

- 같은 소스·분자·시각의 원자 둘은 같은 Source Event id 이고, 소스나 시각이 다르면 갈린다.
- 씨앗 하나로 온 요청은 부호 씨앗이 생기기 «전과 같은 인자 하나»로 `subgraph()` 에 닿는다.
- 선언에 없는 `follow` 는 «거절을 걸어서» 확인한다 — 빈 그래프가 아니라 422 다.
- 엔터티 라벨의 키 순서가 **라이브 `entities` 선언**에서 나온다.
- 예산에 닿은 응답은 `truncated` 없이 완결처럼 보이지 않는다.
- 비정준·위조 id 는 422 다.
- **닿으면 1 이다 — 갈래가 아무리 넓어도.**(`test_reaching_counts_one_however_wide_the_fork`)
  🔴 종전 이 자리는 「전파의 몫은 갈라지는 자리에서만 나뉜다(3갈래는 1/3 씩)」였고,
  그 분수 규칙은 **은퇴했다**(§4.2-bis).
- **대조가 인출과 «같은 두 규칙»으로 걷는다**(`test_reach_obeys_the_two_walk_rules_the_fetch_obeys`) —
  §5.1 의 ②③. 대조가 인출보다 넓게 걸으면 모두가 모두에게 닿아 순위가 사라진다.
- **`reach` 0 이 어느 0 인지를 `reachable` 이 말한다**(`test_a_reach_of_zero_reports_whether_the_side_could_have_reached_that_kind`).
- 은퇴한 라우트들은 부호 씨앗 인자를 받지 않는다.

## 8. 남겨 둔 경계

1. `supersedes` 는 원자에 보존하지만 대상의 `occurred_at` 이 컬럼에 없어 역탐색 엣지를 만들지
   않는다. UUID 만으로 전 파티션을 걷는 숨은 비용을 만들지 않기 위해서다.
2. Source Event 는 cross-source 물리 사건이 아니다. 같은 물리 사건 병합은 «선언된» 동일성
   주장과 검증 규칙이 생긴 뒤의 일이다.
3. 🔴 **종전 「발견이 노드가 아니다」·「순위를 깨울 인자가 없다」는 «둘 다» 거짓이 됐다.**
   발견은 `defect@1`(키 `void_uid`) 엔터티이고 `of_kind@1` 로 `defect_kind@1` 까지 걸어 나간다.
   순위 블록은 §4.2-bis 대로 «항상» 계산된다. 이 자리에 남는 경계는 아래 4·5 다.
4. **발견의 «물리 모델»은 아직 수식어다.** `observed@1` 의 목적어는 `entity_ref → defect@1` 이
   됐지만 선택 수식어 일곱(`radius_x` · `inchip_x` · `inchip_y` · `radius_y` · `unit` · `gate` ·
   `run_uid`)은 여전히 엣지에 실려 있고 **엔터티도 술어도 아니다**(실측 2026-08-29, 라이브 선언).
   즉 「같은 스캔(`run_uid`)의 다른 발견」은 오늘 **걸어서 못 간다** — 그 걸음을 여는 것은
   선언 변경이고 원자 재적재이며 소유자의 판정이다.
5. **`reachable` 의 분모가 «타입»이다**(§4.2-bis). 항목 단위 분모 — 「대조군이 «이 물리량을»
   쟀나」 — 는 아직 답할 수 없다. 그리고 `reach` 두 수를 하나로 접는 규칙이 없다: 접는 날
   그 자리는 `_propagation` 이지 화면이 아니다.
