# Ledger v2 3단계 수락 근거

> 상태: `IN_REVIEW` · 승인: `NOT_APPROVED` · 2026-08-17

## 변경 파일과 역할

| 파일 | 역할 |
|---|---|
| `server/ledger/setup_registry.py` | config-only descriptor, sealed Registry, trusted implementation 대조, immutable snapshot |
| `server/ledger/setup_bundle.py` | validator와 compiler가 공유하는 effective Role binding kind 해석 함수 |
| `server/tests/test_ledger_setup_registry.py` | 3단계 Registry/snapshot/금지 경계 수락 테스트 |

운영 manifest/config, runtime loader, mapper/translator/cursor/store, DB schema는 수정하지 않았다.

## 최종 Registry 계약

```text
LedgerSetupSnapshot
├─ VocabularyRegistry       → PredicateDescriptor
├─ EntityTypeRegistry       → EntityTypeDescriptor
├─ SourcePreparerRegistry   → SourcePreparerDescriptor
├─ MapperRegistry           → MapperDescriptor
├─ PackRegistry             → PackDescriptor → ClaimDescriptor → RoleDescriptor + EmissionDescriptor
├─ ProfileRegistry          → ProfileDescriptor → ProfileMappingDescriptor
├─ VerifiedJoinRegistry     → VerifiedJoinDescriptor
└─ SourcePlanRegistry       → SourcePlan → SourceDriverPlan → SourcePreparationPlan
```

Registry 구축기는 add-only이고 한 번 seal한 뒤에는 공개 Registry의 항목·descriptor·중첩
mapping을 바꿀 수 없다. 모든 descriptor는 `config_path`를 보존하며 도메인 등록값은 오직
`LedgerSetupBundle` section에서 온다. Python은 descriptor schema, compiler, trusted
implementation ID/version 인터페이스만 소유한다.

## 실제 normalized snapshot 예

```json
{
  "setup_version": 2,
  "sha256": "b843cc9c3662d48a377a289818570d0ad66f951e574cf104cd3809654ffb090d",
  "readiness": "ready",
  "registry_ids": {
    "vocabulary": ["moves_to@1"],
    "entities": ["InputEntity@1", "OutputEntity@1"],
    "source_preparers": ["prepare-input@1"],
    "mappers": ["map-transition@1"],
    "packs": ["movement@1"],
    "profiles": ["input-transition@1"],
    "verified_joins": ["input_to_reference"],
    "sources": ["input_rows"]
  },
  "claim": {
    "claim_id": "transition",
    "predicate_id": "moves_to@1",
    "subject_role": "subject",
    "object_role": "target",
    "occurred_at_role": "occurred_at"
  },
  "source_plan": {
    "relation": "input_rows",
    "preparer_id": "prepare-input@1",
    "mapper_id": "map-transition@1",
    "profile_id": "input-transition@1",
    "verified_join_rule_ids": ["input_to_reference"]
  }
}
```

위 요약은 실제 descriptor의 읽기용 축약이다. `ProfileMappingDescriptor.bindings`에는
`binding_origin`, `approval_status`, `suggestion_reason`가 삭제되지 않고 재귀 불변 구조로
보존된다. Binding 승인은 Claim epistemic class를 만들거나 변경하지 않는다.

## 실제 compile 오류 계약

```json
{"code":"untrusted_implementation","path":"bundle.mappers.map-transition@1.implementation_id","message":"mapper implementation 'map-transition-role' version 1 is not trusted"}
{"code":"unsupported_implementation_version","path":"bundle.mappers.map-transition@1.implementation_version","message":"mapper implementation 'map-transition-role' version 1 is not trusted"}
{"code":"binding_not_approved","path":"bundle.profiles.input-transition@1.mappings[0].bind.subject.keys.input_id.approval_status","message":"binding approval_status is 'pending', expected 'approved'"}
{"code":"invalid_driver","path":"bundle.sources.input_rows.driver.preparation.inherit_virtual_join_rules[0]","message":"join rule 'input_to_reference' is disabled"}
```

오류는 `(path, code, message)` 순으로 결정적이다. 직접 생성한 미검증
`LedgerSetupBundle`도 compiler 진입점에서 구조·교차 검증을 다시 통과하므로 fail-closed다.

## 수락 근거

- Pack → Claim → Role/Emission과 Vocabulary/Entity의 v1 닫힌 계약을 2단계
  validator와 공유한다. v1에 존재하지 않는 임의 payload-field 스키마와
  symbolic-constant domain을 Registry가 임의로 만들지 않았다.
