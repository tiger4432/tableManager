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
| Link a key implies (`Die` in the `Wafer` its `mat_id` names) | 🆕 엔티티의 `references`(10-02 `f45c75442`) | `entities.<t>.references` — `edge`(어휘의 술어) · `to.entity` · `to.keys`(상위 키: 이 엔티티의 키) · `from.when`. 그 엔티티를 부르는 소스마다 번역기가 원자를 쓴다(시각은 사건 시각 아님) |
| Backing dataset | 소스 `relation` + `read` | `sources.<s>` |

> 🆕 **키 값의 철자**(10-01 `7350027a6`) — 엔티티 키는 그 컬럼의 `table_config` 선언 타입으로 접혀서 같은 것이 한 키가 됩니다. `number` 칸이면 `01` · `1` · ` 1 ` · `1.0` 이 모두 `1`(정수가 아닌 수는 그대로 `7.5`), 그 밖의 칸은 앞뒤 공백만 뗍니다. 빈 값은 키가 없는 것입니다. 상수로 적은 키는 공백만 뗍니다. 코드 맵퍼가 스스로 지은 키는 이 접기를 안 지납니다.
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
        "unit": "row", "identity": ["wafer_id"], "order_by": ["wafer_id"],
        "cursor": { "columns": ["wafer_id"] },
        "occurred_at": { "column": "updated_at", "timezone": "Asia/Seoul" }
      },
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
        "unit": "row", "identity": ["row_id"], "order_by": ["row_id"],
        "cursor": { "columns": ["row_id"] },
        "occurred_at": { "column": "inspected_at", "timezone": "Asia/Seoul" }
      },
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
🆕 10-02 `a5fe51b3f` — 그 컬럼을 `map.input_columns` 에 다시 적지 않습니다. 읽기가 저절로 싣고 검증기도 요구하지 않습니다(전에는 「Profile column … is missing」)
```

## 3. 이 예시가 «안» 보여 주는 것 (일부러)
```
· 그룹 소스(한 이벤트 = 여러 행, `read.unit: "group"` + `group_by`) — 출하 예제 transfer_explorer 의 dt_log 참고
  row 소스는 `group_by` 를 적지 않습니다 — 폼도 안 그립니다. 옛 파일의 `"group_by": []` 는 그대로 읽히고 저장 때 빠집니다(10-01 `c83fe086a`)
· 계산된 컬럼 — 원장 선언에 «적을 자리가 없습니다». 체인이 표에 쓴 컬럼을 보통의 컬럼으로 읽습니다
  (⚰️ `prepare` 절은 setup_version 6 에서 은퇴 — ONTOLOGY_LEDGER_SETUP §7.3)
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
🔵 **`one` 이면 걷기가 «지금 것»만 그립니다** (총괄 22ebdd153, 10-01 — 판정 256 뒤집음):
```
지금 것      같은 주어의 그 술어 중 occurred_at 이 가장 늦은 사실. 늦게 «도착한» 옛 사실은 지금 것이 아닙니다
시각 지정    ?until= 이면 그 시각 전에서 가장 늦은 것
옛 것 보기   ?include_superseded=true — 옛 사실도 그리되 엣지에 not_current
동시각 둘    둘 다 지금 것으로 그리고, 주어 노드의 current_conflicts 가 셉니다
엣지         cardinality 를 싣습니다 — 화면이 「그린 것을 보고 짐작」하지 않습니다
```
⚰️ 09-10 의 「한 배치의 목적어 둘 거절 · 나중 도착에 `supersedes` 찍기 · `walk.superseded_dropped`」는
한 번도 운영에서 안 돌았고(`918f49ccc`) 은퇴했습니다. 쓰기에서 `one` 은 아무것도 안 합니다 — 소급도 없습니다.

### ③ 수명 — `entities.<타입>.status` · `sources.<소스>.status`
```
운영에서는 그 엔티티(또는 소스)에 status 를 retired 로 적으면 됩니다.
안 적으면 active 입니다.
```
🔵 **셋이 이제 «같은 효력»입니다** (S-103 착지 2026-09-10). 여기 「읽는 쪽이 없습니다 · 소스를
retired 로 적어도 계속 번역합니다」라고 적혀 있었고, 오늘은 둘 다 거짓입니다:
```
소스 retired   그 소스의 «내용을 안 읽습니다» — 검증 · 교차 컬럼 검사 · 컴파일 레지스트리 · 계획,
              «네 패스»가 전부 `is_retired()` 라는 «한 철자»에서 멈춥니다(S-177 ①).
              🔵 그래서 **깨진 소스를 그대로 은퇴시켜도 원장이 돕니다** — 이것이 이 칸의 요점입니다
              그리고 재번역은 `source_retired` 로 «이름 대어» 거절하고, 센서스는 「retired 라서 건너뜀」을
              «로그에 이름 대고» 셈에서 뺍니다 — 조용히 0 이 아닙니다
엔티티 retired  그 타입을 «내는 문장»을 번들 검증이 이름 대어 거절합니다(`_retired_entity_types`)
술어 status    «전부터» 읽혔습니다 — 이제 셋이 한 낱말이고 한 효력입니다
```
⚰️ **[09-11 16:1x 정정] 오늘 아침까지 이 자리는 «반쪽»이었습니다.** 위 두 독자(재번역·센서스)는
그때도 참이었지만, **번들 검증이 `status` 를 읽고도 그 소스의 내용을 «그대로 검사»했습니다** —
그래서 「못 읽는 선언을 retired 로 끄려던」 운영자가 번들 «전체»를 거절당하고 원장이 섰습니다(S-177).
🔴 즉 「끄는 방법」을 적어 둔 이 두 줄이, 정작 «끄고 싶은 이유»(선언이 깨짐)에서는 안 통했습니다.
   S-177 ① 로 네 패스가 «한 철자»를 보게 되면서 오늘 참이 됐습니다.

