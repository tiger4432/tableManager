# Ledger V2 설정 작성 가이드

> **Status:** 🟢 Living
> **Last-verified:** 2026-08-18
> **Owner:** Server / Ledger
> **정본 구현:** `server/ledger/setup_bundle.py`, `setup_registry.py`, `cutover_v2.py`
> **운영 선언 루트:** `server/config/ontology/`

이 문서는 새 원천 테이블을 Ledger V2에 연결할 때 **어떤 JSON을 어떤 순서로 작성하고,
각 필드가 왜 필요한지** 설명하는 단일 설정 가이드다. 구형
`server/config/ledger_config.json`, translator 종류, `declared_lookup`, Position/Frame,
마이그레이션·cursor reset 중심의 옛 설정 절차는 이 문서의 대상이 아니다.

설정은 DB 테이블을 만들지 않고, 데이터를 쓰지 않으며, Python 구현을 config 문자열로
불러오지 않는다. 물리 테이블과 인제션이 먼저 존재해야 한다. 설정은 그 데이터를 어떻게
읽고 의미로 바꿀지를 선언한다.

---

## 1. 먼저 이해할 전체 흐름

```text
server/config/ontology/manifest.json
  ├─ ledger_config.json
  │    ├─ vocabulary      낼 수 있는 술어와 목적어 모양
  │    ├─ entities        개체의 정체성과 키
  │    ├─ source_preparers 물리 행 → EventFrame
  │    ├─ mappers         EventFrame → RoleEmission
  │    ├─ packs           Role → Claim/LedgerFrame
  │    ├─ profiles        소스 컬럼 → Pack Role binding
  │    └─ sources         위 선언을 한 실행 단위로 조립
  ├─ catalog/tables.json          물리 relation/column/key
  ├─ catalog/virtual_joins.json   물리 UNIQUE로 검증할 batch join
  ├─ dataflows/chains.json        source별 legacy/V2 cutover 선택
  └─ dataflows/enrichments.json   예약된 enrichment 선언 영역

strict Bundle validation
  → trusted implementation 대조
  → immutable Registry/Snapshot
  → cursor physical batch
  → Preparer + verified batch join
  → pandas EventFrame
  → Mapper RoleEmission
  → Pack compiler LedgerFrame
  → 기존 gate → LedgerStore → cursor transaction
```

핵심은 세 층을 분리하는 것이다.

| 층 | 질문 | 소유 파일 |
|---|---|---|
| 물리 | 어느 테이블의 어느 컬럼을 어떤 키로 읽나? | `catalog/*.json`, `sources` |
| 의미 | 무엇을 개체·관계·시각으로 말하나? | `vocabulary`, `entities`, `packs`, `profiles` |
| 실행 | 누가 행을 준비하고 Role로 해석하며 어느 경로를 켜나? | `source_preparers`, `mappers`, `chains` |

`Profile`은 Pack이 아니다. Pack은 재사용 가능한 Claim 문법이고, Profile은 특정 Source의
컬럼을 그 문법의 Role에 연결하는 배선이다.

---

## 2. 실제 파일 위치와 복사 가능한 기준 샘플

### 2.1 현재 승인된 `lot_event` 운영 샘플

다음 여섯 파일이 현재 production authoring root다. 새 설정을 만들 때 가장 먼저 이 구조를
복사한다.

```text
server/config/ontology/
├─ manifest.json
├─ ledger_config.json
├─ catalog/
│  ├─ tables.json
│  └─ virtual_joins.json
└─ dataflows/
   ├─ chains.json
   └─ enrichments.json
```

이 파일들은 예시 사본이 아니라 현재 운영 정본이다. 수정 전에는 별도 작업 브랜치에서
전체 Bundle 검증과 preview를 먼저 수행한다.

### 2.2 이종 transfer와 virtual join 샘플

```text
server/config/sample/ontology/transfer_explorer/
```

이 샘플은 다음을 보여준다.

- `dt_log`를 cursor가 읽는다.
- Preparer가 `dt_job_id`를 키로 `dt_inventory`를 batch join한다.
- `CoreDie@1 → DTDie@1 → BondComponent@1 → FinalChip@1` 연속 계보를 선언한다.
- 오른쪽 relation의 `dt_job_id`는 business key와 UNIQUE index로 단일성을 증명한다.

주의: 이 샘플의 Preparer/Mapper 구현 ID는 Explorer와 테스트용이다. 파일을 production
폴더에 복사하는 것만으로 trusted implementation이 생기지 않는다. 운영 실행을 하려면
코드의 trusted catalog와 Preparer/Mapper registry에 같은 `implementation_id@version`이
명시적으로 등록돼 있어야 한다.

---

## 3. 작성 전 준비 사항

설정을 열기 전에 아래 질문에 답한다.

1. **물리 relation은 이미 존재하는가?** `tables.json`은 DDL이 아니다.
2. **한 source event는 한 행인가, 여러 행의 group인가?**
3. **세계 시각 컬럼은 무엇이며 timezone은 무엇인가?** 묵시적 기본 timezone은 없다.
4. **cursor 동률을 제거할 catalog-declared UNIQUE key는 무엇인가?**
5. **Preparer 출력만으로 신원이 완성되는가?** 아니면 verified virtual join이 필요한가?
6. **기존 trusted Preparer/Mapper를 재사용할 수 있는가?**
7. **기존 Vocabulary/Entity/Pack으로 말할 수 있는가?** 새 의미가 아니면 중복 선언하지 않는다.
8. **legacy 결과와 parity를 비교할 수 있는가?** 설명 없는 차이 0이 되기 전 `chains`를 V2
   approved로 바꾸지 않는다.

### row와 group 선택

| 원천 모양 | `source.driver.unit` | `group_by` | 예 |
|---|---|---|---|
| 한 행이 독립된 source event | `row` | 반드시 `[]` | 한 행당 측정 1건 |
| 여러 행이 한 source event를 이룸 | `group` | 1개 이상 | split/merge 한 거래의 여러 wafer 행 |

group일 때 `group_by`는 `identity`의 부분집합이어야 한다. `identity`와 `group_by`에는
Preparer가 만든 EventFrame 컬럼을 쓸 수 있지만, `order_by`, `cursor`, `occurred_at`은 base
physical relation 컬럼이어야 한다.

---

## 4. `manifest.json` — 파일 묶음의 유일한 진입점

현재 운영 파일을 그대로 옮기면 다음과 같다.

```json
{
  "setup_version": 2,
  "ledger": "ledger_config.json",
  "catalog": {
    "tables": "catalog/tables.json",
    "virtual_joins": "catalog/virtual_joins.json"
  },
  "dataflows": {
    "chains": "dataflows/chains.json",
    "enrichments": "dataflows/enrichments.json"
  }
}
```

| 필드 | 필수 | 값/용도 |
|---|---:|---|
| `setup_version` | 예 | 현재 정확히 `2`. 다른 버전은 거절한다. |
| `ledger` | 예 | Vocabulary부터 Source까지 담은 파일의 상대 경로 |
| `catalog.tables` | 예 | 물리 relation catalog 상대 경로 |
| `catalog.virtual_joins` | 예 | verified join 후보 선언 상대 경로 |
| `dataflows.chains` | 예 | source별 실행 모드 selector 상대 경로 |
| `dataflows.enrichments` | 예 | enrichment 선언 상대 경로 |

