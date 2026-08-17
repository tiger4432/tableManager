# Ledger v2 Stage 3 physical proof 경계 봉인

## 상태

- 단계: `STAGE_3_IN_REVIEW`
- 승인: `NOT_APPROVED`
- Stage 4: 미착수

## 현상과 근본 원인

2차 독립 audit가 catalog mapping에 임의 `unique_index` 문자열을 넣고 공개
`VerifiedJoinDescriptor.from_verified_rule()`을 호출해, DB probe 없이 ready snapshot을 만드는
반례를 재현했다. constructor만 닫고 raw mapping public factory를 남겨 둔 것이 근본 원인이었다.

## 수정

- raw mapping public factory를 제거했다.
- descriptor issuance를 `virtual_join_config`가 소유하는 private capability로 제한하고,
  loader 호출 위치 밖의 직접 발급도 거절했다.
- 정상 테스트 descriptor도 production `load_verified_rules()` 경로를 사용하고, DB probe만
  deterministic stub으로 대체한다.
- 가짜 index raw mapping은 `unverified_join`과 `invalid_verified_join` 두 구조화 오류로 거절한다.
- compiler/runtime/DB/cursor/mapper 실행 경로는 변경하지 않았다.

## 검증

- Registry 단독: `43 passed`
- Ledger Bundle/Registry/virtual join 영향군: `216 passed, 1 skipped`
- 동결 LedgerFrame mapper: `29 passed`
- 전체 서버 suite: 사용자 지시에 따라 이번 fix에서 재실행하지 않음
- DB read/write/migration: `0`

audit 승인 전 상태는 계속 `IN_REVIEW / NOT_APPROVED`다.
