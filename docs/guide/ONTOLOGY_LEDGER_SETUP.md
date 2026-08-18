# Ledger V2 설정 작성 가이드

> **Status:** 🟢 Living
> **Last-verified:** 2026-08-18
> **Owner:** Server / Ledger
> **정본 구현:** `server/ledger/setup_bundle.py`(파일 문법), `setup_registry.py`(compile), `setup.py`(로드 경계)
> **운영 선언 루트:** `server/config/ontology/` — 파일 **하나**, `ledger_config.json`

이 문서는 새 원천 테이블을 Ledger V2에 연결할 때 **무엇을 어떤 순서로 작성하고,
각 필드가 왜 필요한지** 설명하는 단일 설정 가이드다. 구형
`server/config/ledger_config.json`(flat legacy 선언), translator 종류, `declared_lookup`,
Position/Frame, 마이그레이션·cursor reset 중심의 옛 설정 절차는 이 문서의 대상이 아니다.

> 🔴 **셋업은 파일 하나다.** 소스 하나를 붙이는 사람이 여는 것은 `ledger_config.json`과 —
> 필요하다면 — mapper 함수 하나뿐이고, **단순한 소스는 mapper조차 필요 없다**(§7.4의
> `declarative-role@1`, §7.3의 `direct-join@1`). 예전에는 `manifest.json`이 열거하는
> 다섯 파일을 세 디렉터리에 나눠 썼다. 그 모양은 **은퇴했다** — 옛 내용은 지워지지 않고
> 보존돼 있지만 **로드되지 않으며 지원 경로가 아니다.** 어디에 무엇이 남았는지는 §2.3.

설정은 DB 테이블을 만들지 않고, 데이터를 쓰지 않으며, Python 구현을 config 문자열로
불러오지 않는다. 물리 테이블과 인제션이 먼저 존재해야 한다. 설정은 그 데이터를 어떻게
읽고 의미로 바꿀지를 선언한다.

---

## 1. 먼저 이해할 전체 흐름