경로는 manifest가 있는 root 아래의 상대 경로만 허용한다. 절대 경로, `..` 탈출, glob,
동일 파일 중복 참조는 거절된다. manifest에 없는 일곱 번째 설정 파일은 로더가 알아서
발견하지 않는다.

---

## 5. `catalog/tables.json` — 물리 스키마와 유일성 근거

현재 `lot_event` 샘플 전체다.

```json
{
  "schema_version": 1,
  "tables": {
    "lot_event": {
      "columns": {
        "lot_id": "string",
        "event_time": "datetime",
        "txn_seq": "string",
        "event_type": "string",
        "parent_lot": "string",
        "child_lot": "string",
        "slotnumbers": "string",
        "waferids": "string"
      },
      "business_key": "txn_seq"
    }
  }
}
```

### 5.1 파일 필드

| 필드 | 필수 | 설명 |
|---|---:|---|
| `schema_version` | 예 | 현재 정확히 `1` |
| `tables` | 예 | relation 이름 → descriptor. 한 개 이상이어야 한다. |

### 5.2 table descriptor

| 필드 | 필수 | 설명 |
|---|---:|---|
| `columns` | 예 | 물리 컬럼명 → 비어 있지 않은 타입 문자열 |
| `business_key` | 아니오 | 한 컬럼 또는 컬럼 배열로 표현한 업무상 유일 키 |
| `composite_key` | 아니오 | 여러 컬럼을 합친 유일 키 |
| `indexes` | 아니오 | 물리 index 선언 목록. `name`, `columns`, `unique` 사용 |

예를 들어 두 컬럼 전체가 유일성 근거라면 다음처럼 쓴다.

```json
{
  "schema_version": 1,
  "tables": {
    "measurement_log": {
      "columns": {
        "event_at": "datetime",
        "machine_id": "string",
        "sequence_no": "number",
        "value": "number"
      },
      "composite_key": ["machine_id", "sequence_no"],
      "indexes": [
        {
          "name": "uq_measurement_machine_sequence",
          "columns": ["machine_id", "sequence_no"],
          "unique": true
        },
        {
          "name": "ix_measurement_event_at",
          "columns": ["event_at"],
          "unique": false
        }
      ]
    }
  }
}
```

`business_key`, `composite_key`, 또는 `unique: true` index의 **전체 컬럼 집합**만 cursor
전순서의 증거가 된다. 컬럼이 존재한다는 사실, `identity`, `group_by`, 비-unique index는
유일성 증거가 아니다. 예를 들어 `event_at`만으로 정렬하면 같은 시각의 두 행 순서가
불안정하므로 `invalid_cursor`다. 위 예시는 `machine_id`와 `sequence_no`를 모두 포함해야
동률이 제거된다.

Catalog 선언은 물리 DB를 만들거나 UNIQUE index를 생성하지 않는다. 실제 DB 구조가 별도로
존재해야 하며, virtual join의 경우 physical verifier가 그 UNIQUE index를 직접 확인한다.

---

## 6. `catalog/virtual_joins.json` — verified read-only batch join

join이 없는 현재 production 파일은 다음처럼 빈 registry다.

```json
{
  "schema_version": 1,
  "rules": {}
}
```

`transfer_explorer`의 실제 join 샘플은 다음과 같다.

```json
{
  "schema_version": 1,
  "rules": {
    "dt_job_to_inventory": {
      "left_table": "dt_log",
      "right_table": "dt_inventory",
      "join_key": [
        {"left": "dt_job_id", "right": "dt_job_id"}
      ],
      "expose": [
        "dt_lot",
        "dt_slot",
        "dt_offset_x",
        "dt_offset_y",
        "bond_wafer",
        "bond_offset_x",
        "bond_offset_y",
        "bond_layer",
        "final_chip"
      ],
      "join_cardinality": "one",
      "enabled": true
    }
  }
}
```

| 필드 | 필수 | 설명 |
|---|---:|---|
| rule ID | 예 | 예: `dt_job_to_inventory`. Source가 상속할 이름 |
| `left_table` | 예 | cursor가 읽는 base relation |
| `right_table` | 예 | read-only batch 조회할 relation |
| `join_key` | 예 | 1개 이상의 `{left, right}` 쌍 |
| `expose` | 예 | 오른쪽에서 EventFrame에 노출할 컬럼 목록 |
| `join_cardinality` | 예 | 현재 정확히 `"one"` |
| `enabled` | 예 | `true`인 rule만 상속 가능 |
| `fold` | 아니오 | 제한된 표기 정규화 선언. 임의 식/SQL/Python이 아니다. |

### 6.1 join이 승인되려면

1. 왼쪽·오른쪽 relation과 모든 컬럼이 `tables.json`에 존재해야 한다.
2. 오른쪽 `join_key.right` 전체를 정확히 덮는 catalog 유일 키 또는 UNIQUE index가 있어야
   한다.
3. 실제 PostgreSQL의 해당 UNIQUE index를 physical verifier가 확인해야 한다.
4. Preparer의 `input_columns`가 모든 `join_key.left`를 포함해야 한다.
5. Preparer가 `accepts_verified_join_rules: true`여야 한다.
6. Source의 `inherit_virtual_join_rules`에 rule ID를 명시해야 한다.

config의 `unique: true`만으로 `VerifiedJoinDescriptor`를 만들 수 없다. descriptor의 유일한
정상 발급 경로는 physical verifier 성공 결과다. raw mapping이나 임의 index 이름을 직접
주입하는 production API는 봉인돼 있다.

### 6.2 실행 의미

- 키를 모아 기본 1,000개 단위 read-only batch query를 수행한다.
- 0건은 `missing`, 2건 이상은 `ambiguous`로 mapper 전에 거절한다.
- 필요한 expose 값이 비면 `incomplete`로 거절한다.
- EventFrame에 이미 존재하는 이름과 expose가 충돌하면 조용히 덮지 않고 거절한다.
- V2 Source Preparer에서는 기존 일반 UI virtual join의 “빈 값만 채우기” 규칙을 재사용하지
  않는다. V2는 collision 자체를 구성 오류로 본다.
- N+1 query를 허용하지 않는다.

`fold`를 쓸 때는 현재 verifier가 지원하는 닫힌 표기만 사용한다. 현재 구현되지 않은
`zero_pad`나 임의 `sql`, `python`, `expression`을 선언하면 거절된다.

---

## 7. `ledger_config.json` — 의미와 실행 조립

최상위 모양은 다음과 같다.

```json
{
  "schema_version": 2,
  "vocabulary": {},
  "entities": {},
  "source_preparers": {},
  "mappers": {},
  "packs": {},
  "profiles": {},
  "sources": {}
}
```

일곱 registry는 사용 여부와 관계없이 전수 검증된다. “아직 Source가 선택하지 않은 Profile”도
unknown Entity/column을 숨길 수 없다. 모든 오류는 `code`, 정확한 JSON `path`, `message`로
돌아오며 여러 오류의 순서도 결정적이다.

