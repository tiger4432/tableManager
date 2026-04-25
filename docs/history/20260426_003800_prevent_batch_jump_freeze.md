# 배치 작업 로그 탐색 시 프리징 방어 로직 추가 (2026-04-26)

## 1. 개요 (Overview)
`HistoryNavigator`를 통해 히스토리 로그를 탐색할 때, 사용자가 개별 데이터가 아닌 "배치 작업(_BATCH_)" 로그를 클릭할 경우 네비게이션 락(`_is_navigating`)이 걸린 채로 10초 타임아웃까지 풀리지 않는 현상을 해결했습니다.

## 2. 문제 원인 (Root Cause)
대량 삭제 등 배치 작업이 발생하면 히스토리 패널에는 `row_id`가 `_BATCH_`로 기록된 요약 로그가 표시됩니다. 
이 로그를 사용자가 클릭했을 때, 클라이언트는 `_BATCH_`라는 문자열을 실제 `row_id`로 착각하고 서버에 점프(`jump_to_id`)를 요청합니다. 
서버는 당연히 해당 ID를 찾지 못하므로 앞서 적용한 패스트페일(Fast-fail) 최적화에 의해 즉시 빈 응답을 반환합니다. 하지만 이 특수한 `_BATCH_` 케이스의 경우, 클라이언트의 페치 컨텍스트 상태가 복잡하게 꼬이거나 의미 없는 재시도 큐에 들어가면서 네비게이션 락을 풀지 못한 채 10초 타임아웃을 맞이하게 되었습니다.

애초에 배치 작업은 수십~수백 개의 행이 한꺼번에 처리된 결과이므로 "특정 위치로 이동(Jump)"하는 것 자체가 논리적으로 불가능합니다.

## 3. 해결 방안 (Solution)
`HistoryNavigator.navigate_to_log` 메서드 최상단에 얼리 리턴(Early Return) 방어 로직을 추가하여, 배치 로그 클릭 시 상태 머신(락)이 아예 동작하지 않도록 원천 차단했습니다.

```python
# client/ui/history_logic.py
def navigate_to_log(self, data: HistoryItemData, parent_widget):
    if self._is_navigating or data.is_summary: return
    
    # [Task] 배치 작업(_BATCH_)은 개별 탐색이 불가능하므로 즉시 차단
    if data.row_id == "_BATCH_":
        self.statusRequested.emit("⚠️ 배치 작업 이력은 개별 이동을 지원하지 않습니다.", 3000)
        return
        
    self._is_navigating = True
    # ... 정상 점프 로직 수행 ...
```

## 4. 검증 및 효과 (Validation)
- 배치 작업(예: 여러 행 삭제)으로 생성된 로그를 클릭했을 때, 하단 상태바에 즉시 "⚠️ 배치 작업 이력은 개별 이동을 지원하지 않습니다." 라는 경고 문구가 표시됩니다.
- 네비게이션 락을 점유하지 않으므로 즉시 다른 로그를 클릭하여 정상적으로 이동할 수 있습니다.
- 무의미한 네트워크 요청과 락 교착(Deadlock) 가능성을 완벽히 차단했습니다.
