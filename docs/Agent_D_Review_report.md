# 📝 Agent D — 소스 코드 리뷰 요약 (WebSocket)

**담당 영역**: 실시간 데이터 동기화 리스너 및 브로드캐스트 처리
**주요 파일**: `client/models/table_model.py`, `server/main.py`

---

## 1. 클래스 구조 및 핵심 역할
### `WsListenerThread (QThread)`
- **역할**: 서버와 WebSocket을 항시 유지하며 브로드캐스트되는 JSON 데이터를 수신.
- **핵심 설계**: 
  - `websockets.sync.client`를 사용하여 동기식 `recv()`를 호출하되, `QThread`로 격리하여 UI 블로킹 방지.
  - `timeout` 설정을 통해 루프마다 중지 플래그(`_running`)를 체크합니다.
  - 연결 실패 시 3초마다 자동 재연결(Reconnect) 로직 내장.

### `ApiLazyTableModel` (WebSocket 관련 메서드)
- **`_on_websocket_broadcast`**: 수신된 JSON을 파싱하여 로컬 캐시(`self._data`)를 갱신하고 `dataChanged` 시그널 방출.
- **`ws_data_changed` Signal**: 수신된 원격 수정 이벤트를 히스토리 패널 등 다른 UI 컴포넌트로 전파하는 인터페이스.

---

## 2. 데이터 I/O 형식 (WS Payload)
### 서버 브로드캐스트 형식
```json
{
  "event": "cell_update" | "batch_cell_update",
  "table_name": "string",
  "row_id": "string",
  "column_name": "string",
  "value": "any",
  "is_overwrite": true,
  "updated_by": "user"
}
```

---

## 3. 유지보수 포인트
- **데이터 일관성**: 서버 응답을 우선순위로 하여 로컬 데이터를 덮어씁니다.
- **최적화**: `_build_row_id_map()`을 통해 `row_id`로 메모리 상의 인덱스를 즉시 찾아 업데이트하므로, 대용량 데이터에서도 O(1) 수준의 성능을 보장합니다.
