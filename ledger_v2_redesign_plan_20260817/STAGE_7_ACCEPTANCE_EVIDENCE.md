# Ledger v2 7단계 수락 근거

> 상태: `IN_REVIEW` · 승인: `NOT_APPROVED` · 2026-08-18
> 검수 대상: Audit round-1 지적을 닫은 Stage 7 후속 exact commit

## 구현 결과

```text
server/config/ontology/manifest.json
  → strict load/readiness
  → immutable snapshot 57d36c07271a019242722cc4627f1c0a9c6b477e632f29f32034e331928b0da0
  → ledger_v2_execution selector (lot_event: v2, parity approved)
  → existing physical cursor batch
  → LiveLotEventSourcePreparer
  → Stage 6 Role mapper/Pack compiler/gate/LedgerStore transaction
```

legacy `ledger_config.json`의 live source는 `lot_event` 하나이며 manifest root가 같은 source를
Vocabulary/Entity/Preparer/Mapper/Pack/Profile/Source 전 section에 선언한다. catalog의 physical
열과 business key는 현재 `table_config.json.lot_event`와 정확히 같다. Registry 등록 데이터는
config이고 code에는 trusted implementation class만 있다.

## selector와 cursor 안전 계약

- CLI 기본 진입은 manifest root이며 legacy config module/file을 읽거나 검증하지 않는다.
  `--legacy`만 flat config loader를 호출하고 `--config`는 `--legacy` 전용이다.
- `--legacy`는 별도 은퇴 승인 전 compatibility escape hatch이지만 reset/replay 승인 경계를
  우회하지 못한다.
- 모든 Bundle source에는 selector가 정확히 하나 필요하며 unknown/missing source를 거절한다.
- `mode=v2`는 `parity_status=approved`와 nonblank approval ref가 필수다.
- 기존 legacy cursor `{event_time}`를 v2 `{event_time, txn_seq}`로 추측 변환하지 않는다.
- cursor shape가 같아도 snapshot translator version이 다르면 재사용하지 않는다.
- `--reset-cursor`와 `--from`은 v2/legacy dispatch, config, DB, source/store 접근보다 먼저 모든
  공개 CLI mode에서 거절한다.
- 한 complete physical batch는 Stage 6의 동일 preview/execute compiler와 기존
  `LedgerStore.write_batch()` transaction을 사용한다.

주요 구조화 오류:

| code | path | 의미 |
|---|---|---|
| `cutover_not_approved` | `bundle.chains.ledger_v2_execution.sources.<source>.parity_status` | 승인되지 않은 v2 mode |
| `missing_execution_selector` | `...sources.<source>` | Bundle source selector 누락 |
| `unknown_execution_source` | `...sources.<source>` | 없는 source 선택 |
| `legacy_cursor_reset_required` | `ledger_cursor.<source>.cursor_value` | legacy cursor shape 자동 변환 금지 |
| `cursor_snapshot_reset_required` | `ledger_cursor.<source>.translator_ver` | 다른 snapshot cursor 혼용 금지 |
| `destructive_approval_required` | `reset_cursor|start_from` | 별도 승인 없는 reset/replay 금지 |
| `legacy_config_requires_legacy_mode` | `config` | v2 mode의 legacy config 혼용 금지 |

## 변환·보존

[Legacy 변환 보고](./LEGACY_CONFIG_CONVERSION_REPORT.md)는 old Ledger config, table catalog,
virtual join, chain, enrichment의 실제 상태와 변환 결과를 기록한다. 기존 config는 byte 수정,
archive 이동, 삭제하지 않았다. Stage 7 runtime에는 reset/drop/truncate/delete capability가 없다.

## 검증

- Stage 7 집중: `22 passed`
- Ledger v2 직접 영향군: `364 passed, 10 skipped`
  - 9 skip: 안전한 `ASSY_PG_TEST_DATABASE_URL` 미설정
  - 1 skip: 기존 Windows symlink 권한
- manifest dry-run: `ready`, snapshot hash 위 값, destructive action 3종 `false`
- 수정 Python `py_compile`: 통과
- `git diff --check`: 통과
- 전체 server suite: 사용자 지시에 따라 실행하지 않았고 통과로 표현하지 않는다.

Stage 7의 새 PostgreSQL test는 manifest→physical read→Pack compiler→existing store/cursor→replay
0-row를 검증하도록 추가했다. 현재 환경에서 새 임시 DB 생성을 시도했으나 existing database
config의 host가 비운영 격리 대상임을 증명할 수 없어 안전 정책이 생성을 거절했다. 따라서 이
9건을 통과로 주장하지 않는다. Stage 6에서는 별도 안전한 임시 PostgreSQL 8건이 통과했고
Audit이 경계를 검토했으나, 그것을 이번 Stage 7 신규 test 실행 결과로 바꾸어 쓰지 않는다.

추가 compatibility probe에서 현재 config와 무관하게 남아 있던 기존 실패도 확인했다.
`test_ledger_transfer_unit` 1건은 legacy config에 `dt_log`가 없다는 기존 상태,
`test_ledger_admin_setup` 4건은 이미 제거된 `WaferLeg`를 기대하는 낡은 테스트다. Stage 7 diff는
그 config/test/vocabulary/selection 파일을 수정하지 않았으며 수락군 신규 실패는 0이다.

초기 Stage 7 Audit은 기본 v2 CLI가 legacy loader를 먼저 호출하고 `--legacy`가 reset/replay
gate를 우회하는 두 경계를 거절했다. 후속 구현은 legacy import/load를 명시적 `--legacy`
분기 안으로 옮기고 operator gate를 모든 dispatch보다 앞에 배치했다. 기본 mode loader 호출
0건, legacy reset/from 각각 source/store 실행 0건을 회귀 테스트로 고정했다.

## 미실행·별도 승인 항목

- 운영 DB의 Ledger/cursor 실측 count와 backup 생성
- 기존 cursor reset 또는 source replay
- legacy config `_archive` 이동
- legacy translator/template/code 삭제
- DT/observation Profile과 parity

위 항목은 구현 누락을 숨긴 것이 아니라 7단계 정본이 별도 사용자 승인을 요구하는 선택적
파괴/은퇴 범위다. Audit은 비파괴 cutover 구현을 검수한다. 승인 전 제품 상태는
`NOT_APPROVED`이며 계획을 `COMPLETE`로 표시하지 않는다.
