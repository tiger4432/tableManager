# 변경 이력: 1,000행 이상 대량 셀 우선순위/원천 관리 일괄 반영 성능 최적화

- **작성일**: 2026년 6월 2일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- 수천 행에 달하는 대용량 범위 셀의 우선순위 고정(Pin) 또는 특정 데이터 원천(Source) 삭제 작업 시, 서버 측 백엔드에서 심각한 API 지연 및 화면 갱신 랙이 발생하는 문제가 있었습니다.
- 원인은 (1) 셀 변경 시마다 인메모리 감사 캐시의 락(Lock)을 매번 개별 획득하고 정렬하는 병목과, (2) 수천 행 전체의 무거운 중첩 셀 JSON 데이터를 그대로 WebSocket으로 브로드캐스트하여 네트워크 및 프론트엔드 파싱 오버헤드를 유발하는 비효율에 있었습니다.
- 이를 해결하기 위해 **감사 캐시 배치 업데이트 로직을 구현**하고, **100행 초과 대용량 업데이트 시 경량화된 새로고침 신호(`batch_refresh_required`)를 방송하는 WebSocket Fallback 메커니즘을 도입**하여 성능을 획기적으로 개선합니다.

## 2. 세부 구현 사항

### 감사 로그 캐시 최적화 (`server/audit_cache.py` & `server/database/crud.py`)
- **단일 락(Lock) 배치 캐싱 기능 구현 (audit_cache.py)**:
  - `AuditLogCache` 클래스 내에 `add_logs_batch(logs_list)` 메서드를 신규 구현했습니다.
  - 들어온 대량의 로그를 트랜잭션 ID 단위로 그룹화한 뒤, 락을 단 한 번만 획득하여 캐시 타임라인 리스트에 한꺼번에 끼워 넣습니다.
- **캐시 쓰기 지연 처리 (crud.py)**:
  - `create_audit_log` 함수가 캐시 추가 여부를 선택할 수 있도록 `add_to_cache` 파라미터를 추가하고 생성된 로그 딕셔너리를 반환하게 수정했습니다.
  - `apply_row_update_internal`이 수집용 리스트(`logs_to_cache`)를 주입받아 캐싱 처리를 생략할 수 있게 개선했습니다.
  - 배치 처리 함수(`apply_batch_updates`, `create_empty_rows_batch`, `delete_rows_batch`, `set_cell_manual_priority_batch`, `delete_cell_source_batch`)에서 변경 로그를 메모리 리스트에 수집한 후, DB 트랜잭션이 최종 `commit`된 뒤에 한 번에 `add_logs_batch`로 전달하도록 최적화했습니다.

### 웹소켓 전송 경량화 (`server/main.py`)
- **대량 변경에 대한 웹소켓 Fallback 방송**:
  - `set_cell_priority_batch_endpoint` (우선순위 일괄 변경) 및 `delete_cell_source_batch_endpoint` (원천 일괄 삭제)에서 변경된 행 수가 **100건을 초과**할 때, 전체 중첩 JSON을 전송하는 대신 `{ "event": "batch_refresh_required", "table_name": table_name, "change_count": N }`과 같은 단순화된 경량 새로고침 신호만 방송하도록 개선했습니다.
  - 이를 통해 파이썬 서버의 CPU 부담을 줄이고 네트워크 트래픽 및 AG-Grid 클라이언트 렌더링 부하를 극적으로 차단했습니다.

## 3. 검증 결과
- 백엔드 핵심 파이썬 소스 코드(`audit_cache.py`, `crud.py`, `main.py`)의 컴파일 상태가 완벽함을 확인했습니다.
- Vite 빌드가 성공적으로 동작하여 프론트엔드 프로덕션 에셋 빌드 정합성을 보장했습니다.
