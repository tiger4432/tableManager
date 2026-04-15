# 📝 Agent Report: Server-Watcher Lifecycle Integration (Agent Stability)

## 1. 작업 개요
FastAPI 서버 기동 시 `directory_watcher`가 자동으로 시작되고, 종료 시 안전하게 리소스를 반환하도록 수명 주기(Lifecycle) 통합을 완료했습니다.

## 2. 변경 사항
- **이벤트 핸들러 구현**:
    - `@app.on_event("startup")`: 서버 시작 시 `WorkspaceWatcher`를 초기화하고 비차단 모드로 실행합니다.
    - `@app.on_event("shutdown")`: 서버 종료 시 `observer.stop()` 및 `join()`을 수행하여 데몬 스레드가 고아화되지 않도록 처리했습니다.
- **예외 처리**: 워처 기동 중 오류가 발생하더라도 메인 서버의 기동이 차단되지 않도록 `try-except` 블록을 구성했습니다.
- **의존성 관리**: `parsers` 디렉토리 하위 모듈이 성공적으로 로드될 수 있도록 `sys.path` 및 임포트 구문을 최적화했습니다.

## 3. 수정 파일
- `server/main.py`

## 4. 특이 사항
- 서버 실행 시 터미널 로그에 `[Startup] Directory Watcher started` 문구가 출력되며, 구체적인 파일 감지 및 인제션 과정은 `server/watcher.log`에서 실시간으로 확인할 수 있습니다.

---
*담당 에이전트: Agent Stability*
