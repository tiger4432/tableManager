# 2026-06-16 BATCH_UPSERT Algorithm Optimization

본 문서에서는 assyManager 적재 엔진의 핵심 연산인 `BATCH_UPSERT` 알고리즘의 성능 병목 및 동시성 취약점을 보완한 설계와 구현 내역을 기록합니다.

## 1. ORM 객체화 배제를 통한 메모리/CPU 최적화
* **기존 문제**: 배치 캐시 생성 시 DB에서 `CellSource` 및 `CellOverwrite` 목록을 조회하여 ORM 객체로 인스턴스화하고, 세션 오염을 막기 위해 `db.expunge(src)` 및 `db.expunge(ow)`를 호출하여 세션에서 분리시켰습니다. 이 루프 연산은 CPU 연산과 메모리 힙 할당량을 불필요하게 가중시켰습니다.
* **보완 내역**: 캐시 쿼리 구문을 `.with_entities` 기반의 스칼라 컬럼 조회 쿼리로 리팩토링하고, 가볍게 속성을 바인딩할 수 있는 `LightCellSource` 및 `LightCellOverwrite` 전용 클래스를 선언하여 대량의 메타데이터를 O(1) 수준의 경량 딕셔너리로 pre-fetch하도록 구조를 전면 개편했습니다. 결과적으로 `db.expunge` 호출이 완전히 배제되어 성능이 향상되었습니다.

## 2. 조기 중복 제거 (Early Deduplication) 도입
* **기존 문제**: 루프를 돌며 모든 변경사항 딕셔너리를 무조건 리스트에 append한 뒤, 최종 쓰기 단계(`bulk_upsert_cell_sources`)에서 해시 맵 데둡을 수행하여 트랜잭션이 큰 경우 임시 딕셔너리가 힙 메모리를 대량 점유하는 현상이 있었습니다.
* **보완 내역**: `apply_row_update_internal` 및 `apply_batch_updates`에서 데이터 수집 컨테이너를 `dict` 형태로 변경하고, 루프 내부에서 고유 제약조건 키를 활용해 최종 매핑 정보만 단 1개 덮어쓰기 방식으로 유지하는 조기 중복 제거 로직을 이식했습니다.

## 3. 데드락 방지 정렬 (Deterministic Sorting) 도입
* **기존 문제**: 벌크 적재(Insert on Conflict Do Update) 쿼리 전송 시 데이터가 무작위 순서로 삽입되어, 병렬 적재 데몬들이 동일 행들에 대해 락을 취득할 때 락 획득 교차 경합이 유발되어 데드락(`deadlock detected` 에러)이 발생할 수 있는 잠재 취약점이 존재했습니다.
* **보완 내역**: `bulk_upsert_cell_sources` 및 `bulk_upsert_cell_overwrites` 실행 직전에 업서트할 딕셔너리 리스트를 고유 제약조건 키(`(table_name, row_id, column_name, source_name)`) 기준으로 **물리적 정렬(Deterministic Sort)**한 뒤 DB에 전송하도록 수정하여 데드락 가능성을 완벽히 차단했습니다.

## 4. 검증 결과
* 13개의 통합 테스트 케이스가 예외 없이 100% 정상 작동(Passed)함을 확인하였습니다.
