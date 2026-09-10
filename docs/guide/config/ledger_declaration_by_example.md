# 원장 선언 — 파운드리 낱말로 읽는 «셋업 예시 하나»

> **Status:** 🟢 Living | **Written:** 2026-09-08 08:3x (소유자 「팔란티어 기준으로 셋업 예시 하나만, 원장 선언 참고하게」) | **Owner:** 총괄
> 문법 정본은 `server/ledger/setup_bundle.py`. 이 문서는 «대응표 + 예시 하나»이고, 키 이름은 출하 샘플 `server/config/sample/ledger_config.json.sample` 에서 «그대로» 가져왔다.
> `attributes` 는 2026-09-08 S-52 로 착지(문법·원자·걷기·선언 발행·선언창 슬롯·출하 샘플 `dtjob@1.attributes`).

## 0. 대응표 — 파운드리 ↔ 원장 선언

| 파운드리 | 원장 선언 | 어디에 적나 |
|---|---|---|
| Object type (`Wafer`) | 엔티티 `wafer@1` | `entities` |
| Primary key | `keys` | `entities.<t>.keys` |
| Property (`product`, `lot`) | **`attributes`** | `entities.<t>.attributes` (이름) + `sources.<s>.bind.entities.<t>.attributes` (컬럼, 소스당 한 번) |
| Link type (`Wafer → Die: inspected`) | 술어 `inspected@1` | `vocabulary` (`subjects` · `object.kind: entity_ref` · `types`) |
| Link property (링크에 붙는 값) | 술어의 `qualifiers` | `vocabulary.<p>.object.qualifiers` + 문장 bind 의 같은 이름 |
| Backing dataset | 소스 `relation` + `read` | `sources.<s>` |
| Object materialization | 등록 원자 (`register@1`, 목적어 없음 — 속성은 그 원자의 qualifiers) | 소스가 속성을 매기면 «암묵 등록» |
| Link materialization | 사실 원자 (주어 → 술어 → 목적어) | 문장 `mappings` |
| Edits layer (사용자 편집) | 표 쪽 `cell_sources` 사용자 층 (원장은 «쓰기 없음») | — |
| Dataset version / Branch / 시간 여행 (표 «전체» 단위) | «없음» — 우리 이력은 «사실 단위»(원자의 occurred_at) (방향 논의 ③④) | — |

## 1. 예시 — 「웨이퍼 마스터 표 + 검사 행 표」 두 표를 원장으로

### 파운드리라면
```
Object type  Wafer   pk wafer_id     properties product, lot      backing dataset wafer_master
Object type  Die     pk (wafer_id, x, y)                          backing dataset inspection_rows
Link type    inspected  Wafer -> Die                              backing dataset inspection_rows
```

