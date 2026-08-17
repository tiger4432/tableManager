# Ledger v2 Stage 3 issuer identity gate

## 상태

- 단계: `STAGE_3_IN_REVIEW`
- 승인: `NOT_APPROVED`
- Stage 4: 미착수

## 현상

3차 audit는 private issuer의 직접 `issue()`는 막혔지만,
`VerifiedJoinDescriptor._issue(raw, issuer=virtual_join_config._VERIFIED_JOIN_ISSUER)`가 caller
검증을 우회하는 반례를 재현했다. 무인자 constructor도 `_data` 없는 인스턴스를 만들었다.

## 수정

- `_issue`는 모든 호출을 `TypeError`로 거절하고 실제 생성에 사용하지 않는다.
- 무인자·인자 constructor를 모두 명시적으로 거절한다.
- 실제 descriptor 생성은 caller 검증을 통과한 issuer 내부로 이동했다.
- compiler는 `isinstance` 대신 physical verifier의 발급 object identity까지 확인한다.
- `object.__new__`로 만든 미발급 인스턴스도 `invalid_verified_join`으로 거절한다.

## 검증

- Registry: `45 passed`
- Ledger Bundle/Registry/virtual join 영향군: `218 passed, 1 skipped`
- 동결 mapper: `29 passed`
- 전체 서버 suite: 사용자 지시에 따라 미실행
- DB read/write/migration: `0`

audit 승인 전 상태는 `IN_REVIEW / NOT_APPROVED`다.
