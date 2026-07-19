# 2026-07-19 19:52:00 - 비즈니스 키 충돌 행 병합 시 사용자(User) 값 충돌의 신규값 덮어쓰기 정책 구현

## 1. 개요 및 동기
* **배경 및 요구사항**:
  * 비즈니스 키 충돌(예: 가상 행을 맵 그리드 상에 배치하여 실존하는 칩과 충돌 발생) 시, 껍데기 행을 실존하는 행에 밀어 넣는 **Silent Merge** 동작을 수행합니다.
  * 기존 병합 정책은 충돌 대상 행에 이미 사용자가 수정한 데이터(User Overwrite)가 기입되어 있으면, 새로 유입되는 값에 의해 덮어씌워지지 않도록 무조건 기존의 사용자 값을 보호(is_value_protected)하게 설계되어 있었습니다.
  * 하지만 **새로 병합되는 유입 행의 값 역시 사용자가 직접 기입/수정한 값(User Value)인 경우**, 사용자가 인지하고 덮어씌운 상황이므로 기존의 보호 정책을 건너뛰고 **새로 유입되는 사용자 입력값을 적용(Overwrite)**해야 합니다.
* **해결 방안**:
  * 백엔드 CRUD 모듈(`apply_batch_updates` 및 `set_cell_manual_priority_batch`) 내 병합 가드 논리를 수정했습니다.
  * 기존 행에 사용자 입력값 보호 설정(`is_old_user_overwritten`)이 존재하더라도, 새로 들어오는 값(`update_item`) 또는 병합되는 행(`row_to_delete`)에 사용자 수준의 오버라이트 설정(`is_new_user_overwritten`)이 확인되는 경우:
    * 두 레코드 모두 사용자 작성 데이터(User vs User)로 판단합니다.
    * 보호 가드를 풀고(`is_value_protected = False`), 새로 유입되는 사용자 값으로 덮어씁니다.
  * 만약 한쪽이 시스템(System/Parser) 수정값이고 다른 쪽이 사용자(User) 입력값인 경우엔 기존처럼 사용자 값을 온전히 보호합니다.

---

## 2. 주요 구현 사항

### A. 사용자 데이터 간의 충돌 판단 및 덮어쓰기 로직 구현 (`server/database/crud.py`)
* `apply_batch_updates` 및 `set_cell_manual_priority_batch` 내부의 병합 루프에 `is_new_user_overwritten` 체크식을 추가했습니다.

```python
                            is_old_user_overwritten = False
                            if old_ow:
                                if old_ow.updated_by != "collision_merge" and old_ow.manual_priority_source != "collision_merge":
                                    is_old_user_overwritten = old_ow.is_overwrite or (old_ow.manual_priority_source is not None)
                                
                            # 새 값이 사용자 입력값인지 판단 (요청 소스 또는 row_to_delete의 CellOverwrite 확인)
                            is_new_user_overwritten = (update_item.source_name == "user" or (update_item.updated_by and update_item.updated_by != "system" and "parser" not in str(update_item.updated_by).lower()))
                            new_ow = overwrites_cache.get((row_to_delete.row_id, col_name)) if overwrites_cache else None
                            if not new_ow:
                                new_ow = db.query(models.CellOverwrite).filter(
                                    models.CellOverwrite.table_name == table_name,
                                    models.CellOverwrite.row_id == row_to_delete.row_id,
                                    models.CellOverwrite.column_name == col_name
                                ).first()
                            if new_ow:
                                if new_ow.updated_by != "collision_merge" and new_ow.manual_priority_source != "collision_merge":
                                    is_new_user_overwritten = is_new_user_overwritten or new_ow.is_overwrite or (new_ow.manual_priority_source is not None)

                            if is_old_user_overwritten and is_new_user_overwritten:
                                # 사용자 값 간의 충돌: 새로 유입되는 사용자 값으로 덮어씀 (보호 해제)
                                is_value_protected = False
                            else:
                                is_value_protected = is_old_user_overwritten and not is_explicitly_edited
```

### B. 단위 테스트 작성 및 검증 (`server/tests/test_composite_business_key.py`)
* 사용자(user_a)의 기존 칩 맵 데이터가 존재하는 상황에서 사용자(user_b)의 수정 데이터 충돌이 병합 유입되었을 때, 신규 값으로 최종 업데이트가 성립되는지 테스트하는 `test_user_vs_user_conflict_merge` 유닛 테스트를 추가하고 통과시켰습니다.

---

## 3. 아키텍처 영향 보고
* **안전하고 유연한 사용자 협업 정책**: 서로 다른 사용자 세션 또는 신구 사용자 데이터 간의 맵 정렬 충돌 시, 사용자가 수동 조작을 거친 신규 값이 유실되지 않고 의도한 대로 덮어씌워지므로 기동 데이터 유실 및 수동 보정 반복 피로도가 획기적으로 경감됩니다.
* **테스트 정합성 확보**: 신규 추가한 충돌 우선권 테스트를 포함한 총 31개 단위 테스트가 빌드 및 테스트 환경에서 무사 통과되었습니다.
