# AssyManager: 비즈니스 로직 및 레이어링 엔진 명세서

본 문서는 데이터 원천(Sources) 간의 우선순위 결정, 중첩 레이어링, 그리고 전구간 감사 로그(Audit) 관리 메커니즘을 기술합니다. 데이터가 왜 특정 값으로 표시되는지 디버깅할 때의 핵심 지침서입니다.

---

## 층 1. 데이터 레이어링 (Data Source Layering)

AssyManager는 하나의 셀에 여러 원천 데이터를 저장할 수 있는 **중첩형(Nested) JSON 구조**를 사용합니다.

### 1.1 데이터 구조 (`models.DataRow`)
- 각 셀은 단순한 값이 아닌 다음과 같은 딕셔너리 구조를 가집니다:
  ```json
  "column_name": {
    "value": "최종 결정값",
    "is_overwrite": true,
    "priority_source": "user",
    "manual_priority_source": null,
    "sources": {
      "user": {"value": "ABC", "updated_at": "..."},
      "parser_v1": {"value": "ABD", "updated_at": "..."}
    }
  }
  ```

### 1.2 우선순위 엔진 (`compute_priority_value`)
- **로직 순서**: 
  1. **수동 고정(Manual Pinning)**: `manual_priority_source`가 지정되어 있으면 해당 소스의 값을 무조건 사용.
  2. **가중치 기반**: 사전 정의된 가중치(`SOURCE_PRIORITY`)에 따라 가장 높은 소스의 값을 선택. (예: `user` > `parser_b` > `parser_a`)
  3. **최신성**: 가중치가 같다면 `updated_at`이 가장 최근인 데이터를 선택.

---

## 🕵️ 2. 감사 로그 및 계보 추적 (Audit & Lineage)

### 2.1 자동 로그 생성 (`crud.py`)
- 모든 데이터 수정(`update_cell`, `upsert_row`) 시, 이전 `value`와 새 `value`를 비교합니다.
- 실제 값이 변경된 경우에만 `AuditLog` 테이블에 레코드를 생성하여 DB 용량 최적화 및 노이즈 제거를 수행합니다.

### 2.2 계보 조회 (Lineage Tracking)
- UI에서 특정 셀을 선택하면 해당 셀의 모든 `AuditLog`를 시간 역순으로 조회합니다.
- 파일 인제션으로 인한 변경인지, 사용자의 직접 수정인지 소스 명칭(`source_name`)으로 확인 가능합니다.

---

## 🛠️ 3. 디버깅 가이드 (Logic Domain)

### Q: 파일을 인제션했는데 UI에 이전 값이 그대로 보입니다.
- **원인**: 사용자가 이미 해당 셀을 수동으로 수정(`user` source 생성)했기 때문입니다. `user` 소스는 인제션 파서보다 높은 우선순위를 가집니다.
- **확인**: '원천 데이터 관리' 다이얼로그에서 `user` 레이어를 삭제하거나, 신규 인제션 소스로 우선순위를 고정(Pin)하십시오.

### Q: 히스토리 패널에 로그가 너무 많이 남습니다.
- **확인**: `crud.py`에서 `old_value == new_value` 체크 로직이 정상 작동하는지 확인하십시오. 인제션 스크립트가 동일한 값을 반복적으로 업서트하지 않는지도 점검이 필요합니다.

---
*AssyManager Business Logic Specification v2.0*