### 원장 선언 (`ledger_config.json`) — 같은 것
```json
{
  "setup_version": 1,
  "entities": {
    "wafer@1": { "keys": ["wafer"], "attributes": ["product", "lot"] },
    "die@1":   { "keys": ["wafer", "x", "y"] }
  },
  "vocabulary": {
    "register@1":  { "status": "active", "subjects": ["wafer@1"],
                     "object": { "kind": "none", "qualifiers": { "required": [], "optional": [] } } },
    "inspected@1": { "status": "active", "subjects": ["wafer@1"],
                     "object": { "kind": "entity_ref", "types": ["die@1"],
                                 "qualifiers": { "required": [], "optional": [] } } }
  },
  "sources": {
    "wafer_master": {
      "relation": "wafer_master",
      "read": {
        "unit": "row", "identity": ["wafer_id"], "group_by": [], "order_by": ["wafer_id"],
        "cursor": { "columns": ["wafer_id"] },
        "occurred_at": { "column": "updated_at", "timezone": "Asia/Seoul" }
      },
      "prepare": { "implementation_id": "direct-join", "implementation_version": 1,
                   "input_columns": ["wafer_id", "product_code", "lot_id", "updated_at"],
                   "output_columns": {}, "accepts_verified_join_rules": false, "inherit_virtual_join_rules": [] },
      "map":     { "implementation_id": "declarative-role", "implementation_version": 1, "unit": { "kind": "row" },
                   "input_columns": ["wafer_id", "product_code", "lot_id", "updated_at"] },
      "bind": {
        "entities": {
          "wafer@1": { "attributes": {
            "product": { "kind": "column", "column": "product_code" },
            "lot":     { "kind": "column", "column": "lot_id" } } }
        },
        "mappings": {
          "wafer-registers": {
            "predicate": "register@1",
            "bind": {
              "occurred_at": { "kind": "column", "column": "updated_at" },
              "subject": { "kind": "entity", "entity_type": "wafer@1",
                           "keys": { "wafer": { "kind": "column", "column": "wafer_id" } } }
            }
          }
        }
      }
    },
    "inspection_rows": {
      "relation": "inspection_rows",
      "read": {
        "unit": "row", "identity": ["row_id"], "group_by": [], "order_by": ["row_id"],
        "cursor": { "columns": ["row_id"] },
        "occurred_at": { "column": "inspected_at", "timezone": "Asia/Seoul" }
      },
      "prepare": { "implementation_id": "direct-join", "implementation_version": 1,
                   "input_columns": ["row_id", "wafer_id", "die_x", "die_y", "inspected_at"],
                   "output_columns": {}, "accepts_verified_join_rules": false, "inherit_virtual_join_rules": [] },
      "map":     { "implementation_id": "declarative-role", "implementation_version": 1, "unit": { "kind": "row" },
                   "input_columns": ["row_id", "wafer_id", "die_x", "die_y", "inspected_at"] },
      "bind": {
        "mappings": {
          "wafer-inspected-die": {
            "predicate": "inspected@1",
            "bind": {
              "occurred_at": { "kind": "column", "column": "inspected_at" },
              "subject": { "kind": "entity", "entity_type": "wafer@1",
                           "keys": { "wafer": { "kind": "column", "column": "wafer_id" } } },
              "target":  { "kind": "entity", "entity_type": "die@1",
                           "keys": { "wafer": { "kind": "column", "column": "wafer_id" },
                                     "x":     { "kind": "column", "column": "die_x" },
                                     "y":     { "kind": "column", "column": "die_y" } } }
            }
          }
        }
      }
    }
  }
}
```

### 읽는 법 — 파운드리 사람에게
```
· 「Object type 의 property」는 «엔티티에 이름», «소스에 컬럼» — 두 줄. 문장마다 «안» 적는다(소스당 한 번, 판정 124)
· 「Object 가 materialize 된다」= 그 소스가 register@1 문장을 내거나, 속성을 매긴 것만으로 «암묵 등록»(판정 127·Ⓖ — 타입이 register@1.subjects 에 있어야 함)
· 「Link」는 술어. 링크에 값이 붙으면 술어의 qualifiers 로 — 노드 속성(attributes)과 «다른 것»이다
· «걷기»가 파운드리의 Object set 질의: 씨앗 노드에서 follow(술어)로 걸어 collect(타입)를 가져온다. 노드는 {id, type, keys, attributes}
· 파운드리와 «다른 것»은 append-only 여부가 «아니라» «이력의 단위»다(소유자 정정 09-08 08:3x). 파운드리는 «데이터셋 버전»(트랜잭션마다 새 버전, 시간 여행은 버전으로), 우리는 «사실(원자)» 단위(원자마다 occurred_at · 속성이 바뀌면 새 등록 원자). 표 «전체»의 버전·브랜치는 우리에게 없다(방향 논의 ③④). 걷기는 최신을 보여 주고 충돌 «수»를 낸다
```

## 2. 두 줄 (완성의 정의)
```
「운영에서는 엔티티 선언에 attributes 이름을 적고, 소스의 bind.entities 에서 그 이름에 컬럼을 «한 번» 매기면 됩니다」
⚠️ 소스가 `map.input_columns` 를 «명시»했으면 그 컬럼을 거기에도 — 안 적으면 검증기가 그 경로를 댑니다(빈 목록이면 기본값이 전부라 이 줄이 없음, 큐 S-52-c)
```

