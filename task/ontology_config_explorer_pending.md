# [Task] Ontology Config Explorer — 설정 선언 탐색·초안 편집 UI

> **상태:** 완료(COMPLETE / APPROVED)
> **우선순위:** 완료
> **등록:** 2026-08-17
> **착수 조건:** Ledger V2 Stage 7 제품 승인 및 cutover 종료
> **UI 기준본:** [ontology_config_explorer_reference.html](./ontology_config_explorer_reference.html)

## 완료 판정

- 승인 구현: `2d1ad863106fc228566cab1a386265957f5c3587`
- 최종 상태 동기화: `cbe139e1adae1c808bfb5774f24ae22ede1cf2ea`
- 독립 Audit: `APPROVE` 및 `STATUS SYNC ACK`
- 수락 근거: `ontology_config_explorer_plan/02_IMPLEMENTATION_AND_ACCEPTANCE.md`
- 인수인계: `docs/process/FORK_SESSION_BRIEF.md`

full server suite와 Explorer PostgreSQL E2E는 후속 사용자 지시에 따라 재실행하지 않았다.
변경 직접군, production build, 실제 브라우저 여정과 file-backed sample은 독립 Audit에서
검증됐다. 운영 config/DB write, reset/replay, migration, legacy 이동·삭제는 수행하지 않았다.

## 사용자 판정

Ontology 설정에서 Pack이 "predicate": "transferred_to@1"처럼 다른 선언을 참조할 때,
사용자가 그 정의와 사용처를 한 화면에서 탐색하고 안전하게 편집할 수 있어야 한다.

UI의 시각 스타일과 화면 구성은 위 기준본으로 확정한다. 다음 개발 세션은 기준본의 CSS,
색상, 간격, 3단 구성과 인터랙션을 임의로 재디자인하지 않는다. 반응형 대응, 접근성 결함,
실제 client2 통합에 필요한 최소 조정 외의 외형 변경은 사용자 재승인을 받는다.

단, 기준본의 **CSS와 화면 배치만 시각 정본**이다. 기준본 안의 하드코딩된 demo 데이터와
JavaScript 상태 처리는 구현 정본이 아니다. 현재 기준본에는 선택 대상을 바꿔도 breadcrumb와
연결 flow가 최초 transferred_to@1 경로로 남고, 초안을 저장하면 선택 항목만 draft 상태로
바뀌는 반면 상단 snapshot과 우측 무결성은 active compiled snapshot으로 남는 알려진
불일치가 있다. 실제 구현은 아래 상태·정합성 계약으로 이 결함을 제거해야 하며, demo 동작을
그대로 복사해서는 안 된다.

## 확정 화면 구성

1. **상단 도구 막대**
   - Ontology Explorer 제목
   - 선언 검색
   - 활성 compiled snapshot 상태
   - 초안 편집 진입
2. **왼쪽 Configuration 탐색 트리**
   - Packs, Vocabulary, Entities, Bindings 및 Ledger V2 Registry 선언
   - 선택 시 중앙 편집기와 오른쪽 Inspector가 같은 선언으로 동기화
3. **중앙 JSON 화면**
   - 원본 config JSON과 Source → Profile → Pack claim → Predicate 참조 흐름
   - 활성 snapshot은 읽기 전용
   - 별도 working draft에서만 편집
4. **오른쪽 Inspector**
   - Definition, Used by, Raw JSON
   - canonical JSON pointer, config 위치, compile validation 결과
   - 참조 선언과 역참조 사용처 이동

## 탐색 계약

- 컴파일된 Registry가 식별자로 인정한 **모든 선언 참조**를 링크로 표시한다.
  Predicate뿐 아니라 Entity, Pack, Profile, Preparer, Mapper, VerifiedJoin, SourcePlan도 같다.
- 링크 판정은 단순 @숫자 정규식 추측이 아니라 현재 LedgerSetupSnapshot의 Registry
  identity와 대조한다.
