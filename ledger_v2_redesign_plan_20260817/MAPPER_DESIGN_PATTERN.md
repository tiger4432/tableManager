# Ledger v2 Mapper Design Pattern

> 상태: `TARGET_CONTRACT` · 구현 전 단계별 승인 필요
> 참고: 루트 `MAPPER_STANDARD.md`의 Template Method 발상을 사용하되, 그 문서의 반환형과
> 파이프라인을 그대로 복제하지 않는다.

## 1. 최종 경계

```text
physical source
→ Cursor
→ Source Preparer
→ pandas EventFrame
→ BaseLedgerMapper.map()
→ pandas RoleFrame
→ Pack Compiler
→ pandas LedgerFrame
→ existing Gate / LedgerStore / Cursor transaction
```

Source Preparer는 join/enrich/frame 해소까지 맡고 완성된 EventFrame을 반환한다. Mapper는
EventFrame의 의미를 Pack Role로 해석한다. Mapper의 **외부 반환형은 항상 pandas RoleFrame**이다.
Claim 객체 목록, Atom, payload dict, LedgerFrame은 Mapper의 외부 출력이 될 수 없다.

## 2. 패턴 — Template Method + 등록 Strategy

`BaseLedgerMapper.map()`은 공통 파이프라인이며 하위 클래스가 덮어쓸 수 없다.

```python
class BaseLedgerMapper:
    @final
    def map(self, context, event_frame, descriptor, profile) -> pd.DataFrame:
        self._validate_input(event_frame, descriptor)
        units = self._partition_units(event_frame, descriptor.unit)
        emissions = []
        for unit in units:
            emissions.extend(self.interpret_unit(context, unit, profile))
        role_frame = self._assemble_role_frame(event_frame, emissions)
        self._validate_role_frame(role_frame, descriptor, profile)
        return self._deterministic_order(role_frame)

    def interpret_unit(self, context, unit, profile):
        raise NotImplementedError
```

Registry는 하위 클래스가 `map()`을 재정의하면 등재를 거절한다. 자유 코드는
`interpret_unit()` 하나에만 둔다. 이 훅의 내부 반환은 닫힌 `RoleEmission` record 목록이며,
공통 구현이 이를 표준 RoleFrame으로 조립한다.

```text
RoleEmission
  mapping_id
  claim_ref
  roles
  source_row_refs
```

## 3. 공통 부분과 자유 부분

| 공통 기본 구현 소유 | 개별 Mapper 자유 부분 |
|---|---|
| EventFrame 필수 열/자료형 검증 | 준비된 값의 업무 의미 해석 |
| 선언된 unit strategy 실행 | 분기, 짝짓기, 리스트 분해, 계산 |
| source event ID/provenance 계승 | 어떤 등록 Claim 후보를 낼지 결정 |
| RoleFrame 고정 열 조립 | Claim Role 값 산출 |
| `claim_ref`/Role/EMITS 대조 | 명시적 거절 사유 산출 |
| 결정적 행 정렬 | 없음 이외의 값을 추측하지 않기 |
| event 경계 이탈·빈/추가 열 거절 |  |

공통 unit strategy v1은 `event`, `row`, `group_by`만 지원한다. 새 strategy는 등록 구현과
테스트를 추가해야 하며 source/table 이름 분기를 core에 넣지 않는다. Source Driver의
event boundary는 cursor·transaction 원자성 단위이고, Mapper unit은 그 EventFrame 내부의
해석 단위다. 둘을 같은 선언으로 중복 작성하지 않는다.

## 4. 기본 Mapper와 사용자 Mapper

### `DeclarativeRoleMapper`

단순 source의 기본 구현이다. Profile의 승인된 `column`, `constant`, `entity` binding을
평가해 RoleEmission을 만들며 사용자 Python 코드를 요구하지 않는다.

### 등록 Python Mapper

split/merge, 위치별 리스트 분해, 여러 행 짝짓기처럼 Profile binding만으로 표현하기 어려울
때만 `BaseLedgerMapper`를 상속한다. 구현 코드는 `interpret_unit()`만 제공한다.

