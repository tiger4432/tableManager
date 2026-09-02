# 입문 — 한 행의 여행: 모든 구성요소의 역할과 실물 예시

> **Status:** 🟢 Living | **Last-verified:** 2026-09-02 (🔴 **읽기 라우트가 「둘」이라 적혀 있었다 — 실제는 «셋»**(`gaps`, 2026-08-31 신설. 그날 다른 넷은 고쳐졌는데 이 파일만 빠졌다) · `follow` 가 **키를 받는다**와 그 «둘째» 422 · 걷기 규칙 셋 → **넷** · 🔴 **한 파일 안에서 술어 수를 「13」과 「열넷」으로 «둘 다» 적고 있었다** — 수를 지우고 묻는 자리를 남겼다) · 직전 2026-08-30 (`references` 칸을 작성 폼이 그리기 시작한 것만) · 직전 2026-08-29 심야 `290bb1af` 재측정 · 그 직전 2026-08-29 밤 (걷기 규칙 셋 · `backbone_hops` · `in_container@1` 반영. 직전: 개정 6 — 읽기측 §4·§5 와 `observed` 예시 정정) | **Owner:** Server / Ledger
> **Source-of-truth:** `server/config/ontology/ledger_config.json`(선언) ·
> `server/ledger/setup_bundle.py`(검증기) · `server/ledger/gate.py`(게이트)

> 실제 표의 행 하나가 원장 원자가 되기까지. 각 요소가 «언제 등장해 무엇을 하는지»를 실물로.
> 쓰기측(§0~§3)의 행·원자는 2026-08-27 라이브 환경 인용이고, 읽기측(§4·§5)과 선언 수는
> 2026-08-29 실측이다. ⚠️ **인용을 그대로 두면 인용도 낡는다** — 이 문서의 `observed` 예시는
> 2026-08-27 에 정확했고 2026-08-28 에 게이트가 거절하는 원자가 됐다(§3 참조).

## 🏛️ 기둥 둘 — 이 문서 전체가 이 위에 선다

```
① 원장은 «선언» 위에 서 있다   선언 하나(ledger_config.json)가 entities 9 · vocabulary 14 를 정한다
                            개정 6: 노드는 «선언된 엔터티»뿐, 엣지는 «선언된 술어»뿐이다
② 답은 «walk» 이 한다         읽기측은 마킹에서 걸어서 닿는 서브그래프를 가져온다
                            차트는 그 서브그래프를 «보는 창»이지 각자 질의하지 않는다
```

🔴 **「원자가 «전부» 선언에서 났다」고 적지 마라 — 선언이 그것을 약속하지 않는다.** 선언은
「번역기가 무엇을 만드는가」를 정할 뿐 「무엇이 써지는가」를 막지 않는다. 실측 2026-08-29:
`store.write_batch` 를 직접 부르는 파일이 `server/scripts/` 에 «일곱» 있고, 그 문으로 들어온
원자는 원장에 있으면서 **선언이 이름을 몰라 walk 의 주어가 되지 못한다.** 정당한 호출자는
`server/ledger/runtime_v2.py` «하나»다.

## 0. 출발 — 실물 행 (`lot_slot_move` 뷰, 라이브)

```
from_lot=CL-2601-005 · from_slot=04 · to_lot=CL-2601-005-A5 · to_slot=04
wafer=WF.010504 · event_time=2026-05-03 11:25:00 · event_type=split
```

이 행은 아직 **뜻이 없다.** 그냥 문자열이다. 아래 요소들이 뜻을 붙인다.

## 1. 여행 순서대로 — 요소 × 역할 × 이 예시에서

