# 현행 Ledger 호출 그래프

> 실측 기준: 2026-08-17, `main@3b640b8`
> 상태: `IN_REVIEW` / `NOT_APPROVED`

## 실제 write 경로

```text
LedgerBackfill.run(source)
  ├─ lineage     → _run_lineage
  │    ├─ chain_mapper 있음 → configured_mapper → run_registered_mapper → LedgerFrame
  │    └─ 없음                → LotEventTranslator → atoms
  ├─ observation → _run_observation → ObservationTranslator → atoms
  ├─ declared    → _run_declared    → DeclaredTranslator → atoms
  └─ transfer    → _run_transfer    → container batch lookup → TransferTranslator → atoms

공통 → gate.building_molecule → gate.screen_molecule → _flush
     → LedgerStore.write_batch → 같은 transaction에서 atom append + cursor advance
```

`chain_mapper` 선택점은 `_run_lineage`에만 있다. `config.py`도 non-lineage source의
`chain_mapper`를 거절한다. 현행 3단계는 범용 경로가 아니라 lineage reader의 한 갈래다.

## live config 경로

현재 live `ledger_config.json` source는 `lot_event` 하나다.

```text
lot_event(kind=lineage, mapper=lot-event@1)
  row_identity=txn_seq / cursor boundary=event_time
  → ledger_lot_event_mapper
  → 내부에서 Atom 직접 생성한 LedgerFrame
  → gate → store → cursor
```

`void_obs`, `delam_obs`, `dt_log`는 sample에만 있다. observation/transfer unit test 중 live
선언을 요구하는 두 테스트는 이 때문에 실패한다.

## cursor와 molecule

| kind | base read/order | molecule | cursor | mapper 선택 |
|---|---|---|---|---|
| lineage | `(event_time,row_identity)` | 완전한 time group + 내부 pairing | `event_time` | 유일하게 가능 |
| observation | 선언 keyset | row 1개 | watermark tuple | 불가 |
| declared | 선언 keyset | row 1개 | watermark tuple | 불가 |
| transfer | `(group_key,row_order)` | job/group 전체 | `group_key` | 불가 |

`event_time` cursor는 late arrival가 cursor 뒤로 들어오는 알려진 비용이 있다. v2는 cursor
소유권은 유지하되 SourcePlan이 event identity/order/index를 명시·검증한다.

## dry-run

`dry_run.py`도 네 kind를 별도 분기한다. lineage만 registered mapper를 호출하고 나머지는
legacy translator와 gate를 직접 호출한다. write/cursor advance는 없지만 변환 분기는
execute와 중복이다.

```text
same SourcePlan snapshot → same Preparer → same Mapper/RoleFrame
  → same Pack compiler/LedgerFrame
  ├─ dry-run: 후보/거절 반환
  └─ execute: 기존 gate/store/cursor 전달
```

## virtual join 경계

```text
현재 UI: load_verified_rules → UNIQUE 증명 → batched LEFT JOIN → attach(UI payload)
현재 Ledger transfer: source container config → 별도 SQL/lookup adapter → Position payload
```

Ledger cursor는 virtual-only column을 읽지 못한다. v2는 verifier의 immutable descriptor만
공유하고 UI `attach()`가 아닌 pandas Source Preparer가 완성 EventFrame을 반환한다.

## 목표와 keep 경계

```text
existing cursor/base reader                    KEEP
  → pandas Source Preparer                     NEW
  → EventFrame → BaseLedgerMapper → RoleFrame  NEW
  → Pack compiler → LedgerFrame                NEW
  → existing gate                              KEEP
  → existing store + cursor transaction        KEEP
```

Kernel과 재작성 계층이 겹치는 symbol은 없다. `backfill.run`의 transaction orchestration은
유지하되 source-kind 분기와 변환 선택은 compiled SourcePlan으로 옮긴다.
