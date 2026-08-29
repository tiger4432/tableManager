# Ledger Evidence Subgraph — 걷기 하나가 답한다

> **Status:** 🟢 Living · **Last verified:** 2026-08-28
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

📌 실측 2026-08-29: 선언된 술어 열셋의 목적어가 **전부** `entity_ref` 다 — `value` 목적어를
내는 술어는 하나도 없다. 위 규칙은 여전히 계약이지만 오늘 그것에 걸리는 원자가 없다.

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

`/api/ledger` 아래 서빙되는 것은 **둘**이다 — `GET /subgraph` 와 `GET /declaration`
(`declaration` 은 원장을 한 줄도 안 읽고, 선언이 무엇을 말할 수 있는지만 답한다).

### 4.1 요청

```http
GET /api/ledger/subgraph
  ?id=<opaque-node-id>
  &hops=12
  &direction=both
  &node_limit=400
  &edge_limit=1200
  &follow=inspected&follow=bonded_from
```

| 파라미터 | 필수 | 기본 | 허용 범위 | 의미 |
|---|---:|---:|---|---|
| `id` | 예 | — | 엔터티 id | 시작 노드. 응답의 어떤 노드 id 든 그대로 재사용 |
| `hops` | 아니오 | 12 | 1..40 | 구조 홉 |
| `direction` | 아니오 | `both` | `outgoing`·`incoming`·`both` | 주어 쪽·목적어 쪽 중 어느 arm 을 인출할지 |
| `node_limit` | 아니오 | 400 | 10..1000 | 응답 노드 하드캡 |
| `edge_limit` | 아니오 | 1200 | 20..3000 | 응답 엣지 하드캡 |
| `positive` | 아니오 | — | 노드 id, 반복 가능 | 추가 관측 씨앗. `id` 는 항상 positive 다 |
| `negative` | 아니오 | — | 노드 id, 반복 가능 | 대조군 씨앗. **목록에 없는 주어는 미검사이지 대조군이 아니다** |
| `follow` | 아니오 | — | 선언된 술어 이름, **반복 가능** | 이 술어만 따라간다. 없으면 전부 |

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
  "propagation": {"collect": null, "state": "not_requested"},
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
- ⚠️ **`propagation` 은 오늘 «항상» `not_requested` 다.** 순위를 요청하던 인자가 은퇴하면서
  라우트에서 그 블록을 깨울 방법이 없다. 안의 기계(`_reach`)는 살아 있고 단위 시험이 그
  분배 규칙을 못 박고 있다 — 다시 필요해지는 날 «인자»가 돌아오는 것이지 코드가 새로 생기는
  것이 아니다.
- 승자만 남기는 해결기를 이 경로는 부르지 않는다. 정정 전 원자가 그대로 보인다.

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
- 전파의 몫은 **갈라지는 자리에서만** 나뉜다(사슬은 감쇠하지 않고, 3갈래는 1/3 씩).
- 은퇴한 라우트들은 부호 씨앗 인자를 받지 않는다.

## 8. 남겨 둔 경계

1. `supersedes` 는 원자에 보존하지만 대상의 `occurred_at` 이 컬럼에 없어 역탐색 엣지를 만들지
   않는다. UUID 만으로 전 파티션을 걷는 숨은 비용을 만들지 않기 위해서다.
2. Source Event 는 cross-source 물리 사건이 아니다. 같은 물리 사건 병합은 «선언된» 동일성
   주장과 검증 규칙이 생긴 뒤의 일이다.
3. 발견이 노드가 아니다(§1). 노드로 만드는 것은 선언 변경이고 원자 재적재이며 소유자의 판정이다.
4. 순위(`propagation`)를 깨울 인자가 없다(§4.2).