| # | 요소 | 정체 (비유) | 역할 | 이 예시에서 실물 |
|---|---|---|---|---|
| 1 | **소스 관계** | 세계의 수첩 | 사실이 행으로 눕는 곳. 뜻 없음 | 위의 행 |
| 2 | **`table_config.json`** | 표의 주민등록 | 이 표의 행을 시스템이 «지목»할 수 있게 하는 것 | 선언이 고를 수 있는 관계 집합이 곧 여기 있는 것 |
| 3 | **선언의 `sources.<이름>`** | 이 소스의 독해 지침서 | 「이 표를 어떻게 읽는가」 전부. 칸은 넷: `read` · `prepare` · `map` · `bind` | `relation: lot_slot_move` |
| 4 | **`read`** | 제본기 | 행을 «분자(한 사건)»로 묶고, 언제인지·어디까지 읽었는지를 정한다 | `unit: row` · `identity: [from_lot, from_slot, to_lot, to_slot, wafer, event_time]` · `occurred_at: {column: event_time, timezone: Asia/Seoul}` |
| 5 | **`prepare`** | 자료 준비 | 필요한 컬럼을 모은다(조인이 필요하면 여기서) | `implementation_id: direct-join` |
| 6 | **`map`** | 통역사 | 분자를 원자 후보로 편다. **구현은 «선언이 고르는 것»이다** | `implementation_id: declarative-role` |
| 7 | **`bind`** | 문장 작성 | 원자의 «칸마다» 어느 컬럼이 들어가는지 적는다. 코드 0줄 | 아래 §2 |
| 8 | **선언의 `vocabulary`** | 문법책 | 술어마다 주어·목적어의 «서명». 서명에 안 맞으면 못 들어온다 | `slot_map@1`: 주어 `lot_slot@1`, 목적어 `entity_ref` → `lot_slot@1`, 수식어 `event_type`(선택) |
| 9 | **선언의 `entities`** | 국어사전 | 개체 타입과 그 «신원 키» | `lot_slot@1`: keys `[lot, slot]` |
| 10 | **게이트** (`ledger/gate.py`) | 검문소 | 원자마다 선언과 대조 — 하나라도 틀리면 **분자 전체** 거절 | 주어가 `lot_slot` 인가? 목적어가 `lot_slot` ref 인가? |
| 11 | **봉투** (`ledger/envelope.py`) | 규격 서류 양식 | 모든 원자의 고정 필드 모양 | §3 의 실물 원자 |
| 12 | **원장** (`ledger_events`) | 등기부 | 통과한 문장이 영구히 눕는 곳. 추가 전용 | 원자 1 삽입 |
| 13 | **읽기측** | walk | 마킹에서 걸어서 서브그래프를 «질의 시점에» 만든다 | §4 |

## 2. `bind` — 「코드 0줄」이 무슨 뜻인가

이 소스의 `bind.mappings["seat-to-seat"]` 전문(라이브에서 인용, `approval_status` 생략):

```jsonc
{ "predicate": "slot_map@1",
  "bind": {
    "occurred_at": { "kind": "column", "column": "event_time" },
    "subject":     { "kind": "entity", "entity_type": "lot_slot@1",
                     "keys": { "lot":  { "kind": "column", "column": "from_lot" },
                               "slot": { "kind": "column", "column": "from_slot" } } },
    "target":      { "kind": "entity", "entity_type": "lot_slot@1",
                     "keys": { "lot":  { "kind": "column", "column": "to_lot" },
                               "slot": { "kind": "column", "column": "to_slot" } } },
    "event_type":  { "kind": "column", "column": "event_type" } } }
```

읽는 법은 한 줄이다: **「이 술어의 주어는 이 컬럼들로 이름 붙은 이 개체다」.**
자리가 하나 늘거나 컬럼 이름이 바뀌면 «이 선언»만 바뀐다. 파이썬은 한 줄도 안 바뀐다.

🔴 **`slot_map` 은 자리에서 자리로 간다** (`lot_slot -> lot_slot`).
랏에서 랏으로 가면서 슬롯을 수식어로 달고 다니지 «않는다» — 자리가 노드이고 이동이 엣지 자체다.

## 3. 도착 — 실물 원자 (라이브 원장에서 인용)

```json
{"predicate": "slot_map", "subject_type": "lot_slot",
 "subject_keys": {"lot": "CL-2601-007-A2", "slot": "01"},
 "object_kind": "entity_ref",
 "object_payload": {"type": "lot_slot", "keys": {"lot": "CL-2601-007-A2-A3", "slot": "01"},
                    "qualifiers": {"event_type": "split"}},
 "occurred_at": "2026-05-03T06:51:00+09:00", "source_who": "lot_slot_move"}
```

다른 술어의 실물도 같은 봉투다:

