# 입문 — 한 행의 여행: 모든 구성요소의 역할과 실물 예시

> **Status:** 🟢 Living | **Last-verified:** 2026-08-27 | **Owner:** Server / Ledger
> **Source-of-truth:** `server/config/ontology/ledger_config.json`(선언) ·
> `server/ledger/setup_bundle.py`(검증기) · `server/ledger/gate.py`(게이트)

> 실제 표의 행 하나가 원장 원자가 되기까지. 각 요소가 «언제 등장해 무엇을 하는지»를 실물로.
> 이 문서의 모든 행·원자·이름은 2026-08-27 라이브 환경에서 «인용»한 것이다.

## 🏛️ 기둥 둘 — 이 문서 전체가 이 위에 선다

```
① 원장은 «선언» 위에 서 있다   원자 645,203 «전부» 선언에서 났다
                            선언 하나(ledger_config.json)가 entities 6 · vocabulary 10 을 정한다
② 답은 «walk» 이 한다         읽기측은 마킹에서 걸어서 닿는 서브그래프를 가져온다
                            차트는 그 서브그래프를 «보는 창»이지 각자 질의하지 않는다
```

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
 "object_kind": "value",
 "object_payload": {"value": 7.691,
                    "qualifiers": {"finding_kind": "void", "unit": "um", "gate": 7.0,
                                   "inchip_x": 7475.16, "inchip_y": 4857.94, "radius_y": 7.591,
                                   "run_uid": "sat|SYN-AUG-BW-001-01|10|10|7|…"}},
 "source_who": "void_observation"}
```

문자열이던 행이 「CL-2601-007-A2 의 01번 자리가 …-A3 의 01번 자리로 갔다(split)」라는
**검사받은 문장 하나**가 됐다.

## 4. 읽기측 — walk 하나, 창 여럿

쓰기측(1~12)은 문장을 **눕히기만** 한다. 답은 읽기측이 질의 순간에 만든다.

```
마킹      부호 붙은 «노드 집합». 화면 상태가 아니라 walk 의 «시작점»이다
walk     그 시작점에서 «걸어서 닿는 하위 그래프»를 가져온다
부품      선언하는 것은 둘뿐 — { start = 읽을 마킹,  collect = 무엇을 걷나 }
체인      마킹1 --walk--> 서브그래프 --찍기--> 마킹2 --walk--> …  «계속»
```

🔴 **차트는 서브그래프를 «보는 창»이다.** 맵과 트렌드는 «같은 collect»이고 시작점만 다르다 —
맵은 다른 데이터가 아니라 «한 그룹으로 좁힌 같은 데이터»다.

### 무엇이 walk 을 좁히나

| 손잡이 | 무엇을 정하나 | 실측 (씨앗 `SYN-BW-101-16`) |
|---|---|---|
| `follow` | 어느 술어를 건너나 | 없이 nodes 839(3,000 에서 잘림) → `inspected`+`observed` 로 **89** |
| `collect` | 무엇을 모아 오나 | 개체 · 값 · 수량 … |
| `node_limit` | 예산 | 넘으면 «잘림»으로 표시된다 — 잘림은 «부재»가 아니다 |
| 선언 | 엣지가 아예 있느냐 | `die@1.references` 를 지우면 엣지가 «사라지고» 넣으면 «생긴다». 같은 코드로 |

### 라이브 읽기 라우트

```
GET /api/ledger/subgraph         walk 본체. 마킹에서 걸어 서브그래프를 낸다
GET /api/ledger/subgraph/table   같은 것을 표 모양으로
GET /api/ledger/declaration      선언 자체 (원장을 한 줄도 안 읽는다)
GET /api/ledger/structure        유형 수준의 그림 — 선언된 절반 + 센서스 절반을 «병합»
GET /api/ledger/trends           시계열
GET /api/ledger/lot_map          맵
GET /api/ledger/composition      구성
GET /api/ledger/siblings         또래 대조
GET /api/ledger/kinds            발견 종류 카탈로그
GET /api/ledger/selection/resolve  선택 해소
```

## 5. `/structure` — 「이 원장은 무엇을 말할 줄 아나」

유형 수준이다. 랏·웨이퍼·보이드 같은 인스턴스는 한 건도 나오지 않는다.
**두 절반을 만들어 병합한다**:

```
선언된 절반   선언의 entities × vocabulary 에서 «생성». 손으로 그린 목록이 «없다»
센서스 절반   ledger_events 를 GROUP BY 한 방
병합         선언에 있고 데이터에 없으면 declared_only (atoms: 0)
             데이터에 있고 선언에 없으면 undeclared  (= 드리프트)
```

실측 2026-08-27: 노드 **6** · 엣지 **12** · 드리프트 **0**.
(`atoms: 0` 은 「세었고 없다」이고 `atoms: null` 은 「아무도 안 셌다」이다. 둘은 다른 답이다.)

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
