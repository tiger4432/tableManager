# 프로젝트 이력: WebSocket 신뢰성 복구 및 수동 수정(Manual Fix) 동기화 고도화 (2026-04-12)

## 1. 개요
클라이언트 시작 시 발생하던 WebSocket 기동 누락 및 데이터 미노출 결함을 근본적으로 해결하고, 다중 사용자 환경에서의 수동 수정 사항 추적 능력을 강화함.

## 2. 상세 작업 내용

### 2.1 WebSocket 기동 무결성 확보 (Initialization Fix)
- **문제 현상**: 서버 응답 지연 시 클라이언트가 에러 폴백(Fallback)으로 진입하면서 WebSocket 리스너 시작 명령이 누락됨.
- **원인 분석**: `_load_all_tables`의 `error` 시그널 핸들러에 `_start_shared_ws()` 호출이 누락되어 있었음.
- **해결 방안**: 모든 초기화 경로(성공/실패)에서 반드시 WebSocket 스레드를 실행하도록 구조 개선.

### 2.2 비동기 워커 가비지 컬렉션(GC) 이슈 해결
- **문제 현상**: API 요청은 성공하나 콜백(`_on_tables_loaded`)이 호출되지 않아 화면이 멈춰 있는 현상.
- **원인 분석**: `QRunnable` 객체가 Python 로컬 변수로만 존재하여 작업 완료 전 GC에 의해 해제되면서 시그널 객체도 소멸함.
- **해결 방안**: `self._active_workers` 멤버 변수를 도입하여 작업 종료 시점까지 워커 레퍼런스를 강제 유지하는 수동 메모리 관리 적용.

### 2.3 수동 수정(Manual Fix) 시각화 및 사용자 추적
- **개선 요약**: 타 사용자의 수동 개입 사항을 자동 업데이트와 시각적으로 명확히 분리함.
- **서버 조치**: `broadcast` 패킷에 `updated_by` 필드와 `is_overwrite` 플래그를 포함하도록 확장.
- **클라이언트 조치**:
  - `setData` 시 로컬 OS 사용자명을 획득하여 `Manual Fix (User)` 형태로 전송.
  - 히스토리 패널에서 `is_overwrite=True`인 이벤트를 `🛠️ [원격 수동수정]` 라벨과 노란색(#f9e2af) 테마로 강조.

## 3. 관련 파일 변경 사항
- `server/main.py`: WebSocket 브로드캐스트 페이로드 확장 (`updated_by` 추가).
- `client/main.py`: 초기화 에러 핸들러 보강 및 워커 GC 방지 로직 도입.
- `client/models/table_model.py`: `setData` 시 사용자 식별자 생성 및 전송.
- `client/ui/panel_history.py`: 수동 수정 전용 아이콘 및 색상 필터링 적용.

## 4. 최종 결과
- **신뢰성**: 어떤 상황에서도 앱 시작 시 WebSocket 연결이 반드시 보장됨.
- **가시성**: 타 사용자의 수동 수정 내역을 즉각적으로 구분 및 추적 가능 (Audit 지원).
- **성능**: 불필요한 타이머 지연 제거로 초기 로딩 속도 최적화.

---
**기록자: Antigravity (PM/Lead)**
