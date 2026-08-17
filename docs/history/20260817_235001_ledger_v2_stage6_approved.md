# Ledger V2 Stage 6 승인

## 상태

- Stage 6: `APPROVED`
- 승인 구현: `b98f0c3804f5bdfc6653670da571f8fef0e9e129`
- Stage 7: `IN_PROGRESS / NOT_APPROVED`

## 독립 검수

Audit은 exact commit archive에서 preview/execute 공통 경로, 기존 gate/store/cursor transaction,
lot_event Role mapper, objectless register, first-sight filtering, incomplete 신호와 shadow comparator를
검증했다. 직접 영향군 결과는 `375 passed, 9 skipped`다. skip은 안전한 PG URL 미설정 8건과
기존 Windows symlink 권한 1건이다.

Main은 별도 임시 PostgreSQL에서 `8 passed`를 얻고 정확한 임시 DB를 삭제했다. Audit 환경은
안전한 PG URL이 없어 이를 재실행하지 않았으므로 두 결과를 합쳐 Audit 실행으로 표현하지 않는다.

## 다음 경계

Stage 7은 config root/manifest, source selector, validation·dry-run 같은 비파괴 전환부터 진행한다.
`lot_event`만 cutover 후보이고 DT/observation은 NO-GO다. 운영 Ledger/cursor reset, 데이터 삭제,
legacy 이동·삭제는 정확한 대상·백업·복구 절차에 대한 별도 사용자 승인 전에는 실행하지 않는다.
