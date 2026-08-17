# 3단계 — Registry와 교차 계약 검증

> 구현 상태: `IN_REVIEW` · 승인: `NOT_APPROVED` · 2026-08-17
> 구현 근거: [`STAGE_3_ACCEPTANCE_EVIDENCE.md`](./STAGE_3_ACCEPTANCE_EVIDENCE.md)

## 목표

Config directory의 각 section을 immutable Registry로 컴파일하고 서로의 계약을 시작 시점에
교차 검증한다. 아직 source row를 읽거나 Claim을 생성하지 않는다.

## Registry 구조

```text
LedgerSetupSnapshot
├─ VocabularyRegistry
│  └─ PredicateDescriptor
├─ EntityTypeRegistry
│  └─ EntityTypeDescriptor
├─ PackRegistry
│  └─ PackDescriptor → ClaimDescriptor → RoleDescriptor + EmissionDescriptor
├─ MapperRegistry
│  └─ MapperDescriptor → unit/input/emits + trusted implementation ID
└─ SourcePlanRegistry
   └─ SourceDriverPlan
      + SourcePreparationPlan
      + inherited VerifiedJoinDescriptor refs
      + SourceProfilePlan
```

Registry는 add-only, version keyed, sealable이고 snapshot 생성 뒤 변경 불가다.
Registry는 config의 compiled view다. `VocabularyRegistry`, `EntityTypeRegistry`,
`PackRegistry`, `SourcePlanRegistry`, `SourcePreparerRegistry`, `MapperRegistry`의 도메인
등록값을 코드 builtin과 합치지 않는다. 코드는 descriptor schema, validator, generic compiler,
닫힌 implementation interface와 trusted Mapper class만 소유한다.

## 핵심 교차 검증

### Pack ↔ Vocabulary

- emission predicate가 존재하고 active인지
- subject Role의 entity type이 predicate 허용 subject인지
- object kind가 일치하는지
- Vocabulary required payload field가 emission에 전부 있는지
- emission field가 선언 Role 또는 닫힌 literal만 참조하는지
- optional Role은 `$role?`로만 생략 가능한지

현재 v1은 object payload 중 `qualifiers`를 `required`/`optional` 닫힌 목록으로 선언한다.
Pack emission은 required qualifier를 빠짐없이 제공하고 목록 밖 qualifier를 만들 수 없다.

### Role ↔ Entity

- entity Role 값은 등록 Entity type과 정확한 key를 가져야 함
- symbolic constant는 Role에 등록된 값만 허용
- transfer Claim의 subject와 target은 Vocabulary가 허용한 stage-local Entity type이어야 함
- 좌표는 Entity key이며 Position 구조나 좌표 payload를 별도로 허용하지 않음

`kind=symbolic` Role은 정렬·중복 없는 `allowed_values`를 필수로 소유한다. 다른 Role의
constant는 기존 deterministic JSON 계약을 유지하며 symbolic domain으로 오인하지 않는다.

### Source ↔ Profile/Driver

- source relation과 Profile source 동일
- binding column이 source preparer의 선언된 EventFrame output schema에서 옴
- event identity/group/order/cursor column 존재
- cursor가 결정적 전순서를 형성할 근거가 있음
- Profile Pack/Claim/Role reference 존재
- cursor column은 base relation의 물리 column이어야 하며 virtual-only column 금지
- source preparer ID/version/output schema가 등록돼야 함
- mapper input contract가 source preparer의 EventFrame output schema로 충족됨
- mapper `emits`가 Profile 승인 mapping과 Pack Claim의 부분집합임
- mapper ID/version이 trusted implementation ID와 연결되며 module/function/path가 없음

### Source Preparation ↔ Verified Virtual Join

- `inherit_virtual_join_rules`의 모든 ID가 존재·enabled·verified 상태인지
- rule의 `left_table`이 source base relation과 같은지
- join left key가 cursor SELECT 물리 column에 포함되는지
- right join key와 expose column이 table config에 존재하는지
- UNIQUE/notation-folding 검증은 기존 virtual join verifier의 결과만 소비하는지
- source preparer가 relation/key/expose/folding을 다시 선언하지 않는지
- EventFrame output schema가 Profile binding column을 전부 제공하는지
- EventFrame output schema가 Mapper input contract를 전부 제공하는지
- Mapper output Claim/Role 계약이 Pack/Profile과 닫혀 있는지
- UI absent-only/unresolved-label 정책이 identity 결정에 섞이지 않는지

## Snapshot

결과는 content hash를 가진 immutable `LedgerSetupSnapshot`이다.

