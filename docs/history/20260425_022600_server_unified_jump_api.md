# 기술 이력: 서버 사이드 Unified Jump API (target_row_id) 도입

## 1. 문제 현상 (Phenomenon)
- 히스토리 내비게이션 시 Discovery API를 통해 인덱스를 찾고 다시 데이터를 요청하는 2-RTT 구조로 인해 지연이 발생함.
- Discovery API 내부의 Window Function(`ROW_NUMBER`)이 대규모 데이터셋에서 성능 저하를 유발함.

## 2. 해결 방안 (Solution)
- 메인 데이터 API(`/tables/{name}/data`)에 `target_row_id` 파라미터를 추가하여 위치 탐색과 데이터 인출을 통합함.
- Window Function 대신 타겟 행 이전의 행 개수를 직접 세는 `COUNT` 기반 고속 인덱스 스캔 로직을 도입함.

## 3. 코드 변경 사항 (Code Changes)

### `server/main.py`
- `get_table_data` 엔드포인트에 `target_row_id` 파라미터 추가.
- 타겟 행의 `Pivot` 값 조회 후, 정렬 조건(`updated_at`, `business_key_val`, `row_id`)에 따른 우선순위 행 `COUNT` 로직 구현.
- 보정된 `skip`을 사용하여 데이터를 페칭하고, 결과에 `calculated_skip` 및 `target_offset`을 포함하여 반환.

```python
# [핵심 로직 스니펫]
if target_row_id:
    target_row = db.query(models.DataRow).filter_by(row_id=target_row_id, table_name=table_name).first()
    if target_row:
        # 고속 COUNT (인덱스 범위 스캔 활용)
        count_query = query.filter(...) 
        actual_target_offset = count_query.count()
        skip = (actual_target_offset // limit) * limit
```

## 4. 아키텍처 영향 보고 (Architecture Impact)
- **1-RTT 지원**: 클라이언트가 한 번의 요청으로 점프 대상 페이지의 데이터를 모두 가져올 수 있게 됨.
- **DB 부하 감소**: Window Function의 전체 정렬 비용을 제거하고 인덱스 지향적 `COUNT`로 전환하여 서버 응답성 개선.

## 5. 검증 결과 (Validation)
- PowerShell `Invoke-RestMethod`를 통해 오프셋 1000 지점의 데이터 점프 테스트 완료.
- `calculated_skip: 1000`, `target_offset: 1000`이 정확히 반환됨을 확인.
