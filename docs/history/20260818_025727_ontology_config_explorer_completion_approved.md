# Ontology Config Explorer 전체 완료 승인

## 상태

- 제품 상태: `ONTOLOGY_CONFIG_EXPLORER_COMPLETE / APPROVED`
- 승인 구현: `2d1ad863106fc228566cab1a386265957f5c3587`
- 지정 Audit task: `01a00f3f-4249-7bf0-ab96-6d32c27273fe`
- 병합: main fast-forward 완료

## 승인 경위

초기 전체 완료 후보 `18607142b1462fa7cb7e25f9ddb05f7cf8a84276`은 dirty editor
history 유실, file-backed sample 계보 단절, reference edge `modified` 미구현으로
REJECT됐다. 후속 커밋은 세 반례를 최소 범위로 닫았다.

1. 저장 후 다시 편집한 버퍼·dirty·cursor와 draft identity를 history checkpoint에 보존하고,
   active context와 revision이 정확히 같을 때만 복원한다.
2. sample 계보를 `CoreDie@1 → DTDie@1 → BondComponent@1 → FinalChip@1`로 연결한다.
3. reference edge의 논리 위치와 비교 내용을 분리해 target/status 변경을 `modified`로 보존한다.

## 독립 Audit 근거

- backend 직접 범위: `165 passed`
- Explorer harness: `35 assertions / 0 failed`
- client contracts: `7 passed`
- production build: Vite `107 modules`, pass
- 실제 UI save → reedit → keep → 이동 → back → forward → back에서 editor bytes와 cursor 보존
- full server suite와 PostgreSQL E2E는 사용자 지시에 따라 미실행

Audit은 exact commit `2d1ad863106fc228566cab1a386265957f5c3587`을 `APPROVE`했다.
운영 config/DB write, reset/replay, migration, legacy 이동·삭제 금지는 별도 사용자 승인 전까지
유지한다.