- 호버는 정의 종류·짧은 설명·선언 위치를 팝오버로 보여준다.
- 클릭은 Inspector에서 정의를 열고, 선언 위치로 이동할 수 있다.
- 선언 이동은 브라우저형 history를 쌓으며 **뒤로 가기**로 이전 JSON 위치와 선택 상태를
  복원한다.
- Used by는 Pack claim, Profile output, Entity domain/range 등 실제 역참조를 보여준다.

## 상태 정합성 최상위 계약

### 1. 서로 다른 상태를 한 필드에 섞지 않는다

프론트엔드 상태는 최소한 아래 다섯 축을 분리한다.

| 상태 축 | 의미 | 화면 소유 영역 |
|---|---|---|
| activeSnapshot | 현재 runtime이 사용하는 승인 snapshot hash·컴파일 시각·valid 상태 | 상단 snapshot 배지 |
| viewContext | 사용자가 지금 보고 있는 active 또는 draft preview와 그 context token | 중앙 상단·Inspector |
| selection | 현재 선택한 Registry ID·kind·canonical pointer | 트리·breadcrumb·flow·제목 |
| navigation | 선택에 도달한 참조 경로와 뒤로/앞으로 history | breadcrumb·flow·뒤로 가기 |
| draft | draft ID·대상·base snapshot·revision·dirty/save/review/stale 상태 | 편집 패널 전용 |

- activeSnapshot 상태를 draft 상태로 덮어쓰지 않는다.
- 선택 항목의 active compile 상태와 해당 항목에 존재하는 draft lifecycle 상태를 별도 배지로
  표시한다. 예: active · valid + draft · saved · not active.
- 검증 상태도 active compile validation과 draft preview validation을 섞지 않는다.
- 상단 snapshot 배지는 오직 실제 runtime active snapshot만 말한다. draft 저장·검토 요청으로
  이 배지의 hash나 상태가 바뀌면 결함이다.

### 2. 한 화면은 하나의 context token만 사용한다

Backend의 정의, raw JSON, Used by, flow, 검증 결과 응답은 모두 동일한 context token을
반환한다.

    active:<snapshot_hash>
    draft:<draft_id>:<revision>:<preview_snapshot_hash>

- 중앙 제목, JSON, breadcrumb, flow, Inspector, Used by, canonical pointer, 검증 결과는 한
  렌더에서 전부 같은 context token이어야 한다.
- 서로 다른 token의 응답을 조합해 화면을 그리지 않는다.
- 선택 ID, 요청 ID, context token 중 하나라도 현재 상태와 다른 늦은 응답은 폐기한다.
- draft가 아직 compile preview를 만들 수 없는 invalid/dirty 상태라면 flow와 무결성 패널은
  active 기준임을 명시하고 draft preview인 것처럼 표시하지 않는다.
- valid draft preview로 전환하면 관련 패널 전체를 draft token으로 함께 전환한다. 일부만
  draft 데이터를 보여주는 혼합 렌더는 금지한다.

### 3. 현재 보고 있는 대상의 단일 진실

selection은 Registry identity 하나를 단일 정본으로 삼는다. 다음 표시가 모두 selection과
일치해야 한다.

- 왼쪽 트리의 aria-current
- breadcrumb 마지막 항목
- 연결 flow에서 선택 강조된 노드
- 중앙 제목과 종류
- Definition/Used by/Raw JSON 내용
- 우측 canonical pointer와 config 경로
- 편집 대상 ID와 draft target

이 중 하나라도 다른 ID를 가리키면 화면을 성공 상태로 렌더하지 말고 context mismatch
오류로 처리한다. 문자열 라벨이 같다는 이유로 일치로 보지 않고 Registry kind + canonical ID
version을 비교한다.

우측 참조 무결성의 검사 문구도 selection kind와 context token으로 동적으로 생성한다.
Predicate를 볼 때의 subject/object 검사를 Entity, Pack, Profile 화면에 그대로 남기지 않는다.
Entity는 identity/signature와 사용처, Pack claim은 role/emission, Profile은 binding/source,
SourcePlan은 relation/cursor/preparer 계약을 보여준다. 해당 kind에 적용되지 않는 검사는
not-applicable로 명시하거나 응답에서 제외하되, 이전 선택의 검사 결과를 재사용하지 않는다.

