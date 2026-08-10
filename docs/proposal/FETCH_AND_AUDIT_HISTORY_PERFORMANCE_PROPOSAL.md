# 조회·감사 이력 성능 및 CellSource 쓰기 증폭 축소 제안

> 상태: **제안** (미확정). 제품 스펙이 아니다.  
> 작성: 2026-08-10

## 결론

대량 인제션 뒤 시스템이 느려지는 직접 원인은 단일 `SELECT`가 아니라, 같은 입력이
`cell_sources`의 셀별 source 행, `audit_logs`의 셀별 이벤트, 그 인덱스와 dead tuple을 함께
늘리는 구조다. 조회 개선은 이 쓰기 증폭을 줄이는 작업과 분리하면 효과가 제한적이다.

우선순위는 다음과 같다.

1. `CellSource`를 **행 단위 출처**로 압축하고, 실제 충돌 셀만 기존 셀 단위 레이어로 승격한다.
2. 대량 최초 적재의 셀별 감사 로그를 생략하거나 배치 요약으로 바꾼다. 사람 편집 감사는 유지한다.
3. 행/셀 감사 이력 API를 keyset 페이지 방식으로 바꾸고, 전역 감사 화면은 트랜잭션 요약만 먼저 받는다.
4. 전역 트랜잭션 요약의 대량 변경 감지는 감사 행 전량 역직렬화가 아니라 요약 레코드로 처리한다.

## 확인된 현상

- `cell_sources`는 `(table_name, row_id, column_name, source_name)`마다 한 행이다. 일반 인제션은
  한 행의 모든 컬럼에 같은 source를 쓰므로 셀 수만큼 source 행과 인덱스를 만든다.
- 현재 `audit_logs` 행/셀 history API는 `LIMIT` 없이 모든 과거 이력을 반환한다.
- 전역 `/audit_logs/recent`은 응답 자체는 대표 로그 한 건씩으로 줄이지만, 다른 프로세스가 쓴
  대량 이력을 감지하면 캐시가 새 AuditLog 행을 전부 읽고 Pydantic 역직렬화한다.
- 이 개발 DB의 가벼운 현재 상태에서는 전역 감사 이력 100그룹이 약 147KB / 17ms이고,
  `dt_log` 첫 1,000행은 약 4.2MB / 318ms다. 따라서 지금 수치는 정상 상태의 하한이며,
  대량 적재 직후의 행 수·인덱스 팽창을 대표하지 않는다.
- 프로젝트 보드의 기존 실측: 셀 단위 출처가 1개인 셀이 99.7%이며, 운영 `cell_sources`의
  dead tuple은 50만+가 관찰됐다. 이미 채택된 방향은 “셀당 층 → 행당 출처, 충돌 시 셀 승격”이다.

## 제안 A — 행 출처 기본 + 셀 승격

### 저장 규칙

- 새 `row_sources`(이름은 구현 시 확정)는 `(table_name, row_id, source_name)`별 한 행으로
  기본 provenance를 저장한다.
- 한 행의 모든 쓰기 컬럼이 이 기본 source 하나와 충돌하지 않으면 `cell_sources` 행을 만들지
  않는다.
- 사용자 수정, 다른 parser/chain 값, manual pin처럼 **그 셀만** 행 기본 source와 달라질 때에만
  해당 셀을 `cell_sources`로 승격한다.
- 읽을 때는 `cell_sources`가 있으면 그것이 해당 셀의 진실이고, 없으면 `row_sources`가 진실이다.

### 보존해야 하는 계약

- `user` 값과 manual pin의 우선순위는 절대 약화하지 않는다.
- 철회(replay withdrawal)는 행 source인지 셀 source인지 구분해 같은 최종값 재계산을 수행한다.
- 상세 source API는 기존 응답 모양을 유지하되, 행 기본 source에서 왔다는 표시를 추가한다.
- 기존 `cell_sources`는 일괄 삭제하지 않는다. 읽기 호환 기간을 둔 뒤, 검증된 행만 압축한다.

### 기대 효과와 검증

- 보드 실측 비율대로라면 기본 source 한 건으로 대부분의 셀 source 행을 제거한다.
- 기준은 인제션 시간뿐 아니라 `cell_sources` heap/index 크기, dead tuple, 행당 source 수,
  사용자·chain 충돌 셀의 재계산 결과다.
