# Ledger v2 목표 구조와 정본 목록

> 상태: `TARGET_CONTRACT` · 구현 전 단계별 승인 필요
> 결정일: 2026-08-17
> 금지: 이 문서를 현행 구현 완료로 읽지 말 것

## 1. 목표 한 문장

물리 원천을 기존 cursor가 안전하게 읽고, 승인된 virtual join 선언을 상속한 pandas source
preparer가 완전한 EventFrame을 만들며, Pack compiler만 그 의미를 LedgerFrame으로 번역한다.

## 2. 전체 실행 구조

```text
server/config/ontology/catalog/tables.json
  └─ base/right relation, physical columns, key/type/index truth

server/config/ontology/catalog/virtual_joins.json
  └─ join relation/key/expose/folding/cardinality declaration
       └─ verifier: right key UNIQUE proof
            └─ immutable VerifiedJoinDescriptor
                 ├─ UI virtual-join executor
                 └─ Ledger Source Preparer

server/config/ontology/ledger_config.json
  ├─ vocabulary / entities / source_preparers / mappers
  ├─ packs / profiles / sources
  └─ immutable Registry inputs

existing Ledger cursor
  └─ base relation physical columns + watermark만 SELECT
       └─ pandas source batch
            └─ registered Source Preparer
                 ├─ verified join rule ID 상속
                 ├─ unique keys batch query
                 ├─ pandas merge
                 ├─ frame/coordinate 계산
                 └─ complete EventFrame + preparation provenance
                      └─ BaseLedgerMapper
                           ├─ default DeclarativeRoleMapper
                           ├─ registered Python interpret hook
                           └─ pandas RoleFrame
                                └─ Pack compiler
                                     └─ pandas LedgerFrame
                                          └─ existing gate
                                               └─ existing LedgerStore + cursor transaction
```

## 3. DT 기준 예시

### Cursor 입력

`dt_log`의 물리 행을 `dt_job_id` source event로 묶는다. cursor identity/order/watermark는
`dt_log`의 물리 column만 사용한다.

### 상속 Join

```text
rule ID: dt_log_to_dt_inventory
left:     dt_log
right:    dt_inventory
key:      dt_job_id = dt_job_id
expose:   dt_lot, dt_slot, dt_frame, core_frame, frame 변환 계수
guard:    dt_inventory.dt_job_id UNIQUE
```

위 relation/key/expose/folding은 virtual join rule만 소유한다. Ledger source plan은 rule ID만
참조한다. 현재 운영 `virtual_join_rules.json`은 없고 sample의 기존 선언도 retired 상태이므로,
실제 v2 착수 시 이 rule을 새 config/DB 기준으로 선언·검증해야 한다.

### EventFrame 출력

```text
core_wafer_id, c_wx, c_wy
inventory_dt_lot, inventory_dt_slot
resolved_dt_x, resolved_dt_y
event_time, dt_job_id
preparation provenance
```

오른쪽 값은 `inventory_*`처럼 충돌 없는 이름으로 보존한다. `dt_log`에 기록된 lot/slot이
틀렸더라도 UI virtual join의 absent-only 규칙으로 그 값이 이기게 하지 않는다.

### 의미 출력

```text
CoreDie{core_wafer, core_x, core_y}
  --transferred_to(job, time, provenance)-->
DTDie{dt_lot, dt_slot, dt_x, dt_y}
```

`dt_lot/dt_slot`만 있으면 wafer 신원이다. die 신원은 표준화된 `dt_x/dt_y`까지 있어야 한다.

## 4. Position과 Lookup의 최종 판정

v2에는 다음이 없다.

- Position 객체/Role/Registry
- `{type, keys, position}` payload
- `lookups` Bundle section
- `declared_lookup` binding
- `LookupRegistry`
- destination별 lookup adapter
- Profile/Pack compiler의 DB read

물리 관계 결합 자체는 사라지지 않는다. 그것은 ontology lookup이 아니라 cursor 이후 source
data preparation이며, verified virtual join 선언을 상속한다.

## 5. Virtual join에서 상속하는 것과 제외하는 것