## 3. 이 예시가 «안» 보여 주는 것 (일부러)
```
· 그룹 소스(한 이벤트 = 여러 행, `read.unit: "group"` + `group_by`) — 출하 샘플 lot_event 참고
· 준비기가 «산출»하는 컬럼(`prepare.output_columns`) — 출하 샘플 참고
· 검증된 가상 조인(`accepts_verified_join_rules`) — `docs/guide/config/` 의 그 문서
· 그룹 «집계»(`aggregations`) — 🔴 원장 선언의 칸이 «아닙니다». 인리치먼트 규칙의 것이고,
  원장이 그 결과를 쓰려면 그 파이프라인이 «표에 쓴» 컬럼을 보통의 컬럼으로 읽습니다(판정 211).
  칸의 뜻은 `docs/guide/config/enrichment_rules.md`
· 파일 «신원»을 데이터 행에 놓기(수동 메타 표와 잇는 열쇠) — 원장 선언이 아니라 «표 선언»의 `filename_rules`(경로에서 뽑을 값 → 컬럼). 배치 id 는 회(run)의 신원이라 감사 행에 있다(판정 159, 2026-09-08)
```

## 4. 2026-09-09 에 열린 칸 «넷» — 칸마다 «두 줄»

> 넷 다 «선택»이고 기본값이 «적혀» 있습니다(`setup_bundle.py:140~155`). 출하 샘플에 «기본값을 그대로 쓴» 예시가 한 벌 있습니다 — `has_netdie@1` · `defect@1` · 소스 `bonded_from`.
> 🔵 **기본값을 «명시»해도 뜻이 안 바뀝니다** — 이 넷은 「안 적음」과 「기본값을 적음」이 같습니다.
> ⚠️ `class` 는 «다릅니다**: 거기서는 「안 적음」과 「dynamic 이라 적음」을 «구별»하므로 기본값을 쓰지 마십시오(`setup_bundle.py:1112` 주석).

### ① 값의 «타입» — `vocabulary.<술어>.object.value_type`
```
운영에서는 그 술어의 object 에 value_type 을 number · string · boolean · timestamp 중 하나로 적으면 됩니다.
안 적으면 number 입니다.
```
🔵 **넷이 «전부» 됩니다** (S-84 · S-84-b 착지 2026-09-10). 여기 「오늘은 `number` 만」이라 적혀
있었고 그것은 판정 178 시점의 사실이었습니다 — 그때는 문법이 받는 넷과 발행이 지키는 하나가 달랐고,
그 차이를 «이름 대어» 거절하고 있었습니다. 오늘은 두 집합이 같아서 그 거절이 «없습니다».

**`timestamp` 만 줄이 하나 더 붙습니다** — 「이 컬럼의 순진한 표기를 «어느 시간대»로 읽나」는
컬럼이 답할 수 없는 것이라, 값을 매기는 «바인딩»이 답합니다:
```
운영에서는 그 값 역할의 바인딩에 timezone 을 적으면 됩니다  (bind.mappings.<문장>.bind.<값 역할>.timezone)
안 적으면 «거절»입니다 — timestamp 에는 기본 시간대가 없습니다
```
⚠️ 이것은 `sources.<소스>.read.occurred_at.timezone` 과 «다른 칸»입니다. 저쪽은 「그 사건이 언제
일어났나」의 시간대이고, 이쪽은 「이 값이 무엇을 뜻하나」입니다. 하나를 빌려 쓰면 소스의 적재 시각이
값의 뜻을 정하게 됩니다.