```text
server/config/ontology/ledger_config.json
  ├─ setup_version      현재 정확히 3
  ├─ tables             물리 relation/column/key/index
  ├─ vocabulary         낼 수 있는 술어와 목적어 모양
  ├─ entities           개체의 정체성과 키
  ├─ packs              Role → Claim/LedgerFrame
  ├─ source_preparers   물리 행 → EventFrame
  ├─ mappers            EventFrame → RoleEmission
  ├─ profiles           소스 컬럼 → Pack Role binding
  ├─ sources            위 선언을 한 실행 단위로 조립 — 여기 있으면 «돈다»
  └─ virtual_joins      (선택) 물리 UNIQUE로 검증할 batch join

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

핵심은 세 층을 분리하는 것이다. 파일이 하나가 됐다고 층이 섞이는 것은 아니다 — 층은
이제 **section**으로 나뉜다.

| 층 | 질문 | 소유 section |
|---|---|---|
| 물리 | 어느 테이블의 어느 컬럼을 어떤 키로 읽나? | `tables`, `virtual_joins`, `sources` |
| 의미 | 무엇을 개체·관계·시각으로 말하나? | `vocabulary`, `entities`, `packs`, `profiles` |
| 실행 | 누가 행을 준비하고 Role로 해석하나? | `source_preparers`, `mappers`, `sources` |

`Profile`은 Pack이 아니다. Pack은 재사용 가능한 Claim 문법이고, Profile은 특정 Source의
컬럼을 그 문법의 Role에 연결하는 배선이다.

---

## 2. 실제 파일 위치와 복사 가능한 기준 샘플

### 2.1 현재 승인된 `lot_event` 운영 root

```text
server/config/ontology/
├─ ledger_config.json   ← 셋업 전부
└─ README.md
```

이 파일은 예시 사본이 아니라 현재 운영 정본이다. 수정 전에는 별도 작업 브랜치에서
전체 Bundle 검증과 preview를 먼저 수행한다.

🔴 **root에 다른 `.json`이 있으면 로더가 «거절»한다**(`unlisted_config_file`). 이것은
정돈 취향이 아니라 「이 파일 하나를 열면 전부 본 것」이라는 약속의 집행이다. 남겨 둔
`catalog/tables.json`은 아무도 읽지 않으면서 권위 있어 보이는 자리에 앉아 있게 된다.
검사는 **재귀한다** — 백업 폴더를 root **안에** 두어도 걸린다. 거절 메시지가
「move it outside the config root」로 끝나는 이유가 그것이다.

### 2.2 이종 transfer와 virtual join 샘플

```text
server/config/sample/ontology/transfer_explorer/ledger_config.json
```

같은 단일 파일 모양이고, 운영 root가 쓰지 않는 **선택 section `virtual_joins`**를 실제로
쓰는 유일한 예제다(§6).

이 샘플은 다음을 보여준다.

- `dt_log`를 cursor가 읽는다.
- Preparer가 `dt_job_id`를 키로 `dt_inventory`를 batch join한다.
- `CoreDie@1 → DTDie@1 → BondComponent@1 → FinalChip@1` 연속 계보를 선언한다.
- 오른쪽 relation의 `dt_job_id`는 business key와 UNIQUE index로 단일성을 증명한다.

주의: config가 이름으로 부를 수 있는 구현은 **코드에 실재하는 클래스**뿐이다. 파일을
production root에 복사하는 것만으로 trusted implementation이 생기지 않는다. 어떤 이름이
실행 가능한지는 `server/ledger/implementations.py`가 **코드에서 발견해** 답한다(§7.3·§7.4).

### 2.3 옛 다섯 파일을 찾고 있다면

2026-08-18 이전 root는 `manifest.json`이 열거하는 다섯 파일이었다. 찾는 것에 따라 자리가
다르다.

**① 은퇴한 «주변» 파일 넷 + manifest** — 지워지지 않고 옮겨졌다.

```text
server/config/_ontology_pre_single_file_20260818/
├─ manifest.json
├─ catalog/{tables,virtual_joins}.json
└─ dataflows/{chains,enrichments}.json
```

⚠️ **여기에 `ledger_config.json`은 «없다».** 그 파일은 옮겨진 것이 아니라 **제자리에서 새
모양으로 다시 쓰였다** — 지금 `server/config/ontology/ledger_config.json`이 그것이다.

**② 접기 «직전»의 다섯 파일 전부(옛 `ledger_config.json` 포함)** — 변환 근거로 통째 보존돼
있다.

```text
task/evidence/ontology_root_before_20260818/
```

둘 다 **내용을 대조할 때만** 본다. **지원되는 config 경로가 아니다** — 로더는 이 모양을 읽지
않고, 어느 쪽이든 config root 안으로 되돌리면 §2.1의 거절이 난다.

아직 옛 모양의 root를 들고 있다면 일회용 변환기가 있다.

```powershell
conda run -n assy_manager python server/scripts/convert_ontology_to_single_file.py --root <다섯 파일이 다 있는 옛 root> --out <빈 디렉터리>/ledger_config.json
```

원본을 지우지 않고 **새 파일 하나**를 쓴 뒤 무엇이 어디로 갔는지 표로 출력한다. 옮길 자리가
없는 선언(비어 있지 않은 `enrichments`, `v2`가 아닌 selector 항목)은 조용히 버리지 않고
**멈춘다**. 옛 root와 새 파일이 한 디렉터리에 공존하면 로드되지 않으므로 출력은 빈
디렉터리에 쓴다. 🔴 `--root`는 **다섯 파일이 다 있는** root여야 한다 — 위 ①은
`ledger_config.json`이 없어 이 변환기의 입력이 아니다(②는 입력이 된다).

---

## 3. 작성 전 준비 사항

설정을 열기 전에 아래 질문에 답한다.

1. **물리 relation은 이미 존재하는가?** `tables` section은 DDL이 아니다.
2. **한 source event는 한 행인가, 여러 행의 group인가?**
3. **세계 시각 컬럼은 무엇이며 timezone은 무엇인가?** 묵시적 기본 timezone은 없다.
4. **cursor 동률을 제거할 catalog-declared UNIQUE key는 무엇인가?**
5. **Preparer 출력만으로 신원이 완성되는가?** 아니면 verified virtual join이 필요한가?
6. **기존 trusted Preparer/Mapper를 재사용할 수 있는가?**
7. **기존 Vocabulary/Entity/Pack으로 말할 수 있는가?** 새 의미가 아니면 중복 선언하지 않는다.
8. **이 소스를 지금 돌려도 되는가?** 🔴 `sources`에 적는 순간 **돈다**. 「적어 두고 나중에
   켜기」를 해 주는 별도 스위치는 없다(§8). 준비가 덜 됐다면 `sources`에 아직 적지
   않는다.

### row와 group 선택

| 원천 모양 | `source.driver.unit` | `group_by` | 예 |
|---|---|---|---|
| 한 행이 독립된 source event | `row` | 반드시 `[]` | 한 행당 측정 1건 |
| 여러 행이 한 source event를 이룸 | `group` | 1개 이상 | split/merge 한 거래의 여러 wafer 행 |

group일 때 `group_by`는 `identity`의 부분집합이어야 한다. `identity`와 `group_by`에는
Preparer가 만든 EventFrame 컬럼을 쓸 수 있지만, `order_by`, `cursor`, `occurred_at`은 base
physical relation 컬럼이어야 한다.

---

## 4. `ledger_config.json` — 하나뿐인 파일과 그 최상위 모양

최상위는 `setup_version` 하나와 section 여덟, 그리고 선택 section 하나다.

```json
{
  "setup_version": 3,
  "tables": {},
  "vocabulary": {},
  "entities": {},
  "packs": {},
  "source_preparers": {},
  "mappers": {},
  "profiles": {},
  "sources": {}
}
```

| 최상위 키 | 필수 | 용도 |
|---|---:|---|
| `setup_version` | 예 | 문법 세대. 현재 정확히 `3`. 다른 값은 `unsupported_setup_version` |
| `tables` | 예 | 물리 relation/column/key/index (§5) |
| `vocabulary` | 예 | 술어의 닫힌 서명 (§7.1) |
| `entities` | 예 | 개체 ID와 key shape (§7.2) |
| `packs` | 예 | Role → Claim 문법 (§7.5) |
| `source_preparers` | 예 | 물리 batch → EventFrame (§7.3) |
| `mappers` | 예 | EventFrame → RoleEmission (§7.4) |
| `profiles` | 예 | source 컬럼 → Pack Role binding (§7.6) |
| `sources` | 예 | 실행 계약 조립 (§7.7) |
| `virtual_joins` | **아니오** | verified read-only batch join (§6) |

🔴 **여덟은 비어 있어도 «있어야» 한다.** 키가 없는 것과 `{}`인 것은 읽는 사람에게 다른
뜻이고, 「이 section은 나에게 해당 없음」은 적어 둘 값어치가 있는 결정이다. 키 자체가
빠지면 `missing_field`다.

`setup_version` 하나가 예전 다섯 파일의 `schema_version` 다섯 개가 하던 말을 한다. 파일별
버전 필드는 **없다** — `schema_version`을 최상위에 적으면 `unknown_field`로 거절된다.
표 밖의 다른 키도 마찬가지다.

section 여덟은 사용 여부와 관계없이 전수 검증된다. “아직 Source가 선택하지 않은 Profile”도
unknown Entity/column을 숨길 수 없다. 모든 오류는 `code`, 정확한 JSON `path`, `message`로
돌아오며 여러 오류의 순서도 결정적이다.

### 4.1 root에 다른 JSON을 두지 않는다

로더는 config root **아래 어디든** `ledger_config.json`이 아닌 `.json`이 있으면
`unlisted_config_file`로 거절한다. 근거는 §2.1에 있다. 백업·초안·변환 결과는 root 밖에
둔다.

---

## 5. `tables` — 물리 스키마와 유일성 근거

현재 `lot_event` 운영 선언 전체다(파일 안 `tables` 값).

```json
{
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
```

### 5.1 section 모양

`tables`는 relation 이름 → descriptor 맵이다. Source를 선언하려면 그 base relation이 여기
있어야 한다.

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
```

`business_key`, `composite_key`, 또는 `unique: true` index의 **전체 컬럼 집합**만 cursor
전순서의 증거가 된다. 컬럼이 존재한다는 사실, `identity`, `group_by`, 비-unique index는
유일성 증거가 아니다. 예를 들어 `event_at`만으로 정렬하면 같은 시각의 두 행 순서가
불안정하므로 `invalid_cursor`다. 위 예시는 `machine_id`와 `sequence_no`를 모두 포함해야
동률이 제거된다.

Catalog 선언은 물리 DB를 만들거나 UNIQUE index를 생성하지 않는다. 실제 DB 구조가 별도로
존재해야 하며, virtual join의 경우 physical verifier가 그 UNIQUE index를 직접 확인한다.

---

## 6. `virtual_joins` — verified read-only batch join (선택 section)

🔴 **이 section만 선택이다.** 운영 root(`server/config/ontology/ledger_config.json`)는
`virtual_joins`를 **갖고 있지 않다** — 그 자리에 있던 registry가 비어 있었고, enabled rule은
어차피 호출자가 물리 검증된 descriptor를 공급해야 승인되므로 잃은 것이 없다. 그러나
**로더는 이 section을 읽을 줄 안다**: `server/config/sample/ontology/transfer_explorer/`가
실제 descriptor를 공급한다. **파일에서 section을 뺀 것과 로더에서 지원을 뺀 것은 다른
일이고, 일어난 것은 앞의 것뿐이다.**

join이 필요 없으면 이 키를 아예 쓰지 않는다. 빈 `{}`를 두어도 되지만 없는 편이 낫다.

`transfer_explorer` 샘플의 실제 선언은 다음과 같다(파일 안 `virtual_joins` 값).

```json
{
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

1. 왼쪽·오른쪽 relation과 모든 컬럼이 `tables` section에 존재해야 한다.
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

## 7. 의미와 실행 section

여기부터는 §4 표의 나머지 일곱 section을 하나씩 본다. 아래의 JSON 블록은 모두
`ledger_config.json` 안 해당 키의 **값**이다.

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

🔴 **먼저 `direct-join@1`을 본다 — 대개 Preparer 코드는 필요 없다.**
`ledger.source_preparation.DirectJoinSourcePreparer`는 계산을 하지 않는 범용 Preparer로,
선언한 출력 컬럼 각각이 상속한 verified join 정확히 하나에 의해 expose되면 그대로 쓴다.
`transfer_explorer` 샘플이 이것을 쓴다. 정규화·그룹 조립처럼 **계산이 필요할 때만** 새
구현을 만든다.

새로운 실행 모양이 필요하면 `BaseSourcePreparer` 하위 클래스를 코드에 추가한다. 클래스가
자기 `implementation_id`/`implementation_version`을 스스로 선언하고
`server/ledger/implementations.py`가 그것을 **코드에서 발견해** 신뢰 집합을 만든다. 별도
목록에 이름을 다시 적을 곳은 없다.

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
      "lot-lineage@1/register",
      "lot-lineage@1/membership",
      "lot-lineage@1/lineage",
      "lot-lineage@1/slot_map"
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

🔴 **단순한 소스는 mapper 코드를 쓰지 않는다.** `ledger.roleframe.DeclarativeRoleMapper`
(`implementation_id: "declarative-role"`, version 1)는 Profile이 선언한 column/constant/entity
binding을 그대로 평가하는 범용 mapper다. 어느 특정 source도 알지 못하고 DB에 접근하지
않는다. **업무적 읽기가 binding만으로 표현되는 소스는 이 이름을 적으면 끝이다** —
`transfer_explorer` 샘플이 그렇게 한다. 위 `lot-event-role@1`처럼 전용 mapper가 필요한 것은
행을 쪼개거나 도메인 규칙으로 해석해야 할 때뿐이다.

전용 mapper를 새로 만든다면 **파일 하나**다: `server/mappers/ledger_v2_*.py`에
`BaseLedgerMapper` 하위 클래스를 쓰고 클래스가 자기 `implementation_id`와
`implementation_version`을 선언한다. `server/ledger/implementations.py`는 편집하지 않는다 —
그 모듈이 발견해 간다.

### 7.5 `packs` — Role을 Vocabulary Claim으로 만드는 문법

아래는 가장 단순한 register Claim의 실제 section fragment다.

```json
{
  "lot-lineage@1": {
    "claims": {
      "register": {
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
        "use": "lot-lineage@1/register",
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
있고, 정본은 `server/config/ontology/ledger_config.json`의 `profiles` section이다.

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
| source ID | `profiles.<id>.source`가 참조하는 이름. **여기 있으면 이 소스는 돈다**(§8) |
| `relation` | `tables` section의 base physical relation |
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

## 8. 선언이 곧 활성화다 — 실행 스위치는 없다

🔴 **`sources`에 있는 source는 «돈다».** 「돈다」고 다시 말해 주는 두 번째 자리는 없다.

예전에는 `dataflows/chains.json`의 `ledger_v2_execution` selector가 source마다 `mode`,
`parity_status`, `approval_ref`를 들고 있었다. 셋 다 은퇴했다. 그 파일도, 그 문법도 없다.

**왜 느슨해진 것이 아닌가.** selector는 애초에 「선언은 됐지만 돌 준비는 안 됨」을 붙들고
있지 않았다. binding이 전부 `approved`가 아닌 Profile은 **로드 시점에** readiness gate가
거절하므로, 절반만 쓴 소스는 스위치가 무슨 말을 하든 돌 수 없었다. 그리고 스위치의 다른
쪽 위치(`legacy`)는 이제 **아무것도 연결되지 않은 config**를 가리켰다. 남겨 두면 새 소스를
**두 번** 적어야 하고, 그중 하나는 Explorer가 보여 주지도 않는 파일이었다 — 실제로 그렇게
한 소스를 적는 것을 잊은 적이 있다.

따라서 준비의 표현은 이렇게 한다.

- **아직 돌리면 안 되는 소스** → `sources`에 아직 적지 않는다. 나머지 section(Pack, Profile,
  Entity)은 먼저 적어도 되고, 전수 검증도 받는다.
- **다 됐는데 잠시 꺼 두고 싶다** → 그런 요구가 실제로 생기면 그 소스 **자기 선언 안**
  (`sources.<id>.enabled`)에 들어갈 자리다. 드리프트하는 별도 파일이 아니다. 🔴 **현재
  그런 필드는 구현돼 있지 않다** — 지금 필요하면 총괄에 가져간다.

`sources` 안에 `sql`, `python`, `exec` 같은 실행 키를 중첩 배열 깊숙이 숨겨도 완전 재귀
검사에서 `unsafe_declaration`으로 거절한다. 이 검사는 파일 전체에 걸린다.

---

## 9. enrichment는 이 셋업에 없다

`dataflows/enrichments.json`은 은퇴했고 대체 section도 없다. 그 파일은 항상 비어 있었고
읽는 코드가 없었다.

결측 Claim 후보, dependency replay, enrich action/worklist가 필요하면 **별도 승인된 계약**을
통해 구현한다. 특히 다음은 하지 않는다.

- `ledger_config.json`에 임의 SQL/Python/expression을 넣어 실행될 것으로 기대
- 미완성 값을 자동 confirmed Claim으로 승격
- cursor 재실행이나 삭제를 부작용으로 숨김

---

## 10. 새 Source를 추가하는 실제 순서

전부 `server/config/ontology/ledger_config.json` **한 파일 안**에서 일어난다. 아래 순서를
바꾸면 뒤 단계의 오류가 앞 단계 결함을 가린다.

🔴 **`sources`(Step 9)를 마지막에 적는다.** 그것이 「켠다」이기 때문이다(§8). 앞의 여덟
단계는 아직 아무것도 돌리지 않는다.

### Step 1. 물리 표와 인제션을 먼저 확정

- 실제 relation 이름과 대소문자를 확인한다.
- 모든 물리 column과 타입을 확인한다.
- source event의 business/composite key를 정한다.
- DB에 그 유일성을 강제하는 constraint/index가 실제로 있는지 확인한다.
- 세계 시각 column과 timezone을 확정한다.
- null, 늦게 도착한 행, re-delivery의 의미를 정한다.

이 단계는 Ledger config 작업이 아니라 Source 소유 작업이다. Ledger config가 relation을
생성하거나 데이터 품질을 고쳐 주지 않는다.

### Step 2. `tables` section에 physical contract 등록

새 relation의 모든 physical column을 적고, cursor 전순서와 join 단일성을 증명할 key/index를
선언한다. 다른 section에서 컬럼을 먼저 참조하지 않는다.

검토 질문:

- 식별자를 `number`로 잘못 선언하지 않았는가?
- composite key 일부만 unique라고 오인하지 않았는가?
- 비-unique index를 cursor 증거로 쓰지 않았는가?
- catalog 선언과 실제 DB가 같은가?

### Step 3. 필요한 경우 `virtual_joins` section 추가

신원이나 목적지 정보가 다른 inventory relation에 있을 때만 사용한다. join 없이 Preparer가
EventFrame을 완성할 수 있으면 이 선택 section을 아예 쓰지 않는다.

join을 추가할 때:

1. 오른쪽 relation도 `tables` section에 등록한다.
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

🔴 **먼저 범용 구현으로 끝나는지 본다.** 다음 둘이면 Python을 한 줄도 쓰지 않는다.

- Preparer `direct-join@1` — 출력 컬럼이 상속한 verified join에서 그대로 오는 경우
- Mapper `declarative-role@1` — 업무적 읽기가 Profile binding만으로 표현되는 경우

전용 구현이 정말 필요하면 다음 코드 경계를 따른다.

- Preparer: `BaseSourcePreparer.prepare_batch()` 최종 경계(하위 클래스는
  `prepare_outputs()`를 구현한다)
- Mapper: `BaseLedgerMapper.map()` 최종 경계(하위 클래스는 `interpret_unit()`을 구현한다)
- 위치: mapper는 `server/mappers/ledger_v2_*.py`, preparer는 `server/ledger/`
- 신뢰 등록: **없다.** 클래스가 `implementation_id`/`implementation_version`을 자기 자신에
  선언하면 `server/ledger/implementations.py`가 발견한다. 손으로 유지하는 목록은 없다.

설정에 module path를 넣어 우회하지 않는다. `implementation_id`가 발견되지 않으면
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

### Step 9. Source driver 조립 — 이것이 「켠다」이다

🔴 **`sources`에 항목을 적는 순간 그 소스는 실행 대상이다.** 앞의 여덟 단계를 끝내고 아래
증거를 만든 뒤에 적는다.

- Bundle validation 성공
- immutable snapshot compile 성공
- preview candidate/refusal/incomplete 결과
- failure 시 Atom 0/cursor 미이동
- 필요한 경우 안전한 격리 PostgreSQL E2E

적을 때 확인할 것:

- relation과 row/group 단위를 정한다.
- identity/group_by를 EventFrame schema에 맞춘다.
- order/cursor가 catalog UNIQUE key 전체를 포함하게 한다.
- occurred_at physical column과 timezone을 명시한다.
- Preparer, inherited join, Mapper, Profile ID를 연결한다.

Source 이름과 `Profile.source`는 정확히 일치해야 한다.

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
```

`sources.lot_event`가 존재한다는 것이 곧 「이 소스는 돈다」이다. 그 위에 얹힌 selector는
없다.

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
server/config/sample/ontology/transfer_explorer/ledger_config.json
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

샘플의 `ledger_config.json` 하나가 `tables`·`virtual_joins`·각 Entity·Pack·Profile mapping을
함께 보여 주므로 새 transfer source를 설계할 때 복사 가능한 출발점이다. 🔴 이 샘플은
Preparer `direct-join@1`과 Mapper `declarative-role@1`을 쓴다 — **전용 Python이 0줄인 소스가
실제로 어떤 모양인지**가 여기 있다.

---

## 13. 검증, preview, 실행의 차이

### 13.1 JSON/Bundle validation

검증은 다음을 모두 전수 대조한다.

- 최상위 exact shape(필수 section 여덟 + `setup_version`, 여분 키 금지)와 config root에 다른
  JSON이 없음
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
  "code": "invalid_mapper",
  "path": "bundle.profiles.my-profile@1.mappings[0].bind.subject.keys.input_id.column",
  "message": "Profile column 'missing_column' at bundle.profiles.my-profile@1.mappings[0].bind.subject.keys.input_id.column is missing"
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
| `unlisted_config_file` | config root에 `ledger_config.json` 말고 다른 `.json`이 있음(재귀) | root 밖으로 옮긴다 |
| `unsupported_setup_version` | `setup_version`이 `3`이 아님 | 파일 최상위 |
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

### 13.2 write-free dry-run

`server` 디렉터리에서 실행한다.

```powershell
conda run -n assy_manager python -m ledger.setup
```

운영 config root를 로드하고 결정적인 JSON 한 줄을 낸다 — `config_root`, `setup_version`,
`snapshot_sha256`, `readiness`, 선언된 `sources`(각 `source_id`/`relation`), 그리고
`destructive_actions`가 전부 false임. 정상 dry-run은 DB write, cursor advance, reset,
migration을 수행하지 않는다.

🔴 **`mode`도 `parity_status`도 이 출력에 없다.** 그런 필드는 은퇴했다(§8). 「이 소스가
도는가」의 답은 `sources` 목록에 있느냐다.

주의: `virtual_joins`를 가진 source는 physical verifier가 발급한 descriptor가 필요하다.
선언 JSON만 맞는다고 physical proof를 생략해 ready라고 주장하지 않는다.

### 13.3 Explorer draft preview

서버를 기동한 뒤 다음 화면에서 active 선언을 읽고 working draft를 만든다.

```text
http://127.0.0.1:8080/admin.html#ontology
```

Admin 인증은 두 상태다.

- `ASSY_ADMIN_TOKEN`이 설정돼 있으면 모든 Admin 요청에 정확한 `X-Admin-Token`이 필요하다.
  header가 없으면 `401`, 값이 설정된 token과 다르면 `403`이다.
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

공개 CLI의 `--reset-cursor`와 `--from` replay는 `destructive_approval_required`로 선행
차단된다. 이 가이드만 보고 우회하거나 lower-level helper를 직접 호출하지 않는다.

CLI가 받는 나머지 플래그는 `--source`, `--fetch-rows`, `--max-batches`, 그리고 config root를
가리키는 `--ontology-root`(기본값 `server/config/ontology`)뿐이다. **실행 경로는 하나이고
`--legacy`나 `--config` 같은 갈래는 없다.**

---

## 14. 테스트 전략

새 Source가 건드린 직접 범위만 우선 실행한다. 긴 full server suite와 PostgreSQL E2E는
사용자 지시에 따라 생략할 수 있지만, 실행하지 않은 테스트를 통과했다고 기록하지 않는다.

🔴 **파일명 목록을 여기 박아 두지 않는다.** 이 문서가 들고 있던 목록은 테스트가 개명되는
날 조용히 낡고, 없는 파일을 지목한 명령은 「돌렸다」는 근거로 재사용된다. 아래 첫 명령은
**패턴**이라 실행 시점에 실재하는 파일로 풀린다.

⚠️ **경로가 `server/tests/`이므로 이 절의 명령은 «저장소 루트»에서 실행한다** — §13의
dry-run/backfill 명령이 `server/`에서 도는 것과 다르다.

```powershell
conda run -n assy_manager python -m pytest server/tests/test_ledger_setup_*.py -q --basetemp .test_tmp/ledger_setup
```

범용 구현으로 Python 0줄 소스를 붙였다면 다음 둘이 그 경로의 직접 범위다.

```powershell
conda run -n assy_manager python -m pytest server/tests/test_ledger_zero_python_source.py server/tests/test_ledger_implementations.py -q --basetemp .test_tmp/ledger_zero_python
```

변경 범위가 더 넓으면 **먼저 수집만 해서** 무엇이 걸리는지 본다. 수집 오류가 섞여 나오면
그 자체가 정보다 — 없는 것을 돌린 셈 치지 말고 원인을 본다.

```powershell
conda run -n assy_manager python -m pytest server/tests/ -q --collect-only -k ledger
```

존재하지 않는 명령을 복사해 통과 근거로 쓰지 않는다.

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
- config root에 다른 JSON을 두면 `unlisted_config_file`로 거절
- 운영 config/DB migration/reset 0

---

## 15. 흔한 실패와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `invalid_mapper` (`Profile column ... is missing`) | physical/EventFrame 층 혼동 | 🔴 **Profile이 binding할 수 있는 컬럼 집합은 정확히 mapper의 `input_columns`다.** `tables`에만 있고 mapper input에 없는 컬럼은 binding할 수 없고, preparer `output_columns`에 있어도 mapper input에 없으면 거절된다 |
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
| 화면이 비어 있음 | Admin auth 상태 오해 | token 설정 시 header 누락 `401`·값 불일치 `403`, token 미설정 strict route `503`을 구분 |
| `unlisted_config_file` | config root 안에 다른 `.json`이 있음(백업 폴더 포함 — 검사는 재귀한다) | root **밖**으로 옮긴다. 옛 다섯 파일은 §2.3 |
| `unsupported_setup_version` | 파일에 `setup_version: 3`이 없거나 옛 `schema_version`을 씀 | §4의 최상위 모양 |
| 안 켠 소스가 돌았다 | `sources`에 적는 것이 곧 켜는 것 | §8. 준비 전이면 `sources`에서 뺀다 |
| `--legacy`/`--config`가 없다 | 실행 경로가 하나가 됨 | `--ontology-root`로 config root를 지정한다(§13.4) |
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
- [ ] `implementation_id`/version을 가진 클래스가 코드에 실제 있다(범용 `direct-join@1`·
      `declarative-role@1`으로 끝나는지 먼저 확인했다).
- [ ] Mapper emits와 Profile mapping use가 양방향 일치한다.
- [ ] Source ID와 `Profile.source`가 일치한다.
- [ ] 이 소스를 **지금 돌려도 되는 상태**에서만 `sources`에 적었다.

### 승인/검증

- [ ] 모든 nested binding까지 origin/approval metadata가 있다.
- [ ] system suggestion마다 suggestion reason이 있다.
- [ ] 실행 전 모든 binding이 approved다.
- [ ] `python -m ledger.setup` dry-run이 `readiness: "ready"`이고 write 0이다.
- [ ] config root에 `ledger_config.json` 말고 다른 `.json`이 없다.
- [ ] preview/execute parity와 all-or-nothing을 검증했다.
- [ ] 미실행 full/PG 테스트를 통과로 표현하지 않았다.
- [ ] reset/replay/migration을 수행하지 않았다.

---

## 17. 정본과 참고 문서

| 목적 | 문서/코드 |
|---|---|
| 현재 시스템 상태와 인수인계 | [FORK_SESSION_BRIEF](../process/FORK_SESSION_BRIEF.md) |
| 최상위 section 목록과 필수/선택 구분 | `server/ledger/setup_bundle.py`의 `LOGICAL_SECTIONS`·`OPTIONAL_SECTIONS`·`SETUP_VERSION` |
| Bundle exact validation | `server/ledger/setup_bundle.py` |
| Registry/Snapshot compile | `server/ledger/setup_registry.py` |
| RoleFrame/Pack compile · 범용 mapper | `server/ledger/roleframe.py` |
| Source preparation · 범용 preparer | `server/ledger/source_preparation.py` |
| 어떤 `implementation_id`가 실행 가능한가 | `server/ledger/implementations.py` |
| preview/execute | `server/ledger/runtime_v2.py` |
| 로드 경계와 dry-run 보고 | `server/ledger/setup.py` |
| 옛 다섯 파일 → 한 파일 변환 | `server/scripts/convert_ontology_to_single_file.py` |
| 현재 production 선언 | `server/config/ontology/ledger_config.json` |
| transfer file-backed sample | `server/config/sample/ontology/transfer_explorer/ledger_config.json` |
| Explorer 전체 계약 | `ontology_config_explorer_plan/02_IMPLEMENTATION_AND_ACCEPTANCE.md` |

정확한 필드가 이 문서와 validator에서 충돌하면 코드와 승인된 V2 acceptance evidence를 먼저
대조한다. 문서를 조용히 추측으로 고치지 말고, 실제 contract 변경이면 validator·테스트·정본
문서를 한 커밋에서 함께 갱신한다.