```text
setup_version
bundle_canonical_json
bundle_sha256
canonical_content_json
snapshot_sha256
compiler_contract_version
registries
source_plans
readiness
```

같은 snapshot hash는 dry-run/execute cursor execution version에 사용한다. hash 계산에
파일 경로, dict 삽입 순서, Python object id, 현재 시각을 넣지 않는다.

## 수락 테스트

- Pack/Vocabulary required field 불일치 거절
- stage-local Entity에 잘못된 identity key 형상 거절
- Entity identity key 불일치 거절
- source preparer 미등록/output schema 불일치 거절
- mapper 미등록/input/emits/implementation 불일치 거절
- inherited join rule missing/disabled/rejected/left-table mismatch 거절
- join 계약 중복 선언 거절
- source cursor 비결정성 거절
- 새 Entity/Pack 등록 시 compiler core 수정 불필요
- Bundle/Registry에 lookup section/kind가 없음
- vocabulary/entity/pack/source/preparer/mapper 등록 항목이 config에서만 유래함
- 새 config entry 등록 시 Registry/compiler core 수정 불필요
- UI executor와 source preparer가 같은 immutable `VerifiedJoinDescriptor`를 소비
- 여러 오류의 순서 결정성
- 동일 Bundle snapshot hash 결정성
- Registry compiler의 DB connection/read/write 0

완료 후 멈추고 3단계 승인을 기다린다.

## 현재 구현 상태

`server/ledger/setup_registry.py`가 승인된 `LedgerSetupBundle`을 config-only descriptor와 sealed
Registry로 컴파일한다. `VocabularyRegistry`, `EntityTypeRegistry`, `SourcePreparerRegistry`,
`MapperRegistry`, `PackRegistry`, `ProfileRegistry`, `VerifiedJoinRegistry`,
`SourcePlanRegistry`를 한 `LedgerSetupSnapshot`에 봉인한다. `bundle_sha256`은 입력 Bundle을,
`snapshot_sha256`은 compiler contract version, compiled Registry/Source Plan, readiness,
선택 implementation version, 물리 join 검증 결과, chain/enrichment 선언을 묶는다. 파일 경로,
dict 삽입 순서, 현재 시각, Python object identity는 두 해시에 들어가지 않는다.

Source Plan은 같은 Snapshot의 `SourcePreparerDescriptor`, `MapperDescriptor`,
`ProfileDescriptor`, `VerifiedJoinDescriptor` 객체를 직접 참조한다. trusted implementation은
module/function/path가 아니라 호출자가 제공한 닫힌 `(implementation_id, version)` 집합과만
대조한다. config의 모든 사용·미사용 preparer/mapper가 이 대조를 통과해야 한다.

Catalog 선언은 `verified=True`가 될 수 없다. 기존
`virtual_join_config.load_verified_rules()`가 PostgreSQL UNIQUE index를 물리 검증한 뒤 만든
neutral immutable `VerifiedJoinDescriptor`만 compiler에 외부 주입할 수 있다. 현행 UI executor와
Source Plan은 같은 descriptor type과 검증 결과를 소비하며, Source Plan은 Registry의 같은
descriptor 인스턴스를 복사 없이 참조한다. `VerifiedJoinDescriptor`에는 raw mapping을 승격하는
public constructor/factory가 없다. 생성 capability는 `virtual_join_config`의 private issuer가
소유하고 issuer 자체도 `load_verified_rules()` 호출 위치 밖에서는 발급을 거절한다. 물리 검증
성공 분기에서만 descriptor를 만든다. 따라서 catalog 선언에
임의 `unique_index` 문자열을 붙여 compiler-ready descriptor로 바꿀 수 없다. compiler 자체의
DB import/read는 0이다. compiler는 단순 `isinstance`가 아니라 physical verifier가 발급한
object identity인지도 확인한다. direct constructor, 무인자 constructor, 과거 `_issue` 진입점,
`object.__new__`로 만든 미발급 인스턴스는 모두 compiler-ready proof가 될 수 없다. 발급 identity
집합·issuer class·bind token은 module attribute가 아니라 closure 내부 상태이며 외부 등록
함수를 제공하지 않는다.

컴파일 진입점은 Bundle 구조·교차 계약을 다시 검증하고 모든 중첩 Binding의 readiness를 먼저
강제한다. source row, pandas, mapper 실행, Claim/LedgerFrame 생성, DB read/write, cursor,
gate/store 연결은 구현하지 않았다. 4단계는 3단계 재승인 전 시작하지 않는다.
