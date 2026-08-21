# Ledger v2 하드코딩 전수표

> 조사 시점: 2026-08-17 · branch `main` · HEAD `3b640b8`
> 판정 상태: `IN_REVIEW` / `NOT_APPROVED`
> 범위: 읽기 전용 조사. 코드·DB·운영 config 변경 없음.

## 읽는 법

`keep`은 기존 Kernel 계약을 그대로 유지한다는 뜻이다. `move`는 의미를
`server/config/ontology/` 선언과 v2 compiler로 옮긴다는 뜻이며 현재 코드를 곧바로
삭제한다는 뜻이 아니다. `retire`는 shadow parity와 cutover가 끝난 뒤에만 제거한다.

## 전수표

| file | symbol | literal / 계약 | current owner | duplicate owners | runtime caller | tests | v2 destination | 판정 |
|---|---|---|---|---|---|---|---|---|
| `server/ledger/vocabulary.py` | `ENTITY_TYPES` | `Lot/Wafer/Product/Equipment/Recipe/Die`와 identity keys | Python builtin | emitter의 `Lot/lot`, `Wafer/wafer`; Profile TypeRegistry | gate, catalog, trace | admin/catalog/Profile tests | `ledger_config.json.entities` → immutable Registry | move |
| `server/ledger/vocabulary.py` | `PREDICATES` | predicate signature와 required payload | Python builtin | `config.py` 상수, emitters, translators | gate `check_signature` | L1/admin tests | `ledger_config.json.vocabulary`; Pack emission과 교차 검증 | move |
| `server/config/ledger_vocabulary.json` | extension entries | builtin 이후 추가 entity/predicate | legacy config | `vocabulary.py` builtin | vocabulary loader | config tests | ontology root의 `ledger_config.json` | move |
| `server/ledger/config.py` | `SOURCE_KIND_*`, `SOURCE_KINDS` | `lineage/observation/transfer/declared` | source validator | `backfill.run`, dry-run, translators | backfill/dry-run dispatch | source tests | `SourcePlan` + registered reader strategy | move |
| `server/ledger/config.py` | `*_REQUIRED_COLUMNS` | grammar별 logical columns | source validator | translators가 같은 이름을 읽음 | config validate | source tests | Pack/Profile/Mapper input + catalog cross-validation | move |
| `server/ledger/config.py` | derivation/predicate constants | `observation_row`, `job_run_*`, `observed`, `transferred` | legacy grammar | translator와 vocabulary | translators/gate | observed/transfer tests | Pack emission/SourcePlan | move |
| `server/ledger/config.py` | `PLACE_*` | `wafer_grid/dt_slot/dt_job` | legacy Position | container registry, translator/emitter | transfer path | transfer/Profile tests | stage-local Entity identity | retire |
| `server/ledger/source_profile_builtins.py` | lot Pack | `lot-lineage@1/transition`; subject/parent/child/time | Python builtin Pack | `_emit_lot_transition` | canonical-profile mapper | Profile tests | `ledger_config.json.packs` | move |
| `server/ledger/source_profile_builtins.py` | transfer Pack | `transfer@1/movement`; subject/from/to/time/... | Python builtin Pack | `_emit_transfer`, TransferTranslator | canonical-profile mapper | Profile/transfer tests | stage Entity 이동 Pack | move |
| `server/ledger/source_profile_builtins.py` | entity TypeRegistry assembly | Vocabulary builtin 복사 | Profile builtin | Vocabulary Registry | Profile validator | Profile tests | Bundle compiler에서 한 번 생성 | retire |
| `server/ledger/source_profile_builtins.py` | container TypeRegistry | Position type/key shape | Profile builtin | `PLACE_*`, `_position` | Profile validator/emitter | Profile tests | v2에 Position Registry 없음 | retire |
| `server/ledger/source_profile_builtins.py` | legacy templates | `lot_lineage`, `transfer`, containers | template registry | Pack/Profile 역할과 중복 | legacy validator | Profile tests | canonical Profile + Pack; template는 archive | retire |
| `server/ledger/source_profile.py` | binding registry | `column/constant/declared_lookup` | Profile schema | runtime evaluator | canonical-profile mapper | Profile tests | v2는 column/constant; 관계는 Source Preparer | move |
| `server/ledger/source_profile.py` | Pack/Claim/Role descriptors | required role/kind/binding | Profile registry | builtin declarations | validator | registry tests | config compiled immutable descriptors | move |
| `server/ledger/source_profile.py` | legacy Profile/template/container | 구 Profile과 Position container | compatibility | builtin templates | explicit legacy validator | legacy tests | historical import only | retire |
| `server/ledger/profile_chain_mapper.py` | emitter registry | Pack/Claim → Python emitter 두 건 | Python registry | Pack, Vocabulary | canonical-profile mapper | mapper tests | generic Pack compiler | retire |
| `server/ledger/profile_chain_mapper.py` | `_emit_lot_transition` | `Lot/lot`, `derived_from`, entity_ref payload | Python emitter | entity/vocabulary/Pack | canonical-profile mapper | mapper tests | Pack emission template | move |
| `server/ledger/profile_chain_mapper.py` | `_emit_transfer` | `Wafer/wafer`, `source_position`, `{from,to,qty}` | Python emitter | Position, TransferTranslator | canonical-profile mapper | transfer tests | stage EntityRef subject/target emission | retire |
| `server/ledger/profile_chain_mapper.py` | `_position` | exact `{type,keys,position}` | Python helper | transfer translator | canonical-profile mapper | mapper tests | 없음 | retire |
| `server/ledger/profile_chain_mapper.py` | lookup evaluator | DB lookup, 0/다건 거절 | Profile runtime | lookup adapter, transfer lookup | canonical-profile mapper | lookup tests | Source Preparer verified batch join | retire |
| `server/ledger/profile_lookup_adapters.py` | `destination_inventory` | 직접 DB batch lookup | mapper capability | transfer driver lookup | canonical-profile mapper | E2E tests | verified descriptor Source Preparer | retire |
| `server/ledger/chain_mapper.py` | `LedgerMapperContext.lookups` | mapper DB lookup capability | mapper runtime | lookup adapter | registered mapper | mapper tests | EventFrame 외 DB capability 제거 | retire |
| `server/ledger/chain_mapper.py` | default mapper registry | `lot-event@1`, `canonical-profile@1` | trusted code registry | source config mapper IDs | lineage driver | mapper tests | config ID/version + trusted implementation class | move |
| `server/ledger/chain_mapper.py` | `run_registered_mapper` | 최종 LedgerFrame 검증 | frozen Phase 3 | mapper가 Atom/LedgerFrame 생성 | lineage/dry-run | mapper tests | Base mapper→RoleFrame, Pack compiler→LedgerFrame | retire |
| `server/mappers/ledger_lot_event_mapper.py` | grouping | 두 source row pairing | Python mapper | LotEventTranslator | lineage driver | lot mapper tests | Base mapper unit partition/custom hook | move |
| `server/mappers/ledger_lot_event_mapper.py` | map function | Atom 직접 생성 후 LedgerFrame | Python mapper | Lot translator/emitter | lineage driver | lot mapper tests | RoleFrame mapper + lineage Pack | retire |
| `server/ledger/*translator.py` | four translators | source별 Atom/payload 직접 생성 | legacy translators | Pack/emitter/config | four drivers | translator tests | source별 parity 후 compatibility only | retire |
| `server/ledger/backfill.py` | `run` dispatch | 네 kind별 driver | write orchestrator | dry-run 동일 분기 | CLI/admin | backfill tests | cursor transaction keep, reader는 SourcePlan | move |
| `server/ledger/backfill.py` | lineage mapper seam | mapper는 lineage만 가능 | frozen Phase 3 | config validator도 제한 | live `lot_event` | mapper/E2E tests | 모든 source의 EventFrame→Mapper 경계 | move |
| `server/ledger/backfill.py` | transfer container fetch | relation/key/lot/slot SQL | transfer driver | lookup adapter/config | transfer driver | transfer tests | Source Preparer + shared join descriptor | retire |
| `server/ledger/backfill.py` | cursor/group functions | time/keyset/group cursor | Ledger driver | source grammar config | backfill | PG/source tests | 물리 reader/cursor ownership 유지 | keep |
| `server/ledger/dry_run.py` | source-kind branches | execute와 같은 변환/gate | dry-run | backfill 구조 중복 | admin | dry-run tests | 동일 snapshot/preparer/mapper/compiler | move |
| `server/ledger/gate.py` | molecule/gate | source event 원자성/signature | Ledger Kernel | 없음 | 모든 write/dry-run | L1/gate tests | 변경 없이 유지 | keep |
| `server/ledger/ledger_frame.py` | columns/validator | 구조화된 write boundary | Ledger Kernel | Atom schema | mapper/import/store | mapper tests | Pack compiler 유일 출력 | keep |
| `server/ledger/store.py` | `write_batch` | Atom insert + cursor 한 commit | Ledger Kernel | 없음 | backfill `_flush` | PostgreSQL L1 | 변경 없이 유지 | keep |
| `server/ledger/schema.py` | envelope/indexes | subject/predicate/object/time/provenance | Ledger Kernel | 없음 | store/read APIs | schema/trace | 변경 없이 유지 | keep |
| `server/config/ledger_config.json` | live `lot_event` | lineage + `lot-event@1` | live config | sample에는 더 많은 source | loader/backfill | source tests | 전환 input → ontology root | move |
| `server/config/table_config.json` | physical tables | columns/business/composite keys | physical config | ledger sample config | DB/cursor | config tests | `catalog/tables.json` | move |
| `server/virtual_join_config.py` | verified rules | right UNIQUE 증거 | join verifier | sample rules | UI read | join tests | immutable descriptor 생성부 | keep |
| `server/virtual_join_executor.py` | `execute_rule`, `attach` | UI payload absent-only merge | UI executor | 미래 preparer와 join 의미 일부 중복 | table reads | join tests | UI 전용 유지; Ledger는 descriptor만 공유 | keep |

