# Ontology Config Explorer — 조사·상태 계약

> 상태: `IMPLEMENTATION_READY`
> 기준: Ledger V2 `COMPLETE / APPROVED` (`f516268eadae5505c586ce5235e76dd729c1e573`)
> 시각 정본: `task/ontology_config_explorer_reference.html`

## 1. 현재 소유 경계

| 관심사 | 현재 정본 | Explorer 영향 |
|---|---|---|
| manifest load·strict validation | `server/ledger/setup_bundle.py` | 그대로 재사용, 별도 validator 금지 |
| immutable Registry·snapshot | `server/ledger/setup_registry.py` | active/draft preview graph의 유일한 identity 원천 |
| trusted runtime compile | `server/ledger/cutover_v2.py` | active 및 preview 모두 같은 compile path 사용 |
| legacy source/predicate admin | `server/ledger_admin.py`, `/admin/ledger/*` | 호환 유지, Explorer가 대체하거나 호출하지 않음 |
| reload/outbox | `server/main.py::reload_system_configs` | 승인 활성화 뒤 기존 reload 경계만 호출 |
| admin 인증 | `server/admin_auth.py`, `adminFetch()` | read는 admin token, draft write/review/activate는 strict token |
| admin 화면 | `client2/admin.html`, `client2/src/admin.js` | full-bleed `#ontology` 탭만 추가 |
| 기존 선언 지도 | `client2/src/ledger_map_panel.js` | 무변경; Explorer는 Registry config 전용 화면 |

기존 `ledger_setup.js`는 legacy flat source/predicate의 dry-run·save 화면이다. V2 snapshot의
Registry identity, reference graph, context token, draft preview를 소유하지 않으므로 새 화면의
상태 저장소나 graph backend로 재사용하지 않는다.

## 2. 현재 active config 실측

- snapshot: `57d36c07271a019242722cc4627f1c0a9c6b477e632f29f32034e331928b0da0`
- registries: vocabulary 4, entities 2, packs 1, profiles 1, preparers 1, mappers 1,
  sources 1, verified joins 0
- 실제 탐색 왕복: `lot_event → lot-event@1 → lot-lineage@1/<claim> → predicate@1`

현재 active config에는 기준본 demo의 `transferred_to@1`, `DTJob@1`, `LotSlot@1`, `DTDie@1`가
없다. 화면 검증을 위해 거짓 운영 선언을 추가하지 않는다. 범용 fixture에서는 해당 ID를
검증하고 실제 서버 왕복은 현재 존재하는 lot-lineage 경로로 검증한다. 이 ID들이 정식 config에
등재되면 화면/API 변경 없이 같은 탐색 계약을 적용한다.

## 3. Backend read model

snapshot compile 시 한 번 다음 immutable index를 만든다.

- `nodes[canonical identity]`: kind, version, source file, canonical JSON pointer, raw JSON,
  compiled definition, normalized definition hash, validation
- `outbound[id]`: from/to identity, reference kind, evidence pointer, status
- `inbound[id]`: outbound edge를 pointer 기준으로 정확히 뒤집은 Used by
- `search`: kind + canonical ID 정렬 인덱스

HTTP 요청마다 config 전체를 재파싱하지 않는다. active snapshot hash 또는 draft preview
snapshot hash를 cache key로 사용한다. resolved edge의 양 끝은 같은 snapshot registry에
존재해야 하며 outbound/inbound는 `(from,to,kind,pointer)`가 1:1이다.

## 4. 단일 상태 축

| 축 | 필드 | 불변식 |
|---|---|---|
| activeSnapshot | hash, compiled_at, valid | draft 저장·검토로 변경 금지 |
| viewContext | mode, contextToken, previewHash, fallbackReason | 한 렌더의 모든 payload token 동일 |
| selection | kind, canonicalId, pointer | 트리·제목·Inspector·flow·편집 대상 동일 |
| navigation | entries, index, route edge, tab, scroll/cursor | 뒤/앞 이동 시 원자적으로 복원 |
| draft | id, targetId, baseHash, revision, lifecycle, dirty | target/base 고정, review revision 불변 |

UI는 `ontology_explorer_store.js` reducer 하나만 이 상태를 변경한다. 패널별 selected 상태는
금지한다. 모든 request는 `{generation, selectionId, contextToken}`을 캡처하고 하나라도 현재와
다르면 응답을 폐기한다.

## 5. 상태 전이

```text
ACTIVE_VIEW
  → CREATE_DRAFT(target, baseHash)
  → DRAFT_EDITING(revision N, dirty)
  → SAVE
      ├─ invalid: DRAFT_INVALID (active context 유지, preview 꾸미기 금지)
      └─ valid: DRAFT_SAVED + DRAFT_PREVIEW(context token 전체 전환)
  → REQUEST_REVIEW: REVIEW_REQUESTED(revision N immutable)
  → ACTIVATE(expected baseHash)
      ├─ base changed: STALE/CONFLICT
      └─ CAS replace + reload + active hash 확인: ACTIVE_VIEW(new hash)
```

dirty draft에서 다른 선언으로 이동할 때는 유지·폐기·취소를 명시적으로 선택한다. 저장은
active 파일·snapshot을 바꾸지 않는다. activation만 manifest 허용 파일의 해당 declaration을
CAS·atomic replace하고 기존 reload 경계를 호출한다.

## 6. API 경계

- `GET /admin/ontology-explorer/view`: active 또는 valid draft preview의 한-token 화면 bundle
- `POST /admin/ontology-explorer/drafts`: target/base 고정 draft 생성
- `PUT /admin/ontology-explorer/drafts/{id}`: expected revision 저장·전체 Bundle preview compile
- `POST /admin/ontology-explorer/drafts/{id}/review`: revision 동결
- `POST /admin/ontology-explorer/drafts/{id}/activate`: expected base CAS 활성화

임의 파일 경로와 임의 JSON pointer를 쓰기 API 인자로 받지 않는다. 서버가 active graph의
canonical identity에서 파일·pointer를 해소한다.

## 7. 변경·테스트 영향표

| 범위 | 신규/수정 | 필수 검증 |
|---|---|---|
| pure backend | `server/ledger/config_explorer.py` | graph 대칭·pointer·kind·diff·결정성·scale |
| draft store | `server/ledger/config_drafts.py` | active byte 불변·revision·stale·atomic CAS |
| admin API | 전용 router + `server/main.py` include | token/context/error 계약 |
| client state/view | 전용 store/view/api 모듈 | mismatch 거절·history·async stale·draft 분리 |
| admin host | `admin.html`, `admin.js` 최소 배선 | 탭 routing·full bleed·기존 탭 회귀 |
| CSS | 기준본 selector를 전용 CSS로 이동 | 1920 desktop·320px·keyboard/ARIA |
| build | Vite dist | prebuild/build 전체 gate |

Mapper 실행, Ledger write, cursor 이동, DB reset, legacy 삭제는 이 작업의 비범위다.
