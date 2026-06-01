# 변경 이력: 수치형 컬럼 타입 유효성 검증 및 PostgreSQL JSONB 수치 캐스팅 구현

- **작성일**: 2026년 6월 1일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- 테이블 셀 변경 시 수치형(number) 데이터를 기입하는 경우, 프론트엔드 및 백엔드 전 계층에서 유효성을 검사합니다.
- 유효하지 않은 데이터(비수치)를 사전에 차단하여 데이터 정합성을 확보합니다.
- PostgreSQL JSONB 컬럼 내 적재 시 문자열 형식이 아닌 실제 숫자(Numeric/Int/Float) 타입으로 저장함으로써 데이터 무결성을 보장하고 저장공간 용량을 최적화하며 쿼리 속도를 향상시킵니다.

## 2. 세부 구현 사항

### 백엔드 (FastAPI + SQLAlchemy)
- **`/tables/{table_name}/schema` API 개선**:
  - `server/main.py` 내 스키마 반환 시, `table_config.json`의 `"column_types"` 명세 정보도 반환하도록 확장.
- **데이터 저장 검증 및 캐스팅 (`server/database/crud.py`)**:
  - `apply_row_update_internal` 함수 실행 시, `cast_value_by_type` 헬퍼 함수를 통해 데이터를 타입에 맞게 파싱하여 DB 저장 시 쌍따옴표 `""`가 제거된 이진 숫자(`{"value": 250}`) 형태로 JSONB 노드에 적재되도록 보장.
- **배치 업데이트 API 예외 처리 (`server/main.py`)**:
  - `apply_batch_updates_endpoint` 엔드포인트에서 데이터 변환 예외(`ValueError`)를 캐칭하여 유저에게 친화적인 `400 Bad Request` 에러 세부 사항 반환.

### 프론트엔드 (Vite + AG-Grid Core)
- **그리드 초기화 및 입력기 제어 (`client2/src/main.js`)**:
  - `loadSchema`를 통해 `currentColumnTypes`를 조회하여 저장.
  - 타입이 `"number"`인 컬럼에 대하여 AG-Grid 기본 수치형 셀 에디터인 `agNumberCellEditor`를 동적으로 바인딩하여 1차 입력 제어.
- **인라인 수정 유효성 검사 및 전송 (`client2/src/main.js`)**:
  - `handleCellEdit`에서 컬럼 타입이 `"number"`인 경우, 수정 값이 올바른 수치형인지 `Number()`를 사용하여 유효성을 검사하고 `isNaN` 판정 시 입력을 기각(Rollback)한 뒤 경고창(Alert)을 표시.
  - 백엔드 에러 반환(400 Bad Request) 시 자세한 서버 검증 실패 메시지를 읽어와 유저에게 alert으로 전달.
- **클립보드 붙여넣기(Smart Paste) 유효성 검사 (`client2/src/main.js`)**:
  - `paste` 이벤트 리스너 내에서 붙여넣은 값들 중 `"number"` 타입인 컬럼의 수신 문자열을 캐스팅하고 유효성을 검사하여 비수치 포함 시 붙여넣기 작업을 완전히 롤백 및 기각 처리.

## 3. 검증 결과
- **스키마 반환 검증**: `/schema` 엔드포인트 호출 시 테이블의 컬럼 타입 스펙이 올바르게 전달됨을 확인.
- **비수치 입력 차단**: 비수치 값 입력 시 프론트엔드(수정 기각, alert 팝업) 및 백엔드(400 Bad Request 예외 가드 작동)에서 정상 차단됨을 검증.
- **JSONB 수치 적재 검증**: 숫자로 구성된 문자열(예: `"250"`)을 전달하였을 때, 문자열 형식이 아닌 실제 `int` 타입으로 PostgreSQL JSONB 필드 내에 바이너리 수치로 변환되어 적재됨을 검증 완료.
