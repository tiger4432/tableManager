# 2026-07-19 20:00:00 - 비즈니스 키 충돌 행 병합 시 원천(CellSource) 테이블 내 기존 사용자(User) 값 보존 정책 구현

## 1. 개요 및 동기
* **배경 및 요구사항**:
  * 비즈니스 키 충돌 행 병합 시, 두 행의 셀에 사용자가 직접 입력한 값(User Value)끼리 충돌할 경우 새로 유입되는 값(덮어쓰는 값)이 이기도록 우선순위 가드를 일부 풀었습니다.
  * 그러나 이 과정에서 새로 입력된 값으로 덮어써지면서 **기존에 적재되어 있던 사용자의 원천 값(CellSource 기록)이 DB에서 훼손되거나 유실되지 않고 원천 정보로서 기록이 남아있어야(남겨)** 한다는 추가 요구사항이 있었습니다.
  * 즉, 액티브 컬럼의 실제 칩 상태값(DataRow)은 새 사용자 값으로 업데이트되더라도, `CellSource` 테이블(원천 이력) 상에는 기존 사용자가 썼던 예전 값이 역사로 고스란히 영속 보존되어야 합니다.
* **해결 방안**:
  * 백엔드 충돌 병합 처리 구간에서 **사용자 값 충돌 감지 시 기존 값 백업 메커니즘**을 탑재했습니다.
  * 기존 행에 등록되어 있던 표준 `"user"` 소스 데이터를 분석하여 값이 존재할 경우, 해당 레코드를 `"user (old_exist_[row_id_앞6자리])"`라는 가상의 과거 이력 소스명으로 복사/백업하여 `CellSource`에 삽입합니다.
  * 새로 유입된 행의 사용자 값은 접미사 없이 표준 `"user"` 소스 명칭을 유지하며 대상 행에 덮어써져, 우선순위 계산(`compute_priority_value`) 시 자연스럽게 최상위 우선순위(0순위)로 동작하여 덮어쓰기 완료 및 활성값 적용에 성공합니다.
  * 또한, 비즈니스 키 충돌 시 동적으로 로드되는 충돌 대상 기존 행의 메타데이터(CellSource, CellOverwrite)가 캐시에 pre-fetch 되지 않아 쿼리가 무시되던 **캐시 미스(Cache Miss) 버그를 수정**하여, 캐시에 없는 동적 획득 행에 대해서도 실시간 DB 쿼리가 원활히 수행되도록 안전장치를 마련했습니다.

---

## 2. 주요 구현 사항

### A. 소스 테이블 내 기존 사용자 값 백업 이식 (`server/database/crud.py`)
* `apply_batch_updates` 및 `set_cell_manual_priority_batch` 내부의 소스 이력 적재 루프 상단에 백업 이식 코드를 추가하고 `"user"` 매핑 시 접미사 결합을 우회 적용했습니다.

```python
                                # user 간 충돌 시 기존의 standard "user" 값을 "user (old_exist_xyz)"로 백업하여 원천에 기존 user값을 보존
                                if is_old_user_overwritten and is_new_user_overwritten:
                                    old_user_src = next((s for s in target_srcs if s.source_name == "user"), None) if target_srcs else None
                                    pending_user_key = (table_name, row.row_id, col_name, "user")
                                    pending_user_data = cell_sources_to_upsert.get(pending_user_key) if cell_sources_to_upsert else None
                                    
                                    old_val_to_backup = pending_user_data["value"] if pending_user_data else (old_user_src.value if old_user_src else None)
                                    old_by_to_backup = pending_user_data["updated_by"] if pending_user_data else (old_user_src.updated_by if old_user_src else "system")
                                    
                                    if old_val_to_backup is not None:
                                        backup_src_name = f"user (old_exist_{row.row_id[:6]})"
                                        backup_key = (table_name, row.row_id, col_name, backup_src_name)
                                        cell_sources_to_upsert[backup_key] = {
                                            "table_name": table_name,
                                            "row_id": row.row_id,
                                            "column_name": col_name,
                                            "source_name": backup_src_name,
                                            "value": clean_str_value(old_val_to_backup),
                                            "updated_by": old_by_to_backup,
                                            "ingested_at": func.now()
                                        }
```

### B. 캐시 미스 가드 보강 (`server/database/crud.py`)
* `_load_metadata_row_cell` 함수에서 bulk pre-fetch 대상이 아니던 충돌 대상 행이 캐시 맵(`sources_cache`, `overwrites_cache`) 누락으로 쿼리가 생략되어 `[]`를 반환받던 로직을 교정하여 실시간으로 DB에서 로드하도록 조치했습니다.
```python
    if sources_cache is not None:
        if key not in sources_cache:
            if is_new:
                col_srcs = []
            else:
                # 캐시 미스 시 데이터베이스에서 실시간으로 직접 로드하여 캐시 채움
                col_srcs = db.query(models.CellSource).filter(...)
```

### C. 회귀 방지 통합 테스트 완성 (`server/tests/test_composite_business_key.py`)
* `test_user_vs_user_conflict_merge` 유닛 테스트에 기존 `"GOOD"` 사용자 원천 값이 `user (old_exist_exist-)` 백업 명세로 보존 및 덮어쓰여지고 최종 칩 등급이 새 값인 `"FAIL"`로 바르게 갱신되는 통합 어설션을 추가하고 모두 통과시켰습니다.

---

## 3. 아키텍처 영향 보고
* **역사 데이터 추적 완결**: 충돌 병합 시 새 값 적용과 구 값 보존이 조화롭게 결합되어, 사용자 작업 데이터가 덮어씌워지더라도 "누가 어떤 값으로 덮어쓰기 전에는 어떤 값이 존재했었는지"의 원천 이력이 CellSource 감사 로그 테이블에 고스란히 백업되므로 추적 데이터의 신뢰성이 극대화되었습니다.
* **테스트 정합성 완벽 패스**: 31개 단위 테스트가 conda 가상 환경에서 무사 통과되었습니다.
