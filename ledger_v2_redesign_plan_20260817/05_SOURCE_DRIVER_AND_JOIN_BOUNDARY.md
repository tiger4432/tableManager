# 5단계 — 기존 Source Driver·Cursor와 pandas Join 경계

## 목표

새 worker/runtime 없이 기존 Ledger source reader와 cursor가 base relation을 읽고, 그 결과를
등록 source preparer가 batch join/enrich한 뒤 완성 EventFrame으로 반환하게 한다. Profile,
Registry, generic binder, Pack compiler는 DB 관계 조회를 전혀 알지 못한다.

Position 객체와 Position validator는 만들지 않는다. 이동의 양 끝은 모두
EntityTypeRegistry가 검증한 stage-local EntityRef다.

## 현재 제약

현재 Ledger backfill cursor는 base relation을 직접 `SELECT`한다. 기존 virtual join은 웹 조회가
물리 행을 읽은 뒤 응답 payload에 붙이는 계산값이며, 저장 column이 아니다. 따라서 Ledger
cursor가 virtual-only column을 직접 `SELECT`할 수 있다는 전제를 두지 않는다.

## Driver 계약

SourceDriverPlan이 다음을 소유한다.

```text
base relation
unit: row | group
identity columns
group_by columns
order_by columns
occurred_at column + timezone
cursor/watermark columns
source_preparer ID/version/output schema
inherited verified virtual-join rule IDs
Profile ID/content hash
```

cursor identity/order/watermark는 모두 base relation의 물리 column이어야 한다. source
preparer가 나중에 붙이는 column을 cursor key로 사용할 수 없다.

## Source preparation

실행 순서는 고정한다.

```text
base table cursor read
→ pandas source batch
→ registered source preparer
   ├─ direct column normalization
   ├─ 상속한 VerifiedJoinDescriptor로 필요한 relation을 고유 key로 batch read
   ├─ pandas merge/join
   ├─ frame/coordinate 계산
   └─ preparation provenance 기록
→ complete pandas EventFrame
```

source preparer는 파일 인제션 parser처럼 DataFrame을 받아 DataFrame을 반환한다. 임의 Atom,
predicate, object payload를 만들지 않는다. config에서 Python module/function/path나 raw SQL을
받지 않고, 등록 ID로만 선택한다.

virtual join 선언은 반드시 상속한다. Ledger source plan은 rule ID만 참조하고 relation,
join key, expose, notation folding, cardinality를 다시 적지 않는다. 기존 verifier가 만든
immutable `VerifiedJoinDescriptor`를 UI executor와 source preparer가 함께 소비한다.

기존 `virtual_join_executor.attach()`를 cursor 앞에 끼우지는 않는다. 그것은 grid payload,
absent-only, `unresolved_label`, 셀 표시 provenance를 소유한다. Ledger source preparer는 같은
descriptor로 cursor 배치의 key만 query하고 pandas merge하며, 오른쪽 값을 충돌 없는 namespace로
보존한다.

## Join 결과와 거절

- 1건: EventFrame에 target column과 join provenance를 추가
- 0건: `source_preparation_missing`; compiler 미호출
- 2건 이상: `source_preparation_ambiguous`; compiler 미호출
- frame/identity key 일부 결측: `source_preparation_incomplete`; compiler 미호출

결손과 모호성은 필요하면 `target_mapping_missing`, `target_mapping_ambiguous` Enrich Action
후보가 된다. 값을 추측하거나 첫 행을 선택하지 않는다. 한 source event 준비가 실패하면 Atom
0이고 cursor는 그 event를 넘지 않는다.

## 늦은 도착과 사후 수정

base cursor는 오른쪽 relation의 변경을 감지하지 못한다. 이를 무시하면 `dt_inventory`가
나중에 들어오거나 고쳐졌을 때 이미 지난 `dt_log` event가 영원히 낡는다.

- join 0건/불완전으로 거절된 event는 cursor가 넘지 않으므로 right row 도착 뒤 같은 event를 재시도
- 성공한 event의 provenance에 join rule ID, right row identity, right value fingerprint,
  right updated_at, preparer version을 기록
- right relation 수정은 해당 left event를 찾는 dependency replay/worklist를 생성
- 재평가는 기존 replay/supersede 경계를 사용하고 generic Pack compiler에 삭제 감지나
  supersession을 넣지 않음
- dependency replay가 착지·검증되기 전에는 해당 source의 운영 cutover 금지

## Stage-local Entity

```text
CoreDie{core_wafer, core_x, core_y}
  --transferred_to(job,time,provenance)-->
DTDie{dt_lot, dt_slot, dt_x, dt_y}
  --transferred_to(job,time,provenance)-->
BondComponent{bond_wafer, bond_x, bond_y, layer}
```

DT 예시는 `dt_job_id`로 `dt_inventory`를 batch join해 `dt_lot/dt_slot`과 frame metadata를
얻고, `dt_log`의 stage 좌표를 표준 `dt_x/dt_y`로 변환한 뒤 `DTDie` identity를 완성한다.
`dt_lot/dt_slot`만 있으면 DT wafer identity이지 개별 die identity가 아니다.

좌표가 없는 bulk 수준에서는 `CoreWafer`, `DTJob`, `DTSlot` 같은 collection Entity를
사용한다. `transferred_to`가 continuity와 방향을 말하므로 base evidence에 `same_as`를
추가하지 않는다. 여러 Core가 하나의 Final Chip을 이루는 경우는 `component_of`다.

## 실행 경로

```text
existing reader/cursor → base DataFrame
→ registered source preparer → complete EventFrame
→ generic binder or registered Python Role mapper
→ Pack compiler → LedgerFrame validator
→ existing gate → existing LedgerStore.write_batch(atoms, next_cursor)
```

일반 실행 경로에서 raw `legacy_atom`, raw LedgerFrame mapper, `declared_lookup`은 거절한다.
과거 import는 별도 명시 API에만 남는다.

## Scale 계약

- join relation은 table config와 실제 UNIQUE/index 근거를 가져야 함
- 페이지의 고유 key를 모아 기본 1000개 단위 batch read
- 행별 query/N+1 금지
- 큰 OFFSET·무제한 SELECT 금지
- source preparer는 commit/rollback/cursor advance 금지
- join input/output 행 수와 0/다건을 계측

## 수락 테스트

- cursor SELECT가 base physical column만 참조
- virtual-only column을 cursor key로 선언하면 거절
- source preparer의 DataFrame → DataFrame 계약
- 1001개 unique key에서 두 batch, N+1 없음
- DT job → inventory 1건 → 완전한 `DTDie` identity
- join 0/다건/frame 결측에서 Atom 0·cursor 미이동
- preparation provenance에 relation/key/right row/version 보존
- virtual join rule ID만으로 join하며 relation/key/expose literal 중복 0
- UI executor와 preparer가 동일 VerifiedJoinDescriptor 사용
- 잘못 기록된 `dt_log.dt_lot`이 inventory 확정값을 덮지 못함
- missing inventory 뒤 도착 시 blocked event 재시도
- 성공 후 inventory 수정 시 dependency replay/worklist 산출
- stage-local Entity exact identity key 검증
- CoreDie → DTDie → BondComponent 방향 Claim
- multi-Core → FinalChip `component_of`, `same_as` 미사용
- pending/rejected nested Binding에서 preparer 호출 전 차단
- generic과 Python Role mapper가 같은 Pack compiler 사용
- 기존 store/cursor transaction 경계 불변

완료 후 멈추고 5단계 승인을 기다린다.
