# 기술 이력: 히스토리 내비게이션 점프 시퀀스 최적화 (Timer-less Signal 기반)

## 1. 문제 현상 (Phenomenon)
- 히스토리 로그 더블 클릭 시, 서버에서 행의 위치(Index)를 찾은 후 데이터를 로딩할 때 700ms 고정 타이머(`QTimer.singleShot`)를 사용함.
- 이로 인해 네트워크가 빠를 때도 불필요한 대기 시간이 발생하여 사용자 경험이 "뻑뻑하게" 느껴짐.
- 반대로 네트워크가 매우 느릴 경우 700ms 내에 로딩이 끝나지 않아 점프가 실패할 가능성이 있음.

## 2. 기술적 원인 분석 (Root Cause)
- `ApiLazyTableModel.fetchMore()`는 비동기 작업이나, 작업 완료를 상위 로직에 알릴 수 있는 범용 시그널이 부재했음.
- 로직 흐름 제어를 위해 임시방편으로 고정 타이머를 사용하여 비동기 로딩 대기를 처리하고 있었음.

## 3. 해결 방안 및 코드 변경 (Solution & Code Changes)

### A. 모델 시그널 보강 (`table_model.py`)
- `ApiLazyTableModel`에 `fetch_finished` 시그널을 추가.
- `_on_fetch_finished` (성공) 및 `_on_fetch_error` (실패) 핸들러의 마지막 시점에 해당 시그널을 방출하여 비동기 작업 종료를 보장함.

```python
# client/models/table_model.py
class ApiLazyTableModel(QAbstractTableModel):
    fetch_finished = Signal() # [신규] 모든 종류의 fetchMore 완료 시 알림

    def _on_fetch_finished(self, result):
        # ... 데이터 처리 로직 ...
        self._update_row_id_map(); self._fetching = False
        self.fetch_finished.emit() # [신규] 작업 종료 알림
```

### B. 내비게이터 로직 최적화 (`history_logic.py`)
- `HistoryNavigator`에서 `QTimer.singleShot(700, ...)`을 제거.
- `Qt.ConnectionType.SingleShotConnection`을 사용하여 `fetch_finished` 시그널 수신 시 즉시 점프 시퀀스를 이어가도록 변경.

```python
# client/ui/history_logic.py
def _on_discovery_finished(self, result):
    # ... 오프셋 계산 ...
    source_model._pending_target_skip = skip
    
    # 4. 최종 점프: 타이머 대신 fetch_finished 시그널에 즉시 응답 (SingleShot)
    source_model.fetch_finished.connect(self._step4_final_hop, Qt.ConnectionType.SingleShotConnection)
    source_model.fetchMore()
```

## 4. 아키텍처 영향 보고 (Architecture Impact)
- **응답성 향상**: 데이터 로딩 속도에 맞춰 즉시 UI가 반응하므로, 평균 점프 속도가 획기적으로 개선됨.
- **안정성 확보**: 고정 시간 대기가 아닌 실제 작업 완료 시점에 트리거되므로, 네트워크 지연 환경에서도 데이터 정합성이 보장됨.
- **결합도 분리**: 모델과 내비게이션 로직 간의 시점을 타이머가 아닌 시그널로 동기화하여 더욱 객체지향적인 아키텍처를 달성함.

## 5. 검증 결과 (Validation)
- 로컬 테스트 결과, 검색 및 탭 전환을 포함한 4단계 점프 시퀀스가 시각적으로 끊김 없이 수행됨을 확인.
- `SingleShotConnection` 사용으로 인해 시그널 핸들러가 누적되지 않고 정상적으로 해제됨을 확인함.
