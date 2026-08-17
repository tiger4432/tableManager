# 모든 단계 공통 규칙

## 1. 한 의미, 한 소유자

| 의미 | 단독 소유자 |
|---|---|
| predicate의 subject/object 최종 서명 | VocabularyRegistry |
| entity type의 identity key | EntityTypeRegistry |
| Claim의 Role과 Role→output 조립 | PackRegistry |
| source 컬럼·상수·Entity key 연결 | Source Profile |
| source event identity/group/order/time/cursor | Source Driver plan |
| cursor 뒤 batch join/enrich와 output schema | 등록 Source Preparer |
| EventFrame→RoleFrame 공통 실행과 자유 훅 경계 | BaseLedgerMapper |
| physical join relation/key/expose/folding/유일성 | verified Virtual Join declaration |
| Atom/cursor 원자적 저장 | 기존 LedgerStore |

다른 계층은 소유자의 ID를 참조할 뿐 key 목록이나 payload 철자를 복사하지 않는다.

v2에는 Position 객체·Role·Registry가 없다. 좌표와 carrier key는 stage-local Entity identity에
포함하고, 이동은 source Entity를 subject로, target Entity를 entity_ref object로 갖는 방향
Claim이다. 동일 물리체 continuity는 이 이동 Claim이 말하며 base evidence로 `same_as`를
추가하지 않는다.

## 2. Config 간소화

- Ledger/온톨로지 작성자가 손대는 정본은 `server/config/ontology/` 한 루트다.
- `manifest.json`이 읽을 파일을 명시하며 glob 자동 발견은 금지한다.
- 물리 테이블 스키마는 `catalog/tables.json`, join은 `catalog/virtual_joins.json`이 소유한다.
- Vocabulary/Entity/Preparer/Mapper/Pack/Profile/Source는 `ledger_config.json`의 각 section이 소유한다.
- chain/enrich는 `dataflows/*.json`이 소유한다.
- 기존 `ledger_config.json`, `ledger_vocabulary.json`은 전환 기간 read-only compatibility
  input이며 v2 authoring surface가 아니다.
- runtime snapshot은 생성물이며 손으로 편집하지 않는다.
- Registry는 config의 immutable compiled view이며 도메인 등록값을 코드 builtin에 두지 않는다.
- config root 밖 경로, symlink escape, glob, 미등재 파일, 중복 ID는 fail-closed다.

## 3. 닫힌 선언만 허용

허용:

- `column`
- `constant`
- `entity`(key binding은 column/constant)
- 등록된 source driver kind
- 등록된 source preparer ID/version
- 등록된 mapper ID/version과 trusted implementation ID
- `$role`과 선택 Role 생략만 가능한 emission field mapping

금지:

- 임의 Python/SQL/JavaScript/eval/exec
- 범용 expression DSL
- config에 module/function/path 입력
- source/table 이름을 기준으로 한 compiler 조건문
- mapper가 live 경로에서 raw Atom/payload 직접 생성
- mapper가 pandas RoleFrame 외의 외부 결과 반환
- 하위 mapper의 `BaseLedgerMapper.map()` 재정의
- `lookup`, `declared_lookup`, `LookupRegistry`
- Profile/Pack compiler의 DB relation read
- Ledger source plan의 join key/expose/folding 재선언

## 4. 승인과 인식론 분리

- `binding_origin`: `user_declared|system_suggested|imported`
- `approval_status`: `pending|approved|rejected`
- `system_suggested`는 `suggestion_reason` 필수
- 모든 중첩 Binding까지 approved여야 executable
- Binding 승인은 mapping 승인일 뿐 Claim을 pin/confirmed로 승격하지 않음

## 5. Source event와 transaction

- event identity는 선언된 source key로 결정하며 pandas index와 행 순서에 의존하지 않는다.
- 한 source event의 모든 Claim은 전부 통과하거나 전부 거절한다.
- dry-run과 execute는 같은 snapshot/compiler를 사용한다.
- Store와 cursor는 기존 transaction 하나가 소유한다.
- compiler, Role mapper, source preparer는 commit/rollback/cursor advance를 호출하지 않는다.

## 6. Scale-first

- source-preparation join N+1 금지, 고유 key batch 조회
- 기본 chunk 1000, 설정 가능한 상한은 검증된 범위만
- relation/key column은 `table_config`와 실제 index 대조
- 큰 OFFSET·무제한 SELECT 금지
- ambiguity 판정을 잃지 않도록 cardinality 확인에 필요한 행 수는 보존
- 1,000만 행 전제의 query plan과 memory bound를 단계 보고에 포함

## 6-bis. Cursor와 virtual join 경계

- 기존 Ledger cursor는 base relation의 물리 column/watermark만 읽는다.
- virtual-only column은 cursor SELECT, identity, order, watermark에 사용할 수 없다.
- cursor가 읽은 DataFrame 뒤에서 source preparer가 batch join/enrich한다.
- join 0/다건은 first-row 선택 없이 source event 전체를 거절한다.
- 완성 EventFrame 이후의 Profile/RoleFrame/Pack compiler는 관계 조회를 모른다.
- source preparer는 verified virtual join rule ID만 참조한다.
- UI의 absent-only/unresolved-label 정책은 Ledger identity 결정에 사용하지 않는다.
- 오른쪽 값은 충돌 없는 namespace로 보존해 잘못 기록된 왼쪽 값이 이기지 못하게 한다.
- right relation 사후 변경은 dependency replay/worklist 대상이며 base cursor에 맡기지 않는다.

## 7. 하위 호환과 삭제

- 6단계 수락 전 legacy 경로 수정·삭제 금지
- parity는 semantic normalization 규칙을 먼저 고정하고 비교
- 7단계 전 DB reset/truncate/drop 금지
- reset은 정확한 schema/table/cursor 대상을 읽기 전용으로 확인한 뒤 별도 사용자 승인을 받음
- 과거 import의 `legacy_atom` 문은 live mapper와 분리

## 8. 단계별 증거

각 단계 보고에는 반드시 다음을 포함한다.

1. 변경 파일과 역할
2. 정규화된 실제 예시
3. 전용 오류 code/path/message
4. 실행한 테스트와 결과
5. baseline 대비 신규 실패 수
6. DB migration/write 여부
7. 미완료·범위 밖
8. 다음 단계 승인 가능 여부 자체 판정