```json
{"predicate": "processed_with", "subject_type": "wafer", "subject_keys": {"wafer": "WF-LOT-A-05"},
 "object_kind": "entity_ref",
 "object_payload": {"type": "recipe", "keys": {"recipe": "R-CLEAN-01"},
                    "qualifiers": {"step": "CLEAN"}},
 "occurred_at": "2026-08-01T23:12:00+09:00", "source_who": "wafer_process_recipe"}

{"predicate": "observed", "subject_type": "die",
 "subject_keys": {"x": 10.0, "y": 10.0, "mat_id": "SYN-AUG-BW-001-01", "mat_type": "Wafer"},
 "object_kind": "entity_ref",
 "object_payload": {"type": "defect", "keys": {"void_uid": "sat|SYN-AUG-BW-001-01|10|10|7|…"},
                    "qualifiers": {"unit": "um", "gate": 7.0,
                                   "inchip_x": 7475.16, "inchip_y": 4857.94, "radius_y": 7.591,
                                   "run_uid": "sat|SYN-AUG-BW-001-01|10|10|7|…"}},
 "source_who": "void_observation"}
```

🔴 **[2026-08-28] 종전 이 자리의 `observed` 예시는 `object_kind: "value"` 에 수식어
`finding_kind: "void"` 를 달고 있었고, 그 원자는 «오늘 게이트가 거절한다».**
`observed@1` 의 목적어는 이제 `entity_ref` → `defect@1` 이고, `finding_kind` 는 수식어 목록에
없다(`unknown_payload_field`). 발견의 «종류»는 수식어가 아니라 **노드**다 — `of_kind@1` 이
`defect@1` 에서 `defect_kind@1` 로 간다. 그 판의 요점은 이름 바꾸기가 아니라 **종점을 없애는
것**이다: 발견이 노드면 거기서 종류·스캔·같은 스캔의 다른 발견으로 «걸어 나갈 수» 있고,
값이면 거기서 끝이라 붙일 자리가 없다.

📌 **선언된 술어의 대다수는 목적어가 `entity_ref` 이고, 그렇지 «않은» 것이 둘 있다.**
⚠️ **[2026-09-02] 종전 이 자리의 수(「열넷 중 열둘」)는 «이 박스»의 수다** — 선언
`server/config/ontology/ledger_config.json` 은 **gitignore 대상**이라 운영은 자기 선언을
따로 든다. 여기서 남는 것은 «수»가 아니라 **「목적어가 entity_ref 가 아닌 술어가 있고,
그것은 붙일 자리가 없다」**는 성질이고, 오늘의 수는
`GET /api/ledger/declaration` 이 답한다. (이 박스 실측 2026-08-29 심야.) 나머지 둘은 `has_netdie@1`(`value`) 과 `register@1`(`none` — 등록 술어라
목적어가 ∅). ⚠️ **종전 이 자리의 「열셋이고 전부 `entity_ref`, `value` 목적어를 내는 술어는
하나도 없다」는 «둘 다» 틀렸다** — 그때도 `has_netdie@1` 은 `value` 였다. 그래서 §3 의
「목적어가 값이면 노드를 안 만든다」는 계약이면서 **오늘 실제로 발화하는 갈래**다.

문자열이던 행이 「CL-2601-007-A2 의 01번 자리가 …-A3 의 01번 자리로 갔다(split)」라는
**검사받은 문장 하나**가 됐다.

## 4. 읽기측 — walk 하나, 창 여럿

쓰기측(1~12)은 문장을 **눕히기만** 한다. 답은 읽기측이 질의 순간에 만든다.

```
마킹      부호 붙은 «노드 집합». 화면 상태가 아니라 walk 의 «시작점»이다
walk     그 시작점에서 «걸어서 닿는 하위 그래프»를 가져온다
부품      선언하는 것은 둘뿐 — { start = 읽을 마킹,  follow = 어느 술어를 어디까지 건너나 }
체인      마킹1 --walk--> 서브그래프 --찍기--> 마킹2 --walk--> …  «계속»
```

🔴 **차트는 서브그래프를 «보는 창»이다.** 맵과 트렌드는 «같은 걷기»이고 시작점만 다르다 —
맵은 다른 데이터가 아니라 «한 그룹으로 좁힌 같은 데이터»다.

### 무엇이 walk 을 좁히나