| 상속 | 제외 |
|---|---|
| left/right relation | `virtual_join_executor.attach()` 호출 모양 |
| join key | UI payload 조립 |
| expose columns | `unresolved_label` 표시 |
| notation folding | absent-only 충돌 병합 |
| `join_cardinality=one` | 셀 표시용 `virtual_join` source |
| right UNIQUE 승인 결과 | UI cache/serialization |

UI executor와 Ledger preparer는 같은 `VerifiedJoinDescriptor`를 소비해야 한다. 둘이 join key를
각자 조립하면 수락 실패다. 이 descriptor는 catalog 선언만으로 만들 수 없고, 기존
`virtual_join_config.load_verified_rules()`가 물리 UNIQUE index를 확인한 뒤에만 생성한다.
공용 descriptor type은 raw mapping용 public constructor/factory를 제공하지 않으며, private
issuance capability는 이 verifier 모듈만 소유한다. issuer는 `load_verified_rules()` 호출 위치
밖에서 사용해도 거절한다. compiler도 verifier가 발급 등록한 object identity만 받으며 단순
class instance는 받지 않는다. 임의 index 이름은 물리 proof가 아니다.

## 6. 실패 계약

| 상황 | 판정 | Atom | Cursor |
|---|---|---:|---|
| inherited rule 없음/disabled/rejected | 실행 전 거절 | 0 | 미이동 |
| right row 0건 | `source_preparation_missing` | 0 | 해당 event를 넘지 않음 |
| right row 2건 이상 | `source_preparation_ambiguous` | 0 | 해당 event를 넘지 않음 |
| lot/slot/frame/좌표 결측 | `source_preparation_incomplete` | 0 | 해당 event를 넘지 않음 |
| Binding pending/rejected | readiness 거절 | 0 | 미이동 |
| Pack/gate/store 실패 | 기존 원자적 거절/rollback | 0 | 미이동 |

첫 행 선택, 기본 Position, lot/slot 추측, 빈 값을 `미상` 문자열로 신원에 넣는 행위는 금지한다.

## 7. Right relation 변경 계약

`dt_inventory`는 `dt_log` cursor 밖에 있으므로 다음을 별도 보장해야 한다.

1. missing 상태에서는 cursor가 막혀 right row 도착 후 같은 event를 재시도한다.
2. 성공한 EventFrame provenance에 rule ID, right row identity, value fingerprint,
   right updated_at, preparer version을 남긴다.
3. 이미 성공한 뒤 right row가 수정되면 affected left event의 dependency replay/worklist를 만든다.
4. replay/supersede는 기존 Ledger 경계를 사용하고 Pack compiler에 넣지 않는다.
5. 이 경로가 없거나 미검증이면 DT source 운영 cutover는 `NO-GO`다.

## 8. 설정 정본

아래는 요약이다. 각 파일의 상세 역할·소비자·금지 내용·legacy 이동표는
[`CONFIG_CANON.md`](./CONFIG_CANON.md)가 단독 정본이다.

| 정본 | 소유하는 것 | 소유하지 않는 것 |
|---|---|---|
| `server/config/ontology/catalog/tables.json` | 물리 relation/column/type/business key | Claim 의미, join 실행 |
| `server/config/ontology/catalog/virtual_joins.json` | join relation/key/expose/folding/cardinality | Pack/Role, UI 또는 Ledger 실행 방식 |
| `server/config/ontology/ledger_config.json` | Vocabulary/Entity/Preparer/Mapper/Pack/Profile/Source section | 물리 join key, Python path, raw SQL |
| `server/config/ontology/dataflows/chains.json` | source 파생 실행 연결 | Pack 의미 |
| `server/config/ontology/dataflows/enrichments.json` | 결측 보강·워크리스트 선언 | Claim 확정 등급 |
| immutable `LedgerSetupSnapshot` | 위 config의 검증 완료 실행 계약과 hash | 사람 편집 |

Registry는 source-of-truth가 아니다. 위 config를 검증·컴파일한 immutable 읽기 모델이다.
`VocabularyRegistry`, `EntityTypeRegistry`, `PackRegistry`, `SourcePlanRegistry`,
`SourcePreparerRegistry`, `MapperRegistry`의 도메인 등록 항목을 Python dict/builtin으로
하드코딩하지 않는다. Mapper의 실행 가능한 구현 클래스만 trusted code registry가 소유하며
config에는 module/function/path를 넣지 않는다.

