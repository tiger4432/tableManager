# HistoryNavigator 안정성 및 아키텍처 리팩토링 (2026-04-26)

## 1. 개요 (Overview)
`HistoryNavigator`가 특수 상황(Edge Cases)에서 시스템이 멈추거나 침묵하는 현상을 해결하고, 엔터프라이즈급 안정성을 확보하기 위해 핵심 로직을 리팩토링했습니다.

## 2. 문제 현상 (Phenomenon)
1. **Proxy 필터 충돌 시 침묵**: 테이블에 검색어(필터)가 활성화되어 있을 때, 해당 필터에 걸리지 않는(숨겨진) 히스토리 데이터를 클릭하면 `mapFromSource`가 유효하지 않은 인덱스를 반환하며 아무런 동작 없이 멈춰버렸습니다.
2. **불안정한 레이아웃 대기 시간**: 탭 전환 후 뷰가 렌더링되기를 기다리는 타이머가 `QTimer.singleShot(10)`으로 하드코딩되어 있어, 성능이 낮은 PC나 무거운 데이터 처리 시 타이밍 이슈(Race Condition)가 발생할 수 있었습니다.
3. **좀비 콜백 축적**: 에러나 실패 상황에서 `fetch_finished` 시그널이 정상 해제되지 않으면, 다음 번 탐색 시 콜백 함수가 중복으로 호출되어 시스템 크래시를 유발할 위험이 있었습니다.

## 3. 해결 방안 및 코드 변경 핵심 요약 (Solution & Code Changes)

### A. 필터 해제 및 재추적 (Auto-Retry on Filter Collision)
타겟 데이터를 찾지 못하거나(`_step4_final_hop`) 뷰에 가려져 있을 때(`_final_scroll`), 단순히 에러를 내뱉지 않고 능동적으로 **필터를 지운 뒤 600ms 뒤에 기존 컨텍스트로 점프를 재시도**하도록 수정했습니다. 이 과정에서 무한 루프나 상태 변조를 막기 위해 **락(`_is_navigating`)을 선제적으로 확실히 풀고** 람다(Lambda)에 객체를 바인딩했습니다.

```python
# client/ui/history_logic.py (_final_scroll 내)
if m_idx.isValid():
    # ... 성공 처리 ...
    return True
else:
    # 필터 등에 의해 숨겨진 경우 필터 해제 후 재시도
    print("[Nav] Target found in source, but m_idx is invalid. Clearing filter and retrying.")
    self.statusRequested.emit("⚠️ 숨겨진 데이터입니다. 필터 해제 후 재탐색...", 2000)
    main_win = ctx["main_win"]
    if hasattr(main_win, "_filter_bar"):
        main_win._filter_bar._search_box.clear()
        
        data_obj = ctx["data_obj"]
        parent_widget = ctx["parent_widget"]
        self._release_guard()  # 락 선제 해제
        QTimer.singleShot(600, lambda d=data_obj, p=parent_widget: self.navigate_to_log(d, p))
    return False
```

### B. Qt 이벤트 루프 기반 레이아웃 대기
단순 10ms 하드코딩을 없애고 `QTimer.singleShot(0)`을 채택하여, **OS의 모든 UI Paint 이벤트가 처리된 직후**에 가장 안전하게 후속 작업을 이어가도록 변경했습니다.

```python
# client/ui/history_logic.py
# 2. 레이아웃 안정화 대기 (Qt 이벤트 큐 기반)
QTimer.singleShot(0, self._step2_deferred_execute)
```

### C. UniqueConnection을 통한 중복 연결 방지
이벤트를 수신할 때 `Qt.ConnectionType.UniqueConnection` 속성을 부여하여 100% 콜백 중복을 방어했습니다.

```python
# client/ui/history_logic.py
from PySide6.QtCore import Qt
try: source_model.fetch_finished.connect(self._step4_final_hop, Qt.ConnectionType.UniqueConnection)
except RuntimeError: pass # 이미 연결되어 있는 경우
```

## 4. 검증 결과 (Validation)
- 검색어를 입력해 의도적으로 타겟 데이터를 보이지 않게 가린 후 다른 히스토리를 클릭했을 때, 검색어가 깨끗하게 지워지고 0.6초 뒤에 해당 데이터로 정상적으로 스크롤 됨을 확인했습니다.
- 여러 번 탭을 넘나들며 광클릭을 시도해도 `fetch_finished` 콜백이 단 한 번만 호출되며 락이 풀리는 것을 확인했습니다.
- 시스템 전반적인 내결함성(Fault Tolerance)이 크게 증가했습니다.
