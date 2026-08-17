# LedgerFrame Chain Mapper

> **Status:** `AWAITING_REVIEW` · **Approval:** `NOT_APPROVED`
>
> **단계 경계:** 2단계 canonical Profile 계약은 승인됨. 이 문서는 3단계 실행 경로이며
> 사용자 승인 전에는 4단계·Frame 계산·`dt_map` change-log·`frame_confirmed`를 시작하지 않는다.

## 1. 결론

Ledger가 실행을 계속 소유하고 Chain mapper는 순수 변환 함수로만 들어간다.

```text
existing Ledger source reader
  -> existing Ledger cursor selects input
  -> registered Chain mapper (db, payload, rule=None)
  -> pandas LedgerFrame
  -> existing gate
  -> existing LedgerStore.write_batch
  -> Atom append + existing Ledger cursor advance in one transaction
```

재사용한 것은 Chain worker가 아니라 기존 mapper의 함수 모양이다. Ledger용 Chain worker,
Chain cursor, table sink, outbox consumer, scheduler, retry queue는 만들지 않았다.

## 2. 기존 경계 조사 결과

| 책임 | 기존 정본 | 3단계 판정 |
|---|---|---|
| source 읽기·cursor | `server/ledger/backfill.py` | 유지. mapper는 입력 범위와 next cursor를 모른다. |
| gate 입력 | `server/ledger/envelope.py::Atom` | LedgerFrame을 검증한 뒤 이 기존 객체로 무손실 복원한다. |
| source-event 원자성 | `server/ledger/gate.py::building_molecule` + `screen_molecule` | 유지. 한 사건 Claim 전부를 한 gate scope로 검사한다. |
| 저장·cursor transaction | `server/ledger/store.py::LedgerStore.write_batch` | 유지. Atom insert와 `_advance_cursor` 후 한 번 commit, 예외 시 rollback한다. |
| dry-run | `server/ledger/dry_run.py::preview` | 같은 등록 mapper와 LedgerFrame validator/gate를 호출하고 store는 호출하지 않는다. |
| 기존 Chain mapper | `server/chain_ingestion_worker.py::execute_custom_mapper` | `(db, payload, rule=None)` 모양만 재사용한다. worker는 변경하지 않았다. |
| 기존 표준 Claim DataFrame | 없음 | `ledger_frame.py`의 단일 pandas 계약을 신설했다. |
| 과거 별도 Profile runtime 초안 | 호출자 없음 | outbox/sink/ExecutionPlan 중심의 미추적 초안 2개를 parity 후 제거했다. |

## 3. LedgerFrame v1

`LedgerFrame`은 저장소나 두 번째 Claim DTO가 아니다. schema marker가 있는 pandas
`DataFrame`이며 mapper와 기존 gate 사이에서만 존재한다.

열 순서는 고정이다.

| 열 | 의미 |
|---|---|
| `source_event_id` | provenance에서 결정적으로 계산된 `uuid.UUID` |
| `source_event_state` | `source_molecule`, `source_record`, `legacy_atom` 중 하나 |
| `subject_type`, `subject_keys` | 주어 유형과 JSON 구조를 보존한 신원 |
| `predicate` | 기존 원장 술어 |
| `object_kind`, `object_payload` | 목적어 종류와 JSON 구조를 보존한 값 |
| `occurred_at` | timezone-aware source world time |
| `source_who` | 원천 이름 |
| `source_translator_ver` | source config version + mapper ID/version/code fingerprint + derivation |
| `source_raw_ref` | 원천 재발화 경로 |
| `supersedes` | 기존 선택적 대체 참조. mapper가 추측하지 않음 |
| `molecule_ref` | gate용 비의미 사건 경계 |
| `derivation` | gate가 검사할 선언된 도출 규칙 |

Validator는 필수/추가 열, 자료형, timezone, nested identity/payload, source event UUID와
provenance의 일치, 동일 사건 경계의 다중 world time 분할을 fail-closed로 거절한다. pandas
index는 읽지 않는다. `empty_ledger_frame()`만 정상 무출력이고 `None`·임의 DataFrame은
실행 실패다.

## 4. Mapper registry와 provenance

`server/ledger/chain_mapper.py`의 `LedgerMapperRegistry`에는 Python callable 자체를 코드로
등록한다. config에는 `mapper_id`와 양의 정수 `version`만 쓸 수 있다. module/function/path는
선언할 수 없다.

등록 시 entry 함수만이 아니라 그 함수가 속한 mapper 모듈 전체 source artifact의 SHA-256을
계산한다. helper만 바뀌어도 fingerprint가 달라진다. 기본 registry는 프로세스당 한 번만
구성·봉인하므로 source 검사와 hashing을 사건마다 반복하지 않는다. 실행한 각 Claim은 다음
꼴을 `source_translator_ver`에 남긴다.

```text
<source-config-version>|mapper:<mapper-id>@<version>:<fingerprint-16>#<derivation>
```

Mapper 첫 인자는 writable DB session 대신 `LedgerMapperContext`다. 이 객체에는 명시적
lookup adapter와 snapshot 값만 있고 engine, cursor, commit, rollback, source reader가 없다.

## 5. Python mapper — lot_event 첫 전환

첫 실제 전환 source는 `lot_event`다.

```json
"chain_mapper": {"mapper_id": "lot-event", "version": 1}
```

