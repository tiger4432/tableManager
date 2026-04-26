# 히스토리 정합성 해결 및 대량 인제션 로그 최적화

## 1. 개요
최신순 정렬 모드에서 시스템 인제션 데이터의 추적 정합성을 확보하고, 대량 인제션(10만 건 이상) 시 히스토리 로그가 파편화되거나 서버 메모리를 과도하게 점유하는 문제를 해결하였습니다.

## 2. 주요 변경 사항

### A. AuditLogCache 글로벌 그룹화 및 성능 최적화 (`server/audit_cache.py`)
기존의 인접 로그 비교 방식(State-machine)을 버리고, **딕셔너리 기반의 글로벌 그룹화**를 도입하여 동일 `transaction_id`를 가진 로그가 시간차를 두고 들어오더라도 하나의 그룹으로 완벽하게 통합되도록 개선하였습니다. 또한, 대량 트랜잭션 시 메모리 보호를 위해 인메모리 캐시에는 **트랜잭션당 최대 500건의 프리뷰만 유지**하고, 전체 개수는 별도로 관리하여 UI에 정확한 수치를 전달합니다.

```python
# server/audit_cache.py 핵심 로직
for log_obj, bk in chunk:
    tid = log_obj.transaction_id or "no_tid"
    if tid not in groups_dict:
        new_group = {"transaction_id": tid, "logs": [], "total_count": 0}
        groups_dict[tid] = new_group
        groups_order.append(new_group)
    
    groups_dict[tid]["total_count"] += 1
    if len(groups_dict[tid]["logs"]) < 500: # 인메모리 캡핑
        groups_dict[tid]["logs"].append(log_model)
```

### B. 전수 추적성(Traceability) 복구 및 트랜잭션 ID 전파 (`server/database/crud.py`)
로그 억제(`skip_log`) 로직을 제거하여 **DB에는 모든 상세 변경 이력이 기록**되도록 복구하였습니다. 이를 통해 사용자가 히스토리 패널에서 "펼쳐보기"를 클릭했을 때, 10만 건의 데이터 중 어떤 행이 어떻게 바뀌었는지 DB 조회를 통해 완벽하게 추적할 수 있습니다.

### C. 정렬 Tie-breaker 및 시간 형식 통일 (`server/main.py`)
`updated_at`이 동일한 경우의 정렬 정합성을 위해 `row_id DESC`를 공통 Tie-breaker로 설정하였습니다. 이는 테이블 메인 뷰, 오프셋 스캐너, 점프 로직 모두에 동일하게 적용되어 "최신순" 모드에서의 데이터 위치 이동 오차를 제거합니다.

```python
# server/main.py 정렬 정합성 수정
if req.order_by == "updated_at":
    sort_expr = models.DataRow.updated_at
    sort_expr = sort_expr.desc() if req.order_desc else sort_expr.asc()
    # 메인 테이블과 동일한 Tie-breaker 방향 적용
    tie_breaker = models.DataRow.row_id.desc() if req.order_desc else models.DataRow.row_id.asc()
    query = query.order_by(sort_expr, tie_breaker)
```

## 3. 아키텍처 영향
- **성능**: 10만 건 이상의 대량 인제션 시에도 서버 메모리 사용량이 일정하게 유지되며, 히스토리 패널 로딩 속도가 대폭 향상되었습니다.
- **정합성**: 사용자 직접 수정과 시스템 자동 인제션이 섞여 발생하는 로그 파편화 현상이 근본적으로 해결되었습니다.
