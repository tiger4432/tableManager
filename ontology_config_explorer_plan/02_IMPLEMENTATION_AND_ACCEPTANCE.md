# Ontology Config Explorer — 구현·수락 근거

> 상태: `COMPLETE / APPROVED`
> 기준 active snapshot: `57d36c07271a019242722cc4627f1c0a9c6b477e632f29f32034e331928b0da0`
> 파괴 작업: DB write/reset/replay, legacy 이동·삭제 모두 0

## 1. 구현 결과

- `config_explorer.py`: 승인된 Ledger V2 snapshot에서 Registry entry와 실제 참조를 한 번
  인덱싱한다. 정방향/역참조는 같은 edge identity와 JSON pointer를 공유한다.
- `config_explorer_service.py`: 파일 stamp가 바뀔 때만 active setup/index를 다시 만든다.
  한 응답의 active/draft context token을 전수 검사한다.
- `config_drafts.py`: manifest가 고른 `ledger_config.json` 선언만 초안화한다. 저장은 active
  파일을 바꾸지 않고, 같은 compiler로 전체 Bundle preview를 만든다. 검토 revision을 동결하고
  활성화는 base hash CAS, 백업, atomic replace, reload, 결과 hash 확인 순서다.
- `ontology_config_explorer_router.py`: 읽기 1개와 strict-token 초안 lifecycle API를 제공한다.
- `ontology_explorer_store.js`: active snapshot, view context, selection, navigation, draft를 분리한
  단일 reducer다. request generation과 context token이 다른 응답은 성공 렌더하지 않는다.
- `ontology_explorer_view.js`: 검색 목록, 독립 경로 flow, Inspector, Used by, kind별 integrity,
  draft 편집을 같은 selection으로 렌더한다. 문자열을 HTML로 주입하지 않는다.

## 2. API

| Method | Path | 계약 |
|---|---|---|
| GET | `/admin/ontology-explorer/view` | `selection,q,page,limit,reference_limit,context_token,draft_id,revision`; active 또는 valid draft preview 한 context |
| POST | `/admin/ontology-explorer/drafts` | `{target_key,base_snapshot_hash}`; target/base 고정 |
| PUT | `/admin/ontology-explorer/drafts/{id}` | `{expected_revision,raw}`; JSON parse + 전체 Bundle compile |
| POST | `/admin/ontology-explorer/drafts/{id}/review` | `{expected_revision}`; exact revision 동결 |
| DELETE | `/admin/ontology-explorer/drafts/{id}` | `expected_revision`; 활성화 전 초안 폐기 |
| POST | `/admin/ontology-explorer/drafts/{id}/activate` | `{expected_revision}`; review/base/hash CAS |

읽기 응답은 `active:<hash>` 또는 `draft:<id>:<revision>:<preview-hash>` 하나만 사용한다.
검색 목록은 `limit≤500`, 직접 참조는 `reference_limit≤500`이며 전체 수와 잘림 여부를 별도로
답한다. 임의 파일 경로나 임의 JSON pointer는 쓰기 입력이 아니다.

## 3. 실제·범용 검증

- 실제 운영 선언 24개를 화면에 열거했다: source 1, profile 1, mappings 6, pack 1,
  claims 6, vocabulary 4, entities 2, preparer 1, mapper 1, table 1.
- 실제 왕복: `lot_event → lot-event@1 → lot-lineage@1/<claim> → predicate@1`.
- 현재 active config에는 VerifiedJoin과 DT/transfer 선언이 없다. 거짓 운영 선언을 추가하지
  않았다. 범용 fixture에서 `CoreDie@1`, `ProcessCell@1`, `transferred_to@1`과 별도 Pack/Claim을
  같은 Registry 경로로 compile·탐색한다.
- 10,000-node/9,999-inbound fixture에서 search total은 10,000, Used by total은 9,999를
  보존하고 응답은 200 edge, 213 node 이하, JSON 1.5 MB 미만으로 제한한다. 테스트 시간 상한은
  2초다.
- 브라우저 실측: 1920×1080에서 기준본의 3단 정보 위계, 실제 24개 목록, 독립 flow,
  Inspector/Integrity를 확인했다. 700px과 320px에서 Explorer root의 가로 overflow는 0이다.
  320px의 기존 Admin header는 이 기능 밖의 기존 410px 최소 폭을 유지한다.

## 4. 안전 경계

- active cache는 draft save/review로 바뀌지 않는다.
- invalid/stale draft는 active fallback만 보여 주며 draft flow를 꾸미지 않는다.
- catalog/physical verified join 파일은 read-only다.
- 활성화 전 strict token, review revision, base snapshot, fresh preview hash를 모두 확인한다.
- mapper/translator/cursor/gate/store/DB schema와 운영 ontology config는 변경하지 않았다.
- PostgreSQL 전용 테스트와 full server suite는 실행하지 않았다. 이 기능은 DB를 읽지 않으며,
  사용자 지시에 따라 직접 영향군만 검증한다.

## 5. Audit 판정

현재 active config에 없는 `transferred_to@1`·VerifiedJoin을 운영 선언으로 추가하지 않은 판단과,
활성화 뒤 지속 snapshot 소비자가 Explorer API 하나이고 backfill은 실행 경계마다 재compile하는
현행 convergence 계약을 독립 Audit이 exact commit `bea0484cd8ab99aab8b4155e7dd5c1178df1b22a`
에서 검수해 `APPROVE`했다. 제품 상태도 사용자 상설 승인 규칙에 따라 `COMPLETE / APPROVED`로
동기화했으며 main에 fast-forward 병합했다.
