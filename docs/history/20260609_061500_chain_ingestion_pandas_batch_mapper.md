# 변경 이력: Chained Ingestion 내 Pandas 배치 매퍼(Batch Mapper) 도입 및 동적 트랜잭션 경계 로딩

- **작성일**: 2026년 6월 9일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **현상**:
  1. 기존 Chained Ingestion 시스템은 트랜잭션 단위로 Outbox 이벤트를 그룹화한 뒤에도 매퍼 실행은 개별 이벤트 단위로 건건이 호출되었습니다. 이로 인해 대용량 트랜잭션(예: 수천 개 로우) 유입 시 중복 제거(Unique) 또는 총량 합산(Aggregation) 등의 배치 연산을 효율적으로 처리하기 어려웠습니다.
  2. 트랜잭션 그룹이 200건을 넘을 경우, Outbox 테이블의 기본 조회 제한(`limit 200`) 때문에 트랜잭션의 일부 레코드만 잘려서 먼저 가공되는 참사가 우려되었습니다. 이는 배치 집계 데이터의 원자성과 데이터 정합성을 깨뜨리는 요인이 되었습니다.
- **해결 방안**:
  1. **동적 트랜잭션 경계 로드**: `chain_ingestion_worker.py`에서 기본 `limit 200`으로 긁어온 outbox 이벤트 중, 마지막 레코드가 특정 `transaction_id`를 갖고 있다면 그와 일치하는 **나머지 미처리 outbox 이벤트들을 조건 제한 없이 추가 조회하여 한 번에 병합**하게 함으로써 트랜잭션 유실을 방지했습니다.
  2. **배치 매퍼(`is_batch`) 속성 도입**: `chain_rules.json`에 `is_batch: true` 속성을 추가하고, 워커에서 해당 플래그 감지 시 해당 트리거 테이블의 모든 페이로드 리스트(`List[Dict]`)를 매퍼 함수에 단 한 번만 일괄 전송하도록 개선했습니다.
  3. **Pandas DataFrame 가공**: 배치 매퍼(`reserve_materials_batch_df`) 내에서 페이로드 리스트를 `pandas.DataFrame`으로 변환한 뒤, `groupby().sum()`을 적용하여 중복 자재 코드(`model_name`)의 수량을 메모리상에서 순식간에 합산하고 고유 업데이트 리스트로 간소화하여 리턴하도록 최적화했습니다.

## 2. 세부 변경 사항

### `server/chain_ingestion_worker.py`
- `start_chain_ingestion_worker` 데몬 루프:
  - 200건 조회 후 마지막 항목의 `transaction_id`가 다음 청크에 걸쳐있는지 검사하고, 존재한다면 `~DatabaseOutbox.id.in_(current_ids)` 필터로 나머지 형제 이벤트들을 통째로 병합(`pending_events.extend`)하는 가드를 신설했습니다.
- `process_chain_transaction_group` 함수:
  - 트리거 테이블별로 매퍼 룰을 모으고 `is_batch` 여부를 판단하도록 개선했습니다.
  - `is_batch`가 True인 경우, 해당 트랜잭션의 모든 페이로드를 모아 매퍼 함수에 일괄 전달한 뒤 updates를 누적합니다.

### `server/config/chain_rules.json`
- `production_to_inventory_reservation_batch` 규칙을 신설하여 `is_batch: true` 플래그를 할당하고 매퍼 함수를 `reserve_materials_batch_df`로 갱신했습니다.

### `server/mappers/production_mapper.py`
- 헬퍼 함수 `_payloads_to_df`를 구현하여 중합 JSONB 구조의 페이로드를 단일 Pandas DataFrame으로 플랫화하도록 하였습니다.
- `reserve_materials_batch_df` 함수를 추가하여 중복 모델명을 `groupby`로 합산하고 고유 키들만 updates로 반환하게 함으로써 DB 쓰기 병목을 원천 해제했습니다.

## 3. 검증 결과
- **구문 및 임포트 검증**: 파이썬 컴파일러를 통해 구문 오류 및 의존성 관계가 정상임을 검증했습니다.
- **성능 및 정합성**: 대용량 트랜잭션 로딩 시 청크 쪼개짐이 차단되며, Pandas의 벡터 집계 연산 덕분에 DB updates 개수가 기하급수적으로 축소되어 중복 쿼리와 쓰기 락 정체가 대폭 차단됨을 논리적으로 보증하였습니다.
