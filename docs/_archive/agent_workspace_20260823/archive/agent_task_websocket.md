# 하위 에이전트 작업 지시서: 실시간 WebSocket 수신 클라이언트 구현

**역할**: UI 상호작용 및 통신(소켓) 전담 에이전트
**대상 파일**: `client/models/table_model.py`, `client/main.py`
**목표**: 서버 측 데이터가 변경되었을 때 쏘는 WebSocket 이벤트를 수신하여, 타 클라이언트 위젯 창의 셀을 즉각 노란색으로 점등(업데이트)시키는 실시간 동기화 기능을 구현하라.

---

## 📋 핵심 구현 플랜 및 요구사항

### 1. 웹소켓 수신 전용 QThread 또는 QRunnable 작성
- **요구사항**: `websockets` 라이브러리의 `asyncio` 루프를 구동하거나, PySide6 내장 모듈인 `QtWebSockets.QWebSocket`을 사용하여 서버(`ws://127.0.0.1:8000/ws`)에 커넥션하라.
- **주의사항**: 소켓을 Listen 상태로 둘 때 데스크톱 UI가 멈추지 않아야 하므로, 반드시 메인 스레드와 격리된 **백그라운드 스레드(QThread)**에서 작동하게 설계하고 수신된 JSON 텍스트를 Qt의 `Signal` 객체 형태로 메인 스레드에 넘겨라. (Cross-thread GUI 업데이트 크래시 방지)

### 2. 서버 JSON 페이로드 처리
- 서버가 일괄 업데이트 완료 후 넘겨주는 브로드캐스트 전문은 다음과 같은 형식이다.
  ```json
  {
    "event": "batch_cell_update",
    "table_name": "raw_table_1",
    "updates": [
      {"row_id": "uuid-1", "column_name": "status", "value": "MANUAL_FIX", "is_overwrite": true}
    ]
  }
  ```
- 이 텍스트를 받아 Python 딕셔너리로 파싱(json.loads)한 뒤 `Signal`로 방출하라.

### 3. ApiLazyTableModel 렌더 갱신
- `table_model.py` 내의 모델 클래스가 위 Signal을 연결(connect)받도록 슬롯(Slot) 함수를 작성하라.
- 도착한 `updates` 리스트를 돌면서, 모델이 현재 보관 중인 메모리(`self._data`) 배열 중 매칭되는 `row_id`를 찾아 값을 수정해라.
- 변경된 셀들의 `QModelIndex`를 계산하고 `dataChanged.emit(...)`을 호출하여 뷰에 반영하라. (이때 `DisplayRole`과 `BackgroundRole`을 명시하여 화면 렌더링을 갱신시킬 것)
