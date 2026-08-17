# Ledger v2 Stage 6 — shadow parity와 PostgreSQL E2E

## 현상

Stage 5까지는 완성 EventFrame을 Pack compiler에 넣을 수 있었지만 실제 gate/store/cursor
transaction과 legacy 의미 비교가 연결되지 않았다. 특히 lot_event는 두 row가 한 사건인
split/merge, object 없는 register, 이미 등록된 Entity의 first-sight memo, 한쪽 row만 도착한
incomplete 상태 때문에 단순 한 행 mapper로 전환할 수 없었다.

## 근본 원인

1. Vocabulary/Pack object kind가 objectless `register`를 표현하지 못했다.
2. source event identity/group을 physical column으로만 제한하면 pair row에서 공통 사건 ID를
   만들 수 없었다.
3. Mapper에 등록 DB 상태를 넣으면 Stage 4 capability 경계를 깨고, 상태가 없으면 register가
   매 event마다 중복됐다.
4. dry-run과 execute가 공유하는 실행 adapter 및 snapshot cursor version guard가 없었다.
5. parity 비교가 candidate 수와 refusal/incomplete outcome을 닫힌 계약으로 세지 않았다.

## 수정

- `none` object 계약을 Bundle→Registry→Pack compiler에 추가하고 물리 Ledger에는 기존 NULL
  object로 컴파일했다.
- SourcePreparer output이 event identity/group을 제공할 수 있게 하되 cursor/order/time은 계속
  physical column으로 제한했다.
- `LotEventSourcePreparer`와 `LotEventRoleMapper`를 추가했다. mapper는 `interpret_unit()`에서
  RoleEmission만 반환하며 Atom/payload/DB/cursor를 만들지 않는다.
- 기존 `LedgerStore.existing_registrations()`의 batched snapshot을 runtime 입력으로 요구하고,
  누락은 fail-closed, explicit empty는 첫 실행, replay/배치 중복은 gate 전에 제거했다.
- pair 한쪽만 온 사건은 보이는 Claim을 유지하고 standard incomplete attr을 기존 cursor 통계로
  전달했다.
- 동일 compiler를 쓰는 preview/execute adapter, compiled gate 경계, cursor snapshot version
  rollback, deterministic shadow comparator를 추가했다.

## 반례

- pending/rejected nested Binding, join 0건/다건, gate refusal → Atom 0/cursor 0
- snapshot translator version 불일치 → Atom insert/cursor update 동시 rollback
- `known_registrations=None`인 register source → `registration_context_required`
- 동일 Lot/Wafer가 두 event에 반복 → register는 배치에서 한 번만 후보
- split/merge pair row 한쪽만 도착 → Claim 기록 + incomplete 1
- slots/wafers 길이 불일치 → candidate 반환 전 구조화 거절

## 검증

- lot_event legacy↔v2 split 10, merge 11, track-in 5 Claim: 정규화 equal 26,
  설명 없는 차이 0.
- Ledger 직접 영향군: `370 passed, 9 skipped`.
- skip: PG 미선언 8, 기존 Windows symlink 권한 1.
- 별도 안전한 임시 PostgreSQL: `8 passed`; 정확한 임시 DB를 종료 시 DROP.
- 전체 server suite는 사용자 지시에 따라 실행하지 않았다.
- 운영 config, migration, production DB write/reset, legacy 삭제: 0.

## 상태

Stage 6은 `IN_REVIEW / NOT_APPROVED`다. exact commit을 독립 Audit 세션에 제출하며 Stage 7은
Audit 승인 전 시작하지 않는다. source별 판정은 lot_event GO, DT/observation은 실제 parity와
운영 replay 연결 전까지 NO-GO다.
