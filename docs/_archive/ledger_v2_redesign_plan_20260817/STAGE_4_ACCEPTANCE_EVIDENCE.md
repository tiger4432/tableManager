# Ledger v2 4단계 수락 근거

> 상태: `COMPLETE` · 승인: `APPROVED` · 2026-08-17
> 승인 커밋: `1d9bd4aa2f1b0ca5012c959e4647d8feab956ee1`

## 변경 파일과 역할

| 파일 | 역할 |
|---|---|
| `server/ledger/setup_bundle.py` | Mapper 내부 `group_by`의 닫힌 `unit.columns` 검증 |
| `server/ledger/setup_registry.py` | 검증된 Mapper unit columns를 immutable descriptor/snapshot에 포함 |
| `server/ledger/roleframe.py` | EventFrame→RoleFrame 공통 mapper와 Pack compiler, 순수 dry-run |
| `server/tests/test_ledger_setup_bundle.py` | group_by columns 필수·input subset·타 unit 금지 반례 |
| `server/tests/test_ledger_setup_registry.py` | unit columns snapshot 보존 |
| `server/tests/test_ledger_roleframe.py` | Stage 4 정상·반례·결정성·무권한 테스트 |

상태·소유권·이력 문서는 구현 사실에 맞춰 동기화했다. 기존 driver, Chain mapper, translator,
LedgerFrame, gate, store, cursor, DB schema/migration은 변경하지 않았다.

## 최종 계약

```text
prepared pandas EventFrame
  → sealed RoleMapperImplementationRegistry
  → BaseLedgerMapper.map() final pipeline
  → RoleEmission only
  → normalized pandas RoleFrame
  → Pack/Vocabulary/Entity compiler
  → existing pandas LedgerFrame
```

`MapperContext`에는 immutable `LedgerSetupSnapshot`과 그 Snapshot이 소유한 `SourcePlan`만 있다.
DB session, relation reader, cursor, gate, store는 없다. 선언형 binder가 지원하는 binding은
`column|constant|entity`뿐이고 Entity key binding도 Stage 2에서 닫힌 같은 계약을 사용한다.
Python mapper 자유 코드는 `interpret_unit()`만 구현하며 raw Atom, mapping, 임의 DataFrame,
LedgerFrame을 반환하면 `unsupported_mapper_output`으로 거절된다. Mapper `group_by` 열은
`mappers.*.unit.columns`가 소유하며 Source Driver의 event grouping을 재사용하지 않는다.
Mapper descriptor 계약 확장에 따라 `compiler_contract_version`은 `2`로 증가해 이전 snapshot과
같은 실행 계약으로 오인되지 않는다.

## 정규화 예시

RoleFrame 한 행:

```json
{
  "source_event_id": "af884364-4da5-5ce5-80c6-263b4036de82",
  "mapping_id": "main_transition",
  "claim_ref": "movement@1/transition",
  "roles": {
    "subject": {"type": "InputEntity@1", "keys": {"input_id": "IN-1"}},
    "target": {"type": "OutputEntity@1", "keys": {"output_id": "OUT-1"}},
    "occurred_at": "2026-08-17T10:30:00+09:00",
    "event_key": "E-1"
  },
  "source_row_refs": ["input_rows:record:R-1"]
}
```

Pack compiler의 의미 출력:

```json
{
  "subject_type": "InputEntity@1",
  "subject_keys": {"input_id": "IN-1"},
  "predicate": "moves_to@1",
  "object_kind": "entity_ref",
  "object_payload": {
    "type": "OutputEntity@1",
    "keys": {"output_id": "OUT-1"},
    "qualifiers": {"event_key": "E-1"}
  },
  "derivation": "main_transition"
}
```

Binding의 `binding_origin` 변경은 위 의미 필드를 바꾸지 않는다. 승인 metadata는 executable
여부만 결정하고 Claim class/pin/confirmed 필드를 만들지 않는다.

## fail-closed 오류 예시

```json
{"code":"unsupported_mapper_override","path":"mapper_type.map","message":"BaseLedgerMapper.map() is final and cannot be overridden"}
{"code":"invalid_entity_ref","path":"role_frame.rows[0].roles.subject.type","message":"entity Role type disagrees with the Profile binding"}
{"code":"unsupported_mapper_output","path":"mapper.units[0].emissions[0]","message":"raw Atom, LedgerFrame, mappings, and arbitrary values are forbidden"}
{"code":"snapshot_mismatch","path":"event_frame.attrs.setup_snapshot_hash","message":"EventFrame was not prepared for this setup snapshot"}
{"code":"ambiguous_source_row_ref","path":"event_frame.rows","message":"indistinguishable rows require explicit __source_row_ref values"}
```

## 검증 결과

1. Stage 4 직접 계약:
   `server/tests/test_ledger_roleframe.py` → `23 passed`
2. 직접 영향군:
   `test_ledger_setup_bundle.py`, `test_ledger_setup_registry.py`,
   `test_ledger_roleframe.py`, `test_ledger_frame_chain_mapper.py`
   → `205 passed, 1 skipped`
3. skip 1건: Windows가 테스트 symlink를 생성할 권한이 없어 기존 manifest escape 테스트가 skip.
4. 전체 서버 suite: 사용자 지시에 따라 실행하지 않았으며 통과로 표현하지 않는다.
5. DB read/write/migration, cursor advance: `0`.

## 범위 밖·미완료

- 기존 source driver/cursor가 EventFrame을 만드는 연결
- virtual join source preparation과 right-row 0/다건 처리
- 기존 gate/store transaction 실행
- PostgreSQL E2E와 legacy parity
- 운영 config·cutover·reset

## 독립 Audit 승인

Audit은 exact commit `1d9bd4aa2f1b0ca5012c959e4647d8feab956ee1`에서 정본 경로,
sealed mapper registry, `compiler_contract_version=2`, runtime/DB 비침범을 확인했다.
독립 직접 영향군 결과는 `205 passed, 1 skipped`였고 skip은 기존 Windows symlink 권한
항목이다. 차단 사항 없이 `APPROVE`됐으며 사용자 상설 승인에 따라 main 병합과 Stage 5
착수를 진행한다.