- 실제 다중 source 행을 포함한 fixture에서 “행 기본 source → 셀 승격 → 철회” 왕복 결과가
  현행 레이어 결과와 동일해야 한다.

## 제안 B — 감사 로그를 ‘이력’과 ‘대량 적재 증빙’으로 분리

- 사람 편집과 source 충돌/승자 변경은 현행 셀 단위 AuditLog를 계속 남긴다.
- 새 행의 최초 적재(`old_value` 없음)는 셀별 감사 이벤트를 만들지 않는다. 파일·트랜잭션 단위
  적재 요약(테이블, 행 수, 컬럼 집합, source, 파일/tx id)은 보존한다.
- 값이 실제로 바뀐 기존 행은 현행처럼 감사한다. 무변경 재적재는 source, 감사, outbox 모두
  만들지 않는 현재 계약을 유지한다.

이 구분은 “누가 값을 교정했는가”를 보존하면서 “CSV가 10만 행을 처음 넣었다”를 10만 개의
셀 이벤트로 복제하지 않는다.

## 제안 C — fetch 경로

### 행/셀 이력

- `/rows/{row_id}/history`, `/cells/{col}/history`에 `limit`과 `(timestamp, id)` cursor를 추가한다.
- 기본값은 제한된 최신 페이지(예: 200)이며, 클라이언트는 ‘더 보기’로 다음 페이지를 요청한다.
- 정렬 안정성을 위해 timestamp 단독이 아니라 `timestamp DESC, id DESC`를 커서로 쓴다.
- 필요한 DB 인덱스는 실제 `EXPLAIN (ANALYZE, BUFFERS)`로 확인한 뒤 다음 후보를 검증한다.
  - `(table_name, row_id, timestamp DESC, id DESC)`
  - `(table_name, row_id, column_name, timestamp DESC, id DESC)`

### 전역 감사 화면

- 초기 화면은 지금처럼 트랜잭션당 대표 로그와 count만 전송한다. 상세 로그는 펼칠 때만 페이지로
  가져온다.
- 현재 캐시는 대량 외부 write가 오면 새 AuditLog를 전부 모델화한다. 이 경로는 큰 tx에서
  요약만 갱신하도록 바꿔야 한다.
- 안정적 최종형은 `audit_transaction_summary` 같은 tx당 1행의 요약 투영이다. 쓰기 tx 안에서
  함께 upsert하고, 전역 화면은 이 표만 읽는다. 이 표가 있으면 100개 최신 트랜잭션을 얻기 위해
  대량 `audit_logs`를 그룹화하거나 캐시를 전량 병합할 필요가 없다.
- 테이블을 당장 추가하지 않는 1차안은 cache의 보관 로그 수를 대표 1건으로 줄이고, 대량 delta는
  cache invalidate 후 요약 SQL로 재구성한다. 다만 장기적으로는 tx 요약 투영보다 비용 예측성이 낮다.

## 실행 순서

1. 운영/QA에서 `cell_sources`, `audit_logs`의 행 수·heap/index·dead tuple·상위 source/테이블을
   측정하고 baseline을 기록한다.
2. B(최초 적재 감사 요약)와 C의 history keyset pagination을 먼저 적용한다. 저장 의미를 바꾸지
   않아 위험이 가장 작고, 즉시 fetch 상한을 만든다.
3. A를 이중 읽기/신규 쓰기부터 도입하고 충돌 fixture와 replay/withdraw 회귀를 통과시킨다.
4. 전역 감사가 대량 tx 뒤에도 병목이면 tx 요약 투영을 도입한다.
5. 각 단계 뒤 `EXPLAIN (ANALYZE, BUFFERS)`, API 응답 byte·p95, DB 크기와 autovacuum 지표를 비교한다.

## 이번에 하지 않는 것

- 감사 이력 전체 삭제 또는 사람 편집 이력 축소
- 인덱스만 추가해 셀별 쓰기 증폭을 덮는 접근
- offset pagination (페이지가 깊어질수록 느려지고 동시 적재에서 중복/누락 위험)
- 대량 write 중에 전역 감사 캐시가 새 행을 전부 Pydantic 모델로 만드는 현 구조의 단순 튜닝

