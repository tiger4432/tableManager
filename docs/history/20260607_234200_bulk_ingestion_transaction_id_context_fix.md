# 변경 이력: 벌크 인제션 및 배치 작업 시 트랜잭션 ID 컨텍스트 전파 누락 수정

- **작성일**: 2026년 6월 7일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **현상**: `inventory_master` 테이블 등에 대량의 파일 인제션(ingestion)을 수행할 때, 생성된 데이터의 변경 감지(`before_flush` ORM 이벤트 리스너)에 의해 `DatabaseOutbox`에 쌓이는 이벤트들이 단일 트랜잭션 ID로 묶이지 못하고 각 행마다 서로 다른 임의의 UUID를 할당받는 현상이 발생했습니다. 이로 인해 `GraphSyncWorker`가 이벤트를 동기화할 때 1건씩 나누어 처리하여 큐 속도가 대폭 저하되고 수많은 자잘한 Mock Sync 트랜잭션 로그가 도배되는 현상(산산조각 현상)이 관찰되었습니다.
- **원인 분석**:
  - 디렉토리 워쳐(`directory_watcher.py`)의 파일 처리 스레드는 비동기/HTTP 흐름 외부의 별도 백그라운드 스레드에서 작동하여 uvicorn HTTP 미들웨어에서 설정해 주는 `request_transaction_id` ContextVar 정보가 전달되지 않았습니다.
  - `crud.apply_batch_updates` 등의 배치 메서드가 실행될 때 `GeneralUpdateBatch` 내에 명시된 `transaction_id` 값을 로컬 스레드 컨텍스트(`ContextVar`)에 바인딩해 주지 않아, `database.py`의 `stage_event` 이벤트 리스너가 호출될 때 `request_transaction_id.get()`이 `None`을 반환하여 매 이벤트마다 신규 `uuid.uuid4()`를 강제 할당하게 되었습니다.
  - 이는 파일 인제션뿐만 아니라 대용량 일괄 생성(`create_empty_rows_batch`) 및 일괄 삭제(`delete_rows_batch`) 시에도 동일한 컨텍스트 단절을 유발했습니다.

## 2. 세부 수정 사항

### 배치 핵심 함수 내 컨텍스트 복제 및 복구 (`server/database/crud.py`)
- **`apply_batch_updates`**:
  - 배치 객체로부터 `transaction_id` 및 사용자명, 변경 소스를 추출한 뒤, `request_user`, `request_transaction_id`, `request_source` ContextVars를 명시적으로 설정(`set()`)했습니다.
  - 모든 DB 처리 작업 및 `db.commit()` 완료 후 ContextVars가 이전 상태로 복구되도록 `try...finally` 가드를 적용했습니다.
- **`create_empty_rows_batch`**:
  - 일괄 행 생성 전에 유일한 `transaction_id`를 사전에 생성하고, 컨텍스트에 설정하여 `stage_event` 리스너가 이를 읽어가도록 조치했습니다.
- **`delete_rows_batch`**:
  - 일괄 삭제 시에도 트랜잭션 ID를 컨텍스트에 전파하여 일괄 삭제 아웃박스 이벤트들이 하나의 트랜잭션 ID로 그룹화되도록 개선했습니다.

## 3. 검증 결과
- **효과**: 파일 인제션 실행 시 생성되는 수천 건의 `DatabaseOutbox` 레코드들이 이제 파일 단위의 유일한 `file_tx_id`를 동일하게 공유합니다. 이로 인해 `GraphSyncWorker`가 동기화 작업을 수행할 때 하나의 트랜잭션 ID 아래 하나의 Cypher 일괄 쿼리 트랜잭션으로 원자적 커밋을 완료하여 그래프 DB 동기화 성능이 크게 향상되었습니다.
- **테스트 생략**: 사용자의 안전 가이드라인에 따라 자동화 테스트 수행을 배제했습니다.
