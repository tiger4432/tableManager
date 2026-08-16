# Source Ontology Profile 2단계 — 수락 보완 진행 중

> **Date:** 2026-08-16 | **Area:** Canonical Ledger / Ontology Setup
> **status:** `IN_PROGRESS`
> **approval:** `NOT_APPROVED`
> **remaining_acceptance:** 사용자 재승인

## 배경

새 소스를 원장에 연결하려면 운영자가 `ledger_config`, 번역기 구현, vocabulary의 내부
계약을 함께 이해해야 했다. 설정 단순화 계획의 2단계로, 이 내부 구조를 직접 노출하지
않는 상위 `SourceOntologyProfile` 스키마를 작성 중이다. 이 기록은 구현 이력이지 승인
기록이 아니며, 사용자 재승인 전에는 완료 상태로 해석하지 않는다.

## 변경

- `server/ledger/source_profile.py`
  - `profile_version/source/packs/mappings` Profile 모델
  - `PackRegistry → PackDescriptor → ClaimDescriptor → RoleDescriptor`
  - `column`, `constant`, `declared_lookup` binding kind registry
  - `mapping_id` 필수·공백·중복 검사
  - 정확한 mapping/role 경로와 전용 오류 code
  - Binding 설정 출처(`user_declared|system_suggested|imported`)와 Mapping 승인 상태
    (`pending|approved|rejected`) 분리 및 결정적 보존
  - `system_suggested`의 `suggestion_reason` 필수 검사와 승인 상태가 Claim class에
    영향을 주지 않는 경계
  - `RoleDescriptor.kind`와 `allowed_binding_kinds` 이중 검사, Pack 등록 symbolic
    constant에 의한 `source_position` fail-closed 검증
  - 입력 순서와 무관한 결정적 JSON 직렬화
  - canonical 진입점은 `profile_version/source/packs/mappings` 네 필드만 수용하고 구형
    6필드 draft는 명시적 `validate_legacy_profile()`로 격리
  - 구조 검증과 실행 준비 판정을 분리한 순수 readiness gate
    (`binding_not_approved`; 중첩 `declared_lookup.key` 포함)
  - 기존 수동 `sources` 옆 canonical `profiles` 선택 섹션 검증
- `server/ledger/source_profile_builtins.py`
  - `lot-lineage@1`, `transfer@1` Pack 등록 데이터
  - `transfer/movement` 등 Claim과 Role 계약
- `server/tests/test_source_ontology_profile.py`
  - Pack/Claim/Role/Binding과 기존 loader 병행 수락 테스트

대표 Profile 구조:

```json
{
  "profile_version": 1,
  "source": "source_rows",
  "packs": ["transfer@1"],
  "mappings": [{
    "mapping_id": "movement",
    "use": "transfer/movement",
    "bind": {
      "subject": {
        "kind": "column",
        "column": "ITEM_ID",
        "binding_origin": "system_suggested",
        "approval_status": "approved",
        "suggestion_reason": "matched the declared source identity"
      },
      "from": {
        "kind": "constant",
        "value": "source_position",
        "binding_origin": "user_declared",
        "approval_status": "approved"
      },
      "to": {
        "kind": "column",
        "column": "DESTINATION",
        "binding_origin": "user_declared",
        "approval_status": "approved"
      },
      "occurred_at": {
        "kind": "column",
        "column": "EVENT_TIME",
        "binding_origin": "user_declared",
        "approval_status": "approved"
      }
    }
  }]
}
```

`use`는 `pack_id/claim_id`이고 `bind`는 그 Claim이 등록한 Role만 받을 수 있다.
Binding 승인 상태는 Profile 설정에 대한 metadata이며 원장 Claim의 `confirmed`·`pin`
등 epistemic class와 별개다. `declared_lookup`은 2단계에서 구조만 검사하고 실행하지 않는다.
구조적으로 유효한 초안도 모든 최상위·중첩 Binding이 `approved`가 아니면 실행 준비 상태가
아니다. readiness gate는 compiler나 translator를 호출하지 않고 이 상태만 판정한다.

## 경계

- 기존 `ledger.config.load()`와 API는 바꾸지 않았다.
- Profile compiler, source adapter, translator 실행은 구현하지 않았다.
- DB import·연결·migration·write를 추가하지 않았다.
- predicate signature, atom, Claim class 번호, translator/derivation 내부명, canonical key,
  provenance envelope는 공개 Profile 및 metadata에 포함하지 않았다.

## 검증

```text
conda run -n assy_manager python -m pytest \
  server/tests/test_source_ontology_profile.py -q -p no:cacheprovider

56 passed
```

`test_ledger_source_contract.py` 9개를 함께 실행한 집중 결과는 **65 passed**다.

작업 전후 ledger 결과는 모두 **7 failed, 396 passed, 119 skipped**로 신규 실패는 0이다.
실패 5개는 폐기된
`WaferLeg` entity 계약, 2개는 현재 live config에 없는 `void_obs`·`dt_log`를 기대한다.
skip 117개는 격리 PostgreSQL URL 부재, 2개는 명시적 cost probe다. 실행할 수 없던
테스트를 통과로 세지 않았다.

3단계 compiler/runtime adapter는 시작하지 않았다. 2단계 재승인 뒤에만 검토한다.