### 7.1 `vocabulary` — 술어의 닫힌 서명

현재 `lot_event`가 쓰는 실제 Vocabulary다.

```json
{
  "register@1": {
    "status": "active",
    "layer": "ontology",
    "subjects": ["Lot@1", "Wafer@1"],
    "object": {
      "kind": "none",
      "qualifiers": {"required": [], "optional": []}
    }
  },
  "has_wafer@1": {
    "status": "active",
    "layer": "ontology",
    "subjects": ["Lot@1"],
    "object": {
      "kind": "entity_ref",
      "types": ["Wafer@1"],
      "qualifiers": {"required": ["slot"], "optional": []}
    }
  },
  "derived_from@1": {
    "status": "active",
    "layer": "ontology",
    "subjects": ["Lot@1"],
    "object": {
      "kind": "entity_ref",
      "types": ["Lot@1"],
      "qualifiers": {"required": [], "optional": []}
    }
  },
  "slot_map@1": {
    "status": "active",
    "layer": "ontology",
    "subjects": ["Lot@1"],
    "object": {
      "kind": "entity_ref",
      "types": ["Lot@1"],
      "qualifiers": {
        "required": ["from", "to", "wafer"],
        "optional": []
      }
    }
  }
}
```

위 블록은 `ledger_config.json`의 `vocabulary` 값만 발췌한 **section fragment**다.

| 필드 | 허용값/용도 |
|---|---|
| Vocabulary ID | 반드시 versioned ID, 예: `has_wafer@1` |
| `status` | `active` 또는 `retired` |
| `layer` | 의미 층 이름. 현재 예시는 `ontology` |
| `subjects` | 허용되는 versioned Entity ID 목록 |
| `object.kind` | `none`, `entity_ref`, `value`, `event_ref` |
| `object.types` | `entity_ref`일 때 허용되는 Entity ID 목록 |
| `object.qualifiers.required` | Pack이 반드시 공급해야 하는 qualifier 이름 |
| `object.qualifiers.optional` | Pack이 선택적으로 공급할 수 있는 qualifier 이름 |

required와 optional은 겹칠 수 없다. `object.kind: "none"`에는 qualifier나 type을 붙일 수
없다. Pack이 `slot_map@1`을 emit하면서 `from`, `to`, `wafer` 중 하나를 빠뜨리면
`missing_required_payload`, 선언하지 않은 `layer` 같은 값을 추가하면
`unknown_payload_field`로 거절한다.

Vocabulary는 “어떤 문장이 문법적으로 가능한가”를 정한다. 실제 source 컬럼은 여기에 쓰지
않는다.

### 7.2 `entities` — 개체 ID와 key shape

현재 실제 선언은 다음과 같다.

```json
{
  "Lot@1": {"keys": ["lot"]},
  "Wafer@1": {"keys": ["wafer"]}
}
```

이 역시 `entities` section fragment다.

| 필드 | 필수 | 설명 |
|---|---:|---|
| Entity ID | 예 | versioned ID, 예: `Lot@1` |
| `keys` | 예 | 개체를 식별하는 논리 key 이름. 비어 있거나 중복될 수 없다. |
| `key_types` | 아니오 | key 이름 → trimmed nonblank type 문자열. 키 집합은 `keys`와 정확히 같아야 한다. |
| `allow_null` | 아니오 | 명시적 boolean. 생략 시 null key를 허용하는 것으로 추측하지 않는다. |

여기서 `lot`은 논리 key 이름이지 반드시 물리 컬럼명일 필요는 없다. Profile A는 `lot_id`,
Profile B는 `batch_name`을 같은 `Lot@1.keys.lot`에 binding할 수 있다. 이것이 source 이름과
column 이름이 바뀌어도 Pack을 재사용할 수 있는 이유다.

복합 개체 예시는 다음과 같다.

```json
{
  "Die@1": {
    "keys": ["wafer", "x", "y"],
    "key_types": {
      "wafer": "string",
      "x": "number",
      "y": "number"
    },
    "allow_null": false
  }
}
```

`key_types.x`에 객체, 배열, null, bool, 숫자 자체, blank 문자열을 넣으면 구조화된 오류로
거절한다. 닫힌 type enum은 현재 계약에 없으므로 임의 enum을 발명하지 않는다.

### 7.3 `source_preparers` — 물리 batch를 EventFrame으로 준비

현재 `lot_event` Preparer descriptor 전체다.

```json
{
  "lot-event-live-frame@1": {
    "implementation_id": "lot-event-live-frame",
    "implementation_version": 1,
    "input_columns": [
      "lot_id",
      "event_type",
      "slotnumbers",
      "waferids",
      "parent_lot",
      "child_lot",
      "txn_seq",
      "event_time"
    ],
    "output_columns": {
      "lot": "string",
      "slots": "string",
      "wafers": "string",
      "row_identity": "string",
      "event_group_key": "string",
      "__source_event_incomplete": "boolean"
    },
    "accepts_verified_join_rules": false
  }
}
```

| 필드 | 설명 |
|---|---|
| Preparer ID | versioned registry ID. 예: `lot-event-live-frame@1` |
| `implementation_id` | trusted code catalog에서 찾을 구현 이름 |
| `implementation_version` | 구현 계약 버전. ID의 `@1`과 별개로 명시한다. |
| `input_columns` | base physical SELECT와 join left key로 필요한 컬럼 전수 |
| `output_columns` | Mapper가 받을 EventFrame 컬럼명 → 타입 문자열 |
| `accepts_verified_join_rules` | physical verification을 통과한 join descriptor 수용 여부 |

Preparer는 source별 정규화·그룹 조립·virtual join 적용·결측 판정을 담당한다. Pack이나
LedgerFrame을 만들지 않는다.

입력과 출력 이름은 충돌할 수 없다. 출력은 base physical catalog 컬럼과도 충돌할 수 없다.
join을 상속하면서 left key가 `input_columns`에 없거나 `accepts_verified_join_rules`가 false면
실행 불가능한 sealed plan이 되지 않도록 compile 전에 거절한다.

Config는 Python module/function/path를 지정할 수 없다. 다음은 금지다.

```json
{
  "implementation_id": "my.module:prepare",
  "python": "lambda row: row",
  "sql": "SELECT * FROM secret"
}
```

새로운 실행 모양이 필요하면 `BaseSourcePreparer` 구현을 코드로 추가하고 trusted catalog와
sealed registry에 명시적으로 등록한 뒤 그 ID를 config에서 선택한다.

### 7.4 `mappers` — EventFrame에서 Role만 해석

현재 mapper descriptor 전체다.

```json
{
  "lot-event-role@1": {
    "implementation_id": "lot-event-role",
    "implementation_version": 1,
    "unit": {"kind": "event"},
    "input_columns": [
      "lot",
      "event_type",
      "slots",
      "wafers",
      "parent_lot",
      "child_lot",
      "row_identity",
      "event_time",
      "event_group_key",
      "__source_event_incomplete"
    ],
    "emits": [
      "lot-lineage@1/register_lot",
      "lot-lineage@1/register_wafer",
      "lot-lineage@1/membership",
      "lot-lineage@1/lineage",
      "lot-lineage@1/split_slot",
      "lot-lineage@1/merge_slot"
    ]
  }
}
```

