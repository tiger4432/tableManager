# 변경 이력: 데이터 업데이트 성공 시 서버 생성 감사 로그(AuditLog) 반환 및 클라이언트 개별 Push 최적화

- **작성일**: 2026년 6월 1일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- 셀 편집 또는 일괄 비우기 수행 시, 클라이언트 사이드에서 임의로 이력 데이터를 모사(Mocking)하여 렌더링하는 기존 로컬 추가 방식은 데이터베이스 원본과 정합성이 완벽히 일치하지 않고, `id`, `transaction_id`, 정확한 `timestamp` 메타데이터가 누락되는 등의 한계가 존재했습니다.
- 이를 근본적으로 해결하기 위해 **서버가 데이터 업데이트 API의 성공 응답 시점에 실제로 DB 트랜잭션 과정에서 발생한 AuditLog 레코드 자체를 반환하도록 API 스펙을 확장**합니다.
- 클라이언트는 API 응답값에 동봉된 실제 AuditLog 레코드들을 그대로 받아 타임라인에 직접 push(prepend)해 줌으로써 데이터 정합성을 100% 보장하고, transaction_id를 통한 트랜잭션 필터링 등 오리지널 이력 카드 UI의 핵심 기능을 온전히 그대로 활용할 수 있게 최적화합니다.

## 2. 세부 구현 사항

### 백엔드 (`server/database/crud.py` & `server/main.py`)
- **트랜잭션 내 생성 로그 가로채기 (crud.py)**:
  - `apply_batch_updates` 실행 도중 `db.commit()`이 수행되기 직전, SQLAlchemy 세션에 신규 추가된 객체들 중 `models.AuditLog` 객체만 `db.new` 조회를 통해 감지하여 수집(`created_log_objs`)하도록 구현했습니다.
  - 커밋이 성공적으로 완료되어 데이터베이스가 할당한 시퀀스 고유 `id`가 채워지면, 해당 레코드 목록을 순회하여 안전하게 직렬화 딕셔너리 리스트(`serialized_logs`)로 변환 후 리턴합니다.
- **FastAPI 응답 구조 확장 (main.py)**:
  - `/tables/{table_name}/data/updates` (PUT) 엔드포인트의 리턴 튜플을 `results, changed_cells, created_logs`로 확장하고, 최종 JSON 바디에 `created_logs` 키로 감사 로그 원본 리스트를 동봉하여 클라이언트에 뿜어주도록 리팩토링했습니다.

### 프론트엔드 (`client2/src/main.js`)
- **개별 로그 수집 및 DOM prepend 처리**:
  - `appendHistoryLocally(log)` 함수가 개별 인자가 아닌 DB 감사 로그 원본 객체(`log`)를 단독으로 수신하도록 개선했습니다.
  - 이로 인해 UI 타임라인에 삽입되는 개별 카드에 실제 `transaction_id` 및 트랜잭션 돋보기 버튼(`filter-tx-btn`) 마크업이 완벽히 포함되어 렌더링되도록 동기화했습니다.
- **클라이언트 비지니스 로직 단순화**:
  - **단일 셀 수정 (`handleCellEdit`)**: API 호출 성공 시 `result.created_logs` 목록이 존재하면 이를 루프 돌며 `appendHistoryLocally`에 그대로 밀어 넣어 갱신합니다.
  - **다중 셀 비우기 (`clearSelectedCells`)**: 클라이언트 측에서 이전 값들을 백업해두던 비효율적인 임시 변수 로직(`oldValuesBackup`)을 완전히 걷어냈습니다. 오직 서버가 돌려주는 `result.created_logs`에만 의존하여 이력을 덧붙이도록 코드를 간결하게 정돈했습니다.

## 3. 검증 결과
- **정합성 및 기능 연동**: 셀을 수정하거나 `Delete` 키로 영역을 지웠을 때, 로딩 딜레이 없이 우측 타임라인에 새로운 카드가 정식 규격으로 붙는 것을 확인했습니다.
- **트랜잭션 필터링 정상 작동**: 로컬로 실시간 덧붙여진 변경 이력 카드 우측 하단의 `Tx: [ID]` 옆 `🔍` 버튼을 클릭했을 때, 해당 트랜잭션으로 수정된 행들만 정상적으로 필터링되어 테이블에 조회됨을 검증 완료했습니다.
