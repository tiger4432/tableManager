# Agent C v2 Report — Business Key Lookup & Upsert API 구현 완료

- **작성자**: Antigravity (Agent C 역할)
- **작성일**: 2026-04-12
- **참조 스킬**: `SubAgentExecution`

---

## 📌 작업 요약

기존의 UUID 기반 접근 외에, 각 테이블의 의미론적 고유 키(Business Key)를 기반으로 데이터를 조회하고 업데이트(또는 생성)할 수 있는 Upsert 엔진과 API를 구현하였습니다.

---

## 🔧 변경 내역

### 1. `server/database/crud.py`
- `TABLE_BUSINESS_KEYS` 매핑 정의:
  - `inventory_master` → `part_no`
  - `production_plan` → `plan_id`
  - `sensor_metrics` → `sensor_id`
- `get_row_by_business_key`: JSON 내부의 특정 컬럼 `value`를 검색하여 해당하는 `DataRow`를 반환합니다.
- `upsert_row`: 비즈니스 키로 행을 검색한 뒤, 존재하면 업데이트(Update), 존재하지 않으면 신규 생성(Insert) 후 데이터를 업데이트합니다. 이 과정에서 `create_audit_log`를 통해 변경 이력이 모두 기록됩니다.

### 2. `server/database/schemas.py`
- `CellUpsert` 스키마 추가: 비즈니스 키 값과 업데이트할 데이터 맵(`updates`)을 포함합니다.

### 3. `server/main.py`
- `PUT /tables/{table_name}/upsert` 엔드포인트 추가.
- Upsert 동작 결과에 따라 WebSocket 브로드캐스트 전송:
  - 신규 생성 시: `row_create` 이벤트
  - 기존 수정 시: `batch_cell_update` 이벤트

---

## ✅ 검증 결과

- 테스트 스크립트(`server/verify_upsert.py`)를 통해 아래 시나리오를 검증하였습니다:
  1. **최초 호출**: 존재하지 않는 `part_no`로 `upsert` 호출 시 신규 행이 생성(`is_new: true`)됨을 확인.
  2. **재호출**: 동일한 `part_no`로 다른 값을 `upsert` 호출 시, 신규 행 생성 없이 기존 행의 데이터만 갱신(`is_new: false`)됨을 확인.
  3. **데이터 정합성**: 최종 조회 시 업데이트된 값이 정확히 반영되어 있으며, 감사 로그가 생성되었음을 확인.

---

## 🔍 향후 참고 사항
- 현재 비즈니스 키 검색은 Python 레벨에서 수행됩니다. 데이터 양이 수만 건 이상으로 늘어날 경우 SQLite의 JSON 추출 인덱싱(JSON Indexing)을 활용한 쿼리로 최적화가 필요할 수 있습니다.