| 필드 | 설명 |
|---|---|
| Mapper ID | versioned registry ID |
| `implementation_id/version` | trusted mapper 코드 선택 |
| `unit.kind` | `event`, `row`, `group_by` 중 하나 |
| `unit.columns` | `group_by` mapper에서만 필요한 grouping columns |
| `input_columns` | Preparer가 만든 EventFrame에서 mapper가 읽을 컬럼 전수 |
| `emits` | 이 mapper가 낼 수 있는 `Pack@version/claim_id` 전수 |

Mapper는 Atom, predicate payload, Ledger 7컬럼을 직접 만들지 않는다. 공통
`BaseLedgerMapper.map()` 경계를 통해 `RoleEmission`만 반환한다. subject/object/time/qualifier
shape는 Pack compiler가 소유한다.

`emits`는 단순 설명이 아니다. Profile `mappings[].use`와 양방향으로 대조된다. Mapper가
말한 Claim을 Profile이 전혀 매핑하지 않거나, Profile이 Mapper의 emits 밖 Claim을 사용하면
compile이 실패한다.

### 7.5 `packs` — Role을 Vocabulary Claim으로 만드는 문법

아래는 가장 단순한 register Claim의 실제 section fragment다.

```json
{
  "lot-lineage@1": {
    "claims": {
      "register_lot": {
        "roles": {
          "subject": {"kind": "entity", "required": true},
          "occurred_at": {"kind": "time", "required": true}
        },
        "emit": {
          "predicate": "register@1",
          "subject": "$subject",
          "object": {"kind": "none"},
          "occurred_at": "$occurred_at"
        }
      }
    }
  }
}
```

qualifier가 있는 실제 `membership` Claim은 다음과 같다.

```json
{
  "membership": {
    "roles": {
      "subject": {"kind": "entity", "required": true},
      "target": {"kind": "entity", "required": true},
      "occurred_at": {"kind": "time", "required": true},
      "slot": {"kind": "attribute", "required": true}
    },
    "emit": {
      "predicate": "has_wafer@1",
      "subject": "$subject",
      "object": {
        "kind": "entity_ref",
        "entity": "$target",
        "qualifiers": {"slot": "$slot"}
      },
      "occurred_at": "$occurred_at"
    }
  }
}
```

구조는 `PackRegistry → PackDescriptor → ClaimDescriptor → RoleDescriptor`다.

| 항목 | 용도 |
|---|---|
| Pack ID | 재사용 가능한 도메인 문법 버전. 예: `lot-lineage@1` |
| Claim ID | Pack 내부 동작 이름. 예: `membership` |
| `roles.<id>.kind` | `entity`, `time`, `quantity`, `identity`, `order`, `attribute`, `symbolic` |
| `roles.<id>.required` | Profile binding과 runtime emission에서 필수인지 |
| `allowed_binding_kinds` | 이 Role에 허용할 `column`, `constant`, `entity` 제한 |
| `allowed_values` | `symbolic` Role의 닫힌 상수 목록 |
| `emit.predicate` | Vocabulary ID |
| `emit.subject/object/occurred_at` | Role을 LedgerFrame 의미 위치에 배치하는 선언 |

기본 허용 binding은 entity Role에는 `entity`, 나머지 Role에는 `column`과 `constant`다.
필요하면 `allowed_binding_kinds`로 더 좁힌다. `symbolic` Role은 정렬된
`allowed_values`가 필수이며 목록 밖 constant를 `invalid_symbolic_constant`로 거절한다.

`RoleDescriptor.kind`는 장식이 아니다. Pack compile은 subject/object/time/qualifier에
실재하는 Role이 연결됐는지, 그 Role kind가 위치에 맞는지, Vocabulary의 subject/entity
type과 qualifier 필드가 닫힌 서명에 맞는지를 전수 대조한다.

### 7.6 `profiles` — 특정 Source 컬럼을 Pack Role에 binding

아래는 현재 `first_sight_lot` mapping 전체다.

```json
{
  "lot-event@1": {
    "source": "lot_event",
    "packs": ["lot-lineage@1"],
    "mappings": [
      {
        "mapping_id": "first_sight_lot",
        "use": "lot-lineage@1/register_lot",
        "bind": {
          "subject": {
            "kind": "entity",
            "entity_type": "Lot@1",
            "keys": {
              "lot": {
                "kind": "column",
                "column": "lot",
                "binding_origin": "user_declared",
                "approval_status": "approved"
              }
            },
            "binding_origin": "user_declared",
            "approval_status": "approved"
          },
          "occurred_at": {
            "kind": "column",
            "column": "event_time",
            "binding_origin": "user_declared",
            "approval_status": "approved"
          }
        }
      }
    ]
  }
}
```

이 블록은 Profile 문법 설명을 위한 section fragment다. 실제 `lot-event@1`에는 여섯 mapping이
있고, 전체 파일은 `server/config/ontology/ledger_config.json`이 정본이다.

| Profile 필드 | 설명 |
|---|---|
| Profile ID | versioned ID. 예: `lot-event@1` |
| `source` | 이 Profile이 해석할 `sources` key |
| `packs` | Profile이 사용할 Pack ID의 닫힌 목록 |
| `mappings` | source EventFrame → Claim Role 배선 목록 |
| `mapping_id` | Profile 안에서 필수·비공백·유일 |
| `use` | 정확한 `Pack@version/claim_id` |
| `bind` | Claim이 선언한 Role 이름 → binding |

`mappings`는 비어 있을 수 없다. `packs`에 적은 Pack은 적어도 한 mapping의 `use`에서 실제로
사용해야 하며, `packs`에 없는 Pack을 mapping이 몰래 사용할 수도 없다.

#### binding 종류

V2 canonical Profile의 binding은 다음 세 가지뿐이다.

**column** — EventFrame의 컬럼 값을 쓴다.

```json
{
  "kind": "column",
  "column": "event_time",
  "binding_origin": "user_declared",
  "approval_status": "approved"
}
```

**constant** — config에 명시한 결정적 JSON 값을 쓴다.

```json
{
  "kind": "constant",
  "value": "track_in",
  "binding_origin": "user_declared",
  "approval_status": "approved"
}
```

constant는 임의 문자열을 무조건 통과시키지 않는다. symbolic Role이면 Pack의
`allowed_values`에 등록된 값이어야 한다. null 허용 여부도 Role/Claim 계약을 따른다.

**entity** — Entity type과 그 논리 key 각각을 nested column/constant로 조립한다.

```json
{
  "kind": "entity",
  "entity_type": "Die@1",
  "keys": {
    "wafer": {
      "kind": "column",
      "column": "core_wafer",
      "binding_origin": "user_declared",
      "approval_status": "approved"
    },
    "x": {
      "kind": "column",
      "column": "core_x",
      "binding_origin": "user_declared",
      "approval_status": "approved"
    },
    "y": {
      "kind": "column",
      "column": "core_y",
      "binding_origin": "user_declared",
      "approval_status": "approved"
    }
  },
  "binding_origin": "user_declared",
  "approval_status": "approved"
}
```

