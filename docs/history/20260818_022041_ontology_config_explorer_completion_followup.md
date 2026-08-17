# Ontology Config Explorer 전체 계약 보완

## 현상

초기 Explorer는 compiled Registry 탐색과 기본 draft lifecycle을 제공했지만 사용자 pending
문서의 전체 완료 조건 가운데 Binding·SourcePlan, 세분화된 참조 오류, exact route history,
dirty 이동 3선택, normalized edge diff, explicit revise, activation consumer convergence,
file-backed transfer 예제와 반응형 증거가 빠져 있었다. 이전 `COMPLETE`는 이 넓은 계약에
대해서는 과한 표현이었다.

## 근본 원인

- graph node 범위를 Registry 상위 정의 중심으로 잡아 Profile Binding과 SourcePlan을 별도
  identity로 만들지 않았다.
- draft preview와 active가 보이는 상태는 있었으나, 변경·history·review 이후 수정 권한과
  persistent consumer 수렴을 하나의 닫힌 계약으로 묶지 않았다.
- 운영 config에 없는 DT/transfer 사례를 거짓으로 추가하지 않는 데 집중하면서, 별도
  file-backed sample로 production compiler 왕복을 증명하는 절반이 빠졌다.

## 수정

- `config_explorer.py`가 SourcePlan/Binding을 포함하고 wrong kind/version/signature/unresolved를
  leaf pointer와 함께 구분한다. node/edge normalized diff와 path context를 추가했다.
- service/router가 explicit `view_mode`와 `/revise`를 제공한다.
- draft store가 review history, stale/conflict 분리, immutable review, explicit revise,
  consumer convergence rollback을 시행한다.
- client 단일 state에 exact route/tab/mode/scroll/editor cursor/token history와 dirty 3선택을
  추가했다. hover/focus, keyboard, ACTIVE/DRAFT, change list, reviewed JSON read-only를 구현했다.
- 운영 manifest 밖 `server/config/sample/ontology/transfer_explorer/`로 Core→DT→Bonding→Final
  transfer와 DTJob/LotSlot/VerifiedJoin/SourcePlan을 production loader/compiler에 태웠다.

## 검증

- backend 직접 범위: `165 passed`
- Explorer harness: `29 assertions, 0 failed`
- client contracts `7/7`, clipboard convention pass, Vite 107-module production build pass
- 10,000-node/9,999-edge 성능·payload 상한 pass
- browser 1920×1080, 700×900, 320×800과 transfer 7 route, history, hover/keyboard,
  dirty 3선택, active/draft, review→revise/read-only 확인
- full server suite/PostgreSQL E2E는 사용자 지시에 따라 미실행

## 안전과 상태

운영 config/DB write, reset/replay, migration, legacy 이동·삭제는 수행하지 않았다. 사용자 소유
`task/ontology_config_explorer_pending.md`와 reference HTML도 수정하지 않았다. 전체 계약은
독립 Audit 전까지 `COMPLETION_IN_REVIEW / NOT_APPROVED`다.