## 계약 대조 결과

| 대조 | 실측 | 판정 |
|---|---|---|
| lot Pack ↔ emitter | required `subject,parent,child,occurred_at`은 일치하나 emitter가 `Lot/lot/derived_from/entity_ref`를 별도 하드코딩 | 의미 정본 중복 |
| transfer Pack ↔ emitter | required Role은 읽지만 `event_key/row_order`는 emitter 결과에 쓰이지 않음 | source event metadata와 Claim Role 분리 |
| Pack ↔ Vocabulary | emitter가 payload를 만들고 Vocabulary가 같은 shape를 재검사 | Pack emission 단독 정본화 |
| Position Registry ↔ translator | Registry key와 translator/emitter payload key 철자가 계층마다 다름 | Position 제거 근거 |
| Profile ↔ table config | live Profile 경로는 lot_event만 연결; sample dt_log와 현재 physical schema의 이름 세대가 다름 | catalog 교차 검증 필요 |
| cursor ↔ virtual-only | cursor는 base columns만 SELECT하고 UI `attach()` 결과를 읽지 못함 | Source Preparer 필수 |
| preparer ↔ virtual join | Ledger preparer는 없고 transfer driver/lookup adapter가 SQL을 별도 소유 | shared descriptor 필요 |
| right correction ↔ replay | 성공 후 right row가 바뀐 event의 dependency replay/worklist 없음 | DT cutover blocker |
| event identity ↔ physical key | lot row=`txn_seq`, boundary=`event_time`; dt composite key는 있으나 live SourcePlan 없음 | identity/order/index 검증 필요 |
| mapper derivation ↔ gate | mapper derivation을 gate가 source declaration과 재검사 | gate keep, 선언은 Pack/SourcePlan 이동 |

## 빠진 구현

- pandas `SourcePreparer`와 shared immutable `VerifiedJoinDescriptor` adapter
- right-row dependency provenance/replay worklist
- `BaseLedgerMapper`/RoleFrame/Pack compiler
- config-only Registry와 deterministic `LedgerSetupSnapshot`

이 항목은 1단계에서 구현하지 않는다.