### 목표 디렉터리

```text
server/config/ontology/
├─ manifest.json
├─ ledger_config.json
├─ catalog/
│  ├─ tables.json
│  └─ virtual_joins.json
└─ dataflows/
   ├─ chains.json
   └─ enrichments.json
```

`manifest.json`은 읽을 파일을 정확히 열거한다. glob·디렉터리 열거 순서·파일명 추측은
금지하고, root 밖 경로·중복 ID·미등재 파일·순환 include를 거절한다. 각 파일은 자기
`schema_version`을 가진다. 모든 파일을 합친 canonical serialization과 hash가
`LedgerSetupSnapshot`이다.

기존 `server/config/table_config.json`, `virtual_join_rules.json`, `ledger_config.json`,
`ledger_vocabulary.json`, `chain_rules.json`, `enrichment_rules.json`은 전환 기간 compatibility
input이다. 목표 정본과 동시에 편집하지 않는다. 단계 7에서 호출부 전수 검사와 함께 새 경로로
전환하고, 구 파일은 `_archive`로 이동한다.

## 9. 문서 정본

| 우선순위 | 문서 | 역할 |
|---:|---|---|
| 1 | `docs/overview/SYSTEM_OVERVIEW.md` | 전체 시스템 SSOT와 현행/목표 상태 |
| 2 | 이 문서 | Ledger v2 목표 실행 구조·경계·정본 |
| 3 | `CONFIG_CANON.md` | config directory·파일별 역할·소유권 |
| 4 | `README.md` | 재설계 상태·단계 지도 |
| 5 | `COMMON_RULES.md` | 모든 단계 불변식 |
| 6 | `00_MASTER_PLAN.md` | 단계 순서·최종 수락 기준 |
| 7 | `02_LEDGER_SETUP_BUNDLE.md` | 목표 authoring schema |
| 8 | `03_REGISTRIES_AND_CROSS_VALIDATION.md` | snapshot/교차 검증 |
| 9 | `04_ROLEFRAME_AND_PACK_COMPILER.md` | EventFrame→RoleFrame→LedgerFrame 계약 |
| 10 | `MAPPER_DESIGN_PATTERN.md` | Mapper 공통 기본 구현·자유 훅·RoleFrame 반환 규격 |
| 11 | `05_SOURCE_DRIVER_AND_JOIN_BOUNDARY.md` | cursor·join·preparer·late update 계약 |
| 12 | `06_SHADOW_PARITY_AND_POSTGRES_E2E.md` | 구현 수락 증거 |
| 13 | `docs/spec/LEDGER_TECHNICAL_SPEC.md` | 현행 Ledger Kernel/구현 계약 |
| 14 | `docs/architecture/LEDGER_FRAME_CHAIN_MAPPER.md` | 동결된 현행 3단계 구현 경계 |

충돌하면 현행 사실은 `SYSTEM_OVERVIEW`와 코드가 우선이고, v2 목표 결정은 이 문서와
`OPEN_DECISIONS`의 `DECIDED` 항목이 우선한다.

## 10. Cutover 금지 조건

- cursor가 virtual-only column을 직접 SELECT함
- Ledger config가 join key/expose/folding을 복사함
- Registry 항목이 `ledger_config.json`이 아니라 Python builtin/dict에만 존재함
- manifest에 없는 파일을 자동 발견해 로드함
- 새 정본과 legacy config를 동시에 편집함
- UI executor와 preparer가 다른 join descriptor를 사용함
- source preparer가 N+1 query를 실행함
- left recorded value가 confirmed right identity를 조용히 이김
- right late arrival/correction replay가 없음
- Profile/compiler가 DB를 읽음
- mapper가 raw Atom/payload를 만듦
- mapper가 pandas RoleFrame 외의 외부 결과를 반환함
- 하위 mapper가 `BaseLedgerMapper.map()` 공통 파이프라인을 재정의함
- 실패 event를 건너뛰고 cursor가 전진함

하나라도 남으면 목표 미달이며 다음 단계 승인이나 운영 전환을 요청하지 않는다.