### 4. 참조 연결 flow의 정합성

- flow는 HTML에 고정된 예시 경로가 아니라 현재 context token의 compiled reference graph에서
  계산한다.
- flow 제목 옆에 현재 보고 있는 기준을 ACTIVE <snapshot short hash> 또는
  DRAFT PREVIEW <draft revision / preview short hash>로 항상 표시한다.
- 선택 강조는 navigation 상태이고 compile 상태가 아니다. 각 노드는 선택 강조와 별개로
  현재 context의 상태를 표시한다.
  - active 보기: active/disabled와 valid/invalid/unresolved
  - draft preview: unchanged/modified/added/removed와 valid/invalid/unresolved
- draft preview의 modified/added/removed는 active snapshot과 preview snapshot의 canonical
  ID + normalized definition hash 차이로 계산한다. 화면 문자열 비교로 추측하지 않는다.
- edge도 resolved/unresolved/wrong-kind/signature-mismatch 상태를 가지며 실패 edge에는 실제
  오류 JSON pointer를 표시한다.
- 각 노드는 Registry identity, kind, config path, canonical pointer를 가진다.
- 각 edge는 from ID, to ID, 참조 종류, 그 참조가 실제로 적힌 JSON pointer를 가진다.
- Pack claim의 predicate, Profile의 Pack/claim 사용, Entity의 domain/range,
  SourcePlan의 Profile/Preparer 연결 등 모든 edge는 실제 config pointer로 증명돼야 한다.
- 정방향 참조 A → B가 있으면 B의 Used by에 같은 근거 pointer를 가진 역참조가 정확히 한 번
  존재해야 한다.
- 끊어진 참조는 가짜 노드를 만들지 않고 unresolved 상태와 원래 JSON pointer를 보여준다.
- 여러 경로가 있는 대상을 임의로 한 줄 경로로 합쳐 허구의 인과를 만들지 않는다. 경로 후보를
  분리하고 사용자가 선택한 현재 경로만 breadcrumb와 주 flow에 표시한다.
- 트리나 검색에서 바로 선택하면 이전 대상의 flow를 남기지 않는다. 단독 선택을 root로 새
  navigation context를 만들고, 관련 inbound/outbound 연결은 별도 목록으로 보여준다.
- 링크 클릭은 현재 항목 → 참조 종류 → 대상 항목을 navigation history에 push한다.
- Used by 클릭은 역참조 근거를 포함한 경로를 push한다.
- flow 노드 클릭, breadcrumb 클릭, 뒤로/앞으로 가기는 선택 ID, 경로 ID, 탭, view token,
  스크롤/커서 위치를 함께 복원한다.

### 5. draft와 현재 보기의 일치

- draft는 target Registry ID와 base snapshot hash를 고정한다. 편집 도중 다른 선언을
  선택했다고 draft target이 조용히 바뀌면 안 된다.
- dirty draft가 있는 상태에서 이동할 때는 유지·폐기·취소 중 명시적 선택을 받는다.
- 초안 저장 뒤 active 정의의 status는 그대로이고 draft status만 saved · not active가 된다.
- 검토 요청 뒤에도 active snapshot은 그대로이며 draft status만 review requested가 된다.
- 검토 요청된 revision은 수정 불가로 고정하고, 재편집은 새 revision을 만든다.
- base snapshot이 바뀌면 draft는 stale/conflict가 되며 최신 snapshot에 대한 재검증 또는
  rebase 전에는 활성화할 수 없다.
- active 보기와 draft preview를 명시적으로 전환할 수 있어야 하며 현재 mode를 제목 주변에
  계속 표시한다.
- draft preview의 Used by와 영향 범위는 저장된 active 역참조가 아니라 preview compile 결과로
  계산한다.

## API·데이터 정합성 계약

Backend는 UI가 여러 응답을 추측으로 조립하지 않도록 최소한 아래 의미를 제공한다.