| 손잡이 | 무엇을 정하나 | 비고 |
|---|---|---|
| `positive` / `negative` | 씨앗이 «부호 붙은 집합»이 된다 | 목록에 없는 주어는 **미검사이지 대조군이 아니다** |
| `follow` | 어느 술어를 건너나, 그리고 🆕 **그 술어가 «어디까지»** | 반복 파라미터. `follow=inspected` 는 술어만 고르고, `follow=inspected:x,y` 는 **그 엣지가 씨앗과 그 키가 같은 노드로만** 걷게 한다(콜론이 없으면 제약도 없다 — 여태까지 그대로). 거절이 **둘**이고 둘 다 «조용한 빈 답이 아니다»: 선언에 없는 이름은 **422 `predicate_not_declared`**, 씨앗이 그 키를 못 들면 **422 `subgraph_request_invalid`** |
| `node_limit` · `edge_limit` | 예산 | 넘으면 «잘림»으로 표시된다 — 잘림은 «부재»가 아니다 |
| `backbone_hops` | 같은 자재에 머무는 걸음의 «둘째 예산» | 양 끝이 **둘 다 dynamic** 인 걸음에만 쓴다. 기본 0 이고, R&D 보드의 좌석 넷이 켠다 |

🔴 **[2026-08-29 셋 · 2026-09-02 넷] 걷기는 «거절 규칙 넷»을 진다 — 그중 셋은 손잡이가 아니다.**
요청이 못 고른다: 무엇이 정적인지도, 정적끼리 어느 술어로 갈 수 있는지도 **선언이 정하고
walk 이 매 요청 읽는다.** 넷째(키 제약)만 **호출자가 켤 때 도는** 규칙이고, 그것도 «키 이름»은
선언이 준다. 규칙의 내용·기전·시험·실측은
**[LEDGER_EVIDENCE_SUBGRAPH_SPEC §5.1](../../spec/LEDGER_EVIDENCE_SUBGRAPH_SPEC.md) 이 «유일하게»
소유한다** — 입문서는 「그런 게 있고 요청이 못 고른다」까지만 안다. 여기 옮겨 적지 마라.
⚠️ 종전 이 표의 `continues_hops`(술어마다 `continues: true`)는 **2026-08-29 에 은퇴**했고
별칭을 받지 않는다 — 판정이 «술어의 플래그»에서 «엔터티의 class» 로 올라갔다.

🔴 **[2026-08-28] `collect` 는 «없다».** 노드 «종류»를 고르던 축인데, 종류가 「선언된 엔터티」
하나가 된 날 함께 은퇴했다. 같은 날 `observations` 와 `include_values` 도 떠났다.
좁히는 것은 `follow` 다.

🔴 **[2026-08-28] 선언의 `entities.<타입>.references` 로 엣지를 «만들 수» 없다.**
그것을 읽던 `_link_containers` 가 삭제됐고 `die@1.references` 도 같은 밤에 지워졌다
— 합성 엣지 `in_container` 가 잇던 쌍 128 중 «유일한 연결»이 «0» 이었기 때문이다
(원자 엣지 `inspected` 가 이미 양방향으로 잇는다). **다시 선언해도 엣지는 안 생긴다.**
🔴 **[2026-08-30] 그런데 작성 폼이 이 칸을 «그리기 시작했다**(`1d17c34a` — `ledger_skeleton.json` 에
`references` 노드가 생겼고 라벨이 「참조 엣지」다). **폼에 있다고 도는 것이 아니다** — 오늘 이 필드를
읽는 것은 검증기(`setup_bundle._validate_references`) «하나»이고, 그 검증은 문법만 본다.
운영자가 여기를 채우면 **거절 없이 저장되고 엣지는 0개**다.

✅ **[2026-08-29] 그리고 그 다리는 «술어로» 돌아왔다.** `in_container@1`(`die@1` → `wafer@1`)은
오늘 `vocabulary` 의 선언된 술어이고 **원자를 갖는다** — `bonded_from` 소스의 매핑 둘
(`core-die-in-core-wafer` · `base-die-in-base-wafer`)이 발화한다. 그래서 `follow=in_container`
도 정상이다(종전에는 422 였다). **바뀐 것은 「다리가 필요한가」가 아니라 「어느 문으로
들어오나」다** — 투영이 합성하면 안 되고, 표 → 소스 선언 → 번역기로 들어와야 한다.
✅ 라이브 선언과 `.sample` 이 **같다**(실측 2026-08-29 밤: 어휘 14 대 14, 차집합 양쪽 0).
⚠️ 종전 이 자리는 「`.sample` 은 아직 열셋」이라 적었고 그것은 **몇 분짜리 참**이었다.

### 라이브 읽기 라우트 — **셋이다**

```
GET /api/ledger/subgraph         walk 본체. 마킹에서 걸어 서브그래프를 낸다
GET /api/ledger/declaration      선언 자체 (원장을 한 줄도 안 읽는다)
GET /api/ledger/gaps             「무엇이 아직 없나」 (인자 없으면 DB 에 닿지도 않는다)
```

