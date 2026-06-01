# 변경 이력: 파일 인제션 완료 시 전체 새로고침 대신 변경 이력(AuditLog) 푸시(Append) 방식으로 최적화

- **작성일**: 2026년 6월 2일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- 기존에는 `DirectoryWatcher`를 통해 파일 인제션이 완료되면 전체 새로고침 이벤트(`batch_refresh_required`)를 수신하여 UI 그리드 데이터와 우측 타임라인 변경 이력을 전체 다시 불러오도록(F5 리로드와 유사) 구현되어 있었습니다.
- 이로 인해 변경 이력이 새로 인입되었음에도 타임라인의 히스토리가 전체 리로드되어 버리며, 실시간 데이터 변경 감지 화면 최적화에 어긋나는 비효율이 발생했습니다.
- 이를 개선하기 위해 **인제션으로 발생한 실제 AuditLog 목록을 WebSocket을 통해 클라이언트에 스트리밍하고, 클라이언트가 이를 실시간으로 prepend하여 덧붙이는(Push-based Append) 방식**으로 전환합니다.

## 2. 세부 구현 사항

### 백엔드 인제스터 및 웹소켓 (`server/parsers/directory_watcher.py` & `server/main.py`)
- **생성된 감사 로그 취합 (directory_watcher.py)**:
  - `_send_to_upsert` 실행 시 `crud.apply_batch_updates`의 세 번째 반환값(`created_logs`)을 가로채서 대용량 처리 루프 내에서 누적 수집(`all_created_logs`)하도록 구조를 다듬었습니다.
  - 배치 완료 후 호출하는 `on_refresh_callback` 콜백 함수 인자에 취합된 감사 로그 리스트(`all_created_logs`)를 함께 넘겨주도록 개선했습니다.
- **웹소켓 브로드캐스트 스펙 확장 (main.py)**:
  - 파일 인제션 성공 콜백 수신 시 실행되는 `trigger_ws_refresh` 함수를 개선하여 세 번째 인자 `created_logs`를 받아들일 수 있도록 했습니다.
  - 전송할 생성 로그가 100건 이하인 안정권 범위 내일 때에만 브로드캐스트 메시지 페이로드에 `created_logs`를 동봉하도록 설계하여 브라우저의 과부하(Freeze)를 사전 방지했습니다.

### 프론트엔드 (`client2/src/main.js`)
- **인제션 히스토리 푸시 연동**:
  - WebSocket 수신 시 `batch_refresh_required` 핸들러 내부에 `created_logs` 존재 여부 체크 분기 로직을 삽입했습니다.
  - `created_logs` 정보가 제공되면 전체 이력을 다시 불러오는 함수(`triggerHistoryReloadDebounced`)를 생략하고, 넘어온 감사 로그 레코드 목록을 순회하며 `appendHistoryLocally(log)`를 호출하여 타임라인에 실시간으로 즉시 밀어 넣습니다.

## 3. 검증 결과
- 수정된 `directory_watcher.py` 및 `main.py` 파일의 파이썬 문법 컴파일 및 정합성이 이상 없음을 검증했습니다.
- Vite 빌드를 정상적으로 마쳐 최신 프론트엔드 에셋이 정상 적용되었음을 확인했습니다.
