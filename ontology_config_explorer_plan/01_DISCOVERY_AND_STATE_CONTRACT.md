# Ontology Config Explorer — 조사·상태 계약

> 상태: `COMPLETION_IN_REVIEW / NOT_APPROVED`
> 기준: Ledger V2 `COMPLETE / APPROVED`; Explorer의 제한 범위 승인 기준 `af2a1d3`
> 시각 정본: `task/ontology_config_explorer_reference.html`

## 1. 완료 범위를 다시 연 이유

`bea0484`/`af2a1d3`은 compiled Registry 탐색과 기본 draft lifecycle을 승인했다. 그러나
`task/ontology_config_explorer_pending.md`의 전체 계약에는 Binding·SourcePlan, 참조 오류의 세부
분류, 정확한 경로 history, dirty 이동 3선택, active/draft 비교, immutable review→revise,
activation consumer convergence, file-backed transfer 예제, payload·반응형 근거가 추가로 있다.
따라서 이전 승인은 역사로 보존하되 이 전체 계약은 새 exact commit의 Audit 전까지 완료로
표현하지 않는다.

## 2. 소유 경계

| 관심사 | 정본/구현 | Explorer 계약 |
|---|---|---|
| manifest·strict validation | `server/ledger/setup_bundle.py` | 별도 validator 없이 재사용 |
| immutable Registry·SourcePlan | `server/ledger/setup_registry.py` | node identity와 compiled definition의 유일한 원천 |
| trusted compile | `server/ledger/cutover_v2.py` | active와 draft preview가 같은 compiler 사용 |
| graph/read model | `server/ledger/config_explorer.py` | Registry·Binding·SourcePlan 정/역참조와 정확한 pointer |
| draft/activation | `server/ledger/config_drafts.py` | target/base 고정, revision 불변, CAS/atomic activation, consumer convergence |
| service/API | `server/ledger/config_explorer_service.py`, 전용 router | active/draft 한-context 응답과 strict write route |
| client state/view | `client2/src/ontology_explorer_*` | 단일 selection/history/draft 상태와 3단 화면 |
| file-backed 예제 | `server/config/sample/ontology/transfer_explorer/` | 운영 manifest 밖에서 transfer 전체 경로 재현 |

Legacy ledger admin, mapper/translator/cursor/gate/store/DB schema는 이 화면이 소유하지 않는다.
샘플 설정도 운영 `server/config/ontology/manifest.json`에 연결하지 않는다.

## 3. Read model과 참조 상태

snapshot당 한 번 immutable index를 만든다.

- node kinds: `source_plan`, `profile`, `mapping`, `binding`, `pack`, `claim`, `predicate`,
  `entity`, `preparer`, `mapper`, `verified_join`, `table`
- edge는 `(from,to,reference_kind,json_pointer)`가 정·역방향에서 동일하다.
- 참조 상태는 `resolved`, `wrong_kind`, `wrong_version`, `signature_mismatch`, `unresolved`로
  닫혀 있으며, 오류는 해당 leaf JSON pointer를 보존한다.
- hover/focus 설명은 node kind·canonical id·설명·config path를 같은 compiled context에서 읽는다.
- 검색/직접 참조/경로는 서버에서 상한을 적용하고 total·truncated를 별도로 반환한다.

## 4. 단일 상태 축

| 축 | 필드 | 불변식 |
|---|---|---|
| activeSnapshot | hash, valid | draft 저장·검토로 변경 금지 |
| viewContext | active/draft_preview, contextToken, previewHash | 한 렌더의 모든 collection token 동일 |
| selection | kind, canonicalId, pointer | tree·breadcrumb·flow·Inspector가 동일 |
| navigation | key, exact route, tab, mode, scroll, editor cursor, token | 뒤/앞 이동 시 원자적으로 복원 |
| draft | target, baseHash, revision, lifecycle, dirty | target/base 고정, reviewed revision 읽기 전용 |

늦은 response, 요청 selection 불일치, collection token 혼합은 화면 상태를 갱신하지 않는다.
dirty draft에서 다른 선언으로 이동할 때는 `초안 유지 / 초안 폐기 / 이동 취소` 중 하나를
명시적으로 선택한다.

## 5. 초안·활성화 상태 전이

```text
ACTIVE
  -> CREATE_DRAFT(target, baseHash)
  -> EDITING(revision N)
  -> SAVE
       invalid: active fallback + structured errors
       valid: DRAFT_PREVIEW(same compiler)
  -> REQUEST_REVIEW(revision N immutable/read-only)
  -> REVISE(revision N+1 editing) | ACTIVATE(exact reviewed revision)
  -> base/hash CAS + atomic replace + reload + every declared consumer hash convergence
       mismatch/empty: rollback + conflict
       match: ACTIVE(new hash)
```

stale base와 write/CAS conflict는 구분한다. reviewed revision은 PUT으로 수정하지 않으며 새
편집은 `/revise`로만 연다. 활성화는 persistent consumer 목록이 비거나 하나라도 새 hash와
다르면 성공하지 않는다.

## 6. API 계약

- `GET /admin/ontology-explorer/view`: `view_mode=active|draft_preview`, exact route/context 포함
- `POST /admin/ontology-explorer/drafts`: target/base 고정
- `PUT /admin/ontology-explorer/drafts/{id}`: expected revision 저장 + 전체 Bundle compile
- `POST .../{id}/review`: exact revision 동결
- `POST .../{id}/revise`: reviewed revision에서 새 editing revision 생성
- `DELETE .../{id}`: expected revision 폐기
- `POST .../{id}/activate`: reviewed revision·base·preview·consumer convergence 확인

임의 경로·JSON pointer·catalog/physical join을 쓰기 입력으로 받지 않는다. 유효하지 않은 draft
preview 요청은 active context로 명시적 fallback하며 draft graph를 꾸며내지 않는다.

## 7. 수락 경계

- file-backed sample은 `CoreDie -> DTDie -> BondComponent -> FinalChip`, `DTJob`, `LotSlot`,
  `transferred_to@1`, VerifiedJoin, SourcePlan을 production loader/compiler로 만든다.
- 10,000-node/9,999-edge fixture는 2초, 213 node, 1.5 MB 상한을 검증한다.
- browser는 1920×1080, 700×900, 320×800에서 tree/flow/Inspector와 overflow를 확인한다.
- Mapper 실행, Ledger write, cursor 이동, DB reset/replay/migration, legacy 이동·삭제는 비범위다.
