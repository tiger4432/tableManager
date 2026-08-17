# Ledger v2 Stage 7 manifest cutover

## 현상

Stage 6까지 실행 compiler와 PostgreSQL transaction은 검증됐지만 운영 authoring root가 비어
있었고 CLI는 legacy flat config를 기본으로 읽었다. legacy cursor와 v2 snapshot cursor를 섞지
않는 cutover gate도 없었다.

## 수정

- `server/config/ontology/`에 manifest와 ledger/catalog/dataflow 정본을 추가했다.
- 현재 legacy Ledger의 유일한 source `lot_event`를 physical catalog부터 Pack/Profile/Source까지
  전수 선언했다.
- `cutover_v2.py`가 selector, parity approval, trusted runtime registry와 manifest-only
  dry-run/execute를 소유한다.
- physical 열을 logical Stage 6 EventFrame으로 바꾸는 live preparer를 추가했다.
- CLI 기본을 manifest selector로 전환하고, legacy cursor shape·snapshot version·reset/replay를
  fail-closed했다. `--legacy`는 별도 은퇴 승인 전 compatibility 경계로 보존했다.

## 검증

- Stage 7 집중 `17 passed`
- 직접 영향군 `359 passed, 10 skipped`
- skip: 안전한 PG URL 미설정 9, 기존 Windows symlink 권한 1
- manifest dry-run ready / snapshot `57d36c07271a019242722cc4627f1c0a9c6b477e632f29f32034e331928b0da0`
- 전체 server suite 미실행

임시 PostgreSQL 생성은 대상 host의 격리성이 증명되지 않아 안전 정책이 거절했다. 신규 PG
test는 추가했지만 통과로 주장하지 않는다. 운영 DB/config 삭제, reset, migration, legacy 이동은
0이다.

## 상태

Stage 7은 `IN_REVIEW / NOT_APPROVED`다. exact commit을 독립 Audit에 제출하며 Audit 판정 전
계획을 COMPLETE로 바꾸지 않는다.