### ② 술어의 «개수» — `vocabulary.<술어>.cardinality`
```
운영에서는 그 술어에 cardinality 를 one 또는 many 로 적으면 됩니다.
안 적으면 many 입니다.
```
🔵 **`one` 은 이제 «세 가지 일»을 합니다** (S-133 착지 2026-09-10, 판정 256). 여기 「검사하는 쪽이
없습니다」라고 적혀 있었고, 그것이 오늘 거짓이 됐습니다:
```
① 새 값이 «앞 값을 대체합니다»   원장이 새 원자에 `supersedes` 를 찍습니다 — 옛 원자는 «지워지지 않고»,
                              「이것이 저것을 대신한다」는 포인터가 생깁니다(기록은 안 지웁니다)
② 한 배치가 «둘»을 말하면 거절   같은 주어에 목적어가 둘인 배치는 「어느 것이 현재인지 아무도 말하지 않는다」라
                              그 분자를 «이름 대어» 거절합니다(`cardinality_one_violated`) — 세고 건너뜁니다
③ 걷기가 그 사실을 «싣습니다»     엣지에 `cardinality` 가 실려, 화면이 「그린 것을 보고 짐작」하지 않습니다
```
⚠️ **소급은 «안 합니다»** — 이미 여러 원자가 살아 있는 (주어, `one` 술어)는 «다음 새 원자부터»
대체됩니다. 과거 정리는 재번역(rescope)의 일입니다.
✅ **걷기는 «현재만» 그립니다**(S-141, 2026-09-10 저녁). 대체된 엣지는 빠지고, 몇 개를 뺐는지는
`walk.superseded_dropped` 가 «0 일 때도» 말합니다. 둘 다 보려면 `?include_superseded=true` 이고
그때는 엣지에 `superseded_by` 표지가 붙습니다.
🪦 이 자리에 아침까지 「걷기가 아직 안 지웁니다」라고 적혀 있었습니다 — 같은 날 닫혔습니다.

### ③ 수명 — `entities.<타입>.status` · `sources.<소스>.status`
```
운영에서는 그 엔티티(또는 소스)에 status 를 retired 로 적으면 됩니다.
안 적으면 active 입니다.
```
🔵 **셋이 이제 «같은 효력»입니다** (S-103 착지 2026-09-10). 여기 「읽는 쪽이 없습니다 · 소스를
retired 로 적어도 계속 번역합니다」라고 적혀 있었고, 오늘은 둘 다 거짓입니다:
```
소스 retired   재번역(backfill)이 «이름 대어» 거절하고(`source_retired`), 센서스는 그 소스를
              「retired 라서 건너뜀」이라고 «로그에 이름을 대고» 셈에서 뺍니다 — 조용히 0 이 아닙니다
엔티티 retired  그 타입을 «내는 문장»을 번들 검증이 이름 대어 거절합니다(`_retired_entity_types`)
술어 status    «전부터» 읽혔습니다 — 이제 셋이 한 낱말이고 한 효력입니다
```
⚠️ 원자는 «그대로 남습니다**. `retired` 는 「새로 들어오는 것을 멈춘다」이지 「있던 것을 지운다」가 아닙니다.

### ④ 판단 단위 — 🔴 원장 선언이 아니라 «표 카탈로그»입니다
```
운영에서는 «표 카탈로그»(table_config.json)의 그 표에 decision_key 로 판단 단위 컬럼들을 적으면 됩니다.
기본값은 «없습니다» — 안 적은 표를 business_key 로 대신 읽지 않고, 필요한 자리에서 «이름 대어» 거절합니다.
```
🔵 **자리가 «표»인 이유**: 판단 단위는 그 표의 성질이지 그 표를 읽는 «원장 소스»의 성질이 아닙니다 —
소스가 둘이면 같은 표에 두 번 적게 되고, 그 둘이 «갈릴 수» 있습니다(판정 e578eabc).
⚠️ 그래서 출하 샘플에는 이 칸의 예시를 «안 넣었습니다** — 어느 컬럼이 판단 단위인지는 «도메인 사실»이고, 기본값이 없는 칸에 예시를 넣으면 그것이 기본값처럼 읽힙니다.