- snapshot hash와 context token
- selected definition의 canonical ID, Registry kind, version, config path, JSON pointer
- active raw JSON과 compiled definition의 명시적 구분
- 정방향 reference edge와 역방향 Used by edge
- 현재 navigation route를 구성할 수 있는 edge 근거
- compile validation 결과와 오류 JSON pointer
- draft ID, target ID, base snapshot hash, revision, lifecycle status
- draft preview snapshot hash와 영향받는 선언 집합

서버는 다음 불변식을 검증한다.

1. 모든 resolved edge의 양 끝 Registry identity가 같은 snapshot에 존재한다.
2. 정방향 edge와 Used by 역참조가 pointer 기준으로 서로 대칭이다.
3. canonical pointer가 실제 source config의 해당 선언을 가리킨다.
4. 한 응답 묶음의 모든 객체가 같은 context token을 가진다.
5. draft preview는 active snapshot을 변형하지 않고 별도 immutable snapshot으로 컴파일된다.
6. active 교체는 expected base hash를 사용한 compare-and-swap 방식으로 stale 승인을 거절한다.
7. 여러 서버 프로세스가 활성화 완료 뒤 같은 snapshot hash를 보고하기 전에는 UI가 전환
   완료로 표시하지 않는다.

## 편집·활성화 안전 계약

- 활성 compiled snapshot을 직접 수정하지 않는다.
- 초안 편집 → 전체 Bundle 검증 → 영향받는 참조 표시 → 초안 저장 → 검토 요청 → 승인 후
  활성화 순서를 지킨다.
- 초안 저장은 runtime 활성화를 뜻하지 않는다.
- JSON 문법뿐 아니라 Ledger V2의 config-only, trusted implementation, Entity/Predicate
  signature, virtual join 상속, unsafe key 차단을 동일 compiler로 재검증한다.
- 검증 실패 시 부분 저장·부분 활성화 없이 fail-closed한다.
- 활성화 시 manifest 허용 경로 밖 파일 접근을 금지하고, 원자적 교체와 snapshot hash를
  보존한다.
- runtime/store/cursor/DB reset은 이 UI의 암묵적 부작용이 아니다. 별도 승인 없이 수행하지
  않는다.

## 구현 실행 순서

다음 순서를 건너뛰지 않는다.

1. 기존 Ledger setup/admin API, Registry와 snapshot 객체, reload 경로, client2 모듈 구조를
   조사하고 호출·소유 문서·테스트 영향표를 먼저 작성한다.
2. active/draft/view/selection/navigation 상태 머신과 context token 계약을 코드보다 먼저
   테스트 가능한 표로 확정한다.
3. compiled reference graph와 역참조 인덱스를 Backend read model로 구현하고 정합성 테스트를
   먼저 통과시킨다.
4. active snapshot read API를 구현한 뒤 mock이 아닌 실제 config로 transferred_to@1 계열
   탐색 E2E를 만든다.
5. draft 저장·preview compile·review·activate를 구현한다. active와 draft 분리 테스트가
   통과하기 전 UI 편집 완료를 선언하지 않는다.
6. client2에 기준본 CSS와 3단 구성을 옮기고 단일 상태 store/reducer에서 모든 패널을
   렌더한다. 각 패널이 따로 selected 상태를 소유하지 않는다.
7. async stale response, history 복원, 다중 경로, unresolved 참조, snapshot 교체 중 draft
   stale을 interaction harness로 검증한다.
8. 실제 서버와 브라우저에서 시각 대조·키보드·반응형·오류 상태를 확인한다.
9. 관련 리빙 문서, API 계약, QA 기능 인벤토리, history와 handoff evidence를 갱신한다.

## 구현 범위

### Backend

- 활성 snapshot 선언 목록·정의·canonical pointer 조회
- 선언별 정방향/역방향 참조 조회
- 원본 JSON과 compiled view 구분 조회
- working draft 검증과 영향 범위 dry-run
- 초안 저장·검토 상태 관리
- 활성화는 기존 Ledger V2 승인·reload 경계를 재사용
- reference graph/Used by를 매 요청마다 전체 스캔하지 않고 snapshot compile 시 결정적으로
  인덱싱
