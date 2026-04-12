# Real-time Watcher Architect (Agent D) Report

## 1. 개요
`watchdog` 라이브러리를 활용하여 `server/ingestion_workspace/` 하위의 데이터 유입을 실시간으로 감시하고, `AdvancedIngester`와 연동하여 자동 인제션을 수행하는 시스템을 구현 완료하였습니다.

## 2. 주요 구현 사항
- **Dynamic Watcher**: `os.walk`를 통해 워크스페이스 내 모든 `raws/` 폴더를 자동으로 찾아 Observer에 등록합니다.
- **Debounce Logic**: 파일 생성 감지 후 1초의 대기 시간을 가져 파일 복사가 완료될 때까지 대기하며, `PermissionError` 발생 시 최대 3회 재시도합니다.
- **Workflow Integration**: 인제션 완료 후 파일을 `archives/` 폴더로 이동시켜 중복 처리를 방지하고 작업 이력을 관리합니다.
- **Conflict Management**: 아카이브 이동 시 파일명이 중복될 경우 타임스탬프를 부착하여 데이터 유실을 방지합니다.

## 3. 검증 결과
- **테스트 케이스**: `inventory_master/raws/` 폴더에 신규 로그 파일 투입.
- **결과**: 파일 감지 -> `AdvancedIngester` 트리거 -> 아카이브 이동 프로세스가 100% 성공적으로 작동함을 확인하였습니다.

## 4. 향후 권장 사항
- 감시 중인 워크스페이스가 늘어날 경우를 대비해 스레드 풀 기반의 비동기 처리 도입 고려.
- 워크스페이스별 에러 발생 시 알림 시스템(WebSocket push) 연동.
