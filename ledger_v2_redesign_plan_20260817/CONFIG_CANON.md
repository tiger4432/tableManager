# Ledger v2 Config Canon

> 상태: `TARGET_CONTRACT` · 구현 전 계획
> Config root: `server/config/ontology/`
> 핵심: Pack/Profile/Registry는 `ledger_config.json` 한 파일 안에서 함께 작성한다.

## 1. 목표 디렉터리

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

Registry마다 파일을 쪼개지 않는다. `ledger_config.json`의 section을 검증·컴파일해 각각의
immutable Registry를 만든다.

## 2. 파일별 역할

| Config | 단독 소유 | 주요 소비자 | 넣으면 안 되는 것 |
|---|---|---|---|
| `manifest.json` | setup version, 읽을 파일의 정확한 경로 | Config loader | Registry 본문, glob, root 밖 경로 |
| `ledger_config.json` | Vocabulary, Entity, Preparer, Mapper, Pack, Profile, Source 선언 | 모든 Ledger Registry/compiler | 물리 join key 복사, Python path, raw SQL |
| `catalog/tables.json` | 물리 relation, column, type, business/composite key | DB/table loader, cursor validator, join verifier | Predicate, Pack, Claim 의미 |
| `catalog/virtual_joins.json` | left/right relation, join key, expose, folding, cardinality | VirtualJoin verifier/UI/Ledger preparer | Pack/Role, source binding, raw SQL |
| `dataflows/chains.json` | source 변화→파생 실행 연결, 순서·활성 상태 | Chain worker/replay | Pack Role/Predicate 의미 |
| `dataflows/enrichments.json` | 결측 판단, 공급 source, worklist/action | Enrichment/dependency replay | Claim을 confirmed/pin으로 승격하는 규칙 |

## 3. `manifest.json`

```jsonc
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

- manifest에 없는 JSON은 로드하지 않는다.
- `..`, 절대경로, symlink root escape, glob을 거절한다.
- 각 파일은 자기 `schema_version`을 가진다.
- 모든 파일의 canonical serialization/hash가 실행 snapshot version이다.

## 4. `ledger_config.json`

한 파일에서 관련 의미를 같이 본다.

```jsonc
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

| Section | 역할 | 컴파일 결과 |
|---|---|---|
| `vocabulary` | Predicate ID/version/status, subject/object signature | `VocabularyRegistry` |
| `entities` | Entity type ID/version, identity key/type/null 규칙 | `EntityTypeRegistry` |
| `source_preparers` | Preparer ID/version, input/output schema, capability | `SourcePreparerRegistry` |
| `mappers` | Mapper ID/version, trusted implementation ID, unit/input/emits 계약 | `MapperRegistry` |
| `packs` | Pack/Claim/Role/required/allowed binding/emission | `PackRegistry` |
| `profiles` | Pack/Claim을 source column/constant/entity에 연결, 승인 metadata | `ProfileRegistry` |
| `sources` | base relation, event/group/time/cursor, preparer/join rule/mapper/profile ID | `SourcePlanRegistry` |

Registry는 section의 immutable compiled view다. 도메인 등록값을 Python builtin과 병합하지
않는다. Python에는 schema/validator/compiler와 trusted preparer implementation만 둔다.

`vocabulary.<predicate>.object.qualifiers`는 `required`와 `optional`의 닫힌 목록을 소유한다.
Pack emission은 required qualifier를 모두 제공하고 두 목록 밖의 qualifier를 만들 수 없다.
Role의 값 domain을 닫아야 할 때는 `kind: "symbolic"`과 정렬·중복 없는
`allowed_values`를 함께 선언한다. Binding의 constant가 이 목록 밖이면 compile 전에 거절한다.

### Section 간 참조

```text
sources.profile_id                                  → profiles
sources.driver.preparation.preparer_id              → source_preparers
sources.driver.mapper_id                            → mappers
sources.driver.preparation.inherit_virtual_join_rules → catalog/virtual_joins.json
profiles.use             → packs/claim
profiles entity binding  → entities
packs emission predicate → vocabulary
mappers.emits            → packs/claim
```

한 파일이라도 같은 key/Role/payload를 section마다 복사하지 않고 ID로 연결한다.

## 5. `catalog/tables.json`

현행 `table_config.json`의 후계다.

- 실제 relation/column/type/key만 선언한다.
- cursor identity/order/watermark는 physical column만 사용한다.
- virtual-only/preparer output을 물리 column으로 등록하지 않는다.
- Entity key와 physical column 연결은 Profile이 소유한다.

## 6. `catalog/virtual_joins.json`

현행 `virtual_join_rules.json`의 후계다.

```jsonc
{
  "schema_version": 1,
  "rules": {
    "dt_log_to_dt_inventory": {
      "left_table": "dt_log",
      "right_table": "dt_inventory",
      "join_key": [{"left": "dt_job_id", "right": "dt_job_id"}],
      "expose": ["dt_lot", "dt_slot", "dt_frame", "core_frame"],
      "join_cardinality": "one",
      "enabled": true
    }
  }
}
```

- 오른쪽 key의 승인된 UNIQUE 근거가 없으면 rule 전체 거절이다.
- UI는 collide column에 기존 absent-only를 적용한다.
- Ledger preparer는 같은 verified descriptor를 쓰되 raw/joined 값을 분리 보존한다.
- `unresolved_label`은 UI 표시값이지 Entity identity가 아니다.
- `ledger_config.json`이 relation/key/expose/folding을 복사하면 거절한다.

## 7. `dataflows/*.json`

`chains.json`은 실행 연결, `enrichments.json`은 결측과 행동을 소유한다.

- missing right row 도착 후 blocked event 재시도
- 성공 후 right row 수정 시 dependency replay/worklist
- `target_mapping_missing|target_mapping_ambiguous` action

Pack compiler에 replay/supersession/deletion detection을 넣지 않는다.

## 8. Legacy 이동표

| 현재 | 목표 |
|---|---|
| `server/config/table_config.json` | `ontology/catalog/tables.json` |
| `server/config/virtual_join_rules.json` | `ontology/catalog/virtual_joins.json` |
| `ledger_config.json` + `ledger_vocabulary.json` + Profile/Pack/Entity builtin | `ontology/ledger_config.json`의 7개 section |
| preparer/mapper registry dict | `ledger_config.json.source_preparers/mappers` + trusted implementation code |
| `chain_rules.json` | `ontology/dataflows/chains.json` |
| `enrichment_rules.json` | `ontology/dataflows/enrichments.json` |

전환 기간에는 새 정본과 legacy를 동시에 편집하지 않는다. snapshot parity 승인 후 구 파일을
`_archive`로 이동한다.

## 9. 수락 기준

- config root 하나, manifest 진입점 하나
- Pack/Profile/Registry authoring file은 `ledger_config.json` 하나
- Registry 등록값 config-only
- manifest 밖 자동 로드 0
- join 계약 중복 0
- source/table 이름별 compiler 조건문 0
- deterministic normalization/hash
- 정확한 file/section/path 오류
- legacy와 새 정본 동시 편집 0
