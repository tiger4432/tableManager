# Ledger V2 설정 가이드 전면 재작성과 인수인계 정정

> **시각:** 2026-08-18 07:01 KST
> **범위:** documentation only
> **제품 상태:** Ledger V2 / Ontology Config Explorer `COMPLETE / APPROVED` 유지
> **문서 follow-up 상태:** `IN_REVIEW` — exact commit Audit 재검수 대기

## 현상

기존 `docs/guide/ONTOLOGY_LEDGER_SETUP.md`는 Ledger V2 승인 이전의 flat config,
source-kind translator, `declared_lookup`, migration/reset 절차를 현행 셋업처럼 설명했다.
사용자가 production manifest 6파일과 JSON 샘플을 보고 직접 새 Source를 설정하기에는
Pack/Profile/Preparer/Mapper, cursor 전순서, verified join, binding 승인 계약이 한 흐름으로
정리돼 있지 않았다.

직전 문서·인수인계 Audit은 별도로 두 불일치를 지적했다.

1. Explorer PostgreSQL E2E 미실행을 Evidence에는 정직하게 적었지만 task 완료 게이트에는
   PostgreSQL 테스트 통과로 표시했다.
2. 인수인계 문서는 Admin token을 항상 필수라고 단정했지만 실제 API는 환경변수 설정 여부에
   따른 두 상태 계약이다.

## 수정

- `ONTOLOGY_LEDGER_SETUP.md`를 Ledger V2 전용 17절 가이드로 전면 재작성했다.
- production `server/config/ontology/` 여섯 파일과
  `server/config/sample/ontology/transfer_explorer/`를 기준 샘플로 연결했다.
- manifest, physical catalog, virtual join, Vocabulary, Entity, Preparer, Mapper, Pack, Profile,
  Source, chain, enrichment의 필드와 용도를 실제 JSON으로 설명했다.
- 새 Source 작성 10단계, validation/preview/execute 구분, 오류 code/path/message,
  troubleshooting과 체크리스트를 추가했다.
- `declared_lookup`/Position/임의 실행식 대신 verified Source Preparer batch join을 쓰고,
  config가 trusted code를 발명할 수 없다는 경계를 명시했다.
- `LEDGER_GUIDE`의 legacy translator/reset 절차에 V2 전환 배너를 추가했다.
- 문서 지도, 소유권, 인수인계 읽기 순서를 새 가이드에 맞췄다.
- Explorer 직접 테스트와 사용자 지시로 미실행한 full/PG E2E를 분리해 기록했다.
- Admin 인증을 token 설정 시 전 Admin route header 필수 / 미설정 시 ordinary read 허용 가능,
  strict draft/write 503 fail-closed의 두 상태로 정정했다.

## 안전 경계

- server/client/runtime/config 코드 변경 없음
- DB read/write/migration 없음
- cursor reset/replay 없음
- legacy 파일 이동·삭제 없음
- 동시 작업 중인 `server/` dirty 변경은 stage/commit 대상에서 제외

## 검증

- Markdown 링크 대상 존재 확인
- 가이드가 참조하는 production/sample JSON 12개 파일 JSON parse 확인
- history index 재생성 및 `--check`
- `git diff --check`
- 문서 전용 변경이므로 full server suite와 PostgreSQL E2E는 재실행하지 않으며 통과로
  주장하지 않음
