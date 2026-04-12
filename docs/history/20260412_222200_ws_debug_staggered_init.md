# 프로젝트 이력: WebSocket 통신 결함 진단 및 에이전트 협업 (2026-04-12)

## 1. 개요
WebSocket 연결 성공(`SUCCESS`) 로그가 확인됨에도 불구하고, 실시간 데이터(히스토리 로그)가 화면에 반영되지 않는 현상이 발생함. 원인 규명을 위해 서버/클라이언트 전 구간에 디버그 로그를 삽입하고 전문 하위 에이전트에게 태스크를 배분함.

## 2. 진단 및 조치 내역

### 2.1 서버 측 (Agent C 태스크)
- **조치**: `ConnectionManager.broadcast` 메서드에 현재 활성 연결 수(`active_connections`)와 실제 전송 패킷 내용을 출력하는 로그 삽입.
- **검증 포인트**: `PUT /upsert` 시 방송 로직이 실제로 실행되는지, 그리고 클라이언트에게 패킷이 전달되는지 확인.

### 2.2 클라이언트 측 (Agent D 태스크)
- **조치**: `MainWindow._dispatch_ws_message`에 수신 패킷 내용 및 모델 분배 수(`_active_models`) 출력 로그 삽입.
- **검증 포인트**: 패킷이 디스패처까지 도달하는지, 그리고 모델 내부의 `ws_data_changed` 시그널이 히스토리 패널로 정상 전달되는지 확인.

### 2.3 에이전트 협업 체계 가동
- `agent_workspace/tasks/`에 다음 지시서 생성:
  - `Agent_C_debug_ws_task.md`: 백엔드 브로드캐스트 엔진 전수 조사.
  - `Agent_D_debug_ws_task.md`: 프론트엔드 시그널 바인딩 및 패킷 처리 전수 조사.

## 3. 관련 파일 변경 사항
- `server/main.py`: `broadcast` 로직 내 상세 로깅 및 예외 처리 추가.
- `client/main.py`: `_dispatch_ws_message` 내 패킷 트래킹 로그 추가.

## 4. 기대 결과
- 서버 터미널 로그를 통해 "방송 대상 클라이언트 수"가 0 이상인지 확인.
- 클라이언트 터미널 로그를 통해 "[MainWS] Dispatching..." 메시지가 출력되는지 확인.
- 위 두 데이터의 대조를 통해 패킷 유실 지점(네트워크 vs 서버 로직 vs 클라이언트 로직)을 즉시 특정.

---
**기록자: Antigravity (PM)**
