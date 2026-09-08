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
· 파일 «신원»을 데이터 행에 놓기(수동 메타 표와 잇는 열쇠) — 원장 선언이 아니라 «표 선언»의 `filename_rules`(경로에서 뽑을 값 → 컬럼). 배치 id 는 회(run)의 신원이라 감사 행에 있다(판정 159, 2026-09-08)
```