Entity key 집합은 Entity descriptor의 `keys`와 정확히 같아야 한다. nested key binding도
각자 승인 metadata를 가져야 한다.

`declared_lookup`, Position, Frame, SQL/Python/JavaScript expression은 canonical V2 binding이
아니다. 외부 값을 붙여야 하면 Source Preparer의 verified batch join으로 EventFrame column을
만든 뒤 `column` binding을 쓴다.

#### binding 승인 metadata

모든 binding에는 두 필드가 보존된다.

| 필드 | 허용값 | 의미 |
|---|---|---|
| `binding_origin` | `user_declared`, `system_suggested`, `imported` | 이 Mapping 설정이 어디서 왔나 |
| `approval_status` | `pending`, `approved`, `rejected` | 이 Mapping 설정을 실행해도 되는가 |
| `suggestion_reason` | 문자열 | `system_suggested`일 때 필수인 추천 근거 |

이 metadata는 canonical 정규화 Profile에 결정적으로 보존된다. Mapping이 사람이 승인됐다는
사실은 **컬럼 배선 승인**일 뿐, 생성되는 원장 Claim을 `pin`, `confirmed` 같은 epistemic
class로 승격하지 않는다.

초안 validation과 실행 readiness는 분리된다. `pending`/`rejected` Profile은 문법 검토는 할
수 있지만 실행 진입점마다 readiness gate가 차단한다. nested Entity key 하나라도 approved가
아니면 Atom 0, cursor 미이동이다.

### 7.7 `sources` — 한 source 실행 계약으로 조립

현재 `lot_event` source 전체다.

```json
{
  "lot_event": {
    "relation": "lot_event",
    "driver": {
      "unit": "group",
      "identity": ["event_group_key"],
      "group_by": ["event_group_key"],
      "order_by": ["txn_seq"],
      "occurred_at": {
        "column": "event_time",
        "timezone": "Asia/Seoul"
      },
      "cursor": {
        "columns": ["event_time", "txn_seq"]
      },
      "preparation": {
        "preparer_id": "lot-event-live-frame@1",
        "inherit_virtual_join_rules": []
      },
      "mapper_id": "lot-event-role@1"
    },
    "profile_id": "lot-event@1"
  }
}
```

| 필드 | 설명 |
|---|---|
| source ID | `profiles.<id>.source`와 `chains`가 참조하는 이름 |
| `relation` | `tables.json`의 base physical relation |
| `driver.unit` | `row` 또는 `group` |
| `driver.identity` | 결정적인 source event identity 컬럼 |
| `driver.group_by` | group event 조립 컬럼. row이면 빈 배열 |
| `driver.order_by` | physical read order. catalog UNIQUE key 전체를 포함해야 함 |
| `driver.occurred_at.column` | 세계 시각을 담은 physical column |
| `driver.occurred_at.timezone` | 명시적 IANA timezone. 묵시 기본값 없음 |
| `driver.cursor.columns` | physical keyset cursor 컬럼. UNIQUE key 전체를 포함해야 함 |
| `driver.preparation.preparer_id` | 등록된 Preparer descriptor ID |
| `inherit_virtual_join_rules` | 이 Source가 물려받을 verified join rule ID 목록 |
| `driver.mapper_id` | 등록된 Mapper descriptor ID |
| `profile_id` | 이 Source를 해석할 Profile ID |

`order_by`와 `cursor.columns`는 각각 유일 키를 완전히 포함해야 한다. 현재 `lot_event`는
`txn_seq`가 business key이므로 `order_by: ["txn_seq"]`가 전순서를 만들고,
`cursor: ["event_time", "txn_seq"]`도 그 키를 포함한다.

Timezone은 “DB session timezone을 쓰겠지”라고 추측하지 않는다. `event_time`이 이미 offset을
갖는지, 현장 local time인지 확인하고 실제 의미를 적는다. 없거나 잘못된 timezone은 validation
단계에서 거절한다.

---

## 8. `dataflows/chains.json` — source별 cutover selector

현재 production 전체 파일이다.

```json
{
  "schema_version": 1,
  "chains": {
    "ledger_v2_execution": {
      "sources": {
        "lot_event": {
          "mode": "v2",
          "parity_status": "approved",
          "approval_ref": "stage6:b98f0c3804f5bdfc6653670da571f8fef0e9e129"
        }
      }
    }
  }
}
```

| 필드 | 허용값/용도 |
|---|---|
| `schema_version` | 현재 `1` |
| `ledger_v2_execution.sources` | `ledger_config.sources`의 모든 source를 정확히 한 번 열거 |
| `mode` | `legacy` 또는 `v2` |
| `parity_status` | `pending`, `approved`, `rejected` |
| `approval_ref` | 승인 근거 commit/stage/문서 식별자. trimmed nonblank 문자열 |

`mode: "v2"`는 `parity_status: "approved"`일 때만 허용한다. 새 source는 처음부터 V2로
켠다고 가정하지 말고, preview와 legacy shadow parity 증거를 만든 뒤 selector를 바꾼다.
설명 없는 Claim/molecule/refusal/incomplete 차이가 하나라도 있으면 approved가 아니다.

`chains` 안에 `sql`, `python`, `exec` 같은 실행 키를 중첩 배열 깊숙이 숨겨도 완전 재귀
검사에서 `unsafe_declaration`으로 거절한다.

---

## 9. `dataflows/enrichments.json` — 현재의 안전한 경계

현재 production 전체 파일이다.

```json
{
  "schema_version": 1,
  "enrichments": {}
}
```

현재 Ledger V2에서 이 파일은 manifest와 Bundle에 포함되는 선언 영역이지만, 이 가이드가
보장할 범용 runtime enrichment 문법은 아직 없다. 빈 객체가 정상이다. 결측 Claim 후보,
dependency replay, enrich action/worklist는 별도 승인된 계약을 통해 구현해야 한다.

따라서 다음을 하지 않는다.

- `enrichments`에 임의 SQL/Python/expression을 넣어 실행될 것으로 기대
- virtual join을 enrichment에 중복 선언
- 미완성 값을 자동 confirmed Claim으로 승격
- cursor 재실행이나 삭제를 enrichment 부작용으로 숨김

안전하지 않은 실행 키는 `chains`와 동일한 완전 재귀 검사로 거절된다.

---

## 10. 새 Source를 추가하는 실제 순서

아래 순서를 바꾸면 뒤 단계의 오류가 앞 단계 결함을 가린다.

### Step 1. 물리 표와 인제션을 먼저 확정

- 실제 relation 이름과 대소문자를 확인한다.
- 모든 물리 column과 타입을 확인한다.
- source event의 business/composite key를 정한다.
- DB에 그 유일성을 강제하는 constraint/index가 실제로 있는지 확인한다.
- 세계 시각 column과 timezone을 확정한다.
- null, 늦게 도착한 행, re-delivery의 의미를 정한다.

이 단계는 Ledger config 작업이 아니라 Source 소유 작업이다. Ledger config가 relation을
생성하거나 데이터 품질을 고쳐 주지 않는다.

