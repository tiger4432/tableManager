# Ledger v2 2단계 Setup Bundle

## 배경

1단계 승인 후 분산된 원장 설정을 `server/config/ontology/` 한 root에서 읽는 순수 authoring
경계를 구현했다. 현행 원장 runtime과 DB는 유지했다.

## 변경

- versioned `LedgerSetupBundle`과 strict manifest loader 추가
- 결정적 정규화/직렬화와 `code/path/message` 오류 계약 추가
- table/join/vocabulary/entity/preparer/mapper/pack/profile/source 교차 검증 추가
- Binding 승인 metadata 보존과 별도 readiness gate 추가
- Position/lookup/임의 코드 선언 차단
- 운영 config는 만들지 않고 authoring root 안내만 추가

## 검증

- 최초 2단계 전용: `43 passed, 1 skipped`
- 최초 Ledger 핵심 합산: `290 passed, 1 skipped`
- `py_compile`, `git diff --check` 통과
- DB migration/read/write, runtime/compiler/translator/cursor 변경 없음

2단계는 `IN_REVIEW/NOT_APPROVED`이며 3단계는 시작하지 않았다.
