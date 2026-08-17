# Ledger v2 Stage 3 closed issuer registry

## 상태

- 단계: `STAGE_3_IN_REVIEW`
- 승인: `NOT_APPROVED`
- Stage 4: 미착수

## 현상

4차 검토 중 compiler가 확인하는 발급 identity 저장소가
`verified_join_contract._ISSUED_DESCRIPTORS` module attribute로 노출돼 있음을 확인했다. 외부
코드가 발급되지 않은 객체를 이 집합에 직접 추가할 수 있어 정본의 닫힌 발급 경계와 달랐다.

## 수정

- 발급 WeakSet, issuer class, bind token을 하나의 closure 내부 상태로 이동했다.
- module namespace에는 mutation handle이나 등록 함수가 남지 않는다.
- compiler에는 `is_physically_verified_descriptor()` 읽기 전용 predicate만 노출한다.
- 기존 constructor·`_issue`·caller guard·미발급 identity 거절 계약은 유지한다.

## 검증

- Registry: `46 passed`
- Ledger Bundle/Registry/virtual join 영향군: `219 passed, 1 skipped`
- 동결 mapper: `29 passed`
- 전체 서버 suite: 사용자 지시에 따라 미실행
- DB read/write/migration: `0`

audit 승인 전 상태는 `IN_REVIEW / NOT_APPROVED`다.
