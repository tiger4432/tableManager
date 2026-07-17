# 함수 시그니처 변경 영향 분석 및 병합 데이터 보존 지침서

이 문서는 `assyManager` 프로젝트 내에서 공용 유틸리티, 데이터베이스 CRUD 코어를 변경할 때 발생할 수 있는 부작용(Side-effects)을 방지하고, 충돌 병합 시의 데이터 유실을 막기 위해 모든 에이전트가 엄격히 준수해야 하는 엔지니어링 표준 지침서입니다.

---

## 1. 함수/메서드 시그니처 변경 영향 분석 규정 (Signature Impact Analysis)

핵심 CRUD 모듈(`server/database/crud.py`)이나 공용 API 구조의 매개변수/반환 구조를 수정할 경우, 단 한 곳의 누락으로도 런타임 언패킹 에러(`ValueError: too many values to unpack`)가 발생해 파이프라인 전체가 마비됩니다. 

### 🚨 필수 준수 수칙
1. **전수 검색 (Grep Search)**:
   * 반환값의 개수나 타입을 변경하기 전, 반드시 프로젝트 전체에서 해당 함수의 호출부를 검색하여 영향 범위를 사전 파악하십시오.
2. **연쇄 수정 의무 대상**:
   * **웹 API 라우터**: `server/main.py` 내의 Endpoint 호출부
   * **백그라운드 데몬 워커**: `server/chain_ingestion_worker.py` (실시간 연쇄 업데이트 엔진)
   * **테스트 코드 스위트**: `server/tests/` 내의 모든 단위/통합 테스트 코드
3. **컴파일 및 테스트 검증**:
   * 시그니처 변경 작업 후, 반드시 가상환경 내에서 `pytest`를 수행하여 언패킹 오류가 없음을 증명해야 합니다.

---

## 2. 병합(Silent Merge) 시 데이터 보존 및 이중 추적 수칙 (Data Preservation)

복합 비즈니스 키 중복 등으로 인해 행 병합이 발생할 때, 사용자가 의도치 않게 수정한 적 없는 데이터가 덮어씌워져 기존 오버라이트 값이 영구 유실(삭제)되거나 데이터의 원천 추적이 깨지는 현상을 방지해야 합니다.

### 🚨 필수 준수 수칙

```
                       [ 중복 충돌 병합 (Silent Merge) ]
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
      [데이터 보존 정책]                        [이중 추적 아키텍처]
  충돌 행에 기존 사용자 오버라이트         - 값의 오리지널 근원(예: file.txt)은
  (수동 수정 / 핀 고정)이 이미 있고            CellSource에 그대로 보존
  이번 updates에서 이 컬럼을 직접         - 병합 충돌 이력은 CellOverwrite의
  수정한 게 아니라면 -> "기존 값 보존"          updated_by = 'collision_merge'
                                           로 기록하여 빨간색 채색 유지
```

### A. 기존 사용자 수정값 보존 정책 (Data Preservation Guard)
* **상황**: `'a,b'` 행(값 `'c'`)을 `'A,B'` 로 비즈니스 키 변경 시, 대상 행 `'A,B'`에 이미 사용자가 수동 수정해 놓은 값 `'d'`가 존재하고 있을 때.
* **동작 규칙**:
  * 충돌 대상 행(`conflict_row`)에 이미 유효한 사용자 오버라이트(`CellOverwrite.is_overwrite = True` 또는 핀 고정) 정보가 존재하고,
  * 이번 수정 요청(`update_item.updates` 또는 `req.updates`)에서 해당 셀을 명시적으로 직접 고친 이력이 없는 경우,
  * **충돌 행에 존재하던 기존 값(`old_val`)을 철저히 보존(덮어쓰기 무시 및 유지)**해야 합니다.

### B. 데이터 원천명 계승 및 이중 추적 (Double Tracking)
* **원천 정보 보존**:
  * 병합 시점에 `CellSource` 의 `source_name` 을 일괄 `"collision_merge"` 로 하드코딩 교체하지 마십시오.
  * 삭제되는 껍데기 행이 가졌던 **오리지널 원천 소스명(예: `file.txt`)을 추적(`_load_metadata_row_cell` 사용)하여 그대로 물려받아(계승)** `CellSource` 에 이식 적재해야 합니다.
* **병합 유형 기록**:
  * 이 셀이 충돌 병합을 거쳤다는 사실은 **`CellOverwrite.updated_by = "collision_merge"`** 및 **`manual_priority_source = "collision_merge"`** 로 `CellOverwrite` 메타데이터에 기록하여, 그리드 상에서 정확히 빨간색 스타일로 렌더링되도록 처리하십시오.