### Step 2. `tables.json`에 physical contract 등록

새 relation의 모든 physical column을 적고, cursor 전순서와 join 단일성을 증명할 key/index를
선언한다. 다른 설정에서 컬럼을 먼저 참조하지 않는다.

검토 질문:

- 식별자를 `number`로 잘못 선언하지 않았는가?
- composite key 일부만 unique라고 오인하지 않았는가?
- 비-unique index를 cursor 증거로 쓰지 않았는가?
- catalog 선언과 실제 DB가 같은가?

### Step 3. 필요한 경우 `virtual_joins.json` 등록

신원이나 목적지 정보가 다른 inventory relation에 있을 때만 사용한다. join 없이 Preparer가
EventFrame을 완성할 수 있으면 빈 registry를 유지한다.

join을 추가할 때:

1. 오른쪽 relation도 `tables.json`에 등록한다.
2. 오른쪽 key 전체의 catalog UNIQUE 근거를 선언한다.
3. `join_key`, `expose`, `join_cardinality: "one"`을 작성한다.
4. physical verifier가 실제 index를 찾을 수 있는 테스트 환경을 준비한다.

### Step 4. 기존 의미 재사용 여부 확인

새 Vocabulary/Entity/Pack을 만들기 전에 현재 registry를 검색한다.

- 같은 개체인데 source column 이름만 다르다 → 기존 Entity 재사용
- 같은 관계인데 source 표현만 다르다 → 기존 Vocabulary/Pack 재사용
- 같은 Claim이지만 source별 컬럼이 다르다 → 새 Profile mapping만 작성
- EventFrame 조립 방식도 같다 → 기존 Preparer/Mapper 재사용
- 그룹 조립이나 도메인 해석이 다르다 → 새 trusted 구현 검토

`Pack`은 물리 테이블 이름을 알아서는 안 된다. 공통 validator와 registry에 `dt_log`,
`bonding_log`, `CORE_WAFER` 같은 source 문자열 분기를 추가하지 않는다.

### Step 5. Vocabulary와 Entity 작성

먼저 “무슨 문장을 말할지”를 닫는다.

- subject Entity type
- object kind와 Entity type
- required/optional qualifier
- 개체 logical key shape

단순히 source에 컬럼이 있다는 이유로 새 qualifier를 만들지 않는다. R&D 질문에서 보존해야 할
의미인지 먼저 판단한다.

### Step 6. Pack 작성

Claim별로 Role을 열거하고 `emit`에서 Vocabulary 위치에 연결한다.

- subject Role은 `entity`
- occurred_at Role은 `time`
- entity_ref object는 target `entity`
- Vocabulary required qualifier마다 대응 Role
- symbolic constant는 `allowed_values` 닫힌 목록

Pack은 `object_payload` dict를 Mapper가 알아서 조립하게 하지 않는다. 어떤 Role이 subject,
object, qualifier인지 Pack이 선언하므로 Mapper는 Role 값만 반환한다.

### Step 7. Preparer/Mapper descriptor 작성

기존 implementation을 재사용할 경우 config descriptor ID만 새로 만들 필요가 있는지 먼저
검토한다. 새 구현이라면 다음 코드 경계를 따른다.

- Preparer: `BaseSourcePreparer.prepare_batch()` 최종 경계
- Mapper: `BaseLedgerMapper.map()` 최종 경계
- 구현 등록: sealed implementation registry + trusted catalog

설정에 module path를 넣어 우회하지 않는다. `implementation_id`가 code registry에 없으면
`untrusted_implementation` 또는 unknown implementation 오류가 정상이다.

### Step 8. Profile 작성

1. `source`와 `packs`를 지정한다.
2. Mapper `emits`의 각 Claim에 `mapping_id`를 만든다.
3. required Role을 모두 binding한다.
4. Entity logical key를 exact set으로 채운다.
5. 모든 binding과 nested key에 origin/approval을 남긴다.
6. system suggestion이면 `suggestion_reason`을 쓴다.

초기 검토 중에는 `approval_status: "pending"`을 사용할 수 있다. 하지만 preview/execute
readiness를 확인하려면 전부 `approved`여야 한다.

### Step 9. Source driver 조립

- relation과 row/group 단위를 정한다.
- identity/group_by를 EventFrame schema에 맞춘다.
- order/cursor가 catalog UNIQUE key 전체를 포함하게 한다.
- occurred_at physical column과 timezone을 명시한다.
- Preparer, inherited join, Mapper, Profile ID를 연결한다.

Source 이름, `Profile.source`, `chains.sources` key는 정확히 일치해야 한다.

### Step 10. `chains.json`은 마지막에 전환

먼저 source를 `legacy` 또는 parity pending 상태로 두고 다음 증거를 만든다.

- Bundle validation 성공
- immutable snapshot compile 성공
- preview candidate/refusal/incomplete 결과
- 기존 translator와 shadow parity
- failure 시 Atom 0/cursor 미이동
- 필요한 경우 안전한 격리 PostgreSQL E2E

그 뒤에만 `mode: "v2"`, `parity_status: "approved"`, 실제 `approval_ref`를 기록한다.

---

## 11. `lot_event` 선언의 end-to-end 연결 읽기

현재 production 선언을 한 줄로 읽으면 다음과 같다.

```text
tables.lot_event
  physical: lot_id/event_time/txn_seq/...
  unique proof: txn_seq business_key

sources.lot_event
  group by prepared event_group_key
  order by txn_seq
  cursor (event_time, txn_seq)
  occurred_at event_time in Asia/Seoul
  preparer lot-event-live-frame@1
  mapper lot-event-role@1
  profile lot-event@1

preparer
  physical lot_id/slotnumbers/waferids/...
  → EventFrame lot/slots/wafers/event_group_key/...

mapper
  EventFrame event
  → lot-lineage claim RoleEmission 6종

profile
  EventFrame lot/wafers/slots/event_time
  → 각 Claim의 subject/target/slot/occurred_at Role

pack
  Role
  → register@1 / has_wafer@1 / derived_from@1 / slot_map@1 LedgerFrame

chains
  lot_event = v2, parity approved
```

예를 들어 `membership`은 다음 연결로 완성된다.

```text
EventFrame.lot
  → Profile subject = Entity Lot@1 {lot}
EventFrame.wafers
  → Profile target = Entity Wafer@1 {wafer}
EventFrame.slots
  → Profile slot Role
EventFrame.event_time
  → Profile occurred_at Role
Pack membership
  → has_wafer@1(subject=Lot, object=Wafer, qualifier.slot)
Vocabulary has_wafer@1
  → Lot subject, Wafer object, required slot 검증
```

어느 한 층도 다른 층의 일을 대신하지 않는다. Mapper에 `{"slot": ...}` payload를
하드코딩하지 않고, Profile이 predicate 이름을 재정의하지 않으며, Pack이 source column을
읽지 않는다.

---

## 12. transfer sample에서 virtual join과 계보 읽기

샘플 위치:

```text
server/config/sample/ontology/transfer_explorer/
```

물리 흐름은 다음과 같다.

