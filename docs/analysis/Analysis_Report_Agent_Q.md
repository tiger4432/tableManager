# Analysis Report — Agent Q (System Integrity & API Integration)

- **작성자**: Antigravity (Agent Q 역할)
- **작성일**: 2026-04-12
- **분석 대상**: `server/main.py`, `client/ui/panel_history.py`, `server/database/models.py`, `server/database/crud.py`

---

## 1. API Robustness (견고성 분석)

### [강점]
- **Pydantic Schema 활용**: `schemas.py`를 통해 요청 데이터의 구조와 타입을 강제하며, 필수 필드 누락 시 FastAPI가 자동으로 422 Unprocessable Entity 응답을 반환함.
- **RESTful 구조**: 리소스 기반의 명확한 엔드포인트 설계(`PUT /cells`, `DELETE /rows`, `GET /schema` 등).

### [취약점 및 개선 권장]
- **테이블 이름 검증 부재**: `table_name`이 경로 파라미터로 입력되나, `TABLE_CONFIG`에 정의된 유효한 테이블인지 확인하지 않고 쿼리에 사용함. 존재하지 않는 테이블 이름 입력 시 빈 결과가 반환되거나 의도치 않은 동작이 발생할 수 있음.
- **에러 핸들링**: 404 에러 외에 DB 연결 오류나 JSON 파싱 오류 등에 대한 상세 에러 메시지 처리가 미흡함.
- **비즈니스 키 검색 성능**: `get_row_by_business_key`에서 모든 행을 메모리로 로드한 뒤 Python에서 필터링함. 데이터가 수천 건 이상일 경우 O(N) 성능 저하가 우려됨. (SQLite의 `->` 또는 `json_extract` 연산자를 활용한 DB 레벨 필터링 권장)

---

## 2. Integrity Management (무결성 및 계보 관리)

### [강점]
- **AuditLog (감사 로그)**: 모든 셀 변경에 대해 `old_value`, `new_value`, `source_name`, `updated_by`를 기록하여 완벽한 데이터 계보(Lineage) 추적이 가능함.
- **Multi-Source Priority**: `SOURCE_PRIORITY`를 통해 사용자(user) 수정이 파서(parser) 데이터보다 항상 우선순위를 갖도록 설계되어 데이터 신뢰성을 보장함.
- **flag_modified**: SQLAlchemy의 JSON 컬럼 변경 감지 한계를 `flag_modified`로 명시적으로 해결하여 업데이트 누락을 방지함.

---

## 3. Cross-Component Sync (컴포넌트 간 동기화)

### [강점]
- **Dynamic Schema API**: `/schema` 엔드포인트를 통해 클라이언트가 서버 설정(`table_config.json`)을 실시간으로 반영하여 UI 컬럼을 구성함. 코드 변경 없이 컬럼 추가/삭제가 가능함.
- **Shared WebSocket**: 클라이언트에서 단일 WS 연결을 통해 모든 탭(테이블)의 변경 사항을 실시간으로 수신하고, `_dispatch_ws_message`를 통해 각 모델에 효율적으로 배분함.

### [체크리스트 — 아키텍처 보호를 위한 권장 사항]
- [ ] **Table Whitelisting**: `crud.py` 등에 유효 테이블 체크 함수를 추가하고 모든 API 진입점에서 검증 수행.
- [ ] **JSON Query Optimization**: `get_row_by_business_key`를 SQLAlchemy의 JSON 필터링 기능으로 변경.
- [ ] **Authentication**: 프로덕션 환경을 위해 최소한의 API Key 또는 JWT 인증 체계 도입 필요.
- [ ] **Batch Logic Bulk Insert**: `update_cells_batch`의 성능 향상을 위해 다중 행 동시 업데이트 쿼리 최적화 고려.

---

## 4. 최종 결론

assyManager 시스템은 동적인 JSON 스키마와 강력한 감사(Audit) 기능을 갖추고 있어 데이터의 유연성과 신뢰성이 매우 높습니다. 특히 WebSocket을 통한 실시간 동기화와 우선순위 기반 데이터 결정 로직은 협업 에디터로서의 핵심 가치를 잘 구현하고 있습니다. 위에서 언급된 성능 최적화 및 유효성 검증 로직을 보완한다면 대규모 데이터 환경에서도 견고한 플랫폼으로 발전할 수 있을 것입니다.

---

## 5. 부록: API 명세 (API Specification)

본 섹션은 `assyManager` 서버의 REST API 엔드포인트와 데이터 입출력(I/O) 형식을 기술합니다.

### 5.1 공통 데이터 구조 (Data Models)

#### `CellData`
단일 셀의 값과 메타데이터를 포함합니다.
```json
{
  "value": "Any",
  "is_overwrite": false,
  "sources": {
    "user": { "value": "...", "timestamp": "..." },
    "parser_a": { "value": "...", "timestamp": "..." }
  },
  "updated_by": "system",
  "priority_source": "user"
}
```

#### `DataRowResponse`
하나의 행(Row)에 대한 응답 형식입니다.
```json
{
  "row_id": "UUID-STR",
  "table_name": "inventory_master",
  "data": {
    "column_name": { "value": "...", "is_overwrite": false, ... }
  },
  "created_at": "ISO-DATETIME",
  "updated_at": "ISO-DATETIME"
}
```

### 5.2 API Endpoints

#### [GET] `/tables`
- **설명**: 서버에 정의된 모든 테이블 목록을 조회합니다.
- **Output**: `{"tables": ["inventory_master", "production_plan", ...]}`

#### [GET] `/tables/{table_name}/schema`
- **설명**: 특정 테이블의 컬럼 이름(Display Columns)을 조회합니다.
- **Output**: `{"table_name": "...", "columns": ["col1", "col2", ...]}`

#### [GET] `/tables/{table_name}/data`
- **설명**: 테이블의 데이터를 페이징하여 조회합니다. (Lazy Loading 지원)
- **Parameters**: `skip` (int), `limit` (int)
- **Output**: `PaginatedDataResponse`

#### [PUT] `/tables/{table_name}/cells` / `/cells/batch`
- **설명**: 단일 또는 다중 셀의 값을 업데이트합니다.
- **Input (Single)**: `{"row_id": "...", "column_name": "...", "value": "..."}`
- **Input (Batch)**: `{"updates": [...]}`

#### [PUT] `/tables/{table_name}/upsert`
- **설명**: 비즈니스 키 기반 Upsert (Update or Insert)를 수행합니다.
- **Input**: `{"business_key_val": "...", "updates": {...}, "source_name": "..."}`

#### [POST] `/tables/{table_name}/rows` / [DELETE] `/rows/{row_id}`
- **설명**: 행 생성 및 삭제.

#### [GET] `/history` (Row/Cell)
- **설명**: 특정 행 또는 셀의 전체 변경 이력(Audit Log)을 조회합니다.

---

### 5.3 Real-time Synchronization (WebSocket)

#### `WS /ws`
- **Event**: `cell_update`, `batch_cell_update`, `row_create`, `row_delete` 등을 통해 실시간으로 클라이언트 간 동기화를 유지합니다.