🔵 **그리고 «끄지 않아도» 됩니다 — 깨진 소스는 혼자 떨어집니다**(S-177 ②③, 같은 날 저녁):
```
운영에서는 아무것도 안 적어도 됩니다 — 선언 하나가 깨지면 «그것만» 계획에서 빠지고
로더가 「어느 것이 · 어느 경로에서 · 왜」를 말합니다. 나머지 소스는 그대로 돕니다
```
⚠️ 그러니 `retired` 는 「깨져서 끄는」 칸이 아니라 「더 안 읽겠다고 «말하는»」 칸입니다 —
   둘이 같은 날 갈렸습니다.
⚠️ 원자는 «그대로 남습니다**. `retired` 는 「새로 들어오는 것을 멈춘다」이지 「있던 것을 지운다」가 아닙니다.

### ④ 판단 단위 — 🔴 원장 선언이 아니라 «표 카탈로그»입니다
```
운영에서는 «표 카탈로그»(table_config.json)의 그 표에 decision_key 로 판단 단위 컬럼들을 적으면 됩니다.
기본값은 «없습니다» — 안 적은 표를 business_key 로 대신 읽지 않고, 필요한 자리에서 «이름 대어» 거절합니다.
```
🔵 **자리가 «표»인 이유**: 판단 단위는 그 표의 성질이지 그 표를 읽는 «원장 소스»의 성질이 아닙니다 —
소스가 둘이면 같은 표에 두 번 적게 되고, 그 둘이 «갈릴 수» 있습니다(판정 e578eabc).
⚠️ 그래서 출하 샘플에는 이 칸의 예시를 «안 넣었습니다** — 어느 컬럼이 판단 단위인지는 «도메인 사실»이고, 기본값이 없는 칸에 예시를 넣으면 그것이 기본값처럼 읽힙니다.

### ⑤ 문장 고르기 — `sources.<소스>.bind.mappings.<문장>.when` (S-99 · 🆕 09-30 `c1746aa1e` 에 넓어짐)
```
운영에서는 소스의 `bind.mappings.<문장>` 에 `when: {컬럼: 값}` 을 적으면 됩니다.
그 칸 값이 맞는 행만 그 문장을 말합니다 — 한 표가 값에 따라 «다른 주어»로 말하게 할 때 씁니다.
```
출하 샘플 `wafer_process_recipe` 가 그 모양입니다 — 같은 술어 `processed_with@1` 을 문장 «둘»로 적고 주어만 가릅니다:
```json
"wafer-processed-with-recipe":   { "predicate": "processed_with@1", "when": {"mat_type": ""},   "bind": { "subject": { "entity_type": "wafer@1",   ... } } },
"dtwafer-processed-with-recipe": { "predicate": "processed_with@1", "when": {"mat_type": "DT"}, "bind": { "subject": { "entity_type": "dtwafer@1", ... } } }
```
`mat_type` 은 체인 조인이 단계 표(`step_phase` — DT 단계만 적음)에서 채웁니다. 조인이 안 닿은 행은 빈 값이라 전처럼 `wafer@1` 로 말합니다.
- **빈 칸은 `""` 입니다** — 값이 없는(NULL) 칸은 `""` 로 견줍니다(09-30 전엔 `"nan"` 이 돼 어느 문장도 안 맞았다). 견줄 때 칸 값과 적은 값을 «둘 다» 같은 글자로 접습니다 — 앞뒤 공백을 떼고, `7.0` 같은 정수 실수는 `"7"`(10-01 `0ba4c82ce`, `clean_str_value`).
- **어느 문장도 안 고른 행은 «세고 이름 댑니다»** — 모든 문장이 `when` 을 들고 그 어느 것도 안 맞으면 그 행은 아무것도 말하지 않고, 값마다 세어 하트비트 노트에 실립니다(`units no sentence said: units=N | <소스>:mat_type='WF'=N`). 한 값이 1 · 10 · 100 … 단위에 닿을 때 한 줄(10-01 d4a949a8c ⑧):
  `[Ledger] Next: correct the value in the table it comes from, or declare a sentence whose when names it. <소스>: mat_type='WF' said no sentence - every sentence's when passed it over | units so far in this process: N`
  미리보기와 배치 영수증에도 `unsaid` 로 실립니다. `when` 없는 문장이 하나라도 있으면 모든 행이 그것을 말하므로 이 줄은 안 납니다.
