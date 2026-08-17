# Ledger v2 5단계 수락 근거

> 상태: `IN_REVIEW` · 승인: `NOT_APPROVED` · 2026-08-17
> 브랜치: `feature/ledger-v2-stage5-source-driver`

## 변경 파일과 역할

| 파일 | 역할 |
|---|---|
| `server/ledger/source_preparation.py` | verified join batch read, sealed SourcePreparer, EventFrame/provenance, replay 후보 |
| `server/ledger/backfill.py` | 기존 cursor가 v2 base SELECT와 preparation을 호출하는 얇은 adapter |
| `server/tests/test_ledger_source_preparation.py` | Stage 5 정상·반례·scale·DT 계층 fixture |

## 실행 계약

```text
existing cursor base physical DataFrame
  → BaseSourcePreparer.prepare_batch() final boundary
  → inherited VerifiedJoinDescriptor의 unique key만 1000개씩 read
  → registered prepare_outputs() hook
  → complete EventFrame + source/right provenance
  → Stage 4 RoleFrame/Pack compiler
```

`base_select_columns()`는 driver identity/group/order/time/cursor, preparer inputs, mapper의
비파생 입력만 반환한다. preparer output은 cursor SELECT에서 제외된다. runtime 구현 registry는
sealed이고 하위 구현은 `prepare_batch()`를 재정의하지 못하며 선언된 output 값 계산만 한다.
SQLAlchemy adapter에는 commit/rollback/cursor/store 권한이 없다.

## fail-closed 계약

```json
{"code":"source_preparation_missing","path":"source_preparation.join_rules.<rule>.keys.<key>","message":"verified right relation returned no row"}
{"code":"source_preparation_ambiguous","path":"source_preparation.join_rules.<rule>.keys.<key>","message":"verified right relation returned N rows"}
{"code":"source_preparation_incomplete","path":"source_batch.rows[0].<key>","message":"join key value is missing"}
{"code":"source_preparation_output_collision","path":"source_batch.columns","message":"prepared outputs cannot overwrite base values"}
```

오류는 mapper/compiler 전에 전파되며 이 모듈에는 cursor advance나 Atom 생성 기능이 없다.
missing/incomplete는 `target_mapping_missing`, ambiguous는 `target_mapping_ambiguous` Enrich
Action 후보로 순수 변환된다.

## provenance와 replay

EventFrame은 source row ref와 함께 rule ID, normalized join key, right relation/row identity,
right value fingerprint, right updated_at, preparer ID/version을 보존한다. 같은 증거는
`source_raw_ref`에도 canonical JSON으로 묶여 Pack compiler 뒤 Claim provenance에서 사라지지
않는다. 성공 뒤 right fingerprint 변경은 `dependency_replay` worklist 후보를 결정적으로 낸다.
missing event는 예외가 cursor caller까지 전파되어 같은 event를 재시도한다.

## DT/다층 fixture

3개 CoreDie가 하나의 DT job과 confirmed inventory 한 행을 공유하는 fixture를 사용했다.
잘못 기록된 left DT lot은 그대로 보존되고 identity에는 inventory lot/slot과 계산한 DT 좌표가
사용된다. 같은 EventFrame은 다음을 만든다.

```text
CoreDie → transferred_to → DTDie
DTDie → transferred_to → BondComponent
CoreDie × 3 → component_of → FinalChip
```

`same_as`는 발화하지 않으며 Entity exact key는 Stage 3 Registry/Stage 4 compiler가 검사한다.

## 검증 결과

- Stage 5 직접 계약: `server/tests/test_ledger_source_preparation.py` → `18 passed`
- Setup/Registry/RoleFrame/SourcePreparer/backfill/동결 mapper/L1 unit 직접 영향군:
  `339 passed, 1 skipped`.
- skip 1건은 기존 Windows symlink 생성 권한 부재다.
- PostgreSQL E2E, gate/store/cursor 실제 transaction: Stage 6 범위이며 통과로 표현하지 않는다.
- 전체 서버 suite: 사용자 지시에 따라 실행하지 않는다.
- DB migration/write, cursor advance: `0`.

## 범위 밖·미완료

- 운영 manifest/config와 source 등록
- 기존 gate→LedgerStore→cursor PostgreSQL E2E
- legacy↔v2 shadow parity
- dependency replay 후보의 DB worklist 적재와 supersede 실행
- 운영 cutover/reset/legacy 제거

자체 판정: Stage 5 독립 Audit을 요청할 수 있다. 승인 전 상태는
`STAGE_5_IN_REVIEW / NOT_APPROVED`이고 Stage 6을 시작하지 않는다.
