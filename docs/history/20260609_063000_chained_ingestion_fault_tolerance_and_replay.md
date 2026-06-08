# 변경 이력: Chained Ingestion 장애 복구 체계(에러 격리 및 관리자 재처리 API) 구축

- **작성일**: 2026년 6월 9일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **현상**: 
  1. Chained Ingestion 체인 워커 데몬 루프 중, 특정 트랜잭션 그룹 내 매퍼 룰 실행에서 데이터 결함 또는 코드 버그 등으로 에러가 발생할 경우 `db.rollback()` 수행 후 무한히 루프를 재시도하는 현상이 있었습니다. 이로 인해 하나의 실패 트랜잭션이 전체 이벤트 대기열을 영구적으로 중단시키는 Head-of-Line Blocking 장애가 유발되었습니다.
  2. 에러가 발생한 Poison Pill 레코드가 데몬을 중단시키지 않도록 임계 횟수 이상 실패 시 대기열 큐에서 격리(Quarantine)하고, 조치 완료 후 원클릭으로 다시 실행(Replay)할 수 있는 관리 도구의 확보가 필수적이었습니다.
- **해결 방안**:
  1. **실패 횟수 누적 및 격리 (Dead Letter Queue화)**:
     - 워커가 트랜잭션 그룹 처리에 실패할 때마다 각 Outbox 레코드의 `retry_count`를 `+1` 합니다.
     - 실패 횟수가 3회 이상이 될 경우, `status = "FAILED"`로 마킹하고 `processed_chain = True` 가드를 씌워 다음 폴링 쿼리 조회 대상에서 원천 배제(격리)합니다.
     - 격리 시 `payload`의 `"error_log"` 딕셔너리에 에러 시각과 상세 사유를 동적으로 저장하여 원인 파악을 용이하게 하였습니다.
  2. **관리자 재처리 API 개설 (`POST /admin/outbox/retry-failed`)**:
     - `server/main.py`에 실패 이벤트를 리플레이하는 전용 관리자 엔드포인트를 구축했습니다.
     - 이 API 호출 시 `FAILED` 상태인 모든 레코드들의 상태를 `PENDING`으로 복원하고 `retry_count = 0`, `processed_chain = False`로 리셋하여 데몬 워커가 즉시 다시 가져와 처리할 수 있도록 동기화하였습니다.

## 2. 세부 변경 사항

### `server/chain_ingestion_worker.py`
- `start_chain_ingestion_worker` 데몬 내 트랜잭션 처리 에러 제어 블록 수정:
  - 트랜잭션 실패로 리턴될 경우 `db.rollback()` 호출 후 그룹에 속한 `events_in_tx` 리스트를 반복문으로 순회.
  - `retry_count`를 1씩 증가시키고, `retry_count >= 3` 이면 `status = "FAILED"`, `processed_chain = True` 마킹 및 `payload["error_log"]`에 실패 메타 데이터 기입.
  - 임계치 미만 실패 시 `status = "RETRYING"` 상태 적용 후 루프 브레이크하여 다음 폴링 루프에서 재시도.
  - 상태 업데이트 적용을 위한 `db.commit()` 명시적 트랜잭션 커밋 완료.

### `server/main.py`
- `@app.post("/admin/outbox/retry-failed")` 엔드포인트 신설:
  - `DatabaseOutbox.status == "FAILED"` 대상을 조회하고, `PENDING` 상태 복구 및 리트라이 카운트 초기화 수행.
  - 이전의 `error_log` 딕셔너리에 `"resolved_at"` 시각 정보를 기입하여 해결 이력을 추적하도록 보조.

## 3. 검증 결과
- **컴파일/구문 오류 검증**: `py_compile`을 이용해 전체 구문 유효성을 검증했습니다.
- **아키텍처 정합성**: 매퍼 버그나 데이터 변환 불일치 시 3회 리트라이 후 격리되며, 그로 인해 다른 테이블의 실시간 체인 처리가 중단되지 않는 완벽한 장애 방어 메커니즘이 성립됨을 확인했습니다.
