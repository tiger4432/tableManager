# 2026-06-16 Real-time Ingestion Progress UI (Floating Progress Widget)

대량 행 데이터를 파싱 및 데이터베이스에 적재(Ingestion)하는 동안 진행 상태와 성공/실패 여부를 사용자가 실시간으로 한눈에 파악하기 어렵던 불편을 해소하기 위해 실시간 파일 수집 진행 상태 표시 패널을 구현하였습니다.

## 주요 변경 사항

### 1. 백엔드 배치(Batch)별 진행률 계산 및 WebSocket 브로드캐스트 전파
- **`server/parsers/directory_watcher.py`**:
  - `IngestionHandler`와 `WorkspaceWatcher`에 `on_progress_callback` 파라미터를 추가했습니다.
  - `_send_to_upsert` 메서드 내에서 전체 파싱된 행의 수(`total_rows = len(rows)`)를 파악하고, 1000개 단위의 배치 루프를 실행할 때마다 누적 처리된 행 수(`processed_rows`)와 진행률(`progress_pct`)을 계산합니다.
  - 각 배치의 DB bulk upsert 처리가 완료되는 즉시 `self.on_progress_callback`을 안전하게 호출하도록 설계했습니다.
- **`server/run_watcher.py`**:
  - 실시간 수집 진행 콜백을 받아 중계하는 `trigger_ws_progress` 함수를 신설했습니다.
  - 이 함수는 내부 webhook API인 `/internal/events/broadcast`에 HTTP POST 요청을 전송하여, 현재 처리 중인 테이블명, 파일명, 진행률(%), 누적 행 수 및 전체 행 수 정보(`file_ingestion_progress` 이벤트)를 전체 웹소켓 세션으로 브로드캐스팅합니다.
  - 완료 이벤트와의 파일명 정합성을 보장하기 위해 progress 이벤트 전송 시에도 원본 대신 정제된 파일명(`clean_filename`)으로 정규화하여 쏘도록 개선했습니다. 이로써 프론트엔드가 카드를 매칭하여 완료 후 정상 소거(dismiss)할 수 있게 됩니다.
  - `poll_pending_retries` 및 `main` 감시 루프 내의 IngestionHandler/WorkspaceWatcher 생성자 호출 시에 해당 콜백을 올바르게 연동했습니다.

### 2. 프론트엔드 실시간 플로팅 진행 상태 위젯 (Floating Progress Card UI)
- **`client2/src/style.css`**:
  - 화면 좌측 하단(상태 바 바로 윗부분)에 둥실 떠 있는 글래스모피즘 기반 플로팅 패널(`ingestion-progress-container`) 및 진행 카드(`.progress-card`) 스타일을 구축했습니다.
  - 보라/파랑 그라데이션 색상의 세련된 가로 충전형 바(`.progress-bar`) 스타일과 성공(`.status-success`), 실패(`.status-error`) 시의 색상 오버라이드 규칙을 구성했습니다.
- **`client2/src/main.js`**:
  - 웹소켓 수신부(`handleWebSocketMessage`)에 `file_ingestion_progress` 수신 필터를 연동하여 `showIngestionProgress(...)` 헬퍼 함수를 트리거합니다.
  - 동적으로 진행률 카드를 생성하며, 동일 파일에 대해 반복 수신 시 UI 내의 % 텍스트, 진행 바 너비 및 stats 정보를 고속 업데이트합니다.
  - `file_ingestion_completed` 수신 시에는 `finishIngestionProgress(...)` 헬퍼를 통해 진행률을 100%로 갱신하며 연두색(성공) 또는 빨간색(실패) 상태로 카드를 전환한 뒤, 2.5초 후 부드러운 페이드아웃 애니메이션과 함께 카드가 사라지도록 제어했습니다.

## 빌드 및 검증
- `client2` 디렉토리 내에서 `npm run build`를 구동하여 Vite 프로덕션 빌드가 에러 없이 깔끔하게 완료됨을 확인하였습니다.
