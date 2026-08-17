# 4단계 — pandas RoleFrame과 범용 Pack Compiler

> 구현 상태: `COMPLETE` · 승인: `APPROVED` · 2026-08-17
> 구현 근거: [`STAGE_4_ACCEPTANCE_EVIDENCE.md`](./STAGE_4_ACCEPTANCE_EVIDENCE.md)

## 목표

live mapper가 raw Atom/payload를 직접 만들지 못하게 한다. generic binding evaluator와
복잡한 Python mapper는 모두 pandas `RoleFrame`을 반환하고, Pack compiler 하나만
`LedgerFrame`을 생성한다.

별도 Molecule runtime, worker, cursor, sink를 만들지 않는다. 기존 Chain mapper 함수 모양과
기존 Ledger driver 실행 경계 안에서 작동한다.

## EventFrame

기존 source driver가 한 source event를 pandas DataFrame으로 전달한다. DataFrame attrs에는
immutable context만 둔다.

```text
source_id
source_event_id
molecule_ref
source_raw_ref
setup_snapshot_hash
```

identity는 driver plan의 선언 컬럼으로 결정하며 pandas index는 사용하지 않는다.

## RoleFrame v1

한 행은 Pack Claim 후보 하나다.

| 열 | 의미 |
|---|---|
| `source_event_id` | 입력 source event의 결정적 ID |
| `mapping_id` | Profile mapping ID |
| `claim_ref` | `pack@version/claim` |
| `roles` | Role ID → typed value mapping |
| `source_row_refs` | 후보를 만든 원천 행 identity 목록 |

`roles` 값의 허용형은 Registry가 정한다.

```text
entity   → {type, keys}
time     → timezone-aware datetime
quantity → number
identity/order/attribute → Role descriptor가 허용한 scalar
```

## 두 생산자

### Generic binder

단순 source는 Profile의 `column`, `constant`, `entity` binding을 평가해 RoleFrame을 만든다.
`entity`의 key 값은 `column|constant`만 허용한다. DB 조회는 하지 않는다.

### Python mapper

복잡한 리스트 분해, split/merge, 짝짓기, 계산이 필요한 source만 등록 Python Role mapper를
사용한다. 관계 join/enrich는 이 mapper보다 앞선 source preparer가 끝낸다. Mapper 작성
규격의 정본은 [`MAPPER_DESIGN_PATTERN.md`](./MAPPER_DESIGN_PATTERN.md)다.

```python
class CustomRoleMapper(BaseLedgerMapper):
    implementation_id = "registered-implementation"

    def interpret_unit(self, context, unit, profile):
        # 자유 코드는 준비된 unit → 닫힌 RoleEmission 변환뿐이다.
        return role_emissions
```

`BaseLedgerMapper.map()`은 입력 검증, unit partition, RoleFrame 조립·검증, 결정적 정렬을
공통 수행하고 최종 pandas RoleFrame을 반환한다. 하위 클래스는 `map()`을 재정의할 수 없다.
Python mapper도 `claim_ref`와 Role 값만 내며 Pack emission을 우회할 수 없다.

Mapper 내부 `group_by`는 `mappers.*.unit.columns`에 선언한 Mapper input columns만 사용한다.
Source Driver의 event identity/group_by는 transaction 경계이므로 이 내부 partition에 재사용하지
않는다.

## Pack Compiler

```text
RoleFrame row
→ ClaimDescriptor/RoleDescriptor 검증
→ Entity Registry 검증
→ EmissionDescriptor의 닫힌 $role mapping
→ Vocabulary signature 사전 검증
→ provenance 결합
→ LedgerFrame row
```

epistemic class와 derivation은 Pack/Source declaration에서 오며 Binding approval에서 오지 않는다.

## 미지원 구조

다음은 안정된 `unsupported_*` code/path로 거절한다.

- 임의 field transform
- 조건문/expression
- 동적 predicate
- 동적 payload key
- Pack에 없는 Role
- mapper의 raw Atom/LedgerFrame 반환
- source event를 가로지르는 mapper 결과
- lookup/declared_lookup/DB access

## dry-run

4단계 dry-run은 source fixture/EventFrame을 입력받아 다음을 출력하되 DB에 쓰지 않는다.

```text
normalized RoleFrame
compiled LedgerFrame
gate preview
provenance
snapshot hash
```

## 수락 테스트

- generic binder의 column/constant/entity → RoleFrame
- 기본 `DeclarativeRoleMapper`와 등록 Python mapper → 같은 RoleFrame 계약
- `BaseLedgerMapper.map()` 재정의 mapper 등재 거절
- Pack compiler가 source Entity → target Entity의 entity_ref를 유일하게 생성
- invalid stage-local Entity key/shape가 LedgerFrame 전 거절
- mapper raw LedgerFrame/Atom 반환 거절
- 같은 RoleFrame의 결정적 LedgerFrame
- Binding approval가 Claim class를 바꾸지 않음
- Pack/Vocabulary/Entity 변경이 snapshot hash와 provenance에 반영
- DB write/cursor advance 0

완료 후 멈추고 4단계 승인을 기다린다.

## 현재 구현 상태

`server/ledger/roleframe.py`가 EventFrame context 검증, `event|row|group_by` unit partition,
`RoleEmission` 조립, `DeclarativeRoleMapper`, sealed Python mapper implementation registry,
RoleFrame 검증, Pack/Vocabulary/Entity 기반 LedgerFrame compiler와 순수 dry-run을 구현한다.

Mapper context에는 Snapshot과 SourcePlan만 있으며 DB/session/cursor/gate/store capability가 없다.
기존 driver, Chain mapper, translator, gate/store/cursor는 수정하거나 연결하지 않았다. 현재는
독립 Audit은 exact commit `1d9bd4aa2f1b0ca5012c959e4647d8feab956ee1`을
`APPROVE`했다. 사용자 상설 승인에 따라 main에 병합했으며 5단계 착수가 승인됐다.
