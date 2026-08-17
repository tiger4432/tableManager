# Ontology Config Explorer — compiled 선언을 탐색·검토하는 표면

## 현상

Ledger V2는 manifest→Bundle→Registry→immutable snapshot까지 완성됐지만 운영자는 JSON 파일을
따로 열어 Source/Profile/Pack/Vocabulary 연결을 머릿속에서 맞춰야 했다. 기존 원장 선언 화면은
legacy source/predicate 편집기라 V2 Registry identity, 역참조, draft preview snapshot을 답하지
못했다. 제공된 기준 HTML도 선택을 바꾼 뒤 flow가 최초 predicate에 남는 서로 다른 상태의
혼합 결함을 갖고 있었다.

## 근본 원인

- 구성 요소마다 선택 상태를 따로 두면 tree/flow/Inspector/편집 대상이 갈라진다.
- config JSON을 HTTP 요청마다 다시 읽으면 참조마다 재parse/N+1이 생긴다.
- draft raw만 바꾸고 active graph를 재사용하면 존재하지 않는 preview를 화면이 꾸민다.
- 문자열 `@version` 링크는 Registry가 실제로 승인한 identity와 wrong-kind를 구별하지 못한다.

## 수정

- compiled snapshot 하나에서 Registry node와 pointer-bearing reference edge를 한 번 인덱싱하고
  정방향/Used by를 동일 edge identity로 만들었다.
- 응답 전체를 `active:<hash>` 또는 `draft:<id>:<revision>:<previewhash>` 하나로 묶고 client
  reducer가 active/view/selection/navigation/draft를 분리한다. request generation과 expected
  context가 어긋난 응답은 성공 렌더하지 않는다.
- draft 저장은 active bytes를 건드리지 않고 동일 validator/compiler로 전체 preview를 만든다.
  invalid/stale은 active fallback, activation은 exact review revision + base/hash CAS + backup +
  atomic replace + reload/hash 확인이다.
- Admin `#ontology`에 기준본 3단 정보 위계를 옮기고 server-side search, 독립 flow, Used by,
  exact pointer, kind별 integrity, keyboard/ARIA를 연결했다.
- 10,000-node/9,999-inbound fixture에서 reference 응답을 200 edge, 213 node 이하로 제한하고
  total/truncated를 별도 보고한다.

## 핵심 반례

- active/draft token이 섞인 응답은 client에서 `context_mismatch`로 거절된다.
- 늦은 request generation은 현재 selection을 덮지 못한다.
- 새 snapshot에서 사라진 selection은 옛 Inspector를 남기지 않는다.
- catalog declaration을 draft target으로 주면 `unsupported_draft_target`이다.
- base snapshot이 바뀐 draft는 active fallback에서 `stale`로 표시되고 활성화되지 않는다.
- 초안 lifecycle 5개 write route는 전부 strict admin gate 뒤에 있다.

## 검증

- Backend/Registry/Ledger V2 직접 영향군: `411 passed, 1 skipped`.
- Explorer UI state harness: `17 assertions, 0 failed`.
- client contracts: 7개 통과. 전체 gated harness 통과(기존 known-red 5개는 그대로 실행·보고).
- 실제 브라우저: active snapshot 24개, `derived` 검색 1개, predicate 3개 독립 경로,
  1920×1080 및 Explorer root 700/320px overflow 0.
- full server suite와 PostgreSQL 전용 테스트는 사용자 범위 지시에 따라 실행하지 않았다.
- 운영 ontology config, DB schema/data, mapper/translator/cursor/gate/store, reset/replay/legacy 파일은
  변경하지 않았다.

## 현재 상태

`ONTOLOGY_CONFIG_EXPLORER_IN_REVIEW / NOT_APPROVED`. exact commit을 지정 독립 Audit에 제출한 뒤
승인 여부를 동기화한다. 현재 active config에 없는 DT/transfer/VerifiedJoin을 시연 목적으로
추가하지 않았고 범용 fixture에서만 그 identity 경로를 검증했다.
