# 기술 이력: 클라이언트 콜백 GC 안정화 및 표준화

## 1. 문제 현상 (Phenomenon)
- 클라이언트 UI 내비게이션 및 데이터 업데이트 중 신호(Signal) 유실 발생.
- `RuntimeError: wrapped C/C++ object has been deleted` 에러가 간헐적으로 발생하여 UI 업데이트가 멈춤.
- 원인 파악 결과, 대다수 콜백이 로컬 클로저(lambda, nested def)로 구현되어 Python GC에 의해 조기 수거됨.

## 2. 기술적 원인 분석 (Root Cause)
- **Nested Functions**: `_on_item_clicked` 내부의 `_deferred_scroll`과 같은 중첩 함수는 부모 함수 종료 시 참조 카운트가 위험해짐. 특히 `QTimer.singleShot`과 결합 시 실행 시점에 함수가 이미 해제된 경우가 발생.
- **Lambda Capturing**: `setData` 내의 `lambda`는 지역 변수(`p_index` 등)를 캡처하는데, 고빈도 호출 시 이전 실행 주기의 캡처본이 오염되거나 유실됨.
- **Missing Context Guard**: 비동기 Worker 호출 시 필요한 상태 정보가 클래스 멤버가 아닌 로컬 변수에만 의존함.

## 3. 해결 방안 및 코드 변경 (Solution & Code Changes)

### A. 중첩 함수 제거 및 클래스 메서드화 (`panel_history.py`)
중첩되어 있던 내비게이션 로직을 시스템 수준의 슬롯으로 분리하고 `self._current_nav_ctx`를 사용하여 상태를 관리함.

```python
# Before
def _on_item_clicked(self, item):
    def _deferred_scroll():
        # ... logic ...
    QTimer.singleShot(100, _deferred_scroll)

# After
def _on_item_clicked(self, item):
    self._current_nav_ctx = { "row_id": ..., ... }
    QTimer.singleShot(100, self._on_navigation_deferred_execute)

@Slot()
def _on_navigation_deferred_execute(self):
    # ctx 복원 후 로직 수행
```

### B. 컨텍스트 매핑 도입 (`table_model.py`)
`id(worker.signals)`를 키로 사용하여 실행 중인 업데이트의 컨텍스트를 `self._pending_update_ctx` 멤버 변수에 추적 관리함.

```python
# After (setData)
ctx = {"index": p_index, "col_name": col_name, "value": value}
self._pending_update_ctx[id(worker.signals)] = ctx
worker.signals.finished.connect(self._on_cell_update_worker_finished)

@Slot(dict)
def _on_cell_update_worker_finished(self, res):
    ctx = self._pending_update_ctx.pop(id(self.sender()), None)
    # 안전하게 ctx 복원 후 처리
```

### C. 동적 버튼 람다 제거 (`dialog_source_manage.py`, `navigation_rail.py`)
`setProperty("data", val)`와 `self.sender()`를 이용한 단일 슬롯 방식으로 전환하여 메모리 효율성 및 안정성 확보.

## 4. 검증 결과 (Validation)
- `audit_callbacks.py` 스크립트를 통한 전수 검사 결과, 고위험 클로저 패턴 제거 확인.
- History Panel 연타 테스트 및 대량 데이터 수정 테스트에서 Signal 유실 현상 재발하지 않음.
- 메모리 누수 여부 확인 결과, `pop()`을 통한 컨텍스트 정리로 정상 동작 확인.
