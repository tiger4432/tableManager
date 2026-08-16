# Canonical Profile 경계 및 Readiness Gate 보완

- 날짜: 2026-08-17
- 단계: 2단계 Claim Mapping Profile
- 상태: `IN_PROGRESS`
- 승인: `NOT_APPROVED`

## 변경 목적

정본 `SourceOntologyProfile`과 구형 6필드 draft의 수용 경계를 분리하고, 구조적으로
유효한 Profile이 실제 실행 가능한지 순수 함수로 판정할 수 있게 했다.

## 변경 내용

- canonical 진입점은 `profile_version/source/packs/mappings` 네 필드만 수용한다.
- 구형 draft는 명시적 `validate_legacy_profile()`에서만 검증한다.
- `validate_profile()`과 `validate_profile_errors()`의 수락·거절 판정을 일치시켰다.
- 모든 최상위 및 중첩 Binding의 `approval_status=approved`를 요구하는 readiness gate를
  추가했다.
- 미승인 Binding은 `binding_not_approved`와 결정적인 Profile 경로로 보고한다.
- compiler, translator, lookup 실행, atom 생성, DB migration/write는 추가하지 않았다.

## 검증

- Profile 집중 테스트: `56 passed`
- 원장 소스 계약 포함 집중 테스트: `65 passed`
- 전체 ledger 테스트: `7 failed, 396 passed, 119 skipped`
- 동일 환경의 보완 전 결과와 비교한 신규 실패: `0`

기존 7개 실패와 119개 skip은 이번 Profile 보완 전후에 동일하다. 2단계는 아직 사용자
재검수 대기 상태이며 3단계는 시작하지 않았다.