```text
dt_log
  record_id, event_at, dt_job_id, core_wafer, core_x, core_y
       │
       │ dt_job_id = dt_job_id
       ▼
dt_inventory
  dt_lot, dt_slot, offsets, bond_wafer, bond_layer, final_chip
```

Source cursor는 `dt_log`만 읽는다. Preparer가 한 batch의 `dt_job_id`를 모아
`dt_inventory`를 read-only batch join하고 EventFrame에 목적지 identity를 붙인다. 따라서
Profile에는 `declared_lookup`이 필요 없고, 완성된 EventFrame column을 binding하면 된다.

이 예제가 보여 주는 의미 계보는 다음과 같다.

```text
CoreDie@1
  → DTDie@1
    → BondComponent@1
      → FinalChip@1
```

중요한 점:

- CoreDie를 FinalChip에 직접 우회 연결하지 않는다.
- 실제 이동 단계를 나타내는 중간 Entity를 보존한다.
- 좌표/lot/slot은 Entity key 또는 qualifier 계약에 따라 표현한다.
- Position이라는 별도 만능 객체를 만들지 않는다.
- join 0건·다건은 불완전 계보를 꾸며 내지 않고 mapper 전 거절한다.
- dependency가 늦게 도착하면 replay 후보로 남길 수 있지만 cursor reset을 자동 실행하지
  않는다.

샘플의 전체 `ledger_config.json`은 각 Entity, Pack, Profile mapping을 함께 보여 주므로 새
transfer source를 설계할 때 복사 가능한 출발점이다. 다만 sample implementation ID를 운영
trusted ID로 오인하지 않는다.

---

## 13. 검증, preview, 실행의 차이

### 13.1 JSON/Bundle validation

검증은 다음을 모두 전수 대조한다.

- manifest exact shape와 경로 경계
- 모든 catalog relation/column/key/index
- 모든 Vocabulary/Entity/Pack/Profile
- Pack ↔ Vocabulary subject/object/qualifier
- Pack Role ↔ Profile binding kind
- Profile use ↔ Mapper emits
- Source ↔ Profile/Preparer/Mapper
- Preparer physical input/output collision와 inherited join
- cursor total order의 catalog UNIQUE 근거
- unsafe executable key의 임의 깊이 재귀 검사
- 모든 binding readiness metadata

malformed JSON도 raw traceback 대신 구조화된 `code/path/message`로 거절된다. 대표 예시는
다음과 같다.

```json
{
  "code": "unknown_entity_type",
  "path": "bundle.profiles.my-profile@1.mappings[0].bind.subject.entity_type",
  "message": "unknown entity type 'Missing@1'"
}
```

```json
{
  "code": "unknown_column",
  "path": "bundle.profiles.my-profile@1.mappings[0].bind.subject.keys.input_id.column",
  "message": "column 'missing_column' is not in EventFrame schema"
}
```

```json
{
  "code": "invalid_cursor",
  "path": "bundle.sources.my_source.driver.cursor.columns",
  "message": "ordering must include every column of a catalog-declared business_key, composite_key, or UNIQUE index"
}
```

그 밖에 자주 보는 code:

| code | 뜻 | 먼저 볼 곳 |
|---|---|---|
| `unsupported_setup_version` | manifest version 불일치 | `manifest.json` |
| `unsupported_file_version` | ledger/catalog/dataflow file schema version 불일치 | 각 JSON의 `schema_version` |
| `unknown_source` | Profile/source/join이 없는 source 참조 | source ID와 `Profile.source` |
| `unknown_pack` / `unknown_claim` | Profile `use`가 registry 밖 | Pack/Claim ID와 version |
| `missing_required_role` | Claim required Role binding 누락 | `mappings[].bind` |
| `unknown_role` | Pack에 없는 Role binding | Role 철자 |
| `invalid_binding` | kind/column/constant/entity shape 오류 | 해당 binding leaf |
| `duplicate_id` | Profile 내부 mapping ID 또는 catalog index ID 중복 | 해당 `mapping_id`/`name` |
| `invalid_symbolic_constant` | Pack 허용 상수 밖 값 | Role `allowed_values` |
| `missing_required_payload` | Vocabulary required qualifier 누락 | Pack `emit.object.qualifiers` |
| `unknown_payload_field` | Vocabulary에 없는 qualifier | Pack emit |
| `unsafe_declaration` | SQL/Python/eval/exec 등 금지 키 | 정확한 nested path |
| `untrusted_implementation` | config ID가 코드 trusted catalog 밖 | Preparer/Mapper 등록 |
| `destructive_approval_required` | reset/from replay 시도 | 별도 사용자 승인 필요 |

### 13.2 write-free manifest dry-run

`server` 디렉터리에서 실행한다.

```powershell
conda run -n assy_manager python -m ledger.cutover_v2
```

이 명령은 production manifest를 로드하고 Bundle/Snapshot readiness와 source selector를
보고한다. 정상 dry-run은 DB write, cursor advance, reset, migration을 수행하지 않는다.

주의: nonempty virtual join을 가진 source는 physical verifier가 발급한 descriptor가 필요하다.
Catalog JSON만 맞는다고 physical proof를 생략해 ready라고 주장하지 않는다.

### 13.3 Explorer draft preview

서버를 기동한 뒤 다음 화면에서 active 선언을 읽고 working draft를 만든다.

```text
http://127.0.0.1:8080/admin.html#ontology
```

Admin 인증은 두 상태다.

- `ASSY_ADMIN_TOKEN`이 설정돼 있으면 모든 Admin 요청에 정확한 `X-Admin-Token`이 필요하다.
- token이 설정되지 않으면 ordinary read route(예: active `/view`)는 열릴 수 있지만,
  draft/write 같은 strict route는 `503`으로 fail-closed한다.

draft 저장은 runtime activation이 아니다. draft preview도 같은 compiler를 사용하며 검토·승인,
CAS activation 전까지 active snapshot을 바꾸지 않는다.

### 13.4 실제 execute — 쓰기 경계

다음은 기존 LedgerStore와 cursor transaction을 실제로 사용한다.

```powershell
conda run -n assy_manager python -m ledger.backfill --source lot_event --max-batches 1
```

이 명령은 **운영 DB 쓰기 권한을 뜻하지 않는다**. 대상 DB, source, 승인 상태를 확인하고 별도
사용자 승인을 받은 경우에만 실행한다. 한 source event의 Claim은 전부 통과하거나 전부
거절되며, 실패 시 Atom 0·cursor 미이동이어야 한다.

공개 CLI의 `--reset-cursor`와 `--from` replay는 V2/legacy 모두
`destructive_approval_required`로 선행 차단된다. 이 가이드만 보고 우회하거나 lower-level
helper를 직접 호출하지 않는다. legacy 실행은 명시적 `--legacy` 경로에 격리돼 있으며 기본
V2 mode는 legacy config를 읽지 않는다.

---

## 14. 테스트 전략

새 Source가 건드린 직접 범위만 우선 실행한다. 긴 full server suite와 PostgreSQL E2E는
사용자 지시에 따라 생략할 수 있지만, 실행하지 않은 테스트를 통과했다고 기록하지 않는다.