⚠️ **[2026-09-02 정정] 여기가 「둘이다」였다.** `gaps` 는 2026-08-31 에 붙었고 그날 다른 문서
넷은 고쳐졌는데 이 파일만 빠졌다 — **입문서라 「전부 다」로 읽히는 자리**여서 특히 나쁘다.
🔴 **수를 세는 문장은 라우트가 하나 늘 때마다 거짓이 된다.** 정본은
`server/ledger_trace_router.py` 의 `@router.get` 전수다.

⚰️ **2026-08-28 에 은퇴한 것**: `subgraph/table` · `structure` · `trends` · `lot_map` ·
`composition` · `siblings` · `kinds` · `selection/resolve`, 그리고 그 앞의 `trace` · `explore` ·
`explore_entity` · `coverage` · `journey` · `lots`. **전부 «키를 받는» 라우트였다** — 키를 받으면
키마다 한 번씩 불리고, 마킹을 받으면 마킹 «전체»에 한 번 답한다. 실측: 한 페이지 로드에
요청 13 · 라우트 5 · 그중 walk 1 · 정확히 중복 2.

## 5. `/declaration` — 「이 원장은 무엇을 말할 줄 아나」

유형 수준이다. 랏·웨이퍼·보이드 같은 인스턴스는 한 건도 나오지 않는다.
응답은 `{state, entities[{type, keys[]}], predicates[{name, subjects[], object, origin}]}` 이고
**원장을 한 줄도 안 읽는다** — 답이 «선언»이라, 선언이 바뀌면 이 답이 바뀌고 코드는 안 바뀐다.

🔴 **[2026-08-28] 종전 이 절은 `/structure` 를 서술했고, 그 라우트도 `ledger_structure.py` 도
없다.** 그것은 **두 절반의 병합**이었다 — 선언된 절반(선언에서 생성) + 센서스 절반
(`ledger_events` 를 `GROUP BY` 한 방) — 그래서 `declared_only`(선언은 있는데 데이터 0)와
`undeclared`(데이터는 있는데 어휘에 없다 = 드리프트)를 답할 수 있었다.
**오늘 남은 것은 선언된 절반뿐이고, 그래서 드리프트를 답하는 화면이 없다.**
다시 만든다면 그것은 walk 의 «인자»여야지 새 라우트가 아니다.

📌 **선언의 «수»를 여기 적지 않는다** — 엔터티도 술어도 `GET /api/ledger/declaration` 이 답한다.
⚠️ **[2026-09-02 정정] 여기가 「술어 13」이라 적고 있었고, 같은 파일 §「목적어」 절이 같은 것을
「열넷」이라 적고 있었다** — 한 파일 안에서 서로를 반박했다. 🔴 **그리고 그 수는 `follow` 가
대조받는 «바로 그 집합»이라**, 틀린 수는 「어느 이름이 422 인가」를 틀리게 가르친다.
수를 적는 대신 **묻는 자리**를 적는 것이 이 절의 규율이고, 그 규율을 이 절이 자기 문장에
안 적용하고 있었다.

## 6. 쓰기측과 읽기측의 결정적 비대칭 (함정의 뿌리)

- **쓰기측 선언이 틀리면 → 게이트가 거절한다.** 시끄럽고, 즉시고, 이름이 붙는다.
- **읽기측 선언이 틀리면 → 그냥 안 보인다.** 엣지가 안 생기고, 잎 철자가 틀리면 영원히 «모름»이다.
  오류가 아니라 «침묵»이다.

그래서 읽기측에서는 **「없다」의 종류를 갈라서** 말해야 한다:

```
안 골랐다  ·  그런 종류가 없다  ·  서버가 답할 수 없다  ·  걸었는데 비었다  ·  «잘렸다»
```
🔴 마지막이 특히 그렇다 — `node_limit` 에 걸린 «잘림»을 «부재»로 읽으면 없는 결론이 선다.

## 7. 한 문장 요약

**소스**는 사실을 눕히고, **선언**이 읽는 법·문법·신원을 «전부» 정하고, **게이트**가 대조하고,
**봉투**에 담겨 **원장**에 눕고, **walk** 이 마킹에서 걸어 서브그래프를 만들고, **차트**가 그것을
보여 준다. — 사람이 만지는 것은 **선언 하나**뿐이다.
