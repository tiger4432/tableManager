# Ontology Config Explorer — 구현·수락 근거

> 상태: `COMPLETION_IN_REVIEW / NOT_APPROVED`
> 기준 active snapshot: `57d36c07271a019242722cc4627f1c0a9c6b477e632f29f32034e331928b0da0`
> 파괴 작업: 운영 config/DB write, reset/replay, migration, legacy 이동·삭제 0

## 1. 이번 완료 후보가 닫은 계약

- compiled node를 SourcePlan과 모든 Profile Binding까지 열거한다.
- wrong kind/version/signature와 unresolved를 서로 다른 status·message·leaf pointer로 답한다.
- current route와 다른 path 후보를 분리하고 breadcrumb/뒤/앞 history가 exact edge route, tab,
  active/draft mode, tree/workspace scroll, editor cursor, context token을 함께 복원한다.
- node hover/focus popover, keyboard Enter/Space, ACTIVE/DRAFT 비색상 문구를 제공한다.
- dirty draft 이동은 유지/폐기/취소 3선택이며 초안 target은 이동해도 바뀌지 않는다.
- draft diff는 normalized node/edge의 added/modified/removed를 별도 collection으로 보존한다.
- review_requested revision은 UI·store·server에서 불변이며 `/revise`로만 새 revision을 연다.
- activation은 base/hash CAS, atomic replace, reload 뒤 선언된 모든 persistent consumer의 새 hash
  일치를 요구하고 empty/mismatch를 rollback한다.

## 2. API와 오류 경계

| Method | Path | 계약 |
|---|---|---|
| GET | `/admin/ontology-explorer/view` | `selection,q,page,limit,reference_limit,context_token,draft_id,revision,view_mode`; 한 context |
| POST | `/admin/ontology-explorer/drafts` | target/base 고정 |
| PUT | `/admin/ontology-explorer/drafts/{id}` | JSON parse + 동일 compiler preview |
| POST | `.../{id}/review` | exact revision 동결 |
| POST | `.../{id}/revise` | immutable review에서 새 editing revision |
| DELETE | `.../{id}` | expected revision 폐기 |
| POST | `.../{id}/activate` | review/base/hash/convergence CAS |

`stale_draft`, `draft_conflict`, `consumer_convergence_failed`는 409로 분리한다. 쓰기 route는
strict Admin token을 요구하고 임의 파일 경로·pointer를 받지 않는다.

## 3. 실제 데이터와 file-backed sample

- 현재 active graph는 47개 declaration을 열거한다. SourcePlan, Profile, Mapping, Binding,
  Pack/Claim/Vocabulary/Entity/Preparer/Mapper/Table을 모두 같은 snapshot에서 왕복한다.
- `server/config/sample/ontology/transfer_explorer/`는 운영 manifest와 격리된 6개 JSON 정본이다.
  production loader/compiler를 통해 `CoreDie -> DTDie -> BondComponent -> FinalChip`, `DTJob`,
  `LotSlot`, `transferred_to@1`, VerifiedJoin, SourcePlan을 재현한다. physical UNIQUE verifier만
  테스트 adapter로 격리한다.
- sample의 custom implementation을 운영 trusted registry에 몰래 등록하지 않는다. 따라서
  샘플을 운영 draft로 활성화하려는 시도는 `untrusted_implementation`으로 fail-closed한다.

## 4. 실제 검증 수치

- backend 직접 범위: `165 passed` (`test_ontology_config_explorer.py` + `test_admin_auth.py`)
- Explorer client harness: `29 assertions, 0 failed`
- client contracts: `7/7`; clipboard convention: pass
- production build: Vite 107 modules, success
- performance fixture: 10,000 nodes/9,999 inbound, `<2s`, `<=213 nodes`, `<1.5MB`
- browser: 1920×1080, 700×900, 320×800; Explorer root/body horizontal overflow 0
- browser journeys: transfer 7 routes, exact breadcrumb/back/forward, hover, keyboard, dirty 3선택,
  active/draft preview, review→revise, reviewed textarea read-only

증거 화면:

- `evidence/transfer_explorer_1920x1080.png`
- `evidence/transfer_explorer_700x900.png`
- `evidence/transfer_explorer_320x800.png`
- `evidence/active_draft_preview_1920x1080.png`

샘플 browser app에서 Explorer 이외 Admin overview API의 의도된 404는 발생하지만 Explorer API
요청은 성공했다. full server suite와 PostgreSQL E2E는 사용자 지시에 따라 실행하지 않았고
통과로 표현하지 않는다.

## 5. 상태와 다음 관문

기존 `bea0484` Audit 승인은 제한된 초기 범위에 대한 역사로 유지한다. 이번 전체 pending 계약은
아직 독립 Audit 전이므로 `COMPLETION_IN_REVIEW / NOT_APPROVED`다. exact commit을 Audit task
`01a00f3f-4249-7bf0-ab96-6d32c27273fe`에 제출하고 APPROVE 뒤에만 main 병합과 최종
`COMPLETE / APPROVED` 상태 동기화를 수행한다.
