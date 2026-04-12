# Agent Excel Report — QTableView 엑셀 인터랙션 기능 전체 완료 보고서

- **작성자**: Antigravity (AI Agent)
- **참조 스킬**: ExcelInteractionExpert, WebSocketExpert
- **최종 업데이트**: 2026-04-12

---

## 📌 작업 요약

| # | 작업 내용 | 상태 |
|---|---|---|
| 1 | ExcelTableView: Ctrl+C/V 키보드 이벤트 처리 | ✅ 완료 |
| 2 | Copy: TSV 포맷 클립보드 복사 | ✅ 완료 |
| 3 | Paste: 클립보드 파싱 → Batch API 단일 전송 | ✅ 완료 |
| 4 | BatchApiUpdateWorker: QRunnable 기반 비동기 전송 | ✅ 완료 |
| 5 | bulkUpdateData: 서버 성공 후 메모리 갱신 + dataChanged 1회 emit | ✅ 완료 |
| 6 | WsListenerThread: WebSocket 실시간 브로드캐스트 수신 | ✅ 완료 (유저 추가) |
| 7 | 수동 편집 셀 색상 시인성 개선 (노랑→앰버) | ✅ 완료 |

---

## 🔧 변경 파일 상세

### `client/main.py`

- `ExcelTableView(QTableView)` 클래스 추가
  - `keyPressEvent` 오버라이드 → `Ctrl+C`, `Ctrl+V` 단축키 처리
  - `copy_selection()`: 선택 영역 정렬 후 TSV 포맷으로 `QGuiApplication.clipboard()`에 저장
  - `paste_selection()`: 클립보드 TSV 파싱 → `model.bulkUpdateData()` 단일 위임
- `QTableView` 인스턴스를 `ExcelTableView`로 교체
- `model.start_ws_listener()` 활성화 + `aboutToQuit` 시 `stop_ws_listener()` 연결

### `client/models/table_model.py`

- `BatchApiUpdateWorker(QRunnable)` 추가
  - 수정된 셀 전체를 JSON Array로 묶어 `PUT /tables/{table_name}/cells/batch` 단 1회 전송
- `ApiLazyTableModel.bulkUpdateData()` 추가
  - 파싱된 2D 배열을 payload로 조립 → Worker 실행
- `ApiLazyTableModel._on_batch_update_finished()` 추가
  - 서버 성공 응답 후 `self._data` 일괄 메모리 갱신
  - bounding box 계산 후 `dataChanged` 1회만 emit (렌더링 최적화)
- `WsListenerThread(QThread)` 추가 (유저 구현)
  - `websockets.sync.client`로 서버 `/ws` 연결, 재연결 자동화
  - `message_received(dict)` 시그널로 JSON 이벤트를 메인 스레드에 전달
- `_on_websocket_broadcast()` Slot 추가
  - `cell_update` / `batch_cell_update` 이벤트 처리
  - `row_id` 맵으로 버퍼 검색 후 값 갱신 + `dataChanged` emit
- 수동 편집 하이라이트 색상 변경: `#ffeb3b` → **`#FF8C00`** (앰버, 시인성 개선)

---

## 🖥️ 서버 연동 엔드포인트

| 방향 | 프로토콜 | 엔드포인트 |
|---|---|---|
| 단일 셀 편집 | PUT | `/tables/{table_name}/cells` |
| 다중 셀 일괄 편집 | PUT | `/tables/{table_name}/cells/batch` |
| 실시간 브로드캐스트 수신 | WebSocket | `/ws` |

---

## 🔍 수동 검증 체크리스트

- [ ] 클라이언트 재시작 후 다중 셀 드래그 선택 → `Ctrl+C` → 메모장에 TSV 형태 확인
- [ ] 외부 엑셀 데이터 복사 → `Ctrl+V` → 서버 콘솔에 Batch API 1회 요청 확인
- [ ] 붙여넣기 후 해당 셀 배경이 앰버(주황)로 표시되는지 확인
- [ ] 다른 클라이언트에서 셀 편집 시 WebSocket 브로드캐스트로 현재 클라이언트에도 즉시 반영되는지 확인