- 각 조회 응답에 context token과 snapshot hash 포함

구체 API 경로는 구현 단계에서 기존 Ledger setup/admin 라우트와 충돌 여부를 조사한 뒤
결정한다. 임의 파일 브라우저나 임의 경로 쓰기 API를 만들지 않는다.

### Frontend

- client2의 전용 Ontology Explorer 화면
- 탐색 트리, JSON 편집기, 참조 팝오버, Inspector, history/back
- 검색 결과는 stale 응답 가드를 적용하고, 대량 선언은 서버 검색·페이지 방식으로 제한
- 패널 로직은 전용 모듈로 분리하며 main.js에는 초기화·바인딩만 둔다.
- 트리·flow·Inspector·편집기가 공유하는 단일 상태 store/reducer 사용
- 정의/사용처/flow API 요청에 selection + context token + request generation stale guard 적용

## 수락 기준

- 기준본과 동일한 CSS·레이아웃·상호작용을 데스크톱 폭에서 재현한다.
- Pack의 transferred_to@1에서 Vocabulary 정의와 모든 사용처로 이동할 수 있다.
- DTJob@1, LotSlot@1, DTDie@1 등 Entity 참조도 같은 방식으로 동작한다.
- 선언 이동을 여러 번 한 뒤 뒤로 가기가 선택·파일·스크롤 위치를 순서대로 복원한다.
- 잘못된 참조, signature 불일치, unsafe key, manifest 밖 경로는 활성화 전에 거절된다.
- 초안 저장만으로 active snapshot hash와 runtime 동작이 바뀌지 않는다.
- 정상 활성화 뒤 모든 프로세스가 동일 snapshot hash를 본다.
- API 계약 테스트, Registry/validator 회귀 테스트, UI interaction harness, 반응형·키보드
  접근성 검증을 통과한다.

## 완료 판정 게이트

아래 항목은 선택 사항이 아니다. 하나라도 증명되지 않으면 상태는 IN_PROGRESS 또는
IN_REVIEW이며 DONE/APPROVED로 보고하지 않는다.

### A. 참조 그래프

- [x] 활성 snapshot의 모든 Registry entry를 열거하고 모든 참조 필드를 graph edge로
      추출했다.
- [x] 모든 resolved edge가 실제 대상과 JSON pointer를 가진다.
- [x] 모든 정방향 edge와 Used by 역참조가 1:1로 대칭이며 중복이 없다.
- [x] Entity, Predicate, Pack, claim, Profile, Preparer, Mapper, VerifiedJoin, SourcePlan을
      각각 최소 1개 이상 실제 config로 탐색했다.
- [x] unresolved, wrong kind, wrong version, signature mismatch를 서로 다른 오류로 표시한다.
- [x] 다중 inbound/outbound 경로를 허구의 단일 선형 flow로 합치지 않는다.

### B. 현재 보기

- [x] 트리, breadcrumb, flow 강조, 제목, 탭 내용, pointer, config path, 편집 대상이 항상 같은
      canonical selection을 가리킨다.
- [x] 트리 직접 선택 시 이전 flow가 남지 않는다.
- [x] 참조 링크와 Used by 링크 이동 시 실제 edge 근거가 navigation history에 남는다.
- [x] 뒤로/앞으로 이동이 selection, route, tab, active/draft mode, 스크롤/커서 위치를
      복원한다.
- [x] 검색 중 늦게 도착한 응답이 현재 선택이나 Inspector를 덮지 않는다.
- [x] 현재 selection이 새 snapshot에서 사라지면 이전 내용을 계속 보여주지 않고 명시적인
      removed/unresolved 상태를 표시한다.
- [x] flow 상단의 ACTIVE/DRAFT PREVIEW 기준, 각 node/edge 상태, 우측 무결성 결과가 모두
      현재 context token과 selection kind에서 계산된다.
