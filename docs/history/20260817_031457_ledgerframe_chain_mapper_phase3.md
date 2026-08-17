# LedgerFrame Chain Mapper 3단계

> **status:** `AWAITING_REVIEW`
>
> **approval:** `NOT_APPROVED`

## 목적

승인된 canonical Profile을 별도 runtime/outbox/worker로 실행하지 않고, 기존 Ledger
reader와 cursor가 등록 Chain mapper를 함수처럼 호출하도록 연결했다. Mapper는 pandas
LedgerFrame만 반환하고 기존 gate와 `LedgerStore.write_batch`가 이후 원자성·저장·cursor를
계속 소유한다.

## 착지 내용

- `ledger/ledger_frame.py`: deterministic source-event identity와 nested JSON을 보존하는
  schema-marked pandas LedgerFrame v1, Atom 왕복, fail-closed validator, 명시적 empty 결과
- `ledger/chain_mapper.py`: 기존 `(db,payload,rule=None)` 함수 모양, trusted callable
  registry, ID/version/mapper-module fingerprint provenance, DB/cursor capability가 없는
  context. 기본 registry와 artifact hash는 프로세스당 한 번만 구성
- `ledger/profile_chain_mapper.py`: 승인 Profile의 column/constant/declared_lookup 실행,
  batch lookup, Pack/Claim emitter registry, 0건·다건·미지원 fail-closed
- `mappers/ledger_lot_event_mapper.py`: Molecule/옛 translator를 호출하지 않는 첫 실제
  Python mapper. split/merge/track-in 원천 행을 LedgerFrame으로 변환
- `backfill.py`·`dry_run.py`: `lot_event`의 기존 source reader와 `event_time` cursor가 동일
  mapper를 호출한 뒤 기존 gate로 전달. selector 없는 source는 기존 실행 유지
- live/sample `lot_event`에 `chain_mapper={mapper_id: lot-event, version: 1}` 명시
- outbox/sink/공개 ExecutionPlan을 만들던 무호출 미추적 초안 2개 제거

## 지킨 경계

- `chain_ingestion_worker`·Chain cursor·outbox·table sink 변경 없음
- mapper의 source/ledger cursor 접근, DB write, commit/rollback 없음
- Atom insert와 cursor advance는 기존 `LedgerStore.write_batch` transaction 하나
- Binding 승인 상태는 실행 readiness일 뿐 Claim epistemic derivation을 바꾸지 않음
- Frame 계산, supersedes 추론, `dt_map` change-log, UI, Trace는 시작하지 않음

## 검증

- 신규 집중 테스트: `25 passed` (split·merge·track-in parity 포함)
- LedgerFrame + 기존 Ledger L1 unit: `116 passed`
- Profile/transfer/observation/L1 기준 묶음: `227 passed, 2 failed`
- 같은 묶음에서 신규 테스트를 뺀 baseline: `202 passed, 2 failed`; 신규 실패 0
  - live config에서 사용자가 비워 둔 `dt_log` 선언 부재 1
  - live config에서 사용자가 비워 둔 `void_obs` 선언 부재 1
- 기존 Chain mapper `73 passed`, 7일 outbox `28 passed`
- 격리 `assy_qa` PostgreSQL mapper 경로 `8 passed, 27 deselected`
- 격리 `assy_qa` 기존 Ledger L1 전체 `35 passed`
- 격리 `assy_qa` 기존 multi-row upsert `36 passed`
- table sink 비-PostgreSQL 묶음 `63 passed, 37 skipped, 2 failed`; 실패 둘은 사용자
  live/sample config의 `dt_slot` 타입과 `dt_map` rule 수가 옛 테스트 기대와 다른 기존 상태
- 현재 dirty/config 상태의 전체 `server/tests`: `3897 passed, 146 failed, 198 skipped,
  1 xfailed, 23 errors`. `void_obs` 등 사용자가 지운 config를 요구하는 다수 기존 fixture 때문에
  전체 수치는 회귀 oracle로 쓰지 않고 위의 동일 환경 포함/제외 기준선을 사용했다.

## 승인 전 남은 것

- 사용자 3단계 재검수
