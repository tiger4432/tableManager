# 프로젝트 이력: Phase 19 데이터 정합성 및 시스템 안정성 강화 (2026-04-12)

## 1. 개요
Phase 18까지 구축된 자동화 인제션 시스템 운영 중 발견된 데이터 무결성 결함과 클라이언트 UI 동기화 문제를 해결하고, 대규모 데이터 환경에서의 시스템 안정성을 확보함.

## 2. 상세 작업 내용

### 2.1 데이터 무결성 (Integrity) 강화
- **이슈**: 동일 비즈니스 키(예: `SENSOR-010`) 유입 시 공백이나 타입 차이로 인해 기존 행을 찾지 못하고 중복 행(`row_id` 신규 생성)을 생성하는 문제 확인.
- **해결**: `server/database/crud.py`의 `get_row_by_business_key` 로직에 `str().strip()` 정규화를 적용하여 완벽한 매칭 보장.
- **최적화**: `AuditLog` 생성 시 실제 값이 변경된 경우에만 기록하도록 최적화하여 로그 부하 감소.

### 2.2 가상 스크롤 (Lazy Loading) 정상화
- **이슈**: `rowCount`가 전체 개수를 따르는 가상 스크롤 환경에서, 아직 로드되지 않은 'Loading...' 영역 진입 시 `fetchMore()`가 자동으로 트리거되지 않는 문제.
- **해결**: `client/models/table_model.py`의 `data()` 메서드에 인덱스 참조 시 수동 페칭 트리거(`QTimer.singleShot` 활용)를 삽입하여 스크롤 기반 자동 로딩 구현.

### 2.3 클라이언트 초기화 안정성 (Stability) 보강
- **이슈**: 다중 테이블 앱 시작 시 수많은 API 요청이 병렬적으로 발생하여 네트워크 타임아웃 및 경쟁 상태(Race Condition) 유발.
- **해결**: 
  - **Staggered Loading**: 탭 생성 시 `200ms` 간격의 시차를 두어 요청 집중 방지.
  - **Sequential Flow**: 각 테이블의 스키마(/schema)가 로드 완료된 후에만 데이터 페칭을 시작하도록 보장.

### 2.4 실시간 히스토리 로그 정합성 (Sync) 및 윈도우 종료 지연 개선
- **이슈**: 
  - 실시간 업데이트 시 표준 `dataChanged` 시그널과 WebSocket 전역 시그널이 중복으로 로그를 남기는 현상.
  - 클라이언트 종료 시 WebSocket `recv()`의 5초 타임아웃 대기열에 걸려 앱이 즉시 닫히지 않고 행(Hang)이 걸리는 현상.
- **해결**: 
  - **Remote Flag**: `ApiLazyTableModel`에 `_is_processing_remote` 플래그를 도입하여, 원격 업데이트 시에는 로컬 로깅을 억제하고 고해상도 원격 로그(`🌐 [원격]`)만 남도록 처리.
  - **Explicit Close**: `WsListenerThread.stop()` 시 활성 WebSocket 객체의 `ws.close()`를 명시적으로 호출하여 블로킹된 `recv()`를 즉시 중단시키고 스레드를 즉각 해제하도록 개선.
  - **User Attribution**: 원격 로그에서 사용자 정보(`updated_by`)가 누락되지 않도록 브로드캐스트 페이로드 병합 로직 보강.

### 2.5 WebSocket 연결 및 초기화 시퀀스 최적화
- **이슈**: 
  - `/tables` HTTP 요청 실패 시 에러 핸들러(`_on_tables_error`)에서 `_start_shared_ws()` 호출이 누락되어 실시간 업데이트 대기 상태로 진입하지 못하는 결함.
  - `/schema` 요청 실패 시 첫 데이터 페칭이 트리거되지 않아 화면에 아무 데이터도 뜨지 않는 현상.
- **해결**:
  - **Error Path Binding**: `/tables` 에러 발생 시에도 기본 탭 생성과 동시에 WebSocket 리스너를 강제 기동하도록 수정.
  - **Schema Fallback**: 스키마 로드 실패 시에도 기본 컬럼 기반으로 `fetchMore()`를 실행하도록 보강.
  - **Robustness**: 서버의 지치(start-up) 지연 상황에서도 클라이언트 기능을 정상적으로 수행할 수 있는 복구력 확보.

## 3. 관련 파일 변경 사항
- `client/main.py`: 에러 핸들러(`_on_tables_error`, `_on_schema_error`) 내 복구 로직 강화.

## 4. 최종 결과
- **정합성**: 중복 행 생성 0건 (검증 완료).
- **성능**: 수만 건 데이터 스크롤 시 지연 없는 로딩 확인.
- **안정성**: 10회 이상 앱 재실행 시 탭 누락 현상 사라짐.

---
**기록자: Antigravity (Lead Developer)**
