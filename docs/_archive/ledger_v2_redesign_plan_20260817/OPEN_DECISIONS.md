# 구현 전 사용자 판정이 필요한 항목

이 항목은 1단계 조사 결과와 함께 확정한다. 확정 전에는 코드에 철자를 박지 않는다.

## D1. Position 모델 제거 — `DECIDED`

2026-08-17 사용자 판정으로 v2에서 `{type, keys, position}` 모델과
`PositionTypeRegistry`를 만들지 않는다. 기존 충돌은 migration inventory로만 기록한다.

```text
Registry:   dt_slot → lot, slot      / dt_job → job
Translator: dt_slot → dt_lot, dt_slot / dt_job → dt_job
```

대체 모델:

```text
CoreDie{core_wafer, core_x, core_y}
  --transferred_to--> DTDie{dt_lot, dt_slot, dt_x, dt_y}
  --transferred_to--> BondComponent{bond_wafer, bond_x, bond_y, layer}
```

### 1단계 실측 근거

`config.py`의 `PLACE_*`, builtin container Registry, transfer Role `from/to: position`,
`profile_chain_mapper.py`의 `source_position/_position/{from,to}`, `transfer_translator.py`가
같은 의미를 각자 조립한다. key 철자도 계층별로 달라 Position 제거 판정을 유지한다.

## D2. 이동과 동일성 — `DECIDED`

기본 증거는 방향·시간·Job·provenance를 가진 `transferred_to` Claim이다.
`same_as`는 base transfer evidence로 사용하지 않는다.

- DT 전후 stage-local Entity는 별도 참조지만 이동 Claim이 물리 continuity를 말한다.
- 여러 Core가 Final Chip을 이루면 `component_of`이며 `same_as`가 아니다.
- 좌표가 없는 bulk 이동은 container/collection Entity 수준 Claim으로 남긴다.
- Frame Pack은 실제 use case가 생길 때까지 v2 초기 범위에서 제외한다.

### 1단계 실측 근거

현행 transfer emitter는 주어 `Wafer`와 Position `{from,to}`를 value payload로 저장해 도착
개체 identity를 원장 목적어로 노출하지 못한다. v2는 stage Entity 사이 방향 Claim으로
바꾸고 물리 continuity와 동일성을 `same_as`로 접지 않는다.

## D3. Python mapper 출력 계약 — `DECIDED`

2026-08-17 사용자 판정으로 Mapper의 외부 출력은 pandas RoleFrame이다. Source Preparer는
완성 EventFrame을 반환하고 `BaseLedgerMapper.map()`이 공통 검증·unit partition·RoleFrame
조립을 소유한다. 개별 Mapper는 제한된 `interpret_unit()`만 구현한다. Pack compiler만
LedgerFrame을 생성하며 raw LedgerFrame은 과거 import 전용으로 제한한다. 상세 정본은
[`MAPPER_DESIGN_PATTERN.md`](./MAPPER_DESIGN_PATTERN.md)다.

### 1단계 실측 근거

현행 lot/profile mapper는 Atom을 직접 만든 뒤 LedgerFrame을 반환한다. 그 결과 entity key,
predicate, payload가 mapper/Pack/Vocabulary에 중복된다. pairing/grouping 해석만 mapper에
남기고 외부 출력은 RoleFrame으로 제한한다.

## D4. 단일 authoring root — `DECIDED`

2026-08-17 사용자 판정으로 `server/config/ontology/` 한 루트를 사용한다. Pack/Profile과
Pack/Profile/Vocabulary/Entity/SourcePreparer/Mapper/Source Registry section은
`ledger_config.json` 한 파일 아래에 함께 둔다. catalog와 dataflow만 하위 폴더로 분리한다.

### 1단계 실측 근거

의미가 legacy ledger/vocabulary/table config, Python builtin Pack/Registry, sample virtual
join에 흩어져 있다. live Ledger config는 `lot_event` 하나뿐이고 sample/test의 source 집합도
다르므로 manifest가 파일 집합을 열거하고 한 Bundle로 교차 검증해야 한다.

## D5. Reset 범위와 시점 — `PENDING_DESTRUCTIVE_APPROVAL`

권고:

- 6단계 shadow parity 수락 전 reset 없음
- 수락 후 `ledger_events`와 ledger cursor만 명시적 초기화 후보
- source table, audit, enrichment, map data는 reset 대상 아님
- 실제 명령과 대상 건수를 보여준 뒤 별도 승인

### 1단계 실측 근거

`LedgerStore.write_batch`와 read API는 유지 가치가 있고 전체 clean baseline도 없다. 지금
reset하면 parity 증거만 사라진다. stage 6 승인 전에는 reset 명령을 만들거나 실행하지 않는다.

## D6. Ledger lookup 제거 — `DECIDED`

2026-08-17 사용자 판정으로 v2 Bundle/Profile/Registry/compiler에서 lookup을 제거한다.

- `lookups` section 없음
- `declared_lookup` binding 없음
- `LookupRegistry` 없음
- destination별 adapter 없음
- Profile/compiler의 DB read 없음

현재 virtual join은 웹 조회 응답에 붙는 값이라 Ledger cursor가 직접 읽을 수 없다. cursor는
base relation을 먼저 읽고, 등록 source preparer가 그 DataFrame에 batch join/enrich를 수행해
완성 EventFrame을 반환한다. 0건·다건·frame 결측은 추측하지 않고 source-preparation 오류와
Enrich Action 후보로 남긴다.

## D7. Virtual join 선언 상속 — `DECIDED`

2026-08-17 사용자 판정으로 source preparer는 승인된 virtual join rule을 ID로 상속한다.

- join relation/key/expose/folding/cardinality/UNIQUE 근거를 Ledger config에 복사하지 않음
- UI executor와 preparer가 같은 immutable VerifiedJoinDescriptor 소비
- `virtual_join_executor.attach()` 자체는 재사용하지 않음
- UI absent-only, unresolved label, 셀 표시 provenance는 상속하지 않음
- 오른쪽 값은 충돌 없는 EventFrame column으로 보존
- missing/ambiguous는 event 거절, 사후 right 변경은 dependency replay/worklist

## D8. Registry-as-Config — `DECIDED`

- `VocabularyRegistry` ← `ledger_config.json.vocabulary`
- `EntityTypeRegistry` ← `ledger_config.json.entities`
- `SourcePreparerRegistry` ← `ledger_config.json.source_preparers`
- `MapperRegistry` ← `ledger_config.json.mappers`
- `PackRegistry` ← `ledger_config.json.packs`
- `ProfileRegistry` ← `ledger_config.json.profiles`
- `SourcePlanRegistry` ← `ledger_config.json.sources`

Registry는 위 config의 immutable compiled view다. 도메인 등록값을 Python builtin과 합치지
않고, 새 entry에 compiler core 수정이 필요하면 수락 실패다.
