# 0. Master Plan

## 0.1 목표

사용자가 새 소스를 연결할 때 흩어진 코드·config를 찾아다니지 않게 한다. 모든 온톨로지
설정은 `server/config/ontology/` 한 루트에 둔다. Pack/Profile/Registry는
`ledger_config.json` 한 파일 아래 section으로 함께 보고, catalog/dataflow만 분리한다.
`manifest.json`에서 시작해 logical `LedgerSetupBundle` 하나로 검증·컴파일한다.

성공 상태:

1. Pack을 추가해도 compiler core를 수정하지 않는다.
2. 같은 Pack을 다른 source/column에 재사용한다.
3. 좌표는 stage-local Entity의 identity key이며 별도 Position 구조를 만들지 않는다.
4. 이동은 source Entity → target Entity 방향 Claim으로 표현한다.
5. Claim payload는 Pack emission만 만든다.
6. 기본 `BaseLedgerMapper`가 공통 검증·unit partition·RoleFrame 조립을 맡고, 개별 Python
   mapper는 제한된 해석 훅만 구현한다. Mapper의 외부 출력은 pandas RoleFrame뿐이다.
7. dry-run과 execute가 동일 snapshot/compiler를 사용한다.
8. 기존 Ledger gate/store/cursor/read API는 바뀌지 않는다.
9. 실패한 source event는 Atom 0, cursor 미이동이다.
10. Ledger compiler는 DB를 읽지 않고 완성된 EventFrame만 해석한다.
11. source preparer는 승인된 virtual join 선언을 ID로 상속하고 join 계약을 복사하지 않는다.
12. 모든 Registry 등록 데이터는 config이며 Python builtin은 validator/implementation만 가진다.

## 0.2 문제 정의

현행은 다음 의미가 여러 곳에 중복돼 있다.

```text
Pack Role                subject/target/occurred_at
Profile emitter          object_payload 조립
Vocabulary               이동 object entity_ref 계약
Entity TypeRegistry      stage별 identity key
legacy translator        from/to Position payload
source preparation       cursor 뒤의 batch join/enrich와 결손 판정
source driver            row_identity와 grouping
```

이 구조에서는 새 source를 추가할 때 config와 Python 파일을 함께 읽어야 하고, 서로 다른
정본이 조용히 어긋날 수 있다. v2는 Position 계약을 정비하는 대신 삭제하고 좌표를
`CoreDie`, `DTDie`, `BondComponent` 같은 stage-local Entity의 identity key로 올린다.

## 0.3 보존 경계

| 계층 | 판정 | 이유 |
|---|---|---|
| `ledger_events` envelope/schema | 유지 | 범용 Claim 저장과 provenance는 이미 분리됨 |
| gate molecule atomicity | 유지 | 한 source event 전체 승인/거절 계약 |
| `LedgerStore.write_batch` | 유지 | Atom과 cursor의 단일 transaction |
| resolver·trace·coverage·structure | 유지 | 쓰기 경로와 독립된 소비 계약 |
| 현재 Profile schema 개념 | 재사용 후 단순화 | approval/binding 결정성은 유효, authoring surface는 분산 |
| Pack builtins·emitter registry | 재작성 | Role/output 계약 중복·도메인 하드코딩 |
| Position constants/registry/payload | v2에서 제거 | stage-local Entity와 방향 Claim으로 대체 |
| source별 translator/config kind | 단계적 대체 | grouping은 살리되 의미 조립은 Pack으로 이동 |
| destination 전용 lookup 코드 | v2에서 제거 | cursor 뒤 pandas source preparer의 batch join으로 이동 |

## 0.4 목표 구성

```text
server/config/ontology/manifest.json
        │ exact config file map
        ▼
ledger_config + catalog + dataflows configs
        │ deterministic logical LedgerSetupBundle
        ▼
server/config/ontology/catalog/tables.json
        │ physical relation/column/index truth
        ▼
existing Ledger source driver + existing cursor
        │ base relation/watermark read
        ▼ pandas source batch
registered source preparer
        │ verified virtual-join rule 상속
        │ batch join/enrich, no cursor/commit
        ▼ complete pandas EventFrame
LedgerSetupCompiler
        ├─ VocabularyRegistry
        ├─ EntityTypeRegistry
        ├─ PackRegistry
        ├─ MapperRegistry
        └─ Source/Profile plans
        ▼ immutable LedgerSetupSnapshot
BaseLedgerMapper
  ├─ default DeclarativeRoleMapper
  └─ registered Python interpret hook
        ▼ pandas RoleFrame
Pack compiler / generic emitter
        ▼ pandas LedgerFrame
existing gate → existing LedgerStore → existing cursor transaction
```

## 0.5 단계 순서

| 단계 | 목적 | 쓰기 허용 |
|---|---|---|
| 1 | 현행 동결·하드코딩/의존/성능 baseline | 문서·테스트만 |
| 2 | 단일 Bundle schema와 공개 계약 확정 | schema/validator 테스트만 |
| 3 | Registry와 교차 검증, immutable snapshot | DB write 없음 |
| 4 | Base Mapper·RoleFrame·Pack compiler | dry-run 후보만 |
| 5 | 기존 driver/cursor 및 pandas source preparation 연결 | 격리 DB 테스트만 |
| 6 | shadow parity와 PostgreSQL E2E | 격리 DB만 |
| 7 | 운영 config 전환과 선택적 reset | 별도 파괴 승인 후만 |

## 0.6 최종 수락 기준

- Pack/Profile/Registry 작성은 `server/config/ontology/ledger_config.json` 한 파일에서 한다.
- `manifest.json`에 명시된 파일만 로드한다.
- `catalog/tables.json`의 존재하는 relation/column만 참조할 수 있다.
- Registry 등록 항목의 config-only 검사가 통과한다.
- Entity/Pack/Profile 전체가 한 번에 교차 검증된다.
- core validator/compiler에 `dt_log`, `bonding_log`, `Core`, `Bonding`, `DT_LOT` 분기가 없다.
- 직접 `object_payload={"from":...,"to":...}`를 만드는 live mapper가 없다.
- stage-local Entity의 identity key 불일치가 config load에서 정확한 path로 거절된다.
- cursor는 base relation의 물리 컬럼만 읽고, source preparer는 페이지 단위 batch join만 한다.
- source preparer의 relation/join key/expose/folding은 승인된 virtual join rule의 단일 계약이다.
- Profile/Registry/Pack compiler에는 lookup 선언과 DB read가 없다.
- 동일 입력의 dry-run/execute LedgerFrame이 같다.
- pending/rejected, source-preparation 결손/다건, invalid EntityRef, Pack/Vocabulary 불일치가
  Atom 0·cursor 미이동이다.
- 기존 read API 회귀가 없다.

## 0.7 중지 조건

아래가 발생하면 다음 단계로 넘어가지 않는다.

- 한 의미를 두 Registry가 동시에 소유해야만 구현 가능함
- source별 `if`가 generic compiler에 필요함
- Profile 승인 상태가 Claim epistemic class를 바꿈
- Ledger compiler가 관계 조회나 virtual join 실행을 알아야 함
- source preparer가 virtual join key/expose/folding을 별도로 재선언해야만 구현 가능함
- Registry entry를 추가하려면 Python builtin 목록도 함께 수정해야 함
- manifest 밖 파일을 glob으로 자동 로드해야만 구현 가능함
- cursor/store transaction을 새 실행기가 별도로 소유해야 함
- baseline 대비 설명되지 않은 신규 실패가 있음