`server/mappers/ledger_lot_event_mapper.py`가 Ledger reader가 넘긴 논리 행을 사건별 pandas
frame으로 묶고 split/merge/track-in 의미를 LedgerFrame으로 반환한다. 실행 경로에서는
`LotEventTranslator`나 옛 Molecule을 호출하지 않는다. 기존 translator는 fixture parity
기준으로만 남는다.

- source 조회, page cut, `event_time` cursor: 기존 `backfill.py`
- event grouping과 Claim 변환: 등록 mapper
- 기존 register 조회: driver가 페이지당 한 번 수행해 명시적 memo snapshot으로 전달
- gate와 `LedgerStore.write_batch`: 기존 경로
- mapper/schema/gate 실패: 현재 처리 단위 Atom 0, cursor 미이동, typed error 전파
- 정상 empty: cursor 이동 여부는 기존 source driver의 처리 정책이 결정
- selector가 없는 observation/transfer/declared 및 다른 lineage source: 기존 runtime 유지

## 6. Canonical Profile mapper

`server/ledger/profile_chain_mapper.py`는 승인된 2단계 Profile을 같은 mapper 함수 모양으로
평가한다. 공개 ExecutionPlan이나 별도 lifecycle은 없다.

지원:

- `column`: 입력 DataFrame의 명시적 열
- `constant`: Profile validator가 Role 계약으로 허용한 값
- `declared_lookup`: 등록 adapter의 `resolve_many`만 호출
- Pack/Claim별 등록 emitter: `lot-lineage@1/transition`, `transfer@1/movement`
- 모든 최상위/중첩 Binding의 기존 readiness gate

Lookup은 binding별 고유 key를 모아 한 번에 호출하며 0건은 `lookup_not_found`, 다건은
`lookup_not_unique`, 미등록 adapter/select와 잘못된 반환 형상은 전용 오류로 거절한다.
raw SQL, 임의 Python/JavaScript/expression은 없다. Binding의 `approval_status`와
`binding_origin`은 실행 허용만 결정하며 Claim의 derivation/epistemic class를 승격하지 않는다.

## 7. Dry-run과 transaction

`dry_run._preview_lineage`와 `backfill._run_lineage`는 동일한 registry와 mapper 함수,
LedgerFrame validator, 기존 gate를 사용한다. dry-run은 PostgreSQL read-only transaction에서
동작하며 `atoms_rendered`에 `source_event_id/state`와 provenance를 포함한다. 분기는 gate 뒤다.

실제 저장은 계속 `LedgerStore.write_batch` 하나뿐이다. 새 코드에는 `LedgerStore`, INSERT,
commit, rollback, cursor update가 없다. 따라서 저장 실패 시 기존 transaction이 Atom과
cursor를 함께 rollback한다.

## 8. 테스트와 검증 결과

자동 테스트는 다음을 고정한다.

- LedgerFrame schema·구조·빈 결과·index 독립성·event time 분할 거절
- Python/Profile mapper·결정성·fingerprint provenance·trusted registry
- column/constant/declared_lookup·nested key readiness·0/다건 lookup 거절
- Profile approval metadata와 Claim derivation 분리
- lot_event split·merge·track-in과 기존 translator의 Claim 의미/provenance parity
- 동일 source event 다중 Claim gate 원자성
- unsafe module/path config 거절과 mapper의 DB/cursor/write capability 부재
- PostgreSQL E2E: 기존 cursor → mapper → LedgerFrame → gate → store → 조회,
  dry-run parity, replay dedupe, mapper/schema/gate 실패 시 cursor 미이동

2026-08-17에 production DB가 아닌 격리 `assy_qa`에서 실제 실행했다.

- 신규 집중 단위: `25 passed`
- 신규 집중 + 기존 Ledger L1 unit: `116 passed`
- 격리 PostgreSQL mapper 경로: `8 passed, 27 deselected`
- 격리 PostgreSQL 기존 Ledger L1 전체: `35 passed`
- 격리 PostgreSQL 기존 multi-row upsert: `36 passed`
- Profile/transfer/observation/L1 묶음, 신규 포함: `227 passed, 2 failed`
- 같은 묶음, 신규 파일 제외 baseline: `202 passed, 2 failed` — **신규 실패 0**
- 기존 Chain mapper: `73 passed`; 7일 outbox: `28 passed`

동일한 두 실패는 사용자가 재작성하려고 비워 둔 live Ledger config의 `dt_log`와 `void_obs`
부재다. table sink 관련 비-PostgreSQL 묶음의 기존 실패 둘도 live `dt_slot` 타입과 sample
`dt_map` rule 수가 현재 테스트의 옛 기대와 다른 config 상태다. 이 파일들은 Phase 3가
수정하지 않았다.

참고로 현재 dirty/config 상태의 `server/tests` 전체 실행은 `3897 passed, 146 failed,
198 skipped, 1 xfailed, 23 errors`였다. 대표 오류는 table config에서 지워진 `void_obs`를
요구하는 fixture처럼 진행 중인 config 재작성에 묶여 있어 Phase 3 회귀 판정에는 쓸 수 없다.
Phase 3 신규 실패 판정은 위의 동일 환경 포함/제외 대조와 격리 PostgreSQL 실경로로 한다.

## 9. 범위 밖

- outbox 기반 Ledger 입력·복구 journal
- Ledger 전용 Chain worker/cursor/sink/scheduler
- 범용 grouping/aggregation/expression DSL
- 자동 supersedes/retract, Frame 계산, `dt_map` change-log
- 미전환 translator 일괄 제거
- UI와 Trace API
