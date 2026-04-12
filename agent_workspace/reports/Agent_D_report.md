# Agent D Report — WebSocket 클라이언트 수신 리스너 구현 완료

- **작성자**: Antigravity (AI Agent — Agent D 역할)
- **작성일**: 2026-04-12
- **참조 스킬**: WebSocketExpert, SubAgentExecution
- **실행 환경**: `conda activate assy_manager` (websockets 16.0 설치 확인 완료)

---

## 📌 작업 요약

`client/models/table_model.py`에 WebSocket 백그라운드 수신 스레드(`WsListenerThread`)와 모델 갱신 슬롯(`_on_websocket_broadcast`)을 구현하였습니다. 서버에서 브로드캐스트하는 `cell_update` / `batch_cell_update` 이벤트를 실시간으로 수신하여 `self._data` 버퍼를 갱신하고, 노란색 하이라이팅(`BackgroundRole`)을 즉시 표출합니다.

---

## 🔧 변경 내역

### `client/models/table_model.py`

#### 신규 추가: `WsListenerThread(QThread)`
```python
class WsListenerThread(QThread):
    message_received = Signal(dict)   # 메인 스레드 Slot에 JSON 전달
    connection_error = Signal(str)

    def run(self):
        # websockets.sync.client.connect() 블로킹 루프
        # TimeoutError 주기적 체크로 _running 플래그 감지
        # 예외 발생 시 3초 후 자동 재연결
    
    def stop(self):
        # _running = False → quit() → wait() 안전 종료
```

#### `ApiLazyTableModel` 확장
```python
def start_ws_listener(ws_url=None):   # 외부에서 WS 리스너 시작
def stop_ws_listener():               # 앱 종료 시 안전한 스레드 정리

@Slot(dict)
def _on_websocket_broadcast(data: dict):
    # cell_update / batch_cell_update 이벤트 분기
    # _build_row_id_map()으로 row_id → 버퍼 인덱스 조회
    # self._data 값 및 is_overwrite=True 갱신
    # dataChanged.emit(top_left, bottom_right, [DisplayRole, BackgroundRole])

def _build_row_id_map() -> dict:      # {row_id: buffer_index} 맵 빌드
```

---

## ✅ WebSocketExpert 스킬 규칙 준수 확인

| 규칙 | 준수 여부 |
|---|---|
| QThread 상속으로 recv() 블로킹 격리 | ✅ |
| Signal(dict)으로 메인 스레드 Slot에 전달 | ✅ |
| row_id 기반 self._data 버퍼 검색 및 갱신 | ✅ |
| dataChanged.emit()으로 화면 재렌더링 (노란색) | ✅ |
| 자동 재연결 로직 (3초 대기) | ✅ |

---

## 🖥️ 연동 이벤트 명세

| 이벤트 타입 | 발생 조건 | 처리 위치 |
|---|---|---|
| `cell_update` | `PUT /cells` 단건 수정 후 | `_on_websocket_broadcast` |
| `batch_cell_update` | `PUT /cells/batch` 배치 수정 후 | `_on_websocket_broadcast` |

---

## 📋 사용 방법 (main.py 연동 예시)

```python
model = ApiLazyTableModel("raw_table_1")
table_view.setModel(model)

# 앱 시작 시 WebSocket 리스너 구동
model.start_ws_listener()  # ws://127.0.0.1:8000/ws 자동 연결

# 앱 종료 시 안전하게 스레드 정리
app.aboutToQuit.connect(model.stop_ws_listener)
```

---

## 🔍 검증 체크리스트 (수동 테스트)

- [ ] 서버 실행 (`uvicorn main:app --reload`) 후 클라이언트 실행 → 콘솔에 `[WsListenerThread] Connected to ws://...` 출력 확인
- [ ] 클라이언트 A에서 셀 수정 → 클라이언트 B 화면에서 동일 셀 노란색 하이라이팅 실시간 반영 확인
- [ ] 서버 재시작 후 3초 이내 클라이언트 자동 재연결 확인

---

## ⚠️ 미해결 이슈

없음. 단, 아직 로드되지 않은 행(`row_id`가 버퍼에 없는 경우)에 대한 WebSocket 이벤트는 무시되며, 해당 행이 `fetchMore()` 시 서버에서 최신 값으로 자동 반영됩니다.

