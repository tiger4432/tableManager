# 2026-07-21 06:28:00 - Chain Ingestion Worker Payload 문자열(str) 파싱 방어 조치

## 1. 개요 및 원인 분석
* **문제 상황**: `chain_ingestion_worker` 가동 중 특정 상황(PostgreSQL/SQLite 드라이버 반환 특성, 직접 DB raw SQL 삽입, 또는 문자열로 직렬화된 Outbox 레코드)에서 `DatabaseOutbox.payload` 값이 파이썬 `dict`가 아닌 **JSON 문자열 (`str`)** 타입으로 반환되는 경우가 발생했습니다.
* **취약점 위치**:
  1. `process_chain_transaction_group` 내 `valid_events` 필터링 및 custom mapper 전송 시 `e.payload.get("source_name")` 또는 `e.payload.get(...)`을 직접 호출 -> `'str' object has no attribute 'get'` 예외 발생.
  2. 배치 mapper(`is_batch=True`) 및 단일 mapper 호출 시 `e.payload` raw string이 그대로 커스텀 맵퍼로 넘어감 -> 커스텀 맵퍼 내부 동작 시 파싱 에러 발생.
  3. 에러 로깅/재시도 처리 루틴에서 `dict(event.payload)` 호출 -> `ValueError: dictionary update sequence element #0 has length 1...` 예외 발생.
  4. `graph_sync_worker` 및 `main.py` 실패 이벤트 조회/리셋 엔드포인트에서도 동일하게 문자열 payload에 `.get()`을 호출하는 취약점 존재.

---

## 2. 세부 개선 사항

### A. 유니버설 파싱 유틸리티 `get_payload_dict` 신설 ([`payload_helper.py`](file:///c:/Users/kk980/Developments/assyManager/server/utils/payload_helper.py))
* `dict`, `str`(JSON 규격 문자열), `DatabaseOutbox` 모델 인스턴스, `None` 등 어떤 타입의 객체가 넘어오더라도 **항상 안전하게 파이썬 `dict` 객체로 자동 역직렬화하여 반환**하는 공용 헬퍼 함수를 구현했습니다.

### B. `DatabaseOutbox` 모델 방어 프로퍼티 추가 ([`models.py`](file:///c:/Users/kk980/Developments/assyManager/server/database/models.py))
* `DatabaseOutbox.safe_payload` 프로퍼티를 추가하여 `payload`가 `str`인 경우에도 즉시 딕셔너리로 안전하게 접근할 수 있도록 보장했습니다.

### C. `chain_ingestion_worker.py` 전반적인 무결성 강화 ([`chain_ingestion_worker.py`](file:///c:/Users/kk980/Developments/assyManager/server/chain_ingestion_worker.py))
* `process_chain_transaction_group`에서 `e.payload.get(...)` 대신 `get_payload_dict(e)`를 사용하도록 전면 교체.
* 커스텀 맵퍼 전달 인자를 `get_payload_dict(e)`로 래핑하여 맵퍼 내부로 전달되는 `payload`가 항상 `dict`임을 보장.
* 3회 재시도 실패 후 `FAILED` 상태 변환 시 `dict(event.payload)` 대신 `dict(get_payload_dict(event))`를 사용하도록 수정.

### D. 관련 워커 및 API 엔드포인트 수정을 통한 동시 방어
* `graph_sync_worker.py`의 `build_queries_for_event`에서도 `get_payload_dict(event)`를 적용.
* `main.py`의 실패 이벤트 리셋(`/admin/outbox/reset-failed`) 및 조회(`/admin/outbox/failed`) 엔드포인트에도 적용.

---

## 3. 검증 결과
* **신규 단위 테스트 구축**: `server/tests/test_chain_payload_resilience.py`를 신설하여 `payload`가 `str` 타입인 경우에도 예외 없이 정상 동작함을 검증.
* **Pytest 테스트 실행**: 35개 전체 테스트 스위트 100% 그린 패스.
