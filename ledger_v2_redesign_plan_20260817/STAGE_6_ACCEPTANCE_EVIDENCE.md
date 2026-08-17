# Ledger v2 6단계 수락 근거

> 상태: `IN_REVIEW` · 승인: `NOT_APPROVED` · 2026-08-17
> 검수 대상: 본 문서를 포함한 Stage 6 구현 exact commit

## 구현 경계

```text
same bounded source batch + immutable LedgerSetupSnapshot
  ├─ preview: SourcePreparer → RoleFrame → Pack compiler → candidate semantics
  └─ execute: 같은 경로 → existing gate → LedgerStore → existing cursor transaction
```

`server/ledger/runtime_v2.py`는 worker나 cursor reader를 새로 만들지 않는다. 기존 driver가
읽은 물리 batch와 exact cursor tuple을 받고, Stage 5/4의 동일 preparer/compiler를 dry-run과
execute에 사용한다. gate 전에 한 event라도 실패하면 `write_batch()`를 호출하지 않는다.
store에는 snapshot hash 기반 translator version을 전달하고, 기존 cursor row의 version이
다르면 Atom insert와 cursor update를 같은 transaction에서 rollback한다.

## objectless register와 first-sight

기존 원장의 `register`는 object가 없는 Claim이다. Bundle/Vocabulary/Pack의 닫힌 object kind에
`none`을 추가했으며 Pack compiler만 물리 `object_kind=NULL, object_payload=NULL`을 만든다.
Registry 주소(`register@1`, `Lot@1`)의 version은 snapshot hash에 남고 기존 Ledger/read API가
쓰는 물리 철자(`register`, `Lot`)는 유지한다.

`LotEventRoleMapper`는 DB를 받지 않고 register 후보만 RoleEmission으로 낸다. 기존 driver가
`LedgerStore.existing_registrations()`로 한 번에 읽은 `(subject_type, canonical_keys)` snapshot을
runtime에 명시적으로 넘겨야 한다. `None`은 “없음”으로 추정하지 않고
`registration_context_required`로 거절한다. 명시적 빈 set은 첫 실행이고, 같은 batch와 replay의
중복 register는 compiler 뒤·gate 전에 제거된다.

## multi-row event와 incomplete

`LotEventSourcePreparer`가 split/merge의 두 physical row에서 결정적 `event_group_key`를 만든다.
prepared output identity/group은 cursor SELECT에 들어가지 않고, order/time/cursor는 계속 base
physical column이다. mapper는 `BaseLedgerMapper.map()`을 재정의하지 않고 `interpret_unit()`에서
split/merge/track-in을 RoleEmission으로만 해석한다.

한쪽 pair row만 온 경우 현재 보이는 membership/lineage 사실을 기록하고
`assy_manager.source_event_incomplete=true`를 RoleFrame까지 보존한다. execute는 기존
`LedgerStore.write_batch(... incomplete=N)`과 gate metric에 같은 수를 전달한다. 이것은 identity
결손·join 0건처럼 Atom 0으로 거절하는 `source_preparation_incomplete`와 다른 상태다.

## legacy↔v2 parity matrix

| source/shape | 후보 수 | 정규화 equal | 승인 차이 | regression | 판정 |
|---|---:|---:|---:|---:|---|
| `lot_event` split | 10 | 10 | provenance/version/등록 mapping 표현 | 0 | GO |
| `lot_event` merge | 11 | 11 | provenance/version/등록 mapping 표현 | 0 | GO |
| `lot_event` track-in | 5 | 5 | provenance/version/등록 mapping 표현 | 0 | GO |
| 한 행 declarative Claim | fixture | 전수 | 없음 | 0 | GO |
| multi-Core→DTDie→BondComponent/FinalChip | Stage 5 fixture | 구조/identity 전수 | legacy Position 제거는 설계 차이 | 0 | 운영 source parity 전까지 NO-GO |
| observation/finding | 기존 legacy unit fixture | 미실행 | 없음 | 미검증 | V2 Profile/Mapper 전까지 NO-GO |

lot_event 26개 Claim의 subject/keys/predicate/object/time은 정규화 후 모두 같다. 전체 envelope를
비교하면 canonical EventFrame event ID/raw ref/molecule ref, snapshot translator version,
register의 type별 unique mapping ID에서 117개 field difference가 발생하며 모두 fixture의 명시적
승인 사유가 있다. 설명 없는 차이는 0이다. source별 GO/NO-GO를 분리하므로 미구현 DT/observation
source를 이 결과로 운영 전환하지 않는다.

## PostgreSQL E2E

실제 운영 DB가 아닌 실행마다 새로 만든 `assy_ledger_v2_stage6_test_*` database에서 다음을
검증하고 정확한 임시 database를 종료 시 DROP했다.

- 실제 PostgreSQL UNIQUE catalog probe가 발급한 `VerifiedJoinDescriptor`
- Bundle→snapshot→dry-run/execute 동일 후보→gate→LedgerStore→cursor
- trace/coverage/structure read API 응답
- join 0건/다건, pending/rejected nested Binding, gate refusal: Atom 0/cursor 0
- snapshot cursor version 충돌: insert와 cursor 모두 rollback
- replay dedupe와 같은 snapshot cursor restart
- source/right relation write 0
- EXPLAIN이 verified right UNIQUE index 사용

결과: `8 passed`. PostgreSQL migration과 운영 config 변경은 0이다.

## scale·replay

- verified join: 1000 unique key는 1 query, 1001 key는 2 query; N+1 없음
- cursor: bounded physical batch의 exact row tuple만 허용; 큰 OFFSET 실행기 없음
- right late arrival: 같은 event 재시도
- right value 수정: provenance fingerprint 기반 `dependency_replay` 후보
- register: 기존 partial index를 쓰는 `existing_registrations()` batched snapshot 필수

dependency replay는 후보 산출까지 검증됐다. 실제 worklist 적재/supersede는 Stage 7 운영 연결 전
별도 경계이며 DT source의 운영 판정은 그 연결 전까지 NO-GO다.

## 검증 결과

- Ledger 직접 영향군: `370 passed, 9 skipped`
  - 8 skip: 격리 PG URL 없이 실행한 `test_ledger_v2_pg.py`
  - 1 skip: 기존 Windows symlink 권한 항목
- 동일 PG module의 실제 격리 PostgreSQL 실행: `8 passed`
- 수정 Python `py_compile`: 통과
- `git diff --check`: 통과
- baseline 대비 직접 영향군 신규 실패: `0`
- 전체 server suite: 사용자 지시에 따라 실행하지 않았고 통과로 표현하지 않는다.

## 아직 하지 않은 것

- 운영 `server/config/ontology/` manifest/config 생성과 실제 source selector 전환
- legacy source 전면 제거
- 운영 Ledger/cursor reset 또는 데이터 삭제
- DT/observation source의 실제 legacy↔v2 parity 승인
- dependency replay 후보의 운영 worklist/supersede 실행

따라서 Stage 6 자체 구현은 독립 Audit 검수 대상이나, Stage 7에서도 `lot_event`만 cutover 후보이며
나머지 source는 NO-GO 상태를 유지한다.