- [x] Predicate에서 Entity로 이동했을 때 predicate 전용 subject/object 검사 문구가 남지
      않는다.

### C. active·draft 분리

- [x] 초안 저장 전후 active snapshot hash와 active raw/compiled view가 byte-equivalent다.
- [x] draft saved, review requested, invalid, stale, conflict 상태가 active 상태와 별도 필드로
      표시된다.
- [x] invalid draft에서는 draft flow/무결성 결과를 꾸며내지 않는다.
- [x] valid draft preview에서는 제목부터 Used by까지 모든 패널이 동일 draft context token을
      사용한다.
- [x] draft preview flow가 active 대비 unchanged/modified/added/removed를 normalized
      definition hash 기준으로 정확히 표시한다.
- [x] active와 draft token을 섞은 fixture를 주입하면 UI가 성공 렌더를 거절한다.
- [x] base snapshot 변경 뒤 stale draft 활성화가 서버에서 거절된다.
- [x] 검토 요청한 revision이 이후 입력으로 조용히 바뀌지 않는다.
- [x] 승인된 활성화 뒤 모든 프로세스의 snapshot hash 일치를 확인한 후에만 완료를 표시한다.

### D. UI 기준본·접근성

- [x] 기준본의 CSS, 색상, 간격, 3단 배치, 정보 위계를 데스크톱 폭에서 시각 대조했다.
- [x] 승인 없는 대시보드·그래프 중심 재디자인이 없다.
- [x] 320px 이상 반응형에서 패널 겹침·클리핑·가로 페이지 overflow가 없다.
- [x] 모든 참조 링크, 탭, 트리, 뒤로 가기, 편집 동작을 키보드로 수행할 수 있다.
- [x] aria-current, aria-selected, aria-pressed가 실제 selection/view 상태와 일치한다.
- [x] 색상만으로 active/draft/invalid/stale을 구분하지 않는다.

### E. 회귀·성능·증거

- [x] server 관련 단위·계약·PostgreSQL 테스트와 기존 Ledger V2 회귀 테스트가 통과한다.
- [x] client2 interaction harness와 package.json의 전체 prebuild/build gate가 통과한다.
- [x] reference graph 조회가 요청당 config 전체 재파싱 또는 N+1을 만들지 않는다.
- [x] 대량 Registry fixture에서 검색·Used by·flow 응답의 시간과 payload 상한을 기록한다.
- [x] 실제 server/config/ontology 입력으로 최소 transferred_to@1 → Pack claim → Profile →
      SourcePlan 왕복 시나리오를 브라우저에서 검증한다.
- [x] 기준본과의 시각 비교 캡처, 테스트 명령·통과 수, exact commit, 미실행 테스트와 이유를
      acceptance evidence에 남긴다.
- [x] API/상태/화면 동작을 관련 리빙 문서와 QA 기능 인벤토리에 반영하고 history index를
      재생성한다.

### 완료로 인정하지 않는 것

- 정적 HTML 목업만 완성
- frontend와 mock 데이터만 연결
- 참조를 @version 문자열 정규식으로만 링크
- Inspector만 바뀌고 breadcrumb/flow/우측 무결성이 이전 선택에 남음
- draft raw JSON만 바뀌고 preview reference graph는 active 것을 재사용
- 일부 pytest 또는 npm build만 통과하고 전체 관련 gate 결과가 없음
- 실제 config·실제 서버·브라우저 왕복 검증 없이 unit test만 통과

## 비범위

- Ledger V2 Stage 7 완료 전 선행 구현
- trace/lot-slot 검색 API 및 생산 계보 복원 기능
- Mapper 실행, 원장 write, cursor 이동, DB reset
- 기준본과 다른 대시보드·그래프 중심 재디자인

## 완료 이후

`Ledger V2 Stage 7 승인 → Ontology Config Explorer`까지 완료했다. lot-slot/DT/Core 계보 검색
API·간단 검색 화면은 이 task의 완료 조건이 아니며, 사용자가 다시 범위를 열 때 별도 task와
Audit 관문으로 진행한다.
