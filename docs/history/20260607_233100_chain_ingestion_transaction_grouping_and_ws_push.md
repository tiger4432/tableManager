# 변경 이력: 체인 인제션 트랜잭션 단위 일괄 처리 및 실시간 이력 타임라인 푸시

- **작성일**: 2026년 6월 7일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **트랜잭션 단위 체인 처리**: 기존 체인 인제션 워커(`chain_ingestion_worker.py`)는 `DatabaseOutbox`에 쌓인 개별 행 변경 이벤트를 루프 내에서 건건이 순차적으로 처리했습니다. 이로 인해 동일한 트랜잭션 내에서 발생한 다수의 변경 사항들이 매번 각각의 개별 트랜잭션으로 커밋되어 데이터베이스 부하가 증가하고, 타겟 테이블에 대한 동시 업데이트 충돌 가능성이 존재했습니다. 이를 해결하고자 동일한 `transaction_id`를 갖는 이벤트를 메모리 상에서 그룹화한 후, 단일 트랜잭션 및 일괄 배치 업데이트(`crud.apply_batch_updates`)로 처리하도록 개선했습니다.
- **실시간 히스토리 타임라인 푸시**: 체인 인제션 워커는 백그라운드 데몬 프로세스로 동작하여 FastAPI 라우터의 HTTP 응답 흐름을 타지 않습니다. 이 때문에 체인으로 인해 파생된 타겟 테이블 업데이트 및 감사 로그(`AuditLog`)가 데이터베이스에는 기록되지만 클라이언트로 실시간 WebSocket 브로드캐스트가 되지 않아 감사 이력 화면이 즉각 갱신되지 못하는 문제가 있었습니다. 이를 해결하기 위해 배치 업데이트 완료 후 WebSocket 매니저를 호출하여 생성된 감사 로그(`created_logs`)와 변경 행 정보를 브로드캐스트하도록 수정했습니다.

## 2. 세부 변경 사항

### 체인 인제션 워커 개선 (`server/chain_ingestion_worker.py`)
- **이벤트 그룹화 및 트랜잭션 처리**:
  - `start_chain_ingestion_worker` 루프 내에서 미처리 아웃박스 이벤트들을 수집한 뒤, `transaction_id` 필드를 기준으로 그룹화(`defaultdict(list)`)합니다. (`transaction_id`가 없는 경우 개별 UUID 기반으로 단일 그룹화)
  - 각 트랜잭션 그룹에 대해 `process_chain_transaction_group` 함수를 호출하여 원자적(Atomic)으로 처리합니다.
  - 실행 실패 시 해당 트랜잭션 그룹 전체를 `db.rollback()`하고 에러를 로깅하여 부분 반영을 차단합니다.
- **배치 업데이트 적용**:
  - 각 이벤트에 설정된 체인 룰을 평가하여 파생되는 업데이트들을 수집한 후, 타겟 테이블별로 모아서 `crud.apply_batch_updates`를 단 한번 호출합니다.
- **실시간 WebSocket 전송 통합**:
  - 순환 참조(Circular Import) 문제를 회피하기 위해 `main` 모듈로부터 `manager`, `inject_system_columns`, `to_local_str`을 함수 내부에서 지연 임포트(Lazy Import)합니다.
  - 배치 업데이트 결과로 반환된 `results`와 생성된 감사 로그(`created_logs`)를 기반으로 `batch_row_upsert` 또는 `batch_refresh_required` 이벤트를 조립해 `await manager.broadcast(json.dumps(msg))`를 실행합니다.

### 데이터 매퍼 및 테스트 정합성 확보
- **매퍼 필드 맵핑 최적화 (`server/mappers/production_mapper.py`)**:
  - 기존의 노후화된 컬럼 맵핑 코드를 현재 데이터베이스 스키마(예: `target_qty`, `model_name`)에 맞추어 수정하였으며, `business_key_val`을 지정하여 일반 배치 업데이트 스키마 규격과 완전히 호환되도록 정리했습니다.
- **통합 테스트 코드 보완 (`server/tests/test_api.py`)**:
  - 체인 워커의 이벤트 처리 로직이 단일 단위에서 트랜잭션 그룹 단위로 개편됨에 따라, `test_chained_ingestion` 내에서 기존의 `process_chain_event` 대신 `process_chain_transaction_group`을 호출하도록 테스트를 수정했습니다.

## 3. 검증 결과
- **테스트 수행 여부**: 사용자의 명시적인 테스트 스킵 요청("테스트 생략")에 따라 자동화 테스트(`pytest`) 대기를 우회하고 변경 사항을 즉시 반영합니다.