```python
class LotEventRoleMapper(BaseLedgerMapper):
    implementation_id = "lot-event-role"

    def interpret_unit(self, context, unit, profile):
        # unit은 Source Preparer가 완성한 DataFrame 조각이다.
        # 반환은 RoleEmission뿐이다.
        ...
```

config에는 module/function/path를 적지 않는다. `ledger_config.json.mappers`가 mapper ID,
version, unit, input contract, 허용 `claim_ref`와 trusted `implementation_id`를 선언한다.
코드는 `implementation_id`에 대응하는 안전한 클래스만 제공한다. 도메인 mapper 등록값과
실행 가능한 Python 경로를 한 개념으로 섞지 않는다.

## 5. Context와 금지 경계

`MapperContext`에는 immutable setup snapshot, source event provenance, Profile/Registry read
view만 있다. writable DB session, relation reader, cursor, commit/rollback, gate/store는 없다.

Mapper에서 금지한다.

- DB 조회와 virtual join: Source Preparer 책임
- event 간 상태와 전역 mutable cache
- raw Atom/LedgerFrame/object_payload 생성
- 동적 predicate, 임의 payload key, SQL/Python/expression 실행
- provenance/cursor/gate/store 조작
- Pack에 없거나 descriptor가 허용하지 않은 `claim_ref`/Role 출력

## 6. RoleFrame 출력 계약

한 행은 Pack Claim 후보 하나다.

| 열 | 의미 |
|---|---|
| `source_event_id` | 입력 EventFrame에서 계승한 결정적 사건 ID |
| `mapping_id` | Profile mapping ID |
| `claim_ref` | `pack@version/claim` |
| `roles` | Role ID → typed value |
| `source_row_refs` | 후보 근거가 된 준비 전 원천 행 identity 목록 |

Mapper는 추가 열을 반환하지 않는다. 공통 구현은 동일 source event 밖의 ID, 미등록 Claim,
미등록/누락 Role, 잘못된 Role 형상, 선언한 emits와 실제 결과 불일치를 fail-closed로 거절한다.

## 7. Config 연결

```jsonc
{
  "mappers": {
    "default-role@1": {
      "implementation_id": "declarative-role",
      "unit": {"kind": "row"},
      "emits": ["transfer@1/movement"]
    },
    "dt-transfer@1": {
      "implementation_id": "dt-transfer-role",
      "unit": {"kind": "event"},
      "input_columns": ["core_wafer_id", "inventory_dt_lot", "inventory_dt_slot",
                        "resolved_dt_x", "resolved_dt_y", "event_time"],
      "emits": ["transfer@1/movement"]
    }
  },
  "sources": {
    "dt_log": {
      "driver": {
        "preparation": {
          "preparer_id": "dt-transfer-frame@1",
          "inherit_virtual_join_rules": ["dt_log_to_dt_inventory"]
        },
        "mapper_id": "dt-transfer@1"
      },
      "profile_id": "dt-transfer@1"
    }
  }
}
```

Source Preparer output schema는 Mapper input contract를 만족해야 하고, Mapper emits는 Profile이
승인한 mapping과 Pack Claim의 부분집합이어야 한다. 이 교차 검증은 DB 실행 전에 끝난다.

## 8. 수락 테스트

- `BaseLedgerMapper.map()` 재정의 mapper 등재 거절
- 기본 `DeclarativeRoleMapper`가 표준 RoleFrame 반환
- 등록 Python Mapper도 동일 열/자료형 RoleFrame 반환
- EventFrame input schema와 preparer output schema 교차 검증
- unit strategy별 결정적 partition과 행 순서 독립성
- 미등록 Claim/Role, required Role 누락, EMITS 불일치 거절
- mapper의 Atom/LedgerFrame/임의 DataFrame 반환 거절
- event boundary 이탈 결과 거절
- 동일 EventFrame/Profile/snapshot의 결정적 RoleFrame
- mapper DB/write/cursor capability 부재
- RoleFrame 이후 Pack compiler 단독 LedgerFrame 생성
- mapper 실패 시 Atom 0, cursor 미이동
