# 2026-06-16 Server CRUD Refactoring & Batch Query Optimization

데이터베이스 I/O 부하를 차단하고 백엔드 아키텍처의 가독성과 SRP(단일 책임 원칙) 준수도를 높이기 위해 서버 CRUD 핵심 모듈(`server/database/crud.py`)을 전면 리팩토링 및 가속 튜닝 완료했습니다.

## 주요 변경 사항

### 1. PIN(우선순위 지정) 및 소스 삭제 배치 API의 N+1 SELECT 병목 전면 차단
- **대상 함수**: `delete_cell_source_batch`, `set_cell_manual_priority_batch`
- **구현 방식**:
  - 기존에는 배치 셀 루프 내에서 개별적으로 DB SELECT 쿼리를 실행하여 N+1 쿼리 지연이 발생하던 현상을 완전히 해소했습니다.
  - 배치로 유입되는 모든 대상 `row_id`들을 선제 추출하여 단 1회의 IN 조건절 쿼리로 `CellSource` 및 `CellOverwrite` 데이터를 사전 벌크 로드했습니다.
  - 이를 `sources_cache` 및 `overwrites_cache` 인메모리 딕셔너리로 조립하여 루프 내의 모든 SELECT 호출을 0ms 레이턴시 메모리 탐색으로 전환했습니다.
  - 루프 내부의 개별 데이터 변경 요청은 캐시 스케줄링 맵에 취합한 후, 루프 완료 시점에 `bulk_upsert_cell_overwrites` 및 `bulk_delete_cell_overwrites`를 호출하여 **단 1회의 SQL 실행**으로 DB 반영을 마쳤습니다. 이로써 두 API의 DB 통신 복잡도를 $O(N)$에서 $O(1)$로 가속했습니다.

### 2. 소스 우선순위 정책의 동적 구성 유연화
- 기존 파이썬 코드에 박혀 있던 우선순위 상수를 `table_config.json` 설정에 맞물려 오버라이드되도록 보완했습니다.
- `compute_priority_value`에 `table_name`을 연계하여 특정 테이블용 `"source_priority"`가 선언되어 있다면 이를 사용하고, 정의되지 않았다면 전역 기본 우선순위(`SOURCE_PRIORITY`)를 안전하게 폴백하도록 처리하여 유저 피드백("정의 안하면 기본값")을 충실히 반영했습니다.

### 3. ContextVar 트랜잭션 생명주기용 `@contextmanager` 추상화
- `request_user`, `request_transaction_id`, `request_source` 변수들을 CRUD 진입점들마다 수동으로 set/reset 하느라 보일러플레이트 코드가 반복 작성되던 구조를 개선했습니다.
- `transaction_context` 컨텍스트 매니저 헬퍼를 신설하여 `with transaction_context(...)` 선언적 블록 단위로 ContextVar 스코프가 자동 소멸 및 롤백되도록 안전 추상화했습니다.

### 4. 거대 핵심 업데이트 함수의 SRP(단일 책임 원칙) 분리
- 270라인 규모의 `apply_row_update_internal` 함수를 논리적 책임별로 하위 보조 함수인 `_get_or_create_row`, `_update_row_business_key`, `_load_metadata_row_cell`로 쪼개어 위임 처리함으로써 모듈 가독성을 극대화하고 향후 단위 검증(UnitTest) 작성이 원활하도록 격리했습니다.

## 빌드 및 검증
- 가상환경(`assy_manager`) 환경에서 `pytest server/tests -v` 테스트 스위트를 구동하여 동적 스키마 핫스와핑, 벌크 최적화, 감사 로그 중복 차단을 포함한 **총 13개 전체 테스트 케이스가 100% 정상 통과(100% Passed)**함을 완전 입증했습니다.
