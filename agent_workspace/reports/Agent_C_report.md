# Agent C Report — Configurable Metadata & Dynamic Schema API 구현 완료

- **작성자**: Antigravity (Agent C 역할)
- **작성일**: 2026-04-12
- **참조 스킬**: `SubAgentExecution`, `WebSocketExpert`

---

## 📌 작업 요약

서버에 하드코딩되어 있던 테이블별 비즈니스 키 및 컬럼 설정을 외부 JSON 파일로 분리하고, 클라이언트가 이를 실시간으로 조회할 수 있는 스키마 엔드포인트를 구현하였습니다.

---

## 🔧 변경 내역

### 1. 설정 파일 추가: `server/config/table_config.json`
- 테이블별 `business_key` 및 `display_columns` 정의를 중앙 집중화하였습니다.
- 새로운 테이블 추가 시 서버 코드 수정 없이 해당 파일만 업데이트하면 됩니다.

### 2. 백엔드 로직 수정: `server/database/crud.py`
- `load_table_config()` 함수 구현: 서버 시작 시 `table_config.json`을 로드합니다.
- 하드코딩된 `TABLE_BUSINESS_KEYS`를 제거하고 `TABLE_CONFIG`를 참조하도록 `get_row_by_business_key` 및 `upsert_row` 로직을 업데이트하였습니다.

### 3. 신규 API 엔드포인트: `server/main.py`
- `GET /tables/{table_name}/schema` 추가:
  - 설정 파일에 정의된 컬럼 리스트를 반환합니다.
  - 설정이 없는 경우, 데이터베이스의 첫 번째 행에서 키를 동적으로 추출하여 반환하는 Fallback 로직을 포함합니다.

---

## ✅ 검증 결과

1. **Schema API 테스트**
   - 정의된 테이블(`inventory_master`) 호출 시 설정된 4개 컬럼이 정확히 반환됨을 확인하였습니다.
   - 정의되지 않은 테이블(`raw_table_1`) 호출 시 실제 데이터 구조에서 컬럼 리스트가 동적 추출됨을 확인하였습니다.

2. **비즈니스 키 Upsert 테스트**
   - 설정 파일에서 변경된 비즈니스 키(`plan_id` 등)를 기반으로 Upsert 기능이 정상 작동(Create/Update 분기 및 중복 방지)함을 검증하였습니다.

---

## 🔍 향후 참고 사항
- `table_config.json` 로드 시 발생할 수 있는 파일 누락이나 JSON 파싱 오류에 대해 예외 처리가 되어 있어 서버 안정성을 유지합니다.
- 클라이언트는 이제 `/schema` API를 호출하여 테이블 뷰의 컬럼 헤더를 동적으로 구성할 수 있습니다.
