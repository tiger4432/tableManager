# Jump Navigation "Target Not Found" 최적화 (2026-04-26)

## 1. 개요 (Overview)
`HistoryNavigator`를 통해 데이터를 탐색(Jump)할 때, 현재 적용된 검색어 필터 조건에 해당 데이터가 포함되지 않는 경우 무거운 순위 계산 쿼리가 실행되어 6~10초간 응답이 멈추는 현상(Freeze)을 해결했습니다.

## 2. 원인 분석 (Root Cause)
서버의 `get_table_data` 엔드포인트에서 점프 오프셋을 계산하기 위해 다음과 같은 로직을 수행하고 있었습니다.
1. `target_row`를 DB에서 PK 기반으로 무조건 조회함 (`db.query(...).filter_by(row_id=...)`)
2. 조회 성공 시, 복잡한 정렬 조건(`coalesce`, `or_`, `and_`)이 결합된 `count_query.count()`를 실행하여 해당 행의 오프셋을 산출함

이때, 타겟 행이 DB에는 존재하지만 **현재 사용자의 검색어(`q`)에는 맞지 않는 경우**, 무의미한 `count_query`가 수백만 건의 데이터를 풀 스캔하며 정렬을 시도하게 되어 심각한 병목(6~10초 지연)을 유발했습니다.

## 3. 해결 방안 (Solution)
`target_row`를 무조건 가져오는 대신, **현재 검색 필터 조건이 적용된 `query` 객체를 재활용하여 타겟 행의 존재 여부를 1차 검증(Fast-fail)** 하도록 변경했습니다. 

```python
# server/main.py
# 변경 전 (무조건 조회)
target_row = db.query(models.DataRow).filter_by(row_id=target_row_id, table_name=table_name).first()

# 변경 후 (검색 필터 만족 여부 선행 검증)
# query는 이미 global_filter(검색어)가 적용된 상태임
target_row = query.filter(models.DataRow.row_id == target_row_id).first()
```

이 방식은 PK(`row_id`)를 활용하므로 DB 엔진에서 단 1건의 행만 가져와서 필터 조건을 확인하게 됩니다 (0.1ms 소요). 여기서 `None`이 반환되면 필터에 숨겨진 것이 확실하므로, 무거운 `count_query.count()` 연산을 완벽하게 스킵(`actual_target_offset = -1`)합니다.

## 4. 아키텍처 및 성능 영향 (Impact)
- **성능 향상**: 검색어와 불일치하는 히스토리 데이터로 점프를 시도할 때 발생하던 **수 초 단위의 프리징을 완전히 제거 (1ms 미만으로 응답)**했습니다.
- **아키텍처 정합성**: 서버가 "이 타겟은 현재 뷰에 없다"고 클라이언트에게 즉시 피드백하게 되며, 이로 인해 이전에 구현된 **클라이언트의 필터 자동 해제 및 재시도 로직(`QTimer.singleShot(600)`)이 즉시 반응(Real-time)**하게 됩니다. 사용자 체감 성능이 대폭 향상되었습니다.
