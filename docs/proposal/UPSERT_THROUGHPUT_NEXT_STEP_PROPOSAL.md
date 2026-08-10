# Upsert 처리량 다음 단계 제안

> 상태: 제안 (미확정)  
> 작성일: 2026-08-10  
> 범위: 대형 파일 인제션의 `apply_batch_updates` 처리량. 제품 스펙이나 운영 설정은 바꾸지 않는다.

## 1. 확인된 기준선

`PROJECT_STATUS.md`에 기록된 P3 결과와 현재 main의 커밋은 다음 상태다.

| 항목 | 확인된 결과 | 상태 |
| --- | --- | --- |
| 집합 기반 identity prefetch | 796초 → 376초, 2.12배; SQL 30.1만 → 1,200 | `4738d84`, main 포함 |
| outbox 경량화 | 행 전체 payload 대신 row 참조, 유니크 업무키와 함께 적용 | `528dfcb`, main 포함 |
| 업무키 동시성 방어 | D3 유니크 인덱스 + `IntegrityError` 후 재조회/재시도 | `crud.apply_batch_updates`에 구현 |

따라서 “행마다 identity SELECT”는 다음 최우선 병목이 아니다. 반면 보드의 P3 항목 일부는 아직 “프로파일링만”으로 적혀 있어, 이 완료된 두 변경과 구분해 정리할 필요가 있다.

## 2. 권장 순서

### A. 먼저: 쓰기 구간 계측

파일·청크마다 다음 시간을 같은 로그 한 줄에 기록한다.

1. 파싱/정규화
2. identity prefetch
3. 행·셀 변경 계산
4. `cell_sources` bulk upsert
5. audit/outbox flush
6. DB commit
7. 체인 후속 쓰기

각 구간은 행 수, 셀 수, 신규/기존 행 수, payload byte 수와 같이 남긴다. 평균만 보지 않고 p50/p95와 10만·100만 행, 신규·기존·혼합 세 입력을 비교한다.

이것이 없는 COPY 전환은 “빠를 것”이라는 추측일 뿐이다. 현재 구조는 CellSource·Audit·Outbox 의미를 함께 보존해야 하므로, 원본 테이블에 직접 COPY하면 속도는 얻어도 정본 행위가 달라질 수 있다.

### B. 다음: 프로세스 병렬화의 안전 게이트

보드의 65% Python 시간 관측을 따른다면, D3가 선 현재는 COPY보다 서로 다른 청크/파일의 프로세스 병렬화가 먼저 검증할 후보다.

시작 조건은 세 가지다.

- `ingestion_checkpoint`가 같은 파일의 이중 claim·병렬 재개를 막는지 실측한다.
- 프로세스 수 × SQLAlchemy pool 합계가 PostgreSQL `max_connections` 이하인지 고정한다.
- 유니크 충돌 재시도 횟수·지연을 계측한다. 충돌이 계속되면 병렬 수를 늘리지 않는다.

초기 시험은 worker 2개, 서로 다른 파일, 격리 DB에서만 한다. 같은 파일 병렬화는 그 다음 단계다.

### C. 그 다음: 튜닝 손잡이

현재 watcher batch size 1,000은 하드코딩이다. `ingestion_settings.json`에 **행 수와 예상 bind 수의 상한을 동시에 지키는** batch-size 설정을 추가하고, A의 결과에서 p95 commit time과 메모리로 기본값을 정한다.

단순히 행 수를 키우면 넓은 CSV가 PostgreSQL bind 한계 또는 큰 rollback 비용을 먼저 만날 수 있다. 따라서 `BULK_CHUNK_SIZE`의 정합성 한계와 인제션 튜닝 값을 분리한다.

### D. 마지막 후보: staging COPY

COPY는 바로 운영 테이블로 쓰지 않는다. 임시 staging table에만 COPY한 뒤, 검증된 키·값을 집합적으로 정규화하고 기존 CellSource/Audit/Outbox 계약으로 합류시킨다.

착수 조건은 A에서 파싱보다 DB insert/flush가 지배적이고, B/C 이후에도 목표 처리량을 못 얻는 경우다. 이 조건 전에는 구현하지 않는다.

## 3. 성공 기준과 중단 기준

| 판정 | 기준 |
| --- | --- |
| 진행 | throughput 상승, 기존 5개 레이어링 시나리오의 값·감사 결과 바이트 동일, duplicate business key 0 |
| 중단/롤백 | p95 commit 급증, unique-race 재시도 급증, checkpoint 이중 claim, pool 포화, Audit/Outbox 의미 변경 |

## 4. 제안 결론

다음 구현은 **A 계측 + B의 2-process 격리 드릴**로 제한한다. PG COPY는 이 결과가 “DB write가 여전히 지배적”이라고 보여 줄 때만 별도 설계로 연다.