기본 집중군 예시:

```powershell
conda run -n assy_manager python -m pytest server/tests/test_ledger_setup_bundle.py -q --basetemp .test_tmp/ledger_setup_bundle
conda run -n assy_manager python -m pytest server/tests/test_ledger_setup_registry.py -q --basetemp .test_tmp/ledger_setup_registry
conda run -n assy_manager python -m pytest server/tests/test_ledger_roleframe.py -q --basetemp .test_tmp/ledger_roleframe
conda run -n assy_manager python -m pytest server/tests/test_ledger_source_preparation.py -q --basetemp .test_tmp/ledger_source_preparation
conda run -n assy_manager python -m pytest server/tests/test_ledger_runtime_v2.py -q --basetemp .test_tmp/ledger_runtime_v2
```

실제 파일명은 변경 범위와 현재 test inventory를 확인한 뒤 선택한다. 존재하지 않는 명령을
복사해 통과 근거로 쓰지 않는다.

PostgreSQL E2E는 `ASSY_PG_TEST_DATABASE_URL`이 안전한 격리 DB를 가리키고 safety guard를
통과할 때만 실행한다. URL이 없으면 skip 수와 이유를 그대로 보고한다.

최소 수락 항목:

- 같은 config의 canonical serialization/snapshot hash 결정성
- source/column 이름이 달라도 같은 Pack/Claim 재사용
- pending/rejected/nested pending 실행 차단
- virtual join 0건/다건/incomplete/collision fail-closed
- batch join N+1 방지
- preview/execute 후보 parity
- source event all-or-nothing
- failure에서 Atom 0/cursor 미이동
- legacy shadow parity의 설명 없는 차이 0
- 운영 config/DB migration/reset/legacy 삭제 0

---

## 15. 흔한 실패와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `unknown_column` | physical/EventFrame 층 혼동 | physical은 catalog/Preparer input, prepared는 output/Mapper/Profile에서 확인 |
| `invalid_cursor` | order/cursor가 UNIQUE key 전체를 안 포함 | business/composite/UNIQUE index 전체 컬럼 추가 |
| join은 선언됐는데 compile 실패 | left key가 Preparer input에 없거나 physical proof 없음 | input_columns와 실제 UNIQUE index 확인 |
| `untrusted_implementation` | sample ID를 production에 복사 | trusted code registry 등록 또는 기존 구현 재사용 |
| `missing_required_role` | Pack required Role과 Profile bind 불일치 | Claim roles를 기준으로 binding 추가 |
| `unknown_payload_field` | Pack qualifier가 Vocabulary 밖 | Vocabulary를 무작정 넓히지 말고 의미 확인 후 Pack 수정 |
| `invalid_symbolic_constant` | 허용 목록 밖 상수 | Pack allowed_values 또는 Profile constant를 올바르게 수정 |
| draft validation은 되는데 execute 불가 | pending/rejected binding 존재 | nested binding 포함 승인 상태 확인 |
| `Profile packs`는 맞는데 mapper 오류 | `mappers.emits`와 `mappings.use` 불일치 | 양쪽 Claim 집합을 정확히 맞춤 |
| join 결과 0건 | inventory 늦은 도착/키 불일치 | 원천·표기·dependency replay 후보 확인; 가짜 값 생성 금지 |
| join 결과 다건 | 오른쪽 유일성 위반 | 물리 중복 해소와 exact UNIQUE proof; 첫 행 임의 선택 금지 |
| 화면이 비어 있음 | Admin auth 상태 오해 | token 설정 여부에 따른 2상태 계약과 401/503 응답 확인 |
| `--config`가 거절됨 | 기본 V2 mode에서 legacy config 전달 | V2는 manifest 단일 진입점 사용; legacy만 명시적 `--legacy` |
| reset/from이 거절됨 | 파괴적 replay 선행 gate | 우회하지 말고 별도 사용자 승인과 작업 범위 확정 |

---

## 16. 작성 완료 체크리스트

### 물리/카탈로그

- [ ] relation과 physical columns가 실제 DB와 일치한다.
- [ ] 식별자와 수치 타입을 구분했다.
- [ ] order/cursor가 catalog-declared UNIQUE key 전체를 포함한다.
- [ ] join 오른쪽 key는 catalog와 실제 DB 모두에서 UNIQUE다.
- [ ] virtual join left key가 Preparer input에 포함된다.

### 의미

- [ ] 기존 Vocabulary/Entity/Pack을 먼저 재사용 검토했다.
- [ ] Vocabulary subject/object/qualifier가 닫혀 있다.
- [ ] Entity logical key가 source 물리 이름과 분리돼 있다.
- [ ] Pack의 Role kind/required/emission이 서로 맞는다.
- [ ] symbolic Role의 allowed values가 닫혀 있다.

### 실행

- [ ] config에 module/path/SQL/Python/expression을 넣지 않았다.
- [ ] Preparer input/output과 Mapper input이 exact하게 맞는다.
- [ ] trusted implementation ID/version이 코드에 실제 등록돼 있다.
- [ ] Mapper emits와 Profile mapping use가 양방향 일치한다.
- [ ] Source/Profile/chain source ID가 일치한다.

### 승인/검증

- [ ] 모든 nested binding까지 origin/approval metadata가 있다.
- [ ] system suggestion마다 suggestion reason이 있다.
- [ ] 실행 전 모든 binding이 approved다.
- [ ] manifest dry-run이 ready이고 write 0이다.
- [ ] preview/execute parity와 all-or-nothing을 검증했다.
- [ ] legacy shadow parity의 설명 없는 차이가 0이다.
- [ ] 미실행 full/PG 테스트를 통과로 표현하지 않았다.
- [ ] reset/replay/migration/legacy 삭제를 수행하지 않았다.

---

## 17. 정본과 참고 문서

| 목적 | 문서/코드 |
|---|---|
| 현재 시스템 상태와 인수인계 | [FORK_SESSION_BRIEF](../process/FORK_SESSION_BRIEF.md) |
| V2 파일 정본과 디렉터리 | [CONFIG_CANON](../../ledger_v2_redesign_plan_20260817/CONFIG_CANON.md) |
| Bundle exact validation | `server/ledger/setup_bundle.py` |
| Registry/Snapshot compile | `server/ledger/setup_registry.py` |
| RoleFrame/Pack compile | `server/ledger/roleframe.py` |
| Source preparation | `server/ledger/source_preparation.py` |
| preview/execute | `server/ledger/runtime_v2.py` |
| manifest dry-run/cutover | `server/ledger/cutover_v2.py` |
| 현재 production 선언 | `server/config/ontology/` |
| transfer file-backed sample | `server/config/sample/ontology/transfer_explorer/` |
| Explorer 전체 계약 | `ontology_config_explorer_plan/02_IMPLEMENTATION_AND_ACCEPTANCE.md` |

정확한 필드가 이 문서와 validator에서 충돌하면 코드와 승인된 V2 acceptance evidence를 먼저
대조한다. 문서를 조용히 추측으로 고치지 말고, 실제 contract 변경이면 validator·테스트·정본
문서를 한 커밋에서 함께 갱신한다.
