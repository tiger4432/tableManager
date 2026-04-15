# 📝 Agent Report: Directory Watcher Refactoring (Agent I)

## 1. 작업 개요
서버 통합을 위해 `directory_watcher.py`에 로그 분리 기능을 추가하고, 서버 메인 루프를 방해하지 않도록 비차단(Non-blocking) 실행 구조로 리팩토링을 완료했습니다.

## 2. 변경 사항
- **로그 분리**: `server/watcher.log` 파일에 로그를 독점적으로 기록하도록 `FileHandler`를 추가했습니다. 터미널(stdout) 출력과 병행됩니다.
- **실행 구조 개선**: `WorkspaceWatcher.start(blocking=True/False)` 인자를 추가하여, 서버에서 호출 시 백그라운드 스레드에서 즉시 반환될 수 있도록 조치했습니다.
- **경로 최적화**: 임포트 환경에 구애받지 않도록 `os.path.abspath(__file__)` 기반으로 모든 설정 파일 경로를 절대화했습니다.

## 3. 수정 파일
- `server/parsers/directory_watcher.py`

## 4. 특이 사항
- `watchdog` 라이브러리의 `Observer.start()`는 이미 별도의 데몬 스레드에서 작동하므로, 서버의 `on_event("startup")`에서 `blocking=False`로 호출하면 안전하게 통합됩니다.

---
*담당 에이전트: Agent I*
