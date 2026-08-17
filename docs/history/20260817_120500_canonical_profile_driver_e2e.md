# Canonical Profile source-driver 실행 경계 보완

> 일시: 2026-08-17 12:05 KST
> 상태: `AWAITING_REVIEW` / `NOT_APPROVED`

## 변경

- 기존 Ledger lineage source driver가 `chain_mapper.profile_id`로 검증된 canonical Profile을
  명시적으로 선택한다.
- Profile ID/source 일치와 Profile section 검증을 config load에서 fail-closed로 묶었다.
- source row의 선언된 `row_identity` 집합에서 순서·pandas index에 독립적인 source-event
  context를 만들고 dry-run/execute가 똑같이 mapper에 전달한다.
- `destination_inventory`의 `row_id/business_key_val/container`를 최대 1000 key씩 읽는
  별도 read-only lookup adapter를 등록했다.
- 일반 `run_registered_mapper`는 `legacy_atom`을 거절한다. 과거 export 복원 전용 함수만
  명시적으로 허용하며 store/cursor를 소유하지 않는다.
- 선택 Profile의 결정적 serialization hash를 기존 cursor 실행 version에 포함했다.

## 검증

- `server/tests/test_ledger_frame_chain_mapper.py`: `29 passed`
- `server/tests/test_ledger_l1_pg.py`: 격리 PostgreSQL에서 `40 passed`
- PostgreSQL E2E가 dry-run 후보와 execute 후보 parity, gate, LedgerStore, cursor를 확인했다.
- nested Binding `pending/rejected`와 lookup 0건/다건은 Atom 0, cursor 미이동을 확인했다.
- Python compile 검사 통과.

## 범위

- DB migration, 새 cursor, 별도 Chain worker, translator 일괄 재작성, UI/Trace는 추가하지 않았다.
- `docs/history/README.md`에는 기존 병합 충돌이 있어 이번 작업에서 수정하거나 인덱스를
  재생성하지 않았다.