- Role effective `allowed_binding_kinds`는 `setup_bundle.role_binding_kinds()` 한 함수가
  validator와 compiler 양쪽에 제공하므로 의미 사본이 없다.
- Profile이 전혀 선택하지 않은 Vocabulary/Entity/Pack/Preparer/Mapper도 registry에 들어가며
  validator/trusted implementation 대조를 통과해야 한다.
- 새 Entity/Predicate/Pack config entry는 compiler core 수정 없이 snapshot에 등록된다.
- source/table/column을 전부 바꾼 동일 Pack도 같은 Pack descriptor로 컴파일된다.
- Source Plan은 Snapshot Registry의 단일 `VerifiedJoinDescriptor` 객체를 복사 없이 참조한다.
  `verification_basis=catalog_declared_unique`는 DB 실측이 아니라 선언 검증임을 명시한다.
- inherited join의 missing/disabled/left mismatch/UNIQUE 증명 실패와 source 쪽 join 계약 재선언을
  snapshot 생성 전에 거절한다.
- inherited join의 left key는 선택 Preparer `input_columns`에 전부 존재해야 하며,
  fold는 닫힌 notation rule vocabulary·boolean toggle·구현 상태를 통과해야 한다.
- 동일 ID의 복수 version을 별도로 조회할 수 있고, builder는 seal 후 add/재-seal을
  구조적으로 거절한다. 사용되지 않아도 trusted인 Preparer/Mapper는 Registry에 보존된다.
- Profile pending/rejected와 중첩 Entity key Binding은 snapshot 생성 전에 차단된다.
- Snapshot canonical hash에는 전체 Bundle가 들어가므로 virtual join과 chain/enrichment 변경이
  모두 hash를 바꾼다. config root 경로와 JSON key 삽입 순서는 hash에 들어가지 않는다.
- `setup_registry.py`는 DB/pandas/runtime 모듈을 import하지 않고 execute/read/write/commit/cursor
  capability를 제공하지 않는다.

## 검증 결과

- 3단계 전용: `35 passed`
- 2+3단계 계약: `128 passed, 1 skipped`
- 동결 mapper 회귀: `29 passed`
- 전체 서버: `4040 passed, 143 failed, 23 errors, 204 skipped, 1 xfailed`
- 전체 실패/오류에는 `test_ledger_setup_bundle.py`와 `test_ledger_setup_registry.py`가 없고,
  새 모듈은 runtime에서 import되지 않는다. 주요 기존 실패군은 현재 config에 `void_obs` 등
  선언이 없는 fixture, live/sample config 불일치, map alignment, audit/API/launcher 환경이다.
- 같은 환경의 `main` 전체 스위트를 별도 재실행하지 않았으므로 전체 143건에 대해
  baseline 대비 신규 실패 0이라고 주장하지 않는다. 변경 도달 범위인 Bundle/Registry와 동결
  mapper 기준 신규 실패는 `0`이다.
- skip 1건은 Windows symlink 생성 권한 부재다. 전체 204 skip은 외부 서비스/선택 fixture와
  현재 config 조건을 포함하며 Stage 3에서 강제 실행하지 않았다.
- 수정 Python `py_compile`: 통과
- DB connection/read/write/migration: `0`

## 독립 audit

`ledger_v2_stage2_audit` 세션이 최종 공유 worktree를 read-only로 재검토했고
`APPROVE`를 판정했다. 감사가 발견한 inherited join input 누락, fold 문법·금지 키,
복수 version/seal/trusted-but-unused 테스트 공백과 대소문자 중복 오류를 모두 닫은 후의
판정이다. 이 `APPROVE`는 3단계 구현 diff의 검수 결과이며 사용자의 3단계
제품 승인을 대체하지 않는다.

## 범위 밖과 다음 단계

- source row/pandas EventFrame/RoleFrame/Pack compiler는 4단계 소유다.
- 기존 driver/cursor, source preparer의 실제 batch join, PostgreSQL E2E는 5·6단계 소유다.
- 현행 UI executor가 이 descriptor를 직접 소비하도록 전환하는 일은 runtime/cutover 범위다.
- 운영 config 생성·runtime cutover·legacy 삭제·DB reset은 하지 않았다.

자체 판정: 3단계의 pure Registry/snapshot 범위는 검수 가능하다. 전체 서버의 기존 config 기반
실패는 별도 기준선 없이는 회귀 없음으로 단언할 수 없다. 독립 audit 결과를 첨부한 뒤 사용자
승인을 기다리며, 승인 전 4단계를 시작하지 않는다.
