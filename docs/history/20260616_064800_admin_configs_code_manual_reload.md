# Manual Configurations and Code Hot-Reloading Trigger in Admin Console

## 1. 개요 (Overview)
- **목적**: 매번 실행 시 자동 핫스왑을 수행하는 대신, 사용자가 코드 및 설정 수정을 완료하고 검증한 후 원하는 시점에 수동으로 핫 리로드를 명령할 수 있는 시스템 갱신 메커니즘 제공
- **작성일**: 2026년 06월 16일

## 2. 변경 내용 (Changes)
### 2.1 Backend 핫 리로드 API 및 분산 동기화 구현 (`server/`)
- **웹 서버 리로드 엔드포인트 개설 (`server/main.py`)**:
  - `POST /admin/reload-configs` 개설: 웹 서버 자체 프로세스의 맵퍼/파서 모듈 캐시(`sys.modules`)를 pop(제거)하고 `table_config.json` 설정을 갱신
  - 다른 독립 데몬 프로세스들로 핫-리로드 지시를 전파하기 위해 `DatabaseOutbox`에 `event_type="SYSTEM_RELOAD"` 이벤트를 발행 및 commit(PostgreSQL NOTIFY 트리거 실행)
- **독립 데몬 워커들의 실시간 갱신 수렴 기법 구현 (`server/chain_ingestion_worker.py`, `server/run_watcher.py`)**:
  - DB 트랜잭션 경합을 방지하고 각 프로세스가 1회씩 리로드하도록 **최종 적용 이벤트 ID 트래커 (`last_reload_event_id`)** 설계 적용
  - 각 데몬 프로세스들의 루프가 돌 때마다 Outbox의 최근 `SYSTEM_RELOAD` 이벤트 ID가 로컬의 `last_reload_event_id`보다 큰 경우, 자신의 파서 플러그인 캐시 및 맵퍼 모듈 캐시(`sys.modules`)를 리셋하고 체인 룰 규칙(`chain_rules.json`)을 디스크에서 갱신

### 2.2 Frontend UI 명시적 리로드 버튼 추가 (`client2/admin.html`, `client2/src/admin.js`)
- 어드민 콘솔 헤더 영역에 노란색 테두리의 **"⚙️ Reload Configs & Code"** 버튼을 추가하여 미적 일관성을 확보
- 클릭 시 사용자에게 최종 재확인 컨펌창을 노출하고, `POST /admin/reload-configs`를 비동기 호출
- 리로드 성공 시 "🚀 시스템 설정 및 파이썬 코드가 성공적으로 핫-리로드되었습니다." 토스트 피드백 알림 출력 후 목록 갱신

### 2.3 컴파일 및 무결성 검증
- Vite 빌드 및 13개 단위 테스트 전체 100% 통과(Passed) 검증 완료
